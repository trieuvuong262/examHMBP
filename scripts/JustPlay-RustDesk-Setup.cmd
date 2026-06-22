@echo off
chcp 65001 >nul 2>&1
title JustPlay - Cai dat RustDesk
set "SRC_DIR=%~dp0"
set "WORK_DIR=%LOCALAPPDATA%\JustPlay\RustDesk-Setup"
set "PS1=%WORK_DIR%\JustPlay-RustDesk-Setup.ps1"
set "PS1_SRC=%SRC_DIR%JustPlay-RustDesk-Setup.ps1"

if not exist "%PS1_SRC%" (
  echo.
  echo  LOI: Khong tim thay JustPlay-RustDesk-Setup.ps1
  echo  Giai nen day du file .zip vao thu muc co dinh, roi chay lai .cmd
  echo.
  pause
  exit /b 1
)

if not exist "%WORK_DIR%" mkdir "%WORK_DIR%"
copy /Y "%PS1_SRC%" "%PS1%" >nul
if errorlevel 1 (
  echo LOI: Khong copy duoc script vao %WORK_DIR%
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
  echo.
  echo  LOI cai dat. Ma loi: %ERR%
  pause
)
exit /b %ERR%
