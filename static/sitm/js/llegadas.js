/* SITM Cartagena · actualización en vivo de llegadas (estación) y próximos buses (ruta) */
(function () {
  'use strict';
  var esc = (window.SITM && window.SITM.esc) || function (t) { return String(t); };
  var minutos = (window.SITM && window.SITM.textoMinutos) || function (m) { return m + ' min'; };

  function color(v) { return /^#[0-9a-f]{6}$/i.test(v) ? v : '#1D4ED8'; }

  function sondear(url, cada, alRecibir, estado) {
    var t = null, ultimo = null;
    function marcar(error) {
      if (!estado) return;
      if (error) { estado.textContent = 'Sin conexión. Reintentando…'; return; }
      if (!ultimo) return;
      var s = Math.round((Date.now() - ultimo) / 1000);
      estado.textContent = s < 5 ? 'Actualizado ahora' : 'Actualizado hace ' + s + ' s';
    }
    setInterval(function () { marcar(false); }, 5000);
    function ir() {
      clearTimeout(t);
      if (document.hidden) return;
      fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (d) { alRecibir(d); ultimo = Date.now(); marcar(false); })
        .catch(function () { marcar(true); })
        .then(function () { t = setTimeout(ir, cada); });
    }
    document.addEventListener('visibilitychange', function () { if (!document.hidden) ir(); });
    t = setTimeout(ir, cada);
  }

  /* Tablero de llegadas de una estación */
  var lista = document.querySelector('[data-llegadas]');
  if (lista) {
    var vacio = document.querySelector('[data-llegadas-vacio]');
    var anuncio = document.querySelector('[data-llegadas-anuncio]');
    sondear(lista.dataset.llegadas, parseInt(lista.dataset.refresco || '10', 10) * 1000, function (d) {
      var items = d.llegadas || [];
      lista.hidden = items.length === 0;
      if (vacio) vacio.hidden = items.length !== 0;
      lista.innerHTML = items.map(function (l) {
        var fuente = l.fuente === 'gps' ? '<span class="fuente gps">GPS</span>'
          : l.fuente === 'programado' ? '<span class="fuente">Programado</span>' : '<span class="fuente">Estimado</span>';
        return '<li class="llegada' + (l.minutos <= 2 ? ' inminente' : '') + '">' +
          '<span class="chip-ruta lg" style="--ruta:' + color(l.color) + '">' + esc(l.ruta) + '</span>' +
          '<div><div class="destino">Hacia ' + esc(l.destino) + '</div>' +
          '<div class="detalle"><span>Bus ' + esc(l.bus) + '</span><span aria-hidden="true">·</span><span>' + esc(l.tipologia) + '</span>' + fuente + '</div></div>' +
          '<div class="eta"><strong>' + (l.minutos <= 0 ? 'Ya' : esc(l.minutos)) + '</strong><small>' +
          (l.minutos <= 0 ? 'llegando' : 'min · ' + esc(l.hora)) + '</small></div></li>';
      }).join('');
      if (anuncio && items.length) anuncio.textContent = 'Próximo bus: ruta ' + items[0].ruta + ' en ' + minutos(items[0].minutos) + '.';
    }, document.querySelector('[data-estado-llegadas]'));
  }

  /* Próximo bus por parada en la página de una ruta */
  var paradas = document.querySelector('[data-paradas-ruta]');
  if (paradas) {
    sondear(paradas.dataset.paradasRuta, parseInt(paradas.dataset.refresco || '10', 10) * 1000, function (d) {
      (d.paradas || []).forEach(function (p) {
        var nodo = paradas.querySelector('[data-prox="' + p.codigo + '"]');
        if (nodo) nodo.textContent = p.proximo_min == null ? 'Sin buses' : minutos(p.proximo_min);
      });
      var conteo = document.querySelector('[data-buses-ruta]');
      if (conteo) conteo.textContent = (d.buses || []).length;
    }, null);
  }
})();
