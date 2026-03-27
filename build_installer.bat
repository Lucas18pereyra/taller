@echo off
setlocal

powershell -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1" %*
if errorlevel 1 (
    echo Error al generar el instalador.
    exit /b 1
)

echo Instalador generado.
exit /b 0
