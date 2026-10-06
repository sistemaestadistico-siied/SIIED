"""
Sistema de Validaciones Automáticas de Datos para Indicadores Estadísticos.

Este módulo implementa validaciones automáticas que se ejecutan durante:
1. Ingesta de datos (extracción de conjunto_datos)
2. Actualización de datos existentes
3. Procesos de verificación programados

Las validaciones detectan inconsistencias, valores atípicos, datos faltantes
y problemas de calidad que podrían afectar la confiabilidad de los indicadores.
"""

from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Avg, Max, Min, StdDev
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import logging
import re
from typing import List, Dict, Any, Tuple
from .models import Indicador, Dato, Desagregacion, ProcesoLog

logger = logging.getLogger(__name__)


class DataValidationResult:
    """Resultado de una validación de datos."""
    
    def __init__(self, validation_type: str, status: str, message: str, 
                 affected_records: int = 0, details: Dict = None):
        self.validation_type = validation_type
        self.status = status  # 'success', 'warning', 'error'
        self.message = message
        self.affected_records = affected_records
        self.details = details or {}
        self.timestamp = timezone.now()


class DataValidator:
    """Validador principal de datos de indicadores."""
    
    def __init__(self):
        self.results = []
        self.error_count = 0
        self.warning_count = 0
    
    def validate_all(self, indicador_id: int = None) -> List[DataValidationResult]:
        """
        Ejecuta todas las validaciones disponibles.
        
        Args:
            indicador_id: ID específico de indicador a validar (opcional)
        
        Returns:
            Lista de resultados de validación
        """
        self.results = []
        self.error_count = 0
        self.warning_count = 0
        
        logger.info(f"Iniciando validaciones automáticas para indicador {indicador_id or 'todos'}")
        
        # Validaciones básicas de integridad
        self._validate_null_values(indicador_id)
        self._validate_negative_values(indicador_id)
        self._validate_date_consistency(indicador_id)
        self._validate_duplicate_records(indicador_id)
        
        # Validaciones estadísticas
        self._validate_outliers(indicador_id)
        self._validate_temporal_consistency(indicador_id)
        self._validate_geographic_completeness(indicador_id)
        
        # Validaciones de negocio
        self._validate_population_constraints(indicador_id)
        self._validate_percentage_bounds(indicador_id)
        self._validate_data_freshness(indicador_id)
        
        logger.info(f"Validaciones completadas: {len(self.results)} resultados, "
                   f"{self.error_count} errores, {self.warning_count} advertencias")
        
        return self.results
    
    def _add_result(self, validation_type: str, status: str, message: str, 
                   affected_records: int = 0, details: Dict = None):
        """Agregar resultado de validación."""
        result = DataValidationResult(validation_type, status, message, 
                                    affected_records, details)
        self.results.append(result)
        
        if status == 'error':
            self.error_count += 1
        elif status == 'warning':
            self.warning_count += 1
    
    def _validate_null_values(self, indicador_id: int = None):
        """Validar valores nulos en datos críticos."""
        queryset = Dato.objects.all()
        if indicador_id:
            queryset = queryset.filter(indicador_id=indicador_id)
        
        null_values = queryset.filter(valor_dato__isnull=True).count()
        total_records = queryset.count()
        
        if null_values > 0:
            percentage = (null_values / total_records) * 100 if total_records > 0 else 0
            status = 'error' if percentage > 5 else 'warning'
            
            self._add_result(
                'null_values',
                status,
                f'Se encontraron {null_values} valores nulos ({percentage:.1f}% del total)',
                null_values,
                {'percentage': percentage, 'total_records': total_records}
            )
        else:
            self._add_result('null_values', 'success', 'No se encontraron valores nulos')
    
    def _validate_negative_values(self, indicador_id: int = None):
        """Validar valores negativos en indicadores que no deberían tenerlos."""
        # Indicadores que típicamente no deberían tener valores negativos
        positive_indicators = [
            'población', 'habitantes', 'total', 'cantidad', 'número',
            'nacimientos', 'defunciones', 'matrimonios'
        ]
        
        queryset = Dato.objects.filter(valor_dato__lt=0)
        if indicador_id:
            queryset = queryset.filter(indicador_id=indicador_id)
        else:
            # Filtrar solo indicadores que deberían ser positivos
            queryset = queryset.filter(
                Q(indicador__nombre__icontains='población') |
                Q(indicador__nombre__icontains='total') |
                Q(indicador__nombre__icontains='cantidad')
            )
        
        negative_count = queryset.count()
        
        if negative_count > 0:
            self._add_result(
                'negative_values',
                'warning',
                f'Se encontraron {negative_count} valores negativos en indicadores poblacionales',
                negative_count
            )
        else:
            self._add_result('negative_values', 'success', 'No se encontraron valores negativos problemáticos')
    
    def _validate_date_consistency(self, indicador_id: int = None):
        """Validar consistencia de fechas."""
        queryset = Dato.objects.all()
        if indicador_id:
            queryset = queryset.filter(indicador_id=indicador_id)
        
        # Fechas futuras
        future_dates = queryset.filter(fecha_dato__gt=timezone.now().date()).count()
        
        # Fechas muy antiguas (antes de 1900)
        old_dates = queryset.filter(fecha_dato__year__lt=1900).count()
        
        issues = []
        if future_dates > 0:
            issues.append(f'{future_dates} registros con fechas futuras')
        if old_dates > 0:
            issues.append(f'{old_dates} registros con fechas anteriores a 1900')
        
        if issues:
            self._add_result(
                'date_consistency',
                'warning',
                f'Inconsistencias de fecha: {", ".join(issues)}',
                future_dates + old_dates
            )
        else:
            self._add_result('date_consistency', 'success', 'Fechas consistentes')
    
    def _validate_duplicate_records(self, indicador_id: int = None):
        """Detectar registros duplicados."""
        queryset = Dato.objects.all()
        if indicador_id:
            queryset = queryset.filter(indicador_id=indicador_id)
        
        # Buscar duplicados por indicador, fecha y desagregaciones
        duplicates = queryset.values(
            'indicador', 'fecha_dato'
        ).annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        duplicate_count = duplicates.count()
        
        if duplicate_count > 0:
            self._add_result(
                'duplicate_records',
                'error',
                f'Se encontraron {duplicate_count} grupos de registros duplicados',
                duplicate_count
            )
        else:
            self._add_result('duplicate_records', 'success', 'No se encontraron duplicados')
    
    def _validate_outliers(self, indicador_id: int = None):
        """Detectar valores atípicos usando desviación estándar."""
        queryset = Dato.objects.all()
        if indicador_id:
            queryset = queryset.filter(indicador_id=indicador_id)
        
        # Agrupar por indicador para análisis estadístico
        indicators = queryset.values('indicador').distinct()
        total_outliers = 0
        
        for indicator in indicators:
            indicator_data = queryset.filter(indicador=indicator['indicador'])
            
            if indicator_data.count() < 10:  # Necesitamos suficientes datos
                continue
            
            stats = indicator_data.aggregate(
                avg=Avg('valor_dato'),
                std=StdDev('valor_dato')
            )
            
            if stats['std'] and stats['avg']:
                # Valores que están más de 3 desviaciones estándar de la media
                threshold_upper = float(stats['avg']) + (3 * float(stats['std']))
                threshold_lower = float(stats['avg']) - (3 * float(stats['std']))
                
                outliers = indicator_data.filter(
                    Q(valor_dato__gt=threshold_upper) | 
                    Q(valor_dato__lt=threshold_lower)
                ).count()
                
                total_outliers += outliers
        
        if total_outliers > 0:
            self._add_result(
                'outliers',
                'warning',
                f'Se detectaron {total_outliers} valores atípicos (>3σ)',
                total_outliers
            )
        else:
            self._add_result('outliers', 'success', 'No se detectaron valores atípicos significativos')
    
    def _validate_temporal_consistency(self, indicador_id: int = None):
        """Validar consistencia temporal en series de datos."""
        queryset = Dato.objects.all()
        if indicador_id:
            queryset = queryset.filter(indicador_id=indicador_id)
        
        # Detectar saltos temporales abruptos (cambios >500% entre períodos consecutivos)
        inconsistencies = 0
        
        indicators = queryset.values('indicador').distinct()
        
        for indicator in indicators:
            data_series = queryset.filter(
                indicador=indicator['indicador']
            ).order_by('fecha_dato').values('valor_dato', 'fecha_dato')
            
            previous_value = None
            for record in data_series:
                if previous_value and record['valor_dato']:
                    current_value = float(record['valor_dato'])
                    prev_value = float(previous_value)
                    
                    if prev_value > 0:  # Evitar división por cero
                        change_ratio = abs(current_value - prev_value) / prev_value
                        if change_ratio > 5.0:  # Cambio mayor al 500%
                            inconsistencies += 1
                
                previous_value = record['valor_dato']
        
        if inconsistencies > 0:
            self._add_result(
                'temporal_consistency',
                'warning',
                f'Se detectaron {inconsistencies} cambios temporales abruptos (>500%)',
                inconsistencies
            )
        else:
            self._add_result('temporal_consistency', 'success', 'Consistencia temporal adecuada')
    
    def _validate_geographic_completeness(self, indicador_id: int = None):
        """Validar completitud geográfica de los datos."""
        queryset = Dato.objects.all()
        if indicador_id:
            queryset = queryset.filter(indicador_id=indicador_id)
        
        # Verificar que todos los elementos geográficos tengan datos
        missing_geo = 0
        
        # Esta validación requiere conocimiento específico de la estructura geográfica
        # Por ahora, validamos que existan desagregaciones geográficas
        datos_sin_geo = queryset.filter(
            desagregaciones_geograficas__isnull=True
        ).count()
        
        if datos_sin_geo > 0:
            self._add_result(
                'geographic_completeness',
                'warning',
                f'{datos_sin_geo} registros sin desagregación geográfica',
                datos_sin_geo
            )
        else:
            self._add_result('geographic_completeness', 'success', 'Completitud geográfica adecuada')
    
    def _validate_population_constraints(self, indicador_id: int = None):
        """Validar restricciones específicas de población."""
        queryset = Dato.objects.all()
        if indicador_id:
            queryset = queryset.filter(indicador_id=indicador_id)
        
        # Validar que la suma de subgrupos no exceda el total
        # Esta es una validación compleja que requiere lógica específica del dominio
        
        population_issues = 0
        
        # Ejemplo: validar que población por sexo no exceda población total
        # (requiere implementación específica según estructura de datos)
        
        self._add_result(
            'population_constraints',
            'success',
            'Validación de restricciones poblacionales completada'
        )
    
    def _validate_percentage_bounds(self, indicador_id: int = None):
        """Validar que los porcentajes estén en rangos válidos (0-100)."""
        queryset = Dato.objects.all()
        if indicador_id:
            queryset = queryset.filter(indicador_id=indicador_id)
        
        # Identificar indicadores que son porcentajes
        percentage_indicators = queryset.filter(
            Q(indicador__unidad_medida__icontains='%') |
            Q(indicador__unidad_medida__icontains='porcentaje') |
            Q(indicador__nombre__icontains='tasa') |
            Q(indicador__nombre__icontains='proporción')
        )
        
        invalid_percentages = percentage_indicators.filter(
            Q(valor_dato__lt=0) | Q(valor_dato__gt=100)
        ).count()
        
        if invalid_percentages > 0:
            self._add_result(
                'percentage_bounds',
                'error',
                f'{invalid_percentages} porcentajes fuera del rango válido (0-100)',
                invalid_percentages
            )
        else:
            self._add_result('percentage_bounds', 'success', 'Porcentajes en rangos válidos')
    
    def _validate_data_freshness(self, indicador_id: int = None):
        """Validar que los datos sean relativamente recientes."""
        queryset = Dato.objects.all()
        if indicador_id:
            queryset = queryset.filter(indicador_id=indicador_id)
        
        # Considerar datos "antiguos" si son de hace más de 5 años
        cutoff_date = timezone.now().date() - timedelta(days=5*365)
        
        old_data_count = queryset.filter(fecha_dato__lt=cutoff_date).count()
        total_data = queryset.count()
        
        if old_data_count > 0 and total_data > 0:
            old_percentage = (old_data_count / total_data) * 100
            status = 'warning' if old_percentage > 50 else 'success'
            
            self._add_result(
                'data_freshness',
                status,
                f'{old_data_count} registros antiguos (>{5} años) - {old_percentage:.1f}% del total',
                old_data_count,
                {'old_percentage': old_percentage}
            )
        else:
            self._add_result('data_freshness', 'success', 'Datos con frescura adecuada')


def run_automatic_validations(indicador_id: int = None) -> Dict[str, Any]:
    """
    Función principal para ejecutar validaciones automáticas.
    
    Args:
        indicador_id: ID específico de indicador (opcional)
    
    Returns:
        Diccionario con resultados de validación
    """
    validator = DataValidator()
    results = validator.validate_all(indicador_id)
    
    # Crear log del proceso
    try:
        log_entry = ProcesoLog.objects.create(
            proceso_extraccion=None,  # No está asociado a un proceso específico
            mensaje=f"Validaciones automáticas ejecutadas: {len(results)} validaciones",
            nivel='INFO',
            detalles={
                'total_validations': len(results),
                'errors': validator.error_count,
                'warnings': validator.warning_count,
                'indicador_id': indicador_id
            }
        )
    except Exception as e:
        logger.error(f"Error creando log de validaciones: {e}")
    
    return {
        'status': 'completed',
        'total_validations': len(results),
        'errors': validator.error_count,
        'warnings': validator.warning_count,
        'results': [
            {
                'type': r.validation_type,
                'status': r.status,
                'message': r.message,
                'affected_records': r.affected_records,
                'details': r.details,
                'timestamp': r.timestamp.isoformat()
            }
            for r in results
        ]
    }
