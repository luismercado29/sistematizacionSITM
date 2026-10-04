import secrets

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone


def generar_token_gps():
    return secrets.token_urlsafe(24)


class Bus(models.Model):
    class Tipologia(models.TextChoices):
        ARTICULADO = 'articulado', 'Articulado'
        PADRON = 'padron', 'Padrón'
        BUSETON = 'buseton', 'Busetón'

    class Estado(models.TextChoices):
        DISPONIBLE = 'disponible', 'Disponible'
        EN_SERVICIO = 'en_servicio', 'En servicio'
        MANTENIMIENTO = 'mantenimiento', 'En mantenimiento'
        FUERA_SERVICIO = 'fuera_servicio', 'Fuera de servicio'

    numero = models.CharField('número interno', max_length=12, unique=True,
                              help_text='Número pintado en el vehículo, p. ej. "TC-1024".')
    placa = models.CharField(max_length=7, unique=True,
                             validators=[RegexValidator(r'^[A-Z]{3}\d{3}$', 'Formato de placa: ABC123.')])
    tipologia = models.CharField('tipología', max_length=12, choices=Tipologia.choices,
                                 default=Tipologia.PADRON)
    capacidad = models.PositiveSmallIntegerField(
        default=80, validators=[MinValueValidator(10), MaxValueValidator(250)],
        help_text='Pasajeros sentados más de pie.')
    operador = models.CharField(max_length=60, blank=True,
                                help_text='Empresa concesionaria que opera el vehículo.')
    modelo = models.PositiveSmallIntegerField(
        'año modelo', null=True, blank=True,
        validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.DISPONIBLE)
    token_gps = models.CharField(
        'token del dispositivo GPS', max_length=40, unique=True, default=generar_token_gps,
        editable=False,
        help_text='Credencial con la que el equipo a bordo reporta su posición.')

    class Meta:
        verbose_name = 'bus'
        verbose_name_plural = 'buses'
        ordering = ['numero']

    def __str__(self):
        return self.numero


class Conductor(models.Model):
    class Categoria(models.TextChoices):
        C2 = 'C2', 'C2 · Servicio público (bus/busetón)'
        C3 = 'C3', 'C3 · Servicio público (articulado)'

    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        DESCANSO = 'descanso', 'En descanso'
        INCAPACITADO = 'incapacitado', 'Incapacitado'
        INACTIVO = 'inactivo', 'Inactivo'

    nombre = models.CharField('nombre completo', max_length=80)
    documento = models.CharField('cédula', max_length=12, unique=True,
                                 validators=[RegexValidator(r'^\d{6,12}$', 'Solo números, entre 6 y 12 dígitos.')])
    telefono = models.CharField('teléfono', max_length=15, blank=True)
    licencia = models.CharField('número de licencia', max_length=20, unique=True)
    categoria = models.CharField('categoría', max_length=2, choices=Categoria.choices,
                                 default=Categoria.C2)
    vencimiento_licencia = models.DateField('vencimiento de la licencia')
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.ACTIVO)

    class Meta:
        verbose_name = 'conductor'
        verbose_name_plural = 'conductores'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @property
    def licencia_vigente(self):
        return self.vencimiento_licencia >= timezone.localdate()

    @property
    def dias_para_vencer(self):
        return (self.vencimiento_licencia - timezone.localdate()).days

    def puede_conducir(self, bus):
        """Un articulado exige categoria C3; los demas aceptan C2 o C3."""
        if bus.tipologia == Bus.Tipologia.ARTICULADO:
            return self.categoria == self.Categoria.C3
        return True
