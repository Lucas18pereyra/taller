"""Regresiones del mapa y de las rutas reales de la interfaz. Datos temporales."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import database
from servicios import espacios
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
from PySide6.QtGui import QFontDatabase
import main


def figura(codigo, original=None, reservado=0, x=25):
    return dict(codigo=codigo, codigo_original=original, es_reservado=reservado,
                x=x, y=35, w=100, h=65)


class MapaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        for fuente in ("segoeui.ttf", "segoeuib.ttf"):
            ruta = Path("C:/Windows/Fonts") / fuente
            if ruta.exists():
                QFontDatabase.addApplicationFont(str(ruta))

    def setUp(self):
        self.temporal = TemporaryDirectory(prefix="mapa_regresion_")
        self.db_patch = patch.object(database, "DB_PATH", Path(self.temporal.name) / "estacionamiento.db")
        self.db_patch.start()
        database.init_db()
        with closing(database.get_connection()) as conn:
            conn.execute("INSERT INTO clientes (dni,nombre) VALUES ('99999999','Cliente prueba')")
            self.cliente = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for patente in ("QA001AA", "QA002AA", "QA003AA"):
                conn.execute("INSERT INTO vehiculos (patente,id_cliente) VALUES (?,?)", (patente, self.cliente))
            for codigo, reservado, cliente in (("LIBRE", 0, None), ("CLIENTE", 1, self.cliente),
                                               ("COCHERA", 1, self.cliente), ("PENDIENTE", 1, None),
                                               ("AUTO", 0, None)):
                conn.execute("INSERT INTO espacios (codigo,es_reservado,id_cliente) VALUES (?,?,?)", (codigo, reservado, cliente))
                conn.execute("INSERT INTO espacios_mapa VALUES (?,23,37,100,65)", (codigo,))
            ids = {r["codigo"]: r["id_espacio"] for r in conn.execute("SELECT * FROM espacios")}
            self.ids = ids
            vencimiento = (datetime.now() + timedelta(days=30)).date().isoformat()
            conn.execute("INSERT INTO cochera_contratos (id_cliente,id_vehiculo,id_espacio,fecha_vencimiento,monto_mensual,activo) VALUES (?,1,?,?,1000,1)", (self.cliente, ids["COCHERA"], vencimiento))
            conn.execute("INSERT INTO cochera_contratos (id_cliente,id_vehiculo,id_espacio,fecha_vencimiento,monto_mensual,activo) VALUES (?,3,?,?,1000,0)", (self.cliente, ids["PENDIENTE"], vencimiento))
            conn.execute("INSERT INTO movimientos (id_vehiculo,id_espacio,fecha_ingreso,tarifa_hora_aplicada) VALUES (2,?,?,1000)", (ids["AUTO"], datetime.now().isoformat(" ")))
            conn.execute("INSERT INTO tarifas (precio_hora,precio_hora_auto,precio_mensual,activa) VALUES (1000,1000,30000,1)")
            conn.commit()
        self.dialogos = []
        self.avisos = []
        self.parches = []
        for nombre in ("information", "warning", "critical"):
            p = patch.object(QMessageBox, nombre, side_effect=lambda *a, **k: self.avisos.append(a[2]) or QMessageBox.Ok)
            p.start()
            self.parches.append(p)
        p = patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
        p.start()
        self.parches.append(p)

    def tearDown(self):
        for dialogo in self.dialogos:
            dialogo.scene.setProperty("suspend_dirty", True)
            dialogo._set_mapa_dirty(False)
            dialogo.close()
            dialogo.deleteLater()
        self.app.processEvents()
        for p in reversed(self.parches):
            p.stop()
        self.db_patch.stop()
        self.temporal.cleanup()

    def consulta(self, sql, args=()):
        with closing(database.get_connection()) as conn:
            return conn.execute(sql, args).fetchall()

    def mapa(self, editable=True):
        dialogo = main.MapaCocheraDialog(editable=editable)
        self.dialogos.append(dialogo)
        return dialogo

    def item(self, dialogo, codigo):
        dialogo.scene.clearSelection()
        item = next(i for i in dialogo.scene.items() if isinstance(i, main.EspacioItem) and i.codigo == codigo)
        item.setSelected(True)
        return item

    def test_no_eliminar_cliente_contrato_pendiente_o_patente(self):
        for codigo in ("CLIENTE", "COCHERA", "PENDIENTE", "AUTO"):
            with self.subTest(codigo=codigo), self.assertRaises(ValueError):
                espacios.guardar_mapa([], {codigo})
            self.assertTrue(self.consulta("SELECT 1 FROM espacios_mapa WHERE codigo=?", (codigo,)))

    def test_eliminar_libre_desactiva_sin_borrar_identidad(self):
        espacios.guardar_mapa([], {"LIBRE"})
        self.assertFalse(self.consulta("SELECT 1 FROM espacios_mapa WHERE codigo='LIBRE'"))
        row = self.consulta("SELECT id_espacio,activo FROM espacios WHERE codigo='LIBRE'")[0]
        self.assertEqual(tuple(row), (self.ids["LIBRE"], 0))

    def test_reutilizar_inactivo_conserva_id(self):
        espacios.guardar_mapa([], {"LIBRE"})
        espacios.guardar_mapa([figura("LIBRE")], set())
        self.assertEqual(tuple(self.consulta("SELECT id_espacio,activo FROM espacios WHERE codigo='LIBRE'")[0]), (self.ids["LIBRE"], 1))

    def test_renombrar_cochera_conserva_contrato_cliente_y_id(self):
        espacios.guardar_mapa([figura("C-NUEVA", "COCHERA", 1)], set())
        self.assertEqual(tuple(self.consulta("SELECT id_espacio,id_cliente FROM espacios WHERE codigo='C-NUEVA'")[0]), (self.ids["COCHERA"], self.cliente))
        self.assertTrue(self.consulta("SELECT 1 FROM cochera_contratos WHERE id_espacio=?", (self.ids["COCHERA"],)))
        self.assertFalse(self.consulta("SELECT 1 FROM espacios_mapa WHERE codigo='COCHERA'"))
        self.assertTrue(self.consulta("SELECT 1 FROM espacios_mapa WHERE codigo='C-NUEVA'"))
        self.assertFalse(self.consulta("PRAGMA foreign_key_check"))

    def test_renombrar_ocupado_conserva_movimiento(self):
        espacios.guardar_mapa([figura("A-NUEVO", "AUTO")], set())
        self.assertEqual(self.consulta("SELECT id_espacio FROM espacios WHERE codigo='A-NUEVO'")[0][0], self.ids["AUTO"])
        self.assertEqual(self.consulta("SELECT id_espacio FROM movimientos WHERE fecha_salida IS NULL")[0][0], self.ids["AUTO"])

    def test_guardado_revalida_ocupacion_y_revierte_todo(self):
        espacios.comprobar_eliminacion("LIBRE")
        with closing(database.get_connection()) as conn:
            conn.execute("UPDATE espacios SET id_cliente=? WHERE codigo='LIBRE'", (self.cliente,))
            conn.commit()
        with self.assertRaises(ValueError):
            espacios.guardar_mapa([figura("NUEVO")], {"LIBRE"})
        self.assertFalse(self.consulta("SELECT 1 FROM espacios WHERE codigo='NUEVO'"))
        self.assertTrue(self.consulta("SELECT 1 FROM espacios_mapa WHERE codigo='LIBRE'"))

    def test_codigo_duplicado_y_dimension_invalida_no_escriben(self):
        for items in ([figura("DUP"), figura("DUP")], [dict(figura("NUEVO"), w=0)],
                      [dict(figura("NUEVO"), x=float("nan"))], [figura("COCHERA", "LIBRE")]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                espacios.guardar_mapa(items, set())
        self.assertFalse(self.consulta("SELECT 1 FROM espacios WHERE codigo='NUEVO'"))

    def test_mapa_ui_bloquea_eliminar_vinculados_inmediatamente(self):
        dialogo = self.mapa()
        for codigo in ("CLIENTE", "COCHERA", "PENDIENTE", "AUTO"):
            self.item(dialogo, codigo)
            dialogo._eliminar()
            self.assertTrue(dialogo._codigo_en_escena(codigo))
        self.assertFalse(dialogo._eliminados)
        self.assertEqual(len(self.avisos), 4)

    def test_mapa_ui_guardar_bloquea_si_ocupacion_cambia(self):
        dialogo = self.mapa()
        self.item(dialogo, "LIBRE")
        dialogo._eliminar()
        with closing(database.get_connection()) as conn:
            conn.execute("UPDATE espacios SET id_cliente=? WHERE codigo='LIBRE'", (self.cliente,))
            conn.commit()
        self.assertFalse(dialogo._guardar(mostrar_mensaje=False))
        self.assertTrue(self.consulta("SELECT 1 FROM espacios_mapa WHERE codigo='LIBRE'"))
        self.assertTrue(dialogo._mapa_tiene_cambios())

    def test_mapa_ui_guardado_limpia_eliminaciones(self):
        dialogo = self.mapa()
        self.item(dialogo, "LIBRE")
        dialogo._eliminar()
        self.assertTrue(dialogo._guardar(mostrar_mensaje=False))
        self.assertFalse(dialogo._eliminados)
        self.assertFalse(dialogo._mapa_tiene_cambios())

    def test_mapa_ui_tipo_es_pendiente_y_limpiar_lo_descarta(self):
        dialogo = self.mapa()
        item = self.item(dialogo, "LIBRE")
        dialogo._set_cochera(True)
        self.assertEqual(item.es_reservado, 1)
        self.assertEqual(self.consulta("SELECT es_reservado FROM espacios WHERE codigo='LIBRE'")[0][0], 0)
        dialogo._recargar()
        self.assertEqual(self.item(dialogo, "LIBRE").es_reservado, 0)

    def test_mapa_ui_tipo_se_guarda_y_persiste(self):
        dialogo = self.mapa()
        self.item(dialogo, "LIBRE")
        dialogo._set_cochera(True)
        self.assertTrue(dialogo._guardar(mostrar_mensaje=False))
        self.assertEqual(self.consulta("SELECT es_reservado FROM espacios WHERE codigo='LIBRE'")[0][0], 1)

    def test_mapa_ui_no_modifica_posiciones_al_cargar(self):
        dialogo = self.mapa()
        item = self.item(dialogo, "LIBRE")
        self.assertEqual((item.pos().x(), item.pos().y()), (23, 37))

    def test_mapa_ui_renombrar_mantiene_original_para_bloquear_delete(self):
        dialogo = self.mapa()
        item = self.item(dialogo, "CLIENTE")
        with patch.object(QInputDialog, "getText", return_value=("CLIENTE-NUEVO", True)):
            dialogo._renombrar()
        self.assertEqual(item.codigo_original, "CLIENTE")
        dialogo._eliminar()
        self.assertTrue(dialogo._codigo_en_escena("CLIENTE-NUEVO"))
        self.assertTrue(dialogo._guardar(mostrar_mensaje=False))
        self.assertEqual(item.codigo_original, "CLIENTE-NUEVO")

    def test_mapa_solo_lectura_bloquea_metodos_mutantes(self):
        dialogo = self.mapa(editable=False)
        self.item(dialogo, "LIBRE")
        with patch.object(QInputDialog, "getText", side_effect=AssertionError("No debe pedir codigo en modo lectura")):
            dialogo._agregar()
            dialogo._renombrar()
        dialogo._eliminar()
        dialogo._set_cochera(True)
        self.assertFalse(dialogo._guardar(mostrar_mensaje=False))
        self.assertTrue(dialogo._codigo_en_escena("LIBRE"))
        self.assertEqual(self.consulta("SELECT es_reservado FROM espacios WHERE codigo='LIBRE'")[0][0], 0)

    def test_codigo_explicito_invalido_no_asigna_otro_lugar(self):
        dummy = SimpleNamespace(_buscar_espacio_libre_est=lambda cur: cur.execute("SELECT id_espacio,codigo FROM espacios WHERE codigo='LIBRE'").fetchone())
        with closing(database.get_connection()) as conn:
            for codigo in ("INEXISTENTE", "AUTO", "COCHERA", "CLIENTE"):
                self.assertIsNone(main.VentanaPrincipal._resolver_espacio_est(dummy, conn.cursor(), codigo)[0])
            self.assertEqual(main.VentanaPrincipal._resolver_espacio_est(dummy, conn.cursor(), "")[0], self.ids["LIBRE"])

    def ventana(self):
        ventana = main.VentanaPrincipal(usuario="qa", rol="DUENO")
        self.addCleanup(ventana.deleteLater)
        self.addCleanup(ventana.close)
        ventana.ui.input_patente_est.setText("QA002AA")
        ventana._solicitar_metodo_pago_est = lambda **kw: "Efectivo"
        return ventana

    def test_salida_ui_pago_y_movimiento_usen_misma_fecha_local(self):
        ventana = self.ventana()
        with closing(database.get_connection()) as conn:
            conn.execute("UPDATE movimientos SET fecha_ingreso=?", ((datetime.now() - timedelta(hours=2)).isoformat(" "),))
            conn.commit()
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.Ok), patch.object(main, "_emitir_ticket_estacionamiento_seguro", return_value=(None, None)):
            ventana._registrar_salida_est()
        row = self.consulta("SELECT m.fecha_salida,p.fecha_pago,m.total,p.monto,p.usuario FROM movimientos m JOIN pagos p ON p.id_movimiento=m.id_movimiento")[0]
        self.assertEqual(row[0], row[1])
        self.assertEqual(row[2], row[3])
        self.assertEqual(row[4], "qa")

    def test_salida_ui_concurrente_no_duplica_cobro(self):
        ventana = self.ventana()

        def otro_cierre(**kw):
            with closing(database.get_connection()) as conn:
                conn.execute("UPDATE movimientos SET fecha_salida=?,total=1000", (datetime.now().isoformat(" "),))
                conn.execute("INSERT INTO pagos (id_movimiento,monto,metodo) VALUES (1,1000,'Efectivo')")
                conn.commit()
            return "Efectivo"

        ventana._solicitar_metodo_pago_est = otro_cierre
        with patch.object(main, "_emitir_ticket_estacionamiento_seguro", side_effect=AssertionError("No debe emitir otro ticket")):
            ventana._registrar_salida_est()
        self.assertEqual(self.consulta("SELECT count(*) FROM pagos")[0][0], 1)
        self.assertEqual(self.consulta("SELECT total FROM movimientos")[0][0], 1000)

    def test_salida_ui_fecha_invalida_no_produce_salida_gratis(self):
        ventana = self.ventana()
        with closing(database.get_connection()) as conn:
            conn.execute("UPDATE movimientos SET fecha_ingreso='fecha incorrecta'")
            conn.commit()
        ventana._solicitar_metodo_pago_est = lambda **kw: self.fail("No debe pedir cobro con fecha invalida")
        ventana._registrar_salida_est()
        self.assertIsNone(self.consulta("SELECT fecha_salida FROM movimientos")[0][0])
        self.assertEqual(self.consulta("SELECT count(*) FROM pagos")[0][0], 0)

    def test_ingreso_ui_codigo_ocupado_no_crea_vehiculo_huerfano(self):
        ventana = self.ventana()
        ventana.ui.input_patente_est.setText("QA999AA")
        ventana.ui.input_espacio_est.setText("AUTO")
        combo = ventana.ui.combo_tipo_vehiculo_est
        combo.setCurrentIndex(combo.findData("AUTO"))
        ventana._registrar_ingreso_est()
        self.assertFalse(self.consulta("SELECT 1 FROM vehiculos WHERE patente='QA999AA'"))
        self.assertEqual(self.consulta("SELECT count(*) FROM movimientos")[0][0], 1)


if __name__ == "__main__":
    unittest.main()
