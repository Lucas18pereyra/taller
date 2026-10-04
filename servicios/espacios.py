"""Operaciones del mapa, atomicas y sin borrar historial comercial."""
import math

from database import get_connection


def motivos_bloqueo(cur, codigo):
    row = cur.execute("SELECT id_espacio, id_cliente FROM espacios WHERE codigo = ?", (codigo,)).fetchone()
    if row is None:
        return []
    motivos = []
    if row["id_cliente"] is not None:
        motivos.append("tiene un cliente asignado")
    if cur.execute("SELECT 1 FROM cochera_contratos WHERE id_espacio = ? AND (activo = 1 OR COALESCE(en_historial, 0) = 0) LIMIT 1", (row["id_espacio"],)).fetchone():
        motivos.append("tiene un contrato activo o pendiente")
    if cur.execute("SELECT 1 FROM movimientos WHERE id_espacio = ? AND fecha_salida IS NULL LIMIT 1", (row["id_espacio"],)).fetchone():
        motivos.append("tiene una patente con ingreso activo")
    return motivos


def comprobar_eliminacion(codigo, conn=None):
    propia = conn is None
    conn = conn or get_connection()
    try:
        motivos = motivos_bloqueo(conn.cursor(), codigo)
        if motivos:
            raise ValueError(f"No se puede eliminar {codigo}: " + "; ".join(motivos) + ". Libera primero la asignacion desde la pantalla correspondiente.")
    finally:
        if propia:
            conn.close()


def comprobar_tipo(cur, codigo, reservado):
    row = cur.execute("SELECT id_espacio, es_reservado, id_cliente FROM espacios WHERE codigo = ?", (codigo,)).fetchone()
    if row is None or int(row["es_reservado"] or 0) == reservado:
        return
    if reservado:
        ocupado = cur.execute("SELECT 1 FROM movimientos WHERE id_espacio = ? AND fecha_salida IS NULL LIMIT 1", (row["id_espacio"],)).fetchone()
        if ocupado:
            raise ValueError(f"No se puede marcar {codigo} como cochera: tiene un ingreso activo.")
    else:
        contrato = cur.execute("SELECT 1 FROM cochera_contratos WHERE id_espacio = ? AND COALESCE(en_historial, 0) = 0 LIMIT 1", (row["id_espacio"],)).fetchone()
        if contrato or row["id_cliente"] is not None:
            raise ValueError(f"No se puede quitar la marca de cochera a {codigo}: tiene un cliente o contrato fuera del historial.")


def guardar_mapa(items, eliminados):
    """Items con codigo_original mantienen el ID y todos sus vinculos al renombrar."""
    items = [dict(item) for item in items]
    codigos = set()
    originales = set()
    for item in items:
        codigo = str(item.get("codigo") or "").strip().upper()
        if not codigo or codigo in codigos:
            raise ValueError("Cada espacio debe tener un codigo unico y no vacio.")
        item["codigo"] = codigo
        codigos.add(codigo)
        original = item.get("codigo_original")
        if original:
            if original in originales:
                raise ValueError("Un espacio existente aparece mas de una vez en el mapa.")
            originales.add(original)
        for campo in ("x", "y", "w", "h"):
            valor = float(item[campo])
            if not math.isfinite(valor) or (campo in ("w", "h") and valor <= 0):
                raise ValueError("Las dimensiones y posiciones del mapa no son validas.")
            item[campo] = int(valor)
            if campo in ("w", "h") and item[campo] <= 0:
                raise ValueError("Cada espacio debe tener ancho y alto positivos.")
        item["es_reservado"] = 1 if item.get("es_reservado") else 0
    eliminados = set(eliminados)
    if eliminados & (codigos | originales):
        raise ValueError("Un espacio pendiente de eliminacion no puede reutilizarse antes de guardar.")
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("PRAGMA defer_foreign_keys = ON")
        cur = conn.cursor()
        # Revalidar bajo bloqueo, por si la ocupacion cambio con el mapa abierto.
        for codigo in eliminados:
            comprobar_eliminacion(codigo, conn)
        for item in items:
            original, codigo = item.get("codigo_original"), item["codigo"]
            if original:
                row = cur.execute("SELECT id_espacio, activo FROM espacios WHERE codigo = ?", (original,)).fetchone()
                if row is None or not row["activo"]:
                    raise ValueError(f"El espacio {original} cambio en otra ventana. Recarga el mapa.")
            destino = cur.execute("SELECT id_espacio, activo FROM espacios WHERE codigo = ?", (codigo,)).fetchone()
            if original != codigo and destino:
                # Reutilizar un lugar dado de baja conserva su identidad/historial.
                if original or destino["activo"]:
                    raise ValueError(f"El codigo {codigo} ya existe en la base. Elige otro codigo.")
                comprobar_eliminacion(codigo, conn)
            comprobar_tipo(cur, original or codigo, item["es_reservado"])
        for codigo in eliminados:
            cur.execute("DELETE FROM espacios_mapa WHERE codigo = ?", (codigo,))
            cur.execute("UPDATE espacios SET activo = 0 WHERE codigo = ?", (codigo,))
        for item in items:
            original, codigo = item.get("codigo_original"), item["codigo"]
            if original and original != codigo:
                cur.execute("UPDATE espacios SET codigo = ? WHERE codigo = ?", (codigo, original))
                cur.execute("UPDATE espacios_mapa SET codigo = ? WHERE codigo = ?", (codigo, original))
            cur.execute("INSERT INTO espacios (codigo, es_reservado, activo) VALUES (?, ?, 1) ON CONFLICT(codigo) DO UPDATE SET es_reservado = excluded.es_reservado, activo = 1", (codigo, item["es_reservado"]))
            cur.execute("INSERT INTO espacios_mapa (codigo, x, y, w, h) VALUES (?, ?, ?, ?, ?) ON CONFLICT(codigo) DO UPDATE SET x=excluded.x, y=excluded.y, w=excluded.w, h=excluded.h", (codigo, item["x"], item["y"], item["w"], item["h"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
