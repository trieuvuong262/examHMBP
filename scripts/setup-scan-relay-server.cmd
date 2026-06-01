@echo off
REM Chay khong can doi Execution Policy he thong
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-scan-relay-server.ps1" -ProjectDir "%~1"
exit /b %ERRORLEVEL%
