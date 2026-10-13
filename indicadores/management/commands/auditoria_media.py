"""Auditoría de sincronía entre la base y MEDIA_ROOT.

Recorre todos los FileField/ImageField de los modelos y cruza las
rutas que la base referencia con los archivos que hay en disco.
Pensado para correr tras restaurar un dump (o en producción):

    python manage.py auditoria_media
    python manage.py auditoria_media --csv /tmp/auditoria.csv

Solo lee: no toca ni la base ni el disco.
"""
import csv
import os

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models

# Prefijos que NO son contenido de la base: temporales de wizards y
# dumps soltados dentro de media/
TEMPORAL = ('wizard_temp/', '_geo_wizard/', 'tmp/')


def es_temporal(p):
    return p.startswith(TEMPORAL) or p.endswith('.psql.bin')


class Command(BaseCommand):
    help = 'Cruza las rutas de archivos que la base referencia con ' \
           'los archivos presentes en MEDIA_ROOT'

    def add_arguments(self, parser):
        parser.add_argument('--csv', metavar='RUTA',
                            help='exporta el detalle completo a CSV')
        parser.add_argument('--dirs', action='store_true',
                            help='agrupa los faltantes por carpeta de 1er nivel')

    def handle(self, *args, **opts):
        # 1) Todas las rutas que la base referencia, con quién las pide
        refs = {}
        for m in apps.get_models():
            for f in m._meta.get_fields():
                if not isinstance(f, models.FileField):
                    continue
                qs = (m.objects
                        .exclude(**{f.name: ''})
                        .exclude(**{f.name + '__isnull': True})
                        .values_list(f.name))
                for (v,) in qs:
                    if v:
                        refs.setdefault(v, set()).add(
                            f'{m._meta.label}.{f.name}')

        # 2) Todo lo que hay en MEDIA_ROOT
        mr = str(settings.MEDIA_ROOT)
        en_disco = set()
        for root, _dirs, files in os.walk(mr):
            for fn in files:
                en_disco.add(os.path.relpath(os.path.join(root, fn), mr))

        refs_ok = {p for p in refs if not es_temporal(p)}
        disk_ok = {p for p in en_disco if not es_temporal(p)}
        faltan = sorted(refs_ok - disk_ok)
        huerf = sorted(disk_ok - refs_ok)

        self.stdout.write(
            f'MEDIA_ROOT: {mr}\n'
            f'referencias en BD: {len(refs_ok)} | archivos en disco: '
            f'{len(disk_ok)}\n'
            f'FALTAN EN DISCO: {len(faltan)} | HUÉRFANOS: {len(huerf)}')

        if opts['dirs']:
            from collections import Counter
            c = Counter(p.split('/')[0] for p in faltan)
            self.stdout.write('\n--- faltantes por carpeta ---')
            for d, n in c.most_common():
                self.stdout.write(f'  {n:5d}  {d}/')

        lim = 40
        self.stdout.write(f'\n--- faltan en disco (muestra {lim}) ---')
        for p in faltan[:lim]:
            self.stdout.write('  - %s  <- %s' % (p, ', '.join(sorted(refs[p]))))
        if len(faltan) > lim:
            self.stdout.write(f'  … y {len(faltan) - lim} más')

        self.stdout.write(f'\n--- huérfanos en disco (muestra {lim}) ---')
        for p in huerf[:lim]:
            self.stdout.write('  - %s' % p)
        if len(huerf) > lim:
            self.stdout.write(f'  … y {len(huerf) - lim} más')

        if opts['csv']:
            with open(opts['csv'], 'w', newline='') as fh:
                w = csv.writer(fh)
                w.writerow(['estado', 'ruta', 'referencias'])
                for p in faltan:
                    w.writerow(['falta_en_disco', p,
                                '; '.join(sorted(refs[p]))])
                for p in huerf:
                    w.writerow(['huerfano', p, ''])
            self.stdout.write(f'\nDetalle completo en {opts["csv"]}')
