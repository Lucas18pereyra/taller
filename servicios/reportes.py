import sqlite3

from database import get_connection


def consultar_resumen(mes_key):
    cochera = 0.0
    estacionamiento = 0.0
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM pagos_cochera "
            "WHERE strftime('%Y-%m', fecha_pago) = ?",
            (mes_key,),
        )
        cochera = float(cur.fetchone()[0] or 0.0)
        cur.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM pagos "
            "WHERE strftime('%Y-%m', fecha_pago) = ?",
            (mes_key,),
        )
        estacionamiento = float(cur.fetchone()[0] or 0.0)
    except sqlite3.Error:
        pass
    finally:
        if conn:
            conn.close()
    return cochera, estacionamiento, cochera + estacionamiento


def consultar_resumen_rango(desde_key, hasta_key):
    cochera = 0.0
    estacionamiento = 0.0
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM pagos_cochera "
            "WHERE date(fecha_pago) BETWEEN date(?) AND date(?)",
            (desde_key, hasta_key),
        )
        cochera = float(cur.fetchone()[0] or 0.0)
        cur.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM pagos "
            "WHERE date(fecha_pago) BETWEEN date(?) AND date(?)",
            (desde_key, hasta_key),
        )
        estacionamiento = float(cur.fetchone()[0] or 0.0)
    except sqlite3.Error:
        pass
    finally:
        if conn:
            conn.close()
    return cochera, estacionamiento, cochera + estacionamiento


def consultar_detalle(mes_key):
    detalle = []
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT pc.id_pago, pc.fecha_pago, pc.monto, pc.metodo, "
            "COALESCE(pc.usuario, '') AS usuario, "
            "COALESCE(c.nombre, '') AS nombre, "
            "COALESCE(e.codigo, '') AS codigo, "
            "pc.id_contrato "
            "FROM pagos_cochera pc "
            "LEFT JOIN cochera_contratos cc ON cc.id_contrato = pc.id_contrato "
            "LEFT JOIN clientes c ON c.id_cliente = cc.id_cliente "
            "LEFT JOIN espacios e ON e.id_espacio = cc.id_espacio "
            "WHERE strftime('%Y-%m', pc.fecha_pago) = ? "
            "ORDER BY pc.fecha_pago DESC",
            (mes_key,),
        )
        for row in cur.fetchall():
            detalle.append(
                {
                    "pago_id": row["id_pago"],
                    "tipo": "Cochera",
                    "fecha_pago": row["fecha_pago"],
                    "monto": row["monto"],
                    "metodo": row["metodo"],
                    "usuario": row["usuario"] or "",
                    "cliente": row["nombre"] or "",
                    "patente": "",
                    "espacio": row["codigo"] or "",
                    "contrato_id": row["id_contrato"],
                    "movimiento_id": "",
                    "tipo_vehiculo": "",
                }
            )

        cur.execute(
            "SELECT p.id_pago, p.fecha_pago, p.monto, p.metodo, "
            "COALESCE(p.usuario, '') AS usuario, "
            "COALESCE(m.tipo_vehiculo, 'AUTO') AS tipo_vehiculo, "
            "COALESCE(v.patente, '') AS patente, "
            "COALESCE(e.codigo, '') AS codigo, "
            "p.id_movimiento "
            "FROM pagos p "
            "LEFT JOIN movimientos m ON m.id_movimiento = p.id_movimiento "
            "LEFT JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
            "LEFT JOIN espacios e ON e.id_espacio = m.id_espacio "
            "WHERE strftime('%Y-%m', p.fecha_pago) = ? "
            "ORDER BY p.fecha_pago DESC",
            (mes_key,),
        )
        for row in cur.fetchall():
            detalle.append(
                {
                    "pago_id": row["id_pago"],
                    "tipo": "Estacionamiento",
                    "fecha_pago": row["fecha_pago"],
                    "monto": row["monto"],
                    "metodo": row["metodo"],
                    "usuario": row["usuario"] or "",
                    "cliente": "Estacionamiento",
                    "patente": row["patente"] or "",
                    "espacio": row["codigo"] or "",
                    "contrato_id": "",
                    "movimiento_id": row["id_movimiento"],
                    "tipo_vehiculo": row["tipo_vehiculo"] or "AUTO",
                }
            )
    except sqlite3.Error:
        pass
    finally:
        if conn:
            conn.close()
    return detalle


def consultar_detalle_rango(desde_key, hasta_key):
    detalle = []
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT pc.id_pago, pc.fecha_pago, pc.monto, pc.metodo, "
            "COALESCE(pc.usuario, '') AS usuario, "
            "COALESCE(c.nombre, '') AS nombre, "
            "COALESCE(e.codigo, '') AS codigo, "
            "pc.id_contrato "
            "FROM pagos_cochera pc "
            "LEFT JOIN cochera_contratos cc ON cc.id_contrato = pc.id_contrato "
            "LEFT JOIN clientes c ON c.id_cliente = cc.id_cliente "
            "LEFT JOIN espacios e ON e.id_espacio = cc.id_espacio "
            "WHERE date(pc.fecha_pago) BETWEEN date(?) AND date(?) "
            "ORDER BY pc.fecha_pago DESC",
            (desde_key, hasta_key),
        )
        for row in cur.fetchall():
            detalle.append(
                {
                    "pago_id": row["id_pago"],
                    "tipo": "Cochera",
                    "fecha_pago": row["fecha_pago"],
                    "monto": row["monto"],
                    "metodo": row["metodo"],
                    "usuario": row["usuario"] or "",
                    "cliente": row["nombre"] or "",
                    "patente": "",
                    "espacio": row["codigo"] or "",
                    "contrato_id": row["id_contrato"],
                    "movimiento_id": "",
                    "tipo_vehiculo": "",
                }
            )

        cur.execute(
            "SELECT p.id_pago, p.fecha_pago, p.monto, p.metodo, "
            "COALESCE(p.usuario, '') AS usuario, "
            "COALESCE(m.tipo_vehiculo, 'AUTO') AS tipo_vehiculo, "
            "COALESCE(v.patente, '') AS patente, "
            "COALESCE(e.codigo, '') AS codigo, "
            "p.id_movimiento "
            "FROM pagos p "
            "LEFT JOIN movimientos m ON m.id_movimiento = p.id_movimiento "
            "LEFT JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
            "LEFT JOIN espacios e ON e.id_espacio = m.id_espacio "
            "WHERE date(p.fecha_pago) BETWEEN date(?) AND date(?) "
            "ORDER BY p.fecha_pago DESC",
            (desde_key, hasta_key),
        )
        for row in cur.fetchall():
            detalle.append(
                {
                    "pago_id": row["id_pago"],
                    "tipo": "Estacionamiento",
                    "fecha_pago": row["fecha_pago"],
                    "monto": row["monto"],
                    "metodo": row["metodo"],
                    "usuario": row["usuario"] or "",
                    "cliente": "Estacionamiento",
                    "patente": row["patente"] or "",
                    "espacio": row["codigo"] or "",
                    "contrato_id": "",
                    "movimiento_id": row["id_movimiento"],
                    "tipo_vehiculo": row["tipo_vehiculo"] or "AUTO",
                }
            )
    except sqlite3.Error:
        pass
    finally:
        if conn:
            conn.close()
    return detalle


def consultar_pagos_mensuales_rango(desde_key, hasta_key):
    detalle = []
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT pc.id_pago, pc.fecha_pago, pc.monto, pc.metodo, "
            "COALESCE(c.nombre, '') AS nombre, "
            "COALESCE(c.dni, '') AS dni, "
            "COALESCE(e.codigo, '') AS codigo, "
            "pc.id_contrato, "
            "(SELECT v.patente FROM vehiculos v "
            " WHERE v.id_cliente = c.id_cliente ORDER BY v.patente LIMIT 1) AS patente "
            "FROM pagos_cochera pc "
            "LEFT JOIN cochera_contratos cc ON cc.id_contrato = pc.id_contrato "
            "LEFT JOIN clientes c ON c.id_cliente = cc.id_cliente "
            "LEFT JOIN espacios e ON e.id_espacio = cc.id_espacio "
            "WHERE date(pc.fecha_pago) BETWEEN date(?) AND date(?) "
            "ORDER BY pc.fecha_pago DESC",
            (desde_key, hasta_key),
        )
        for row in cur.fetchall():
            detalle.append(
                {
                    "id_pago": row["id_pago"],
                    "fecha_pago": row["fecha_pago"],
                    "monto": row["monto"],
                    "metodo": row["metodo"],
                    "cliente": row["nombre"] or "",
                    "dni": row["dni"] or "",
                    "patente": row["patente"] or "",
                    "espacio": row["codigo"] or "",
                    "id_contrato": row["id_contrato"],
                }
            )
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()
    return detalle
