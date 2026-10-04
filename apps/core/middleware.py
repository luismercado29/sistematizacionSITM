from django.conf import settings


def _politica():
    imagenes = ["'self'", 'data:', 'https://tile.openstreetmap.org']
    if settings.MAPBOX_TOKEN:
        imagenes.append('https://api.mapbox.com')
    directivas = {
        'default-src': ["'self'"],
        # Sin scripts en linea: solo archivos propios y Leaflet desde cdnjs (con SRI).
        'script-src': ["'self'", 'https://cdnjs.cloudflare.com'],
        # Los atributos style="" de las plantillas requieren 'unsafe-inline' en estilos
        # (no permite ejecutar codigo).
        'style-src': ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com', 'https://cdnjs.cloudflare.com'],
        'font-src': ["'self'", 'https://fonts.gstatic.com'],
        'img-src': imagenes,
        'connect-src': ["'self'"],
        'object-src': ["'none'"],
        'base-uri': ["'self'"],
        'form-action': ["'self'"],
        'frame-ancestors': ["'none'"],
    }
    return '; '.join(f'{k} {" ".join(v)}' for k, v in directivas.items())


class CabecerasSeguridad:
    """Content-Security-Policy y Permissions-Policy en todas las respuestas."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.csp = _politica()

    def __call__(self, request):
        respuesta = self.get_response(request)
        respuesta.headers.setdefault('Content-Security-Policy', self.csp)
        respuesta.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()')
        return respuesta
