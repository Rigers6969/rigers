@echo off
cd /d "%~dp0"
title Clip Factory
where python >nul 2>&1 || (echo Python is not installed - get it from python.org and tick "Add python.exe to PATH". & pause & exit /b)
where ffmpeg >nul 2>&1 || echo WARNING: ffmpeg was not found - clips cannot be cut until it is installed. See README.md.
if not exist ".installed" (
  echo First run: installing what Clip Factory needs, this takes a minute...
  python -m pip install -r requirements.txt || (echo Install failed - check your internet and run start.bat again. & pause & exit /b)
  echo ok> .installed
)
start "" cmd /c "timeout /t 3 >nul & start http://localhost:5003"
python clip_app.py
pause
