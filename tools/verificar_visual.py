"""Render real Qt screens and verify visual interactions using disposable data."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def contrast(foreground, background):
    def luminance(value):
        channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045
                  else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    values = sorted((luminance(foreground), luminance(background)))
    return (values[1] + 0.05) / (values[0] + 0.05)


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "preview_visual"))
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--deep-case", choices=("empty_1024", "empty_1366", "abundant_1024", "abundant_1366", "dpi_125", "dpi_150"))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if args.deep_case:
        run_deep_case(args.deep_case, output)
        return
    if args.deep:
        run_deep(output)
        return
    original_db = ROOT / "estacionamiento.db"
    before = hashlib.sha256(original_db.read_bytes()).hexdigest() if original_db.exists() else None
    from demo_muestra import preparar_demo
    session = preparar_demo()
    import database
    import main
    assert main._config_get("ui_tema") == "oscuro"
    # The showcase starts dark; explicitly exercise the preserved light theme too.
    main._config_set("ui_tema", "claro")
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtGui import QFontDatabase, QPalette
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    from presentacion_estilos import palette
    app = QApplication([])
    # Windows' offscreen plugin has no system font database; native Windows does.
    for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        path = Path("C:/Windows/Fonts") / filename
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app._modo_demo = True
    main._aplicar_fuente_aplicacion(app)
    app._dialog_translation_filter = main._DialogTranslationFilter(app)
    app.installEventFilter(app._dialog_translation_filter)
    window = main.VentanaPrincipal(usuario="demo", rol="DUENO")
    window.resize(1280, 800)
    window.show()
    app.processEvents()
    assert window.ui.label_total_value.text() == "24"
    assert window.ui.label_ocupadas_value.text() == "16"
    assert window.ui.label_libres_value.text() == "8"
    assert window.ui.btn_cochera.isChecked()
    assert not window.ui.btn_estacionamiento.isChecked()
    assert not window.ui.menubar.isVisible()
    window.grab().save(str(output / "01_cochera.png"))
    window.ui.btn_estacionamiento.click()
    app.processEvents()
    assert window.ui.stack.currentIndex() == 1
    assert window.ui.btn_estacionamiento.isChecked()
    assert window.ui.table_est_activos.columnCount() == 3
    assert window.ui.table_est_activos.rowCount() == 6
    first_plate = window.ui.table_est_activos.item(0, 0).text()
    window.ui.table_est_activos.setCurrentCell(0, 0)
    assert window._patente_desde_tabla_est(0, 0) == first_plate.upper()
    window.grab().save(str(output / "02_estacionamiento.png"))
    window._input_filtro_est_activos.setText("sin-coincidencias")
    app.processEvents()
    assert window.ui.table_est_activos.columnSpan(0, 0) == 3
    window._input_filtro_est_activos.clear()
    app.processEvents()
    assert window.ui.table_est_activos.rowCount() == 6
    assert window.ui.table_est_activos.columnSpan(0, 0) == 1
    dialogs = [
        ("03_login", main.LoginDialog()),
        ("04_clientes", main.ClientesDialog(window, rol="DUENO")),
        ("05_contratos", main.ContratosDialog(window, rol="DUENO")),
        ("06_reportes", main.ReportesDialog(window)),
        ("07_mapa", main.MapaCocheraDialog(window)),
        ("08_configuracion", main.ConfiguracionDialog(window, rol="DUENO")),
        ("09_vencimientos", main.VencimientosDialog(window)),
        ("10_modo_sencillo", main.ModoSencilloEstacionamientoDialog(window)),
        ("11_primer_usuario", main.FirstUserDialog()),
    ]
    for name, dialog in dialogs:
        dialog.show()
        app.processEvents()
        if name not in {"03_login", "10_modo_sencillo", "11_primer_usuario"}:
            dialog.resize(1100, 700)
            app.processEvents()
        assert dialog.property("presentationPrepared")
        dialog.grab().save(str(output / (name + ".png")))
        if name == "03_login":
            dialog.input_usuario.setText("demo")
            dialog.input_password.setText("demo")
            dialog.btn_ingresar.click()
            assert dialog.result() == QDialog.Accepted
            assert dialog.rol == "DUENO"
        elif name == "04_clientes":
            dialog.table.setCurrentCell(0, 0)
            app.processEvents()
            assert dialog.input_nombre.text() == dialog.table.item(0, 0).text()
            assert dialog.vehiculos_table.rowCount() == 1
        elif name == "05_contratos":
            dialog.table.setCurrentCell(0, 0)
            app.processEvents()
            assert dialog._selected_ids()[0]
            assert dialog.input_patente.text()
            dialog.input_buscar.setText("sin-coincidencias")
            app.processEvents()
            assert dialog.table.rowCount() == 0
            dialog.input_buscar.clear()
            app.processEvents()
            assert dialog.table.rowCount() == 16
        dialog.hide()
    # Reapplying preferences must retain layout and each callback just once.
    main._config_set("ui_tema", "oscuro")
    window._aplicar_preferencias_ui()
    app.processEvents()
    window.ui.stack.setCurrentIndex(0)
    app.processEvents()
    dark = palette(False)
    assert dark["bg"] == "#1E1E1E"
    assert dark["sidebar"] == "#252526"
    assert dark["accent"] == "#007ACC"
    assert contrast(dark["text"], dark["bg"]) >= 7
    assert contrast(dark["muted"], dark["surface"]) >= 4.5
    for token in ("accent", "accent_hover", "success_button", "danger_button", "warning_button"):
        assert contrast(dark["on_accent"], dark[token]) >= 4.5, token
    assert app.palette().color(QPalette.Window).name() == dark["bg"].lower()
    assert window._presentacion.map.light is False
    assert window.grab().toImage().pixelColor(5, 100).name() == dark["sidebar"].lower()
    window.grab().save(str(output / "12_oscuro.png"))
    window.ui.btn_estacionamiento.click()
    app.processEvents()
    assert window.ui.stack.currentIndex() == 1
    assert window.ui.table_est_activos.rowCount() == 6
    window.grab().save(str(output / "16_estacionamiento_oscuro.png"))
    dark_dialogs = [
        ("17_login_oscuro", main.LoginDialog()),
        ("18_contratos_oscuro", main.ContratosDialog(window, rol="DUENO")),
        ("19_reportes_oscuro", main.ReportesDialog(window)),
        ("20_configuracion_oscuro", main.ConfiguracionDialog(window, rol="DUENO")),
        ("21_vencimientos_oscuro", main.VencimientosDialog(window)),
        ("22_mapa_oscuro", main.MapaCocheraDialog(window)),
    ]
    for name, dialog in dark_dialogs:
        dialog.show()
        app.processEvents()
        if name != "17_login_oscuro":
            dialog.resize(1100, 700)
            app.processEvents()
        assert dialog.property("presentationPrepared")
        dialog.grab().save(str(output / (name + ".png")))
        dialog.hide()
    window.ui.stack.setCurrentIndex(0)
    main._config_set("ui_tema", "claro")
    window._aplicar_preferencias_ui()
    app.processEvents()
    assert app.palette().color(QPalette.Window).name() == palette(True)["bg"].lower()
    assert window._presentacion.map.light is True
    window.resize(1024, 600)
    app.processEvents()
    window.grab().save(str(output / "13_compacto.png"))
    window.resize(1366, 768)
    window.ui.stack.setCurrentIndex(1)
    app.processEvents()
    window.grab().save(str(output / "14_estacionamiento_1366.png"))
    operator = main.VentanaPrincipal(usuario="operador", rol="OPERADOR")
    operator.show()
    app.processEvents()
    assert operator.ui.card_ingresos.isHidden()
    assert operator.ui.btn_reportes.isHidden()
    assert operator.ui.btn_vencimientos.isHidden()
    assert operator._presentacion.due_panel.isHidden()
    operator.grab().save(str(output / "15_operador.png"))
    operator.hide()
    # Allow clocks/dashboard timers to run, with no startup popup in demo mode.
    QTimer.singleShot(1200, app.quit)
    app.exec()
    assert not any(isinstance(widget, QMessageBox) and widget.isVisible() for widget in app.topLevelWidgets())
    with closing(database.get_connection()) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    window.hide()
    if original_db.exists():
        after = hashlib.sha256(original_db.read_bytes()).hexdigest()
        assert before == after, "Original database changed during visual verification"
    session.cleanup()
    print("PASS: dashboard, navigation, 3-column active table, filter/reset, light/VS Code dark,")
    print("      small display, dialogs, login, client/contract selection and search,")
    print("      operator visibility and isolated demo database.")
    print("Original database SHA256:", before)
    print("Screenshots:", output)


def run_deep(output):
    """Each DPI/font profile owns its process and an isolated database."""
    results = []
    for case, dpi in (("empty_1024", "1"), ("empty_1366", "1"),
                      ("abundant_1024", "1"), ("abundant_1366", "1"),
                      ("dpi_125", "1.25"), ("dpi_150", "1.5")):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=dpi,
                   PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                  "--deep-case", case, "--output", str(output)],
                                 env=env, capture_output=True, text=True, timeout=90)
        if process.returncode:
            raise AssertionError(f"{case}: {process.stdout}\n{process.stderr}")
        result = json.loads((output / case / "result.json").read_text(encoding="utf-8"))
        results.append(result)
        print(f"PASS {case}: {len(result['screens'])} screens, reachable controls, isolated data", flush=True)
    (output / "resultado_visual.json").write_text(
        json.dumps({"profiles": results, "status": "passed"}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def run_deep_case(case, output):
    import sqlite3
    from unittest.mock import patch
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFontDatabase
    from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox,
                                  QLabel, QMessageBox, QPushButton, QTableWidget)
    folder = output / case
    folder.mkdir(parents=True, exist_ok=True)
    width, height = (1024, 600) if "1024" in case else (1366, 768)
    font_size = "muy_grande" if case == "abundant_1024" else "grande"
    screens = []
    messages = []
    with TemporaryDirectory(prefix="estacionamiento_visual_profunda_") as temp:
        os.environ["ESTACIONAMIENTO_DATA_DIR"] = temp
        import database
        session = None
        if not case.startswith("empty"):
            from demo_muestra import preparar_demo
            session = preparar_demo()
        else:
            database.init_db()
        allowed = Path(database.DB_PATH).resolve().parent

        def audit(event, values):
            if event == "sqlite3.connect" and str(values[0]) != ":memory:":
                assert Path(str(values[0])).resolve().is_relative_to(allowed), values[0]
            if event in ("os.startfile", "subprocess.Popen"):
                raise AssertionError("Visual QA cannot start external services")

        sys.addaudithook(audit)
        import main
        from presentacion_estilos import palette
        main._config_set("ui_tema", "claro")
        main._config_set("ui_tamano_texto", font_size)
        main._config_set("ui_resolucion", f"{width}x{height}")
        # Only suppress startup scheduling; each notice screen is inspected below.
        main.VentanaPrincipal._programar_popup_vencimientos_inicio = lambda self: None
        main.VentanaPrincipal._programar_popup_primeros_pasos = lambda self: None
        for kind in ("information", "warning", "critical", "question"):
            setattr(QMessageBox, kind, lambda *a, _kind=kind, **kw:
                    messages.append(_kind) or QMessageBox.No)
        if session:
            with closing(database.get_connection()) as conn:
                conn.execute("UPDATE clientes SET nombre=? WHERE id_cliente=(SELECT min(id_cliente) FROM clientes)",
                             ("María de los Ángeles Fernández de la Torre y Rodríguez del Valle",))
                for index in range(60):
                    conn.execute("INSERT INTO clientes (dni,nombre,telefono,activo) VALUES (?,?,?,1)",
                                 (str(98000000 + index), f"Cliente de prueba abundante {index:03d} con apellido extenso", "Sin contacto QA"))
                conn.commit()
        app = QApplication([])
        for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / filename))
        app._modo_demo = False
        main._aplicar_fuente_aplicacion(app)
        app._dialog_translation_filter = main._DialogTranslationFilter(app)
        app.installEventFilter(app._dialog_translation_filter)
        window = main.VentanaPrincipal(usuario="Nombre de usuario largo para comprobar toda la navegación", rol="DUENO")
        window.resize(width, height)
        window.show()
        app.processEvents()
        assert window.width() == width and window.height() == height

        def capture(widget, name):
            app.processEvents()
            assert widget.grab().save(str(folder / (name + ".png")))
            screens.append(name)

        capture(window, "01_cochera")
        sidebar = window._presentacion.sidebar_scroll
        for button in window._presentacion.sidebar.findChildren(QPushButton):
            if not button.isVisible():
                continue
            sidebar.ensureWidgetVisible(button)
            app.processEvents()
            assert button.width() >= button.fontMetrics().horizontalAdvance(button.text()) + 40, button.text()
        capture(window, "02_sidebar_bottom")
        sidebar.verticalScrollBar().setValue(0)
        window.ui.stack.setCurrentIndex(1)
        app.processEvents()
        capture(window, "03_estacionamiento")
        with closing(database.get_connection()) as conn:
            client = conn.execute("SELECT min(id_cliente) FROM clientes").fetchone()[0] or 0
            contract = conn.execute("SELECT min(id_contrato) FROM cochera_contratos").fetchone()[0] or 0
        constructors = [
            ("login", lambda: main.LoginDialog()),
            ("primer_usuario", lambda: main.FirstUserDialog()),
            ("clientes", lambda: main.ClientesDialog(window, rol="DUENO")),
            ("contratos", lambda: main.ContratosDialog(window, rol="DUENO")),
            ("reportes", lambda: main.ReportesDialog(window)),
            ("mapa", lambda: main.MapaCocheraDialog(window)),
            ("configuracion", lambda: main.ConfiguracionDialog(window, rol="DUENO")),
            ("caja", lambda: main.CajaDiariaDialog(window)),
            ("historial", lambda: main.HistorialDialog(window)),
            ("historial_contratos", lambda: main.HistorialContratosDialog(window)),
            ("historial_pagos", lambda: main.HistorialPagosContratoDialog(contract, window)),
            ("tarifas", lambda: main.TarifaDialog(window)),
            ("usuarios", lambda: main.UsuariosDialog(window, usuario_actual="qa")),
            ("backups", lambda: main.BackupsDialog(window)),
            ("vencimientos", lambda: main.VencimientosDialog(window)),
            ("estado_cuenta", lambda: main.EstadoCuentaDialog(client, window)),
            ("modo_sencillo", lambda: main.ModoSencilloEstacionamientoDialog(window)),
            ("ingreso_rapido", lambda: main.IngresoRapidoEstDialog([("Auto", "AUTO"), ("Moto", "MOTO"), ("Camioneta", "CAMIONETA")], window)),
            ("vuelto", lambda: main.CalcularVueltoDialog(1500, window)),
            ("pago_activacion", lambda: main.PagoActivacionDialog(48000, window)),
            ("pago_cochera", lambda: main.PagoCocheraDialog(48000, window)),
            ("transferencia", lambda: main.DatosTransferenciaDialog(window)),
            ("colores", lambda: main.ColoresMapaDialog(QColor("#3C50C8"), QColor("#B43232"), QColor("#FFFFFF"), window)),
            ("activos", lambda: main.ActivosEstacionamientoDialog(window._activos_est_cache, parent=window)),
        ]
        dialogs = []
        for name, constructor in constructors:
            dialog = constructor()
            dialogs.append(dialog)
            dialog.show()
            app.processEvents()
            if name not in {"login", "primer_usuario"}:
                dialog.setMinimumSize(0, 0)
                dialog.resize(width - 40, height - 60)
            else:
                dialog.setMinimumHeight(0)
                dialog.resize(dialog.width(), min(dialog.height(), height - 60))
            app.processEvents()
            scroll = dialog._presentation_scroll
            assert dialog.width() <= width and dialog.height() <= height, name
            titles = [label for label in dialog.findChildren(QLabel) if label.property("role") == "title"]
            assert len(titles) <= 1, (name, "duplicate header")
            for field in dialog.findChildren(QAbstractSpinBox) + dialog.findChildren(QComboBox):
                if field.isVisibleTo(dialog):
                    assert field.height() >= field.fontMetrics().height() + 12, (name, field.objectName(), field.height())
            for table in dialog.findChildren(QTableWidget):
                controller = getattr(table, "_presentation_columns", None)
                if controller:
                    assert table.columnWidth(controller.column) >= 150, (name, "unreadable text column")
            for button in dialog.findChildren(QPushButton):
                if not button.isVisibleTo(dialog):
                    continue
                scroll.ensureWidgetVisible(button)
                app.processEvents()
                center = button.mapTo(scroll.viewport(), button.rect().center())
                parent = button.parentWidget()
                in_table = False
                while parent and parent is not dialog:
                    if isinstance(parent, QTableWidget):
                        in_table = True
                        break
                    parent = parent.parentWidget()
                if not in_table:
                    assert scroll.viewport().rect().contains(center), (name, button.text(), "unreachable")
            scroll.horizontalScrollBar().setValue(0)
            scroll.verticalScrollBar().setValue(0)
            capture(dialog, name)
            if scroll.verticalScrollBar().maximum() > 0:
                scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                capture(dialog, name + "_bottom")
            if name == "configuracion":
                for index in range(dialog.tabs.count()):
                    dialog.tabs.setCurrentIndex(index)
                    capture(dialog, f"configuracion_tab_{index}")
            if name in {"clientes", "contratos", "reportes"}:
                dialog.input_buscar.setText("sin-coincidencias-qa")
                app.processEvents()
                capture(dialog, name + "_sin_resultados")
            if name in {"reportes", "caja"}:
                service = ("svc_consultar_detalle_reportes_rango" if name == "reportes"
                           else "svc_consultar_totales_caja")
                with patch.object(main, service, side_effect=sqlite3.OperationalError("Fallo de lectura simulado en QA")):
                    assert dialog._cargar() is False
                    app.processEvents()
                    if name == "reportes":
                        labels = (dialog.label_cochera_value, dialog.label_est_value, dialog.label_total_value)
                        assert not dialog.btn_export_excel.isEnabled()
                        assert not dialog.btn_eliminar.isEnabled()
                        error_table = dialog.table_historial
                    else:
                        labels = (dialog.label_cochera, dialog.label_est, dialog.label_total,
                                  dialog.label_total_real, dialog.label_diferencia)
                        assert not dialog.btn_guardar_cierre.isEnabled()
                        assert not dialog.btn_reabrir_cierre.isEnabled()
                        assert not dialog.btn_limpiar_cierre.isEnabled()
                        error_table = dialog.table_metodos
                    assert all(label.text() == "No disponible" for label in labels)
                    assert error_table.rowCount() == 1
                    assert "No se pudieron leer" in error_table.item(0, 0).text()
                    assert error_table.columnSpan(0, 0) == error_table.columnCount()
                    assert all(error_table.cellWidget(0, column) is None
                               for column in range(error_table.columnCount())), (name, "stale value widget overlays error state")
                    scroll.horizontalScrollBar().setValue(0)
                    scroll.verticalScrollBar().setValue(0)
                    capture(dialog, name + "_no_disponible")
                    if scroll.verticalScrollBar().maximum() > 0:
                        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                        capture(dialog, name + "_no_disponible_bottom")
                assert dialog._cargar() is True, (name, "reading must recover after QA exception")
                assert all(label.text() != "No disponible" for label in labels)
            dialog.hide()
        assert contrast(palette(True)["text"], palette(True)["surface"]) > 7
        for surface in ("bg", "surface", "raised", "soft"):
            assert contrast(palette(True)["muted"], palette(True)[surface]) >= 4.5
        for tone in ("accent", "success", "warning", "danger"):
            colors = palette(True)
            assert contrast(colors[tone + "_text"], colors["bg"]) >= 4.5
            assert contrast(colors[tone + "_text"], colors["soft" if tone == "accent" else tone + "_soft"]) >= 4.5
        assert contrast(palette(True)["map_free_fg"], palette(True)["map_free_bg"]) >= 4.5
        for light in (True, False):
            colors = palette(light)
            for token in ("accent", "accent_hover", "success_button", "success_hover",
                          "danger_button", "danger_hover", "warning_button", "warning_hover",
                          "sidebar_selected", "sidebar_selected_hover"):
                assert contrast(colors["on_accent"], colors[token]) >= 4.5, (light, token)
        window.hide()
        result = {"case": case, "status": "passed", "width": width, "height": height,
                  "font": font_size, "dpi": app.devicePixelRatio(), "screens": screens,
                  "notice_types": messages, "database_isolated": True,
                  "controls_reachable": True, "unavailable_states_verified": ["reportes", "caja"]}
        (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if session:
            session.cleanup()


if __name__ == "__main__":
    run()
