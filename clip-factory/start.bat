@echo off
cd /d "%~dp0"
title Clip Factory
where python >nul 2>&1 || (echo Python is not installed - get it from python.org and tick "Add python.exe to PATH". & pause & exit /b)
where ffmpeg >nul 2>&1 || echo WARNING: ffmpeg was not found - clips cannot be cut until it is installed. See README.md.
if not exist ".installed-v5" (
  echo Installing what Clip Factory needs, this takes a minute...
  python -m pip install -r requirements.txt || (echo Install failed - check your internet and run start.bat again. & pause & exit /b)
  echo ok> .installed-v5
)
rem YouTube downloads need a JavaScript runtime - install Deno once if there's none
where deno >nul 2>&1 && goto jsok
where node >nul 2>&1 && goto jsok
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\deno.exe" goto jsok
if exist "%USERPROFILE%\.deno\bin\deno.exe" goto jsok
echo Installing Deno, needed to download from YouTube...
winget install --id DenoLand.Deno -e --accept-source-agreements --accept-package-agreements
:jsok
rem YouTube changes often - keep the downloader up to date
echo Checking for downloader updates...
python -m pip install -U -q "yt-dlp[default,curl-cffi]" >nul 2>&1
start "" cmd /c "timeout /t 3 >nul & start http://localhost:5003"
python clip_app.py
pause
