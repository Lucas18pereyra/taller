r"""Verificación del programa completo, sin --demo y sin escribir en la base real.

Ejecutar con .venv\Scripts\python.exe tools\verificar_normal.py.
Las bases y credenciales de QA son temporales; las evidencias quedan en
preview_visual/normal. Nunca se leen las contraseñas de los usuarios originales.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import traceback
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
REAL_DB = ROOT / "estacionamiento.db"
TABLES = (
    "usuarios", "clientes", "vehiculos", "espacios", "cochera_contratos",
    "movimientos", "pagos", "pagos_cochera", "tarifas", "configuracion",
)
QA_USER = "qa_visual"
QA_PASSWORD = "SoloPrueba123"


def hash_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def counts(path):
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
        present = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in TABLES if name in present}


def seed_fixture(database):
    """Sólo prepara insumos de QA. Los cobros se prueban con servicios reales."""
    from datetime import date, timedelta

    with database.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO clientes (dni,nombre,direccion,telefono,activo) "
                    "VALUES ('99900001','Cliente QA','Dirección ficticia','Sin contacto',1)")
        client = cur.lastrowid
        cur.execute("INSERT INTO vehiculos (patente,modelo,tipo_vehiculo,id_cliente) "
                    "VALUES ('QA001AA','Vehículo QA','AUTO',?)", (client,))
        vehicle = cur.lastrowid
        cur.execute("INSERT INTO espacios (codigo,es_reservado,activo) VALUES ('QA-C01',1,1)")
        cochera = cur.lastrowid
        cur.execute("INSERT INTO espacios (codigo,es_reservado,activo) VALUES ('QA-E01',0,1)")
        cur.execute("INSERT INTO espacios (codigo,es_reservado,activo) VALUES ('QA-E02',0,1)")
        for index, code in enumerate(("QA-C01", "QA-E01", "QA-E02")):
            cur.execute("INSERT INTO espacios_mapa (codigo,x,y,w,h) VALUES (?,?,50,120,70)",
                        (code, 80 + index * 160))
        cur.execute("INSERT INTO tarifas (precio_hora,precio_hora_auto,precio_hora_moto,"
                    "precio_hora_camioneta,precio_mensual,precio_mensual_auto,"
                    "precio_mensual_camioneta,activa) VALUES (1500,1500,1000,2000,48000,48000,60000,1)")
        cur.execute("INSERT INTO cochera_contratos (id_cliente,id_vehiculo,id_espacio,"
                    "fecha_vencimiento,monto_mensual,activo) VALUES (?,?,?,?,48000,0)",
                    (client, vehicle, cochera, (date.today() + timedelta(days=20)).isoformat()))
        contract = cur.lastrowid
        conn.commit()
    conn.close()
    return contract


def child_run(args):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["ESTACIONAMIENTO_DATA_DIR"] = str(args.data_dir)
    sys.path.insert(0, str(ROOT))
    import database

    database.DB_PATH = args.data_dir / "estacionamiento.db"
    report = {"scenario": args.scenario, "status": "running", "checks": [],
              "dialogs": [], "messages": [], "external_attempts": [], "captures": []}
    sql_paths = set()

    def audit(event, values):
        if event == "sqlite3.connect":
            raw_path = str(values[0])
            if raw_path.startswith("file:"):
                raw_path = unquote(urlsplit(raw_path).path).lstrip("/")
            candidate = Path(raw_path).resolve()
            if not candidate.is_relative_to(args.data_dir.resolve()):
                raise AssertionError("Conexión SQLite fuera de la carpeta aislada de prueba")
            sql_paths.add(str(candidate))
        if event in ("os.startfile", "subprocess.Popen"):
            report["external_attempts"].append(event)
            raise AssertionError("La verificación no permite abrir aplicaciones externas")

    sys.addaudithook(audit)
    before = counts(database.DB_PATH) if database.DB_PATH.exists() else {}
    database.init_db()
    after = counts(database.DB_PATH)
    assert all(after.get(name) == value for name, value in before.items() if name != "configuracion"), (before, after)
    report["counts_before_init"] = before
    report["counts_after_init"] = after
    report["checks"].append("init_db conserva los conteos de datos existentes")
    role = "OPERADOR" if args.scenario == "operador" else "DUENO"
    with database.get_connection() as conn:
        for key, value in {
            "ui_tema": "claro", "ui_resolucion": "1280x800", "ui_tamano_texto": "normal",
            "empresa_nombre": "Estacionamiento QA", "empresa_direccion": "Dirección ficticia",
            "empresa_telefono": "Sin contacto (QA)",
            **{key: str(args.data_dir / folder) for key, folder in (
                ("dir_reportes", "reportes"), ("dir_comprobantes", "comprobantes"),
                ("dir_tickets_salida", "tickets_salida"))},
        }.items():
            conn.execute("INSERT INTO configuracion (clave,valor) VALUES (?,?) "
                         "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (key, value))
        if args.scenario not in ("primer_usuario", "reabrir"):
            conn.execute("INSERT INTO usuarios (usuario,password,rol,activo) VALUES (?,?,?,1)",
                         (QA_USER, QA_PASSWORD, role))
        conn.commit()
    conn.close()
    contract = seed_fixture(database) if args.scenario in ("dueno", "operador") else None

    import runpy
    from datetime import datetime, timedelta
    from zipfile import ZipFile
    from PySide6.QtCore import QDate, QTimer
    from PySide6.QtGui import QDesktopServices, QFontDatabase, QPalette
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

    real_app_exec = QApplication.exec
    real_app_init = QApplication.__init__
    real_dialog_exec = QDialog.exec
    completed = False

    def app_init(app, *values, **kwargs):
        real_app_init(app, *values, **kwargs)
        # El plugin offscreen de Windows no descubre fuentes del sistema.
        # Registrar las mismas fuentes de la UI antes de crear los formularios.
        folder = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        loaded = []
        for name in ("segoeui.ttf", "segoeuib.ttf", "arial.ttf", "arialbd.ttf"):
            font_id = QFontDatabase.addApplicationFont(str(folder / name))
            if font_id >= 0:
                loaded.extend(QFontDatabase.applicationFontFamilies(font_id))
        assert "Segoe UI" in loaded, "No se pudo cargar Segoe UI para las capturas"
        report["offscreen_fonts"] = sorted(set(loaded))

    QApplication.__init__ = app_init

    def capture(widget, name):
        path = args.output / f"{args.scenario}_{name}.png"
        assert widget.grab().save(str(path)), path
        report["captures"].append(path.name)

    def message(kind, *values, **kwargs):
        title = str(values[1]) if len(values) > 1 else ""
        report["messages"].append({"kind": kind, "title": title})
        return QMessageBox.Yes if kind == "question" else QMessageBox.Ok

    for kind in ("information", "warning", "critical", "question"):
        setattr(QMessageBox, kind, lambda *values, _kind=kind, **kw: message(_kind, *values, **kw))

    def box_exec(box):
        report["messages"].append({"kind": "box", "title": box.windowTitle()})
        return QMessageBox.Ok

    QMessageBox.exec = box_exec

    def forbidden_url(url):
        report["external_attempts"].append("QDesktopServices.openUrl")
        return False

    QDesktopServices.openUrl = forbidden_url

    def dialog_exec(dialog):
        name = type(dialog).__name__
        report["dialogs"].append(name)

        def drive():
            try:
                if name in ("LoginDialog", "FirstUserDialog"):
                    dialog.input_usuario.setText(QA_USER)
                    dialog.input_password.setText(QA_PASSWORD)
                    if name == "FirstUserDialog":
                        dialog.input_password2.setText(QA_PASSWORD)
                    capture(dialog, "acceso")
                    (dialog.btn_crear if name == "FirstUserDialog" else dialog.btn_ingresar).click()
                    assert dialog.result() == QDialog.Accepted, "El acceso normal no fue aceptado"
                    report["checks"].append("primer administrador creado mediante formulario" if name == "FirstUserDialog"
                                            else "login aceptado mediante campos y botón reales")
                else:
                    capture(dialog, name)
                    dialog.reject()
            except BaseException:
                report["callback_error"] = traceback.format_exc()
                dialog.reject()

        QTimer.singleShot(80, drive)
        return real_dialog_exec(dialog)

    QDialog.exec = dialog_exec

    def exercise():
        nonlocal completed
        app = QApplication.instance()
        windows = [w for w in app.topLevelWidgets() if type(w).__name__ == "VentanaPrincipal" and w.isVisible()]
        try:
            assert len(windows) == 1, "No se abrió la ventana principal normal"
            window = windows[0]
            namespace = window._refrescar_dashboard.__func__.__globals__
            assert app._modo_demo is False and app._demo_session is None
            assert app.palette().color(QPalette.Window).name() == "#f2f5f8"
            assert window.rol == role
            assert window._presentacion.demo is False
            report["checks"].append("arranque completo sin --demo, tema claro y rol correcto")
            if args.scenario == "primer_usuario":
                seed_fixture(database)
                window._actualizar_estado_menu_estacionamiento()
                window._refrescar_dashboard()
                report["checks"].append("primer usuario puede continuar con la puesta en marcha")
            capture(window, "cochera")
            window.ui.btn_estacionamiento.click()
            assert window.ui.stack.currentIndex() == 1
            capture(window, "estacionamiento")
            window.ui.btn_cochera.click()
            assert window.ui.stack.currentIndex() == 0
            assert window.ui.btn_reportes.isVisible() == (role == "DUENO")
            assert window.ui.btn_vencimientos.isVisible() == (role == "DUENO")
            report["checks"].append("navegación y visibilidad por rol DUENO/OPERADOR")
            for callback in (window._abrir_clientes, window._abrir_contratos, window._abrir_mapa_cocheras,
                             window._abrir_configuracion, window._abrir_historial, window._abrir_cierre_caja):
                callback()
            if role == "OPERADOR":
                count = len(report["dialogs"])
                window._abrir_tarifas()
                window._abrir_usuarios()
                assert len(report["dialogs"]) == count
                assert report["messages"][-2:] == [
                    {"kind": "warning", "title": "Administracion"},
                    {"kind": "warning", "title": "Administracion"},
                ]
                report["checks"].append("operador impedido de abrir usuarios y tarifas")
            if args.scenario == "dueno":
                from servicios.contratos import registrar_primer_pago_contrato, registrar_renovacion_contrato
                from servicios.reportes import consultar_resumen
                from servicios.backups import crear_backup_db, restaurar_backup_db

                activation = registrar_primer_pago_contrato(contract, 48000, "Efectivo", usuario=QA_USER)
                renewal = registrar_renovacion_contrato(contract, 1, 48000, "Transferencia", usuario=QA_USER)
                assert activation["id_cliente"] and renewal > activation["fecha_vencimiento"]
                receipt = namespace["_emitir_comprobante_cochera"](
                    contract, 48000, "Transferencia", 1, renewal)
                assert receipt and receipt.read_bytes().startswith(b"%PDF") and receipt.stat().st_size > 1000
                report["checks"].append("activación y renovación reales de contrato, comprobante PDF")

                window.ui.btn_estacionamiento.click()
                window.ui.input_patente_est.setText("QA102AA")
                window.ui.input_espacio_est.setText("QA-E01")
                combo = window.ui.combo_tipo_vehiculo_est
                index = combo.findData("AUTO")
                assert index >= 0
                combo.setCurrentIndex(index)
                window._registrar_ingreso_est()
                with database.get_connection() as conn:
                    movement = conn.execute("SELECT m.id_movimiento FROM movimientos m JOIN vehiculos v "
                                            "ON v.id_vehiculo=m.id_vehiculo WHERE v.patente='QA102AA' "
                                            "AND m.fecha_salida IS NULL").fetchone()
                    assert movement, "No se registró el ingreso desde la interfaz"
                    # Simular tiempo transcurrido sólo sobre el movimiento de QA.
                    conn.execute("UPDATE movimientos SET fecha_ingreso=? WHERE id_movimiento=?",
                                 ((datetime.now() - timedelta(hours=2, minutes=5)).strftime("%Y-%m-%d %H:%M:%S"), movement[0]))
                    conn.commit()
                conn.close()
                window.ui.input_patente_est.setText("QA102AA")
                window._solicitar_metodo_pago_est = lambda **kwargs: "Efectivo"
                window._registrar_salida_est()
                with database.get_connection() as conn:
                    payment = conn.execute("SELECT m.fecha_salida,m.total,p.monto FROM movimientos m "
                                           "JOIN pagos p ON p.id_movimiento=m.id_movimiento WHERE m.id_movimiento=?", movement).fetchone()
                    assert payment and payment[0] and payment[1] == payment[2] == 3000, tuple(payment or ())
                conn.close()
                assert list((args.data_dir / "tickets_salida").glob("*.pdf"))
                report["checks"].append("ingreso y salida desde UI, tarifa aplicada y pago $3000, tickets PDF")

                detail = namespace["ReportesDialog"](window)
                detail.input_desde.setDate(QDate.currentDate().addDays(-1))
                detail.input_hasta.setDate(QDate.currentDate())
                detail._cargar()
                excel = args.data_dir / "reportes" / "reporte_qa.xlsx"
                excel.parent.mkdir(parents=True, exist_ok=True)
                QFileDialog.getSaveFileName = lambda *a, **kw: (str(excel), "Excel (*.xlsx)")
                detail._exportar_excel()
                assert excel.exists() and excel.stat().st_size > 1000
                with ZipFile(excel) as archive:
                    assert archive.testzip() is None and "xl/workbook.xml" in archive.namelist()
                report["checks"].append("exportación Excel real mediante ReportesDialog")
                summary = consultar_resumen(datetime.now().strftime("%Y-%m"))
                assert summary[0] >= 96000 and summary[1] >= 3000
                report["report_totals"] = summary
                backup = crear_backup_db()
                assert backup and backup.exists()
                assert restaurar_backup_db(backup)
                report["checks"].append("respaldo y restauración reales en carpeta aislada")
                detail.close()
                window._refrescar_dashboard()
                capture(window, "operaciones")
            if args.scenario == "reabrir":
                with database.get_connection() as conn:
                    assert conn.execute("SELECT COUNT(*) FROM pagos_cochera WHERE usuario=?", (QA_USER,)).fetchone()[0] == 2
                    assert conn.execute("SELECT COUNT(*) FROM pagos p JOIN movimientos m ON m.id_movimiento=p.id_movimiento "
                                        "JOIN vehiculos v ON v.id_vehiculo=m.id_vehiculo WHERE v.patente='QA102AA'").fetchone()[0] == 1
                conn.close()
                report["checks"].append("cierre y reapertura conservan contrato y pagos de la sesión anterior")
            assert not report.get("callback_error"), report.get("callback_error")
            assert not report["external_attempts"], report["external_attempts"]
            assert not any(m["kind"] == "critical" for m in report["messages"]), report["messages"]
            with database.get_connection() as conn:
                assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert not conn.execute("PRAGMA foreign_key_check").fetchall()
            conn.close()
            report["checks"].append("integridad y referencias correctas después de operar")
            completed = True
        except BaseException:
            report["error"] = traceback.format_exc()
        finally:
            for window in windows:
                window.close()
            app.quit()

    def app_exec(app):
        QTimer.singleShot(1600, exercise)
        QTimer.singleShot(12000, app.quit)
        return real_app_exec()

    QApplication.exec = app_exec
    sys.argv = [str(ROOT / "main.py")]
    try:
        runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
    except SystemExit as exc:
        assert exc.code in (None, 0), exc.code
    finally:
        QApplication.exec = real_app_exec
        QApplication.__init__ = real_app_init
        QDialog.exec = real_dialog_exec
    report["status"] = "passed" if completed else "failed"
    report["sqlite_paths"] = sorted(sql_paths)
    report["counts_after_close"] = counts(database.DB_PATH)
    report["closed_normally"] = not any(w.isVisible() for w in QApplication.instance().topLevelWidgets())
    (args.output / f"{args.scenario}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.scenario + ": " + report["status"])
    return 0 if completed and report["closed_normally"] else 1


def controller(args):
    args.output.mkdir(parents=True, exist_ok=True)
    initial_hash = hash_file(REAL_DB)
    results = []
    with TemporaryDirectory(prefix="estacionamiento_normal_qa_") as temporary:
        isolated = Path(temporary)
        for scenario in ("dueno", "reabrir", "operador", "primer_usuario"):
            data = isolated / ("dueno" if scenario == "reabrir" else scenario)
            data.mkdir(exist_ok=True)
            if scenario in ("dueno", "operador"):
                source = sqlite3.connect(REAL_DB.as_uri() + "?mode=ro", uri=True)
                target = sqlite3.connect(data / "estacionamiento.db")
                try:
                    source.backup(target)
                finally:
                    target.close()
                    source.close()
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--scenario", scenario,
                       "--data-dir", str(data), "--output", str(args.output)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=40)
            evidence = args.output / f"{scenario}.json"
            item = json.loads(evidence.read_text(encoding="utf-8")) if evidence.exists() else {
                "scenario": scenario, "status": "failed", "error": result.stdout + result.stderr}
            item["exit_code"] = result.returncode
            results.append(item)
            print(scenario + ": " + item["status"])
            if result.returncode and result.stderr:
                print(result.stderr)
    unchanged = hash_file(REAL_DB) == initial_hash
    summary = {"normal_mode_only": True, "real_db_unchanged": unchanged,
               "real_db_sha256": initial_hash, "temporary_data_removed": not isolated.exists(),
               "scenarios": results}
    (args.output / "resultado.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Verificación del programa completo", "", "Pruebas sin `--demo`, sobre una copia consistente y bases temporales.",
             "Las credenciales originales no se leen. El acceso QA existe sólo en la copia.", "",
             f"Base original sin cambios: {unchanged}.", f"SHA256: `{initial_hash}`.",
             f"Datos temporales eliminados: {not isolated.exists()}.", ""]
    for item in results:
        lines += [f"## {item['scenario']}: {item['status']}", ""]
        lines += ["- " + check for check in item.get("checks", [])]
        if item.get("error"):
            lines += ["", "```text", item["error"], "```"]
        lines += [""]
    (args.output / "VERIFICACION.md").write_text("\n".join(lines), encoding="utf-8")
    return 0 if unchanged and all(item["status"] == "passed" and item["exit_code"] == 0 for item in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("dueno", "operador", "primer_usuario", "reabrir"))
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "preview_visual" / "normal")
    parsed = parser.parse_args()
    parsed.output = parsed.output.resolve()
    if parsed.scenario:
        assert parsed.data_dir, "Falta --data-dir"
        parsed.data_dir = parsed.data_dir.resolve()
        assert parsed.data_dir != ROOT and not REAL_DB.is_relative_to(parsed.data_dir)
        assert parsed.data_dir.parent.name.startswith("estacionamiento_normal_qa_"), "La prueba sólo acepta su propia carpeta temporal"
        sys.exit(child_run(parsed))
    sys.exit(controller(parsed))
