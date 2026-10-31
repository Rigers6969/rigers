@echo off
cd /d "%~dp0"
title Wayne Factory - making a science Short
echo Making "The Radium Girls" Short for The Forgotten Lab (takes 3-6 minutes)...
echo.
python photo_short.py stories\radium_girls.json
echo.
echo Open Wayne Factory - Autopilot - My videos to watch and download it.
start "" "content\forgotten-lab-radium-girls-short"
pause
