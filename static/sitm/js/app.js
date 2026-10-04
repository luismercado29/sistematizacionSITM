/* SITM Cartagena · comportamiento común de la interfaz */
(function () {
  'use strict';

  var raiz = document.documentElement;

  function leer(clave) { try { return localStorage.getItem(clave); } catch (e) { return null; } }
  function guardar(clave, valor) { try { localStorage.setItem(clave, valor); } catch (e) { /* modo privado */ } }

  /* ---- Tema claro / oscuro ---- */
  function temaActual() {
    var fijado = raiz.getAttribute('data-theme');
    if (fijado) return fijado;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function pintarBotonesTema() {
    var oscuro = temaActual() === 'dark';
    document.querySelectorAll('[data-tema]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(oscuro));
      b.setAttribute('aria-label', oscuro ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro');
      b.title = b.getAttribute('aria-label');
      b.querySelectorAll('[data-icono-tema]').forEach(function (i) {
        i.hidden = i.getAttribute('data-icono-tema') !== (oscuro ? 'sol' : 'luna');
      });
    });
  }
  document.addEventListener('click', function (ev) {
    if (!ev.target.closest('[data-tema]')) return;
    var nuevo = temaActual() === 'dark' ? 'light' : 'dark';
    raiz.setAttribute('data-theme', nuevo);
    guardar('sitm-tema', nuevo);
    pintarBotonesTema();
    document.dispatchEvent(new CustomEvent('sitm:tema', { detail: nuevo }));
  });
  pintarBotonesTema();

  /* ---- Menú lateral en móvil ---- */
  var lateral = document.getElementById('lateral');
  var velo = document.querySelector('.velo');
  var abridor = document.querySelector('[data-abrir-menu]');
  function menu(abrir) {
    if (!lateral) return;
    lateral.classList.toggle('abierto', abrir);
    if (velo) velo.classList.toggle('visible', abrir);
    if (abridor) abridor.setAttribute('aria-expanded', String(abrir));
    if (abrir) { var primero = lateral.querySelector('a'); if (primero) primero.focus(); }
    else if (abridor) abridor.focus();
  }
  if (abridor) abridor.addEventListener('click', function () { menu(!lateral.classList.contains('abierto')); });
  if (velo) velo.addEventListener('click', function () { menu(false); });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && lateral && lateral.classList.contains('abierto')) menu(false);
  });

  /* ---- Diálogos de confirmación ---- */
  document.addEventListener('click', function (ev) {
    var abre = ev.target.closest('[data-dialogo]');
    if (abre) {
      var d = document.getElementById(abre.getAttribute('data-dialogo'));
      if (d && d.showModal) { ev.preventDefault(); d.showModal(); var f = d.querySelector('textarea, input:not([type=hidden])'); if (f) f.focus(); }
      return;
    }
    var cierra = ev.target.closest('[data-cerrar-dialogo]');
    if (cierra) { var dlg = cierra.closest('dialog'); if (dlg) dlg.close(); }
  });
  document.querySelectorAll('dialog.dialogo').forEach(function (d) {
    d.addEventListener('click', function (ev) { if (ev.target === d) d.close(); });
  });

  /* ---- Evitar doble envío y mostrar progreso ---- */
  document.addEventListener('submit', function (ev) {
    var form = ev.target;
    if (form.hasAttribute('data-sin-bloqueo')) return;
    if (form.dataset.enviando) { ev.preventDefault(); return; }
    form.dataset.enviando = '1';
    var boton = ev.submitter || form.querySelector('[type=submit]');
    if (boton) { boton.setAttribute('aria-disabled', 'true'); boton.dataset.textoOriginal = boton.textContent; }
  });
  window.addEventListener('pageshow', function () {
    document.querySelectorAll('form[data-enviando]').forEach(function (f) {
      delete f.dataset.enviando;
      f.querySelectorAll('[aria-disabled=true]').forEach(function (b) { b.removeAttribute('aria-disabled'); });
    });
  });

  /* ---- Mensajes flotantes ---- */
  document.querySelectorAll('.toast').forEach(function (t) {
    function quitar() { t.classList.add('sale'); setTimeout(function () { t.remove(); }, 160); }
    var boton = t.querySelector('button');
    if (boton) boton.addEventListener('click', quitar);
    if (!t.classList.contains('error')) setTimeout(quitar, 6000);
  });

  /* ---- Reloj de operación ---- */
  var reloj = document.querySelector('[data-reloj]');
  if (reloj) {
    var formato = new Intl.DateTimeFormat('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'America/Bogota' });
    var tic = function () { reloj.textContent = formato.format(new Date()); };
    tic(); setInterval(tic, 1000);
  }

  /* ---- Formulario de despacho: mostrar hora solo si se programa ---- */
  var cuando = document.querySelectorAll('input[name="cuando"]');
  var grupoHora = document.querySelector('[data-grupo-hora]');
  if (cuando.length && grupoHora) {
    var sync = function () {
      var programar = document.querySelector('input[name="cuando"]:checked');
      grupoHora.hidden = !(programar && programar.value === 'programar');
    };
    cuando.forEach(function (r) { r.addEventListener('change', sync); });
    sync();
  }

  /* ---- Mostrar / ocultar contraseña ---- */
  document.querySelectorAll('[data-ver-clave]').forEach(function (boton) {
    boton.addEventListener('click', function () {
      var campo = document.getElementById(boton.getAttribute('data-ver-clave'));
      if (!campo) return;
      var mostrar = campo.type === 'password';
      campo.type = mostrar ? 'text' : 'password';
      boton.setAttribute('aria-pressed', String(mostrar));
      boton.setAttribute('aria-label', mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña');
    });
  });

  /* ---- Selects que navegan al cambiar (p. ej. "Cambiar de estación") ---- */
  document.querySelectorAll('[data-enviar-al-cambiar]').forEach(function (s) {
    s.addEventListener('change', function () { if (s.value) s.form.submit(); });
  });

  /* ---- Envío automático de filtros al cambiar un select ---- */
  document.querySelectorAll('form[data-auto] select, form[data-auto] input[type=date]').forEach(function (c) {
    c.addEventListener('change', function () { c.form.requestSubmit ? c.form.requestSubmit() : c.form.submit(); });
  });
})();
