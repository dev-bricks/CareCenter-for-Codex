@echo off
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Python nicht gefunden!
    pause
    exit /b 1
)
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
python -m codex_logdatenbank_wartung.cli tray
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo CareCenter for Codex wurde mit Exit-Code %EXIT_CODE% beendet.
pause
exit /b %EXIT_CODE%
