from django.apps import AppConfig


class MyappConfig(AppConfig):
    """Tablas del prototipo inicial (reservas de buses).

    Ya no tienen vistas ni rutas: se conservan solo para no perder los datos
    que existan en la base de produccion. Se pueden consultar desde /admin/.
    """

    name = 'myapp'
    verbose_name = 'Sistema anterior (legado)'
