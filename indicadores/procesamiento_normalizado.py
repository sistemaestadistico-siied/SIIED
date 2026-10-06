"""
Módulo de procesamiento normalizado para ConjuntoDatos e Indicadores.
Proporciona funciones reutilizables desde el wizard y otras partes de la aplicación.
"""

from typing import Dict, Any, Optional
from django.core.management import call_command
from io import StringIO
import sys


def procesar_conjunto_datos_a_indicador(
    carga_conjunto_datos_id: int,
    regla_extraccion_id: int,
    eliminar_datos_previos: bool = True,
    crear_faltantes: bool = False,
    verbosity: int = 1
) -> Dict[str, Any]:
    """
    Procesa una conjunto_datos aplicando regla de extracción y producto cartesiano.
    
    Esta función envuelve el comando de management 'procesar_conjunto_datos_cartesiano'
    para ser llamada programáticamente desde el wizard o vistas.
    
    Args:
        carga_conjunto_datos_id: ID de la carga de conjunto_datos
        regla_extraccion_id: ID de la regla de extracción a aplicar
        eliminar_datos_previos: Si True, elimina datos existentes del indicador
        verbosity: Nivel de detalle de logs (0-3)
    
    Returns:
        Dict con resultado del procesamiento:
        {
            'exitoso': bool,
            'registros_procesados': int,
            'registros_exitosos': int,
            'registros_error': int,
            'mensaje': str,
            'output': str  # Output completo del comando
        }
    """
    from .models import CargaConjuntoDatos, ReglaExtraccion, Indicador
    
    try:
        # Verificar que existan los objetos
        carga = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
        regla = ReglaExtraccion.objects.get(id=regla_extraccion_id)
        indicador = regla.indicador
        
        # Capturar output del comando
        output_buffer = StringIO()
        
        # Ejecutar comando
        call_command(
            'procesar_conjunto_datos_cartesiano',
            regla_id=regla_extraccion_id,
            eliminar_datos_previos=eliminar_datos_previos,
            crear_faltantes=crear_faltantes,
            verbosity=verbosity,
            stdout=output_buffer,
            stderr=output_buffer
        )
        
        # Obtener output
        output = output_buffer.getvalue()
        
        # Contar datos creados
        registros_exitosos = indicador.datos.count()
        
        return {
            'exitoso': True,
            'registros_procesados': registros_exitosos,  # Aproximación
            'registros_exitosos': registros_exitosos,
            'registros_error': 0,
            'mensaje': f'Procesamiento cartesiano completado. {registros_exitosos} datos generados.',
            'output': output,
            'indicador_id': indicador.id,
            'regla_id': regla.id
        }
    
    except Exception as e:
        return {
            'exitoso': False,
            'registros_procesados': 0,
            'registros_exitosos': 0,
            'registros_error': 1,
            'mensaje': f'Error en procesamiento: {str(e)}',
            'output': str(e),
            'error': str(e)
        }


def procesar_serie_a_indicador(
    carga_serie_id: int,
    indicador_id: int,
    columna_fecha: str,
    columna_valor: str,
    eliminar_datos_previos: bool = False
) -> Dict[str, Any]:
    """
    Procesa una serie de datos agregados importándola directamente.
    
    Args:
        carga_serie_id: ID de la carga de serie
        indicador_id: ID del indicador destino
        columna_fecha: Nombre de la columna que contiene fechas
        columna_valor: Nombre de la columna que contiene valores
        eliminar_datos_previos: Si True, elimina datos existentes
    
    Returns:
        Dict con resultado del procesamiento
    """
    from .models import CargaSerieIndicador, Indicador, Dato
    import pandas as pd
    from datetime import datetime
    
    try:
        carga = CargaSerieIndicador.objects.get(id=carga_serie_id)
        indicador = Indicador.objects.get(id=indicador_id)
        
        # Eliminar datos previos si se solicita
        if eliminar_datos_previos:
            indicador.datos.all().delete()
        
        # Leer archivo CSV
        archivo_path = carga.archivo_datos_csv.path if carga.archivo_datos_csv else carga.archivo_datos_xlsx.path
        
        if archivo_path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(archivo_path)
        else:
            df = pd.read_csv(archivo_path, sep=';')
        
        # Validar columnas
        if columna_fecha not in df.columns:
            raise ValueError(f"Columna '{columna_fecha}' no encontrada en el archivo")
        if columna_valor not in df.columns:
            raise ValueError(f"Columna '{columna_valor}' no encontrada en el archivo")
        
        # Importar datos
        registros_exitosos = 0
        registros_error = 0
        
        for index, row in df.iterrows():
            try:
                fecha_valor = row[columna_fecha]
                valor = row[columna_valor]
                
                # Convertir fecha (año int/float/string o fecha completa).
                # Import lazy: wizard_admin_unificado importa este módulo.
                from .wizard_admin_unificado import _parsear_fecha_dato
                fecha_dato = _parsear_fecha_dato(fecha_valor)
                if fecha_dato is None:
                    raise ValueError(f"Fecha no interpretable: {fecha_valor!r}")
                
                # Crear dato
                Dato.objects.create(
                    indicador=indicador,
                    fecha_dato=fecha_dato,
                    valor_dato=float(valor)
                )
                registros_exitosos += 1
            
            except Exception as e:
                registros_error += 1
                continue
        
        return {
            'exitoso': True,
            'registros_procesados': len(df),
            'registros_exitosos': registros_exitosos,
            'registros_error': registros_error,
            'mensaje': f'Serie importada. {registros_exitosos} de {len(df)} registros creados.',
            'indicador_id': indicador.id
        }
    
    except Exception as e:
        return {
            'exitoso': False,
            'registros_procesados': 0,
            'registros_exitosos': 0,
            'registros_error': 1,
            'mensaje': f'Error al procesar serie: {str(e)}',
            'error': str(e)
        }


def diagnosticar_conjunto_datos(regla_extraccion_id: int) -> Dict[str, Any]:
    """
    Ejecuta diagnóstico de conjunto_datos antes del procesamiento.
    Envuelve el comando 'diagnosticar_conjunto_datos'.
    
    Args:
        regla_extraccion_id: ID de la regla de extracción
    
    Returns:
        Dict con resultado del diagnóstico
    """
    from io import StringIO
    from django.core.management import call_command
    from .models import ReglaExtraccion
    
    try:
        regla = ReglaExtraccion.objects.get(id=regla_extraccion_id)
        indicador = regla.indicador
        
        if not indicador.conjunto_datos:
            raise ValueError("El indicador no tiene conjunto_datos asociada")
        
        # Capturar output
        output_buffer = StringIO()
        
        # Ejecutar comando
        call_command(
            'diagnosticar_conjunto_datos',
            conjunto_datos_id=indicador.conjunto_datos.id,
            stdout=output_buffer,
            stderr=output_buffer
        )
        
        output = output_buffer.getvalue()
        
        # TODO: Parsear output para extraer información estructurada
        # Por ahora retornamos el output raw
        
        return {
            'exitoso': True,
            'output': output,
            'mensaje': 'Diagnóstico completado'
        }
    
    except Exception as e:
        return {
            'exitoso': False,
            'output': str(e),
            'mensaje': f'Error en diagnóstico: {str(e)}',
            'error': str(e)
        }


def crear_graficos_automaticos(indicador_id: int) -> Dict[str, Any]:
    """
    Crea gráficos automáticos para un indicador basándose en sus datos.
    
    Args:
        indicador_id: ID del indicador
    
    Returns:
        Dict con resultado de la creación
    """
    from .models import Indicador, Grafico, GraficoSerie
    
    try:
        indicador = Indicador.objects.get(id=indicador_id)
        
        # Verificar que tenga datos
        if not indicador.datos.exists():
            return {
                'exitoso': False,
                'mensaje': 'El indicador no tiene datos para graficar',
                'graficos_creados': 0
            }
        
        # Crear gráfico de línea temporal por defecto
        grafico, created = Grafico.objects.get_or_create(
            indicador=indicador,
            tipo_grafico='line',
            defaults={
                'nombre': f'Evolución de {indicador.nombre}',
                'descripcion': f'Serie temporal de {indicador.nombre}',
                'activo': True,
                'titulo': indicador.nombre,
                'eje_x_titulo': 'Año',
                'eje_y_titulo': indicador.unidad_medida or 'Valor',
                'mostrar_leyenda': True,
                'posicion_leyenda': 'right',
                'mostrar_cuadricula': True,
                'begin_at_zero': False,
                'orden': 1
            }
        )
        
        if created:
            # Crear serie del gráfico
            GraficoSerie.objects.create(
                grafico=grafico,
                nombre_personalizado=indicador.nombre,
                orden=1
            )
            
            return {
                'exitoso': True,
                'graficos_creados': 1,
                'mensaje': f'Gráfico "{grafico.nombre}" creado exitosamente',
                'grafico_id': grafico.id
            }
        else:
            return {
                'exitoso': True,
                'graficos_creados': 0,
                'mensaje': 'El gráfico ya existía',
                'grafico_id': grafico.id
            }
    
    except Exception as e:
        return {
            'exitoso': False,
            'graficos_creados': 0,
            'mensaje': f'Error al crear gráficos: {str(e)}',
            'error': str(e)
        }
