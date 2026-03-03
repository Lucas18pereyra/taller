from database import get_connection
from datetime import datetime
import math


def obtener_o_crear_vehiculo(patente):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id_vehiculo, id_cliente FROM vehiculos WHERE patente = ?",
        (patente,)
    )
    row = cursor.fetchone()

    if row:
        conn.close()
        return row["id_vehiculo"], row["id_cliente"]

    cursor.execute(
        "INSERT INTO vehiculos (patente) VALUES (?)",
        (patente,)
    )
    conn.commit()
    vehiculo_id = cursor.lastrowid
    conn.close()

    return vehiculo_id, None


def buscar_espacio_disponible(id_cliente=None):
    conn = get_connection()
    cursor = conn.cursor()

    # Cliente fijo → su espacio reservado
    if id_cliente:
        cursor.execute("""
            SELECT id_espacio
            FROM espacios
            WHERE id_cliente = ?
              AND activo = 1
        """, (id_cliente,))
        row = cursor.fetchone()
        conn.close()
        return row["id_espacio"] if row else None

    # Visitante → espacio libre
    cursor.execute("""
        SELECT e.id_espacio
        FROM espacios e
        LEFT JOIN movimientos m
          ON e.id_espacio = m.id_espacio
          AND m.fecha_salida IS NULL
        WHERE e.activo = 1
          AND e.es_reservado = 0
          AND m.id_movimiento IS NULL
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row["id_espacio"] if row else None


def ingresar_vehiculo(patente):
    vehiculo_id, id_cliente = obtener_o_crear_vehiculo(patente)
    espacio_id = buscar_espacio_disponible(id_cliente)

    if not espacio_id:
        raise Exception("No hay espacios disponibles")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO movimientos (id_vehiculo, id_espacio)
        VALUES (?, ?)
    """, (vehiculo_id, espacio_id))

    conn.commit()
    conn.close()

    return espacio_id


def salir_vehiculo(patente):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT m.id_movimiento, m.fecha_ingreso
        FROM movimientos m
        JOIN vehiculos v ON m.id_vehiculo = v.id_vehiculo
        WHERE v.patente = ?
          AND m.fecha_salida IS NULL
    """, (patente,))
    mov = cursor.fetchone()

    if not mov:
        conn.close()
        raise Exception("El vehículo no está dentro")

    ingreso = datetime.fromisoformat(mov["fecha_ingreso"])
    horas = math.ceil((datetime.now() - ingreso).total_seconds() / 3600)

    cursor.execute("""
        SELECT precio_hora
        FROM tarifas
        WHERE activa = 1
        ORDER BY fecha_desde DESC
        LIMIT 1
    """)
    tarifa = cursor.fetchone()

    if not tarifa:
        conn.close()
        raise Exception("No hay tarifa activa")

    total = horas * tarifa["precio_hora"]

    cursor.execute("""
        UPDATE movimientos
        SET fecha_salida = CURRENT_TIMESTAMP,
            total = ?
        WHERE id_movimiento = ?
    """, (total, mov["id_movimiento"]))

    conn.commit()
    conn.close()

    return total
