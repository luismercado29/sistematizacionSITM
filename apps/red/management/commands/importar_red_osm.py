"""Descarga de OpenStreetMap los recorridos de las rutas de Cartagena.

Genera ``apps/red/datos/red_cartagena.json``, que se guarda en el repositorio:
``cargar_demo`` lo usa sin conexion a internet. Volver a correrlo solo hace
falta si cambian las rutas en OpenStreetMap.

    python manage.py importar_red_osm
"""

import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.red import osm

ARCHIVO = Path(__file__).resolve().parents[2] / 'datos' / 'red_cartagena.json'

LV, S, D = 'Lun a vie', 'Sáb', 'Dom y festivos'
# Horarios publicados por el sistema (guía de rutas y recorridos, 2024).
HORARIOS = {
    'T100E': f'{LV} 6:00–20:00 · {S} 6:00–13:00 · {D}: no opera',
    'T101': f'{LV} 5:00–21:30 · {S} 5:30–20:30 · {D} 6:00–20:00',
    **{c: f'{LV} 5:00–21:00 · {S} 5:30–20:30 · {D} 6:00–20:00'
       for c in ('T102', 'T103', 'X101', 'X102', 'X103', 'X104', 'X105', 'X106')},
    **{c: f'{LV} 4:30–22:40 · {S} 5:00–22:00 · {D} 5:30–21:30'
       for c in ('A101', 'A103', 'A104', 'A105', 'A107', 'A108', 'A114', 'A117')},
    'A102': f'{LV} 5:00–22:00 · {S} 6:00–19:00 · {D}: no opera',
    'A111': f'{LV} 4:45–9:00 y 16:30–19:30 · {S} y {D.lower()}: no opera',
    'C001': f'{LV} 4:30–21:30 · {S} 5:00–21:30 · {D} 5:30–21:00',
    'C016': f'{LV} 5:30–7:45 y 16:30–19:30 · {S} y {D.lower()}: no opera',
    'C017': f'{LV} 5:00–9:00 y 16:00–19:00 · {S} y {D.lower()}: no opera',
}


class Command(BaseCommand):
    help = 'Descarga las rutas de bus de OpenStreetMap y actualiza los datos de la red.'

    def add_arguments(self, parser):
        parser.add_argument('--desde-archivos', nargs=2, metavar=('RUTAS_JSON', 'PARADAS_JSON'),
                            help='Usa respuestas de Overpass ya descargadas en lugar de consultar.')

    def handle(self, *args, **opciones):
        if opciones['desde_archivos']:
            rutas, paradas = (json.loads(Path(p).read_text(encoding='utf-8')) for p in opciones['desde_archivos'])
        else:
            self.stdout.write('Consultando OpenStreetMap (Overpass)…')
            try:
                rutas, paradas = osm.descargar_todo()
            except OSError as exc:
                raise CommandError(f'No se pudo descargar: {exc}') from exc

        red, avisos = osm.construir_red(rutas, paradas, HORARIOS)
        if not red['rutas']:
            raise CommandError('La respuesta no trae rutas del sistema.')
        red['generado'] = date.today().isoformat()
        ARCHIVO.parent.mkdir(exist_ok=True)
        ARCHIVO.write_text(json.dumps(red, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

        for aviso in avisos:
            self.stdout.write(self.style.WARNING(aviso))
        self.stdout.write(self.style.SUCCESS(
            f'{len(red["rutas"])} rutas y {len(red["estaciones"])} paradas → {ARCHIVO.name} '
            f'({ARCHIVO.stat().st_size // 1024} KB).'))
