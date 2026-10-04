# Release y Empaquetado

## 1) Ejecutar la versión normal

Abrí `EstacionamientoApp.exe` en la raíz del proyecto o `Abrir_estacionamiento.bat`.
No usa `--demo` y conserva los cambios de `estacionamiento.db`. Esta entrega,
por pedido del usuario, inicia con base vacía y creación del primer administrador.
La versión normal abre en Claro si no existe otra preferencia guardada.
La demo permanece separada en `Mostrar_demo.bat`.

## 2) Generar EXE (PyInstaller)

Requisitos:
- Windows
- `.venv` creado en el proyecto, con `requirements-build.txt` instalado

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

Comando recomendado:

```powershell
.\build_exe.ps1 -Version 1.4.0 -CompanyName "Lucas" -ProductName "Estacionamiento App" -Clean
```

Salida esperada:
- `dist\EstacionamientoApp.exe`
- `EstacionamientoApp.exe`, junto a la base existente para usarla en esta PC.

No se empaqueta ninguna base de datos ni credencial. Un EXE copiado a una carpeta
nueva crea su propia base y solicita crear un administrador. Las exportaciones
se guardan junto a la base, fuera de la carpeta temporal del bundle. Ver
[información de rutas de PyInstaller](https://pyinstaller.org/en/stable/runtime-information.html).

Si existe un EXE anterior en la raíz, el build lo respalda antes de reemplazarlo.

## 3) Generar instalador opcional (Inno Setup)

Requisitos:
- Inno Setup 6 (ISCC.exe)
- Haber generado antes el `dist\EstacionamientoApp.exe`

Comando:

```powershell
.\build_installer.ps1
```

Salida esperada:
- `dist_installer\Instalador_EstacionamientoApp_*.exe`

El destino predeterminado es una carpeta de programas del usuario, con permiso
de escritura. No se necesita el instalador para abrir el EXE portable.

## 4) Archivos clave de release

- `EstacionamientoApp.spec`: define build de PyInstaller.
- `assets\app_icon.ico`: icono del ejecutable/instalador.
- `installer\version_info.txt`: metadatos de version para Windows.
- `installer\EstacionamientoApp.iss`: script del instalador.

## 5) Verificación

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\verificar_regresiones.py
.\.venv\Scripts\python.exe tools\verificar_visual.py
.\.venv\Scripts\python.exe tools\verificar_visual.py --deep --output preview_visual\revision_profunda\visual
.\.venv\Scripts\python.exe tools\verificar_normal.py
.\.venv\Scripts\python.exe tools\verificar_arranque.py
.\.venv\Scripts\python.exe tools\verificar_exe.py
```

Las pruebas crean bases temporales y verifican que la original no cambia.
`verificar_exe.py` ejecuta el EXE real con `--verificar-inicio`: este diagnóstico
requiere `ESTACIONAMIENTO_DATA_DIR`, sólo inspecciona y cierra el login o alta
inicial y no permite saltar la autenticación. La evidencia queda en
`preview_visual\normal` y `preview_visual\revision_profunda`.

Pendiente de comprobar en otra computadora limpia:

1. Copiar solo el instalador a otra PC sin entorno de desarrollo.
2. Instalar y abrir la app desde acceso directo.
3. Confirmar que abre sin Python instalado.
4. Crear un cliente de prueba y cerrar/abrir la app.
5. Probar exportacion de reporte y ticket.
6. Desinstalar y validar que no quedan accesos directos rotos.
