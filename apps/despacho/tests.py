import json
from io import StringIO
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.roles import DESPACHADORES, SUPERVISORES
from apps.flota.models import Bus, Conductor
from apps.red.models import Estacion, Ruta

from . import demo, seguimiento, servicios
from .models import Despacho, EventoDespacho, PosicionGPS


@override_settings(SITM_MODO_DEMO=False)  # independiente del .env local
class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('cargar_demo', stdout=StringIO())
        cls.ruta = Ruta.objects.get(codigo='T101')
        cls.padron = Bus.objects.filter(tipologia=Bus.Tipologia.PADRON, estado=Bus.Estado.DISPONIBLE).first()
        cls.articulado = Bus.objects.filter(tipologia=Bus.Tipologia.ARTICULADO, estado=Bus.Estado.DISPONIBLE).first()
        cls.c3 = Conductor.objects.filter(categoria='C3', estado=Conductor.Estado.ACTIVO).first()
        cls.c2 = Conductor.objects.filter(categoria='C2', estado=Conductor.Estado.ACTIVO).first()
        cls.despachador = User.objects.create_user('desp', password='x')
        cls.despachador.groups.add(Group.objects.get(name=DESPACHADORES))
        cls.supervisor = User.objects.create_user('sup', password='x')
        cls.supervisor.groups.add(Group.objects.get(name=SUPERVISORES))

    def setUp(self):
        cache.clear()  # los limites de intentos viven en la cache

    def despachar(self, bus=None, conductor=None, **kw):
        return servicios.crear_despacho(ruta=self.ruta, bus=bus or self.padron,
                                        conductor=conductor or self.c2, usuario=self.despachador, **kw)


class ReglasDeDespachoTests(Base):
    def test_ciclo_completo_actualiza_bus_y_bitacora(self):
        d = self.despachar(salir_ahora=True)
        self.padron.refresh_from_db()
        self.assertEqual(d.estado, Despacho.Estado.EN_RUTA)
        self.assertEqual(self.padron.estado, Bus.Estado.EN_SERVICIO)

        servicios.finalizar_despacho(d, self.despachador)
        d.refresh_from_db(); self.padron.refresh_from_db()
        self.assertEqual(d.estado, Despacho.Estado.FINALIZADO)
        self.assertIsNotNone(d.hora_llegada)
        self.assertEqual(self.padron.estado, Bus.Estado.DISPONIBLE)
        self.assertEqual(list(d.eventos.order_by('creado').values_list('tipo', flat=True)),
                         ['creado', 'salida', 'llegada'])

    def test_bus_no_puede_tener_dos_despachos_activos(self):
        self.despachar()
        otro = Conductor.objects.filter(estado=Conductor.Estado.ACTIVO).exclude(pk=self.c2.pk).first()
        with self.assertRaisesMessage(servicios.ErrorDespacho, 'ya tiene un despacho activo'):
            self.despachar(conductor=otro)

    def test_conductor_no_puede_tener_dos_despachos_activos(self):
        self.despachar()
        otro_bus = Bus.objects.filter(estado=Bus.Estado.DISPONIBLE, tipologia=Bus.Tipologia.PADRON).exclude(pk=self.padron.pk).first()
        with self.assertRaisesMessage(servicios.ErrorDespacho, 'otro despacho activo'):
            self.despachar(bus=otro_bus)

    def test_articulado_exige_licencia_c3(self):
        with self.assertRaisesMessage(servicios.ErrorDespacho, 'exige C3'):
            self.despachar(bus=self.articulado, conductor=self.c2)
        self.assertEqual(self.despachar(bus=self.articulado, conductor=self.c3).estado, Despacho.Estado.PROGRAMADO)

    def test_licencia_vencida_bloquea_el_despacho(self):
        self.c2.vencimiento_licencia = timezone.localdate() - timedelta(days=1)
        self.c2.save()
        with self.assertRaisesMessage(servicios.ErrorDespacho, 'venció'):
            self.despachar()

    def test_bus_en_mantenimiento_no_se_despacha(self):
        taller = Bus.objects.filter(estado=Bus.Estado.MANTENIMIENTO).first()
        with self.assertRaisesMessage(servicios.ErrorDespacho, 'no está disponible'):
            self.despachar(bus=taller)

    def test_cancelar_exige_motivo_y_libera_recursos(self):
        d = self.despachar(salir_ahora=True)
        with self.assertRaises(servicios.ErrorDespacho):
            servicios.cancelar_despacho(d, self.despachador, '  ')
        servicios.cancelar_despacho(d, self.despachador, 'Pinchazo en la llanta')
        self.padron.refresh_from_db()
        self.assertEqual(self.padron.estado, Bus.Estado.DISPONIBLE)
        self.assertIn(self.c2, servicios.conductores_disponibles())

    def test_no_se_finaliza_un_despacho_programado(self):
        d = self.despachar()
        with self.assertRaises(servicios.ErrorDespacho):
            servicios.finalizar_despacho(d, self.despachador)

    def test_bus_enviado_a_taller_en_ruta_no_vuelve_a_disponible(self):
        d = self.despachar(salir_ahora=True)
        Bus.objects.filter(pk=self.padron.pk).update(estado=Bus.Estado.MANTENIMIENTO)
        servicios.finalizar_despacho(d, self.despachador)
        self.padron.refresh_from_db()
        self.assertEqual(self.padron.estado, Bus.Estado.MANTENIMIENTO)


class SeguimientoTests(Base):
    def test_posicion_estimada_avanza_con_el_tiempo(self):
        ahora = timezone.now()
        d = self.despachar(salir_ahora=True, ahora=ahora - timedelta(minutes=10))
        trazado = seguimiento.Trazado(self.ruta)
        estado = seguimiento.estado_despacho(d, trazado, ahora)
        esperado_km = 10 / 60 * self.ruta.velocidad_kmh
        self.assertAlmostEqual(estado.km, esperado_km, places=2)
        self.assertEqual(estado.fuente, 'estimada')
        self.assertGreater(float(estado.proxima_parada.distancia_km), estado.km)

    def test_gps_reciente_tiene_prioridad(self):
        ahora = timezone.now()
        d = self.despachar(salir_ahora=True, ahora=ahora - timedelta(minutes=1))
        bazurto = Estacion.objects.get(codigo='bazurto')
        PosicionGPS.objects.create(bus=d.bus, despacho=d, latitud=bazurto.latitud,
                                   longitud=bazurto.longitud, registrado=ahora)
        estado = seguimiento.flota_en_vivo(ahora)[0]
        ida = float(self.ruta.paradas.filter(estacion=bazurto).order_by('orden').first().distancia_km)
        self.assertEqual(estado.fuente, 'gps')
        self.assertAlmostEqual(estado.km, ida, delta=0.1)

    def test_gps_en_ruta_circular_respeta_el_sentido(self):
        """Bazurto se pasa a la ida y a la vuelta: el GPS se ubica segun el horario."""
        ahora = timezone.now()
        bazurto = Estacion.objects.get(codigo='bazurto')
        vuelta = float(self.ruta.paradas.filter(estacion=bazurto).order_by('orden').last().distancia_km)
        salida = ahora - timedelta(minutes=vuelta / self.ruta.velocidad_kmh * 60)
        d = self.despachar(salir_ahora=True, ahora=salida)
        PosicionGPS.objects.create(bus=d.bus, despacho=d, latitud=bazurto.latitud,
                                   longitud=bazurto.longitud, registrado=ahora)
        self.assertAlmostEqual(seguimiento.flota_en_vivo(ahora)[0].km, vuelta, delta=0.1)

    def test_la_posicion_sigue_la_via(self):
        """El bus se dibuja sobre el trazado real, no en linea recta entre paradas."""
        ahora = timezone.now()
        self.despachar(salir_ahora=True, ahora=ahora - timedelta(minutes=7))
        estado = seguimiento.flota_en_vivo(ahora)[0]
        trazado = seguimiento.Trazado(self.ruta)
        km = trazado.km_de_punto((estado.latitud, estado.longitud), pista_km=estado.km)
        self.assertAlmostEqual(km, estado.km, delta=0.05)
        self.assertGreater(len(self.ruta.trazado), 20)

    def test_gps_viejo_se_ignora(self):
        ahora = timezone.now()
        d = self.despachar(salir_ahora=True, ahora=ahora - timedelta(minutes=1))
        PosicionGPS.objects.create(bus=d.bus, despacho=d, latitud=10.42, longitud=-75.54,
                                   registrado=ahora - timedelta(minutes=10))
        self.assertEqual(seguimiento.flota_en_vivo(ahora)[0].fuente, 'estimada')

    def test_llegadas_excluyen_buses_que_ya_pasaron(self):
        ahora = timezone.now()
        bazurto = Estacion.objects.get(codigo='bazurto')
        cerca = self.despachar(salir_ahora=True, ahora=ahora - timedelta(minutes=5))
        otro_bus = Bus.objects.filter(estado=Bus.Estado.DISPONIBLE, tipologia=Bus.Tipologia.ARTICULADO).first()
        lejos = self.despachar(bus=otro_bus, conductor=self.c3, salir_ahora=True,
                               ahora=ahora - timedelta(minutes=self.ruta.duracion_min - 1))
        ids = [l['despacho'] for l in seguimiento.llegadas_a_estacion(bazurto, ahora)]
        self.assertIn(cerca.pk, ids)
        self.assertNotIn(lejos.pk, ids)

    def test_sentido_de_las_llegadas_en_ruta_circular(self):
        """A la ida el bus va hacia La Bodeguita; despues del retorno, hacia el Portal."""
        ahora = timezone.now()
        bazurto = Estacion.objects.get(codigo='bazurto')
        self.despachar(salir_ahora=True, ahora=ahora - timedelta(minutes=2))
        destinos = [l['destino'] for l in seguimiento.llegadas_a_estacion(bazurto, ahora) if l['ruta'] == 'T101']
        self.assertEqual(destinos, ['La Bodeguita', 'Portal'])

    def test_el_final_del_circuito_no_cuenta_como_llegada(self):
        ahora = timezone.now()
        self.despachar(salir_ahora=True, ahora=ahora - timedelta(minutes=30))
        portal = Estacion.objects.get(codigo='portal')
        self.assertFalse([l for l in seguimiento.llegadas_a_estacion(portal, ahora) if l['ruta'] == 'T101'])


class ApiTests(Base):
    def test_flota_no_expone_datos_del_conductor(self):
        self.despachar(salir_ahora=True)
        datos = self.client.get(reverse('api:flota')).json()
        self.assertEqual(len(datos['buses']), 1)
        self.assertNotIn(self.c2.nombre, json.dumps(datos, ensure_ascii=False))

    def test_gps_requiere_token(self):
        r = self.client.post(reverse('api:gps'), {'lat': 1, 'lng': 1}, content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_gps_valida_coordenadas(self):
        r = self.client.post(reverse('api:gps'), {'lat': 'x'}, content_type='application/json',
                             HTTP_AUTHORIZATION=f'Bearer {self.padron.token_gps}')
        self.assertEqual(r.status_code, 400)
        r = self.client.post(reverse('api:gps'), {'lat': 200, 'lng': 0}, content_type='application/json',
                             HTTP_AUTHORIZATION=f'Bearer {self.padron.token_gps}')
        self.assertEqual(r.status_code, 400)

    def test_gps_se_asocia_al_despacho_en_ruta(self):
        d = self.despachar(salir_ahora=True)
        r = self.client.post(reverse('api:gps'), {'lat': 10.41, 'lng': -75.53, 'velocidad': 31.2},
                             content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {self.padron.token_gps}')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(PosicionGPS.objects.get().despacho, d)


class PermisosYVistasTests(Base):
    def test_anonimo_va_al_login(self):
        r = self.client.get(reverse('operacion:tablero'))
        self.assertRedirects(r, f"{reverse('cuentas:ingresar')}?next={reverse('operacion:tablero')}")

    def test_usuario_sin_rol_recibe_403(self):
        self.client.force_login(User.objects.create_user('nadie', password='x'))
        self.assertEqual(self.client.get(reverse('operacion:tablero')).status_code, 403)

    def test_despachador_no_edita_flota_pero_supervisor_si(self):
        url = reverse('operacion:bus_editar', args=[self.padron.pk])
        self.client.force_login(self.despachador)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_despachar_desde_el_formulario(self):
        self.client.force_login(self.despachador)
        r = self.client.post(reverse('operacion:nuevo'), {
            'ruta': self.ruta.pk, 'bus': self.padron.pk, 'conductor': self.c2.pk, 'cuando': 'ahora'})
        d = Despacho.objects.get()
        self.assertRedirects(r, reverse('operacion:despacho', args=[d.pk]))
        self.assertEqual(d.estado, Despacho.Estado.EN_RUTA)
        self.assertEqual(d.despachador, self.despachador)

    def test_cancelar_desde_la_vista_registra_motivo(self):
        d = self.despachar(salir_ahora=True)
        self.client.force_login(self.despachador)
        self.client.post(reverse('operacion:cancelar', args=[d.pk]), {'motivo': 'Bloqueo en la vía'})
        d.refresh_from_db()
        self.assertEqual(d.estado, Despacho.Estado.CANCELADO)
        self.assertTrue(EventoDespacho.objects.filter(despacho=d, descripcion='Bloqueo en la vía').exists())

    def test_redireccion_externa_no_permitida(self):
        d = self.despachar()
        self.client.force_login(self.despachador)
        r = self.client.post(reverse('operacion:iniciar', args=[d.pk]), {'siguiente': '//evil.example'})
        self.assertRedirects(r, reverse('operacion:despacho', args=[d.pk]), fetch_redirect_response=False)

    def test_paginas_principales_cargan(self):
        self.despachar(salir_ahora=True)
        self.client.force_login(self.supervisor)
        for nombre in ('tablero', 'mapa', 'despachos', 'nuevo', 'buses', 'conductores', 'rutas', 'exportar'):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.get(reverse(f'operacion:{nombre}')).status_code, 200)
        for url in ('/', '/mapa/', '/estaciones/bazurto/', '/rutas/T101/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class ModoDemoTests(Base):
    @override_settings(SITM_MODO_DEMO=False)
    def test_apagado_no_despacha(self):
        demo.mantener_operacion(forzar=True)
        self.assertFalse(Despacho.objects.exists())

    @override_settings(SITM_MODO_DEMO=True)
    def test_no_cierra_despachos_hechos_por_personas(self):
        d = self.despachar(salir_ahora=True, ahora=timezone.now() - timedelta(hours=3))
        demo.mantener_operacion(forzar=True)
        d.refresh_from_db()
        self.assertEqual(d.estado, Despacho.Estado.EN_RUTA)

    @override_settings(SITM_MODO_DEMO=True)
    def test_encendido_cubre_las_rutas_y_cierra_lo_terminado(self):
        demo.mantener_operacion(forzar=True)
        self.assertTrue(Despacho.objects.filter(estado=Despacho.Estado.EN_RUTA).exists())
        self.assertEqual(set(Despacho.objects.values_list('ruta__codigo', flat=True)),
                         set(Ruta.objects.values_list('codigo', flat=True)))
        # Tres horas despues todo lo que salio ya debio terminar (la ruta mas larga dura ~2 h).
        demo.mantener_operacion(ahora=timezone.now() + timedelta(hours=3), forzar=True)
        self.assertTrue(Despacho.objects.filter(estado=Despacho.Estado.FINALIZADO).exists())


class SeguridadTests(Base):
    def test_cabeceras_de_seguridad(self):
        r = self.client.get('/')
        csp = r.headers['Content-Security-Policy']
        self.assertIn("script-src 'self' https://cdnjs.cloudflare.com", csp)
        self.assertNotIn("'unsafe-inline'", csp.split('script-src')[1].split(';')[0])
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(r.headers['X-Frame-Options'], 'DENY')

    def test_las_plantillas_no_tienen_scripts_en_linea(self):
        self.client.force_login(self.supervisor)
        for url in ('/', '/estaciones/bazurto/', reverse('cuentas:ingresar'), reverse('operacion:tablero')):
            html = self.client.get(url).content.decode()
            with self.subTest(url=url):
                self.assertNotRegex(html, r'<script>(?!\s*</script>)')
                self.assertNotRegex(html, r'\son(click|change|submit|load)=')

    def test_login_se_bloquea_tras_varios_intentos_fallidos(self):
        url = reverse('cuentas:ingresar')
        for _ in range(5):
            self.client.post(url, {'username': 'desp', 'password': 'mala'})
        # Incluso con la contrasena correcta, la cuenta queda bloqueada un rato.
        r = self.client.post(url, {'username': 'desp', 'password': 'x'})
        self.assertContains(r, 'Demasiados intentos fallidos')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_exitoso_no_revela_si_el_usuario_existe(self):
        url = reverse('cuentas:ingresar')
        a = self.client.post(url, {'username': 'no-existe', 'password': 'x'}).content.decode()
        b = self.client.post(url, {'username': 'desp', 'password': 'mala'}).content.decode()
        self.assertIn('Usuario o contraseña incorrectos', a)
        self.assertIn('Usuario o contraseña incorrectos', b)

    def test_gps_limita_reportes_seguidos_y_tokens_invalidos(self):
        auth = {'HTTP_AUTHORIZATION': f'Bearer {self.padron.token_gps}'}
        datos = {'lat': 10.41, 'lng': -75.53}
        self.assertEqual(self.client.post(reverse('api:gps'), datos, content_type='application/json', **auth).status_code, 201)
        self.assertEqual(self.client.post(reverse('api:gps'), datos, content_type='application/json', **auth).status_code, 429)
        for _ in range(30):
            self.client.post(reverse('api:gps'), datos, content_type='application/json', HTTP_AUTHORIZATION='Bearer falso')
        r = self.client.post(reverse('api:gps'), datos, content_type='application/json', HTTP_AUTHORIZATION='Bearer falso')
        self.assertEqual(r.status_code, 429)

    def test_la_api_publica_no_expone_tokens(self):
        self.despachar(salir_ahora=True)
        cuerpo = self.client.get(reverse('api:flota')).content.decode() + self.client.get(reverse('api:red')).content.decode()
        self.assertNotIn(self.padron.token_gps, cuerpo)
