import sqlite3
import calendar
from datetime import date, datetime

from database import get_connection
from servicios.validaciones import cliente_tiene_movimiento_activo


def obtener_patente_por_dni(dni):
    dni = (dni or "").strip()
    if not dni:
        return ""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT v.patente "
            "FROM clientes c "
            "LEFT JOIN vehiculos v ON v.id_cliente = c.id_cliente "
            "WHERE c.dni = ? "
            "ORDER BY v.patente LIMIT 1",
            (dni,),
        )
        row = cur.fetchone()
        return (row["patente"] if row and row["patente"] else "") or ""
    except sqlite3.Error:
        return ""
    finally:
        if conn:
            conn.close()


def obtener_tarifa_mensual_actual():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT precio_mensual FROM tarifas WHERE activa = 1 "
            "ORDER BY fecha_desde DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row and row["precio_mensual"] is not None:
            return float(row["precio_mensual"])
        return None
    except sqlite3.Error:
        return None
    finally:
        if conn:
            conn.close()


def listar_contratos():
    conn = None
    salida = []
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT cc.id_contrato, c.nombre, c.dni, "
            "(SELECT v.patente FROM vehiculos v "
            "WHERE v.id_cliente = c.id_cliente "
            "ORDER BY v.patente LIMIT 1) AS patente, "
            "e.codigo, cc.fecha_inicio, cc.fecha_vencimiento, "
            "cc.monto_mensual, cc.activo, e.id_espacio "
            "FROM cochera_contratos cc "
            "JOIN clientes c ON c.id_cliente = cc.id_cliente "
            "JOIN espacios e ON e.id_espacio = cc.id_espacio "
            "ORDER BY cc.activo DESC, cc.fecha_vencimiento"
        )
        for row in cur.fetchall():
            salida.append(dict(row))
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()
    return salida


def obtener_detalle_contrato(id_contrato):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT c.dni, "
            "(SELECT v.patente FROM vehiculos v "
            "WHERE v.id_cliente = c.id_cliente "
            "ORDER BY v.patente LIMIT 1) AS patente, "
            "e.codigo, cc.fecha_vencimiento, cc.monto_mensual, cc.activo "
            "FROM cochera_contratos cc "
            "JOIN clientes c ON c.id_cliente = cc.id_cliente "
            "JOIN espacios e ON e.id_espacio = cc.id_espacio "
            "WHERE cc.id_contrato = ?",
            (id_contrato,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None
    finally:
        if conn:
            conn.close()


def _parse_date(valor):
    if isinstance(valor, date):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    texto = str(valor or "").strip()
    if not texto:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            pass
    return None


def _add_months(base_date, months):
    months = int(months)
    y = base_date.year + (base_date.month - 1 + months) // 12
    m = (base_date.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    d = min(base_date.day, last_day)
    return date(y, m, d)


def calcular_nueva_fecha_vencimiento(fecha_vencimiento, meses, hoy=None):
    meses = int(meses or 0)
    if meses < 1:
        raise ValueError("Los meses deben ser 1 o mas.")

    fecha_venc = _parse_date(fecha_vencimiento)
    hoy_date = _parse_date(hoy) or date.today()
    base = fecha_venc if fecha_venc and fecha_venc >= hoy_date else hoy_date
    return _add_months(base, meses).isoformat()


def registrar_primer_pago_contrato(
    id_contrato,
    monto,
    metodo,
    ref_externa=None,
    usuario=None,
):
    monto = float(monto or 0.0)
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0.")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id_espacio, id_cliente, activo, fecha_vencimiento "
            "FROM cochera_contratos WHERE id_contrato = ?",
            (id_contrato,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Contrato no encontrado.")
        if int(row["activo"] or 0) == 1:
            raise ValueError("El contrato ya esta ACTIVO.")
        fecha_venc = _parse_date(row["fecha_vencimiento"])
        if fecha_venc and fecha_venc < date.today():
            raise ValueError(
                "El contrato esta vencido. Ajusta el vencimiento antes de activar."
            )

        id_espacio = row["id_espacio"]
        id_cliente = row["id_cliente"]

        if id_espacio:
            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos "
                "WHERE id_espacio = ? AND activo = 1 AND id_contrato <> ?",
                (id_espacio, id_contrato),
            )
            if (cur.fetchone()[0] or 0) > 0:
                raise ValueError("Ya existe un contrato activo para ese espacio.")

        if id_cliente:
            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos "
                "WHERE id_cliente = ? AND activo = 1 AND id_contrato <> ?",
                (id_cliente, id_contrato),
            )
            if (cur.fetchone()[0] or 0) > 0:
                raise ValueError("Ese cliente ya tiene otro contrato activo.")

        if id_cliente:
            mov = cliente_tiene_movimiento_activo(cur, id_cliente)
            if mov:
                patente = mov["patente"] or "-"
                codigo = mov["codigo"] or "-"
                raise ValueError(
                    f"La patente {patente} tiene un ingreso activo en "
                    f"estacionamiento (espacio {codigo}). Registra la salida "
                    "antes de activar el contrato."
                )

        cur.execute(
            "INSERT INTO pagos_cochera (id_contrato, monto, metodo, ref_externa, usuario) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                id_contrato,
                monto,
                metodo,
                (ref_externa or "").strip() or None,
                (usuario or "").strip() or None,
            ),
        )
        cur.execute(
            "UPDATE cochera_contratos SET activo = 1 WHERE id_contrato = ?",
            (id_contrato,),
        )
        if id_espacio and id_cliente:
            cur.execute(
                "UPDATE espacios SET id_cliente = ? WHERE id_espacio = ?",
                (id_cliente, id_espacio),
            )
        conn.commit()
        return {
            "fecha_vencimiento": row["fecha_vencimiento"],
            "id_espacio": id_espacio,
            "id_cliente": id_cliente,
        }
    finally:
        if conn:
            conn.close()


def registrar_renovacion_contrato(
    id_contrato,
    meses,
    monto,
    metodo,
    hoy=None,
    ref_externa=None,
    usuario=None,
):
    meses = int(meses or 0)
    monto = float(monto or 0.0)
    if meses < 1:
        raise ValueError("Los meses deben ser 1 o mas.")
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0.")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT fecha_vencimiento, activo FROM cochera_contratos WHERE id_contrato = ?",
            (id_contrato,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Contrato no encontrado.")
        if int(row["activo"] or 0) != 1:
            raise ValueError("El contrato esta INACTIVO.")

        nueva_venc = calcular_nueva_fecha_vencimiento(
            row["fecha_vencimiento"],
            meses,
            hoy=hoy,
        )
        cur.execute(
            "INSERT INTO pagos_cochera (id_contrato, monto, metodo, ref_externa, usuario) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                id_contrato,
                monto,
                metodo,
                (ref_externa or "").strip() or None,
                (usuario or "").strip() or None,
            ),
        )
        cur.execute(
            "UPDATE cochera_contratos SET fecha_vencimiento = ?, activo = 1 "
            "WHERE id_contrato = ?",
            (nueva_venc, id_contrato),
        )
        conn.commit()
        return nueva_venc
    finally:
        if conn:
            conn.close()
