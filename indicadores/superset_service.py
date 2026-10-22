"""
Servicio de integración con Apache Superset API REST.
Maneja autenticación, consulta de dashboards, subida de CSV y gestión de datasets.
"""
import logging
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


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
        """Obtiene CSRF token para operaciones de escritura"""
        try:
            headers = self._get_headers()
            if not headers:
                return None
            url = f"{self.base_url}/api/v1/security/csrf_token/"
            resp = self._session.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            self._csrf_token = resp.json().get('result')
            return self._csrf_token
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
        if not data:
            return []

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
                'thumbnail_url': d.get('thumbnail_url', ''),
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
                        first_name='', last_name=''):
        """Genera un guest token para embeber un recurso (dashboard).

        El token lo consume @superset-ui/embedded-sdk en el navegador;
        expira según GUEST_TOKEN_JWT_EXP_SECONDS de Superset.
        """
        payload = {
            'resources': [{'type': 'dashboard', 'id': str(resource_id)}],
            'rls': [],
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
        if not data:
            return []

        datasets = []
        for d in data.get('result', []):
            datasets.append({
                'id': d.get('id'),
                'table_name': d.get('table_name', ''),
                'kind': d.get('kind', ''),
                'schema': d.get('schema', ''),
                'database_name': (d.get('database') or {}).get('database_name', ''),
                'changed_on': d.get('changed_on_delta_humanized', ''),
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
                form_data['delimiter'] = ','
            elif tipo == 'excel':
                form_data['sheet_name'] = '0'
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
                logger.error(f"Superset: error subiendo CSV: {resp.status_code} {error_msg}")
                return {'error': f'Error {resp.status_code}: {error_msg}'}

        except requests.RequestException as e:
            logger.error(f"Superset: error subiendo CSV: {e}")
            return {'error': str(e)}

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

    def usuario_existe(self, username):
        """Verifica si un usuario ya existe en Superset"""
        data = self._api_request(
            'GET', 'security/users/',
            params={'q': f'(filters:!((col:username,opr:eq,value:{username})))'}
        )
        if not data:
            return False
        return len(data.get('result', [])) > 0

    def crear_usuario(self, username, email='', first_name='', last_name='', role_name='Alpha'):
        """
        Crea un usuario en Superset con la contraseña compartida.
        Retorna dict con success/error.
        """
        shared_password = getattr(settings, 'SUPERSET_SHARED_PASSWORD', '')
        if not shared_password:
            return {'error': 'SUPERSET_SHARED_PASSWORD no configurado en settings.py'}

        if self.usuario_existe(username):
            logger.info(f"Superset: usuario '{username}' ya existe")
            return {'success': True, 'message': 'Usuario ya existe', 'username': username}

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
            'roles': [role_name],
            'is_active': True,
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

    def crear_chart(self, nombre, dataset_id, viz_type, params,
                    dashboards=None):
        """Crea un chart (slice) en Superset.

        Equivalente a `generate_chart` del MCP. `params` es el dict de
        configuración del viz; se serializa a JSON. Retorna
        {'ok', 'chart_id', 'error'}."""
        import json as _json
        payload = {
            'datasource_id': int(dataset_id),
            'datasource_type': 'table',
            'slice_name': str(nombre)[:250],
            'viz_type': viz_type,
            'params': _json.dumps(params or {}),
            'cache_timeout': None,
            'owners': [],
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

    def crear_dashboard(self, titulo, slug=None, publicar=False):
        """Crea un dashboard vacío. Equivalente a `generate_dashboard`."""
        import json as _json
        payload = {
            'dashboard_title': str(titulo)[:250],
            'slug': slug or None,
            'published': bool(publicar),
            'css': '',
            'json_metadata': _json.dumps({}),
            'position_json': _json.dumps({}),
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
                dashboard_count = len(dashboards)
                dataset_count = len(datasets)

        return {
            'superset_disponible': is_healthy,
            'autenticacion_ok': can_auth,
            'total_dashboards': dashboard_count,
            'total_datasets': dataset_count,
            'url_publica': self.public_url,
        }
