"""Garantías de integridad verificadas únicamente en bases temporales."""

from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database


class IntegridadDBTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="estacionamiento_integridad_test_")
        self.previous_path = database.DB_PATH
        database.DB_PATH = Path(self.temporary.name) / "test.db"
        database.init_db()
        self.conn = database.get_connection()
        self.conn.executemany("INSERT INTO clientes (id_cliente,dni,nombre) VALUES (?,?,?)",
                              [(1, "QA1", "Cliente QA 1"), (2, "QA2", "Cliente QA 2")])
        self.conn.executemany("INSERT INTO vehiculos (id_vehiculo,patente,id_cliente) VALUES (?,?,?)",
                              [(1, "QA001AA", 1), (2, "QA002AA", 2), (3, "QA003AA", 1)])
        self.conn.executemany("INSERT INTO espacios (id_espacio,codigo,es_reservado) VALUES (?,?,?)",
                              [(1, "C01", 1), (2, "C02", 1), (3, "E01", 0), (4, "E02", 0)])
        self.conn.executemany("INSERT INTO espacios_mapa (codigo,x,y,w,h) VALUES (?,0,0,120,70)",
                              [("C01",), ("C02",), ("E01",), ("E02",)])
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        database.DB_PATH = self.previous_path
        self.temporary.cleanup()

    def contract(self, space=1, vehicle=1, active=1, history=0):
        client = self.conn.execute("SELECT id_cliente FROM vehiculos WHERE id_vehiculo=?", (vehicle,)).fetchone()[0]
        cursor = self.conn.execute(
            "INSERT INTO cochera_contratos (id_cliente,id_vehiculo,id_espacio,fecha_vencimiento,"
            "monto_mensual,activo,en_historial) VALUES (?,?,?,'2099-12-31',48000,?,?)",
            (client, vehicle, space, active, history))
        self.conn.commit()
        return cursor.lastrowid

    def movement(self, space=3, vehicle=1, closed=False):
        cursor = self.conn.execute("INSERT INTO movimientos (id_vehiculo,id_espacio,fecha_ingreso,fecha_salida) "
                                   "VALUES (?,?,'2026-01-01 10:00:00',?)",
                                   (vehicle, space, "2026-01-01 12:00:00" if closed else None))
        self.conn.commit()
        return cursor.lastrowid

    def rejected(self, code, sql, parameters=()):
        with self.assertRaisesRegex(sqlite3.IntegrityError, code):
            self.conn.execute(sql, parameters)
        self.conn.rollback()

    def remove_guards(self):
        names = [row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")]
        for name in names:
            self.conn.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        self.conn.commit()

    def data_snapshot(self):
        names = ("clientes", "vehiculos", "espacios", "espacios_mapa", "cochera_contratos", "movimientos", "pagos", "pagos_cochera")
        return {name: [tuple(row) for row in self.conn.execute("SELECT * FROM " + name + " ORDER BY 1")]
                for name in names}

    def test_cliente_asignado_impide_borrar_desactivar_y_quitar_del_mapa(self):
        self.conn.execute("UPDATE espacios SET id_cliente=1 WHERE id_espacio=1")
        self.conn.commit()
        for action in ("DELETE FROM espacios WHERE id_espacio=1", "UPDATE espacios SET activo=0 WHERE id_espacio=1",
                       "UPDATE espacios SET activo=NULL WHERE id_espacio=1", "DELETE FROM espacios_mapa WHERE codigo='C01'"):
            with self.subTest(action=action):
                self.rejected("espacio_tiene_cliente_asignado", action)

    def test_contrato_activo_impide_borrar_desactivar_y_quitar_del_mapa(self):
        self.contract()
        for sql in ("DELETE FROM espacios WHERE id_espacio=1", "UPDATE espacios SET activo=0 WHERE id_espacio=1",
                    "DELETE FROM espacios_mapa WHERE codigo='C01'"):
            with self.subTest(sql=sql):
                self.rejected("espacio_tiene_contrato_activo", sql)

    def test_contrato_pendiente_impide_borrar_desactivar_y_quitar_del_mapa(self):
        self.contract(active=0, history=0)
        for sql in ("DELETE FROM espacios WHERE id_espacio=1", "UPDATE espacios SET activo=0 WHERE id_espacio=1",
                    "DELETE FROM espacios_mapa WHERE codigo='C01'"):
            with self.subTest(sql=sql):
                self.rejected("espacio_tiene_contrato_pendiente", sql)

    def test_estadia_abierta_impide_borrar_desactivar_y_quitar_del_mapa(self):
        self.movement()
        for sql in ("DELETE FROM espacios WHERE id_espacio=3", "UPDATE espacios SET activo=0 WHERE id_espacio=3",
                    "DELETE FROM espacios_mapa WHERE codigo='E01'"):
            with self.subTest(sql=sql):
                self.rejected("espacio_tiene_movimiento_abierto", sql)

    def test_geometria_del_lugar_ocupado_puede_cambiar(self):
        self.movement()
        self.conn.execute("UPDATE espacios_mapa SET x=100,y=200,w=130,h=80 WHERE codigo='E01'")
        self.conn.commit()
        self.assertEqual((100, 200, 130, 80), tuple(self.conn.execute("SELECT x,y,w,h FROM espacios_mapa WHERE codigo='E01'").fetchone()))

    def test_lugar_libre_se_puede_borrar(self):
        self.conn.execute("DELETE FROM espacios_mapa WHERE codigo='E02'")
        self.conn.execute("DELETE FROM espacios WHERE id_espacio=4")
        self.conn.commit()
        self.assertIsNone(self.conn.execute("SELECT 1 FROM espacios WHERE id_espacio=4").fetchone())

    def test_historico_permite_desactivar_y_quitar_mapa_pero_preserva_fk(self):
        self.contract(active=0, history=1)
        self.conn.execute("DELETE FROM espacios_mapa WHERE codigo='C01'")
        self.conn.execute("UPDATE espacios SET activo=0 WHERE id_espacio=1")
        self.conn.commit()
        self.rejected("FOREIGN KEY constraint failed", "DELETE FROM espacios WHERE id_espacio=1")
        self.assertEqual(1, self.conn.execute("SELECT COUNT(*) FROM cochera_contratos").fetchone()[0])

    def test_estadia_cerrada_permite_desactivar_y_preserva_historial(self):
        self.movement(closed=True)
        self.conn.execute("DELETE FROM espacios_mapa WHERE codigo='E01'")
        self.conn.execute("UPDATE espacios SET activo=0 WHERE id_espacio=3")
        self.conn.commit()
        self.rejected("FOREIGN KEY constraint failed", "DELETE FROM espacios WHERE id_espacio=3")

    def test_contrato_unico_por_espacio_en_insert_y_update(self):
        self.contract()
        self.rejected("espacio_ya_tiene_contrato_activo",
                      "INSERT INTO cochera_contratos (id_cliente,id_vehiculo,id_espacio,fecha_vencimiento,monto_mensual) "
                      "VALUES (2,2,1,'2099-12-31',48000)")
        second = self.contract(space=2, vehicle=2, active=0)
        self.rejected("espacio_ya_tiene_contrato_activo",
                      "UPDATE cochera_contratos SET id_espacio=1,activo=1 WHERE id_contrato=?", (second,))

    def test_estadia_unica_por_espacio_en_insert_y_update(self):
        self.movement()
        self.rejected("espacio_ya_tiene_movimiento_activo", "INSERT INTO movimientos (id_vehiculo,id_espacio) VALUES (2,3)")
        second = self.movement(space=4, vehicle=2, closed=True)
        self.rejected("espacio_ya_tiene_movimiento_activo",
                      "UPDATE movimientos SET id_espacio=3,fecha_salida=NULL WHERE id_movimiento=?", (second,))

    def test_vehiculo_no_puede_tener_dos_contratos_activos(self):
        self.contract()
        self.rejected("vehiculo_ya_tiene_contrato_activo",
                      "INSERT INTO cochera_contratos (id_cliente,id_vehiculo,id_espacio,fecha_vencimiento,monto_mensual) "
                      "VALUES (1,1,2,'2099-12-31',48000)")

    def test_vehiculo_no_puede_tener_dos_estadias_abiertas(self):
        self.movement()
        self.rejected("vehiculo_ya_tiene_movimiento_activo", "INSERT INTO movimientos (id_vehiculo,id_espacio) VALUES (1,4)")

    def test_contrato_activo_impide_estadia_para_mismo_vehiculo(self):
        self.contract()
        self.rejected("vehiculo_ya_tiene_contrato_activo", "INSERT INTO movimientos (id_vehiculo,id_espacio) VALUES (1,3)")

    def test_estadia_abierta_impide_contrato_para_mismo_vehiculo(self):
        self.movement()
        self.rejected("vehiculo_ya_tiene_movimiento_activo",
                      "INSERT INTO cochera_contratos (id_cliente,id_vehiculo,id_espacio,fecha_vencimiento,monto_mensual) "
                      "VALUES (1,1,1,'2099-12-31',48000)")

    def test_otro_vehiculo_del_mismo_cliente_puede_estacionar(self):
        self.contract()
        self.movement(vehicle=3)
        self.assertEqual(1, self.conn.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0])

    def test_contrato_inactivo_no_bloquea_estadia(self):
        self.contract(active=0, history=1)
        self.movement()

    def test_lugar_desactivado_no_admite_estadia_ni_activacion_de_contrato(self):
        self.conn.execute("UPDATE espacios SET activo=0 WHERE id_espacio IN (1,3)")
        self.conn.commit()
        self.rejected("espacio_no_disponible_para_estacionamiento", "INSERT INTO movimientos (id_vehiculo,id_espacio) VALUES (1,3)")
        contract = self.contract(active=0, history=1)
        self.rejected("espacio_no_es_cochera", "UPDATE cochera_contratos SET activo=1 WHERE id_contrato=?", (contract,))

    def test_cochera_reservada_o_asignada_no_admite_estadia(self):
        self.rejected("espacio_no_disponible_para_estacionamiento", "INSERT INTO movimientos (id_vehiculo,id_espacio) VALUES (1,1)")
        self.conn.execute("UPDATE espacios SET id_cliente=1 WHERE id_espacio=3")
        self.conn.commit()
        self.rejected("espacio_no_disponible_para_estacionamiento", "INSERT INTO movimientos (id_vehiculo,id_espacio) VALUES (1,3)")

    def test_no_se_puede_convertir_lugar_ocupado_en_cochera(self):
        self.movement()
        self.rejected("espacio_tiene_movimiento_abierto", "UPDATE espacios SET es_reservado=1 WHERE id_espacio=3")
        self.rejected("espacio_tiene_movimiento_abierto", "UPDATE espacios SET id_cliente=1 WHERE id_espacio=3")

    def test_conflicto_heredado_no_borra_dos_estadias(self):
        self.remove_guards()
        self.movement()
        self.movement(vehicle=2)
        before = self.data_snapshot()
        with self.assertRaises(database.DatabaseIntegrityError) as raised:
            database.init_db()
        self.assertIn("movimientos_abiertos_por_espacio", raised.exception.conflictos)
        self.assertEqual(before, self.data_snapshot())

    def test_conflicto_heredado_no_borra_contratos_duplicados(self):
        self.remove_guards()
        self.contract()
        self.contract(vehicle=2)
        before = self.data_snapshot()
        with self.assertRaises(database.DatabaseIntegrityError) as raised:
            database.init_db()
        self.assertIn("contratos_activos_por_espacio", raised.exception.conflictos)
        self.assertEqual(before, self.data_snapshot())

    def test_conflicto_heredado_mezcla_contrato_y_estadia_se_informa(self):
        self.remove_guards()
        self.contract()
        self.movement(space=1, vehicle=2)
        before = self.data_snapshot()
        with self.assertRaises(database.DatabaseIntegrityError) as raised:
            database.init_db()
        self.assertIn("espacios_con_contrato_y_estadia", raised.exception.conflictos)
        self.assertEqual(before, self.data_snapshot())

    def test_referencia_huerfana_se_informa_sin_borrar_pago(self):
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.execute("INSERT INTO pagos (id_movimiento,monto,metodo) VALUES (999,1500,'Efectivo')")
        self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys=ON")
        before = self.data_snapshot()
        with self.assertRaises(database.DatabaseIntegrityError) as raised:
            database.init_db()
        self.assertIn("referencias_invalidas", raised.exception.conflictos)
        self.assertEqual(before, self.data_snapshot())

    def test_init_repetido_preserva_fechas_y_contrato_sin_vehiculo(self):
        contract = self.contract(active=0, history=1)
        self.conn.execute("UPDATE cochera_contratos SET id_vehiculo=NULL WHERE id_contrato=?", (contract,))
        self.conn.execute("INSERT INTO pagos_cochera (id_contrato,monto,metodo,fecha_pago) "
                          "VALUES (?,48000,'Efectivo','2024-05-08 12:30:00')", (contract,))
        self.conn.execute("DELETE FROM configuracion WHERE clave='migracion_pagos_cochera_local_v1'")
        self.conn.commit()
        before = self.data_snapshot()
        database.init_db()
        database.init_db()
        self.assertEqual(before, self.data_snapshot())

    def test_fallo_al_instalar_guardias_hace_rollback_y_cierra_conexion(self):
        before = self.data_snapshot()
        schema = [tuple(row) for row in self.conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name")]
        with patch("database._instalar_guardias_integridad", side_effect=RuntimeError("fallo QA")):
            with self.assertRaisesRegex(RuntimeError, "fallo QA"):
                database.init_db()
        self.assertEqual(before, self.data_snapshot())
        self.assertEqual(schema, [tuple(row) for row in self.conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name")])
        self.conn.execute("BEGIN IMMEDIATE")
        self.conn.rollback()

    def test_reset_explicito_sigue_funcionando_con_guardias(self):
        self.contract()
        self.conn.execute("UPDATE espacios SET id_cliente=1 WHERE id_espacio=1")
        self.conn.commit()
        database.reset_db()
        self.assertTrue(all(not rows for rows in self.data_snapshot().values()))

    def test_helper_de_reparacion_es_diagnostico_sin_modificar(self):
        self.remove_guards()
        self.movement()
        self.movement(vehicle=2)
        before = self.data_snapshot()
        resultado = database.reparar_integridad_db(self.conn)
        self.assertIn("movimientos_abiertos_por_espacio", resultado["conflictos"])
        self.assertGreater(resultado["violaciones_restantes"], 0)
        self.assertEqual(before, self.data_snapshot())

    def test_init_candidata_no_cambia_la_ruta_actual(self):
        candidate = Path(self.temporary.name) / "candidate.db"
        target = sqlite3.connect(candidate)
        try:
            self.conn.backup(target)
        finally:
            target.close()
        original_path = database.DB_PATH
        database.init_db(db_path=candidate)
        self.assertEqual(original_path, database.DB_PATH)
        with sqlite3.connect(candidate) as conn:
            self.assertEqual(database.SCHEMA_VERSION, conn.execute("PRAGMA user_version").fetchone()[0])
        conn.close()

    def legacy_db(self):
        candidate = Path(self.temporary.name) / "legacy.db"
        conn = sqlite3.connect(candidate)
        conn.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE clientes (id_cliente INTEGER PRIMARY KEY,dni TEXT UNIQUE,nombre TEXT,direccion TEXT,telefono TEXT,fecha_nacimiento DATE,activo INTEGER DEFAULT 1);
            CREATE TABLE vehiculos (id_vehiculo INTEGER PRIMARY KEY,patente TEXT UNIQUE,id_cliente INTEGER REFERENCES clientes(id_cliente));
            CREATE TABLE espacios (id_espacio INTEGER PRIMARY KEY,codigo TEXT UNIQUE,es_reservado INTEGER DEFAULT 0,id_cliente INTEGER REFERENCES clientes(id_cliente),activo INTEGER DEFAULT 1);
            CREATE TABLE cochera_contratos (id_contrato INTEGER PRIMARY KEY,id_cliente INTEGER REFERENCES clientes(id_cliente),id_espacio INTEGER REFERENCES espacios(id_espacio),fecha_inicio DATE,fecha_vencimiento DATE,monto_mensual REAL,activo INTEGER DEFAULT 1);
            CREATE TABLE movimientos (id_movimiento INTEGER PRIMARY KEY,id_vehiculo INTEGER REFERENCES vehiculos(id_vehiculo),id_espacio INTEGER REFERENCES espacios(id_espacio),fecha_ingreso DATETIME,fecha_salida DATETIME,total REAL);
            CREATE TABLE pagos (id_pago INTEGER PRIMARY KEY,id_movimiento INTEGER REFERENCES movimientos(id_movimiento),monto REAL,metodo TEXT,fecha_pago DATETIME);
            CREATE TABLE pagos_cochera (id_pago INTEGER PRIMARY KEY,id_contrato INTEGER REFERENCES cochera_contratos(id_contrato),monto REAL,metodo TEXT,fecha_pago DATETIME);
            CREATE TABLE tarifas (id_tarifa INTEGER PRIMARY KEY,precio_hora REAL,activa INTEGER DEFAULT 1,fecha_desde DATETIME);
            CREATE TABLE configuracion (clave TEXT PRIMARY KEY,valor TEXT);
            INSERT INTO clientes (id_cliente,dni,nombre) VALUES (1,'LEGADO-QA','Cliente legado QA');
            INSERT INTO vehiculos VALUES (1,'QA099AA',1);
            INSERT INTO espacios (id_espacio,codigo,es_reservado) VALUES (1,'L-C01',1),(2,'L-E01',0);
            INSERT INTO cochera_contratos VALUES (1,1,1,'2024-01-01','2024-02-01',48000,0);
            INSERT INTO movimientos VALUES (1,1,2,'2024-05-08 10:30:00','2024-05-08 12:30:00',3000);
            INSERT INTO pagos VALUES (1,1,3000,'Efectivo','2024-05-08 12:30:00');
            INSERT INTO pagos_cochera VALUES (1,1,48000,'Efectivo','2024-01-02 14:25:00');
            INSERT INTO tarifas VALUES (1,1500,1,'2024-01-01 00:00:00');
        """)
        conn.close()
        return candidate

    def test_migracion_heredada_preserva_todos_los_registros_y_fechas(self):
        candidate = self.legacy_db()
        conn = sqlite3.connect(candidate)
        tables = ("clientes", "vehiculos", "espacios", "cochera_contratos", "movimientos", "pagos", "pagos_cochera", "tarifas")
        columns = {table: [row[1] for row in conn.execute(f"PRAGMA table_info({table})")] for table in tables}
        before = {table: conn.execute(f"SELECT {','.join(columns[table])} FROM {table} ORDER BY 1").fetchall() for table in tables}
        conn.close()
        database.init_db(db_path=candidate)
        database.init_db(db_path=candidate)
        conn = sqlite3.connect(candidate)
        after = {table: conn.execute(f"SELECT {','.join(columns[table])} FROM {table} ORDER BY 1").fetchall() for table in tables}
        self.assertEqual(before, after)
        self.assertIsNone(conn.execute("SELECT id_vehiculo FROM cochera_contratos").fetchone()[0])
        self.assertEqual(database.SCHEMA_VERSION, conn.execute("PRAGMA user_version").fetchone()[0])
        conn.close()

    def test_fallo_migracion_heredada_revierte_columnas_y_tablas_nuevas(self):
        candidate = self.legacy_db()
        conn = sqlite3.connect(candidate)
        before = conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name").fetchall()
        conn.close()
        with patch("database._instalar_guardias_integridad", side_effect=RuntimeError("fallo QA")):
            with self.assertRaisesRegex(RuntimeError, "fallo QA"):
                database.init_db(db_path=candidate)
        conn = sqlite3.connect(candidate)
        self.assertEqual(before, conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name").fetchall())
        self.assertEqual(0, conn.execute("PRAGMA user_version").fetchone()[0])
        self.assertEqual("2024-01-02 14:25:00", conn.execute("SELECT fecha_pago FROM pagos_cochera").fetchone()[0])
        conn.close()


if __name__ == "__main__":
    unittest.main()
