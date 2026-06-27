@echo off
chcp 65001 >nul
setlocal
title JustPlay NAS - Ket noi WebDAV

:: Admin CHI de sua registry WebClient; map o dia chay session user (Explorer thay duoc Z:)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Prepare-JustPlay-WebClient.ps1"
if not "%ERRORLEVEL%"=="0" (
    echo.
    echo Khong cau hinh duoc WebClient. Thu chay lai va chap nhan UAC.
    pause
    exit /b %ERRORLEVEL%
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
