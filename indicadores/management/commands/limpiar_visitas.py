# -*- coding: utf-8 -*-
"""Limpia y normaliza el histórico de PageVisit.

Dos operaciones sobre el histórico acumulado:

1. BORRADO: elimina registros que nunca debieron contarse
   (llamados internos a APIs AJAX, estáticos, admin, monitoring,
   favicons colados, sondas de bots como /.well-known/traffic-advice,
   apple-touch-icon, wp-*, etc.).

2. NORMALIZACIÓN + CATEGORÍA: reescribe `path` en forma canónica
   (minúsculas, sin slash final, sin '//') y asigna `categoria`
   (pagina | api | mcp) usando la misma lógica del middleware.

Uso:
    python manage.py limpiar_visitas             # aplica todo
    python manage.py limpiar_visitas --dry-run   # solo reporta
"""
import re

from django.core.management.base import BaseCommand

from indicadores.middleware import _categoria_visita, _normalizar_path
from indicadores.models import PageVisit


class Command(BaseCommand):
    help = 'Limpia el histórico de visitas: borra URLs internas/ruido, ' \
           'normaliza paths y asigna categoría (pagina/api/mcp).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra qué se haría sin tocar la base de datos.')
        parser.add_argument(
            '--batch', type=int, default=2000,
            help='Tamaño de lote para updates de normalización.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        total = PageVisit.objects.count()
        self.stdout.write(f'Registros actuales: {total}')

        # ---------- 1) BORRADO de ruido ----------
        # Prefijos de rutas internas/no registrables (se compara contra
        # el path normalizado en minúsculas).
        borrables = 0
        vistos = set()

        # Primero: todo lo que la clasificadora marcaría como None.
        for v in PageVisit.objects.values_list('id', 'path').iterator():
            if _categoria_visita(_normalizar_path(v[1])) is None:
                vistos.add(v[0])
        borrables = len(vistos)

        self.stdout.write(
            f'A borrar (URLs internas/ruido): {borrables}')

        if not dry and vistos:
            # Borrado en lotes para no hacer un DELETE gigante
            ids = list(vistos)
            for i in range(0, len(ids), 5000):
                PageVisit.objects.filter(
                    id__in=ids[i:i + 5000]).delete()
            self.stdout.write(self.style.SUCCESS(
                f'  ✔ {borrables} registros eliminados'))
        elif dry:
            # Muestra de lo que se borraría
            muestra = list(
                PageVisit.objects
                .filter(id__in=list(vistos)[:15])
                .values_list('path', flat=True))
            for p in muestra:
                self.stdout.write(f'  ✗ {p}')

        # ---------- 2) NORMALIZACIÓN + CATEGORÍA ----------
        cambios_path = 0
        cambios_cat = 0
        actualizar = []
        for v in (PageVisit.objects
                  .exclude(id__in=vistos)
                  .values_list('id', 'path', 'categoria')
                  .iterator()):
            norm = _normalizar_path(v[1])
            cat = _categoria_visita(norm) or PageVisit.Categoria.PAGINA
            if norm != v[1]:
                cambios_path += 1
            if cat != v[2]:
                cambios_cat += 1
            if not dry and (norm != v[1] or cat != v[2]):
                actualizar.append(
                    PageVisit(id=v[0], path=norm, categoria=cat))
                if len(actualizar) >= options['batch']:
                    PageVisit.objects.bulk_update(
                        actualizar, ['path', 'categoria'])
                    actualizar = []

        self.stdout.write(
            f'A normalizar: {cambios_path} paths | '
            f'a recategorizar: {cambios_cat} registros')
        if not dry and actualizar:
            PageVisit.objects.bulk_update(actualizar, ['path', 'categoria'])
            self.stdout.write(self.style.SUCCESS(
                f'  ✔ {cambios_path} paths normalizados, '
                f'{cambios_cat} categorías asignadas'))

        if dry:
            self.stdout.write(self.style.WARNING(
                'Dry-run: no se modificó nada.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Listo. Registros restantes: {PageVisit.objects.count()}'))
