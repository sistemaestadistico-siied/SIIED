"""
Views del sistema SIIED (Sistema de Información e Indicadores Estadísticos)
"""
# Standard library imports
import csv
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, date
from types import SimpleNamespace
from typing import Dict, List, Optional, Any, Generator

# Third-party imports
import humanize
import pandas as pd
import requests
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification

# Django core imports
from django.apps import apps
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection, models
from django.db.models import Q, Sum, Count, Max, Min, Prefetch
from django.http import JsonResponse, StreamingHttpResponse, FileResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Local application imports
from .cache_utils import cache_grafico_data, get_cached_desagregaciones
from .chat_config import CHAT_CONFIG, CHAT_CONTEXTS, get_context, get_config
from .embeddings import EmbeddingService
from .models import (
    MenuDominio, MenuTema, MenuSubtema, Indicador, Dato,
    Desagregacion, DominioDesagregacion, NivelGeografico, CapaGeo, ElementoGeo,
    CategoriaInformacion, SistemaInformacion, CategoriaProyecto, ProyectoInformacion,
    NoticiaBanner, AreaInfraestructura, CategoriaInfraestructura, SubcategoriaInfraestructura,
    GrupoDocumento, DocumentoInfraestructura, Grafico, GraficoSerie, Aliado, Evento,
    DocumentoVector, ConjuntoDatos, OperacionEstadistica, ProcesoExtraccion, ProcesoLog,
    ProductoAcademico, SeccionPaper, CatalogoDominio, CatalogoConsulta, Organismo
)
from .search import SemanticSearch
from collections import defaultdict as _dd
from django.db.models import Sum, Q, Max, Case, When, IntegerField, Value, Count, F, FloatField
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from openai import OpenAI
import re
import traceback
import numpy as np
# Extraer términos individuales de la consulta (sin stopwords)
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import string
from django.db.models.functions import Concat, Length, Replace, Lower, Greatest, Coalesce, Now
# Try to import TTS, fallback to pico2wave if not available
try:
    from TTS.api import TTS
    COQUI_TTS_AVAILABLE = True
    print("✅ Coqui TTS disponible")
except ImportError:
    COQUI_TTS_AVAILABLE = False
    print("⚠️ Coqui TTS no disponible, usando pico2wave como fallback")

# Optional imports
try:
    from pyproj import CRS, Transformer
except Exception:  # pragma: no cover - entorno sin pyproj
    CRS = None
    Transformer = None

from .views_chat import ChatService
# Logger configuration
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURACIÓN GLOBAL
# =============================================================================

# Configuración de tokens para chat
MAX_CONTEXT_TOKENS = getattr(settings, 'MAX_CONTEXT_TOKENS', 32000)
RESPONSE_TOKENS = getattr(settings, 'RESPONSE_TOKENS', 4000)
MAX_HISTORY_TOKENS = getattr(settings, 'MAX_HISTORY_TOKENS', MAX_CONTEXT_TOKENS - RESPONSE_TOKENS)
TOKENS_PER_CHAR = 0.25  # 1 token ≈ 4 caracteres (para español)

# Modelo de clasificación Zero-Shot
model_name = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir="./modelos")
model = AutoModelForSequenceClassification.from_pretrained(model_name, cache_dir="./modelos")
classifier = pipeline(
    "zero-shot-classification",
    use_fast=True,
    tokenizer=tokenizer,
    model=model,
    device=-1
)

# Diccionario para rastrear solicitudes activas por usuario único
# Clave: user_key (combinación de session_id + client_ip + user_agent hash)
# Esto permite que múltiples usuarios usen el chat simultáneamente sin bloquearse
active_requests = {}
active_requests_lock = threading.Lock()

# Locks por sesión para evitar bloqueo global
from threading import RLock
from contextlib import contextmanager
import hashlib

session_locks = {}
session_locks_lock = RLock()

def get_user_key(request):
    """Genera una clave única por usuario basada en sesión, IP y user agent"""
    session_id = request.session.session_key or 'anonymous'
    client_ip = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')[:100]
    
    # Crear hash del user agent para mantener la clave corta
    ua_hash = hashlib.md5(user_agent.encode()).hexdigest()[:8]
    
    # Combinar para crear clave única
    user_key = f"{session_id}_{client_ip}_{ua_hash}"
    return user_key

def get_session_lock(session_id):
    """Obtiene un lock específico para una sesión"""
    with session_locks_lock:
        if session_id not in session_locks:
            session_locks[session_id] = RLock()
        return session_locks[session_id]

@contextmanager
def safe_request_access(user_key):
    """Context manager para acceso seguro a active_requests de un usuario específico"""
    with active_requests_lock:
        yield active_requests.get(user_key)

def register_request_atomic(user_key, request_id):
    """Registra un request de forma atómica, cancelando el anterior del MISMO usuario si existe"""
    with active_requests_lock:
        # Cancelar request anterior del MISMO usuario si existe
        old = active_requests.pop(user_key, None)
        if old and 'abort_controller' in old:
            try:
                old['abort_controller'].set()
            except:
                pass
        
        # Crear nuevo abort controller
        abort_controller = threading.Event()
        
        # Registrar nuevo request
        active_requests[user_key] = {
            'abort_controller': abort_controller,
            'timestamp': timezone.now(),
            'request_id': request_id,
            'active': True
        }
        
        return abort_controller

def unregister_request_atomic(user_key, request_id):
    """Elimina un request de forma atómica solo si coincide el request_id"""
    with active_requests_lock:
        current = active_requests.get(user_key)
        if current and current.get('request_id') == request_id:
            active_requests.pop(user_key, None)
            return True
        return False

def is_request_cancelled(user_key, request_id):
    """Verifica si un request fue cancelado de forma thread-safe"""
    with active_requests_lock:
        current = active_requests.get(user_key)
        if not current:
            return True
        if current.get('request_id') != request_id:
            return True
        if current.get('abort_controller', threading.Event()).is_set():
            return True
        return not current.get('active', False)

# =============================================================================
# CLASES Y FUNCIONES AUXILIARES
# =============================================================================

class DateTimeEncoder(json.JSONEncoder):
    """Encoder JSON personalizado para objetos datetime"""
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


def classify_text(texto: str):
    """Clasifica texto usando zero-shot classification"""
    labels = getattr(settings, "ZERO_SHOT_LABELS", [])
    result = classifier(texto, candidate_labels=labels)
    return str(result["labels"][0])  # etiqueta con mayor score


def get_client_ip(request):
    """Obtiene la IP del cliente, considerando proxies"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# =============================================================================
# VISTAS
# =============================================================================

 
 
def acceso_modulos(request):
    """Vista para la página de acceso a módulos.
    Muestra siempre todas las cards. Si el usuario no está autenticado,
    los links lo llevan al login de cada módulo. Las restricciones reales
    se aplican en las vistas internas mediante los decoradores."""
    return render(request, 'indicadores/acceso_modulos.html')


def home(request):
    """Vista para la página de inicio con el banner"""
    # Carrusel: siempre las 5 noticias más recientes por fecha de publicación.
    # Las demás quedan consultables en el archivo (/noticias/).
    noticias = NoticiaBanner.objects.filter(activa=True).prefetch_related(
        'estadisticas', 'enlaces'
    ).order_by('-fecha_publicacion')[:5]
    
    # Obtener eventos futuros y actuales (próximos 30 días)
    ahora = timezone.now()
    fecha_limite = ahora + timezone.timedelta(days=30)
    
    # Depuración: registrar el rango de fechas
    logger.info(f'Buscando eventos entre {ahora} y {fecha_limite}')
    
    # Filtrar eventos que estén activos y que su fecha de fin sea posterior a ahora
    # o que su fecha de inicio sea dentro de los próximos 30 días
    eventos = Evento.objects.filter(
        activo=True
    ).filter(
        models.Q(fecha_fin__gte=ahora) | 
        models.Q(fecha_inicio__lte=ahora, fecha_fin__gte=ahora) |
        models.Q(fecha_inicio__range=(ahora, fecha_limite))
    ).order_by('fecha_inicio')[:6]  # Mostrar hasta 6 eventos
    
    # Depuración: registrar cuántos eventos se encontraron
    logger.info(f'Eventos encontrados: {eventos.count()}')
    for evento in eventos:
        logger.info(f'Evento: {evento.nombre} (Inicio: {evento.fecha_inicio}, Fin: {evento.fecha_fin}, Activo: {evento.activo})')
    
    return render(request, 'indicadores/home.html', {
        'page': 'inicio',
        'noticias': noticias,
        'eventos': eventos
    })


def visor_comparativo(request):
    # Usar el template standalone como visor principal
    dominios = MenuDominio.objects.filter(activo=True).order_by('orden')
    return render(request, 'indicadores/visor_comparativo_standalone.html', {
        'dominios': dominios
    })


def sistemas_informacion(request):
    """Vista para mostrar los sistemas de información organizados por categorías"""
    categorias = CategoriaInformacion.objects.filter(activo=True).prefetch_related(
        'sistemas'
    ).order_by('orden', 'nombre')
    
    # Agregar sistemas activos a cada categoría
    for categoria in categorias:
        categoria.sistemas_activos = categoria.sistemas.filter(activo=True).order_by('orden', 'nombre')
    
    context = {
        'categorias': categorias,
        'page_context': 'sistemas',  # Para el menú activo
    }
    
    return render(request, 'indicadores/sistemas_informacion.html', context)


def proyectos_informacion(request):
    """Vista para mostrar los proyectos de información organizados por categorías"""
    categorias = CategoriaProyecto.objects.filter(activo=True).prefetch_related(
        'proyectos'
    ).order_by('orden', 'nombre')
    
    # Agregar proyectos activos a cada categoría
    for categoria in categorias:
        categoria.proyectos_activos = categoria.proyectos.filter(activo=True).order_by('orden', 'nombre')
    
    context = {
        'categorias': categorias,
        'page_context': 'proyectos',  # Para el menú activo
    }
    
    return render(request, 'indicadores/proyectos_informacion.html', context)


def aliado_detalle(request, slug):
    """Vista para mostrar el detalle de un aliado"""
    aliado = get_object_or_404(Aliado, slug=slug, activo=True)
    
    context = {
        'aliado': aliado,
    }
    
    return render(request, 'indicadores/aliado_detalle.html', context)


def eventos_lista(request):
    """Vista para mostrar la lista de eventos"""
    # Obtener eventos futuros y actuales
    eventos_futuros = Evento.objects.filter(
        activo=True,
        fecha_inicio__gte=timezone.now()
    ).order_by('fecha_inicio')
    
    # Obtener eventos pasados (últimos 10)
    eventos_pasados = Evento.objects.filter(
        activo=True,
        fecha_fin__lt=timezone.now()
    ).order_by('-fecha_inicio')[:10]
    
    context = {
        'eventos_futuros': eventos_futuros,
        'eventos_pasados': eventos_pasados,
    }
    
    return render(request, 'indicadores/eventos_lista.html', context)


def evento_detalle(request, slug):
    """Vista para mostrar el detalle de un evento"""
    evento = get_object_or_404(Evento, slug=slug, activo=True)
    
    # Obtener eventos relacionados (próximos eventos)
    eventos_relacionados = Evento.objects.filter(
        activo=True,
        fecha_inicio__gte=timezone.now()
    ).exclude(id=evento.id).order_by('fecha_inicio')[:3]
    
    context = {
        'evento': evento,
        'eventos_relacionados': eventos_relacionados,
    }
    
    return render(request, 'indicadores/evento_detalle.html', context)


def noticias_lista(request):
    """Archivo público de noticias: todas las activas, orden cronológico,
    con búsqueda (?q=) y paginación para el archivo histórico migrado."""
    from django.core.paginator import Paginator

    noticias = NoticiaBanner.objects.filter(activa=True).prefetch_related(
        'estadisticas', 'enlaces'
    ).order_by('-fecha_publicacion')

    # Búsqueda libre por título, subtítulo o descripción
    q = request.GET.get('q', '').strip()
    if q:
        noticias = noticias.filter(
            models.Q(titulo__icontains=q) |
            models.Q(subtitulo__icontains=q) |
            models.Q(descripcion__icontains=q)
        )

    paginator = Paginator(noticias, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'indicadores/noticias_lista.html', {
        'page_obj': page_obj,
        'noticias': page_obj.object_list,
        'q': q,
        'total': paginator.count,
    })


# Vistas para Infraestructura de Información
def infraestructura_index(request):
    """Vista principal de infraestructura de información"""
    areas = AreaInfraestructura.objects.filter(activo=True).prefetch_related(
        'categorias'
    ).order_by('orden', 'nombre')
    
    # Agregar categorías activas a cada área
    for area in areas:
        area.categorias_activas = area.categorias.filter(activo=True).order_by('orden', 'nombre')
    
    context = {
        'areas': areas,
        'page_context': 'infraestructura',
    }
    
    return render(request, 'indicadores/infraestructura_navegacion.html', context)


def infraestructura_area(request, area_slug):
    """Vista de un área específica de infraestructura"""
    area = get_object_or_404(AreaInfraestructura, slug=area_slug, activo=True)
    areas = AreaInfraestructura.objects.filter(activo=True).prefetch_related(
        'categorias'
    ).order_by('orden', 'nombre')
    
    # Agregar categorías activas a cada área para la navegación
    for nav_area in areas:
        nav_area.categorias_activas = nav_area.categorias.filter(activo=True).order_by('orden', 'nombre')
    
    context = {
        'area': area,
        'areas': areas,
        'page_context': 'infraestructura',
    }
    
    return render(request, 'indicadores/infraestructura_navegacion.html', context)


def infraestructura_categoria(request, area_slug, categoria_slug):
    """Vista de una categoría específica de infraestructura"""
    area = get_object_or_404(AreaInfraestructura, slug=area_slug, activo=True)
    categoria = get_object_or_404(CategoriaInfraestructura, slug=categoria_slug, area=area, activo=True)
    
    areas = AreaInfraestructura.objects.filter(activo=True).prefetch_related(
        'categorias'
    ).order_by('orden', 'nombre')
    
    # Agregar categorías y subcategorías activas para la navegación
    for nav_area in areas:
        nav_area.categorias_activas = nav_area.categorias.filter(activo=True).order_by('orden', 'nombre')
        for nav_categoria in nav_area.categorias_activas:
            nav_categoria.subcategorias_activas = nav_categoria.subcategorias.filter(activo=True).order_by('orden', 'nombre')
    
    # Subcategorías de la categoría actual
    subcategorias = categoria.subcategorias.filter(activo=True).order_by('orden', 'nombre')
    
    context = {
        'area': area,
        'categoria': categoria,
        'subcategorias': subcategorias,
        'areas': areas,
        'page_context': 'infraestructura',
    }
    
    return render(request, 'indicadores/infraestructura_navegacion.html', context)


def infraestructura_subcategoria(request, area_slug, categoria_slug, subcategoria_slug):
    """Vista de una subcategoría específica de infraestructura"""
    area = get_object_or_404(AreaInfraestructura, slug=area_slug, activo=True)
    categoria = get_object_or_404(CategoriaInfraestructura, slug=categoria_slug, area=area, activo=True)
    subcategoria = get_object_or_404(SubcategoriaInfraestructura, slug=subcategoria_slug, categoria=categoria, activo=True)
    
    areas = AreaInfraestructura.objects.filter(activo=True).prefetch_related(
        'categorias'
    ).order_by('orden', 'nombre')
    
    # Agregar navegación completa
    for nav_area in areas:
        nav_area.categorias_activas = nav_area.categorias.filter(activo=True).order_by('orden', 'nombre')
        for nav_categoria in nav_area.categorias_activas:
            nav_categoria.subcategorias_activas = nav_categoria.subcategorias.filter(activo=True).order_by('orden', 'nombre')
    
    # Grupos de documentos de la subcategoría actual
    grupos_documentos = subcategoria.grupos_documentos.filter(activo=True).order_by('orden', 'nombre')
    
    context = {
        'area': area,
        'categoria': categoria,
        'subcategoria': subcategoria,
        'grupos_documentos': grupos_documentos,
        'areas': areas,
        'page_context': 'infraestructura',
    }
    
    return render(request, 'indicadores/infraestructura_navegacion.html', context)


def infraestructura_grupo(request, area_slug, categoria_slug, subcategoria_slug, grupo_slug):
    """Vista de un grupo de documentos específico de infraestructura"""
    area = get_object_or_404(AreaInfraestructura, slug=area_slug, activo=True)
    categoria = get_object_or_404(CategoriaInfraestructura, slug=categoria_slug, area=area, activo=True)
    subcategoria = get_object_or_404(SubcategoriaInfraestructura, slug=subcategoria_slug, categoria=categoria, activo=True)
    grupo_documento = get_object_or_404(GrupoDocumento, slug=grupo_slug, subcategoria=subcategoria, activo=True)
    
    areas = AreaInfraestructura.objects.filter(activo=True).prefetch_related('categorias').order_by('orden', 'nombre')
    
    # Agregar navegación completa
    for nav_area in areas:
        nav_area.categorias_activas = nav_area.categorias.filter(activo=True).order_by('orden', 'nombre')
        for nav_categoria in nav_area.categorias_activas:
            nav_categoria.subcategorias_activas = nav_categoria.subcategorias.filter(activo=True).order_by('orden', 'nombre')
    
    # Documentos del grupo actual
    documentos = grupo_documento.documentos.filter(activo=True, estado='publicado').order_by('orden', 'nombre')
    
    context = {
        'area': area,
        'categoria': categoria,
        'subcategoria': subcategoria,
        'grupo_documento': grupo_documento,
        'current_grupo': grupo_documento,
        'documentos': documentos,
        'areas': areas,
        'page_context': 'infraestructura'
    }
    
    return render(request, 'indicadores/infraestructura_navegacion.html', context)


def infraestructura_documento(request, area_slug, categoria_slug, subcategoria_slug, grupo_slug, documento_slug):
    """Vista de un documento específico de infraestructura"""
    area = get_object_or_404(AreaInfraestructura, slug=area_slug, activo=True)
    categoria = get_object_or_404(CategoriaInfraestructura, slug=categoria_slug, area=area, activo=True)
    subcategoria = get_object_or_404(SubcategoriaInfraestructura, slug=subcategoria_slug, categoria=categoria, activo=True)
    grupo_documento = get_object_or_404(GrupoDocumento, slug=grupo_slug, subcategoria=subcategoria, activo=True)
    documento = get_object_or_404(DocumentoInfraestructura, slug=documento_slug, grupo_documento=grupo_documento, activo=True, estado='publicado')
    
    areas = AreaInfraestructura.objects.filter(activo=True).prefetch_related(
        'categorias'
    ).order_by('orden', 'nombre')
    
    # Agregar navegación completa
    for nav_area in areas:
        nav_area.categorias_activas = nav_area.categorias.filter(activo=True).order_by('orden', 'nombre')
        for nav_categoria in nav_area.categorias_activas:
            nav_categoria.subcategorias_activas = nav_categoria.subcategorias.filter(activo=True).order_by('orden', 'nombre')
    
    context = {
        'area': area,
        'categoria': categoria,
        'subcategoria': subcategoria,
        'grupo_documento': grupo_documento,
        'documento': documento,
        'current_documento': documento,
        'current_grupo': grupo_documento,
        'areas': areas,
        'page_context': 'infraestructura',
    }
    
    return render(request, 'indicadores/infraestructura_documento.html', context)


def producto_academico(request, slug):
    """Vista de un Producto Académico. Público solo ve publicados;
    staff/superuser pueden previsualizar cualquier estado."""
    base_qs = ProductoAcademico.objects.prefetch_related('temas_relacionados')
    if request.user.is_authenticated and request.user.is_staff:
        producto = get_object_or_404(base_qs, slug=slug)
    else:
        producto = get_object_or_404(base_qs, slug=slug, estado='publicado')

    secciones = producto.secciones.all().select_related(
        'indicador_vinculado', 'conjunto_datos_vinculado',
        'documento_vinculado', 'sistema_vinculado', 'sistema_vinculado__categoria'
    ).prefetch_related('publicaciones_relacionadas').order_by('numero_orden', 'subnumero')

    # Precargar recursos vinculados para el JS frontend (una sola pasada)
    indicadores_vinculados = []
    mapas_vinculados = []
    tablas_indicador_vinculadas = []
    fichas_indicador_vinculadas = []
    tablas_conjunto_datos_vinculados = []
    resultados_destacados = []

    for s in secciones:
        if s.tipo_bloque == 'grafico_indicador' and s.indicador_vinculado:
            indicadores_vinculados.append({'id': s.indicador_vinculado.id, 'config': s.configuracion_grafico or {}})
        elif s.tipo_bloque == 'mapa_indicador' and s.indicador_vinculado:
            mapas_vinculados.append({'seccion_id': s.id, 'indicador_id': s.indicador_vinculado.id, 'config': s.configuracion_grafico or {}})
        elif s.tipo_bloque == 'tabla_datos_indicador' and s.indicador_vinculado:
            tablas_indicador_vinculadas.append({'seccion_id': s.id, 'indicador_id': s.indicador_vinculado.id, 'config': s.configuracion_grafico or {}})
        elif s.tipo_bloque == 'ficha_indicador' and s.indicador_vinculado:
            fichas_indicador_vinculadas.append({'seccion_id': s.id, 'indicador_id': s.indicador_vinculado.id})
        elif s.tipo_bloque == 'tabla_microdata' and s.conjunto_datos_vinculado:
            tablas_conjunto_datos_vinculados.append({'seccion_id': s.id, 'conjunto_datos_id': s.conjunto_datos_vinculado.id, 'config': s.configuracion_grafico or {}})
        elif s.tipo_bloque == 'resultado_destacado' and s.indicador_vinculado:
            resultados_destacados.append({'seccion_id': s.id, 'indicador_id': s.indicador_vinculado.id, 'config': s.configuracion_grafico or {}})

    # Agrupar secciones por tipo_seccion para modo producto estadístico
    presentacion_secciones = []
    tabs = []
    if producto.es_producto_estadistico:
        secciones_por_tab = {}
        for s in secciones:
            key = s.tipo_seccion
            if key not in secciones_por_tab:
                secciones_por_tab[key] = []
            secciones_por_tab[key].append(s)

        # Presentación = introduccion + resumen (antes de los tabs)
        for tipo in ('resumen', 'introduccion'):
            if tipo in secciones_por_tab:
                presentacion_secciones.extend(secciones_por_tab.pop(tipo))

        # Resto como tabs, ordenados según TIPO_SECCION
        orden_tipos = [t[0] for t in SeccionPaper.TIPO_SECCION]
        label_map = dict(SeccionPaper.TIPO_SECCION)
        for key in orden_tipos:
            if key in secciones_por_tab:
                secs = secciones_por_tab[key]
                # Sub-tabs: agrupar por prefijo del subnumero (ej. 4.1, 4.2 → sub-tabs)
                sub_tab_groups = {}
                no_sub = []
                for s in secs:
                    if s.subnumero and '.' in s.subnumero:
                        prefix = s.subnumero.split('.')[0]
                        sub_tab_groups.setdefault(prefix, []).append(s)
                    elif s.subnumero:
                        sub_tab_groups.setdefault(s.subnumero, []).append(s)
                    else:
                        no_sub.append(s)
                sub_tabs = []
                for prefix in sorted(sub_tab_groups.keys(), key=lambda x: float(x)):
                    sub_tabs.append({
                        'label': sub_tab_groups[prefix][0].titulo or f'Sección {prefix}',
                        'secciones': sub_tab_groups[prefix]
                    })
                tabs.append({
                    'key': key,
                    'label': label_map.get(key, key),
                    'secciones': no_sub,
                    'sub_tabs': sub_tabs
                })

    context = {
        'producto': producto,
        'secciones': secciones,
        'presentacion_secciones': presentacion_secciones,
        'tabs': tabs,
        'indicadores_vinculados_json': json.dumps(indicadores_vinculados),
        'mapas_vinculados_json': json.dumps(mapas_vinculados),
        'tablas_indicador_json': json.dumps(tablas_indicador_vinculadas),
        'fichas_indicador_json': json.dumps(fichas_indicador_vinculadas),
        'tablas_conjunto_datos_json': json.dumps(tablas_conjunto_datos_vinculados),
        'resultados_destacados_json': json.dumps(resultados_destacados),
        'page_context': 'producto_academico',
        'preview': producto.estado != 'publicado' and request.user.is_authenticated and request.user.is_staff,
    }
    return render(request, 'indicadores/producto_academico.html', context)


def dominios(request):
    # Obtener todos los dominios activos ordenados por el campo 'orden'
    dominios_data = MenuDominio.objects.filter(activo=True).order_by('orden')
    
    return render(request, 'indicadores/dominios.html', {
        'page': 'dominios',
        'dominios': dominios_data
    })


def dominio_detalle(request, slug):
    # Obtener el dominio por slug (case-insensitive)
    dominio = get_object_or_404(MenuDominio, slug__iexact=slug)
    
    # Obtener los temas activos del dominio ordenados por el campo 'orden'
    temas = MenuTema.objects.filter(dominio=dominio).order_by('orden')
    
    return render(request, 'indicadores/dominio_detalle.html', {
        'page': 'dominios',
        'dominio': dominio,
        'temas': temas
    })

def tema_detalle(request, dominio_slug, tema_slug):
    # Obtener el dominio por slug (case-insensitive)
    dominio = get_object_or_404(MenuDominio, slug__iexact=dominio_slug)
    
    # Obtener el tema por slug (case-insensitive)
    tema = get_object_or_404(MenuTema, slug__iexact=tema_slug, dominio=dominio, activo=True)
    
    # Obtener todos los temas del dominio para la navegación lateral
    temas_del_dominio = MenuTema.objects.filter(dominio=dominio, activo=True).order_by('orden')
    
    # Obtener los subtemas activos del tema ordenados por el campo 'orden'
    subtemas = MenuSubtema.objects.filter(tema=tema, activo=True).order_by('orden')
    
    return render(request, 'indicadores/tema_detalle.html', {
        'page': 'dominios',
        'dominio': dominio,
        'tema_actual': tema,
        'temas_del_dominio': temas_del_dominio,
        'subtemas': subtemas
    })

@cache_page(getattr(settings, 'CACHE_TIMEOUT_PAGE', 15 * 60))
def subtema_detalle(request, dominio_slug, tema_slug, subtema_slug):
    # Obtener el dominio por slug (case-insensitive)
    dominio = get_object_or_404(MenuDominio, slug__iexact=dominio_slug)
    
    # Obtener el tema por slug (case-insensitive)
    tema = get_object_or_404(MenuTema, slug__iexact=tema_slug, dominio=dominio, activo=True)
    
    # Obtener el subtema por slug (case-insensitive)
    subtema = get_object_or_404(MenuSubtema, slug__iexact=subtema_slug, tema=tema, activo=True)
    
    # Obtener todos los indicadores activos del subtema ordenados por campo orden
    # indicadores_todos() une el subtema principal (FK) con los
    # subtemas adicionales (M2M): el indicador aparece en todos.
    indicadores = subtema.indicadores_todos().order_by('orden', 'nombre')
    
    return render(request, 'indicadores/subtema_detalle.html', {
        'page': 'dominios',
        'dominio': dominio,
        'tema': tema,
        'subtema_actual': subtema,
        'indicadores': indicadores
    })

@cache_page(getattr(settings, 'CACHE_TIMEOUT_PAGE', 15 * 60))
def subtema_detalle_2(request, tema_slug, subtema_slug):

    tema = get_object_or_404(MenuTema, slug__iexact=tema_slug, activo=True)

    slug = tema.dominio.slug
    
    # Obtener el dominio por slug (case-insensitive)
    dominio = get_object_or_404(MenuDominio, slug__iexact=slug)
    
    # Obtener el tema por slug
    
    # Obtener el subtema por slug (case-insensitive)
    subtema = get_object_or_404(MenuSubtema, slug__iexact=subtema_slug, tema=tema, activo=True)
    
    # Obtener todos los indicadores activos del subtema ordenados por campo orden
    # indicadores_todos() une el subtema principal (FK) con los
    # subtemas adicionales (M2M): el indicador aparece en todos.
    indicadores = subtema.indicadores_todos().order_by('orden', 'nombre')
    
    return render(request, 'indicadores/subtema_detalle.html', {
        'page': 'dominios',
        'dominio': dominio,
        'tema': tema,
        'subtema_actual': subtema,
        'indicadores': indicadores
    })    


@cache_page(getattr(settings, 'CACHE_TIMEOUT_PAGE', 15 * 60))
def subtema_detalle_3d(request, dominio_slug, tema_slug, subtema_slug):
    """
    Vista para mostrar detalles de un subtema con visualización 3D.
    Toma dominio_slug, tema_slug y subtema_slug como parámetros.
    """
    # Obtener el dominio por slug (case-insensitive)
    dominio = get_object_or_404(MenuDominio, slug__iexact=dominio_slug)
    
    # Obtener el tema por slug (case-insensitive)
    tema = get_object_or_404(MenuTema, slug__iexact=tema_slug, dominio=dominio, activo=True)
    
    # Obtener el subtema por slug (case-insensitive)
    subtema = get_object_or_404(MenuSubtema, slug__iexact=subtema_slug, tema=tema, activo=True)
    
    # Obtener todos los indicadores activos del subtema ordenados por campo orden
    # (principal FK + adicionales M2M — ver MenuSubtema.indicadores_todos)
    indicadores = subtema.indicadores_todos().order_by('orden', 'nombre')
    
    return render(request, 'indicadores/subtema_detalle_3d.html', {
        'page': 'dominios',
        'dominio': dominio,
        'tema': tema,
        'subtema_actual': subtema,
        'indicadores': indicadores
    })

     

@cache_grafico_data(timeout=getattr(settings, 'CACHE_TIMEOUT_API', 30 * 60))
def get_graficos(request, indicador_id):
    # Obtener parámetros de filtro
    ano_inicio = request.GET.get('ano_inicio')
    ano_fin = request.GET.get('ano_fin')
    
    # Obtener filtros múltiples de desagregaciones
    desagregaciones_geograficas_ids = request.GET.getlist('desagregaciones_geograficas')
    desagregaciones_tematicas_ids = request.GET.getlist('desagregaciones_tematicas')
    
    # Convertir IDs a enteros
    try:
        desagregaciones_geograficas_ids = [int(id) for id in desagregaciones_geograficas_ids if id.isdigit()]
        desagregaciones_tematicas_ids = [int(id) for id in desagregaciones_tematicas_ids if id.isdigit()]
    except ValueError:
        desagregaciones_geograficas_ids = []
        desagregaciones_tematicas_ids = []
    
    # Obtener el indicador
    indicador = get_object_or_404(Indicador, id=indicador_id, activo=True)

    # Indicador enlazado al catálogo de consulta: no hay gráficos que
    # procesar — el front renderiza el cuadro de consulta del conjunto.
    if indicador.catalogo_consulta_id:
        return JsonResponse([], safe=False)

    # Obtener los gráficos activos del indicador
    graficos = Grafico.objects.filter(indicador=indicador, activo=True).order_by('orden')

    # Preparar los datos de los gráficos
    graficos_data = []
    for grafico in graficos:
        plotly_grafico = procesar_grafico_uno(
            grafico, indicador,
            ano_inicio=ano_inicio,
            ano_fin=ano_fin,
            desagregaciones_geograficas_ids=desagregaciones_geograficas_ids,
            desagregaciones_tematicas_ids=desagregaciones_tematicas_ids
        )
        graficos_data.append(plotly_grafico)

    return JsonResponse(graficos_data, safe=False)


def _agrupar_ids_por_dominio(desag_ids):
    """Devuelve {dominio_id: [desag_ids]} para una lista de IDs de Desagregacion."""
    if not desag_ids:
        return {}
    grupos = defaultdict(list)
    for did, dom_id in Desagregacion.objects.filter(id__in=desag_ids).values_list('id', 'dominio_id'):
        grupos[dom_id].append(did)
    return grupos


def filtrar_datos_por_desagregaciones(qs, geo_ids=None, tem_ids=None):
    """
    Aplica los filtros de desagregación seleccionados por el usuario a un
    queryset de Dato con la semántica esperada por el usuario final:

      - OR dentro de un mismo dominio: seleccionar 'Hombres' y 'Mujeres'
        (dominio Sexo) trae ambos.
      - AND entre dominios distintos: seleccionar 'Hombres' (Sexo) y '0-5'
        (Edad) trae solo los datos que tienen ambas etiquetas.

    Seleccionar solo 'Hombres' trae todos los datos de hombres sin importar
    las demás desagregaciones (todas las edades).

    Un único `id__in` con todos los IDs (comportamiento anterior) producía
    OR global: 'Hombres' + '0-5' devolvía hombres de todas las edades Y
    mujeres de 0-5.
    """
    for ids_dom in _agrupar_ids_por_dominio(geo_ids).values():
        qs = qs.filter(desagregaciones_geograficas__id__in=ids_dom)
    for ids_dom in _agrupar_ids_por_dominio(tem_ids).values():
        qs = qs.filter(desagregaciones_tematicas__id__in=ids_dom)
    return qs.distinct()


def _filtrar_datos_por_serie(qs, serie):
    """
    Aplica los filtros propios de una GraficoSerie (una desagregación por
    dominio) con coincidencia EXACTA por tipo: una serie 'Hombres' no
    debe absorber los datos 'Hombres - 0-5', 'Hombres - 5-10'... (eso
    generaba varios valores por año y rompía la tabla), y una serie
    'Hombres - 0-5' solo trae esa celda.

    Implementación: los filter() encadenados sobre el mismo M2M crean
    joins separados (AND real), y el exclude() descarta datos que tengan
    CUALQUIER desagregación del tipo fuera del conjunto de la serie.
    (No usar Count() sobre el M2M filtrado: reutiliza el join del filter
    y el conteo queda sesgado). Los tipos que la serie NO menciona
    quedan sin restricción.
    """
    geo_ids = []
    tem_ids = []
    for desag in serie.get_desagregaciones():
        if desag.dominio and desag.dominio.tipo == 'geografica':
            qs = qs.filter(desagregaciones_geograficas=desag)
            geo_ids.append(desag.id)
        else:
            qs = qs.filter(desagregaciones_tematicas=desag)
            tem_ids.append(desag.id)
    if geo_ids:
        qs = qs.exclude(desagregaciones_geograficas__in=Desagregacion.objects.exclude(id__in=geo_ids))
    if tem_ids:
        qs = qs.exclude(desagregaciones_tematicas__in=Desagregacion.objects.exclude(id__in=tem_ids))
    return qs


def procesar_grafico_uno(grafico, indicador, ano_inicio=None, ano_fin=None,
                         desagregaciones_geograficas_ids=None,
                         desagregaciones_tematicas_ids=None):
    """
    Procesa un único gráfico y devuelve su configuración Plotly.
    Permite recargar gráficos individuales con parámetros propios.
    """
    if desagregaciones_geograficas_ids is None:
        desagregaciones_geograficas_ids = []
    if desagregaciones_tematicas_ids is None:
        desagregaciones_tematicas_ids = []

    # Usar series del wrapper (ConfigGrafico) o consultar DB para instancias reales
    if getattr(grafico, '_is_config_wrapper', False):
        series = grafico.series.all()
    else:
        series = GraficoSerie.objects.filter(grafico=grafico).order_by('orden')
    series_data = []
    tipos_descartan_vacias = {'line', 'bar', 'bar_horizontal', 'barras_apiladas',
                              'area', 'areas_apiladas', 'sin_grafico', 'tabla_dinamica'}

    for serie in series:
        datos = Dato.objects.filter(indicador=indicador)

        # Filtros de la serie: una desagregación por dominio (M2M nuevo,
        # con fallback a los FKs legacy vía get_desagregaciones()).
        datos = _filtrar_datos_por_serie(datos, serie)

        # Filtros del usuario (AND entre dominios, OR dentro del dominio)
        datos = filtrar_datos_por_desagregaciones(
            datos, desagregaciones_geograficas_ids, desagregaciones_tematicas_ids
        )

        if ano_inicio:
            datos = datos.filter(fecha_dato__year__gte=ano_inicio)
        if ano_fin:
            datos = datos.filter(fecha_dato__year__lte=ano_fin)

        datos = datos.order_by('fecha_dato')

        x_data = [dato.fecha_dato.strftime('%Y') for dato in datos]
        y_data = [dato.valor_dato for dato in datos]

        # Una serie filtrada que quedó sin datos no aporta nada al gráfico ni
        # a la tabla (columna vacía). Se omite para tipos basados en series.
        if not x_data and grafico.tipo_grafico in tipos_descartan_vacias:
            continue

        if serie.nombre_personalizado:
            nombre_serie = serie.nombre_personalizado
        else:
            nombres_desagregaciones = [d.nombre for d in serie.get_desagregaciones()]
            nombre_serie = ' - '.join(nombres_desagregaciones) if nombres_desagregaciones else f'Serie {serie.orden}'

        plotly_serie = {
            'x': x_data,
            'y': y_data,
            'name': nombre_serie,
            'marker': {'color': serie.color} if serie.color and serie.color != '#000000' and serie.color.lower() != 'rgb(0,0,0)' else {}
        }

        tipo = grafico.tipo_grafico
        if tipo == 'line':
            plotly_serie['type'] = 'scatter'
            plotly_serie['mode'] = 'lines+markers'
        elif tipo == 'bar':
            plotly_serie['type'] = 'bar'
        elif tipo == 'bar_horizontal':
            plotly_serie['type'] = 'bar'
            plotly_serie['orientation'] = 'h'
        elif tipo == 'barras_apiladas':
            plotly_serie['type'] = 'bar'
        elif tipo == 'area':
            plotly_serie['type'] = 'scatter'
            plotly_serie['mode'] = 'lines'
            plotly_serie['fill'] = 'tonexty' if len(series_data) > 0 else 'tozeroy'
        elif tipo == 'areas_apiladas':
            plotly_serie['type'] = 'scatter'
            plotly_serie['mode'] = 'lines'
            plotly_serie['fill'] = 'tonexty' if len(series_data) > 0 else 'tozeroy'
            plotly_serie['stackgroup'] = 'one'
        elif tipo == 'pie':
            pass
        elif tipo == 'piramide_poblacional':
            plotly_serie['type'] = 'bar'
            plotly_serie['orientation'] = 'h'
        elif tipo == 'treemap':
            plotly_serie['type'] = 'treemap'
        else:
            plotly_serie['type'] = 'scatter'
            plotly_serie['mode'] = 'lines+markers'

        series_data.append(plotly_serie)

    if grafico.tipo_grafico == 'piramide_poblacional':
        datos_filtrados = Dato.objects.filter(indicador=indicador)
        if ano_inicio:
            datos_filtrados = datos_filtrados.filter(fecha_dato__year__gte=ano_inicio)
        if ano_fin:
            datos_filtrados = datos_filtrados.filter(fecha_dato__year__lte=ano_fin)
        datos_filtrados = filtrar_datos_por_desagregaciones(
            datos_filtrados, desagregaciones_geograficas_ids, desagregaciones_tematicas_ids
        )
        datos_filtrados = datos_filtrados.order_by('fecha_dato')
        series_data = crear_piramide_poblacional(grafico, datos_filtrados)
    elif grafico.tipo_grafico == 'pie':
        series_data = crear_grafico_pie(grafico, series_data, ano_inicio, ano_fin,
                                        desagregaciones_geograficas_ids, desagregaciones_tematicas_ids)
    elif grafico.tipo_grafico == 'treemap':
        series_data = crear_grafico_treemap(grafico, series_data, ano_inicio, ano_fin,
                                            desagregaciones_geograficas_ids, desagregaciones_tematicas_ids)
    elif grafico.tipo_grafico in ('sin_grafico', 'tabla_dinamica') and not series_data:
        # Tipos sin renderizado Plotly: si no hay GraficoSerie configuradas,
        # construir una serie única con todos los datos filtrados para que
        # la tabla de datos no quede vacía.
        datos_filtrados = Dato.objects.filter(indicador=indicador)
        if ano_inicio:
            datos_filtrados = datos_filtrados.filter(fecha_dato__year__gte=ano_inicio)
        if ano_fin:
            datos_filtrados = datos_filtrados.filter(fecha_dato__year__lte=ano_fin)
        datos_filtrados = filtrar_datos_por_desagregaciones(
            datos_filtrados, desagregaciones_geograficas_ids, desagregaciones_tematicas_ids
        )
        datos_filtrados = datos_filtrados.order_by('fecha_dato')
        series_data = [{
            'x': [dato.fecha_dato.strftime('%Y') for dato in datos_filtrados],
            'y': [dato.valor_dato for dato in datos_filtrados],
            'name': indicador.nombre,
            'type': 'scatter',
        }]

    layout_config = configurar_layout_por_tipo(grafico, series_data)

    plotly_grafico = {
        'id': grafico.id,
        'nombre': grafico.nombre,
        'tipo_grafico': grafico.tipo_grafico,
        'series': series_data,
        'altura_grafico': grafico.altura_grafico,
        'begin_at_zero': grafico.begin_at_zero,
        'layout': layout_config
    }

    aplicar_rangos_ejes(plotly_grafico, grafico, series_data)
    return plotly_grafico


def get_grafico(request, grafico_id):
    """
    API para obtener un único gráfico con parámetros de filtro personalizados.
    Permite recargar gráficos individuales con controles independientes.
    """
    grafico = get_object_or_404(Grafico, id=grafico_id, activo=True)
    indicador = grafico.indicador

    ano_inicio = request.GET.get('ano_inicio')
    ano_fin = request.GET.get('ano_fin')

    desagregaciones_geograficas_ids = request.GET.getlist('desagregaciones_geograficas')
    desagregaciones_tematicas_ids = request.GET.getlist('desagregaciones_tematicas')

    try:
        desagregaciones_geograficas_ids = [int(id) for id in desagregaciones_geograficas_ids if id.isdigit()]
        desagregaciones_tematicas_ids = [int(id) for id in desagregaciones_tematicas_ids if id.isdigit()]
    except ValueError:
        desagregaciones_geograficas_ids = []
        desagregaciones_tematicas_ids = []

    plotly_grafico = procesar_grafico_uno(
        grafico, indicador,
        ano_inicio=ano_inicio,
        ano_fin=ano_fin,
        desagregaciones_geograficas_ids=desagregaciones_geograficas_ids,
        desagregaciones_tematicas_ids=desagregaciones_tematicas_ids
    )

    return JsonResponse(plotly_grafico, safe=False)


class ConfigSerie:
    """Wrapper que emula una GraficoSerie desde un dict de config JSON."""
    def __init__(self, config):
        self._config = config

    def get_desagregaciones(self):
        """
        Desagregaciones que filtran la serie. Prioriza 'desagregaciones_ids'
        (formato nuevo, una por dominio) y cae a los ids legacy geo/tematica.
        """
        from .models import Desagregacion
        ids = self._config.get('desagregaciones_ids') or []
        if ids:
            return list(Desagregacion.objects.filter(id__in=ids).select_related('dominio'))
        legacy_ids = [
            self._config.get('desagregacion_geografica_id'),
            self._config.get('desagregacion_tematica_id'),
        ]
        legacy_ids = [i for i in legacy_ids if i]
        if legacy_ids:
            return list(Desagregacion.objects.filter(id__in=legacy_ids).select_related('dominio'))
        return []

    def __getattr__(self, name):
        val = self._config.get(name)
        if name == 'desagregacion_geografica':
            desag_id = self._config.get('desagregacion_geografica_id')
            if desag_id:
                from .models import Desagregacion
                return Desagregacion.objects.filter(id=desag_id).first()
            return None
        if name == 'desagregacion_tematica':
            desag_id = self._config.get('desagregacion_tematica_id')
            if desag_id:
                from .models import Desagregacion
                return Desagregacion.objects.filter(id=desag_id).first()
            return None
        if name == 'nombre_personalizado':
            return self._config.get('nombre_personalizado', '')
        if name == 'color':
            return self._config.get('color', '')
        if name == 'orden':
            return self._config.get('orden', 0)
        return val


class ConfigSeriesManager:
    """Emula grafico.series.all() para ConfigGrafico."""
    def __init__(self, series_configs):
        self._series = [ConfigSerie(c) for c in (series_configs or [])]

    def all(self):
        return self._series

    def filter(self, **kwargs):
        result = []
        for s in self._series:
            match = True
            for k, v in kwargs.items():
                if getattr(s, k, None) != v:
                    match = False
                    break
            if match:
                result.append(s)
        return result

    def first(self):
        return self._series[0] if self._series else None


class ConfigGrafico:
    """Wrapper que emula un Grafico desde un dict de config JSON."""
    _is_config_wrapper = True

    def __init__(self, config, indicador):
        self._config = config
        self.indicador = indicador
        self.series = ConfigSeriesManager(config.get('series', []))

    def __getattr__(self, name):
        defaults = {
            'tipo_grafico': 'line',
            'titulo': '',
            'subtitulo': '',
            'nombre': 'Gráfico',
            'descripcion': '',
            'altura_grafico': 400,
            'margen_derecho': 50,
            'margen_inferior': 50,
            'mostrar_leyenda': True,
            'posicion_leyenda': 'right',
            'mostrar_cuadricula': True,
            'mostrar_valores': False,
            'mostrar_linea_tendencia': False,
            'begin_at_zero': True,
            'mostrar_todas_etiquetas_x': True,
            'eje_x_titulo': '',
            'eje_y_titulo': '',
            'eje_y2_titulo': '',
            'mostrar_eje_y2': False,
            'ancho_completo': False,
            'rango_personalizado_min': None,
            'rango_personalizado_max': None,
        }
        return self._config.get(name, defaults.get(name, None))


def procesar_grafico_desde_config(config_dict, indicador, ano_inicio=None, ano_fin=None,
                                    desagregaciones_geograficas_ids=None,
                                    desagregaciones_tematicas_ids=None):
    """
    Procesa un gráfico a partir de un dict de configuración (para gráficos embebidos en secciones).
    """
    grafico = ConfigGrafico(config_dict, indicador)
    return procesar_grafico_uno(
        grafico, indicador,
        ano_inicio=ano_inicio,
        ano_fin=ano_fin,
        desagregaciones_geograficas_ids=desagregaciones_geograficas_ids,
        desagregaciones_tematicas_ids=desagregaciones_tematicas_ids
    )


def api_get_grafico_seccion(request):
    """
    API para obtener un gráfico configurado por sección (embebido en producto académico).
    Parámetros GET:
      - seccion_id: ID de la SeccionPaper
      - ano_inicio, ano_fin: filtros de año
      - desagregaciones_geograficas, desagregaciones_tematicas: filtros de desagregación
    """
    try:
        from .models import SeccionPaper
        seccion_id = request.GET.get('seccion_id')
        if not seccion_id:
            return JsonResponse({'error': 'seccion_id requerido'}, status=400)

        try:
            seccion = SeccionPaper.objects.select_related('indicador_vinculado').get(id=seccion_id)
        except SeccionPaper.DoesNotExist:
            return JsonResponse({'error': 'Sección no encontrada'}, status=404)

        indicador = seccion.indicador_vinculado
        if not indicador:
            return JsonResponse({'error': 'La sección no tiene indicador vinculado'}, status=400)

        config = seccion.configuracion_grafico or {}
        if isinstance(config, str):
            try:
                config = json.loads(config.strip()) if config.strip() else {}
            except (json.JSONDecodeError, ValueError):
                config = {}

        # Si no hay config guardada, intentar construirla desde los parámetros GET (vista previa)
        if not config or not config.get('series'):
            from .forms_editorial import SectionGraficoConfigForm
            preview_form = SectionGraficoConfigForm(request.GET, indicador=indicador)
            if preview_form.is_valid():
                config = preview_form.to_config()
            else:
                return JsonResponse({'error': 'La sección no tiene configuración de gráfico'}, status=400)

        ano_inicio = request.GET.get('ano_inicio')
        ano_fin = request.GET.get('ano_fin')
        desagregaciones_geograficas_ids = request.GET.getlist('desagregaciones_geograficas')
        desagregaciones_tematicas_ids = request.GET.getlist('desagregaciones_tematicas')

        try:
            desagregaciones_geograficas_ids = [int(id) for id in desagregaciones_geograficas_ids if id.isdigit()]
            desagregaciones_tematicas_ids = [int(id) for id in desagregaciones_tematicas_ids if id.isdigit()]
        except ValueError:
            desagregaciones_geograficas_ids = []
            desagregaciones_tematicas_ids = []

        try:
            plotly_grafico = procesar_grafico_desde_config(
                config, indicador,
                ano_inicio=ano_inicio,
                ano_fin=ano_fin,
                desagregaciones_geograficas_ids=desagregaciones_geograficas_ids,
                desagregaciones_tematicas_ids=desagregaciones_tematicas_ids
            )
        except Exception as e:
            import traceback, sys
            tb = traceback.format_exc()
            print("=" * 60, file=sys.stderr)
            print("ERROR en procesar_grafico_desde_config:", file=sys.stderr)
            print(tb, file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            return JsonResponse({
                'error': f'Error procesando gráfico: {str(e)}',
                'traceback': tb
            }, status=500)

        # Incluir años disponibles y desagregaciones para controles del frontend
        datos = Dato.objects.filter(indicador=indicador)
        anos = sorted({y for y in datos.values_list('fecha_dato__year', flat=True) if y is not None})

        desags_geo = []
        desags_tem = []
        for dato in datos:
            desags_geo.extend(dato.desagregaciones_geograficas.all())
            desags_tem.extend(dato.desagregaciones_tematicas.all())

        plotly_grafico['anos_disponibles'] = anos
        plotly_grafico['desagregaciones_geograficas'] = [
            {'id': d.id, 'nombre': d.nombre} for d in set(desags_geo)
        ]
        plotly_grafico['desagregaciones_tematicas'] = [
            {'id': d.id, 'nombre': d.nombre} for d in set(desags_tem)
        ]
        plotly_grafico['desagregaciones_geograficas_predeterminadas'] = config.get('desagregaciones_geograficas_predeterminadas', [])
        plotly_grafico['desagregaciones_tematicas_predeterminadas'] = config.get('desagregaciones_tematicas_predeterminadas', [])
        plotly_grafico['rango_anios_min'] = config.get('rango_anios_min')
        plotly_grafico['rango_anios_max'] = config.get('rango_anios_max')

        return JsonResponse(plotly_grafico, safe=False)

    except Exception as e:
        import traceback
        return JsonResponse({
            'error': f'Error interno: {str(e)}',
            'traceback': traceback.format_exc()
        }, status=500)


@cache_grafico_data(timeout=getattr(settings, 'CACHE_TIMEOUT_API', 30 * 60))
def get_mapa(request, indicador_id):
    """API para obtener configuración y datos de mapas (choropleth) para un indicador.
    Parámetros GET opcionales:
      - anio: año específico a mostrar. Si no se envía, usa `ano_predeterminado` del mapa o el máximo disponible.
      - desagregaciones_tematicas: lista de IDs (múltiples) para filtrar datos temáticos.
      - serie_mapa: id de una serie del mapa para aplicar filtros específicos de la serie.
    Devuelve lista de mapas activos con:
      - config: configuración visual y geográfica
      - filtros: desagregaciones disponibles, predeterminados y rango de años
      - data: valores agregados por desagregación geográfica para el año seleccionado
    """
    # Validar indicador
    indicador = get_object_or_404(Indicador, id=indicador_id, activo=True)

    # Parsear parámetros
    anio_param = request.GET.get('anio')
    try:
        anio_param = int(anio_param) if anio_param is not None and str(anio_param).isdigit() else None
    except (TypeError, ValueError):
        anio_param = None

    desag_tem_ids = request.GET.getlist('desagregaciones_tematicas')
    try:
        desag_tem_ids = [int(i) for i in desag_tem_ids if str(i).isdigit()]
    except ValueError:
        desag_tem_ids = []

    # Serie seleccionada (opcional)
    serie_mapa_param = request.GET.get('serie_mapa')
    try:
        serie_mapa_param = int(serie_mapa_param) if serie_mapa_param is not None and str(serie_mapa_param).isdigit() else None
    except (TypeError, ValueError):
        serie_mapa_param = None

    # Mapas activos para el indicador
    mapas_qs = (Mapa.objects
                .filter(indicador=indicador, activo=True)
                .prefetch_related('desagregaciones_geograficas_predeterminadas', 'desagregaciones_tematicas_predeterminadas')
                .order_by('orden', 'id'))

    if not mapas_qs.exists():
        return JsonResponse({'error': 'No hay mapas configurados para este indicador.'}, status=404)

    # Rango de años disponible para el indicador
    datos_ind = Dato.objects.filter(indicador=indicador).only('fecha_dato')
    if datos_ind.exists():
        anos = list(datos_ind.values_list('fecha_dato__year', flat=True))
        ano_min_disponible = min(anos)
        ano_max_disponible = max(anos)
    else:
        ano_min_disponible = 2010
        ano_max_disponible = datetime.date.today().year

    # Desagregaciones temáticas disponibles por dominios del indicador
    dominios_tem = indicador.dominios_desagregacion_tematica.all()
    tem_disponibles_qs = (
        Desagregacion.objects
        .filter(dominio__in=dominios_tem)
        .select_related('dominio')
        .distinct()
    )

    mapas_data = []
    for mapa in mapas_qs:
        # Año seleccionado
        selected_year = anio_param if anio_param is not None else (mapa.ano_predeterminado or ano_max_disponible)

        # Predeterminados de desagregaciones
        tem_predet_ids = list(mapa.desagregaciones_tematicas_predeterminadas.values_list('id', flat=True))
        geo_predet_ids = list(mapa.desagregaciones_geograficas_predeterminadas.values_list('id', flat=True))

        # Series disponibles para el mapa
        series_qs = []  # MapaSerie ha sido eliminado
        series_disponibles = []
        serie_seleccionada = None
        for s in series_qs:
            if s.nombre_personalizado:
                nombre_s = s.nombre_personalizado
            else:
                partes = []
                if s.desagregacion_geografica:
                    partes.append(s.desagregacion_geografica.nombre)
                # Concatenar múltiples temáticas si existen
                tem_names = list(s.desagregaciones_tematicas.values_list('nombre', flat=True))
                if tem_names:
                    partes.append(' / '.join(tem_names))
                nombre_s = ' - '.join(partes) if partes else f"Serie {s.orden}"
            tem_ids_s = list(s.desagregaciones_tematicas.values_list('id', flat=True))
            series_disponibles.append({
                'id': s.id,
                'nombre': nombre_s,
                'color': s.color,
                'orden': s.orden,
                'desagregacion_geografica_id': s.desagregacion_geografica_id,
                'desagregaciones_tematicas_ids': tem_ids_s,
            })
            if serie_mapa_param and s.id == serie_mapa_param:
                serie_seleccionada = s

        # Base: si el usuario envió filtros temáticos, usarlos como selección base;
        # de lo contrario usar los predeterminados del mapa. No forzamos los de la serie aquí;
        # la combinación con la serie se hará por-cada-serie (intersección) más abajo.
        user_has_selection = bool(desag_tem_ids)
        selected_tem_ids_base = desag_tem_ids if user_has_selection else tem_predet_ids

        # Desagregaciones geográficas disponibles: derivadas de los dominios geográficos del indicador
        dominios_geo = indicador.dominios_desagregacion_geografica.all()
        # Geografías disponibles: SIEMPRE todas derivadas del indicador (no limitar por serie seleccionada)
        geos_qs = (
            Desagregacion.objects
            .filter(dominio__in=dominios_geo, capa_geo__isnull=False)
            .exclude(Q(nombre__iexact='Total') | Q(codigo__iexact='Total'))
            .distinct()
            .order_by('nombre')
        )

        # Sanitizar predeterminadas geográficas para excluir IDs no disponibles (p.ej. 'Total')
        geos_ids_set = set(geos_qs.values_list('id', flat=True))
        geo_predet_ids_sane = [gid for gid in geo_predet_ids if gid in geos_ids_set]

        # Capas disponibles (derivadas de las desagregaciones geográficas)
        capa_ids = sorted({d.capa_geo_id for d in geos_qs if d.capa_geo_id})

        # Mapear id de capa -> nombre, para permitir configuración por settings
        capas_map = {row['id']: row['nombre'] for row in CapaGeo.objects.filter(id__in=capa_ids).values('id', 'nombre')}

        geos_disponibles = [
            {
                'id': d.id,
                'codigo': d.codigo,
                'nombre': d.nombre,
                'predeterminada': d.id in geo_predet_ids_sane,
            }
            for d in geos_qs
        ]

        tem_disponibles = [
            {
                'id': d.id,
                'codigo': d.codigo,
                'nombre': d.nombre,
                'predeterminada': d.id in tem_predet_ids,
                'dominio': {
                    'id': d.dominio_id,
                    'nombre': getattr(d.dominio, 'nombre', None),
                    'tipo': getattr(d.dominio, 'tipo', None),
                }
            }
            for d in tem_disponibles_qs
        ]

        # Helper: construir valores por features para una combinación (serie)
        def _build_valores_for(geos_qs_local, tem_ids_local, serie_geo_id=None):
            # Datos base por indicador y año
            datos_base = Dato.objects.filter(indicador=indicador, fecha_dato__year=selected_year)
            # 1) Filtrar por temáticas usando subconsulta para evitar multiplicación por joins M2M
            # Si tem_ids_local es None: no aplicar filtro temático.
            # Si es lista (incluida lista vacía): aplicar filtro; lista vacía producirá "sin datos".
            if tem_ids_local is not None:
                datos_ids = (
                    Dato.objects
                    .filter(indicador=indicador, fecha_dato__year=selected_year,
                            desagregaciones_tematicas__id__in=tem_ids_local)
                    .values('id')
                    .distinct()
                )
                datos_qs_local = datos_base.filter(id__in=Subquery(datos_ids))
            else:
                datos_qs_local = datos_base
            # 1.b) Filtrar por desagregación geográfica de la serie si se especifica (p.ej. Cabecera/CPyRD)
            if serie_geo_id:
                datos_qs_local = datos_qs_local.filter(desagregaciones_geograficas=serie_geo_id)
            # 2) Limitar por geografía disponible (todas las derivadas del indicador)
            if dominios_geo.exists():
                datos_qs_local = datos_qs_local.filter(
                    desagregaciones_geograficas__dominio__in=dominios_geo,
                    desagregaciones_geograficas__in=geos_qs_local,
                )

            agregados_local = list(
                datos_qs_local.values(
                    'desagregaciones_geograficas__id',
                    'desagregaciones_geograficas__codigo',
                    'desagregaciones_geograficas__nombre',
                    'desagregaciones_geograficas__capa_geo_id',
                ).annotate(valor=Sum('valor_dato')).order_by('desagregaciones_geograficas__nombre')
            )

            # Capas involucradas en esta combinación
            capa_ids_local = sorted({d.capa_geo_id for d in geos_qs_local if d.capa_geo_id})

            # Elementos por capa
            elementos_local = list(
                ElementoGeo.objects
                .filter(capa_geo_id__in=capa_ids_local)
                .values('capa_geo_id', 'codigo', 'nombre')
            )

            elementos_por_capa_local = _dd(list)
            codigos_por_capa_local = _dd(set)
            # Normalizador de códigos (string, trim, upper, sin separadores comunes, sin ceros a la izquierda)
            def _norm(code):
                if code is None:
                    return None
                s = str(code).strip()
                if not s:
                    return None
                # Remover separadores comunes
                for ch in [' ', '-', '_', '.']:
                    s = s.replace(ch, '')
                # Uppercase y sin ceros a la izquierda
                s = s.upper().lstrip('0') or '0'
                return s
            for e in elementos_local:
                cid = e['capa_geo_id']
                elementos_por_capa_local[cid].append(e)
                if e['codigo'] is not None:
                    # Guardar ambas formas por tolerancia
                    raw = str(e['codigo'])
                    codigos_por_capa_local[cid].add(raw)
                    norm = _norm(raw)
                    if norm is not None:
                        codigos_por_capa_local[cid].add(norm)

            agregados_por_capa_local = _dd(list)
            for row in agregados_local:
                agregados_por_capa_local[row['desagregaciones_geograficas__capa_geo_id']].append(row)

            valores_local = []
            for cid in capa_ids_local:
                elems = elementos_por_capa_local.get(cid, [])
                if not elems:
                    continue
                codigo_a_valor = {}
                for row in agregados_por_capa_local.get(cid, []):
                    cod = row['desagregaciones_geograficas__codigo']
                    val = float(row['valor']) if row['valor'] is not None else None
                    if cod is not None:
                        # Intentar match tanto por raw como por normalizado
                        raw = str(cod)
                        norm = _norm(raw)
                        if raw in codigos_por_capa_local[cid] or (norm is not None and norm in codigos_por_capa_local[cid]):
                            # Usar la clave normalizada para ser consistentes
                            key = norm if (norm is not None and norm in codigos_por_capa_local[cid]) else raw
                            codigo_a_valor[key] = val
                for e in elems:
                    code_raw = str(e['codigo']) if e['codigo'] is not None else None
                    code_norm = _norm(code_raw) if code_raw is not None else None
                    # Resolver por norm o por raw
                    key = None
                    if code_norm is not None and code_norm in codigo_a_valor:
                        key = code_norm
                    elif code_raw is not None and code_raw in codigo_a_valor:
                        key = code_raw
                    valores_local.append({
                        'geo_id': None,
                        'codigo': code_raw,
                        'nombre': e['nombre'],
                        'capa_id': cid,
                        'valor': codigo_a_valor.get(key)
                    })
            return valores_local, capa_ids_local

        # Construir capas (layers)
        layers = []
        all_capa_ids = set()
        for s in series_qs:
            # Temáticas definidas por la serie (si existen)
            tem_ids_series = list(s.desagregaciones_tematicas.values_list('id', flat=True))
            # Combinar con selección del usuario (si la hay): intersección.
            if user_has_selection and tem_ids_series:
                tem_ids_s = sorted(set(tem_ids_series).intersection(desag_tem_ids))
            elif tem_ids_series:
                # Sin selección del usuario, usar las de la serie
                tem_ids_s = tem_ids_series
            elif user_has_selection:
                # Serie no define temáticas; usar selección del usuario
                tem_ids_s = desag_tem_ids
            else:
                # Ni serie ni usuario: usar predeterminadas del mapa; si no hay, no filtrar (None)
                tem_ids_s = selected_tem_ids_base if selected_tem_ids_base else None
            # La serie NO limita las capas geográficas: siempre usar todas las geos derivadas del indicador
            geos_qs_s = (
                Desagregacion.objects
                .filter(dominio__in=dominios_geo, capa_geo__isnull=False)
                .exclude(Q(nombre__iexact='Total') | Q(codigo__iexact='Total'))
                .distinct()
            )
            valores_s, capa_ids_s = _build_valores_for(geos_qs_s, tem_ids_s, s.desagregacion_geografica_id)
            all_capa_ids.update(capa_ids_s)
            layers.append({
                'serie_id': s.id,
                'nombre': series_name_map.get(s.id, f"Serie {s.orden}"),
                'color': s.color,
                'capa_ids': capa_ids_s,
                'valores': valores_s,
            })

        # Backward compatibility: elegir valores de la serie seleccionada o la primera
        if serie_seleccionada and layers:
            selected_layer = next((ly for ly in layers if ly['serie_id'] == serie_seleccionada.id), layers[0])
            valores = selected_layer['valores']
        elif layers:
            valores = layers[0]['valores']
        else:
            # Fallback: sin series definidas -> usar configuración general
            # Si no hay base de temáticas, pasar None (sin filtro). Si hay lista vacía, producirá sin datos.
            tem_base_for_fallback = selected_tem_ids_base if selected_tem_ids_base else None
            valores, capa_ids = _build_valores_for(geos_qs, tem_base_for_fallback, None)
            all_capa_ids.update(capa_ids)

        # Configuración del mapa
        mapa_config = {
            'id': mapa.id,
            'nombre': mapa.nombre,
            'descripcion': mapa.descripcion,
            'tipo_mapa': mapa.tipo_mapa,
            'titulo': mapa.titulo or mapa.nombre,
            'subtitulo': mapa.subtitulo,
            'altura_mapa': mapa.altura_mapa,
            'colorscale': mapa.colorscale,
            'colorscale_reversa': mapa.colorscale_reversa,
            'color_borde': mapa.color_borde,
            'grosor_borde': mapa.grosor_borde,
            'color_sin_dato': mapa.color_sin_dato,
            'mostrar_leyenda': mapa.mostrar_leyenda,
            'begin_at_zero': mapa.begin_at_zero,
            'rango_personalizado_min': mapa.rango_personalizado_min,
            'rango_personalizado_max': mapa.rango_personalizado_max,
            'formato_valor': mapa.formato_valor,
            'propiedad_feature_id': mapa.propiedad_feature_id,
            'ano_predeterminado': mapa.ano_predeterminado,
            'unidad_medida': indicador.unidad_medida,
            'geografia_derivada_de_indicador': True,
        }

        mapas_data.append({
            'config': mapa_config,
            'filtros': {
                'desagregaciones_geograficas_disponibles': geos_disponibles,
                'desagregaciones_tematicas_disponibles': tem_disponibles,
                'series_disponibles': series_disponibles,
                # Capas disponibles: unión de todas las capas usadas por las series
                'capas_disponibles': [
                    {
                        'id': cid,
                        'nombre': CapaGeo.objects.filter(id=cid).values_list('nombre', flat=True).first()
                    } for cid in sorted(all_capa_ids)
                ],
                'predeterminados': {
                    'anio': selected_year,
                    # Exponer la base efectiva (usuario si envió, si no predeterminadas del mapa)
                    'desagregaciones_tematicas': selected_tem_ids_base or [],
                    'desagregaciones_geograficas': geo_predet_ids_sane,
                    'serie_mapa': serie_seleccionada.id if serie_seleccionada else None,
                },
                'rango_anios': {
                    'min': ano_min_disponible,
                    'max': ano_max_disponible,
                    'min_disponible': ano_min_disponible,
                    'max_disponible': ano_max_disponible,
                },
            },
            # Compatibilidad: exponer también series_disponibles a nivel raíz del mapa
            'series_disponibles': series_disponibles,
            'data': {
                'anio': selected_year,
                'valores': valores,
                'layers': layers,
            },
        })

    return JsonResponse(mapas_data, safe=False)


def valores_geo(request, indicador_id):
    # FORCE RELOAD - VERSION 2.0
    """Endpoint ligero: valores geográficos agregados por código/capa para un indicador y año.

    Parámetros GET opcionales:
      - anio: año específico (int). Si no se envía, usa el máximo disponible del indicador.
      - desagregaciones_tematicas: lista de IDs para filtrar temáticas (interseca con las de serie si se pasa serie_mapa).
      - serie_mapa: id de MapaSerie para aplicar filtro de desagregación geográfica y combinar temáticas.

    Respuesta mínima:
      {
        'indicador_id': <int>,
        'anio': <int>,
        'capas': [<capa_id>, ...],
        'valores': [ { 'codigo': <str>, 'capa_id': <int>, 'valor': <float|null> }, ... ],
        'meta': { 'tematicas': [...], 'serie_mapa': <int|null> }
      }
    """
    indicador = get_object_or_404(Indicador, id=indicador_id, activo=True)

    # Año seleccionado
    anio_param = request.GET.get('anio')
    try:
        anio_param = int(anio_param) if anio_param is not None and str(anio_param).isdigit() else None
    except (TypeError, ValueError):
        anio_param = None

    datos_ind = Dato.objects.filter(indicador=indicador).only('fecha_dato')
    if datos_ind.exists():
        anos = list(datos_ind.values_list('fecha_dato__year', flat=True))
        ano_max_disponible = max(anos)
    else:
        ano_max_disponible = datetime.date.today().year
    selected_year = anio_param if anio_param is not None else ano_max_disponible

    # Temáticas desde query
    desag_tem_ids = request.GET.getlist('desagregaciones_tematicas')
    try:
        desag_tem_ids = [int(i) for i in desag_tem_ids if str(i).isdigit()]
    except ValueError:
        desag_tem_ids = []

    # Serie seleccionada (opcional) para aplicar filtro geográfico y/o combinar temáticas
    serie_mapa_param = request.GET.get('serie_mapa')
    try:
        serie_mapa_param = int(serie_mapa_param) if serie_mapa_param is not None and str(serie_mapa_param).isdigit() else None
    except (TypeError, ValueError):
        serie_mapa_param = None

    # Serie de mapa ya no está disponible
    if serie_mapa_param:
        return JsonResponse({'error': 'La funcionalidad de series de mapa ya no está disponible'}, status=400)

    # Combinar temáticas como en get_mapa: intersección cuando aplica
    # Nota: serie_mapa está deprecada (rechazada arriba), por lo que
    # tem_ids_series siempre es None. Se conserva la estructura por compatibilidad.
    user_has_selection = bool(desag_tem_ids)
    if user_has_selection:
        tem_ids_effective = desag_tem_ids
    else:
        tem_ids_effective = None  # sin filtro temático

    # Geografías disponibles: derivadas de dominios del indicador
    dominios_geo = indicador.dominios_desagregacion_geografica.all()
    print(f"[DEBUG] Dominios geográficos encontrados: {list(dominios_geo.values('id', 'nombre'))}")
    
    if not dominios_geo.exists():
        print(f"[DEBUG] No hay dominios geográficos para indicador {indicador.id}")
        return JsonResponse({
            'indicador_id': indicador.id,
            'anio': selected_year,
            'capas': [],
            'valores': [],
            'meta': { 'tematicas': desag_tem_ids or [], 'serie_mapa': serie_mapa_param }
        })

    geos_qs = (
        Desagregacion.objects
        .filter(dominio__in=dominios_geo, capa_geo__isnull=False)
        .exclude(Q(nombre__iexact='Total') | Q(codigo__iexact='Total'))
        .distinct()
        .order_by('nombre')
    )
    
    print(f"[DEBUG] FIXED VERSION - Desagregaciones geográficas con capa_geo (excluyendo Total): {list(geos_qs.values('id', 'nombre', 'codigo', 'capa_geo_id'))}")

    # Agregación base - SIEMPRE excluir "Total" geográfico desde el inicio
    datos_base = Dato.objects.filter(
        indicador=indicador, 
        fecha_dato__year=selected_year
    ).exclude(
        Q(desagregaciones_geograficas__nombre__iexact='Total') | 
        Q(desagregaciones_geograficas__codigo__iexact='Total')
    )
    print(f"[DEBUG] Datos base encontrados para año {selected_year} (sin Total geográfico): {datos_base.count()}")
    
    if tem_ids_effective is not None:
        # Agrupar desagregaciones temáticas por dominio
        desags_tematicas = Desagregacion.objects.filter(id__in=tem_ids_effective)
        dominios_filtros = {}
        for desag in desags_tematicas:
            dominio_id = desag.dominio.id
            if dominio_id not in dominios_filtros:
                dominios_filtros[dominio_id] = []
            dominios_filtros[dominio_id].append(desag.id)
        
        print(f"[DEBUG] Filtros temáticos agrupados por dominio: {dominios_filtros}")
        
        # Aplicar filtros por intersección de dominios
        datos_qs_local = datos_base
        for dominio_id, desag_ids in dominios_filtros.items():
            datos_qs_local = datos_qs_local.filter(desagregaciones_tematicas__id__in=desag_ids)
            print(f"[DEBUG] Datos después de filtrar dominio {dominio_id}: {datos_qs_local.count()}")
        
        datos_qs_local = datos_qs_local.distinct()
        print(f"[DEBUG] Datos finales después de filtros temáticos: {datos_qs_local.count()}")
    else:
        datos_qs_local = datos_base
        print(f"[DEBUG] Sin filtros temáticos, usando todos los datos base (sin Total geográfico)")
        
    # serie_geo_id se derivaba de serie_mapa (deprecada), ya no aplica.
    # Se conserva el bloque comentado por referencia futura.
        
    if dominios_geo.exists():
        print(f"[DEBUG] APLICANDO FILTRO GEOGRÁFICO - geos_qs count: {geos_qs.count()}")
        print(f"[DEBUG] geos_qs códigos: {list(geos_qs.values_list('codigo', flat=True))}")
        datos_qs_local = datos_qs_local.filter(
            desagregaciones_geograficas__dominio__in=dominios_geo,
            desagregaciones_geograficas__in=geos_qs,
        )
        print(f"[DEBUG] Datos después de filtro dominios geográficos: {datos_qs_local.count()}")
    else:
        # Aplicar filtro para mantener solo desagregaciones geográficas válidas
        datos_qs_local = datos_qs_local.filter(desagregaciones_geograficas__in=geos_qs)
        print(f"[DEBUG] Datos después de filtro geográfico: {datos_qs_local.count()}")
        
    # Debug: mostrar algunos datos encontrados
    if datos_qs_local.exists():
        sample_datos = list(datos_qs_local.values('desagregaciones_geograficas__codigo', 'desagregaciones_geograficas__nombre', 'valor_dato')[:5])
        print(f"[DEBUG] Muestra de datos encontrados: {sample_datos}")
    else:
        print(f"[DEBUG] No se encontraron datos después de aplicar filtros")

    # Verificar si hay gráficos de pirámide poblacional para este indicador
    tiene_piramide = (
        Grafico.objects
        .filter(indicador=indicador, tipo_grafico='piramide_poblacional')
        .exists()
    )
    
    if tiene_piramide:
        print(f"[DEBUG] Indicador {indicador.id} tiene pirámide poblacional, usando lógica especial")
        
        # Para pirámides poblacionales, obtener datos directamente sin usar GraficoSerie
        datos_piramide = Dato.objects.filter(indicador=indicador, fecha_dato__year=selected_year)
        
        # Aplicar filtros temáticos si existen
        if tem_ids_effective is not None:
            datos_ids = (
                Dato.objects
                .filter(indicador=indicador, fecha_dato__year=selected_year,
                        desagregaciones_tematicas__id__in=tem_ids_effective)
                .values('id')
                .distinct()
            )
            datos_piramide = datos_piramide.filter(id__in=Subquery(datos_ids))
        
        # Excluir datos con desagregaciones geográficas "Total"
        datos_piramide = datos_piramide.exclude(
            desagregaciones_geograficas__nombre__iexact='Total'
        ).exclude(
            desagregaciones_geograficas__codigo__iexact='Total'
        )
        
        # Agregar por desagregación geográfica específica (no por capa)
        agregados_piramide = list(
            datos_piramide.values(
                'desagregaciones_geograficas__codigo',
                'desagregaciones_geograficas__nombre',
                'desagregaciones_geograficas__capa_geo_id',
            ).annotate(valor=Sum('valor_dato'))
        )
        
        print(f"[DEBUG] Datos pirámide encontrados: {len(agregados_piramide)}")
        
        # CORREGIDO: Para pirámides, retornar solo las desagregaciones geográficas que tienen datos reales
        # No distribuir valores de capa a elementos individuales
        valores = []
        for row in agregados_piramide:
            if row['desagregaciones_geograficas__capa_geo_id']:
                valores.append({
                    'codigo': row['desagregaciones_geograficas__codigo'],
                    'capa_id': row['desagregaciones_geograficas__capa_geo_id'],
                    'valor': float(row['valor']) if row['valor'] is not None else None,
                    'nombre_capa': row['desagregaciones_geograficas__nombre'],
                    'nombre_elemento': row['desagregaciones_geograficas__nombre']  # Usar el mismo nombre
                })
                print(f"[DEBUG] Pirámide - Agregado valor {row['valor']} para desagregación {row['desagregaciones_geograficas__codigo']}")
        
        # Para pirámides, las capas son las que tienen datos
        capa_ids = sorted({row['desagregaciones_geograficas__capa_geo_id'] for row in agregados_piramide if row['desagregaciones_geograficas__capa_geo_id']})
        
    else:
        # Lógica normal para otros tipos de gráficos
        # Obtener valores directamente por desagregación geográfica
        agregados_por_desag = list(
            datos_qs_local.values(
                'desagregaciones_geograficas__id',
                'desagregaciones_geograficas__codigo',
                'desagregaciones_geograficas__nombre',
                'desagregaciones_geograficas__capa_geo_id',
            ).annotate(valor=Sum('valor_dato'))
        )
        
        print(f"[DEBUG] Datos encontrados para año {selected_year}: {len(agregados_por_desag)}")
        print(f"[DEBUG] Agregados por desagregación: {agregados_por_desag}")

        # Capas involucradas
        capa_ids = sorted({row['desagregaciones_geograficas__capa_geo_id'] for row in agregados_por_desag if row['desagregaciones_geograficas__capa_geo_id']})
        
        # CORREGIDO: Retornar solo las desagregaciones geográficas que tienen datos reales
        # No distribuir valores de capa a elementos individuales
        # EXCLUIR explícitamente "Total" geográfico de los resultados finales
        valores = []
        for row in agregados_por_desag:
            codigo = row['desagregaciones_geograficas__codigo']
            nombre = row['desagregaciones_geograficas__nombre']
            
            # FILTRO ADICIONAL: Excluir "Total" geográfico en los resultados finales
            if (codigo and codigo.lower() != 'total' and 
                nombre and nombre.lower() != 'total' and
                row['desagregaciones_geograficas__capa_geo_id']):
                
                valores.append({
                    'codigo': codigo,
                    'capa_id': row['desagregaciones_geograficas__capa_geo_id'],
                    'valor': float(row['valor']) if row['valor'] is not None else None,
                    'nombre_capa': nombre,
                    'nombre_elemento': nombre  # Usar el mismo nombre
                })
                print(f"[DEBUG] INCLUIDO - Agregado valor {row['valor']} para desagregación {codigo}")
            else:
                print(f"[DEBUG] EXCLUIDO - Total geográfico {codigo}: {row['valor']}")

        print(f"[DEBUG] Total valores retornados: {len(valores)}")

    resp = {
        'indicador_id': indicador.id,
        'anio': selected_year,
        'capas': capa_ids,
        'valores': valores,
        'meta': {
            'tematicas': [] if tem_ids_effective is None else list(tem_ids_effective),
            'serie_mapa': serie_mapa_param,
        }
    }
    return JsonResponse(resp)


def test_valores_geo(request, indicador_id):
    """Test endpoint with corrected Total exclusion logic"""
    
    # Get parameters
    selected_year = int(request.GET.get('anio', 2020))  # Default to 2020 instead of 2013
    tem_ids = request.GET.getlist('desagregaciones_tematicas')
    tem_ids_effective = [int(x) for x in tem_ids] if tem_ids else None  # No default filters
    
    # Get indicator
    try:
        indicador = Indicador.objects.get(id=indicador_id)
    except Indicador.DoesNotExist:
        return JsonResponse({'error': 'Indicador no encontrado'}, status=404)
    
    # Base data - EXCLUDE Total geographic from the start
    datos_base = Dato.objects.filter(
        indicador=indicador, 
        fecha_dato__year=selected_year
    ).exclude(
        Q(desagregaciones_geograficas__nombre__iexact='Total') | 
        Q(desagregaciones_geograficas__codigo__iexact='Total')
    )
    
    # Apply thematic filters by domain intersection only if filters are provided
    if tem_ids_effective:
        desags_tematicas = Desagregacion.objects.filter(id__in=tem_ids_effective)
        dominios_filtros = {}
        for desag in desags_tematicas:
            dominio_id = desag.dominio.id
            if dominio_id not in dominios_filtros:
                dominios_filtros[dominio_id] = []
            dominios_filtros[dominio_id].append(desag.id)
        
        datos_qs_local = datos_base
        for dominio_id, desag_ids in dominios_filtros.items():
            datos_qs_local = datos_qs_local.filter(desagregaciones_tematicas__id__in=desag_ids)
        
        datos_qs_local = datos_qs_local.distinct()
    else:
        datos_qs_local = datos_base
    
    # Aggregate by geographic disaggregation
    agregados = list(
        datos_qs_local.values(
            'desagregaciones_geograficas__codigo',
            'desagregaciones_geograficas__nombre',
            'desagregaciones_geograficas__capa_geo_id',
        ).annotate(valor=Sum('valor_dato'))
    )
    
    # Build response
    valores = []
    capa_ids = []
    for row in agregados:
        codigo = row['desagregaciones_geograficas__codigo']
        nombre = row['desagregaciones_geograficas__nombre']
        capa_id = row['desagregaciones_geograficas__capa_geo_id']
        
        if codigo and capa_id:
            valores.append({
                'codigo': codigo,
                'capa_id': capa_id,
                'valor': float(row['valor']) if row['valor'] is not None else None,
                'nombre_capa': nombre,
                'nombre_elemento': nombre
            })
            if capa_id not in capa_ids:
                capa_ids.append(capa_id)
    
    return JsonResponse({
        'indicador_id': indicador.id,
        'anio': selected_year,
        'capas': sorted(capa_ids),
        'valores': valores,
        'meta': {
            'tematicas': tem_ids_effective or [],
            'serie_mapa': None,
            'test_version': True
        }
    })


@cache_grafico_data(timeout=getattr(settings, 'CACHE_TIMEOUT_API', 30 * 60))
def geojson_indicador(request, indicador_id):
    """Devuelve un GeoJSON FeatureCollection para las capas geográficas asociadas
    a los dominios de desagregación geográfica del indicador.

    No requiere parámetros. Usa `Indicador.dominios_desagregacion_geografica` para
    derivar las `CapaGeo` involucradas a través de `Desagregacion.capa_geo` y luego
    construye features a partir de `ElementoGeo` (geom_wkt) de esas capas.

    Propiedades mínimas por feature: codigo, nombre, capa_id.
    """
    indicador = get_object_or_404(Indicador, id=indicador_id, activo=True)

    # Dominios geográficos del indicador -> desagregaciones -> capas
    dominios_geo = indicador.dominios_desagregacion_geografica.all()
    if not dominios_geo.exists():
        return JsonResponse({
            'type': 'FeatureCollection',
            'features': [],
            'meta': {
                'capas': [],
                'count': 0,
                'nota': 'Indicador sin dominios geográficos'
            }
        })

    desags = (Desagregacion.objects
              .filter(dominio__in=dominios_geo, capa_geo__isnull=False)
              .select_related('capa_geo')
              .distinct())
    capa_ids = sorted({d.capa_geo_id for d in desags if d.capa_geo_id})

    # Mapear id de capa -> nombre, para permitir configuración por settings
    capas_info = {row['id']: row['nombre'] for row in CapaGeo.objects.filter(id__in=capa_ids).values('id', 'nombre')}

    if not capa_ids:
        return JsonResponse({
            'type': 'FeatureCollection',
            'features': [],
            'meta': {
                'capas': [],
                'count': 0,
                'nota': 'Dominios geográficos sin capas asociadas en desagregaciones'
            }
        })

    # Conversor muy simple de WKT -> GeoJSON (POLYGON/MULTIPOLYGON/LINESTRING/POINT)
    def _coords_from_ring(txt):
        pts = []
        for pair in txt.split(','):
            pair = pair.strip()
            if not pair:
                continue
            parts = pair.split()
            if len(parts) < 2:
                continue
            try:
                x = float(parts[0])
                y = float(parts[1])
                
                # Transform projected coordinates to geographic (lat/lng)
                # Assuming UTM Zone 18N (EPSG:32618) to WGS84 (EPSG:4326)
                # Simple approximation for Cali, Colombia area
                if x > 180 or y > 90:  # Detect projected coordinates
                    # Convert UTM to approximate lat/lng for Cali area
                    # UTM Zone 18N false easting: 500000, false northing: 0
                    # Cali is approximately at 3.4°N, 76.5°W
                    
                    # Simple linear transformation (approximation)
                    # This is a rough conversion - for production use proper coordinate transformation
                    lng = -76.5 + (x - 1000000) / 111320  # Rough conversion
                    lat = 3.4 + (y - 900000) / 110540    # Rough conversion
                    
                    # Clamp to valid ranges
                    lng = max(-180, min(180, lng))
                    lat = max(-90, min(90, lat))
                    
                    pts.append([lng, lat])
                else:
                    pts.append([x, y])
            except Exception:
                continue
        return pts

    def wkt_to_geo(geom_wkt):
        if not geom_wkt or not isinstance(geom_wkt, str):
            return None
        txt = geom_wkt.strip()
        if not txt:
            return None
        upper = txt.upper()
        try:
            if upper.startswith('MULTIPOLYGON'):
                inner = txt[len('MULTIPOLYGON'):].strip()
                # Espera formato: (( (x y, ...), (hole...) ), ( ( ... ) ))
                # Quitamos el primer y último paréntesis
                if inner.startswith('(') and inner.endswith(')'):
                    inner = inner[1:-1]
                polys = []
                depth = 0
                cur = ''
                # Particionar por polígonos de primer nivel
                for ch in inner:
                    if ch == '(':
                        depth += 1
                    if ch == ')':
                        depth -= 1
                    cur += ch
                    if depth == 0 and cur.strip():
                        poly_txt = cur.strip()
                        if poly_txt.startswith('(') and poly_txt.endswith(')'):
                            poly_txt = poly_txt[1:-1]
                        # Ahora poly_txt contiene: (ring1),(ring2)...
                        rings = []
                        ring_depth = 0
                        ring_cur = ''
                        for ch2 in poly_txt:
                            if ch2 == '(':
                                ring_depth += 1
                            if ch2 == ')':
                                ring_depth -= 1
                            ring_cur += ch2
                            if ring_depth == 0 and ring_cur.strip():
                                ring_txt = ring_cur.strip()
                                if ring_txt.startswith('(') and ring_txt.endswith(')'):
                                    ring_txt = ring_txt[1:-1]
                                rings.append(_coords_from_ring(ring_txt))
                                ring_cur = ''
                        polys.append(rings)
                        cur = ''
                return {'type': 'MultiPolygon', 'coordinates': polys}

            if upper.startswith('POLYGON'):
                inner = txt[len('POLYGON'):].strip()
                if inner.startswith('(') and inner.endswith(')'):
                    inner = inner[1:-1]
                rings = []
                depth = 0
                cur = ''
                for ch in inner:
                    if ch == '(':
                        depth += 1
                    if ch == ')':
                        depth -= 1
                    cur += ch
                    if depth == 0 and cur.strip():
                        ring_txt = cur.strip()
                        if ring_txt.startswith('(') and ring_txt.endswith(')'):
                            ring_txt = ring_txt[1:-1]
                        rings.append(_coords_from_ring(ring_txt))
                        cur = ''
                return {'type': 'Polygon', 'coordinates': rings}

            if upper.startswith('LINESTRING'):
                inner = txt[len('LINESTRING'):].strip()
                if inner.startswith('(') and inner.endswith(')'):
                    inner = inner[1:-1]
                return {'type': 'LineString', 'coordinates': _coords_from_ring(inner)}

            if upper.startswith('POINT'):
                inner = txt[len('POINT'):].strip()
                if inner.startswith('(') and inner.endswith(')'):
                    inner = inner[1:-1]
                parts = [p for p in inner.replace(',', ' ').split() if p]
                if len(parts) >= 2:
                    return {'type': 'Point', 'coordinates': [float(parts[0]), float(parts[1])]}
        except Exception:
            return None
        return None

    # Helpers para detectar lon/lat y aplicar transformación de coordenadas
    def _iter_coords(geom):
        """Generador de pares (x, y) dentro de un GeoJSON simple."""
        gtype = geom.get('type') if isinstance(geom, dict) else None
        coords = geom.get('coordinates') if isinstance(geom, dict) else None
        if gtype == 'Point' and isinstance(coords, (list, tuple)) and len(coords) >= 2:
            yield coords[0], coords[1]
        elif gtype == 'LineString' and isinstance(coords, list):
            for xy in coords:
                if isinstance(xy, (list, tuple)) and len(xy) >= 2:
                    yield xy[0], xy[1]
        elif gtype == 'Polygon' and isinstance(coords, list):
            for ring in coords:
                for xy in ring:
                    if isinstance(xy, (list, tuple)) and len(xy) >= 2:
                        yield xy[0], xy[1]
        elif gtype == 'MultiPolygon' and isinstance(coords, list):
            for poly in coords:
                for ring in poly:
                    for xy in ring:
                        if isinstance(xy, (list, tuple)) and len(xy) >= 2:
                            yield xy[0], xy[1]

    def _looks_like_lonlat(geom, sample_limit=50):
        cnt = 0
        for x, y in _iter_coords(geom):
            cnt += 1
            if x < -180 or x > 180 or y < -90 or y > 90:
                return False
            if cnt >= sample_limit:
                break
        # Si no hay coordenadas, no transformamos
        return True

    def _transform_geom(geom, transformer):
        gtype = geom.get('type')
        coords = geom.get('coordinates')
        if gtype == 'Point':
            x, y = coords[0], coords[1]
            lon, lat = transformer.transform(x, y)
            geom['coordinates'] = [lon, lat]
        elif gtype == 'LineString':
            geom['coordinates'] = [list(transformer.transform(x, y)) for x, y in coords]
        elif gtype == 'Polygon':
            new_rings = []
            for ring in coords:
                new_rings.append([list(transformer.transform(x, y)) for x, y in ring])
            geom['coordinates'] = new_rings
        elif gtype == 'MultiPolygon':
            new_polys = []
            for poly in coords:
                new_rings = []
                for ring in poly:
                    new_rings.append([list(transformer.transform(x, y)) for x, y in ring])
                new_polys.append(new_rings)
            geom['coordinates'] = new_polys
        return geom

    def _get_source_crs_for_capa(capa_id):
        """Obtiene CRS fuente desde settings por id o nombre de capa, o default."""
        try:
            by_id = getattr(settings, 'GEO_SOURCE_CRS_BY_CAPA_ID', {}) or {}
            by_name = getattr(settings, 'GEO_SOURCE_CRS_BY_CAPA_NAME', {}) or {}
            default_crs = getattr(settings, 'GEO_SOURCE_CRS_DEFAULT', None)
        except Exception:
            by_id, by_name, default_crs = {}, {}, None

        if capa_id in by_id:
            return by_id.get(capa_id)
        nombre = capas_info.get(capa_id)
        if nombre and nombre in by_name:
            return by_name.get(nombre)
        return default_crs

    # Construir features
    elementos = (ElementoGeo.objects
                 .filter(capa_geo_id__in=capa_ids)
                 .only('codigo', 'nombre', 'geom_wkt', 'capa_geo_id'))

    features = []
    reproj_count = 0
    for e in elementos:
        geom = wkt_to_geo(e.geom_wkt)
        if not geom:
            continue
        # Intentar reproyección a WGS84 si es necesario y posible
        src_crs_str = _get_source_crs_for_capa(e.capa_geo_id)
        if Transformer is not None and src_crs_str:
            try:
                src_crs = CRS.from_user_input(src_crs_str)
                dst_crs = CRS.from_epsg(4326)
                transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
                if not _looks_like_lonlat(geom):
                    geom = _transform_geom(geom, transformer)
                    reproj_count += 1
            except Exception:
                # Si falla la reproyección, devolvemos la geometría tal cual
                pass
        features.append({
            'type': 'Feature',
            'properties': {
                'codigo': str(e.codigo) if e.codigo is not None else None,
                'nombre': e.nombre,
                'capa_id': e.capa_geo_id,
            },
            'geometry': geom,
        })

    fc = {
        'type': 'FeatureCollection',
        'features': features,
        'meta': {
            'capas': capa_ids,
            'count': len(features),
            'indicador_id': indicador.id,
            'reprojected_features': reproj_count,
        }
    }
    return JsonResponse(fc)

def configurar_layout_por_tipo(grafico, series_data):
    """
    Configura el layout de Plotly según el tipo de gráfico
    """
    # Layout base común
    layout = {
        'title': grafico.titulo or grafico.nombre,
        'showlegend': grafico.mostrar_leyenda,
        'height': grafico.altura_grafico,
        'margin': {
            'l': 80,  # Margen izquierdo más amplio para etiquetas
            'r': grafico.margen_derecho,
            'b': grafico.margen_inferior,
            't': 50,
            'pad': 4
        }
    }
    
    # Configuración de leyenda si está habilitada
    if grafico.mostrar_leyenda:
        layout['legend'] = {
            'orientation': 'h',
            'y': -0.3,
            'x': 0.5,
            'xanchor': 'center'
        }
    
    # Configuración específica por tipo de gráfico
    if grafico.tipo_grafico == 'bar_horizontal':
        layout.update({
            'xaxis': {
                'title': grafico.eje_y_titulo or '',  # En horizontal, el eje X muestra los valores
                'zeroline': True,
                'automargin': True
            },
            'yaxis': {
                'title': grafico.eje_x_titulo or '',  # En horizontal, el eje Y muestra las categorías
                'automargin': True,
                'categoryorder': 'total ascending'  # Ordenar por valores
            }
        })
    elif grafico.tipo_grafico in ['barras_apiladas']:
        layout.update({
            'barmode': 'stack',  # Apilar las barras
            'xaxis': {
                'title': grafico.eje_x_titulo or '',
                'automargin': True
            },
            'yaxis': {
                'title': grafico.eje_y_titulo or '',
                'automargin': True
            }
        })
    elif grafico.tipo_grafico == 'pie':
        layout.update({
            'showlegend': True,  # Los pie charts necesitan leyenda
            'margin': {'l': 20, 'r': 20, 'b': 20, 't': 50}
        })
    elif grafico.tipo_grafico == 'treemap':
        layout.update({
            'showlegend': False,  # Los treemaps no necesitan leyenda
            'margin': {'l': 10, 'r': 10, 'b': 10, 't': 50}
        })
    elif grafico.tipo_grafico == 'piramide_poblacional':
        # Para la pirámide poblacional, necesitamos calcular los ticks del eje X
        # basados en los valores reales de las series
        tick_vals = []
        tick_text = []
        
        # Obtener los valores mínimos y máximos de las series
        if series_data:
            # Extraer todos los valores x de las series
            all_x_values = []
            for serie in series_data:
                all_x_values.extend(serie.get('x', []))
            
            if all_x_values:
                # Calcular valores para ticks positivos
                max_val = max(abs(v) for v in all_x_values)
                # Crear ticks simétricos positivos
                tick_count = 5
                step = max_val / tick_count if max_val > 0 else 1
                
                # Crear valores de tick de -max a +max pero mostrar como positivos
                tick_positions = []
                tick_labels = []
                
                for i in range(-tick_count, tick_count + 1):
                    pos = i * step
                    tick_positions.append(pos)
                    tick_labels.append(f'{abs(pos):.1f}%')
                
                tick_vals = tick_positions
                tick_text = tick_labels
        
        layout.update({
            'xaxis': {
                'title': 'Porcentaje de Población',
                'zeroline': True,
                'automargin': True,
                'tickmode': 'array',
                'tickvals': tick_vals,
                'ticktext': tick_text
            },
            'yaxis': {
                'title': 'Rango de Edad',
                'automargin': True,
                'categoryorder': 'array',
                'categoryarray': []  # Se llenará dinámicamente
            },
            'barmode': 'overlay'  # Para que las barras se superpongan en el centro
        })
    else:
        # Configuración para line, bar, area, etc.
        layout.update({
            'xaxis': {
                'title': grafico.eje_x_titulo or '',
                'tickmode': 'linear' if grafico.mostrar_todas_etiquetas_x else 'auto',
                'dtick': 1 if grafico.mostrar_todas_etiquetas_x else None,
                'automargin': True
            },
            'yaxis': {
                'title': grafico.eje_y_titulo or '',
                'zeroline': True,
                'automargin': True
            }
        })
    
    return layout


def aplicar_rangos_ejes(plotly_grafico, grafico, series_data):
    """
    Aplica configuración de rangos a los ejes según el tipo de gráfico
    """
    if not series_data or grafico.tipo_grafico in ['pie']:
        return
    
    # Determinar qué eje contiene los valores numéricos
    valor_eje = 'xaxis' if grafico.tipo_grafico == 'bar_horizontal' else 'yaxis'
    
    # Recopilar valores numéricos
    all_values = []
    for serie in series_data:
        if grafico.tipo_grafico == 'bar_horizontal':
            # En barras horizontales, los valores están en 'x'
            values = serie.get('x', [])
        else:
            # En otros tipos, los valores están en 'y'
            values = serie.get('y', [])
        
        for val in values:
            if val is not None:
                try:
                    all_values.append(float(val))
                except (ValueError, TypeError):
                    continue
    
    if not all_values:
        return
    
    # Calcular rangos
    if grafico.rango_personalizado_min is not None and grafico.rango_personalizado_max is not None:
        val_min = grafico.rango_personalizado_min
        val_max = grafico.rango_personalizado_max
    else:
        val_min = min(all_values)
        val_max = max(all_values)
        
        # Calcular margen
        data_range = val_max - val_min
        margin = max(data_range * 0.1, 1) if data_range > 0 else 1
        
        # Ajustar según begin_at_zero
        if grafico.begin_at_zero:
            val_min = 0
            val_max = val_max + margin
        else:
            val_min = val_min - margin
            val_max = val_max + margin
    
    # Aplicar rango al eje correspondiente
    plotly_grafico['layout'][valor_eje]['range'] = [val_min, val_max]


@cache_grafico_data(timeout=getattr(settings, 'CACHE_TIMEOUT_API', 30 * 60))
def get_desagregaciones(request, indicador_id):
    # Obtener el indicador
    indicador = get_object_or_404(Indicador, id=indicador_id, activo=True)
    
    # Obtener las desagregaciones geográficas y temáticas asociadas al indicador
    # Necesitamos obtener las desagregaciones, no los dominios
    desagregaciones_geograficas = set()
    desagregaciones_tematicas = set()
    
    # Recorrer los datos del indicador para obtener las desagregaciones reales
    datos = Dato.objects.filter(indicador=indicador)
    
    # Obtener desagregaciones geográficas
    for dato in datos:
        desagregaciones_geograficas.update(dato.desagregaciones_geograficas.all())
        
    # Obtener desagregaciones temáticas
    for dato in datos:
        desagregaciones_tematicas.update(dato.desagregaciones_tematicas.all())
        
    # Obtener el rango de años disponible para este indicador
    if datos.exists():
        anos = [dato.fecha_dato.year for dato in datos]
        ano_min_disponible = min(anos)
        ano_max_disponible = max(anos)
    else:
        # Valores por defecto si no hay datos
        ano_min_disponible = 2010
        ano_max_disponible = 2025
    
    # Obtener el primer gráfico asociado al indicador para obtener los valores predeterminados
    grafico = indicador.graficos.first()
    
    # Determinar los valores de rango de años a usar
    if grafico and (grafico.rango_anios_min is not None or grafico.rango_anios_max is not None):
        # Usar los valores predeterminados del gráfico si están definidos
        ano_min = grafico.rango_anios_min if grafico.rango_anios_min is not None else ano_min_disponible
        ano_max = grafico.rango_anios_max if grafico.rango_anios_max is not None else ano_max_disponible
    else:
        # Usar los valores disponibles si no hay valores predeterminados
        ano_min = ano_min_disponible
        ano_max = ano_max_disponible
    
    # Obtener desagregaciones predeterminadas del gráfico
    desagregaciones_geo_predeterminadas = []
    desagregaciones_tem_predeterminadas = []
    
    if grafico:
        desagregaciones_geo_predeterminadas = [
            desag.id for desag in grafico.desagregaciones_geograficas_predeterminadas.all()
        ]
        desagregaciones_tem_predeterminadas = [
            desag.id for desag in grafico.desagregaciones_tematicas_predeterminadas.all()
        ]
    
    # Agrupar desagregaciones por dominio para renderizar un control de
    # filtro por cada dominio (con soporte de jerarquía dominio_padre /
    # desagregacion_padre para filtros en cascada)
    todas_desagregaciones = list(desagregaciones_geograficas) + list(desagregaciones_tematicas)
    dominios_ids = {d.dominio_id for d in todas_desagregaciones if d.dominio_id}
    dominios_qs = DominioDesagregacion.objects.filter(id__in=dominios_ids).select_related('dominio_padre')
    dominios_map = {d.id: d for d in dominios_qs}
    predeterminadas_ids = set(desagregaciones_geo_predeterminadas) | set(desagregaciones_tem_predeterminadas)

    dominios_data = []
    for dominio in sorted(dominios_map.values(), key=lambda d: (d.dominio_padre_id or d.id, d.id)):
        desags_dominio = [d for d in todas_desagregaciones if d.dominio_id == dominio.id]
        dominios_data.append({
            'id': dominio.id,
            'nombre': dominio.nombre,
            'tipo': dominio.tipo,
            'dominio_padre': dominio.dominio_padre_id,
            'desagregaciones': [
                {
                    'id': desag.id,
                    'nombre': desag.nombre,
                    'desagregacion_padre': desag.desagregacion_padre_id,
                    'predeterminada': desag.id in predeterminadas_ids,
                }
                for desag in sorted(desags_dominio, key=lambda d: d.nombre)
            ],
        })

    # Preparar los datos de las desagregaciones
    desagregaciones_data = {
        'dominios': dominios_data,
        'desagregaciones_geograficas': [
            {
                'id': desag.id,
                'nombre': desag.nombre,
                'predeterminada': desag.id in desagregaciones_geo_predeterminadas
            }
            for desag in desagregaciones_geograficas
        ],
        'desagregaciones_tematicas': [
            {
                'id': desag.id,
                'nombre': desag.nombre,
                'predeterminada': desag.id in desagregaciones_tem_predeterminadas
            }
            for desag in desagregaciones_tematicas
        ],
        'rango_anios': {
            'min': ano_min,
            'max': ano_max,
            'min_disponible': ano_min_disponible,
            'max_disponible': ano_max_disponible
        }
    }

    # Si el indicador está enlazado a un conjunto del catálogo de consulta,
    # el front renderiza el cuadro de consulta en lugar de buscar Datos.
    if indicador.catalogo_consulta_id:
        conjunto = indicador.catalogo_consulta
        desagregaciones_data['catalogo_consulta'] = {
            'id': conjunto.pk,
            'nombre': conjunto.nombre,
            'tipo_consulta': conjunto.tipo_consulta,
            'tipo_display': conjunto.get_tipo_consulta_display(),
            'columnas': conjunto.columnas or [],
            'filas': conjunto.filas or [],
            'url': reverse('indicadores:catalogo_consulta_detalle', args=[conjunto.pk]),
        }

    return JsonResponse(desagregaciones_data, safe=False)


def get_ficha_tecnica_conjunto_datos(request, indicador_id):
    """
    Devuelve la ficha técnica de variables de conjunto_datos en formato JSON.
    """
    try:
        indicador = get_object_or_404(Indicador, id=indicador_id, activo=True)
        
        # Obtener todas las variables asociadas al indicador
        variables = indicador.variables_conjunto_datos.all().order_by('orden', 'codigo_variable')
        
        # Serializar las variables
        variables_data = []
        for variable in variables:
            variables_data.append({
                'id': variable.id,
                'codigo_variable': variable.codigo_variable,
                'nombre_variable': variable.nombre_variable,
                'definicion_conceptual': variable.definicion_conceptual,
                'poblacion_objetivo': variable.poblacion_objetivo,
                'cobertura_geografica': variable.cobertura_geografica,
                'desagregacion_geografica': variable.desagregacion_geografica,
                'desagregacion_tematica': variable.desagregacion_tematica,
                'tipo_dato': variable.tipo_dato,
                'dominio_dato': variable.dominio_dato,
                'unidad_medida': variable.unidad_medida,
                'tipo_variable_estadistica': variable.tipo_variable_estadistica,
                'fuente_datos': variable.fuente_datos,
                'periodicidad': variable.periodicidad,
                'observaciones': variable.observaciones,
                'organismo_productor': (variable.organismo_productor.nombre if variable.organismo_productor else (variable.organismo_productor_legado or '')),
                'orden': variable.orden
            })
        
        return JsonResponse(variables_data, safe=False)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_conjunto_datos_csv(request, indicador_id=None, conjunto_datos_id=None):
    """
    Devuelve el archivo CSV de conjunto_datos asociado a un indicador o directamente por ID de conjunto_datos.
    - 404 si el indicador/conjunto_datos no existe o no tiene archivo.
    - 500 si ocurre un error al abrir el archivo.
    """
    try:
        conjunto_datos = None
        
        # Si se proporciona conjunto_datos_id, usarlo directamente
        if conjunto_datos_id:
            conjunto_datos = get_object_or_404(ConjuntoDatos, id=conjunto_datos_id)
        # Si se proporciona indicador_id, obtener el conjunto_datos a través del indicador
        elif indicador_id:
            # Obtener el indicador activo
            indicador = get_object_or_404(Indicador, id=indicador_id, activo=True)
            
            # Validar que el indicador tenga conjunto_datos asociado
            if not indicador.conjunto_datos:
                return JsonResponse(
                    {'error': f'El indicador "{indicador.nombre}" no tiene conjunto_datos asociado.'}, 
                    status=404
                )
            conjunto_datos = indicador.conjunto_datos
        else:
            return JsonResponse(
                {'error': 'Se requiere indicador_id o conjunto_datos_id'}, 
                status=400
            )
        
        # Validar que el conjunto_datos tenga archivo CSV
        if not conjunto_datos.archivo_csv:
            return JsonResponse({'error': f'El conjunto_datos "{conjunto_datos.nombre}" no tiene archivo CSV.'}, status=404)

        ffield = conjunto_datos.archivo_csv
        file_handle = None

        # Try multiple file path strategies
        file_paths_to_try = []
        
        # Strategy 1: Direct path from BASE_DIR + field name
        rel_path = ffield.name
        file_paths_to_try.append(os.path.join(getattr(settings, 'BASE_DIR', ''), rel_path))
        
        # Strategy 2: Direct path in conjunto_datos directory using filename only
        filename = os.path.basename(rel_path)
        file_paths_to_try.append(os.path.join(getattr(settings, 'BASE_DIR', ''), 'conjunto_datos', filename))
        
        # Strategy 3: Try storage if available (but don't rely on exists() method)
        if hasattr(ffield, 'storage'):
            try:
                file_handle = ffield.storage.open(ffield.name, 'rb')
                # If we get here, the file was opened successfully
            except Exception:
                # Storage failed, continue with file system paths
                pass
        
        # Try file system paths if storage didn't work
        if file_handle is None:
            for path in file_paths_to_try:
                try:
                    if os.path.exists(path):
                        file_handle = open(path, 'rb')
                        break
                except Exception:
                    continue

        if file_handle is None:
            return JsonResponse({'error': f'No se encontró el archivo CSV: {ffield.name}'}, status=404)

        # Para requests AJAX, devolver el contenido como texto plano en lugar de FileResponse
        if request.headers.get('Accept') == 'application/json' or 'XMLHttpRequest' in request.headers.get('X-Requested-With', ''):
            try:
                content = file_handle.read().decode('utf-8')
                file_handle.close()
                return HttpResponse(content, content_type='text/csv')
            except UnicodeDecodeError:
                try:
                    file_handle.seek(0)
                    content = file_handle.read().decode('latin1')
                    file_handle.close()
                    return HttpResponse(content, content_type='text/csv')
                except Exception as e:
                    file_handle.close()
                    return JsonResponse({'error': f'Error al leer el archivo CSV: {str(e)}'}, status=500)

        # Para descargas normales, usar FileResponse
        filename = os.path.basename(ffield.name) or f"conjunto_datos_indicador_{indicador_id}.csv"
        return FileResponse(file_handle, as_attachment=True, filename=filename, content_type='text/csv')
        
    except Exception as e:
        return JsonResponse({'error': f'Error interno del servidor: {str(e)}'}, status=500)


def crear_grafico_pie(grafico, series_data, ano_inicio, ano_fin, desagregaciones_geograficas_ids=None, desagregaciones_tematicas_ids=None):
    """
    Crea un gráfico pie consolidado a partir de múltiples series
    Aplica los filtros de desagregaciones seleccionados en el frontend
    """
    if not series_data:
        return []
    
    # Para gráficos pie, usar siempre el año final (año máximo seleccionado)
    ano_objetivo = ano_fin if ano_fin else ano_inicio
    if not ano_objetivo:
        # Buscar el último año disponible en los datos
        anos_disponibles = []
        for serie in grafico.series.all():
            qs = Dato.objects.filter(indicador=grafico.indicador)
            for desag in serie.get_desagregaciones():
                if desag.dominio and desag.dominio.tipo == 'geografica':
                    qs = qs.filter(desagregaciones_geograficas=desag)
                else:
                    qs = qs.filter(desagregaciones_tematicas=desag)
            anos_disponibles.extend(qs.values_list('fecha_dato__year', flat=True))
        ano_objetivo = max(anos_disponibles) if anos_disponibles else None
    
    if not ano_objetivo:
        return []
    
    # Para gráficos pie, generar segmentos basados en los filtros seleccionados
    # en lugar de usar las series predefinidas del gráfico
    labels = []
    values = []
    colors = []
    
    # Obtener datos base para el año objetivo
    datos_base = Dato.objects.filter(
        indicador=grafico.indicador,
        fecha_dato__year=ano_objetivo
    )
    
    # Si hay filtros de desagregaciones seleccionados, usarlos
    if desagregaciones_geograficas_ids or desagregaciones_tematicas_ids:
        # AND entre dominios, OR dentro del mismo dominio
        datos_base = filtrar_datos_por_desagregaciones(
            datos_base, desagregaciones_geograficas_ids, desagregaciones_tematicas_ids
        )

        # Agrupar por desagregaciones para crear segmentos del pie
        # Priorizar desagregaciones temáticas para los segmentos
        if desagregaciones_tematicas_ids:
            # Agrupar por desagregación temática
            for desag_id in desagregaciones_tematicas_ids:
                datos_segmento = datos_base.filter(desagregaciones_tematicas__id=desag_id)
                valor_total = sum(dato.valor_dato for dato in datos_segmento if dato.valor_dato > 0)
                
                if valor_total > 0:
                    desagregacion = Desagregacion.objects.get(id=desag_id)
                    labels.append(desagregacion.nombre)
                    values.append(float(valor_total))
                    # Buscar color de serie si existe
                    serie_color = grafico.series.filter(desagregacion_tematica_id=desag_id).first()
                    if serie_color and serie_color.color and serie_color.color != '#000000' and serie_color.color.lower() != 'rgb(0,0,0)':
                        colors.append(serie_color.color)
        
        elif desagregaciones_geograficas_ids:
            # Agrupar por desagregación geográfica
            for desag_id in desagregaciones_geograficas_ids:
                datos_segmento = datos_base.filter(desagregaciones_geograficas__id=desag_id)
                valor_total = sum(dato.valor_dato for dato in datos_segmento if dato.valor_dato > 0)
                
                if valor_total > 0:
                    desagregacion = Desagregacion.objects.get(id=desag_id)
                    labels.append(desagregacion.nombre)
                    values.append(float(valor_total))
                    # Buscar color de serie si existe
                    serie_color = grafico.series.filter(desagregacion_geografica_id=desag_id).first()
                    if serie_color and serie_color.color and serie_color.color != '#000000' and serie_color.color.lower() != 'rgb(0,0,0)':
                        colors.append(serie_color.color)
    
    else:
        # Si no hay filtros, usar las series predefinidas del gráfico
        for serie in grafico.series.all():
            # Obtener datos para el año específico
            datos = Dato.objects.filter(
                indicador=grafico.indicador,
                fecha_dato__year=ano_objetivo
            )
            
            # Aplicar filtros de desagregación de la serie (exactos por tipo)
            serie_desags = serie.get_desagregaciones()
            datos = _filtrar_datos_por_serie(datos, serie)

            # Obtener el valor
            dato = datos.first()
            if dato and dato.valor_dato > 0:  # Solo incluir valores positivos
                # Generar nombre del segmento
                if serie.nombre_personalizado:
                    nombre_segmento = serie.nombre_personalizado
                else:
                    nombres_desagregaciones = [d.nombre for d in serie_desags]
                    nombre_segmento = ' - '.join(nombres_desagregaciones) if nombres_desagregaciones else f'Serie {serie.orden}'
                
                labels.append(nombre_segmento)
                values.append(float(dato.valor_dato))
                if serie.color and serie.color != '#000000' and serie.color.lower() != 'rgb(0,0,0)':
                    colors.append(serie.color)
    
    # Crear el gráfico pie consolidado
    if labels and values:
        pie_data = {
            'type': 'pie',
            'labels': labels,
            'values': values,
            'name': grafico.nombre or 'Distribución'
        }
        
        # Agregar colores si están disponibles
        if colors and len(colors) == len(labels):
            pie_data['marker'] = {'colors': colors}
        
        return [pie_data]
    
    return []


def crear_grafico_treemap(grafico, series_data, ano_inicio, ano_fin, desagregaciones_geograficas_ids=None, desagregaciones_tematicas_ids=None):
    """
    Crea un gráfico treemap para un año específico (similar a pie chart)
    Usa el año final seleccionado o el último disponible
    """
    if not series_data:
        return []
    
    # Para treemaps, usar siempre el año final (año máximo seleccionado)
    ano_objetivo = ano_fin if ano_fin else ano_inicio
    if not ano_objetivo:
        # Buscar el último año disponible en los datos
        ultimo_ano = Dato.objects.filter(
            indicador=grafico.indicador
        ).aggregate(Max('fecha_dato'))['fecha_dato__max']
        
        if ultimo_ano:
            ano_objetivo = ultimo_ano.year
    
    if not ano_objetivo:
        return []
    
    # Para treemaps, generar segmentos basados en los filtros seleccionados
    labels = []
    values = []
    parents = []
    colors = []
    
    # Obtener datos base para el año objetivo
    datos_base = Dato.objects.filter(
        indicador=grafico.indicador,
        fecha_dato__year=ano_objetivo
    )
    
    # Aplicar filtros de desagregaciones si se proporcionan
    # (AND entre dominios, OR dentro del mismo dominio)
    datos_base = filtrar_datos_por_desagregaciones(
        datos_base, desagregaciones_geograficas_ids, desagregaciones_tematicas_ids
    )

    # Agrupar por desagregaciones para crear segmentos del treemap
    # Priorizar desagregaciones temáticas para los segmentos
    if desagregaciones_tematicas_ids:
        # Agrupar por desagregación temática
        
        datos_agrupados = datos_base.values(
            'desagregaciones_tematicas__nombre'
        ).annotate(
            total=Sum('valor_dato')
        ).order_by('-total')
        
        for item in datos_agrupados:
            nombre_desag = item['desagregaciones_tematicas__nombre']
            if nombre_desag and item['total']:
                labels.append(nombre_desag)
                values.append(float(item['total']))
                parents.append("")  # Nivel raíz para treemap
    else:
        # Si no hay filtros temáticos, usar todas las desagregaciones temáticas disponibles
        datos_agrupados = datos_base.values(
            'desagregaciones_tematicas__nombre'
        ).annotate(
            total=Sum('valor_dato')
        ).order_by('-total')
        
        for item in datos_agrupados:
            nombre_desag = item['desagregaciones_tematicas__nombre']
            if nombre_desag and item['total']:
                labels.append(nombre_desag)
                values.append(float(item['total']))
                parents.append("")  # Nivel raíz para treemap
    
    # Obtener colores de las series si están disponibles
    for serie in grafico.series.all():
        if serie.color and serie.color != '#000000' and serie.color.lower() != 'rgb(0,0,0)':
            colors.append(serie.color)
    
    # Crear el gráfico treemap
    if labels and values:
        # Calcular el total para porcentajes
        total_valores = sum(values)
        
        treemap_data = {
            'type': 'treemap',
            'labels': labels,
            'values': values,
            'parents': parents,
            'name': grafico.nombre or 'Distribución',
            'textinfo': 'label+percent parent',
        }
        
        # Agregar colores si están disponibles
        if colors and len(colors) >= len(labels):
            treemap_data['marker'] = {'colors': colors[:len(labels)]}
        
        return [treemap_data]
    
    return []


def crear_piramide_poblacional(grafico, datos_filtrados):
    """
    Crea una pirámide poblacional con barras horizontales espejo por género
    Asume que hay desagregaciones de género (Hombre/Mujer) y rangos de edad
    Muestra porcentajes en lugar de valores absolutos
    """
    
    # Agrupar datos por desagregaciones
    datos_por_genero_edad = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
    
    # Identificar desagregaciones de género y edad
    generos = set()
    rangos_edad = set()
    
    # Calcular el total de población
    total_poblacion = Decimal('0')
    
    for dato in datos_filtrados:
        # Buscar desagregaciones de género
        genero = None
        rango_edad = None
        
        for desag_geo in dato.desagregaciones_geograficas.all():
            nombre_lower = desag_geo.nombre.lower()
            if any(word in nombre_lower for word in ['hombre', 'mujer', 'masculino', 'femenino', 'sexo']):
                genero = desag_geo.nombre
                generos.add(genero)
        
        for desag_tem in dato.desagregaciones_tematicas.all():
            nombre_lower = desag_tem.nombre.lower()
            if any(word in nombre_lower for word in ['hombre', 'mujer', 'masculino', 'femenino', 'sexo']):
                genero = desag_tem.nombre
                generos.add(genero)
            elif any(word in nombre_lower for word in ['edad', 'años', 'año']) or '-' in desag_tem.nombre:
                rango_edad = desag_tem.nombre
                rangos_edad.add(rango_edad)
            else:
                # Detectar rangos abiertos como "85 y más" o notación con '+' (p.ej., "85+")
                try:
                    if re.search(r"\b\d+\s*(\+|y\s*m[aá]s)\b", nombre_lower):
                        rango_edad = desag_tem.nombre
                        rangos_edad.add(rango_edad)
                except Exception:
                    pass
        
        if genero and rango_edad:
            datos_por_genero_edad[genero][rango_edad] += dato.valor_dato
            total_poblacion += dato.valor_dato
    
    # Ordenar rangos de edad (asumiendo formato "X-Y años" o similar)
    rangos_ordenados = sorted(list(rangos_edad), key=lambda x: extraer_edad_inicial(x))
    
    series_data = []
    
    # Crear series para cada género
    # Primero procesamos las mujeres (lado derecho)
    for genero in sorted(list(generos), key=lambda x: 0 if ('mujer' in x.lower() or 'femenino' in x.lower()) else 1):
        valores = []
        for rango in rangos_ordenados:
            valor = datos_por_genero_edad[genero][rango]
            # Convertir a porcentaje si hay población total
            if total_poblacion > 0:
                valor = float(valor / total_poblacion) * 100
            else:
                valor = 0
            # Para pirámide, los valores de un lado deben ser negativos (solo para el efecto visual)
            if 'hombre' in genero.lower() or 'masculino' in genero.lower():
                valor = -abs(valor)  # Lado izquierdo (negativo para efecto visual)
            valores.append(valor)
        
        serie = {
            'type': 'bar',
            'orientation': 'h',
            'x': valores,
            'y': rangos_ordenados,
            'name': genero,
            'marker': {
                'color': '#3498db' if 'hombre' in genero.lower() or 'masculino' in genero.lower() else '#e74c3c'
            },
            'hovertemplate': '%{y}<br>%{text}: %{customdata:.1f}%<extra></extra>',
            'text': [genero] * len(valores),
            'customdata': [abs(v) for v in valores]  # Valores positivos para mostrar en hover
        }
        series_data.append(serie)
    
    return series_data


def extraer_edad_inicial(rango_edad):
    """
    Extrae la edad inicial de un rango para ordenamiento
    Ej: "0-4 años" -> 0, "15-19 años" -> 15
    """
    match = re.search(r'(\d+)', rango_edad)
    return int(match.group(1)) if match else 0


def visor_comparativo_standalone(request):
    """Vista para el visor comparativo independiente sin base.html"""
    dominios = MenuDominio.objects.filter(activo=True).order_by('orden')
    context = {
        'dominios': dominios,
    }
    return render(request, 'indicadores/visor_comparativo_standalone.html', context)


from django.views.decorators.http import require_http_methods
import traceback

@require_http_methods(["GET"])
def api_buscar_indicadores(request):
    """
    API endpoint to perform semantic search on indicators
    Expected query param: q (search query)
    """
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'success': False, 'error': 'Search query is required'}, status=400)
    
    try:
        from .search import SemanticSearch
        from .models import Indicador
        from django.db.models import Q
        
        # Búsqueda por palabra clave (match exacto o parcial)
        keyword_indicadores = list(Indicador.objects.filter(
            Q(nombre__icontains=query) | Q(codigo_indicador__icontains=query),
            activo=True
        ).select_related('subtema__tema__dominio'))
        
        # Búsqueda semántica
        search_service = SemanticSearch()
        resultados = search_service.buscar_similar(
            consulta=query,
            tipo_doc='indicador',
            top_k=10,  # Return top 10 results
            umbral=0.4 # Minimum similarity threshold
        )
        
        if not resultados and not keyword_indicadores:
            return JsonResponse({'success': True, 'resultados': [], 'mensaje': 'No se encontraron resultados'})
            
        # Get IDs of matched indicators for semantic search
        indicador_ids = [r['referencia_id'] for r in resultados]
        
        # Fetch indicator details from DB for semantic search
        semantic_indicadores = Indicador.objects.filter(
            id__in=indicador_ids,
            activo=True
        ).select_related('subtema__tema__dominio')
        
        # Create a map to preserve search relevance order
        indicadores_map = {ind.id: ind for ind in semantic_indicadores}
        
        resultados_formateados = []
        procesados_ids = set()
        
        # Primero agregar resultados por coincidencia de texto (prioridad alta)
        for ind in keyword_indicadores:
            if ind.subtema and ind.subtema.tema and ind.subtema.tema.dominio:
                procesados_ids.add(ind.id)
                resultados_formateados.append({
                    'id': ind.id,
                    'nombre': ind.nombre,
                    'codigo': ind.codigo_indicador,
                    'similitud': 1.0,  # Máxima similitud para match de texto
                    'dominio_slug': ind.subtema.tema.dominio.slug,
                    'dominio_nombre': ind.subtema.tema.dominio.nombre,
                    'tema_slug': ind.subtema.tema.slug,
                    'tema_nombre': ind.subtema.tema.nombre,
                    'subtema_slug': ind.subtema.slug,
                    'subtema_nombre': ind.subtema.nombre
                })
                
        # Luego agregar resultados de búsqueda semántica
        for res in resultados:
            ref_id = res['referencia_id']
            if ref_id in indicadores_map and ref_id not in procesados_ids:
                ind = indicadores_map[ref_id]
                procesados_ids.add(ind.id)
                
                # Make sure we have the full hierarchy
                if ind.subtema and ind.subtema.tema and ind.subtema.tema.dominio:
                    resultados_formateados.append({
                        'id': ind.id,
                        'nombre': ind.nombre,
                        'codigo': ind.codigo_indicador,
                        'similitud': round(res['similitud'], 3),
                        'dominio_slug': ind.subtema.tema.dominio.slug,
                        'dominio_nombre': ind.subtema.tema.dominio.nombre,
                        'tema_slug': ind.subtema.tema.slug,
                        'tema_nombre': ind.subtema.tema.nombre,
                        'subtema_slug': ind.subtema.slug,
                        'subtema_nombre': ind.subtema.nombre
                    })
                    
        return JsonResponse({
            'success': True,
            'resultados': resultados_formateados,
            'total': len(resultados_formateados)
        })
        
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_indicador_metadata(request):
    """
    Devuelve la metadata existente de un indicador para precargar formularios.
    Query param: indicador_id
    """
    indicador_id = request.GET.get('indicador_id')
    if not indicador_id:
        return JsonResponse({'success': False, 'error': 'indicador_id requerido'}, status=400)
    try:
        i = Indicador.objects.select_related(
            'subtema__tema__dominio', 'organismo_responsable', 'suborganismo'
        ).get(id=indicador_id, activo=True)
        metadata = {
            'Grupo_Indicador': i.grupo_indicador or '',
            'Dominio': i.subtema.tema.dominio.nombre if i.subtema and i.subtema.tema and i.subtema.tema.dominio else '',
            'Tema': i.subtema.tema.nombre if i.subtema and i.subtema.tema else '',
            'Subtema': i.subtema.nombre if i.subtema else '',
            'Codigo_Indicador': i.codigo_indicador or '',
            'Nombre_Indicador': i.nombre or '',
            'Sigla': i.sigla or '',
            'Descripcion_Indicador': i.descripcion_indicador or '',
            'Objetivo': i.objetivo or '',
            'Justificacion': '',  # Campo legacy eliminado (mergeado en Comentarios_Adicionales)
            'Metodo_Medicion': i.metodo_medicion or '',
            'Formula': i.formula_ficha or '',
            'Variables': i.variables or '',
            'Unidad_Medida': i.unidad_medida or '',
            'Valores_Referencia': '',  # Campo legacy eliminado
            'Nomenclaturas_Clasificaciones': i.nomenclaturas_clasificaciones or '',
            'Alcance_Tematico': i.alcance_tematico or '',
            'Poblacion_Objetivo': i.poblacion_objetivo or '',
            'Cobertura_Geografica': i.cobertura_geografica or '',
            'Periodo_Referencia': i.periodo_referencia or '',
            'Periodo_Base': i.periodo_base or '',
            'Linea_Base': '',  # Campo legacy eliminado
            'Periodicidad': '',  # Campo legacy eliminado (usar Frecuencia_Difusion)
            'Fuente_Datos': i.fuente_datos or '',
            'Responsable': i.entidad_responsable or '',
            'Comentarios_Adicionales': i.comentarios_adicionales or '',
            'Fecha_Elaboracion': '',  # Campo legacy eliminado
            'Fecha_Actualizacion': '',  # Campo legacy eliminado (usar Fecha_Publicacion_Metadatos)
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
            'organismo_id': i.organismo_responsable_id or '',
            'suborganismo_id': i.suborganismo_id or '',
        }
        suborganismos = list(Suborganismo.objects.filter(
            organismo=i.organismo_responsable, activo=True
        ).values('id', 'nombre').order_by('orden', 'nombre')) if i.organismo_responsable else []
        return JsonResponse({
            'success': True,
            'metadata': metadata,
            'suborganismos': suborganismos,
        })
    except Indicador.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Indicador no encontrado'}, status=404)


def api_conjunto_datos_list(request):
    """Lista SOLO los datasets que tienen un registro en la tabla conjunto_datos.
    Se muestra el nombre desde BD (conjunto_datos.nombre) y se valida que el archivo exista
    en el storage del FileField (media/microdata/) para evitar enlaces rotos.
    """
    datasets = []
    vistos = set()
    try:
        for md in ConjuntoDatos.objects.all().order_by('nombre'):
            ffield = getattr(md, 'archivo_csv', None)
            if not ffield:
                continue
            rel_name = getattr(ffield, 'name', '') or ''
            fname = os.path.basename(rel_name)
            if not fname or not fname.lower().endswith('.csv'):
                continue
            if fname in vistos:
                continue
            try:
                fpath = ffield.storage.path(rel_name)
            except (NotImplementedError, ValueError):
                continue
            if not os.path.isfile(fpath):
                # Si no existe físicamente, omitir para no romper el flujo
                continue
            try:
                size = os.path.getsize(fpath)
            except OSError:
                size = None
            label = md.nombre or os.path.splitext(fname)[0].replace('_', ' ')
            datasets.append({
                'file': fname,
                'label': label,
                'size': size,
            })
            vistos.add(fname)
    except Exception:
        datasets = []

    return JsonResponse({'datasets': datasets})


def api_conjunto_datos_rows(request):
    """Devuelve filas JSON de un CSV en conjunto_datos/ con paginación básica.
    Parámetros:
      - file: nombre del archivo CSV (obligatorio)
      - limit: cantidad máxima de filas (por defecto 2000, máx 10000)
      - offset: desplazamiento de filas (por defecto 0)
      - encoding: opcional ('utf-8-sig' por defecto con fallback a 'latin-1')
      - columns: lista separada por comas de columnas a incluir (opcional)
    """
    file_param = (request.GET.get('file') or '').strip()
    if not file_param:
        return JsonResponse({'error': 'Parámetro "file" es requerido'}, status=400)

    # Evitar path traversal: solo nombre base. Autorización y ubicación salen
    # del registro de ConjuntoDatos: los CSV viven en media/microdata/
    file_name = os.path.basename(file_param)
    md = ConjuntoDatos.objects.filter(
        archivo_csv__iendswith='/' + file_name).first()
    if md is None:
        return JsonResponse({'error': 'Archivo no autorizado. Debe estar registrado en conjunto_datos.'}, status=404)

    try:
        csv_path = md.archivo_csv.path
    except (NotImplementedError, ValueError):
        csv_path = ''
    if not csv_path or not os.path.isfile(csv_path):
        return JsonResponse({'error': 'Archivo no encontrado'}, status=404)

    try:
        limit = int(request.GET.get('limit', '10000'))
        offset = int(request.GET.get('offset', '0'))
    except ValueError:
        return JsonResponse({'error': 'Parámetros de paginación inválidos'}, status=400)

    limit = max(1, min(limit, 10000))
    offset = max(0, offset)

    enc = request.GET.get('encoding') or 'utf-8-sig'
    fallbacks = [enc]
    if enc.lower() != 'latin-1':
        fallbacks.append('latin-1')

    # Parseo opcional de filtro de año y columnas a filtrar
    anio_inicio = request.GET.get('anio_inicio')
    anio_fin = request.GET.get('anio_fin')
    try:
        anio_inicio = int(anio_inicio) if anio_inicio is not None and anio_inicio != '' else None
    except ValueError:
        return JsonResponse({'error': 'Parámetro anio_inicio inválido'}, status=400)
    try:
        anio_fin = int(anio_fin) if anio_fin is not None and anio_fin != '' else None
    except ValueError:
        return JsonResponse({'error': 'Parámetro anio_fin inválido'}, status=400)

    columns_param = (request.GET.get('columns') or '').strip()
    selected_columns = [c for c in (columns_param.split(',') if columns_param else []) if c]

    try:
        logger.debug('api_conjunto_datos_rows | file=%s limit=%s offset=%s anio_inicio=%s anio_fin=%s columns=%s',
                     file_name, limit, offset, anio_inicio, anio_fin, columns_param)
    except Exception:
        pass

    fieldnames = []
    rows = []
    total = 0
    opened = False
    for encoding in fallbacks:
        try:
            with open(csv_path, 'r', encoding=encoding, newline='') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                # Detección de columna de año/fecha
                def _norm(s: str) -> str:
                    return (s or '').strip().lower().replace('ñ', 'n')

                year_col = None
                normalized_map = { c: _norm(c) for c in fieldnames }
                for c, n in normalized_map.items():
                    if n == 'fecha' or n == 'ano' or n == 'anio' or n == 'año':
                        year_col = c
                        break

                def _extract_year(val: str):
                    try:
                        s = str(val or '').strip()
                        # buscar 4 dígitos
                        m = re.search(r'(\d{4})', s)
                        if m:
                            return int(m.group(1))
                        # fallback: número directo
                        return int(s)
                    except Exception:
                        return None

                # Iteración con filtro por año (si aplica) o paginación clásica
                if anio_inicio is not None or anio_fin is not None:
                    if not year_col:
                        return JsonResponse({'error': 'No se encontró una columna "año" o "fecha" para filtrar'}, status=400)
                    filtered_total = 0
                    passed_offset = 0
                    for row in reader:
                        # Extraer y verificar año
                        y = _extract_year(row.get(year_col))
                        if y is None:
                            continue
                        if anio_inicio is not None and y < anio_inicio:
                            continue
                        if anio_fin is not None and y > anio_fin:
                            continue
                        # Cuenta de coincidencias totales con el filtro
                        filtered_total += 1
                        # Aplicar offset sobre el conjunto filtrado
                        if passed_offset < offset:
                            passed_offset += 1
                            continue
                        # Limitar cantidad devuelta
                        if len(rows) < limit:
                            if row is None:
                                continue
                            normalized_full = { (k or ''): v for k, v in row.items() }
                            if selected_columns:
                                normalized = { k: normalized_full.get(k, '') for k in selected_columns if k in normalized_full }
                            else:
                                normalized = normalized_full
                            rows.append(normalized)
                    total = filtered_total
                else:
                    # Paginación por filas (comportamiento anterior)
                    idx = 0
                    for row in reader:
                        # Saltar filas totalmente vacías (no cuentan en el total ni en la paginación)
                        try:
                            if row is None or not any(str(v or '').strip() for v in row.values()):
                                continue
                        except Exception:
                            # Si algo falla al evaluar la fila, omitirla sin contar
                            continue
                        total += 1
                        if idx < offset:
                            idx += 1
                            continue
                        if len(rows) < limit:
                            # Normalizar claves None -> ''
                            normalized_full = { (k or ''): v for k, v in row.items() }
                            if selected_columns:
                                # Conservar solo columnas seleccionadas (si existen en el CSV)
                                normalized = { k: normalized_full.get(k, '') for k in selected_columns if k in normalized_full }
                            else:
                                normalized = normalized_full
                            rows.append(normalized)
                        idx += 1
                opened = True
            break
        except UnicodeDecodeError:
            # Intentar con siguiente encoding
            fieldnames, rows, total = [], [], 0
            continue
        except Exception:
            return JsonResponse({'error': 'Error al leer el archivo CSV'}, status=500)

    if not opened:
        return JsonResponse({'error': 'No fue posible abrir el archivo con las codificaciones soportadas'}, status=500)

    try:
        logger.debug('api_conjunto_datos_rows | result file=%s total=%s returned_rows=%s limit=%s offset=%s columns=%s',
                     file_name, total, len(rows), limit, offset, ','.join(fieldnames or []))
    except Exception:
        pass

    try:
        return JsonResponse({
            'file': file_name,
            'columns': fieldnames,
            'rows': rows,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        logger.error(f'Error serializing JSON response for {file_name}: {str(e)}', exc_info=True)
        return JsonResponse({'error': 'Error al serializar la respuesta JSON', 'details': str(e)}, status=500)


def api_conjunto_datos_headers(request):
    """Devuelve únicamente las columnas (headers) de un CSV en conjunto_datos/.
    Parámetros:
      - file: nombre del archivo CSV (obligatorio)
      - encoding: opcional ('utf-8-sig' por defecto con fallback a 'latin-1')
    """
    file_param = (request.GET.get('file') or '').strip()
    if not file_param:
        return JsonResponse({'error': 'Parámetro "file" es requerido'}, status=400)

    file_name = os.path.basename(file_param)
    # Autorización y ubicación vía el registro de ConjuntoDatos
    # (los CSV viven en media/microdata/, no en BASE_DIR/conjunto_datos)
    md = ConjuntoDatos.objects.filter(
        archivo_csv__iendswith='/' + file_name).first()
    if md is None:
        return JsonResponse({'error': 'Archivo no autorizado. Debe estar registrado en conjunto_datos.'}, status=404)

    try:
        csv_path = md.archivo_csv.path
    except (NotImplementedError, ValueError):
        csv_path = ''
    if not csv_path or not os.path.isfile(csv_path):
        return JsonResponse({'error': 'Archivo no encontrado'}, status=404)

    enc = request.GET.get('encoding') or 'utf-8-sig'
    fallbacks = [enc]
    if enc.lower() != 'latin-1':
        fallbacks.append('latin-1')

    for encoding in fallbacks:
        try:
            with open(csv_path, 'r', encoding=encoding, newline='') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                return JsonResponse({'file': file_name, 'columns': fieldnames})
        except UnicodeDecodeError:
            continue
        except Exception as e:
           
            logger.error(f'Error reading CSV file {file_name} with encoding {encoding}: {str(e)}', exc_info=True)
            return JsonResponse({'error': 'Error al leer el archivo CSV', 'details': str(e)}, status=500)
    
    # Si llegamos aquí, todos los intentos de codificación fallaron
    return JsonResponse({
        'error': 'No se pudo leer el archivo con las codificaciones disponibles',
        'tried_encodings': fallbacks
    }, status=400)

def _cargar_diccionario_oe():
    """Lee el diccionario de datos desde el CSV Hoja 2 y devuelve una lista de {variable, descripcion}."""
    # Ruta relativa provista en docs
    csv_rel_path = 'docs/OOEE_ICED_completa_V3_Andrés_24072025.xlsx - Hoja 2.csv'
    base_dir = getattr(settings, 'BASE_DIR', '')
    csv_path = os.path.join(base_dir, csv_rel_path) if base_dir else csv_rel_path

    diccionario = []
    if not os.path.exists(csv_path):
        return diccionario

    # Intentar con codificaciones comunes
    for enc in ['utf-8-sig', 'utf-8', 'latin-1']:
        try:
            with open(csv_path, 'r', encoding=enc, newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Manejar variantes de encabezados
                    var = row.get('Variable') or row.get('variable') or ''
                    desc = row.get('Descripción') or row.get('Descripcion') or row.get('descripcion') or ''
                    var = (var or '').strip()
                    desc = (desc or '').strip()
                    if var or desc:
                        diccionario.append({'variable': var, 'descripcion': desc})
            break
        except UnicodeDecodeError:
            diccionario = []
            continue
        except Exception:
            # Cualquier otro error: retornar lo acumulado (o vacío)
            break

    return diccionario


def inventario_operaciones(request):
    """
    Visor: Inventario de Operaciones Estadísticas del Distrito de Santiago de Cali.
    - Listado con búsqueda y filtros jerárquicos por organismo/suborganismo.
    - Muestra diccionario de datos (Hoja 2 del CSV en docs).
    """

    q = (request.GET.get('q') or '').strip()
    organismo_filter = (request.GET.get('organismo') or '').strip()
    suborganismo_filter = (request.GET.get('suborganismo') or '').strip()
    
    qs = OperacionEstadistica.objects.filter(activo=True).order_by('organismo', 'suborganismo', 'nombre')

    # Aplicar filtros
    if q:
        qs = qs.filter(
            Q(nombre__icontains=q) |
            Q(organismo__icontains=q) |
            Q(suborganismo__icontains=q) |
            Q(area_tem__icontains=q) |
            Q(tema__icontains=q) |
            Q(sicode__icontains=q) |
            Q(codigo__icontains=q)
        )
    
    if organismo_filter:
        qs = qs.filter(organismo=organismo_filter)
    
    if suborganismo_filter:
        qs = qs.filter(suborganismo=suborganismo_filter)

    # Obtener jerarquía de organismos para los dropdowns
    organismos_data = {}
    all_ops = OperacionEstadistica.objects.filter(activo=True).values('organismo', 'suborganismo').distinct()
    
    for op in all_ops:
        organismo = op['organismo'] or 'Sin Organismo'
        suborganismo = op['suborganismo'] or 'Sin Suborganismo'
        
        if organismo not in organismos_data:
            organismos_data[organismo] = set()
        organismos_data[organismo].add(suborganismo)
    
    # Convertir sets a listas ordenadas
    for organismo in organismos_data:
        organismos_data[organismo] = sorted(list(organismos_data[organismo]))
    
    organismos_data = dict(sorted(organismos_data.items()))

    diccionario = _cargar_diccionario_oe()

    context = {
        'page': 'inventario_operaciones',
        'q': q,
        'organismo_filter': organismo_filter,
        'suborganismo_filter': suborganismo_filter,
        'operaciones': qs,
        'total': qs.count(),
        'organismos_data': organismos_data,
        'diccionario': diccionario,
        'titulo': 'Inventario de Operaciones Estadísticas del Distrito de Santiago de Cali',
    }
    return render(request, 'indicadores/inventario_operaciones.html', context)


def operacion_detalle(request, pk: int):
    """Detalle con campos clave de interés académico de una operación estadística."""
    operacion = get_object_or_404(OperacionEstadistica, pk=pk, activo=True)

    campos_clave = {
        'Código': operacion.codigo,
        'Nombre': operacion.nombre,
        'Descripción': operacion.descripcion,
        'Organismo': operacion.organismo,
        'Suborganismo': operacion.suborganismo,
        'Área temática': operacion.area_tem,
        'Tema': operacion.tema,
        'Unidad de observación': operacion.unidad_observ,
        'Objetivo': operacion.objetivo,
        'Principales resultados': operacion.principales_resultados,
        'Metodología': operacion.metodologia,
        'Periodicidad': operacion.periodicidad,
        'Fecha de inicio': operacion.fecha_inicio,
        'Fecha de fin': operacion.fecha_fin,
        'Entidad recopiladora': operacion.entidad_recopiladora,
        'Desagregación de resultados': operacion.desagregacion_resultados,
        'Enfoque diferencial': operacion.enfoque_diferencial,
        'SICODE': operacion.sicode,
        'Tipo OE': operacion.tipo_oe_i,
        'Documento metodológico': operacion.doc_met,
        'Ficha metodológica': operacion.ficha_met,
        'Manual operativo': operacion.manual_op,
        'Diccionario de datos': operacion.diccionario_datos,
        'URL pública': operacion.url,
        'Enlace ADDA': operacion.link_adda,
        'Inventario OE (histórico)': operacion.link_pe,
    }

    context = {
        'operacion': operacion,
        'campos_clave': campos_clave,
        'titulo': f"Operación Estadística: {operacion.nombre}",
    }
    return render(request, 'indicadores/operacion_detalle.html', context)


 


def get_dominios(request):
    """API para obtener todos los dominios activos"""
    dominios = MenuDominio.objects.filter(activo=True).order_by('orden')
    dominios_data = [{'id': d.id, 'nombre': d.nombre, 'icono': d.icono} for d in dominios]
    return JsonResponse(dominios_data, safe=False)


def get_temas(request):
    """API para obtener temas filtrados por dominios"""
    dominio_ids = request.GET.get('dominios', '').split(',')
    if dominio_ids and dominio_ids[0]:
        try:
            dominio_ids = [int(id) for id in dominio_ids if id.isdigit()]
            temas = MenuTema.objects.filter(dominio_id__in=dominio_ids, activo=True).order_by('orden')
            temas_data = [{'id': t.id, 'nombre': t.nombre, 'dominio_id': t.dominio.id, 'icono': t.icono} for t in temas]
            return JsonResponse(temas_data, safe=False)
        except ValueError:
            pass
    return JsonResponse([], safe=False)

def get_indicadores_simple(request):
    """API simple para listar indicadores activos sin requerir subtemas.
    Parámetros GET opcionales:
      - q: texto para filtrar por nombre (icontains)
      - limit: máximo de registros a devolver (por defecto 200, máximo 1000)
      - solo_geo: si es '1' o 'true', solo indicadores con datos geográficos
    Devuelve: lista de {id, nombre}
    """
    try:
        q = (request.GET.get('q') or '').strip()
        try:
            limit = int(request.GET.get('limit', 600))
        except (TypeError, ValueError):
            limit = 600
        # Limitar rangos razonables
        limit = max(1, min(limit, 1000))

        indicadores_qs = Indicador.objects.filter(activo=True)
        # Filtrar solo indicadores con datos geográficos si se solicita
        solo_geo_param = (request.GET.get('solo_geo') or '').strip().lower()
        if solo_geo_param in ('1', 'true', 'yes', 'si'):
            indicadores_qs = indicadores_qs.filter(
                datos__desagregaciones_geograficas__capa_geo__isnull=False
            ).distinct()
        if q:
            indicadores_qs = indicadores_qs.filter(nombre__icontains=q)

        # Si se solicita un indicador específico, incluir metadatos completos de ficha técnica
        indicador_id = request.GET.get('indicador_id')
        if indicador_id:
            try:
                indicador = indicadores_qs.get(id=int(indicador_id))
                data = [{
                    'id': indicador.id,
                    'nombre': indicador.nombre,
                    'codigo_indicador': indicador.codigo_indicador,
                    'sigla': indicador.sigla,
                    'grupo_indicador': indicador.grupo_indicador,
                    # Contacto (MSD)
                    'organismo_responsable': indicador.organismo_responsable.nombre if indicador.organismo_responsable else None,
                    'entidad_responsable': indicador.entidad_responsable,
                    'operacion': indicador.operacion.nombre if indicador.operacion else None,
                    'suborganismo': indicador.suborganismo.nombre if indicador.suborganismo else None,
                    'correo_contacto': indicador.correo_contacto,
                    'telefono_contacto': indicador.telefono_contacto,
                    'fecha_publicacion_metadatos': indicador.fecha_publicacion_metadatos.strftime('%Y-%m-%d') if indicador.fecha_publicacion_metadatos else None,
                    # Descripción y características (MSD)
                    'descripcion_indicador': indicador.descripcion_indicador,
                    'objetivo': indicador.objetivo,
                    'justificacion': None,  # Campo legacy eliminado
                    'metodo_medicion': indicador.metodo_medicion,
                    'formula_ficha': indicador.formula_ficha,
                    'variables': indicador.variables,
                    'unidad_medida': indicador.unidad_medida,
                    'valores_referencia': None,  # Campo legacy eliminado
                    'nomenclaturas_clasificaciones': indicador.nomenclaturas_clasificaciones,
                    'alcance_tematico': indicador.alcance_tematico,
                    'poblacion_objetivo': indicador.poblacion_objetivo,
                    'cobertura_geografica': indicador.cobertura_geografica,
                    'periodo_referencia': indicador.periodo_referencia,
                    'periodo_base': indicador.periodo_base,
                    'linea_base': None,  # Campo legacy eliminado
                    'periodicidad': indicador.frecuencia_difusion,
                    'fuente_datos': indicador.fuente_datos,
                    'responsable': indicador.entidad_responsable,
                    # Difusión (MSD)
                    'serie_historica_disponible': indicador.serie_historica_disponible,
                    'frecuencia_difusion': indicador.frecuencia_difusion,
                    'medios_difusion': indicador.medios_difusion,
                    # Comentarios (MSD)
                    'comentarios_adicionales': indicador.comentarios_adicionales,
                    'notas': indicador.notas,
                    'fecha_elaboracion': indicador.fecha_elaboracion.strftime('%Y-%m-%d') if indicador.fecha_elaboracion else None,
                    'fecha_actualizacion': indicador.fecha_actualizacion_ficha.strftime('%Y-%m-%d') if indicador.fecha_actualizacion_ficha else None,
                    'nombre_conjunto_datos': indicador.nombre_conjunto_datos,
                    # SDMX: referencias y responsabilidad institucional
                    # NOTA: datos personales del responsable técnico (nombre/cargo/correo/celular)
                    # NO se exponen en el API pública — solo en formularios internos y admin.
                    'referencias': indicador.referencias,
                    'equipo_responsable': indicador.equipo_responsable.nombre if indicador.equipo_responsable else None,
                }]
                return JsonResponse(data, safe=False)
            except (ValueError, Indicador.DoesNotExist):
                return JsonResponse([], safe=False)
        
        # Lista normal de indicadores (solo id y nombre)
        indicadores = indicadores_qs.order_by('nombre')[:limit]
        data = [{'id': i.id, 'nombre': i.nombre} for i in indicadores]
        return JsonResponse(data, safe=False)
    except Exception:
        return JsonResponse([], safe=False)


def get_niveles_geograficos(request):
    """API para obtener todos los niveles geográficos.
    Devuelve: lista de {id, nombre}
    """
    try:
        niveles = NivelGeografico.objects.all().order_by('nombre')
        data = [{'id': n.id, 'nombre': n.nombre} for n in niveles]
        return JsonResponse(data, safe=False)
    except Exception:
        return JsonResponse([], safe=False)


def get_capas_geograficas(request):
    """API para obtener capas geográficas filtradas opcionalmente por niveles geográficos.
    Parámetros GET opcionales:
    - niveles: lista de IDs de nivel separados por coma
    Devuelve: lista de {id, nombre, nivel_geografico_id}
    """
    niveles_param = request.GET.get('niveles', '').split(',')
    capas_qs = CapaGeo.objects.all()
    if niveles_param and niveles_param[0]:
        try:
            nivel_ids = [int(i) for i in niveles_param if i.isdigit()]
            if nivel_ids:
                capas_qs = capas_qs.filter(nivel_geografico_id__in=nivel_ids)
        except ValueError:
            pass

    capas = capas_qs.order_by('nombre')
    data = [{'id': c.id, 'nombre': c.nombre, 'nivel_geografico_id': c.nivel_geografico_id} for c in capas]
    return JsonResponse(data, safe=False)


def get_subtemas(request):
    """API para obtener subtemas filtrados por temas"""
    tema_ids = request.GET.get('temas', '').split(',')
    if tema_ids and tema_ids[0]:
        try:
            tema_ids = [int(id) for id in tema_ids if id.isdigit()]
            subtemas = MenuSubtema.objects.filter(tema_id__in=tema_ids, activo=True).order_by('orden')
            subtemas_data = [{'id': s.id, 'nombre': s.nombre, 'tema_id': s.tema.id, 'icono': s.icono} for s in subtemas]
            return JsonResponse(subtemas_data, safe=False)
        except ValueError:
            pass
    return JsonResponse([], safe=False)


def get_dominios_desagregacion(request):
    """API para obtener dominios de desagregación asociados a indicadores de los subtemas seleccionados.
    Acepta el parámetro GET 'subtemas' como lista separada por comas.
    Devuelve dominios únicos de ambos tipos (temática y geográfica).
    """
    subtema_ids = request.GET.get('subtemas', '').split(',')
    if subtema_ids and subtema_ids[0]:
        try:
            subtema_ids = [int(i) for i in subtema_ids if i.isdigit()]

            # Indicadores activos bajo los subtemas
            indicadores_qs = Indicador.objects.filter(subtema_id__in=subtema_ids, activo=True)

            # Dominios asociados por cualquiera de las dos relaciones M2M
            dominios = (DominioDesagregacion.objects
                        .filter(
                            Q(indicadores_con_dominios_tematicos__in=indicadores_qs) |
                            Q(indicadores_con_dominios_geograficos__in=indicadores_qs)
                        )
                        .distinct()
                        .order_by('nombre'))

            dominios_data = [{'id': d.id, 'nombre': d.nombre, 'tipo': d.tipo} for d in dominios]
            return JsonResponse(dominios_data, safe=False)
        except ValueError:
            pass
    return JsonResponse([], safe=False)


def get_indicadores(request):
    """API para obtener indicadores filtrados por subtemas y opcionalmente por dominios y geografía.
    Parámetros GET:
    - subtemas: lista de IDs de subtema separados por coma (obligatorio)
    - dominios_desagregacion: lista de IDs de dominio de desagregación separados por coma (opcional)
    - niveles: lista de IDs de NivelGeografico separados por coma (opcional)
    - capas: lista de IDs de CapaGeo separados por coma (opcional)
    """
    subtema_ids = request.GET.get('subtemas', '').split(',')
    dominios_ids = request.GET.get('dominios_desagregacion', '').split(',')
    niveles_ids = request.GET.get('niveles', '').split(',')
    capas_ids = request.GET.get('capas', '').split(',')
    if subtema_ids and subtema_ids[0]:
        try:
            subtema_ids = [int(i) for i in subtema_ids if i.isdigit()]
            dominios_ids = [int(i) for i in dominios_ids if i.isdigit()]
            niveles_ids = [int(i) for i in niveles_ids if i.isdigit()]
            capas_ids = [int(i) for i in capas_ids if i.isdigit()]

            
            # Construir consulta OR para dominios de desagregación
            dominio_queries = Q()
            if dominios_ids:
                for d_id in dominios_ids:
                    dominio_queries |= Q(dominios_desagregacion_tematica__id=d_id) | Q(dominios_desagregacion_geografica__id=d_id)
            
            # Aplicar filtros en una sola consulta
            queryset = Indicador.objects.filter(
                subtema_id__in=subtema_ids,
                activo=True
            )
            
            # Aplicar filtro de dominios si existen
            if dominios_ids:
                queryset = queryset.filter(dominio_queries)
            
            # Filtro por niveles geográficos
            if niveles_ids:
                queryset = queryset.filter(
                    dominios_desagregacion_geografica__nivel_geografico_id__in=niveles_ids
                ).distinct()

            # Filtro por capas geográficas
            if capas_ids:
                queryset = queryset.filter(
                    datos__desagregaciones_geograficas__capa_geo_id__in=capas_ids
                ).distinct()
            
            # Obtener resultados únicos y ordenados
            indicadores = queryset.distinct().order_by('nombre')

            indicadores = indicadores.order_by('nombre')
            indicadores_data = [{'id': i.id, 'nombre': i.nombre, 'subtema_id': i.subtema.id} for i in indicadores]
            return JsonResponse(indicadores_data, safe=False)
        except ValueError:
            pass
    return JsonResponse([], safe=False)


def get_datos_indicadores(request):
    """API para obtener datos de indicadores seleccionados para el visor comparativo"""
    indicador_ids = request.GET.get('indicadores', '').split(',')
    # Obtener parámetros de paginación de forma segura
    try:
        limit = int(request.GET.get('limit', '1000'))
    except (TypeError, ValueError):
        limit = 1000
    # Clampear límite para evitar respuestas gigantes
    limit = max(1, min(limit, 10000))

    try:
        offset = int(request.GET.get('offset', '0'))
    except (TypeError, ValueError):
        offset = 0
    # No permitir offset negativo
    offset = max(0, offset)

    # Filtros opcionales por año (inclusive). Si se proveen ambos, usar rango; si uno, usar borde abierto.
    ano_min_param = request.GET.get('anio_min')
    ano_max_param = request.GET.get('anio_max')
    ano_min = None
    ano_max = None
    try:
        if ano_min_param is not None and ano_min_param != '':
            ano_min = int(ano_min_param)
    except (TypeError, ValueError):
        ano_min = None
    try:
        if ano_max_param is not None and ano_max_param != '':
            ano_max = int(ano_max_param)
    except (TypeError, ValueError):
        ano_max = None
    
    if indicador_ids and indicador_ids[0]:
        try:
            indicador_ids = [int(id) for id in indicador_ids if id.isdigit()]
            
            # Obtener indicadores para incluir metadatos
            indicadores = Indicador.objects.filter(id__in=indicador_ids).order_by('id')
            
            # Obtener datos de los indicadores seleccionados con filtros opcionales por año
            datos = (
                Dato.objects
                .filter(indicador_id__in=indicador_ids)
                .select_related('indicador')
                .only('id', 'valor_dato', 'fecha_dato', 'indicador_id', 'indicador__nombre')
                .prefetch_related(
                    Prefetch('desagregaciones_geograficas', queryset=Desagregacion.objects.only('id', 'nombre')),
                    Prefetch('desagregaciones_tematicas', queryset=Desagregacion.objects.only('id', 'nombre')),
                )
                .order_by('indicador_id', 'fecha_dato', 'id')  # orden estable para paginación consistente
            )

            # Aplicar filtros por año si corresponden (usar límites de fecha para mejor desempeño)
            if ano_min is not None or ano_max is not None:
                # Construir rango de fechas
                start_date = None
                end_date = None
                if ano_min is not None:
                    try:
                        start_date = datetime.date(ano_min, 1, 1)
                    except Exception:
                        start_date = None
                if ano_max is not None:
                    try:
                        end_date = datetime.date(ano_max, 12, 31)
                    except Exception:
                        end_date = None
                if start_date and end_date:
                    datos = datos.filter(fecha_dato__range=(start_date, end_date))
                elif start_date:
                    datos = datos.filter(fecha_dato__gte=start_date)
                elif end_date:
                    datos = datos.filter(fecha_dato__lte=end_date)
            
            # Aplicar límite y offset
            total_datos = datos.count()
            datos = datos[offset:offset + limit]
            
            # Preparar datos para WebDataRocks
            datos_comparativos = []
            for dato in datos:
                # Obtener desagregaciones
                # Usar relaciones prefeteadas para evitar N+1 (iterar objetos en memoria)
                desagregaciones_geo = [d.nombre for d in dato.desagregaciones_geograficas.all()]
                desagregaciones_tem = [d.nombre for d in dato.desagregaciones_tematicas.all()]
                
                # Crear registro para WebDataRocks
                registro = {
                    'Año': dato.fecha_dato.year,
                    'Indicador': dato.indicador.nombre,
                    'Valor': float(dato.valor_dato),
                    'Desagregaciones Geográficas': ', '.join(desagregaciones_geo),
                    'Desagregaciones Temáticas': ', '.join(desagregaciones_tem)
                }
                datos_comparativos.append(registro)
            
            # Preparar metadatos de indicadores (evitar cargar columnas innecesarias)
            indicadores_data = list(
                indicadores.values('id', 'nombre', 'unidad_medida')
            )
            
            # Devolver datos junto con información de paginación
            response_data = {
                'datos': datos_comparativos,
                'indicadores': indicadores_data,
                'total': total_datos,
                'limit': limit,
                'offset': offset
            }
            
            return JsonResponse(response_data, safe=False)
        except ValueError:
            pass
    return JsonResponse({'datos': [], 'total': 0, 'limit': limit, 'offset': offset}, safe=False)


def proceso_en_vivo(request, proceso_id: int):
    """Vista que muestra el template con logs en tiempo real del proceso."""
    proceso = get_object_or_404(ProcesoExtraccion, id=proceso_id)
    return render(request, 'admin/proceso_en_vivo.html', {
        'proceso': proceso,
    })


def api_proceso_status(request, proceso_id: int):
    """Devuelve estado actual del proceso y el último ID de log disponible.
    Tolera bloqueos de SQLite devolviendo locked=True para que el frontend reintente.
    """
    try:
        proceso = get_object_or_404(ProcesoExtraccion, id=proceso_id)
        last_log = proceso.logs.order_by('-id').first()
        data = {
            'id': proceso.id,
            'indicador_id': proceso.indicador_id,
            'estado': proceso.estado,
            'exit_code': proceso.exit_code,
            'error_message': proceso.error_message,
            'created_at': proceso.created_at.isoformat() if proceso.created_at else None,
            'started_at': proceso.started_at.isoformat() if proceso.started_at else None,
            'finished_at': proceso.finished_at.isoformat() if proceso.finished_at else None,
            'last_log_id': last_log.id if last_log else 0,
            'locked': False,
        }
        return JsonResponse(data)
    except OperationalError:
        # SQLite bloqueo temporal: notificar para reintento sin cortar UI
        return JsonResponse({'locked': True}, status=200)


def api_proceso_logs(request, proceso_id: int):
    """Devuelve logs incrementales a partir de last_id (exclusivo).
    Si hay bloqueo de DB, devolver locked=True y una lista vacía para que el cliente reintente.
    """
    try:
        proceso = get_object_or_404(ProcesoExtraccion, id=proceso_id)
        try:
            last_id = int(request.GET.get('last_id', '0'))
        except ValueError:
            last_id = 0

        # Limitar cantidad por respuesta para evitar respuestas enormes
        limite = int(request.GET.get('limit', '500'))
        limite = max(1, min(limite, 1000))

        logs_qs = proceso.logs.filter(id__gt=last_id).order_by('id')[:limite]
        logs = [{'id': l.id, 'nivel': l.nivel, 'mensaje': l.mensaje, 'creado_en': l.creado_en.isoformat()} for l in logs_qs]
        return JsonResponse({'logs': logs, 'locked': False})
    except OperationalError:
        return JsonResponse({'logs': [], 'locked': True}, status=200)


@login_required
def workspace_dashboard(request):
    """Dashboard unificado /workspace/ — landing page según rol del usuario."""
    user = request.user
    perfil = getattr(user, 'perfil_recolector', None)
    rol = perfil.rol if perfil else None
    activo = perfil.activo if perfil else False

    # Determinar acceso a módulos
    es_staff = user.is_staff
    if es_staff:
        # Admin ve todo
        puede_recoleccion = True
        puede_reportes = True
        es_delegado = True
        es_validador = True
        puede_editorial = True
    else:
        puede_recoleccion = rol in ('recolector', 'ambos')
        puede_reportes = rol in ('consultor', 'ambos')
        es_delegado = rol == 'delegado' and activo
        es_validador = rol == 'validador' and activo
        puede_editorial = rol == 'editor' and activo

    # Stats para cards (solo si tiene acceso, para no hacer queries innecesarias)
    stats = {}
    if puede_recoleccion:
        from .models import CargaSerieIndicador, CargaConjuntoDatos
        stats['mis_series'] = CargaSerieIndicador.objects.filter(usuario=user).count()
        stats['mis_conjunto_datos'] = CargaConjuntoDatos.objects.filter(usuario=user).count()
        stats['series_pendientes'] = CargaSerieIndicador.objects.filter(
            usuario=user, estado__in=['pendiente', 'procesando', 'enviado', 'en_revision', 'correcciones_solicitadas']
        ).count()
        stats['conjunto_datos_pendientes'] = CargaConjuntoDatos.objects.filter(
            usuario=user, estado__in=['pendiente', 'procesando', 'enviado', 'en_revision', 'correcciones_solicitadas']
        ).count()

    if puede_reportes:
        from .models import Indicador, Dato
        stats['total_indicadores'] = Indicador.objects.filter(activo=True).count()
        stats['total_datos'] = Dato.objects.count()

    if es_delegado:
        from .models import CargaSerieIndicador, CargaConjuntoDatos
        organismo = perfil.organismo if perfil else None
        stats['delegado_series'] = CargaSerieIndicador.objects.filter(
            usuario=user, es_carga_delegado=True
        ).count() if organismo else 0
        stats['delegado_conjunto_datos'] = CargaConjuntoDatos.objects.filter(
            usuario=user, es_carga_delegado=True
        ).count() if organismo else 0

    if es_validador:
        from .models import CargaSerieIndicador, CargaConjuntoDatos
        stats['validar_series'] = CargaSerieIndicador.objects.filter(
            estado__in=['enviado', 'en_revision', 'correcciones_solicitadas']
        ).count()
        stats['validar_conjunto_datos'] = CargaConjuntoDatos.objects.filter(
            estado__in=['enviado', 'en_revision', 'correcciones_solicitadas']
        ).count()

    if es_staff:
        from .models import CargaSerieIndicador, CargaConjuntoDatos, ProcesoExtraccion
        stats['admin_series_pendientes'] = CargaSerieIndicador.objects.filter(
            estado__in=['pendiente', 'aprobado']
        ).count()
        stats['admin_conjunto_datos_pendientes'] = CargaConjuntoDatos.objects.filter(
            estado__in=['pendiente', 'aprobado']
        ).count()
        stats['procesos_activos'] = ProcesoExtraccion.objects.filter(
            estado__in=['pendiente', 'procesando']
        ).count()

    if puede_editorial:
        from .models import ProductoAcademico, Evento, NoticiaBanner
        stats['productos_count'] = ProductoAcademico.objects.count()
        stats['eventos_count'] = Evento.objects.count()
        stats['noticias_count'] = NoticiaBanner.objects.filter(activa=True).count()

    context = {
        'perfil': perfil,
        'rol': rol,
        'es_staff': es_staff,
        'puede_recoleccion': puede_recoleccion,
        'puede_reportes': puede_reportes,
        'es_delegado': es_delegado,
        'es_validador': es_validador,
        'puede_editorial': puede_editorial,
        'stats': stats,
    }
    return render(request, 'workspace/dashboard.html', context)


@staff_member_required
def admin_procesos_dashboard(request):
    """Dashboard de procesos en ejecución para administradores."""
    from django.utils import timezone
    from datetime import timedelta

    # Procesos de extracción activos
    procesos_extraccion = ProcesoExtraccion.objects.filter(
        estado__in=['pendiente', 'procesando']
    ).select_related('indicador', 'regla').order_by('-created_at')[:50]

    # Cargas de series en procesamiento
    cargas_series = CargaSerieIndicador.objects.filter(
        estado='procesando'
    ).select_related('usuario', 'indicador').order_by('-fecha_carga')[:50]

    # Cargas de conjunto_datos en procesamiento
    cargas_conjuntos_datos = CargaConjuntoDatos.objects.filter(
        estado='procesando'
    ).select_related('usuario', 'conjunto_datos').order_by('-fecha_carga')[:50]

    # Estadísticas rápidas
    stats = {
        'extraccion_activos': ProcesoExtraccion.objects.filter(estado='procesando').count(),
        'extraccion_pendientes': ProcesoExtraccion.objects.filter(estado='pendiente').count(),
        'series_procesando': CargaSerieIndicador.objects.filter(estado='procesando').count(),
        'conjunto_datos_procesando': CargaConjuntoDatos.objects.filter(estado='procesando').count(),
        'total_hoy': ProcesoExtraccion.objects.filter(
            created_at__date=timezone.now().date()
        ).count(),
    }

    context = {
        'procesos_extraccion': procesos_extraccion,
        'cargas_series': cargas_series,
        'cargas_conjuntos_datos': cargas_conjuntos_datos,
        'stats': stats,
    }
    return render(request, 'admin/procesos_dashboard.html', context)


def api_documentation(request):
    """Vista para la documentación de la API abierta del Sistema Integrado de Información Estadística Distrital."""

    # Definir los endpoints disponibles organizados por categorías
    api_endpoints = {
        'conjuntos_datos': [
            {
                'endpoint': '/api/conjuntos-datos/list/',
                'method': 'GET',
                'description': 'Lista de conjuntos_datos disponibles',
                'parameters': [],
                'example': '/api/conjuntos-datos/list/'
            },
            {
                'endpoint': '/api/conjuntos-datos/rows/',
                'method': 'GET',
                'description': 'Filas de datos de conjuntos_datos con paginación y filtros',
                'parameters': [
                    {'name': 'file', 'type': 'string', 'required': True, 'description': 'Nombre del archivo CSV registrado en conjunto_datos'},
                    {'name': 'limit', 'type': 'int', 'required': False, 'description': 'Límite de filas (por defecto 10000, máx. 10000)'},
                    {'name': 'offset', 'type': 'int', 'required': False, 'description': 'Desplazamiento de filas (por defecto 0)'},
                    {'name': 'encoding', 'type': 'string', 'required': False, 'description': 'Codificación del archivo (por defecto utf-8-sig)'},
                    {'name': 'columns', 'type': 'string', 'required': False, 'description': 'Columnas a incluir separadas por comas'},
                    {'name': 'anio_inicio', 'type': 'int', 'required': False, 'description': 'Año de inicio para filtrar datos'},
                    {'name': 'anio_fin', 'type': 'int', 'required': False, 'description': 'Año de fin para filtrar datos'}
                ],
                'example': '/api/conjuntos-datos/rows/?file=Poblacion_Santiago_de_Cali_1985_-_2042_7aDvi5e.csv&limit=100&offset=0'
            },
            {
                'endpoint': '/api/conjuntos-datos/headers/',
                'method': 'GET',
                'description': 'Encabezados de columnas del microdato',
                'parameters': [
                    {'name': 'file', 'type': 'string', 'required': True, 'description': 'Nombre del archivo CSV registrado en conjunto_datos'},
                    {'name': 'encoding', 'type': 'string', 'required': False, 'description': 'Codificación del archivo (por defecto utf-8-sig)'}
                ],
                'example': '/api/conjuntos-datos/headers/?file=Poblacion_Santiago_de_Cali_1985_-_2042_7aDvi5e.csv'
            }
        ],
        'dominios_y_navegacion': [
            {
                'endpoint': '/api/get_dominios/',
                'method': 'GET',
                'description': 'Lista de dominios disponibles',
                'parameters': [],
                'example': '/api/get_dominios/'
            },
            {
                'endpoint': '/api/get_temas/',
                'method': 'GET',
                'description': 'Temas de uno o más dominios',
                'parameters': [
                    {'name': 'dominios', 'type': 'string', 'required': True, 'description': 'IDs de dominios separados por comas'}
                ],
                'example': '/api/get_temas/?dominios=1,2,3'
            },
            {
                'endpoint': '/api/get_subtemas/',
                'method': 'GET',
                'description': 'Subtemas de uno o más temas',
                'parameters': [
                    {'name': 'temas', 'type': 'string', 'required': True, 'description': 'IDs de temas separados por comas'}
                ],
                'example': '/api/get_subtemas/?temas=1,2,3'
            }
        ],
        'indicadores': [
            {
                'endpoint': '/api/get_indicadores_simple/',
                'method': 'GET',
                'description': 'Lista simplificada de indicadores',
                'parameters': [
                    {'name': 'subtema_id', 'type': 'int', 'required': False, 'description': 'Filtrar por subtema'}
                ],
                'example': '/api/get_indicadores_simple/?subtema_id=1'
            }
        ],
        'desagregaciones': [
            {
                'endpoint': '/api/get_dominios_desagregacion/',
                'method': 'GET',
                'description': 'Dominios de desagregación disponibles para indicadores de los subtemas especificados',
                'parameters': [
                    {'name': 'subtemas', 'type': 'string', 'required': True, 'description': 'IDs de subtemas separados por comas'}
                ],
                'example': '/api/get_dominios_desagregacion/?subtemas=1,2,3'
            },
            {
                'endpoint': '/api/get_desagregaciones/<int:indicador_id>/',
                'method': 'GET',
                'description': 'Obtiene las desagregaciones disponibles para un indicador, incluyendo información de rangos de años',
                'parameters': [],
                'example': '/api/get_desagregaciones/3/',
                'response_example': '''{
  "desagregaciones_geograficas": [
    {"id": 1, "nombre": "Cali", "predeterminada": true},
    {"id": 2, "nombre": "Comunas", "predeterminada": false}
  ],
  "desagregaciones_tematicas": [
    {"id": 3, "nombre": "Género", "predeterminada": true},
    {"id": 4, "nombre": "Grupo etario", "predeterminada": false}
  ],
  "rango_anios": {
    "min": 2015,
    "max": 2023,
    "min_disponible": 2010,
    "max_disponible": 2025
  }
}'''
            }
        ],
        'geografia': [
            {
                'endpoint': '/api/get_niveles_geograficos/',
                'method': 'GET',
                'description': 'Niveles geográficos disponibles',
                'parameters': [],
                'example': '/api/get_niveles_geograficos/'
            },
            {
                'endpoint': '/api/get_capas_geograficas/',
                'method': 'GET',
                'description': 'Capas geográficas disponibles',
                'parameters': [],
                'example': '/api/get_capas_geograficas/'
            },
            {
                'endpoint': '/api/geojson/indicador/<int:indicador_id>/',
                'method': 'GET',
                'description': 'Obtiene las geometrías GeoJSON asociadas a las desagregaciones geográficas de un indicador. Incluye información de las capas geográficas disponibles y sus elementos (comunas, barrios, etc.)',
                'parameters': [],
                'example': '/api/geojson/indicador/3/',
                'response_example': '''{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "codigo": "1",
        "nombre": "Comuna 1",
        "capa_id": 1
      },
      "geometry": {
        "type": "MultiPolygon",
        "coordinates": [
          [
            [
              [-76.54, 3.45],
              [-76.53, 3.46],
              [-76.52, 3.45],
              [-76.54, 3.45]
            ]
          ]
        ]
      }
    }
  ],
  "meta": {
    "capas": [1, 2],
    "count": 22,
    "indicador_id": 1,
    "reprojected_features": 0
  }
}'''
            }
        ],
        'visualizacion': [
            {
                'endpoint': '/api/get_graficos/<int:indicador_id>/',
                'method': 'GET',
                'description': 'Obtiene la configuración de gráficos para un indicador específico, incluyendo series de datos, estilos y diseño visual. Soporta múltiples tipos de gráficos como barras, líneas, áreas y pirámides poblacionales.',
                'parameters': [
                    {'name': 'ano_inicio', 'type': 'int', 'required': False, 'description': 'Año inicial para filtrar los datos'},
                    {'name': 'ano_fin', 'type': 'int', 'required': False, 'description': 'Año final para filtrar los datos'},
                    {'name': 'desagregaciones_geograficas', 'type': 'list', 'required': False, 'description': 'Lista de IDs de desagregaciones geográficas para filtrar los datos'},
                    {'name': 'desagregaciones_tematicas', 'type': 'list', 'required': False, 'description': 'Lista de IDs de desagregaciones temáticas para filtrar los datos'}
                ],
                'example': '/api/get_graficos/3/?ano_inicio=2020&ano_fin=2023&desagregaciones_geograficas[]=1&desagregaciones_tematicas[]=5',
                'response_example': '''{
  "id": 1,
  "nombre": "Gráfico de ejemplo",
  "tipo_grafico": "bar",
  "series": [
    {
      "x": ["2020", "2021", "2022", "2023"],
      "y": [100, 120, 90, 150],
      "name": "Serie 1",
      "type": "bar",
      "marker": {"color": "#4285F4"}
    },
    {
      "x": ["2020", "2021", "2022", "2023"],
      "y": [80, 95, 110, 130],
      "name": "Serie 2",
      "type": "bar",
      "marker": {"color": "#EA4335"}
    }
  ],
  "altura_grafico": 400,
  "begin_at_zero": true,
  "layout": {
    "title": "Título del Gráfico",
    "xaxis": {"title": "Año"},
    "yaxis": {"title": "Valor"},
    "showlegend": true
  }
}'''
            },
            
            {
                'endpoint': '/api/test_valores_geo/<int:indicador_id>/',
                'method': 'GET',
                'description': 'Endpoint ligero que devuelve valores numéricos agregados por desagregación geográfica para un indicador y año específico. Diseñado para ser más eficiente que el endpoint de mapas completo cuando solo se necesitan los valores numéricos sin la configuración de visualización. Excluye automáticamente cualquier desagregación geográfica llamada "Total".',
                'parameters': [
                    {'name': 'anio', 'type': 'int', 'required': False, 'description': 'Año específico a consultar. Si no se especifica, se usa el año más reciente con datos disponibles.'},
                    {'name': 'desagregaciones_tematicas[]', 'type': 'list', 'required': False, 'description': 'IDs de desagregaciones temáticas para filtrar los datos (pueden ser múltiples).'}
                ],
                'example': '/api/test_valores_geo/3/?anio=2023&desagregaciones_tematicas[]=5&desagregaciones_tematicas[]=6',
                'response_example': '''{
  "indicador_id": 3,
  "anio": 2023,
  "capas": [1, 2, 3],
  "valores": [
    {
      "codigo": "01",
      "capa_id": 1,
      "valor": 45.2,
      "nombre_capa": "Comuna 1",
      "nombre_elemento": "Comuna 1"
    },
    {
      "codigo": "02",
      "capa_id": 1,
      "valor": 78.9,
      "nombre_capa": "Comuna 2",
      "nombre_elemento": "Comuna 2"
    },
    {
      "codigo": "B01",
      "capa_id": 2,
      "valor": 120.5,
      "nombre_capa": "Barrio 1",
      "nombre_elemento": "Barrio 1"
    }
  ],
  "meta": {
    "tematicas": [5, 6],
    "serie_mapa": 1
  }
}''',
                'notas_importantes': [
                    'Este endpoint excluye automáticamente cualquier desagregación geográfica con nombre o código "Total" (case insensitive).',
                    'Para indicadores con pirámide poblacional, se aplica una lógica especial de agregación de datos.',
                    'El parámetro desagregaciones_tematicas[] puede usarse con múltiples valores para filtrar por intersección de desagregaciones.'
                ]
            }
        ],
        'datos': [
            {
                'endpoint': '/api/get_datos_indicadores/',
                'method': 'GET',
                'description': 'Datos de indicadores con paginación y filtros',
                'parameters': [
                    {'name': 'indicadores', 'type': 'string', 'required': True, 'description': 'IDs de indicadores separados por comas (ej: "1,2,3")'},
                    {'name': 'limit', 'type': 'int', 'required': False, 'description': 'Límite de registros (1-10000, default: 1000)'},
                    {'name': 'offset', 'type': 'int', 'required': False, 'description': 'Desplazamiento de registros (default: 0)'},
                    {'name': 'anio', 'type': 'int', 'required': False, 'description': 'Filtrar por año específico'}
                ],
                'example': '/api/get_datos_indicadores/?indicadores=1,2,3&limit=100&anio=2023',
                'response_example': '''{
  "datos": [
    {
      "indicador_id": 1,
      "nombre": "Tasa de desempleo",
      "valor": 12.5,
      "anio": 2023,
      "desagregaciones_tematicas": [5, 7],
      "desagregaciones_geograficas": [10, 12]
    },
    {
      "indicador_id": 2,
      "nombre": "Población en edad de trabajar",
      "valor": 1500000,
      "anio": 2023,
      "desagregaciones_tematicas": [3],
      "desagregaciones_geograficas": [10, 11, 12]
    }
  ],
  "total": 2,
  "limit": 100,
  "offset": 0
}'''
            },

        ],
       
    }

    # Estadísticas de la API
    api_stats = {
        'total_endpoints': sum(len(endpoints) for endpoints in api_endpoints.values()),
        'categories': len(api_endpoints),
        'last_updated': '2025-01-01',  # Fecha de ejemplo
        'version': '1.0.0'
    }

    # URL base = mismo origen del request (esquema + host + FORCE_SCRIPT_NAME).
    # Hardcodear producción hacía que en local los botones "probar" llamaran
    # a indicadores.cali.gov.co y CORS los bloqueara.
    base_url = request.build_absolute_uri('/').rstrip('/')
    
    context = {
        'page': 'api_documentation',
        'api_endpoints': api_endpoints,
        'api_stats': api_stats,
        'base_url': base_url  # URL base dinámica que respeta FORCE_SCRIPT_NAME
    }

    return render(request, 'indicadores/api_documentation.html', context)


def conjunto_datos_detalle(request, indicador_id):
    """Vista de detalle de conjunto_datos para un indicador específico"""
    indicador = get_object_or_404(Indicador, id=indicador_id)
    
    # Obtener conjunto_datos asociado al indicador
    conjunto_datos = None
    if hasattr(indicador, 'conjunto_datos') and indicador.conjunto_datos:
        conjunto_datos = indicador.conjunto_datos
    
    context = {
        'indicador': indicador,
        'conjunto_datos': conjunto_datos,
        'page_context': 'conjunto_datos_detalle',
        'standalone': False
    }
    
    return render(request, 'indicadores/conjunto_datos_detalle.html', context)


def conjuntos_datos_explorer(request):
    """Vista standalone del explorador de conjunto_datos"""
    # Obtener estructura jerárquica de dominios con conjunto_datos disponible
    dominios = MenuDominio.objects.filter(
        activo=True,
        temas__subtemas__indicadores__conjunto_datos__isnull=False
    ).distinct().prefetch_related(
        'temas__subtemas__indicadores__conjunto_datos'
    ).order_by('orden', 'nombre')
    
    context = {
        'dominios': dominios,
        'page_context': 'conjuntos_datos_explorer',
        'standalone': True
    }
    
    return render(request, 'indicadores/conjuntos_datos_explorer.html', context)


def api_conjunto_datos_all(request):
    """API para obtener TODOS los datasets en formato plano para búsqueda"""
    try:
        # Obtener todos los conjunto_datos con sus indicadores relacionados
        conjunto_datos_list = ConjuntoDatos.objects.prefetch_related(
            'indicadores__subtema__tema__dominio'
        ).all().order_by('nombre')
        
        datasets = []
        for conjunto_datos in conjunto_datos_list:
            # Obtener el primer indicador activo relacionado (si existe)
            indicador = conjunto_datos.indicadores.filter(
                activo=True,
                subtema__activo=True,
                subtema__tema__dominio__activo=True
            ).select_related('subtema__tema__dominio').first()
            
            if indicador:
                datasets.append({
                    'id': conjunto_datos.id,
                    'nombre': conjunto_datos.nombre,
                    'descripcion': conjunto_datos.descripcion or '',
                    'codigo': '',  # conjunto_datos no tiene código
                    'archivo': conjunto_datos.archivo_csv.name if conjunto_datos.archivo_csv else None,
                    'indicador_id': indicador.id,
                    'indicador_nombre': indicador.nombre,
                    'subtema_id': indicador.subtema.id,
                    'subtema_nombre': indicador.subtema.nombre,
                    'tema_nombre': indicador.subtema.tema.nombre,
                    'dominio_nombre': indicador.subtema.tema.dominio.nombre,
                    'fecha_actualizacion': conjunto_datos.fecha_carga.strftime('%Y-%m-%d') if conjunto_datos.fecha_carga else None,
                    'tamaño_archivo': None,  # No está en el modelo
                    'num_filas': None,  # No está en el modelo
                    'num_columnas': None  # No está en el modelo
                })
        
        return JsonResponse(datasets, safe=False)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def api_conjunto_datos_datasets(request):
    """API para obtener datasets de conjunto_datos organizados jerárquicamente"""
    try:
        # Obtener todos los conjunto_datos con sus relaciones
        conjunto_datos_list = ConjuntoDatos.objects.select_related(
            'indicador__subtema__tema__dominio'
        ).filter(
            indicador__subtema__tema__dominio__activo=True,
            indicador__subtema__activo=True,
            indicador__activo=True
        ).order_by(
            'indicador__subtema__tema__dominio__orden',
            'indicador__subtema__tema__orden',
            'indicador__subtema__orden',
            'indicador__nombre'
        )
        
        # Organizar en estructura jerárquica
        datasets = {}
        for conjunto_datos in conjunto_datos_list:
            dominio = conjunto_datos.indicador.subtema.tema.dominio
            tema = conjunto_datos.indicador.subtema.tema
            subtema = conjunto_datos.indicador.subtema
            
            if dominio.slug not in datasets:
                datasets[dominio.slug] = {
                    'id': dominio.id,
                    'nombre': dominio.nombre,
                    'slug': dominio.slug,
                    'temas': {}
                }
            
            if tema.slug not in datasets[dominio.slug]['temas']:
                datasets[dominio.slug]['temas'][tema.slug] = {
                    'id': tema.id,
                    'nombre': tema.nombre,
                    'slug': tema.slug,
                    'subtemas': {}
                }
            
            if subtema.slug not in datasets[dominio.slug]['temas'][tema.slug]['subtemas']:
                datasets[dominio.slug]['temas'][tema.slug]['subtemas'][subtema.slug] = {
                    'id': subtema.id,
                    'nombre': subtema.nombre,
                    'slug': subtema.slug,
                    'datasets': []
                }
            
            datasets[dominio.slug]['temas'][tema.slug]['subtemas'][subtema.slug]['datasets'].append({
                'id': conjunto_datos.id,
                'nombre': conjunto_datos.nombre,
                'archivo': conjunto_datos.archivo.name if conjunto_datos.archivo else None,
                'descripcion': conjunto_datos.descripcion,
                'indicador_id': conjunto_datos.indicador.id,
                'indicador_nombre': conjunto_datos.indicador.nombre,
                'fecha_carga': conjunto_datos.fecha_carga.isoformat() if conjunto_datos.fecha_carga else None,
                'tamaño_archivo': conjunto_datos.tamaño_archivo,
                'num_filas': conjunto_datos.num_filas,
                'num_columnas': conjunto_datos.num_columnas
            })
        
        return JsonResponse({
            'success': True,
            'datasets': datasets
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_conjunto_datos_datasets_hierarchical(request):
    """
    API que devuelve los datasets de conjunto_datos organizados jerárquicamente por dominio > tema > subtema.
    Se puede filtrar por dominio_id, tema_id o subtema_id.
    """
    try:
        # Obtener parámetros de filtro
        dominio_id = request.GET.get('dominio_id')
        tema_id = request.GET.get('tema_id')
        subtema_id = request.GET.get('subtema_id')
        
        # Construir el queryset base de indicadores con sus relaciones
        indicadores = Indicador.objects.filter(
            activo=True,
            conjunto_datos__isnull=False,
            conjunto_datos__archivo_csv__isnull=False
        ).select_related(
            'subtema__tema__dominio',
            'conjunto_datos'
        ).prefetch_related(
            'conjunto_datos__indicadores'
        )
        
        # Aplicar filtros jerárquicos (subtema principal + adicionales M2M)
        if subtema_id:
            indicadores = indicadores.filter(
                Q(subtema_id=subtema_id) | Q(subtemas_adicionales__id=subtema_id)
            ).distinct()
        elif tema_id:
            indicadores = indicadores.filter(
                Q(subtema__tema_id=tema_id) | Q(subtemas_adicionales__tema_id=tema_id)
            ).distinct()
        elif dominio_id:
            indicadores = indicadores.filter(
                Q(subtema__tema__dominio_id=dominio_id) |
                Q(subtemas_adicionales__tema__dominio_id=dominio_id)
            ).distinct()
        
        # Construir la estructura jerárquica
        dominios = {}
        
        for indicador in indicadores:
            if not hasattr(indicador, 'subtema') or not hasattr(indicador.subtema, 'tema') or not hasattr(indicador.subtema.tema, 'dominio'):
                continue
                
            conjunto_datos = indicador.conjunto_datos
            subtema = indicador.subtema
            tema = subtema.tema
            dominio = tema.dominio
            
            # Inicializar la estructura si no existe
            if dominio.id not in dominios:
                dominios[dominio.id] = {
                    'id': dominio.id,
                    'nombre': dominio.nombre,
                    'slug': dominio.slug,
                    'temas': {}
                }
            
            if tema.id not in dominios[dominio.id]['temas']:
                dominios[dominio.id]['temas'][tema.id] = {
                    'id': tema.id,
                    'nombre': tema.nombre,
                    'slug': tema.slug,
                    'subtemas': {}
                }
            
            if subtema.id not in dominios[dominio.id]['temas'][tema.id]['subtemas']:
                dominios[dominio.id]['temas'][tema.id]['subtemas'][subtema.id] = {
                    'id': subtema.id,
                    'nombre': subtema.nombre,
                    'slug': subtema.slug,
                    'datasets': []
                }
            
            # Verificar si ya existe este dataset en este subtema
            existing_dataset = next(
                (d for d in dominios[dominio.id]['temas'][tema.id]['subtemas'][subtema.id]['datasets'] 
                 if d['id'] == conjunto_datos.id), None
            )
            
            if not existing_dataset and conjunto_datos.archivo_csv:
                try:
                    file_size = conjunto_datos.archivo_csv.size
                    file_name = conjunto_datos.archivo_csv.name
                    file_exists = os.path.exists(conjunto_datos.archivo_csv.path)
                    
                    # Only include the dataset if the file exists
                    if file_exists:
                        dominios[dominio.id]['temas'][tema.id]['subtemas'][subtema.id]['datasets'].append({
                            'id': conjunto_datos.id,
                            'nombre': conjunto_datos.nombre,
                            'descripcion': conjunto_datos.descripcion,
                            'fecha_carga': conjunto_datos.fecha_carga.strftime('%Y-%m-%d %H:%M:%S') if conjunto_datos.fecha_carga else None,
                            'archivo': file_name,
                            'tamano': file_size,
                            'tamano_humano': humanize.naturalsize(file_size) if file_size else '0 B',
                            'indicador_id': indicador.id,
                            'indicador_nombre': indicador.nombre,
                            'disponible': True
                        })
                    else:
                        logger.warning(f"Archivo no encontrado: {conjunto_datos.archivo_csv.path}")
                        
                except Exception as e:
                    logger.error(f"Error al procesar archivo {conjunto_datos.archivo_csv.name if hasattr(conjunto_datos.archivo_csv, 'name') else 'unknown'}: {str(e)}")
                    try:
                      
                        detail_url = request.build_absolute_uri(detail_url)
                    except Exception as url_error:
                        logger.error(f"Error construyendo URL para dataset {conjunto_datos.id}: {str(url_error)}")
                
                    
                    # Include the dataset but mark it as unavailable
                    dominios[dominio.id]['temas'][tema.id]['subtemas'][subtema.id]['datasets'].append({
                        'id': conjunto_datos.id,
                        'nombre': conjunto_datos.nombre,
                        'descripcion': conjunto_datos.descripcion,
                        'fecha_carga': conjunto_datos.fecha_carga.strftime('%Y-%m-%d %H:%M:%S') if conjunto_datos.fecha_carga else None,
                        'archivo': conjunto_datos.archivo_csv.name if hasattr(conjunto_datos.archivo_csv, 'name') else None,
                        'tamano': 0,
                        'tamano_human': '0 B',
    
                        'indicador_id': indicador.id,
                        'indicador_nombre': indicador.nombre,
                        'disponible': False,
                        'error': 'Archivo no disponible temporalmente'
                    })
        
        # Convertir diccionarios anidados a listas para la respuesta JSON
        response_data = []
        for dominio in dominios.values():
            dominio_data = dominio.copy()
            dominio_data['temas'] = list(dominio['temas'].values())
            
            for tema in dominio_data['temas']:
                tema['subtemas'] = list(tema['subtemas'].values())
                
                for subtema in tema['subtemas']:
                    subtema['datasets_count'] = len(subtema['datasets'])
            
            response_data.append(dominio_data)
        
        return JsonResponse({'dominios': response_data})
        
    except Exception as e:
        logger.error(f"Error en api_conjunto_datos_datasets_hierarchical: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse(
            {'error': 'Error al cargar los datasets jerárquicos', 'detalle': str(e)},
            status=500
        )


def api_conjunto_datos_detail(request, conjunto_datos_id):
    """API para obtener detalles de un conjunto_datos específico"""
    try:
        conjunto_datos = get_object_or_404(ConjuntoDatos, id=conjunto_datos_id)
        
        # Get file stats if file exists
        file_stats = None
        if conjunto_datos.archivo_csv and os.path.exists(conjunto_datos.archivo_csv.path):
            try:
                file_stats = os.stat(conjunto_datos.archivo_csv.path)
            except (OSError, ValueError):
                pass
        
        # Información técnica del conjunto_datos
        data = {
            'id': conjunto_datos.id,
            'nombre': conjunto_datos.nombre,
            'descripcion': conjunto_datos.descripcion,
            'archivo': conjunto_datos.archivo_csv.name if conjunto_datos.archivo_csv else None,
            'archivo_url': conjunto_datos.archivo_csv.url if conjunto_datos.archivo_csv else None,
            'fecha_carga': conjunto_datos.fecha_carga.isoformat() if conjunto_datos.fecha_carga else None,
            'tamano_archivo': file_stats.st_size if file_stats else 0,
            'tamano_archivo_humano': humanize.naturalsize(file_stats.st_size) if file_stats else '0 B',
            'num_filas': getattr(conjunto_datos, 'num_filas', 0),
            'num_columnas': getattr(conjunto_datos, 'num_columnas', 0),
            'columnas_detectadas': getattr(conjunto_datos, 'columnas_detectadas', []),
            'tipos_datos': getattr(conjunto_datos, 'tipos_datos', {}),
            'muestra_datos': getattr(conjunto_datos, 'muestra_datos', []),
        }
        
        # Add related indicador info if exists
        if hasattr(conjunto_datos, 'indicador'):
            # Extraer texto limpio de descripcion_indicador (MSD 2.2)
            import re
            definiciones = ''
            if conjunto_datos.indicador.descripcion_indicador:
                definiciones = re.sub(r'<[^>]+>', '', str(conjunto_datos.indicador.descripcion_indicador))
            
            indicador_data = {
                'id': conjunto_datos.indicador.id,
                'nombre': conjunto_datos.indicador.nombre,
                'descripcion': definiciones,
                'unidad_medida': conjunto_datos.indicador.unidad_medida,
            }
            
            # Add subtema info if exists
            if hasattr(conjunto_datos.indicador, 'subtema'):
                subtema_data = {
                    'nombre': conjunto_datos.indicador.subtema.nombre,
                }
                
                # Add tema info if exists
                if hasattr(conjunto_datos.indicador.subtema, 'tema'):
                    tema_data = {
                        'nombre': conjunto_datos.indicador.subtema.tema.nombre,
                    }
                    
                    # Add dominio info if exists
                    if hasattr(conjunto_datos.indicador.subtema.tema, 'dominio'):
                        tema_data['dominio'] = {
                            'nombre': conjunto_datos.indicador.subtema.tema.dominio.nombre,
                        }
                    
                    subtema_data['tema'] = tema_data
                
                indicador_data['subtema'] = subtema_data
            
            data['indicador'] = indicador_data
        
        return JsonResponse({
            'success': True,
            'conjunto_datos': data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# SERVICIOS DE CHAT E IA
# =============================================================================





# Mantener funciones de vista existentes con mejoras mínimas
def cleanup_old_requests(max_age_minutes=None, max_processing_time=None, max_users=None):
    """Limpieza optimizada de requests antiguos por usuario"""
    # Usar valores de configuración si no se proporcionan
    # OJO: streams LLM legítimos pueden durar varios minutos; un umbral
    # corto hacía que el cleanup "cancelara" respuestas en curso.
    max_age_minutes = max_age_minutes or get_config('REQUEST_MAX_AGE_MINUTES', 20)
    max_processing_time = max_processing_time or get_config('CLEANUP_MAX_TIME', 3.0)
    max_users = max_users or get_config('MAX_ACTIVE_USERS', 50)
    
    start_time = time.time()
    logger.info(f"[CLEANUP] Iniciando limpieza optimizada")
    
    try:
        if not active_requests_lock.acquire(blocking=False):
            logger.debug("[CLEANUP] Lock ocupado, omitiendo limpieza")
            return
        
        try:
            now = timezone.now()
            old_user_keys = [
                user_key for user_key, req in list(active_requests.items())[:max_users]
                if (now - req['timestamp']).total_seconds() > max_age_minutes * 60
            ]
            
            for user_key in old_user_keys:
                if (time.time() - start_time) > max_processing_time:
                    break
                
                try:
                    if user_key in active_requests:
                        del active_requests[user_key]
                        logger.debug(f"[CLEANUP] Usuario {user_key[:20]}... eliminado")
                except Exception as e:
                    logger.warning(f"[CLEANUP] Error eliminando usuario {user_key[:20]}...: {e}")
            
            logger.info(f"[CLEANUP] Completado en {time.time() - start_time:.2f}s. "
                       f"Eliminadas: {len(old_user_keys)}")
                       
        finally:
            active_requests_lock.release()
            
    except Exception as e:
        logger.error(f"[CLEANUP] Error crítico: {e}")


# === VISTAS OPTIMIZADAS ===

@csrf_exempt
@require_http_methods(["POST"])
def chat_message(request):
    """Endpoint principal para mensajes del chat con streaming optimizado"""
    
    # Configurar sesión
    if not request.session.session_key:
        request.session.create()
        request.session.modified = True
    
    if 'conversation' not in request.session:
        request.session['conversation'] = []
    
    session_id = request.session.session_key
    request_id = request.headers.get('X-Request-ID') or f"req_{uuid.uuid4().hex[:8]}"
    
    # Generar clave única por usuario (permite múltiples usuarios concurrentes)
    user_key = get_user_key(request)
    
    try:
        # Parsear datos de entrada
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return JsonResponse({"error": "Mensaje vacío"}, status=400)
        
        logger.info(f"Nueva consulta - User: {user_key[:20]}..., Mensaje: {user_message[:50]}...")
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Formato JSON inválido"}, status=400)
    except Exception as e:
        logger.error(f"Error procesando solicitud: {e}")
        return JsonResponse({"error": "Error interno del servidor"}, status=500)

    # Gestión de requests concurrentes optimizada con funciones atómicas
    cleanup_old_requests()
    
    # Registrar request de forma atómica (cancela el anterior del MISMO usuario automáticamente)
    abort_controller = register_request_atomic(user_key, request_id)

    def optimized_event_stream():
        """Stream de eventos con formato SSE consistente"""
        assistant_response = ""
        
        try:
            def is_cancelled():
                return is_request_cancelled(user_key, request_id)
            
            if is_cancelled():
                yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
                return
            
            conversation_history = request.session.get('conversation', [])
            max_history = get_config('MAX_HISTORY_MESSAGES', 8)
            conversation_history = [
                msg for msg in conversation_history[-max_history:]
                if (isinstance(msg, dict) and 
                    msg.get('content') and 
                    msg.get('role') in ['user', 'assistant'])
            ]
            
            # Crear nueva instancia con request para URLs dinámicas
            chat_service = ChatService(request=request)
            
            relevant_data = {}
            try:
                relevant_data = chat_service.search_relevant_data(user_message)
            except Exception as e:
                logger.warning(f"Error buscando datos relevantes: {e}")
            
            # Detectar si necesita tools
            uses_tools = chat_service._should_use_tools(user_message)
            
            chunk_count = 0
            tool_used = False
            updated_history = None
            
            # ENVIAR EVENTO DE INICIO
            yield f"data: {json.dumps({'type': 'start', 'uses_tools': uses_tools})}\n\n"
            
            # Obtener el generador de respuesta y capturar el historial actualizado
            response_generator = chat_service.generate_response_stream(
                user_message,
                relevant_data=relevant_data,
                conversation_history=conversation_history
            )
            
            # Procesar los chunks de respuesta
            for chunk in response_generator:
                if chunk_count % 5 == 0 and is_cancelled():
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                    return
                
                chunk_count += 1
                
                if isinstance(chunk, dict):
                    # Manejar contenido normal
                    if 'content' in chunk and chunk['content']:
                        content = chunk['content']
                        assistant_response += content
                        
                        # Enviar contenido al frontend
                        yield f"data: {json.dumps({'type': 'content', 'content': content,'source': chunk.get('source', 'unknown')})}\n\n"
                    
                    # Manejar herramientas ejecutadas
                    elif 'tool_results' in chunk:
                        tool_used = True
                        # Obtener los resultados de la herramienta
                        tool_results = chunk['tool_results']
                        
                        # Verificar si hay un error en los resultados
                        if isinstance(tool_results, dict) and 'error' in tool_results:
                            error_msg = tool_results.get('error', 'Error desconocido al ejecutar la herramienta')
                            yield f"data: {json.dumps({'type': 'error', 'content': f'Error: {error_msg}'})}\n\n"
                            assistant_response += f"Error: {error_msg}\n\n"
                        else:
                            # Formatear los resultados para mostrar al usuario
                            formatted_results = chat_service._format_tool_results_for_display(tool_results)
                            if formatted_results:
                                assistant_response += formatted_results
                                yield f"data: {json.dumps({'type': 'tool_results', 'content': formatted_results})}\n\n"
                    # Manejar errores
                    elif 'error' in chunk:
                        yield f"data: {json.dumps({'type': 'error', 'error': chunk['error']})}\n\n"
                        return
                    
                    # Verificar si está completo
                    elif chunk.get('is_complete'):
                        # Si el chunk contiene el historial actualizado, guardarlo
                        if isinstance(chunk, dict) and 'updated_history' in chunk:
                            updated_history = chunk['updated_history']
                        break
            
            # Actualizar el historial de conversación en la sesión
            try:
                if updated_history is not None:
                    # Si tenemos un historial actualizado, usarlo
                    request.session['conversation'] = updated_history
                else:
                    # Si no, actualizar manualmente con la respuesta
                    if assistant_response:
                        request.session['conversation'].append({
                            'role': 'user',
                            'content': user_message
                        })
                        request.session['conversation'].append({
                            'role': 'assistant',
                            'content': assistant_response
                        })
                
                # Guardar la sesión
                request.session.modified = True
                request.session.save()
                
            except Exception as e:
                logger.error(f"Error actualizando historial de conversación: {e}")
            
            # Evento de finalización
            yield f"data: {json.dumps({'type': 'complete', 'final_length': len(assistant_response),'tool_used': tool_used})}\n\n"
            
        except Exception as e:
            logger.error(f"Error en event stream: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Error procesando solicitud'})}\n\n"
        
        finally:
            # Limpiar request activo de forma atómica
            unregister_request_atomic(user_key, request_id)
            
    # Return the streaming response
    response = StreamingHttpResponse(
        optimized_event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Deshabilitar buffering en Nginx
    return response
@require_http_methods(["POST"])  
def chat_cancel(request):
    """Endpoint para cancelar requests activos"""
    if not request.session.session_key:
        return JsonResponse({"error": "No hay sesión activa"}, status=400)
    
    # Generar clave única del usuario
    user_key = get_user_key(request)
    
    # Cancelar request de forma thread-safe
    with active_requests_lock:
        current = active_requests.get(user_key)
        if current:
            # Marcar como cancelado
            current['active'] = False
            if 'abort_controller' in current:
                current['abort_controller'].set()
            logger.info(f"Request cancelado para usuario: {user_key[:20]}...")
            return JsonResponse({"status": "cancelled"})
        else:
            return JsonResponse({"status": "no_active_request"})


@require_http_methods(["GET"])
def chat_suggestions(request):
    """Endpoint optimizado para sugerencias inteligentes - Lee de chat_config.py"""
    from . import chat_config
    
    # Obtener sugerencias desde la configuración (editable desde el admin)
    suggestions = getattr(chat_config, 'CHAT_SUGGESTIONS', {
        "exploratorias": ["¿Qué dominios están disponibles?"],
        "especificas": ["Buscar indicadores de población"],
        "comparativas": ["Comparar datos entre años"],
        "datos_completos": ["Obtener histórico de indicadores"]
    })
    
    # Seleccionar sugerencias variadas (2 de cada categoría)
    all_suggestions = []
    for category in suggestions.values():
        all_suggestions.extend(category[:2])  # 2 de cada categoría
    
    return JsonResponse({
        'suggestions': all_suggestions[:8],  # Máximo 8 sugerencias
        'categories': list(suggestions.keys())
    })


@require_http_methods(["GET"])
def chat_status(request):
    """Endpoint para verificar estado del sistema de chat"""
    try:
        # Verificar disponibilidad de herramientas
        chat_service = ChatService(request=request)
        tools_available = chat_service.tools_enabled
        
        # Estadísticas básicas del sistema
        stats = chat_service._get_basic_stats()
        
        # Información de requests activos
        with active_requests_lock:
            active_count = len(active_requests)
        
        return JsonResponse({
            "status": "operational",
            "tools_enabled": tools_available,
            "active_requests": active_count,
            "system_stats": stats,
            "api_model": chat_service.model_config.get("model", "Unknown"),
            "timestamp": timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error en chat status: {e}")
        return JsonResponse({
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat()
        }, status=500)


@require_http_methods(["GET"])
def chat_view(request):
    """Vista principal del chat con contexto optimizado"""
    
    # Obtener estadísticas para el contexto inicial
    try:
        chat_service = ChatService(request=request)
        context = {
            'tools_enabled': chat_service.tools_enabled,
            'system_stats': chat_service._get_basic_stats(),
            'session_id': request.session.session_key or 'new'
        }
    except Exception as e:
        logger.error(f"Error preparando contexto de chat: {e}")
        context = {
            'tools_enabled': False,
            'system_stats': {},
            'session_id': 'error'
        }
    
    return render(request, 'indicadores/chat.html', context)


def optimize_conversation_for_context(conversation_history, max_messages=None):
    """
    Optimiza el historial de conversación para el contexto.
    Mantiene mensajes del sistema y asegura que el contexto de la conversación se mantenga.
    """
    # Usar valor de configuración si no se proporciona
    max_messages = max_messages or get_config('MAX_HISTORY_MESSAGES', 8)
    max_length = get_config('MAX_MESSAGE_LENGTH', 1000)
    
    if not conversation_history or not isinstance(conversation_history, list):
        return []
    
    # Filtrar mensajes válidos
    valid_messages = []
    seen_messages = set()  # Para evitar duplicados
    
    # Mantener mensajes del sistema primero
    system_messages = []
    other_messages = []
    
    for msg in conversation_history:
        if not isinstance(msg, dict) or not msg.get('content') or not isinstance(msg.get('content'), str):
            continue
            
        content = msg['content'].strip()
        if not content:
            continue
            
        # Generar una firma única para el mensaje para evitar duplicados
        msg_signature = f"{msg.get('role', '')}:{content[:100]}"
        if msg_signature in seen_messages:
            continue
            
        seen_messages.add(msg_signature)
        
        # Truncar contenido muy largo
        if len(content) > max_length:
            content = content[:max_length] + "..."
            msg = {**msg, 'content': content}
        
        if msg.get('role') == 'system':
            system_messages.append(msg)
        else:
            other_messages.append(msg)
    
    # Mantener todos los mensajes del sistema y los últimos mensajes de la conversación
    max_other_messages = max(1, max_messages - len(system_messages))  # Asegurar al menos 1 mensaje
    return system_messages + other_messages[-max_other_messages:]
        
    
    # Mantener solo los mensajes más recientes
    return valid_messages[-max_messages:] if len(valid_messages) > max_messages else valid_messages


# === CONFIGURACIÓN Y VALIDACIÓN ===

def validate_chat_configuration():
    """Valida la configuración del sistema de chat"""
    issues = []
    
    try:
        # Verificar API key (sin request ya que es una validación general)
        test_service = ChatService()
        if not hasattr(test_service, 'api_key') or not test_service.api_key:
            issues.append("API key de Cerebras no configurada")

        # Verificar base de datos
        try:
            MenuDominio.objects.count()
        except Exception as e:
            issues.append(f"Error de base de datos: {e}")
        
        # Verificar caché
        try:
            cache.set('test_key', 'test_value', 30)
            if cache.get('test_key') != 'test_value':
                issues.append("Sistema de caché no funcional")
            cache.delete('test_key')
        except Exception as e:
            issues.append(f"Error de caché: {e}")
    
    except Exception as e:
        issues.append(f"Error de validación general: {e}")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "timestamp": timezone.now().isoformat()
    }

@csrf_exempt  
@require_http_methods(["POST"])
def chat_stream(request):
    """Endpoint para respuestas streaming con soporte para cancelación"""
    # Ensure we have a session key and save it if it's new
    if not request.session.session_key:
        request.session.create()
        request.session.modified = True
    session_id = request.session.session_key
    request_id = str(uuid.uuid4())
    
    # Generar clave única por usuario (permite múltiples usuarios concurrentes)
    user_key = get_user_key(request)
    
    # Limpiar solicitudes antiguas
    cleanup_old_requests()
    
    # Registrar request de forma atómica
    abort_controller = register_request_atomic(user_key, request_id)
    
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return JsonResponse({
                'error': 'Mensaje vacío',
                'request_id': request_id
            }, status=400)
        
        # Configurar timeout para la solicitud (30 segundos)
        timeout = 30
        start_time = timezone.now()
        
        # Inicializar servicio de chat con request para URLs dinámicas
        chat_service = ChatService(request=request)
        
        # Verificar si la solicitud fue cancelada
        def check_aborted():
            return is_request_cancelled(user_key, request_id)
        
        def generate_stream():
            try:
                system_context = chat_service.get_system_context()
                
                # Verificar si la solicitud fue cancelada antes de buscar datos
                if check_aborted():
                    yield "event: aborted\ndata: {\"status\": \"cancelled\"}\n\n"
                    return
                
                # Buscar datos relevantes
                relevant_data = chat_service.search_relevant_data(user_message)
                
                # Verificar nuevamente después de buscar datos
                if check_aborted():
                    yield "event: aborted\ndata: {\"status\": \"cancelled\"}\n\n"
                    return
                
                # Construir mensajes con contexto del sistema y datos relevantes
                messages = [{"role": "system", "content": system_context}]
                
                # Agregar datos relevantes al contexto si existen
                if relevant_data:
                    messages.append({
                        "role": "system",
                        "content": get_context('relevant_data_simple', data=relevant_data)
                    })
                
                # Agregar el mensaje del usuario
                messages.append({"role": "user", "content": user_message})
                
                # Realizar la llamada a la API con streaming
                response = chat_service.call_openrouter_api(messages, stream=True)
                
                # Procesar la respuesta en tiempo real
                for line in response.iter_lines():
                    # Verificar timeout
                    if (timezone.now() - start_time).total_seconds() > timeout:
                        yield "event: error\ndata: {\"error\": \"Tiempo de espera agotado\"}\n\n"
                        break
                        
                    # Verificar si se canceló la solicitud
                    if check_aborted():
                        yield "event: aborted\ndata: {\"status\": \"cancelled\"}\n\n"
                        break
                        
                    if line:
                        line_text = line.decode('utf-8')
                        if line_text.startswith('data: '):
                            data_text = line_text[6:]
                            if data_text.strip() == '[DONE]':
                                yield "event: done\ndata: {\"status\": \"completed\"}\n\n"
                                break
                            try:
                                chunk_data = json.loads(data_text)
                                if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                    delta = chunk_data['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        # Enviar el fragmento de respuesta como un evento SSE
                                        yield f"event: message\ndata: {json.dumps({'content': delta['content']})}\n\n"
                            except json.JSONDecodeError:
                                continue
                
                # Marcar como completado
                yield "event: done\ndata: {\"status\": \"completed\"}\n\n"
                                
            except Exception as e:
                logger.error(f"Error en stream: {e}")
                yield f"event: error\ndata: {json.dumps({'error': 'Error en la transmisión'})}\n\n"
            finally:
                # Limpiar la solicitud activa de forma atómica
                unregister_request_atomic(user_key, request_id)
        
        # Configurar la respuesta de streaming
        response = StreamingHttpResponse(
            generate_stream(),
            content_type='text/event-stream'
        )
        
        # Configurar headers para evitar caché
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # Deshabilitar buffering en Nginx
        response['X-Request-ID'] = request_id  # Incluir el ID de solicitud
        
        return response
        
    except Exception as e:
        logger.error(f"Error configurando stream: {e}")
        return JsonResponse({'error': 'Error interno'}, status=500)



@csrf_exempt
@require_http_methods(["POST"])
def buscar_semantico(request):
    """Endpoint para búsqueda semántica"""
    try:
        data = json.loads(request.body)
        consulta = data.get('consulta', '')
        tipo_doc = data.get('tipo_doc')  # opcional: 'indicador', 'tema', etc.
        top_k = int(data.get('top_k', 5))
        umbral = float(data.get('umbral', 0.6))
        
        if not consulta:
            return JsonResponse({'error': 'La consulta no puede estar vacía'}, status=400)
        
        buscador = SemanticSearch()
        resultados = buscador.buscar_similar(
            consulta=consulta,
            tipo_doc=tipo_doc,
            top_k=top_k,
            umbral=umbral
        )
        
        return JsonResponse({
            'resultados': resultados,
            'consulta': consulta
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# SERVICIOS DE TEXT-TO-SPEECH (TTS)
# =============================================================================


_tts_instance = None
_tts_model_name = None
_tts_lock = threading.Lock()  # Para thread-safety

def get_tts_instance(preferred_model=None):
    """
    Obtiene o crea una instancia singleton de TTS con lazy loading.
    Esto evita cargar el modelo en memoria hasta que sea necesario.
    
    Args:
        preferred_model (str, optional): Nombre del modelo preferido
        
    Returns:
        TTS: Instancia del modelo TTS o None si falla
    """
    global _tts_instance, _tts_model_name
    
    if not COQUI_TTS_AVAILABLE:
        return None
    
    with _tts_lock:
        # Si ya existe una instancia con el mismo modelo, reutilizarla
        if _tts_instance is not None:
            if preferred_model is None or _tts_model_name == preferred_model:
                print(f"♻️  Reutilizando instancia TTS existente: {_tts_model_name}")
                return _tts_instance
            else:
                # Si se solicita un modelo diferente, limpiar la instancia anterior
                print(f"🔄 Cambiando modelo de {_tts_model_name} a {preferred_model}")
                _tts_instance = None
                _tts_model_name = None
        
        # Modelos a probar en orden de prioridad
        latino_models = [
            "tts_models/es/css10/vits-neon",
            "tts_models/es/mai/tacotron2-DDC",
            "tts_models/es/css10/vits",
            "tts_models/multilingual/multi-dataset/your_tts",
        ]
        
        fallback_models = [
            "tts_models/en/ljspeech/tacotron2-DDC_ph",
        ]
        
        # Si se especifica un modelo preferido, intentarlo primero
        models_to_try = [preferred_model] if preferred_model else []
        models_to_try.extend(latino_models + fallback_models)
        
        # Intentar cargar modelos en orden
        for model_name in models_to_try:
            if not model_name:
                continue
                
            try:
                print(f"🔄 Cargando modelo TTS (lazy): {model_name}")
                _tts_instance = TTS(model_name, progress_bar=False)
                _tts_model_name = model_name
                print(f"✅ Modelo TTS cargado exitosamente: {model_name}")
                return _tts_instance
            except Exception as e:
                print(f"⚠️ Error cargando modelo {model_name}: {e}")
                continue
        
        # Si ningún modelo específico funciona, intentar el modelo por defecto
        try:
            print("🔄 Cargando modelo TTS por defecto...")
            _tts_instance = TTS(progress_bar=False)
            _tts_model_name = "default"
            print("✅ Modelo TTS por defecto cargado")
            return _tts_instance
        except Exception as e:
            print(f"❌ Error cargando modelo TTS por defecto: {e}")
            return None

@csrf_exempt
@require_http_methods(["GET"])
def text_to_speech(request):
    """
    Genera audio usando Coqui TTS o pico2wave como fallback
    con soporte para acentos latinoamericanos

    Parámetros opcionales:
    - text: texto a convertir (requerido)
    - lang: idioma (por defecto 'es')
    - accent: variante de acento ('standard', 'latino', 'neutral')

    Ejemplos de uso:
    - /tts/?text=Hola%20mundo                           # Acento latino por defecto
    - /tts/?text=Hello&lang=en                         # Inglés estándar
    - /tts/?text=Bonjour&lang=fr&accent=neutral        # Francés acento neutral
    - /tts/?text=Texto&accent=standard                 # Acento estándar
    """
    text = request.GET.get("text", "Texto de prueba")
    lang = request.GET.get("lang", "es")
    accent = request.GET.get("accent", "latino")  # Por defecto acento latino
    # Nota: speed se maneja en el frontend con Web Audio API

    # Validar texto
    if not text or len(text.strip()) == 0:
        return HttpResponse("Texto vacío", status=400)

    if len(text) > 2000:  # Limitar longitud
        text = text[:2000] + "..."

    # Cache de audio: la síntesis TTS en CPU es costosa y los textos se repiten
    cache_key = f"tts_audio:{hashlib.md5(f'{text}|{lang}|{accent}'.encode()).hexdigest()}"
    cached_audio = cache.get(cache_key)
    if cached_audio:
        response = HttpResponse(cached_audio, content_type='audio/wav')
        response['Content-Disposition'] = 'inline; filename="tts_cached.wav"'
        return response

    # Intentar con Coqui TTS usando lazy loading
    tts_instance = get_tts_instance()

    if tts_instance:
        try:
            response = _generate_audio_coqui_tts(tts_instance, text, lang, accent)
        except Exception as e:
            print(f"Error con Coqui TTS: {e}")
            print("Intentando con pico2wave...")
            response = _generate_audio_pico2wave(text, lang)
    else:
        # Si no hay TTS disponible, usar pico2wave
        response = _generate_audio_pico2wave(text, lang)

    # Guardar en cache solo respuestas de audio válidas (7 días)
    if getattr(response, 'status_code', 0) == 200 and getattr(response, 'content', None):
        cache.set(cache_key, response.content, timeout=7 * 24 * 3600)
    return response

def _generate_audio_coqui_tts(tts, text, lang, accent="latino"):
    """
    Genera audio usando una instancia existente de Coqui TTS.
    El modelo ya está cargado (lazy loading), solo genera el audio.
    
    Args:
        tts (TTS): Instancia del modelo TTS ya cargada
        text (str): Texto a sintetizar
        lang (str): Idioma
        accent (str): Tipo de acento (latino, neutral, standard)
        
    Returns:
        HttpResponse: Audio WAV como respuesta HTTP
    """
    try:
        # Crear buffer para el audio
        audio_buffer = io.BytesIO()

        # Nota: El parámetro 'speed' está deprecado en Coqui TTS
        # La velocidad se manipula en el frontend usando Web Audio API
        print(f"🎵 Generando audio con acento: {accent}")

        # Generar audio usando el modelo precargado
        tts.tts_to_file(
            text=text,
            file_path=audio_buffer,
            split_sentences=True,  # Mejor calidad para textos largos
        )

        audio_data = audio_buffer.getvalue()

        # Verificar que se generó audio válido
        if len(audio_data) < 1000:  # Si es muy pequeño, probablemente falló
            raise Exception("Audio generado muy pequeño, posiblemente corrupto")

        # Devolver audio como respuesta HTTP
        response = HttpResponse(audio_data, content_type='audio/wav')
        response['Content-Disposition'] = 'inline; filename="tts_latino.wav"'
        return response

    except Exception as e:
        print(f"Error generando audio con Coqui TTS: {e}")
        raise

def _generate_audio_pico2wave(text, lang):
    """Genera audio usando pico2wave como fallback"""
    try:
        # Crear archivo temporal para el audio
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            output_file = tmp_file.name

        # Mapear idiomas a códigos de pico2wave con acentos latinos
        lang_map = {
            'es': 'es-ES',  # Español estándar
            'en': 'en-US',
            'fr': 'fr-FR',
            'de': 'de-DE',
            'it': 'it-IT'
        }

        pico_lang = lang_map.get(lang, 'es-ES')

        # Generar audio con pico2wave
        # Usar configuración para mejor calidad y acento más claro
        subprocess.run([
            "pico2wave",
            f"-l={pico_lang}",
            "-w=" + output_file,
            text
        ], check=True, capture_output=True)

        # Leer archivo generado
        with open(output_file, 'rb') as audio_file:
            audio_data = audio_file.read()

        # Limpiar archivo temporal
        os.unlink(output_file)

        # Devolver audio como respuesta HTTP
        response = HttpResponse(audio_data, content_type='audio/wav')
        response['Content-Disposition'] = 'inline; filename="tts_fallback.wav"'
        return response

    except subprocess.CalledProcessError as e:
        print(f"Error en pico2wave: {e}")
        return HttpResponse("Error generando audio", status=500)
    except FileNotFoundError:
        print("pico2wave no encontrado. Instala: sudo apt-get install libttspico-utils")
        return HttpResponse("TTS no disponible", status=503)
    except Exception as e:
        print(f"Error inesperado en TTS: {e}")
        return HttpResponse("Error interno", status=500)


# ========================================
# VISTAS PARA VERSIONES 3D
# ========================================

def dominios_3d(request):
    """Vista para la página de dominios en versión 3D educativa"""
    dominios_data = MenuDominio.objects.filter(activo=True).order_by('orden')
    
    return render(request, 'indicadores/dominios_3d.html', {
        'page': 'dominios_3d',
        'dominios': dominios_data
    })


def dominio_detalle_3d(request, slug):
    """Vista para el detalle de un dominio en versión 3D educativa"""
    dominio = get_object_or_404(MenuDominio, slug__iexact=slug)
    temas = MenuTema.objects.filter(dominio=dominio).order_by('orden')
    
    return render(request, 'indicadores/dominio_detalle_3d.html', {
        'page': 'dominios_3d',
        'dominio': dominio,
        'temas': temas
    })


def tema_detalle_3d(request, dominio_slug, tema_slug):
    """Vista para el detalle de un tema en versión 3D educativa"""
    dominio = get_object_or_404(MenuDominio, slug__iexact=dominio_slug)
    tema = get_object_or_404(MenuTema, slug__iexact=tema_slug, dominio=dominio, activo=True)
    temas_del_dominio = MenuTema.objects.filter(dominio=dominio, activo=True).order_by('orden')
    subtemas = MenuSubtema.objects.filter(tema=tema, activo=True).order_by('orden')
    
    return render(request, 'indicadores/tema_detalle_3d.html', {
        'page': 'dominios_3d',
        'dominio': dominio,
        'tema_actual': tema,
        'temas_del_dominio': temas_del_dominio,
        'subtemas': subtemas
    })


# ========================================
# HALL DE CAPACIDAD ESTADÍSTICA
# ========================================

def hall_capacidad_estadistica(request):
    """
    Vista principal del Hall de Capacidad Estadística
    Muestra todos los organismos con sus métricas de capacidad estadística
    """
    from django.db.models import Count, Avg, Q
    from .models import Organismo, Indicador
    
    # Obtener todos los organismos activos con sus métricas
    organismos = Organismo.objects.filter(activo=True).annotate(
        # Indicadores bajo responsabilidad
        total_indicadores=Count('indicadores_responsables', distinct=True),
        # Inscripciones al taller de gestión de datos institucionales realizadas
        total_sesiones_taller=Count('inscripciones_taller', distinct=True),
        # Equipos del organismo (a través de suborganismos)
        total_equipos=Count('suborganismos__equipos', distinct=True),
        # Respuestas de satisfacción
        total_respuestas_rapidas=Count('respuestas_rapidas_organismo', distinct=True),
        total_respuestas_completas=Count('respuestas_completas_organismo', distinct=True),
        # Promedio de satisfacción (respuestas rápidas)
        promedio_satisfaccion=Avg('respuestas_rapidas_organismo__calificacion')
    ).order_by('-total_indicadores', '-promedio_satisfaccion', 'nombre')
    
    # Agregar índice de madurez, ICED y datos de equipos a cada organismo
    for organismo in organismos:
        organismo.indice_madurez_ecosistema = calcular_indice_madurez_ecosistema(organismo)
        
        # FICED del organismo (más reciente, validado o enviado).
        # Solo consolidados: los formularios por equipo son parciales.
        from .models_iced import ICEDFormulario
        organismo.ficed = ICEDFormulario.objects.filter(
            organismo=organismo,
            equipo='',
            estado__in=['validado', 'enviado']
        ).order_by('-periodo').first()
        
        # Agregar datos de equipos con sus métricas
        from .models import EquipoOrganismo
        equipos = EquipoOrganismo.objects.filter(
            suborganismo__organismo=organismo
        ).select_related('suborganismo').annotate(
            total_respuestas_rapidas=Count('respuestas_rapidas', distinct=True),
            total_respuestas_completas=Count('respuestas_completas', distinct=True),
            promedio_satisfaccion=Avg('respuestas_rapidas__calificacion')
        ).order_by('suborganismo__orden', 'nombre')[:5]  # Top 5 equipos
        organismo.equipos_data = equipos
    
    # Calcular estadísticas globales
    stats_globales = {
        'total_organismos': organismos.count(),
        'total_indicadores': sum(o.total_indicadores or 0 for o in organismos),
        'total_equipos': sum(o.total_equipos or 0 for o in organismos),
        'total_sesiones': sum(o.total_sesiones_taller or 0 for o in organismos),
        'total_evaluaciones': sum((o.total_respuestas_rapidas or 0) + (o.total_respuestas_completas or 0) for o in organismos),
        'promedio_global': organismos.aggregate(Avg('promedio_satisfaccion'))['promedio_satisfaccion__avg'] or 0
    }
    
    return render(request, 'indicadores/hall_capacidad_estadistica.html', {
        'page': 'hall_capacidad',
        'organismos': organismos,
        'stats_globales': stats_globales
    })


def organismo_detalle(request, codigo):
    """
    Vista detallada de un organismo específico
    Muestra la hoja de vida completa del organismo
    """
    from django.db.models import Count, Avg, Q, Prefetch
    from .models import (
        Organismo, Indicador,
        RespuestaSatisfaccionRapida, RespuestaSatisfaccionCompleta,
    )
    from .models_taller import InscripcionTaller
    from .models_catalogo import FuenteDatos, FuenteOrigen
    
    organismo = get_object_or_404(Organismo, codigo=codigo, activo=True)
    
    # Indicadores bajo responsabilidad
    indicadores = Indicador.objects.filter(
        organismo_responsable=organismo
    ).select_related('operacion').order_by('-fecha_actualizacion_ficha')[:10]
    
    # Inscripciones al taller de gestión de datos institucionales (instrumento F1/F2/F3)
    sesiones = InscripcionTaller.objects.filter(
        organismo=organismo
    ).select_related('suborganismo', 'equipo').annotate(
        num_fuentes=Count('fuentes', distinct=True)
    ).order_by('-creado')
    
    # Respuestas de satisfacción
    respuestas_rapidas = RespuestaSatisfaccionRapida.objects.filter(
        organismo=organismo
    ).order_by('-fecha_registro')[:20]
    
    respuestas_completas = RespuestaSatisfaccionCompleta.objects.filter(
        organismo=organismo
    ).order_by('-fecha_registro')[:10]
    
    # Consulta separada para distribución de calificaciones (sin slice)
    respuestas_rapidas_todas = RespuestaSatisfaccionRapida.objects.filter(
        organismo=organismo
    )
    
    # Fuentes de datos del organismo por rol (catálogo F1)
    fuentes_org = FuenteDatos.objects.filter(inscripcion__organismo=organismo)
    flujos_recibe = fuentes_org.filter(rol__in=['usuario', 'ambos'])[:10]
    flujos_envia = fuentes_org.filter(rol__in=['productor', 'ambos'])[:10]
    
    # Calcular índice de madurez del ecosistema
    indice_madurez = calcular_indice_madurez_ecosistema(organismo)
    
    # FICED: Formulario de Capacidad Estadística Distrital.
    # Solo consolidados: los formularios por equipo son parciales.
    from .models_iced import ICEDFormulario
    ficed_qs = ICEDFormulario.objects.filter(
        organismo=organismo,
        equipo='',
        estado__in=['validado', 'enviado'],
    ).order_by('-periodo')
    ficed_historico = list(ficed_qs.all())
    periodos_disponibles = [h.periodo for h in ficed_historico]
    # Allow selecting a specific period via ?periodo=
    periodo_sel = request.GET.get('periodo')
    if periodo_sel and periodo_sel in periodos_disponibles:
        ficed = ficed_qs.filter(periodo=periodo_sel).first()
    else:
        ficed = ficed_qs.first()
    
    # Métricas calculadas
    metricas = {
        'total_indicadores': indicadores.count(),
        'total_sesiones': sesiones.count(),
        'total_participantes': sesiones.count(),
        'total_respuestas_rapidas': respuestas_rapidas.count(),
        'total_respuestas_completas': respuestas_completas.count(),
        'promedio_satisfaccion_rapida': respuestas_rapidas.aggregate(Avg('calificacion'))['calificacion__avg'] or 0,
        'total_flujos_entrada': flujos_recibe.count(),
        'total_flujos_salida': flujos_envia.count(),
        # Nuevas métricas del ecosistema
        'indice_madurez_ecosistema': indice_madurez,
        'roles_identificados': obtener_roles_identificados(organismo),
        'flujos_internos': obtener_flujos_internos(organismo),
        'flujos_externos': obtener_flujos_externos(organismo),
        'densidad_red': calcular_densidad_red(organismo),
        'diversidad_datos': obtener_diversidad_datos(organismo),
        'fuentes_caracterizadas': fuentes_org.count(),
        'fuentes_origen_declaradas': FuenteOrigen.objects.filter(
            fuente__inscripcion__organismo=organismo).count(),
        # FICED
        'ficed': ficed,
        'ficed_historico': ficed_historico,
        'periodos_disponibles': periodos_disponibles,
    }
    # Nombres legibles de los 36 indicadores ICED
    from .calcular_iced import INDICADOR_LABELS
    metricas['iced_indicador_labels'] = INDICADOR_LABELS
    
    # Distribución de calificaciones
    distribucion_calificaciones = {
        1: respuestas_rapidas_todas.filter(calificacion=1).count(),
        2: respuestas_rapidas_todas.filter(calificacion=2).count(),
        3: respuestas_rapidas_todas.filter(calificacion=3).count(),
        4: respuestas_rapidas_todas.filter(calificacion=4).count(),
        5: respuestas_rapidas_todas.filter(calificacion=5).count(),
    }
    
    # ========================================================================
    # INDICADORES ESPECÍFICOS PARA RESPUESTAS COMPLETAS DEL ORGANISMO
    # ========================================================================
    
    # Variables de las 3 dimensiones
    variables = {
        'utilidad_tiempo_respuesta': 'Utilidad: Tiempo de respuesta',
        'utilidad_claridad': 'Utilidad: Claridad, precisión y facilidad de uso',
        'relevancia_periodicidad': 'Relevancia: Correspondencia de periodicidad',
        'relevancia_concordancia': 'Relevancia: Concordancia entre lo solicitado y entregado',
        'accesibilidad_canal': 'Accesibilidad: Canal de solicitud',
        'accesibilidad_formato': 'Accesibilidad: Formato de entrega',
    }
    
    # INDICADOR 1: Porcentaje de satisfacción por variable y categoría (SV)
    indicador_sv = {}
    respuestas_completas_todas = RespuestaSatisfaccionCompleta.objects.filter(organismo=organismo)
    
    for campo, nombre in variables.items():
        total_var = respuestas_completas_todas.filter(**{f'{campo}__isnull': False}).count()
        if total_var > 0:
            distribucion = {}
            for categoria in range(1, 6):
                count = respuestas_completas_todas.filter(**{campo: categoria}).count()
                porcentaje = (count / total_var) * 100
                distribucion[categoria] = {
                    'count': count,
                    'porcentaje': round(porcentaje, 2)
                }
            indicador_sv[campo] = {
                'nombre': nombre,
                'total': total_var,
                'distribucion': distribucion
            }
    
    # INDICADOR 2: Índice Neto de Satisfacción por Dimensión (INSD)
    indicador_insd = {}
    
    dimensiones_campos = {
        'Utilidad': ['utilidad_tiempo_respuesta', 'utilidad_claridad'],
        'Relevancia': ['relevancia_periodicidad', 'relevancia_concordancia'],
        'Accesibilidad': ['accesibilidad_canal', 'accesibilidad_formato']
    }
    
    for dimension, campos in dimensiones_campos.items():
        total_dimension = 0
        satisfechas = 0
        no_satisfechas = 0
        
        for campo in campos:
            satisfechas += respuestas_completas_todas.filter(**{f'{campo}__in': [4, 5]}).count()
            no_satisfechas += respuestas_completas_todas.filter(**{f'{campo}__in': [1, 2, 3]}).count()
            total_dimension += respuestas_completas_todas.filter(**{f'{campo}__isnull': False}).count()
        
        if total_dimension > 0:
            diferencia = satisfechas - no_satisfechas
            insd_valor = abs(diferencia) / total_dimension * 100
            percepcion = 'positiva' if diferencia > 0 else 'negativa' if diferencia < 0 else 'neutral'
            
            indicador_insd[dimension] = {
                'satisfechas': satisfechas,
                'no_satisfechas': no_satisfechas,
                'total': total_dimension,
                'diferencia': diferencia,
                'insd': round(insd_valor, 2),
                'percepcion': percepcion
            }
    
    # INDICADOR 3: Índice Neto de Satisfacción Global (INSG)
    total_global = 0
    satisfechas_global = 0
    no_satisfechas_global = 0
    
    for campos in dimensiones_campos.values():
        for campo in campos:
            satisfechas_global += respuestas_completas_todas.filter(**{f'{campo}__in': [4, 5]}).count()
            no_satisfechas_global += respuestas_completas_todas.filter(**{f'{campo}__in': [1, 2, 3]}).count()
            total_global += respuestas_completas_todas.filter(**{f'{campo}__isnull': False}).count()
    
    if total_global > 0:
        diferencia_global = satisfechas_global - no_satisfechas_global
        insg_valor = abs(diferencia_global) / total_global * 100
        percepcion_global = 'positiva' if diferencia_global > 0 else 'negativa' if diferencia_global < 0 else 'neutral'
        
        indicador_insg = {
            'satisfechas': satisfechas_global,
            'no_satisfechas': no_satisfechas_global,
            'total': total_global,
            'diferencia': diferencia_global,
            'insg': round(insg_valor, 2),
            'percepcion': percepcion_global
        }
    else:
        indicador_insg = None
    
    return render(request, 'indicadores/organismo_detalle.html', {
        'page': 'hall_capacidad',
        'organismo': organismo,
        'indicadores': indicadores,
        'sesiones': sesiones,
        'respuestas_rapidas': respuestas_rapidas,
        'respuestas_completas': respuestas_completas,
        'flujos_recibe': flujos_recibe,
        'flujos_envia': flujos_envia,
        'metricas': metricas,
        'distribucion_calificaciones': distribucion_calificaciones,
        # Indicadores específicos de satisfacción
        'indicador_sv': indicador_sv,
        'indicador_insd': indicador_insd,
        'indicador_insg': indicador_insg,
    })


# ========================================
# FUNCIONES AUXILIARES PARA MÉTRICAS DEL ECOSISTEMA
# ========================================

def calcular_indice_madurez_ecosistema(organismo):
    """
    Índice 0-100 de madurez del ecosistema de datos del organismo,
    calculado sobre los datos del taller de gestión de datos institucionales (F1/F2/F3):
      D1: inscripciones completadas (25 pts)
      D2: fuentes de datos caracterizadas (25 pts)
      D3: retos de análisis formulados (25 pts)
      D4: fuentes con evaluación de seguridad (25 pts)
    """
    from .models_taller import InscripcionTaller
    from .models_catalogo import FuenteDatos, EvaluacionSeguridad

    inscripciones = InscripcionTaller.objects.filter(organismo=organismo)
    if not inscripciones.exists():
        return 0

    total_insc = inscripciones.count()
    completadas = inscripciones.filter(estado='completada').count()
    fuentes = FuenteDatos.objects.filter(inscripcion__organismo=organismo)
    retos = inscripciones.filter(reto__isnull=False).count()
    evaluadas = fuentes.filter(seguridad__isnull=False).count()

    d1 = (completadas / total_insc) * 25
    d2 = min(fuentes.count() / 5, 1) * 25      # meta: 5 fuentes caracterizadas
    d3 = min(retos / 3, 1) * 25                # meta: 3 retos formulados
    d4 = (evaluadas / fuentes.count()) * 25 if fuentes.count() else 0

    return round(d1 + d2 + d3 + d4, 1)


def obtener_roles_identificados(organismo):
    """Distribución de fuentes del organismo por rol (productor/usuario/ambos)."""
    from .models_catalogo import FuenteDatos

    roles = FuenteDatos.objects.filter(
        inscripcion__organismo=organismo
    ).exclude(rol='').values('rol').annotate(count=Count('id'))

    return {r['rol']: r['count'] for r in roles}


def obtener_flujos_internos(organismo):
    """Fuentes con origen declarado dentro del mismo organismo."""
    from .models_catalogo import FuenteOrigen

    return FuenteOrigen.objects.filter(
        fuente__inscripcion__organismo=organismo,
        organismo_productor__icontains=organismo.nombre.split()[0],
    ).count()


def obtener_flujos_externos(organismo):
    """Fuentes de origen externas declaradas por el organismo."""
    from .models_catalogo import FuenteOrigen

    return FuenteOrigen.objects.filter(
        fuente__inscripcion__organismo=organismo
    ).exclude(
        organismo_productor__icontains=organismo.nombre.split()[0]
    ).count()


def calcular_densidad_red(organismo):
    """Porcentaje de fuentes caracterizadas que declaran fuentes de origen."""
    from .models_catalogo import FuenteDatos

    fuentes = FuenteDatos.objects.filter(inscripcion__organismo=organismo)
    total = fuentes.count()
    if not total:
        return 0
    con_origen = fuentes.filter(fuentes_origen__isnull=False).distinct().count()
    return round((con_origen / total) * 100, 1)


def obtener_diversidad_datos(organismo):
    """Distribución de fuentes evaluadas por criticidad de seguridad (verde/amarillo/rojo)."""
    from .models_catalogo import EvaluacionSeguridad

    distribucion = EvaluacionSeguridad.objects.filter(
        fuente__inscripcion__organismo=organismo
    ).values('criticidad').annotate(count=Count('id'))

    resultado = {'verde': 0, 'amarillo': 0, 'rojo': 0}
    for item in distribucion:
        nivel = (item['criticidad'] or '').lower()
        if nivel in resultado:
            resultado[nivel] = item['count']

    return resultado


# ============================================================================
# ENDPOINTS AJAX PARA EL WIZARD UNIFICADO
# ============================================================================

from django.http import JsonResponse
from django.views.decorators.http import require_POST

@login_required
@require_POST
def api_contar_series_grafico(request):
    """
    Endpoint AJAX: recibe dominios seleccionados y devuelve estimación
    de cuántas GraficoSerie se generarían.
    """
    from .utils_wizard import estimar_series_grafico
    import json

    try:
        body = json.loads(request.body)
        dominios_geo = body.get('dominios_geo', [])
        dominios_tem = body.get('dominios_tem', [])
        resultado = estimar_series_grafico(dominios_geo, dominios_tem)
        return JsonResponse(resultado)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def api_validar_datos(request):
    """
    Endpoint AJAX: valida un archivo de datos CSV/XLSX y retorna
    errores, warnings e información detectada.

    POST params (JSON):
        carga_id: int
        tipo_carga: 'serie' | 'conjunto_datos'

    Response (JSON):
        {
            errores: [{codigo, severidad, mensaje, detalle}],
            warnings: [{codigo, severidad, mensaje, detalle}],
            info: [{codigo, severidad, mensaje, detalle}],
            bloqueado: bool,
            resumen: {filas, columnas, total_errores, total_warnings, total_info}
        }
    """
    from .utils_wizard import ValidadorDatos
    from .models import CargaSerieIndicador, CargaConjuntoDatos
    import json
    import pandas as pd

    try:
        body = json.loads(request.body)
        carga_id = body.get('carga_id')
        tipo_carga = body.get('tipo_carga', 'serie')

        if tipo_carga == 'serie':
            carga = CargaSerieIndicador.objects.get(id=carga_id)
            path = carga.archivo_datos_csv.path if carga.archivo_datos_csv else carga.archivo_datos_xlsx.path
        else:
            carga = CargaConjuntoDatos.objects.get(id=carga_id)
            path = carga.archivo_microdata_xlsx.path

        if path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(path)
        else:
            df = pd.read_csv(path)

        validador = ValidadorDatos(df)
        resultado = validador.validar_todo()
        return JsonResponse(resultado)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ========================================
# CALENDARIO DE DIFUSIÓN ESTADÍSTICA
# ========================================

def calendario_difusion(request):
    """
    Vista pública del Calendario de Difusión Estadística.
    Muestra los productos estadísticos por organismo con fechas de publicación.
    """
    from django.db.models import Count
    from .models import CalendarioDifusion

    # Obtener todos los productos activos
    productos = CalendarioDifusion.objects.filter(activo=True).select_related('organismo').order_by('organismo__nombre', 'observatorio', 'producto')

    # Agrupar por organismo
    organismos_data = {}
    for producto in productos:
        org_id = producto.organismo.id
        if org_id not in organismos_data:
            organismos_data[org_id] = {
                'organismo': producto.organismo,
                'productos': [],
                'observatorios': set(),
            }
        organismos_data[org_id]['productos'].append(producto)
        if producto.observatorio:
            organismos_data[org_id]['observatorios'].add(producto.observatorio.strip())

    # Calcular estadísticas globales
    stats_globales = {
        'total_organismos': len(organismos_data),
        'total_productos': productos.count(),
        'total_observatorios': len(set(p.observatorio.strip() for p in productos if p.observatorio)),
    }

    # Conteo por periodicidad
    periodicidad_counts = {}
    for p in productos:
        periodicidad_counts[p.get_periodicidad_display()] = periodicidad_counts.get(p.get_periodicidad_display(), 0) + 1

    return render(request, 'indicadores/calendario_difusion.html', {
        'page': 'calendario_difusion',
        'organismos_data': organismos_data.values(),
        'stats_globales': stats_globales,
        'periodicidad_counts': periodicidad_counts,
    })


# ========================================
# MÓDULO ICED PÚBLICO
# ========================================

def modulo_iced(request):
    """
    Vista pública del módulo ICED.
    Muestra todos los organismos con su puntaje ICED en un gráfico de barras
    y permite desplegar los detalles de cada organismo.
    """
    from django.db.models import Count
    from .models import Organismo
    from .models_iced import ICEDFormulario
    from .calcular_iced import INDICADOR_LABELS, calcular_iced

    organismos = Organismo.objects.filter(activo=True).annotate(
        total_indicadores=Count('indicadores_responsables', distinct=True),
    ).order_by('nombre')

    organismos_con_iced = []
    for organismo in organismos:
        # Solo consolidados: los formularios por equipo son parciales.
        ficed = ICEDFormulario.objects.filter(
            organismo=organismo,
            equipo='',
            estado__in=['validado', 'enviado']
        ).order_by('-periodo').first()

        if ficed:
            puntajes = calcular_iced(ficed)
            organismo.ficed = ficed
            # puntaje_global puede ser None si el formulario fue enviado sin
            # recalcular; usar el valor calculado en vivo (escala 0-100)
            if ficed.puntaje_global is not None:
                organismo.puntaje_global_pct = int(ficed.puntaje_global * 100)
            else:
                organismo.puntaje_global_pct = int(puntajes['puntaje_global'])
            organismo.nivel_global_display = ficed.nivel_global_display
            organismo.periodo = ficed.periodo
            organismo.puntajes_detalle = puntajes
            organismos_con_iced.append(organismo)

    # Calcular estadísticas globales
    total_organismos = len(organismos_con_iced)
    promedio_global = sum(o.puntaje_global_pct for o in organismos_con_iced) / total_organismos if total_organismos else 0
    organismos_alto = sum(1 for o in organismos_con_iced if o.puntaje_global_pct >= 75)
    organismos_medio = sum(1 for o in organismos_con_iced if 60 <= o.puntaje_global_pct < 75)
    organismos_bajo = sum(1 for o in organismos_con_iced if o.puntaje_global_pct < 60)

    stats_globales = {
        'total_organismos': total_organismos,
        'promedio_global': round(promedio_global, 1),
        'organismos_alto': organismos_alto,
        'organismos_medio': organismos_medio,
        'organismos_bajo': organismos_bajo,
    }

    return render(request, 'indicadores/modulo_iced.html', {
        'page': 'modulo_iced',
        'organismos': organismos_con_iced,
        'stats_globales': stats_globales,
        'iced_indicador_labels': INDICADOR_LABELS,
    })


# ============================================================================
# CATÁLOGOS DE DATOS POR DOMINIO
# ============================================================================

def catalogos_dominios(request):
    """
    Lista los dominios de desagregación que tienen catálogos de datos activos
    (directorios de referencia: hospitales, teatros, colegios, etc.).
    """
    dominios = (
        DominioDesagregacion.objects
        .filter(catalogos__activo=True)
        .prefetch_related('catalogos')
        .distinct()
        .order_by('nombre')
    )
    dominios_data = [
        {
            'dominio': d,
            'catalogos': [c for c in d.catalogos.all() if c.activo],
        }
        for d in dominios
    ]
    return render(request, 'indicadores/catalogos_dominios.html', {
        'page': 'catalogos',
        'dominios_data': dominios_data,
    })


def catalogo_detalle(request, pk):
    """
    Muestra un catálogo de dominio: vista previa en tabla (primeras filas)
    y enlace de descarga del archivo original.
    """
    catalogo = get_object_or_404(
        CatalogoDominio.objects.select_related('dominio'),
        pk=pk, activo=True
    )

    columnas = []
    filas = []
    total_filas = 0
    error_lectura = None
    MAX_PREVIEW = 200

    if catalogo.archivo:
        try:
            from .views_recoleccion import _leer_archivo_datos
            df = _leer_archivo_datos(catalogo.archivo.path)
            total_filas = len(df)
            columnas = [str(c) for c in df.columns]
            filas = (
                df.head(MAX_PREVIEW)
                .fillna('')
                .astype(str)
                .values
                .tolist()
            )
        except Exception:
            logger.exception('Error leyendo catálogo %s', catalogo.pk)
            error_lectura = 'No fue posible leer el archivo del catálogo.'

    return render(request, 'indicadores/catalogo_detalle.html', {
        'page': 'catalogos',
        'catalogo': catalogo,
        'columnas': columnas,
        'filas': filas,
        'total_filas': total_filas,
        'filas_mostradas': len(filas),
        'error_lectura': error_lectura,
    })


# ============================================================================
# CATÁLOGO DE CONSULTA (vista pública)
# ============================================================================

def catalogo_consulta_listado(request):
    """
    Listado público del catálogo de consulta: conjuntos activos agrupados
    bajo los dominios visibles del menú de indicadores (los 4 activos).
    """
    dominios = MenuDominio.objects.filter(activo=True).prefetch_related(
        'catalogos_consulta'
    ).order_by('orden', 'nombre')

    dominios_data = []
    for dominio in dominios:
        conjuntos = [c for c in dominio.catalogos_consulta.all() if c.activo]
        if conjuntos:
            dominios_data.append({'dominio': dominio, 'conjuntos': conjuntos})

    return render(request, 'indicadores/catalogo_consulta_listado.html', {
        'page': 'catalogo_consulta',
        'dominios_data': dominios_data,
    })


def catalogo_consulta_detalle(request, pk):
    """
    Detalle de un conjunto del catálogo de consulta: tabla con buscador,
    descarga del archivo fuente e indicadores enlazados.
    """
    conjunto = get_object_or_404(
        CatalogoConsulta.objects.select_related('dominio').prefetch_related(
            'indicadores_enlazados__subtema__tema__dominio'
        ),
        pk=pk, activo=True,
    )

    busqueda = (request.GET.get('q') or '').strip()
    filas = conjunto.filas or []
    if busqueda:
        term = busqueda.lower()
        filas = [
            f for f in filas
            if any(term in str(v).lower() for v in f.values() if v is not None)
        ]

    paginador = Paginator(filas, 50)
    pagina = paginador.get_page(request.GET.get('pagina'))

    indicadores_enlazados = [i for i in conjunto.indicadores_enlazados.all() if i.activo]

    # Filas como listas de valores alineadas al orden de `columnas`
    columnas = conjunto.columnas or []
    pagina_valores = [[f.get(col) for col in columnas] for f in pagina]

    return render(request, 'indicadores/catalogo_consulta_detalle.html', {
        'page': 'catalogo_consulta',
        'conjunto': conjunto,
        'columnas': columnas,
        'pagina': pagina,
        'pagina_valores': pagina_valores,
        'total_filas': len(filas),
        'busqueda': busqueda,
        'indicadores_enlazados': indicadores_enlazados,
    })


def modelo_datos(request):
    """
    Diagrama interactivo del modelo de datos.

    Introspecta el ORM en tiempo de ejecución (sin codegen): cada modelo es un
    nodo con sus campos, y cada FK/O2O/M2M una arista. Sirve como mapa guía de
    la arquitectura de datos de la plataforma.
    """
    FAMILIAS = {
        'indicadores.models': ('Núcleo SIIED', '#0284c7'),
        'indicadores.models_iced': ('ICED', '#d97706'),
        'indicadores.models_catalogo': ('Catálogo de datos', '#059669'),
        'indicadores.models_taller': ('Taller Ecosistema', '#9333ea'),
    }

    nodos = {}
    aristas = []

    modelos = list(apps.get_app_config('indicadores').get_models())
    for modelo in modelos:
        meta = modelo._meta
        familia, color = FAMILIAS.get(modelo.__module__, ('Otros', '#64748b'))

        campos = []
        for f in meta.get_fields():
            # Omitir accessors inversos (auto_created y no concretos)
            if getattr(f, 'auto_created', False) and not getattr(f, 'concrete', False):
                continue
            try:
                tipo = f.get_internal_type()
            except Exception:
                tipo = type(f).__name__
            campo = {
                'nombre': f.name,
                'tipo': tipo,
                'pk': bool(getattr(f, 'primary_key', False)),
                'nulo': bool(getattr(f, 'null', False)),
            }
            if getattr(f, 'is_relation', False) and f.related_model is not None:
                campo['destino'] = f.related_model._meta.label
            campos.append(campo)

        nodos[meta.label] = {
            'id': meta.label,
            'nombre': meta.object_name,
            'tabla': meta.db_table,
            'familia': familia,
            'color': color,
            'verbose': str(meta.verbose_name),
            'campos': campos,
        }

        for f in meta.get_fields():
            if getattr(f, 'auto_created', False) and not getattr(f, 'concrete', False):
                continue
            if not (f.many_to_one or f.one_to_one or f.many_to_many):
                continue
            destino = getattr(f, 'related_model', None)
            if destino is None:
                continue
            # Solo aristas hacia indicadores o auth.User (referencia externa)
            if destino._meta.app_label == 'indicadores':
                pass
            elif destino._meta.label == 'auth.User':
                pass
            else:
                continue
            aristas.append({
                'source': meta.label,
                'target': destino._meta.label,
                'campo': f.name,
                'tipo': 'M2M' if f.many_to_many else ('O2O' if f.one_to_one else 'FK'),
            })

    # auth.User como nodo externo si es referenciado
    if any(a['target'] == 'auth.User' for a in aristas):
        from django.contrib.auth.models import User
        nodos['auth.User'] = {
            'id': 'auth.User',
            'nombre': 'User',
            'tabla': User._meta.db_table,
            'familia': 'Usuarios',
            'color': '#475569',
            'verbose': 'usuario',
            'campos': [
                {'nombre': 'id', 'tipo': 'AutoField', 'pk': True, 'nulo': False},
                {'nombre': 'username', 'tipo': 'CharField', 'pk': False, 'nulo': False},
                {'nombre': 'email', 'tipo': 'EmailField', 'pk': False, 'nulo': False},
                {'nombre': 'is_staff', 'tipo': 'BooleanField', 'pk': False, 'nulo': False},
                {'nombre': 'is_active', 'tipo': 'BooleanField', 'pk': False, 'nulo': False},
                {'nombre': 'date_joined', 'tipo': 'DateTimeField', 'pk': False, 'nulo': False},
            ],
        }

    familias = []
    vistos = set()
    for n in nodos.values():
        clave = (n['familia'], n['color'])
        if clave not in vistos:
            vistos.add(clave)
            familias.append({'nombre': n['familia'], 'color': n['color']})

    total_campos = sum(len(n['campos']) for n in nodos.values())

    return render(request, 'indicadores/modelo_datos.html', {
        'page': 'modelo_datos',
        'modelo_nodos': list(nodos.values()),
        'modelo_aristas': aristas,
        'modelo_familias': familias,
        'stats': {
            'modelos': len(nodos),
            'relaciones': len(aristas),
            'campos': total_campos,
        },
    })


def presentacion(request):
    """
    Cinemática 3D "La Maquila de Datos" — página standalone de presentación.

    Escena estilo Tiempos Modernos: cinta transportadora, estaciones de
    máquina con nombres del modelo de datos real y Don Daticos operarios.
    """
    stats = {
        'modelos': len(list(apps.get_app_config('indicadores').get_models())),
        'indicadores': Indicador.objects.filter(activo=True).count(),
        'conjuntos': ConjuntoDatos.objects.filter(activo=True).count() if hasattr(ConjuntoDatos, 'activo') else ConjuntoDatos.objects.count(),
        'dominios': MenuDominio.objects.filter(activo=True).count(),
        'organismos': Organismo.objects.filter(activo=True).count() if hasattr(Organismo, 'activo') else Organismo.objects.count(),
    }
    return render(request, 'indicadores/presentacion.html', {'stats': stats})


def presentacion_slides(request):
    """
    Presentación del SIIED en diapositivas — versión "para proyectar y
    leer" del recorrido de la Maquila 3D: plataforma → portal público →
    censo de conjuntos → inventarios → roles → líneas de producción
    (D, C, E1-E3) → módulos administrativos → validación →
    administración → nivel estratégico → ciudadanía → código abierto.

    Pensada para audiencias y contextos donde el show 3D no aplica;
    comparte los mismos stats en vivo del sistema.
    """
    stats = {
        'modelos': len(list(apps.get_app_config('indicadores').get_models())),
        'indicadores': Indicador.objects.filter(activo=True).count(),
        'conjuntos': ConjuntoDatos.objects.filter(activo=True).count() if hasattr(ConjuntoDatos, 'activo') else ConjuntoDatos.objects.count(),
        'dominios': MenuDominio.objects.filter(activo=True).count(),
        'organismos': Organismo.objects.filter(activo=True).count() if hasattr(Organismo, 'activo') else Organismo.objects.count(),
    }
    return render(request, 'indicadores/presentacion_slides.html', {'stats': stats})


def documentacion(request):
    """
    Documentación open source de la plataforma: mapa del repositorio
    archivo por archivo, manuales de operación y acceso al modelo de
    datos. Las métricas del encabezado se calculan en VIVO sobre el
    código instalado — el documento nunca se desactualiza respecto
    al código que corre en el servidor.
    """
    from pathlib import Path

    app_dir = Path(__file__).resolve().parent

    def _lineas(archivos):
        total = 0
        for ruta in archivos:
            try:
                with open(ruta, 'r', encoding='utf-8', errors='ignore') as fh:
                    total += sum(1 for _ in fh)
            except OSError:
                pass
        return total

    # Descripción de cada carpeta de plantillas de la app
    DESC_CARPETAS = {
        'indicadores': 'Portal público: dominios, fichas de indicadores, gráficos, '
                       'páginas 3D, presentación y modelo de datos',
        'admin': 'Personalización del admin de Django para el equipo estadístico',
        'editorial': 'Línea editorial: noticias, eventos y productos académicos',
        'taller': 'Taller de gestión de datos institucionales: wizard del censo, dashboard y metodología',
        'recoleccion': 'Operación estadística de campo',
        'delegado': 'Módulo delegado por organismo',
        'validacion': 'Control de calidad de los datos',
        'reportes': 'Informes y reportes',
        'satisfaccion': 'Encuestas de satisfacción',
        'workspace': 'Área de trabajo interna',
    }

    stats_doc = {}
    carpetas_plantillas = []
    try:
        pys = [p for p in app_dir.glob('*.py') if p.is_file()]
        proyecto = [app_dir.parent / 'manage.py'] + \
            list((app_dir.parent / 'myproject').glob('*.py'))
        plantillas = list((app_dir / 'templates').rglob('*.html'))
        estaticos = [p for p in (app_dir / 'static').rglob('*') if p.is_file()]
        migraciones = [p for p in (app_dir / 'migrations').glob('*.py')
                       if p.name != '__init__.py']
        stats_doc = {
            'archivos_py': len(pys) + len(proyecto),
            'lineas_py': _lineas(pys) + _lineas(proyecto),
            'plantillas': len(plantillas),
            'lineas_plantillas': _lineas(plantillas),
            'estaticos': len(estaticos),
            'migraciones': len(migraciones),
        }
        for sub in (app_dir / 'templates').iterdir():
            if sub.is_dir():
                carpetas_plantillas.append({
                    'nombre': sub.name,
                    'cantidad': len(list(sub.rglob('*.html'))),
                    'descripcion': DESC_CARPETAS.get(
                        sub.name, 'Plantillas de la aplicación'),
                })
        carpetas_plantillas.sort(key=lambda c: -c['cantidad'])
    except OSError:
        pass

    return render(request, 'indicadores/documentacion.html', {
        'page': 'documentacion',
        'stats_doc': stats_doc,
        'carpetas_plantillas': carpetas_plantillas,
    })
