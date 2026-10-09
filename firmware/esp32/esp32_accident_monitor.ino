#include <Wire.h>
#include <LiquidCrystal.h>
#include <TinyGPS++.h>
#include <HardwareSerial.h>

// LCD pins (RS, E, D4, D5, D6, D7)
LiquidCrystal lcd(15, 2, 4, 16, 17, 5);

// Pin map
const int BUZZER_PIN = 19;
const int MOTOR_PIN = 23;
const int LIMIT_PIN = 18;   // HIGH=open, LOW=closed (crash)
const int BUTTON_PIN = 33;  // button to GND

// MPU6050 I2C address
const uint8_t MPU_ADDR = 0x68;

// GPS: RX pin on ESP32 connected to TX of NEO-6M
HardwareSerial gpsSerial(2);
TinyGPSPlus gps;

// Runtime state
float ax = 0.0f, ay = 0.0f, az = 0.0f;
bool localAccident = false;
bool preAlert = false;
unsigned long lastSendMs = 0;
unsigned long lastLcdMs = 0;
unsigned long buzzerUntilMs = 0;
unsigned long buttonPressStartMs = 0;
float lastImpact = 0.0f;
double lastGpsLat = 0.0;
double lastGpsLon = 0.0;
bool hasGpsFix = false;

void writeMPU(uint8_t reg, uint8_t data) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(data);
  Wire.endTransmission(true);
}

bool readMPURaw(int16_t &x, int16_t &y, int16_t &z) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom((int)MPU_ADDR, 6, true) != 6) {
    return false;
  }

  x = (Wire.read() << 8) | Wire.read();
  y = (Wire.read() << 8) | Wire.read();
  z = (Wire.read() << 8) | Wire.read();
  return true;
}

void updateIMU() {
  int16_t rx, ry, rz;
  if (readMPURaw(rx, ry, rz)) {
    // MPU6050 default accel scale: +/-2g -> 16384 LSB/g
    ax = rx / 16384.0f;
    ay = ry / 16384.0f;
    az = rz / 16384.0f;
  }
}

float computeImpactIndex() {
  float mag = sqrtf(ax * ax + ay * ay + az * az);
  return fabsf(mag - 1.0f);
}

void showNormalOnLCD(double lat, double lon, bool gpsValid) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Status: NORMAL");
  lcd.setCursor(0, 1);
  if (gpsValid) {
    lcd.print(String(lat, 2) + "," + String(lon, 2));
  } else {
    lcd.print("GPS: searching");
  }
}

void showPreAlertOnLCD(float severityScore) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("RISK WARNING!");
  lcd.setCursor(0, 1);
  lcd.print("Score:");
  lcd.print(severityScore, 2);
}

void showAccidentOnLCD(double lat, double lon, bool gpsValid) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("ACCIDENT!");
  lcd.setCursor(0, 1);
  if (gpsValid) {
    lcd.print(String(lat, 2) + "," + String(lon, 2));
  } else {
    lcd.print("GPS unavailable");
  }
}

void handleIncomingCommands() {
  while (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "CMD:PREALERT") {
      preAlert = true;
      buzzerUntilMs = millis() + 300;
      showPreAlertOnLCD(computeImpactIndex());
      Serial.println("ACK:PREALERT");
    } else if (cmd == "CMD:ACCIDENT") {
      localAccident = true;
      buzzerUntilMs = millis() + 2000;
      showAccidentOnLCD(lastGpsLat, lastGpsLon, hasGpsFix);
      Serial.println("ACK:ACCIDENT");
    } else if (cmd == "CMD:CLEAR") {
      preAlert = false;
      localAccident = false;
      digitalWrite(BUZZER_PIN, LOW);
      showNormalOnLCD(lastGpsLat, lastGpsLon, hasGpsFix);
      Serial.println("ACK:CLEAR");
    }
  }
}

void handleManualResetButton() {
  // Short press: panic trigger. Hold >=2s: manual clear.
  if (digitalRead(BUTTON_PIN) == LOW) {
    if (buttonPressStartMs == 0) {
      buttonPressStartMs = millis();
    } else if ((millis() - buttonPressStartMs) >= 80 && (millis() - buttonPressStartMs) < 1200 && !localAccident) {
      localAccident = true;
      preAlert = false;
      buzzerUntilMs = millis() + 2000;
      showAccidentOnLCD(lastGpsLat, lastGpsLon, hasGpsFix);
      Serial.println("EVT:PANIC_BUTTON");
      // Prevent re-trigger until release
      buttonPressStartMs = millis() + 100000UL;
    } else if ((millis() - buttonPressStartMs) >= 2000) {
      localAccident = false;
      preAlert = false;
      digitalWrite(BUZZER_PIN, LOW);
      showNormalOnLCD(lastGpsLat, lastGpsLon, hasGpsFix);
      Serial.println("ACK:MANUAL_CLEAR");
      buttonPressStartMs = millis() + 100000UL; // one-shot until release
    }
  } else {
    buttonPressStartMs = 0;
  }
}

void sendTelemetryLine() {
  double lat = hasGpsFix ? lastGpsLat : 0.0;
  double lon = hasGpsFix ? lastGpsLon : 0.0;
  int limitState = digitalRead(LIMIT_PIN);          // LOW means crash
  int buttonPressed = (digitalRead(BUTTON_PIN) == LOW) ? 1 : 0;
  float impact = computeImpactIndex();
  float deltaImpact = fabsf(impact - lastImpact);
  lastImpact = impact;

  // Local accident fallback conditions on board
  // Higher sensitivity for shake demo:
  // impact >= 0.55g offset or sudden jump >= 0.25
  bool severeMotion = (impact >= 0.55f) || (deltaImpact >= 0.25f);
  bool crashSwitch = (limitState == LOW);
  int motionLevel = 0; // 0=none, 1=sudden impact, 2=vigorous shake
  if ((impact >= 1.20f) || (deltaImpact >= 0.60f)) {
    motionLevel = 2;
  } else if ((impact >= 0.55f) || (deltaImpact >= 0.25f)) {
    motionLevel = 1;
  }
  if (severeMotion || crashSwitch) {
    localAccident = true;
    buzzerUntilMs = millis() + 1200;
    if (!hasGpsFix) {
      showAccidentOnLCD(0, 0, false);
    } else {
      showAccidentOnLCD(lastGpsLat, lastGpsLon, true);
    }
    Serial.println("EVT:LOCAL_TRIGGER");
  }

  if (localAccident) {
    digitalWrite(MOTOR_PIN, LOW);
  } else {
    digitalWrite(MOTOR_PIN, HIGH);
  }

  Serial.print("{\"ax\":");
  Serial.print(ax, 3);
  Serial.print(",\"ay\":");
  Serial.print(ay, 3);
  Serial.print(",\"az\":");
  Serial.print(az, 3);
  Serial.print(",\"impact\":");
  Serial.print(impact, 3);
  Serial.print(",\"lat\":");
  Serial.print(lat, 6);
  Serial.print(",\"lon\":");
  Serial.print(lon, 6);
  Serial.print(",\"gps_valid\":");
  Serial.print(hasGpsFix ? 1 : 0);
  Serial.print(",\"limit\":");
  Serial.print(limitState);
  Serial.print(",\"button\":");
  Serial.print(buttonPressed);
  Serial.print(",\"localAccident\":");
  Serial.print(localAccident ? 1 : 0);
  Serial.print(",\"motionLevel\":");
  Serial.print(motionLevel);
  Serial.println("}");
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20);
  Wire.begin(21, 22);
  gpsSerial.begin(9600, SERIAL_8N1, 26, -1);

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(MOTOR_PIN, OUTPUT);
  pinMode(LIMIT_PIN, INPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(MOTOR_PIN, HIGH);

  lcd.begin(16, 2);
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Accident Monitor");
  lcd.setCursor(0, 1);
  lcd.print("Initializing...");

  // Wake MPU6050
  writeMPU(0x6B, 0x00);
  delay(200);

  showNormalOnLCD(0, 0, false);
}

void loop() {
  while (gpsSerial.available()) {
    gps.encode(gpsSerial.read());
  }
  if (gps.location.isValid()) {
    hasGpsFix = true;
    lastGpsLat = gps.location.lat();
    lastGpsLon = gps.location.lng();
  }

  updateIMU();
  handleIncomingCommands();
  handleManualResetButton();

  unsigned long now = millis();
  if (now - lastSendMs >= 1000) {
    lastSendMs = now;
    sendTelemetryLine();
  }

  if (buzzerUntilMs > now) {
    digitalWrite(BUZZER_PIN, HIGH);
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }

  if ((now - lastLcdMs >= 1500) && !localAccident && !preAlert) {
    lastLcdMs = now;
    showNormalOnLCD(lastGpsLat, lastGpsLon, hasGpsFix);
  }
}
