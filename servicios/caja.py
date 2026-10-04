import sqlite3
import math
from datetime import date, datetime

from database import get_connection
from servicios.validaciones import validar_monto


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
        raise
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
        raise
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
        raise
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
        raise
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
        fecha_key = date.fromisoformat(str(fecha_key)).isoformat()
        total_esperado = validar_monto(total_esperado, permitir_cero=True)
        total_contado = validar_monto(total_contado, permitir_cero=True)
        diferencia_calculada = round(total_contado - total_esperado, 2)
        if not math.isfinite(float(diferencia)) or abs(float(diferencia) - diferencia_calculada) > 0.009:
            raise ValueError("La diferencia de caja no coincide con los totales.")
        diferencia = diferencia_calculada
        if detalle_metodos is not None:
            detalles_validados = []
            metodos_vistos = set()
            for item in detalle_metodos:
                metodo = str(item.get("metodo") or "").strip() or "Sin metodo"
                if metodo.casefold() in metodos_vistos:
                    raise ValueError("Un metodo de pago aparece mas de una vez en el cierre.")
                metodos_vistos.add(metodo.casefold())
                esperado = validar_monto(item.get("total_esperado"), permitir_cero=True)
                contado = validar_monto(item.get("total_contado"), permitir_cero=True)
                diferencia_metodo = round(contado - esperado, 2)
                declarado = float(item.get("diferencia"))
                if not math.isfinite(declarado) or abs(declarado - diferencia_metodo) > 0.009:
                    raise ValueError("La diferencia por metodo no coincide con los totales.")
                detalles_validados.append({"metodo": metodo, "total_esperado": esperado,
                                           "total_contado": contado, "diferencia": diferencia_metodo})
            if (abs(sum(item["total_esperado"] for item in detalles_validados) - total_esperado) > 0.009
                    or abs(sum(item["total_contado"] for item in detalles_validados) - total_contado) > 0.009):
                raise ValueError("El detalle por metodo no coincide con el total del cierre.")
            detalle_metodos = detalles_validados
        fecha_cierre = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cierres_caja "
            "(fecha, total_esperado, total_contado, diferencia, observacion, usuario, fecha_cierre) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(fecha) DO UPDATE SET "
            "total_esperado=excluded.total_esperado, "
            "total_contado=excluded.total_contado, "
            "diferencia=excluded.diferencia, "
            "observacion=excluded.observacion, "
            "usuario=excluded.usuario, "
            "fecha_cierre=excluded.fecha_cierre",
            (
                fecha_key,
                float(total_esperado or 0.0),
                float(total_contado or 0.0),
                float(diferencia or 0.0),
                (observacion or "").strip(),
                (usuario or "sistema").strip() or "sistema",
                fecha_cierre,
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
    except (sqlite3.Error, ValueError, TypeError, OverflowError):
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
