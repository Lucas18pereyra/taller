import sqlite3
import os
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from contextlib import closing

import database


def _ruta_db():
    return Path(database.DB_PATH)


def _carpeta_backups():
    carpeta = _ruta_db().resolve().parent / "backups"
    carpeta.mkdir(exist_ok=True)
    return carpeta


def crear_backup_db(max_backups=30):
    db_path = _ruta_db()
    if not db_path.exists():
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = _carpeta_backups() / f"{db_path.stem}_{ts}_{uuid4().hex[:8]}.db"

    src = None
    dst = None
    try:
        src = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
        dst = sqlite3.connect(str(destino))
        src.backup(dst)
    finally:
        if dst:
            dst.close()
        if src:
            src.close()

    _limpiar_backups_antiguos(db_path.stem, max_backups=max_backups)
    return destino


def listar_backups_db(limit=50):
    carpeta = _carpeta_backups()
    stem = _ruta_db().stem
    backups = sorted(
        carpeta.glob(f"{stem}_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if limit is None:
        return backups
    return backups[: max(0, int(limit))]


def eliminar_backup_db(path_backup):
    carpeta = _carpeta_backups().resolve()
    path = Path(path_backup).resolve()
    if path.parent != carpeta:
        return False
    if not path.exists() or not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def restaurar_backup_db(path_backup):
    carpeta = _carpeta_backups().resolve()
    backup_path = Path(path_backup).resolve()
    if backup_path.parent != carpeta:
        return False
    if not backup_path.exists() or not backup_path.is_file():
        return False

    db_path = _ruta_db().resolve()
    try:
        # Validar una COPIA antes de reemplazar los datos actuales. Una copia
        # corrupta o incompatible no debe dejar la aplicacion a medio restaurar.
        with TemporaryDirectory(prefix="restauracion_", dir=db_path.parent) as temporal:
            candidato = Path(temporal) / db_path.name
            with closing(sqlite3.connect(backup_path.as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(str(candidato))) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    return False
                tablas = {r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"clientes", "vehiculos", "espacios", "movimientos"}.issubset(tablas):
                    return False
            database.init_db(db_path=candidato)
            if db_path.exists():
                crear_backup_db(max_backups=None)
            os.replace(candidato, db_path)
        return True
    except (sqlite3.Error, OSError):
        return False


def _limpiar_backups_antiguos(stem, max_backups=30):
    if max_backups is None or int(max_backups) <= 0:
        return
    carpeta = _carpeta_backups()
    backups = sorted(
        carpeta.glob(f"{stem}_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in backups[int(max_backups):]:
        try:
            path.unlink()
        except OSError:
            pass
