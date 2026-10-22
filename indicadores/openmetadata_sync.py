"""Sincronización SIIED -> OpenMetadata (catálogo vivo de activos).

Diferente de ``om_sync.py`` (que apunta al Metadata Editor/NADA y solo
publica Operaciones Estadísticas consolidadas como DDI): aquí se
catalogan los activos del inventario como entidades OpenMetadata:

  - FuenteDatos (taller)          -> Table en siied.taller_fuentes
  - BaseCatalogo (datalake)       -> Table en siied.datalake_bases
  - ConjuntoDatos                 -> Table en siied.conjuntos
  - OperacionEstadistica          -> Table en siied.nada_operaciones
  - Indicador                     -> Dashboard en servicio siied_dashboards
  - capa bronce/plata/gold        -> tag siied.<capa>

Ver docs/ARQUITECTURA_OPENMETADATA_Y_NADA.md.

Variables de entorno:
    OM_SERVER_URL      (default http://localhost:8585)
    OM_ADMIN_EMAIL     (default admin@open-metadata.org)
    OM_ADMIN_PASSWORD  (default admin — solo piloto local)
"""
import base64
import os
import re
import unicodedata

import requests

SERVER = os.environ.get('OM_SERVER_URL', 'http://localhost:8585').rstrip('/')
API = f'{SERVER}/api/v1'
ADMIN_EMAIL = os.environ.get('OM_ADMIN_EMAIL', 'admin@open-metadata.org')
ADMIN_PASSWORD = os.environ.get('OM_ADMIN_PASSWORD', 'admin')

SERVICE = 'siied'
DASH_SERVICE = 'siied_dashboards'

# database -> (descripcion, schema)
DATABASES = {
    'taller_fuentes': (
        'Fuentes de datos censadas en el taller de gestión '
        '(DADII). Capa bronce/plata/gold según madurez.'),
    'datalake_bases': (
        'Bases del Data Lake publicadas en el catálogo '
        '(capa gold y dimensiones).'),
    'conjuntos': (
        'Conjuntos de datos con ficha técnica del SIIED '
        '(VariableConjuntoDatos).'),
    'nada_operaciones': (
        'Operaciones Estadísticas publicadas en NADA '
        '(fuente de verdad: catálogo NADA/ADDA).'),
}

TIPO_OM = {
    'texto': 'VARCHAR', 'char': 'VARCHAR', 'str': 'VARCHAR',
    'numero': 'DOUBLE', 'decimal': 'DOUBLE', 'float': 'DOUBLE',
    'entero': 'INT', 'int': 'INT', 'integer': 'INT',
    'fecha': 'DATE', 'date': 'DATE', 'timestamp': 'TIMESTAMP',
    'booleano': 'BOOLEAN', 'bool': 'BOOLEAN',
    'geografico': 'VARCHAR', 'json': 'JSON',
}


def _slug(texto, fallback='x'):
    """Nombre seguro para FQN de OpenMetadata: [a-z0-9_]."""
    t = unicodedata.normalize('NFKD', str(texto or ''))
    t = ''.join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r'[^a-z0-9]+', '_', t).strip('_')
    return t[:64] or fallback


def _tipo(raw):
    return TIPO_OM.get(_slug(raw), 'VARCHAR')


def _col(nombre, tipo, descripcion=''):
    col = {'name': _slug(nombre), 'dataType': _tipo(tipo)}
    if col['dataType'] == 'VARCHAR':
        col['dataLength'] = 255  # OM exige dataLength para char/varchar
    if descripcion:
        col['description'] = str(descripcion)[:250]
    return col


class OMClient:
    def __init__(self):
        self.token = None

    def login(self):
        pwd = base64.b64encode(ADMIN_PASSWORD.encode()).decode()
        r = requests.post(f'{API}/users/login', json={
            'email': ADMIN_EMAIL, 'password': pwd}, timeout=30)
        r.raise_for_status()
        self.token = r.json()['accessToken']

    def _put(self, path, payload):
        r = requests.put(f'{API}/{path}', json=payload,
                         headers={'Authorization': f'Bearer {self.token}'},
                         timeout=30)
        if r.status_code not in (200, 201):
            raise RuntimeError(f'PUT {path}: {r.status_code} {r.text[:200]}')
        return r.json()

    def ensure_infra(self):
        """Servicio + bases + schemas + clasificación/tags de capa."""
        self._put('services/databaseServices', {
            'name': SERVICE, 'serviceType': 'CustomDatabase',
            'description': 'Inventario de activos estadísticos del SIIED '
                           '(push vía API; el datalake vive fuera).'})
        self._put('services/dashboardServices', {
            'name': DASH_SERVICE, 'serviceType': 'CustomDashboard',
            'description': 'Indicadores y productos de análisis del SIIED.'})
        for db, desc in DATABASES.items():
            self._put('databases', {
                'name': db, 'service': SERVICE, 'description': desc})
            self._put('databaseSchemas', {
                'name': 'public', 'database': f'{SERVICE}.{db}'})
        self._put('classifications', {
            'name': 'siied', 'description':
                'Clasificación SIIED: capa de madurez de la fuente '
                '(taller->integración) y dominios temáticos.'})
        for capa in ('bronce', 'plata', 'gold'):
            self._put('tags', {
                'name': capa, 'classification': 'siied',
                'description': f'Capa {capa} del ciclo taller->datalake.'})

    def put_table(self, database, nombre, descripcion='', columns=None,
                  tags=None, source_url='', key=''):
        # key = pk SIIED: slugs truncados a 64 chars colisionan entre
        # nombres largos iguales (indicadores PIB x departamento…)
        name = f'{_slug(nombre, "x")[:57]}_{key}' if key else _slug(nombre)
        fq = f'{SERVICE}.{database}.public.{name}'
        payload = {
            'name': name,
            'displayName': str(nombre)[:128],
            'databaseSchema': f'{SERVICE}.{database}.public',
            'tableType': 'Regular',
            'description': (str(descripcion or '') or '(sin descripción)')[:4000],
            'columns': columns or [],
            'tags': [{'tagFQN': f'siied.{t}'} for t in (tags or [])],
        }
        if source_url:
            payload['sourceUrl'] = source_url
        return fq, self._put('tables', payload)

    def put_dashboard(self, nombre, descripcion='', source_url='', key=''):
        name = f'{_slug(nombre, "x")[:57]}_{key}' if key else _slug(nombre)
        fq = f'{DASH_SERVICE}.{name}'
        payload = {
            'name': name,
            'displayName': str(nombre)[:128],
            'service': DASH_SERVICE,
            'description': (str(descripcion or '') or '(sin descripción)')[:4000],
        }
        if source_url:
            payload['sourceUrl'] = source_url
        return fq, self._put('dashboards', payload)


# ------------------------------------------------------------------
# Serializadores SIIED -> entidades OM
# ------------------------------------------------------------------

def ser_fuente(f):
    """FuenteDatos (taller) -> table + tag de capa."""
    cols = [_col(v.nombre, v.tipo,
                 (v.descripcion or '')
                 + (' [identificador]' if v.es_identificador else ''))
            for v in f.variables.all()]
    org = getattr(getattr(f, 'inscripcion', None), 'organismo', None)
    desc = f.descripcion or ''
    if org:
        desc = f'Organismo: {org}\n\n{desc}'
    return 'taller_fuentes', f.nombre, desc, cols, \
        [f.capa] if getattr(f, 'capa', '') in ('bronce', 'plata', 'gold') else []


def ser_base(b):
    """BaseCatalogo (datalake) -> table gold."""
    cols = [_col(c.nombre, getattr(c, 'tipo', 'texto'),
                 c.descripcion or '')
            for c in b.campos.all()]
    partes = [b.descripcion or '']
    if b.get_organismo_display:
        partes.insert(0, f'Organismo: {b.get_organismo_display()}')
    if b.frecuencia:
        partes.append(f'Frecuencia: {b.frecuencia}')
    if b.cobertura:
        partes.append(f'Cobertura: {b.cobertura}')
    return 'datalake_bases', b.nombre, '\n\n'.join(p for p in partes if p), \
        cols, ['gold']


def ser_conjunto(cd):
    """ConjuntoDatos -> table con columnas desde VariableConjuntoDatos."""
    cols = [_col(v.codigo_variable, getattr(v, 'tipo_dato', 'texto'),
                 v.nombre_variable or v.codigo_variable)
            for v in cd.variables.all()]
    return 'conjuntos', cd.nombre, cd.descripcion or '', cols, []


def ser_operacion(oe):
    """OperacionEstadistica -> table (metadato de descubrimiento)."""
    nombre = getattr(oe, 'nombre', None) or getattr(oe, 'titulo', '') \
        or f'OE-{oe.pk}'
    desc = getattr(oe, 'descripcion', '') or getattr(oe, 'objetivo', '') \
        or ''
    org = getattr(getattr(oe, 'organismo', None), 'nombre', '') \
        or getattr(oe, 'organismo_texto', '')
    if org:
        desc = f'Organismo: {org}\n\n{desc}'
    return 'nada_operaciones', nombre, desc, [], []


def ser_indicador(ind):
    """Indicador -> dashboard (activo de consumo)."""
    partes = []
    sub = getattr(ind, 'subtema', None)
    if sub and getattr(sub, 'tema', None):
        partes.append(f'Tema: {sub.tema.nombre}')
        dom = getattr(sub.tema, 'dominio', None)
        if dom:
            partes.append(f'Dominio: {dom.nombre}')
    if ind.unidad_medida:
        partes.append(f'Unidad: {ind.unidad_medida}')
    partes.append(getattr(ind, 'descripcion_indicador', '') or '')
    return ind.nombre, '\n\n'.join(p for p in partes if p), \
        f'/admin/indicadores/indicador/{ind.pk}/change/'
