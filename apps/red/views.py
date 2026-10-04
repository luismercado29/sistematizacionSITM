from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.roles import es_supervisor, operador_requerido, supervisor_requerido
from apps.despacho.models import Despacho

from .forms import RutaForm
from .models import Ruta


@operador_requerido
def rutas(request):
    qs = (Ruta.objects.prefetch_related('paradas__estacion')
          .annotate(en_ruta=Count('despachos', filter=Q(despachos__estado=Despacho.Estado.EN_RUTA))))
    return render(request, 'operacion/red/rutas.html', {'rutas': qs})


def _detalle(request, ruta, form, status=200):
    return render(request, 'operacion/red/ruta.html', {
        'ruta': ruta,
        'paradas': list(ruta.paradas.select_related('estacion')),
        'ruta_lista': Ruta.objects.filter(pk=ruta.pk).prefetch_related('paradas__estacion'),
        'form': form,
    }, status=status)


@operador_requerido
def ruta(request, pk):
    ruta = get_object_or_404(Ruta, pk=pk)
    return _detalle(request, ruta, RutaForm(instance=ruta) if es_supervisor(request.user) else None)


@supervisor_requerido
def ruta_guardar(request, pk):
    ruta = get_object_or_404(Ruta, pk=pk)
    form = RutaForm(request.POST, instance=ruta)
    if not form.is_valid():
        return _detalle(request, ruta, form, status=400)
    velocidad_cambio = 'velocidad_kmh' in form.changed_data
    ruta = form.save()
    if velocidad_cambio:
        ruta.recalcular_tiempos()
    messages.success(request, f'Ruta {ruta.codigo} actualizada.')
    return redirect('operacion:ruta', pk=pk)
