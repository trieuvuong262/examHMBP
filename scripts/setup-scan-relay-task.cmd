@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-scan-relay-task.ps1" -ProjectDir "%~1"
exit /b %ERRORLEVEL%
