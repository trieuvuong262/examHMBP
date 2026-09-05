@echo off
title JustPlay Cong cu IT
REM Khoi dong Cong cu IT - go chan Windows SmartScreen / Mark of the Web
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Mo-Ket-Noi-NAS.ps1"
if errorlevel 1 pause
