@echo off
cd /d "%~dp0"

echo Stopping old Python processes...
taskkill /F /IM python.exe >nul 2>&1

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

if not exist ".env" (
  echo .env not found. Creating from .env.example
  copy ".env.example" ".env" >nul
  echo Edit .env with real keys and phone numbers, then run again.
  pause
  exit /b 1
)

echo Launching dashboard server...
start "Dashboard Server" cmd /k "cd /d %~dp0 && python -m http.server 8080"

echo Launching laptop monitor...
start "Laptop Monitor" cmd /k "cd /d %~dp0 && .\.venv\Scripts\python -u laptop_monitor.py"

echo Done.
echo Open: http://127.0.0.1:8080/dashboard.html
