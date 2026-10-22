"""Sincroniza los conjuntos de metadatos del SIIED hacia OpenMetadata.

A diferencia de ``sync_om`` (Metadata Editor/NADA, solo OEs
consolidadas), este comando cataloga los activos del inventario en el
catálogo vivo — ver docs/ARQUITECTURA_OPENMETADATA_Y_NADA.md.

Uso:
    python manage.py sync_openmetadata --dry-run
    python manage.py sync_openmetadata --set fuentes --limit 5
    python manage.py sync_openmetadata            # todos los sets
"""

from django.core.management.base import BaseCommand

from indicadores.models import ConjuntoDatos, Indicador, OperacionEstadistica
from indicadores.models_catalogo import BaseCatalogo, FuenteDatos
from indicadores import openmetadata_sync as om

SETS = {
    'fuentes': {
        'kind': 'table',
        'serialize': om.ser_fuente,
        'queryset': lambda: FuenteDatos.objects
            .select_related('inscripcion__organismo')
            .prefetch_related('variables').order_by('id'),
    },
    'bases': {
        'kind': 'table',
        'serialize': om.ser_base,
        'queryset': lambda: BaseCatalogo.objects
            .filter(activa=True).prefetch_related('campos').order_by('id'),
    },
    'conjuntos': {
        'kind': 'table',
        'serialize': om.ser_conjunto,
        'queryset': lambda: ConjuntoDatos.objects
            .prefetch_related('variables').order_by('id'),
    },
    'operaciones': {
        'kind': 'table',
        'serialize': om.ser_operacion,
        'queryset': lambda: OperacionEstadistica.objects
            .filter(activo=True).order_by('id'),
    },
    'indicadores': {
        'kind': 'dashboard',
        'serialize': om.ser_indicador,
        'queryset': lambda: Indicador.objects
            .filter(activo=True)
            .select_related('subtema__tema__dominio').order_by('id'),
    },
}


class Command(BaseCommand):
    help = 'Sincroniza conjuntos de metadatos del SIIED hacia OpenMetadata'

    def add_arguments(self, parser):
        parser.add_argument(
            '--set', choices=list(SETS) + ['all'], default='all')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        keys = list(SETS) if opts['set'] == 'all' else [opts['set']]
        client = None if opts['dry_run'] else om.OMClient()

        if client:
            client.login()
            client.ensure_infra()
            self.stdout.write('Infraestructura OM lista '
                              f'(servicio {om.SERVICE}, '
                              f'{len(om.DATABASES)} databases, tags capa).')

        for key in keys:
            cfg = SETS[key]
            ok = err = 0
            qs = cfg['queryset']()
            if opts['limit']:
                qs = qs[:opts['limit']]
            for obj in qs:
                try:
                    if cfg['kind'] == 'table':
                        db, nombre, desc, cols, tags = cfg['serialize'](obj)
                        if client:
                            fq, _ = client.put_table(
                                db, nombre, desc, cols, tags,
                                key=str(obj.pk))
                            self.stdout.write(f'  {fq} ({len(cols)} cols)')
                        else:
                            self.stdout.write(
                                f'  DRY {om.SERVICE}.{db}.public.'
                                f'{om._slug(nombre)} ({len(cols)} cols, '
                                f'tags={tags})')
                    else:
                        nombre, desc, url = cfg['serialize'](obj)
                        if client:
                            fq, _ = client.put_dashboard(
                                nombre, desc, url, key=str(obj.pk))
                            self.stdout.write(f'  {fq}')
                        else:
                            self.stdout.write(
                                f'  DRY {om.DASH_SERVICE}.'
                                f'{om._slug(nombre)}')
                    ok += 1
                except Exception as e:
                    err += 1
                    self.stderr.write(f'  [{key}] #{obj.pk}: {e}')
            self.stdout.write(self.style.SUCCESS(
                f'[{key}] {ok} ok, {err} errores'))
