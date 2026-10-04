"""Panel interno de operacion (requiere rol de despachador o supervisor)."""

from django.urls import path

from apps.despacho import views as despacho
from apps.flota import views as flota
from apps.red import views as red

app_name = 'operacion'

urlpatterns = [
    path('', despacho.tablero, name='tablero'),
    path('mapa/', despacho.mapa, name='mapa'),
    path('despachos/', despacho.lista, name='despachos'),
    path('despachos/exportar.csv', despacho.exportar, name='exportar'),
    path('despachos/nuevo/', despacho.nuevo, name='nuevo'),
    path('despachos/<int:pk>/', despacho.detalle, name='despacho'),
    path('despachos/<int:pk>/iniciar/', despacho.iniciar, name='iniciar'),
    path('despachos/<int:pk>/finalizar/', despacho.finalizar, name='finalizar'),
    path('despachos/<int:pk>/cancelar/', despacho.cancelar, name='cancelar'),
    path('despachos/<int:pk>/novedad/', despacho.novedad, name='novedad'),
    path('flota/', flota.buses, name='buses'),
    path('flota/nuevo/', flota.bus_form, name='bus_nuevo'),
    path('flota/<int:pk>/', flota.bus_form, name='bus_editar'),
    path('conductores/', flota.conductores, name='conductores'),
    path('conductores/nuevo/', flota.conductor_form, name='conductor_nuevo'),
    path('conductores/<int:pk>/', flota.conductor_form, name='conductor_editar'),
    path('rutas/', red.rutas, name='rutas'),
    path('rutas/<int:pk>/', red.ruta, name='ruta'),
    path('rutas/<int:pk>/guardar/', red.ruta_guardar, name='ruta_guardar'),
]
