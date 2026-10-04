"""Respaldo previo a migraciones, sin modificar ni depurar la base original."""
from datetime import datetime
from pathlib import Path
import sqlite3
import uuid
from contextlib import closing

import database


def respaldar_antes_de_migrar():
    origen = Path(database.DB_PATH).resolve()
    if not origen.exists():
        return None
    conn = sqlite3.connect(origen.as_uri() + "?mode=ro", uri=True)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= database.SCHEMA_VERSION:
            return None
        carpeta = origen.parent / "backups"
        carpeta.mkdir(parents=True, exist_ok=True)
        nombre = f"{origen.stem}_antes_migracion_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.db"
        destino = carpeta / nombre
        try:
            with closing(sqlite3.connect(str(destino))) as backup:
                conn.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("El respaldo no supero la comprobacion de integridad.")
        except (sqlite3.Error, OSError):
            # Es una copia NUEVA fallida, no un respaldo del usuario. Conservarla
            # fuera del listado restaurable evita ofrecer un archivo corrupto.
            if destino.exists():
                try:
                    destino.replace(destino.with_suffix(".incompleto"))
                except OSError:
                    pass
            raise
        return destino
    finally:
        conn.close()
