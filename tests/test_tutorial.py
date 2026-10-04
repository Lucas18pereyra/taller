"""El tutorial tiene cuatro pasos y no exige operaciones comerciales."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import main


class TutorialTests(unittest.TestCase):
    def ventana(self, espacios=0, completa=True):
        estado = dict(tarifas=int(completa), espacios=espacios,
                      clientes=0, vehiculos=0, contratos=0, movimientos=0,
                      **{k: 'configurado' if completa else '' for k in (
                          'empresa_nombre', 'empresa_direccion', 'empresa_telefono',
                          'dir_reportes', 'dir_comprobantes', 'dir_tickets_salida')})
        ventana = SimpleNamespace(_estado_primeros_pasos=lambda: estado,
                                  _popup_primeros_pasos_mostrado=False, isVisible=lambda: True)
        ventana._pasos_primeros_pasos = lambda: main.VentanaPrincipal._pasos_primeros_pasos(ventana)
        ventana._siguiente_paso_primeros_pasos = lambda: main.VentanaPrincipal._siguiente_paso_primeros_pasos(ventana)
        return ventana

    def test_cuatro_pasos_numerados_en_orden(self):
        pasos = self.ventana(completa=False)._pasos_primeros_pasos()
        self.assertEqual([p['numero'] for p in pasos], [1, 2, 3, 4])
        self.assertEqual([p['titulo'] for p in pasos], ['Tarifas', 'Configuracion', 'Carpetas de archivos', 'Mapa y espacios'])

    def test_mapa_es_ultimo_paso_y_popup_enumerado(self):
        ventana = self.ventana()
        with patch.object(main.QMessageBox, 'information') as aviso:
            main.VentanaPrincipal._mostrar_popup_primeros_pasos(ventana)
        texto = aviso.call_args.args[2]
        self.assertIn('1. Tarifas', texto)
        self.assertIn('2. Configuracion', texto)
        self.assertIn('3. Carpetas de archivos', texto)
        self.assertIn('Paso 4 de 4: Mapa y espacios', texto)
        self.assertNotIn('Clientes y patentes', texto)
        self.assertNotIn('Puesta en marcha', texto)

    def test_finaliza_con_mapa_sin_clientes_patentes_o_movimientos(self):
        ventana = self.ventana(espacios=1)
        self.assertIsNone(ventana._siguiente_paso_primeros_pasos()[0])
        with patch.object(main.QMessageBox, 'information') as aviso:
            main.VentanaPrincipal._mostrar_popup_primeros_pasos(ventana)
        aviso.assert_not_called()


if __name__ == '__main__':
    unittest.main()
