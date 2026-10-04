"""Corre la suite local y deja evidencia reproducible sin tocar la base real."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main():
    real = ROOT / "estacionamiento.db"
    antes = hashlib.sha256(real.read_bytes()).hexdigest()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    log = io.StringIO()
    inicio = time.perf_counter()
    resultado = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    despues = hashlib.sha256(real.read_bytes()).hexdigest()
    evidencia = {
        "status": "passed" if resultado.wasSuccessful() and antes == despues else "failed",
        "tests": resultado.testsRun,
        "failures": len(resultado.failures), "errors": len(resultado.errors),
        "skipped": len(resultado.skipped),
        "duration_seconds": round(time.perf_counter() - inicio, 3),
        "real_db_unchanged": antes == despues, "real_db_sha256": despues,
        "source_sha256": {str(r.relative_to(ROOT)): hashlib.sha256(r.read_bytes()).hexdigest()
                          for r in (ROOT / "main.py", ROOT / "database.py", ROOT / "presentacion.py", ROOT / "presentacion_estilos.py", *sorted((ROOT / "servicios").glob("*.py")))},
    }
    carpeta = ROOT / "preview_visual" / "revision_profunda" / "regresiones"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "resultado.json").write_text(json.dumps(evidencia, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "pruebas.txt").write_text(log.getvalue(), encoding="utf-8")
    print(json.dumps({k: v for k, v in evidencia.items() if k != "source_sha256"}, indent=2))
    if not resultado.wasSuccessful():
        print(log.getvalue())
    return 0 if evidencia["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
