@echo off
cd /d "%~dp0"
start "" cmd /c "timeout /t 3 >nul & start http://localhost:5002"
python voice_app.py
pause
