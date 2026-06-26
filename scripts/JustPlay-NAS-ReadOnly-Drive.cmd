@echo off
setlocal
REM Map NAS share read-only — File Explorer bao loi ngay khi tao thu muc (khong treo).
REM Sua DRIVE va UNC ben duoi roi double-click (hoac Run as user thuong).
set DRIVE=Z
set UNC=\\100.93.5.42\04_KINH_DOANH_CSKH

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0JustPlay-NAS-ReadOnly-Drive.ps1" -DriveLetter %DRIVE% -UncPath "%UNC%" -Persist
pause
