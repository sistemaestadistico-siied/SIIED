"""
Panel de Validación para Estadísticos del SIIED.
Espejo del módulo de reportes pero orientado a aprobar/rechazar cargas de delegados.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count

import logging
import os
import pandas as pd

logger = logging.getLogger(__name__)

from .models import (
    PerfilRecolector, CargaSerieIndicador, CargaConjuntoDatos,
    Indicador, ConjuntoDatos, Grafico
)
from .models_iced import ICEDFormulario
from .calcular_iced import (
    calcular_iced, aplicar_puntajes, _normalizar_respuestas,
    PREGUNTA_LABELS, INDICADOR_LABELS, ESTRUCTURA_ICED, INDICADOR_PREGUNTA,
)
from .forms_iced import ICED_WIZARD_FORMS
from .decorators import validador_required


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
    # Cargas de delegados pendientes de validación
    series_enviadas = CargaSerieIndicador.objects.filter(
        es_carga_delegado=True,
        estado__in=['enviado', 'en_revision']
    ).select_related('usuario', 'indicador', 'usuario__perfil_recolector__organismo').order_by('fecha_carga')

    conjunto_datos_enviadas = CargaConjuntoDatos.objects.filter(
        es_carga_delegado=True,
        estado__in=['enviado', 'en_revision']
    ).select_related('usuario', 'conjunto_datos', 'usuario__perfil_recolector__organismo').order_by('fecha_carga')

    # Historial reciente de validaciones propias
    mis_validaciones_series = CargaSerieIndicador.objects.filter(
        validado_por=request.user,
        es_carga_delegado=True
    ).order_by('-fecha_validacion')[:10]

    mis_validaciones_conjunto_datos = CargaConjuntoDatos.objects.filter(
        validado_por=request.user,
        es_carga_delegado=True
    ).order_by('-fecha_validacion')[:10]

    # Formularios ICED pendientes de validación
    try:
        iced_pendientes = ICEDFormulario.objects.filter(
            estado='enviado'
        ).select_related('organismo', 'usuario_diligencia').order_by('-fecha_envio')

        iced_validados_recientes = ICEDFormulario.objects.filter(
            estado='validado'
        ).select_related('organismo').order_by('-fecha_validacion')[:5]

        iced_count = iced_pendientes.count()
    except Exception:
        iced_pendientes = []
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
        'iced_validados_recientes': iced_validados_recientes,
        'stats': stats,
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
        CargaSerieIndicador, id=carga_id, es_carga_delegado=True
    )

    # Marcar como en revisión al abrir
    if carga.estado == 'enviado':
        carga.estado = 'en_revision'
        carga.save()

    # Toggle es_calculo_complejo vía GET rápido (AJAX-friendly)
    if request.method == 'POST' and request.POST.get('accion') == 'toggle_calculo_complejo':
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
    }
    return render(request, 'validacion/revisar_carga.html', context)


@validador_required
def validacion_revisar_conjunto_datos(request, carga_id):
    """
    Revisar una carga de conjunto_datos: vista previa y acciones de validación.
    """
    carga = get_object_or_404(
        CargaConjuntoDatos, id=carga_id, es_carga_delegado=True
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
    }
    return render(request, 'validacion/revisar_carga.html', context)


# ============================================================================
# ACCIONES DE VALIDACIÓN (POST)
# ============================================================================

@validador_required
def validacion_decidir_serie(request, carga_id):
    """Procesa la decisión del validador sobre una carga de serie."""
    if request.method != 'POST':
        return redirect('indicadores:validacion_dashboard')

    carga = get_object_or_404(
        CargaSerieIndicador, id=carga_id, es_carga_delegado=True
    )
    accion = request.POST.get('accion')
    observaciones = request.POST.get('observaciones', '').strip()

    if accion == 'aprobar':
        carga.estado = 'aprobado'
        carga.observaciones_validador = observaciones or None
        msg = f'✅ Carga {carga.codigo_evidencia} aprobada. Queda lista para procesamiento del administrador.'
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
        CargaConjuntoDatos, id=carga_id, es_carga_delegado=True
    )
    accion = request.POST.get('accion')
    observaciones = request.POST.get('observaciones', '').strip()

    if accion == 'aprobar':
        carga.estado = 'aprobado'
        carga.observaciones_validador = observaciones or None
        msg = f'✅ Carga {carga.codigo_evidencia} aprobada.'
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

@validador_required
def validacion_manual(request):
    """Manual de uso del Panel de Validación."""
    return render(request, 'validacion/manual.html')


@validador_required
def validacion_historial(request):
    """Historial completo de cargas validadas (todas, no solo las propias)."""
    filtro_estado = request.GET.get('estado', 'todos')
    filtro_tipo = request.GET.get('tipo', 'todos')

    series = CargaSerieIndicador.objects.filter(
        es_carga_delegado=True
    ).select_related(
        'usuario', 'indicador',
        'validado_por', 'usuario__perfil_recolector__organismo'
    ).order_by('-fecha_carga')

    conjunto_datos = CargaConjuntoDatos.objects.filter(
        es_carga_delegado=True
    ).select_related(
        'usuario', 'conjunto_datos',
        'validado_por', 'usuario__perfil_recolector__organismo'
    ).order_by('-fecha_carga')

    if filtro_estado != 'todos':
        series = series.filter(estado=filtro_estado)
        conjunto_datos = conjunto_datos.filter(estado=filtro_estado)

    # Métricas globales
    stats = {
        'total_series': CargaSerieIndicador.objects.filter(es_carga_delegado=True).count(),
        'series_aprobadas': CargaSerieIndicador.objects.filter(es_carga_delegado=True, estado='aprobado').count(),
        'series_pendientes': CargaSerieIndicador.objects.filter(
            es_carga_delegado=True, estado__in=['enviado', 'en_revision']).count(),
        'total_conjunto_datos': CargaConjuntoDatos.objects.filter(es_carga_delegado=True).count(),
        'conjunto_datos_aprobadas': CargaConjuntoDatos.objects.filter(es_carga_delegado=True, estado='aprobado').count(),
    }

    context = {
        'series': series if filtro_tipo in ('todos', 'series') else CargaSerieIndicador.objects.none(),
        'conjunto_datos': conjunto_datos if filtro_tipo in ('todos', 'conjunto_datos') else CargaConjuntoDatos.objects.none(),
        'filtro_estado': filtro_estado,
        'filtro_tipo': filtro_tipo,
        'estados_disponibles': CargaSerieIndicador.ESTADO_CHOICES,
        'stats': stats,
    }
    return render(request, 'validacion/historial.html', context)


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

@validador_required
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
                }

            sub['indicadores_detalle'] = indicadores_detalle
            sub['preguntas_detalle'] = preguntas_detalle

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

    # Construir estructura de respuestas por módulo con labels legibles
    respuestas_modulo_display = []
    for nombre_modulo, respuestas in [
        ('Módulo A — Identificación', resp_a),
        ('Módulo B — Entorno Institucional', resp_b),
        ('Módulo C — Infraestructura', resp_c),
        ('Módulo D — Metodología', resp_d),
        ('Módulo E — Accesibilidad', resp_e),
    ]:
        items = []
        for field_key, valor in sorted(respuestas.items()):
            label = pregunta_labels.get(field_key) or form_labels.get(field_key, field_key)
            items.append({
                'label': label,
                'field_key': field_key,
                'respuesta': valor,
            })
        respuestas_modulo_display.append((nombre_modulo, items))

    context = {
        'formulario': formulario,
        'resultado': resultado,
        'organismo': organismo,
        'respuestas_modulo_display': respuestas_modulo_display,
    }
    return render(request, 'validacion/revisar_iced.html', context)


@validador_required
def validacion_calcular_iced(request, formulario_id):
    """Ejecutar cálculo ICED y persistir puntajes en el modelo."""
    if request.method != 'POST':
        return redirect('indicadores:validacion_dashboard')

    formulario = get_object_or_404(ICEDFormulario, pk=formulario_id)
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


@validador_required
def validacion_decidir_iced(request, formulario_id):
    """Procesa la decisión del validador sobre un formulario ICED."""
    if request.method != 'POST':
        return redirect('indicadores:validacion_dashboard')

    formulario = get_object_or_404(ICEDFormulario, pk=formulario_id)
    accion = request.POST.get('accion')
    observaciones = request.POST.get('observaciones', '').strip()

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
        formulario.estado = 'devuelto'
        formulario.observaciones_validador = observaciones
        formulario.save(update_fields=['estado', 'observaciones_validador'])

        msg = f'❌ Formulario ICED de {formulario.organismo.nombre} rechazado.'
        level = messages.WARNING

        # Notificar por correo al delegado (no bloquea la decisión si falla)
        try:
            from .notifications import notificar_delegado_iced
            notificar_delegado_iced(formulario, 'devuelto', observaciones)
        except Exception:
            logger.exception('Error notificando rechazo del ICED %s', formulario.pk)

    else:
        messages.error(request, 'Acción no válida.')
        return redirect('indicadores:validacion_revisar_iced', formulario_id=formulario.pk)

    messages.add_message(request, level, msg)
    return redirect('indicadores:validacion_dashboard')


# ============================================================================
# FORMULARIO SIMPLIFICADO DE GRÁFICO
# ============================================================================

@validador_required
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
