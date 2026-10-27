# Manual de Despliegue — SIIED BI (Apache Superset)

Guía operativa del servidor Superset que alimenta **SIIED BI** y **Don Datico BI**.
Instalación actual: venv pip en `/opt/superset` (Apache Superset **6.1.0**),
metadata en PostgreSQL, ejecución vía `superset run`.

---

## 1. Estructura de la instalación

| Ruta | Contenido |
|---|---|
| `/opt/superset/venv/` | Virtualenv con `apache-superset==6.1.0` |
| `/opt/superset/config/superset_config.py` | **Toda la configuración** (DB, CORS, features, branding, guest tokens) |
| `/opt/superset/config/assets/` | Assets de marca versionables (logos, favicon, `head_custom_extra.html`) |
| `/opt/superset/config/apply_rebrand.sh` | Script que re-instala assets de marca en site-packages |
| `/opt/superset/uploads/` | CSV/XLSX subidos por usuarios |
| `/opt/superset/results/` | Backend de resultados de SQL Lab (FileSystemCache) |
| `/opt/superset/superset.log` | Log del proceso |
| Paquete instalado | `venv/lib/python3.12/site-packages/superset/` — **se pisa al actualizar** |

Variables de entorno requeridas por el proceso:

```bash
SUPERSET_CONFIG_PATH=/opt/superset/config/superset_config.py
FLASK_APP=superset
VIRTUAL_ENV=/opt/superset/venv          # vía activation
```

## 2. Instalación desde cero

```bash
# Requisitos del sistema (Ubuntu/Debian)
sudo apt install python3.12 python3.12-venv build-essential libpq-dev

# Virtualenv + instalación
mkdir -p /opt/superset/{config/assets,uploads,results}
python3.12 -m venv /opt/superset/venv
/opt/superset/venv/bin/pip install apache-superset psycopg2-binary pillow

# Base de datos de metadata (PostgreSQL)
sudo -u postgres createdb superset
sudo -u postgres createuser $USER --superuser   # o el rol que prefieras

# Config: copiar superset_config.py a /opt/superset/config/ y ajustar
# SECRET_KEY, SQLALCHEMY_DATABASE_URI y credenciales.

# Inicialización
export SUPERSET_CONFIG_PATH=/opt/superset/config/superset_config.py
export FLASK_APP=superset
source /opt/superset/venv/bin/activate
superset db upgrade
superset fab create-admin \
    --username admin --firstname Admin --lastname SIIED \
    --email admin@cali.gov.co --password 'CAMBIAR'
superset init
```

## 3. Ejecución

```bash
source /opt/superset/venv/bin/activate
export SUPERSET_CONFIG_PATH=/opt/superset/config/superset_config.py
export FLASK_APP=superset
cd /opt/superset

# Desarrollo (estado actual)
superset run -p 8088 --with-threads --reload --debugger --host=0.0.0.0

# Producción (gunicorn, detrás de proxy)
gunicorn -w 4 -k gevent --timeout 120 -b 127.0.0.1:8088 \
    "superset.app:create_app()" >> /opt/superset/superset.log 2>&1 &
```

> **Nota `--reload`:** werkzeug vigila `.py` importados, pero `superset_config.py`
> se carga con `from_pyfile` (no es un módulo en `sys.modules`) → **los cambios
> de config NO recargan solos**. Truco: `touch venv/.../superset/__init__.py`
> fuerza el reinicio del worker; en producción reiniciar el servicio.

## 4. Rebranding — SIIED BI

Capa 1 (config, `superset_config.py`):

```python
APP_NAME = 'SIIED BI'
APP_ICON = '/static/assets/images/siied-bi-logo.png'
LOGO_TOOLTIP = 'SIIED BI — Tableros del Sistema Integrado...'
LOGO_RIGHT_TEXT = 'SIIED BI'
FAVICONS = [{'href': '/static/assets/images/siied-bi-favicon.png'}]

THEME_DEFAULT = {'token': {  # Ant Design — colores marca
    'brandAppName': 'SIIED BI', 'brandLogoAlt': 'SIIED BI',
    'brandLogoUrl': APP_ICON, 'brandLogoHeight': '38px',
    'colorPrimary': '#0369a1', 'colorLink': '#0284c7', ...
}, 'algorithm': 'default'}
THEME_DARK = {'token': {...hereda _SIIED_TOKEN...}, 'algorithm': 'dark'}
```

Capa 2 (assets → site-packages, **no persisten upgrades**):

```bash
bash /opt/superset/config/apply_rebrand.sh
```

Copia a `site-packages/superset/`:

- `static/assets/images/siied-bi-logo.png` — logo navbar/login
- `static/assets/images/siied-bi-favicon.png` — favicon 64×64
- `static/assets/images/siied-logo.png` — logo completo (uso futuro)
- `templates/head_custom_extra.html` — **hook oficial de override**:
  se incluye en todas las vistas (ver `templates/superset/spa.html`);
  contiene el CSS de marca (navbar degradado azul SIIED, login redondeado,
  botones primarios sky-600, oculta versión en footer).

> **Tras `pip install -U apache-superset`: ejecutar `apply_rebrand.sh` y
> reiniciar. La config vive fuera de site-packages y sobrevive el upgrade.**

Fuentes de los logos: `indicadores/static/indicadores/images/logo_siied_bi.png`
y `siied-logo.png` (repo SIIED → `/opt/superset/config/assets/`).

## 5. Seguridad — modelo de acceso SIIED ↔ Superset

### 5.1 Cuentas de consumo (guest tokens)

Dashboards embebidos en el SIIED (`indicadores:bi_tablero`, `/bi/<id>/`):
el usuario del SIIED **no necesita cuenta en Superset**. Django pide
`POST /api/v1/security/guest_token/` y Superset firma el token con el rol
`GUEST_ROLE_NAME`.

```python
FEATURE_FLAGS = {'EMBEDDED_SUPERSET': True, 'DASHBOARD_RBAC': True, ...}
GUEST_ROLE_NAME = 'Gamma'          # solo lectura dashboards+fuentes
GUEST_TOKEN_JWT_SECRET = '<64+ chars aleatorios>'   # ¡distinto de SECRET_KEY!
GUEST_TOKEN_JWT_EXP_SECONDS = 300
PUBLIC_ROLE_LIKE = None            # anónimo sin token no hereda nada
```

- RLS por tablero: `TableroBI.rls_clause` viaja en el payload del guest token.
- El dashboard debe estar marcado **Embedded → Allowed domains** (o por API
  `/api/v1/dashboard/{id}/embedded`).

### 5.2 Cuentas de construcción (natives)

Quienes **construyen** en BI sí tienen cuenta Superset, creada/desactivada
automáticamente desde el admin del SIIED (`PerfilRecolector.save_model`):

| Rol SIIED | Rol Superset | Capacidad |
|---|---|---|
| `analista` | `Alpha` | explorar, crear charts/dashboards sobre fuentes permitidas |
| `analista_organismo` | `Gamma` | consumo BI (SIIED BI / Don Datico BI) vía vistas Django |
| cualquier otro / `activo=False` | — | `desactivar_usuario()` → `active=False` vía API |

- `admin`: cuenta de servicio usada por `SupersetService` para todas las
  acciones de backend (datasets, dashboards, usuarios, guest tokens).
- `SUPERSET_SHARED_PASSWORD` (env): password compartido de cuentas nativas —
  el usuario nunca entra a Superset directo; todo el trabajo es vía API/SDK.

### 5.3 Visibilidad de datasets y tableros (modelos `DatasetBI`/`TableroBI`)

- `DatasetBI.visibilidad`: `propio` | `interno` (equipo SIIED) | `publico`.
  `es_base_siied=True` marca los datasets del catálogo SIIED.
- `TableroBI.visibilidad`: `publico` | `autenticado` | `organismo` | `interno`;
  `url_publica()` = `/bi/<dashboard_id>/` (guest token por política).

## 6. Proxy reverso y embedding

```python
ENABLE_PROXY_FIX = True          # ya configurado
PROXY_FIX_CONFIG = {x_for/x_proto/x_host/x_prefix/x_port: 1}
HTTP_HEADERS = {'X-Frame-Options': 'ALLOWALL'}
TALISMAN_ENABLED = False         # si se activa, definir CSP completa para iframe
CORS_OPTIONS['origins'] += ['https://indicadores.cali.gov.co']
```

Apache (producción) debe reenviar `X-Forwarded-Proto`/`Host`/`Prefix` para que
`SUPERSET_PUBLIC_URL` (env, usado por Django) resuelva bien los iframes.

## 7. Mantenimiento

| Tarea | Comando / nota |
|---|---|
| Upgrade Superset | `pip install -U apache-superset` → `superset db upgrade` → `bash config/apply_rebrand.sh` → reiniciar |
| Backup metadata | `pg_dump superset > backup.sql` (dashboards, datasets, usuarios, roles) |
| Limpiar results | `rm -rf /opt/superset/results/*` (cache de SQL Lab) |
| Rotar guest secret | cambiar `GUEST_TOKEN_JWT_SECRET` → invalida tokens emitidos (máx 5 min) |
| Crear rol embed propio | UI: *Settings → Roles → +*, permisos `can read` sobre Dashboard/Datasource/Chart + `menu access` mínimo; luego `GUEST_ROLE_NAME = 'SIIED-Embed'` |
| Revisar usuarios huérfanos | admin SIIED desactiva en Superset automáticamente; manual: API `PUT /api/v1/security/users/{id}` `{"active": false}` |

## 8. Verificación rápida post-despliegue

```bash
curl -s http://localhost:8088/health                        # "OK"
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8088/static/assets/images/siied-bi-logo.png   # 200
curl -s http://localhost:8088/login/ | grep -c 'SIIED BI'   # >0 = branding activo
# En Django:
python manage.py check
# Login SIIED como analista_organismo → /analitica/superset/ lista solo datasets visibles
```

## 9. Mapas coropléticos con capas geográficas SIIED

Las geometrías (comunas, corregimientos, etc.) viven en `ElementoGeo.geom_wkt`
(WKT texto). Superset no puede subir archivos GeoJSON — los datasets vienen de
tablas/vistas de BD — así que se materializa una tabla puente:

```bash
python manage.py export_geojson_superset            # todas las capas
python manage.py export_geojson_superset --capa-id 7 --dry-run
```

Genera `indicadores_capageojson` (`capa_geo_id, codigo, nombre, geojson`),
idempotente por `(capa_geo, codigo)`. Re-correr tras recargar geometrías.

**En Superset** (la conexión `SIIED - Indicadores` debe apuntar a la BD de
Django para que vea la tabla):

1. Subir el Excel de la dependencia como dataset físico.
2. Crear **dataset virtual** (SQL Lab → guardar como dataset) uniendo métricas
   con geometría:

   ```sql
   SELECT d.*, g.geojson
   FROM <tabla_excel> d
   JOIN indicadores_capageojson g
     ON lpad(d.codigo_comuna::text, 2, '0') = lpad(g.codigo, 2, '0')
   WHERE g.capa_geo_id IN (SELECT id FROM indicadores_capageo
                           WHERE nombre LIKE 'Comuna %')
   ```

   Si el Excel trae nombre de comuna en vez de código, el join es
   `UPPER(g.nombre) = UPPER(d.comuna)` — normalizar tildes/mayúsculas antes.
3. Crear gráfico **deck.gl Polygon**: columna geojson = `geojson`, métrica =
   `sum(valor)`, tooltip = nombre + valor. Esa es la coropleta.
4. Armar el dashboard → embeber en SIIED vía guest token (sección 5).

> Nota: `wkt_to_geojson` aplica una aproximación lineal UTM→WGS84 para Cali
> (la misma que usan los mapas del portal). Si se requiere precisión
> cartográfica en Superset, habilitar PostGIS y usar `ST_AsGeoJSON`.

---

*Última actualización: rebranding + modelo de acceso seguro (guest tokens,
subrol `analista_organismo`, DatasetBI/TableroBI).*
