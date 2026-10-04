import json
from pathlib import Path

from django.test import SimpleTestCase

from apps.red import osm

DATOS = Path(__file__).resolve().parent / 'datos' / 'red_cartagena.json'


def via(*puntos):
    return {'type': 'way', 'role': '', 'geometry': [{'lat': a, 'lon': b} for a, b in puntos]}


class EncadenarTests(SimpleTestCase):
    def test_orienta_las_vias_para_formar_una_linea(self):
        linea = osm.encadenar([via((0, 0), (0, 1)), via((0, 2), (0, 1)), via((0, 2), (0, 3))])
        self.assertEqual(linea, [(0, 0), (0, 1), (0, 2), (0, 3)])

    def test_orienta_la_primera_via_segun_la_siguiente(self):
        linea = osm.encadenar([via((0, 1), (0, 0)), via((0, 1), (0, 2))])
        self.assertEqual(linea[0], (0, 0))


class NombresTests(SimpleTestCase):
    def test_nombre_de_ruta_legible(self):
        self.assertEqual(osm.nombre_ruta('Troncal 101 - Portal - Centro - Portal', 'T101'),
                         'Portal → Centro → Portal')

    def test_no_se_importa_ninguna_marca(self):
        self.assertEqual(osm.limpiar_nombre('Parada Transcaribe Bazurto'), 'Parada Bazurto')


class DatosDeLaRedTests(SimpleTestCase):
    """El archivo versionado debe ser coherente: lo usa cargar_demo sin internet."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.red = json.loads(DATOS.read_text(encoding='utf-8'))

    def test_incluye_todas_las_familias_de_rutas(self):
        codigos = {r['codigo'] for r in self.red['rutas']}
        self.assertTrue({'T100E', 'T101', 'T102', 'T103', 'X101', 'X106', 'A101', 'C001'} <= codigos)
        self.assertGreaterEqual(len(codigos), 20)

    def test_cada_ruta_tiene_trazado_y_paradas_conocidas(self):
        estaciones = {e['codigo'] for e in self.red['estaciones']}
        for r in self.red['rutas']:
            with self.subTest(ruta=r['codigo']):
                self.assertGreater(len(r['trazado']), 10)
                self.assertGreaterEqual(len(r['paradas']), 2)
                self.assertTrue(set(r['paradas']) <= estaciones)

    def test_la_troncal_va_y_vuelve_por_las_estaciones(self):
        t101 = next(r for r in self.red['rutas'] if r['codigo'] == 'T101')
        self.assertEqual(t101['paradas'][0], 'portal')
        self.assertEqual(t101['paradas'][-1], 'portal')
        self.assertIn('la-bodeguita', t101['paradas'])
        self.assertEqual(t101['paradas'].count('bazurto'), 2)

    def test_sin_marca_en_los_datos(self):
        self.assertNotIn('transcaribe', DATOS.read_text(encoding='utf-8').lower())
