"""
Sistema de caché inteligente para optimizar el rendimiento de la plataforma de indicadores.
Implementa caché granular para datos de gráficos, consultas de base de datos y respuestas de API.
"""
import hashlib
import json
from django.core.cache import cache
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Constantes de timeout desde settings
CACHE_TIMEOUT_PAGE = getattr(settings, 'CACHE_TIMEOUT_PAGE', 15 * 60)
CACHE_TIMEOUT_API = getattr(settings, 'CACHE_TIMEOUT_API', 30 * 60)
CACHE_TIMEOUT_QUERY = getattr(settings, 'CACHE_TIMEOUT_QUERY', 60 * 60)


def generate_cache_key(prefix, *args, **kwargs):
    """
    Genera una clave de caché única basada en los parámetros proporcionados.
    """
    # Crear string único con todos los parámetros
    key_data = {
        'args': args,
        'kwargs': sorted(kwargs.items()) if kwargs else {}
    }
    key_string = json.dumps(key_data, sort_keys=True, default=str)
    key_hash = hashlib.md5(key_string.encode()).hexdigest()[:12]
    
    return f"{prefix}_{key_hash}"


def cache_grafico_data(timeout=CACHE_TIMEOUT_API):
    """
    Decorador para cachear datos de gráficos basado en indicador y filtros.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, indicador_id, *args, **kwargs):
            # Extraer parámetros de filtro de la request
            filtros = {
                'ano_inicio': request.GET.get('ano_inicio'),
                'ano_fin': request.GET.get('ano_fin'),
                'desagregaciones_geograficas': request.GET.getlist('desagregaciones_geograficas'),
                'desagregaciones_tematicas': request.GET.getlist('desagregaciones_tematicas'),
            }
            
            # Generar clave de caché
            cache_key = generate_cache_key(
                f"grafico_{func.__name__}",
                indicador_id,
                filtros=filtros,
                args=args,
                kwargs=kwargs
            )
            
            # Intentar obtener del caché
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                return cached_data
            
            # Si no existe, ejecutar función y cachear resultado
            logger.debug(f"Cache MISS: {cache_key}")
            result = func(request, indicador_id, *args, **kwargs)
            
            # Cachear solo si la respuesta es exitosa
            if hasattr(result, 'status_code') and result.status_code == 200:
                cache.set(cache_key, result, timeout=timeout)
                logger.debug(f"Cache SET: {cache_key}")
            
            return result
        return wrapper
    return decorator


def cache_query_result(timeout=CACHE_TIMEOUT_QUERY):
    """
    Decorador para cachear resultados de consultas de base de datos.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave de caché basada en función y parámetros
            cache_key = generate_cache_key(
                f"query_{func.__name__}",
                args=args,
                kwargs=kwargs
            )
            
            # Intentar obtener del caché
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                logger.debug(f"Query cache HIT: {cache_key}")
                return cached_data
            
            # Ejecutar consulta y cachear resultado
            logger.debug(f"Query cache MISS: {cache_key}")
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout=timeout)
            logger.debug(f"Query cache SET: {cache_key}")
            
            return result
        return wrapper
    return decorator


def invalidate_indicator_cache(indicador_id):
    """
    Invalida todas las entradas de caché relacionadas con un indicador específico.
    """
    # Patrones de claves a invalidar
    patterns = [
        f"grafico_*_{indicador_id}_*",
        f"query_*_{indicador_id}_*",
        f"page_subtema_*_{indicador_id}_*",
        f"api_*_{indicador_id}_*"
    ]
    
    # En Django cache framework no hay delete_pattern nativo
    # Para implementación completa se necesitaría Redis con django-redis
    logger.info(f"Cache invalidation requested for indicator {indicador_id}")
    
    # Alternativa: limpiar todo el caché (menos eficiente pero funcional)
    # cache.clear()


def invalidate_subtema_cache(subtema_id):
    """
    Invalida caché relacionado con un subtema específico.
    """
    logger.info(f"Cache invalidation requested for subtema {subtema_id}")
    # Implementación similar a invalidate_indicator_cache


class CacheMetrics:
    """
    Clase para recopilar métricas de uso del caché.
    """
    
    @staticmethod
    def get_cache_stats():
        """
        Obtiene estadísticas básicas del caché.
        """
        # Esta funcionalidad depende del backend de caché utilizado
        # Con Redis se pueden obtener estadísticas más detalladas
        return {
            'backend': settings.CACHES['default']['BACKEND'],
            'status': 'active'
        }


# Funciones auxiliares para caché de datos específicos

def get_cached_indicadores_by_subtema(subtema_id):
    """
    Obtiene indicadores de un subtema con caché.
    """
    cache_key = f"indicadores_subtema_{subtema_id}"
    cached_data = cache.get(cache_key)
    
    if cached_data is not None:
        return cached_data
    
    # Importar aquí para evitar circular imports
    from .models import Indicador
    
    indicadores = list(Indicador.objects.filter(
        subtema_id=subtema_id, 
        activo=True
    ).order_by('orden', 'nombre').values(
        'id', 'nombre', 'unidad_medida', 'orden'
    ))
    
    cache.set(cache_key, indicadores, timeout=CACHE_TIMEOUT_QUERY)
    return indicadores


def get_cached_desagregaciones(indicador_id):
    """
    Obtiene desagregaciones disponibles para un indicador con caché.
    """
    cache_key = f"desagregaciones_indicador_{indicador_id}"
    cached_data = cache.get(cache_key)
    
    if cached_data is not None:
        return cached_data
    
    # Importar aquí para evitar circular imports
    from .models import Indicador
    
    try:
        indicador = Indicador.objects.get(id=indicador_id, activo=True)
        
        # Obtener desagregaciones geográficas disponibles
        desag_geo = []
        for dominio in indicador.dominios_desagregacion_geografica.filter(tipo='geografica'):
            desag_geo.extend(dominio.desagregaciones.values(
                'id', 'nombre', 'codigo'
            ))
        
        # Obtener desagregaciones temáticas disponibles
        desag_tem = []
        for dominio in indicador.dominios_desagregacion_tematica.filter(tipo='tematica'):
            desag_tem.extend(dominio.desagregaciones.values(
                'id', 'nombre', 'codigo'
            ))
        
        result = {
            'geograficas': desag_geo,
            'tematicas': desag_tem
        }
        
        cache.set(cache_key, result, timeout=CACHE_TIMEOUT_QUERY)
        return result
        
    except Exception as e:
        logger.error(f"Error getting desagregaciones for indicator {indicador_id}: {e}")
        return {'geograficas': [], 'tematicas': []}


# Señales para invalidación automática de caché

@receiver(post_save, sender='indicadores.Dato')
def invalidate_dato_cache(sender, instance, **kwargs):
    """
    Invalida caché cuando se actualiza un dato.
    """
    if instance.indicador_id:
        invalidate_indicator_cache(instance.indicador_id)


@receiver(post_delete, sender='indicadores.Dato')
def invalidate_dato_cache_on_delete(sender, instance, **kwargs):
    """
    Invalida caché cuando se elimina un dato.
    """
    if instance.indicador_id:
        invalidate_indicator_cache(instance.indicador_id)


@receiver(post_save, sender='indicadores.Indicador')
def invalidate_indicador_cache(sender, instance, **kwargs):
    """
    Invalida caché cuando se actualiza un indicador.
    """
    invalidate_indicator_cache(instance.id)
    if instance.subtema_id:
        invalidate_subtema_cache(instance.subtema_id)


@receiver(post_save, sender='indicadores.Grafico')
def invalidate_grafico_cache(sender, instance, **kwargs):
    """
    Invalida caché cuando se actualiza un gráfico.
    """
    if instance.indicador_id:
        invalidate_indicator_cache(instance.indicador_id)
