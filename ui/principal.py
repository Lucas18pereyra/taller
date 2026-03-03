from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QMessageBox
)
from servicios.estacionamiento import ingresar_vehiculo, salir_vehiculo


class VentanaPrincipal(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Estacionamiento / Cochera")
        self.setFixedSize(300, 200)

        self.label = QLabel("Patente")
        self.input_patente = QLineEdit()
        self.input_patente.setPlaceholderText("ABC123")

        self.btn_ingresar = QPushButton("Ingresar")
        self.btn_salir = QPushButton("Salir")

        self.btn_ingresar.clicked.connect(self.ingresar)
        self.btn_salir.clicked.connect(self.salir)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.input_patente)
        layout.addWidget(self.btn_ingresar)
        layout.addWidget(self.btn_salir)

        self.setLayout(layout)

    def ingresar(self):
        patente = self.input_patente.text().strip().upper()
        if not patente:
            QMessageBox.warning(self, "Error", "Ingrese una patente")
            return

        try:
            espacio = ingresar_vehiculo(patente)
            QMessageBox.information(
                self, "Ingreso OK",
                f"Vehículo ingresado\nEspacio asignado: {espacio}"
            )
            self.input_patente.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def salir(self):
        patente = self.input_patente.text().strip().upper()
        if not patente:
            QMessageBox.warning(self, "Error", "Ingrese una patente")
            return

        try:
            total = salir_vehiculo(patente)
            QMessageBox.information(
                self, "Salida OK",
                f"Total a pagar: ${total}"
            )
            self.input_patente.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
