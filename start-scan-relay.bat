@echo off
cd /d "%~dp0"
if not exist scan_relay.env (
    echo Chua co scan_relay.env - copy tu scan_relay.env.example
    pause
    exit /b 1
)
echo JustPlay Scan Relay - http://127.0.0.1:8765/health
python scan_relay_server.py
pause
