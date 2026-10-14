"""
Vistas para importación masiva de Indicadores y Datos desde CSV
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.utils import timezone
from .forms_import import ImportarIndicadoresForm, ImportarDatosForm
from .models import Indicador, Dato, MenuSubtema, OperacionEstadistica, DominioDesagregacion, Desagregacion
import pandas as pd
import io
from datetime import datetime


@staff_member_required
def importar_indicadores(request):
    """
    Vista para importar múltiples indicadores desde un archivo CSV
    """
    if request.method == 'POST':
        form = ImportarIndicadoresForm(request.POST, request.FILES)
        
        if form.is_valid():
            archivo_csv = request.FILES['archivo_csv']
            eliminar_existentes = form.cleaned_data['eliminar_existentes']
            actualizar_existentes = form.cleaned_data['actualizar_existentes']
            
            try:
                # Leer el CSV
                df = pd.read_csv(archivo_csv)
                
                # Preview: mostrar las primeras filas y pedir confirmación
                if 'confirmar' not in request.POST:
                    context = {
                        'form': form,
                        'preview': True,
                        'df_head': df.head(10).to_html(classes='table table-striped', index=False),
                        'total_filas': len(df),
                        'columnas': list(df.columns),
                        'eliminar_existentes': eliminar_existentes,
                        'actualizar_existentes': actualizar_existentes,
                    }
                    return render(request, 'admin/importar_indicadores.html', context)
                
                # Procesar la importación
                resultado = procesar_importacion_indicadores(
                    df, 
                    eliminar_existentes=eliminar_existentes,
                    actualizar_existentes=actualizar_existentes
                )
                
                # Mostrar resultados
                if resultado['errores']:
                    messages.warning(
                        request,
                        f"Importación completada con errores. "
                        f"Creados: {resultado['creados']}, "
                        f"Actualizados: {resultado['actualizados']}, "
                        f"Errores: {resultado['errores']}"
                    )
                else:
                    messages.success(
                        request,
                        f"✅ Importación exitosa! "
                        f"Creados: {resultado['creados']}, "
                        f"Actualizados: {resultado['actualizados']}"
                    )
                
                # Guardar log detallado en la sesión para mostrarlo
                request.session['import_log'] = resultado['log']
                
                return redirect('admin:indicadores_indicador_changelist')
                
            except Exception as e:
                messages.error(request, f'Error al procesar el archivo: {str(e)}')
    else:
        form = ImportarIndicadoresForm()
    
    context = {
        'form': form,
        'title': 'Importar Indicadores desde CSV',
        'preview': False,
    }
    return render(request, 'admin/importar_indicadores.html', context)


def procesar_importacion_indicadores(df, eliminar_existentes=False, actualizar_existentes=True):
    """
    Procesa la importación de indicadores desde un DataFrame
    
    Columnas esperadas en el CSV:
    - nombre (requerido)
    - subtema (requerido) - nombre o ID del subtema
    - descripcion (opcional)
    - definicion_operacional (opcional)
    - unidad_medida (opcional)
    - fuente_datos (opcional)
    - entidad_responsable (opcional; antes entidad_recopiladora)
    - periodicidad (opcional)
    - fecha_actualizacion (opcional) - formato YYYY-MM-DD
    - notas (opcional)
    - operacion (opcional) - nombre o ID de la operación estadística
    - activo (opcional) - True/False, 1/0, Si/No
    - orden (opcional) - número entero
    - mostrar_mapa (opcional) - True/False, 1/0, Si/No
    - dominios_tematicos (opcional) - IDs o nombres separados por coma
    - dominios_geograficos (opcional) - IDs o nombres separados por coma
    """
    resultado = {
        'creados': 0,
        'actualizados': 0,
        'errores': 0,
        'log': []
    }
    
    with transaction.atomic():
        # Eliminar existentes si se solicita
        if eliminar_existentes:
            count = Indicador.objects.all().delete()[0]
            resultado['log'].append(f'🗑️ Eliminados {count} indicadores existentes')
        
        # Procesar cada fila
        for index, row in df.iterrows():
            try:
                # Obtener datos básicos
                nombre = str(row['nombre']).strip()
                subtema_valor = str(row['subtema']).strip()
                
                # Buscar el subtema
                subtema = None
                try:
                    # Intentar por ID
                    subtema = MenuSubtema.objects.get(id=int(subtema_valor))
                except (ValueError, MenuSubtema.DoesNotExist):
                    # Intentar por nombre
                    subtema = MenuSubtema.objects.filter(nombre__iexact=subtema_valor).first()
                
                if not subtema:
                    resultado['errores'] += 1
                    resultado['log'].append(f'❌ Fila {index+2}: Subtema "{subtema_valor}" no encontrado')
                    continue
                
                # Preparar datos del indicador
                datos_indicador = {
                    'nombre': nombre,
                    'subtema': subtema,
                    'descripcion': row.get('descripcion', ''),
                    'definicion_operacional': row.get('definicion_operacional', ''),
                    'unidad_medida': row.get('unidad_medida', ''),
                    'fuente_datos': row.get('fuente_datos', ''),
                    'entidad_responsable': row.get('entidad_responsable', row.get('entidad_recopiladora', '')),
                    'frecuencia_difusion': row.get('frecuencia_difusion', row.get('periodicidad', '')),
                    'referencias': row.get('referencias', ''),
                    'nombre_responsable_validacion': row.get('nombre_responsable_validacion', ''),
                    'cargo_responsable_validacion': row.get('cargo_responsable_validacion', ''),
                    'correo_responsable_validacion': row.get('correo_responsable_validacion', ''),
                    'celular_responsable_validacion': row.get('celular_responsable_validacion', ''),
                    'notas': row.get('notas', ''),
                    'orden': int(row.get('orden', 0)) if pd.notna(row.get('orden')) else 0,
                }
                
                # Procesar fecha_actualizacion
                if 'fecha_actualizacion' in row and pd.notna(row['fecha_actualizacion']):
                    try:
                        datos_indicador['fecha_publicacion_metadatos'] = pd.to_datetime(row['fecha_actualizacion']).date()
                    except:
                        pass
                
                # Procesar campo activo
                if 'activo' in row and pd.notna(row['activo']):
                    valor_activo = str(row['activo']).lower()
                    datos_indicador['activo'] = valor_activo in ['true', '1', 'si', 'sí', 'yes', 'y']
                
                # Procesar mostrar_mapa
                if 'mostrar_mapa' in row and pd.notna(row['mostrar_mapa']):
                    valor_mapa = str(row['mostrar_mapa']).lower()
                    datos_indicador['mostrar_mapa'] = valor_mapa in ['true', '1', 'si', 'sí', 'yes', 'y']
                
                # Buscar operación estadística
                if 'operacion' in row and pd.notna(row['operacion']):
                    operacion_valor = str(row['operacion']).strip()
                    try:
                        operacion = OperacionEstadistica.objects.get(id=int(operacion_valor))
                        datos_indicador['operacion'] = operacion
                    except (ValueError, OperacionEstadistica.DoesNotExist):
                        operacion = OperacionEstadistica.objects.filter(nombre__iexact=operacion_valor).first()
                        if operacion:
                            datos_indicador['operacion'] = operacion
                
                # Crear o actualizar indicador
                indicador_existente = Indicador.objects.filter(nombre=nombre).first()
                
                if indicador_existente and actualizar_existentes:
                    # Actualizar
                    for key, value in datos_indicador.items():
                        setattr(indicador_existente, key, value)
                    indicador_existente.save()
                    indicador = indicador_existente
                    resultado['actualizados'] += 1
                    resultado['log'].append(f'✏️ Fila {index+2}: Actualizado "{nombre}"')
                elif not indicador_existente:
                    # Crear nuevo
                    indicador = Indicador.objects.create(**datos_indicador)
                    resultado['creados'] += 1
                    resultado['log'].append(f'✅ Fila {index+2}: Creado "{nombre}"')
                else:
                    # Ya existe y no se debe actualizar
                    resultado['log'].append(f'⏭️ Fila {index+2}: Omitido "{nombre}" (ya existe)')
                    continue
                
                # Procesar dominios temáticos
                if 'dominios_tematicos' in row and pd.notna(row['dominios_tematicos']):
                    dominios_str = str(row['dominios_tematicos']).strip()
                    if dominios_str:
                        dominios_ids = [d.strip() for d in dominios_str.split(',')]
                        dominios = []
                        for dom_id in dominios_ids:
                            try:
                                dom = DominioDesagregacion.objects.get(id=int(dom_id), tipo='tematica')
                                dominios.append(dom)
                            except (ValueError, DominioDesagregacion.DoesNotExist):
                                dom = DominioDesagregacion.objects.filter(nombre__iexact=dom_id, tipo='tematica').first()
                                if dom:
                                    dominios.append(dom)
                        
                        if dominios:
                            indicador.dominios_desagregacion_tematica.set(dominios)
                
                # Procesar dominios geográficos
                if 'dominios_geograficos' in row and pd.notna(row['dominios_geograficos']):
                    dominios_str = str(row['dominios_geograficos']).strip()
                    if dominios_str:
                        dominios_ids = [d.strip() for d in dominios_str.split(',')]
                        dominios = []
                        for dom_id in dominios_ids:
                            try:
                                dom = DominioDesagregacion.objects.get(id=int(dom_id), tipo='geografica')
                                dominios.append(dom)
                            except (ValueError, DominioDesagregacion.DoesNotExist):
                                dom = DominioDesagregacion.objects.filter(nombre__iexact=dom_id, tipo='geografica').first()
                                if dom:
                                    dominios.append(dom)
                        
                        if dominios:
                            indicador.dominios_desagregacion_geografica.set(dominios)
                
                # Subtemas adicionales (opcional): nombres o IDs separados
                # por ';' o ','. El indicador queda clasificado también bajo
                # esos subtemas, aunque sean de otro dominio.
                if 'subtemas_adicionales' in row and pd.notna(row['subtemas_adicionales']):
                    adic_str = str(row['subtemas_adicionales']).strip()
                    if adic_str:
                        adicionales = []
                        for valor in adic_str.replace(';', ',').split(','):
                            valor = valor.strip()
                            if not valor:
                                continue
                            try:
                                st = MenuSubtema.objects.get(id=int(valor))
                            except (ValueError, MenuSubtema.DoesNotExist):
                                st = MenuSubtema.objects.filter(
                                    nombre__iexact=valor).first()
                            if st and st.id != indicador.subtema_id:
                                adicionales.append(st)
                        if adicionales:
                            indicador.subtemas_adicionales.add(*adicionales)
                            resultado['log'].append(
                                f'   ↳ Fila {index+2}: +{len(adicionales)} '
                                f'subtema(s) adicional(es) en "{nombre}"')
                
            except Exception as e:
                resultado['errores'] += 1
                resultado['log'].append(f'❌ Fila {index+2}: Error - {str(e)}')
    
    return resultado


@staff_member_required
def importar_datos(request):
    """
    Vista para importar múltiples datos desde un archivo CSV
    (Se implementará en la siguiente fase)
    """
    messages.info(request, 'La importación de Datos estará disponible próximamente')
    return redirect('admin:indicadores_dato_changelist')
