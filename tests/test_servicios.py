r"""Regresiones de servicios. Cada prueba usa exclusivamente una base temporal.

Ejecutar: .venv\Scripts\python.exe -m unittest discover -s tests -v
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import os
from tempfile import TemporaryDirectory
from threading import Barrier
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import database
from servicios import caja, cobro, contratos, estacionamiento, reportes, validaciones


class CalculoEstadiaTests(unittest.TestCase):
    def test_limites_tolerancia_actual_de_quince_minutos(self):
        casos = ((0, 0), (899, 0), (900, 0), (901, 1), (3599, 1),
                 (3600, 1), (4500, 1), (4501, 2), (7200, 2), (8100, 2), (8101, 3))
        for segundos, horas in casos:
            with self.subTest(segundos=segundos):
                self.assertEqual(cobro.horas_cobradas_con_tolerancia(segundos), horas)

    def test_redondeo_moneda_y_tarifa_cero(self):
        ingreso = datetime(2026, 1, 1, 22, 0)
        self.assertEqual(cobro.calcular_total_estadia(ingreso, ingreso + timedelta(hours=2), 1000.125), (2, 2000.25))
        self.assertEqual(cobro.calcular_total_estadia(ingreso, ingreso + timedelta(hours=2), 0), (2, 0))

    def test_no_importes_negativos_nan_inf_o_tolerancia_invalida(self):
        for valor in (-1, float("nan"), float("inf"), "invalido"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                cobro.horas_cobradas_con_tolerancia(valor)
        for tolerancia in (-1, 60, float("nan"), float("inf"), None):
            with self.subTest(tolerancia=tolerancia), self.assertRaises(ValueError):
                cobro.horas_cobradas_con_tolerancia(3600, tolerancia)
        for tarifa in (-1, float("nan"), float("inf"), None):
            with self.subTest(tarifa=tarifa), self.assertRaises(ValueError):
                cobro.calcular_total_estadia(datetime(2026, 1, 1), datetime(2026, 1, 2), tarifa)

    def test_fechas_invalidas_no_producen_cobro_gratis(self):
        ingreso = datetime(2026, 1, 2)
        for salida in (datetime(2026, 1, 1), ingreso.replace(tzinfo=timezone.utc), None):
            with self.subTest(salida=salida), self.assertRaises(ValueError):
                cobro.calcular_total_estadia(ingreso, salida, 1500)

    def test_duracion_con_zona_horaria_y_desborde(self):
        ingreso = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(cobro.calcular_total_estadia(ingreso, ingreso + timedelta(hours=1), 1500), (1, 1500))
        with self.assertRaises(ValueError):
            cobro.calcular_total_estadia(ingreso, ingreso + timedelta(hours=24), 1e308)

    def test_fecha_db_y_patentes(self):
        self.assertEqual(cobro.parse_fecha_db("2026-01-02 03:04:05"), datetime(2026, 1, 2, 3, 4, 5))
        self.assertIsNone(cobro.parse_fecha_db("fecha corrupta"))
        self.assertEqual(validaciones.normalizar_patente(" ab-123 cd "), "AB123CD")
        for metodo in (None, "", "   ", "xxx"):
            with self.assertRaises(ValueError):
                validaciones.normalizar_metodo_pago(metodo)
        self.assertEqual(validaciones.normalizar_metodo_pago(" efectivo "), "Efectivo")
        self.assertEqual(validaciones.normalizar_metodo_pago("qr"), "QR")


class FechasContratoTests(unittest.TestCase):
    def test_fin_mes_y_anio_bisiesto(self):
        casos = (("2026-01-31", 1, "2026-02-28"), ("2024-01-31", 1, "2024-02-29"),
                 ("2024-02-29", 12, "2025-02-28"), ("2026-12-31", 1, "2027-01-31"))
        for inicio, meses, esperado in casos:
            with self.subTest(inicio=inicio):
                self.assertEqual(contratos.calcular_nueva_fecha_vencimiento(inicio, meses, hoy="2020-01-01"), esperado)

    def test_hoy_datetime_no_se_compara_con_date(self):
        self.assertEqual(contratos.calcular_nueva_fecha_vencimiento(date(2026, 1, 31), 1,
                         hoy=datetime(2026, 1, 20, 12)), "2026-02-28")
        self.assertEqual(contratos.calcular_nueva_fecha_vencimiento(datetime(2026, 1, 1), 1,
                         hoy=datetime(2026, 1, 31, 12)), "2026-02-28")

    def test_vencido_renueva_desde_hoy_y_meses_deben_ser_enteros(self):
        self.assertEqual(contratos.calcular_nueva_fecha_vencimiento("2020-01-01", 2, hoy="2026-01-31"), "2026-03-31")
        for meses in (0, -1, 1.5, "1.5", None, float("inf"), float("nan")):
            with self.subTest(meses=meses), self.assertRaises(ValueError):
                contratos.calcular_nueva_fecha_vencimiento("2026-01-01", meses, hoy="2026-01-01")


class BaseDatosTemporalMixin:
    def setUp(self):
        self.original_path = database.DB_PATH
        self.temp = TemporaryDirectory(prefix="taller-servicios-qa-")
        self.addCleanup(self.restaurar_base)
        database.DB_PATH = Path(self.temp.name) / "estacionamiento.db"
        database.init_db()
        self.vencimiento = (date.today() + timedelta(days=30)).isoformat()
        with closing(database.get_connection()) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO clientes (dni,nombre,activo) VALUES ('99000001','Cliente de prueba',1)")
            self.cliente = cur.lastrowid
            cur.execute("INSERT INTO clientes (dni,nombre,activo) VALUES ('99000002','Otro cliente',1)")
            self.otro_cliente = cur.lastrowid
            cur.execute("INSERT INTO vehiculos (patente,id_cliente,tipo_vehiculo) VALUES ('AB123CD',?,'AUTO')", (self.cliente,))
            self.vehiculo = cur.lastrowid
            cur.execute("INSERT INTO vehiculos (patente,id_cliente,tipo_vehiculo) VALUES ('ZZ999ZZ',?,'CAMIONETA')", (self.cliente,))
            self.segundo_vehiculo = cur.lastrowid
            cur.execute("INSERT INTO espacios (codigo,es_reservado,activo) VALUES ('C01',1,1)")
            self.cochera = cur.lastrowid
            for codigo in ("E01", "E02", "E03"):
                cur.execute("INSERT INTO espacios (codigo,es_reservado,activo) VALUES (?,0,1)", (codigo,))
            cur.execute("INSERT INTO tarifas (precio_hora,precio_hora_auto,precio_hora_moto,precio_hora_camioneta,"
                        "precio_mensual,activa) VALUES (1500,1500,1000,2000,48000,1)")
            conn.commit()

    def restaurar_base(self):
        database.DB_PATH = self.original_path
        self.temp.cleanup()

    def ejecutar(self, sql, params=()):
        with closing(database.get_connection()) as conn:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid

    def filas(self, sql, params=()):
        with closing(database.get_connection()) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def contrato(self, vehiculo=None, activo=0, historial=0, vencimiento=None):
        return self.ejecutar("INSERT INTO cochera_contratos (id_cliente,id_vehiculo,id_espacio,fecha_vencimiento,"
                             "monto_mensual,activo,en_historial) VALUES (?,?,?,?,48000,?,?)",
                             (self.cliente, vehiculo or self.vehiculo, self.cochera,
                              vencimiento or self.vencimiento, activo, historial))


class ServiciosDBTests(BaseDatosTemporalMixin, unittest.TestCase):
    def test_primer_pago_activa_y_no_modifica_vencimiento(self):
        contrato = self.contrato()
        resultado = contratos.registrar_primer_pago_contrato(contrato, 48000, "efectivo",
                                                           fecha_pago="2026-01-02 23:45:00")
        self.assertEqual(resultado["fecha_vencimiento"], self.vencimiento)
        row = self.filas("SELECT * FROM cochera_contratos WHERE id_contrato=?", (contrato,))[0]
        self.assertEqual(row["activo"], 1)
        self.assertEqual(self.filas("SELECT id_cliente FROM espacios WHERE id_espacio=?", (self.cochera,))[0]["id_cliente"], self.cliente)
        pago = self.filas("SELECT * FROM pagos_cochera")[0]
        self.assertEqual((pago["monto"], pago["metodo"], pago["fecha_pago"]), (48000, "Efectivo", "2026-01-02 23:45:00"))
        with self.assertRaises(ValueError):
            contratos.registrar_primer_pago_contrato(contrato, 48000, "Efectivo")
        self.assertEqual(len(self.filas("SELECT * FROM pagos_cochera")), 1)

    def test_primer_pago_rechaza_importes_y_metodos_invalidos(self):
        contrato = self.contrato()
        for monto in (0, -1, float("nan"), float("inf"), None):
            with self.subTest(monto=monto), self.assertRaises(ValueError):
                contratos.registrar_primer_pago_contrato(contrato, monto, "Efectivo")
        for metodo in (None, "", "xxx"):
            with self.subTest(metodo=metodo), self.assertRaises(ValueError):
                contratos.registrar_primer_pago_contrato(contrato, 48000, metodo)
        self.assertEqual(self.filas("SELECT * FROM pagos_cochera"), [])
        self.assertEqual(self.filas("SELECT activo FROM cochera_contratos")[0]["activo"], 0)

    def test_primer_pago_rechaza_espacio_inactivo(self):
        self.ejecutar("UPDATE espacios SET activo=0 WHERE id_espacio=?", (self.cochera,))
        # La base nueva tambien impide crear este estado. Para probar el guard
        # del servicio se simula un contrato heredado, solo en esta DB temporal.
        with self.assertRaises(sqlite3.IntegrityError):
            self.contrato()
        self.ejecutar("DROP TRIGGER IF EXISTS trg_contrato_espacio_integridad_insert_v2")
        contrato = self.contrato()
        with self.assertRaisesRegex(ValueError, "desactivado"):
            contratos.registrar_primer_pago_contrato(contrato, 48000, "Efectivo")
        self.assertEqual(self.filas("SELECT * FROM pagos_cochera"), [])

    def test_primer_pago_rechaza_historial_cliente_inactivo_y_vencido(self):
        contrato = self.contrato(historial=1)
        with self.assertRaisesRegex(ValueError, "historial"):
            contratos.registrar_primer_pago_contrato(contrato, 48000, "Efectivo")
        self.ejecutar("UPDATE cochera_contratos SET en_historial=0 WHERE id_contrato=?", (contrato,))
        self.ejecutar("UPDATE clientes SET activo=0 WHERE id_cliente=?", (self.cliente,))
        with self.assertRaisesRegex(ValueError, "desactivado"):
            contratos.registrar_primer_pago_contrato(contrato, 48000, "Efectivo")
        self.ejecutar("UPDATE clientes SET activo=1 WHERE id_cliente=?", (self.cliente,))
        self.ejecutar("UPDATE cochera_contratos SET fecha_vencimiento='2020-01-01' WHERE id_contrato=?", (contrato,))
        with self.assertRaisesRegex(ValueError, "vencido"):
            contratos.registrar_primer_pago_contrato(contrato, 48000, "Efectivo")
        self.assertEqual(self.filas("SELECT * FROM pagos_cochera"), [])

    def test_pago_abortado_revierte_activacion_y_asignacion(self):
        contrato = self.contrato()
        self.ejecutar("UPDATE cochera_contratos SET id_vehiculo=NULL WHERE id_contrato=?", (contrato,))
        self.ejecutar("CREATE TRIGGER qa_abort_pago BEFORE INSERT ON pagos_cochera BEGIN SELECT RAISE(ABORT,'qa_abort'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            contratos.registrar_primer_pago_contrato(contrato, 48000, "Efectivo")
        row = self.filas("SELECT activo,id_vehiculo FROM cochera_contratos")[0]
        self.assertEqual(row, {"activo": 0, "id_vehiculo": None})
        self.assertIsNone(self.filas("SELECT id_cliente FROM espacios WHERE id_espacio=?", (self.cochera,))[0]["id_cliente"])
        self.assertEqual(self.filas("SELECT * FROM pagos_cochera"), [])

    def test_activaciones_simultaneas_no_generan_pago_doble(self):
        contrato = self.contrato()
        barrera = Barrier(2)
        def activar():
            barrera.wait(timeout=5)
            try:
                contratos.registrar_primer_pago_contrato(contrato, 48000, "Efectivo")
                return "ok"
            except ValueError:
                return "rechazado"
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(lambda _: activar(), range(2)))
        self.assertCountEqual(resultados, ["ok", "rechazado"])
        self.assertEqual(len(self.filas("SELECT * FROM pagos_cochera")), 1)

    def test_renovar_extiende_desde_vencimiento_y_no_desde_pago(self):
        contrato = self.contrato(activo=1, vencimiento="2026-01-31")
        self.assertEqual(contratos.registrar_renovacion_contrato(contrato, 1, 48000, "Transferencia",
                         hoy=datetime(2026, 1, 20, 12)), "2026-02-28")
        self.assertEqual(contratos.registrar_renovacion_contrato(contrato, 1, 48000, "Tarjeta", hoy="2026-03-31"), "2026-04-30")
        self.assertEqual(len(self.filas("SELECT * FROM pagos_cochera")), 2)

    def test_renovaciones_simultaneas_no_pierden_meses(self):
        contrato = self.contrato(activo=1, vencimiento="2026-01-15")
        barrera = Barrier(2)
        def renovar():
            barrera.wait(timeout=5)
            return contratos.registrar_renovacion_contrato(contrato, 1, 48000, "Efectivo", hoy="2026-01-01")
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(lambda _: renovar(), range(2)))
        self.assertCountEqual(resultados, ["2026-02-15", "2026-03-15"])
        self.assertEqual(len(self.filas("SELECT * FROM pagos_cochera")), 2)

    def test_reactivar_historial_deja_pendiente_primer_pago(self):
        contrato = self.contrato(historial=1, vencimiento="2020-01-01")
        resultado = contratos.reactivar_contrato_desde_historial(contrato, hoy=datetime(2026, 1, 31))
        self.assertEqual(resultado, {"fecha_vencimiento": "2026-02-28", "vencimiento_ajustado": True})
        row = self.filas("SELECT activo,en_historial FROM cochera_contratos")[0]
        self.assertEqual(row, {"activo": 0, "en_historial": 0})
        self.assertEqual(self.filas("SELECT * FROM pagos_cochera"), [])

    def test_reportes_usando_patente_del_contrato_no_la_primera_del_cliente(self):
        contrato = self.contrato(vehiculo=self.segundo_vehiculo)
        self.ejecutar("INSERT INTO pagos_cochera (id_contrato,monto,metodo,fecha_pago) VALUES (?,48000,'Efectivo','2026-01-31 23:45:00')", (contrato,))
        mensual = reportes.consultar_pagos_mensuales_rango("2026-01-01", "2026-01-31")
        self.assertEqual(mensual[0]["patente"], "ZZ999ZZ")
        for rows in (reportes.consultar_detalle("2026-01"), reportes.consultar_detalle_rango("2026-01-01", "2026-01-31")):
            self.assertEqual(rows[0]["patente"], "ZZ999ZZ")
            self.assertEqual(rows[0]["tipo_vehiculo"], "CAMIONETA")
        self.assertEqual(reportes.consultar_resumen("2026-01"), (48000, 0, 48000))
        self.assertEqual(caja.consultar_totales_dia("2026-01-31"), (48000, 0, 48000))
        self.assertEqual(caja.consultar_totales_dia("2026-02-01"), (0, 0, 0))

    def test_ingreso_normaliza_patente_y_congela_tarifa(self):
        espacio = estacionamiento.ingresar_vehiculo("ab 123 cd")
        row = self.filas("SELECT * FROM movimientos")[0]
        self.assertEqual(row["id_espacio"], espacio)
        self.assertEqual(row["tarifa_hora_aplicada"], 1500)
        self.assertLess(abs((datetime.now() - datetime.fromisoformat(row["fecha_ingreso"])).total_seconds()), 10)
        with self.assertRaises(ValueError):
            estacionamiento.ingresar_vehiculo("AB-123-CD")
        self.assertEqual(len(self.filas("SELECT * FROM movimientos")), 1)
        self.assertEqual(len(self.filas("SELECT * FROM vehiculos WHERE patente='AB123CD'")), 1)

    def test_ingreso_sin_tarifa_revierte_nueva_patente(self):
        self.ejecutar("UPDATE tarifas SET activa=0")
        with self.assertRaises(ValueError):
            estacionamiento.ingresar_vehiculo("DE456FG")
        self.assertEqual(self.filas("SELECT * FROM vehiculos WHERE patente='DE456FG'"), [])
        self.assertEqual(self.filas("SELECT * FROM movimientos"), [])

    def test_ingresos_simultaneos_usando_espacios_distintos(self):
        barrera = Barrier(2)
        def ingresar(patente):
            barrera.wait(timeout=5)
            return estacionamiento.ingresar_vehiculo(patente)
        with ThreadPoolExecutor(max_workers=2) as pool:
            espacios = list(pool.map(ingresar, ("DE456FG", "HI789JK")))
        self.assertEqual(len(set(espacios)), 2)
        self.assertEqual(len(self.filas("SELECT * FROM movimientos WHERE fecha_salida IS NULL")), 2)

    def test_regla_actual_cliente_con_cochera_no_ingresa_por_hora(self):
        self.contrato(activo=1)
        with self.assertRaisesRegex(ValueError, "cochera activa"):
            estacionamiento.ingresar_vehiculo("AB123CD")
        self.assertIsNone(estacionamiento.buscar_espacio_disponible(self.cliente))
        self.assertEqual(self.filas("SELECT * FROM movimientos"), [])

    def test_salida_usa_snapshot_y_registra_pago_local(self):
        estacionamiento.ingresar_vehiculo("AB123CD")
        self.ejecutar("UPDATE movimientos SET fecha_ingreso='2026-01-31 21:00:00'")
        self.ejecutar("UPDATE tarifas SET precio_hora=9000,precio_hora_auto=9000")
        with patch.object(estacionamiento, "datetime") as reloj:
            reloj.now.return_value = datetime(2026, 1, 31, 23, 15)
            total = estacionamiento.salir_vehiculo("ab 123 cd", "qr")
        self.assertEqual(total, 3000)
        mov = self.filas("SELECT * FROM movimientos")[0]
        pago = self.filas("SELECT * FROM pagos")[0]
        self.assertEqual(mov["fecha_salida"], "2026-01-31 23:15:00")
        self.assertEqual((pago["monto"], pago["metodo"], pago["fecha_pago"]), (3000, "QR", "2026-01-31 23:15:00"))
        self.assertEqual(caja.consultar_totales_dia("2026-01-31"), (0, 3000, 3000))
        self.assertEqual(caja.consultar_totales_dia("2026-02-01"), (0, 0, 0))
        with self.assertRaises(ValueError):
            estacionamiento.salir_vehiculo("AB123CD")
        self.assertEqual(len(self.filas("SELECT * FROM pagos")), 1)

    def test_tarifa_moto_y_camioneta(self):
        estacionamiento.ingresar_vehiculo("123ABC")
        estacionamiento.ingresar_vehiculo("ZZ999ZZ")
        self.assertCountEqual([row["tarifa_hora_aplicada"] for row in self.filas("SELECT * FROM movimientos")], [1000, 2000])

    def test_pago_abortado_revierte_salida(self):
        estacionamiento.ingresar_vehiculo("AB123CD")
        self.ejecutar("CREATE TRIGGER qa_abort_pago BEFORE INSERT ON pagos BEGIN SELECT RAISE(ABORT,'qa_abort'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            estacionamiento.salir_vehiculo("AB123CD")
        self.assertIsNone(self.filas("SELECT fecha_salida FROM movimientos")[0]["fecha_salida"])
        self.assertEqual(self.filas("SELECT * FROM pagos"), [])

    def test_salida_con_fecha_danada_no_registra_cobro(self):
        estacionamiento.ingresar_vehiculo("AB123CD")
        self.ejecutar("UPDATE movimientos SET fecha_ingreso='corrupta'")
        with self.assertRaisesRegex(ValueError, "fecha de ingreso"):
            estacionamiento.salir_vehiculo("AB123CD")
        self.assertIsNone(self.filas("SELECT fecha_salida FROM movimientos")[0]["fecha_salida"])
        self.assertEqual(self.filas("SELECT * FROM pagos"), [])

    def test_caja_coherente_y_reemplazo_atomico(self):
        detalles = [{"metodo": "Efectivo", "total_esperado": 3000, "total_contado": 2900, "diferencia": -100}]
        self.assertTrue(caja.guardar_cierre_caja("2026-01-31", 3000, 2900, -100, "Diferencia de prueba", detalle_metodos=detalles))
        cierre = caja.obtener_cierre_caja("2026-01-31")
        self.assertEqual(cierre["diferencia"], -100)
        self.assertLess(abs((datetime.now() - datetime.fromisoformat(cierre["fecha_cierre"])).total_seconds()), 10)
        self.ejecutar("CREATE TRIGGER qa_abort_cierre BEFORE INSERT ON cierres_caja_metodos BEGIN SELECT RAISE(ABORT,'qa_abort'); END")
        nuevo = [{"metodo": "Tarjeta", "total_esperado": 3000, "total_contado": 3000, "diferencia": 0}]
        self.assertFalse(caja.guardar_cierre_caja("2026-01-31", 3000, 3000, 0, detalle_metodos=nuevo))
        self.assertEqual(caja.obtener_cierre_caja("2026-01-31")["total_contado"], 2900)
        self.assertIn("Efectivo", caja.obtener_cierre_caja_metodos("2026-01-31"))
        self.assertTrue(caja.eliminar_cierre_caja("2026-01-31"))
        self.assertIsNone(caja.obtener_cierre_caja("2026-01-31"))
        self.assertEqual(caja.obtener_cierre_caja_metodos("2026-01-31"), {})

    def test_caja_rechaza_importes_invalidos_y_diferencias_inconsistentes(self):
        for esperado, contado, diferencia in ((float("inf"), 1, 0), (1, float("nan"), 0),
                                               (-1, 0, 1), (100, 80, 0), (100, 80, float("nan"))):
            with self.subTest(esperado=esperado, contado=contado):
                self.assertFalse(caja.guardar_cierre_caja("2026-01-31", esperado, contado, diferencia))
        detalle = [{"metodo": "Efectivo", "total_esperado": 100, "total_contado": 80, "diferencia": 0}]
        self.assertFalse(caja.guardar_cierre_caja("2026-01-31", 100, 80, -20, detalle_metodos=detalle))
        self.assertIsNone(caja.obtener_cierre_caja("2026-01-31"))

    def test_caja_rechaza_metodos_duplicados_y_sumas_inconsistentes(self):
        fila = {"metodo": "Efectivo", "total_esperado": 100, "total_contado": 100, "diferencia": 0}
        self.assertFalse(caja.guardar_cierre_caja("2026-01-31", 200, 200, 0, detalle_metodos=[fila, fila]))
        self.assertFalse(caja.guardar_cierre_caja("2026-01-31", 200, 200, 0, detalle_metodos=[fila]))
        self.assertFalse(caja.guardar_cierre_caja("fecha invalida", 0, 0, 0))
        self.assertEqual(self.filas("SELECT * FROM cierres_caja"), [])


class AccionesMainMixin(BaseDatosTemporalMixin):
    def setUp(self):
        super().setUp()
        import main
        self.main = main
        self.mocks = []
        for owner, atributo, kwargs in (
                (main.QMessageBox, "warning", {}),
                (main.QMessageBox, "information", {}),
                (main.QMessageBox, "question", {"return_value": main.QMessageBox.Yes}),
                (main, "_auditar", {}), (main, "_mostrar_error", {})):
            parche = patch.object(owner, atributo, **kwargs)
            self.mocks.append(parche)
            setattr(self, atributo.lstrip("_") + "_mock", parche.start())

    def tearDown(self):
        for parche in reversed(self.mocks):
            parche.stop()
        super().tearDown()


class OperacionMapaTests(AccionesMainMixin, unittest.TestCase):
    """Prueba el metodo real del mapa sin ventanas, sobre la misma DB temporal."""

    def setUp(self):
        super().setUp()
        self.item = SimpleNamespace(codigo="C01", codigo_original="C01")
        self.dialog = SimpleNamespace(_editable=True,
                                      _abrir_salida_desde_mapa=unittest.mock.Mock(return_value=False),
                                      _actualizar_item_por_codigo=unittest.mock.Mock())

    def desocupar(self):
        self.main.MapaCocheraDialog._desocupar_desde_mapa(self.dialog, self.item)

    def test_mapa_movimiento_sin_parent_no_cierra_ni_cobra(self):
        espacio = self.filas("SELECT id_espacio FROM espacios WHERE codigo='E01'")[0]["id_espacio"]
        self.ejecutar("INSERT INTO movimientos (id_vehiculo,id_espacio,fecha_ingreso,tarifa_hora_aplicada) "
                     "VALUES (?,?,'2026-01-31 12:00:00',1500)", (self.vehiculo, espacio))
        self.item.codigo = self.item.codigo_original = "E01"
        self.desocupar()
        self.dialog._abrir_salida_desde_mapa.assert_called_once()
        self.assertIsNone(self.filas("SELECT fecha_salida FROM movimientos")[0]["fecha_salida"])
        self.assertEqual(self.filas("SELECT * FROM pagos"), [])
        self.question_mock.assert_not_called()
        self.warning_mock.assert_called_once()

    def test_mapa_movimiento_con_ruta_solo_abre_salida(self):
        espacio = self.filas("SELECT id_espacio FROM espacios WHERE codigo='E01'")[0]["id_espacio"]
        self.ejecutar("INSERT INTO movimientos (id_vehiculo,id_espacio,fecha_ingreso) VALUES (?,?,'2026-01-31 12:00:00')",
                     (self.vehiculo, espacio))
        self.item.codigo = self.item.codigo_original = "E01"
        self.dialog._abrir_salida_desde_mapa.return_value = True
        self.desocupar()
        self.assertIsNone(self.filas("SELECT fecha_salida FROM movimientos")[0]["fecha_salida"])
        self.assertEqual(self.filas("SELECT * FROM pagos"), [])
        self.warning_mock.assert_not_called()
        self.question_mock.assert_not_called()

    def test_mapa_contrato_activo_no_da_de_baja(self):
        self.contrato(activo=1)
        self.ejecutar("UPDATE espacios SET id_cliente=? WHERE id_espacio=?", (self.cliente, self.cochera))
        self.desocupar()
        self.assertEqual(self.filas("SELECT activo FROM cochera_contratos")[0]["activo"], 1)
        self.assertEqual(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"], self.cliente)
        self.question_mock.assert_not_called()
        self.warning_mock.assert_called_once()

    def test_mapa_operador_no_quita_cliente_asignado(self):
        self.ejecutar("UPDATE espacios SET id_cliente=? WHERE id_espacio=?", (self.cliente, self.cochera))
        self.dialog._editable = False
        self.desocupar()
        self.assertEqual(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"], self.cliente)
        self.question_mock.assert_not_called()
        self.warning_mock.assert_called_once()

    def test_mapa_duenio_quita_solo_asignacion_sin_borrar_cliente_vehiculos(self):
        self.ejecutar("UPDATE espacios SET id_cliente=? WHERE id_espacio=?", (self.cliente, self.cochera))
        self.desocupar()
        self.assertIsNone(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"])
        self.assertEqual(len(self.filas("SELECT * FROM clientes")), 2)
        self.assertEqual(len(self.filas("SELECT * FROM vehiculos")), 2)
        self.question_mock.assert_called_once()
        self.dialog._actualizar_item_por_codigo.assert_called_once_with(self.item)

    def test_mapa_confirmacion_cancelada_no_modifica(self):
        self.ejecutar("UPDATE espacios SET id_cliente=? WHERE id_espacio=?", (self.cliente, self.cochera))
        self.question_mock.return_value = self.main.QMessageBox.No
        self.desocupar()
        self.assertEqual(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"], self.cliente)

    def test_mapa_revalida_contrato_creado_mientras_confirmaban(self):
        self.ejecutar("UPDATE espacios SET id_cliente=? WHERE id_espacio=?", (self.cliente, self.cochera))
        def confirmar(*_args):
            self.contrato(activo=1)
            return self.main.QMessageBox.Yes
        self.question_mock.side_effect = confirmar
        self.desocupar()
        self.assertEqual(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"], self.cliente)
        self.assertEqual(self.filas("SELECT activo FROM cochera_contratos")[0]["activo"], 1)
        self.warning_mock.assert_called_once()
        self.dialog._actualizar_item_por_codigo.assert_not_called()

    def test_mapa_nuevo_o_renombrado_debe_guardarse_antes(self):
        for original in (None, "OTRO"):
            self.item.codigo_original = original
            self.main.MapaCocheraDialog._desocupar_desde_mapa(self.dialog, self.item)
            self.main.MapaCocheraDialog._abrir_registro_hora(self.dialog, self.item)
            self.assertFalse(self.main.MapaCocheraDialog._abrir_salida_desde_mapa(self.dialog, self.item, {}))
        self.assertEqual(self.warning_mock.call_count, 6)
        self.question_mock.assert_not_called()


class ContratosClientesTests(AccionesMainMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        for atributo, kwargs in (("_antirebote_iniciar", {"return_value": True}), ("_antirebote_finalizar", {})):
            parche = patch.object(self.main, atributo, **kwargs)
            self.mocks.append(parche)
            parche.start()

    def dialogo_contrato(self, contrato, espacio=None):
        return SimpleNamespace(rol="DUENO", _selected_ids=lambda: (contrato, espacio or self.cochera),
                               _validar_cliente_activo_contrato=lambda *_: True,
                               _actualizar_acciones_pago=unittest.mock.Mock(),
                               _cargar=unittest.mock.Mock())

    def dialogo_cliente(self, rol="DUENO"):
        return SimpleNamespace(rol=rol, _selected_cliente_id=lambda: self.cliente,
                               _validar_cliente_activo_seleccionado=lambda *_: True,
                               input_nombre=SimpleNamespace(text=lambda: "Cliente QA"),
                               input_dni=SimpleNamespace(text=lambda: "99000001"),
                               _cargar=unittest.mock.Mock(), _limpiar_form=unittest.mock.Mock())

    def contrato_de_otro_cliente(self):
        vehiculo = self.ejecutar("INSERT INTO vehiculos (patente,id_cliente) VALUES ('GH456IJ',?)", (self.otro_cliente,))
        contrato = self.ejecutar("INSERT INTO cochera_contratos (id_cliente,id_vehiculo,id_espacio,fecha_vencimiento,"
                                "monto_mensual,activo) VALUES (?,?,?,?,48000,1)",
                                (self.otro_cliente, vehiculo, self.cochera, self.vencimiento))
        self.ejecutar("UPDATE espacios SET id_cliente=? WHERE id_espacio=?", (self.otro_cliente, self.cochera))
        return contrato

    def test_baja_lee_lugar_actual_no_id_stale_de_ui(self):
        contrato = self.contrato(activo=1)
        self.ejecutar("UPDATE espacios SET id_cliente=? WHERE id_espacio=?", (self.cliente, self.cochera))
        espacio_equivocado = self.filas("SELECT id_espacio FROM espacios WHERE codigo='E03'")[0]["id_espacio"]
        dialog = self.dialogo_contrato(contrato, espacio_equivocado)
        self.main.ContratosDialog._baja(dialog)
        self.assertEqual(self.filas("SELECT activo,en_historial FROM cochera_contratos")[0], {"activo": 0, "en_historial": 1})
        self.assertIsNone(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"])
        dialog._cargar.assert_called_once()

    def test_baja_historica_obsoleta_no_libera_lugar_de_otro_cliente(self):
        antiguo = self.contrato(historial=1)
        nuevo = self.contrato_de_otro_cliente()
        dialog = self.dialogo_contrato(antiguo)
        self.main.ContratosDialog._baja(dialog)
        self.assertEqual(self.filas("SELECT activo FROM cochera_contratos WHERE id_contrato=?", (nuevo,))[0]["activo"], 1)
        self.assertEqual(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"], self.otro_cliente)
        dialog._cargar.assert_not_called()
        self.warning_mock.assert_called_once()



    def test_baja_revalida_cliente_desactivado_durante_confirmacion(self):
        contrato = self.contrato(activo=1)
        def confirmar(*_args):
            self.ejecutar("UPDATE clientes SET activo=0 WHERE id_cliente=?", (self.cliente,))
            return self.main.QMessageBox.Yes
        self.question_mock.side_effect = confirmar
        self.main.ContratosDialog._baja(self.dialogo_contrato(contrato))
        self.assertEqual(self.filas("SELECT activo FROM cochera_contratos")[0]["activo"], 1)
        self.warning_mock.assert_called_once()

    def test_eliminar_cliente_sin_historial_quita_solo_sus_vehiculos(self):
        self.ejecutar("UPDATE espacios SET id_cliente=? WHERE id_espacio=?", (self.cliente, self.cochera))
        dialog = self.dialogo_cliente()
        self.main.ClientesDialog._eliminar_cliente(dialog)
        self.assertEqual(self.filas("SELECT * FROM clientes WHERE id_cliente=?", (self.cliente,)), [])
        self.assertEqual(len(self.filas("SELECT * FROM clientes")), 1)
        self.assertEqual(self.filas("SELECT * FROM vehiculos WHERE id_cliente=?", (self.cliente,)), [])
        self.assertIsNone(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"])
        dialog._limpiar_form.assert_called_once()

    def test_eliminar_cliente_operador_no_puede_invocar_handler(self):
        self.main.ClientesDialog._eliminar_cliente(self.dialogo_cliente("OPERADOR"))
        self.assertEqual(len(self.filas("SELECT * FROM clientes")), 2)
        self.question_mock.assert_not_called()
        self.warning_mock.assert_called_once()

    def test_eliminar_cliente_con_historial_se_rechaza(self):
        self.contrato(historial=1)
        self.main.ClientesDialog._eliminar_cliente(self.dialogo_cliente())
        self.assertEqual(len(self.filas("SELECT * FROM clientes")), 2)
        self.assertEqual(len(self.filas("SELECT * FROM vehiculos")), 2)
        self.assertEqual(len(self.filas("SELECT * FROM cochera_contratos")), 1)
        self.warning_mock.assert_called_once()

    def test_eliminar_cliente_revalida_historial_creado_durante_confirmacion(self):
        def confirmar(*_args):
            self.contrato()
            return self.main.QMessageBox.Yes
        self.question_mock.side_effect = confirmar
        self.main.ClientesDialog._eliminar_cliente(self.dialogo_cliente())
        self.assertEqual(len(self.filas("SELECT * FROM clientes")), 2)
        self.warning_mock.assert_called_once()

    def test_eliminar_cliente_consulta_fallida_no_se_interpreta_como_sin_deps(self):
        conexion = unittest.mock.Mock()
        conexion.cursor.return_value.execute.side_effect = sqlite3.OperationalError("Fallo de prueba")
        with patch.object(self.main, "get_connection", return_value=conexion):
            self.main.ClientesDialog._eliminar_cliente(self.dialogo_cliente())
        conexion.commit.assert_not_called()
        conexion.close.assert_called_once()
        self.mostrar_error_mock.assert_called_once()
        self.assertEqual(len(self.filas("SELECT * FROM clientes")), 2)

    def test_eliminar_historial_antiguo_sin_pagos_no_libera_nuevo_cliente(self):
        antiguo = self.contrato(historial=1)
        nuevo = self.contrato_de_otro_cliente()
        resultado = self.main._eliminar_contrato_definitivo(antiguo)
        self.assertEqual(resultado, {"ok": True, "pagos": 0, "id_espacio": self.cochera})
        self.assertEqual(self.filas("SELECT * FROM cochera_contratos WHERE id_contrato=?", (antiguo,)), [])
        self.assertEqual(self.filas("SELECT activo FROM cochera_contratos WHERE id_contrato=?", (nuevo,))[0]["activo"], 1)
        self.assertEqual(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"], self.otro_cliente)

    def test_eliminar_con_pagos_conserva_contrato_pago_y_nuevo_cliente(self):
        antiguo = self.contrato(historial=1)
        nuevo = self.contrato_de_otro_cliente()
        self.ejecutar("INSERT INTO pagos_cochera (id_contrato,monto,metodo) VALUES (?,48000,'Efectivo')", (antiguo,))
        with self.assertRaisesRegex(ValueError, "pagos registrados"):
            self.main._eliminar_contrato_definitivo(antiguo)
        self.assertEqual(len(self.filas("SELECT * FROM cochera_contratos")), 2)
        self.assertEqual(len(self.filas("SELECT * FROM pagos_cochera")), 1)
        self.assertEqual(self.filas("SELECT activo FROM cochera_contratos WHERE id_contrato=?", (nuevo,))[0]["activo"], 1)
        self.assertEqual(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"], self.otro_cliente)

    def test_eliminar_contrato_activo_o_inexistente(self):
        contrato = self.contrato(activo=1)
        with self.assertRaisesRegex(ValueError, "activo"):
            self.main._eliminar_contrato_definitivo(contrato)
        self.assertFalse(self.main._eliminar_contrato_definitivo(9999)["ok"])
        self.assertFalse(self.main._eliminar_contrato_definitivo(None)["ok"])
        self.assertEqual(len(self.filas("SELECT * FROM cochera_contratos")), 1)

    def test_eliminar_contrato_error_revierte_toda_operacion(self):
        contrato = self.contrato(historial=1)
        self.ejecutar("UPDATE espacios SET id_cliente=? WHERE id_espacio=?", (self.cliente, self.cochera))
        self.ejecutar("CREATE TRIGGER qa_abort_contrato BEFORE DELETE ON cochera_contratos BEGIN SELECT RAISE(ABORT,'qa_abort'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.main._eliminar_contrato_definitivo(contrato)
        self.assertEqual(len(self.filas("SELECT * FROM cochera_contratos")), 1)
        self.assertEqual(self.filas("SELECT id_cliente FROM espacios WHERE codigo='C01'")[0]["id_cliente"], self.cliente)

    def test_ui_contrato_con_pagos_no_pide_confirmacion_destructiva(self):
        contrato = self.contrato(historial=1)
        self.ejecutar("INSERT INTO pagos_cochera (id_contrato,monto,metodo) VALUES (?,48000,'Efectivo')", (contrato,))
        self.main.ContratosDialog._eliminar(self.dialogo_contrato(contrato))
        self.question_mock.assert_not_called()
        self.warning_mock.assert_called_once()
        self.assertEqual(len(self.filas("SELECT * FROM pagos_cochera")), 1)

    def test_ui_historial_con_pagos_no_pide_confirmacion_destructiva(self):
        contrato = self.contrato(historial=1)
        self.ejecutar("INSERT INTO pagos_cochera (id_contrato,monto,metodo) VALUES (?,48000,'Efectivo')", (contrato,))
        dialog = SimpleNamespace(_selected_contrato_id=lambda: contrato, _es_dueno=lambda: True,
                                 _contar_pagos_contrato=lambda _: 1)
        self.main.HistorialContratosDialog._eliminar(dialog)
        self.question_mock.assert_not_called()
        self.warning_mock.assert_called_once()
        self.assertEqual(len(self.filas("SELECT * FROM pagos_cochera")), 1)

    def test_ui_eliminar_revalida_pago_creado_durante_confirmacion(self):
        contrato = self.contrato(historial=1)
        def confirmar(*_args):
            self.ejecutar("INSERT INTO pagos_cochera (id_contrato,monto,metodo) VALUES (?,48000,'Efectivo')", (contrato,))
            return self.main.QMessageBox.Yes
        self.question_mock.side_effect = confirmar
        self.main.ContratosDialog._eliminar(self.dialogo_contrato(contrato))
        self.assertEqual(len(self.filas("SELECT * FROM cochera_contratos")), 1)
        self.assertEqual(len(self.filas("SELECT * FROM pagos_cochera")), 1)
        self.warning_mock.assert_called_once()


class ErroresLecturaTests(AccionesMainMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def reportes_dialog(self):
        dialog = self.main.ReportesDialog()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def caja_dialog(self):
        dialog = self.main.CajaDiariaDialog()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_todos_lectores_financieros_propagan_error_sql_y_cierran_conexion(self):
        lectores = ((reportes, reportes.consultar_resumen, ("2026-01",)),
                    (reportes, reportes.consultar_resumen_rango, ("2026-01-01", "2026-01-31")),
                    (reportes, reportes.consultar_detalle, ("2026-01",)),
                    (reportes, reportes.consultar_detalle_rango, ("2026-01-01", "2026-01-31")),
                    (reportes, reportes.consultar_pagos_mensuales_rango, ("2026-01-01", "2026-01-31")),
                    (caja, caja.consultar_totales_dia, ("2026-01-31",)),
                    (caja, caja.consultar_detalle_por_metodo_dia, ("2026-01-31",)),
                    (caja, caja.obtener_cierre_caja, ("2026-01-31",)),
                    (caja, caja.obtener_cierre_caja_metodos, ("2026-01-31",)))
        for modulo, funcion, args in lectores:
            with self.subTest(funcion=funcion.__name__):
                conn = unittest.mock.Mock()
                conn.cursor.return_value.execute.side_effect = sqlite3.OperationalError("Lectura fallida de QA")
                with patch.object(modulo, "get_connection", return_value=conn), self.assertRaises(sqlite3.OperationalError):
                    funcion(*args)
                conn.close.assert_called_once()

    def test_resumen_no_devuelve_totales_parciales_si_segunda_consulta_falla(self):
        conn = unittest.mock.Mock()
        conn.cursor.return_value.execute.side_effect = [None, sqlite3.OperationalError("Segunda consulta fallida")]
        conn.cursor.return_value.fetchone.return_value = (48000,)
        with patch.object(reportes, "get_connection", return_value=conn), self.assertRaises(sqlite3.OperationalError):
            reportes.consultar_resumen("2026-01")
        conn.close.assert_called_once()

    def test_reportes_fallidos_no_muestran_cero_ni_permiten_exportar(self):
        with patch.object(self.main, "svc_consultar_detalle_reportes_rango", side_effect=sqlite3.OperationalError("QA")):
            dialog = self.reportes_dialog()
        self.assertEqual(dialog.label_total_value.text(), "No disponible")
        self.assertIn("No se pudieron leer", dialog.table_historial.item(0, 0).text())
        self.assertFalse(dialog.btn_export_excel.isEnabled())
        dialog.combo_metodo.setCurrentText("QR")
        self.assertEqual(dialog.label_total_value.text(), "No disponible")
        with patch.object(self.main.QFileDialog, "getSaveFileName") as elegir_archivo:
            dialog._exportar_excel()
        elegir_archivo.assert_not_called()
        self.warning_mock.assert_called_once()

    def test_reportes_recuperan_lectura_y_filtro_qr(self):
        with patch.object(self.main, "svc_consultar_detalle_reportes_rango", side_effect=sqlite3.OperationalError("QA")):
            dialog = self.reportes_dialog()
        contrato = self.contrato(historial=1)
        self.ejecutar("INSERT INTO pagos_cochera (id_contrato,monto,metodo,fecha_pago) VALUES (?,48000,'QR',?)",
                     (contrato, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.assertTrue(dialog._cargar())
        dialog.combo_metodo.setCurrentText("QR")
        self.assertEqual(len(dialog._detalle_filtrado_cache), 1)
        self.assertEqual(dialog._detalle_filtrado_cache[0]["metodo"], "QR")
        self.assertTrue(dialog.btn_export_excel.isEnabled())
        self.assertNotEqual(dialog.label_total_value.text(), "No disponible")
        self.assertEqual(dialog.table_historial.columnSpan(0, 0), 1)

    def test_caja_fallida_no_muestra_cero_ni_guarda_cierre(self):
        with patch.object(self.main, "svc_consultar_totales_caja", side_effect=sqlite3.OperationalError("QA")):
            dialog = self.caja_dialog()
        self.assertEqual(dialog.label_total.text(), "No disponible")
        self.assertEqual(dialog.input_total_contado.specialValueText(), "No disponible")
        self.assertFalse(dialog.btn_guardar_cierre.isEnabled())
        self.assertFalse(dialog.btn_reabrir_cierre.isEnabled())
        dialog._actualizar_diferencia()
        self.assertEqual(dialog.label_diferencia.text(), "No disponible")
        with patch.object(self.main, "svc_guardar_cierre_caja") as guardar:
            self.assertFalse(dialog._guardar_cierre())
        guardar.assert_not_called()
        self.assertEqual(self.filas("SELECT * FROM cierres_caja"), [])

    def test_caja_fallo_cualquier_lector_deja_importes_no_disponibles(self):
        for lector in ("svc_consultar_detalle_metodo_caja", "svc_obtener_cierre_caja", "svc_obtener_cierre_caja_metodos"):
            with self.subTest(lector=lector), patch.object(self.main, lector, side_effect=sqlite3.OperationalError("QA")):
                dialog = self.caja_dialog()
                self.assertTrue(dialog._error_lectura)
                self.assertEqual(dialog.label_total.text(), "No disponible")
                self.assertFalse(dialog.btn_guardar_cierre.isEnabled())

    def test_caja_error_tras_carga_quita_controles_e_importes_anteriores(self):
        dialog = self.caja_dialog()
        dialog._metodo_rows[0]["input_contado"].setValue(269500)
        self.assertTrue(any(dialog.table_metodos.cellWidget(0, c) is not None
                            for c in range(dialog.table_metodos.columnCount())))
        with patch.object(self.main, "svc_consultar_totales_caja", side_effect=sqlite3.OperationalError("QA")):
            self.assertFalse(dialog._cargar())
        self.assertTrue(all(dialog.table_metodos.cellWidget(0, c) is None
                            for c in range(dialog.table_metodos.columnCount())))
        self.assertIn("No se pudieron leer", dialog.table_metodos.item(0, 0).text())
        self.assertFalse(dialog.btn_guardar_cierre.isEnabled())

    def test_caja_recupera_lectura_valida_y_cero_real(self):
        with patch.object(self.main, "svc_consultar_totales_caja", side_effect=sqlite3.OperationalError("QA")):
            dialog = self.caja_dialog()
        self.assertTrue(dialog._cargar())
        self.assertFalse(dialog._error_lectura)
        self.assertTrue(dialog.btn_guardar_cierre.isEnabled())
        self.assertEqual(dialog._total_esperado_actual, 0)
        self.assertEqual(dialog.input_total_contado.specialValueText(), "")
        self.assertEqual(dialog.table_metodos.columnSpan(0, 0), 1)

    def test_guardar_caja_error_lectura_entre_carga_y_guardado_no_escribe(self):
        dialog = self.caja_dialog()
        with patch.object(self.main, "_antirebote_iniciar", return_value=True), patch.object(self.main, "_antirebote_finalizar"), \
                patch.object(self.main, "svc_consultar_totales_caja", side_effect=sqlite3.OperationalError("QA")), \
                patch.object(self.main, "svc_guardar_cierre_caja") as guardar:
            self.assertFalse(dialog._guardar_cierre())
        self.assertTrue(dialog._error_lectura)
        self.assertEqual(dialog.label_total.text(), "No disponible")
        guardar.assert_not_called()
        self.assertEqual(self.filas("SELECT * FROM cierres_caja"), [])

    def test_cerrar_caja_y_guardar_no_cierra_ventana_si_falla_lectura(self):
        from PySide6.QtGui import QCloseEvent
        dialog = self.caja_dialog()
        dialog._metodo_rows[0]["input_contado"].setValue(100)
        evento = QCloseEvent()
        with patch.object(self.main, "_confirmar_guardado_pendiente", return_value=self.main.QMessageBox.Yes), \
                patch.object(self.main, "_antirebote_iniciar", return_value=True), \
                patch.object(self.main, "_antirebote_finalizar"), \
                patch.object(self.main, "svc_obtener_cierre_caja", side_effect=sqlite3.OperationalError("QA")):
            dialog.closeEvent(evento)
        self.assertFalse(evento.isAccepted())
        self.assertEqual(self.filas("SELECT * FROM cierres_caja"), [])

    def test_reabrir_caja_error_lectura_no_elimina_cierre(self):
        dialog = self.caja_dialog()
        with patch.object(dialog, "_es_dueno", return_value=True), \
                patch.object(self.main, "svc_obtener_cierre_caja", side_effect=sqlite3.OperationalError("QA")), \
                patch.object(self.main, "svc_eliminar_cierre_caja") as eliminar:
            dialog._reabrir_cierre()
        eliminar.assert_not_called()
        self.assertTrue(dialog._error_lectura)
        self.mostrar_error_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
