@echo off
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Python nicht gefunden!
    pause
    exit /b 1
)
where pythonw >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] pythonw.exe nicht gefunden!
    pause
    exit /b 1
)
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
start "" pythonw -m codex_logdatenbank_wartung.cli tray
exit /b 0
