from django.conf import settings
from django.utils.functional import SimpleLazyObject

from .roles import es_operador, es_supervisor, nombre_rol


def _buses_en_ruta():
    from apps.despacho.models import Despacho
    return Despacho.objects.filter(estado=Despacho.Estado.EN_RUTA).count()


def sitm(request):
    user = getattr(request, 'user', None)
    autenticado = bool(user and user.is_authenticated)
    operador = autenticado and es_operador(user)
    return {
        'MODO_DEMO': settings.SITM_MODO_DEMO,
        'REFRESCO_S': settings.SITM_REFRESCO_S,
        'MAPBOX_TOKEN': settings.MAPBOX_TOKEN,
        'es_operador': operador,
        'es_supervisor': autenticado and es_supervisor(user),
        'rol_usuario': nombre_rol(user) if autenticado else '',
        # Perezoso: solo consulta la base si la plantilla lo usa (menu lateral).
        'nav_en_ruta': SimpleLazyObject(_buses_en_ruta) if operador else 0,
    }
