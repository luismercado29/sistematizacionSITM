from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Trazos de Lucide (https://lucide.dev, licencia ISC). Se incrustan en linea
# para no depender de un CDN ni de una fuente de iconos.
ICONOS = {
    'bus': '<path d="M8 6v6"/><path d="M15 6v6"/><path d="M2 12h19.6"/><path d="M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3"/><circle cx="7" cy="18" r="2"/><path d="M9 18h5"/><circle cx="16" cy="18" r="2"/>',
    'tablero': '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
    'mapa': '<path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/>',
    'usuarios': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    'usuario': '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    'ruta': '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
    'despachar': '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>',
    'reloj': '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    'pin': '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
    'buscar': '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    'mas': '<path d="M5 12h14"/><path d="M12 5v14"/>',
    'iniciar': '<polygon points="6 3 20 12 6 21 6 3"/>',
    'bandera': '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/>',
    'cerrar': '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    'cancelar': '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    'ok': '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
    'alerta': '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    'taller': '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    'salir': '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/>',
    'menu': '<line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/>',
    'sol': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    'luna': '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    'derecha': '<path d="m9 18 6-6-6-6"/>',
    'atras': '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    'flecha': '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    'editar': '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
    'licencia': '<path d="M16 10h2"/><path d="M16 14h2"/><path d="M6.17 15a3 3 0 0 1 5.66 0"/><circle cx="9" cy="11" r="2"/><rect x="2" y="5" width="20" height="14" rx="2"/>',
    'actividad': '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
    'en-vivo': '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
    'calendario': '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    'info': '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    'candado': '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    'ojo': '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
    'ajustes': '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    'descargar': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
    'nota': '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    'estacion': '<path d="M4 21V9l8-6 8 6v12"/><path d="M9 21v-6h6v6"/>',
}


@register.simple_tag
def icono(nombre, clase='', etiqueta=''):
    """SVG en linea. Sin ``etiqueta`` es decorativo (aria-hidden)."""
    trazo = ICONOS.get(nombre)
    if trazo is None:
        raise template.TemplateSyntaxError(f'Icono desconocido: {nombre}')
    accesible = (format_html('role="img" aria-label="{}"', etiqueta) if etiqueta
                 else mark_safe('aria-hidden="true" focusable="false"'))
    return format_html(
        '<svg class="icono {}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" {}>{}</svg>',
        clase, accesible, mark_safe(trazo))


@register.filter
def minutos(valor):
    """12 -> '12 min', 75 -> '1 h 15 min', 0 -> 'Llegando'."""
    if valor is None:
        return '—'
    valor = int(valor)
    if valor <= 0:
        return 'Llegando'
    if valor < 60:
        return f'{valor} min'
    h, m = divmod(valor, 60)
    return f'{h} h {m} min' if m else f'{h} h'


@register.filter
def porcentaje(valor):
    return '—' if valor is None else f'{valor}%'


@register.simple_tag(takes_context=True)
def activo(context, *prefijos):
    """'is-active' si la URL actual empieza por alguno de los prefijos."""
    ruta = context['request'].path
    return 'is-active' if any(ruta.startswith(p) for p in prefijos) else ''


@register.simple_tag(takes_context=True)
def consulta(context, **cambios):
    """Querystring actual con algunos parametros cambiados (para paginar con filtros)."""
    params = context['request'].GET.copy()
    for clave, valor in cambios.items():
        if valor in (None, ''):
            params.pop(clave, None)
        else:
            params[clave] = valor
    texto = params.urlencode()
    return f'?{texto}' if texto else '?'


@register.simple_tag
def red_mapa(rutas):
    """Rutas con sus paradas listas para ``json_script`` y el mapa en vivo."""
    from django.urls import reverse

    return [{
        'codigo': r.codigo, 'nombre': r.nombre, 'color': r.color,
        # Recorrido por la via; el mapa lo dibuja y mueve los buses sobre el.
        'trazado': r.trazado or [[float(p.estacion.latitud), float(p.estacion.longitud)] for p in r.paradas.all()],
        'paradas': [{
            'nombre': p.estacion.nombre,
            'lat': float(p.estacion.latitud), 'lng': float(p.estacion.longitud),
            'url': reverse('publico:estacion', args=[p.estacion.codigo]),
        } for p in r.paradas.all()],
    } for r in rutas]


@register.filter
def nombre_usuario(user, si_no_hay='Sistema'):
    """Nombre visible de un usuario; ``si_no_hay`` cuando la accion fue automatica."""
    if user is None:
        return si_no_hay
    return user.get_full_name() or user.get_username()
