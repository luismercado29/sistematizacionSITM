from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.despacho import demo, seguimiento
from apps.despacho.models import Despacho
from apps.red.models import Estacion, Ruta


def inicio(request):
    demo.mantener_operacion()
    if request.GET.get('estacion'):
        return redirect('publico:estacion', codigo=request.GET['estacion'])
    estaciones = Estacion.objects.filter(activa=True, paradas__ruta__activa=True).distinct()
    rutas = (Ruta.objects.filter(activa=True)
             .annotate(en_ruta=Count('despachos', filter=Q(despachos__estado=Despacho.Estado.EN_RUTA)))
             .prefetch_related('paradas__estacion'))
    return render(request, 'publico/inicio.html', {
        'estaciones': estaciones,
        'rutas': rutas,
        'buses_en_ruta': sum(r.en_ruta for r in rutas),
    })


def estacion(request, codigo):
    demo.mantener_operacion()
    estacion = get_object_or_404(Estacion, codigo=codigo, activa=True)
    rutas = Ruta.objects.filter(activa=True, paradas__estacion=estacion).distinct()
    return render(request, 'publico/estacion.html', {
        'estacion': estacion,
        'rutas': rutas.prefetch_related('paradas__estacion'),
        'llegadas': seguimiento.llegadas_a_estacion(estacion),
        'otras': Estacion.objects.filter(activa=True, paradas__ruta__activa=True).exclude(pk=estacion.pk).distinct(),
    })


def ruta(request, codigo):
    demo.mantener_operacion()
    ruta = get_object_or_404(Ruta, codigo__iexact=codigo, activa=True)
    paradas = list(ruta.paradas.select_related('estacion'))
    proximos = proximos_por_parada(ruta, paradas)
    for p in paradas:
        p.proximo_min = proximos.get(p.pk)
    return render(request, 'publico/ruta.html', {
        'ruta': ruta,
        'paradas': paradas,
        'buses_en_ruta': Despacho.objects.filter(ruta=ruta, estado=Despacho.Estado.EN_RUTA).count(),
        'ruta_lista': Ruta.objects.filter(pk=ruta.pk).prefetch_related('paradas__estacion'),
    })


def mapa(request):
    demo.mantener_operacion()
    return render(request, 'publico/mapa.html', {
        'rutas': Ruta.objects.filter(activa=True).prefetch_related('paradas__estacion'),
    })


def proximos_por_parada(ruta, paradas, estados=None):
    """Minutos hasta el proximo bus en cada parada de la ruta."""
    if estados is None:
        estados = seguimiento.flota_en_vivo(ruta=ruta)
    trazado = seguimiento.Trazado(ruta, paradas)
    resultado = {}
    for parada in paradas[:-1]:
        km = float(parada.distancia_km)
        etas = [trazado.minutos(km - e.km) for e in estados if e.km <= km + seguimiento.TOLERANCIA_KM]
        resultado[parada.pk] = max(0, round(min(etas))) if etas else None
    return resultado
