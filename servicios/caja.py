import sqlite3

from database import get_connection


def consultar_totales_dia(fecha_key):
    cochera = 0.0
    estacionamiento = 0.0
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM pagos_cochera "
            "WHERE date(fecha_pago) = ?",
            (fecha_key,),
        )
        cochera = float(cur.fetchone()[0] or 0.0)
        cur.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM pagos "
            "WHERE date(fecha_pago) = ?",
            (fecha_key,),
        )
        estacionamiento = float(cur.fetchone()[0] or 0.0)
    except sqlite3.Error:
        pass
    finally:
        if conn:
            conn.close()
    return cochera, estacionamiento, cochera + estacionamiento


def consultar_detalle_por_metodo_dia(fecha_key):
    detalle = []
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT metodo, "
            "SUM(CASE WHEN tipo = 'Cochera' THEN monto ELSE 0 END) AS cochera, "
            "SUM(CASE WHEN tipo = 'Estacionamiento' THEN monto ELSE 0 END) AS estacionamiento, "
            "SUM(monto) AS total, "
            "COUNT(*) AS operaciones "
            "FROM ( "
            "  SELECT metodo, monto, 'Cochera' AS tipo FROM pagos_cochera WHERE date(fecha_pago) = ? "
            "  UNION ALL "
            "  SELECT metodo, monto, 'Estacionamiento' AS tipo FROM pagos WHERE date(fecha_pago) = ? "
            ") t "
            "GROUP BY metodo "
            "ORDER BY metodo",
            (fecha_key, fecha_key),
        )
        for row in cur.fetchall():
            detalle.append(
                {
                    "metodo": row["metodo"] or "Sin metodo",
                    "cochera": float(row["cochera"] or 0.0),
                    "estacionamiento": float(row["estacionamiento"] or 0.0),
                    "total": float(row["total"] or 0.0),
                    "operaciones": int(row["operaciones"] or 0),
                }
            )
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()
    return detalle


def obtener_cierre_caja(fecha_key):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT fecha, total_esperado, total_contado, diferencia, observacion, "
            "usuario, fecha_cierre "
            "FROM cierres_caja WHERE fecha = ?",
            (fecha_key,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "fecha": row["fecha"],
            "total_esperado": float(row["total_esperado"] or 0.0),
            "total_contado": float(row["total_contado"] or 0.0),
            "diferencia": float(row["diferencia"] or 0.0),
            "observacion": row["observacion"] or "",
            "usuario": row["usuario"] or "",
            "fecha_cierre": row["fecha_cierre"] or "",
        }
    except sqlite3.Error:
        return None
    finally:
        if conn:
            conn.close()


def obtener_cierre_caja_metodos(fecha_key):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT metodo, total_esperado, total_contado, diferencia "
            "FROM cierres_caja_metodos WHERE fecha = ? "
            "ORDER BY metodo",
            (fecha_key,),
        )
        rows = {}
        for row in cur.fetchall():
            metodo = (row["metodo"] or "").strip() or "Sin metodo"
            rows[metodo] = {
                "metodo": metodo,
                "total_esperado": float(row["total_esperado"] or 0.0),
                "total_contado": float(row["total_contado"] or 0.0),
                "diferencia": float(row["diferencia"] or 0.0),
            }
        return rows
    except sqlite3.Error:
        return {}
    finally:
        if conn:
            conn.close()


def guardar_cierre_caja(
    fecha_key,
    total_esperado,
    total_contado,
    diferencia,
    observacion="",
    usuario="sistema",
    detalle_metodos=None,
):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cierres_caja "
            "(fecha, total_esperado, total_contado, diferencia, observacion, usuario, fecha_cierre) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(fecha) DO UPDATE SET "
            "total_esperado=excluded.total_esperado, "
            "total_contado=excluded.total_contado, "
            "diferencia=excluded.diferencia, "
            "observacion=excluded.observacion, "
            "usuario=excluded.usuario, "
            "fecha_cierre=CURRENT_TIMESTAMP",
            (
                fecha_key,
                float(total_esperado or 0.0),
                float(total_contado or 0.0),
                float(diferencia or 0.0),
                (observacion or "").strip(),
                (usuario or "sistema").strip() or "sistema",
            ),
        )
        if detalle_metodos is not None:
            cur.execute(
                "DELETE FROM cierres_caja_metodos WHERE fecha = ?",
                (fecha_key,),
            )
            for item in detalle_metodos:
                metodo = (item.get("metodo") or "").strip() or "Sin metodo"
                cur.execute(
                    "INSERT INTO cierres_caja_metodos "
                    "(fecha, metodo, total_esperado, total_contado, diferencia) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        fecha_key,
                        metodo,
                        float(item.get("total_esperado") or 0.0),
                        float(item.get("total_contado") or 0.0),
                        float(item.get("diferencia") or 0.0),
                    ),
                )
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        if conn:
            conn.close()


def eliminar_cierre_caja(fecha_key):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM cierres_caja_metodos WHERE fecha = ?", (fecha_key,))
        cur.execute("DELETE FROM cierres_caja WHERE fecha = ?", (fecha_key,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        if conn:
            conn.close()
