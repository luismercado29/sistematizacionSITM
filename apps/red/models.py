from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.core.geo import acumulado_km, distancia_km, ubicar_en_linea


class Estacion(models.Model):
    class Tipo(models.TextChoices):
        PORTAL = 'portal', 'Portal'
        ESTACION = 'estacion', 'Estación troncal'
        PARADA = 'parada', 'Parada de alimentación'

    codigo = models.SlugField('código', max_length=20, unique=True,
                              help_text='Identificador corto, p. ej. "bazurto". Se usa en las URL públicas.')
    nombre = models.CharField(max_length=80)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.ESTACION)
    latitud = models.DecimalField(max_digits=9, decimal_places=6,
                                  validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitud = models.DecimalField(max_digits=9, decimal_places=6,
                                   validators=[MinValueValidator(-180), MaxValueValidator(180)])
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'estación'
        verbose_name_plural = 'estaciones'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @property
    def coordenadas(self):
        return float(self.latitud), float(self.longitud)


class Ruta(models.Model):
    class Tipo(models.TextChoices):
        TRONCAL = 'troncal', 'Troncal'
        EXPRESA = 'expresa', 'Expresa'
        PRETRONCAL = 'pretroncal', 'Pretroncal'
        ALIMENTADORA = 'alimentadora', 'Alimentadora'
        COMPLEMENTARIA = 'complementaria', 'Complementaria'

    codigo = models.CharField('código', max_length=10, unique=True,
                              help_text='Código visible para el pasajero, p. ej. "T101".')
    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.TRONCAL)
    color = models.CharField(max_length=7, default='#1D4ED8',
                             validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Usa un color hexadecimal, p. ej. #1D4ED8.')])
    frecuencia_min = models.PositiveSmallIntegerField(
        'frecuencia objetivo (min)', default=10,
        validators=[MinValueValidator(1), MaxValueValidator(120)],
        help_text='Cada cuántos minutos debería salir un bus en hora valle.')
    velocidad_kmh = models.PositiveSmallIntegerField(
        'velocidad comercial (km/h)', default=20,
        validators=[MinValueValidator(5), MaxValueValidator(80)],
        help_text='Promedio incluyendo detenciones. Se usa para estimar tiempos de llegada.')
    horario = models.CharField(max_length=160, blank=True,
                               help_text='Horario de operación que ve el pasajero.')
    trazado = models.JSONField(
        default=list, blank=True,
        help_text='Recorrido por la vía como lista [[lat, lng], ...]. Vacío = línea recta entre paradas.')
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} · {self.nombre}'

    @property
    def origen(self):
        primera = self.paradas.select_related('estacion').first()
        return primera.estacion if primera else None

    @property
    def destino(self):
        ultima = self.paradas.select_related('estacion').last()
        return ultima.estacion if ultima else None

    @property
    def duracion_min(self):
        ultima = self.paradas.last()
        return ultima.minutos_desde_inicio if ultima else 0

    @property
    def longitud_km(self):
        ultima = self.paradas.last()
        return float(ultima.distancia_km) if ultima else 0.0

    def recalcular_tiempos(self):
        """Recalcula distancia acumulada y minutos de cada parada.

        Con ``trazado`` (la via real) cada parada se ubica sobre el recorrido
        avanzando siempre hacia adelante, asi en rutas de ida y vuelta una misma
        estacion queda en el km correcto de cada sentido. Sin trazado se usa la
        linea recta entre paradas por un factor de 1.25 que aproxima la red vial.
        """
        paradas = list(self.paradas.select_related('estacion'))
        if len(self.trazado) >= 2:
            puntos = [tuple(p) for p in self.trazado]
            acumulado = acumulado_km(puntos)
            desde, km_previo = 0, 0.0
            for i, parada in enumerate(paradas):
                if i == 0:
                    km = 0.0
                elif i == len(paradas) - 1 and parada.estacion_id == paradas[0].estacion_id:
                    km = acumulado[-1]  # recorrido circular: termina donde empezo
                else:
                    km, desde, _ = ubicar_en_linea(puntos, acumulado, parada.estacion.coordenadas, desde)
                    km = max(km, km_previo)
                parada.distancia_km = round(km, 2)
                km_previo = km
        else:
            acumulado, anterior = 0.0, None
            for parada in paradas:
                if anterior is not None:
                    acumulado += distancia_km(anterior.coordenadas, parada.estacion.coordenadas) * 1.25
                parada.distancia_km = round(acumulado, 2)
                anterior = parada.estacion
        for parada in paradas:
            parada.minutos_desde_inicio = round(float(parada.distancia_km) / self.velocidad_kmh * 60)
        ParadaRuta.objects.bulk_update(paradas, ['distancia_km', 'minutos_desde_inicio'])


class ParadaRuta(models.Model):
    ruta = models.ForeignKey(Ruta, on_delete=models.CASCADE, related_name='paradas')
    estacion = models.ForeignKey(Estacion, on_delete=models.PROTECT, related_name='paradas')
    orden = models.PositiveSmallIntegerField()
    distancia_km = models.DecimalField('distancia desde el origen (km)', max_digits=6,
                                       decimal_places=2, default=0)
    minutos_desde_inicio = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'parada de ruta'
        verbose_name_plural = 'paradas de ruta'
        ordering = ['ruta', 'orden']
        constraints = [
            models.UniqueConstraint(fields=['ruta', 'orden'], name='parada_orden_unico_por_ruta'),
        ]

    def __str__(self):
        return f'{self.ruta.codigo} #{self.orden} {self.estacion}'
