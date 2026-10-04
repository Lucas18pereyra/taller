"""Reinicio solicitado: archiva la base anterior y coloca una nueva, sin SQL DELETE.

No usar con la aplicacion abierta. Requiere --confirmar-base-vacia.
"""
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database


def sha(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def preparar():
    if sys.argv[1:] != ["--confirmar-base-vacia"]:
        raise SystemExit("Operacion no ejecutada. Requiere --confirmar-base-vacia y la app cerrada.")
    actual = ROOT / "estacionamiento.db"
    if Path(database.DB_PATH).resolve() != actual:
        raise SystemExit("No se admite un directorio de datos externo para este reinicio.")
    for sufijo in ("-wal", "-shm", "-journal"):
        if Path(str(actual) + sufijo).exists():
            raise SystemExit("Hay archivos de una transaccion SQLite. Cierra la app y revisa la base antes de continuar.")
    carpeta = ROOT / ".respaldo_visual" / f"base-anterior-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
    carpeta.mkdir(parents=True)
    evidencia = {"version_esquema": database.SCHEMA_VERSION, "base": str(actual), "archivo_anterior": None}
    hash_anterior = sha(actual) if actual.exists() else None
    copia = carpeta / "estacionamiento-antes-vaciar.db"
    if actual.exists():
        with closing(sqlite3.connect(actual.as_uri() + "?mode=ro", uri=True)) as origen:
            with closing(sqlite3.connect(copia)) as respaldo:
                origen.backup(respaldo)
                if respaldo.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Respaldo no valido. La base original no se modifico.")
    with TemporaryDirectory(prefix="nueva_base_", dir=carpeta) as temporal:
        nueva = Path(temporal) / actual.name
        database.init_db(db_path=nueva)
        with closing(sqlite3.connect(nueva)) as conn:
            tablas = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            conteos = {tabla: conn.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0] for tabla in tablas}
            if any(conteos.values()) or conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("La candidata no esta vacia o no es valida. No se cambio la base anterior.")
        if actual.exists() and sha(actual) != hash_anterior:
            raise RuntimeError("La base cambio durante la preparacion. No se reemplazo.")
        archivo_anterior = carpeta / "estacionamiento-original.db"
        if actual.exists():
            actual.replace(archivo_anterior)
            evidencia["archivo_anterior"] = str(archivo_anterior)
        try:
            nueva.replace(actual)
        except BaseException:
            if archivo_anterior.exists() and not actual.exists():
                archivo_anterior.replace(actual)
            raise
        evidencia.update(conteos=conteos, sha256_anterior=hash_anterior,
                         sha256_nueva=sha(actual), respaldo=str(copia) if copia.exists() else None)
    (carpeta / "REINICIO.json").write_text(json.dumps(evidencia, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidencia, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    preparar()
