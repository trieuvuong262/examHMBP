@echo off
chcp 65001 >nul
setlocal
title JustPlay NAS - local dev (tu repo)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Prepare-JustPlay-WebClient.ps1"
if not "%ERRORLEVEL%"=="0" (
    echo Khong cau hinh duoc WebClient.
    pause
    exit /b %ERRORLEVEL%
)

set "MODE=-Gui"
if not "%~1"=="" set "MODE=%*"

powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-NAS-Local-Connect.ps1" %MODE%
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
    echo.
    echo Loi ma %EC%.
    pause
)
endlocal
exit /b %EC%
