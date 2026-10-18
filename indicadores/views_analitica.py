"""
Módulo Analítica e Inteligencia Artificial.

Acceso: rol 'analista' (y staff). Reúne en un solo lugar la administración
de la IA del portal (parámetros, contextos/prompts y consultas sugeridas de
Don Datico — el mismo formulario de ConfiguracionSistema que usa el admin) y,
a futuro, el acceso a la generación de tableros de Superset.
"""

import os
import re
import importlib

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.conf import settings
from django.core.cache import cache

from .decorators import analista_required
from .forms_chat_config import ChatConfigForm, ChatContextForm, ChatSuggestionsForm
from . import chat_config
from .models import ConfiguracionSistema


# ============================================================================
# AUTENTICACIÓN
# ============================================================================

def analitica_login(request):
    """Login del módulo Analítica e IA (analistas y staff)."""
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('indicadores:analitica_dashboard')
        if hasattr(request.user, 'perfil_recolector'):
            if request.user.perfil_recolector.es_analista():
                return redirect('indicadores:analitica_dashboard')
        auth_logout(request)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_staff or (
                hasattr(user, 'perfil_recolector') and
                user.perfil_recolector.es_analista()
            ):
                auth_login(request, user)
                messages.success(
                    request,
                    f'Bienvenido/a, {user.get_full_name() or user.username}')
                return redirect('indicadores:analitica_dashboard')
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
# TABLEROS SUPERSET (placeholder — integración futura)
# ============================================================================

@analista_required
def analitica_superset(request):
    """Acceso a la generación de tableros con Apache Superset.

    La integración está planificada; por ahora la página muestra el estado
    y actúa como ancla del futuro punto de entrada."""
    return render(request, 'analitica/superset.html')
