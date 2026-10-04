from django.contrib import admin

from .models import Bus, Conductor


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ('numero', 'placa', 'tipologia', 'capacidad', 'operador', 'estado')
    list_filter = ('estado', 'tipologia', 'operador')
    search_fields = ('numero', 'placa')
    readonly_fields = ('token_gps',)


@admin.register(Conductor)
class ConductorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'documento', 'categoria', 'vencimiento_licencia', 'estado')
    list_filter = ('estado', 'categoria')
    search_fields = ('nombre', 'documento', 'licencia')
