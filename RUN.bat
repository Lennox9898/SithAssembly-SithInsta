@echo off
setlocal
cd /d "%~dp0"

if /I "%~1"=="dev" (
  python app.py --dev
) else (
  python app.py
)
