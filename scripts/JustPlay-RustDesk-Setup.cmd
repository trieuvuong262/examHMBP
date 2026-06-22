@echo off
chcp 65001 >nul 2>&1
title JustPlay - Cai dat RustDesk
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0JustPlay-RustDesk-Setup.ps1" %*
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
  echo.
  echo  LOI cai dat. Ma loi: %ERR%
  pause
)
exit /b %ERR%
