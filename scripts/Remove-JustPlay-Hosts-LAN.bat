@echo off
:: Xoa hosts JustPlay LAN — can UAC Administrator
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Remove-JustPlay-Hosts-LAN.ps1"
pause
