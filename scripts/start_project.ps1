$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (!(Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "Creating virtual environment..."
  python -m venv .venv
}

Write-Host "Installing/updating dependencies..."
.\.venv\Scripts\python.exe -m pip install -r requirements.txt | Out-Host

if (!(Test-Path ".env")) {
  Write-Host ".env not found. Creating from .env.example"
  Copy-Item .env.example .env
  Write-Host "Please edit .env with your real API keys and phone numbers, then rerun."
  exit 1
}

Write-Host "Starting dashboard server on http://127.0.0.1:8080/dashboard.html"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; python -m http.server 8080"

Write-Host "Starting laptop monitor..."
.\.venv\Scripts\python.exe -u laptop_monitor.py
