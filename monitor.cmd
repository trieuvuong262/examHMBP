@echo off
REM Theo doi RAM / CPU / SSD tren VPS (mac dinh)
REM   .\monitor.cmd
REM   .\monitor.cmd watch
REM   .\monitor.cmd watch 10
REM   .\monitor.cmd local
REM   .\monitor.cmd all
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\monitor-system.ps1" %*
exit /b %ERRORLEVEL%
