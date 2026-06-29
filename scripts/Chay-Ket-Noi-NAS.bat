@echo off
title JustPlay NAS
REM Khoi dong NAS - gỡ chặn Windows SmartScreen / Mark of the Web
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Mo-Ket-Noi-NAS.ps1"
if errorlevel 1 pause
