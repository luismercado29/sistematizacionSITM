# Create your models here.
from django.db import models


# Create your models here.

class Bus(models.Model):
    bus_name = models.CharField(max_length=30)
    source = models.CharField(max_length=30)
    dest = models.CharField(max_length=30)
    nos = models.CharField(max_length=30)
    rem = models.CharField(max_length=30)
    
    price = models.CharField(max_length=30)
    date = models.DateField()
    time = models.TimeField()

    class Meta:
        # Sin esto Django pluraliza anadiendo una 's' y muestra "Buss".
        verbose_name = 'bus'
        verbose_name_plural = 'buses'

    def __str__(self):
        return self.bus_name

class Drivers(models.Model):
    id = models.AutoField(primary_key=True)
    nombre= models.CharField(max_length=50)
    licencia= models.CharField(max_length=10)

    class Meta:
        # Igual que arriba: por defecto se mostraba como "Driverss".
        verbose_name = 'conductor'
        verbose_name_plural = 'conductores'

    def __str__(self):
        return f'{self.nombre} ({self.licencia})'

class User(models.Model):
    """Modelo heredado. La autenticacion usa django.contrib.auth.models.User.

    Se conserva porque su tabla ya existe con datos, pero no interviene en el
    login ni en los permisos.
    """

    user_id = models.AutoField(primary_key=True)
    email = models.EmailField()
    name = models.CharField(max_length=30)
    password = models.CharField(max_length=30)

    class Meta:
        verbose_name = 'usuario (modelo heredado)'
        verbose_name_plural = 'usuarios (modelo heredado)'

    def __str__(self):
        return self.email


class Book(models.Model):
    DESPACHADO = 'R'
    CANCELADO = 'C'

    TICKET_STATUSES = ((DESPACHADO, 'Despachado'),
                       (CANCELADO, 'Cancelado'),)
    email = models.EmailField()
    name = models.CharField(max_length=30)
    userid =models.DecimalField(decimal_places=0, max_digits=2)
    busid=models.DecimalField(decimal_places=0, max_digits=2)
    bus_name = models.CharField(max_length=30)
    source = models.CharField(max_length=30)
    dest = models.CharField(max_length=30)
    nos = models.CharField(max_length=30)
    price = models.CharField(max_length=30)
    date = models.DateField()
    time = models.TimeField()
    status = models.CharField(choices=TICKET_STATUSES, default=DESPACHADO, max_length=2)

    class Meta:
        verbose_name = 'despacho'
        verbose_name_plural = 'despachos'

    def __str__(self):
        return self.email
