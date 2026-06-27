@echo off
chcp 65001 >nul
setlocal
title JustPlay NAS - Ket noi WebDAV

:: Prepare tu nang cap UAC khi can; map o phai chay session user (Explorer thay duoc Z:)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Prepare-JustPlay-WebClient.ps1"
if not "%ERRORLEVEL%"=="0" (
    echo.
    echo Khong cau hinh duoc WebClient. Thu chay lai va chap nhan UAC khi duoc hoi.
    pause
    exit /b %ERRORLEVEL%
)

:: Luon mo GUI o session user — KHONG chay map trong cua so Admin
explorer.exe powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0JustPlay-NAS-RaiDrive-Setup.ps1"
endlocal
exit /b 0
