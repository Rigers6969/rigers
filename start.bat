@echo off
cd /d "%~dp0"
title Wayne Factory
start "" cmd /c "timeout /t 4 >nul & start http://localhost:5001/produce.html"
python web_server.py
pause
