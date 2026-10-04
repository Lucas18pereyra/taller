"""Seleccion real con clics, sin guardar ni tocar la base del usuario."""
from contextlib import closing
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
    from PySide6.QtWidgets import QApplication
    from main import MapaCocheraDialog, EspacioItem
    from presentacion_estilos import apply_application_theme

    original = Path(database.DB_PATH)
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    app = QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    output = ROOT / "preview_visual" / "seleccion_mapa"
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="seleccion_mapa_qa_") as temp:
        database.DB_PATH = Path(temp) / "estacionamiento.db"
        database.init_db()
        with closing(database.get_connection()) as conn:
            for col, letra in enumerate("ABC"):
                for fila in range(5):
                    codigo = f"{letra}{fila + 1}"
                    conn.execute("INSERT INTO espacios (codigo) VALUES (?)", (codigo,))
                    conn.execute("INSERT INTO espacios_mapa VALUES (?,?,?,?,?)", (codigo, col * 160, fila * 50, 80, 50))
            conn.commit()
        for editable in (True, False):
            apply_application_theme(app, light=True)
            dialog = MapaCocheraDialog(editable=editable)
            dialog.resize(1000, 700)
            dialog.show()
            dialog.view.resetTransform()
            dialog.view.centerOn(200, 125)
            app.processEvents()
            items = {it.codigo: it for it in dialog.scene.items() if isinstance(it, EspacioItem)}
            for codigo in ("A1", "B2", "C3"):
                item = items[codigo]
                fill = item.brush().color().name()
                geometry = item.rect(), item.pos(), item.boundingRect()
                dialog.view.ensureVisible(item)
                punto = dialog.view.mapFromScene(item.mapToScene(item.rect().center()))
                QTest.mouseClick(dialog.view.viewport(), Qt.LeftButton, pos=punto)
                app.processEvents()
                assert item.isSelected(), codigo
                assert {it.codigo for it in dialog.scene.selectedItems() if isinstance(it, EspacioItem)} == {codigo}
                assert item.brush().color().name() == fill
                assert geometry == (item.rect(), item.pos(), item.boundingRect())
                assert not dialog._mapa_tiene_cambios(), "Seleccionar no debe marcar cambios de mapa"
                dialog.grab().save(str(output / f"{'edicion' if editable else 'lectura'}_{codigo}.png"))
            dialog.scene.clearSelection()
            assert not any(it.isSelected() for it in items.values())
            dialog.close()
        database.DB_PATH = original
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    print("PASS: seleccion y cambio con clic, solo lectura/edicion, sin cambiar colores/geometria/datos.")


if __name__ == "__main__":
    run()
