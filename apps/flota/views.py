from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.roles import operador_requerido, supervisor_requerido
from apps.despacho.models import Despacho

from .forms import BusForm, ConductorForm
from .models import Bus, Conductor


def _despacho_activo():
    return Prefetch('despachos', to_attr='activos',
                    queryset=Despacho.objects.filter(estado__in=Despacho.ACTIVOS).select_related('ruta'))


@operador_requerido
def buses(request):
    estado = request.GET.get('estado', '')
    qs = Bus.objects.prefetch_related(_despacho_activo())
    if estado in Bus.Estado.values:
        qs = qs.filter(estado=estado)
    conteo = dict(Bus.objects.values_list('estado').annotate(n=Count('id')))
    filtros = [('', 'Todos', sum(conteo.values()))] + [
        (valor, etiqueta, conteo.get(valor, 0)) for valor, etiqueta in Bus.Estado.choices]
    return render(request, 'operacion/flota/buses.html', {
        'buses': qs, 'filtros': filtros, 'estado': estado,
    })


@supervisor_requerido
def bus_form(request, pk=None):
    bus = get_object_or_404(Bus, pk=pk) if pk else None
    form = BusForm(request.POST or None, instance=bus)
    if request.method == 'POST' and form.is_valid():
        bus = form.save()
        messages.success(request, f'Bus {bus} guardado.')
        return redirect('operacion:buses')
    return render(request, 'operacion/flota/form.html', {
        'form': form, 'objeto': bus, 'titulo': f'Editar bus {bus}' if bus else 'Registrar bus',
        'volver': 'operacion:buses', 'icono': 'bus',
    })


@operador_requerido
def conductores(request):
    q = request.GET.get('q', '').strip()
    qs = Conductor.objects.prefetch_related(_despacho_activo()).annotate(
        recorridos_hoy=Count('despachos', filter=Q(
            despachos__estado=Despacho.Estado.FINALIZADO,
            despachos__hora_salida__date=timezone.localdate())))
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(documento__icontains=q) | Q(licencia__icontains=q))
    return render(request, 'operacion/flota/conductores.html', {'conductores': qs, 'q': q})


@supervisor_requerido
def conductor_form(request, pk=None):
    conductor = get_object_or_404(Conductor, pk=pk) if pk else None
    form = ConductorForm(request.POST or None, instance=conductor)
    if request.method == 'POST' and form.is_valid():
        conductor = form.save()
        messages.success(request, f'Conductor {conductor} guardado.')
        return redirect('operacion:conductores')
    return render(request, 'operacion/flota/form.html', {
        'form': form, 'objeto': conductor,
        'titulo': f'Editar a {conductor}' if conductor else 'Registrar conductor',
        'volver': 'operacion:conductores', 'icono': 'licencia',
    })
