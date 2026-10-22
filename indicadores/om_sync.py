"""Sincronización de metadatos del SIIED hacia OpenMetadata Editor.

Cada conjunto de metadatos se serializa al esquema JSON del editor y se sube
con ``POST /api/editor/create/{type}`` usando un ``idno`` estable +
``overwrite: true``, de modo que las sincronizaciones son idempotentes.

Conjuntos soportados:
- Operaciones estadísticas -> tipo ``microdata`` (DDI + Dublin Core)
- Conjuntos de datos      -> tipo ``microdata`` (DDI, con variables)
- Indicadores             -> tipo ``indicator`` (SDMX/MSD)
- Fuentes de información  -> tipo ``document``  (Dublin Core + DDI)

Configuración vía settings o variables de entorno:
    OM_EDITOR_BASE_URL (default http://localhost:8080/index.php/api)
    OM_EDITOR_API_KEY  (default siied-local-2026)
"""

import logging
import os
import re
import unicodedata

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

OM_BASE_URL = getattr(
    settings, 'OM_EDITOR_BASE_URL',
    os.environ.get('OM_EDITOR_BASE_URL', 'http://localhost:8080/index.php/api'))
OM_API_KEY = getattr(
    settings, 'OM_EDITOR_API_KEY',
    os.environ.get('OM_EDITOR_API_KEY', 'siied-local-2026'))

# clave interna -> título de colección en OM Editor
COLLECTIONS = {
    'operaciones': 'Operaciones Estadísticas',
    'conjuntos': 'Conjuntos de Datos',
    'indicadores': 'Indicadores',
    'fuentes': 'Fuentes de Información',
}


def _txt(v):
    """Normaliza texto: None->'', strip."""
    return (str(v).strip() if v is not None else '')


def _names(v):
    """Convierte un nombre (o varios separados por ';') en lista DDI [{name}]."""
    if not v:
        return []
    partes = [p.strip() for p in str(v).replace('|', ';').split(';') if p.strip()]
    return [{'name': p} for p in partes]


def _keywords(v):
    """Convierte texto separado por comas/; en lista DDI [{keyword}]."""
    if not v:
        return []
    partes = [p.strip() for p in str(v).replace(';', ',').split(',') if p.strip()]
    return [{'keyword': p} for p in partes]


def _year(v):
    """Extrae año de fecha/str; '' si no aplica."""
    s = _txt(v)
    return s[:4] if s[:4].isdigit() else ''


class OMClient:
    """Cliente REST mínimo para el API del OpenMetadata Editor."""

    def __init__(self, base_url=None, api_key=None):
        self.base_url = (base_url or OM_BASE_URL).rstrip('/')
        self.session = requests.Session()
        self.session.headers['X-API-KEY'] = api_key or OM_API_KEY

    def _post(self, path, payload):
        r = self.session.post(f'{self.base_url}/{path}', json=payload, timeout=60)
        try:
            data = r.json()
        except ValueError:
            raise RuntimeError(f'OM {path}: HTTP {r.status_code} sin JSON')
        if data.get('status') not in ('success', True):
            raise RuntimeError(f"OM {path}: {data.get('message') or data}")
        return data

    def _get(self, path):
        r = self.session.get(f'{self.base_url}/{path}', timeout=60)
        return r.json()

    def list_collections(self):
        return self._get('collections') or {}

    def ensure_collection(self, title):
        """Devuelve el id de la colección con ese título; la crea si falta."""
        for c in self.list_collections().get('collections', []):
            if c.get('title') == title:
                return c['id']
        data = self._post('collections', {'title': title})
        return data['collection']

    def upsert_project(self, ptype, idno, metadata, collection_id=None):
        """Crea/actualiza idempotentemente un proyecto del tipo dado."""
        payload = dict(metadata)
        payload['idno'] = idno
        payload['overwrite'] = True
        if collection_id:
            payload['collection_ids'] = [collection_id]
        return self._post(f'editor/create/{ptype}', payload)

    def ensure_datafile(self, sid, file_id, file_name):
        """Crea el archivo de datos lógico del proyecto; idempotente."""
        try:
            return self._post(f'datafiles/{sid}', {
                'file_id': file_id, 'file_name': file_name})
        except RuntimeError as e:
            if 'already exists' in str(e):
                return {'status': 'success', 'datafile': {
                    'file_id': file_id, 'file_name': file_name}}
            raise

    def sync_variables(self, sid, variables):
        """Sube/actualiza variables de un proyecto (upsert por nombre)."""
        if not variables:
            return {'status': 'success', 'variables': []}
        return self._post(f'variables/{sid}', variables)


# ---------------------------------------------------------------------------
# Serializadores: objeto SIIED -> (tipo_om, idno, metadata)
# ---------------------------------------------------------------------------

def serialize_operacion(op):
    """OperacionEstadistica -> proyecto microdata (DDI + Dublin Core)."""
    idno = f'SIIED-OPE-{op.pk}'
    org = _txt(getattr(op, 'entidad_recopiladora', '') or getattr(op, 'organismo', ''))
    return 'microdata', idno, {
        'doc_desc': {
            'title': _txt(op.nombre),
            'idno': idno,
            'producers': _names(org),
            'prod_date': _year(getattr(op, 'anio_adda', None) or getattr(op, 'fecha_inicio', None)),
        },
        'study_desc': {
            'title_statement': {
                'idno': idno,
                'title': _txt(op.nombre),
                'identifiers': [{'identifier': _txt(op.codigo), 'type': 'codigo'}] if op.codigo else [],
            },
            'authoring_entity': _names(org),
            'production_statement': {'producers': _names(org)},
            'study_info': {
                'abstract': _txt(op.descripcion or op.objetivo),
                'purpose': _txt(op.objetivo),
                'analysis_unit': _txt(getattr(op, 'unidad_observ', '')),
                'geog_coverage': 'Santiago de Cali, Colombia',
                'nation': {'name': 'Colombia', 'abbreviation': 'CO'},
                'kind_of_data': _txt(getattr(op, 'tipo_operacion', '')),
                'keywords': _keywords(getattr(op, 'tema', '')),
                'time_periods': ([{'start': _year(op.fecha_inicio), 'end': _year(op.fecha_fin)}]
                                 if getattr(op, 'fecha_inicio', None) else []),
            },
            'method': {'data_collection': {'frequency': _txt(getattr(op, 'periodicidad', ''))}},
            'data_access': {'dataset_use': {'contact': _contactos(op)}},
        },
        'dublin_core': {
            'title': _txt(op.nombre),
            'creator': org,
            'subject': _txt(getattr(op, 'tema', '')),
            'description': _txt(op.descripcion or op.objetivo),
            'type': 'Dataset',
            'coverage': 'Santiago de Cali, Colombia',
        },
    }


def serialize_conjunto_variables(cd, file_id='F1'):
    """Variables del conjunto como table_columns del schema 'table'.

    Cada entrada conserva la ficha técnica completa de
    VariableConjuntoDatos (los proyectos 'table' no tienen subsistema
    de datafiles/variables: las columnas van dentro del metadato).
    """
    columnas = []
    for i, v in enumerate(cd.variables.all().order_by('orden', 'id'), start=1):
        org = v.organismo_productor or v.organismo_productor_legado or ''
        col = {
            # claves declaradas del schema table_columns
            'var_name': _txt(v.codigo_variable) or f'V{i}',
            'label': _txt(v.nombre_variable) or _txt(v.codigo_variable),
            'dataset': 'F1',
            # ficha técnica SIIED (props extendidas)
            'definicion': _txt(getattr(v, 'definicion_conceptual', '')),
            'poblacion_objetivo': _txt(getattr(v, 'poblacion_objetivo', '')),
            'cobertura_geografica': _txt(getattr(v, 'cobertura_geografica', '')),
            'desagregacion_geografica': _txt(getattr(v, 'desagregacion_geografica', '')),
            'desagregacion_tematica': _txt(getattr(v, 'desagregacion_tematica', '')),
            'tipo_dato': _txt(getattr(v, 'tipo_dato', '')),
            'dominio_dato': _txt(getattr(v, 'dominio_dato', '')),
            'unidad_medida': _txt(getattr(v, 'unidad_medida', '')),
            'tipo_variable': _txt(getattr(v, 'tipo_variable_estadistica', '')),
            'fuente_datos': _txt(getattr(v, 'fuente_datos', '')),
            'periodicidad': _txt(getattr(v, 'periodicidad', '')),
            'observaciones': _txt(getattr(v, 'observaciones', '')),
            'referencias': _txt(getattr(v, 'referencias', '')),
            'organismo_productor': _txt(org),
            'universo': _txt(getattr(v, 'universo', '')),
            'concepto': _txt(getattr(v, 'concepto', '')),
            'pregunta': _txt(getattr(v, 'pregunta', '')),
            'tipo_representacion': _txt(getattr(v, 'tipo_representacion', '')),
            'categoria_estadistica': _txt(getattr(v, 'categoria_estadistica', '')),
            'sello_calidad': _txt(getattr(v, 'sello_calidad', '')),
            'orden': v.orden or i,
        }
        columnas.append(col)
    return columnas


def serialize_conjunto(cd):
    """ConjuntoDatos (+ VariableConjuntoDatos) -> proyecto 'table'.

    La ficha técnica de las variables va embebida como
    ``table_description.table_columns`` — el tipo table del editor no
    tiene subsistema de datafiles/variables."""
    idno = f'SIIED-CD-{cd.pk}'
    prod = _txt(getattr(cd, 'organismo_productor', '') or getattr(cd, 'productor_legado', ''))
    contacto = []
    cnombre = _txt(getattr(cd, 'contacto_nombre', ''))
    cemail = _txt(getattr(cd, 'contacto_email', ''))
    if cnombre or cemail:
        contacto.append({'name': cnombre, 'email': cemail})
    columnas = serialize_conjunto_variables(cd)
    return 'table', idno, {
        'metadata_information': {
            'idno': idno,
            'title': _txt(cd.nombre),
            'producers': _names(prod),
            'production_date': _year(getattr(cd, 'fecha_carga', None)),
            'version': _txt(getattr(cd, 'version', '')),
        },
        'table_description': {
            'title_statement': {
                'idno': _txt(getattr(cd, 'identificador', '')) or idno,
                'title': _txt(cd.nombre),
                'alternate_title': _txt(getattr(cd, 'doi_citacion', '')),
            },
            'authoring_entity': _names(prod),
            'publisher': _names(getattr(cd, 'distribuidor', '')),
            'date_published': _year(getattr(cd, 'fecha_carga', None)),
            'version': _txt(getattr(cd, 'version', '')),
            'description': _txt(cd.descripcion),
            # Variables del conjunto: ficha técnica completa como
            # columnas de la tabla (el tipo table no usa datafiles)
            'table_columns': columnas,
            'table_rows': [{'label': _txt(getattr(cd, 'unidad_analisis', ''))}]
                          if getattr(cd, 'unidad_analisis', '') else [],
            'universe': [{'value': _txt(cd.universo)}]
                        if getattr(cd, 'universo', '') else [],
            'unit_observation': [{'value': _txt(getattr(cd, 'unidad_analisis', ''))}]
                                if getattr(cd, 'unidad_analisis', '') else [],
            'data_sources': ([{'name': _txt(getattr(cd, 'operacion', None) and cd.operacion.nombre),
                               'source_id': f'SIIED-OPE-{cd.operacion_id}'}]
                             if getattr(cd, 'operacion_id', None) else []),
            'time_periods': ([{'from': _txt(cd.periodo_campo_inicio),
                              'to': _txt(cd.periodo_campo_fin)}]
                             if getattr(cd, 'periodo_campo_inicio', None) else []),
            'contacts': contacto,
            'notes': ([{'note': _txt(cd.notas_procesamiento)}]
                      if getattr(cd, 'notas_procesamiento', '') else []),
        },
        'tags': [{'tag': t} for t in _txt(
            getattr(cd, 'palabras_clave', '')).split(',') if t.strip()],
        'additional': {
            'identificador': _txt(getattr(cd, 'identificador', '')),
            'doi_citacion': _txt(getattr(cd, 'doi_citacion', '')),
            'idioma': _txt(getattr(cd, 'idioma', '') or 'es'),
            'financiamiento': _txt(getattr(cd, 'financiamiento', '')),
            'cobertura_geografica': _txt(getattr(cd, 'cobertura_geografica', '') or 'Santiago de Cali, Colombia'),
            'cobertura_temporal': _txt(getattr(cd, 'cobertura_temporal', '')),
            'tipo_estudio': _txt(getattr(cd, 'tipo_estudio', '')),
            'metodo_muestreo': _txt(getattr(cd, 'metodo_muestreo', '')),
            'modo_coleccion': _txt(getattr(cd, 'modo_coleccion', '')),
            'instrumento': _txt(getattr(cd, 'instrumento', '')),
            'ponderacion': _txt(getattr(cd, 'ponderacion', '')),
            'condiciones_acceso': _txt(getattr(cd, 'condiciones_acceso', '')),
            'derechos_uso': _txt(getattr(cd, 'derechos_uso', '')),
            'confidencialidad': _txt(getattr(cd, 'confidencialidad', '')),
            'unidad_analisis': _txt(getattr(cd, 'unidad_analisis', '')),
        },
    }


def serialize_indicador(ind):
    """Indicador -> proyecto indicator (SDMX/MSD)."""
    idno = f'SIIED-IND-{ind.pk}'
    org = _txt(getattr(ind, 'organismo_responsable', '') or getattr(ind, 'entidad_responsable_legado', ''))
    return 'indicator', idno, {
        # El tipo 'indicator' resuelve a schema 'timeseries': el editor
        # deriva el título desde series_description.name
        'series_description': {
            'idno': idno,
            'name': _txt(ind.nombre),
            'database_id': _txt(getattr(ind, 'codigo_indicador', '')),
            'abbreviation': _txt(getattr(ind, 'sigla', '')),
            # MSD 2.x en claves del schema timeseries
            'authoring_entity': [{
                'name': org,
                'affiliation': _txt(getattr(getattr(ind, 'suborganismo', None), 'nombre', '')),
                'email': _txt(getattr(ind, 'correo_contacto', '')),
            }] if org else [],
            'definition_long': _txt(getattr(ind, 'descripcion_indicador', '')),
            'statistical_concept': _txt(getattr(ind, 'metodo_medicion', '')),
            'measurement_unit': _txt(getattr(ind, 'unidad_medida', '')),
            'universe': _txt(getattr(ind, 'poblacion_objetivo', '')),
            'periodicity': _txt(getattr(ind, 'frecuencia_difusion', '')),
            'base_period': _txt(getattr(ind, 'periodo_base', '')),
            'data_collection': {
                'data_source': _txt(getattr(ind, 'fuente_datos', '')),
                'period': _txt(getattr(ind, 'periodo_referencia', '')),
            },
            'definition_references': ([{
                'source': _txt(ind.referencias),
            }] if getattr(ind, 'referencias', '') else []),
        },
        'data_notes': {
            'note': _txt(getattr(ind, 'comentarios_adicionales', '')),
        },
        # Campos MSD sin clave propia en el schema -> additional
        'additional': {
            'grupo_indicador': _txt(getattr(ind, 'grupo_indicador', '')),
            'clasificacion': _txt(getattr(ind, 'subtema', '') and str(ind.subtema)),
            'objetivo': _txt(getattr(ind, 'objetivo', '')),
            'formula': _txt(getattr(ind, 'formula_ficha', '')),
            'variables_descripcion': _txt(getattr(ind, 'variables', '')),
            'operacion_estadistica': _txt(getattr(getattr(ind, 'operacion', None), 'nombre', '')),
            'conjunto_datos': _txt(getattr(ind, 'nombre_conjunto_datos', '')),
            'nomenclaturas_clasificaciones': _txt(
                getattr(ind, 'nomenclaturas_clasificaciones', '')),
            'alcance_tematico': _txt(getattr(ind, 'alcance_tematico', '')),
            'cobertura_geografica': _txt(getattr(ind, 'cobertura_geografica', '')),
            'serie_historica_disponible': _txt(
                getattr(ind, 'serie_historica_disponible', '')),
            'medios_difusion': _txt(getattr(ind, 'medios_difusion', '')),
            'telefono_contacto': _txt(getattr(ind, 'telefono_contacto', '')),
            'equipo_responsable': _txt(getattr(
                getattr(ind, 'equipo_responsable', None), 'nombre', '')),
            'responsable_validacion': {
                'nombre': _txt(getattr(ind, 'nombre_responsable_validacion', '')),
                'cargo': _txt(getattr(ind, 'cargo_responsable_validacion', '')),
                'correo': _txt(getattr(ind, 'correo_responsable_validacion', '')),
                'celular': _txt(getattr(ind, 'celular_responsable_validacion', '')),
            },
        },
        'metadata_information': {
            'title': _txt(ind.nombre),
            'idno': idno,
            'producers': _names(org),
            'production_date': _year(getattr(ind, 'fecha_publicacion_metadatos', None)),
        },
        'database_description': {
            'title_statement': {
                'idno': idno,
                'title': _txt(ind.nombre),
                'sub_title': _txt(getattr(ind, 'sigla', '')),
                'identifiers': ([{'identifier': _txt(ind.codigo_indicador), 'type': 'codigo'}]
                                if getattr(ind, 'codigo_indicador', '') else []),
            },
            'authoring_entity': _names(org),
            'abstract': _txt(getattr(ind, 'descripcion_indicador', '') or getattr(ind, 'objetivo', '')),
            'update_frequency': _txt(getattr(ind, 'frecuencia_difusion', '')),
            'keywords': _keywords(getattr(ind, 'subtema', '') or getattr(ind, 'alcance_tematico', '')),
            'themes': _names(getattr(ind, 'alcance_tematico', '')),
        },
        'indicator_metadata': {
            'methodology': _txt(getattr(ind, 'metodo_medicion', '')),
            'formula': _txt(getattr(ind, 'formula_ficha', '')),
            'unit_of_measure': _txt(getattr(ind, 'unidad_medida', '')),
            'data_source': _txt(getattr(ind, 'fuente_datos', '')),
            'geographic_coverage': _txt(getattr(ind, 'cobertura_geografica', '')),
            'reference_period': _txt(getattr(ind, 'periodo_referencia', '')),
            'base_period': _txt(getattr(ind, 'periodo_base', '')),
            'objective': _txt(getattr(ind, 'objetivo', '')),
            'references': _txt(getattr(ind, 'referencias', '')),
            'classification': _txt(getattr(ind, 'nomenclaturas_clasificaciones', '')),
            'comments': _txt(getattr(ind, 'comentarios_adicionales', '')),
        },
    }


def serialize_fuente(f):
    """FuenteDatos (taller) -> proyecto document (Dublin Core + DDI)."""
    idno = f'SIIED-FTE-{f.pk}'
    org = ''
    insc = getattr(f, 'inscripcion', None)
    if insc is not None:
        org = _txt(getattr(getattr(insc, 'organismo', None), 'nombre', '') or getattr(insc, 'organismo', ''))
    return 'document', idno, {
        'metadata_information': {
            'title': _txt(f.nombre),
            'idno': idno,
            'producers': _names(org),
        },
        'document_description': {
            'title_statement': {'idno': idno, 'title': _txt(f.nombre)},
            'authors': [{'first_name': org}] if org else [],
            'date_created': _txt(getattr(f, 'fecha_inicio', ''))[:10],
            'description': _txt(getattr(f, 'descripcion', '')),
            'type': 'dataset',
            'publishers': _names(org),
            'coverage': 'Santiago de Cali, Colombia',
            'languages': [{'name': 'Español', 'code': 'es'}],
            'tags': [{'tag': _txt(getattr(f, 'capa', ''))}] if getattr(f, 'capa', '') else [],
        },
        'dublin_core': {
            'title': _txt(f.nombre),
            'creator': org,
            'description': _txt(getattr(f, 'descripcion', '')),
            'type': 'Dataset',
            'coverage': 'Santiago de Cali, Colombia',
        },
    }


def _contactos(op):
    """Contactos DDI para una operación estadística."""
    contactos = []
    for nombre, correo in (
        (getattr(op, 'nombre_coordinador', ''), getattr(op, 'correo_coordinador', '')),
        (getattr(op, 'nombre_tematico', ''), getattr(op, 'correo_tematico', '')),
    ):
        if nombre or correo:
            contactos.append({'name': _txt(nombre), 'email': _txt(correo)})
    return contactos
