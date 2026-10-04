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

rem OmniRoute: a free AI router (many free AIs behind one address) - install once, start it if it isn't running.
rem To never use it, create an empty file called no-omniroute.txt in this folder.
if exist "no-omniroute.txt" goto omnidone
set "PATH=%PATH%;%ProgramFiles%\nodejs;%APPDATA%\npm"
rem OmniRoute needs Node.js 24 or newer (22.22+ also works) - install or upgrade it once
where node >nul 2>&1 || goto nodeinstall
node -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a>=24||(a===22&&b>=22)?0:1)" && goto nodeok
:nodeinstall
echo Installing Node.js (needed for OmniRoute, the free AI router)...
winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
:nodeok
where npm >nul 2>&1 || goto omnidone
where omniroute >nul 2>&1 && goto omniinstalled
echo Installing OmniRoute (free AI router) - one time, about a minute...
call npm install -g omniroute
:omniinstalled
where omniroute >nul 2>&1 || goto omnidone
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 20128); $c.Close(); exit 0 } catch { exit 1 }"
if not errorlevel 1 goto omnidone
echo Starting OmniRoute in its own window (leave it open)...
start "OmniRoute - free AI router (leave open)" /min cmd /k omniroute
:omnidone

start "" cmd /c "timeout /t 3 >nul & start http://localhost:5003"
python clip_app.py
pause
