from django.contrib.auth import views as auth
from django.urls import path

from .views import IngresarView

app_name = 'cuentas'

urlpatterns = [
    path('ingresar/', IngresarView.as_view(), name='ingresar'),
    path('salir/', auth.LogoutView.as_view(), name='salir'),
]
