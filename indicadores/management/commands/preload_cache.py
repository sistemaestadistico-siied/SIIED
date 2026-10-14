"""
Management command to preload cache for popular indicators and improve system performance.
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.test import RequestFactory
from django.conf import settings
from django.db import models
from indicadores.models import Indicador, Dato
from indicadores.views import get_graficos, get_desagregaciones, get_mapa, geojson_indicador
from indicadores.cache_utils import get_cached_indicadores_by_subtema, get_cached_desagregaciones
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Preload cache for popular indicators to improve performance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--indicators',
            nargs='+',
            type=int,
            help='Specific indicator IDs to preload (default: all active indicators)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Limit number of indicators to preload (default: 10)',
        )
        parser.add_argument(
            '--clear-first',
            action='store_true',
            help='Clear cache before preloading',
        )

    def handle(self, *args, **options):
        if options['clear_first']:
            self.stdout.write('Clearing cache...')
            cache.clear()
            self.stdout.write(self.style.SUCCESS('Cache cleared'))

        # Get indicators to preload
        if options['indicators']:
            indicadores = Indicador.objects.filter(
                id__in=options['indicators'],
                activo=True
            )
        else:
            # Get most popular indicators (those with most data points)
            indicadores = Indicador.objects.filter(activo=True).annotate(
                dato_count=models.Count('datos')
            ).order_by('-dato_count')[:options['limit']]

        factory = RequestFactory()
        preloaded_count = 0

        for indicador in indicadores:
            self.stdout.write(f'Preloading cache for indicator {indicador.id}: {indicador.nombre}')
            
            try:
                # Preload basic indicator data (subtema principal + adicionales)
                get_cached_indicadores_by_subtema(indicador.subtema_id)
                for st_id in indicador.subtemas_adicionales.values_list('id', flat=True):
                    get_cached_indicadores_by_subtema(st_id)
                get_cached_desagregaciones(indicador.id)
                
                # Preload API endpoints with common parameters
                self._preload_graficos(factory, indicador.id)
                self._preload_desagregaciones(factory, indicador.id)
                self._preload_mapa(factory, indicador.id)
                self._preload_geojson(factory, indicador.id)
                
                preloaded_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Cached indicator {indicador.id}')
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Error caching indicator {indicador.id}: {e}')
                )
                logger.error(f'Error preloading cache for indicator {indicador.id}: {e}')

        self.stdout.write(
            self.style.SUCCESS(f'Cache preloading completed. {preloaded_count} indicators cached.')
        )

    def _preload_graficos(self, factory, indicador_id):
        """Preload graficos endpoint with common filter combinations"""
        # Basic request without filters
        request = factory.get(f'/api/get_graficos/{indicador_id}/')
        get_graficos(request, indicador_id)
        
        # Get recent years for this indicator
        recent_years = Dato.objects.filter(
            indicador_id=indicador_id
        ).values_list('fecha_dato__year', flat=True).distinct().order_by('-fecha_dato__year')[:3]
        
        # Preload with year filters
        for year in recent_years:
            request = factory.get(f'/api/get_graficos/{indicador_id}/?ano_inicio={year}&ano_fin={year}')
            get_graficos(request, indicador_id)

    def _preload_desagregaciones(self, factory, indicador_id):
        """Preload desagregaciones endpoint"""
        request = factory.get(f'/api/get_desagregaciones/{indicador_id}/')
        get_desagregaciones(request, indicador_id)

    def _preload_mapa(self, factory, indicador_id):
        """Preload mapa endpoint"""
        try:
            request = factory.get(f'/api/get_mapa/{indicador_id}/')
            get_mapa(request, indicador_id)
        except Exception:
            # Not all indicators have maps, skip silently
            pass

    def _preload_geojson(self, factory, indicador_id):
        """Preload geojson endpoint"""
        try:
            request = factory.get(f'/api/geojson/indicador/{indicador_id}/')
            geojson_indicador(request, indicador_id)
        except Exception:
            # Not all indicators have geographic data, skip silently
            pass
