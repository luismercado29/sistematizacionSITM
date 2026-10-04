from django.contrib import admin

from .models import Despacho, EventoDespacho, PosicionGPS


class EventoInline(admin.TabularInline):
    model = EventoDespacho
    extra = 0
    can_delete = False
    readonly_fields = ('tipo', 'descripcion', 'usuario', 'creado')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Despacho)
class DespachoAdmin(admin.ModelAdmin):
    """Solo lectura: los cambios de estado se hacen desde el panel de operacion
    para que pasen por las validaciones y queden en la bitacora."""

    list_display = ('folio', 'ruta', 'bus', 'conductor', 'estado', 'hora_programada', 'hora_salida')
    list_filter = ('estado', 'ruta')
    search_fields = ('bus__numero', 'conductor__nombre')
    date_hierarchy = 'hora_programada'
    inlines = [EventoInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PosicionGPS)
class PosicionGPSAdmin(admin.ModelAdmin):
    list_display = ('bus', 'despacho', 'latitud', 'longitud', 'velocidad_kmh', 'registrado')
    list_filter = ('bus',)
    date_hierarchy = 'registrado'
