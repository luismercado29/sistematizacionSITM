"""Carga la red de Cartagena, una flota y conductores de demostracion.

La red (rutas, recorridos por la via y paradas) sale de
``apps/red/datos/red_cartagena.json``, generado desde OpenStreetMap con
``importar_red_osm``. La flota, los conductores y las frecuencias son
ficticios: sirven para probar el sistema y para la demo publica.

Es idempotente: se puede ejecutar varias veces sin duplicar registros.
"""

import json
import random
import secrets
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.roles import DESPACHADORES, SUPERVISORES
from apps.flota.models import Bus, Conductor
from apps.red.models import Estacion, ParadaRuta, Ruta

DATOS_RED = Path(__file__).resolve().parents[3] / 'red' / 'datos' / 'red_cartagena.json'

# Parametros de operacion por tipo de ruta: (frecuencia en min, velocidad comercial km/h).
OPERACION = {
    Ruta.Tipo.TRONCAL: (10, 20),
    Ruta.Tipo.EXPRESA: (15, 26),
    Ruta.Tipo.PRETRONCAL: (20, 18),
    Ruta.Tipo.ALIMENTADORA: (20, 16),
    Ruta.Tipo.COMPLEMENTARIA: (30, 16),
}
# Colores con contraste AA sobre texto blanco, uno por ruta dentro de cada familia.
COLORES = {
    Ruta.Tipo.TRONCAL: ['#1D4ED8', '#0E7490', '#4338CA'],
    Ruta.Tipo.EXPRESA: ['#C2410C'],
    Ruta.Tipo.PRETRONCAL: ['#7C3AED', '#A21CAF', '#9333EA', '#6D28D9', '#86198F', '#7E22CE'],
    Ruta.Tipo.ALIMENTADORA: ['#15803D', '#047857', '#166534', '#0F766E', '#3F6212', '#065F46',
                             '#15803D', '#047857', '#166534', '#0F766E'],
    Ruta.Tipo.COMPLEMENTARIA: ['#A16207', '#B45309', '#92400E', '#9A3412'],
}
NUM_BUSES = 130
NUM_CONDUCTORES = 150

# Nombres genericos: el sistema no menciona empresas ni marcas reales.
OPERADORES = ['Operador Norte', 'Operador Sur', 'Operador Centro']
NOMBRES = ['Carlos', 'José', 'Luis', 'Andrés', 'Jorge', 'Rafael', 'Miguel', 'Julio', 'Álvaro',
           'Hernán', 'Wilson', 'Édgar', 'Fabio', 'Yesid', 'Alberto', 'Diana', 'Paola', 'Katia',
           'Yolanda', 'Sandra']
APELLIDOS = ['Pérez', 'Martínez', 'Herrera', 'Julio', 'Cassiani', 'Cabarcas', 'Marrugo', 'Barrios',
             'Castro', 'Puello', 'Torres', 'Caraballo', 'Mendoza', 'Orozco', 'Salgado', 'Díaz',
             'Arrieta', 'Bustillo', 'Villadiego', 'Guerrero']


class Command(BaseCommand):
    help = 'Carga datos de demostración (red, flota, conductores, roles).'

    def add_arguments(self, parser):
        parser.add_argument('--usuarios', action='store_true',
                            help='Crea las cuentas "despachador" y "supervisor" con contraseñas aleatorias.')

    @transaction.atomic
    def handle(self, *args, **opciones):
        rng = random.Random(2026)  # mismos datos en cada ejecucion
        self._roles()
        self._red()
        self._flota(rng)
        self._conductores(rng)
        if opciones['usuarios']:
            self._usuarios()
        self.stdout.write(self.style.SUCCESS(
            f'Listo: {Estacion.objects.count()} estaciones, {Ruta.objects.count()} rutas, '
            f'{Bus.objects.count()} buses, {Conductor.objects.count()} conductores.'))

    def _roles(self):
        for nombre in (DESPACHADORES, SUPERVISORES):
            Group.objects.get_or_create(name=nombre)

    def _red(self):
        datos = json.loads(DATOS_RED.read_text(encoding='utf-8'))
        for e in datos['estaciones']:
            Estacion.objects.update_or_create(codigo=e['codigo'], defaults={
                'nombre': e['nombre'], 'tipo': e['tipo'], 'latitud': e['lat'], 'longitud': e['lng'], 'activa': True})
        estaciones = {e.codigo: e for e in Estacion.objects.all()}
        usados = {t: 0 for t in COLORES}
        codigos = []
        for r in datos['rutas']:
            tipo = r['tipo']
            frecuencia, velocidad = OPERACION[tipo]
            color = COLORES[tipo][usados[tipo] % len(COLORES[tipo])]
            usados[tipo] += 1
            ruta, _ = Ruta.objects.update_or_create(codigo=r['codigo'], defaults={
                'nombre': r['nombre'], 'tipo': tipo, 'color': color, 'horario': r['horario'],
                'frecuencia_min': frecuencia, 'velocidad_kmh': velocidad,
                'trazado': r['trazado'], 'activa': True})
            ParadaRuta.objects.filter(ruta=ruta).delete()
            ParadaRuta.objects.bulk_create(
                ParadaRuta(ruta=ruta, estacion=estaciones[c], orden=i) for i, c in enumerate(r['paradas'], 1))
            ruta.recalcular_tiempos()
            codigos.append(r['codigo'])

        # Rutas de versiones anteriores de la demo: se borran si nunca se usaron.
        viejas = Ruta.objects.exclude(codigo__in=codigos)
        con_historia = viejas.filter(despachos__isnull=False).distinct()
        con_historia.update(activa=False)
        ParadaRuta.objects.filter(ruta__in=con_historia).delete()
        viejas.exclude(pk__in=con_historia).delete()
        actuales = [e['codigo'] for e in datos['estaciones']]
        Estacion.objects.exclude(codigo__in=actuales).filter(paradas__isnull=True).delete()
        Estacion.objects.exclude(codigo__in=actuales).update(activa=False)

    def _flota(self, rng):
        letras = 'ABCDEFGHJKLMNPRSTUVWXYZ'
        for i in range(NUM_BUSES):
            numero = f'TC-{1001 + i}'
            if Bus.objects.filter(numero=numero).exists():
                continue
            # Proporcion aproximada de una flota de SITM: articulados para la troncal,
            # padrones para pretroncales y busetones para alimentacion.
            if i % 10 < 3:
                tipologia, capacidad = Bus.Tipologia.ARTICULADO, 160
            elif i % 10 < 7:
                tipologia, capacidad = Bus.Tipologia.PADRON, rng.choice([80, 90])
            else:
                tipologia, capacidad = Bus.Tipologia.BUSETON, 50
            Bus.objects.create(
                numero=numero, placa=''.join(rng.choice(letras) for _ in range(3)) + f'{rng.randint(100, 999)}',
                tipologia=tipologia, capacidad=capacidad,
                operador=OPERADORES[i % 3], modelo=rng.randint(2015, 2024),
                estado=Bus.Estado.MANTENIMIENTO if i % 17 == 7 else Bus.Estado.DISPONIBLE,
            )

    def _conductores(self, rng):
        hoy = timezone.localdate()
        for i in range(NUM_CONDUCTORES):
            documento = str(73100000 + i * 137)
            if Conductor.objects.filter(documento=documento).exists():
                continue
            # Algunas licencias vencen pronto para que se vea la alerta.
            dias = rng.randint(10, 25) if i % 40 == 3 else rng.randint(120, 1400)
            Conductor.objects.create(
                nombre=f'{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}',
                documento=documento, telefono=f'3{rng.randint(0, 2)}{rng.randint(10000000, 99999999)}',
                licencia=f'1304{rng.randint(100000, 999999)}{i:02d}',
                categoria=Conductor.Categoria.C3 if i % 10 < 6 else Conductor.Categoria.C2,
                vencimiento_licencia=hoy + timedelta(days=dias),
                estado=Conductor.Estado.DESCANSO if i % 25 == 5 else Conductor.Estado.ACTIVO,
            )

    def _usuarios(self):
        User = get_user_model()
        for username, grupo in (('despachador', DESPACHADORES), ('supervisor', SUPERVISORES)):
            if User.objects.filter(username=username).exists():
                self.stdout.write(f'La cuenta "{username}" ya existe; no se modifica.')
                continue
            clave = secrets.token_urlsafe(10)
            user = User.objects.create_user(username, password=clave,
                                            first_name=username.capitalize())
            user.groups.add(Group.objects.get(name=grupo))
            self.stdout.write(self.style.WARNING(f'Cuenta {username} / contraseña: {clave}'))
