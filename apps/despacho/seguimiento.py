"""Posicion de los buses y tiempos estimados de llegada.

Cada bus en ruta tiene una posicion que viene de una de dos fuentes:

* ``gps``: el equipo a bordo reporto su ubicacion hace menos de
  ``GPS_VIGENCIA``. Se proyecta sobre el trazado de la ruta para saber cuantos
  kilometros lleva recorridos.
* ``estimada``: no hay reporte reciente, asi que se calcula con el tiempo
  transcurrido desde la salida y la velocidad comercial de la ruta.

Con los kilometros recorridos se obtiene la proxima parada y el tiempo que
falta para llegar a cualquier estacion posterior.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from apps.core.geo import acumulado_km, distancia_km, interpolar, proyectar_en_tramo, punto_en_linea
from apps.red.models import ParadaRuta

from .models import Despacho, PosicionGPS

GPS_VIGENCIA = timedelta(minutes=2)
# Margen para considerar que el bus ya esta "en" una parada.
TOLERANCIA_KM = 0.05


class Trazado:
    """Geometria de una ruta: el recorrido por la via y sus paradas con km acumulado.

    Si la ruta tiene ``trazado`` (la via real) se usa; si no, la linea entre
    paradas. En ambos casos los km de las paradas son los de ``ParadaRuta``,
    calculados sobre la misma geometria.
    """

    def __init__(self, ruta, paradas=None):
        self.ruta = ruta
        self.paradas = list(paradas if paradas is not None
                            else ruta.paradas.select_related('estacion'))
        if len(ruta.trazado or []) >= 2:
            self.puntos = [tuple(p) for p in ruta.trazado]
            self.km = acumulado_km(self.puntos)
        else:
            self.puntos = [p.estacion.coordenadas for p in self.paradas]
            self.km = [float(p.distancia_km) for p in self.paradas]
        self.total_km = float(self.paradas[-1].distancia_km) if self.paradas else (self.km[-1] if self.km else 0.0)

    def punto_en_km(self, km):
        if not self.puntos:
            return None
        # Las paradas pueden medir ligeramente distinto que el trazado (redondeo):
        # se escala para que el ultimo km de paradas coincida con el fin de la via.
        escala = (self.km[-1] / self.total_km) if self.total_km else 1.0
        return punto_en_linea(self.puntos, self.km, km * escala)

    def km_de_punto(self, punto, pista_km=None):
        """Kilometro del recorrido que corresponde a un punto GPS.

        En recorridos de ida y vuelta por la misma via un punto queda cerca de
        dos tramos; entre los candidatos se elige el mas cercano a ``pista_km``
        (la posicion esperada por horario).
        """
        if len(self.puntos) < 2:
            return 0.0
        escala = (self.total_km / self.km[-1]) if self.km[-1] else 1.0
        candidatos = []
        for i in range(len(self.puntos) - 1):
            a, b = self.puntos[i], self.puntos[i + 1]
            t = proyectar_en_tramo(punto, a, b)
            dist = distancia_km(punto, interpolar(a, b, t))
            candidatos.append((dist, (self.km[i] + t * (self.km[i + 1] - self.km[i])) * escala))
        minimo = min(d for d, _ in candidatos)
        cerca = [km for d, km in candidatos if d <= minimo + 0.05]
        if pista_km is None:
            return cerca[0]
        return min(cerca, key=lambda km: abs(km - pista_km))

    def minutos(self, km):
        return km / self.ruta.velocidad_kmh * 60

    @property
    def retorno(self):
        """Parada mas lejana del origen: donde un recorrido circular da la vuelta."""
        if not hasattr(self, '_retorno'):
            origen = self.paradas[0].estacion.coordenadas if self.paradas else None
            self._retorno = max(self.paradas, key=lambda p: distancia_km(origen, p.estacion.coordenadas),
                                default=None)
        return self._retorno

    def sentido(self, parada):
        """Hacia donde va un bus que pasa por ``parada`` (para el tablero de llegadas)."""
        ultima = self.paradas[-1] if self.paradas else None
        circular = ultima is not None and ultima.estacion_id == self.paradas[0].estacion_id
        if circular and self.retorno is not None and parada.orden < self.retorno.orden:
            return self.retorno.estacion.nombre
        return ultima.estacion.nombre if ultima else ''

    def proxima_parada(self, km):
        for parada in self.paradas:
            if float(parada.distancia_km) > km + TOLERANCIA_KM:
                return parada
        return None


@dataclass
class EstadoBus:
    despacho: Despacho
    latitud: float
    longitud: float
    km: float
    progreso: float
    fuente: str
    proxima_parada: ParadaRuta | None
    minutos_a_destino: int
    total_km: float = 0.0

    @property
    def en_destino(self):
        return self.proxima_parada is None

    def como_dict(self):
        d = self.despacho
        return {
            'despacho': d.pk,
            'folio': d.folio,
            'bus': d.bus.numero,
            'tipologia': d.bus.get_tipologia_display(),
            'ruta': d.ruta.codigo,
            'ruta_nombre': d.ruta.nombre,
            'color': d.ruta.color,
            'lat': round(self.latitud, 6),
            'lng': round(self.longitud, 6),
            'progreso': round(self.progreso, 3),
            'km': round(self.km, 3),
            'total_km': round(self.total_km, 3),
            'vel': d.ruta.velocidad_kmh if d.estado == Despacho.Estado.EN_RUTA and not self.en_destino else 0,
            'fuente': self.fuente,
            'proxima_parada': self.proxima_parada.estacion.nombre if self.proxima_parada else None,
            'minutos_a_destino': self.minutos_a_destino,
            'en_destino': self.en_destino,
        }


def ultimas_posiciones(despachos, ahora):
    """Ultimo reporte GPS vigente por despacho, en una sola consulta."""
    ids = [d.pk for d in despachos]
    if not ids:
        return {}
    resultado = {}
    reportes = (PosicionGPS.objects
                .filter(despacho_id__in=ids, registrado__gte=ahora - GPS_VIGENCIA)
                .order_by('despacho_id', '-registrado'))
    for pos in reportes:
        resultado.setdefault(pos.despacho_id, pos)
    return resultado


def estado_despacho(despacho, trazado, ahora=None, gps=None):
    ahora = ahora or timezone.now()
    if despacho.estado == Despacho.Estado.EN_RUTA and despacho.hora_salida:
        transcurrido_h = max(0.0, (ahora - despacho.hora_salida).total_seconds() / 3600)
        km_horario = min(trazado.total_km, transcurrido_h * despacho.ruta.velocidad_kmh)
    else:
        km_horario = 0.0
    if gps is not None:
        punto = (float(gps.latitud), float(gps.longitud))
        km = trazado.km_de_punto(punto, pista_km=km_horario)
        lat, lng = punto
        fuente = 'gps'
    else:
        km = km_horario
        lat, lng = trazado.punto_en_km(km)
        fuente = 'estimada'

    progreso = km / trazado.total_km if trazado.total_km else 0.0
    return EstadoBus(
        despacho=despacho, latitud=lat, longitud=lng, km=km, progreso=min(1.0, progreso),
        fuente=fuente, proxima_parada=trazado.proxima_parada(km),
        minutos_a_destino=max(0, round(trazado.minutos(trazado.total_km - km))),
        total_km=trazado.total_km,
    )


def _trazados(rutas):
    paradas = (ParadaRuta.objects.filter(ruta__in=rutas)
               .select_related('estacion').order_by('ruta_id', 'orden'))
    por_ruta = {}
    for p in paradas:
        por_ruta.setdefault(p.ruta_id, []).append(p)
    return {r.pk: Trazado(r, por_ruta.get(r.pk, [])) for r in rutas}


def flota_en_vivo(ahora=None, ruta=None):
    """Estado de todos los buses en ruta (opcionalmente de una sola ruta)."""
    ahora = ahora or timezone.now()
    despachos = (Despacho.objects.filter(estado=Despacho.Estado.EN_RUTA)
                 .select_related('ruta', 'bus', 'conductor'))
    if ruta is not None:
        despachos = despachos.filter(ruta=ruta)
    despachos = list(despachos)
    trazados = _trazados({d.ruta for d in despachos})
    gps = ultimas_posiciones(despachos, ahora)
    return [estado_despacho(d, trazados[d.ruta_id], ahora, gps.get(d.pk)) for d in despachos]


def llegadas_a_estacion(estacion, ahora=None, limite=10):
    """Proximos buses que pasaran por una estacion, ordenados por ETA."""
    ahora = ahora or timezone.now()
    paradas = list(ParadaRuta.objects.filter(estacion=estacion, ruta__activa=True)
                   .select_related('ruta'))
    if not paradas:
        return []
    rutas = {p.ruta for p in paradas}
    trazados = _trazados(rutas)
    despachos = list(Despacho.objects
                     .filter(ruta__in=rutas, estado__in=Despacho.ACTIVOS)
                     .select_related('ruta', 'bus'))
    gps = ultimas_posiciones([d for d in despachos if d.estado == Despacho.Estado.EN_RUTA], ahora)

    llegadas = []
    for parada in paradas:
        trazado = trazados[parada.ruta_id]
        # La ultima parada es el fin del recorrido: ningun pasajero aborda ahi.
        if trazado.paradas and parada.pk == trazado.paradas[-1].pk:
            continue
        km_parada = float(parada.distancia_km)
        for d in despachos:
            if d.ruta_id != parada.ruta_id:
                continue
            if d.estado == Despacho.Estado.EN_RUTA:
                estado = estado_despacho(d, trazado, ahora, gps.get(d.pk))
                if estado.km > km_parada + TOLERANCIA_KM:
                    continue
                minutos = trazado.minutos(km_parada - estado.km)
                fuente = estado.fuente
            else:
                espera = max(0.0, (d.hora_programada - ahora).total_seconds() / 60)
                minutos = espera + parada.minutos_desde_inicio
                fuente = 'programado'
            llegadas.append({
                'despacho': d.pk,
                'ruta': d.ruta.codigo,
                'ruta_nombre': d.ruta.nombre,
                'color': d.ruta.color,
                'destino': trazado.sentido(parada),
                'bus': d.bus.numero,
                'tipologia': d.bus.get_tipologia_display(),
                'minutos': max(0, round(minutos)),
                'hora': timezone.localtime(ahora + timedelta(minutes=minutos)).strftime('%H:%M'),
                'fuente': fuente,
            })
    llegadas.sort(key=lambda x: x['minutos'])
    return llegadas[:limite]


def itinerario(despacho, ahora=None):
    """Paso por cada parada: hora real/estimada y si ya la supero."""
    ahora = ahora or timezone.now()
    trazado = Trazado(despacho.ruta)
    base = despacho.hora_salida or despacho.hora_programada
    estado = None
    if despacho.estado == Despacho.Estado.EN_RUTA:
        gps = ultimas_posiciones([despacho], ahora).get(despacho.pk)
        estado = estado_despacho(despacho, trazado, ahora, gps)

    filas = []
    for parada in trazado.paradas:
        km = float(parada.distancia_km)
        if despacho.estado == Despacho.Estado.FINALIZADO:
            situacion = 'pasada'
        elif estado is not None:
            situacion = 'pasada' if estado.km >= km - TOLERANCIA_KM else 'pendiente'
        else:
            situacion = 'pendiente'
        if estado is not None and situacion == 'pendiente':
            hora = ahora + timedelta(minutes=trazado.minutos(km - estado.km))
        else:
            hora = base + timedelta(minutes=parada.minutos_desde_inicio)
        filas.append({'parada': parada, 'hora': hora, 'situacion': situacion,
                      'es_proxima': estado is not None and estado.proxima_parada == parada})
    return trazado, estado, filas
