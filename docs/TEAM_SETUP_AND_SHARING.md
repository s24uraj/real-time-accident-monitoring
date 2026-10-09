# Team Setup and Sharing Guide

## 1. What each team member needs on their laptop

### Minimum software
- Windows 10 or Windows 11
- Python 3.10 or above
- Arduino IDE 2.x
- Google Chrome or any modern browser
- Internet connection for weather API and Telegram alerts

### Python packages
These are installed automatically from `requirements.txt`:
- `pyserial`
- `requests`
- `python-dotenv`

### Arduino libraries
Install in Arduino IDE:
- `TinyGPSPlus`
- `LiquidCrystal` (default)
- `Wire` (default)

### USB driver for ESP32
Depending on the ESP32 board, install one of these if the board is not detected:
- CP210x driver
- CH340 driver

## 2. If they want the full project working

They need:
- The full project folder
- One ESP32 board with the connected hardware
- Uploaded firmware: `esp32_accident_monitor.ino`
- A correct `.env` file
- The correct COM port in `.env`

Hardware required for full live demo:
- ESP32
- MPU6050
- 16x2 LCD
- NEO-6M GPS
- Active buzzer
- Crash switch / limit switch
- Push button
- Small motor

## 3. Best way to share the project

### Share these items
- Entire project folder
- `.env.example`
- `README.md`
- `launch_demo.bat`
- `esp32_accident_monitor.ino`
- Any screenshots / documentation files

### Do not share publicly
- Real Telegram bot token
- Real chat IDs
- Any private API keys

If you trust your teammates and want the project to run exactly as your system does, you can privately share your real `.env` file with them. Otherwise, tell them to create their own `.env` from `.env.example`.

## 4. Setup steps on teammate laptop

1. Copy the complete project folder to the teammate laptop.
2. Open terminal in the project folder.
3. Run:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

4. Create `.env`:

```powershell
copy .env.example .env
```

5. Edit `.env` and fill:
- `SERIAL_PORT`
- `BAUD_RATE`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_IDS`
- optional weather / phone values

6. Upload `esp32_accident_monitor.ino` to ESP32 using Arduino IDE.
7. Close Arduino Serial Monitor after upload.
8. Run the project:

```powershell
.\launch_demo.bat
```

9. Open:

```text
http://127.0.0.1:8080/dashboard.html
```

## 5. Easiest working-sharing method

If your teammates only want the project to run quickly, do this:

1. Zip the entire project folder.
2. Include the already-tested `.env` file privately.
3. Tell them to change only `SERIAL_PORT` in `.env`.
4. Tell them to run `launch_demo.bat`.

This is the fastest method.

## 6. If they do not have hardware

Without ESP32 hardware, the full system will not work live.

But they can still:
- read the code
- open the dashboard HTML
- view documentation
- run image / PDF generation scripts

For full live accident demo, hardware is required.

## 7. Common issues

### Issue: `could not open port COMx`
Reason:
- Wrong COM port
- Arduino Serial Monitor is still open
- Another app is using the port

Fix:
- Close Serial Monitor
- Check Device Manager
- Update `SERIAL_PORT` in `.env`

### Issue: No Telegram alert
Reason:
- Wrong bot token
- Wrong chat ID
- Internet issue

Fix:
- Recheck `.env`
- Message bot once from Telegram
- Verify `getUpdates`

### Issue: GPS shows searching
Reason:
- No satellite lock
- Indoor environment

Fix:
- Move near open sky
- Wait for GPS fix

### Issue: Dashboard opens but no live data
Reason:
- Python monitor not running
- ESP32 not connected
- Wrong serial port

Fix:
- Run `launch_demo.bat`
- Check terminal logs
- Verify COM port

## 8. Recommended sharing checklist

Before sharing to teammates, verify:
- ESP32 code uploads successfully
- `.env` is correct
- `launch_demo.bat` works
- Dashboard opens
- Telegram test message works
- COM port note is given

## 9. Short instruction to send teammates

Use this message:

```text
Install Python and Arduino IDE, copy the project folder, create .env from .env.example, set the correct COM port, upload esp32_accident_monitor.ino, close Serial Monitor, and run launch_demo.bat.
```
