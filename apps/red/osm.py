"""Construye la red de rutas a partir de OpenStreetMap.

OpenStreetMap modela cada ruta de bus como una relacion (esquema PTv2) cuyos
miembros son, en orden, las vias que recorre y las plataformas donde para.
Aqui se encadenan esas vias en una sola polilinea, se ubican las paradas y se
devuelve una estructura lista para guardar como datos del proyecto.

Datos (c) colaboradores de OpenStreetMap, licencia ODbL.
"""

import json
import re
import unicodedata
import urllib.parse
import urllib.request

from apps.core.geo import acumulado_km, distancia_km, simplificar, ubicar_en_linea

OVERPASS = 'https://overpass-api.de/api/interpreter'
CAJA = '10.30,-75.60,10.50,-75.38'  # Cartagena y alrededores
# Solo rutas del sistema: troncales (T), pretroncales (X), alimentadoras (A) y complementarias (C).
CODIGO_VALIDO = re.compile(r'^[TXAC]\d{3}E?$')
TIPOS = {'T': 'troncal', 'X': 'pretroncal', 'A': 'alimentadora', 'C': 'complementaria'}
# Nombres que OpenStreetMap escribe distinto de como se ven en las estaciones.
NOMBRES = {
    'Patio Portal': 'Portal',
    'Rep. del Líbano': 'República del Líbano',
    'Delicias': 'Las Delicias',
    'Bodeguita': 'La Bodeguita',
}
# El sistema no se nombra en la interfaz: se limpia de cualquier texto importado.
MARCA = re.compile(r'\s*\b(transcaribe|transcribe)\b\s*', re.IGNORECASE)
TOLERANCIA_SIMPLIFICACION_KM = 0.008


def slug(texto):
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', texto.lower()).strip('-')[:20]


def limpiar_nombre(nombre):
    nombre = MARCA.sub(' ', (nombre or '')).strip(' -')
    nombre = re.sub(r'\s+', ' ', nombre)
    return NOMBRES.get(nombre, nombre)


def nombre_ruta(nombre_osm, codigo):
    """'Troncal 101 - Portal - Centro - Portal' -> 'Portal → Centro → Portal'."""
    texto = limpiar_nombre(nombre_osm)
    texto = re.sub(r'^(Ruta|Troncal Expresa|Troncal|Pretroncal)\s*(\d{3}|' + codigo + r')?\s*-\s*', '', texto)
    partes = [limpiar_nombre(p) for p in texto.split(' - ') if p.strip()]
    return ' → '.join(partes) or codigo


def descargar(consulta, timeout=180):
    datos = urllib.parse.urlencode({'data': consulta}).encode()
    peticion = urllib.request.Request(OVERPASS, data=datos,
                                      headers={'User-Agent': 'sitm-cartagena/1.0 (importador de red)'})
    with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
        return json.loads(respuesta.read().decode('utf-8'))


def descargar_todo():
    rutas = descargar(f'[out:json][timeout:180];rel["route"="bus"]({CAJA});out geom;')
    paradas = descargar(
        f'[out:json][timeout:180];rel["route"="bus"]({CAJA})->.r;'
        '(way(r.r:"platform");way(r.r:"platform_entry_only");way(r.r:"platform_exit_only");'
        'rel(r.r:"platform");node(r.r:"platform");node(r.r:"platform_entry_only");'
        'node(r.r:"platform_exit_only");node(r.r:"stop"););out center tags;')
    return rutas, paradas


def _clave(p):
    return round(p[0], 6), round(p[1], 6)


def encadenar(vias):
    """Une las vias de una relacion en una polilinea, orientando cada una."""
    linea = []
    for i, via in enumerate(vias):
        g = [(n['lat'], n['lon']) for n in via.get('geometry') or [] if n]
        if len(g) < 2:
            continue
        if not linea:
            siguiente = next((v for v in vias[i + 1:] if v.get('geometry')), None)
            if siguiente:
                extremos = {_clave((n['lat'], n['lon'])) for n in (siguiente['geometry'][0], siguiente['geometry'][-1])}
                if _clave(g[0]) in extremos and _clave(g[-1]) not in extremos:
                    g.reverse()
            linea = g
            continue
        ultimo = linea[-1]
        if _clave(g[0]) == _clave(ultimo):
            linea.extend(g[1:])
        elif _clave(g[-1]) == _clave(ultimo):
            linea.extend(reversed(g[:-1]))
        else:
            # Hueco en los datos: se pega por el extremo mas cercano.
            if distancia_km(g[-1], ultimo) < distancia_km(g[0], ultimo):
                g.reverse()
            linea.extend(g)
    return linea


def _centro(elemento):
    c = elemento.get('center') or elemento
    return (c['lat'], c['lon']) if 'lat' in c else None


ORDEN_TIPO = {'T': 0, 'X': 1, 'A': 2, 'C': 3}
CIRCULAR_KM = 0.3     # inicio y fin del trazado a menos de esto = recorrido circular
MISMO_PUNTO_KM = 0.3  # una parada a menos de esto del trazado (o de otra) es "la misma"


def _rotar(linea, indice):
    """Hace que un recorrido circular empiece en ``indice`` y vuelva a cerrar ahi."""
    abierta = linea[:-1] if _clave(linea[0]) == _clave(linea[-1]) else list(linea)
    rotada = abierta[indice:] + abierta[:indice]
    return rotada + [rotada[0]]


def _mas_cercano(linea, punto):
    return min(range(len(linea)), key=lambda i: distancia_km(linea[i], punto))


def _mas_lejano(linea, punto):
    return max(range(len(linea)), key=lambda i: distancia_km(linea[i], punto))


def construir_red(datos_rutas, datos_paradas, horarios=None):
    """Devuelve ``(red, avisos)``.

    Para cada ruta se arma el trazado y la secuencia de paradas ordenada segun
    su posicion sobre el trazado. Varios recorridos estan mapeados como
    circuitos que empiezan en un punto arbitrario: se rotan para empezar en el
    origen declarado (``from``) y se agregan origen y destino como paradas
    aunque OpenStreetMap no los marque.
    """
    horarios = horarios or {}
    indice = {(e['type'], e['id']): e for e in datos_paradas.get('elements', [])}
    rutas, avisos = [], []
    estaciones = {}  # slug -> {codigo, nombre, lat, lng}
    troncales, usadas = set(), set()

    # Posiciones reales de las plataformas con nombre: mandan sobre cualquier
    # punto deducido de etiquetas "from"/"to".
    for e in datos_paradas.get('elements', []):
        nombre, punto = limpiar_nombre(e.get('tags', {}).get('name')), _centro(e)
        if nombre and punto and slug(nombre) not in estaciones:
            estaciones[slug(nombre)] = {'codigo': slug(nombre), 'nombre': nombre,
                                        'lat': round(punto[0], 6), 'lng': round(punto[1], 6)}

    def coords(clave):
        return estaciones[clave]['lat'], estaciones[clave]['lng']

    def registrar(nombre, punto):
        """Slug de la parada ``nombre`` en ``punto``, creandola si no existe."""
        clave = slug(nombre)
        if clave in estaciones and distancia_km(coords(clave), punto) > 1.0:
            # Un barrio que se llama igual que una estacion lejana.
            nombre, clave = f'{nombre} (terminal)', slug(f'{nombre} terminal')
        if clave not in estaciones:
            estaciones[clave] = {'codigo': clave, 'nombre': nombre,
                                 'lat': round(punto[0], 6), 'lng': round(punto[1], 6)}
        return clave

    def cercana(punto):
        opciones = [(distancia_km(punto, coords(c)), c) for c in estaciones]
        opciones = [o for o in opciones if o[0] <= MISMO_PUNTO_KM]
        return min(opciones)[1] if opciones else None

    relaciones = [r for r in datos_rutas.get('elements', [])
                  if CODIGO_VALIDO.match((r.get('tags', {}).get('ref') or '').strip())]
    # Troncales primero: definen el Portal y las estaciones que reutilizan las demas.
    relaciones.sort(key=lambda r: (ORDEN_TIPO[r['tags']['ref'].strip()[0]], r['tags']['ref']))

    for rel in relaciones:
        etiquetas = rel['tags']
        codigo = etiquetas['ref'].strip()
        linea = encadenar([m for m in rel['members'] if m['type'] == 'way' and m['role'] == ''])
        if len(linea) < 2:
            avisos.append(f'{codigo}: sin geometría, se omite.')
            continue
        origen = limpiar_nombre(etiquetas.get('from')) or 'Origen'
        destino = limpiar_nombre(etiquetas.get('to')) or 'Destino'

        # 1. Plataformas en el orden de la relacion.
        plataformas = []
        for m in rel['members']:
            if not (m['role'].startswith('platform') or (m['role'] == 'stop' and m['type'] == 'node')):
                continue
            elemento = indice.get((m['type'], m['ref']), {})
            punto = _centro(elemento) or ((m['lat'], m['lon']) if 'lat' in m else None)
            if punto is None:
                continue
            nombre = limpiar_nombre(elemento.get('tags', {}).get('name'))
            # Entrada/salida sin nombre: solo vale si coincide con una parada conocida.
            clave = registrar(nombre, punto) if nombre else cercana(punto)
            if clave:
                plataformas.append(clave)

        # 2. Ubicacion de cada plataforma sobre el trazado (avanzando: ida y vuelta).
        acumulado = acumulado_km(linea)
        ubicadas, desde = [], 0
        for clave in plataformas:
            km, desde, dist = ubicar_en_linea(linea, acumulado, coords(clave), desde)
            if dist > MISMO_PUNTO_KM:
                avisos.append(f'{codigo}: {estaciones[clave]["nombre"]} queda a {dist * 1000:.0f} m del trazado.')
                continue
            ubicadas.append((km, clave))

        circular = distancia_km(linea[0], linea[-1]) <= CIRCULAR_KM
        if circular and codigo[0] in 'AC':
            # Alimentadoras y complementarias: el circuito empieza en el punto de
            # transbordo (donde OSM lo inicia) y el barrio queda en el extremo lejano.
            total = acumulado[-1]

            def en_trazado(nombre):
                c = slug(nombre)
                if c in estaciones:
                    km, _, dist = ubicar_en_linea(linea, acumulado, coords(c), 0, cerca_km=99)
                    if dist <= MISMO_PUNTO_KM:
                        return km, c
                return None

            desconocidos = [n for n in (origen, destino) if en_trazado(n) is None]
            c_inicio = cercana(linea[0])
            if c_inicio is None:
                # El destino declarado ("→ Santa Lucía", "→ Portal") es el transbordo.
                c_inicio = registrar(desconocidos.pop() if desconocidos else destino, linea[0])
            ubicadas += [t for t in (en_trazado(origen), en_trazado(destino)) if t and t[1] != c_inicio]
            if desconocidos:
                lejano = _mas_lejano(linea, linea[0])
                ubicadas.append((acumulado[lejano], registrar(desconocidos[0], linea[lejano])))
            ubicadas = [(km, c) for km, c in ubicadas
                        if not (c == c_inicio and (km < MISMO_PUNTO_KM or km > total - MISMO_PUNTO_KM))]
            ubicadas = [(0.0, c_inicio)] + sorted(set(ubicadas)) + [(total, c_inicio)]
        elif circular:
            # 3. Rotar el circuito para que empiece en el origen.
            c_org, c_dst = slug(origen), slug(destino)
            if c_org in estaciones and distancia_km(coords(c_org), linea[_mas_cercano(linea, coords(c_org))]) <= MISMO_PUNTO_KM:
                pivote = _mas_cercano(linea, coords(c_org))
            elif c_dst in estaciones:
                pivote = _mas_lejano(linea, coords(c_dst))  # el barrio de origen es el extremo opuesto
            else:
                pivote = 0
            desfase, total = acumulado[pivote], acumulado[-1]
            linea = _rotar(linea, pivote)
            ubicadas = sorted(((km - desfase) % total, c) for km, c in ubicadas)
            acumulado = acumulado_km(linea)
            total = acumulado[-1]

            # 4. Origen al principio y al final del circuito.
            if c_org in estaciones and distancia_km(coords(c_org), linea[0]) <= MISMO_PUNTO_KM:
                c_origen = c_org
            else:
                c_origen = registrar(origen, linea[0])
            ubicadas = [(km, c) for km, c in ubicadas
                        if not (c == c_origen and (km < MISMO_PUNTO_KM or km > total - MISMO_PUNTO_KM))]
            # 5. Destino, si no esta ya entre las paradas.
            if c_dst not in {c for _, c in ubicadas} and c_dst != c_origen:
                lejano = _mas_lejano(linea, linea[0])
                if c_dst in estaciones:
                    km, _, dist = ubicar_en_linea(linea, acumulado, coords(c_dst), 0, cerca_km=99)
                    if dist > MISMO_PUNTO_KM:
                        km, c_dst = acumulado[lejano], registrar(destino, linea[lejano])
                else:
                    km, c_dst = acumulado[lejano], registrar(destino, linea[lejano])
                ubicadas.append((km, c_dst))
            ubicadas = [(0.0, c_origen)] + sorted(ubicadas) + [(total, c_origen)]
        else:
            total = acumulado[-1]
            if not ubicadas or ubicadas[0][0] > MISMO_PUNTO_KM:
                ubicadas.insert(0, (0.0, cercana(linea[0]) or registrar(origen, linea[0])))
            if ubicadas[-1][0] < total - MISMO_PUNTO_KM:
                ubicadas.append((total, cercana(linea[-1]) or registrar(destino, linea[-1])))

        secuencia = []
        for _, clave in ubicadas:
            if not secuencia or secuencia[-1] != clave:
                secuencia.append(clave)
        usadas.update(secuencia)
        if codigo[0] == 'T':
            troncales.update(secuencia)
        elif codigo[0] == 'X':
            troncales.update(c for c in plataformas if c in secuencia)

        simple = simplificar(linea, TOLERANCIA_SIMPLIFICACION_KM)
        rutas.append({
            'codigo': codigo,
            'nombre': nombre_ruta(etiquetas.get('name', codigo), codigo),
            'tipo': 'expresa' if codigo.endswith('E') else TIPOS[codigo[0]],
            'horario': horarios.get(codigo, ''),
            'circular': circular,
            'longitud_km': round(acumulado_km(simple)[-1], 2),
            'paradas': secuencia,
            'trazado': [[round(lat, 6), round(lng, 6)] for lat, lng in simple],
        })

    resultado = []
    for clave in sorted(usadas, key=lambda c: estaciones[c]['nombre']):
        e = dict(estaciones[clave])
        e['tipo'] = 'portal' if clave == 'portal' else ('estacion' if clave in troncales else 'parada')
        resultado.append(e)
    return {
        'fuente': 'Datos © colaboradores de OpenStreetMap (ODbL).',
        'estaciones': resultado,
        'rutas': sorted(rutas, key=lambda r: (ORDEN_TIPO[r['codigo'][0]], r['codigo'])),
    }, avisos
