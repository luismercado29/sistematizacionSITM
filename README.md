# SITM Cartagena · Despacho y seguimiento de buses

Sistema web para **despachar los buses** de un sistema integrado de transporte masivo y llevar
toda la operación sin papel, con un **portal para el pasajero** que muestra en tiempo real por
dónde va cada bus y cuánto tarda en llegar a su estación.

## Qué hace

**Centro de despacho** (`/operacion/`, requiere cuenta)
- Tablero con indicadores del día: buses en ruta, disponibilidad de flota, puntualidad de salida,
  licencias por vencer.
- Cumplimiento de **frecuencia por ruta**: cuándo salió el último bus y si toca o está atrasada la siguiente salida.
- **Despacho** de buses ("sale ahora" o programado) con validaciones de negocio: bus disponible,
  conductor activo con licencia vigente, licencia C3 para articulados, un solo despacho activo por
  bus y por conductor (garantizado también en la base de datos).
- Detalle de cada despacho con itinerario parada a parada, mapa en vivo y **bitácora** inmutable
  (creación, salida, llegada, novedades, incidentes, cancelaciones con motivo).
- Mapa en vivo de toda la flota, gestión de flota, conductores y parámetros de ruta.
- Exportación de despachos a CSV (compatible con Excel).

**Portal del pasajero** (público, sin datos personales)
- Tablero de llegadas por estación con tiempo estimado, actualizado automáticamente.
- Página por ruta con el próximo bus en cada parada y mapa en vivo.

## Cómo se calcula la posición

Cada bus en ruta tiene una de dos fuentes (`apps/despacho/seguimiento.py`):

| Fuente | Cuándo | Cómo |
|---|---|---|
| `gps` | El equipo a bordo reportó hace menos de 2 min | Se proyecta el punto sobre el trazado de la ruta |
| `estimada` | No hay reporte reciente | Tiempo desde la salida × velocidad comercial de la ruta, sobre el recorrido real |

Con los kilómetros recorridos se obtienen la próxima parada y el tiempo a cualquier estación posterior.
La interfaz siempre indica cuál de las dos fuentes se está usando. En los recorridos circulares
(ida y vuelta por la misma vía) el GPS se asigna al sentido que corresponde según el horario.

Entre una consulta y otra el navegador sigue moviendo cada bus sobre su recorrido a la velocidad de
la ruta, así el mapa se ve continuo sin consultar al servidor cada segundo.

## Estructura

```
config/            settings, urls (públicas, /operacion, /api/v1)
apps/core/         roles, iconos, utilidades geográficas, comando cargar_demo
apps/red/          estaciones, rutas y paradas
apps/flota/        buses y conductores
apps/despacho/     despachos, bitácora, GPS, reglas (servicios.py), seguimiento, modo demo
apps/publico/      portal del pasajero y API JSON
templates/         base, componentes, operacion, publico
static/sitm/       sistema de diseño (css) y scripts (mapa en vivo, llegadas)
myapp/             tablas del prototipo anterior, conservadas solo por sus datos
```

Las reglas de negocio viven en `apps/despacho/servicios.py`: vistas, admin y comandos pasan por ahí.

## Roles

Las cuentas se crean en `/admin/` (no hay registro público).

- **Despachadores**: despachan, dan salida, cierran, cancelan y registran novedades.
- **Supervisores**: además editan flota, conductores y parámetros de ruta.
- **Superusuarios**: todo, incluido `/admin/`.

## Puesta en marcha local

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate en Linux/Mac)
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py cargar_demo --usuarios   # red, flota y cuentas de prueba (imprime las contraseñas)
python manage.py createsuperuser
python manage.py runserver
```

Para ver buses moviéndose sin operar a mano, activa `SITM_MODO_DEMO=true` en `.env`:
el sistema despacha y cierra recorridos solo. **Nunca lo actives en una operación real.**

### Datos de la red

La red real de Cartagena (24 rutas: troncales, expresa, pretroncales, alimentadoras y complementarias,
con su recorrido por la vía y sus estaciones) está en `apps/red/datos/red_cartagena.json`. Se genera
desde OpenStreetMap con:

```bash
python manage.py importar_red_osm
```

El archivo se guarda en el repositorio, así que `cargar_demo` y el despliegue no necesitan internet.
Los horarios provienen de la guía pública de rutas del sistema. La flota, los conductores y las
frecuencias de la demo son ficticios. Datos de recorridos © colaboradores de OpenStreetMap (ODbL).

## Pruebas

```bash
python manage.py test apps
```

Cubren las reglas de despacho, el cálculo de posiciones y llegadas, la API, los permisos y el modo demo.

## API v1

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/v1/red/` | Rutas activas con sus paradas |
| GET | `/api/v1/flota/?ruta=T101` | Buses en ruta con posición y fuente |
| GET | `/api/v1/estaciones/<codigo>/llegadas/` | Próximas llegadas a una estación |
| GET | `/api/v1/rutas/<codigo>/en-vivo/` | Buses de la ruta y próximo bus por parada |
| POST | `/api/v1/gps/` | Reporte del equipo a bordo |

Reporte GPS (el token de cada bus se ve en `/admin/` → Buses):

```bash
curl -X POST https://<dominio>/api/v1/gps/ \
  -H "Authorization: Bearer <token del bus>" -H "Content-Type: application/json" \
  -d '{"lat": 10.4128, "lng": -75.5310, "velocidad": 28.5}'
```

## Despliegue (Vercel + Neon)

1. Variables en Vercel: `SECRET_KEY`, `DATABASE_URL` (Neon), `DEBUG=false`, `MAPBOX_TOKEN` y, para la demo pública, `SITM_MODO_DEMO=true`.
2. Las migraciones se corren desde tu equipo contra Neon:
   `DATABASE_URL=<cadena de Neon> python manage.py migrate` y luego `cargar_demo`.
3. Vercel no admite WebSockets en funciones serverless, por eso las pantallas en vivo consultan la API
   cada `SITM_REFRESCO_S` segundos (10 por defecto).

## Seguridad

- **Secretos fuera del código**: `SECRET_KEY`, `DATABASE_URL`, `MAPBOX_TOKEN` y `ADMIN_URL` se leen
  del entorno (`.env` en local, variables en Vercel). `.env` y `db.sqlite3` están en `.gitignore`.
- **Producción** (`DEBUG=false`): HTTPS obligatorio, HSTS, cookies `Secure`/`HttpOnly`, sesión de
  12 h y `python manage.py check --deploy` sin observaciones.
- **Content-Security-Policy** sin scripts en línea: solo se ejecutan archivos propios y Leaflet
  desde cdnjs con integridad (SRI). Además `X-Frame-Options: DENY`, `Permissions-Policy` y COOP.
- **Login**: bloqueo temporal tras 5 intentos fallidos por usuario (20 por IP) y el mismo mensaje
  exista o no la cuenta. No hay registro público; las cuentas las crea un administrador.
- **Permisos por rol** en cada vista y CSRF en todos los formularios; redirecciones solo internas.
- **API pública** sin datos personales ni tokens. El endpoint GPS exige el token de cada bus,
  limita a un reporte por segundo y bloquea IPs con muchos tokens inválidos.
- **Mapbox**: el token es público (`pk.`) por diseño; restríngelo a tus dominios en su panel.
- Los límites de intentos usan la caché de Django; en serverless cada instancia lleva su cuenta.
  Para un límite global configura una caché compartida (Redis) en `CACHES`.

## Próximos pasos sugeridos

- Importar la red oficial desde GTFS (trazados reales en lugar de tramos entre paradas).
- App ligera para el conductor que envíe el GPS desde el celular.
- Reportes históricos de puntualidad y kilómetros por bus.
