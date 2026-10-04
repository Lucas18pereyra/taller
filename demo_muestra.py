"""Datos ficticios y efímeros para presentar la aplicación en una muestra.

Se debe llamar a ``preparar_demo()`` antes de importar los servicios de la
aplicación y conservar el objeto retornado durante toda la sesión.
"""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


def _fecha_hora(valor):
    return valor.strftime("%Y-%m-%d %H:%M:%S")


def preparar_demo(ahora=None):
    """Crea una base nueva de muestra y devuelve el dueño de su carpeta temporal.

    Cada llamada crea una carpeta distinta. Nunca se abre ni se copia la base
    instalada. ``ahora`` permite verificar el escenario con una fecha fija.
    """
    import database

    if ahora is None:
        # Argentina usa UTC-3; no depende de tzdata instalado en Windows.
        ahora = datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    elif ahora.tzinfo is not None:
        ahora = ahora.astimezone(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    ahora = ahora.replace(microsecond=0)
    hoy = ahora.date()
    temporal = TemporaryDirectory(prefix="estacionamiento_muestra_")
    raiz = Path(temporal.name)
    ruta_anterior = database.DB_PATH
    database.DB_PATH = raiz / "demostracion.db"

    try:
        database.init_db()
        with closing(database.get_connection()) as conn:
            cur = conn.cursor()
            carpetas = {}
            for clave, nombre in (
                ("dir_reportes", "reportes"),
                ("dir_comprobantes", "comprobantes"),
                ("dir_tickets_salida", "tickets_salida"),
            ):
                carpeta = raiz / nombre
                carpeta.mkdir()
                carpetas[clave] = str(carpeta)
            configuracion = {
                "ui_tema": "oscuro",
                "ui_resolucion": "1280x800",
                "empresa_nombre": "Estacionamiento (Demo)",
                "empresa_direccion": "Av. de la Muestra 123 · dirección ficticia",
                "empresa_telefono": "Sin contacto (demo)",
                "modo_demostracion": "1",
                **carpetas,
            }
            cur.executemany(
                "INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                configuracion.items(),
            )
            cur.execute(
                "INSERT INTO usuarios (usuario, password, rol, activo) "
                "VALUES ('demo', 'demo', 'DUENO', 1)"
            )
            cur.execute(
                "INSERT INTO tarifas (precio_hora, precio_hora_auto, "
                "precio_hora_moto, precio_hora_camioneta, precio_mensual, "
                "precio_mensual_auto, precio_mensual_camioneta, activa, fecha_desde) "
                "VALUES (1500, 1500, 1000, 2000, 48000, 48000, 60000, 1, ?)",
                (_fecha_hora(ahora - timedelta(days=90)),),
            )
            tarifa_id = cur.lastrowid
            espacios = {}
            for prefijo, cantidad, reservado, fila_base in (
                ("C", 24, 1, 0),
                ("E", 12, 0, 5),
            ):
                for indice in range(cantidad):
                    codigo = f"{prefijo}{indice + 1:02d}"
                    cur.execute(
                        "INSERT INTO espacios (codigo, es_reservado, activo) "
                        "VALUES (?, ?, 1)",
                        (codigo, reservado),
                    )
                    espacios[codigo] = cur.lastrowid
                    cur.execute(
                        "INSERT INTO espacios_mapa (codigo, x, y, w, h) "
                        "VALUES (?, ?, ?, 120, 70)",
                        (
                            codigo,
                            80 + (indice % 6) * 160,
                            50 + (fila_base + indice // 6) * 100,
                        ),
                    )

            nombres = (
                "Lucía Fernández", "Martín López", "Camila Torres", "Diego Ruiz",
                "Valentina Gómez", "Julián Pérez", "Sofía Martínez", "Nicolás Díaz",
                "Florencia Castro", "Tomás Romero", "Agustina Silva", "Federico Costa",
                "Victoria Molina", "Santiago Álvarez", "Paula Medina", "Andrés Herrera",
            )
            modelos = (
                ("Toyota Corolla", "AUTO"),
                ("Peugeot 208", "AUTO"),
                ("Volkswagen Polo", "AUTO"),
                ("Toyota Hilux", "CAMIONETA"),
            )
            metodos = ("Efectivo", "Transferencia", "Tarjeta")
            comienzo_mes = ahora.replace(day=1, hour=0, minute=0, second=0)

            for indice, nombre in enumerate(nombres):
                numero = indice + 1
                cur.execute(
                    "INSERT INTO clientes (dni, nombre, direccion, telefono, "
                    "fecha_nacimiento, activo) VALUES (?, ?, ?, ?, ?, 1)",
                    (
                        f"DEMO-{numero:04d}",
                        nombre,
                        f"Calle de Ejemplo {100 + numero} (ficticia)",
                        "Sin contacto (demo)",
                        f"{1980 + indice % 15}-06-15",
                    ),
                )
                cliente_id = cur.lastrowid
                modelo, tipo = modelos[indice % len(modelos)]
                cur.execute(
                    "INSERT INTO vehiculos (patente, modelo, tipo_vehiculo, id_cliente) "
                    "VALUES (?, ?, ?, ?)",
                    (f"DM{numero:03d}AA", modelo, tipo, cliente_id),
                )
                vehiculo_id = cur.lastrowid
                codigo = f"C{numero:02d}"
                espacio_id = espacios[codigo]
                dias_vencimiento = (0, 2, 5)[indice] if indice < 3 else 10 + indice % 11
                vencimiento = hoy + timedelta(days=dias_vencimiento)
                mensual = 60000 if tipo == "CAMIONETA" else 48000
                cur.execute(
                    "INSERT INTO cochera_contratos (id_cliente, id_vehiculo, "
                    "id_espacio, fecha_inicio, fecha_vencimiento, monto_mensual, "
                    "activo, en_historial) VALUES (?, ?, ?, ?, ?, ?, 1, 0)",
                    (
                        cliente_id, vehiculo_id, espacio_id,
                        (vencimiento - timedelta(days=30)).isoformat(),
                        vencimiento.isoformat(), mensual,
                    ),
                )
                contrato_id = cur.lastrowid
                cur.execute(
                    "UPDATE espacios SET id_cliente = ? WHERE id_espacio = ?",
                    (cliente_id, espacio_id),
                )
                # Cada contrato tiene un pago; los trece al día se pagaron este
                # mes y los tres próximos a vencer, en el mes anterior.
                if indice < 3:
                    pago = comienzo_mes - timedelta(days=5 + indice)
                else:
                    pago = max(
                        comienzo_mes,
                        ahora - timedelta(days=min(indice // 3, hoy.day - 1), minutes=numero),
                    )
                cur.execute(
                    "INSERT INTO pagos_cochera (id_contrato, monto, metodo, "
                    "ref_externa, usuario, fecha_pago) VALUES (?, ?, ?, ?, 'demo', ?)",
                    (
                        contrato_id, mensual, metodos[indice % 3],
                        f"DEMO-MENSUAL-{numero:03d}", _fecha_hora(pago),
                    ),
                )

            tipos_visitante = ("AUTO", "AUTO", "CAMIONETA", "MOTO", "AUTO", "AUTO")
            precios = {"AUTO": 1500, "MOTO": 1000, "CAMIONETA": 2000}
            for indice, tipo in enumerate(tipos_visitante):
                cur.execute(
                    "INSERT INTO vehiculos (patente, modelo, tipo_vehiculo) VALUES (?, ?, ?)",
                    (f"DM{101 + indice:03d}MO", "Visitante de demostración", tipo),
                )
                vehiculo_id = cur.lastrowid
                ingreso = ahora - timedelta(minutes=(25, 48, 75, 98, 145, 180)[indice])
                cur.execute(
                    "INSERT INTO movimientos (id_vehiculo, id_espacio, fecha_ingreso, "
                    "tipo_vehiculo, id_tarifa_aplicada, tarifa_hora_aplicada) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        vehiculo_id, espacios[f"E{indice + 1:02d}"],
                        _fecha_hora(ingreso), tipo, tarifa_id, precios[tipo],
                    ),
                )

            # Salidas ya cobradas para llenar historial, caja y reportes.
            # Vehículos y franjas separados de las visitas actualmente activas.
            for indice in range(24):
                tipo = tipos_visitante[indice % len(tipos_visitante)]
                cur.execute(
                    "INSERT INTO vehiculos (patente, modelo, tipo_vehiculo) VALUES (?, ?, ?)",
                    (f"DM{201 + indice:03d}MO", "Visita de ejemplo", tipo),
                )
                vehiculo_id = cur.lastrowid
                if indice < 4:
                    salida = max(
                        ahora.replace(hour=0, minute=0, second=0),
                        ahora - timedelta(minutes=12 + indice * 17),
                    )
                else:
                    salida = ahora - timedelta(days=1 + (indice - 4) // 2, hours=indice % 3)
                horas = 1 + indice % 4
                ingreso = salida - timedelta(hours=horas)
                monto = float(horas * precios[tipo])
                cur.execute(
                    "INSERT INTO movimientos (id_vehiculo, id_espacio, fecha_ingreso, "
                    "tipo_vehiculo, id_tarifa_aplicada, tarifa_hora_aplicada, "
                    "fecha_salida, total) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        vehiculo_id, espacios[f"E{7 + indice % 6:02d}"],
                        _fecha_hora(ingreso), tipo, tarifa_id, precios[tipo],
                        _fecha_hora(salida), monto,
                    ),
                )
                movimiento_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO pagos (id_movimiento, monto, metodo, ref_externa, "
                    "usuario, fecha_pago) VALUES (?, ?, ?, ?, 'demo', ?)",
                    (
                        movimiento_id, monto, metodos[indice % 3],
                        f"DEMO-VISITA-{indice + 1:03d}", _fecha_hora(salida),
                    ),
                )
            conn.commit()
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("La base de demostración no pasó la verificación de integridad.")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Hay referencias inválidas en la base de demostración.")
        return temporal
    except BaseException:
        database.DB_PATH = ruta_anterior
        temporal.cleanup()
        raise
