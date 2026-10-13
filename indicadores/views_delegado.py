"""
Portal del Delegado de Organismo — Estándar APT (A Prueba de Tontos).
Soporta cargas parciales e incrementales:
  Serie: datos + metadata (pueden subirse por separado o juntos)
  conjunto_datos: conjuntos_datos + metadata de variables (pueden subirse por separado o juntos)
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Q
from django.core.files.base import ContentFile
from django.core.paginator import Paginator

import os
import logging
import pandas as pd
from io import BytesIO

logger = logging.getLogger(__name__)

from .models import (
    PerfilRecolector, CargaSerieIndicador, CargaConjuntoDatos,
    Indicador, ConjuntoDatos, EquipoOrganismo,
    Organismo, Suborganismo, OperacionEstadistica
)
from .decorators import delegado_required

_EXT_VALIDAS = ('.xlsx', '.xls', '.csv')


# ============================================================================
# HELPERS INTERNOS
# ============================================================================

def _get_organismo(request):
    if hasattr(request.user, 'perfil_recolector'):
        return request.user.perfil_recolector.organismo
    return None


def _get_indicadores(request, organismo):
    if organismo:
        return Indicador.objects.filter(
            organismo_responsable=organismo, activo=True
        ).order_by('codigo_indicador')
    return Indicador.objects.filter(activo=True).order_by('codigo_indicador')


def _get_conjunto_datoss(request, organismo):
    if organismo:
        return ConjuntoDatos.objects.filter(
            indicadores__organismo_responsable=organismo
        ).distinct().order_by('nombre')
    return ConjuntoDatos.objects.all().order_by('nombre')


# ============================================================================
# AUTENTICACIÓN
# ============================================================================

def delegado_login(request):
    """Login exclusivo para delegados de organismos."""
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('indicadores:delegado_dashboard')
        if hasattr(request.user, 'perfil_recolector'):
            if request.user.perfil_recolector.es_delegado():
                return redirect('indicadores:delegado_dashboard')
        auth_logout(request)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_staff or (
                hasattr(user, 'perfil_recolector') and
                user.perfil_recolector.es_delegado()
            ):
                auth_login(request, user)
                nombre = user.get_full_name() or user.username
                messages.success(request, f'Bienvenido/a, {nombre}')
                return redirect('indicadores:delegado_dashboard')
            else:
                messages.error(
                    request,
                    'Tu cuenta no tiene permisos para este portal. '
                    'Contacta al equipo del SIIED si crees que es un error.'
                )
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'delegado/login.html')


def delegado_logout(request):
    auth_logout(request)
    messages.success(request, 'Sesión cerrada correctamente.')
    return redirect('indicadores:delegado_login')


# ============================================================================
# DASHBOARD PRINCIPAL
# ============================================================================

@delegado_required
def delegado_dashboard(request):
    """Panel principal del delegado: muestra sus indicadores y estado de cargas."""
    organismo = None
    indicadores = Indicador.objects.none()

    if hasattr(request.user, 'perfil_recolector'):
        organismo = request.user.perfil_recolector.organismo
        if organismo:
            indicadores = Indicador.objects.filter(
                organismo_responsable=organismo, activo=True
            ).order_by('codigo_indicador')

    # Estadísticas de cargas del usuario
    mis_series = CargaSerieIndicador.objects.filter(
        usuario=request.user, es_carga_delegado=True
    ).select_related('indicador').order_by('-fecha_carga')

    mis_conjunto_datos = CargaConjuntoDatos.objects.filter(
        usuario=request.user, es_carga_delegado=True
    ).select_related('conjunto_datos').order_by('-fecha_carga')

    stats = {
        'total_indicadores': indicadores.count(),
        'series_borrador': mis_series.filter(estado='borrador').count(),
        'series_pendientes': mis_series.filter(estado__in=['enviado', 'en_revision']).count(),
        'series_aprobadas': mis_series.filter(estado='aprobado').count(),
        'series_rechazadas': mis_series.filter(estado__in=['rechazado', 'correcciones_solicitadas']).count(),
        'conjunto_datos_borrador': mis_conjunto_datos.filter(estado='borrador').count(),
        'conjunto_datos_pendientes': mis_conjunto_datos.filter(estado__in=['enviado', 'en_revision']).count(),
        'conjunto_datos_aprobadas': mis_conjunto_datos.filter(estado='aprobado').count(),
        'conjunto_datos_rechazadas': mis_conjunto_datos.filter(estado__in=['rechazado', 'correcciones_solicitadas']).count(),
    }

    # Alertas: cargas con correcciones solicitadas (requieren acción)
    alertas = list(
        mis_series.filter(estado='correcciones_solicitadas')[:5]
    ) + list(
        mis_conjunto_datos.filter(estado='correcciones_solicitadas')[:5]
    )

    # FICED: Formulario de Capacidad Estadística Distrital
    ficed = None
    if organismo:
        from .models_iced import ICEDFormulario
        periodo_actual = str(timezone.now().year)
        ficed = ICEDFormulario.objects.filter(
            organismo=organismo,
            periodo=periodo_actual
        ).first()

    context = {
        'organismo': organismo,
        'indicadores': indicadores[:10],
        'total_indicadores': indicadores.count(),
        'ultimas_series': mis_series[:5],
        'ultimos_conjuntos_datos': mis_conjunto_datos[:5],
        'stats': stats,
        'alertas': alertas,
        'ficed': ficed,
        'periodo_actual': str(timezone.now().year),
    }
    return render(request, 'delegado/dashboard.html', context)


# ============================================================================
# MIS INDICADORES
# ============================================================================

@delegado_required
def delegado_mis_indicadores(request):
    """Lista todos los indicadores del organismo del delegado."""
    organismo = None
    indicadores = Indicador.objects.none()

    if hasattr(request.user, 'perfil_recolector'):
        organismo = request.user.perfil_recolector.organismo

    if organismo:
        indicadores = Indicador.objects.filter(
            organismo_responsable=organismo, activo=True
        ).prefetch_related('cargas_series').order_by('codigo_indicador')
    elif request.user.is_staff:
        indicadores = Indicador.objects.filter(activo=True).order_by('codigo_indicador')

    # Agregar estado de última carga a cada indicador
    indicadores_con_estado = []
    now = timezone.now()
    periodicidad_dias = {
        'diaria': 1,
        'semanal': 7,
        'quincenal': 15,
        'mensual': 30,
        'bimestral': 60,
        'trimestral': 90,
        'cuatrimestral': 120,
        'semestral': 180,
        'anual': 365,
        'bianual': 730,
    }
    for ind in indicadores:
        ultima_serie = CargaSerieIndicador.objects.filter(
            indicador=ind, usuario=request.user, es_carga_delegado=True
        ).order_by('-fecha_carga').first()

        desactualizado = False
        dias_desde_ultima = None
        if ultima_serie:
            dias_desde_ultima = (now - ultima_serie.fecha_carga).days
            periodo_dias = periodicidad_dias.get(
                (ind.frecuencia_difusion or '').lower().strip(), 365
            )
            if dias_desde_ultima > periodo_dias * 1.5:
                desactualizado = True

        indicadores_con_estado.append({
            'indicador': ind,
            'ultima_carga': ultima_serie,
            'estado': ultima_serie.estado if ultima_serie else None,
            'desactualizado': desactualizado,
            'dias_desde_ultima': dias_desde_ultima,
        })

    context = {
        'organismo': organismo,
        'indicadores_con_estado': indicadores_con_estado,
    }
    return render(request, 'delegado/mis_indicadores.html', context)


# ============================================================================
# CARGAR SERIE DE INDICADOR
# ============================================================================

@delegado_required
def delegado_cargar_serie(request):
    """
    Formulario de carga de serie de indicador.
    Soporta cargas PARCIALES: el delegado puede subir solo los datos,
    solo la metadata, o ambos a la vez. Puede completar la carga más tarde.
    """
    organismo = _get_organismo(request)
    indicadores = _get_indicadores(request, organismo)
    indicador_pre = request.GET.get('indicador')
    indicador_obj = None
    dominios_headers = []
    datos_rows = []
    if indicador_pre:
        try:
            indicador_obj = Indicador.objects.prefetch_related(
                'dominios_desagregacion_geografica', 'dominios_desagregacion_tematica'
            ).get(id=indicador_pre, activo=True)
            dominios_geo = list(indicador_obj.dominios_desagregacion_geografica.all())
            dominios_tem = list(indicador_obj.dominios_desagregacion_tematica.all())
            dominios_headers = dominios_geo + dominios_tem

            def _desags_del_dominio_para_indicador(dominio):
                """Desagregaciones que el indicador usa realmente en sus Dato.
                Si el indicador aún no tiene datos, cae a todas las del dominio
                como referencia para orientar la carga del delegado."""
                usados = list(
                    dominio.desagregaciones.filter(
                        datos_tematicos__indicador=indicador_obj
                    ) | dominio.desagregaciones.filter(
                        datos_geograficos__indicador=indicador_obj
                    )
                )
                if not usados:
                    usados = list(dominio.desagregaciones.all())
                return usados

            dominios_geo_info = []
            for d in dominios_geo:
                desag_list = _desags_del_dominio_para_indicador(d)
                dominios_geo_info.append({
                    'nombre': d.nombre,
                    'desagregaciones': [des.nombre for des in desag_list[:10]],
                    'total': len(desag_list),
                })
            dominios_tem_info = []
            for d in dominios_tem:
                desag_list = _desags_del_dominio_para_indicador(d)
                dominios_tem_info.append({
                    'nombre': d.nombre,
                    'desagregaciones': [des.nombre for des in desag_list[:10]],
                    'total': len(desag_list),
                })

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

    if request.method == 'POST':
        indicador_id = request.POST.get('indicador_id')
        archivo_datos = request.FILES.get('archivo_datos')
        archivo_metadata = request.FILES.get('archivo_metadata')
        accion = request.POST.get('accion', 'borrador')

        errores = []
        if not indicador_id:
            errores.append('Debes seleccionar un indicador.')
        if not archivo_datos and not archivo_metadata:
            errores.append('Debes subir al menos un archivo (datos o metadata).')
        if archivo_datos and not archivo_datos.name.lower().endswith(_EXT_VALIDAS):
            errores.append('El archivo de datos debe ser Excel (.xlsx, .xls) o CSV (.csv).')
        if archivo_metadata and not archivo_metadata.name.lower().endswith(_EXT_VALIDAS):
            errores.append('El archivo de metadata debe ser Excel (.xlsx, .xls) o CSV (.csv).')

        # Si quiere enviar, debe tener ambos archivos
        if accion == 'enviar' and (not archivo_datos or not archivo_metadata):
            errores.append(
                'Para enviar a validación necesitas subir AMBOS archivos: '
                'datos y metadata. Si aún no tienes alguno, guarda como borrador.'
            )

        if errores:
            for e in errores:
                messages.error(request, e)
            return render(request, 'delegado/cargar_serie.html', {
                'indicadores': indicadores, 'organismo': organismo,
            })

        try:
            indicador = get_object_or_404(Indicador, id=indicador_id)
            estado_inicial = 'enviado' if accion == 'enviar' else 'borrador'

            kwargs = {
                'usuario': request.user,
                'indicador': indicador,
                'estado': estado_inicial,
                'es_carga_delegado': True,
            }
            if archivo_datos:
                kwargs['archivo_datos_xlsx'] = archivo_datos
            if archivo_metadata:
                kwargs['archivo_metadata_xlsx'] = archivo_metadata

            carga = CargaSerieIndicador(**kwargs)
            carga.save()
            _convertir_serie_a_csv(carga)

            if accion == 'enviar':
                from .notifications import notificar_validadores_nueva_carga_serie
                resultado = notificar_validadores_nueva_carga_serie(carga)
                if resultado:
                    messages.info(request, '✉️ Se notificó a los validadores por correo.')
                else:
                    messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los validadores.')
                messages.success(
                    request,
                    f'Carga enviada para validación. Código: {carga.codigo_evidencia}. '
                    f'El equipo del SIIED la revisará en los próximos días.'
                )
            else:
                partes = []
                if archivo_datos: partes.append('datos')
                if archivo_metadata: partes.append('metadata')
                faltante = 'metadata' if not archivo_metadata else ('datos' if not archivo_datos else None)
                msg = f'Borrador guardado ({", ".join(partes)}). Código: {carga.codigo_evidencia}.'
                if faltante:
                    msg += f' Recuerda subir el archivo de {faltante} para poder enviarlo.'
                messages.info(request, msg)

            return redirect('indicadores:delegado_detalle_serie', carga_id=carga.id)

        except Exception as e:
            messages.error(request, f'Error al guardar: {str(e)}')

    return render(request, 'delegado/cargar_serie.html', {
        'indicadores': indicadores, 'organismo': organismo,
        'indicador_pre': indicador_pre,
        'indicador_obj': indicador_obj,
        'dominios_headers': dominios_headers,
        'datos_rows': datos_rows,
        'dominios_geo_info': dominios_geo_info if indicador_pre else [],
        'dominios_tem_info': dominios_tem_info if indicador_pre else [],
    })


@delegado_required
def delegado_completar_serie(request, carga_id):
    """
    Permite agregar archivos faltantes a una carga de serie existente.
    Caso: el delegado subió solo datos primero, ahora agrega la metadata.
    """
    carga = get_object_or_404(CargaSerieIndicador, id=carga_id, usuario=request.user)

    if carga.estado not in ('borrador', 'rechazado', 'correcciones_solicitadas'):
        messages.error(request, 'Esta carga no puede modificarse en su estado actual.')
        return redirect('indicadores:delegado_detalle_serie', carga_id=carga.id)

    if request.method == 'POST':
        archivo_datos = request.FILES.get('archivo_datos')
        archivo_metadata = request.FILES.get('archivo_metadata')
        accion = request.POST.get('accion', 'guardar')
        cambios = False

        errores = []
        if archivo_datos and not archivo_datos.name.lower().endswith(_EXT_VALIDAS):
            errores.append('El archivo de datos debe ser Excel (.xlsx, .xls) o CSV (.csv).')
        if archivo_metadata and not archivo_metadata.name.lower().endswith(_EXT_VALIDAS):
            errores.append('El archivo de metadata debe ser Excel (.xlsx, .xls) o CSV (.csv).')
        if not archivo_datos and not archivo_metadata:
            errores.append('Selecciona al menos un archivo para actualizar.')

        if accion == 'enviar':
            tiene_datos_final = bool(archivo_datos) or carga.tiene_datos
            tiene_meta_final = bool(archivo_metadata) or carga.tiene_metadata
            if not tiene_datos_final or not tiene_meta_final:
                errores.append(
                    'Para enviar necesitas tener ambos archivos. '
                    'Faltan: ' + (
                        'datos' if not tiene_datos_final else 'metadata'
                    )
                )

        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            if archivo_datos:
                carga.archivo_datos_xlsx = archivo_datos
                carga.archivo_datos_csv = None
                cambios = True
            if archivo_metadata:
                carga.archivo_metadata_xlsx = archivo_metadata
                carga.archivo_metadata_csv = None
                cambios = True
            if accion == 'enviar':
                carga.estado = 'enviado'
                carga.observaciones_validador = None
            if cambios:
                carga.save()
                _convertir_serie_a_csv(carga)
            if accion == 'enviar':
                from .notifications import notificar_validadores_nueva_carga_serie
                resultado = notificar_validadores_nueva_carga_serie(carga)
                if resultado:
                    messages.info(request, '✉️ Se notificó a los validadores por correo.')
                else:
                    messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los validadores.')
            messages.success(
                request,
                'Archivos actualizados.' +
                (' Carga enviada para validación.' if accion == 'enviar' else '')
            )
            return redirect('indicadores:delegado_detalle_serie', carga_id=carga.id)

    return render(request, 'delegado/completar_serie.html', {
        'carga': carga,
    })


def _convertir_serie_a_csv(carga):
    """Convierte los archivos disponibles (xlsx/xls/csv) de una carga de serie a CSV (para vista previa)."""
    from .views_recoleccion import _leer_archivo_datos
    try:
        if carga.tiene_datos:
            df_datos = _leer_archivo_datos(carga.archivo_datos_xlsx.path)
            buf = BytesIO()
            df_datos.to_csv(buf, index=False, encoding='utf-8', sep=';')
            buf.seek(0)
            carga.archivo_datos_csv.save(
                f"datos_{carga.codigo_evidencia}.csv",
                ContentFile(buf.read()), save=False
            )
            carga.registros_procesados = len(df_datos)

        if carga.tiene_metadata:
            df_meta = _leer_archivo_datos(carga.archivo_metadata_xlsx.path)
            buf2 = BytesIO()
            df_meta.to_csv(buf2, index=False, encoding='utf-8', sep=';')
            buf2.seek(0)
            carga.archivo_metadata_csv.save(
                f"metadata_{carga.codigo_evidencia}.csv",
                ContentFile(buf2.read()), save=False
            )
        carga.save(update_fields=[
            'archivo_datos_csv', 'archivo_metadata_csv', 'registros_procesados'
        ])
    except Exception:
        logger.exception(
            'Error convirtiendo carga de serie %s a CSV (delegado)', carga.codigo_evidencia
        )


# ============================================================================
# CARGAR MICRODATA
# ============================================================================

@delegado_required
def delegado_cargar_conjunto_datos(request):
    """
    Formulario de carga de conjunto_datos.
    Soporta dos tipos: nueva creación (desde indicadores) y actualización (conjunto_datos existente).
    """
    organismo = _get_organismo(request)
    conjuntos_datos = _get_conjunto_datoss(request, organismo)

    if request.method == 'POST':
        tipo_carga = request.POST.get('tipo_carga', 'nueva')
        archivo_micro = request.FILES.get('archivo_conjunto_datos')
        archivo_vars = request.FILES.get('archivo_metadata_variables')
        accion = request.POST.get('accion', 'borrador')

        # Validaciones comunes
        errores = []
        if not archivo_micro and not archivo_vars:
            errores.append('Debes subir al menos un archivo (conjuntos_datos o metadata de variables).')
        if archivo_micro and not archivo_micro.name.lower().endswith(_EXT_VALIDAS):
            errores.append('El archivo de conjuntos_datos debe ser Excel (.xlsx, .xls) o CSV (.csv).')
        if archivo_vars and not archivo_vars.name.lower().endswith(_EXT_VALIDAS):
            errores.append('El archivo de metadata de variables debe ser Excel (.xlsx, .xls) o CSV (.csv).')
        if accion == 'enviar' and (not archivo_micro or not archivo_vars):
            errores.append(
                'Para enviar a validación necesitas AMBOS archivos: '
                'conjuntos_datos y metadata de variables. Si aún no tienes alguno, guarda como borrador.'
            )

        # Validaciones específicas según tipo de carga
        if tipo_carga == 'nueva':
            indicadores_ids = request.POST.get('indicadores_ids', '').strip()
            if not indicadores_ids:
                errores.append('Para crear nueva conjunto_datos debes ingresar IDs de indicadores relacionados.')
            else:
                # Validar IDs de indicadores
                try:
                    ids_list = [int(id.strip()) for id in indicadores_ids.split(',') if id.strip()]
                    if not ids_list:
                        raise ValueError("No se ingresaron IDs válidos")
                    
                    # Verificar que los indicadores existan
                    from .models import Indicador
                    indicadores_existentes = Indicador.objects.filter(id__in=ids_list)
                    if indicadores_existentes.count() != len(ids_list):
                        ids_no_encontrados = set(ids_list) - set(indicadores_existentes.values_list('id', flat=True))
                        errores.append(f'Los siguientes IDs de indicadores no existen: {", ".join(map(str, ids_no_encontrados))}')
                        
                except ValueError:
                    errores.append('Error en los IDs de indicadores. Use números separados por comas.')
        else:  # tipo_carga == 'actualizacion'
            conjunto_datos_id = request.POST.get('conjunto_datos_id')
            if not conjunto_datos_id:
                errores.append('Para actualizar conjunto_datos debes seleccionar un conjunto existente.')

        if errores:
            for e in errores:
                messages.error(request, e)
            return render(request, 'delegado/cargar_conjunto_datos.html', {
                'conjuntos_datos': conjuntos_datos, 'organismo': organismo,
            })

        try:
            estado_inicial = 'enviado' if accion == 'enviar' else 'borrador'
            kwargs = {
                'usuario': request.user,
                'estado': estado_inicial,
                'es_carga_delegado': True,
            }
            
            if archivo_micro:
                kwargs['archivo_microdata_xlsx'] = archivo_micro
            if archivo_vars:
                kwargs['archivo_metadata_variables_xlsx'] = archivo_vars
            
            # Asociar según tipo de carga
            if tipo_carga == 'nueva':
                # Sin asociar a conjunto_datos existente (se creará en validación)
                kwargs['conjunto_datos'] = None
                carga = CargaConjuntoDatos(**kwargs)
                carga.save()
                # Guardar IDs de indicadores en log
                carga.log_procesamiento = f"Indicadores relacionados: {indicadores_ids}"
                carga.save()
            else:
                # Asociar a conjunto_datos existente
                conjunto_datos_obj = get_object_or_404(ConjuntoDatos, id=conjunto_datos_id)
                kwargs['conjunto_datos'] = conjunto_datos_obj
                carga = CargaConjuntoDatos(**kwargs)
                carga.save()
                # Guardar referencia en log
                carga.log_procesamiento = f"Actualización de conjunto_datos existente: {conjunto_datos_obj.nombre} (ID: {conjunto_datos_id})"
                carga.save()
            
            _convertir_conjunto_datos_a_csv(carga)

            if accion == 'enviar':
                from .notifications import notificar_validadores_nueva_carga_conjunto_datos
                resultado = notificar_validadores_nueva_carga_conjunto_datos(carga)
                if resultado:
                    messages.info(request, '✉️ Se notificó a los validadores por correo.')
                else:
                    messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los validadores.')
                messages.success(
                    request,
                    f'Carga enviada para validación. Código: {carga.codigo_evidencia}.'
                )
            else:
                partes = []
                if archivo_micro: partes.append('conjuntos_datos')
                if archivo_vars: partes.append('metadata de variables')
                faltante = 'metadata de variables' if not archivo_vars else ('conjuntos_datos' if not archivo_micro else None)
                msg = f'Borrador guardado ({", ".join(partes)}). Código: {carga.codigo_evidencia}.'
                if faltante:
                    msg += f' Recuerda subir {faltante} para poder enviarlo.'
                messages.info(request, msg)

            return redirect('indicadores:delegado_detalle_conjunto_datos', carga_id=carga.id)

        except Exception as e:
            messages.error(request, f'Error al guardar: {str(e)}')

    indicadores = _get_indicadores(request, organismo)
    return render(request, 'delegado/cargar_conjunto_datos.html', {
        'conjuntos_datos': conjuntos_datos, 'organismo': organismo,
        'indicadores': indicadores,
    })


@delegado_required
def delegado_completar_conjunto_datos(request, carga_id):
    """
    Permite agregar archivos faltantes a una carga de conjunto_datos existente.
    Caso: el delegado subió conjuntos_datos primero, ahora agrega metadata de variables.
    """
    carga = get_object_or_404(CargaConjuntoDatos, id=carga_id, usuario=request.user)

    if carga.estado not in ('borrador', 'rechazado', 'correcciones_solicitadas'):
        messages.error(request, 'Esta carga no puede modificarse en su estado actual.')
        return redirect('indicadores:delegado_detalle_conjunto_datos', carga_id=carga.id)

    if request.method == 'POST':
        archivo_micro = request.FILES.get('archivo_conjunto_datos')
        archivo_vars = request.FILES.get('archivo_metadata_variables')
        accion = request.POST.get('accion', 'guardar')
        cambios = False

        errores = []
        if archivo_micro and not archivo_micro.name.lower().endswith(_EXT_VALIDAS):
            errores.append('El archivo de conjuntos_datos debe ser Excel (.xlsx, .xls) o CSV (.csv).')
        if archivo_vars and not archivo_vars.name.lower().endswith(_EXT_VALIDAS):
            errores.append('El archivo de metadata debe ser Excel (.xlsx, .xls) o CSV (.csv).')
        if not archivo_micro and not archivo_vars:
            errores.append('Selecciona al menos un archivo para actualizar.')

        if accion == 'enviar':
            tiene_micro_final = bool(archivo_micro) or carga.tiene_conjunto_datos
            tiene_vars_final = bool(archivo_vars) or carga.tiene_metadata_variables
            if not tiene_micro_final or not tiene_vars_final:
                errores.append(
                    'Para enviar necesitas ambos archivos. Falta: ' +
                    ('conjuntos_datos' if not tiene_micro_final else 'metadata de variables')
                )

        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            if archivo_micro:
                carga.archivo_microdata_xlsx = archivo_micro
                carga.archivo_microdata_csv = None
                cambios = True
            if archivo_vars:
                carga.archivo_metadata_variables_xlsx = archivo_vars
                carga.archivo_metadata_variables_csv = None
                cambios = True
            if accion == 'enviar':
                carga.estado = 'enviado'
                carga.observaciones_validador = None
            if cambios:
                carga.save()
                _convertir_conjunto_datos_a_csv(carga)
            if accion == 'enviar':
                from .notifications import notificar_validadores_nueva_carga_conjunto_datos
                resultado = notificar_validadores_nueva_carga_conjunto_datos(carga)
                if resultado:
                    messages.info(request, '✉️ Se notificó a los validadores por correo.')
                else:
                    messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los validadores.')
            messages.success(
                request,
                'Archivos actualizados.' +
                (' Carga enviada para validación.' if accion == 'enviar' else '')
            )
            return redirect('indicadores:delegado_detalle_conjunto_datos', carga_id=carga.id)

    return render(request, 'delegado/completar_conjunto_datos.html', {'carga': carga})


def _convertir_conjunto_datos_a_csv(carga):
    """Convierte los archivos disponibles (xlsx/xls/csv) de una carga de conjunto_datos a CSV."""
    from .views_recoleccion import _leer_archivo_datos
    try:
        if carga.tiene_conjunto_datos:
            df = _leer_archivo_datos(carga.archivo_microdata_xlsx.path)
            buf = BytesIO()
            df.to_csv(buf, index=False, encoding='utf-8', sep=';')
            buf.seek(0)
            carga.archivo_microdata_csv.save(
                f"conjunto_datos_{carga.codigo_evidencia}.csv",
                ContentFile(buf.read()), save=False
            )
            carga.registros_procesados = len(df)

        if carga.tiene_metadata_variables:
            df_vars = _leer_archivo_datos(carga.archivo_metadata_variables_xlsx.path)
            buf2 = BytesIO()
            df_vars.to_csv(buf2, index=False, encoding='utf-8', sep=';')
            buf2.seek(0)
            carga.archivo_metadata_variables_csv.save(
                f"metadata_vars_{carga.codigo_evidencia}.csv",
                ContentFile(buf2.read()), save=False
            )
        carga.save(update_fields=[
            'archivo_microdata_csv', 'archivo_metadata_variables_csv', 'registros_procesados'
        ])
    except Exception:
        logger.exception(
            'Error convirtiendo carga de conjunto_datos %s a CSV (delegado)', carga.codigo_evidencia
        )


# ============================================================================
# HISTORIAL Y DETALLE
# ============================================================================

@delegado_required
def delegado_historial(request):
    """Vista del historial completo de cargas del delegado."""
    mis_series = CargaSerieIndicador.objects.filter(
        usuario=request.user, es_carga_delegado=True
    ).select_related('indicador').order_by('-fecha_carga')

    mis_conjunto_datos = CargaConjuntoDatos.objects.filter(
        usuario=request.user, es_carga_delegado=True
    ).select_related('conjunto_datos').order_by('-fecha_carga')

    # Filtros opcionales
    filtro_tipo = request.GET.get('tipo', 'todos')
    filtro_estado = request.GET.get('estado', 'todos')

    if filtro_estado != 'todos':
        mis_series = mis_series.filter(estado=filtro_estado)
        mis_conjunto_datos = mis_conjunto_datos.filter(estado=filtro_estado)

    # Paginación combinada: paginar series y conjunto_datos por separado
    series_paginator = Paginator(mis_series, 25)
    conjunto_datos_paginator = Paginator(mis_conjunto_datos, 25)
    page_number = request.GET.get('page')
    mis_series_page = series_paginator.get_page(page_number)
    mis_conjunto_datos_page = conjunto_datos_paginator.get_page(page_number)

    context = {
        'mis_series': mis_series_page,
        'mis_conjunto_datos': mis_conjunto_datos_page,
        'series_page_obj': mis_series_page,
        'conjunto_datos_page_obj': mis_conjunto_datos_page,
        'filtro_tipo': filtro_tipo,
        'filtro_estado': filtro_estado,
        'estados_disponibles': CargaSerieIndicador.ESTADO_CHOICES,
    }
    return render(request, 'delegado/historial.html', context)


@delegado_required
def delegado_detalle_serie(request, carga_id):
    """Detalle de una carga de serie: estado, archivos, observaciones del validador."""
    carga = get_object_or_404(
        CargaSerieIndicador, id=carga_id, usuario=request.user
    )

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'enviar' and carga.estado in ('borrador', 'rechazado', 'correcciones_solicitadas'):
            if not carga.esta_completa:
                messages.error(
                    request,
                    'No puedes enviar: faltan archivos. '
                    + ('Falta el archivo de datos. ' if not carga.tiene_datos else '')
                    + ('Falta el archivo de metadata.' if not carga.tiene_metadata else '')
                )
            else:
                carga.estado = 'enviado'
                carga.observaciones_validador = None
                carga.save()
                from .notifications import notificar_validadores_nueva_carga_serie
                resultado = notificar_validadores_nueva_carga_serie(carga)
                if resultado:
                    messages.info(request, '✉️ Se notificó a los validadores por correo.')
                else:
                    messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los validadores.')
                messages.success(request, 'Carga enviada para validación correctamente.')
                return redirect('indicadores:delegado_detalle_serie', carga_id=carga.id)

    preview_datos = _leer_preview_csv(carga.archivo_datos_csv)
    preview_metadata = _leer_preview_csv(carga.archivo_metadata_csv)

    context = {
        'carga': carga,
        'preview_datos': preview_datos,
        'preview_metadata': preview_metadata,
        'puede_enviar': carga.esta_completa and carga.estado in ('borrador', 'rechazado', 'correcciones_solicitadas'),
        'puede_completar': not carga.esta_completa and carga.estado in ('borrador', 'rechazado', 'correcciones_solicitadas'),
    }
    return render(request, 'delegado/detalle_serie.html', context)


@delegado_required
def delegado_detalle_conjunto_datos(request, carga_id):
    """Detalle de una carga de conjunto_datos."""
    carga = get_object_or_404(
        CargaConjuntoDatos, id=carga_id, usuario=request.user
    )

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'enviar' and carga.estado in ('borrador', 'rechazado', 'correcciones_solicitadas'):
            if not carga.esta_completa:
                messages.error(
                    request,
                    'No puedes enviar: faltan archivos. '
                    + ('Falta el archivo de conjuntos_datos. ' if not carga.tiene_conjunto_datos else '')
                    + ('Falta el archivo de metadata de variables.' if not carga.tiene_metadata_variables else '')
                )
            else:
                carga.estado = 'enviado'
                carga.observaciones_validador = None
                carga.save()
                from .notifications import notificar_validadores_nueva_carga_conjunto_datos
                resultado = notificar_validadores_nueva_carga_conjunto_datos(carga)
                if resultado:
                    messages.info(request, '✉️ Se notificó a los validadores por correo.')
                else:
                    messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los validadores.')
                messages.success(request, 'Carga enviada para validación correctamente.')
                return redirect('indicadores:delegado_detalle_conjunto_datos', carga_id=carga.id)

    preview_datos = _leer_preview_csv(carga.archivo_microdata_csv)
    preview_vars = _leer_preview_csv(carga.archivo_metadata_variables_csv)

    context = {
        'carga': carga,
        'preview_datos': preview_datos,
        'preview_vars': preview_vars,
        'puede_enviar': carga.esta_completa and carga.estado in ('borrador', 'rechazado', 'correcciones_solicitadas'),
        'puede_completar': not carga.esta_completa and carga.estado in ('borrador', 'rechazado', 'correcciones_solicitadas'),
    }
    return render(request, 'delegado/detalle_conjunto_datos.html', context)


def _leer_preview_csv(archivo_field, max_rows=10):
    """Lee las primeras filas de un CSV para mostrar vista previa."""
    if not archivo_field or not archivo_field.name:
        return None
    try:
        if os.path.exists(archivo_field.path):
            df = pd.read_csv(archivo_field.path, nrows=max_rows, sep=';')
            return {
                'columnas': list(df.columns),
                'filas': df.values.tolist(),
                'total_cols': len(df.columns),
            }
    except Exception:
        pass
    return None


# ============================================================================
# MANUAL Y PLANTILLAS
# ============================================================================

@delegado_required
def delegado_manual(request):
    """Mini manual APT (A Prueba de Tontos) para el portal de organismos."""
    return render(request, 'delegado/manual.html')


@delegado_required
def delegado_plantillas(request):
    """Página de descarga de plantillas de formatos Excel."""
    return render(request, 'delegado/plantillas.html')


# ============================================================================
# INGRESO INLINE — PORTAL DELEGADO
# (Misma lógica que recolección; resultado pasa por validación)
# ============================================================================

@delegado_required
def delegado_cargar_serie_inline(request):
    """
    Ingreso de datos de una serie mediante tabla inline (sin xlsx).
    Genera el xlsx en memoria; la carga queda en borrador/enviado y pasa
    por el módulo de validación antes de llegar al wizard.

    Si se pasa ?indicador_id=ID, precarga los datos existentes (solo visual).
    """
    from .views_recoleccion import _generar_xlsx_datos, procesar_serie_indicador as _procesar_serie
    from io import BytesIO
    from django.core.files.base import ContentFile

    organismo = _get_organismo(request)
    indicadores = _get_indicadores(request, organismo)

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
        accion = request.POST.get('accion', 'borrador')
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
            return render(request, 'delegado/cargar_serie_inline.html', {
                'indicadores': indicadores, 'organismo': organismo,
                'indicador_pre': indicador_pre,
                'datos_existentes': datos_existentes,
                'desagregaciones_pre': desagregaciones_pre,
            })

        try:
            indicador = get_object_or_404(Indicador, id=indicador_id)
            buf = _generar_xlsx_datos(filas, desagregaciones=desagregaciones)
            estado_inicial = 'enviado' if accion == 'enviar' else 'borrador'

            carga = CargaSerieIndicador(
                usuario=request.user,
                indicador=indicador,
                estado=estado_inicial,
                es_carga_delegado=True,
            )
            carga.archivo_datos_xlsx.save(
                f'datos_inline_{indicador.codigo_indicador}_{timezone.now().strftime("%Y%m%d%H%M%S")}.xlsx',
                ContentFile(buf.read()), save=False
            )
            carga.save()
            _procesar_serie(carga)

            if accion == 'enviar':
                from .notifications import notificar_validadores_nueva_carga_serie
                resultado = notificar_validadores_nueva_carga_serie(carga)
                if resultado:
                    messages.info(request, '✉️ Se notificó a los validadores por correo.')
                else:
                    messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los validadores.')
                messages.success(
                    request,
                    f'✅ {len(filas)} datos enviados para validación. Código: {carga.codigo_evidencia}'
                )
            else:
                messages.info(
                    request,
                    f'Borrador guardado ({len(filas)} datos). Código: {carga.codigo_evidencia}'
                )
            return redirect('indicadores:delegado_detalle_serie', carga_id=carga.id)

        except Exception as e:
            messages.error(request, f'Error al guardar: {str(e)}')

    return render(request, 'delegado/cargar_serie_inline.html', {
        'indicadores': indicadores, 'organismo': organismo,
        'indicador_pre': indicador_pre,
        'datos_existentes': datos_existentes,
        'desagregaciones_pre': desagregaciones_pre,
    })


@delegado_required
def delegado_cargar_metadata_form(request):
    """
    Ingresa la metadata de un indicador mediante formulario (sin xlsx).
    Puede adjuntarse a una carga de serie existente o crear una carga de solo metadata.
    La carga pasa por el módulo de validación.
    """
    from .views_recoleccion import (
        _generar_xlsx_metadata_indicador,
        procesar_serie_indicador as _procesar_serie,
        _crear_o_actualizar_conjunto_datos_desde_variables,
    )
    from io import BytesIO
    from django.core.files.base import ContentFile

    organismo = _get_organismo(request)
    indicadores = _get_indicadores(request, organismo)
    cargas_pendientes = CargaSerieIndicador.objects.filter(
        usuario=request.user,
        estado__in=['borrador', 'correcciones_solicitadas'],
        archivo_metadata_xlsx=''
    ).order_by('-fecha_carga')[:20]

    suborganismos_pre = []
    if organismo:
        suborganismos_pre = list(Suborganismo.objects.filter(
            organismo=organismo, activo=True
        ).values('id', 'nombre').order_by('orden', 'nombre'))

    indicador_id_get = request.GET.get('indicador_id')
    indicador_pre = None
    metadata_pre = {}

    if indicador_id_get:
        try:
            indicador_pre = Indicador.objects.select_related(
                'subtema__tema__dominio', 'organismo_responsable', 'suborganismo'
            ).get(id=indicador_id_get, activo=True)
            i = indicador_pre
            metadata_pre = {
                'Grupo_Indicador': i.grupo_indicador or '',
                'Dominio': i.subtema.tema.dominio.nombre if i.subtema and i.subtema.tema and i.subtema.tema.dominio else '',
                'Tema': i.subtema.tema.nombre if i.subtema and i.subtema.tema else '',
                'Subtema': i.subtema.nombre if i.subtema else '',
                'Codigo_Indicador': i.codigo_indicador or '',
                'Nombre_Indicador': i.nombre or '',
                'Sigla': i.sigla or '',
                'Descripcion_Indicador': i.descripcion_indicador or '',
                'Objetivo': i.objetivo or '',
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
                'Entidad_Institucion': i.organismo_responsable.nombre if i.organismo_responsable else '',
                'Area_Dependencia': i.suborganismo.nombre if i.suborganismo else '',
                'Comentarios_Adicionales': i.comentarios_adicionales or '',
                'Referencias': i.referencias or '',
                'Equipo_Responsable': i.equipo_responsable.nombre if i.equipo_responsable else '',
                'Nombre_Responsable_Validacion': i.nombre_responsable_validacion or '',
                'Cargo_Responsable_Validacion': i.cargo_responsable_validacion or '',
                'Correo_Responsable_Validacion': i.correo_responsable_validacion or '',
                'Celular_Responsable_Validacion': i.celular_responsable_validacion or '',
                'Fecha_Elaboracion': str(i.fecha_elaboracion) if i.fecha_elaboracion else '',
                'Fecha_Actualizacion': str(i.fecha_actualizacion_ficha) if i.fecha_actualizacion_ficha else '',
                'Fecha_Publicacion_Metadatos': str(i.fecha_publicacion_metadatos) if i.fecha_publicacion_metadatos else '',
                'Correo_Contacto': i.correo_contacto or (i.organismo_responsable.email_contacto if i.organismo_responsable else '') or '',
                'Telefono_Contacto': i.telefono_contacto or '',
                'Nombre_Conjunto_conjunto_datos': i.nombre_conjunto_datos or '',
                'Serie_Historica_Disponible': i.serie_historica_disponible or '',
                'Frecuencia_Difusion': i.frecuencia_difusion or '',
                'Medios_Difusion': i.medios_difusion or '',
            }
        except Indicador.DoesNotExist:
            pass

    if request.method == 'POST':
        indicador_id = request.POST.get('indicador_id')
        carga_id = request.POST.get('carga_id')
        accion = request.POST.get('accion', 'borrador')

        if not indicador_id:
            messages.error(request, 'Debes seleccionar un indicador.')
            unidades_existentes = list(
                Indicador.objects.exclude(unidad_medida__isnull=True)
                .exclude(unidad_medida='')
                .values_list('unidad_medida', flat=True)
                .distinct().order_by('unidad_medida')
            )
            return render(request, 'delegado/cargar_metadata_form.html', {
                'indicadores': indicadores, 'organismo': organismo,
                'cargas_pendientes': cargas_pendientes,
                'indicador_pre': indicador_pre, 'metadata_pre': metadata_pre,
                'suborganismos_pre': suborganismos_pre,
                'unidades_existentes': unidades_existentes,
            })

        indicador = get_object_or_404(Indicador, id=indicador_id)
        campos = [
            'Grupo_Indicador', 'Dominio', 'Tema', 'Subtema',
            'Codigo_Indicador', 'Nombre_Indicador', 'Sigla',
            'Descripcion_Indicador', 'Objetivo',
            'Metodo_Medicion', 'Formula', 'Variables',
            'Unidad_Medida',
            'Nomenclaturas_Clasificaciones',
            'Alcance_Tematico', 'Poblacion_Objetivo',
            'Cobertura_Geografica', 'Periodo_Referencia', 'Periodo_Base',
            'Fuente_Datos', 'Operacion_Estadistica', 'Entidad_Responsable',
            'Entidad_Institucion', 'Area_Dependencia',
            'Comentarios_Adicionales',
            'Fecha_Publicacion_Metadatos',
            'Fecha_Elaboracion', 'Fecha_Actualizacion',
            'Correo_Contacto', 'Telefono_Contacto',
            'Nombre_Conjunto_conjunto_datos',
            'Serie_Historica_Disponible', 'Frecuencia_Difusion', 'Medios_Difusion',
            'Referencias', 'Equipo_Responsable',
            'Nombre_Responsable_Validacion', 'Cargo_Responsable_Validacion',
            'Correo_Responsable_Validacion', 'Celular_Responsable_Validacion',
        ]
        data = {c: request.POST.get(c, '') for c in campos}

        # Completar claves institucionales para el xlsx antes de generarlo
        data['Entidad_Institucion'] = organismo.nombre if organismo else ''
        data['Entidad_Responsable'] = organismo.nombre if organismo else ''
        sub_id_pre = request.POST.get('suborganismo_id')
        if sub_id_pre:
            try:
                data['Area_Dependencia'] = Suborganismo.objects.get(
                    id=sub_id_pre, activo=True).nombre
            except Suborganismo.DoesNotExist:
                pass

        buf = _generar_xlsx_metadata_indicador(data)
        nombre_archivo = f'metadata_{indicador.codigo_indicador}_{timezone.now().strftime("%Y%m%d%H%M%S")}.xlsx'

        # Actualizar suborganismo
        suborganismo_id_post = request.POST.get('suborganismo_id')
        if suborganismo_id_post and organismo:
            try:
                indicador.suborganismo = Suborganismo.objects.get(
                    id=suborganismo_id_post, organismo=organismo, activo=True
                )
            except Suborganismo.DoesNotExist:
                pass

        # Actualizar organismo si aún no tiene
        if organismo and not indicador.organismo_responsable:
            indicador.organismo_responsable = organismo

        # Actualizar indicador con campos MSD
        indicador.variables = data.get('Variables', '')
        indicador.descripcion_indicador = data.get('Descripcion_Indicador', '')
        indicador.objetivo = data.get('Objetivo', '')
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
        indicador.correo_contacto = data.get('Correo_Contacto', '')
        indicador.telefono_contacto = data.get('Telefono_Contacto', '')
        indicador.nombre_conjunto_datos = data.get('Nombre_Conjunto_conjunto_datos', '')

        # Entidad responsable (1.1): se deriva del organismo del delegado
        if organismo:
            indicador.entidad_responsable = organismo.nombre
        # Completar claves institucionales para el xlsx
        data['Entidad_Institucion'] = organismo.nombre if organismo else ''
        data['Entidad_Responsable'] = organismo.nombre if organismo else ''
        if indicador.suborganismo:
            data['Area_Dependencia'] = indicador.suborganismo.nombre

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
                if accion == 'enviar' and carga.tiene_datos:
                    carga.estado = 'enviado'
                carga.save()
                if accion == 'enviar' and carga.tiene_datos:
                    from .notifications import notificar_validadores_nueva_carga_serie
                    resultado = notificar_validadores_nueva_carga_serie(carga)
                    if resultado:
                        messages.info(request, '✉️ Se notificó a los validadores por correo.')
                    else:
                        messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los validadores.')
            else:
                estado_inicial = 'enviado' if accion == 'enviar' else 'borrador'
                carga = CargaSerieIndicador(
                    usuario=request.user,
                    indicador=indicador,
                    estado=estado_inicial,
                    es_carga_delegado=True,
                )
                carga.archivo_metadata_xlsx.save(nombre_archivo, ContentFile(buf.read()), save=False)
                carga.save()
                _procesar_serie(carga)
                if accion == 'enviar':
                    from .notifications import notificar_validadores_nueva_carga_serie
                    resultado = notificar_validadores_nueva_carga_serie(carga)
                    if resultado:
                        messages.info(request, '✉️ Se notificó a los validadores por correo.')
                    else:
                        messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los validadores.')

            messages.success(request, f'✅ Metadata guardada. Código: {carga.codigo_evidencia}')
            return redirect('indicadores:delegado_detalle_serie', carga_id=carga.id)

        except Exception as e:
            messages.error(request, f'Error al guardar metadata: {str(e)}')

    unidades_existentes = list(
        Indicador.objects.exclude(unidad_medida__isnull=True)
        .exclude(unidad_medida='')
        .values_list('unidad_medida', flat=True)
        .distinct().order_by('unidad_medida')
    )

    return render(request, 'delegado/cargar_metadata_form.html', {
        'indicadores': indicadores,
        'organismo': organismo,
        'cargas_pendientes': cargas_pendientes,
        'indicador_pre': indicador_pre,
        'metadata_pre': metadata_pre,
        'suborganismos_pre': suborganismos_pre,
        'unidades_existentes': unidades_existentes,
    })


@delegado_required
def delegado_cargar_variables_form(request):
    """
    Ingresa metadata de variables de conjunto_datos mediante tabla inline (sin xlsx).
    Puede adjuntarse a una carga de conjunto_datos existente.

    Si se pasa ?conjunto_datos_id=ID, precarga las variables existentes.
    """
    from .views_recoleccion import _generar_xlsx_variables
    from io import BytesIO
    from django.core.files.base import ContentFile

    organismo = _get_organismo(request)
    conjuntos_datos = _get_conjunto_datoss(request, organismo)
    cargas_sin_variables = CargaConjuntoDatos.objects.filter(
        usuario=request.user,
        es_carga_delegado=True,
        estado__in=['borrador', 'correcciones_solicitadas'],
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
                'observaciones'
            ))
            for v in variables_pre:
                v['organismo_productor'] = v.pop('organismo_productor__nombre') or v.pop('organismo_productor_legado') or ''
        except ConjuntoDatos.DoesNotExist:
            pass

    if request.method == 'POST':
        carga_id = request.POST.get('carga_id')
        conjunto_datos_id = request.POST.get('conjunto_datos_id')
        accion = request.POST.get('accion', 'borrador')

        codigos = request.POST.getlist('Codigo_Variable[]')
        nombres = request.POST.getlist('Nombre_Variable[]')
        definiciones = request.POST.getlist('Definicion_Conceptual[]')
        tipos = request.POST.getlist('Tipo_Dato[]')
        unidades = request.POST.getlist('Unidad_Medida[]')
        periodicidades = request.POST.getlist('Periodicidad[]')
        fuentes = request.POST.getlist('Fuente_Datos[]')
        organismos_prod = request.POST.getlist('Organismo_Productor[]')
        referencias_list = request.POST.getlist('Referencias[]')
        observaciones = request.POST.getlist('Observaciones[]')

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
                        f'Como delegado solo puedes actualizar variables previamente '
                        f'creadas desde la metadata del indicador. Códigos válidos: '
                        f'{", ".join(sorted(codigos_existentes))}'
                    )
                    return render(request, 'delegado/cargar_variables_form.html', {
                        'conjuntos_datos': conjuntos_datos, 'organismo': organismo,
                        'cargas_sin_variables': cargas_sin_variables,
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
                    'Organismo_Productor': organismos_prod[i] if i < len(organismos_prod) else '',
                    'Observaciones': observaciones[i] if i < len(observaciones) else '',
                    'Referencias': referencias_list[i] if i < len(referencias_list) else '',
                })

        if not filas:
            messages.error(request, 'Debes ingresar al menos una variable.')
            return render(request, 'delegado/cargar_variables_form.html', {
                'conjuntos_datos': conjuntos_datos, 'organismo': organismo,
                'cargas_sin_variables': cargas_sin_variables,
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
                    estado='enviado' if accion == 'enviar' else 'borrador',
                    es_carga_delegado=True,
                    conjunto_datos=ConjuntoDatos.objects.filter(id=conjunto_datos_id).first() if conjunto_datos_id else None,
                )
            carga.archivo_metadata_variables_xlsx.save(nombre_archivo, ContentFile(buf.read()), save=False)
            if accion == 'enviar' and carga.tiene_conjunto_datos:
                carga.estado = 'enviado'
            carga.save()
            if accion == 'enviar' and carga.tiene_conjunto_datos:
                from .notifications import notificar_validadores_nueva_carga_conjunto_datos
                resultado = notificar_validadores_nueva_carga_conjunto_datos(carga)
                if resultado:
                    messages.info(request, '✉️ Se notificó a los validadores por correo.')
                else:
                    messages.warning(request, '⚠️ No se pudo enviar la notificación por correo a los validadores.')

            messages.success(request, f'✅ {len(filas)} variables guardadas. Código: {carga.codigo_evidencia}')
            return redirect('indicadores:delegado_detalle_conjunto_datos', carga_id=carga.id)

        except Exception as e:
            messages.error(request, f'Error al guardar variables: {str(e)}')

    return render(request, 'delegado/cargar_variables_form.html', {
        'conjuntos_datos': conjuntos_datos,
        'organismo': organismo,
        'cargas_sin_variables': cargas_sin_variables,
        'conjunto_datos_pre': conjunto_datos_pre,
        'variables_pre': variables_pre,
    })


# ============================================================================
# FICED — Formulario de Capacidad Estadística Distrital
# ============================================================================

@delegado_required
def delegado_ficed(request):
    """
    Redirige al formulario FICED del organismo del delegado.
    Solo permite un formulario por organismo por período.
    """
    organismo = _get_organismo(request)
    if not organismo:
        messages.error(request, 'No tienes un organismo asignado.')
        return redirect('indicadores:delegado_dashboard')

    from .models_iced import ICEDFormulario
    periodo_actual = str(timezone.now().year)

    # Un FICED por equipo técnico (subrol_ficed); '' = formulario completo
    equipo = getattr(
        getattr(request.user, 'perfil_recolector', None), 'subrol_ficed', ''
    ) or ''

    # Buscar formulario existente del equipo
    ficed = ICEDFormulario.objects.filter(
        organismo=organismo,
        periodo=periodo_actual,
        equipo=equipo,
    ).first()

    if ficed:
        if ficed.estado in ('enviado', 'validado'):
            # Ya enviado o validado → mostrar resultado
            return redirect('indicadores:iced_resultado', formulario_id=ficed.id)
        else:
            # En borrador → retomar
            return redirect('indicadores:iced_formulario_retomar', formulario_id=ficed.id)
    else:
        # No existe → crear nuevo
        return redirect('indicadores:iced_formulario_nuevo')


# ============================================================================
# DESCUBRIMIENTO — Actualizar indicadores/conjunto_datos existentes
# ============================================================================

@delegado_required
def delegado_actualizar_existente(request):
    """
    Permite al delegado buscar indicadores o conjunto_datos de su organismo
    para actualizarlos mediante los formularios inline.
    """
    organismo = _get_organismo(request)
    q = request.GET.get('q', '').strip()

    indicadores = _get_indicadores(request, organismo)
    conjuntos_datos = _get_conjunto_datoss(request, organismo)

    if q:
        indicadores = indicadores.filter(
            Q(nombre__icontains=q) | Q(codigo_indicador__icontains=q)
        )
        conjuntos_datos = conjuntos_datos.filter(
            Q(nombre__icontains=q)
        )

    indicadores = indicadores.order_by('codigo_indicador')[:50]
    conjuntos_datos = conjuntos_datos.order_by('nombre')[:50]

    return render(request, 'delegado/actualizar_existente.html', {
        'indicadores': indicadores,
        'conjuntos_datos': conjuntos_datos,
        'q': q,
    })
