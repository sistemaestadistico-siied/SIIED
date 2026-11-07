"""
Módulo Analítica e Inteligencia Artificial.

Acceso: rol 'analista' (y staff). Reúne en un solo lugar la administración
de la IA del portal (parámetros, contextos/prompts y consultas sugeridas de
Don Datico — el mismo formulario de ConfiguracionSistema que usa el admin) y,
a futuro, el acceso a la generación de tableros de Superset.
"""

import os
import re
import csv
import io
import logging
import importlib

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse, Http404
from django.core.signing import Signer, BadSignature
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST
from django.db.models import Count

from .decorators import analista_required, bi_required
from .forms_chat_config import ChatConfigForm, ChatContextForm, ChatSuggestionsForm
from . import chat_config
from .models import (ConfiguracionSistema, ConjuntoDatos, CatalogoConsulta,
                     MenuDominio, DatasetBI, TableroBI,
                     NivelGeografico, ElementoGeo, CapaGeoJSON)
from .superset_service import SupersetService
from django.utils.text import slugify

logger = logging.getLogger(__name__)


# ============================================================================
# AUTENTICACIÓN
# ============================================================================

def _es_bi(request_or_user):
    """True si el usuario puede entrar a las vistas de BI."""
    user = getattr(request_or_user, 'user', request_or_user)
    if user.is_staff:
        return True
    perfil = getattr(user, 'perfil_recolector', None)
    return bool(perfil and perfil.es_bi())


def analitica_login(request):
    """Login del módulo Analítica e IA (analistas, analistas BI y staff)."""
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('indicadores:analitica_dashboard')
        if hasattr(request.user, 'perfil_recolector'):
            perfil = request.user.perfil_recolector
            if perfil.es_analista():
                return redirect('indicadores:analitica_dashboard')
            if perfil.es_bi():
                # analista_organismo entra directo a SIIED BI
                return redirect('indicadores:analitica_superset')
        auth_logout(request)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_staff or (
                hasattr(user, 'perfil_recolector') and
                user.perfil_recolector.es_bi()
            ):
                auth_login(request, user)
                messages.success(
                    request,
                    f'Bienvenido/a, {user.get_full_name() or user.username}')
                if user.is_staff or (
                        user.perfil_recolector.es_analista()):
                    return redirect('indicadores:analitica_dashboard')
                return redirect('indicadores:analitica_superset')
            else:
                messages.error(
                    request,
                    'Tu cuenta no tiene permisos de analista. '
                    'Contacta al administrador.')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'analitica/login.html')


def analitica_logout(request):
    auth_logout(request)
    messages.success(request, 'Sesión cerrada.')
    return redirect('indicadores:analitica_login')


# ============================================================================
# DASHBOARD DEL MÓDULO
# ============================================================================

@analista_required
def analitica_dashboard(request):
    """Portada del módulo con los accesos a sus secciones."""
    return render(request, 'analitica/dashboard.html')


# ============================================================================
# CONFIGURACIÓN DE DON DATICO (mismo formulario del admin)
# ============================================================================

@analista_required
def analitica_configuracion(request):
    """Parámetros del chat Don Datico.

    Réplica de admin/chat-config/: lee ConfiguracionSistema → CHAT_CONFIG →
    initial del field y persiste cada campo en ConfiguracionSistema.
    """
    if request.method == 'POST':
        form = ChatConfigForm(request.POST)
        if form.is_valid():
            try:
                updated = 0
                for field_name, value in form.cleaned_data.items():
                    ConfiguracionSistema.objects.update_or_create(
                        clave=field_name,
                        defaults={
                            'valor': value,
                            'descripcion': f'Configuración del chat: {field_name}',
                        })
                    updated += 1

                # Limpiar caché de contexto para efecto inmediato
                cache.delete(chat_config.CHAT_CONFIG.get(
                    'CONTEXT_CACHE_KEY', 'chat_system_context_v6'))

                messages.success(
                    request,
                    f'✅ Configuración guardada exitosamente ({updated} parámetros)')
                return redirect('indicadores:analitica_configuracion')
            except Exception as e:
                messages.error(request, f'❌ Error al guardar configuración: {str(e)}')
    else:
        initial_data = {
            name: chat_config.get_config(name, field.initial)
            for name, field in ChatConfigForm.base_fields.items()
        }
        form = ChatConfigForm(initial=initial_data)

    return render(request, 'analitica/configuracion.html', {
        'form': form,
        'title': 'Configuración del Chat - Don Datico',
        'current_config': chat_config.CHAT_CONFIG,
        'back_url': '/analitica/',
    })


# ============================================================================
# CONTEXTOS / PROMPTS DE DON DATICO (mismo editor del admin)
# ============================================================================

@analista_required
def analitica_contextos(request):
    """Editor de los contextos de sistema (prompts) de Don Datico.

    Reescribe el bloque correspondiente en chat_config.py — igual que la
    vista del admin — para que ambos portales compartan el mismo archivo.
    """
    selected_context = request.GET.get('context_key', 'don_datico_base')

    if request.method == 'POST':
        form = ChatContextForm(request.POST)
        if form.is_valid():
            try:
                context_key = form.cleaned_data['context_key']
                context_content = form.cleaned_data['context_content']

                # El contenido va en un literal triple-comilla: no puede
                # contener '"""' ni terminar en '"' o '\' sin romper el
                # delimitador de cierre.
                if '"""' in context_content:
                    raise ValueError(
                        'El contexto no puede contener triple comilla (""").')
                if context_content and context_content[-1] in '"\\':
                    context_content += ' '

                config_file_path = os.path.join(
                    settings.BASE_DIR, 'indicadores', 'chat_config.py')

                with open(config_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # No-greedy hasta el primer '"""' de cierre: [^\"]* fallaba
                # (no-op silencioso) si el prompt contenía comillas.
                pattern = rf"'{context_key}':\s*\"\"\".*?\"\"\""
                new_context_str = f"'{context_key}': \"\"\"{context_content}\"\"\""
                new_content, n_subs = re.subn(
                    pattern, new_context_str, content, count=1,
                    flags=re.DOTALL)
                if n_subs == 0:
                    raise ValueError(
                        f'No se encontró el bloque "{context_key}" '
                        'en chat_config.py')

                with open(config_file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                importlib.reload(chat_config)

                # don_datico_base se compone y cachea ~6h en get_system_context;
                # sin esto el prompt nuevo no aplica hasta que expire.
                cache.delete(chat_config.CHAT_CONFIG.get(
                    'CONTEXT_CACHE_KEY', 'chat_system_context_v6'))

                messages.success(
                    request, f'✅ Contexto "{context_key}" guardado exitosamente')
                return redirect(
                    f'/analitica/contextos/?context_key={context_key}')
            except Exception as e:
                messages.error(request, f'❌ Error al guardar contexto: {str(e)}')
    else:
        form = ChatContextForm(initial={
            'context_key': selected_context,
            'context_content': chat_config.CHAT_CONTEXTS.get(selected_context, ''),
        })

    contexts_info = {
        'don_datico_base': {
            'description': 'Contexto base que define la personalidad y misión de Don Datico',
            'variables': ['dominios', 'temas', 'subtemas', 'indicadores']
        },
        'tools_round_1': {
            'description': 'Contexto para la primera ronda cuando se usan herramientas',
            'variables': []
        },
        'tools_round_n': {
            'description': 'Contexto para rondas subsiguientes con herramientas',
            'variables': ['round', 'max_rounds', 'tools_used', 'has_data']
        },
        'conversational': {
            'description': 'Contexto para conversaciones sin herramientas',
            'variables': []
        },
        'enhanced_tools': {
            'description': 'Contexto mejorado con instrucciones detalladas de herramientas',
            'variables': []
        },
        'fallback': {
            'description': 'Contexto de respaldo mínimo',
            'variables': []
        },
    }

    return render(request, 'analitica/contextos.html', {
        'form': form,
        'title': 'Contextos del Sistema - Don Datico',
        'selected_context': selected_context,
        'contexts_info': contexts_info,
        'current_contexts': chat_config.CHAT_CONTEXTS,
        'back_url': '/analitica/',
    })


# ============================================================================
# CONSULTAS SUGERIDAS DE DON DATICO (mismo editor del admin)
# ============================================================================

@analista_required
def analitica_sugerencias(request):
    """Editor de las consultas sugeridas del chat."""
    selected_category = request.GET.get('category', 'exploratorias')

    if request.method == 'POST':
        form = ChatSuggestionsForm(request.POST)
        if form.is_valid():
            try:
                category = form.cleaned_data['category']
                suggestions_list = form.cleaned_data['suggestions']

                config_file_path = os.path.join(
                    settings.BASE_DIR, 'indicadores', 'chat_config.py')

                with open(config_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                current_suggestions = dict(chat_config.CHAT_SUGGESTIONS)
                current_suggestions[category] = suggestions_list

                suggestions_str = "CHAT_SUGGESTIONS = {\n"
                category_comments = {
                    'exploratorias': '    # Consultas exploratorias - para descubrir qué hay disponible',
                    'especificas': '    # Consultas específicas - búsquedas directas',
                    'comparativas': '    # Consultas comparativas - análisis temporal o entre categorías',
                    'datos_completos': '    # Consultas de datos completos - para obtener datasets',
                }
                # Iterar TODAS las categorías existentes: reescribir solo las 4
                # del formulario borraba categorías extra (ej. modulos_extendidos).
                for cat_key, cat_suggestions in current_suggestions.items():
                    comment = category_comments.get(cat_key)
                    if comment:
                        suggestions_str += f"{comment}\n"
                    suggestions_str += f'    "{cat_key}": [\n'
                    for suggestion in cat_suggestions:
                        escaped = suggestion.replace('"', '\\"')
                        suggestions_str += f'        "{escaped}",\n'
                    suggestions_str += '    ],\n'
                suggestions_str += "}"

                pattern = r'CHAT_SUGGESTIONS\s*=\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\}'
                new_content = re.sub(
                    pattern, suggestions_str, content, flags=re.DOTALL)

                with open(config_file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                importlib.reload(chat_config)

                messages.success(
                    request,
                    f'✅ Consultas sugeridas de "{category}" guardadas exitosamente')
                return redirect(f'/analitica/sugerencias/?category={category}')
            except Exception as e:
                messages.error(request, f'❌ Error al guardar: {str(e)}')
    else:
        current_suggestions = chat_config.CHAT_SUGGESTIONS.get(selected_category, [])
        form = ChatSuggestionsForm(initial={
            'category': selected_category,
            'suggestions': '\n'.join(current_suggestions),
        })

    categories_info = {
        'exploratorias': {
            'icon': '🔍',
            'description': 'Para descubrir qué dominios, temas y datos están disponibles',
            'example': 'Ej: "¿Qué temas hay en educación?"'
        },
        'especificas': {
            'icon': '🎯',
            'description': 'Búsquedas directas de indicadores o datos concretos',
            'example': 'Ej: "Datos de población por comunas"'
        },
        'comparativas': {
            'icon': '📊',
            'description': 'Para comparar datos entre períodos o categorías',
            'example': 'Ej: "Comparar tasa de desempleo 2020 vs 2024"'
        },
        'datos_completos': {
            'icon': '📁',
            'description': 'Para obtener datasets o históricos completos',
            'example': 'Ej: "Histórico completo de natalidad"'
        },
    }

    return render(request, 'analitica/sugerencias.html', {
        'form': form,
        'title': 'Consultas Sugeridas - Chat Don Datico',
        'selected_category': selected_category,
        'categories_info': categories_info,
        'current_suggestions': chat_config.CHAT_SUGGESTIONS,
        'back_url': '/analitica/',
    })


# ============================================================================
# TABLEROS SUPERSET — Integración SIIED ↔ Apache Superset
# ============================================================================

@bi_required
def analitica_superset(request):
    """Panel de Tableros Superset: lista dashboards del servicio y su estado."""
    service = SupersetService()

    superset_disponible = service.health_check()
    dashboards = []
    status = {}

    datasets = []
    if superset_disponible:
        dashboards = service.listar_dashboards()
        status = service.get_status()
        datasets = service.listar_datasets()

        # Reconciliar: lo borrado directamente en Superset deja de estar
        # activo en el registro local (evita tableros/datasets fantasma).
        _reconciliar_registros_bi(dashboards, datasets)

        # Registrar TableroBI para dashboards creados a mano en Superset:
        # sin fila no hay visibilidad configurable ni acceso embed.
        ya = set(
            TableroBI.objects.filter(
                dashboard_id__in=[d['id'] for d in dashboards]
            ).values_list('dashboard_id', flat=True))
        TableroBI.objects.bulk_create([
            TableroBI(dashboard_id=d['id'],
                      titulo=(d.get('title') or 'Tablero')[:250],
                      visibilidad='interno', origen='manual')
            for d in dashboards if d['id'] not in ya
        ], ignore_conflicts=True)

        # Metadata local (origen/visibilidad/registro) sobre los activos.
        tableros = {
            t.dashboard_id: t for t in TableroBI.objects.filter(
                dashboard_id__in=[d['id'] for d in dashboards],
                activo=True)}
        datasets_reg = {
            r.nombre_tabla: r for r in DatasetBI.objects.filter(
                nombre_tabla__in=[d.get('table_name') for d in datasets],
                activo=True)}
        perfil = getattr(request.user, 'perfil_recolector', None)
        for d in dashboards:
            t = tableros.get(d['id'])
            d['origen'] = t.origen if t else 'manual'
            d['tablero'] = t
            d['puede_gestionar'] = _puede_gestionar_bi(
                request, t.creado_por if t else None)
            # Link público por enlace (firma del dashboard_id): solo se
            # expone a quien gestiona el tablero — cualquiera con ese
            # link accede sin login, por fuera de la visibilidad.
            if d['puede_gestionar']:
                d['link_publico'] = request.build_absolute_uri(
                    reverse('indicadores:bi_tablero_publico',
                            args=[d['id'], _bi_firma_link(d['id'])]))
        if (perfil and perfil.rol == 'analista_organismo'
                and not request.user.is_staff):
            # El analista BI del organismo solo ve los datasets visibles
            # para él en el registro: base SIIED + públicos + propios.
            visibles = set(
                DatasetBI.visibles_para(request.user)
                .values_list('nombre_tabla', flat=True))
            datasets = [d for d in datasets
                        if d.get('table_name') in visibles]
        _ICONOS_VIS = {'propio': 'fa-user-lock',
                       'organismo': 'fa-building', 'publico': 'fa-globe'}
        for d in datasets:
            r = datasets_reg.get(d.get('table_name'))
            d['datasetbi'] = r
            d['visibilidad'] = r.visibilidad if r else ''
            d['icono_vis'] = _ICONOS_VIS.get(r.visibilidad) if r else ''
            d['visibilidad_label'] = (r.get_visibilidad_display()
                                      if r else '')
            d['puede_gestionar'] = _puede_gestionar_bi(
                request, r.usuario if r else None)
    else:
        messages.warning(
            request,
            'Apache Superset no está disponible en este momento. '
            'Contacte al administrador del sistema.')

    # Agrupar datasets por familia SIIED para facilitar su descubrimiento
    dataset_familias = {
        'indicadores': [], 'conjuntos': [], 'catalogos': [],
        'ficed': [], 'taller': [], 'satisf': [], 'propios': []}
    for d in datasets:
        nombre = d.get('table_name', '')
        if nombre == 'vista_indicadores_datos' or nombre.startswith('dominio_'):
            dataset_familias['indicadores'].append(d)
        elif nombre.startswith('conjunto_'):
            dataset_familias['conjuntos'].append(d)
        elif nombre.startswith('catalogo_'):
            dataset_familias['catalogos'].append(d)
        elif nombre.startswith('ficed_'):
            dataset_familias['ficed'].append(d)
        elif nombre.startswith('taller_'):
            dataset_familias['taller'].append(d)
        elif nombre.startswith('satisf_'):
            dataset_familias['satisf'].append(d)
        else:
            dataset_familias['propios'].append(d)

    context = {
        'dashboards': dashboards,
        'superset_disponible': superset_disponible,
        'status': status,
        'dataset_familias': dataset_familias,
        'conjuntos_disponible': ConjuntoDatos.objects.count(),
        'superset_public_url': getattr(
            settings, 'SUPERSET_PUBLIC_URL',
            'http://127.0.0.1:8088').rstrip('/'),
        'visibilidades_dataset': DatasetBI.VISIBILIDAD_CHOICES,
        'visibilidades_tablero': TableroBI.VISIBILIDAD_CHOICES,
    }
    return render(request, 'analitica/superset.html', context)


def _superset_embed_view(request, target_path, page_title='SIIED BI',
                         icon='chart-bar'):
    """Renderiza la UI de Superset en un iframe.

    Superset 4.x sirve su login como SPA (JWT en el cliente): no existe
    formulario server-side ni cookie de sesión que se pueda transferir,
    así que el auto-login programático no es posible. Se carga la UI
    directamente y el usuario autentica dentro del iframe la primera
    vez (su token queda en el storage del dominio de Superset).
    """
    superset_url = getattr(
        settings, 'SUPERSET_PUBLIC_URL', 'http://127.0.0.1:8088').rstrip('/')

    # El target_path lleva el mount interno de la app (/superset/...).
    # En producción SUPERSET_PUBLIC_URL es el prefijo del proxy externo
    # (…gov.co/superset) y hay que conservar ambos: la URL pública real
    # es /superset (proxy) + /superset/... (app) = /superset/superset/...
    # — quitar el prefijo interno producía /superset/welcome → 404.

    # Hint de credenciales: la clave compartida SOLO funciona en cuentas
    # Alpha/Gamma creadas por el sync del admin. Cuentas Admin (p.ej. la
    # de servicio) o pre-existentes tienen su propia contraseña.
    try:
        roles = SupersetService().roles_de_usuario(request.user.username)
    except Exception:
        roles = []
    if {'Alpha', 'Gamma'} & set(roles):
        superset_password = getattr(settings, 'SUPERSET_SHARED_PASSWORD', '')
        login_hint = 'shared'
    elif roles:
        superset_password = ''
        login_hint = 'admin'
    else:
        superset_password = ''
        login_hint = 'none'

    return render(request, 'analitica/superset_embed.html', {
        'target_url': f"{superset_url}{target_path}",
        'page_title': page_title,
        'icon': icon,
        'superset_public_url': superset_url,
        'login_ok': True,
        # La página va tras bi_required: solo usuarios SIIED autenticados.
        'superset_username': request.user.username,
        'superset_password': superset_password,
        'login_hint': login_hint,
    })


@bi_required
def analitica_superset_crear(request):
    """Interfaz de Superset embebida para crear/gestionar dashboards."""
    return _superset_embed_view(
        request,
        '/superset/dashboard/list/',
        page_title='SIIED BI · Gestionar Tableros',
        icon='th-large')


@bi_required
def analitica_superset_detalle(request, dashboard_id):
    """Muestra un dashboard de Superset embebido en el módulo."""
    service = SupersetService()
    dashboard = service.obtener_dashboard(dashboard_id)

    if not dashboard:
        messages.error(request, 'No se pudo obtener el dashboard solicitado.')
        return redirect('indicadores:analitica_superset')

    title = dashboard.get('title', f'Dashboard {dashboard_id}')

    # Embedding oficial: guest token + @superset-ui/embedded-sdk.
    # El usuario no necesita sesión interactiva en Superset.
    embed_uuid = service.get_or_create_embed_id(dashboard_id)
    guest_token = (
        service.get_guest_token(
            embed_uuid,
            request.user.username,
            first_name=request.user.first_name or '',
            last_name=request.user.last_name or '')
        if embed_uuid else None)

    if embed_uuid and guest_token:
        return render(request, 'analitica/superset_embed.html', {
            'embed_uuid': embed_uuid,
            'guest_token': guest_token,
            'superset_domain': getattr(
                settings, 'SUPERSET_PUBLIC_URL', '').rstrip('/'),
            'page_title': title,
            'icon': 'chart-area',
            'login_ok': True,
        })

    # Fallback: iframe directo — el usuario autentica dentro del iframe.
    slug = dashboard.get('slug')
    path = (f"/superset/dashboard/{slug}/" if slug
            else f"/superset/dashboard/{dashboard_id}/")
    logger.warning(
        f"Analítica: embed con guest token no disponible para "
        f"dashboard {dashboard_id} (embed_uuid={embed_uuid}); "
        f"usando iframe directo")
    return _superset_embed_view(request, path, page_title=title,
                                icon='chart-area')


def _puede_gestionar_bi(request, dueno=None):
    """staff/'analista' gestionan todo; 'analista_organismo' solo lo suyo."""
    perfil = getattr(request.user, 'perfil_recolector', None)
    if request.user.is_staff or (perfil and perfil.rol == 'analista'):
        return True
    return bool(dueno and dueno == request.user)


def _reconciliar_registros_bi(dashboards, datasets):
    """Desactiva los registros BI cuyo activo ya no existe en Superset.

    Cubre los borrados hechos directamente en la UI de Superset: sin esto
    el tablero/dataset seguía activo en SIIED BI / Don Datico BI / admin.
    """
    ids = [d.get('id') for d in dashboards]
    TableroBI.objects.filter(activo=True).exclude(
        dashboard_id__in=ids).update(activo=False)
    nombres = [d.get('table_name') for d in datasets]
    DatasetBI.objects.filter(activo=True).exclude(
        nombre_tabla__in=nombres).update(activo=False)


def _volver_superset(request):
    """Redirige al panel de BI o a Don Datico BI según ?volver=."""
    if request.GET.get('volver') == 'dondatico':
        return redirect('indicadores:analitica_dondatico')
    return redirect('indicadores:analitica_superset')


@bi_required
@require_POST
def analitica_tablero_visibilidad(request, dashboard_id):
    """Cambia la visibilidad SIIED del tablero (guest token / embed)."""
    visibilidad = request.POST.get('visibilidad', '')
    if visibilidad not in dict(TableroBI.VISIBILIDAD_CHOICES):
        messages.error(request, 'Visibilidad no válida.')
        return _volver_superset(request)
    tablero = TableroBI.objects.filter(
        dashboard_id=dashboard_id, activo=True).first()
    if not _puede_gestionar_bi(
            request, tablero.creado_por if tablero else None):
        messages.error(request, 'No tiene permisos para gestionar '
                                'este tablero.')
        return _volver_superset(request)
    perfil = getattr(request.user, 'perfil_recolector', None)
    TableroBI.objects.update_or_create(
        dashboard_id=dashboard_id,
        defaults={
            'titulo': (tablero.titulo if tablero
                       else f'Dashboard {dashboard_id}')[:250],
            'visibilidad': visibilidad,
            'origen': tablero.origen if tablero else 'manual',
            'organismo': (tablero.organismo if tablero
                          else (perfil.organismo if perfil else None)),
            'creado_por': (tablero.creado_por if tablero
                           else request.user),
            'activo': True,
        })
    messages.success(request, 'Visibilidad del tablero actualizada.')
    return _volver_superset(request)


@bi_required
@require_POST
def analitica_tablero_eliminar(request, dashboard_id):
    """Elimina el dashboard en Superset y desactiva su registro local.

    También elimina los charts que quedan huérfanos: Superset no los
    borra con el dashboard y luego bloquean el borrado de los datasets.
    """
    tablero = TableroBI.objects.filter(
        dashboard_id=dashboard_id, activo=True).first()
    if not _puede_gestionar_bi(
            request, tablero.creado_por if tablero else None):
        messages.error(request, 'No tiene permisos para eliminar '
                                'este tablero.')
        return _volver_superset(request)
    res = SupersetService().eliminar_dashboard(
        dashboard_id, con_charts=True)
    if res.get('ok'):
        if tablero:
            tablero.activo = False
            tablero.save(update_fields=['activo'])
        extra = (f" ({res['charts_eliminados']} gráfico(s) huérfano(s) "
                 'también eliminados)'
                 if res.get('charts_eliminados') else '')
        messages.success(request, f'Tablero eliminado de Superset{extra}.')
    else:
        messages.error(
            request,
            f'No se pudo eliminar el tablero: {res.get("error")}')
    return _volver_superset(request)


@bi_required
@require_POST
def analitica_dataset_visibilidad(request, dataset_id):
    """Cambia la visibilidad de un dataset (quién puede consumirlo)."""
    visibilidad = request.POST.get('visibilidad', '')
    if visibilidad not in dict(DatasetBI.VISIBILIDAD_CHOICES):
        messages.error(request, 'Visibilidad no válida.')
        return _volver_superset(request)
    service = SupersetService()
    info = service.info_dataset(dataset_id)
    if not info:
        messages.error(request, 'Dataset no encontrado en Superset.')
        return _volver_superset(request)
    nombre = info['table_name']
    reg = DatasetBI.objects.filter(
        nombre_tabla=nombre, activo=True).first()
    if not _puede_gestionar_bi(request, reg.usuario if reg else None):
        messages.error(request, 'No tiene permisos para gestionar '
                                'este dataset.')
        return _volver_superset(request)
    DatasetBI.objects.update_or_create(
        nombre_tabla=nombre,
        defaults={
            'dataset_id': dataset_id,
            'usuario': reg.usuario if reg else request.user,
            'organismo': (reg.organismo if reg else getattr(
                getattr(request.user, 'perfil_recolector', None),
                'organismo', None)),
            'visibilidad': visibilidad,
            'activo': True,
        })
    messages.success(request, f'Visibilidad de «{nombre}» actualizada.')
    return _volver_superset(request)


@bi_required
@require_POST
def analitica_dataset_eliminar(request, dataset_id):
    """Elimina el dataset en Superset, su tabla física y su registro.

    Superset rechaza el DELETE mientras haya charts que lo usen: primero
    se eliminan los que no están en ningún tablero; los que quedan en
    tableros se informan como bloqueantes.
    """
    service = SupersetService()
    info = service.info_dataset(dataset_id)
    if not info:
        messages.error(request, 'Dataset no encontrado en Superset.')
        return _volver_superset(request)
    nombre = info['table_name']
    reg = DatasetBI.objects.filter(
        nombre_tabla=nombre, activo=True).first()
    if not _puede_gestionar_bi(request, reg.usuario if reg else None):
        messages.error(request, 'No tiene permisos para eliminar '
                                'este dataset.')
        return _volver_superset(request)

    for chart in service.charts_de_dataset(dataset_id):
        if not service.chart_en_dashboard(chart['id']):
            service.eliminar_chart(chart['id'])

    res = service.eliminar_dataset(dataset_id)
    if res.get('ok'):
        # La tabla física del upload queda fuera de Superset: solo se
        # elimina si el registro dice que la subió un usuario (nunca las
        # tablas base del SIIED ni datasets virtuales).
        drop_ok = bool(reg and not reg.es_base_siied
                       and service.eliminar_tabla_fisica(nombre))
        if reg:
            reg.activo = False
            reg.save(update_fields=['activo'])
        extra = ' y su tabla de datos eliminada' if drop_ok else ''
        messages.success(
            request,
            f'Dataset «{nombre}» eliminado de Superset{extra}.')
    else:
        bloquean = res.get('charts_bloquean') or []
        extra = ''
        if bloquean:
            nombres = ', '.join(
                c['nombre'] or f"#{c['id']}" for c in bloquean[:5])
            extra = (f' Sigue en uso por: {nombres} — elimine primero '
                     'esos gráficos o su tablero.')
        messages.error(
            request,
            f'No se pudo eliminar «{nombre}»: {res.get("error")}.{extra}')
    return _volver_superset(request)


@bi_required
def analitica_superset_subir_csv(request):
    """Sube un CSV a Superset como nuevo dataset (propio o ConjuntoDatos).

    Registra el dataset en DatasetBI con la visibilidad elegida por el
    usuario. El analista_organismo solo puede listar los ConjuntoDatos
    de su organismo como origen.
    """
    service = SupersetService()

    perfil = getattr(request.user, 'perfil_recolector', None)
    es_analista_organismo = (
        perfil and perfil.rol == 'analista_organismo'
        and not request.user.is_staff)
    organismo_perfil = perfil.organismo if perfil else None

    # El slice va después del filtro — filtrar un queryset sliceado lanza
    # TypeError ("Cannot filter a query once a slice has been taken").
    conjuntos = ConjuntoDatos.objects.order_by('-fecha_carga')
    if es_analista_organismo:
        conjuntos = conjuntos.filter(
            indicadores__organismo_responsable=organismo_perfil
        ).distinct()
    conjuntos = conjuntos[:50]

    if request.method == 'POST':
        nombre_tabla = request.POST.get('nombre_tabla', '').strip()
        archivo = request.FILES.get('archivo_csv')
        conjunto_id = request.POST.get('conjunto_id')

        # Fuente Google Sheet: URL pública → dataset vivo vía shillelagh.
        url_gsheet = request.POST.get('url_gsheet', '').strip()
        if url_gsheet:
            return _crear_dataset_gsheet_bi(
                request, service, url_gsheet, organismo_perfil, conjuntos)

        # Si seleccionó un conjunto de datos existente, usar su archivo CSV
        if conjunto_id and not archivo:
            try:
                conjunto = ConjuntoDatos.objects.get(id=conjunto_id)
                if conjunto.archivo_csv:
                    archivo = _archivo_a_memoria(conjunto.archivo_csv)
                    if not nombre_tabla:
                        nombre_tabla = _nombre_tabla_siied(
                            'conjunto', conjunto.pk, conjunto.nombre)
                else:
                    messages.error(
                        request,
                        'El conjunto de datos seleccionado no tiene '
                        'archivo CSV.')
                    return render(
                        request, 'analitica/superset_subir_csv.html', {
                            'conjuntos': conjuntos,
                            'superset_disponible': service.health_check(),
                        })
            except ConjuntoDatos.DoesNotExist:
                messages.error(request, 'Conjunto de datos no encontrado.')
                return render(request, 'analitica/superset_subir_csv.html', {
                    'conjuntos': conjuntos,
                    'superset_disponible': service.health_check(),
                })

        if not archivo:
            messages.error(
                request,
                'Debe seleccionar un archivo CSV, TSV o Excel, o un '
                'conjunto de datos existente.')
            return render(request, 'analitica/superset_subir_csv.html', {
                'conjuntos': conjuntos,
                'superset_disponible': service.health_check(),
            })

        # Nombre automático desde el archivo si el campo quedó vacío,
        # y normalización a identificador seguro para PostgreSQL
        if not nombre_tabla:
            nombre_tabla = os.path.splitext(
                os.path.basename(archivo.name))[0]
        nombre_tabla = slugify(nombre_tabla)[:40].strip('-').replace('-', '_')
        if not nombre_tabla:
            messages.error(
                request, 'Debe especificar un nombre para la tabla.')

            return render(request, 'analitica/superset_subir_csv.html', {
                'conjuntos': conjuntos,
                'superset_disponible': service.health_check(),
            })

        resultado = service.subir_csv(archivo, nombre_tabla)

        if resultado.get('success'):
            # Registrar en DatasetBI: la visibilidad elegida decide quién
            # puede consumirlo en SIIED BI / Don Datico BI.
            visibilidad = request.POST.get('visibilidad', 'propio')
            if visibilidad not in dict(
                    DatasetBI.VISIBILIDAD_CHOICES):
                visibilidad = 'propio'
            # Id del dataset en Superset: permite eliminarlo después.
            ds_id = next(
                (d['id'] for d in service.listar_datasets()
                 if d.get('table_name') == nombre_tabla), None)
            DatasetBI.objects.update_or_create(
                nombre_tabla=nombre_tabla,
                defaults={
                    'usuario': request.user,
                    'organismo': organismo_perfil,
                    'visibilidad': visibilidad,
                    'dataset_id': ds_id,
                    'activo': True,
                })
            messages.success(
                request,
                f'Dataset "{nombre_tabla}" creado exitosamente en Superset '
                f'(visibilidad: {visibilidad}). '
                'Ya puede usarlo para crear gráficos y dashboards.')
            return redirect('indicadores:analitica_superset')
        else:
            messages.error(
                request,
                'Error al subir CSV: '
                f'{resultado.get("error", "Error desconocido")}')

    return render(request, 'analitica/superset_subir_csv.html', {
        'conjuntos': conjuntos,
        'superset_disponible': service.health_check(),
    })


def _crear_dataset_gsheet_bi(request, service, url_gsheet,
                             organismo_perfil, conjuntos):
    """Dataset Superset sobre un Google Sheet público + registro DatasetBI.

    El table_name es la URL completa (incluye #gid=N → pestaña elegida);
    se guarda igual para que la reconciliación por nombre la encuentre."""
    render_form = lambda: render(  # noqa: E731
        request, 'analitica/superset_subir_csv.html', {
            'conjuntos': conjuntos,
            'superset_disponible': service.health_check(),
        })
    if len(url_gsheet) > 200:
        messages.error(
            request, 'La URL es demasiado larga (máx. 200 caracteres).')
        return render_form()

    resultado = service.crear_dataset_gsheet(url_gsheet)
    if not resultado.get('success'):
        messages.error(
            request,
            'Error creando dataset de Google Sheet: '
            f'{resultado.get("error", "Error desconocido")}')
        return render_form()

    visibilidad = request.POST.get('visibilidad', 'propio')
    if visibilidad not in dict(DatasetBI.VISIBILIDAD_CHOICES):
        visibilidad = 'propio'
    DatasetBI.objects.update_or_create(
        nombre_tabla=url_gsheet,
        defaults={
            'usuario': request.user,
            'organismo': organismo_perfil,
            'visibilidad': visibilidad,
            'dataset_id': resultado.get('dataset_id'),
            'activo': True,
        })
    messages.success(
        request,
        'Dataset de Google Sheet creado en Superset '
        f'(visibilidad: {visibilidad}). '
        'Ya puede usarlo para crear gráficos y dashboards.')
    return redirect('indicadores:analitica_superset')


def _nombre_tabla_siied(prefijo, pk, nombre):
    """Nombre de tabla determinístico para datasets sincronizados.

    El prefijo identifica la familia (conjunto_/catalogo_) y el pk hace el
    nombre único, así re-sincronizar reemplaza la misma tabla en Superset.
    """
    slug = slugify(nombre)[:40].strip('-').replace('-', '_') or 'sin_nombre'
    return f"{prefijo}_{pk}_{slug}"


def _catalogo_a_csv(catalogo):
    """Genera un CSV en memoria desde CatalogoConsulta.filas (JSON)."""
    columnas = catalogo.columnas or sorted(
        {k for fila in catalogo.filas for k in fila})
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columnas, extrasaction='ignore')
    writer.writeheader()
    for fila in catalogo.filas:
        writer.writerow({k: fila.get(k, '') for k in columnas})
    data = io.BytesIO(buf.getvalue().encode('utf-8-sig'))
    data.name = f"{_nombre_tabla_siied('catalogo', catalogo.pk, catalogo.nombre)}.csv"
    return data


def _archivo_a_memoria(archivo_field, nombre=None):
    """Lee un FileField a BytesIO con nombre de archivo limpio (basename)."""
    archivo_field.open('rb')
    try:
        data = io.BytesIO(archivo_field.read())
    finally:
        archivo_field.close()
    data.name = nombre or os.path.basename(archivo_field.name)
    return data


# SQL de la vista plana de indicadores (la misma de vista_indicadores_datos).
# Se reutiliza para generar datasets virtuales filtrados por tema.
_SQL_INDICADORES_BASE = """SELECT
  d.id AS dato_id,
  i.id AS indicador_id,
  i.nombre AS indicador,
  i.codigo_indicador,
  i.unidad_medida,
  i.frecuencia_difusion AS periodicidad,
  dom.nombre AS dominio,
  t.nombre AS tema,
  st.nombre AS subtema,
  d.fecha_dato,
  EXTRACT(YEAR FROM d.fecha_dato)::int AS anio,
  d.valor_dato,
  COALESCE(dg.nombre, 'Total') AS desagregacion_geografica,
  COALESCE(dt.nombre, 'Total') AS desagregacion_tematica
FROM indicadores_dato d
JOIN indicadores_indicador i ON d.indicador_id = i.id
JOIN indicadores_menusubtema st ON i.subtema_id = st.id
JOIN indicadores_menutema t ON st.tema_id = t.id
JOIN indicadores_menudominio dom ON t.dominio_id = dom.id
LEFT JOIN indicadores_dato_desagregaciones_geograficas ddg_rel
  ON d.id = ddg_rel.dato_id
LEFT JOIN indicadores_desagregacion dg ON ddg_rel.desagregacion_id = dg.id
LEFT JOIN indicadores_dato_desagregaciones_tematicas ddt_rel
  ON d.id = ddt_rel.dato_id
LEFT JOIN indicadores_desagregacion dt ON ddt_rel.desagregacion_id = dt.id
WHERE i.activo = true"""

# ============================================================================
# Datasets virtuales por módulo: FICED, Taller de Gestión de Datos, Satisfacción
# ============================================================================

_SQL_FICED_FORMULARIOS = """SELECT
  f.id,
  o.nombre AS organismo,
  o.codigo AS codigo_organismo,
  f.periodo,
  f.equipo,
  f.estado,
  f.puntaje_b AS puntaje_entorno_institucional,
  f.puntaje_c AS puntaje_infraestructura,
  f.puntaje_d AS puntaje_metodologia_estadistica,
  f.puntaje_e AS puntaje_accesibilidad_uso,
  f.puntaje_global,
  f.fecha_envio,
  f.fecha_validacion,
  f.fecha_creacion
FROM indicadores_icedformulario f
JOIN indicadores_organismo o ON f.organismo_id = o.id"""

_SQL_FICED_RRHH = """SELECT
  rh.id,
  o.nombre AS organismo,
  f.periodo,
  f.equipo AS equipo_ficed,
  rh.grupo,
  rh.tipo_vinculacion,
  rh.categoria_cargo,
  rh.nivel_formacion,
  rh.anios_experiencia,
  rh.funciones_estadisticas,
  jsonb_array_length(COALESCE(rh.etapas_proceso, '[]'::jsonb)) AS n_etapas_proceso
FROM indicadores_icedrecursohumano rh
JOIN indicadores_icedformulario f ON rh.formulario_id = f.id
JOIN indicadores_organismo o ON f.organismo_id = o.id"""

_SQL_FICED_DIMENSIONES = """SELECT f.id AS formulario_id, o.nombre AS organismo, f.periodo, f.equipo, f.estado,
       'B · Entorno Institucional' AS dimension, f.puntaje_b AS puntaje
FROM indicadores_icedformulario f JOIN indicadores_organismo o ON f.organismo_id = o.id
WHERE f.puntaje_b IS NOT NULL
UNION ALL
SELECT f.id, o.nombre, f.periodo, f.equipo, f.estado,
       'C · Infraestructura', f.puntaje_c
FROM indicadores_icedformulario f JOIN indicadores_organismo o ON f.organismo_id = o.id
WHERE f.puntaje_c IS NOT NULL
UNION ALL
SELECT f.id, o.nombre, f.periodo, f.equipo, f.estado,
       'D · Metodología Estadística', f.puntaje_d
FROM indicadores_icedformulario f JOIN indicadores_organismo o ON f.organismo_id = o.id
WHERE f.puntaje_d IS NOT NULL
UNION ALL
SELECT f.id, o.nombre, f.periodo, f.equipo, f.estado,
       'E · Accesibilidad y Uso', f.puntaje_e
FROM indicadores_icedformulario f JOIN indicadores_organismo o ON f.organismo_id = o.id
WHERE f.puntaje_e IS NOT NULL"""

_SQL_TALLER_INSCRIPCIONES = """SELECT
  i.id,
  o.nombre AS organismo,
  sg.nombre AS suborganismo,
  eq.nombre AS equipo,
  i.estado,
  i.ficha_inicial,
  i.paso_actual,
  i.edicion,
  i.nombre_completo,
  i.creado AS fecha_inscripcion,
  i.actualizado AS fecha_actualizacion
FROM indicadores_inscripciontaller i
JOIN indicadores_organismo o ON i.organismo_id = o.id
LEFT JOIN indicadores_suborganismo sg ON i.suborganismo_id = sg.id
LEFT JOIN indicadores_equipoorganismo eq ON i.equipo_id = eq.id"""

_SQL_TALLER_RETOS = """SELECT
  r.id,
  r.nombre AS reto,
  r.estado_seguimiento,
  o.nombre AS organismo,
  eq.nombre AS equipo,
  (SELECT COUNT(*) FROM indicadores_fuenterequerida fr
    WHERE fr.reto_id = r.id) AS n_fuentes_requeridas,
  (r.fusionado_en_id IS NOT NULL) AS absorbido_por_otro_reto,
  i.creado AS fecha_inscripcion
FROM indicadores_retoanalisis r
JOIN indicadores_inscripciontaller i ON r.inscripcion_id = i.id
JOIN indicadores_organismo o ON i.organismo_id = o.id
LEFT JOIN indicadores_equipoorganismo eq ON i.equipo_id = eq.id"""

_SQL_TALLER_FUENTES = """SELECT
  fd.id,
  fd.nombre AS fuente,
  o.nombre AS organismo,
  fd.rol,
  fd.georreferenciacion,
  fd.capa,
  fd.num_registros,
  fd.tiene_diccionario,
  (SELECT COUNT(*) FROM indicadores_variablefuente v
    WHERE v.fuente_id = fd.id) AS n_variables,
  (SELECT COUNT(*) FROM indicadores_fuentedatos_etiquetas e
    WHERE e.fuentedatos_id = fd.id) AS n_etiquetas,
  (fd.fusionada_en_id IS NOT NULL) AS absorbida_por_otra_fuente,
  fd.fecha_inicio,
  fd.fecha_actualizacion
FROM indicadores_fuentedatos fd
JOIN indicadores_inscripciontaller i ON fd.inscripcion_id = i.id
JOIN indicadores_organismo o ON i.organismo_id = o.id"""

_SQL_TALLER_EVALUACIONES = """SELECT
  es.id,
  fd.nombre AS fuente,
  o.nombre AS organismo,
  es.contiene_datos_personales,
  es.base_legitima,
  es.datos_necesarios,
  es.salvaguardas,
  es.transparencia,
  es.riesgo_dano,
  (SELECT COUNT(*) FROM indicadores_evaluacionseguridad_datos_sensibles ds
    WHERE ds.evaluacionseguridad_id = es.id) AS n_datos_sensibles
FROM indicadores_evaluacionseguridad es
JOIN indicadores_fuentedatos fd ON es.fuente_id = fd.id
JOIN indicadores_inscripciontaller i ON fd.inscripcion_id = i.id
JOIN indicadores_organismo o ON i.organismo_id = o.id"""

_SQL_TALLER_AVANCES = """SELECT
  a.id,
  fd.nombre AS fuente,
  o.nombre AS organismo,
  a.hito,
  a.nota,
  a.creado AS fecha_avance,
  EXTRACT(YEAR FROM a.creado)::int AS anio
FROM indicadores_avanceformalizacion a
JOIN indicadores_fuentedatos fd ON a.fuente_id = fd.id
JOIN indicadores_inscripciontaller i ON fd.inscripcion_id = i.id
JOIN indicadores_organismo o ON i.organismo_id = o.id"""

_SQL_SATISF_RESPUESTAS = """SELECT
  r.id,
  o.nombre AS organismo,
  eq.nombre AS equipo,
  r.fecha_respuesta_solicitud,
  EXTRACT(YEAR FROM r.fecha_respuesta_solicitud)::int AS anio,
  EXTRACT(MONTH FROM r.fecha_respuesta_solicitud)::int AS mes,
  r.utilidad_tiempo_respuesta,
  r.utilidad_claridad,
  r.relevancia_periodicidad,
  r.relevancia_concordancia,
  r.accesibilidad_canal,
  r.accesibilidad_formato,
  ROUND((
    COALESCE(r.utilidad_tiempo_respuesta, 0)
    + COALESCE(r.utilidad_claridad, 0)
    + COALESCE(r.relevancia_periodicidad, 0)
    + COALESCE(r.relevancia_concordancia, 0)
    + COALESCE(r.accesibilidad_canal, 0)
    + COALESCE(r.accesibilidad_formato, 0)
  )::numeric / 6, 2) AS promedio,
  r.razon_insatisfaccion,
  r.fecha_registro
FROM indicadores_respuestasatisfaccioncompleta r
JOIN indicadores_organismo o ON r.organismo_id = o.id
LEFT JOIN indicadores_equipoorganismo eq ON r.equipo_id = eq.id"""

_SQL_SATISF_DIMENSIONES = """SELECT r.id AS respuesta_id, o.nombre AS organismo, eq.nombre AS equipo,
       r.fecha_respuesta_solicitud,
       'Utilidad · Tiempo de respuesta' AS dimension, r.utilidad_tiempo_respuesta AS puntaje
FROM indicadores_respuestasatisfaccioncompleta r
JOIN indicadores_organismo o ON r.organismo_id = o.id
LEFT JOIN indicadores_equipoorganismo eq ON r.equipo_id = eq.id
WHERE r.utilidad_tiempo_respuesta IS NOT NULL
UNION ALL
SELECT r.id, o.nombre, eq.nombre, r.fecha_respuesta_solicitud,
       'Utilidad · Claridad', r.utilidad_claridad
FROM indicadores_respuestasatisfaccioncompleta r
JOIN indicadores_organismo o ON r.organismo_id = o.id
LEFT JOIN indicadores_equipoorganismo eq ON r.equipo_id = eq.id
WHERE r.utilidad_claridad IS NOT NULL
UNION ALL
SELECT r.id, o.nombre, eq.nombre, r.fecha_respuesta_solicitud,
       'Relevancia · Periodicidad', r.relevancia_periodicidad
FROM indicadores_respuestasatisfaccioncompleta r
JOIN indicadores_organismo o ON r.organismo_id = o.id
LEFT JOIN indicadores_equipoorganismo eq ON r.equipo_id = eq.id
WHERE r.relevancia_periodicidad IS NOT NULL
UNION ALL
SELECT r.id, o.nombre, eq.nombre, r.fecha_respuesta_solicitud,
       'Relevancia · Concordancia', r.relevancia_concordancia
FROM indicadores_respuestasatisfaccioncompleta r
JOIN indicadores_organismo o ON r.organismo_id = o.id
LEFT JOIN indicadores_equipoorganismo eq ON r.equipo_id = eq.id
WHERE r.relevancia_concordancia IS NOT NULL
UNION ALL
SELECT r.id, o.nombre, eq.nombre, r.fecha_respuesta_solicitud,
       'Accesibilidad · Canal', r.accesibilidad_canal
FROM indicadores_respuestasatisfaccioncompleta r
JOIN indicadores_organismo o ON r.organismo_id = o.id
LEFT JOIN indicadores_equipoorganismo eq ON r.equipo_id = eq.id
WHERE r.accesibilidad_canal IS NOT NULL
UNION ALL
SELECT r.id, o.nombre, eq.nombre, r.fecha_respuesta_solicitud,
       'Accesibilidad · Formato', r.accesibilidad_formato
FROM indicadores_respuestasatisfaccioncompleta r
JOIN indicadores_organismo o ON r.organismo_id = o.id
LEFT JOIN indicadores_equipoorganismo eq ON r.equipo_id = eq.id
WHERE r.accesibilidad_formato IS NOT NULL"""


def _sincronizar_datasets_siied(service):
    """Sube ConjuntoDatos y Catálogos de Consulta como datasets de Superset,
    y crea los datasets virtuales de indicadores (global + por tema).

    Retorna una lista de resultados: {fuente, tabla, ok, skip, error}.
    """
    resultados = []

    for conjunto in ConjuntoDatos.objects.order_by('nombre'):
        tabla = _nombre_tabla_siied('conjunto', conjunto.pk, conjunto.nombre)
        fuente = f"Conjunto «{conjunto.nombre}»"
        if not conjunto.archivo_csv:
            resultados.append({
                'fuente': fuente, 'tabla': tabla, 'ok': False,
                'skip': True, 'error': 'sin archivo cargado'})
            continue
        try:
            if not os.path.exists(conjunto.archivo_csv.path):
                resultados.append({
                    'fuente': fuente, 'tabla': tabla, 'ok': False,
                    'skip': True,
                    'error': 'archivo no encontrado en disco '
                             '(registro huérfano — vuelva a cargarlo)'})
                continue
            archivo = _archivo_a_memoria(conjunto.archivo_csv)
            res = service.subir_csv(archivo, tabla)
        except Exception as e:
            res = {'error': str(e)}
        resultados.append({
            'fuente': fuente, 'tabla': tabla,
            'ok': bool(res.get('success')),
            'skip': False, 'error': res.get('error')})

    for catalogo in CatalogoConsulta.objects.filter(activo=True).order_by('nombre'):
        tabla = _nombre_tabla_siied('catalogo', catalogo.pk, catalogo.nombre)
        fuente = f"Catálogo «{catalogo.nombre}»"
        try:
            if catalogo.filas:
                archivo = _catalogo_a_csv(catalogo)
                res = service.subir_csv(archivo, tabla)
            elif catalogo.archivo and os.path.exists(catalogo.archivo.path):
                archivo = _archivo_a_memoria(catalogo.archivo)
                res = service.subir_csv(archivo, tabla)
            else:
                resultados.append({
                    'fuente': fuente, 'tabla': tabla, 'ok': False,
                    'skip': True,
                    'error': 'sin filas ni archivo fuente'})
                continue
        except Exception as e:
            res = {'error': str(e)}
        resultados.append({
            'fuente': fuente, 'tabla': tabla,
            'ok': bool(res.get('success')),
            'skip': False, 'error': res.get('error')})

    # --- Datasets virtuales de indicadores ---
    # Consultan las tablas en vivo (no copian datos): solo se crean los que
    # falten y nunca quedan desactualizados.
    existentes = {d.get('table_name') for d in service.listar_datasets()}

    if 'vista_indicadores_datos' not in existentes:
        res = service.crear_dataset_virtual(
            'vista_indicadores_datos', _SQL_INDICADORES_BASE)
        resultados.append({
            'fuente': 'Indicadores (vista global)', 'tabla': 'vista_indicadores_datos',
            'ok': bool(res.get('success')), 'skip': False,
            'error': res.get('error')})

    # Un dataset virtual por dominio: cada uno trae solo sus indicadores
    # pero conserva las columnas de taxonomía (dominio/tema/subtema).
    # Se incluyen dominios ocultos del menú público (ODS, Cali en Cifras):
    # para analítica lo relevante es que tengan datos, no que sean visibles.
    dominios = (MenuDominio.objects
                .filter(temas__subtemas__indicadores__activo=True,
                        temas__subtemas__indicadores__datos__isnull=False)
                .distinct().order_by('orden', 'nombre'))
    for dominio in dominios:
        tabla = _nombre_tabla_siied('dominio', dominio.pk, dominio.nombre)
        fuente = f"Dominio «{dominio.nombre}»"
        if tabla in existentes:
            continue
        sql = _SQL_INDICADORES_BASE + f"\n  AND dom.id = {int(dominio.pk)}"
        res = service.crear_dataset_virtual(tabla, sql)
        resultados.append({
            'fuente': fuente, 'tabla': tabla,
            'ok': bool(res.get('success') or res.get('exists')),
            'skip': False, 'error': res.get('error')})

    # --- Datasets virtuales por módulo (FICED, Taller, Satisfacción) ---
    datasets_modulos = {
        'ficed_formularios': _SQL_FICED_FORMULARIOS,
        'ficed_recursos_humanos': _SQL_FICED_RRHH,
        'ficed_dimensiones': _SQL_FICED_DIMENSIONES,
        'taller_inscripciones': _SQL_TALLER_INSCRIPCIONES,
        'taller_retos': _SQL_TALLER_RETOS,
        'taller_fuentes': _SQL_TALLER_FUENTES,
        'taller_evaluaciones': _SQL_TALLER_EVALUACIONES,
        'taller_avances': _SQL_TALLER_AVANCES,
        'satisf_respuestas': _SQL_SATISF_RESPUESTAS,
        'satisf_dimensiones': _SQL_SATISF_DIMENSIONES,
    }
    for tabla, sql in datasets_modulos.items():
        if tabla in existentes:
            continue
        res = service.crear_dataset_virtual(tabla, sql)
        resultados.append({
            'fuente': f'Módulo', 'tabla': tabla,
            'ok': bool(res.get('success') or res.get('exists')),
            'skip': False, 'error': res.get('error')})

    # Registrar los datasets base en DatasetBI (es_base_siied=True):
    # sin fila el analista_organismo no los ve — visibles_para solo
    # admite base SIIED, públicos y propios.
    gestionadas = {'vista_indicadores_datos'}
    gestionadas |= {r['tabla'] for r in resultados if r.get('ok')}
    gestionadas |= {
        n for n in existentes
        if n and n.startswith(('conjunto_', 'catalogo_', 'dominio_',
                               'ficed_', 'taller_', 'satisf_'))}
    for tabla in gestionadas:
        DatasetBI.objects.update_or_create(
            nombre_tabla=tabla,
            defaults={'es_base_siied': True, 'visibilidad': 'publico',
                      'activo': True})

    return resultados


@analista_required
def analitica_superset_sincronizar(request):
    """Sincroniza ConjuntoDatos y Catálogos de Consulta hacia Superset."""
    if request.method != 'POST':
        return redirect('indicadores:analitica_superset')
    service = SupersetService()
    if not service.health_check():
        messages.error(request, 'Superset no está disponible. '
                                'No se pudo sincronizar los datasets.')
        return redirect('indicadores:analitica_superset')

    resultados = _sincronizar_datasets_siied(service)
    ok = sum(1 for r in resultados if r['ok'])
    skip = sum(1 for r in resultados if r.get('skip'))
    for r in resultados:
        if r['ok']:
            messages.success(
                request, f"{r['fuente']} → dataset «{r['tabla']}»")
        elif r.get('skip'):
            messages.info(request, f"{r['fuente']}: {r['error']}")
        else:
            messages.warning(request, f"{r['fuente']}: {r['error']}")
    messages.info(
        request,
        f'Sincronización completada: {ok} dataset(s) actualizados'
        f'{f", {skip} omitidos" if skip else ""}.')
    return redirect('indicadores:analitica_superset')


@bi_required
def analitica_superset_explorar(request):
    """Abre la interfaz completa de Superset embebida."""
    return _superset_embed_view(
        request,
        '/superset/welcome/',
        page_title='Explorar SIIED BI',
        icon='compass')


@bi_required
def analitica_superset_manual(request):
    """Manual de uso de los Tableros Superset."""
    return render(request, 'analitica/superset_manual.html')


EXCEL_MAX_CELL = 32000  # límite real de celda: 32767; margen de seguridad


@bi_required
def analitica_geo_descargas(request):
    """Catálogo descargable de niveles/capas geográficas para tableros Superset.

    Cada nivel se descarga en XLSX o CSV con codigo/nombre (claves de join) y
    geojson. El XLSX omite geojson cuando excede el límite de celda de Excel
    (32767 caracteres) — para esas capas el CSV es la única vía completa.
    """
    niveles = NivelGeografico.objects.annotate(
        n_capas=Count('capas', distinct=True),
        n_elementos=Count('capas__elementos', distinct=True),
    ).order_by('id')

    # Tamaño máximo de geojson por nivel (define si el XLSX puede llevarlo)
    max_geo = {}
    for fila in (CapaGeoJSON.objects
                 .select_related('capa_geo')
                 .only('capa_geo', 'geojson')):
        nid = fila.capa_geo.nivel_geografico_id
        largo = len(fila.geojson or '')
        if largo > max_geo.get(nid, 0):
            max_geo[nid] = largo

    filas = [{
        'id': n.id,
        'nombre': n.nombre,
        'capas': n.n_capas,
        'elementos': n.n_elementos,
        'geo_exportados': CapaGeoJSON.objects.filter(
            capa_geo__nivel_geografico=n).count(),
        'excede_excel': max_geo.get(n.id, 0) > EXCEL_MAX_CELL,
    } for n in niveles]

    return render(request, 'analitica/superset_geo_descargas.html', {
        'niveles': filas,
        'excel_max_cell': EXCEL_MAX_CELL,
    })


@bi_required
def analitica_geo_exportar(request, nivel_id, formato):
    """Descarga las capas de un NivelGeografico como XLSX o CSV.

    Columnas: nivel_geografico, capa_id, capa, codigo, nombre, geojson.
    En XLSX, geojson va vacío (y geojson_excede=1) cuando la geometría supera
    el límite de celda de Excel — el CSV siempre la incluye completa.
    """
    nivel = get_object_or_404(NivelGeografico, pk=nivel_id)
    filas = (CapaGeoJSON.objects
             .filter(capa_geo__nivel_geografico=nivel)
             .select_related('capa_geo')
             .order_by('capa_geo__nombre', 'codigo'))

    if not filas.exists():
        messages.warning(
            request,
            f'«{nivel.nombre}» no tiene geometrías exportadas. Ejecute '
            f'`manage.py export_geojson_superset` primero.')
        return redirect('indicadores:analitica_geo_descargas')

    slug_n = slugify(nivel.nombre) or f'nivel_{nivel_id}'
    headers = ['nivel_geografico', 'capa_id', 'capa',
               'codigo', 'nombre', 'geojson', 'geojson_excede']

    def _fila(f, con_geo=True):
        g = f.geojson or ''
        excede = len(g) > EXCEL_MAX_CELL
        if con_geo:
            return [nivel.nombre, f.capa_geo_id, f.capa_geo.nombre,
                    f.codigo, f.nombre, '' if excede else g,
                    1 if excede else 0]
        return [nivel.nombre, f.capa_geo_id, f.capa_geo.nombre,
                f.codigo, f.nombre, g, 0]

    if formato == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = (
            f'attachment; filename="capas_geo_{slug_n}.csv"')
        resp.write('﻿')  # BOM para que Excel reconozca UTF-8
        w = csv.writer(resp)
        w.writerow(headers)
        for f in filas:
            # CSV siempre lleva el geojson completo (sin límite de celda)
            w.writerow(_fila(f, con_geo=False))
        return resp

    if formato == 'xlsx':
        try:
            from openpyxl import Workbook
        except ImportError:
            messages.error(request, 'openpyxl no está instalado; use el CSV.')
            return redirect('indicadores:analitica_geo_descargas')

        wb = Workbook()
        ws = wb.active
        ws.title = 'capas_geo'
        ws.append(headers)
        for f in filas:
            ws.append(_fila(f, con_geo=True))

        nota = wb.create_sheet('leeme')
        nota.append(['Columna geojson:'])
        nota.append(['  Si geojson_excede=1, la geometría supera el límite de '
                     'celda de Excel (32767 chars) y va vacía.'])
        nota.append(['  Para esas capas descargue el CSV, que la incluye '
                     'completa. Superset acepta CSV y Excel por igual.'])

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(
            buf.read(),
            content_type='application/vnd.openxmlformats-'
                         'officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = (
            f'attachment; filename="capas_geo_{slug_n}.xlsx"')
        return resp

    messages.error(request, f'Formato «{formato}» no soportado (use csv o xlsx).')
    return redirect('indicadores:analitica_geo_descargas')


# ============================================================================
# TABLEROS PÚBLICOS — guest token por visibilidad (TableroBI)
# ============================================================================

@xframe_options_exempt
def bi_tablero(request, dashboard_id):
    """Embed de un TableroBI según su nivel de visibilidad.

    - publico:      sin sesión; identidad 'anonimo_ciudadano'.
    - autenticado:  cualquier usuario SIIED logueado.
    - organismo:    login + perfil.organismo == tablero.organismo (RLS).
    - interno:      staff + analista + analista_organismo (es_bi).
    """
    tablero = get_object_or_404(
        TableroBI, dashboard_id=dashboard_id, activo=True)

    if tablero.visibilidad == 'interno' and not _es_bi(request):
        messages.error(request, 'Este tablero es solo para el equipo SIIED.')
        return redirect('indicadores:analitica_login')

    if tablero.visibilidad in ('autenticado', 'organismo', 'interno') \
            and not request.user.is_authenticated:
        return redirect(
            f"{reverse('indicadores:delegado_login')}"
            f"?next={request.get_full_path()}")

    acceso = _bi_tablero_auth(request, tablero)
    if acceso is None:
        messages.error(
            request, 'Este tablero es exclusivo de otro organismo.')
        return redirect('indicadores:index')

    embed_uuid, guest_token = _bi_mint_tablero(tablero, *acceso)

    if not (embed_uuid and guest_token):
        logger.warning(
            f"bi_tablero: guest token no disponible para dashboard "
            f"{dashboard_id} (embed_uuid={embed_uuid})")
        messages.error(
            request,
            'El tablero no está disponible en este momento.')
        return redirect('indicadores:index')

    return render(request, 'analitica/superset_embed.html', {
        'embed_uuid': embed_uuid,
        'guest_token': guest_token,
        'guest_token_url': reverse(
            'indicadores:bi_guest_token', args=[dashboard_id]),
        'superset_domain': getattr(
            settings, 'SUPERSET_PUBLIC_URL', '').rstrip('/'),
        'page_title': tablero.titulo,
        'icon': 'chart-area',
        'login_ok': True,
    })


def _bi_tablero_auth(request, tablero):
    """(identidad, rls) si el request puede ver el tablero; None si no.

    `identidad` alimenta el claim `user` del guest token y `rls` sus
    cláusulas de row-level security. Es la misma política de visibilidad
    que aplica bi_tablero, compartida con bi_tablero_embed y
    bi_guest_token (la vista HTML añade redirecciones/mensajes propios).
    """
    if tablero.visibilidad == 'interno' and not _es_bi(request):
        return None
    if tablero.visibilidad in ('autenticado', 'organismo', 'interno') \
            and not request.user.is_authenticated:
        return None

    rls = []
    if tablero.visibilidad == 'organismo':
        perfil = getattr(request.user, 'perfil_recolector', None)
        org_user = perfil.organismo if perfil else None
        if not request.user.is_staff \
                and org_user != tablero.organismo:
            return None
        if tablero.rls_clause:
            rls = [{'clause': tablero.rls_clause}]
        elif org_user:
            rls = [{'clause': f"organismo = '{org_user.nombre}'"}]
    elif tablero.rls_clause:
        rls = [{'clause': tablero.rls_clause}]

    identidad = (
        {'username': request.user.username,
         'first_name': request.user.first_name or '',
         'last_name': request.user.last_name or ''}
        if request.user.is_authenticated
        else {'username': 'anonimo_ciudadano',
              'first_name': 'Ciudadano', 'last_name': ''})
    return identidad, rls


def _bi_mint_tablero(tablero, identidad, rls):
    """Retorna (embed_uuid, guest_token); (None, None) si el minteo falla."""
    service = SupersetService()
    embed_uuid = service.get_or_create_embed_id(tablero.dashboard_id)
    if not embed_uuid:
        return None, None
    return embed_uuid, service.get_guest_token(
        embed_uuid, rls=rls, **identidad)


@xframe_options_exempt
def bi_tablero_embed(request, dashboard_id):
    """Versión 'bare' del embed: solo el tablero, sin chrome del portal.

    Es el destino del <iframe> copiable desde el listado de tableros.
    El guest token se refresca vía bi_guest_token (expira en ~5 min).
    Sin acceso, responde 403 dentro del iframe en vez de redirigir.
    """
    tablero = get_object_or_404(
        TableroBI, dashboard_id=dashboard_id, activo=True)

    acceso = _bi_tablero_auth(request, tablero)
    if acceso is None:
        return render(
            request, 'analitica/superset_embed_bare.html',
            {'acceso_denegado': True, 'page_title': tablero.titulo},
            status=403)

    embed_uuid, guest_token = _bi_mint_tablero(tablero, *acceso)
    if not (embed_uuid and guest_token):
        logger.warning(
            f"bi_tablero_embed: guest token no disponible para dashboard "
            f"{dashboard_id} (embed_uuid={embed_uuid})")

    return render(request, 'analitica/superset_embed_bare.html', {
        'embed_uuid': embed_uuid or '',
        'guest_token': guest_token or '',
        'guest_token_url': reverse(
            'indicadores:bi_guest_token', args=[dashboard_id]),
        'superset_domain': getattr(
            settings, 'SUPERSET_PUBLIC_URL', '').rstrip('/'),
        'page_title': tablero.titulo,
        'acceso_denegado': False,
    })


def bi_guest_token(request, dashboard_id):
    """JSON {"token": ...}: refresco del guest token para el embedded-sdk.

    Aplica la misma visibilidad de bi_tablero; sin acceso responde 403.
    """
    tablero = get_object_or_404(
        TableroBI, dashboard_id=dashboard_id, activo=True)
    acceso = _bi_tablero_auth(request, tablero)
    if acceso is None:
        return JsonResponse({'error': 'forbidden'}, status=403)
    _, guest_token = _bi_mint_tablero(tablero, *acceso)
    if not guest_token:
        return JsonResponse({'error': 'unavailable'}, status=503)
    return JsonResponse({'token': guest_token})


# ============================================================================
# LINK PÚBLICO POR ENLACE — URL firmada, sin login SIIED ni Superset
# ============================================================================

_BI_FIRMA_SALT = 'siied.bi.compartir'


def _bi_firma_link(dashboard_id):
    """Token firmado del dashboard_id para el link público por enlace.

    La firma usa SECRET_KEY: rotarla invalida los enlaces emitidos.
    """
    return Signer(salt=_BI_FIRMA_SALT).sign(str(dashboard_id))


def _bi_firma_ok(dashboard_id, token):
    try:
        return Signer(salt=_BI_FIRMA_SALT).unsign(token) \
            == str(dashboard_id)
    except BadSignature:
        return False


def _bi_acceso_enlace(tablero):
    """(identidad, rls) para acceso por enlace firmado: anónimo + RLS fija."""
    identidad = {'username': 'anonimo_enlace',
                 'first_name': 'Enlace', 'last_name': 'SIIED'}
    rls = [{'clause': tablero.rls_clause}] if tablero.rls_clause else []
    return identidad, rls


@xframe_options_exempt
def bi_tablero_publico(request, dashboard_id, token):
    """Página pública por enlace firmado: quien tenga el link ve el tablero
    sin sesión SIIED ni Superset (guest token anónimo).

    El token es la firma del dashboard_id — no es enumerable ni
    falsificable, y solo lo genera quien gestiona el tablero desde
    Analítica. Un link inválido responde 404 para no filtrar existencia.
    """
    if not _bi_firma_ok(dashboard_id, token):
        raise Http404
    tablero = get_object_or_404(
        TableroBI, dashboard_id=dashboard_id, activo=True)
    embed_uuid, guest_token = _bi_mint_tablero(
        tablero, *_bi_acceso_enlace(tablero))
    if not (embed_uuid and guest_token):
        logger.warning(
            f"bi_tablero_publico: guest token no disponible para "
            f"dashboard {dashboard_id} (embed_uuid={embed_uuid})")
    return render(request, 'analitica/superset_embed_bare.html', {
        'embed_uuid': embed_uuid or '',
        'guest_token': guest_token or '',
        'guest_token_url': reverse(
            'indicadores:bi_guest_token_publico',
            args=[dashboard_id, token]),
        'superset_domain': getattr(
            settings, 'SUPERSET_PUBLIC_URL', '').rstrip('/'),
        'page_title': tablero.titulo,
        'acceso_denegado': False,
    })


def bi_guest_token_publico(request, dashboard_id, token):
    """Refresco del guest token para el enlace firmado (sin sesión).

    Misma firma que bi_tablero_publico: sin ella, 403.
    """
    if not _bi_firma_ok(dashboard_id, token):
        return JsonResponse({'error': 'forbidden'}, status=403)
    tablero = get_object_or_404(
        TableroBI, dashboard_id=dashboard_id, activo=True)
    _, guest_token = _bi_mint_tablero(
        tablero, *_bi_acceso_enlace(tablero))
    if not guest_token:
        return JsonResponse({'error': 'unavailable'}, status=503)
    return JsonResponse({'token': guest_token})
