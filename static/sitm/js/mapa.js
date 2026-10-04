/* SITM Cartagena · mapa en vivo de la flota (Leaflet)
 *
 * <div class="mapa" data-mapa
 *      data-api="/api/v1/flota/"          posiciones de los buses (se consulta cada N s)
 *      data-red="red-json"                id de un <script type="application/json"> con las rutas
 *      data-enlace="/operacion/despachos/{id}/"   (opcional) enlace del popup del bus
 *      data-rutas="T101,T102"             (opcional) solo estas rutas
 *      data-estacion="10.41,-75.53"       (opcional) estación destacada y centro inicial
 *      data-refresco="10"></div>
 */
(function () {
  'use strict';
  if (!window.L) return;

  var reducirMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var ICONO_BUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 6v6"/><path d="M15 6v6"/><path d="M2 12h19.6"/><path d="M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3"/><circle cx="7" cy="18" r="2"/><path d="M9 18h5"/><circle cx="16" cy="18" r="2"/></svg>';
  var CARTAGENA = [10.405, -75.51];

  function esc(texto) {
    return String(texto == null ? '' : texto).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function color(valor) { return /^#[0-9a-f]{6}$/i.test(valor) ? valor : '#1D4ED8'; }
  function temaOscuro() {
    var t = document.documentElement.getAttribute('data-theme');
    return t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  // Token publico de Mapbox (pk.*) inyectado por el servidor. Sin token se usa OpenStreetMap.
  var nodoToken = document.querySelector('meta[name="sitm-mapbox"]');
  var MAPBOX = nodoToken ? nodoToken.content : '';
  var ATRIB_OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

  function teselas() {
    if (MAPBOX) {
      var estilo = temaOscuro() ? 'dark-v11' : 'light-v11';
      return L.tileLayer('https://api.mapbox.com/styles/v1/mapbox/' + estilo + '/tiles/{z}/{x}/{y}?access_token=' + encodeURIComponent(MAPBOX), {
        tileSize: 512, zoomOffset: -1, maxZoom: 20,
        attribution: '&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> ' + ATRIB_OSM +
          ' <a href="https://www.mapbox.com/map-feedback/" target="_blank" rel="noopener">Mejorar este mapa</a>'
      });
    }
    return L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: ATRIB_OSM });
  }
  // Con OpenStreetMap el tema oscuro se logra invirtiendo las teselas por CSS;
  // Mapbox ya trae un estilo oscuro propio.
  function aplicarTema(el) { el.classList.toggle('mapa-oscuro', !MAPBOX && temaOscuro()); }
  function textoMinutos(m) {
    if (m == null) return '—';
    if (m <= 0) return 'Llegando';
    if (m < 60) return m + ' min';
    return Math.floor(m / 60) + ' h ' + (m % 60) + ' min';
  }

  /* Atribución compacta: los créditos de Mapbox/OpenStreetMap son obligatorios por
   * licencia, pero se muestran plegados tras un botón ⓘ (como hace Mapbox GL).
   * El prefijo "Leaflet" sí es opcional y se omite. Leaflet reescribe el contenedor
   * en cada cambio de capas, por eso el texto vive en su propio <span>. */
  var AtribucionCompacta = L.Control.Attribution.extend({
    options: { prefix: false },
    onAdd: function (mapa) {
      var caja = L.Control.Attribution.prototype.onAdd.call(this, mapa);
      caja.innerHTML = '';
      caja.classList.add('atribucion-compacta');
      var boton = L.DomUtil.create('button', 'atribucion-boton', caja);
      boton.type = 'button';
      boton.setAttribute('aria-label', 'Créditos del mapa');
      boton.setAttribute('aria-expanded', 'false');
      boton.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>';
      this._texto = L.DomUtil.create('span', 'atribucion-texto', caja);
      L.DomEvent.on(boton, 'click', function () {
        boton.setAttribute('aria-expanded', String(caja.classList.toggle('abierta')));
      });
      this._update();
      return caja;
    },
    _update: function () {
      if (!this._map || !this._texto) return;
      var textos = [];
      for (var t in this._attributions) { if (this._attributions[t]) textos.push(t); }
      this._texto.innerHTML = textos.join(' ');
    }
  });

  /* Geometría: las mismas fórmulas que apps/core/geo.py, para que el km que
   * calcula el servidor caiga exactamente en el mismo punto del recorrido. */
  function distanciaKm(a, b) {
    var r = Math.PI / 180, dLat = (b[0] - a[0]) * r, dLng = (b[1] - a[1]) * r;
    var h = Math.pow(Math.sin(dLat / 2), 2) + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.pow(Math.sin(dLng / 2), 2);
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  }
  function geometria(puntos) {
    var acum = [0];
    for (var i = 1; i < puntos.length; i++) acum.push(acum[i - 1] + distanciaKm(puntos[i - 1], puntos[i]));
    return { puntos: puntos, acum: acum, total: acum[acum.length - 1] || 0 };
  }
  function puntoEnKm(g, km) {
    var p = g.puntos, a = g.acum;
    if (km <= 0) return p[0];
    if (km >= g.total) return p[p.length - 1];
    var lo = 0, hi = a.length - 1;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (a[mid] <= km) lo = mid; else hi = mid; }
    var tramo = a[hi] - a[lo], f = tramo ? (km - a[lo]) / tramo : 0;
    return [p[lo][0] + (p[hi][0] - p[lo][0]) * f, p[lo][1] + (p[hi][1] - p[lo][1]) * f];
  }

  function crear(el) {
    var opciones = el.dataset;
    var soloRutas = opciones.rutas ? opciones.rutas.split(',') : null;
    var refresco = Math.max(5, parseInt(opciones.refresco || '10', 10)) * 1000;
    var mapa = L.map(el, { zoomControl: true, attributionControl: false, scrollWheelZoom: !el.hasAttribute('data-sin-rueda') });
    new AtribucionCompacta({ position: 'bottomright' }).addTo(mapa);
    mapa.setView(CARTAGENA, 13);
    var capaBase = teselas().addTo(mapa);
    aplicarTema(el);
    document.addEventListener('sitm:tema', function () {
      if (MAPBOX) { mapa.removeLayer(capaBase); capaBase = teselas().addTo(mapa); capaBase.bringToBack(); }
      aplicarTema(el);
    });

    var capasRuta = {};   // codigo -> L.layerGroup (trazado + paradas)
    var capaBuses = L.layerGroup().addTo(mapa);
    var marcadores = {};  // despacho -> {marker, datos, km0, t0}
    var geometrias = {};  // codigo de ruta -> geometria del recorrido
    var capaEstaciones = L.layerGroup().addTo(mapa);
    var estacionesPintadas = {};
    var ocultas = {};
    var limites = L.latLngBounds([]);

    /* Trazado de las rutas */
    var nodoRed = opciones.red && document.getElementById(opciones.red);
    var red = nodoRed ? JSON.parse(nodoRed.textContent) : [];
    red.forEach(function (ruta) {
      if (soloRutas && soloRutas.indexOf(ruta.codigo) === -1) return;
      var c = color(ruta.color);
      var puntos = (ruta.trazado && ruta.trazado.length > 1) ? ruta.trazado : ruta.paradas.map(function (p) { return [p.lat, p.lng]; });
      geometrias[ruta.codigo] = geometria(puntos);
      var grupo = L.layerGroup();
      L.polyline(puntos, { color: '#ffffff', weight: 7, opacity: .8, interactive: false }).addTo(grupo);
      L.polyline(puntos, { color: c, weight: 4, opacity: .9 }).addTo(grupo)
        .bindTooltip(esc(ruta.codigo + ' · ' + ruta.nombre), { sticky: true });
      puntos.forEach(function (p) { limites.extend(p); });
      // Una estacion la comparten varias rutas: se dibuja una sola vez.
      ruta.paradas.forEach(function (p) {
        var clave = p.nombre + p.lat + p.lng;
        if (estacionesPintadas[clave]) return;
        estacionesPintadas[clave] = true;
        L.marker([p.lat, p.lng], {
          icon: L.divIcon({ className: '', html: '<div class="marcador-estacion" style="--ruta:' + c + '"></div>', iconSize: null }),
          keyboard: false, title: p.nombre
        }).bindPopup('<strong>' + esc(p.nombre) + '</strong>' +
          (p.url ? '<br><a href="' + esc(p.url) + '">Ver próximas llegadas</a>' : '')).addTo(capaEstaciones);
      });
      grupo.addTo(mapa);
      capasRuta[ruta.codigo] = grupo;
    });

    if (opciones.estacion) {
      var e = opciones.estacion.split(',').map(Number);
      L.marker(e, {
        icon: L.divIcon({ className: '', html: '<div class="marcador-estacion destacada" style="--ruta:#EA580C"></div>', iconSize: null }),
        zIndexOffset: 1000, title: 'Estación seleccionada'
      }).addTo(mapa);
      mapa.setView(e, 15);
    } else if (limites.isValid()) {
      mapa.fitBounds(limites, { padding: [24, 24] });
    }

    /* Filtro por ruta (checkboxes con data-filtro-ruta) */
    var filtro = document.querySelector('[data-filtro-mapa="' + el.id + '"]');
    function mostrarRuta(codigo, visible) {
      ocultas[codigo] = !visible;
      if (capasRuta[codigo]) { if (visible) capasRuta[codigo].addTo(mapa); else mapa.removeLayer(capasRuta[codigo]); }
    }
    if (filtro) {
      filtro.addEventListener('change', function (ev) {
        mostrarRuta(ev.target.value, ev.target.checked);
        Object.keys(marcadores).forEach(function (id) { visibilidad(marcadores[id]); });
      });
      [['todas', true], ['ninguna', false]].forEach(function (par) {
        var boton = document.querySelector('[data-filtro-' + par[0] + '="' + el.id + '"]');
        if (!boton) return;
        boton.addEventListener('click', function () {
          filtro.querySelectorAll('input[type=checkbox]').forEach(function (c) { c.checked = par[1]; mostrarRuta(c.value, par[1]); });
          Object.keys(marcadores).forEach(function (id) { visibilidad(marcadores[id]); });
        });
      });
    }
    // En el detalle de un despacho, su bus se resalta y los demas se atenuan.
    var destacado = opciones.destacar;
    if (destacado) el.classList.add('con-destacado');

    function visibilidad(m) {
      var visible = !ocultas[m.datos.ruta];
      if (visible && !capaBuses.hasLayer(m.marker)) capaBuses.addLayer(m.marker);
      if (!visible && capaBuses.hasLayer(m.marker)) capaBuses.removeLayer(m.marker);
    }

    function icono(b) {
      return L.divIcon({
        className: '', iconSize: null,
        html: '<div class="marcador-bus ' + (b.fuente === 'gps' ? 'gps' : 'estimada') +
          (destacado && String(b.despacho) === destacado ? ' destacado' : '') + '" style="--ruta:' + color(b.color) + '">' +
          ICONO_BUS + '<span>' + esc(b.ruta) + '</span></div>'
      });
    }

    function popup(b) {
      var enlace = opciones.enlace ? '<a href="' + esc(opciones.enlace.replace('{id}', b.despacho)) + '">Abrir despacho ' + esc(b.folio) + '</a>' : '';
      return '<div class="popup-bus"><strong>Bus ' + esc(b.bus) + ' · ' + esc(b.ruta) + '</strong>' +
        '<span>' + esc(b.ruta_nombre) + '</span>' +
        '<span>' + (b.en_destino ? 'En la terminal' : 'Próxima parada: <b>' + esc(b.proxima_parada) + '</b>') + '</span>' +
        '<span>Llega al destino en <b>' + textoMinutos(b.minutos_a_destino) + '</b></span>' +
        '<span class="sutil">' + (b.fuente === 'gps' ? 'Posición GPS' : 'Posición estimada por horario') + ' · ' + esc(b.tipologia) + '</span>' +
        enlace + '</div>';
    }

    /* Movimiento continuo: entre una consulta y otra cada bus avanza sobre su
     * recorrido a la velocidad comercial de la ruta (la misma que usa el
     * servidor), así se desliza por la vía en lugar de saltar cada N segundos. */
    function posicion(m, ahora) {
      var b = m.datos, g = geometrias[b.ruta];
      if (!g || !b.total_km || reducirMovimiento) return [b.lat, b.lng];
      var km = Math.min(b.total_km, m.km0 + b.vel * (ahora - m.t0) / 3600000);
      return puntoEnKm(g, km * g.total / b.total_km);
    }
    function avanzar() {
      var ahora = Date.now();
      Object.keys(marcadores).forEach(function (id) {
        var m = marcadores[id];
        if (capaBuses.hasLayer(m.marker)) m.marker.setLatLng(posicion(m, ahora));
      });
    }
    if (!reducirMovimiento) setInterval(function () { if (!document.hidden) avanzar(); }, 250);

    function pintar(buses) {
      var vistos = {};
      buses.forEach(function (b) {
        if (soloRutas && soloRutas.indexOf(b.ruta) === -1) return;
        vistos[b.despacho] = true;
        var m = marcadores[b.despacho];
        if (!m) {
          var esDestacado = destacado && String(b.despacho) === destacado;
          var marker = L.marker([b.lat, b.lng], { icon: icono(b), title: 'Bus ' + b.bus + ', ruta ' + b.ruta,
            riseOnHover: true, zIndexOffset: esDestacado ? 1000 : 0 });
          marker.bindPopup(popup(b));
          marker.bindTooltip('Bus ' + esc(b.bus) + ' · ' + esc(b.ruta), { direction: 'top', offset: [0, -12] });
          m = marcadores[b.despacho] = { marker: marker, datos: b, km0: b.km || 0, t0: Date.now() };
          marker.setLatLng(posicion(m, Date.now()));
        } else {
          if (m.datos.fuente !== b.fuente) m.marker.setIcon(icono(b));
          // Si el cálculo local iba un poco adelantado, no se retrocede el bus.
          var actual = m.km0 + m.datos.vel * (Date.now() - m.t0) / 3600000;
          m.km0 = (b.km < actual && actual - b.km < 0.08) ? actual : b.km;
          m.t0 = Date.now();
          m.datos = b;
          m.marker.setPopupContent(popup(b));
          m.marker.setLatLng(posicion(m, Date.now()));
        }
        visibilidad(m);
      });
      Object.keys(marcadores).forEach(function (id) {
        if (!vistos[id]) { capaBuses.removeLayer(marcadores[id].marker); delete marcadores[id]; }
      });
      document.querySelectorAll('[data-conteo-buses="' + el.id + '"]').forEach(function (n) { n.textContent = Object.keys(vistos).length; });
    }

    var estado = document.querySelector('[data-estado-mapa="' + el.id + '"]');
    var ultimo = null, temporizador = null;
    function textoEstado(error) {
      if (!estado) return;
      if (error) { estado.textContent = 'Sin conexión. Reintentando…'; return; }
      if (!ultimo) return;
      var s = Math.round((Date.now() - ultimo) / 1000);
      estado.textContent = s < 5 ? 'Actualizado ahora' : 'Actualizado hace ' + s + ' s';
    }
    setInterval(function () { textoEstado(false); }, 5000);

    function consultar() {
      clearTimeout(temporizador);
      if (document.hidden) return;
      fetch(opciones.api, { headers: { Accept: 'application/json' }, cache: 'no-store' })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (datos) { pintar(datos.buses || []); ultimo = Date.now(); textoEstado(false); })
        .catch(function () { textoEstado(true); })
        .then(function () { temporizador = setTimeout(consultar, refresco); });
    }
    document.addEventListener('visibilitychange', function () { if (!document.hidden) consultar(); });
    consultar();
    return mapa;
  }

  window.SITM = window.SITM || {};
  window.SITM.textoMinutos = textoMinutos;
  window.SITM.esc = esc;
  document.querySelectorAll('[data-mapa]').forEach(crear);
})();
