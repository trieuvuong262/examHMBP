@echo off
REM SSH tunnel local:5433 -> VPS PostgreSQL (127.0.0.1:5432)
REM Giu cua so nay mo khi dung pgAdmin.
REM pgAdmin: Host=localhost Port=5433 Database=portaljustplay_db User=postgres

set "VPS_HOST=103.90.224.203"
set "VPS_USER=root"
set "VPS_PORT=22"
set "LOCAL_PORT=5433"

set "CFG=%~dp0..\deploy.local.env"
if exist "%CFG%" (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /r "^VPS_HOST= ^VPS_USER= ^VPS_PORT=" "%CFG%"`) do (
    if /i "%%A"=="VPS_HOST" set "VPS_HOST=%%B"
    if /i "%%A"=="VPS_USER" set "VPS_USER=%%B"
    if /i "%%A"=="VPS_PORT" set "VPS_PORT=%%B"
  )
)

echo SSH tunnel: localhost:%LOCAL_PORT% -^> %VPS_USER%@%VPS_HOST%:127.0.0.1:5432
echo pgAdmin: Host=localhost Port=%LOCAL_PORT% Database=portaljustplay_db User=postgres
echo Nhan Ctrl+C de dong tunnel.
echo.

ssh -p %VPS_PORT% -N -L %LOCAL_PORT%:127.0.0.1:5432 %VPS_USER%@%VPS_HOST%
