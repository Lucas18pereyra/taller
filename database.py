import sqlite3
from pathlib import Path

DB_PATH = Path("estacionamiento.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
        id_espacio INTEGER NOT NULL,
        fecha_inicio DATE DEFAULT CURRENT_DATE,
        fecha_vencimiento DATE NOT NULL,
        monto_mensual REAL NOT NULL,
        activo INTEGER DEFAULT 1,
        FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente),
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
        fecha_salida DATETIME,
        total REAL,
        FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo),
        FOREIGN KEY (id_espacio) REFERENCES espacios(id_espacio)
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
        precio_mensual REAL DEFAULT 0,
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

    CREATE TRIGGER IF NOT EXISTS trg_contrato_activo_cliente_insert
    BEFORE INSERT ON cochera_contratos
    WHEN NEW.activo = 1
    BEGIN
        SELECT RAISE(ABORT, 'cliente_ya_tiene_contrato_activo')
        WHERE EXISTS (
            SELECT 1
            FROM cochera_contratos cc
            WHERE cc.id_cliente = NEW.id_cliente
              AND cc.activo = 1
        );
    END;

    CREATE TRIGGER IF NOT EXISTS trg_contrato_activo_cliente_update
    BEFORE UPDATE ON cochera_contratos
    WHEN NEW.activo = 1
    BEGIN
        SELECT RAISE(ABORT, 'cliente_ya_tiene_contrato_activo')
        WHERE EXISTS (
            SELECT 1
            FROM cochera_contratos cc
            WHERE cc.id_cliente = NEW.id_cliente
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
        cursor.execute(
            "UPDATE tarifas SET "
            "precio_hora_auto = COALESCE(precio_hora_auto, precio_hora), "
            "precio_hora_moto = COALESCE(precio_hora_moto, precio_hora), "
            "precio_hora_camioneta = COALESCE(precio_hora_camioneta, precio_hora)"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE movimientos ADD COLUMN tipo_vehiculo TEXT DEFAULT 'AUTO'")
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
        cursor.execute("ALTER TABLE vehiculos ADD COLUMN modelo TEXT")
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

