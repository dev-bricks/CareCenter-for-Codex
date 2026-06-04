@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Python nicht gefunden!
    pause
    exit /b 1
)

set "PROJECT_ROOT=%CD%"
set "PYTHONPATH=%PROJECT_ROOT%\src"
set "PYGAME_HIDE_SUPPORT_PROMPT=1"
REM _tools liegt im .SOFTWARE-Root; CCC liegt 2 Ebenen darunter (CODING\DEV_...).
set "SCANNER=%PROJECT_ROOT%\..\..\_tools\build_exclude_scanner.py"
set "DIST_DIR=C:\_Local_DEV\codex-maintenance\bin"
set "WORK_DIR=C:\_Local_DEV\codex_build\codex-logwartung"
set "SPEC_DIR=C:\_Local_DEV\codex_build\codex-logwartung-spec"

python -m compileall -q src tests
if errorlevel 1 pause & exit /b 1

REM Keep the build isolated from unrelated projects that may be present in the parent shell.
set "PYTHONPATH=%PROJECT_ROOT%\src"

REM --- PFLICHT (.SOFTWARE\BUILD-VERFAHREN.md): Auto-Excludes gegen Schwergewichte ---
set "EXCLUDES="
for /f "delims=" %%E in ('python "%SCANNER%" --project "%PROJECT_ROOT%" --emit pyinstaller') do set "EXCLUDES=%%E"
echo [build] Auto-Excludes: !EXCLUDES!

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name CareCenterForCodex ^
  --icon "%PROJECT_ROOT%\CareCenterForCodex.ico" ^
  --add-data "%PROJECT_ROOT%\CareCenterForCodex.ico;." ^
  --paths "%PROJECT_ROOT%\src" ^
  %EXCLUDES% ^
  --distpath "%DIST_DIR%" ^
  --workpath "%WORK_DIR%" ^
  --specpath "%SPEC_DIR%" ^
  "%PROJECT_ROOT%\src\codex_logdatenbank_wartung\tray_app.py"

if errorlevel 1 pause & exit /b 1
echo EXE erstellt: %DIST_DIR%\CareCenterForCodex.exe
