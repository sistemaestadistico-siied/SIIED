"""
Servicio de integración con Apache Superset API REST.
Maneja autenticación, consulta de dashboards, subida de CSV y gestión de datasets.
"""
import logging
import os
import re
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Identificador de tabla válido para DROP TABLE (defensa en profundidad:
# el caller ya filtra por es_base_siied, pero el nombre viaja a SQL).
_RE_TABLA = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]{0,62}$')


class SupersetService:
    """Cliente para la API REST de Apache Superset"""

    def __init__(self):
        self.base_url = getattr(settings, 'SUPERSET_BASE_URL', 'http://127.0.0.1:8088')
        self.public_url = getattr(settings, 'SUPERSET_PUBLIC_URL', '/superset')
        self.admin_username = getattr(settings, 'SUPERSET_ADMIN_USERNAME', 'admin')
        self.admin_password = getattr(settings, 'SUPERSET_ADMIN_PASSWORD', '')
        self._access_token = None
        self._csrf_token = None
        self._session = requests.Session()

    # ========================================================================
    # AUTENTICACIÓN
    # ========================================================================

    def _authenticate(self):
        """Obtiene token de acceso via Superset Security API"""
        try:
            url = f"{self.base_url}/api/v1/security/login"
            payload = {
                "username": self.admin_username,
                "password": self.admin_password,
                "provider": "db",
                "refresh": True,
            }
            resp = self._session.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get('access_token')
            logger.info("Superset: autenticación exitosa")
            return True
        except requests.RequestException as e:
            logger.error(f"Superset: error de autenticación: {e}")
            self._access_token = None
            return False

    def _get_headers(self):
        """Retorna headers con token de autenticación"""
        if not self._access_token:
            if not self._authenticate():
                return None
        return {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/json',
        }

    def _get_csrf_token(self):
        """Obtiene CSRF token para operaciones de escritura.

        Si el JWT expiró, el csrf_token GET responde 401: re-login y un
        solo reintento (mismo patrón que _api_request)."""
        url = f"{self.base_url}/api/v1/security/csrf_token/"
        try:
            for intento in range(2):
                headers = self._get_headers()
                if not headers:
                    return None
                resp = self._session.get(
                    url, headers=headers, timeout=10)
                if resp.status_code == 401 and intento == 0:
                    self._access_token = None
                    continue
                resp.raise_for_status()
                self._csrf_token = resp.json().get('result')
                return self._csrf_token
            return None
        except requests.RequestException as e:
            logger.error(f"Superset: error obteniendo CSRF token: {e}")
            return None

    def _api_request(self, method, endpoint, **kwargs):
        """Wrapper para requests con retry de autenticación"""
        headers = self._get_headers()
        if not headers:
            return None

        url = f"{self.base_url}/api/v1/{endpoint}"

        try:
            resp = self._session.request(method, url, headers=headers, timeout=30, **kwargs)

            # Si 401, re-autenticar y reintentar una vez
            if resp.status_code == 401:
                self._access_token = None
                headers = self._get_headers()
                if not headers:
                    return None
                resp = self._session.request(method, url, headers=headers, timeout=30, **kwargs)

            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Superset API [{method} {endpoint}]: {e}")
            return None

    # ========================================================================
    # DASHBOARDS
    # ========================================================================

    def listar_dashboards(self):
        """Retorna lista de dashboards con metadata básica"""
        data = self._api_request(
            'GET', 'dashboard/',
            params={
                'q': '(page_size:100,order_column:changed_on_delta_humanized,order_direction:desc)',
            }
        )
        if data is None:
            # Fallo de API (red/401): NO es lo mismo que "sin dashboards".
            # Devolver [] aquí haría que la reconciliación desactivara
            # todos los registros BI por un fallo transitorio.
            return None

        dashboards = []
        for d in data.get('result', []):
            dashboards.append({
                'id': d.get('id'),
                'title': d.get('dashboard_title', ''),
                'slug': d.get('slug', ''),
                'url': d.get('url', ''),
                'status': d.get('status', 'draft'),
                'published': d.get('published', False),
                'changed_on': d.get('changed_on_delta_humanized', ''),
                'changed_by_name': (d.get('changed_by') or {}).get('first_name', ''),
                'owners': [
                    o.get('first_name', '') + ' ' + o.get('last_name', '')
                    for o in (d.get('owners') or [])
                ],
                # THUMBNAILS deshabilitado → la URL siempre 404; el template
                # muestra el placeholder cuando la clave está ausente/vacía.
                'thumbnail_url': '',
            })

        return dashboards

    def obtener_dashboard(self, dashboard_id):
        """Retorna detalle completo de un dashboard"""
        data = self._api_request('GET', f'dashboard/{dashboard_id}')
        if not data:
            return None
        result = data.get('result', {})
        return {
            'id': result.get('id'),
            'title': result.get('dashboard_title', ''),
            'slug': result.get('slug', ''),
            'url': result.get('url', ''),
            'published': result.get('published', False),
            'changed_on': result.get('changed_on_delta_humanized', ''),
            'owners': [
                o.get('first_name', '') + ' ' + o.get('last_name', '')
                for o in (result.get('owners') or [])
            ],
            'json_metadata': result.get('json_metadata', ''),
        }

    def obtener_url_publica_dashboard(self, dashboard_id):
        """Genera la URL pública para un dashboard embebido o accesible"""
        dashboard = self.obtener_dashboard(dashboard_id)
        if not dashboard:
            return None

        slug = dashboard.get('slug')
        if slug:
            return f"{self.public_url}/superset/dashboard/{slug}/"
        return f"{self.public_url}/superset/dashboard/{dashboard_id}/"

    def obtener_embed_id(self, dashboard_id):
        """Obtiene el UUID para embeber un dashboard vía iframe (requiere EMBEDDED_SUPERSET=True)"""
        data = self._api_request('GET', f'dashboard/{dashboard_id}/embedded')
        if not data:
            return None
        result = data.get('result', {})
        return result.get('uuid')

    def get_or_create_embed_id(self, dashboard_id):
        """Retorna el embedded UUID del dashboard, activando el embed si falta.

        PUT dashboard/{id}/embedded hace upsert de la configuración de
        embedding (allowed_domains vacío = sin restricción de dominio).
        """
        uuid = self.obtener_embed_id(dashboard_id)
        if uuid:
            return uuid
        data = self._write_request(
            'PUT', f'dashboard/{dashboard_id}/embedded',
            {'allowed_domains': []})
        if not data or '_error' in data:
            return None
        return self.obtener_embed_id(dashboard_id)

    def get_guest_token(self, resource_id, username,
                        first_name='', last_name='', rls=None):
        """Genera un guest token para embeber un recurso (dashboard).

        El token lo consume @superset-ui/embedded-sdk en el navegador;
        expira según GUEST_TOKEN_JWT_EXP_SECONDS de Superset.

        `rls`: lista de cláusulas de row-level security para Superset,
        p.ej. [{'clause': "organismo_id = 5"}]. Vacío = sin filtro.
        """
        payload = {
            'resources': [{'type': 'dashboard', 'id': str(resource_id)}],
            'rls': list(rls or []),
            'user': {
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
            },
        }
        data = self._write_request('POST', 'security/guest_token/', payload)
        if not data or '_error' in data:
            return None
        result = data.get('result')
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return result.get('token')
        return data.get('token')

    # ========================================================================
    # DATASETS / CSV UPLOAD
    # ========================================================================

    def listar_datasets(self):
        """Retorna lista de datasets disponibles"""
        data = self._api_request(
            'GET', 'dataset/',
            params={
                'q': '(page_size:100,order_column:changed_on_delta_humanized,order_direction:desc)',
            }
        )
        if data is None:
            # Fallo de API: [] haría reconciliar (desactivar) en falso.
            return None

        datasets = []
        for d in data.get('result', []):
            datasets.append({
                'id': d.get('id'),
                'table_name': d.get('table_name', ''),
                'kind': d.get('kind', ''),
                'schema': d.get('schema', ''),
                'database_name': (d.get('database') or {}).get('database_name', ''),
                'changed_on': d.get('changed_on_delta_humanized', ''),
                'owners': [o.get('username') or ''
                           for o in (d.get('owners') or [])],
            })
        return datasets

    def crear_dataset_virtual(self, nombre_tabla, sql, database_id=None,
                              schema='public'):
        """Registra un dataset virtual (query SQL) en Superset.

        Args:
            nombre_tabla: Nombre del dataset en Superset
            sql: Consulta SQL que define el dataset
            database_id: ID de la base de datos (si None, busca la del SIIED)
            schema: Esquema de la base de datos
        """
        if not database_id:
            database_id = self._get_siied_database_id()
            if not database_id:
                return {'error': 'No se encontró la base de datos SIIED en Superset'}

        csrf_token = self._get_csrf_token()
        headers = self._get_headers()
        if not headers or not csrf_token:
            return {'error': 'Error de autenticación con Superset'}
        headers['X-CSRFToken'] = csrf_token
        headers['Referer'] = self.base_url

        try:
            resp = self._session.post(
                f"{self.base_url}/api/v1/dataset/",
                headers=headers,
                json={
                    'database': database_id,
                    'table_name': nombre_tabla,
                    'schema': schema,
                    'sql': sql,
                },
                timeout=60,
            )
            if resp.status_code in (200, 201):
                logger.info(
                    f"Superset: dataset virtual '{nombre_tabla}' creado")
                return {'success': True, 'table_name': nombre_tabla,
                        'id': resp.json().get('id')}
            if resp.status_code == 422 or 'already exists' in resp.text.lower():
                return {'exists': True, 'table_name': nombre_tabla}
            logger.error(
                f"Superset: error creando dataset '{nombre_tabla}': "
                f"{resp.status_code} {resp.text[:300]}")
            return {'error': f'Error {resp.status_code}: {resp.text[:300]}'}
        except requests.RequestException as e:
            logger.error(f"Superset: error creando dataset virtual: {e}")
            return {'error': str(e)}

    def _habilitar_file_upload(self, database_id):
        """Activa 'Allow file uploads' en la conexión destino (best-effort).

        Sin ese flag, POST /database/{id}/upload/ responde 500 con página
        HTML — el error más común al subir CSV a Superset."""
        try:
            info = self._api_request('GET', f'database/{database_id}')
            result = (info or {}).get('result') or {}
            if result.get('allow_file_upload'):
                return True
            reg = self._write_request(
                'PUT', f'database/{database_id}',
                {'allow_file_upload': True})
            if not reg or '_error' in reg:
                logger.warning(
                    f"Superset: no se pudo activar allow_file_upload en "
                    f"database {database_id}")
                return False
            return True
        except Exception as e:
            logger.warning(
                f"Superset: error verificando allow_file_upload: {e}")
            return False

    def subir_csv(self, archivo, nombre_tabla, database_id=None, tipo=None):
        """
        Sube un archivo CSV/TSV/Excel como nuevo dataset en Superset.

        Args:
            archivo: File-like object (ej: request.FILES['archivo'])
            nombre_tabla: Nombre que tendrá la tabla en Superset
            database_id: ID de la base de datos destino (si None, busca la del SIIED)
            tipo: 'csv' | 'excel' (si None, se infiere por la extensión)
        """
        if not database_id:
            database_id = self._get_siied_database_id()
            if not database_id:
                return {'error': 'No se encontró la base de datos SIIED en Superset'}

        self._habilitar_file_upload(database_id)

        csrf_token = self._get_csrf_token()
        headers = self._get_headers()
        if not headers or not csrf_token:
            return {'error': 'Error de autenticación con Superset'}

        # Para upload de archivo, cambiar Content-Type
        headers.pop('Content-Type', None)
        headers['X-CSRFToken'] = csrf_token
        headers['Referer'] = self.base_url

        if tipo is None:
            ext = os.path.splitext(getattr(archivo, 'name', ''))[1].lower()
            tipo = 'excel' if ext in ('.xls', '.xlsx') else 'csv'

        # API moderna (Superset >= 2.x): POST /api/v1/database/{id}/upload/
        url = f"{self.base_url}/api/v1/database/{database_id}/upload/"

        try:
            mime = ('application/vnd.openxmlformats-officedocument'
                    '.spreadsheetml.sheet' if tipo == 'excel' else 'text/csv')
            files = {
                'file': (archivo.name, archivo, mime),
            }
            form_data = {
                'type': tipo,
                'table_name': nombre_tabla,
                'already_exists': 'replace',
                'schema': 'public',
            }
            if tipo == 'csv':
                ext = os.path.splitext(
                    getattr(archivo, 'name', ''))[1].lower()
                form_data['delimiter'] = '\t' if ext == '.tsv' else ','
            # Excel: NO enviar sheet_name. '0' llega como string a
            # pd.read_excel y pandas busca una hoja literalmente llamada
            # "0" -> DatabaseUploadFailed "Worksheet named '0' not found".
            # Sin el parámetro, pandas lee la primera hoja por defecto.
            resp = self._session.post(
                url,
                headers=headers,
                files=files,
                data=form_data,
                timeout=120,
            )

            if resp.status_code in (200, 201, 302):
                logger.info(f"Superset: CSV '{nombre_tabla}' subido exitosamente")
                return {'success': True, 'table_name': nombre_tabla}
            else:
                error_msg = resp.text[:500]
                if '<html' in resp.text.lower():
                    error_msg = (
                        'Superset respondió una página de error interna '
                        f'({resp.status_code}) en vez de JSON. Causas '
                        'frecuentes: "Allow file uploads" deshabilitado '
                        'en la conexión, el esquema "public" no existe '
                        'o el CSV es inválido.')
                logger.error(f"Superset: error subiendo CSV: {resp.status_code} {error_msg}")
                return {'error': f'Error {resp.status_code}: {error_msg}'}

        except requests.RequestException as e:
            logger.error(f"Superset: error subiendo CSV: {e}")
            return {'error': str(e)}

    def _get_gsheets_database_id(self):
        """ID de la database gsheets:// registrada en Superset (o None).

        El engine gsheets lo provee shillelagh; solo existe si alguien
        agregó la conexión (Data → Databases → + gsheets://)."""
        data = self._api_request('GET', 'database/')
        for db in (data or {}).get('result', []):
            uri = (db.get('sqlalchemy_uri') or '')
            nombre = (db.get('database_name') or '').lower()
            # El listado no siempre expone engine/sqlalchemy_uri — de
            # ahí el fallback por nombre (la auto-provisión la registra
            # como 'Google Sheets').
            if (db.get('engine') == 'gsheets'
                    or uri.startswith('gsheets')
                    or nombre.replace(' ', '') in (
                        'googlesheets', 'gsheets')):
                return db.get('id')
        # El listado viene paginado (~25): si hay muchas conexiones la
        # gsheets puede quedar fuera. Consulta filtrada por nombre —
        # no depende de la página ni de columnas del listado completo.
        for nombre_db in ('Google Sheets', 'gsheets', 'google sheets'):
            data = self._api_request(
                'GET', 'database/',
                params={'q': "(filters:!((col:database_name,opr:eq,"
                             f"value:'{nombre_db}')))"})
            for db in (data or {}).get('result', []):
                if db.get('id'):
                    return db['id']
        return None

    def crear_dataset_gsheet(self, url_sheet, owner_usuario=None):
        """Crea un dataset Superset sobre una hoja de Google (shillelagh).

        El table_name del dataset ES la URL completa — así el engine
        resuelve también la pestaña (#gid=N) incluida en el enlace.
        La hoja debe ser pública ("cualquiera con el enlace") salvo que
        la conexión gsheets tenga service account.

        `owner_usuario`: username Superset que queda como owner — sin
        él un usuario Gamma no tendría datasource_access y sus charts
        fallarían con "This endpoint requires the datasource …"."""
        # Normalizar a '.../spreadsheets/d/<id>' + '#gid=N': los params
        # de /edit?usp=...&authuser=... no aportan y ensucian el dataset.
        m = re.match(
            r'^(https://docs\.google\.com/spreadsheets/d/[\w-]+)',
            url_sheet or '')
        if not m:
            return {'error': 'URL de Google Sheet inválida'}
        # Conservar el fragmento #gid=N (pestaña) del enlace original.
        url_sheet = m.group(1)
        if '#' in m.string:
            url_sheet += '#' + m.string.split('#', 1)[1]

        db_id = self._get_gsheets_database_id()
        if not db_id:
            # Auto-provisión: registrar la conexión gsheets:// (shillelagh)
            # en vez de exigir el paso manual en Superset.
            reg = self.crear_database('Google Sheets', 'gsheets://',
                                    cache_timeout=0)
            if 'error' in reg:
                # Puede existir ya con ese nombre y el listado no
                # reconocerla (engine/URI no expuestos) → rebuscar.
                db_id = self._get_gsheets_database_id()
                if not db_id:
                    return {'error': 'No hay una base gsheets:// '
                                     'registrada en Superset y no se '
                                     'pudo crear automáticamente: '
                                     f'{reg["error"]}'}
            else:
                db_id = reg.get('database_id') or \
                    self._get_gsheets_database_id()
            if not db_id:
                return {'error': 'La base gsheets:// se creó pero no '
                                 'aparece en el listado de Superset'}

        # timeout=120: crear el dataset dispara un probe de shillelagh
        # que descarga la hoja de Google en vivo — si el egress hacia
        # Google es lento o está bloqueado, el default de 60s queda
        # corto y el request muere silencioso (data=None).
        data = self._write_request('POST', 'dataset/', {
            'database': db_id,
            'table_name': url_sheet,
            'owners': self._owner_ids(owner_usuario),
        }, timeout=120)
        if data is None:
            return {'error': 'la API de Superset no respondió '
                             '(timeout/red o auth). Crear el dataset '
                             'descarga la hoja en vivo — verifique '
                             'que el servidor alcance google.com y '
                             'que la hoja sea pública'}
        detalle = data.get('_detalle') or data.get('_error')
        if '_error' in data or not data:
            if not isinstance(detalle, str):
                detalle = str(detalle)[:300]
            return {'error': detalle or 'Superset respondió sin JSON '
                                       'al crear el dataset'}

        ds_id = data.get('id')
        if ds_id is None:
            ds_id = (data.get('result') or {}).get('id')
        logger.info(f"Superset: dataset gsheets '{url_sheet}' creado (id={ds_id})")
        return {'success': True, 'dataset_id': ds_id,
                'table_name': url_sheet}

    # ========================================================================
    # CONEXIONES A BASES DE DATOS EXTERNAS
    # ========================================================================

    def test_conexion_db(self, sqlalchemy_uri):
        """Prueba una URI antes de registrarla (POST test_connection)."""
        data = self._write_request('POST', 'database/test_connection', {
            'database_name': 'prueba-siied',
            'sqlalchemy_uri': sqlalchemy_uri,
        })
        if not data or '_error' in data:
            detalle = ((data or {}).get('_detalle')
                       or (data or {}).get('_error'))
            return {'error': detalle or 'sin respuesta de Superset'}
        return {'success': True}

    def crear_database(self, nombre, sqlalchemy_uri, cache_timeout=None):
        """Registra una conexión de BD externa (POST database/).

        Nunca loguear sqlalchemy_uri — contiene la contraseña.
        cache_timeout=0 desactiva el caché de consultas: indispensable
        en gsheets://, donde el dataset debe reflejar la hoja en vivo."""
        payload = {
            'database_name': nombre,
            'sqlalchemy_uri': sqlalchemy_uri,
            'expose_in_sqllab': False,
        }
        if cache_timeout is not None:
            payload['cache_timeout'] = cache_timeout
        data = self._write_request('POST', 'database/', payload)
        if data is None:
            # Sin respuesta: la auth/CSRF falló antes del request — la
            # cuenta de servicio no puede autenticarse (credenciales
            # rechazadas, cuenta desactivada o rol sin acceso a la API).
            return {'error': 'la cuenta de servicio no pudo autenticarse '
                             'en la API de Superset (login o CSRF '
                             'rechazado) — verifique SUPERSET_ADMIN_'
                             'USERNAME/PASSWORD y que la cuenta esté '
                             'activa con rol Admin'}
        if '_error' in data:
            detalle = data.get('_detalle') or data.get('_error')
            if not isinstance(detalle, str):
                # Superset responde {"message": {...}} o {"errors": [...]}
                detalle = str(detalle)[:300]
            return {'error': detalle or 'error registrando conexión'}
        db_id = data.get('id')
        if db_id is None:
            db_id = (data.get('result') or {}).get('id')
        return {'success': True, 'database_id': db_id}

    def _perm_view_menu_id(self, permission_name, view_menu_name,
                           crear=False):
        """Id del permission_view_menu (permiso + objeto) o None.

        'datasource_access' sobre cada datasource lo crea Superset de
        forma diferida; con `crear` se intenta dar de alta por POST si
        aún no existe (la API lo permite con rol Admin)."""
        def _f(col, val):
            esc = val.replace('!', '!!').replace("'", "!'")
            return f"(col:{col},opr:eq,value:'{esc}')"
        data = self._api_request(
            'GET', 'security/permissions_view_menus/',
            params={'q': '(filters:!('
                    + _f('permission_name', permission_name) + ','
                    + _f('view_menu_name', view_menu_name) + '))'})
        resultados = (data or {}).get('result') or []
        if resultados:
            return resultados[0].get('id')
        if not crear:
            return None
        data = self._write_request(
            'POST', 'security/permissions_view_menus/',
            {'permission_name': permission_name,
             'view_menu_name': view_menu_name})
        if not data or '_error' in data:
            return None
        return data.get('id') or (data.get('result') or {}).get('id')

    def acceso_dataset_rol(self, dataset_id, role_name='Gamma',
                           otorgar=True):
        """Otorga o revoca 'datasource_access' del dataset a un rol.

        `DatasetBI.visibilidad` gobierna el selector del SIIED, pero
        Superset tiene su propio ACL: un Gamma solo consulta un
        datasource si es owner o si su rol tiene este permission_view_
        menu. Esto es lo que hace efectivo «Público / todos los
        organismos» también dentro de Superset."""
        data = self._api_request('GET', f'dataset/{int(dataset_id)}')
        perm = ((data or {}).get('result') or {}).get('perm')
        if not perm:
            return {'error': 'no se pudo leer el perm del dataset '
                             f'{dataset_id}'}
        pvm_id = self._perm_view_menu_id(
            'datasource_access', perm, crear=True)
        if not pvm_id:
            return {'error': f"no existe el permiso 'datasource_access' "
                             f"para {perm}"}
        rol_id = self.obtener_rol_id(role_name)
        if not rol_id:
            return {'error': f"rol Superset '{role_name}' no existe"}
        rol = self._api_request('GET', f'security/roles/{rol_id}')
        permisos = ((rol or {}).get('result') or {}).get('permissions')
        if not permisos:
            # Guardia de seguridad: si el GET no devuelve la lista,
            # un PUT con solo el nuevo permiso BORRARÍA todos los
            # demás permisos del rol. Mejor fallar sin tocar nada.
            return {'error': f"no se pudo leer la lista de permisos "
                             f"del rol '{role_name}'; abortando para "
                             f"no vaciarla"}
        ids = {p.get('id') if isinstance(p, dict) else p
               for p in permisos}
        ids.discard(None)
        if otorgar:
            ids.add(pvm_id)
        else:
            ids.discard(pvm_id)
        data = self._write_request(
            'PUT', f'security/roles/{rol_id}',
            {'name': role_name, 'permissions': sorted(ids)})
        if data is None or '_error' in data:
            detalle = ((data or {}).get('_detalle')
                       or (data or {}).get('_error'))
            return {'error': detalle or 'error actualizando permisos '
                                      f'del rol {role_name}'}
        return {'success': True}

    def asignar_owners_dataset(self, dataset_id, usernames):
        """PUT dataset/{id} owners — declara owners adicionales al dataset.

        El endpoint de upload (database/{id}/upload/) no acepta owners en
        el form-data, así que el archivo sube con la cuenta de servicio
        como único dueño y se corrige después con este PUT. Sin owner,
        un usuario Gamma no tiene datasource_access y sus charts fallan
        con "This endpoint requires the datasource … permission".
        """
        ids = self._owner_ids(usernames)
        if not ids:
            return {'error': 'sin usuarios válidos para asignar como owners'}
        data = self._write_request(
            'PUT', f'dataset/{int(dataset_id)}', {'owners': ids})
        if data is None or '_error' in data:
            detalle = ((data or {}).get('_detalle')
                       or (data or {}).get('_error'))
            return {'error': detalle or 'error asignando owners al dataset'}
        return {'success': True}

    def eliminar_database(self, database_id):
        """DELETE database/{id} — retira la conexión de Superset."""
        data = self._write_request('DELETE', f'database/{database_id}', {})
        if not data or '_error' in data:
            detalle = ((data or {}).get('_detalle')
                       or (data or {}).get('_error'))
            return {'error': detalle or 'error eliminando conexión'}
        return {'success': True}

    def listar_esquemas_db(self, database_id):
        """Schemas disponibles en una database registrada."""
        data = self._api_request('GET', f'database/{database_id}/schemas/')
        return (data or {}).get('result') or []

    def listar_tablas_db(self, database_id, schema=None):
        """Tablas de un schema (o todas si schema=None)."""
        params = {}
        if schema:
            esc = schema.replace('!', '!!').replace("'", "!'")
            params['q'] = f"(schema_name:'{esc}')"
        data = self._api_request(
            'GET', f'database/{database_id}/tables/', params=params)
        result = (data or {}).get('result') or []
        return [t.get('value') or t.get('label') for t in result
                if isinstance(t, dict) and (t.get('value') or t.get('label'))]

    def crear_dataset_tabla(self, database_id, schema, table_name,
                            owner_usuario=None):
        """Dataset físico apuntando a una tabla de una conexión BD.

        `owner_usuario`: username Superset que queda como owner del
        dataset (datasource_access implícito para usuarios Gamma)."""
        data = self._write_request('POST', 'dataset/', {
            'database': database_id,
            'schema': schema or None,
            'table_name': table_name,
            'owners': self._owner_ids(owner_usuario),
        })
        if not data or '_error' in data:
            detalle = ((data or {}).get('_detalle')
                       or (data or {}).get('_error'))
            return {'error': detalle or 'error creando dataset'}
        ds_id = data.get('id')
        if ds_id is None:
            ds_id = (data.get('result') or {}).get('id')
        logger.info(
            f"Superset: dataset '{table_name}' creado sobre "
            f"database_id={database_id} (id={ds_id})")
        return {'success': True, 'dataset_id': ds_id,
                'table_name': table_name}

    def _get_siied_database_id(self):
        """Busca el ID de la base de datos del SIIED configurada en Superset"""
        db_name = getattr(settings, 'SUPERSET_DATABASE_NAME', 'SIIED - Indicadores')
        data = self._api_request('GET', 'database/')
        if not data:
            return None

        for db in data.get('result', []):
            if db.get('database_name') == db_name:
                return db.get('id')

        logger.warning(f"Superset: no se encontró database '{db_name}'")
        return None

    # ========================================================================
    # GESTIÓN DE USUARIOS (para rol cientifico_de_datos)
    # ========================================================================

    @staticmethod
    def _q_username(username):
        """Filtro rison por username con el valor entre comillas.

        Sin comillas, un username con '@', '.' u otros caracteres
        especiales rompe el parser de filtros de Superset y la búsqueda
        retorna vacío (usuario fantasma: existe pero no se encuentra)."""
        esc = username.replace('!', '!!').replace("'", "!'")
        return f"(filters:!((col:username,opr:eq,value:'{esc}')))"

    def usuario_existe(self, username):
        """Verifica si un usuario ya existe en Superset"""
        data = self._api_request(
            'GET', 'security/users/',
            params={'q': self._q_username(username)}
        )
        if not data:
            return False
        return len(data.get('result', [])) > 0

    def roles_de_usuario(self, username):
        """Roles Superset del usuario (['Alpha','Admin',...]) o [] si no existe."""
        data = self._api_request(
            'GET', 'security/users/',
            params={'q': self._q_username(username)}
        )
        result = (data or {}).get('result') or []
        if not result:
            return []
        return [r.get('name') for r in (result[0].get('roles') or [])
                if r.get('name')]

    def api_disponible(self):
        """True si la API responde con JSON válido (incluye auth admin)."""
        return self._api_request('GET', 'security/roles/') is not None

    def _obtener_usuario(self, username):
        """Fila completa del usuario en Superset (result[0]) o None."""
        data = self._api_request(
            'GET', 'security/users/',
            params={'q': self._q_username(username)}
        )
        resultados = (data or {}).get('result') or []
        return resultados[0] if resultados else None

    def _actualizar_usuario(self, user_actual, cambios):
        """PUT security/users/{id} con payload fusionado.

        La API es estricta con el esquema (rechaza campos desconocidos y
        roles que no sean IDs enteros), así que se envía la fila completa
        con los cambios aplicados sobre los campos escriturables."""
        payload = {
            'username': user_actual.get('username'),
            'email': user_actual.get('email') or '',
            'first_name': user_actual.get('first_name') or '',
            'last_name': user_actual.get('last_name') or '',
            'active': bool(user_actual.get('active', True)),
            'roles': [r.get('id') for r in (user_actual.get('roles') or [])
                      if r.get('id')],
        }
        payload.update(cambios)
        user_id = user_actual.get('id')
        data = self._write_request('PUT', f'security/users/{user_id}', payload)
        if data is None or '_error' in data:
            return {'error': (data or {}).get('_detalle')
                            or (data or {}).get('_error')
                            or 'error actualizando usuario en Superset'}
        return {'success': True}

    def obtener_rol_id(self, role_name):
        """ID interno de un rol Superset por nombre ('Alpha','Gamma',...) o None."""
        data = self._api_request('GET', 'security/roles/')
        result = (data or {}).get('result') or []
        for r in result:
            if (r.get('name') or '').lower() == role_name.lower():
                return r.get('id')
        return None

    def roles_disponibles(self):
        """Nombres de los roles existentes en la instancia (para mensajes de error)."""
        data = self._api_request('GET', 'security/roles/')
        return [r.get('name') for r in ((data or {}).get('result') or [])
                if r.get('name')]

    def crear_usuario(self, username, email='', first_name='', last_name='', role_name='Alpha'):
        """
        Crea un usuario en Superset con la contraseña compartida.
        Retorna dict con success/error.
        """
        shared_password = getattr(settings, 'SUPERSET_SHARED_PASSWORD', '')
        if not shared_password:
            return {'error': 'SUPERSET_SHARED_PASSWORD no configurado en settings.py'}

        # La API exige el ID entero del rol, no el nombre. Se consulta una
        # sola vez para distinguir dos fallas que antes daban el mismo
        # mensaje engañoso ('Rol X no existe. Roles disponibles: ninguno'):
        # API inaccesible/credenciales inválidas (data=None) vs rol
        # realmente ausente en la instancia.
        data_roles = self._api_request('GET', 'security/roles/')
        if data_roles is None:
            return {'error': 'No se pudo consultar Superset: el servicio no '
                             'responde o las credenciales admin fueron '
                             'rechazadas (o la cuenta de servicio está '
                             'desactivada en Superset — reactivarla '
                             'manualmente). Verifique SUPERSET_BASE_URL y '
                             'SUPERSET_ADMIN_USERNAME/PASSWORD.'}
        roles_api = (data_roles or {}).get('result') or []
        rol_id = next(
            (r.get('id') for r in roles_api
             if (r.get('name') or '').lower() == role_name.lower()),
            None)
        if rol_id is None:
            disponibles = ', '.join(
                r.get('name') for r in roles_api if r.get('name')) or 'ninguno'
            return {'error': f"Rol Superset '{role_name}' no existe. "
                             f'Roles disponibles: {disponibles}'}

        usuario_actual = self._obtener_usuario(username)
        if usuario_actual:
            # Ya existe: asegurar rol correcto y cuenta activa — el rol
            # SIIED pudo cambiar (analista ↔ analista_organismo) o el
            # usuario pudo quedar desactivado (active=False) al pasar por
            # un rol sin acceso BI.
            roles_actuales = [r.get('name') for r in
                              (usuario_actual.get('roles') or [])]
            if (role_name in roles_actuales
                    and usuario_actual.get('active', True)):
                logger.info(f"Superset: usuario '{username}' ya existe")
                return {'success': True, 'message': 'Usuario ya existe',
                        'username': username}
            nuevos_roles = [rol_id]
            # La cuenta de servicio necesita Admin para autenticar este
            # servicio: roles=[Alpha] sin Admin la deja activa pero con
            # 403 en toda la API (mismo deadlock que active=False).
            if (role_name.lower() != 'admin' and usuario_actual.get(
                    'username', '').lower()
                    == (self.admin_username or '').lower()):
                admin_id = next(
                    (r.get('id') for r in roles_api
                     if (r.get('name') or '').lower() == 'admin'), None)
                if admin_id and admin_id not in nuevos_roles:
                    nuevos_roles.append(admin_id)
            r = self._actualizar_usuario(
                usuario_actual, {'roles': nuevos_roles, 'active': True})
            if 'error' in r:
                return r
            logger.info(
                f"Superset: rol de '{username}' actualizado a {role_name}")
            return {'success': True,
                    'message': f'Rol actualizado a {role_name}',
                    'username': username}

        csrf_token = self._get_csrf_token()
        headers = self._get_headers()
        if not headers or not csrf_token:
            return {'error': 'Error de autenticación con Superset (admin)'}

        headers['X-CSRFToken'] = csrf_token
        headers['Referer'] = self.base_url

        url = f"{self.base_url}/api/v1/security/users/"
        payload = {
            'username': username,
            'email': email or f'{username}@siied.local',
            'first_name': first_name or username,
            'last_name': last_name or '',
            'password': shared_password,
            'roles': [rol_id],
            'active': True,
        }

        try:
            resp = self._session.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code in (200, 201):
                logger.info(f"Superset: usuario '{username}' creado exitosamente con rol {role_name}")
                return {'success': True, 'username': username}
            else:
                error_msg = resp.text[:500]
                logger.error(f"Superset: error creando usuario '{username}': {resp.status_code} {error_msg}")
                return {'error': f'Error {resp.status_code}: {error_msg}'}
        except requests.RequestException as e:
            logger.error(f"Superset: error creando usuario '{username}': {e}")
            return {'error': str(e)}

    def obtener_usuario_id(self, username):
        """Retorna el ID interno del usuario en Superset (o None)."""
        data = self._api_request(
            'GET', 'security/users/',
            params={'q': self._q_username(username)}
        )
        if not data:
            return None
        resultados = data.get('result', [])
        return resultados[0].get('id') if resultados else None

    def desactivar_usuario(self, username):
        """Desactiva (active=False) la cuenta de Superset del usuario.

        Se usa cuando el perfil SIIED pasa a activo=False o cambia a un
        rol sin acceso BI — evita cuentas Alpha/Gamma huérfanas."""
        # self.admin_username es la cuenta con la que este servicio se
        # autentica (default 'admin' si el setting no está). Usar el getattr
        # directo dejaba un hueco: si el setting estaba vacío, el guard no
        # disparaba y la cuenta 'admin' podía desactivarse igual → deadlock.
        if username and username.lower() == (self.admin_username or '').lower():
            # Desactivar la cuenta de servicio mata la credencial con la
            # que este servicio se autentica → deadlock: ya no puede
            # verificar, crear ni reactivar ninguna cuenta.
            logger.warning(
                "Superset: se evitó desactivar la cuenta de servicio "
                f"'{username}' (SUPERSET_ADMIN_USERNAME)")
            return {'error': 'No se puede desactivar la cuenta admin de '
                             'servicio (SUPERSET_ADMIN_USERNAME): el sync '
                             'dejaría de poder autenticarse. Use una '
                             'cuenta de servicio dedicada.'}
        usuario_actual = self._obtener_usuario(username)
        if not usuario_actual:
            return {'success': True, 'message': 'Usuario no existe en Superset'}
        if not usuario_actual.get('active', True):
            return {'success': True, 'message': 'Usuario ya estaba desactivado'}
        r = self._actualizar_usuario(usuario_actual, {'active': False})
        if 'error' in r:
            return r
        logger.info(f"Superset: usuario '{username}' desactivado")
        return {'success': True, 'username': username}

    # ========================================================================
    # TOOLS DE ANALÍTICA (equivalente REST de las tools del MCP de Superset:
    # get_dataset_info, get_chart_data, generate_chart, generate_dashboard).
    # Si la instancia expone superset/mcp_service, este mismo contrato puede
    # transportarse por MCP sin cambiar los consumidores.
    # ========================================================================

    def _write_request(self, method, endpoint, payload, timeout=60):
        """POST/PUT autenticado con CSRF — para operaciones que mutan."""
        csrf_token = self._get_csrf_token()
        headers = self._get_headers()
        if not headers or not csrf_token:
            logger.error(
                f"Superset API [{method} {endpoint}]: abortada — "
                f"headers={bool(headers)} csrf={bool(csrf_token)}. "
                "Falló auth/CSRF, no la request propiamente.")
            return None
        headers['X-CSRFToken'] = csrf_token
        headers['Referer'] = self.base_url
        try:
            resp = self._session.request(
                method, f"{self.base_url}/api/v1/{endpoint}",
                headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 401:
                self._access_token = None
                headers = self._get_headers()
                if not headers:
                    return None
                headers['X-CSRFToken'] = csrf_token
                headers['Referer'] = self.base_url
                resp = self._session.request(
                    method, f"{self.base_url}/api/v1/{endpoint}",
                    headers=headers, json=payload, timeout=timeout)
            if resp.status_code >= 400:
                logger.error(
                    f"Superset API [{method} {endpoint}]: "
                    f"{resp.status_code} {resp.text[:400]}")
                try:
                    detalle = resp.json()
                except ValueError:
                    detalle = resp.text[:400]
                return {'_error': f'HTTP {resp.status_code}',
                        '_detalle': detalle}
            try:
                return resp.json()
            except ValueError:
                return {}
        except requests.RequestException as e:
            logger.error(f"Superset API [{method} {endpoint}]: {e}")
            return None

    def info_dataset(self, dataset_id):
        """Detalle de un dataset: columnas con tipo y si es temporal.

        Equivalente a la tool `get_dataset_info` del MCP service."""
        data = self._api_request('GET', f'dataset/{dataset_id}')
        if not data:
            return None
        result = data.get('result', {})
        return {
            'id': result.get('id'),
            'table_name': result.get('table_name', ''),
            'database_id': (result.get('database') or {}).get('id'),
            'kind': result.get('kind', ''),
            'schema': result.get('schema', ''),
            'sql': result.get('sql') or '',
            'columnas': [
                {
                    'nombre': c.get('column_name', ''),
                    'tipo': c.get('type', ''),
                    'temporal': bool(c.get('is_dttm')),
                }
                for c in (result.get('columns') or [])
            ],
        }

    def consultar_dataset(self, dataset_id, columnas=None, metricas=None,
                          filtros=None, orden=None, limite=100):
        """Ejecuta una consulta agregada sobre un dataset vía chart/data.

        Sirve tanto para datasets físicos como virtuales — no requiere
        SQL crudo. Equivalente a `get_chart_data`/`execute_sql` del MCP.
        Retorna {'ok', 'columnas', 'filas', 'error'}."""
        query = {
            'columns': [str(c) for c in (columnas or [])][:10],
            # Las métricas pueden ser strings (métricas guardadas) o
            # dicts adhoc {expressionType, ...} — pasarlas tal cual.
            'metrics': list(metricas or [])[:10],
            'row_limit': max(1, min(int(limite or 100), 1000)),
            'result_format': 'json',
        }
        if filtros:
            query['filters'] = filtros[:20]
        if orden:
            # orden: (columna str o métrica adhoc dict, descendente)
            col, desc = orden
            query['orderby'] = [[col, bool(desc)]]
        payload = {
            'datasource': {'id': int(dataset_id), 'type': 'table'},
            'queries': [query],
            'result_format': 'json',
            'result_type': 'full',
        }
        data = self._write_request('POST', 'chart/data', payload)
        if not data or '_error' in data:
            return {'ok': False, 'columnas': [], 'filas': [],
                    'error': (data or {}).get('_error')
                              or 'Superset no respondio'}
        resultados = data.get('result') or []
        if not resultados:
            return {'ok': False, 'columnas': [], 'filas': [],
                    'error': 'La consulta no devolvio resultados'}
        r = resultados[0]
        if r.get('status') == 'failed' or r.get('error'):
            return {'ok': False, 'columnas': [], 'filas': [],
                    'error': str(r.get('error')
                                 or r.get('message')
                                 or 'consulta fallida')[:300]}
        return {
            'ok': True,
            'columnas': r.get('colnames') or [],
            'filas': (r.get('data') or [])[:500],
            'error': None,
        }

    def _owner_ids(self, usernames):
        """IDs Superset de los usernames dados (omite los inexistentes).

        Acepta str único o iterable. Se usa para que los activos creados
        por la cuenta de servicio queden también a nombre del usuario
        SIIED que los pidió — de otro modo no aparecen bajo «Mío» en la
        UI de Superset ni el usuario puede editarlos."""
        if isinstance(usernames, str):
            usernames = [usernames]
        ids = []
        for un in (usernames or []):
            u = self._obtener_usuario(un)
            if u and u.get('id'):
                ids.append(u['id'])
        return ids

    def crear_chart(self, nombre, dataset_id, viz_type, params,
                    dashboards=None, owner_usuario=None):
        """Crea un chart (slice) en Superset.

        Equivalente a `generate_chart` del MCP. `params` es el dict de
        configuración del viz; se serializa a JSON. Retorna
        {'ok', 'chart_id', 'error'}.

        `owner_usuario`: username Superset que queda como owner del
        chart además de la cuenta de servicio (visibilidad «Mío»)."""
        import json as _json
        payload = {
            'datasource_id': int(dataset_id),
            'datasource_type': 'table',
            'slice_name': str(nombre)[:250],
            'viz_type': viz_type,
            'params': _json.dumps(params or {}),
            'cache_timeout': None,
            'owners': self._owner_ids(owner_usuario),
        }
        if dashboards:
            payload['dashboards'] = [int(d) for d in dashboards]
        data = self._write_request('POST', 'chart/', payload)
        if not data or '_error' in data:
            return {'ok': False, 'chart_id': None,
                    'error': (data or {}).get('_detalle')
                             or (data or {}).get('_error')
                             or 'error creando chart'}
        chart_id = data.get('id') or (data.get('result') or {}).get('id')
        return {'ok': bool(chart_id), 'chart_id': chart_id,
                'error': None if chart_id else 'sin id en respuesta'}

    def crear_dashboard(self, titulo, slug=None, publicar=False,
                        owner_usuario=None):
        """Crea un dashboard vacío. Equivalente a `generate_dashboard`.

        `owner_usuario`: username Superset que queda como owner además
        de la cuenta de servicio (lo ve bajo «Mío» y puede editarlo)."""
        import json as _json
        payload = {
            'dashboard_title': str(titulo)[:250],
            'slug': slug or None,
            'published': bool(publicar),
            'css': '',
            'json_metadata': _json.dumps({}),
            'position_json': _json.dumps({}),
            'owners': self._owner_ids(owner_usuario),
        }
        data = self._write_request('POST', 'dashboard/', payload)
        if not data or '_error' in data:
            return {'ok': False, 'dashboard_id': None,
                    'error': (data or {}).get('_detalle')
                             or (data or {}).get('_error')
                             or 'error creando dashboard'}
        dash_id = data.get('id') or (data.get('result') or {}).get('id')
        return {'ok': bool(dash_id), 'dashboard_id': dash_id,
                'error': None if dash_id else 'sin id en respuesta'}

    def actualizar_dashboard(self, dashboard_id, payload):
        """PUT parcial sobre un dashboard (position_json, metadata...)."""
        data = self._write_request(
            'PUT', f'dashboard/{int(dashboard_id)}', payload)
        if data is None or '_error' in data:
            return {'ok': False,
                    'error': (data or {}).get('_detalle')
                             or (data or {}).get('_error')
                             or 'error actualizando dashboard'}
        return {'ok': True, 'error': None}

    # ========================================================================
    # ELIMINACIÓN DE ACTIVOS
    # ========================================================================

    def charts_de_dashboard(self, dashboard_id):
        """IDs de los charts asociados a un dashboard.

        GET dashboard/{id} devuelve result.charts como lista de STRINGS
        (títulos); el endpoint dashboard/{id}/charts sí devuelve los
        objetos chart con su id.
        """
        data = self._api_request(
            'GET', f'dashboard/{int(dashboard_id)}/charts')
        if not data:
            return []
        return [c.get('id') for c in (data.get('result') or [])
                if isinstance(c, dict) and c.get('id') is not None]

    def charts_de_dataset(self, dataset_id):
        """Charts que referencian un dataset (bloquean su eliminación)."""
        data = self._api_request(
            'GET', 'chart/',
            params={'q': (
                '(filters:!((col:datasource_id,opr:eq,value:%s)),'
                'columns:!(id,slice_name))' % int(dataset_id))})
        if not data:
            return []
        return [{'id': c.get('id'), 'nombre': c.get('slice_name', '')}
                for c in data.get('result', [])]

    def chart_en_dashboard(self, chart_id):
        """True si el chart sigue asociado a algún dashboard."""
        data = self._api_request('GET', f'chart/{int(chart_id)}')
        if not data:
            return True  # prudente: sin certeza no se borra
        return bool(data.get('result', {}).get('dashboards'))

    def eliminar_chart(self, chart_id):
        """Elimina un chart (slice). Retorna True si quedó eliminado."""
        data = self._write_request('DELETE', f'chart/{int(chart_id)}', None)
        return data is not None and not (
            isinstance(data, dict) and '_error' in data)

    def eliminar_dashboard(self, dashboard_id, con_charts=True):
        """Elimina el dashboard en Superset.

        Con ``con_charts=True`` elimina además los charts que quedaron
        huérfanos (no asociados a otro dashboard). Superset NO borra los
        charts con el dashboard y después siguen bloqueando el borrado
        de los datasets.
        """
        chart_ids = (self.charts_de_dashboard(dashboard_id)
                     if con_charts else [])
        data = self._write_request(
            'DELETE', f'dashboard/{int(dashboard_id)}', None)
        if data is None or (isinstance(data, dict) and '_error' in data):
            return {'ok': False,
                    'error': ((data or {}).get('_detalle')
                              or (data or {}).get('_error')
                              or 'Superset no respondió')}
        huerfanos = 0
        for cid in chart_ids:
            if not self.chart_en_dashboard(cid) \
                    and self.eliminar_chart(cid):
                huerfanos += 1
        return {'ok': True, 'charts_eliminados': huerfanos}

    def eliminar_dataset(self, dataset_id):
        """Elimina el dataset en Superset.

        Superset rechaza el DELETE mientras existan charts que lo
        referencien — 'charts_bloquean' permite informar cuáles faltan
        por borrar primero.
        """
        data = self._write_request(
            'DELETE', f'dataset/{int(dataset_id)}', None)
        if data is None:
            return {'ok': False, 'error': 'Superset no respondió',
                    'charts_bloquean': []}
        if isinstance(data, dict) and '_error' in data:
            return {'ok': False,
                    'error': str(data.get('_detalle')
                                 or data.get('_error'))[:300],
                    'charts_bloquean': self.charts_de_dataset(dataset_id)}
        return {'ok': True, 'charts_bloquean': []}

    def eliminar_tabla_fisica(self, nombre_tabla):
        """DROP TABLE de la copia física que deja el upload de CSV.

        Superset solo borra el dataset (metadato): la tabla subida por
        CSV queda en el esquema public de la BD del SIIED. Solo debe
        invocarse para datasets registrados como subidos por usuarios
        (es_base_siied=False) — nunca sobre tablas del modelo SIIED ni
        datasets virtuales. Retorna True si la eliminó.
        """
        if not _RE_TABLA.match(nombre_tabla or ''):
            return False
        try:
            from django.db import connection
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT table_type FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=%s",
                    [nombre_tabla])
                row = cur.fetchone()
                if not row or row[0] != 'BASE TABLE':
                    return False
                cur.execute('DROP TABLE IF EXISTS "%s"' % nombre_tabla)
            return True
        except Exception:
            logger.exception(
                'Superset: no se pudo eliminar la tabla %s', nombre_tabla)
            return False

    # ========================================================================
    # HEALTH CHECK
    # ========================================================================

    def health_check(self):
        """Verifica si Superset está disponible.

        Algunos deployments no exponen /health ni rutas públicas con 200
        (devuelven 404 en cualquier path). Como base_url apunta directo
        al WSGI (localhost), cualquier respuesta HTTP < 500 indica que el
        servicio está sirviendo; solo errores de conexión o 5xx lo marcan
        como caído.
        """
        try:
            resp = self._session.get(f"{self.base_url}/health", timeout=5)
            if resp.status_code < 500:
                return True
            logger.warning(
                f"Superset health_check: {self.base_url}/health "
                f"respondió {resp.status_code}")
            return False
        except requests.RequestException as e:
            logger.warning(
                f"Superset health_check: {self.base_url} no responde: {e}")
            return False

    def get_status(self):
        """Retorna estado completo de la integración"""
        is_healthy = self.health_check()
        can_auth = False
        dashboard_count = 0
        dataset_count = 0

        if is_healthy:
            can_auth = self._authenticate()
            if can_auth:
                dashboards = self.listar_dashboards()
                datasets = self.listar_datasets()
                dashboard_count = len(dashboards or [])
                dataset_count = len(datasets or [])

        return {
            'superset_disponible': is_healthy,
            'autenticacion_ok': can_auth,
            'total_dashboards': dashboard_count,
            'total_datasets': dataset_count,
            'url_publica': self.public_url,
        }
