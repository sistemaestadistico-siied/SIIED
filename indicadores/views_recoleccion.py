"""
Vistas para el módulo de Recolección
Permite a usuarios con rol de recolector cargar datos
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, FileResponse
from django.utils import timezone
from django.db.models import Count, Q, Prefetch
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.files.base import ContentFile
from django.conf import settings
from django.db import transaction

import pandas as pd
import openpyxl
from io import BytesIO
import csv
import os
from datetime import datetime

from .models import (
    PerfilRecolector, CargaSerieIndicador, CargaConjuntoDatos, CargaMasivaSerie,
    Indicador, Dato, ConjuntoDatos, VariableConjuntoDatos, Grafico, Organismo,
    EquipoOrganismo, Suborganismo, OperacionEstadistica
)
from .decorators import recolector_required, admin_required


# ============================================================================
# AUTENTICACIÓN
# ============================================================================

def recoleccion_login(request):
    """Vista de login para recolectores"""
    if request.user.is_authenticated:
        # Si ya está autenticado, verificar permisos
        if request.user.is_staff:
            # Los administradores staff tienen acceso directo
            return redirect('indicadores:recoleccion_dashboard')
        elif hasattr(request.user, 'perfil_recolector') and request.user.perfil_recolector.puede_recolectar():
            return redirect('indicadores:recoleccion_dashboard')
        else:
            # Si no tiene permisos de recolector, hacer logout y mostrar mensaje
            # Esto evita el loop de redirecciones
            auth_logout(request)
            messages.warning(request, 'No tiene permisos para acceder al módulo de recolección. Por favor inicie sesión con una cuenta autorizada.')
            # No redirigir, mostrar el formulario de login con el mensaje
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Verificar permisos
            if user.is_staff:
                # Los administradores tienen acceso total
                auth_login(request, user)
                messages.success(request, f'Bienvenido Administrador {user.get_full_name() or user.username}')
                return redirect('indicadores:recoleccion_dashboard')
            elif hasattr(user, 'perfil_recolector') and user.perfil_recolector.puede_recolectar():
                auth_login(request, user)
                messages.success(request, f'Bienvenido {user.get_full_name() or user.username}')
                return redirect('indicadores:recoleccion_dashboard')
            else:
                messages.error(request, 'No tiene permisos para acceder al módulo de recolección o su cuenta está inactiva')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos')
    
    return render(request, 'recoleccion/login.html')


@login_required(login_url='/recoleccion/login/')
def recoleccion_logout(request):
    """Vista de logout para recolectores"""
    auth_logout(request)
    messages.success(request, 'Sesión cerrada exitosamente')
    return redirect('indicadores:recoleccion_login')


# ============================================================================
# DASHBOARD
# ============================================================================

@recolector_required
def recoleccion_dashboard(request):
    """Dashboard principal del módulo de recolección"""
    # El decorador ya verificó los permisos (staff o perfil_recolector)
    # No necesitamos verificar de nuevo aquí
    
    # Estadísticas del usuario
    total_cargas_series = CargaSerieIndicador.objects.filter(usuario=request.user).count()
    total_cargas_conjuntos_datos = CargaConjuntoDatos.objects.filter(usuario=request.user).count()
    
    cargas_series_exitosas = CargaSerieIndicador.objects.filter(
        usuario=request.user, estado='exitoso'
    ).count()
    cargas_conjuntos_datos_exitosas = CargaConjuntoDatos.objects.filter(
        usuario=request.user, estado='exitoso'
    ).count()
    
    # Últimas cargas
    ultimas_series = CargaSerieIndicador.objects.filter(
        usuario=request.user
    ).select_related('indicador').order_by('-fecha_carga')[:5]
    
    ultimos_conjuntos_datos = CargaConjuntoDatos.objects.filter(
        usuario=request.user
    ).order_by('-fecha_carga')[:5]
    
    # Cargas con correcciones solicitadas por el admin
    cargas_con_correcciones = CargaSerieIndicador.objects.filter(
        usuario=request.user,
        estado='correcciones_solicitadas'
    ).select_related('indicador').order_by('-fecha_carga')

    # Cargas masivas en proceso (validación del recolector o despachadas)
    masivas_activas = (
        CargaMasivaSerie.objects.filter(
            usuario=request.user,
            estado__in=('validacion_recolector', 'despachada')
        )
        .prefetch_related('cargas_series__indicador')
        .order_by('-fecha_carga')[:5]
    )

    # Indicadores activos sin carga exitosa por este usuario
    indicadores_con_carga = CargaSerieIndicador.objects.filter(
        usuario=request.user, estado='exitoso'
    ).values_list('indicador_id', flat=True)
    indicadores_pendientes = Indicador.objects.filter(
        activo=True
    ).exclude(id__in=indicadores_con_carga).order_by('codigo_indicador')[:15]
    
    # Obtener perfil si existe (para usuarios no-staff)
    perfil = getattr(request.user, 'perfil_recolector', None)
    
    context = {
        'perfil': perfil,
        'total_cargas_series': total_cargas_series,
        'total_cargas_conjuntos_datos': total_cargas_conjuntos_datos,
        'cargas_series_exitosas': cargas_series_exitosas,
        'cargas_conjuntos_datos_exitosas': cargas_conjuntos_datos_exitosas,
        'ultimas_series': ultimas_series,
        'ultimos_conjuntos_datos': ultimos_conjuntos_datos,
        'cargas_con_correcciones': cargas_con_correcciones,
        'masivas_activas': masivas_activas,
        'indicadores_pendientes': indicadores_pendientes,
    }
    
    return render(request, 'recoleccion/dashboard.html', context)


# ============================================================================
# CARGA DE SERIES DE INDICADORES
# ============================================================================

def _all_dominios_info(tipo, asociados_ids=None):
    """Retorna todos los dominios de desagregación del tipo dado con sus desagregaciones.
    Si asociados_ids se proporciona, marca cada dominio con 'asociado'=True si está en el set."""
    from .models import DominioDesagregacion, Desagregacion
    from django.db.models import Prefetch
    if asociados_ids is None:
        asociados_ids = set()
    dominios = (
        DominioDesagregacion.objects.filter(tipo=tipo)
        .prefetch_related(Prefetch(
            'desagregaciones', queryset=Desagregacion.objects.order_by('nombre')
        ))
        .order_by('nombre')
    )
    info = []
    for d in dominios:
        desag_list = list(d.desagregaciones.all())
        info.append({
            'nombre': d.nombre,
            'desagregaciones': [des.nombre for des in desag_list[:10]],
            'total': len(desag_list),
            'asociado': d.id in asociados_ids,
        })
    return info

@login_required(login_url='/recoleccion/login/')
def cargar_serie_indicador(request):
    """Página para cargar series de indicadores"""
    if request.method == 'POST':
        try:
            archivo_datos = request.FILES.get('archivo_datos')
            archivo_metadata = request.FILES.get('archivo_metadata')
            indicador_id = request.POST.get('indicador_id')
            
            if not archivo_datos:
                messages.error(request, 'Debe subir el archivo de datos del indicador')
                return redirect('indicadores:cargar_serie_indicador')
            
            if not indicador_id:
                messages.error(request, 'Debe seleccionar un indicador')
                return redirect('indicadores:cargar_serie_indicador')

            _ext_validas = ('.xlsx', '.xls', '.csv')
            if not archivo_datos.name.lower().endswith(_ext_validas):
                messages.error(request, 'El archivo de datos debe ser Excel (.xlsx, .xls) o CSV (.csv).')
                return redirect('indicadores:cargar_serie_indicador')
            if archivo_metadata and not archivo_metadata.name.lower().endswith(_ext_validas):
                messages.error(request, 'El archivo de metadata debe ser Excel (.xlsx, .xls) o CSV (.csv).')
                return redirect('indicadores:cargar_serie_indicador')

            # Crear registro de carga (metadata es opcional)
            create_kwargs = {
                'usuario': request.user,
                'indicador_id': indicador_id,
                'archivo_datos_xlsx': archivo_datos,
                'estado': 'procesando',
            }
            if archivo_metadata:
                create_kwargs['archivo_metadata_xlsx'] = archivo_metadata
            carga = CargaSerieIndicador.objects.create(**create_kwargs)
            
            # Procesar archivos
            procesar_serie_indicador(carga)

            from .notifications import notificar_admins_nueva_carga_recoleccion_serie
            resultado = notificar_admins_nueva_carga_recoleccion_serie(carga)
            if resultado:
                messages.info(request, '✉️ Se notificó a los administradores por correo.')
            else:
                messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los administradores.')

            messages.success(request, f'Carga procesada exitosamente. Código de evidencia: {carga.codigo_evidencia}')
            return redirect('indicadores:detalle_carga_serie', carga_id=carga.id)
            
        except Exception as e:
            messages.error(request, f'Error al procesar la carga: {str(e)}')
            return redirect('indicadores:cargar_serie_indicador')
    
    # Obtener todos los indicadores para el selector
    indicadores = Indicador.objects.filter(activo=True).order_by('codigo_indicador')
    indicador_pre = request.GET.get('indicador')
    indicador_obj = None
    dominios_headers = []
    datos_rows = []

    # IDs de dominios asociados al indicador (para marcarlos en el catálogo)
    dominios_asociados_ids = set()
    if indicador_pre:
        try:
            indicador_obj = Indicador.objects.prefetch_related(
                'dominios_desagregacion_geografica', 'dominios_desagregacion_tematica'
            ).get(id=indicador_pre, activo=True)
            dominios_geo = list(indicador_obj.dominios_desagregacion_geografica.all())
            dominios_tem = list(indicador_obj.dominios_desagregacion_tematica.all())
            dominios_headers = dominios_geo + dominios_tem
            dominios_asociados_ids = {d.id for d in dominios_geo + dominios_tem}

            datos_preview = list(
                indicador_obj.datos
                .prefetch_related(
                    'desagregaciones_geograficas__dominio',
                    'desagregaciones_tematicas__dominio'
                )
                .order_by('-fecha_dato')[:5]
            )
            for dato in datos_preview:
                desag_map = {}
                for des in dato.desagregaciones_geograficas.all():
                    desag_map[des.dominio_id] = des.nombre
                for des in dato.desagregaciones_tematicas.all():
                    desag_map[des.dominio_id] = des.nombre
                datos_rows.append({
                    'fecha_dato': dato.fecha_dato,
                    'valor_dato': dato.valor_dato,
                    'desag_values': [desag_map.get(dom.id, '—') for dom in dominios_headers],
                })
        except Indicador.DoesNotExist:
            pass

    # Siempre mostrar el catálogo completo de dominios del sistema,
    # marcando cuáles están asociados al indicador seleccionado (si lo hay)
    dominios_geo_info = _all_dominios_info('geografica', dominios_asociados_ids)
    dominios_tem_info = _all_dominios_info('tematica', dominios_asociados_ids)

    context = {
        'indicadores': indicadores,
        'indicador_pre': indicador_pre,
        'indicador_obj': indicador_obj,
        'dominios_headers': dominios_headers,
        'datos_rows': datos_rows,
        'dominios_geo_info': dominios_geo_info,
        'dominios_tem_info': dominios_tem_info,
    }

    return render(request, 'recoleccion/cargar_serie_indicador.html', context)


def _leer_archivo_datos(path, hojas_preferidas=None, con_col_codigo=False):
    """Lee un archivo Excel o CSV según su extensión.

    hojas_preferidas: nombres de hoja a intentar primero
    (case-insensitive, igualdad o 'contiene'). La plantilla oficial
    de metadatos trae 'Diccionario de datos' en la hoja 0 — los
    callers de metadata deben pedir 'Indicadores'.

    con_col_codigo=True: recorre las hojas en orden de preferencia
    (exacta, parcial, resto) probando encabezados en las primeras filas,
    y devuelve la primera hoja que contenga la columna de código de
    indicador — evita que una coincidencia parcial ('datos' ↔
    'Diccionario de datos') o una fila de título oculten la columna.
    Sin coincidencia devuelve la hoja preferida (comportamiento previo).
    """
    if path.lower().endswith('.csv'):
        from .wizard_admin_unificado import _leer_csv_auto_sep
        return _leer_csv_auto_sep(path)
    if not hojas_preferidas:
        return pd.read_excel(path)
    libro = pd.ExcelFile(path)
    orden = []
    nombres = {h.lower(): h for h in libro.sheet_names}
    for pref in hojas_preferidas:
        p = pref.lower()
        if p in nombres and nombres[p] not in orden:
            orden.append(nombres[p])
        for h in libro.sheet_names:
            if p in h.lower() and h not in orden:
                orden.append(h)
    orden += [h for h in libro.sheet_names if h not in orden]

    if con_col_codigo:
        for hoja in orden:
            for hdr in (0, 1, 2):
                try:
                    df = pd.read_excel(libro, sheet_name=hoja, header=hdr)
                except Exception:
                    break
                if _obtener_col_codigo(df):
                    return df
    return pd.read_excel(libro, sheet_name=orden[0] if orden else libro.sheet_names[0])


def procesar_serie_indicador(carga):
    """Procesa los archivos xlsx/csv y los convierte a csv. La metadata es opcional."""
    try:
        # Leer y convertir archivo de datos
        df_datos = _leer_archivo_datos(carga.archivo_datos_xlsx.path,
                                       hojas_preferidas=('datos',),
                                       con_col_codigo=True)
        csv_buffer = BytesIO()
        df_datos.to_csv(csv_buffer, index=False, encoding='utf-8', sep=';')
        csv_buffer.seek(0)
        csv_filename = f"datos_{carga.codigo_evidencia}.csv"
        carga.archivo_datos_csv.save(csv_filename, ContentFile(csv_buffer.read()))
        
        log_parts = [f"Procesados {len(df_datos)} registros de datos"]
        
        # Procesar metadata solo si fue adjuntada
        if carga.archivo_metadata_xlsx and carga.archivo_metadata_xlsx.name:
            df_metadata = _leer_archivo_datos(
                carga.archivo_metadata_xlsx.path,
                hojas_preferidas=('indicadores', 'metadata'))
            csv_buffer_meta = BytesIO()
            df_metadata.to_csv(csv_buffer_meta, index=False, encoding='utf-8', sep=';')
            csv_buffer_meta.seek(0)
            csv_meta_filename = f"metadata_{carga.codigo_evidencia}.csv"
            carga.archivo_metadata_csv.save(csv_meta_filename, ContentFile(csv_buffer_meta.read()))
            log_parts.append(f"{len(df_metadata)} registros de metadata")
        else:
            log_parts.append("metadata pendiente (no adjuntada)")
        
        # Actualizar estado
        carga.estado = 'pendiente'
        carga.fecha_procesamiento = timezone.now()
        carga.registros_procesados = len(df_datos)
        carga.registros_exitosos = len(df_datos)
        carga.log_procesamiento = ", ".join(log_parts)
        carga.save()
        
    except Exception as e:
        carga.estado = 'error'
        carga.mensaje_error = str(e)
        carga.fecha_procesamiento = timezone.now()
        carga.save()
        raise


@login_required(login_url='/recoleccion/login/')
def detalle_carga_serie(request, carga_id):
    """Detalle de una carga de serie de indicador (evidencia)"""
    carga = get_object_or_404(CargaSerieIndicador, id=carga_id, usuario=request.user)
    
    context = {
        'carga': carga,
    }
    
    return render(request, 'recoleccion/detalle_carga_serie.html', context)


@login_required(login_url='/recoleccion/login/')
def historial_cargas_series(request):
    """Historial de cargas de series de indicadores"""
    cargas = CargaSerieIndicador.objects.filter(
        usuario=request.user
    ).select_related('indicador').order_by('-fecha_carga')

    estado_filtro = request.GET.get('estado', '')
    busqueda = request.GET.get('q', '').strip()

    if estado_filtro:
        cargas = cargas.filter(estado=estado_filtro)
    if busqueda:
        from django.db.models import Q
        cargas = cargas.filter(
            Q(codigo_evidencia__icontains=busqueda) |
            Q(indicador__nombre__icontains=busqueda) |
            Q(indicador__codigo_indicador__icontains=busqueda)
        )

    paginator = Paginator(cargas, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'cargas': page_obj,
        'page_obj': page_obj,
        'estado_filtro': estado_filtro,
        'busqueda': busqueda,
        'estados': [
            ('exitoso', 'Exitoso'),
            ('error', 'Error'),
            ('procesando', 'Procesando'),
            ('pendiente', 'Pendiente'),
            ('correcciones_solicitadas', 'Correcciones solicitadas'),
        ],
    }
    
    return render(request, 'recoleccion/historial_cargas_series.html', context)


# ============================================================================
# CARGA DE MICRODATA
# ============================================================================

@login_required(login_url='/recoleccion/login/')
def cargar_conjunto_datos(request):
    """Formulario para cargar conjunto_datos"""
    if request.method == 'POST':
        try:
            # Obtener tipo de carga
            tipo_carga = request.POST.get('tipo_carga', 'nueva')
            
            # Obtener archivos
            archivo_conjunto_datos = request.FILES.get('archivo_conjunto_datos')
            archivo_metadata_variables = request.FILES.get('archivo_metadata_variables')
            
            if not archivo_conjunto_datos or not archivo_metadata_variables:
                messages.error(request, 'Debe subir ambos archivos (conjunto_datos y metadata de variables)')
                return redirect('indicadores:cargar_conjunto_datos')
            
            # Validar según tipo de carga
            if tipo_carga == 'nueva':
                # Validar IDs de indicadores
                indicadores_ids = request.POST.get('indicadores_ids', '').strip()
                if not indicadores_ids:
                    messages.error(request, 'Debe ingresar al menos un ID de indicador para crear nueva conjunto_datos')
                    return redirect('indicadores:cargar_conjunto_datos')
                
                # Validar que los IDs sean números válidos
                try:
                    ids_list = [int(id.strip()) for id in indicadores_ids.split(',') if id.strip()]
                    if not ids_list:
                        raise ValueError("No se ingresaron IDs válidos")
                    
                    # Verificar que los indicadores existan
                    indicadores_existentes = Indicador.objects.filter(id__in=ids_list)
                    if indicadores_existentes.count() != len(ids_list):
                        ids_no_encontrados = set(ids_list) - set(indicadores_existentes.values_list('id', flat=True))
                        messages.error(request, f'Los siguientes IDs de indicadores no existen: {", ".join(map(str, ids_no_encontrados))}')
                        return redirect('indicadores:cargar_conjunto_datos')
                        
                except ValueError as e:
                    messages.error(request, f'Error en los IDs de indicadores: {str(e)}. Use números separados por comas.')
                    return redirect('indicadores:cargar_conjunto_datos')
                
                # Crear nuevo registro de carga sin conjunto_datos asociada
                carga = CargaConjuntoDatos.objects.create(
                    usuario=request.user,
                    archivo_microdata_xlsx=archivo_conjunto_datos,
                    archivo_metadata_variables_xlsx=archivo_metadata_variables,
                    estado='procesando',
                    conjunto_datos=None  # Se creará después en el proceso de validación
                )
                
                # Guardar IDs de indicadores en log para referencia
                carga.log_procesamiento = f"Indicadores relacionados: {indicadores_ids}"
                
            else:  # tipo_carga == 'actualizacion'
                # Validar conjunto_datos existente
                conjunto_datos_id = request.POST.get('conjunto_datos_id')
                if not conjunto_datos_id:
                    messages.error(request, 'Debe seleccionar un conjunto de conjunto_datos existente para actualizar')
                    return redirect('indicadores:cargar_conjunto_datos')
                
                try:
                    conjunto_datos = ConjuntoDatos.objects.get(id=conjunto_datos_id)
                except ConjuntoDatos.DoesNotExist:
                    messages.error(request, 'El conjunto de conjunto_datos seleccionado no existe')
                    return redirect('indicadores:cargar_conjunto_datos')
                
                # Crear registro de carga asociado al conjunto_datos existente
                carga = CargaConjuntoDatos.objects.create(
                    usuario=request.user,
                    archivo_microdata_xlsx=archivo_conjunto_datos,
                    archivo_metadata_variables_xlsx=archivo_metadata_variables,
                    estado='procesando',
                    conjunto_datos=conjunto_datos  # Asociar al conjunto_datos existente
                )
                
                # Guardar referencia en log
                carga.log_procesamiento = f"Actualización de conjunto_datos existente: {conjunto_datos.nombre} (ID: {conjunto_datos_id})"
            
            # Procesar archivos
            procesar_conjunto_datos(carga)

            from .notifications import notificar_admins_nueva_carga_recoleccion_conjunto_datos
            resultado = notificar_admins_nueva_carga_recoleccion_conjunto_datos(carga)
            if resultado:
                messages.info(request, '✉️ Se notificó a los administradores por correo.')
            else:
                messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los administradores.')

            messages.success(request, f'Carga procesada exitosamente. Código de evidencia: {carga.codigo_evidencia}.')
            return redirect('indicadores:detalle_carga_conjunto_datos', carga_id=carga.id)
            
        except Exception as e:
            messages.error(request, f'Error al procesar la carga: {str(e)}')
            return redirect('indicadores:cargar_conjunto_datos')
    
    # Obtener conjuntos_datos existentes para el selector de actualización
    conjuntos_datos = ConjuntoDatos.objects.all().order_by('nombre')
    indicadores = Indicador.objects.filter(activo=True).order_by('codigo_indicador')

    return render(request, 'recoleccion/cargar_conjunto_datos.html', {
        'conjuntos_datos': conjuntos_datos,
        'indicadores': indicadores,
    })


def procesar_conjunto_datos(carga):
    """Procesa los archivos xlsx de conjunto_datos y los convierte a csv"""
    try:
        # Leer archivo de conjunto_datos xlsx
        df_conjunto_datos = pd.read_excel(carga.archivo_microdata_xlsx.path)
        
        # Convertir a CSV
        csv_buffer = BytesIO()
        df_conjunto_datos.to_csv(csv_buffer, index=False, encoding='utf-8', sep=';')
        csv_buffer.seek(0)
        
        # Guardar CSV
        csv_filename = f"conjunto_datos_{carga.codigo_evidencia}.csv"
        carga.archivo_microdata_csv.save(csv_filename, ContentFile(csv_buffer.read()))
        
        # Leer archivo de metadata de variables xlsx
        df_metadata_vars = pd.read_excel(carga.archivo_metadata_variables_xlsx.path)
        
        # Convertir metadata a CSV
        csv_buffer_meta = BytesIO()
        df_metadata_vars.to_csv(csv_buffer_meta, index=False, encoding='utf-8', sep=';')
        csv_buffer_meta.seek(0)
        
        # Guardar CSV metadata
        csv_meta_filename = f"metadata_vars_{carga.codigo_evidencia}.csv"
        carga.archivo_metadata_variables_csv.save(csv_meta_filename, ContentFile(csv_buffer_meta.read()))
        
        # Actualizar estado
        carga.estado = 'pendiente'
        carga.fecha_procesamiento = timezone.now()
        carga.registros_procesados = len(df_conjunto_datos)
        carga.registros_exitosos = len(df_conjunto_datos)
        carga.log_procesamiento = f"Procesados {len(df_conjunto_datos)} registros de conjunto_datos y {len(df_metadata_vars)} variables"
        carga.save()
        
    except Exception as e:
        carga.estado = 'error'
        carga.mensaje_error = str(e)
        carga.fecha_procesamiento = timezone.now()
        carga.save()
        raise


@login_required(login_url='/recoleccion/login/')
def detalle_carga_conjunto_datos(request, carga_id):
    """Detalle de una carga de conjunto_datos (evidencia)"""
    carga = get_object_or_404(CargaConjuntoDatos, id=carga_id, usuario=request.user)
    
    context = {
        'carga': carga,
    }
    
    return render(request, 'recoleccion/detalle_carga_conjunto_datos.html', context)


@login_required(login_url='/recoleccion/login/')
def historial_cargas_conjuntos_datos(request):
    """Historial de cargas de conjunto_datos"""
    cargas = CargaConjuntoDatos.objects.filter(
        usuario=request.user
    ).order_by('-fecha_carga')
    
    context = {
        'cargas': cargas,
    }
    
    return render(request, 'recoleccion/historial_cargas_conjuntos_datos.html', context)


# ============================================================================
# REPORTES - INDICADORES
# ============================================================================

@login_required(login_url='/recoleccion/login/')
def reportes_indicadores(request):
    """Página de reportes de indicadores"""
    indicadores = Indicador.objects.filter(activo=True).order_by('nombre')
    
    context = {
        'indicadores': indicadores,
    }
    
    return render(request, 'recoleccion/reportes_indicadores.html', context)


@login_required(login_url='/recoleccion/login/')
def descargar_datos_indicador(request, indicador_id=None):
    """Descarga datos de un indicador o todos los indicadores en xlsx con desagregaciones"""
    try:
        if indicador_id:
            # Descargar un solo indicador
            indicador = get_object_or_404(Indicador, id=indicador_id)
            datos = Dato.objects.filter(indicador=indicador).prefetch_related(
                'desagregaciones_geograficas__dominio',
                'desagregaciones_tematicas__dominio'
            ).order_by('fecha_dato')
            
            # Crear DataFrame con desagregaciones
            data = []
            for dato in datos:
                # Obtener desagregaciones geográficas
                desag_geo = dato.desagregaciones_geograficas.all()
                desag_geo_str = ' | '.join([f"{d.dominio.nombre}: {d.nombre}" for d in desag_geo]) if desag_geo else ''
                
                # Obtener desagregaciones temáticas
                desag_tem = dato.desagregaciones_tematicas.all()
                desag_tem_str = ' | '.join([f"{d.dominio.nombre}: {d.nombre}" for d in desag_tem]) if desag_tem else ''
                
                data.append({
                    'Codigo_Indicador': indicador.codigo_indicador,
                    'Nombre_Indicador': indicador.nombre,
                    'Fecha': dato.fecha_dato,
                    'Valor': dato.valor_dato,
                    'Desagregaciones_Geograficas': desag_geo_str,
                    'Desagregaciones_Tematicas': desag_tem_str,
                })
            
            df = pd.DataFrame(data)
            filename = f"datos_{indicador.codigo_indicador}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        else:
            # Descargar todos los indicadores
            datos = Dato.objects.select_related('indicador').prefetch_related(
                'desagregaciones_geograficas__dominio',
                'desagregaciones_tematicas__dominio'
            ).order_by('indicador__codigo_indicador', 'fecha_dato')
            
            data = []
            for dato in datos:
                # Obtener desagregaciones geográficas
                desag_geo = dato.desagregaciones_geograficas.all()
                desag_geo_str = ' | '.join([f"{d.dominio.nombre}: {d.nombre}" for d in desag_geo]) if desag_geo else ''
                
                # Obtener desagregaciones temáticas
                desag_tem = dato.desagregaciones_tematicas.all()
                desag_tem_str = ' | '.join([f"{d.dominio.nombre}: {d.nombre}" for d in desag_tem]) if desag_tem else ''
                
                data.append({
                    'Codigo_Indicador': dato.indicador.codigo_indicador,
                    'Nombre_Indicador': dato.indicador.nombre,
                    'Fecha': dato.fecha_dato,
                    'Valor': dato.valor_dato,
                    'Desagregaciones_Geograficas': desag_geo_str,
                    'Desagregaciones_Tematicas': desag_tem_str,
                })
            
            df = pd.DataFrame(data)
            filename = f"datos_todos_indicadores_{datetime.now().strftime('%Y%m%d')}.xlsx"
        
        # Crear archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Datos', index=False)
        output.seek(0)
        
        # Retornar respuesta
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar el reporte: {str(e)}')
        return redirect('indicadores:reportes_indicadores')


@login_required(login_url='/recoleccion/login/')
def descargar_metadata_indicador(request, indicador_id=None):
    """Descarga metadata de un indicador o todos los indicadores en xlsx"""
    try:
        if indicador_id:
            # Descargar metadata de un solo indicador
            indicador = get_object_or_404(Indicador, id=indicador_id)
            indicadores = [indicador]
            filename = f"metadata_{indicador.codigo_indicador}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        else:
            # Descargar metadata de todos los indicadores
            indicadores = Indicador.objects.filter(activo=True)
            filename = f"metadata_todos_indicadores_{datetime.now().strftime('%Y%m%d')}.xlsx"
        
        # Crear DataFrame con metadata — encabezados de la plantilla
        # oficial (Metadatos_SDMX) para que el archivo sea re-subible
        # tal cual por la vía masiva o la carga individual.
        data = []
        for ind in indicadores:
            data.append({
                'Grupo_indicador': ind.grupo_indicador or '',
                'Codigo_Indicador': ind.codigo_indicador,
                'Dominio': ind.subtema.tema.dominio.nombre if ind.subtema else '',
                'Tema': ind.subtema.tema.nombre if ind.subtema else '',
                'Subtema': ind.subtema.nombre if ind.subtema else '',
                'Nombre indicador': ind.nombre,
                'Sigla o abreviatura': ind.sigla or '',
                'Descripción del indicador': ind.descripcion_indicador or '',
                'Cálculo del indicador': ind.metodo_medicion or '',
                'Unidad de medida': ind.unidad_medida or '',
                'Fuente de la información': ind.fuente_datos or '',
                'Nombre de la operación estadística': ind.operacion.nombre if ind.operacion else '',
                'Nomenclatura y clasificaciones estadísticas': ind.nomenclaturas_clasificaciones or '',
                'Alcance temático': ind.alcance_tematico or '',
                'Población objetivo': ind.poblacion_objetivo or '',
                'Cobertura geográfica': ind.cobertura_geografica or '',
                'Periodo de referencia': ind.periodo_referencia or '',
                'Periodo base': ind.periodo_base or '',
                'Serie histórica disponible': ind.serie_historica_disponible or '',
                'Frecuencia de difusión': ind.frecuencia_difusion or '',
                'Medios de difusión': ind.medios_difusion or '',
                'Comentarios adicionales': ind.comentarios_adicionales or '',
                'Referencias': ind.referencias or '',
                'Organismo responsable': ind.organismo_responsable.nombre if ind.organismo_responsable else (ind.entidad_responsable or ''),
                'Suborganismo responsable': ind.suborganismo.nombre if ind.suborganismo else '',
                'Equipo responsable': ind.equipo_responsable.nombre if ind.equipo_responsable else '',
                'Dirección de correo electrónico de contacto': ind.correo_contacto or '',
                'Nombre responsable técnico de validación': ind.nombre_responsable_validacion or '',
                'Cargo responsable técnico de validación': ind.cargo_responsable_validacion or '',
                'Correo electrónico del responsable técnico del indicador': ind.correo_responsable_validacion or '',
                'Celular responsable técnico de validación': ind.celular_responsable_validacion or '',
                # Extras internos (fuera del estándar) — roundtrip completo:
                'Formula': ind.formula_ficha or '',
                'Variables': ind.variables or '',
                'Nombre_Conjunto_Datos': ind.nombre_conjunto_datos or '',
                'Telefono_Contacto': ind.telefono_contacto or '',
                'Fecha_Publicacion_Metadatos': str(ind.fecha_publicacion_metadatos) if ind.fecha_publicacion_metadatos else '',
                'Fecha_Elaboracion': str(ind.fecha_elaboracion) if ind.fecha_elaboracion else '',
                'Fecha_Actualizacion': str(ind.fecha_actualizacion_ficha) if ind.fecha_actualizacion_ficha else '',
            })
        
        df = pd.DataFrame(data)
        
        # Crear archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Metadata', index=False)
        output.seek(0)
        
        # Retornar respuesta
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar el reporte: {str(e)}')
        return redirect('indicadores:reportes_indicadores')


# ============================================================================
# REPORTES - MICRODATA
# ============================================================================

@login_required(login_url='/recoleccion/login/')
def reportes_conjuntos_datos(request):
    """Página de reportes de conjunto_datos"""
    conjuntos_datos = ConjuntoDatos.objects.all().order_by('nombre')
    
    context = {
        'conjuntos_datos': conjuntos_datos,
    }
    
    return render(request, 'recoleccion/reportes_conjuntos_datos.html', context)


@login_required(login_url='/recoleccion/login/')
def descargar_conjunto_datos(request, conjunto_datos_id):
    """Descarga archivo de conjunto_datos en xlsx (convertido desde csv)"""
    try:
        conjunto_datos = get_object_or_404(ConjuntoDatos, id=conjunto_datos_id)
        
        if not conjunto_datos.archivo_csv:
            messages.error(request, 'Este archivo de conjunto_datos no tiene CSV asociado')
            return redirect('indicadores:reportes_conjuntos_datos')
        
        # Leer CSV y convertir a xlsx
        df = pd.read_csv(conjunto_datos.archivo_csv.path, sep=';')
        
        # Crear archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='conjunto_datos', index=False)
        output.seek(0)
        
        filename = f"conjunto_datos_{conjunto_datos.nombre}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        
        # Retornar respuesta
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar el reporte: {str(e)}')
        return redirect('indicadores:reportes_conjuntos_datos')


@login_required(login_url='/recoleccion/login/')
def descargar_metadata_variables(request, conjunto_datos_id):
    """Descarga metadata de variables de un archivo de conjunto_datos en xlsx"""
    try:
        conjunto_datos = get_object_or_404(ConjuntoDatos, id=conjunto_datos_id)
        
        # Obtener variables directamente de la conjunto_datos
        variables = conjunto_datos.variables.all()
        
        # Crear DataFrame con metadata de variables
        data = []
        for var in variables:
            data.append({
                'Codigo_Variable': var.codigo_variable,
                'Nombre_Variable': var.nombre_variable,
                'Definicion_Conceptual': var.definicion_conceptual or '',
                'Poblacion_Objetivo': var.poblacion_objetivo or '',
                'Cobertura_Geografica': var.cobertura_geografica or '',
                'Desagregacion_Geografica': var.desagregacion_geografica or '',
                'Desagregacion_Tematica': var.desagregacion_tematica or '',
                'Tipo_Dato': var.tipo_dato or '',
                'Dominio_Dato': var.dominio_dato or '',
                'Unidad_Medida': var.unidad_medida or '',
                'Tipo_Variable_Estadistica': var.tipo_variable_estadistica or '',
                'Fuente_Datos': var.fuente_datos or '',
                'Periodicidad': var.periodicidad or '',
                'Observaciones': var.observaciones or '',
                'Organismo_Productor': (var.organismo_productor.nombre if var.organismo_productor else (var.organismo_productor_legado or '')),
            })
        
        df = pd.DataFrame(data)
        
        # Crear archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Metadata Variables', index=False)
        output.seek(0)
        
        filename = f"metadata_variables_{conjunto_datos.nombre}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        
        # Retornar respuesta
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar el reporte: {str(e)}')
        return redirect('indicadores:reportes_conjuntos_datos')


# ============================================================================
# DESCARGAR PLANTILLAS DE EJEMPLO
# ============================================================================

def descargar_plantilla_serie_datos(request):
    """Descarga plantilla Excel de ejemplo para series de datos de indicadores"""
    try:
        # Crear DataFrame con estructura de ejemplo incluyendo desagregaciones
        data = {
            'Codigo_Indicador': ['ICET_SAL_DEM_MOR_02', 'ICET_SAL_DEM_MOR_02', 'ICET_SAL_DEM_MOR_02', 'ICET_SAL_DEM_MOR_02'],
            'Nombre_Indicador': [
                'Tasa de mortalidad de niños menores de 5 años',
                'Tasa de mortalidad de niños menores de 5 años',
                'Tasa de mortalidad de niños menores de 5 años',
                'Tasa de mortalidad de niños menores de 5 años'
            ],
            'Año': [2022, 2022, 2023, 2023],
            'Desagregacion_Geografica': ['Comuna 1', 'Comuna 2', 'Comuna 1', 'Comuna 2'],
            'Desagregacion_Tematica_1': ['Hombre', 'Mujer', 'Hombre', 'Mujer'],
            'Desagregacion_Tematica_2': ['0-1 años', '0-1 años', '0-1 años', '0-1 años'],
            'Valor': [10.89, 11.25, 10.50, 11.00]
        }
        df = pd.DataFrame(data)
        
        # Crear archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Datos')
            
            # Agregar hoja de instrucciones
            instrucciones = pd.DataFrame({
                'INSTRUCCIONES': [
                    '1. Complete los datos en la hoja "Datos"',
                    '2. Codigo_Indicador: Use el código oficial del indicador (ej: ICET_SAL_DEM_MOR_02)',
                    '3. Nombre_Indicador: Nombre completo del indicador',
                    '4. Anio: Año de la medición (formato numérico: 2024)',
                    '5. Desagregacion_Geografica: Nombre de la desagregación geográfica (ej: Comuna 1, Barrio Centro)',
                    '6. Desagregacion_Tematica_1: Primera desagregación temática (ej: Hombre, Mujer)',
                    '7. Desagregacion_Tematica_2: Segunda desagregación temática (ej: 0-1 años, 2-5 años)',
                    '8. Valor: Valor numérico del indicador (use punto como separador decimal)',
                    '',
                    'IMPORTANTE:',
                    '- No modifique los nombres de las columnas',
                    '- Las columnas de desagregación son opcionales, déjelas vacías si no aplican',
                    '- Si no usa Desagregacion_Tematica_2, puede dejar esa columna vacía',
                    '- Los valores numéricos deben usar punto (.) como separador decimal',
                    '- El código del indicador debe existir en el sistema',
                    '- Las desagregaciones deben existir previamente en el sistema'
                ]
            })
            instrucciones.to_excel(writer, index=False, sheet_name='Instrucciones')
        
        output.seek(0)
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="plantilla_serie_datos_indicador.xlsx"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar la plantilla: {str(e)}')
        return redirect('indicadores:cargar_serie_indicador')


def descargar_plantilla_metadata_indicador(request):
    """Descarga la plantilla oficial de metadatos (portal delegado y
    carga individual). Es el mismo archivo que la carga masiva."""
    return _servir_plantilla_oficial_metadatos(
        request, 'indicadores:cargar_serie_indicador')


def _descargar_plantilla_metadata_indicador_generada(request):
    """Generador histórico (deprecado): estándar MSD numerado viejo.
    Solo respaldo; ya no se expone en ninguna URL."""
    try:
        data = {
            '0.2 Código del Indicador': ['ICET_SAL_DEM_MOR_02'],
            '0.1 Nombre del Indicador': ['Tasa de mortalidad de niños menores de 5 años'],
            '0.3 Sigla': ['TMM5'],
            '0.4 Grupo Indicador': ['ICET'],
            '1.1 Entidad o Institución Responsable': ['Departamento Administrativo de Planeación'],
            '1.2 Entidad (organismo registrado)': ['Departamento Administrativo de Planeación'],
            '1.3 Área o Dependencia Responsable': ['Dirección de Estadísticas'],
            '1.4 Correo Electrónico de Contacto': ['planeacion@cali.gov.co'],
            '1.5 Número Telefónico': ['885 8000'],
            '1.6 Fecha de Publicación de los Metadatos': ['2025-09-16'],
            '2.2 Descripción del Indicador': ['Cuantifica la relación de las muertes en la población menor de 5 años...'],
            '2.3 Objetivo': ['Evaluar el comportamiento de la salud infantil en el distrito...'],
            '2.4 Cálculo del Indicador / Método de Medición': ['El cálculo se realiza mediante el procesamiento de registros administrativos...'],
            '2.5 Fórmula': ['TMM5 = (V₁ / V₂) × 1.000'],
            '2.6 Variables': ['V₁: Número total de defunciones en menores de 5 años; V₂: Número total de nacidos vivos'],
            '2.7 Unidad de Medida': ['Número de muertes por cada 1.000 nacidos vivos'],
            '2.8 Fuente de la Información': ['Cálculos propios con base en datos del DANE'],
            '2.9 Nombre de la Operación Estadística': ['Registros administrativos de defunciones'],
            '2.10 Nombre del Conjunto de Datos': ['Mortalidad infantil distrito de Cali'],
            '2.11 Nomenclaturas y Clasificaciones': ['Divipola, Clasificación Colombiana de Ocupaciones...'],
            '2.12 Alcance Temático': ['Salud pública, mortalidad infantil'],
            '2.13 Población Objetivo': ['Población menor de 5 años residente en Santiago de Cali'],
            '2.14 Cobertura Geográfica': ['Distrital, comunas, barrios'],
            '2.15 Período de Referencia': ['Anual'],
            '2.16 Período Base': ['2022'],
            '3.1 Serie Histórica Disponible': ['2010-2024'],
            '3.2 Frecuencia de Difusión': ['Anual'],
            '3.3 Medios de Difusión': ['Portal SIIED, informes anuales'],
            '4.1 Comentarios Adicionales': ['Es importante considerar que cerca de dos tercios de las muertes...'],
            '5.1 Referencias (APA 7)': ['DANE. (2024). Estadísticas vitales. https://...'],
            '6.3 Equipo Responsable': ['Equipo de Demografía'],
            'Fecha_Elaboracion': ['2025-09-16'],
            'Fecha_Actualizacion': ['2025-09-16'],
        }
        df = pd.DataFrame(data)

        # Crear archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Metadata')

            # Agregar hoja de instrucciones
            instrucciones = pd.DataFrame({
                'INSTRUCCIONES': [
                    '1. Complete una fila por cada indicador en la hoja "Metadata"',
                    '2. La columna "0.2 Código del Indicador" es OBLIGATORIA y debe existir en el sistema',
                    '3. Use formato de fecha YYYY-MM-DD para 1.6, Fecha_Elaboracion y Fecha_Actualizacion',
                    '4. Los nombres de columnas siguen la numeración del estándar MSD de la ficha técnica',
                    '5. NO modifique los nombres de las columnas (la numeración 0.1, 1.1, 2.1... es requerida)',
                    '',
                    'CAMPOS PRINCIPALES:',
                    '- Sección 0: Identificación (nombre, código, sigla, grupo ICET/SIIET)',
                    '- Sección 1: Contacto institucional (entidad, organismo, área, correo, teléfono)',
                    '- Sección 2: Características del indicador (descripción, fórmula, variables, fuente)',
                    '- Sección 3: Difusión (serie histórica, frecuencia, medios)',
                    '- Sección 4-5: Comentarios y referencias APA 7',
                    '- Sección 6: Equipo responsable (nombre tal cual está registrado)',
                    '',
                    'NOTAS:',
                    '- 1.2 y 1.3 deben coincidir con Organismos/Suborganismos registrados en el sistema',
                    '- 2.9 debe coincidir con una Operación Estadística registrada (opcional)',
                    '- 6.3 debe coincidir con un equipo del organismo responsable (opcional)',
                    '- Las celdas vacías no modifican el valor actual del indicador'
                ]
            })
            instrucciones.to_excel(writer, index=False, sheet_name='Instrucciones')
        
        output.seek(0)
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="plantilla_metadata_indicador.xlsx"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar la plantilla: {str(e)}')
        return redirect('indicadores:cargar_serie_indicador')


@login_required(login_url='/recoleccion/login/')
def instrucciones_conjuntos_datos(request):
    """Muestra las instrucciones para cargar conjunto_datos"""
    return render(request, 'recoleccion/instrucciones_conjuntos_datos.html')


def descargar_plantilla_conjunto_datos(request):
    """Descarga plantilla Excel de ejemplo para conjunto_datos con dos formatos"""
    try:
        # FORMATO 1: Formato largo (desagregaciones en columnas)
        data_largo = {
            'Año': [2022, 2022, 2022, 2023, 2023, 2023],
            'Grupos de edad': ['15-19', '20-24', '25-29', '15-19', '20-24', '25-29'],
            'Nacimientos': [5500, 7800, 6500, 5400, 7700, 6400],
            'Poblacion_Mujeres': [93000, 91000, 89000, 93500, 91500, 89500]
        }
        df_largo = pd.DataFrame(data_largo)
        
        # FORMATO 2: Formato ancho (desagregaciones en encabezados)
        data_ancho = {
            'AÑO': [2022, 2023, 2024],
            'ÁREA GEOGRÁFICA': ['Cabecera Municipal', 'Cabecera Municipal', 'Cabecera Municipal'],
            'Hombres_0': [17722, 17937, 18304],
            'Hombres_1': [17603, 17748, 17940],
            'Hombres_2': [17564, 17703, 17810],
            'Mujeres_0': [16677, 16940, 17296],
            'Mujeres_1': [16595, 16795, 17006],
            'Mujeres_2': [16542, 16731, 16884],
            'Total_0': [34399, 34877, 35600],
            'Total_1': [34198, 34543, 34946],
            'Total_2': [34106, 34434, 34694]
        }
        df_ancho = pd.DataFrame(data_ancho)
        
        # Crear archivo Excel con ambos formatos
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_largo.to_excel(writer, index=False, sheet_name='Formato Largo')
            df_ancho.to_excel(writer, index=False, sheet_name='Formato Ancho')
            
            # Agregar hoja de instrucciones detalladas
            instrucciones = pd.DataFrame({
                'INSTRUCCIONES Y FORMATOS': [
                    '=== FORMATOS ACEPTADOS ===',
                    '',
                    'Este sistema acepta conjunto_datos en DOS formatos diferentes:',
                    '',
                    '1. FORMATO LARGO (ver hoja "Formato Largo")',
                    '   - Desagregaciones temáticas en COLUMNAS',
                    '   - Cada fila es una observación con sus desagregaciones',
                    '   - Ejemplo: Año | Grupos de edad | Nacimientos | Poblacion_Mujeres',
                    '   - Ideal para: Datos con pocas desagregaciones o datos tabulares',
                    '',
                    '2. FORMATO ANCHO (ver hoja "Formato Ancho")',
                    '   - Desagregaciones temáticas en ENCABEZADOS',
                    '   - Cada columna representa una combinación de desagregaciones',
                    '   - Ejemplo: AÑO | ÁREA GEOGRÁFICA | Hombres_0 | Hombres_1 | Mujeres_0...',
                    '   - Ideal para: Datos demográficos, tablas cruzadas, muchas desagregaciones',
                    '',
                    '=== COLUMNAS REQUERIDAS ===',
                    '',
                    'FECHA/AÑO (obligatorio):',
                    '   - Encabezado puede ser: Año, AÑO, año, Fecha, fecha, FECHA',
                    '   - Formato: número (2024) o fecha (2024-01-15)',
                    '',
                    'DESAGREGACIONES GEOGRÁFICAS (opcional):',
                    '   - Encabezado debe tener el nombre del dominio',
                    '   - Ejemplos: "Barrios y Veredas", "Comunas y Corregimientos", "Área Geográfica"',
                    '   - Pueden estar en columnas (formato largo) o en encabezados (formato ancho)',
                    '',
                    'DESAGREGACIONES TEMÁTICAS (opcional):',
                    '   - FORMATO LARGO: En columnas con nombre del dominio (ej: "Grupos de edad")',
                    '   - FORMATO ANCHO: En encabezados separados por guión bajo (ej: Hombres_0, Mujeres_15-19)',
                    '   - Configuración en admin permite extraer temáticas de columnas o viceversa',
                    '',
                    '=== CRITERIO DE SELECCIÓN DE FORMATO ===',
                    '',
                    'Elija el formato que sea:',
                    '   1. Más cómodo de leer para el usuario final',
                    '   2. Más estético y agradable visualmente',
                    '   3. Más pragmático según la naturaleza de los datos',
                    '',
                    'Ejemplo: Población por comunas (solo desagregación geográfica)',
                    '   - Formato ANCHO es mejor: permite ver todas las comunas en una tabla',
                    '   - Formato LARGO sería incómodo: una columna con comunas y otra con valores',
                    '',
                    '=== IMPORTANTE ===',
                    '',
                    '- Use punto (.) como separador decimal',
                    '- Los nombres de desagregaciones deben existir en el sistema',
                    '- El sistema extraerá automáticamente los valores según configuración',
                    '- La tabla será visible para usuarios como recurso primario'
                ]
            })
            instrucciones.to_excel(writer, index=False, sheet_name='Instrucciones')
        
        output.seek(0)
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="plantilla_conjunto_datos_formatos.xlsx"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar la plantilla: {str(e)}')
        return redirect('indicadores:cargar_conjunto_datos')


def descargar_plantilla_metadata_variables(request):
    """Descarga plantilla Excel de ejemplo para metadata de variables"""
    try:
        # Crear DataFrame con estructura completa
        data = {
            'Codigo_Indicador': ['ICET_ECO_FIN_ING_01', 'ICET_ECO_FIN_ING_01'],
            'Nombre_Indicador': [
                'Porcentaje de presupuesto municipal financiado con recursos propios',
                'Porcentaje de presupuesto municipal financiado con recursos propios'
            ],
            'Codigo_Variable': ['V1', 'V2'],
            'Nombre_Variable': ['Ingresos totales', 'Ingresos tributarios'],
            'Definicion_Conceptual': [
                'Suma de todos los ingresos del municipio incluyendo tributarios y no tributarios',
                'Ingresos provenientes de impuestos y contribuciones municipales'
            ],
            'Poblacion_Objetivo': ['Municipio de Santiago de Cali', 'Municipio de Santiago de Cali'],
            'Cobertura_Geografica': ['Distrital', 'Distrital'],
            'Desagregacion_Geografica': ['Municipal', 'Municipal'],
            'Desagregacion_Tematica': ['Por tipo de ingreso', 'Por tipo de impuesto'],
            'Tipo_Dato': ['Numérico continuo', 'Numérico continuo'],
            'Dominio_Dato': ['Valores positivos en millones de pesos', 'Valores positivos en millones de pesos'],
            'Unidad_Medida': ['Millones de pesos', 'Millones de pesos'],
            'Tipo_Variable_Estadistica': ['Cuantitativa continua', 'Cuantitativa continua'],
            'Fuente_Datos': ['DNP - CIFFIT', 'DNP - CIFFIT'],
            'Periodicidad': ['Anual', 'Anual'],
            'Observaciones': ['Cifras en millones de pesos corrientes', 'Incluye predial industria y comercio y otros'],
            'Organismo_Productor': ['Departamento Nacional de Planeación', 'Departamento Nacional de Planeación']
        }
        df = pd.DataFrame(data)
        
        # Crear archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Metadata Variables')
            
            # Agregar hoja de instrucciones
            instrucciones = pd.DataFrame({
                'INSTRUCCIONES': [
                    '1. Complete la metadata de cada variable en la hoja "Metadata Variables"',
                    '2. Cada fila representa una variable del indicador',
                    '3. El Codigo_Variable debe coincidir con el archivo de conjunto_datos',
                    '',
                    'CAMPOS PRINCIPALES:',
                    '- Codigo_Indicador: Código del indicador asociado',
                    '- Codigo_Variable: Código único de la variable (V1, V2, etc.)',
                    '- Nombre_Variable: Nombre descriptivo',
                    '- Definicion_Conceptual: Explicación detallada de la variable',
                    '- Tipo_Dato: Numérico continuo, Numérico discreto, Categórico, etc.',
                    '- Unidad_Medida: Unidad en que se expresa la variable',
                    '',
                    'IMPORTANTE:',
                    '- No modifique los nombres de las columnas',
                    '- Todos los campos son obligatorios',
                    '- Sea preciso en las definiciones conceptuales'
                ]
            })
            instrucciones.to_excel(writer, index=False, sheet_name='Instrucciones')
        
        output.seek(0)
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="plantilla_metadata_variables.xlsx"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar la plantilla: {str(e)}')
        return redirect('indicadores:cargar_conjunto_datos')


# ============================================================================
# DASHBOARD ADMIN - VISUALIZACIÓN Y DESCARGA DE CARGAS
# ============================================================================

@staff_member_required
def admin_cargas_dashboard(request):
    """Dashboard para que el admin vea y descargue las cargas del equipo"""
    
    # Obtener todas las cargas
    cargas_series = CargaSerieIndicador.objects.all().order_by('-fecha_carga')
    cargas_conjuntos_datos = CargaConjuntoDatos.objects.all().order_by('-fecha_carga')
    
    # Calcular estadísticas
    stats = {
        'total_series': cargas_series.count(),
        'total_conjunto_datos': cargas_conjuntos_datos.count(),
        'pendientes': cargas_series.filter(estado='procesando').count() + 
                     cargas_conjuntos_datos.filter(estado='procesando').count(),
        'completadas': cargas_series.filter(estado='completado').count() + 
                      cargas_conjuntos_datos.filter(estado='completado').count(),
    }
    
    context = {
        'cargas_series': cargas_series,
        'cargas_conjuntos_datos': cargas_conjuntos_datos,
        'stats': stats,
    }
    
    return render(request, 'admin/cargas_dashboard.html', context)


@staff_member_required
def descargar_csv_serie_datos(request, carga_id):
    """Descarga el archivo CSV de datos de una carga de serie"""
    carga = get_object_or_404(CargaSerieIndicador, id=carga_id)
    
    if not carga.archivo_datos_csv:
        messages.error(request, 'No hay archivo CSV de datos disponible')
        return redirect('indicadores:admin_cargas_dashboard')
    
    response = FileResponse(
        carga.archivo_datos_csv.open('rb'),
        content_type='text/csv'
    )
    filename = f'datos_{carga.codigo_evidencia}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@staff_member_required
def restart_services(request):
    """Reinicia los servicios Gunicorn y Apache2 usando credenciales proporcionadas.
    
    Nota: Gunicorn se reinicia en segundo plano porque no puede reiniciarse a sí mismo
    de forma síncrona (el proceso que ejecuta el comando sería terminado).
    """
    import subprocess
    import logging
    import tempfile
    import os
    logger = logging.getLogger(__name__)

    if request.method == 'POST':
        sudo_user = request.POST.get('sudo_user')
        sudo_password = request.POST.get('sudo_password')
        
        if not sudo_password:
            messages.error(request, '❌ Debe proporcionar la contraseña sudo.')
            return redirect('admin:index')

        try:
            # Preparar el input para sudo (contraseña + newline)
            input_bytes = f"{sudo_password}\n".encode()
            
            # Primero verificamos que las credenciales son correctas con un comando simple
            cmd_verify = ['sudo', '-S', '-p', '', '-k', 'true']  # -k invalida cache, 'true' es comando que siempre funciona
            result = subprocess.run(cmd_verify, input=input_bytes, capture_output=True)
            
            if result.returncode != 0:
                error_msg = result.stderr.decode() if result.stderr else "Credenciales inválidas"
                messages.error(request, f'❌ Error de autenticación sudo. Verifique las credenciales.')
                logger.error(f"Error de autenticación sudo: {error_msg}")
                return redirect('admin:index')
            
            # Crear script temporal para reiniciar servicios en segundo plano
            # Esto evita que Gunicorn se mate a sí mismo durante el reinicio
            script_content = f'''#!/bin/bash
sleep 2
echo "{sudo_password}" | sudo -S systemctl restart gunicorn 2>/dev/null
echo "{sudo_password}" | sudo -S systemctl restart apache2 2>/dev/null
'''
            # Crear archivo temporal
            fd, script_path = tempfile.mkstemp(suffix='.sh', prefix='restart_services_')
            try:
                os.write(fd, script_content.encode())
                os.close(fd)
                os.chmod(script_path, 0o700)
                
                # Ejecutar script en segundo plano completamente desacoplado
                # nohup + & + start_new_session aseguran que el proceso sobreviva
                subprocess.Popen(
                    ['nohup', 'bash', script_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True
                )
                
                # Programar eliminación del script después de un tiempo
                subprocess.Popen(
                    ['bash', '-c', f'sleep 10 && rm -f {script_path}'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True
                )
                
                messages.success(request, f'✅ Reinicio de servicios programado. Gunicorn y Apache2 se reiniciarán en ~2 segundos. (Solicitado por: {sudo_user})')
                logger.info(f"Reinicio de servicios programado por {request.user.username} (credenciales de: {sudo_user})")
                
            except Exception as e:
                # Limpiar script en caso de error
                try:
                    os.unlink(script_path)
                except:
                    pass
                raise e
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            messages.error(request, f'❌ Error al reiniciar servicios. Detalle: {error_msg}')
            logger.error(f"Error reiniciando servicios: {error_msg}")
        except Exception as e:
            messages.error(request, f'❌ Error inesperado: {str(e)}')
            logger.error(f"Error inesperado reiniciando servicios: {e}")
            
    return redirect('admin:index')


@staff_member_required
def descargar_csv_serie_metadata(request, carga_id):
    """Descarga el archivo CSV de metadata de una carga de serie"""
    carga = get_object_or_404(CargaSerieIndicador, id=carga_id)
    
    if not carga.archivo_metadata_csv:
        messages.error(request, 'No hay archivo CSV de metadata disponible')
        return redirect('indicadores:admin_cargas_dashboard')
    
    response = FileResponse(
        carga.archivo_metadata_csv.open('rb'),
        content_type='text/csv'
    )
    filename = f'metadata_{carga.codigo_evidencia}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@staff_member_required
def descargar_csv_conjunto_datos(request, carga_id):
    """Descarga el archivo CSV de conjunto_datos"""
    carga = get_object_or_404(CargaConjuntoDatos, id=carga_id)
    
    if not carga.archivo_microdata_csv:
        messages.error(request, 'No hay archivo CSV de conjunto_datos disponible')
        return redirect('indicadores:admin_cargas_dashboard')
    
    response = FileResponse(
        carga.archivo_microdata_csv.open('rb'),
        content_type='text/csv'
    )
    filename = f'conjunto_datos_{carga.codigo_evidencia}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@staff_member_required
def descargar_csv_metadata_variables(request, carga_id):
    """Descarga el archivo CSV de metadata de variables"""
    carga = get_object_or_404(CargaConjuntoDatos, id=carga_id)
    
    if not carga.archivo_metadata_variables_csv:
        messages.error(request, 'No hay archivo CSV de metadata de variables disponible')
        return redirect('indicadores:admin_cargas_dashboard')
    
    response = FileResponse(
        carga.archivo_metadata_variables_csv.open('rb'),
        content_type='text/csv'
    )
    filename = f'metadata_variables_{carga.codigo_evidencia}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


# ============================================================================
# WIZARD ADMIN UNIFICADO
# ============================================================================

@staff_member_required
def wizard_dashboard(request):
    """
    Dashboard de operaciones del wizard.
    Permite al admin visualizar todas las cargas pendientes, aprobadas,
    correcciones solicitadas, etc., con filtros y paginacion.
    """
    from datetime import timedelta
    from django.utils import timezone

    hoy = timezone.now().date()

    # --- Resumen de tarjetas ---
    resumen = {
        'aprobadas': CargaSerieIndicador.objects.filter(estado='aprobado').count(),
        'pendientes': CargaSerieIndicador.objects.filter(estado='pendiente').count(),
        'correcciones': CargaSerieIndicador.objects.filter(estado='correcciones_solicitadas').count(),
        'procesadas_hoy': CargaSerieIndicador.objects.filter(
            fecha_carga__date=hoy, estado__in=('procesado', 'exitoso')
        ).count(),
        'conjunto_datos_pendientes': CargaConjuntoDatos.objects.filter(estado='pendiente').count(),
        'conjunto_datos_aprobadas': CargaConjuntoDatos.objects.filter(estado='aprobado').count(),
    }

    # --- Filtros GET ---
    estado_filtro = request.GET.get('estado', '')
    origen_filtro = request.GET.get('origen', '')
    tipo_filtro = request.GET.get('tipo', '')
    busqueda = request.GET.get('q', '')

    # --- Queryset series ---
    qs_series = CargaSerieIndicador.objects.all().select_related(
        'usuario', 'indicador', 'validado_por'
    ).prefetch_related('carga_masiva_origen').order_by('-fecha_carga')

    if estado_filtro:
        qs_series = qs_series.filter(estado=estado_filtro)

    if origen_filtro == 'delegado':
        qs_series = qs_series.filter(es_carga_delegado=True)
    elif origen_filtro == 'interno':
        qs_series = qs_series.filter(es_carga_delegado=False, carga_masiva_origen__isnull=True)
    elif origen_filtro == 'masiva':
        qs_series = qs_series.filter(es_carga_delegado=False, carga_masiva_origen__isnull=False)

    if busqueda:
        qs_series = qs_series.filter(
            Q(codigo_evidencia__icontains=busqueda) |
            Q(indicador__nombre__icontains=busqueda) |
            Q(usuario__username__icontains=busqueda)
        )

    # --- Queryset conjunto_datos ---
    qs_conjunto_datos = CargaConjuntoDatos.objects.all().select_related(
        'usuario', 'conjunto_datos'
    ).order_by('-fecha_carga')

    if estado_filtro:
        qs_conjunto_datos = qs_conjunto_datos.filter(estado=estado_filtro)

    if origen_filtro == 'delegado':
        qs_conjunto_datos = qs_conjunto_datos.filter(es_carga_delegado=True)
    elif origen_filtro in ('interno', 'masiva'):
        qs_conjunto_datos = qs_conjunto_datos.filter(es_carga_delegado=False)

    if busqueda:
        qs_conjunto_datos = qs_conjunto_datos.filter(
            Q(codigo_evidencia__icontains=busqueda) |
            Q(conjunto_datos__nombre__icontains=busqueda) |
            Q(usuario__username__icontains=busqueda)
        )

    # --- Union paginada ---
    # Para la tabla principal mostramos series y conjunto_datos juntas.
    # Usamos una lista de dicts genericos para el template.
    items = []
    for c in qs_series[:200]:
        items.append({
            'tipo': 'serie',
            'obj': c,
            'id': c.id,
            'codigo': c.codigo_evidencia,
            'nombre': c.indicador.nombre if c.indicador else 'Sin indicador',
            'estado': c.estado,
            'origen': 'Delegado' if c.es_carga_delegado else ('Masiva' if c.carga_masiva_origen.exists() else 'Interno'),
            'usuario': c.usuario.get_full_name() or c.usuario.username,
            'fecha': c.fecha_carga,
            'observaciones_admin': c.observaciones_admin,
        })
    for c in qs_conjunto_datos[:200]:
        items.append({
            'tipo': 'conjunto_datos',
            'obj': c,
            'id': c.id,
            'codigo': c.codigo_evidencia,
            'nombre': c.conjunto_datos.nombre if c.conjunto_datos else 'Sin conjunto_datos',
            'estado': c.estado,
            'origen': 'Delegado' if c.es_carga_delegado else 'Interno',
            'usuario': c.usuario.get_full_name() or c.usuario.username,
            'fecha': c.fecha_carga,
            'observaciones_admin': '',
        })

    # Ordenar union por fecha descendente
    items.sort(key=lambda x: x['fecha'], reverse=True)

    # Filtrar por tipo si aplica
    if tipo_filtro == 'serie':
        items = [i for i in items if i['tipo'] == 'serie']
    elif tipo_filtro == 'conjunto_datos':
        items = [i for i in items if i['tipo'] == 'conjunto_datos']

    # Paginacion
    page = request.GET.get('page', 1)
    paginator = Paginator(items, 20)
    try:
        items_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        items_page = paginator.page(1)

    context = {
        'resumen': resumen,
        'items': items_page,
        'estado_filtro': estado_filtro,
        'origen_filtro': origen_filtro,
        'tipo_filtro': tipo_filtro,
        'busqueda': busqueda,
        'estados': ['', 'borrador', 'pendiente', 'enviado', 'aprobado', 'correcciones_solicitadas', 'rechazado', 'procesado', 'exitoso', 'error'],
        'origenes': ['', 'delegado', 'interno', 'masiva'],
        'tipos': ['', 'serie', 'conjunto_datos'],
    }
    return render(request, 'admin/wizard_unificado/dashboard.html', context)


@staff_member_required
def wizard_admin_unificado(request):
    """
    Vista del Wizard Admin Unificado.
    Detecta parámetros GET para pre-seleccionar cargas.
    """
    from .wizard_admin_unificado import WizardAdminUnificado
    from . import wizard_unificado_forms
    from formtools.wizard.views import SessionWizardView
    from django.core.files.storage import FileSystemStorage
    from django.conf import settings
    import os
    import tempfile
    
    # Detectar parámetros GET
    carga_conjunto_datos_id = request.GET.get('carga_conjunto_datos')
    carga_serie_id = request.GET.get('carga_serie')
    
    # Guardar en sesión para que el wizard los use
    if carga_conjunto_datos_id:
        request.session['wizard_carga_conjunto_datos_id'] = carga_conjunto_datos_id
    if carga_serie_id:
        request.session['wizard_carga_serie_id'] = carga_serie_id
    
    # Configurar almacenamiento temporal para archivos del wizard
    temp_storage_path = os.path.join(settings.MEDIA_ROOT, 'wizard_temp')
    os.makedirs(temp_storage_path, exist_ok=True)
    
    # Crear instancia del wizard con la lista de formularios inicial
    form_list = [
        ('seleccion_fuente', wizard_unificado_forms.FormSeleccionFuente),
    ]  
    
    # Crear clase temporal con file_storage configurado
    class WizardWithStorage(WizardAdminUnificado):
        file_storage = FileSystemStorage(location=temp_storage_path)
    
    wizard = WizardWithStorage.as_view(form_list=form_list)
    
    # Ejecutar el wizard
    return wizard(request)


@staff_member_required
def wizard_diagnostico_ajax(request):
    """
    Endpoint AJAX para diagnosticar una regla de extracción
    contra una muestra del CSV de conjunto_datos sin avanzar el wizard.
    """
    import json
    from django.http import JsonResponse
    from .models import CargaConjuntoDatos, Indicador, DominioDesagregacion
    from .utils_wizard import DiagnosticoConjuntoDatos, generar_output_diagnostico_html

    if request.method != 'POST':
        return JsonResponse({'error': 'Solo POST'}, status=405)

    try:
        carga_conjunto_datos_id = request.POST.get('carga_conjunto_datos_id')
        if not carga_conjunto_datos_id:
            return JsonResponse({'error': 'Falta carga_conjunto_datos_id'}, status=400)

        carga = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
        archivo_csv = carga.archivo_microdata_csv.path if carga.archivo_microdata_csv else None
        if not archivo_csv:
            return JsonResponse({'error': 'No hay archivo CSV de conjunto_datos'}, status=400)

        # Datos de la regla desde el POST
        columna_fecha = request.POST.get('columna_fecha', '').strip()
        columnas_fuente = request.POST.get('columnas_fuente', '').strip()
        formula = request.POST.get('formula', '').strip()
        filtros_json_str = request.POST.get('filtros_json', '').strip()
        orden_desagregaciones = request.POST.get('orden_desagregaciones', '').strip()

        # Validar mínimos
        if not columna_fecha or not columnas_fuente or not formula:
            return JsonResponse({'error': 'Faltan campos obligatorios de la regla'}, status=400)

        # Crear regla temporal
        class ReglaTemp:
            def __init__(self, cf, cols, f, fj, od):
                self.columna_fecha = cf
                self.columnas_fuente = cols
                self.formula = f
                self.filtros_json = fj
                self.orden_desagregaciones = od

        regla_temp = ReglaTemp(columna_fecha, columnas_fuente, formula,
                               filtros_json_str, orden_desagregaciones)

        # Crear indicador temporal con dominios mínimos
        indicador_id = request.POST.get('indicador_id')
        dominios_geo = []
        dominios_tem = []
        if indicador_id:
            try:
                indicador_real = Indicador.objects.prefetch_related(
                    'dominios_desagregacion_geografica',
                    'dominios_desagregacion_tematica'
                ).get(id=indicador_id)
                dominios_geo = list(indicador_real.dominios_desagregacion_geografica.all())
                dominios_tem = list(indicador_real.dominios_desagregacion_tematica.all())
            except Indicador.DoesNotExist:
                pass

        class IndicadorTemp:
            def __init__(self, dom_geo, dom_tem):
                self.dominios_desagregacion_geografica = DomManager(dom_geo)
                self.dominios_desagregacion_tematica = DomManager(dom_tem)

        class DomManager:
            def __init__(self, dominios):
                self._dominios = dominios
            def all(self):
                return self._dominios

        indicador_temp = IndicadorTemp(dominios_geo, dominios_tem)

        # Ejecutar diagnóstico
        diagnostico = DiagnosticoConjuntoDatos(archivo_csv)
        resultado = diagnostico.ejecutar_diagnostico_completo(regla_temp, indicador_temp)
        html_output = generar_output_diagnostico_html(resultado)

        return JsonResponse({
            'exitoso': resultado['exitoso'],
            'html': html_output,
            'errores': resultado.get('errores', []),
            'advertencias': resultado.get('advertencias', []),
        })

    except Exception as e:
        import traceback
        return JsonResponse({'error': str(e), 'trace': traceback.format_exc()}, status=500)


# ============================================================================
# ADMIN: SOLICITAR CORRECCIÓN DESDE EL WIZARD
# ============================================================================

@staff_member_required
def wizard_solicitar_correccion(request, carga_id):
    """
    El admin solicita correcciones al recolector desde el contexto del wizard.
    Actualiza estado, guarda observaciones y notifica al recolector.
    """
    from .notifications import notificar_recolector_correccion_solicitada

    carga = get_object_or_404(CargaSerieIndicador, id=carga_id)

    next_url = request.GET.get('next') or request.POST.get('next')

    if carga.estado not in ('pendiente', 'procesando'):
        messages.error(request, 'Esta carga no está en un estado que permita solicitar correcciones.')
        if next_url == 'dashboard':
            return redirect('wizard_dashboard')
        return redirect('wizard_admin_unificado')

    if request.method == 'POST':
        observaciones = request.POST.get('observaciones', '').strip()
        if not observaciones:
            messages.warning(request, 'Debe indicar qué correcciones se necesitan.')
            return redirect('wizard_solicitar_correccion', carga_id=carga.id)

        carga.estado = 'correcciones_solicitadas'
        carga.observaciones_admin = observaciones
        carga.save(update_fields=['estado', 'observaciones_admin'])

        # Notificar al recolector
        try:
            notificar_recolector_correccion_solicitada(carga, observaciones)
        except Exception:
            pass  # No bloquear por fallo de notificación

        messages.success(
            request,
            f'Corrección solicitada para {carga.codigo_evidencia}. Se notificó al recolector.'
        )
        if next_url == 'dashboard':
            return redirect('wizard_dashboard')
        return redirect('wizard_admin_unificado')

    context = {
        'carga': carga,
        'indicador': carga.indicador,
        'next': next_url,
    }
    return render(request, 'admin/wizard_unificado/solicitar_correccion.html', context)


# ============================================================================
# FORMULARIO SIMPLIFICADO DE GRÁFICO
# ============================================================================

@login_required
def crear_grafico_simplificado(request, indicador_id):
    """
    Vista simplificada para crear un gráfico básico desde el módulo de recolección.
    Solo captura la información esencial (tipo, ejes, nombre).
    El admin completará la configuración avanzada desde el panel de administración.
    """
    indicador = get_object_or_404(Indicador, id=indicador_id)
    
    # Verificar permisos: solo recolectores o staff
    if not request.user.is_staff and not (hasattr(request.user, 'perfil_recolector') and request.user.perfil_recolector.puede_recolectar()):
        messages.error(request, 'No tiene permisos para crear gráficos.')
        return redirect('indicadores:recoleccion_dashboard')
    
    from .forms_grafico import GraficoSimplificadoForm
    
    if request.method == 'POST':
        form = GraficoSimplificadoForm(request.POST, indicador=indicador)
        if form.is_valid():
            grafico = form.save()
            messages.success(
                request,
                f'✅ Gráfico "{grafico.nombre}" creado exitosamente. '
                f'El equipo SIIED completará la configuración avanzada desde el panel de administración.'
            )
            # Redirigir al detalle de la carga si viene de ahí
            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('indicadores:recoleccion_dashboard')
    else:
        form = GraficoSimplificadoForm(indicador=indicador)
    
    context = {
        'form': form,
        'indicador': indicador,
        'titulo_pagina': f'Configurar Gráfico: {indicador.nombre}',
    }
    
    return render(request, 'recoleccion/crear_grafico_simplificado.html', context)


# ============================================================================
# HELPERS PARA GENERACIÓN DE XLSX DESDE FORMULARIOS
# ============================================================================

def _generar_xlsx_datos(filas, desagregaciones=None):
    """
    Genera un xlsx con columnas (Año, Valor, [desagregaciones…]) a partir de
    una lista de dicts.  Retorna BytesIO listo para guardar.

    filas: list[dict] con claves 'fecha', 'valor' y opcionalmente
           'des_<nombre>' para cada desagregación.
    desagregaciones: list[str] con los nombres de las columnas extra.
    """
    import openpyxl
    desagregaciones = desagregaciones or []
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Datos'
    headers = ['Año', 'Valor'] + desagregaciones
    ws.append(headers)
    for fila in filas:
        row = [fila.get('fecha', ''), fila.get('valor', '')]
        for des in desagregaciones:
            row.append(fila.get(f'des_{des}', ''))
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _generar_xlsx_metadata_indicador(data):
    """
    Genera un xlsx de metadata de indicador a partir de un dict con los campos
    del formulario.  Usa columnas del estándar MSD del DANE.
    Retorna BytesIO listo para guardar.
    """
    columnas = [
        'Grupo_Indicador', 'Dominio', 'Tema', 'Subtema',
        'Codigo_Indicador', 'Nombre_Indicador', 'Sigla',
        # Sección 1: Contacto Institucional
        'Entidad_Institucion', 'Area_Dependencia',
        'Correo_Contacto', 'Telefono_Contacto',
        'Fecha_Publicacion_Metadatos',
        # Sección 2: Características del Indicador
        'Descripcion_Indicador',
        'Metodo_Medicion', 'Formula', 'Variables',
        'Unidad_Medida',
        'Nomenclaturas_Clasificaciones',
        'Alcance_Tematico', 'Poblacion_Objetivo',
        'Cobertura_Geografica', 'Periodo_Referencia', 'Periodo_Base',
        'Fuente_Datos', 'Responsable',
        # Sección 3: Difusión
        'Serie_Historica_Disponible', 'Frecuencia_Difusion', 'Medios_Difusion',
        # Sección 4: Comentarios
        'Comentarios_Adicionales',
        # SDMX: referencias y responsabilidad institucional
        'Referencias', 'Equipo_Responsable',
        'Nombre_Responsable_Validacion', 'Cargo_Responsable_Validacion',
        'Correo_Responsable_Validacion', 'Celular_Responsable_Validacion',
    ]
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Metadata'
    ws.append(columnas)
    ws.append([data.get(c, '') for c in columnas])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _generar_xlsx_variables(filas):
    """
    Genera un xlsx de metadata de variables a partir de una lista de dicts.
    Retorna BytesIO listo para guardar.
    """
    columnas = [
        'Codigo_Variable', 'Nombre_Variable', 'Definicion_Conceptual',
        'Tipo_Dato', 'Unidad_Medida', 'Periodicidad',
        'Fuente_Datos', 'Organismo_Productor', 'Observaciones',
        'Referencias',
    ]
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Variables'
    ws.append(columnas)
    for fila in filas:
        ws.append([fila.get(c, '') for c in columnas])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ============================================================================
# INGRESO INLINE DE DATOS — MÓDULO RECOLECCIÓN
# ============================================================================

@recolector_required
def cargar_serie_inline(request):
    """
    Permite ingresar los datos de una serie directamente en una tabla dinámica
    (sin subir un xlsx).  Genera el xlsx en memoria y crea el CargaSerieIndicador
    exactamente igual que la carga por archivo.

    Si se pasa ?indicador_id=ID, precarga los datos existentes para facilitar
    la actualización (siempre genera una nueva carga; nunca edita inplace).
    """
    indicadores = Indicador.objects.filter(activo=True).order_by('codigo_indicador')

    indicador_id_get = request.GET.get('indicador_id')
    indicador_pre = None
    datos_existentes = []
    desagregaciones_pre = []

    if indicador_id_get:
        try:
            indicador_pre = Indicador.objects.get(id=indicador_id_get, activo=True)
            datos_qs = indicador_pre.datos.select_related().prefetch_related(
                'desagregaciones_geograficas__dominio',
                'desagregaciones_tematicas__dominio'
            ).order_by('fecha_dato')

            des_cols = set()
            for dato in datos_qs:
                fila = {
                    'fecha': str(dato.fecha_dato.year) if dato.fecha_dato else '',
                    'valor': str(dato.valor_dato),
                }
                for des in dato.desagregaciones_geograficas.all():
                    col = des.dominio.nombre
                    des_cols.add(col)
                    fila[col] = des.nombre
                for des in dato.desagregaciones_tematicas.all():
                    col = des.dominio.nombre
                    des_cols.add(col)
                    fila[col] = des.nombre
                datos_existentes.append(fila)
            desagregaciones_pre = sorted(des_cols)
        except Indicador.DoesNotExist:
            pass

    if request.method == 'POST':
        indicador_id = request.POST.get('indicador_id')
        fechas = request.POST.getlist('fecha[]')
        valores = request.POST.getlist('valor[]')
        desagregaciones = [d.strip() for d in request.POST.getlist('desagregacion_nombre[]') if d.strip()]

        errores = []
        if not indicador_id:
            errores.append('Debes seleccionar un indicador.')

        filas = []
        for i, (f, v) in enumerate(zip(fechas, valores)):
            if f.strip() and v.strip():
                fila = {'fecha': f, 'valor': v}
                for des in desagregaciones:
                    vals = request.POST.getlist(f'desagregacion_valor_{des}[]')
                    fila[f'des_{des}'] = vals[i] if i < len(vals) else ''
                filas.append(fila)

        if not filas:
            errores.append('Debes ingresar al menos un dato (fecha y valor).')

        if errores:
            for e in errores:
                messages.error(request, e)
            return render(request, 'recoleccion/cargar_serie_inline.html', {
                'indicadores': indicadores,
                'indicador_pre': indicador_pre,
                'datos_existentes': datos_existentes,
                'desagregaciones_pre': desagregaciones_pre,
            })

        try:
            indicador = get_object_or_404(Indicador, id=indicador_id)
            buf = _generar_xlsx_datos(filas, desagregaciones=desagregaciones)

            carga = CargaSerieIndicador(
                usuario=request.user,
                indicador=indicador,
                estado='procesando',
                es_carga_delegado=False,
            )
            carga.archivo_datos_xlsx.save(
                f'datos_inline_{indicador.codigo_indicador}_{timezone.now().strftime("%Y%m%d%H%M%S")}.xlsx',
                ContentFile(buf.read()), save=False
            )
            carga.save()
            procesar_serie_indicador(carga)

            from .notifications import notificar_admins_nueva_carga_recoleccion_serie
            resultado = notificar_admins_nueva_carga_recoleccion_serie(carga)
            if resultado:
                messages.info(request, '✉️ Se notificó a los administradores por correo.')
            else:
                messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los administradores.')

            messages.success(
                request,
                f'✅ {len(filas)} datos ingresados para "{indicador.nombre}". '
                f'Código: {carga.codigo_evidencia}'
            )
            return redirect('indicadores:detalle_carga_serie', carga_id=carga.id)

        except Exception as e:
            messages.error(request, f'Error al guardar: {str(e)}')

    return render(request, 'recoleccion/cargar_serie_inline.html', {
        'indicadores': indicadores,
        'indicador_pre': indicador_pre,
        'datos_existentes': datos_existentes,
        'desagregaciones_pre': desagregaciones_pre,
    })


@recolector_required
def cargar_metadata_form(request):
    """
    Ingresa la metadata de un indicador mediante formulario web (sin xlsx).
    Genera el xlsx de metadata en memoria y lo adjunta a una CargaSerieIndicador
    existente (si se pasa carga_id) o crea una nueva carga de solo metadata.

    Si se pasa ?indicador_id=ID, precarga la metadata existente del indicador.
    """
    indicadores = Indicador.objects.filter(activo=True).order_by('codigo_indicador')
    cargas_pendientes = CargaSerieIndicador.objects.filter(
        usuario=request.user,
        estado__in=['pendiente', 'procesando'],
        archivo_metadata_xlsx=''
    ).order_by('-fecha_carga')[:20]

    organismos = Organismo.objects.filter(activo=True).order_by('nombre')
    suborganismos_pre = []

    indicador_id_get = request.GET.get('indicador_id')
    indicador_pre = None
    metadata_pre = {}
    carga_delegada_activa = None

    if indicador_id_get:
        try:
            indicador_pre = Indicador.objects.select_related(
                'subtema__tema__dominio', 'organismo_responsable', 'suborganismo'
            ).get(id=indicador_id_get, activo=True)
            i = indicador_pre
            # Verificar si hay carga delegada en curso para este indicador
            carga_delegada_activa = CargaSerieIndicador.objects.filter(
                indicador=i,
                estado__in=['enviado', 'en_revision', 'correcciones_solicitadas', 'borrador'],
                es_carga_delegado=True,
            ).order_by('-fecha_carga').first()
            metadata_pre = {
                'Grupo_Indicador': i.grupo_indicador or '',
                'Dominio': i.subtema.tema.dominio.nombre if i.subtema and i.subtema.tema and i.subtema.tema.dominio else '',
                'Tema': i.subtema.tema.nombre if i.subtema and i.subtema.tema else '',
                'Subtema': i.subtema.nombre if i.subtema else '',
                'Codigo_Indicador': i.codigo_indicador or '',
                'Nombre_Indicador': i.nombre or '',
                'Sigla': i.sigla or '',
                'Descripcion_Indicador': i.descripcion_indicador or '',
                'Justificacion': '',  # campo legacy eliminado
                'Metodo_Medicion': i.metodo_medicion or '',
                'Formula': i.formula_ficha or '',
                'Variables': i.variables or '',
                'Unidad_Medida': i.unidad_medida or '',
                'Valores_Referencia': '',  # campo legacy eliminado
                'Nomenclaturas_Clasificaciones': i.nomenclaturas_clasificaciones or '',
                'Alcance_Tematico': i.alcance_tematico or '',
                'Poblacion_Objetivo': i.poblacion_objetivo or '',
                'Cobertura_Geografica': i.cobertura_geografica or '',
                'Periodo_Referencia': i.periodo_referencia or '',
                'Periodo_Base': i.periodo_base or '',
                'Linea_Base': '',  # campo legacy eliminado
                'Periodicidad': '',  # campo legacy eliminado (usar Frecuencia_Difusion)
                'Fuente_Datos': i.fuente_datos or '',
                'Operacion_Estadistica': i.operacion.nombre if i.operacion else '',
                'Entidad_Responsable': i.entidad_responsable or '',
                'Comentarios_Adicionales': i.comentarios_adicionales or '',
                'Fecha_Elaboracion': str(i.fecha_elaboracion) if i.fecha_elaboracion else '',
                'Fecha_Actualizacion': str(i.fecha_actualizacion_ficha) if i.fecha_actualizacion_ficha else '',
                'Fecha_Publicacion_Metadatos': str(i.fecha_publicacion_metadatos) if i.fecha_publicacion_metadatos else '',
                'Correo_Contacto': i.correo_contacto or (i.organismo_responsable.email_contacto if i.organismo_responsable else '') or '',
                'Telefono_Contacto': i.telefono_contacto or '',
                'Entidad_Institucion': i.organismo_responsable.nombre if i.organismo_responsable else '',
                'Area_Dependencia': i.suborganismo.nombre if i.suborganismo else '',
                'Nombre_Conjunto_conjunto_datos': i.nombre_conjunto_datos or '',
                'Serie_Historica_Disponible': i.serie_historica_disponible or '',
                'Frecuencia_Difusion': i.frecuencia_difusion or '',
                'Medios_Difusion': i.medios_difusion or '',
                'Referencias': i.referencias or '',
                'Equipo_Responsable': i.equipo_responsable.nombre if i.equipo_responsable else '',
                'Nombre_Responsable_Validacion': i.nombre_responsable_validacion or '',
                'Cargo_Responsable_Validacion': i.cargo_responsable_validacion or '',
                'Correo_Responsable_Validacion': i.correo_responsable_validacion or '',
                'Celular_Responsable_Validacion': i.celular_responsable_validacion or '',
            }
            if i.organismo_responsable:
                suborganismos_pre = list(Suborganismo.objects.filter(
                    organismo=i.organismo_responsable, activo=True
                ).values('id', 'nombre').order_by('orden', 'nombre'))
        except Indicador.DoesNotExist:
            pass

    if request.method == 'POST':
        indicador_id = request.POST.get('indicador_id')
        carga_id = request.POST.get('carga_id')

        if not indicador_id:
            messages.error(request, 'Debes seleccionar un indicador.')
            unidades_existentes = list(
                Indicador.objects.exclude(unidad_medida__isnull=True)
                .exclude(unidad_medida='')
                .values_list('unidad_medida', flat=True)
                .distinct().order_by('unidad_medida')
            )
            return render(request, 'recoleccion/cargar_metadata_form.html', {
                'indicadores': indicadores, 'cargas_pendientes': cargas_pendientes,
                'unidades_existentes': unidades_existentes,
                'indicador_pre': indicador_pre, 'metadata_pre': metadata_pre,
                'organismos': organismos, 'suborganismos_pre': suborganismos_pre,
            })

        indicador = get_object_or_404(Indicador, id=indicador_id)

        campos = [
            'Grupo_Indicador', 'Dominio', 'Tema', 'Subtema',
            'Codigo_Indicador', 'Nombre_Indicador', 'Sigla',
            'Descripcion_Indicador',
            'Metodo_Medicion', 'Formula', 'Variables',
            'Unidad_Medida',
            'Nomenclaturas_Clasificaciones',
            'Alcance_Tematico', 'Poblacion_Objetivo',
            'Cobertura_Geografica', 'Periodo_Referencia', 'Periodo_Base',
            'Fuente_Datos', 'Operacion_Estadistica', 'Entidad_Responsable',
            'Comentarios_Adicionales',
            'Fecha_Publicacion_Metadatos',
            'Fecha_Elaboracion', 'Fecha_Actualizacion',
            'Correo_Contacto', 'Telefono_Contacto',
            'Entidad_Institucion', 'Area_Dependencia',
            'Nombre_Conjunto_conjunto_datos',
            'Serie_Historica_Disponible', 'Frecuencia_Difusion', 'Medios_Difusion',
            'Referencias', 'Equipo_Responsable',
            'Nombre_Responsable_Validacion', 'Cargo_Responsable_Validacion',
            'Correo_Responsable_Validacion', 'Celular_Responsable_Validacion',
        ]
        data = {c: request.POST.get(c, '') for c in campos}

        # Actualizar organismo / suborganismo
        organismo_id_post = request.POST.get('organismo_id')
        suborganismo_id_post = request.POST.get('suborganismo_id')

        # Completar en data las claves institucionales para el xlsx
        if organismo_id_post:
            try:
                org_sel = Organismo.objects.get(id=organismo_id_post, activo=True)
                data['Entidad_Institucion'] = org_sel.nombre
                data['Entidad_Responsable'] = org_sel.nombre
            except Organismo.DoesNotExist:
                pass
        if suborganismo_id_post:
            try:
                sub_sel = Suborganismo.objects.get(id=suborganismo_id_post, activo=True)
                data['Area_Dependencia'] = sub_sel.nombre
            except Suborganismo.DoesNotExist:
                pass

        buf = _generar_xlsx_metadata_indicador(data)
        nombre_archivo = f'metadata_{indicador.codigo_indicador}_{timezone.now().strftime("%Y%m%d%H%M%S")}.xlsx'

        if organismo_id_post:
            try:
                indicador.organismo_responsable = Organismo.objects.get(
                    id=organismo_id_post, activo=True
                )
            except Organismo.DoesNotExist:
                pass
        if suborganismo_id_post:
            try:
                indicador.suborganismo = Suborganismo.objects.get(
                    id=suborganismo_id_post, organismo=indicador.organismo_responsable, activo=True
                )
            except Suborganismo.DoesNotExist:
                pass

        # Actualizar indicador con campos MSD
        indicador.variables = data.get('Variables', '')
        indicador.descripcion_indicador = data.get('Descripcion_Indicador', '')
        indicador.metodo_medicion = data.get('Metodo_Medicion', '')
        indicador.formula_ficha = data.get('Formula', '')
        indicador.unidad_medida = data.get('Unidad_Medida', '')
        indicador.fuente_datos = data.get('Fuente_Datos', '')
        indicador.nomenclaturas_clasificaciones = data.get('Nomenclaturas_Clasificaciones', '')
        indicador.poblacion_objetivo = data.get('Poblacion_Objetivo', '')
        indicador.alcance_tematico = data.get('Alcance_Tematico', '')
        indicador.cobertura_geografica = data.get('Cobertura_Geografica', '')
        indicador.periodo_referencia = data.get('Periodo_Referencia', '')
        indicador.periodo_base = data.get('Periodo_Base', '')
        indicador.serie_historica_disponible = data.get('Serie_Historica_Disponible', '')
        indicador.frecuencia_difusion = data.get('Frecuencia_Difusion', '')
        indicador.medios_difusion = data.get('Medios_Difusion', '')
        indicador.comentarios_adicionales = data.get('Comentarios_Adicionales', '')
        # Identificación: solo si vienen con valor (evita borrado accidental)
        for clave, campo in (
            ('Codigo_Indicador', 'codigo_indicador'),
            ('Nombre_Indicador', 'nombre'),
            ('Sigla', 'sigla'),
            ('Grupo_Indicador', 'grupo_indicador'),
        ):
            valor = (data.get(clave) or '').strip()
            if valor:
                setattr(indicador, campo, valor)
        # Campos SDMX adicionales
        indicador.referencias = data.get('Referencias', '')
        indicador.nombre_responsable_validacion = data.get('Nombre_Responsable_Validacion', '')
        indicador.cargo_responsable_validacion = data.get('Cargo_Responsable_Validacion', '')
        indicador.correo_responsable_validacion = data.get('Correo_Responsable_Validacion', '')
        indicador.celular_responsable_validacion = data.get('Celular_Responsable_Validacion', '')
        # Equipo responsable: resolver por nombre en catálogo EquipoOrganismo
        equipo_txt = (data.get('Equipo_Responsable') or '').strip()
        if equipo_txt:
            eq_qs = EquipoOrganismo.objects.filter(nombre__iexact=equipo_txt, activo=True)
            if indicador.suborganismo_id:
                eq_qs = eq_qs.filter(suborganismo_id=indicador.suborganismo_id)
            eq = eq_qs.first()
            if eq:
                indicador.equipo_responsable = eq
        elif 'Equipo_Responsable' in data:
            indicador.equipo_responsable = None
        indicador.correo_contacto = data.get('Correo_Contacto', '')
        indicador.telefono_contacto = data.get('Telefono_Contacto', '')
        indicador.nombre_conjunto_datos = data.get('Nombre_Conjunto_conjunto_datos', '')

        # Entidad responsable (1.1): se deriva del organismo seleccionado
        if data.get('Entidad_Responsable'):
            indicador.entidad_responsable = data['Entidad_Responsable']
        elif indicador.organismo_responsable:
            indicador.entidad_responsable = indicador.organismo_responsable.nombre

        # Operación estadística (2.9): resolver por nombre en catálogo
        operacion_txt = (data.get('Operacion_Estadistica') or '').strip()
        if operacion_txt:
            op = OperacionEstadistica.objects.filter(nombre__iexact=operacion_txt).first()
            if not op:
                op = OperacionEstadistica.objects.filter(nombre__icontains=operacion_txt).first()
            if op:
                indicador.operacion = op
        elif 'Operacion_Estadistica' in data:
            indicador.operacion = None

        # Fechas
        for campo_fecha in ('fecha_publicacion_metadatos', 'fecha_elaboracion', 'fecha_actualizacion_ficha'):
            clave = 'Fecha_Actualizacion' if campo_fecha == 'fecha_actualizacion_ficha' else campo_fecha.replace('fecha_', 'Fecha_').title()
            valor = data.get(clave, '')
            if valor:
                setattr(indicador, campo_fecha, valor)

        indicador.save()
        _crear_o_actualizar_conjunto_datos_desde_variables(indicador)

        try:
            if carga_id:
                carga = get_object_or_404(CargaSerieIndicador, id=carga_id, usuario=request.user)
                carga.archivo_metadata_xlsx.save(nombre_archivo, ContentFile(buf.read()), save=False)
                carga.save()
                from .notifications import notificar_admins_nueva_carga_recoleccion_serie
                resultado = notificar_admins_nueva_carga_recoleccion_serie(carga)
                if resultado:
                    messages.info(request, '✉️ Se notificó a los administradores por correo.')
                else:
                    messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los administradores.')
            else:
                carga = CargaSerieIndicador(
                    usuario=request.user,
                    indicador=indicador,
                    estado='procesando',
                    es_carga_delegado=False,
                )
                carga.archivo_metadata_xlsx.save(nombre_archivo, ContentFile(buf.read()), save=False)
                carga.save()
                procesar_serie_indicador(carga)
                from .notifications import notificar_admins_nueva_carga_recoleccion_serie
                resultado = notificar_admins_nueva_carga_recoleccion_serie(carga)
                if resultado:
                    messages.info(request, '✉️ Se notificó a los administradores por correo.')
                else:
                    messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los administradores.')

            messages.success(request, f'✅ Metadata guardada. Código: {carga.codigo_evidencia}')
            return redirect('indicadores:detalle_carga_serie', carga_id=carga.id)

        except Exception as e:
            messages.error(request, f'Error al guardar metadata: {str(e)}')

    unidades_existentes = list(
        Indicador.objects.exclude(unidad_medida__isnull=True)
        .exclude(unidad_medida='')
        .values_list('unidad_medida', flat=True)
        .distinct().order_by('unidad_medida')
    )

    return render(request, 'recoleccion/cargar_metadata_form.html', {
        'indicadores': indicadores,
        'cargas_pendientes': cargas_pendientes,
        'indicador_pre': indicador_pre,
        'metadata_pre': metadata_pre,
        'organismos': organismos,
        'suborganismos_pre': suborganismos_pre,
        'carga_delegada_activa': carga_delegada_activa,
        'unidades_existentes': unidades_existentes,
    })


@recolector_required
def cargar_variables_form(request):
    """
    Ingresa la metadata de variables de una conjunto_datos mediante tabla inline (sin xlsx).
    Genera el xlsx de variables y lo adjunta a una CargaConjuntoDatos.

    Si se pasa ?conjunto_datos_id=ID, precarga las variables existentes.
    """
    conjuntos_datos = ConjuntoDatos.objects.all().order_by('nombre')
    cargas_sin_variables = CargaConjuntoDatos.objects.filter(
        usuario=request.user,
        estado__in=['pendiente', 'procesando'],
        archivo_metadata_variables_xlsx=''
    ).order_by('-fecha_carga')[:20]

    conjunto_datos_id_get = request.GET.get('conjunto_datos_id')
    conjunto_datos_pre = None
    variables_pre = []

    if conjunto_datos_id_get:
        try:
            conjunto_datos_pre = ConjuntoDatos.objects.get(id=conjunto_datos_id_get)
            variables_pre = list(conjunto_datos_pre.variables.values(
                'codigo_variable', 'nombre_variable', 'definicion_conceptual',
                'tipo_dato', 'unidad_medida', 'periodicidad',
                'fuente_datos', 'organismo_productor__nombre', 'organismo_productor_legado',
                'observaciones', 'referencias'
            ))
            for v in variables_pre:
                v['organismo_productor'] = v.pop('organismo_productor__nombre') or v.pop('organismo_productor_legado') or ''
        except ConjuntoDatos.DoesNotExist:
            pass

    if request.method == 'POST':
        carga_id = request.POST.get('carga_id')
        conjunto_datos_id = request.POST.get('conjunto_datos_id')

        codigos = request.POST.getlist('Codigo_Variable[]')
        nombres = request.POST.getlist('Nombre_Variable[]')
        definiciones = request.POST.getlist('Definicion_Conceptual[]')
        tipos = request.POST.getlist('Tipo_Dato[]')
        unidades = request.POST.getlist('Unidad_Medida[]')
        periodicidades = request.POST.getlist('Periodicidad[]')
        fuentes = request.POST.getlist('Fuente_Datos[]')
        organismos = request.POST.getlist('Organismo_Productor[]')
        observaciones = request.POST.getlist('Observaciones[]')
        referencias_list = request.POST.getlist('Referencias[]')

        # ------------------------------------------------------------------
        # Validación: solo se permiten variables ya existentes en la conjunto_datos
        # ------------------------------------------------------------------
        conjunto_datos_obj = None
        if conjunto_datos_id:
            conjunto_datos_obj = ConjuntoDatos.objects.filter(id=conjunto_datos_id).first()

        if conjunto_datos_obj:
            codigos_existentes = set(
                conjunto_datos_obj.variables.values_list('codigo_variable', flat=True)
            )
        else:
            codigos_existentes = set()

        filas = []
        for i in range(len(codigos)):
            if codigos[i].strip():
                codigo = codigos[i].strip()
                # Si hay conjunto_datos con variables, rechazar códigos nuevos
                if codigos_existentes and codigo not in codigos_existentes:
                    messages.error(
                        request,
                        f'La variable "{codigo}" no existe en la conjunto_datos. '
                        f'Solo puedes actualizar variables previamente creadas desde '
                        f'la metadata del indicador. Códigos válidos: {", ".join(sorted(codigos_existentes))}'
                    )
                    return render(request, 'recoleccion/cargar_variables_form.html', {
                        'conjuntos_datos': conjuntos_datos, 'cargas_sin_variables': cargas_sin_variables,
                        'conjunto_datos_pre': conjunto_datos_pre, 'variables_pre': variables_pre,
                    })
                filas.append({
                    'Codigo_Variable': codigo,
                    'Nombre_Variable': nombres[i] if i < len(nombres) else '',
                    'Definicion_Conceptual': definiciones[i] if i < len(definiciones) else '',
                    'Tipo_Dato': tipos[i] if i < len(tipos) else '',
                    'Unidad_Medida': unidades[i] if i < len(unidades) else '',
                    'Periodicidad': periodicidades[i] if i < len(periodicidades) else '',
                    'Fuente_Datos': fuentes[i] if i < len(fuentes) else '',
                    'Organismo_Productor': organismos[i] if i < len(organismos) else '',
                    'Observaciones': observaciones[i] if i < len(observaciones) else '',
                    'Referencias': referencias_list[i] if i < len(referencias_list) else '',
                })

        if not filas:
            messages.error(request, 'Debes ingresar al menos una variable.')
            return render(request, 'recoleccion/cargar_variables_form.html', {
                'conjuntos_datos': conjuntos_datos, 'cargas_sin_variables': cargas_sin_variables,
                'conjunto_datos_pre': conjunto_datos_pre, 'variables_pre': variables_pre,
            })

        buf = _generar_xlsx_variables(filas)
        nombre_archivo = f'variables_inline_{timezone.now().strftime("%Y%m%d%H%M%S")}.xlsx'

        try:
            if carga_id:
                carga = get_object_or_404(CargaConjuntoDatos, id=carga_id, usuario=request.user)
            else:
                carga = CargaConjuntoDatos(
                    usuario=request.user,
                    estado='procesando',
                    conjunto_datos=ConjuntoDatos.objects.filter(id=conjunto_datos_id).first() if conjunto_datos_id else None,
                )
            carga.archivo_metadata_variables_xlsx.save(nombre_archivo, ContentFile(buf.read()), save=False)
            carga.save()

            messages.success(request, f'✅ {len(filas)} variables guardadas. Código: {carga.codigo_evidencia}')
            return redirect('indicadores:detalle_carga_conjunto_datos', carga_id=carga.id)

        except Exception as e:
            messages.error(request, f'Error al guardar variables: {str(e)}')

    return render(request, 'recoleccion/cargar_variables_form.html', {
        'conjuntos_datos': conjuntos_datos,
        'cargas_sin_variables': cargas_sin_variables,
        'conjunto_datos_pre': conjunto_datos_pre,
        'variables_pre': variables_pre,
    })


# ============================================================================
# DESCUBRIMIENTO — Actualizar indicadores/conjunto_datos existentes
# ============================================================================

@recolector_required
def actualizar_existente(request):
    """
    Permite buscar indicadores o conjunto_datos activos para actualizarlos
    mediante los formularios inline (sin necesidad de tener una carga previa).
    """
    q = request.GET.get('q', '').strip()

    indicadores = Indicador.objects.filter(activo=True)
    conjuntos_datos = ConjuntoDatos.objects.all()

    if q:
        indicadores = indicadores.filter(
            Q(nombre__icontains=q) | Q(codigo_indicador__icontains=q)
        )
        conjuntos_datos = conjuntos_datos.filter(
            Q(nombre__icontains=q)
        )

    indicadores = indicadores.order_by('codigo_indicador')[:50]
    conjuntos_datos = conjuntos_datos.order_by('nombre')[:50]

    return render(request, 'recoleccion/actualizar_existente.html', {
        'indicadores': indicadores,
        'conjuntos_datos': conjuntos_datos,
        'q': q,
    })


def recoleccion_manual(request):
    """Manual de uso del módulo de recolección."""
    return render(request, 'recoleccion/manual.html')


# ============================================================================
# CARGA MASIVA DE SERIES
# ============================================================================

@recolector_required
def cargar_masiva_series(request):
    """
    Vista para cargar archivos maestros con datos y/o metadata de múltiples indicadores.
    Soporta: solo datos, solo metadata, o ambos (con archivos separados).
    """
    from .forms_recoleccion import CargarMasivaForm

    if request.method == 'POST':
        form = CargarMasivaForm(request.POST, request.FILES)
        if form.is_valid():
            carga_masiva = form.save(commit=False)
            carga_masiva.usuario = request.user
            carga_masiva.estado = 'procesando'
            carga_masiva.save()

            try:
                resultado = _procesar_archivo_masivo(carga_masiva)
                if resultado.get('error'):
                    carga_masiva.estado = 'error'
                    carga_masiva.mensaje_error = resultado['error']
                    carga_masiva.save()
                    messages.error(request, f"Error en carga masiva: {resultado['error']}")
                    return redirect('indicadores:cargar_masiva_series')

                # Actualizar estado según tipo de carga
                if carga_masiva.tipo_carga == 'metadata':
                    carga_masiva.estado = 'finalizada'
                    carga_masiva.save()
                    messages.success(
                        request,
                        f"✅ Metadata actualizada para {len(resultado.get('indicadores', []))} indicadores. "
                        f"Código: {carga_masiva.codigo_evidencia}"
                    )
                    return redirect('indicadores:recoleccion_dashboard')
                else:
                    # Datos o ambos: pasar a revisión del recolector
                    carga_masiva.estado = 'validacion_recolector'
                    carga_masiva.save()
                    n_ind = len(resultado.get('indicadores', []))
                    n_warn = len(resultado.get('advertencias', []))
                    msg = f"Archivo parseado: {n_ind} indicadores detectados."
                    if n_warn:
                        msg += f" {n_warn} advertencia(s) requieren tu atención."
                    messages.info(request, msg)
                    return redirect('indicadores:revisar_masiva', carga_masiva_id=carga_masiva.id)

            except Exception as e:
                carga_masiva.estado = 'error'
                carga_masiva.mensaje_error = str(e)
                carga_masiva.save()
                messages.error(request, f"Error procesando carga masiva: {str(e)}")
                return redirect('indicadores:cargar_masiva_series')
    else:
        form = CargarMasivaForm()

    # Contexto de referencia UX: dominios e indicadores existentes
    from .models import DominioDesagregacion, Desagregacion

    desag_prefetch = Prefetch(
        'desagregaciones', queryset=Desagregacion.objects.order_by('nombre')
    )
    dominios_geo = (
        DominioDesagregacion.objects.filter(tipo='geografica')
        .prefetch_related(desag_prefetch)
        .order_by('nombre')
    )
    dominios_tem = (
        DominioDesagregacion.objects.filter(tipo='tematica')
        .prefetch_related(desag_prefetch)
        .order_by('nombre')
    )

    # Anotar cada dominio con sus desagregaciones para el tooltip
    dominios_geo_info = []
    for d in dominios_geo:
        desag_list = list(d.desagregaciones.all())
        dominios_geo_info.append({
            'nombre': d.nombre,
            'desagregaciones': [des.nombre for des in desag_list[:10]],
            'total': len(desag_list),
        })
    dominios_tem_info = []
    for d in dominios_tem:
        desag_list = list(d.desagregaciones.all())
        dominios_tem_info.append({
            'nombre': d.nombre,
            'desagregaciones': [des.nombre for des in desag_list[:10]],
            'total': len(desag_list),
        })

    context = {
        'form': form,
        'dominios_geo_info': dominios_geo_info,
        'dominios_tem_info': dominios_tem_info,
        # Dominios creados por cargas aún no admitidos al catálogo — alimenta
        # el aviso "solicita conciliación si ves dominios repetidos".
        'n_dominios_pendientes': DominioDesagregacion.objects.filter(
            en_catalogo=False).count(),
    }
    return render(request, 'recoleccion/cargar_masiva_series.html', context)


def _leer_archivo_a_df(archivo, hojas_preferidas=None, con_col_codigo=False):
    """Lee un archivo Excel o CSV y retorna (DataFrame, error|None).

    Lee el contenido con archivo.read() en un BytesIO en vez de
    archivo.path — .path no existe en uploads en memoria ni en storages
    sin filesystem, y además rompe si el archivo desapareció del disco.
    En fallo devuelve (None, razón) para que el mensaje al usuario
    muestre la causa real en vez de 'verifique el formato' a ciegas.

    hojas_preferidas: lista de nombres de hoja a intentar primero
    (case-insensitive, coincidencia por igualdad o 'contiene'). La
    plantilla oficial de metadatos trae 'Diccionario de datos' en la
    hoja 0 — sin preferencia se leería esa hoja en vez de 'Indicadores'.

    con_col_codigo=True: recorre las hojas en orden de preferencia (exacta,
    parcial, resto) probando las primeras filas como encabezado, y devuelve
    la primera hoja que contenga la columna de código de indicador. Útil
    cuando una coincidencia parcial ('datos' ↔ 'Diccionario de datos') o
    una fila de título dejarían la columna invisible. Si ninguna hoja la
    tiene, devuelve la lectura de la hoja preferida para que el error de
    validación posterior siga siendo el mismo.
    """
    if not archivo:
        return None, 'no se recibió ningún archivo'
    extension = (archivo.name or '').lower().split('.')[-1]
    if extension not in ('xlsx', 'xls', 'csv'):
        return None, (f'extensión ".{extension}" no soportada; '
                      'use .xlsx, .xls o .csv')
    try:
        archivo.seek(0)
    except Exception:
        pass
    try:
        contenido = BytesIO(archivo.read())
    except Exception as e:
        return None, f'no se pudo acceder al contenido del archivo ({e})'
    try:
        if extension in ('xlsx', 'xls'):
            libro = pd.ExcelFile(contenido)
            if not hojas_preferidas:
                return pd.read_excel(libro, sheet_name=libro.sheet_names[0]), None
            # Orden de preferencia: exacta por cada pref, luego parcial,
            # y al final las demás hojas (orden[0] = la hoja elegida
            # histórica, preserva el comportamiento previo).
            orden = []
            nombres = {h.lower(): h for h in libro.sheet_names}
            for pref in hojas_preferidas:
                p = pref.lower()
                if p in nombres and nombres[p] not in orden:
                    orden.append(nombres[p])
                for h in libro.sheet_names:
                    if p in h.lower() and h not in orden:
                        orden.append(h)
            orden += [h for h in libro.sheet_names if h not in orden]

            if con_col_codigo:
                for hoja in orden:
                    for hdr in (0, 1, 2):
                        try:
                            df = pd.read_excel(libro, sheet_name=hoja, header=hdr)
                        except Exception:
                            break
                        if _obtener_col_codigo(df):
                            return df, None
            return (pd.read_excel(libro, sheet_name=orden[0] if orden else libro.sheet_names[0]),
                    None)
        elif extension == 'csv':
            mejor_df = None
            mejor_cols = 0
            for encoding in ('utf-8', 'utf-8-sig', 'latin-1', 'iso-8859-1'):
                for sep in (';', ',', '\t'):
                    try:
                        contenido.seek(0)
                        df = pd.read_csv(contenido, encoding=encoding, sep=sep)
                        if len(df.columns) > mejor_cols:
                            mejor_df = df
                            mejor_cols = len(df.columns)
                    except (UnicodeDecodeError, pd.errors.ParserError):
                        continue
                if mejor_df is not None and mejor_cols > 1:
                    return mejor_df, None
            return mejor_df, None
        else:
            return None, f'extensión ".{extension}" no soportada'
    except Exception as e:
        # causa real (motor faltante, archivo dañado, hoja ausente…)
        # — antes se tragaba en silencio
        return None, f'{type(e).__name__}: {e}'


def _obtener_col_codigo(df):
    """Busca y retorna el nombre de la columna de código de indicador.

    Normaliza cada encabezado antes de comparar (sin tildes, sin prefijo
    numérico MSD tipo '0.2 ', snake_case, alias de plantilla oficial), así
    'Código del Indicador', 'ID_Indicador_SIIED' o '0.2 Código del
    Indicador' también se reconocen. Devuelve el nombre real de la columna.
    """
    import re
    from .models import normalizar_ascii
    posibles = {'codigo_indicador', 'codigo', 'id_indicador', 'indicador_codigo'}
    for col in df.columns:
        c = normalizar_ascii(str(col).strip().lower())
        c = re.sub(r'^\s*\d+(?:\.\d+)*\s*[\.\)\-:]?\s+', '', c)
        c = re.sub(r'[^a-z0-9]+', '_', c).strip('_')
        c = _COLUMNAS_METADATA_ALIAS.get(c, c)
        if c in posibles:
            return col
    return None


# ---------------------------------------------------------------------------
# Normalización de encabezados de la plantilla MSD
# ---------------------------------------------------------------------------
# El Excel del estándar usa encabezados "N.N Nombre Campo" (ej: "2.5 Fórmula",
# "1.4 Correo Electrónico de Contacto"). Este mapeo lleva el encabezado
# normalizado (sin prefijo numérico, sin tildes, snake_case) al nombre canónico
# de columna que entiende _actualizar_metadata_indicador_masiva.
_COLUMNAS_METADATA_ALIAS = {
    # Identificación (0.x)
    'nombre_del_indicador': 'nombre_indicador',
    'nombre_indicador': 'nombre_indicador',
    'codigo_del_indicador': 'codigo_indicador',
    'codigo_indicador': 'codigo_indicador',
    'id_indicador_siied': 'codigo_indicador',      # plantilla oficial
    'codigo': 'codigo_indicador',
    'sigla': 'sigla',
    'sigla_o_abreviatura': 'sigla',                # plantilla oficial
    'grupo_indicador': 'grupo_indicador',
    'grupo': 'grupo_indicador',
    # Taxonomía SIIED (plantilla oficial): se resuelven a MenuSubtema
    'dominio': 'dominio',
    'tema': 'tema',
    'subtema': 'subtema',
    # Sección 1 — Contacto Institucional
    'entidad_o_institucion_responsable': 'entidad_responsable',
    'entidad_institucion': 'entidad_institucion',
    'entidad_responsable': 'entidad_responsable',
    'responsable': 'entidad_responsable',
    'entidad_organismo_registrado': 'organismo_responsable',
    'organismo_responsable': 'organismo_responsable',
    'area_o_dependencia_responsable': 'suborganismo',
    'area_dependencia': 'suborganismo',
    'suborganismo': 'suborganismo',
    'suborganismo_responsable': 'suborganismo',    # plantilla oficial
    'correo_electronico_de_contacto': 'correo_contacto',
    'direccion_de_correo_electronico_de_contacto': 'correo_contacto',  # oficial
    'correo_electronico': 'correo_contacto',
    'correo_contacto': 'correo_contacto',
    'numero_telefonico': 'telefono_contacto',
    'telefono_contacto': 'telefono_contacto',
    'telefono': 'telefono_contacto',
    'fecha_de_publicacion_de_los_metadatos': 'fecha_publicacion_metadatos',
    'fecha_publicacion_metadatos': 'fecha_publicacion_metadatos',
    'fecha_publicacion': 'fecha_publicacion_metadatos',
    # Sección 2 — Características
    'descripcion_del_indicador': 'descripcion_indicador',
    'descripcion_indicador': 'descripcion_indicador',
    'descripcion': 'descripcion_indicador',
    'definiciones_conceptos': 'descripcion_indicador',
    'definiciones_y_conceptos': 'descripcion_indicador',
    'objetivo': 'objetivo',
    'justificacion': 'objetivo',
    'calculo_del_indicador_metodo_de_medicion': 'metodo_medicion',
    'calculo_del_indicador': 'metodo_medicion',
    'metodo_de_medicion': 'metodo_medicion',
    'metodo_medicion': 'metodo_medicion',
    'formula': 'formula_ficha',
    'formula_ficha': 'formula_ficha',
    'variables': 'variables',
    'unidad_de_medida': 'unidad_medida',
    'unidad_medida': 'unidad_medida',
    'fuente_de_la_informacion': 'fuente_datos',
    'fuente_de_datos': 'fuente_datos',
    'fuente_datos': 'fuente_datos',
    'fuente': 'fuente_datos',
    'nombre_de_la_operacion_estadistica': 'operacion',
    'operacion_estadistica': 'operacion',
    'operacion': 'operacion',
    'nombre_del_conjunto_de_datos': 'nombre_conjunto_datos',
    'nombre_conjunto_datos': 'nombre_conjunto_datos',
    'nombre_conjunto_conjunto_datos': 'nombre_conjunto_datos',  # forms inline
    'nomenclaturas_y_clasificaciones': 'nomenclaturas_clasificaciones',
    'nomenclaturas_y_clasificaciones_estadisticas': 'nomenclaturas_clasificaciones',
    'nomenclatura_y_clasificaciones_estadisticas': 'nomenclaturas_clasificaciones',  # oficial
    'nomenclaturas_clasificaciones': 'nomenclaturas_clasificaciones',
    'alcance_tematico': 'alcance_tematico',
    'poblacion_objetivo': 'poblacion_objetivo',
    'cobertura_geografica': 'cobertura_geografica',
    'periodo_de_referencia': 'periodo_referencia',
    'periodo_referencia': 'periodo_referencia',
    'periodo_base': 'periodo_base',
    # Sección 3 — Difusión
    'serie_historica_disponible': 'serie_historica_disponible',
    'frecuencia_de_difusion': 'frecuencia_difusion',
    'frecuencia_difusion': 'frecuencia_difusion',
    'periodicidad': 'frecuencia_difusion',
    'medios_de_difusion': 'medios_difusion',
    'medios_difusion': 'medios_difusion',
    # Sección 4 — Comentarios
    'comentarios_adicionales': 'comentarios_adicionales',
    'comentarios': 'comentarios_adicionales',
    'observaciones': 'comentarios_adicionales',
    # Sección 5 — Referencias
    'referencias_apa_7': 'referencias',
    'referencias': 'referencias',
    # Sección 6 — Responsabilidad
    'equipo_responsable': 'equipo_responsable',
    # Plantilla oficial — responsable técnico de validación
    'nombre_responsable_tecnico_de_validacion': 'nombre_responsable_validacion',
    'cargo_responsable_tecnico_de_validacion': 'cargo_responsable_validacion',
    'correo_electronico_del_responsable_tecnico_del_indicador': 'correo_responsable_validacion',
    'celular_responsable_tecnico_de_validacion': 'celular_responsable_validacion',
    # Trazabilidad
    'fecha_elaboracion': 'fecha_elaboracion',
    'fecha_actualizacion': 'fecha_actualizacion',
    'linea_base': 'linea_base',
    'valores_referencia': 'valores_referencia',
}


def _normalizar_columnas_metadata(columns):
    """
    Normaliza encabezados del Excel de metadata al esquema canónico:
    quita prefijo numérico MSD ('2.5 ', '2.16.'), tildes, y aplica alias.
    Devuelve la lista de nombres canónicos para df.columns.
    """
    import re
    from .models import normalizar_ascii

    normalizadas = []
    for col in columns:
        c = normalizar_ascii(str(col).strip().lower())
        # Quitar prefijo numérico de sección MSD: "2.5 Formula" -> "formula"
        c = re.sub(r'^\s*\d+(?:\.\d+)*\s*[\.\)\-:]?\s+', '', c)
        # snake_case
        c = re.sub(r'[^a-z0-9]+', '_', c).strip('_')
        c = _COLUMNAS_METADATA_ALIAS.get(c, c)
        normalizadas.append(c)
    return normalizadas


def _procesar_archivo_masivo(carga_masiva):
    """
    Procesa los archivos maestros de una CargaMasivaSerie.
    Puede procesar archivo de datos, de metadata, o ambos.
    Retorna dict con indicadores y errores.
    """
    tipo = carga_masiva.tipo_carga
    df_datos = None
    df_metadata = None
    errores_acumulados = []

    # Leer archivo de datos si aplica
    if tipo in ('datos', 'ambos') and carga_masiva.archivo_maestro_datos:
        df_datos, err_datos = _leer_archivo_a_df(
            carga_masiva.archivo_maestro_datos,
            hojas_preferidas=('datos',),
            con_col_codigo=True)
        if df_datos is None:
            return {'error': 'No se pudo leer el archivo maestro de datos. '
                             f'({err_datos})'}
    # Leer archivo de metadata si aplica
    if tipo in ('metadata', 'ambos') and carga_masiva.archivo_maestro_metadata:
        df_metadata, err_meta = _leer_archivo_a_df(
            carga_masiva.archivo_maestro_metadata,
            hojas_preferidas=('indicadores', 'metadata'),
            con_col_codigo=True)
        if df_metadata is None:
            return {'error': 'No se pudo leer el archivo maestro de metadata. '
                             f'({err_meta})'}

    # Validar columnas de código
    col_codigo_datos = None
    col_codigo_metadata = None

    if df_datos is not None:
        df_datos.columns = [str(c).strip().lower().replace(' ', '_') for c in df_datos.columns]
        col_codigo_datos = _obtener_col_codigo(df_datos)
        if not col_codigo_datos:
            return {'error': 'El archivo de datos no contiene la columna "codigo_indicador".'}
        df_datos[col_codigo_datos] = df_datos[col_codigo_datos].astype(str).str.strip()
        df_datos = df_datos[df_datos[col_codigo_datos].notna() & (df_datos[col_codigo_datos] != '') & (df_datos[col_codigo_datos] != 'nan')]
        if df_datos.empty:
            return {'error': 'El archivo de datos no contiene filas con código de indicador válido.'}

    if df_metadata is not None:
        df_metadata.columns = _normalizar_columnas_metadata(df_metadata.columns)
        col_codigo_metadata = _obtener_col_codigo(df_metadata)
        if not col_codigo_metadata:
            return {'error': 'El archivo de metadata no contiene la columna "codigo_indicador".'}
        df_metadata[col_codigo_metadata] = df_metadata[col_codigo_metadata].astype(str).str.strip()
        df_metadata = df_metadata[df_metadata[col_codigo_metadata].notna() & (df_metadata[col_codigo_metadata] != '') & (df_metadata[col_codigo_metadata] != 'nan')]
        if df_metadata.empty:
            return {'error': 'El archivo de metadata no contiene filas con código de indicador válido.'}

    # Construir conjunto de códigos a procesar
    codigos = set()
    if df_datos is not None:
        codigos.update(df_datos[col_codigo_datos].unique())
    if df_metadata is not None:
        codigos.update(df_metadata[col_codigo_metadata].unique())

    # --- Detectar columnas de desagregación (comunes a todos los indicadores) ---
    from .models import DominioDesagregacion
    dominios_detectados = []
    advertencias = []

    if df_datos is not None:
        columnas = list(df_datos.columns)
        col_fecha = _detectar_columna(columnas, _COLS_FECHA)
        col_valor = _detectar_columna(columnas, _COLS_VALOR)

        if not col_fecha:
            advertencias.append('No se detectó columna de fecha (año/fecha/periodo/vigencia).')
        if not col_valor:
            advertencias.append('No se detectó columna de valor (valor/dato/value/cantidad).')

        # Columnas restantes = posibles dominios de desagregación
        for col_name in columnas:
            if col_name in _COLS_NO_DESAGREGACION or col_name == col_fecha or col_name == col_valor or col_name == col_codigo_datos:
                continue
            nombre_dominio = col_name.replace('_', ' ').strip().title()
            tipo_sugerido = 'geografica' if 'geograf' in col_name else 'tematica'
            existente = DominioDesagregacion.objects.filter(nombre__iexact=nombre_dominio).first()
            dominios_detectados.append({
                'columna': col_name,
                'nombre_dominio': nombre_dominio,
                'tipo_sugerido': tipo_sugerido,
                'existe': existente is not None,
                'dominio_id': existente.id if existente else None,
                'dominio_nombre_bd': existente.nombre if existente else None,
            })
    else:
        col_fecha = None
        col_valor = None

    # --- Procesar cada indicador detectado ---
    indicadores_resultado = []
    indicadores_no_encontrados = []
    cargas_creadas = 0

    for codigo in codigos:
        try:
            indicador = Indicador.objects.filter(codigo_indicador=codigo).first()

            if not indicador:
                indicadores_no_encontrados.append(codigo)
                advertencias.append(f'Indicador "{codigo}" NO existe en el sistema. No se podrá procesar.')
                continue

            info = {'codigo': codigo, 'nombre': indicador.nombre, 'id': indicador.id}

            # Procesar metadata (si aplica)
            if df_metadata is not None and col_codigo_metadata:
                fila_meta = df_metadata[df_metadata[col_codigo_metadata] == codigo]
                if not fila_meta.empty:
                    _actualizar_metadata_indicador_masiva(indicador, fila_meta.iloc[0])
                    info['metadata_actualizada'] = True

            # Crear carga individual para que el admin la procese vía wizard
            if df_datos is not None and col_codigo_datos:
                grupo_df = df_datos[df_datos[col_codigo_datos] == codigo]
                if not grupo_df.empty:
                    carga_individual = _crear_carga_individual(carga_masiva, indicador, grupo_df)
                    if carga_individual:
                        info['carga_id'] = carga_individual.id
                        info['registros'] = len(grupo_df)
                        info['codigo_evidencia'] = carga_individual.codigo_evidencia
                        carga_masiva.cargas_series.add(carga_individual)
                        cargas_creadas += 1
                    else:
                        errores_acumulados.append(
                            f'Indicador "{codigo}": datos detectados pero no se pudo crear la carga individual.'
                        )

            carga_masiva.indicadores_afectados.add(indicador)
            indicadores_resultado.append(info)

        except Exception as e:
            errores_acumulados.append(f'Error procesando indicador "{codigo}": {str(e)}')

    if not indicadores_resultado and not indicadores_no_encontrados:
        return {'error': ' ; '.join(errores_acumulados) if errores_acumulados else 'No se detectaron indicadores válidos.'}

    carga_masiva.resumen_json = {
        'indicadores_detectados': len(indicadores_resultado),
        'indicadores_no_encontrados': indicadores_no_encontrados,
        'tareas_creadas': cargas_creadas,
        'col_fecha': col_fecha,
        'col_valor': col_valor,
        'dominios_detectados': dominios_detectados,
        'advertencias': advertencias,
        'errores': errores_acumulados,
        'detalle': indicadores_resultado,
    }
    carga_masiva.log_procesamiento = (
        f"Parseados {len(indicadores_resultado)} indicadores válidos. "
        f"No encontrados: {len(indicadores_no_encontrados)}. "
        f"Tareas individuales: {cargas_creadas}. "
        f"Dominios detectados: {len(dominios_detectados)}. "
        f"Advertencias: {len(advertencias)}."
    )
    carga_masiva.fecha_procesamiento = timezone.now()
    carga_masiva.save()

    return {
        'indicadores': indicadores_resultado,
        'indicadores_no_encontrados': indicadores_no_encontrados,
        'dominios_detectados': dominios_detectados,
        'advertencias': advertencias,
        'errores': errores_acumulados,
    }


def _resolver_subtema_desde_texto(nombre_subtema, nombre_tema=None, nombre_dominio=None):
    """Resuelve Dominio/Tema/Subtema de la plantilla oficial al MenuSubtema.

    Busca exacto (acotado por tema/dominio si vienen), luego por nombre
    normalizado (sin tildes/case) y por último icontains. Devuelve None
    si no hay coincidencia.
    """
    from .models import MenuSubtema

    nombre_subtema = str(nombre_subtema or '').strip()
    if not nombre_subtema:
        return None
    sub_qs = MenuSubtema.objects.filter(activo=True)
    nombre_tema = str(nombre_tema or '').strip()
    nombre_dominio = str(nombre_dominio or '').strip()
    if nombre_tema:
        sub_qs = sub_qs.filter(tema__nombre__iexact=nombre_tema)
    if nombre_dominio:
        sub_qs = sub_qs.filter(tema__dominio__nombre__iexact=nombre_dominio)
    subtema = sub_qs.filter(nombre__iexact=nombre_subtema).first()
    if not subtema:
        for s in MenuSubtema.objects.filter(activo=True):
            if _normalizar_nombre(s.nombre) == _normalizar_nombre(nombre_subtema):
                subtema = s
                break
    if not subtema:
        subtema = MenuSubtema.objects.filter(
            activo=True, nombre__icontains=nombre_subtema).first()
    return subtema


def _actualizar_metadata_indicador_masiva(indicador, fila):
    """
    Actualiza los campos de metadata de un indicador a partir de una fila del DataFrame.
    Usa el estándar MSD del DANE. Solo actualiza campos que existan en el DataFrame
    y tengan valor no vacío.
    """
    # ------------------------------------------------------------------
    # Mapeo MSD: columna del archivo → campo del modelo Indicador
    # ------------------------------------------------------------------
    campos_texto = {
        # Identificación básica
        'nombre_indicador': 'nombre',
        'sigla': 'sigla',
        'grupo_indicador': 'grupo_indicador',
        # Sección 2
        'descripcion_indicador': 'descripcion_indicador',
        'objetivo': 'objetivo',
        'metodo_medicion': 'metodo_medicion',
        'formula': 'formula_ficha',
        'variables': 'variables',
        'unidad_medida': 'unidad_medida',
        'nombre_conjunto_datos': 'nombre_conjunto_datos',
        'nomenclaturas_clasificaciones': 'nomenclaturas_clasificaciones',
        'alcance_tematico': 'alcance_tematico',
        'poblacion_objetivo': 'poblacion_objetivo',
        'cobertura_geografica': 'cobertura_geografica',
        'periodo_referencia': 'periodo_referencia',
        'periodo_base': 'periodo_base',
        'periodicidad': 'frecuencia_difusion',   # alias legacy → MSD 3.2
        'fuente_datos': 'fuente_datos',
        'responsable': 'entidad_responsable',    # alias legacy → MSD 1.1
        'entidad_responsable': 'entidad_responsable',  # texto → property resuelve Organismo
        # Sección 3
        'serie_historica_disponible': 'serie_historica_disponible',
        'frecuencia_difusion': 'frecuencia_difusion',
        'medios_difusion': 'medios_difusion',
        # Sección 4
        'comentarios_adicionales': 'comentarios_adicionales',
        # Sección 5 — Referencias
        'referencias': 'referencias',
        # Sección 6 — Responsables de validación
        'nombre_responsable_validacion': 'nombre_responsable_validacion',
        'cargo_responsable_validacion': 'cargo_responsable_validacion',
        'correo_responsable_validacion': 'correo_responsable_validacion',
        'celular_responsable_validacion': 'celular_responsable_validacion',
        # Contacto
        'correo_contacto': 'correo_contacto',
        'telefono_contacto': 'telefono_contacto',
    }

    for col_archivo, campo_modelo in campos_texto.items():
        if col_archivo in fila.index:
            valor = fila[col_archivo]
            if pd.notna(valor) and str(valor).strip() != '':
                setattr(indicador, campo_modelo, str(valor).strip())

    # ------------------------------------------------------------------
    # Fechas (MSD + técnicas)
    # ------------------------------------------------------------------
    for col_archivo, campo_modelo in [
        ('fecha_elaboracion', 'fecha_elaboracion'),
        ('fecha_actualizacion', 'fecha_actualizacion_ficha'),
        ('fecha_publicacion_metadatos', 'fecha_publicacion_metadatos'),
    ]:
        if col_archivo in fila.index:
            valor = fila[col_archivo]
            if pd.notna(valor):
                try:
                    from datetime import date
                    if isinstance(valor, (datetime, date)):
                        setattr(indicador, campo_modelo, valor)
                    else:
                        setattr(indicador, campo_modelo, pd.to_datetime(valor).date())
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Organismo / Suborganismo: coincidencia semántica por nombre
    # ------------------------------------------------------------------
    from .models import normalizar_ascii

    def _normalizar_nombre(n):
        return normalizar_ascii(str(n).lower().strip())

    # Entidad/Institución → Organismo
    nombre_organismo = None
    for col_posible in ('entidad_institucion', 'organismo_responsable', 'entidad'):
        if col_posible in fila.index and pd.notna(fila[col_posible]):
            nombre_organismo = str(fila[col_posible]).strip()
            break

    if nombre_organismo:
        organismo = None
        organismo_qs = Organismo.objects.filter(activo=True)
        # 1) Coincidencia exacta
        organismo = organismo_qs.filter(nombre__iexact=nombre_organismo).first()
        # 2) Coincidencia normalizada
        if not organismo:
            for org in organismo_qs:
                if _normalizar_nombre(org.nombre) == _normalizar_nombre(nombre_organismo):
                    organismo = org
                    break
        # 3) Contiene (matching parcial)
        if not organismo:
            organismo = organismo_qs.filter(nombre__icontains=nombre_organismo).first()
        if organismo:
            indicador.organismo_responsable = organismo

            # Área o Dependencia → Suborganismo (dentro del organismo encontrado)
            nombre_sub = None
            for col_sub in ('area_dependencia', 'suborganismo', 'area', 'dependencia'):
                if col_sub in fila.index and pd.notna(fila[col_sub]):
                    nombre_sub = str(fila[col_sub]).strip()
                    break

            if nombre_sub:
                suborganismo = None
                sub_qs = Suborganismo.objects.filter(organismo=organismo, activo=True)
                # 1) Exacta
                suborganismo = sub_qs.filter(nombre__iexact=nombre_sub).first()
                # 2) Normalizada
                if not suborganismo:
                    for sub in sub_qs:
                        if _normalizar_nombre(sub.nombre) == _normalizar_nombre(nombre_sub):
                            suborganismo = sub
                            break
                # 3) Contiene
                if not suborganismo:
                    suborganismo = sub_qs.filter(nombre__icontains=nombre_sub).first()
                if suborganismo:
                    indicador.suborganismo = suborganismo

    # ------------------------------------------------------------------
    # Operación Estadística (2.9 MSD): FK por nombre
    # ------------------------------------------------------------------
    nombre_operacion = None
    for col_op in ('operacion', 'operacion_estadistica'):
        if col_op in fila.index and pd.notna(fila[col_op]):
            nombre_operacion = str(fila[col_op]).strip()
            break

    if nombre_operacion:
        operacion = None
        op_qs = OperacionEstadistica.objects.all()
        operacion = op_qs.filter(nombre__iexact=nombre_operacion).first()
        if not operacion:
            for op in op_qs:
                if _normalizar_nombre(op.nombre) == _normalizar_nombre(nombre_operacion):
                    operacion = op
                    break
        if not operacion:
            operacion = op_qs.filter(nombre__icontains=nombre_operacion).first()
        if operacion:
            indicador.operacion = operacion

    # ------------------------------------------------------------------
    # Equipo Responsable (6.3 MSD): FK por nombre
    # ------------------------------------------------------------------
    nombre_equipo = None
    for col_eq in ('equipo_responsable', 'equipo'):
        if col_eq in fila.index and pd.notna(fila[col_eq]):
            nombre_equipo = str(fila[col_eq]).strip()
            break

    if nombre_equipo:
        eq_qs = EquipoOrganismo.objects.filter(activo=True)
        # Acotar al suborganismo/organismo ya resuelto si existe
        if indicador.suborganismo_id:
            eq_qs = eq_qs.filter(suborganismo=indicador.suborganismo)
        elif indicador.organismo_responsable_id:
            eq_qs = eq_qs.filter(suborganismo__organismo=indicador.organismo_responsable)
        equipo = eq_qs.filter(nombre__iexact=nombre_equipo).first()
        if not equipo:
            for eq in eq_qs:
                if _normalizar_nombre(eq.nombre) == _normalizar_nombre(nombre_equipo):
                    equipo = eq
                    break
        if equipo:
            indicador.equipo_responsable = equipo

    # ------------------------------------------------------------------
    # Columnas legacy de la plantilla vieja (sin campo MSD): van a notas
    # ------------------------------------------------------------------
    notas_extras = []
    for col_legacy, etiqueta in (('linea_base', 'Línea base'),
                                 ('valores_referencia', 'Valores de referencia')):
        if col_legacy in fila.index and pd.notna(fila[col_legacy]):
            valor = str(fila[col_legacy]).strip()
            if valor:
                notas_extras.append(f'{etiqueta}: {valor}')
    if notas_extras:
        notas_actuales = (indicador.notas or '').strip()
        agregado = ' | '.join(notas_extras)
        indicador.notas = f'{notas_actuales}\n{agregado}'.strip() if notas_actuales else agregado

    # ------------------------------------------------------------------
    # Taxonomía SIIED (plantilla oficial): Dominio / Tema / Subtema
    # ------------------------------------------------------------------
    subtema = _resolver_subtema_desde_texto(
        fila.get('subtema'), fila.get('tema'), fila.get('dominio'))
    if subtema:
        indicador.subtema = subtema

    indicador.save()

    # Si el archivo traía columna variables, sincronizar conjunto_datos y sus variables
    if 'variables' in fila.index and pd.notna(fila.get('variables')):
        _crear_o_actualizar_conjunto_datos_desde_variables(indicador)


def _crear_o_actualizar_conjunto_datos_desde_variables(indicador):
    """
    A partir del campo 'variables' del indicador, crea o actualiza el objeto
    conjunto_datos asociado y sus VariableConjuntoDatos.
    Si el indicador tiene 'nombre_conjunto_datos', se usa para buscar o
    crear la conjunto_datos, permitiendo que varios indicadores compartan la misma.
    Se asume que las variables están separadas por comas.
    """
    from django.utils.html import strip_tags
    from .models import ConjuntoDatos, VariableConjuntoDatos

    texto_variables = indicador.variables
    if not texto_variables:
        return

    # Limpiar HTML si viene de CKEditor
    texto_limpio = strip_tags(str(texto_variables)).strip()
    if not texto_limpio:
        return

    # Determinar nombre del conjunto de datos
    nombre_conjunto = (
        indicador.nombre_conjunto_datos.strip()
        if indicador.nombre_conjunto_datos
        else None
    )

    # Crear o reutilizar conjunto_datos
    conjunto_datos = indicador.conjunto_datos
    if not conjunto_datos:
        if nombre_conjunto:
            # Buscar conjunto_datos existente con el mismo nombre
            conjunto_datos_existente = ConjuntoDatos.objects.filter(nombre=nombre_conjunto).first()
            if conjunto_datos_existente:
                conjunto_datos = conjunto_datos_existente
            else:
                conjunto_datos = ConjuntoDatos.objects.create(
                    nombre=nombre_conjunto,
                    descripcion=(
                        f"conjunto_datos generada automáticamente desde metadata del indicador "
                        f"{indicador.codigo_indicador or indicador.nombre}"
                    ),
                )
        else:
            # Fallback: nombre por defecto
            conjunto_datos = ConjuntoDatos.objects.create(
                nombre=f"conjunto de datos - {indicador.nombre}",
                descripcion=(
                    f"conjunto_datos generada automáticamente desde metadata del indicador "
                    f"{indicador.codigo_indicador or indicador.nombre}"
                ),
            )
        indicador.conjunto_datos = conjunto_datos
        indicador.save(update_fields=['conjunto_datos'])

    # Parsear nombres de variables (separadas por comas)
    nombres = [v.strip() for v in texto_limpio.split(',') if v.strip()]

    # Crear/actualizar variables
    codigos_existentes = set()
    for i, nombre in enumerate(nombres, start=1):
        codigo = f"V{i}"
        VariableConjuntoDatos.objects.update_or_create(
            conjunto_datos=conjunto_datos,
            codigo_variable=codigo,
            defaults={
                'nombre_variable': nombre,
                'definicion_conceptual': f"Variable {nombre} del indicador {indicador.nombre}",
                'orden': i,
            }
        )
        codigos_existentes.add(codigo)

    # Eliminar variables que ya no están en la lista
    VariableConjuntoDatos.objects.filter(conjunto_datos=conjunto_datos).exclude(
        codigo_variable__in=codigos_existentes
    ).delete()


def _crear_carga_individual(carga_masiva, indicador, grupo_df):
    """
    Crea un CargaSerieIndicador individual a partir de un grupo de filas de datos.
    Genera el CSV de datos y lo asocia a la carga.
    Retorna la instancia creada o None si falla.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        with transaction.atomic():
            # Crear registro de carga
            carga = CargaSerieIndicador(
                usuario=carga_masiva.usuario,
                indicador=indicador,
                estado='pendiente',
                es_carga_delegado=False,
            )
            carga.save()

            # Generar CSV en memoria
            csv_buffer = BytesIO()
            grupo_df.to_csv(csv_buffer, index=False, encoding='utf-8')
            csv_buffer.seek(0)

            # Guardar CSV
            csv_filename = f"datos_masiva_{carga.codigo_evidencia}.csv"
            carga.archivo_datos_csv.save(csv_filename, ContentFile(csv_buffer.read()), save=False)

            # También generar xlsx para trazabilidad
            xlsx_buffer = BytesIO()
            with pd.ExcelWriter(xlsx_buffer, engine='openpyxl') as writer:
                grupo_df.to_excel(writer, index=False, sheet_name='Datos')
            xlsx_buffer.seek(0)
            xlsx_filename = f"datos_masiva_{carga.codigo_evidencia}.xlsx"
            carga.archivo_datos_xlsx.save(xlsx_filename, ContentFile(xlsx_buffer.read()), save=False)

            carga.registros_procesados = len(grupo_df)
            carga.registros_exitosos = len(grupo_df)
            carga.log_procesamiento = f"Creado desde carga masiva {carga_masiva.codigo_evidencia}. {len(grupo_df)} registros."
            carga.save()

        logger.info(
            f"[CARGA MASIVA] Carga individual creada exitosamente: "
            f"carga_id={carga.id}, indicador={indicador.codigo_indicador}, registros={len(grupo_df)}"
        )
        return carga
    except Exception as e:
        logger.error(f"[CARGA MASIVA] Error creando carga individual para {indicador.codigo_indicador}: {str(e)}")
        return None


# Columnas que NO son desagregaciones (identificación, fecha o valor)
_COLS_NO_DESAGREGACION = {
    'codigo_indicador', 'codigo', 'id_indicador', 'indicador_codigo',
    'nombre_indicador', 'nombre', 'sigla',
}
_COLS_FECHA = ('año', 'ano', 'anio', 'fecha', 'periodo', 'year', 'vigencia', 'fecha_dato')
_COLS_VALOR = ('valor', 'valor_dato', 'dato', 'value', 'cantidad')


def _detectar_columna(df_columns, candidatas):
    """Retorna la primera columna del df que coincida con alguna candidata."""
    for cand in candidatas:
        if cand in df_columns:
            return cand
    return None


def _importar_datos_serie_masiva(indicador, grupo_df):
    """
    DEPRECATED: Esta función ya no se usa en el flujo de carga masiva.
    La creación de datos, dominios y desagregaciones ahora se realiza
    exclusivamente en el wizard admin (wizard_admin_unificado.py → _procesar_flujo_b).
    Se mantiene por compatibilidad y referencia histórica.
    """
    raise NotImplementedError(
        "_importar_datos_serie_masiva está deprecada. "
        "La creación de datos se realiza en el wizard admin."
    )


@recolector_required
def revisar_masiva(request, carga_masiva_id):
    """
    Vista de informe de validación post-parseo.
    Muestra: indicadores detectados, dominios existentes/nuevos, advertencias.
    El recolector revisa y decide continuar a configurar gráficos o cancelar.
    """
    carga_masiva = get_object_or_404(CargaMasivaSerie, id=carga_masiva_id, usuario=request.user)

    if carga_masiva.estado not in ('validacion_recolector', 'despachada'):
        messages.error(request, 'Esta carga masiva no está en estado de revisión.')
        return redirect('indicadores:recoleccion_dashboard')

    resumen = carga_masiva.resumen_json or {}

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'cancelar':
            carga_masiva.estado = 'error'
            carga_masiva.mensaje_error = 'Cancelada por el recolector durante revisión.'
            carga_masiva.save()
            # Marcar cargas individuales como borrador
            carga_masiva.cargas_series.update(estado='borrador')
            messages.info(request, 'Carga masiva cancelada.')
            return redirect('indicadores:recoleccion_dashboard')
        elif accion == 'continuar':
            # Guardar clasificación de dominios elegida por el recolector
            dominios = resumen.get('dominios_detectados', [])
            for i, dom in enumerate(dominios):
                tipo_elegido = request.POST.get(f'tipo_dominio_{i}')
                if tipo_elegido in ('geografica', 'tematica'):
                    dom['tipo_sugerido'] = tipo_elegido
                padre_elegido = request.POST.get(f'padre_dominio_{i}', '')
                dom['padre_sugerido'] = padre_elegido or None
            resumen['dominios_detectados'] = dominios
            carga_masiva.resumen_json = resumen
            carga_masiva.save(update_fields=['resumen_json'])
            return redirect('indicadores:configurar_graficos_masiva', carga_masiva_id=carga_masiva.id)

    context = {
        'carga_masiva': carga_masiva,
        'resumen': resumen,
        'indicadores': resumen.get('detalle', []),
        'indicadores_no_encontrados': resumen.get('indicadores_no_encontrados', []),
        'dominios_detectados': resumen.get('dominios_detectados', []),
        'advertencias': resumen.get('advertencias', []),
        'errores': resumen.get('errores', []),
        'col_fecha': resumen.get('col_fecha'),
        'col_valor': resumen.get('col_valor'),
    }
    return render(request, 'recoleccion/revisar_masiva.html', context)


@recolector_required
def configurar_graficos_masiva(request, carga_masiva_id):
    """
    Vista para configurar las preferencias de gráficos por indicador.
    NO crea gráficos reales — solo guarda preferencias en CargaSerieIndicador.preferencias_grafico
    para que el admin las use como sugerencia al procesar en el wizard.
    """
    from .forms_recoleccion import GraficoMasivaForm

    carga_masiva = get_object_or_404(CargaMasivaSerie, id=carga_masiva_id, usuario=request.user)

    if carga_masiva.estado not in ('validacion_recolector', 'despachada'):
        messages.error(request, 'Esta carga masiva no está en estado de configuración.')
        return redirect('indicadores:recoleccion_dashboard')

    cargas_por_indicador = {}
    for carga in carga_masiva.cargas_series.select_related('indicador').all():
        if carga.indicador_id:
            cargas_por_indicador[carga.indicador_id] = carga

    indicadores_list = list(
        carga_masiva.indicadores_afectados.order_by('codigo_indicador')
    )

    if request.method == 'POST':
        forms_info_post = []
        todos_validos = True

        for indicador in indicadores_list:
            prefix = f"ind_{indicador.id}"
            form = GraficoMasivaForm(request.POST, prefix=prefix)
            if not form.is_valid():
                todos_validos = False
            forms_info_post.append({'indicador': indicador, 'form': form})

        if not todos_validos:
            messages.warning(request, 'Por favor corrija los errores en los formularios.')
            context = {
                'carga_masiva': carga_masiva,
                'forms_info': [{'indicador': i['indicador'], 'form': i['form']} for i in forms_info_post],
            }
            return render(request, 'recoleccion/configurar_graficos_masiva.html', context)

        # Guardar preferencias en cada CargaSerieIndicador (NO crear gráfico real)
        for item in forms_info_post:
            indicador = item['indicador']
            form = item['form']
            carga_ind = cargas_por_indicador.get(indicador.id)
            if carga_ind:
                carga_ind.preferencias_grafico = {
                    'tipo_grafico': form.cleaned_data['tipo_grafico'],
                    'titulo': form.cleaned_data['nombre'],
                    'eje_x': form.cleaned_data.get('eje_x_titulo') or 'Año',
                    'eje_y': form.cleaned_data.get('eje_y_titulo') or indicador.unidad_medida or '',
                }
                carga_ind.save(update_fields=['preferencias_grafico'])

        messages.success(request, 'Preferencias de gráfico guardadas. Revise el informe final.')
        return redirect('indicadores:confirmar_masiva', carga_masiva_id=carga_masiva.id)

    # GET: preparar formularios
    forms_info = []
    for indicador in indicadores_list:
        prefix = f"ind_{indicador.id}"
        carga_ind = cargas_por_indicador.get(indicador.id)
        prefs = (carga_ind.preferencias_grafico or {}) if carga_ind else {}
        initial = {
            'indicador_id': indicador.id,
            'nombre': prefs.get('titulo', indicador.nombre),
            'tipo_grafico': prefs.get('tipo_grafico', 'line'),
            'eje_x_titulo': prefs.get('eje_x', 'Año'),
            'eje_y_titulo': prefs.get('eje_y', indicador.unidad_medida or ''),
        }
        form = GraficoMasivaForm(prefix=prefix, initial=initial)
        forms_info.append({'indicador': indicador, 'form': form})

    context = {
        'carga_masiva': carga_masiva,
        'forms_info': forms_info,
    }
    return render(request, 'recoleccion/configurar_graficos_masiva.html', context)


@recolector_required
def confirmar_masiva(request, carga_masiva_id):
    """
    Vista de informe final y confirmación/cancelación.
    Muestra resumen completo. Al confirmar, despacha las cargas al admin.
    """
    from .notifications import notificar_admins_nueva_carga_recoleccion_serie

    carga_masiva = get_object_or_404(CargaMasivaSerie, id=carga_masiva_id, usuario=request.user)

    if carga_masiva.estado not in ('validacion_recolector',):
        messages.error(request, 'Esta carga masiva no está en estado de confirmación.')
        return redirect('indicadores:recoleccion_dashboard')

    resumen = carga_masiva.resumen_json or {}
    cargas_individuales = list(
        carga_masiva.cargas_series.select_related('indicador').order_by('indicador__codigo_indicador')
    )

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'cancelar':
            carga_masiva.estado = 'error'
            carga_masiva.mensaje_error = 'Cancelada por el recolector antes de enviar.'
            carga_masiva.save()
            carga_masiva.cargas_series.update(estado='borrador')
            messages.info(request, 'Carga masiva cancelada. Puede volver a subir el archivo.')
            return redirect('indicadores:cargar_masiva_series')

        elif accion == 'confirmar':
            # Despachar: marcar cargas individuales como 'pendiente' para el wizard
            carga_masiva.cargas_series.update(estado='pendiente')
            carga_masiva.estado = 'despachada'
            carga_masiva.save()

            # Notificar al admin en background (evita timeout por llamadas síncronas a API de Brevo)
            import threading
            def _notificar_async(cargas_list):
                from django.db import connections
                try:
                    for carga_ind in cargas_list:
                        try:
                            notificar_admins_nueva_carga_recoleccion_serie(carga_ind)
                        except Exception:
                            pass
                finally:
                    connections.close_all()

            hilo = threading.Thread(
                target=_notificar_async,
                args=(list(cargas_individuales),),
                daemon=True
            )
            hilo.start()

            messages.success(
                request,
                f"✅ {len(cargas_individuales)} tareas enviadas al administrador para procesamiento. "
                f"Recibirá notificaciones cuando sean procesadas."
            )
            return redirect('indicadores:historial_cargas_series')

    context = {
        'carga_masiva': carga_masiva,
        'resumen': resumen,
        'cargas_individuales': cargas_individuales,
        'dominios_detectados': resumen.get('dominios_detectados', []),
    }
    return render(request, 'recoleccion/confirmar_masiva.html', context)


def _crear_series_grafico_masiva(grafico, indicador):
    """
    DEPRECATED: La creación de series de gráfico ahora se realiza en el wizard admin.
    Se mantiene como stub por si algún código externo la referencia.
    """
    raise NotImplementedError(
        "_crear_series_grafico_masiva está deprecada. "
        "Las series de gráfico se crean en wizard_admin_unificado._crear_series_grafico."
    )


@recolector_required
def buscar_indicadores_masiva(request):
    """API para buscar indicadores disponibles en la carga masiva."""
    query = request.GET.get('q', '').strip()
    page = request.GET.get('page', 1)

    indicadores = Indicador.objects.filter(activo=True)
    if query:
        indicadores = indicadores.filter(
            Q(codigo_indicador__icontains=query) |
            Q(nombre__icontains=query)
        )

    indicadores = indicadores.order_by('codigo_indicador')
    paginator = Paginator(indicadores, 25)

    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    results = [
        {
            'codigo': indicador.codigo_indicador or '',
            'nombre': indicador.nombre,
        }
        for indicador in page_obj.object_list
    ]

    return JsonResponse({
        'results': results,
        'page': page_obj.number,
        'has_next': page_obj.has_next(),
        'total': paginator.count,
        'page_size': paginator.per_page,
        'query': query,
    })


@recolector_required
def descargar_catalogo_dominios(request):
    """Descarga un CSV con el catálogo completo de dominios y desagregaciones."""
    from .models import DominioDesagregacion

    dominios = (
        DominioDesagregacion.objects
        .order_by('tipo', '-en_catalogo', 'nombre')
        .prefetch_related('desagregaciones')
    )

    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="catalogo_dominios_{timestamp}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Tipo', 'Dominio', 'Desagregación', 'Estado'])

    for dominio in dominios:
        tipo = dominio.get_tipo_display()
        estado = 'catálogo' if dominio.en_catalogo else 'pendiente'
        desagregaciones = list(dominio.desagregaciones.all())
        if desagregaciones:
            for desagregacion in desagregaciones:
                writer.writerow([tipo, dominio.nombre, desagregacion.nombre, estado])
        else:
            writer.writerow([tipo, dominio.nombre, '', estado])

    return response


# ============================================================================
# PLANTILLAS DE CARGA MASIVA
# ============================================================================

def descargar_plantilla_masiva_datos(request):
    """Descarga plantilla Excel de ejemplo para carga masiva de datos de series"""
    try:
        data = {
            'codigo_indicador': ['ICET_SAL_DEM_MOR_02', 'ICET_SAL_DEM_MOR_02', 'ICET_EDU_TIE_ESC_01', 'ICET_EDU_TIE_ESC_01'],
            'nombre_indicador': [
                'Tasa de mortalidad de niños menores de 5 años',
                'Tasa de mortalidad de niños menores de 5 años',
                'Tasa neta de escolarización',
                'Tasa neta de escolarización'
            ],
            'año': [2022, 2023, 2022, 2023],
            'desagregacion_geografica': ['Comuna 1', 'Comuna 1', 'Comuna 2', 'Comuna 2'],
            'desagregacion_tematica_1': ['Hombre', 'Hombre', 'Mujer', 'Mujer'],
            'desagregacion_tematica_2': ['0-1 años', '0-1 años', '0-1 años', '0-1 años'],
            'valor': [10.89, 10.50, 95.2, 96.1]
        }
        df = pd.DataFrame(data)

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Datos')
            instrucciones = pd.DataFrame({
                'INSTRUCCIONES': [
                    '1. Este archivo contiene datos de MULTIPLES indicadores en un solo archivo.',
                    '2. Cada fila representa un dato de serie (un valor para un año y desagregación).',
                    '3. Columna obligatoria: codigo_indicador (en minúsculas).',
                    '4. Las filas se agrupan por codigo_indicador para generar un CSV por indicador.',
                    '5. Columnas de desagregación son opcionales si el indicador no las usa.',
                    '6. Use punto (.) como separador decimal.',
                    '',
                    'EJEMPLO: Si tiene 3 indicadores con datos de 2022-2023,',
                    'repita el codigo_indicador en cada fila correspondiente.',
                    '',
                    'IMPORTANTE: Todos los codigo_indicador deben existir en el sistema.'
                ]
            })
            instrucciones.to_excel(writer, index=False, sheet_name='Instrucciones')

        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="plantilla_masiva_datos.xlsx"'
        return response

    except Exception as e:
        messages.error(request, f'Error al generar la plantilla: {str(e)}')
        return redirect('indicadores:cargar_masiva_series')


def _servir_plantilla_oficial_metadatos(request, fallback_url):
    """Sirve verbatim la plantilla oficial de metadatos de indicadores
    (hojas: 'Diccionario de datos', 'Indicadores', 'Variables').

    Es el archivo aprobado por el equipo: mismo orden de columnas y
    nomenclatura. Todos los puntos de descarga (carga masiva, carga
    individual y portal delegado) sirven este mismo archivo.
    """
    import os
    from django.conf import settings
    from django.http import FileResponse

    ruta = os.path.join(
        settings.BASE_DIR, 'indicadores', 'plantillas',
        'plantilla_metadatos_indicadores.xlsx')
    try:
        return FileResponse(
            open(ruta, 'rb'),
            as_attachment=True,
            filename='plantilla_metadatos_indicadores.xlsx',
        )
    except FileNotFoundError:
        messages.error(request, 'La plantilla oficial no está instalada en el servidor.')
        return redirect(fallback_url)


def descargar_plantilla_masiva_metadata(request):
    """Descarga la plantilla oficial (botón de carga masiva)."""
    return _servir_plantilla_oficial_metadatos(
        request, 'indicadores:cargar_masiva_series')


def _descargar_plantilla_masiva_metadata_generada(request):
    """Generador histórico (deprecado): queda por si la plantilla
    oficial desaparece del servidor. Usa columnas del estándar viejo."""
    try:
        data = {
            'codigo_indicador': ['ICET_SAL_DEM_MOR_02', 'ICET_EDU_TIE_ESC_01'],
            # Identificación
            'nombre_indicador': [
                'Tasa de mortalidad de niños menores de 5 años',
                'Tasa neta de escolarización'
            ],
            'sigla': ['TMM5', 'TNE'],
            'grupo_indicador': ['ICET', 'ICET'],
            # 1. Contacto Institucional (MSD)
            'entidad_institucion': ['DAPD', 'Secretaría de Educación'],
            'area_dependencia': ['Subdirección de Salud', 'Oficina de Planeación'],
            'correo_contacto': ['salud@ejemplo.gov.co', 'educacion@ejemplo.gov.co'],
            'telefono_contacto': ['601-1234567', '601-7654321'],
            'fecha_publicacion_metadatos': ['2025-09-16', '2025-09-16'],
            # 2. Características del Indicador (MSD)
            'descripcion_indicador': ['Cuantifica la relación de las muertes...', 'Mide la cobertura del sistema educativo...'],
            'objetivo': ['Evaluar salud infantil', 'Evaluar cobertura educativa'],
            'metodo_medicion': ['Registros civiles', 'Censo educativo'],
            'formula': ['TMM5 = (V₁ / V₂) × 1.000', 'TNE = (Matriculados / Población en edad escolar) × 100'],
            'variables': ['V₁: Defunciones menores 5; V₂: Nacidos vivos', 'Matriculados: total inscritos'],
            'unidad_medida': ['Muertes por 1.000 nacidos vivos', 'Porcentaje (%)'],
            'nomenclaturas_clasificaciones': ['CIE-10', 'Clasificación ISCED'],
            'alcance_tematico': ['Grupo de edad, Sexo', 'Nivel educativo'],
            'poblacion_objetivo': ['Población menor de 5 años', 'Población en edad escolar'],
            'cobertura_geografica': ['Distrital', 'Distrital'],
            'periodo_referencia': ['Año calendario', 'Año académico'],
            'periodo_base': ['2018 = 100', '2015 = 100'],
            # 3. Difusión (MSD)
            'serie_historica_disponible': ['2010-2024', '2015-2024'],
            'frecuencia_difusion': ['Anual', 'Anual'],
            'medios_difusion': ['Página web, boletín', 'Página web, informe anual'],
            # Operación y conjunto_datos
            'operacion_estadistica': ['Encuesta Nacional de Calidad de Vida', 'Censo Escolar'],
            'nombre_conjunto_datos': ['Registros de mortalidad infantil', 'Matrícula escolar'],
            # 5. Referencias (MSD)
            'referencias': ['DANE (2024). Metodología TMM5', 'MEN (2024). Boletín educativo'],
            # 6. Responsabilidad institucional (MSD)
            'equipo_responsable': ['Equipo de Estadísticas de Salud', 'Equipo de Estadísticas Educativas'],
            'nombre_responsable_validacion': ['Juan Pérez', 'María Gómez'],
            'cargo_responsable_validacion': ['Profesional especializado', 'Profesional especializado'],
            'correo_responsable_validacion': ['jperez@ejemplo.gov.co', 'mgomez@ejemplo.gov.co'],
            'celular_responsable_validacion': ['3101234567', '3117654321'],
            # Administrativos
            'fuente_datos': ['DANE', 'Secretaría de Educación'],
            'entidad_responsable': ['Departamento Administrativo de Planeación', 'Secretaría de Educación'],
            'comentarios_adicionales': ['Considerar subregistro...', 'Incluir educación formal...'],
            'notas': ['Actualización anual', 'Corte a 31 de diciembre'],
            'fecha_elaboracion': ['2025-01-15', '2025-01-15'],
            'fecha_actualizacion': ['2025-09-16', '2025-09-16'],
        }
        df = pd.DataFrame(data)

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Metadata')
            instrucciones = pd.DataFrame({
                'INSTRUCCIONES': [
                    '1. Este archivo actualiza la metadata de MULTIPLES indicadores.',
                    '2. Cada fila representa UN indicador.',
                    '3. Columna obligatoria: codigo_indicador (en minúsculas).',
                    '4. Solo se actualizan los campos que tengan valor no vacío.',
                    '5. Use el formato de fecha YYYY-MM-DD para las fechas.',
                    '',
                    'CAMPOS MSD — SECCION 1: CONTACTO INSTITUCIONAL',
                    'entidad_institucion   → nombre exacto del Organismo existente en el sistema',
                    'area_dependencia      → nombre exacto del Suborganismo del organismo elegido',
                    'correo_contacto, telefono_contacto, fecha_publicacion_metadatos',
                    '',
                    'CAMPOS MSD — SECCION 2: CARACTERISTICAS DEL INDICADOR',
                    'descripcion_indicador, objetivo, metodo_medicion, formula,',
                    'variables, unidad_medida, nomenclaturas_clasificaciones,',
                    'alcance_tematico, poblacion_objetivo, cobertura_geografica,',
                    'periodo_referencia, periodo_base',
                    '',
                    'CAMPOS MSD — SECCION 3: DIFUSION',
                    'serie_historica_disponible, frecuencia_difusion, medios_difusion',
                    '',
                    'CAMPOS MSD — SECCION 4: COMENTARIOS',
                    'comentarios_adicionales',
                    '',
                    'CAMPOS MSD — SECCION 5: REFERENCIAS',
                    'referencias',
                    '',
                    'CAMPOS MSD — SECCION 6: RESPONSABILIDAD',
                    'equipo_responsable, nombre_responsable_validacion,',
                    'cargo_responsable_validacion, correo_responsable_validacion,',
                    'celular_responsable_validacion',
                    '',
                    'OPERACION Y CONJUNTO DE DATOS',
                    'operacion_estadistica  → nombre exacto de la Operación Estadística',
                    'nombre_conjunto_datos  → nombre del conjunto de datos del indicador',
                    '',
                    'CAMPOS ADMINISTRATIVOS (compatibilidad)',
                    'fuente_datos, notas, fecha_elaboracion, fecha_actualizacion',
                    'entidad_responsable → texto legado; prefiera entidad_institucion',
                    '',
                    'IMPORTANTE: El indicador y el Organismo/Suborganismo deben existir previamente.'
                ]
            })
            instrucciones.to_excel(writer, index=False, sheet_name='Instrucciones')

        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="plantilla_masiva_metadata.xlsx"'
        return response

    except Exception as e:
        messages.error(request, f'Error al generar la plantilla: {str(e)}')
        return redirect('indicadores:cargar_masiva_series')


# ============================================================================
# HERRAMIENTA: DECONSTRUIR TABLA DINÁMICA (pivot → formato plano requerido)
# ============================================================================

def _dt_read_raw(file_obj, sheet_name=0):
    """Lee un archivo Excel o CSV crudo sin header."""
    name = file_obj.name.lower() if hasattr(file_obj, 'name') else ''
    if name.endswith('.csv'):
        file_obj.seek(0)
        content = file_obj.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')
        best_df, best_cols = None, 0
        for sep in (',', ';', '\t'):
            try:
                df = pd.read_csv(pd.io.common.StringIO(content), sep=sep, header=None, dtype=str)
                if len(df.columns) > best_cols:
                    best_df, best_cols = df, len(df.columns)
            except Exception:
                pass
        return best_df if best_df is not None else pd.read_csv(pd.io.common.StringIO(content), header=None, dtype=str)
    else:
        ext = name.split('.')[-1] if name else 'xlsx'
        engine = 'xlrd' if ext == 'xls' else 'openpyxl'
        file_obj.seek(0)
        return pd.read_excel(file_obj, sheet_name=sheet_name, header=None, engine=engine)


def _dt_find_header_row(df):
    """
    Encuentra la fila de encabezado descartando posibles filas de título
    al inicio. Busca la primera fila con ≥N celdas no-vacías donde N es
    al menos el 60% del máximo observado en todo el DataFrame.
    """
    non_empty = df.notna().sum(axis=1)
    max_nonempty = non_empty.max()
    if max_nonempty == 0:
        return 0
    threshold = max(2, int(max_nonempty * 0.6))
    candidates = non_empty[non_empty >= threshold]
    if candidates.empty:
        return int(non_empty.idxmax())
    return int(candidates.index[0])


def _dt_is_year_header(val):
    """Heurística: ¿parece un año?"""
    if pd.isna(val):
        return False
    s = str(val).strip()
    try:
        n = int(float(s))
        return 1900 <= n <= 2100
    except (ValueError, TypeError):
        return False


def _dt_build_col_names(raw_header):
    """Convierte fila de encabezado en nombres de columna limpios."""
    cols, seen = [], {}
    for i, val in enumerate(raw_header):
        if pd.isna(val) or str(val).strip() in ('', 'nan'):
            name = f'_empty_{i}'
        else:
            try:
                name = str(int(float(val)))
            except (ValueError, TypeError):
                name = str(val).strip()
        if name in seen:
            seen[name] += 1
            name = f'{name}_{seen[name]}'
        else:
            seen[name] = 0
        cols.append(name)
    return cols


def _dt_row_is_empty(row):
    """Considera vacía si la primera celda está vacía Y ≥80% de las celdas están vacías."""
    first = row.iloc[0]
    first_empty = pd.isna(first) or str(first).strip() in ('', 'nan')
    if not first_empty:
        return False
    pct_empty = row.isna().sum() / len(row)
    return pct_empty >= 0.8


def _dt_split_groups(df, header_idx):
    """Separa DataFrame en grupos por filas vacías."""
    groups, current = [], []
    for idx, row in df.iloc[header_idx + 1:].iterrows():
        if _dt_row_is_empty(row):
            if current:
                groups.append(df.loc[current])
                current = []
        else:
            current.append(idx)
    if current:
        groups.append(df.loc[current])
    return groups


def _dt_clean_val(v):
    if pd.isna(v):
        return ''
    s = str(v).strip() if isinstance(v, str) else v
    if isinstance(s, str) and s in ('-', '--', '...', 'N/A', 'n/a', 'N/D', 'n/d'):
        return ''
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, str):
        return v.strip()
    return v


def _dt_clean_numeric_val(v):
    """Limpia un valor numérico: maneja guiones como null, comas de miles, etc."""
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)) and not (isinstance(v, float) and v != v):
        return v
    s = str(v).strip()
    if s in ('', '-', '--', '...', 'N/A', 'n/a', 'N/D', 'n/d', 'nan', 'NaN'):
        return None
    # Quitar separador de miles (coma dentro de comillas en CSV)
    s_clean = s.replace(',', '')
    try:
        f = float(s_clean)
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return None


def _dt_detect_double_header(df, header_idx):
    """
    Detecta si hay doble header (fila de años repetidos + fila de sub-categorías).
    Retorna (True, sub_header_idx) o (False, None).
    """
    row1 = df.iloc[header_idx]
    year_vals = [v for v in row1 if _dt_is_year_header(v)]
    if len(year_vals) < 4:
        return False, None
    unique_years = set(str(int(float(v))) for v in year_vals)
    # Si los años se repiten (muchos valores-año pero pocos únicos)
    if len(year_vals) <= len(unique_years) * 1.5:
        return False, None
    next_idx = header_idx + 1
    if next_idx >= len(df):
        return False, None
    row2 = df.iloc[next_idx]
    non_empty = [v for v in row2 if pd.notna(v) and str(v).strip() not in ('', 'nan')]
    non_year = [v for v in non_empty if not _dt_is_year_header(v)]
    if len(non_year) >= 2:
        return True, next_idx
    return False, None


def _dt_prepare_crossed_melted(df, header_idx, sub_header_idx, parent_name, child_name, header2_name=None):
    """
    Procesa una tabla con doble header (desagregación cruzada).
    Extrae 3 dominios de desagregación:
      1. header2_name: dominio del segundo header (ej: Tipo_Servicio)
      2. child_name:   dominio de la primera columna - valores hoja (ej: Subclase_vehiculo)
      3. parent_name:  dominio formado por la primera fila de cada grupo (ej: Clase_vehiculo)
    
    Produce DataFrame con columnas: [Año, parent_name, child_name, header2_name, Valor].
    Solo conserva filas "hijas" (sub); las filas "padre" se usan como fill-down.
    Ignora columnas vacías separadoras y trata guiones como null.
    """
    years_row = df.iloc[header_idx]
    subs_row = df.iloc[sub_header_idx]

    # Si no se provee header2_name, se usa un nombre genérico
    if header2_name is None:
        header2_name = 'Categoria'

    # Construir mapeo: col_idx → (año, sub_categoría)
    col_map = {}
    for i in range(1, len(years_row)):
        year_val = years_row.iloc[i]
        sub_val = subs_row.iloc[i]
        if _dt_is_year_header(year_val) and pd.notna(sub_val) and str(sub_val).strip() not in ('', 'nan'):
            year_str = str(int(float(year_val)))
            sub_str = str(sub_val).strip()
            col_map[i] = (year_str, sub_str)

    if not col_map:
        return None

    # ── Clasificar filas de datos en "padre" (clase) y "sub" (hija) ──
    # Lógica: si la fila anterior está vacía (o es la primera fila de datos),
    # es un padre (clase). Si la anterior es no-vacía, es una hija (sub).
    data_start = sub_header_idx + 1

    def _is_empty_row(idx):
        row = df.iloc[idx]
        first = row.iloc[0]
        return pd.isna(first) or str(first).strip() in ('', 'nan')

    # Recolectar metadatos por fila: tipo (padre/sub/vacía) + valor
    fila_info = []  # [(idx, tipo, valor_col_a)]
    for idx in range(data_start, len(df)):
        if _is_empty_row(idx):
            fila_info.append((idx, 'vacia', ''))
        else:
            val_a = str(df.iloc[idx, 0]).strip()
            # Es padre si la fila anterior es vacía o es la primera de datos
            if not fila_info or fila_info[-1][1] == 'vacia':
                fila_info.append((idx, 'padre', val_a))
            else:
                fila_info.append((idx, 'sub', val_a))

    # Fill-down del padre: para cada fila sub, el padre es el último padre visto
    rows = []
    current_parent = ''
    for (idx, tipo, val_a) in fila_info:
        if tipo == 'padre':
            current_parent = val_a
            # No incluir la fila padre en el resultado final (solo sirve de agrupador)
            # Excepto si no tiene hijos (grupo de una sola fila) → se incluye
            continue
        elif tipo == 'vacia':
            continue
        # tipo == 'sub'
        data_row = df.iloc[idx]
        for col_idx, (year_str, sub_str) in col_map.items():
            if col_idx >= len(data_row):
                continue
            raw_val = data_row.iloc[col_idx]
            clean = _dt_clean_numeric_val(raw_val)
            if clean is None:
                continue
            rows.append({
                'Año': year_str,
                parent_name: current_parent,
                child_name: val_a,
                header2_name: sub_str,
                'Valor': clean,
            })

    # Si no hubo subs (todas eran padres aislados), incluir padres directamente
    if not rows:
        current_parent = ''
        for (idx, tipo, val_a) in fila_info:
            if tipo != 'padre':
                continue
            data_row = df.iloc[idx]
            for col_idx, (year_str, sub_str) in col_map.items():
                if col_idx >= len(data_row):
                    continue
                raw_val = data_row.iloc[col_idx]
                clean = _dt_clean_numeric_val(raw_val)
                if clean is None:
                    continue
                rows.append({
                    'Año': year_str,
                    parent_name: val_a,
                    child_name: val_a,
                    header2_name: sub_str,
                    'Valor': clean,
                })

    if not rows:
        return None
    result = pd.DataFrame(rows)
    return result[['Año', parent_name, child_name, header2_name, 'Valor']]


def _dt_sanitize_name(raw):
    import re
    s = re.sub(r'[^\w\s\-]', '', str(raw).strip(), flags=re.UNICODE)
    return re.sub(r'\s+', '_', s).strip('_')


def _dt_detect_year_columns(col_names):
    """Devuelve índices de columnas cuyo nombre parece año."""
    return [i for i, c in enumerate(col_names) if _dt_is_year_header(c)]


def _dt_prepare_block_melted(group, col_names, group_name):
    """
    Prepara un bloque de datos: limpia valores, detecta columnas-año,
    hace melt a formato largo (Año, Valor) y renombra la columna
    descriptora con el nombre del grupo.
    """
    df = group.copy().reset_index(drop=True)
    n = len(df.columns)
    names = col_names[:n] + [f'_extra_{i}' for i in range(len(col_names), n)]
    df.columns = names
    df = df.apply(lambda col: col.map(_dt_clean_val))

    # Quitar columnas auxiliares vacías
    aux_cols = [c for c in df.columns if c.startswith('_empty_') or c.startswith('_extra_')]
    empty_aux = [c for c in aux_cols if df[c].replace('', pd.NA).isna().all()]
    if empty_aux:
        df = df.drop(columns=empty_aux)

    real_cols = [c for c in df.columns if not c.startswith('_')]
    if not real_cols:
        return None

    # Primera columna = descriptor (ej: AÑO, CATEGORIA, etc.)
    desc_col = real_cols[0]
    potential_years = real_cols[1:]
    year_cols = [c for c in potential_years if _dt_is_year_header(c)]

    if not year_cols:
        # Sin columnas-año: no es un formato pivot reconocible
        return None

    # Melt de ancho → largo
    melted = df.melt(
        id_vars=[desc_col],
        value_vars=year_cols,
        var_name='Año',
        value_name='Valor'
    )

    # Limpiar columna Año
    melted['Año'] = melted['Año'].apply(
        lambda x: str(int(float(x))) if pd.notna(x) and str(x).strip() not in ('', 'nan') else ''
    )

    # Quitar filas sin valor
    melted = melted[melted['Valor'].astype(str).str.strip() != '']

    # Renombrar columna descriptora con el nombre del grupo (ej: Zona_Geografica)
    melted = melted.rename(columns={desc_col: group_name})

    return melted


def _dt_analyze_sheet(file_obj, sheet_name=0):
    """Analiza una hoja y retorna info sobre los grupos detectados."""
    try:
        raw = _dt_read_raw(file_obj, sheet_name)
    except Exception as e:
        return {'error': f'Error leyendo hoja: {str(e)}'}

    if raw.empty:
        return {'error': 'La hoja está vacía.'}

    header_idx = _dt_find_header_row(raw)

    # Verificar doble header (desagregación cruzada)
    is_double, sub_header_idx = _dt_detect_double_header(raw, header_idx)

    if is_double:
        years_row = raw.iloc[header_idx]
        subs_row = raw.iloc[sub_header_idx]

        # Valores únicos de sub-categoría (2do header) → Dominio 3
        sub_values = []
        for i in range(1, len(subs_row)):
            v = subs_row.iloc[i]
            if pd.notna(v) and str(v).strip() not in ('', 'nan'):
                sv = str(v).strip()
                if sv not in sub_values:
                    sub_values.append(sv)

        # Clasificar filas en padres e hijos para la primera columna
        data_start = sub_header_idx + 1
        parent_values = []  # Primeros de cada grupo → Dominio 1
        child_values = []   # Hijos (sub) → Dominio 2

        prev_empty = True  # Empieza como si hubiera fila vacía antes
        for idx in range(data_start, len(raw)):
            first = raw.iloc[idx, 0]
            is_empty = pd.isna(first) or str(first).strip() in ('', 'nan')
            if is_empty:
                prev_empty = True
                continue
            val = str(first).strip()
            if prev_empty:
                # Primera fila no-vacía tras vacía = padre
                if val not in parent_values:
                    parent_values.append(val)
                prev_empty = False
            else:
                # Fila continua = hijo
                if val not in child_values:
                    child_values.append(val)

        # Nombre sugerido de la primera columna (header de col A)
        col_a_header = ''
        first_cell = raw.iloc[header_idx, 0]
        if pd.notna(first_cell) and str(first_cell).strip() not in ('', 'nan'):
            col_a_header = str(first_cell).strip()

        # Años únicos
        year_values = sorted(set(
            str(int(float(v))) for v in years_row if _dt_is_year_header(v)
        ))

        # 3 grupos para nombrar:
        # 0 = dominio padre (formado por primeros de cada grupo)
        # 1 = dominio hijo (la primera columna, valores hoja)
        # 2 = dominio del segundo header
        groups_info = [
            {
                'index': 0,
                'num_variables': len(parent_values),
                'preview': parent_values[:5],
                'has_more': len(parent_values) > 5,
                'total': len(parent_values),
                'hint': 'Dominio padre (primeros de cada grupo)',
            },
            {
                'index': 1,
                'num_variables': len(child_values),
                'preview': child_values[:5],
                'has_more': len(child_values) > 5,
                'total': len(child_values),
                'hint': f'Dominio hijos (columna "{col_a_header}")' if col_a_header else 'Dominio hijos (primera columna)',
            },
            {
                'index': 2,
                'num_variables': len(sub_values),
                'preview': sub_values[:5],
                'has_more': len(sub_values) > 5,
                'total': len(sub_values),
                'hint': 'Dominio del segundo header',
            },
        ]

        return {
            'header_row': header_idx + 1,
            'columns': year_values,
            'num_groups': 3,
            'groups_info': groups_info,
            'col_names': [],
            'has_years': True,
            'year_indices': [],
            'is_crossed': True,
            'sub_header_row': sub_header_idx + 1,
            'sub_values': sub_values,
            'col_a_header': col_a_header,
        }

    # Modo estándar: header simple
    col_names = _dt_build_col_names(raw.iloc[header_idx])
    groups = _dt_split_groups(raw, header_idx)

    if not groups:
        return {'error': 'No se encontraron grupos de datos separados por filas vacías.'}

    visible_cols = [c for c in col_names if not c.startswith('_')]
    year_indices = _dt_detect_year_columns(col_names)
    has_years = len(year_indices) > 0

    groups_info = []
    for i, grp in enumerate(groups):
        variables = (grp.iloc[:, 0].dropna().astype(str).str.strip().tolist())
        groups_info.append({
            'index': i,
            'num_variables': len(variables),
            'preview': variables[:5],
            'has_more': len(variables) > 5,
            'total': len(variables),
        })

    return {
        'header_row': header_idx + 1,
        'columns': visible_cols,
        'num_groups': len(groups),
        'groups_info': groups_info,
        'col_names': col_names,
        'has_years': has_years,
        'year_indices': year_indices,
        'is_crossed': False,
    }


def _dt_process_sheet(file_obj, sheet_name, group_names,
                      codigo_indicador=None, nombre_indicador=None):
    """
    Procesa una hoja y retorna el DataFrame consolidado en formato plano
    compatible con el sistema de carga de series.

    Modo cruzado (doble header): produce Año + Desag1 + Desag2 + Desag3 + Valor.
    Modo estándar: cada grupo se convierte en una columna separada y
    las columnas-año se funden en 'Año' con 'Valor'.
    """
    raw = _dt_read_raw(file_obj, sheet_name)
    header_idx = _dt_find_header_row(raw)

    is_double, sub_header_idx = _dt_detect_double_header(raw, header_idx)

    if is_double:
        parent_name = group_names.get('0', 'Clase')
        child_name = group_names.get('1', 'Subclase')
        header2_name = group_names.get('2', 'Categoria')
        result = _dt_prepare_crossed_melted(
            raw, header_idx, sub_header_idx, parent_name, child_name, header2_name
        )
    else:
        col_names = _dt_build_col_names(raw.iloc[header_idx])
        groups = _dt_split_groups(raw, header_idx)

        blocks = []
        for i, grp in enumerate(groups):
            group_name = group_names.get(str(i), f'grupo_{i+1}')
            block = _dt_prepare_block_melted(grp, col_names, group_name)
            if block is not None and not block.empty:
                blocks.append(block)

        if not blocks:
            return None

        result = pd.concat(blocks, ignore_index=True)

        # Reordenar columnas: Año primero, luego grupos en orden, luego Valor
        all_cols = list(result.columns)
        group_cols = [c for c in all_cols if c not in ('Año', 'Valor')]

        ordered_groups = []
        for i in range(len(groups)):
            name = group_names.get(str(i), f'grupo_{i+1}')
            if name in group_cols:
                ordered_groups.append(name)
        for c in group_cols:
            if c not in ordered_groups:
                ordered_groups.append(c)

        result = result[['Año'] + ordered_groups + ['Valor']]

    if result is None or result.empty:
        return None

    # Añadir Codigo_Indicador y Nombre_Indicador si se proporcionan
    if codigo_indicador:
        result.insert(0, 'Codigo_Indicador', codigo_indicador)
    if nombre_indicador:
        result.insert(1, 'Nombre_Indicador', nombre_indicador)

    return result


@login_required(login_url='/recoleccion/login/')
def deconstruir_tabla(request):
    """
    Herramienta para deconstruir tablas dinámicas (pivot tables) al formato
    plano requerido por el sistema de carga de series.

    Modo 'individual':  procesa la primera hoja, genera archivo formateado.
    Modo 'masivo':      procesa cada hoja del Excel y ofrece descargas ZIP.
    """
    # Verificar permisos (recolector o delegado)
    tiene_permiso = (
        request.user.is_staff or
        (hasattr(request.user, 'perfil_recolector') and
         (request.user.perfil_recolector.puede_recolectar() or
          request.user.perfil_recolector.es_delegado()))
    )
    if not tiene_permiso:
        messages.error(request, 'No tiene permisos para usar esta herramienta.')
        return redirect('indicadores:acceso_modulos')

    from django.core.files.storage import default_storage
    import re
    import zipfile

    wizard_key = 'deconstruir_tabla_wizard'
    wizard_data = request.session.get(wizard_key, {})
    paso = wizard_data.get('paso', 1)
    modo = request.GET.get('modo', wizard_data.get('modo', 'individual'))
    indicador_id = request.GET.get('indicador_id', '')

    if request.method == 'GET' and 'reset' in request.GET:
        request.session.pop(wizard_key, None)
        return redirect('indicadores:deconstruir_tabla')

    if request.method == 'POST':
        action = request.POST.get('action', '')

        # ── PASO 1: Subir archivo ──────────────────────────────────────
        if action == 'upload':
            archivo = request.FILES.get('archivo')
            if not archivo:
                messages.error(request, 'Debe seleccionar un archivo.')
                return redirect('indicadores:deconstruir_tabla')

            ext = archivo.name.lower().split('.')[-1]
            if ext not in ('xlsx', 'xls', 'csv'):
                messages.error(request, 'Solo se aceptan archivos .xlsx, .xls o .csv')
                return redirect('indicadores:deconstruir_tabla')

            modo = request.POST.get('modo', 'individual')
            indicador_id = request.POST.get('indicador_id', '')

            tmp_name = f'tmp/deconstruir_{request.user.id}_{timezone.now().strftime("%Y%m%d%H%M%S")}.{ext}'
            saved_path = default_storage.save(tmp_name, archivo)

            try:
                if ext == 'csv':
                    sheet_names = ['Datos']
                else:
                    archivo.seek(0)
                    engine = 'xlrd' if ext == 'xls' else 'openpyxl'
                    xl = pd.ExcelFile(archivo, engine=engine)
                    sheet_names = xl.sheet_names
            except Exception as e:
                messages.error(request, f'Error leyendo el archivo: {str(e)}')
                default_storage.delete(saved_path)
                return redirect('indicadores:deconstruir_tabla')

            sheets_analysis = {}
            for sn in sheet_names:
                archivo.seek(0)
                analysis = _dt_analyze_sheet(archivo, sheet_name=sn)
                sheets_analysis[sn] = analysis

            if modo == 'individual':
                first_analysis = sheets_analysis.get(sheet_names[0], {})
                if first_analysis.get('error'):
                    messages.error(request, first_analysis['error'])
                    default_storage.delete(saved_path)
                    return redirect('indicadores:deconstruir_tabla')

            wizard_data = {
                'paso': 2,
                'modo': modo,
                'indicador_id': indicador_id,
                'archivo_path': saved_path,
                'archivo_nombre': archivo.name,
                'sheet_names': sheet_names,
                'sheets_analysis': sheets_analysis,
                'current_sheet_idx': 0,
                'sheets_group_names': {},
            }
            request.session[wizard_key] = wizard_data
            return redirect('indicadores:deconstruir_tabla')

        # ── PASO 2: Nombrar grupos ─────────────────────────────────────
        elif action == 'name_groups':
            sheets_group_names = wizard_data.get('sheets_group_names', {})

            if modo == 'individual':
                sheet_name = wizard_data['sheet_names'][0]
                analysis = wizard_data['sheets_analysis'].get(sheet_name, {})
                num_groups = analysis.get('num_groups', 0)
                group_names = {}
                for i in range(num_groups):
                    name = request.POST.get(f'group_{i}', '').strip()
                    if not name:
                        messages.error(request, f'Debe asignar un nombre al grupo {i+1}.')
                        return redirect('indicadores:deconstruir_tabla')
                    name = _dt_sanitize_name(name)
                    if not name:
                        messages.error(request, f'Nombre inválido para el grupo {i+1}.')
                        return redirect('indicadores:deconstruir_tabla')
                    group_names[str(i)] = name
                sheets_group_names[sheet_name] = group_names
            else:
                current_idx = wizard_data.get('current_sheet_idx', 0)
                sheet_names = wizard_data.get('sheet_names', [])
                if current_idx >= len(sheet_names):
                    wizard_data['paso'] = 3
                    request.session[wizard_key] = wizard_data
                    return redirect('indicadores:deconstruir_tabla')

                sheet_name = sheet_names[current_idx]
                analysis = wizard_data['sheets_analysis'].get(sheet_name, {})

                if analysis.get('error'):
                    sheets_group_names[sheet_name] = None
                else:
                    num_groups = analysis.get('num_groups', 0)
                    group_names = {}
                    for i in range(num_groups):
                        name = request.POST.get(f'group_{i}', '').strip()
                        if not name:
                            messages.error(
                                request,
                                f'Debe asignar un nombre al grupo {i+1} de la hoja "{sheet_name}".'
                            )
                            return redirect('indicadores:deconstruir_tabla')
                        name = _dt_sanitize_name(name)
                        if not name:
                            messages.error(request, f'Nombre inválido para el grupo {i+1}.')
                            return redirect('indicadores:deconstruir_tabla')
                        group_names[str(i)] = name
                    sheets_group_names[sheet_name] = group_names

                next_idx = current_idx + 1
                if next_idx < len(sheet_names):
                    wizard_data['current_sheet_idx'] = next_idx
                    wizard_data['sheets_group_names'] = sheets_group_names
                    request.session[wizard_key] = wizard_data
                    return redirect('indicadores:deconstruir_tabla')

            wizard_data['sheets_group_names'] = sheets_group_names
            wizard_data['paso'] = 3
            request.session[wizard_key] = wizard_data
            return redirect('indicadores:deconstruir_tabla')

        # ── PASO 3: Generar ────────────────────────────────────────────
        elif action == 'generate':
            archivo_path = wizard_data.get('archivo_path')
            if not archivo_path or not default_storage.exists(archivo_path):
                messages.error(request, 'El archivo temporal expiró. Suba el archivo nuevamente.')
                request.session.pop(wizard_key, None)
                return redirect('indicadores:deconstruir_tabla')

            sheets_group_names = wizard_data.get('sheets_group_names', {})
            modo = wizard_data.get('modo', 'individual')

            # Obtener datos del indicador para modo individual
            codigo_indicador = None
            nombre_indicador = None
            if modo == 'individual':
                indicador_id = wizard_data.get('indicador_id')
                if indicador_id:
                    try:
                        ind = Indicador.objects.get(id=indicador_id)
                        codigo_indicador = ind.codigo_indicador
                        nombre_indicador = ind.nombre
                    except Indicador.DoesNotExist:
                        pass

            with default_storage.open(archivo_path, 'rb') as f:
                if modo == 'individual':
                    sheet_name = wizard_data['sheet_names'][0]
                    gnames = sheets_group_names.get(sheet_name, {})
                    result_df = _dt_process_sheet(f, 0, gnames, codigo_indicador, nombre_indicador)

                    if result_df is None or result_df.empty:
                        messages.error(request, 'No se generaron datos. Verifique el archivo.')
                        return redirect('indicadores:deconstruir_tabla')

                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        result_df.to_excel(writer, index=False, sheet_name='Datos')
                    output.seek(0)

                    default_storage.delete(archivo_path)
                    request.session.pop(wizard_key, None)

                    base_name = wizard_data.get('archivo_nombre', 'tabla').rsplit('.', 1)[0]
                    response = HttpResponse(
                        output.read(),
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
                    response['Content-Disposition'] = (
                        f'attachment; filename="{base_name}_deconstruido.xlsx"'
                    )
                    return response

                else:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for sn in wizard_data['sheet_names']:
                            gnames = sheets_group_names.get(sn)
                            if gnames is None:
                                continue
                            f.seek(0)
                            # Para masivo, usamos el nombre de la hoja como código de indicador si parece un código
                            sheet_codigo = sn if sn and not sn.startswith('Hoja') else None
                            result_df = _dt_process_sheet(f, sn, gnames, sheet_codigo, None)
                            if result_df is None or result_df.empty:
                                continue

                            sheet_output = BytesIO()
                            with pd.ExcelWriter(sheet_output, engine='openpyxl') as writer:
                                result_df.to_excel(writer, index=False, sheet_name='Datos')
                            sheet_output.seek(0)

                            safe_name = re.sub(r'[^\w\s\-]', '', sn, flags=re.UNICODE)
                            safe_name = re.sub(r'\s+', '_', safe_name).strip('_') or 'hoja'
                            zf.writestr(f'{safe_name}_deconstruido.xlsx', sheet_output.read())

                    zip_buffer.seek(0)
                    default_storage.delete(archivo_path)
                    request.session.pop(wizard_key, None)

                    base_name = wizard_data.get('archivo_nombre', 'tabla').rsplit('.', 1)[0]
                    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
                    response['Content-Disposition'] = (
                        f'attachment; filename="{base_name}_deconstruidos.zip"'
                    )
                    return response

    # ── RENDER del paso actual ─────────────────────────────────────────
    context = {
        'paso': paso,
        'modo': modo,
        'wizard_data': wizard_data,
        'indicador_id': indicador_id,
    }

    if paso == 2:
        if modo == 'individual':
            sheet_name = wizard_data.get('sheet_names', [''])[0]
            context['current_sheet'] = sheet_name
            context['analysis'] = wizard_data.get('sheets_analysis', {}).get(sheet_name, {})
        else:
            current_idx = wizard_data.get('current_sheet_idx', 0)
            sheet_names = wizard_data.get('sheet_names', [])
            if current_idx < len(sheet_names):
                sheet_name = sheet_names[current_idx]
                context['current_sheet'] = sheet_name
                context['current_sheet_idx'] = current_idx + 1
                context['total_sheets'] = len(sheet_names)
                context['analysis'] = wizard_data.get('sheets_analysis', {}).get(sheet_name, {})
            else:
                wizard_data['paso'] = 3
                request.session[wizard_key] = wizard_data
                context['paso'] = 3

    if paso == 3:
        context['sheets_group_names'] = wizard_data.get('sheets_group_names', {})
        context['archivo_nombre'] = wizard_data.get('archivo_nombre', '')

    return render(request, 'recoleccion/deconstruir_tabla.html', context)
