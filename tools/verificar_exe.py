"""Run the actual packaged executable against isolated, persistent test data."""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def run():
    original = ROOT / "estacionamiento.db"
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    with closing(sqlite3.connect(original.as_uri() + "?mode=ro", uri=True)) as source:
        original_clients = source.execute("SELECT count(*) FROM clientes").fetchone()[0]
    executable = ROOT / "EstacionamientoApp.exe"
    assert executable.is_file(), "Build the executable first"
    output = ROOT / "preview_visual" / "revision_profunda" / "exe"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with TemporaryDirectory(prefix="estacionamiento_exe_qa_") as temp:
        folder = Path(temp)
        # The test machine needs only the EXE; no Python packages or source files.
        copy_exe = folder / executable.name
        shutil.copy2(executable, copy_exe)
        for scenario in ("nueva", "existente", "reapertura"):
            data = folder / ("nueva" if scenario == "nueva" else "existente")
            data.mkdir(exist_ok=True)
            target_db = data / "estacionamiento.db"
            if scenario == "existente":
                with closing(sqlite3.connect(original.as_uri() + "?mode=ro", uri=True)) as source:
                    with closing(sqlite3.connect(target_db)) as target:
                        source.backup(target)
                # A partir de la entrega vacia no hay usuario real. La prueba de
                # login utiliza una cuenta ficticia SOLO dentro de la copia QA.
                with closing(sqlite3.connect(target_db)) as target:
                    # Las carpetas del usuario tambien se aislan en la copia QA.
                    for key, subfolder in (("dir_reportes", "reportes"),
                                           ("dir_comprobantes", "comprobantes"),
                                           ("dir_tickets_salida", "tickets")):
                        target.execute("INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
                                       "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                                       (key, str(data / subfolder)))
                    if target.execute("SELECT count(*) FROM usuarios WHERE activo=1").fetchone()[0] == 0:
                        target.execute("INSERT INTO usuarios (usuario,password,rol,activo) VALUES ('qa_exe','SoloPrueba123','DUENO',1)")
                    target.commit()
            env = dict(os.environ)
            env["ESTACIONAMIENTO_DATA_DIR"] = str(data)
            env["QT_QPA_PLATFORM"] = "offscreen"
            process = subprocess.Popen([str(copy_exe), "--verificar-inicio"],
                                       cwd=folder, env=env,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                code = process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                # Only the process tree started by this test is stopped.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               check=False, capture_output=True)
                raise AssertionError("The packaged startup did not close normally")
            assert code == 0, (scenario, code)
            result = json.loads((data / "verificacion_inicio.json").read_text(encoding="utf-8"))
            assert result["ok"] and not result["demo"], result
            assert result["tema"] == "claro", result
            assert result["integridad"] == "ok" and result["excel"], result
            expected_clients = 0 if scenario == "nueva" else original_clients
            assert result["clientes"] == expected_clients, "Startup must preserve client counts"
            assert result["pantalla"] == ("FirstUserDialog" if scenario == "nueva" else "LoginDialog"), result
            assert Path(result["db_path"]) == target_db
            for key in ("reportes_dir", "comprobantes_dir", "tickets_dir"):
                assert Path(result[key]).is_relative_to(data), result
                assert Path(result[key]).is_dir()
            shutil.copy2(data / "verificacion_inicio.png", output / ("exe_" + scenario + ".png"))
            result["escenario"] = scenario
            results.append(result)
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    (output / "verificacion_exe.json").write_text(
        json.dumps({"resultados": results, "original_sha256": before,
                    "exe_sha256": hashlib.sha256(executable.read_bytes()).hexdigest()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS: actual EXE, normal clear startup, first user/login, Excel bundled,")
    print("      persistent output paths, reopen, clean exit and original DB unchanged.")
    print("Evidence:", output)


if __name__ == "__main__":
    run()
