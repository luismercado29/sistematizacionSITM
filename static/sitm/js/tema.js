/* Aplica el tema guardado antes de pintar la página para evitar el destello.
 * Va en un archivo (no en línea) para que la Content-Security-Policy no
 * tenga que permitir scripts en línea. */
try {
  var t = localStorage.getItem('sitm-tema');
  if (t === 'dark' || t === 'light') document.documentElement.setAttribute('data-theme', t);
} catch (e) { /* almacenamiento bloqueado: se usa el tema del sistema */ }
