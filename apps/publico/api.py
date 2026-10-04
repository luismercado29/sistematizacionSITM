"""API JSON v1.

Lectura publica (sin datos personales: nunca se expone el conductor) y un
endpoint de escritura para los equipos GPS a bordo, autenticado con el token
de cada bus.
"""

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core import limites
from apps.despacho import demo, seguimiento
from apps.despacho.models import Despacho, PosicionGPS
from apps.flota.models import Bus
from apps.red.models import Estacion, Ruta

from .views import proximos_por_parada


def _respuesta(datos, status=200):
    datos.setdefault('actualizado', timezone.now().isoformat())
    datos.setdefault('refresco_s', settings.SITM_REFRESCO_S)
    return JsonResponse(datos, status=status, json_dumps_params={'ensure_ascii': False})


@require_GET
@never_cache
def flota(request):
    demo.mantener_operacion()
    ruta = None
    if request.GET.get('ruta'):
        ruta = get_object_or_404(Ruta, codigo__iexact=request.GET['ruta'])
    buses = [e.como_dict() for e in seguimiento.flota_en_vivo(ruta=ruta)]
    return _respuesta({'buses': buses})


@require_GET
@never_cache
def llegadas(request, codigo):
    demo.mantener_operacion()
    estacion = get_object_or_404(Estacion, codigo=codigo, activa=True)
    return _respuesta({
        'estacion': {'codigo': estacion.codigo, 'nombre': estacion.nombre,
                     'lat': float(estacion.latitud), 'lng': float(estacion.longitud)},
        'llegadas': seguimiento.llegadas_a_estacion(estacion),
    })


@require_GET
@never_cache
def ruta_en_vivo(request, codigo):
    demo.mantener_operacion()
    ruta = get_object_or_404(Ruta, codigo__iexact=codigo, activa=True)
    paradas = list(ruta.paradas.select_related('estacion'))
    estados = seguimiento.flota_en_vivo(ruta=ruta)
    proximos = proximos_por_parada(ruta, paradas, estados)
    return _respuesta({
        'ruta': ruta.codigo,
        'buses': [e.como_dict() for e in estados],
        'paradas': [{'codigo': p.estacion.codigo, 'nombre': p.estacion.nombre,
                     'proximo_min': proximos.get(p.pk)} for p in paradas],
    })


@require_GET
def red(request):
    """Rutas activas con sus paradas: el trazado que dibujan los mapas."""
    rutas = Ruta.objects.filter(activa=True).prefetch_related('paradas__estacion')
    return _respuesta({'rutas': [{
        'codigo': r.codigo, 'nombre': r.nombre, 'tipo': r.get_tipo_display(), 'color': r.color,
        'paradas': [{'codigo': p.estacion.codigo, 'nombre': p.estacion.nombre,
                     'lat': float(p.estacion.latitud), 'lng': float(p.estacion.longitud)}
                    for p in r.paradas.all()],
    } for r in rutas]})


@csrf_exempt
@require_POST
def reportar_gps(request):
    """Recibe la posicion del equipo a bordo.

    ``Authorization: Bearer <token del bus>`` y cuerpo JSON
    ``{"lat": 10.41, "lng": -75.53, "velocidad": 32.5, "registrado": "<ISO 8601>"}``
    (``velocidad`` y ``registrado`` son opcionales).
    """
    clave_ip = f'gps:fallos:{limites.ip_cliente(request)}'
    if limites.excedido(clave_ip, 30):
        return JsonResponse({'error': 'Demasiados intentos con token inválido. Espera unos minutos.'}, status=429)
    cabecera = request.headers.get('Authorization', '')
    token = cabecera.removeprefix('Bearer ').strip() if cabecera.startswith('Bearer ') else ''
    bus = Bus.objects.filter(token_gps=token).first() if 0 < len(token) <= 64 else None
    if bus is None:
        limites.sumar(clave_ip, 10 * 60)
        return JsonResponse({'error': 'Token inválido.'}, status=401)
    if len(request.body) > 2048:
        return JsonResponse({'error': 'Cuerpo demasiado grande.'}, status=413)

    try:
        cuerpo = json.loads(request.body or b'{}')
        lat = Decimal(str(cuerpo['lat']))
        lng = Decimal(str(cuerpo['lng']))
        velocidad = Decimal(str(cuerpo['velocidad'])) if cuerpo.get('velocidad') is not None else None
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return JsonResponse({'error': 'Se esperan "lat" y "lng" numéricos.'}, status=400)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return JsonResponse({'error': 'Coordenadas fuera de rango.'}, status=400)
    if velocidad is not None and not (0 <= velocidad <= 200):
        return JsonResponse({'error': 'Velocidad fuera de rango (0 a 200 km/h).'}, status=400)

    # Un equipo normal reporta cada 5-10 s; mas rapido que 1 por segundo es un error o abuso.
    if limites.sumar(f'gps:bus:{bus.pk}', 1) > 1:
        return JsonResponse({'error': 'Reportes demasiado seguidos para este bus.'}, status=429)

    ahora = timezone.now()
    registrado = parse_datetime(cuerpo['registrado']) if cuerpo.get('registrado') else None
    # Relojes de equipos desajustados: no se aceptan marcas futuras ni muy viejas.
    if registrado is None or timezone.is_naive(registrado) or not (
            ahora - timedelta(minutes=10) <= registrado <= ahora + timedelta(seconds=30)):
        registrado = ahora

    despacho = Despacho.objects.filter(bus=bus, estado=Despacho.Estado.EN_RUTA).first()
    PosicionGPS.objects.create(bus=bus, despacho=despacho, latitud=lat.quantize(Decimal('0.000001')),
                               longitud=lng.quantize(Decimal('0.000001')), velocidad_kmh=velocidad,
                               registrado=registrado)
    return JsonResponse({'ok': True, 'despacho': despacho.folio if despacho else None}, status=201)
