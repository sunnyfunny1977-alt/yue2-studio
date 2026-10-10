@echo off
cd /d "%~dp0"
if not exist ".venv-yue2\Scripts\python.exe" (
    echo Bitte zuerst install.ps1 ausfuehren:
    echo   powershell -ExecutionPolicy Bypass -File install.ps1
    pause
    exit /b 1
)
set PYTHONUTF8=1
".venv-yue2\Scripts\python.exe" app.py
pause
