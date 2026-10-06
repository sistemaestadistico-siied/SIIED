"""
Views para el dashboard de monitoreo del sistema de indicadores.
Incluye métricas de caché, rendimiento y estado del sistema.
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.db.models import Count, Avg, Max, Min
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta
import psutil
import time
import json
from .models import Indicador, Dato, Grafico, ProcesoExtraccion, ProcesoLog, PageVisit
from .cache_utils import CacheMetrics


@staff_member_required
def monitoring_dashboard(request):
    """
    Dashboard principal de monitoreo del sistema.
    """
    return render(request, 'indicadores/monitoring/dashboard.html', {
        'page': 'monitoring',
        'title': 'Dashboard de Monitoreo'
    })


@staff_member_required
def api_system_stats(request):
    """
    API para obtener estadísticas del sistema en tiempo real.
    """
    try:
        # Estadísticas de base de datos
        db_stats = {
            'indicadores_activos': Indicador.objects.filter(activo=True).count(),
            'total_datos': Dato.objects.count(),
            'graficos_activos': Grafico.objects.filter(activo=True).count(),
            'procesos_extraccion': ProcesoExtraccion.objects.count(),
        }
        
        # Estadísticas de datos por período
        now = timezone.now()
        last_month = now - timedelta(days=30)
        last_week = now - timedelta(days=7)
        
        data_stats = {
            'datos_ultimo_mes': Dato.objects.filter(fecha_actualizacion__gte=last_month).count(),
            'datos_ultima_semana': Dato.objects.filter(fecha_actualizacion__gte=last_week).count(),
            'ultimo_proceso': ProcesoExtraccion.objects.order_by('-fecha_inicio').first(),
        }
        
        # Estadísticas de sistema
        system_stats = {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent,
            'uptime': time.time() - psutil.boot_time(),
        }
        
        # Estadísticas de caché
        cache_stats = CacheMetrics.get_cache_stats()
        
        return JsonResponse({
            'status': 'success',
            'timestamp': now.isoformat(),
            'database': db_stats,
            'data_activity': data_stats,
            'system': system_stats,
            'cache': cache_stats,
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@staff_member_required
def api_cache_metrics(request):
    """
    API para métricas detalladas del sistema de caché.
    """
    try:
        # Simular métricas de caché (en producción vendría de Redis/Memcached)
        cache_data = {
            'hit_rate': 85.7,  # Porcentaje de cache hits
            'miss_rate': 14.3,  # Porcentaje de cache misses
            'total_keys': 156,  # Número total de claves en caché
            'memory_usage': 45.2,  # MB de memoria utilizada
            'avg_response_time': 0.045,  # Tiempo promedio de respuesta (segundos)
            'popular_endpoints': [
                {'endpoint': '/api/get_graficos/', 'hits': 1250, 'avg_time': 0.032},
                {'endpoint': '/api/get_desagregaciones/', 'hits': 890, 'avg_time': 0.028},
                {'endpoint': '/api/get_mapa/', 'hits': 567, 'avg_time': 0.055},
                {'endpoint': '/api/geojson/indicador/', 'hits': 234, 'avg_time': 0.078},
            ],
            'recent_activity': [
                {'time': '22:15:30', 'action': 'CACHE_HIT', 'key': 'grafico_get_graficos_3_*', 'time_saved': 7.2},
                {'time': '22:14:45', 'action': 'CACHE_SET', 'key': 'desagregaciones_indicador_5', 'size': '2.3KB'},
                {'time': '22:13:12', 'action': 'CACHE_INVALIDATE', 'key': 'indicadores_subtema_*', 'reason': 'data_update'},
                {'time': '22:12:08', 'action': 'CACHE_HIT', 'key': 'geojson_indicador_2_*', 'time_saved': 3.1},
            ]
        }
        
        return JsonResponse({
            'status': 'success',
            'timestamp': timezone.now().isoformat(),
            'metrics': cache_data
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@staff_member_required
def api_data_quality(request):
    """
    API para métricas de calidad de datos y validaciones.
    """
    try:
        # Análisis de calidad de datos
        total_datos = Dato.objects.count()
        
        # Datos con valores nulos o cero
        datos_nulos = Dato.objects.filter(valor_dato__isnull=True).count()
        datos_cero = Dato.objects.filter(valor_dato=0).count()
        
        # Datos por rango de fechas
        current_year = timezone.now().year
        datos_actuales = Dato.objects.filter(fecha_dato__year=current_year).count()
        datos_antiguos = Dato.objects.filter(fecha_dato__year__lt=current_year-5).count()
        
        # Indicadores con pocos datos
        indicadores_pocos_datos = Indicador.objects.annotate(
            num_datos=Count('datos')
        ).filter(num_datos__lt=10, activo=True).count()
        
        # Procesos de extracción recientes
        procesos_exitosos = ProcesoLog.objects.filter(
            estado='completado',
            fecha_inicio__gte=timezone.now() - timedelta(days=7)
        ).count()
        
        procesos_fallidos = ProcesoLog.objects.filter(
            estado='error',
            fecha_inicio__gte=timezone.now() - timedelta(days=7)
        ).count()
        
        quality_metrics = {
            'total_datos': total_datos,
            'datos_nulos': datos_nulos,
            'datos_cero': datos_cero,
            'datos_actuales': datos_actuales,
            'datos_antiguos': datos_antiguos,
            'indicadores_pocos_datos': indicadores_pocos_datos,
            'procesos_exitosos_semana': procesos_exitosos,
            'procesos_fallidos_semana': procesos_fallidos,
            'calidad_score': round(((total_datos - datos_nulos) / total_datos * 100), 2) if total_datos > 0 else 0,
            'validaciones': [
                {
                    'tipo': 'Valores Nulos',
                    'estado': 'warning' if datos_nulos > 0 else 'success',
                    'count': datos_nulos,
                    'descripcion': f'{datos_nulos} registros con valores nulos'
                },
                {
                    'tipo': 'Indicadores Incompletos',
                    'estado': 'error' if indicadores_pocos_datos > 5 else 'warning' if indicadores_pocos_datos > 0 else 'success',
                    'count': indicadores_pocos_datos,
                    'descripcion': f'{indicadores_pocos_datos} indicadores con menos de 10 datos'
                },
                {
                    'tipo': 'Procesos de Extracción',
                    'estado': 'error' if procesos_fallidos > procesos_exitosos else 'success',
                    'count': procesos_exitosos,
                    'descripcion': f'{procesos_exitosos} exitosos, {procesos_fallidos} fallidos esta semana'
                }
            ]
        }
        
        return JsonResponse({
            'status': 'success',
            'timestamp': timezone.now().isoformat(),
            'quality': quality_metrics
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@staff_member_required
def api_performance_trends(request):
    """
    API para tendencias de rendimiento del sistema.
    """
    try:
        # Simular datos de tendencias (en producción vendría de métricas reales)
        days = request.GET.get('days', 7)
        
        # Generar datos simulados para los últimos N días
        trends_data = {
            'response_times': [
                {'date': '2025-01-01', 'avg_time': 0.045, 'max_time': 0.120},
                {'date': '2025-01-02', 'avg_time': 0.038, 'max_time': 0.095},
                {'date': '2025-01-03', 'avg_time': 0.042, 'max_time': 0.110},
                {'date': '2025-01-04', 'avg_time': 0.035, 'max_time': 0.088},
                {'date': '2025-01-05', 'avg_time': 0.040, 'max_time': 0.102},
            ],
            'cache_performance': [
                {'date': '2025-01-01', 'hit_rate': 82.5, 'requests': 1250},
                {'date': '2025-01-02', 'hit_rate': 85.2, 'requests': 1340},
                {'date': '2025-01-03', 'hit_rate': 87.1, 'requests': 1180},
                {'date': '2025-01-04', 'hit_rate': 89.3, 'requests': 1420},
                {'date': '2025-01-05', 'hit_rate': 85.7, 'requests': 1380},
            ],
            'system_resources': [
                {'date': '2025-01-01', 'cpu': 45.2, 'memory': 67.8, 'disk': 23.4},
                {'date': '2025-01-02', 'cpu': 42.1, 'memory': 65.2, 'disk': 23.5},
                {'date': '2025-01-03', 'cpu': 48.7, 'memory': 69.1, 'disk': 23.6},
                {'date': '2025-01-04', 'cpu': 41.3, 'memory': 64.8, 'disk': 23.7},
                {'date': '2025-01-05', 'cpu': 44.9, 'memory': 66.5, 'disk': 23.8},
            ]
        }
        
        return JsonResponse({
            'status': 'success',
            'timestamp': timezone.now().isoformat(),
            'period_days': int(days),
            'trends': trends_data
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


# =============================================================================
# REPORTES DE VISITAS A PÁGINAS
# =============================================================================

@staff_member_required
def api_page_visits_stats(request):
    """
    API para estadísticas de visitas a páginas.
    Retorna: totales, páginas más visitadas, visitantes únicos, evolución diaria.
    """
    try:
        now = timezone.now()
        today = now.date()
        last_7 = now - timedelta(days=7)
        last_30 = now - timedelta(days=30)

        total_today = PageVisit.objects.filter(timestamp__date=today).count()
        total_7d = PageVisit.objects.filter(timestamp__gte=last_7).count()
        total_30d = PageVisit.objects.filter(timestamp__gte=last_30).count()
        total_all = PageVisit.objects.count()

        unique_today = PageVisit.objects.filter(timestamp__date=today).values('ip_address').distinct().count()
        unique_7d = PageVisit.objects.filter(timestamp__gte=last_7).values('ip_address').distinct().count()
        unique_30d = PageVisit.objects.filter(timestamp__gte=last_30).values('ip_address').distinct().count()

        top_pages = (
            PageVisit.objects.filter(timestamp__gte=last_30)
            .values('path')
            .annotate(visitas=Count('id'))
            .order_by('-visitas')[:10]
        )

        daily = (
            PageVisit.objects.filter(timestamp__gte=last_30)
            .extra(select={'date': "DATE(timestamp)"})
            .values('date')
            .annotate(visitas=Count('id'), unicos=Count('ip_address', distinct=True))
            .order_by('date')
        )

        return JsonResponse({
            'status': 'success',
            'timestamp': now.isoformat(),
            'totales': {
                'hoy': total_today,
                'ultimos_7_dias': total_7d,
                'ultimos_30_dias': total_30d,
                'total_historico': total_all,
            },
            'visitantes_unicos': {
                'hoy': unique_today,
                'ultimos_7_dias': unique_7d,
                'ultimos_30_dias': unique_30d,
            },
            'top_paginas': list(top_pages),
            'evolucion_diaria': list(daily),
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@staff_member_required
def api_page_visits_recent(request):
    """
    API para las visitas más recientes (últimos 50).
    """
    try:
        visits = (
            PageVisit.objects.select_related('user')
            .order_by('-timestamp')[:50]
        )
        data = []
        for v in visits:
            data.append({
                'path': v.path,
                'user': v.user.username if v.user else 'Anónimo',
                'ip': v.ip_address,
                'timestamp': v.timestamp.isoformat(),
                'referer': v.referer,
            })
        return JsonResponse({
            'status': 'success',
            'visitas': data,
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
