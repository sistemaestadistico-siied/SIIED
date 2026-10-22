"""Importa las Operaciones Estadísticas desde el catálogo NADA (ADDA)
hacia OpenMetadata Editor como proyectos microdata con su DDI real.

El inventario SIIED ya no genera estos proyectos: el metadato
authoritative de las OOEE vive en ADDA (documentado con plantillas
DANE/IHSN). Este comando descarga el DDI de cada estudio vía la API de
NADA y lo importa al editor (upsert por idno), asignándolo a la
colección 'Operaciones Estadísticas'.

Configuración (settings o env):
    ADDA_BASE_URL  default https://planestadistico.cali.gov.co/amda
    ADDA_API_KEY   API key de un usuario admin del NADA remoto
                   (si no se define, se toma la primera conexión
                   registrada en `editor_catalogs` del editor vía
                   settings.OM_EDITOR_MYSQL_DSN o la BD configurada
                   en OPENMETADATA)

Uso:
    python manage.py pull_adda_operaciones                # todo
    python manage.py pull_adda_operaciones --dry-run      # solo lista
    python manage.py pull_adda_operaciones --ps 10        # primeras 10
"""

import os

import requests
import urllib3
from django.conf import settings
from django.core.management.base import BaseCommand

from indicadores.om_sync import OMClient, COLLECTIONS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ADDA_BASE = getattr(
    settings, 'ADDA_BASE_URL',
    os.environ.get(
        'ADDA_BASE_URL',
        'https://planestadistico.cali.gov.co/amda'))


def _adda_api_key():
    """API key de ADDA: env/settings, o la primera conexión de
    `editor_catalogs` (la registrada en el editor)."""
    key = getattr(settings, 'ADDA_API_KEY', None) or \
        os.environ.get('ADDA_API_KEY')
    if key:
        return key
    try:
        import subprocess
        out = subprocess.check_output([
            'mysql', '-ueditor_user', '-pEditorLocal2026!',
            'metadata_editor', '-sN', '-e',
            'select api_key from editor_catalogs limit 1'])
        key = out.decode().strip()
        if key:
            return key
    except Exception:
        pass
    raise RuntimeError(
        'Sin API key de ADDA: defina ADDA_API_KEY o registre una '
        'catalog connection en el editor')


class Command(BaseCommand):
    help = 'Importa las OOEE desde ADDA (NADA) al OM Editor'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--ps', type=int, default=200,
                            help='page size del catálogo')
        parser.add_argument('--collection-id', type=int, default=None,
                            help='id de colección destino en el editor')

    def handle(self, *args, **opts):
        base = ADDA_BASE.rstrip('/') + '/index.php/api'
        h = {'X-API-KEY': _adda_api_key()}
        client = OMClient()

        # colección destino
        collection_id = opts['collection_id'] or client.ensure_collection(
            COLLECTIONS['operaciones'])
        self.stdout.write(
            f'colección destino: {collection_id}')

        # listar catálogo ADDA
        r = requests.get(f'{base}/catalog/search',
                         params={'ps': opts['ps'], 'offset': 0},
                         headers=h, timeout=60, verify=False)
        result = r.json().get('result', {})
        rows = result.get('rows', [])
        self.stdout.write(f'ADDA: {result.get("found")} estudios, '
                          f'importando {len(rows)}')

        ok, errs = 0, []
        for row in rows:
            idno = row['idno']
            if opts['dry_run']:
                self.stdout.write(f'  DRY {idno} {row.get("title", "")[:60]}')
                ok += 1
                continue
            try:
                d = requests.get(f'{base}/catalog/{idno}/ddi',
                                 headers=h, timeout=90,
                                 verify=False).json()
                ds = d.get('dataset')
                if not ds or 'metadata' not in ds:
                    errs.append((idno, 'respuesta sin dataset.metadata'))
                    continue
                metadata = dict(ds['metadata'])
                client.upsert_project(
                    'microdata', idno, metadata, collection_id)
                ok += 1
            except Exception as e:
                errs.append((idno, str(e)[:120]))

        for idno, e in errs:
            self.stderr.write(f'  {idno}: {e}')
        self.stdout.write(self.style.SUCCESS(
            f'{ok} importados, {len(errs)} errores'))
