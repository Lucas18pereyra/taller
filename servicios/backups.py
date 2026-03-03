import sqlite3
from datetime import datetime
from pathlib import Path

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
    destino = _carpeta_backups() / f"{db_path.stem}_{ts}.db"

    src = None
    dst = None
    try:
        src = sqlite3.connect(str(db_path))
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


def _reconciliar_espacios_contratos(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='espacios'"
    )
    if not cur.fetchone():
        return
    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='cochera_contratos'"
    )
    if not cur.fetchone():
        return
    cur.execute(
        "UPDATE espacios "
        "SET id_cliente = ("
        "SELECT cc.id_cliente "
        "FROM cochera_contratos cc "
        "WHERE cc.id_espacio = espacios.id_espacio "
        "AND cc.activo = 1 "
        "ORDER BY cc.id_contrato DESC "
        "LIMIT 1"
        ")"
    )


def restaurar_backup_db(path_backup):
    carpeta = _carpeta_backups().resolve()
    backup_path = Path(path_backup).resolve()
    if backup_path.parent != carpeta:
        return False
    if not backup_path.exists() or not backup_path.is_file():
        return False

    db_path = _ruta_db().resolve()
    src = None
    dst = None
    try:
        src = sqlite3.connect(str(backup_path))
        dst = sqlite3.connect(str(db_path))
        src.backup(dst)
        try:
            _reconciliar_espacios_contratos(dst)
            dst.commit()
        except sqlite3.Error:
            pass
        return True
    except sqlite3.Error:
        return False
    finally:
        if dst:
            dst.close()
        if src:
            src.close()


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
