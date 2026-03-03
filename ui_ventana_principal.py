# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ventana_principal.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMenuBar,
    QPushButton, QSizePolicy, QSpacerItem, QStackedWidget,
    QStatusBar, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1280, 720)
        MainWindow.setMinimumSize(QSize(1280, 720))
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.modeButtonsLayout = QHBoxLayout()
        self.modeButtonsLayout.setObjectName(u"modeButtonsLayout")
        self.btn_cochera = QPushButton(self.centralwidget)
        self.btn_cochera.setObjectName(u"btn_cochera")

        self.modeButtonsLayout.addWidget(self.btn_cochera)

        self.btn_estacionamiento = QPushButton(self.centralwidget)
        self.btn_estacionamiento.setObjectName(u"btn_estacionamiento")

        self.modeButtonsLayout.addWidget(self.btn_estacionamiento)


        self.verticalLayout.addLayout(self.modeButtonsLayout)

        self.stack = QStackedWidget(self.centralwidget)
        self.stack.setObjectName(u"stack")
        self.page_cochera = QWidget()
        self.page_cochera.setObjectName(u"page_cochera")
        self.cocheraLayout = QVBoxLayout(self.page_cochera)
        self.cocheraLayout.setSpacing(6)
        self.cocheraLayout.setObjectName(u"cocheraLayout")
        self.cocheraLayout.setContentsMargins(0, 0, 0, 0)
        self.fechaHoraLayout = QHBoxLayout()
        self.fechaHoraLayout.setObjectName(u"fechaHoraLayout")
        self.fechaHoraLayout.setAlignment(Qt.AlignLeft)
        self.fechaHoraLayout.setContentsMargins(0, 0, 0, 0)
        self.fechaLayout = QVBoxLayout()
        self.fechaLayout.setObjectName(u"fechaLayout")
        self.label_fecha_num = QLabel(self.page_cochera)
        self.label_fecha_num.setObjectName(u"label_fecha_num")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.label_fecha_num.setFont(font)

        self.fechaLayout.addWidget(self.label_fecha_num)


        self.fechaHoraLayout.addLayout(self.fechaLayout)

        self.label_hora_value = QLabel(self.page_cochera)
        self.label_hora_value.setObjectName(u"label_hora_value")
        self.label_hora_value.setFont(font)

        self.fechaHoraLayout.addWidget(self.label_hora_value)


        self.cocheraLayout.addLayout(self.fechaHoraLayout)

        self.label_cochera_title = QLabel(self.page_cochera)
        self.label_cochera_title.setObjectName(u"label_cochera_title")
        self.label_cochera_title.setFont(font)
        self.label_cochera_title.setAlignment(Qt.AlignCenter)

        self.cocheraLayout.addWidget(self.label_cochera_title)

        self.group_cochera_acciones = QGroupBox(self.page_cochera)
        self.group_cochera_acciones.setObjectName(u"group_cochera_acciones")
        self.accionesCocheraLayout = QHBoxLayout(self.group_cochera_acciones)
        self.accionesCocheraLayout.setObjectName(u"accionesCocheraLayout")
        self.btn_mapa_cocheras = QPushButton(self.group_cochera_acciones)
        self.btn_mapa_cocheras.setObjectName(u"btn_mapa_cocheras")

        self.accionesCocheraLayout.addWidget(self.btn_mapa_cocheras)

        self.btn_clientes = QPushButton(self.group_cochera_acciones)
        self.btn_clientes.setObjectName(u"btn_clientes")

        self.accionesCocheraLayout.addWidget(self.btn_clientes)

        self.btn_contratos = QPushButton(self.group_cochera_acciones)
        self.btn_contratos.setObjectName(u"btn_contratos")

        self.accionesCocheraLayout.addWidget(self.btn_contratos)

        self.btn_reportes = QPushButton(self.group_cochera_acciones)
        self.btn_reportes.setObjectName(u"btn_reportes")

        self.accionesCocheraLayout.addWidget(self.btn_reportes)

        self.btn_vencimientos = QPushButton(self.group_cochera_acciones)
        self.btn_vencimientos.setObjectName(u"btn_vencimientos")

        self.accionesCocheraLayout.addWidget(self.btn_vencimientos)

        self.accionesCocheraSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.accionesCocheraLayout.addItem(self.accionesCocheraSpacer)


        self.cocheraLayout.addWidget(self.group_cochera_acciones)

        self.group_cochera_resumen = QGroupBox(self.page_cochera)
        self.group_cochera_resumen.setObjectName(u"group_cochera_resumen")
        self.cochera_resumen_layout = QVBoxLayout(self.group_cochera_resumen)
        self.cochera_resumen_layout.setObjectName(u"cochera_resumen_layout")
        self.kpiGrid = QGridLayout()
        self.kpiGrid.setObjectName(u"kpiGrid")
        self.card_total = QFrame(self.group_cochera_resumen)
        self.card_total.setObjectName(u"card_total")
        self.card_total.setFrameShape(QFrame.StyledPanel)
        self.cardTotalLayout = QVBoxLayout(self.card_total)
        self.cardTotalLayout.setObjectName(u"cardTotalLayout")
        self.label_total_title = QLabel(self.card_total)
        self.label_total_title.setObjectName(u"label_total_title")
        self.label_total_title.setAlignment(Qt.AlignCenter)

        self.cardTotalLayout.addWidget(self.label_total_title)

        self.label_total_value = QLabel(self.card_total)
        self.label_total_value.setObjectName(u"label_total_value")
        font1 = QFont()
        font1.setPointSize(16)
        font1.setBold(True)
        self.label_total_value.setFont(font1)
        self.label_total_value.setAlignment(Qt.AlignCenter)

        self.cardTotalLayout.addWidget(self.label_total_value)


        self.kpiGrid.addWidget(self.card_total, 0, 0, 1, 1)

        self.card_ocupadas = QFrame(self.group_cochera_resumen)
        self.card_ocupadas.setObjectName(u"card_ocupadas")
        self.card_ocupadas.setFrameShape(QFrame.StyledPanel)
        self.cardOcupadasLayout = QVBoxLayout(self.card_ocupadas)
        self.cardOcupadasLayout.setObjectName(u"cardOcupadasLayout")
        self.label_ocupadas_title = QLabel(self.card_ocupadas)
        self.label_ocupadas_title.setObjectName(u"label_ocupadas_title")
        self.label_ocupadas_title.setAlignment(Qt.AlignCenter)

        self.cardOcupadasLayout.addWidget(self.label_ocupadas_title)

        self.label_ocupadas_value = QLabel(self.card_ocupadas)
        self.label_ocupadas_value.setObjectName(u"label_ocupadas_value")
        self.label_ocupadas_value.setFont(font1)
        self.label_ocupadas_value.setAlignment(Qt.AlignCenter)

        self.cardOcupadasLayout.addWidget(self.label_ocupadas_value)


        self.kpiGrid.addWidget(self.card_ocupadas, 0, 1, 1, 1)

        self.card_libres = QFrame(self.group_cochera_resumen)
        self.card_libres.setObjectName(u"card_libres")
        self.card_libres.setFrameShape(QFrame.StyledPanel)
        self.cardLibresLayout = QVBoxLayout(self.card_libres)
        self.cardLibresLayout.setObjectName(u"cardLibresLayout")
        self.label_libres_title = QLabel(self.card_libres)
        self.label_libres_title.setObjectName(u"label_libres_title")
        self.label_libres_title.setAlignment(Qt.AlignCenter)

        self.cardLibresLayout.addWidget(self.label_libres_title)

        self.label_libres_value = QLabel(self.card_libres)
        self.label_libres_value.setObjectName(u"label_libres_value")
        self.label_libres_value.setFont(font1)
        self.label_libres_value.setAlignment(Qt.AlignCenter)

        self.cardLibresLayout.addWidget(self.label_libres_value)


        self.kpiGrid.addWidget(self.card_libres, 0, 2, 1, 1)

        self.card_ingresos = QFrame(self.group_cochera_resumen)
        self.card_ingresos.setObjectName(u"card_ingresos")
        self.card_ingresos.setFrameShape(QFrame.StyledPanel)
        self.cardIngresosLayout = QVBoxLayout(self.card_ingresos)
        self.cardIngresosLayout.setObjectName(u"cardIngresosLayout")
        self.label_ingresos_title = QLabel(self.card_ingresos)
        self.label_ingresos_title.setObjectName(u"label_ingresos_title")
        self.label_ingresos_title.setAlignment(Qt.AlignCenter)

        self.cardIngresosLayout.addWidget(self.label_ingresos_title)

        self.label_ingresos_value = QLabel(self.card_ingresos)
        self.label_ingresos_value.setObjectName(u"label_ingresos_value")
        self.label_ingresos_value.setFont(font1)
        self.label_ingresos_value.setAlignment(Qt.AlignCenter)

        self.cardIngresosLayout.addWidget(self.label_ingresos_value)


        self.kpiGrid.addWidget(self.card_ingresos, 1, 1, 1, 1)

        self.card_mensual = QFrame(self.group_cochera_resumen)
        self.card_mensual.setObjectName(u"card_mensual")
        self.card_mensual.setFrameShape(QFrame.StyledPanel)
        self.cardMensualLayout = QVBoxLayout(self.card_mensual)
        self.cardMensualLayout.setObjectName(u"cardMensualLayout")
        self.label_mensual_title = QLabel(self.card_mensual)
        self.label_mensual_title.setObjectName(u"label_mensual_title")
        self.label_mensual_title.setAlignment(Qt.AlignCenter)

        self.cardMensualLayout.addWidget(self.label_mensual_title)

        self.label_mensual_value = QLabel(self.card_mensual)
        self.label_mensual_value.setObjectName(u"label_mensual_value")
        self.label_mensual_value.setFont(font1)
        self.label_mensual_value.setAlignment(Qt.AlignCenter)

        self.cardMensualLayout.addWidget(self.label_mensual_value)


        self.kpiGrid.addWidget(self.card_mensual, 1, 0, 1, 1)


        self.cochera_resumen_layout.addLayout(self.kpiGrid)


        self.cocheraLayout.addWidget(self.group_cochera_resumen)

        self.stack.addWidget(self.page_cochera)
        self.page_estacionamiento = QWidget()
        self.page_estacionamiento.setObjectName(u"page_estacionamiento")
        self.estacionamientoLayout = QVBoxLayout(self.page_estacionamiento)
        self.estacionamientoLayout.setObjectName(u"estacionamientoLayout")
        self.estFechaHoraLayout = QHBoxLayout()
        self.estFechaHoraLayout.setObjectName(u"estFechaHoraLayout")
        self.estFechaHoraLayout.setAlignment(Qt.AlignLeft)
        self.estFechaHoraLayout.setContentsMargins(0, 0, 0, 0)
        self.estFechaLayout = QVBoxLayout()
        self.estFechaLayout.setObjectName(u"estFechaLayout")
        self.label_est_fecha_num = QLabel(self.page_estacionamiento)
        self.label_est_fecha_num.setObjectName(u"label_est_fecha_num")
        self.label_est_fecha_num.setFont(font)

        self.estFechaLayout.addWidget(self.label_est_fecha_num)


        self.estFechaHoraLayout.addLayout(self.estFechaLayout)

        self.label_est_hora_top_value = QLabel(self.page_estacionamiento)
        self.label_est_hora_top_value.setObjectName(u"label_est_hora_top_value")
        self.label_est_hora_top_value.setFont(font)

        self.estFechaHoraLayout.addWidget(self.label_est_hora_top_value)


        self.estacionamientoLayout.addLayout(self.estFechaHoraLayout)

        self.label_estacionamiento = QLabel(self.page_estacionamiento)
        self.label_estacionamiento.setObjectName(u"label_estacionamiento")
        self.label_estacionamiento.setFont(font)
        self.label_estacionamiento.setAlignment(Qt.AlignCenter)

        self.estacionamientoLayout.addWidget(self.label_estacionamiento)

        self.group_est_acciones = QGroupBox(self.page_estacionamiento)
        self.group_est_acciones.setObjectName(u"group_est_acciones")
        self.estAccionesLayout = QHBoxLayout(self.group_est_acciones)
        self.estAccionesLayout.setObjectName(u"estAccionesLayout")
        self.btn_mapa_est = QPushButton(self.group_est_acciones)
        self.btn_mapa_est.setObjectName(u"btn_mapa_est")

        self.estAccionesLayout.addWidget(self.btn_mapa_est)

        self.estAccionesSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.estAccionesLayout.addItem(self.estAccionesSpacer)


        self.estacionamientoLayout.addWidget(self.group_est_acciones)

        self.est_kpi_layout = QVBoxLayout()
        self.est_kpi_layout.setObjectName(u"est_kpi_layout")
        self.card_est_hora = QFrame(self.page_estacionamiento)
        self.card_est_hora.setObjectName(u"card_est_hora")
        self.card_est_hora.setFrameShape(QFrame.StyledPanel)
        self.cardEstHoraLayout = QVBoxLayout(self.card_est_hora)
        self.cardEstHoraLayout.setObjectName(u"cardEstHoraLayout")
        self.label_est_hora_title = QLabel(self.card_est_hora)
        self.label_est_hora_title.setObjectName(u"label_est_hora_title")
        self.label_est_hora_title.setAlignment(Qt.AlignCenter)

        self.cardEstHoraLayout.addWidget(self.label_est_hora_title)

        self.label_est_hora_value = QLabel(self.card_est_hora)
        self.label_est_hora_value.setObjectName(u"label_est_hora_value")
        self.label_est_hora_value.setFont(font1)
        self.label_est_hora_value.setAlignment(Qt.AlignCenter)

        self.cardEstHoraLayout.addWidget(self.label_est_hora_value)


        self.est_kpi_layout.addWidget(self.card_est_hora)

        self.card_est_tarifa = QFrame(self.page_estacionamiento)
        self.card_est_tarifa.setObjectName(u"card_est_tarifa")
        self.card_est_tarifa.setFrameShape(QFrame.StyledPanel)
        self.cardEstTarifaLayout = QVBoxLayout(self.card_est_tarifa)
        self.cardEstTarifaLayout.setObjectName(u"cardEstTarifaLayout")
        self.label_est_tarifa_title = QLabel(self.card_est_tarifa)
        self.label_est_tarifa_title.setObjectName(u"label_est_tarifa_title")
        self.label_est_tarifa_title.setAlignment(Qt.AlignCenter)

        self.cardEstTarifaLayout.addWidget(self.label_est_tarifa_title)

        self.label_est_tarifa_value = QLabel(self.card_est_tarifa)
        self.label_est_tarifa_value.setObjectName(u"label_est_tarifa_value")
        self.label_est_tarifa_value.setFont(font1)
        self.label_est_tarifa_value.setAlignment(Qt.AlignCenter)

        self.cardEstTarifaLayout.addWidget(self.label_est_tarifa_value)


        self.est_kpi_layout.addWidget(self.card_est_tarifa)


        self.estacionamientoLayout.addLayout(self.est_kpi_layout)

        self.group_est_registro = QGroupBox(self.page_estacionamiento)
        self.group_est_registro.setObjectName(u"group_est_registro")
        self.est_registro_layout = QVBoxLayout(self.group_est_registro)
        self.est_registro_layout.setObjectName(u"est_registro_layout")
        self.est_form_layout = QFormLayout()
        self.est_form_layout.setObjectName(u"est_form_layout")
        self.label_est_patente = QLabel(self.group_est_registro)
        self.label_est_patente.setObjectName(u"label_est_patente")

        self.est_form_layout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_est_patente)

        self.input_patente_est = QLineEdit(self.group_est_registro)
        self.input_patente_est.setObjectName(u"input_patente_est")

        self.est_form_layout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.input_patente_est)

        self.label_est_espacio = QLabel(self.group_est_registro)
        self.label_est_espacio.setObjectName(u"label_est_espacio")

        self.est_form_layout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_est_espacio)

        self.input_espacio_est = QLineEdit(self.group_est_registro)
        self.input_espacio_est.setObjectName(u"input_espacio_est")

        self.est_form_layout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.input_espacio_est)

        self.label_est_metodo = QLabel(self.group_est_registro)
        self.label_est_metodo.setObjectName(u"label_est_metodo")

        self.est_form_layout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.label_est_metodo)

        self.combo_metodo_est = QComboBox(self.group_est_registro)
        self.combo_metodo_est.addItem("")
        self.combo_metodo_est.addItem("")
        self.combo_metodo_est.addItem("")
        self.combo_metodo_est.setObjectName(u"combo_metodo_est")

        self.est_form_layout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.combo_metodo_est)


        self.est_registro_layout.addLayout(self.est_form_layout)

        self.est_buttons_layout = QHBoxLayout()
        self.est_buttons_layout.setObjectName(u"est_buttons_layout")
        self.btn_ingreso_est = QPushButton(self.group_est_registro)
        self.btn_ingreso_est.setObjectName(u"btn_ingreso_est")

        self.est_buttons_layout.addWidget(self.btn_ingreso_est)

        self.btn_salida_est = QPushButton(self.group_est_registro)
        self.btn_salida_est.setObjectName(u"btn_salida_est")

        self.est_buttons_layout.addWidget(self.btn_salida_est)


        self.est_registro_layout.addLayout(self.est_buttons_layout)

        self.label_resultado_est = QLabel(self.group_est_registro)
        self.label_resultado_est.setObjectName(u"label_resultado_est")

        self.est_registro_layout.addWidget(self.label_resultado_est)


        self.estacionamientoLayout.addWidget(self.group_est_registro)

        self.group_est_activos = QGroupBox(self.page_estacionamiento)
        self.group_est_activos.setObjectName(u"group_est_activos")
        self.est_activos_layout = QVBoxLayout(self.group_est_activos)
        self.est_activos_layout.setObjectName(u"est_activos_layout")
        self.table_est_activos = QTableWidget(self.group_est_activos)
        if (self.table_est_activos.columnCount() < 3):
            self.table_est_activos.setColumnCount(3)
        __qtablewidgetitem = QTableWidgetItem()
        self.table_est_activos.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.table_est_activos.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.table_est_activos.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        self.table_est_activos.setObjectName(u"table_est_activos")
        self.table_est_activos.setColumnCount(3)

        self.est_activos_layout.addWidget(self.table_est_activos)


        self.estacionamientoLayout.addWidget(self.group_est_activos)

        self.stack.addWidget(self.page_estacionamiento)

        self.verticalLayout.addWidget(self.stack)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 900, 33))
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.btn_cochera.setText(QCoreApplication.translate("MainWindow", u"Cochera", None))
        self.btn_estacionamiento.setText(QCoreApplication.translate("MainWindow", u"Estacionamiento", None))
        self.label_fecha_num.setText(QCoreApplication.translate("MainWindow", u"Fecha: 07/02/2026", None))
        self.label_hora_value.setText(QCoreApplication.translate("MainWindow", u"Hora: 00:00", None))
        self.label_cochera_title.setText(QCoreApplication.translate("MainWindow", u"Interfaz Cochera", None))
        self.group_cochera_acciones.setTitle(QCoreApplication.translate("MainWindow", u"Acciones", None))
        self.btn_mapa_cocheras.setText(QCoreApplication.translate("MainWindow", u"Mapa de cocheras", None))
        self.btn_clientes.setText(QCoreApplication.translate("MainWindow", u"Clientes", None))
        self.btn_contratos.setText(QCoreApplication.translate("MainWindow", u"Contratos", None))
        self.btn_reportes.setText(QCoreApplication.translate("MainWindow", u"Reportes", None))
        self.btn_vencimientos.setText(QCoreApplication.translate("MainWindow", u"Vencimientos proximos", None))
        self.group_cochera_resumen.setTitle(QCoreApplication.translate("MainWindow", u"Resumen cochera", None))
        self.label_total_title.setText(QCoreApplication.translate("MainWindow", u"Cocheras totales", None))
        self.label_total_value.setText(QCoreApplication.translate("MainWindow", u"0", None))
        self.label_ocupadas_title.setText(QCoreApplication.translate("MainWindow", u"Cocheras ocupadas", None))
        self.label_ocupadas_value.setText(QCoreApplication.translate("MainWindow", u"0", None))
        self.label_libres_title.setText(QCoreApplication.translate("MainWindow", u"Cocheras libres", None))
        self.label_libres_value.setText(QCoreApplication.translate("MainWindow", u"0", None))
        self.label_ingresos_title.setText(QCoreApplication.translate("MainWindow", u"Ingresos del mes", None))
        self.label_ingresos_value.setText(QCoreApplication.translate("MainWindow", u"$ 0", None))
        self.label_mensual_title.setText(QCoreApplication.translate("MainWindow", u"Precio mensual cochera", None))
        self.label_mensual_value.setText(QCoreApplication.translate("MainWindow", u"$ 0.00", None))
        self.label_est_fecha_num.setText(QCoreApplication.translate("MainWindow", u"Fecha: 07/02/2026", None))
        self.label_est_hora_top_value.setText(QCoreApplication.translate("MainWindow", u"Hora: 00:00", None))
        self.label_estacionamiento.setText(QCoreApplication.translate("MainWindow", u"Interfaz de Estacionamiento", None))
        self.group_est_acciones.setTitle(QCoreApplication.translate("MainWindow", u"Acciones", None))
        self.btn_mapa_est.setText(QCoreApplication.translate("MainWindow", u"Mapa de cocheras", None))
        self.label_est_hora_title.setText(QCoreApplication.translate("MainWindow", u"Hora actual", None))
        self.label_est_hora_value.setText(QCoreApplication.translate("MainWindow", u"00:00:00", None))
        self.label_est_tarifa_title.setText(QCoreApplication.translate("MainWindow", u"Tarifa por hora", None))
        self.label_est_tarifa_value.setText(QCoreApplication.translate("MainWindow", u"$ 0.00", None))
        self.group_est_registro.setTitle(QCoreApplication.translate("MainWindow", u"Registro por hora", None))
        self.label_est_patente.setText(QCoreApplication.translate("MainWindow", u"Patente", None))
        self.label_est_espacio.setText(QCoreApplication.translate("MainWindow", u"Espacio (opcional)", None))
        self.label_est_metodo.setText(QCoreApplication.translate("MainWindow", u"Metodo pago", None))
        self.combo_metodo_est.setItemText(0, QCoreApplication.translate("MainWindow", u"Efectivo", None))
        self.combo_metodo_est.setItemText(1, QCoreApplication.translate("MainWindow", u"Tarjeta", None))
        self.combo_metodo_est.setItemText(2, QCoreApplication.translate("MainWindow", u"Transferencia", None))

        self.btn_ingreso_est.setText(QCoreApplication.translate("MainWindow", u"Registrar ingreso", None))
        self.btn_salida_est.setText(QCoreApplication.translate("MainWindow", u"Registrar salida", None))
        self.label_resultado_est.setText("")
        self.group_est_activos.setTitle(QCoreApplication.translate("MainWindow", u"Vehiculos en playa", None))
        ___qtablewidgetitem = self.table_est_activos.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("MainWindow", u"Patente", None));
        ___qtablewidgetitem1 = self.table_est_activos.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("MainWindow", u"Espacio", None));
        ___qtablewidgetitem2 = self.table_est_activos.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("MainWindow", u"Ingreso", None));
    # retranslateUi

