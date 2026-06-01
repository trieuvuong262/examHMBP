@echo off
if "%~1"=="" (
    echo Usage: install-justplay-agent.cmd C:\JustPlayAgent
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-justplay-agent.ps1" -AgentDir "%~1"
