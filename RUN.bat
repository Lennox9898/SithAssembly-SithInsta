@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if /I "%~1"=="dev" (
  "%PYTHON_EXE%" app.py --dev
) else (
  "%PYTHON_EXE%" app.py
)
