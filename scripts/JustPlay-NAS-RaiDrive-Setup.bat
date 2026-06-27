@echo off
chcp 65001 >nul
setlocal
title JustPlay NAS - Ket noi WebDAV

:: Can quyen Admin de sua registry WebClient (BasicAuth / AuthForwardServerList)
net session >nul 2>&1
if not "%errorLevel%"=="0" (
    echo Yeu cau quyen Administrator de cau hinh WebClient...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0JustPlay-NAS-RaiDrive-Setup.ps1"
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
    echo.
    echo Loi ma %EC%. Lien he IT neu can ho tro.
    pause
)
endlocal
exit /b %EC%
