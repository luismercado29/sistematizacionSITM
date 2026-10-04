"""Utilidades geograficas sin dependencias externas."""

from math import asin, cos, radians, sin, sqrt

RADIO_TIERRA_KM = 6371.0


def distancia_km(a, b):
    """Distancia haversine entre dos puntos (lat, lng) en kilometros."""
    lat1, lng1 = map(radians, a)
    lat2, lng2 = map(radians, b)
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * RADIO_TIERRA_KM * asin(sqrt(h))


def interpolar(a, b, fraccion):
    """Punto intermedio entre a y b. Para tramos urbanos cortos basta lineal."""
    fraccion = max(0.0, min(1.0, fraccion))
    return a[0] + (b[0] - a[0]) * fraccion, a[1] + (b[1] - a[1]) * fraccion


def proyectar_en_tramo(p, a, b):
    """Fraccion (0..1) del tramo a-b mas cercana al punto p.

    Usa una proyeccion equirectangular local, suficiente a escala de ciudad.
    """
    escala = cos(radians((a[0] + b[0]) / 2))
    ax, ay = a[1] * escala, a[0]
    bx, by = b[1] * escala, b[0]
    px, py = p[1] * escala, p[0]
    dx, dy = bx - ax, by - ay
    largo2 = dx * dx + dy * dy
    if largo2 == 0:
        return 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / largo2
    return max(0.0, min(1.0, t))


def acumulado_km(puntos):
    """Distancia acumulada (km) en cada vertice de una polilinea."""
    total, resultado = 0.0, []
    for i, p in enumerate(puntos):
        if i:
            total += distancia_km(puntos[i - 1], p)
        resultado.append(total)
    return resultado


def punto_en_linea(puntos, acumulado, km):
    """Punto de la polilinea a ``km`` del inicio."""
    if not puntos:
        return None
    if km <= 0 or len(puntos) == 1:
        return tuple(puntos[0])
    if km >= acumulado[-1]:
        return tuple(puntos[-1])
    from bisect import bisect_right
    i = min(bisect_right(acumulado, km) - 1, len(puntos) - 2)
    tramo = acumulado[i + 1] - acumulado[i]
    return interpolar(puntos[i], puntos[i + 1], (km - acumulado[i]) / tramo if tramo else 0.0)


def ubicar_en_linea(puntos, acumulado, p, desde=0, cerca_km=0.04):
    """Ubica ``p`` sobre la polilinea buscando hacia adelante desde el vertice ``desde``.

    Devuelve ``(km, indice_tramo, distancia_km)``. En recorridos de ida y vuelta
    por la misma via, una estacion queda a ~0 m de ambos sentidos; por eso se toma
    el primer tramo que pase a menos de ``cerca_km`` (y su minimo local), y solo si
    ninguno pasa tan cerca se usa el minimo global.
    """
    mejor = None
    local = None
    for i in range(max(0, desde), len(puntos) - 1):
        a, b = puntos[i], puntos[i + 1]
        t = proyectar_en_tramo(p, a, b)
        d = distancia_km(p, interpolar(a, b, t))
        km = acumulado[i] + t * (acumulado[i + 1] - acumulado[i])
        if mejor is None or d < mejor[2]:
            mejor = (km, i, d)
        if d <= cerca_km:
            if local is None or d <= local[2]:
                local = (km, i, d)
        elif local is not None:
            return local
    return local or mejor or (0.0, 0, 0.0)


def simplificar(puntos, tolerancia_km=0.008):
    """Douglas-Peucker: reduce vertices sin alejarse mas de ``tolerancia_km``."""
    if len(puntos) < 3:
        return list(puntos)
    a, b = puntos[0], puntos[-1]
    peor_i, peor_d = 0, -1.0
    for i in range(1, len(puntos) - 1):
        d = distancia_km(puntos[i], interpolar(a, b, proyectar_en_tramo(puntos[i], a, b)))
        if d > peor_d:
            peor_i, peor_d = i, d
    if peor_d <= tolerancia_km:
        return [a, b]
    izquierda = simplificar(puntos[:peor_i + 1], tolerancia_km)
    return izquierda[:-1] + simplificar(puntos[peor_i:], tolerancia_km)
