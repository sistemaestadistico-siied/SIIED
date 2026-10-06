"""
Parsers de CSV para el Wizard Admin Unificado.
Funciones para extraer metadata de archivos CSV subidos por el equipo de recolección.
"""

import pandas as pd
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class MetadataVariablesParser:
    """
    Parser para archivos de metadata de variables (metadata_variables.csv).
    Extrae información de las variables de conjunto_datos.
    """
    
    # Mapeo de nombres de columnas (flexibilidad en mayúsculas/minúsculas)
    COLUMN_MAPPINGS = {
        'codigo_variable': ['Codigo_Variable', 'codigo_variable', 'codigo', 'Codigo'],
        'nombre_variable': ['Nombre_Variable', 'nombre_variable', 'nombre', 'Nombre'],
        'definicion_conceptual': ['Definicion_Conceptual', 'definicion_conceptual', 'definicion', 'Definicion'],
        'tipo_dato': ['Tipo_Dato', 'tipo_dato', 'tipo', 'Tipo'],
        'dominio_dato': ['Dominio_Dato', 'dominio_dato', 'dominio', 'Dominio'],
        'unidad_medida': ['Unidad_Medida', 'unidad_medida', 'unidad', 'Unidad'],
        'tipo_variable_estadistica': ['Tipo_Variable_Estadistica', 'tipo_variable_estadistica', 'tipo_variable'],
        'poblacion_objetivo': ['Poblacion_Objetivo', 'poblacion_objetivo', 'poblacion'],
        'cobertura_geografica': ['Cobertura_Geografica', 'cobertura_geografica', 'cobertura'],
        'fuente_datos': ['Fuente_Datos', 'fuente_datos', 'fuente', 'Fuente de la información'],
        'periodicidad': ['Periodicidad', 'periodicidad'],
        'organismo_productor': ['Organismo_Productor', 'organismo_productor', 'organismo'],
        'observaciones': ['Observaciones', 'observaciones', 'obs'],
    }
    
    @classmethod
    def parse(cls, csv_path: str) -> List[Dict[str, Any]]:
        """
        Parsea el archivo CSV de metadata de variables.
        
        Args:
            csv_path: Ruta al archivo CSV
            
        Returns:
            Lista de diccionarios con la metadata de cada variable
        """
        try:
            df = pd.read_csv(csv_path)
            
            # Normalizar nombres de columnas
            column_map = cls._build_column_map(df.columns)
            
            variables = []
            for idx, row in df.iterrows():
                variable = {}
                
                for field, possible_names in cls.COLUMN_MAPPINGS.items():
                    actual_column = column_map.get(field)
                    if actual_column and actual_column in df.columns:
                        value = row[actual_column]
                        # Convertir NaN a None
                        variable[field] = None if pd.isna(value) else str(value)
                    else:
                        variable[field] = None
                
                # Asegurar que al menos tenga código o nombre
                if variable.get('codigo_variable') or variable.get('nombre_variable'):
                    # Si no tiene código, generar uno
                    if not variable.get('codigo_variable'):
                        variable['codigo_variable'] = f'VAR_{idx + 1}'
                    
                    variables.append(variable)
            
            logger.info(f"Parseadas {len(variables)} variables desde {csv_path}")
            return variables
            
        except Exception as e:
            logger.error(f"Error al parsear metadata de variables: {e}")
            raise
    
    @classmethod
    def _build_column_map(cls, columns: List[str]) -> Dict[str, str]:
        """
        Construye un mapeo de campos normalizados a nombres de columnas reales.
        
        Args:
            columns: Lista de nombres de columnas del CSV
            
        Returns:
            Diccionario {campo_normalizado: nombre_columna_real}
        """
        column_map = {}
        
        for field, possible_names in cls.COLUMN_MAPPINGS.items():
            for possible_name in possible_names:
                if possible_name in columns:
                    column_map[field] = possible_name
                    break
        
        return column_map


class MetadataIndicadorParser:
    """
    Parser para archivos de metadata del indicador (metadata.csv).
    Extrae información de la ficha técnica del indicador.
    """
    
    # Mapeo de nombres de columnas
    COLUMN_MAPPINGS = {
        'codigo_indicador': ['Codigo_Indicador', 'codigo_indicador', 'codigo', 'Codigo', 'ID_Indicador_SIIED'],
        'nombre_indicador': ['Nombre_Indicador', 'nombre_indicador', 'nombre', 'Nombre', 'Nombre indicador'],
        'sigla': ['Sigla', 'sigla', 'Sigla o abreviatura'],
        'grupo_indicador': ['Grupo_Indicador', 'grupo_indicador', 'grupo', 'Grupo indicador'],
        'descripcion': ['Descripcion', 'descripcion', 'Descripcion_Indicador', 'Descripción del indicador'],
        'definiciones_conceptos': ['Definiciones_Conceptos', 'definiciones_conceptos', 'definiciones'],
        'objetivo': ['Objetivo', 'objetivo'],
        'justificacion': ['Justificacion', 'justificacion'],
        'formula': ['Formula', 'formula'],
        'variables': ['Variables', 'variables'],
        'unidad_medida': ['Unidad_Medida', 'unidad_medida', 'unidad', 'Unidad de medida'],
        'tipo_medida': ['Tipo_Medida', 'tipo_medida', 'tipo'],
        'interpretacion': ['Interpretacion', 'interpretacion'],
        'limitaciones': ['Limitaciones', 'limitaciones'],
        'fuente_datos': ['Fuente_Datos', 'fuente_datos', 'fuente', 'Fuente de la información'],
        'periodicidad_actualizacion': ['Periodicidad_Actualizacion', 'periodicidad_actualizacion', 'periodicidad'],
        'desagregacion_tematica': ['Desagregacion_Tematica', 'desagregacion_tematica', 'desag_tematica'],
        'desagregacion_geografica': ['Desagregacion_Geografica', 'desagregacion_geografica', 'desag_geografica'],
        'cobertura_geografica': ['Cobertura_Geografica', 'cobertura_geografica', 'cobertura'],
        'cobertura_temporal': ['Cobertura_Temporal', 'cobertura_temporal'],
        'responsable_produccion': ['Responsable_Produccion', 'responsable_produccion', 'responsable'],
        'contacto': ['Contacto', 'contacto'],
        'observaciones': ['Observaciones', 'observaciones', 'obs'],
        'fecha_elaboracion': ['Fecha_Elaboracion', 'fecha_elaboracion', 'fecha'],
        'version': ['Version', 'version'],
        # Aliases plantilla SDMX (Metadatos_SDMX_Plantilla.xlsx)
        'metodo_medicion': ['Metodo_Medicion', 'metodo_medicion', 'Cálculo del indicador', 'Calculo del indicador'],
        'operacion_nombre': ['Nombre de la operación estadística', 'Operacion_Estadistica'],
        'nomenclaturas_clasificaciones': ['Nomenclaturas_Clasificaciones', 'Nomenclatura y clasificaciones estadísticas'],
        'alcance_tematico': ['Alcance_Tematico', 'alcance_tematico', 'Alcance temático'],
        'poblacion_objetivo': ['Poblacion_Objetivo', 'poblacion_objetivo', 'Población objetivo'],
        'periodo_referencia': ['Periodo_Referencia', 'periodo_referencia', 'Periodo de referencia'],
        'periodo_base': ['Periodo_Base', 'periodo_base', 'Periodo base'],
        'serie_historica_disponible': ['Serie_Historica_Disponible', 'Serie histórica disponible'],
        'frecuencia_difusion': ['Frecuencia_Difusion', 'frecuencia_difusion', 'Frecuencia de difusión'],
        'medios_difusion': ['Medios_Difusion', 'medios_difusion', 'Medios de difusión'],
        'comentarios_adicionales': ['Comentarios_Adicionales', 'comentarios_adicionales', 'Comentarios adicionales'],
        'referencias': ['Referencias', 'referencias'],
        'organismo_responsable_nombre': ['Organismo responsable', 'Entidad_Institucion'],
        'suborganismo_responsable': ['Suborganismo responsable', 'Suborganismo responsable del indicador', 'Area_Dependencia'],
        'equipo_responsable': ['Equipo_Responsable', 'Equipo responsable'],
        'nombre_responsable_validacion': ['Nombre_Responsable_Validacion', 'Nombre responsable técnico de validación'],
        'cargo_responsable_validacion': ['Cargo_Responsable_Validacion', 'Cargo responsable técnico de validación'],
        'correo_responsable_validacion': ['Correo_Responsable_Validacion', 'Correo electrónico del responsable técnico del indicador'],
        'celular_responsable_validacion': ['Celular_Responsable_Validacion', 'Celular responsable técnico de validación'],
        'correo_contacto': ['Correo_Contacto', 'correo_contacto', 'Dirección de correo electrónico de contacto'],
        'telefono_contacto': ['Telefono_Contacto', 'telefono_contacto'],
    }
    
    @classmethod
    def parse(cls, csv_path: str) -> Dict[str, Any]:
        """
        Parsea el archivo CSV de metadata del indicador.
        
        Args:
            csv_path: Ruta al archivo CSV
            
        Returns:
            Diccionario con la metadata del indicador
        """
        try:
            df = pd.read_csv(csv_path)
            
            # Normalizar nombres de columnas
            column_map = cls._build_column_map(df.columns)
            
            # Tomar la primera fila (asumimos que solo hay un indicador por archivo)
            if len(df) == 0:
                logger.warning(f"Archivo de metadata vacío: {csv_path}")
                return {}
            
            row = df.iloc[0]
            metadata = {}
            
            for field, possible_names in cls.COLUMN_MAPPINGS.items():
                actual_column = column_map.get(field)
                if actual_column and actual_column in df.columns:
                    value = row[actual_column]
                    # Convertir NaN a None
                    metadata[field] = None if pd.isna(value) else str(value)
                else:
                    metadata[field] = None
            
            logger.info(f"Parseada metadata de indicador desde {csv_path}")
            return metadata
            
        except Exception as e:
            logger.error(f"Error al parsear metadata de indicador: {e}")
            raise
    
    @classmethod
    def _build_column_map(cls, columns: List[str]) -> Dict[str, str]:
        """Construye mapeo de campos normalizados a nombres de columnas reales"""
        column_map = {}
        
        for field, possible_names in cls.COLUMN_MAPPINGS.items():
            for possible_name in possible_names:
                if possible_name in columns:
                    column_map[field] = possible_name
                    break
        
        return column_map


class DesagregacionesAnalyzer:
    """
    Analizador de desagregaciones mencionadas en archivos CSV.
    Detecta qué desagregaciones se usan y cuáles faltan en la BD.
    """
    
    @classmethod
    def analizar_desde_conjunto_datos(cls, csv_path: str, regla_extraccion: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Analiza qué desagregaciones se mencionan en el archivo de conjunto_datos.
        
        Args:
            csv_path: Ruta al archivo CSV de conjunto_datos
            regla_extraccion: Diccionario con información de la regla (opcional)
            
        Returns:
            Diccionario con análisis de desagregaciones geográficas y temáticas
        """
        try:
            df = pd.read_csv(csv_path, nrows=1000)  # Solo primeras 1000 filas para análisis
            
            # Detectar columnas que parecen desagregaciones
            columnas_geo = cls._detectar_columnas_geograficas(df.columns)
            columnas_tem = cls._detectar_columnas_tematicas(df.columns)
            
            analisis = {
                'geograficas': cls._analizar_columnas(df, columnas_geo, tipo='geografica'),
                'tematicas': cls._analizar_columnas(df, columnas_tem, tipo='tematica'),
            }
            
            return analisis
            
        except Exception as e:
            logger.error(f"Error al analizar desagregaciones: {e}")
            raise
    
    @classmethod
    def analizar_desde_serie(cls, csv_path: str) -> Dict[str, Any]:
        """
        Analiza qué desagregaciones se mencionan en el archivo de serie de datos.
        
        Args:
            csv_path: Ruta al archivo CSV de serie
            
        Returns:
            Diccionario con análisis de desagregaciones
        """
        try:
            df = pd.read_csv(csv_path)
            
            # Detectar columnas de desagregación
            columnas_geo = cls._detectar_columnas_geograficas(df.columns)
            columnas_tem = cls._detectar_columnas_tematicas(df.columns)
            
            analisis = {
                'geograficas': cls._analizar_columnas(df, columnas_geo, tipo='geografica'),
                'tematicas': cls._analizar_columnas(df, columnas_tem, tipo='tematica'),
            }
            
            return analisis
            
        except Exception as e:
            logger.error(f"Error al analizar desagregaciones: {e}")
            raise
    
    @classmethod
    def _detectar_columnas_geograficas(cls, columns: List[str]) -> List[str]:
        """Detecta columnas que parecen desagregaciones geográficas"""
        keywords = [
            'comuna', 'barrio', 'zona', 'localidad', 'municipio',
            'departamento', 'region', 'provincia', 'distrito',
            'geo', 'geografica', 'territorio', 'area'
        ]
        
        columnas_geo = []
        for col in columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in keywords):
                columnas_geo.append(col)
        
        return columnas_geo
    
    @classmethod
    def _detectar_columnas_tematicas(cls, columns: List[str]) -> List[str]:
        """Detecta columnas que parecen desagregaciones temáticas"""
        keywords = [
            'sexo', 'genero', 'edad', 'grupo_edad', 'rango_edad',
            'nivel_educativo', 'educacion', 'estrato', 'ingreso',
            'ocupacion', 'actividad', 'sector', 'categoria',
            'tipo', 'clase', 'grupo'
        ]
        
        columnas_tem = []
        for col in columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in keywords):
                columnas_tem.append(col)
        
        return columnas_tem
    
    @classmethod
    def _analizar_columnas(cls, df: pd.DataFrame, columnas: List[str], tipo: str) -> Dict[str, Any]:
        """
        Analiza columnas específicas y sus valores únicos.
        
        Args:
            df: DataFrame con los datos
            columnas: Lista de columnas a analizar
            tipo: 'geografica' o 'tematica'
            
        Returns:
            Diccionario con análisis
        """
        from .models import Desagregacion, DominioDesagregacion
        
        detectadas = []
        existentes = []
        faltantes = []
        dominios_sugeridos = []
        
        for columna in columnas:
            valores_unicos = df[columna].dropna().unique()
            
            for valor in valores_unicos:
                valor_str = str(valor).strip()
                if not valor_str:
                    continue
                
                detectadas.append({
                    'columna': columna,
                    'valor': valor_str
                })
                
                # Verificar si existe en la BD
                existe = Desagregacion.objects.filter(
                    nombre__iexact=valor_str,
                    dominio__tipo=tipo
                ).exists()
                
                if existe:
                    existentes.append(valor_str)
                else:
                    faltantes.append({
                        'columna': columna,
                        'valor': valor_str
                    })
        
        # Sugerir dominios basándose en las columnas
        dominios_sugeridos = cls._sugerir_dominios(columnas, tipo)
        
        return {
            'detectadas': detectadas,
            'existentes': existentes,
            'faltantes': faltantes,
            'dominios_sugeridos': dominios_sugeridos,
            'columnas_analizadas': columnas
        }
    
    @classmethod
    def _sugerir_dominios(cls, columnas: List[str], tipo: str) -> List[str]:
        """Sugiere nombres de dominios basándose en las columnas detectadas"""
        dominios = []
        
        for columna in columnas:
            col_lower = columna.lower()
            
            # Patrones comunes
            if 'comuna' in col_lower:
                dominios.append('Comunas')
            elif 'barrio' in col_lower:
                dominios.append('Barrios')
            elif 'zona' in col_lower:
                dominios.append('Zonas')
            elif 'sexo' in col_lower or 'genero' in col_lower:
                dominios.append('Sexo')
            elif 'edad' in col_lower:
                dominios.append('Grupo de Edad')
            elif 'educati' in col_lower:
                dominios.append('Nivel Educativo')
            elif 'estrato' in col_lower:
                dominios.append('Estrato Socioeconómico')
            else:
                # Capitalizar el nombre de la columna
                dominios.append(columna.replace('_', ' ').title())
        
        return list(set(dominios))  # Eliminar duplicados
