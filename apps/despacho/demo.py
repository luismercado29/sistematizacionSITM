"""Operacion automatica para el modo demostracion.

Con ``SITM_MODO_DEMO=true`` el sistema se comporta como si un despachador
estuviera trabajando: cierra los recorridos que ya terminaron y despacha buses
para mantener la frecuencia de cada ruta. Asi el mapa en vivo y el portal del
pasajero siempre tienen buses moviendose, aunque nadie use el panel.

Nunca debe activarse en una operacion real: los despachos automaticos no los
hace ninguna persona.
"""

import logging
import random
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from django.utils import timezone

from apps.red.models import Ruta

from . import servicios
from .models import Despacho, EventoDespacho
from .seguimiento import Trazado

log = logging.getLogger(__name__)

CLAVE_CACHE = 'sitm:demo:ultima-ejecucion'
INTERVALO_S = 45
ETIQUETA = '[modo demostración]'


def activo():
    return getattr(settings, 'SITM_MODO_DEMO', False)


def mantener_operacion(ahora=None, forzar=False):
    """Ejecuta un ciclo de la operacion automatica si corresponde.

    Esta pensado para llamarse desde las vistas: como mucho corre una vez cada
    ``INTERVALO_S`` por proceso, asi que su costo es despreciable.
    """
    if not activo():
        return
    if not forzar and not cache.add(CLAVE_CACHE, True, INTERVALO_S):
        return
    try:
        _ciclo(ahora or timezone.now())
    except Exception:  # la demo nunca debe tumbar una pagina
        log.exception('Fallo el ciclo del modo demostracion')


def _ciclo(ahora):
    _cerrar_recorridos_terminados(ahora)
    for ruta in Ruta.objects.filter(activa=True):
        _completar_frecuencia(ruta, ahora)


def _cerrar_recorridos_terminados(ahora):
    # Solo los despachos automaticos: los que hace una persona los cierra esa persona,
    # igual que en la operacion real (quedan "en terminal, pendiente de cierre").
    for d in (Despacho.objects.filter(estado=Despacho.Estado.EN_RUTA, despachador__isnull=True)
              .select_related('ruta')):
        duracion = d.ruta.duracion_min + 2
        if d.hora_salida + timedelta(minutes=duracion) <= ahora:
            llegada = d.hora_salida + timedelta(minutes=duracion)
            servicios.finalizar_despacho(d, None, ETIQUETA, ahora=llegada)


def _completar_frecuencia(ruta, ahora):
    """Despacha los buses que faltan para cubrir la ruta segun su frecuencia.

    Si la demo estuvo inactiva (p. ej. nadie abrio la pagina en horas), las
    salidas se reparten hacia atras en el tiempo para que el mapa vuelva a
    mostrar buses a lo largo de todo el recorrido y no todos en el origen.
    """
    trazado = Trazado(ruta)
    if len(trazado.paradas) < 2:
        return
    duracion = max(ruta.duracion_min, 1)
    activos = list(Despacho.objects.filter(ruta=ruta, estado=Despacho.Estado.EN_RUTA)
                   .values_list('hora_salida', flat=True))
    ultima = max(activos) if activos else None
    salidas = []
    if ultima is None:
        # Ruta vacia: reconstruye la operacion de la ultima vuelta completa.
        # El desfase aleatorio evita que rutas paralelas queden sincronizadas.
        # Se acota a la duracion para que las rutas cortas tengan al menos una salida.
        desfase = random.uniform(0, min(ruta.frecuencia_min, duracion - 1))
        t = ahora - timedelta(minutes=duracion - 1 - desfase)
        while t <= ahora:
            salidas.append(t)
            t += timedelta(minutes=ruta.frecuencia_min)
    else:
        t = ultima + timedelta(minutes=ruta.frecuencia_min)
        while t <= ahora:
            salidas.append(t)
            t += timedelta(minutes=ruta.frecuencia_min)
        # Tras una pausa larga solo valen las salidas que siguen en recorrido.
        salidas = [s for s in salidas if s > ahora - timedelta(minutes=duracion)]

    for salida in salidas:
        if not _despachar(ruta, salida):
            break


# Vehiculo preferido por tipo de ruta (si no hay, se usa cualquiera disponible).
PREFERENCIA = {
    'troncal': ['articulado', 'padron'],
    'expresa': ['articulado', 'padron'],
    'pretroncal': ['padron', 'articulado'],
    'alimentadora': ['buseton', 'padron'],
    'complementaria': ['buseton', 'padron'],
}


def _despachar(ruta, salida):
    buses = list(servicios.buses_disponibles())
    conductores = list(servicios.conductores_disponibles())
    random.shuffle(buses)
    orden = PREFERENCIA.get(ruta.tipo, [])
    buses.sort(key=lambda b: orden.index(b.tipologia) if b.tipologia in orden else len(orden))
    for bus in buses:
        aptos = [c for c in conductores if c.puede_conducir(bus)]
        if not aptos:
            continue
        try:
            despacho = servicios.crear_despacho(
                ruta=ruta, bus=bus, conductor=random.choice(aptos), usuario=None,
                hora_programada=salida, salir_ahora=True, ahora=salida,
                observaciones=f'Despacho automático {ETIQUETA}.')
        except (servicios.ErrorDespacho, IntegrityError):
            # Otro proceso lo tomo primero; se intenta con el siguiente.
            continue
        EventoDespacho.objects.filter(despacho=despacho).update(creado=salida)
        return True
    return False
