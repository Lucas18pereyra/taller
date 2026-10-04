"""Presentation layer: layout, visual components and read-only dashboard views."""
import math
import sqlite3
from datetime import date

from PySide6.QtCore import QDateTime, QEvent, QObject, QPointF, QRectF, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QBoxLayout, QComboBox, QDialog, QFormLayout, QFrame, QGridLayout,
    QHeaderView, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QLayout, QTableWidget, QVBoxLayout, QWidget,
)

from database import get_connection
from presentacion_estilos import palette


def _role(widget, name, tone=None):
    widget.setProperty("role", name)
    if tone:
        widget.setProperty("tone", tone)
    return widget


def _label(text, role="subtitle", parent=None):
    return _role(QLabel(text, parent), role)


def _refresh(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _detach_layout_item(layout, index):
    # Keep Qt's removed layout-item wrappers alive until their container dies.
    # PySide can otherwise recycle a wrapper address while widgets are reparented.
    item = layout.takeAt(index)
    if item is not None:
        retained = getattr(layout, "_presentation_detached_items", None)
        if retained is None:
            retained = layout._presentation_detached_items = []
        retained.append(item)
    return item


def _clear_layout(layout):
    # Keep the widgets and their original signal connections; only move them.
    while layout.count():
        _detach_layout_item(layout, 0)


def line_icon(name, color=None, size=22):
    """Small native vector-like icons, with no file or network dependency."""
    if color is None:
        light = getattr(QApplication.instance(), "_presentation_light", True)
        color = palette(light)["muted"]
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size * 2 / 24, size * 2 / 24)
    painter.setPen(QPen(QColor(color), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    line = lambda x1, y1, x2, y2: painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    rect = lambda x, y, w, h, r=2: painter.drawRoundedRect(QRectF(x, y, w, h), r, r)
    if name in {"car", "parking"}:
        rect(3, 9, 18, 9)
        line(5, 9, 7, 4); line(7, 4, 17, 4); line(17, 4, 19, 9)
        line(6, 18, 6, 21); line(18, 18, 18, 21)
        line(6, 13, 8, 13); line(16, 13, 18, 13)
    elif name == "users":
        painter.drawEllipse(QRectF(8, 3, 7, 7))
        painter.drawArc(QRectF(4, 12, 15, 14), 0, 180 * 16)
        line(4, 19, 19, 19); line(20, 10, 22, 13); line(21, 16, 21, 19)
    elif name == "map":
        for a, b in ((3, 8), (8, 16), (16, 21)):
            line(a, 6 if a != 8 else 3, b, 3 if b == 8 else 6)
            line(a, 20 if a != 8 else 17, b, 17 if b == 8 else 20)
        line(3, 6, 3, 20); line(8, 3, 8, 17); line(16, 6, 16, 20); line(21, 6, 21, 20)
    elif name == "report":
        line(4, 21, 21, 21); line(5, 17, 5, 12); line(10, 17, 10, 6)
        line(15, 17, 15, 10); line(20, 17, 20, 3)
    elif name == "calendar":
        rect(3, 5, 18, 16); line(3, 10, 21, 10)
        line(7, 2, 7, 7); line(17, 2, 17, 7)
        line(7, 14, 9, 14); line(14, 14, 16, 14)
    elif name == "settings":
        painter.drawEllipse(QRectF(4, 4, 16, 16))
        painter.drawEllipse(QRectF(9, 9, 6, 6))
        for n in range(8):
            a = n * math.pi / 4
            line(12 + 8 * math.cos(a), 12 + 8 * math.sin(a),
                 12 + 10 * math.cos(a), 12 + 10 * math.sin(a))
    elif name == "simple":
        rect(3, 3, 18, 15); line(8, 21, 16, 21); line(12, 18, 12, 21)
        line(7, 10, 10, 13); line(10, 13, 17, 7)
    elif name == "arrow":
        line(3, 12, 20, 12); line(15, 7, 20, 12); line(15, 17, 20, 12)
    else:
        rect(5, 3, 14, 18); line(9, 8, 15, 8); line(9, 12, 15, 12); line(9, 16, 13, 16)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class AvailabilityMap(QWidget):
    """A compact live preview. The existing editor still owns map editing."""
    def __init__(self, open_map, parent=None):
        super().__init__(parent)
        self.rows = []
        self.light = True
        self.open_map = open_map
        self._cells = []
        self.setMinimumHeight(248)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Abrir el mapa completo de espacios")
        self.setAccessibleName("Mapa de disponibilidad de cocheras")

    def set_rows(self, rows):
        self.rows = rows
        self.update()

    def paintEvent(self, event):
        p = palette(self.light)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._cells = []
        if not self.rows:
            painter.setPen(QColor(p["muted"]))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "Todavía no hay cocheras\nCreá tus espacios desde el mapa")
            return
        shown = self.rows
        left = min(row["x"] for row in shown)
        top = min(row["y"] for row in shown)
        right = max(row["x"] + row["w"] for row in shown)
        bottom = max(row["y"] + row["h"] for row in shown)
        scale = min((self.width() - 16) / max(1, right-left),
                    (self.height() - 16) / max(1, bottom-top))
        offset_x = (self.width() - (right-left)*scale) / 2
        offset_y = (self.height() - (bottom-top)*scale) / 2
        occupied_bg = p["map_occupied_bg"]
        occupied_fg = p["map_occupied_fg"]
        for index, row in enumerate(shown):
            x = offset_x + (row["x"] - left) * scale
            y = offset_y + (row["y"] - top) * scale
            width, height = row["w"] * scale, row["h"] * scale
            area = QRectF(x, y, width, height)
            occupied = row["occupied"]
            bg = row["color"]
            color = QColor(bg)
            fg = "#FFFFFF" if color.lightnessF() < 0.55 else "#14263F"
            painter.setPen(QPen(QColor(p["border"]), 1))
            painter.setBrush(QColor(bg))
            painter.drawRect(area)
            painter.setPen(QPen(QColor(fg), 1.4))
            painter.setBrush(Qt.NoBrush)
            font = QFont("Segoe UI")
            font.setPixelSize(max(8, min(14, int(height / 4))))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(area.adjusted(2, 2, -2, -2), Qt.AlignCenter,
                             row["code"] + "\n" + row["state"])
            self._cells.append((area, row))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_map()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        for area, row in self._cells:
            if area.contains(event.position()):
                state = "Ocupada" if row["occupied"] else "Disponible"
                self.setToolTip(f"{row['code']} · {state}\nClic para abrir el mapa")
                break
        super().mouseMoveEvent(event)


class Presentation:
    def __init__(self, window):
        self.window = window
        self.ui = window.ui
        self.demo = bool(getattr(QApplication.instance(), "_modo_demo", False))
        self.light = True
        self._map_rows = None
        self._due_rows = None
        self._build_shell()
        self._build_cochera()
        self._build_estacionamiento()
        self._wrap_pages()
        self.ui.stack.currentChanged.connect(self._switch_page)
        self.window._reloj_timer.timeout.connect(self.update_clock)
        self.apply_preferences()
        self.update_dashboard()
        self._switch_page(self.ui.stack.currentIndex())

    def _button(self, text, callback, icon="document", parent=None, primary=False):
        button = QPushButton(text, parent)
        button.setProperty("presentationIcon", icon)
        light = getattr(QApplication.instance(), "_presentation_light", True)
        p = palette(light)
        button.setIcon(line_icon(icon, p["on_accent"] if primary else p["muted"]))
        if primary:
            button.setProperty("variant", "primary")
        button.clicked.connect(callback)
        return button

    def _navigation(self, button, text, icon):
        button.setProperty("presentationIcon", icon)
        button.setProperty("presentationText", text)
        button.setParent(self.sidebar)
        button.setText(text)
        _role(button, "navButton")
        button.setProperty("variant", None)
        p = palette(getattr(QApplication.instance(), "_presentation_light", True))
        button.setIcon(line_icon(icon, p["sidebar_muted"]))
        button.setIconSize(QSize(21, 21))
        button.setMinimumHeight(45)
        button.setMaximumHeight(52)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setStyleSheet("")
        self.nav_layout.addWidget(button)
        button.show()
        return button

    def _build_shell(self):
        ui, w = self.ui, self.window
        _clear_layout(ui.verticalLayout)
        shell = QHBoxLayout()
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        ui.verticalLayout.addLayout(shell)
        self.sidebar = _role(QFrame(ui.centralwidget), "navSidebar")
        self.sidebar.setObjectName("presentation_sidebar")
        self.sidebar.setFixedWidth(210)
        self.nav_layout = QVBoxLayout(self.sidebar)
        self.nav_layout.setContentsMargins(14, 23, 14, 18)
        self.nav_layout.setSpacing(6)
        brand = QHBoxLayout()
        mark = _label("P", "navBrandMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(36, 36)
        brand.addWidget(mark)
        name = _label("Estacionamiento", "navBrand")
        name.setStyleSheet("font-size: 16px;")
        brand.addWidget(name)
        brand.addStretch()
        self.nav_layout.addLayout(brand)
        self.nav_layout.addSpacing(26)
        self._navigation(ui.btn_cochera, "Cochera", "car")
        self._navigation(ui.btn_estacionamiento, "Estacionamiento", "parking")
        ui.btn_cochera.setCheckable(True)
        ui.btn_estacionamiento.setCheckable(True)
        self.nav_layout.addSpacing(17)
        self.nav_layout.addWidget(_label("GESTIÓN", "navSection"))
        self.nav_layout.addSpacing(4)
        self._navigation(ui.btn_clientes, "Clientes", "users")
        self._navigation(ui.btn_contratos, "Contratos", "document")
        self._navigation(ui.btn_mapa_cocheras, "Mapa de espacios", "map")
        self._navigation(ui.btn_reportes, "Reportes", "report")
        # Same report view, with its mode-specific initial filter.
        ui.btn_reportes.clicked.disconnect()
        ui.btn_reportes.clicked.connect(w._atajo_f8)
        self._navigation(ui.btn_vencimientos, "Vencimientos", "calendar")
        self.nav_layout.addStretch(1)
        self.settings = self._button("Configuración", w._abrir_configuracion, "settings")
        self._navigation(self.settings, "Configuración", "settings")
        self.admin = self._button("Administración", self._open_admin, "document")
        self._navigation(self.admin, "Administración", "document")
        self.sidebar_scroll = QScrollArea(ui.centralwidget)
        self.sidebar_scroll.setObjectName("presentation_sidebar_scroll")
        self.sidebar_scroll.setFrameShape(QFrame.NoFrame)
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar_scroll.setWidget(self.sidebar)
        shell.addWidget(self.sidebar_scroll)
        content = QWidget(ui.centralwidget)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        header = _role(QFrame(content), "header")
        header.setObjectName("presentation_header")
        header.setStyleSheet("QFrame#presentation_header { border-radius: 0; border-top: none; border-left: none; border-right: none; }")
        row = QHBoxLayout(header)
        row.setContentsMargins(24, 14, 24, 14)
        self.breadcrumb = _label("Inicio / Cochera")
        self.breadcrumb.hide()
        row.addStretch(1)
        if self.demo:
            chip = _label("DEMO · Datos ficticios", "chip")
            row.addWidget(chip)
            row.addSpacing(12)
        self.clock = _label("")
        row.addWidget(self.clock)
        content_layout.addWidget(header)
        content_layout.addWidget(ui.stack, 1)
        shell.addWidget(content, 1)
        ui.menubar.hide()
        w.setWindowTitle("Estacionamiento · Muestra" if self.demo else "Estacionamiento · Gestión")
        w.statusBar().setSizeGripEnabled(False)
        w.statusBar().showMessage(
            "Sesión de demostración · Datos ficticios · Los cambios se reinician al cerrar"
            if self.demo else ""
        )
        self.update_clock()

    def _open_admin(self):
        self.window.menu_admin.popup(self.admin.mapToGlobal(self.admin.rect().topRight()))

    def _page_heading(self, title, subtitle, callback, button_text="Abrir mapa", icon="map"):
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(4)
        column.addWidget(_label(title, "title"))
        column.addWidget(_label(subtitle))
        row.addLayout(column, 1)
        row.addWidget(self._button(button_text, callback, icon, primary=True))
        return row

    def _metric(self, card_name, title_name, value_name, title, note, tone=None):
        card = getattr(self.ui, card_name)
        _role(card, "metric", tone)
        card.setStyleSheet("")
        card.setFrameShape(QFrame.NoFrame)
        card.setMinimumHeight(118)
        card.setMaximumHeight(148)
        layout = card.layout()
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(5)
        title_label = getattr(self.ui, title_name)
        title_label.setText(title)
        _role(title_label, "metricTitle")
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        value_label = getattr(self.ui, value_name)
        _role(value_label, "metricValue")
        value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        value_label.setStyleSheet("")
        note_label = _label(note, "metricNote")
        layout.addWidget(note_label)
        return note_label

    def _panel(self, parent=None):
        frame = _role(QFrame(parent), "panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        return frame, layout

    def _build_cochera(self):
        ui, w = self.ui, self.window
        _clear_layout(ui.cocheraLayout)
        ui.group_cochera_acciones.hide()
        ui.label_cochera_title.hide()
        ui.label_fecha_num.hide()
        ui.label_hora_value.hide()
        ui.cocheraLayout.addLayout(self._page_heading(
            "Resumen de cocheras", "Ocupación, contratos y cobros en un solo lugar.", w._abrir_mapa_cocheras))
        group = ui.group_cochera_resumen
        group.setTitle("")
        group.setProperty("role", "metrics")
        _clear_layout(ui.kpiGrid)
        self.occupied_note = self._metric("card_ocupadas", "label_ocupadas_title", "label_ocupadas_value",
                                          "Ocupadas", "Cocheras asignadas", "accent")
        self._metric("card_total", "label_total_title", "label_total_value",
                     "Espacios totales", "Cocheras habilitadas")
        self._metric("card_libres", "label_libres_title", "label_libres_value",
                     "Disponibles", "Listas para asignar", "success")
        self._metric("card_ingresos", "label_ingresos_title", "label_ingresos_value",
                     "Ingresos del mes", "Cobros de cochera")
        for col, card in enumerate((ui.card_total, ui.card_ocupadas, ui.card_libres, ui.card_ingresos)):
            ui.kpiGrid.addWidget(card, 0, col)
            ui.kpiGrid.setColumnStretch(col, 1)
        ui.card_mensual.hide()
        ui.cocheraLayout.addWidget(group)
        panels = QHBoxLayout()
        panels.setSpacing(16)
        self.map_panel, map_layout = self._panel()
        headings = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(_label("Mapa de disponibilidad", "sectionTitle"))
        heading.addWidget(_label("Estado actual de los espacios"))
        headings.addLayout(heading, 1)
        legend = _label("Cochera · Ocupado · Libre", "metricNote")
        headings.addWidget(legend)
        map_layout.addLayout(headings)
        self.map = AvailabilityMap(w._abrir_mapa_cocheras, self.map_panel)
        self.map.setMouseTracking(True)
        map_layout.addWidget(self.map, 1)
        footer = QHBoxLayout()
        ui.label_mensual_title.setParent(self.map_panel)
        ui.label_mensual_title.setText("Tarifa mensual")
        _role(ui.label_mensual_title, "subtitle")
        footer.addWidget(ui.label_mensual_title)
        footer.addStretch(1)
        ui.label_mensual_value.setParent(self.map_panel)
        _role(ui.label_mensual_value, "sectionTitle")
        footer.addWidget(ui.label_mensual_value)
        ui.label_mensual_title.show()
        ui.label_mensual_value.show()
        map_layout.addLayout(footer)
        panels.addWidget(self.map_panel, 3)
        self.due_panel, due_layout = self._panel()
        self.due_panel.setMinimumWidth(282)
        due_layout.addWidget(_label("Próximos vencimientos", "sectionTitle"))
        due_layout.addWidget(_label("Seguimiento de contratos"))
        self.due_list = QVBoxLayout()
        self.due_list.setSpacing(8)
        due_layout.addLayout(self.due_list)
        due_layout.addStretch(1)
        due_layout.addWidget(self._button("Ver vencimientos", w._abrir_vencimientos, "arrow"))
        panels.addWidget(self.due_panel, 2)
        ui.cocheraLayout.addLayout(panels, 1)
        shortcuts, shortcuts_layout = self._panel()
        shortcuts.setProperty("role", "quickAccess")
        shortcuts_layout.setContentsMargins(18, 12, 18, 12)
        row = QHBoxLayout()
        row.addWidget(_label("Accesos rápidos", "sectionTitle"))
        row.addStretch(1)
        clientes_shortcut = self._button("Clientes", w._abrir_clientes, "users")
        contratos_shortcut = self._button("Contratos", w._abrir_contratos)
        row.addWidget(clientes_shortcut)
        row.addWidget(contratos_shortcut)
        self.report_shortcut = self._button("Reportes", w._atajo_f8, "report")
        row.addWidget(self.report_shortcut)
        for button in (clientes_shortcut, contratos_shortcut, self.report_shortcut):
            button.setProperty("variant", "primary")
            button.setMinimumHeight(42)
            button.setIcon(line_icon(button.property("presentationIcon") or "document", "#FFFFFF"))
            _refresh(button)
        shortcuts_layout.addLayout(row)
        ui.cocheraLayout.addWidget(shortcuts)

    def _build_estacionamiento(self):
        ui, w = self.ui, self.window
        _clear_layout(ui.estacionamientoLayout)
        ui.label_estacionamiento.hide()
        ui.label_est_fecha_num.hide()
        ui.label_est_hora_top_value.hide()
        ui.group_est_acciones.hide()
        ui.card_est_hora.hide()
        ui.card_est_tarifa.hide()
        ui.estacionamientoLayout.addLayout(self._page_heading(
            "Estacionamiento", "Registrá ingresos y salidas, y consultá los vehículos en playa.",
            w._abrir_mapa_cocheras))
        ui.group_est_resumen.setTitle("")
        ui.group_est_resumen.setProperty("role", "metrics")
        self._metric("card_est_total", "label_est_total_title", "label_est_total_value",
                     "Espacios totales", "Lugares de estacionamiento")
        self._metric("card_est_ocupadas", "label_est_ocupadas_title", "label_est_ocupadas_value",
                     "Vehículos en playa", "Ingresos activos", "accent")
        self._metric("card_est_libres", "label_est_libres_title", "label_est_libres_value",
                     "Disponibles", "Espacios libres", "success")
        self._metric("card_est_tarifa_resumen", "label_est_tarifa_resumen_title", "label_est_tarifa_resumen_value",
                     "Tarifa por hora", "Tarifa base para autos")
        ui.estacionamientoLayout.addWidget(ui.group_est_resumen)
        body = QHBoxLayout()
        body.setSpacing(16)
        ui.group_est_registro.setTitle("Registro de vehículo")
        ui.group_est_registro.setMinimumWidth(290)
        ui.group_est_registro.setMaximumWidth(390)
        ui.est_form_layout.setRowWrapPolicy(QFormLayout.WrapAllRows)
        ui.est_form_layout.setVerticalSpacing(10)
        ui.est_form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        ui.est_registro_layout.setContentsMargins(18, 18, 18, 18)
        ui.est_registro_layout.setSpacing(14)
        ui.input_patente_est.setPlaceholderText("Ej.: AB 123 CD")
        ui.input_espacio_est.setPlaceholderText("Asignación automática")
        ui.label_est_espacio.setText("Espacio (opcional)")
        ui.label_est_tipo_vehiculo.setText("Tipo de vehículo")
        ui.btn_ingreso_est.setText("Registrar ingreso · F9")
        ui.btn_salida_est.setText("Registrar salida · F10")
        ui.btn_ingreso_est.setIcon(line_icon("arrow", "#FFFFFF"))
        ui.btn_salida_est.setIcon(line_icon("car", "#FFFFFF"))
        # Vertical buttons keep the full action labels legible on a small screen.
        ui.est_buttons_layout.setDirection(QBoxLayout.TopToBottom)
        ui.est_buttons_layout.setSpacing(8)
        ui.label_resultado_est.setWordWrap(True)
        _role(ui.label_resultado_est, "subtitle")
        helper = _label("Ingresá una patente para registrar un ingreso.\nPara una salida, seleccioná el vehículo en la lista.")
        helper.setWordWrap(True)
        ui.est_registro_layout.addWidget(helper)
        ui.est_registro_layout.addStretch(1)
        body.addWidget(ui.group_est_registro, 2)
        ui.group_est_activos.setTitle("Vehículos en playa")
        ui.est_activos_layout.setContentsMargins(16, 18, 16, 16)
        # Filter and sorting controls wrap gracefully beside the narrower form.
        bar = ui.est_activos_layout.itemAt(0).layout()
        if bar:
            for index in range(bar.count()):
                widget = bar.itemAt(index).widget()
                if isinstance(widget, QLabel):
                    widget.hide()
            _clear_layout(bar)
            bar.addWidget(w._input_filtro_est_activos, 1)
            bar.addWidget(w._combo_orden_est_activos)
        w._input_filtro_est_activos.setPlaceholderText("Buscar patente o espacio…")
        w._input_filtro_est_activos.setMinimumWidth(140)
        w._combo_orden_est_activos.setMinimumWidth(150)
        self.active_count = _label("", "metricNote")
        self.active_count.hide()
        body.addWidget(ui.group_est_activos, 4)
        ui.estacionamientoLayout.addLayout(body, 1)
        ui.btn_modo_sencillo.setParent(ui.page_estacionamiento)
        ui.btn_modo_sencillo.setText("Modo sencillo")
        ui.btn_modo_sencillo.setProperty("variant", "primary")
        ui.btn_modo_sencillo.setProperty("presentationIcon", "simple")
        ui.btn_modo_sencillo.setIcon(line_icon("simple", "#FFFFFF"))
        ui.btn_modo_sencillo.setMinimumHeight(42)
        _refresh(ui.btn_modo_sencillo)
        ui.estacionamientoLayout.itemAt(0).layout().addWidget(ui.btn_modo_sencillo)
        ui.btn_modo_sencillo.show()

    def _wrap_pages(self):
        current = self.ui.stack.currentIndex()
        for index, page in enumerate((self.ui.page_cochera, self.ui.page_estacionamiento)):
            self.ui.stack.removeWidget(page)
            scroll = QScrollArea()
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setWidget(page)
            self.ui.stack.insertWidget(index, scroll)
        self.ui.stack.setCurrentIndex(current)

    def apply_preferences(self):
        """Run after the legacy preferences pass so visual constraints stay consistent."""
        app = QApplication.instance()
        self.light = getattr(app, "_presentation_light", True)
        p = palette(self.light)
        self.window.setStyleSheet("")
        self.map.light = self.light
        self.map.update()
        self.ui.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.ui.verticalLayout.setSpacing(0)
        for page, layout in ((self.ui.page_cochera, self.ui.cocheraLayout),
                             (self.ui.page_estacionamiento, self.ui.estacionamientoLayout)):
            layout.setContentsMargins(24, 20, 24, 20)
            layout.setSpacing(16)
            # Remove legacy trailing spacers added during preference refreshes.
            while layout.count() and layout.itemAt(layout.count() - 1).spacerItem():
                layout.takeAt(layout.count() - 1)
            page.setMinimumHeight(660)
        for group, layout in ((self.ui.group_cochera_resumen, self.ui.cochera_resumen_layout),
                              (self.ui.group_est_resumen, self.ui.est_resumen_layout)):
            group.setMinimumHeight(118)
            group.setMaximumHeight(160)
            group.setStyleSheet("QGroupBox { background: transparent; border: none; margin: 0; padding: 0; }")
            layout.setContentsMargins(0, 0, 0, 0)
        for grid in (self.ui.kpiGrid, self.ui.est_resumen_grid):
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(0)
        for card_name in ("card_total", "card_ocupadas", "card_libres", "card_ingresos",
                          "card_est_total", "card_est_ocupadas", "card_est_libres", "card_est_tarifa_resumen"):
            card = getattr(self.ui, card_name)
            card.setMinimumHeight(118)
            card.setMaximumHeight(148)
        for button in self.sidebar.findChildren(QPushButton):
            button.setText(button.property("presentationText") or button.text())
            color = p["on_accent"] if button.isChecked() else p["sidebar_muted"]
            button.setIcon(line_icon(button.property("presentationIcon") or "document", color))
            button.setIconSize(QSize(21, 21))
            button.setStyleSheet("")
            button.setMinimumHeight(44)
            button.setMaximumHeight(52)
        navigation_width = max(
            (button.fontMetrics().horizontalAdvance(button.text()) + 100
             for button in self.sidebar.findChildren(QPushButton)), default=210)
        self.sidebar.setFixedWidth(max(210, min(300, navigation_width)))
        self.sidebar_scroll.setFixedWidth(self.sidebar.width() + 10)
        self.sidebar_scroll.setStyleSheet(
            f"QScrollArea#presentation_sidebar_scroll {{ background: {palette(self.light)['sidebar']}; }}")
        self.sidebar.setMinimumHeight(self.nav_layout.minimumSize().height())
        for button in self.window.findChildren(QPushButton):
            icon = button.property("presentationIcon")
            if icon and button.property("role") != "navButton":
                color = p["on_accent"] if button.property("variant") == "primary" else p["muted"]
                button.setIcon(line_icon(icon, color))
        self.ui.btn_ingreso_est.setIcon(line_icon("arrow", "#FFFFFF"))
        self.ui.btn_salida_est.setIcon(line_icon("car", "#FFFFFF"))
        for button in (self.ui.btn_ingreso_est, self.ui.btn_salida_est):
            button.setMinimumHeight(42)
            button.setMaximumHeight(52)
        self.ui.group_est_registro.setMinimumHeight(380)
        self.ui.group_est_registro.setMaximumHeight(16777215)
        self.ui.group_est_activos.setMinimumHeight(380)
        self.ui.group_est_activos.setMaximumHeight(16777215)
        self.ui.input_patente_est.setMinimumHeight(42)
        self.ui.input_patente_est.setStyleSheet("font-size: 19px; font-weight: 600;")
        for field in self.window.findChildren(QAbstractSpinBox) + self.window.findChildren(QComboBox):
            field.setMinimumHeight(max(36, field.fontMetrics().height() + 18))
        self.ui.card_mensual.hide()
        self.ui.group_cochera_acciones.hide()
        self.ui.group_est_acciones.hide()
        self.ui.label_cochera_title.hide()
        self.ui.label_estacionamiento.hide()
        self.ui.label_fecha_num.hide()
        self.ui.label_est_fecha_num.hide()
        self.ui.label_mensual_value.setStyleSheet("font-size: 19px; font-weight: 700;")
        admin = (self.window.rol or "").upper() == "DUENO"
        allowed = (self.window.rol or "").upper() in {"DUENO", "OPERADOR"}
        self.ui.card_ingresos.setVisible(admin)
        self.due_panel.setVisible(admin)
        self.ui.btn_reportes.setVisible(admin)
        self.ui.btn_vencimientos.setVisible(admin)
        self.report_shortcut.setVisible(admin)
        self.ui.btn_mapa_cocheras.setVisible(allowed)
        self.settings.setVisible(allowed)
        self.admin.setVisible(allowed)
        for table in self.window.findChildren(QTableWidget):
            _style_table(table)
        self.update_clock()

    def _switch_page(self, index):
        self.ui.btn_cochera.setChecked(index == 0)
        self.ui.btn_estacionamiento.setChecked(index == 1)
        p = palette(self.light)
        for button in (self.ui.btn_cochera, self.ui.btn_estacionamiento):
            color = p["on_accent"] if button.isChecked() else p["sidebar_muted"]
            button.setIcon(line_icon(button.property("presentationIcon"), color))
        self.breadcrumb.setText("Inicio / " + ("Cochera" if index == 0 else "Estacionamiento"))
        if index == 1:
            self.update_active_count()

    def update_clock(self):
        self.clock.setText(QDateTime.currentDateTime().toString("dd MMM yyyy  ·  HH:mm"))

    def update_active_count(self):
        count = len(getattr(self.window, "_activos_est_cache", []))
        self.active_count.setText(f"{count} vehículo{'s' if count != 1 else ''} en playa · Doble clic para seleccionar")

    def update_dashboard(self):
        """Fetch only the two new presentation surfaces; no writes or migrations."""
        ui = self.ui
        total = int(ui.label_total_value.text() or 0)
        occupied = int(ui.label_ocupadas_value.text() or 0)
        self.occupied_note.setText(f"{occupied / total:.0%} de ocupación" if total else "Cocheras asignadas")
        ui.btn_vencimientos.setStyleSheet("")
        ui.btn_vencimientos.setText("Vencimientos")
        ui.label_ocupadas_value.setStyleSheet("")
        ui.label_libres_value.setStyleSheet("")
        connection = None
        try:
            connection = get_connection()
            rows = connection.execute(
                "SELECT e.codigo,e.id_cliente,e.es_reservado,m.x,m.y,m.w,m.h, "
                "EXISTS(SELECT 1 FROM movimientos v WHERE v.id_espacio=e.id_espacio "
                "AND v.fecha_salida IS NULL) AS ocupado "
                "FROM espacios e JOIN espacios_mapa m ON m.codigo=e.codigo "
                "WHERE e.activo=1 ORDER BY e.codigo"
            ).fetchall()
            colors = {"map_color_cochera": "#3c50c8", "map_color_ocupado": "#b43232",
                      "map_color_libre": "#ffffff"}
            for config in connection.execute("SELECT clave,valor FROM configuracion WHERE clave LIKE 'map_color_%'"):
                if config["clave"] in colors and QColor(config["valor"]).isValid():
                    colors[config["clave"]] = config["valor"]
            map_rows = []
            for row in rows:
                state = "OCUPADO" if row["ocupado"] else "COCHERA" if row["es_reservado"] or row["id_cliente"] is not None else "LIBRE"
                key = "map_color_ocupado" if state == "OCUPADO" else "map_color_cochera" if state == "COCHERA" else "map_color_libre"
                map_rows.append(dict(code=str(row["codigo"]), occupied=bool(row["ocupado"] or row["id_cliente"]),
                                     state=state,color=colors[key], **{k: row[k] for k in ("x","y","w","h")}))
            due_rows = []
            if (self.window.rol or "").upper() == "DUENO":
                due_rows = [dict(row) for row in connection.execute(
                    "SELECT c.nombre, e.codigo, cc.fecha_vencimiento FROM cochera_contratos cc "
                    "JOIN clientes c ON c.id_cliente=cc.id_cliente JOIN espacios e ON e.id_espacio=cc.id_espacio "
                    "WHERE cc.activo=1 AND date(cc.fecha_vencimiento)<=date(?, '+7 days') "
                    "ORDER BY cc.fecha_vencimiento LIMIT 3", (date.today().isoformat(),)
                ).fetchall()]
            if map_rows != self._map_rows:
                self._map_rows = map_rows
                self.map.set_rows(map_rows)
            if due_rows != self._due_rows:
                self._due_rows = due_rows
                self._show_due(due_rows)
        except sqlite3.Error:
            if self._map_rows is None:
                self.map.set_rows([])
            if self._due_rows is None:
                self._show_due(None)
        finally:
            if connection:
                connection.close()
        self.update_active_count()

    def _show_due(self, rows):
        while self.due_list.count():
            item = self.due_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not rows:
            text = "No se pudieron cargar los vencimientos." if rows is None else "Todo al día\nSin vencimientos en los próximos 7 días."
            label = _label(text, "emptyText")
            label.setWordWrap(True)
            label.setMinimumHeight(100)
            self.due_list.addWidget(label)
            return
        for row in rows:
            frame = QFrame()
            layout = QHBoxLayout(frame)
            layout.setContentsMargins(0, 12, 0, 12)
            column = QVBoxLayout()
            name = _label(row["nombre"], "sectionTitle")
            name.setWordWrap(True)
            column.addWidget(name)
            column.addWidget(_label(f"Cochera {row['codigo']}"))
            layout.addLayout(column, 1)
            try:
                delta = (date.fromisoformat(str(row["fecha_vencimiento"])[:10]) - date.today()).days
            except ValueError:
                delta = None
            text = "Revisar fecha" if delta is None else ("Vencido" if delta < 0 else "Hoy" if delta == 0 else f"En {delta} día{'s' if delta != 1 else ''}")
            badge = _label(text, "badge")
            badge.setProperty("tone", "danger" if delta is not None and delta < 0 else "warning")
            layout.addWidget(badge)
            self.due_list.addWidget(frame)


def _style_table(table):
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(max(40, table.fontMetrics().height() + 18))
    table.horizontalHeader().setMinimumSectionSize(60)
    table.horizontalHeader().setMinimumHeight(38)
    if not table.property("presentationTooltips"):
        table.setProperty("presentationTooltips", True)

        def add_tooltip(item):
            if item is not None and not item.toolTip() and item.text():
                item.setToolTip(item.text())

        table.itemChanged.connect(add_tooltip)
        for row in range(table.rowCount()):
            for column in range(table.columnCount()):
                add_tooltip(table.item(row, column))


class _ReadableTableColumns(QObject):
    """A stretch column must keep a readable minimum, even beside long data."""
    def __init__(self, table, column):
        super().__init__(table)
        self.table, self.column = table, column
        self._queued = False
        table.viewport().installEventFilter(self)
        table.model().dataChanged.connect(self.schedule)
        table.model().rowsInserted.connect(self.schedule)
        self.schedule()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Show):
            self.schedule()
        return super().eventFilter(watched, event)

    def schedule(self, *args):
        if not self._queued:
            self._queued = True
            QTimer.singleShot(0, self.adjust)

    def adjust(self):
        self._queued = False
        table, column = self.table, self.column
        header = table.horizontalHeader()
        title = table.horizontalHeaderItem(column)
        minimum = max(150, header.fontMetrics().horizontalAdvance(title.text() if title else "") + 28)
        occupied = sum(header.sectionSize(index) for index in range(table.columnCount())
                       if index != column and not table.isColumnHidden(index))
        mode = QHeaderView.Stretch if table.viewport().width() - occupied >= minimum else QHeaderView.Interactive
        if header.sectionResizeMode(column) != mode:
            header.setSectionResizeMode(column, mode)
        if mode == QHeaderView.Interactive and header.sectionSize(column) != minimum:
            header.resizeSection(column, minimum)


def _style_dialog_table(table):
    _style_table(table)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setStretchLastSection(False)
    header.setMaximumSectionSize(360)
    table.setMinimumHeight(max(150, table.minimumHeight()))
    for wanted in ("Cliente", "Nombre", "Modelo", "Detalle", "Descripcion"):
        matches = [index for index in range(table.columnCount())
                   if table.horizontalHeaderItem(index)
                   and table.horizontalHeaderItem(index).text().strip() == wanted
                   and not table.isColumnHidden(index)]
        if matches:
            header.setSectionResizeMode(matches[0], QHeaderView.Stretch)
            table._presentation_columns = _ReadableTableColumns(table, matches[0])
            break


def _compact_contract_form(dialog):
    layout = dialog.layout()
    for index in range(layout.count()):
        form = layout.itemAt(index).layout()
        if not isinstance(form, QFormLayout):
            continue
        rows = []
        for row in range(form.rowCount()):
            label = form.itemAt(row, QFormLayout.LabelRole)
            field = form.itemAt(row, QFormLayout.FieldRole)
            if label and field:
                rows.append((label.widget(), field.widget()))
        _clear_layout(form)
        _detach_layout_item(layout, index)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        for row, (label, field) in enumerate(rows):
            column = (row % 2) * 2
            grid.addWidget(label, row // 2, column)
            grid.addWidget(field, row // 2, column + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        layout.insertLayout(index, grid)
        break
    dialog.table.setMinimumHeight(180)
    layout.setStretch(layout.indexOf(dialog.table), 1)


def _compact_client_form(dialog):
    layout = dialog.layout()
    panel_list = layout.itemAt(0).layout()
    panel_form = layout.itemAt(1).layout()
    layout.setStretch(0, 1)
    layout.setStretch(1, 1)
    for index in range(panel_form.count()):
        row = panel_form.itemAt(index).layout()
        if row and row.indexOf(dialog.input_patente) >= 0:
            _clear_layout(row)
            _detach_layout_item(panel_form, index)
            grid = QGridLayout()
            grid.setSpacing(8)
            grid.addWidget(dialog.input_patente, 0, 0)
            grid.addWidget(dialog.input_modelo, 0, 1)
            grid.addWidget(dialog.combo_tipo_vehiculo, 0, 2)
            grid.addWidget(dialog.btn_agregar_veh, 1, 0, 1, 2)
            grid.addWidget(dialog.btn_eliminar_veh, 1, 2)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 2)
            grid.setColumnStretch(2, 1)
            panel_form.insertLayout(index, grid)
            break
    panel_list.insertWidget(0, _label("Clientes", "title"))
    panel_form.insertWidget(0, _label("Datos del cliente", "sectionTitle"))
    dialog.vehiculos_table.setMinimumHeight(125)


def _compact_map_toolbar(dialog):
    layout = dialog.layout()
    toolbar = layout.itemAt(0).layout()
    _clear_layout(toolbar)
    _detach_layout_item(layout, 0)
    grid = QGridLayout()
    grid.setSpacing(8)
    rows = (
        (dialog.btn_agregar, dialog.btn_renombrar, dialog.btn_eliminar,
         dialog.btn_marcar_cochera, dialog.btn_quitar_cochera, dialog.btn_guardar),
        (dialog.btn_colores, dialog.btn_zoom_in,
         dialog.btn_zoom_out, dialog.btn_zoom_reset, dialog.btn_recargar),
    )
    for row, buttons in enumerate(rows):
        for column, button in enumerate(buttons):
            grid.addWidget(button, row, column)
            grid.setColumnStretch(column, 1)
    dialog.btn_alineado.hide()
    for button in (dialog.btn_renombrar, dialog.btn_colores):
        button.setProperty("variant", "neutral")
        _refresh(button)
    dialog.btn_guardar.setProperty("variant", "primary")
    _refresh(dialog.btn_guardar)
    dialog.btn_marcar_cochera.setProperty("variant", "primary")
    _refresh(dialog.btn_marcar_cochera)
    layout.insertLayout(0, grid)
    layout.setStretch(layout.indexOf(dialog.view), 1)


def _scroll_dialog_body(dialog):
    """Keep the original controls reachable on small displays and large fonts."""
    original_layout = dialog.layout()
    if original_layout is None:
        return
    body = QWidget(dialog)
    body.setObjectName("presentation_dialog_body")
    body.setLayout(original_layout)
    original_layout.setSizeConstraint(QLayout.SetMinimumSize)
    scroll = QScrollArea(dialog)
    scroll.setObjectName("presentation_dialog_scroll")
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setWidgetResizable(True)
    scroll.setWidget(body)
    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(scroll)
    dialog._presentation_scroll = scroll
    dialog._presentation_body = body


def prepare_dialog(dialog):
    """Polish dialogs once, after their dynamic contents have been built."""
    if dialog.property("presentationPrepared"):
        return
    dialog.setProperty("presentationPrepared", True)
    if isinstance(dialog, QMessageBox):
        return
    # Native file/color dialogs own their layout; the global palette is enough.
    if type(dialog).__module__.startswith("PySide6"):
        return
    dialog.setStyleSheet("")
    layout = dialog.layout()
    if layout:
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
    name = type(dialog).__name__
    if name == "ContratosDialog":
        _compact_contract_form(dialog)
    elif name == "ClientesDialog":
        _compact_client_form(dialog)
    elif name == "MapaCocheraDialog":
        _compact_map_toolbar(dialog)
    if name in {"LoginDialog", "FirstUserDialog"}:
        _prepare_access(dialog)
    elif isinstance(layout, QVBoxLayout):
        title = dialog.findChild(QLabel, "modo_sencillo_titulo")
        if title:
            _role(title, "title")
            title.setStyleSheet("")
            _refresh(title)
        else:
            title = _label(dialog.windowTitle(), "title")
            title.setWordWrap(True)
            layout.insertWidget(0, title)
    for table in dialog.findChildren(QTableWidget):
        _style_dialog_table(table)
    for field in dialog.findChildren(QLineEdit):
        if isinstance(field.parentWidget(), QAbstractSpinBox):
            field.setMinimumHeight(0)
        else:
            field.setMinimumHeight(max(34, field.fontMetrics().height() + 16))
    for field in dialog.findChildren(QAbstractSpinBox) + dialog.findChildren(QComboBox):
        field.setMinimumHeight(max(36, field.fontMetrics().height() + 18))
    for button in dialog.findChildren(QPushButton):
        if button.maximumHeight() < 34:
            button.setMaximumHeight(52)
        button.setMinimumHeight(max(34, button.minimumHeight()))
    # Calcular el contenido antes de envolverlo: el sizeHint del scroll pierde
    # el tamaño natural y antes dejaba ventanas chicas con controles ocultos.
    if layout:
        layout.activate()
    natural = dialog.sizeHint().expandedTo(dialog.minimumSizeHint())
    desired_width = max(dialog.width(), natural.width())
    desired_height = max(dialog.height(), natural.height())
    for table in dialog.findChildren(QTableWidget):
        columns_width = sum(table.columnWidth(i) for i in range(table.columnCount())
                            if not table.isColumnHidden(i))
        desired_width = max(desired_width, columns_width + 70)
    _scroll_dialog_body(dialog)
    # Keep large dialogs accessible when the user has a 1366x768 display.
    screen = dialog.screen() or QApplication.primaryScreen()
    if screen:
        available = screen.availableGeometry()
        max_width, max_height = available.width() - 56, available.height() - 72
        dialog.setMinimumWidth(min(dialog.minimumWidth(), max_width))
        dialog.setMinimumHeight(min(dialog.minimumHeight(), max_height))
        dialog.resize(min(desired_width + 20, max_width),
                      min(desired_height + 20, max_height))
        dialog.move(available.center() - dialog.rect().center())
    if hasattr(dialog, "_presentation_scroll"):
        dialog._presentation_scroll.verticalScrollBar().setValue(0)
        dialog._presentation_scroll.horizontalScrollBar().setValue(0)


def _prepare_access(dialog):
    layout = dialog.layout()
    _clear_layout(layout)
    first = type(dialog).__name__ == "FirstUserDialog"
    dialog.setMinimumWidth(460)
    dialog.setMinimumHeight(580 if first else 510)
    dialog.resize(480, 580 if first else 510)
    layout.setContentsMargins(36, 30, 36, 30)
    layout.setSpacing(8)
    brand = QHBoxLayout()
    mark = _label("P", "navBrandMark")
    mark.setFixedSize(40, 40)
    mark.setAlignment(Qt.AlignCenter)
    brand.addWidget(mark)
    names = QVBoxLayout()
    names.setSpacing(2)
    names.setContentsMargins(0, 0, 0, 0)
    names.addWidget(_label("Estacionamiento", "sectionTitle"))
    names.addWidget(_label("Cocheras y estacionamiento"))
    brand.addLayout(names)
    brand.addStretch()
    layout.addLayout(brand)
    layout.addSpacing(20)
    layout.addWidget(_label("Creá tu administrador" if first else "Bienvenido", "title"))
    layout.addWidget(_label("Configurá el primer acceso al sistema." if first else "Ingresá tus datos para comenzar."))
    layout.addSpacing(8)
    for title, field in (("Usuario", dialog.input_usuario), ("Contraseña", dialog.input_password)):
        layout.addWidget(_label(title, "metricTitle"))
        layout.addWidget(field)
        field.setMinimumHeight(40)
        field.show()
    if first:
        layout.addWidget(_label("Repetir contraseña", "metricTitle"))
        layout.addWidget(dialog.input_password2)
        dialog.input_password2.setMinimumHeight(40)
        dialog.input_password2.show()
    layout.addSpacing(12)
    button = dialog.btn_crear if first else dialog.btn_ingresar
    button.setText("Crear administrador" if first else "Ingresar al sistema")
    button.setProperty("variant", "primary")
    _refresh(button)
    layout.addWidget(button)
    layout.addWidget(dialog.btn_cancelar)
    button.show()
    dialog.btn_cancelar.show()
    # Old labels belonged to the detached form; hide them explicitly.
    for child in dialog.findChildren(QLabel):
        if child.property("role") is None:
            child.hide()
    dialog.input_usuario.setFocus()
