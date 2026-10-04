import csv

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.roles import operador_requerido
from apps.red.models import Ruta

from . import demo, operacion, seguimiento, servicios
from .forms import CancelarForm, FiltroDespachosForm, NovedadForm, NuevoDespachoForm
from .models import Despacho, EventoDespacho


@operador_requerido
def tablero(request):
    demo.mantener_operacion()
    ahora = timezone.now()
    context = {
        'kpi': operacion.indicadores(ahora),
        'rutas': operacion.estado_rutas(ahora),
        'proximos': (Despacho.objects.filter(estado=Despacho.Estado.PROGRAMADO)
                     .select_related('ruta', 'bus', 'conductor').order_by('hora_programada')[:6]),
        'eventos': (EventoDespacho.objects.select_related('despacho__ruta', 'despacho__bus', 'usuario')[:8]),
        'en_ruta': sorted(seguimiento.flota_en_vivo(ahora), key=lambda e: -e.progreso),
        'rutas_mapa': Ruta.objects.filter(activa=True).prefetch_related('paradas__estacion'),
    }
    return render(request, 'operacion/tablero.html', context)


def _filtrar(request):
    form = FiltroDespachosForm(request.GET or None)
    qs = Despacho.objects.select_related('ruta', 'bus', 'conductor', 'despachador')
    if form.is_valid():
        datos = form.cleaned_data
        if datos['fecha']:
            qs = qs.filter(hora_programada__date=datos['fecha'])
        if datos['ruta']:
            qs = qs.filter(ruta=datos['ruta'])
        if datos['estado']:
            qs = qs.filter(estado=datos['estado'])
        if datos['q']:
            q = datos['q'].strip()
            filtro = Q(bus__numero__icontains=q) | Q(bus__placa__icontains=q) | Q(conductor__nombre__icontains=q)
            folio = q.upper().removeprefix('D-').lstrip('0')
            if folio.isdigit():
                filtro |= Q(pk=int(folio))
            qs = qs.filter(filtro)
    return form, qs


@operador_requerido
def lista(request):
    form, qs = _filtrar(request)
    pagina = Paginator(qs, 25).get_page(request.GET.get('pagina'))
    return render(request, 'operacion/despachos/lista.html', {
        'form': form, 'pagina': pagina, 'total': pagina.paginator.count,
        'hay_filtros': any(request.GET.get(k) for k in ('fecha', 'ruta', 'estado', 'q')),
    })


@operador_requerido
def exportar(request):
    _, qs = _filtrar(request)
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    nombre = f'despachos-{timezone.localdate():%Y%m%d}.csv'
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
    respuesta.write('﻿')  # BOM para que Excel respete las tildes
    w = csv.writer(respuesta, delimiter=';')
    w.writerow(['Folio', 'Ruta', 'Bus', 'Placa', 'Conductor', 'Estado', 'Programado',
                'Salida', 'Llegada', 'Demora salida (min)', 'Duración (min)', 'Despachador'])

    def hora(valor):
        return timezone.localtime(valor).strftime('%Y-%m-%d %H:%M') if valor else ''

    for d in qs[:5000]:
        w.writerow([d.folio, d.ruta.codigo, d.bus.numero, d.bus.placa, d.conductor.nombre,
                    d.get_estado_display(), hora(d.hora_programada), hora(d.hora_salida),
                    hora(d.hora_llegada), d.demora_salida_min if d.demora_salida_min is not None else '',
                    d.duracion_real_min or '', d.despachador.get_username() if d.despachador else 'Automático'])
    return respuesta


@operador_requerido
def nuevo(request):
    inicial = {}
    if request.GET.get('ruta'):
        inicial['ruta'] = Ruta.objects.filter(pk=request.GET['ruta']).first()
    form = NuevoDespachoForm(request.POST or None, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        salir_ahora = datos['cuando'] == NuevoDespachoForm.AHORA
        try:
            despacho = servicios.crear_despacho(
                ruta=datos['ruta'], bus=datos['bus'], conductor=datos['conductor'],
                usuario=request.user, salir_ahora=salir_ahora,
                hora_programada=None if salir_ahora else datos['hora_programada'],
                observaciones=datos['observaciones'])
        except servicios.ErrorDespacho as error:
            form.add_error(None, str(error))
        else:
            verbo = 'salió a ruta' if salir_ahora else 'quedó programado'
            messages.success(request, f'{despacho.folio}: el bus {despacho.bus} {verbo} en la {despacho.ruta.codigo}.')
            return redirect('operacion:despacho', pk=despacho.pk)
    return render(request, 'operacion/despachos/nuevo.html', {
        'form': form,
        'sin_buses': not form.fields['bus'].queryset.exists(),
        'sin_conductores': not form.fields['conductor'].queryset.exists(),
    })


@operador_requerido
def detalle(request, pk):
    despacho = get_object_or_404(Despacho.objects.select_related('ruta', 'bus', 'conductor', 'despachador'), pk=pk)
    trazado, estado, itinerario = seguimiento.itinerario(despacho)
    return render(request, 'operacion/despachos/detalle.html', {
        'd': despacho,
        'estado': estado,
        'itinerario': itinerario,
        'rutas_mapa': Ruta.objects.filter(pk=despacho.ruta_id).prefetch_related('paradas__estacion'),
        'eventos': despacho.eventos.select_related('usuario'),
        'cancelar_form': CancelarForm(),
        'novedad_form': NovedadForm(),
    })


def _accion(request, pk, funcion, mensaje, *args):
    despacho = get_object_or_404(Despacho, pk=pk)
    try:
        funcion(despacho, request.user, *args)
    except servicios.ErrorDespacho as error:
        messages.error(request, str(error))
    else:
        messages.success(request, mensaje.format(folio=despacho.folio, bus=despacho.bus))
    destino = request.POST.get('siguiente')
    if destino and destino.startswith('/') and not destino.startswith('//'):
        return redirect(destino)
    return redirect('operacion:despacho', pk=pk)


@operador_requerido
@require_POST
def iniciar(request, pk):
    return _accion(request, pk, servicios.iniciar_despacho, '{folio}: el bus {bus} salió a ruta.')


@operador_requerido
@require_POST
def finalizar(request, pk):
    return _accion(request, pk, servicios.finalizar_despacho, '{folio}: recorrido cerrado.',
                   request.POST.get('observacion', '').strip())


@operador_requerido
@require_POST
def cancelar(request, pk):
    form = CancelarForm(request.POST)
    motivo = form.cleaned_data['motivo'] if form.is_valid() else ''
    return _accion(request, pk, servicios.cancelar_despacho, '{folio}: despacho cancelado.', motivo)


@operador_requerido
@require_POST
def novedad(request, pk):
    form = NovedadForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Escribe la novedad antes de guardarla.')
        return redirect('operacion:despacho', pk=pk)
    return _accion(request, pk, servicios.registrar_novedad, '{folio}: novedad registrada.',
                   form.cleaned_data['descripcion'], form.cleaned_data['incidente'])


@operador_requerido
def mapa(request):
    demo.mantener_operacion()
    return render(request, 'operacion/mapa.html', {
        'rutas': Ruta.objects.filter(activa=True).prefetch_related('paradas__estacion'),
    })
