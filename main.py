# main.py
import sys
import sqlite3
import csv
import subprocess
import json
import re
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import quote
from PySide6.QtCore import (
    QDate,
    QDateTime,
    QTime,
    QTimer,
    Qt,
    QRectF,
    QPointF,
    QSize,
    QSizeF,
    QEvent,
    QUrl,
    QStringListModel,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QBrush,
    QPen,
    QPainter,
    QFont,
    QFontMetrics,
    QIcon,
    QDesktopServices,
    QPdfWriter,
    QPageSize,
    QKeySequence,
    QShortcut,
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
    QFormLayout,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
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
    QTimeEdit,
    QAbstractItemView,
    QMessageBox,
    QFileDialog,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QColorDialog,
    QHeaderView,
    QSizePolicy,
    QStyle,
    QMenu,
    QCompleter,
)
from ui_ventana_principal import Ui_MainWindow
from database import get_connection, init_db, reset_db
from servicios.contratos import (
    listar_contratos as svc_listar_contratos,
    obtener_detalle_contrato as svc_obtener_detalle_contrato,
    obtener_patente_por_dni as svc_obtener_patente_por_dni,
    obtener_tarifa_mensual_actual as svc_obtener_tarifa_mensual_actual,
    registrar_primer_pago_contrato as svc_registrar_primer_pago_contrato,
    registrar_renovacion_contrato as svc_registrar_renovacion_contrato,
)
from servicios.reportes import (
    consultar_detalle as svc_consultar_detalle_reportes,
    consultar_resumen as svc_consultar_resumen_reportes,
    consultar_detalle_rango as svc_consultar_detalle_reportes_rango,
    consultar_resumen_rango as svc_consultar_resumen_reportes_rango,
    consultar_pagos_mensuales_rango as svc_consultar_pagos_mensuales_rango,
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
    QMessageBox.critical(widget, titulo, mensaje)
    if accion:
        _auditar(widget, accion, detalle or mensaje)


def _confirmar_guardado_pendiente(widget, mensaje):
    return QMessageBox.question(
        widget,
        "Cambios sin guardar",
        mensaje,
        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        QMessageBox.Yes,
    )


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


def _parse_fecha_db(valor):
    return svc_parse_fecha_db(valor)


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
    if txt in {"MOTO", "MOTOCICLETA"}:
        return "MOTO"
    if txt in {"CAMIONETA", "PICKUP", "UTILITARIO"}:
        return "CAMIONETA"
    return "AUTO"


def _label_tipo_vehiculo(tipo):
    tipo_norm = _normalizar_tipo_vehiculo(tipo)
    if tipo_norm == "MOTO":
        return "Moto"
    if tipo_norm == "CAMIONETA":
        return "Camioneta"
    return "Auto"


def _tarifa_hora_desde_row(row, tipo_vehiculo="AUTO"):
    if not row:
        return None
    tipo_norm = _normalizar_tipo_vehiculo(tipo_vehiculo)
    valor = None
    if tipo_norm == "MOTO":
        valor = row["precio_hora_moto"]
    elif tipo_norm == "CAMIONETA":
        valor = row["precio_hora_camioneta"]
    else:
        valor = row["precio_hora_auto"]
    if valor is None:
        valor = row["precio_hora_auto"]
    if valor is None:
        valor = row["precio_hora"]
    if valor is None:
        return None
    return float(valor)


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


def _reportes_dir():
    valor = (_config_get("dir_reportes", "") or "").strip()
    carpeta = Path(valor) if valor else (Path(__file__).resolve().parent / "reportes")
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _comprobantes_dir():
    valor = (_config_get("dir_comprobantes", "") or "").strip()
    carpeta = Path(valor) if valor else (Path(__file__).resolve().parent / "comprobantes")
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _tickets_salida_dir():
    valor = (_config_get("dir_tickets_salida", "") or "").strip()
    if valor:
        carpeta = Path(valor)
    else:
        carpeta = _comprobantes_dir() / "tickets_salida"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _es_metodo_qr(metodo):
    return (metodo or "").strip().lower() == "qr"


def _normalizar_ref_externa(texto, max_len=80):
    base = (texto or "").strip()
    if not base:
        return ""
    limpio = []
    for ch in base:
        if ch.isalnum() or ch in ("-", "_", ".", "/", "#"):
            limpio.append(ch)
        elif ch.isspace():
            limpio.append("-")
    valor = "".join(limpio).strip("-_.#/")
    return valor[:max_len]


def _solo_digitos(texto):
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


def _normalizar_dni(dni):
    return _solo_digitos(dni)


def _validar_dni(dni):
    d = _normalizar_dni(dni)
    return 7 <= len(d) <= 10


def _normalizar_telefono(telefono):
    txt = str(telefono or "").strip()
    if not txt:
        return ""
    pref_plus = txt.startswith("+")
    dig = _solo_digitos(txt)
    if not dig:
        return ""
    return f"+{dig}" if pref_plus else dig


def _validar_telefono(telefono):
    if not str(telefono or "").strip():
        return True
    dig = _solo_digitos(telefono)
    return 8 <= len(dig) <= 15


def _normalizar_patente(patente):
    return "".join(ch for ch in str(patente or "").strip().upper() if ch.isalnum())


def _validar_patente(patente):
    p = _normalizar_patente(patente)
    if not p:
        return False
    # Formatos comunes AR y fallback alfanumerico acotado.
    if re.fullmatch(r"[A-Z]{3}\d{3}", p):
        return True
    if re.fullmatch(r"[A-Z]{2}\d{3}[A-Z]{2}", p):
        return True
    return bool(re.fullmatch(r"[A-Z0-9]{5,8}", p))


def _normalizar_cbu(cbu):
    return _solo_digitos(cbu)


def _validar_cbu(cbu):
    if not str(cbu or "").strip():
        return True
    return len(_normalizar_cbu(cbu)) == 22


def _telefono_a_whatsapp(telefono):
    dig = _solo_digitos(telefono)
    if not dig:
        return ""
    if dig.startswith("0"):
        dig = dig.lstrip("0")
    if len(dig) <= 11 and not dig.startswith("54"):
        dig = f"54{dig}"
    return dig


def _mensaje_recordatorio_whatsapp(nombre, deuda, vencimiento):
    plantilla = (
        _config_get(
            "wa_recordatorio_template",
            "Hola {nombre}, te recordamos tu vencimiento de cochera "
            "({vencimiento}). Deuda estimada: {deuda}.",
        )
        or ""
    )
    try:
        return plantilla.format(
            nombre=(nombre or "cliente").strip() or "cliente",
            deuda=deuda,
            vencimiento=vencimiento,
        )
    except Exception:
        return (
            f"Hola {nombre or 'cliente'}, te recordamos tu vencimiento de cochera "
            f"({vencimiento}). Deuda estimada: {deuda}."
        )


def _hora_en_rango(hora, hora_desde, hora_hasta):
    if hora is None or hora_desde is None or hora_hasta is None:
        return True
    if hora_desde <= hora_hasta:
        return hora_desde <= hora <= hora_hasta
    return hora >= hora_desde or hora <= hora_hasta


def _crear_orden_mp_point(monto, descripcion, external_reference):
    token = (_config_get("mp_access_token", "") or "").strip()
    collector_id = (_config_get("mp_collector_id", "") or "").strip()
    pos_id = (_config_get("mp_pos_id", "") or "").strip()
    if not token or not collector_id or not pos_id:
        raise ValueError(
            "Falta configurar Mercado Pago Point (token, collector ID o POS ID) "
            "en Configuracion > General."
        )

    url = (
        "https://api.mercadopago.com/instore/orders/qr/"
        f"seller/collectors/{collector_id}/pos/{pos_id}/qrs"
    )
    monto = float(monto or 0.0)
    payload = {
        "external_reference": external_reference,
        "title": "Pago cochera/estacionamiento",
        "description": descripcion or "Pago",
        "total_amount": monto,
        "items": [
            {
                "title": descripcion or "Pago",
                "quantity": 1,
                "unit_price": monto,
                "total_amount": monto,
                "unit_measure": "unit",
            }
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url=url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            status = int(getattr(resp, "status", 200) or 200)
    except HTTPError as e:
        detalle = ""
        try:
            detalle = e.read().decode("utf-8", "ignore")
        except Exception:
            detalle = str(e)
        raise ValueError(f"Mercado Pago devolvio error {e.code}. {detalle}")
    except URLError as e:
        raise ValueError(f"No se pudo conectar con Mercado Pago. {e.reason}")
    except Exception as e:
        raise ValueError(f"No se pudo crear la orden QR. {e}")

    if status >= 400:
        raise ValueError(f"Mercado Pago devolvio estado HTTP {status}.")
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {}
    return parsed


def _solicitar_ref_qr(widget, monto, concepto):
    referencia_sugerida = f"QR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    proveedor = (_config_get("qr_provider", "manual") or "manual").strip().lower()

    if proveedor == "mercadopago_point":
        ref_mp = _normalizar_ref_externa(
            f"MP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        try:
            _crear_orden_mp_point(
                monto=monto,
                descripcion=concepto,
                external_reference=ref_mp,
            )
            referencia_sugerida = ref_mp
            QMessageBox.information(
                widget,
                "Pago QR",
                "Orden enviada al dispositivo Point.\n"
                "Cuando se confirme el cobro, guarda el ID de operacion.",
            )
        except ValueError as e:
            QMessageBox.warning(widget, "Pago QR", str(e))
            return None

    texto, ok = QInputDialog.getText(
        widget,
        "Referencia QR",
        "Ingresa la referencia/ID de operacion del cobro QR:",
        QLineEdit.Normal,
        referencia_sugerida,
    )
    if not ok:
        return None
    ref_final = _normalizar_ref_externa(texto or referencia_sugerida)
    if not ref_final:
        QMessageBox.warning(widget, "Pago QR", "Debes indicar una referencia valida.")
        return None
    return ref_final


def _generar_comprobante_pdf(path, titulo, lineas):
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setResolution(96)
    painter = QPainter(writer)
    try:
        x = 40
        y = 60
        line_h = 22
        painter.setFont(QFont("Arial", 16))
        painter.drawText(x, y, titulo)
        y += 30
        painter.setFont(QFont("Arial", 11))
        for label, value in lineas:
            painter.drawText(x, y, f"{label}: {value}")
            y += line_h
    finally:
        painter.end()


def _generar_ticket_pdf(path, titulo, lineas, ancho_mm=80.0, subtitulo=""):
    lineas = list(lineas or [])
    subtitulo = (subtitulo or "").strip()

    dpi = 96.0
    mm_to_px = lambda mm: int(round((float(mm) / 25.4) * dpi))
    px_to_mm = lambda px: (float(px) * 25.4) / dpi

    x = 10
    y_inicio = 10
    line_h = 14
    fuente_body = QFont("Arial", 9)
    metrics = QFontMetrics(fuente_body)
    ancho_px = max(mm_to_px(ancho_mm), 220)
    max_text_width = max(100, ancho_px - (x * 2))

    def _wrap_line(texto):
        texto = str(texto or "").strip()
        if not texto:
            return [""]
        out = []
        actual = ""
        for token in texto.split():
            candidato = token if not actual else f"{actual} {token}"
            if metrics.horizontalAdvance(candidato) <= max_text_width:
                actual = candidato
                continue
            if actual:
                out.append(actual)
            if metrics.horizontalAdvance(token) <= max_text_width:
                actual = token
                continue
            pedazo = ""
            for ch in token:
                cand = pedazo + ch
                if metrics.horizontalAdvance(cand) <= max_text_width:
                    pedazo = cand
                else:
                    if pedazo:
                        out.append(pedazo)
                    pedazo = ch
            actual = pedazo
        if actual:
            out.append(actual)
        return out or [texto]

    lineas_render = []
    for label, value in lineas:
        texto = f"{label}: {value}"
        lineas_render.extend(_wrap_line(texto))

    alto_header = 24 + (12 if subtitulo else 0) + 10
    alto_px_estimado = y_inicio + alto_header + (len(lineas_render) * line_h) + 10
    alto_mm = max(55.0, px_to_mm(alto_px_estimado))

    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QSizeF(float(ancho_mm), float(alto_mm)), QPageSize.Millimeter))
    writer.setResolution(96)

    painter = QPainter(writer)
    try:
        w = float(writer.width())
        y = y_inicio
        painter.setPen(QPen(QColor("#111111")))

        painter.setFont(QFont("Arial", 11, QFont.Bold))
        painter.drawText(QRectF(0, y, w, 16), Qt.AlignCenter, titulo)
        y += 16
        if subtitulo:
            painter.setFont(QFont("Arial", 8))
            painter.drawText(QRectF(0, y, w, 12), Qt.AlignCenter, subtitulo)
            y += 12
        y += 3
        painter.drawLine(x, y, int(w - x), y)
        y += 12

        painter.setFont(fuente_body)
        for texto in lineas_render:
            painter.drawText(x, y, texto)
            y += line_h
    finally:
        painter.end()


def _emitir_comprobante_cochera(id_contrato, monto, metodo, meses, nueva_venc):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT c.nombre, c.dni, e.codigo "
            "FROM cochera_contratos cc "
            "JOIN clientes c ON c.id_cliente = cc.id_cliente "
            "JOIN espacios e ON e.id_espacio = cc.id_espacio "
            "WHERE cc.id_contrato = ?",
            (id_contrato,),
        )
        row = cur.fetchone()
        if not row:
            return None
    except sqlite3.Error:
        return None
    finally:
        if conn:
            conn.close()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _comprobantes_dir() / f"cochera_{id_contrato}_{ts}.pdf"
    lineas = [
        ("Tipo", "Cochera"),
        ("Contrato ID", id_contrato),
        ("Cliente", row["nombre"]),
        ("DNI", row["dni"]),
        ("Espacio", row["codigo"]),
        ("Meses", meses),
        ("Monto", f"$ {monto:.2f}"),
        ("Metodo", metodo),
        ("Nuevo vencimiento", nueva_venc),
        ("Fecha emision", datetime.now().strftime("%d/%m/%Y %H:%M")),
    ]
    _generar_comprobante_pdf(path, "Comprobante de pago", lineas)
    return path


def _emitir_comprobante_cochera_pago(id_pago):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT pc.id_pago, pc.fecha_pago, pc.monto, pc.metodo, "
            "cc.id_contrato, c.nombre, c.dni, e.codigo "
            "FROM pagos_cochera pc "
            "JOIN cochera_contratos cc ON cc.id_contrato = pc.id_contrato "
            "JOIN clientes c ON c.id_cliente = cc.id_cliente "
            "JOIN espacios e ON e.id_espacio = cc.id_espacio "
            "WHERE pc.id_pago = ?",
            (id_pago,),
        )
        row = cur.fetchone()
        if not row:
            return None
    except sqlite3.Error:
        return None
    finally:
        if conn:
            conn.close()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _comprobantes_dir() / f"cochera_pago_{id_pago}_{ts}.pdf"
    lineas = [
        ("Tipo", "Cochera"),
        ("Pago ID", row["id_pago"]),
        ("Contrato ID", row["id_contrato"]),
        ("Cliente", row["nombre"]),
        ("DNI", row["dni"]),
        ("Espacio", row["codigo"]),
        ("Monto", f"$ {float(row['monto'] or 0.0):.2f}"),
        ("Metodo", row["metodo"] or ""),
        ("Fecha pago", row["fecha_pago"] or ""),
        ("Fecha emision", datetime.now().strftime("%d/%m/%Y %H:%M")),
    ]
    _generar_comprobante_pdf(path, "Comprobante de pago (reimpresion)", lineas)
    return path


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
    ref_externa=None,
    tipo_vehiculo="AUTO",
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
        ("Tipo vehiculo", _label_tipo_vehiculo(tipo_vehiculo)),
        ("Espacio", espacio or ""),
        ("Ingreso", dt_ingreso.strftime("%d/%m/%Y %H:%M:%S") if dt_ingreso else ""),
        ("Salida", dt_salida.strftime("%d/%m/%Y %H:%M:%S") if dt_salida else ""),
        ("Tarifa por hora", f"$ {float(tarifa_hora or 0.0):.2f}"),
        ("Horas cobradas", horas_cobradas),
        ("Monto", f"$ {float(total or 0.0):.2f}"),
        ("Metodo", metodo or ""),
        ("Referencia", ref_externa or ""),
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
    movimiento_id=None,
    ref_externa=None,
    tipo_vehiculo="AUTO",
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
    local_nombre = _config_get("empresa_nombre", "").strip()
    direccion = _config_get("empresa_direccion", "").strip()
    telefono = _config_get("empresa_telefono", "").strip()

    lineas = [
        ("Patente", patente or ""),
        ("Tipo vehiculo", _label_tipo_vehiculo(tipo_vehiculo)),
        ("Espacio", espacio or ""),
        ("Ingreso", dt_ingreso.strftime("%d/%m/%Y %H:%M:%S") if dt_ingreso else ""),
    ]
    if dt_salida:
        lineas.append(("Salida", dt_salida.strftime("%d/%m/%Y %H:%M:%S")))
    if tarifa_hora is not None:
        lineas.append(("Tarifa por hora", f"$ {float(tarifa_hora or 0.0):.2f}"))
    if horas_cobradas is not None:
        lineas.append(("Horas cobradas", horas_cobradas))
    if total is not None:
        lineas.append(("Total", f"$ {float(total or 0.0):.2f}"))
    if metodo:
        lineas.append(("Metodo", metodo))
    if ref_externa:
        lineas.append(("Referencia", ref_externa))
    if direccion:
        lineas.append(("Direccion", direccion))
    if telefono:
        lineas.append(("Telefono", telefono))

    _generar_ticket_pdf(
        path,
        "Ticket de estacionamiento",
        lineas,
        ancho_mm=80.0,
        subtitulo=local_nombre,
    )
    return path


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
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password2 = QLineEdit()
        self.input_password2.setEchoMode(QLineEdit.Password)
        form.addRow("Usuario", self.input_usuario)
        form.addRow("Contrasena", self.input_password)
        form.addRow("Repetir contrasena", self.input_password2)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_crear = QPushButton("Crear")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_crear.setAutoDefault(False)
        self.btn_crear.setDefault(False)
        self.btn_cancelar.setAutoDefault(False)
        self.btn_cancelar.setDefault(False)
        buttons.addWidget(self.btn_crear)
        buttons.addWidget(self.btn_cancelar)
        layout.addLayout(buttons)

        self.btn_crear.clicked.connect(self._crear_usuario)
        self.btn_cancelar.clicked.connect(self.reject)
        self.input_usuario.returnPressed.connect(self._avanzar_teclado)
        self.input_password.returnPressed.connect(self._avanzar_teclado)
        self.input_password2.returnPressed.connect(self._crear_usuario)
        self.input_usuario.installEventFilter(self)
        self.input_password.installEventFilter(self)
        self.input_password2.installEventFilter(self)
        self.input_usuario.setFocus()

    def _avanzar_teclado(self):
        foco = QApplication.focusWidget()
        if foco is self.input_usuario:
            self.input_password.setFocus()
            self.input_password.selectAll()
            return
        if foco is self.input_password:
            self.input_password2.setFocus()
            self.input_password2.selectAll()
            return
        self._crear_usuario()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and int(event.key()) == int(Qt.Key_Space):
            if obj in (self.input_usuario, self.input_password):
                self._avanzar_teclado()
                return True
            if obj is self.input_password2:
                self._crear_usuario()
                return True
        return super().eventFilter(obj, event)

    def _crear_usuario(self):
        usuario = self.input_usuario.text().strip()
        password = self.input_password.text()
        password2 = self.input_password2.text()

        if not usuario or not password:
            QMessageBox.warning(self, "Datos incompletos", "Completa todos los campos.")
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
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_password2 = QLineEdit()
        self.input_password2.setEchoMode(QLineEdit.Password)
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
        self.input_new_password2 = QLineEdit()
        self.input_new_password2.setEchoMode(QLineEdit.Password)
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

        if not usuario or not password:
            QMessageBox.warning(self, "Datos incompletos", "Completa todos los campos.")
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


class ContratosDialog(QDialog):
    def __init__(self, parent=None, rol=None):
        super().__init__(parent)
        self.rol = rol
        self.setWindowTitle("Contratos de cochera")
        self.setMinimumWidth(720)

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Cliente",
                "DNI",
                "Patente",
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
        self.input_patente = QLineEdit()
        self.input_patente.setReadOnly(True)
        self.input_patente.setPlaceholderText("Patente del cliente/contrato")
        self.input_espacio = QLineEdit()
        self.input_venc = QDateEdit()
        self.input_venc.setCalendarPopup(True)
        self.input_venc.setDate(QDate.currentDate().addMonths(1))
        self.input_monto = QDoubleSpinBox()
        self.input_monto.setDecimals(2)
        self.input_monto.setRange(0.0, 999999.0)
        self.input_monto.setSingleStep(100.0)
        form.addRow("DNI cliente", self.input_dni)
        form.addRow("Patente", self.input_patente)
        form.addRow("Espacio (codigo)", self.input_espacio)
        form.addRow("Vencimiento", self.input_venc)
        form.addRow("Monto mensual", self.input_monto)
        layout.addLayout(form)

        botones = QHBoxLayout()
        self.btn_crear = QPushButton("Crear contrato")
        self.btn_registrar_pago = QPushButton("Registro de pagos")
        self.btn_renovar_pago = QPushButton("Renovar pago")
        self.btn_historial = QPushButton("Historial cambios")
        self.btn_baja = QPushButton("Dar de baja")
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_crear.setProperty("variant", "success")
        self.btn_registrar_pago.setProperty("variant", "info")
        self.btn_renovar_pago.setProperty("variant", "info")
        self.btn_historial.setProperty("variant", "info")
        self.btn_baja.setProperty("variant", "warning")
        self.btn_eliminar.setProperty("variant", "danger")
        botones.addWidget(self.btn_crear)
        botones.addWidget(self.btn_registrar_pago)
        botones.addWidget(self.btn_renovar_pago)
        botones.addWidget(self.btn_historial)
        botones.addWidget(self.btn_baja)
        botones.addWidget(self.btn_eliminar)
        botones.addStretch(1)
        layout.addLayout(botones)

        self.btn_crear.clicked.connect(self._crear_contrato)
        self.btn_registrar_pago.clicked.connect(self._registrar_pago)
        self.btn_renovar_pago.clicked.connect(self._renovar_pago)
        self.btn_historial.clicked.connect(self._abrir_historial_contrato)
        self.btn_baja.clicked.connect(self._baja)
        self.btn_eliminar.clicked.connect(self._eliminar)
        self.table.itemSelectionChanged.connect(self._seleccion_changed)
        self.input_dni.editingFinished.connect(self._actualizar_patente_por_dni)

        es_admin = (self.rol or "").upper() == "DUENO"
        if not es_admin:
            self.btn_eliminar.setEnabled(False)
            self.btn_eliminar.setVisible(False)

        self._cargar_tarifa_mensual()
        self._cargar()
        self._actualizar_acciones_pago()
        self._actualizar_snapshot_form()

    def _snapshot_form(self):
        return {
            "dni": self.input_dni.text().strip(),
            "patente": self.input_patente.text().strip().upper(),
            "espacio": self.input_espacio.text().strip().upper(),
            "vencimiento": self.input_venc.date().toString("yyyy-MM-dd"),
            "monto": round(float(self.input_monto.value()), 2),
        }

    def _actualizar_snapshot_form(self):
        self._form_snapshot = self._snapshot_form()

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
                "WHERE activo = 1 AND id_cliente IS NULL "
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

    def _actualizar_patente_por_dni(self):
        dni = self.input_dni.text().strip()
        self.input_patente.clear()
        if not dni:
            return
        patente = svc_obtener_patente_por_dni(dni)
        if patente:
            self.input_patente.setText(patente)

    def _cargar_tarifa_mensual(self):
        monto = svc_obtener_tarifa_mensual_actual()
        if monto is not None:
            self.input_monto.setValue(float(monto))

    def _cargar(self):
        self.table.setRowCount(0)
        rows = svc_listar_contratos()
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            item_cliente = QTableWidgetItem(row["nombre"])
            item_cliente.setData(Qt.UserRole, row["id_contrato"])
            item_cliente.setData(Qt.UserRole + 1, row["id_espacio"])
            item_cliente.setData(Qt.UserRole + 2, int(row["activo"] or 0))
            self.table.setItem(r, 0, item_cliente)
            self.table.setItem(r, 1, QTableWidgetItem(row["dni"]))
            self.table.setItem(r, 2, QTableWidgetItem(row["patente"] or ""))
            self.table.setItem(r, 3, QTableWidgetItem(row["codigo"]))
            self.table.setItem(r, 4, QTableWidgetItem(row["fecha_inicio"] or ""))
            item_venc = QTableWidgetItem(row["fecha_vencimiento"] or "")
            self.table.setItem(r, 5, item_venc)
            self.table.setItem(
                r, 6, QTableWidgetItem(f"$ {float(row['monto_mensual'] or 0):.2f}")
            )
            activo = "ACTIVO" if row["activo"] == 1 else "INACTIVO"
            self.table.setItem(r, 7, QTableWidgetItem(activo))

            if row["activo"] == 1:
                fecha_venc = QDate.fromString(item_venc.text(), "yyyy-MM-dd")
                if fecha_venc.isValid():
                    dias = QDate.currentDate().daysTo(fecha_venc)
                    if dias < 0:
                        bg = QColor(127, 29, 29)
                        fg = QColor(255, 255, 255)
                        tip = f"Vencido hace {abs(dias)} dia/s"
                    elif dias == 0:
                        bg = QColor(180, 83, 9)
                        fg = QColor(255, 255, 255)
                        tip = "Vence hoy"
                    elif dias <= 7:
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
        self._actualizar_acciones_pago()
        self._actualizar_snapshot_form()

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

    def _actualizar_acciones_pago(self, activo=None):
        id_contrato, _ = self._selected_ids()
        hay_sel = bool(id_contrato)
        if not hay_sel:
            self.btn_registrar_pago.setEnabled(False)
            self.btn_renovar_pago.setEnabled(False)
            self.btn_historial.setEnabled(False)
            self.btn_baja.setEnabled(False)
            if self.btn_eliminar.isVisible():
                self.btn_eliminar.setEnabled(False)
            return

        if activo is None:
            activo = self._selected_activo()
        es_activo = bool(activo)

        self.btn_registrar_pago.setEnabled(not es_activo)
        self.btn_renovar_pago.setEnabled(es_activo)
        self.btn_historial.setEnabled(True)
        self.btn_baja.setEnabled(es_activo)
        if self.btn_eliminar.isVisible():
            self.btn_eliminar.setEnabled(True)

        if es_activo:
            self.btn_registrar_pago.setToolTip("Solo para activar contratos inactivos.")
            self.btn_renovar_pago.setToolTip("Renueva y extiende vencimiento.")
            self.btn_baja.setToolTip("Desactiva contrato y libera espacio.")
        else:
            self.btn_registrar_pago.setToolTip("Registra primer pago y activa el contrato.")
            self.btn_renovar_pago.setToolTip("Disponible solo para contratos activos.")
            self.btn_baja.setToolTip("Disponible solo para contratos activos.")

    def _seleccion_changed(self):
        id_contrato, _ = self._selected_ids()
        if not id_contrato:
            self._actualizar_acciones_pago()
            self._actualizar_snapshot_form()
            return
        row = svc_obtener_detalle_contrato(id_contrato)
        if not row:
            return
        self.input_dni.setText(row["dni"] or "")
        self.input_patente.setText(row["patente"] or "")
        self.input_espacio.setText((row["codigo"] or "").upper())
        fecha = QDate.fromString(row["fecha_vencimiento"] or "", "yyyy-MM-dd")
        if fecha.isValid():
            self.input_venc.setDate(fecha)
        self.input_monto.setValue(float(row["monto_mensual"] or 0.0))
        self._actualizar_acciones_pago(int(row["activo"] or 0) == 1)
        self._actualizar_snapshot_form()

    def _crear_contrato(self):
        dni = self.input_dni.text().strip()
        codigo = self.input_espacio.text().strip().upper()
        fecha_venc = self.input_venc.date().toString("yyyy-MM-dd")
        monto = float(self.input_monto.value())

        if not dni or not codigo:
            QMessageBox.warning(self, "Datos incompletos", "Completa DNI y espacio.")
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
                QMessageBox.warning(self, "Cliente", "No existe cliente con ese DNI.")
                return False
            id_cliente = row["id_cliente"]

            if id_cliente:
                cur.execute(
                    "SELECT COUNT(*) FROM cochera_contratos "
                    "WHERE id_cliente = ? AND activo = 1",
                    (id_cliente,),
                )
                if (cur.fetchone()[0] or 0) > 0:
                    QMessageBox.warning(
                        self,
                        "Contrato",
                        "Ese cliente ya tiene un contrato activo.\n"
                        "Da de baja el contrato actual antes de crear otro.",
                    )
                    return False
                cur.execute(
                    "SELECT COUNT(*) FROM vehiculos "
                    "WHERE id_cliente = ? "
                    "AND TRIM(COALESCE(patente, '')) <> ''",
                    (id_cliente,),
                )
                if (cur.fetchone()[0] or 0) <= 0:
                    QMessageBox.warning(
                        self,
                        "Contrato",
                        "Este cliente no tiene ninguna patente a su nombre.\n"
                        "Agrega un vehiculo antes de crear el contrato.",
                    )
                    return False

            cur.execute("SELECT id_espacio FROM espacios WHERE codigo = ? AND activo = 1", (codigo,))
            row = cur.fetchone()
            if row:
                id_espacio = row["id_espacio"]
            else:
                cur.execute(
                    "INSERT INTO espacios (codigo, es_reservado, activo) VALUES (?, 0, 1)",
                    (codigo,),
                )
                id_espacio = cur.lastrowid

            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos WHERE id_espacio = ? AND activo = 1",
                (id_espacio,),
            )
            if (cur.fetchone()[0] or 0) > 0:
                QMessageBox.warning(self, "Contrato", "Ese espacio ya tiene un contrato activo.")
                return False

            cur.execute(
                "INSERT INTO cochera_contratos "
                "(id_cliente, id_espacio, fecha_vencimiento, monto_mensual, activo) "
                "VALUES (?, ?, ?, ?, 0)",
                (id_cliente, id_espacio, fecha_venc, monto),
            )
            id_contrato = cur.lastrowid
            conn.commit()
            _auditar(
                self,
                "Contrato creado (inactivo)",
                f"Contrato {id_contrato} - DNI {dni} - Espacio {codigo} - "
                f"Venc {fecha_venc} - $ {monto:.2f}",
            )
            QMessageBox.information(
                self,
                "Contrato",
                "Contrato creado como INACTIVO.\n"
                "Registra el primer pago para activarlo.",
            )
            self.input_dni.clear()
            self.input_patente.clear()
            self.input_espacio.clear()
            self._cargar()
            return True
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo crear el contrato.")
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
            QMessageBox.warning(self, "Pago", "Selecciona un contrato.")
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
                    QMessageBox.warning(self, "Pago", "Contrato no encontrado.")
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
                fecha_venc_date = QDate.fromString(fecha_venc_str or "", "yyyy-MM-dd")
                if fecha_venc_date.isValid() and fecha_venc_date < QDate.currentDate():
                    QMessageBox.warning(
                        self,
                        "Pago",
                        "El contrato esta vencido. Ajusta el vencimiento antes de activar.",
                    )
                    return
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
                if id_cliente:
                    cur.execute(
                        "SELECT COUNT(*) FROM cochera_contratos "
                        "WHERE id_cliente = ? AND activo = 1 AND id_contrato <> ?",
                        (id_cliente, id_contrato),
                    )
                    if (cur.fetchone()[0] or 0) > 0:
                        QMessageBox.warning(
                            self,
                            "Pago",
                            "Ese cliente ya tiene otro contrato activo.",
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
                QMessageBox.warning(self, "Pago", "El monto debe ser mayor a 0.")
                return
            ref_externa = None
            if _es_metodo_qr(metodo):
                ref_externa = _solicitar_ref_qr(
                    self,
                    monto,
                    f"Primer pago contrato {id_contrato}",
                )
                if ref_externa is None:
                    return

            try:
                resultado = svc_registrar_primer_pago_contrato(
                    id_contrato,
                    monto,
                    metodo,
                    ref_externa=ref_externa,
                    usuario=_usuario_desde_widget(self),
                )
                fecha_venc_str = resultado.get("fecha_vencimiento") or fecha_venc_str
                _auditar(
                    self,
                    "Primer pago cochera registrado",
                    f"Contrato {id_contrato} - $ {monto:.2f} - {metodo}"
                    + (f" - ref {ref_externa}" if ref_externa else ""),
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
                QMessageBox.information(
                    self,
                    "Pago",
                    "Primer pago registrado. Contrato ACTIVADO.\n"
                    f"Vencimiento sin cambios: {venc_txt}.{info_extra}",
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
            QMessageBox.warning(self, "Renovar pago", "Selecciona un contrato.")
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
                    QMessageBox.warning(self, "Renovar pago", "Contrato no encontrado.")
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
                QMessageBox.warning(self, "Renovar pago", "El monto debe ser mayor a 0.")
                return
            ref_externa = None
            if _es_metodo_qr(metodo):
                ref_externa = _solicitar_ref_qr(
                    self,
                    monto,
                    f"Renovacion contrato {id_contrato}",
                )
                if ref_externa is None:
                    return

            try:
                nueva_venc_str = svc_registrar_renovacion_contrato(
                    id_contrato,
                    meses,
                    monto,
                    metodo,
                    ref_externa=ref_externa,
                    usuario=_usuario_desde_widget(self),
                )
                nueva_venc = QDate.fromString(nueva_venc_str or "", "yyyy-MM-dd")
                if not nueva_venc.isValid():
                    nueva_venc = QDate.currentDate()
                _auditar(
                    self,
                    "Renovacion de pago cochera",
                    f"Contrato {id_contrato} - {meses} mes/es - $ {monto:.2f} - {metodo}"
                    + (f" - ref {ref_externa}" if ref_externa else ""),
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
                QMessageBox.information(
                    self,
                    "Renovar pago",
                    f"Renovacion registrada ({meses} mes/es). Nuevo vencimiento: "
                    f"{nueva_venc.toString('dd/MM/yyyy')}.{info_extra}",
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
            QMessageBox.warning(self, "Contrato", "Selecciona un contrato.")
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
                    "UPDATE cochera_contratos SET activo = 0 WHERE id_contrato = ?",
                    (id_contrato,),
                )
                if id_espacio:
                    cur.execute(
                        "UPDATE espacios SET id_cliente = NULL WHERE id_espacio = ?",
                        (id_espacio,),
                    )
                conn.commit()
                _auditar(self, "Contrato baja", f"Contrato {id_contrato}")
                self._cargar()
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
            QMessageBox.warning(self, "Contrato", "Selecciona un contrato.")
            return
        if not _antirebote_iniciar(self, "contratos_eliminar"):
            return
        try:
            activo = False
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
            except sqlite3.Error:
                activo = False
            finally:
                if conn:
                    conn.close()

            confirmar = QMessageBox.question(
                self,
                "Eliminar contrato",
                "El contrato esta ACTIVO. Realmente quieres eliminarlo?"
                if activo
                else "Esto eliminara el contrato definitivamente. Continuar?",
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
                    "DELETE FROM cochera_contratos WHERE id_contrato = ?",
                    (id_contrato,),
                )
                if id_espacio:
                    cur.execute(
                        "UPDATE espacios SET id_cliente = NULL WHERE id_espacio = ?",
                        (id_espacio,),
                    )
                conn.commit()
                _auditar(self, "Contrato eliminado", f"Contrato {id_contrato}")
                self._cargar()
            except sqlite3.Error:
                _mostrar_error(self, "Error", "No se pudo eliminar el contrato.")
            finally:
                if conn:
                    conn.close()
        finally:
            _antirebote_finalizar(
                self,
                "contratos_eliminar",
                cooldown_ms=700,
                on_release=self._actualizar_acciones_pago,
            )

    def _abrir_historial_contrato(self):
        id_contrato, _ = self._selected_ids()
        if not id_contrato:
            QMessageBox.warning(self, "Historial", "Selecciona un contrato.")
            return
        dlg = HistorialContratoDialog(id_contrato, self)
        dlg.exec()


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
        self.combo_metodo = QComboBox()
        self.combo_metodo.addItems(["Efectivo", "Transferencia", "Tarjeta", "QR", "Otro"])
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
        self.label_sugerido = QLabel(f"$ {self._monto_base:.2f}")
        self.input_monto = QDoubleSpinBox()
        self.input_monto.setDecimals(2)
        self.input_monto.setRange(0.0, 999999.0)
        self.input_monto.setValue(self._monto_base)
        self.combo_metodo = QComboBox()
        self.combo_metodo.addItems(["Efectivo", "Transferencia", "Tarjeta", "QR", "Otro"])

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

    def _actualizar_sugerido(self):
        meses = self.input_meses.value()
        sugerido = self._monto_base * meses
        self.label_sugerido.setText(f"$ {sugerido:.2f}")
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
        self.setMinimumWidth(820)

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
        self.input_nombre = QLineEdit()
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

        self.vehiculos_table = QTableWidget(0, 2)
        self.vehiculos_table.setHorizontalHeaderLabels(["Patente", "Modelo"])
        self.vehiculos_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.vehiculos_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.vehiculos_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        panel_form.addWidget(self.vehiculos_table)

        form_veh = QHBoxLayout()
        self.input_patente = QLineEdit()
        self.input_patente.setPlaceholderText("Patente")
        self.input_modelo = QLineEdit()
        self.input_modelo.setPlaceholderText("Modelo (opcional)")
        self.btn_agregar_veh = QPushButton("Agregar vehiculo")
        self.btn_eliminar_veh = QPushButton("Eliminar vehiculo")
        self.btn_agregar_veh.setProperty("variant", "success")
        self.btn_eliminar_veh.setProperty("variant", "danger")
        form_veh.addWidget(self.input_patente)
        form_veh.addWidget(self.input_modelo)
        form_veh.addWidget(self.btn_agregar_veh)
        form_veh.addWidget(self.btn_eliminar_veh)
        panel_form.addLayout(form_veh)

        self.btn_crear_contrato = QPushButton("Crear contrato")
        self.btn_crear_contrato.setProperty("variant", "info")
        self.btn_estado_cuenta = QPushButton("Estado de cuenta")
        self.btn_estado_cuenta.setProperty("variant", "info")
        self.btn_historial_clientes = QPushButton("Historial clientes")
        self.btn_historial_clientes.setProperty("variant", "neutral")
        self.btn_recordatorio_whatsapp = QPushButton("Recordatorio WhatsApp")
        self.btn_recordatorio_whatsapp.setProperty("variant", "success")
        acciones_cliente = QHBoxLayout()
        acciones_cliente.addWidget(self.btn_crear_contrato)
        acciones_cliente.addWidget(self.btn_estado_cuenta)
        acciones_cliente.addWidget(self.btn_historial_clientes)
        acciones_cliente.addWidget(self.btn_recordatorio_whatsapp)
        panel_form.addLayout(acciones_cliente)
        self.label_alerta_deuda = QLabel("")
        self.label_alerta_deuda.setStyleSheet("color: #f87171; font-weight: 600;")
        panel_form.addWidget(self.label_alerta_deuda)
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
        self.btn_historial_clientes.clicked.connect(self._abrir_historial_clientes)
        self.btn_recordatorio_whatsapp.clicked.connect(self._enviar_recordatorio_whatsapp)
        self.table.itemSelectionChanged.connect(self._seleccion_changed)
        self.table.cellDoubleClicked.connect(lambda *_: self._crear_contrato_desde_cliente())
        self._sc_f7 = QShortcut(QKeySequence("F7"), self)
        self._sc_f7.setContext(Qt.WindowShortcut)
        self._sc_f7.activated.connect(self._crear_contrato_desde_cliente)

        es_admin = (self.rol or "").upper() == "DUENO"
        if not es_admin:
            self.btn_eliminar.setEnabled(False)
            self.btn_eliminar.setVisible(False)

        self._cargar()
        self._actualizar_snapshot_form()

    def _configurar_enter_navegacion(self):
        self._enter_next_map = {
            self.input_dni: self.input_nombre,
            self.input_nombre: self.input_direccion,
            self.input_direccion: self.input_telefono,
            self.input_telefono: self.input_nacimiento,
            self.input_nacimiento: self.btn_guardar,
            self.input_patente: self.input_modelo,
            self.input_modelo: self.btn_agregar_veh,
        }
        for widget in self._enter_next_map:
            widget.installEventFilter(self)

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

    def _seleccion_changed(self):
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            return
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM clientes WHERE id_cliente = ?", (cliente_id,))
            row = cur.fetchone()
            if not row:
                return
            self.input_dni.setText(row["dni"])
            self.input_nombre.setText(row["nombre"])
            self.input_direccion.setText(row["direccion"] or "")
            self.input_telefono.setText(row["telefono"] or "")
            fecha = QDate.fromString(row["fecha_nacimiento"] or "", "yyyy-MM-dd")
            if fecha.isValid():
                self.input_nacimiento.setDate(fecha)
            self._cargar_vehiculos(cliente_id)
            self._actualizar_alerta_deuda(cliente_id)
            self._actualizar_snapshot_form()
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()

    def _cargar(self):
        self._cargar_filtrado(None)

    def _actualizar_alerta_deuda(self, cliente_id):
        if not cliente_id:
            self.label_alerta_deuda.setText("")
            return
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos "
                "WHERE id_cliente = ? AND activo = 1 "
                "AND date(fecha_vencimiento) < date('now')",
                (cliente_id,),
            )
            vencidos = cur.fetchone()[0] or 0
            if vencidos > 0:
                self.label_alerta_deuda.setText("Cliente con contratos vencidos (deuda pendiente).")
            else:
                self.label_alerta_deuda.setText("")
        except sqlite3.Error:
            self.label_alerta_deuda.setText("")
        finally:
            if conn:
                conn.close()

    def _cargar_filtrado(self, texto):
        self.table.setRowCount(0)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            if texto:
                like = f"%{texto}%"
                cur.execute(
                    "SELECT id_cliente, nombre, dni, telefono, activo "
                    "FROM clientes WHERE nombre LIKE ? OR dni LIKE ? "
                    "ORDER BY nombre",
                    (like, like),
                )
            else:
                cur.execute(
                    "SELECT id_cliente, nombre, dni, telefono, activo FROM clientes ORDER BY nombre"
                )
            for row in cur.fetchall():
                r = self.table.rowCount()
                self.table.insertRow(r)
                item_nombre = QTableWidgetItem(row["nombre"])
                item_nombre.setData(Qt.UserRole, row["id_cliente"])
                self.table.setItem(r, 0, item_nombre)
                self.table.setItem(r, 1, QTableWidgetItem(row["dni"]))
                self.table.setItem(r, 2, QTableWidgetItem(row["telefono"] or ""))
                activo = "SI" if row["activo"] == 1 else "NO"
                self.table.setItem(r, 3, QTableWidgetItem(activo))
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo cargar clientes.")
        finally:
            if conn:
                conn.close()
        self.vehiculos_table.setRowCount(0)

    def _buscar(self):
        texto = self.input_buscar.text().strip()
        self._cargar_filtrado(texto if texto else None)

    def _limpiar_busqueda(self):
        self.input_buscar.clear()
        self._cargar()

    def _snapshot_form(self):
        return {
            "dni": self.input_dni.text().strip(),
            "nombre": self.input_nombre.text().strip(),
            "direccion": self.input_direccion.text().strip(),
            "telefono": self.input_telefono.text().strip(),
            "nacimiento": self.input_nacimiento.date().toString("yyyy-MM-dd"),
            "patente": self.input_patente.text().strip().upper(),
            "modelo": self.input_modelo.text().strip(),
        }

    def _actualizar_snapshot_form(self):
        self._form_snapshot = self._snapshot_form()

    def _hay_cambios_sin_guardar(self):
        base = getattr(self, "_form_snapshot", None)
        if base is None:
            return False
        return self._snapshot_form() != base

    def _nuevo_cliente(self):
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
        self.input_nacimiento.setDate(QDate.currentDate().addYears(-18))
        self.vehiculos_table.setRowCount(0)
        self._actualizar_snapshot_form()

    def _guardar_cliente(self):
        dni = _normalizar_dni(self.input_dni.text())
        nombre = self.input_nombre.text().strip()
        direccion = self.input_direccion.text().strip()
        telefono = _normalizar_telefono(self.input_telefono.text())
        fecha = self.input_nacimiento.date().toString("yyyy-MM-dd")

        if not dni or not nombre:
            QMessageBox.warning(self, "Datos", "DNI y nombre son obligatorios.")
            return False
        if not _validar_dni(dni):
            QMessageBox.warning(self, "DNI", "El DNI debe tener entre 7 y 10 digitos.")
            return False
        if not _validar_telefono(telefono):
            QMessageBox.warning(self, "Telefono", "Telefono invalido.")
            return False
        self.input_dni.setText(dni)
        self.input_telefono.setText(telefono)
        if not _antirebote_iniciar(self, "clientes_guardar"):
            return False

        cliente_id = self._selected_cliente_id()
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
            _auditar(self, accion, f"{nombre} - DNI {dni}")
            self._cargar()
            self._limpiar_form()
            return True
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "DNI", "Ese DNI ya existe.")
            return False
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo guardar el cliente.")
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
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo actualizar el cliente.")
        finally:
            if conn:
                conn.close()

    def _eliminar_cliente(self):
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(self, "Cliente", "Selecciona un cliente.")
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
                cur.execute("DELETE FROM vehiculos WHERE id_cliente = ?", (cliente_id,))
                cur.execute("DELETE FROM clientes WHERE id_cliente = ?", (cliente_id,))
                conn.commit()
                detalle = (
                    f"{self.input_nombre.text().strip()} - DNI {self.input_dni.text().strip()}".strip()
                )
                _auditar(self, "Cliente eliminado", detalle)
                self._cargar()
                self._limpiar_form()
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
                "SELECT id_vehiculo, patente, modelo FROM vehiculos WHERE id_cliente = ?",
                (cliente_id,),
            )
            for row in cur.fetchall():
                r = self.vehiculos_table.rowCount()
                self.vehiculos_table.insertRow(r)
                item = QTableWidgetItem(row["patente"])
                item.setData(Qt.UserRole, row["id_vehiculo"])
                self.vehiculos_table.setItem(r, 0, item)
                self.vehiculos_table.setItem(r, 1, QTableWidgetItem(row["modelo"] or ""))
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()

    def _agregar_vehiculo(self):
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(self, "Cliente", "Selecciona un cliente.")
            return
        patente = _normalizar_patente(self.input_patente.text())
        if not patente:
            return
        if not _validar_patente(patente):
            QMessageBox.warning(self, "Patente", "Formato de patente invalido.")
            return
        self.input_patente.setText(patente)
        if not _antirebote_iniciar(self, "clientes_agregar_vehiculo"):
            return
        modelo = self.input_modelo.text().strip()
        if modelo:
            modelo = " ".join(modelo.split())
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO vehiculos (patente, modelo, id_cliente) VALUES (?, ?, ?)",
                (patente, modelo if modelo else None, cliente_id),
            )
            conn.commit()
            detalle = f"Patente {patente} - DNI {self.input_dni.text().strip()}"
            if modelo:
                detalle = f"{detalle} - Modelo {modelo}"
            _auditar(self, "Vehiculo agregado", detalle)
            self.input_patente.clear()
            self.input_modelo.clear()
            self._cargar_vehiculos(cliente_id)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Patente", "Esa patente ya existe.")
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo agregar el vehiculo.")
        finally:
            if conn:
                conn.close()
            _antirebote_finalizar(self, "clientes_agregar_vehiculo", cooldown_ms=650)

    def _eliminar_vehiculo(self):
        row = self.vehiculos_table.currentRow()
        if row < 0:
            return
        item = self.vehiculos_table.item(row, 0)
        if not item:
            return
        if not _antirebote_iniciar(self, "clientes_eliminar_vehiculo"):
            return
        veh_id = item.data(Qt.UserRole)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM vehiculos WHERE id_vehiculo = ?", (veh_id,))
            conn.commit()
            patente = item.text()
            detalle = f"Patente {patente} - DNI {self.input_dni.text().strip()}"
            _auditar(self, "Vehiculo eliminado", detalle)
            cliente_id = self._selected_cliente_id()
            if cliente_id:
                self._cargar_vehiculos(cliente_id)
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo eliminar el vehiculo.")
        finally:
            if conn:
                conn.close()
            _antirebote_finalizar(self, "clientes_eliminar_vehiculo", cooldown_ms=650)

    def _crear_contrato_desde_cliente(self):
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(self, "Cliente", "Selecciona un cliente.")
            return
        dni = self.input_dni.text().strip()
        if not dni:
            return
        dlg = ContratosDialog(self, rol=self.rol)
        dlg.input_dni.setText(dni)
        dlg.autocompletar()
        dlg.input_espacio.setFocus()
        dlg.exec()

    def _abrir_estado_cuenta(self):
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(self, "Cliente", "Selecciona un cliente.")
            return
        dlg = EstadoCuentaDialog(cliente_id, self)
        dlg.exec()

    def _abrir_historial_clientes(self):
        dni = _normalizar_dni(self.input_dni.text().strip())
        dlg = HistorialDialog(
            self,
            solo_clientes=True,
            dni_objetivo=dni,
        )
        dlg.exec()

    def _resumen_recordatorio_cliente(self, cliente_id):
        conn = None
        data = {
            "nombre": "",
            "telefono": "",
            "deuda_total": 0.0,
            "proximo_vencimiento": "Sin contratos activos",
        }
        hoy = QDate.currentDate()
        proximo = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT nombre, telefono FROM clientes WHERE id_cliente = ?",
                (cliente_id,),
            )
            row_cliente = cur.fetchone()
            if not row_cliente:
                return data
            data["nombre"] = row_cliente["nombre"] or ""
            data["telefono"] = row_cliente["telefono"] or ""

            cur.execute(
                "SELECT fecha_vencimiento, monto_mensual, activo "
                "FROM cochera_contratos WHERE id_cliente = ? "
                "ORDER BY fecha_vencimiento",
                (cliente_id,),
            )
            for row in cur.fetchall():
                activo = int(row["activo"] or 0) == 1
                if not activo:
                    continue
                fecha_venc = QDate.fromString(row["fecha_vencimiento"] or "", "yyyy-MM-dd")
                if not fecha_venc.isValid():
                    continue
                if proximo is None or fecha_venc < proximo:
                    proximo = fecha_venc
                if fecha_venc >= hoy:
                    continue
                meses = 0
                cursor = fecha_venc
                while cursor < hoy and meses < 240:
                    meses += 1
                    cursor = cursor.addMonths(1)
                data["deuda_total"] += float(row["monto_mensual"] or 0.0) * meses
        except sqlite3.Error:
            return data
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

    def _enviar_recordatorio_whatsapp(self):
        cliente_id = self._selected_cliente_id()
        if not cliente_id:
            QMessageBox.warning(self, "WhatsApp", "Selecciona un cliente.")
            return
        data = self._resumen_recordatorio_cliente(cliente_id)
        telefono_wa = _telefono_a_whatsapp(data.get("telefono") or "")
        if not telefono_wa:
            QMessageBox.warning(
                self,
                "WhatsApp",
                "El cliente no tiene telefono valido para WhatsApp.",
            )
            return
        deuda_txt = f"$ {float(data.get('deuda_total') or 0.0):.2f}"
        mensaje = _mensaje_recordatorio_whatsapp(
            data.get("nombre") or "",
            deuda_txt,
            data.get("proximo_vencimiento") or "Sin fecha",
        )
        url = QUrl(f"https://wa.me/{telefono_wa}?text={quote(mensaje)}")
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "WhatsApp", "No se pudo abrir WhatsApp Web.")
            return
        _auditar(
            self,
            "Recordatorio WhatsApp",
            (
                f"Cliente {data.get('nombre') or '-'} - "
                f"DNI {self.input_dni.text().strip()} - "
                f"Telefono {telefono_wa}"
            ),
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
        self.btn_export_pdf = QPushButton("Exportar PDF")
        self.btn_reimprimir = QPushButton("Reimprimir comprobante")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_actualizar.setProperty("variant", "info")
        self.btn_export_pdf.setProperty("variant", "info")
        self.btn_reimprimir.setProperty("variant", "info")
        self.btn_cerrar.setProperty("variant", "neutral")
        acciones.addStretch(1)
        acciones.addWidget(self.btn_actualizar)
        acciones.addWidget(self.btn_export_pdf)
        acciones.addWidget(self.btn_reimprimir)
        acciones.addWidget(self.btn_cerrar)
        layout.addLayout(acciones)

        self.btn_actualizar.clicked.connect(self._cargar)
        self.btn_export_pdf.clicked.connect(self._exportar_pdf)
        self.btn_reimprimir.clicked.connect(self._reimprimir_pago)
        self.btn_cerrar.clicked.connect(self.reject)
        self._cargar()

    @staticmethod
    def _fmt_money(value):
        return f"$ {float(value or 0.0):.2f}"

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
                "SELECT pc.id_pago, pc.fecha_pago, pc.monto, pc.metodo, pc.id_contrato, e.codigo "
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
                        "id_pago": row["id_pago"],
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
            QMessageBox.warning(self, "Estado de cuenta", "No se pudo cargar el estado de cuenta.")
            return

        self.label_cliente.setText(f"Cliente: {data['cliente']}")
        self.label_dni.setText(data["dni"])
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

        self.table_pagos.setRowCount(0)
        for row in data["pagos"]:
            r = self.table_pagos.rowCount()
            self.table_pagos.insertRow(r)
            item_fecha = QTableWidgetItem(row["fecha_pago"])
            item_fecha.setData(Qt.UserRole, row.get("id_pago"))
            self.table_pagos.setItem(r, 0, item_fecha)
            self.table_pagos.setItem(r, 1, QTableWidgetItem(self._fmt_money(row["monto"])))
            self.table_pagos.setItem(r, 2, QTableWidgetItem(row["metodo"]))
            self.table_pagos.setItem(r, 3, QTableWidgetItem(str(row["id_contrato"])))
            self.table_pagos.setItem(r, 4, QTableWidgetItem(row["espacio"]))

    def _reimprimir_pago(self):
        row = self.table_pagos.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Comprobante", "Selecciona un pago.")
            return
        item = self.table_pagos.item(row, 0)
        if not item:
            QMessageBox.warning(self, "Comprobante", "Selecciona un pago.")
            return
        id_pago = item.data(Qt.UserRole)
        if not id_pago:
            QMessageBox.warning(self, "Comprobante", "No se pudo identificar el pago.")
            return
        comprobante = _emitir_comprobante_cochera_pago(id_pago)
        if not comprobante:
            _mostrar_error(self, "Error", "No se pudo generar el comprobante.")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Comprobante")
        box.setText(f"Comprobante generado:\n{Path(comprobante).name}")
        btn_abrir = box.addButton("Abrir comprobante", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() == btn_abrir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(comprobante)))

    def _exportar_pdf(self):
        data = self._consultar()
        if not data:
            QMessageBox.warning(self, "Estado de cuenta", "No se pudo generar el PDF.")
            return
        dni = _normalizar_dni(data.get("dni") or "") or str(self.id_cliente)
        nombre_default = f"estado_cuenta_{dni}_{QDate.currentDate().toString('yyyyMMdd')}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar estado de cuenta PDF",
            str(_reportes_dir() / nombre_default),
            "PDF (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            pdf = QPdfWriter(path)
            pdf.setPageSize(QPageSize(QPageSize.A4))
            pdf.setResolution(144)
            painter = QPainter(pdf)
            if not painter.isActive():
                raise OSError("No se pudo inicializar el generador PDF.")

            margen = 80
            ancho = max(100, int(pdf.width() - (margen * 2)))
            alto = int(pdf.height())
            y = margen

            def escribir(texto, bold=False, size=10, gap=6):
                nonlocal y
                fuente = QFont("Arial", size)
                fuente.setBold(bool(bold))
                painter.setFont(fuente)
                fm = QFontMetrics(fuente)
                h = max(20, fm.height() + 6)
                if y + h > alto - margen:
                    pdf.newPage()
                    y = margen
                painter.drawText(margen, y, ancho, h, Qt.AlignLeft | Qt.AlignVCenter, texto)
                y += h + int(gap)

            escribir("Estado de cuenta", bold=True, size=16, gap=10)
            escribir(f"Cliente: {data.get('cliente') or '-'}", bold=True, size=11, gap=2)
            escribir(f"DNI: {data.get('dni') or '-'}", size=10, gap=10)
            escribir(
                (
                    f"Contratos activos: {data.get('contratos_activos', 0)}  |  "
                    f"Mensual: {self._fmt_money(data.get('mensual'))}  |  "
                    f"Pagado mes: {self._fmt_money(data.get('pagado_mes'))}"
                ),
                size=10,
                gap=2,
            )
            escribir(
                (
                    f"Saldo mes: {self._fmt_money(data.get('saldo_mes'))}  |  "
                    f"Deuda estimada: {self._fmt_money(data.get('deuda'))}  |  "
                    f"Pagado historico: {self._fmt_money(data.get('pagado_total'))}"
                ),
                size=10,
                gap=2,
            )
            escribir(
                f"Proximo vencimiento: {data.get('proximo_vencimiento') or 'Sin contratos activos'}",
                size=10,
                gap=12,
            )

            escribir("Contratos", bold=True, size=12, gap=4)
            contratos = data.get("contratos") or []
            if not contratos:
                escribir("Sin contratos.", size=10, gap=8)
            else:
                for c in contratos:
                    escribir(
                        (
                            f"#{c.get('id_contrato')} | Espacio {c.get('espacio') or '-'} | "
                            f"Mensual {self._fmt_money(c.get('monto'))} | "
                            f"Venc: {c.get('vencimiento') or '-'} | "
                            f"{c.get('estado') or '-'} | "
                            f"Deuda {self._fmt_money(c.get('deuda'))} | "
                            f"Activo: {c.get('activo') or '-'}"
                        ),
                        size=9,
                        gap=2,
                    )
                y += 6

            escribir("Ultimos pagos", bold=True, size=12, gap=4)
            pagos = data.get("pagos") or []
            if not pagos:
                escribir("Sin pagos registrados.", size=10, gap=8)
            else:
                for p in pagos:
                    escribir(
                        (
                            f"{p.get('fecha_pago') or '-'} | {self._fmt_money(p.get('monto'))} | "
                            f"{p.get('metodo') or '-'} | Contrato {p.get('id_contrato') or '-'} | "
                            f"Espacio {p.get('espacio') or '-'}"
                        ),
                        size=9,
                        gap=2,
                    )

            painter.end()

            box = QMessageBox(self)
            box.setWindowTitle("Estado de cuenta")
            box.setIcon(QMessageBox.Information)
            box.setText(f"PDF generado:\n{Path(path).name}")
            btn_abrir = box.addButton("Abrir PDF", QMessageBox.ActionRole)
            btn_carpeta = box.addButton("Abrir carpeta", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Ok)
            box.exec()
            if box.clickedButton() == btn_abrir:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path))))
            elif box.clickedButton() == btn_carpeta:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
        except OSError as e:
            _mostrar_error(self, "Error", f"No se pudo guardar el PDF.\n{e}")


class TarifaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tarifas")
        self.setMinimumWidth(360)
        self._snapshot = None

        layout = QVBoxLayout(self)

        self.label_actual_hora = QLabel("Hora auto actual: sin definir")
        self.label_actual_moto = QLabel("Hora moto actual: sin definir")
        self.label_actual_camioneta = QLabel("Hora camioneta actual: sin definir")
        self.label_actual_mensual = QLabel("Mensual actual: sin definir")

        self.label_nuevo_hora = QLabel("Nuevo precio por hora (auto)")
        self.input_precio_hora = QDoubleSpinBox()
        self.input_precio_hora.setDecimals(2)
        self.input_precio_hora.setRange(0.0, 999999.0)
        self.input_precio_hora.setSingleStep(10.0)
        self.label_nuevo_hora_moto = QLabel("Nuevo precio por hora (moto)")
        self.input_precio_hora_moto = QDoubleSpinBox()
        self.input_precio_hora_moto.setDecimals(2)
        self.input_precio_hora_moto.setRange(0.0, 999999.0)
        self.input_precio_hora_moto.setSingleStep(10.0)
        self.label_nuevo_hora_camioneta = QLabel("Nuevo precio por hora (camioneta)")
        self.input_precio_hora_camioneta = QDoubleSpinBox()
        self.input_precio_hora_camioneta.setDecimals(2)
        self.input_precio_hora_camioneta.setRange(0.0, 999999.0)
        self.input_precio_hora_camioneta.setSingleStep(10.0)
        self.label_nuevo_mensual = QLabel("Nuevo precio mensual cochera")
        self.input_precio_mensual = QDoubleSpinBox()
        self.input_precio_mensual.setDecimals(2)
        self.input_precio_mensual.setRange(0.0, 999999.0)
        self.input_precio_mensual.setSingleStep(100.0)

        layout.addWidget(self.label_actual_hora)
        layout.addWidget(self.label_nuevo_hora)
        layout.addWidget(self.input_precio_hora)
        layout.addWidget(self.label_actual_moto)
        layout.addWidget(self.label_nuevo_hora_moto)
        layout.addWidget(self.input_precio_hora_moto)
        layout.addWidget(self.label_actual_camioneta)
        layout.addWidget(self.label_nuevo_hora_camioneta)
        layout.addWidget(self.input_precio_hora_camioneta)
        layout.addWidget(self.label_actual_mensual)
        layout.addWidget(self.label_nuevo_mensual)
        layout.addWidget(self.input_precio_mensual)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_guardar = QPushButton("Guardar")
        self.btn_cancelar = QPushButton("Cancelar")
        buttons.addWidget(self.btn_guardar)
        buttons.addWidget(self.btn_cancelar)
        layout.addLayout(buttons)

        self.btn_guardar.clicked.connect(self._guardar)
        self.btn_cancelar.clicked.connect(self.reject)

        self._cargar_actual()

    def _snapshot_form(self):
        return (
            round(float(self.input_precio_hora.value()), 2),
            round(float(self.input_precio_hora_moto.value()), 2),
            round(float(self.input_precio_hora_camioneta.value()), 2),
            round(float(self.input_precio_mensual.value()), 2),
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
                "SELECT precio_hora, precio_hora_auto, precio_hora_moto, "
                "precio_hora_camioneta, precio_mensual "
                "FROM tarifas WHERE activa = 1 "
                "ORDER BY fecha_desde DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                valor_hora = _tarifa_hora_desde_row(row, "AUTO")
                valor_moto = _tarifa_hora_desde_row(row, "MOTO")
                valor_camioneta = _tarifa_hora_desde_row(row, "CAMIONETA")
                if valor_hora is None:
                    valor_hora = 0.0
                if valor_moto is None:
                    valor_moto = valor_hora
                if valor_camioneta is None:
                    valor_camioneta = valor_hora
                valor_mensual = float(row["precio_mensual"] or 0)
                self.label_actual_hora.setText(f"Hora auto actual: $ {valor_hora:.2f}")
                self.label_actual_moto.setText(f"Hora moto actual: $ {valor_moto:.2f}")
                self.label_actual_camioneta.setText(
                    f"Hora camioneta actual: $ {valor_camioneta:.2f}"
                )
                self.label_actual_mensual.setText(f"Mensual actual: $ {valor_mensual:.2f}")
                self.input_precio_hora.setValue(valor_hora)
                self.input_precio_hora_moto.setValue(valor_moto)
                self.input_precio_hora_camioneta.setValue(valor_camioneta)
                self.input_precio_mensual.setValue(valor_mensual)
            else:
                self.label_actual_hora.setText("Hora auto actual: sin definir")
                self.label_actual_moto.setText("Hora moto actual: sin definir")
                self.label_actual_camioneta.setText("Hora camioneta actual: sin definir")
                self.label_actual_mensual.setText("Mensual actual: sin definir")
        except sqlite3.Error:
            self.label_actual_hora.setText("Hora auto actual: error al leer")
            self.label_actual_moto.setText("Hora moto actual: error al leer")
            self.label_actual_camioneta.setText("Hora camioneta actual: error al leer")
            self.label_actual_mensual.setText("Mensual actual: error al leer")
        finally:
            if conn:
                conn.close()
        self._actualizar_snapshot()

    def _guardar(self, cerrar=True, mostrar_mensaje=True):
        precio_hora = float(self.input_precio_hora.value())
        precio_hora_moto = float(self.input_precio_hora_moto.value())
        precio_hora_camioneta = float(self.input_precio_hora_camioneta.value())
        precio_mensual = float(self.input_precio_mensual.value())
        if (
            precio_hora <= 0
            or precio_hora_moto <= 0
            or precio_hora_camioneta <= 0
            or precio_mensual <= 0
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
                "precio_hora, precio_hora_auto, precio_hora_moto, "
                "precio_hora_camioneta, precio_mensual, activa"
                ") VALUES (?, ?, ?, ?, ?, 1)",
                (
                    precio_hora,
                    precio_hora,
                    precio_hora_moto,
                    precio_hora_camioneta,
                    precio_mensual,
                ),
            )
            conn.commit()
            _auditar(
                self,
                "Tarifas actualizadas",
                (
                    f"hora_auto={precio_hora:.2f}, "
                    f"hora_moto={precio_hora_moto:.2f}, "
                    f"hora_camioneta={precio_hora_camioneta:.2f}, "
                    f"mensual={precio_mensual:.2f}"
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
            x = round(pos.x() / self.grid) * self.grid
            y = round(pos.y() / self.grid) * self.grid
            rect = self.rect()
            escena = self.scene()
            bounds = escena.sceneRect()
            max_ancho = escena.property("scene_max_width")
            max_alto = escena.property("scene_max_height")
            max_ancho = int(max_ancho) if max_ancho else int(bounds.width())
            max_alto = int(max_alto) if max_alto else int(bounds.height())
            margen_expandir = max(self.grid * 20, 200)
            expandio = False

            limite_derecha = bounds.right() - rect.width()
            limite_abajo = bounds.bottom() - rect.height()
            if x > (limite_derecha - self.grid):
                nuevo_ancho = max(
                    bounds.width(),
                    (x + rect.width() + margen_expandir) - bounds.left(),
                )
                nuevo_ancho = min(nuevo_ancho, max_ancho)
                bounds.setWidth(nuevo_ancho)
                expandio = True
            if y > (limite_abajo - self.grid):
                nuevo_alto = max(
                    bounds.height(),
                    (y + rect.height() + margen_expandir) - bounds.top(),
                )
                nuevo_alto = min(nuevo_alto, max_alto)
                bounds.setHeight(nuevo_alto)
                expandio = True
            if expandio:
                escena.setSceneRect(bounds)
                bounds = escena.sceneRect()

            x = min(max(bounds.left(), x), bounds.right() - rect.width())
            y = min(max(bounds.top(), y), bounds.bottom() - rect.height())
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

        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        self.btn_agregar = QPushButton("Agregar")
        self.btn_renombrar = QPushButton("Renombrar")
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_marcar_cochera = QPushButton("Marcar cochera")
        self.btn_quitar_cochera = QPushButton("Quitar cochera")
        self.btn_colores = QPushButton("Colores")
        self.btn_zoom_in = QPushButton("Acercar +")
        self.btn_zoom_out = QPushButton("Alejar -")
        self.btn_zoom_reset = QPushButton("Escala 100%")
        self.btn_alinear = QPushButton("Alinear")
        self.btn_guardar = QPushButton("Guardar")
        self.btn_recargar = QPushButton("Limpiar")
        self.btn_agregar.setProperty("variant", "success")
        self.btn_renombrar.setProperty("variant", "warning")
        self.btn_eliminar.setProperty("variant", "danger")
        self.btn_marcar_cochera.setProperty("variant", "info")
        self.btn_quitar_cochera.setProperty("variant", "warning")
        self.btn_colores.setProperty("variant", "info")
        self.btn_zoom_in.setProperty("variant", "neutral")
        self.btn_zoom_out.setProperty("variant", "neutral")
        self.btn_zoom_reset.setProperty("variant", "neutral")
        self.btn_alinear.setProperty("variant", "neutral")
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

        zoom_col = QVBoxLayout()
        zoom_col.addWidget(self.btn_zoom_in)
        zoom_col.addWidget(self.btn_zoom_out)
        zoom_col.addWidget(self.btn_zoom_reset)
        zoom_col.addWidget(self.btn_alinear)
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
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        self.btn_zoom_reset.clicked.connect(self._zoom_reset)
        self.btn_alinear.clicked.connect(self._alinear_items)
        self.btn_guardar.clicked.connect(self._guardar)
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
            self.btn_alinear.setEnabled(False)

        self._configurar_atajos()
        self._cargar()

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

    def _items_espacios_ordenados(self):
        items = [item for item in self.scene.items() if isinstance(item, EspacioItem)]
        items.sort(key=lambda it: (it.codigo or "").upper())
        return items

    def _posicion_predeterminada(self, indice, ancho=80, alto=50):
        col_max = 8
        sep_x = int(ancho) + 20
        sep_y = int(alto) + 20
        x = 20 + (int(indice) % col_max) * sep_x
        y = 20 + (int(indice) // col_max) * sep_y
        return x, y

    def _alinear_items(self, mostrar_mensaje=True):
        items = self._items_espacios_ordenados()
        if not items:
            return
        for idx, item in enumerate(items):
            rect = item.rect()
            x, y = self._posicion_predeterminada(idx, rect.width(), rect.height())
            item.setPos(x, y)
        self._set_mapa_dirty(True)
        self._actualizar_area_trabajo()
        if mostrar_mensaje:
            QMessageBox.information(self, "Mapa", "Espacios alineados.")

    def _agregar(self):
        codigo, ok = QInputDialog.getText(self, "Nuevo espacio", "Codigo (ej: A1)")
        if not ok:
            return
        codigo = codigo.strip().upper()
        if not codigo:
            return
        if self._codigo_en_escena(codigo):
            QMessageBox.warning(self, "Codigo", "Ese codigo ya existe en el mapa.")
            return

        size = QRectF(0, 0, 80, 50)
        item = EspacioItem(codigo, size, self._color_libre, estado="LIBRE", grid=self._grid)
        idx_nuevo = len(self._items_espacios_ordenados())
        x, y = self._posicion_predeterminada(idx_nuevo, size.width(), size.height())
        item.setPos(x, y)
        if not self._editable:
            item.setFlags(QGraphicsItem.ItemIsSelectable)
        self.scene.addItem(item)
        self._set_mapa_dirty(True)
        self._actualizar_area_trabajo()

    def _renombrar(self):
        item = self._item_seleccionado()
        if not item:
            QMessageBox.warning(self, "Seleccion", "Selecciona un rectangulo.")
            return
        nuevo, ok = QInputDialog.getText(self, "Renombrar", "Nuevo codigo")
        if not ok:
            return
        nuevo = nuevo.strip().upper()
        if not nuevo:
            return
        if self._codigo_en_escena(nuevo):
            QMessageBox.warning(self, "Codigo", "Ese codigo ya existe en el mapa.")
            return
        item.set_codigo(nuevo)
        self._set_mapa_dirty(True)

    def _eliminar(self):
        item = self._item_seleccionado()
        if not item:
            return
        confirmar = QMessageBox.question(
            self,
            "Eliminar",
            "Eliminar del mapa? (no borra datos de clientes)",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirmar != QMessageBox.Yes:
            return
        self._eliminados.add(item.codigo)
        self.scene.removeItem(item)
        self._set_mapa_dirty(True)

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
                QMessageBox.warning(self, "Desocupar", "Ese espacio no existe en la base.")
                return
            id_espacio = row["id_espacio"]

            cur.execute(
                "SELECT m.id_movimiento, m.fecha_ingreso, m.tipo_vehiculo, v.patente "
                "FROM movimientos m "
                "JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
                "WHERE m.id_espacio = ? AND m.fecha_salida IS NULL "
                "ORDER BY m.fecha_ingreso",
                (id_espacio,),
            )
            movimientos_activos = cur.fetchall()
            mov_activos = len(movimientos_activos)

            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos WHERE id_espacio = ? AND activo = 1",
                (id_espacio,),
            )
            contratos_activos = cur.fetchone()[0] or 0

            tiene_cliente = row["id_cliente"] is not None
            if mov_activos == 0 and contratos_activos == 0 and not tiene_cliente:
                QMessageBox.information(self, "Desocupar", "Ese espacio ya esta libre.")
                return

            tarifa_hora = None
            tarifa_row = None
            if mov_activos > 0:
                cur.execute(
                    "SELECT precio_hora, precio_hora_auto, precio_hora_moto, "
                    "precio_hora_camioneta "
                    "FROM tarifas WHERE activa = 1 "
                    "ORDER BY fecha_desde DESC LIMIT 1"
                )
                tarifa_row = cur.fetchone()
                tarifa_hora = _tarifa_hora_desde_row(tarifa_row, "AUTO")
                if tarifa_row is None or tarifa_hora is None:
                    QMessageBox.warning(
                        self,
                        "Desocupar",
                        "No hay tarifas por hora definidas para calcular el precio.",
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
                    tipo_mov = _normalizar_tipo_vehiculo(mov["tipo_vehiculo"])
                    tarifa_mov = _tarifa_hora_desde_row(tarifa_row, tipo_mov)
                    if tarifa_mov is None:
                        QMessageBox.warning(
                            self,
                            "Desocupar",
                            "No hay tarifa por hora definida para "
                            f"{_label_tipo_vehiculo(tipo_mov).lower()}.",
                        )
                        return
                    dt_ing = _parse_fecha_db(fecha_ingreso)
                    if not dt_ing:
                        dt_ing = salida_dt
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
                        "INSERT INTO pagos (id_movimiento, monto, metodo, ref_externa, usuario) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            mov["id_movimiento"],
                            total,
                            "Mapa",
                            None,
                            (_usuario_desde_widget(self) or "").strip() or None,
                        ),
                    )

                    ingreso_txt = dt_ing.strftime("%d/%m/%Y %H:%M:%S")
                    detalle_salida.append(
                        (
                            mov["patente"] or "-",
                            ingreso_txt,
                            salida_txt,
                            total,
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
                for patente, ingreso_txt, salida_txt, total in detalle_salida:
                    bloques.append(
                        f"Patente: {patente}\n"
                        f"Ingreso: {ingreso_txt}\n"
                        f"Salida: {salida_txt}\n"
                        f"Precio: $ {total:.2f}"
                    )
                detalle_txt = "\n\n".join(bloques)
                QMessageBox.information(
                    self,
                    "Desocupar",
                    f"Espacio {codigo} desocupado.\n\n{detalle_txt}",
                )
            else:
                QMessageBox.information(self, "Desocupar", f"Espacio {codigo} desocupado.")
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
                "COALESCE(e.es_reservado, 0), "
                "COALESCE(e.id_cliente, cc_act.id_cliente), "
                "CASE WHEN mv.id_movimiento IS NULL THEN 0 ELSE 1 END, "
                "v.patente, c.nombre "
                "FROM espacios_mapa m "
                "LEFT JOIN espacios e ON e.codigo = m.codigo "
                "LEFT JOIN ("
                "SELECT c1.id_espacio, c1.id_cliente "
                "FROM cochera_contratos c1 "
                "WHERE c1.activo = 1 "
                "AND c1.id_contrato = ("
                "SELECT MAX(c2.id_contrato) "
                "FROM cochera_contratos c2 "
                "WHERE c2.id_espacio = c1.id_espacio AND c2.activo = 1"
                ")"
                ") cc_act ON cc_act.id_espacio = e.id_espacio "
                "LEFT JOIN movimientos mv ON mv.id_espacio = e.id_espacio AND mv.fecha_salida IS NULL "
                "LEFT JOIN vehiculos v ON v.id_vehiculo = mv.id_vehiculo "
                "LEFT JOIN clientes c ON c.id_cliente = COALESCE(e.id_cliente, cc_act.id_cliente) "
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
                    info = patente
                elif (id_cliente is not None or es_reservado == 1) and nombre:
                    partes = [p for p in nombre.strip().split() if p]
                    info = partes[-1] if partes else nombre
                elif es_reservado == 1:
                    info = "Reservado"
                item.set_info(info)
                item.setPos(x, y)
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
            respuesta = _confirmar_guardado_pendiente(
                self,
                "Hay cambios en el mapa.\nQuieres guardarlos antes de limpiar?",
            )
            if respuesta == QMessageBox.Cancel:
                return
            if respuesta == QMessageBox.Yes and not self._guardar(mostrar_mensaje=False):
                return
        self._cargar()

    def _set_cochera(self, valor):
        item = self._item_seleccionado()
        if not item:
            QMessageBox.warning(self, "Cochera", "Selecciona un rectangulo.")
            return
        codigo = item.codigo
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
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
                        "No se puede marcar como cochera porque el espacio esta ocupado.",
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
            info = patente
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
                "COALESCE(e.id_cliente, cc_act.id_cliente) AS id_cliente, "
                "CASE WHEN mv.id_movimiento IS NULL THEN 0 ELSE 1 END AS ocupado, "
                "v.patente, c.nombre "
                "FROM espacios_mapa m "
                "LEFT JOIN espacios e ON e.codigo = m.codigo "
                "LEFT JOIN ("
                "SELECT c1.id_espacio, c1.id_cliente "
                "FROM cochera_contratos c1 "
                "WHERE c1.activo = 1 "
                "AND c1.id_contrato = ("
                "SELECT MAX(c2.id_contrato) "
                "FROM cochera_contratos c2 "
                "WHERE c2.id_espacio = c1.id_espacio AND c2.activo = 1"
                ")"
                ") cc_act ON cc_act.id_espacio = e.id_espacio "
                "LEFT JOIN movimientos mv ON mv.id_espacio = e.id_espacio AND mv.fecha_salida IS NULL "
                "LEFT JOIN vehiculos v ON v.id_vehiculo = mv.id_vehiculo "
                "LEFT JOIN clientes c ON c.id_cliente = COALESCE(e.id_cliente, cc_act.id_cliente)"
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
                info = row["patente"]
            elif (row["id_cliente"] is not None or row["es_reservado"] == 1) and row["nombre"]:
                partes = [p for p in row["nombre"].strip().split() if p]
                info = partes[-1] if partes else row["nombre"]
            elif row["es_reservado"] == 1:
                info = "Reservado"
            item.set_info(info)

    def _guardar(self, mostrar_mensaje=True):
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
                QMessageBox.information(self, "Mapa", "Mapa guardado.")
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
        self.setWindowTitle("Vencimientos proximos")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        self.label_resumen = QLabel("Total proximos: 0")
        layout.addWidget(self.label_resumen)

        self.lista = QListWidget()
        layout.addWidget(self.lista)

        self._cargar()

    def _cargar(self):
        self.lista.clear()
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
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
            rows = cur.fetchall()
            for nombre, fecha in rows:
                self.lista.addItem(f"{nombre} - {fecha}")
            self.label_resumen.setText(f"Total proximos: {len(rows)}")
        except sqlite3.Error:
            self.label_resumen.setText("No disponible (falta tabla de contratos)")
        finally:
            if conn:
                conn.close()


class HistorialContratoDialog(QDialog):
    def __init__(self, id_contrato, parent=None):
        super().__init__(parent)
        self.id_contrato = id_contrato
        self.setWindowTitle(f"Historial contrato {id_contrato}")
        self.setMinimumWidth(720)
        self.setMinimumHeight(420)

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Fecha", "Usuario", "Accion", "Detalle"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        acciones = QHBoxLayout()
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_actualizar.setProperty("variant", "info")
        self.btn_cerrar.setProperty("variant", "neutral")
        acciones.addStretch(1)
        acciones.addWidget(self.btn_actualizar)
        acciones.addWidget(self.btn_cerrar)
        layout.addLayout(acciones)

        self.btn_actualizar.clicked.connect(self._cargar)
        self.btn_cerrar.clicked.connect(self.reject)
        self._cargar()

    def _cargar(self):
        self.table.setRowCount(0)
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT fecha, usuario, accion, detalle FROM auditoria "
                "WHERE detalle LIKE ? "
                "ORDER BY fecha DESC",
                (f"%Contrato {self.id_contrato}%",),
            )
            for row in cur.fetchall():
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(row["fecha"] or ""))
                self.table.setItem(r, 1, QTableWidgetItem(row["usuario"] or ""))
                self.table.setItem(r, 2, QTableWidgetItem(row["accion"] or ""))
                self.table.setItem(r, 3, QTableWidgetItem(row["detalle"] or ""))
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo cargar el historial.")
        finally:
            if conn:
                conn.close()


class HistorialDialog(QDialog):
    def __init__(self, parent=None, solo_clientes=False, dni_objetivo=""):
        super().__init__(parent)
        self._solo_clientes = bool(solo_clientes)
        self._dni_objetivo = _normalizar_dni(dni_objetivo)
        if self._solo_clientes:
            self.setWindowTitle("Historial de clientes")
        else:
            self.setWindowTitle("Historial de cambios")
        self.setMinimumWidth(860)

        layout = QVBoxLayout(self)
        filtro = QHBoxLayout()
        self.input_buscar = QLineEdit()
        if self._solo_clientes:
            self.input_buscar.setPlaceholderText("Buscar por usuario, accion o detalle de cliente")
        else:
            self.input_buscar.setPlaceholderText("Buscar por usuario, accion o detalle")
        filtro.addWidget(self.input_buscar)
        filtro.addWidget(QLabel("Desde"))
        self.input_desde = QDateEdit()
        self.input_desde.setCalendarPopup(True)
        self.input_desde.setDisplayFormat("dd/MM/yyyy")
        self.input_desde.setDate(QDate.currentDate().addDays(-30))
        filtro.addWidget(self.input_desde)
        filtro.addWidget(QLabel("Hasta"))
        self.input_hasta = QDateEdit()
        self.input_hasta.setCalendarPopup(True)
        self.input_hasta.setDisplayFormat("dd/MM/yyyy")
        self.input_hasta.setDate(QDate.currentDate())
        filtro.addWidget(self.input_hasta)
        self.btn_export_csv = QPushButton("Exportar CSV")
        self.btn_export_csv.setProperty("variant", "info")
        filtro.addWidget(self.btn_export_csv)
        layout.addLayout(filtro)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Fecha", "Usuario", "Accion", "Detalle"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        self._rows_cache = []
        self.input_buscar.textChanged.connect(self._cargar)
        self.input_desde.dateChanged.connect(self._cargar)
        self.input_hasta.dateChanged.connect(self._cargar)
        self.btn_export_csv.clicked.connect(self._exportar_csv)
        self._cargar()

    def _periodo(self):
        desde = self.input_desde.date()
        hasta = self.input_hasta.date()
        if desde.toJulianDay() > hasta.toJulianDay():
            desde, hasta = hasta, desde
            self.input_desde.setDate(desde)
            self.input_hasta.setDate(hasta)
        return desde.toString("yyyy-MM-dd"), hasta.toString("yyyy-MM-dd")

    def _cargar(self):
        texto = self.input_buscar.text().strip()
        self.table.setRowCount(0)
        self._rows_cache = []
        desde_key, hasta_key = self._periodo()
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            condiciones = ["date(fecha) BETWEEN date(?) AND date(?)"]
            params = [desde_key, hasta_key]
            if self._solo_clientes:
                condiciones.append("(accion LIKE 'Cliente %' OR accion LIKE 'Vehiculo %')")
            if self._dni_objetivo:
                condiciones.append("detalle LIKE ?")
                params.append(f"%DNI {self._dni_objetivo}%")
            if texto:
                like = f"%{texto}%"
                condiciones.append("(usuario LIKE ? OR accion LIKE ? OR detalle LIKE ?)")
                params.extend([like, like, like])
            where = " AND ".join(condiciones)
            cur.execute(
                "SELECT fecha, usuario, accion, detalle FROM auditoria "
                f"WHERE {where} "
                "ORDER BY fecha DESC LIMIT 1200",
                tuple(params),
            )
            self._rows_cache = [dict(row) for row in cur.fetchall()]
            for row in self._rows_cache:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(row["fecha"] or ""))
                self.table.setItem(r, 1, QTableWidgetItem(row["usuario"] or ""))
                self.table.setItem(r, 2, QTableWidgetItem(row["accion"] or ""))
                self.table.setItem(r, 3, QTableWidgetItem(row["detalle"] or ""))
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()

    def _exportar_csv(self):
        desde_key, hasta_key = self._periodo()
        nombre_default = f"historial_{desde_key}_a_{hasta_key}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar historial CSV",
            str(_reportes_dir() / nombre_default),
            "CSV (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["Historial de clientes" if self._solo_clientes else "Historial de cambios"]
                )
                writer.writerow(["Desde", desde_key])
                writer.writerow(["Hasta", hasta_key])
                if self._dni_objetivo:
                    writer.writerow(["DNI objetivo", self._dni_objetivo])
                writer.writerow(["Buscar", self.input_buscar.text().strip()])
                writer.writerow([])
                writer.writerow(["Fecha", "Usuario", "Accion", "Detalle"])
                for row in self._rows_cache:
                    writer.writerow(
                        [
                            row.get("fecha") or "",
                            row.get("usuario") or "",
                            row.get("accion") or "",
                            row.get("detalle") or "",
                        ]
                    )
            QMessageBox.information(self, "Historial", f"CSV guardado:\n{Path(path).name}")
        except OSError:
            _mostrar_error(self, "Error", "No se pudo guardar el CSV del historial.")


class ReportesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reportes")
        self.setMinimumWidth(720)

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
        filtros.addWidget(self.combo_tipo)
        filtros.addWidget(QLabel("Metodo"))
        self.combo_metodo = QComboBox()
        self.combo_metodo.addItems(["Todos", "Efectivo", "Transferencia", "Tarjeta", "QR", "Otro"])
        filtros.addWidget(self.combo_metodo)
        filtros.addWidget(QLabel("Usuario"))
        self.input_usuario = QLineEdit()
        self.input_usuario.setPlaceholderText("Usuario que registró")
        filtros.addWidget(self.input_usuario)
        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText("Buscar cliente/patente/espacio")
        filtros.addWidget(self.input_buscar)
        filtros.addStretch(1)
        layout.addLayout(filtros)

        filtros_extra = QHBoxLayout()
        filtros_extra.addWidget(QLabel("Tipo vehiculo"))
        self.combo_tipo_vehiculo = QComboBox()
        self.combo_tipo_vehiculo.addItems(
            ["Todos", "Auto", "Moto", "Camioneta", "Sin vehiculo (cochera)"]
        )
        filtros_extra.addWidget(self.combo_tipo_vehiculo)
        self.check_hora = QCheckBox("Filtrar por hora")
        filtros_extra.addWidget(self.check_hora)
        filtros_extra.addWidget(QLabel("Desde"))
        self.input_hora_desde = QTimeEdit()
        self.input_hora_desde.setDisplayFormat("HH:mm")
        self.input_hora_desde.setTime(QTime(0, 0))
        filtros_extra.addWidget(self.input_hora_desde)
        filtros_extra.addWidget(QLabel("Hasta"))
        self.input_hora_hasta = QTimeEdit()
        self.input_hora_hasta.setDisplayFormat("HH:mm")
        self.input_hora_hasta.setTime(QTime(23, 59))
        filtros_extra.addWidget(self.input_hora_hasta)
        filtros_extra.addStretch(1)
        layout.addLayout(filtros_extra)
        self.input_hora_desde.setEnabled(False)
        self.input_hora_hasta.setEnabled(False)

        self.table_historial = QTableWidget(0, 10)
        self.table_historial.setHorizontalHeaderLabels(
            [
                "Tipo",
                "Fecha",
                "Monto",
                "Metodo",
                "Usuario",
                "Tipo vehiculo",
                "Cliente",
                "Patente",
                "Espacio",
                "ID",
            ]
        )
        self.table_historial.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_historial.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_historial.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table_historial)

        acciones = QHBoxLayout()
        self.btn_export_csv = QPushButton("Exportar CSV")
        self.btn_export_excel = QPushButton("Exportar Excel")
        self.btn_export_pagos = QPushButton("Exportar pagos mensuales")
        self.btn_export_pagos.setProperty("variant", "info")
        acciones.addWidget(self.btn_export_csv)
        acciones.addWidget(self.btn_export_excel)
        acciones.addWidget(self.btn_export_pagos)
        acciones.addStretch(1)
        layout.addLayout(acciones)

        self.btn_actualizar.clicked.connect(self._cargar)
        self.input_desde.dateChanged.connect(self._cargar)
        self.input_hasta.dateChanged.connect(self._cargar)
        self.btn_export_csv.clicked.connect(self._exportar_csv)
        self.btn_export_excel.clicked.connect(self._exportar_excel)
        self.btn_export_pagos.clicked.connect(self._exportar_pagos_mensuales)
        self.combo_tipo.currentIndexChanged.connect(self._aplicar_filtros)
        self.combo_metodo.currentIndexChanged.connect(self._aplicar_filtros)
        self.combo_tipo_vehiculo.currentIndexChanged.connect(self._aplicar_filtros)
        self.input_usuario.textChanged.connect(self._aplicar_filtros)
        self.input_buscar.textChanged.connect(self._aplicar_filtros)
        self.check_hora.toggled.connect(self._aplicar_filtros)
        self.check_hora.toggled.connect(self.input_hora_desde.setEnabled)
        self.check_hora.toggled.connect(self.input_hora_hasta.setEnabled)
        self.input_hora_desde.timeChanged.connect(self._aplicar_filtros)
        self.input_hora_hasta.timeChanged.connect(self._aplicar_filtros)
        self._cargar()

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
        self.label_cochera_value.setText(f"$ {cochera:.2f}")
        self.label_est_value.setText(f"$ {estacionamiento:.2f}")
        self.label_total_value.setText(f"$ {total:.2f}")

    def _detalle_filtrado(self):
        detalle = list(self._detalle_cache or [])
        tipo = self.combo_tipo.currentText()
        if tipo != "Todos":
            detalle = [r for r in detalle if r["tipo"] == tipo]

        metodo = self.combo_metodo.currentText()
        if metodo != "Todos":
            detalle = [r for r in detalle if r["metodo"] == metodo]

        usuario_txt = self.input_usuario.text().strip().lower()
        if usuario_txt:
            detalle = [r for r in detalle if usuario_txt in (r.get("usuario") or "").lower()]

        tipo_vehiculo = self.combo_tipo_vehiculo.currentText()
        if tipo_vehiculo == "Auto":
            detalle = [
                r
                for r in detalle
                if str(r.get("tipo_vehiculo") or "").strip().upper() == "AUTO"
            ]
        elif tipo_vehiculo == "Moto":
            detalle = [
                r
                for r in detalle
                if str(r.get("tipo_vehiculo") or "").strip().upper() == "MOTO"
            ]
        elif tipo_vehiculo == "Camioneta":
            detalle = [
                r
                for r in detalle
                if str(r.get("tipo_vehiculo") or "").strip().upper() == "CAMIONETA"
            ]
        elif tipo_vehiculo == "Sin vehiculo (cochera)":
            detalle = [
                r
                for r in detalle
                if not str(r.get("tipo_vehiculo") or "").strip()
            ]

        if self.check_hora.isChecked():
            hora_desde = self.input_hora_desde.time()
            hora_hasta = self.input_hora_hasta.time()
            detalle_hora = []
            for r in detalle:
                dt = _parse_fecha_db(r.get("fecha_pago") or "")
                if not dt:
                    continue
                qh = QTime(dt.hour, dt.minute)
                if _hora_en_rango(qh, hora_desde, hora_hasta):
                    detalle_hora.append(r)
            detalle = detalle_hora

        texto = self.input_buscar.text().strip().lower()
        if texto:
            detalle = [
                r
                for r in detalle
                if texto in (r["cliente"] or "").lower()
                or texto in (r["patente"] or "").lower()
                or texto in (r["espacio"] or "").lower()
                or texto in (r.get("usuario") or "").lower()
            ]

        detalle.sort(key=lambda r: r["fecha_pago"] or "", reverse=True)
        return detalle

    def _aplicar_filtros(self):
        detalle = self._detalle_filtrado()
        self._actualizar_resumen(detalle)
        self.table_historial.setRowCount(0)
        for row in detalle:
            r = self.table_historial.rowCount()
            self.table_historial.insertRow(r)
            self.table_historial.setItem(r, 0, QTableWidgetItem(row["tipo"]))
            self.table_historial.setItem(r, 1, QTableWidgetItem(row["fecha_pago"]))
            self.table_historial.setItem(
                r, 2, QTableWidgetItem(f"$ {row['monto']:.2f}")
            )
            self.table_historial.setItem(r, 3, QTableWidgetItem(row["metodo"]))
            self.table_historial.setItem(r, 4, QTableWidgetItem(row.get("usuario") or ""))
            tipo_veh_txt = row.get("tipo_vehiculo") or ""
            if tipo_veh_txt:
                tipo_veh_txt = _label_tipo_vehiculo(tipo_veh_txt)
            self.table_historial.setItem(r, 5, QTableWidgetItem(tipo_veh_txt))
            self.table_historial.setItem(r, 6, QTableWidgetItem(row["cliente"]))
            self.table_historial.setItem(r, 7, QTableWidgetItem(row["patente"]))
            self.table_historial.setItem(r, 8, QTableWidgetItem(row["espacio"]))
            id_val = row["contrato_id"] or row["movimiento_id"] or ""
            self.table_historial.setItem(r, 9, QTableWidgetItem(str(id_val)))

    def _mostrar_export_ok(self, path, titulo="Reporte"):
        destino = Path(path)
        box = QMessageBox(self)
        box.setWindowTitle(titulo)
        box.setIcon(QMessageBox.Information)
        box.setText(f"Archivo exportado correctamente.\n{destino.name}")
        btn_abrir = box.addButton("Abrir archivo", QMessageBox.ActionRole)
        btn_carpeta = box.addButton("Abrir carpeta", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() == btn_abrir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(destino)))
        elif box.clickedButton() == btn_carpeta:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(destino.parent)))

    def _exportar_csv(self):
        desde_key, hasta_key = self._periodo()
        nombre_default = f"reporte_{desde_key}_a_{hasta_key}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar reporte CSV",
            str(_reportes_dir() / nombre_default),
            "CSV (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        detalle = self._detalle_filtrado()
        cochera = self._sum_monto(detalle, "Cochera")
        estacionamiento = self._sum_monto(detalle, "Estacionamiento")
        total = cochera + estacionamiento
        cantidad_operaciones = len(detalle)
        ticket_promedio = (total / cantidad_operaciones) if cantidad_operaciones else 0.0

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Reporte", f"{desde_key} a {hasta_key}"])
                writer.writerow(["Filtro tipo", self.combo_tipo.currentText()])
                writer.writerow(["Filtro metodo", self.combo_metodo.currentText()])
                writer.writerow(["Filtro usuario", self.input_usuario.text().strip()])
                writer.writerow(["Filtro tipo vehiculo", self.combo_tipo_vehiculo.currentText()])
                if self.check_hora.isChecked():
                    writer.writerow(
                        [
                            "Filtro hora",
                            (
                                f"{self.input_hora_desde.time().toString('HH:mm')} - "
                                f"{self.input_hora_hasta.time().toString('HH:mm')}"
                            ),
                        ]
                    )
                else:
                    writer.writerow(["Filtro hora", "No aplicado"])
                writer.writerow(["Buscar", self.input_buscar.text().strip()])
                writer.writerow([])
                writer.writerow(["Ingresos cochera", f"{cochera:.2f}"])
                writer.writerow(["Ingresos estacionamiento", f"{estacionamiento:.2f}"])
                writer.writerow(["Total", f"{total:.2f}"])
                writer.writerow([])
                writer.writerow(
                    [
                        "Tipo",
                        "Fecha pago",
                        "Monto",
                        "Metodo",
                        "Usuario",
                        "Tipo vehiculo",
                        "Cliente",
                        "Patente",
                        "Espacio",
                        "Contrato ID",
                        "Movimiento ID",
                    ]
                )
                for row in detalle:
                    writer.writerow(
                        [
                            row["tipo"],
                            row["fecha_pago"],
                            f"{row['monto']:.2f}",
                            row["metodo"],
                            row.get("usuario") or "",
                            _label_tipo_vehiculo(row.get("tipo_vehiculo"))
                            if row.get("tipo_vehiculo")
                            else "",
                            row["cliente"],
                            row["patente"],
                            row["espacio"],
                            row["contrato_id"],
                            row["movimiento_id"],
                        ]
                    )
            self._mostrar_export_ok(path, "Reporte")
        except OSError:
            _mostrar_error(self, "Error", "No se pudo guardar el CSV.")

    def _exportar_excel(self):
        try:
            import xlsxwriter
        except ImportError:
            QMessageBox.warning(
                self,
                "Excel",
                "Para exportar a Excel necesitas instalar xlsxwriter.\n"
                "Puedes usar CSV por ahora.",
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
        cochera = self._sum_monto(detalle, "Cochera")
        estacionamiento = self._sum_monto(detalle, "Estacionamiento")
        total = cochera + estacionamiento
        cantidad_operaciones = len(detalle)
        ticket_promedio = (total / cantidad_operaciones) if cantidad_operaciones else 0.0

        try:
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                _mostrar_error(
                    self,
                    "Error",
                    f"No se pudo crear la carpeta de destino.\n{e}",
                )
                return
            workbook = xlsxwriter.Workbook(path)
            fmt_titulo = workbook.add_format(
                {"bold": True, "font_size": 14, "bg_color": "#E2E8F0", "border": 1}
            )
            fmt_subtitulo = workbook.add_format({"bold": True, "font_size": 10})
            fmt_label = workbook.add_format({"bold": True, "bg_color": "#F8FAFC", "border": 1})
            fmt_celda = workbook.add_format({"border": 1})
            fmt_header = workbook.add_format(
                {"bold": True, "font_color": "#FFFFFF", "bg_color": "#2563EB", "border": 1}
            )
            fmt_moneda = workbook.add_format({"num_format": "$ #,##0.00", "border": 1})
            fmt_texto = workbook.add_format({"border": 1})
            fmt_fecha = workbook.add_format({"border": 1})

            ws_resumen = workbook.add_worksheet("Resumen")
            ws_resumen.set_column("A:A", 28)
            ws_resumen.set_column("B:B", 30)
            ws_resumen.merge_range("A1:B1", "Reporte de ingresos", fmt_titulo)
            ws_resumen.write("A3", "Desde", fmt_label)
            ws_resumen.write("B3", desde_key, fmt_celda)
            ws_resumen.write("A4", "Hasta", fmt_label)
            ws_resumen.write("B4", hasta_key, fmt_celda)
            ws_resumen.write("A6", "Filtro tipo", fmt_label)
            ws_resumen.write("B6", self.combo_tipo.currentText(), fmt_celda)
            ws_resumen.write("A7", "Filtro metodo", fmt_label)
            ws_resumen.write("B7", self.combo_metodo.currentText(), fmt_celda)
            ws_resumen.write("A8", "Filtro usuario", fmt_label)
            ws_resumen.write("B8", self.input_usuario.text().strip(), fmt_celda)
            ws_resumen.write("A9", "Filtro tipo vehiculo", fmt_label)
            ws_resumen.write("B9", self.combo_tipo_vehiculo.currentText(), fmt_celda)
            ws_resumen.write("A10", "Filtro hora", fmt_label)
            if self.check_hora.isChecked():
                ws_resumen.write(
                    "B10",
                    (
                        f"{self.input_hora_desde.time().toString('HH:mm')} - "
                        f"{self.input_hora_hasta.time().toString('HH:mm')}"
                    ),
                    fmt_celda,
                )
            else:
                ws_resumen.write("B10", "No aplicado", fmt_celda)
            ws_resumen.write("A11", "Buscar", fmt_label)
            ws_resumen.write("B11", self.input_buscar.text().strip(), fmt_celda)
            ws_resumen.write("A13", "Ingresos cochera", fmt_label)
            ws_resumen.write_number("B13", cochera, fmt_moneda)
            ws_resumen.write("A14", "Ingresos estacionamiento", fmt_label)
            ws_resumen.write_number("B14", estacionamiento, fmt_moneda)
            ws_resumen.write("A15", "Total", fmt_label)
            ws_resumen.write_number("B15", total, fmt_moneda)
            ws_resumen.write("A16", "Operaciones", fmt_label)
            ws_resumen.write_number("B16", cantidad_operaciones, fmt_celda)
            ws_resumen.write("A17", "Ticket promedio", fmt_label)
            ws_resumen.write_number("B17", ticket_promedio, fmt_moneda)

            ws_metodos = workbook.add_worksheet("Por metodo")
            ws_metodos.set_column("A:A", 22)
            ws_metodos.set_column("B:B", 20)
            ws_metodos.write("A1", "Metodo", fmt_header)
            ws_metodos.write("B1", "Total", fmt_header)
            totales_metodo = {}
            for row in detalle:
                metodo = row.get("metodo") or "Sin metodo"
                totales_metodo[metodo] = float(totales_metodo.get(metodo, 0.0)) + float(
                    row.get("monto") or 0.0
                )
            fila_metodo = 1
            for metodo, monto in sorted(totales_metodo.items(), key=lambda x: x[0]):
                ws_metodos.write(fila_metodo, 0, metodo, fmt_texto)
                ws_metodos.write_number(fila_metodo, 1, float(monto), fmt_moneda)
                fila_metodo += 1
            ws_metodos.write(fila_metodo, 0, "Total", fmt_label)
            ws_metodos.write_number(fila_metodo, 1, float(total), fmt_moneda)

            ws_vista = workbook.add_worksheet("Vista reporte")
            headers_vista = []
            for col in range(self.table_historial.columnCount()):
                hdr = self.table_historial.horizontalHeaderItem(col)
                headers_vista.append(hdr.text() if hdr else f"Col {col + 1}")
            ws_vista.set_row(0, 22)
            ws_vista.set_column("A:A", 18)
            ws_vista.set_column("B:B", 22)
            ws_vista.set_column("C:C", 16)
            ws_vista.set_column("D:D", 16)
            ws_vista.set_column("E:E", 24)
            ws_vista.set_column("F:F", 14)
            ws_vista.set_column("G:G", 12)
            ws_vista.set_column("H:H", 14)
            ws_vista.set_column("I:J", 14)
            ws_vista.write_row(0, 0, headers_vista, fmt_header)
            for r in range(self.table_historial.rowCount()):
                for c in range(self.table_historial.columnCount()):
                    item = self.table_historial.item(r, c)
                    texto = item.text() if item else ""
                    ws_vista.write(r + 1, c, texto, fmt_texto)
            ultima_fila_vista = max(1, self.table_historial.rowCount())
            ws_vista.autofilter(0, 0, ultima_fila_vista, len(headers_vista) - 1)
            ws_vista.freeze_panes(1, 0)

            ws_detalle = workbook.add_worksheet("Detalle")
            headers = [
                "Tipo",
                "Fecha pago",
                "Monto",
                "Metodo",
                "Usuario",
                "Tipo vehiculo",
                "Cliente",
                "Patente",
                "Espacio",
                "Contrato ID",
                "Movimiento ID",
            ]
            ws_detalle.set_row(0, 22)
            ws_detalle.set_column("A:A", 18)
            ws_detalle.set_column("B:B", 22)
            ws_detalle.set_column("C:C", 16)
            ws_detalle.set_column("D:D", 16)
            ws_detalle.set_column("E:E", 16)
            ws_detalle.set_column("F:F", 16)
            ws_detalle.set_column("G:G", 24)
            ws_detalle.set_column("H:H", 14)
            ws_detalle.set_column("I:I", 12)
            ws_detalle.set_column("J:K", 14)
            ws_detalle.write_row(0, 0, headers, fmt_header)

            for idx, row in enumerate(detalle, start=1):
                ws_detalle.write(idx, 0, row["tipo"], fmt_texto)
                ws_detalle.write(idx, 1, row["fecha_pago"], fmt_fecha)
                ws_detalle.write_number(idx, 2, float(row["monto"] or 0.0), fmt_moneda)
                ws_detalle.write(idx, 3, row["metodo"], fmt_texto)
                ws_detalle.write(idx, 4, row.get("usuario") or "", fmt_texto)
                ws_detalle.write(
                    idx,
                    5,
                    _label_tipo_vehiculo(row.get("tipo_vehiculo"))
                    if row.get("tipo_vehiculo")
                    else "",
                    fmt_texto,
                )
                ws_detalle.write(idx, 6, row["cliente"], fmt_texto)
                ws_detalle.write(idx, 7, row["patente"], fmt_texto)
                ws_detalle.write(idx, 8, row["espacio"], fmt_texto)
                ws_detalle.write(idx, 9, str(row["contrato_id"] or ""), fmt_texto)
                ws_detalle.write(idx, 10, str(row["movimiento_id"] or ""), fmt_texto)

            ultima_fila = max(1, len(detalle))
            ws_detalle.autofilter(0, 0, ultima_fila, len(headers) - 1)
            ws_detalle.freeze_panes(1, 0)
            ws_detalle.write(ultima_fila + 2, 1, "Total", fmt_subtitulo)
            ws_detalle.write_number(ultima_fila + 2, 2, float(total), fmt_moneda)

            workbook.close()
            self._mostrar_export_ok(path, "Reporte")
        except Exception as e:
            _mostrar_error(self, "Error", f"No se pudo guardar el Excel.\n{e}")

    def _exportar_pagos_mensuales(self):
        desde_key, hasta_key = self._periodo()
        detalle = svc_consultar_pagos_mensuales_rango(desde_key, hasta_key)
        if not detalle:
            QMessageBox.information(self, "Reporte", "No hay pagos mensuales en ese rango.")
            return

        nombre_base = f"pagos_mensuales_{desde_key}_a_{hasta_key}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar pagos mensuales",
            str(_reportes_dir() / f"{nombre_base}.xlsx"),
            "Excel (*.xlsx);;CSV (*.csv)",
        )
        if not path:
            return

        ext = Path(path).suffix.lower()
        if ext not in (".xlsx", ".csv"):
            path += ".xlsx"
            ext = ".xlsx"

        total = sum(float(r.get("monto") or 0.0) for r in detalle)

        if ext == ".csv":
            try:
                try:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    _mostrar_error(
                        self,
                        "Error",
                        f"No se pudo crear la carpeta de destino.\n{e}",
                    )
                    return
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Pagos mensuales", f"{desde_key} a {hasta_key}"])
                    writer.writerow(["Total", f"{total:.2f}"])
                    writer.writerow([])
                    writer.writerow(
                        [
                            "Fecha pago",
                            "Monto",
                            "Metodo",
                            "Cliente",
                            "DNI",
                            "Patente",
                            "Espacio",
                            "Contrato ID",
                            "Pago ID",
                        ]
                    )
                    for row in detalle:
                        writer.writerow(
                            [
                                row["fecha_pago"],
                                f"{float(row['monto'] or 0.0):.2f}",
                                row["metodo"],
                                row["cliente"],
                                row["dni"],
                                row["patente"],
                                row["espacio"],
                                row["id_contrato"],
                                row["id_pago"],
                            ]
                        )
                self._mostrar_export_ok(path, "Pagos mensuales")
            except OSError:
                _mostrar_error(self, "Error", "No se pudo guardar el CSV.")
            return

        try:
            import xlsxwriter
        except ImportError:
            QMessageBox.warning(
                self,
                "Excel",
                "Para exportar a Excel necesitas instalar xlsxwriter.\n"
                "Puedes usar CSV por ahora.",
            )
            return

        try:
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                _mostrar_error(
                    self,
                    "Error",
                    f"No se pudo crear la carpeta de destino.\n{e}",
                )
                return
            workbook = xlsxwriter.Workbook(path)
            fmt_header = workbook.add_format(
                {"bold": True, "font_color": "#FFFFFF", "bg_color": "#2563EB", "border": 1}
            )
            fmt_moneda = workbook.add_format({"num_format": "$ #,##0.00", "border": 1})
            fmt_texto = workbook.add_format({"border": 1})
            ws = workbook.add_worksheet("Pagos mensuales")
            ws.set_column("A:A", 20)
            ws.set_column("B:B", 14)
            ws.set_column("C:C", 14)
            ws.set_column("D:D", 24)
            ws.set_column("E:E", 12)
            ws.set_column("F:F", 12)
            ws.set_column("G:G", 12)
            ws.set_column("H:I", 12)

            headers = [
                "Fecha pago",
                "Monto",
                "Metodo",
                "Cliente",
                "DNI",
                "Patente",
                "Espacio",
                "Contrato ID",
                "Pago ID",
            ]
            ws.write_row(0, 0, headers, fmt_header)
            for idx, row in enumerate(detalle, start=1):
                ws.write(idx, 0, row["fecha_pago"] or "", fmt_texto)
                ws.write_number(idx, 1, float(row["monto"] or 0.0), fmt_moneda)
                ws.write(idx, 2, row["metodo"] or "", fmt_texto)
                ws.write(idx, 3, row["cliente"] or "", fmt_texto)
                ws.write(idx, 4, row["dni"] or "", fmt_texto)
                ws.write(idx, 5, row["patente"] or "", fmt_texto)
                ws.write(idx, 6, row["espacio"] or "", fmt_texto)
                ws.write(idx, 7, str(row["id_contrato"] or ""), fmt_texto)
                ws.write(idx, 8, str(row["id_pago"] or ""), fmt_texto)

            ultima = max(1, len(detalle))
            ws.autofilter(0, 0, ultima, len(headers) - 1)
            ws.freeze_panes(1, 0)
            ws.write(ultima + 2, 0, "Total", fmt_texto)
            ws.write_number(ultima + 2, 1, float(total), fmt_moneda)

            workbook.close()
            self._mostrar_export_ok(path, "Pagos mensuales")
        except Exception as e:
            _mostrar_error(self, "Error", f"No se pudo guardar el Excel.\n{e}")


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
        self.btn_exportar_csv = QPushButton("Exportar CSV")
        filtros.addWidget(self.btn_actualizar)
        filtros.addWidget(self.btn_exportar_csv)
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
        self.btn_exportar_csv.clicked.connect(self._exportar_csv)
        self.btn_guardar_cierre.clicked.connect(self._guardar_cierre)
        self.btn_reabrir_cierre.clicked.connect(self._reabrir_cierre)
        self.btn_limpiar_cierre.clicked.connect(self._limpiar_form_cierre)
        self.input_observacion.textChanged.connect(self._actualizar_estado_observacion)
        self._cargar()

    def _cargar(self):
        fecha_key = self.input_fecha.date().toString("yyyy-MM-dd")
        cochera, est, total = svc_consultar_totales_caja(fecha_key)
        detalle = svc_consultar_detalle_metodo_caja(fecha_key)
        cierre = svc_obtener_cierre_caja(fecha_key)
        cierre_metodos = svc_obtener_cierre_caja_metodos(fecha_key)

        self.label_cochera.setText(f"$ {cochera:.2f}")
        self.label_est.setText(f"$ {est:.2f}")
        self.label_total.setText(f"$ {total:.2f}")
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
            return f"$ +{diferencia:.2f} (sobrante)"
        if diferencia < -0.009:
            return f"$ {diferencia:.2f} (faltante)"
        return "$ 0.00 (cuadra)"

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
        self.table_metodos.setItem(r, 1, QTableWidgetItem(f"$ {float(cochera or 0.0):.2f}"))
        self.table_metodos.setItem(
            r, 2, QTableWidgetItem(f"$ {float(estacionamiento or 0.0):.2f}")
        )
        self.table_metodos.setItem(r, 3, QTableWidgetItem(f"$ {float(esperado or 0.0):.2f}"))

        input_contado = QDoubleSpinBox()
        input_contado.setDecimals(2)
        input_contado.setRange(0.0, 999999999.0)
        input_contado.setSingleStep(100.0)
        input_contado.setValue(float(contado or 0.0))
        input_contado.valueChanged.connect(self._actualizar_diferencia)
        self.table_metodos.setCellWidget(r, 4, input_contado)

        item_dif = QTableWidgetItem("$ 0.00")
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
        self.label_total_real.setText(f"$ {contado:.2f}")
        self.label_diferencia.setText(self._texto_diferencia(diferencia))
        if diferencia > 0.009:
            self.label_diferencia.setStyleSheet("color: #34d399; font-weight: 600;")
        elif diferencia < -0.009:
            self.label_diferencia.setStyleSheet("color: #f87171; font-weight: 600;")
        else:
            self.label_diferencia.setStyleSheet("color: #a7f3d0; font-weight: 600;")
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
            cochera, est, total = svc_consultar_totales_caja(fecha_key)
            self.label_cochera.setText(f"$ {cochera:.2f}")
            self.label_est.setText(f"$ {est:.2f}")
            self.label_total.setText(f"$ {total:.2f}")
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

    def _exportar_csv(self):
        fecha = self.input_fecha.date()
        fecha_key = fecha.toString("yyyy-MM-dd")
        nombre_default = f"cierre_caja_{fecha_key}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar cierre de caja",
            str(_reportes_dir() / nombre_default),
            "CSV (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        cochera, est, total = svc_consultar_totales_caja(fecha_key)
        detalle = svc_consultar_detalle_metodo_caja(fecha_key)
        cierre = svc_obtener_cierre_caja(fecha_key)
        cierre_metodos = svc_obtener_cierre_caja_metodos(fecha_key)
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Cierre de caja", fecha.toString("dd/MM/yyyy")])
                writer.writerow(["Cochera", f"{cochera:.2f}"])
                writer.writerow(["Estacionamiento", f"{est:.2f}"])
                writer.writerow(["Total esperado", f"{total:.2f}"])
                if cierre:
                    writer.writerow(["Total contado", f"{cierre['total_contado']:.2f}"])
                    writer.writerow(["Diferencia", f"{cierre['diferencia']:.2f}"])
                    writer.writerow(["Observacion", cierre["observacion"] or ""])
                    writer.writerow(["Usuario cierre", cierre["usuario"] or ""])
                    writer.writerow(["Fecha cierre", cierre["fecha_cierre"] or ""])
                writer.writerow([])
                writer.writerow(
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
                for row in detalle:
                    metodo = (row["metodo"] or "").strip() or "Sin metodo"
                    cierre_metodo = cierre_metodos.get(metodo, {})
                    esperado = float(row["total"] or 0.0)
                    contado = float(cierre_metodo.get("total_contado", esperado) or 0.0)
                    writer.writerow(
                        [
                            metodo,
                            f"{row['cochera']:.2f}",
                            f"{row['estacionamiento']:.2f}",
                            f"{esperado:.2f}",
                            f"{contado:.2f}",
                            f"{(contado - esperado):.2f}",
                            row["operaciones"],
                        ]
                    )
                metodos_detalle = {
                    ((row["metodo"] or "").strip() or "Sin metodo") for row in detalle
                }
                for metodo, data in cierre_metodos.items():
                    if metodo in metodos_detalle:
                        continue
                    esperado = float(data.get("total_esperado") or 0.0)
                    contado = float(data.get("total_contado") or 0.0)
                    writer.writerow(
                        [
                            metodo,
                            "0.00",
                            "0.00",
                            f"{esperado:.2f}",
                            f"{contado:.2f}",
                            f"{(contado - esperado):.2f}",
                            0,
                        ]
                    )
            QMessageBox.information(self, "Caja", "CSV exportado correctamente.")
        except OSError:
            _mostrar_error(self, "Error", "No se pudo guardar el cierre de caja.")

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
        self.setWindowTitle("Copias de seguridad")
        self.setMinimumWidth(720)
        self.setMinimumHeight(420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Copias de seguridad disponibles (base de datos)"))

        self.lista = QListWidget()
        layout.addWidget(self.lista)

        acciones = QHBoxLayout()
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_crear = QPushButton("Crear copia")
        self.btn_restaurar = QPushButton("Restaurar")
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_actualizar.setProperty("variant", "neutral")
        self.btn_crear.setProperty("variant", "info")
        self.btn_restaurar.setProperty("variant", "warning")
        self.btn_eliminar.setProperty("variant", "danger")
        self.btn_cerrar.setProperty("variant", "neutral")
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

        self._cargar()

    def _refrescar_padre(self):
        parent = self.parent()
        if not parent:
            return
        for nombre in ("_refrescar_dashboard", "_actualizar_activos_est"):
            fn = getattr(parent, nombre, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass

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
        for path in svc_listar_backups_db(limit=200):
            item = QListWidgetItem(self._fmt_item(path))
            item.setData(Qt.UserRole, str(path))
            self.lista.addItem(item)

    def _crear_backup(self):
        if not _antirebote_iniciar(self, "backups_crear"):
            return
        try:
            try:
                path = svc_crear_backup_db(max_backups=30)
            except Exception:
                path = None
            if not path:
                QMessageBox.warning(
                    self,
                    "Copias de seguridad",
                    "No se pudo crear la copia de seguridad.",
                )
                return
            _auditar(self, "Backup creado", str(path))
            QMessageBox.information(
                self,
                "Copias de seguridad",
                f"Copia de seguridad creada:\n{path}",
            )
            self._cargar()
            self._refrescar_padre()
        finally:
            _antirebote_finalizar(self, "backups_crear", cooldown_ms=700)

    def _eliminar_backup(self):
        path = self._selected_path()
        if not path:
            QMessageBox.warning(
                self,
                "Copias de seguridad",
                "Selecciona una copia de seguridad.",
            )
            return
        if not _antirebote_iniciar(self, "backups_eliminar"):
            return
        try:
            confirmar = QMessageBox.question(
                self,
                "Eliminar copia de seguridad",
                f"Eliminar esta copia de seguridad?\n{path.name}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirmar != QMessageBox.Yes:
                return
            ok = svc_eliminar_backup_db(path)
            if not ok:
                QMessageBox.warning(
                    self,
                    "Copias de seguridad",
                    "No se pudo eliminar la copia de seguridad.",
                )
                return
            _auditar(self, "Backup eliminado", str(path))
            self._cargar()
        finally:
            _antirebote_finalizar(self, "backups_eliminar", cooldown_ms=700)

    def _restaurar_backup(self):
        path = self._selected_path()
        if not path:
            QMessageBox.warning(
                self,
                "Copias de seguridad",
                "Selecciona una copia de seguridad.",
            )
            return
        if not _antirebote_iniciar(self, "backups_restaurar"):
            return
        try:
            confirmar = QMessageBox.question(
                self,
                "Restaurar copia de seguridad",
                "Esto reemplazara la base de datos por la copia seleccionada.\n"
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

            ok = svc_restaurar_backup_db(path)
            if not ok:
                _mostrar_error(
                    self,
                    "Error",
                    "No se pudo restaurar la copia de seguridad.",
                )
                return
            _auditar(self, "Backup restaurado", str(path))
            QMessageBox.information(
                self,
                "Copias de seguridad",
                "Copia de seguridad restaurada.\nSe recomienda reiniciar la aplicacion.",
            )
            self._cargar()
            self._refrescar_padre()
        finally:
            _antirebote_finalizar(self, "backups_restaurar", cooldown_ms=1000)


class ConfiguracionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.combo_qr_provider = QComboBox()
        self.combo_qr_provider.addItem("Manual", "manual")
        self.combo_qr_provider.addItem("Mercado Pago Point", "mercadopago_point")
        self.input_mp_token = QLineEdit()
        self.input_mp_token.setEchoMode(QLineEdit.Password)
        self.input_mp_collector = QLineEdit()
        self.input_mp_pos = QLineEdit()
        self.input_wa_template = QLineEdit()
        self.input_mp_token.setPlaceholderText("APP_USR-...")
        self.input_mp_collector.setPlaceholderText("Collector ID")
        self.input_mp_pos.setPlaceholderText("POS ID")
        self.input_wa_template.setPlaceholderText(
            "Hola {nombre}, te recordamos tu vencimiento ({vencimiento}). Deuda: {deuda}."
        )
        form_general.addRow("Nombre del negocio", self.input_nombre)
        form_general.addRow("Telefono", self.input_telefono)
        form_general.addRow("Direccion", self.input_direccion)
        form_general.addRow("Alias cochera", self.input_alias)
        form_general.addRow("CBU cochera", self.input_cbu)
        form_general.addRow("Proveedor QR", self.combo_qr_provider)
        form_general.addRow("Token de acceso MP", self.input_mp_token)
        form_general.addRow("ID cobrador MP", self.input_mp_collector)
        form_general.addRow("ID POS MP", self.input_mp_pos)
        form_general.addRow("Plantilla WhatsApp", self.input_wa_template)
        self.tabs.addTab(tab_general, "General")

        tab_reportes = QWidget()
        form_reportes = QFormLayout(tab_reportes)
        self.input_moneda = QLineEdit()
        self.input_moneda.setMaxLength(4)
        self.input_moneda.setPlaceholderText("$")
        form_reportes.addRow("Simbolo moneda", self.input_moneda)
        self.input_dir_reportes = QLineEdit()
        self.btn_dir_reportes = QPushButton("Elegir...")
        fila_reportes = QHBoxLayout()
        fila_reportes.addWidget(self.input_dir_reportes)
        fila_reportes.addWidget(self.btn_dir_reportes)
        form_reportes.addRow("Carpeta de reportes", fila_reportes)
        self.input_dir_tickets_salida = QLineEdit()
        self.btn_dir_tickets_salida = QPushButton("Elegir...")
        fila_tickets_salida = QHBoxLayout()
        fila_tickets_salida.addWidget(self.input_dir_tickets_salida)
        fila_tickets_salida.addWidget(self.btn_dir_tickets_salida)
        form_reportes.addRow("Carpeta tickets de salida", fila_tickets_salida)
        self.input_dir_comprobantes = QLineEdit()
        self.btn_dir_comprobantes = QPushButton("Elegir...")
        fila_comp = QHBoxLayout()
        fila_comp.addWidget(self.input_dir_comprobantes)
        fila_comp.addWidget(self.btn_dir_comprobantes)
        form_reportes.addRow("Carpeta comprobantes", fila_comp)
        self.tabs.addTab(tab_reportes, "Reportes")

        tab_sistema = QWidget()
        form_sistema = QFormLayout(tab_sistema)
        self.combo_resolucion = QComboBox()
        self.combo_resolucion.addItems(
            ["1024x600", "1280x720", "1366x768", "1600x900", "1920x1080"]
        )
        self.combo_tema = QComboBox()
        self.combo_tema.addItems(["Oscuro", "Claro"])
        self.check_modo_operador_rapido = QCheckBox("Activar modo operador rapido")
        self.btn_ultra_rtx = QPushButton("Activar modo RTX 8K a 120 FPS")
        self.btn_ultra_rtx.setProperty("variant", "info")
        form_sistema.addRow("Resolucion", self.combo_resolucion)
        form_sistema.addRow("Tema", self.combo_tema)
        form_sistema.addRow("Modo operador rapido", self.check_modo_operador_rapido)
        form_sistema.addRow("Modo gamer", self.btn_ultra_rtx)
        self.tabs.addTab(tab_sistema, "Sistema")

        acciones = QHBoxLayout()
        acciones.addStretch(1)
        self.btn_guardar = QPushButton("Guardar")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_guardar.setProperty("variant", "success")
        self.btn_cerrar.setProperty("variant", "neutral")
        acciones.addWidget(self.btn_guardar)
        acciones.addWidget(self.btn_cerrar)
        layout.addLayout(acciones)

        self.btn_guardar.clicked.connect(self._guardar)
        self.btn_cerrar.clicked.connect(self.reject)
        self.btn_dir_reportes.clicked.connect(
            lambda: self._seleccionar_carpeta(self.input_dir_reportes)
        )
        self.btn_dir_tickets_salida.clicked.connect(
            lambda: self._seleccionar_carpeta(self.input_dir_tickets_salida)
        )
        self.btn_dir_comprobantes.clicked.connect(
            lambda: self._seleccionar_carpeta(self.input_dir_comprobantes)
        )
        self.btn_ultra_rtx.clicked.connect(self._activar_ultra_rtx)
        self.combo_qr_provider.currentIndexChanged.connect(self._ajustar_qr_fields)
        self._cargar()

    def _cargar(self):
        self.input_nombre.setText(_config_get("empresa_nombre", ""))
        self.input_telefono.setText(_config_get("empresa_telefono", ""))
        self.input_direccion.setText(_config_get("empresa_direccion", ""))
        self.input_alias.setText(_config_get("cochera_alias", ""))
        self.input_cbu.setText(_config_get("cochera_cbu", ""))
        qr_provider = (_config_get("qr_provider", "manual") or "manual").strip().lower()
        idx_qr = self.combo_qr_provider.findData(qr_provider)
        self.combo_qr_provider.setCurrentIndex(idx_qr if idx_qr >= 0 else 0)
        self.input_mp_token.setText(_config_get("mp_access_token", ""))
        self.input_mp_collector.setText(_config_get("mp_collector_id", ""))
        self.input_mp_pos.setText(_config_get("mp_pos_id", ""))
        self.input_wa_template.setText(_config_get("wa_recordatorio_template", ""))
        self.input_moneda.setText(_config_get("simbolo_moneda", "$"))
        self.input_dir_reportes.setText(_config_get("dir_reportes", ""))
        self.input_dir_tickets_salida.setText(_config_get("dir_tickets_salida", ""))
        self.input_dir_comprobantes.setText(_config_get("dir_comprobantes", ""))
        resolucion = _config_get("ui_resolucion", "1280x720")
        idx_res = self.combo_resolucion.findText(resolucion)
        self.combo_resolucion.setCurrentIndex(idx_res if idx_res >= 0 else 1)
        tema = (_config_get("ui_tema", "oscuro") or "oscuro").strip().lower()
        self.combo_tema.setCurrentIndex(1 if tema == "claro" else 0)
        self.check_modo_operador_rapido.setChecked(
            (_config_get("ui_operador_rapido", "0") or "0").strip() == "1"
        )
        self._ajustar_qr_fields()

    def _ajustar_qr_fields(self):
        proveedor = self.combo_qr_provider.currentData() or "manual"
        usa_mp = proveedor == "mercadopago_point"
        self.input_mp_token.setEnabled(usa_mp)
        self.input_mp_collector.setEnabled(usa_mp)
        self.input_mp_pos.setEnabled(usa_mp)

    def _seleccionar_carpeta(self, input_destino):
        base = input_destino.text().strip() or str(Path(__file__).resolve().parent)
        carpeta = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", base)
        if carpeta:
            input_destino.setText(carpeta)

    def _activar_ultra_rtx(self):
        QMessageBox.information(
            self,
            "Ultra RTX 8K 120 FPS",
            "Modo ultra activado.\nAhora funciona a 120 FPS... en tu imaginacion.",
        )

    def _guardar(self):
        moneda = (self.input_moneda.text() or "$").strip() or "$"
        tema = "claro" if self.combo_tema.currentText() == "Claro" else "oscuro"
        resolucion = self.combo_resolucion.currentText()
        telefono = _normalizar_telefono(self.input_telefono.text())
        if not _validar_telefono(telefono):
            QMessageBox.warning(self, "Telefono", "Telefono invalido.")
            return
        cbu = _normalizar_cbu(self.input_cbu.text())
        if not _validar_cbu(cbu):
            QMessageBox.warning(self, "CBU", "El CBU debe tener 22 digitos.")
            return
        self.input_telefono.setText(telefono)
        self.input_cbu.setText(cbu)
        dir_reportes = self.input_dir_reportes.text().strip()
        dir_tickets_salida = self.input_dir_tickets_salida.text().strip()
        dir_comprobantes = self.input_dir_comprobantes.text().strip()
        try:
            if dir_reportes:
                Path(dir_reportes).mkdir(parents=True, exist_ok=True)
            if dir_tickets_salida:
                Path(dir_tickets_salida).mkdir(parents=True, exist_ok=True)
            if dir_comprobantes:
                Path(dir_comprobantes).mkdir(parents=True, exist_ok=True)
            ok = True
            ok = _config_set("empresa_nombre", self.input_nombre.text().strip()) and ok
            ok = _config_set("empresa_telefono", telefono) and ok
            ok = _config_set("empresa_direccion", self.input_direccion.text().strip()) and ok
            ok = _config_set("cochera_alias", self.input_alias.text().strip()) and ok
            ok = _config_set("cochera_cbu", cbu) and ok
            ok = _config_set("qr_provider", self.combo_qr_provider.currentData() or "manual") and ok
            ok = _config_set("mp_access_token", self.input_mp_token.text().strip()) and ok
            ok = _config_set("mp_collector_id", self.input_mp_collector.text().strip()) and ok
            ok = _config_set("mp_pos_id", self.input_mp_pos.text().strip()) and ok
            ok = _config_set("wa_recordatorio_template", self.input_wa_template.text().strip()) and ok
            ok = _config_set("simbolo_moneda", moneda) and ok
            ok = _config_set("dir_reportes", dir_reportes) and ok
            ok = _config_set("dir_tickets_salida", dir_tickets_salida) and ok
            ok = _config_set("dir_comprobantes", dir_comprobantes) and ok
            ok = _config_set("ui_tema", tema) and ok
            ok = _config_set("ui_resolucion", resolucion) and ok
            ok = _config_set(
                "ui_operador_rapido",
                "1" if self.check_modo_operador_rapido.isChecked() else "0",
            ) and ok
            if not ok:
                raise sqlite3.Error()
            _auditar(self, "Configuracion actualizada", "Datos generales del sistema")
            QMessageBox.information(self, "Configuracion", "Cambios guardados.")
            self.accept()
        except (sqlite3.Error, OSError):
            _mostrar_error(self, "Error", "No se pudo guardar la configuracion.")


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
        self._aplicar_modo_operador_rapido()
        self._alerta_inicio_mostrada = False
        QTimer.singleShot(900, self._mostrar_alerta_vencimientos_inicio)

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
                background-color: #e07a2f;
                border-color: #f08a3a;
                color: #fff3e6;
            }
            QPushButton#btn_estacionamiento:hover {
                background-color: #e98a44;
            }
            QPushButton#btn_estacionamiento:pressed {
                background-color: #c86a25;
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
            QPushButton#btn_reportes {
                background-color: #2D7A2D;
                border-color: #43A043;
                color: #E9F6E9;
            }
            QPushButton#btn_reportes:hover {
                background-color: #368A36;
            }
            QPushButton#btn_reportes:pressed {
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
            """
        )

    def _aplicar_preferencias_ui(self):
        tema = (_config_get("ui_tema", "oscuro") or "oscuro").strip().lower()
        if tema == "claro":
            self.setStyleSheet("")
        else:
            self.setStyleSheet(getattr(self, "_estilo_oscuro_cache", self.styleSheet()))

        resolucion = (_config_get("ui_resolucion", "1280x720") or "1280x720").strip().lower()
        cambio_resolucion = False
        if "x" in resolucion:
            try:
                w_txt, h_txt = resolucion.split("x", 1)
                w = max(1024, int(w_txt))
                h = max(600, int(h_txt))
                if self.width() != w or self.height() != h:
                    cambio_resolucion = True
                self.resize(w, h)
            except ValueError:
                pass
        if cambio_resolucion:
            self._centrar_ventana_en_pantalla()

        kpi_title_font = QFont()
        kpi_title_font.setPointSize(8)
        kpi_title_font.setBold(True)

        kpi_value_font = QFont()
        kpi_value_font.setPointSize(11)
        kpi_value_font.setBold(True)

        if hasattr(self.ui, "verticalLayout"):
            self.ui.verticalLayout.setContentsMargins(4, 2, 4, 2)
            self.ui.verticalLayout.setSpacing(0)

        if hasattr(self.ui, "modeButtonsLayout"):
            self.ui.modeButtonsLayout.setContentsMargins(0, 0, 0, 0)
            self.ui.modeButtonsLayout.setSpacing(4)

        if hasattr(self.ui, "cocheraLayout"):
            self.ui.cocheraLayout.setSpacing(2)
            self.ui.cocheraLayout.setContentsMargins(0, 0, 0, 0)

        if hasattr(self.ui, "estacionamientoLayout"):
            self.ui.estacionamientoLayout.setSpacing(2)
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
            self.ui.group_cochera_resumen.setMaximumHeight(200)

        if hasattr(self.ui, "kpiGrid"):
            for col in range(3):
                self.ui.kpiGrid.setColumnStretch(col, 1)
            self.ui.kpiGrid.setRowStretch(0, 0)
            self.ui.kpiGrid.setRowStretch(1, 0)
            self.ui.kpiGrid.setHorizontalSpacing(6)
            self.ui.kpiGrid.setVerticalSpacing(6)

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
                card.setMinimumHeight(48)
                card.setMaximumHeight(80)

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
            self.ui.cochera_resumen_layout.setContentsMargins(6, 6, 6, 6)
            self.ui.cochera_resumen_layout.setSpacing(6)

        titulo_font = QFont()
        titulo_font.setPointSize(12)
        titulo_font.setBold(True)

        for name in ("label_cochera_title",):
            label = getattr(self.ui, name, None)
            if label:
                label.setFont(titulo_font)
                label.setMaximumHeight(26)
                label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        fecha_font = QFont()
        fecha_font.setPointSize(14)
        fecha_font.setBold(True)

        for name in ("label_fecha_num", "label_est_fecha_num", "label_hora_value"):
            label = getattr(self.ui, name, None)
            if label:
                label.setFont(fecha_font)
                label.setMaximumHeight(24)
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
                self.ui.est_resumen_layout.setContentsMargins(6, 6, 6, 6)
                self.ui.est_resumen_layout.setSpacing(6)
                self.ui.est_resumen_grid = QGridLayout()
                self.ui.est_resumen_grid.setHorizontalSpacing(6)
                self.ui.est_resumen_grid.setVerticalSpacing(6)
                for col in range(4):
                    self.ui.est_resumen_grid.setColumnStretch(col, 1)

                def _crear_card_est(nombre_card, nombre_title, nombre_value, texto_title, texto_value):
                    card = QFrame(self.ui.group_est_resumen)
                    card.setObjectName(nombre_card)
                    card.setFrameShape(QFrame.StyledPanel)
                    layout_card = QVBoxLayout(card)
                    layout_card.setContentsMargins(6, 6, 6, 6)
                    layout_card.setSpacing(4)
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
            self.ui.group_est_resumen.setMaximumHeight(150)
            self.ui.group_est_resumen.setMinimumHeight(95)

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
            "btn_vencimientos",
            "btn_mapa_est",
            "btn_ingreso_est",
            "btn_salida_est",
        ]
        for name in botones:
            btn = getattr(self.ui, name, None)
            if not btn:
                continue
            btn.setMinimumHeight(26)
            btn.setMaximumHeight(32)
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
                group.setMaximumHeight(64)
            layout = getattr(self.ui, layout_name, None)
            if layout:
                layout.setContentsMargins(4, 4, 4, 4)
                layout.setSpacing(4)

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
            self.ui.fechaHoraLayout.setSpacing(4)

        if hasattr(self.ui, "cocheraLayout"):
            self.ui.cocheraLayout.addStretch(1)

        self._configurar_iconos_acciones()

    def _centrar_ventana_en_pantalla(self):
        screen = None
        try:
            wh = self.windowHandle()
            if wh:
                screen = wh.screen()
        except Exception:
            screen = None
        if screen is None:
            app = QApplication.instance()
            if app is not None:
                try:
                    screen = app.primaryScreen()
                except Exception:
                    screen = None
        if screen is None:
            return

        area = screen.availableGeometry()
        max_x = area.x() + max(0, area.width() - self.width())
        max_y = area.y() + max(0, area.height() - self.height())
        x = area.x() + (area.width() - self.width()) // 2
        y = area.y() + (area.height() - self.height()) // 2
        x = max(area.x(), min(x, max_x))
        y = max(area.y(), min(y, max_y))
        self.move(int(x), int(y))

    def _configurar_iconos_acciones(self):
        iconos = {
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
        self.menu_admin.addAction(self.action_usuarios)
        self.menu_admin.addAction(self.action_tarifas)
        self.menu_admin.addAction(self.action_historial)
        self.menu_admin.addAction(self.action_cierre_caja)
        self.action_usuarios.triggered.connect(self._abrir_usuarios)
        self.action_tarifas.triggered.connect(self._abrir_tarifas)
        self.action_historial.triggered.connect(self._abrir_historial)
        self.action_cierre_caja.triggered.connect(self._abrir_cierre_caja)
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
        self.action_configuracion.setVisible(es_admin or es_operador)
        self.action_usuarios.setEnabled(es_admin)
        self.action_tarifas.setEnabled(es_admin)
        self.action_historial.setEnabled(es_admin or es_operador)
        self.action_cierre_caja.setEnabled(es_admin or es_operador)
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
        self.ui.btn_mapa_cocheras.setVisible(es_admin or es_operador)
        self.ui.btn_contratos.setVisible(True)
        self.ui.btn_clientes.setVisible(True)
        self.ui.btn_mapa_est.setVisible(es_admin or es_operador)

    def _es_dueno(self):
        return (self.rol or "").upper() == "DUENO"

    def _requiere_dueno(self, accion):
        if self._es_dueno():
            return True
        QMessageBox.warning(self, "Permisos", "Esta accion es solo para DUENO.")
        _auditar(
            self,
            "Intento sin permiso",
            f"{accion} (usuario={self.usuario or '-'}, rol={self.rol or '-'})",
        )
        return False

    def _abrir_tarifas(self):
        if not self._requiere_dueno("abrir tarifas"):
            return
        dlg = TarifaDialog(self)
        dlg.exec()

    def _abrir_usuarios(self):
        if not self._requiere_dueno("abrir usuarios"):
            return
        dlg = UsuariosDialog(self, usuario_actual=self.usuario)
        dlg.exec()

    def _abrir_historial(self):
        dlg = HistorialDialog(self)
        dlg.exec()

    def _abrir_cierre_caja(self):
        dlg = CajaDiariaDialog(self)
        dlg.exec()

    def _abrir_backups(self):
        if not self._requiere_dueno("abrir backups"):
            return
        dlg = BackupsDialog(self)
        dlg.exec()
        self._refrescar_dashboard()
        self._actualizar_activos_est()

    def _abrir_configuracion(self):
        dlg = ConfiguracionDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self._aplicar_preferencias_ui()
            self._aplicar_modo_operador_rapido()

    def _ejecutar_tests(self):
        if not self._requiere_dueno("ejecutar tests"):
            return
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
        if not self._requiere_dueno("probar error"):
            return
        _mostrar_error(self, "Error simulado", "Este es un ejemplo de error.")

    def _restaurar_base(self):
        if not self._requiere_dueno("restaurar base"):
            return
        confirmar = QMessageBox.question(
            self,
            "Restaurar base",
            "Esto eliminara TODOS los datos y reiniciara los contadores.\n"
            "Esta accion no se puede deshacer. Continuar?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirmar != QMessageBox.Yes:
            return

        texto, ok = QInputDialog.getText(
            self,
            "Confirmar restauracion",
            "Escribe BORRAR para confirmar:",
        )
        if not ok or texto.strip().upper() != "BORRAR":
            return

        try:
            svc_crear_backup_db(max_backups=30)
        except Exception:
            pass

        try:
            reset_db()
        except sqlite3.Error:
            _mostrar_error(self, "Error", "No se pudo restaurar la base.")
            return

        _auditar(self, "Base restaurada", "Limpieza total de tablas.")
        QMessageBox.information(
            self,
            "Base restaurada",
            "La base se reinicio correctamente.\n"
            "Se recomienda reiniciar la aplicacion.",
        )
        self._refrescar_dashboard()
        self._actualizar_activos_est()

    def _configurar_modos(self):
        self.ui.stack.setCurrentIndex(0)
        self.ui.btn_cochera.clicked.connect(lambda: self.ui.stack.setCurrentIndex(0))
        self.ui.btn_estacionamiento.clicked.connect(lambda: self.ui.stack.setCurrentIndex(1))
        self.ui.btn_vencimientos.clicked.connect(self._abrir_vencimientos)
        self.ui.btn_reportes.clicked.connect(self._abrir_reportes)
        self.ui.btn_mapa_cocheras.clicked.connect(self._abrir_mapa_cocheras)
        self.ui.btn_contratos.clicked.connect(self._abrir_contratos)
        self.ui.btn_clientes.clicked.connect(self._abrir_clientes)
        self.ui.btn_mapa_est.clicked.connect(self._abrir_mapa_cocheras)

    def _aplicar_modo_operador_rapido(self):
        rol = (self.rol or "").strip().upper()
        activo = rol == "OPERADOR" and (_config_get("ui_operador_rapido", "0") or "0").strip() == "1"
        self._modo_operador_rapido = activo

        for nombre in ("btn_cochera", "btn_estacionamiento"):
            btn = getattr(self.ui, nombre, None)
            if btn is not None:
                btn.setVisible(not activo)

        if activo and hasattr(self.ui, "stack"):
            self.ui.stack.setCurrentIndex(1)
            if hasattr(self.ui, "input_patente_est"):
                QTimer.singleShot(
                    0,
                    lambda: (
                        self.ui.input_patente_est.setFocus(),
                        self.ui.input_patente_est.selectAll(),
                    ),
                )

        if self.usuario:
            sufijo = " | Modo operador rapido" if activo else ""
            self.statusBar().showMessage(f"Usuario: {self.usuario} ({rol}){sufijo}")
        elif rol:
            sufijo = " | Modo operador rapido" if activo else ""
            self.statusBar().showMessage(f"Rol: {rol}{sufijo}")

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

    def _atajo_menu_cochera(self):
        if bool(getattr(self, "_modo_operador_rapido", False)):
            return
        if getattr(self.ui, "stack", None) is None:
            return
        self.ui.stack.setCurrentIndex(0)

    def _atajo_menu_estacionamiento(self):
        if getattr(self.ui, "stack", None) is None:
            return
        self.ui.stack.setCurrentIndex(1)
        if hasattr(self.ui, "input_patente_est"):
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
            self._abrir_reportes()
        elif self._en_menu_estacionamiento() and hasattr(self.ui, "combo_metodo_est"):
            self.ui.combo_metodo_est.setFocus()
            self.ui.combo_metodo_est.showPopup()

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

    def _log_estacionamiento(self, mensaje, nivel="info", mostrar_popup=True):
        self.ui.label_resultado_est.setText(mensaje)
        if not mostrar_popup or not mensaje:
            return
        titulo = "Estacionamiento"
        nivel_norm = (nivel or "info").lower()
        if nivel_norm == "error":
            QMessageBox.critical(self, titulo, mensaje)
        elif nivel_norm == "warn":
            QMessageBox.warning(self, titulo, mensaje)
        else:
            QMessageBox.information(self, titulo, mensaje)

    def _configurar_estacionamiento(self):
        self.ui.btn_ingreso_est.clicked.connect(self._registrar_ingreso_est)
        self.ui.btn_salida_est.clicked.connect(self._registrar_salida_est)
        self.ui.input_espacio_est.editingFinished.connect(self._validar_espacio_est)
        if not hasattr(self, "_modelo_patentes_est"):
            self._modelo_patentes_est = QStringListModel(self)
            self._completer_patentes_est = QCompleter(self._modelo_patentes_est, self)
            self._completer_patentes_est.setCaseSensitivity(Qt.CaseInsensitive)
            self._completer_patentes_est.setFilterMode(Qt.MatchContains)
            self._completer_patentes_est.setCompletionMode(QCompleter.PopupCompletion)
            self.ui.input_patente_est.setCompleter(self._completer_patentes_est)
        self._actualizar_autocomplete_patentes_est()
        if not hasattr(self.ui, "combo_tipo_vehiculo_est"):
            self.ui.label_tipo_vehiculo_est = QLabel("Tipo de vehiculo", self.ui.group_est_registro)
            self.ui.combo_tipo_vehiculo_est = QComboBox(self.ui.group_est_registro)
            self.ui.combo_tipo_vehiculo_est.setObjectName("combo_tipo_vehiculo_est")
            self.ui.combo_tipo_vehiculo_est.addItem("Auto", "AUTO")
            self.ui.combo_tipo_vehiculo_est.addItem("Moto", "MOTO")
            self.ui.combo_tipo_vehiculo_est.addItem("Camioneta", "CAMIONETA")
            if hasattr(self.ui, "est_form_layout"):
                self.ui.est_form_layout.insertRow(
                    2,
                    self.ui.label_tipo_vehiculo_est,
                    self.ui.combo_tipo_vehiculo_est,
                )
        if hasattr(self.ui, "combo_metodo_est"):
            combo = self.ui.combo_metodo_est
            existentes = [
                (combo.itemText(i) or "").strip().lower()
                for i in range(int(combo.count() or 0))
            ]
            if "qr" not in existentes:
                idx_otro = next(
                    (
                        i
                        for i in range(int(combo.count() or 0))
                        if (combo.itemText(i) or "").strip().lower() == "otro"
                    ),
                    int(combo.count() or 0),
                )
                combo.insertItem(idx_otro, "QR")
            self.ui.combo_metodo_est.installEventFilter(self)
            try:
                self.ui.combo_metodo_est.view().installEventFilter(self)
            except Exception:
                pass
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
        self._actualizar_activos_est()
        self._est_timer = QTimer(self)
        self._est_timer.timeout.connect(self._actualizar_activos_est)
        self._est_timer.start(5000)

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
        filas_por_col = (total + 1) // 2
        table.setRowCount(filas_por_col)
        for idx, row in enumerate(filas):
            col_offset = 0 if idx < filas_por_col else 3
            r = idx if idx < filas_por_col else idx - filas_por_col
            table.setItem(r, col_offset + 0, QTableWidgetItem(row["patente"]))
            table.setItem(r, col_offset + 1, QTableWidgetItem(row["codigo"]))
            table.setItem(r, col_offset + 2, QTableWidgetItem(row["fecha_ingreso"]))

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

    def _espacio_desde_tabla_est(self, row, column):
        table = self.ui.table_est_activos
        if row < 0 or column < 0:
            return ""
        col_base = 0 if column < 3 else 3
        item_espacio = table.item(row, col_base + 1)
        if item_espacio and item_espacio.text().strip():
            return item_espacio.text().strip().upper()
        return ""

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
            cur.execute("SELECT 1 FROM espacios_mapa WHERE codigo = ? LIMIT 1", (codigo,))
            if not cur.fetchone():
                sugerido = self._espacio_sugerido_mas_cercano(cur, codigo)
                msg = "Ese espacio no existe en el mapa."
                if sugerido:
                    msg += f" Sugerencia: {sugerido}."
                self._log_estacionamiento(
                    msg,
                    "warn",
                )
                if sugerido:
                    self.ui.input_espacio_est.setText(sugerido)
                else:
                    self.ui.input_espacio_est.clear()
                return
            cur.execute(
                "SELECT es_reservado, id_cliente FROM espacios WHERE codigo = ? AND activo = 1",
                (codigo,),
            )
            row = cur.fetchone()
            if row and (row["es_reservado"] == 1 or row["id_cliente"] is not None):
                sugerido = self._espacio_sugerido_mas_cercano(cur, codigo)
                msg = "Ese espacio esta reservado para cochera mensual."
                if sugerido:
                    msg += f" Sugerencia: {sugerido}."
                self._log_estacionamiento(
                    msg,
                    "warn",
                )
                if sugerido:
                    self.ui.input_espacio_est.setText(sugerido)
                else:
                    self.ui.input_espacio_est.clear()
        except sqlite3.Error:
            pass
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

    def _listar_vencimientos_criticos(self, dias=3):
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT c.nombre, e.codigo, cc.fecha_vencimiento "
                "FROM cochera_contratos cc "
                "JOIN clientes c ON c.id_cliente = cc.id_cliente "
                "JOIN espacios e ON e.id_espacio = cc.id_espacio "
                "WHERE cc.activo = 1 "
                "AND cc.fecha_vencimiento IS NOT NULL "
                "AND date(cc.fecha_vencimiento) <= date('now', ?) "
                "ORDER BY cc.fecha_vencimiento ASC "
                "LIMIT 12",
                (f"+{int(dias)} day",),
            )
            return [dict(row) for row in cur.fetchall()]
        except sqlite3.Error:
            return []
        finally:
            if conn:
                conn.close()

    def _mostrar_alerta_vencimientos_inicio(self):
        if self._alerta_inicio_mostrada:
            return
        if not self._es_dueno():
            return
        self._alerta_inicio_mostrada = True
        vencimientos = self._listar_vencimientos_criticos(dias=3)
        if not vencimientos:
            return
        lineas = []
        for row in vencimientos[:5]:
            nombre = row.get("nombre") or "-"
            codigo = row.get("codigo") or "-"
            fecha = row.get("fecha_vencimiento") or "-"
            lineas.append(f"- {nombre} | Espacio {codigo} | vence {fecha}")
        extra = ""
        if len(vencimientos) > 5:
            extra = f"\n... y {len(vencimientos) - 5} mas."
        QMessageBox.warning(
            self,
            "Vencimientos proximos",
            "Hay contratos que vencen en los proximos 3 dias:\n\n"
            + "\n".join(lineas)
            + extra,
        )

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
                "SELECT COUNT(*) FROM espacios e "
                "WHERE e.activo = 1 AND ("
                "COALESCE(e.es_reservado, 0) = 1 OR EXISTS ("
                "SELECT 1 FROM cochera_contratos cc "
                "WHERE cc.id_espacio = e.id_espacio AND cc.activo = 1"
                "))"
            )
            total = cur.fetchone()[0] or 0

            cur.execute(
                "SELECT COUNT(*) FROM espacios e "
                "WHERE e.activo = 1 AND EXISTS ("
                "SELECT 1 FROM cochera_contratos cc "
                "WHERE cc.id_espacio = e.id_espacio AND cc.activo = 1"
                ")"
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
        self.ui.label_ingresos_value.setText(f"$ {ingresos:.2f}")
        if tarifa_hora is None:
            self.ui.label_est_tarifa_value.setText("$ 0.00")
        else:
            self.ui.label_est_tarifa_value.setText(f"$ {tarifa_hora:.2f}")

        if tarifa_mensual is None:
            self.ui.label_mensual_value.setText("$ 0.00")
        else:
            self.ui.label_mensual_value.setText(f"$ {tarifa_mensual:.2f}")

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
                self.ui.label_est_tarifa_resumen_value.setText(f"$ {tarifa_hora:.2f}")

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
        if not self._requiere_dueno("abrir vencimientos"):
            return
        dlg = VencimientosDialog(self)
        dlg.exec()

    def _abrir_reportes(self):
        if not self._requiere_dueno("abrir reportes"):
            return
        dlg = ReportesDialog(self)
        dlg.exec()

    def _abrir_mapa_cocheras(self):
        es_admin = (self.rol or "").upper() == "DUENO"
        dlg = MapaCocheraDialog(self, editable=es_admin)
        dlg.exec()

    def _abrir_contratos(self):
        dlg = ContratosDialog(self, rol=self.rol)
        dlg.exec()

    def _abrir_clientes(self):
        dlg = ClientesDialog(self, rol=self.rol)
        dlg.exec()

    def _tipo_vehiculo_seleccionado_est(self):
        combo = getattr(self.ui, "combo_tipo_vehiculo_est", None)
        if combo is None:
            return "AUTO"
        valor = combo.currentData()
        if valor is None or valor == "":
            valor = combo.currentText()
        return _normalizar_tipo_vehiculo(valor)

    def _get_tarifa_hora(self, tipo_vehiculo="AUTO"):
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT precio_hora, precio_hora_auto, precio_hora_moto, "
                "precio_hora_camioneta "
                "FROM tarifas WHERE activa = 1 "
                "ORDER BY fecha_desde DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                return _tarifa_hora_desde_row(row, tipo_vehiculo)
        except sqlite3.Error:
            return None
        finally:
            if conn:
                conn.close()
        return None

    def _listar_patentes_est(self, cur):
        cur.execute(
            "SELECT DISTINCT UPPER(TRIM(patente)) AS patente "
            "FROM vehiculos "
            "WHERE TRIM(COALESCE(patente, '')) <> '' "
            "ORDER BY patente"
        )
        return [row["patente"] for row in cur.fetchall() if row["patente"]]

    def _actualizar_autocomplete_patentes_est(self):
        modelo = getattr(self, "_modelo_patentes_est", None)
        if modelo is None:
            return
        conn = None
        patentes = []
        try:
            conn = get_connection()
            cur = conn.cursor()
            patentes = self._listar_patentes_est(cur)
        except sqlite3.Error:
            patentes = []
        finally:
            if conn:
                conn.close()
        modelo.setStringList(patentes)

    @staticmethod
    def _descomponer_codigo_espacio(codigo):
        texto = (codigo or "").strip().upper()
        prefijo = "".join(ch for ch in texto if ch.isalpha())
        numero_txt = "".join(ch for ch in texto if ch.isdigit())
        numero = int(numero_txt) if numero_txt else None
        return prefijo, numero

    def _espacio_sugerido_mas_cercano(self, cur, codigo_referencia=""):
        cur.execute(
            "SELECT e.codigo "
            "FROM espacios_mapa em "
            "JOIN espacios e ON e.codigo = em.codigo "
            "LEFT JOIN movimientos m ON m.id_espacio = e.id_espacio AND m.fecha_salida IS NULL "
            "WHERE e.activo = 1 AND e.es_reservado = 0 AND e.id_cliente IS NULL "
            "AND m.id_movimiento IS NULL "
            "ORDER BY e.codigo"
        )
        opciones = [row["codigo"] for row in cur.fetchall() if row["codigo"]]
        if not opciones:
            return None

        ref = (codigo_referencia or "").strip().upper()
        if not ref:
            return opciones[0]

        pref_ref, num_ref = self._descomponer_codigo_espacio(ref)

        def _score(codigo):
            pref, num = self._descomponer_codigo_espacio(codigo)
            mismo_pref = 0 if pref_ref and pref == pref_ref else 1
            if num_ref is not None and num is not None:
                dist_num = abs(num - num_ref)
            else:
                dist_num = 9999
            delta_largo = abs(len(codigo) - len(ref))
            return (mismo_pref, dist_num, delta_largo, codigo)

        return min(opciones, key=_score)

    def _hay_espacios_mapa_est(self, cur):
        cur.execute("SELECT COUNT(*) FROM espacios_mapa")
        return (cur.fetchone()[0] or 0) > 0

    def _espacio_existe_en_mapa_est(self, cur, codigo):
        cur.execute("SELECT 1 FROM espacios_mapa WHERE codigo = ? LIMIT 1", (codigo,))
        return cur.fetchone() is not None

    def _buscar_espacio_libre_est(self, cur):
        cur.execute(
            "SELECT e.id_espacio, e.codigo "
            "FROM espacios_mapa em "
            "JOIN espacios e ON e.codigo = em.codigo "
            "LEFT JOIN movimientos m ON m.id_espacio = e.id_espacio AND m.fecha_salida IS NULL "
            "WHERE e.activo = 1 AND e.es_reservado = 0 AND e.id_cliente IS NULL "
            "AND m.id_movimiento IS NULL "
            "ORDER BY e.codigo LIMIT 1"
        )
        return cur.fetchone()

    def _resolver_espacio_est(self, cur, codigo):
        if codigo:
            cur.execute(
                "SELECT e.id_espacio, e.es_reservado, e.id_cliente "
                "FROM espacios e "
                "JOIN espacios_mapa em ON em.codigo = e.codigo "
                "WHERE e.codigo = ? AND e.activo = 1",
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
            "SELECT m.id_movimiento, m.fecha_ingreso, m.tipo_vehiculo, e.codigo "
            "FROM movimientos m "
            "JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
            "JOIN espacios e ON e.id_espacio = m.id_espacio "
            "WHERE v.patente = ? AND m.fecha_salida IS NULL "
            "ORDER BY m.fecha_ingreso DESC LIMIT 1",
            (patente,),
        )
        return cur.fetchone()

    def _registrar_ingreso_est(self):
        patente = self.ui.input_patente_est.text().strip().upper()
        codigo = self.ui.input_espacio_est.text().strip().upper()
        if not patente:
            self._log_estacionamiento("Completa la patente (ej: ABC123).", "warn")
            return
        tipo_vehiculo = self._tipo_vehiculo_seleccionado_est()
        tarifa = self._get_tarifa_hora(tipo_vehiculo)
        if tarifa is None:
            self._log_estacionamiento(
                "No hay tarifa por hora definida para "
                f"{_label_tipo_vehiculo(tipo_vehiculo).lower()}.",
                "warn",
            )
            return
        if not _antirebote_iniciar(self, "est_ingreso"):
            return

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()

            if not self._hay_espacios_mapa_est(cur):
                self._log_estacionamiento(
                    "No hay espacios cargados en el mapa. Configura el mapa antes de ingresar autos.",
                    "warn",
                )
                return
            if codigo and not self._espacio_existe_en_mapa_est(cur, codigo):
                sugerido = self._espacio_sugerido_mas_cercano(cur, codigo)
                msg = "Ese espacio no existe en el mapa."
                if sugerido:
                    msg += f" Sugerencia: {sugerido}."
                self._log_estacionamiento(
                    msg,
                    "warn",
                )
                if sugerido:
                    self.ui.input_espacio_est.setText(sugerido)
                return

            id_vehiculo, id_cliente = self._obtener_o_crear_vehiculo_est(cur, patente)

            codigo_cochera = self._codigo_cochera_activa_cliente(cur, id_cliente)
            if codigo_cochera:
                self._log_estacionamiento(
                    f"La patente ya tiene cochera activa (espacio {codigo_cochera}).",
                    "warn",
                )
                return

            if self._vehiculo_tiene_ingreso_activo(cur, id_vehiculo):
                self._log_estacionamiento(
                    "La patente ya tiene un ingreso activo. Registra la salida antes de volver a ingresar.",
                    "warn",
                )
                return

            id_espacio, codigo_resuelto, auto = self._resolver_espacio_est(cur, codigo)
            if not id_espacio:
                self._log_estacionamiento(
                    "No hay espacios disponibles en el mapa en este momento.",
                    "warn",
                )
                return
            codigo_original = codigo
            if auto or codigo_resuelto != codigo:
                codigo = codigo_resuelto
                self.ui.input_espacio_est.setText(codigo)
                if codigo_original and codigo_original != codigo:
                    self._log_estacionamiento(
                        f"Espacio solicitado no disponible. Se asigno automaticamente {codigo}.",
                        "info",
                        mostrar_popup=False,
                    )

            cur.execute(
                "SELECT COUNT(*) FROM movimientos WHERE id_espacio = ? AND fecha_salida IS NULL",
                (id_espacio,),
            )
            if (cur.fetchone()[0] or 0) > 0:
                sugerido = self._espacio_sugerido_mas_cercano(cur, codigo)
                msg = "Ese espacio ya esta ocupado."
                if sugerido:
                    msg += f" Sugerencia: {sugerido}."
                self._log_estacionamiento(msg, "warn")
                if sugerido:
                    self.ui.input_espacio_est.setText(sugerido)
                return

            dt_ing = datetime.now()
            cur.execute(
                "INSERT INTO movimientos (id_vehiculo, id_espacio, fecha_ingreso, tipo_vehiculo) "
                "VALUES (?, ?, ?, ?)",
                (
                    id_vehiculo,
                    id_espacio,
                    dt_ing.strftime("%Y-%m-%d %H:%M:%S"),
                    tipo_vehiculo,
                ),
            )
            movimiento_id = cur.lastrowid
            conn.commit()
            ticket = None
            try:
                ticket = _emitir_ticket_estacionamiento(
                    evento="Ingreso",
                    patente=patente,
                    espacio=codigo,
                    dt_ingreso=dt_ing,
                    tarifa_hora=tarifa,
                    movimiento_id=movimiento_id,
                    tipo_vehiculo=tipo_vehiculo,
                )
            except Exception:
                ticket = None

            self._log_estacionamiento(
                f"Ingreso registrado en espacio {codigo}.",
                "ok",
                mostrar_popup=False,
            )
            box = QMessageBox(self)
            box.setWindowTitle("Ticket de ingreso")
            box.setIcon(QMessageBox.Information)
            texto = (
                f"Patente: {patente}\n"
                f"Tipo: {_label_tipo_vehiculo(tipo_vehiculo)}\n"
                f"Espacio: {codigo}\n"
                f"Ingreso: {dt_ing.strftime('%d/%m/%Y %H:%M:%S')}"
            )
            btn_abrir = None
            if ticket:
                texto += f"\nTicket: {Path(ticket).name}"
                btn_abrir = box.addButton("Abrir ticket", QMessageBox.ActionRole)
            box.setText(texto)
            box.addButton("Aceptar", QMessageBox.AcceptRole)
            box.exec()
            if btn_abrir and box.clickedButton() == btn_abrir:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(ticket)))
            self.ui.input_patente_est.clear()
            self._actualizar_autocomplete_patentes_est()
            self._actualizar_activos_est()
        except sqlite3.Error:
            self._log_estacionamiento("Error al registrar ingreso.", "error")
        finally:
            if conn:
                conn.close()
            _antirebote_finalizar(self, "est_ingreso", cooldown_ms=700)

    def _registrar_salida_est(self):
        patente = self.ui.input_patente_est.text().strip().upper()
        if not patente:
            self._log_estacionamiento("Completa la patente para registrar la salida.", "warn")
            return

        if not _antirebote_iniciar(self, "est_salida"):
            return

        metodo = self.ui.combo_metodo_est.currentText()

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            row = self._buscar_movimiento_activo_por_patente(cur, patente)
            if not row:
                self._log_estacionamiento(
                    "No hay ingreso activo para esa patente. Verifica la patente o registra el ingreso primero.",
                    "warn",
                )
                return

            fecha_ingreso = row["fecha_ingreso"] or ""
            tipo_vehiculo = _normalizar_tipo_vehiculo(row["tipo_vehiculo"])
            tarifa = self._get_tarifa_hora(tipo_vehiculo)
            if tarifa is None:
                self._log_estacionamiento(
                    "No hay tarifa por hora definida para "
                    f"{_label_tipo_vehiculo(tipo_vehiculo).lower()}.",
                    "warn",
                )
                return
            dt_ing = _parse_fecha_db(fecha_ingreso)
            dt_out = datetime.now()
            if not dt_ing:
                dt_ing = dt_out
            horas_cobradas, total = _calcular_total_estadia(
                dt_ing,
                dt_out,
                tarifa,
                tolerancia_min=15,
            )
            ref_externa = None
            if _es_metodo_qr(metodo):
                ref_externa = _solicitar_ref_qr(
                    self,
                    total,
                    f"Salida estacionamiento {patente}",
                )
                if ref_externa is None:
                    self._log_estacionamiento("Cobro QR cancelado.", "warn")
                    return

            cur.execute(
                "UPDATE movimientos SET fecha_salida = CURRENT_TIMESTAMP, total = ? "
                "WHERE id_movimiento = ?",
                (total, row["id_movimiento"]),
            )
            cur.execute(
                "INSERT INTO pagos (id_movimiento, monto, metodo, ref_externa, usuario) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    row["id_movimiento"],
                    total,
                    metodo,
                    ref_externa,
                    (self.usuario or "").strip() or None,
                ),
            )
            conn.commit()
            ingreso_txt = dt_ing.strftime("%d/%m/%Y %H:%M:%S")
            salida_txt = dt_out.strftime("%d/%m/%Y %H:%M:%S")
            ticket = None
            try:
                ticket = _emitir_ticket_estacionamiento(
                    evento="Salida",
                    patente=patente,
                    espacio=row["codigo"],
                    dt_ingreso=dt_ing,
                    dt_salida=dt_out,
                    tarifa_hora=tarifa,
                    horas_cobradas=horas_cobradas,
                    total=total,
                    metodo=metodo,
                    movimiento_id=row["id_movimiento"],
                    ref_externa=ref_externa,
                    tipo_vehiculo=tipo_vehiculo,
                )
            except Exception:
                ticket = None
            self._log_estacionamiento(
                f"Salida registrada. Total: $ {total:.2f} "
                f"({horas_cobradas} hora/s cobradas, Espacio {row['codigo']}).",
                "ok",
                mostrar_popup=False,
            )
            box = QMessageBox(self)
            box.setWindowTitle("Detalle de salida")
            box.setIcon(QMessageBox.Information)
            texto = (
                f"Patente: {patente}\n"
                f"Tipo: {_label_tipo_vehiculo(tipo_vehiculo)}\n"
                f"Espacio: {row['codigo']}\n"
                f"Ingreso: {ingreso_txt}\n"
                f"Salida: {salida_txt}\n"
                f"Horas cobradas: {horas_cobradas}\n"
                f"Metodo: {metodo}\n"
                f"Precio: $ {total:.2f}"
            )
            if ref_externa:
                texto += f"\nReferencia QR: {ref_externa}"
            btn_abrir = None
            if ticket:
                texto += f"\nTicket: {Path(ticket).name}"
                btn_abrir = box.addButton("Abrir ticket", QMessageBox.ActionRole)
            box.setText(texto)
            box.addButton("Aceptar", QMessageBox.AcceptRole)
            box.exec()
            if btn_abrir and box.clickedButton() == btn_abrir:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(ticket)))
            self.ui.input_patente_est.clear()
            self._actualizar_activos_est()
        except sqlite3.Error:
            self._log_estacionamiento("Error al registrar salida.", "error")
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
                "SELECT v.patente, e.codigo, m.fecha_ingreso "
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
                                                                                                                                                
