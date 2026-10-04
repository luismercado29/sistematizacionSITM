"""Limites de intentos (fuerza bruta en el login, abuso del endpoint GPS).

Usan la cache de Django. Con la cache por defecto (memoria local) cada
proceso lleva su propia cuenta: en serverless eso frena ataques desde una
misma conexion, pero para un limite global configura una cache compartida
(p. ej. Redis) en ``CACHES``.
"""

from django.conf import settings
from django.core.cache import cache


def ip_cliente(request):
    # Detras del proxy de Vercel la IP real llega en X-Forwarded-For. Fuera de
    # el, esa cabecera la puede inventar el cliente, asi que no se usa.
    if getattr(settings, 'CONFIAR_X_FORWARDED_FOR', False):
        reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if reenviada:
            return reenviada.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'desconocida')


def excedido(clave, limite):
    return cache.get(clave, 0) >= limite


def sumar(clave, ventana_s):
    if cache.add(clave, 1, ventana_s):
        return 1
    try:
        return cache.incr(clave)
    except ValueError:  # expiro entre add e incr
        cache.add(clave, 1, ventana_s)
        return 1


def limpiar(*claves):
    cache.delete_many(claves)
