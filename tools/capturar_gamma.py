"""Capturas de la UI real para la muestra, exclusivamente con datos ficticios.

No cambia la aplicación. Todos los SQLite abiertos deben pertenecer a la
carpeta temporal; esta regla también cubre tickets y operaciones de prueba.
"""
import hashlib
import json
import os
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = "2"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
OUTPUT = ROOT / "material_muestra" / "capturas_gamma_2026-10-05"


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    originals = OUTPUT / "completas"
    originals.mkdir(exist_ok=True)
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                     for name in ("main.py", "database.py", "presentacion.py", "presentacion_estilos.py")}
    db_path = ROOT / "estacionamiento.db"
    before = (db_path.stat().st_size, db_path.stat().st_mtime_ns)
    now = datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None, microsecond=0)

    with TemporaryDirectory(prefix="gamma_boot_") as boot:
        os.environ["ESTACIONAMIENTO_DATA_DIR"] = boot
        import database
        from demo_muestra import preparar_demo
        session = preparar_demo(ahora=now)
        allowed = Path(database.DB_PATH).resolve().parent
        assert allowed != ROOT
        connections = []

        def guard(event, values):
            if event == "sqlite3.connect" and str(values[0]) != ":memory:":
                path = Path(str(values[0])).resolve()
                if not path.is_relative_to(allowed):
                    raise AssertionError(f"Conexión fuera de la demo: {path}")
                connections.append(str(path))
            if event in ("os.startfile", "subprocess.Popen"):
                raise AssertionError("Las capturas no pueden abrir servicios externos")

        sys.addaudithook(guard)
        with closing(database.get_connection()) as conn:
            conn.execute("UPDATE clientes SET dni=CAST(30000000+id_cliente AS TEXT)")
            conn.executemany("INSERT INTO configuracion(clave,valor) VALUES (?,?) "
                             "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (
                ("ui_tema", "claro"), ("ui_tamano_texto", "grande"),
                ("ui_resolucion", "1366x768"), ("empresa_nombre", "No hay lugar (demostración)")))
            conn.commit()

        import main
        from PySide6.QtCore import QPoint, QRect, Qt, QTimer
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtWidgets import QApplication, QMessageBox, QLabel

        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / filename))
        app._modo_demo = True
        main._aplicar_fuente_aplicacion(app)
        app._dialog_translation_filter = main._DialogTranslationFilter(app)
        app.installEventFilter(app._dialog_translation_filter)
        shots = []

        def settle():
            for _ in range(6):
                app.processEvents()

        def shot(widget, name, slide, note, rect=None, full=False):
            settle()
            # Un hijo puede tener fondo transparente: capturar su área desde
            # la ventana conserva el fondo real y no requiere editar el PNG.
            root = widget.window()
            if root is not widget:
                area = QRect(rect) if rect is not None else widget.rect()
                area.moveTopLeft(widget.mapTo(root, area.topLeft()))
                if root is window and window.statusBar().isVisible():
                    area = area.intersected(QRect(0, 0, root.width(), window.statusBar().y()))
                pixmap = root.grab(area)
            else:
                pixmap = widget.grab(rect) if rect is not None else widget.grab()
            target = (originals if full else OUTPUT) / (name + ".png")
            assert pixmap.save(str(target)), target
            shots.append({"archivo": str(target.relative_to(OUTPUT)), "diapositiva": slide,
                          "descripcion": note, "ancho": pixmap.width(), "alto": pixmap.height()})
            print(f"CAPTURA {target.name}: {pixmap.width()}x{pixmap.height()}", flush=True)

        def show_dialog(dialog, width, height):
            dialog.show()
            settle()
            dialog.resize(width, height)
            settle()
            if hasattr(dialog, "_presentation_scroll"):
                dialog._presentation_scroll.horizontalScrollBar().setValue(0)
                dialog._presentation_scroll.verticalScrollBar().setValue(0)
            settle()
            return dialog

        window = main.VentanaPrincipal(usuario="demo", rol="DUENO")
        window.resize(1366, 768)
        window.show()
        settle()
        shot(window, "03a_cochera_completa", 3, "Vista completa de cochera", full=True)
        shot(window.ui.page_cochera, "03a_cochera", 3, "Modalidad cochera mensual")
        window.ui.btn_estacionamiento.click()
        settle()
        shot(window, "03b_estacionamiento_completo", 3, "Vista completa de estacionamiento", full=True)
        shot(window.ui.page_estacionamiento, "03b_estacionamiento", 3, "Modalidad estacionamiento por tiempo")

        # El mismo vehículo recorre ingreso, permanencia y salida.
        plate = "DM777MO"
        window.ui.input_patente_est.setText(plate)
        window.ui.input_espacio_est.setText("E07")
        window.ui.combo_tipo_vehiculo_est.setCurrentIndex(window.ui.combo_tipo_vehiculo_est.findData("AUTO"))
        shot(window.ui.group_est_registro, "04a_registrar_ingreso", 4,
             "Ingreso de DM 777 MO en E07, antes de confirmar")

        class DemoDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return cls.instant
                return cls.instant.replace(tzinfo=timezone(timedelta(hours=-3))).astimezone(tz)

        DemoDateTime.instant = now - timedelta(hours=2, minutes=5)

        def capture_message(box):
            box.show()
            settle()
            if box.windowTitle() == "Ticket de ingreso":
                shot(box, "04a_ingreso_confirmado", 4, "Confirmación real del ingreso", full=True)
            box.hide()
            return int(QMessageBox.Ok)

        with patch.object(main, "datetime", DemoDateTime), patch.object(QMessageBox, "exec", capture_message):
            window._registrar_ingreso_est()
        settle()
        with closing(database.get_connection()) as conn:
            movement = conn.execute("SELECT m.* FROM movimientos m JOIN vehiculos v USING(id_vehiculo) "
                                    "WHERE v.patente=? AND m.fecha_salida IS NULL", (plate,)).fetchone()
            assert movement is not None
        window._input_filtro_est_activos.setText(plate)
        settle()
        window.ui.table_est_activos.setCurrentCell(0, 0)
        shot(window.ui.group_est_activos, "04b_vehiculo_en_estacionamiento", 4,
             "El mismo vehículo aparece en la lista de vehículos activos",
             QRect(0, 0, window.ui.group_est_activos.width(), 180))
        window._input_filtro_est_activos.clear()

        def capture_question(parent, title, message, buttons, default):
            box = QMessageBox(QMessageBox.Question, title, message, buttons, parent)
            box.setDefaultButton(default)
            box.show()
            settle()
            box.setMinimumWidth(560)
            box.adjustSize()
            settle()
            shot(box, "04c_salida_completa", 4, "Confirmación de salida original", full=True)
            label = box.findChild(QLabel, "qt_msgbox_label")
            content_height = label.y() + 7 * label.fontMetrics().lineSpacing() + 16
            shot(box, "04c_calculo_de_salida", 4,
                 "Cálculo real: 2 h 5 min, tolerancia 15 min, 2 horas cobradas a $1.500",
                 QRect(0, 0, box.width(), content_height))
            box.hide()
            return QMessageBox.No  # No cobramos ni cerramos el ejemplo.

        window.ui.input_patente_est.setText(plate)
        DemoDateTime.instant = now
        with patch.object(main, "datetime", DemoDateTime), patch.object(QMessageBox, "question", capture_question):
            window._registrar_salida_est()

        mapa = show_dialog(main.MapaCocheraDialog(window), 1140, 980)
        mapa.view.horizontalScrollBar().setValue(0)
        mapa.view.verticalScrollBar().setValue(0)
        settle()
        shot(mapa, "05_mapa_completo", 5, "Mapa y herramientas originales", full=True)
        # Captura de la leyenda y el área real del mapa; sin fabricar gráficos.
        viewport_top = mapa.view.mapTo(mapa, QPoint(0, 0)).y()
        shot(mapa, "05_mapa_de_espacios", 5, "Mapa real con libres, ocupados y cocheras",
             QRect(16, viewport_top - 40, mapa.width() - 32, min(800, mapa.height() - viewport_top + 24)))
        mapa.hide()

        contracts = show_dialog(main.ContratosDialog(window, rol="DUENO"), 1260, 780)
        contracts.input_buscar.setText("Lucía Fernández")
        settle()
        assert contracts.table.rowCount() == 1
        contracts.table.setCurrentCell(0, 0)
        settle()
        assert contracts.input_patente.text()
        assert contracts.input_espacio.text() == "C01"
        shot(contracts, "06_contrato_completo", 6, "Contrato real seleccionado con datos ficticios", full=True)
        form_top = min(field.mapTo(contracts, QPoint(0, 0)).y() for field in (
            contracts.input_dni, contracts.input_patente, contracts.input_modelo,
            contracts.input_tipo_vehiculo, contracts.input_espacio,
            contracts.input_venc, contracts.input_monto)) - 12
        form_bottom = max(field.mapTo(contracts, QPoint(0, field.height())).y() for field in (
            contracts.input_dni, contracts.input_patente, contracts.input_modelo,
            contracts.input_tipo_vehiculo, contracts.input_espacio,
            contracts.input_venc, contracts.input_monto)) + 12
        shot(contracts, "06_datos_del_contrato", 6, "Espacio, patente, monto y vencimiento del contrato",
             QRect(14, form_top, contracts.width() - 28, form_bottom - form_top))
        table_top = contracts.table.mapTo(contracts, QPoint(0, 0)).y()
        shot(contracts, "06_cliente_y_contrato", 6, "Cliente y fila del contrato seleccionado",
             QRect(14, table_top, contracts.width() - 28, 106))
        contracts.hide()

        simple = show_dialog(main.ModoSencilloEstacionamientoDialog(window), 860, 460)
        shot(simple, "07a_modo_sencillo", 7, "Modo sencillo original, sin cambios de diseño")
        simple.hide()

        reports = show_dialog(main.ReportesDialog(window), 1180, 630)
        reports.combo_tipo.setCurrentText("Todos")
        reports.btn_actualizar.setFocus()
        settle()
        shot(reports, "07b_reportes_completos", 7, "Reportes y exportación a Excel", full=True)
        report_bottom = (reports.table_historial.mapTo(reports, QPoint(0, 0)).y()
                         + reports.table_historial.horizontalHeader().height()
                         + sum(reports.table_historial.rowHeight(i) for i in range(4))
                         + reports.table_historial.frameWidth())
        shot(reports, "07b_reportes", 7, "Resumen de ingresos y detalle por medio de pago",
             QRect(0, 0, reports.width(), report_bottom))
        reports.hide()

        with closing(database.get_connection()) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        after = (db_path.stat().st_size, db_path.stat().st_mtime_ns)
        assert before == after, "La base real cambió durante la captura; verificar antes de afirmar aislamiento"
        for name, expected in source_hashes.items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
        manifest = {"generado": now.isoformat(), "origen": "Widgets reales de la aplicación, captura nativa Qt a escala 2",
                    "datos": "Todos ficticios; demo nueva y desechable", "base_real_abierta": False,
                    "base_real_metadata_sin_cambios": before == after,
                    "conexiones_verificadas_solo_demo": len(connections), "fuentes_sha256": source_hashes,
                    "capturas": shots}
        (OUTPUT / "verificacion.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        window.hide()
        for widget in app.topLevelWidgets():
            widget.hide()
        session.cleanup()
    print("OK: capturas reales, datos ficticios, sin abrir la base de trabajo ni editar la aplicación.")


if __name__ == "__main__":
    run()
