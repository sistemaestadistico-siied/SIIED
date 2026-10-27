"""
Panel de Validación para Estadísticos del SIIED.
Espejo del módulo de reportes pero orientado a aprobar/rechazar cargas de delegados.
"""

from django import forms
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST

import io
import json
import logging
import os
import re
import pandas as pd

logger = logging.getLogger(__name__)

from .models import (
    PerfilRecolector, CargaSerieIndicador, CargaConjuntoDatos,
    Indicador, ConjuntoDatos, VariableConjuntoDatos,
    Grafico, DocumentoVector, RegistroCambio,
    SELLO_CALIDAD_CHOICES, SELLO_NIVEL,
)
from .models_iced import ICEDFormulario, ICEDPreguntaEquipo
from .calcular_iced import (
    calcular_iced, aplicar_puntajes, _normalizar_respuestas,
    PREGUNTA_LABELS, INDICADOR_LABELS, ESTRUCTURA_ICED, INDICADOR_PREGUNTA,
)
from .forms_iced import ICED_WIZARD_FORMS, ICED_STEP_LABELS
from .templatetags.iced_tags import iced_field_label
from .decorators import validador_required, validador_sistema_required
from . import views_normalizacion as _nz


# ============================================================================
# HELPERS DE ROL / SCOPE
# ============================================================================

def _perfil(request):
    return getattr(request.user, 'perfil_recolector', None)


def _es_validador_organismo(request):
    """True si el usuario es validador del organismo (pre-validador)."""
    if request.user.is_staff:
        return False
    p = _perfil(request)
    return bool(p and p.es_validador_organismo())


def _es_validador_sistema(request):
    """True si puede dar la validación final (staff, validador, analista)."""
    if request.user.is_staff:
        return True
    p = _perfil(request)
    return bool(p and p.es_validador_sistema())


def _organismo_perfil(request):
    p = _perfil(request)
    return p.organismo if p else None


def _scope_cargas_organismo(qs, request):
    """Restringe un queryset de cargas al organismo del validador.
    El validador del organismo solo pre-valida cargas de delegados de su
    propio organismo. Sin organismo asignado, no ve nada."""
    if _es_validador_organismo(request):
        org = _organismo_perfil(request)
        if org:
            return qs.filter(usuario__perfil_recolector__organismo=org)
        return qs.none()
    return qs


def _estados_cola(request):
    """Estados que conforman la cola de trabajo según el rol.
    - Validador organismo: lo enviado/en revisión aún no decidido por él.
    - Validador SIIED: incluye lo pre-validado por los organismos."""
    if _es_validador_organismo(request):
        return ['enviado', 'en_revision']
    return ['enviado', 'en_revision', 'prevalidado']


# ============================================================================
# AUTENTICACIÓN
# ============================================================================

def validacion_login(request):
    """Login para validadores estadísticos del SIIED."""
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('indicadores:validacion_dashboard')
        if hasattr(request.user, 'perfil_recolector'):
            if request.user.perfil_recolector.es_validador():
                return redirect('indicadores:validacion_dashboard')
        auth_logout(request)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_staff or (
                hasattr(user, 'perfil_recolector') and
                user.perfil_recolector.es_validador()
            ):
                auth_login(request, user)
                messages.success(request, f'Bienvenido/a, {user.get_full_name() or user.username}')
                return redirect('indicadores:validacion_dashboard')
            else:
                messages.error(request, 'Tu cuenta no tiene permisos de validador. Contacta al administrador.')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'validacion/login.html')


def validacion_logout(request):
    auth_logout(request)
    messages.success(request, 'Sesión cerrada.')
    return redirect('indicadores:validacion_login')


# ============================================================================
# DASHBOARD
# ============================================================================

@validador_required
def validacion_dashboard(request):
    """Panel principal del validador: cargas pendientes y métricas."""
    es_org = _es_validador_organismo(request)
    estados_cola = _estados_cola(request)

    # Cargas de delegados pendientes de validación (scope por organismo
    # cuando el usuario es validador del organismo)
    series_enviadas = _scope_cargas_organismo(
        CargaSerieIndicador.objects.filter(
            es_carga_delegado=True,
            estado__in=estados_cola
        ), request
    ).select_related('usuario', 'indicador', 'usuario__perfil_recolector__organismo').order_by('fecha_carga')

    conjunto_datos_enviadas = _scope_cargas_organismo(
        CargaConjuntoDatos.objects.filter(
            es_carga_delegado=True,
            estado__in=estados_cola
        ), request
    ).select_related('usuario', 'conjunto_datos', 'usuario__perfil_recolector__organismo').order_by('fecha_carga')

    # Historial reciente de validaciones propias (decisiones o
    # pre-validaciones hechas por este usuario)
    mis_validaciones_series = CargaSerieIndicador.objects.filter(
        Q(validado_por=request.user) | Q(prevalidado_por=request.user),
        es_carga_delegado=True
    ).order_by('-fecha_validacion')[:10]

    mis_validaciones_conjunto_datos = CargaConjuntoDatos.objects.filter(
        Q(validado_por=request.user) | Q(prevalidado_por=request.user),
        es_carga_delegado=True
    ).order_by('-fecha_validacion')[:10]

    # Formularios ICED: solo el equipo SIIED los valida (el validador del
    # organismo trabaja exclusivamente con indicadores y conjuntos de datos)
    iced_pendientes = []
    iced_devueltos = []
    iced_validados_recientes = []
    iced_count = 0
    if not es_org:
      try:
        iced_pendientes = list(
            ICEDFormulario.objects.filter(estado='enviado')
            .select_related('organismo', 'usuario_diligencia')
            .order_by('organismo__nombre', '-periodo', 'equipo')
        )

        # Formularios de equipo por (organismo, periodo): si el organismo
        # trabaja con equipos, el validador debe conciliar antes de decidir.
        from collections import Counter
        org_ids = {f.organismo_id for f in iced_pendientes}
        cnt_equipos = Counter(
            ICEDFormulario.objects
            .filter(organismo_id__in=org_ids)
            .exclude(equipo='')
            .values_list('organismo_id', 'periodo')
        )
        for f in iced_pendientes:
            f.n_equipos_org = cnt_equipos.get((f.organismo_id, f.periodo), 0)

        # Devueltos que el organismo aún no corrige ni reenvía
        iced_devueltos = ICEDFormulario.objects.filter(
            estado='devuelto'
        ).select_related('organismo', 'usuario_diligencia').order_by('-fecha_actualizacion')[:10]

        iced_validados_recientes = ICEDFormulario.objects.filter(
            estado='validado'
        ).select_related('organismo').order_by('-fecha_validacion')[:5]

        iced_count = len(iced_pendientes)
      except Exception:
        iced_pendientes = []
        iced_devueltos = []
        iced_validados_recientes = []
        iced_count = 0

    stats = {
        'series_pendientes': series_enviadas.count(),
        'conjunto_datos_pendientes': conjunto_datos_enviadas.count(),
        'iced_pendientes': iced_count,
        'total_pendientes': series_enviadas.count() + conjunto_datos_enviadas.count() + iced_count,
        'series_aprobadas_hoy': CargaSerieIndicador.objects.filter(
            validado_por=request.user,
            estado='aprobado',
            fecha_validacion__date=timezone.now().date()
        ).count(),
        'series_rechazadas_hoy': CargaSerieIndicador.objects.filter(
            validado_por=request.user,
            estado__in=['rechazado', 'correcciones_solicitadas'],
            fecha_validacion__date=timezone.now().date()
        ).count(),
    }

    context = {
        'series_enviadas': series_enviadas,
        'conjunto_datos_enviadas': conjunto_datos_enviadas,
        'mis_validaciones_series': mis_validaciones_series,
        'mis_validaciones_conjunto_datos': mis_validaciones_conjunto_datos,
        'iced_pendientes': iced_pendientes,
        'iced_devueltos': iced_devueltos,
        'iced_validados_recientes': iced_validados_recientes,
        'stats': stats,
        'es_validador_organismo': es_org,
        'es_validador_sistema': _es_validador_sistema(request),
        'organismo_perfil': _organismo_perfil(request),
    }
    return render(request, 'validacion/dashboard.html', context)


# ============================================================================
# REVISIÓN DE SERIES
# ============================================================================

@validador_required
def validacion_revisar_serie(request, carga_id):
    """
    Revisar una carga de serie: vista previa de datos, metadata y acciones
    (aprobar, rechazar, solicitar correcciones).
    """
    carga = get_object_or_404(
        _scope_cargas_organismo(
            CargaSerieIndicador.objects.filter(es_carga_delegado=True),
            request),
        id=carga_id,
    )

    # Marcar como en revisión al abrir (el prevalidado lo conserva hasta que
    # el SIIED decida; solo lo enviado pasa a en_revision)
    if carga.estado == 'enviado':
        carga.estado = 'en_revision'
        carga.save()

    # Toggle es_calculo_complejo vía GET rápido (AJAX-friendly) — solo equipo SIIED
    if (request.method == 'POST'
            and request.POST.get('accion') == 'toggle_calculo_complejo'
            and _es_validador_sistema(request)):
        carga.es_calculo_complejo = not carga.es_calculo_complejo
        carga.save(update_fields=['es_calculo_complejo'])
        messages.info(
            request,
            'Marcado como cálculo complejo. El wizard procesará solo la serie precalculada.' if carga.es_calculo_complejo
            else 'Desmarcado como cálculo complejo. El wizard aplicará extracción cartesiana.'
        )
        return redirect('indicadores:validacion_revisar_serie', carga_id=carga_id)

    preview_datos = _leer_preview_completo(carga.archivo_datos_csv)
    preview_metadata = _leer_preview_completo(carga.archivo_metadata_csv)

    organismo = None
    if hasattr(carga.usuario, 'perfil_recolector'):
        organismo = carga.usuario.perfil_recolector.organismo

    context = {
        'carga': carga,
        'tipo': 'serie',
        'preview_datos': preview_datos,
        'preview_metadata': preview_metadata,
        'organismo': organismo,
        'es_calculo_complejo': carga.es_calculo_complejo,
        'es_validador_organismo': _es_validador_organismo(request),
        'es_validador_sistema': _es_validador_sistema(request),
    }
    return render(request, 'validacion/revisar_carga.html', context)


@validador_required
def validacion_revisar_conjunto_datos(request, carga_id):
    """
    Revisar una carga de conjunto_datos: vista previa y acciones de validación.
    """
    carga = get_object_or_404(
        _scope_cargas_organismo(
            CargaConjuntoDatos.objects.filter(es_carga_delegado=True),
            request),
        id=carga_id,
    )

    if carga.estado == 'enviado':
        carga.estado = 'en_revision'
        carga.save()

    preview_datos = _leer_preview_completo(carga.archivo_microdata_csv)
    preview_vars = _leer_preview_completo(carga.archivo_metadata_variables_csv)

    organismo = None
    if hasattr(carga.usuario, 'perfil_recolector'):
        organismo = carga.usuario.perfil_recolector.organismo

    context = {
        'carga': carga,
        'tipo': 'conjunto_datos',
        'preview_datos': preview_datos,
        'preview_metadata': preview_vars,
        'organismo': organismo,
        'es_validador_organismo': _es_validador_organismo(request),
        'es_validador_sistema': _es_validador_sistema(request),
    }
    return render(request, 'validacion/revisar_carga.html', context)


# ============================================================================
# ACCIONES DE VALIDACIÓN (POST)
# ============================================================================

@validador_required
def validacion_decidir_serie(request, carga_id):
    """Decisión sobre una carga de serie.

    Validador del organismo: 'prevalidar' | 'correcciones' | 'rechazar'
    (primera capa; al prevalidar sube el sello del indicador a 'organismo').
    Validador SIIED/staff/analista: 'aprobar' | 'rechazar' | 'correcciones'
    (segunda capa; al aprobar sube el sello a 'sistema').
    """
    if request.method != 'POST':
        return redirect('indicadores:validacion_dashboard')

    carga = get_object_or_404(
        _scope_cargas_organismo(
            CargaSerieIndicador.objects.filter(es_carga_delegado=True),
            request),
        id=carga_id,
    )
    accion = request.POST.get('accion')
    observaciones = request.POST.get('observaciones', '').strip()
    es_org = _es_validador_organismo(request)

    if es_org:
        # ── Pre-validación del organismo ──
        if carga.estado not in ('enviado', 'en_revision'):
            messages.error(request, 'Esta carga ya no está pendiente de tu validación.')
            return redirect('indicadores:validacion_dashboard')
        if accion == 'prevalidar':
            carga.estado = 'prevalidado'
            carga.prevalidado_por = request.user
            carga.fecha_prevalidacion = timezone.now()
            carga.observaciones_prevalidador = observaciones or None
            sello_nota = ''
            if carga.indicador_id:
                if carga.indicador.metadata_completa_para_sello():
                    carga.indicador.marcar_sello('organismo', request.user)
                    sello_nota = (' la metadata del indicador recibió el sello'
                                  ' del organismo y')
                else:
                    sello_nota = (f' (la metadata del indicador tiene '
                                  f'{carga.indicador.porcentaje_completitud_metadatos()}% '
                                  f'de completitud < {carga.indicador.UMBRAL_SELLO_MIN}%: '
                                  f'no se otorgó sello)')
            msg = (f'✔️ Carga {carga.codigo_evidencia} pre-validada.'
                   f'{sello_nota} Queda pendiente la validación final del SIIED.')
            level = messages.SUCCESS
        elif accion == 'correcciones':
            if not observaciones:
                messages.error(request, 'Debes indicar qué correcciones se necesitan.')
                return redirect('indicadores:validacion_revisar_serie', carga_id=carga_id)
            carga.estado = 'correcciones_solicitadas'
            carga.observaciones_validador = observaciones
            msg = f'🔄 Correcciones solicitadas para {carga.codigo_evidencia}.'
            level = messages.INFO
        elif accion == 'rechazar':
            if not observaciones:
                messages.error(request, 'Debes explicar el motivo del rechazo.')
                return redirect('indicadores:validacion_revisar_serie', carga_id=carga_id)
            carga.estado = 'rechazado'
            carga.observaciones_validador = observaciones
            msg = f'❌ Carga {carga.codigo_evidencia} rechazada en pre-validación.'
            level = messages.WARNING
        else:
            messages.error(request, 'Acción no válida para tu rol.')
            return redirect('indicadores:validacion_revisar_serie', carga_id=carga_id)
        carga.validado_por = request.user
        carga.fecha_validacion = timezone.now()
    else:
        # ── Validación final del SIIED ──
        if accion == 'aprobar':
            carga.estado = 'aprobado'
            carga.observaciones_validador = observaciones or None
            sello_nota = ''
            if carga.indicador_id:
                if carga.indicador.metadata_completa_para_sello():
                    carga.indicador.marcar_sello('sistema', request.user)
                    sello_nota = ' Sello SIIED otorgado a la metadata del indicador.'
                else:
                    sello_nota = (f' Metadata del indicador al '
                                  f'{carga.indicador.porcentaje_completitud_metadatos()}% '
                                  f'< {carga.indicador.UMBRAL_SELLO_MIN}%: no se otorgó sello.')
            msg = f'✅ Carga {carga.codigo_evidencia} aprobada.{sello_nota}'
            level = messages.SUCCESS
        elif accion == 'rechazar':
            if not observaciones:
                messages.error(request, 'Debes explicar el motivo del rechazo.')
                return redirect('indicadores:validacion_revisar_serie', carga_id=carga_id)
            carga.estado = 'rechazado'
            carga.observaciones_validador = observaciones
            msg = f'❌ Carga {carga.codigo_evidencia} rechazada. El delegado recibirá las observaciones.'
            level = messages.WARNING
        elif accion == 'correcciones':
            if not observaciones:
                messages.error(request, 'Debes indicar qué correcciones se necesitan.')
                return redirect('indicadores:validacion_revisar_serie', carga_id=carga_id)
            carga.estado = 'correcciones_solicitadas'
            carga.observaciones_validador = observaciones
            msg = f'🔄 Se solicitaron correcciones para la carga {carga.codigo_evidencia}.'
            level = messages.INFO
        else:
            messages.error(request, 'Acción no válida.')
            return redirect('indicadores:validacion_revisar_serie', carga_id=carga_id)
        carga.validado_por = request.user
        carga.fecha_validacion = timezone.now()

    carga.save()

    # Notificar al delegado por email
    from .notifications import notificar_delegado_serie
    resultado = notificar_delegado_serie(carga, accion, observaciones)
    if resultado:
        messages.info(request, '✉️ Se notificó al delegado por correo.')
    else:
        messages.warning(request, '⚠️ No se pudo enviar la notificación por correo al delegado.')

    messages.add_message(request, level, msg)
    return redirect('indicadores:validacion_dashboard')


@validador_required
def validacion_decidir_conjunto_datos(request, carga_id):
    """Procesa la decisión del validador sobre una carga de conjunto_datos."""
    if request.method != 'POST':
        return redirect('indicadores:validacion_dashboard')

    carga = get_object_or_404(
        _scope_cargas_organismo(
            CargaConjuntoDatos.objects.filter(es_carga_delegado=True),
            request),
        id=carga_id,
    )
    accion = request.POST.get('accion')
    observaciones = request.POST.get('observaciones', '').strip()
    es_org = _es_validador_organismo(request)

    def _sellar_variables(nivel):
        """Sube el sello de las variables del conjunto al nivel dado."""
        if not carga.conjunto_datos_id:
            return
        niveles = {'organismo': ['sin_sello'], 'sistema': ['sin_sello', 'organismo']}
        carga.conjunto_datos.variables.filter(
            sello_calidad__in=niveles.get(nivel, [])
        ).update(
            sello_calidad=nivel,
            sello_otorgado_por=request.user,
            sello_fecha=timezone.now(),
        )

    if es_org:
        # ── Pre-validación del organismo ──
        if carga.estado not in ('enviado', 'en_revision'):
            messages.error(request, 'Esta carga ya no está pendiente de tu validación.')
            return redirect('indicadores:validacion_dashboard')
        if accion == 'prevalidar':
            carga.estado = 'prevalidado'
            carga.prevalidado_por = request.user
            carga.fecha_prevalidacion = timezone.now()
            carga.observaciones_prevalidador = observaciones or None
            _sellar_variables('organismo')
            msg = (f'✔️ Carga {carga.codigo_evidencia} pre-validada. '
                   'Las variables recibieron el sello del organismo y la '
                   'carga pasa a la validación final del SIIED.')
            level = messages.SUCCESS
        elif accion == 'correcciones':
            if not observaciones:
                messages.error(request, 'Debes indicar qué correcciones se necesitan.')
                return redirect('indicadores:validacion_revisar_conjunto_datos', carga_id=carga_id)
            carga.estado = 'correcciones_solicitadas'
            carga.observaciones_validador = observaciones
            msg = f'🔄 Correcciones solicitadas para la carga {carga.codigo_evidencia}.'
            level = messages.INFO
        elif accion == 'rechazar':
            if not observaciones:
                messages.error(request, 'Debes explicar el motivo del rechazo.')
                return redirect('indicadores:validacion_revisar_conjunto_datos', carga_id=carga_id)
            carga.estado = 'rechazado'
            carga.observaciones_validador = observaciones
            msg = f'❌ Carga {carga.codigo_evidencia} rechazada en pre-validación.'
            level = messages.WARNING
        else:
            messages.error(request, 'Acción no válida para tu rol.')
            return redirect('indicadores:validacion_revisar_conjunto_datos', carga_id=carga_id)
        carga.validado_por = request.user
        carga.fecha_validacion = timezone.now()
    else:
        # ── Validación final del SIIED ──
        if accion == 'aprobar':
            carga.estado = 'aprobado'
            carga.observaciones_validador = observaciones or None
            _sellar_variables('sistema')
            msg = f'✅ Carga {carga.codigo_evidencia} aprobada. Sello SIIED otorgado a las variables.'
            level = messages.SUCCESS
        elif accion == 'rechazar':
            if not observaciones:
                messages.error(request, 'Debes explicar el motivo del rechazo.')
                return redirect('indicadores:validacion_revisar_conjunto_datos', carga_id=carga_id)
            carga.estado = 'rechazado'
            carga.observaciones_validador = observaciones
            msg = f'❌ Carga {carga.codigo_evidencia} rechazada.'
            level = messages.WARNING
        elif accion == 'correcciones':
            if not observaciones:
                messages.error(request, 'Debes indicar qué correcciones se necesitan.')
                return redirect('indicadores:validacion_revisar_conjunto_datos', carga_id=carga_id)
            carga.estado = 'correcciones_solicitadas'
            carga.observaciones_validador = observaciones
            msg = f'🔄 Correcciones solicitadas para la carga {carga.codigo_evidencia}.'
            level = messages.INFO
        else:
            messages.error(request, 'Acción no válida.')
            return redirect('indicadores:validacion_revisar_conjunto_datos', carga_id=carga_id)
        carga.validado_por = request.user
        carga.fecha_validacion = timezone.now()

    carga.save()

    # Notificar al delegado por email
    from .notifications import notificar_delegado_conjunto_datos
    resultado = notificar_delegado_conjunto_datos(carga, accion, observaciones)
    if resultado:
        messages.info(request, '✉️ Se notificó al delegado por correo.')
    else:
        messages.warning(request, '⚠️ No se pudo enviar la notificación por correo al delegado.')

    messages.add_message(request, level, msg)
    return redirect('indicadores:validacion_dashboard')


# ============================================================================
# HISTORIAL DE VALIDACIONES
# ============================================================================

@validador_sistema_required
def validacion_manual(request):
    """Manual de uso del Panel de Validación."""
    return render(request, 'validacion/manual.html')


# ============================================================================
# CONCILIACIÓN DE DESAGREGACIONES — mismo wizard del admin
# (views_normalizacion) montado con los estilos del módulo.
# ============================================================================

def _nz_cfg(request):
    """El wizard compartido renderiza templates del módulo y resuelve
    sus URLs internas con los nombres de validación."""
    request._nz_tmpl = 'validacion/normalizacion/'
    request._nz_dom_url = 'indicadores:validacion_conciliacion_dominio'
    request._nz_ind_url = 'indicadores:validacion_conciliacion_indicador'
    request._nz_list_url = 'indicadores:validacion_conciliacion'


@validador_sistema_required
def validacion_conciliacion(request):
    _nz_cfg(request)
    return _nz.wizard_normalizacion.__wrapped__(request)


@validador_sistema_required
def validacion_conciliacion_manual(request):
    _nz_cfg(request)
    return _nz.wizard_manual.__wrapped__(request)


@validador_sistema_required
def validacion_conciliacion_equivalencias(request):
    _nz_cfg(request)
    return _nz.wizard_equivalencias.__wrapped__(request)


@validador_sistema_required
def validacion_conciliacion_preview(request):
    _nz_cfg(request)
    return _nz.wizard_preview.__wrapped__(request)


@validador_sistema_required
def validacion_conciliacion_aplicar(request):
    _nz_cfg(request)
    return _nz.wizard_aplicar.__wrapped__(request)


@validador_sistema_required
def validacion_conciliacion_eliminar(request):
    _nz_cfg(request)
    return _nz.wizard_eliminar_aplicar.__wrapped__(request)


@validador_sistema_required
def validacion_conciliacion_dominio(request, dominio_id):
    _nz_cfg(request)
    return _nz.wizard_dominio_detalle.__wrapped__(request, dominio_id)


@validador_sistema_required
def validacion_conciliacion_indicador(request, indicador_id):
    _nz_cfg(request)
    return _nz.wizard_indicador_detalle.__wrapped__(request, indicador_id)


@validador_required
def validacion_historial(request):
    """Historial completo de cargas validadas (todas, no solo las propias)."""
    filtro_estado = request.GET.get('estado', 'todos')
    filtro_tipo = request.GET.get('tipo', 'todos')

    es_org = _es_validador_organismo(request)

    series = _scope_cargas_organismo(
        CargaSerieIndicador.objects.filter(es_carga_delegado=True),
        request
    ).select_related(
        'usuario', 'indicador',
        'validado_por', 'usuario__perfil_recolector__organismo'
    ).order_by('-fecha_carga')

    conjunto_datos = _scope_cargas_organismo(
        CargaConjuntoDatos.objects.filter(es_carga_delegado=True),
        request
    ).select_related(
        'usuario', 'conjunto_datos',
        'validado_por', 'usuario__perfil_recolector__organismo'
    ).order_by('-fecha_carga')

    if filtro_estado != 'todos':
        series = series.filter(estado=filtro_estado)
        conjunto_datos = conjunto_datos.filter(estado=filtro_estado)

    # Métricas (del mismo scope visible para el usuario)
    base_series = _scope_cargas_organismo(
        CargaSerieIndicador.objects.filter(es_carga_delegado=True), request)
    base_conj = _scope_cargas_organismo(
        CargaConjuntoDatos.objects.filter(es_carga_delegado=True), request)
    stats = {
        'total_series': base_series.count(),
        'series_aprobadas': base_series.filter(estado='aprobado').count(),
        'series_pendientes': base_series.filter(
            estado__in=_estados_cola(request)).count(),
        'total_conjunto_datos': base_conj.count(),
        'conjunto_datos_aprobadas': base_conj.filter(estado='aprobado').count(),
    }

    context = {
        'series': series if filtro_tipo in ('todos', 'series') else CargaSerieIndicador.objects.none(),
        'conjunto_datos': conjunto_datos if filtro_tipo in ('todos', 'conjunto_datos') else CargaConjuntoDatos.objects.none(),
        'filtro_estado': filtro_estado,
        'filtro_tipo': filtro_tipo,
        'estados_disponibles': CargaSerieIndicador.ESTADO_CHOICES,
        'stats': stats,
        'es_validador_organismo': es_org,
    }
    return render(request, 'validacion/historial.html', context)


# ============================================================================
# SELLOS DE CALIDAD DE METADATOS
# La metadata se publica al instante desde cualquier vía de carga; el sello
# solo certifica el nivel de verificación. Validador del organismo → sello
# 'organismo' (solo su organismo). Validador SIIED/analista/staff → 'sistema'.
# ============================================================================

@validador_required
def validacion_sellos(request):
    """Panel de sellos de calidad sobre metadata publicada.

    Lista indicadores y variables con su sello actual. El validador del
    organismo solo ve los elementos de su propio organismo."""
    es_org = _es_validador_organismo(request)
    org = _organismo_perfil(request)

    if es_org and not org:
        messages.error(
            request,
            'Tu perfil de validador de organismo no tiene un organismo '
            'asignado. Contacta al administrador.')
        return redirect('indicadores:validacion_dashboard')

    filtro_sello = request.GET.get('sello', 'todos')
    q = (request.GET.get('q') or '').strip()

    indicadores = Indicador.objects.filter(activo=True).select_related(
        'organismo_responsable', 'sello_otorgado_por', 'subtema__tema__dominio'
    ).order_by('nombre')
    variables = VariableConjuntoDatos.objects.select_related(
        'conjunto_datos', 'organismo_productor', 'sello_otorgado_por'
    ).prefetch_related(
        'conjunto_datos__indicadores__subtema__tema__dominio',
    ).order_by('conjunto_datos__nombre', 'orden', 'codigo_variable')

    if es_org:
        indicadores = indicadores.filter(organismo_responsable=org)
        variables = variables.filter(organismo_productor=org)

    if filtro_sello != 'todos':
        indicadores = indicadores.filter(sello_calidad=filtro_sello)
        variables = variables.filter(sello_calidad=filtro_sello)

    if q:
        indicadores = indicadores.filter(
            Q(nombre__icontains=q) | Q(codigo_indicador__icontains=q)
            | Q(sigla__icontains=q))
        variables = variables.filter(
            Q(nombre_variable__icontains=q)
            | Q(codigo_variable__icontains=q)
            | Q(conjunto_datos__nombre__icontains=q))

    # Gate de completitud: indicadores con < UMBRAL_SELLO_MIN% de
    # metadata no se muestran para validar (sello).
    aptos = []
    for ind in indicadores:
        ind.pct_metadatos = ind.porcentaje_completitud_metadatos()
        if ind.pct_metadatos >= Indicador.UMBRAL_SELLO_MIN:
            aptos.append(ind)

    # Agrupación dominio → tema → subtema (como en reportes) para
    # desplegables en el panel. Los sin subtema quedan aparte.
    def _sort_key(obj):
        if obj is None:
            return (9999, 'zzzz')
        return (getattr(obj, 'orden', 9999) or 9999, obj.nombre or '')

    grupos = {}
    for ind in aptos:
        st = ind.subtema
        tm = st.tema if st else None
        dm = tm.dominio if tm else None
        grupos.setdefault(dm, {}).setdefault(tm, {}).setdefault(st, []).append(ind)

    grupos_indicadores = []
    for dm, temas_map in sorted(grupos.items(), key=lambda kv: _sort_key(kv[0])):
        temas = []
        n_dm = 0
        for tm, subs_map in sorted(temas_map.items(), key=lambda kv: _sort_key(kv[0])):
            subs = []
            n_tm = 0
            for st, inds in sorted(subs_map.items(), key=lambda kv: _sort_key(kv[0])):
                subs.append({'subtema': st, 'indicadores': inds, 'n': len(inds)})
                n_tm += len(inds)
            temas.append({'tema': tm, 'subtemas': subs, 'n': n_tm})
            n_dm += n_tm
        grupos_indicadores.append({'dominio': dm, 'temas': temas, 'n': n_dm})

    # Variables de conjuntos: agrupación dominio → tema → subtema → conjunto,
    # ubicando cada conjunto por su primer indicador (como el explorador de
    # conjuntos de datos). Cada variable lleva su índice de completitud.
    grupos_var = {}
    for var in variables:
        var.pct_metadatos = var.porcentaje_completitud_metadatos()
        conj = var.conjunto_datos
        ind0 = None
        if conj is not None:
            inds = list(conj.indicadores.all())  # prefetch, sin consulta extra
            ind0 = inds[0] if inds else None
        st = ind0.subtema if ind0 else None
        tm = st.tema if st else None
        dm = tm.dominio if tm else None
        grupos_var.setdefault(dm, {}).setdefault(tm, {}).setdefault(
            st, {}).setdefault(conj, []).append(var)

    grupos_variables = []
    n_variables = 0
    for dm, temas_map in sorted(grupos_var.items(), key=lambda kv: _sort_key(kv[0])):
        temas = []
        n_dm = 0
        for tm, subs_map in sorted(temas_map.items(), key=lambda kv: _sort_key(kv[0])):
            subs = []
            n_tm = 0
            for st, conjs_map in sorted(subs_map.items(), key=lambda kv: _sort_key(kv[0])):
                conjs = []
                n_st = 0
                for conj, vs in sorted(conjs_map.items(), key=lambda kv: _sort_key(kv[0])):
                    conjs.append({'conjunto': conj, 'variables': vs, 'n': len(vs)})
                    n_st += len(vs)
                subs.append({'subtema': st, 'conjuntos': conjs, 'n': n_st})
                n_tm += n_st
            temas.append({'tema': tm, 'subtemas': subs, 'n': n_tm})
            n_dm += n_tm
        grupos_variables.append({'dominio': dm, 'temas': temas, 'n': n_dm})
        n_variables += n_dm

    context = {
        'grupos_indicadores': grupos_indicadores,
        'grupos_variables': grupos_variables,
        'n_indicadores': len(aptos),
        'n_variables': n_variables,
        'filtro_sello': filtro_sello,
        'q': q,
        'sello_choices': SELLO_CALIDAD_CHOICES,
        'umbral_sello_min': Indicador.UMBRAL_SELLO_MIN,
        'es_validador_organismo': es_org,
        'es_validador_sistema': _es_validador_sistema(request),
        'nivel_otorgable': 'organismo' if es_org else 'sistema',
        'organismo_perfil': org,
    }
    return render(request, 'validacion/sellos.html', context)


@validador_required
@require_POST
def validacion_sello_otorgar(request, tipo, pk):
    """Otorga el sello del nivel que corresponde al rol.

    tipo: 'indicador' | 'variable' | 'conjunto' (todas sus variables).
    El sello solo sube de nivel; nunca baja por esta vía."""
    es_org = _es_validador_organismo(request)
    org = _organismo_perfil(request)
    nivel = 'organismo' if es_org else 'sistema'

    if es_org and not org:
        messages.error(request, 'Tu perfil no tiene organismo asignado.')
        return redirect('indicadores:validacion_sellos')

    if tipo == 'indicador':
        obj = get_object_or_404(Indicador, pk=pk)
        if es_org and obj.organismo_responsable_id != org.id:
            messages.error(
                request,
                'Solo puedes sellar indicadores de tu propio organismo.')
            return redirect('indicadores:validacion_sellos')
        pct = obj.porcentaje_completitud_metadatos()
        if pct < obj.UMBRAL_SELLO_MIN:
            messages.error(
                request,
                f'No se puede validar "{obj.nombre[:60]}": su metadata está al '
                f'{pct}% de completitud y el mínimo para sellar es '
                f'{obj.UMBRAL_SELLO_MIN}%. Completa la ficha técnica primero.')
            return redirect('indicadores:validacion_sellos')
        cambio = obj.marcar_sello(nivel, request.user)
        if cambio:
            messages.success(
                request,
                f'Sello {nivel} otorgado al indicador "{obj.nombre[:60]}".')
        else:
            messages.info(
                request,
                'El indicador ya tiene un sello igual o superior.')

    elif tipo == 'variable':
        obj = get_object_or_404(
            VariableConjuntoDatos.objects.select_related('organismo_productor'),
            pk=pk)
        if es_org and obj.organismo_productor_id != org.id:
            messages.error(
                request,
                'Solo puedes sellar variables de tu propio organismo.')
            return redirect('indicadores:validacion_sellos')
        cambio = obj.marcar_sello(nivel, request.user)
        if cambio:
            messages.success(
                request,
                f'Sello {nivel} otorgado a la variable '
                f'"{obj.codigo_variable} — {obj.nombre_variable[:50]}".')
        else:
            messages.info(
                request,
                'La variable ya tiene un sello igual o superior.')

    elif tipo == 'conjunto':
        conjunto = get_object_or_404(ConjuntoDatos, pk=pk)
        qs = conjunto.variables.all()
        if es_org:
            qs = qs.filter(organismo_productor=org)
        ahora = timezone.now()
        if es_org:
            n = qs.filter(sello_calidad='sin_sello').update(
                sello_calidad='organismo',
                sello_otorgado_por=request.user, sello_fecha=ahora)
        else:
            n = qs.exclude(sello_calidad='sistema').update(
                sello_calidad='sistema',
                sello_otorgado_por=request.user, sello_fecha=ahora)
        if n:
            messages.success(
                request,
                f'Sello {nivel} otorgado a {n} variable(s) de '
                f'"{conjunto.nombre[:60]}".')
        else:
            messages.info(
                request,
                'Ninguna variable del conjunto requería subir de sello.')
    else:
        messages.error(request, 'Tipo de elemento no válido.')

    return redirect(request.POST.get('next') or 'indicadores:validacion_sellos')


# ============================================================================
# HELPERS
# ============================================================================

def _leer_preview_completo(archivo_field, max_rows=50):
    """Lee un CSV para vista previa en el panel de validación."""
    if not archivo_field or not archivo_field.name:
        return None
    try:
        import os
        if os.path.exists(archivo_field.path):
            df = pd.read_csv(archivo_field.path, nrows=max_rows)
            return {
                'columnas': list(df.columns),
                'filas': df.fillna('').values.tolist(),
                'total_cols': len(df.columns),
                'total_filas': len(df),
            }
    except Exception:
        pass
    return None


# ============================================================================
# REVISIÓN DE FORMULARIOS ICED
# ============================================================================

def _vacio(valor):
    """Una respuesta guardada que no aporta información."""
    return valor is None or valor == '' or valor == [] or valor == {}


def _campo_captura_dato(field):
    """
    True si el campo del formulario del wizard captura un dato real.
    Excluye textos informativos (intro/header: readonly o disabled) y
    los HiddenInput pelados sin attrs (separadores/secciones como
    p21_hw_header). iced_widget() y los campos JSON llevan attrs
    (data-iced-widget, data-config, class iced-json-field) → capturan.
    """
    attrs = getattr(field.widget, 'attrs', {}) or {}
    if 'readonly' in attrs or 'disabled' in attrs:
        return False
    if isinstance(field.widget, forms.HiddenInput):
        return bool(attrs)
    return True


# Dimension puntuable alimentada por cada modulo del cuestionario ICED
# (A solo identifica; B->1 Entorno, C->2 Infraestructura,
#  D->3 Metodologia, E->4 Accesibilidad)
DIM_POR_MODULO = {'b': '1', 'c': '2', 'd': '3', 'e': '4'}


@validador_sistema_required
def validacion_revisar_iced(request, formulario_id):
    """
    Revisar un formulario ICED: puntajes calculados en preview,
    respuestas reales por pregunta, y acciones (aprobar/devolver).
    """
    formulario = get_object_or_404(ICEDFormulario, pk=formulario_id)

    # Calcular puntajes en preview (sin persistir)
    resultado = calcular_iced(formulario)

    # Respuestas normalizadas por módulo (para mostrar al validador)
    resp_a = _normalizar_respuestas(formulario.respuestas_a)
    resp_b = _normalizar_respuestas(formulario.respuestas_b)
    resp_c = _normalizar_respuestas(formulario.respuestas_c)
    resp_d = _normalizar_respuestas(formulario.respuestas_d)
    resp_e = _normalizar_respuestas(formulario.respuestas_e)
    modulos = {'b': resp_b, 'c': resp_c, 'd': resp_d, 'e': resp_e}

    # Enriquecer el detalle con indicadores individuales y respuestas reales
    detalle = resultado.get('detalle', {})
    indicadores = resultado.get('indicadores', {})
    # Tracking de respuestas compartidas: un mismo campo puede alimentar
    # indicadores de varias dimensiones (ej. P23 -> 3.1.x y 4.1.4)
    ocurrencias = {}
    for dim_key, dim in detalle.items():
        for sub_key, sub in dim.get('subdimensiones', {}).items():
            sub_estructura = ESTRUCTURA_ICED.get(dim_key, {}).get('subdimensiones', {}).get(sub_key, {})
            ind_keys = sub_estructura.get('indicadores', [])

            # Indicadores detalle (score + label)
            indicadores_detalle = {}
            # Preguntas detalle (respuesta real del organismo)
            preguntas_detalle = {}
            seen_fields = set()

            for ind_key in ind_keys:
                score = indicadores.get(ind_key, 0)
                indicadores_detalle[ind_key] = {
                    'score': score,
                    'label': INDICADOR_LABELS.get(ind_key, ind_key),
                }

                # Enlazar indicador con su pregunta y respuesta real
                pregunta_info = INDICADOR_PREGUNTA.get(ind_key)
                if not pregunta_info:
                    continue
                preg_id, field_key, modulo = pregunta_info
                ocurrencias.setdefault(field_key, []).append((dim_key, ind_key))
                if field_key in seen_fields:
                    continue
                seen_fields.add(field_key)

                preg_label, _ = PREGUNTA_LABELS.get(preg_id, (preg_id, field_key))
                respuesta = modulos.get(modulo, {}).get(field_key, '')
                preguntas_detalle[field_key] = {
                    'label': preg_label,
                    'score': score,
                    'respuesta': respuesta,
                    'field_key': field_key,
                    'modulo': modulo,
                }

            sub['indicadores_detalle'] = indicadores_detalle
            sub['preguntas_detalle'] = preguntas_detalle

    # Anotar preguntas compartidas: una respuesta puede puntuar indicadores
    # de varias dimensiones; el validador la vera donde corresponda con la
    # nota de procedencia, en vez de una duplicacion silenciosa.
    for dim_key, dim in detalle.items():
        for sub in dim.get('subdimensiones', {}).values():
            for preg in sub.get('preguntas_detalle', {}).values():
                usos = ocurrencias.get(preg['field_key'], [])
                inds_misma = [i for d, i in usos if d == dim_key]
                dims_otras = sorted({d for d, i in usos if d != dim_key})
                notas = []
                if len(inds_misma) > 1:
                    notas.append('alimenta los indicadores '
                                 + ', '.join(inds_misma))
                if dims_otras:
                    notas.append('tambien puntua en la dimension '
                                 + ' y '.join(dims_otras))
                if preg.get('modulo') and DIM_POR_MODULO.get(
                        preg['modulo']) != dim_key:
                    notas.append('se diligencia en el modulo '
                                 + preg['modulo'].upper())
                preg['compartida'] = ' · '.join(notas)

    organismo = formulario.organismo

    # Labels legibles por field_key: primero los de PREGUNTA_LABELS
    # (preguntas puntuadas), luego los labels reales de los forms como
    # fallback para campos auxiliares/condicionales.
    pregunta_labels = {v[1]: v[0] for k, v in PREGUNTA_LABELS.items()}
    form_labels = {}
    for _step, form_cls in ICED_WIZARD_FORMS:
        for name, fld in form_cls.base_fields.items():
            if fld.label:
                form_labels.setdefault(name, str(fld.label))

    # Construir estructura de respuestas agrupada por PASO del wizard
    # (orden real del cuestionario). Cada módulo contiene subsecciones
    # por paso — C se divide en C1/C2/C3 y D en D1/D2/D3/D4 — y dentro
    # de cada paso los campos siguen el orden de declaración del form,
    # no orden alfabético.
    paso_campo = {
        'identificacion': 'a', 'entorno': 'b',
        'infraestructura_c1': 'c', 'infraestructura_c2': 'c',
        'infraestructura_c3': 'c',
        'metodologia_d1': 'd', 'metodologia_d2': 'd',
        'metodologia_d3': 'd', 'metodologia_d4': 'd',
        'accesibilidad': 'e',
    }
    respuestas_por_letra = {'a': resp_a, 'b': resp_b, 'c': resp_c, 'd': resp_d, 'e': resp_e}

    respuestas_modulo_display = []
    for letra, nombre_modulo in [
        ('a', 'Módulo A — Identificación'),
        ('b', 'Módulo B — Entorno Institucional'),
        ('c', 'Módulo C — Infraestructura'),
        ('d', 'Módulo D — Metodología'),
        ('e', 'Módulo E — Accesibilidad'),
    ]:
        respuestas = respuestas_por_letra[letra]
        usados = set()
        pasos = []
        for step_key, form_cls in ICED_WIZARD_FORMS:
            if paso_campo.get(step_key) != letra:
                continue
            items = []
            faltantes = []
            for name, fld in form_cls.base_fields.items():
                if name in respuestas and not _vacio(respuestas[name]):
                    usados.add(name)
                    items.append({
                        'label': pregunta_labels.get(name) or form_labels.get(name, name),
                        'field_key': name,
                        'respuesta': respuestas[name],
                    })
                    continue
                # Campos sin respuesta útil: solo los que capturan dato
                # (no intros/headers/displays) y, para formularios de
                # equipo, solo los asignados a ese equipo.
                usados.add(name)
                if not _campo_captura_dato(fld):
                    continue
                if formulario.equipo and not ICEDPreguntaEquipo.campo_pertenece_a_equipo(name, formulario.equipo):
                    continue
                codigo = ICEDPreguntaEquipo.codigo_de_campo(name)
                faltantes.append({
                    'label': pregunta_labels.get(name) or form_labels.get(name, name),
                    'field_key': name,
                    'codigo': codigo or '',
                    'condicional': bool(
                        (getattr(fld.widget, 'attrs', {}) or {}).get('data-show-if')
                    ) or any(s in name for s in ('especificar', 'otro', 'motivo')),
                })
            if items or faltantes:
                pasos.append({
                    'label': ICED_STEP_LABELS.get(step_key, step_key),
                    'items': items,
                    'faltantes': faltantes,
                })
        # Campos no mapeados a ningún form: auxiliares generados por
        # widgets (displays, contactos) o respuestas huérfanas.
        resto = [{
            'label': pregunta_labels.get(k) or form_labels.get(k, k),
            'field_key': k,
            'respuesta': v,
        } for k, v in respuestas.items() if k not in usados]
        if resto:
            pasos.append({'label': 'Otros campos del módulo', 'items': resto, 'faltantes': []})
        total = sum(len(p['items']) for p in pasos)
        # Preview del puntaje de la dimension alimentada por este modulo
        dim_preview = detalle.get(DIM_POR_MODULO.get(letra))
        respuestas_modulo_display.append(
            (nombre_modulo, pasos, total, dim_preview))

    # Formularios hermanos: mismo organismo y período, otros equipos técnicos
    hermanos = ICEDFormulario.objects.filter(
        organismo=formulario.organismo,
        periodo=formulario.periodo,
    ).exclude(pk=formulario.pk).order_by('equipo')

    context = {
        'formulario': formulario,
        'resultado': resultado,
        'organismo': organismo,
        'respuestas_modulo_display': respuestas_modulo_display,
        'hermanos': hermanos,
    }
    return render(request, 'validacion/revisar_iced.html', context)


@validador_sistema_required
def validacion_calcular_iced(request, formulario_id):
    """Ejecutar cálculo ICED y persistir puntajes en el modelo."""
    if request.method != 'POST':
        return redirect('indicadores:validacion_dashboard')

    formulario = get_object_or_404(ICEDFormulario, pk=formulario_id)
    # Los formularios por equipo son parciales: el ICED oficial se
    # calcula sobre el consolidado generado por la conciliación.
    if formulario.equipo:
        messages.warning(
            request,
            f'Este formulario solo cubre las preguntas del equipo '
            f'{formulario.equipo}; el ICED se calcula sobre el consolidado. '
            f'Concilie primero las respuestas de los equipos.'
        )
        return redirect('indicadores:validacion_conciliar_iced',
                        organismo_id=formulario.organismo_id,
                        periodo=formulario.periodo)
    if formulario.estado not in ('enviado', 'validado'):
        messages.error(request, 'Solo se pueden calcular puntajes de formularios enviados.')
        return redirect('indicadores:validacion_revisar_iced', formulario_id=formulario.pk)
    resultado = aplicar_puntajes(formulario)

    messages.success(
        request,
        f'Puntajes ICED calculados y guardados: {resultado["puntaje_global"]}% '
        f'({resultado["nivel_nombre"]})'
    )
    return redirect('indicadores:validacion_revisar_iced', formulario_id=formulario.pk)


@validador_sistema_required
def validacion_decidir_iced(request, formulario_id):
    """Procesa la decisión del validador sobre un formulario ICED."""
    if request.method != 'POST':
        return redirect('indicadores:validacion_dashboard')

    formulario = get_object_or_404(ICEDFormulario, pk=formulario_id)
    accion = request.POST.get('accion')
    observaciones = request.POST.get('observaciones', '').strip()

    # Los formularios por equipo son parciales: aprobarlos publicaría un
    # ICED incompleto. La decisión se toma sobre el consolidado.
    if formulario.equipo:
        messages.warning(
            request,
            f'Este formulario solo cubre las preguntas del equipo '
            f'{formulario.equipo}; la decisión se toma sobre el consolidado. '
            f'Concilie primero las respuestas de los equipos.'
        )
        return redirect('indicadores:validacion_conciliar_iced',
                        organismo_id=formulario.organismo_id,
                        periodo=formulario.periodo)

    # Solo se puede decidir sobre formularios en estado 'enviado':
    # evita aprobar borradores o re-decidir formularios ya resueltos.
    if formulario.estado != 'enviado':
        messages.error(
            request,
            f'No se puede procesar la decisión: el formulario está en estado '
            f'"{formulario.get_estado_display()}", no "Enviado".'
        )
        return redirect('indicadores:validacion_revisar_iced', formulario_id=formulario.pk)

    if accion == 'aprobar':
        # Recalcular SIEMPRE al aprobar: si el formulario fue devuelto,
        # corregido y reenviado, los puntajes previos quedarían obsoletos.
        aplicar_puntajes(formulario)
        formulario.refresh_from_db()

        formulario.estado = 'validado'
        formulario.fecha_validacion = timezone.now()
        formulario.observaciones_validador = observaciones or ''
        formulario.save(update_fields=['estado', 'fecha_validacion', 'observaciones_validador'])

        pct = round(float(formulario.puntaje_global) * 100) if formulario.puntaje_global else 0
        msg = (
            f'✅ ICED de {formulario.organismo.nombre} aprobado y publicado. '
            f'Puntaje: {pct}%'
        )
        level = messages.SUCCESS

        # Notificar por correo al delegado (no bloquea la decisión si falla)
        try:
            from .notifications import notificar_delegado_iced
            notificar_delegado_iced(formulario, 'validado', observaciones)
        except Exception:
            logger.exception('Error notificando aprobación del ICED %s', formulario.pk)

    elif accion == 'devolver':
        if not observaciones:
            messages.error(request, 'Debes indicar las observaciones para devolver el formulario.')
            return redirect('indicadores:validacion_revisar_iced', formulario_id=formulario.pk)
        formulario.estado = 'devuelto'
        formulario.observaciones_validador = observaciones
        formulario.save(update_fields=['estado', 'observaciones_validador'])

        msg = f'🔄 Formulario ICED devuelto a {formulario.organismo.nombre} con observaciones.'
        level = messages.INFO

        # Notificar por correo al delegado (no bloquea la decisión si falla)
        try:
            from .notifications import notificar_delegado_iced
            notificar_delegado_iced(formulario, 'devuelto', observaciones)
        except Exception:
            logger.exception('Error notificando devolución del ICED %s', formulario.pk)

    elif accion == 'rechazar':
        if not observaciones:
            messages.error(request, 'Debes explicar el motivo del rechazo.')
            return redirect('indicadores:validacion_revisar_iced', formulario_id=formulario.pk)
        # Rechazo terminal: el formulario queda cerrado y no puede
        # corregirse ni reenviarse (a diferencia de 'devuelto').
        formulario.estado = 'rechazado'
        formulario.observaciones_validador = observaciones
        formulario.save(update_fields=['estado', 'observaciones_validador'])

        msg = f'❌ Formulario ICED de {formulario.organismo.nombre} rechazado.'
        level = messages.WARNING

        # Notificar por correo al delegado (no bloquea la decisión si falla)
        try:
            from .notifications import notificar_delegado_iced
            notificar_delegado_iced(formulario, 'rechazado', observaciones)
        except Exception:
            logger.exception('Error notificando rechazo del ICED %s', formulario.pk)

    else:
        messages.error(request, 'Acción no válida.')
        return redirect('indicadores:validacion_revisar_iced', formulario_id=formulario.pk)

    messages.add_message(request, level, msg)
    return redirect('indicadores:validacion_dashboard')


# ============================================================================
# CONCILIACIÓN FICED POR EQUIPOS TÉCNICOS
# ============================================================================

_CAMPOS_RESP = ('respuestas_a', 'respuestas_b', 'respuestas_c',
                'respuestas_d', 'respuestas_e')


def _codigo_de_campo(field_name):
    """'p15_1_herramientas' → '15.1'; 'p17_suficiencia' → '17'; otro → None."""
    from .models_iced import ICEDPreguntaEquipo
    return ICEDPreguntaEquipo.codigo_de_campo(field_name)


def _respuestas_planas(formulario):
    """Une los 5 JSONField de módulo en un solo dict field_key → valor.

    Normaliza claves: los borradores del autosave AJAX llegan con prefijo
    de paso ('entorno-p11_x'); sin normalizar, esas respuestas eran
    invisibles para la conciliación (_codigo_de_campo devuelve None).
    """
    r = {}
    for attr in _CAMPOS_RESP:
        r.update(_normalizar_respuestas(getattr(formulario, attr) or {}))
    return r


# --- Clasificación de campos para conciliación -------------------------------
# La divergencia entre equipos se mide SOLO sobre los campos de decisión
# (la opción seleccionada: radio/select/checkbox/boolean). Los campos de
# texto libre, tablas/matrices JSON y auxiliares (¿Cuál?, otros, actividades)
# no divergen: se fusionan de todos los equipos en el consolidado.

_PASO_CAMPO = {
    'identificacion': 'respuestas_a',
    'entorno': 'respuestas_b',
    'infraestructura_c1': 'respuestas_c',
    'infraestructura_c2': 'respuestas_c',
    'infraestructura_c3': 'respuestas_c',
    'metodologia_d1': 'respuestas_d',
    'metodologia_d2': 'respuestas_d',
    'metodologia_d3': 'respuestas_d',
    'metodologia_d4': 'respuestas_d',
    'accesibilidad': 'respuestas_e',
}
_FIELD_DEFS = {}
_FIELD_ATTR = {}
for _s, _c in ICED_WIZARD_FORMS:
    for _n, _f in _c.base_fields.items():
        _FIELD_DEFS.setdefault(_n, _f)
        if _s in _PASO_CAMPO:
            _FIELD_ATTR.setdefault(_n, _PASO_CAMPO[_s])


def _es_campo_decision(field_name):
    """True si el campo es una opción seleccionable (radio/select/checkbox/
    booleano): es la respuesta 'oficial' de la pregunta y define divergencia."""
    fld = _FIELD_DEFS.get(field_name)
    if fld is None:
        return False
    if isinstance(fld, forms.BooleanField):
        return True
    return isinstance(
        fld.widget,
        (forms.RadioSelect, forms.Select, forms.CheckboxSelectMultiple))


def _fusionar_valores(valores):
    """Fusiona valores no-decisión de varios equipos en uno solo.

    - listas/tablones: se concatenan sin duplicar filas idénticas;
    - dicts: se fusionan por clave recursivamente;
    - textos y escalares: se unen con ' - ' (orden de equipo), sin repetir
      valores idénticos; un solo valor no vacío se devuelve tal cual.
    """
    vals = [v for v in valores if not _vacio(v)]
    if not vals:
        return ''
    if all(isinstance(v, dict) for v in vals):
        claves = []
        for v in vals:
            for k in v:
                if k not in claves:
                    claves.append(k)
        return {k: _fusionar_valores([v.get(k) for v in vals])
                for k in claves}
    if any(isinstance(v, list) for v in vals):
        out, vistos = [], set()
        for v in vals:
            items = v if isinstance(v, list) else [v]
            for item in items:
                s = json.dumps(item, sort_keys=True, default=str,
                               ensure_ascii=False)
                if s not in vistos:
                    vistos.add(s)
                    out.append(item)
        return out
    if len(vals) == 1:
        return vals[0]
    return ' - '.join(dict.fromkeys(str(v) for v in vals))


@validador_sistema_required
def validacion_conciliar_iced(request, organismo_id, periodo):
    """
    Concilia las respuestas FICED de un organismo entre sus equipos técnicos.

    Cada equipo responde solo sus preguntas asignadas; las preguntas
    asignadas a varios equipos reciben respuestas independientes. Aquí el
    validador compara las respuestas por equipo, elige la canónica para las
    divergentes y genera/actualiza el formulario consolidado (equipo=''),
    que es el que pasa por cálculo y decisión.
    """
    import json as _json
    from .models_iced import ICEDPreguntaEquipo
    from .models import Organismo

    organismo = get_object_or_404(Organismo, pk=organismo_id)
    formularios = list(
        ICEDFormulario.objects.filter(organismo=organismo, periodo=periodo)
        .exclude(equipo='')
        .select_related('usuario_diligencia')
        .order_by('equipo')
    )
    if not formularios:
        messages.info(request, 'Este organismo no tiene formularios por equipo.')
        return redirect('indicadores:validacion_dashboard')

    consolidado = ICEDFormulario.objects.filter(
        organismo=organismo, periodo=periodo, equipo='').first()

    resp_por_equipo = {f.equipo: _respuestas_planas(f) for f in formularios}
    form_por_equipo = {f.equipo: f for f in formularios}

    # Labels legibles por código: 'p15_1' → codigo '15.1'
    def label_de(codigo):
        key = 'p' + codigo.replace('.', '_')
        return PREGUNTA_LABELS.get(key, (f'P{codigo}', ''))[0]

    # Agrupar asignaciones por código de pregunta (orden natural 1, 2, 15.1…)
    def _orden(cod):
        return tuple(int(p) for p in cod.split('.'))

    asignaciones = {}
    for codigo, equipo in ICEDPreguntaEquipo.objects.values_list('codigo', 'equipo'):
        asignaciones.setdefault(codigo, set()).add(equipo)

    # Códigos con asignación oficial + códigos que algún equipo respondió
    # aunque no estén en la matriz (en el wizard, 'sin asignación → la
    # responde cualquiera'). Sin esto, esas respuestas se perdían en el
    # consolidado y no aparecían en la validación (ej. P11).
    codigos_respondidos = {
        cod
        for resp in resp_por_equipo.values()
        for k in resp
        for cod in [_codigo_de_campo(k)] if cod
    }

    # field_key → atributo respuestas_* donde se guardó (para respuestas
    # huérfanas no presentes en los forms del wizard).
    attr_de = {}
    for f in formularios:
        for attr in _CAMPOS_RESP:
            for k in _normalizar_respuestas(getattr(f, attr) or {}):
                attr_de.setdefault(k, attr)

    preguntas = []
    for codigo in sorted(asignaciones.keys() | codigos_respondidos, key=_orden):
        por_equipo = {
            f.equipo: {
                k: v for k, v in resp_por_equipo[f.equipo].items()
                if _codigo_de_campo(k) == codigo
            }
            for f in formularios
        }
        # Divergencia SOLO sobre la opción seleccionada (campos de
        # decisión). Textos/tablas/auxiliares se fusionan, no divergen.
        snapshots = {
            _json.dumps(
                {k: v for k, v in resp.items()
                 if _es_campo_decision(k) and not _vacio(v)},
                sort_keys=True, default=str)
            for resp in por_equipo.values() if resp
        }
        # Preguntas sin asignación en la matriz: participan los equipos
        # que de hecho respondieron.
        respondieron = sorted(e for e, r in por_equipo.items() if r)
        preguntas.append({
            'codigo': codigo,
            'label': label_de(codigo),
            'asignados': sorted(asignaciones.get(codigo) or respondieron),
            'por_equipo': por_equipo,
            'por_equipo_items': {
                eq: [{
                    'field_key': k,
                    'label': iced_field_label(k),
                    'respuesta': v,
                } for k, v in resp.items() if not _vacio(v)]
                for eq, resp in por_equipo.items()
            },
            'divergente': len(snapshots) > 1,
        })

    if request.method == 'POST':
        consolidado, _ = ICEDFormulario.objects.get_or_create(
            organismo=organismo, periodo=periodo, equipo='',
            defaults={'usuario_diligencia': request.user},
        )
        nuevos = {attr: {} for attr in _CAMPOS_RESP}
        conciliadas = 0
        for p in preguntas:
            equipos_resp = [e for e, r in p['por_equipo'].items() if r]
            if not equipos_resp:
                continue
            ganador = request.POST.get(f"ganador_{p['codigo']}")
            # Sin elección explícita: único equipo que respondió gana
            if ganador not in equipos_resp:
                ganador = equipos_resp[0]
            resp_ganador = p['por_equipo'][ganador]
            campos = set()
            for r in p['por_equipo'].values():
                campos.update(r)
            for k in campos:
                attr = _FIELD_ATTR.get(k) or attr_de.get(k) or 'respuestas_a'
                if _es_campo_decision(k):
                    # La opción seleccionada es la del equipo elegido
                    v = resp_ganador.get(k)
                    if not _vacio(v):
                        nuevos[attr][k] = v
                else:
                    # Textos/tablas/auxiliares: se fusionan de TODOS los
                    # equipos que respondieron (actividades, ¿cuál?, otros)
                    v = _fusionar_valores(
                        [p['por_equipo'][e].get(k) for e in equipos_resp])
                    if not _vacio(v):
                        nuevos[attr][k] = v
            conciliadas += 1

        # Campos sin código de pregunta (personas de contacto, campos
        # display auxiliares): no pasan por elección de equipo; se conserva
        # el primer valor no vacío encontrado entre los formularios.
        for f in formularios:
            for attr in _CAMPOS_RESP:
                for k, v in _normalizar_respuestas(getattr(f, attr) or {}).items():
                    if (_codigo_de_campo(k) is None
                            and v not in (None, '', [], {})
                            and k not in nuevos[attr]):
                        nuevos[attr][k] = v

        for attr in _CAMPOS_RESP:
            setattr(consolidado, attr, nuevos[attr])
        consolidado.estado = 'enviado'
        consolidado.fecha_envio = timezone.now()
        consolidado.usuario_diligencia = request.user
        consolidado.save()

        messages.success(
            request,
            f'Consolidado generado con {conciliadas} preguntas de '
            f'{len(formularios)} equipo(s). Ya puede revisarlo y calcular el ICED.'
        )
        return redirect('indicadores:validacion_revisar_iced',
                        formulario_id=consolidado.pk)

    context = {
        'organismo': organismo,
        'periodo': periodo,
        'formularios': formularios,
        'consolidado': consolidado,
        'preguntas': preguntas,
        'n_divergentes': sum(1 for p in preguntas if p['divergente']),
    }
    return render(request, 'validacion/conciliar_iced.html', context)


# ============================================================================
# FORMULARIO SIMPLIFICADO DE GRÁFICO
# ============================================================================

@validador_sistema_required
def crear_grafico_simplificado_validacion(request, indicador_id):
    """
    Vista simplificada para crear un gráfico básico desde el módulo de validación.
    Solo captura la información esencial (tipo, ejes, nombre).
    El admin completará la configuración avanzada desde el panel de administración.
    """
    indicador = get_object_or_404(Indicador, id=indicador_id)
    
    # Verificar permisos: solo validadores o staff
    if not request.user.is_staff and not (hasattr(request.user, 'perfil_recolector') and request.user.perfil_recolector.es_validador()):
        messages.error(request, 'No tiene permisos para crear gráficos.')
        return redirect('indicadores:validacion_dashboard')
    
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
            return redirect('indicadores:validacion_dashboard')
    else:
        form = GraficoSimplificadoForm(indicador=indicador)
    
    context = {
        'form': form,
        'indicador': indicador,
        'titulo_pagina': f'Configurar Gráfico: {indicador.nombre}',
    }
    
    return render(request, 'validacion/crear_grafico_simplificado.html', context)


# ============================================================================
# WIZARD: NORMALIZACIÓN DE IDENTIDAD DE INDICADORES
#
# Identidad = código indicador + conciliación de duplicados:
#   - consulta 1:1 del id interno (pk) y ruta taxonómica,
#   - export xlsx: dominio › tema › subtema › nombre | código | id,
#   - actualización de código individual y masiva (csv/xlsx: id + codigo),
#   - conciliación A+B → se conserva uno, el otro se elimina y TODAS sus
#     relaciones (datos, gráficos, cargas, procesos, regla, enlaces M2M) se
#     reasignan; metadatos se eligen campo a campo.
# ============================================================================

# Campos escalariales que el usuario puede tomar del indicador eliminado.
# Los M2M propios (subtemas/dominios de desagregación) siempre hacen unión.
CAMPOS_CONCILIABLES = [
    ('nombre', 'Nombre'),
    ('codigo_indicador', 'Código'),
    ('sigla', 'Sigla'),
    ('grupo_indicador', 'Grupo de indicador'),
    ('descripcion_indicador', 'Descripción'),
    ('objetivo', 'Objetivo'),
    ('metodo_medicion', 'Método de medición'),
    ('formula_ficha', 'Fórmula de ficha'),
    ('variables', 'Variables'),
    ('unidad_medida', 'Unidad de medida'),
    ('fuente_datos', 'Fuente de datos'),
    ('notas', 'Notas'),
    ('nomenclaturas_clasificaciones', 'Nomenclaturas / clasificaciones'),
    ('poblacion_objetivo', 'Población objetivo'),
    ('alcance_tematico', 'Alcance temático'),
    ('cobertura_geografica', 'Cobertura geográfica'),
    ('periodo_referencia', 'Periodo de referencia'),
    ('periodo_base', 'Periodo base'),
    ('serie_historica_disponible', 'Serie histórica disponible'),
    ('frecuencia_difusion', 'Frecuencia de difusión'),
    ('medios_difusion', 'Medios de difusión'),
    ('comentarios_adicionales', 'Comentarios adicionales'),
    ('referencias', 'Referencias'),
    ('equipo_responsable', 'Equipo responsable'),
    ('organismo_responsable', 'Organismo responsable'),
    ('suborganismo', 'Suborganismo'),
    ('operacion', 'Operación estadística'),
    ('conjunto_datos', 'Conjunto de datos'),
    ('catalogo_consulta', 'Catálogo de consulta enlazado'),
    ('subtema', 'Subtema principal'),
    ('mostrar_mapa', 'Mostrar mapa'),
    ('activo', 'Activo'),
]


def _ind_ruta(ind):
    """'Dominio › Tema › Subtema' de la clasificación principal."""
    st = ind.subtema
    if st and st.tema and st.tema.dominio:
        return f"{st.tema.dominio.nombre} › {st.tema.nombre} › {st.nombre}"
    return '—'


def _ind_json(ind):
    return {
        'id': ind.id,
        'codigo': ind.codigo_indicador or '',
        'nombre': ind.nombre,
        'ruta': _ind_ruta(ind),
        'adicionales': [
            f"{s.tema.dominio.nombre} › {s.tema.nombre} › {s.nombre}"
            for s in ind.subtemas_adicionales.select_related('tema__dominio')
            if s.tema and s.tema.dominio
        ],
        'n_datos': ind.datos.count(),
        'n_graficos': ind.graficos.count(),
        'activo': ind.activo,
    }


def _val_campo(ind, campo):
    """Representación corta de un campo para la tabla de comparación."""
    v = getattr(ind, campo)
    if v is None:
        return ''
    field = Indicador._meta.get_field(campo)
    if field.many_to_one:           # FK → su str()
        return str(v)
    s = re.sub(r'<[^>]+>', ' ', str(v))   # CKEditor → texto plano
    s = ' '.join(s.split())
    return s[:200] + ('…' if len(s) > 200 else '')


@validador_sistema_required
def validacion_normalizacion(request):
    """Página del wizard de normalización de identidad."""
    return render(request, 'validacion/normalizacion_identidad.html')


@validador_sistema_required
def norm_buscar_indicador(request):
    """GET ?q= — consulta 1:1 de id interno, código y ruta del indicador."""
    q = (request.GET.get('q') or '').strip()
    if len(q) < 2:
        return JsonResponse({'resultados': []})
    qs = Indicador.objects.select_related(
        'subtema__tema__dominio'
    ).prefetch_related('subtemas_adicionales__tema__dominio')
    filtro = Q(nombre__icontains=q) | Q(codigo_indicador__icontains=q) | Q(sigla__icontains=q)
    if q.isdigit():
        filtro |= Q(id=int(q))
    qs = qs.filter(filtro).order_by('nombre')[:20]
    return JsonResponse({'resultados': [_ind_json(i) for i in qs]})


@validador_sistema_required
def norm_exportar_identidad(request):
    """GET — xlsx con la relación completa dominio-tema-subtema-nombre-código-id."""
    rows = []
    qs = Indicador.objects.select_related(
        'subtema__tema__dominio'
    ).prefetch_related('subtemas_adicionales').order_by(
        'subtema__tema__dominio__nombre', 'subtema__tema__nombre',
        'subtema__nombre', 'nombre'
    )
    for ind in qs:
        st = ind.subtema
        rows.append({
            'dominio': st.tema.dominio.nombre if st and st.tema and st.tema.dominio else '',
            'tema': st.tema.nombre if st and st.tema else '',
            'subtema': st.nombre if st else '',
            'nombre': ind.nombre,
            'codigo_indicador': ind.codigo_indicador or '',
            'id': ind.id,
            'subtemas_adicionales': '; '.join(
                s.nombre for s in ind.subtemas_adicionales.all()),
        })
    df = pd.DataFrame(rows, columns=[
        'dominio', 'tema', 'subtema', 'nombre',
        'codigo_indicador', 'id', 'subtemas_adicionales',
    ])
    bio = io.BytesIO()
    with pd.ExcelWriter(bio) as writer:
        df.to_excel(writer, index=False, sheet_name='indicadores')
    resp = HttpResponse(
        bio.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="identidad_indicadores.xlsx"'
    return resp


@validador_sistema_required
@require_POST
def norm_actualizar_codigo(request):
    """POST {id, codigo} — cambia el código de un indicador (1:1)."""
    try:
        data = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)
    ind = get_object_or_404(Indicador, pk=data.get('id'))
    nuevo = (data.get('codigo') or '').strip()
    if nuevo:
        dup = Indicador.objects.filter(
            codigo_indicador=nuevo).exclude(pk=ind.pk).first()
        if dup:
            return JsonResponse({
                'ok': False,
                'error': f'Código "{nuevo}" ya usado por [{dup.id}] {dup.nombre}'
            }, status=409)
    anterior = ind.codigo_indicador
    ind.codigo_indicador = nuevo or None
    ind.save(update_fields=['codigo_indicador'])
    return JsonResponse({'ok': True, 'id': ind.id,
                         'anterior': anterior or '', 'nuevo': nuevo})


@validador_sistema_required
@require_POST
def norm_importar_codigos(request):
    """POST archivo csv/xlsx con columnas id + codigo — actualización masiva."""
    archivo = request.FILES.get('archivo')
    if not archivo:
        return JsonResponse({'ok': False, 'error': 'No se envió archivo'}, status=400)
    try:
        if archivo.name.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(archivo, dtype=str)
        else:
            df = pd.read_csv(archivo, sep=None, engine='python', dtype=str)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': f'No se pudo leer el archivo: {e}'},
                            status=400)
    cols = {c.strip().lower(): c for c in df.columns}
    col_id = next((cols[c] for c in
                   ('id', 'pk', 'indicador_id', 'id_indicador') if c in cols), None)
    col_cod = next((cols[c] for c in
                    ('codigo', 'codigo_indicador', 'nuevo_codigo', 'codigo_nuevo')
                    if c in cols), None)
    if not col_id or not col_cod:
        return JsonResponse({
            'ok': False,
            'error': f'Se requieren columnas id + codigo. '
                     f'Encontradas: {", ".join(df.columns)}'
        }, status=400)
    actualizados, errores = 0, []
    for i, row in df.iterrows():
        pid = str(row[col_id] or '').strip()
        cod = str(row[col_cod] or '').strip()
        # pandas puede leer la columna id como float: "123.0" → "123"
        if pid.endswith('.0'):
            pid = pid[:-2]
        if not pid or pid.lower() in ('nan', 'none'):
            continue
        ind = Indicador.objects.filter(pk=pid).first()
        if not ind:
            errores.append(f'Fila {i + 2}: no existe indicador id={pid}')
            continue
        if cod and cod.lower() not in ('nan', 'none'):
            dup = Indicador.objects.filter(
                codigo_indicador=cod).exclude(pk=ind.pk).first()
            if dup:
                errores.append(
                    f'Fila {i + 2}: código "{cod}" ya en [{dup.id}] {dup.nombre}')
                continue
            ind.codigo_indicador = cod
        else:
            ind.codigo_indicador = None
        ind.save(update_fields=['codigo_indicador'])
        actualizados += 1
    return JsonResponse({
        'ok': True, 'actualizados': actualizados,
        'errores': errores[:50], 'n_errores': len(errores),
    })


def _conteo_relaciones(ind):
    """Conteos de relaciones que se reasignarán al conciliar."""
    return {
        'datos': ind.datos.count(),
        'graficos': ind.graficos.count(),
        'procesos': ind.procesos_extraccion.count(),
        'cargas_series': ind.cargas_series.count(),
        'regla_extraccion': 1 if getattr(ind, 'regla_extraccion', None) else 0,
        'subtemas_adicionales': ind.subtemas_adicionales.count(),
        'dominios_desag': (ind.dominios_desagregacion_tematica.count() +
                           ind.dominios_desagregacion_geografica.count()),
    }


@validador_sistema_required
def norm_conciliar_comparar(request):
    """GET ?a=&b= — comparación campo a campo de los dos indicadores."""
    a_id, b_id = request.GET.get('a'), request.GET.get('b')
    if not a_id or not b_id or str(a_id) == str(b_id):
        return JsonResponse({'ok': False, 'error': 'Selecciona dos indicadores distintos'},
                            status=400)
    qs = Indicador.objects.select_related('subtema__tema__dominio')
    a = get_object_or_404(qs, pk=a_id)
    b = get_object_or_404(qs, pk=b_id)
    campos = [
        {'campo': f, 'label': l, 'a': _val_campo(a, f), 'b': _val_campo(b, f)}
        for f, l in CAMPOS_CONCILIABLES
    ]
    return JsonResponse({
        'ok': True,
        'a': _ind_json(a), 'b': _ind_json(b),
        'campos': campos,
        'rels': {'a': _conteo_relaciones(a), 'b': _conteo_relaciones(b)},
    })


@validador_sistema_required
@require_POST
def norm_conciliar_aplicar(request):
    """POST {conservar, eliminar, campos:{campo:'a'|'b'}, otro_subtema_adicional}.

    El indicador 'conservar' queda con los metadatos elegidos; el 'eliminar'
    desaparece y TODAS sus relaciones se reasignan al conservado.
    """
    try:
        data = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)
    cid, eid = data.get('conservar'), data.get('eliminar')
    if not cid or not eid or str(cid) == str(eid):
        return JsonResponse({'ok': False, 'error': 'Ids inválidos o iguales'}, status=400)
    campos = data.get('campos') or {}
    otro_adicional = bool(data.get('otro_subtema_adicional', True))

    with transaction.atomic():
        conservado = Indicador.objects.select_for_update().get(pk=cid)
        eliminado = Indicador.objects.select_for_update().get(pk=eid)
        st_cons, st_elim = conservado.subtema, eliminado.subtema
        nombre_elim, pk_elim = eliminado.nombre, eliminado.pk

        # 1. Metadatos: campo a campo, gana el lado elegido
        for campo, _label in CAMPOS_CONCILIABLES:
            if campos.get(campo) == 'b':
                setattr(conservado, campo, getattr(eliminado, campo))
        conservado.save()

        # 2. Subtemas: unión de adicionales + principal no elegido pasa
        #    a adicional (clasificación sin pérdida, si el usuario lo pide)
        adics = list(eliminado.subtemas_adicionales.all())
        if otro_adicional:
            for st in (st_cons, st_elim):
                if st and st.pk != conservado.subtema_id and st not in adics:
                    adics.append(st)
        if adics:
            conservado.subtemas_adicionales.add(*adics)
        if conservado.subtema_id:
            conservado.subtemas_adicionales.remove(conservado.subtema)

        # 3. M2M propias restantes: unión (dominios de desagregación)
        conservado.dominios_desagregacion_tematica.add(
            *eliminado.dominios_desagregacion_tematica.all())
        conservado.dominios_desagregacion_geografica.add(
            *eliminado.dominios_desagregacion_geografica.all())

        # 4. Relaciones reversas por reflexión — ninguna queda huérfana:
        #    FK (datos, gráficos, procesos, cargas, registros),
        #    O2O (regla_extraccion), M2M ajenas (derivados, afectados, ...)
        for rel in Indicador._meta.get_fields():
            if not (rel.auto_created and not rel.concrete):
                continue
            acc = rel.get_accessor_name()
            if not acc:
                continue
            if rel.many_to_many:
                for obj in getattr(eliminado, acc).all():
                    getattr(obj, rel.field.name).add(conservado)
            elif rel.one_to_one:
                inst = getattr(eliminado, acc, None)
                if inst is not None and getattr(conservado, acc, None) is None:
                    setattr(inst, rel.field.name, conservado)
                    inst.save(update_fields=[rel.field.name])
            else:
                getattr(eliminado, acc).update(**{rel.field.name: conservado})

        # 5. Embeddings del eliminado (los del conservado se regeneran)
        DocumentoVector.objects.filter(
            tipo='indicador', referencia_id=pk_elim).delete()

        # 6. Trazabilidad
        tomados = sorted(c for c, v in campos.items() if v == 'b')
        RegistroCambio.objects.create(
            indicador=conservado,
            usuario=request.user if request.user.is_authenticated else None,
            tipo_evento='cambio_metadatos',
            diff_json={
                'conciliacion': {
                    'eliminado_id': pk_elim, 'eliminado_nombre': nombre_elim,
                    'campos_del_eliminado': tomados,
                }
            },
        )

        # 7. Eliminar el duplicado (sus relaciones ya están reasignadas)
        eliminado.delete()

    return JsonResponse({
        'ok': True, 'id': conservado.id, 'nombre': conservado.nombre,
        'mensaje': f'[{pk_elim}] "{nombre_elim}" fusionado en [{conservado.id}] '
                   f'"{conservado.nombre}"',
    })


# ============================================================================
# FUENTES DEL TALLER — validación final a capa gold
# ============================================================================
#
# Pipeline medallón: el analista de Analítica prevalida la fuente (bronce →
# plata) y esta cola confirma el ingreso a capa gold: la fuente se publica
# como base del catálogo de datos (BaseCatalogo + CampoCatalogo) y, si es
# registro administrativo o censo, se formaliza su Operación Estadística.

@validador_sistema_required
def validacion_fuentes_taller(request):
    """Cola de fuentes del taller prevalidadas (capa plata) pendientes de
    la validación final que las promueve a capa gold."""
    from .models_catalogo import FuenteDatos

    pendientes = (FuenteDatos.objects
                  .filter(capa=FuenteDatos.Capa.PLATA, fusionada_en__isnull=True)
                  .select_related('inscripcion__organismo', 'prevalidada_por',
                                  'seguridad')
                  .prefetch_related('variables', 'etiquetas', 'avances')
                  .order_by('fecha_prevalidacion'))
    recientes_gold = (FuenteDatos.objects
                      .filter(capa=FuenteDatos.Capa.GOLD)
                      .select_related('inscripcion__organismo', 'base_catalogo')
                      .order_by('-pk')[:10])

    context = {
        'pendientes': pendientes,
        'recientes_gold': recientes_gold,
        'n_pendientes': pendientes.count(),
        'es_validador_organismo': False,
    }
    return render(request, 'validacion/fuentes_taller.html', context)


@validador_sistema_required
def validacion_fuente_revisar(request, pk):
    """Revisión de una fuente prevalidada antes del paso a gold:
    metadata F1, variables, seguridad F3 y avances de formalización."""
    from .models_catalogo import FuenteDatos, AvanceFormalizacion

    fuente = get_object_or_404(
        FuenteDatos.objects
        .select_related('inscripcion__organismo', 'inscripcion__suborganismo',
                        'seguridad', 'prevalidada_por', 'base_catalogo')
        .prefetch_related('variables', 'etiquetas', 'avances__usuario',
                          'periodicidades', 'desagregaciones',
                          'unidades_analisis', 'fuentes_origen'),
        pk=pk)

    # Checklist gold: acuerdos + metadata + normalización
    hitos = {a.hito for a in fuente.avances.all()}
    checklist = [
        {'hito': 'acuerdo_transferencia',
         'label': 'Acuerdo de transferencia de información',
         'ok': 'acuerdo_transferencia' in hitos},
        {'hito': 'acuerdo_confidencialidad',
         'label': 'Acuerdo de confidencialidad',
         'ok': 'acuerdo_confidencialidad' in hitos},
        {'hito': 'normalizacion',
         'label': 'Fuente normalizada',
         'ok': 'normalizacion' in hitos},
        {'hito': 'metadata_ddi',
         'label': 'Metadata estándar (DDI)',
         'ok': 'metadata_ddi' in hitos},
        {'hito': 'operacion_estadistica',
         'label': 'Formalización como operación estadística',
         'ok': 'operacion_estadistica' in hitos},
    ]

    seguridad = getattr(fuente, 'seguridad', None)
    context = {
        'fuente': fuente,
        'checklist': checklist,
        'seguridad': seguridad,
        'avances': fuente.avances.all(),
        'es_validador_organismo': False,
    }
    return render(request, 'validacion/fuente_taller.html', context)


@validador_sistema_required
@require_POST
def validacion_fuente_decidir(request, pk):
    """Decisión final sobre una fuente prevalidada.

    Aprobar → capa gold: crea la BaseCatalogo con sus CampoCatalogo a partir
    de las variables F1 (identificadores → llaves de cruce) y, opcionalmente,
    la Operación Estadística cuando es registro administrativo o censo.
    Rechazar → vuelve a capa bronce con el motivo registrado como avance.
    """
    from .models import OperacionEstadistica
    from .models_catalogo import (
        AvanceFormalizacion, BaseCatalogo, CampoCatalogo, FuenteDatos,
    )
    from django.utils.text import slugify

    fuente = get_object_or_404(FuenteDatos, pk=pk)
    decision = request.POST.get('decision')

    if fuente.capa != FuenteDatos.Capa.PLATA:
        messages.warning(request, 'Esta fuente no está en capa plata; nada que decidir.')
        return redirect('indicadores:validacion_fuentes_taller')

    if decision == 'aprobar':
        with transaction.atomic():
            # Slug único para la base
            slug_base = slugify(fuente.nombre)[:50] or f'fuente-{fuente.pk}'
            slug = slug_base
            n = 2
            while BaseCatalogo.objects.filter(slug=slug).exists():
                slug = f'{slug_base}-{n}'
                n += 1

            periodicidad = fuente.periodicidades.first()
            desagregacion = fuente.desagregaciones.first()
            operacion = None

            if request.POST.get('crear_operacion') == 'si':
                tipo = request.POST.get('tipo_operacion', 'registro_administrativo')
                tipo_label = ('Registro administrativo' if tipo == 'registro_administrativo'
                              else 'Censo' if tipo == 'censo' else tipo)
                codigo = f'OE-TALLER-{slug[:40].upper()}'
                codigo_base, m = codigo, 2
                while OperacionEstadistica.objects.filter(codigo=codigo).exists():
                    codigo = f'{codigo_base}-{m}'
                    m += 1
                unidad = fuente.unidades_analisis.first()
                operacion = OperacionEstadistica.objects.create(
                    codigo=codigo,
                    nombre=fuente.nombre,
                    descripcion=fuente.descripcion,
                    tipo_operacion=tipo_label,
                    periodicidad=(periodicidad.etiqueta if periodicidad
                                  else 'Por definir'),
                    fecha_inicio=fuente.fecha_inicio or timezone.now().date(),
                    entidad_recopiladora=fuente.inscripcion.organismo.nombre,
                    organismo=fuente.inscripcion.organismo.nombre,
                    suborganismo=(fuente.inscripcion.suborganismo.nombre
                                  if fuente.inscripcion.suborganismo else None),
                    unidad_observ=(unidad.etiqueta if unidad else None),
                    objetivo=fuente.decisiones_apoya or None,
                    descripcion_proceso=fuente.validacion_descripcion or None,
                    metodologia=fuente.validacion_descripcion or None,
                    diccionario_datos=fuente.diccionario_ubicacion or None,
                )

            base = BaseCatalogo.objects.create(
                slug=slug,
                nombre=fuente.nombre,
                descripcion=fuente.descripcion,
                organismo=fuente.inscripcion.organismo,
                frecuencia=(periodicidad.etiqueta if periodicidad else ''),
                cobertura=(desagregacion.etiqueta if desagregacion else ''),
                fuente_origen=fuente,
                operacion=operacion,
            )
            tipo_map = {'texto': 'texto', 'numero': 'numero',
                        'fecha': 'fecha', 'geografico': 'geografico'}
            for i, v in enumerate(fuente.variables.all().order_by('id')):
                CampoCatalogo.objects.create(
                    base=base,
                    nombre=v.nombre[:120],
                    tipo=tipo_map.get(v.tipo, 'texto'),
                    descripcion=v.descripcion[:250],
                    es_llave_cruce=v.es_identificador,
                    orden=i,
                )

            fuente.capa = FuenteDatos.Capa.GOLD
            fuente.base_catalogo = base
            fuente.save(update_fields=['capa', 'base_catalogo'])

            AvanceFormalizacion.objects.create(
                fuente=fuente,
                hito=AvanceFormalizacion.Hito.OPERACION_ESTADISTICA if operacion
                     else AvanceFormalizacion.Hito.OTRO,
                nota=(f'Validación final: aprobada a capa gold como base '
                      f'«{base.nombre}» del catálogo'
                      + (f' con operación estadística {operacion.codigo}.'
                         if operacion else '.')),
                usuario=request.user)

        messages.success(
            request,
            f'«{fuente.nombre}» pasó a capa gold: publicada como base '
            f'«{base.nombre}» del catálogo de datos.')

    elif decision == 'rechazar':
        motivo = request.POST.get('motivo', '').strip()
        with transaction.atomic():
            fuente.capa = FuenteDatos.Capa.BRONCE
            fuente.prevalidada_por = None
            fuente.fecha_prevalidacion = None
            fuente.save(update_fields=['capa', 'prevalidada_por',
                                       'fecha_prevalidacion'])
            AvanceFormalizacion.objects.create(
                fuente=fuente,
                hito=AvanceFormalizacion.Hito.OTRO,
                nota=(f'Validación final: rechazada a capa bronce.'
                      + (f' Motivo: {motivo}' if motivo else '')),
                usuario=request.user)
        messages.warning(
            request, f'«{fuente.nombre}» devuelta a capa bronce.')

    else:
        messages.error(request, 'Decisión no reconocida.')

    return redirect('indicadores:validacion_fuentes_taller')
