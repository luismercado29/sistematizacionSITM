from django.contrib import admin

from .models import Book, Bus, Drivers, User


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ('id', 'bus_name', 'source', 'dest', 'nos', 'price', 'date', 'time')
    list_filter = ('source', 'dest', 'date')
    search_fields = ('bus_name', 'source', 'dest')


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('id', 'bus_name', 'name', 'source', 'dest', 'date', 'time', 'status')
    list_filter = ('status', 'date')
    search_fields = ('bus_name', 'name', 'email')


@admin.register(Drivers)
class DriversAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'licencia')
    search_fields = ('nombre', 'licencia')


# Modelo heredado, sin relacion con el login: la autenticacion usa el User de
# django.contrib.auth. Se deja registrado para poder consultar sus datos.
admin.site.register(User)


