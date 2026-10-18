"""
Vistas para administrar la configuración del chat desde el panel de admin
"""
import os
import ast
import importlib
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from django.core.management import call_command
from django.views.decorators.csrf import csrf_protect
from io import StringIO
from .forms_chat_config import ChatConfigForm, ChatContextForm, ChatSuggestionsForm
from . import chat_config
from .models import DocumentoVector, Indicador, ProductoAcademico, DocumentoInfraestructura


@staff_member_required
def chat_config_view(request):
    """Vista para configurar parámetros del chat"""
    
    if request.method == 'POST':
        form = ChatConfigForm(request.POST)
        if form.is_valid():
            try:
                from .models import ConfiguracionSistema

                updated = 0
                for field_name, value in form.cleaned_data.items():
                    _, created = ConfiguracionSistema.objects.update_or_create(
                        clave=field_name,
                        defaults={'valor': value, 'descripcion': f'Configuración del chat: {field_name}'}
                    )
                    updated += 1

                # Limpiar caché de contexto para que la nueva config sea efectiva inmediatamente
                from django.core.cache import cache
                cache.delete(chat_config.CHAT_CONFIG.get('CONTEXT_CACHE_KEY', 'chat_system_context_v6'))

                messages.success(
                    request,
                    f'✅ Configuración guardada exitosamente ({updated} parámetros)'
                )
                return redirect('indicadores:admin_chat_config')

            except Exception as e:
                messages.error(request, f'❌ Error al guardar configuración: {str(e)}')
    else:
        # Cargar valores actuales para TODOS los campos del form:
        # get_config lee BD primero (ConfiguracionSistema), luego CHAT_CONFIG;
        # el .initial del field cubre claves sin default en CHAT_CONFIG.
        initial_data = {
            name: chat_config.get_config(name, field.initial)
            for name, field in ChatConfigForm.base_fields.items()
        }
        form = ChatConfigForm(initial=initial_data)
    
    context = {
        'form': form,
        'title': 'Configuración del Chat - Don Datico',
        'current_config': chat_config.CHAT_CONFIG,
    }
    
    return render(request, 'admin/chat_config.html', context)


@staff_member_required
def chat_contexts_view(request):
    """Vista para editar contextos del sistema"""
    
    # Obtener el contexto seleccionado
    selected_context = request.GET.get('context_key', 'don_datico_base')
    
    if request.method == 'POST':
        form = ChatContextForm(request.POST)
        if form.is_valid():
            try:
                context_key = form.cleaned_data['context_key']
                context_content = form.cleaned_data['context_content']
                
                # Leer el archivo actual
                config_file_path = os.path.join(
                    settings.BASE_DIR, 
                    'indicadores', 
                    'chat_config.py'
                )
                
                with open(config_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Escapar comillas triples en el contenido
                escaped_content = context_content.replace('"""', '\\"\\"\\"')
                
                # Buscar y reemplazar el contexto específico
                import re
                # Pattern para encontrar el contexto específico
                pattern = rf"'{context_key}':\s*\"\"\"[^\"]*\"\"\""
                
                # Construir el nuevo contexto
                new_context_str = f"'{context_key}': \"\"\"{context_content}\"\"\""
                
                # Reemplazar en el contenido
                new_content = re.sub(pattern, new_context_str, content, flags=re.DOTALL)
                
                # Guardar el archivo
                with open(config_file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                # Recargar el módulo
                importlib.reload(chat_config)
                
                messages.success(request, f'✅ Contexto "{context_key}" guardado exitosamente')
                return redirect(f'/admin/chat-contexts/?context_key={context_key}')
                
            except Exception as e:
                messages.error(request, f'❌ Error al guardar contexto: {str(e)}')
    else:
        # Cargar el contexto seleccionado
        initial_data = {
            'context_key': selected_context,
            'context_content': chat_config.CHAT_CONTEXTS.get(selected_context, ''),
        }
        form = ChatContextForm(initial=initial_data)
    
    # Obtener información sobre los contextos
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
    
    context = {
        'form': form,
        'title': 'Contextos del Sistema - Don Datico',
        'selected_context': selected_context,
        'contexts_info': contexts_info,
        'current_contexts': chat_config.CHAT_CONTEXTS,
    }
    
    return render(request, 'admin/chat_contexts.html', context)


@staff_member_required
@csrf_protect
def update_embeddings_view(request):
    """Vista para actualizar los embeddings vectoriales"""
    
    if request.method == 'POST':
        try:
            force = request.POST.get('force', '0') == '1'

            # Estadísticas ANTES (los 3 tipos de contenido)
            stats_antes = {
                'indicadores': {
                    'total': Indicador.objects.count(),
                    'embeddings': DocumentoVector.objects.filter(tipo='indicador').count(),
                },
                'productos_academicos': {
                    'total': ProductoAcademico.objects.filter(estado='publicado').count(),
                    'embeddings': DocumentoVector.objects.filter(tipo='producto_academico').count(),
                },
                'documentos_infraestructura': {
                    'total': DocumentoInfraestructura.objects.filter(activo=True, estado='publicado').count(),
                    'embeddings': DocumentoVector.objects.filter(tipo='documento_infraestructura').count(),
                },
            }

            out = StringIO()
            if force:
                call_command('generar_embeddings', '--force', '--batch-size=50', stdout=out, stderr=out)
            else:
                call_command('generar_embeddings', '--batch-size=50', stdout=out, stderr=out)

            # Estadísticas DESPUÉS
            stats_despues = {
                'indicadores': DocumentoVector.objects.filter(tipo='indicador').count(),
                'productos_academicos': DocumentoVector.objects.filter(tipo='producto_academico').count(),
                'documentos_infraestructura': DocumentoVector.objects.filter(tipo='documento_infraestructura').count(),
            }

            # Calcular procesados por tipo
            procesados_por_tipo = {
                k: stats_despues[k] - stats_antes[k]['embeddings']
                for k in stats_despues
            }
            total_procesados = sum(procesados_por_tipo.values())

            if force:
                mensaje = f'✅ Embeddings regenerados: {total_procesados} documentos vectorizados'
            else:
                mensaje = f'✅ Embeddings actualizados: {total_procesados} nuevos documentos vectorizados'

            return JsonResponse({
                'success': True,
                'message': mensaje,
                'force': force,
                'stats': {
                    'indicadores': {
                        'total': stats_antes['indicadores']['total'],
                        'embeddings': stats_despues['indicadores'],
                        'procesados': procesados_por_tipo['indicadores'],
                    },
                    'productos_academicos': {
                        'total': stats_antes['productos_academicos']['total'],
                        'embeddings': stats_despues['productos_academicos'],
                        'procesados': procesados_por_tipo['productos_academicos'],
                    },
                    'documentos_infraestructura': {
                        'total': stats_antes['documentos_infraestructura']['total'],
                        'embeddings': stats_despues['documentos_infraestructura'],
                        'procesados': procesados_por_tipo['documentos_infraestructura'],
                    },
                },
                'output': out.getvalue()
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'❌ Error al actualizar embeddings: {str(e)}',
                'error': str(e)
            }, status=500)
    
    # GET request - mostrar información de los 3 tipos de contenido
    context = {
        'title': 'Actualizar Embeddings Vectoriales',
        'stats': {
            'indicadores': {
                'total': Indicador.objects.count(),
                'embeddings': DocumentoVector.objects.filter(tipo='indicador').count(),
            },
            'productos_academicos': {
                'total': ProductoAcademico.objects.filter(estado='publicado').count(),
                'embeddings': DocumentoVector.objects.filter(tipo='producto_academico').count(),
            },
            'documentos_infraestructura': {
                'total': DocumentoInfraestructura.objects.filter(activo=True, estado='publicado').count(),
                'embeddings': DocumentoVector.objects.filter(tipo='documento_infraestructura').count(),
            },
        }
    }
    # Totales globales para compatibilidad con JS existente
    context['total_indicadores'] = context['stats']['indicadores']['total']
    context['embeddings_existentes'] = context['stats']['indicadores']['embeddings']
    context['sin_embeddings'] = context['stats']['indicadores']['total'] - context['stats']['indicadores']['embeddings']
    context['porcentaje_cobertura'] = round(
        (context['embeddings_existentes'] / context['total_indicadores'] * 100)
        if context['total_indicadores'] > 0 else 0, 1
    )
    return render(request, 'admin/update_embeddings.html', context)


@staff_member_required
def chat_suggestions_view(request):
    """Vista para editar las consultas sugeridas del chat"""
    
    # Obtener la categoría seleccionada
    selected_category = request.GET.get('category', 'exploratorias')
    
    if request.method == 'POST':
        form = ChatSuggestionsForm(request.POST)
        if form.is_valid():
            try:
                category = form.cleaned_data['category']
                suggestions_list = form.cleaned_data['suggestions']  # Ya es una lista limpia
                
                # Leer el archivo actual
                config_file_path = os.path.join(
                    settings.BASE_DIR, 
                    'indicadores', 
                    'chat_config.py'
                )
                
                with open(config_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Construir el nuevo diccionario CHAT_SUGGESTIONS completo
                # Primero obtener los valores actuales
                current_suggestions = dict(chat_config.CHAT_SUGGESTIONS)
                current_suggestions[category] = suggestions_list
                
                # Construir el string del diccionario
                suggestions_str = "CHAT_SUGGESTIONS = {\n"
                
                category_comments = {
                    'exploratorias': '    # Consultas exploratorias - para descubrir qué hay disponible',
                    'especificas': '    # Consultas específicas - búsquedas directas',
                    'comparativas': '    # Consultas comparativas - análisis temporal o entre categorías',
                    'datos_completos': '    # Consultas de datos completos - para obtener datasets',
                }
                
                for cat_key in ['exploratorias', 'especificas', 'comparativas', 'datos_completos']:
                    suggestions_str += f"{category_comments.get(cat_key, '')}\n"
                    suggestions_str += f'    "{cat_key}": [\n'
                    for suggestion in current_suggestions.get(cat_key, []):
                        # Escapar comillas en la sugerencia
                        escaped = suggestion.replace('"', '\\"')
                        suggestions_str += f'        "{escaped}",\n'
                    suggestions_str += '    ],\n'
                
                suggestions_str += "}"
                
                # Buscar y reemplazar CHAT_SUGGESTIONS en el contenido
                import re
                pattern = r'CHAT_SUGGESTIONS\s*=\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\}'
                new_content = re.sub(pattern, suggestions_str, content, flags=re.DOTALL)
                
                # Guardar el archivo
                with open(config_file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                # Recargar el módulo
                importlib.reload(chat_config)
                
                messages.success(request, f'✅ Consultas sugeridas de "{category}" guardadas exitosamente')
                return redirect(f'/admin/chat-suggestions/?category={category}')
                
            except Exception as e:
                messages.error(request, f'❌ Error al guardar: {str(e)}')
    else:
        # Cargar las sugerencias de la categoría seleccionada
        current_suggestions = chat_config.CHAT_SUGGESTIONS.get(selected_category, [])
        initial_data = {
            'category': selected_category,
            'suggestions': '\n'.join(current_suggestions),
        }
        form = ChatSuggestionsForm(initial=initial_data)
    
    # Info de categorías para mostrar en el template
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
    
    context = {
        'form': form,
        'title': 'Consultas Sugeridas - Chat Don Datico',
        'selected_category': selected_category,
        'categories_info': categories_info,
        'current_suggestions': chat_config.CHAT_SUGGESTIONS,
    }
    
    return render(request, 'admin/chat_suggestions.html', context)
