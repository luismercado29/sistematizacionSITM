from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.shortcuts import render

from . import limites
from .formularios import EstiloSITM

# Intentos fallidos permitidos antes de bloquear temporalmente.
INTENTOS_POR_USUARIO = 5
INTENTOS_POR_IP = 20
BLOQUEO_S = 15 * 60


class IngresarForm(EstiloSITM, AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        # Mismo mensaje exista o no la cuenta: no revela que usuarios hay.
        'invalid_login': 'Usuario o contraseña incorrectos. Revisa mayúsculas y vuelve a intentarlo.',
        'bloqueado': 'Demasiados intentos fallidos. Espera 15 minutos antes de volver a intentarlo.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Usuario'
        self.fields['username'].widget.attrs.update({'autocomplete': 'username', 'autofocus': True})
        self.fields['password'].widget.attrs['autocomplete'] = 'current-password'

    def _claves(self):
        ip = limites.ip_cliente(self.request) if self.request else 'sin-request'
        usuario = (self.data.get('username') or '').strip().lower()[:150]
        return f'login:ip:{ip}', f'login:usuario:{usuario}'

    def clean(self):
        clave_ip, clave_usuario = self._claves()
        if limites.excedido(clave_ip, INTENTOS_POR_IP) or limites.excedido(clave_usuario, INTENTOS_POR_USUARIO):
            raise ValidationError(self.error_messages['bloqueado'], code='bloqueado')
        try:
            datos = super().clean()
        except ValidationError:
            limites.sumar(clave_ip, BLOQUEO_S)
            limites.sumar(clave_usuario, BLOQUEO_S)
            raise
        limites.limpiar(clave_usuario)
        return datos


class IngresarView(LoginView):
    template_name = 'cuentas/ingresar.html'
    authentication_form = IngresarForm
    redirect_authenticated_user = True


def error_403(request, exception=None):
    return render(request, 'errores/error.html', {
        'codigo': 403, 'titulo': 'No tienes acceso a esta sección',
        'detalle': 'Tu cuenta no tiene el rol necesario. Pide a un supervisor que te lo asigne.',
    }, status=403)


def error_404(request, exception=None):
    return render(request, 'errores/error.html', {
        'codigo': 404, 'titulo': 'No encontramos esta página',
        'detalle': 'Puede que el enlace esté mal escrito o que el registro ya no exista.',
    }, status=404)


def error_500(request):
    return render(request, 'errores/error.html', {
        'codigo': 500, 'titulo': 'Algo falló de nuestro lado',
        'detalle': 'El error quedó registrado. Intenta de nuevo en unos minutos.',
    }, status=500)
