@echo off
title Update Clip Factory
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm ('https://raw.githubusercontent.com/Rigers6969/rigers/claude/sweet-dijkstra-lyzrb5/update.ps1?v=' + [DateTime]::Now.Ticks) | iex"
pause
