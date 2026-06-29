@echo off
REM Gỡ chặn Windows và mở EXE kết nối NAS (nếu Ket-Noi-NAS-JustPlay.exe bị "unsafe")
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Mo-Ket-Noi-NAS.ps1"
if errorlevel 1 pause
