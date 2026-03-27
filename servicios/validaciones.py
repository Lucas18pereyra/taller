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
