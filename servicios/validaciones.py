import math


def normalizar_patente(texto):
    """Identidad de patente compartida con los formularios de la aplicacion."""
    return "".join(ch for ch in str(texto or "").strip().upper() if ch.isalnum())


def validar_monto(valor, *, permitir_cero=False, nombre="El monto"):
    try:
        monto = float(valor)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{nombre} debe ser un numero valido.") from exc
    if not math.isfinite(monto):
        raise ValueError(f"{nombre} debe ser un numero finito.")
    if monto < 0 or (monto == 0 and not permitir_cero):
        comparacion = "mayor o igual a 0" if permitir_cero else "mayor a 0"
        raise ValueError(f"{nombre} debe ser {comparacion}.")
    return monto


def normalizar_metodo_pago(metodo):
    texto = str(metodo or "").strip()
    if not texto:
        raise ValueError("Selecciona un metodo de pago.")
    conocidos = {"efectivo": "Efectivo", "transferencia": "Transferencia",
                 "tarjeta": "Tarjeta", "otro": "Otro", "qr": "QR"}
    try:
        return conocidos[texto.casefold()]
    except KeyError as exc:
        raise ValueError("El metodo de pago seleccionado no es valido.") from exc


def codigo_cochera_activa_cliente(cur, id_cliente):
    if id_cliente is None:
        return None
    cur.execute(
        "SELECT e.codigo "
        "FROM cochera_contratos cc "
        "JOIN espacios e ON e.id_espacio = cc.id_espacio "
        "WHERE cc.id_cliente = ? AND cc.activo = 1 "
        "ORDER BY cc.fecha_inicio DESC LIMIT 1",
        (id_cliente,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return row["codigo"] or "-"


def vehiculo_tiene_movimiento_activo(cur, id_vehiculo):
    cur.execute(
        "SELECT COUNT(*) FROM movimientos WHERE id_vehiculo = ? AND fecha_salida IS NULL",
        (id_vehiculo,),
    )
    return (cur.fetchone()[0] or 0) > 0


def cliente_tiene_movimiento_activo(cur, id_cliente):
    if id_cliente is None:
        return None
    cur.execute(
        "SELECT v.patente, e.codigo "
        "FROM movimientos m "
        "JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
        "LEFT JOIN espacios e ON e.id_espacio = m.id_espacio "
        "WHERE v.id_cliente = ? AND m.fecha_salida IS NULL "
        "ORDER BY m.fecha_ingreso LIMIT 1",
        (id_cliente,),
    )
    row = cur.fetchone()
    return row


def espacio_tiene_movimiento_activo(cur, id_espacio):
    if id_espacio is None:
        return None
    cur.execute(
        "SELECT v.patente, e.codigo "
        "FROM movimientos m "
        "JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
        "LEFT JOIN espacios e ON e.id_espacio = m.id_espacio "
        "WHERE m.id_espacio = ? AND m.fecha_salida IS NULL "
        "ORDER BY m.fecha_ingreso LIMIT 1",
        (id_espacio,),
    )
    return cur.fetchone()
