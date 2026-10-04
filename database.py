import sqlite3
import sys
import os
from datetime import datetime
from pathlib import Path

if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).resolve().parent
else:
    _BASE_DIR = Path(__file__).resolve().parent

# Portable by default; an explicit data directory keeps launchers/tests isolated.
_DATA_DIR = os.environ.get("ESTACIONAMIENTO_DATA_DIR", "").strip()
DB_PATH = (Path(_DATA_DIR).expanduser().resolve() if _DATA_DIR else _BASE_DIR) / "estacionamiento.db"
SCHEMA_VERSION = 2
APPLICATION_ID = 0x45535441  # ESTA: identifica esta base, no un SQLite cualquiera.


class DatabaseIntegrityError(sqlite3.IntegrityError):
    """Conflictos existentes que requieren revisión sin eliminar datos."""

    def __init__(self, conflictos):
        self.conflictos = conflictos
        detalle = "; ".join(f"{clave}: {len(filas)} caso(s)" for clave, filas in conflictos.items())
        super().__init__(
            "La base presenta conflictos de integridad. Los datos se conservaron. "
            "Revise el respaldo y los registros afectados antes de continuar. " + detalle
        )


def _columnas_tabla(conn, tabla):
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{tabla}")')}


def diagnosticar_integridad_db(conn=None):
    """Describe conflictos con IDs, sin leer credenciales ni modificar registros."""
    own_conn = conn is None
    conn = conn or get_connection()
    try:
        conflictos = {}
        integridad = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        if integridad != ["ok"]:
            conflictos["integridad_sqlite"] = integridad
        referencias = validar_integridad_db(conn)
        if referencias:
            conflictos["referencias_invalidas"] = referencias
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        app_id = conn.execute("PRAGMA application_id").fetchone()[0]
        tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if app_id not in (0, APPLICATION_ID):
            conflictos["base_de_otra_aplicacion"] = [(app_id,)]
        if tablas and not {"clientes", "vehiculos", "espacios", "movimientos"}.issubset(tablas):
            conflictos["esquema_no_reconocido"] = [tuple(sorted(tablas))]
        elif tablas:
            for tabla, campos in {"clientes": {"id_cliente", "dni", "nombre"},
                                  "vehiculos": {"id_vehiculo", "patente"},
                                  "espacios": {"id_espacio", "codigo"},
                                  "movimientos": {"id_movimiento", "id_vehiculo", "id_espacio", "fecha_ingreso", "fecha_salida"}}.items():
                if not campos.issubset(_columnas_tabla(conn, tabla)):
                    conflictos.setdefault("columnas_de_esquema_no_reconocidas", []).append((tabla,))
        if version > SCHEMA_VERSION:
            conflictos["version_de_esquema_mas_nueva"] = [(version, SCHEMA_VERSION)]
        columnas = {tabla: _columnas_tabla(conn, tabla) for tabla in (
            "espacios", "cochera_contratos", "movimientos", "vehiculos")}

        def consultar(clave, sql, requeridas):
            if all(set(nombres).issubset(columnas[tabla]) for tabla, nombres in requeridas.items()):
                filas = [tuple(row) for row in conn.execute(sql)]
                if filas:
                    conflictos[clave] = filas

        consultar("contratos_activos_por_espacio",
                  "SELECT id_espacio, COUNT(*) FROM cochera_contratos WHERE activo=1 "
                  "GROUP BY id_espacio HAVING COUNT(*)>1",
                  {"cochera_contratos": ("id_espacio", "activo")})
        consultar("contratos_activos_por_vehiculo",
                  "SELECT id_vehiculo, COUNT(*) FROM cochera_contratos WHERE activo=1 "
                  "AND id_vehiculo IS NOT NULL GROUP BY id_vehiculo HAVING COUNT(*)>1",
                  {"cochera_contratos": ("id_vehiculo", "activo")})
        consultar("movimientos_abiertos_por_espacio",
                  "SELECT id_espacio, COUNT(*) FROM movimientos WHERE fecha_salida IS NULL "
                  "GROUP BY id_espacio HAVING COUNT(*)>1",
                  {"movimientos": ("id_espacio", "fecha_salida")})
        consultar("movimientos_abiertos_por_vehiculo",
                  "SELECT id_vehiculo, COUNT(*) FROM movimientos WHERE fecha_salida IS NULL "
                  "GROUP BY id_vehiculo HAVING COUNT(*)>1",
                  {"movimientos": ("id_vehiculo", "fecha_salida")})
        consultar("espacios_con_contrato_y_estadia",
                  "SELECT cc.id_contrato,m.id_movimiento,cc.id_espacio FROM cochera_contratos cc "
                  "JOIN movimientos m ON m.id_espacio=cc.id_espacio "
                  "WHERE cc.activo=1 AND m.fecha_salida IS NULL",
                  {"cochera_contratos": ("id_contrato", "id_espacio", "activo"),
                   "movimientos": ("id_movimiento", "id_espacio", "fecha_salida")})
        consultar("vehiculos_con_contrato_y_estadia",
                  "SELECT cc.id_contrato,m.id_movimiento,cc.id_vehiculo FROM cochera_contratos cc "
                  "JOIN movimientos m ON m.id_vehiculo=cc.id_vehiculo "
                  "WHERE cc.activo=1 AND m.fecha_salida IS NULL",
                  {"cochera_contratos": ("id_contrato", "id_vehiculo", "activo"),
                   "movimientos": ("id_movimiento", "id_vehiculo", "fecha_salida")})
        consultar("espacios_inactivos_con_cliente",
                  "SELECT id_espacio FROM espacios WHERE COALESCE(activo,0)<>1 AND id_cliente IS NOT NULL",
                  {"espacios": ("id_espacio", "activo", "id_cliente")})
        consultar("contratos_activos_o_pendientes_sin_cochera_disponible",
                  "SELECT cc.id_contrato,cc.id_espacio FROM cochera_contratos cc "
                  "JOIN espacios e ON e.id_espacio=cc.id_espacio "
                  "WHERE (cc.activo=1 OR COALESCE(cc.en_historial,0)=0) "
                  "AND (COALESCE(e.activo,0)<>1 OR COALESCE(e.es_reservado,0)<>1)",
                  {"cochera_contratos": ("id_contrato", "id_espacio", "activo", "en_historial"),
                   "espacios": ("id_espacio", "activo", "es_reservado")})
        consultar("movimientos_abiertos_sin_espacio_disponible",
                  "SELECT m.id_movimiento,m.id_espacio FROM movimientos m "
                  "JOIN espacios e ON e.id_espacio=m.id_espacio "
                  "WHERE m.fecha_salida IS NULL AND (COALESCE(e.activo,0)<>1 "
                  "OR COALESCE(e.es_reservado,0)<>0 OR e.id_cliente IS NOT NULL)",
                  {"movimientos": ("id_movimiento", "id_espacio", "fecha_salida"),
                   "espacios": ("id_espacio", "activo", "es_reservado", "id_cliente")})
        return conflictos
    except DatabaseIntegrityError:
        raise
    except sqlite3.Error as exc:
        raise DatabaseIntegrityError({"error_al_validar_la_base": [(str(exc),)]}) from exc
    finally:
        if own_conn:
            conn.close()


def _comprobar_integridad_db(conn):
    conflictos = diagnosticar_integridad_db(conn)
    if conflictos:
        raise DatabaseIntegrityError(conflictos)


def _migrar_columnas_no_destructivo(cursor):
    """Agrega estructura; no infiere vehículos, borra filas ni cambia fechas."""
    columnas = {
        "vehiculos": {"tipo_vehiculo": "TEXT DEFAULT 'AUTO'", "modelo": "TEXT"},
        "cochera_contratos": {"id_vehiculo": "INTEGER REFERENCES vehiculos(id_vehiculo)",
                               "en_historial": "INTEGER DEFAULT 0"},
        "tarifas": {"precio_mensual": "REAL DEFAULT 0", "precio_hora_auto": "REAL",
                    "precio_hora_moto": "REAL", "precio_hora_camioneta": "REAL",
                    "precio_mensual_auto": "REAL", "precio_mensual_camioneta": "REAL"},
        "movimientos": {"tipo_vehiculo": "TEXT DEFAULT 'AUTO'",
                        "id_tarifa_aplicada": "INTEGER REFERENCES tarifas(id_tarifa)",
                        "tarifa_hora_aplicada": "REAL"},
        "pagos": {"ref_externa": "TEXT", "usuario": "TEXT"},
        "pagos_cochera": {"ref_externa": "TEXT", "usuario": "TEXT"},
    }
    for tabla, nuevas in columnas.items():
        presentes = _columnas_tabla(cursor.connection, tabla)
        for nombre, declaracion in nuevas.items():
            if nombre not in presentes:
                cursor.execute(f'ALTER TABLE "{tabla}" ADD COLUMN "{nombre}" {declaracion}')
    for nombre, tabla, campos in (
        ("idx_vehiculos_tipo", "vehiculos", "tipo_vehiculo"),
        ("idx_contratos_vehiculo_activo", "cochera_contratos", "id_vehiculo, activo"),
        ("idx_contratos_historial", "cochera_contratos", "en_historial, activo"),
        ("idx_movimientos_tarifa", "movimientos", "id_tarifa_aplicada"),
        ("idx_pagos_ref_externa", "pagos", "ref_externa"),
        ("idx_pagos_usuario_fecha", "pagos", "usuario, fecha_pago"),
        ("idx_pagos_cochera_ref_externa", "pagos_cochera", "ref_externa"),
        ("idx_pagos_cochera_usuario_fecha", "pagos_cochera", "usuario, fecha_pago"),
    ):
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {nombre} ON {tabla} ({campos})")
    cursor.execute("DROP TRIGGER IF EXISTS trg_contrato_activo_cliente_insert")
    cursor.execute("DROP TRIGGER IF EXISTS trg_contrato_activo_cliente_update")


def _instalar_guardias_integridad(cursor):
    # SQL dentro de la transacción de init_db; execute no hace commits implícitos.
    def proteger_lugar(nombre, evento, tabla, condicion, lookup):
        cursor.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {nombre}
            BEFORE {evento} ON {tabla} {condicion}
            BEGIN
                SELECT RAISE(ABORT,'espacio_tiene_cliente_asignado')
                WHERE EXISTS (SELECT 1 FROM espacios e WHERE {lookup} AND e.id_cliente IS NOT NULL);
                SELECT RAISE(ABORT,'espacio_tiene_contrato_activo')
                WHERE EXISTS (SELECT 1 FROM cochera_contratos cc JOIN espacios e ON e.id_espacio=cc.id_espacio
                              WHERE {lookup} AND cc.activo=1);
                SELECT RAISE(ABORT,'espacio_tiene_contrato_pendiente')
                WHERE EXISTS (SELECT 1 FROM cochera_contratos cc JOIN espacios e ON e.id_espacio=cc.id_espacio
                              WHERE {lookup} AND COALESCE(cc.activo,0)<>1 AND COALESCE(cc.en_historial,0)=0);
                SELECT RAISE(ABORT,'espacio_tiene_movimiento_abierto')
                WHERE EXISTS (SELECT 1 FROM movimientos m JOIN espacios e ON e.id_espacio=m.id_espacio
                              WHERE {lookup} AND m.fecha_salida IS NULL);
            END
        """)

    proteger_lugar("trg_espacio_borrado_protegido_v2", "DELETE", "espacios", "", "e.id_espacio=OLD.id_espacio")
    proteger_lugar("trg_espacio_desactivacion_protegida_v2", "UPDATE OF activo", "espacios",
                   "WHEN COALESCE(NEW.activo,0)<>1", "e.id_espacio=OLD.id_espacio")
    proteger_lugar("trg_mapa_borrado_protegido_v2", "DELETE", "espacios_mapa", "", "e.codigo=OLD.codigo")

    for evento, sufijo, excluir in (("INSERT", "insert", ""),
                                   ("UPDATE", "update", "AND m.id_movimiento<>NEW.id_movimiento")):
        cursor.execute(f"""
            CREATE TRIGGER IF NOT EXISTS trg_movimiento_espacio_integridad_{sufijo}_v2
            BEFORE {evento} ON movimientos WHEN NEW.fecha_salida IS NULL
            BEGIN
                SELECT RAISE(ABORT,'espacio_ya_tiene_movimiento_activo')
                WHERE EXISTS (SELECT 1 FROM movimientos m WHERE m.id_espacio=NEW.id_espacio
                              AND m.fecha_salida IS NULL {excluir});
                SELECT RAISE(ABORT,'espacio_ya_tiene_contrato_activo')
                WHERE EXISTS (SELECT 1 FROM cochera_contratos cc WHERE cc.id_espacio=NEW.id_espacio AND cc.activo=1);
                SELECT RAISE(ABORT,'vehiculo_ya_tiene_contrato_activo')
                WHERE EXISTS (SELECT 1 FROM cochera_contratos cc WHERE cc.id_vehiculo=NEW.id_vehiculo AND cc.activo=1);
                SELECT RAISE(ABORT,'espacio_no_disponible_para_estacionamiento')
                WHERE EXISTS (SELECT 1 FROM espacios e WHERE e.id_espacio=NEW.id_espacio
                              AND (COALESCE(e.activo,0)<>1 OR COALESCE(e.es_reservado,0)<>0 OR e.id_cliente IS NOT NULL));
            END
        """)
    for evento, sufijo in (("INSERT", "insert"), ("UPDATE", "update")):
        cursor.execute(f"""
            CREATE TRIGGER IF NOT EXISTS trg_contrato_espacio_integridad_{sufijo}_v2
            BEFORE {evento} ON cochera_contratos
            WHEN NEW.activo=1 OR COALESCE(NEW.en_historial,0)=0
            BEGIN
                SELECT RAISE(ABORT,'espacio_no_es_cochera')
                WHERE EXISTS (SELECT 1 FROM espacios e WHERE e.id_espacio=NEW.id_espacio
                              AND (COALESCE(e.activo,0)<>1 OR COALESCE(e.es_reservado,0)<>1));
                SELECT RAISE(ABORT,'espacio_tiene_movimiento_abierto')
                WHERE NEW.activo=1 AND EXISTS (SELECT 1 FROM movimientos m
                                              WHERE m.id_espacio=NEW.id_espacio AND m.fecha_salida IS NULL);
                SELECT RAISE(ABORT,'vehiculo_ya_tiene_movimiento_activo')
                WHERE NEW.activo=1 AND EXISTS (SELECT 1 FROM movimientos m
                                              WHERE m.id_vehiculo=NEW.id_vehiculo AND m.fecha_salida IS NULL);
            END
        """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_espacio_clasificacion_protegida_v2
        BEFORE UPDATE OF es_reservado,id_cliente ON espacios
        BEGIN
            SELECT RAISE(ABORT,'espacio_tiene_movimiento_abierto')
            WHERE (COALESCE(NEW.es_reservado,0)<>0 OR NEW.id_cliente IS NOT NULL)
              AND EXISTS (SELECT 1 FROM movimientos m WHERE m.id_espacio=OLD.id_espacio AND m.fecha_salida IS NULL);
            SELECT RAISE(ABORT,'espacio_tiene_contrato_activo')
            WHERE COALESCE(NEW.es_reservado,0)<>1
              AND EXISTS (SELECT 1 FROM cochera_contratos cc WHERE cc.id_espacio=OLD.id_espacio AND cc.activo=1);
            SELECT RAISE(ABORT,'espacio_tiene_contrato_pendiente')
            WHERE COALESCE(NEW.es_reservado,0)<>1
              AND EXISTS (SELECT 1 FROM cochera_contratos cc WHERE cc.id_espacio=OLD.id_espacio
                          AND COALESCE(cc.activo,0)<>1 AND COALESCE(cc.en_historial,0)=0);
        END
    """)


def _configurar_conexion(conn):
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise DatabaseIntegrityError({"claves_foraneas_deshabilitadas": [(1,)]})
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_connection():
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        return _configurar_conexion(conn)
    except BaseException:
        conn.close()
        raise


def validar_integridad_db(conn=None):
    own_conn = conn is None
    try:
        conn = conn or get_connection()
        cur = conn.cursor()
        return [tuple(row) for row in cur.execute("PRAGMA foreign_key_check").fetchall()]
    finally:
        if own_conn and conn:
            conn.close()


def reparar_integridad_db(conn=None):
    """Compatibilidad: informa conflictos sin corregir ni eliminar registros.

    Una reparación exige revisar el diagnóstico y un respaldo; nunca se infieren
    propietarios, vehículos o zonas horarias automáticamente.
    """
    conflictos = diagnosticar_integridad_db(conn)
    return {"conflictos": conflictos,
            "violaciones_restantes": sum(len(filas) for filas in conflictos.values())}


def init_db(db_path=None):
    """Inicializa atómicamente la base actual o una candidata, sin cambiar DB_PATH."""
    if db_path is None:
        conn = get_connection()
    else:
        candidate = Path(db_path).expanduser().resolve()
        candidate.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(candidate))
    try:
        if db_path is not None:
            _configurar_conexion(conn)
        # Diagnóstico previo: si hay datos incompatibles no se modifica ni el esquema.
        _comprobar_integridad_db(conn)
        _crear_esquema_y_migrar(conn)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _crear_esquema_y_migrar(conn):
    cursor = conn.cursor()

    cursor.executescript("""
    BEGIN IMMEDIATE;
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

    _migrar_columnas_no_destructivo(cursor)
    _comprobar_integridad_db(conn)
    _instalar_guardias_integridad(cursor)
    cursor.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


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
            if tabla == "espacios_mapa":
                # Sólo el reset explícito: contratos y estadías ya se borraron.
                # Liberar la asignación permite quitar el mapa con sus guardias.
                cursor.execute("UPDATE espacios SET id_cliente = NULL")
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
