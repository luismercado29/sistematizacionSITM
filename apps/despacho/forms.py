from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.core.formularios import FormularioSITM
from apps.red.models import Ruta

from . import servicios


class EtiquetaBus(forms.ModelChoiceField):
    def label_from_instance(self, bus):
        return f'{bus.numero} · {bus.get_tipologia_display()} · {bus.capacidad} pas.'


class EtiquetaConductor(forms.ModelChoiceField):
    def label_from_instance(self, c):
        return f'{c.nombre} · Lic. {c.categoria}'


class NuevoDespachoForm(FormularioSITM):
    AHORA, PROGRAMAR = 'ahora', 'programar'

    ruta = forms.ModelChoiceField(queryset=Ruta.objects.none(), empty_label='Selecciona la ruta')
    bus = EtiquetaBus(queryset=None, empty_label='Selecciona un bus disponible')
    conductor = EtiquetaConductor(queryset=None, empty_label='Selecciona un conductor',
                                  help_text='Solo aparecen conductores activos, con licencia vigente y sin otro despacho.')
    cuando = forms.ChoiceField(choices=[(AHORA, 'Sale ahora'), (PROGRAMAR, 'Programar salida')],
                               initial=AHORA, widget=forms.RadioSelect, label='Salida')
    hora_programada = forms.DateTimeField(
        required=False, label='Hora de salida programada',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        input_formats=['%Y-%m-%dT%H:%M'])
    observaciones = forms.CharField(required=False, max_length=500,
                                    widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ruta'].queryset = Ruta.objects.filter(activa=True, paradas__isnull=False).distinct()
        self.fields['bus'].queryset = servicios.buses_disponibles().order_by('numero')
        self.fields['conductor'].queryset = servicios.conductores_disponibles().order_by('nombre')

    def clean(self):
        datos = super().clean()
        if datos.get('cuando') == self.PROGRAMAR:
            hora = datos.get('hora_programada')
            if not hora:
                self.add_error('hora_programada', 'Indica a qué hora sale.')
            elif hora < timezone.now() - timedelta(minutes=5):
                self.add_error('hora_programada', 'La hora programada ya pasó. Usa "Sale ahora".')
        bus, conductor = datos.get('bus'), datos.get('conductor')
        if bus and conductor and not conductor.puede_conducir(bus):
            self.add_error('conductor', f'{conductor} tiene licencia {conductor.categoria}; '
                                        'un bus articulado exige C3.')
        return datos


class CancelarForm(FormularioSITM):
    motivo = forms.CharField(max_length=280, widget=forms.Textarea(attrs={'rows': 2}),
                             help_text='Queda registrado en la bitácora del despacho.')


class NovedadForm(FormularioSITM):
    descripcion = forms.CharField(label='Novedad', max_length=280,
                                  widget=forms.Textarea(attrs={'rows': 2}))
    incidente = forms.BooleanField(required=False, label='Marcar como incidente')


class FiltroDespachosForm(FormularioSITM):
    fecha = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    ruta = forms.ModelChoiceField(queryset=Ruta.objects.all(), required=False, empty_label='Todas las rutas')
    estado = forms.ChoiceField(required=False)
    q = forms.CharField(required=False, label='Buscar', max_length=40,
                        widget=forms.TextInput(attrs={'placeholder': 'Bus, conductor o folio'}))

    def __init__(self, *args, **kwargs):
        from .models import Despacho
        super().__init__(*args, **kwargs)
        self.fields['estado'].choices = [('', 'Todos los estados'), *Despacho.Estado.choices]
