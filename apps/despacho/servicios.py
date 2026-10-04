"""Reglas de negocio del despacho.

Las vistas, el admin y los comandos pasan siempre por aqui para que las
validaciones (bus disponible, licencia vigente, categoria compatible, un solo
despacho activo) se apliquen igual sin importar desde donde se despache.
"""

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.flota.models import Bus, Conductor

from .models import Despacho, EventoDespacho


class ErrorDespacho(Exception):
    """Operacion de despacho no permitida. El mensaje se muestra al usuario."""


def buses_disponibles():
    activos = Despacho.objects.filter(bus=OuterRef('pk'), estado__in=Despacho.ACTIVOS)
    return Bus.objects.filter(estado=Bus.Estado.DISPONIBLE).exclude(Exists(activos))


def conductores_disponibles():
    activos = Despacho.objects.filter(conductor=OuterRef('pk'), estado__in=Despacho.ACTIVOS)
    return (Conductor.objects
            .filter(estado=Conductor.Estado.ACTIVO,
                    vencimiento_licencia__gte=timezone.localdate())
            .exclude(Exists(activos)))


def _registrar(despacho, tipo, usuario, descripcion=''):
    return EventoDespacho.objects.create(despacho=despacho, tipo=tipo, usuario=usuario,
                                         descripcion=descripcion[:280])


def crear_despacho(*, ruta, bus, conductor, usuario, hora_programada=None,
                   salir_ahora=False, observaciones='', ahora=None):
    ahora = ahora or timezone.now()
    hora_programada = hora_programada or ahora

    if not ruta.activa:
        raise ErrorDespacho(f'La ruta {ruta.codigo} está inactiva.')
    if not ruta.paradas.exists():
        raise ErrorDespacho(f'La ruta {ruta.codigo} no tiene paradas configuradas.')

    with transaction.atomic():
        # Bloquea las filas para que dos despachadores no asignen el mismo bus
        # o conductor en paralelo.
        bus = Bus.objects.select_for_update().get(pk=bus.pk)
        conductor = Conductor.objects.select_for_update().get(pk=conductor.pk)

        if bus.estado != Bus.Estado.DISPONIBLE:
            raise ErrorDespacho(f'El bus {bus} no está disponible ({bus.get_estado_display().lower()}).')
        if Despacho.objects.filter(bus=bus, estado__in=Despacho.ACTIVOS).exists():
            raise ErrorDespacho(f'El bus {bus} ya tiene un despacho activo.')
        if conductor.estado != Conductor.Estado.ACTIVO:
            raise ErrorDespacho(f'{conductor} no está activo ({conductor.get_estado_display().lower()}).')
        if not conductor.licencia_vigente:
            raise ErrorDespacho(f'La licencia de {conductor} venció el {conductor.vencimiento_licencia:%d/%m/%Y}.')
        if not conductor.puede_conducir(bus):
            raise ErrorDespacho(f'{conductor} tiene licencia {conductor.categoria}; '
                                f'un bus {bus.get_tipologia_display().lower()} exige C3.')
        if Despacho.objects.filter(conductor=conductor, estado__in=Despacho.ACTIVOS).exists():
            raise ErrorDespacho(f'{conductor} ya está asignado a otro despacho activo.')

        try:
            despacho = Despacho.objects.create(
                ruta=ruta, bus=bus, conductor=conductor, despachador=usuario,
                hora_programada=hora_programada, observaciones=observaciones.strip(),
            )
        except IntegrityError as exc:
            raise ErrorDespacho('El bus o el conductor acaba de ser asignado por otro usuario. '
                                'Actualiza la página e inténtalo de nuevo.') from exc
        _registrar(despacho, EventoDespacho.Tipo.CREADO, usuario,
                   f'Programado para las {timezone.localtime(hora_programada):%H:%M}.')

        if salir_ahora:
            despacho = iniciar_despacho(despacho, usuario, ahora=ahora)
    return despacho


def iniciar_despacho(despacho, usuario, ahora=None):
    ahora = ahora or timezone.now()
    with transaction.atomic():
        despacho = Despacho.objects.select_for_update().get(pk=despacho.pk)
        if despacho.estado != Despacho.Estado.PROGRAMADO:
            raise ErrorDespacho(f'{despacho.folio} no se puede iniciar: está {despacho.get_estado_display().lower()}.')
        despacho.estado = Despacho.Estado.EN_RUTA
        despacho.hora_salida = ahora
        despacho.save(update_fields=['estado', 'hora_salida'])
        Bus.objects.filter(pk=despacho.bus_id).update(estado=Bus.Estado.EN_SERVICIO)
        _registrar(despacho, EventoDespacho.Tipo.SALIDA, usuario,
                   f'Salió de {despacho.ruta.origen} a las {timezone.localtime(ahora):%H:%M}.')
    return despacho


def finalizar_despacho(despacho, usuario, observacion='', ahora=None):
    ahora = ahora or timezone.now()
    with transaction.atomic():
        despacho = Despacho.objects.select_for_update().get(pk=despacho.pk)
        if despacho.estado != Despacho.Estado.EN_RUTA:
            raise ErrorDespacho(f'{despacho.folio} no está en ruta.')
        despacho.estado = Despacho.Estado.FINALIZADO
        despacho.hora_llegada = ahora
        despacho.save(update_fields=['estado', 'hora_llegada'])
        _liberar_bus(despacho)
        texto = f'Llegó a {despacho.ruta.destino} a las {timezone.localtime(ahora):%H:%M}.'
        if observacion:
            texto += f' {observacion}'
        _registrar(despacho, EventoDespacho.Tipo.LLEGADA, usuario, texto)
    return despacho


def cancelar_despacho(despacho, usuario, motivo, ahora=None):
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorDespacho('Indica el motivo de la cancelación.')
    ahora = ahora or timezone.now()
    with transaction.atomic():
        despacho = Despacho.objects.select_for_update().get(pk=despacho.pk)
        if not despacho.activo:
            raise ErrorDespacho(f'{despacho.folio} ya está {despacho.get_estado_display().lower()}.')
        despacho.estado = Despacho.Estado.CANCELADO
        if despacho.hora_salida:
            despacho.hora_llegada = ahora
        despacho.save(update_fields=['estado', 'hora_llegada'])
        _liberar_bus(despacho)
        _registrar(despacho, EventoDespacho.Tipo.CANCELACION, usuario, motivo)
    return despacho


def registrar_novedad(despacho, usuario, descripcion, incidente=False):
    descripcion = (descripcion or '').strip()
    if not descripcion:
        raise ErrorDespacho('Escribe la descripción de la novedad.')
    tipo = EventoDespacho.Tipo.INCIDENTE if incidente else EventoDespacho.Tipo.NOTA
    return _registrar(despacho, tipo, usuario, descripcion)


def _liberar_bus(despacho):
    # Solo vuelve a "disponible" si seguia en servicio: si alguien lo mando a
    # mantenimiento mientras rodaba, se respeta ese estado.
    Bus.objects.filter(pk=despacho.bus_id, estado=Bus.Estado.EN_SERVICIO).update(
        estado=Bus.Estado.DISPONIBLE)
