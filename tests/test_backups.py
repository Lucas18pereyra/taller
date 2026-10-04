"""Un respaldo invalido nunca debe pisar la base que funciona."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import sqlite3
import unittest
from unittest.mock import patch

import database
from servicios import backups, arranque


class RespaldoTests(unittest.TestCase):
    def setUp(self):
        self.temporal = TemporaryDirectory(prefix="respaldos_regresion_")
        self.ruta = Path(self.temporal.name) / "estacionamiento.db"
        self.parche = patch.object(database, "DB_PATH", self.ruta)
        self.parche.start()
        database.init_db()
        with closing(database.get_connection()) as conn:
            conn.execute("INSERT INTO clientes (dni,nombre) VALUES ('99000001','Cliente conservado')")
            conn.execute("INSERT INTO espacios (codigo,es_reservado,id_cliente) VALUES ('C01',1,1)")
            conn.commit()

    def tearDown(self):
        self.parche.stop()
        self.temporal.cleanup()

    def hash(self):
        return hashlib.sha256(self.ruta.read_bytes()).hexdigest()

    def test_dos_respaldos_seguidos_no_se_pisan(self):
        uno = backups.crear_backup_db(max_backups=None)
        dos = backups.crear_backup_db(max_backups=None)
        self.assertNotEqual(uno, dos)
        self.assertTrue(uno.exists() and dos.exists())

    def test_restaurar_preserva_cliente_asignado_sin_contrato(self):
        original = backups.crear_backup_db(max_backups=None)
        with closing(database.get_connection()) as conn:
            conn.execute("UPDATE clientes SET nombre='Cambio posterior'")
            conn.commit()
        self.assertTrue(backups.restaurar_backup_db(original))
        with closing(database.get_connection()) as conn:
            self.assertEqual(conn.execute("SELECT nombre FROM clientes").fetchone()[0], "Cliente conservado")
            self.assertEqual(conn.execute("SELECT id_cliente FROM espacios WHERE codigo='C01'").fetchone()[0], 1)
        self.assertGreaterEqual(len(backups.listar_backups_db()), 2)

    def test_respaldo_corrupto_no_reemplaza_datos(self):
        candidato = backups.crear_backup_db(max_backups=None)
        # Corromper SOLO una copia temporal con una operacion SQLite valida.
        with closing(sqlite3.connect(candidato)) as conn:
            conn.execute("PRAGMA writable_schema=ON")
            conn.execute("UPDATE sqlite_master SET sql='not a create statement' WHERE name='clientes'")
            conn.commit()
        antes = self.hash()
        self.assertFalse(backups.restaurar_backup_db(candidato))
        self.assertEqual(self.hash(), antes)

    def test_duplicados_heredados_no_reemplazan_datos(self):
        candidato = backups.crear_backup_db(max_backups=None)
        with closing(sqlite3.connect(candidato)) as conn:
            for nombre, in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
                conn.execute(f'DROP TRIGGER "{nombre}"')
            for nombre, in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql LIKE '%UNIQUE%' AND tbl_name='movimientos'").fetchall():
                conn.execute(f'DROP INDEX "{nombre}"')
            conn.execute("INSERT INTO vehiculos (patente) VALUES ('QA001AA')")
            conn.execute("INSERT INTO vehiculos (patente) VALUES ('QA002AA')")
            conn.execute("INSERT INTO espacios (codigo) VALUES ('E01')")
            conn.execute("INSERT INTO movimientos (id_vehiculo,id_espacio) VALUES (1,2)")
            conn.execute("INSERT INTO movimientos (id_vehiculo,id_espacio) VALUES (2,2)")
            conn.commit()
        antes = self.hash()
        self.assertFalse(backups.restaurar_backup_db(candidato))
        self.assertEqual(self.hash(), antes)

    def test_sqlite_ajeno_y_ruta_externa_se_rechazan(self):
        carpeta = self.ruta.parent / "backups"
        carpeta.mkdir(exist_ok=True)
        candidato = carpeta / "otra_aplicacion.db"
        with closing(sqlite3.connect(candidato)) as conn:
            conn.execute("CREATE TABLE otra (dato TEXT)")
            conn.commit()
        antes = self.hash()
        self.assertFalse(backups.restaurar_backup_db(candidato))
        self.assertFalse(backups.restaurar_backup_db(self.ruta))
        self.assertFalse(backups.eliminar_backup_db(self.ruta))
        self.assertEqual(self.hash(), antes)

    def test_migracion_respalda_antes_y_no_repite_version_actual(self):
        self.assertIsNone(arranque.respaldar_antes_de_migrar())
        with closing(database.get_connection()) as conn:
            conn.execute("PRAGMA user_version=0")
        antes = self.hash()
        ruta = arranque.respaldar_antes_de_migrar()
        self.assertTrue(ruta.exists())
        self.assertEqual(self.hash(), antes)
        self.assertIn(ruta, backups.listar_backups_db())
        database.init_db()
        self.assertIsNone(arranque.respaldar_antes_de_migrar())

    def test_init_rechaza_otro_sqlite_sin_agregar_tablas(self):
        ajena = self.ruta.parent / "otra.db"
        with closing(sqlite3.connect(ajena)) as conn:
            conn.execute("CREATE TABLE ajena (dato TEXT)")
            conn.commit()
        antes = hashlib.sha256(ajena.read_bytes()).hexdigest()
        with self.assertRaises(database.DatabaseIntegrityError):
            database.init_db(db_path=ajena)
        self.assertEqual(hashlib.sha256(ajena.read_bytes()).hexdigest(), antes)

    def test_init_rechaza_id_de_otra_app_sin_cambiar_datos(self):
        with closing(database.get_connection()) as conn:
            conn.execute("PRAGMA application_id=12345")
        antes = self.hash()
        with self.assertRaises(database.DatabaseIntegrityError):
            database.init_db()
        self.assertEqual(self.hash(), antes)


if __name__ == "__main__":
    unittest.main()
