"""El borde de seleccion se distingue sin cambiar el color de ocupacion."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene
from main import EspacioItem


class SeleccionVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def render(self, scene):
        image = QImage(100, 70, QImage.Format_ARGB32)
        image.fill(QColor("#FFFFFF"))
        painter = QPainter(image)
        scene.render(painter, QRectF(0, 0, 100, 70), QRectF(-10, -10, 100, 70))
        painter.end()
        return image

    def test_borde_oscuro_al_seleccionar_y_desaparece_al_desmarcar(self):
        for color in ("#FFFFFF", "#3B4CC0", "#BA3832"):
            with self.subTest(color=color):
                scene = QGraphicsScene()
                item = EspacioItem("A1", QRectF(0, 0, 80, 50), QColor(color))
                scene.addItem(item)
                normal = self.render(scene)
                item.setSelected(True)
                selected = self.render(scene)
                self.assertEqual(selected.pixelColor(14, 25).name(), "#0b1b30")
                self.assertNotEqual(normal.pixelColor(14, 25), selected.pixelColor(14, 25))
                self.assertEqual(normal.pixelColor(30, 50), selected.pixelColor(30, 50))
                self.assertEqual(item.brush().color().name(), color.lower())
                item.setSelected(False)
                self.assertEqual(normal, self.render(scene))


if __name__ == "__main__":
    unittest.main()
