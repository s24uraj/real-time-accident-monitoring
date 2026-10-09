import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests
import serial
from dotenv import load_dotenv

load_dotenv()

SERIAL_PORT = os.getenv("SERIAL_PORT", "COM5")
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))
READ_TIMEOUT = 1.5

# Fallback location if GPS is not valid
DEFAULT_LAT = float(os.getenv("DEFAULT_LAT", "16.5062"))
DEFAULT_LON = float(os.getenv("DEFAULT_LON", "80.6480"))

# API configs
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
THINGSPEAK_API_KEY = os.getenv("THINGSPEAK_API_KEY", "")
THINGSPEAK_URL = "https://api.thingspeak.com/update"

FAST2SMS_API_KEY = os.getenv("FAST2SMS_API_KEY", "")
FAST2SMS_ROUTE_URL = "https://www.fast2sms.com/dev/bulkV2"
FAST2SMS_ROUTE = os.getenv("FAST2SMS_ROUTE", "q")
SMS_DEBUG = os.getenv("SMS_DEBUG", "0") == "1"
DRIVER_PHONE = os.getenv("DRIVER_PHONE", "")
EMERGENCY_PHONES = [p.strip() for p in os.getenv("EMERGENCY_PHONES", "").split(",") if p.strip()]
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_IDS = [c.strip() for c in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]

# Logic thresholds
PRE_ALERT_SCORE = 55
ACCIDENT_SCORE = 78
PRE_ALERT_COOLDOWN_SEC = 60
ACCIDENT_COOLDOWN_SEC = 120
WEATHER_REFRESH_SEC = 300
VISION_STATE_FILE = Path(os.getenv("VISION_STATE_FILE", "vision_state.json"))
LIVE_STATE_FILE = Path(os.getenv("LIVE_STATE_FILE", "live_state.json"))
SERIAL_CMD_GAP_SEC = 0.8

last_pre_alert_ts = 0.0
last_accident_ts = 0.0
last_weather_ts = 0.0
cached_weather = {}
last_command = ""
last_command_ts = 0.0
current_device_state = "NORMAL"
last_heartbeat_ts = 0.0


def masked(v: str) -> str:
  if not v:
    return "MISSING"
  if len(v) <= 6:
    return "***"
  return f"{v[:3]}***{v[-3:]}"


def safe_console_print(text: str) -> None:
  # Avoid rare Windows console write crashes from non-printable serial bytes.
  cleaned = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "?", text)
  try:
    print(cleaned)
  except OSError:
    pass


def write_live_state(payload: dict) -> None:
  try:
    LIVE_STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  except Exception:
    pass


def read_vision_state() -> dict:
  # Expected schema:
  # {
  #   "accident_prob": 0.0..1.0,
  #   "sequence_risk_prob": 0.0..1.0,
  #   "label": "accident|non_accident",
  #   "updated_at": "ISO string"
  # }
  if not VISION_STATE_FILE.exists():
    return {}
  try:
    state = json.loads(VISION_STATE_FILE.read_text(encoding="utf-8"))
    return state if isinstance(state, dict) else {}
  except Exception:
    return {}


def send_fast2sms(message: str, numbers: list[str]) -> bool:
  if not FAST2SMS_API_KEY or not numbers:
    return False

  normalized = []
  for n in numbers:
    d = "".join(ch for ch in n if ch.isdigit())
    if len(d) == 12 and d.startswith("91"):
      d = d[2:]
    normalized.append(d)
  normalized = [n for n in normalized if len(n) == 10]
  if not normalized:
    safe_console_print("[SMS] No valid 10-digit numbers after normalization.")
    return False

  headers = {
      "authorization": FAST2SMS_API_KEY,
      "Content-Type": "application/x-www-form-urlencoded",
      "Cache-Control": "no-cache",
  }
  payload = {
      "route": FAST2SMS_ROUTE,
      "sender_id": "FSTSMS",
      "message": message,
      "language": "english",
      "flash": 0,
      "numbers": ",".join(normalized),
  }
  try:
    r = requests.post(FAST2SMS_ROUTE_URL, headers=headers, data=payload, timeout=10)
    ok = r.status_code == 200
    if SMS_DEBUG or not ok:
      safe_console_print(f"[SMS] status={r.status_code} response={r.text[:220]}")
    return ok
  except Exception:
    return False


def send_telegram(message: str, chat_ids: list[str] | None = None) -> bool:
  if not TELEGRAM_BOT_TOKEN:
    return False
  targets = chat_ids if chat_ids else TELEGRAM_CHAT_IDS
  if not targets:
    return False

  ok_any = False
  for chat_id in targets:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
      r = requests.post(url, data=payload, timeout=10)
      ok = r.status_code == 200
      ok_any = ok_any or ok
      if SMS_DEBUG or not ok:
        safe_console_print(f"[TELEGRAM] chat={chat_id} status={r.status_code} response={r.text[:220]}")
    except Exception as e:
      if SMS_DEBUG:
        safe_console_print(f"[TELEGRAM] chat={chat_id} error={e}")
  return ok_any


def send_thingspeak(status: str, severity: str, lat: float, lon: float, score: float) -> bool:
  if not THINGSPEAK_API_KEY:
    return False
  params = {
      "api_key": THINGSPEAK_API_KEY,
      "field1": f"{score:.2f}",
      "field2": f"{lat:.6f}",
      "field3": f"{lon:.6f}",
      "field4": "1" if status == "ACCIDENT" else "0",
      "field5": "1" if status == "RISK_WARNING" else "0",
      "status": f"{status} | Severity={severity}",
  }
  try:
    r = requests.get(THINGSPEAK_URL, params=params, timeout=10)
    return r.status_code == 200 and r.text.strip() != "0"
  except Exception:
    return False


def maybe_send_command(ser: serial.Serial, command: str) -> None:
  global last_command, last_command_ts
  now = time.time()
  if command == last_command and (now - last_command_ts) < SERIAL_CMD_GAP_SEC:
    return
  ser.write(f"{command}\n".encode("utf-8"))
  last_command = command
  last_command_ts = now


def fetch_weather(lat: float, lon: float) -> dict:
  global last_weather_ts, cached_weather
  now = time.time()
  if cached_weather and (now - last_weather_ts) < WEATHER_REFRESH_SEC:
    return cached_weather

  params = {
      "latitude": lat,
      "longitude": lon,
      "current": "temperature_2m,precipitation,rain,weather_code,wind_speed_10m,visibility",
      "timezone": "auto",
  }
  try:
    r = requests.get(OPEN_METEO_URL, params=params, timeout=10)
    r.raise_for_status()
    current = r.json().get("current", {})
    cached_weather = {
        "rain": float(current.get("rain", 0.0) or 0.0),
        "precipitation": float(current.get("precipitation", 0.0) or 0.0),
        "wind": float(current.get("wind_speed_10m", 0.0) or 0.0),
        "visibility": float(current.get("visibility", 10000.0) or 10000.0),
        "weather_code": int(current.get("weather_code", 0) or 0),
    }
    last_weather_ts = now
  except Exception:
    if not cached_weather:
      cached_weather = {"rain": 0.0, "precipitation": 0.0, "wind": 0.0, "visibility": 10000.0, "weather_code": 0}
  return cached_weather


def severity_label(score: float) -> str:
  if score >= 80:
    return "HIGH"
  if score >= 60:
    return "MEDIUM"
  return "LOW"


def derive_event_severity(data: dict, score: float) -> str:
  # Requested mapping:
  # - Crash sensor press => LOW
  # - Sudden impact => MEDIUM
  # - Vigorous shake => HIGH
  motion_level = int(data.get("motionLevel", 0) or 0)  # 0,1,2 from ESP32
  crash_switch = (int(data.get("limit", 1)) == 0)

  if motion_level >= 2:
    return "HIGH"
  if motion_level == 1:
    return "MEDIUM"
  if crash_switch:
    return "LOW"
  return severity_label(score)


def calculate_risk_score(data: dict, weather: dict, vision: dict | None = None) -> float:
  impact = float(data.get("impact", 0.0))
  ax = abs(float(data.get("ax", 0.0)))
  ay = abs(float(data.get("ay", 0.0)))
  az = abs(float(data.get("az", 0.0)))
  crash_switch = (int(data.get("limit", 1)) == 0)

  score = 0.0
  score += min(45.0, impact * 28.0)
  score += min(20.0, (ax + ay) * 2.8)
  score += max(0.0, 10.0 - abs(az - 1.0) * 5.0)

  if crash_switch:
    score += 30.0

  rain = weather.get("rain", 0.0)
  precipitation = weather.get("precipitation", 0.0)
  wind = weather.get("wind", 0.0)
  visibility = weather.get("visibility", 10000.0)

  if rain > 0.2 or precipitation > 0.5:
    score += 8.0
  if wind > 25:
    score += 6.0
  if visibility < 2000:
    score += 12.0

  if vision:
    accident_prob = float(vision.get("accident_prob", 0.0) or 0.0)
    sequence_prob = float(vision.get("sequence_risk_prob", 0.0) or 0.0)
    score += min(25.0, accident_prob * 20.0)
    score += min(20.0, sequence_prob * 15.0)

  return max(0.0, min(100.0, score))


def print_status_block(
    data: dict,
    lat: float,
    lon: float,
    status: str,
    severity: str | None = None,
    vision: dict | None = None,
) -> None:
  print("\n------ Accident Monitoring System ------")
  print("\nAccelerometer Data")
  print(f"X-axis: {float(data.get('ax', 0.0)):.2f}")
  print(f"Y-axis: {float(data.get('ay', 0.0)):.2f}")
  print(f"Z-axis: {float(data.get('az', 0.0)):.2f}")
  print("\nLocation")
  print(f"Latitude : {lat:.4f}")
  print(f"Longitude: {lon:.4f}")
  if severity:
    print(f"\nSeverity: {severity}")
  if vision:
    print("\nVision Model")
    print(f"Accident Prob : {float(vision.get('accident_prob', 0.0) or 0.0):.2f}")
    print(f"Sequence Risk : {float(vision.get('sequence_risk_prob', 0.0) or 0.0):.2f}")
    label = str(vision.get("label", "") or "").strip()
    if label:
      print(f"Label         : {label}")
  print(f"\nStatus: {status}")
  print("----------------------------------------")


def run():
  global last_pre_alert_ts, last_accident_ts, current_device_state, last_heartbeat_ts
  print(f"Opening serial port {SERIAL_PORT} @ {BAUD_RATE} ...")
  print(
      "Config | "
      f"ThingSpeak={masked(THINGSPEAK_API_KEY)} | "
      f"Fast2SMS={masked(FAST2SMS_API_KEY)} | "
      f"TelegramToken={masked(TELEGRAM_BOT_TOKEN)} | "
      f"TelegramChats={len(TELEGRAM_CHAT_IDS)} | "
      f"Driver={masked(DRIVER_PHONE)} | "
      f"EmergencyCount={len(EMERGENCY_PHONES)}"
  )
  ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=READ_TIMEOUT)
  time.sleep(2)

  while True:
    now = time.time()
    raw = ser.readline().decode("utf-8", errors="ignore").strip()
    if not raw:
      if (now - last_heartbeat_ts) >= 2.0:
        safe_console_print(f"[HEARTBEAT] monitor alive | device_state={current_device_state}")
        last_heartbeat_ts = now
      continue
    if raw.startswith("ACK:"):
      safe_console_print(f"[ESP32] {raw}")
      continue
    if not raw.startswith("{"):
      continue

    try:
      data = json.loads(raw)
    except json.JSONDecodeError:
      continue

    gps_valid = int(data.get("gps_valid", 0)) == 1
    lat = float(data.get("lat", DEFAULT_LAT)) if gps_valid else DEFAULT_LAT
    lon = float(data.get("lon", DEFAULT_LON)) if gps_valid else DEFAULT_LON
    weather = fetch_weather(lat, lon)
    vision = read_vision_state()
    score = calculate_risk_score(data, weather, vision)
    severity = derive_event_severity(data, score)
    local_accident = int(data.get("localAccident", 0)) == 1
    vision_hard_trigger = float(vision.get("accident_prob", 0.0) or 0.0) >= 0.92

    now = time.time()
    accident_triggered = local_accident or (score >= ACCIDENT_SCORE) or vision_hard_trigger
    pre_alert_triggered = (score >= PRE_ALERT_SCORE) and not accident_triggered

    desired_state = "NORMAL"
    if accident_triggered:
      desired_state = "ACCIDENT"
    elif pre_alert_triggered:
      desired_state = "PREALERT"

    if desired_state != current_device_state:
      if desired_state == "ACCIDENT":
        maybe_send_command(ser, "CMD:ACCIDENT")
      elif desired_state == "PREALERT":
        maybe_send_command(ser, "CMD:PREALERT")
      else:
        maybe_send_command(ser, "CMD:CLEAR")
      current_device_state = desired_state

    if desired_state == "ACCIDENT":
      live_payload = {
          "timestamp": datetime.now().isoformat(timespec="seconds"),
          "status": "ACCIDENT DETECTED",
          "severity": severity,
          "score": round(score, 2),
          "ax": round(float(data.get("ax", 0.0)), 3),
          "ay": round(float(data.get("ay", 0.0)), 3),
          "az": round(float(data.get("az", 0.0)), 3),
          "impact": round(float(data.get("impact", 0.0)), 3),
          "motion_level": int(data.get("motionLevel", 0) or 0),
          "lat": round(lat, 6),
          "lon": round(lon, 6),
          "maps_url": f"https://maps.google.com/?q={lat:.6f},{lon:.6f}",
          "vision": vision or {},
          "weather": weather or {},
          "device_state": current_device_state,
      }
      write_live_state(live_payload)
      if (now - last_accident_ts) >= ACCIDENT_COOLDOWN_SEC:
        last_accident_ts = now
        msg = (
            "ACCIDENT DETECTED! "
            f"Severity={severity}, "
            f"Location={lat:.6f},{lon:.6f}, "
            f"Maps=https://maps.google.com/?q={lat:.6f},{lon:.6f}"
        )
        send_thingspeak("ACCIDENT", severity, lat, lon, score)
        sms_ok = send_fast2sms(msg, EMERGENCY_PHONES if EMERGENCY_PHONES else [DRIVER_PHONE] if DRIVER_PHONE else [])
        tg_ok = send_telegram(msg)
        if not sms_ok and not tg_ok:
          safe_console_print("[ALERT] Neither SMS nor Telegram could be delivered.")
      print_status_block(data, lat, lon, "ACCIDENT DETECTED", severity, vision)
      print("Sending alert to emergency contacts...")
      print("\nGoogle Maps Location:")
      print(f"https://maps.google.com/?q={lat:.4f},{lon:.4f}")
      continue

    if desired_state == "PREALERT":
      live_payload = {
          "timestamp": datetime.now().isoformat(timespec="seconds"),
          "status": "RISK WARNING",
          "severity": severity,
          "score": round(score, 2),
          "ax": round(float(data.get("ax", 0.0)), 3),
          "ay": round(float(data.get("ay", 0.0)), 3),
          "az": round(float(data.get("az", 0.0)), 3),
          "impact": round(float(data.get("impact", 0.0)), 3),
          "motion_level": int(data.get("motionLevel", 0) or 0),
          "lat": round(lat, 6),
          "lon": round(lon, 6),
          "maps_url": f"https://maps.google.com/?q={lat:.6f},{lon:.6f}",
          "vision": vision or {},
          "weather": weather or {},
          "device_state": current_device_state,
      }
      write_live_state(live_payload)
      if (now - last_pre_alert_ts) >= PRE_ALERT_COOLDOWN_SEC:
        last_pre_alert_ts = now
        warn_msg = (
            "RISK WARNING: Accident likely due to motion/weather. "
            f"Severity={severity}, "
            f"Location={lat:.6f},{lon:.6f}"
        )
        send_thingspeak("RISK_WARNING", severity, lat, lon, score)
        send_telegram(warn_msg)
        if DRIVER_PHONE:
          send_fast2sms(warn_msg, [DRIVER_PHONE])
      print_status_block(data, lat, lon, "RISK WARNING", severity, vision)
      print("Warning sent to driver.")
      continue

    live_payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": "NORMAL",
        "severity": None,
        "score": round(score, 2),
        "ax": round(float(data.get("ax", 0.0)), 3),
        "ay": round(float(data.get("ay", 0.0)), 3),
        "az": round(float(data.get("az", 0.0)), 3),
        "impact": round(float(data.get("impact", 0.0)), 3),
        "motion_level": int(data.get("motionLevel", 0) or 0),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "maps_url": f"https://maps.google.com/?q={lat:.6f},{lon:.6f}",
        "vision": vision or {},
        "weather": weather or {},
        "device_state": current_device_state,
    }
    write_live_state(live_payload)
    print_status_block(data, lat, lon, "NORMAL", None, vision)


if __name__ == "__main__":
  try:
    run()
  except KeyboardInterrupt:
    print(f"\nStopped at {datetime.now().isoformat(timespec='seconds')}")
