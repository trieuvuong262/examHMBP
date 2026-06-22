@echo off
chcp 65001 >nul 2>&1
title JustPlay - Cau hinh RustDesk (IT)
set "WORK_DIR=%LOCALAPPDATA%\JustPlay\RustDesk-Setup"
set "PS1=%WORK_DIR%\JustPlay-RustDesk-IT-Setup.ps1"
if not exist "%~dp0JustPlay-RustDesk-IT-Setup.ps1" (
  echo LOI: Thieu JustPlay-RustDesk-IT-Setup.ps1
  pause
  exit /b 1
)
if not exist "%WORK_DIR%" mkdir "%WORK_DIR%"
copy /Y "%~dp0JustPlay-RustDesk-IT-Setup.ps1" "%PS1%" >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
echo.
pause
exit /b %ERRORLEVEL%
