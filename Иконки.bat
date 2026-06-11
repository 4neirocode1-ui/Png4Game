@echo off
rem ASCII-only launcher. All Russian UI lives in launcher.py (UTF-8 safe).
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Python venv not found: "%PY%"
  echo Check that the .venv folder sits next to this file.
  pause
  exit /b 1
)
"%PY%" "%~dp0launcher.py"
