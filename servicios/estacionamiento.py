"""API compatible de estacionamiento, con ingreso y cobro atomicos.

Las fechas nuevas se guardan en hora local, igual que la interfaz, y cada
ingreso conserva la tarifa que le corresponde.
"""

from datetime import datetime
import re

from database import get_connection
from servicios.cobro import calcular_total_estadia, parse_fecha_db
from servicios.validaciones import (
    codigo_cochera_activa_cliente,
    normalizar_metodo_pago,
    normalizar_patente,
    validar_monto,
    vehiculo_tiene_movimiento_activo,
)


def _patente_valida(patente):
    patente = normalizar_patente(patente)
    if not re.fullmatch(r"(?:[A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\d{3}|\d{3}[A-Z]{3}|[A-Z]\d{3}[A-Z]{3})", patente):
        raise ValueError("La patente no tiene un formato valido.")
    return patente


def _obtener_o_crear_vehiculo(cur, patente):
    cur.execute("SELECT id_vehiculo, id_cliente, tipo_vehiculo FROM vehiculos WHERE patente = ?", (patente,))
    row = cur.fetchone()
    if row:
        return row["id_vehiculo"], row["id_cliente"], row["tipo_vehiculo"] or "AUTO"
    tipo = "MOTO" if re.fullmatch(r"(?:\d{3}[A-Z]{3}|[A-Z]\d{3}[A-Z]{3})", patente) else "AUTO"
    cur.execute("INSERT INTO vehiculos (patente, tipo_vehiculo) VALUES (?, ?)", (patente, tipo))
    return cur.lastrowid, None, tipo


def obtener_o_crear_vehiculo(patente):
    patente = _patente_valida(patente)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        vehiculo_id, id_cliente, _tipo = _obtener_o_crear_vehiculo(conn.cursor(), patente)
        conn.commit()
        return vehiculo_id, id_cliente
    finally:
        conn.close()


def _buscar_espacio_disponible(cur):
    cur.execute(
        "SELECT e.id_espacio FROM espacios e "
        "WHERE e.activo = 1 AND COALESCE(e.es_reservado, 0) = 0 AND e.id_cliente IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM movimientos m WHERE m.id_espacio = e.id_espacio AND m.fecha_salida IS NULL) "
        "AND NOT EXISTS (SELECT 1 FROM cochera_contratos cc WHERE cc.id_espacio = e.id_espacio AND cc.activo = 1) "
        "ORDER BY e.codigo, e.id_espacio LIMIT 1"
    )
    row = cur.fetchone()
    return row["id_espacio"] if row else None


def buscar_espacio_disponible(id_cliente=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if id_cliente and codigo_cochera_activa_cliente(cur, id_cliente):
            return None
        return _buscar_espacio_disponible(cur)
    finally:
        conn.close()


def _tarifa_actual(cur, tipo_vehiculo):
    cur.execute(
        "SELECT id_tarifa, precio_hora, precio_hora_auto, precio_hora_moto, precio_hora_camioneta "
        "FROM tarifas WHERE activa = 1 ORDER BY fecha_desde DESC, id_tarifa DESC LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("No hay una tarifa activa.")
    tipo = str(tipo_vehiculo or "AUTO").strip().upper()
    campo = "precio_hora_moto" if tipo in ("MOTO", "MOTOCICLETA") else (
        "precio_hora_camioneta" if tipo in ("CAMIONETA", "PICKUP") else "precio_hora_auto")
    valor = row[campo] if row[campo] is not None else row["precio_hora"]
    return row["id_tarifa"], validar_monto(valor, nombre="La tarifa por hora")


def ingresar_vehiculo(patente):
    patente = _patente_valida(patente)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        vehiculo_id, id_cliente, tipo = _obtener_o_crear_vehiculo(cur, patente)
        # Misma regla vigente de la UI para clientes con cochera.
        if codigo_cochera_activa_cliente(cur, id_cliente):
            raise ValueError("La patente pertenece a un cliente con cochera activa.")
        if vehiculo_tiene_movimiento_activo(cur, vehiculo_id):
            raise ValueError("El vehiculo ya tiene un ingreso activo.")
        espacio_id = _buscar_espacio_disponible(cur)
        if espacio_id is None:
            raise ValueError("No hay espacios disponibles.")
        tarifa_id, tarifa = _tarifa_actual(cur, tipo)
        ingreso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT INTO movimientos (id_vehiculo, id_espacio, fecha_ingreso, tipo_vehiculo, "
            "id_tarifa_aplicada, tarifa_hora_aplicada) VALUES (?, ?, ?, ?, ?, ?)",
            (vehiculo_id, espacio_id, ingreso, tipo, tarifa_id, tarifa),
        )
        conn.commit()
        return espacio_id
    finally:
        conn.close()


def salir_vehiculo(patente, metodo="Efectivo"):
    patente = _patente_valida(patente)
    metodo = normalizar_metodo_pago(metodo)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        cur.execute(
            "SELECT m.id_movimiento, m.fecha_ingreso, m.tipo_vehiculo, m.tarifa_hora_aplicada "
            "FROM movimientos m JOIN vehiculos v ON m.id_vehiculo = v.id_vehiculo "
            "WHERE v.patente = ? AND m.fecha_salida IS NULL ORDER BY m.id_movimiento DESC LIMIT 1",
            (patente,),
        )
        mov = cur.fetchone()
        if not mov:
            raise ValueError("El vehiculo no tiene un ingreso activo.")
        ingreso = parse_fecha_db(mov["fecha_ingreso"])
        if ingreso is None:
            raise ValueError("La fecha de ingreso no es valida. Corrigela antes de cobrar.")
        tarifa = mov["tarifa_hora_aplicada"]
        if tarifa is None:
            _tarifa_id, tarifa = _tarifa_actual(cur, mov["tipo_vehiculo"])
        else:
            tarifa = validar_monto(tarifa, permitir_cero=True, nombre="La tarifa aplicada")
        salida = datetime.now()
        _horas, total = calcular_total_estadia(ingreso, salida, tarifa, tolerancia_min=15)
        salida_db = salida.strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE movimientos SET fecha_salida = ?, total = ? "
                    "WHERE id_movimiento = ? AND fecha_salida IS NULL", (salida_db, total, mov["id_movimiento"]))
        if cur.rowcount != 1:
            raise ValueError("La salida del vehiculo ya fue registrada.")
        cur.execute("INSERT INTO pagos (id_movimiento, monto, metodo, fecha_pago) VALUES (?, ?, ?, ?)",
                    (mov["id_movimiento"], total, metodo, salida_db))
        conn.commit()
        return total
    finally:
        conn.close()
