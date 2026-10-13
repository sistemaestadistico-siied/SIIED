#!/usr/bin/env python3
"""
Audita (y opcionalmente desactiva) subtemas que son en realidad items del
catálogo Cali en Cifras: nombres con prefijo numérico tipo '6.1.1
Licencias expedidas por usos'.

Origen del problema: `cargar_indicadores_masivo` crea un MenuSubtema nuevo
cuando la columna 'subtema' del CSV no coincide con una existente. Si el
CSV del CEC traía el nombre del listado numerado como subtema (o el tema
hizo match parcial con un tema real, ej. 'Construcción'), los items del
catálogo quedaron registrados como subtemas y `tema_detalle` los muestra
mezclados con los subtemas reales del dominio.

Uso — primero auditar (dry-run por defecto, no toca la BD):
    python manage.py auditar_subtemas_cec

    python manage.py auditar_subtemas_cec --patron '^\\d+\\.\\d+'
    python manage.py auditar_subtemas_cec --tema construccion

Desactivar los hallados (activo=False, reversible, NUNCA borra):
    python manage.py auditar_subtemas_cec --desactivar

Nota: Indicador.subtema es FK CASCADE — por eso se desactiva y no se
elimina. Los indicadores que cuelguen de un subtema desactivado dejan de
verse en el dominio; revísalos antes con el reporte del dry-run.
"""

import re

from django.core.management.base import BaseCommand
from django.db.models import Count


class Command(BaseCommand):
    help = 'Audita subtemas con nombre numerado tipo catálogo CEC y los desactiva opcionalmente'

    def add_arguments(self, parser):
        parser.add_argument(
            '--patron', type=str, default=r'^\d+(\.\d+)+\s',
            help='Regex sobre el nombre del subtema (default: numeración tipo 6.1.1)',
        )
        parser.add_argument(
            '--tema', type=str, default='',
            help='Filtrar por slug/nombre de tema (icontains)',
        )
        parser.add_argument(
            '--desactivar', action='store_true',
            help='Marcar activo=False en los subtemas hallados (default: solo reporta)',
        )

    def handle(self, *args, **options):
        from indicadores.models import MenuSubtema

        patron = re.compile(options['patron'])
        qs = (
            MenuSubtema.objects
            .select_related('tema__dominio')
            .annotate(n_indicadores=Count('indicadores'))
            .order_by('tema__dominio__nombre', 'tema__nombre', 'nombre')
        )
        if options['tema']:
            from django.db.models import Q
            qs = qs.filter(
                Q(tema__slug__icontains=options['tema']) |
                Q(tema__nombre__icontains=options['tema'])
            )

        hallados = [st for st in qs if patron.match(st.nombre or '')]

        self.stdout.write(self.style.WARNING(
            f"Patrón: /{options['patron']}/ — {len(hallados)} subtema(s) sospechosos"
        ))
        self.stdout.write('-' * 72)

        sin_indicadores = 0
        con_indicadores = 0
        for st in hallados:
            ruta = f"{st.tema.dominio.nombre} > {st.tema.nombre}"
            marca = '' if st.activo else ' [YA INACTIVO]'
            self.stdout.write(
                f"  {ruta} :: «{st.nombre}» (id={st.id}, slug={st.slug}, "
                f"{st.n_indicadores} indicador(es)){marca}"
            )
            if st.n_indicadores:
                con_indicadores += 1
            else:
                sin_indicadores += 1

        self.stdout.write('-' * 72)
        self.stdout.write(
            f"Total: {len(hallados)} | con indicadores colgando: {con_indicadores} | "
            f"vacíos: {sin_indicadores}"
        )

        if not options['desactivar']:
            self.stdout.write(self.style.NOTICE(
                'DRY-RUN: nada se modificó. Reejecuta con --desactivar para ocultarlos.'
            ))
            return

        n = 0
        for st in hallados:
            if st.activo:
                st.activo = False
                st.save(update_fields=['activo'])
                n += 1
        self.stdout.write(self.style.SUCCESS(
            f'{n} subtema(s) desactivados (activo=False). '
            'Reversible desde el admin. Los indicadores asociados quedan ocultos '
            'junto al subtema — reasigna los que deban conservarse.'
        ))
