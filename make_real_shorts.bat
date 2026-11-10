@echo off
cd /d "%~dp0"
title TOP G - making real-footage Shorts
echo Making 3 real-footage Paper Trail Shorts (about 3-5 minutes each)...
echo Needs the free Pexels/Pixabay keys: TOP G - Autopilot - Stock video and photos.
echo.
for %%s in (real_blockbuster real_archegos real_paperclip) do python real_short.py stories\%%s.json
echo.
echo Done - open TOP G - Autopilot - My videos, or the folders in content\
start "" "content"
pause
