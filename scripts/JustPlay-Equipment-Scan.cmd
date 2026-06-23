@echo off
chcp 65001 >nul 2>&1
title JustPlay - Quet cau hinh may
set "SRC_DIR=%~dp0"
set "WORK_DIR=%LOCALAPPDATA%\JustPlay\Equipment-Scan"
set "PS1=%WORK_DIR%\JustPlay-Equipment-Scan.ps1"
set "PS1_SRC=%SRC_DIR%JustPlay-Equipment-Scan.ps1"

if not exist "%PS1_SRC%" (
  echo.
  echo  LOI: Khong tim thay JustPlay-Equipment-Scan.ps1
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
echo.
if "%ERR%"=="0" (
  echo  Hoan tat. Kiem tra thiet bi trong Quan ly thiet bi IT tren Portal.
) else (
  echo  LOI quet cau hinh. Ma loi: %ERR%
)
pause
exit /b %ERR%
