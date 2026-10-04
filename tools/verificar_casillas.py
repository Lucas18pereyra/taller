"""Prueba casillas reales de Configuracion sin guardar ni tocar datos reales."""
import hashlib
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def run():
    import database
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionButton
    from main import ConfiguracionDialog
    from presentacion import prepare_dialog
    from presentacion_estilos import apply_application_theme

    original = Path(database.DB_PATH)
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    app = QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    output = ROOT / "preview_visual" / "casillas_vehiculos"
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="casillas_qa_") as temp:
        database.DB_PATH = Path(temp) / "estacionamiento.db"
        database.init_db()
        for light in (True, False):
            apply_application_theme(app, light=light)
            app._presentation_light = light
            dialog = ConfiguracionDialog()
            dialog.tabs.setCurrentIndex(3)
            prepare_dialog(dialog)
            dialog.resize(1200, 700)
            dialog.show()
            app.processEvents()
            controles = [getattr(dialog, f"check_{grupo}_{tipo}")
                         for grupo in ("coch", "est") for tipo in ("auto", "moto", "camioneta")]
            for checkbox in controles:
                checkbox.setChecked(False)
                opt = QStyleOptionButton()
                checkbox.initStyleOption(opt)
                rect = checkbox.style().subElementRect(QStyle.SE_CheckBoxIndicator, opt, checkbox)
                assert rect.width() >= 20 and rect.height() >= 20
                QTest.mouseClick(checkbox, Qt.LeftButton, pos=rect.center())
                assert checkbox.isChecked(), "El cuadrado debe activar la opcion"
                QTest.mouseClick(checkbox, Qt.LeftButton, pos=rect.center())
                assert not checkbox.isChecked(), "El cuadrado debe desactivar la opcion"
            # Mostrar simultaneamente cuadrados vacios y marcados.
            for checkbox in controles[::2]:
                checkbox.setChecked(True)
            app.processEvents()
            dialog.grab().save(str(output / ("casillas_claro.png" if light else "casillas_oscuro.png")))
            dialog._actualizar_snapshot()
            dialog.close()
        database.DB_PATH = original
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    print("PASS: seis casillas, clic en cuadrado activa/desactiva, claro/oscuro, base real intacta.")


if __name__ == "__main__":
    run()
