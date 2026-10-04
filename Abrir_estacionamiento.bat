@echo off
setlocal
cd /d "%~dp0"
rem Use this folder's existing database, never the disposable demo database.
set "ESTACIONAMIENTO_DATA_DIR=%~dp0"

if exist "%~dp0EstacionamientoApp.exe" (
    start "" "%~dp0EstacionamientoApp.exe"
    exit /b
)

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
    exit /b
)

where pyw >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import PySide6, xlsxwriter" >nul 2>&1
    if not errorlevel 1 (
        start "" pyw -3 "%~dp0main.py"
        exit /b
    )
)

echo No se encontro el ejecutable completo ni un Python con las dependencias.
echo Genera EstacionamientoApp.exe con build_exe.bat, o instala requirements.txt.
pause
