import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QDoubleSpinBox
from main import _configurar_spinbox_numerico, _instalar_formato_dni


class FormatoNumerosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dni_mientras_escribe_y_borra(self):
        edit = QLineEdit()
        edit.setMaxLength(10)
        _instalar_formato_dni(edit)
        QTest.keyClicks(edit, "12345678")
        self.assertEqual(edit.text(), "12.345.678")
        QTest.keyClick(edit, Qt.Key_Backspace)
        self.assertEqual(edit.text(), "1.234.567")
        edit.selectAll()
        QTest.keyClicks(edit, "9876543")
        self.assertEqual(edit.text(), "9.876.543")

    def test_importe_con_decimales_y_valor_real(self):
        spin = QDoubleSpinBox()
        spin.setRange(0, 9999999)
        spin.setDecimals(2)
        _configurar_spinbox_numerico(spin)
        edit = spin.lineEdit()
        edit.selectAll()
        QTest.keyClicks(edit, "123456,75")
        self.assertEqual(edit.text(), "123.456,75")
        spin.interpretText()
        self.assertEqual(spin.value(), 123456.75)
        _configurar_spinbox_numerico(spin)
        edit.selectAll()
        QTest.keyClicks(edit, "1000")
        self.assertEqual(edit.text(), "1.000")
        spin.interpretText()
        self.assertEqual(spin.value(), 1000)

    def test_cursor_al_insertar_en_medio_del_dni(self):
        edit = QLineEdit("1.234.567")
        _instalar_formato_dni(edit)
        edit.setCursorPosition(3)
        QTest.keyClicks(edit, "9")
        self.assertEqual(edit.text(), "12.934.567")
        self.assertEqual(edit.cursorPosition(), 4)
