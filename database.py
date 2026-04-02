import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).resolve().parent
else:
    _BASE_DIR = Path(__file__).resolve().parent

DB_PATH = _BASE_DIR / "estacionamiento.db"


def _configurar_conexion(conn):
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error:
        pass
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
    except sqlite3.Error:
        pass
    return conn


def get_connection():
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    return _configurar_conexion(conn)


def validar_integridad_db(conn=None):
    own_conn = conn is None
    try:
        conn = conn or get_connection()
        cur = conn.cursor()
        return [tuple(row) for row in cur.execute("PRAGMA foreign_key_check").fetchall()]
    except sqlite3.Error:
        return []
    finally:
        if own_conn and conn:
            conn.close()


def reparar_integridad_db(conn=None):
    own_conn = conn is None
    reparaciones = {}
    try:
        conn = conn or get_connection()
        cur = conn.cursor()
        operaciones = [
            (
                "vehiculos_sin_cliente",
                "UPDATE vehiculos "
                "SET id_cliente = NULL "
                "WHERE id_cliente IS NOT NULL "
                "AND NOT EXISTS ("
                "SELECT 1 FROM clientes c WHERE c.id_cliente = vehiculos.id_cliente"
                ")",
            ),
            (
                "contratos_vehiculo_invalido",
                "UPDATE cochera_contratos "
                "SET id_vehiculo = NULL "
                "WHERE id_vehiculo IS NOT NULL "
                "AND NOT EXISTS ("
                "SELECT 1 FROM vehiculos v "
                "WHERE v.id_vehiculo = cochera_contratos.id_vehiculo "
                "AND v.id_cliente = cochera_contratos.id_cliente"
                ")",
            ),
            (
                "contratos_sin_vehiculo",
                "UPDATE cochera_contratos "
                "SET id_vehiculo = ("
                "SELECT v.id_vehiculo FROM vehiculos v "
                "WHERE v.id_cliente = cochera_contratos.id_cliente "
                "ORDER BY v.patente LIMIT 1"
                ") "
                "WHERE id_vehiculo IS NULL",
            ),
            (
                "espacios_sin_cliente",
                "UPDATE espacios "
                "SET id_cliente = NULL "
                "WHERE id_cliente IS NOT NULL "
                "AND NOT EXISTS ("
                "SELECT 1 FROM clientes c WHERE c.id_cliente = espacios.id_cliente"
                ")",
            ),
            (
                "pagos_sin_movimiento",
                "DELETE FROM pagos "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM movimientos m WHERE m.id_movimiento = pagos.id_movimiento"
                ")",
            ),
            (
                "pagos_cochera_sin_contrato",
                "DELETE FROM pagos_cochera "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM cochera_contratos cc "
                "WHERE cc.id_contrato = pagos_cochera.id_contrato"
                ")",
            ),
            (
                "pagos_movimientos_invalidos",
                "DELETE FROM pagos "
                "WHERE id_movimiento IN ("
                "SELECT m.id_movimiento "
                "FROM movimientos m "
                "LEFT JOIN vehiculos v ON v.id_vehiculo = m.id_vehiculo "
                "LEFT JOIN espacios e ON e.id_espacio = m.id_espacio "
                "WHERE v.id_vehiculo IS NULL OR e.id_espacio IS NULL"
                ")",
            ),
            (
                "movimientos_invalidos",
                "DELETE FROM movimientos "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM vehiculos v WHERE v.id_vehiculo = movimientos.id_vehiculo"
                ") "
                "OR NOT EXISTS ("
                "SELECT 1 FROM espacios e WHERE e.id_espacio = movimientos.id_espacio"
                ")",
            ),
            (
                "movimientos_tarifa_invalida",
                "UPDATE movimientos "
                "SET id_tarifa_aplicada = NULL "
                "WHERE id_tarifa_aplicada IS NOT NULL "
                "AND NOT EXISTS ("
                "SELECT 1 FROM tarifas t "
                "WHERE t.id_tarifa = movimientos.id_tarifa_aplicada"
                ")",
            ),
            (
                "pagos_contratos_invalidos",
                "DELETE FROM pagos_cochera "
                "WHERE id_contrato IN ("
                "SELECT cc.id_contrato "
                "FROM cochera_contratos cc "
                "LEFT JOIN clientes c ON c.id_cliente = cc.id_cliente "
                "LEFT JOIN espacios e ON e.id_espacio = cc.id_espacio "
                "WHERE c.id_cliente IS NULL OR e.id_espacio IS NULL"
                ")",
            ),
            (
                "contratos_invalidos",
                "DELETE FROM cochera_contratos "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM clientes c WHERE c.id_cliente = cochera_contratos.id_cliente"
                ") "
                "OR NOT EXISTS ("
                "SELECT 1 FROM espacios e WHERE e.id_espacio = cochera_contratos.id_espacio"
                ")",
            ),
            (
                "espacios_mapa_invalidos",
                "DELETE FROM espacios_mapa "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM espacios e WHERE e.codigo = espacios_mapa.codigo"
                ")",
            ),
            (
                "pagos_sin_movimiento_post",
                "DELETE FROM pagos "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM movimientos m WHERE m.id_movimiento = pagos.id_movimiento"
                ")",
            ),
            (
                "pagos_cochera_sin_contrato_post",
                "DELETE FROM pagos_cochera "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM cochera_contratos cc "
                "WHERE cc.id_contrato = pagos_cochera.id_contrato"
                ")",
            ),
        ]
        for clave, sql in operaciones:
            cur.execute(sql)
            reparaciones[clave] = max(0, int(cur.rowcount or 0))
        conn.commit()
        reparaciones["violaciones_restantes"] = len(validar_integridad_db(conn))
        return reparaciones
    except sqlite3.Error:
        if conn:
            conn.rollback()
        reparaciones["violaciones_restantes"] = -1
        return reparaciones
    finally:
        if own_conn and conn:
            conn.close()


def _migrar_fechas_pagos_cochera_utc_a_local(cursor):
    try:
        cursor.execute(
            "SELECT valor FROM configuracion "
            "WHERE clave = 'migracion_pagos_cochera_local_v1'"
        )
        row = cursor.fetchone()
        if row and str(row["valor"] or "").strip() == "1":
            return
        offset = datetime.now().astimezone().utcoffset()
        offset_min = int((offset.total_seconds() // 60) if offset else 0)
        if offset_min:
            cursor.execute(
                "UPDATE pagos_cochera "
                "SET fecha_pago = datetime(fecha_pago, ?) "
                "WHERE fecha_pago IS NOT NULL AND TRIM(fecha_pago) <> ''",
                (f"{offset_min:+d} minutes",),
            )
        cursor.execute(
            "INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            ("migracion_pagos_cochera_local_v1", "1"),
        )
    except sqlite3.Error:
        pass


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        rol TEXT NOT NULL CHECK (rol IN ('DUENO', 'OPERADOR')),
        activo INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS clientes (
        id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
        dni TEXT NOT NULL UNIQUE,
        nombre TEXT NOT NULL,
        direccion TEXT,
        telefono TEXT,
        fecha_nacimiento DATE,
        activo INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS vehiculos (
        id_vehiculo INTEGER PRIMARY KEY AUTOINCREMENT,
        patente TEXT NOT NULL UNIQUE,
        modelo TEXT,
        tipo_vehiculo TEXT DEFAULT 'AUTO',
        id_cliente INTEGER,
        FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
    );

    CREATE TABLE IF NOT EXISTS espacios (
        id_espacio INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL UNIQUE,
        es_reservado INTEGER DEFAULT 0,
        id_cliente INTEGER,
        activo INTEGER DEFAULT 1,
        FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
    );

    CREATE TABLE IF NOT EXISTS cochera_contratos (
        id_contrato INTEGER PRIMARY KEY AUTOINCREMENT,
        id_cliente INTEGER NOT NULL,
        id_vehiculo INTEGER,
        id_espacio INTEGER NOT NULL,
        fecha_inicio DATE DEFAULT CURRENT_DATE,
        fecha_vencimiento DATE NOT NULL,
        monto_mensual REAL NOT NULL,
        activo INTEGER DEFAULT 1,
        en_historial INTEGER DEFAULT 0,
        FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente),
        FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo),
        FOREIGN KEY (id_espacio) REFERENCES espacios(id_espacio)
    );

    CREATE TABLE IF NOT EXISTS espacios_mapa (
        codigo TEXT PRIMARY KEY,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        w INTEGER NOT NULL,
        h INTEGER NOT NULL,
        FOREIGN KEY (codigo) REFERENCES espacios(codigo)
    );

    CREATE TABLE IF NOT EXISTS movimientos (
        id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
        id_vehiculo INTEGER NOT NULL,
        id_espacio INTEGER NOT NULL,
        fecha_ingreso DATETIME DEFAULT CURRENT_TIMESTAMP,
        tipo_vehiculo TEXT DEFAULT 'AUTO',
        id_tarifa_aplicada INTEGER,
        tarifa_hora_aplicada REAL,
        fecha_salida DATETIME,
        total REAL,
        FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo),
        FOREIGN KEY (id_espacio) REFERENCES espacios(id_espacio),
        FOREIGN KEY (id_tarifa_aplicada) REFERENCES tarifas(id_tarifa)
    );

    CREATE TABLE IF NOT EXISTS pagos (
        id_pago INTEGER PRIMARY KEY AUTOINCREMENT,
        id_movimiento INTEGER NOT NULL,
        monto REAL NOT NULL,
        metodo TEXT NOT NULL,
        ref_externa TEXT,
        usuario TEXT,
        fecha_pago DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (id_movimiento) REFERENCES movimientos(id_movimiento)
    );

    CREATE TABLE IF NOT EXISTS pagos_cochera (
        id_pago INTEGER PRIMARY KEY AUTOINCREMENT,
        id_contrato INTEGER NOT NULL,
        monto REAL NOT NULL,
        metodo TEXT NOT NULL,
        ref_externa TEXT,
        usuario TEXT,
        fecha_pago DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (id_contrato) REFERENCES cochera_contratos(id_contrato)
    );

    CREATE TABLE IF NOT EXISTS tarifas (
        id_tarifa INTEGER PRIMARY KEY AUTOINCREMENT,
        precio_hora REAL NOT NULL,
        precio_hora_auto REAL,
        precio_hora_moto REAL,
        precio_hora_camioneta REAL,
        precio_mensual REAL DEFAULT 0,
        precio_mensual_auto REAL,
        precio_mensual_camioneta REAL,
        activa INTEGER DEFAULT 1,
        fecha_desde DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY,
        valor TEXT
    );

    CREATE TABLE IF NOT EXISTS auditoria (
        id_evento INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        usuario TEXT,
        accion TEXT NOT NULL,
        detalle TEXT
    );

    CREATE TABLE IF NOT EXISTS cierres_caja (
        fecha TEXT PRIMARY KEY,
        total_esperado REAL NOT NULL,
        total_contado REAL NOT NULL,
        diferencia REAL NOT NULL,
        observacion TEXT,
        usuario TEXT,
        fecha_cierre DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS cierres_caja_metodos (
        fecha TEXT NOT NULL,
        metodo TEXT NOT NULL,
        total_esperado REAL NOT NULL,
        total_contado REAL NOT NULL,
        diferencia REAL NOT NULL,
        PRIMARY KEY (fecha, metodo)
    );

    CREATE INDEX IF NOT EXISTS idx_vehiculos_cliente
        ON vehiculos (id_cliente);

    CREATE INDEX IF NOT EXISTS idx_espacios_estado
        ON espacios (activo, es_reservado, id_cliente);

    CREATE INDEX IF NOT EXISTS idx_contratos_cliente_activo
        ON cochera_contratos (id_cliente, activo);
    CREATE INDEX IF NOT EXISTS idx_contratos_espacio_activo
        ON cochera_contratos (id_espacio, activo);
    CREATE INDEX IF NOT EXISTS idx_contratos_vencimiento_activo
        ON cochera_contratos (activo, fecha_vencimiento);

    CREATE INDEX IF NOT EXISTS idx_movimientos_vehiculo_salida
        ON movimientos (id_vehiculo, fecha_salida);
    CREATE INDEX IF NOT EXISTS idx_movimientos_espacio_salida
        ON movimientos (id_espacio, fecha_salida);
    CREATE INDEX IF NOT EXISTS idx_movimientos_ingreso
        ON movimientos (fecha_ingreso);

    CREATE INDEX IF NOT EXISTS idx_pagos_movimiento
        ON pagos (id_movimiento);
    CREATE INDEX IF NOT EXISTS idx_pagos_fecha
        ON pagos (fecha_pago);
    CREATE INDEX IF NOT EXISTS idx_pagos_metodo_fecha
        ON pagos (metodo, fecha_pago);
    CREATE INDEX IF NOT EXISTS idx_pagos_mes
        ON pagos (strftime('%Y-%m', fecha_pago));
    CREATE INDEX IF NOT EXISTS idx_pagos_dia
        ON pagos (date(fecha_pago));

    CREATE INDEX IF NOT EXISTS idx_pagos_cochera_contrato
        ON pagos_cochera (id_contrato);
    CREATE INDEX IF NOT EXISTS idx_pagos_cochera_fecha
        ON pagos_cochera (fecha_pago);
    CREATE INDEX IF NOT EXISTS idx_pagos_cochera_metodo_fecha
        ON pagos_cochera (metodo, fecha_pago);
    CREATE INDEX IF NOT EXISTS idx_pagos_cochera_mes
        ON pagos_cochera (strftime('%Y-%m', fecha_pago));
    CREATE INDEX IF NOT EXISTS idx_pagos_cochera_dia
        ON pagos_cochera (date(fecha_pago));

    CREATE INDEX IF NOT EXISTS idx_auditoria_fecha
        ON auditoria (fecha);

    CREATE INDEX IF NOT EXISTS idx_cierres_caja_fecha
        ON cierres_caja (fecha);

    CREATE INDEX IF NOT EXISTS idx_cierres_caja_metodos_fecha
        ON cierres_caja_metodos (fecha);

    CREATE TRIGGER IF NOT EXISTS trg_contrato_activo_vehiculo_insert
    BEFORE INSERT ON cochera_contratos
    WHEN NEW.activo = 1 AND NEW.id_vehiculo IS NOT NULL
    BEGIN
        SELECT RAISE(ABORT, 'vehiculo_ya_tiene_contrato_activo')
        WHERE EXISTS (
            SELECT 1
            FROM cochera_contratos cc
            WHERE cc.id_vehiculo = NEW.id_vehiculo
              AND cc.activo = 1
        );
    END;

    CREATE TRIGGER IF NOT EXISTS trg_contrato_activo_vehiculo_update
    BEFORE UPDATE ON cochera_contratos
    WHEN NEW.activo = 1 AND NEW.id_vehiculo IS NOT NULL
    BEGIN
        SELECT RAISE(ABORT, 'vehiculo_ya_tiene_contrato_activo')
        WHERE EXISTS (
            SELECT 1
            FROM cochera_contratos cc
            WHERE cc.id_vehiculo = NEW.id_vehiculo
              AND cc.activo = 1
              AND cc.id_contrato <> NEW.id_contrato
        );
    END;

    CREATE TRIGGER IF NOT EXISTS trg_contrato_activo_espacio_insert
    BEFORE INSERT ON cochera_contratos
    WHEN NEW.activo = 1
    BEGIN
        SELECT RAISE(ABORT, 'espacio_ya_tiene_contrato_activo')
        WHERE EXISTS (
            SELECT 1
            FROM cochera_contratos cc
            WHERE cc.id_espacio = NEW.id_espacio
              AND cc.activo = 1
        );
    END;

    CREATE TRIGGER IF NOT EXISTS trg_contrato_activo_espacio_update
    BEFORE UPDATE ON cochera_contratos
    WHEN NEW.activo = 1
    BEGIN
        SELECT RAISE(ABORT, 'espacio_ya_tiene_contrato_activo')
        WHERE EXISTS (
            SELECT 1
            FROM cochera_contratos cc
            WHERE cc.id_espacio = NEW.id_espacio
              AND cc.activo = 1
              AND cc.id_contrato <> NEW.id_contrato
        );
    END;

    CREATE TRIGGER IF NOT EXISTS trg_movimiento_activo_vehiculo_insert
    BEFORE INSERT ON movimientos
    WHEN NEW.fecha_salida IS NULL
    BEGIN
        SELECT RAISE(ABORT, 'vehiculo_ya_tiene_movimiento_activo')
        WHERE EXISTS (
            SELECT 1
            FROM movimientos m
            WHERE m.id_vehiculo = NEW.id_vehiculo
              AND m.fecha_salida IS NULL
        );
    END;

    CREATE TRIGGER IF NOT EXISTS trg_movimiento_activo_vehiculo_update
    BEFORE UPDATE ON movimientos
    WHEN NEW.fecha_salida IS NULL
    BEGIN
        SELECT RAISE(ABORT, 'vehiculo_ya_tiene_movimiento_activo')
        WHERE EXISTS (
            SELECT 1
            FROM movimientos m
            WHERE m.id_vehiculo = NEW.id_vehiculo
              AND m.fecha_salida IS NULL
              AND m.id_movimiento <> NEW.id_movimiento
        );
    END;
    """)

    try:
        cursor.execute("ALTER TABLE tarifas ADD COLUMN precio_mensual REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE vehiculos ADD COLUMN tipo_vehiculo TEXT DEFAULT 'AUTO'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "UPDATE vehiculos "
            "SET tipo_vehiculo = CASE "
            "WHEN UPPER(TRIM(COALESCE(tipo_vehiculo, ''))) IN ('MOTO', 'MOTOCICLETA') THEN 'MOTO' "
            "WHEN UPPER(TRIM(COALESCE(tipo_vehiculo, ''))) IN ('CAMIONETA', 'PICKUP') THEN 'CAMIONETA' "
            "ELSE 'AUTO' END"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_vehiculos_tipo "
            "ON vehiculos (tipo_vehiculo)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "ALTER TABLE cochera_contratos "
            "ADD COLUMN id_vehiculo INTEGER REFERENCES vehiculos(id_vehiculo)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "UPDATE cochera_contratos "
            "SET id_vehiculo = ("
            "SELECT v.id_vehiculo FROM vehiculos v "
            "WHERE v.id_cliente = cochera_contratos.id_cliente "
            "ORDER BY v.patente LIMIT 1"
            ") "
            "WHERE id_vehiculo IS NULL"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "ALTER TABLE cochera_contratos "
            "ADD COLUMN en_historial INTEGER DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "UPDATE cochera_contratos "
            "SET en_historial = COALESCE(en_historial, 0)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_contratos_vehiculo_activo "
            "ON cochera_contratos (id_vehiculo, activo)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_contratos_historial "
            "ON cochera_contratos (en_historial, activo)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE tarifas ADD COLUMN precio_hora_auto REAL")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE tarifas ADD COLUMN precio_hora_moto REAL")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE tarifas ADD COLUMN precio_hora_camioneta REAL")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE tarifas ADD COLUMN precio_mensual_auto REAL")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE tarifas ADD COLUMN precio_mensual_camioneta REAL")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "UPDATE tarifas SET "
            "precio_hora_auto = COALESCE(precio_hora_auto, precio_hora), "
            "precio_hora_moto = COALESCE(precio_hora_moto, precio_hora), "
            "precio_hora_camioneta = COALESCE(precio_hora_camioneta, precio_hora), "
            "precio_mensual_auto = COALESCE(precio_mensual_auto, precio_mensual), "
            "precio_mensual_camioneta = COALESCE(precio_mensual_camioneta, precio_mensual)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE movimientos ADD COLUMN tipo_vehiculo TEXT DEFAULT 'AUTO'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "ALTER TABLE movimientos "
            "ADD COLUMN id_tarifa_aplicada INTEGER REFERENCES tarifas(id_tarifa)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE movimientos ADD COLUMN tarifa_hora_aplicada REAL")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "UPDATE movimientos "
            "SET tipo_vehiculo = COALESCE(NULLIF(TRIM(tipo_vehiculo), ''), 'AUTO')"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_movimientos_tarifa "
            "ON movimientos (id_tarifa_aplicada)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "SELECT id_tarifa, precio_hora, precio_hora_auto, precio_hora_moto, precio_hora_camioneta "
            "FROM tarifas WHERE activa = 1 ORDER BY fecha_desde DESC LIMIT 1"
        )
        tarifa_activa = cursor.fetchone()
        if tarifa_activa:
            tarifa_id = int(tarifa_activa["id_tarifa"])
            cursor.execute(
                "UPDATE movimientos "
                "SET id_tarifa_aplicada = COALESCE(id_tarifa_aplicada, ?), "
                "tarifa_hora_aplicada = COALESCE("
                "tarifa_hora_aplicada, "
                "CASE "
                "WHEN UPPER(TRIM(COALESCE(tipo_vehiculo, 'AUTO'))) = 'MOTO' "
                "THEN COALESCE(?, ?, 0) "
                "WHEN UPPER(TRIM(COALESCE(tipo_vehiculo, 'AUTO'))) = 'CAMIONETA' "
                "THEN COALESCE(?, ?, 0) "
                "ELSE COALESCE(?, ?, 0) "
                "END"
                ") "
                "WHERE fecha_salida IS NULL "
                "AND (id_tarifa_aplicada IS NULL OR tarifa_hora_aplicada IS NULL)",
                (
                    tarifa_id,
                    tarifa_activa["precio_hora_moto"],
                    tarifa_activa["precio_hora"],
                    tarifa_activa["precio_hora_camioneta"],
                    tarifa_activa["precio_hora"],
                    tarifa_activa["precio_hora_auto"],
                    tarifa_activa["precio_hora"],
                ),
            )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE vehiculos ADD COLUMN modelo TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("DROP TRIGGER IF EXISTS trg_contrato_activo_cliente_insert")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("DROP TRIGGER IF EXISTS trg_contrato_activo_cliente_update")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE pagos ADD COLUMN ref_externa TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE pagos ADD COLUMN usuario TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE pagos_cochera ADD COLUMN ref_externa TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE pagos_cochera ADD COLUMN usuario TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pagos_ref_externa "
            "ON pagos (ref_externa)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pagos_usuario_fecha "
            "ON pagos (usuario, fecha_pago)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pagos_cochera_ref_externa "
            "ON pagos_cochera (ref_externa)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pagos_cochera_usuario_fecha "
            "ON pagos_cochera (usuario, fecha_pago)"
        )
    except sqlite3.OperationalError:
        pass
    _migrar_fechas_pagos_cochera_utc_a_local(cursor)

    reparar_integridad_db(conn=conn)
    try:
        cursor.execute("PRAGMA optimize")
    except sqlite3.Error:
        pass

    conn.commit()
    conn.close()


def reset_db():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = OFF")
        tablas = [
            "pagos",
            "movimientos",
            "pagos_cochera",
            "cochera_contratos",
            "espacios_mapa",
            "espacios",
            "vehiculos",
            "clientes",
            "tarifas",
            "configuracion",
            "auditoria",
            "cierres_caja_metodos",
            "cierres_caja",
            "usuarios",
        ]
        for tabla in tablas:
            cursor.execute(f"DELETE FROM {tabla}")

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        )
        if cursor.fetchone():
            cursor.execute("DELETE FROM sqlite_sequence")
        conn.commit()
    finally:
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error:
            pass
        conn.close()

