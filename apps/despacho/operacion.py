"""Indicadores de operacion para el tablero del despachador."""

from datetime import timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.flota.models import Bus, Conductor
from apps.red.models import Ruta

from .models import Despacho


def inicio_del_dia(ahora=None):
    ahora = timezone.localtime(ahora or timezone.now())
    return ahora.replace(hour=0, minute=0, second=0, microsecond=0)


def indicadores(ahora=None):
    ahora = ahora or timezone.now()
    hoy = Despacho.objects.filter(hora_programada__gte=inicio_del_dia(ahora))
    conteo_hoy = hoy.aggregate(
        total=Count('id'),
        finalizados=Count('id', filter=Q(estado=Despacho.Estado.FINALIZADO)),
        cancelados=Count('id', filter=Q(estado=Despacho.Estado.CANCELADO)),
        # Puntual = salio a mas tardar 3 minutos despues de lo programado.
        con_salida=Count('id', filter=Q(hora_salida__isnull=False)),
    )
    puntuales = sum(1 for d in hoy.filter(hora_salida__isnull=False).only('hora_salida', 'hora_programada')
                    if d.hora_salida - d.hora_programada <= timedelta(minutes=3))
    flota = Bus.objects.aggregate(
        total=Count('id'),
        en_servicio=Count('id', filter=Q(estado=Bus.Estado.EN_SERVICIO)),
        disponibles=Count('id', filter=Q(estado=Bus.Estado.DISPONIBLE)),
        taller=Count('id', filter=Q(estado__in=[Bus.Estado.MANTENIMIENTO, Bus.Estado.FUERA_SERVICIO])),
    )
    limite_licencia = timezone.localdate() + timedelta(days=30)
    return {
        'despachos_hoy': conteo_hoy['total'],
        'finalizados_hoy': conteo_hoy['finalizados'],
        'cancelados_hoy': conteo_hoy['cancelados'],
        'puntualidad': round(puntuales / conteo_hoy['con_salida'] * 100) if conteo_hoy['con_salida'] else None,
        'flota': flota,
        'disponibilidad': round(flota['disponibles'] / flota['total'] * 100) if flota['total'] else 0,
        'conductores_activos': Conductor.objects.filter(estado=Conductor.Estado.ACTIVO).count(),
        'licencias_por_vencer': Conductor.objects.filter(
            estado=Conductor.Estado.ACTIVO, vencimiento_licencia__lte=limite_licencia).count(),
    }


def estado_rutas(ahora=None):
    """Cumplimiento de frecuencia por ruta: cuando salio el ultimo bus y cuando toca el siguiente."""
    ahora = ahora or timezone.now()
    rutas = (Ruta.objects.filter(activa=True)
             .annotate(ultima_salida=Max('despachos__hora_salida'),
                       en_ruta=Count('despachos', filter=Q(despachos__estado=Despacho.Estado.EN_RUTA)),
                       programados=Count('despachos', filter=Q(despachos__estado=Despacho.Estado.PROGRAMADO)),
                       salidas_hoy=Count('despachos', filter=Q(despachos__hora_salida__gte=inicio_del_dia(ahora))))
             .order_by('codigo'))
    filas = []
    for ruta in rutas:
        if ruta.ultima_salida:
            transcurrido = (ahora - ruta.ultima_salida).total_seconds() / 60
            faltan = round(ruta.frecuencia_min - transcurrido)
        else:
            transcurrido, faltan = None, 0
        if ruta.programados:
            situacion = 'programado'
        elif faltan < -ruta.frecuencia_min / 2:
            situacion = 'atrasado'
        elif faltan <= 0:
            situacion = 'toca'
        else:
            situacion = 'al_dia'
        filas.append({
            'ruta': ruta,
            'en_ruta': ruta.en_ruta,
            'programados': ruta.programados,
            'salidas_hoy': ruta.salidas_hoy,
            'minutos_desde_ultima': round(transcurrido) if transcurrido is not None else None,
            'faltan': faltan,
            'situacion': situacion,
        })
    return filas
