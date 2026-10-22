"""Sincroniza conjuntos de metadatos del SIIED hacia el Metadata Editor (NADA).

Arquitectura acordada (ver docs/ARQUITECTURA_OPENMETADATA_Y_NADA.md):
al Metadata Editor/NADA solo llegan **Operaciones Estadísticas**
consolidadas (tipo ``microdata``, DDI). Fuentes, conjuntos e indicadores
son activos del catálogo vivo y se catalogan en **OpenMetadata**, no en
NADA.

La dirección principal para OEs es **pull** (ADDA/NADA -> inventario
SIIED). El push desde SIIED queda desactivado: recrear proyectos skeleton
pisaba los DDI reales importados desde ADDA.

Uso:
    python manage.py sync_om --set operaciones --dry-run
"""

from django.core.management.base import BaseCommand

# Al reactivar un set, reimportar:
#   from indicadores.models import (
#       OperacionEstadistica, ConjuntoDatos, Indicador, FuenteDatos)
#   from indicadores import om_sync

SETS = {
    # 'operaciones': desactivado en push — las OOEE se importan desde
    # ADDA (NADA) con sus DDI reales; sincronizar skeletons las pisaba.
    # Se reactivará cuando una OE del ciclo taller->gold requiera crear
    # su DDI en el editor.
    # 'operaciones': {
    #     'collection': om_sync.COLLECTIONS['operaciones'],
    #     'queryset': lambda: OperacionEstadistica.objects.filter(
    #         activo=True).order_by('id'),
    #     'serialize': om_sync.serialize_operacion,
    # },

    # Retirados del sync a NADA — pasan a OpenMetadata como activos del
    # catálogo vivo (tables, data products, glossary, certifications):
    # 'conjuntos':   serialize_conjunto
    # 'indicadores': serialize_indicador
    # 'fuentes':     serialize_fuente
}

KNOWN_SETS = ['operaciones', 'conjuntos', 'indicadores', 'fuentes']


class Command(BaseCommand):
    help = 'Sincroniza conjuntos de metadatos del SIIED hacia el Metadata Editor'

    def add_arguments(self, parser):
        parser.add_argument(
            '--set', choices=KNOWN_SETS + ['all'], default='all')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        keys = KNOWN_SETS if opts['set'] == 'all' else [opts['set']]
        for key in keys:
            if key not in SETS:
                self.stdout.write(
                    f'[{key}] desactivado — ver docstring y '
                    'docs/ARQUITECTURA_OPENMETADATA_Y_NADA.md')
        activos = [k for k in keys if k in SETS]
        if not activos:
            return

        from indicadores import om_sync
        client = om_sync.OMClient()

        for key in activos:
            cfg = SETS[key]
            try:
                collection_id = client.ensure_collection(cfg['collection'])
            except Exception as e:
                self.stderr.write(
                    f'[{key}] no se pudo asegurar la colección: {e}')
                collection_id = None
            if collection_id:
                self.stdout.write(
                    f'[{key}] colección "{cfg["collection"]}" '
                    f'-> {collection_id}')

            ok = err = 0
            qs = cfg['queryset']()
            if opts['limit']:
                qs = qs[:opts['limit']]
            for obj in qs:
                ptype, idno, metadata = cfg['serialize'](obj)
                if opts['dry_run']:
                    self.stdout.write(f'  DRY {ptype} {idno}')
                    ok += 1
                    continue
                try:
                    client.upsert_project(
                        ptype, idno, metadata, collection_id)
                    ok += 1
                    if key == 'conjuntos':
                        # tipo table: variables embebidas en
                        # table_description.table_columns
                        nvars = len(metadata.get('table_description', {})
                                    .get('table_columns', []))
                        self.stdout.write(f'  {idno}: {nvars} variables')
                except Exception as e:
                    err += 1
                    self.stderr.write(f'  [{key}] {idno}: {e}')
            self.stdout.write(self.style.SUCCESS(
                f'[{key}] {ok} sincronizados, {err} errores'))
