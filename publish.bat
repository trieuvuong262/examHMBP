@echo off
REM Chay file .bat / .cmd nay — KHONG chay truc tiep publish.ps1 (bi chan Execution Policy)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
