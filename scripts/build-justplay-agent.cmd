@echo off
cd /d "%~dp0.."
pip install pyinstaller -q
python -m PyInstaller --onefile --clean --noconsole --name JustPlayAgent --paths . justplay_agent.py
if exist dist\JustPlayAgent.exe (
    if not exist static\equipment mkdir static\equipment
    copy /Y dist\JustPlayAgent.exe static\equipment\JustPlayAgent.exe
    echo.
    echo OK: static\equipment\JustPlayAgent.exe
    echo Deploy len VPS: git push hoac scp file len server
) else (
    echo Build failed
    exit /b 1
)
