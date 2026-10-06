from collections import Counter
from itertools import chain

from django.core.management.base import BaseCommand
from django.db.models import Count, F

from indicadores.models import (
    Dato,
    DominioDesagregacion,
    Grafico,
    GraficoSerie,
    Indicador,
)


def _combos_reales(indicador):
    """
    Devuelve el set de tuplas (ids de desagregación ordenados) de cada
    combinación real presente en los datos del indicador.
    """
    combos = set()
    for dato in (
        Dato.objects.filter(indicador=indicador)
        .prefetch_related('desagregaciones_geograficas', 'desagregaciones_tematicas')
        .iterator(chunk_size=2000)
    ):
        ids = [x.id for x in dato.desagregaciones_geograficas.all()]
        ids += [x.id for x in dato.desagregaciones_tematicas.all()]
        combos.add(tuple(sorted(ids)))
    return combos


def _combo_es_subconjunto(serie_combo, combos_reales):
    """
    ¿Hay AL MENOS un combo real que contenga este combo de serie?
    Soporta series con filtro parcial (solo geo, solo tem) sobre datos
    con varias dimensiones.
    """
    sc = set(serie_combo)
    if not sc:
        return True  # serie sin desags = "Total", siempre válida
    for real in combos_reales:
        if sc.issubset(set(real)):
            return True
    return False


class Command(BaseCommand):
    help = (
        'Limpia GraficoSerie "fantasma" — series cuyo filtro de desagregaciones '
        'no es subconjunto de ninguna combinación real de los datos del indicador. '
        'Por defecto corre en dry-run; usar --apply para escribir. '
        'OPCIONAL: --split-domains analiza macro-dominios y propone sus divisiones '
        'por universo sin aplicar cambios.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Escribir de verdad. Sin esto, solo dry-run.',
        )
        parser.add_argument(
            '--min-series',
            type=int,
            default=50,
            help='Solo procesar gráficos con más de N series (default 50). '
                 'Usa --min-series 1 para incluir todos.',
        )
        parser.add_argument(
            '--grafico',
            type=int,
            default=None,
            help='Procesar solo este ID de gráfico.',
        )
        parser.add_argument(
            '--split-domains',
            action='store_true',
            help='Solo análisis: reporta los macro-dominios y la división '
                 'de universos que haría por indicador (sin tocar BD).',
        )

    def handle(self, *args, **options):
        if options['split_domains']:
            self._analizar_split_dominios()
            return

        grafico_id = options['grafico']
        min_series = options['min_series']
        apply = options['apply']

        qs = Grafico.objects.annotate(n_series=Count('series')).filter(n_series__gt=min_series)
        if grafico_id:
            qs = qs.filter(pk=grafico_id)
        qs = qs.order_by('-n_series')

        self.stdout.write(f'{"DRY-RUN → " if not apply else "APLICANDO → "}gráficos a procesar: {qs.count()} (min_series={min_series})')

        total_previas = total_eliminadas = 0
        for grafico in qs.select_related('indicador'):
            ri, re_, combos = self._procesar_grafico(grafico, apply)
            total_previas += ri
            total_eliminadas += re_

        self.stdout.write(self.style.SUCCESS(
            f'{"DRY-RUN " if not apply else ""}RESUMEN: {total_eliminadas:,} series fantasma de {total_previas:,} '
            f'(restantes: {total_previas-total_eliminadas:,})'
        ))

    def _procesar_grafico(self, grafico, apply):
        series = list(
            GraficoSerie.objects.filter(grafico=grafico)
            .prefetch_related('desagregaciones')
            .only('id', 'nombre_personalizado', 'orden')
        )
        combos_reales = _combos_reales(grafico.indicador)

        borrar_ids = []
        conservar = 0
        for s in series:
            serie_combo = sorted(d.id for d in s.desagregaciones.all())
            # fallback: si no tiene M2M pero sí FKs legacy
            if not serie_combo:
                serie_combo = sorted(x for x in (s.desagregacion_geografica_id, s.desagregacion_tematica_id) if x)
            if _combo_es_subconjunto(serie_combo, combos_reales):
                conservar += 1
            else:
                borrar_ids.append(s.id)

        self.stdout.write(
            f'  g{grafico.pk} ({grafico.indicador.nombre[:50]!r}): '
            f'series={len(series):,} → conservar={conservar:,} borrar={len(borrar_ids):,} | combos reales={len(combos_reales)}'
        )

        if apply and borrar_ids:
            # borrar en chunks para no matar la conexión
            CHUNK = 5000
            for i in range(0, len(borrar_ids), CHUNK):
                GraficoSerie.objects.filter(id__in=borrar_ids[i:i+CHUNK]).delete()
            self.stdout.write(f'    → borradas {len(borrar_ids):,} series')

        return len(series), len(borrar_ids), combos_reales

    # ============ ANÁLISIS DE MACROS-DOMINIOS ============

    def _analizar_split_dominios(self):
        """Propone divisiones de macro-dominios por universo sin tocar BD."""
        self.stdout.write(self.style.WARNING('=== ANÁLISIS DE MACRO-DOMINIOS (sin cambios) ===\n'))

        for dominio in DominioDesagregacion.objects.annotate(n_desag=Count('desagregaciones')).filter(n_desag__gt=50).order_by('-n_desag'):
            campo = 'datos_tematicos' if dominio.tipo == 'tematica' else 'datos_geograficos'
            # indicadores que usan desags de este dominio con datos reales
            uso = Counter()
            for des in dominio.desagregaciones.all():
                inds = getattr(des, campo).values_list('indicador_id', flat=True).distinct()
                for i in set(inds):
                    uso[i] += 1

            if len(uso) < 2:
                self.stdout.write(f'\n{dominio.nombre!r}: mono-universo ({len(uso)} indicador), OK')
                continue

            self.stdout.write(f'\n{dominio.nombre!r} ({dominio.tipo}): {dominio.n_desag} desags, {len(uso)} indicadores')
            for ind_id, ndes in uso.most_common(10):
                ind = Indicador.objects.filter(pk=ind_id).only('nombre').first()
                self.stdout.write(f'    {ind_id:>5} {ind.nombre[:45]!r}: usa {ndes} desags')

            # ¿solapamiento?
            multi = sum(1 for des in dominio.desagregaciones.all()
                        if getattr(des, campo).values_list('indicador_id', flat=True).distinct().count() > 1)
            self.stdout.write(f'    → {multi} desags compartidas por >1 indicador')
            if multi <= 3:
                self.stdout.write(f'    → CANDIDATO A SPLIT (casi todo exclusivo)')
            else:
                self.stdout.write(f'    → revisado: hay {multi} desags compartidas, split más delicado')
