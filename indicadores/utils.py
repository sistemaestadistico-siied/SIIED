import csv
import io
import json
from django.utils import timezone
from django.core.management import call_command
from django.core.management.base import CommandError
from .models import Dato, Desagregacion

def procesar_conjunto_datos_para_indicador(indicador):
    """
    Procesa los datos de conjunto_datos para un indicador específico
    usando el nuevo comando con inferencia automática de desagregaciones
    """
    try:
        # Verificar que el indicador tenga conjunto_datos asociado
        if not indicador.conjunto_datos:
            raise Exception(f'El indicador {indicador.nombre} no tiene conjunto_datos asociado')
        
        # Verificar que el archivo de conjunto_datos exista
        if not indicador.conjunto_datos.archivo_csv:
            raise Exception(f'El conjunto_datos {indicador.conjunto_datos.nombre} no tiene archivo CSV asociado')
        
        # Verificar que el indicador tenga dominios de desagregación
        # Si no tiene dominios, se procesará sin desagregaciones
        if not indicador.dominios_desagregacion_geografica.exists() and not indicador.dominios_desagregacion_tematica.exists():
            print(f'Advertencia: El indicador {indicador.nombre} no tiene dominios de desagregación asociados. Se procesará sin desagregaciones.')
        
        # Obtener la regla de extracción
        try:
            regla = indicador.regla_extraccion
            # Actualizar estado a "procesando"
            regla.estado_procesamiento = 'procesando'
            regla.ultima_ejecucion = timezone.now()
            regla.save(update_fields=['estado_procesamiento', 'ultima_ejecucion'])
            print(f'[DEBUG] Regla actualizada a procesando: {regla.estado_procesamiento}, {regla.ultima_ejecucion}')
        except Exception as e:
            raise Exception(f'No se encontró regla de extracción para el indicador {indicador.nombre}: {str(e)}')
        
        # Verificar que la regla tenga columnas fuente definidas
        if not regla.columnas_fuente:
            raise Exception(f'La regla de extracción para el indicador {indicador.nombre} no tiene columnas fuente definidas')
        
        # Llamar al nuevo comando de procesamiento con inferencia automática
        try:
            # Ejecutar el comando de procesamiento cartesiano que maneja correctamente múltiples dominios temáticos
            output = call_command(
                'procesar_conjunto_datos_cartesiano',
                '--indicador-id', indicador.id,
                '--eliminar-datos-previos',
                stdout=io.StringIO(),
                stderr=io.StringIO()
            )
            
            # Actualizar estado a "completado"
            regla.estado_procesamiento = 'completado'
            regla.ultima_ejecucion = timezone.now()
            regla.save(update_fields=['estado_procesamiento', 'ultima_ejecucion'])
            print(f'[DEBUG] Regla actualizada a completado: {regla.estado_procesamiento}, {regla.ultima_ejecucion}')
            
            # Contar registros creados
            datos_count = Dato.objects.filter(indicador=indicador).count()
            
            return {
                'mensaje': f'Procesamiento completado exitosamente para {indicador.nombre}',
                'registros': datos_count,
                'estado': 'completado'
            }
            
        except CommandError as e:
            # Actualizar estado a "error"
            regla.estado_procesamiento = 'error'
            regla.ultima_ejecucion = timezone.now()
            regla.save(update_fields=['estado_procesamiento', 'ultima_ejecucion'])
            print(f'[DEBUG] Regla actualizada a error: {regla.estado_procesamiento}, {regla.ultima_ejecucion}')
            
            raise Exception(f'Error al ejecutar el comando de procesamiento: {str(e)}')
        
    except Exception as e:
        # Si ya se actualizó el estado a error, no hacerlo de nuevo
        try:
            regla = indicador.regla_extraccion
            if regla.estado_procesamiento != 'error':
                regla.estado_procesamiento = 'error'
                regla.ultima_ejecucion = timezone.now()
                regla.save(update_fields=['estado_procesamiento', 'ultima_ejecucion'])
                print(f'[DEBUG] Regla actualizada a error (catch): {regla.estado_procesamiento}, {regla.ultima_ejecucion}')
        except Exception as save_error:
            print(f'[ERROR] No se pudo actualizar el estado de la regla: {str(save_error)}')
        
        raise Exception(f'Error al procesar conjunto_datos para el indicador {indicador.nombre}: {str(e)}')

def evaluar_formula(formula, valores_columnas):
    """
    Evalúa una fórmula usando los valores de las columnas
    """
    if not formula:
        # Si no hay fórmula, devolver el primer valor disponible
        return next(iter(valores_columnas.values()), 0.0)
    
    # Reemplazar los nombres de columnas en la fórmula con sus valores
    formula_evaluable = formula
    for columna, valor in valores_columnas.items():
        formula_evaluable = formula_evaluable.replace(columna, str(valor))
    
    # Evaluar la fórmula
    # NOTA: En un entorno de producción, se debería usar una biblioteca
    # de evaluación segura en lugar de eval() para prevenir inyección de código
    try:
        resultado = eval(formula_evaluable)
        return float(resultado)
    except:
        return 0.0
