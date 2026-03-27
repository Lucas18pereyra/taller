import tempfile
import unittest
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import database
from database import get_connection, init_db
from servicios.cobro import (
    calcular_total_estadia,
    horas_cobradas_con_tolerancia,
    parse_fecha_db,
)
from servicios.contratos import (
    calcular_nueva_fecha_vencimiento,
    obtener_detalle_contrato,
    obtener_patente_por_dni,
    registrar_primer_pago_contrato,
    registrar_renovacion_contrato,
)
from servicios.validaciones import (
    cliente_tiene_movimiento_activo,
    codigo_cochera_activa_cliente,
    vehiculo_tiene_movimiento_activo,
)
from servicios.caja import (
    eliminar_cierre_caja,
    guardar_cierre_caja,
    obtener_cierre_caja,
)
from servicios.backups import crear_backup_db, restaurar_backup_db
import main as app_main


def _tmp_dir_tests():
    base = Path(tempfile.gettempdir()) / "cochera_app_tests"
    base.mkdir(parents=True, exist_ok=True)
    return base


class CobroPorHoraTests(unittest.TestCase):
    def test_tolerancia_15_minutos(self):
        self.assertEqual(horas_cobradas_con_tolerancia(60 * 60 + 15 * 60), 1)
        self.assertEqual(horas_cobradas_con_tolerancia(60 * 60 + 15 * 60 + 1), 2)

    def test_tolerancia_primeros_15_minutos_sin_cobro(self):
        self.assertEqual(horas_cobradas_con_tolerancia(10 * 60), 0)
        self.assertEqual(horas_cobradas_con_tolerancia(15 * 60), 0)
        self.assertEqual(horas_cobradas_con_tolerancia(15 * 60 + 1), 1)

    def test_calculo_total_con_tarifa(self):
        ingreso = datetime(2026, 2, 13, 10, 0, 0)
        salida = ingreso + timedelta(hours=1, minutes=10)
        horas, total = calcular_total_estadia(ingreso, salida, tarifa_hora=1000)
        self.assertEqual(horas, 1)
        self.assertEqual(total, 1000.0)

        salida = ingreso + timedelta(hours=1, minutes=16)
        horas, total = calcular_total_estadia(ingreso, salida, tarifa_hora=1000)
        self.assertEqual(horas, 2)
        self.assertEqual(total, 2000.0)

        salida = ingreso + timedelta(minutes=10)
        horas, total = calcular_total_estadia(ingreso, salida, tarifa_hora=1000)
        self.assertEqual(horas, 0)
        self.assertEqual(total, 0.0)

    def test_parseo_fechas_db(self):
        self.assertIsNotNone(parse_fecha_db("2026-02-13 10:00:00"))
        self.assertIsNotNone(parse_fecha_db("2026-02-13T10:00:00"))
        self.assertIsNone(parse_fecha_db(""))


class ExclusividadPatenteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=_tmp_dir_tests())
        self._db_original = database.DB_PATH
        database.DB_PATH = Path(self._tmp.name) / "test_estacionamiento.db"
        init_db()

    def tearDown(self):
        database.DB_PATH = self._db_original
        self._tmp.cleanup()

    def _crear_cliente(self, dni="30111222", nombre="Juan"):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clientes (dni, nombre, activo) VALUES (?, ?, 1)",
            (dni, nombre),
        )
        cid = cur.lastrowid
        conn.commit()
        conn.close()
        return cid

    def _crear_espacio(self, codigo="A1", reservado=0):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO espacios (codigo, es_reservado, activo) VALUES (?, ?, 1)",
            (codigo, reservado),
        )
        eid = cur.lastrowid
        conn.commit()
        conn.close()
        return eid

    def _crear_vehiculo(self, patente="AAA111", id_cliente=None):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO vehiculos (patente, id_cliente) VALUES (?, ?)",
            (patente, id_cliente),
        )
        vid = cur.lastrowid
        conn.commit()
        conn.close()
        return vid

    def test_detecta_cochera_activa_por_cliente(self):
        id_cliente = self._crear_cliente()
        id_espacio = self._crear_espacio("C1", reservado=1)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cochera_contratos "
            "(id_cliente, id_espacio, fecha_vencimiento, monto_mensual, activo) "
            "VALUES (?, ?, '2026-03-13', 20000, 1)",
            (id_cliente, id_espacio),
        )
        conn.commit()

        codigo = codigo_cochera_activa_cliente(cur, id_cliente)
        conn.close()
        self.assertEqual(codigo, "C1")

    def test_detecta_movimiento_activo_por_cliente_y_vehiculo(self):
        id_cliente = self._crear_cliente()
        id_espacio = self._crear_espacio("E5", reservado=0)
        id_vehiculo = self._crear_vehiculo("BBB222", id_cliente=id_cliente)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO movimientos (id_vehiculo, id_espacio) VALUES (?, ?)",
            (id_vehiculo, id_espacio),
        )
        conn.commit()

        self.assertTrue(vehiculo_tiene_movimiento_activo(cur, id_vehiculo))
        row = cliente_tiene_movimiento_activo(cur, id_cliente)
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["patente"], "BBB222")
        self.assertEqual(row["codigo"], "E5")

    def test_vehiculo_no_activo_despues_de_salida(self):
        id_cliente = self._crear_cliente()
        id_espacio = self._crear_espacio("E8", reservado=0)
        id_vehiculo = self._crear_vehiculo("CCC333", id_cliente=id_cliente)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO movimientos (id_vehiculo, id_espacio, fecha_salida, total) "
            "VALUES (?, ?, '2026-02-13 12:00:00', 1000)",
            (id_vehiculo, id_espacio),
        )
        conn.commit()
        activo = vehiculo_tiene_movimiento_activo(cur, id_vehiculo)
        conn.close()

        self.assertFalse(activo)

    def test_db_impide_dos_movimientos_activos_mismo_vehiculo(self):
        id_cliente = self._crear_cliente(dni="40111222")
        id_espacio_1 = self._crear_espacio("E10", reservado=0)
        id_espacio_2 = self._crear_espacio("E11", reservado=0)
        id_vehiculo = self._crear_vehiculo("DDD555", id_cliente=id_cliente)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO movimientos (id_vehiculo, id_espacio) VALUES (?, ?)",
            (id_vehiculo, id_espacio_1),
        )
        conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute(
                "INSERT INTO movimientos (id_vehiculo, id_espacio) VALUES (?, ?)",
                (id_vehiculo, id_espacio_2),
            )
            conn.commit()
        conn.close()

    def test_db_permite_nuevo_movimiento_si_el_anterior_ya_salio(self):
        id_cliente = self._crear_cliente(dni="40111223")
        id_espacio_1 = self._crear_espacio("E12", reservado=0)
        id_espacio_2 = self._crear_espacio("E13", reservado=0)
        id_vehiculo = self._crear_vehiculo("EEE666", id_cliente=id_cliente)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO movimientos (id_vehiculo, id_espacio, fecha_salida, total) "
            "VALUES (?, ?, '2026-02-13 12:00:00', 1000)",
            (id_vehiculo, id_espacio_1),
        )
        cur.execute(
            "INSERT INTO movimientos (id_vehiculo, id_espacio) VALUES (?, ?)",
            (id_vehiculo, id_espacio_2),
        )
        conn.commit()
        conn.close()


class ContratosPagoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=_tmp_dir_tests())
        self._db_original = database.DB_PATH
        database.DB_PATH = Path(self._tmp.name) / "test_estacionamiento.db"
        init_db()

    def tearDown(self):
        database.DB_PATH = self._db_original
        self._tmp.cleanup()

    def _crear_cliente(self, dni="30111222", nombre="Juan"):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clientes (dni, nombre, activo) VALUES (?, ?, 1)",
            (dni, nombre),
        )
        cid = cur.lastrowid
        conn.commit()
        conn.close()
        return cid

    def _crear_espacio(self, codigo="A1", reservado=1):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO espacios (codigo, es_reservado, activo) VALUES (?, ?, 1)",
            (codigo, reservado),
        )
        eid = cur.lastrowid
        conn.commit()
        conn.close()
        return eid

    def _crear_vehiculo(self, patente="AAA111", id_cliente=None):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO vehiculos (patente, id_cliente) VALUES (?, ?)",
            (patente, id_cliente),
        )
        vid = cur.lastrowid
        conn.commit()
        conn.close()
        return vid

    def _crear_contrato(
        self,
        id_cliente,
        id_espacio,
        fecha_vencimiento=None,
        monto=20000,
        activo=0,
        id_vehiculo=None,
    ):
        if not fecha_vencimiento:
            fecha_vencimiento = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cochera_contratos "
            "(id_cliente, id_vehiculo, id_espacio, fecha_vencimiento, monto_mensual, activo) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (id_cliente, id_vehiculo, id_espacio, fecha_vencimiento, monto, activo),
        )
        contrato_id = cur.lastrowid
        conn.commit()
        conn.close()
        return contrato_id

    def test_primer_pago_activa_contrato_y_asigna_espacio(self):
        id_cliente = self._crear_cliente()
        id_espacio = self._crear_espacio("C2", reservado=1)
        self._crear_vehiculo("AAA111", id_cliente=id_cliente)
        contrato_id = self._crear_contrato(id_cliente, id_espacio, activo=0)

        resultado = registrar_primer_pago_contrato(contrato_id, 20000, "Efectivo")
        self.assertEqual(resultado["id_cliente"], id_cliente)
        self.assertEqual(resultado["id_espacio"], id_espacio)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT activo FROM cochera_contratos WHERE id_contrato = ?",
            (contrato_id,),
        )
        self.assertEqual(int(cur.fetchone()["activo"] or 0), 1)
        cur.execute(
            "SELECT id_cliente FROM espacios WHERE id_espacio = ?",
            (id_espacio,),
        )
        self.assertEqual(cur.fetchone()["id_cliente"], id_cliente)
        cur.execute(
            "SELECT COUNT(*) FROM pagos_cochera WHERE id_contrato = ?",
            (contrato_id,),
        )
        self.assertEqual(cur.fetchone()[0], 1)
        conn.close()

    def test_primer_pago_guarda_fecha_local_explicita(self):
        id_cliente = self._crear_cliente(dni="30111221")
        id_espacio = self._crear_espacio("C2B", reservado=1)
        self._crear_vehiculo("AAA112", id_cliente=id_cliente)
        contrato_id = self._crear_contrato(id_cliente, id_espacio, activo=0)

        registrar_primer_pago_contrato(
            contrato_id,
            20000,
            "Efectivo",
            fecha_pago="2026-03-26 21:45:00",
        )

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT fecha_pago FROM pagos_cochera WHERE id_contrato = ?",
            (contrato_id,),
        )
        self.assertEqual(cur.fetchone()["fecha_pago"], "2026-03-26 21:45:00")
        conn.close()

    def test_primer_pago_rechaza_si_cliente_esta_en_estacionamiento(self):
        id_cliente = self._crear_cliente()
        id_espacio_cochera = self._crear_espacio("C3", reservado=1)
        contrato_id = self._crear_contrato(id_cliente, id_espacio_cochera, activo=0)

        id_espacio_est = self._crear_espacio("E1", reservado=0)
        id_vehiculo = self._crear_vehiculo("DDD444", id_cliente=id_cliente)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO movimientos (id_vehiculo, id_espacio) VALUES (?, ?)",
            (id_vehiculo, id_espacio_est),
        )
        conn.commit()
        conn.close()

        with self.assertRaises(ValueError):
            registrar_primer_pago_contrato(contrato_id, 20000, "Efectivo")

    def test_renovacion_toma_vencimiento_si_sigue_vigente(self):
        id_cliente = self._crear_cliente(dni="30111223")
        id_espacio = self._crear_espacio("C4", reservado=1)
        contrato_id = self._crear_contrato(
            id_cliente,
            id_espacio,
            fecha_vencimiento="2026-02-20",
            activo=1,
        )

        nueva = registrar_renovacion_contrato(
            contrato_id,
            meses=1,
            monto=20000,
            metodo="Transferencia",
            hoy="2026-02-01",
        )
        self.assertEqual(nueva, "2026-03-20")

    def test_renovacion_toma_hoy_si_esta_vencido(self):
        id_cliente = self._crear_cliente(dni="30111224")
        id_espacio = self._crear_espacio("C5", reservado=1)
        contrato_id = self._crear_contrato(
            id_cliente,
            id_espacio,
            fecha_vencimiento="2026-01-10",
            activo=1,
        )

        nueva = registrar_renovacion_contrato(
            contrato_id,
            meses=1,
            monto=20000,
            metodo="Transferencia",
            hoy="2026-02-01",
        )
        self.assertEqual(nueva, "2026-03-01")

    def test_renovacion_guarda_fecha_local_explicita(self):
        id_cliente = self._crear_cliente(dni="30111224")
        id_espacio = self._crear_espacio("C5B", reservado=1)
        contrato_id = self._crear_contrato(
            id_cliente,
            id_espacio,
            fecha_vencimiento="2026-02-20",
            activo=1,
        )

        registrar_renovacion_contrato(
            contrato_id,
            meses=1,
            monto=20000,
            metodo="Transferencia",
            hoy="2026-02-01",
            fecha_pago="2026-03-26 22:10:00",
        )

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT fecha_pago FROM pagos_cochera WHERE id_contrato = ? "
            "ORDER BY id_pago DESC LIMIT 1",
            (contrato_id,),
        )
        self.assertEqual(cur.fetchone()["fecha_pago"], "2026-03-26 22:10:00")
        conn.close()

    def test_primer_pago_rechaza_si_contrato_esta_vencido(self):
        id_cliente = self._crear_cliente(dni="30111225")
        id_espacio = self._crear_espacio("C6", reservado=1)
        contrato_id = self._crear_contrato(
            id_cliente,
            id_espacio,
            fecha_vencimiento="2020-01-01",
            activo=0,
        )

        with self.assertRaises(ValueError) as ctx:
            registrar_primer_pago_contrato(contrato_id, 20000, "Efectivo")
        self.assertIn("vencido", str(ctx.exception).lower())

    def test_contrato_guarda_la_patente_elegida(self):
        id_cliente = self._crear_cliente(dni="30111226")
        id_espacio = self._crear_espacio("C7", reservado=1)
        self._crear_vehiculo("AAA111", id_cliente=id_cliente)
        id_vehiculo_2 = self._crear_vehiculo("BBB222", id_cliente=id_cliente)

        contrato_id = self._crear_contrato(
            id_cliente,
            id_espacio,
            activo=0,
            id_vehiculo=id_vehiculo_2,
        )

        detalle = obtener_detalle_contrato(contrato_id)
        self.assertIsNotNone(detalle)
        self.assertEqual(detalle["patente"], "BBB222")
        self.assertEqual(obtener_patente_por_dni("30111226", "BBB222"), "BBB222")

    def test_db_permite_dos_contratos_activos_mismo_cliente_si_son_patentes_distintas(self):
        id_cliente = self._crear_cliente(dni="30111226")
        id_espacio_1 = self._crear_espacio("C7", reservado=1)
        id_espacio_2 = self._crear_espacio("C8", reservado=1)
        id_vehiculo_1 = self._crear_vehiculo("AAA111", id_cliente=id_cliente)
        id_vehiculo_2 = self._crear_vehiculo("BBB222", id_cliente=id_cliente)

        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO cochera_contratos "
                "(id_cliente, id_espacio, id_vehiculo, fecha_vencimiento, monto_mensual, activo) "
                "VALUES (?, ?, ?, '2026-12-31', 20000, 1)",
                (id_cliente, id_espacio_1, id_vehiculo_1),
            )
            cur.execute(
                "INSERT INTO cochera_contratos "
                "(id_cliente, id_espacio, id_vehiculo, fecha_vencimiento, monto_mensual, activo) "
                "VALUES (?, ?, ?, '2026-12-31', 20000, 1)",
                (id_cliente, id_espacio_2, id_vehiculo_2),
            )
            conn.commit()

            cur.execute(
                "SELECT COUNT(*) FROM cochera_contratos "
                "WHERE id_cliente = ? AND activo = 1",
                (id_cliente,),
            )
            self.assertEqual(cur.fetchone()[0], 2)
        finally:
            conn.close()

    def test_db_impide_dos_contratos_activos_mismo_espacio(self):
        id_cliente_1 = self._crear_cliente(dni="30111227")
        id_cliente_2 = self._crear_cliente(dni="30111228")
        id_espacio = self._crear_espacio("C9", reservado=1)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cochera_contratos "
            "(id_cliente, id_espacio, fecha_vencimiento, monto_mensual, activo) "
            "VALUES (?, ?, '2026-12-31', 20000, 1)",
            (id_cliente_1, id_espacio),
        )
        conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute(
                "INSERT INTO cochera_contratos "
                "(id_cliente, id_espacio, fecha_vencimiento, monto_mensual, activo) "
                "VALUES (?, ?, '2026-12-31', 20000, 1)",
                (id_cliente_2, id_espacio),
            )
            conn.commit()
        conn.close()

    def test_calculo_vencimiento_respeta_fin_de_mes(self):
        nueva = calcular_nueva_fecha_vencimiento(
            "2026-01-31",
            meses=1,
            hoy="2026-01-01",
        )
        self.assertEqual(nueva, "2026-02-28")


class CajaCierreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=_tmp_dir_tests())
        self._db_original = database.DB_PATH
        database.DB_PATH = Path(self._tmp.name) / "test_estacionamiento.db"
        init_db()

    def tearDown(self):
        database.DB_PATH = self._db_original
        self._tmp.cleanup()

    def test_guardar_y_leer_cierre(self):
        ok = guardar_cierre_caja(
            fecha_key="2026-02-14",
            total_esperado=32000,
            total_contado=31900,
            diferencia=-100,
            observacion="Faltante en efectivo",
            usuario="lucas",
        )
        self.assertTrue(ok)

        row = obtener_cierre_caja("2026-02-14")
        self.assertIsNotNone(row)
        self.assertEqual(row["fecha"], "2026-02-14")
        self.assertAlmostEqual(row["total_esperado"], 32000.0)
        self.assertAlmostEqual(row["total_contado"], 31900.0)
        self.assertAlmostEqual(row["diferencia"], -100.0)
        self.assertEqual(row["observacion"], "Faltante en efectivo")
        self.assertEqual(row["usuario"], "lucas")

    def test_guardar_mismo_dia_actualiza(self):
        self.assertTrue(
            guardar_cierre_caja(
                fecha_key="2026-02-14",
                total_esperado=1000,
                total_contado=1000,
                diferencia=0,
                observacion="ok",
                usuario="u1",
            )
        )
        self.assertTrue(
            guardar_cierre_caja(
                fecha_key="2026-02-14",
                total_esperado=1500,
                total_contado=1400,
                diferencia=-100,
                observacion="reconteo",
                usuario="u2",
            )
        )
        row = obtener_cierre_caja("2026-02-14")
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row["total_esperado"], 1500.0)
        self.assertAlmostEqual(row["total_contado"], 1400.0)
        self.assertAlmostEqual(row["diferencia"], -100.0)
        self.assertEqual(row["observacion"], "reconteo")
        self.assertEqual(row["usuario"], "u2")

    def test_eliminar_cierre(self):
        self.assertTrue(
            guardar_cierre_caja(
                fecha_key="2026-02-14",
                total_esperado=5000,
                total_contado=5000,
                diferencia=0,
                observacion="ok",
                usuario="u1",
                detalle_metodos=[
                    {
                        "metodo": "Efectivo",
                        "total_esperado": 5000,
                        "total_contado": 5000,
                        "diferencia": 0,
                    }
                ],
            )
        )
        self.assertTrue(eliminar_cierre_caja("2026-02-14"))
        self.assertIsNone(obtener_cierre_caja("2026-02-14"))


class IntegridadBaseDatosTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=_tmp_dir_tests())
        self._db_original = database.DB_PATH
        database.DB_PATH = Path(self._tmp.name) / "test_estacionamiento.db"
        init_db()

    def tearDown(self):
        database.DB_PATH = self._db_original
        self._tmp.cleanup()

    def test_get_connection_activa_foreign_keys(self):
        conn = get_connection()
        cur = conn.cursor()
        self.assertEqual(cur.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        conn.close()

    def test_reparar_integridad_limpia_pagos_cochera_huerfanos(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO clientes (dni, nombre, activo) VALUES ('60111222', 'Marta', 1)")
        id_cliente = cur.lastrowid
        cur.execute(
            "INSERT INTO espacios (codigo, es_reservado, activo) VALUES ('Z1', 1, 1)"
        )
        id_espacio = cur.lastrowid
        cur.execute(
            "INSERT INTO cochera_contratos "
            "(id_cliente, id_espacio, fecha_vencimiento, monto_mensual, activo) "
            "VALUES (?, ?, '2026-12-31', 18000, 0)",
            (id_cliente, id_espacio),
        )
        id_contrato = cur.lastrowid
        cur.execute(
            "INSERT INTO pagos_cochera (id_contrato, monto, metodo) VALUES (?, 18000, 'Efectivo')",
            (id_contrato,),
        )
        conn.commit()
        conn.close()

        raw = sqlite3.connect(database.DB_PATH)
        raw.execute("PRAGMA foreign_keys = OFF")
        raw.execute("DELETE FROM cochera_contratos WHERE id_contrato = ?", (id_contrato,))
        raw.commit()
        raw.close()

        self.assertEqual(len(database.validar_integridad_db()), 1)

        reparaciones = database.reparar_integridad_db()
        self.assertGreater(
            reparaciones["pagos_cochera_sin_contrato"]
            + reparaciones["pagos_cochera_sin_contrato_post"],
            0,
        )
        self.assertEqual(database.validar_integridad_db(), [])

    def test_init_db_migra_fechas_legacy_de_pagos_cochera_a_hora_local(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM configuracion WHERE clave = 'migracion_pagos_cochera_local_v1'")
        cur.execute("INSERT INTO clientes (dni, nombre, activo) VALUES ('60111223', 'Mario', 1)")
        id_cliente = cur.lastrowid
        cur.execute(
            "INSERT INTO espacios (codigo, es_reservado, activo) VALUES ('Z2', 1, 1)"
        )
        id_espacio = cur.lastrowid
        cur.execute(
            "INSERT INTO cochera_contratos "
            "(id_cliente, id_espacio, fecha_vencimiento, monto_mensual, activo) "
            "VALUES (?, ?, '2026-12-31', 18000, 1)",
            (id_cliente, id_espacio),
        )
        id_contrato = cur.lastrowid
        cur.execute(
            "INSERT INTO pagos_cochera (id_contrato, monto, metodo, fecha_pago) "
            "VALUES (?, 18000, 'Efectivo', '2026-03-27 00:15:00')",
            (id_contrato,),
        )
        conn.commit()
        conn.close()

        offset = datetime.now().astimezone().utcoffset()
        offset_min = int((offset.total_seconds() // 60) if offset else 0)
        esperado = datetime(2026, 3, 27, 0, 15, 0) + timedelta(minutes=offset_min)

        init_db()

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT fecha_pago FROM pagos_cochera WHERE id_contrato = ?",
            (id_contrato,),
        )
        self.assertEqual(
            cur.fetchone()["fecha_pago"],
            esperado.strftime("%Y-%m-%d %H:%M:%S"),
        )
        cur.execute(
            "SELECT valor FROM configuracion WHERE clave = 'migracion_pagos_cochera_local_v1'"
        )
        self.assertEqual(cur.fetchone()["valor"], "1")
        conn.close()

    def test_db_impide_eliminar_vehiculo_con_movimientos(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO clientes (dni, nombre, activo) VALUES ('61111222', 'Luca', 1)")
        id_cliente = cur.lastrowid
        cur.execute(
            "INSERT INTO vehiculos (patente, id_cliente) VALUES ('AAA111', ?)",
            (id_cliente,),
        )
        id_vehiculo = cur.lastrowid
        cur.execute(
            "INSERT INTO espacios (codigo, es_reservado, activo) VALUES ('E20', 0, 1)"
        )
        id_espacio = cur.lastrowid
        cur.execute(
            "INSERT INTO movimientos (id_vehiculo, id_espacio) VALUES (?, ?)",
            (id_vehiculo, id_espacio),
        )
        conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute("DELETE FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
            conn.commit()
        conn.close()

    def test_db_impide_eliminar_contrato_con_pagos(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO clientes (dni, nombre, activo) VALUES ('62111222', 'Nora', 1)")
        id_cliente = cur.lastrowid
        cur.execute(
            "INSERT INTO espacios (codigo, es_reservado, activo) VALUES ('C20', 1, 1)"
        )
        id_espacio = cur.lastrowid
        cur.execute(
            "INSERT INTO cochera_contratos "
            "(id_cliente, id_espacio, fecha_vencimiento, monto_mensual, activo) "
            "VALUES (?, ?, '2026-12-31', 22000, 1)",
            (id_cliente, id_espacio),
        )
        id_contrato = cur.lastrowid
        cur.execute(
            "INSERT INTO pagos_cochera (id_contrato, monto, metodo) VALUES (?, 22000, 'Transferencia')",
            (id_contrato,),
        )
        conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute("DELETE FROM cochera_contratos WHERE id_contrato = ?", (id_contrato,))
            conn.commit()
        conn.close()


class FlujosIntegracionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=_tmp_dir_tests())
        self._db_original = database.DB_PATH
        database.DB_PATH = Path(self._tmp.name) / "test_estacionamiento.db"
        init_db()

    def tearDown(self):
        database.DB_PATH = self._db_original
        self._tmp.cleanup()

    def test_backup_restore_reconcilia_espacios_contrato_activo(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO clientes (dni, nombre, activo) VALUES ('50111222', 'Ana', 1)")
        id_cliente = cur.lastrowid
        cur.execute(
            "INSERT INTO espacios (codigo, es_reservado, id_cliente, activo) VALUES ('C100', 1, NULL, 1)"
        )
        id_espacio = cur.lastrowid
        cur.execute(
            "INSERT INTO cochera_contratos "
            "(id_cliente, id_espacio, fecha_vencimiento, monto_mensual, activo) "
            "VALUES (?, ?, '2026-12-31', 25000, 1)",
            (id_cliente, id_espacio),
        )
        conn.commit()
        conn.close()

        backup_path = crear_backup_db(max_backups=5)
        self.assertIsNotNone(backup_path)
        self.assertTrue(Path(backup_path).exists())

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE cochera_contratos SET activo = 0 WHERE id_espacio = ?", (id_espacio,))
        cur.execute("UPDATE espacios SET id_cliente = NULL WHERE id_espacio = ?", (id_espacio,))
        conn.commit()
        conn.close()

        self.assertTrue(restaurar_backup_db(backup_path))

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id_cliente FROM espacios WHERE id_espacio = ?", (id_espacio,))
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(int(row["id_cliente"] or 0), id_cliente)

    def test_tarifas_por_tipo_devuelven_valor_correcto(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE tarifas SET activa = 0 WHERE activa = 1")
        cur.execute(
            "INSERT INTO tarifas ("
            "precio_hora, precio_hora_auto, precio_hora_moto, "
            "precio_hora_camioneta, precio_mensual, activa"
            ") VALUES (?, ?, ?, ?, ?, 1)",
            (1000, 1000, 600, 1500, 20000),
        )
        conn.commit()
        cur.execute(
            "SELECT precio_hora, precio_hora_auto, precio_hora_moto, precio_hora_camioneta "
            "FROM tarifas WHERE activa = 1 ORDER BY fecha_desde DESC LIMIT 1"
        )
        row = cur.fetchone()
        conn.close()

        self.assertEqual(app_main._tarifa_hora_desde_row(row, "AUTO"), 1000.0)
        self.assertEqual(app_main._tarifa_hora_desde_row(row, "MOTO"), 600.0)
        self.assertEqual(app_main._tarifa_hora_desde_row(row, "CAMIONETA"), 1500.0)

    def test_whatsapp_admite_variable_cuota_en_plantilla(self):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (
                "wa_recordatorio_template",
                "Hola {nombre}. Vence: {vencimiento}. Nueva cuota: {cuota}.",
            ),
        )
        conn.commit()
        conn.close()

        mensaje = app_main._render_mensaje_whatsapp(
            "Lucas",
            "26/03/2026 (vence hoy)",
            "$ 10000.00",
            modelo="Cronos",
            patente="AAA111",
        )
        self.assertIn("Nueva cuota: $ 10000.00", mensaje)


if __name__ == "__main__":
    unittest.main()
