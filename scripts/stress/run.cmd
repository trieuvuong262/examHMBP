@echo off
REM Stress test Portal JustPlay (k6)
REM   cd scripts\stress
REM   .\run.cmd
REM   .\run.cmd login
REM   .\run.cmd reports
REM   .\run.cmd requests
REM   .\run.cmd kho-npl
REM   .\run.cmd mixed
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
exit /b %ERRORLEVEL%
