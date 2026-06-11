@echo off
REM Stress test k6 - goi scripts/stress
REM   .\stress-test.cmd
REM   .\stress-test.cmd login
REM   .\stress-test.cmd reports
REM   .\stress-test.cmd requests
REM   .\stress-test.cmd kho-npl
REM   .\stress-test.cmd mixed
cd /d "%~dp0"
call "%~dp0scripts\stress\run.cmd" %*
exit /b %ERRORLEVEL%
