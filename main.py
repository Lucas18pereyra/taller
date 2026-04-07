import sys
import os
import sqlite3
import subprocess
import re
import traceback
import unicodedata
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from PySide6.QtCore import (
    QDate,
    QDateTime,
    QTimer,
    Qt,
    QObject,
    QRectF,
    QPointF,
    QSize,
    QSizeF,
    QEvent,
    QUrl,
    QRegularExpression,
    QStringListModel,
    QLocale,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QBrush,
    QPen,
    QPainter,
    QFont,
    QIcon,
    QPixmap,
    QDesktopServices,
    QPdfWriter,
    QPageSize,
    QKeySequence,
    QShortcut,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow, 
    QDialog,
    QWidget,
    QTabWidget,
    QGroupBox,
    QFrame,
    QLabel,
    QLineEdit,
    QTextEdit,
    QFormLayout,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
    QDoubleSpinBox,
    QListWidget,
    QListWidgetItem,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsRectItem,
    QGraphicsItem,
    QGraphicsTextItem,
    QInputDialog,
    QTableWidget,
    QTableWidgetItem,
    QDateEdit,
    QAbstractItemView,
    QMessageBox,
    QFileDialog,
    QComboBox,
    QCompleter,
    QSpinBox,
    QColorDialog,
    QHeaderView,
    QSizePolicy,
    QStyle,
    QMenu,
)
from ui_ventana_principal import Ui_MainWindow
from database import get_connection, init_db, reset_db
from servicios.contratos import (
    listar_contratos as svc_listar_contratos,
    obtener_detalle_contrato as svc_obtener_detalle_contrato,
    obtener_vehiculo_por_dni as svc_obtener_vehiculo_por_dni,
    obtener_tarifa_mensual_actual as svc_obtener_tarifa_mensual_actual,
    reactivar_contrato_desde_historial as svc_reactivar_contrato_desde_historial,
    registrar_primer_pago_contrato as svc_registrar_primer_pago_contrato,
    registrar_renovacion_contrato as svc_registrar_renovacion_contrato,
)
from servicios.reportes import (
    consultar_detalle as svc_consultar_detalle_reportes,
    consultar_resumen as svc_consultar_resumen_reportes,
    consultar_detalle_rango as svc_consultar_detalle_reportes_rango,
    consultar_resumen_rango as svc_consultar_resumen_reportes_rango,
)
from servicios.backups import (
    crear_backup_db as svc_crear_backup_db,
    eliminar_backup_db as svc_eliminar_backup_db,
    listar_backups_db as svc_listar_backups_db,
    restaurar_backup_db as svc_restaurar_backup_db,
)
from servicios.caja import (
    consultar_detalle_por_metodo_dia as svc_consultar_detalle_metodo_caja,
    eliminar_cierre_caja as svc_eliminar_cierre_caja,
    guardar_cierre_caja as svc_guardar_cierre_caja,
    obtener_cierre_caja as svc_obtener_cierre_caja,
    obtener_cierre_caja_metodos as svc_obtener_cierre_caja_metodos,
    consultar_totales_dia as svc_consultar_totales_caja,
)
from servicios.cobro import (
    calcular_total_estadia as svc_calcular_total_estadia,
    horas_cobradas_con_tolerancia as svc_horas_cobradas_tolerancia,
    parse_fecha_db as svc_parse_fecha_db,
)
from servicios.validaciones import (
    cliente_tiene_movimiento_activo as svc_cliente_tiene_movimiento_activo,
    codigo_cochera_activa_cliente as svc_codigo_cochera_activa_cliente,
    espacio_tiene_movimiento_activo as svc_espacio_tiene_movimiento_activo,
    vehiculo_tiene_movimiento_activo as svc_vehiculo_tiene_movimiento_activo,
)


def _usuario_desde_widget(widget):
    if widget is None:
        return "sistema"
    usuario = getattr(widget, "usuario_actual", None)
    if usuario:
        return usuario
    obj = widget
    while obj is not None:
        usuario = getattr(obj, "usuario", None)
        if usuario:
            return usuario
        try:
            obj = obj.parent()
        except Exception:
            break
    return "sistema"


def _rol_desde_widget(widget):
    obj = widget
    while obj is not None:
        rol = getattr(obj, "rol", None)
        if rol:
            return str(rol)
        try:
            obj = obj.parent()
        except Exception:
            break
    return ""


def _consultar_estado_cliente(id_cliente):
    if not id_cliente:
        return None
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id_cliente, nombre, dni, activo "
            "FROM clientes WHERE id_cliente = ?",
            (id_cliente,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id_cliente": row["id_cliente"],
            "nombre": row["nombre"] or "",
            "dni": row["dni"] or "",
            "activo": int(row["activo"] or 0) == 1,
        }
    except sqlite3.Error:
        return None
    finally:
        if conn:
            conn.close()


def _auditar(widget, accion, detalle=""):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO auditoria (usuario, accion, detalle) VALUES (?, ?, ?)",
            (_usuario_desde_widget(widget), accion, detalle),
        )
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        if conn:
            conn.close()


def _mostrar_error(widget, titulo, mensaje, accion=None, detalle=None):
    detalle_texto = _detalle_error_breve(detalle)
    detalle_extendido = _detalle_error_extendido(detalle)

    box = QMessageBox(widget)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(str(titulo or "Error"))
    box.setText(str(mensaje or "Ocurrio un error."))
    if detalle_texto and detalle_texto not in box.text():
        box.setInformativeText(f"Detalle: {detalle_texto}")
    if detalle_extendido and detalle_extendido != detalle_texto:
        box.setDetailedText(detalle_extendido)
    box.exec()
    if accion:
        _auditar(widget, accion, detalle_texto or detalle or mensaje)


def _detalle_error_breve(detalle=None):
    if isinstance(detalle, BaseException):
        nombre = detalle.__class__.__name__
        texto = str(detalle or "").strip()
        return f"{nombre}: {texto}" if texto else nombre

    texto = str(detalle or "").strip()
    if texto:
        primera_linea = texto.splitlines()[0].strip()
        return primera_linea or texto

    _, exc_value, _ = sys.exc_info()
    if exc_value is not None:
        nombre = exc_value.__class__.__name__
        texto = str(exc_value or "").strip()
        return f"{nombre}: {texto}" if texto else nombre
    return ""


def _detalle_error_extendido(detalle=None):
    if isinstance(detalle, BaseException):
        return "".join(
            traceback.format_exception(
                type(detalle), detalle, detalle.__traceback__
            )
        ).strip()

    texto = str(detalle or "").strip()
    if texto and "Traceback" in texto:
        return texto

    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_value is not None:
        return "".join(traceback.format_exception(exc_type, exc_value, exc_tb)).strip()
    return texto


def _manejar_excepcion_no_controlada(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    detalle = "".join(traceback.format_exception(exc_type, exc_value, exc_tb)).strip()
    try:
        app = QApplication.instance()
        parent = app.activeWindow() if app else None
        _mostrar_error(
            parent,
            "Error inesperado",
            "La aplicacion encontro un error no controlado.",
            accion="Error inesperado",
            detalle=detalle,
        )
    except Exception:
        pass

    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _confirmar_guardado_pendiente(widget, mensaje):
    return QMessageBox.question(
        widget,
        "Cambios sin guardar",
        mensaje,
        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        QMessageBox.Yes,
    )


_TEXTOS_BOTONES_MENSAJE = {
    QMessageBox.Ok: "Aceptar",
    QMessageBox.Open: "Abrir",
    QMessageBox.Save: "Guardar",
    QMessageBox.Cancel: "Cancelar",
    QMessageBox.Close: "Cerrar",
    QMessageBox.Yes: "Si",
    QMessageBox.YesToAll: "Si a todo",
    QMessageBox.No: "No",
    QMessageBox.NoToAll: "No a todo",
    QMessageBox.Abort: "Abortar",
    QMessageBox.Retry: "Reintentar",
    QMessageBox.Ignore: "Ignorar",
    QMessageBox.Apply: "Aplicar",
    QMessageBox.Reset: "Restablecer",
    QMessageBox.Help: "Ayuda",
    QMessageBox.Discard: "Descartar",
}


_TEXTOS_BOTONES_INGLES = {
    "Yes": "Si",
    "&Yes": "Si",
    "Yes to All": "Si a todo",
    "&Yes to All": "Si a todo",
    "No": "No",
    "&No": "No",
    "No to All": "No a todo",
    "&No to All": "No a todo",
    "OK": "Aceptar",
    "&OK": "Aceptar",
    "Cancel": "Cancelar",
    "&Cancel": "Cancelar",
    "Close": "Cerrar",
    "&Close": "Cerrar",
    "Open": "Abrir",
    "&Open": "Abrir",
    "Save": "Guardar",
    "&Save": "Guardar",
    "Save All": "Guardar todo",
    "&Save All": "Guardar todo",
    "Abort": "Abortar",
    "Retry": "Reintentar",
    "Ignore": "Ignorar",
    "Apply": "Aplicar",
    "Reset": "Restablecer",
    "Help": "Ayuda",
    "Discard": "Descartar",
}


def _traducir_botones_mensaje(box):
    if not isinstance(box, QMessageBox):
        return
    for boton_std, texto in _TEXTOS_BOTONES_MENSAJE.items():
        try:
            boton = box.button(boton_std)
        except Exception:
            boton = None
        if boton is not None:
            boton.setText(texto)


def _traducir_botones_widget(widget):
    if not isinstance(widget, QWidget):
        return
    try:
        botones = widget.findChildren(QPushButton)
    except Exception:
        botones = []
    for boton in botones:
        try:
            texto = str(boton.text() or "").strip()
        except Exception:
            texto = ""
        traducido = _TEXTOS_BOTONES_INGLES.get(texto)
        if traducido:
            boton.setText(traducido)


class _DialogTranslationFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() in (
            QEvent.Polish,
            QEvent.Show,
            QEvent.LanguageChange,
        ) and isinstance(watched, QWidget):
            _traducir_botones_widget(watched)
        if isinstance(watched, QMessageBox) and event.type() in (
            QEvent.Polish,
            QEvent.Show,
            QEvent.LanguageChange,
        ):
            _traducir_botones_mensaje(watched)
        return super().eventFilter(watched, event)


def _antirebote_iniciar(obj, clave):
    bloqueos = getattr(obj, "_antirebote_bloqueos", None)
    if bloqueos is None:
        bloqueos = set()
        setattr(obj, "_antirebote_bloqueos", bloqueos)
    if clave in bloqueos:
        return False
    bloqueos.add(clave)
    return True


def _antirebote_finalizar(obj, clave, cooldown_ms=650, on_release=None):
    bloqueos = getattr(obj, "_antirebote_bloqueos", None)
    if not isinstance(bloqueos, set):
        return

    def _liberar():
        try:
            bloqueos.discard(clave)
        except Exception:
            pass
        if on_release:
            try:
                on_release()
            except Exception:
                pass

    try:
        QTimer.singleShot(int(cooldown_ms), _liberar)
    except Exception:
        _liberar()


class _EnterNavigationFilter(QObject):
    def __init__(self, owner, mapping):
        super().__init__(owner)
        self._mapping = {}
        for origen, destino in (mapping or {}).items():
            if origen is None or destino is None:
                continue
            self._registrar_origen(origen, destino)
            try:
                line_edit = origen.lineEdit() if hasattr(origen, "lineEdit") else None
            except Exception:
                line_edit = None
            if line_edit is not None and line_edit is not origen:
                self._registrar_origen(line_edit, destino)

    def _registrar_origen(self, origen, destino):
        self._mapping[origen] = destino
        try:
            origen.installEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            destino = self._mapping.get(obj)
            if destino is not None:
                self._activar_destino(destino)
                return True
        return super().eventFilter(obj, event)

    @staticmethod
    def _activar_destino(destino):
        if callable(destino):
            destino()
            return

        widget = destino
        modo = "focus"
        if isinstance(destino, tuple) and len(destino) >= 2:
            modo, widget = destino[0], destino[1]

        if widget is None:
            return
        if hasattr(widget, "isEnabled") and not widget.isEnabled():
            return

        if modo == "click" and hasattr(widget, "click"):
            widget.click()
            return

        try:
            widget.setFocus()
        except Exception:
            return

        if isinstance(widget, QLineEdit):
            widget.selectAll()
        elif isinstance(widget, QComboBox):
            try:
                widget.showPopup()
            except Exception:
                pass


def _instalar_enter_navegacion(owner, mapping):
    filtros = getattr(owner, "_enter_nav_filters", None)
    if filtros is None:
        filtros = []
        setattr(owner, "_enter_nav_filters", filtros)
    filtro = _EnterNavigationFilter(owner, mapping)
    filtros.append(filtro)
    return filtro


def _parse_fecha_db(valor):
    return svc_parse_fecha_db(valor)


def _fmt_fecha_hora_local(valor):
    dt = _parse_fecha_db(valor)
    if not dt:
        return str(valor or "")
    return dt.strftime("%d/%m/%Y %H:%M:%S")


_LOCALE_ES_AR = QLocale(QLocale.Spanish, QLocale.Argentina)
try:
    _LOCALE_ES_AR.setNumberOptions(
        _LOCALE_ES_AR.numberOptions() & ~QLocale.RejectGroupSeparator
    )
except Exception:
    pass


def _fmt_numero_local(valor, decimales=2):
    try:
        numero = float(valor or 0.0)
    except (TypeError, ValueError):
        numero = 0.0
    return _LOCALE_ES_AR.toString(numero, "f", max(0, int(decimales or 0)))


def _fmt_money(valor, decimales=2):
    return f"$ {_fmt_numero_local(valor, decimales=decimales)}"


def _configurar_spinbox_numerico(spinbox):
    if spinbox is None:
        return
    try:
        spinbox.setLocale(_LOCALE_ES_AR)
    except Exception:
        pass
    try:
        spinbox.setGroupSeparatorShown(True)
    except Exception:
        pass


def _horas_cobradas_con_tolerancia(segundos, tolerancia_min=15):
    return svc_horas_cobradas_tolerancia(segundos, tolerancia_min=tolerancia_min)


def _calcular_total_estadia(dt_ingreso, dt_salida, tarifa_hora, tolerancia_min=15):
    return svc_calcular_total_estadia(
        dt_ingreso,
        dt_salida,
        tarifa_hora,
        tolerancia_min=tolerancia_min,
    )


def _normalizar_tipo_vehiculo(tipo):
    txt = (tipo or "").strip().upper()
    if txt in ("MOTO", "MOTOCICLETA"):
        return "MOTO"
    if txt in ("CAMIONETA", "PICKUP"):
        return "CAMIONETA"
    return "AUTO"


def _texto_tipo_vehiculo(tipo):
    tipo_norm = _normalizar_tipo_vehiculo(tipo)
    if tipo_norm == "MOTO":
        return "Moto"
    if tipo_norm == "CAMIONETA":
        return "Camioneta"
    return "Auto"


def _solo_digitos(texto):
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


def _usuario_longitud_valida(texto):
    cantidad = len((texto or "").strip())
    return 3 <= cantidad <= 16


def _password_longitud_valida(texto):
    cantidad = len(texto or "")
    return 6 <= cantidad <= 16


def _dni_longitud_valida(texto):
    cantidad = len(_solo_digitos(texto))
    return 6 < cantidad < 9


def _formatear_documento(texto):
    digitos = _solo_digitos(texto)
    if not digitos:
        return ""
    grupos = []
    while len(digitos) > 3:
        grupos.insert(0, digitos[-3:])
        digitos = digitos[:-3]
    if digitos:
        grupos.insert(0, digitos)
    return ".".join(grupos)


def _normalizar_patente(texto):
    return "".join(ch for ch in str(texto or "").strip().upper() if ch.isalnum())


def _formatear_patente(texto):
    patente = _normalizar_patente(texto)
    # Aca meto el espacio solo cuando el formato ya cierra, asi no inventamos una patente rara.
    if re.fullmatch(r"[A-Z]{2}\d{3}[A-Z]{2}", patente):
        return f"{patente[:2]} {patente[2:5]} {patente[5:]}"
    if re.fullmatch(r"[A-Z]{3}\d{3}", patente):
        return f"{patente[:3]} {patente[3:]}"
    if re.fullmatch(r"\d{3}[A-Z]{3}", patente):
        return f"{patente[:3]} {patente[3:]}"
    return patente


def _patente_formato_valido(texto):
    patente = _normalizar_patente(texto)
    if not patente:
        return False
    return bool(
        re.fullmatch(r"[A-Z]{2}\d{3}[A-Z]{2}", patente)
        or re.fullmatch(r"[A-Z]{3}\d{3}", patente)
        or re.fullmatch(r"\d{3}[A-Z]{3}", patente)
    )


def _patente_est_formato_valido(texto):
    patente = _normalizar_patente(texto)
    if not patente:
        return False
    return bool(
        re.fullmatch(r"[A-Z]{2}\d{3}[A-Z]{2}", patente)
        or re.fullmatch(r"[A-Z]{3}\d{3}", patente)
        or re.fullmatch(r"\d{3}[A-Z]{3}", patente)
    )


def _patente_es_moto(texto):
    patente = _normalizar_patente(texto)
    if not patente:
        return False
    return bool(re.fullmatch(r"\d{3}[A-Z]{3}", patente))


def _patente_est_es_moto(texto):
    return _patente_es_moto(texto)


def _formatear_patente_estacionamiento(texto):
    patente = _normalizar_patente(texto)
    if re.fullmatch(r"\d{3}[A-Z]{3}", patente):
        return f"{patente[:3]} {patente[3:]}"
    return _formatear_patente(texto)


def _telefono_a_whatsapp(telefono):
    texto = str(telefono or "").strip()
    if not texto:
        return ""
    # Se respeta el numero ingresado (sin forzar codigo de pais).
    numero = "".join(ch for ch in texto if ch.isdigit() or ch == "+")
    if not numero:
        return ""
    if numero.count("+") > 1:
        return ""
    if "+" in numero and not numero.startswith("+"):
        return ""
    digitos = _solo_digitos(numero)
    if len(digitos) < 6:
        return ""
    return numero


def _plantilla_whatsapp_default():
    return (
        "Hola {nombre}, te recordamos tu vencimiento de cochera ({vencimiento}). "
        "Patente: {patente}. Nueva cuota: {deuda}."
    )


def _sanitizar_template_whatsapp(texto):
    plantilla = str(texto or "").strip()
    if not plantilla:
        return _plantilla_whatsapp_default()
    plantilla = plantilla.replace("{modelo_extra}", "")
    plantilla = plantilla.replace("{patente_extra}", "")
    plantilla = re.sub(r"[ \t]{2,}", " ", plantilla)
    plantilla = re.sub(r" +([.,;:])", r"\1", plantilla)
    plantilla = re.sub(r"\n{3,}", "\n\n", plantilla)
    return plantilla.strip() or _plantilla_whatsapp_default()


def _render_mensaje_whatsapp(nombre, vencimiento, deuda, modelo="", patente=""):
    plantilla = _sanitizar_template_whatsapp(
        _config_get("wa_recordatorio_template", _plantilla_whatsapp_default())
    )
    nombre_txt = (nombre or "").strip() or "cliente"
    venc_txt = (vencimiento or "").strip() or "sin vencimiento"
    deuda_txt = (deuda or "").strip() or "$ 0.00"
    cuota_txt = deuda_txt
    modelo_txt = (modelo or "").strip()
    patente_txt = _formatear_patente(patente or "").strip() or "-"
    modelo_extra = f" Modelo del vehiculo: {modelo_txt}." if modelo_txt else ""
    patente_extra = f" Patente: {patente_txt}." if patente_txt and patente_txt != "-" else ""
    try:
        return plantilla.format(
            nombre=nombre_txt,
            vencimiento=venc_txt,
            deuda=deuda_txt,
            cuota=cuota_txt,
            modelo=modelo_txt,
            modelo_extra=modelo_extra,
            patente=patente_txt,
            patente_extra=patente_extra,
        )
    except Exception:
        return _plantilla_whatsapp_default().format(
            nombre=nombre_txt,
            vencimiento=venc_txt,
            deuda=deuda_txt,
            cuota=cuota_txt,
            modelo=modelo_txt,
            modelo_extra=modelo_extra,
            patente=patente_txt,
            patente_extra=patente_extra,
        )


def _texto_cuota_recordatorio(tipo_vehiculo="AUTO", monto_contrato=0.0):
    monto_actual = svc_obtener_tarifa_mensual_actual(tipo_vehiculo)
    if monto_actual is None or float(monto_actual or 0.0) <= 0:
        monto_actual = float(monto_contrato or 0.0)
    return _fmt_money(float(monto_actual or 0.0))


def _nombre_cliente_valido(texto):
    valor = " ".join(str(texto or "").strip().split())
    if not valor:
        return False
    return bool(re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü' -]+", valor))


def _icono_whatsapp(size=18):
    size = max(14, int(size or 18))
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#25D366"))
        painter.drawEllipse(0, 0, size - 1, size - 1)
        painter.setPen(QPen(QColor("#FFFFFF"), max(1, int(size * 0.08))))
        font = QFont("Arial", max(8, int(size * 0.55)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "W")
    finally:
        painter.end()
    return QIcon(pix)


def _fecha_contrato_qdate(valor):
    fecha = QDate.fromString((valor or "").strip(), "yyyy-MM-dd")
    return fecha if fecha.isValid() else QDate()


def _clasificar_contrato_vista(row, hoy=None):
    hoy = hoy or QDate.currentDate()
    en_historial = int(row.get("en_historial") or 0) == 1
    activo = int(row.get("activo") or 0) == 1
    fecha_venc = _fecha_contrato_qdate(row.get("fecha_vencimiento") or "")
    dias = hoy.daysTo(fecha_venc) if fecha_venc.isValid() else None
    if en_historial:
        estado = "BAJA"
    elif activo and fecha_venc.isValid() and fecha_venc < hoy:
        estado = f"VENCIDO HACE {abs(hoy.daysTo(fecha_venc))} DIA/S"
    elif activo:
        estado = "ACTIVO"
    else:
        estado = "INACTIVO"

    return {
        "principal": not en_historial,
        "estado": estado,
        "dias": dias,
        "fecha_venc": fecha_venc,
    }


def _tarifa_hora_desde_row(row, tipo_vehiculo="AUTO"):
    if not row:
        return None
    tipo_norm = _normalizar_tipo_vehiculo(tipo_vehiculo)

    def _to_float(valor):
        if valor is None:
            return None
        try:
            num = float(valor)
        except (TypeError, ValueError):
            return None
        return num if num > 0 else None

    base = _to_float(row["precio_hora"]) if "precio_hora" in row.keys() else None
    auto = _to_float(row["precio_hora_auto"]) if "precio_hora_auto" in row.keys() else None
    moto = _to_float(row["precio_hora_moto"]) if "precio_hora_moto" in row.keys() else None
    camioneta = (
        _to_float(row["precio_hora_camioneta"]) if "precio_hora_camioneta" in row.keys() else None
    )

    if tipo_norm == "MOTO":
        return moto or base or auto or camioneta
    if tipo_norm == "CAMIONETA":
        return camioneta or base or auto or moto
    return auto or base or moto or camioneta


def _tarifa_mensual_desde_row(row, tipo_vehiculo="AUTO"):
    if not row:
        return None
    tipo_norm = _normalizar_tipo_vehiculo(tipo_vehiculo)

    def _to_float(valor):
        if valor is None:
            return None
        try:
            num = float(valor)
        except (TypeError, ValueError):
            return None
        return num if num > 0 else None

    base = _to_float(row["precio_mensual"]) if "precio_mensual" in row.keys() else None
    auto = _to_float(row["precio_mensual_auto"]) if "precio_mensual_auto" in row.keys() else None
    camioneta = (
        _to_float(row["precio_mensual_camioneta"])
        if "precio_mensual_camioneta" in row.keys()
        else None
    )

    if tipo_norm == "CAMIONETA":
        return camioneta or auto or base
    return auto or base or camioneta


def _config_get(clave, default=""):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT valor FROM configuracion WHERE clave = ?", (clave,))
        row = cur.fetchone()
        if not row:
            return default
        valor = row["valor"]
        if valor is None or valor == "":
            return default
        return valor
    except sqlite3.Error:
        return default
    finally:
        if conn:
            conn.close()


def _config_set(clave, valor):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)",
            (clave, str(valor or "")),
        )
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        if conn:
            conn.close()


def _config_get_bool(clave, default=True):
    valor = str(_config_get(clave, "1" if default else "0") or "").strip().lower()
    return valor not in ("", "0", "false", "no", "off")


def _tema_claro_activo():
    return (_config_get("ui_tema", "oscuro") or "oscuro").strip().lower() == "claro"


def _ui_tamano_texto():
    valor = (_config_get("ui_tamano_texto", "grande") or "grande").strip().lower()
    alias = {
        "normal": "normal",
        "grande": "grande",
        "muy grande": "muy_grande",
        "muy_grande": "muy_grande",
    }
    return alias.get(valor, "grande")


def _ui_factor_escala():
    return {
        "normal": 1.0,
        "grande": 1.2,
        "muy_grande": 1.35,
    }.get(_ui_tamano_texto(), 1.2)


def _ui_escalar_pt(valor, minimo=1):
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        return max(int(minimo or 1), 1)
    return max(int(minimo or 1), int(round(numero * _ui_factor_escala())))


def _ui_escalar_px(valor, minimo=1):
    return _ui_escalar_pt(valor, minimo=minimo)


def _aplicar_fuente_aplicacion(app=None):
    app = app or QApplication.instance()
    if app is None:
        return
    base = getattr(app, "_base_font_ui", None)
    if base is None:
        base = QFont(app.font())
        app._base_font_ui = QFont(base)
    font = QFont(base)
    factor = _ui_factor_escala()
    if font.pointSizeF() > 0:
        font.setPointSizeF(max(8.0, float(font.pointSizeF()) * factor))
    elif font.pointSize() > 0:
        font.setPointSize(max(8, int(round(float(font.pointSize()) * factor))))
    elif font.pixelSize() > 0:
        font.setPixelSize(max(10, int(round(float(font.pixelSize()) * factor))))
    else:
        font.setPointSize(max(10, _ui_escalar_pt(10, minimo=10)))
    app.setFont(font)


def _estilo_modo_sencillo():
    info_font_px = _ui_escalar_px(12, minimo=12)
    if _tema_claro_activo():
        return """
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f6f9fc, stop:0.6 #eef3f9, stop:1 #e6edf6);
                color: #1f2937;
            }
            QLabel#modo_sencillo_titulo {
                color: #0f172a;
                font-weight: 800;
                letter-spacing: 0.3px;
            }
            QLabel#modo_sencillo_info {
                color: #475569;
                font-size: __INFO_FONT__px;
            }
            QLabel#modo_sencillo_fecha_hora {
                color: #0f4c5c;
                background-color: rgba(255, 255, 255, 0.75);
                border: 1px solid #d9e2ec;
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 700;
            }
            QLabel#modo_sencillo_estado {
                background-color: rgba(255, 255, 255, 0.92);
                border: 1px solid #d9e2ec;
                border-left: 6px solid #0f766e;
                border-radius: 10px;
                padding: 10px 12px;
                color: #0f4c5c;
                font-weight: 700;
            }
            QLabel#modo_sencillo_label {
                color: #334155;
                font-weight: 700;
            }
            QLineEdit, QComboBox, QListWidget {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px 8px;
                selection-background-color: #bfdbfe;
                selection-color: #0f172a;
            }
            QLineEdit:focus, QComboBox:focus, QListWidget:focus {
                border-color: #22c55e;
                background-color: #f8fffb;
            }
            QListWidget {
                alternate-background-color: #f8fafc;
            }
            QListWidget::item {
                padding: 8px 10px;
                margin: 2px 0px;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background-color: #dbeafe;
                color: #1e3a8a;
            }
            QPushButton {
                background-color: #0f766e;
                color: #f8fafc;
                border: 1px solid #0f766e;
                border-radius: 10px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background-color: #0d8a81;
            }
            QPushButton:pressed {
                background-color: #0b5f59;
            }
            QPushButton[variant="success"] {
                background-color: #15803d;
                border-color: #16a34a;
                color: #f0fdf4;
            }
            QPushButton[variant="success"]:hover {
                background-color: #169447;
            }
            QPushButton[variant="warning"] {
                background-color: #d97706;
                border-color: #f59e0b;
                color: #fff7ed;
            }
            QPushButton[variant="warning"]:hover {
                background-color: #ea8a10;
            }
            QPushButton[variant="info"] {
                background-color: #2563eb;
                border-color: #3b82f6;
                color: #eff6ff;
            }
            QPushButton[variant="info"]:hover {
                background-color: #1d4ed8;
            }
            QPushButton[variant="neutral"] {
                background-color: #e2e8f0;
                border-color: #cbd5e1;
                color: #334155;
            }
            QPushButton[variant="neutral"]:hover {
                background-color: #dbe4ef;
            }
        """.replace("__INFO_FONT__", str(info_font_px))
    return """
        QDialog {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #171c22, stop:0.55 #11161c, stop:1 #0d1117);
            color: #e5edf5;
        }
        QLabel#modo_sencillo_titulo {
            color: #f8fafc;
            font-weight: 800;
            letter-spacing: 0.3px;
        }
        QLabel#modo_sencillo_info {
            color: #9fb0c3;
            font-size: __INFO_FONT__px;
        }
        QLabel#modo_sencillo_fecha_hora {
            color: #dbeafe;
            background-color: rgba(27, 36, 48, 0.82);
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 6px 12px;
            font-weight: 700;
        }
        QLabel#modo_sencillo_estado {
            background-color: rgba(27, 36, 48, 0.92);
            border: 1px solid #334155;
            border-left: 6px solid #22c55e;
            border-radius: 10px;
            padding: 10px 12px;
            color: #d1fae5;
            font-weight: 700;
        }
        QLabel#modo_sencillo_label {
            color: #d4dde7;
            font-weight: 700;
        }
        QLineEdit, QComboBox, QListWidget {
            background-color: #161b22;
            color: #e5edf5;
            border: 1px solid #374151;
            border-radius: 8px;
            padding: 6px 8px;
            selection-background-color: #1d4ed8;
            selection-color: #eff6ff;
        }
        QLineEdit:focus, QComboBox:focus, QListWidget:focus {
            border-color: #34d399;
            background-color: #1b2430;
        }
        QListWidget {
            alternate-background-color: #11161c;
        }
        QListWidget::item {
            padding: 8px 10px;
            margin: 2px 0px;
            border-radius: 8px;
        }
        QListWidget::item:selected {
            background-color: #1e3a8a;
            color: #dbeafe;
        }
        QPushButton {
            background-color: #2b8a95;
            color: #eaf6f6;
            border: 1px solid #37a3ae;
            border-radius: 10px;
            padding: 8px 14px;
        }
        QPushButton:hover {
            background-color: #33a4af;
        }
        QPushButton:pressed {
            background-color: #257983;
        }
        QPushButton[variant="success"] {
            background-color: #1F7A4C;
            border-color: #2FA86B;
            color: #E9FFF1;
        }
        QPushButton[variant="success"]:hover {
            background-color: #25915B;
        }
        QPushButton[variant="warning"] {
            background-color: #B45309;
            border-color: #F59E0B;
            color: #FFFBEB;
        }
        QPushButton[variant="warning"]:hover {
            background-color: #D97706;
        }
        QPushButton[variant="info"] {
            background-color: #1D4ED8;
            border-color: #3B82F6;
            color: #EEF2FF;
        }
        QPushButton[variant="info"]:hover {
            background-color: #2563EB;
        }
        QPushButton[variant="neutral"] {
            background-color: #3F4C59;
            border-color: #556270;
            color: #F3F4F6;
        }
        QPushButton[variant="neutral"]:hover {
            background-color: #4B5968;
        }
    """.replace("__INFO_FONT__", str(info_font_px))


def _tipos_vehiculo_config_estacionamiento():
    tipos = []
    if _config_get_bool("est_perm_auto", True):
        tipos.append(("Auto", "AUTO"))
    if _config_get_bool("est_perm_moto", True):
        tipos.append(("Moto", "MOTO"))
    if _config_get_bool("est_perm_camioneta", True):
        tipos.append(("Camioneta", "CAMIONETA"))
    return tipos


def _tipos_vehiculo_config_cochera():
    tipos = []
    if _config_get_bool("coch_perm_auto", True):
        tipos.append(("Auto", "AUTO"))
    if _config_get_bool("coch_perm_moto", True):
        tipos.append(("Moto", "MOTO"))
    if _config_get_bool("coch_perm_camioneta", True):
        tipos.append(("Camioneta", "CAMIONETA"))
    return tipos


def _tipo_vehiculo_habilitado_estacionamiento(tipo):
    tipo_norm = _normalizar_tipo_vehiculo(tipo)
    return any(codigo == tipo_norm for _texto, codigo in _tipos_vehiculo_config_estacionamiento())


def _tipo_vehiculo_habilitado_cochera(tipo):
    tipo_norm = _normalizar_tipo_vehiculo(tipo)
    return any(codigo == tipo_norm for _texto, codigo in _tipos_vehiculo_config_cochera())


def _escritorio_base_actual():
    candidatos = [
        Path.home() / "Desktop",
        Path.home() / "OneDrive" / "Desktop",
    ]
    for candidato in candidatos:
        if candidato.exists():
            return candidato
    return candidatos[0]


def _resolver_directorio_app(clave_config, fallback_relativo):
    valor = (_config_get(clave_config, "") or "").strip()
    app_dir = Path(__file__).resolve().parent
    candidatos = []

    if valor:
        ruta_configurada = Path(valor).expanduser()
        candidatos.append(ruta_configurada)

        nombre = ruta_configurada.name.strip()
        if nombre:
            candidatos.append(_escritorio_base_actual() / nombre)

    candidatos.append(app_dir / fallback_relativo)

    vistos = set()
    for carpeta in candidatos:
        carpeta_txt = str(carpeta)
        if not carpeta_txt or carpeta_txt in vistos:
            continue
        vistos.add(carpeta_txt)
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            if valor and carpeta_txt != valor:
                _config_set(clave_config, carpeta_txt)
            return carpeta
        except OSError:
            continue

    carpeta = app_dir / fallback_relativo
    carpeta.mkdir(parents=True, exist_ok=True)
    if valor and str(carpeta) != valor:
        _config_set(clave_config, str(carpeta))
    return carpeta


def _reportes_dir():
    return _resolver_directorio_app("dir_reportes", "reportes")


def _comprobantes_dir():
    return _resolver_directorio_app("dir_comprobantes", "comprobantes")


def _tickets_salida_dir():
    valor = (_config_get("dir_tickets_salida", "") or "").strip()
    if valor:
        return _resolver_directorio_app("dir_tickets_salida", "tickets_salida")
    carpeta = _comprobantes_dir() / "tickets_salida"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _parse_datetime_local(valor):
    texto = str(valor or "").strip()
    if not texto:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(texto, fmt)
        except ValueError:
            pass
    return None


def _slug_archivo(texto):
    base = unicodedata.normalize("NFKD", str(texto or ""))
    base = base.encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower()
    return base or "cliente"


def _mes_texto_archivo(valor_fecha):
    dt = _parse_datetime_local(valor_fecha) or datetime.now()
    meses = [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]
    return f"{meses[max(0, min(11, dt.month - 1))]}_{dt.year}"


def _path_unico(base_path):
    path = Path(base_path)
    if not path.exists():
        return path
    carpeta = path.parent
    stem = path.stem
    suffix = path.suffix
    idx = 2
    while True:
        candidato = carpeta / f"{stem}_{idx}{suffix}"
        if not candidato.exists():
            return candidato
        idx += 1


def _mostrar_en_explorador(path):
    if not path:
        return False
    try:
        archivo = Path(path).expanduser().resolve()
    except Exception:
        archivo = Path(os.path.abspath(str(path)))

    carpeta = archivo if archivo.is_dir() else archivo.parent

    if sys.platform.startswith("win"):
        if archivo.exists() and archivo.is_file():
            try:
                subprocess.Popen(["explorer.exe", "/select,", str(archivo)])
                return True
            except Exception:
                pass
        try:
            os.startfile(str(carpeta))
            return True
        except Exception:
            pass

    try:
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(carpeta)))
    except Exception:
        return False


def _abrir_archivo_local(path):
    archivo = Path(path).resolve()
    if not archivo.exists():
        return False
    try:
        if archivo.is_file() and archivo.stat().st_size <= 0:
            return False
    except Exception:
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(archivo))
            return True
    except Exception:
        pass
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(archivo)],
                shell=False,
            )
            return True
    except Exception:
        pass
    try:
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(archivo))):
            return True
    except Exception:
        pass
    return _mostrar_en_explorador(archivo)


def _abrir_ticket_o_avisar(parent, path):
    if _abrir_archivo_local(path):
        return True
    QMessageBox.warning(
        parent,
        "Ticket",
        "No se pudo abrir el ticket automaticamente.\n"
        f"Revisa esta ubicacion:\n{Path(path).resolve()}",
    )
    return False


def _generar_comprobante_pdf(path, titulo, lineas, subtitulo=None):
    lineas = [
        (str(label or "").strip(), str(value or "").strip())
        for label, value in (lineas or [])
        if str(label or "").strip()
    ]

    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setResolution(96)
    painter = QPainter(writer)
    try:
        w = float(writer.width())
        h = float(writer.height())
        margen = 42.0
        content_w = max(240.0, w - (margen * 2.0))
        y = 40.0

        nombre_local = (_config_get("empresa_nombre", "") or "").strip()
        direccion_local = (_config_get("empresa_direccion", "") or "").strip()
        telefono_local = (_config_get("empresa_telefono", "") or "").strip()
        subtitulo_final = str(subtitulo or nombre_local or "").strip()

        painter.setRenderHint(QPainter.Antialiasing, True)

        header_h = 92.0 if subtitulo_final else 76.0
        header_rect = QRectF(margen, y, content_w, header_h)
        painter.setPen(QPen(QColor(208, 214, 220), 1))
        painter.setBrush(QBrush(QColor(246, 248, 251)))
        painter.drawRoundedRect(header_rect, 10.0, 10.0)

        painter.setFont(QFont("Arial", 18, QFont.Bold))
        painter.setPen(QColor(28, 31, 36))
        painter.drawText(
            QRectF(margen + 16.0, y + 14.0, content_w - 32.0, 28.0),
            Qt.AlignCenter | Qt.AlignVCenter,
            str(titulo or ""),
        )

        if subtitulo_final:
            painter.setFont(QFont("Arial", 10))
            painter.setPen(QColor(78, 85, 93))
            painter.drawText(
                QRectF(margen + 16.0, y + 42.0, content_w - 32.0, 18.0),
                Qt.AlignCenter | Qt.AlignVCenter,
                subtitulo_final,
            )

        painter.setPen(QColor(182, 188, 196))
        painter.drawLine(
            int(margen + 18.0),
            int(y + header_h - 24.0),
            int(margen + content_w - 18.0),
            int(y + header_h - 24.0),
        )
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor(88, 95, 104))
        painter.drawText(
            QRectF(margen + 18.0, y + header_h - 20.0, content_w - 36.0, 14.0),
            Qt.AlignCenter | Qt.AlignVCenter,
            f"Emitido: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        )

        y += header_h + 18.0

        label_w = max(120.0, content_w * 0.32)
        value_w = max(140.0, content_w - label_w - 28.0)
        font_label = QFont("Arial", 10, QFont.Bold)
        font_valor = QFont("Arial", 11)
        font_destacado = QFont("Arial", 12, QFont.Bold)
        total_h = 18.0
        filas_medidas = []

        for label, value in lineas:
            painter.setFont(font_valor)
            rect_valor = painter.boundingRect(
                QRectF(0.0, 0.0, value_w, 1000.0),
                Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
                value or "-",
            )
            row_h = max(28.0, rect_valor.height() + 14.0)
            filas_medidas.append((label, value or "-", row_h))
            total_h += row_h

        body_rect = QRectF(margen, y, content_w, total_h)
        painter.setPen(QPen(QColor(214, 219, 226), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawRoundedRect(body_rect, 10.0, 10.0)

        fila_y = y + 9.0
        for idx, (label, value, row_h) in enumerate(filas_medidas):
            row_rect = QRectF(margen + 8.0, fila_y, content_w - 16.0, row_h)
            if label.lower() in ("monto", "total"):
                painter.fillRect(row_rect, QColor(232, 245, 235))
            elif idx % 2 == 0:
                painter.fillRect(row_rect, QColor(249, 250, 252))

            painter.setFont(font_label)
            painter.setPen(QColor(84, 89, 97))
            painter.drawText(
                QRectF(margen + 18.0, fila_y + 4.0, label_w, row_h - 8.0),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"{label}:",
            )

            painter.setFont(
                font_destacado if label.lower() in ("monto", "total") else font_valor
            )
            painter.setPen(
                QColor(26, 92, 54)
                if label.lower() in ("monto", "total")
                else QColor(25, 28, 34)
            )
            painter.drawText(
                QRectF(margen + 18.0 + label_w, fila_y + 4.0, value_w, row_h - 8.0),
                Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
                value,
            )

            painter.setPen(QPen(QColor(228, 232, 238), 1))
            painter.drawLine(
                int(margen + 16.0),
                int(fila_y + row_h),
                int(margen + content_w - 16.0),
                int(fila_y + row_h),
            )
            fila_y += row_h

        y = body_rect.bottom() + 18.0
        datos_local = []
        if direccion_local:
            datos_local.append(f"Direccion: {direccion_local}")
        if telefono_local:
            datos_local.append(f"Telefono: {telefono_local}")
        if datos_local:
            footer_rect = QRectF(margen, y, content_w, 42.0)
            painter.setPen(QPen(QColor(222, 226, 232), 1))
            painter.setBrush(QBrush(QColor(248, 249, 251)))
            painter.drawRoundedRect(footer_rect, 8.0, 8.0)
            painter.setFont(QFont("Arial", 9))
            painter.setPen(QColor(86, 92, 100))
            painter.drawText(
                QRectF(margen + 14.0, y + 8.0, content_w - 28.0, 26.0),
                Qt.AlignCenter | Qt.AlignVCenter,
                " | ".join(datos_local),
            )
    finally:
        painter.end()


def _generar_ticket_pdf(path, titulo, lineas, ancho_mm=80.0, subtitulo=None):
    lineas = [
        (str(label or "").strip(), str(value or "").strip())
        for label, value in (lineas or [])
    ]

    def _filas_envueltas(valor, max_chars=28):
        texto = str(valor or "").strip()
        if not texto:
            return 1
        total = 0
        for parte in texto.splitlines() or [texto]:
            total += max(1, (len(parte) + max_chars - 1) // max_chars)
        return max(1, total)

    filas_extra = sum(max(0, _filas_envueltas(value) - 1) for _, value in lineas)
    header_px = 54 if subtitulo else 42
    alto_px_estimado = header_px + (len(lineas) * 18) + (filas_extra * 10) + 20
    alto_mm = max(95.0, (float(alto_px_estimado) / 96.0) * 25.4 + 4.0)

    writer = QPdfWriter(str(path))
    writer.setPageSize(
        QPageSize(QSizeF(float(ancho_mm), float(alto_mm)), QPageSize.Millimeter)
    )
    writer.setResolution(96)

    painter = QPainter(writer)
    try:
        w = float(writer.width())
        x = 10.0
        y = 10.0
        content_w = max(100.0, w - (x * 2.0))

        header_h = 38.0 + (12.0 if subtitulo else 0.0)
        header_rect = QRectF(x, y, content_w, header_h)
        painter.setPen(QPen(QColor(70, 70, 70), 1))
        painter.setBrush(QBrush(QColor(240, 240, 240)))
        painter.drawRoundedRect(header_rect, 4.0, 4.0)

        font_titulo = QFont("Arial", 13)
        font_titulo.setBold(True)
        painter.setFont(font_titulo)
        painter.setPen(QColor(18, 18, 18))
        painter.drawText(
            QRectF(x + 4.0, y + 4.0, content_w - 8.0, 20.0),
            Qt.AlignCenter | Qt.AlignVCenter,
            str(titulo or ""),
        )

        if subtitulo:
            painter.setFont(QFont("Arial", 10))
            painter.setPen(QColor(35, 35, 35))
            painter.drawText(
                QRectF(x + 4.0, y + 22.0, content_w - 8.0, 14.0),
                Qt.AlignCenter | Qt.AlignVCenter,
                str(subtitulo),
            )

        y += header_h + 8.0

        label_w = max(70.0, content_w * 0.34)
        value_w = max(60.0, content_w - label_w - 8.0)

        font_label = QFont("Arial", 8)
        font_label.setBold(True)
        font_valor = QFont("Arial", 9)

        for idx, (label, value) in enumerate(lineas):
            valor_txt = value or "-"
            painter.setFont(font_valor)
            rect_valor = painter.boundingRect(
                QRectF(0.0, 0.0, value_w, 1000.0),
                Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
                valor_txt,
            )
            row_h = max(16.0, rect_valor.height() + 6.0)

            if idx % 2 == 0:
                painter.fillRect(QRectF(x, y, content_w, row_h), QColor(248, 248, 248))

            painter.setFont(font_label)
            painter.setPen(QColor(82, 82, 82))
            painter.drawText(
                QRectF(x + 2.0, y + 1.0, label_w - 2.0, row_h - 2.0),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"{label}:",
            )

            painter.setFont(font_valor)
            painter.setPen(QColor(20, 20, 20))
            painter.drawText(
                QRectF(x + label_w, y + 1.0, value_w, row_h - 2.0),
                Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
                valor_txt,
            )

            painter.setPen(QPen(QColor(215, 215, 215), 1))
            painter.drawLine(int(x), int(y + row_h), int(x + content_w), int(y + row_h))
            y += row_h
    finally:
        painter.end()


def _emitir_comprobante_cochera(id_contrato, monto, metodo, meses, nueva_venc):
    pago = _ultimo_pago_contrato(id_contrato)
    if not pago:
        return None

    nombre_archivo = (
        f"cochera_{_slug_archivo(pago.get('nombre'))}_"
        f"comprobante_{_mes_texto_archivo(pago.get('fecha_pago'))}.pdf"
    )
    path = _path_unico(_comprobantes_dir() / nombre_archivo)
    concepto = (
        "Activacion de contrato"
        if str(meses or "").strip().lower() == "activacion"
        else f"Pago de cochera ({meses} mes/es)"
    )
    fecha_pago = _parse_datetime_local(pago.get("fecha_pago"))
    lineas = [
        ("Tipo", "Cochera"),
        ("Cliente", pago.get("nombre") or "-"),
        ("DNI", _formatear_documento(pago.get("dni")) or "-"),
        ("Telefono", pago.get("telefono") or "-"),
        ("Patente", pago.get("patente") or "-"),
        ("Modelo", pago.get("modelo") or "-"),
        ("Espacio", pago.get("codigo") or "-"),
        ("Concepto", concepto),
        ("Monto", _fmt_money(monto)),
        ("Metodo", metodo),
        (
            "Fecha del pago",
            fecha_pago.strftime("%d/%m/%Y %H:%M")
            if fecha_pago
            else str(pago.get("fecha_pago") or "-"),
        ),
        ("Nuevo vencimiento", nueva_venc),
    ]
    if str(pago.get("usuario") or "").strip():
        lineas.append(("Registrado por", pago.get("usuario")))
    if str(pago.get("ref_externa") or "").strip():
        lineas.append(("Referencia", pago.get("ref_externa")))
    _generar_comprobante_pdf(
        path,
        "Comprobante de pago",
        lineas,
        subtitulo=(_config_get("empresa_nombre", "") or "").strip() or None,
    )
    return path


def _ultimo_pago_contrato(id_contrato):
    if not id_contrato:
        return None
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT pc.id_pago, pc.monto, pc.metodo, pc.ref_externa, pc.usuario, "
            "pc.fecha_pago, cc.fecha_inicio, cc.fecha_vencimiento, "
            "c.nombre, c.dni, COALESCE(c.telefono, '') AS telefono, "
            "e.codigo, COALESCE(v_sel.patente, '') AS patente, "
            "COALESCE(v_sel.modelo, '') AS modelo "
            "FROM pagos_cochera pc "
            "JOIN cochera_contratos cc ON cc.id_contrato = pc.id_contrato "
            "JOIN clientes c ON c.id_cliente = cc.id_cliente "
            "JOIN espacios e ON e.id_espacio = cc.id_espacio "
            "LEFT JOIN vehiculos v_sel ON v_sel.id_vehiculo = cc.id_vehiculo "
            "WHERE pc.id_contrato = ? "
            "ORDER BY datetime(pc.fecha_pago) DESC, pc.id_pago DESC "
            "LIMIT 1",
            (id_contrato,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None
    finally:
        if conn:
            conn.close()


def _emitir_comprobante_ultimo_pago_contrato(id_contrato):
    pago = _ultimo_pago_contrato(id_contrato)
    if not pago:
        return None, None

    nombre_archivo = (
        f"cochera_{_slug_archivo(pago.get('nombre'))}_"
        f"comprobante_{_mes_texto_archivo(pago.get('fecha_pago'))}.pdf"
    )
    path = _path_unico(_comprobantes_dir() / nombre_archivo)
    fecha_pago = _parse_datetime_local(pago.get("fecha_pago"))
    lineas = [
        ("Tipo", "Cochera"),
        ("Cliente", pago.get("nombre") or "-"),
        ("DNI", _formatear_documento(pago.get("dni")) or "-"),
        ("Telefono", pago.get("telefono") or "-"),
        ("Patente", pago.get("patente") or "-"),
        ("Modelo", pago.get("modelo") or "-"),
        ("Espacio", pago.get("codigo") or "-"),
        (
            "Fecha del pago",
            fecha_pago.strftime("%d/%m/%Y %H:%M") if fecha_pago else str(pago.get("fecha_pago") or "-"),
        ),
        ("Monto", _fmt_money(float(pago.get("monto") or 0.0))),
        ("Metodo", pago.get("metodo") or "-"),
        (
            "Vencimiento actual",
            QDate.fromString(pago.get("fecha_vencimiento") or "", "yyyy-MM-dd").toString("dd/MM/yyyy")
            if QDate.fromString(pago.get("fecha_vencimiento") or "", "yyyy-MM-dd").isValid()
            else (pago.get("fecha_vencimiento") or "-"),
        ),
    ]
    if str(pago.get("usuario") or "").strip():
        lineas.append(("Registrado por", pago.get("usuario")))
    if str(pago.get("ref_externa") or "").strip():
        lineas.append(("Referencia", pago.get("ref_externa")))

    _generar_comprobante_pdf(
        path,
        "Comprobante de pago",
        lineas,
        subtitulo=(_config_get("empresa_nombre", "") or "").strip() or None,
    )
    return path, pago


def _emitir_estado_cuenta_pdf(data):
    data = data or {}
    cliente = (data.get("cliente") or "").strip() or "cliente"
    carpeta = _reportes_dir() / "estados_cuenta"
    carpeta.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = _path_unico(carpeta / f"estado_cuenta_{_slug_archivo(cliente)}_{ts}.pdf")

    contratos = data.get("contratos") or []
    pagos = data.get("pagos") or []

    contratos_txt = "Sin contratos registrados."
    if contratos:
        contratos_txt = "\n".join(
            [
                (
                    f"Contrato {row.get('id_contrato') or '-'} | "
                    f"Espacio {row.get('espacio') or '-'} | "
                    f"{row.get('vencimiento') or '-'} | "
                    f"{row.get('estado') or '-'} | "
                    f"Deuda: {_fmt_money(float(row.get('deuda') or 0.0))}"
                )
                for row in contratos
            ]
        )

    pagos_txt = "Sin pagos registrados."
    if pagos:
        filas_pagos = []
        for row in pagos:
            fecha_pago = _parse_datetime_local(row.get("fecha_pago"))
            fecha_txt = (
                fecha_pago.strftime("%d/%m/%Y %H:%M")
                if fecha_pago
                else str(row.get("fecha_pago") or "-")
            )
            filas_pagos.append(
                (
                    f"{fecha_txt} | {_fmt_money(float(row.get('monto') or 0.0))} | "
                    f"{row.get('metodo') or '-'} | "
                    f"Contrato {row.get('id_contrato') or '-'} | "
                    f"Espacio {row.get('espacio') or '-'}"
                )
            )
        pagos_txt = "\n".join(filas_pagos)

    lineas = [
        ("Cliente", cliente),
        ("DNI", _formatear_documento(data.get("dni")) or "-"),
        ("Contratos activos", str(int(data.get("contratos_activos") or 0))),
        ("Mensual comprometido", _fmt_money(float(data.get("mensual") or 0.0))),
        ("Pagado este mes", _fmt_money(float(data.get("pagado_mes") or 0.0))),
        ("Saldo del mes", _fmt_money(float(data.get("saldo_mes") or 0.0))),
        ("Deuda estimada", _fmt_money(float(data.get("deuda") or 0.0))),
        ("Proximo vencimiento", data.get("proximo_vencimiento") or "Sin contratos activos"),
        ("Pagado historico", _fmt_money(float(data.get("pagado_total") or 0.0))),
        ("Detalle contratos", contratos_txt),
        ("Ultimos pagos", pagos_txt),
    ]
    _generar_comprobante_pdf(
        path,
        "Estado de cuenta",
        lineas,
        subtitulo=(_config_get("empresa_nombre", "") or "").strip() or None,
    )
    return path


def _mostrar_resultado_comprobante(parent, titulo, mensaje, path=None):
    path_txt = str(path or "").strip()
    if not path_txt:
        QMessageBox.information(parent, titulo, mensaje)
        return

    box = QMessageBox(parent)
    box.setWindowTitle(titulo)
    box.setIcon(QMessageBox.Information)
    box.setText(mensaje)
    btn_abrir = box.addButton("Abrir comprobante", QMessageBox.ActionRole)
    btn_abrir.clicked.connect(
        lambda: (
            None
            if _abrir_archivo_local(path_txt)
            else QMessageBox.warning(
                parent,
                titulo,
                "No se pudo abrir el comprobante automaticamente.\n"
                f"Revisa esta ubicacion:\n{Path(path_txt).resolve()}",
            )
        )
    )
    box.addButton(QMessageBox.Ok)
    box.exec()


def _eliminar_contrato_definitivo(id_contrato):
    if not id_contrato:
        return {"ok": False, "pagos": 0, "id_espacio": None}
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id_espacio FROM cochera_contratos WHERE id_contrato = ?",
            (id_contrato,),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "pagos": 0, "id_espacio": None}

        id_espacio = row["id_espacio"]
        cur.execute(
            "SELECT COUNT(*) AS cantidad FROM pagos_cochera WHERE id_contrato = ?",
            (id_contrato,),
        )
        row_pagos = cur.fetchone()
        pagos = int((row_pagos["cantidad"] if row_pagos else 0) or 0)

        if pagos > 0:
            cur.execute(
                "DELETE FROM pagos_cochera WHERE id_contrato = ?",
                (id_contrato,),
            )
        cur.execute(
            "DELETE FROM cochera_contratos WHERE id_contrato = ?",
            (id_contrato,),
        )
        if id_espacio:
            cur.execute(
                "UPDATE espacios SET id_cliente = NULL WHERE id_espacio = ?",
                (id_espacio,),
            )
        conn.commit()
        return {"ok": True, "pagos": pagos, "id_espacio": id_espacio}
    finally:
        if conn:
            conn.close()


def _emitir_comprobante_estacionamiento(
    patente,
    espacio,
    dt_ingreso,
    dt_salida,
    tarifa_hora,
    horas_cobradas,
    total,
    metodo,
    movimiento_id=None,
):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = str(movimiento_id or "").strip() or (patente or "SIN_PATENTE")
    base = "".join(ch for ch in base if ch.isalnum() or ch in ("-", "_")).strip("_-")
    if not base:
        base = "mov"
    path = _comprobantes_dir() / f"est_{base}_{ts}.pdf"

    lineas = [
        ("Tipo", "Estacionamiento"),
        ("Movimiento ID", movimiento_id or ""),
        ("Patente", patente or ""),
        ("Espacio", espacio or ""),
        ("Ingreso", dt_ingreso.strftime("%d/%m/%Y %H:%M:%S") if dt_ingreso else ""),
        ("Salida", dt_salida.strftime("%d/%m/%Y %H:%M:%S") if dt_salida else ""),
        ("Tarifa por hora", _fmt_money(float(tarifa_hora or 0.0))),
        ("Horas cobradas", horas_cobradas),
        ("Monto", _fmt_money(float(total or 0.0))),
        ("Metodo", metodo or ""),
        ("Fecha emision", datetime.now().strftime("%d/%m/%Y %H:%M")),
    ]
    _generar_comprobante_pdf(path, "Comprobante de estacionamiento", lineas)
    return path


def _emitir_ticket_estacionamiento(
    evento,
    patente,
    espacio,
    dt_ingreso,
    dt_salida=None,
    tarifa_hora=None,
    horas_cobradas=None,
    total=None,
    metodo=None,
    tipo_vehiculo=None,
    movimiento_id=None,
):
    evento_txt = (evento or "").strip().upper() or "MOV"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = str(movimiento_id or "").strip() or (patente or "SIN_PATENTE")
    base = "".join(ch for ch in base if ch.isalnum() or ch in ("-", "_")).strip("_-")
    if not base:
        base = "mov"
    if evento_txt == "SALIDA":
        path = _tickets_salida_dir() / f"ticket_est_salida_{base}_{ts}.pdf"
    else:
        path = _comprobantes_dir() / f"ticket_est_{evento_txt.lower()}_{base}_{ts}.pdf"

    nombre_local = (_config_get("empresa_nombre", "") or "").strip()
    direccion_local = (_config_get("empresa_direccion", "") or "").strip()
    telefono_local = (_config_get("empresa_telefono", "") or "").strip()

    lineas = [
        ("Patente", patente or ""),
        ("Espacio", espacio or ""),
        ("Tipo vehiculo", _texto_tipo_vehiculo(tipo_vehiculo)),
        ("Ingreso", dt_ingreso.strftime("%d/%m/%Y %H:%M:%S") if dt_ingreso else ""),
    ]
    if dt_salida:
        lineas.append(("Salida", dt_salida.strftime("%d/%m/%Y %H:%M:%S")))
    if tarifa_hora is not None:
        lineas.append(("Tarifa por hora", _fmt_money(float(tarifa_hora or 0.0))))
    if horas_cobradas is not None:
        lineas.append(("Horas cobradas", horas_cobradas))
    if total is not None:
        lineas.append(("Total", _fmt_money(float(total or 0.0))))
    if metodo:
        lineas.append(("Metodo", metodo))
    if direccion_local:
        lineas.append(("Direccion", direccion_local))
    if telefono_local:
        lineas.append(("Telefono", telefono_local))

    _generar_ticket_pdf(
        path,
        "Ticket de estacionamiento",
        lineas,
        ancho_mm=80.0,
        subtitulo=nombre_local or None,
    )
    return path


def _emitir_ticket_estacionamiento_seguro(**kwargs):
    try:
        path = Path(_emitir_ticket_estacionamiento(**kwargs)).resolve()
        if not path.exists() or not path.is_file():
            return None, "No se encontro el archivo del ticket generado."
        if path.stat().st_size <= 0:
            return None, "El ticket se genero vacio."
        return str(path), ""
    except Exception as exc:
        return None, str(exc)


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.usuario = None
        self.rol = None

        self.setWindowTitle("Iniciar sesion")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        titulo = QLabel("Acceso al sistema")
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)

        form = QFormLayout()
        self.input_usuario = QLineEdit()
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        form.addRow("Usuario", self.input_usuario)
        form.addRow("Contrasena", self.input_password)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_ingresar = QPushButton("Ingresar")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_ingresar.setAutoDefault(False)
        self.btn_ingresar.setDefault(False)
        self.btn_cancelar.setAutoDefault(False)
        self.btn_cancelar.setDefault(False)
        buttons.addWidget(self.btn_ingresar)
        buttons.addWidget(self.btn_cancelar)
        layout.addLayout(buttons)

        self.btn_ingresar.clicked.connect(self._intentar_login)
        self.btn_cancelar.clicked.connect(self.reject)
        self.input_usuario.returnPressed.connect(self.input_password.setFocus)
        self.input_password.returnPressed.connect(self._intentar_login)
        self.input_usuario.setFocus()

    def _intentar_login(self):
        usuario = self.input_usuario.text().strip()
        password = self.input_password.text()

        if not usuario or not password:
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Completa usuario y contrasena.",
            )
            return

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT usuario, password, rol, activo FROM usuarios WHERE usuario = ?",
                (usuario,),
            )
            row = cur.fetchone()
            if not row or row["activo"] != 1 or row["password"] != password:
                QMessageBox.warning(
                    self,
                    "Acceso denegado",
                    "Usuario o contrasena incorrectos.",
                )
                return

            self.usuario = row["usuario"]
            self.rol = row["rol"]
            self.accept()
        except sqlite3.Error:
            _mostrar_error(
                self,
                "Error de base de datos",
                "No se pudo validar el usuario.",
            )
        finally:
            if conn:
                conn.close()


class FirstUserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.usuario = None
        self.rol = "DUENO"

        self.setWindowTitle("Crear primer administrador")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        titulo = QLabel("Crear primer usuario administrador")
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)

        form = QFormLayout()
        self.input_usuario = QLineEdit()
        self.input_usuario.setMaxLength(16)
        self.input_usuario.setToolTip("El usuario debe tener entre 3 y 16 caracteres.")
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.setMaxLength(16)
        self.input_password.setToolTip("La contrasena debe tener entre 6 y 16 caracteres.")
        self.input_password2 = QLineEdit()
        self.input_password2.setEchoMode(QLineEdit.Password)
        self.input_password2.setMaxLength(16)
        form.addRow("Usuario", self.input_usuario)
        form.addRow("Contrasena", self.input_password)
        form.addRow("Repetir contrasena", self.input_password2)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_crear = QPushButton("Crear")
        self.btn_cancelar = QPushButton("Cancelar")
        buttons.addWidget(self.btn_crear)
        buttons.addWidget(self.btn_cancelar)
        layout.addLayout(buttons)

        self.btn_crear.clicked.connect(self._crear_usuario)
        self.btn_cancelar.clicked.connect(self.reject)
        _instalar_enter_navegacion(
            self,
            {
                self.input_usuario: self.input_password,
                self.input_password: self.input_password2,
                self.input_password2: self._crear_usuario,
            },
        )

    def _crear_usuario(self):
        usuario = self.input_usuario.text().strip()
        password = self.input_password.text()
        password2 = self.input_password2.text()

        if not usuario:
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Completa el nombre de usuario del administrador.",
            )
            return
        if not _usuario_longitud_valida(usuario):
            QMessageBox.warning(
                self,
                "Usuario",
                "El nombre de usuario debe tener entre 3 y 16 caracteres.",
            )
            return
        if not password:
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Completa la contrasena del administrador.",
            )
            return
        if not _password_longitud_valida(password):
            QMessageBox.warning(
                self,
                "Contrasena",
                "La contrasena debe tener entre 6 y 16 caracteres.",
            )
            return
        if not password2:
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Repite la contrasena para confirmar el primer usuario.",
            )
            return
        if password != password2:
            QMessageBox.warning(self, "Contrasena", "Las contrasenas no coinciden.")
            return

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO usuarios (usuario, password, rol, activo) VALUES (?, ?, 'DUENO', 1)",
                (usuario, password),
            )
            conn.commit()
            self.usuario = usuario
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self,
                "Usuario existente",
                "Ese usuario ya existe. Elige otro.",
            )
        except sqlite3.Error:
            _mostrar_error(
                self,
                "Error de base de datos",
                "No se pudo crear el usuario.",
            )
        finally:
            if conn:
                conn.close()


class UsuariosDialog(QDialog):
    def __init__(self, parent=None, usuario_actual=None):
        super().__init__(parent)
        self.usuario_actual = usuario_actual
        self.setWindowTitle("Usuarios")
        self.setMinimumWidth(560)

        layout = QHBoxLayout(self)

        panel_lista = QVBoxLayout()
        self.lista = QListWidget()
        panel_lista.addWidget(self.lista)

        acciones = QHBoxLayout()
        self.btn_activar = QPushButton("Activar")
        self.btn_desactivar = QPushButton("Desactivar")
        self.btn_eliminar = QPushButton("Eliminar")
        acciones.addWidget(self.btn_activar)
        acciones.addWidget(self.btn_desactivar)
        acciones.addWidget(self.btn_eliminar)
        panel_lista.addLayout(acciones)

        layout.addLayout(panel_lista, 2)

        panel_form = QVBoxLayout()
        form = QFormLayout()
        self.input_usuario = QLineEdit()
        self.input_usuario.setMaxLength(16)
        self.input_usuario.setToolTip("El usuario debe tener entre 3 y 16 caracteres.")
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password.setMaxLength(16)
        self.input_password.setToolTip("La contrasena debe tener entre 6 y 16 caracteres.")
        self.input_password2 = QLineEdit()
        self.input_password2.setEchoMode(QLineEdit.Password)
        self.input_password2.setMaxLength(16)
        form.addRow("Usuario", self.input_usuario)
        form.addRow("Contrasena", self.input_password)
        form.addRow("Repetir contrasena", self.input_password2)
        panel_form.addLayout(form)

        self.btn_crear = QPushButton("Crear operador")
        panel_form.addWidget(self.btn_crear)

        panel_form.addSpacing(12)

        form_pass = QFormLayout()
        self.input_new_password = QLineEdit()
        self.input_new_password.setEchoMode(QLineEdit.Password)
        self.input_new_password.setMaxLength(16)
        self.input_new_password.setToolTip("La contrasena debe tener entre 6 y 16 caracteres.")
        self.input_new_password2 = QLineEdit()
        self.input_new_password2.setEchoMode(QLineEdit.Password)
        self.input_new_password2.setMaxLength(16)
        form_pass.addRow("Nueva contrasena", self.input_new_password)
        form_pass.addRow("Repetir contrasena", self.input_new_password2)
        panel_form.addLayout(form_pass)

        self.btn_cambiar_pass = QPushButton("Cambiar contrasena")
        panel_form.addWidget(self.btn_cambiar_pass)
        panel_form.addStretch(1)

        layout.addLayout(panel_form, 3)

        self.btn_crear.clicked.connect(self._crear_operador)
        self.btn_cambiar_pass.clicked.connect(self._cambiar_password)
        self.btn_activar.clicked.connect(lambda: self._cambiar_activo(1))
        self.btn_desactivar.clicked.connect(lambda: self._cambiar_activo(0))
        self.btn_eliminar.clicked.connect(self._eliminar_usuario)
        _instalar_enter_navegacion(
            self,
            {
                self.input_usuario: self.input_password,
                self.input_password: self.input_password2,
                self.input_password2: self._crear_operador,
                self.input_new_password: self.input_new_password2,
                self.input_new_password2: self._cambiar_password,
            },
        )

        self._cargar_usuarios()

    def _cargar_usuarios(self):
        self.lista.clear()
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT id_usuario, usuario, rol, activo FROM usuarios ORDER BY usuario"
            )
            for row in cur.fetchall():
                estado = "activo" if row["activo"] == 1 else "inactivo"
                texto = f'{row["usuario"]} ({row["rol"]}) - {estado}'
                item = QListWidgetItem(texto)
                item.setData(Qt.UserRole, row["id_usuario"])
                item.setData(Qt.UserRole + 1, row["rol"])
                item.setData(Qt.UserRole + 2, row["usuario"])
                self.lista.addItem(item)
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo cargar usuarios.")
        finally:
            if conn:
                conn.close()

    def _crear_operador(self):
        usuario = self.input_usuario.text().strip()
        password = self.input_password.text()
        password2 = self.input_password2.text()

        if not usuario:
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Completa el nombre de usuario del operador.",
            )
            return False
        if not _usuario_longitud_valida(usuario):
            QMessageBox.warning(
                self,
                "Usuario",
                "El nombre de usuario debe tener entre 3 y 16 caracteres.",
            )
            return False
        if not password:
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Completa la contrasena del operador.",
            )
            return False
        if not _password_longitud_valida(password):
            QMessageBox.warning(
                self,
                "Contrasena",
                "La contrasena debe tener entre 6 y 16 caracteres.",
            )
            return False
        if not password2:
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Repite la contrasena para confirmar el operador.",
            )
            return False
        if password != password2:
            QMessageBox.warning(self, "Contrasena", "Las contrasenas no coinciden.")
            return False

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO usuarios (usuario, password, rol, activo) VALUES (?, ?, 'OPERADOR', 1)",
                (usuario, password),
            )
            conn.commit()
            _auditar(self, "Usuario creado", f"{usuario} (OPERADOR)")
            self.input_usuario.clear()
            self.input_password.clear()
            self.input_password2.clear()
            self._cargar_usuarios()
            return True
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Usuario", "Ese usuario ya existe.")
            return False
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo crear el usuario.")
            return False
        finally:
            if conn:
                conn.close()

    def _cambiar_activo(self, activo):
        item = self.lista.currentItem()
        if not item:
            QMessageBox.warning(
                self,
                "Usuario",
                "Selecciona un usuario de la lista antes de activarlo o desactivarlo.",
            )
            return
        rol = item.data(Qt.UserRole + 1)
        if rol == "DUENO":
            QMessageBox.warning(self, "Accion no permitida", "No puedes desactivar al DUENO.")
            return
        if self.usuario_actual and item.data(Qt.UserRole + 2) == self.usuario_actual:
            QMessageBox.warning(
                self,
                "Accion no permitida",
                "No puedes desactivar tu propio usuario.",
            )
            return

        user_id = item.data(Qt.UserRole)
        usuario_obj = item.data(Qt.UserRole + 2)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("UPDATE usuarios SET activo = ? WHERE id_usuario = ?", (activo, user_id))
            conn.commit()
            accion = "Usuario activado" if activo == 1 else "Usuario desactivado"
            _auditar(self, accion, str(usuario_obj))
            self._cargar_usuarios()
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo actualizar el usuario.")
        finally:
            if conn:
                conn.close()

    def _cambiar_password(self):
        item = self.lista.currentItem()
        if not item:
            QMessageBox.warning(self, "Usuario", "Selecciona un usuario.")
            return False

        rol = item.data(Qt.UserRole + 1)
        if rol == "DUENO":
            QMessageBox.warning(
                self,
                "Accion no permitida",
                "No puedes cambiar la contrasena del DUENO.",
            )
            return False

        password = self.input_new_password.text()
        password2 = self.input_new_password2.text()
        if not password:
            QMessageBox.warning(self, "Contrasena", "Completa la nueva contrasena.")
            return False
        if not _password_longitud_valida(password):
            QMessageBox.warning(
                self,
                "Contrasena",
                "La contrasena debe tener entre 6 y 16 caracteres.",
            )
            return False
        if not password2:
            QMessageBox.warning(
                self,
                "Contrasena",
                "Repite la nueva contrasena para confirmarla.",
            )
            return False
        if password != password2:
            QMessageBox.warning(self, "Contrasena", "Las contrasenas no coinciden.")
            return False

        user_id = item.data(Qt.UserRole)
        usuario_obj = item.data(Qt.UserRole + 2)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE usuarios SET password = ? WHERE id_usuario = ?",
                (password, user_id),
            )
            conn.commit()
            _auditar(self, "Password actualizado", str(usuario_obj))
            self.input_new_password.clear()
            self.input_new_password2.clear()
            QMessageBox.information(self, "Contrasena", "Contrasena actualizada.")
            return True
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo cambiar la contrasena.")
            return False
        finally:
            if conn:
                conn.close()

    def _hay_operador_pendiente(self):
        return bool(
            self.input_usuario.text().strip()
            or self.input_password.text()
            or self.input_password2.text()
        )

    def _hay_password_pendiente(self):
        return bool(
            self.input_new_password.text()
            or self.input_new_password2.text()
        )

    def _eliminar_usuario(self):
        item = self.lista.currentItem()
        if not item:
            QMessageBox.warning(self, "Usuario", "Selecciona un usuario.")
            return

        rol = item.data(Qt.UserRole + 1)
        if rol == "DUENO":
            QMessageBox.warning(
                self,
                "Accion no permitida",
                "No puedes eliminar al DUENO.",
            )
            return
        if self.usuario_actual and item.data(Qt.UserRole + 2) == self.usuario_actual:
            QMessageBox.warning(
                self,
                "Accion no permitida",
                "No puedes eliminar tu propio usuario.",
            )
            return

        confirmar = QMessageBox.question(
            self,
            "Eliminar usuario",
            "Esto eliminara al usuario definitivamente. Continuar?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirmar != QMessageBox.Yes:
            return

        user_id = item.data(Qt.UserRole)
        usuario_obj = item.data(Qt.UserRole + 2)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM usuarios WHERE id_usuario = ?", (user_id,))
            conn.commit()
            _auditar(self, "Usuario eliminado", str(usuario_obj))
            self._cargar_usuarios()
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo eliminar el usuario.")
        finally:
            if conn:
                conn.close()

    def closeEvent(self, event):
        if self._hay_operador_pendiente():
            respuesta = _confirmar_guardado_pendiente(
                self,
                "Hay un operador nuevo sin guardar.\nQuieres guardarlo antes de salir?",
            )
            if respuesta == QMessageBox.Cancel:
                event.ignore()
                return
            if respuesta == QMessageBox.Yes and not self._crear_operador():
                event.ignore()
                return

        if self._hay_password_pendiente():
            respuesta = _confirmar_guardado_pendiente(
                self,
                "Hay un cambio de contrasena sin guardar.\nQuieres guardarlo antes de salir?",
            )
            if respuesta == QMessageBox.Cancel:
                event.ignore()
                return
            if respuesta == QMessageBox.Yes and not self._cambiar_password():
                event.ignore()
                return

        event.accept()


class DatosTransferenciaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Datos de transferencia")
        self.setMinimumWidth(460)

        self._alias = (_config_get("empresa_alias", "") or "").strip()
        self._cbu = (_config_get("empresa_cbu", "") or "").strip()

        layout = QVBoxLayout(self)
        self.label_info = QLabel(
            "Comparte estos datos para cobros por transferencia.\n"
            "Si falta alguno, puedes configurarlo en Configuracion > General."
        )
        self.label_info.setWordWrap(True)
        layout.addWidget(self.label_info)

        form = QFormLayout()
        self.input_alias = QLineEdit(self._alias)
        self.input_alias.setReadOnly(True)
        self.input_cbu = QLineEdit(self._cbu)
        self.input_cbu.setReadOnly(True)
        form.addRow("Alias", self.input_alias)
        form.addRow("CBU", self.input_cbu)
        layout.addLayout(form)

        if not self._alias and not self._cbu:
            aviso = QLabel(
                "Todavia no hay alias ni CBU configurados para la cochera."
            )
            aviso.setWordWrap(True)
            layout.addWidget(aviso)

        acciones = QHBoxLayout()
        self.btn_copiar_alias = QPushButton("Copiar alias")
        self.btn_copiar_cbu = QPushButton("Copiar CBU")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_copiar_alias.setProperty("variant", "info")
        self.btn_copiar_cbu.setProperty("variant", "info")
        self.btn_cerrar.setProperty("variant", "neutral")
        self.btn_copiar_alias.setEnabled(bool(self._alias))
        self.btn_copiar_cbu.setEnabled(bool(self._cbu))
        acciones.addWidget(self.btn_copiar_alias)
        acciones.addWidget(self.btn_copiar_cbu)
        acciones.addStretch(1)
        acciones.addWidget(self.btn_cerrar)
        layout.addLayout(acciones)

        self.btn_copiar_alias.clicked.connect(
            lambda: self._copiar_texto(self._alias, "Alias")
        )
        self.btn_copiar_cbu.clicked.connect(lambda: self._copiar_texto(self._cbu, "CBU"))
        self.btn_cerrar.clicked.connect(self.accept)

    def _copiar_texto(self, texto, etiqueta):
        if not texto:
            QMessageBox.warning(
                self,
                "Transferencia",
                f"No hay {etiqueta.lower()} configurado para copiar.",
            )
            return
        QApplication.clipboard().setText(texto)
        QMessageBox.information(
            self,
            "Transferencia",
            f"{etiqueta} copiado al portapapeles.",
        )


class HistorialPagosContratoDialog(QDialog):
    def __init__(self, id_contrato, parent=None):
        super().__init__(parent)
        self.id_contrato = id_contrato
        self.setWindowTitle("Historial de pagos del contrato")
        self.setMinimumWidth(760)
        self.setMinimumHeight(420)

        layout = QVBoxLayout(self)
        self.label_resumen = QLabel("Contrato: -")
        self.label_resumen.setWordWrap(True)
        layout.addWidget(self.label_resumen)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Fecha", "Monto", "Metodo", "Usuario", "Referencia"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        acciones = QHBoxLayout()
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_actualizar.setProperty("variant", "neutral")
        self.btn_cerrar.setProperty("variant", "neutral")
        self.label_resumen.setToolTip(
            "Resumen rapido del contrato, la patente y el total pagado."
        )
        self.btn_actualizar.setToolTip(
            "Vuelve a consultar los pagos registrados para este contrato."
        )
        self.btn_cerrar.setToolTip("Cierra este historial de pagos.")
        acciones.addStretch(1)
        acciones.addWidget(self.btn_actualizar)
        acciones.addWidget(self.btn_cerrar)
        layout.addLayout(acciones)

        self.btn_actualizar.clicked.connect(self._cargar)
        self.btn_cerrar.clicked.connect(self.accept)
        self._cargar()

    def _cargar(self):
        self.table.setRowCount(0)
        detalle = svc_obtener_detalle_contrato(self.id_contrato) or {}
        conn = None
        pagos = []
        total = 0.0
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT fecha_pago, monto, metodo, COALESCE(usuario, '') AS usuario, "
                "COALESCE(ref_externa, '') AS ref_externa "
                "FROM pagos_cochera WHERE id_contrato = ? "
                "ORDER BY datetime(fecha_pago) DESC, id_pago DESC",
                (self.id_contrato,),
            )
            pagos = [dict(row) for row in cur.fetchall()]
        except sqlite3.Error:
            pagos = []
        finally:
            if conn:
                conn.close()

        for row in pagos:
            total += float(row.get("monto") or 0.0)
            r = self.table.rowCount()
            self.table.insertRow(r)
            fecha_pago = _parse_datetime_local(row.get("fecha_pago"))
            fecha_txt = (
                fecha_pago.strftime("%d/%m/%Y %H:%M")
                if fecha_pago
                else str(row.get("fecha_pago") or "-")
            )
            self.table.setItem(r, 0, QTableWidgetItem(fecha_txt))
            self.table.setItem(
                r, 1, QTableWidgetItem(_fmt_money(float(row.get("monto") or 0.0)))
            )
            self.table.setItem(r, 2, QTableWidgetItem(row.get("metodo") or ""))
            self.table.setItem(r, 3, QTableWidgetItem(row.get("usuario") or ""))
            self.table.setItem(r, 4, QTableWidgetItem(row.get("ref_externa") or ""))

        if not pagos:
            self.table.insertRow(0)
            item = QTableWidgetItem(
                "Todavia no hay pagos registrados para este contrato."
            )
            item.setFlags(Qt.NoItemFlags)
            self.table.setSpan(0, 0, 1, self.table.columnCount())
            self.table.setItem(0, 0, item)

        self.label_resumen.setText(
            (
                f"Contrato {self.id_contrato} | "
                f"Cliente: {detalle.get('nombre') or '-'} | "
                f"Patente: {detalle.get('patente') or '-'} | "
                f"Espacio: {detalle.get('codigo') or '-'} | "
                f"Pagos: {len(pagos)} | Total: {_fmt_money(total)}"
            )
        )


class IngresoRapidoEstDialog(QDialog):
    def __init__(self, tipos_disponibles, parent=None):
        super().__init__(parent)
        self._atajos = []
        self.setWindowTitle("Modo sencillo - Ingreso")
        self.setMinimumWidth(520)
        self.setStyleSheet(_estilo_modo_sencillo())

        layout = QVBoxLayout(self)

        titulo = QLabel("Ingreso rapido")
        titulo.setObjectName("modo_sencillo_titulo")
        titulo_font = QFont()
        titulo_font.setPointSize(_ui_escalar_pt(16, minimo=16))
        titulo_font.setBold(True)
        titulo.setFont(titulo_font)
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)

        info = QLabel(
            "Completa solo lo necesario para registrar un ingreso en estacionamiento."
        )
        info.setObjectName("modo_sencillo_info")
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)

        form = QFormLayout()
        self.input_patente = QLineEdit()
        self.input_patente.setPlaceholderText("Patente")
        self.input_patente.setMaxLength(10)
        self.input_patente.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(r"[A-Za-z0-9\\s]{0,10}"),
                self.input_patente,
            )
        )
        self.input_espacio = QLineEdit()
        self.input_espacio.setPlaceholderText("Automatico si lo dejas vacio")
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItem("Seleccionar tipo...", "")
        for texto, valor in tipos_disponibles or [("Auto", "AUTO")]:
            self.combo_tipo.addItem(texto, valor)
        self.combo_tipo.setCurrentIndex(0)
        for widget in (
            self.input_patente,
            self.input_espacio,
            self.combo_tipo,
        ):
            widget.setMinimumHeight(40)
        label_patente = QLabel("Patente (F4)")
        label_patente.setBuddy(self.input_patente)
        label_espacio = QLabel("Espacio (opcional)")
        label_tipo = QLabel("Tipo vehiculo")
        for label in (label_patente, label_espacio, label_tipo):
            label.setObjectName("modo_sencillo_label")
        form.addRow(label_patente, self.input_patente)
        form.addRow(label_espacio, self.input_espacio)
        form.addRow(label_tipo, self.combo_tipo)
        layout.addLayout(form)

        botones = QHBoxLayout()
        self.btn_confirmar = QPushButton("Registrar ingreso")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_confirmar.setProperty("variant", "success")
        self.btn_cancelar.setProperty("variant", "neutral")
        self.btn_confirmar.setToolTip(
            "Registra el ingreso rapido del vehiculo con estos datos."
        )
        self.btn_cancelar.setToolTip("Cancela este ingreso rapido y vuelve atras.")
        self.btn_confirmar.setMinimumHeight(48)
        self.btn_cancelar.setMinimumHeight(48)
        botones.addWidget(self.btn_confirmar)
        botones.addWidget(self.btn_cancelar)
        layout.addLayout(botones)

        self.btn_confirmar.clicked.connect(self.accept)
        self.btn_cancelar.clicked.connect(self.reject)
        _instalar_enter_navegacion(
            self,
            {
                self.input_patente: self.input_espacio,
                self.input_espacio: self.combo_tipo,
                self.combo_tipo: self.accept,
            },
        )
        self._crear_atajos()

    def _crear_atajos(self):
        sc = QShortcut(QKeySequence("F4"), self)
        sc.setContext(Qt.WindowShortcut)
        sc.activated.connect(self._enfocar_patente)
        self._atajos.append(sc)

    def _enfocar_patente(self):
        self.input_patente.setFocus()
        self.input_patente.selectAll()

    def _tipo_vehiculo_seleccionado(self):
        valor = self.combo_tipo.currentData()
        if valor is None:
            valor = self.combo_tipo.currentText()
        if not str(valor or "").strip():
            return ""
        return _normalizar_tipo_vehiculo(valor)

    def accept(self):
        patente = _normalizar_patente(self.input_patente.text())
        if not patente:
            QMessageBox.warning(
                self,
                "Ingreso rapido",
                "Completa la patente antes de registrar el ingreso.",
            )
            self.input_patente.setFocus()
            return
        if not self._tipo_vehiculo_seleccionado():
            QMessageBox.warning(
                self,
                "Ingreso rapido",
                "Selecciona un tipo de vehiculo antes de registrar el ingreso.",
            )
            self.combo_tipo.setFocus()
            return
        self.input_patente.setText(_formatear_patente(patente))
        super().accept()

    def get_data(self):
        return {
            "patente": self.input_patente.text().strip(),
            "espacio": self.input_espacio.text().strip().upper(),
            "tipo_vehiculo": self._tipo_vehiculo_seleccionado(),
        }


class CalcularVueltoDialog(QDialog):
    def __init__(self, total, parent=None):
        super().__init__(parent)
        self._total = round(float(total or 0.0), 2)
        self.setWindowTitle("Calcular vuelto")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        titulo = QLabel("Calcular vuelto")
        fuente = titulo.font()
        fuente.setPointSize(_ui_escalar_pt(14, minimo=14))
        fuente.setBold(True)
        titulo.setFont(fuente)
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)

        info = QLabel(
            "Ingresa el efectivo recibido para calcular cuanto debes devolver."
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)

        form = QFormLayout()
        self.label_total = QLabel(_fmt_money(self._total))
        self.input_efectivo = QDoubleSpinBox()
        self.input_efectivo.setDecimals(2)
        self.input_efectivo.setRange(0.0, 999999999.0)
        self.input_efectivo.setSingleStep(100.0)
        _configurar_spinbox_numerico(self.input_efectivo)
        self.label_resultado = QLabel("Ingresa el efectivo recibido.")
        self.label_resultado.setWordWrap(True)
        form.addRow("Total a cobrar", self.label_total)
        form.addRow("Efectivo recibido", self.input_efectivo)
        form.addRow("Resultado", self.label_resultado)
        layout.addLayout(form)

        botones = QHBoxLayout()
        self.btn_calcular = QPushButton("Calcular vuelto")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_calcular.setProperty("variant", "success")
        self.btn_cerrar.setProperty("variant", "neutral")
        self.btn_calcular.setToolTip(
            "Calcula si el pago alcanza y cuanto debes devolver de vuelto."
        )
        self.btn_cerrar.setToolTip("Cierra esta ventana de calculo.")
        botones.addWidget(self.btn_calcular)
        botones.addWidget(self.btn_cerrar)
        layout.addLayout(botones)

        self.btn_calcular.clicked.connect(self._actualizar_resultado)
        self.btn_cerrar.clicked.connect(self.accept)
        self.input_efectivo.valueChanged.connect(self._actualizar_resultado)
        _instalar_enter_navegacion(
            self,
            {
                self.input_efectivo: self._actualizar_resultado,
            },
        )

    def _actualizar_resultado(self):
        recibido = round(float(self.input_efectivo.value() or 0.0), 2)
        if recibido <= 0:
            self.label_resultado.setText("Ingresa el efectivo recibido.")
            return
        diferencia = round(recibido - self._total, 2)
        if diferencia < 0:
            self.label_resultado.setText(
                f"Faltan $ {_fmt_numero_local(abs(diferencia))} para completar el pago."
            )
        elif diferencia == 0:
            self.label_resultado.setText("Pago exacto. No hay que dar vuelto.")
        else:
            self.label_resultado.setText(
                f"Debes dar $ {_fmt_numero_local(diferencia)} de vuelto."
            )


class ActivosEstacionamientoDialog(QDialog):
    def __init__(self, filas, permitir_salida=False, metodos_disponibles=None, parent=None):
        super().__init__(parent)
        self._permitir_salida = bool(permitir_salida)
        self._filas_cache = list(filas or [])
        self.setWindowTitle(
            "Modo sencillo - Salida" if self._permitir_salida else "Modo sencillo - Vehiculos activos"
        )
        self.setMinimumWidth(620)
        self.setMinimumHeight(420)
        self.setStyleSheet(_estilo_modo_sencillo())

        layout = QVBoxLayout(self)
        self.label_info = QLabel("")
        self.label_info.setObjectName("modo_sencillo_estado")
        self.label_info.setWordWrap(True)
        layout.addWidget(self.label_info)

        self.lista = QListWidget()
        self.lista.setAlternatingRowColors(True)
        layout.addWidget(self.lista)

        botones = QHBoxLayout()
        self.btn_principal = QPushButton(
            "Registrar salida" if self._permitir_salida else "Actualizar"
        )
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_principal.setProperty("variant", "warning" if self._permitir_salida else "neutral")
        self.btn_cerrar.setProperty("variant", "neutral")
        self.btn_cerrar.setToolTip("Cierra esta ventana y vuelve al modo sencillo.")
        botones.addWidget(self.btn_principal)
        botones.addStretch(1)
        botones.addWidget(self.btn_cerrar)
        layout.addLayout(botones)

        self.btn_principal.clicked.connect(self._accion_principal)
        self.btn_cerrar.clicked.connect(self.reject)
        self.lista.itemDoubleClicked.connect(self._doble_click)
        self._cargar(self._filas_cache)

    def _cargar(self, filas):
        self.lista.clear()
        self.label_info.setText(
            (
                "Selecciona un vehiculo activo para registrar su salida."
                if self._permitir_salida
                else "Aqui ves los vehiculos que siguen dentro del estacionamiento."
            )
        )
        for row in filas:
            patente = _formatear_patente(row.get("patente") or "")
            codigo = (row.get("codigo") or "").strip() or "-"
            ingreso = _fmt_fecha_hora_local(row.get("fecha_ingreso"))
            texto = f"{patente} | {codigo} | {ingreso}"
            item = QListWidgetItem(texto)
            item.setData(Qt.UserRole, _normalizar_patente(row.get("patente") or ""))
            self.lista.addItem(item)
        if self.lista.count() == 0:
            vacio = QListWidgetItem("No hay vehiculos activos en este momento.")
            vacio.setFlags(Qt.NoItemFlags)
            self.lista.addItem(vacio)
            self.btn_principal.setEnabled(False)
            self.btn_principal.setToolTip(
                "No hay vehiculos activos para operar desde esta ventana."
            )
        else:
            self.btn_principal.setEnabled(True)
            self.btn_principal.setToolTip(
                "Selecciona un vehiculo activo y registrale la salida."
                if self._permitir_salida
                else "Vuelve a consultar los vehiculos que siguen dentro del estacionamiento."
            )

    def _doble_click(self, item):
        if self._permitir_salida and item and item.data(Qt.UserRole):
            self.accept()

    def _accion_principal(self):
        if self._permitir_salida:
            if not self.patente_seleccionada():
                QMessageBox.warning(
                    self,
                    "Salida",
                    "Selecciona un vehiculo activo para registrar la salida.",
                )
                return
            self.accept()
            return
        parent = self.parent()
        if parent is not None and hasattr(parent, "_filas_activas"):
            try:
                self._filas_cache = list(parent._filas_activas() or [])
            except Exception:
                self._filas_cache = []
        self._cargar(self._filas_cache)
        QMessageBox.information(
            self,
            "Vehiculos activos",
            "La lista de vehiculos activos se actualizo.",
        )

    def patente_seleccionada(self):
        item = self.lista.currentItem()
        if not item:
            return ""
        return item.data(Qt.UserRole) or ""


class ModoSencilloEstacionamientoDialog(QDialog):
    def __init__(self, ventana_principal, parent=None):
        super().__init__(None)
        self.ventana = ventana_principal
        self._atajos = []
        self.setWindowTitle("Modo sencillo - Estacionamiento")
        self.setWindowFlag(Qt.Window, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMinimumSize(760, 420)
        self.resize(860, 460)
        self.setStyleSheet(_estilo_modo_sencillo())

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        titulo = QLabel("Modo sencillo - Estacionamiento")
        titulo.setObjectName("modo_sencillo_titulo")
        titulo_font = QFont()
        titulo_font.setPointSize(_ui_escalar_pt(18, minimo=18))
        titulo_font.setBold(True)
        titulo.setFont(titulo_font)
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)

        self.label_fecha_hora = QLabel("")
        self.label_fecha_hora.setObjectName("modo_sencillo_fecha_hora")
        self.label_fecha_hora.setAlignment(Qt.AlignCenter)
        self.label_fecha_hora.setToolTip(
            "Fecha y hora actual del equipo usada como referencia en el modo sencillo."
        )
        layout.addWidget(self.label_fecha_hora)

        self.label_estado = QLabel("")
        self.label_estado.setObjectName("modo_sencillo_estado")
        self.label_estado.setAlignment(Qt.AlignCenter)
        self.label_estado.setWordWrap(True)
        layout.addWidget(self.label_estado)

        botones = QGridLayout()
        botones.setHorizontalSpacing(12)
        botones.setVerticalSpacing(12)
        self.btn_ingreso = QPushButton("Ingreso rapido")
        self.btn_salida = QPushButton("Salida rapida")
        self.btn_activos = QPushButton("Ver vehiculos activos")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_ingreso.setProperty("variant", "success")
        self.btn_salida.setProperty("variant", "warning")
        self.btn_activos.setProperty("variant", "info")
        self.btn_cerrar.setProperty("variant", "neutral")
        self.btn_ingreso.setToolTip(
            "Abre el formulario simple para registrar un ingreso. Atajo: Ctrl+Q."
        )
        self.btn_salida.setToolTip(
            "Muestra los vehiculos activos para elegir uno y registrar la salida. Atajo: Ctrl+W."
        )
        self.btn_activos.setToolTip(
            "Muestra la lista actual de vehiculos que siguen dentro del estacionamiento. Atajo: Ctrl+E."
        )
        self.btn_cerrar.setToolTip(
            "Cierra el modo sencillo y vuelve a la ventana principal."
        )
        for btn in (self.btn_ingreso, self.btn_salida, self.btn_activos, self.btn_cerrar):
            fuente = btn.font()
            fuente.setPointSize(_ui_escalar_pt(15, minimo=15))
            fuente.setBold(True)
            btn.setFont(fuente)
            btn.setMinimumHeight(92)
        botones.addWidget(self.btn_ingreso, 0, 0)
        botones.addWidget(self.btn_salida, 0, 1)
        botones.addWidget(self.btn_activos, 1, 0)
        botones.addWidget(self.btn_cerrar, 1, 1)
        layout.addLayout(botones)

        ayuda = QLabel(
            "Este modo trabaja solo con estacionamiento y deja visibles solo las acciones rapidas mas usadas."
            "\nAtajos: Ctrl+Q ingreso, Ctrl+W salida, Ctrl+E vehiculos activos."
        )
        ayuda.setObjectName("modo_sencillo_info")
        ayuda.setWordWrap(True)
        ayuda.setAlignment(Qt.AlignCenter)
        layout.addWidget(ayuda)

        self.btn_ingreso.clicked.connect(self._abrir_ingreso)
        self.btn_salida.clicked.connect(self._abrir_salida)
        self.btn_activos.clicked.connect(self._ver_activos)
        self.btn_cerrar.clicked.connect(self.close)
        self._crear_atajos()
        self._timer_fecha_hora = QTimer(self)
        self._timer_fecha_hora.setInterval(1000)
        self._timer_fecha_hora.timeout.connect(self._actualizar_fecha_hora)
        self._timer_fecha_hora.start()

        self._actualizar_fecha_hora()
        self._refrescar_estado()

    def _crear_atajos(self):
        for secuencia, accion in (
            ("Ctrl+Q", self._abrir_ingreso),
            ("Ctrl+W", self._abrir_salida),
            ("Ctrl+E", self._ver_activos),
            ("Escape", self.close),
        ):
            sc = QShortcut(QKeySequence(secuencia), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(accion)
            self._atajos.append(sc)

    def _filas_activas(self):
        try:
            self.ventana._actualizar_activos_est()
        except Exception:
            pass
        return list(getattr(self.ventana, "_activos_est_cache", []) or [])

    def _actualizar_fecha_hora(self):
        # Esto sale de la hora de la PC, asi en el modo sencillo vemos una referencia real y no algo inventado.
        actual = QDateTime.currentDateTime()
        texto = _LOCALE_ES_AR.toString(actual, "dddd dd/MM/yyyy  |  HH:mm:ss")
        self.label_fecha_hora.setText(texto[:1].upper() + texto[1:] if texto else "")

    def _refrescar_estado(self):
        filas = self._filas_activas()
        self.label_estado.setText(
            f"Vehiculos activos ahora: {len(filas)}"
        )

    def _metodos_disponibles(self):
        combo = getattr(self.ventana.ui, "combo_metodo_est", None)
        if combo is None:
            return ["Efectivo"]
        return [combo.itemText(i) for i in range(combo.count()) if combo.itemText(i).strip()]

    def _aplicar_datos_ingreso_en_principal(self, data):
        self.ventana.ui.input_patente_est.setText(_formatear_patente(data.get("patente") or ""))
        self.ventana.ui.input_espacio_est.setText((data.get("espacio") or "").strip().upper())
        combo_tipo = getattr(self.ventana.ui, "combo_tipo_vehiculo_est", None)
        if combo_tipo is not None:
            idx_tipo = combo_tipo.findData(_normalizar_tipo_vehiculo(data.get("tipo_vehiculo")))
            if idx_tipo >= 0:
                combo_tipo.setCurrentIndex(idx_tipo)

    def _abrir_ingreso(self):
        tipos = _tipos_vehiculo_config_estacionamiento()
        if not tipos:
            QMessageBox.warning(
                self,
                "Modo sencillo",
                "No hay tipos de vehiculo habilitados para estacionamiento.\n"
                "Activalos en Configuracion > Sistema.",
            )
            return
        dlg = IngresoRapidoEstDialog(tipos, self)
        if dlg.exec() != QDialog.Accepted:
            return
        if not self.ventana._abrir_menu_estacionamiento(popup_parent=self):
            return
        self._aplicar_datos_ingreso_en_principal(dlg.get_data())
        self.ventana._registrar_ingreso_est(popup_parent=self)
        self.raise_()
        self.activateWindow()
        self._refrescar_estado()

    def _abrir_salida(self):
        filas = self._filas_activas()
        if not filas:
            QMessageBox.information(
                self,
                "Modo sencillo",
                "No hay vehiculos activos para registrar una salida.",
            )
            self._refrescar_estado()
            return
        dlg = ActivosEstacionamientoDialog(
            filas,
            permitir_salida=True,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            self._refrescar_estado()
            return
        patente = dlg.patente_seleccionada()
        if not patente:
            return
        if not self.ventana._abrir_menu_estacionamiento(popup_parent=self):
            return
        self.ventana.ui.input_patente_est.setText(_formatear_patente_estacionamiento(patente))
        self.ventana._registrar_salida_est(popup_parent=self)
        self.raise_()
        self.activateWindow()
        self._refrescar_estado()

    def _ver_activos(self):
        filas = self._filas_activas()
        if not filas:
            QMessageBox.information(
                self,
                "Modo sencillo",
                "No hay vehiculos activos para mostrar en este momento.",
            )
            self._refrescar_estado()
            return
        dlg = ActivosEstacionamientoDialog(filas, permitir_salida=False, parent=self)
        dlg.exec()
        self._refrescar_estado()

    def closeEvent(self, event):
        try:
            self.ventana._restaurar_desde_modo_sencillo(self)
        finally:
            super().closeEvent(event)


class ContratosDialog(QDialog):
    def __init__(self, parent=None, rol=None):
        super().__init__(parent)
        self.rol = rol
        self._patente_preferida = ""
        self.setWindowTitle("Contratos de cochera")
        self.setMinimumWidth(1180)
        self.setMinimumHeight(720)
        self.resize(1260, 780)

        layout = QVBoxLayout(self)

        fila_buscar = QHBoxLayout()
        fila_buscar.addWidget(QLabel("Buscar"))
        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText(
            "Cliente, DNI, patente, modelo, espacio o estado"
        )
        fila_buscar.addWidget(self.input_buscar)
        layout.addLayout(fila_buscar)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Cliente",
                "DNI",
                "Patente",
                "Modelo",
                "Espacio",
                "Entrada",
                "Vencimiento",
                "Monto",
                "Activo",
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        form = QFormLayout()
        self.input_dni = QLineEdit()
        self.input_dni.setMaxLength(10)
        self.input_dni.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(r"[0-9.]{0,10}"),
                self.input_dni,
            )
        )
        self.input_patente = QLineEdit()
        self.input_patente.setReadOnly(True)
        self.input_patente.setPlaceholderText("Patente del cliente/contrato")
        self.input_modelo = QLineEdit()
        self.input_modelo.setReadOnly(True)
        self.input_modelo.setPlaceholderText("Modelo del vehiculo")
        self.input_tipo_vehiculo = QLineEdit()
        self.input_tipo_vehiculo.setReadOnly(True)
        self.input_tipo_vehiculo.setPlaceholderText("Tipo del vehiculo")
        self.input_espacio = QLineEdit()
        self.input_venc = QDateEdit()
        self.input_venc.setCalendarPopup(True)
        self.input_venc.setDate(QDate.currentDate().addMonths(1))
        self.input_monto = QDoubleSpinBox()
        self.input_monto.setDecimals(2)
        self.input_monto.setRange(0.0, 999999.0)
        self.input_monto.setSingleStep(100.0)
        _configurar_spinbox_numerico(self.input_monto)
        form.addRow("DNI cliente", self.input_dni)
        form.addRow("Patente", self.input_patente)
        form.addRow("Modelo", self.input_modelo)
        form.addRow("Tipo vehiculo", self.input_tipo_vehiculo)
        form.addRow("Espacio (codigo)", self.input_espacio)
        form.addRow("Vencimiento", self.input_venc)
        form.addRow("Monto mensual", self.input_monto)
        layout.addLayout(form)

        fila_botones = QHBoxLayout()
        fila_botones.setSpacing(18)
        col_izquierda = QVBoxLayout()
        col_centro_izquierda = QVBoxLayout()
        col_centro_derecha = QVBoxLayout()
        col_derecha = QVBoxLayout()
        self.btn_crear = QPushButton("Crear contrato")
        self.btn_historial = QPushButton("Historial")
        self.btn_transferencia = QPushButton("Transferencia")
        self.btn_whatsapp = QPushButton("Avisar vencimiento")
        self.btn_comprobante = QPushButton("Enviar comprobante")
        self.btn_historial_pagos = QPushButton("Historial pagos")
        self.btn_registrar_pago = QPushButton("Registro de pagos")
        self.btn_renovar_pago = QPushButton("Renovar pago")
        self.btn_baja = QPushButton("Dar de baja")
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_crear.setProperty("variant", "success")
        self.btn_historial.setProperty("variant", "neutral")
        self.btn_transferencia.setProperty("variant", "success")
        self.btn_whatsapp.setProperty("variant", "success")
        self.btn_comprobante.setProperty("variant", "info")
        self.btn_historial_pagos.setProperty("variant", "neutral")
        self.btn_whatsapp.setIcon(_icono_whatsapp(18))
        self.btn_whatsapp.setIconSize(QSize(16, 16))
        self.btn_registrar_pago.setProperty("variant", "info")
        self.btn_renovar_pago.setProperty("variant", "info")
        self.btn_baja.setProperty("variant", "warning")
        self.btn_eliminar.setProperty("variant", "danger")
        for btn in (
            self.btn_crear,
            self.btn_registrar_pago,
            self.btn_renovar_pago,
            self.btn_whatsapp,
            self.btn_comprobante,
            self.btn_transferencia,
            self.btn_historial,
            self.btn_historial_pagos,
            self.btn_baja,
            self.btn_eliminar,
        ):
            btn.setMinimumWidth(170)

        col_izquierda.addWidget(self.btn_crear)
        col_izquierda.addWidget(self.btn_registrar_pago)
        col_izquierda.addWidget(self.btn_renovar_pago)
        col_izquierda.addStretch(1)

        col_centro_izquierda.addWidget(self.btn_whatsapp)
        col_centro_izquierda.addWidget(self.btn_comprobante)
        col_centro_izquierda.addWidget(self.btn_transferencia)
        col_centro_izquierda.addStretch(1)

        col_centro_derecha.addWidget(self.btn_historial)
        col_centro_derecha.addWidget(self.btn_historial_pagos)
        col_centro_derecha.addStretch(1)

        col_derecha.addWidget(self.btn_baja)
        col_derecha.addWidget(self.btn_eliminar)
        col_derecha.addStretch(1)

        fila_botones.addLayout(col_izquierda)
        fila_botones.addStretch(1)
        fila_botones.addLayout(col_centro_izquierda)
        fila_botones.addStretch(1)
        fila_botones.addLayout(col_centro_derecha)
        fila_botones.addStretch(1)
        fila_botones.addLayout(col_derecha)
        layout.addLayout(fila_botones)

        self.btn_crear.clicked.connect(self._crear_contrato)
        self.btn_historial.clicked.connect(self._abrir_historial)
        self.btn_transferencia.clicked.connect(self._abrir_transferencia)
        self.btn_whatsapp.clicked.connect(self._enviar_whatsapp_contrato)
        self.btn_comprobante.clicked.connect(self._enviar_comprobante_contrato)
        self.btn_historial_pagos.clicked.connect(self._abrir_historial_pagos)
        self.btn_registrar_pago.clicked.connect(self._registrar_pago)
        self.btn_renovar_pago.clicked.connect(self._renovar_pago)
        self.btn_baja.clicked.connect(self._baja)
        self.btn_eliminar.clicked.connect(self._eliminar)
        self.table.itemSelectionChanged.connect(self._seleccion_changed)
        self.input_buscar.textChanged.connect(self._cargar)
        self.input_dni.editingFinished.connect(self._actualizar_patente_por_dni)
        _instalar_enter_navegacion(
            self,
            {
                self.input_buscar: self.input_dni,
                self.input_dni: self.input_espacio,
                self.input_espacio: self.input_venc,
                self.input_venc: self.input_monto,
                self.input_monto: self._crear_contrato,
            },
        )

        self._cargar_tarifa_mensual()
        self._cargar()
        self._actualizar_acciones_pago()
        self._actualizar_snapshot_form()
        es_dueno = (self.rol or "").strip().upper() == "DUENO"
        if not es_dueno:
            self.btn_eliminar.setVisible(False)
            self.btn_eliminar.setEnabled(False)

    def _snapshot_form(self):
        return {
            "dni": _solo_digitos(self.input_dni.text().strip()),
            "patente": self.input_patente.text().strip().upper(),
            "modelo": self.input_modelo.text().strip(),
            "tipo_vehiculo": self.input_tipo_vehiculo.text().strip(),
            "espacio": self.input_espacio.text().strip().upper(),
            "vencimiento": self.input_venc.date().toString("yyyy-MM-dd"),
            "monto": round(float(self.input_monto.value()), 2),
        }

    def _actualizar_snapshot_form(self):
        self._form_snapshot = self._snapshot_form()

    def _limpiar_form_contrato(self):
        self._patente_preferida = ""
        self.input_dni.clear()
        self.input_patente.clear()
        self.input_modelo.clear()
        self.input_tipo_vehiculo.clear()
        self.input_espacio.clear()
        self.input_venc.setDate(QDate.currentDate().addMonths(1))
        self._cargar_tarifa_mensual()
        self._actualizar_acciones_pago()
        self._actualizar_snapshot_form()

    def _hay_cambios_sin_guardar(self):
        # Solo cuenta como pendiente si se esta cargando un nuevo contrato.
        id_contrato, _ = self._selected_ids()
        if id_contrato:
            return False
        base = getattr(self, "_form_snapshot", None)
        if base is None:
            return False
        return self._snapshot_form() != base

    def _sugerir_espacio_libre(self):
        if self.input_espacio.text().strip():
            return
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT codigo FROM espacios "
                "WHERE activo = 1 AND COALESCE(es_reservado, 0) = 1 "
                "AND id_cliente IS NULL "
                "ORDER BY codigo LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                self.input_espacio.setText(row["codigo"])
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()

    def autocompletar(self):
        self._cargar_tarifa_mensual()
        self._sugerir_espacio_libre()
        self._actualizar_patente_por_dni()

    def set_patente_preferida(self, patente):
        self._patente_preferida = _normalizar_patente(patente)
        if self.input_dni.text().strip():
            self._actualizar_patente_por_dni()

    def _formatear_input_dni(self):
        dni = _solo_digitos(self.input_dni.text().strip())
        self.input_dni.setText(_formatear_documento(dni))
        return dni

    def _actualizar_patente_por_dni(self):
        dni = self._formatear_input_dni()
        self.input_patente.clear()
        self.input_modelo.clear()
        self.input_tipo_vehiculo.clear()
        if not dni:
            self._cargar_tarifa_mensual()
            return
        # Esto respeta la patente que ya veniamos usando si el cliente tiene varias, asi no salta a cualquiera.
        vehiculo = svc_obtener_vehiculo_por_dni(dni, self._patente_preferida)
        patente = (vehiculo.get("patente") or "").strip()
        tipo_vehiculo = vehiculo.get("tipo_vehiculo") or "AUTO"
        if patente:
            self.input_patente.setText(_formatear_patente(patente))
        self.input_modelo.setText((vehiculo.get("modelo") or "").strip())
        self.input_tipo_vehiculo.setText(_texto_tipo_vehiculo(tipo_vehiculo))
        self._cargar_tarifa_mensual(tipo_vehiculo)

    def _cargar_tarifa_mensual(self, tipo_vehiculo="AUTO"):
        monto = svc_obtener_tarifa_mensual_actual(tipo_vehiculo)
        if monto is not None:
            self.input_monto.setValue(float(monto))

    def _row_contrato_match(self, row, vista, texto):
        if not texto:
            return True
        campos = [
            row.get("nombre"),
            row.get("dni"),
            _formatear_documento(row.get("dni")),
            row.get("patente"),
            row.get("modelo"),
            _texto_tipo_vehiculo(row.get("tipo_vehiculo")),
            row.get("codigo"),
            row.get("fecha_inicio"),
            row.get("fecha_vencimiento"),
            vista.get("estado"),
        ]
        bolsa = " ".join(str(valor or "").strip().lower() for valor in campos)
        return texto in bolsa

    def _cargar(self):
        id_contrato_previo, _ = self._selected_ids()
        texto_buscar = self.input_buscar.text().strip().lower()
        self.table.setRowCount(0)
        rows = svc_listar_contratos()
        hoy = QDate.currentDate()
        visible_ids = set()
        for row in rows:
            vista = _clasificar_contrato_vista(row, hoy=hoy)
            if not vista["principal"]:
                continue
            if not self._row_contrato_match(row, vista, texto_buscar):
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            item_cliente = QTableWidgetItem(row["nombre"])
            item_cliente.setData(Qt.UserRole, row["id_contrato"])
            item_cliente.setData(Qt.UserRole + 1, row["id_espacio"])
            item_cliente.setData(Qt.UserRole + 2, int(row["activo"] or 0))
            item_cliente.setData(Qt.UserRole + 3, int(row.get("cliente_activo", 1) or 0))
            item_cliente.setData(Qt.UserRole + 4, int(row.get("en_historial", 0) or 0))
            self.table.setItem(r, 0, item_cliente)
            visible_ids.add(row["id_contrato"])
            self.table.setItem(r, 1, QTableWidgetItem(_formatear_documento(row["dni"])))
            self.table.setItem(r, 2, QTableWidgetItem(row["patente"] or ""))
            self.table.setItem(r, 3, QTableWidgetItem((row.get("modelo") or "").strip()))
            self.table.setItem(r, 4, QTableWidgetItem(row["codigo"]))
            self.table.setItem(r, 5, QTableWidgetItem(row["fecha_inicio"] or ""))
            item_venc = QTableWidgetItem(row["fecha_vencimiento"] or "")
            self.table.setItem(r, 6, item_venc)
            self.table.setItem(
                r, 7, QTableWidgetItem(_fmt_money(row["monto_mensual"] or 0))
            )
            activo = vista["estado"]
            self.table.setItem(r, 8, QTableWidgetItem(activo))

            fecha_venc = vista["fecha_venc"]
            if fecha_venc.isValid():
                dias = vista["dias"]
                if dias is not None and dias < 0:
                    bg = QColor(127, 29, 29)
                    fg = QColor(255, 255, 255)
                    tip = f"Vencido hace {abs(dias)} dia/s"
                elif dias == 0:
                    bg = QColor(180, 83, 9)
                    fg = QColor(255, 255, 255)
                    tip = "Vence hoy"
                elif dias is not None and dias <= 7:
                    bg = QColor(202, 138, 4)
                    fg = QColor(0, 0, 0)
                    tip = f"Vence en {dias} dia/s"
                else:
                    bg = QColor(21, 128, 61)
                    fg = QColor(255, 255, 255)
                    tip = f"Vence en {dias} dia/s"
                item_venc.setBackground(QBrush(bg))
                item_venc.setForeground(QBrush(fg))
                item_venc.setToolTip(tip)
            if int(row.get("cliente_activo", 1) or 0) != 1:
                for c in range(self.table.columnCount()):
                    item = self.table.item(r, c)
                    if item:
                        item.setForeground(QBrush(QColor(140, 140, 140)))
                item_cliente.setToolTip("Cliente desactivado: contrato solo lectura.")
        if id_contrato_previo and id_contrato_previo in visible_ids:
            self._seleccionar_contrato(id_contrato_previo)
        elif not visible_ids and not self._hay_cambios_sin_guardar():
            self._limpiar_form_contrato()
        self._actualizar_acciones_pago()
        self._actualizar_snapshot_form()

    def _seleccionar_contrato(self, id_contrato):
        if not id_contrato:
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == id_contrato:
                self.table.selectRow(row)
                self.table.setCurrentCell(row, 0)
                self._seleccion_changed()
                return

    def _abrir_historial(self):
        dlg = HistorialContratosDialog(self)
        dlg.exec()

    def _selected_ids(self):
        row = self.table.currentRow()
        if row < 0:
            return None, None
        item = self.table.item(row, 0)
        if not item:
            return None, None
        return item.data(Qt.UserRole), item.data(Qt.UserRole + 1)

    def _selected_activo(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        val = item.data(Qt.UserRole + 2)
        if val is None:
            return None
        return int(val) == 1

    def _selected_codigo_espacio(self):
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 4)
        if not item:
            return ""
        return (item.text() or "").strip().upper()

    def _selected_cliente_activo(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        val = item.data(Qt.UserRole + 3)
        if val is None:
            return None
        return int(val) == 1

    def _cliente_activo_por_contrato(self, id_contrato):
        if not id_contrato:
            return False
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COALESCE(c.activo, 0) AS activo "
                "FROM cochera_contratos cc "
                "JOIN clientes c ON c.id_cliente = cc.id_cliente "
                "WHERE cc.id_contrato = ?",
                (id_contrato,),
            )
            row = cur.fetchone()
            return bool(row and int(row["activo"] or 0) == 1)
        except sqlite3.Error:
            return False
        finally:
            if conn:
                conn.close()

    def _contar_pagos_contrato(self, id_contrato):
        if not id_contrato:
            return 0
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) AS cantidad "
                "FROM pagos_cochera "
                "WHERE id_contrato = ?",
                (id_contrato,),
            )
            row = cur.fetchone()
            return int((row["cantidad"] if row else 0) or 0)
        except sqlite3.Error:
            return 0
        finally:
            if conn:
                conn.close()

    def _validar_cliente_activo_contrato(self, id_contrato, accion):
        if self._cliente_activo_por_contrato(id_contrato):
            return True
        QMessageBox.warning(
            self,
            "Cliente desactivado",
            f"No se puede {accion}: el cliente del contrato esta desactivado.\n"
            "Activalo desde Clientes para continuar.",
        )
        return False

    def _actualizar_acciones_pago(self, activo=None, cliente_activo=None):
        id_contrato, _ = self._selected_ids()
        hay_sel = bool(id_contrato)
        if not hay_sel:
            self.btn_historial_pagos.setEnabled(True)
            self.btn_whatsapp.setEnabled(False)
            self.btn_comprobante.setEnabled(False)
            self.btn_registrar_pago.setEnabled(False)
            self.btn_renovar_pago.setEnabled(False)
            self.btn_baja.setEnabled(False)
            if self.btn_eliminar and self.btn_eliminar.isVisible():
                self.btn_eliminar.setEnabled(False)
                self.btn_eliminar.setToolTip("Selecciona un contrato.")
            self.btn_transferencia.setToolTip(
                "Selecciona un contrato para enviar alias y CBU por WhatsApp."
            )
            self.btn_historial_pagos.setToolTip(
                "Haz clic para ver el aviso si todavia no seleccionaste un contrato."
            )
            self.btn_whatsapp.setToolTip("Selecciona un contrato.")
            self.btn_comprobante.setToolTip("Selecciona un contrato.")
            return

        if activo is None:
            activo = self._selected_activo()
        es_activo = bool(activo)
        if cliente_activo is None:
            cliente_activo = self._selected_cliente_activo()
        if cliente_activo is None:
            cliente_activo = True
        pagos_contrato = self._contar_pagos_contrato(id_contrato)
        resumen_venc = self._resumen_recordatorio_whatsapp(id_contrato)
        dias_para_vencimiento = (
            resumen_venc.get("dias_para_vencimiento")
            if resumen_venc
            else None
        )
        puede_avisar_vencimiento = (
            dias_para_vencimiento is not None and dias_para_vencimiento <= 0
        )
        self.btn_transferencia.setToolTip(
            "Envia alias y CBU al cliente por WhatsApp."
        )
        self.btn_historial_pagos.setEnabled(True)
        if pagos_contrato > 0:
            self.btn_historial_pagos.setToolTip(
                f"Abre el historial de {pagos_contrato} pago/s registrados en este contrato."
            )
        else:
            self.btn_historial_pagos.setToolTip(
                "Abre el historial de pagos de este contrato. Todavia no hay pagos registrados."
            )
        if not bool(cliente_activo):
            self.btn_whatsapp.setEnabled(False)
            self.btn_comprobante.setEnabled(False)
            self.btn_registrar_pago.setEnabled(False)
            self.btn_renovar_pago.setEnabled(False)
            self.btn_baja.setEnabled(False)
            if self.btn_eliminar and self.btn_eliminar.isVisible():
                self.btn_eliminar.setEnabled(bool(not es_activo))
                self.btn_eliminar.setToolTip(
                    "Elimina este contrato inactivo aunque el cliente este desactivado."
                    if not es_activo
                    else "Primero da de baja el contrato activo para pasarlo a historial."
                )
            tip = "Cliente desactivado. Reactivalo desde Clientes."
            self.btn_whatsapp.setToolTip(tip)
            self.btn_comprobante.setToolTip(tip)
            self.btn_registrar_pago.setToolTip(tip)
            self.btn_renovar_pago.setToolTip(tip)
            self.btn_baja.setToolTip(tip)
            return

        self.btn_whatsapp.setEnabled(puede_avisar_vencimiento)
        self.btn_comprobante.setEnabled(pagos_contrato > 0)
        self.btn_registrar_pago.setEnabled(not es_activo)
        self.btn_renovar_pago.setEnabled(es_activo)
        self.btn_baja.setEnabled(es_activo)
        if self.btn_eliminar and self.btn_eliminar.isVisible():
            self.btn_eliminar.setEnabled(not es_activo)
        if puede_avisar_vencimiento:
            self.btn_whatsapp.setToolTip(
                "Abre WhatsApp con el aviso de vencimiento del contrato."
            )
        else:
            self.btn_whatsapp.setToolTip(
                "Disponible solo cuando el contrato vence hoy o ya esta vencido."
            )
        if pagos_contrato > 0:
            self.btn_comprobante.setToolTip(
                "Genera el comprobante del ultimo pago y abre WhatsApp."
            )
        else:
            self.btn_comprobante.setToolTip(
                "Todavia no hay pagos registrados para este contrato."
            )

        if es_activo:
            self.btn_registrar_pago.setToolTip("Solo para activar contratos inactivos.")
            self.btn_renovar_pago.setToolTip("Renueva y extiende vencimiento.")
            self.btn_baja.setToolTip("Desactiva contrato y libera espacio.")
            if self.btn_eliminar and self.btn_eliminar.isVisible():
                self.btn_eliminar.setToolTip(
                    "Los contratos activos no se eliminan desde aqui.\n"
                    "Usa 'Dar de baja' y, si hace falta, elimÃ­nalo luego desde Historial."
                )
        else:
            self.btn_registrar_pago.setToolTip("Registra primer pago y activa el contrato.")
            self.btn_renovar_pago.setToolTip("Disponible solo para contratos activos.")
            self.btn_baja.setToolTip("Disponible solo para contratos activos.")
            if self.btn_eliminar and self.btn_eliminar.isVisible():
                self.btn_eliminar.setToolTip(
                    "Elimina este contrato inactivo definitivamente."
                )

    @staticmethod
    def _meses_mora_whatsapp(fecha_venc, hoy):
        if not fecha_venc.isValid() or fecha_venc >= hoy:
            return 0
        meses = 0
        cursor = fecha_venc
        while cursor < hoy and meses < 240:
            meses += 1
            cursor = cursor.addMonths(1)
        return meses

    def _resumen_recordatorio_whatsapp(self, id_contrato):
        if not id_contrato:
            return None
        row = svc_obtener_detalle_contrato(id_contrato)
        if not row:
            return None

        nombre = (row.get("nombre") or "").strip()
        telefono = (row.get("telefono") or "").strip()
        modelo = (row.get("modelo") or "").strip()
        monto = float(row.get("monto_mensual") or 0.0)
        tipo_vehiculo = row.get("tipo_vehiculo") or "AUTO"
        fecha_venc = QDate.fromString(row.get("fecha_vencimiento") or "", "yyyy-MM-dd")
        hoy = QDate.currentDate()
        vencimiento = "Sin vencimiento"
        if fecha_venc.isValid():
            dias = hoy.daysTo(fecha_venc)
            dias_para_vencimiento = dias
            base = fecha_venc.toString("dd/MM/yyyy")
            if dias < 0:
                vencimiento = f"{base} (vencido hace {abs(dias)} dia/s)"
            elif dias == 0:
                vencimiento = f"{base} (vence hoy)"
            else:
                vencimiento = f"{base} (en {dias} dia/s)"
        else:
            dias_para_vencimiento = None
        return {
            "nombre": nombre,
            "telefono": telefono,
            "modelo": modelo,
            "patente": _formatear_patente(row.get("patente") or ""),
            "vencimiento": vencimiento,
            "deuda": _texto_cuota_recordatorio(tipo_vehiculo, monto),
            "activo": int(row.get("activo") or 0),
            "dias_para_vencimiento": dias_para_vencimiento,
        }

    def _enviar_whatsapp_contrato(self):
        id_contrato, _ = self._selected_ids()
        if not id_contrato:
            QMessageBox.warning(
                self,
                "Vencimiento",
                "Selecciona un contrato de la lista para enviar su aviso de vencimiento.",
            )
            return
        if not self._validar_cliente_activo_contrato(
            id_contrato, "enviar el aviso de vencimiento"
        ):
            self._actualizar_acciones_pago()
            return

        resumen = self._resumen_recordatorio_whatsapp(id_contrato)
        if not resumen:
            QMessageBox.warning(
                self,
                "Vencimiento",
                "No se pudo preparar el recordatorio del contrato.\n"
                "Actualiza la lista y vuelve a intentarlo.",
            )
            return

        dias_para_vencimiento = resumen.get("dias_para_vencimiento")
        if dias_para_vencimiento is None or dias_para_vencimiento > 0:
            QMessageBox.warning(
                self,
                "Vencimiento",
                "Este contrato todavia no vencio.\n"
                "El aviso por WhatsApp solo se puede enviar cuando vence hoy o ya esta vencido.",
            )
            return

        numero = _telefono_a_whatsapp(resumen.get("telefono"))
        if not numero:
            QMessageBox.warning(
                self,
                "Vencimiento",
                "El cliente no tiene un telefono valido para WhatsApp.",
            )
            return

        nombre = resumen.get("nombre") or "cliente"
        vencimiento = resumen.get("vencimiento") or "sin vencimiento"
        deuda = resumen.get("deuda") or "$ 0.00"
        modelo = resumen.get("modelo") or ""
        patente = resumen.get("patente") or ""
        mensaje = _render_mensaje_whatsapp(
            nombre, vencimiento, deuda, modelo=modelo, patente=patente
        )

        url = QUrl(
            f"https://api.whatsapp.com/send?phone={quote(numero)}&text={quote(mensaje)}"
        )
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                "Vencimiento",
                "No se pudo abrir WhatsApp.\n"
                "Verifica que tengas un navegador o la app disponible.",
            )
            return

        _auditar(
            self,
            "Recordatorio vencimiento contrato",
            (
                f"Contrato {id_contrato} - {nombre or '-'} - {numero} - "
                f"{vencimiento} - {deuda} - Modelo: {modelo or '-'}"
            ),
        )

    def _abrir_transferencia(self):
        id_contrato, _ = self._selected_ids()
        if not id_contrato:
            QMessageBox.warning(
                self,
                "Transferencia",
                "Selecciona un contrato de la lista para enviar alias y CBU por WhatsApp.",
            )
            return
        if not self._validar_cliente_activo_contrato(id_contrato, "enviar datos de transferencia"):
            self._actualizar_acciones_pago()
            return

        resumen = self._resumen_recordatorio_whatsapp(id_contrato)
        if not resumen:
            QMessageBox.warning(
                self,
                "Transferencia",
                "No se encontraron datos del contrato seleccionado.",
            )
            return

        numero = _telefono_a_whatsapp(resumen.get("telefono"))
        if not numero:
            QMessageBox.warning(
                self,
                "Transferencia",
                "El cliente no tiene un telefono valido para WhatsApp.",
            )
            return

        alias = (_config_get("empresa_alias", "") or "").strip()
        cbu = (_config_get("empresa_cbu", "") or "").strip()
        if not alias and not cbu:
            QMessageBox.warning(
                self,
                "Transferencia",
                "No hay alias ni CBU configurados.\n"
                "Cargalos en Configuracion > General antes de enviarlos por WhatsApp.",
            )
            return

        nombre = resumen.get("nombre") or "cliente"
        partes = [f"Hola {nombre}, te compartimos los datos para realizar la transferencia."]
        if alias:
            partes.append(f"Alias: {alias}")
        if cbu:
            partes.append(f"CBU: {cbu}")
        mensaje = "\n".join(partes)

        url = QUrl(
            f"https://api.whatsapp.com/send?phone={quote(numero)}&text={quote(mensaje)}"
        )
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                "Transferencia",
                "No se pudo abrir WhatsApp.\n"
                "Verifica que tengas un navegador o la app disponible.",
            )
            return

        _auditar(
            self,
            "Datos de transferencia enviados por WhatsApp",
            f"Contrato {id_contrato} - {nombre} - {numero}",
        )

    def _abrir_historial_pagos(self):
        id_contrato, _ = self._selected_ids()
        if not id_contrato:
            QMessageBox.warning(
                self,
                "Pagos",
                "Selecciona un contrato de la lista para ver su historial de pagos.",
            )
            return
        dlg = HistorialPagosContratoDialog(id_contrato, self)
        dlg.exec()

    def _enviar_comprobante_contrato(self):
        id_contrato, _ = self._selected_ids()
        if not id_contrato:
            QMessageBox.warning(
                self,
                "Comprobante",
                "Selecciona un contrato en la lista para generar o enviar su comprobante.",
            )
            return
        if not self._validar_cliente_activo_contrato(
            id_contrato, "enviar el comprobante"
        ):
            self._actualizar_acciones_pago()
            return

        path, pago = _emitir_comprobante_ultimo_pago_contrato(id_contrato)
        if not path or not pago:
            QMessageBox.warning(
                self,
                "Comprobante",
                "Este contrato todavia no tiene pagos registrados.",
            )
            return

        nombre = (pago.get("nombre") or "").strip() or "cliente"
        monto = _fmt_money(float(pago.get("monto") or 0.0))
        numero = _telefono_a_whatsapp(pago.get("telefono"))
        fecha_pago = _parse_datetime_local(pago.get("fecha_pago"))
        fecha_txt = (
            fecha_pago.strftime("%d/%m/%Y %H:%M")
            if fecha_pago
            else str(pago.get("fecha_pago") or "-")
        )
        espacio = (pago.get("codigo") or "").strip() or "-"
        patente = (pago.get("patente") or "").strip() or "-"
        mensaje = (
            f"Hola {nombre}, te compartimos el comprobante de pago de tu cochera. "
            f"Espacio: {espacio}. Patente: {patente}. "
            f"Monto: {monto}. Fecha: {fecha_txt}."
        )

        se_mostro_archivo = _mostrar_en_explorador(path)
        se_abrio_whatsapp = False
        if numero:
            url = QUrl(
                f"https://api.whatsapp.com/send?phone={quote(numero)}&text={quote(mensaje)}"
            )
            se_abrio_whatsapp = QDesktopServices.openUrl(url)

        _auditar(
            self,
            "Comprobante compartido contrato",
            (
                f"Contrato {id_contrato} - Pago {pago.get('id_pago') or '-'} - "
                f"{nombre} - {monto} - PDF: {path.name}"
            ),
        )

        if se_mostro_archivo and se_abrio_whatsapp:
            _mostrar_resultado_comprobante(
                self,
                "Comprobante",
                "Se abrio la carpeta con el comprobante seleccionado y el chat de WhatsApp para que lo adjuntes.",
                path,
            )
            return
        if se_mostro_archivo and not numero:
            _mostrar_resultado_comprobante(
                self,
                "Comprobante",
                "Se abrio la carpeta con el comprobante seleccionado, pero el cliente no tiene un telefono valido para WhatsApp.",
                path,
            )
            return
        if se_mostro_archivo and not se_abrio_whatsapp:
            _mostrar_resultado_comprobante(
                self,
                "Comprobante",
                "Se abrio la carpeta con el comprobante seleccionado, pero no se pudo abrir WhatsApp.",
                path,
            )
            return
        _mostrar_resultado_comprobante(
            self,
            "Comprobante",
            f"Comprobante generado en:\n{path}",
            path,
        )

    def _seleccion_changed(self):
        id_contrato, _ = self._selected_ids()
        if not id_contrato:
            if not self._hay_cambios_sin_guardar():
                self._limpiar_form_contrato()
                return
            self._actualizar_acciones_pago()
            self._actualizar_snapshot_form()
            return
        row = svc_obtener_detalle_contrato(id_contrato)
        if not row:
            if not self._hay_cambios_sin_guardar():
                self._limpiar_form_contrato()
                return
            return
        self.input_dni.setText(_formatear_documento(row["dni"] or ""))
        self.input_patente.setText(_formatear_patente(row["patente"] or ""))
        self.input_modelo.setText((row.get("modelo") or "").strip())
        self.input_tipo_vehiculo.setText(_texto_tipo_vehiculo(row.get("tipo_vehiculo")))
        self.input_espacio.setText((row["codigo"] or "").upper())
        fecha = QDate.fromString(row["fecha_vencimiento"] or "", "yyyy-MM-dd")
        if fecha.isValid():
            self.input_venc.setDate(fecha)
        self.input_monto.setValue(float(row["monto_mensual"] or 0.0))
        self._actualizar_acciones_pago(
            int(row["activo"] or 0) == 1,
            int(row.get("cliente_activo", 1) or 0) == 1,
        )
        self._actualizar_snapshot_form()

    def _crear_contrato(self):
        dni = self._formatear_input_dni()
        codigo = self.input_espacio.text().strip().upper()
        fecha_venc = self.input_venc.date().toString("yyyy-MM-dd")
        monto = float(self.input_monto.value())

        if not dni:
            QMessageBox.warning(self, "Datos incompletos", "Completa el DNI del cliente.")
            return False
        if not codigo:
            codigo_sel = self._selected_codigo_espacio()
            if codigo_sel and self._selected_activo():
                QMessageBox.warning(
                    self,
                    "Espacio ocupado",
                    (
                        f"No se puede crear otro contrato en el espacio {codigo_sel} "
                        "porque ya hay un contrato activo con ese lugar.\n"
                        "Elige otro espacio o da de baja el contrato actual."
                    ),
                )
            else:
                QMessageBox.warning(
                    self,
                    "Datos incompletos",
                    "Completa el espacio del contrato.",
                )
            return False
        if monto <= 0:
            QMessageBox.warning(self, "Monto", "El monto debe ser mayor a 0.")
            return False
        if not _antirebote_iniciar(self, "contratos_crear"):
            return False

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()

            cur.execute("SELECT id_cliente FROM clientes WHERE dni = ? AND activo = 1", (dni,))
            row = cur.fetchone()
            if not row:
                QMessageBox.warning(
                    self,
                    "Cliente",
                    "No existe un cliente activo con ese DNI.\n"
                    "Crealo o reactivalo desde Clientes antes de generar el contrato.",
                )
                return False
            id_cliente = row["id_cliente"]

            patente = _normalizar_patente(self.input_patente.text())
            cur.execute(
                "SELECT COUNT(*) AS cantidad FROM vehiculos "
                "WHERE id_cliente = ? AND patente IS NOT NULL AND TRIM(patente) <> ''",
                (id_cliente,),
            )
            cantidad_patentes = int((cur.fetchone()["cantidad"] or 0) or 0)
            if cantidad_patentes <= 0:
                QMessageBox.warning(
                    self,
                    "Contrato",
                    "Este cliente no tiene ninguna patente a su nombre.",
                )
                return False
            if cantidad_patentes > 1 and not patente:
                QMessageBox.warning(
                    self,
                    "Contrato",
                    "Selecciona la patente que corresponde a este contrato.",
                )
                return False

            if patente:
                cur.execute(
                    "SELECT id_vehiculo, patente, modelo, "
                    "COALESCE(NULLIF(TRIM(tipo_vehiculo), ''), 'AUTO') AS tipo_vehiculo "
                    "FROM vehiculos "
                    "WHERE id_cliente = ? AND patente = ? "
                    "LIMIT 1",
                    (id_cliente, patente),
                )
            else:
                cur.execute(
                    "SELECT id_vehiculo, patente, modelo, "
                    "COALESCE(NULLIF(TRIM(tipo_vehiculo), ''), 'AUTO') AS tipo_vehiculo "
                    "FROM vehiculos "
                    "WHERE id_cliente = ? AND patente IS NOT NULL AND TRIM(patente) <> '' "
                    "ORDER BY patente LIMIT 1",
                    (id_cliente,),
                )
            row_pat = cur.fetchone()
            id_vehiculo = int(row_pat["id_vehiculo"]) if row_pat else None
            patente = (row_pat["patente"] or "").strip().upper() if row_pat else ""
            modelo = (row_pat["modelo"] or "").strip() if row_pat else ""
            tipo_vehiculo = row_pat["tipo_vehiculo"] if row_pat else "AUTO"
            if not id_vehiculo or not patente:
                QMessageBox.warning(
                    self,
                    "Contrato",
                    "La patente seleccionada no pertenece al cliente.",
                )
                return False
            self.input_patente.setText(_formatear_patente(patente))
            self.input_modelo.setText(modelo)
            self.input_tipo_vehiculo.setText(_texto_tipo_vehiculo(tipo_vehiculo))
            if not _tipo_vehiculo_habilitado_cochera(tipo_vehiculo):
                QMessageBox.warning(
                    self,
                    "Tipo no permitido",
                    (
                        f"El tipo {_texto_tipo_vehiculo(tipo_vehiculo)} no esta habilitado para cochera.\n"
                        "Revisalo en Configuracion > Sistema > Tipos en cochera."
                    ),
                )
                return False
            tarifa_sugerida = svc_obtener_tarifa_mensual_actual(tipo_vehiculo)
            if tarifa_sugerida is not None and monto <= 0:
                monto = float(tarifa_sugerida)
                self.input_monto.setValue(monto)

            cur.execute(
                "SELECT id_espacio, COALESCE(es_reservado, 0) AS es_reservado "
                "FROM espacios WHERE codigo = ? AND activo = 1",
                (codigo,),
            )
            row = cur.fetchone()
            if not row:
                QMessageBox.warning(
                    self,
                    "Espacio",
                    "Ese espacio no existe en el mapa.\n"
                    "Primero crealo y marcalo como cochera desde Mapa.",
                )
                return False
            if int(row["es_reservado"] or 0) != 1:
                QMessageBox.warning(
                    self,
                    "Espacio",
                    f"El espacio {codigo} esta configurado para estacionamiento.\n"
                    "Los contratos solo pueden hacerse en lugares marcados como cochera.",
                )
                return False
            id_espacio = row["id_espacio"]

            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos WHERE id_espacio = ? AND activo = 1",
                (id_espacio,),
            )
            if (cur.fetchone()[0] or 0) > 0:
                QMessageBox.warning(
                    self,
                    "Espacio ocupado",
                    (
                        f"No se puede crear otro contrato en el espacio {codigo} "
                        "porque ya hay un contrato activo con ese lugar.\n"
                        "Elige otro espacio o da de baja el contrato actual."
                    ),
                )
                return False

            mov_espacio = svc_espacio_tiene_movimiento_activo(cur, id_espacio)
            if mov_espacio:
                patente_est = mov_espacio["patente"] or "-"
                codigo_est = mov_espacio["codigo"] or codigo
                QMessageBox.warning(
                    self,
                    "Espacio ocupado",
                    (
                        f"No se puede crear el contrato en el espacio {codigo_est} "
                        f"porque la patente {patente_est} tiene un ingreso activo "
                        "en estacionamiento.\nRegistra la salida antes de usar ese lugar."
                    ),
                )
                return False

            cur.execute(
                "SELECT cc.id_contrato, e.codigo "
                "FROM cochera_contratos cc "
                "JOIN espacios e ON e.id_espacio = cc.id_espacio "
                "WHERE cc.activo = 1 "
                "AND (cc.id_vehiculo = ? OR (cc.id_vehiculo IS NULL AND cc.id_cliente = ?)) "
                "LIMIT 1",
                (id_vehiculo, id_cliente),
            )
            row_pat_act = cur.fetchone()
            if row_pat_act:
                QMessageBox.warning(
                    self,
                    "Contrato",
                    (
                        f"La patente {patente} ya tiene un contrato activo "
                        f"(espacio {row_pat_act['codigo']})."
                    ),
                )
                return False

            cur.execute(
                "INSERT INTO cochera_contratos "
                "(id_cliente, id_vehiculo, id_espacio, fecha_vencimiento, monto_mensual, activo, en_historial) "
                "VALUES (?, ?, ?, ?, ?, 0, 0)",
                (id_cliente, id_vehiculo, id_espacio, fecha_venc, monto),
            )
            conn.commit()
            _auditar(
                self,
                "Contrato creado (inactivo)",
                " - ".join(
                    [
                        f"DNI {_formatear_documento(dni)}",
                        f"Patente {patente}",
                        f"Tipo {_texto_tipo_vehiculo(tipo_vehiculo)}",
                        f"Espacio {codigo}",
                        f"Venc {fecha_venc}",
                        _fmt_money(monto),
                    ]
                ),
            )
            QMessageBox.information(
                self,
                "Contrato",
                "Contrato creado como INACTIVO.\n"
                "Registra el primer pago para activarlo.",
            )
            self.input_dni.clear()
            self.input_patente.clear()
            self.input_modelo.clear()
            self.input_espacio.clear()
            self._cargar()
            return True
        except sqlite3.Error:
            _mostrar_error(
                self,
                "Error",
                "No se pudo crear el contrato.\n"
                "Revisa los datos y vuelve a intentarlo.",
            )
            return False
        finally:
            if conn:
                conn.close()
            _antirebote_finalizar(self, "contratos_crear", cooldown_ms=700)

    def closeEvent(self, event):
        if not self._hay_cambios_sin_guardar():
            event.accept()
            return
        respuesta = _confirmar_guardado_pendiente(
            self,
            "Hay un contrato sin crear.\nQuieres guardarlo antes de salir?",
        )
        if respuesta == QMessageBox.Cancel:
            event.ignore()
            return
        if respuesta == QMessageBox.No:
            event.accept()
            return
        if self._crear_contrato():
            event.accept()
        else:
            event.ignore()

    def _renovar(self):
        self._renovar_pago()

    def _registrar_pago(self):
        id_contrato, _ = self._selected_ids()
        if not id_contrato:
            QMessageBox.warning(
                self,
                "Pago",
                "Selecciona un contrato de la lista para registrar el primer pago.",
            )
            return
        if not self._validar_cliente_activo_contrato(id_contrato, "registrar pagos"):
            self._actualizar_acciones_pago()
            return
        if not _antirebote_iniciar(self, "contratos_primer_pago"):
            return

        try:
            monto_base = 0.0
            fecha_venc_str = None
            id_espacio = None
            id_cliente = None
            conn = None
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute(
                    "SELECT monto_mensual, fecha_vencimiento, activo, id_espacio, id_cliente "
                    "FROM cochera_contratos WHERE id_contrato = ?",
                    (id_contrato,),
                )
                row = cur.fetchone()
                if not row:
                    QMessageBox.warning(
                        self,
                        "Pago",
                        "No se encontro el contrato seleccionado.\n"
                        "Actualiza la lista y vuelve a intentarlo.",
                    )
                    return
                if row["activo"] == 1:
                    QMessageBox.information(
                        self,
                        "Pago",
                        "El contrato ya esta ACTIVO.\nUsa 'Renovar pago'.",
                    )
                    return
                if row["monto_mensual"] is not None:
                    monto_base = float(row["monto_mensual"])
                fecha_venc_str = row["fecha_vencimiento"]
                id_espacio = row["id_espacio"]
                id_cliente = row["id_cliente"]
                if id_espacio:
                    cur.execute(
                        "SELECT COUNT(*) FROM cochera_contratos "
                        "WHERE id_espacio = ? AND activo = 1 AND id_contrato <> ?",
                        (id_espacio, id_contrato),
                    )
                    if (cur.fetchone()[0] or 0) > 0:
                        QMessageBox.warning(
                            self,
                            "Pago",
                            "Ya existe un contrato activo para ese espacio.",
                        )
                        return
                    mov_espacio = svc_espacio_tiene_movimiento_activo(cur, id_espacio)
                    if mov_espacio:
                        patente_est = mov_espacio["patente"] or "-"
                        codigo_est = mov_espacio["codigo"] or "-"
                        QMessageBox.warning(
                            self,
                            "Pago",
                            f"El espacio {codigo_est} esta ocupado por la patente "
                            f"{patente_est} en estacionamiento. Registra la salida "
                            "antes de activar el contrato.",
                        )
                        return
                if id_cliente:
                    mov_activo = svc_cliente_tiene_movimiento_activo(cur, id_cliente)
                    if mov_activo:
                        patente_activa = mov_activo["patente"] or "-"
                        codigo_est = mov_activo["codigo"] or "-"
                        QMessageBox.warning(
                            self,
                            "Pago",
                            f"La patente {patente_activa} tiene un ingreso activo en "
                            f"estacionamiento (espacio {codigo_est}). Registra la salida "
                            "antes de activar el contrato.",
                        )
                        return
            except sqlite3.Error:
                _mostrar_error(self, "Error", "No se pudo leer el monto del contrato.")
                return
            finally:
                if conn:
                    conn.close()

            dlg = PagoActivacionDialog(monto_base, self)
            if dlg.exec() != QDialog.Accepted:
                return
            monto, metodo = dlg.get_data()
            if monto <= 0:
                QMessageBox.warning(
                    self,
                    "Pago",
                    "El monto ingresado debe ser mayor a 0 para registrar el pago.",
                )
                return

            try:
                resultado = svc_registrar_primer_pago_contrato(id_contrato, monto, metodo)
                fecha_venc_str = resultado.get("fecha_vencimiento") or fecha_venc_str
                _auditar(
                    self,
                    "Primer pago cochera registrado",
                    f"Contrato {id_contrato} - $ {monto:.2f} - {metodo}",
                )
                self._cargar()
                fecha_venc = QDate.fromString(fecha_venc_str or "", "yyyy-MM-dd")
                venc_txt = fecha_venc.toString("dd/MM/yyyy") if fecha_venc.isValid() else "-"
                comprobante = _emitir_comprobante_cochera(
                    id_contrato,
                    monto,
                    metodo,
                    "Activacion",
                    venc_txt,
                )
                info_extra = ""
                if comprobante:
                    info_extra = f"\nComprobante: {comprobante.name}"
                _mostrar_resultado_comprobante(
                    self,
                    "Pago",
                    "Primer pago registrado. Contrato ACTIVADO.\n"
                    f"Vencimiento sin cambios: {venc_txt}.{info_extra}",
                    comprobante,
                )
            except ValueError as e:
                QMessageBox.warning(self, "Pago", str(e))
            except sqlite3.Error:
                _mostrar_error(self, "Error", "No se pudo registrar el pago.")
        finally:
            _antirebote_finalizar(
                self,
                "contratos_primer_pago",
                cooldown_ms=700,
                on_release=self._actualizar_acciones_pago,
            )

    def _renovar_pago(self):
        id_contrato, _ = self._selected_ids()
        if not id_contrato:
            QMessageBox.warning(
                self,
                "Renovar pago",
                "Selecciona un contrato de la lista para registrar la renovacion.",
            )
            return
        if not self._validar_cliente_activo_contrato(id_contrato, "renovar pagos"):
            self._actualizar_acciones_pago()
            return
        if not _antirebote_iniciar(self, "contratos_renovar_pago"):
            return

        try:
            monto_base = 0.0
            fecha_venc_str = None
            conn = None
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute(
                    "SELECT monto_mensual, fecha_vencimiento, activo "
                    "FROM cochera_contratos WHERE id_contrato = ?",
                    (id_contrato,),
                )
                row = cur.fetchone()
                if not row:
                    QMessageBox.warning(
                        self,
                        "Renovar pago",
                        "No se encontro el contrato seleccionado.\n"
                        "Actualiza la lista y vuelve a intentarlo.",
                    )
                    return
                if row["activo"] != 1:
                    QMessageBox.information(
                        self,
                        "Renovar pago",
                        "El contrato esta INACTIVO.\nUsa 'Registro de pagos' para activarlo.",
                    )
                    return
                if row["monto_mensual"] is not None:
                    monto_base = float(row["monto_mensual"])
                fecha_venc_str = row["fecha_vencimiento"]
            except sqlite3.Error:
                _mostrar_error(self, "Error", "No se pudo leer el monto del contrato.")
                return
            finally:
                if conn:
                    conn.close()

            dlg = PagoCocheraDialog(monto_base, self)
            if dlg.exec() != QDialog.Accepted:
                return
            meses, monto, metodo = dlg.get_data()
            if monto <= 0:
                QMessageBox.warning(
                    self,
                    "Renovar pago",
                    "El monto ingresado debe ser mayor a 0 para registrar la renovacion.",
                )
                return

            try:
                nueva_venc_str = svc_registrar_renovacion_contrato(
                    id_contrato,
                    meses,
                    monto,
                    metodo,
                )
                nueva_venc = QDate.fromString(nueva_venc_str or "", "yyyy-MM-dd")
                if not nueva_venc.isValid():
                    nueva_venc = QDate.currentDate()
                _auditar(
                    self,
                    "Renovacion de pago cochera",
                    f"Contrato {id_contrato} - {meses} mes/es - $ {monto:.2f} - {metodo}",
                )
                self._cargar()
                comprobante = _emitir_comprobante_cochera(
                    id_contrato,
                    monto,
                    metodo,
                    meses,
                    nueva_venc.toString("dd/MM/yyyy"),
                )
                info_extra = ""
                if comprobante:
                    info_extra = f"\nComprobante: {comprobante.name}"
                _mostrar_resultado_comprobante(
                    self,
                    "Renovar pago",
                    f"Renovacion registrada ({meses} mes/es). Nuevo vencimiento: "
                    f"{nueva_venc.toString('dd/MM/yyyy')}.{info_extra}",
                    comprobante,
                )
            except ValueError as e:
                QMessageBox.warning(self, "Renovar pago", str(e))
            except sqlite3.Error:
                _mostrar_error(self, "Error", "No se pudo registrar la renovacion.")
        finally:
            _antirebote_finalizar(
                self,
                "contratos_renovar_pago",
                cooldown_ms=700,
                on_release=self._actualizar_acciones_pago,
            )

    def _baja(self):
        id_contrato, id_espacio = self._selected_ids()
        if not id_contrato:
            QMessageBox.warning(
                self,
                "Contrato",
                "Selecciona un contrato de la lista para darlo de baja.",
            )
            return
        if not self._validar_cliente_activo_contrato(id_contrato, "dar de baja el contrato"):
            self._actualizar_acciones_pago()
            return
        if not _antirebote_iniciar(self, "contratos_baja"):
            return
        try:
            confirmar = QMessageBox.question(
                self,
                "Dar de baja",
                "Desactivar contrato y liberar espacio?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirmar != QMessageBox.Yes:
                return
            conn = None
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE cochera_contratos SET activo = 0, en_historial = 1 "
                    "WHERE id_contrato = ?",
                    (id_contrato,),
                )
                if id_espacio:
                    cur.execute(
                        "UPDATE espacios SET id_cliente = NULL WHERE id_espacio = ?",
                        (id_espacio,),
                    )
                conn.commit()
                _auditar(self, "Contrato baja", f"ID {id_contrato}")
                self._cargar()
                QMessageBox.information(
                    self,
                    "Contrato",
                    "Contrato dado de baja.\nAhora se encuentra en Historial.",
                )
            except sqlite3.Error:
                _mostrar_error(self, "Error", "No se pudo dar de baja.")
            finally:
                if conn:
                    conn.close()
        finally:
            _antirebote_finalizar(
                self,
                "contratos_baja",
                cooldown_ms=700,
                on_release=self._actualizar_acciones_pago,
            )

    def _eliminar(self):
        id_contrato, id_espacio = self._selected_ids()
        if not id_contrato:
            QMessageBox.warning(
                self,
                "Contrato",
                "Selecciona un contrato de la lista para eliminarlo.",
            )
            return
        if (self.rol or "").strip().upper() != "DUENO":
            QMessageBox.warning(
                self,
                "Contrato",
                "Solo DUENO puede eliminar contratos desde esta pantalla.",
            )
            return
        if not _antirebote_iniciar(self, "contratos_eliminar"):
            return
        try:
            activo = False
            pagos = 0
            conn = None
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute(
                    "SELECT activo FROM cochera_contratos WHERE id_contrato = ?",
                    (id_contrato,),
                )
                row = cur.fetchone()
                activo = bool(row and row["activo"] == 1)
                cur.execute(
                    "SELECT COUNT(*) AS cantidad FROM pagos_cochera WHERE id_contrato = ?",
                    (id_contrato,),
                )
                row_pagos = cur.fetchone()
                pagos = int((row_pagos["cantidad"] if row_pagos else 0) or 0)
            except sqlite3.Error:
                activo = False
                pagos = 0
            finally:
                if conn:
                    conn.close()

            if activo:
                QMessageBox.warning(
                    self,
                    "Contrato activo",
                    "Este contrato esta ACTIVO y no se puede eliminar desde aqui.\n"
                    "Si quieres quitarlo, primero usa 'Dar de baja' para mandarlo a Historial.",
                )
                return

            detalle_extra = ""
            if pagos > 0:
                detalle_extra = (
                    f"\nTambien se eliminaran {pagos} pago/s asociados a este contrato."
                )
            confirmar = QMessageBox.question(
                self,
                "Eliminar contrato",
                "Esto eliminara el contrato inactivo definitivamente. Continuar?"
                + detalle_extra,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirmar != QMessageBox.Yes:
                return

            try:
                resultado = _eliminar_contrato_definitivo(id_contrato)
                if not resultado.get("ok"):
                    QMessageBox.warning(
                        self,
                        "Contrato",
                        "No se encontro el contrato para eliminar.",
                    )
                    return
                _auditar(
                    self,
                    "Contrato eliminado",
                    f"ID {id_contrato} - pagos eliminados: {resultado.get('pagos', 0)}",
                )
                self._cargar()
            except sqlite3.IntegrityError:
                _mostrar_error(
                    self,
                    "Error",
                    "No se pudo eliminar el contrato porque tiene datos relacionados.",
                )
            except sqlite3.Error:
                _mostrar_error(self, "Error", "No se pudo eliminar el contrato.")
        finally:
            _antirebote_finalizar(
                self,
                "contratos_eliminar",
                cooldown_ms=700,
                on_release=self._actualizar_acciones_pago,
            )


class HistorialContratosDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Historial de contratos")
        self.setMinimumWidth(900)
        self.setMinimumHeight(480)

        layout = QVBoxLayout(self)
        self.label_resumen = QLabel(
            "Aqui se muestran los contratos dados de baja. "
            "Los contratos nuevos o inactivos siguen en la pantalla principal."
        )
        self.label_resumen.setWordWrap(True)
        layout.addWidget(self.label_resumen)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Cliente",
                "DNI",
                "Patente",
                "Modelo",
                "Espacio",
                "Entrada",
                "Vencimiento",
                "Monto",
                "Estado",
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        acciones = QHBoxLayout()
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_reactivar = QPushButton("Reactivar")
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_actualizar.setProperty("variant", "neutral")
        self.btn_reactivar.setProperty("variant", "success")
        self.btn_eliminar.setProperty("variant", "danger")
        self.btn_cerrar.setProperty("variant", "neutral")
        acciones.addWidget(self.btn_actualizar)
        acciones.addWidget(self.btn_reactivar)
        acciones.addWidget(self.btn_eliminar)
        acciones.addStretch(1)
        acciones.addWidget(self.btn_cerrar)
        layout.addLayout(acciones)

        self.btn_actualizar.clicked.connect(self._cargar)
        self.btn_reactivar.clicked.connect(self._reactivar)
        self.btn_eliminar.clicked.connect(self._eliminar)
        self.btn_cerrar.clicked.connect(self.accept)
        self.table.itemSelectionChanged.connect(self._actualizar_estado_acciones)
        if not self._es_dueno():
            self.btn_eliminar.setVisible(False)
            self.btn_eliminar.setEnabled(False)
        self._cargar()

    def _es_dueno(self):
        return (_rol_desde_widget(self) or "").strip().upper() == "DUENO"

    def _selected_contrato_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(Qt.UserRole)

    def _contar_pagos_contrato(self, id_contrato):
        if not id_contrato:
            return 0
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) AS cantidad FROM pagos_cochera WHERE id_contrato = ?",
                (id_contrato,),
            )
            row = cur.fetchone()
            return int((row["cantidad"] if row else 0) or 0)
        except sqlite3.Error:
            return 0
        finally:
            if conn:
                conn.close()

    def _actualizar_estado_acciones(self):
        id_contrato = self._selected_contrato_id()
        self.btn_reactivar.setEnabled(bool(id_contrato))
        if id_contrato:
            self.btn_reactivar.setToolTip(
                "Devuelve el contrato a la pantalla principal de Contratos como inactivo."
            )
        else:
            self.btn_reactivar.setToolTip("Selecciona un contrato del historial.")
        if not self.btn_eliminar.isVisible():
            return
        if not id_contrato:
            self.btn_eliminar.setEnabled(False)
            self.btn_eliminar.setToolTip("Selecciona un contrato del historial.")
            return
        pagos = self._contar_pagos_contrato(id_contrato)
        self.btn_eliminar.setEnabled(True)
        if pagos > 0:
            self.btn_eliminar.setToolTip(
                f"Elimina el contrato del historial y tambien sus {pagos} pago/s."
            )
        else:
            self.btn_eliminar.setToolTip("Elimina el contrato del historial.")

    def _cargar(self):
        self.table.setRowCount(0)
        rows = svc_listar_contratos()
        hoy = QDate.currentDate()
        cantidad = 0
        for row in rows:
            vista = _clasificar_contrato_vista(row, hoy=hoy)
            if vista["principal"]:
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            item_cliente = QTableWidgetItem(row["nombre"])
            item_cliente.setData(Qt.UserRole, row["id_contrato"])
            self.table.setItem(r, 0, item_cliente)
            self.table.setItem(r, 1, QTableWidgetItem(_formatear_documento(row["dni"])))
            self.table.setItem(r, 2, QTableWidgetItem(_formatear_patente(row["patente"] or "")))
            self.table.setItem(r, 3, QTableWidgetItem((row.get("modelo") or "").strip()))
            self.table.setItem(r, 4, QTableWidgetItem(row["codigo"]))
            self.table.setItem(r, 5, QTableWidgetItem(row["fecha_inicio"] or ""))
            self.table.setItem(r, 6, QTableWidgetItem(row["fecha_vencimiento"] or ""))
            self.table.setItem(
                r, 7, QTableWidgetItem(_fmt_money(float(row["monto_mensual"] or 0)))
            )
            item_estado = QTableWidgetItem(vista["estado"])
            self.table.setItem(r, 8, item_estado)

            estado = vista["estado"]
            if "VENCIDO" in estado:
                bg = QColor(127, 29, 29)
                fg = QColor(255, 255, 255)
            else:
                bg = QColor(55, 65, 81)
                fg = QColor(229, 231, 235)
            item_estado.setBackground(QBrush(bg))
            item_estado.setForeground(QBrush(fg))
            cantidad += 1

        if cantidad == 0:
            self.table.insertRow(0)
            item = QTableWidgetItem(
                "Todavia no hay contratos en historial.\n"
                "Cuando des de baja uno desde Contratos, aparecera aqui."
            )
            item.setFlags(Qt.NoItemFlags)
            self.table.setSpan(0, 0, 1, self.table.columnCount())
            self.table.setItem(0, 0, item)

        self.label_resumen.setText(
            f"Contratos en historial: {cantidad}. "
            "Aqui se muestran los contratos dados de baja."
        )
        self._actualizar_estado_acciones()

    def _reactivar(self):
        id_contrato = self._selected_contrato_id()
        if not id_contrato:
            QMessageBox.warning(
                self,
                "Historial",
                "Selecciona un contrato del historial para reactivarlo.",
            )
            return
        confirmar = QMessageBox.question(
            self,
            "Reactivar contrato",
            "El contrato volvera a la pantalla principal de Contratos como INACTIVO.\n"
            "Luego podras activarlo nuevamente desde Registro de pagos.\n\n"
            "Quieres continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if confirmar != QMessageBox.Yes:
            return
        try:
            resultado = svc_reactivar_contrato_desde_historial(id_contrato)
            _auditar(self, "Contrato reactivado", f"ID {id_contrato}")
            self._cargar()
            parent = self.parent()
            if parent is not None and hasattr(parent, "_cargar"):
                try:
                    parent._cargar()
                    if hasattr(parent, "_seleccionar_contrato"):
                        parent._seleccionar_contrato(id_contrato)
                except Exception:
                    pass
            fecha_venc = QDate.fromString(
                resultado.get("fecha_vencimiento") or "", "yyyy-MM-dd"
            )
            venc_txt = fecha_venc.toString("dd/MM/yyyy") if fecha_venc.isValid() else "-"
            ajuste = ""
            if resultado.get("vencimiento_ajustado"):
                ajuste = (
                    "\nSe ajusto el vencimiento porque el anterior ya habia pasado: "
                    f"{venc_txt}."
                )
            QMessageBox.information(
                self,
                "Historial",
                "Contrato reactivado.\n"
                "Ya volvio a la pantalla principal de Contratos como INACTIVO."
                f"{ajuste}",
            )
        except ValueError as e:
            QMessageBox.warning(self, "Historial", str(e))
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo reactivar el contrato.")

    def _eliminar(self):
        id_contrato = self._selected_contrato_id()
        if not id_contrato:
            QMessageBox.warning(
                self,
                "Historial",
                "Selecciona un contrato del historial para eliminarlo.",
            )
            return
        if not self._es_dueno():
            QMessageBox.warning(self, "Historial", "Solo DUENO puede eliminar contratos.")
            return
        pagos = self._contar_pagos_contrato(id_contrato)
        confirmar = QMessageBox.question(
            self,
            "Eliminar contrato",
            "Esto eliminara el contrato del historial definitivamente. Continuar?"
            + (
                f"\nTambien se eliminaran {pagos} pago/s asociados."
                if pagos > 0
                else ""
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmar != QMessageBox.Yes:
            return
        try:
            resultado = _eliminar_contrato_definitivo(id_contrato)
            if not resultado.get("ok"):
                QMessageBox.warning(
                    self,
                    "Historial",
                    "No se encontro el contrato para eliminar.",
                )
                return
            _auditar(
                self,
                "Contrato eliminado desde historial",
                f"ID {id_contrato} - pagos eliminados: {resultado.get('pagos', 0)}",
            )
            self._cargar()
            parent = self.parent()
            if parent is not None and hasattr(parent, "_cargar"):
                try:
                    parent._cargar()
                except Exception:
                    pass
        except sqlite3.IntegrityError:
            _mostrar_error(
                self,
                "Error",
                "No se pudo eliminar el contrato porque tiene datos relacionados.",
            )
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo eliminar el contrato.")


class PagoActivacionDialog(QDialog):
    def __init__(self, monto_base, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Registrar primer pago")
        self.setMinimumWidth(360)
        self._monto_base = float(monto_base or 0.0)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.label_info = QLabel("Este pago activa el contrato y no modifica el vencimiento.")
        self.label_info.setWordWrap(True)
        self.input_monto = QDoubleSpinBox()
        self.input_monto.setDecimals(2)
        self.input_monto.setRange(0.0, 999999.0)
        self.input_monto.setValue(self._monto_base)
        _configurar_spinbox_numerico(self.input_monto)
        self.combo_metodo = QComboBox()
        self.combo_metodo.addItems(["Efectivo", "Transferencia", "Tarjeta", "Otro"])
        form.addRow("Info", self.label_info)
        form.addRow("Monto a cobrar", self.input_monto)
        form.addRow("Metodo", self.combo_metodo)
        layout.addLayout(form)

        botones = QHBoxLayout()
        self.btn_ok = QPushButton("Aceptar")
        self.btn_cancel = QPushButton("Cancelar")
        botones.addStretch(1)
        botones.addWidget(self.btn_ok)
        botones.addWidget(self.btn_cancel)
        layout.addLayout(botones)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        _instalar_enter_navegacion(
            self,
            {
                self.input_monto: self.combo_metodo,
                self.combo_metodo: self.accept,
            },
        )

    def get_data(self):
        return float(self.input_monto.value()), self.combo_metodo.currentText()


class PagoCocheraDialog(QDialog):
    def __init__(self, monto_base, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Registrar pago")
        self.setMinimumWidth(360)
        self._monto_base = float(monto_base or 0.0)
        self._monto_fijado = False
        self._actualizando = False

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.input_meses = QSpinBox()
        self.input_meses.setRange(1, 24)
        self.input_meses.setValue(1)
        self.label_sugerido = QLabel(_fmt_money(self._monto_base))
        self.input_monto = QDoubleSpinBox()
        self.input_monto.setDecimals(2)
        self.input_monto.setRange(0.0, 999999.0)
        self.input_monto.setValue(self._monto_base)
        _configurar_spinbox_numerico(self.input_monto)
        self.combo_metodo = QComboBox()
        self.combo_metodo.addItems(["Efectivo", "Transferencia", "Tarjeta", "Otro"])

        form.addRow("Meses", self.input_meses)
        form.addRow("Sugerido", self.label_sugerido)
        form.addRow("Monto a cobrar", self.input_monto)
        form.addRow("Metodo", self.combo_metodo)
        layout.addLayout(form)

        botones = QHBoxLayout()
        self.btn_ok = QPushButton("Aceptar")
        self.btn_cancel = QPushButton("Cancelar")
        botones.addStretch(1)
        botones.addWidget(self.btn_ok)
        botones.addWidget(self.btn_cancel)
        layout.addLayout(botones)

        self.input_meses.valueChanged.connect(self._actualizar_sugerido)
        self.input_monto.valueChanged.connect(self._on_monto_changed)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        _instalar_enter_navegacion(
            self,
            {
                self.input_meses: self.input_monto,
                self.input_monto: self.combo_metodo,
                self.combo_metodo: self.accept,
            },
        )

    def _actualizar_sugerido(self):
        meses = self.input_meses.value()
        sugerido = self._monto_base * meses
        self.label_sugerido.setText(_fmt_money(sugerido))
        if not self._monto_fijado:
            self._actualizando = True
            self.input_monto.setValue(sugerido)
            self._actualizando = False

    def _on_monto_changed(self, _):
        if self._actualizando:
            return
        if self.input_monto.hasFocus():
            self._monto_fijado = True

    def get_data(self):
        return (
            self.input_meses.value(),
            float(self.input_monto.value()),
            self.combo_metodo.currentText(),
        )


class ClientesDialog(QDialog):
    def __init__(self, parent=None, rol=None):
        super().__init__(parent)
        self.rol = rol
        self.setWindowTitle("Clientes y vehiculos")
        self.setMinimumWidth(1100)
        self.setMinimumHeight(640)
        self.resize(1180, 700)

        layout = QHBoxLayout(self)

        panel_lista = QVBoxLayout()
        filtro = QHBoxLayout()
        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText("Buscar por nombre o DNI")
        self.btn_buscar = QPushButton("Buscar")
        self.btn_buscar.setProperty("variant", "info")
        filtro.addWidget(self.input_buscar)
        filtro.addWidget(self.btn_buscar)
        panel_lista.addLayout(filtro)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Nombre", "DNI", "Telefono", "Activo"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        panel_lista.addWidget(self.table)

        acciones = QHBoxLayout()
        self.btn_activar = QPushButton("Activar")
        self.btn_desactivar = QPushButton("Desactivar")
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_activar.setProperty("variant", "success")
        self.btn_desactivar.setProperty("variant", "warning")
        self.btn_eliminar.setProperty("variant", "danger")
        acciones.addStretch(1)
        acciones.addWidget(self.btn_activar)
        acciones.addWidget(self.btn_desactivar)
        acciones.addWidget(self.btn_eliminar)
        panel_lista.addLayout(acciones)

        layout.addLayout(panel_lista, 3)

        panel_form = QVBoxLayout()
        form = QFormLayout()
        self.input_dni = QLineEdit()
        self.input_dni.setMaxLength(10)
        self.input_dni.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"[0-9.]{0,10}"), self.input_dni)
        )
        self.input_dni.editingFinished.connect(self._formatear_input_dni)
        self.input_nombre = QLineEdit()
        self.input_nombre.setMaxLength(80)
        self.input_nombre.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü' -]{0,80}"),
                self.input_nombre,
            )
        )
        self.input_direccion = QLineEdit()
        self.input_telefono = QLineEdit()
        self.input_nacimiento = QDateEdit()
        self.input_nacimiento.setCalendarPopup(True)
        self.input_nacimiento.setDate(QDate.currentDate().addYears(-18))
        form.addRow("DNI", self.input_dni)
        form.addRow("Nombre", self.input_nombre)
        form.addRow("Direccion", self.input_direccion)
        form.addRow("Telefono", self.input_telefono)
        form.addRow("Nacimiento", self.input_nacimiento)
        panel_form.addLayout(form)

        botones_cliente = QHBoxLayout()
        self.btn_nuevo = QPushButton("Nuevo")
        self.btn_guardar = QPushButton("Guardar")
        self.btn_nuevo.setProperty("variant", "success")
        self.btn_guardar.setProperty("variant", "success")
        botones_cliente.addWidget(self.btn_nuevo)
        botones_cliente.addWidget(self.btn_guardar)
        panel_form.addLayout(botones_cliente)

        panel_form.addSpacing(12)

        self.vehiculos_table = QTableWidget(0, 3)
        self.vehiculos_table.setHorizontalHeaderLabels(["Patente", "Modelo", "Tipo"])
        self.vehiculos_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.vehiculos_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.vehiculos_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        panel_form.addWidget(self.vehiculos_table)

        form_veh = QHBoxLayout()
        self.input_patente = QLineEdit()
        self.input_patente.setPlaceholderText("Patente")
        self.input_patente.setMaxLength(10)
        self.input_patente.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(r"[A-Za-z0-9\s]{0,10}"),
                self.input_patente,
            )
        )
        self.input_patente.editingFinished.connect(self._formatear_input_patente)
        self.input_modelo = QLineEdit()
        self.input_modelo.setPlaceholderText("Modelo (opcional)")
        self._historial_modelos = self._cargar_historial_modelos()
        self._modelo_historial_qt = QStringListModel(self._historial_modelos, self)
        self._completer_modelos = QCompleter(self._modelo_historial_qt, self)
        self._completer_modelos.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer_modelos.setFilterMode(Qt.MatchContains)
        self._completer_modelos.setCompletionMode(QCompleter.PopupCompletion)
        self.input_modelo.setCompleter(self._completer_modelos)
        self.combo_tipo_vehiculo = QComboBox()
        self.combo_tipo_vehiculo.addItem("Seleccionar tipo...", "")
        self.combo_tipo_vehiculo.addItem("Auto", "AUTO")
        self.combo_tipo_vehiculo.addItem("Moto", "MOTO")
        self.combo_tipo_vehiculo.addItem("Camioneta", "CAMIONETA")
        self.btn_agregar_veh = QPushButton("Agregar vehiculo")
        self.btn_eliminar_veh = QPushButton("Eliminar vehiculo")
        self.btn_agregar_veh.setProperty("variant", "success")
        self.btn_eliminar_veh.setProperty("variant", "danger")
        form_veh.addWidget(self.input_patente)
        form_veh.addWidget(self.input_modelo)
        form_veh.addWidget(self.combo_tipo_vehiculo)
        form_veh.addWidget(self.btn_agregar_veh)
        form_veh.addWidget(self.btn_eliminar_veh)
        panel_form.addLayout(form_veh)

        self.btn_crear_contrato = QPushButton("Crear contrato")
        self.btn_crear_contrato.setProperty("variant", "info")
        self.btn_estado_cuenta = QPushButton("Estado de cuenta")
        self.btn_estado_cuenta.setProperty("variant", "info")
        self.btn_whatsapp = QPushButton("Abrir WhatsApp")
        self.btn_whatsapp.setProperty("variant", "success")
        self.btn_whatsapp.setIcon(_icono_whatsapp(18))
        self.btn_whatsapp.setIconSize(QSize(16, 16))
        acciones_cliente = QHBoxLayout()
        acciones_cliente.addWidget(self.btn_crear_contrato)
        acciones_cliente.addWidget(self.btn_estado_cuenta)
        acciones_cliente.addWidget(self.btn_whatsapp)
        panel_form.addLayout(acciones_cliente)
        panel_form.addStretch(1)
        layout.addLayout(panel_form, 4)

        self._configurar_enter_navegacion()

        self.btn_activar.clicked.connect(lambda: self._cambiar_activo(1))
        self.btn_desactivar.clicked.connect(lambda: self._cambiar_activo(0))
        self.btn_eliminar.clicked.connect(self._eliminar_cliente)
        self.btn_nuevo.clicked.connect(self._nuevo_cliente)
        self.btn_guardar.clicked.connect(self._guardar_cliente)
        self.btn_buscar.clicked.connect(self._buscar)
        self.btn_agregar_veh.clicked.connect(self._agregar_vehiculo)
        self.btn_eliminar_veh.clicked.connect(self._eliminar_vehiculo)
        self.btn_crear_contrato.clicked.connect(self._crear_contrato_desde_cliente)
        self.btn_estado_cuenta.clicked.connect(self._abrir_estado_cuenta)
        self.btn_whatsapp.clicked.connect(self._enviar_whatsapp_cliente)
        self.table.itemSelectionChanged.connect(self._seleccion_changed)
        self.vehiculos_table.itemSelectionChanged.connect(self._actualizar_estado_interaccion_cliente)
        self._atajo_f7 = QShortcut(QKeySequence("F7"), self)
        self._atajo_f7.setContext(Qt.WidgetWithChildrenShortcut)
        self._atajo_f7.activated.connect(self._atajo_abrir_contratos)

        es_admin = (self.rol or "").upper() == "DUENO"
        if not es_admin:
            self.btn_eliminar.setEnabled(False)
            self.btn_eliminar.setVisible(False)

        self._cargar()
        self._actualizar_snapshot_form()
        self._actualizar_estado_interaccion_cliente()

    def _atajo_abrir_contratos(self):
        if self.isActiveWindow():
            self._crear_contrato_desde_cliente()

    def _configurar_enter_navegacion(self):
        self._enter_next_map = {
            self.input_dni: self.input_nombre,
            self.input_nombre: self.input_direccion,
            self.input_direccion: self.input_telefono,
            self.input_telefono: self.input_nacimiento,
            self.input_nacimiento: self.btn_guardar,
            self.input_patente: self.input_modelo,
            self.input_modelo: self.combo_tipo_vehiculo,
            self.combo_tipo_vehiculo: self.btn_agregar_veh,
        }
        for widget in self._enter_next_map:
            widget.installEventFilter(self)

    @staticmethod
    def _normalizar_texto_modelo(texto):
        return " ".join(str(texto or "").split()).strip()

    def _cargar_historial_modelos(self):
        raw = _config_get("historial_modelos", "") or ""
        modelos = []
        vistos = set()
        for linea in raw.splitlines():
            modelo = self._normalizar_texto_modelo(linea)
            if not modelo:
                continue
            clave = modelo.casefold()
            if clave in vistos:
                continue
            vistos.add(clave)
            modelos.append(modelo)
        return modelos

    def _guardar_historial_modelos(self):
        payload = "\n".join(self._historial_modelos[:200])
        _config_set("historial_modelos", payload)

    def _actualizar_completer_modelos(self):
        if hasattr(self, "_modelo_historial_qt"):
            self._modelo_historial_qt.setStringList(self._historial_modelos)

    def _agregar_modelo_historial(self, modelo):
        modelo_txt = self._normalizar_texto_modelo(modelo)
        if not modelo_txt:
            return
        clave = modelo_txt.casefold()
        nuevos = [modelo_txt]
        for existente in self._historial_modelos:
            if existente.casefold() == clave:
                continue
            nuevos.append(existente)
        self._historial_modelos = nuevos[:200]
        self._guardar_historial_modelos()
        self._actualizar_completer_modelos()

    def eventFilter(self, obj, event):
        if (
            obj in getattr(self, "_enter_next_map", {})
            and event.type() == QEvent.KeyPress
            and event.key() in (Qt.Key_Return, Qt.Key_Enter)
        ):
            siguiente = self._enter_next_map.get(obj)
            if siguiente is not None:
                siguiente.setFocus()
                return True
        return super().eventFilter(obj, event)

    def _selected_cliente_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(Qt.UserRole)

    def _selected_cliente_activo(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        activo = item.data(Qt.UserRole + 1)
        if activo is None:
            return None
        return int(activo) == 1

    def _selected_contratos_activos(self):
        row = self.table.currentRow()
        if row < 0:
            return 0
        item = self.table.item(row, 0)
        if not item:
            return 0
        try:
            return int(item.data(Qt.UserRole + 2) or 0)
        except Exception:
            return 0

    def _seleccionar_cliente_en_tabla(self, cliente_id):
        if not cliente_id:
            return
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.data(Qt.UserRole) == cliente_id:
                self.table.setCurrentCell(r, 0)
                return

    def _contar_contratos_activos_cliente(self, cliente_id):
        if not cliente_id:
            return 0
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) AS cantidad "
                "FROM cochera_contratos "
                "WHERE id_cliente = ? AND activo = 1",
                (cliente_id,),
            )
            row = cur.fetchone()
            return int((row["cantidad"] if row else 0) or 0)
        except sqlite3.Error:
            return 0
        finally:
            if conn:
                conn.close()

    def _selected_vehiculo_id(self):
        row = self.vehiculos_table.currentRow()
        if row < 0:
            return None
        item = self.vehiculos_table.item(row, 0)
        if not item:
            return None
        return item.data(Qt.UserRole)

    def _selected_vehiculo_patente(self):
        row = self.vehiculos_table.currentRow()
        if row < 0:
            return ""
        item = self.vehiculos_table.item(row, 0)
        if not item:
            return ""
        return _normalizar_patente(item.text())

    def _contar_contratos_vehiculo(self, vehiculo_id, conn=None):
        if not vehiculo_id:
            return 0
        own_conn = conn is None
        try:
            conn = conn or get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(DISTINCT cc.id_contrato) AS cantidad "
                "FROM vehiculos v "
                "JOIN cochera_contratos cc ON cc.id_cliente = v.id_cliente "
                "WHERE v.id_vehiculo = ?",
                (vehiculo_id,),
            )
            row = cur.fetchone()
            return int((row["cantidad"] if row else 0) or 0)
        except sqlite3.Error:
            return 0
        finally:
            if own_conn and conn:
                conn.close()

    def _contar_movimientos_vehiculo(self, vehiculo_id, conn=None):
        if not vehiculo_id:
            return 0
        own_conn = conn is None
        try:
            conn = conn or get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) AS cantidad "
                "FROM movimientos "
                "WHERE id_vehiculo = ?",
                (vehiculo_id,),
            )
            row = cur.fetchone()
            return int((row["cantidad"] if row else 0) or 0)
        except sqlite3.Error:
            return 0
        finally:
            if own_conn and conn:
                conn.close()

    def _resumen_dependencias_cliente(self, cliente_id, conn=None):
        datos = {
            "vehiculos": 0,
            "contratos": 0,
            "movimientos": 0,
            "espacios": 0,
        }
        if not cliente_id:
            return datos
        own_conn = conn is None
        try:
            conn = conn or get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM vehiculos WHERE id_cliente = ?) AS vehiculos, "
                "(SELECT COUNT(*) FROM cochera_contratos WHERE id_cliente = ?) AS contratos, "
                "(SELECT COUNT(*) FROM vehiculos v "
                " JOIN movimientos m ON m.id_vehiculo = v.id_vehiculo "
                " WHERE v.id_cliente = ?) AS movimientos, "
                "(SELECT COUNT(*) FROM espacios WHERE id_cliente = ?) AS espacios",
                (cliente_id, cliente_id, cliente_id, cliente_id),
            )
            row = cur.fetchone()
            if row:
                for clave in datos:
                    datos[clave] = int((row[clave] if row[clave] is not None else 0) or 0)
            return datos
        except sqlite3.Error:
            return datos
        finally:
            if own_conn and conn:
                conn.close()

    def _validar_cliente_activo_seleccionado(self, accion):
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(
                self,
                "Cliente",
                "Selecciona un cliente en la lista para continuar.",
            )
            return False
        estado = _consultar_estado_cliente(cliente_id)
        if not estado:
            QMessageBox.warning(
                self,
                "Cliente",
                "No se encontro el cliente seleccionado.\n"
                "Actualiza la lista y vuelve a intentarlo.",
            )
            return False
        if not estado["activo"]:
            QMessageBox.warning(
                self,
                "Cliente desactivado",
                f"No se puede {accion}: el cliente esta desactivado.\n"
                "Activalo para continuar.",
            )
            return False
        return True

    def _actualizar_estado_interaccion_cliente(self):
        cliente_id = self._selected_cliente_id()
        hay_sel = cliente_id is not None
        activo = self._selected_cliente_activo()
        contratos_activos = self._selected_contratos_activos()
        vehiculo_id = self._selected_vehiculo_id()

        if activo is None and hay_sel:
            estado = _consultar_estado_cliente(cliente_id)
            activo = bool(estado and estado["activo"])
            contratos_activos = self._contar_contratos_activos_cliente(cliente_id)
        if activo is None:
            activo = True

        puede_interactuar = (not hay_sel) or bool(activo)
        es_admin = (self.rol or "").upper() == "DUENO"
        contratos_vehiculo = self._contar_contratos_vehiculo(vehiculo_id) if vehiculo_id else 0
        movimientos_vehiculo = self._contar_movimientos_vehiculo(vehiculo_id) if vehiculo_id else 0

        for widget in (
            self.input_dni,
            self.input_nombre,
            self.input_direccion,
            self.input_telefono,
            self.input_nacimiento,
            self.input_patente,
            self.input_modelo,
            self.combo_tipo_vehiculo,
            self.vehiculos_table,
            self.btn_guardar,
            self.btn_agregar_veh,
            self.btn_eliminar_veh,
            self.btn_crear_contrato,
            self.btn_estado_cuenta,
            self.btn_whatsapp,
        ):
            widget.setEnabled(puede_interactuar)

        self.btn_eliminar_veh.setEnabled(
            bool(
                puede_interactuar
                and hay_sel
                and vehiculo_id
                and contratos_vehiculo <= 0
                and movimientos_vehiculo <= 0
            )
        )
        self.btn_activar.setEnabled(hay_sel and not bool(activo))
        self.btn_desactivar.setEnabled(hay_sel and bool(activo) and contratos_activos <= 0)
        if es_admin and self.btn_eliminar.isVisible():
            self.btn_eliminar.setEnabled(hay_sel and bool(activo))

        if hay_sel and not bool(activo):
            self.btn_guardar.setToolTip("Cliente desactivado. Activalo para editar.")
            self.btn_agregar_veh.setToolTip("Cliente desactivado. Activalo para operar.")
            self.btn_eliminar_veh.setToolTip("Cliente desactivado. Activalo para operar.")
            self.btn_crear_contrato.setToolTip("Cliente desactivado. Activalo para operar.")
            self.btn_estado_cuenta.setToolTip("Cliente desactivado. Activalo para operar.")
            self.btn_whatsapp.setToolTip("Cliente desactivado. Activalo para operar.")
            self.btn_desactivar.setToolTip("")
        elif hay_sel and vehiculo_id and contratos_vehiculo > 0:
            self.btn_guardar.setToolTip("")
            self.btn_agregar_veh.setToolTip("")
            self.btn_eliminar_veh.setToolTip(
                "No se puede eliminar esta patente mientras el cliente tenga contrato/s asociado/s."
            )
            self.btn_crear_contrato.setToolTip("")
            self.btn_estado_cuenta.setToolTip("")
            self.btn_whatsapp.setToolTip("")
            self.btn_desactivar.setToolTip("")
        elif hay_sel and vehiculo_id and movimientos_vehiculo > 0:
            self.btn_guardar.setToolTip("")
            self.btn_agregar_veh.setToolTip("")
            self.btn_eliminar_veh.setToolTip(
                "No se puede eliminar esta patente porque tiene movimientos registrados."
            )
            self.btn_crear_contrato.setToolTip("")
            self.btn_estado_cuenta.setToolTip("")
            self.btn_whatsapp.setToolTip("")
            self.btn_desactivar.setToolTip("")
        elif hay_sel and bool(activo) and contratos_activos > 0:
            self.btn_guardar.setToolTip("")
            self.btn_agregar_veh.setToolTip("")
            self.btn_eliminar_veh.setToolTip(
                "Selecciona una patente sin contratos asociados para poder eliminarla."
                if not vehiculo_id
                else ""
            )
            self.btn_crear_contrato.setToolTip("")
            self.btn_estado_cuenta.setToolTip("")
            self.btn_whatsapp.setToolTip("")
            self.btn_desactivar.setToolTip(
                "No se puede desactivar: tiene contrato/s activo/s. Primero desactiva el contrato."
            )
        else:
            self.btn_guardar.setToolTip("")
            self.btn_agregar_veh.setToolTip("")
            self.btn_eliminar_veh.setToolTip("Selecciona un vehiculo." if hay_sel and not vehiculo_id else "")
            self.btn_crear_contrato.setToolTip("")
            self.btn_estado_cuenta.setToolTip("")
            self.btn_whatsapp.setToolTip("")
            self.btn_desactivar.setToolTip("")

    def _seleccion_changed(self):
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            self._actualizar_estado_interaccion_cliente()
            return
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM clientes WHERE id_cliente = ?", (cliente_id,))
            row = cur.fetchone()
            if not row:
                return
            self.input_dni.setText(_formatear_documento(row["dni"] or ""))
            self.input_nombre.setText(row["nombre"])
            self.input_direccion.setText(row["direccion"] or "")
            self.input_telefono.setText(row["telefono"] or "")
            fecha = QDate.fromString(row["fecha_nacimiento"] or "", "yyyy-MM-dd")
            if fecha.isValid():
                self.input_nacimiento.setDate(fecha)
            self._cargar_vehiculos(cliente_id)
            self._actualizar_snapshot_form()
            self._actualizar_estado_interaccion_cliente()
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()

    def _cargar(self):
        self._cargar_filtrado(None)

    def _cargar_filtrado(self, texto):
        self.table.setRowCount(0)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            if texto:
                like_nombre = f"%{texto}%"
                texto_dni = _solo_digitos(texto)
                like_dni = f"%{texto_dni or texto}%"
                cur.execute(
                    "SELECT c.id_cliente, c.nombre, c.dni, c.telefono, c.activo, "
                    "(SELECT COUNT(*) FROM cochera_contratos cc "
                    " WHERE cc.id_cliente = c.id_cliente AND cc.activo = 1) AS contratos_activos "
                    "FROM clientes c WHERE c.nombre LIKE ? OR c.dni LIKE ? "
                    "ORDER BY c.nombre",
                    (like_nombre, like_dni),
                )
            else:
                cur.execute(
                    "SELECT c.id_cliente, c.nombre, c.dni, c.telefono, c.activo, "
                    "(SELECT COUNT(*) FROM cochera_contratos cc "
                    " WHERE cc.id_cliente = c.id_cliente AND cc.activo = 1) AS contratos_activos "
                    "FROM clientes c ORDER BY c.nombre"
                )
            for row in cur.fetchall():
                r = self.table.rowCount()
                self.table.insertRow(r)
                item_nombre = QTableWidgetItem(row["nombre"])
                item_nombre.setData(Qt.UserRole, row["id_cliente"])
                item_nombre.setData(Qt.UserRole + 1, int(row["activo"] or 0))
                item_nombre.setData(Qt.UserRole + 2, int(row["contratos_activos"] or 0))
                self.table.setItem(r, 0, item_nombre)
                self.table.setItem(r, 1, QTableWidgetItem(_formatear_documento(row["dni"])))
                self.table.setItem(r, 2, QTableWidgetItem(row["telefono"] or ""))
                activo = "SI" if row["activo"] == 1 else "NO"
                self.table.setItem(r, 3, QTableWidgetItem(activo))
                if int(row["activo"] or 0) != 1:
                    for c in range(4):
                        item = self.table.item(r, c)
                        if item:
                            item.setForeground(QBrush(QColor(140, 140, 140)))
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo cargar clientes.")
        finally:
            if conn:
                conn.close()
        self.vehiculos_table.setRowCount(0)
        self._actualizar_estado_interaccion_cliente()

    def _buscar(self):
        texto = self.input_buscar.text().strip()
        self._cargar_filtrado(texto if texto else None)

    def _limpiar_busqueda(self):
        self.input_buscar.clear()
        self._cargar()

    def _snapshot_form(self):
        return {
            "dni": _solo_digitos(self.input_dni.text().strip()),
            "nombre": self.input_nombre.text().strip(),
            "direccion": self.input_direccion.text().strip(),
            "telefono": self.input_telefono.text().strip(),
            "nacimiento": self.input_nacimiento.date().toString("yyyy-MM-dd"),
            "patente": self.input_patente.text().strip().upper(),
            "modelo": self.input_modelo.text().strip(),
            "tipo_vehiculo": self.combo_tipo_vehiculo.currentData(),
        }

    def _actualizar_snapshot_form(self):
        self._form_snapshot = self._snapshot_form()

    def _hay_cambios_sin_guardar(self):
        base = getattr(self, "_form_snapshot", None)
        if base is None:
            return False
        return self._snapshot_form() != base

    def _formulario_cliente_vacio(self):
        snap = self._snapshot_form()
        return (
            not snap["dni"]
            and not snap["nombre"]
            and not snap["direccion"]
            and not snap["telefono"]
            and not snap["patente"]
            and not snap["modelo"]
            and not str(snap["tipo_vehiculo"] or "").strip()
        )

    def _nuevo_cliente(self):
        if self._formulario_cliente_vacio():
            QMessageBox.information(
                self,
                "Cliente",
                "El formulario ya esta vacio.\nCompleta los datos del cliente antes de usar este boton.",
            )
            return
        if self._hay_cambios_sin_guardar():
            confirmar = QMessageBox.question(
                self,
                "Cambios sin guardar",
                "No guardaste el cliente actual. Seguro que quieres limpiar el formulario?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirmar != QMessageBox.Yes:
                return
        self._limpiar_form()

    def _limpiar_form(self):
        self.table.clearSelection()
        self.input_dni.clear()
        self.input_nombre.clear()
        self.input_direccion.clear()
        self.input_telefono.clear()
        self.input_patente.clear()
        self.input_modelo.clear()
        self.combo_tipo_vehiculo.setCurrentIndex(0)
        self.input_nacimiento.setDate(QDate.currentDate().addYears(-18))
        self.vehiculos_table.setRowCount(0)
        self._actualizar_snapshot_form()
        self._actualizar_estado_interaccion_cliente()

    def _formatear_input_dni(self):
        dni = _solo_digitos(self.input_dni.text().strip())
        self.input_dni.setText(_formatear_documento(dni))
        return dni

    def _guardar_cliente(self):
        dni = self._formatear_input_dni()
        nombre = " ".join(self.input_nombre.text().strip().split())
        direccion = self.input_direccion.text().strip()
        telefono = self.input_telefono.text().strip()
        fecha = self.input_nacimiento.date().toString("yyyy-MM-dd")

        if self._formulario_cliente_vacio():
            QMessageBox.information(
                self,
                "Cliente",
                "El formulario esta vacio.\nCompleta al menos DNI y nombre antes de guardar.",
            )
            return False
        if not _dni_longitud_valida(dni):
            QMessageBox.warning(
                self,
                "Datos",
                "El DNI debe tener 7 u 8 numeros.",
            )
            return False
        if not nombre:
            QMessageBox.warning(self, "Datos", "El nombre es obligatorio.")
            return False
        if not direccion:
            QMessageBox.warning(self, "Datos", "La direccion es obligatoria.")
            return False
        if not telefono:
            QMessageBox.warning(self, "Datos", "El telefono es obligatorio.")
            return False
        if not _nombre_cliente_valido(nombre):
            QMessageBox.warning(
                self,
                "Datos",
                "El nombre solo puede contener letras y espacios.",
            )
            return False
        self.input_nombre.setText(nombre)
        if not _antirebote_iniciar(self, "clientes_guardar"):
            return False

        cliente_id = self._selected_cliente_id()
        if cliente_id and not self._validar_cliente_activo_seleccionado("guardar cambios"):
            return False
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            if cliente_id:
                cur.execute(
                    "UPDATE clientes SET dni = ?, nombre = ?, direccion = ?, telefono = ?, "
                    "fecha_nacimiento = ? WHERE id_cliente = ?",
                    (dni, nombre, direccion, telefono, fecha, cliente_id),
                )
                accion = "Cliente actualizado"
            else:
                cur.execute(
                    "INSERT INTO clientes (dni, nombre, direccion, telefono, fecha_nacimiento, activo) "
                    "VALUES (?, ?, ?, ?, ?, 1)",
                    (dni, nombre, direccion, telefono, fecha),
                )
                accion = "Cliente creado"
            conn.commit()
            _auditar(self, accion, f"{nombre} - DNI {_formatear_documento(dni)}")
            self._cargar()
            self._limpiar_form()
            return True
        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self,
                "DNI",
                "Ese DNI ya existe en el sistema.\n"
                "Busca el cliente y editalo en lugar de crear uno nuevo.",
            )
            return False
        except sqlite3.Error:
            _mostrar_error(
                self,
                "Error",
                "No se pudo guardar el cliente.\n"
                "Verifica los datos e intenta nuevamente.",
            )
            return False
        finally:
            if conn:
                conn.close()
            _antirebote_finalizar(self, "clientes_guardar", cooldown_ms=650)

    def closeEvent(self, event):
        if not self._hay_cambios_sin_guardar():
            event.accept()
            return
        respuesta = _confirmar_guardado_pendiente(
            self,
            "Hay cambios en el cliente actual.\nQuieres guardarlos antes de salir?",
        )
        if respuesta == QMessageBox.Cancel:
            event.ignore()
            return
        if respuesta == QMessageBox.No:
            event.accept()
            return
        if self._guardar_cliente():
            event.accept()
        else:
            event.ignore()

    def _cambiar_activo(self, activo):
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(
                self,
                "Cliente",
                "Selecciona un cliente en la lista antes de activarlo o desactivarlo.",
            )
            return
        if int(activo or 0) == 0:
            contratos_activos = self._contar_contratos_activos_cliente(cliente_id)
            if contratos_activos > 0:
                QMessageBox.warning(
                    self,
                    "Cliente",
                    "No se puede desactivar este cliente porque tiene "
                    f"{contratos_activos} contrato/s activo/s.\n"
                    "Primero desactiva el/los contrato/s.",
                )
                self._actualizar_estado_interaccion_cliente()
                return
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("UPDATE clientes SET activo = ? WHERE id_cliente = ?", (activo, cliente_id))
            conn.commit()
            accion = "Cliente activado" if activo == 1 else "Cliente desactivado"
            detalle = self.input_dni.text().strip()
            _auditar(self, accion, f"DNI {detalle}" if detalle else "")
            self._cargar()
            self._seleccionar_cliente_en_tabla(cliente_id)
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo actualizar el cliente.")
        finally:
            if conn:
                conn.close()

    def _eliminar_cliente(self):
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(
                self,
                "Cliente",
                "Selecciona un cliente en la lista para eliminarlo.",
            )
            return
        if not self._validar_cliente_activo_seleccionado("eliminar el cliente"):
            return
        if not _antirebote_iniciar(self, "clientes_eliminar"):
            return
        try:
            confirmar = QMessageBox.question(
                self,
                "Eliminar cliente",
                "Esto eliminara el cliente y sus vehiculos. Continuar?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirmar != QMessageBox.Yes:
                return
            conn = None
            try:
                conn = get_connection()
                cur = conn.cursor()
                deps = self._resumen_dependencias_cliente(cliente_id, conn=conn)
                if deps["contratos"] > 0 or deps["movimientos"] > 0:
                    partes = []
                    if deps["contratos"] > 0:
                        partes.append(f"{deps['contratos']} contrato/s")
                    if deps["movimientos"] > 0:
                        partes.append(f"{deps['movimientos']} movimiento/s")
                    detalle = ", ".join(partes)
                    QMessageBox.warning(
                        self,
                        "Cliente",
                        "No se puede eliminar el cliente porque tiene historial asociado.\n"
                        f"Dependencias detectadas: {detalle}.\n"
                        "Si quieres conservar el historial, desactivalo en lugar de eliminarlo.",
                    )
                    return
                cur.execute(
                    "UPDATE espacios SET id_cliente = NULL WHERE id_cliente = ?",
                    (cliente_id,),
                )
                cur.execute("DELETE FROM vehiculos WHERE id_cliente = ?", (cliente_id,))
                cur.execute("DELETE FROM clientes WHERE id_cliente = ?", (cliente_id,))
                conn.commit()
                detalle = (
                    f"{self.input_nombre.text().strip()} - DNI {self.input_dni.text().strip()}".strip()
                )
                _auditar(self, "Cliente eliminado", detalle)
                self._cargar()
                self._limpiar_form()
            except sqlite3.IntegrityError:
                _mostrar_error(
                    self,
                    "Error",
                    "No se pudo eliminar el cliente porque tiene datos relacionados.",
                )
            except sqlite3.Error:
                _mostrar_error(self, "Error", "No se pudo eliminar el cliente.")
            finally:
                if conn:
                    conn.close()
        finally:
            _antirebote_finalizar(self, "clientes_eliminar", cooldown_ms=700)

    def _cargar_vehiculos(self, cliente_id):
        self.vehiculos_table.setRowCount(0)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT id_vehiculo, patente, modelo, "
                "COALESCE(NULLIF(TRIM(tipo_vehiculo), ''), 'AUTO') AS tipo_vehiculo "
                "FROM vehiculos WHERE id_cliente = ?",
                (cliente_id,),
            )
            for row in cur.fetchall():
                r = self.vehiculos_table.rowCount()
                self.vehiculos_table.insertRow(r)
                item = QTableWidgetItem(_formatear_patente(row["patente"]))
                item.setData(Qt.UserRole, row["id_vehiculo"])
                self.vehiculos_table.setItem(r, 0, item)
                self.vehiculos_table.setItem(r, 1, QTableWidgetItem(row["modelo"] or ""))
                self.vehiculos_table.setItem(
                    r, 2, QTableWidgetItem(_texto_tipo_vehiculo(row["tipo_vehiculo"]))
                )
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()

    def _formatear_input_patente(self):
        texto = self.input_patente.text()
        if not texto:
            return
        patente_fmt = _formatear_patente(texto)
        self.input_patente.setText(patente_fmt)
        if _patente_es_moto(texto) and _tipo_vehiculo_habilitado_cochera("MOTO"):
            idx = self.combo_tipo_vehiculo.findData("MOTO")
            if idx >= 0:
                self.combo_tipo_vehiculo.setCurrentIndex(idx)

    def _agregar_vehiculo(self):
        if not self._validar_cliente_activo_seleccionado("agregar vehiculos"):
            return
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(
                self,
                "Cliente",
                "Selecciona un cliente en la lista antes de agregarle una patente.",
            )
            return
        patente = _normalizar_patente(self.input_patente.text())
        self.input_patente.setText(_formatear_patente(patente))
        if not patente:
            QMessageBox.warning(
                self,
                "Patente",
                "Escribe una patente antes de agregar el vehiculo al cliente.",
            )
            return
        if not _patente_formato_valido(patente):
            QMessageBox.warning(
                self,
                "Patente",
                "Patente invalida. Formatos validos: AA 123 AA, AAA 123 o 123 ABC.",
            )
            return
        if _patente_es_moto(patente):
            if not _tipo_vehiculo_habilitado_cochera("MOTO"):
                QMessageBox.warning(
                    self,
                    "Tipo no permitido",
                    "El tipo Moto no esta habilitado para cochera.\n"
                    "Revisalo en Configuracion > Sistema > Tipos en cochera.",
                )
                return
            idx = self.combo_tipo_vehiculo.findData("MOTO")
            if idx >= 0:
                self.combo_tipo_vehiculo.setCurrentIndex(idx)
        if not _antirebote_iniciar(self, "clientes_agregar_vehiculo"):
            return
        modelo = self.input_modelo.text().strip()
        if modelo:
            modelo = " ".join(modelo.split())
        tipo_raw = self.combo_tipo_vehiculo.currentData()
        if not str(tipo_raw or "").strip():
            QMessageBox.warning(
                self,
                "Vehiculo",
                "No se establecio el tipo de vehiculo.\nSelecciona si la patente corresponde a Auto, Moto o Camioneta antes de agregarla.",
            )
            return
        tipo_vehiculo = _normalizar_tipo_vehiculo(tipo_raw)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO vehiculos (patente, modelo, tipo_vehiculo, id_cliente) "
                "VALUES (?, ?, ?, ?)",
                (patente, modelo if modelo else None, tipo_vehiculo, cliente_id),
            )
            conn.commit()
            detalle = f"Patente {patente} - DNI {self.input_dni.text().strip()}"
            if modelo:
                detalle = f"{detalle} - Modelo {modelo}"
            detalle = f"{detalle} - Tipo {_texto_tipo_vehiculo(tipo_vehiculo)}"
            _auditar(self, "Vehiculo agregado", detalle)
            if modelo:
                self._agregar_modelo_historial(modelo)
            self.input_patente.clear()
            self.input_modelo.clear()
            self.combo_tipo_vehiculo.setCurrentIndex(0)
            self._cargar_vehiculos(cliente_id)
        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self,
                "Patente",
                "Esa patente ya existe en el sistema.\n"
                "Revisa si ya fue cargada para este u otro cliente.",
            )
        except sqlite3.Error:
            _mostrar_error(
                self,
                "Error",
                "No se pudo agregar la patente al cliente.\n"
                "Intenta nuevamente en unos segundos.",
            )
        finally:
            if conn:
                conn.close()
            _antirebote_finalizar(self, "clientes_agregar_vehiculo", cooldown_ms=650)

    def _eliminar_vehiculo(self):
        if not self._validar_cliente_activo_seleccionado("eliminar vehiculos"):
            return
        row = self.vehiculos_table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self,
                "Vehiculo",
                "Selecciona una patente de la lista antes de eliminarla.",
            )
            return
        item = self.vehiculos_table.item(row, 0)
        if not item:
            QMessageBox.warning(
                self,
                "Vehiculo",
                "Selecciona una patente de la lista antes de eliminarla.",
            )
            return
        if not _antirebote_iniciar(self, "clientes_eliminar_vehiculo"):
            return
        veh_id = item.data(Qt.UserRole)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            contratos_asociados = self._contar_contratos_vehiculo(veh_id, conn=conn)
            if contratos_asociados > 0:
                QMessageBox.warning(
                    self,
                    "Vehiculo",
                    "No se puede eliminar esta patente mientras el cliente tenga contrato/s asociado/s.\n"
                    "Primero elimina o da de baja el contrato correspondiente.",
                )
                return
            movimientos_asociados = self._contar_movimientos_vehiculo(veh_id, conn=conn)
            if movimientos_asociados > 0:
                QMessageBox.warning(
                    self,
                    "Vehiculo",
                    "No se puede eliminar esta patente porque tiene movimientos registrados.\n"
                    "Se conserva para mantener el historial.",
                )
                return
            cur.execute("DELETE FROM vehiculos WHERE id_vehiculo = ?", (veh_id,))
            conn.commit()
            patente = item.text()
            detalle = f"Patente {patente} - DNI {self.input_dni.text().strip()}"
            _auditar(self, "Vehiculo eliminado", detalle)
            cliente_id = self._selected_cliente_id()
            if cliente_id:
                self._cargar_vehiculos(cliente_id)
        except sqlite3.IntegrityError:
            _mostrar_error(
                self,
                "Error",
                "No se pudo eliminar el vehiculo porque tiene datos relacionados.",
            )
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo eliminar el vehiculo.")
        finally:
            if conn:
                conn.close()
            _antirebote_finalizar(self, "clientes_eliminar_vehiculo", cooldown_ms=650)

    def _crear_contrato_desde_cliente(self):
        if not self._validar_cliente_activo_seleccionado("crear contratos"):
            return
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(
                self,
                "Cliente",
                "Selecciona un cliente en la lista antes de crearle un contrato.",
            )
            return
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM vehiculos "
                "WHERE id_cliente = ? AND patente IS NOT NULL AND TRIM(patente) <> ''",
                (cliente_id,),
            )
            cantidad_patentes = int((cur.fetchone()[0] or 0) or 0)
            if cantidad_patentes <= 0:
                QMessageBox.warning(
                    self,
                    "Contrato",
                    "Este cliente no tiene ninguna patente a su nombre.",
                )
                return
            patente_seleccionada = self._selected_vehiculo_patente()
            if cantidad_patentes > 1 and not patente_seleccionada:
                QMessageBox.warning(
                    self,
                    "Contrato",
                    "Este cliente tiene mas de una patente.\n"
                    "Selecciona la patente correcta antes de crear el contrato.",
                )
                return
        except sqlite3.Error:
            QMessageBox.warning(
                self,
                "Contrato",
                "No se pudo validar la patente del cliente.",
            )
            return
        finally:
            if conn:
                conn.close()
        dni = self.input_dni.text().strip()
        if not dni:
            return
        dlg = ContratosDialog(self, rol=self.rol)
        dlg.input_dni.setText(dni)
        if patente_seleccionada:
            dlg.set_patente_preferida(patente_seleccionada)
        dlg.autocompletar()
        dlg.input_espacio.setFocus()
        dlg.exec()

    def _abrir_estado_cuenta(self):
        if not self._validar_cliente_activo_seleccionado("abrir estado de cuenta"):
            return
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(
                self,
                "Cliente",
                "Selecciona un cliente en la lista para abrir su estado de cuenta.",
            )
            return
        dlg = EstadoCuentaDialog(cliente_id, self)
        dlg.exec()

    @staticmethod
    def _meses_mora_whatsapp(fecha_venc, hoy):
        if not fecha_venc.isValid() or fecha_venc >= hoy:
            return 0
        meses = 0
        cursor = fecha_venc
        while cursor < hoy and meses < 240:
            meses += 1
            cursor = cursor.addMonths(1)
        return meses

    def _resumen_recordatorio_whatsapp(self, cliente_id):
        conn = None
        data = {
            "nombre": "",
            "vencimiento": "Sin contratos activos",
            "deuda": "$ 0.00",
            "modelo": "",
            "contratos_activos": 0,
        }
        hoy = QDate.currentDate()
        proximo = None
        deuda_total = 0.0
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT nombre FROM clientes WHERE id_cliente = ?",
                (cliente_id,),
            )
            row_cli = cur.fetchone()
            if not row_cli:
                return None
            data["nombre"] = row_cli["nombre"] or ""

            cur.execute(
                "SELECT modelo FROM vehiculos "
                "WHERE id_cliente = ? AND TRIM(COALESCE(modelo, '')) <> '' "
                "ORDER BY id_vehiculo LIMIT 1",
                (cliente_id,),
            )
            row_modelo = cur.fetchone()
            if row_modelo:
                data["modelo"] = (row_modelo["modelo"] or "").strip()

            cur.execute(
                "SELECT fecha_vencimiento, monto_mensual "
                "FROM cochera_contratos "
                "WHERE id_cliente = ? AND activo = 1 "
                "ORDER BY fecha_vencimiento",
                (cliente_id,),
            )
            for row in cur.fetchall():
                data["contratos_activos"] += 1
                fecha_venc = QDate.fromString(row["fecha_vencimiento"] or "", "yyyy-MM-dd")
                monto = float(row["monto_mensual"] or 0.0)
                deuda_total += monto * self._meses_mora_whatsapp(fecha_venc, hoy)
                if fecha_venc.isValid() and (proximo is None or fecha_venc < proximo):
                    proximo = fecha_venc
        except sqlite3.Error:
            return None
        finally:
            if conn:
                conn.close()

        if proximo is not None and proximo.isValid():
            dias = hoy.daysTo(proximo)
            base = proximo.toString("dd/MM/yyyy")
            if dias < 0:
                data["vencimiento"] = f"{base} (vencido hace {abs(dias)} dia/s)"
            elif dias == 0:
                data["vencimiento"] = f"{base} (vence hoy)"
            else:
                data["vencimiento"] = f"{base} (en {dias} dia/s)"

        data["deuda"] = _fmt_money(deuda_total)
        return data

    def _enviar_whatsapp_cliente(self):
        if not self._validar_cliente_activo_seleccionado("abrir WhatsApp"):
            return
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(
                self,
                "WhatsApp",
                "Selecciona un cliente en la lista para abrir su chat.",
            )
            return

        telefono = self.input_telefono.text().strip()
        numero = _telefono_a_whatsapp(telefono)
        if not numero:
            QMessageBox.warning(
                self,
                "WhatsApp",
                "El cliente no tiene un telefono valido para WhatsApp.",
            )
            return

        url = QUrl(f"https://api.whatsapp.com/send?phone={quote(numero)}")
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                "WhatsApp",
                "No se pudo abrir WhatsApp.\n"
                "Verifica que tengas un navegador o la app disponible.",
            )
            return

        _auditar(
            self,
            "Chat WhatsApp cliente",
            f"Cliente {cliente_id} - {self.input_nombre.text().strip() or '-'} - {numero}",
        )


class EstadoCuentaDialog(QDialog):
    def __init__(self, id_cliente, parent=None):
        super().__init__(parent)
        self.id_cliente = id_cliente
        self.setWindowTitle("Estado de cuenta")
        self.setMinimumWidth(860)
        self.setMinimumHeight(560)

        layout = QVBoxLayout(self)

        self.label_cliente = QLabel("Cliente: -")
        self.label_cliente.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.label_cliente)

        resumen = QFormLayout()
        self.label_dni = QLabel("-")
        self.label_contratos = QLabel("0")
        self.label_mensual = QLabel("$ 0.00")
        self.label_pagado_mes = QLabel("$ 0.00")
        self.label_saldo_mes = QLabel("$ 0.00")
        self.label_deuda = QLabel("$ 0.00")
        self.label_proximo = QLabel("Sin contratos activos")
        self.label_pagado_total = QLabel("$ 0.00")
        resumen.addRow("DNI", self.label_dni)
        resumen.addRow("Contratos activos", self.label_contratos)
        resumen.addRow("Mensual comprometido", self.label_mensual)
        resumen.addRow("Pagado este mes", self.label_pagado_mes)
        resumen.addRow("Saldo del mes", self.label_saldo_mes)
        resumen.addRow("Deuda estimada", self.label_deuda)
        resumen.addRow("Proximo vencimiento", self.label_proximo)
        resumen.addRow("Pagado historico", self.label_pagado_total)
        layout.addLayout(resumen)

        layout.addWidget(QLabel("Contratos"))
        self.table_contratos = QTableWidget(0, 7)
        self.table_contratos.setHorizontalHeaderLabels(
            ["Contrato", "Espacio", "Monto mensual", "Vencimiento", "Estado", "Deuda", "Activo"]
        )
        self.table_contratos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_contratos.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_contratos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_contratos.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_contratos)

        layout.addWidget(QLabel("Ultimos pagos"))
        self.table_pagos = QTableWidget(0, 5)
        self.table_pagos.setHorizontalHeaderLabels(
            ["Fecha", "Monto", "Metodo", "Contrato", "Espacio"]
        )
        self.table_pagos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_pagos.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_pagos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_pagos.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_pagos)

        acciones = QHBoxLayout()
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_transferencia = QPushButton("Transferencia")
        self.btn_exportar_pdf = QPushButton("Exportar PDF")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_actualizar.setProperty("variant", "info")
        self.btn_transferencia.setProperty("variant", "neutral")
        self.btn_exportar_pdf.setProperty("variant", "info")
        self.btn_cerrar.setProperty("variant", "neutral")
        self.btn_actualizar.setToolTip(
            "Vuelve a cargar los contratos, pagos y saldos del cliente."
        )
        self.btn_transferencia.setToolTip(
            "Abre los datos de alias y CBU para compartir una transferencia."
        )
        self.btn_exportar_pdf.setToolTip(
            "Genera un PDF con el resumen de contratos y pagos del cliente."
        )
        self.btn_cerrar.setToolTip("Cierra el estado de cuenta del cliente.")
        acciones.addStretch(1)
        acciones.addWidget(self.btn_actualizar)
        acciones.addWidget(self.btn_transferencia)
        acciones.addWidget(self.btn_exportar_pdf)
        acciones.addWidget(self.btn_cerrar)
        layout.addLayout(acciones)

        self.btn_actualizar.clicked.connect(self._cargar)
        self.btn_transferencia.clicked.connect(self._abrir_transferencia)
        self.btn_exportar_pdf.clicked.connect(self._exportar_pdf)
        self.btn_cerrar.clicked.connect(self.reject)
        self._cargar()

    @staticmethod
    def _fmt_money(value):
        return _fmt_money(value)

    @staticmethod
    def _meses_mora(fecha_venc, hoy):
        if not fecha_venc.isValid() or fecha_venc >= hoy:
            return 0
        meses = 0
        cursor = fecha_venc
        while cursor < hoy and meses < 240:
            meses += 1
            cursor = cursor.addMonths(1)
        return meses

    def _consultar(self):
        conn = None
        data = {
            "cliente": "",
            "dni": "",
            "contratos_activos": 0,
            "mensual": 0.0,
            "pagado_mes": 0.0,
            "saldo_mes": 0.0,
            "deuda": 0.0,
            "proximo_vencimiento": "Sin contratos activos",
            "pagado_total": 0.0,
            "contratos": [],
            "pagos": [],
        }

        hoy = QDate.currentDate()
        mes_key = hoy.toString("yyyy-MM")

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT nombre, dni FROM clientes WHERE id_cliente = ?",
                (self.id_cliente,),
            )
            row_cliente = cur.fetchone()
            if not row_cliente:
                return None
            data["cliente"] = row_cliente["nombre"] or ""
            data["dni"] = row_cliente["dni"] or ""

            cur.execute(
                "SELECT cc.id_contrato, e.codigo, cc.fecha_vencimiento, cc.monto_mensual, cc.activo "
                "FROM cochera_contratos cc "
                "JOIN espacios e ON e.id_espacio = cc.id_espacio "
                "WHERE cc.id_cliente = ? "
                "ORDER BY cc.activo DESC, cc.fecha_vencimiento",
                (self.id_cliente,),
            )

            proximo = None
            for row in cur.fetchall():
                activo = int(row["activo"] or 0) == 1
                monto = float(row["monto_mensual"] or 0.0)
                fecha_venc = QDate.fromString(row["fecha_vencimiento"] or "", "yyyy-MM-dd")
                estado = "Sin fecha"
                deuda = 0.0

                if activo:
                    data["contratos_activos"] += 1
                    data["mensual"] += monto

                if fecha_venc.isValid():
                    dias = hoy.daysTo(fecha_venc)
                    if dias < 0:
                        estado = f"Vencido hace {abs(dias)} dia/s"
                    elif dias == 0:
                        estado = "Vence hoy"
                    else:
                        estado = f"Vence en {dias} dia/s"

                    if activo and (proximo is None or fecha_venc < proximo):
                        proximo = fecha_venc

                if activo:
                    meses = self._meses_mora(fecha_venc, hoy)
                    deuda = monto * meses
                    data["deuda"] += deuda

                data["contratos"].append(
                    {
                        "id_contrato": row["id_contrato"],
                        "espacio": row["codigo"] or "",
                        "monto": monto,
                        "vencimiento": row["fecha_vencimiento"] or "",
                        "estado": estado,
                        "deuda": deuda,
                        "activo": "SI" if activo else "NO",
                    }
                )

            cur.execute(
                "SELECT COALESCE(SUM(pc.monto), 0) "
                "FROM pagos_cochera pc "
                "JOIN cochera_contratos cc ON cc.id_contrato = pc.id_contrato "
                "WHERE cc.id_cliente = ?",
                (self.id_cliente,),
            )
            data["pagado_total"] = float(cur.fetchone()[0] or 0.0)

            cur.execute(
                "SELECT COALESCE(SUM(pc.monto), 0) "
                "FROM pagos_cochera pc "
                "JOIN cochera_contratos cc ON cc.id_contrato = pc.id_contrato "
                "WHERE cc.id_cliente = ? AND strftime('%Y-%m', pc.fecha_pago) = ?",
                (self.id_cliente, mes_key),
            )
            data["pagado_mes"] = float(cur.fetchone()[0] or 0.0)
            data["saldo_mes"] = data["pagado_mes"] - data["mensual"]

            cur.execute(
                "SELECT pc.fecha_pago, pc.monto, pc.metodo, pc.id_contrato, e.codigo "
                "FROM pagos_cochera pc "
                "JOIN cochera_contratos cc ON cc.id_contrato = pc.id_contrato "
                "JOIN espacios e ON e.id_espacio = cc.id_espacio "
                "WHERE cc.id_cliente = ? "
                "ORDER BY pc.fecha_pago DESC LIMIT 20",
                (self.id_cliente,),
            )
            for row in cur.fetchall():
                data["pagos"].append(
                    {
                        "fecha_pago": row["fecha_pago"] or "",
                        "monto": float(row["monto"] or 0.0),
                        "metodo": row["metodo"] or "",
                        "id_contrato": row["id_contrato"] or "",
                        "espacio": row["codigo"] or "",
                    }
                )
        except sqlite3.Error:
            return None
        finally:
            if conn:
                conn.close()

        if proximo is not None and proximo.isValid():
            dias = hoy.daysTo(proximo)
            base = proximo.toString("dd/MM/yyyy")
            if dias < 0:
                data["proximo_vencimiento"] = f"{base} (vencido hace {abs(dias)} dia/s)"
            elif dias == 0:
                data["proximo_vencimiento"] = f"{base} (vence hoy)"
            else:
                data["proximo_vencimiento"] = f"{base} (en {dias} dia/s)"

        return data

    def _cargar(self):
        data = self._consultar()
        if not data:
            QMessageBox.warning(
                self,
                "Estado de cuenta",
                "No se pudo cargar el estado de cuenta del cliente.\n"
                "Actualiza la lista y vuelve a intentarlo.",
            )
            return

        self.label_cliente.setText(f"Cliente: {data['cliente']}")
        self.label_dni.setText(_formatear_documento(data["dni"]))
        self.label_contratos.setText(str(data["contratos_activos"]))
        self.label_mensual.setText(self._fmt_money(data["mensual"]))
        self.label_pagado_mes.setText(self._fmt_money(data["pagado_mes"]))
        self.label_saldo_mes.setText(self._fmt_money(data["saldo_mes"]))
        self.label_deuda.setText(self._fmt_money(data["deuda"]))
        self.label_proximo.setText(data["proximo_vencimiento"])
        self.label_pagado_total.setText(self._fmt_money(data["pagado_total"]))

        self.table_contratos.setRowCount(0)
        for row in data["contratos"]:
            r = self.table_contratos.rowCount()
            self.table_contratos.insertRow(r)
            self.table_contratos.setItem(r, 0, QTableWidgetItem(str(row["id_contrato"])))
            self.table_contratos.setItem(r, 1, QTableWidgetItem(row["espacio"]))
            self.table_contratos.setItem(r, 2, QTableWidgetItem(self._fmt_money(row["monto"])))
            self.table_contratos.setItem(r, 3, QTableWidgetItem(row["vencimiento"]))
            self.table_contratos.setItem(r, 4, QTableWidgetItem(row["estado"]))
            self.table_contratos.setItem(r, 5, QTableWidgetItem(self._fmt_money(row["deuda"])))
            self.table_contratos.setItem(r, 6, QTableWidgetItem(row["activo"]))
        if not data["contratos"]:
            self.table_contratos.insertRow(0)
            item = QTableWidgetItem(
                "Este cliente todavia no tiene contratos cargados."
            )
            item.setFlags(Qt.NoItemFlags)
            self.table_contratos.setSpan(0, 0, 1, self.table_contratos.columnCount())
            self.table_contratos.setItem(0, 0, item)

        self.table_pagos.setRowCount(0)
        for row in data["pagos"]:
            r = self.table_pagos.rowCount()
            self.table_pagos.insertRow(r)
            self.table_pagos.setItem(r, 0, QTableWidgetItem(row["fecha_pago"]))
            self.table_pagos.setItem(r, 1, QTableWidgetItem(self._fmt_money(row["monto"])))
            self.table_pagos.setItem(r, 2, QTableWidgetItem(row["metodo"]))
            self.table_pagos.setItem(r, 3, QTableWidgetItem(str(row["id_contrato"])))
            self.table_pagos.setItem(r, 4, QTableWidgetItem(row["espacio"]))
        if not data["pagos"]:
            self.table_pagos.insertRow(0)
            item = QTableWidgetItem(
                "Todavia no hay pagos registrados para este cliente."
            )
            item.setFlags(Qt.NoItemFlags)
            self.table_pagos.setSpan(0, 0, 1, self.table_pagos.columnCount())
            self.table_pagos.setItem(0, 0, item)
        self._data_cache = data

    def _abrir_transferencia(self):
        alias = (_config_get("empresa_alias", "") or "").strip()
        cbu = (_config_get("empresa_cbu", "") or "").strip()
        if not alias and not cbu:
            QMessageBox.warning(
                self,
                "Transferencia",
                "Todavia no hay alias ni CBU configurados.\n"
                "Cargalos en Configuracion > General antes de compartir datos de transferencia.",
            )
            return
        dlg = DatosTransferenciaDialog(self)
        dlg.exec()

    def _exportar_pdf(self):
        data = getattr(self, "_data_cache", None) or self._consultar()
        if not data:
            QMessageBox.warning(
                self,
                "Estado de cuenta",
                "No hay datos disponibles para exportar el estado de cuenta.",
            )
            return
        try:
            path = _emitir_estado_cuenta_pdf(data)
        except Exception:
            _mostrar_error(self, "Error", "No se pudo generar el PDF del estado de cuenta.")
            return
        _auditar(
            self,
            "Estado de cuenta exportado",
            f"Cliente {data.get('cliente') or '-'} - PDF: {Path(path).name}",
        )
        if _mostrar_en_explorador(path):
            QMessageBox.information(
                self,
                "Estado de cuenta",
                "Se abrio la carpeta con el PDF seleccionado.",
            )
            return
        QMessageBox.information(
            self,
            "Estado de cuenta",
            f"PDF generado en:\n{path}",
        )


class TarifaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tarifas")
        self.setMinimumWidth(420)
        self._snapshot = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        self.label_actual_hora_auto = QLabel("Hora auto actual: sin definir")
        self.label_actual_hora_moto = QLabel("Hora moto actual: sin definir")
        self.label_actual_hora_camioneta = QLabel("Hora camioneta actual: sin definir")
        self.label_actual_mensual_auto = QLabel("Mensual auto actual: sin definir")
        self.label_actual_mensual_camioneta = QLabel("Mensual camioneta actual: sin definir")

        self.label_nuevo_hora_auto = QLabel("Nuevo precio por hora (Auto)")
        self.input_precio_hora_auto = QDoubleSpinBox()
        self.input_precio_hora_auto.setDecimals(2)
        self.input_precio_hora_auto.setRange(0.0, 999999.0)
        self.input_precio_hora_auto.setSingleStep(10.0)
        _configurar_spinbox_numerico(self.input_precio_hora_auto)

        self.label_nuevo_hora_moto = QLabel("Nuevo precio por hora (Moto)")
        self.input_precio_hora_moto = QDoubleSpinBox()
        self.input_precio_hora_moto.setDecimals(2)
        self.input_precio_hora_moto.setRange(0.0, 999999.0)
        self.input_precio_hora_moto.setSingleStep(10.0)
        _configurar_spinbox_numerico(self.input_precio_hora_moto)

        self.label_nuevo_hora_camioneta = QLabel("Nuevo precio por hora (Camioneta)")
        self.input_precio_hora_camioneta = QDoubleSpinBox()
        self.input_precio_hora_camioneta.setDecimals(2)
        self.input_precio_hora_camioneta.setRange(0.0, 999999.0)
        self.input_precio_hora_camioneta.setSingleStep(10.0)
        _configurar_spinbox_numerico(self.input_precio_hora_camioneta)

        self.label_nuevo_mensual_auto = QLabel("Nuevo precio mensual cochera (Auto)")
        self.input_precio_mensual_auto = QDoubleSpinBox()
        self.input_precio_mensual_auto.setDecimals(2)
        self.input_precio_mensual_auto.setRange(0.0, 999999.0)
        self.input_precio_mensual_auto.setSingleStep(100.0)
        _configurar_spinbox_numerico(self.input_precio_mensual_auto)

        self.label_nuevo_mensual_camioneta = QLabel("Nuevo precio mensual cochera (Camioneta)")
        self.input_precio_mensual_camioneta = QDoubleSpinBox()
        self.input_precio_mensual_camioneta.setDecimals(2)
        self.input_precio_mensual_camioneta.setRange(0.0, 999999.0)
        self.input_precio_mensual_camioneta.setSingleStep(100.0)
        _configurar_spinbox_numerico(self.input_precio_mensual_camioneta)

        def agregar_bloque(label_actual, label_nuevo, input_widget):
            layout.addWidget(label_actual)
            layout.addWidget(label_nuevo)
            layout.addWidget(input_widget)
            layout.addSpacing(10)

        agregar_bloque(
            self.label_actual_hora_auto,
            self.label_nuevo_hora_auto,
            self.input_precio_hora_auto,
        )
        agregar_bloque(
            self.label_actual_hora_moto,
            self.label_nuevo_hora_moto,
            self.input_precio_hora_moto,
        )
        agregar_bloque(
            self.label_actual_hora_camioneta,
            self.label_nuevo_hora_camioneta,
            self.input_precio_hora_camioneta,
        )
        agregar_bloque(
            self.label_actual_mensual_auto,
            self.label_nuevo_mensual_auto,
            self.input_precio_mensual_auto,
        )
        layout.addWidget(self.label_actual_mensual_camioneta)
        layout.addWidget(self.label_nuevo_mensual_camioneta)
        layout.addWidget(self.input_precio_mensual_camioneta)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 8, 0, 0)
        buttons.addStretch(1)
        self.btn_guardar = QPushButton("Guardar")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_guardar.setProperty("variant", "success")
        self.btn_cancelar.setProperty("variant", "neutral")
        self.btn_guardar.setToolTip(
            "Guarda los precios actuales de estacionamiento y cochera."
        )
        self.btn_cancelar.setToolTip(
            "Cierra esta ventana. Si cambiaste algo, la app te preguntara si quieres guardarlo."
        )
        buttons.addWidget(self.btn_guardar)
        buttons.addWidget(self.btn_cancelar)
        layout.addLayout(buttons)

        self.btn_guardar.clicked.connect(lambda: self._guardar(mostrar_mensaje=True))
        self.btn_cancelar.clicked.connect(self.reject)
        _instalar_enter_navegacion(
            self,
            {
                self.input_precio_hora_auto: self.input_precio_hora_moto,
                self.input_precio_hora_moto: self.input_precio_hora_camioneta,
                self.input_precio_hora_camioneta: self.input_precio_mensual_auto,
                self.input_precio_mensual_auto: self.input_precio_mensual_camioneta,
                self.input_precio_mensual_camioneta: self._guardar,
            },
        )

        self._cargar_actual()

    def _snapshot_form(self):
        return (
            round(float(self.input_precio_hora_auto.value()), 2),
            round(float(self.input_precio_hora_moto.value()), 2),
            round(float(self.input_precio_hora_camioneta.value()), 2),
            round(float(self.input_precio_mensual_auto.value()), 2),
            round(float(self.input_precio_mensual_camioneta.value()), 2),
        )

    def _actualizar_snapshot(self):
        self._snapshot = self._snapshot_form()

    def _hay_cambios_sin_guardar(self):
        return self._snapshot is not None and self._snapshot_form() != self._snapshot

    def _cargar_actual(self):
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT precio_hora, precio_mensual, "
                "COALESCE(precio_hora_auto, precio_hora) AS precio_hora_auto, "
                "COALESCE(precio_hora_moto, precio_hora) AS precio_hora_moto, "
                "COALESCE(precio_hora_camioneta, precio_hora) AS precio_hora_camioneta, "
                "COALESCE(precio_mensual_auto, precio_mensual) AS precio_mensual_auto, "
                "COALESCE(precio_mensual_camioneta, precio_mensual) AS precio_mensual_camioneta "
                "FROM tarifas WHERE activa = 1 "
                "ORDER BY fecha_desde DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                valor_hora_auto = float(row["precio_hora_auto"] or 0)
                valor_hora_moto = float(row["precio_hora_moto"] or 0)
                valor_hora_camioneta = float(row["precio_hora_camioneta"] or 0)
                valor_mensual_auto = float(row["precio_mensual_auto"] or row["precio_mensual"] or 0)
                valor_mensual_camioneta = float(
                    row["precio_mensual_camioneta"] or row["precio_mensual"] or 0
                )
                self.label_actual_hora_auto.setText(
                    f"Hora auto actual: {_fmt_money(valor_hora_auto)}"
                )
                self.label_actual_hora_moto.setText(
                    f"Hora moto actual: {_fmt_money(valor_hora_moto)}"
                )
                self.label_actual_hora_camioneta.setText(
                    f"Hora camioneta actual: {_fmt_money(valor_hora_camioneta)}"
                )
                self.label_actual_mensual_auto.setText(
                    f"Mensual auto actual: {_fmt_money(valor_mensual_auto)}"
                )
                self.label_actual_mensual_camioneta.setText(
                    f"Mensual camioneta actual: {_fmt_money(valor_mensual_camioneta)}"
                )
                self.input_precio_hora_auto.setValue(valor_hora_auto)
                self.input_precio_hora_moto.setValue(valor_hora_moto)
                self.input_precio_hora_camioneta.setValue(valor_hora_camioneta)
                self.input_precio_mensual_auto.setValue(valor_mensual_auto)
                self.input_precio_mensual_camioneta.setValue(valor_mensual_camioneta)
            else:
                self.label_actual_hora_auto.setText("Hora auto actual: sin definir")
                self.label_actual_hora_moto.setText("Hora moto actual: sin definir")
                self.label_actual_hora_camioneta.setText("Hora camioneta actual: sin definir")
                self.label_actual_mensual_auto.setText("Mensual auto actual: sin definir")
                self.label_actual_mensual_camioneta.setText(
                    "Mensual camioneta actual: sin definir"
                )
        except sqlite3.Error:
            self.label_actual_hora_auto.setText("Hora auto actual: error al leer")
            self.label_actual_hora_moto.setText("Hora moto actual: error al leer")
            self.label_actual_hora_camioneta.setText("Hora camioneta actual: error al leer")
            self.label_actual_mensual_auto.setText("Mensual auto actual: error al leer")
            self.label_actual_mensual_camioneta.setText(
                "Mensual camioneta actual: error al leer"
            )
        finally:
            if conn:
                conn.close()
        self._actualizar_snapshot()

    def _guardar(self, cerrar=True, mostrar_mensaje=True):
        precio_hora_auto = float(self.input_precio_hora_auto.value())
        precio_hora_moto = float(self.input_precio_hora_moto.value())
        precio_hora_camioneta = float(self.input_precio_hora_camioneta.value())
        precio_mensual_auto = float(self.input_precio_mensual_auto.value())
        precio_mensual_camioneta = float(self.input_precio_mensual_camioneta.value())
        if not self._hay_cambios_sin_guardar():
            if mostrar_mensaje:
                QMessageBox.information(
                    self,
                    "Tarifas",
                    "No hay cambios nuevos para guardar.",
                )
            return True
        if (
            precio_hora_auto <= 0
            or precio_hora_moto <= 0
            or precio_hora_camioneta <= 0
            or precio_mensual_auto <= 0
            or precio_mensual_camioneta <= 0
        ):
            QMessageBox.warning(
                self,
                "Precio",
                "Los precios deben ser mayores a 0.",
            )
            return False
        if not _antirebote_iniciar(self, "tarifas_guardar"):
            return False

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("UPDATE tarifas SET activa = 0 WHERE activa = 1")
            cur.execute(
                "INSERT INTO tarifas ("
                "precio_hora, precio_mensual, precio_mensual_auto, precio_mensual_camioneta, "
                "precio_hora_auto, precio_hora_moto, precio_hora_camioneta, activa"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    precio_hora_auto,
                    precio_mensual_auto,
                    precio_mensual_auto,
                    precio_mensual_camioneta,
                    precio_hora_auto,
                    precio_hora_moto,
                    precio_hora_camioneta,
                ),
            )
            conn.commit()
            _auditar(
                self,
                "Tarifas actualizadas",
                (
                    f"auto={precio_hora_auto:.2f}, "
                    f"moto={precio_hora_moto:.2f}, "
                    f"camioneta={precio_hora_camioneta:.2f}, "
                    f"mensual_auto={precio_mensual_auto:.2f}, "
                    f"mensual_camioneta={precio_mensual_camioneta:.2f}"
                ),
            )
            self._actualizar_snapshot()
            if mostrar_mensaje:
                QMessageBox.information(self, "Tarifas", "Tarifa actualizada.")
            if cerrar:
                self.accept()
            return True
        except sqlite3.Error:
            _mostrar_error(
                self,
                "Error de base de datos",
                "No se pudo guardar la tarifa.",
            )
            return False
        finally:
            if conn:
                conn.close()
            _antirebote_finalizar(self, "tarifas_guardar", cooldown_ms=700)

    def closeEvent(self, event):
        if not self._hay_cambios_sin_guardar():
            event.accept()
            return
        respuesta = _confirmar_guardado_pendiente(
            self,
            "Hay cambios en tarifas.\nQuieres guardarlos antes de salir?",
        )
        if respuesta == QMessageBox.Cancel:
            event.ignore()
            return
        if respuesta == QMessageBox.No:
            event.accept()
            return
        if self._guardar(cerrar=False, mostrar_mensaje=False):
            event.accept()
        else:
            event.ignore()


class EspacioItem(QGraphicsRectItem):
    def __init__(self, codigo, rect, color, estado="LIBRE", grid=10):
        super().__init__(rect)
        self.codigo = codigo
        self.estado = estado
        self.info = ""
        self.grid = grid
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setBrush(QBrush(color))
        self.setPen(QPen(Qt.black, 2))
        self.label = QGraphicsTextItem(self)
        self.label.setFont(QFont("Arial", 8))
        self.set_estado(estado, color)
        self._centrar_label()

    def set_codigo(self, codigo):
        self.codigo = codigo
        self._actualizar_label()
        self._centrar_label()

    def set_estado(self, estado, color):
        self.estado = estado
        self.setBrush(QBrush(color))
        self._actualizar_label()
        self._centrar_label()

    def set_info(self, info):
        self.info = info or ""
        self._actualizar_label()
        self._centrar_label()

    def _actualizar_label(self):
        info = self._format_info(self.info)
        texto = f"{self.codigo}\n{self.estado}"
        if info:
            texto = f"{texto}\n{info}"
        self.label.setPlainText(texto)
        color = self.brush().color()
        brillo = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
        texto = Qt.white if brillo < 140 else Qt.black
        self.label.setDefaultTextColor(texto)

    def _format_info(self, info):
        info = (info or "").strip()
        if not info:
            return ""
        if len(info) <= 14:
            return info
        return info[:11].rstrip() + "..."

    def _centrar_label(self):
        rect = self.rect()
        br = self.label.boundingRect()
        x = (rect.width() - br.width()) / 2
        y = (rect.height() - br.height()) / 2
        self.label.setPos(x, y)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            pos = value
            rect = self.rect()
            ancho = float(rect.width())
            alto = float(rect.height())
            escena = self.scene()
            snap_enabled = bool(escena.property("snap_enabled"))
            step_x_prop = escena.property("snap_step_x")
            step_y_prop = escena.property("snap_step_y")
            try:
                step_x = float(step_x_prop) if step_x_prop else float(self.grid)
            except (TypeError, ValueError):
                step_x = float(self.grid)
            try:
                step_y = float(step_y_prop) if step_y_prop else float(self.grid)
            except (TypeError, ValueError):
                step_y = float(self.grid)
            step_x = max(float(self.grid), step_x)
            step_y = max(float(self.grid), step_y)
            x = float(pos.x())
            y = float(pos.y())

            if snap_enabled:
                x = round(x / step_x) * step_x
                y = round(y / step_y) * step_y
                snap_tol_x = max(step_x * 0.45, min(ancho * 0.45, 60.0), 24.0)
                snap_tol_y = max(step_y * 0.45, min(alto * 0.45, 45.0), 20.0)
                mejor_x = x
                mejor_dx = snap_tol_x + 1.0
                mejor_y = y
                mejor_dy = snap_tol_y + 1.0

                # Ajuste magnetico: prioriza que los bordes queden pegados entre si.
                def _solape(a0, a1, b0, b1):
                    return max(0.0, min(a1, b1) - max(a0, b0))

                for other in escena.items():
                    if other is self or not isinstance(other, EspacioItem):
                        continue
                    other_pos = other.pos()
                    other_rect = other.rect()
                    ox = float(other_pos.x())
                    oy = float(other_pos.y())
                    ow = float(other_rect.width())
                    oh = float(other_rect.height())

                    solape_y = _solape(y, y + alto, oy, oy + oh)
                    if solape_y >= min(alto, oh) * 0.35:
                        candidatos_x = (ox - ancho, ox + ow)
                        for cx in candidatos_x:
                            dx = abs(x - cx)
                            if dx <= snap_tol_x and dx < mejor_dx:
                                mejor_dx = dx
                                mejor_x = cx

                    solape_x = _solape(x, x + ancho, ox, ox + ow)
                    if solape_x >= min(ancho, ow) * 0.35:
                        candidatos_y = (oy - alto, oy + oh)
                        for cy in candidatos_y:
                            dy = abs(y - cy)
                            if dy <= snap_tol_y and dy < mejor_dy:
                                mejor_dy = dy
                                mejor_y = cy

                magnetico_x = mejor_dx <= snap_tol_x
                magnetico_y = mejor_dy <= snap_tol_y
                x = mejor_x if magnetico_x else round(x / step_x) * step_x
                y = mejor_y if magnetico_y else round(y / step_y) * step_y
            bounds = escena.sceneRect()
            max_ancho = escena.property("scene_max_width")
            max_alto = escena.property("scene_max_height")
            max_ancho = int(max_ancho) if max_ancho else int(bounds.width())
            max_alto = int(max_alto) if max_alto else int(bounds.height())
            margen_expandir = max(self.grid * 20, 200)
            expandio = False

            limite_derecha = bounds.right() - ancho
            limite_abajo = bounds.bottom() - alto
            if x > (limite_derecha - self.grid):
                nuevo_ancho = max(
                    bounds.width(),
                    (x + ancho + margen_expandir) - bounds.left(),
                )
                nuevo_ancho = min(nuevo_ancho, max_ancho)
                bounds.setWidth(nuevo_ancho)
                expandio = True
            if y > (limite_abajo - self.grid):
                nuevo_alto = max(
                    bounds.height(),
                    (y + alto + margen_expandir) - bounds.top(),
                )
                nuevo_alto = min(nuevo_alto, max_alto)
                bounds.setHeight(nuevo_alto)
                expandio = True
            if expandio:
                escena.setSceneRect(bounds)
                bounds = escena.sceneRect()

            x = min(max(bounds.left(), x), bounds.right() - ancho)
            y = min(max(bounds.top(), y), bounds.bottom() - alto)
            return QPointF(x, y)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._centrar_label()
            escena = self.scene()
            if escena and not bool(escena.property("suspend_dirty")):
                escena.setProperty("map_dirty", True)
        return super().itemChange(change, value)


class ColoresMapaDialog(QDialog):
    def __init__(self, color_cochera, color_ocupado, color_libre, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Colores del mapa")
        self.setMinimumWidth(360)

        self.color_cochera = QColor(color_cochera)
        self.color_ocupado = QColor(color_ocupado)
        self.color_libre = QColor(color_libre)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.btn_cochera = QPushButton("Elegir")
        self.swatch_cochera = QLabel()
        self.swatch_cochera.setFixedSize(24, 16)
        self._aplicar_swatch(self.swatch_cochera, self.color_cochera)
        fila_cochera = QHBoxLayout()
        fila_cochera.addWidget(self.btn_cochera)
        fila_cochera.addWidget(self.swatch_cochera)
        fila_cochera.addStretch(1)
        form.addRow("Cochera", fila_cochera)

        self.btn_ocupado = QPushButton("Elegir")
        self.swatch_ocupado = QLabel()
        self.swatch_ocupado.setFixedSize(24, 16)
        self._aplicar_swatch(self.swatch_ocupado, self.color_ocupado)
        fila_ocupado = QHBoxLayout()
        fila_ocupado.addWidget(self.btn_ocupado)
        fila_ocupado.addWidget(self.swatch_ocupado)
        fila_ocupado.addStretch(1)
        form.addRow("Ocupado (hora)", fila_ocupado)

        self.btn_libre = QPushButton("Elegir")
        self.swatch_libre = QLabel()
        self.swatch_libre.setFixedSize(24, 16)
        self._aplicar_swatch(self.swatch_libre, self.color_libre)
        fila_libre = QHBoxLayout()
        fila_libre.addWidget(self.btn_libre)
        fila_libre.addWidget(self.swatch_libre)
        fila_libre.addStretch(1)
        form.addRow("Libre", fila_libre)

        layout.addLayout(form)

        botones = QHBoxLayout()
        botones.addStretch(1)
        self.btn_ok = QPushButton("Guardar")
        self.btn_cancel = QPushButton("Cancelar")
        botones.addWidget(self.btn_ok)
        botones.addWidget(self.btn_cancel)
        layout.addLayout(botones)

        self.btn_cochera.clicked.connect(lambda: self._elegir("cochera"))
        self.btn_ocupado.clicked.connect(lambda: self._elegir("ocupado"))
        self.btn_libre.clicked.connect(lambda: self._elegir("libre"))
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self._snapshot = self._snapshot_colores()

    def _aplicar_swatch(self, swatch, color):
        swatch.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid #333;"
        )

    def _elegir(self, tipo):
        actual = {
            "cochera": self.color_cochera,
            "ocupado": self.color_ocupado,
            "libre": self.color_libre,
        }[tipo]
        color = QColorDialog.getColor(actual, self, "Seleccionar color")
        if not color.isValid():
            return
        if tipo == "cochera":
            self.color_cochera = color
            self._aplicar_swatch(self.swatch_cochera, color)
        elif tipo == "ocupado":
            self.color_ocupado = color
            self._aplicar_swatch(self.swatch_ocupado, color)
        else:
            self.color_libre = color
            self._aplicar_swatch(self.swatch_libre, color)

    def get_colors(self):
        return self.color_cochera, self.color_ocupado, self.color_libre

    def _snapshot_colores(self):
        return (
            self.color_cochera.name(),
            self.color_ocupado.name(),
            self.color_libre.name(),
        )

    def _hay_cambios_sin_guardar(self):
        return self._snapshot_colores() != self._snapshot

    def reject(self):
        if not self._hay_cambios_sin_guardar():
            super().reject()
            return
        respuesta = _confirmar_guardado_pendiente(
            self,
            "Hay cambios en los colores del mapa.\nQuieres guardarlos antes de salir?",
        )
        if respuesta == QMessageBox.Cancel:
            return
        if respuesta == QMessageBox.Yes:
            self.accept()
            return
        super().reject()


class MapaCocheraDialog(QDialog):
    def __init__(self, parent=None, editable=True):
        super().__init__(parent)
        self._editable = bool(editable)
        titulo = "Mapa de cocheras"
        if not self._editable:
            titulo += " (solo lectura)"
        self.setWindowTitle(titulo)
        self.setMinimumSize(700, 500)
        self._eliminados = set()
        self._grid = 10
        self._scene_base_width = 1800
        self._scene_base_height = 1100
        self._scene_max_width = 6000
        self._scene_max_height = 4000
        self._paso_guia_x = 80
        self._paso_guia_y = 50
        self._guias_visibles = False
        self._items_guias = []

        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        self.btn_agregar = QPushButton("Agregar")
        self.btn_renombrar = QPushButton("Renombrar")
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_marcar_cochera = QPushButton("Marcar cochera")
        self.btn_quitar_cochera = QPushButton("Quitar cochera")
        self.btn_colores = QPushButton("Colores")
        self.btn_alineado = QPushButton("Alineado")
        self.btn_alineado.setCheckable(True)
        self.btn_zoom_in = QPushButton("Zoom +")
        self.btn_zoom_out = QPushButton("Zoom -")
        self.btn_zoom_reset = QPushButton("Zoom 100%")
        self.btn_guardar = QPushButton("Guardar")
        self.btn_recargar = QPushButton("Limpiar")
        self.btn_agregar.setProperty("variant", "success")
        self.btn_renombrar.setProperty("variant", "warning")
        self.btn_eliminar.setProperty("variant", "danger")
        self.btn_marcar_cochera.setProperty("variant", "info")
        self.btn_quitar_cochera.setProperty("variant", "warning")
        self.btn_colores.setProperty("variant", "info")
        self.btn_alineado.setProperty("variant", "neutral")
        self.btn_zoom_in.setProperty("variant", "neutral")
        self.btn_zoom_out.setProperty("variant", "neutral")
        self.btn_zoom_reset.setProperty("variant", "neutral")
        self.btn_guardar.setProperty("variant", "success")
        self.btn_recargar.setProperty("variant", "warning")
        barra.addWidget(self.btn_agregar)
        barra.addWidget(self.btn_renombrar)
        barra.addWidget(self.btn_eliminar)

        cochera_col = QVBoxLayout()
        cochera_col.addWidget(self.btn_marcar_cochera)
        cochera_col.addWidget(self.btn_quitar_cochera)
        barra.addLayout(cochera_col)

        barra.addWidget(self.btn_colores)
        barra.addWidget(self.btn_alineado)

        zoom_col = QVBoxLayout()
        zoom_col.addWidget(self.btn_zoom_in)
        zoom_col.addWidget(self.btn_zoom_out)
        zoom_col.addWidget(self.btn_zoom_reset)
        barra.addLayout(zoom_col)
        barra.addStretch(1)
        barra.addWidget(self.btn_recargar)
        barra.addWidget(self.btn_guardar)
        layout.addLayout(barra)

        self._cargar_colores()

        leyenda = QHBoxLayout()
        leyenda.addWidget(QLabel("Leyenda:"))
        self._legend_swatch_cochera = self._agregar_leyenda_item(
            leyenda, self._color_cochera, "Cochera"
        )
        self._legend_swatch_ocupado = self._agregar_leyenda_item(
            leyenda, self._color_ocupado, "Ocupado (hora)"
        )
        self._legend_swatch_libre = self._agregar_leyenda_item(
            leyenda, self._color_libre, "Libre"
        )
        leyenda.addStretch(1)
        layout.addLayout(leyenda)

        self.scene = QGraphicsScene(self)
        self.scene.setProperty("scene_max_width", self._scene_max_width)
        self.scene.setProperty("scene_max_height", self._scene_max_height)
        self.scene.setProperty("snap_step_x", self._paso_guia_x)
        self.scene.setProperty("snap_step_y", self._paso_guia_y)
        self.scene.setProperty("snap_enabled", False)
        self.scene.setProperty("suspend_dirty", False)
        self.scene.setProperty("map_dirty", False)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing, True)
        self.view.setDragMode(QGraphicsView.NoDrag)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._menu_contextual)
        self.scene.setSceneRect(0, 0, self._scene_base_width, self._scene_base_height)
        layout.addWidget(self.view)

        self.btn_agregar.clicked.connect(self._agregar)
        self.btn_renombrar.clicked.connect(self._renombrar)
        self.btn_eliminar.clicked.connect(self._eliminar)
        self.btn_marcar_cochera.clicked.connect(lambda: self._set_cochera(True))
        self.btn_quitar_cochera.clicked.connect(lambda: self._set_cochera(False))
        self.btn_colores.clicked.connect(self._editar_colores)
        self.btn_alineado.toggled.connect(self._set_guias_visibles)
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        self.btn_zoom_reset.clicked.connect(self._zoom_reset)
        self.btn_guardar.clicked.connect(lambda: self._guardar(mostrar_mensaje=True))
        self.btn_recargar.clicked.connect(self._recargar)

        self._zoom_factor = 1.0

        if not self._editable:
            self.btn_agregar.setEnabled(False)
            self.btn_renombrar.setEnabled(False)
            self.btn_eliminar.setEnabled(False)
            self.btn_marcar_cochera.setEnabled(False)
            self.btn_quitar_cochera.setEnabled(False)
            self.btn_colores.setEnabled(False)
            self.btn_guardar.setEnabled(False)

        self._configurar_atajos()
        self._cargar()
        self.btn_alineado.setChecked(False)

    def _mapa_tiene_cambios(self):
        return bool(self.scene.property("map_dirty"))

    def _set_mapa_dirty(self, valor):
        self.scene.setProperty("map_dirty", bool(valor))

    def _configurar_atajos(self):
        self._sc_zoom_in_1 = QShortcut(QKeySequence("Ctrl++"), self)
        self._sc_zoom_in_2 = QShortcut(QKeySequence("Ctrl+="), self)
        self._sc_zoom_out = QShortcut(QKeySequence("Ctrl+-"), self)
        self._sc_zoom_reset = QShortcut(QKeySequence("Ctrl+0"), self)
        for sc in (self._sc_zoom_in_1, self._sc_zoom_in_2):
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(self._zoom_in)
        self._sc_zoom_out.setContext(Qt.WidgetWithChildrenShortcut)
        self._sc_zoom_out.activated.connect(self._zoom_out)
        self._sc_zoom_reset.setContext(Qt.WidgetWithChildrenShortcut)
        self._sc_zoom_reset.activated.connect(self._zoom_reset)

        if self._editable:
            self._sc_add = QShortcut(QKeySequence("Ctrl+N"), self)
            self._sc_rename = QShortcut(QKeySequence("F2"), self)
            self._sc_delete = QShortcut(QKeySequence("Delete"), self)
            self._sc_save = QShortcut(QKeySequence("Ctrl+S"), self)
            for sc in (self._sc_add, self._sc_rename, self._sc_delete, self._sc_save):
                sc.setContext(Qt.WidgetWithChildrenShortcut)
            self._sc_add.activated.connect(self._agregar)
            self._sc_rename.activated.connect(self._renombrar)
            self._sc_delete.activated.connect(self._eliminar)
            self._sc_save.activated.connect(self._guardar)

    def _set_zoom(self, factor):
        factor = max(0.5, min(2.5, factor))
        if abs(factor - self._zoom_factor) < 0.001:
            return
        self._zoom_factor = factor
        self._actualizar_area_trabajo()
        self.view.resetTransform()
        self.view.scale(self._zoom_factor, self._zoom_factor)

    def _actualizar_area_trabajo(self):
        escala = max(1.0, float(self._zoom_factor or 1.0))
        ancho = int(self._scene_base_width * escala)
        alto = int(self._scene_base_height * escala)
        margen = 200
        for item in self.scene.items():
            if not isinstance(item, EspacioItem):
                continue
            br = item.sceneBoundingRect()
            ancho = max(ancho, int(br.right() + margen))
            alto = max(alto, int(br.bottom() + margen))
        ancho = min(max(ancho, 400), int(self._scene_max_width))
        alto = min(max(alto, 300), int(self._scene_max_height))
        self.scene.setSceneRect(0, 0, ancho, alto)
        self._repintar_guias()

    def _snap_a_cuadricula(self, x, y):
        if not bool(self.scene.property("snap_enabled")):
            return float(x), float(y)
        paso_x_prop = self.scene.property("snap_step_x")
        paso_y_prop = self.scene.property("snap_step_y")
        try:
            paso_x = float(paso_x_prop) if paso_x_prop else float(self._paso_guia_x)
        except (TypeError, ValueError):
            paso_x = float(self._paso_guia_x)
        try:
            paso_y = float(paso_y_prop) if paso_y_prop else float(self._paso_guia_y)
        except (TypeError, ValueError):
            paso_y = float(self._paso_guia_y)
        paso_x = max(float(self._grid), paso_x)
        paso_y = max(float(self._grid), paso_y)
        return round(float(x) / paso_x) * paso_x, round(float(y) / paso_y) * paso_y

    def _limpiar_guias(self):
        for item in self._items_guias:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self._items_guias = []

    def _set_guias_visibles(self, visible):
        self._guias_visibles = bool(visible)
        self.scene.setProperty("snap_enabled", bool(visible))
        self._repintar_guias()

    def _repintar_guias(self):
        self._limpiar_guias()
        if not self._guias_visibles:
            return

        rect = self.scene.sceneRect()
        ancho = int(rect.width())
        alto = int(rect.height())
        paso_x = max(int(self._paso_guia_x), 10)
        paso_y = max(int(self._paso_guia_y), 10)

        color_fino = QColor(110, 118, 129, 70)
        color_fuerte = QColor(130, 140, 152, 110)
        pen_fino = QPen(color_fino, 1, Qt.DotLine)
        pen_fino.setCosmetic(True)
        pen_fuerte = QPen(color_fuerte, 1, Qt.SolidLine)
        pen_fuerte.setCosmetic(True)

        x = 0
        idx = 0
        while x <= ancho:
            pen = pen_fuerte if idx % 5 == 0 else pen_fino
            line = self.scene.addLine(x, 0, x, alto, pen)
            line.setZValue(-1000)
            line.setAcceptedMouseButtons(Qt.NoButton)
            self._items_guias.append(line)
            x += paso_x
            idx += 1

        y = 0
        idx = 0
        while y <= alto:
            pen = pen_fuerte if idx % 5 == 0 else pen_fino
            line = self.scene.addLine(0, y, ancho, y, pen)
            line.setZValue(-1000)
            line.setAcceptedMouseButtons(Qt.NoButton)
            self._items_guias.append(line)
            y += paso_y
            idx += 1

    def _zoom_in(self):
        self._set_zoom(self._zoom_factor + 0.1)

    def _zoom_out(self):
        self._set_zoom(self._zoom_factor - 0.1)

    def _zoom_reset(self):
        self._set_zoom(1.0)

    def _agregar_leyenda_item(self, layout, color, texto):
        swatch = QLabel()
        swatch.setFixedSize(16, 16)
        swatch.setStyleSheet(
            f"background-color: rgb({color.red()}, {color.green()}, {color.blue()});"
            "border: 1px solid #333;"
        )
        layout.addWidget(swatch)
        layout.addWidget(QLabel(texto))
        layout.addSpacing(12)
        return swatch

    def _aplicar_swatch(self, swatch, color):
        swatch.setStyleSheet(
            f"background-color: rgb({color.red()}, {color.green()}, {color.blue()});"
            "border: 1px solid #333;"
        )

    def _cargar_colores(self):
        self._color_cochera = QColor(60, 80, 200)
        self._color_ocupado = QColor(180, 50, 50)
        self._color_libre = QColor(255, 255, 255)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT clave, valor FROM configuracion WHERE clave IN (?, ?, ?)",
                ("map_color_cochera", "map_color_ocupado", "map_color_libre"),
            )
            for clave, valor in cur.fetchall():
                if not valor:
                    continue
                if clave == "map_color_cochera":
                    self._color_cochera = QColor(valor)
                elif clave == "map_color_ocupado":
                    self._color_ocupado = QColor(valor)
                elif clave == "map_color_libre":
                    self._color_libre = QColor(valor)
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()

    def _guardar_colores(self):
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)",
                ("map_color_cochera", self._color_cochera.name()),
            )
            cur.execute(
                "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)",
                ("map_color_ocupado", self._color_ocupado.name()),
            )
            cur.execute(
                "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)",
                ("map_color_libre", self._color_libre.name()),
            )
            conn.commit()
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()

    def _editar_colores(self):
        dlg = ColoresMapaDialog(
            self._color_cochera, self._color_ocupado, self._color_libre, self
        )
        if dlg.exec() != QDialog.Accepted:
            return
        self._color_cochera, self._color_ocupado, self._color_libre = dlg.get_colors()
        self._guardar_colores()
        self._aplicar_swatch(self._legend_swatch_cochera, self._color_cochera)
        self._aplicar_swatch(self._legend_swatch_ocupado, self._color_ocupado)
        self._aplicar_swatch(self._legend_swatch_libre, self._color_libre)
        self._aplicar_colores_items()
        self._actualizar_colores_escena()
        QMessageBox.information(
            self,
            "Mapa",
            "Los colores del mapa se actualizaron correctamente.",
        )

    def _aplicar_colores_items(self):
        for item in self.scene.items():
            if not isinstance(item, EspacioItem):
                continue
            estado = (item.estado or "LIBRE").upper()
            if estado == "OCUPADO":
                color = self._color_ocupado
            elif estado == "COCHERA":
                color = self._color_cochera
            else:
                color = self._color_libre
            item.set_estado(estado, color)

    def _estado_por_datos(self, es_reservado, id_cliente, ocupado):
        if ocupado == 1:
            return "OCUPADO", self._color_ocupado
        if id_cliente is not None or es_reservado == 1:
            return "COCHERA", self._color_cochera
        return "LIBRE", self._color_libre

    def _codigo_en_escena(self, codigo):
        for item in self.scene.items():
            if isinstance(item, EspacioItem) and item.codigo == codigo:
                return True
        return False

    def _item_requerido_para(self, accion):
        item = self._item_seleccionado()
        if item:
            return item
        QMessageBox.warning(
            self,
            "Mapa",
            f"Selecciona un espacio del mapa antes de {accion}.",
        )
        return None

    def _agregar(self):
        codigo, ok = QInputDialog.getText(self, "Nuevo espacio", "Codigo (ej: A1)")
        if not ok:
            return
        codigo = codigo.strip().upper()
        if not codigo:
            QMessageBox.warning(
                self,
                "Codigo",
                "Escribe un codigo para el nuevo espacio antes de agregarlo al mapa.",
            )
            return
        if self._codigo_en_escena(codigo):
            QMessageBox.warning(
                self,
                "Codigo",
                "Ese codigo ya existe en el mapa.\n"
                "Usa otro codigo para evitar duplicados.",
            )
            return

        size = QRectF(0, 0, 80, 50)
        item = EspacioItem(codigo, size, self._color_libre, estado="LIBRE", grid=self._grid)
        if bool(self.scene.property("snap_enabled")):
            espacios = [it for it in self.scene.items() if isinstance(it, EspacioItem)]
            if espacios:
                ultimo = max(
                    espacios,
                    key=lambda it: (
                        round(float(it.pos().y()) / max(float(self._paso_guia_y), 1.0)),
                        round(float(it.pos().x()) / max(float(self._paso_guia_x), 1.0)),
                    ),
                )
                nuevo_x = float(ultimo.pos().x()) + float(ultimo.rect().width())
                nuevo_y = float(ultimo.pos().y())
                x_snap, y_snap = self._snap_a_cuadricula(nuevo_x, nuevo_y)
            else:
                x_snap, y_snap = self._snap_a_cuadricula(10, 10)
        else:
            offset = 10 + len(self.scene.items()) * 10
            x_snap, y_snap = self._snap_a_cuadricula(offset, offset)
        item.setPos(x_snap, y_snap)
        if not self._editable:
            item.setFlags(QGraphicsItem.ItemIsSelectable)
        self.scene.addItem(item)
        self._set_mapa_dirty(True)
        self._actualizar_area_trabajo()
        QMessageBox.information(
            self,
            "Mapa",
            f"Espacio {codigo} agregado al mapa.\nRecuerda guardar para dejar el cambio fijo.",
        )

    def _renombrar(self):
        item = self._item_requerido_para("renombrarlo")
        if not item:
            return
        codigo_anterior = item.codigo
        nuevo, ok = QInputDialog.getText(self, "Renombrar", "Nuevo codigo")
        if not ok:
            return
        nuevo = nuevo.strip().upper()
        if not nuevo:
            QMessageBox.warning(
                self,
                "Codigo",
                "Escribe el nuevo codigo antes de guardar el cambio.",
            )
            return
        if nuevo == codigo_anterior:
            QMessageBox.information(
                self,
                "Mapa",
                "El codigo no cambio.\nNo hay nada nuevo para guardar.",
            )
            return
        if self._codigo_en_escena(nuevo):
            QMessageBox.warning(
                self,
                "Codigo",
                "Ese codigo ya existe en el mapa.\n"
                "Elige otro para que no haya dos espacios iguales.",
            )
            return
        item.set_codigo(nuevo)
        self._set_mapa_dirty(True)
        QMessageBox.information(
            self,
            "Mapa",
            f"Espacio {codigo_anterior} renombrado a {nuevo}.\nRecuerda guardar para dejar el cambio fijo.",
        )

    def _eliminar(self):
        item = self._item_requerido_para("eliminarlo")
        if not item:
            return
        codigo = item.codigo
        confirmar = QMessageBox.question(
            self,
            "Eliminar",
            "Se quitara este espacio solo del mapa visual.\n"
            "No se borran clientes, contratos ni pagos.\n\n"
            "Quieres continuar?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirmar != QMessageBox.Yes:
            return
        self._eliminados.add(item.codigo)
        self.scene.removeItem(item)
        self._set_mapa_dirty(True)
        QMessageBox.information(
            self,
            "Mapa",
            f"Espacio {codigo} quitado del mapa.\nRecuerda guardar para confirmar la eliminacion.",
        )

    def _item_seleccionado(self):
        for item in self.scene.selectedItems():
            if isinstance(item, EspacioItem):
                return item
        return None

    def _item_en_pos_vista(self, pos):
        scene_pos = self.view.mapToScene(pos)
        item = self.scene.itemAt(scene_pos, self.view.transform())
        while item is not None and not isinstance(item, EspacioItem):
            item = item.parentItem()
        return item

    def _menu_contextual(self, pos):
        item = self._item_en_pos_vista(pos)
        if not item:
            return
        item.setSelected(True)
        menu = QMenu(self)
        accion_registro_hora = menu.addAction("Registro por hora")
        accion_desocupar = menu.addAction("Desocupar espacio")
        elegido = menu.exec(self.view.viewport().mapToGlobal(pos))
        if elegido == accion_registro_hora:
            self._abrir_registro_hora(item)
        elif elegido == accion_desocupar:
            self._desocupar_desde_mapa(item)

    def _abrir_registro_hora(self, item):
        parent = self.parent()
        if not parent or not hasattr(parent, "ui"):
            return
        parent.ui.stack.setCurrentIndex(1)
        parent.ui.input_espacio_est.setText(item.codigo)
        parent.ui.input_patente_est.setFocus()
        parent.raise_()
        parent.activateWindow()
        self.accept()

    def _abrir_salida_desde_mapa(self, item, movimiento):
        parent = self.parent()
        if not parent or not hasattr(parent, "ui"):
            return False
        if hasattr(parent, "_abrir_menu_estacionamiento"):
            if not parent._abrir_menu_estacionamiento(popup_parent=self):
                return False
        else:
            parent.ui.stack.setCurrentIndex(1)

        patente = _formatear_patente((movimiento["patente"] or "").strip())
        parent.ui.input_patente_est.setText(patente)
        parent.ui.input_espacio_est.setText((item.codigo or "").strip().upper())

        if hasattr(parent.ui, "btn_salida_est"):
            try:
                parent.ui.btn_salida_est.setFocus()
            except Exception:
                pass

        parent.raise_()
        parent.activateWindow()
        self.accept()
        return True

    def _desocupar_desde_mapa(self, item):
        codigo = item.codigo
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT id_espacio, id_cliente FROM espacios WHERE codigo = ? AND activo = 1",
                (codigo,),
            )
            row = cur.fetchone()
            if not row:
                QMessageBox.warning(
                    self,
                    "Desocupar",
                    "Ese espacio no existe en la base.\n"
                    "Guarda el mapa o actualiza la informacion antes de intentar desocuparlo.",
                )
                return
            id_espacio = row["id_espacio"]

            cur.execute(
                "SELECT m.id_movimiento, m.fecha_ingreso, m.id_tarifa_aplicada, "
                "m.tarifa_hora_aplicada, v.patente, "
                "COALESCE(NULLIF(TRIM(m.tipo_vehiculo), ''), 'AUTO') AS tipo_vehiculo "
                "FROM movimientos m "
                "JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
                "WHERE m.id_espacio = ? AND m.fecha_salida IS NULL "
                "ORDER BY m.fecha_ingreso DESC",
                (id_espacio,),
            )
            movimientos_activos = cur.fetchall()
            mov_activos = len(movimientos_activos)

            if mov_activos > 0:
                movimiento = movimientos_activos[0]
                if self._abrir_salida_desde_mapa(item, movimiento):
                    return

            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos WHERE id_espacio = ? AND activo = 1",
                (id_espacio,),
            )
            contratos_activos = cur.fetchone()[0] or 0

            tiene_cliente = row["id_cliente"] is not None
            if mov_activos == 0 and contratos_activos == 0 and not tiene_cliente:
                QMessageBox.information(
                    self,
                    "Desocupar",
                    "Ese espacio ya esta libre.\nNo hay nada para cerrar o liberar.",
                )
                return

            tarifa_row = None
            if mov_activos > 0:
                for mov in movimientos_activos:
                    tarifa_mov = float(mov["tarifa_hora_aplicada"] or 0.0)
                    if tarifa_mov <= 0:
                        if tarifa_row is None:
                            cur.execute(
                                "SELECT precio_hora, precio_hora_auto, precio_hora_moto, precio_hora_camioneta "
                                "FROM tarifas WHERE activa = 1 "
                                "ORDER BY fecha_desde DESC LIMIT 1"
                            )
                            tarifa_row = cur.fetchone()
                        if not tarifa_row:
                            QMessageBox.warning(
                                self,
                                "Desocupar",
                                "No hay tarifa por hora definida para calcular el cierre del estacionamiento.\n"
                                "Carga una tarifa antes de desocupar este espacio.",
                            )
                            return
                        tarifa_mov = _tarifa_hora_desde_row(tarifa_row, mov["tipo_vehiculo"])
                    if tarifa_mov is None:
                        QMessageBox.warning(
                            self,
                            "Desocupar",
                            (
                                "No hay tarifa por hora definida para "
                                f"{_texto_tipo_vehiculo(mov['tipo_vehiculo'])}.\n"
                                "Carga esa tarifa antes de cerrar el movimiento."
                            ),
                        )
                        return

            confirmar = QMessageBox.question(
                self,
                "Desocupar espacio",
                "Se liberara el espacio y se cerraran ocupaciones activas.\nContinuar?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirmar != QMessageBox.Yes:
                return

            detalle_salida = []
            if mov_activos > 0:
                salida_dt = datetime.now()
                salida_db = salida_dt.strftime("%Y-%m-%d %H:%M:%S")
                salida_txt = salida_dt.strftime("%d/%m/%Y %H:%M:%S")
                for mov in movimientos_activos:
                    fecha_ingreso = mov["fecha_ingreso"] or ""
                    dt_ing = _parse_fecha_db(fecha_ingreso)
                    if not dt_ing:
                        dt_ing = salida_dt
                    tarifa_mov = float(mov["tarifa_hora_aplicada"] or 0.0)
                    if tarifa_mov <= 0:
                        tarifa_mov = _tarifa_hora_desde_row(tarifa_row, mov["tipo_vehiculo"])
                    _, total = _calcular_total_estadia(
                        dt_ing,
                        salida_dt,
                        tarifa_mov,
                        tolerancia_min=15,
                    )

                    cur.execute(
                        "UPDATE movimientos SET fecha_salida = ?, total = ? WHERE id_movimiento = ?",
                        (salida_db, total, mov["id_movimiento"]),
                    )
                    cur.execute(
                        "INSERT INTO pagos (id_movimiento, monto, metodo) VALUES (?, ?, ?)",
                        (mov["id_movimiento"], total, "Mapa"),
                    )

                    ingreso_txt = dt_ing.strftime("%d/%m/%Y %H:%M:%S")
                    detalle_salida.append(
                        (
                            _formatear_patente(mov["patente"] or "-"),
                            ingreso_txt,
                            salida_txt,
                            total,
                            _texto_tipo_vehiculo(mov["tipo_vehiculo"]),
                        )
                    )

            if contratos_activos > 0:
                cur.execute(
                    "UPDATE cochera_contratos SET activo = 0 WHERE id_espacio = ? AND activo = 1",
                    (id_espacio,),
                )

            cur.execute(
                "UPDATE espacios SET id_cliente = NULL WHERE id_espacio = ?",
                (id_espacio,),
            )
            conn.commit()

            _auditar(
                self,
                "Espacio desocupado desde mapa",
                f"Codigo {codigo} - Movimientos cerrados: {mov_activos} - Contratos dados de baja: {contratos_activos}",
            )
            self._actualizar_item_por_codigo(item)
            if detalle_salida:
                bloques = []
                for patente, ingreso_txt, salida_txt, total, tipo_txt in detalle_salida:
                    bloques.append(
                        f"Patente: {patente}\n"
                        f"Tipo: {tipo_txt}\n"
                        f"Ingreso: {ingreso_txt}\n"
                        f"Salida: {salida_txt}\n"
                        f"Precio: {_fmt_money(total)}"
                    )
                detalle_txt = "\n\n".join(bloques)
                QMessageBox.information(
                    self,
                    "Desocupar",
                    f"Espacio {codigo} desocupado correctamente.\n\n{detalle_txt}",
                )
            else:
                QMessageBox.information(
                    self,
                    "Desocupar",
                    f"Espacio {codigo} desocupado correctamente.",
                )
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo desocupar el espacio.")
        finally:
            if conn:
                conn.close()

    def _cargar(self):
        self.scene.setProperty("suspend_dirty", True)
        self.scene.clear()
        self._eliminados.clear()
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT m.codigo, m.x, m.y, m.w, m.h, "
                "COALESCE(e.es_reservado, 0), e.id_cliente, "
                "CASE WHEN mv.id_movimiento IS NULL THEN 0 ELSE 1 END, "
                "v.patente, c.nombre "
                "FROM espacios_mapa m "
                "LEFT JOIN espacios e ON e.codigo = m.codigo "
                "LEFT JOIN movimientos mv ON mv.id_espacio = e.id_espacio AND mv.fecha_salida IS NULL "
                "LEFT JOIN vehiculos v ON v.id_vehiculo = mv.id_vehiculo "
                "LEFT JOIN clientes c ON c.id_cliente = e.id_cliente "
                "ORDER BY m.codigo"
            )
            for (
                codigo,
                x,
                y,
                w,
                h,
                es_reservado,
                id_cliente,
                ocupado,
                patente,
                nombre,
            ) in cur.fetchall():
                estado, color = self._estado_por_datos(es_reservado, id_cliente, ocupado)
                item = EspacioItem(
                    codigo,
                    QRectF(0, 0, w, h),
                    color,
                    estado=estado,
                    grid=self._grid,
                )
                if not self._editable:
                    item.setFlags(QGraphicsItem.ItemIsSelectable)
                info = ""
                if ocupado == 1 and patente:
                    info = _formatear_patente(patente)
                elif (id_cliente is not None or es_reservado == 1) and nombre:
                    partes = [p for p in nombre.strip().split() if p]
                    info = partes[-1] if partes else nombre
                elif es_reservado == 1:
                    info = "Reservado"
                item.set_info(info)
                x_snap, y_snap = self._snap_a_cuadricula(x, y)
                item.setPos(x_snap, y_snap)
                self.scene.addItem(item)
            self._actualizar_area_trabajo()
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo cargar el mapa.")
        finally:
            if conn:
                conn.close()
            self.scene.setProperty("suspend_dirty", False)
            self._set_mapa_dirty(False)

    def _recargar(self):
        if self._editable and self._mapa_tiene_cambios():
            respuesta = QMessageBox.question(
                self,
                "Limpiar mapa",
                "Limpiar deshace los cambios sin guardar.\nContinuar?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if respuesta != QMessageBox.Yes:
                return
        elif self._editable and not self._mapa_tiene_cambios():
            QMessageBox.information(
                self,
                "Limpiar mapa",
                "No hay cambios sin guardar para deshacer.",
            )
            return
        self._cargar()
        if self._editable:
            QMessageBox.information(
                self,
                "Mapa",
                "Mapa recargado correctamente.",
            )

    def _set_cochera(self, valor):
        item = self._item_requerido_para(
            "marcarlo como cochera" if valor else "quitarle la marca de cochera"
        )
        if not item:
            return
        codigo = item.codigo
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COALESCE(es_reservado, 0) AS es_reservado FROM espacios WHERE codigo = ?",
                (codigo,),
            )
            row_actual = cur.fetchone()
            es_cochera_actual = int((row_actual["es_reservado"] if row_actual else 0) or 0) == 1
            if valor and es_cochera_actual:
                QMessageBox.information(
                    self,
                    "Cochera",
                    f"El espacio {codigo} ya esta marcado como cochera.",
                )
                return
            if not valor and not es_cochera_actual:
                QMessageBox.information(
                    self,
                    "Cochera",
                    f"El espacio {codigo} ya esta disponible para estacionamiento.",
                )
                return
            if not valor:
                cur.execute(
                    "SELECT COUNT(*) FROM cochera_contratos "
                    "WHERE id_espacio = ("
                    "SELECT id_espacio FROM espacios WHERE codigo = ? AND activo = 1"
                    ") "
                    "AND COALESCE(en_historial, 0) = 0",
                    (codigo,),
                )
                contratos_vigentes = int((cur.fetchone()[0] or 0) or 0)
                if contratos_vigentes > 0:
                    QMessageBox.warning(
                        self,
                        "Cochera",
                        "No se puede quitar la marca de cochera porque ese espacio "
                        "todavia tiene contratos fuera del historial.\n"
                        "Da de baja o pasa esos contratos a historial primero.",
                    )
                    return
            if valor:
                cur.execute(
                    "SELECT COUNT(*) FROM movimientos m "
                    "JOIN espacios e ON e.id_espacio = m.id_espacio "
                    "WHERE e.codigo = ? AND m.fecha_salida IS NULL",
                    (codigo,),
                )
                if (cur.fetchone()[0] or 0) > 0:
                    QMessageBox.warning(
                        self,
                        "Cochera",
                        "No se puede marcar como cochera porque el espacio tiene un ingreso activo.\n"
                        "Registra la salida o desocupa el lugar primero.",
                    )
                    return
            cur.execute(
                "INSERT INTO espacios (codigo, es_reservado, activo) "
                "VALUES (?, ?, 1) "
                "ON CONFLICT(codigo) DO UPDATE SET es_reservado = excluded.es_reservado",
                (codigo, 1 if valor else 0),
            )
            conn.commit()
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo actualizar el espacio.")
            return
        finally:
            if conn:
                conn.close()

        self._actualizar_item_por_codigo(item)
        QMessageBox.information(
            self,
            "Cochera",
            (
                f"El espacio {codigo} se marco como cochera."
                if valor
                else f"El espacio {codigo} dejo de estar marcado como cochera."
            )
            + "\nRecuerda guardar para dejar el cambio fijo.",
        )

    def _actualizar_item_por_codigo(self, item):
        conn = None
        row = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COALESCE(e.es_reservado, 0), e.id_cliente, "
                "CASE WHEN mv.id_movimiento IS NULL THEN 0 ELSE 1 END, "
                "v.patente, c.nombre "
                "FROM espacios e "
                "LEFT JOIN movimientos mv ON mv.id_espacio = e.id_espacio AND mv.fecha_salida IS NULL "
                "LEFT JOIN vehiculos v ON v.id_vehiculo = mv.id_vehiculo "
                "LEFT JOIN clientes c ON c.id_cliente = e.id_cliente "
                "WHERE e.codigo = ?",
                (item.codigo,),
            )
            row = cur.fetchone()
        except sqlite3.Error:
            row = None
        finally:
            if conn:
                conn.close()

        if not row:
            item.set_estado("LIBRE", self._color_libre)
            item.set_info("")
            return

        es_reservado, id_cliente, ocupado, patente, nombre = row
        estado, color = self._estado_por_datos(es_reservado, id_cliente, ocupado)
        info = ""
        if ocupado == 1 and patente:
            info = _formatear_patente(patente)
        elif (id_cliente is not None or es_reservado == 1) and nombre:
            partes = [p for p in nombre.strip().split() if p]
            info = partes[-1] if partes else nombre
        elif es_reservado == 1:
            info = "Reservado"
        item.set_estado(estado, color)
        item.set_info(info)

    def _actualizar_colores_escena(self):
        conn = None
        status = {}
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT m.codigo, "
                "COALESCE(e.es_reservado, 0) AS es_reservado, "
                "e.id_cliente, "
                "CASE WHEN mv.id_movimiento IS NULL THEN 0 ELSE 1 END AS ocupado, "
                "v.patente, c.nombre "
                "FROM espacios_mapa m "
                "LEFT JOIN espacios e ON e.codigo = m.codigo "
                "LEFT JOIN movimientos mv ON mv.id_espacio = e.id_espacio AND mv.fecha_salida IS NULL "
                "LEFT JOIN vehiculos v ON v.id_vehiculo = mv.id_vehiculo "
                "LEFT JOIN clientes c ON c.id_cliente = e.id_cliente"
            )
            for row in cur.fetchall():
                status[row["codigo"]] = row
        except sqlite3.Error:
            status = {}
        finally:
            if conn:
                conn.close()

        for item in self.scene.items():
            if not isinstance(item, EspacioItem):
                continue
            row = status.get(item.codigo)
            if not row:
                estado = (item.estado or "LIBRE").upper()
                if estado == "OCUPADO":
                    color = self._color_ocupado
                elif estado == "COCHERA":
                    color = self._color_cochera
                else:
                    color = self._color_libre
                item.set_estado(estado, color)
                continue
            estado, color = self._estado_por_datos(
                row["es_reservado"], row["id_cliente"], row["ocupado"]
            )
            item.set_estado(estado, color)
            info = ""
            if row["ocupado"] == 1 and row["patente"]:
                info = _formatear_patente(row["patente"])
            elif (row["id_cliente"] is not None or row["es_reservado"] == 1) and row["nombre"]:
                partes = [p for p in row["nombre"].strip().split() if p]
                info = partes[-1] if partes else row["nombre"]
            elif row["es_reservado"] == 1:
                info = "Reservado"
            item.set_info(info)

    def _guardar(self, mostrar_mensaje=True):
        if not self._mapa_tiene_cambios():
            if mostrar_mensaje:
                QMessageBox.information(
                    self,
                    "Mapa",
                    "No hay cambios pendientes para guardar.",
                )
            return True
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()

            for codigo in self._eliminados:
                cur.execute("DELETE FROM espacios_mapa WHERE codigo = ?", (codigo,))

            for item in self.scene.items():
                if not isinstance(item, EspacioItem):
                    continue
                codigo = item.codigo
                pos = item.pos()
                rect = item.rect()
                # Si el cuadrado existe en el mapa pero todavia no en espacios, lo doy de alta aca y queda todo parejo.
                cur.execute(
                    "INSERT OR IGNORE INTO espacios (codigo, es_reservado, activo) "
                    "VALUES (?, 0, 1)",
                    (codigo,),
                )
                cur.execute(
                    "INSERT INTO espacios_mapa (codigo, x, y, w, h) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(codigo) DO UPDATE SET "
                    "x=excluded.x, y=excluded.y, w=excluded.w, h=excluded.h",
                    (codigo, int(pos.x()), int(pos.y()), int(rect.width()), int(rect.height())),
                )

            conn.commit()
            self._set_mapa_dirty(False)
            if mostrar_mensaje:
                QMessageBox.information(
                    self,
                    "Mapa",
                    "Mapa guardado correctamente.\n"
                    "Los cambios visuales ya quedaron registrados.",
                )
            return True
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo guardar el mapa.")
            return False
        finally:
            if conn:
                conn.close()

    def closeEvent(self, event):
        if not self._editable or not self._mapa_tiene_cambios():
            event.accept()
            return
        respuesta = _confirmar_guardado_pendiente(
            self,
            "Hay cambios en el mapa.\nQuieres guardarlos antes de salir?",
        )
        if respuesta == QMessageBox.Cancel:
            event.ignore()
            return
        if respuesta == QMessageBox.No:
            event.accept()
            return
        if self._guardar(mostrar_mensaje=False):
            event.accept()
        else:
            event.ignore()

class VencimientosDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vencimientos de contratos")
        self.setMinimumWidth(520)
        self.setMinimumHeight(560)
        self._aplicar_estilo_tema()

        layout = QVBoxLayout(self)

        titulo_vencidos = QLabel("Vencidos")
        titulo_vencidos.setObjectName("titulo_vencidos")
        layout.addWidget(titulo_vencidos)

        self.label_vencidos = QLabel("Total vencidos: 0")
        self.label_vencidos.setObjectName("resumen_vencidos")
        layout.addWidget(self.label_vencidos)

        self.lista_vencidos = QListWidget()
        layout.addWidget(self.lista_vencidos)
        acciones_vencidos = QHBoxLayout()
        self.btn_wsp_vencido = QPushButton("WhatsApp seleccionado")
        self.btn_wsp_vencidos = QPushButton("WhatsApp a vencidos")
        self.btn_wsp_vencido.setProperty("variant", "success")
        self.btn_wsp_vencidos.setProperty("variant", "success")
        self.btn_wsp_vencido.setIcon(_icono_whatsapp(18))
        self.btn_wsp_vencidos.setIcon(_icono_whatsapp(18))
        self.btn_wsp_vencido.setIconSize(QSize(16, 16))
        self.btn_wsp_vencidos.setIconSize(QSize(16, 16))
        acciones_vencidos.addWidget(self.btn_wsp_vencido)
        acciones_vencidos.addWidget(self.btn_wsp_vencidos)
        acciones_vencidos.addStretch(1)
        layout.addLayout(acciones_vencidos)

        titulo_proximos = QLabel("Vencimientos proximos (7 dias)")
        titulo_proximos.setObjectName("titulo_proximos")
        layout.addWidget(titulo_proximos)

        self.label_proximos = QLabel("Total proximos: 0")
        self.label_proximos.setObjectName("resumen_proximos")
        layout.addWidget(self.label_proximos)

        self.lista_proximos = QListWidget()
        layout.addWidget(self.lista_proximos)
        acciones_proximos = QHBoxLayout()
        self.btn_wsp_proximo = QPushButton("WhatsApp seleccionado")
        self.btn_wsp_proximos = QPushButton("WhatsApp a proximos")
        self.btn_wsp_hoy = QPushButton("WhatsApp vence hoy")
        self.btn_wsp_proximo.setProperty("variant", "success")
        self.btn_wsp_proximos.setProperty("variant", "success")
        self.btn_wsp_hoy.setProperty("variant", "success")
        self.btn_wsp_proximo.setIcon(_icono_whatsapp(18))
        self.btn_wsp_proximos.setIcon(_icono_whatsapp(18))
        self.btn_wsp_hoy.setIcon(_icono_whatsapp(18))
        self.btn_wsp_proximo.setIconSize(QSize(16, 16))
        self.btn_wsp_proximos.setIconSize(QSize(16, 16))
        self.btn_wsp_hoy.setIconSize(QSize(16, 16))
        acciones_proximos.addWidget(self.btn_wsp_proximo)
        acciones_proximos.addWidget(self.btn_wsp_proximos)
        acciones_proximos.addWidget(self.btn_wsp_hoy)
        acciones_proximos.addStretch(1)
        layout.addLayout(acciones_proximos)

        acciones_finales = QHBoxLayout()
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_actualizar.setProperty("variant", "neutral")
        self.btn_cerrar.setProperty("variant", "neutral")
        self.btn_actualizar.setToolTip(
            "Vuelve a consultar contratos vencidos y proximos a vencer."
        )
        self.btn_cerrar.setToolTip("Cierra esta ventana de vencimientos.")
        acciones_finales.addStretch(1)
        acciones_finales.addWidget(self.btn_actualizar)
        acciones_finales.addWidget(self.btn_cerrar)
        layout.addLayout(acciones_finales)

        self.lista_vencidos.itemDoubleClicked.connect(
            lambda *_: self._enviar_whatsapp_item(self.lista_vencidos, "vencido")
        )
        self.lista_proximos.itemDoubleClicked.connect(
            lambda *_: self._enviar_whatsapp_item(self.lista_proximos, "proximo")
        )
        self.btn_wsp_vencido.clicked.connect(
            lambda: self._enviar_whatsapp_item(self.lista_vencidos, "vencido")
        )
        self.btn_wsp_vencidos.clicked.connect(
            lambda: self._enviar_whatsapp_lote(self.lista_vencidos, "vencidos")
        )
        self.btn_wsp_proximo.clicked.connect(
            lambda: self._enviar_whatsapp_item(self.lista_proximos, "proximo")
        )
        self.btn_wsp_proximos.clicked.connect(
            lambda: self._enviar_whatsapp_lote(self.lista_proximos, "proximos")
        )
        self.btn_wsp_hoy.clicked.connect(self._enviar_whatsapp_vence_hoy)
        self.btn_actualizar.clicked.connect(self._cargar)
        self.btn_cerrar.clicked.connect(self.accept)
        self.lista_vencidos.itemSelectionChanged.connect(self._actualizar_estado_acciones)
        self.lista_proximos.itemSelectionChanged.connect(self._actualizar_estado_acciones)

        self._cargar()

    def _tema_claro(self):
        return (_config_get("ui_tema", "oscuro") or "oscuro").strip().lower() == "claro"

    def _aplicar_estilo_tema(self):
        if self._tema_claro():
            self.setStyleSheet(
                """
                QDialog {
                    background-color: #eef2f7;
                    color: #1f2937;
                }
                QLabel#titulo_vencidos {
                    color: #b91c1c;
                    font-size: 14px;
                    font-weight: 700;
                }
                QLabel#titulo_proximos {
                    color: #b45309;
                    font-size: 14px;
                    font-weight: 700;
                }
                QLabel#resumen_vencidos {
                    color: #7f1d1d;
                    font-weight: 600;
                }
                QLabel#resumen_proximos {
                    color: #92400e;
                    font-weight: 600;
                }
                QListWidget {
                    background-color: #ffffff;
                    border: 1px solid #d5dde6;
                    border-radius: 8px;
                    padding: 4px;
                }
                QListWidget::viewport {
                    background-color: #ffffff;
                }
                QListWidget::item {
                    padding: 7px 9px;
                    border-radius: 6px;
                    margin: 2px 0px;
                }
                """
            )
            return

        self.setStyleSheet(
            """
            QDialog {
                background-color: #161a20;
            }
            QLabel#titulo_vencidos {
                color: #fca5a5;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#titulo_proximos {
                color: #fcd34d;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#resumen_vencidos {
                color: #fecaca;
                font-weight: 600;
            }
            QLabel#resumen_proximos {
                color: #fde68a;
                font-weight: 600;
            }
            QListWidget {
                background-color: #161a20;
                border: 1px solid #3a4452;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::viewport {
                background-color: #161a20;
            }
            QListWidget::item {
                padding: 7px 9px;
                border-radius: 6px;
                margin: 2px 0px;
            }
            """
        )

    def _texto_estado_vencimiento(self, fecha_db):
        fecha = QDate.fromString((fecha_db or "").strip(), "yyyy-MM-dd")
        if not fecha.isValid():
            return "fecha invalida"
        hoy = QDate.currentDate()
        dias = hoy.daysTo(fecha)
        if dias < 0:
            return f"vencido hace {abs(dias)} dia/s"
        if dias == 0:
            return "vence hoy"
        return f"vence en {dias} dia/s"

    def _dias_hasta(self, fecha_db):
        fecha = QDate.fromString((fecha_db or "").strip(), "yyyy-MM-dd")
        if not fecha.isValid():
            return None
        return QDate.currentDate().daysTo(fecha)

    def _formatear_recordatorio(self, row):
        nombre = (row.get("nombre") or "").strip() or "cliente"
        modelo = (row.get("modelo") or "").strip()
        monto = float(row.get("monto_mensual") or 0.0)
        tipo_vehiculo = row.get("tipo_vehiculo") or "AUTO"
        fecha_venc = QDate.fromString(row.get("fecha_vencimiento") or "", "yyyy-MM-dd")
        hoy = QDate.currentDate()
        vencimiento = "Sin vencimiento"
        if fecha_venc.isValid():
            dias = hoy.daysTo(fecha_venc)
            base = fecha_venc.toString("dd/MM/yyyy")
            if dias < 0:
                vencimiento = f"{base} (vencido hace {abs(dias)} dia/s)"
            elif dias == 0:
                vencimiento = f"{base} (vence hoy)"
            else:
                vencimiento = f"{base} (en {dias} dia/s)"
        return {
            "nombre": nombre,
            "telefono": (row.get("telefono") or "").strip(),
            "modelo": modelo,
            "vencimiento": vencimiento,
            "deuda": _texto_cuota_recordatorio(tipo_vehiculo, monto),
            "codigo": (row.get("codigo") or "").strip() or "-",
            "patente": _formatear_patente(row.get("patente") or ""),
            "id_contrato": row.get("id_contrato"),
        }

    def _abrir_whatsapp_resumen(self, resumen):
        numero = _telefono_a_whatsapp(resumen.get("telefono"))
        if not numero:
            return False, "sin_numero"
        mensaje = _render_mensaje_whatsapp(
            resumen.get("nombre") or "cliente",
            resumen.get("vencimiento") or "sin vencimiento",
            resumen.get("deuda") or "$ 0.00",
            modelo=resumen.get("modelo") or "",
            patente=resumen.get("patente") or "",
        )
        url = QUrl(
            f"https://api.whatsapp.com/send?phone={quote(numero)}&text={quote(mensaje)}"
        )
        if not QDesktopServices.openUrl(url):
            return False, "no_abrio"
        return True, numero

    def _contratos_recordados_hoy(self):
        conn = None
        ids = set()
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT detalle FROM auditoria "
                "WHERE accion = ? AND date(fecha) = date('now', 'localtime')",
                ("Recordatorio WhatsApp vencimientos",),
            )
            for row in cur.fetchall():
                detalle = str(row["detalle"] or "")
                match = re.search(r"Contrato\s+(\d+)", detalle)
                if match:
                    ids.add(int(match.group(1)))
        except sqlite3.Error:
            return set()
        finally:
            if conn:
                conn.close()
        return ids

    def _fila_valida_desde_item(self, item):
        if not item:
            return None
        row = item.data(Qt.UserRole)
        return row if row else None

    def _filas_validas_lista(self, lista):
        filas = []
        if lista is None:
            return filas
        for idx in range(lista.count()):
            item = lista.item(idx)
            row = self._fila_valida_desde_item(item)
            if row:
                filas.append(row)
        return filas

    def _actualizar_estado_acciones(self):
        row_vencido = self._fila_valida_desde_item(self.lista_vencidos.currentItem())
        row_proximo = self._fila_valida_desde_item(self.lista_proximos.currentItem())
        filas_vencidos = self._filas_validas_lista(self.lista_vencidos)
        filas_proximos = self._filas_validas_lista(self.lista_proximos)
        filas_hoy = [
            row
            for row in filas_proximos
            if self._dias_hasta(row.get("fecha_vencimiento")) == 0
        ]

        self.btn_wsp_vencido.setEnabled(bool(row_vencido))
        self.btn_wsp_proximo.setEnabled(bool(row_proximo))
        self.btn_wsp_vencidos.setEnabled(bool(filas_vencidos))
        self.btn_wsp_proximos.setEnabled(bool(filas_proximos))
        self.btn_wsp_hoy.setEnabled(bool(filas_hoy))

        self.btn_wsp_vencido.setToolTip(
            "Enviar recordatorio al contrato vencido seleccionado."
            if row_vencido
            else "Selecciona un contrato vencido de la lista para enviarle WhatsApp."
        )
        self.btn_wsp_proximo.setToolTip(
            "Enviar recordatorio al contrato proximo seleccionado."
            if row_proximo
            else "Selecciona un contrato proximo de la lista para enviarle WhatsApp."
        )
        self.btn_wsp_vencidos.setToolTip(
            f"Abrir WhatsApp para los {len(filas_vencidos)} contrato/s vencido/s."
            if filas_vencidos
            else "No hay contratos vencidos disponibles para enviar."
        )
        self.btn_wsp_proximos.setToolTip(
            f"Abrir WhatsApp para los {len(filas_proximos)} contrato/s proximo/s."
            if filas_proximos
            else "No hay contratos proximos disponibles para enviar."
        )
        self.btn_wsp_hoy.setToolTip(
            f"Abrir WhatsApp para los {len(filas_hoy)} contrato/s que vencen hoy."
            if filas_hoy
            else "No hay contratos que venzan hoy en la lista de proximos."
        )

    def _enviar_whatsapp_item(self, lista, categoria):
        if lista is None:
            QMessageBox.warning(
                self,
                "WhatsApp",
                "Selecciona un contrato de la lista antes de abrir WhatsApp.",
            )
            return
        seleccionados = lista.selectedItems()
        item = seleccionados[0] if seleccionados else None
        if not item:
            QMessageBox.warning(
                self,
                "WhatsApp",
                "Selecciona un contrato de la lista antes de abrir WhatsApp.",
            )
            return
        row = item.data(Qt.UserRole)
        if not row:
            QMessageBox.warning(
                self,
                "WhatsApp",
                "Ese registro no tiene datos para enviar recordatorio.",
            )
            return
        resumen = self._formatear_recordatorio(row)
        ok, extra = self._abrir_whatsapp_resumen(resumen)
        if not ok:
            if extra == "sin_numero":
                QMessageBox.warning(
                    self,
                    "WhatsApp",
                    "El cliente no tiene un telefono valido para WhatsApp.",
                )
            else:
                QMessageBox.warning(self, "WhatsApp", "No se pudo abrir WhatsApp.")
            return
        _auditar(
            self,
            "Recordatorio WhatsApp vencimientos",
            (
                f"Contrato {resumen.get('id_contrato') or '-'} - "
                f"{categoria} - {resumen.get('nombre') or '-'} - {extra}"
            ),
        )
        self._cargar()

    def _enviar_whatsapp_lote(self, lista, categoria):
        filas = []
        if lista is not None:
            for idx in range(lista.count()):
                item = lista.item(idx)
                row = item.data(Qt.UserRole) if item else None
                if row:
                    filas.append(row)
        self._enviar_whatsapp_lote_desde_filas(filas, categoria)

    def _enviar_whatsapp_vence_hoy(self):
        filas = []
        for idx in range(self.lista_proximos.count()):
            item = self.lista_proximos.item(idx)
            row = item.data(Qt.UserRole) if item else None
            if not row:
                continue
            dias = self._dias_hasta(row.get("fecha_vencimiento"))
            if dias == 0:
                filas.append(row)
        if not filas:
            QMessageBox.information(
                self,
                "WhatsApp",
                "No hay contratos que venzan hoy.",
            )
            return
        self._enviar_whatsapp_lote_desde_filas(filas, "vence hoy")

    def _enviar_whatsapp_lote_desde_filas(self, filas, categoria):
        if not filas:
            QMessageBox.information(
                self,
                "WhatsApp",
                "No hay contratos para enviar en esta lista.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "WhatsApp",
            f"Se abriran chats de WhatsApp para {len(filas)} contrato/s ({categoria}). Continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if confirm != QMessageBox.Yes:
            return

        urls = []
        sin_numero = 0
        auditables = []
        for row in filas:
            resumen = self._formatear_recordatorio(row)
            numero = _telefono_a_whatsapp(resumen.get("telefono"))
            if not numero:
                sin_numero += 1
                continue
            mensaje = _render_mensaje_whatsapp(
                resumen.get("nombre") or "cliente",
                resumen.get("vencimiento") or "sin vencimiento",
                resumen.get("deuda") or "$ 0.00",
                modelo=resumen.get("modelo") or "",
                patente=resumen.get("patente") or "",
            )
            urls.append(
                QUrl(
                    f"https://api.whatsapp.com/send?phone={quote(numero)}&text={quote(mensaje)}"
                )
            )
            auditables.append((resumen, numero))

        if not urls:
            QMessageBox.warning(
                self,
                "WhatsApp",
                "Ningun contrato tiene un telefono valido para WhatsApp.",
            )
            return

        for idx, url in enumerate(urls):
            QTimer.singleShot(idx * 350, lambda u=url: QDesktopServices.openUrl(u))
        for resumen, numero in auditables:
            _auditar(
                self,
                "Recordatorio WhatsApp vencimientos",
                (
                    f"Contrato {resumen.get('id_contrato') or '-'} - "
                    f"{categoria} - {resumen.get('nombre') or '-'} - {numero}"
                ),
            )
        _auditar(
            self,
            "Recordatorio WhatsApp masivo",
            f"{categoria}: {len(urls)} chat/s abiertos, {sin_numero} sin numero valido",
        )
        self._cargar()
        QMessageBox.information(
            self,
            "WhatsApp",
            f"Se abrieron {len(urls)} chat/s de WhatsApp.\n"
            f"Sin numero valido: {sin_numero}.",
        )

    def _cargar(self):
        self.lista_vencidos.clear()
        self.lista_proximos.clear()
        tema_claro = self._tema_claro()
        recordados_hoy = self._contratos_recordados_hoy()
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()

            cur.execute(
                "SELECT cc.id_contrato, c.nombre, COALESCE(c.telefono, '') AS telefono, "
                "COALESCE(e.codigo, '-') AS codigo, cc.fecha_vencimiento, "
                "cc.monto_mensual, COALESCE(v_sel.patente, '') AS patente, "
                "COALESCE(v_sel.modelo, '') AS modelo, "
                "COALESCE(NULLIF(TRIM(v_sel.tipo_vehiculo), ''), 'AUTO') AS tipo_vehiculo "
                "FROM cochera_contratos cc "
                "JOIN clientes c ON c.id_cliente = cc.id_cliente "
                "LEFT JOIN espacios e ON e.id_espacio = cc.id_espacio "
                "LEFT JOIN vehiculos v_sel ON v_sel.id_vehiculo = cc.id_vehiculo "
                "WHERE cc.activo = 1 "
                "AND cc.fecha_vencimiento IS NOT NULL "
                "AND date(cc.fecha_vencimiento) < date('now') "
                "ORDER BY cc.fecha_vencimiento "
                "LIMIT 100"
            )
            vencidos = cur.fetchall()

            for row in vencidos:
                nombre = row["nombre"] or "-"
                codigo = row["codigo"] or "-"
                fecha = row["fecha_vencimiento"] or "-"
                estado = self._texto_estado_vencimiento(fecha)
                avisado_hoy = int(row["id_contrato"] or 0) in recordados_hoy
                texto = f"{fecha} | {nombre} | Espacio {codigo} | {estado}"
                if avisado_hoy:
                    texto += " | avisado hoy"
                item = QListWidgetItem(texto)
                item.setData(Qt.UserRole, dict(row))
                if tema_claro:
                    item.setBackground(QColor("#fee2e2"))
                    item.setForeground(QColor("#991b1b"))
                else:
                    item.setBackground(QColor("#3b1f25"))
                    item.setForeground(QColor("#fecaca"))
                if avisado_hoy:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setToolTip("Ya se envio un recordatorio hoy.")
                self.lista_vencidos.addItem(item)
            self.label_vencidos.setText(f"Total vencidos: {len(vencidos)}")
            if not vencidos:
                item = QListWidgetItem("Sin contratos vencidos.")
                item.setForeground(QColor("#64748b" if tema_claro else "#9ca3af"))
                self.lista_vencidos.addItem(item)

            cur.execute(
                "SELECT cc.id_contrato, c.nombre, COALESCE(c.telefono, '') AS telefono, "
                "COALESCE(e.codigo, '-') AS codigo, cc.fecha_vencimiento, "
                "cc.monto_mensual, COALESCE(v_sel.patente, '') AS patente, "
                "COALESCE(v_sel.modelo, '') AS modelo, "
                "COALESCE(NULLIF(TRIM(v_sel.tipo_vehiculo), ''), 'AUTO') AS tipo_vehiculo "
                "FROM cochera_contratos cc "
                "JOIN clientes c ON c.id_cliente = cc.id_cliente "
                "LEFT JOIN espacios e ON e.id_espacio = cc.id_espacio "
                "LEFT JOIN vehiculos v_sel ON v_sel.id_vehiculo = cc.id_vehiculo "
                "WHERE cc.activo = 1 "
                "AND cc.fecha_vencimiento IS NOT NULL "
                "AND date(cc.fecha_vencimiento) >= date('now') "
                "AND date(cc.fecha_vencimiento) <= date('now', '+7 day') "
                "ORDER BY cc.fecha_vencimiento "
                "LIMIT 100"
            )
            proximos = cur.fetchall()
            for row in proximos:
                nombre = row["nombre"] or "-"
                codigo = row["codigo"] or "-"
                fecha = row["fecha_vencimiento"] or "-"
                estado = self._texto_estado_vencimiento(fecha)
                avisado_hoy = int(row["id_contrato"] or 0) in recordados_hoy
                texto = f"{fecha} | {nombre} | Espacio {codigo} | {estado}"
                if avisado_hoy:
                    texto += " | avisado hoy"
                item = QListWidgetItem(texto)
                item.setData(Qt.UserRole, dict(row))
                dias = self._dias_hasta(fecha)
                if dias is not None and dias <= 1:
                    item.setBackground(QColor("#ffedd5" if tema_claro else "#402018"))
                    item.setForeground(QColor("#9a3412" if tema_claro else "#fdba74"))
                elif dias is not None and dias <= 3:
                    item.setBackground(QColor("#fef3c7" if tema_claro else "#3b3217"))
                    item.setForeground(QColor("#92400e" if tema_claro else "#fde68a"))
                else:
                    item.setBackground(QColor("#eff6ff" if tema_claro else "#242a33"))
                    item.setForeground(QColor("#1d4ed8" if tema_claro else "#dbeafe"))
                if avisado_hoy:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setToolTip("Ya se envio un recordatorio hoy.")
                self.lista_proximos.addItem(item)
            self.label_proximos.setText(f"Total proximos: {len(proximos)}")
            if not proximos:
                item = QListWidgetItem("Sin vencimientos proximos.")
                item.setForeground(QColor("#64748b" if tema_claro else "#9ca3af"))
                self.lista_proximos.addItem(item)
        except sqlite3.Error:
            self.label_vencidos.setText("No disponible (falta tabla de contratos)")
            self.label_proximos.setText("No disponible (falta tabla de contratos)")
        finally:
            if conn:
                conn.close()
        self._actualizar_estado_acciones()


class HistorialDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Historial de cambios")
        self.setMinimumWidth(740)

        layout = QVBoxLayout(self)
        filtro = QHBoxLayout()
        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText("Buscar por usuario, accion o detalle")
        filtro.addWidget(self.input_buscar)
        layout.addLayout(filtro)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Fecha", "Usuario", "Accion", "Detalle"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        acciones = QHBoxLayout()
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_actualizar.setProperty("variant", "neutral")
        self.btn_cerrar.setProperty("variant", "neutral")
        self.input_buscar.setToolTip(
            "Filtra el historial por usuario, accion o detalle."
        )
        self.btn_actualizar.setToolTip(
            "Vuelve a consultar los ultimos cambios registrados en la auditoria."
        )
        self.btn_cerrar.setToolTip("Cierra esta ventana y vuelve al menu anterior.")
        acciones.addStretch(1)
        acciones.addWidget(self.btn_actualizar)
        acciones.addWidget(self.btn_cerrar)
        layout.addLayout(acciones)

        self.input_buscar.textChanged.connect(self._cargar)
        self.btn_actualizar.clicked.connect(self._cargar)
        self.btn_cerrar.clicked.connect(self.accept)
        self._cargar()

    def _cargar(self):
        texto = self.input_buscar.text().strip()
        self.table.setRowCount(0)
        conn = None
        cantidad = 0
        try:
            conn = get_connection()
            cur = conn.cursor()
            if texto:
                like = f"%{texto}%"
                cur.execute(
                    "SELECT fecha, usuario, accion, detalle FROM auditoria "
                    "WHERE usuario LIKE ? OR accion LIKE ? OR detalle LIKE ? "
                    "ORDER BY fecha DESC LIMIT 300",
                    (like, like, like),
                )
            else:
                cur.execute(
                    "SELECT fecha, usuario, accion, detalle FROM auditoria "
                    "ORDER BY fecha DESC LIMIT 300"
                )
            for row in cur.fetchall():
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(row["fecha"]))
                self.table.setItem(r, 1, QTableWidgetItem(row["usuario"] or ""))
                self.table.setItem(r, 2, QTableWidgetItem(row["accion"]))
                self.table.setItem(r, 3, QTableWidgetItem(row["detalle"] or ""))
                cantidad += 1
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()
        if cantidad == 0:
            self.table.insertRow(0)
            texto_vacio = (
                "No hay cambios que coincidan con la busqueda."
                if texto
                else "Todavia no hay movimientos en el historial de cambios."
            )
            item = QTableWidgetItem(texto_vacio)
            item.setFlags(Qt.NoItemFlags)
            self.table.setSpan(0, 0, 1, self.table.columnCount())
            self.table.setItem(0, 0, item)


class ReportesDialog(QDialog):
    def __init__(self, parent=None, tipo_inicial="Todos"):
        super().__init__(parent)
        self.setWindowTitle("Reportes")
        self.setMinimumWidth(720)
        self._tipo_inicial = (tipo_inicial or "Todos").strip()
        self._es_dueno = (getattr(parent, "rol", "") or "").strip().upper() == "DUENO"
        self._detalle_cache = []
        self._detalle_filtrado_cache = []

        layout = QVBoxLayout(self)

        filtro = QHBoxLayout()
        filtro.addWidget(QLabel("Desde"))
        self.input_desde = QDateEdit()
        self.input_desde.setCalendarPopup(True)
        self.input_desde.setDisplayFormat("dd/MM/yyyy")
        hoy = QDate.currentDate()
        inicio_mes = hoy.addDays(1 - hoy.day())
        self.input_desde.setDate(inicio_mes)
        filtro.addWidget(self.input_desde)
        filtro.addWidget(QLabel("Hasta"))
        self.input_hasta = QDateEdit()
        self.input_hasta.setCalendarPopup(True)
        self.input_hasta.setDisplayFormat("dd/MM/yyyy")
        self.input_hasta.setDate(hoy)
        filtro.addWidget(self.input_hasta)
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_actualizar.setProperty("variant", "neutral")
        self.btn_actualizar.setToolTip(
            "Vuelve a cargar los movimientos segun el periodo seleccionado."
        )
        filtro.addWidget(self.btn_actualizar)
        filtro.addStretch(1)
        layout.addLayout(filtro)

        resumen = QFormLayout()
        self.label_cochera_value = QLabel("$ 0.00")
        self.label_est_value = QLabel("$ 0.00")
        self.label_total_value = QLabel("$ 0.00")
        resumen.addRow("Ingresos cochera", self.label_cochera_value)
        resumen.addRow("Ingresos estacionamiento", self.label_est_value)
        resumen.addRow("Total", self.label_total_value)
        layout.addLayout(resumen)

        filtros = QHBoxLayout()
        filtros.addWidget(QLabel("Tipo"))
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(["Todos", "Cochera", "Estacionamiento"])
        self.combo_tipo.setToolTip("Filtra el historial por tipo de operacion.")
        filtros.addWidget(self.combo_tipo)
        filtros.addWidget(QLabel("Metodo"))
        self.combo_metodo = QComboBox()
        self.combo_metodo.addItems(["Todos", "Efectivo", "Transferencia", "Tarjeta", "Otro"])
        self.combo_metodo.setToolTip("Filtra el historial por metodo de cobro.")
        filtros.addWidget(self.combo_metodo)
        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText("Buscar cliente/patente/espacio")
        self.input_buscar.setToolTip(
            "Busca por cliente, patente o espacio dentro del historial filtrado."
        )
        filtros.addWidget(self.input_buscar)
        filtros.addStretch(1)
        layout.addLayout(filtros)

        self.table_historial = QTableWidget(0, 8)
        self.table_historial.setHorizontalHeaderLabels(
            [
                "Tipo",
                "Fecha",
                "Monto",
                "Metodo",
                "Cliente",
                "Patente",
                "Espacio",
                "ID",
            ]
        )
        self.table_historial.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_historial.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_historial.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_historial.setColumnHidden(7, True)
        layout.addWidget(self.table_historial)

        acciones = QHBoxLayout()
        self.btn_export_excel = QPushButton("Exportar Excel")
        self.btn_export_excel.setProperty("variant", "info")
        self.btn_export_excel.setToolTip(
            "Genera un Excel con el resumen y el detalle visible en Reportes."
        )
        acciones.addWidget(self.btn_export_excel)
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_eliminar.setProperty("variant", "danger")
        self.btn_eliminar.setVisible(self._es_dueno)
        acciones.addWidget(self.btn_eliminar)
        acciones.addStretch(1)
        layout.addLayout(acciones)

        self.btn_actualizar.clicked.connect(self._cargar)
        self.input_desde.dateChanged.connect(self._cargar)
        self.input_hasta.dateChanged.connect(self._cargar)
        self.btn_export_excel.clicked.connect(self._exportar_excel)
        self.btn_eliminar.clicked.connect(self._eliminar_reporte)
        self.combo_tipo.currentIndexChanged.connect(self._aplicar_filtros)
        self.combo_metodo.currentIndexChanged.connect(self._aplicar_filtros)
        self.input_buscar.textChanged.connect(self._aplicar_filtros)
        self.table_historial.itemSelectionChanged.connect(self._actualizar_estado_eliminar)
        _instalar_enter_navegacion(
            self,
            {
                self.input_desde: self.input_hasta,
                self.input_hasta: self.btn_actualizar,
                self.combo_tipo: self.combo_metodo,
                self.combo_metodo: self.input_buscar,
                self.input_buscar: self._cargar,
            },
        )
        idx_tipo = self.combo_tipo.findText(self._tipo_inicial)
        if idx_tipo >= 0:
            self.combo_tipo.setCurrentIndex(idx_tipo)
        self._cargar()

    def _fila_reporte_seleccionada(self):
        row = self.table_historial.currentRow()
        if row < 0 or row >= len(self._detalle_filtrado_cache):
            return None
        return self._detalle_filtrado_cache[row]

    def _periodo(self):
        desde = self.input_desde.date()
        hasta = self.input_hasta.date()
        if desde.toJulianDay() > hasta.toJulianDay():
            desde, hasta = hasta, desde
            self.input_desde.setDate(desde)
            self.input_hasta.setDate(hasta)
        return desde.toString("yyyy-MM-dd"), hasta.toString("yyyy-MM-dd")

    def _consultar_resumen(self, desde_key, hasta_key):
        return svc_consultar_resumen_reportes_rango(desde_key, hasta_key)

    def _consultar_detalle(self, desde_key, hasta_key):
        return svc_consultar_detalle_reportes_rango(desde_key, hasta_key)

    def _cargar(self):
        desde_key, hasta_key = self._periodo()
        self._detalle_cache = self._consultar_detalle(desde_key, hasta_key)
        self._aplicar_filtros()

    @staticmethod
    def _sum_monto(rows, tipo=None):
        total = 0.0
        for r in rows:
            if tipo and r.get("tipo") != tipo:
                continue
            try:
                total += float(r.get("monto") or 0.0)
            except (TypeError, ValueError):
                continue
        return total

    def _actualizar_resumen(self, detalle):
        cochera = self._sum_monto(detalle, "Cochera")
        estacionamiento = self._sum_monto(detalle, "Estacionamiento")
        total = cochera + estacionamiento
        self.label_cochera_value.setText(_fmt_money(cochera))
        self.label_est_value.setText(_fmt_money(estacionamiento))
        self.label_total_value.setText(_fmt_money(total))

    def _detalle_filtrado(self):
        detalle = list(self._detalle_cache or [])
        # Primero armamos el lote entero y despues lo achicamos, asi el resumen y la tabla salen del mismo corte.
        tipo = self.combo_tipo.currentText()
        if tipo != "Todos":
            detalle = [r for r in detalle if r["tipo"] == tipo]

        metodo = self.combo_metodo.currentText()
        if metodo != "Todos":
            detalle = [r for r in detalle if r["metodo"] == metodo]

        texto = self.input_buscar.text().strip().lower()
        if texto:
            detalle = [
                r
                for r in detalle
                if texto in (r["cliente"] or "").lower()
                or texto in (r["patente"] or "").lower()
                or texto in (r["espacio"] or "").lower()
            ]

        detalle.sort(key=lambda r: r["fecha_pago"] or "", reverse=True)
        return detalle

    def _aplicar_filtros(self):
        detalle = self._detalle_filtrado()
        self._detalle_filtrado_cache = list(detalle)
        self._actualizar_resumen(detalle)
        self.table_historial.setRowCount(0)
        for row in detalle:
            r = self.table_historial.rowCount()
            self.table_historial.insertRow(r)
            item_tipo = QTableWidgetItem(row["tipo"])
            item_tipo.setData(Qt.UserRole, dict(row))
            self.table_historial.setItem(r, 0, item_tipo)
            self.table_historial.setItem(r, 1, QTableWidgetItem(row["fecha_pago"]))
            self.table_historial.setItem(
                r, 2, QTableWidgetItem(_fmt_money(row["monto"]))
            )
            self.table_historial.setItem(r, 3, QTableWidgetItem(row["metodo"]))
            self.table_historial.setItem(r, 4, QTableWidgetItem(row["cliente"]))
            self.table_historial.setItem(r, 5, QTableWidgetItem(row["patente"]))
            self.table_historial.setItem(r, 6, QTableWidgetItem(row["espacio"]))
            id_val = row["contrato_id"] or row["movimiento_id"] or ""
            self.table_historial.setItem(r, 7, QTableWidgetItem(str(id_val)))
        if not detalle:
            self.table_historial.insertRow(0)
            texto_vacio = (
                "No hay movimientos en el periodo y filtros actuales."
                if self._detalle_cache
                else "Todavia no hay movimientos para mostrar en Reportes."
            )
            item = QTableWidgetItem(texto_vacio)
            item.setFlags(Qt.NoItemFlags)
            self.table_historial.setSpan(0, 0, 1, self.table_historial.columnCount())
            self.table_historial.setItem(0, 0, item)
        self._actualizar_estado_eliminar()

    def _actualizar_estado_eliminar(self):
        if not self._es_dueno:
            return
        row = self._fila_reporte_seleccionada()
        if not row:
            self.btn_eliminar.setEnabled(False)
            self.btn_eliminar.setToolTip("Selecciona una fila del historial.")
            return
        if (row.get("tipo") or "").strip() != "Estacionamiento":
            self.btn_eliminar.setEnabled(False)
            self.btn_eliminar.setToolTip(
                "Desde Reportes solo se pueden eliminar movimientos de Estacionamiento."
            )
            return
        self.btn_eliminar.setEnabled(True)
        self.btn_eliminar.setToolTip(
            "Elimina definitivamente esta operacion de estacionamiento del historial."
        )

    def _eliminar_reporte(self):
        if not self._es_dueno:
            QMessageBox.warning(
                self,
                "Reportes",
                "Solo DUENO puede eliminar registros desde Reportes.",
            )
            return

        row = self._fila_reporte_seleccionada()
        if not row:
            QMessageBox.warning(
                self,
                "Reportes",
                "Selecciona una fila del historial para eliminarla.",
            )
            return
        if (row.get("tipo") or "").strip() != "Estacionamiento":
            QMessageBox.warning(
                self,
                "Reportes",
                "Desde Reportes solo se pueden eliminar movimientos de Estacionamiento.",
            )
            return

        pago_id = row.get("pago_id")
        movimiento_id = row.get("movimiento_id")
        patente = (row.get("patente") or "").strip() or "-"
        espacio = (row.get("espacio") or "").strip() or "-"
        fecha = (row.get("fecha_pago") or "").strip() or "-"
        monto = float(row.get("monto") or 0.0)

        confirmar = QMessageBox.question(
            self,
            "Eliminar movimiento",
            "Esto eliminara definitivamente la operacion seleccionada de Estacionamiento.\n\n"
            f"Patente: {patente}\n"
            f"Espacio: {espacio}\n"
            f"Fecha: {fecha}\n"
            f"Monto: {_fmt_money(monto)}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmar != QMessageBox.Yes:
            return

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            id_vehiculo = None
            if movimiento_id:
                cur.execute(
                    "SELECT id_vehiculo FROM movimientos WHERE id_movimiento = ?",
                    (movimiento_id,),
                )
                row_mov = cur.fetchone()
                if row_mov:
                    id_vehiculo = row_mov["id_vehiculo"]

            if pago_id:
                cur.execute("DELETE FROM pagos WHERE id_pago = ?", (pago_id,))
            if movimiento_id:
                cur.execute("DELETE FROM movimientos WHERE id_movimiento = ?", (movimiento_id,))

            if id_vehiculo:
                cur.execute(
                    "SELECT id_cliente FROM vehiculos WHERE id_vehiculo = ?",
                    (id_vehiculo,),
                )
                row_veh = cur.fetchone()
                id_cliente = row_veh["id_cliente"] if row_veh else None
                if id_cliente is None:
                    cur.execute(
                        "SELECT COUNT(*) FROM movimientos WHERE id_vehiculo = ?",
                        (id_vehiculo,),
                    )
                    restantes = int(cur.fetchone()[0] or 0)
                    if restantes <= 0:
                        cur.execute(
                            "DELETE FROM vehiculos WHERE id_vehiculo = ?",
                            (id_vehiculo,),
                        )

            conn.commit()
            _auditar(
                self,
                "Movimiento eliminado desde reportes",
                f"Estacionamiento - Movimiento {movimiento_id or '-'} - Pago {pago_id or '-'} - Patente {patente} - Espacio {espacio}",
            )
            QMessageBox.information(
                self,
                "Reportes",
                "El movimiento de estacionamiento se elimino correctamente.",
            )
            self._cargar()
        except sqlite3.Error:
            QMessageBox.warning(
                self,
                "Reportes",
                "No se pudo eliminar el movimiento seleccionado.",
            )
        finally:
            if conn:
                conn.close()

    def _exportar_excel(self):
        try:
            import xlsxwriter
        except ImportError:
            QMessageBox.warning(
                self,
                "Excel",
                "Para exportar a Excel necesitas instalar xlsxwriter.",
            )
            return

        desde_key, hasta_key = self._periodo()
        nombre_default = f"reporte_{desde_key}_a_{hasta_key}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar reporte Excel",
            str(_reportes_dir() / nombre_default),
            "Excel (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        detalle = self._detalle_filtrado()
        if not detalle:
            QMessageBox.information(
                self,
                "Reporte",
                "No hay movimientos en el periodo y filtros actuales.\n"
                "Cambia las fechas o filtros antes de exportar.",
            )
            return
        cochera = self._sum_monto(detalle, "Cochera")
        estacionamiento = self._sum_monto(detalle, "Estacionamiento")
        total = cochera + estacionamiento
        cantidad_operaciones = len(detalle)
        ticket_promedio = (total / cantidad_operaciones) if cantidad_operaciones else 0.0

        resumen_diario = {}
        totales_metodo = {}
        for row in detalle:
            monto = float(row.get("monto") or 0.0)
            metodo = (row.get("metodo") or "").strip() or "Sin metodo"
            totales_metodo.setdefault(metodo, {"operaciones": 0, "total": 0.0})
            totales_metodo[metodo]["operaciones"] += 1
            totales_metodo[metodo]["total"] += monto

            dt_pago = _parse_fecha_db(row.get("fecha_pago"))
            fecha_key = (
                dt_pago.strftime("%Y-%m-%d")
                if dt_pago
                else (str(row.get("fecha_pago") or "").strip()[:10] or "Sin fecha")
            )
            entry = resumen_diario.setdefault(
                fecha_key,
                {"cochera": 0.0, "estacionamiento": 0.0, "total": 0.0, "operaciones": 0},
            )
            if row.get("tipo") == "Cochera":
                entry["cochera"] += monto
            elif row.get("tipo") == "Estacionamiento":
                entry["estacionamiento"] += monto
            entry["total"] += monto
            entry["operaciones"] += 1

        workbook = None
        try:
            workbook = xlsxwriter.Workbook(path)

            fmt_titulo = workbook.add_format(
                {
                    "bold": True,
                    "font_size": 14,
                    "bg_color": "#E2E8F0",
                    "border": 1,
                    "align": "center",
                    "valign": "vcenter",
                }
            )
            fmt_subtitulo = workbook.add_format({"bold": True, "font_size": 10, "border": 1})
            fmt_label = workbook.add_format({"bold": True, "bg_color": "#F8FAFC", "border": 1})
            fmt_celda = workbook.add_format({"border": 1})
            fmt_celda_center = workbook.add_format({"border": 1, "align": "center"})
            fmt_header = workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": "#2563EB",
                    "border": 1,
                    "align": "center",
                    "valign": "vcenter",
                }
            )
            fmt_moneda = workbook.add_format({"num_format": "$ #,##0.00", "border": 1})
            fmt_texto = workbook.add_format({"border": 1})
            fmt_fecha = workbook.add_format({"num_format": "dd/mm/yyyy", "border": 1})
            fmt_fecha_hora = workbook.add_format({"num_format": "dd/mm/yyyy hh:mm:ss", "border": 1})
            fmt_pct = workbook.add_format({"num_format": "0.00%", "border": 1, "align": "center"})

            ws_resumen = workbook.add_worksheet("Resumen")
            ws_resumen.set_column("A:A", 30)
            ws_resumen.set_column("B:B", 28)
            ws_resumen.set_column("C:C", 18)
            ws_resumen.merge_range("A1:C1", "Reporte de ingresos", fmt_titulo)
            ws_resumen.write("A3", "Periodo desde", fmt_label)
            ws_resumen.write("B3", desde_key, fmt_celda)
            ws_resumen.write("A4", "Periodo hasta", fmt_label)
            ws_resumen.write("B4", hasta_key, fmt_celda)
            ws_resumen.write("A6", "Filtro tipo", fmt_label)
            ws_resumen.write("B6", self.combo_tipo.currentText(), fmt_celda)
            ws_resumen.write("A7", "Filtro metodo", fmt_label)
            ws_resumen.write("B7", self.combo_metodo.currentText(), fmt_celda)
            ws_resumen.write("A8", "Buscar", fmt_label)
            ws_resumen.write("B8", self.input_buscar.text().strip(), fmt_celda)
            ws_resumen.write("A9", "Exportado", fmt_label)
            ws_resumen.write("B9", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), fmt_celda)
            ws_resumen.write("A11", "Ingresos cochera", fmt_label)
            ws_resumen.write_number("B11", cochera, fmt_moneda)
            ws_resumen.write("A12", "Ingresos estacionamiento", fmt_label)
            ws_resumen.write_number("B12", estacionamiento, fmt_moneda)
            ws_resumen.write("A13", "Total", fmt_label)
            ws_resumen.write_number("B13", total, fmt_moneda)
            ws_resumen.write("A14", "Operaciones", fmt_label)
            ws_resumen.write_number("B14", cantidad_operaciones, fmt_celda_center)
            ws_resumen.write("A15", "Ticket promedio", fmt_label)
            ws_resumen.write_number("B15", ticket_promedio, fmt_moneda)
            ws_resumen.write("A16", "Dias con movimientos", fmt_label)
            ws_resumen.write_number("B16", len(resumen_diario), fmt_celda_center)

            ws_metodos = workbook.add_worksheet("Por metodo")
            ws_metodos.set_column("A:A", 24)
            ws_metodos.set_column("B:B", 14)
            ws_metodos.set_column("C:C", 18)
            ws_metodos.set_column("D:D", 18)
            ws_metodos.set_column("E:E", 14)
            ws_metodos.write_row(
                0,
                0,
                ["Metodo", "Operaciones", "Total", "Ticket promedio", "% del total"],
                fmt_header,
            )
            fila_metodo = 1
            for metodo, data in sorted(
                totales_metodo.items(),
                key=lambda it: (it[1]["total"], it[1]["operaciones"]),
                reverse=True,
            ):
                ops = int(data["operaciones"] or 0)
                total_metodo = float(data["total"] or 0.0)
                ws_metodos.write(fila_metodo, 0, metodo, fmt_texto)
                ws_metodos.write_number(fila_metodo, 1, ops, fmt_celda_center)
                ws_metodos.write_number(fila_metodo, 2, total_metodo, fmt_moneda)
                ws_metodos.write_number(
                    fila_metodo,
                    3,
                    (total_metodo / ops) if ops else 0.0,
                    fmt_moneda,
                )
                ws_metodos.write_number(
                    fila_metodo,
                    4,
                    (total_metodo / total) if total else 0.0,
                    fmt_pct,
                )
                fila_metodo += 1
            ws_metodos.write(fila_metodo, 0, "Total", fmt_subtitulo)
            ws_metodos.write_number(fila_metodo, 1, cantidad_operaciones, fmt_celda_center)
            ws_metodos.write_number(fila_metodo, 2, total, fmt_moneda)
            ws_metodos.autofilter(0, 0, max(1, fila_metodo), 4)
            ws_metodos.freeze_panes(1, 0)

            ws_diario = workbook.add_worksheet("Resumen diario")
            ws_diario.set_column("A:A", 14)
            ws_diario.set_column("B:B", 14)
            ws_diario.set_column("C:E", 18)
            ws_diario.write_row(
                0,
                0,
                ["Fecha", "Operaciones", "Cochera", "Estacionamiento", "Total"],
                fmt_header,
            )
            fila_dia = 1
            for dia in sorted(resumen_diario.keys()):
                data = resumen_diario[dia]
                dt_dia = _parse_fecha_db(f"{dia} 00:00:00")
                if dt_dia:
                    ws_diario.write_datetime(fila_dia, 0, dt_dia, fmt_fecha)
                else:
                    ws_diario.write(fila_dia, 0, dia, fmt_texto)
                ws_diario.write_number(fila_dia, 1, int(data["operaciones"] or 0), fmt_celda_center)
                ws_diario.write_number(fila_dia, 2, float(data["cochera"] or 0.0), fmt_moneda)
                ws_diario.write_number(fila_dia, 3, float(data["estacionamiento"] or 0.0), fmt_moneda)
                ws_diario.write_number(fila_dia, 4, float(data["total"] or 0.0), fmt_moneda)
                fila_dia += 1
            ws_diario.write(fila_dia, 0, "Total", fmt_subtitulo)
            ws_diario.write_number(fila_dia, 1, cantidad_operaciones, fmt_celda_center)
            ws_diario.write_number(fila_dia, 2, cochera, fmt_moneda)
            ws_diario.write_number(fila_dia, 3, estacionamiento, fmt_moneda)
            ws_diario.write_number(fila_dia, 4, total, fmt_moneda)
            ws_diario.autofilter(0, 0, max(1, fila_dia), 4)
            ws_diario.freeze_panes(1, 0)

            ws_historial = workbook.add_worksheet("Historial reporte")
            headers_historial = []
            for col in range(self.table_historial.columnCount()):
                item_hdr = self.table_historial.horizontalHeaderItem(col)
                headers_historial.append(item_hdr.text() if item_hdr else f"Columna {col + 1}")
            ws_historial.set_row(0, 22)
            ws_historial.set_column("A:A", 18)
            ws_historial.set_column("B:B", 22)
            ws_historial.set_column("C:C", 16)
            ws_historial.set_column("D:D", 16)
            ws_historial.set_column("E:E", 18)
            ws_historial.set_column("F:F", 28)
            ws_historial.set_column("G:G", 14)
            ws_historial.set_column("H:H", 12)
            ws_historial.set_column("I:I", 14)
            ws_historial.write_row(0, 0, headers_historial, fmt_header)
            for r in range(self.table_historial.rowCount()):
                for c in range(self.table_historial.columnCount()):
                    item = self.table_historial.item(r, c)
                    ws_historial.write(r + 1, c, item.text() if item else "", fmt_texto)
            ultima_hist = max(1, self.table_historial.rowCount())
            ws_historial.autofilter(0, 0, ultima_hist, len(headers_historial) - 1)
            ws_historial.freeze_panes(1, 0)

            ws_detalle = workbook.add_worksheet("Detalle")
            headers_detalle = [
                "Tipo",
                "Fecha pago",
                "Monto",
                "Metodo",
                "Usuario",
                "Cliente",
                "Patente",
                "Espacio",
                "Vehiculo",
            ]
            ws_detalle.set_row(0, 22)
            ws_detalle.set_column("A:A", 18)
            ws_detalle.set_column("B:B", 22)
            ws_detalle.set_column("C:C", 16)
            ws_detalle.set_column("D:D", 16)
            ws_detalle.set_column("E:E", 18)
            ws_detalle.set_column("F:F", 28)
            ws_detalle.set_column("G:G", 14)
            ws_detalle.set_column("H:H", 12)
            ws_detalle.set_column("I:I", 14)
            ws_detalle.write_row(0, 0, headers_detalle, fmt_header)
            for idx, row in enumerate(detalle, start=1):
                dt_pago = _parse_fecha_db(row.get("fecha_pago"))
                ws_detalle.write(idx, 0, row.get("tipo") or "", fmt_texto)
                if dt_pago is not None:
                    ws_detalle.write_datetime(idx, 1, dt_pago, fmt_fecha_hora)
                else:
                    ws_detalle.write(idx, 1, row.get("fecha_pago") or "", fmt_texto)
                ws_detalle.write_number(idx, 2, float(row.get("monto") or 0.0), fmt_moneda)
                ws_detalle.write(idx, 3, row.get("metodo") or "", fmt_texto)
                ws_detalle.write(idx, 4, row.get("usuario") or "", fmt_texto)
                ws_detalle.write(idx, 5, row.get("cliente") or "", fmt_texto)
                ws_detalle.write(idx, 6, row.get("patente") or "", fmt_texto)
                ws_detalle.write(idx, 7, row.get("espacio") or "", fmt_texto)
                vehiculo_txt = (
                    "Mensual"
                    if row.get("tipo") == "Cochera"
                    else _texto_tipo_vehiculo(row.get("tipo_vehiculo"))
                )
                ws_detalle.write(idx, 8, vehiculo_txt, fmt_texto)

            ultima_det = max(1, len(detalle))
            ws_detalle.autofilter(0, 0, ultima_det, len(headers_detalle) - 1)
            ws_detalle.freeze_panes(1, 0)
            ws_detalle.write(ultima_det + 2, 1, "Total", fmt_subtitulo)
            ws_detalle.write_number(ultima_det + 2, 2, total, fmt_moneda)

            workbook.close()
            box = QMessageBox(self)
            box.setWindowTitle("Reporte")
            box.setIcon(QMessageBox.Information)
            box.setText(
                "Excel exportado correctamente.\n"
                "Si quieres revisarlo ahora, puedes abrirlo desde aqui."
            )
            btn_abrir = box.addButton("Abrir Excel", QMessageBox.ActionRole)
            btn_abrir.clicked.connect(
                lambda: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(Path(path).resolve()))
                )
            )
            box.addButton(QMessageBox.Ok)
            box.exec()
        except Exception as e:
            try:
                if workbook is not None:
                    workbook.close()
            except Exception:
                pass
            if isinstance(e, PermissionError):
                _mostrar_error(
                    self,
                    "Error",
                    "No se pudo guardar el Excel.\n"
                    "Cierra el archivo si ya estaba abierto y vuelve a intentarlo.",
                )
            else:
                _mostrar_error(
                    self,
                    "Error",
                    f"No se pudo guardar el Excel.\n{e}",
                )


class CajaDiariaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cierre de caja diario")
        self.setMinimumWidth(620)
        self._total_esperado_actual = 0.0
        self._snapshot_cierre = None
        self._metodo_rows = []

        layout = QVBoxLayout(self)

        filtros = QHBoxLayout()
        filtros.addWidget(QLabel("Fecha"))
        self.input_fecha = QDateEdit()
        self.input_fecha.setCalendarPopup(True)
        self.input_fecha.setDisplayFormat("dd/MM/yyyy")
        self.input_fecha.setDate(QDate.currentDate())
        filtros.addWidget(self.input_fecha)
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_actualizar.setProperty("variant", "neutral")
        self.btn_actualizar.setToolTip(
            "Vuelve a calcular el resumen y el arqueo del dia seleccionado."
        )
        filtros.addWidget(self.btn_actualizar)
        filtros.addStretch(1)
        layout.addLayout(filtros)

        resumen = QFormLayout()
        self.label_cochera = QLabel("$ 0.00")
        self.label_est = QLabel("$ 0.00")
        self.label_total = QLabel("$ 0.00")
        self.label_total_real = QLabel("$ 0.00")
        resumen.addRow("Cochera", self.label_cochera)
        resumen.addRow("Estacionamiento", self.label_est)
        resumen.addRow("Total esperado del dia", self.label_total)
        resumen.addRow("Total real contado", self.label_total_real)
        self.label_estado_cierre = QLabel("Cierre no guardado")
        resumen.addRow("Estado cierre", self.label_estado_cierre)
        layout.addLayout(resumen)

        arqueo = QFormLayout()
        self.input_total_contado = QDoubleSpinBox()
        self.input_total_contado.setDecimals(2)
        self.input_total_contado.setRange(0.0, 999999999.0)
        self.input_total_contado.setSingleStep(100.0)
        self.input_total_contado.setReadOnly(True)
        self.input_total_contado.setEnabled(False)
        _configurar_spinbox_numerico(self.input_total_contado)
        self.label_diferencia = QLabel("$ 0.00")
        self.input_observacion = QLineEdit()
        self.input_observacion.setPlaceholderText(
            "Si hay diferencia, escribe el motivo"
        )
        arqueo.addRow("Total contado", self.input_total_contado)
        arqueo.addRow("Diferencia", self.label_diferencia)
        arqueo.addRow("Observacion", self.input_observacion)
        layout.addLayout(arqueo)

        acciones_cierre = QHBoxLayout()
        self.btn_guardar_cierre = QPushButton("Guardar cierre")
        self.btn_reabrir_cierre = QPushButton("Reabrir cierre")
        self.btn_limpiar_cierre = QPushButton("Limpiar")
        self.btn_guardar_cierre.setProperty("variant", "success")
        self.btn_reabrir_cierre.setProperty("variant", "danger")
        self.btn_limpiar_cierre.setProperty("variant", "warning")
        self.btn_guardar_cierre.setToolTip(
            "Guarda el cierre del dia con los importes contados por metodo."
        )
        self.btn_reabrir_cierre.setToolTip(
            "Vuelve a abrir un cierre ya guardado para corregirlo."
        )
        self.btn_limpiar_cierre.setToolTip(
            "Limpia los importes contados y la observacion cargada en este cierre."
        )
        acciones_cierre.addWidget(self.btn_guardar_cierre)
        acciones_cierre.addWidget(self.btn_reabrir_cierre)
        acciones_cierre.addWidget(self.btn_limpiar_cierre)
        acciones_cierre.addStretch(1)
        layout.addLayout(acciones_cierre)

        self.table_metodos = QTableWidget(0, 7)
        self.table_metodos.setHorizontalHeaderLabels(
            [
                "Metodo",
                "Cochera",
                "Estacionamiento",
                "Esperado",
                "Contado",
                "Diferencia",
                "Operaciones",
            ]
        )
        self.table_metodos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_metodos.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_metodos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table_metodos.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setStretchLastSection(False)
        layout.addWidget(self.table_metodos)

        self.btn_actualizar.clicked.connect(self._cargar)
        self.input_fecha.dateChanged.connect(self._cargar)
        self.btn_guardar_cierre.clicked.connect(self._guardar_cierre)
        self.btn_reabrir_cierre.clicked.connect(self._reabrir_cierre)
        self.btn_limpiar_cierre.clicked.connect(self._limpiar_form_cierre)
        self.input_observacion.textChanged.connect(self._actualizar_estado_observacion)
        _instalar_enter_navegacion(
            self,
            {
                self.input_fecha: self.btn_actualizar,
                self.input_observacion: self._guardar_cierre,
            },
        )
        self._cargar()

    def _cargar(self):
        fecha_key = self.input_fecha.date().toString("yyyy-MM-dd")
        cochera, est, total = svc_consultar_totales_caja(fecha_key)
        detalle = svc_consultar_detalle_metodo_caja(fecha_key)
        cierre = svc_obtener_cierre_caja(fecha_key)
        cierre_metodos = svc_obtener_cierre_caja_metodos(fecha_key)

        self.label_cochera.setText(_fmt_money(cochera))
        self.label_est.setText(_fmt_money(est))
        self.label_total.setText(_fmt_money(total))
        self._total_esperado_actual = float(total or 0.0)

        self.table_metodos.setRowCount(0)
        self._metodo_rows = []
        metodos_cargados = set()
        for row in detalle:
            metodo = (row["metodo"] or "").strip() or "Sin metodo"
            esperado = float(row["total"] or 0.0)
            if metodo in cierre_metodos:
                contado = float(cierre_metodos[metodo].get("total_contado") or 0.0)
            else:
                contado = esperado
            self._agregar_fila_metodo(
                metodo=metodo,
                cochera=float(row["cochera"] or 0.0),
                estacionamiento=float(row["estacionamiento"] or 0.0),
                esperado=esperado,
                contado=contado,
                operaciones=int(row["operaciones"] or 0),
            )
            metodos_cargados.add(metodo)

        for metodo, data in cierre_metodos.items():
            if metodo in metodos_cargados:
                continue
            self._agregar_fila_metodo(
                metodo=metodo,
                cochera=0.0,
                estacionamiento=0.0,
                esperado=float(data.get("total_esperado") or 0.0),
                contado=float(data.get("total_contado") or 0.0),
                operaciones=0,
            )
            metodos_cargados.add(metodo)

        for metodo_base in ("Efectivo", "Tarjeta", "Transferencia"):
            if metodo_base in metodos_cargados:
                continue
            self._agregar_fila_metodo(
                metodo=metodo_base,
                cochera=0.0,
                estacionamiento=0.0,
                esperado=0.0,
                contado=0.0,
                operaciones=0,
            )
            metodos_cargados.add(metodo_base)

        if cierre and not self._metodo_rows:
            self._agregar_fila_metodo(
                metodo="No desglosado",
                cochera=0.0,
                estacionamiento=0.0,
                esperado=float(cierre.get("total_esperado") or 0.0),
                contado=float(cierre.get("total_contado") or 0.0),
                operaciones=0,
            )

        if cierre and not cierre_metodos and self._metodo_rows and metodos_cargados:
            diferencia_legacy = float(cierre["total_contado"] or 0.0) - float(
                self._total_esperado_actual or 0.0
            )
            if abs(diferencia_legacy) > 0.009:
                primer = self._metodo_rows[0]["input_contado"]
                primer.setValue(float(primer.value()) + diferencia_legacy)

        if cierre:
            self.input_observacion.setText(cierre["observacion"] or "")
            usuario = cierre["usuario"] or "sistema"
            fecha_cierre = cierre["fecha_cierre"] or ""
            self.label_estado_cierre.setText(
                f"Guardado por {usuario} ({fecha_cierre})"
            )
        else:
            self.input_observacion.clear()
            self.label_estado_cierre.setText("Cierre no guardado")
        self.btn_reabrir_cierre.setEnabled(bool(cierre) and self._es_dueno())
        if not self._es_dueno():
            self.btn_reabrir_cierre.setToolTip("Solo DUENO puede reabrir el cierre.")
        elif not cierre:
            self.btn_reabrir_cierre.setToolTip("No hay cierre guardado para esta fecha.")
        else:
            self.btn_reabrir_cierre.setToolTip("")
        self._actualizar_diferencia()
        self._actualizar_snapshot_cierre()

    def _es_dueno(self):
        return (_rol_desde_widget(self) or "").strip().upper() == "DUENO"

    def _texto_diferencia(self, diferencia):
        if diferencia > 0.009:
            return f"$ +{_fmt_numero_local(diferencia)} (sobrante)"
        if diferencia < -0.009:
            return f"$ -{_fmt_numero_local(abs(diferencia))} (faltante)"
        return f"{_fmt_money(0)} (cuadra)"

    def _hay_diferencia(self, diferencia):
        return abs(float(diferencia or 0.0)) > 0.009

    def _agregar_fila_metodo(
        self,
        metodo,
        cochera,
        estacionamiento,
        esperado,
        contado,
        operaciones,
    ):
        r = self.table_metodos.rowCount()
        self.table_metodos.insertRow(r)
        self.table_metodos.setItem(r, 0, QTableWidgetItem(str(metodo)))
        self.table_metodos.setItem(r, 1, QTableWidgetItem(_fmt_money(cochera)))
        self.table_metodos.setItem(r, 2, QTableWidgetItem(_fmt_money(estacionamiento)))
        self.table_metodos.setItem(r, 3, QTableWidgetItem(_fmt_money(esperado)))

        input_contado = QDoubleSpinBox()
        input_contado.setDecimals(2)
        input_contado.setRange(0.0, 999999999.0)
        input_contado.setSingleStep(100.0)
        input_contado.setValue(float(contado or 0.0))
        _configurar_spinbox_numerico(input_contado)
        input_contado.valueChanged.connect(self._actualizar_diferencia)
        self.table_metodos.setCellWidget(r, 4, input_contado)

        item_dif = QTableWidgetItem(_fmt_money(0))
        self.table_metodos.setItem(r, 5, item_dif)
        self.table_metodos.setItem(r, 6, QTableWidgetItem(str(int(operaciones or 0))))
        self._metodo_rows.append(
            {
                "metodo": str(metodo),
                "esperado": float(esperado or 0.0),
                "input_contado": input_contado,
                "item_diferencia": item_dif,
            }
        )

    def _total_contado_metodos(self):
        total = 0.0
        for row in self._metodo_rows:
            total += float(row["input_contado"].value() or 0.0)
        return total

    def _detalle_contado_metodos(self):
        detalle = []
        for row in self._metodo_rows:
            esperado = float(row["esperado"] or 0.0)
            contado = float(row["input_contado"].value() or 0.0)
            detalle.append(
                {
                    "metodo": row["metodo"],
                    "total_esperado": esperado,
                    "total_contado": contado,
                    "diferencia": contado - esperado,
                }
            )
        return detalle

    def _actualizar_estado_observacion(self):
        diferencia = self._total_contado_metodos() - float(self._total_esperado_actual or 0.0)
        requiere_motivo = self._hay_diferencia(diferencia)
        observacion = self.input_observacion.text().strip()
        if requiere_motivo and not observacion:
            self.input_observacion.setStyleSheet("border: 1px solid #f87171;")
            self.input_observacion.setToolTip("Obligatoria cuando hay diferencia de caja.")
        else:
            self.input_observacion.setStyleSheet("")
            self.input_observacion.setToolTip("")

    def _actualizar_diferencia(self):
        for row in self._metodo_rows:
            esperado = float(row["esperado"] or 0.0)
            contado_metodo = float(row["input_contado"].value() or 0.0)
            diferencia_metodo = contado_metodo - esperado
            row["item_diferencia"].setText(self._texto_diferencia(diferencia_metodo))
        contado = self._total_contado_metodos()
        self.input_total_contado.setValue(contado)
        diferencia = contado - float(self._total_esperado_actual or 0.0)
        self.label_total_real.setText(_fmt_money(contado))
        self.label_diferencia.setText(self._texto_diferencia(diferencia))
        tema_claro = _tema_claro_activo()
        if diferencia > 0.009:
            color = "#15803d" if tema_claro else "#34d399"
        elif diferencia < -0.009:
            color = "#b91c1c" if tema_claro else "#f87171"
        else:
            color = "#475569" if tema_claro else "#a7f3d0"
        self.label_diferencia.setStyleSheet(f"color: {color}; font-weight: 600;")
        self._actualizar_estado_observacion()

    def _snapshot_form_cierre(self):
        metodos = tuple(
            sorted(
                (
                    row["metodo"],
                    round(float(row["input_contado"].value() or 0.0), 2),
                )
                for row in self._metodo_rows
            )
        )
        return (
            self.input_fecha.date().toString("yyyy-MM-dd"),
            round(float(self._total_contado_metodos()), 2),
            self.input_observacion.text().strip(),
            metodos,
        )

    def _actualizar_snapshot_cierre(self):
        self._snapshot_cierre = self._snapshot_form_cierre()

    def _hay_cambios_sin_guardar(self):
        base = getattr(self, "_snapshot_cierre", None)
        if base is None:
            return False
        return self._snapshot_form_cierre() != base

    def _guardar_cierre(self, mostrar_mensaje=True):
        if not _antirebote_iniciar(self, "caja_guardar_cierre"):
            return False
        try:
            fecha_key = self.input_fecha.date().toString("yyyy-MM-dd")
            cierre_existente = svc_obtener_cierre_caja(fecha_key)
            if cierre_existente and not self._hay_cambios_sin_guardar():
                if mostrar_mensaje:
                    QMessageBox.information(
                        self,
                        "Caja",
                        "No hay cambios nuevos para guardar en este cierre.",
                    )
                return False
            cochera, est, total = svc_consultar_totales_caja(fecha_key)
            self.label_cochera.setText(_fmt_money(cochera))
            self.label_est.setText(_fmt_money(est))
            self.label_total.setText(_fmt_money(total))
            self._total_esperado_actual = float(total or 0.0)

            total_contado = float(self._total_contado_metodos())
            diferencia = total_contado - self._total_esperado_actual
            observacion = self.input_observacion.text().strip()
            if self._hay_diferencia(diferencia) and not observacion:
                QMessageBox.warning(
                    self,
                    "Caja",
                    "Hay diferencia entre esperado y contado. Ingresa el motivo en Observacion.",
                )
                self.input_observacion.setFocus()
                self._actualizar_estado_observacion()
                return False
            usuario = _usuario_desde_widget(self)

            ok = svc_guardar_cierre_caja(
                fecha_key=fecha_key,
                total_esperado=self._total_esperado_actual,
                total_contado=total_contado,
                diferencia=diferencia,
                observacion=observacion,
                usuario=usuario,
                detalle_metodos=self._detalle_contado_metodos(),
            )
            if not ok:
                _mostrar_error(self, "Error", "No se pudo guardar el cierre de caja.")
                return False

            _auditar(
                self,
                "Cierre de caja guardado",
                f"{fecha_key} - esperado={self._total_esperado_actual:.2f} "
                f"contado={total_contado:.2f} diferencia={diferencia:.2f}",
            )
            self.label_estado_cierre.setText(
                f"Guardado por {usuario} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
            )
            self._actualizar_diferencia()
            self._actualizar_snapshot_cierre()
            if mostrar_mensaje:
                QMessageBox.information(self, "Caja", "Cierre de caja guardado.")
            return True
        finally:
            _antirebote_finalizar(self, "caja_guardar_cierre", cooldown_ms=700)

    def _limpiar_form_cierre(self):
        if not self._hay_cambios_sin_guardar():
            QMessageBox.information(
                self,
                "Caja",
                "No hay cambios cargados para limpiar en este cierre.",
            )
            return
        for row in self._metodo_rows:
            row["input_contado"].setValue(float(row["esperado"] or 0.0))
        self.input_observacion.clear()
        self._actualizar_diferencia()

    def _reabrir_cierre(self):
        if not self._es_dueno():
            QMessageBox.warning(
                self,
                "Caja",
                "Solo un usuario DUENO puede reabrir un cierre.",
            )
            return

        fecha_key = self.input_fecha.date().toString("yyyy-MM-dd")
        cierre = svc_obtener_cierre_caja(fecha_key)
        if not cierre:
            QMessageBox.information(
                self,
                "Caja",
                "No hay cierre guardado para esa fecha.",
            )
            return

        motivo, ok = QInputDialog.getText(
            self,
            "Reabrir cierre",
            "Motivo de la reapertura:",
            QLineEdit.Normal,
            "",
        )
        if not ok:
            return
        motivo = (motivo or "").strip()
        if not motivo:
            QMessageBox.warning(
                self,
                "Caja",
                "Debes indicar un motivo para reabrir el cierre.",
            )
            return

        respuesta = QMessageBox.question(
            self,
            "Confirmar reapertura",
            f"Se eliminara el cierre de caja del dia {fecha_key}.\nContinuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if respuesta != QMessageBox.Yes:
            return

        if not svc_eliminar_cierre_caja(fecha_key):
            _mostrar_error(self, "Error", "No se pudo reabrir el cierre de caja.")
            return

        _auditar(
            self,
            "Cierre de caja reabierto",
            (
                f"{fecha_key} - motivo={motivo} - "
                f"esperado={float(cierre.get('total_esperado') or 0.0):.2f} "
                f"contado={float(cierre.get('total_contado') or 0.0):.2f} "
                f"diferencia={float(cierre.get('diferencia') or 0.0):.2f}"
            ),
        )
        QMessageBox.information(
            self,
            "Caja",
            "Cierre reabierto. Ahora puedes volver a editar y guardar.",
        )
        self._cargar()

    def closeEvent(self, event):
        if not self._hay_cambios_sin_guardar():
            event.accept()
            return
        respuesta = _confirmar_guardado_pendiente(
            self,
            "Hay cambios en el cierre de caja.\nQuieres guardarlos antes de salir?",
        )
        if respuesta == QMessageBox.Cancel:
            event.ignore()
            return
        if respuesta == QMessageBox.No:
            event.accept()
            return
        if self._guardar_cierre(mostrar_mensaje=False):
            event.accept()
        else:
            event.ignore()


class BackupsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Respaldos")
        self.setMinimumWidth(720)
        self.setMinimumHeight(420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Respaldos disponibles (base de datos)"))

        self.lista = QListWidget()
        layout.addWidget(self.lista)

        acciones = QHBoxLayout()
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_crear = QPushButton("Crear respaldo")
        self.btn_restaurar = QPushButton("Restaurar")
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_actualizar.setProperty("variant", "neutral")
        self.btn_crear.setProperty("variant", "info")
        self.btn_restaurar.setProperty("variant", "warning")
        self.btn_eliminar.setProperty("variant", "danger")
        self.btn_cerrar.setProperty("variant", "neutral")
        self.btn_actualizar.setToolTip(
            "Vuelve a cargar la lista de respaldos disponibles."
        )
        self.btn_crear.setToolTip(
            "Genera un respaldo nuevo de la base de datos actual."
        )
        self.btn_cerrar.setToolTip("Cierra esta ventana de respaldos.")
        acciones.addWidget(self.btn_actualizar)
        acciones.addWidget(self.btn_crear)
        acciones.addWidget(self.btn_restaurar)
        acciones.addWidget(self.btn_eliminar)
        acciones.addStretch(1)
        acciones.addWidget(self.btn_cerrar)
        layout.addLayout(acciones)

        self.btn_actualizar.clicked.connect(self._cargar)
        self.btn_crear.clicked.connect(self._crear_backup)
        self.btn_restaurar.clicked.connect(self._restaurar_backup)
        self.btn_eliminar.clicked.connect(self._eliminar_backup)
        self.btn_cerrar.clicked.connect(self.reject)
        self.lista.itemSelectionChanged.connect(self._actualizar_estado_acciones)

        self._cargar()

    @staticmethod
    def _fmt_item(path: Path):
        try:
            ts = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M:%S")
        except OSError:
            ts = "-"
        return f"{ts}  |  {path.name}"

    def _selected_path(self):
        item = self.lista.currentItem()
        if not item:
            return None
        path = item.data(Qt.UserRole)
        if not path:
            return None
        try:
            return Path(str(path))
        except Exception:
            return None

    def _cargar(self):
        self.lista.clear()
        paths = list(svc_listar_backups_db(limit=200))
        if not paths:
            item = QListWidgetItem("No hay respaldos disponibles.")
            item.setFlags(Qt.NoItemFlags)
            self.lista.addItem(item)
            self._actualizar_estado_acciones()
            return
        for path in paths:
            item = QListWidgetItem(self._fmt_item(path))
            item.setData(Qt.UserRole, str(path))
            self.lista.addItem(item)
        self._actualizar_estado_acciones()

    def _actualizar_estado_acciones(self):
        path = self._selected_path()
        tiene_seleccion = path is not None
        self.btn_restaurar.setEnabled(tiene_seleccion)
        self.btn_eliminar.setEnabled(tiene_seleccion)
        if tiene_seleccion:
            self.btn_restaurar.setToolTip(
                f"Restaura el respaldo seleccionado: {path.name}"
            )
            self.btn_eliminar.setToolTip(
                f"Elimina el respaldo seleccionado: {path.name}"
            )
        else:
            self.btn_restaurar.setToolTip(
                "Selecciona un respaldo de la lista para restaurarlo."
            )
            self.btn_eliminar.setToolTip(
                "Selecciona un respaldo de la lista para eliminarlo."
            )

    def _crear_backup(self):
        if not _antirebote_iniciar(self, "backups_crear"):
            return
        try:
            try:
                path = svc_crear_backup_db(max_backups=30)
            except Exception:
                path = None
            if not path:
                QMessageBox.warning(self, "Respaldos", "No se pudo crear el respaldo.")
                return
            _auditar(self, "Backup creado", str(path))
            QMessageBox.information(self, "Respaldos", f"Respaldo creado:\n{path}")
            self._cargar()
        finally:
            _antirebote_finalizar(self, "backups_crear", cooldown_ms=700)

    def _eliminar_backup(self):
        path = self._selected_path()
        if not path:
            QMessageBox.warning(self, "Respaldos", "Selecciona un respaldo.")
            return
        if not _antirebote_iniciar(self, "backups_eliminar"):
            return
        try:
            confirmar = QMessageBox.question(
                self,
                "Eliminar respaldo",
                f"Eliminar este respaldo?\n{path.name}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirmar != QMessageBox.Yes:
                return
            ok = svc_eliminar_backup_db(path)
            if not ok:
                QMessageBox.warning(self, "Respaldos", "No se pudo eliminar el respaldo.")
                return
            _auditar(self, "Backup eliminado", str(path))
            self._cargar()
        finally:
            _antirebote_finalizar(self, "backups_eliminar", cooldown_ms=700)

    def _restaurar_backup(self):
        path = self._selected_path()
        if not path:
            QMessageBox.warning(self, "Respaldos", "Selecciona un respaldo.")
            return
        if not _antirebote_iniciar(self, "backups_restaurar"):
            return
        try:
            confirmar = QMessageBox.question(
                self,
                "Restaurar respaldo",
                "Esto reemplazara la base de datos por el respaldo seleccionado.\n"
                "Se recomienda reiniciar la aplicacion luego.\n"
                "Continuar?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirmar != QMessageBox.Yes:
                return

            texto, ok = QInputDialog.getText(
                self,
                "Confirmar restauracion",
                "Escribe RESTAURAR para confirmar:",
            )
            if not ok or texto.strip().upper() != "RESTAURAR":
                return

            try:
                svc_crear_backup_db(max_backups=30)
            except Exception:
                pass

            ok = svc_restaurar_backup_db(path)
            if not ok:
                _mostrar_error(self, "Error", "No se pudo restaurar el respaldo.")
                return
            _auditar(self, "Backup restaurado", str(path))
            QMessageBox.information(
                self,
                "Respaldos",
                "Respaldo restaurado.\nSe recomienda reiniciar la aplicacion.",
            )
            self._cargar()
        finally:
            _antirebote_finalizar(self, "backups_restaurar", cooldown_ms=1000)


class ConfiguracionDialog(QDialog):
    def __init__(self, parent=None, rol=None):
        super().__init__(parent)
        self._rol = (rol or "").strip().upper()
        self.setWindowTitle("Configuracion")
        self.setMinimumWidth(520)
        self.setMinimumHeight(320)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        tab_general = QWidget()
        form_general = QFormLayout(tab_general)
        self.input_nombre = QLineEdit()
        self.input_telefono = QLineEdit()
        self.input_direccion = QLineEdit()
        self.input_alias = QLineEdit()
        self.input_cbu = QLineEdit()
        form_general.addRow("Nombre del negocio", self.input_nombre)
        form_general.addRow("Telefono", self.input_telefono)
        form_general.addRow("Direccion", self.input_direccion)
        form_general.addRow("Alias de cochera", self.input_alias)
        form_general.addRow("CBU de cochera", self.input_cbu)
        self._idx_tab_general = self.tabs.addTab(tab_general, "General")

        tab_contratos = QWidget()
        layout_contratos = QVBoxLayout(tab_contratos)
        form_contratos = QFormLayout()
        self.input_wa_template = QTextEdit()
        self.input_wa_template.setMinimumHeight(110)
        self.input_wa_template.setPlaceholderText(_plantilla_whatsapp_default())
        form_contratos.addRow("Mensaje recordatorio de contratos", self.input_wa_template)
        layout_contratos.addLayout(form_contratos)
        ayuda_wa = QLabel(
            "Como usar variables en el mensaje:\n"
            "{nombre}: reemplaza por el nombre del cliente.\n"
            "{vencimiento}: reemplaza por el vencimiento del contrato seleccionado.\n"
            "{deuda}: reemplaza por el valor de la nueva cuota del contrato.\n"
            "{cuota}: alias de {deuda} para usar el nombre mas claro.\n"
            "{patente}: reemplaza por la patente con formato (AA 123 AA o AAA 123).\n"
            "{modelo}: reemplaza por el modelo del vehiculo asociado (si existe).\n"
            "Escribilas tal cual, entre llaves.\n"
            "Ejemplo: Hola {nombre}, tu vencimiento es {vencimiento}. "
            "Patente: {patente}. Nueva cuota: {cuota}."
        )
        ayuda_wa.setObjectName("help_whatsapp")
        ayuda_wa.setWordWrap(True)
        layout_contratos.addWidget(ayuda_wa)
        layout_contratos.addStretch(1)
        self.tabs.addTab(tab_contratos, "Contratos")

        tab_reportes = QWidget()
        form_reportes = QFormLayout(tab_reportes)
        self.input_dir_reportes = QLineEdit()
        self.btn_dir_reportes = QPushButton("Elegir...")
        fila_reportes = QHBoxLayout()
        fila_reportes.addWidget(self.input_dir_reportes)
        fila_reportes.addWidget(self.btn_dir_reportes)
        form_reportes.addRow("Carpeta de reportes", fila_reportes)
        self.input_dir_comprobantes = QLineEdit()
        self.btn_dir_comprobantes = QPushButton("Elegir...")
        fila_comp = QHBoxLayout()
        fila_comp.addWidget(self.input_dir_comprobantes)
        fila_comp.addWidget(self.btn_dir_comprobantes)
        form_reportes.addRow("Carpeta de comprobantes", fila_comp)
        self.input_dir_tickets_salida = QLineEdit()
        self.btn_dir_tickets_salida = QPushButton("Elegir...")
        fila_tickets = QHBoxLayout()
        fila_tickets.addWidget(self.input_dir_tickets_salida)
        fila_tickets.addWidget(self.btn_dir_tickets_salida)
        form_reportes.addRow("Carpeta tickets de salida", fila_tickets)
        self.btn_carpetas_escritorio = QPushButton("Crear carpetas en el Escritorio")
        self.btn_carpetas_escritorio.setProperty("variant", "info")
        form_reportes.addRow("Acceso rapido", self.btn_carpetas_escritorio)
        self.tabs.addTab(tab_reportes, "Reportes")

        tab_sistema = QWidget()
        form_sistema = QFormLayout(tab_sistema)
        self.combo_resolucion = QComboBox()
        self.combo_resolucion.addItems(
            ["1024x600", "1280x720", "1366x768", "1600x900", "1920x1080"]
        )
        self.combo_tema = QComboBox()
        self.combo_tema.addItems(["Oscuro", "Claro"])
        self.combo_tamano_texto = QComboBox()
        self.combo_tamano_texto.addItem("Normal", "normal")
        self.combo_tamano_texto.addItem("Grande", "grande")
        self.combo_tamano_texto.addItem("Muy grande", "muy_grande")
        self.combo_tamano_texto.setToolTip(
            "Ajusta el tamano general del texto para facilitar la lectura."
        )
        self.check_coch_auto = QCheckBox("Permitir autos")
        self.check_coch_moto = QCheckBox("Permitir motos")
        self.check_coch_camioneta = QCheckBox("Permitir camionetas")
        tipos_coch = QVBoxLayout()
        tipos_coch.setContentsMargins(10, 8, 10, 10)
        tipos_coch.setSpacing(6)
        tipos_coch.addWidget(self.check_coch_auto)
        tipos_coch.addWidget(self.check_coch_moto)
        tipos_coch.addWidget(self.check_coch_camioneta)
        grupo_tipos_coch = QGroupBox("Cochera")
        grupo_tipos_coch.setToolTip(
            "Define que tipos de vehiculos se pueden usar para contratos de cochera."
        )
        grupo_tipos_coch.setLayout(tipos_coch)
        self.check_est_auto = QCheckBox("Permitir autos")
        self.check_est_moto = QCheckBox("Permitir motos")
        self.check_est_camioneta = QCheckBox("Permitir camionetas")
        tipos_est = QVBoxLayout()
        tipos_est.setContentsMargins(10, 8, 10, 10)
        tipos_est.setSpacing(6)
        tipos_est.addWidget(self.check_est_auto)
        tipos_est.addWidget(self.check_est_moto)
        tipos_est.addWidget(self.check_est_camioneta)
        grupo_tipos_est = QGroupBox("Estacionamiento")
        grupo_tipos_est.setToolTip(
            "Define que tipos de vehiculos se pueden recibir en estacionamiento."
        )
        grupo_tipos_est.setLayout(tipos_est)
        fila_tipos = QHBoxLayout()
        fila_tipos.setContentsMargins(0, 0, 0, 0)
        fila_tipos.setSpacing(12)
        fila_tipos.addWidget(grupo_tipos_coch, 1)
        fila_tipos.addWidget(grupo_tipos_est, 1)
        cont_tipos = QWidget()
        layout_tipos = QVBoxLayout(cont_tipos)
        layout_tipos.setContentsMargins(0, 0, 0, 0)
        layout_tipos.setSpacing(0)
        layout_tipos.addLayout(fila_tipos)
        self.btn_ultra_rtx = QPushButton("Activar ultra RTX 8K 120 FPS")
        self.btn_ultra_rtx.setProperty("variant", "info")
        form_sistema.addRow("Resolucion", self.combo_resolucion)
        form_sistema.addRow("Tema", self.combo_tema)
        form_sistema.addRow("Tamano de texto", self.combo_tamano_texto)
        form_sistema.addRow("Vehiculos permitidos", cont_tipos)
        form_sistema.addRow("Modo gamer", self.btn_ultra_rtx)
        self.tabs.addTab(tab_sistema, "Sistema")

        acciones = QHBoxLayout()
        acciones.addStretch(1)
        self.btn_guardar = QPushButton("Guardar")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_guardar.setProperty("variant", "success")
        self.btn_cerrar.setProperty("variant", "neutral")
        self.btn_guardar.setToolTip(
            "Guarda los cambios de General, Reportes y Sistema."
        )
        self.btn_cerrar.setToolTip(
            "Cierra Configuracion. Si cambiaste algo, la app te preguntara si quieres guardarlo."
        )
        acciones.addWidget(self.btn_guardar)
        acciones.addWidget(self.btn_cerrar)
        layout.addLayout(acciones)

        self.btn_guardar.clicked.connect(self._guardar)
        self.btn_cerrar.clicked.connect(self.reject)
        self.btn_dir_reportes.clicked.connect(
            lambda: self._seleccionar_carpeta(self.input_dir_reportes)
        )
        self.btn_dir_comprobantes.clicked.connect(
            lambda: self._seleccionar_carpeta(self.input_dir_comprobantes)
        )
        self.btn_dir_tickets_salida.clicked.connect(
            lambda: self._seleccionar_carpeta(self.input_dir_tickets_salida)
        )
        self.btn_carpetas_escritorio.clicked.connect(self._crear_carpetas_escritorio)
        self.btn_ultra_rtx.clicked.connect(self._activar_ultra_rtx)
        _instalar_enter_navegacion(
            self,
            {
                self.input_nombre: self.input_telefono,
                self.input_telefono: self.input_direccion,
                self.input_direccion: self.input_alias,
                self.input_alias: self.input_cbu,
                self.input_cbu: self.btn_guardar,
                self.input_dir_reportes: self.input_dir_comprobantes,
                self.input_dir_comprobantes: self.input_dir_tickets_salida,
                self.input_dir_tickets_salida: self.btn_carpetas_escritorio,
                self.btn_carpetas_escritorio: self.btn_guardar,
                self.combo_resolucion: self.combo_tema,
                self.combo_tema: self.combo_tamano_texto,
                self.combo_tamano_texto: self.check_coch_auto,
                self.check_coch_auto: self.check_coch_moto,
                self.check_coch_moto: self.check_coch_camioneta,
                self.check_coch_camioneta: self.check_est_auto,
                self.check_est_auto: self.check_est_moto,
                self.check_est_moto: self.check_est_camioneta,
                self.check_est_camioneta: self.btn_guardar,
            },
        )
        self._cargar()
        if self._rol == "OPERADOR":
            self.tabs.removeTab(self._idx_tab_general)

    def _snapshot_form(self):
        return (
            self.input_nombre.text().strip(),
            self.input_telefono.text().strip(),
            self.input_direccion.text().strip(),
            self.input_alias.text().strip(),
            self.input_cbu.text().strip(),
            self.input_wa_template.toPlainText().strip(),
            self.input_dir_reportes.text().strip(),
            self.input_dir_comprobantes.text().strip(),
            self.input_dir_tickets_salida.text().strip(),
            self.combo_resolucion.currentText(),
            self.combo_tema.currentText(),
            self.combo_tamano_texto.currentData(),
            bool(self.check_coch_auto.isChecked()),
            bool(self.check_coch_moto.isChecked()),
            bool(self.check_coch_camioneta.isChecked()),
            bool(self.check_est_auto.isChecked()),
            bool(self.check_est_moto.isChecked()),
            bool(self.check_est_camioneta.isChecked()),
        )

    def _actualizar_snapshot(self):
        self._snapshot = self._snapshot_form()

    def _hay_cambios_sin_guardar(self):
        return getattr(self, "_snapshot", None) != self._snapshot_form()

    def _cargar(self):
        self.input_nombre.setText(_config_get("empresa_nombre", ""))
        self.input_telefono.setText(_config_get("empresa_telefono", ""))
        self.input_direccion.setText(_config_get("empresa_direccion", ""))
        self.input_alias.setText(_config_get("empresa_alias", ""))
        self.input_cbu.setText(_config_get("empresa_cbu", ""))
        self.input_wa_template.setPlainText(
            _sanitizar_template_whatsapp(
                _config_get("wa_recordatorio_template", _plantilla_whatsapp_default())
            )
        )
        self.input_dir_reportes.setText(_config_get("dir_reportes", ""))
        self.input_dir_comprobantes.setText(_config_get("dir_comprobantes", ""))
        self.input_dir_tickets_salida.setText(_config_get("dir_tickets_salida", ""))
        resolucion = _config_get("ui_resolucion", "1280x720")
        idx_res = self.combo_resolucion.findText(resolucion)
        self.combo_resolucion.setCurrentIndex(idx_res if idx_res >= 0 else 1)
        tema = (_config_get("ui_tema", "oscuro") or "oscuro").strip().lower()
        self.combo_tema.setCurrentIndex(1 if tema == "claro" else 0)
        tamano_texto = _ui_tamano_texto()
        idx_tamano = self.combo_tamano_texto.findData(tamano_texto)
        self.combo_tamano_texto.setCurrentIndex(idx_tamano if idx_tamano >= 0 else 1)
        self.check_coch_auto.setChecked(_config_get_bool("coch_perm_auto", True))
        self.check_coch_moto.setChecked(_config_get_bool("coch_perm_moto", True))
        self.check_coch_camioneta.setChecked(_config_get_bool("coch_perm_camioneta", True))
        self.check_est_auto.setChecked(_config_get_bool("est_perm_auto", True))
        self.check_est_moto.setChecked(_config_get_bool("est_perm_moto", True))
        self.check_est_camioneta.setChecked(_config_get_bool("est_perm_camioneta", True))
        self._actualizar_snapshot()

    def _seleccionar_carpeta(self, input_destino):
        base = input_destino.text().strip() or str(Path(__file__).resolve().parent)
        carpeta = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", base)
        if carpeta:
            input_destino.setText(carpeta)

    def _carpeta_escritorio_base(self):
        return _escritorio_base_actual()

    def _crear_carpetas_escritorio(self):
        base = self._carpeta_escritorio_base()
        rutas = {
            "reportes": base / "Reportes Cochera",
            "comprobantes": base / "Comprobantes Cochera",
            "tickets": base / "Tickets Salida Cochera",
        }
        try:
            for ruta in rutas.values():
                ruta.mkdir(parents=True, exist_ok=True)
        except OSError:
            _mostrar_error(
                self,
                "Carpetas",
                "No se pudieron crear las carpetas en el Escritorio.",
            )
            return

        self.input_dir_reportes.setText(str(rutas["reportes"]))
        self.input_dir_comprobantes.setText(str(rutas["comprobantes"]))
        self.input_dir_tickets_salida.setText(str(rutas["tickets"]))
        QMessageBox.information(
            self,
            "Carpetas",
            "Se crearon las carpetas en el Escritorio y las rutas ya quedaron cargadas.\n"
            f"Ubicacion usada: {base}\n\n"
            "Pulsa Guardar para dejarlas fijas en la configuracion.",
        )

    def _activar_ultra_rtx(self):
        QMessageBox.information(
            self,
            "Ultra RTX 8K 120 FPS",
            "Modo ultra activado.\nAhora funciona a 120 FPS... en tu imaginacion.",
        )

    def _guardar(self):
        tema = "claro" if self.combo_tema.currentText() == "Claro" else "oscuro"
        resolucion = self.combo_resolucion.currentText()
        tamano_texto = self.combo_tamano_texto.currentData() or "grande"
        dir_reportes = self.input_dir_reportes.text().strip()
        dir_comprobantes = self.input_dir_comprobantes.text().strip()
        dir_tickets_salida = self.input_dir_tickets_salida.text().strip()
        coch_perm_auto = self.check_coch_auto.isChecked()
        coch_perm_moto = self.check_coch_moto.isChecked()
        coch_perm_camioneta = self.check_coch_camioneta.isChecked()
        est_perm_auto = self.check_est_auto.isChecked()
        est_perm_moto = self.check_est_moto.isChecked()
        est_perm_camioneta = self.check_est_camioneta.isChecked()
        if not self._hay_cambios_sin_guardar():
            QMessageBox.information(
                self,
                "Configuracion",
                "No hay cambios nuevos para guardar.",
            )
            return
        try:
            # Primero dejo listas las carpetas, porque si no despues exportar o guardar comprobantes falla al pedo.
            if dir_reportes:
                Path(dir_reportes).mkdir(parents=True, exist_ok=True)
            if dir_comprobantes:
                Path(dir_comprobantes).mkdir(parents=True, exist_ok=True)
            if dir_tickets_salida:
                Path(dir_tickets_salida).mkdir(parents=True, exist_ok=True)
            ok = True
            ok = _config_set("empresa_nombre", self.input_nombre.text().strip()) and ok
            ok = _config_set("empresa_telefono", self.input_telefono.text().strip()) and ok
            ok = _config_set("empresa_direccion", self.input_direccion.text().strip()) and ok
            ok = _config_set("empresa_alias", self.input_alias.text().strip()) and ok
            ok = _config_set("empresa_cbu", self.input_cbu.text().strip()) and ok
            ok = _config_set(
                "wa_recordatorio_template",
                _sanitizar_template_whatsapp(self.input_wa_template.toPlainText()),
            ) and ok
            ok = _config_set("dir_reportes", dir_reportes) and ok
            ok = _config_set("dir_comprobantes", dir_comprobantes) and ok
            ok = _config_set("dir_tickets_salida", dir_tickets_salida) and ok
            ok = _config_set("ui_tema", tema) and ok
            ok = _config_set("ui_resolucion", resolucion) and ok
            ok = _config_set("ui_tamano_texto", tamano_texto) and ok
            ok = _config_set("coch_perm_auto", "1" if coch_perm_auto else "0") and ok
            ok = _config_set("coch_perm_moto", "1" if coch_perm_moto else "0") and ok
            ok = _config_set("coch_perm_camioneta", "1" if coch_perm_camioneta else "0") and ok
            ok = _config_set("est_perm_auto", "1" if est_perm_auto else "0") and ok
            ok = _config_set("est_perm_moto", "1" if est_perm_moto else "0") and ok
            ok = _config_set("est_perm_camioneta", "1" if est_perm_camioneta else "0") and ok
            if not ok:
                raise sqlite3.Error()
            _auditar(self, "Configuracion actualizada", "Datos generales del sistema")
            self._actualizar_snapshot()
            QMessageBox.information(self, "Configuracion", "Cambios guardados.")
            self.accept()
        except (sqlite3.Error, OSError):
            _mostrar_error(self, "Error", "No se pudo guardar la configuracion.")

    def closeEvent(self, event):
        if not self._hay_cambios_sin_guardar():
            event.accept()
            return
        respuesta = _confirmar_guardado_pendiente(
            self,
            "Hay cambios en Configuracion.\nQuieres guardarlos antes de salir?",
        )
        if respuesta == QMessageBox.Cancel:
            event.ignore()
            return
        if respuesta == QMessageBox.No:
            event.accept()
            return
        self._guardar()
        if self.result() == QDialog.Accepted:
            event.accept()
        else:
            event.ignore()


def _usuarios_existen():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM usuarios")
        return (cur.fetchone()[0] or 0) > 0
    except sqlite3.Error:
        return False
    finally:
        if conn:
            conn.close()


class VentanaPrincipal(QMainWindow):
    def __init__(self, usuario=None, rol=None):
        super().__init__()
        self.usuario = usuario
        self.rol = rol
        self._popup_vencimientos_mostrado = False
        self._popup_vencimientos_intentos = 0
        self._popup_primeros_pasos_mostrado = False
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("Gestor bien pro")
        self._ajustar_ui()
        self._estilo_oscuro_cache = self.styleSheet()
        self._aplicar_preferencias_ui()
        self._configurar_menus()
        self._aplicar_rol()
        self._configurar_modos()
        self._configurar_reloj()
        self._configurar_dashboard()
        self._configurar_estacionamiento()
        self._configurar_atajos()
        self._programar_popup_vencimientos_inicio()
        self._programar_popup_primeros_pasos()

    def _ajustar_ui(self):
        self.resize(1280, 720)
        self.setMinimumSize(1024, 600)
        self.setStyleSheet(
            """
            QGroupBox {
                border: 1px solid #3b3f45;
                border-radius: 8px;
                margin-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #f0c674;
                font-weight: 600;
            }
            QPushButton {
                background-color: #2b8a95;
                color: #eaf6f6;
                border: 1px solid #37a3ae;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #33a4af;
            }
            QPushButton:pressed {
                background-color: #257983;
            }
            QPushButton:disabled {
                background-color: #3a3a3a;
                color: #777777;
                border-color: #444444;
            }
            QPushButton[variant="success"] {
                background-color: #1F7A4C;
                border-color: #2FA86B;
                color: #E9FFF1;
            }
            QPushButton[variant="success"]:hover {
                background-color: #25915B;
            }
            QPushButton[variant="success"]:pressed {
                background-color: #17613D;
            }
            QPushButton[variant="info"] {
                background-color: #1D4ED8;
                border-color: #3B82F6;
                color: #EEF2FF;
            }
            QPushButton[variant="info"]:hover {
                background-color: #2563EB;
            }
            QPushButton[variant="info"]:pressed {
                background-color: #1E40AF;
            }
            QPushButton[variant="warning"] {
                background-color: #B45309;
                border-color: #F59E0B;
                color: #FFFBEB;
            }
            QPushButton[variant="warning"]:hover {
                background-color: #D97706;
            }
            QPushButton[variant="warning"]:pressed {
                background-color: #92400E;
            }
            QPushButton[variant="danger"] {
                background-color: #B42318;
                border-color: #EF4444;
                color: #FFF5F5;
            }
            QPushButton[variant="danger"]:hover {
                background-color: #DC2626;
            }
            QPushButton[variant="danger"]:pressed {
                background-color: #991B1B;
            }
            QPushButton[variant="neutral"] {
                background-color: #3F4C59;
                border-color: #556270;
                color: #F3F4F6;
            }
            QPushButton[variant="neutral"]:hover {
                background-color: #4B5968;
            }
            QPushButton[variant="neutral"]:pressed {
                background-color: #2E3640;
            }
            QPushButton#btn_cochera {
                background-color: #1f6feb;
                border-color: #2a7fff;
                color: #f2f6ff;
            }
            QPushButton#btn_cochera:hover {
                background-color: #2f7bf0;
            }
            QPushButton#btn_cochera:pressed {
                background-color: #1b5fc9;
            }
            QPushButton#btn_estacionamiento {
                background-color: #b42318;
                border-color: #ef4444;
                color: #fff5f5;
            }
            QPushButton#btn_estacionamiento:hover {
                background-color: #dc2626;
            }
            QPushButton#btn_estacionamiento:pressed {
                background-color: #991b1b;
            }
            QPushButton#btn_mapa_cocheras {
                background-color: #0F6B6C;
                border-color: #1B8C8E;
                color: #E6F7F7;
            }
            QPushButton#btn_mapa_cocheras:hover {
                background-color: #147C7D;
            }
            QPushButton#btn_mapa_cocheras:pressed {
                background-color: #0B5556;
            }
            QPushButton#btn_clientes {
                background-color: #5B3CC4;
                border-color: #7A5CE0;
                color: #F1ECFF;
            }
            QPushButton#btn_clientes:hover {
                background-color: #6A4AD1;
            }
            QPushButton#btn_clientes:pressed {
                background-color: #4A2FA7;
            }
            QPushButton#btn_contratos {
                background-color: #C96B24;
                border-color: #E08A3F;
                color: #FFF3E6;
            }
            QPushButton#btn_contratos:hover {
                background-color: #D97A2E;
            }
            QPushButton#btn_contratos:pressed {
                background-color: #B55B1E;
            }
            QPushButton#btn_reportes, QPushButton#btn_reportes_est {
                background-color: #2D7A2D;
                border-color: #43A043;
                color: #E9F6E9;
            }
            QPushButton#btn_reportes:hover, QPushButton#btn_reportes_est:hover {
                background-color: #368A36;
            }
            QPushButton#btn_reportes:pressed, QPushButton#btn_reportes_est:pressed {
                background-color: #236223;
            }
            QPushButton#btn_vencimientos {
                background-color: #2b2f33;
                border-color: #3b3f45;
                color: #e0e0e0;
            }
            QPushButton#btn_vencimientos:hover {
                background-color: #353a3f;
            }
            QPushButton#btn_vencimientos:pressed {
                background-color: #24282c;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
                background-color: #202325;
                border: 1px solid #3c4a52;
                border-radius: 6px;
                padding: 4px 6px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {
                border-color: #53c7b8;
            }
            QFrame#card_total, QFrame#card_ocupadas, QFrame#card_libres,
            QFrame#card_ingresos, QFrame#card_mensual,
            QFrame#card_est_hora, QFrame#card_est_tarifa,
            QFrame#card_est_total, QFrame#card_est_ocupadas,
            QFrame#card_est_libres, QFrame#card_est_tarifa_resumen {
                background-color: #262b2f;
                border: 1px solid #384046;
                border-radius: 8px;
            }
            QFrame#card_total {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0ea5e9, stop:0.08 #0ea5e9,
                    stop:0.081 #262b2f, stop:1 #262b2f);
                border-color: #0284c7;
            }
            QFrame#card_ocupadas {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f97316, stop:0.08 #f97316,
                    stop:0.081 #262b2f, stop:1 #262b2f);
                border-color: #ea580c;
            }
            QFrame#card_libres {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #22c55e, stop:0.08 #22c55e,
                    stop:0.081 #262b2f, stop:1 #262b2f);
                border-color: #16a34a;
            }
            QFrame#card_ingresos {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #14b8a6, stop:0.08 #14b8a6,
                    stop:0.081 #262b2f, stop:1 #262b2f);
                border-color: #0f766e;
            }
            QFrame#card_mensual {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #a855f7, stop:0.08 #a855f7,
                    stop:0.081 #262b2f, stop:1 #262b2f);
                border-color: #9333ea;
            }
            QFrame#card_est_total {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0ea5e9, stop:0.08 #0ea5e9,
                    stop:0.081 #262b2f, stop:1 #262b2f);
                border-color: #0284c7;
            }
            QFrame#card_est_ocupadas {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f97316, stop:0.08 #f97316,
                    stop:0.081 #262b2f, stop:1 #262b2f);
                border-color: #ea580c;
            }
            QFrame#card_est_libres {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #22c55e, stop:0.08 #22c55e,
                    stop:0.081 #262b2f, stop:1 #262b2f);
                border-color: #16a34a;
            }
            QFrame#card_est_tarifa_resumen {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #a855f7, stop:0.08 #a855f7,
                    stop:0.081 #262b2f, stop:1 #262b2f);
                border-color: #9333ea;
            }
            QLabel#label_est_total_value {
                color: #7dd3fc;
            }
            QLabel#label_est_ocupadas_value {
                color: #fdba74;
            }
            QLabel#label_est_libres_value {
                color: #86efac;
            }
            QLabel#label_est_tarifa_resumen_value {
                color: #d8b4fe;
            }
            QLabel#label_total_value {
                color: #7dd3fc;
            }
            QLabel#label_ocupadas_value {
                color: #fdba74;
            }
            QLabel#label_libres_value {
                color: #86efac;
            }
            QLabel#label_ingresos_value {
                color: #5eead4;
            }
            QLabel#label_mensual_value {
                color: #d8b4fe;
            }
            QLabel#help_whatsapp {
                color: #9ca3af;
            }
            """
        )

    def _estilo_claro(self):
        return """
            QMainWindow, QDialog {
                background-color: #eef2f7;
                color: #1f2937;
            }
            QWidget {
                color: #1f2937;
            }
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #d8dee6;
                border-radius: 8px;
                margin-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #9a3412;
                font-weight: 700;
            }
            QPushButton {
                background-color: #0f766e;
                color: #f8fafc;
                border: 1px solid #0f766e;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #0d8a81;
            }
            QPushButton:pressed {
                background-color: #0b5f59;
            }
            QPushButton:disabled {
                background-color: #e5e7eb;
                color: #94a3b8;
                border-color: #cbd5e1;
            }
            QPushButton[variant="success"] {
                background-color: #15803d;
                border-color: #16a34a;
                color: #f0fdf4;
            }
            QPushButton[variant="success"]:hover {
                background-color: #169447;
            }
            QPushButton[variant="success"]:pressed {
                background-color: #166534;
            }
            QPushButton[variant="info"] {
                background-color: #2563eb;
                border-color: #3b82f6;
                color: #eff6ff;
            }
            QPushButton[variant="info"]:hover {
                background-color: #1d4ed8;
            }
            QPushButton[variant="info"]:pressed {
                background-color: #1e40af;
            }
            QPushButton[variant="warning"] {
                background-color: #d97706;
                border-color: #f59e0b;
                color: #fff7ed;
            }
            QPushButton[variant="warning"]:hover {
                background-color: #ea8a10;
            }
            QPushButton[variant="warning"]:pressed {
                background-color: #b45309;
            }
            QPushButton[variant="danger"] {
                background-color: #dc2626;
                border-color: #ef4444;
                color: #fef2f2;
            }
            QPushButton[variant="danger"]:hover {
                background-color: #ef4444;
            }
            QPushButton[variant="danger"]:pressed {
                background-color: #b91c1c;
            }
            QPushButton[variant="neutral"] {
                background-color: #e2e8f0;
                border-color: #cbd5e1;
                color: #334155;
            }
            QPushButton[variant="neutral"]:hover {
                background-color: #dbe4ef;
            }
            QPushButton[variant="neutral"]:pressed {
                background-color: #cbd5e1;
            }
            QPushButton#btn_cochera {
                background-color: #2563eb;
                border-color: #3b82f6;
                color: #eff6ff;
            }
            QPushButton#btn_cochera:hover {
                background-color: #1d4ed8;
            }
            QPushButton#btn_cochera:pressed {
                background-color: #1e40af;
            }
            QPushButton#btn_estacionamiento {
                background-color: #dc2626;
                border-color: #ef4444;
                color: #fef2f2;
            }
            QPushButton#btn_estacionamiento:hover {
                background-color: #ef4444;
            }
            QPushButton#btn_estacionamiento:pressed {
                background-color: #b91c1c;
            }
            QPushButton#btn_mapa_cocheras {
                background-color: #0f766e;
                border-color: #14b8a6;
                color: #f0fdfa;
            }
            QPushButton#btn_mapa_cocheras:hover {
                background-color: #0d8a81;
            }
            QPushButton#btn_mapa_cocheras:pressed {
                background-color: #0f5f59;
            }
            QPushButton#btn_clientes {
                background-color: #6d28d9;
                border-color: #8b5cf6;
                color: #f5f3ff;
            }
            QPushButton#btn_clientes:hover {
                background-color: #7c3aed;
            }
            QPushButton#btn_clientes:pressed {
                background-color: #5b21b6;
            }
            QPushButton#btn_contratos {
                background-color: #c96b24;
                border-color: #e08a3f;
                color: #fff7ed;
            }
            QPushButton#btn_contratos:hover {
                background-color: #d97706;
            }
            QPushButton#btn_contratos:pressed {
                background-color: #b45309;
            }
            QPushButton#btn_reportes, QPushButton#btn_reportes_est {
                background-color: #2f855a;
                border-color: #38a169;
                color: #f0fff4;
            }
            QPushButton#btn_reportes:hover, QPushButton#btn_reportes_est:hover {
                background-color: #38a169;
            }
            QPushButton#btn_reportes:pressed, QPushButton#btn_reportes_est:pressed {
                background-color: #276749;
            }
            QPushButton#btn_vencimientos {
                background-color: #ffffff;
                border-color: #d8dee6;
                color: #334155;
            }
            QPushButton#btn_vencimientos:hover {
                background-color: #f8fafc;
            }
            QPushButton#btn_vencimientos:pressed {
                background-color: #e2e8f0;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 4px 6px;
                selection-background-color: #bfdbfe;
                selection-color: #0f172a;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTextEdit:focus {
                border-color: #38bdf8;
                background-color: #f8fbff;
            }
            QTableWidget, QListWidget {
                background-color: #ffffff;
                alternate-background-color: #f8fafc;
                color: #111827;
                border: 1px solid #d8dee6;
                border-radius: 8px;
                gridline-color: #e5e7eb;
            }
            QHeaderView::section {
                background-color: #eef2f7;
                color: #334155;
                border: none;
                border-bottom: 1px solid #d8dee6;
                border-right: 1px solid #e5e7eb;
                padding: 6px;
                font-weight: 600;
            }
            QTabWidget::pane {
                background-color: #ffffff;
                border: 1px solid #d8dee6;
                border-radius: 8px;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #e8eef5;
                color: #475569;
                border: 1px solid #d8dee6;
                border-bottom: none;
                padding: 7px 12px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #0f172a;
            }
            QMenuBar {
                background-color: #ffffff;
                color: #1f2937;
                border-bottom: 1px solid #d8dee6;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background-color: #eff6ff;
                border-radius: 4px;
            }
            QMenu {
                background-color: #ffffff;
                color: #1f2937;
                border: 1px solid #d8dee6;
            }
            QMenu::item {
                padding: 6px 22px;
            }
            QMenu::item:selected {
                background-color: #0ea5e9;
                color: #f8fafc;
            }
            QFrame#card_total, QFrame#card_ocupadas, QFrame#card_libres,
            QFrame#card_ingresos, QFrame#card_mensual,
            QFrame#card_est_hora, QFrame#card_est_tarifa,
            QFrame#card_est_total, QFrame#card_est_ocupadas,
            QFrame#card_est_libres, QFrame#card_est_tarifa_resumen {
                background-color: #ffffff;
                border: 1px solid #d8dee6;
                border-radius: 8px;
            }
            QFrame#card_total {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #38bdf8, stop:0.08 #38bdf8,
                    stop:0.081 #ffffff, stop:1 #ffffff);
                border-color: #7dd3fc;
            }
            QFrame#card_ocupadas {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #fb923c, stop:0.08 #fb923c,
                    stop:0.081 #ffffff, stop:1 #ffffff);
                border-color: #fdba74;
            }
            QFrame#card_libres {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4ade80, stop:0.08 #4ade80,
                    stop:0.081 #ffffff, stop:1 #ffffff);
                border-color: #86efac;
            }
            QFrame#card_ingresos {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2dd4bf, stop:0.08 #2dd4bf,
                    stop:0.081 #ffffff, stop:1 #ffffff);
                border-color: #5eead4;
            }
            QFrame#card_mensual {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #c084fc, stop:0.08 #c084fc,
                    stop:0.081 #ffffff, stop:1 #ffffff);
                border-color: #d8b4fe;
            }
            QFrame#card_est_total {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #38bdf8, stop:0.08 #38bdf8,
                    stop:0.081 #ffffff, stop:1 #ffffff);
                border-color: #7dd3fc;
            }
            QFrame#card_est_ocupadas {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #fb923c, stop:0.08 #fb923c,
                    stop:0.081 #ffffff, stop:1 #ffffff);
                border-color: #fdba74;
            }
            QFrame#card_est_libres {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4ade80, stop:0.08 #4ade80,
                    stop:0.081 #ffffff, stop:1 #ffffff);
                border-color: #86efac;
            }
            QFrame#card_est_tarifa_resumen {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #c084fc, stop:0.08 #c084fc,
                    stop:0.081 #ffffff, stop:1 #ffffff);
                border-color: #d8b4fe;
            }
            QLabel#label_est_total_value {
                color: #0369a1;
            }
            QLabel#label_est_ocupadas_value {
                color: #c2410c;
            }
            QLabel#label_est_libres_value {
                color: #15803d;
            }
            QLabel#label_est_tarifa_resumen_value {
                color: #7e22ce;
            }
            QLabel#label_total_value {
                color: #0369a1;
            }
            QLabel#label_ocupadas_value {
                color: #c2410c;
            }
            QLabel#label_libres_value {
                color: #15803d;
            }
            QLabel#label_ingresos_value {
                color: #0f766e;
            }
            QLabel#label_mensual_value {
                color: #7e22ce;
            }
            QLabel#help_whatsapp {
                color: #475569;
            }
        """

    def _centrar_en_pantalla(self):
        pantalla = self.screen() or QApplication.primaryScreen()
        if pantalla is None:
            return
        area = pantalla.availableGeometry()
        marco = self.frameGeometry()
        marco.moveCenter(area.center())
        self.move(marco.topLeft())

    def _aplicar_preferencias_ui(self):
        app = QApplication.instance()
        _aplicar_fuente_aplicacion(app)
        if app is not None:
            self.setFont(app.font())
        tema = (_config_get("ui_tema", "oscuro") or "oscuro").strip().lower()
        if tema == "claro":
            self.setStyleSheet(self._estilo_claro())
        else:
            self.setStyleSheet(getattr(self, "_estilo_oscuro_cache", self.styleSheet()))

        resolucion = (_config_get("ui_resolucion", "1280x720") or "1280x720").strip().lower()
        if "x" in resolucion:
            try:
                w_txt, h_txt = resolucion.split("x", 1)
                w = max(1024, int(w_txt))
                h = max(600, int(h_txt))
                self.resize(w, h)
                self._centrar_en_pantalla()
            except ValueError:
                pass

        kpi_title_font = QFont()
        kpi_title_font.setPointSize(_ui_escalar_pt(8, minimo=8))
        kpi_title_font.setBold(True)

        kpi_value_font = QFont()
        kpi_value_font.setPointSize(_ui_escalar_pt(11, minimo=11))
        kpi_value_font.setBold(True)

        if hasattr(self.ui, "verticalLayout"):
            self.ui.verticalLayout.setContentsMargins(
                _ui_escalar_px(4, minimo=4),
                _ui_escalar_px(2, minimo=2),
                _ui_escalar_px(4, minimo=4),
                _ui_escalar_px(2, minimo=2),
            )
            self.ui.verticalLayout.setSpacing(0)

        if hasattr(self.ui, "modeButtonsLayout"):
            self.ui.modeButtonsLayout.setContentsMargins(0, 0, 0, 0)
            self.ui.modeButtonsLayout.setSpacing(_ui_escalar_px(4, minimo=4))

        if hasattr(self.ui, "cocheraLayout"):
            self.ui.cocheraLayout.setSpacing(_ui_escalar_px(2, minimo=2))
            self.ui.cocheraLayout.setContentsMargins(0, 0, 0, 0)

        if hasattr(self.ui, "estacionamientoLayout"):
            self.ui.estacionamientoLayout.setSpacing(_ui_escalar_px(2, minimo=2))
            self.ui.estacionamientoLayout.setContentsMargins(0, 0, 0, 0)

        if hasattr(self.ui, "cocheraLayout") and hasattr(
            self.ui, "group_cochera_resumen"
        ):
            idx = self.ui.cocheraLayout.indexOf(self.ui.group_cochera_resumen)
            if idx >= 0:
                self.ui.cocheraLayout.setStretch(idx, 0)
            self.ui.group_cochera_resumen.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Fixed
            )
            self.ui.group_cochera_resumen.setMaximumHeight(_ui_escalar_px(200, minimo=200))

        if hasattr(self.ui, "kpiGrid"):
            for col in range(3):
                self.ui.kpiGrid.setColumnStretch(col, 1)
            self.ui.kpiGrid.setRowStretch(0, 0)
            self.ui.kpiGrid.setRowStretch(1, 0)
            self.ui.kpiGrid.setHorizontalSpacing(_ui_escalar_px(6, minimo=6))
            self.ui.kpiGrid.setVerticalSpacing(_ui_escalar_px(6, minimo=6))

        for card_name in (
            "card_total",
            "card_ocupadas",
            "card_libres",
            "card_ingresos",
            "card_mensual",
        ):
            card = getattr(self.ui, card_name, None)
            if card:
                card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                card.setMinimumHeight(_ui_escalar_px(48, minimo=48))
                card.setMaximumHeight(_ui_escalar_px(80, minimo=80))

        for name in (
            "label_total_title",
            "label_ocupadas_title",
            "label_libres_title",
            "label_ingresos_title",
            "label_mensual_title",
        ):
            label = getattr(self.ui, name, None)
            if label:
                label.setFont(kpi_title_font)

        for name in (
            "label_total_value",
            "label_ocupadas_value",
            "label_libres_value",
            "label_ingresos_value",
            "label_mensual_value",
        ):
            label = getattr(self.ui, name, None)
            if label:
                label.setFont(kpi_value_font)

        if hasattr(self.ui, "cochera_resumen_layout"):
            self.ui.cochera_resumen_layout.setContentsMargins(
                _ui_escalar_px(6, minimo=6),
                _ui_escalar_px(6, minimo=6),
                _ui_escalar_px(6, minimo=6),
                _ui_escalar_px(6, minimo=6),
            )
            self.ui.cochera_resumen_layout.setSpacing(_ui_escalar_px(6, minimo=6))

        titulo_font = QFont()
        titulo_font.setPointSize(_ui_escalar_pt(12, minimo=12))
        titulo_font.setBold(True)

        for name in ("label_cochera_title",):
            label = getattr(self.ui, name, None)
            if label:
                label.setFont(titulo_font)
                label.setMaximumHeight(_ui_escalar_px(26, minimo=26))
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        fecha_font = QFont()
        fecha_font.setPointSize(_ui_escalar_pt(14, minimo=14))
        fecha_font.setBold(True)

        for name in ("label_fecha_num", "label_est_fecha_num", "label_hora_value"):
            label = getattr(self.ui, name, None)
            if label:
                label.setFont(fecha_font)
                label.setMaximumHeight(_ui_escalar_px(24, minimo=24))
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if hasattr(self.ui, "label_hora_value"):
            self.ui.label_hora_value.setVisible(False)
        if hasattr(self.ui, "label_est_hora_top_value"):
            self.ui.label_est_hora_top_value.setVisible(False)

        if hasattr(self.ui, "estacionamientoLayout") and hasattr(
            self.ui, "group_est_activos"
        ):
            idx = self.ui.estacionamientoLayout.indexOf(self.ui.group_est_activos)
            if idx >= 0:
                self.ui.estacionamientoLayout.setStretch(idx, 1)

        if hasattr(self.ui, "card_est_hora"):
            self.ui.card_est_hora.setVisible(False)
        if hasattr(self.ui, "card_est_tarifa"):
            self.ui.card_est_tarifa.setVisible(False)

        if hasattr(self.ui, "estacionamientoLayout") and hasattr(
            self.ui, "group_est_registro"
        ):
            if not hasattr(self.ui, "group_est_resumen"):
                self.ui.group_est_resumen = QGroupBox(self.ui.page_estacionamiento)
                self.ui.group_est_resumen.setObjectName("group_est_resumen")
                self.ui.group_est_resumen.setTitle("Resumen estacionamiento")
                self.ui.est_resumen_layout = QVBoxLayout(self.ui.group_est_resumen)
                self.ui.est_resumen_layout.setContentsMargins(
                    _ui_escalar_px(6, minimo=6),
                    _ui_escalar_px(6, minimo=6),
                    _ui_escalar_px(6, minimo=6),
                    _ui_escalar_px(6, minimo=6),
                )
                self.ui.est_resumen_layout.setSpacing(_ui_escalar_px(6, minimo=6))
                self.ui.est_resumen_grid = QGridLayout()
                self.ui.est_resumen_grid.setHorizontalSpacing(_ui_escalar_px(6, minimo=6))
                self.ui.est_resumen_grid.setVerticalSpacing(_ui_escalar_px(6, minimo=6))
                for col in range(4):
                    self.ui.est_resumen_grid.setColumnStretch(col, 1)

                def _crear_card_est(nombre_card, nombre_title, nombre_value, texto_title, texto_value):
                    card = QFrame(self.ui.group_est_resumen)
                    card.setObjectName(nombre_card)
                    card.setFrameShape(QFrame.StyledPanel)
                    layout_card = QVBoxLayout(card)
                    layout_card.setContentsMargins(
                        _ui_escalar_px(6, minimo=6),
                        _ui_escalar_px(6, minimo=6),
                        _ui_escalar_px(6, minimo=6),
                        _ui_escalar_px(6, minimo=6),
                    )
                    layout_card.setSpacing(_ui_escalar_px(4, minimo=4))
                    lbl_title = QLabel(card)
                    lbl_title.setObjectName(nombre_title)
                    lbl_title.setAlignment(Qt.AlignCenter)
                    lbl_title.setText(texto_title)
                    lbl_value = QLabel(card)
                    lbl_value.setObjectName(nombre_value)
                    lbl_value.setAlignment(Qt.AlignCenter)
                    lbl_value.setText(texto_value)
                    layout_card.addWidget(lbl_title)
                    layout_card.addWidget(lbl_value)
                    setattr(self.ui, nombre_card, card)
                    setattr(self.ui, nombre_title, lbl_title)
                    setattr(self.ui, nombre_value, lbl_value)
                    return card

                card_est_total = _crear_card_est(
                    "card_est_total",
                    "label_est_total_title",
                    "label_est_total_value",
                    "Espacios totales",
                    "0",
                )
                card_est_ocupadas = _crear_card_est(
                    "card_est_ocupadas",
                    "label_est_ocupadas_title",
                    "label_est_ocupadas_value",
                    "Espacios usados",
                    "0",
                )
                card_est_libres = _crear_card_est(
                    "card_est_libres",
                    "label_est_libres_title",
                    "label_est_libres_value",
                    "Espacios libres",
                    "0",
                )
                card_est_tarifa_resumen = _crear_card_est(
                    "card_est_tarifa_resumen",
                    "label_est_tarifa_resumen_title",
                    "label_est_tarifa_resumen_value",
                    "Tarifa por hora",
                    "$ 0.00",
                )

                self.ui.est_resumen_grid.addWidget(card_est_total, 0, 0, 1, 1)
                self.ui.est_resumen_grid.addWidget(card_est_ocupadas, 0, 1, 1, 1)
                self.ui.est_resumen_grid.addWidget(card_est_libres, 0, 2, 1, 1)
                self.ui.est_resumen_grid.addWidget(card_est_tarifa_resumen, 0, 3, 1, 1)
                self.ui.est_resumen_layout.addLayout(self.ui.est_resumen_grid)

                idx_reg = self.ui.estacionamientoLayout.indexOf(self.ui.group_est_registro)
                if idx_reg < 0:
                    self.ui.estacionamientoLayout.addWidget(self.ui.group_est_resumen)
                else:
                    self.ui.estacionamientoLayout.insertWidget(idx_reg, self.ui.group_est_resumen)

        if hasattr(self.ui, "group_est_resumen"):
            self.ui.group_est_resumen.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.ui.group_est_resumen.setMaximumHeight(_ui_escalar_px(150, minimo=150))
            self.ui.group_est_resumen.setMinimumHeight(_ui_escalar_px(95, minimo=95))

        if hasattr(self.ui, "group_est_acciones") and not hasattr(self.ui, "btn_reportes_est"):
            self.ui.btn_reportes_est = QPushButton(self.ui.group_est_acciones)
            self.ui.btn_reportes_est.setObjectName("btn_reportes_est")
            self.ui.btn_reportes_est.setText("Reportes")
            if hasattr(self.ui, "estAccionesSpacer"):
                idx_spacer = self.ui.estAccionesLayout.indexOf(self.ui.estAccionesSpacer)
                if idx_spacer >= 0:
                    self.ui.estAccionesLayout.insertWidget(idx_spacer, self.ui.btn_reportes_est)
                else:
                    self.ui.estAccionesLayout.addWidget(self.ui.btn_reportes_est)
            else:
                self.ui.estAccionesLayout.addWidget(self.ui.btn_reportes_est)

        for name in (
            "label_est_total_title",
            "label_est_ocupadas_title",
            "label_est_libres_title",
            "label_est_tarifa_resumen_title",
        ):
            label = getattr(self.ui, name, None)
            if label:
                label.setFont(kpi_title_font)

        for name in (
            "label_est_total_value",
            "label_est_ocupadas_value",
            "label_est_libres_value",
            "label_est_tarifa_resumen_value",
        ):
            label = getattr(self.ui, name, None)
            if label:
                label.setFont(kpi_value_font)

        botones = [
            "btn_cochera",
            "btn_estacionamiento",
            "btn_mapa_cocheras",
            "btn_clientes",
            "btn_contratos",
            "btn_reportes",
            "btn_reportes_est",
            "btn_vencimientos",
            "btn_mapa_est",
            "btn_ingreso_est",
            "btn_salida_est",
        ]
        for name in botones:
            btn = getattr(self.ui, name, None)
            if not btn:
                continue
            btn.setMinimumHeight(_ui_escalar_px(26, minimo=26))
            btn.setMaximumHeight(_ui_escalar_px(32, minimo=32))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if hasattr(self.ui, "btn_ingreso_est"):
            self.ui.btn_ingreso_est.setProperty("variant", "success")
            self.ui.btn_ingreso_est.style().unpolish(self.ui.btn_ingreso_est)
            self.ui.btn_ingreso_est.style().polish(self.ui.btn_ingreso_est)
        if hasattr(self.ui, "btn_salida_est"):
            self.ui.btn_salida_est.setProperty("variant", "danger")
            self.ui.btn_salida_est.style().unpolish(self.ui.btn_salida_est)
            self.ui.btn_salida_est.style().polish(self.ui.btn_salida_est)
        if hasattr(self.ui, "btn_mapa_est"):
            self.ui.btn_mapa_est.setProperty("variant", "info")
            self.ui.btn_mapa_est.style().unpolish(self.ui.btn_mapa_est)
            self.ui.btn_mapa_est.style().polish(self.ui.btn_mapa_est)

        for group_name, layout_name in (
            ("group_cochera_acciones", "accionesCocheraLayout"),
            ("group_est_acciones", "estAccionesLayout"),
        ):
            group = getattr(self.ui, group_name, None)
            if group:
                group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                group.setMaximumHeight(_ui_escalar_px(64, minimo=64))
            layout = getattr(self.ui, layout_name, None)
            if layout:
                layout.setContentsMargins(
                    _ui_escalar_px(4, minimo=4),
                    _ui_escalar_px(4, minimo=4),
                    _ui_escalar_px(4, minimo=4),
                    _ui_escalar_px(4, minimo=4),
                )
                layout.setSpacing(_ui_escalar_px(4, minimo=4))

        if hasattr(self.ui, "accionesCocheraLayout"):
            acciones = [
                "btn_mapa_cocheras",
                "btn_clientes",
                "btn_contratos",
                "btn_reportes",
                "btn_vencimientos",
            ]
            for i, name in enumerate(acciones):
                btn = getattr(self.ui, name, None)
                if not btn:
                    continue
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                self.ui.accionesCocheraLayout.setStretch(i, 1)
            if hasattr(self.ui, "accionesCocheraSpacer"):
                self.ui.accionesCocheraLayout.removeItem(self.ui.accionesCocheraSpacer)

        if hasattr(self.ui, "fechaHoraLayout"):
            self.ui.fechaHoraLayout.setSpacing(_ui_escalar_px(4, minimo=4))

        if hasattr(self.ui, "cocheraLayout"):
            self.ui.cocheraLayout.addStretch(1)

        self._configurar_iconos_acciones()

    def _configurar_iconos_acciones(self):
        iconos = {
            "btn_modo_sencillo": (
                ["preferences-system", "applications-system", "system-run"],
                QStyle.SP_ComputerIcon,
            ),
            "btn_mapa_cocheras": (
                ["map", "view-grid", "folder"],
                QStyle.SP_DirOpenIcon,
            ),
            "btn_clientes": (
                ["user", "users", "contact-new"],
                QStyle.SP_DirHomeIcon,
            ),
            "btn_contratos": (
                ["document", "text-x-generic", "file"],
                QStyle.SP_FileIcon,
            ),
            "btn_reportes": (
                ["view-statistics", "chart", "report"],
                QStyle.SP_FileDialogDetailedView,
            ),
            "btn_reportes_est": (
                ["view-statistics", "chart", "report"],
                QStyle.SP_FileDialogDetailedView,
            ),
            "btn_vencimientos": (
                ["dialog-warning", "warning", "alarm"],
                QStyle.SP_MessageBoxWarning,
            ),
        }

        estilo = self.style()
        for nombre, (temas, fallback) in iconos.items():
            btn = getattr(self.ui, nombre, None)
            if not btn:
                continue
            icono = QIcon()
            for tema in temas:
                icono = QIcon.fromTheme(tema)
                if not icono.isNull():
                    break
            if icono.isNull():
                icono = estilo.standardIcon(fallback)
            btn.setIcon(icono)
            btn.setIconSize(QSize(16, 16))

    def _configurar_menus(self):
        self.menu_admin = self.ui.menubar.addMenu("Administracion")
        self.action_configuracion = QAction("Configuracion", self)
        self.ui.menubar.addAction(self.action_configuracion)
        self.action_usuarios = QAction("Usuarios", self)
        self.action_tarifas = QAction("Tarifas", self)
        self.action_historial = QAction("Historial", self)
        self.action_cierre_caja = QAction("Cierre de caja", self)
        self.action_reset_cero = QAction("Restablecer a 0", self)
        self.menu_admin.addAction(self.action_usuarios)
        self.menu_admin.addAction(self.action_tarifas)
        self.menu_admin.addAction(self.action_historial)
        self.menu_admin.addAction(self.action_cierre_caja)
        self.menu_admin.addSeparator()
        self.menu_admin.addAction(self.action_reset_cero)
        self.action_usuarios.triggered.connect(self._abrir_usuarios)
        self.action_tarifas.triggered.connect(self._abrir_tarifas)
        self.action_historial.triggered.connect(self._abrir_historial)
        self.action_cierre_caja.triggered.connect(self._abrir_cierre_caja)
        self.action_reset_cero.triggered.connect(self._restaurar_base)
        self.action_configuracion.triggered.connect(self._abrir_configuracion)

    def _aplicar_rol(self):
        rol = (self.rol or "").upper()
        es_admin = rol == "DUENO"
        es_operador = rol == "OPERADOR"
        self.menu_admin.menuAction().setVisible(es_admin or es_operador)
        self.action_usuarios.setVisible(es_admin)
        self.action_tarifas.setVisible(es_admin)
        self.action_historial.setVisible(es_admin or es_operador)
        self.action_cierre_caja.setVisible(es_admin or es_operador)
        self.action_reset_cero.setVisible(es_admin)
        self.action_configuracion.setVisible(es_admin or es_operador)
        self.action_usuarios.setEnabled(es_admin)
        self.action_tarifas.setEnabled(es_admin)
        self.action_historial.setEnabled(es_admin or es_operador)
        self.action_cierre_caja.setEnabled(es_admin or es_operador)
        self.action_reset_cero.setEnabled(es_admin)
        self.action_configuracion.setEnabled(es_admin or es_operador)
        self._aplicar_restricciones_ui(es_admin, es_operador)
        if self.usuario:
            self.statusBar().showMessage(f"Usuario: {self.usuario} ({rol})")
        elif rol:
            self.statusBar().showMessage(f"Rol: {rol}")

    def _aplicar_restricciones_ui(self, es_admin, es_operador):
        self.ui.card_ingresos.setVisible(es_admin)
        self.ui.btn_vencimientos.setVisible(es_admin)
        self.ui.btn_reportes.setVisible(es_admin)
        if hasattr(self.ui, "btn_reportes_est"):
            self.ui.btn_reportes_est.setVisible(es_admin)
        self.ui.btn_mapa_cocheras.setVisible(es_admin or es_operador)
        self.ui.btn_contratos.setVisible(True)
        self.ui.btn_clientes.setVisible(True)
        self.ui.btn_mapa_est.setVisible(es_admin or es_operador)

    def _abrir_tarifas(self):
        if (self.rol or "").strip().upper() != "DUENO":
            QMessageBox.warning(
                self,
                "Administracion",
                "Solo un usuario DUENO puede abrir Tarifas.",
            )
            return
        dlg = TarifaDialog(self)
        dlg.exec()
        self._programar_popup_primeros_pasos()

    def _abrir_usuarios(self):
        if (self.rol or "").strip().upper() != "DUENO":
            QMessageBox.warning(
                self,
                "Administracion",
                "Solo un usuario DUENO puede abrir Usuarios.",
            )
            return
        dlg = UsuariosDialog(self, usuario_actual=self.usuario)
        dlg.exec()

    def _abrir_historial(self):
        if (self.rol or "").strip().upper() not in {"DUENO", "OPERADOR"}:
            QMessageBox.warning(
                self,
                "Administracion",
                "Tu usuario no tiene permisos para abrir Historial.",
            )
            return
        dlg = HistorialDialog(self)
        dlg.exec()

    def _abrir_cierre_caja(self):
        if (self.rol or "").strip().upper() not in {"DUENO", "OPERADOR"}:
            QMessageBox.warning(
                self,
                "Administracion",
                "Tu usuario no tiene permisos para abrir Cierre de caja.",
            )
            return
        dlg = CajaDiariaDialog(self)
        dlg.exec()

    def _abrir_backups(self):
        dlg = BackupsDialog(self)
        dlg.exec()

    def _abrir_configuracion(self):
        if (self.rol or "").strip().upper() not in {"DUENO", "OPERADOR"}:
            QMessageBox.warning(
                self,
                "Administracion",
                "Tu usuario no tiene permisos para abrir Configuracion.",
            )
            return
        dlg = ConfiguracionDialog(self, rol=self.rol)
        if dlg.exec() == QDialog.Accepted:
            self._aplicar_preferencias_ui()
            self._actualizar_tipos_estacionamiento_ui()
        self._programar_popup_primeros_pasos()

    def _ejecutar_tests(self):
        base_dir = Path(__file__).resolve().parent
        tests_dir = base_dir / "tests"
        if not tests_dir.exists():
            QMessageBox.warning(self, "Tests", "No existe la carpeta de tests.")
            return

        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(base_dir),
                capture_output=True,
                text=True,
                timeout=180,
            )
        except Exception:
            _mostrar_error(self, "Tests", "No se pudieron ejecutar los tests.")
            return

        salida = (proc.stdout or "").strip()
        errores = (proc.stderr or "").strip()
        detalle = "\n".join([s for s in (salida, errores) if s]).strip()
        lineas = [ln.strip() for ln in detalle.splitlines() if ln.strip()]
        resumen = ""
        for ln in reversed(lineas):
            if ln.startswith("Ran ") or ln == "OK" or ln.startswith("FAILED"):
                resumen = ln if not resumen else f"{ln} | {resumen}"
                if ln.startswith("Ran "):
                    break
        if not resumen:
            resumen = "Ejecucion finalizada."

        if proc.returncode == 0:
            titulo = "Tests"
            texto = f"Tests OK.\n{resumen}"
            icono = QMessageBox.Information
        else:
            titulo = "Tests"
            texto = f"Hay fallas en tests.\n{resumen}"
            icono = QMessageBox.Warning

        box = QMessageBox(self)
        box.setIcon(icono)
        box.setWindowTitle(titulo)
        box.setText(texto)
        if detalle:
            box.setDetailedText(detalle[-12000:])
        box.exec()
        _auditar(self, "Ejecucion de tests", f"returncode={proc.returncode} - {resumen}")

    def _probar_error(self):
        _mostrar_error(self, "Error simulado", "Este es un ejemplo de error.")

    def _restaurar_base(self):
        confirmar = QMessageBox.question(
            self,
            "Restablecer a 0",
            "Esto eliminara TODOS los datos del sistema: usuarios, clientes, patentes,\n"
            "contratos, movimientos, pagos, tarifas, configuracion e historial.\n\n"
            "Antes se intentara crear un respaldo automatico.\n"
            "Esta accion no se puede deshacer. Continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmar != QMessageBox.Yes:
            return

        texto, ok = QInputDialog.getText(
            self,
            "Confirmacion final",
            "Escribe BORRAR TODO para dejar la app desde cero:",
        )
        if not ok or texto.strip().upper() != "BORRAR TODO":
            QMessageBox.information(
                self,
                "Restablecer a 0",
                "Operacion cancelada. No se realizo ningun cambio.",
            )
            return

        respaldo_ok = True
        try:
            svc_crear_backup_db(max_backups=30)
        except Exception:
            respaldo_ok = False

        if not respaldo_ok:
            seguir = QMessageBox.question(
                self,
                "Respaldo no disponible",
                "No se pudo crear el respaldo automatico.\n"
                "Si continuas, los datos se borraran igual.\n\n"
                "Quieres seguir de todos modos?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if seguir != QMessageBox.Yes:
                return

        try:
            reset_db()
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo restablecer la base a cero.")
            return

        _auditar(self, "Base restablecida a 0", "Limpieza total de tablas.")
        QMessageBox.information(
            self,
            "Restablecer a 0",
            "La base se limpio correctamente.\n"
            "La aplicacion se cerrara para iniciar desde cero.",
        )
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)

    def _configurar_modos(self):
        if hasattr(self.ui, "modeButtonsLayout") and not hasattr(self.ui, "btn_modo_sencillo"):
            self.ui.btn_modo_sencillo = QPushButton(self.centralWidget())
            self.ui.btn_modo_sencillo.setObjectName("btn_modo_sencillo")
            self.ui.btn_modo_sencillo.setProperty("variant", "neutral")
            self.ui.modeButtonsLayout.addWidget(self.ui.btn_modo_sencillo)
        self.ui.stack.setCurrentIndex(0)
        self._aplicar_textos_botones_atajos()
        self._aplicar_tooltips_botones_principales()
        self.ui.btn_cochera.clicked.connect(lambda: self.ui.stack.setCurrentIndex(0))
        self.ui.btn_estacionamiento.clicked.connect(self._abrir_menu_estacionamiento)
        if hasattr(self.ui, "btn_modo_sencillo"):
            self.ui.btn_modo_sencillo.clicked.connect(self._abrir_modo_sencillo_estacionamiento)
        self.ui.btn_vencimientos.clicked.connect(self._abrir_vencimientos)
        self.ui.btn_reportes.clicked.connect(lambda: self._abrir_reportes("Cochera"))
        if hasattr(self.ui, "btn_reportes_est"):
            self.ui.btn_reportes_est.clicked.connect(
                lambda: self._abrir_reportes("Estacionamiento")
            )
        self.ui.btn_mapa_cocheras.clicked.connect(self._abrir_mapa_cocheras)
        self.ui.btn_contratos.clicked.connect(self._abrir_contratos)
        self.ui.btn_clientes.clicked.connect(self._abrir_clientes)
        self.ui.btn_mapa_est.clicked.connect(self._abrir_mapa_cocheras)
        self._actualizar_estado_menu_estacionamiento()

    def _aplicar_textos_botones_atajos(self):
        textos = {
            "btn_cochera": "Cochera (F1)",
            "btn_estacionamiento": "Estacionamiento (F2)",
            "btn_modo_sencillo": "Modo sencillo",
            "btn_mapa_cocheras": "Mapa de cocheras (F5)",
            "btn_clientes": "Clientes (F6)",
            "btn_contratos": "Contratos (F7)",
            "btn_reportes": "Reportes (F8)",
            "btn_reportes_est": "Reportes (F8)",
            "btn_mapa_est": "Mapa de cocheras (F5)",
            "btn_ingreso_est": "Registrar ingreso (F9)",
            "btn_salida_est": "Registrar salida (F10)",
        }
        for nombre, texto in textos.items():
            btn = getattr(self.ui, nombre, None)
            if btn is not None:
                btn.setText(texto)

    def _tooltips_botones_principales(self):
        return {
            "btn_cochera": (
                "Abre el modo Cochera.\n"
                "Aqui ves el resumen general y accedes a mapa, clientes, contratos, reportes y vencimientos.\n"
                "Atajo: F1."
            ),
            "btn_estacionamiento": (
                "Abre el modo Estacionamiento.\n"
                "Aqui registras ingresos y salidas por hora, cobras al confirmar la salida y ves los vehiculos activos.\n"
                "Atajo: F2."
            ),
            "btn_modo_sencillo": (
                "Abre una version simplificada solo para Estacionamiento.\n"
                "Muestra botones grandes para ingreso rapido, salida rapida y consulta de vehiculos activos."
            ),
            "btn_mapa_cocheras": (
                "Abre el mapa de espacios.\n"
                "Aqui creas, ordenas y editas los lugares de cochera y estacionamiento.\n"
                "Atajo: F5."
            ),
            "btn_clientes": (
                "Abre Clientes y vehiculos.\n"
                "Aqui cargas clientes, DNI, telefono, patentes, modelos y accesos rapidos como WhatsApp.\n"
                "Atajo: F6."
            ),
            "btn_contratos": (
                "Abre Contratos.\n"
                "Aqui creas contratos, registras pagos, das de baja, envias comprobantes y consultas historial.\n"
                "Atajo: F7."
            ),
            "btn_reportes": (
                "Abre Reportes con filtro inicial en Cochera.\n"
                "Aqui revisas historial de cobros, totales y exportas la informacion a Excel.\n"
                "Atajo: F8."
            ),
            "btn_reportes_est": (
                "Abre Reportes con filtro inicial en Estacionamiento.\n"
                "Aqui revisas cobros por hora, historial y exportas la informacion a Excel.\n"
                "Atajo: F8."
            ),
            "btn_vencimientos": (
                "Abre Vencimientos de contratos.\n"
                "Aqui ves contratos vencidos o proximos a vencer y puedes enviar recordatorios por WhatsApp."
            ),
            "btn_mapa_est": (
                "Abre el mapa de espacios.\n"
                "Aqui defines los lugares que usara el modo Estacionamiento.\n"
                "Atajo: F5."
            ),
            "btn_ingreso_est": (
                "Registra un nuevo ingreso en estacionamiento.\n"
                "Aqui guardas patente, espacio y tipo de vehiculo.\n"
                "Atajo: F9."
            ),
            "btn_salida_est": (
                "Registra la salida de un vehiculo.\n"
                "Aqui calculas el cobro final, eliges el metodo de pago, generas el ticket y liberas el espacio.\n"
                "Atajo: F10."
            ),
        }

    def _aplicar_tooltips_botones_principales(self):
        for nombre, tooltip in self._tooltips_botones_principales().items():
            btn = getattr(self.ui, nombre, None)
            if btn is not None:
                btn.setToolTip(tooltip)

    def _configurar_atajos(self):
        # Mantener referencias para que los QShortcut no se liberen por GC.
        self._atajos_funciones = []

        def add(seq, fn):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(fn)
            self._atajos_funciones.append(sc)

        add("F1", self._atajo_menu_cochera)
        add("F2", self._atajo_menu_estacionamiento)
        add("F5", self._abrir_mapa_cocheras)
        add("F6", self._atajo_f6)
        add("F7", self._atajo_f7)
        add("F8", self._atajo_f8)
        add("F9", self._atajo_f9)
        add("F10", self._atajo_f10)

    def _en_menu_cochera(self):
        return getattr(self.ui, "stack", None) is not None and self.ui.stack.currentIndex() == 0

    def _en_menu_estacionamiento(self):
        return getattr(self.ui, "stack", None) is not None and self.ui.stack.currentIndex() == 1

    def _estado_menu_estacionamiento(self):
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM espacios "
                "WHERE activo = 1 AND COALESCE(es_reservado, 0) = 0 "
                "AND id_cliente IS NULL"
            )
            total = int(cur.fetchone()[0] or 0)
            if total > 0:
                return True, ""
            return (
                False,
                "No puedes entrar a Estacionamiento porque el mapa no tiene espacios de estacionamiento.\n"
                "Crea al menos uno desde Mapa antes de usar este menu.",
            )
        except sqlite3.Error:
            return True, ""
        finally:
            if conn:
                conn.close()

    def _actualizar_estado_menu_estacionamiento(self):
        disponible, mensaje = self._estado_menu_estacionamiento()
        aviso_bloqueo = (
            "Bloqueado por ahora:\n"
            "Primero crea al menos un espacio de estacionamiento en el mapa."
        )
        if hasattr(self.ui, "btn_estacionamiento"):
            tooltip_base = self._tooltips_botones_principales().get(
                "btn_estacionamiento", ""
            )
            if disponible:
                self.ui.btn_estacionamiento.setToolTip(tooltip_base)
            else:
                self.ui.btn_estacionamiento.setToolTip(f"{tooltip_base}\n\n{aviso_bloqueo}")
        if hasattr(self.ui, "btn_modo_sencillo"):
            tooltip_base = self._tooltips_botones_principales().get(
                "btn_modo_sencillo", ""
            )
            if disponible:
                self.ui.btn_modo_sencillo.setToolTip(tooltip_base)
            else:
                self.ui.btn_modo_sencillo.setToolTip(f"{tooltip_base}\n\n{aviso_bloqueo}")
        if not disponible and self._en_menu_estacionamiento():
            self.ui.stack.setCurrentIndex(0)
        return disponible, mensaje

    def _abrir_menu_estacionamiento(self, popup_parent=None):
        if getattr(self.ui, "stack", None) is None:
            return False
        disponible, mensaje = self._actualizar_estado_menu_estacionamiento()
        if not disponible:
            QMessageBox.warning(popup_parent or self, "Estacionamiento", mensaje)
            return False
        self.ui.stack.setCurrentIndex(1)
        return True

    def _abrir_modo_sencillo_estacionamiento(self):
        disponible, mensaje = self._actualizar_estado_menu_estacionamiento()
        if not disponible:
            QMessageBox.warning(self, "Modo sencillo", mensaje)
            return
        dlg_existente = getattr(self, "_modo_sencillo_dialog", None)
        if dlg_existente is not None and dlg_existente.isVisible():
            dlg_existente.raise_()
            dlg_existente.activateWindow()
            return
        self._modo_sencillo_dialog = ModoSencilloEstacionamientoDialog(self)
        self.hide()
        self._modo_sencillo_dialog.show()
        self._modo_sencillo_dialog.raise_()
        self._modo_sencillo_dialog.activateWindow()

    def _restaurar_desde_modo_sencillo(self, dialog=None):
        dlg = getattr(self, "_modo_sencillo_dialog", None)
        if dialog is not None and dlg is dialog:
            self._modo_sencillo_dialog = None
        elif dlg is not None and not dlg.isVisible():
            self._modo_sencillo_dialog = None
        if not self.isVisible():
            self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _atajo_menu_cochera(self):
        if getattr(self.ui, "stack", None) is None:
            return
        self.ui.stack.setCurrentIndex(0)

    def _atajo_menu_estacionamiento(self):
        self._abrir_menu_estacionamiento()
        if hasattr(self.ui, "input_patente_est"):
            if self._en_menu_estacionamiento():
                self.ui.input_patente_est.setFocus()
                self.ui.input_patente_est.selectAll()

    def _atajo_f6(self):
        if self._en_menu_cochera():
            self._abrir_clientes()
        elif self._en_menu_estacionamiento() and hasattr(self.ui, "input_patente_est"):
            self.ui.input_patente_est.setFocus()
            self.ui.input_patente_est.selectAll()

    def _atajo_f7(self):
        if self._en_menu_cochera():
            self._abrir_contratos()
        elif self._en_menu_estacionamiento() and hasattr(self.ui, "input_espacio_est"):
            self.ui.input_espacio_est.setFocus()
            self.ui.input_espacio_est.selectAll()

    def _atajo_f8(self):
        if self._en_menu_cochera():
            self._abrir_reportes("Cochera")
        elif self._en_menu_estacionamiento():
            self._abrir_reportes("Estacionamiento")

    def _cambiar_metodo_pago_tab(self, retroceder=False):
        combo = getattr(self.ui, "combo_metodo_est", None)
        if combo is None:
            return
        count = int(combo.count() or 0)
        if count <= 0:
            return
        idx = int(combo.currentIndex() or 0)
        paso = -1 if retroceder else 1
        combo.setCurrentIndex((idx + paso) % count)
        if combo.hasFocus():
            combo.showPopup()

    def eventFilter(self, obj, event):
        combo = getattr(self.ui, "combo_metodo_est", None)
        if combo is not None and event.type() == QEvent.KeyPress:
            es_objetivo = obj is combo
            try:
                es_objetivo = es_objetivo or obj is combo.view()
            except Exception:
                pass
            if es_objetivo:
                tecla = int(event.key() or 0)
                if tecla in (int(Qt.Key_Tab), int(Qt.Key_Backtab)):
                    retroceder = tecla == int(Qt.Key_Backtab) or bool(
                        event.modifiers() & Qt.ShiftModifier
                    )
                    self._cambiar_metodo_pago_tab(retroceder=retroceder)
                    return True
        return super().eventFilter(obj, event)

    def _atajo_f9(self):
        if self._en_menu_estacionamiento():
            self._registrar_ingreso_est()

    def _atajo_f10(self):
        if self._en_menu_estacionamiento():
            self._registrar_salida_est()

    def _log_estacionamiento(
        self,
        mensaje,
        nivel="info",
        mostrar_popup=True,
        popup_parent=None,
        detalle=None,
    ):
        self.ui.label_resultado_est.setText(mensaje)
        if not mostrar_popup or not mensaje:
            return
        titulo = "Estacionamiento"
        nivel_norm = (nivel or "info").lower()
        parent = popup_parent or self
        if nivel_norm == "error":
            _mostrar_error(parent, titulo, mensaje, detalle=detalle)
        elif nivel_norm == "warn":
            QMessageBox.warning(parent, titulo, mensaje)
        else:
            QMessageBox.information(parent, titulo, mensaje)

    def _configurar_estacionamiento(self):
        if hasattr(self.ui, "est_form_layout") and not hasattr(self.ui, "combo_tipo_vehiculo_est"):
            self.ui.label_est_tipo_vehiculo = QLabel("Tipo vehiculo", self.ui.group_est_registro)
            self.ui.combo_tipo_vehiculo_est = QComboBox(self.ui.group_est_registro)
            self.ui.est_form_layout.insertRow(
                2,
                self.ui.label_est_tipo_vehiculo,
                self.ui.combo_tipo_vehiculo_est,
            )

        if hasattr(self.ui, "combo_metodo_est") and self.ui.combo_metodo_est.findText("QR") < 0:
            self.ui.combo_metodo_est.addItem("QR")
        if hasattr(self.ui, "label_est_metodo"):
            self.ui.label_est_metodo.setVisible(False)
        if hasattr(self.ui, "combo_metodo_est"):
            self.ui.combo_metodo_est.setVisible(False)

        if hasattr(self.ui, "input_patente_est"):
            self.ui.input_patente_est.setMaxLength(10)
            self.ui.input_patente_est.setValidator(
                QRegularExpressionValidator(
                    QRegularExpression(r"[A-Za-z0-9\s]{0,10}"),
                    self.ui.input_patente_est,
                )
            )
            self.ui.input_patente_est.editingFinished.connect(
                self._formatear_input_patente_est
            )

        self.ui.btn_ingreso_est.clicked.connect(self._registrar_ingreso_est)
        self.ui.btn_salida_est.clicked.connect(self._registrar_salida_est)
        self.ui.input_espacio_est.editingFinished.connect(self._validar_espacio_est)
        enter_map_est = {}
        if hasattr(self.ui, "input_patente_est") and hasattr(self.ui, "input_espacio_est"):
            enter_map_est[self.ui.input_patente_est] = self.ui.input_espacio_est
        if hasattr(self.ui, "input_espacio_est"):
            if hasattr(self.ui, "combo_tipo_vehiculo_est"):
                enter_map_est[self.ui.input_espacio_est] = self.ui.combo_tipo_vehiculo_est
            elif hasattr(self.ui, "btn_ingreso_est"):
                enter_map_est[self.ui.input_espacio_est] = ("click", self.ui.btn_ingreso_est)
        if hasattr(self.ui, "combo_tipo_vehiculo_est") and hasattr(self.ui, "btn_ingreso_est"):
            enter_map_est[self.ui.combo_tipo_vehiculo_est] = ("click", self.ui.btn_ingreso_est)
        if enter_map_est:
            _instalar_enter_navegacion(self, enter_map_est)
        self._activos_est_cache = []
        self._configurar_tabla_est_activos()
        self._configurar_filtros_est_activos()
        table = self.ui.table_est_activos
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._menu_contextual_est_activos)
        table.cellClicked.connect(self._cargar_datos_tabla_est_activos)
        self.ui.card_est_hora.setVisible(False)
        self._actualizar_tipos_estacionamiento_ui()
        self._actualizar_activos_est()
        self._est_timer = QTimer(self)
        self._est_timer.timeout.connect(self._actualizar_activos_est)
        self._est_timer.start(5000)

    def _actualizar_tipos_estacionamiento_ui(self):
        combo = getattr(self.ui, "combo_tipo_vehiculo_est", None)
        if combo is None:
            return
        tipos = _tipos_vehiculo_config_estacionamiento()
        actual = combo.currentData()
        if actual is None:
            actual = combo.currentText()
        actual = _normalizar_tipo_vehiculo(actual) if str(actual or "").strip() else ""
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Seleccionar tipo...", "")
        for texto, codigo in tipos:
            combo.addItem(texto, codigo)
        combo.setEnabled(bool(tipos))
        if tipos:
            idx = combo.findData(actual)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.setToolTip(
                "Selecciona el tipo de vehiculo antes de registrar el ingreso."
            )
        else:
            combo.setToolTip(
                "No hay tipos de vehiculo habilitados en Configuracion > Sistema."
            )
        combo.blockSignals(False)
        if hasattr(self.ui, "btn_ingreso_est"):
            self.ui.btn_ingreso_est.setEnabled(bool(tipos))
            self.ui.btn_ingreso_est.setToolTip(
                ""
                if tipos
                else "No hay tipos de vehiculo habilitados para estacionamiento."
            )

    def _resetear_tipo_vehiculo_est(self):
        combo = getattr(self.ui, "combo_tipo_vehiculo_est", None)
        if combo is None or combo.count() <= 0:
            return
        combo.setCurrentIndex(0)

    def _metodos_pago_est(self):
        combo = getattr(self.ui, "combo_metodo_est", None)
        if combo is None:
            return ["Efectivo", "Tarjeta", "Transferencia", "QR"]
        metodos = [
            combo.itemText(i).strip()
            for i in range(combo.count())
            if combo.itemText(i).strip()
        ]
        return metodos or ["Efectivo", "Tarjeta", "Transferencia", "QR"]

    def _solicitar_metodo_pago_est(self, total=0.0, popup_parent=None):
        metodos = self._metodos_pago_est()
        combo = getattr(self.ui, "combo_metodo_est", None)
        actual = (combo.currentText() or "").strip() if combo is not None else ""
        if actual not in metodos:
            actual = metodos[0]
        idx_actual = metodos.index(actual) if actual in metodos else 0
        metodo, ok = QInputDialog.getItem(
            popup_parent or self,
            "Metodo de pago",
            "Selecciona el metodo de pago para esta salida.\n"
            f"Total: {_fmt_money(total)}",
            metodos,
            idx_actual,
            False,
        )
        metodo = str(metodo or "").strip()
        if not ok or not metodo:
            return ""
        if combo is not None:
            idx = combo.findText(metodo, Qt.MatchExactly)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        return metodo

    def _tipo_vehiculo_est_db(self):
        combo = getattr(self.ui, "combo_tipo_vehiculo_est", None)
        if combo is None:
            return ""
        valor = combo.currentData()
        if valor is None:
            valor = combo.currentText()
        if not str(valor or "").strip():
            return ""
        return _normalizar_tipo_vehiculo(valor)

    def _configurar_tabla_est_activos(self):
        table = self.ui.table_est_activos
        table.setColumnCount(6)
        headers = ["Patente", "Espacio", "Ingreso", "Patente", "Espacio", "Ingreso"]
        for i, texto in enumerate(headers):
            item = table.horizontalHeaderItem(i)
            if item is None:
                item = QTableWidgetItem()
                table.setHorizontalHeaderItem(i, item)
            item.setText(texto)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setStretchLastSection(False)

    def _configurar_filtros_est_activos(self):
        if hasattr(self, "_input_filtro_est_activos"):
            return

        barra = QHBoxLayout()
        barra.addWidget(QLabel("Filtro"))
        self._input_filtro_est_activos = QLineEdit(self.ui.group_est_activos)
        self._input_filtro_est_activos.setPlaceholderText("Patente o espacio")
        self._input_filtro_est_activos.setMinimumWidth(220)
        self._input_filtro_est_activos.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        barra.addWidget(self._input_filtro_est_activos, 2)

        barra.addWidget(QLabel("Orden"))
        self._combo_orden_est_activos = QComboBox(self.ui.group_est_activos)
        self._combo_orden_est_activos.addItem("Ingreso mas reciente", "newest")
        self._combo_orden_est_activos.addItem("Ingreso mas antiguo", "oldest")
        self._combo_orden_est_activos.addItem("Patente A-Z", "plate_asc")
        self._combo_orden_est_activos.addItem("Patente Z-A", "plate_desc")
        self._combo_orden_est_activos.setMinimumWidth(180)
        barra.addWidget(self._combo_orden_est_activos)
        barra.addStretch(1)

        self.ui.est_activos_layout.insertLayout(0, barra)
        self._input_filtro_est_activos.textChanged.connect(self._aplicar_filtros_activos_est)
        self._combo_orden_est_activos.currentIndexChanged.connect(
            self._aplicar_filtros_activos_est
        )

    def _filtrar_ordenar_activos_est(self, filas):
        filas_norm = [
            {
                "id_movimiento": row.get("id_movimiento"),
                "patente": (row["patente"] or ""),
                "codigo": (row["codigo"] or ""),
                "fecha_ingreso": (row["fecha_ingreso"] or ""),
            }
            for row in (filas or [])
        ]

        texto = ""
        if hasattr(self, "_input_filtro_est_activos"):
            texto = self._input_filtro_est_activos.text().strip().lower()
        if texto:
            filas_norm = [
                row
                for row in filas_norm
                if texto in row["patente"].lower() or texto in row["codigo"].lower()
            ]

        modo = "newest"
        if hasattr(self, "_combo_orden_est_activos"):
            modo = self._combo_orden_est_activos.currentData() or "newest"

        if modo == "oldest":
            filas_norm.sort(
                key=lambda r: _parse_fecha_db(r["fecha_ingreso"]) or datetime.min
            )
        elif modo == "plate_asc":
            filas_norm.sort(key=lambda r: r["patente"])
        elif modo == "plate_desc":
            filas_norm.sort(key=lambda r: r["patente"], reverse=True)
        else:
            filas_norm.sort(
                key=lambda r: _parse_fecha_db(r["fecha_ingreso"]) or datetime.min,
                reverse=True,
            )
        return filas_norm

    def _render_activos_est(self, filas):
        table = self.ui.table_est_activos
        table.clearContents()
        total = len(filas)
        if total <= 0:
            table.setRowCount(1)
            texto_filtro = ""
            if hasattr(self, "_input_filtro_est_activos"):
                texto_filtro = self._input_filtro_est_activos.text().strip()
            mensaje = (
                "No hay vehiculos activos que coincidan con el filtro actual."
                if texto_filtro
                else "No hay vehiculos activos en este momento."
            )
            item = QTableWidgetItem(mensaje)
            item.setFlags(Qt.NoItemFlags)
            table.setSpan(0, 0, 1, table.columnCount())
            table.setItem(0, 0, item)
            return
        filas_por_col = (total + 1) // 2
        table.setRowCount(filas_por_col)
        for idx, row in enumerate(filas):
            col_offset = 0 if idx < filas_por_col else 3
            r = idx if idx < filas_por_col else idx - filas_por_col
            patente_mostrar = _formatear_patente_estacionamiento(row["patente"])
            items = [
                QTableWidgetItem(patente_mostrar),
                QTableWidgetItem(row["codigo"]),
                QTableWidgetItem(_fmt_fecha_hora_local(row["fecha_ingreso"])),
            ]
            for idx_item, item in enumerate(items):
                item.setData(Qt.UserRole, row.get("id_movimiento"))
                table.setItem(r, col_offset + idx_item, item)

    def _aplicar_filtros_activos_est(self):
        filas = self._filtrar_ordenar_activos_est(self._activos_est_cache)
        self._render_activos_est(filas)

    def _patente_desde_tabla_est(self, row, column):
        table = self.ui.table_est_activos
        if row < 0 or column < 0:
            return ""
        col_base = 0 if column < 3 else 3
        item_patente = table.item(row, col_base)
        if item_patente and item_patente.text().strip():
            return item_patente.text().strip().upper()
        return ""

    def _formatear_input_patente_est(self):
        if not hasattr(self.ui, "input_patente_est"):
            return
        texto = self.ui.input_patente_est.text()
        if not texto:
            return
        patente_fmt = _formatear_patente_estacionamiento(texto)
        self.ui.input_patente_est.setText(patente_fmt)

    def _espacio_desde_tabla_est(self, row, column):
        table = self.ui.table_est_activos
        if row < 0 or column < 0:
            return ""
        col_base = 0 if column < 3 else 3
        item_espacio = table.item(row, col_base + 1)
        if item_espacio and item_espacio.text().strip():
            return item_espacio.text().strip().upper()
        return ""

    def _movimiento_id_desde_tabla_est(self, row, column):
        table = self.ui.table_est_activos
        if row < 0 or column < 0:
            return None
        col_base = 0 if column < 3 else 3
        item_patente = table.item(row, col_base)
        if item_patente is None:
            return None
        valor = item_patente.data(Qt.UserRole)
        try:
            return int(valor or 0) or None
        except (TypeError, ValueError):
            return None

    def _movimiento_activo_seleccionado_est(self):
        table = self.ui.table_est_activos
        item = table.currentItem()
        if item is not None:
            row = item.row()
            column = item.column()
            return (
                self._movimiento_id_desde_tabla_est(row, column),
                self._patente_desde_tabla_est(row, column),
                self._espacio_desde_tabla_est(row, column),
            )

        input_patente = getattr(self.ui, "input_patente_est", None)
        patente = _normalizar_patente(input_patente.text() if input_patente is not None else "")
        if not patente:
            return None, "", ""

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            row = self._buscar_movimiento_activo_por_patente(cur, patente)
            if not row:
                return None, _formatear_patente_estacionamiento(patente), ""
            return (
                int(row["id_movimiento"] or 0) or None,
                _formatear_patente_estacionamiento(patente),
                (row["codigo"] or "").strip().upper(),
            )
        except sqlite3.Error:
            return None, _formatear_patente_estacionamiento(patente), ""
        finally:
            if conn:
                conn.close()

    def _cargar_datos_tabla_est_activos(self, row, column):
        patente = self._patente_desde_tabla_est(row, column)
        espacio = self._espacio_desde_tabla_est(row, column)
        if patente:
            self.ui.input_patente_est.setText(patente)
        if espacio:
            self.ui.input_espacio_est.setText(espacio)

    def _menu_contextual_est_activos(self, pos):
        table = self.ui.table_est_activos
        item = table.itemAt(pos)
        if not item:
            return
        patente = self._patente_desde_tabla_est(item.row(), item.column())
        espacio = self._espacio_desde_tabla_est(item.row(), item.column())
        movimiento_id = self._movimiento_id_desde_tabla_est(item.row(), item.column())
        if not patente:
            return
        table.selectRow(item.row())
        menu = QMenu(self)
        accion_salida = menu.addAction("Registrar salida")
        elegido = menu.exec(table.viewport().mapToGlobal(pos))
        if elegido == accion_salida:
            self.ui.input_patente_est.setText(patente)
            if espacio:
                self.ui.input_espacio_est.setText(espacio)
            self._registrar_salida_est()

    def _validar_espacio_est(self):
        codigo = self.ui.input_espacio_est.text().strip().upper()
        if not codigo:
            return
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT es_reservado, id_cliente FROM espacios WHERE codigo = ? AND activo = 1",
                (codigo,),
            )
            row = cur.fetchone()
            if row and (row["es_reservado"] == 1 or row["id_cliente"] is not None):
                self._log_estacionamiento(
                    "Ese espacio es de cochera (mensual).",
                    "warn",
                )
                self.ui.input_espacio_est.clear()
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()

    def _eliminar_ingreso_est(self):
        if (self.rol or "").strip().upper() != "DUENO":
            QMessageBox.warning(
                self,
                "Estacionamiento",
                "Solo DUENO puede eliminar ingresos desde Estacionamiento.",
            )
            return

        movimiento_id, patente, espacio = self._movimiento_activo_seleccionado_est()
        if not movimiento_id:
            QMessageBox.warning(
                self,
                "Estacionamiento",
                "Selecciona un vehiculo activo o escribe su patente para eliminar el ingreso.",
            )
            return

        texto = (
            "Esto eliminara el ingreso activo sin registrar salida ni cobro.\n"
            "Usalo solo si el ingreso fue cargado por error.\n\n"
            f"Patente: {patente or '-'}\n"
            f"Espacio: {espacio or '-'}"
        )
        confirmar = QMessageBox.question(
            self,
            "Eliminar ingreso",
            texto,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmar != QMessageBox.Yes:
            return

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT id_vehiculo FROM movimientos WHERE id_movimiento = ? AND fecha_salida IS NULL",
                (movimiento_id,),
            )
            row = cur.fetchone()
            if not row:
                QMessageBox.warning(
                    self,
                    "Eliminar ingreso",
                    "Ese ingreso ya no esta activo.\nActualiza la lista e intentalo de nuevo.",
                )
                return

            id_vehiculo = int(row["id_vehiculo"] or 0) or None
            cur.execute("DELETE FROM pagos WHERE id_movimiento = ?", (movimiento_id,))
            cur.execute("DELETE FROM movimientos WHERE id_movimiento = ?", (movimiento_id,))

            if id_vehiculo:
                cur.execute(
                    "SELECT id_cliente FROM vehiculos WHERE id_vehiculo = ?",
                    (id_vehiculo,),
                )
                row_veh = cur.fetchone()
                id_cliente = row_veh["id_cliente"] if row_veh else None
                if id_cliente is None:
                    cur.execute(
                        "SELECT COUNT(*) FROM movimientos WHERE id_vehiculo = ?",
                        (id_vehiculo,),
                    )
                    restantes = int(cur.fetchone()[0] or 0)
                    if restantes <= 0:
                        cur.execute(
                            "DELETE FROM vehiculos WHERE id_vehiculo = ?",
                            (id_vehiculo,),
                        )

            conn.commit()
            _auditar(
                self,
                "Ingreso de estacionamiento eliminado",
                f"Movimiento {movimiento_id} - Patente {patente or '-'} - Espacio {espacio or '-'}",
            )
            self.ui.input_patente_est.clear()
            self.ui.input_espacio_est.clear()
            self._actualizar_activos_est()
            QMessageBox.information(
                self,
                "Eliminar ingreso",
                "El ingreso activo se elimino correctamente.",
            )
        except sqlite3.Error:
            QMessageBox.warning(
                self,
                "Eliminar ingreso",
                "No se pudo eliminar el ingreso activo.",
            )
        finally:
            if conn:
                conn.close()

    def _configurar_reloj(self):
        self._actualizar_hora()
        self._reloj_timer = QTimer(self)
        self._reloj_timer.timeout.connect(self._actualizar_hora)
        self._reloj_timer.start(1000)

    def _actualizar_hora(self):
        ahora = QDateTime.currentDateTime()
        hora = ahora.toString("HH:mm")
        fecha_num = ahora.toString("dd/MM/yyyy")

        texto = f"Fecha: {fecha_num}  Hora: {hora}"
        self.ui.label_fecha_num.setText(texto)
        self.ui.label_hora_value.setText("")
        self.ui.label_est_fecha_num.setText(texto)
        self.ui.label_est_hora_top_value.setText("")
        self.ui.label_est_hora_value.setText(hora)

    def _configurar_dashboard(self):
        self._refrescar_dashboard()
        self._dashboard_timer = QTimer(self)
        self._dashboard_timer.timeout.connect(self._refrescar_dashboard)
        self._dashboard_timer.start(5000)

    def _configurar_backups_automaticos(self):
        # Backups automÃ¡ticos deshabilitados.
        # La copia de seguridad se realiza manualmente antes de resetear tablas.
        self._backup_interval_ms = None
        self._backup_ultimo = None
        self._backup_timer = None

    def _backup_automatico(self, forzar=False):
        if not forzar and self._backup_ultimo is not None:
            segundos_desde_ultimo = (datetime.now() - self._backup_ultimo).total_seconds()
            if segundos_desde_ultimo < 60:
                return
        try:
            path = svc_crear_backup_db(max_backups=30)
        except Exception:
            return
        if path:
            self._backup_ultimo = datetime.now()

    def closeEvent(self, event):
        super().closeEvent(event)

    def _refrescar_dashboard(self):
        total = 0
        ocupadas = 0
        est_total = 0
        est_ocupadas = 0
        ingresos = 0.0
        vencimientos = []
        vencimientos_criticos = 0
        tarifa_hora = None
        tarifa_mensual = None

        try:
            conn = get_connection()
            cur = conn.cursor()

            cur.execute(
                "SELECT COUNT(*) FROM espacios "
                "WHERE activo = 1 AND COALESCE(es_reservado, 0) = 1"
            )
            total = cur.fetchone()[0] or 0

            cur.execute(
                "SELECT COUNT(*) FROM espacios "
                "WHERE activo = 1 AND COALESCE(es_reservado, 0) = 1 "
                "AND id_cliente IS NOT NULL"
            )
            ocupadas = cur.fetchone()[0] or 0

            cur.execute(
                "SELECT COUNT(*) FROM espacios "
                "WHERE activo = 1 AND COALESCE(es_reservado, 0) = 0 "
                "AND id_cliente IS NULL"
            )
            est_total = cur.fetchone()[0] or 0

            cur.execute(
                "SELECT COUNT(DISTINCT e.id_espacio) "
                "FROM espacios e "
                "JOIN movimientos m ON m.id_espacio = e.id_espacio AND m.fecha_salida IS NULL "
                "WHERE e.activo = 1 AND COALESCE(e.es_reservado, 0) = 0 "
                "AND e.id_cliente IS NULL"
            )
            est_ocupadas = cur.fetchone()[0] or 0

            mes_key = QDate.currentDate().toString("yyyy-MM")
            cur.execute(
                "SELECT COALESCE(SUM(monto), 0) FROM pagos_cochera "
                "WHERE strftime('%Y-%m', fecha_pago) = ?",
                (mes_key,),
            )
            ingresos = cur.fetchone()[0] or 0.0

            cur.execute(
                "SELECT precio_hora, precio_mensual FROM tarifas WHERE activa = 1 "
                "ORDER BY fecha_desde DESC LIMIT 1"
            )
            row_tarifa = cur.fetchone()
            if row_tarifa:
                tarifa_hora = float(row_tarifa[0])
                tarifa_mensual = float(row_tarifa[1] or 0)

            cur.execute(
                "SELECT c.nombre, cc.fecha_vencimiento "
                "FROM cochera_contratos cc "
                "JOIN clientes c ON c.id_cliente = cc.id_cliente "
                "WHERE cc.activo = 1 "
                "AND cc.fecha_vencimiento IS NOT NULL "
                "AND date(cc.fecha_vencimiento) <= date('now', '+7 day') "
                "ORDER BY cc.fecha_vencimiento "
                "LIMIT 50"
            )
            vencimientos = cur.fetchall()
            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos "
                "WHERE activo = 1 AND fecha_vencimiento IS NOT NULL "
                "AND date(fecha_vencimiento) <= date('now', '+3 day')"
            )
            vencimientos_criticos = cur.fetchone()[0] or 0

        except sqlite3.Error:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

        libres = max(total - ocupadas, 0)
        est_libres = max(est_total - est_ocupadas, 0)

        self.ui.label_total_value.setText(str(total))
        self.ui.label_ocupadas_value.setText(str(ocupadas))
        self.ui.label_libres_value.setText(str(libres))
        self.ui.label_ingresos_value.setText(_fmt_money(ingresos))
        if tarifa_hora is None:
            self.ui.label_est_tarifa_value.setText("$ 0.00")
        else:
            self.ui.label_est_tarifa_value.setText(_fmt_money(tarifa_hora))

        if tarifa_mensual is None:
            self.ui.label_mensual_value.setText("$ 0.00")
        else:
            self.ui.label_mensual_value.setText(_fmt_money(tarifa_mensual))

        if hasattr(self.ui, "label_est_total_value"):
            self.ui.label_est_total_value.setText(str(est_total))
        if hasattr(self.ui, "label_est_ocupadas_value"):
            self.ui.label_est_ocupadas_value.setText(str(est_ocupadas))
        if hasattr(self.ui, "label_est_libres_value"):
            self.ui.label_est_libres_value.setText(str(est_libres))
        if hasattr(self.ui, "label_est_tarifa_resumen_value"):
            if tarifa_hora is None:
                self.ui.label_est_tarifa_resumen_value.setText("$ 0.00")
            else:
                self.ui.label_est_tarifa_resumen_value.setText(_fmt_money(tarifa_hora))

        self._actualizar_estado_menu_estacionamiento()

        self.ui.btn_vencimientos.setText(
            f"Vencimientos proximos ({len(vencimientos)})"
        )

        ocupacion_pct = (ocupadas / total * 100) if total > 0 else 0
        if vencimientos_criticos > 0:
            self.ui.btn_vencimientos.setStyleSheet(
                "background-color: #B71C1C; color: white; font-weight: bold;"
            )
            self.ui.btn_vencimientos.setText(
                f"Vencimientos proximos ({len(vencimientos)}) - URGENTE"
            )
        else:
            self.ui.btn_vencimientos.setStyleSheet("")

        if ocupacion_pct >= 90:
            self.ui.label_ocupadas_value.setStyleSheet(
                "color: #B71C1C; font-weight: bold;"
            )
            self.ui.label_libres_value.setStyleSheet("color: #B71C1C; font-weight: bold;")
        elif ocupacion_pct >= 75:
            self.ui.label_ocupadas_value.setStyleSheet(
                "color: #F57C00; font-weight: bold;"
            )
            self.ui.label_libres_value.setStyleSheet("color: #F57C00; font-weight: bold;")
        else:
            self.ui.label_ocupadas_value.setStyleSheet("")
            self.ui.label_libres_value.setStyleSheet("")

    def _abrir_vencimientos(self):
        dlg = VencimientosDialog(self)
        dlg.exec()

    def _contar_vencimientos_para_popup(self):
        vencidos = 0
        proximos = 0
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos "
                "WHERE activo = 1 "
                "AND fecha_vencimiento IS NOT NULL "
                "AND date(fecha_vencimiento) < date('now')"
            )
            vencidos = cur.fetchone()[0] or 0
            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos "
                "WHERE activo = 1 "
                "AND fecha_vencimiento IS NOT NULL "
                "AND date(fecha_vencimiento) >= date('now') "
                "AND date(fecha_vencimiento) <= date('now', '+7 day')"
            )
            proximos = cur.fetchone()[0] or 0
        except sqlite3.Error:
            return 0, 0
        finally:
            if conn:
                conn.close()
        return int(vencidos), int(proximos)

    def _programar_popup_vencimientos_inicio(self):
        if (self.rol or "").upper() != "DUENO":
            return
        self._popup_vencimientos_intentos = 0
        QTimer.singleShot(900, self._mostrar_popup_vencimientos_inicio)

    def _mostrar_popup_vencimientos_inicio(self):
        if self._popup_vencimientos_mostrado:
            return
        if not self.isVisible():
            if self._popup_vencimientos_intentos < 8:
                self._popup_vencimientos_intentos += 1
                QTimer.singleShot(500, self._mostrar_popup_vencimientos_inicio)
            return
        vencidos, proximos = self._contar_vencimientos_para_popup()
        if vencidos <= 0 and proximos <= 0:
            return
        self._popup_vencimientos_mostrado = True
        self._abrir_vencimientos()

    def _estado_primeros_pasos(self):
        estado = {
            "tarifas": 0,
            "espacios": 0,
            "clientes": 0,
            "vehiculos": 0,
            "contratos": 0,
            "movimientos": 0,
            "empresa_nombre": "",
            "empresa_direccion": "",
            "empresa_telefono": "",
            "dir_reportes": "",
            "dir_comprobantes": "",
            "dir_tickets_salida": "",
        }
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM tarifas) AS tarifas, "
                "(SELECT COUNT(*) FROM espacios) AS espacios, "
                "(SELECT COUNT(*) FROM clientes) AS clientes, "
                "(SELECT COUNT(*) FROM vehiculos) AS vehiculos, "
                "(SELECT COUNT(*) FROM cochera_contratos) AS contratos, "
                "(SELECT COUNT(*) FROM movimientos) AS movimientos"
            )
            row = cur.fetchone()
            if row:
                estado.update(
                    {
                        "tarifas": int(row["tarifas"] or 0),
                        "espacios": int(row["espacios"] or 0),
                        "clientes": int(row["clientes"] or 0),
                        "vehiculos": int(row["vehiculos"] or 0),
                        "contratos": int(row["contratos"] or 0),
                        "movimientos": int(row["movimientos"] or 0),
                    }
                )
            cur.execute(
                "SELECT clave, valor FROM configuracion WHERE clave IN (?, ?, ?, ?, ?, ?)",
                (
                    "empresa_nombre",
                    "empresa_direccion",
                    "empresa_telefono",
                    "dir_reportes",
                    "dir_comprobantes",
                    "dir_tickets_salida",
                ),
            )
            for cfg in cur.fetchall():
                estado[cfg["clave"]] = (cfg["valor"] or "").strip()
            return estado
        except sqlite3.Error:
            return estado
        finally:
            if conn:
                conn.close()

    def _pasos_primeros_pasos(self):
        estado = self._estado_primeros_pasos()
        config_completa = all(
            [
                estado["empresa_nombre"],
                estado["empresa_direccion"],
                estado["empresa_telefono"],
            ]
        )
        carpetas_completas = all(
            [
                estado["dir_reportes"],
                estado["dir_comprobantes"],
                estado["dir_tickets_salida"],
            ]
        )
        clientes_patentes_completo = estado["clientes"] > 0 and estado["vehiculos"] > 0
        primera_operacion_completa = estado["contratos"] > 0 or estado["movimientos"] > 0

        faltantes_config = []
        if not estado["empresa_nombre"]:
            faltantes_config.append("nombre del negocio")
        if not estado["empresa_direccion"]:
            faltantes_config.append("direccion")
        if not estado["empresa_telefono"]:
            faltantes_config.append("telefono")

        faltantes_carpetas = []
        if not estado["dir_reportes"]:
            faltantes_carpetas.append("reportes")
        if not estado["dir_comprobantes"]:
            faltantes_carpetas.append("comprobantes")
        if not estado["dir_tickets_salida"]:
            faltantes_carpetas.append("tickets de salida")

        if estado["clientes"] <= 0 and estado["vehiculos"] <= 0:
            detalle_clientes = "Crea tu primer cliente y registra al menos una patente para poder operar."
        elif estado["clientes"] <= 0:
            detalle_clientes = "Todavia falta cargar al menos un cliente."
        elif estado["vehiculos"] <= 0:
            detalle_clientes = "Ya hay clientes, pero todavia falta registrar al menos una patente."
        else:
            detalle_clientes = "Clientes y patentes cargados."

        pasos = [
            {
                "titulo": "Tarifas",
                "completo": estado["tarifas"] > 0,
                "detalle": (
                    "Abre Administracion > Tarifas y carga al menos una tarifa activa. "
                    "Sin este paso la app no puede calcular cobros de cochera ni estacionamiento."
                ),
            },
            {
                "titulo": "Configuracion",
                "completo": config_completa,
                "detalle": (
                    "Abre Configuracion > General y completa los datos del negocio."
                    if not faltantes_config
                    else "Abre Configuracion > General y completa: "
                    + ", ".join(faltantes_config)
                    + "."
                ),
            },
            {
                "titulo": "Carpetas de archivos",
                "completo": carpetas_completas,
                "detalle": (
                    "Abre Configuracion > Reportes y define las carpetas donde se guardaran reportes, comprobantes y tickets."
                    if faltantes_carpetas
                    else "Las carpetas de reportes, comprobantes y tickets ya estan definidas en Configuracion > Reportes."
                ),
            },
            {
                "titulo": "Mapa y espacios",
                "completo": estado["espacios"] > 0,
                "detalle": (
                    "En Cochera > Acciones > Mapa de cocheras crea el mapa y agrega al menos un espacio. "
                    "Primero define cuales seran cocheras y cuales seran lugares de estacionamiento."
                ),
            },
            {
                "titulo": "Clientes y patentes",
                "completo": clientes_patentes_completo,
                "detalle": (
                    detalle_clientes
                    + " Esto se hace desde Cochera > Clientes (F6), donde cargas datos del cliente, telefono y patentes."
                ),
            },
            {
                "titulo": "Puesta en marcha",
                "completo": primera_operacion_completa,
                "detalle": (
                    "Ya puedes operar normalmente."
                    if primera_operacion_completa
                    else "Como siguiente paso, entra a Cochera > Contratos (F7) para crear el primer contrato o entra a Estacionamiento para registrar el primer ingreso."
                ),
            },
        ]
        return pasos

    def _siguiente_paso_primeros_pasos(self):
        pasos = self._pasos_primeros_pasos()
        for paso in pasos:
            if not paso["completo"]:
                return paso, pasos
        return None, pasos

    def _programar_popup_primeros_pasos(self):
        if (self.rol or "").upper() != "DUENO":
            return
        self._popup_primeros_pasos_mostrado = False
        QTimer.singleShot(1100, self._mostrar_popup_primeros_pasos)

    def _mostrar_popup_primeros_pasos(self):
        if self._popup_primeros_pasos_mostrado:
            return
        if not self.isVisible():
            QTimer.singleShot(500, self._mostrar_popup_primeros_pasos)
            return
        siguiente, pasos = self._siguiente_paso_primeros_pasos()
        if not siguiente:
            return
        self._popup_primeros_pasos_mostrado = True
        completados = [paso["titulo"] for paso in pasos if paso["completo"]]
        pendientes = [paso["titulo"] for paso in pasos if not paso["completo"]]
        bloque_completados = (
            "Pasos ya completos:\n- " + "\n- ".join(completados)
            if completados
            else "Todavia no hay pasos completos."
        )
        bloque_pendientes = (
            "Pendientes despues de este:\n- " + "\n- ".join(pendientes[1:])
            if len(pendientes) > 1
            else "Si completas este paso, ya quedara lista la puesta en marcha inicial."
        )
        QMessageBox.information(
            self,
            "Primeros pasos",
            f"{bloque_completados}\n\n"
            f"Siguiente paso sugerido: {siguiente['titulo']}\n"
            f"{siguiente['detalle']}\n\n"
            f"{bloque_pendientes}",
        )

    def _abrir_reportes(self, tipo_inicial="Todos"):
        dlg = ReportesDialog(self, tipo_inicial=tipo_inicial)
        dlg.exec()

    def _abrir_mapa_cocheras(self):
        es_admin = (self.rol or "").upper() == "DUENO"
        dlg = MapaCocheraDialog(self, editable=es_admin)
        dlg.exec()
        self._actualizar_estado_menu_estacionamiento()
        self._programar_popup_primeros_pasos()

    def _abrir_contratos(self):
        dlg = ContratosDialog(self, rol=self.rol)
        dlg.exec()
        self._programar_popup_primeros_pasos()

    def _abrir_clientes(self):
        dlg = ClientesDialog(self, rol=self.rol)
        dlg.exec()
        self._programar_popup_primeros_pasos()

    def _get_tarifa_hora(self, tipo_vehiculo="AUTO"):
        _, tarifa = self._get_tarifa_hora_info(tipo_vehiculo)
        return tarifa

    def _get_tarifa_hora_info(self, tipo_vehiculo="AUTO"):
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT id_tarifa, precio_hora, precio_hora_auto, precio_hora_moto, precio_hora_camioneta "
                "FROM tarifas WHERE activa = 1 "
                "ORDER BY fecha_desde DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                return int(row["id_tarifa"]), _tarifa_hora_desde_row(row, tipo_vehiculo)
        except sqlite3.Error:
            return None, None
        finally:
            if conn:
                conn.close()
        return None, None

    def _buscar_espacio_libre_est(self, cur):
        cur.execute(
            "SELECT e.id_espacio, e.codigo "
            "FROM espacios e "
            "LEFT JOIN movimientos m ON m.id_espacio = e.id_espacio AND m.fecha_salida IS NULL "
            "WHERE e.activo = 1 AND e.es_reservado = 0 AND e.id_cliente IS NULL "
            "AND m.id_movimiento IS NULL "
            "ORDER BY e.codigo LIMIT 1"
        )
        return cur.fetchone()

    def _resolver_espacio_est(self, cur, codigo):
        if codigo:
            cur.execute(
                "SELECT id_espacio, es_reservado, id_cliente FROM espacios "
                "WHERE codigo = ? AND activo = 1",
                (codigo,),
            )
            row = cur.fetchone()
            if row and row["es_reservado"] == 0 and row["id_cliente"] is None:
                cur.execute(
                    "SELECT COUNT(*) FROM movimientos "
                    "WHERE id_espacio = ? AND fecha_salida IS NULL",
                    (row["id_espacio"],),
                )
                if (cur.fetchone()[0] or 0) == 0:
                    return row["id_espacio"], codigo, False

        row = self._buscar_espacio_libre_est(cur)
        if not row:
            return None, None, False
        return row["id_espacio"], row["codigo"], True

    def _obtener_o_crear_vehiculo_est(self, cur, patente):
        cur.execute(
            "SELECT id_vehiculo, id_cliente FROM vehiculos WHERE patente = ?",
            (patente,),
        )
        row = cur.fetchone()
        if row:
            return row["id_vehiculo"], row["id_cliente"]
        cur.execute(
            "INSERT INTO vehiculos (patente, id_cliente) VALUES (?, NULL)",
            (patente,),
        )
        return cur.lastrowid, None

    def _codigo_cochera_activa_cliente(self, cur, id_cliente):
        return svc_codigo_cochera_activa_cliente(cur, id_cliente)

    def _vehiculo_tiene_ingreso_activo(self, cur, id_vehiculo):
        return svc_vehiculo_tiene_movimiento_activo(cur, id_vehiculo)

    def _buscar_movimiento_activo_por_patente(self, cur, patente):
        cur.execute(
            "SELECT m.id_movimiento, m.fecha_ingreso, m.id_tarifa_aplicada, "
            "m.tarifa_hora_aplicada, e.codigo, "
            "COALESCE(NULLIF(TRIM(m.tipo_vehiculo), ''), 'AUTO') AS tipo_vehiculo "
            "FROM movimientos m "
            "JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
            "JOIN espacios e ON e.id_espacio = m.id_espacio "
            "WHERE v.patente = ? AND m.fecha_salida IS NULL "
            "ORDER BY m.fecha_ingreso DESC LIMIT 1",
            (patente,),
        )
        return cur.fetchone()

    def _registrar_ingreso_est(self, popup_parent=None):
        patente = _normalizar_patente(self.ui.input_patente_est.text())
        patente_fmt = _formatear_patente_estacionamiento(patente)
        self.ui.input_patente_est.setText(patente_fmt)
        codigo = self.ui.input_espacio_est.text().strip().upper()
        tipo_vehiculo = self._tipo_vehiculo_est_db()
        if not tipo_vehiculo:
            mensaje_tipo = (
                "No hay tipos de vehiculo habilitados para estacionamiento.\n"
                "Activalos en Configuracion > Sistema."
                if not _tipos_vehiculo_config_estacionamiento()
                else "Selecciona un tipo de vehiculo antes de registrar el ingreso."
            )
            self._log_estacionamiento(
                mensaje_tipo,
                "warn",
                popup_parent=popup_parent,
            )
            combo = getattr(self.ui, "combo_tipo_vehiculo_est", None)
            if combo is not None:
                combo.setFocus()
            return
        if not _tipo_vehiculo_habilitado_estacionamiento(tipo_vehiculo):
            self._log_estacionamiento(
                f"El tipo {_texto_tipo_vehiculo(tipo_vehiculo)} no esta habilitado para estacionamiento.\nRevisalo en Configuracion > Sistema.",
                "warn",
                popup_parent=popup_parent,
            )
            return
        if not patente:
            self._log_estacionamiento("Completa la patente.", "warn", popup_parent=popup_parent)
            return
        if not _patente_est_formato_valido(patente):
            self._log_estacionamiento(
                "Patente invalida. Formatos validos: AA 123 AA, AAA 123 o 123 ABC.",
                "warn",
                popup_parent=popup_parent,
            )
            return
        if not _antirebote_iniciar(self, "est_ingreso"):
            return

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()

            id_vehiculo, id_cliente = self._obtener_o_crear_vehiculo_est(cur, patente)

            codigo_cochera = self._codigo_cochera_activa_cliente(cur, id_cliente)
            if codigo_cochera:
                self._log_estacionamiento(
                    f"La patente ya tiene cochera activa (espacio {codigo_cochera}).",
                    "warn",
                    popup_parent=popup_parent,
                )
                return

            if self._vehiculo_tiene_ingreso_activo(cur, id_vehiculo):
                self._log_estacionamiento(
                    "La patente ya tiene un ingreso activo.",
                    "warn",
                    popup_parent=popup_parent,
                )
                return

            id_espacio, codigo_resuelto, auto = self._resolver_espacio_est(cur, codigo)
            if not id_espacio:
                self._log_estacionamiento(
                    "No hay espacios disponibles en este momento.",
                    "warn",
                    popup_parent=popup_parent,
                )
                return
            if auto or codigo_resuelto != codigo:
                codigo = codigo_resuelto
                self.ui.input_espacio_est.setText(codigo)

            tarifa_id, tarifa = self._get_tarifa_hora_info(tipo_vehiculo)
            if tarifa is None:
                self._log_estacionamiento(
                    f"No hay tarifa por hora definida para {_texto_tipo_vehiculo(tipo_vehiculo)}.",
                    "warn",
                    popup_parent=popup_parent,
                )
                return

            cur.execute(
                "SELECT COUNT(*) FROM movimientos WHERE id_espacio = ? AND fecha_salida IS NULL",
                (id_espacio,),
            )
            if (cur.fetchone()[0] or 0) > 0:
                self._log_estacionamiento(
                    "Ese espacio ya esta ocupado.",
                    "warn",
                    popup_parent=popup_parent,
                )
                return

            dt_ing = datetime.now()
            ingreso_db = dt_ing.strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "INSERT INTO movimientos ("
                "id_vehiculo, id_espacio, fecha_ingreso, tipo_vehiculo, "
                "id_tarifa_aplicada, tarifa_hora_aplicada"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                (id_vehiculo, id_espacio, ingreso_db, tipo_vehiculo, tarifa_id, tarifa),
            )
            movimiento_id = cur.lastrowid
            conn.commit()
            ticket, ticket_error = _emitir_ticket_estacionamiento_seguro(
                evento="Ingreso",
                patente=patente_fmt,
                espacio=codigo,
                dt_ingreso=dt_ing,
                tarifa_hora=tarifa,
                tipo_vehiculo=tipo_vehiculo,
                movimiento_id=movimiento_id,
            )

            self._log_estacionamiento(
                f"Ingreso registrado en espacio {codigo}.",
                "ok",
                mostrar_popup=False,
            )
            box = QMessageBox(popup_parent or self)
            box.setWindowTitle("Ticket de ingreso")
            box.setIcon(QMessageBox.Information)
            texto = (
                f"Patente: {patente_fmt}\n"
                f"Espacio: {codigo}\n"
                f"Tipo: {_texto_tipo_vehiculo(tipo_vehiculo)}\n"
                f"Ingreso: {dt_ing.strftime('%d/%m/%Y %H:%M:%S')}"
            )
            btn_abrir = None
            if ticket:
                texto += f"\nTicket: {Path(ticket).name}"
                btn_abrir = box.addButton("Abrir ticket", QMessageBox.ActionRole)
                btn_abrir.clicked.connect(
                    lambda: _abrir_ticket_o_avisar(popup_parent or self, ticket)
                )
            elif ticket_error:
                texto += (
                    "\nNo se pudo generar el ticket automaticamente."
                    f"\nDetalle: {ticket_error}"
                )
            box.setText(texto)
            box.addButton(QMessageBox.Ok)
            box.exec()
            self.ui.input_patente_est.clear()
            self._resetear_tipo_vehiculo_est()
            self._actualizar_activos_est()
        except sqlite3.Error:
            self._log_estacionamiento(
                "Error al registrar ingreso.",
                "error",
                popup_parent=popup_parent,
            )
        finally:
            if conn:
                conn.close()
            _antirebote_finalizar(self, "est_ingreso", cooldown_ms=700)

    def _registrar_salida_est(self, popup_parent=None):
        patente = _normalizar_patente(self.ui.input_patente_est.text())
        patente_fmt = _formatear_patente_estacionamiento(patente)
        self.ui.input_patente_est.setText(patente_fmt)
        if not patente:
            self._log_estacionamiento("Completa la patente.", "warn", popup_parent=popup_parent)
            return
        if not _patente_est_formato_valido(patente):
            self._log_estacionamiento(
                "Patente invalida. Formatos validos: AA 123 AA, AAA 123 o 123 ABC.",
                "warn",
                popup_parent=popup_parent,
            )
            return
        if not _antirebote_iniciar(self, "est_salida"):
            return

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            row = self._buscar_movimiento_activo_por_patente(cur, patente)
            if not row:
                self._log_estacionamiento(
                    "No hay ingreso activo para esa patente.",
                    "warn",
                    popup_parent=popup_parent,
                )
                return

            tipo_vehiculo = _normalizar_tipo_vehiculo(row["tipo_vehiculo"])
            tarifa = float(row["tarifa_hora_aplicada"] or 0.0)
            if tarifa <= 0:
                _tarifa_id, tarifa = self._get_tarifa_hora_info(tipo_vehiculo)
            if tarifa is None:
                self._log_estacionamiento(
                    f"No hay tarifa por hora definida para {_texto_tipo_vehiculo(tipo_vehiculo)}.",
                    "warn",
                    popup_parent=popup_parent,
                )
                return

            fecha_ingreso = row["fecha_ingreso"] or ""
            dt_ing = _parse_fecha_db(fecha_ingreso)
            dt_out = datetime.now()
            salida_db = dt_out.strftime("%Y-%m-%d %H:%M:%S")
            if not dt_ing:
                dt_ing = dt_out
            horas_cobradas, total = _calcular_total_estadia(
                dt_ing,
                dt_out,
                tarifa,
                tolerancia_min=15,
            )

            ingreso_txt = dt_ing.strftime("%d/%m/%Y %H:%M:%S")
            salida_txt = dt_out.strftime("%d/%m/%Y %H:%M:%S")
            texto_confirmacion = (
                f"Patente: {patente_fmt}\n"
                f"Espacio: {row['codigo']}\n"
                f"Tipo: {_texto_tipo_vehiculo(tipo_vehiculo)}\n"
                f"Ingreso: {ingreso_txt}\n"
                f"Salida: {salida_txt}\n"
                f"Horas cobradas: {horas_cobradas}\n"
                f"Precio: {_fmt_money(total)}\n\n"
                "Aceptar esta salida?"
            )
            confirmar = QMessageBox.question(
                popup_parent or self,
                "Confirmar salida",
                texto_confirmacion,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if confirmar != QMessageBox.Yes:
                return

            metodo = self._solicitar_metodo_pago_est(
                total=total,
                popup_parent=popup_parent,
            )
            if not metodo:
                return

            cur.execute(
                "UPDATE movimientos SET fecha_salida = ?, total = ? "
                "WHERE id_movimiento = ?",
                (salida_db, total, row["id_movimiento"]),
            )
            cur.execute(
                "INSERT INTO pagos (id_movimiento, monto, metodo) VALUES (?, ?, ?)",
                (row["id_movimiento"], total, metodo),
            )
            conn.commit()
            ticket, ticket_error = _emitir_ticket_estacionamiento_seguro(
                evento="Salida",
                patente=patente_fmt,
                espacio=row["codigo"],
                dt_ingreso=dt_ing,
                dt_salida=dt_out,
                tarifa_hora=tarifa,
                horas_cobradas=horas_cobradas,
                total=total,
                metodo=metodo,
                tipo_vehiculo=tipo_vehiculo,
                movimiento_id=row["id_movimiento"],
            )
            self._log_estacionamiento(
                f"Salida registrada. Total: $ {total:.2f} "
                f"({horas_cobradas} hora/s cobradas, Espacio {row['codigo']}).",
                "ok",
                mostrar_popup=False,
            )
            box = QMessageBox(popup_parent or self)
            box.setWindowTitle("Salida registrada")
            box.setIcon(QMessageBox.Information)
            texto = (
                f"Patente: {patente_fmt}\n"
                f"Espacio: {row['codigo']}\n"
                f"Tipo: {_texto_tipo_vehiculo(tipo_vehiculo)}\n"
                f"Ingreso: {ingreso_txt}\n"
                f"Salida: {salida_txt}\n"
                f"Horas cobradas: {horas_cobradas}\n"
                f"Metodo: {metodo}\n"
                f"Precio: {_fmt_money(total)}"
            )
            if ticket:
                texto += f"\nTicket: {Path(ticket).name}"
                btn_abrir = box.addButton("Abrir ticket", QMessageBox.ActionRole)
                btn_abrir.clicked.connect(
                    lambda: _abrir_ticket_o_avisar(popup_parent or self, ticket)
                )
            elif ticket_error:
                texto += (
                    "\nNo se pudo generar el ticket automaticamente."
                    f"\nDetalle: {ticket_error}"
                )
            if (metodo or "").strip().lower() == "efectivo":
                btn_vuelto = box.addButton("Calcular vuelto", QMessageBox.ActionRole)
                btn_vuelto.clicked.connect(
                    lambda: CalcularVueltoDialog(total, popup_parent or self).exec()
                )
            box.setText(texto)
            box.addButton(QMessageBox.Ok)
            box.exec()
            self.ui.input_patente_est.clear()
            self._actualizar_activos_est()
        except sqlite3.Error:
            self._log_estacionamiento(
                "Error al registrar salida.",
                "error",
                popup_parent=popup_parent,
            )
        finally:
            if conn:
                conn.close()
            _antirebote_finalizar(self, "est_salida", cooldown_ms=700)
    def _actualizar_activos_est(self):
        self.ui.table_est_activos.setRowCount(0)
        conn = None
        filas_cache = []
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT m.id_movimiento, v.patente, e.codigo, m.fecha_ingreso "
                "FROM movimientos m "
                "JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
                "JOIN espacios e ON e.id_espacio = m.id_espacio "
                "WHERE m.fecha_salida IS NULL "
                "ORDER BY m.fecha_ingreso DESC"
            )
            filas_cache = [dict(row) for row in cur.fetchall()]
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()
        self._activos_est_cache = filas_cache
        self._aplicar_filtros_activos_est()


if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    _aplicar_fuente_aplicacion(app)
    sys.excepthook = _manejar_excepcion_no_controlada
    app._dialog_translation_filter = _DialogTranslationFilter(app)
    app.installEventFilter(app._dialog_translation_filter)

    if not _usuarios_existen():
        crear = FirstUserDialog()
        if crear.exec() != QDialog.Accepted:
            sys.exit(0)
        ventana = VentanaPrincipal(usuario=crear.usuario, rol=crear.rol)
        ventana.show()
        sys.exit(app.exec())

    login = LoginDialog()
    if login.exec() != QDialog.Accepted:
        sys.exit(0)
    ventana = VentanaPrincipal(usuario=login.usuario, rol=login.rol)
    ventana.show()
    sys.exit(app.exec())
    

