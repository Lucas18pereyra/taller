r"""Prueba errores del arranque REAL, sin --demo ni omitir autenticacion.

Ejecutar: .venv\Scripts\python.exe tools\verificar_arranque.py
Los escenarios y respaldos se crean en TemporaryDirectory. Ninguna conexion
SQLite puede salir de esa carpeta. Evidencias: preview_visual/revision_profunda/arranque.
"""

import argparse
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import traceback
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "estacionamiento_arranque_test_"
SCENARIOS = ("duplicados_heredados", "sqlite_ajeno", "esquema_futuro", "sqlite_corrupto")


def hash_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def sqlite_path(value):
    raw = str(value)
    if raw.startswith("file:"):
        raw = unquote(urlsplit(raw).path)
        if os.name == "nt":
            raw = raw.lstrip("/")
    if raw in (":memory:", ""):
        raise AssertionError("El verificador exige SQLite con ruta temporal explicita")
    return Path(raw).resolve()


def install_audit(allowed_dir, paths, block_external=False):
    allowed_dir = Path(allowed_dir).resolve()
    assert allowed_dir.name.startswith(PREFIX), "La carpeta no es temporal del verificador"

    def audit(event, values):
        if event == "sqlite3.connect":
            path = sqlite_path(values[0])
            if not path.is_relative_to(allowed_dir):
                raise AssertionError(f"SQLite fuera del aislamiento: {path}")
            paths.add(str(path))
        if block_external and event in ("os.startfile", "subprocess.Popen"):
            raise AssertionError("El proceso de prueba no puede abrir aplicaciones externas")

    sys.addaudithook(audit)


def db_snapshot(path):
    """Huella logica de las bases SINTETICAS, sin guardar valores de usuarios."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = sorted(row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        counts = {table: conn.execute('SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0]
                  for table in tables}
        logical = hashlib.sha256("\n".join(conn.iterdump()).encode("utf-8")).hexdigest().upper()
        return dict(integridad=integrity, version=version, conteos=counts, huella_logica=logical)


def create_fixture(scenario, path):
    sys.path.insert(0, str(ROOT))
    import database

    if scenario == "sqlite_ajeno":
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE otra_aplicacion (id INTEGER PRIMARY KEY, dato TEXT)")
            conn.execute("INSERT INTO otra_aplicacion VALUES (1,'Registro ficticio que debe conservarse')")
            conn.commit()
        return 0

    database.init_db(db_path=path)
    with closing(sqlite3.connect(path)) as conn:
        if scenario == "duplicados_heredados":
            # Quitar garantias UNICAMENTE de la fixture para simular una DB vieja.
            for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
                conn.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
            for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql LIKE '%UNIQUE%' AND tbl_name='movimientos'").fetchall():
                conn.execute('DROP INDEX "' + name.replace('"', '""') + '"')
            conn.execute("INSERT INTO vehiculos (patente) VALUES ('QA001AA')")
            conn.execute("INSERT INTO vehiculos (patente) VALUES ('QA002AA')")
            conn.execute("INSERT INTO espacios (codigo) VALUES ('QA-E01')")
            conn.execute("INSERT INTO movimientos (id_vehiculo,id_espacio,fecha_ingreso) VALUES (1,1,'2024-05-01 12:30:00')")
            conn.execute("INSERT INTO movimientos (id_vehiculo,id_espacio,fecha_ingreso) VALUES (2,1,'2024-05-01 12:31:00')")
            conn.execute("PRAGMA user_version=0")
            version = 0
        elif scenario == "esquema_futuro":
            version = database.SCHEMA_VERSION + 1
            conn.execute(f"PRAGMA user_version={version}")
        elif scenario == "sqlite_corrupto":
            # Corrupcion de esquema por API SQLite, nunca archivos ajenos.
            conn.execute("PRAGMA user_version=0")
            conn.execute("PRAGMA writable_schema=ON")
            conn.execute("UPDATE sqlite_master SET sql='not a create statement' WHERE name='clientes'")
            version = 0
        else:
            raise ValueError(scenario)
        conn.commit()
    return version


def child_run(args):
    data_dir, evidence = args.data_dir.resolve(), args.output.resolve()
    allowed_dir = data_dir.parent
    assert allowed_dir.name.startswith(PREFIX) and data_dir.name == args.scenario
    assert args.scenario in SCENARIOS
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["ESTACIONAMIENTO_DATA_DIR"] = str(data_dir)
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    paths = set()
    install_audit(allowed_dir, paths, block_external=True)
    report = dict(escenario=args.scenario, modo="main.__main__ normal sin --demo",
                  mensajes_criticos=[], dialogos_autenticacion=[], bucles_principales=0,
                  capturas=[], codigo_salida=None, errores=[])
    evidence.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QDesktopServices, QFontDatabase, QPalette
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton, QTextEdit

    original_init = QApplication.__init__
    original_exec = QApplication.exec
    apps = []

    def app_init(app, *values, **kwargs):
        original_init(app, *values, **kwargs)
        apps.append(app)
        for name in ("segoeui.ttf", "segoeuib.ttf", "arial.ttf", "arialbd.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))

    def capture_message(box):
        content = "\n".join(part for part in (box.text(), box.informativeText(), box.detailedText()) if part)
        report["mensajes_criticos"].append(dict(titulo=box.windowTitle(), texto=content,
                                               principal=box.text(), detalles=box.detailedText(),
                                               icono_critico=box.icon() == QMessageBox.Critical))
        box.show()
        QApplication.instance().processEvents()
        capture = evidence / "error_arranque.png"
        if box.grab().save(str(capture)):
            report["capturas"].append(capture.name)
        if box.detailedText():
            buttons = [button for button in box.findChildren(QPushButton)
                       if box.buttonRole(button) == QMessageBox.ActionRole]
            if buttons:
                report["boton_detalles"] = buttons[0].text()
                buttons[0].click()
                QApplication.instance().processEvents()
                report["detalles_accesibles"] = any(editor.isVisible() for editor in box.findChildren(QTextEdit))
                capture = evidence / "detalles_arranque.png"
                if box.grab().save(str(capture)):
                    report["capturas"].append(capture.name)
                for editor in box.findChildren(QTextEdit):
                    if editor.isVisible():
                        report["detalle_completo_disponible"] = editor.toPlainText() == box.detailedText()
                        editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum())
                QApplication.instance().processEvents()
                capture = evidence / "rutas_arranque.png"
                if box.grab().save(str(capture)):
                    report["capturas"].append(capture.name)
        report["fondo_error"] = QApplication.instance().palette().color(QPalette.Window).name()
        report["tema_claro_error"] = report["fondo_error"] == "#f2f5f8"
        box.close()
        box.deleteLater()
        return QMessageBox.Ok

    def critical(parent, title, message, *values, **kwargs):
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle(str(title))
        box.setText(str(message))
        box.setStandardButtons(QMessageBox.Ok)
        return capture_message(box)

    def reject_auth(dialog):
        # Si el rechazo falla, capturar y CANCELAR: nunca aceptar un login.
        report["dialogos_autenticacion"].append(type(dialog).__name__)
        dialog.show()
        QApplication.instance().processEvents()
        capture = evidence / "acceso_no_esperado.png"
        if dialog.grab().save(str(capture)):
            report["capturas"].append(capture.name)
        dialog.reject()
        return QDialog.Rejected

    def guarded_exec(app):
        report["bucles_principales"] += 1
        QTimer.singleShot(100, app.quit)
        return original_exec()

    def forbid_external(*values, **kwargs):
        raise AssertionError("No se permite abrir enlaces externos durante la prueba")

    QApplication.__init__ = app_init
    QApplication.exec = guarded_exec
    QDialog.exec = reject_auth
    QMessageBox.critical = critical
    QMessageBox.exec = capture_message
    QDesktopServices.openUrl = forbid_external
    try:
        sys.argv = [str(ROOT / "main.py")]
        runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
        report["codigo_salida"] = 0
    except SystemExit as exc:
        report["codigo_salida"] = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException:
        report["codigo_salida"] = 3
        report["errores"].append(traceback.format_exc())
    finally:
        for app in apps:
            for widget in app.topLevelWidgets():
                widget.close()
            app.processEvents()
            app.quit()
        report["rutas_sqlite"] = sorted(paths)
        (evidence / "proceso.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report["codigo_salida"]


def controller(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = dict(fecha=datetime.now().astimezone().isoformat(), escenarios=[],
                  aislamiento="Todos los accesos SQLite limitados a TemporaryDirectory; base real nunca abierta.")
    audit_paths = set()
    with TemporaryDirectory(prefix=PREFIX) as temporal:
        temporary_root = Path(temporal).resolve()
        install_audit(temporary_root, audit_paths)
        for scenario in SCENARIOS:
            data_dir, evidence = temporary_root / scenario, output / scenario
            data_dir.mkdir()
            evidence.mkdir(parents=True, exist_ok=True)
            candidate = data_dir / "estacionamiento.db"
            version = create_fixture(scenario, candidate)
            before = hash_file(candidate)
            try:
                snapshot = db_snapshot(candidate)
            except sqlite3.Error:
                snapshot = None
            env = os.environ.copy()
            env.update(QT_QPA_PLATFORM="offscreen", ESTACIONAMIENTO_DATA_DIR=str(data_dir), PYTHONDONTWRITEBYTECODE="1")
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child",
                       "--scenario", scenario, "--data-dir", str(data_dir), "--output", str(evidence)]
            try:
                process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                                         encoding="utf-8", errors="replace", timeout=50)
                process_info = dict(codigo=process.returncode, stdout=process.stdout, stderr=process.stderr)
            except subprocess.TimeoutExpired as exc:
                # subprocess.run mata y espera al hijo si vence el timeout.
                process_info = dict(codigo=None, error="Timeout: proceso hijo terminado", stderr=str(exc))
            (evidence / "subprocess.json").write_text(json.dumps(process_info, ensure_ascii=False, indent=2), encoding="utf-8")
            child_path = evidence / "proceso.json"
            child = json.loads(child_path.read_text(encoding="utf-8")) if child_path.exists() else {}
            backups = sorted((data_dir / "backups").glob("*.db"))
            backup_reports = []
            for path in backups:
                try:
                    backup_snapshot = db_snapshot(path)
                    backup_reports.append(dict(nombre=path.name, sha256=hash_file(path),
                                               integridad_ok=backup_snapshot["integridad"] == ["ok"],
                                               mismo_contenido=backup_snapshot == snapshot))
                except sqlite3.Error as exc:
                    backup_reports.append(dict(nombre=path.name, error=str(exc)))
            checks = {
                "exit_1": process_info["codigo"] == 1 and child.get("codigo_salida") == 1,
                "mensaje_critico_claro": len(child.get("mensajes_criticos", [])) == 1 and child.get("tema_claro_error") is True,
                "captura_guardada": bool(child.get("capturas")),
                "detalles_accesibles": child.get("detalles_accesibles") is True and child.get("boton_detalles") == "Ver detalles",
                "rutas_completas_disponibles": child.get("detalle_completo_disponible") is True,
                "sin_acceso_ni_autenticacion": not child.get("dialogos_autenticacion") and child.get("bucles_principales") == 0,
                "candidato_sin_cambios": hash_file(candidate) == before,
                "sqlite_solo_temporal": bool(child.get("rutas_sqlite")) and all(Path(path).is_relative_to(temporary_root) for path in child.get("rutas_sqlite", [])),
                "sin_excepcion_no_controlada": not child.get("errores"),
            }
            if snapshot is not None and version < 2:
                checks["respaldo_previo_integro"] = len(backup_reports) == 1 and all(item.get("integridad_ok") and item.get("mismo_contenido") for item in backup_reports)
            else:
                checks["sin_respaldo_innecesario_o_invalido"] = not backup_reports
            if scenario == "duplicados_heredados":
                checks["diagnostico_duplicados"] = any("movimientos_abiertos_por_espacio" in item["texto"] for item in child.get("mensajes_criticos", []))
            if scenario == "esquema_futuro":
                checks["diagnostico_version"] = any("version_de_esquema_mas_nueva" in item["texto"] for item in child.get("mensajes_criticos", []))
            if backup_reports and all(item.get("integridad_ok") for item in backup_reports) and child.get("mensajes_criticos"):
                checks["mensaje_indica_respaldo"] = any("Respaldo previo:" in item["texto"] for item in child["mensajes_criticos"])
            result = dict(escenario=scenario, ok=all(checks.values()), comprobaciones=checks,
                          sha256_antes=before, sha256_despues=hash_file(candidate), version_inicial=version,
                          respaldos=backup_reports, proceso=child)
            report["escenarios"].append(result)
            print(f"{scenario}: {'OK' if result['ok'] else 'FALLO'}", flush=True)
            for name, passed in checks.items():
                if not passed:
                    print(f"  - {name}", flush=True)
        report["rutas_sqlite_controlador"] = sorted(audit_paths)
    report["temporales_eliminados"] = not temporary_root.exists()
    report["ok"] = all(result["ok"] for result in report["escenarios"]) and report["temporales_eliminados"]
    (output / "resultado.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Verificacion de errores del arranque normal", "", f"Fecha: {report['fecha']}", "",
             "Se ejecuto main.py como __main__ en procesos nuevos, sin --demo ni omitir autenticacion.",
             "Todas las bases fueron sinteticas y temporales; nunca se abrio la base real.", "",
             "| Escenario | Resultado | SHA256 candidato intacto | Respaldo previo |", "| --- | --- | --- | --- |"]
    for item in report["escenarios"]:
        backups_ok = all(backup.get("integridad_ok") and backup.get("mismo_contenido") for backup in item["respaldos"])
        backup_text = "Integro" if item["respaldos"] and backups_ok else ("No requerido/disponible" if not item["respaldos"] else "Error")
        lines.append(f"| {item['escenario']} | {'OK' if item['ok'] else 'FALLO'} | {'Si' if item['comprobaciones']['candidato_sin_cambios'] else 'NO'} | {backup_text} |")
    lines.extend(["", "## Comprobaciones", "", "- Salida de proceso 1 y mensaje critico legible en tema claro.",
                  "- No se llega al login, primer usuario ni a la ventana principal.",
                  "- Candidato sin cambios; respaldo de esquemas viejos valido y con contenido identico.",
                  "- Todas las conexiones SQLite auditadas dentro de TemporaryDirectory.",
                  f"- Temporales eliminados al finalizar: {'si' if report['temporales_eliminados'] else 'NO'}.", "",
                  "Los PNG muestran el aviso real, el boton Ver detalles abierto y las rutas desplazadas hasta el final.",
                  "Los JSON contienen la evidencia completa."])
    (output / "VERIFICACION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "preview_visual" / "revision_profunda" / "arranque")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--scenario", choices=SCENARIOS, help=argparse.SUPPRESS)
    parser.add_argument("--data-dir", type=Path, help=argparse.SUPPRESS)
    options = parser.parse_args()
    sys.exit(child_run(options) if options.child else controller(options))
