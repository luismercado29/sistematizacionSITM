from django import forms

from apps.core.formularios import ModeloSITM

from .models import Ruta


class RutaForm(ModeloSITM):
    """Parametros operativos de una ruta. Las paradas se editan en /admin/."""

    class Meta:
        model = Ruta
        fields = ['nombre', 'tipo', 'color', 'frecuencia_min', 'velocidad_kmh', 'activa']
        widgets = {'color': forms.TextInput(attrs={'type': 'color'})}
