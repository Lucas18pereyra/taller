from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget
import sys

class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        contenedor = QWidget()
        layout = QVBoxLayout(contenedor)

        botones = QHBoxLayout()
        btn_cochera = QPushButton("Cochera")
        btn_est = QPushButton("Estacionamiento")
        botones.addWidget(btn_cochera)
        botones.addWidget(btn_est)

        stack = QStackedWidget()
        vista1 = QLabel("Interfaz de Cochera")
        vista2 = QLabel("Interfaz de Estacionamiento")

        stack.addWidget(vista1)
        stack.addWidget(vista2)

        btn_cochera.clicked.connect(lambda: stack.setCurrentIndex(0))
        btn_est.clicked.connect(lambda: stack.setCurrentIndex(1))

        layout.addLayout(botones)
        layout.addWidget(stack)

        self.setCentralWidget(contenedor)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    v = Ventana()
    v.show()
    sys.exit(app.exec())
