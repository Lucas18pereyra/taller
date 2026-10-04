import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton
from main import ContratosDialog, MapaCocheraDialog, EspacioItem
from presentacion import AvailabilityMap


class MapaContratosUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "test.db"
        database.init_db()
        conn = database.get_connection()
        for code, reserved in (("A1", 1), ("A2", 1), ("C1", 0)):
            conn.execute("INSERT INTO espacios(codigo,es_reservado) VALUES (?,?)", (code, reserved))
            conn.execute("INSERT INTO espacios_mapa VALUES (?,?,?,?,?)", (code, len(code)*80, 0, 80, 50))
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_PATH = self.original
        self.temp.cleanup()

    def test_mapa_no_reordena_ni_limita_a_32(self):
        widget = AvailabilityMap(lambda: None)
        rows = [dict(code=str(i), x=i*100, y=(i%3)*100, w=80, h=50,
                     color="#ffffff", state="LIBRE", occupied=False) for i in range(40)]
        widget.set_rows(rows)
        widget.resize(1000, 400)
        widget.grab()
        self.assertEqual(len(widget._cells), 40)
        first, second = widget._cells[0][0], widget._cells[1][0]
        self.assertAlmostEqual(second.x()-first.x(), second.y()-first.y())
        self.assertAlmostEqual(first.width()/first.height(), 80/50)

    def test_codigo_vacio_y_monto_personalizado(self):
        dialog = ContratosDialog(rol="DUENO")
        dialog.input_espacio.clear()
        dialog._sugerir_espacio_libre()
        self.assertEqual(dialog.input_espacio.text(), "A1")
        dialog.input_monto.setValue(125000)
        self.assertEqual(dialog._snapshot_form()["monto"], 125000)
        self.assertFalse(dialog.input_monto.isReadOnly())

    def _choose(self, owner, code):
        def act():
            dialog = next(w for w in self.app.topLevelWidgets()
                          if isinstance(w, MapaCocheraDialog) and w.isVisible())
            item = next(i for i in dialog.scene.items() if isinstance(i, EspacioItem) and i.codigo == code)
            item.setSelected(True)
            button = next(b for b in dialog.findChildren(QPushButton)
                          if b.text() == "Elegir espacio seleccionado")
            button.click()
            if dialog.isVisible():
                dialog.reject()
        QTimer.singleShot(0, act)
        owner._elegir_espacio_mapa()

    def test_selector_elige_cochera_y_rechaza_estacionamiento(self):
        owner = ContratosDialog(rol="DUENO")
        self._choose(owner, "A2")
        self.assertEqual(owner.input_espacio.text(), "A2")
        conn = database.get_connection()
        client = conn.execute("INSERT INTO clientes(nombre,dni) VALUES ('Prueba','12345678')").lastrowid
        conn.execute("UPDATE espacios SET id_cliente=? WHERE codigo='A1'", (client,))
        conn.commit()
        conn.close()
        with patch("main.QMessageBox.warning") as warning:
            self._choose(owner, "A1")
            warning.assert_called_once()
        self.assertEqual(owner.input_espacio.text(), "A2")
        owner.input_espacio.clear()
        owner._sugerir_espacio_libre()
        self.assertEqual(owner.input_espacio.text(), "A2")
        with patch("main.QMessageBox.warning") as warning:
            self._choose(owner, "C1")
            warning.assert_called_once()
        self.assertEqual(owner.input_espacio.text(), "A2")


if __name__ == "__main__":
    unittest.main()
