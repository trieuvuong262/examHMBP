@echo off
cd /d "%~dp0.."
pip install pyinstaller -q
pyinstaller --onefile --clean --name JustPlayAgent --paths . justplay_agent.py
if exist dist\JustPlayAgent.exe (
    echo.
    echo OK: dist\JustPlayAgent.exe
    echo Copy cung justplay_agent.ini len tung PC
) else (
    echo Build failed
    exit /b 1
)
