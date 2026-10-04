from django import forms

from apps.core.formularios import ModeloSITM
from apps.despacho.models import Despacho

from .models import Bus, Conductor


class BusForm(ModeloSITM):
    class Meta:
        model = Bus
        fields = ['numero', 'placa', 'tipologia', 'capacidad', 'operador', 'modelo', 'estado']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['placa'].widget.attrs.update({'autocapitalize': 'characters', 'placeholder': 'ABC123'})
        # "En servicio" lo asigna el despacho; no se elige a mano.
        if self.instance.estado != Bus.Estado.EN_SERVICIO:
            self.fields['estado'].choices = [c for c in Bus.Estado.choices if c[0] != Bus.Estado.EN_SERVICIO]

    def clean_placa(self):
        return self.cleaned_data['placa'].upper().replace(' ', '').replace('-', '')

    def clean_estado(self):
        estado = self.cleaned_data['estado']
        if (self.instance.pk and estado != self.instance.estado
                and Despacho.objects.filter(bus=self.instance, estado__in=Despacho.ACTIVOS).exists()):
            raise forms.ValidationError('El bus tiene un despacho activo. Ciérralo o cancélalo antes de cambiar su estado.')
        return estado


class ConductorForm(ModeloSITM):
    class Meta:
        model = Conductor
        fields = ['nombre', 'documento', 'telefono', 'licencia', 'categoria',
                  'vencimiento_licencia', 'estado']
        widgets = {
            'vencimiento_licencia': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'telefono': forms.TextInput(attrs={'type': 'tel', 'autocomplete': 'tel', 'inputmode': 'tel'}),
            'documento': forms.TextInput(attrs={'inputmode': 'numeric'}),
        }

    def clean_estado(self):
        estado = self.cleaned_data['estado']
        if (self.instance.pk and estado != Conductor.Estado.ACTIVO
                and Despacho.objects.filter(conductor=self.instance, estado__in=Despacho.ACTIVOS).exists()):
            raise forms.ValidationError('El conductor tiene un despacho activo. Ciérralo antes de cambiar su estado.')
        return estado
