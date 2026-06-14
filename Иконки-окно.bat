@echo off
rem ASCII-only starter for the GUI window. All Russian UI lives in gui.py (UTF-8 safe).
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Python venv not found: "%PY%"
  echo Check that the .venv folder sits next to this file.
  pause
  exit /b 1
)
"%PY%" "%~dp0gui.py"
