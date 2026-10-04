"""Tema de presentación para Qt, independiente de las reglas del negocio."""

from math import isfinite
from pathlib import Path
import sys

from PySide6.QtGui import QColor, QFont, QPalette


def palette(light=True):
    """Colores semánticos compartidos por las vistas y sus componentes."""
    colors = {
        "sidebar": "#14263F", "sidebar_raised": "#203650",
        "sidebar_border": "#2B415B", "sidebar_text": "#F2F6FC",
        "sidebar_muted": "#B1C0D2", "sidebar_accent": "#34C1B2",
        "sidebar_selected": "#087F81", "sidebar_selected_hover": "#088385",
        "brand_text": "#14263F", "shadow": "#0A1525",
    }
    if light:
        colors.update({
            "bg": "#F2F5F8", "surface": "#FFFFFF", "raised": "#F7F9FC",
            "border": "#DCE4ED", "text": "#172B45", "muted": "#5E6D82",
            "accent": "#087F81", "accent_hover": "#066D70", "soft": "#E7F4F3",
            "success": "#16805F", "warning": "#A75D11", "danger": "#BB4250",
            "accent_text": "#066D70", "success_text": "#117254",
            "warning_text": "#98530E", "danger_text": "#BB4250",
            "success_soft": "#E8F6EF", "warning_soft": "#FFF3DF",
            "danger_soft": "#FCECEF", "on_accent": "#FFFFFF",
            "success_button": "#16805F", "danger_button": "#BB4250",
            "warning_button": "#A75D11",
            "success_hover": "#187A5C", "danger_hover": "#AD3745",
            "warning_hover": "#9A5510",
            "map_occupied_bg": "#E8EFF8", "map_occupied_fg": "#4A6A92",
            "map_free_bg": "#E7F4F3", "map_free_fg": "#066D70",
        })
    else:
        colors.update({
            # VS Code Dark+: charcoal chrome, neutral surfaces and blue actions.
            "bg": "#1E1E1E", "surface": "#252526", "raised": "#2D2D30",
            "border": "#3C3C3C", "text": "#D4D4D4", "muted": "#A6A6A6",
            "accent": "#007ACC", "accent_hover": "#006FBA", "soft": "#094771",
            "success": "#89D185", "warning": "#DCDCAA", "danger": "#F48771",
            "accent_text": "#4FC1FF", "success_text": "#89D185",
            "warning_text": "#DCDCAA", "danger_text": "#F48771",
            "success_soft": "#26362B", "warning_soft": "#3D3823",
            "danger_soft": "#402727", "on_accent": "#FFFFFF",
            "success_button": "#2B6D4A", "danger_button": "#A1260D",
            "warning_button": "#865A18",
            "success_hover": "#32805A", "danger_hover": "#B43C29",
            "warning_hover": "#98651C",
            "sidebar": "#252526", "sidebar_raised": "#2A2D2E",
            "sidebar_border": "#3C3C3C", "sidebar_text": "#F0F0F0",
            "sidebar_muted": "#BBBBBB", "sidebar_accent": "#007ACC",
            "sidebar_selected": "#37373D", "sidebar_selected_hover": "#414145",
            "brand_text": "#FFFFFF", "shadow": "#000000",
            "map_occupied_bg": "#333333", "map_occupied_fg": "#C5C5C5",
            "map_free_bg": "#093C5A", "map_free_fg": "#4FC1FF",
        })
    return colors


def stylesheet(light=True):
    """Devuelve QSS para la aplicación y los roles de la nueva presentación."""
    colors = palette(light)
    asset_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    colors["checkbox_check"] = (asset_root / "assets" / "checkbox-check.svg").as_posix()
    base = """
    QMainWindow, QDialog { background: %(bg)s; color: %(text)s; }
    QWidget { color: %(text)s; font-family: "Segoe UI"; }
    QLabel { background: transparent; border: none; }
    QWidget#centralwidget, QStackedWidget, QScrollArea,
    QScrollArea > QWidget > QWidget { background: transparent; }
    QFrame[role="panel"], QFrame[role="metric"] {
        background: %(surface)s; border: 1px solid %(border)s; border-radius: 14px;
    }
    QFrame[role="header"] {
        background: %(surface)s; border: 1px solid %(border)s; border-radius: 14px;
    }
    QFrame[role="quickAccess"] {
        background: %(soft)s; border: 1px solid %(accent)s;
        border-left: 5px solid %(accent)s; border-radius: 14px;
    }
    QFrame[role="hero"] {
        background: %(raised)s; border: 1px solid %(border)s; border-radius: 16px;
    }
    QFrame[role="metric"][tone="accent"] { border-top: 3px solid %(accent)s; }
    QFrame[role="metric"][tone="success"] { border-top: 3px solid %(success)s; }
    QFrame[role="metric"][tone="warning"] { border-top: 3px solid %(warning)s; }
    QFrame[role="metric"][tone="danger"] { border-top: 3px solid %(danger)s; }
    QLabel[role="eyebrow"] {
        color: %(accent_text)s; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;
    }
    QLabel[role="title"] { color: %(text)s; font-size: 25px; font-weight: 700; }
    QLabel[role="sectionTitle"] { color: %(text)s; font-size: 16px; font-weight: 600; }
    QLabel[role="subtitle"] { color: %(muted)s; font-size: 12px; }
    QLabel[role="metricTitle"] { color: %(muted)s; font-size: 12px; font-weight: 500; }
    QLabel[role="metricValue"] { color: %(text)s; font-size: 28px; font-weight: 700; }
    QLabel[role="metricNote"] { color: %(muted)s; font-size: 10px; }
    QLabel[role="emptyTitle"] { color: %(text)s; font-size: 18px; font-weight: 600; }
    QLabel[role="emptyText"] { color: %(muted)s; font-size: 12px; }
    QLabel[role="chip"], QLabel[role="badge"] {
        color: %(accent_text)s; background: %(soft)s; border: 1px solid %(border)s;
        border-radius: 9px; padding: 5px 9px; font-size: 11px; font-weight: 600;
    }
    QLabel[tone="accent"] { color: %(accent_text)s; }
    QLabel[tone="success"] { color: %(success_text)s; }
    QLabel[tone="warning"] { color: %(warning_text)s; }
    QLabel[tone="danger"] { color: %(danger_text)s; }
    QLabel[role="badge"][tone="success"], QLabel[role="chip"][tone="success"] {
        color: %(success_text)s; background: %(success_soft)s; border: none;
    }
    QLabel[role="badge"][tone="warning"], QLabel[role="chip"][tone="warning"] {
        color: %(warning_text)s; background: %(warning_soft)s; border: none;
    }
    QLabel[role="badge"][tone="danger"], QLabel[role="chip"][tone="danger"] {
        color: %(danger_text)s; background: %(danger_soft)s; border: none;
    }
    QFrame[role="navSidebar"] {
        background: %(sidebar)s; border: none; border-radius: 0;
    }
    QFrame[role="navSidebar"] QLabel { color: %(sidebar_text)s; }
    QLabel[role="navSection"] {
        color: %(sidebar_muted)s; font-size: 10px; font-weight: 600; letter-spacing: 1.3px;
    }
    QLabel[role="navBrand"] { color: %(sidebar_text)s; font-size: 19px; font-weight: 700; }
    QLabel[role="navUser"] { color: %(sidebar_muted)s; font-size: 11px; }
    QLabel[role="navBrandMark"] {
        color: %(brand_text)s; background: %(sidebar_accent)s; border-radius: 10px;
        font-size: 22px; font-weight: 800;
    }
    QFrame[role="navSidebar"] QLabel[role="navSection"],
    QFrame[role="navSidebar"] QLabel[role="navUser"] { color: %(sidebar_muted)s; }
    QFrame[role="navSidebar"] QLabel[role="navBrandMark"] { color: %(brand_text)s; }
    QPushButton[role="navButton"] {
        background: transparent; color: %(sidebar_muted)s; border: 1px solid transparent;
        border-radius: 9px; padding: 11px 14px; text-align: left; font-weight: 500;
    }
    QPushButton[role="navButton"]:hover {
        background: %(sidebar_raised)s; color: %(sidebar_text)s;
    }
    QPushButton[role="navButton"]:checked {
        background: %(sidebar_selected)s; color: #FFFFFF; border-color: %(sidebar_selected)s; font-weight: 600;
    }
    QPushButton[role="navButton"]:checked:hover {
        background: %(sidebar_selected_hover)s; border-color: %(sidebar_selected_hover)s;
    }
    QPushButton[role="navButton"]:focus { border-color: %(sidebar_accent)s; }
    QPushButton[role="navButton"]:disabled {
        background: transparent; color: #75869C; border-color: transparent;
    }
    QGroupBox {
        background: %(surface)s; border: 1px solid %(border)s;
        border-radius: 12px; margin-top: 15px; padding-top: 12px; font-weight: 600;
    }
    QGroupBox::title {
        subcontrol-origin: margin; left: 14px; padding: 0 6px;
        color: %(text)s; background: %(bg)s;
    }
    QPushButton, QToolButton {
        color: %(text)s; background: %(raised)s; border: 1px solid %(border)s;
        border-radius: 8px; padding: 7px 12px; font-weight: 600;
    }
    QPushButton:hover, QToolButton:hover { background: %(soft)s; border-color: %(accent)s; }
    QPushButton:pressed, QToolButton:pressed { background: %(border)s; }
    QPushButton:focus, QToolButton:focus { border-color: %(accent)s; }
    QPushButton:disabled, QToolButton:disabled {
        color: %(muted)s; background: %(raised)s; border-color: %(border)s;
    }
    QPushButton[role="actionTile"] {
        background: %(surface)s; color: %(text)s; border: 1px solid %(border)s;
        border-radius: 12px; padding: 12px 16px; text-align: left; font-size: 13px;
    }
    QPushButton[role="actionTile"]:hover { background: %(raised)s; border-color: %(accent)s; }
    QPushButton[variant="info"], QPushButton[variant="primary"] {
        background: %(accent)s; color: %(on_accent)s; border-color: %(accent)s;
    }
    QPushButton[variant="info"]:hover, QPushButton[variant="primary"]:hover {
        background: %(accent_hover)s; border-color: %(accent_hover)s;
    }
    QPushButton[variant="success"] {
        background: %(success_button)s; color: #FFFFFF; border-color: %(success_button)s;
    }
    QPushButton[variant="success"]:hover { background: %(success_hover)s; border-color: %(success_hover)s; }
    QPushButton[variant="danger"] {
        background: %(danger_button)s; color: #FFFFFF; border-color: %(danger_button)s;
    }
    QPushButton[variant="danger"]:hover { background: %(danger_hover)s; border-color: %(danger_hover)s; }
    QPushButton[variant="warning"] {
        background: %(warning_button)s; color: #FFFFFF; border-color: %(warning_button)s;
    }
    QPushButton[variant="warning"]:hover { background: %(warning_hover)s; border-color: %(warning_hover)s; }
    QPushButton[variant="neutral"] { background: %(raised)s; color: %(text)s; border-color: %(border)s; }
    QPushButton[variant="neutral"]:hover { background: %(soft)s; border-color: %(accent)s; }
    QPushButton[variant="info"]:disabled, QPushButton[variant="primary"]:disabled,
    QPushButton[variant="success"]:disabled, QPushButton[variant="danger"]:disabled,
    QPushButton[variant="warning"]:disabled, QPushButton[variant="neutral"]:disabled {
        color: %(muted)s; background: %(raised)s; border-color: %(border)s;
    }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
    QDateTimeEdit, QTextEdit, QPlainTextEdit {
        background: %(raised)s; color: %(text)s; border: 1px solid %(border)s;
        border-radius: 8px; padding: 7px 9px;
        selection-background-color: %(accent)s; selection-color: %(on_accent)s;
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border-color: %(accent)s;
    }
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
    QDateEdit:disabled, QTimeEdit:disabled, QDateTimeEdit:disabled,
    QTextEdit:disabled, QPlainTextEdit:disabled { background: %(surface)s; color: %(muted)s; }
    QComboBox::drop-down { border: none; width: 26px; }
    QComboBox QAbstractItemView {
        background: %(surface)s; color: %(text)s; border: 1px solid %(border)s;
        selection-background-color: %(soft)s; selection-color: %(text)s; outline: none;
    }
    QTableWidget, QTableView, QListWidget, QListView, QTreeWidget, QTreeView {
        background: %(surface)s; alternate-background-color: %(raised)s;
        color: %(text)s; border: 1px solid %(border)s; border-radius: 10px;
        gridline-color: %(border)s; selection-background-color: %(soft)s;
        selection-color: %(text)s; outline: none;
    }
    QTableWidget::item, QTableView::item { padding: 7px 8px; border-bottom: 1px solid %(border)s; }
    QTableWidget::item:selected, QTableView::item:selected,
    QListWidget::item:selected, QTreeWidget::item:selected { background: %(soft)s; color: %(text)s; }
    QHeaderView::section {
        background: %(raised)s; color: %(muted)s; border: none;
        border-bottom: 1px solid %(border)s; padding: 9px 8px; font-weight: 600;
    }
    QTableCornerButton::section { background: %(raised)s; border: none; }
    QTabWidget::pane { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; }
    QTabBar::tab {
        background: %(raised)s; color: %(muted)s; border: 1px solid %(border)s;
        border-bottom: none; padding: 9px 15px; margin-right: 4px;
        border-top-left-radius: 8px; border-top-right-radius: 8px;
    }
    QTabBar::tab:selected { background: %(surface)s; color: %(accent_text)s; }
    QTabBar::tab:hover { color: %(text)s; }
    QMenuBar { background: %(bg)s; color: %(muted)s; border: none; }
    QMenuBar::item { background: transparent; padding: 5px 11px; }
    QMenuBar::item:selected { background: %(raised)s; color: %(text)s; border-radius: 6px; }
    QMenu { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; padding: 5px; }
    QMenu::item { padding: 8px 25px; border-radius: 5px; }
    QMenu::item:selected { background: %(soft)s; color: %(accent_text)s; }
    QMenu::item:disabled { color: %(muted)s; }
    QMenu::separator { height: 1px; background: %(border)s; margin: 5px 8px; }
    QStatusBar { background: %(bg)s; color: %(muted)s; font-size: 10px; }
    QStatusBar::item { border: none; }
    QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; padding: 7px; }
    QScrollBar:vertical { background: transparent; width: 10px; margin: 3px; }
    QScrollBar:horizontal { background: transparent; height: 10px; margin: 3px; }
    QScrollBar::handle:vertical { background: %(border)s; border-radius: 3px; min-height: 24px; }
    QScrollBar::handle:horizontal { background: %(border)s; border-radius: 3px; min-width: 24px; }
    QScrollBar::handle:hover { background: %(muted)s; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    QCheckBox, QRadioButton { spacing: 7px; background: transparent; }
    QRadioButton::indicator { width: 16px; height: 16px; }
    QCheckBox::indicator {
        width: 20px; height: 20px; border: 2px solid %(muted)s;
        border-radius: 4px; background: %(surface)s;
    }
    QCheckBox::indicator:hover, QCheckBox::indicator:focus { border-color: %(accent)s; }
    QCheckBox::indicator:checked {
        background: %(accent)s; border-color: %(accent)s;
        image: url("%(checkbox_check)s");
    }
    QCheckBox::indicator:checked:hover { background: %(accent_hover)s; border-color: %(accent_hover)s; }
    QCheckBox::indicator:disabled { background: %(raised)s; border-color: %(border)s; }
    QCheckBox::indicator:checked:disabled {
        background: %(muted)s; border-color: %(muted)s;
        image: url("%(checkbox_check)s");
    }
    QProgressBar {
        background: %(raised)s; color: %(text)s; border: 1px solid %(border)s;
        border-radius: 5px; text-align: center;
    }
    QProgressBar::chunk { background: %(accent)s; border-radius: 4px; }
    QSplitter::handle { background: %(border)s; }
    """ % colors
    if light:
        return base
    return base + """
    QFrame[role="panel"], QFrame[role="metric"], QFrame[role="header"],
    QFrame[role="hero"], QGroupBox { border-radius: 4px; }
    QLabel[role="navBrandMark"] { border-radius: 4px; }
    QLabel[role="chip"], QLabel[role="badge"] { border-radius: 3px; }
    QLabel[role="eyebrow"], QLabel[role="chip"], QLabel[role="badge"],
    QLabel[tone="accent"] { color: #4FC1FF; }
    QFrame[role="header"] { background: #333333; }
    QPushButton, QToolButton, QPushButton[role="actionTile"] { border-radius: 3px; }
    QPushButton[role="navButton"] {
        border-radius: 0; border: 1px solid transparent;
        border-left: 3px solid transparent;
    }
    QPushButton[role="navButton"]:checked,
    QPushButton[role="navButton"]:checked:hover { border-left: 3px solid #007ACC; }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
    QDateTimeEdit, QTextEdit, QPlainTextEdit { background: #3C3C3C; border-radius: 3px; }
    QTableWidget, QTableView, QListWidget, QListView, QTreeWidget, QTreeView {
        border-radius: 3px;
    }
    QHeaderView::section { background: #333333; color: #CCCCCC; }
    QTabWidget::pane { border-radius: 3px; }
    QTabBar::tab { border-top-left-radius: 0; border-top-right-radius: 0; }
    QTabBar::tab:selected { color: #FFFFFF; border-top: 2px solid #007ACC; }
    QMenu::item { border-radius: 0; }
    QMenu::item:selected { color: #FFFFFF; }
    QStatusBar { background: #007ACC; color: #FFFFFF; }
    """


def apply_application_theme(app, light=True, scale=1.0):
    """Aplica una base consistente también a diálogos y controles nativos Qt."""
    if app is None:
        return
    try:
        factor = float(scale)
    except (TypeError, ValueError):
        factor = 1.0
    if not isfinite(factor) or factor <= 0:
        factor = 1.0
    p = palette(light)
    app.setStyle("Fusion")
    qt_palette = QPalette()
    role_colors = {
        "Window": p["bg"], "WindowText": p["text"], "Base": p["surface"],
        "AlternateBase": p["raised"], "ToolTipBase": p["surface"],
        "ToolTipText": p["text"], "Text": p["text"], "Button": p["raised"],
        "ButtonText": p["text"], "BrightText": p["danger"],
        "Highlight": p["accent"], "HighlightedText": p["on_accent"],
        "Link": p["accent_text"], "LinkVisited": p["muted"],
        "Light": p["surface"], "Midlight": p["raised"], "Dark": p["border"],
        "Mid": p["border"], "Shadow": p["shadow"], "PlaceholderText": p["muted"],
    }
    for role_name, color in role_colors.items():
        role = getattr(QPalette.ColorRole, role_name)
        qt_palette.setColor(role, QColor(color))
    if hasattr(QPalette.ColorRole, "Accent"):
        qt_palette.setColor(QPalette.ColorRole.Accent, QColor(p["accent"]))
    for role_name in ("Text", "WindowText", "ButtonText", "PlaceholderText"):
        qt_palette.setColor(QPalette.ColorGroup.Disabled,
                            getattr(QPalette.ColorRole, role_name), QColor(p["muted"]))
    qt_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight,
                        QColor(p["border"]))
    qt_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText,
                        QColor(p["muted"]))
    app.setPalette(qt_palette)
    font = QFont("Segoe UI")
    font.setPointSizeF(max(8.0, 10.0 * factor))
    app.setFont(font)
    app.setStyleSheet(stylesheet(light))
