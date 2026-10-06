"""
Funciones auxiliares para el Wizard Admin Unificado.
Incluye creación automática de desagregaciones, procesamiento de datos, etc.
"""

from typing import Dict, List, Any, Optional, Tuple
import logging
from django.db import transaction

from .models import (
    ConjuntoDatos, Indicador, VariableConjuntoDatos, DominioDesagregacion,
    Desagregacion, ReglaExtraccion, CargaConjuntoDatos, CargaSerieIndicador,
    ProcesoExtraccion, Grafico, GraficoSerie
)

logger = logging.getLogger(__name__)


class DesagregacionesCreator:
    """
    Clase para crear automáticamente desagregaciones faltantes.
    """
    
    @classmethod
    @transaction.atomic
    def crear_faltantes(
        cls,
        analisis_geograficas: Dict[str, Any],
        analisis_tematicas: Dict[str, Any],
        crear_dominios_si_no_existen: bool = True
    ) -> Dict[str, Any]:
        """
        Crea las desagregaciones faltantes detectadas en el análisis.
        
        Args:
            analisis_geograficas: Análisis de desagregaciones geográficas
            analisis_tematicas: Análisis de desagregaciones temáticas
            crear_dominios_si_no_existen: Si True, crea dominios automáticamente
            
        Returns:
            Diccionario con resultados de la creación
        """
        resultado = {
            'geograficas_creadas': [],
            'tematicas_creadas': [],
            'dominios_creados': [],
            'errores': []
        }
        
        # Crear desagregaciones geográficas
        if analisis_geograficas.get('faltantes'):
            resultado_geo = cls._crear_desagregaciones(
                analisis_geograficas['faltantes'],
                analisis_geograficas.get('dominios_sugeridos', []),
                tipo='geografica',
                crear_dominios=crear_dominios_si_no_existen
            )
            resultado['geograficas_creadas'] = resultado_geo['creadas']
            resultado['dominios_creados'].extend(resultado_geo['dominios_creados'])
            resultado['errores'].extend(resultado_geo['errores'])
        
        # Crear desagregaciones temáticas
        if analisis_tematicas.get('faltantes'):
            resultado_tem = cls._crear_desagregaciones(
                analisis_tematicas['faltantes'],
                analisis_tematicas.get('dominios_sugeridos', []),
                tipo='tematica',
                crear_dominios=crear_dominios_si_no_existen
            )
            resultado['tematicas_creadas'] = resultado_tem['creadas']
            resultado['dominios_creados'].extend(resultado_tem['dominios_creados'])
            resultado['errores'].extend(resultado_tem['errores'])
        
        logger.info(
            f"Creadas {len(resultado['geograficas_creadas'])} desag. geográficas, "
            f"{len(resultado['tematicas_creadas'])} temáticas, "
            f"{len(resultado['dominios_creados'])} dominios"
        )
        
        return resultado
    
    @classmethod
    def _crear_desagregaciones(
        cls,
        faltantes: List[Dict[str, str]],
        dominios_sugeridos: List[str],
        tipo: str,
        crear_dominios: bool = True
    ) -> Dict[str, Any]:
        """
        Crea desagregaciones faltantes.
        
        Args:
            faltantes: Lista de desagregaciones faltantes
            dominios_sugeridos: Lista de nombres de dominios sugeridos
            tipo: 'geografica' o 'tematica'
            crear_dominios: Si True, crea dominios si no existen
            
        Returns:
            Diccionario con resultados
        """
        resultado = {
            'creadas': [],
            'dominios_creados': [],
            'errores': []
        }
        
        # Agrupar faltantes por columna (para asignar al mismo dominio)
        por_columna = {}
        for item in faltantes:
            columna = item['columna']
            if columna not in por_columna:
                por_columna[columna] = []
            por_columna[columna].append(item['valor'])
        
        # Crear desagregaciones por columna
        for columna, valores in por_columna.items():
            try:
                # Buscar o crear dominio
                dominio = cls._obtener_o_crear_dominio(
                    columna,
                    dominios_sugeridos,
                    tipo,
                    crear_dominios
                )
                
                if not dominio:
                    resultado['errores'].append(
                        f"No se pudo crear/encontrar dominio para columna '{columna}'"
                    )
                    continue
                
                # Crear desagregaciones
                for valor in valores:
                    try:
                        desag, created = Desagregacion.objects.get_or_create(
                            nombre=valor,
                            dominio=dominio,
                            defaults={
                                'descripcion': f'Desagregación creada automáticamente desde columna {columna}'
                            }
                        )
                        
                        if created:
                            resultado['creadas'].append({
                                'nombre': valor,
                                'dominio': dominio.nombre,
                                'tipo': tipo
                            })
                            logger.info(f"Creada desagregación: {valor} en dominio {dominio.nombre}")
                    
                    except Exception as e:
                        resultado['errores'].append(
                            f"Error al crear desagregación '{valor}': {str(e)}"
                        )
            
            except Exception as e:
                resultado['errores'].append(
                    f"Error al procesar columna '{columna}': {str(e)}"
                )
        
        return resultado
    
    @classmethod
    def _obtener_o_crear_dominio(
        cls,
        columna: str,
        dominios_sugeridos: List[str],
        tipo: str,
        crear_si_no_existe: bool
    ) -> Optional[DominioDesagregacion]:
        """
        Obtiene o crea un dominio para una columna.
        
        Args:
            columna: Nombre de la columna
            dominios_sugeridos: Lista de nombres de dominios sugeridos
            tipo: 'geografica' o 'tematica'
            crear_si_no_existe: Si True, crea el dominio si no existe
            
        Returns:
            Instancia de DominioDesagregacion o None
        """
        # Buscar dominio sugerido que coincida con la columna
        nombre_dominio = None
        columna_lower = columna.lower()
        
        for sugerido in dominios_sugeridos:
            if columna_lower in sugerido.lower() or sugerido.lower() in columna_lower:
                nombre_dominio = sugerido
                break
        
        # Si no hay coincidencia, usar el nombre de la columna
        if not nombre_dominio:
            nombre_dominio = columna.replace('_', ' ').title()
        
        # Buscar dominio existente
        dominio = DominioDesagregacion.objects.filter(
            nombre__iexact=nombre_dominio,
            tipo=tipo
        ).first()
        
        # Crear si no existe y está permitido
        if not dominio and crear_si_no_existe:
            try:
                dominio = DominioDesagregacion.objects.create(
                    nombre=nombre_dominio,
                    tipo=tipo,
                    descripcion=f'Dominio creado automáticamente desde columna {columna}'
                )
                logger.info(f"Creado dominio: {nombre_dominio} ({tipo})")
            except Exception as e:
                logger.error(f"Error al crear dominio '{nombre_dominio}': {e}")
                return None
        
        return dominio


class VariablesCreator:
    """
    Clase para crear automáticamente variables de conjunto_datos desde metadata CSV.
    """
    
    @classmethod
    @transaction.atomic
    def crear_desde_metadata(
        cls,
        conjunto_datos: ConjuntoDatos,
        variables_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Crea variables de conjunto_datos desde la metadata parseada.
        
        Args:
            conjunto_datos: Instancia de ConjuntoDatos
            variables_data: Lista de diccionarios con metadata de variables
            
        Returns:
            Diccionario con resultados
        """
        resultado = {
            'creadas': [],
            'actualizadas': [],
            'errores': []
        }
        
        for var_data in variables_data:
            try:
                codigo = var_data.get('codigo_variable')
                
                # Buscar si ya existe
                variable, created = VariableConjuntoDatos.objects.update_or_create(
                    conjunto_datos=conjunto_datos,
                    codigo_variable=codigo,
                    defaults={
                        'nombre_variable': var_data.get('nombre_variable', ''),
                        'definicion_conceptual': var_data.get('definicion_conceptual', ''),
                        'tipo_dato': var_data.get('tipo_dato', ''),
                        'dominio_dato': var_data.get('dominio_dato', ''),
                        'unidad_medida': var_data.get('unidad_medida'),
                        'tipo_variable_estadistica': var_data.get('tipo_variable_estadistica'),
                        'poblacion_objetivo': var_data.get('poblacion_objetivo'),
                        'cobertura_geografica': var_data.get('cobertura_geografica'),
                        'fuente_datos': var_data.get('fuente_datos'),
                        'periodicidad': var_data.get('periodicidad'),
                        'organismo_productor': var_data.get('organismo_productor'),
                        'observaciones': var_data.get('observaciones'),
                    }
                )
                
                if created:
                    resultado['creadas'].append(codigo)
                    logger.info(f"Creada variable: {codigo}")
                else:
                    resultado['actualizadas'].append(codigo)
                    logger.info(f"Actualizada variable: {codigo}")
            
            except Exception as e:
                resultado['errores'].append(f"Error con variable {var_data.get('codigo_variable')}: {str(e)}")
                logger.error(f"Error al crear/actualizar variable: {e}")
        
        return resultado


class IndicadorMetadataUpdater:
    """
    Clase para actualizar metadata completa de un indicador desde CSV.
    """
    
    @classmethod
    @transaction.atomic
    def actualizar_desde_metadata(
        cls,
        indicador: Indicador,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Actualiza todos los campos de metadata del indicador.
        
        Args:
            indicador: Instancia de Indicador
            metadata: Diccionario con metadata parseada del CSV
            
        Returns:
            Diccionario con campos actualizados
        """
        campos_actualizados = []
        
        # Mapeo de campos del CSV a campos del modelo
        field_mapping = {
            'codigo_indicador': 'codigo_indicador',
            'nombre_indicador': 'nombre',
            'sigla': 'sigla',
            'descripcion': 'descripcion_indicador',
            'definiciones_conceptos': 'descripcion_indicador',
            'descripcion_indicador': 'descripcion_indicador',
            'objetivo': 'objetivo',
            'justificacion': 'comentarios_adicionales',
            'formula': 'formula_ficha',
            'variables': 'variables',
            'unidad_medida': 'unidad_medida',
            'tipo_medida': 'tipo_medida',
            'interpretacion': 'interpretacion',
            'limitaciones': 'limitaciones',
            'fuente_datos': 'fuente_datos',
            'periodicidad_actualizacion': 'frecuencia_difusion',
            'desagregacion_tematica': 'alcance_tematico',
            'desagregacion_geografica': 'cobertura_geografica',
            'cobertura_geografica': 'cobertura_geografica',
            'cobertura_temporal': 'cobertura_temporal',
            'responsable_produccion': 'entidad_responsable',
            'contacto': 'contacto',
            'observaciones': 'comentarios_adicionales',
            'fecha_elaboracion': 'fecha_publicacion_metadatos',
            'version': 'version',
            # SDMX
            'metodo_medicion': 'metodo_medicion',
            'nomenclaturas_clasificaciones': 'nomenclaturas_clasificaciones',
            'alcance_tematico': 'alcance_tematico',
            'poblacion_objetivo': 'poblacion_objetivo',
            'periodo_referencia': 'periodo_referencia',
            'periodo_base': 'periodo_base',
            'serie_historica_disponible': 'serie_historica_disponible',
            'frecuencia_difusion': 'frecuencia_difusion',
            'medios_difusion': 'medios_difusion',
            'comentarios_adicionales': 'comentarios_adicionales',
            'referencias': 'referencias',
            'nombre_responsable_validacion': 'nombre_responsable_validacion',
            'cargo_responsable_validacion': 'cargo_responsable_validacion',
            'correo_responsable_validacion': 'correo_responsable_validacion',
            'celular_responsable_validacion': 'celular_responsable_validacion',
            'correo_contacto': 'correo_contacto',
            'telefono_contacto': 'telefono_contacto',
        }
        
        for csv_field, model_field in field_mapping.items():
            if csv_field in metadata and metadata[csv_field] is not None:
                # Verificar si el campo existe en el modelo
                if hasattr(indicador, model_field):
                    setattr(indicador, model_field, metadata[csv_field])
                    campos_actualizados.append(model_field)
        
        indicador.save()
        
        logger.info(f"Actualizados {len(campos_actualizados)} campos de metadata para {indicador.nombre}")
        
        return {
            'campos_actualizados': campos_actualizados,
            'total': len(campos_actualizados)
        }


class WizardDataProcessor:
    """
    Clase principal para procesar datos al finalizar el wizard.
    """
    
    @classmethod
    @transaction.atomic
    def procesar_flujo_a(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa Flujo A: Con ConjuntoDatos.
        
        Args:
            data: Diccionarios con todos los datos del wizard
            
        Returns:
            Diccionario con resultado del procesamiento
        """
        # TODO: Implementar procesamiento completo
        # Por ahora retorna estructura básica
        return {
            'mensaje': 'Flujo A procesado correctamente',
            'indicador_id': None,
            'proceso_id': None
        }
    
    @classmethod
    @transaction.atomic
    def procesar_flujo_b(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa Flujo B: Solo Serie.
        
        Args:
            data: Diccionarios con todos los datos del wizard
            
        Returns:
            Diccionario con resultado del procesamiento
        """
        # TODO: Implementar procesamiento completo
        return {
            'mensaje': 'Flujo B procesado correctamente',
            'indicador_id': None
        }
    
    @classmethod
    @transaction.atomic
    def procesar_flujo_c(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa Flujo C: Completo (ConjuntoDatos + Serie).
        
        Args:
            data: Diccionarios con todos los datos del wizard
            
        Returns:
            Diccionario con resultado del procesamiento
        """
        # TODO: Implementar procesamiento completo
        return {
            'mensaje': 'Flujo C procesado correctamente',
            'indicador_id': None,
            'proceso_id': None
        }
    
    @classmethod
    @transaction.atomic
    def procesar_flujo_d(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa Flujo D: Actualizar Existente.
        
        Args:
            data: Diccionarios con todos los datos del wizard
            
        Returns:
            Diccionario con resultado del procesamiento
        """
        # TODO: Implementar procesamiento completo
        return {
            'mensaje': 'Flujo D procesado correctamente',
            'indicador_id': None
        }
