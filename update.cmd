@echo off
REM Push + deploy VPS (khong can doi Execution Policy)
REM chcp 65001: console UTF-8 — log deploy.sh (tiếng Việt) không bị lỗi font
cd /d "%~dp0"
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish.ps1" %*
exit /b %ERRORLEVEL%
