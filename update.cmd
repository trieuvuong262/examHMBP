@echo off
REM Push + deploy VPS qua SSH public, khong qua Tailscale.
REM ssh -i %USERPROFILE%\.ssh\vps_portal -p 22 root@103.90.224.203
REM chcp 65001: console UTF-8 — log deploy.sh (tiếng Việt) không bị lỗi font
cd /d "%~dp0"
chcp 65001 >nul
set "VPS_HOST=103.90.224.203"
set "VPS_USER=root"
set "VPS_PORT=22"
set "VPS_SSH_KEY=%USERPROFILE%\.ssh\vps_portal"
set "VPS_TAILSCALE_HOST="
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish.ps1" %*
exit /b %ERRORLEVEL%
