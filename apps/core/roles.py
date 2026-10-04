"""Roles de la operacion.

* Despachadores: crean, inician, cierran y cancelan despachos.
* Supervisores: ademas administran flota, conductores y rutas.

Los superusuarios tienen todos los permisos. Las cuentas se crean desde
/admin/ (no hay registro publico: es un sistema interno).
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

DESPACHADORES = 'Despachadores'
SUPERVISORES = 'Supervisores'


def _grupos(user):
    if not hasattr(user, '_sitm_grupos'):
        user._sitm_grupos = set(user.groups.values_list('name', flat=True))
    return user._sitm_grupos


def es_operador(user):
    return user.is_authenticated and (
        user.is_superuser or bool(_grupos(user) & {DESPACHADORES, SUPERVISORES}))


def es_supervisor(user):
    return user.is_authenticated and (user.is_superuser or SUPERVISORES in _grupos(user))


def nombre_rol(user):
    if user.is_superuser:
        return 'Administrador'
    if es_supervisor(user):
        return 'Supervisor'
    if es_operador(user):
        return 'Despachador'
    return 'Sin rol asignado'


def _requiere(prueba):
    def decorador(vista):
        @login_required
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not prueba(request.user):
                raise PermissionDenied
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


operador_requerido = _requiere(es_operador)
supervisor_requerido = _requiere(es_supervisor)
