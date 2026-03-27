import sqlite3
import calendar
from datetime import date, datetime

from database import get_connection
from servicios.validaciones import (
    cliente_tiene_movimiento_activo,
    espacio_tiene_movimiento_activo,
)


def _normalizar_tipo_vehiculo(tipo):
    txt = (tipo or "").strip().upper()
    if txt in ("MOTO", "MOTOCICLETA"):
        return "MOTO"
    if txt in ("CAMIONETA", "PICKUP"):
        return "CAMIONETA"
    return "AUTO"


def _normalizar_patente(texto):
    return "".join(str(texto or "").upper().split())


def listar_vehiculos_por_dni(dni):
    dni = (dni or "").strip()
    if not dni:
        return []
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT c.id_cliente, c.nombre, c.telefono, "
            "v.id_vehiculo, v.patente, v.modelo, "
            "COALESCE(NULLIF(TRIM(v.tipo_vehiculo), ''), 'AUTO') AS tipo_vehiculo "
            "FROM clientes c "
            "JOIN vehiculos v ON v.id_cliente = c.id_cliente "
            "WHERE c.dni = ? AND COALESCE(c.activo, 0) = 1 "
            "AND v.patente IS NOT NULL AND TRIM(v.patente) <> '' "
            "ORDER BY v.patente",
            (dni,),
        )
        return [dict(row) for row in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()


def listar_patentes_por_dni(dni):
    salida = []
    for row in listar_vehiculos_por_dni(dni):
        salida.append(
            {
                "id_vehiculo": row.get("id_vehiculo"),
                "patente": row.get("patente"),
            }
        )
    return salida


def obtener_vehiculo_por_dni(dni, patente_preferida=None):
    vehiculos = listar_vehiculos_por_dni(dni)
    if not vehiculos:
        return {}
    preferida = _normalizar_patente(patente_preferida)
    if preferida:
        for row in vehiculos:
            if _normalizar_patente(row.get("patente")) == preferida:
                return dict(row)
    return dict(vehiculos[0])


def obtener_patente_por_dni(dni, patente_preferida=None):
    row = obtener_vehiculo_por_dni(dni, patente_preferida)
    return (row.get("patente") or "") if row else ""


def obtener_tarifa_mensual_actual(tipo_vehiculo="AUTO"):
    tipo_norm = _normalizar_tipo_vehiculo(tipo_vehiculo)
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT precio_mensual, "
                "COALESCE(precio_mensual_auto, precio_mensual) AS precio_mensual_auto, "
                "COALESCE(precio_mensual_camioneta, precio_mensual) AS precio_mensual_camioneta "
                "FROM tarifas WHERE activa = 1 "
                "ORDER BY fecha_desde DESC LIMIT 1"
            )
            row = cur.fetchone()
        except sqlite3.OperationalError:
            cur.execute(
                "SELECT precio_mensual FROM tarifas WHERE activa = 1 "
                "ORDER BY fecha_desde DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row and row["precio_mensual"] is not None:
                return float(row["precio_mensual"])
            return None
        if not row:
            return None
        if tipo_norm == "CAMIONETA":
            valor = row["precio_mensual_camioneta"]
        else:
            valor = row["precio_mensual_auto"]
        if valor is None:
            valor = row["precio_mensual"]
        return float(valor) if valor is not None else None
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
            "COALESCE(c.activo, 0) AS cliente_activo, "
            "COALESCE(c.telefono, '') AS telefono, "
            "COALESCE(v_sel.patente, (SELECT v.patente FROM vehiculos v "
            "WHERE v.id_cliente = c.id_cliente "
            "ORDER BY v.patente LIMIT 1)) AS patente, "
            "COALESCE(v_sel.modelo, (SELECT COALESCE(v.modelo, '') FROM vehiculos v "
            "WHERE v.id_cliente = c.id_cliente "
            "ORDER BY v.patente LIMIT 1), '') AS modelo, "
            "COALESCE(NULLIF(TRIM(v_sel.tipo_vehiculo), ''), "
            "(SELECT COALESCE(NULLIF(TRIM(v.tipo_vehiculo), ''), 'AUTO') FROM vehiculos v "
            "WHERE v.id_cliente = c.id_cliente "
            "ORDER BY v.patente LIMIT 1), 'AUTO') AS tipo_vehiculo, "
            "e.codigo, cc.fecha_inicio, cc.fecha_vencimiento, "
            "cc.monto_mensual, cc.activo, COALESCE(cc.en_historial, 0) AS en_historial, "
            "e.id_espacio, cc.id_vehiculo "
            "FROM cochera_contratos cc "
            "JOIN clientes c ON c.id_cliente = cc.id_cliente "
            "JOIN espacios e ON e.id_espacio = cc.id_espacio "
            "LEFT JOIN vehiculos v_sel ON v_sel.id_vehiculo = cc.id_vehiculo "
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
            "SELECT c.nombre, c.dni, COALESCE(c.telefono, '') AS telefono, "
            "COALESCE(c.activo, 0) AS cliente_activo, "
            "COALESCE(v_sel.patente, (SELECT v.patente FROM vehiculos v "
            "WHERE v.id_cliente = c.id_cliente "
            "ORDER BY v.patente LIMIT 1)) AS patente, "
            "COALESCE(v_sel.modelo, (SELECT COALESCE(v.modelo, '') FROM vehiculos v "
            "WHERE v.id_cliente = c.id_cliente "
            "ORDER BY v.patente LIMIT 1), '') AS modelo, "
            "COALESCE(NULLIF(TRIM(v_sel.tipo_vehiculo), ''), "
            "(SELECT COALESCE(NULLIF(TRIM(v.tipo_vehiculo), ''), 'AUTO') FROM vehiculos v "
            "WHERE v.id_cliente = c.id_cliente "
            "ORDER BY v.patente LIMIT 1), 'AUTO') AS tipo_vehiculo, "
            "e.codigo, cc.fecha_vencimiento, cc.monto_mensual, cc.activo, "
            "COALESCE(cc.en_historial, 0) AS en_historial, "
            "cc.id_vehiculo "
            "FROM cochera_contratos cc "
            "JOIN clientes c ON c.id_cliente = cc.id_cliente "
            "JOIN espacios e ON e.id_espacio = cc.id_espacio "
            "LEFT JOIN vehiculos v_sel ON v_sel.id_vehiculo = cc.id_vehiculo "
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
            "SELECT id_espacio, id_cliente, id_vehiculo, activo, fecha_vencimiento "
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
        id_vehiculo = row["id_vehiculo"]
        if id_espacio:
            cur.execute(
                "SELECT codigo, COALESCE(es_reservado, 0) AS es_reservado "
                "FROM espacios WHERE id_espacio = ?",
                (id_espacio,),
            )
            row_esp = cur.fetchone()
            if not row_esp:
                raise ValueError("El espacio asociado al contrato ya no existe.")
            if int(row_esp["es_reservado"] or 0) != 1:
                raise ValueError(
                    f"El espacio {row_esp['codigo'] or '-'} ya no esta marcado como cochera en el mapa."
                )
        if id_cliente:
            cur.execute(
                "SELECT COALESCE(activo, 0) AS activo FROM clientes WHERE id_cliente = ?",
                (id_cliente,),
            )
            row_cli = cur.fetchone()
            if not row_cli or int(row_cli["activo"] or 0) != 1:
                raise ValueError("El cliente del contrato esta desactivado.")

        patente_principal = ""
        if id_vehiculo:
            cur.execute(
                "SELECT patente, id_cliente FROM vehiculos WHERE id_vehiculo = ?",
                (id_vehiculo,),
            )
            row_pat = cur.fetchone()
            if not row_pat:
                raise ValueError("La patente asociada al contrato ya no existe.")
            if id_cliente and int(row_pat["id_cliente"] or 0) != int(id_cliente):
                raise ValueError("La patente asociada no pertenece a ese cliente.")
            patente_principal = (row_pat["patente"] or "").strip().upper()
        elif id_cliente:
            cur.execute(
                "SELECT id_vehiculo, patente FROM vehiculos "
                "WHERE id_cliente = ? AND patente IS NOT NULL AND TRIM(patente) <> '' "
                "ORDER BY patente LIMIT 1",
                (id_cliente,),
            )
            row_pat = cur.fetchone()
            if not row_pat:
                raise ValueError("Este cliente no tiene ninguna patente a su nombre.")
            id_vehiculo = row_pat["id_vehiculo"]
            patente_principal = (row_pat["patente"] or "").strip().upper()
            cur.execute(
                "UPDATE cochera_contratos SET id_vehiculo = ? WHERE id_contrato = ?",
                (id_vehiculo, id_contrato),
            )

        if id_espacio:
            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos "
                "WHERE id_espacio = ? AND activo = 1 AND id_contrato <> ?",
                (id_espacio, id_contrato),
            )
            if (cur.fetchone()[0] or 0) > 0:
                raise ValueError("Ya existe un contrato activo para ese espacio.")
            mov_espacio = espacio_tiene_movimiento_activo(cur, id_espacio)
            if mov_espacio:
                patente = mov_espacio["patente"] or "-"
                codigo = mov_espacio["codigo"] or "-"
                raise ValueError(
                    f"El espacio {codigo} esta ocupado por la patente {patente} "
                    "en estacionamiento. Registra la salida antes de activar el contrato."
                )

        if id_vehiculo:
            cur.execute(
                "SELECT e.codigo "
                "FROM cochera_contratos cc "
                "JOIN espacios e ON e.id_espacio = cc.id_espacio "
                "WHERE cc.activo = 1 AND cc.id_contrato <> ? AND cc.id_vehiculo = ? "
                "LIMIT 1",
                (id_contrato, id_vehiculo),
            )
            row_pat_act = cur.fetchone()
            if row_pat_act:
                raise ValueError(
                    (
                        f"La patente {patente_principal} ya tiene un contrato activo "
                        f"(espacio {row_pat_act['codigo']})."
                    )
                )

        if id_vehiculo:
            cur.execute(
                "SELECT e.codigo, v.patente "
                "FROM movimientos m "
                "JOIN espacios e ON e.id_espacio = m.id_espacio "
                "JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
                "WHERE m.id_vehiculo = ? AND m.fecha_salida IS NULL "
                "ORDER BY m.id_movimiento DESC LIMIT 1",
                (id_vehiculo,),
            )
            mov = cur.fetchone()
            if mov:
                patente = mov["patente"] or "-"
                codigo = mov["codigo"] or "-"
                raise ValueError(
                    f"La patente {patente} tiene un ingreso activo en "
                    f"estacionamiento (espacio {codigo}). Registra la salida "
                    "antes de activar el contrato."
                )
        elif id_cliente:
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
            "UPDATE cochera_contratos SET activo = 1, en_historial = 0 WHERE id_contrato = ?",
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
            "SELECT fecha_vencimiento, activo, id_cliente, id_espacio "
            "FROM cochera_contratos WHERE id_contrato = ?",
            (id_contrato,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Contrato no encontrado.")
        if int(row["activo"] or 0) != 1:
            raise ValueError("El contrato esta INACTIVO.")
        id_cliente = row["id_cliente"]
        id_espacio = row["id_espacio"] if "id_espacio" in row.keys() else None
        if id_espacio:
            cur.execute(
                "SELECT codigo, COALESCE(es_reservado, 0) AS es_reservado "
                "FROM espacios WHERE id_espacio = ?",
                (id_espacio,),
            )
            row_esp = cur.fetchone()
            if not row_esp:
                raise ValueError("El espacio asociado al contrato ya no existe.")
            if int(row_esp["es_reservado"] or 0) != 1:
                raise ValueError(
                    f"El espacio {row_esp['codigo'] or '-'} ya no esta marcado como cochera en el mapa."
                )
        if id_cliente:
            cur.execute(
                "SELECT COALESCE(activo, 0) AS activo FROM clientes WHERE id_cliente = ?",
                (id_cliente,),
            )
            row_cli = cur.fetchone()
            if not row_cli or int(row_cli["activo"] or 0) != 1:
                raise ValueError("El cliente del contrato esta desactivado.")

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


def reactivar_contrato_desde_historial(id_contrato, hoy=None):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id_cliente, fecha_vencimiento, COALESCE(en_historial, 0) AS en_historial "
            "FROM cochera_contratos WHERE id_contrato = ?",
            (id_contrato,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Contrato no encontrado.")
        if int(row["en_historial"] or 0) != 1:
            raise ValueError("Ese contrato ya no esta en historial.")

        id_cliente = row["id_cliente"]
        if id_cliente:
            cur.execute(
                "SELECT COALESCE(activo, 0) AS activo FROM clientes WHERE id_cliente = ?",
                (id_cliente,),
            )
            row_cli = cur.fetchone()
            if not row_cli or int(row_cli["activo"] or 0) != 1:
                raise ValueError(
                    "El cliente del contrato esta desactivado. Activalo primero desde Clientes."
                )

        hoy_date = _parse_date(hoy) or date.today()
        fecha_venc = _parse_date(row["fecha_vencimiento"])
        vencimiento_ajustado = False
        if fecha_venc and fecha_venc >= hoy_date:
            nueva_venc = fecha_venc.isoformat()
        else:
            nueva_venc = _add_months(hoy_date, 1).isoformat()
            vencimiento_ajustado = True

        cur.execute(
            "UPDATE cochera_contratos "
            "SET en_historial = 0, activo = 0, fecha_vencimiento = ? "
            "WHERE id_contrato = ?",
            (nueva_venc, id_contrato),
        )
        conn.commit()
        return {
            "fecha_vencimiento": nueva_venc,
            "vencimiento_ajustado": vencimiento_ajustado,
        }
    finally:
        if conn:
            conn.close()
