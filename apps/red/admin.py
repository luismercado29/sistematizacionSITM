from django.contrib import admin

from .models import Estacion, ParadaRuta, Ruta


@admin.register(Estacion)
class EstacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'tipo', 'latitud', 'longitud', 'activa')
    list_filter = ('tipo', 'activa')
    search_fields = ('nombre', 'codigo')
    prepopulated_fields = {'codigo': ('nombre',)}


class ParadaInline(admin.TabularInline):
    model = ParadaRuta
    extra = 1
    autocomplete_fields = ('estacion',)
    readonly_fields = ('distancia_km', 'minutos_desde_inicio')


@admin.register(Ruta)
class RutaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'tipo', 'frecuencia_min', 'velocidad_kmh', 'activa')
    list_filter = ('tipo', 'activa')
    search_fields = ('codigo', 'nombre')
    inlines = [ParadaInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Distancias y tiempos se derivan de las paradas: siempre al dia.
        form.instance.recalcular_tiempos()
