@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py" --demo
    exit /b
)

where pyw >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import PySide6" >nul 2>&1
    if not errorlevel 1 (
        start "" pyw -3 "%~dp0main.py" --demo
        exit /b
    )
)

where pythonw >nul 2>&1
if not errorlevel 1 (
    python -c "import PySide6" >nul 2>&1
    if not errorlevel 1 (
        start "" pythonw "%~dp0main.py" --demo
        exit /b
    )
)

echo No se encontro un Python con PySide6 para abrir la demostracion.
echo Si aparece un error debajo, conserva este texto para revisarlo.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0main.py" --demo
) else (
    python "%~dp0main.py" --demo
)
pause
