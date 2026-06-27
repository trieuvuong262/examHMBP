@echo off
chcp 65001 >nul
setlocal
title JustPlay NAS - Ket noi WebDAV

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Chay-Ket-Noi-NAS.ps1"
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" pause
endlocal
exit /b %EC%
