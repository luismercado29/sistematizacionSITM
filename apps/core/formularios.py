from django import forms


class EstiloSITM:
    """Agrega las clases del sistema de diseno y los atributos ARIA a los widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            widget = campo.widget
            if isinstance(widget, forms.RadioSelect):
                clase = 'radio'
            elif isinstance(widget, forms.CheckboxInput):
                clase = 'check'
            elif isinstance(widget, forms.Select):
                clase = 'campo select'
            else:
                clase = 'campo'
            widget.attrs['class'] = f"{widget.attrs.get('class', '')} {clase}".strip()
            if campo.help_text:
                widget.attrs['aria-describedby'] = f'{self.auto_id % nombre}-ayuda'

    def full_clean(self):
        super().full_clean()
        # Despues de validar, los campos con error se marcan para lectores de pantalla.
        for nombre in self.errors:
            if nombre in self.fields:
                attrs = self.fields[nombre].widget.attrs
                attrs['aria-invalid'] = 'true'
                attrs['aria-describedby'] = f'{self.auto_id % nombre}-error'


class FormularioSITM(EstiloSITM, forms.Form):
    pass


class ModeloSITM(EstiloSITM, forms.ModelForm):
    pass
