"""
Views para el módulo de Reportes (independiente de Recolección)
"""
from io import BytesIO
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
import pandas as pd

from .models import Indicador, Dato, ConjuntoDatos, VariableConjuntoDatos
from .decorators import consultor_reportes_required


# =============================================================================
# AUTENTICACIÓN
# =============================================================================

def reportes_login(request):
    """Vista de login para el módulo de reportes"""
    if request.user.is_authenticated:
        # Si ya está autenticado, verificar permisos
        if request.user.is_staff:
            # Los administradores staff tienen acceso directo
            return redirect('indicadores:reportes_dashboard')
        elif hasattr(request.user, 'perfil_recolector') and request.user.perfil_recolector.puede_consultar_reportes():
            return redirect('indicadores:reportes_dashboard')
        else:
            # Si no tiene permisos, hacer logout y mostrar mensaje
            # Esto evita el loop de redirecciones
            logout(request)
            messages.warning(request, 'No tiene permisos para acceder al módulo de reportes. Por favor inicie sesión con una cuenta autorizada.')
            # No redirigir, mostrar el formulario de login con el mensaje
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Verificar permisos
            if user.is_staff:
                # Los administradores tienen acceso total
                login(request, user)
                messages.success(request, f'Bienvenido Administrador {user.get_full_name() or user.username}')
                return redirect('indicadores:reportes_dashboard')
            elif hasattr(user, 'perfil_recolector') and user.perfil_recolector.puede_consultar_reportes():
                login(request, user)
                messages.success(request, f'Bienvenido al módulo de reportes, {user.get_full_name() or user.username}')
                return redirect('indicadores:reportes_dashboard')
            else:
                messages.error(request, 'No tiene permisos para acceder al módulo de reportes o su cuenta está inactiva')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos')
    
    return render(request, 'reportes/login.html')


@login_required(login_url='/reportes/login/')
def reportes_logout(request):
    """Vista de logout para el módulo de reportes"""
    logout(request)
    messages.success(request, 'Sesión cerrada correctamente')
    return redirect('indicadores:reportes_login')


# =============================================================================
# DASHBOARD
# =============================================================================

@consultor_reportes_required
def reportes_dashboard(request):
    """Dashboard principal del módulo de reportes con observabilidad completa"""
    from django.db.models import Count, Min, Max, Q, Prefetch
    from .models import MenuDominio, MenuTema, MenuSubtema
    
    # =========================================================================
    # ESTADÍSTICAS GENERALES
    # =========================================================================
    total_indicadores = Indicador.objects.filter(activo=True).count()
    total_datos = Dato.objects.count()
    total_conjunto_datos = ConjuntoDatos.objects.count()
    
    # Indicadores con datos
    indicadores_con_datos = Indicador.objects.filter(
        activo=True,
        datos__isnull=False
    ).distinct().count()
    
    # Indicadores con gráficos activos
    indicadores_con_graficos = Indicador.objects.filter(
        activo=True,
        graficos__activo=True
    ).distinct().count()
    
    # Indicadores con mapa activo
    indicadores_con_mapa = Indicador.objects.filter(
        activo=True,
        mostrar_mapa=True
    ).count()
    
    # Porcentajes
    porcentaje_con_datos = round((indicadores_con_datos / total_indicadores * 100), 1) if total_indicadores > 0 else 0
    porcentaje_con_graficos = round((indicadores_con_graficos / total_indicadores * 100), 1) if total_indicadores > 0 else 0
    porcentaje_con_mapa = round((indicadores_con_mapa / total_indicadores * 100), 1) if total_indicadores > 0 else 0
    
    # =========================================================================
    # ANÁLISIS POR DOMINIO, TEMA Y SUBTEMA
    # =========================================================================
    dominios_stats = []
    dominios = MenuDominio.objects.prefetch_related(
        'temas__subtemas__indicadores',
        'temas__subtemas__indicadores_adicionales'
    ).order_by('orden', 'nombre')
    
    for dominio in dominios:
        temas_stats = []
        for tema in dominio.temas.all().order_by('orden', 'nombre'):
            subtemas_stats = []
            for subtema in tema.subtemas.all().order_by('orden', 'nombre'):
                # Indicadores del subtema con anotación de fechas
                # (subtema principal FK + subtemas adicionales M2M)
                indicadores_subtema = Indicador.objects.filter(
                    Indicador.q_por_subtema(subtema),
                    activo=True
                ).distinct().annotate(
                    fecha_min=Min('datos__fecha_dato'),
                    fecha_max=Max('datos__fecha_dato'),
                    total_datos_count=Count('datos')
                ).prefetch_related(
                    'dominios_desagregacion_tematica',
                    'dominios_desagregacion_geografica',
                    'subtemas_adicionales',
                ).order_by('orden', 'nombre')
                
                total_ind_subtema = indicadores_subtema.count()
                
                # Lista de indicadores serializada para el template
                lista_indicadores = []

                if total_ind_subtema > 0:
                    # Contar estadísticas
                    ind_con_datos = 0
                    ind_con_graficos = 0
                    ind_con_mapa = 0
                    suma_completitud_metadatos = 0

                    for ind in indicadores_subtema:
                        has_data = ind.total_datos_count > 0
                        has_graph = ind.graficos.filter(activo=True).exists()
                        has_map = ind.mostrar_mapa

                        # Completitud solo sobre campos del estándar MSD/SDMX
                        # (fuente única: Indicador.campos_metadatos_estandar)
                        porcentaje_metadatos = ind.porcentaje_completitud_metadatos()
                        suma_completitud_metadatos += porcentaje_metadatos
                        
                        if has_data:
                            ind_con_datos += 1
                        if has_graph:
                            ind_con_graficos += 1
                        if has_map:
                            ind_con_mapa += 1
                            
                        lista_indicadores.append({
                            'id': ind.id,
                            'nombre': ind.nombre,
                            'codigo': ind.codigo_indicador,
                            'tiene_datos': has_data,
                            'fecha_min': ind.fecha_min,
                            'fecha_max': ind.fecha_max,
                            'total_datos': ind.total_datos_count,
                            'porcentaje_metadatos': porcentaje_metadatos,
                        })
                    
                    subtemas_stats.append({
                        'nombre': subtema.nombre,
                        'slug': subtema.slug,
                        'total_indicadores': total_ind_subtema,
                        'con_datos': ind_con_datos,
                        'con_graficos': ind_con_graficos,
                        'con_mapa': ind_con_mapa,
                        'porcentaje_datos': round((ind_con_datos / total_ind_subtema * 100), 1),
                        'promedio_metadatos': round((suma_completitud_metadatos / total_ind_subtema), 1),
                        'indicadores': lista_indicadores  # Agregamos la lista detallada
                    })
            
            # Totales del tema
            total_ind_tema = sum(s['total_indicadores'] for s in subtemas_stats)
            if total_ind_tema > 0:
                temas_stats.append({
                    'nombre': tema.nombre,
                    'slug': tema.slug,
                    'total_indicadores': total_ind_tema,
                    'con_datos': sum(s['con_datos'] for s in subtemas_stats),
                    'con_graficos': sum(s['con_graficos'] for s in subtemas_stats),
                    'con_mapa': sum(s['con_mapa'] for s in subtemas_stats),
                    'promedio_metadatos': round(sum(s['promedio_metadatos'] * s['total_indicadores'] for s in subtemas_stats) / total_ind_tema, 1) if total_ind_tema > 0 else 0,
                    'subtemas': subtemas_stats,
                })
        
        # Totales del dominio
        total_ind_dominio = sum(t['total_indicadores'] for t in temas_stats)
        if total_ind_dominio > 0:
            dominios_stats.append({
                'nombre': dominio.nombre,
                'slug': dominio.slug,
                'color': dominio.color or '#3B82F6',
                'total_indicadores': total_ind_dominio,
                'con_datos': sum(t['con_datos'] for t in temas_stats),
                'con_graficos': sum(t['con_graficos'] for t in temas_stats),
                'con_mapa': sum(t['con_mapa'] for t in temas_stats),
                'porcentaje_datos': round((sum(t['con_datos'] for t in temas_stats) / total_ind_dominio * 100), 1),
                'promedio_metadatos': round(sum(t['promedio_metadatos'] * t['total_indicadores'] for t in temas_stats) / total_ind_dominio, 1) if total_ind_dominio > 0 else 0,
                'temas': temas_stats,
            })
    
    # =========================================================================
    # INDICADORES CON DATOS - ANÁLISIS TEMPORAL
    # =========================================================================
    indicadores_con_fechas = Indicador.objects.filter(
        activo=True,
        datos__isnull=False
    ).annotate(
        fecha_min=Min('datos__fecha_dato'),
        fecha_max=Max('datos__fecha_dato'),
        total_datos=Count('datos')
    ).order_by('-fecha_max')[:20]  # Top 20 más recientes
    
    # =========================================================================
    # INDICADORES SIN DATOS (PENDIENTES)
    # =========================================================================
    indicadores_sin_datos = Indicador.objects.filter(
        activo=True,
        datos__isnull=True
    ).select_related(
        'subtema__tema__dominio', 'organismo_responsable'
    ).order_by('subtema__tema__dominio__nombre', 'nombre')[:50]
    
    # =========================================================================
    # INDICADORES DESACTUALIZADOS (con datos pero antiguos)
    # =========================================================================
    from datetime import timedelta as td
    hoy = datetime.now()
    umbral_desactualizado = hoy - td(days=365 * 2)  # 2 años sin actualización
    indicadores_desactualizados = Indicador.objects.filter(
        activo=True,
        datos__isnull=False
    ).annotate(
        ultima_fecha=Max('datos__fecha_dato')
    ).filter(
        ultima_fecha__lt=umbral_desactualizado
    ).select_related(
        'subtema__tema__dominio', 'organismo_responsable'
    ).order_by('ultima_fecha')[:30]

    # =========================================================================
    # ALERTAS Y NOTIFICACIONES
    # =========================================================================
    alertas = []
    
    # Alerta: Indicadores sin datos
    if total_indicadores - indicadores_con_datos > 0:
        alertas.append({
            'tipo': 'warning',
            'titulo': 'Indicadores sin datos',
            'mensaje': f'{total_indicadores - indicadores_con_datos} indicadores ({100 - porcentaje_con_datos:.1f}%) no tienen datos cargados',
            'icono': 'fa-exclamation-triangle'
        })
    
    # Alerta: Indicadores con datos pero sin gráficos
    ind_datos_sin_graficos = indicadores_con_datos - indicadores_con_graficos
    if ind_datos_sin_graficos > 0:
        alertas.append({
            'tipo': 'info',
            'titulo': 'Indicadores sin gráficos',
            'mensaje': f'{ind_datos_sin_graficos} indicadores tienen datos pero no tienen gráficos configurados',
            'icono': 'fa-chart-line'
        })
    
    # Alerta: Progreso general
    if porcentaje_con_datos >= 50:
        alertas.append({
            'tipo': 'success',
            'titulo': '¡Buen progreso!',
            'mensaje': f'Ya se ha completado el {porcentaje_con_datos}% de los indicadores con datos',
            'icono': 'fa-check-circle'
        })
    
    # ----------------------------------------------------------------
    # T3: TRAZABILIDAD — Resumen en dashboard
    # ----------------------------------------------------------------
    from .models import RegistroCambio
    from django.db.models import Count
    from datetime import timedelta
    ultimos_30 = hoy - timedelta(days=30)

    ultimos_cambios = RegistroCambio.objects.select_related(
        'indicador', 'usuario', 'organismo_origen', 'organismo_responsable'
    ).order_by('-fecha')[:10]

    cambios_por_organismo = RegistroCambio.objects.filter(
        fecha__gte=hoy - timedelta(days=180)
    ).values('organismo_origen__nombre').annotate(
        total=Count('id')
    ).order_by('-total')[:8]

    context = {
        # Estadísticas generales
        'total_indicadores': total_indicadores,
        'total_datos': total_datos,
        'total_conjunto_datos': total_conjunto_datos,
        'indicadores_con_datos': indicadores_con_datos,
        'indicadores_con_graficos': indicadores_con_graficos,
        'indicadores_con_mapa': indicadores_con_mapa,
        'porcentaje_con_datos': porcentaje_con_datos,
        'porcentaje_con_graficos': porcentaje_con_graficos,
        'porcentaje_con_mapa': porcentaje_con_mapa,

        # Análisis por estructura
        'dominios_stats': dominios_stats,

        # Indicadores con datos
        'indicadores_con_fechas': indicadores_con_fechas,

        # Indicadores pendientes
        'indicadores_sin_datos': indicadores_sin_datos,
        'total_sin_datos': total_indicadores - indicadores_con_datos,

        # Indicadores desactualizados
        'indicadores_desactualizados': indicadores_desactualizados,

        # Alertas
        'alertas': alertas,

        # Trazabilidad
        'ultimos_cambios': ultimos_cambios,
        'cambios_por_organismo': cambios_por_organismo,
    }

    return render(request, 'reportes/dashboard.html', context)


# =============================================================================
# REPORTES DE INDICADORES
# =============================================================================

@consultor_reportes_required
def reportes_indicadores(request):
    """Vista para generar reportes de indicadores"""
    indicadores = Indicador.objects.filter(activo=True).order_by('codigo_indicador')
    
    context = {
        'indicadores': indicadores,
    }
    
    return render(request, 'reportes/reportes_indicadores.html', context)


@consultor_reportes_required
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


@consultor_reportes_required
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
        
        # Crear DataFrame con metadata
        data = []
        for ind in indicadores:
            data.append({
                'Codigo_Indicador': ind.codigo_indicador,
                'Nombre_Indicador': ind.nombre,
                'Sigla': ind.sigla or '',
                'Descripcion_Indicador': ind.descripcion_indicador or '',
                'Objetivo': ind.objetivo or '',
                'Unidad_Medida': ind.unidad_medida or '',
                'Formula': ind.formula_ficha or '',
                'Frecuencia_Difusion': ind.frecuencia_difusion or '',
                'Fuente_Datos': ind.fuente_datos or '',
                'Comentarios_Adicionales': ind.comentarios_adicionales or '',
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


# =============================================================================
# REPORTES DE MICRODATA
# =============================================================================

@consultor_reportes_required
def reportes_conjuntos_datos(request):
    """Vista para generar reportes de conjunto_datos"""
    conjunto_datos_list = ConjuntoDatos.objects.all().order_by('-fecha_carga')
    
    context = {
        'conjunto_datos_list': conjunto_datos_list,
    }
    
    return render(request, 'reportes/reportes_conjuntos_datos.html', context)


@consultor_reportes_required
def descargar_conjunto_datos(request, conjunto_datos_id):
    """Descarga archivo de conjunto_datos"""
    try:
        conjunto_datos = get_object_or_404(ConjuntoDatos, id=conjunto_datos_id)
        
        # Leer el archivo CSV
        with open(conjunto_datos.archivo_csv.path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="conjunto_datos_{conjunto_datos.id}_{datetime.now().strftime("%Y%m%d")}.csv"'
            return response
            
    except Exception as e:
        messages.error(request, f'Error al descargar conjunto_datos: {str(e)}')
        return redirect('indicadores:reportes_conjuntos_datos')


@consultor_reportes_required
def descargar_metadata_variables(request, conjunto_datos_id):
    """Descarga metadata de variables de una conjunto_datos"""
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
        
        filename = f"metadata_variables_conjunto_datos_{conjunto_datos.id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        
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


# =============================================================================
# TRAZABILIDAD DE CAMBIOS POR ORGANISMO
# =============================================================================

@consultor_reportes_required
def reportes_trazabilidad(request):
    """
    Vista dedicada de trazabilidad con filtros dinámicos, timeline y heatmap.
    """
    from django.db.models import Count, Q
    from django.core.paginator import Paginator
    from .models import Organismo, RegistroCambio

    # Filtros GET
    organismo_origen_id = request.GET.get('organismo_origen', '')
    organismo_resp_id = request.GET.get('organismo_responsable', '')
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    tipo_evento = request.GET.get('tipo_evento', '')
    indicador_q = request.GET.get('indicador', '')

    qs = RegistroCambio.objects.select_related(
        'indicador', 'usuario', 'organismo_origen', 'organismo_responsable'
    ).order_by('-fecha')

    # Aplicar filtros
    if organismo_origen_id:
        qs = qs.filter(organismo_origen_id=organismo_origen_id)
    if organismo_resp_id:
        qs = qs.filter(organismo_responsable_id=organismo_resp_id)
    if fecha_desde:
        qs = qs.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha__date__lte=fecha_hasta)
    if tipo_evento:
        qs = qs.filter(tipo_evento=tipo_evento)
    if indicador_q:
        qs = qs.filter(
            Q(indicador__nombre__icontains=indicador_q) |
            Q(indicador__codigo_indicador__icontains=indicador_q)
        )

    # Paginación
    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Stats para filtros y cards
    organismos = Organismo.objects.filter(activo=True).order_by('nombre')
    tipos_evento = RegistroCambio.TIPO_EVENTO

    # Contadores rápidos (últimos 30 días)
    from datetime import timedelta
    hoy = datetime.now()
    ultimos_30 = hoy - timedelta(days=30)

    total_cambios = qs.count()
    cambios_30d = RegistroCambio.objects.filter(fecha__gte=ultimos_30).count()

    top_organismos_origen = RegistroCambio.objects.filter(
        fecha__gte=ultimos_30
    ).values('organismo_origen__nombre').annotate(
        total=Count('id')
    ).order_by('-total')[:5]

    top_organismos_resp = RegistroCambio.objects.filter(
        fecha__gte=ultimos_30
    ).values('organismo_responsable__nombre').annotate(
        total=Count('id')
    ).order_by('-total')[:5]

    # Heatmap data: organismos × meses (últimos 6 meses)
    from django.db.models.functions import TruncMonth
    heatmap_qs = RegistroCambio.objects.filter(fecha__gte=hoy - timedelta(days=180))
    heatmap_data = list(
        heatmap_qs.values('organismo_origen__nombre', mes=TruncMonth('fecha')).annotate(
            total=Count('id')
        ).order_by('organismo_origen__nombre', 'mes')
    )

    context = {
        'page_obj': page_obj,
        'total_cambios': total_cambios,
        'cambios_30d': cambios_30d,
        'top_organismos_origen': top_organismos_origen,
        'top_organismos_resp': top_organismos_resp,
        'heatmap_data': heatmap_data,
        'organismos': organismos,
        'tipos_evento': tipos_evento,
        'filtros': {
            'organismo_origen': organismo_origen_id,
            'organismo_responsable': organismo_resp_id,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'tipo_evento': tipo_evento,
            'indicador': indicador_q,
        }
    }
    return render(request, 'reportes/trazabilidad.html', context)


@consultor_reportes_required
def exportar_trazabilidad_excel(request):
    """Exporta la trazabilidad filtrada a Excel."""
    from django.db.models import Q
    from .models import RegistroCambio

    organismo_origen_id = request.GET.get('organismo_origen', '')
    organismo_resp_id = request.GET.get('organismo_responsable', '')
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    tipo_evento = request.GET.get('tipo_evento', '')
    indicador_q = request.GET.get('indicador', '')

    qs = RegistroCambio.objects.select_related(
        'indicador', 'usuario', 'organismo_origen', 'organismo_responsable'
    ).order_by('-fecha')

    if organismo_origen_id:
        qs = qs.filter(organismo_origen_id=organismo_origen_id)
    if organismo_resp_id:
        qs = qs.filter(organismo_responsable_id=organismo_resp_id)
    if fecha_desde:
        qs = qs.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha__date__lte=fecha_hasta)
    if tipo_evento:
        qs = qs.filter(tipo_evento=tipo_evento)
    if indicador_q:
        qs = qs.filter(
            Q(indicador__nombre__icontains=indicador_q) |
            Q(indicador__codigo_indicador__icontains=indicador_q)
        )

    data = []
    for rc in qs:
        data.append({
            'Fecha': rc.fecha.strftime('%Y-%m-%d %H:%M'),
            'Indicador': rc.indicador.nombre if rc.indicador else '',
            'Codigo': rc.indicador.codigo_indicador if rc.indicador else '',
            'Usuario': rc.usuario.username if rc.usuario else 'Sistema',
            'Organismo_Origen': rc.organismo_origen.nombre if rc.organismo_origen else '—',
            'Organismo_Responsable': rc.organismo_responsable.nombre if rc.organismo_responsable else '—',
            'Tipo_Evento': rc.get_tipo_evento_display(),
            'Filas_Afectadas': rc.filas_afectadas,
            'Archivo': rc.archivo_relacionado or '',
        })

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Trazabilidad', index=False)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="trazabilidad_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx"'
    return response


# =============================================================================
# OPERACIONES — OBSERVABILIDAD DEL PIPELINE DE CARGAS
# =============================================================================

@consultor_reportes_required
def reportes_operaciones(request):
    """
    Vista de observabilidad operacional del pipeline de cargas.
    Métricas del flujo recolector → validador → admin sin saturar al usuario.
    """
    from django.db.models import Count, Avg, F, Q, DurationField, ExpressionWrapper
    from django.db.models.functions import TruncDate
    from django.core.paginator import Paginator
    from django.utils import timezone
    from datetime import timedelta

    from .models import CargaSerieIndicador, CargaConjuntoDatos, CargaMasivaSerie

    hoy = timezone.now().date()
    ultimos_7d = hoy - timedelta(days=7)
    ultimos_30d = hoy - timedelta(days=30)

    # =====================================================================
    # 1. RESUMEN HOY
    # =====================================================================
    series_hoy = CargaSerieIndicador.objects.filter(
        fecha_carga__date=hoy
    ).count()
    conjunto_datos_hoy = CargaConjuntoDatos.objects.filter(
        fecha_carga__date=hoy
    ).count()
    masivas_hoy = CargaMasivaSerie.objects.filter(
        fecha_carga__date=hoy
    ).count()

    # =====================================================================
    # 2. ESTADOS ACTUALES — Pipeline General
    # =====================================================================
    estados_series = dict(
        CargaSerieIndicador.objects.values('estado').annotate(
            total=Count('id')
        ).values_list('estado', 'total')
    )
    estados_conjunto_datos = dict(
        CargaConjuntoDatos.objects.values('estado').annotate(
            total=Count('id')
        ).values_list('estado', 'total')
    )

    # =====================================================================
    # 3. PIPELINE DE VALIDACIÓN (flujo delegado)
    # =====================================================================
    pipeline_validacion = CargaSerieIndicador.objects.filter(
        es_carga_delegado=True
    ).values('estado').annotate(total=Count('id')).order_by('estado')

    pipeline_conjunto_datos_validacion = CargaConjuntoDatos.objects.filter(
        es_carga_delegado=True
    ).values('estado').annotate(total=Count('id')).order_by('estado')

    # =====================================================================
    # 4. CORRECCIONES
    # =====================================================================
    correcciones_pendientes = CargaSerieIndicador.objects.filter(
        estado='correcciones_solicitadas'
    ).select_related('usuario', 'indicador').order_by('-fecha_carga')[:20]

    correcciones_pendientes_conjunto_datos = CargaConjuntoDatos.objects.filter(
        estado='correcciones_solicitadas'
    ).select_related('usuario', 'conjunto_datos').order_by('-fecha_carga')[:20]

    # =====================================================================
    # 5. CARGAS MASIVAS EN PROCESO
    # =====================================================================
    masivas_en_proceso = CargaMasivaSerie.objects.filter(
        estado__in=('pendiente', 'procesando', 'validacion_recolector', 'despachada')
    ).select_related('usuario').order_by('-fecha_carga')[:15]

    masivas_resumen = dict(
        CargaMasivaSerie.objects.values('estado').annotate(
            total=Count('id')
        ).values_list('estado', 'total')
    )

    # =====================================================================
    # 6. ERRORES RECIENTES
    # =====================================================================
    errores_series = CargaSerieIndicador.objects.filter(
        Q(estado='error') | Q(mensaje_error__isnull=False),
        fecha_carga__date__gte=ultimos_7d
    ).exclude(mensaje_error='').select_related('usuario', 'indicador').order_by('-fecha_carga')[:15]

    errores_conjunto_datos = CargaConjuntoDatos.objects.filter(
        Q(estado='error') | Q(mensaje_error__isnull=False),
        fecha_carga__date__gte=ultimos_7d
    ).exclude(mensaje_error='').select_related('usuario', 'conjunto_datos').order_by('-fecha_carga')[:15]

    # =====================================================================
    # 7. TOP ACTIVIDAD POR USUARIO (últimos 30 días)
    # =====================================================================
    top_recolectores = CargaSerieIndicador.objects.filter(
        fecha_carga__date__gte=ultimos_30d
    ).values('usuario__username', 'usuario__first_name', 'usuario__last_name').annotate(
        total=Count('id')
    ).order_by('-total')[:10]

    # =====================================================================
    # 8. VOLUMEN DIARIO (últimos 14 días)
    # =====================================================================
    hoy_dt = timezone.now()
    inicio_14d = hoy_dt - timedelta(days=14)
    volumen_diario = list(
        CargaSerieIndicador.objects.filter(
            fecha_carga__gte=inicio_14d
        ).annotate(dia=TruncDate('fecha_carga')).values('dia').annotate(
            total=Count('id')
        ).order_by('dia')
    )
    max_volumen = max((v['total'] for v in volumen_diario), default=1)

    # =====================================================================
    # 9. CARGAS RECIENTES (tabla filtrable/paginada para consulta)
    # =====================================================================
    op_estado = request.GET.get('op_estado', '')
    op_q = request.GET.get('op_q', '')

    qs_series_op = CargaSerieIndicador.objects.all().select_related(
        'usuario', 'indicador'
    ).order_by('-fecha_carga')
    if op_estado:
        qs_series_op = qs_series_op.filter(estado=op_estado)
    if op_q:
        qs_series_op = qs_series_op.filter(
            Q(codigo_evidencia__icontains=op_q) |
            Q(indicador__nombre__icontains=op_q)
        )

    qs_conjunto_datos_op = CargaConjuntoDatos.objects.all().select_related(
        'usuario', 'conjunto_datos'
    ).order_by('-fecha_carga')
    if op_estado:
        qs_conjunto_datos_op = qs_conjunto_datos_op.filter(estado=op_estado)
    if op_q:
        qs_conjunto_datos_op = qs_conjunto_datos_op.filter(
            Q(codigo_evidencia__icontains=op_q) |
            Q(conjunto_datos__nombre__icontains=op_q)
        )

    op_items = []
    for c in qs_series_op[:150]:
        op_items.append({
            'tipo': 'serie',
            'codigo': c.codigo_evidencia,
            'nombre': c.indicador.nombre if c.indicador else 'Sin indicador',
            'estado': c.estado,
            'origen': 'Delegado' if c.es_carga_delegado else ('Masiva' if c.carga_masiva_origen else 'Interno'),
            'usuario': c.usuario.get_full_name() or c.usuario.username,
            'fecha': c.fecha_carga,
        })
    for c in qs_conjunto_datos_op[:150]:
        op_items.append({
            'tipo': 'conjunto_datos',
            'codigo': c.codigo_evidencia,
            'nombre': c.conjunto_datos.nombre if c.conjunto_datos else 'Sin conjunto_datos',
            'estado': c.estado,
            'origen': 'Delegado' if c.es_carga_delegado else 'Interno',
            'usuario': c.usuario.get_full_name() or c.usuario.username,
            'fecha': c.fecha_carga,
        })
    op_items.sort(key=lambda x: x['fecha'], reverse=True)

    op_page = request.GET.get('op_page', 1)
    op_paginator = Paginator(op_items, 15)
    try:
        op_items_page = op_paginator.page(op_page)
    except (PageNotAnInteger, EmptyPage):
        op_items_page = op_paginator.page(1)

    context = {
        'hoy': hoy,
        'series_hoy': series_hoy,
        'conjunto_datos_hoy': conjunto_datos_hoy,
        'masivas_hoy': masivas_hoy,
        'estados_series': estados_series,
        'estados_conjunto_datos': estados_conjunto_datos,
        'pipeline_validacion': pipeline_validacion,
        'pipeline_conjunto_datos_validacion': pipeline_conjunto_datos_validacion,
        'correcciones_pendientes': correcciones_pendientes,
        'correcciones_pendientes_conjunto_datos': correcciones_pendientes_conjunto_datos,
        'masivas_en_proceso': masivas_en_proceso,
        'masivas_resumen': masivas_resumen,
        'errores_series': errores_series,
        'errores_conjunto_datos': errores_conjunto_datos,
        'top_recolectores': top_recolectores,
        'volumen_diario': volumen_diario,
        'max_volumen': max_volumen,
        'op_items': op_items_page,
        'op_estado': op_estado,
        'op_q': op_q,
        'op_estados': ['', 'borrador', 'pendiente', 'enviado', 'aprobado', 'correcciones_solicitadas', 'rechazado', 'procesado', 'exitoso', 'error'],
    }
    return render(request, 'reportes/operaciones.html', context)


# =============================================================================
# PRODUCCION MENSUAL (Reporte de Control)
# =============================================================================

@consultor_reportes_required
def reportes_produccion_mensual(request):
    """
    Reporte de producción mensual para el informe de control.
    Muestra qué indicadores fueron cargados cada mes.
    """
    from django.db.models import Count
    from django.db.models.functions import TruncMonth
    from django.utils import timezone
    from datetime import timedelta
    from .models import CargaSerieIndicador, CargaConjuntoDatos

    hoy = timezone.now()
    inicio_12m = hoy - timedelta(days=365)

    # --- Series por mes (para tabla resumen) ---
    series_por_mes = list(
        CargaSerieIndicador.objects.filter(
            fecha_carga__gte=inicio_12m,
            indicador__isnull=False
        ).annotate(mes=TruncMonth('fecha_carga')).values('mes').annotate(
            total=Count('id'),
            unicos=Count('indicador', distinct=True)
        ).order_by('-mes')
    )

    # --- conjunto_datos por mes (para tabla resumen) ---
    conjunto_datos_por_mes = list(
        CargaConjuntoDatos.objects.filter(
            fecha_carga__gte=inicio_12m,
            conjunto_datos__isnull=False
        ).annotate(mes=TruncMonth('fecha_carga')).values('mes').annotate(
            total=Count('id')
        ).order_by('-mes')
    )

    # --- Series por usuario y mes ---
    series_por_usuario_mes = list(
        CargaSerieIndicador.objects.filter(
            fecha_carga__gte=inicio_12m
        ).annotate(mes=TruncMonth('fecha_carga')).values(
            'mes', 'usuario__first_name', 'usuario__last_name', 'usuario__username'
        ).annotate(
            total=Count('id')
        ).order_by('-mes', 'usuario__username')
    )

    # --- conjunto_datos por usuario y mes ---
    conjunto_datos_por_usuario_mes = list(
        CargaConjuntoDatos.objects.filter(
            fecha_carga__gte=inicio_12m
        ).annotate(mes=TruncMonth('fecha_carga')).values(
            'mes', 'usuario__first_name', 'usuario__last_name', 'usuario__username'
        ).annotate(
            total=Count('id')
        ).order_by('-mes', 'usuario__username')
    )

    # --- Totales ---
    total_series = CargaSerieIndicador.objects.filter(
        fecha_carga__gte=inicio_12m
    ).count()
    total_conjunto_datos = CargaConjuntoDatos.objects.filter(
        fecha_carga__gte=inicio_12m
    ).count()
    total_indicadores_unicos = CargaSerieIndicador.objects.filter(
        fecha_carga__gte=inicio_12m,
        indicador__isnull=False
    ).values('indicador').distinct().count()

    context = {
        'series_por_mes': series_por_mes,
        'conjunto_datos_por_mes': conjunto_datos_por_mes,
        'series_por_usuario_mes': series_por_usuario_mes,
        'conjunto_datos_por_usuario_mes': conjunto_datos_por_usuario_mes,
        'total_series': total_series,
        'total_conjunto_datos': total_conjunto_datos,
        'total_indicadores_unicos': total_indicadores_unicos,
        'inicio_periodo': inicio_12m,
        'fin_periodo': hoy,
    }
    return render(request, 'reportes/produccion_mensual.html', context)


@consultor_reportes_required
def reportes_produccion_mensual_exportar_excel(request):
    """
    Exporta el reporte de producción mensual a Excel (.xlsx).
    Hoja 1: Resumen por mes.
    Hoja 2: Indicadores cargados por mes (código, nombre, cargas, registros).
    Hoja 3: conjunto_datos cargados por mes.
    """
    from django.db.models import Count, Sum
    from django.db.models.functions import TruncMonth
    from django.utils import timezone
    from datetime import timedelta
    from io import BytesIO
    from .models import CargaSerieIndicador, CargaConjuntoDatos

    hoy = timezone.now()
    inicio_12m = hoy - timedelta(days=365)

    # --- Hoja 1: Resumen Mensual ---
    indicadores_mes = list(
        CargaSerieIndicador.objects.filter(
            fecha_carga__gte=inicio_12m,
            indicador__isnull=False
        ).annotate(mes=TruncMonth('fecha_carga')).values('mes').annotate(
            indicadores=Count('indicador', distinct=True),
            cargas=Count('id'),
            registros=Sum('registros_procesados')
        ).order_by('mes')
    )

    conjunto_datos_mes = list(
        CargaConjuntoDatos.objects.filter(
            fecha_carga__gte=inicio_12m
        ).annotate(mes=TruncMonth('fecha_carga')).values('mes').annotate(
            conjunto_datos=Count('id')
        ).order_by('mes')
    )

    df_ind = pd.DataFrame(indicadores_mes)
    df_md = pd.DataFrame(conjunto_datos_mes)

    # Normalizar columnas de mes
    for df in (df_ind, df_md):
        if not df.empty and 'mes' in df.columns:
            df['mes'] = pd.to_datetime(df['mes']).dt.strftime('%Y-%m')

    # Construir resumen unificado robusto
    all_meses = set()
    if not df_ind.empty and 'mes' in df_ind.columns:
        all_meses.update(df_ind['mes'].tolist())
    if not df_md.empty and 'mes' in df_md.columns:
        all_meses.update(df_md['mes'].tolist())

    rows_resumen = []
    for mes in sorted(all_meses):
        row = {'Mes': mes}
        if not df_ind.empty and 'mes' in df_ind.columns:
            vals = df_ind[df_ind['mes'] == mes]
            row['Indicadores Unicos'] = int(vals['indicadores'].sum()) if not vals.empty else 0
            row['Cargas Series'] = int(vals['cargas'].sum()) if not vals.empty else 0
            row['Registros Procesados'] = int(vals['registros'].sum()) if not vals.empty else 0
        else:
            row.update({'Indicadores Unicos': 0, 'Cargas Series': 0, 'Registros Procesados': 0})
        if not df_md.empty and 'mes' in df_md.columns:
            vals = df_md[df_md['mes'] == mes]
            row['conjunto_datos Cargados'] = int(vals['conjunto_datos'].sum()) if not vals.empty else 0
        else:
            row['conjunto_datos Cargados'] = 0
        rows_resumen.append(row)

    if not rows_resumen:
        rows_resumen = [{'Mes': '', 'Indicadores Unicos': 0, 'Cargas Series': 0,
                         'Registros Procesados': 0, 'conjunto_datos Cargados': 0}]
    df_resumen = pd.DataFrame(rows_resumen)

    # --- Hoja 2: Indicadores por Mes ---
    det_ind = list(
        CargaSerieIndicador.objects.filter(
            fecha_carga__gte=inicio_12m,
            indicador__isnull=False
        ).annotate(mes=TruncMonth('fecha_carga')).values(
            'mes', 'indicador__codigo_indicador', 'indicador__nombre', 'indicador__responsable'
        ).annotate(
            cargas=Count('id'),
            registros_procesados=Sum('registros_procesados'),
            registros_exitosos=Sum('registros_exitosos')
        ).order_by('mes', 'indicador__nombre')
    )

    rows_ind = []
    for r in det_ind:
        rows_ind.append({
            'Mes': r['mes'].strftime('%Y-%m') if r['mes'] else '',
            'Codigo Indicador': r['indicador__codigo_indicador'] or 'SIN-CODIGO',
            'Nombre Indicador': r['indicador__nombre'],
            '1.1 Entidad o Institucion Responsable': r['indicador__responsable'] or '',
            'Cargas': r['cargas'],
            'Registros Procesados': r['registros_procesados'] or 0,
            'Registros Exitosos': r['registros_exitosos'] or 0,
        })
    df_det_ind = pd.DataFrame(rows_ind) if rows_ind else pd.DataFrame(
        columns=['Mes', 'Codigo Indicador', 'Nombre Indicador',
                 '1.1 Entidad o Institucion Responsable', 'Cargas',
                 'Registros Procesados', 'Registros Exitosos']
    )

    # --- Hoja 3: conjunto_datos por Mes ---
    det_md = list(
        CargaConjuntoDatos.objects.filter(
            fecha_carga__gte=inicio_12m,
            conjunto_datos__isnull=False
        ).annotate(mes=TruncMonth('fecha_carga')).values(
            'mes', 'conjunto_datos__nombre'
        ).annotate(cargas=Count('id')).order_by('mes', 'conjunto_datos__nombre')
    )

    rows_md = []
    for r in det_md:
        rows_md.append({
            'Mes': r['mes'].strftime('%Y-%m') if r['mes'] else '',
            'Nombre conjunto_datos': r['conjunto_datos__nombre'],
            'Cargas': r['cargas'],
        })
    df_det_md = pd.DataFrame(rows_md) if rows_md else pd.DataFrame(
        columns=['Mes', 'Nombre conjunto_datos', 'Cargas']
    )

    # --- Generar Excel ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_resumen.to_excel(writer, sheet_name='Resumen Mensual', index=False)
        df_det_ind.to_excel(writer, sheet_name='Indicadores por Mes', index=False)
        df_det_md.to_excel(writer, sheet_name='conjunto_datos por Mes', index=False)

    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"produccion_mensual_{hoy.strftime('%Y%m%d')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# =============================================================================
# REPORTE DE VISITAS A PÁGINAS
# =============================================================================

@consultor_reportes_required
def reportes_visitas(request):
    """
    Reporte de visitas a páginas del sitio.
    Muestra estadísticas agregadas y permite filtrar por rango de fechas.
    """
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta
    from .models import PageVisit

    hoy = timezone.now()

    # Filtros GET
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')

    # Rango por defecto: últimos 30 días
    if not fecha_desde:
        fecha_desde = (hoy - timedelta(days=30)).strftime('%Y-%m-%d')
    if not fecha_hasta:
        fecha_hasta = hoy.strftime('%Y-%m-%d')

    qs = PageVisit.objects.all()
    try:
        qs = qs.filter(timestamp__date__gte=fecha_desde, timestamp__date__lte=fecha_hasta)
    except Exception:
        pass

    # Totales por categoría (pagina / api / mcp) antes del filtro
    totales_categoria = {
        r['categoria']: r['n'] for r in
        qs.values('categoria').annotate(n=Count('id'))
    }

    # Filtro opcional por categoría
    categoria = request.GET.get('categoria', '')
    categorias_validas = {c.value for c in PageVisit.Categoria}
    if categoria in categorias_validas:
        qs = qs.filter(categoria=categoria)
    else:
        categoria = ''

    # Totales del período filtrado
    total_visitas = qs.count()
    visitantes_unicos = qs.values('ip_address').distinct().count()

    # Top páginas
    top_paginas = (
        qs.values('path')
        .annotate(visitas=Count('id'))
        .order_by('-visitas')[:20]
    )

    # Visitas por día
    visitas_por_dia_raw = list(
        qs.extra(select={'dia': "DATE(timestamp)"})
        .values('dia')
        .annotate(visitas=Count('id'), unicos=Count('ip_address', distinct=True))
        .order_by('dia')
    )
    # Convertir objetos date a strings para JSON serialization
    visitas_por_dia = []
    for row in visitas_por_dia_raw:
        dia_val = row['dia']
        if hasattr(dia_val, 'strftime'):
            dia_val = dia_val.strftime('%Y-%m-%d')
        visitas_por_dia.append({
            'dia': dia_val,
            'visitas': row['visitas'],
            'unicos': row['unicos'],
        })

    # Visitas recientes (últimas 50)
    visitas_recientes = (
        PageVisit.objects.select_related('user')
        .order_by('-timestamp')[:50]
    )

    # Comparación con período anterior (mismo rango)
    try:
        desde_dt = datetime.strptime(fecha_desde, '%Y-%m-%d')
        hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d')
        dias_rango = (hasta_dt - desde_dt).days + 1
        prev_desde = (desde_dt - timedelta(days=dias_rango)).strftime('%Y-%m-%d')
        prev_hasta = (desde_dt - timedelta(days=1)).strftime('%Y-%m-%d')
        prev_total = PageVisit.objects.filter(
            timestamp__date__gte=prev_desde, timestamp__date__lte=prev_hasta
        ).count()
    except Exception:
        prev_total = None

    import json
    context = {
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'categoria': categoria,
        'totales_categoria': totales_categoria,
        'total_visitas': total_visitas,
        'visitantes_unicos': visitantes_unicos,
        'top_paginas': list(top_paginas),
        'visitas_por_dia': json.dumps(visitas_por_dia),
        'visitas_recientes': visitas_recientes,
        'prev_total': prev_total,
    }
    return render(request, 'reportes/visitas.html', context)


@consultor_reportes_required
def reportes_visitas_exportar_excel(request):
    """
    Exporta los datos de visitas a un archivo Excel (.xlsx).
    Incluye 3 hojas: resumen diario, top páginas, visitas detalladas.
    Respeta los filtros de fecha del dashboard (GET params).
    """
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta
    from .models import PageVisit

    hoy = timezone.now()
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')

    if not fecha_desde:
        fecha_desde = (hoy - timedelta(days=30)).strftime('%Y-%m-%d')
    if not fecha_hasta:
        fecha_hasta = hoy.strftime('%Y-%m-%d')

    qs = PageVisit.objects.all()
    try:
        qs = qs.filter(timestamp__date__gte=fecha_desde, timestamp__date__lte=fecha_hasta)
    except Exception:
        pass

    categoria = request.GET.get('categoria', '')
    if categoria in {c.value for c in PageVisit.Categoria}:
        qs = qs.filter(categoria=categoria)

    # Hoja 1: Resumen diario
    visitas_por_dia_raw = list(
        qs.extra(select={'dia': "DATE(timestamp)"})
        .values('dia')
        .annotate(visitas=Count('id'), unicos=Count('ip_address', distinct=True))
        .order_by('dia')
    )
    for row in visitas_por_dia_raw:
        dia_val = row['dia']
        if hasattr(dia_val, 'strftime'):
            row['dia'] = dia_val.strftime('%Y-%m-%d')

    df_dia = pd.DataFrame(visitas_por_dia_raw) if visitas_por_dia_raw else pd.DataFrame(
        columns=['dia', 'visitas', 'unicos']
    )
    df_dia.columns = ['Fecha', 'Total Visitas', 'Visitantes Unicos']

    # Hoja 2: Top páginas
    top_paginas = list(
        qs.values('path')
        .annotate(visitas=Count('id'))
        .order_by('-visitas')
    )
    df_top = pd.DataFrame(top_paginas) if top_paginas else pd.DataFrame(columns=['path', 'visitas'])
    df_top.columns = ['Pagina', 'Visitas']

    # Hoja 3: Detalle completo de visitas
    visitas_detalle = qs.select_related('user').values(
        'timestamp', 'categoria', 'path', 'ip_address', 'user__username', 'user_agent', 'referer'
    )
    df_detalle = pd.DataFrame(visitas_detalle) if visitas_detalle else pd.DataFrame(
        columns=['timestamp', 'categoria', 'path', 'ip_address', 'user__username', 'user_agent', 'referer']
    )
    df_detalle.columns = ['Fecha/Hora', 'Categoria', 'Pagina', 'IP', 'Usuario', 'User Agent', 'Referer']

    # Convertir datetimes timezone-aware a naive (Excel no soporta tz)
    if not df_detalle.empty:
        df_detalle['Fecha/Hora'] = pd.to_datetime(df_detalle['Fecha/Hora']).dt.tz_localize(None)

    # Generar Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_dia.to_excel(writer, sheet_name='Resumen Diario', index=False)
        df_top.to_excel(writer, sheet_name='Top Paginas', index=False)
        df_detalle.to_excel(writer, sheet_name='Detalle Visitas', index=False)

        # Auto-ajustar anchos de columna en cada hoja
        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        max_length = max(max_length, len(str(cell.value)))
                    except Exception:
                        pass
                adjusted_width = min(max_length + 2, 50)
                ws.column_dimensions[column].width = adjusted_width

    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="visitas_{fecha_desde}_a_{fecha_hasta}.xlsx"'
    )
    return response
