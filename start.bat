@echo off
cd /d "%~dp0"
title Wayne Factory
where python >nul 2>&1 || (echo Python is not installed - get it from python.org and tick "Add python.exe to PATH". & pause & exit /b)
if not exist ".installed-wf2" (
  echo Installing what Wayne Factory needs, this takes a minute...
  python -m pip install -r requirements.txt || (echo Install failed - check your internet and run start.bat again. & pause & exit /b)
  echo ok> .installed-wf2
)
rem Ollama: the free AI on this PC - installed once, started if it isn't running, and a small fast model fetched once.
rem To never use it, create an empty file called no-ollama.txt in this folder.
if exist "no-ollama.txt" goto ollamadone
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
where ollama >nul 2>&1 && goto ollamahave
echo Installing Ollama - the free AI that runs on this PC. One time, a few minutes...
winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
where ollama >nul 2>&1 || goto ollamadone
:ollamahave
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 11434); $c.Close(); exit 0 } catch { exit 1 }"
if not errorlevel 1 goto ollamaup
echo Starting Ollama...
start "Ollama - the AI on this PC - leave open" /min ollama serve
timeout /t 5 >nul
:ollamaup
ollama list 2>nul | findstr /r /c:"^[a-z]" | findstr /v /c:"NAME" >nul && goto ollamadone
echo Getting a small fast AI model for this PC - about 2 GB, one time...
ollama pull llama3.2
:ollamadone

start "" cmd /c "timeout /t 4 >nul & start http://localhost:5001/produce.html"
python web_server.py
pause
