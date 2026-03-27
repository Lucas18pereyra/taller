# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


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
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file.exists() else None,
    version=str(version_file) if version_file.exists() else None,
)
