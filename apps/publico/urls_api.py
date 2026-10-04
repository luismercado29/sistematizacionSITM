from django.urls import path

from . import api

app_name = 'api'

urlpatterns = [
    path('red/', api.red, name='red'),
    path('flota/', api.flota, name='flota'),
    path('estaciones/<slug:codigo>/llegadas/', api.llegadas, name='llegadas'),
    path('rutas/<str:codigo>/en-vivo/', api.ruta_en_vivo, name='ruta_en_vivo'),
    path('gps/', api.reportar_gps, name='gps'),
]
