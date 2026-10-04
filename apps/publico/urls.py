from django.urls import path

from . import views

app_name = 'publico'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('mapa/', views.mapa, name='mapa'),
    path('estaciones/<slug:codigo>/', views.estacion, name='estacion'),
    path('rutas/<str:codigo>/', views.ruta, name='ruta'),
]
