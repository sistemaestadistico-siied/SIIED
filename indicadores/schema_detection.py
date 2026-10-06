"""
Sistema de Autodetección de Esquemas para Archivos de conjunto_datos
Analiza automáticamente la estructura de archivos CSV/Excel para:
- Detectar tipos de columnas (fecha, numérico, categórico)
- Identificar desagregaciones geográficas y temáticas
- Sugerir reglas de extracción automáticamente
"""

import pandas as pd
import numpy as np
from datetime import datetime
import re
from typing import Dict, List, Tuple, Optional
from django.core.exceptions import ValidationError
from .models import DominioDesagregacion, Desagregacion, NivelGeografico


class SchemaDetector:
    """Detector automático de esquemas en archivos de conjunto_datos."""
    
    def __init__(self):
        # Patrones para identificar tipos de columnas
        self.date_patterns = [
            r'fecha', r'año', r'year', r'date', r'periodo', r'time'
        ]
        
        self.geographic_patterns = [
            r'comuna', r'barrio', r'localidad', r'municipio', r'departamento',
            r'zona', r'sector', r'corregimiento', r'vereda', r'región',
            r'área', r'territorio', r'distrito', r'cabecera', r'rural'
        ]
        
        self.demographic_patterns = [
            r'sexo', r'género', r'edad', r'grupo.*edad', r'rango.*edad',
            r'estrato', r'nivel.*educativo', r'ocupación', r'profesión'
        ]
        
        self.value_patterns = [
            r'total', r'cantidad', r'número', r'valor', r'población',
            r'habitantes', r'personas', r'casos', r'eventos'
        ]
        
        # Biblioteca de patrones de indicadores conocidos
        self.indicator_patterns = {
            'poblacion': {
                'keywords': ['población', 'habitantes', 'personas', 'total'],
                'formula_type': 'sum',
                'expected_disaggregations': ['sexo', 'edad', 'comuna'],
                'validation_rules': ['no_negative', 'sum_consistency']
            },
            'nacimientos': {
                'keywords': ['nacimientos', 'natalidad', 'nacidos'],
                'formula_type': 'sum',
                'expected_disaggregations': ['sexo', 'comuna', 'mes'],
                'validation_rules': ['no_negative', 'temporal_consistency']
            },
            'defunciones': {
                'keywords': ['defunciones', 'mortalidad', 'muertes', 'fallecidos'],
                'formula_type': 'sum',
                'expected_disaggregations': ['sexo', 'edad', 'causa'],
                'validation_rules': ['no_negative', 'temporal_consistency']
            },
            'tasa_mortalidad': {
                'keywords': ['tasa', 'mortalidad', 'por mil', 'por 1000'],
                'formula_type': 'rate',
                'expected_disaggregations': ['sexo', 'edad'],
                'validation_rules': ['rate_bounds', 'no_negative']
            },
            'porcentaje': {
                'keywords': ['porcentaje', '%', 'proporción', 'participación'],
                'formula_type': 'percentage',
                'expected_disaggregations': ['categoria'],
                'validation_rules': ['percentage_bounds']
            }
        }
    
    def analyze_file_with_context(self, file_path: str, indicador_context: Dict = None, sample_rows: int = 1000) -> Dict:
        """
        Analiza un archivo con contexto del indicador para sugerir configuración específica.
        
        Args:
            file_path: Ruta al archivo CSV/Excel
            indicador_context: Contexto del indicador (nombre, tipo, dominios esperados)
            sample_rows: Número de filas a analizar (para archivos grandes)
        
        Returns:
            Diccionario con el esquema detectado y sugerencias contextuales
        """
        try:
            # Leer archivo (detectar formato automáticamente)
            if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
                df = pd.read_excel(file_path, nrows=sample_rows)
            else:
                # Probar diferentes encodings para CSV
                encodings = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']
                df = None
                for encoding in encodings:
                    try:
                        df = pd.read_csv(file_path, nrows=sample_rows, encoding=encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                
                if df is None:
                    raise ValidationError("No se pudo leer el archivo con ninguna codificación")
            
            # Analizar cada columna
            schema = {
                'file_info': {
                    'total_columns': len(df.columns),
                    'sample_rows': len(df),
                    'columns': list(df.columns)
                },
                'column_analysis': {},
                'suggested_mappings': {
                    'date_columns': [],
                    'value_columns': [],
                    'geographic_disaggregations': [],
                    'thematic_disaggregations': []
                },
                'data_quality': {
                    'null_percentages': {},
                    'unique_value_counts': {},
                    'data_types': {}
                }
            }
            
            for column in df.columns:
                analysis = self._analyze_column(df[column], column)
                schema['column_analysis'][column] = analysis
                
                # Clasificar columna según el análisis
                if analysis['likely_type'] == 'date':
                    schema['suggested_mappings']['date_columns'].append(column)
                elif analysis['likely_type'] == 'numeric_value':
                    schema['suggested_mappings']['value_columns'].append(column)
                elif analysis['likely_type'] == 'geographic':
                    schema['suggested_mappings']['geographic_disaggregations'].append(column)
                elif analysis['likely_type'] == 'demographic':
                    schema['suggested_mappings']['thematic_disaggregations'].append(column)
                
                # Métricas de calidad
                schema['data_quality']['null_percentages'][column] = (df[column].isnull().sum() / len(df)) * 100
                schema['data_quality']['unique_value_counts'][column] = df[column].nunique()
                schema['data_quality']['data_types'][column] = str(df[column].dtype)
            
            # Detectar tipo de indicador basado en contexto
            indicator_type = self._detect_indicator_type(indicador_context, df)
            schema['detected_indicator_type'] = indicator_type
            
            # Generar sugerencias contextuales de reglas de extracción
            schema['extraction_suggestions'] = self._suggest_contextual_extraction_rules(
                schema, df, indicator_type, indicador_context
            )
            
            # Validar compatibilidad con algoritmo cartesiano
            schema['cartesian_compatibility'] = self._validate_cartesian_compatibility(
                schema, indicator_type
            )
            
            return schema
            
        except Exception as e:
            raise ValidationError(f"Error analizando archivo: {str(e)}")
    
    def _analyze_column(self, series: pd.Series, column_name: str) -> Dict:
        """Analiza una columna individual para determinar su tipo y características."""
        
        analysis = {
            'column_name': column_name,
            'likely_type': 'unknown',
            'confidence': 0.0,
            'sample_values': [],
            'unique_count': series.nunique(),
            'null_count': series.isnull().sum(),
            'data_type': str(series.dtype),
            'patterns_found': []
        }
        
        # Obtener muestra de valores no nulos
        non_null_values = series.dropna()
        if len(non_null_values) > 0:
            sample_size = min(10, len(non_null_values))
            analysis['sample_values'] = non_null_values.head(sample_size).tolist()
        
        # Detectar tipo de columna
        column_lower = column_name.lower()
        
        # 1. Detectar columnas de fecha
        if self._matches_patterns(column_lower, self.date_patterns):
            analysis['likely_type'] = 'date'
            analysis['confidence'] = 0.8
            analysis['patterns_found'].append('date_pattern_in_name')
            
            # Verificar si los valores parecen fechas
            if self._looks_like_dates(non_null_values):
                analysis['confidence'] = 0.95
                analysis['patterns_found'].append('date_values_detected')
        
        # 2. Detectar columnas geográficas
        elif self._matches_patterns(column_lower, self.geographic_patterns):
            analysis['likely_type'] = 'geographic'
            analysis['confidence'] = 0.8
            analysis['patterns_found'].append('geographic_pattern_in_name')
            
            # Verificar si hay valores geográficos conocidos
            if self._contains_known_geographic_values(non_null_values):
                analysis['confidence'] = 0.9
                analysis['patterns_found'].append('known_geographic_values')
        
        # 3. Detectar columnas demográficas/temáticas
        elif self._matches_patterns(column_lower, self.demographic_patterns):
            analysis['likely_type'] = 'demographic'
            analysis['confidence'] = 0.8
            analysis['patterns_found'].append('demographic_pattern_in_name')
        
        # 4. Detectar columnas de valores numéricos
        elif self._matches_patterns(column_lower, self.value_patterns) or pd.api.types.is_numeric_dtype(series):
            analysis['likely_type'] = 'numeric_value'
            analysis['confidence'] = 0.7
            analysis['patterns_found'].append('numeric_pattern')
            
            if pd.api.types.is_numeric_dtype(series):
                analysis['confidence'] = 0.9
                analysis['patterns_found'].append('numeric_dtype')
        
        # 5. Detectar columnas categóricas
        elif analysis['unique_count'] < len(non_null_values) * 0.5:  # Menos del 50% de valores únicos
            analysis['likely_type'] = 'categorical'
            analysis['confidence'] = 0.6
            analysis['patterns_found'].append('low_unique_ratio')
        
        return analysis
    
    def _matches_patterns(self, text: str, patterns: List[str]) -> bool:
        """Verifica si un texto coincide con alguno de los patrones."""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _looks_like_dates(self, values: pd.Series) -> bool:
        """Verifica si los valores parecen fechas."""
        if len(values) == 0:
            return False
        
        # Probar convertir una muestra a fechas
        sample = values.head(min(10, len(values)))
        date_count = 0
        
        for value in sample:
            try:
                # Intentar parsear como fecha
                if isinstance(value, (int, float)):
                    # Podría ser año
                    if 1900 <= value <= 2100:
                        date_count += 1
                else:
                    pd.to_datetime(str(value))
                    date_count += 1
            except:
                pass
        
        return date_count / len(sample) > 0.7  # 70% de los valores parecen fechas
    
    def _contains_known_geographic_values(self, values: pd.Series) -> bool:
        """Verifica si contiene valores geográficos conocidos."""
        if len(values) == 0:
            return False
        
        # Valores geográficos comunes en Colombia
        known_places = [
            'cali', 'bogotá', 'medellín', 'barranquilla', 'cartagena',
            'buenaventura', 'palmira', 'tulua', 'buga', 'cartago',
            'comuna', 'corregimiento', 'cabecera', 'rural', 'urbano'
        ]
        
        sample = values.head(min(20, len(values)))
        matches = 0
        
        for value in sample:
            value_str = str(value).lower()
            for place in known_places:
                if place in value_str:
                    matches += 1
                    break
        
        return matches / len(sample) > 0.3  # 30% de coincidencias
    
    def _detect_indicator_type(self, indicador_context: Dict, df: pd.DataFrame) -> str:
        """Detecta el tipo de indicador basado en contexto y contenido del archivo."""
        if not indicador_context:
            return 'unknown'
        
        indicator_name = indicador_context.get('nombre', '').lower()
        
        # Buscar coincidencias con patrones conocidos
        for pattern_type, pattern_info in self.indicator_patterns.items():
            for keyword in pattern_info['keywords']:
                if keyword in indicator_name:
                    return pattern_type
        
        # Análisis de columnas para inferir tipo
        columns_text = ' '.join(df.columns).lower()
        
        if any(word in columns_text for word in ['tasa', 'por mil', 'por 1000']):
            return 'tasa_mortalidad'
        elif any(word in columns_text for word in ['%', 'porcentaje', 'proporción']):
            return 'porcentaje'
        elif any(word in columns_text for word in ['población', 'habitantes']):
            return 'poblacion'
        
        return 'unknown'
    
    def _suggest_contextual_extraction_rules(self, schema: Dict, df: pd.DataFrame, 
                                           indicator_type: str, indicador_context: Dict) -> Dict:
        """Genera sugerencias para reglas de extracción basadas en el esquema detectado."""
        
        suggestions = {
            'recommended_date_column': None,
            'recommended_value_columns': [],
            'suggested_formula': None,
            'geographic_mappings': [],
            'thematic_mappings': [],
            'filters_suggestions': [],
            'cartesian_formula': None,  # Fórmula compatible con algoritmo cartesiano
            'aggregation_level': None,  # Nivel de agregación sugerido
            'validation_rules': [],     # Reglas de validación específicas
            'confidence_score': 0.0     # Confianza en las sugerencias
        }
        
        # Sugerir columna de fecha principal
        date_columns = schema['suggested_mappings']['date_columns']
        if date_columns:
            # Preferir columnas con 'año' o 'fecha' en el nombre
            for col in date_columns:
                if 'año' in col.lower() or 'fecha' in col.lower():
                    suggestions['recommended_date_column'] = col
                    break
            if not suggestions['recommended_date_column']:
                suggestions['recommended_date_column'] = date_columns[0]
        
        # Sugerir columnas de valores
        value_columns = schema['suggested_mappings']['value_columns']
        suggestions['recommended_value_columns'] = value_columns[:3]  # Máximo 3 sugerencias
        
        # Generar fórmula contextual basada en tipo de indicador
        if indicator_type in self.indicator_patterns:
            pattern_info = self.indicator_patterns[indicator_type]
            formula_type = pattern_info['formula_type']
            
            if value_columns:
                main_value_col = value_columns[0]
                
                if formula_type == 'sum':
                    suggestions['suggested_formula'] = f"SUM({main_value_col})"
                    suggestions['cartesian_formula'] = f"df.groupby(disaggregations)['{main_value_col}'].sum()"
                elif formula_type == 'rate':
                    # Buscar denominador (población)
                    denominator_col = self._find_denominator_column(df, value_columns)
                    if denominator_col:
                        suggestions['suggested_formula'] = f"({main_value_col} / {denominator_col}) * 1000"
                        suggestions['cartesian_formula'] = f"(df['{main_value_col}'] / df['{denominator_col}']) * 1000"
                    else:
                        suggestions['suggested_formula'] = f"SUM({main_value_col})"
                elif formula_type == 'percentage':
                    suggestions['suggested_formula'] = f"({main_value_col} / SUM({main_value_col})) * 100"
                    suggestions['cartesian_formula'] = f"(df['{main_value_col}'] / df['{main_value_col}'].sum()) * 100"
                
                suggestions['validation_rules'] = pattern_info['validation_rules']
                suggestions['confidence_score'] = 0.9
        elif value_columns:
            # Fórmula genérica si no hay contexto
            main_value_col = value_columns[0]
            suggestions['suggested_formula'] = f"SUM({main_value_col})"
            suggestions['cartesian_formula'] = f"df.groupby(disaggregations)['{main_value_col}'].sum()"
            suggestions['confidence_score'] = 0.5
        
        # Mapear desagregaciones geográficas a dominios existentes
        for geo_col in schema['suggested_mappings']['geographic_disaggregations']:
            domain_suggestion = self._suggest_geographic_domain(geo_col, df[geo_col])
            if domain_suggestion:
                suggestions['geographic_mappings'].append({
                    'column': geo_col,
                    'suggested_domain': domain_suggestion,
                    'confidence': 0.7
                })
        
        # Mapear desagregaciones temáticas
        for theme_col in schema['suggested_mappings']['thematic_disaggregations']:
            suggestions['thematic_mappings'].append({
                'column': theme_col,
                'suggested_type': 'tematica',
                'unique_values': df[theme_col].unique()[:10].tolist()  # Primeros 10 valores únicos
            })
        
        # Validar desagregaciones esperadas vs encontradas
        if indicator_type in self.indicator_patterns:
            expected_disagg = self.indicator_patterns[indicator_type]['expected_disaggregations']
            found_disagg = [col.lower() for col in 
                          schema['suggested_mappings']['geographic_disaggregations'] + 
                          schema['suggested_mappings']['thematic_disaggregations']]
            
            missing_disagg = [d for d in expected_disagg if not any(d in found for found in found_disagg)]
            if missing_disagg:
                suggestions['filters_suggestions'].append({
                    'type': 'missing_disaggregations',
                    'message': f"Desagregaciones esperadas no encontradas: {missing_disagg}",
                    'action': 'review_column_mapping'
                })
        
        return suggestions
    
    def _find_denominator_column(self, df: pd.DataFrame, value_columns: List[str]) -> Optional[str]:
        """Busca columna que podría servir como denominador para tasas."""
        denominator_keywords = ['población', 'total', 'habitantes', 'personas']
        
        for col in df.columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in denominator_keywords):
                if col not in value_columns:  # No debe ser la misma columna del numerador
                    return col
        return None
    
    def _validate_cartesian_compatibility(self, schema: Dict, indicator_type: str) -> Dict:
        """Valida que las sugerencias sean compatibles con el algoritmo cartesiano."""
        compatibility = {
            'is_compatible': True,
            'issues': [],
            'recommendations': []
        }
        
        # Verificar que hay al menos una columna de fecha
        if not schema['suggested_mappings']['date_columns']:
            compatibility['is_compatible'] = False
            compatibility['issues'].append('No se detectó columna de fecha')
            compatibility['recommendations'].append('Verificar que existe una columna con años o fechas')
        
        # Verificar que hay columnas de valores
        if not schema['suggested_mappings']['value_columns']:
            compatibility['is_compatible'] = False
            compatibility['issues'].append('No se detectaron columnas de valores numéricos')
            compatibility['recommendations'].append('Verificar que existen columnas con datos cuantitativos')
        
        # Verificar desagregaciones mínimas
        total_disagg = (len(schema['suggested_mappings']['geographic_disaggregations']) + 
                       len(schema['suggested_mappings']['thematic_disaggregations']))
        
        if total_disagg == 0:
            compatibility['issues'].append('No se detectaron desagregaciones')
            compatibility['recommendations'].append('El algoritmo cartesiano requiere al menos una desagregación')
        
        # Validaciones específicas por tipo de indicador
        if indicator_type in self.indicator_patterns:
            pattern_info = self.indicator_patterns[indicator_type]
            
            if pattern_info['formula_type'] == 'rate':
                # Las tasas requieren numerador y denominador
                suggestions = schema.get('extraction_suggestions', {})
                if not suggestions.get('cartesian_formula') or 'df[' not in suggestions.get('cartesian_formula', ''):
                    compatibility['issues'].append('Fórmula de tasa incompleta')
                    compatibility['recommendations'].append('Verificar que existen columnas para numerador y denominador')
        
        return compatibility
    
    def _suggest_geographic_domain(self, column_name: str, values: pd.Series) -> Optional[str]:
        """Sugiere un dominio geográfico basado en el nombre de columna y valores."""
        
        column_lower = column_name.lower()
        unique_values = values.dropna().unique()
        
        # Mapeo de patrones a dominios geográficos
        domain_mappings = {
            'comuna': 'Comunas',
            'barrio': 'Barrios',
            'corregimiento': 'Corregimientos',
            'localidad': 'Localidades',
            'zona': 'Zonas',
            'sector': 'Sectores'
        }
        
        for pattern, domain in domain_mappings.items():
            if pattern in column_lower:
                return domain
        
        # Analizar valores únicos para inferir el tipo
        if len(unique_values) <= 30:  # Pocos valores únicos, probablemente comunas/sectores
            return 'Comunas'
        elif len(unique_values) <= 100:  # Valores medios, probablemente barrios
            return 'Barrios'
        
        return None


def analyze_conjunto_datos_schema(file_path: str, indicador_id: int = None) -> Dict:
    """
    Función principal para analizar el esquema de un archivo de conjunto_datos con contexto.
    
    Args:
        file_path: Ruta al archivo a analizar
        indicador_id: ID del indicador para obtener contexto
    
    Returns:
        Diccionario con el análisis completo del esquema
    """
    from .models import Indicador
    
    detector = SchemaDetector()
    
    # Obtener contexto del indicador si se proporciona ID
    indicador_context = None
    if indicador_id:
        try:
            indicador = Indicador.objects.get(id=indicador_id)
            indicador_context = {
                'nombre': indicador.nombre,
                'subtema': indicador.subtema.nombre,
                'tema': indicador.subtema.tema.nombre,
                'dominio': indicador.subtema.tema.dominio.nombre,
                'unidad_medida': getattr(indicador, 'unidad_medida', ''),
                'dominios_geograficos': [d.nombre for d in indicador.dominios_desagregacion_geografica.all()],
                'dominios_tematicos': [d.nombre for d in indicador.dominios_desagregacion_tematica.all()]
            }
        except Indicador.DoesNotExist:
            pass
    
    return detector.analyze_file_with_context(file_path, indicador_context)


def create_extraction_rule_from_schema(indicador_id: int, schema: Dict) -> Dict:
    """
    Crea una regla de extracción automáticamente basada en el esquema detectado.
    
    Args:
        indicador_id: ID del indicador
        schema: Esquema detectado por analyze_conjunto_datos_schema
    
    Returns:
        Diccionario con los parámetros para crear la ReglaExtraccion
    """
    suggestions = schema.get('extraction_suggestions', {})
    
    rule_params = {
        'indicador_id': indicador_id,
        'columna_fecha': suggestions.get('recommended_date_column'),
        'columnas_fuente': suggestions.get('recommended_value_columns', []),
        'formula': suggestions.get('suggested_formula', 'SUM(valor)'),
        'filtros': {},
        'orden_desagregaciones': []
    }
    
    # Agregar orden de desagregaciones sugerido
    geographic_cols = [m['column'] for m in suggestions.get('geographic_mappings', [])]
    thematic_cols = [m['column'] for m in suggestions.get('thematic_mappings', [])]
    
    rule_params['orden_desagregaciones'] = geographic_cols + thematic_cols
    
    return rule_params
