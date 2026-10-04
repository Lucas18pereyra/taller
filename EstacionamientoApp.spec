# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import PySide6
import os


try:
    project_dir = Path(SPEC).resolve().parent
except Exception:
    project_dir = Path.cwd()
main_script = project_dir / "main.py"
icon_file = project_dir / "assets" / "app_icon.ico"
version_file = project_dir / "installer" / "version_info.txt"

a = Analysis(
    [str(main_script)],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[(str(icon_file), "assets"), (str(project_dir / "assets" / "checkbox-check.svg"), "assets")],
    hiddenimports=["xlsxwriter"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Python y Qt pueden aportar distintas versiones del runtime de Visual C++.
# El bootloader carga las DLL de la raiz antes que Qt: usar el mismo runtime
# distribuido por Qt tambien en la raiz evita resolver exports en una DLL vieja.
qt_dir = Path(PySide6.__file__).resolve().parent
# Qt usa ICU de Windows. No empaquetar la ICU de Poppler encontrada en PATH:
# sus simbolos versionados son incompatibles con Qt y bloquean QtCore.
a.binaries = [(dest, src, kind) for dest, src, kind in a.binaries
              if Path(dest).name.lower() not in ("icuuc.dll", "icudt78.dll")]
runtime_names = ("VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll",
                 "MSVCP140_1.dll", "MSVCP140_2.dll")
runtime_sources = {name: qt_dir / name for name in runtime_names}
for name, source in runtime_sources.items():
    if not source.is_file():
        raise RuntimeError(f"Falta el runtime de Qt: {source}")
a.binaries = [(dest, str(runtime_sources[Path(dest).name]), kind)
              if Path(dest).name in runtime_sources else (dest, src, kind)
              for dest, src, kind in a.binaries]
for name, source in runtime_sources.items():
    if not any(dest == name for dest, _, _ in a.binaries):
        a.binaries.append((name, str(source), "BINARY"))
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EstacionamientoApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=os.environ.get("ESTACIONAMIENTO_BUILD_CONSOLE") == "1",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file.exists() else None,
    version=str(version_file) if version_file.exists() else None,
)
