from django.conf import settings
from django.contrib import admin
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from apps.core import views as core

admin.site.site_header = 'SITM Cartagena · Administración'
admin.site.site_title = 'SITM Cartagena'
admin.site.index_title = 'Datos maestros'

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url=static('sitm/img/favicon.svg'), permanent=True)),
    path('cuentas/', include('apps.core.urls')),
    path('operacion/', include('config.urls_operacion')),
    path('api/v1/', include('apps.publico.urls_api')),
    path('', include('apps.publico.urls')),
]

handler403 = core.error_403
handler404 = core.error_404
handler500 = core.error_500
