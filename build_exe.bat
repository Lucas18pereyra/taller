@echo off
setlocal

powershell -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1" %*
if errorlevel 1 (
    echo Error al generar el .exe
    exit /b 1
)

echo Build finalizado.
exit /b 0
