@echo off
chcp 65001 >nul
setlocal
title JustPlay NAS - Ket noi SMB

powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0JustPlay-NAS-RaiDrive-Setup.ps1"
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
    echo.
    echo Loi ma %EC%. Lien he IT neu can ho tro.
    pause
)
endlocal
exit /b %EC%
