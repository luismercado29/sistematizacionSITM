from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.flota.models import Bus, Conductor
from apps.red.models import Ruta


class Despacho(models.Model):
    class Estado(models.TextChoices):
        PROGRAMADO = 'programado', 'Programado'
        EN_RUTA = 'en_ruta', 'En ruta'
        FINALIZADO = 'finalizado', 'Finalizado'
        CANCELADO = 'cancelado', 'Cancelado'

    ACTIVOS = (Estado.PROGRAMADO, Estado.EN_RUTA)

    ruta = models.ForeignKey(Ruta, on_delete=models.PROTECT, related_name='despachos')
    bus = models.ForeignKey(Bus, on_delete=models.PROTECT, related_name='despachos')
    conductor = models.ForeignKey(Conductor, on_delete=models.PROTECT, related_name='despachos')
    despachador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='despachos')
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PROGRAMADO)
    hora_programada = models.DateTimeField()
    hora_salida = models.DateTimeField(null=True, blank=True)
    hora_llegada = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-hora_programada']
        indexes = [
            models.Index(fields=['estado', 'hora_programada']),
            models.Index(fields=['ruta', 'hora_salida']),
        ]
        # Garantia a nivel de base de datos: un bus o un conductor no pueden
        # estar en dos despachos activos a la vez, aunque dos despachadores
        # guarden al mismo tiempo.
        constraints = [
            models.UniqueConstraint(fields=['bus'], condition=Q(estado__in=['programado', 'en_ruta']),
                                    name='un_despacho_activo_por_bus'),
            models.UniqueConstraint(fields=['conductor'], condition=Q(estado__in=['programado', 'en_ruta']),
                                    name='un_despacho_activo_por_conductor'),
        ]

    def __str__(self):
        return f'{self.folio} · {self.ruta.codigo} · {self.bus}'

    @property
    def folio(self):
        return f'D-{self.pk:06d}' if self.pk else 'D-nuevo'

    @property
    def activo(self):
        return self.estado in self.ACTIVOS

    @property
    def duracion_real_min(self):
        if self.hora_salida and self.hora_llegada:
            return round((self.hora_llegada - self.hora_salida).total_seconds() / 60)
        return None

    @property
    def demora_salida_min(self):
        """Minutos entre lo programado y la salida real (negativo = salio antes)."""
        if self.hora_salida:
            return round((self.hora_salida - self.hora_programada).total_seconds() / 60)
        return None


class EventoDespacho(models.Model):
    """Bitacora inmutable de lo que paso con cada despacho."""

    class Tipo(models.TextChoices):
        CREADO = 'creado', 'Despacho creado'
        SALIDA = 'salida', 'Salida a ruta'
        LLEGADA = 'llegada', 'Llegada a destino'
        INCIDENTE = 'incidente', 'Incidente'
        CANCELACION = 'cancelacion', 'Cancelación'
        NOTA = 'nota', 'Nota'

    despacho = models.ForeignKey(Despacho, on_delete=models.CASCADE, related_name='eventos')
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    descripcion = models.CharField('descripción', max_length=280, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'evento de despacho'
        verbose_name_plural = 'eventos de despacho'
        ordering = ['-creado']

    def __str__(self):
        return f'{self.despacho.folio} · {self.get_tipo_display()}'


class PosicionGPS(models.Model):
    """Reporte de posicion enviado por el equipo a bordo del bus."""

    bus = models.ForeignKey(Bus, on_delete=models.CASCADE, related_name='posiciones')
    despacho = models.ForeignKey(Despacho, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='posiciones')
    latitud = models.DecimalField(max_digits=9, decimal_places=6)
    longitud = models.DecimalField(max_digits=9, decimal_places=6)
    velocidad_kmh = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    registrado = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = 'posición GPS'
        verbose_name_plural = 'posiciones GPS'
        ordering = ['-registrado']
        indexes = [models.Index(fields=['despacho', '-registrado'])]

    def __str__(self):
        return f'{self.bus} @ {self.registrado:%H:%M:%S}'
