# Real-Time Accident Monitoring and Risk Prediction

A student project combining ESP32-based accident-event sensing, a Python monitoring application, weather context, location reporting, messaging alerts, and a browser dashboard.

> **Project status:** This repository includes an MVP integration and a demonstration vision-state writer. The included `vision_bridge_writer.py` produces simulated example probabilities; it is not a trained DenseNet/LSTM inference implementation. Do not treat this prototype as a certified vehicle safety system or rely on it for real emergency response.

## Features in the project

- ESP32 firmware for motion/impact-related inputs and local indicators.
- Python serial monitor and risk-scoring workflow.
- Weather data retrieval from Open-Meteo.
- Optional Telegram, SMS-provider, and ThingSpeak integrations when configured with your own credentials.
- HTML dashboard for displaying status, score, sensor readings, weather, and coordinates.
- Vision-state JSON bridge interface for future model integration.

## Repository layout

```text
firmware/esp32/       ESP32 Arduino sketch
src/                  Python monitor, vision demo writer, dashboard
scripts/              Windows launch scripts
docs/                 Project report, presentation, team setup guide, paper
examples/              Example JSON schemas (not live runtime data)
requirements.txt       Python dependencies
.env.example           Safe configuration template
```

## Requirements

- Windows 10/11 (launch scripts are Windows-oriented)
- Python 3.10 or newer
- Arduino IDE with ESP32 board support
- ESP32 and the sensors/peripherals described in the report for hardware testing
- Internet connection for weather and any configured alert services

## Setup

1. Clone or download this repository.
2. Open a terminal in the repository root and create a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Create your local configuration file:

   ```powershell
   Copy-Item .env.example .env
   ```

4. Edit `.env` with your own settings. Set `SERIAL_PORT` to the ESP32's actual COM port. Add only your own API keys and recipient IDs locally. **Never commit `.env`.**
5. In Arduino IDE, install `TinyGPSPlus`, select the correct ESP32 board and port, then upload `firmware/esp32/esp32_accident_monitor.ino`. Check the sketch's pin mapping before connecting hardware.
6. Close Arduino Serial Monitor if the Python application needs the same serial port.
7. Start the Python monitor from the repository root:

   ```powershell
   python src/laptop_monitor.py
   ```

8. Open `src/dashboard.html` in a browser only if your application setup serves the expected live state endpoint. For the bundled launchers, review paths before running because the original scripts may assume files are located together in one folder.

## Demo vision-state writer

The demo writer emits simulated values for testing the integration contract. From the repository root, run:

```powershell
python src/vision_bridge_writer.py
```

It writes `vision_state.json` in the current working directory. Replace this demo logic with your actual trained model's inference output before claiming real AI-based predictions.

## Hardware notes

See `docs/TEAM_SETUP_AND_SHARING.md` and the project report for components and pin mapping. Use a suitable motor driver/transistor and protection diode for the DC motor; never drive a motor directly from an ESP32 GPIO. Test alerts with dummy recipients before enabling any real notifications.

## Academic documents

- `docs/project-report.pdf`
- `docs/project-presentation.pptx`
- `docs/conference-paper.pdf`

The report and paper include team and institution information. Confirm all team members are comfortable with public publication before making the repository public.

## Limitations

- The bundled vision writer is simulated, not a trained inference model.
- Risk thresholds are prototype logic and have not been validated for road-safety use.
- Weather/API/alert integrations require internet access and individually configured credentials.
- GPS may not obtain a fix indoors.

## License

No license has been selected yet. Until a license is added, do not assume others have permission to reuse or redistribute this project's code or documents.
