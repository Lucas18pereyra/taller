# Release y Empaquetado

## 1) Generar EXE (PyInstaller)

Requisitos:
- Windows
- `.venv` creado en el proyecto
- `pyinstaller` instalado en la venv

Comando recomendado:

```powershell
.\build_exe.ps1 -Version 1.2.0 -CompanyName "Lucas" -ProductName "Estacionamiento App" -Clean
```

Salida esperada:
- `dist\EstacionamientoApp.exe`

## 2) Generar instalador (Inno Setup)

Requisitos:
- Inno Setup 6 (ISCC.exe)
- Haber generado antes el `dist\EstacionamientoApp.exe`

Comando:

```powershell
.\build_installer.ps1
```

Salida esperada:
- `dist_installer\Instalador_EstacionamientoApp_*.exe`

## 3) Archivos clave de release

- `EstacionamientoApp.spec`: define build de PyInstaller.
- `assets\app_icon.ico`: icono del ejecutable/instalador.
- `installer\version_info.txt`: metadatos de version para Windows.
- `installer\EstacionamientoApp.iss`: script del instalador.

## 4) Verificacion en maquina limpia (checklist)

1. Copiar solo el instalador a otra PC sin entorno de desarrollo.
2. Instalar y abrir la app desde acceso directo.
3. Confirmar que abre sin Python instalado.
4. Crear un cliente de prueba y cerrar/abrir la app.
5. Probar exportacion de reporte y ticket.
6. Desinstalar y validar que no quedan accesos directos rotos.
