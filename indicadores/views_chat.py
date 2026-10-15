
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
from django.conf import settings
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
from .embeddings import EmbeddingService, get_embedding_service
from .models import (
    MenuDominio, MenuTema, MenuSubtema, Indicador, Dato,
    Desagregacion, DominioDesagregacion, NivelGeografico, CapaGeo, ElementoGeo,
    CategoriaInformacion, SistemaInformacion, CategoriaProyecto, ProyectoInformacion,
    NoticiaBanner, AreaInfraestructura, CategoriaInfraestructura, SubcategoriaInfraestructura,
    GrupoDocumento, DocumentoInfraestructura, Grafico, GraficoSerie, Aliado, Evento,
    DocumentoVector, ConjuntoDatos, OperacionEstadistica, ProcesoExtraccion, ProcesoLog,
    ProductoAcademico, SeccionPaper, Organismo, Suborganismo, EquipoOrganismo,
    RespuestaSatisfaccionRapida, RespuestaSatisfaccionCompleta,
    InscripcionTaller, FuenteDatos, RetoAnalisis, EvaluacionSeguridad,
    VariableConjuntoDatos, CatalogoConsulta,
)
from .models_iced import ICEDFormulario
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

logger = logging.getLogger(__name__)


class CerebrasToolsService:
    def __init__(self, api_key: str, base_url: str = None, request=None):
        self.api_key = api_key
        # Obtener base_url dinámicamente si se proporciona request
        if request:
            # Construir URL base sin duplicar /proxy.php/
            # Usar get_host() para obtener el host correcto (incluso detrás de proxy)
            scheme = 'https' if request.is_secure() else 'http'
            host = request.get_host()
            self.base_url = f"{scheme}://{host}"
        else:
            self.base_url = base_url or get_config('TOOLS_FALLBACK_BASE_URL', 'http://127.0.0.1:8000')
        self.client = None
        self.logger = logging.getLogger('indicadores.tools')
        # Usar OpenAI SDK con endpoint de Cerebras
        self.client = OpenAI(
            api_key=api_key,
            base_url=get_config('CEREBRAS_BASE_URL', 'https://api.cerebras.ai/v1')
        )
        self.logger.info("CerebrasToolsService inicializado correctamente")

    # ====================================================================
    # HELPERS
    # ====================================================================

    def _rag_hybrid_search(self, consulta: str, tipo_doc: str, qs, text_filter_fields: list, umbral: float = 0.3, top_k_semantic: int = 20):
        """
        Búsqueda híbrida: primero semántica (RAG) en DocumentoVector, luego fallback a texto.
        Devuelve el queryset filtrado y ordenado. Si no hay consulta, devuelve qs sin cambios.
        """
        if not consulta:
            return qs

        try:
            search_service = SemanticSearch()
            resultados_sem = search_service.buscar_similar(
                consulta=consulta,
                tipo_doc=tipo_doc,
                top_k=top_k_semantic,
                umbral=umbral
            )
            if resultados_sem:
                ref_ids = [r['referencia_id'] for r in resultados_sem if r.get('referencia_id')]
                if ref_ids:
                    # Preservar orden de relevancia semántica usando Case/When
                    from django.db.models import Case, When, IntegerField, Value
                    preserved_order = Case(
                        *[When(id=pk, then=Value(pos)) for pos, pk in enumerate(ref_ids)],
                        default=Value(len(ref_ids)),
                        output_field=IntegerField()
                    )
                    return qs.filter(id__in=ref_ids).order_by(preserved_order)
        except Exception as e:
            self.logger.warning(f"RAG falló para {tipo_doc}: {e}")

        # Fallback a búsqueda de texto
        text_q = Q()
        for field in text_filter_fields:
            text_q |= Q(**{f"{field}__icontains": consulta})
        return qs.filter(text_q)

    def _build_absolute_url(self, relative_or_reverse_url: str = None, obj=None, named_url: str = None, kwargs: dict = None) -> str:
        """Construye URL absoluta usando self.base_url. Soporta reverse() o path relativo."""
        try:
            if obj and hasattr(obj, 'get_absolute_url'):
                relative = obj.get_absolute_url()
            elif named_url:
                from django.urls import reverse
                relative = reverse(named_url, kwargs=kwargs or {})
            else:
                relative = relative_or_reverse_url or ''
            if relative and self.base_url:
                base = self.base_url.rstrip('/')
                rel = relative.lstrip('/')
                return f"{base}/{rel}"
            return relative or ''
        except Exception:
            return relative_or_reverse_url or ''

    def get_tools_definition(self):
        """Define herramientas optimizadas solo para consulta de indicadores y conjunto_datos"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "buscar_indicadores",
                    "description": "Busca indicadores por nombre, tema o palabras clave. Usa esta herramienta cuando el usuario pregunte por datos estadísticos específicos, indicadores de cualquier tema (educación, salud, economía, seguridad, etc.), o cuando mencione términos como 'cuántos', 'cuál es el valor', 'estadísticas de', 'datos de', 'indicadores de'. Devuelve indicadores activos con sus metadatos básicos.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "consulta": {
                                "type": "string",
                                "description": "Términos de búsqueda: nombre del indicador, tema, o palabras clave relacionadas"
                            },
                            "limite": {
                                "type": "integer",
                                "default": 10,
                                "description": "Máximo de indicadores a devolver (1-20)"
                            }
                        },
                        "required": ["consulta"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "consultar_indicador",
                    "description": "Obtiene datos completos de un indicador específico incluyendo valores históricos, metadatos, desagregaciones disponibles y últimas cifras. Usa esta herramienta cuando el usuario pregunte por valores específicos, series históricas, o después de buscar indicadores para profundizar en uno concreto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "indicador_id": {
                                "type": "integer",
                                "description": "ID numérico del indicador a consultar"
                            },
                            "año_inicio": {
                                "type": "integer",
                                "description": "Año inicial para filtrar datos (opcional)"
                            },
                            "año_fin": {
                                "type": "integer",
                                "description": "Año final para filtrar datos (opcional)"
                            },
                            "limite": {
                                "type": "integer",
                                "default": 100,
                                "description": "Máximo de registros de datos a devolver (1-500)"
                            }
                        },
                        "required": ["indicador_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "obtener_matriz_indicador",
                    "description": "Obtiene matriz completa de datos de un indicador: filas=observaciones, columnas=[año, valor, desagregacion_geo, desagregacion_tematica]. Usar cuando el usuario quiera analizar tendencias, comparar desagregaciones, o hacer cálculos personalizados. La IA realizará el análisis sobre estos datos brutos.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "indicador_id": {
                                "type": "integer",
                                "description": "ID del indicador"
                            },
                            "año_inicio": {
                                "type": "integer",
                                "description": "Año inicial (opcional)"
                            },
                            "año_fin": {
                                "type": "integer",
                                "description": "Año final (opcional)"
                            },
                            "incluir_desagregaciones": {
                                "type": "boolean",
                                "default": True,
                                "description": "Incluir columnas de desagregación"
                            }
                        },
                        "required": ["indicador_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "obtener_matriz_conjunto_datos",
                    "description": "Obtiene muestra de matriz de conjunto_datos en formato CSV-like compacto: filas=registros, columnas=variables. Usar cuando el usuario quiera explorar datos individuales, hacer análisis estadístico, o cruzar variables. Retorna máximo 1000 registros para eficiencia de tokens. La IA analizará la distribución, frecuencias, y patrones.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "conjunto_datos_id": {
                                "type": "integer",
                                "description": "ID del conjunto de conjunto_datos"
                            },
                            "variables": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Lista de variables específicas a incluir (opcional, por defecto todas)"
                            },
                            "muestra": {
                                "type": "integer",
                                "default": 500,
                                "description": "Número máximo de registros (10-1000)"
                            }
                        },
                        "required": ["conjunto_datos_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "listar_variables_conjunto_datos",
                    "description": "Lista variables disponibles en un conjunto de conjunto_datos con sus metadatos: nombre, tipo, definición. Usar ANTES de solicitar la matriz para conocer qué variables están disponibles.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "conjunto_datos_id": {
                                "type": "integer",
                                "description": "ID del conjunto de conjunto_datos"
                            }
                        },
                        "required": ["conjunto_datos_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "explorar_estructura",
                    "description": "Explora la estructura jerárquica del SIIED: dominios → temas → subtemas. Usar cuando el usuario pregunte QUÉ dominios, temas o categorías estadísticas existen, qué información hay disponible, o quiera navegar la estructura del sistema antes de buscar indicadores concretos. Es la herramienta correcta para '¿qué dominios/temas hay?', NO buscar_indicadores.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "nivel": {
                                "type": "string",
                                "enum": ["dominios", "temas", "subtemas", "completa"],
                                "default": "dominios",
                                "description": "Nivel a explorar: 'dominios' lista dominios, 'temas' lista temas (opcionalmente de un dominio), 'subtemas' lista subtemas, 'completa' devuelve la jerarquía dominio→tema→subtema"
                            },
                            "dominio_id": {
                                "type": "integer",
                                "description": "Filtrar temas/subtemas de un dominio específico (opcional)"
                            },
                            "tema_id": {
                                "type": "integer",
                                "description": "Filtrar subtemas de un tema específico (opcional)"
                            },
                            "incluir_indicadores": {
                                "type": "boolean",
                                "default": False,
                                "description": "Si true, incluye el conteo de indicadores por subtema"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "explorar_microdatos",
                    "description": "Lista los conjuntos de conjuntos_datos disponibles en el SIIED (encuestas/registros con datos a nivel de registro individual). Usar cuando el usuario pregunte qué conjuntos_datos o conjuntos de datos existen, o para encontrar el ID de un conjunto antes de usar obtener_matriz_conjunto_datos/listar_variables_conjunto_datos.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "accion": {
                                "type": "string",
                                "enum": ["listar", "explorar"],
                                "default": "listar",
                                "description": "'listar' devuelve los conjuntos de conjuntos_datos activos; 'explorar' detalla un conjunto por nombre"
                            },
                            "conjunto_datos": {
                                "type": "string",
                                "description": "Nombre del conjunto a explorar (solo con accion='explorar')"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analizar_comparativo",
                    "description": "Compara varios indicadores entre sí: estadísticas básicas por indicador para análisis temporal o cruzado. Usar cuando el usuario pida comparar indicadores, evolución entre periodos o contrastes entre temas. Requiere los IDs de los indicadores (obtenidos con buscar_indicadores).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "indicadores_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Lista de IDs de indicadores a comparar (2-10)"
                            },
                            "tipo_analisis": {
                                "type": "string",
                                "enum": ["temporal", "cruzado", "ranking"],
                                "default": "temporal",
                                "description": "Tipo de comparación"
                            }
                        },
                        "required": ["indicadores_ids"]
                    }
                }
            },
            # ================================================================
            # NUEVAS HERRAMIENTAS — Módulos extendidos de la plataforma
            # ================================================================
            {
                "type": "function",
                "function": {
                    "name": "consultar_iced",
                    "description": "Consulta el Índice de Capacidad Estadística y de Datos (ICED) de los organismos de la Alcaldía de Cali. El ICED mide la capacidad estadística en 4 dimensiones: Entorno Institucional, Infraestructura, Metodología Estadística y Accesibilidad. Cada dimensión pesa 25%. Escala 0-100%. Usar cuando pregunten por ICED, capacidad estadística, fortalezas/debilidades de un organismo, o comparaciones entre organismos.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "organismo": {
                                "type": "string",
                                "description": "Nombre o código del organismo (opcional, si vacío devuelve ranking general)"
                            },
                            "periodo": {
                                "type": "string",
                                "description": "Período/vigencia a consultar (ej: '2025'). Si vacío, devuelve el más reciente"
                            },
                            "incluir_subdimensiones": {
                                "type": "boolean",
                                "default": False,
                                "description": "Si true, incluye puntajes por subdimensión e indicador individual"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "consultar_ecosistema_datos",
                    "description": "Consulta información del ecosistema de datos de un organismo levantada en el taller de gestión de datos institucionales (fichas F1/F2/F3). Incluye: fuentes de datos caracterizadas, rol del organismo frente a cada fuente, retos de análisis propuestos y valoración de seguridad/privacidad por criticidad. NO revela nombres ni datos personales de los diligenciantes. Usar cuando pregunten por ecosistema de datos, catálogo de datos, fuentes de información, retos de análisis o la estructura de producción de datos de un organismo.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "organismo": {
                                "type": "string",
                                "description": "Nombre o código del organismo"
                            },
                            "aspecto": {
                                "type": "string",
                                "enum": ["resumen", "fuentes", "retos", "seguridad"],
                                "default": "resumen",
                                "description": "Qué aspecto del ecosistema consultar: resumen general, fuentes de datos caracterizadas, retos de análisis, o valoración de seguridad"
                            }
                        },
                        "required": ["organismo"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "consultar_producto_academico",
                    "description": "Busca y consulta los productos académicos (papers, documentos de investigación) publicados en el SIIED. Incluyen metodologías, resultados, análisis y documentación sobre indicadores y operaciones estadísticas. Usar cuando pregunten por investigaciones, publicaciones, papers, metodologías documentadas, o producción académica del SIIED.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "consulta": {
                                "type": "string",
                                "description": "Términos de búsqueda por título, resumen o palabras clave (opcional)"
                            },
                            "producto_id": {
                                "type": "integer",
                                "description": "ID de un producto específico para obtener detalle completo (opcional)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "buscar_documentos_infraestructura",
                    "description": "Busca documentos de la infraestructura estadística del SIIED: normas, estándares, lineamientos técnicos, metodologías, guías, manuales y formatos. Organizados en 5 niveles: Área → Categoría → Subcategoría → Grupo → Documento. Usar cuando pregunten por lineamientos, normas, estándares, guías metodológicas, formatos, o documentación técnica del sistema estadístico.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "consulta": {
                                "type": "string",
                                "description": "Términos de búsqueda por nombre, contenido o palabras clave"
                            },
                            "area": {
                                "type": "string",
                                "description": "Filtrar por área específica (ej: 'Normas y estándares')"
                            },
                            "tipo_documento": {
                                "type": "string",
                                "enum": ["proceso", "subproceso", "procedimiento", "herramienta", "metodologia", "guia", "manual", "formato", "otro"],
                                "description": "Filtrar por tipo de documento"
                            },
                            "limite": {
                                "type": "integer",
                                "default": 10,
                                "description": "Máximo de documentos a devolver"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "consultar_sistemas_informacion",
                    "description": "Lista los sistemas de consulta y los proyectos de información (productos) disponibles en el SIIED y otras dependencias de la Alcaldía. Incluye visualizadores, observatorios, sistemas sectoriales, aplicaciones web y herramientas de consulta. Usar cuando pregunten por herramientas disponibles, sistemas de información, observatorios, dónde consultar datos, qué aplicaciones hay, o qué productos de información ofrece la Alcaldía.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tipo": {
                                "type": "string",
                                "enum": ["sistemas", "productos", "todos"],
                                "default": "todos",
                                "description": "'sistemas' para Sistemas de Consulta, 'productos' para Proyectos de Información, 'todos' para ambos"
                            },
                            "consulta": {
                                "type": "string",
                                "description": "Búsqueda por nombre o descripción (opcional)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "consultar_operaciones_estadisticas",
                    "description": "Consulta las operaciones estadísticas (OOEE) registradas en el sistema: encuestas, registros administrativos, censos y demás procesos de producción estadística. Incluye organismo responsable, periodicidad, metodología, indicadores derivados, y enlaces al Archivo Distrital de Datos (ADDA) y al Archivo de conjunto_datos (AMDA) cuando estén disponibles. Usar cuando pregunten por operaciones estadísticas, encuestas, registros administrativos, fuentes de datos, o producción estadística de un organismo.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "consulta": {
                                "type": "string",
                                "description": "Búsqueda por nombre, tema o descripción de la operación"
                            },
                            "organismo": {
                                "type": "string",
                                "description": "Filtrar por organismo productor"
                            },
                            "limite": {
                                "type": "integer",
                                "default": 15,
                                "description": "Máximo de resultados"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "consultar_satisfaccion",
                    "description": "Consulta estadísticas de satisfacción ciudadana por organismo de la Alcaldía. Incluye promedio de calificación (1-5), distribución de respuestas, tendencia temporal y número de evaluaciones. Los datos son anónimos y agregados. Usar cuando pregunten por satisfacción ciudadana, calidad del servicio, calificaciones de dependencias, o percepción de los ciudadanos.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "organismo": {
                                "type": "string",
                                "description": "Nombre o código del organismo (opcional, si vacío devuelve resumen general)"
                            },
                            "periodo_meses": {
                                "type": "integer",
                                "default": 12,
                                "description": "Período en meses hacia atrás para calcular estadísticas (1-36)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "buscar_catalogo_consulta",
                    "description": "Busca conjuntos del Catálogo de Consulta: directorios y listados de referencia del distrito (teatros, museos, bibliotecas, hoteles, plazas de mercado, oficinas bancarias, inspecciones de policía, nomencladores de barrios/veredas, capacidad instalada, fichas territoriales). Usar cuando el usuario pregunte por DÓNDE está algo, QUÉ entidades existen, directorios, listados de establecimientos, códigos de barrios/veredas, o capacidad instalada — NO son series estadísticas. Devuelve los conjuntos con su id, tipo, dominio y número de registros.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "consulta": {
                                "type": "string",
                                "description": "Términos de búsqueda: tipo de establecimiento o listado (ej: 'teatros', 'hoteles', 'plazas de mercado', 'códigos de barrios')"
                            },
                            "limite": {
                                "type": "integer",
                                "default": 10,
                                "description": "Máximo de conjuntos a devolver (1-20)"
                            }
                        },
                        "required": ["consulta"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "consultar_catalogo_consulta",
                    "description": "Devuelve el cuadro de consulta completo de un conjunto del Catálogo de Consulta: columnas y filas (entidades, direcciones, teléfonos, códigos, capacidades). Usar después de buscar_catalogo_consulta para leer los datos del directorio/listado encontrado, o cuando el usuario pida 'listar', 'dame el directorio de', 'qué hoteles hay', etc. Soporta filtro de texto y límite de filas.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "conjunto_id": {
                                "type": "integer",
                                "description": "ID del conjunto del catálogo (obtenido de buscar_catalogo_consulta)"
                            },
                            "filtro": {
                                "type": "string",
                                "description": "Texto para filtrar filas (busca en todos los campos, ej: 'comuna 8', 'navarro')"
                            },
                            "limite": {
                                "type": "integer",
                                "default": 50,
                                "description": "Máximo de filas a devolver (1-200)"
                            }
                        },
                        "required": ["conjunto_id"]
                    }
                }
            }
        ]

    def _handle_buscar_indicadores_semantico(self, arguments: dict) -> Dict[str, Any]:
        """Maneja la búsqueda semántica de indicadores"""
        try:
            
            consulta = arguments.get('consulta', '').strip()
            indicadores_ids = arguments.get('indicadores_ids')  # NUEVO: IDs para filtrar

            raw_top_k = arguments.get('top_k', 50)
            try:
                top_k = int(raw_top_k)
            except (TypeError, ValueError):
                top_k = 50
            top_k = max(1, min(top_k, 200))

            raw_umbral = arguments.get('umbral_similitud', 0.4)
            try:
                umbral = float(raw_umbral)
            except (TypeError, ValueError):
                umbral = 0.4
            if not 0 <= umbral <= 1:
                umbral = 0.4
            
            if not consulta:
                return {"error": "La consulta no puede estar vacía"}
            
            # Inicializar el servicio de búsqueda semántica
            search_service = SemanticSearch()
            
            # Realizar la búsqueda (con filtro de IDs si se proporciona)
            resultados = search_service.buscar_similar(
                consulta=consulta,
                tipo_doc='indicador',
                top_k=top_k,
                umbral=umbral,
                referencia_ids=indicadores_ids  # NUEVO: Pasar filtro de IDs
            )
            
            if not resultados:
                return {"mensaje": "No se encontraron indicadores relevantes para la búsqueda."}
            
            # Obtener los IDs de los indicadores
            indicador_ids = [r['referencia_id'] for r in resultados]
            
            # Obtener los indicadores completos
            indicadores = Indicador.objects.filter(
                id__in=indicador_ids,
                activo=True
            ).select_related('subtema__tema__dominio')
            
            # Mapear para mantener el orden de relevancia
            indicadores_map = {ind.id: ind for ind in indicadores}
            resultados_formateados = []
            
            for res in resultados:
                if res['referencia_id'] in indicadores_map:
                    ind = indicadores_map[res['referencia_id']]
                    
                    # Extraer descripción desde descripcion_indicador
                    import re
                    desc_texto = 'Sin descripción'
                    if ind.descripcion_indicador:
                        desc_limpio = re.sub(r'<[^>]+>', '', str(ind.descripcion_indicador))
                        desc_texto = desc_limpio[:200] if len(desc_limpio) > 200 else desc_limpio
                    
                    dominio_slug = ind.subtema.tema.dominio.slug if ind.subtema and ind.subtema.tema and ind.subtema.tema.dominio else None
                    tema_slug = ind.subtema.tema.slug if ind.subtema and ind.subtema.tema else None
                    resultados_formateados.append({
                        'id': ind.id,
                        'nombre': ind.nombre,
                        'descripcion': desc_texto,
                        'tema': ind.subtema.tema.nombre if ind.subtema and ind.subtema.tema else None,
                        'dominio': ind.subtema.tema.dominio.nombre if ind.subtema and ind.subtema.tema and ind.subtema.tema.dominio else None,
                        'similitud': round(res['similitud'], 3),
                        'unidad_medida': getattr(ind, 'unidad_medida', '') or 'N/A',
                        'url': self._build_absolute_url(named_url='indicadores:tema_detalle_3d', kwargs={'dominio_slug': dominio_slug, 'tema_slug': tema_slug}) if dominio_slug and tema_slug else None,
                    })
            
            return {
                "success": True,
                "resultados": resultados_formateados,
                "total_resultados": len(resultados_formateados),
                "consulta": consulta
            }
            
        except Exception as e:
            self.logger.error(f"Error en búsqueda semántica: {str(e)}", exc_info=True)
            return {"error": f"Error en búsqueda semántica: {str(e)}"}

    def execute_tool_call(self, tool_call) -> Dict[str, Any]:
        """Ejecuta una llamada a herramienta específica"""
        try:
            function_name = tool_call.function.name
            
            # Parsear argumentos - manejar tanto dict como string JSON
            if isinstance(tool_call.function.arguments, dict):
                arguments = tool_call.function.arguments
            else:
                arguments = json.loads(tool_call.function.arguments)
            
            self.logger.info(f"Ejecutando herramienta: {function_name} con args: {arguments}")
            
            # Mapeo de herramientas a sus manejadores (datos en bruto para análisis por IA)
            handlers = {
                'buscar_indicadores': self._handle_buscar_indicadores,
                'consultar_indicador': self._handle_consultar_indicador,
                'explorar_estructura': self._handle_explorar_estructura,
                'analizar_comparativo': self._handle_analizar_comparativo,
                'explorar_microdatos': self._handle_explorar_microdatos,
                'obtener_matriz_indicador': self._handle_obtener_matriz_indicador,
                'obtener_matriz_conjunto_datos': self._handle_obtener_matriz_conjunto_datos,
                'listar_variables_conjunto_datos': self._handle_listar_variables_conjunto_datos,
                # Nuevas herramientas — módulos extendidos
                'consultar_iced': self._handle_consultar_iced,
                'consultar_ecosistema_datos': self._handle_consultar_ecosistema_datos,
                'consultar_producto_academico': self._handle_consultar_producto_academico,
                'buscar_documentos_infraestructura': self._handle_buscar_documentos_infraestructura,
                'consultar_sistemas_informacion': self._handle_consultar_sistemas_informacion,
                'consultar_operaciones_estadisticas': self._handle_consultar_operaciones_estadisticas,
                'consultar_satisfaccion': self._handle_consultar_satisfaccion,
                'buscar_catalogo_consulta': self._handle_buscar_catalogo_consulta,
                'consultar_catalogo_consulta': self._handle_consultar_catalogo_consulta,
            }
            
            handler = handlers.get(function_name)
            if not handler:
                return {"error": f"Herramienta no implementada: {function_name}"}
                
            result = handler(arguments)
            self.logger.info(f"Resultado de herramienta {function_name}: {type(result)} items")
            return result
            
        except Exception as e:
            self.logger.error(f"Error ejecutando herramienta {tool_call.function.name}: {str(e)}", exc_info=True)
            return {"error": f"Error ejecutando herramienta: {str(e)}"}


    def _handle_explorar_estructura(self, arguments: dict) -> Dict[str, Any]:
        """Maneja la exploración de la estructura jerárquica del SIIED"""
        try:
            
            nivel = (arguments.get('nivel') or 'dominios').lower()
            incluir_indicadores = bool(arguments.get('incluir_indicadores', False))

            dominio_id = arguments.get('dominio_id')
            tema_id = arguments.get('tema_id')

            try:
                dominio_id = int(dominio_id) if dominio_id is not None else None
            except (TypeError, ValueError):
                dominio_id = None

            try:
                tema_id = int(tema_id) if tema_id is not None else None
            except (TypeError, ValueError):
                tema_id = None
            
            # Estructura básica de respuesta
            response = {
                "success": True,
                "tipo": nivel,
                "total": 0,
                "datos": []
            }
            
            if nivel == 'dominios' or nivel == 'completa':
                # Solo información básica de dominios
                dominios = MenuDominio.objects.only(
                    'id', 'nombre', 'slug', 'descripcion', 'orden'
                ).order_by('orden')
                
                if nivel == 'dominios':
                    response["datos"] = [
                        {
                            "id": d.id,
                            "nombre": d.nombre,
                            "slug": d.slug,
                            "descripcion": d.descripcion,
                            "orden": d.orden,
                            "tipo": "dominio"
                        } for d in dominios
                    ]
                    response["total"] = len(dominios)
                    return response
                    
                # Si es 'completa', continuamos con la estructura jerárquica
                estructura = []
                for dominio in dominios:
                    dominio_data = {
                        "id": dominio.id,
                        "nombre": dominio.nombre,
                        "slug": dominio.slug,
                        "tipo": "dominio",
                        "temas": []
                    }
                    
                    # Obtener temas activos para este dominio
                    temas = MenuTema.objects.filter(
                        dominio=dominio,
                        activo=True
                    ).only('id', 'nombre', 'slug', 'descripcion', 'orden').order_by('orden')
                    
                    for tema in temas:
                        tema_data = {
                            "id": tema.id,
                            "nombre": tema.nombre,
                            "slug": tema.slug,
                            "tipo": "tema",
                            "subtemas": []
                        }
                        
                        # Obtener subtemas activos para este tema
                        subtemas = MenuSubtema.objects.filter(
                            tema=tema,
                            activo=True
                        ).only('id', 'nombre', 'slug', 'orden').order_by('orden')
                        
                        for subtema in subtemas:
                            subtema_data = {
                                "id": subtema.id,
                                "nombre": subtema.nombre,
                                "slug": subtema.slug,
                                "tipo": "subtema"
                            }
                            
                            # Si se solicita información de indicadores
                            if nivel == 'completa' and arguments.get('incluir_indicadores', False):
                                # Solo contamos los indicadores activos
                                # (subtema principal FK + adicionales M2M)
                                subtema_data["total_indicadores"] = subtema.indicadores_todos().count()
                                
                            tema_data["subtemas"].append(subtema_data)
                        
                        dominio_data["temas"].append(tema_data)
                    
                    estructura.append(dominio_data)
                
                response["datos"] = estructura
                response["total"] = len(estructura)
                return response
                
            elif nivel == 'temas':
                temas_qs = MenuTema.objects.filter(activo=True)
                if dominio_id is not None:
                    temas_qs = temas_qs.filter(dominio_id=dominio_id)
                if tema_id is not None:
                    temas_qs = temas_qs.filter(id=tema_id)

                temas_qs = temas_qs.select_related('dominio').order_by('orden')
                temas = list(temas_qs)

                if not temas:
                    response.update({
                        "success": False,
                        "error": "No se encontraron temas para los filtros proporcionados"
                    })
                    return response

                tema_ids = [tema.id for tema in temas]
                subtemas_qs = MenuSubtema.objects.filter(
                    tema_id__in=tema_ids,
                    activo=True
                ).order_by('orden')
                subtemas = list(subtemas_qs)

                subtemas_por_tema: Dict[int, List[Dict[str, Any]]] = {tid: [] for tid in tema_ids}

                subtema_ids = [sub.id for sub in subtemas]
                indicadores_por_subtema = {}
                if incluir_indicadores and subtema_ids:
                    counts = (
                        Indicador.objects
                        .filter(subtema_id__in=subtema_ids, activo=True)
                        .values('subtema_id')
                        .annotate(total=Count('id'))
                    )
                    indicadores_por_subtema = {row['subtema_id']: row['total'] for row in counts}

                for subtema in subtemas:
                    subtema_data = {
                        "id": subtema.id,
                        "nombre": subtema.nombre,
                        "slug": subtema.slug,
                        "tipo": "subtema"
                    }
                    if incluir_indicadores:
                        subtema_data["total_indicadores"] = indicadores_por_subtema.get(subtema.id, 0)
                    subtemas_por_tema[subtema.tema_id].append(subtema_data)

                datos = []
                for tema in temas:
                    tema_data = {
                        "id": tema.id,
                        "nombre": tema.nombre,
                        "slug": tema.slug,
                        "tipo": "tema",
                        "dominio": {
                            "id": tema.dominio.id,
                            "nombre": tema.dominio.nombre
                        } if tema.dominio else None,
                        "subtemas": subtemas_por_tema.get(tema.id, [])
                    }
                    if incluir_indicadores:
                        total_tema = sum(
                            item.get("total_indicadores", 0)
                            for item in tema_data["subtemas"]
                        )
                        tema_data["total_indicadores"] = total_tema
                    datos.append(tema_data)

                response["datos"] = datos
                response["total"] = len(datos)
                return response

            elif nivel == 'subtemas':
                subtemas_qs = MenuSubtema.objects.filter(activo=True)
                if tema_id is not None:
                    subtemas_qs = subtemas_qs.filter(tema_id=tema_id)
                if dominio_id is not None:
                    subtemas_qs = subtemas_qs.filter(tema__dominio_id=dominio_id)

                subtemas_qs = subtemas_qs.select_related('tema__dominio').order_by('orden')
                subtemas = list(subtemas_qs)

                if not subtemas:
                    response.update({
                        "success": False,
                        "error": "No se encontraron subtemas para los filtros proporcionados"
                    })
                    return response

                subtema_ids = [sub.id for sub in subtemas]
                indicadores_por_subtema = {}
                if incluir_indicadores and subtema_ids:
                    counts = (
                        Indicador.objects
                        .filter(subtema_id__in=subtema_ids, activo=True)
                        .values('subtema_id')
                        .annotate(total=Count('id'))
                    )
                    indicadores_por_subtema = {row['subtema_id']: row['total'] for row in counts}

                datos = []
                for subtema in subtemas:
                    item = {
                        "id": subtema.id,
                        "nombre": subtema.nombre,
                        "slug": subtema.slug,
                        "tipo": "subtema",
                        "tema": {
                            "id": subtema.tema.id,
                            "nombre": subtema.tema.nombre,
                            "dominio": {
                                "id": subtema.tema.dominio.id,
                                "nombre": subtema.tema.dominio.nombre
                            } if subtema.tema and subtema.tema.dominio else None
                        } if subtema.tema else None
                    }
                    if incluir_indicadores:
                        item["total_indicadores"] = indicadores_por_subtema.get(subtema.id, 0)
                    datos.append(item)

                response["datos"] = datos
                response["total"] = len(datos)
                return response

            else:
                response["success"] = False
                response["error"] = "Parámetros inválidos para la consulta"
                return response
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Error al obtener la estructura: {str(e)}"
            }

    def _handle_buscar_indicadores(self, arguments: dict) -> Dict[str, Any]:
        """Búsqueda simplificada de indicadores - optimizada para consultas directas"""
        try:
            consulta = (arguments.get('consulta') or '').strip()
            limite_arg = arguments.get('limite', 10)
            
            try:
                limite = max(1, min(int(limite_arg or 10), 20))
            except (TypeError, ValueError):
                limite = 10
            
            if not consulta:
                return {"error": "La consulta no puede estar vacía"}
            
            # Búsqueda vectorial primero
            search_service = SemanticSearch()
            resultados_semanticos = search_service.buscar_similar(
                consulta=consulta,
                tipo_doc='indicador',
                top_k=limite * 2,
                umbral=0.3
            )
            
            # Obtener IDs de indicadores encontrados
            indicador_ids = [r['referencia_id'] for r in resultados_semanticos] if resultados_semanticos else []
            
            # Fallback a búsqueda de texto si no hay resultados vectoriales
            if not indicador_ids:
                text_filter = (
                    Q(nombre__icontains=consulta) |
                    Q(descripcion_indicador__icontains=consulta) |
                    Q(subtema__nombre__icontains=consulta) |
                    Q(subtemas_adicionales__nombre__icontains=consulta) |
                    Q(subtema__tema__nombre__icontains=consulta) |
                    Q(subtemas_adicionales__tema__nombre__icontains=consulta)
                )
                indicadores = Indicador.objects.filter(text_filter, activo=True).select_related(
                    'subtema__tema__dominio'
                ).distinct()[:limite]
            else:
                indicadores = Indicador.objects.filter(
                    id__in=indicador_ids, 
                    activo=True
                ).select_related('subtema__tema__dominio')[:limite]
            
            # Formatear resultados
            resultados = []
            for ind in indicadores:
                import re
                desc = 'Sin descripción'
                if ind.descripcion_indicador:
                    desc_limpio = re.sub(r'<[^>]+>', '', str(ind.descripcion_indicador))
                    desc = desc_limpio[:150] if len(desc_limpio) > 150 else desc_limpio
                
                dominio_slug = ind.subtema.tema.dominio.slug if ind.subtema and ind.subtema.tema and ind.subtema.tema.dominio else None
                tema_slug = ind.subtema.tema.slug if ind.subtema and ind.subtema.tema else None
                resultados.append({
                    'id': ind.id,
                    'nombre': ind.nombre,
                    'descripcion': desc,
                    'unidad_medida': ind.unidad_medida or 'N/A',
                    'tema': ind.subtema.tema.nombre if ind.subtema and ind.subtema.tema else None,
                    'dominio': ind.subtema.tema.dominio.nombre if ind.subtema and ind.subtema.tema and ind.subtema.tema.dominio else None,
                    'url': self._build_absolute_url(named_url='indicadores:tema_detalle_3d', kwargs={'dominio_slug': dominio_slug, 'tema_slug': tema_slug}) if dominio_slug and tema_slug else None,
                })
            
            return {
                'success': True,
                'consulta': consulta,
                'total': len(resultados),
                'indicadores': resultados
            }

        except Exception as e:
            self.logger.error(f"Error en búsqueda de indicadores: {e}")
            return {'error': f'Error en búsqueda: {str(e)}'}

    def _handle_buscar_catalogo_consulta(self, arguments: dict) -> Dict[str, Any]:
        """Búsqueda híbrida (semántica + texto) de conjuntos del catálogo de consulta"""
        try:
            consulta = (arguments.get('consulta') or '').strip()
            limite_arg = arguments.get('limite', 10)
            try:
                limite = max(1, min(int(limite_arg or 10), 20))
            except (TypeError, ValueError):
                limite = 10

            if not consulta:
                return {"error": "La consulta no puede estar vacía"}

            qs = CatalogoConsulta.objects.filter(activo=True).select_related('dominio')
            qs = self._rag_hybrid_search(
                consulta=consulta,
                tipo_doc='catalogo_consulta',
                qs=qs,
                text_filter_fields=['nombre', 'descripcion'],
                umbral=0.3,
                top_k_semantic=limite * 2,
            )
            conjuntos = list(qs[:limite])

            resultados = []
            for c in conjuntos:
                desc = 'Sin descripción'
                if c.descripcion:
                    desc_limpio = re.sub(r'<[^>]+>', '', str(c.descripcion)).strip()
                    desc = desc_limpio[:150] if len(desc_limpio) > 150 else desc_limpio
                resultados.append({
                    'id': c.pk,
                    'nombre': c.nombre,
                    'descripcion': desc,
                    'tipo_consulta': c.get_tipo_consulta_display(),
                    'dominio': c.dominio.nombre if c.dominio else None,
                    'total_registros': c.total_filas,
                    'tiene_datos': c.total_filas > 0,
                    'url': self._build_absolute_url(
                        named_url='indicadores:catalogo_consulta_detalle',
                        kwargs={'pk': c.pk}
                    ),
                    'indicadores_enlazados': [
                        i.nombre for i in c.indicadores_enlazados.filter(activo=True)[:3]
                    ],
                })

            return {
                'success': True,
                'consulta': consulta,
                'total': len(resultados),
                'conjuntos': resultados,
                'nota': 'Son datos de referencia (directorios/listados), no series estadísticas. '
                       'Usa consultar_catalogo_consulta con el id para leer el cuadro completo.'
            }

        except Exception as e:
            self.logger.error(f"Error en búsqueda de catálogo de consulta: {e}")
            return {'error': f'Error en búsqueda: {str(e)}'}

    def _handle_consultar_catalogo_consulta(self, arguments: dict) -> Dict[str, Any]:
        """Devuelve el cuadro de consulta de un conjunto: columnas + filas filtradas"""
        try:
            conjunto_id = arguments.get('conjunto_id')
            if not conjunto_id:
                return {'error': 'Se requiere conjunto_id'}

            try:
                limite = max(1, min(int(arguments.get('limite') or 50), 200))
            except (TypeError, ValueError):
                limite = 50
            filtro = (arguments.get('filtro') or '').strip().lower()

            try:
                conjunto = CatalogoConsulta.objects.select_related('dominio').get(
                    pk=int(conjunto_id), activo=True
                )
            except CatalogoConsulta.DoesNotExist:
                return {'error': f'Conjunto {conjunto_id} no existe o está inactivo'}

            columnas = conjunto.columnas or []
            filas = conjunto.filas or []
            if filtro:
                filas = [
                    f for f in filas
                    if any(filtro in str(v).lower() for v in f.values() if v is not None)
                ]

            return {
                'success': True,
                'conjunto': {
                    'id': conjunto.pk,
                    'nombre': conjunto.nombre,
                    'tipo_consulta': conjunto.get_tipo_consulta_display(),
                    'dominio': conjunto.dominio.nombre if conjunto.dominio else None,
                    'url': self._build_absolute_url(
                        named_url='indicadores:catalogo_consulta_detalle',
                        kwargs={'pk': conjunto.pk}
                    ),
                },
                'columnas': columnas,
                'total_filas_encontradas': len(filas),
                'filas': filas[:limite],
                'truncado': len(filas) > limite,
            }

        except Exception as e:
            self.logger.error(f"Error consultando catálogo de consulta: {e}")
            return {'error': f'Error: {str(e)}'}

    def _handle_consultar_indicador(self, arguments: dict) -> Dict[str, Any]:
        """Consulta simplificada de indicador específico con datos históricos"""
        try:
            indicador_id = arguments.get('indicador_id')
            if not indicador_id:
                return {'error': 'ID del indicador requerido'}
            
            año_inicio = arguments.get('año_inicio')
            año_fin = arguments.get('año_fin')
            limite_arg = arguments.get('limite', 100)
            
            try:
                limite = max(1, min(int(limite_arg), 500))
            except (TypeError, ValueError):
                limite = 100
            
            # Obtener indicador
            indicador = Indicador.objects.select_related(
                'subtema__tema__dominio'
            ).get(id=indicador_id, activo=True)
            
            # Extraer descripción limpia
            import re
            descripcion = ''
            if indicador.descripcion_indicador:
                descripcion = re.sub(r'<[^>]+>', '', str(indicador.descripcion_indicador))
            
            # Consultar datos
            datos_qs = Dato.objects.filter(indicador=indicador)
            if año_inicio:
                datos_qs = datos_qs.filter(fecha_dato__year__gte=año_inicio)
            if año_fin:
                datos_qs = datos_qs.filter(fecha_dato__year__lte=año_fin)
            
            datos = datos_qs.order_by('-fecha_dato')[:limite]
            
            # Formatear datos
            datos_formateados = []
            for dato in datos:
                try:
                    valor = float(dato.valor_dato)
                except (TypeError, ValueError):
                    valor = None
                
                datos_formateados.append({
                    'fecha': dato.fecha_dato.isoformat() if dato.fecha_dato else None,
                    'anio': dato.fecha_dato.year if dato.fecha_dato else None,
                    'valor': valor,
                    'desagregaciones': {
                        'geograficas': [dg.nombre for dg in dato.desagregaciones_geograficas.all()],
                        'tematicas': [dt.nombre for dt in dato.desagregaciones_tematicas.all()]
                    }
                })
            
            dominio_slug = indicador.subtema.tema.dominio.slug if indicador.subtema and indicador.subtema.tema and indicador.subtema.tema.dominio else None
            tema_slug = indicador.subtema.tema.slug if indicador.subtema and indicador.subtema.tema else None
            return {
                'success': True,
                'indicador': {
                    'id': indicador.id,
                    'nombre': indicador.nombre,
                    'descripcion': descripcion[:500] if len(descripcion) > 500 else descripcion,
                    'unidad_medida': indicador.unidad_medida or 'N/A',
                    'clasificacion': {
                        'dominio': indicador.subtema.tema.dominio.nombre if indicador.subtema and indicador.subtema.tema and indicador.subtema.tema.dominio else None,
                        'tema': indicador.subtema.tema.nombre if indicador.subtema and indicador.subtema.tema else None,
                        'subtema': indicador.subtema.nombre if indicador.subtema else None,
                    },
                    'url': self._build_absolute_url(named_url='indicadores:tema_detalle_3d', kwargs={'dominio_slug': dominio_slug, 'tema_slug': tema_slug}) if dominio_slug and tema_slug else None,
                },
                'datos': datos_formateados,
                'total_datos': len(datos_formateados)
            }
            
        except Indicador.DoesNotExist:
            return {'error': f'Indicador con ID {indicador_id} no encontrado'}
        except Exception as e:
            self.logger.error(f"Error consultando indicador: {e}")
            return {'error': f'Error consultando indicador: {str(e)}'}
            dominios = arguments.get('dominios') or []
            temas = arguments.get('temas') or []
            con_datos_geograficos = arguments.get('con_datos_geograficos', False)
            limite_arg = arguments.get('limite', 20)
            top_k_arg = arguments.get('top_k')
            umbral_semantico = arguments.get('umbral_similitud')

            # Normalizar entradas
            if isinstance(dominios, int):
                dominios = [dominios]
            if isinstance(temas, int):
                temas = [temas]
            if isinstance(con_datos_geograficos, str):
                con_datos_geograficos = con_datos_geograficos.lower() in ['1', 'true', 'sí', 'si', 'yes']
            try:
                limite = max(1, min(int(limite_arg or 20), 50))
            except (TypeError, ValueError):
                limite = 20

            # MEJORA: Primero obtener IDs de indicadores que cumplen filtros SQL
            # para limitar la búsqueda vectorial solo a esos indicadores
            filtered_ids = None
            if dominios or temas:
                pre_query = Indicador.objects.filter(activo=True)
                if dominios:
                    pre_query = pre_query.filter(
                        Q(subtema__tema__dominio_id__in=dominios) |
                        Q(subtemas_adicionales__tema__dominio_id__in=dominios)
                    )
                if temas:
                    pre_query = pre_query.filter(
                        Q(subtema__tema_id__in=temas) |
                        Q(subtemas_adicionales__tema_id__in=temas)
                    )
                filtered_ids = list(pre_query.values_list('id', flat=True).distinct())
                logger.info(f"Pre-filtro SQL: {len(filtered_ids)} indicadores en dominio/tema especificado")
            
            # Ejecutar búsqueda semántica para obtener candidatos iniciales
            semantic_ids_order: List[int] = []
            semantic_metadata: Dict[int, Dict[str, Any]] = {}
            semantic_response: Optional[Dict[str, Any]] = None
            if consulta:
                sem_args = {
                    'consulta': consulta,
                    'top_k': max(50, int(top_k_arg or 50)),
                    'umbral_similitud': 0.4,
                }
                # MEJORA: Pasar IDs filtrados a la búsqueda semántica
                if filtered_ids is not None:
                    sem_args['indicadores_ids'] = filtered_ids
                    
                if umbral_semantico is not None:
                    try:
                        sem_args['umbral_similitud'] = float(umbral_semantico)
                    except (TypeError, ValueError):
                        logger.warning(f"Umbral semántico inválido: {umbral_semantico}")

                semantic_response = self._handle_buscar_indicadores_semantico(sem_args)
                logger.debug(
                    "Respuesta semántica bruta",
                    extra={
                        'consulta': consulta,
                        'total': semantic_response.get('total_resultados') if isinstance(semantic_response, dict) else None,
                        'tiene_success': semantic_response.get('success') if isinstance(semantic_response, dict) else None
                    }
                )

                if isinstance(semantic_response, dict):
                    resultados_sem = semantic_response.get('resultados') or []
                    if not resultados_sem and isinstance(semantic_response.get('mensaje'), str):
                        logger.info(f"Búsqueda semántica sin resultados: {semantic_response['mensaje']}")

                    for item in resultados_sem:
                        raw_id = item.get('id') or item.get('referencia_id')
                        try:
                            item_id = int(raw_id)
                        except (TypeError, ValueError):
                            logger.debug(f"ID semántico inválido: {raw_id}")
                            continue

                        if item_id not in semantic_ids_order:
                            semantic_ids_order.append(item_id)
                            semantic_metadata[item_id] = {
                                'similitud': item.get('similitud'),
                                'descripcion_semantica': item.get('descripcion') or item.get('descripcion_semantica'),
                                'fuente_vectorial': True
                            }

            # Construir query base sobre los candidatos (o sobre todos si no hay semánticos)
            query = Indicador.objects.filter(activo=True).select_related('subtema__tema__dominio')
            fallback_text_search = False

            if semantic_ids_order:
                query = query.filter(id__in=semantic_ids_order)
            elif consulta:
                fallback_text_search = True
                text_filter = (
                    Q(nombre__icontains=consulta) |
                    Q(descripcion_indicador__icontains=consulta) |
                    Q(objetivo__icontains=consulta) |
                    Q(subtema__nombre__icontains=consulta) |
                    Q(subtemas_adicionales__nombre__icontains=consulta) |
                    Q(subtema__tema__nombre__icontains=consulta) |
                    Q(subtemas_adicionales__tema__nombre__icontains=consulta) |
                    Q(subtema__tema__dominio__nombre__icontains=consulta) |
                    Q(subtemas_adicionales__tema__dominio__nombre__icontains=consulta)
                )
                query = query.filter(text_filter)

            # Aplicar filtros jerárquicos y geográficos
            # (subtema principal + adicionales M2M → distinct por el join)
            if dominios:
                query = query.filter(
                    Q(subtema__tema__dominio_id__in=dominios) |
                    Q(subtemas_adicionales__tema__dominio_id__in=dominios)
                )

            if temas:
                query = query.filter(
                    Q(subtema__tema_id__in=temas) |
                    Q(subtemas_adicionales__tema_id__in=temas)
                )
            query = query.distinct()

            if con_datos_geograficos:
                query = query.exclude(dominios_desagregacion_geografica__isnull=True)

            # Ordenar preservando relevancia semántica cuando aplique
            if semantic_ids_order:
                ordering = Case(
                    *[When(id=pk, then=Value(idx)) for idx, pk in enumerate(semantic_ids_order)],
                    default=Value(len(semantic_ids_order)),
                    output_field=IntegerField()
                )
                query = query.order_by(ordering, '-fecha_actualizacion')
            else:
                query = query.order_by('-fecha_actualizacion')

            indicadores = list(query[:limite])

            # Obtener datos asociados a los indicadores seleccionados
            datos_por_indicador: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
            max_datos = arguments.get('max_datos_por_indicador', 10)
            try:
                max_datos = max(1, min(int(max_datos), 500))
            except (TypeError, ValueError):
                max_datos = 10

            if indicadores:
                for indicador in indicadores:
                    datos_qs = list(
                        Dato.objects
                        .filter(indicador=indicador)
                        .order_by('-fecha_dato')
                        .prefetch_related('desagregaciones_geograficas', 'desagregaciones_tematicas')
                    )[:max_datos]

                    for dato in datos_qs:
                        geo_labels = [
                            {
                                'id': dg.id,
                                'nombre': dg.nombre,
                                'codigo': dg.codigo
                            }
                            for dg in dato.desagregaciones_geograficas.all()
                        ]
                        tem_labels = [
                            {
                                'id': dt.id,
                                'nombre': dt.nombre,
                                'codigo': dt.codigo
                            }
                            for dt in dato.desagregaciones_tematicas.all()
                        ]

                        try:
                            valor = float(dato.valor_dato)
                        except (TypeError, ValueError, InvalidOperation):
                            valor = None

                        datos_por_indicador[indicador.id].append({
                            'fecha': dato.fecha_dato.isoformat() if dato.fecha_dato else None,
                            'anio': dato.fecha_dato.year if dato.fecha_dato else None,
                            'valor': valor,
                            'desagregaciones_geograficas': geo_labels,
                            'desagregaciones_tematicas': tem_labels
                        })

            resultados = []
            for indicador in indicadores:
                datos_detalle = datos_por_indicador.get(indicador.id, [])

                # Extraer descripción desde descripcion_indicador (sin HTML)
                descripcion_texto = 'Sin descripción'
                if indicador.descripcion_indicador:
                    import re
                    desc_limpio = re.sub(r'<[^>]+>', '', str(indicador.descripcion_indicador))
                    descripcion_texto = (desc_limpio[:200] + '...') if len(desc_limpio) > 200 else desc_limpio
                
                info = {
                    'id': indicador.id,
                    'nombre': indicador.nombre,
                    'descripcion': descripcion_texto,
                    'unidad_medida': getattr(indicador, 'unidad_medida', '') or 'N/A',
                    'subtema': indicador.subtema.nombre if indicador.subtema else 'N/A',
                    'tema': indicador.subtema.tema.nombre if indicador.subtema and indicador.subtema.tema else 'N/A',
                    'dominio': indicador.subtema.tema.dominio.nombre if indicador.subtema and indicador.subtema.tema and indicador.subtema.tema.dominio else 'N/A',
                    'tiene_datos_geograficos': bool(getattr(indicador, 'dominios_desagregacion_geografica', None)),
                    'fecha_actualizacion': indicador.fecha_publicacion_metadatos.isoformat() if indicador.fecha_publicacion_metadatos else None,
                    'metodo': 'vectorial' if indicador.id in semantic_metadata else ('texto' if consulta else 'filtros'),
                    'metadata': {
                        'unidad_medida': indicador.unidad_medida or 'N/A',
                        'fuente': getattr(indicador, 'fuente_datos', None) or getattr(indicador, 'fuente', None) or 'No especificada',
                        'periodicidad': getattr(indicador, 'periodicidad', 'No especificada'),
                        'metodo_medicion': getattr(indicador, 'metodo_medicion', '') or '',
                        'operacion_estadistica': indicador.operacion.nombre if indicador.operacion else None
                    },
                    'datos': datos_detalle,
                }

                if datos_detalle:
                    resumen_por_anio: Dict[int, List[float]] = defaultdict(list)
                    for punto in datos_detalle:
                        anio = punto.get('anio')
                        valor = punto.get('valor')
                        if anio and isinstance(valor, (int, float)):
                            resumen_por_anio[anio].append(valor)

                    resumen_estadistico = []
                    for anio, valores in sorted(resumen_por_anio.items(), reverse=True):
                        if not valores:
                            continue
                        promedio = sum(valores) / len(valores)
                        resumen_estadistico.append({
                            'anio': anio,
                            'observaciones': len(valores),
                            'promedio': round(promedio, 4),
                            'min': round(min(valores), 4),
                            'max': round(max(valores), 4)
                        })

                    info['datos_disponibles'] = len(datos_detalle)
                    info['datos_resumen'] = resumen_estadistico
                else:
                    info['datos_disponibles'] = 0
                    info['datos_resumen'] = []

                meta = semantic_metadata.get(indicador.id)
                if meta and meta.get('similitud') is not None:
                    try:
                        info['similitud'] = round(float(meta['similitud']), 3)
                    except (TypeError, ValueError):
                        info['similitud'] = meta['similitud']
                resultados.append(info)

            response: Dict[str, Any] = {
                "success": True,
                "consulta_original": consulta,
                "total_encontrados": len(resultados),
                "filtros_aplicados": {
                    "dominios": dominios,
                    "temas": temas,
                    "con_datos_geograficos": con_datos_geograficos
                },
                "resultados": resultados,
                "metodo_busqueda": 'vectorial' if semantic_ids_order else ('texto' if consulta else 'filtros'),
                "uso_vectorial": bool(semantic_ids_order)
            }

            if fallback_text_search:
                response["fallback_textual"] = True

            if semantic_response and semantic_response.get('resultados'):
                response["resultados_semanticos"] = semantic_response['resultados'][:limite]
                response["total_semantico"] = len(semantic_response['resultados'])

            if not resultados and semantic_response and semantic_response.get('resultados'):
                fallback_semantic = []
                for item in semantic_response['resultados'][:limite]:
                    fallback_semantic.append({
                        'id': item.get('id'),
                        'nombre': item.get('nombre'),
                        'descripcion': item.get('descripcion', 'Sin descripción'),
                        'unidad_medida': item.get('unidad_medida', 'N/A'),
                        'tema': item.get('tema'),
                        'dominio': item.get('dominio'),
                        'similitud': item.get('similitud'),
                        'metodo': 'vectorial_fallback'
                    })

                if fallback_semantic:
                    response['resultados'] = fallback_semantic
                    response['total_encontrados'] = len(fallback_semantic)
                    response['metodo_busqueda'] = 'vectorial'
                    response['uso_vectorial'] = True
                    response['mensaje'] = "Se muestran resultados semánticos al no encontrar coincidencias que cumplieran los filtros solicitados."
                else:
                    response["mensaje"] = "No se encontraron resultados que cumplieran los filtros adicionales. Se incluyen resultados semánticos sin filtrar para referencia."

            if not resultados and not (semantic_response and semantic_response.get('resultados')):
                response["mensaje"] = "No se encontraron indicadores que coincidan con la búsqueda."

            return response

        except Exception as e:
            self.logger.error(f"Error en búsqueda inteligente: {e}", exc_info=True)
            return {"error": f"Error en búsqueda inteligente: {str(e)}"}

    def _handle_obtener_datos_completo(self, arguments: dict) -> dict:
        """Obtiene información completa de un indicador"""
        indicador_id = arguments.get('indicador_id')
        
        try:
            indicador = Indicador.objects.select_related(
                'subtema__tema__dominio'
            ).get(id=indicador_id, activo=True)
            
            # Extraer texto limpio de campos CKEditor
            import re
            definiciones = ''
            if indicador.descripcion_indicador:
                definiciones = re.sub(r'<[^>]+>', '', str(indicador.descripcion_indicador))
            
            metodo = ''
            if indicador.metodo_medicion:
                metodo = re.sub(r'<[^>]+>', '', str(indicador.metodo_medicion))
            
            resultado = {
                "indicador": {
                    "id": indicador.id,
                    "nombre": indicador.nombre,
                    "descripcion": definiciones or '',
                    "unidad_medida": indicador.unidad_medida or '',
                    "metodologia": metodo or '',
                    "fuente": getattr(indicador, 'fuente_datos', '') or '',
                    "fecha_actualizacion": indicador.fecha_publicacion_metadatos,
                    "clasificacion": {
                        "dominio": indicador.subtema.tema.dominio.nombre,
                        "tema": indicador.subtema.tema.nombre,
                        "subtema": indicador.subtema.nombre
                    }
                }
            }
            
            # Incluir metadatos si se solicita
            if arguments.get('incluir_metadatos', True):
                resultado["metadatos"] = self._get_indicador_metadata(indicador)
            
            # Incluir datos si se solicita
            if arguments.get('incluir_datos', True):
                datos = self._get_indicador_data(
                    indicador_id,
                    arguments.get('año_inicio'),
                    arguments.get('año_fin'),
                    arguments.get('desagregaciones_geograficas'),
                    arguments.get('desagregaciones_tematicas')
                )
                resultado["datos"] = datos
            
            return resultado
            
        except Indicador.DoesNotExist:
            return {"error": f"Indicador con ID {indicador_id} no encontrado"}
        except Exception as e:
            self.logger.error(f"Error obteniendo datos completos: {e}")
            return {"error": f"Error obteniendo datos: {str(e)}"}

    def _handle_analizar_comparativo(self, arguments: dict) -> dict:
        """Realiza análisis comparativo entre indicadores"""
        indicadores_ids = arguments.get('indicadores_ids', [])
        tipo_analisis = arguments.get('tipo_analisis', 'temporal')
        
        try:
            # Obtener indicadores
            indicadores = Indicador.objects.filter(
                id__in=indicadores_ids, activo=True
            ).select_related('subtema__tema__dominio')
            
            if not indicadores.exists():
                return {"error": "No se encontraron indicadores válidos para comparar"}
            
            resultado = {
                "tipo_analisis": tipo_analisis,
                "indicadores_analizados": len(indicadores),
                "indicadores": [
                    {
                        "id": ind.id,
                        "nombre": ind.nombre,
                        "unidad_medida": ind.unidad_medida or 'N/A'
                    }
                    for ind in indicadores
                ],
                "analisis": {}
            }
            
            # Realizar análisis según el tipo
            if tipo_analisis == 'temporal':
                resultado["analisis"] = self._analizar_tendencia_temporal(
                    indicadores, arguments.get('período', {})
                )
            elif tipo_analisis == 'territorial':
                resultado["analisis"] = self._analizar_comparativo_territorial(
                    indicadores, arguments.get('nivel_geografico', 'ciudad')
                )
            elif tipo_analisis == 'tematico':
                resultado["analisis"] = self._analizar_comparativo_tematico(indicadores)
            
            return resultado
            
        except Exception as e:
            self.logger.error(f"Error en análisis comparativo: {e}")
            return {"error": f"Error en análisis: {str(e)}"}

    def _handle_explorar_microdatos(self, arguments: dict) -> dict:
        """Explora conjuntos de conjuntos_datos"""
        accion = arguments.get('accion', 'listar')
        
        try:
            if accion == 'listar':
                conjuntos_datos = ConjuntoDatos.objects.filter(activo=True).select_related(
                    'operacion'
                ).values(
                    'id', 'nombre', 'descripcion', 'fecha_carga',
                    'operacion__nombre', 'tamaño_archivo', 'formato'
                ).order_by('-fecha_carga')[:20]
                
                return {
                    "accion": "listar",
                    "total": conjuntos_datos.count(),
                    "conjuntos_datos": list(conjuntos_datos)
                }
            
            elif accion == 'explorar':
                conjunto = arguments.get('conjunto_datos')
                if not conjunto:
                    return {"error": "Nombre del conjunto de datos requerido"}
                
                # Lógica para explorar un conjunto específico
                return self._explorar_conjunto_especifico(conjunto, arguments.get('filtros', {}))
            
            # Más acciones...
            
        except Exception as e:
            self.logger.error(f"Error explorando conjuntos_datos: {e}")
            return {"error": f"Error explorando conjuntos_datos: {str(e)}"}

    def _handle_informacion_contextual(self, arguments: dict) -> dict:
        """Obtiene información contextual del sistema"""
        tipo = arguments.get('tipo_informacion')
        filtros = arguments.get('filtros', {})
        
        try:
            if tipo == 'operaciones_estadisticas':
                ops = OperacionEstadistica.objects.filter(
                    activo=filtros.get('activos_solamente', True)
                ).values(
                    'nombre', 'descripcion', 'periodicidad',
                    'entidad_recopiladora', 'fecha_inicio'
                )[:filtros.get('limite', 10)]
                
                return {
                    "tipo": "operaciones_estadisticas",
                    "datos": list(ops)
                }
            
            elif tipo == 'eventos_proximos':
                eventos = Evento.objects.filter(
                    fecha_inicio__gte=timezone.now(),
                    activo=filtros.get('activos_solamente', True)
                ).values(
                    'nombre', 'descripcion', 'fecha_inicio', 'lugar'
                ).order_by('fecha_inicio')[:filtros.get('limite', 5)]
                
                return {
                    "tipo": "eventos_proximos", 
                    "datos": list(eventos)
                }
            
            elif tipo == 'estadisticas_generales':
                stats = {
                    'total_dominios': MenuDominio.objects.filter(activo=True).count(),
                    'total_temas': MenuTema.objects.filter(activo=True).count(),
                    'total_subtemas': MenuSubtema.objects.filter(activo=True).count(),
                    'total_indicadores': Indicador.objects.filter(activo=True).count(),
                    'total_operaciones': OperacionEstadistica.objects.filter(activo=True).count(),
                    'total_microdatos': ConjuntoDatos.objects.count()
                }
                
                return {
                    "tipo": "estadisticas_generales",
                    "datos": stats
                }
            
        except Exception as e:
            self.logger.error(f"Error obteniendo información contextual: {e}")
            return {"error": f"Error: {str(e)}"}

    def _handle_obtener_matriz_indicador(self, arguments: dict) -> Dict[str, Any]:
        """Retorna matriz de datos en bruto para análisis por IA (sin cálculos)"""
        try:
            indicador_id = arguments.get('indicador_id')
            if not indicador_id:
                return {'error': 'ID del indicador requerido'}
            
            año_inicio = arguments.get('año_inicio')
            año_fin = arguments.get('año_fin')
            incluir_desagregaciones = arguments.get('incluir_desagregaciones', True)
            
            # Obtener indicador
            indicador = Indicador.objects.get(id=indicador_id, activo=True)
            
            # Consultar datos
            datos_qs = Dato.objects.filter(indicador=indicador).order_by('fecha_dato')
            if año_inicio:
                datos_qs = datos_qs.filter(fecha_dato__year__gte=año_inicio)
            if año_fin:
                datos_qs = datos_qs.filter(fecha_dato__year__lte=año_fin)
            
            datos = list(datos_qs.prefetch_related('desagregaciones_geograficas', 'desagregaciones_tematicas'))
            
            # Construir matriz en bruto
            matriz = []
            for dato in datos:
                fila = {
                    'año': dato.fecha_dato.year if dato.fecha_dato else None,
                    'valor': float(dato.valor_dato) if dato.valor_dato else None
                }
                if incluir_desagregaciones:
                    geo_names = [dg.nombre for dg in dato.desagregaciones_geograficas.all()]
                    tem_names = [dt.nombre for dt in dato.desagregaciones_tematicas.all()]
                    if geo_names:
                        fila['desag_geo'] = geo_names
                    if tem_names:
                        fila['desag_tem'] = tem_names
                matriz.append(fila)
            
            return {
                'indicador_id': indicador.id,
                'nombre': indicador.nombre,
                'unidad_medida': indicador.unidad_medida,
                'total_registros': len(matriz),
                'matriz': matriz  # Datos en bruto para análisis por IA
            }
            
        except Indicador.DoesNotExist:
            return {'error': f'Indicador {indicador_id} no encontrado'}
        except Exception as e:
            self.logger.error(f"Error obteniendo matriz: {e}")
            return {'error': str(e)}

    def _handle_listar_variables_conjunto_datos(self, arguments: dict) -> Dict[str, Any]:
        """Lista variables disponibles en conjunto_datos con metadatos básicos"""
        try:
            conjunto_datos_id = arguments.get('conjunto_datos_id')
            if not conjunto_datos_id:
                return {'error': 'ID de conjunto_datos requerido'}
            
            conjunto_datos = ConjuntoDatos.objects.get(id=conjunto_datos_id)
            variables = VariableConjuntoDatos.objects.filter(conjunto_datos=conjunto_datos).order_by('orden')
            
            lista = []
            for var in variables:
                lista.append({
                    'codigo': var.codigo_variable,
                    'nombre': var.nombre_variable,
                    'tipo_dato': var.tipo_dato,
                    'definicion': var.definicion_conceptual[:200] if var.definicion_conceptual else None,
                    'unidad_medida': var.unidad_medida,
                    'desagregacion_geo': var.desagregacion_geografica,
                    'desagregacion_tem': var.desagregacion_tematica
                })
            
            return {
                'conjunto_datos_id': conjunto_datos.id,
                'nombre': conjunto_datos.nombre,
                'total_variables': len(lista),
                'variables': lista
            }
            
        except ConjuntoDatos.DoesNotExist:
            return {'error': f'conjunto_datos {conjunto_datos_id} no encontrada'}
        except Exception as e:
            self.logger.error(f"Error listando variables: {e}")
            return {'error': str(e)}

    def _handle_obtener_matriz_conjunto_datos(self, arguments: dict) -> Dict[str, Any]:
        """Retorna muestra de conjunto_datos en formato matriz para análisis por IA"""
        try:
            conjunto_datos_id = arguments.get('conjunto_datos_id')
            if not conjunto_datos_id:
                return {'error': 'ID de conjunto_datos requerido'}
            
            variables_filter = arguments.get('variables', [])  # Variables específicas
            muestra = arguments.get('muestra', 500)
            
            # Normalizar muestra
            try:
                muestra = max(10, min(int(muestra), 1000))
            except:
                muestra = 500
            
            conjunto_datos = ConjuntoDatos.objects.get(id=conjunto_datos_id)
            
            # Obtener variables
            vars_qs = VariableConjuntoDatos.objects.filter(conjunto_datos=conjunto_datos)
            if variables_filter:
                vars_qs = vars_qs.filter(codigo_variable__in=variables_filter)
            
            variables = list(vars_qs.order_by('orden'))
            if not variables:
                return {'error': 'No se encontraron variables'}
            
            # Leer CSV si existe
            if not conjunto_datos.archivo_csv:
                return {'error': 'No hay archivo CSV asociado'}
            
            import csv
            import random
            
            registros = []
            try:
                with conjunto_datos.archivo_csv.open('r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames or []
                    
                    # Mapear códigos de variables a nombres de columnas
                    codigos_vars = [v.codigo_variable for v in variables]
                    
                    # Leer todos los registros
                    all_rows = list(reader)
                    
                    # Muestreo aleatorio si hay muchos registros
                    if len(all_rows) > muestra:
                        selected = random.sample(all_rows, muestra)
                    else:
                        selected = all_rows
                    
                    # Construir matriz
                    for row in selected:
                        fila = {}
                        for var in variables:
                            if var.codigo_variable in row:
                                val = row[var.codigo_variable]
                                # Intentar convertir a número
                                try:
                                    val = float(val)
                                except:
                                    pass
                                fila[var.codigo_variable] = val
                        if fila:
                            registros.append(fila)
                            
            except Exception as csv_err:
                return {'error': f'Error leyendo CSV: {str(csv_err)}'}
            
            return {
                'conjunto_datos_id': conjunto_datos.id,
                'nombre': conjunto_datos.nombre,
                'variables': [v.codigo_variable for v in variables],
                'total_registros_muestra': len(registros),
                'matriz': registros  # Datos en bruto para análisis por IA
            }
            
        except ConjuntoDatos.DoesNotExist:
            return {'error': f'conjunto_datos {conjunto_datos_id} no encontrada'}
        except Exception as e:
            self.logger.error(f"Error obteniendo matriz conjunto_datos: {e}")
            return {'error': str(e)}

    # ====================================================================
    # NUEVOS HANDLERS — Módulos extendidos de la plataforma
    # ====================================================================

    def _handle_consultar_iced(self, arguments: dict) -> Dict[str, Any]:
        """Consulta puntajes ICED de organismos"""
        try:
            org_query = (arguments.get('organismo') or '').strip()
            periodo = (arguments.get('periodo') or '').strip()
            incluir_sub = arguments.get('incluir_subdimensiones', False)

            qs = ICEDFormulario.objects.filter(estado='validado').select_related('organismo')

            if periodo:
                qs = qs.filter(periodo=periodo)
            if org_query:
                qs = qs.filter(
                    Q(organismo__nombre__icontains=org_query) |
                    Q(organismo__codigo__icontains=org_query)
                )

            # Si no hay periodo específico, tomar el más reciente
            if not periodo:
                ultimo = qs.order_by('-periodo').values_list('periodo', flat=True).first()
                if ultimo:
                    qs = qs.filter(periodo=ultimo)
                    periodo = ultimo

            formularios = qs.order_by('-puntaje_global')[:50]

            if not formularios.exists():
                return {'mensaje': 'No se encontraron formularios ICED validados con esos criterios.', 'total': 0}

            resultados = []
            for f in formularios:
                entry = {
                    'organismo': f.organismo.nombre,
                    'periodo': f.periodo,
                    'puntaje_global': float(f.puntaje_global * 100) if f.puntaje_global else None,
                    'nivel': f.nivel_global_display,
                    'dimensiones': {
                        'entorno_institucional': float(f.puntaje_b * 100) if f.puntaje_b else None,
                        'infraestructura': float(f.puntaje_c * 100) if f.puntaje_c else None,
                        'metodologia_estadistica': float(f.puntaje_d * 100) if f.puntaje_d else None,
                        'accesibilidad_uso': float(f.puntaje_e * 100) if f.puntaje_e else None,
                    },
                    'url': self._build_absolute_url(named_url='indicadores:validacion_revisar_iced', kwargs={'formulario_id': f.id}),
                }
                if incluir_sub and f.puntajes_detalle:
                    entry['detalle_subdimensiones'] = f.puntajes_detalle
                resultados.append(entry)

            return {
                'periodo': periodo or 'último disponible',
                'total': len(resultados),
                'escala': '0-100%',
                'formula': 'ICED = promedio simple de 4 dimensiones (25% cada una)',
                'resultados': resultados
            }

        except Exception as e:
            self.logger.error(f"Error consultando ICED: {e}", exc_info=True)
            return {'error': f'Error consultando ICED: {str(e)}'}

    def _handle_consultar_ecosistema_datos(self, arguments: dict) -> Dict[str, Any]:
        """Consulta ecosistema de datos de un organismo (datos del taller F1/F2/F3, anonimizado)"""
        try:
            org_query = (arguments.get('organismo') or '').strip()
            aspecto = arguments.get('aspecto', 'resumen')

            if not org_query:
                return {'error': 'Se requiere el nombre del organismo'}

            organismo = Organismo.objects.filter(
                Q(nombre__icontains=org_query) | Q(codigo__icontains=org_query),
                activo=True
            ).first()

            if not organismo:
                return {'error': f'Organismo "{org_query}" no encontrado'}

            inscripciones = InscripcionTaller.objects.filter(organismo=organismo)
            if not inscripciones.exists():
                return {'mensaje': f'No hay inscripciones al taller de gestión de datos institucionales para {organismo.nombre}.'}

            fuentes = FuenteDatos.objects.filter(inscripcion__organismo=organismo)
            retos = RetoAnalisis.objects.filter(inscripcion__organismo=organismo)
            evaluaciones = EvaluacionSeguridad.objects.filter(
                fuente__inscripcion__organismo=organismo)

            if aspecto == 'resumen':
                return {
                    'organismo': organismo.nombre,
                    'total_inscripciones': inscripciones.count(),
                    'inscripciones_completadas': inscripciones.filter(estado='completada').count(),
                    'total_fuentes_caracterizadas': fuentes.count(),
                    'total_retos_analisis': retos.count(),
                    'total_evaluaciones_seguridad': evaluaciones.count(),
                    'fuentes_criticas': evaluaciones.filter(criticidad='rojo').count(),
                    'nota': 'Los datos personales de los diligenciantes han sido anonimizados.'
                }

            elif aspecto == 'fuentes':
                lista = []
                for f in fuentes[:50]:
                    seguridad = getattr(f, 'seguridad', None)
                    lista.append({
                        'nombre': f.nombre,
                        'rol': f.get_rol_display() if f.rol else None,
                        'descripcion': (f.descripcion or '')[:300],
                        'num_registros': f.num_registros,
                        'georreferenciacion': f.get_georreferenciacion_display() if f.georreferenciacion else None,
                        'criticidad_seguridad': seguridad.criticidad if seguridad else None,
                    })
                return {
                    'organismo': organismo.nombre,
                    'total': fuentes.count(),
                    'fuentes': lista,
                    'nota': 'Datos personales anonimizados.'
                }

            elif aspecto == 'retos':
                lista = []
                for r in retos[:50]:
                    lista.append({
                        'nombre': r.nombre,
                        'analisis_propuesto': (r.analisis_propuesto or '')[:300],
                        'decision_apoya': (r.decision_apoya or '')[:300],
                        'variables_enriquecer': (r.variables_enriquecer or '')[:200],
                    })
                return {
                    'organismo': organismo.nombre,
                    'total': retos.count(),
                    'retos': lista,
                    'nota': 'Datos personales anonimizados.'
                }

            elif aspecto == 'seguridad':
                lista = []
                for e in evaluaciones.select_related('fuente')[:50]:
                    riesgos = e.calcular_factores_riesgo_ocha()
                    lista.append({
                        'fuente': e.fuente.nombre,
                        'contiene_datos_personales': e.contiene_datos_personales or None,
                        'confidencialidad': e.confidencialidad or None,
                        'integridad': e.integridad or None,
                        'disponibilidad': e.disponibilidad or None,
                        'criticidad': e.criticidad or None,
                        'factores_riesgo_ocha': f"{riesgos['total_riesgos']}/{riesgos['total_criterios']}",
                    })
                return {
                    'organismo': organismo.nombre,
                    'total': evaluaciones.count(),
                    'evaluaciones': lista,
                    'nota': 'Datos personales anonimizados.'
                }

            return {'error': f'Aspecto "{aspecto}" no reconocido'}

        except Exception as e:
            self.logger.error(f"Error consultando ecosistema: {e}", exc_info=True)
            return {'error': f'Error consultando ecosistema de datos: {str(e)}'}

    def _handle_consultar_producto_academico(self, arguments: dict) -> Dict[str, Any]:
        """Busca y consulta productos académicos"""
        try:
            consulta = (arguments.get('consulta') or '').strip()
            producto_id = arguments.get('producto_id')

            # Detalle de un producto específico
            if producto_id:
                try:
                    prod = ProductoAcademico.objects.get(id=producto_id, estado='publicado')
                except ProductoAcademico.DoesNotExist:
                    return {'error': f'Producto académico {producto_id} no encontrado o no publicado'}

                secciones = SeccionPaper.objects.filter(producto=prod).order_by('numero_orden', 'subnumero')
                secciones_list = []
                for s in secciones:
                    contenido_limpio = re.sub(r'<[^>]+>', '', str(s.contenido or ''))[:500]
                    secciones_list.append({
                        'tipo': s.get_tipo_seccion_display(),
                        'titulo': s.titulo or s.get_tipo_seccion_display(),
                        'orden': f"{s.numero_orden}.{s.subnumero}" if s.subnumero else str(s.numero_orden),
                        'tipo_bloque': s.get_tipo_bloque_display(),
                        'contenido_preview': contenido_limpio,
                    })

                indicadores_derivados = list(
                    prod.indicadores_derivados.values_list('nombre', flat=True)[:20]
                )

                return {
                    'id': prod.id,
                    'titulo': prod.titulo,
                    'resumen': prod.resumen,
                    'autor': prod.autor,
                    'institucion': prod.institucion,
                    'area_tematica': prod.area_tematica,
                    'palabras_clave': prod.palabras_clave,
                    'fecha_publicacion': str(prod.fecha_publicacion) if prod.fecha_publicacion else None,
                    'organismo': prod.organismo.nombre if prod.organismo else None,
                    'indicadores_derivados': indicadores_derivados,
                    'total_secciones': len(secciones_list),
                    'secciones': secciones_list,
                    'url': self._build_absolute_url(obj=prod),
                }

            # Búsqueda general (híbrida: RAG semántico + fallback texto)
            qs = ProductoAcademico.objects.filter(estado='publicado')
            qs = self._rag_hybrid_search(
                consulta=consulta,
                tipo_doc='producto_academico',
                qs=qs,
                text_filter_fields=['titulo', 'resumen', 'palabras_clave', 'area_tematica']
            )

            productos = qs.select_related('organismo')[:20]

            if not productos.exists():
                return {'mensaje': 'No se encontraron productos académicos publicados.', 'total': 0}

            resultados = []
            for p in productos:
                resultados.append({
                    'id': p.id,
                    'titulo': p.titulo,
                    'resumen': (p.resumen or '')[:300],
                    'autor': p.autor,
                    'area_tematica': p.area_tematica,
                    'fecha_publicacion': str(p.fecha_publicacion) if p.fecha_publicacion else None,
                    'url': self._build_absolute_url(obj=p),
                })

            return {'total': len(resultados), 'productos': resultados}

        except Exception as e:
            self.logger.error(f"Error consultando productos académicos: {e}", exc_info=True)
            return {'error': f'Error consultando productos académicos: {str(e)}'}

    def _handle_buscar_documentos_infraestructura(self, arguments: dict) -> Dict[str, Any]:
        """Busca documentos de infraestructura estadística"""
        try:
            consulta = (arguments.get('consulta') or '').strip()
            area_filter = (arguments.get('area') or '').strip()
            tipo_doc = arguments.get('tipo_documento')
            limite = min(max(arguments.get('limite', 10), 1), 50)

            # Si no hay filtros, devolver estructura de áreas
            if not consulta and not area_filter and not tipo_doc:
                areas = AreaInfraestructura.objects.filter(activo=True).order_by('orden')
                estructura = []
                for area in areas:
                    cats = CategoriaInfraestructura.objects.filter(area=area, activo=True).order_by('orden')
                    cat_list = []
                    for cat in cats:
                        n_docs = DocumentoInfraestructura.objects.filter(
                            grupo_documento__subcategoria__categoria=cat,
                            activo=True, estado='publicado'
                        ).count()
                        cat_list.append({'nombre': cat.nombre, 'total_documentos': n_docs})
                    estructura.append({
                        'area': area.nombre,
                        'descripcion': area.descripcion,
                        'categorias': cat_list,
                    })
                return {
                    'tipo': 'estructura',
                    'total_areas': len(estructura),
                    'areas': estructura,
                    'mensaje': 'Usa el parámetro "consulta" o "area" para buscar documentos específicos.'
                }

            # Buscar documentos (híbrida: RAG semántico + fallback texto)
            qs = DocumentoInfraestructura.objects.filter(activo=True, estado='publicado')
            qs = self._rag_hybrid_search(
                consulta=consulta,
                tipo_doc='documento_infraestructura',
                qs=qs,
                text_filter_fields=['nombre', 'descripcion', 'palabras_clave', 'resumen_ejecutivo']
            )
            if area_filter:
                qs = qs.filter(grupo_documento__subcategoria__categoria__area__nombre__icontains=area_filter)
            if tipo_doc:
                qs = qs.filter(tipo_documento=tipo_doc)

            documentos = qs.select_related(
                'grupo_documento__subcategoria__categoria__area'
            ).order_by('grupo_documento__subcategoria__categoria__area__orden', 'orden')[:limite]

            resultados = []
            for doc in documentos:
                ruta = (
                    f"{doc.grupo_documento.subcategoria.categoria.area.nombre} → "
                    f"{doc.grupo_documento.subcategoria.categoria.nombre} → "
                    f"{doc.grupo_documento.subcategoria.nombre} → "
                    f"{doc.grupo_documento.nombre}"
                )
                resultados.append({
                    'id': doc.id,
                    'nombre': doc.nombre,
                    'tipo': doc.get_tipo_documento_display(),
                    'descripcion': (doc.descripcion or '')[:200],
                    'resumen_ejecutivo': (doc.resumen_ejecutivo or '')[:300],
                    'version': doc.version,
                    'autor': doc.autor,
                    'ruta_jerarquica': ruta,
                    'tiene_pdf': bool(doc.archivo_pdf),
                    'tiene_word': bool(doc.archivo_word),
                    'url': self._build_absolute_url(obj=doc),
                })

            return {'total': len(resultados), 'documentos': resultados}

        except Exception as e:
            self.logger.error(f"Error buscando documentos infraestructura: {e}", exc_info=True)
            return {'error': f'Error buscando documentos: {str(e)}'}

    def _handle_consultar_sistemas_informacion(self, arguments: dict) -> Dict[str, Any]:
        """Lista sistemas de consulta y proyectos de información"""
        try:
            tipo = arguments.get('tipo', 'todos')
            consulta = (arguments.get('consulta') or '').strip()
            resultado = {}

            # Sistemas de Consulta
            if tipo in ('sistemas', 'todos'):
                qs_sis = SistemaInformacion.objects.filter(activo=True).select_related('categoria')
                if consulta:
                    qs_sis = qs_sis.filter(
                        Q(nombre__icontains=consulta) | Q(descripcion__icontains=consulta)
                    )

                categorias_sis = {}
                for sis in qs_sis.order_by('categoria__orden', 'orden'):
                    cat_name = sis.categoria.nombre
                    if cat_name not in categorias_sis:
                        categorias_sis[cat_name] = []
                    categorias_sis[cat_name].append({
                        'nombre': sis.nombre,
                        'descripcion': (sis.descripcion or '')[:200],
                        'url': sis.url,
                        'url_interna': self._build_absolute_url(named_url='indicadores:sistemas_informacion'),
                        'tipo_enlace': sis.get_tipo_enlace_display(),
                        'requiere_autenticacion': sis.requiere_autenticacion,
                    })

                resultado['sistemas_consulta'] = {
                    'total': qs_sis.count(),
                    'por_categoria': categorias_sis,
                }

            # Proyectos de Información (Productos)
            if tipo in ('productos', 'todos'):
                qs_proy = ProyectoInformacion.objects.filter(activo=True).select_related('categoria')
                if consulta:
                    qs_proy = qs_proy.filter(
                        Q(nombre__icontains=consulta) | Q(descripcion__icontains=consulta)
                    )

                categorias_proy = {}
                for proy in qs_proy.order_by('categoria__orden', 'orden'):
                    cat_name = proy.categoria.nombre
                    if cat_name not in categorias_proy:
                        categorias_proy[cat_name] = []
                    categorias_proy[cat_name].append({
                        'nombre': proy.nombre,
                        'descripcion': (proy.descripcion or '')[:200],
                        'url': proy.url,
                        'url_interna': self._build_absolute_url(named_url='indicadores:proyectos_informacion'),
                        'dependencia_responsable': proy.dependencia_responsable,
                        'estado': proy.get_estado_display(),
                        'poblacion_objetivo': proy.poblacion_objetivo,
                    })

                resultado['productos_informacion'] = {
                    'total': qs_proy.count(),
                    'por_categoria': categorias_proy,
                }

            return resultado

        except Exception as e:
            self.logger.error(f"Error consultando sistemas de información: {e}", exc_info=True)
            return {'error': f'Error consultando sistemas de información: {str(e)}'}

    def _handle_consultar_operaciones_estadisticas(self, arguments: dict) -> Dict[str, Any]:
        """Consulta operaciones estadísticas con enlaces ADDA/AMDA"""
        try:
            consulta = (arguments.get('consulta') or '').strip()
            org_filter = (arguments.get('organismo') or '').strip()
            limite = min(max(arguments.get('limite', 15), 1), 50)

            qs = OperacionEstadistica.objects.filter(activo=True)

            if consulta:
                qs = qs.filter(
                    Q(nombre__icontains=consulta) |
                    Q(descripcion__icontains=consulta) |
                    Q(tema__icontains=consulta) |
                    Q(area_tem__icontains=consulta) |
                    Q(objetivo__icontains=consulta)
                )
            if org_filter:
                qs = qs.filter(
                    Q(organismo__icontains=org_filter) |
                    Q(entidad_recopiladora__icontains=org_filter) |
                    Q(grupo_productor__icontains=org_filter)
                )

            ooee_list = qs.order_by('nombre')[:limite]

            if not ooee_list.exists():
                # Devolver resumen de lo disponible
                total = OperacionEstadistica.objects.filter(activo=True).count()
                return {
                    'mensaje': f'No se encontraron OOEE con esos criterios. Hay {total} operaciones activas en total.',
                    'total': 0,
                    'sugerencia': 'Intenta con términos más generales o consulta sin filtros.'
                }

            resultados = []
            for oe in ooee_list:
                # Contar indicadores derivados de esta OE
                n_indicadores = Indicador.objects.filter(operacion=oe, activo=True).count()

                entry = {
                    'id': oe.id,
                    'codigo': oe.codigo,
                    'nombre': oe.nombre,
                    'descripcion': (oe.descripcion or '')[:300],
                    'tipo_operacion': oe.tipo_operacion,
                    'periodicidad': oe.periodicidad,
                    'organismo': oe.organismo,
                    'suborganismo': oe.suborganismo,
                    'area_tematica': oe.area_tem,
                    'tema': oe.tema,
                    'objetivo': (oe.objetivo or '')[:300],
                    'entidad_recopiladora': oe.entidad_recopiladora,
                    'indicadores_derivados': n_indicadores,
                    'url': self._build_absolute_url(named_url='indicadores:operacion_detalle', kwargs={'pk': oe.id}),
                    'enlace_adda': oe.link_adda,
                    'enlace_pe': oe.link_pe,
                    'cant_amda': oe.cant_amda,
                    'anio_adda': oe.anio_adda,
                }

                # Solo incluir campos no vacíos
                entry = {k: v for k, v in entry.items() if v is not None and v != ''}
                resultados.append(entry)

            return {
                'total': len(resultados),
                'operaciones': resultados,
                'nota_adda': 'Los enlaces ADDA llevan al Archivo Distrital de Datos Abiertos. Los enlaces PE llevan al Plan Estadístico.'
            }

        except Exception as e:
            self.logger.error(f"Error consultando OOEE: {e}", exc_info=True)
            return {'error': f'Error consultando operaciones estadísticas: {str(e)}'}

    def _handle_consultar_satisfaccion(self, arguments: dict) -> Dict[str, Any]:
        """Consulta estadísticas agregadas de satisfacción ciudadana"""
        try:
            from django.db.models import Avg, Count as DjCount
            org_query = (arguments.get('organismo') or '').strip()
            periodo_meses = min(max(arguments.get('periodo_meses', 12), 1), 36)
            fecha_desde = timezone.now() - timedelta(days=periodo_meses * 30)

            if org_query:
                organismo = Organismo.objects.filter(
                    Q(nombre__icontains=org_query) | Q(codigo__icontains=org_query),
                    activo=True
                ).first()
                if not organismo:
                    return {'error': f'Organismo "{org_query}" no encontrado'}

                rapidas = RespuestaSatisfaccionRapida.objects.filter(
                    organismo=organismo, fecha_registro__gte=fecha_desde
                )
                total = rapidas.count()
                if total == 0:
                    return {'mensaje': f'No hay respuestas de satisfacción para {organismo.nombre} en los últimos {periodo_meses} meses.'}

                distribucion = dict(
                    rapidas.values_list('calificacion').annotate(n=DjCount('id')).order_by('calificacion')
                )
                promedio = rapidas.aggregate(avg=Avg('calificacion'))['avg']

                return {
                    'organismo': organismo.nombre,
                    'periodo_meses': periodo_meses,
                    'total_respuestas': total,
                    'promedio_calificacion': round(float(promedio), 2) if promedio else None,
                    'escala': '1=Muy insatisfecho, 2=Insatisfecho, 3=Neutral, 4=Satisfecho, 5=Muy satisfecho',
                    'distribucion': {
                        'muy_insatisfecho': distribucion.get(1, 0),
                        'insatisfecho': distribucion.get(2, 0),
                        'neutral': distribucion.get(3, 0),
                        'satisfecho': distribucion.get(4, 0),
                        'muy_satisfecho': distribucion.get(5, 0),
                    }
                }

            # Resumen general: ranking por organismo
            ranking = (
                RespuestaSatisfaccionRapida.objects
                .filter(fecha_registro__gte=fecha_desde)
                .values('organismo__nombre')
                .annotate(promedio=Avg('calificacion'), total=DjCount('id'))
                .order_by('-promedio')[:20]
            )

            if not ranking:
                return {'mensaje': 'No hay datos de satisfacción disponibles.'}

            resultados = []
            for r in ranking:
                resultados.append({
                    'organismo': r['organismo__nombre'],
                    'promedio': round(float(r['promedio']), 2),
                    'total_respuestas': r['total'],
                })

            return {
                'periodo_meses': periodo_meses,
                'total_organismos': len(resultados),
                'ranking': resultados,
                'escala': '1-5 (1=Muy insatisfecho, 5=Muy satisfecho)',
            }

        except Exception as e:
            self.logger.error(f"Error consultando satisfacción: {e}", exc_info=True)
            return {'error': f'Error consultando satisfacción: {str(e)}'}

    def generate_response_with_tools(self, user_message: str, conversation_history: List[Dict] = None) -> Generator[Dict[str, Any], None, None]:
        """Genera respuesta usando Cerebras con herramientas - CORREGIDO"""
        try:
            # Construir mensajes con contexto mejorado
            messages = []
            
            # Sistema con personalidad clara
            system_context = self._get_enhanced_system_context()
            messages.append({
                "role": "system",
                "content": system_context
            })
            
            # Agregar historial limitado
            if conversation_history:
                max_history = get_config('MAX_HISTORY_MESSAGES', 8)
                max_length = get_config('MAX_MESSAGE_LENGTH', 1000)
                for msg in conversation_history[-max_history:]:
                    if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
                        messages.append({
                            "role": msg["role"],
                            "content": str(msg["content"])[:max_length]
                        })
            
            # Mensaje del usuario
            messages.append({"role": "user", "content": user_message})
            
            # Configuración para Cerebras (usando config centralizada)
            response = self.client.chat.completions.create(
                messages=messages,
                model=get_config('CEREBRAS_MODEL', 'gpt-oss-120b'),
                tools=self.get_tools_definition(),
                tool_choice="auto",
                parallel_tool_calls=True,
                max_tokens=get_config('CEREBRAS_MAX_TOKENS', 14200),
                temperature=get_config('CEREBRAS_TEMPERATURE', 0.15),
                top_p=get_config('CEREBRAS_TOP_P', 0.9),
                stream=True
            )
            
            # Variables para acumular contenido
            accumulated_content = ""
            tool_calls = []
            current_tool_call = None
            
            # Procesar streaming
            for chunk in response:
                if not hasattr(chunk, 'choices') or not chunk.choices:
                    continue
                    
                choice = chunk.choices[0]
                delta = choice.delta
                
                is_tool_delta = hasattr(delta, 'tool_calls') and delta.tool_calls
                content_piece = getattr(delta, 'content', None)

                # Manejar contenido de texto únicamente si no corresponde a un tool-call
                if content_piece and not is_tool_delta and not self._looks_like_tool_call_payload(content_piece):
                    accumulated_content += content_piece
                    yield {"content": content_piece, "is_complete": False}
                
                # Manejar tool calls
                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        if tool_call.index == 0:  # Nueva tool call
                            if current_tool_call:
                                tool_calls.append(current_tool_call)
                            current_tool_call = {
                                "id": getattr(tool_call, 'id', f"call_{len(tool_calls)}"),
                                "type": "function",  # Añadido campo type requerido
                                "function": {
                                    "name": "",
                                    "arguments": ""
                                }
                            }
                        
                        # Acumular función y argumentos
                        if hasattr(tool_call, 'function'):
                            if hasattr(tool_call.function, 'name') and tool_call.function.name:
                                current_tool_call["function"]["name"] += tool_call.function.name
                            if hasattr(tool_call.function, 'arguments') and tool_call.function.arguments:
                                current_tool_call["function"]["arguments"] += tool_call.function.arguments
                
                # Verificar si el streaming terminó
                if hasattr(choice, 'finish_reason') and choice.finish_reason:
                    if current_tool_call:
                        tool_calls.append(current_tool_call)
                    break
            
            # Si hay tool calls, ejecutarlas
            if tool_calls:
                self.logger.info(f"Ejecutando {len(tool_calls)} tool calls")
                
                # Ejecutar todas las herramientas
                tool_results = []
                for tool_call in tool_calls:
                    try:
                        # Crear objeto mock para compatibilidad
                        class MockToolCall:
                            def __init__(self, data):
                                self.id = data["id"]
                                self.function = type('obj', (object,), {
                                    'name': data["function"]["name"],
                                    'arguments': data["function"]["arguments"]
                                })
                        
                        mock_call = MockToolCall(tool_call)
                        result = self.execute_tool_call(mock_call)
                        tool_results.append({
                            "tool_call_id": tool_call["id"],
                            "role": "tool",
                            "name": tool_call["function"]["name"],
                            "content": json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
                        })
                        
                    except Exception as e:
                        self.logger.error(f"Error ejecutando tool call: {e}", exc_info=True)
                        tool_results.append({
                            "tool_call_id": tool_call["id"],
                            "role": "tool",
                            "name": tool_call["function"]["name"],
                            "content": json.dumps({"error": str(e)}, ensure_ascii=False)
                        })
                
                # Enviar resultados formateados al flujo antes de solicitar la respuesta final
                formatted_payloads = []
                for result in tool_results:
                    content = result.get("content")
                    if isinstance(content, str):
                        try:
                            formatted_payloads.append(json.loads(content))
                        except json.JSONDecodeError:
                            formatted_payloads.append(content)
                    else:
                        formatted_payloads.append(content)

                if formatted_payloads:
                    payload = formatted_payloads[0] if len(formatted_payloads) == 1 else formatted_payloads
                    yield {
                        "tool_results": payload,
                        "is_complete": False
                    }

                # Agregar las tool calls y resultados a los mensajes
                messages.append({
                    "role": "assistant",
                    "content": accumulated_content if accumulated_content else None,
                    "tool_calls": tool_calls
                })
                
                for result in tool_results:
                    messages.append(result)
                
                # Obtener respuesta final del LLM con los resultados
                final_response = self.client.chat.completions.create(
                    messages=messages,
                    model=get_config('CEREBRAS_MODEL', 'gpt-oss-120b'),
                    max_tokens=get_config('CEREBRAS_MAX_TOKENS', 14200),
                    temperature=get_config('CEREBRAS_TEMPERATURE', 0.15),
                    top_p=get_config('CEREBRAS_TOP_P', 0.9),
                    stream=True
                )
                
                # Stream de la respuesta final
                for chunk in final_response:
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content and not self._looks_like_tool_call_payload(delta.content):
                            yield {"content": delta.content, "is_complete": False}
            
            # Indicar finalización
            yield {"content": "", "is_complete": True}

        except Exception as e:
            error_msg = f"Error en generate_response_with_tools: {str(e)}"
            logger.error(error_msg, exc_info=True)
            yield {"content": f"Error: {error_msg}", "is_complete": True, "error": True}


    def _get_enhanced_system_context(self) -> str:
        """Retorna el contexto mejorado del sistema usando configuración centralizada"""
        return get_context('enhanced_tools')

    def _optimize_conversation_history(self, history: List[Dict]) -> List[Dict]:
        """Optimiza el historial de conversación para el contexto"""
        if not history:
            return []
        
        # Tomar solo los últimos N mensajes para mantener contexto relevante
        max_history = get_config('MAX_HISTORY_MESSAGES', 8)
        recent = history[-max_history:]
        
        # Filtrar mensajes válidos
        optimized = []
        for msg in recent:
            if (isinstance(msg, dict) and 
                msg.get('content') and 
                msg.get('role') in ['user', 'assistant']):
                # Truncar mensajes muy largos
                content = msg['content']
                max_length = get_config('MAX_MESSAGE_LENGTH', 1000)
                if len(content) > max_length:
                    content = content[:max_length] + "..."
                
                optimized.append({
                    "role": msg['role'],
                    "content": content
                })
        
        return optimized

    def _process_multiple_tools(self, messages: List[Dict], tool_calls: List) -> str:
        """Procesa múltiples llamadas de herramientas de forma paralela"""
        try:
            # Agregar mensaje del asistente con tool calls
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls
            })
            
            # Ejecutar todas las herramientas
            tool_results = {}
            for tool_call in tool_calls:
                try:
                    tool_result = self.execute_tool_call(tool_call)
                    tool_results[tool_call.function.name] = tool_result
                    
                    # Agregar resultado al historial (sin modificar el formato)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                        "name": tool_call.function.name,
                        "preserve_markdown": True  # Marcar para preservar formato
                    })
                    
                except Exception as e:
                    error_msg = f"Error ejecutando herramienta {tool_call.function.name}: {e}"
                    logger.error(error_msg)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({
                            "error": error_msg
                        }),
                        "name": tool_call.function.name,
                        "is_error": True
                    })
            
            # Construir mensaje de sistema con instrucciones para preservar markdown
            system_message = get_context('tool_results_processor')
            
            # Insertar mensaje del sistema al principio
            messages.insert(0, {"role": "system", "content": system_message})
            
            # Generar respuesta final con resultados de herramientas
            final_response = self.client.chat.completions.create(
                messages=messages,
                model=get_config('CEREBRAS_MODEL', 'gpt-oss-120b'),
                max_tokens=get_config('CEREBRAS_MAX_TOKENS', 14200),
                temperature=get_config('CEREBRAS_TEMPERATURE', 0.3),
                top_p=get_config('CEREBRAS_TOP_P', 0.95)
            )
            
            # Obtener la respuesta y asegurar que el markdown sea válido
            response_content = final_response.choices[0].message.content
            
            # Si la respuesta parece contener markdown pero no está bien formateado,
            # intentar corregir el formato básico
            if "```" in response_content and "\n```" not in response_content:
                response_content = response_content.replace("```", "\n```\n")
                
            return response_content
            
        except Exception as e:
            logger.error(f"Error procesando múltiples herramientas: {e}")
            return self._generate_error_response(str(e))

    def _generate_fallback_response(self, user_message: str) -> str:
        """Genera respuesta de fallback cuando no se necesitan herramientas"""
        return f"""¡Hola parce! Soy Don Datico, del SIIED de Cali.

Tu consulta sobre "{user_message[:50]}..." es interesante, pero necesito un poco más de información específica para ayudarte mejor.

¿Podrías decirme exactamente qué tipo de datos o información estadística de Cali te interesa? Por ejemplo:
- Indicadores de población, educación, salud, etc.
- Datos de una comuna o zona específica
- Información sobre algún período en particular

¡A la orden para ayudarte con los datos del SIIED!"""

    def _generate_error_response(self, error: str) -> str:
        """Genera respuesta amigable para errores"""
        return f"""¡Uy parce, qué pena! Se presentó un problemita técnico consultando los datos del SIIED.

No te preocupes, esto pasa a veces. ¿Podrías intentar reformular tu pregunta de manera más específica?

Por ejemplo:
- "Muéstrame indicadores de población de Cali"
- "¿Qué datos de educación están disponibles?"
- "Información sobre eventos próximos"

¡Estoy aquí para ayudarte con toda la información estadística de nuestra bella Cali!"""

    # Métodos auxiliares para análisis específicos
    def _get_indicador_metadata(self, indicador) -> dict:
        """Obtiene metadatos detallados de un indicador"""
        # Extraer método de medición (reemplaza metodologia)
        import re
        metodo = ''
        if hasattr(indicador, 'metodo_medicion') and indicador.metodo_medicion:
            metodo = re.sub(r'<[^>]+>', '', str(indicador.metodo_medicion))
        
        return {
            "metodologia": metodo or 'No disponible',
            "fuente": getattr(indicador, 'fuente_datos', None) or getattr(indicador, 'fuente', None) or 'No especificada',
            "periodicidad": getattr(indicador, 'periodicidad', 'No especificada'),
            "cobertura_geografica": getattr(indicador, 'cobertura_geografica', 'Ciudad'),
            "fecha_ultima_actualizacion": getattr(indicador, 'fecha_actualizacion', None),
            "responsable": getattr(indicador, 'entidad_responsable', None) or 'SIIED Cali'
        }

    def _get_indicador_data(self, indicador_id: int, año_inicio: int = None,
                           año_fin: int = None, desag_geo: List[int] = None,
                           desag_tem: List[int] = None, limite: int = 500) -> dict:
        """Obtiene datos de un indicador con filtros y límite de registros"""
        try:
            # Normalizar límite (1-500)
            try:
                limite_normalizado = max(1, min(int(limite or 500), 500))
            except (TypeError, ValueError):
                limite_normalizado = 500

            # Construir parámetros para la API
            params = {"indicadores": indicador_id, "limite": limite_normalizado}
            
            if año_inicio:
                params["anio_inicio"] = año_inicio
            if año_fin:
                params["anio_fin"] = año_fin
            
            # Llamar a la API interna
            result = self.call_api_endpoint("get_datos_indicadores", params)

            valores = result.get("datos", [])
            total_original = len(valores) if isinstance(valores, list) else 0
            if isinstance(valores, list):
                valores = valores[:limite_normalizado]

            return {
                "valores": valores,
                "total_registros": len(valores),
                "total_original": total_original,
                "limite_aplicado": limite_normalizado,
                "truncado": total_original > len(valores),
                "filtros_aplicados": {
                    "año_inicio": año_inicio,
                    "año_fin": año_fin,
                    "desagregaciones_geograficas": desag_geo,
                    "desagregaciones_tematicas": desag_tem
                }
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo datos del indicador {indicador_id}: {e}")
            return {"error": f"Error obteniendo datos: {str(e)}"}

    def _analizar_tendencia_temporal(self, indicadores, periodo: dict) -> dict:
        """Analiza tendencias temporales de indicadores"""
        try:
            analisis = {
                "tipo": "tendencia_temporal",
                "periodo_analizado": periodo,
                "indicadores_con_tendencia": [],
                "resumen": ""
            }
            
            for indicador in indicadores:
                # Obtener datos temporales del indicador
                datos_temporales = self._get_indicador_data(
                    indicador.id,
                    periodo.get('año_inicio'),
                    periodo.get('año_fin')
                )
                
                if datos_temporales.get("valores"):
                    # Análisis básico de tendencia
                    valores = datos_temporales["valores"]
                    if len(valores) > 1:
                        tendencia = "creciente" if valores[-1] > valores[0] else "decreciente"
                        analisis["indicadores_con_tendencia"].append({
                            "indicador": indicador.nombre,
                            "tendencia": tendencia,
                            "cambio_porcentual": round(((valores[-1] - valores[0]) / valores[0]) * 100, 2),
                            "datos_disponibles": len(valores)
                        })
            
            return analisis
            
        except Exception as e:
            logger.error(f"Error en análisis temporal: {e}")
            return {"error": f"Error en análisis: {str(e)}"}

    def _analizar_comparativo_territorial(self, indicadores, nivel_geo: str) -> dict:
        """Analiza comparación territorial de indicadores"""
        return {
            "tipo": "comparativo_territorial",
            "nivel_geografico": nivel_geo,
            "message": "Análisis territorial en desarrollo - se requiere implementación específica de desagregaciones geográficas"
        }

    def _analizar_comparativo_tematico(self, indicadores) -> dict:
        """Analiza comparación temática entre indicadores"""
        try:
            temas = {}
            for indicador in indicadores:
                tema = indicador.subtema.tema.nombre
                if tema not in temas:
                    temas[tema] = []
                temas[tema].append({
                    "nombre": indicador.nombre,
                    "unidad": indicador.unidad_medida or "N/A"
                })
            
            return {
                "tipo": "comparativo_tematico",
                "temas_identificados": len(temas),
                "distribucion_por_tema": temas,
                "recomendacion": "Los indicadores abarcan múltiples temas, permitiendo análisis intersectorial"
            }
            
        except Exception as e:
            logger.error(f"Error en análisis temático: {e}")
            return {"error": f"Error en análisis: {str(e)}"}

    def _explorar_conjunto_especifico(self, nombre_conjunto: str, filtros: dict) -> dict:
        """Explora un conjunto específico de conjuntos_datos"""
        try:
            # Buscar el conjunto de conjuntos_datos
            conjunto = ConjuntoDatos.objects.filter(
                nombre__icontains=nombre_conjunto
            ).first()
            
            if not conjunto:
                return {"error": f"Conjunto de datos '{nombre_conjunto}' no encontrado"}
            
            return {
                "conjunto": {
                    "nombre": conjunto.nombre,
                    "descripcion": conjunto.descripcion or "Sin descripción",
                    "fecha_carga": conjunto.fecha_carga,
                    "tamaño": getattr(conjunto, 'tamaño_archivo', 'No especificado'),
                    "formato": getattr(conjunto, 'formato', 'CSV')
                },
                "estructura": "Análisis de estructura en desarrollo",
                "filtros_aplicados": filtros
            }
            
        except Exception as e:
            logger.error(f"Error explorando conjunto específico: {e}")
            return {"error": f"Error: {str(e)}"}

    def call_api_endpoint(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Realiza llamadas a los endpoints de la API con manejo mejorado de errores"""
        try:
            # Las rutas reales son /api/conjuntos-datos/... (guiones),
            # no /api/conjunto_datos/ como quedó en la doc vieja
            ep = endpoint.replace('conjunto_datos/', 'conjuntos-datos/').rstrip('/')
            url = f"{self.base_url}/api/{ep}/"
                
            logger.info(f"Llamando a: {url} con parámetros: {params}")
            
            response = requests.get(url, params=params, timeout=get_config('HTTP_TOOLS_TIMEOUT_SECONDS', 30))
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Respuesta exitosa de {endpoint}")
            return data
            
        except requests.exceptions.Timeout:
            error_msg = f"Timeout al consultar {endpoint}"
            logger.error(error_msg)
            return {"error": error_msg, "status": "timeout"}
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error de conexión en {endpoint}: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "status": "connection_error"}
            
        except json.JSONDecodeError as e:
            error_msg = f"Error decodificando JSON de {endpoint}: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "status": "json_error"}
            
        except Exception as e:
            error_msg = f"Error inesperado en {endpoint}: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "status": "unknown_error"}


class _PrimaryLLMCooldown(Exception):
    """El LLM principal está marcado como caído (circuit breaker activo)."""


class ChatService:
    # Circuit breaker del LLM principal: ante errores no transitorios
    # (402 billing, 401/403 credenciales) se deja de intentar Cerebras
    # durante LLM_PRIMARY_COOLDOWN_SECONDS y se usa directamente el fallback.
    PRIMARY_DOWN_CACHE_KEY = 'chat_llm_primary_down'

    @classmethod
    def primary_llm_down(cls):
        return bool(cache.get(cls.PRIMARY_DOWN_CACHE_KEY))

    def __init__(self, request=None):
        self.api_key = get_config('CEREBRAS_API_KEY', '***REMOVED***')
        self.request = request
        
        # Configuración compatible con Cerebras API (desde configuración centralizada)
        self.model_config = {
            "model": get_config('CEREBRAS_MODEL', 'gpt-oss-120b'),
            "max_tokens": get_config('CEREBRAS_MAX_TOKENS', 14200),
            "temperature": get_config('CEREBRAS_TEMPERATURE', 0.15),
            "top_p": get_config('CEREBRAS_TOP_P', 0.92)
            # Nota: frequency_penalty y presence_penalty no soportados por Cerebras
        }
        
        # Configuración del proveedor fallback (modelo de respaldo)
        self.fallback_config = {
            "model": get_config('OLLAMA_MODEL', 'cogito:3b'),
            "max_tokens": get_config('OLLAMA_MAX_TOKENS', 8000),
            "temperature": get_config('OLLAMA_TEMPERATURE', 0.2),
            "top_p": get_config('OLLAMA_TOP_P', 0.9),
            "base_url": get_config('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
        }
        
        # Cliente principal: Cerebras con OpenAI SDK
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=get_config('CEREBRAS_BASE_URL', 'https://api.cerebras.ai/v1'),
            timeout=get_config('CEREBRAS_TIMEOUT_SECONDS', 45.0)
        )
        
        # Cliente fallback (proveedor alternativo configurado en admin)
        self.fallback_client = OpenAI(
            api_key=get_config('OLLAMA_API_KEY', 'ollama'),
            base_url=get_config('OLLAMA_BASE_URL', 'http://localhost:11434/v1'),
            timeout=get_config('OLLAMA_CLIENT_TIMEOUT_SECONDS', 120.0)
        )
        self.using_fallback = False
        
        # Inicializar tools
        self.tools_enabled = False
        try:
            self.tools_service = CerebrasToolsService(self.api_key, request=request)
            self.tools_enabled = True
            logger.info("ChatService con tools de Cerebras inicializado correctamente")
        except Exception as e:
            logger.warning(f"Tools no disponibles: {e}")

    def _call_llm_with_fallback(self, messages, stream=False, **kwargs):
        """
        Llama al LLM principal; si falla, usa el proveedor fallback configurado.
        Maneja errores 429 (rate limit) y otros errores de API.
        """
        # Intentar con Cerebras primero (salvo circuit breaker activo)
        try:
            if self.primary_llm_down():
                raise _PrimaryLLMCooldown("LLM principal en cooldown")
            if stream:
                return self.client.chat.completions.create(
                    messages=messages,
                    stream=True,
                    **kwargs
                )
            else:
                return self.client.chat.completions.create(
                    messages=messages,
                    stream=False,
                    **kwargs
                )
        except Exception as e:
            error_str = str(e)
            en_cooldown = isinstance(e, _PrimaryLLMCooldown)

            # Errores no transitorios: no tiene sentido reintentar Cerebras en cada request
            error_persistente = not en_cooldown and (
                "401" in error_str or
                "402" in error_str or
                "403" in error_str or
                "payment" in error_str.lower() or
                "billing" in error_str.lower() or
                "wrong api key" in error_str.lower() or
                "unauthorized" in error_str.lower()
            )
            if error_persistente:
                cooldown = get_config('LLM_PRIMARY_COOLDOWN_SECONDS', 600)
                cache.set(self.PRIMARY_DOWN_CACHE_KEY, True, timeout=cooldown)
                logger.error(
                    f"⛔ LLM principal marcado como caído por {cooldown}s "
                    f"(error no transitorio: {error_str[:120]})"
                )
            
            # Detectar errores que deben activar fallback:
            # - 4xx: rate limit, credenciales o solicitudes inválidas (incluye 400 por max_tokens)
            # - 5xx: errores del proveedor (incluye 503 over capacity)
            should_fallback = (
                en_cooldown or
                error_persistente or
                "429" in error_str or 
                "401" in error_str or 
                "403" in error_str or
                "400" in error_str or
                "503" in error_str or
                "rate" in error_str.lower() or 
                "quota" in error_str.lower() or
                "wrong api key" in error_str.lower() or
                "unauthorized" in error_str.lower() or
                "max_tokens" in error_str.lower() or
                "over capacity" in error_str.lower()
            )
            
            if should_fallback:
                if not en_cooldown:
                    logger.warning(f"⚠️ Cerebras API error ({error_str[:100]}...)")
                fallback_provider = self.fallback_config.get('base_url', 'fallback').replace('https://', '').replace('http://', '').split('/')[0]
                logger.info(f"🔄 Cambiando a fallback ({self.fallback_config['model']} @ {fallback_provider})...")
                self.using_fallback = True
                
                # Ajustar kwargs para el proveedor fallback usando configuración
                fallback_kwargs = kwargs.copy()
                fallback_kwargs['model'] = self.fallback_config['model']
                fallback_kwargs['max_tokens'] = self.fallback_config['max_tokens']
                fallback_kwargs['temperature'] = self.fallback_config['temperature']
                fallback_kwargs['top_p'] = self.fallback_config['top_p']
                
                num_tools = len(fallback_kwargs.get('tools', []))
                logger.info(f"🔧 Fallback con {num_tools} tools habilitados")
                
                # Contar tokens aproximados en mensajes
                total_chars = sum(len(str(m.get('content', ''))) for m in messages)
                approx_tokens = total_chars // 4  # Aproximación: 1 token ≈ 4 caracteres
                logger.info(f"📊 Contexto aproximado: {approx_tokens} tokens (~{total_chars} caracteres)")
                logger.info(f"📋 Número de mensajes: {len(messages)}")
                
                # Log de los roles de los mensajes para debugging
                roles_summary = [m.get('role', 'unknown') for m in messages]
                logger.info(f"📝 Roles de mensajes: {roles_summary}")
                
                # Modelo fallback puede ser pequeño; limitamos contexto agresivamente
                # Límite conservador para modelos pequeños: 2000 tokens
                max_context = get_config('OLLAMA_MAX_CONTEXT_TOKENS', 2000)
                truncate_count = get_config('OLLAMA_TRUNCATE_MESSAGES_COUNT', 4)
                
                if approx_tokens > max_context:
                    logger.warning(f"⚠️ Contexto muy grande ({approx_tokens} tokens), truncando mensajes...")
                    # Mantener solo: system + últimos 3 mensajes (user/assistant/tool)
                    system_msgs = [m for m in messages if m.get('role') == 'system']
                    other_msgs = [m for m in messages if m.get('role') != 'system']
                    messages = system_msgs + other_msgs[-truncate_count:]
                    
                    # Recalcular tokens después de truncar
                    new_total_chars = sum(len(str(m.get('content', ''))) for m in messages)
                    new_approx_tokens = new_total_chars // 4
                    logger.info(f"📊 Contexto reducido a {len(messages)} mensajes (~{new_approx_tokens} tokens)")
                
                try:
                    logger.info(f"🚀 Enviando petición a fallback (stream={stream})...")
                    
                    if stream:
                        response = self.fallback_client.chat.completions.create(
                            messages=messages,
                            stream=True,
                            **fallback_kwargs
                        )
                        logger.info("✅ Stream de fallback iniciado correctamente")
                        return response
                    else:
                        response = self.fallback_client.chat.completions.create(
                            messages=messages,
                            stream=False,
                            **fallback_kwargs
                        )
                        logger.info("✅ Respuesta de fallback recibida correctamente")
                        return response
                        
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback también falló: {fallback_error}")
                    logger.error(f"   Tipo de error: {type(fallback_error).__name__}")
                    import traceback
                    logger.error(f"   Traceback: {traceback.format_exc()}")
                    raise Exception(f"LLM principal y fallback fallaron. Principal: {e}, Fallback: {fallback_error}")
            else:
                # Otro tipo de error, no usar fallback
                logger.error(f"❌ Error en Cerebras API (no 429): {e}")
                raise

    # ------------------------------------------------------------------
    # Respuestas estructuradas (JSON Schema)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_structured_json(content):
        """Extrae el primer objeto JSON de la respuesta del LLM.

        Tolera fences ```json ... ``` y texto alrededor del objeto.
        Lanza ValueError si no hay JSON parseable.
        """
        if not content:
            raise ValueError('Respuesta vacía del LLM')
        text = content.strip()
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```\s*$', '', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                raise ValueError('El LLM no devolvió un objeto JSON')
            return json.loads(match.group(0))

    def generate_structured(self, user_prompt, json_schema,
                            system_prompt=None,
                            schema_name='structured_response',
                            max_seconds=None):
        """Genera una respuesta estructurada (dict) según un JSON Schema.

        Reusa la misma cadena de proveedores del chat (principal → fallback)
        sin tools ni streaming. El cliente es OpenAI-compatible con base_url
        configurable, así que no asume proveedor: intenta
        response_format=json_schema y, si el endpoint lo rechaza o devuelve
        JSON inválido, degrada a {'type': 'json_object'} y finalmente a
        JSON pedido por prompt. Última línea de defensa: el schema viaja
        también en el prompt, así el modo prompt-only sigue siendo útil.

        max_seconds limita el tiempo TOTAL de la operación (todos los
        intentos). Los reverse proxies suelen cortar requests largos (~60s):
        sin presupuesto, varios intentos x (primario + fallback) pueden
        tardar minutos y el cliente solo recibe la página de error del
        gateway. El timeout de cada llamada se acota al tiempo restante.

        Retorna el dict parseado. Lanza ValueError si ningún intento
        produce JSON válido, RuntimeError si todos los proveedores fallan.
        """
        sys_content = (system_prompt or
                       'Eres un asistente que responde ÚNICAMENTE con un '
                       'objeto JSON válido. Sin explicaciones, sin markdown.')
        user_content = (
            f'{user_prompt}\n\n'
            'Responde SOLO con un objeto JSON que cumpla este schema:\n'
            f'{json.dumps(json_schema, ensure_ascii=False)}'
        )
        messages = [
            {'role': 'system', 'content': sys_content},
            {'role': 'user', 'content': user_content},
        ]

        # Orden de degradación según lo que el endpoint soporte
        format_candidates = [
            {'type': 'json_schema', 'json_schema': {
                'name': schema_name, 'schema': json_schema}},
            {'type': 'json_object'},
            None,  # prompt-only: el schema va inline en el user message
        ]

        max_seconds = float(max_seconds or get_config(
            'LLM_STRUCTURED_MAX_SECONDS', 55.0))
        deadline = time.monotonic() + max_seconds

        last_error = None
        for fmt in format_candidates:
            remaining = deadline - time.monotonic()
            if remaining < 8.0:
                logger.warning(
                    f"⏱️ generate_structured: presupuesto agotado "
                    f"({max_seconds:.0f}s) antes del intento "
                    f"{fmt.get('type') if fmt else 'prompt-only'}")
                break
            call_kwargs = dict(self.model_config)
            call_kwargs['timeout'] = max(5.0, remaining - 2.0)
            if fmt is not None:
                call_kwargs['response_format'] = fmt
            try:
                resp = self._call_llm_with_fallback(
                    messages, stream=False, **call_kwargs)
                data = self._parse_structured_json(
                    resp.choices[0].message.content)
                if isinstance(data, dict):
                    return data
                raise ValueError('El LLM devolvió JSON pero no un objeto')
            except Exception as e:
                last_error = e
                logger.warning(
                    f"⚠️ generate_structured falló con "
                    f"response_format={fmt.get('type') if fmt else 'none'}: {e}")
                continue
        raise ValueError(
            f'No se obtuvo JSON válido del LLM tras {len(format_candidates)} '
            f'intentos. Último error: {last_error}')

    def _should_use_tools(self, user_message: str) -> bool:

        texto = user_message

        if not texto:
            return JsonResponse({"error": "Falta el parámetro 'texto'"}, status=400)

        # Con el LLM principal caído, el fallback local (CPU) con tools es muy lento
        # (respuesta no-stream de decenas de segundos) y la conexión SSE se corta
        # por inactividad. Se usa el camino de stream directo, que sí funciona.
        if self.primary_llm_down():
            logger.warning("LLM principal caído: se omite el camino con tools")
            return False

        # Clasificador zero-shot (mDeBERTa en CPU, ~segundos por mensaje)
        # reemplazado por heurística de keywords — misma decisión sin latencia.
        intent = self._analyze_query_intent(texto)
        if intent.get('is_search'):
            logger.warning("Consulta detectada (heurística): se llaman herramientas MCP")
            return True

        logger.warning("Mensaje conversacional: el modelo responde con su contexto inicial")
        return False
            
                
        
    def _clean_conversation_history(self, conversation_history):
        """Limpia y optimiza el historial de conversación, asegurando alternancia correcta de roles"""
        if not isinstance(conversation_history, list):
            return []
            
        clean_history = []
        seen_messages = set()
        last_role = None
        
        # Procesar el historial existente
        for msg in conversation_history:
            if not isinstance(msg, dict) or 'role' not in msg or 'content' not in msg:
                continue
                
            content = str(msg.get('content', '')).strip()
            if not content:
                continue
            
            current_role = msg['role']
            
            # CRÍTICO: Evitar roles consecutivos iguales (inválido en OpenAI)
            # Si el rol es el mismo que el anterior, omitir este mensaje
            if last_role == current_role:
                logger.debug(f"[CLEAN_HISTORY] Omitiendo mensaje duplicado de rol '{current_role}'")
                continue
                
            # Crear firma única para detectar duplicados
            msg_signature = f"{current_role}:{content[:100]}"
            if msg_signature in seen_messages:
                continue
                
            seen_messages.add(msg_signature)
            
            # Truncar contenido muy largo
            max_length = get_config('MAX_MESSAGE_LENGTH', 1000)
            if len(content) > max_length:
                content = content[:max_length] + "..."
                
            clean_history.append({
                'role': current_role,
                'content': content
            })
            
            last_role = current_role
            
        return clean_history
        
    def generate_response_stream(self, user_message, relevant_data=None, conversation_history=None):
        """
        Genera respuesta con streaming optimizado, delegando al LLM la decisión de usar herramientas
        Mantiene un historial de conversación limpio y consistente
        """
        logger.info("[STREAM] Iniciando generate_response_stream")
        
        # Validar y limpiar el mensaje del usuario
        if not user_message or not isinstance(user_message, str) or not user_message.strip():
            yield {
                "content": "Por favor, proporciona un mensaje válido.",
                'is_complete': True,
                'source': 'system'
            }
            return
            
        user_message = user_message.strip()
        
        try:
            # Limpiar y optimizar el historial de conversación
            clean_history = self._clean_conversation_history(conversation_history)
            
            # Mantener solo los últimos N mensajes para evitar sobrecarga
            max_history = get_config('MAX_HISTORY_MESSAGES', 8)
            clean_history = clean_history[-max_history:]
            
            # Log de validación del historial limpio
            if clean_history:
                roles_clean = [m['role'] for m in clean_history]
                logger.info(f"[STREAM] Historial limpio: {len(clean_history)} mensajes, roles: {roles_clean}")
            
            # 1. Analizar la intención del mensaje
            logger.info("[STREAM] Analizando intención del mensaje...")
            intent_analysis = self._analyze_query_intent(user_message)
            logger.info(f"[STREAM] Análisis de intención: {intent_analysis}")
            
            # 2. Usar herramientas si el mensaje lo requiere
            if self._should_use_tools(user_message):
                logger.info("[STREAM] Usando herramientas de Cerebras para respuesta completa")
                try:
                    # Obtener el generador de _generate_with_tools_stream
                    tools_generator = self._generate_with_tools_stream(user_message, clean_history)
                    
                    if tools_generator is None:
                        raise ValueError("No se pudo iniciar el generador de herramientas")
                    
                    # Procesar los chunks del generador
                    last_chunk = None
                    for chunk in tools_generator:
                        if chunk:
                            last_chunk = chunk
                            yield chunk
                    
                    # Si el último chunk tiene el historial actualizado, devolverlo
                    if last_chunk and isinstance(last_chunk, dict) and 'updated_history' in last_chunk:
                        yield {
                            'is_complete': True,
                            'updated_history': last_chunk['updated_history']
                        }
                except Exception as e:
                    logger.error(f"[STREAM] Error en _generate_with_tools_stream: {e}", exc_info=True)
                    
                    # En caso de error, intentar con el método tradicional
                    error_msg = "Lo siento, tuve un problema al procesar tu solicitud con herramientas avanzadas. Intentando de otra manera..."
                    clean_history.append({
                        'role': 'user',
                        'content': user_message
                    })
                    clean_history.append({
                        'role': 'assistant',
                        'content': error_msg
                    })
                    
                    yield {
                        "content": error_msg,
                        "is_complete": True
                    }
                    
                    # Reintentar con el método tradicional
                    try:
                        yield from self._generate_traditional_stream(user_message, relevant_data, clean_history)
                    except Exception as e:
                        logger.error(f"[STREAM] Error en _generate_traditional_stream (fallback): {e}", exc_info=True)
                        error_msg = "Lo siento, no pude procesar tu solicitud. Por favor, inténtalo de nuevo más tarde."
                        clean_history.append({
                            'role': 'assistant',
                            'content': error_msg
                        })
                        yield {
                            "content": error_msg,
                            "is_complete": True,
                            'updated_history': clean_history
                        }
            else:
                logger.info("[STREAM] Conversación casual - usando método tradicional sin tools")
                try:
                    # Confiar en el clasificador, NO hardcodear saludos
                    # El LLM manejará saludos y conversación casual naturalmente
                    full_response = ""
                    for chunk in self._generate_traditional_stream(user_message, relevant_data, clean_history):
                        if 'content' in chunk and chunk['content']:
                            full_response += chunk['content']
                        yield chunk
                    
                    # Si el generador no devolvió el historial actualizado, actualizarlo manualmente
                    if full_response:
                        clean_history.append({
                            'role': 'user',
                            'content': user_message
                        })
                        clean_history.append({
                            'role': 'assistant',
                            'content': full_response
                        })
                        
                        # Devolver el historial actualizado como parte del último chunk
                        yield {
                            'is_complete': True,
                            'updated_history': clean_history
                        }
                except Exception as e:
                    logger.error(f"[STREAM] Error en conversación casual: {e}", exc_info=True)
                    error_msg = "Lo siento, tuve un problema al procesar tu solicitud. Por favor, inténtalo de nuevo más tarde."
                    clean_history.append({
                        'role': 'user',
                        'content': user_message
                    })
                    clean_history.append({
                        'role': 'assistant',
                        'content': error_msg
                    })
                    yield {
                        "content": error_msg,
                        "is_complete": True,
                        'updated_history': clean_history
                    }
                    
        except Exception as e:
            logger.error(f"[STREAM] Error inesperado en generate_response_stream: {e}", exc_info=True)
            yield {
                "content": "Lo siento, ocurrió un error inesperado. Por favor, inténtalo de nuevo más tarde.",
                "is_complete": True
            }
        finally:
            logger.info("[STREAM] Finalizado generate_response_stream")

    def stream_response_view(request):
        # ... (obtener user_message, conversation_history, etc.)
        # Asumiendo que tienes el objeto chat_service instanciado

        def event_stream():
            # Obtener el generador de _generate_with_tools_stream
            tools_generator = chat_service._generate_with_tools_stream(user_message, conversation_history)

            # Procesar los chunks del generador
            for chunk in tools_generator:
                # chunk ya es una cadena tipo "data: {...}\n\n"
                yield chunk

            # No es necesario manejar updated_history aquí si lo actualizas en la vista principal
            # después de que termine el stream.

        response = StreamingHttpResponse(event_stream(), content_type='text/plain')
        response['Cache-Control'] = 'no-cache'
        return response        

    def _stream_search_results(self, search_results):
        """Envía los resultados de búsqueda en formato de streaming"""
        try:
            # Verificar si hay resultados
            if not search_results or 'error' in search_results:
                error_msg = search_results.get('error', 'No se encontraron resultados')
                yield {"content": f"No encontré información relevante para tu búsqueda. {error_msg}", "is_complete": True}
                return

            # Obtener resultados directamente o de la clave 'results'
            results = search_results.get('results', search_results)
            
            # Si es una lista, la procesamos directamente
            if isinstance(results, list):
                if not results:
                    yield {"content": "No encontré información relevante para tu búsqueda.", "is_complete": True}
                    return
                
                # Encabezado inicial
                header = "🔍 **Resultados de búsqueda**\n\n"
                yield {"content": header, "is_complete": False}
                
                # Contador de resultados mostrados
                result_count = 0
                max_results = min(10, len(results))  # Mostrar máximo 10 resultados
                
                # Mostrar resultados
                for i, result in enumerate(results[:max_results], 1):
                    try:
                        # Obtener datos del resultado
                        nombre = result.get('nombre', result.get('contenido', 'Sin nombre')[:100])
                        descripcion = result.get('descripcion', result.get('contenido', 'Sin descripción')[:150])
                        similitud = result.get('similitud', 0)
                        
                        # Formatear resultado
                        sim_text = f" (Relevancia: {similitud*100:.1f}%)" if similitud > 0 else ""
                        result_text = (
                            f"{i}. **{nombre}**{sim_text}\n"
                            f"   - {descripcion}...\n\n"
                        )
                        
                        yield {"content": result_text, "is_complete": False}
                        
                    except Exception as e:
                        logger.error(f"Error formateando resultado {i}: {e}")
                        continue
                
                # Mostrar total de resultados
                if len(results) > max_results:
                    yield {"content": f"\n*Mostrando {max_results} de {len(results)} resultados encontrados.*\n\n", "is_complete": False}
                
                # Añadir sugerencias finales
                suggestions = self._generate_search_suggestions(len(results))
                yield {"content": suggestions, "is_complete": True}
                
            # Si es un diccionario con resultados por tipo
            elif isinstance(results, dict) and 'resultados_por_tipo' in results:
                resultados_por_tipo = results.get('resultados_por_tipo', {})
                total_resultados = results.get('total_resultados', 0)
                
                if total_resultados == 0:
                    yield {"content": "No encontré información relevante para tu búsqueda.", "is_complete": True}
                    return
                
                # Encabezado inicial
                header = "🔍 **Resultados de búsqueda**\n\n"
                yield {"content": header, "is_complete": False}
                
                # Contador de resultados mostrados
                result_count = 0
                max_results = 10  # Máximo de resultados a mostrar
                
                # Mostrar resultados por tipo (en orden de importancia)
                tipos_ordenados = ['indicador', 'subtema', 'tema', 'dominio', 'documento']
                
                for tipo in tipos_ordenados:
                    if tipo not in resultados_por_tipo or not resultados_por_tipo[tipo]:
                        continue
                        
                    # Título de la sección
                    tipo_titulo = tipo.capitalize() + 's' if tipo != 'documento' else 'Documentos'
                    yield {"content": f"**{tipo_titulo}**\n", "is_complete": False}
                    
                    # Mostrar resultados de este tipo
                    for result in resultados_por_tipo[tipo]:
                        try:
                            # Obtener datos del resultado
                            nombre = result.get('nombre', result.get('contenido', 'Sin nombre')[:100])
                            descripcion = result.get('descripcion', result.get('contenido', 'Sin descripción')[:150])
                            similitud = result.get('similitud', 0)
                            
                            # Formatear resultado
                            sim_text = f" (Relevancia: {similitud*100:.1f}%)" if similitud > 0 else ""
                            result_text = (
                                f"{result_count + 1}. **{nombre}**{sim_text}\n"
                                f"   - {descripcion}...\n\n"
                            )
                            
                            yield {"content": result_text, "is_complete": False}
                            
                            result_count += 1
                            if result_count >= max_results:
                                break
                                
                        except Exception as e:
                            logger.error(f"Error formateando resultado {tipo}: {e}")
                            continue
                    
                    if result_count >= max_results:
                        break
                
                # Mostrar total de resultados
                if total_resultados > max_results:
                    yield {"content": f"\n*Mostrando {result_count} de {total_resultados} resultados encontrados.*\n\n", "is_complete": False}
                
                # Añadir sugerencias finales
                suggestions = self._generate_search_suggestions(total_resultados)
                yield {"content": suggestions, "is_complete": True}
                
            else:
                # Formato de respuesta no reconocido
                logger.error(f"Formato de resultados no reconocido: {type(search_results)}")
                yield {"content": "No se pudieron procesar los resultados de búsqueda.", "is_complete": True}
            
        except Exception as e:
            logger.error(f"Error en _stream_search_results: {e}", exc_info=True)
            yield {"content": "Ocurrió un error al procesar los resultados de búsqueda.", "is_complete": True}

    def _generate_search_suggestions(self, num_results):
        """Genera sugerencias basadas en el número de resultados"""
        if num_results == 0:
            return (
                "\nNo encontré resultados exactos. Prueba con otros términos o "
                "revisa la ortografía de tu búsqueda."
            )
        elif num_results == 1:
            return "\n¿Te refieres a este indicador o necesitas buscar algo más específico?"
        else:
            return (
                "\n¿Alguno de estos resultados responde a tu búsqueda? "
                "Puedes hacer clic en 'Ver detalles' para más información."
            )

    # En el método _generate_with_tools_stream de la clase ChatService
    # Modificar el método _generate_with_tools_stream
   
   
    def _calculate_tokens(self, text: str) -> int:
        """Calcula el número aproximado de tokens en un texto"""
        # Aproximación: 1 token = 4 caracteres en español
        return max(1, len(str(text).strip()) // 4)

    def _trim_messages_to_token_limit(self, messages: List[Dict], max_tokens: int = 3200) -> List[Dict]:
        """
        Reduce la cantidad de mensajes para no exceder el límite de tokens
        Mantiene los mensajes del sistema y los mensajes más recientes
        """
        if not messages:
            return []
            
        # Mantener siempre los mensajes del sistema
        system_messages = [msg for msg in messages if msg.get('role') == 'system']
        other_messages = [msg for msg in messages if msg.get('role') != 'system']
        
        total_tokens = sum(self._calculate_tokens(msg.get('content', '')) for msg in system_messages)
        trimmed_messages = system_messages.copy()
        
        # Agregar mensajes recientes hasta alcanzar el límite
        for msg in reversed(other_messages):
            msg_tokens = self._calculate_tokens(msg.get('content', ''))
            if total_tokens + msg_tokens > max_tokens:
                break
            trimmed_messages.insert(len(system_messages), msg)
            total_tokens += msg_tokens
        
        return trimmed_messages

    
    def _looks_like_tool_call_payload(self, text: str) -> bool:
        """Heurística mejorada para detectar fragmentos de payload de tool-call."""
        if not text or not isinstance(text, str):
            return False

        snippet = text.strip()
        if not snippet:
            return False

        # VERIFICACIÓN 1: Estructura de tool call básica
        if snippet.startswith('{') and ('"name"' in snippet or '"function"' in snippet):
            return True
        
        # VERIFICACIÓN 2: JSON con argumentos de herramienta
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                # Estructura de tool call directa
                if "name" in parsed and "arguments" in parsed:
                    return True
                # Estructura de función dentro de tool call
                if "function" in parsed and isinstance(parsed["function"], dict):
                    func = parsed["function"]
                    if "name" in func and "arguments" in func:
                        return True
                # ID de tool call
                if "tool_call_id" in parsed:
                    return True
            elif isinstance(parsed, list) and parsed:
                # Lista de tool calls
                if all(isinstance(item, dict) and ("name" in item or "function" in item) for item in parsed):
                    return True
        except json.JSONDecodeError:
            pass

        # VERIFICACIÓN 3: Tokens específicos de herramientas del SIIED
        tool_indicators = [
            '"name": "explorar_estructura"',
            '"name": "buscar_indicadores"',
            '"name": "consultar_indicador"',
            '"name": "analizar_comparativo"',
            '"name": "explorar_microdatos"',
            '"name": "consultar_iced"',
            '"name": "consultar_ecosistema_datos"',
            '"name": "consultar_producto_academico"',
            '"name": "buscar_documentos_infraestructura"',
            '"name": "consultar_sistemas_informacion"',
            '"name": "consultar_operaciones_estadisticas"',
            '"name": "consultar_satisfaccion"',
            '"arguments": {',
            '"nivel": "',
            '"consulta": "',
            '"indicador_id":',
            '"dominios":',
            '"temas":'
        ]
        
        return any(indicator in snippet for indicator in tool_indicators)

    def _format_tool_results_for_model(self, tool_results: Any) -> str:
        """Convierte la salida de una herramienta en texto legible para el modelo."""
        if tool_results is None:
            return "La herramienta no devolvió resultados."

        try:
            if isinstance(tool_results, str):
                return tool_results.strip()

            if isinstance(tool_results, list):
                if not tool_results:
                    return "La herramienta no encontró elementos relevantes."
                lines = ["Resultados obtenidos:"]
                for idx, item in enumerate(tool_results[:10], 1):
                    if isinstance(item, dict):
                        nombre = item.get('nombre') or item.get('titulo') or 'Elemento sin nombre'
                        descripcion = item.get('descripcion') or item.get('resumen') or ''
                        lines.append(f"{idx}. {nombre}: {descripcion[:200]}")
                    else:
                        lines.append(f"{idx}. {str(item)}")
                if len(tool_results) > 10:
                    lines.append(f"Se omitieron {len(tool_results) - 10} resultados adicionales.")
                return "\n".join(lines)

            if isinstance(tool_results, dict):
                if 'error' in tool_results:
                    return f"La herramienta reportó un error: {tool_results['error']}"

                resultados = tool_results.get('resultados')
                total = tool_results.get('total_encontrados')
                metodo = tool_results.get('metodo_busqueda')
                mensaje = tool_results.get('mensaje')

                lines = []
                if metodo:
                    lines.append(f"Método utilizado: {metodo}.")
                if total is not None:
                    lines.append(f"Total de resultados considerados: {total}.")
                if mensaje:
                    lines.append(mensaje)

                if isinstance(resultados, list) and resultados:
                    lines.append("Resumen de los principales indicadores:")
                    for idx, item in enumerate(resultados[:10], 1):
                        nombre = item.get('nombre') or 'Indicador sin nombre'
                        descripcion = item.get('descripcion') or 'Sin descripción'
                        tema = item.get('tema') or ''
                        dominio = item.get('dominio') or ''
                        similitud = item.get('similitud')
                        partes = [f"{idx}. {nombre}"]
                        if tema:
                            partes.append(f"Tema: {tema}")
                        if dominio:
                            partes.append(f"Dominio: {dominio}")
                        partes.append(f"Descripción: {descripcion[:200]}")
                        if similitud is not None:
                            partes.append(f"Similitud: {similitud}")
                        lines.append(" | ".join(partes))
                    if len(resultados) > 10:
                        lines.append(f"Se omitieron {len(resultados) - 10} indicadores adicionales.")

                if not lines:
                    # Fallback textual
     
                    return json.dumps(tool_results, ensure_ascii=False)[:800]

                return "\n".join(lines)

        except Exception as e:
            logger.warning(f"No se pudo formatear resultado de herramienta para el modelo: {e}")

        # Fallback final
        return json.dumps(tool_results, ensure_ascii=False)[:800]

        
    def _generate_with_tools_stream(self, user_message: str, conversation_history: list):
        """
        Flujo MCP con verificación estricta de tool call payloads
        """
        MAX_TOOL_ROUNDS = get_config('MAX_TOOL_ROUNDS', 3)
        TOOL_TIMEOUT = get_config('TOOL_TIMEOUT_SECONDS', 120)
        
        session_state = {
            'tools_used': set(),
            'last_tool_result': None,
            'has_meaningful_data': False,
            'round': 0,
            'response_ready': False,
            'start_time': timezone.now(),
            'tools_sequence': [],
            'max_chain_length': get_config('MAX_TOOL_CHAIN_LENGTH', 4),
            'max_tool_rounds': MAX_TOOL_ROUNDS
        }
        
        current_history = conversation_history + [{"role": "user", "content": user_message}]
        
        try:
            while session_state['round'] < MAX_TOOL_ROUNDS:
                session_state['round'] += 1
                elapsed = (timezone.now() - session_state['start_time']).total_seconds()
                
                if elapsed > TOOL_TIMEOUT:
                    yield {'content': 'El procesamiento está tardando demasiado. Generando respuesta con los datos disponibles...', 'is_complete': False}
                    break
                
                # Preparar mensajes
                messages = self._build_optimized_messages(current_history, session_state)
                tools = self.tools_service.get_tools_definition() if self.tools_service else []
                
                logger.info(f"[MCP_FIX] Ronda {session_state['round']} - Llamando Cerebras API")
                logger.info(f"[MCP_FIX] Mensajes a enviar: {len(messages)}, Tools: {len(tools)}")
                
                # Log del tamaño de los mensajes
                total_msg_size = sum(len(str(m)) for m in messages)
                logger.info(f"[MCP_FIX] Tamaño total de mensajes: {total_msg_size} caracteres (~{total_msg_size//4} tokens)")
                
                try:
                    # stream=True: deltas progresivos al usuario; tool_calls se
                    # acumulan en _consume_llm_stream
                    response = self._call_llm_with_fallback(
                        messages=messages,
                        model=get_config('CEREBRAS_MODEL', 'gpt-oss-120b'),
                        tools=tools,
                        tool_choice="auto",
                        parallel_tool_calls=True,
                        max_tokens=get_config('CEREBRAS_TOOL_ROUND_MAX_TOKENS', 2500),
                        temperature=0.2,
                        top_p=0.9,
                        stream=True
                    )
                except Exception as e:
                    logger.error(f"[MCP_FIX] Error Cerebras API (sin fallback disponible): {e}")
                    yield {'content': 'Error de conexión. No hay servicio de respaldo disponible.', 'is_complete': False}
                    break
                
                # Consumir el stream: emite deltas de contenido progresivamente
                # y retorna (content, tool_calls, emitted_content)
                final_content, stream_tool_calls, emitted_content = yield from \
                    self._consume_llm_stream(response)
                message = SimpleNamespace(
                    content=final_content, tool_calls=stream_tool_calls)
                
                # Log para debugging: verificar si hay tool_calls
                provider = self.fallback_config.get('base_url', 'fallback').replace('https://', '').replace('http://', '').split('/')[0] if self.using_fallback else "Cerebras"
                has_tool_calls = hasattr(message, 'tool_calls') and message.tool_calls
                logger.info(f"[MCP_FIX] Respuesta de {provider}: tool_calls={has_tool_calls}, content_length={len(final_content)}")
                
                # Verificar si el modelo solicita herramientas
                if has_tool_calls:
                    logger.info(f"[MCP_FIX] Modelo solicita {len(message.tool_calls)} herramientas - PROCESANDO INTERNAMENTE")
                    
                    tools_executed = yield from self._process_tool_calls(
                        message.tool_calls,
                        current_history,
                        session_state,
                        assistant_content=message.content or ""
                    )
                    
                    if tools_executed == 0:
                        logger.info("[MCP_FIX] No hay nuevas herramientas pendientes")
                        session_state['response_ready'] = True
                    
                    should_continue = self._should_continue_with_tools(session_state, tools_executed)
                    if should_continue:
                        session_state['response_ready'] = False
                        continue

                    logger.info("[MCP_FIX] Condiciones cumplidas, forzando respuesta final")
                    session_state['response_ready'] = True
                    continue
                    
                else:
                    # NO HAY TOOL CALLS - respuesta final del LLM
                    final_content = getattr(message, 'content', '') or ""
                    
                    # Log del contenido para debugging
                    logger.info(f"[MCP_FIX] Contenido recibido (primeros 200 chars): {final_content[:200]}")
                    
                    # VERIFICACIÓN ADICIONAL: ¿El contenido parece un tool call?
                    looks_like_tool = self._looks_like_tool_call_payload(final_content)
                    logger.info(f"[MCP_FIX] ¿Parece tool call inline? {looks_like_tool}")
                    
                    # Si el fallback devolvió respuesta final (no tool calls) pero teníamos tools disponibles
                    # Simular feedback de tools para UX consistente
                    if not looks_like_tool and self.using_fallback and tools and len(final_content) > 200:
                        logger.info("[MCP_FIX] Fallback devolvió respuesta procesada - Generando feedback simulado")
                        # Enviar feedback genérico de que se consultaron herramientas
                        yield {
                            'content': '🔍 Consultando base de datos del SIIED...',
                            'is_complete': False,
                            'source': 'progress',
                            'tool_name': 'fallback_internal_tools'
                        }
                    
                    if looks_like_tool:
                        payloads = self._parse_tool_call_payload(final_content)
                        if payloads:
                            logger.info("[MCP_FIX] Payload inline de herramienta detectado. Ejecutando internamente.")
                            synthetic_tool_calls = [self._build_tool_call_namespace(p) for p in payloads]
                            tools_executed = yield from self._process_tool_calls(
                                synthetic_tool_calls,
                                current_history,
                                session_state,
                                assistant_content=final_content
                            )
                            
                            if tools_executed == 0:
                                logger.info("[MCP_FIX] Payload inline sin herramientas nuevas. Solicitando respuesta final.")
                                session_state['response_ready'] = True
                            else:
                                logger.info("[MCP_FIX] Herramientas inline ejecutadas. Solicitando nueva respuesta del modelo.")
                                if len(session_state['tools_sequence']) < session_state['max_chain_length']:
                                    session_state['response_ready'] = False
                            
                            continue
                        
                        logger.warning(f"[MCP_FIX] CONTENIDO PARECE TOOL CALL, FILTRANDO: {final_content[:100]}")
                        # No enviar este contenido, generar fallback
                        break
                    
                    if final_content:
                        logger.info(f"[MCP_FIX] Respuesta final válida recibida después de {session_state['round']} rondas")

                        # Stream de respuesta final — solo si los deltas no
                        # llegaron ya al usuario (evita la respuesta duplicada)
                        if not emitted_content:
                            yield from self._stream_final_response(final_content)
                        
                        # Actualizar historial
                        current_history.append({"role": "assistant", "content": final_content})
                        
                        session_state['response_ready'] = True
                        yield {
                            'content': '',
                            'is_complete': True,
                            'updated_history': current_history
                        }
                        return
                    else:
                        logger.warning("[MCP_FIX] Respuesta final vacía")
                        break
            
            # Intentar obtener respuesta final del modelo sin herramientas si ya hay datos
            if session_state.get('response_ready') and self.client:
                logger.info("[MCP_FIX] Forzando respuesta final del modelo sin herramientas adicionales")
                try:
                    final_messages = self._build_optimized_messages(current_history, session_state)
                    response = self._call_llm_with_fallback(
                        messages=final_messages,
                        model=self.model_config["model"],
                        tool_choice="none",
                        max_tokens=self.model_config["max_tokens"],
                        temperature=self.model_config["temperature"],
                        top_p=self.model_config["top_p"],
                        stream=True
                    )
                    final_content, _tc, emitted_final = yield from \
                        self._consume_llm_stream(response)
                    if final_content:
                        logger.info("[MCP_FIX] Respuesta final obtenida sin herramientas")
                        if not emitted_final:
                            yield from self._stream_final_response(final_content)
                        current_history.append({"role": "assistant", "content": final_content})
                        yield {
                            'content': '',
                            'is_complete': True,
                            'updated_history': current_history
                        }
                        return
                    logger.warning("[MCP_FIX] Respuesta final sin herramientas vacía")
                except Exception as e:
                    logger.error(f"[MCP_FIX] Error solicitando respuesta final sin herramientas: {e}", exc_info=True)

            # FALLBACK cuando no hay respuesta válida
            logger.info(f"[MCP_FIX] Generando fallback. Estado: {session_state}")
            
            fallback_response = self._generate_fallback_response_with_data(
                user_message,
                session_state.get('last_tool_result'),
                session_state.get('has_meaningful_data', False),
                response_ready=session_state.get('response_ready', False)
            )
            
            yield from self._stream_final_response(fallback_response)
            
            current_history.append({"role": "assistant", "content": fallback_response})
            yield {
                'content': '',
                'is_complete': True,
                'updated_history': current_history
            }
            
        except Exception as e:
            logger.error(f"[MCP_FIX] Error crítico: {e}", exc_info=True)
            error_response = "Ocurrió un error procesando tu solicitud. Por favor, intenta con una consulta más específica."
            
            yield {'content': error_response, 'is_complete': False}
            yield {
                'content': '',
                'is_complete': True,
                'updated_history': current_history + [{"role": "assistant", "content": error_response}]
            }


    def _build_optimized_messages(self, history: list, session_state: dict) -> list:
        """Construye mensajes optimizados según el estado de la sesión"""
        messages = []
        
        # Contexto base optimizado según la ronda
        if session_state['round'] == 1:
            system_context = get_context('tools_round_1')
            # Inyectar taxonomía real (dominio → temas) para que el modelo
            # pueda responder 'qué dominios hay' sin depender de herramientas.
            # Persiste en el historial de la sesión para las rondas siguientes.
            taxonomia = self._get_taxonomia_texto()
            if taxonomia:
                system_context += '\n\n' + taxonomia
        else:
            system_context = get_context(
                'tools_round_n',
                round=session_state['round'],
                max_rounds=session_state['max_tool_rounds'],
                tools_used=len(session_state['tools_used']),
                has_data=session_state['has_meaningful_data']
            )
        
        messages.append({"role": "system", "content": system_context})
        
        # Agregar historial reciente
        max_history = get_config('MAX_HISTORY_MESSAGES', 8)
        recent_history = history[-max_history:] if len(history) > max_history else history
        messages.extend(recent_history)
        
        return messages


    def _serialize_tool_call(self, tool_call) -> dict:
        """Serializa tool call para el historial"""
        return {
            "id": tool_call.id,
            "type": "function",
            "function": {
                "name": tool_call.function.name,
                "arguments": tool_call.function.arguments
            }
        }


    def _process_tool_calls(self, tool_calls, current_history, session_state, assistant_content: str = ""):
        """Ejecuta una lista de tool calls y gestiona historial/estado."""
        if not tool_calls:
            return 0

        assistant_tool_calls = []
        tools_to_execute = []

        for tool_call in tool_calls:
            data = self._extract_tool_call_data(tool_call)
            if not data or not data['name']:
                logger.warning("[MCP_FIX] Tool call sin nombre válido, ignorado")
                continue

            signature = self._build_tool_signature(data['name'], data['signature_arguments'])
            if signature in session_state['tools_used']:
                logger.warning(f"[MCP_FIX] Herramienta repetida evitada: {data['name']}")
                continue

            session_state['tools_used'].add(signature)

            assistant_tool_calls.append({
                "id": data['id'],
                "type": "function",
                "function": {
                    "name": data['name'],
                    "arguments": json.dumps(data['assistant_arguments'], ensure_ascii=False)
                }
            })

            tools_to_execute.append({
                'namespace': self._build_tool_call_namespace(data),
                'name': data['name'],
                'signature': signature
            })

        if not tools_to_execute:
            if assistant_tool_calls:
                current_history.append({
                    "role": "assistant",
                    "content": assistant_content or "",
                    "tool_calls": assistant_tool_calls
                })
            return 0

        current_history.append({
            "role": "assistant",
            "content": assistant_content or "",
            "tool_calls": assistant_tool_calls
        })

        tools_executed = 0
        for tool_info in tools_to_execute:
            if len(session_state['tools_sequence']) >= session_state.get('max_chain_length', 4):
                logger.info("[MCP_FIX] Límite de cadena de herramientas alcanzado, deteniendo ejecución adicional")
                session_state['response_ready'] = True
                break

            tool_call = tool_info['namespace']
            try:
                logger.info(f"[MCP_FIX] EJECUTANDO INTERNAMENTE: {tool_call.function.name}")

                tool_result = self.tools_service.execute_tool_call(tool_call)
                session_state['last_tool_result'] = tool_result

                if self._has_meaningful_data(tool_result):
                    session_state['has_meaningful_data'] = True
                    max_chain = session_state.get('max_chain_length', 4)
                    current_length = len(session_state.get('tools_sequence', []))
                    if current_length >= max_chain - 1:
                        session_state['response_ready'] = True
                    else:
                        session_state['response_ready'] = session_state.get('response_ready', False)
                    logger.info(f"[MCP_FIX] Datos significativos encontrados en {tool_call.function.name}")

                tool_content = self._format_tool_result_for_model(tool_result)

                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_content
                }
                current_history.append(tool_message)

                progress_message = f"🔍 Consultando {tool_call.function.name.replace('_', ' ')}..."
                yield {
                    'content': progress_message,
                    'is_complete': False,
                    'source': 'progress',
                    'tool_name': tool_call.function.name
                }

                session_state['tools_sequence'].append({
                    'name': tool_info['name'],
                    'signature': tool_info['signature'],
                    'round': session_state['round']
                })

                tools_executed += 1
                logger.info(f"[MCP_FIX] Herramienta {tool_call.function.name} ejecutada exitosamente")

            except Exception as e:
                logger.error(f"[MCP_FIX] Error ejecutando {tool_call.function.name}: {e}")
                error_message = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps({"error": f"Error ejecutando herramienta: {str(e)}"}, ensure_ascii=False)
                }
                current_history.append(error_message)

        return tools_executed


    def _extract_tool_call_data(self, tool_call) -> Optional[dict]:
        """Normaliza la información de un tool call cualquiera."""
        try:
            if isinstance(tool_call, dict):
                call_id = tool_call.get('id') or str(uuid.uuid4())
                function = tool_call.get('function', {})
                name = function.get('name') or tool_call.get('name')
                raw_arguments = function.get('arguments', tool_call.get('arguments', {}))
            else:
                call_id = getattr(tool_call, 'id', None) or str(uuid.uuid4())
                function = getattr(tool_call, 'function', None)
                name = getattr(function, 'name', None) if function else None
                raw_arguments = getattr(function, 'arguments', {}) if function else {}

            normalized_arguments = self._normalize_tool_arguments(raw_arguments)

            assistant_arguments = normalized_arguments
            if assistant_arguments is None:
                assistant_arguments = {}

            return {
                'id': call_id,
                'name': name,
                'raw_arguments': raw_arguments,
                'assistant_arguments': assistant_arguments,
                'signature_arguments': normalized_arguments if normalized_arguments is not None else {}
            }
        except Exception as e:
            logger.error(f"[MCP_FIX] No se pudo normalizar tool call: {e}")
            return None


    def _normalize_tool_arguments(self, arguments):
        """Convierte argumentos a estructura estable para firmas y logging."""
        if arguments is None:
            return {}
        if isinstance(arguments, (dict, list)):
            return arguments
        if isinstance(arguments, str):
            try:
                return json.loads(arguments)
            except json.JSONDecodeError:
                return arguments.strip()
        return arguments


    def _build_tool_signature(self, name: str, arguments) -> str:
        """Crea firma única para evitar repeticiones."""
        if isinstance(arguments, (dict, list)):
            try:
                arg_repr = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
            except (TypeError, ValueError):
                arg_repr = str(arguments)
        else:
            arg_repr = str(arguments)
        return f"{name}:{arg_repr}"


    def _build_tool_call_namespace(self, tool_data: dict) -> SimpleNamespace:
        """Construye objeto compatible con execute_tool_call."""
        arguments = tool_data.get('raw_arguments')
        if arguments is None:
            arguments = tool_data.get('assistant_arguments', {})
        return SimpleNamespace(
            id=tool_data.get('id') or str(uuid.uuid4()),
            type='function',
            function=SimpleNamespace(
                name=tool_data.get('name'),
                arguments=arguments
            )
        )


    def _parse_tool_call_payload(self, text: str) -> List[dict]:
        """Intenta parsear tool calls embebidos en texto del asistente."""
        if not text or not isinstance(text, str):
            return []

        snippet = text.strip()
        if not snippet:
            return []

        payloads = []

        def _normalize_payload(item):
            if not isinstance(item, dict):
                return None
            function = item.get('function', {}) if isinstance(item.get('function'), dict) else {}
            name = function.get('name') or item.get('name')
            if not name:
                return None
            arguments = function.get('arguments', item.get('arguments', {}))
            return {
                'id': item.get('id') or str(uuid.uuid4()),
                'name': name,
                'arguments': arguments,
                'raw_arguments': arguments
            }

        try:
            parsed = json.loads(snippet)
            items = parsed if isinstance(parsed, list) else [parsed]
            for item in items:
                normalized = _normalize_payload(item)
                if normalized:
                    payloads.append(normalized)
            return payloads
        except json.JSONDecodeError:
            # Intento de extraer objetos JSON individuales
            pattern = r'\{[^{}]*"name"\s*:\s*"[^"]+".*?\}'
            for match in re.finditer(pattern, snippet, flags=re.DOTALL):
                try:
                    candidate = json.loads(match.group())
                    normalized = _normalize_payload(candidate)
                    if normalized:
                        payloads.append(normalized)
                except json.JSONDecodeError:
                    continue
        return payloads


    def _format_tool_result_for_model(self, tool_result) -> str:
        """Formatea resultado de herramienta para el modelo (JSON string requerido)"""
        if isinstance(tool_result, str):
            try:
                # Verificar si ya es JSON válido
                json.loads(tool_result)
                return tool_result
            except json.JSONDecodeError:
                # Si no es JSON, encapsularlo
                return json.dumps({"content": tool_result}, ensure_ascii=False)
        
        # Para dictionaries y otros tipos, serializar directamente
        return json.dumps(tool_result, ensure_ascii=False, default=str)


    def _has_meaningful_data(self, tool_result) -> bool:
        """Verifica si el resultado de la herramienta contiene datos útiles"""
        if not tool_result:
            return False
            
        if isinstance(tool_result, dict):
            # Verificar errores
            if 'error' in tool_result:
                return False
                
            # Verificar si hay resultados
            resultados = tool_result.get('resultados', tool_result.get('datos', []))
            if isinstance(resultados, list) and len(resultados) > 0:
                return True
                
            # Verificar otros campos de datos (incluye nuevos módulos)
            data_fields = [
                'indicadores', 'dominios', 'temas', 'subtemas', 'total_encontrados',
                'productos', 'documentos', 'operaciones', 'ranking',
                'sistemas_consulta', 'productos_informacion', 'flujos', 'clasificaciones',
                'areas', 'secciones', 'total',
            ]
            return any(tool_result.get(field) for field in data_fields)
        
        return bool(str(tool_result).strip())


    def _should_continue_with_tools(self, session_state: dict, tools_executed: int) -> bool:
        """Decide si continuar con herramientas o generar respuesta final"""
        
        max_rounds = session_state.get('max_tool_rounds', 2)
        max_chain = session_state.get('max_chain_length', 4)
        current_chain = len(session_state.get('tools_sequence', []))

        # No continuar si alcanzamos el número máximo de rondas permitidas
        if session_state['round'] >= max_rounds:
            return False
        
        # No continuar si no ejecutamos ninguna herramienta esta ronda
        if tools_executed == 0:
            return False

        # No continuar si alcanzamos el límite total de cadena
        if current_chain >= max_chain:
            return False

        # Si ya marcamos response_ready explícitamente, no continuar
        if session_state.get('response_ready'):
            return False

        tool_names_used = set(item['name'] for item in session_state.get('tools_sequence', []))

        # Herramientas autocontenidas (módulos extendidos): una sola llamada = respuesta completa
        self_contained_tools = {
            'consultar_iced', 'consultar_ecosistema_datos', 'consultar_producto_academico',
            'buscar_documentos_infraestructura', 'consultar_sistemas_informacion',
            'consultar_operaciones_estadisticas', 'consultar_satisfaccion',
            'explorar_estructura', 'explorar_microdatos',
        }
        if tool_names_used & self_contained_tools and session_state.get('has_meaningful_data'):
            return False

        # Flujo de indicadores: si se usó una tool de búsqueda, requiere una de detalle
        indicator_search_tools = {'buscar_indicadores'}
        indicator_detail_tools = {'consultar_indicador', 'obtener_matriz_indicador', 'analizar_comparativo'}
        if tool_names_used & indicator_search_tools:
            if not (tool_names_used & indicator_detail_tools):
                return True  # Busqueda sin detalle → seguir
            if session_state.get('has_meaningful_data'):
                return False  # Tiene detalle + datos → parar

        # Por defecto, continuar solo si aún no hay datos significativos
        return not session_state.get('has_meaningful_data')

    def _stream_final_response(self, content: str):
        """Stream simulado de respuesta final compatible con template"""
        if not content:
            return

        yield {
            'content': content,
            'is_complete': False,
            'source': 'assistant',
            'format': 'markdown'
        }

    def _consume_llm_stream(self, stream):
        """Consume un stream de chat.completions acumulando tool_calls y
        emitiendo deltas de contenido progresivamente.

        Retorna (content, tool_calls, emitted_content) vía `return`
        (usar con `yield from`). Los deltas de contenido se retienen solo
        mientras el texto pueda ser un payload JSON inline de herramienta
        (artefacto del fallback); en cuanto es claramente texto plano se
        emiten en tiempo real para reducir la latencia percibida.
        """
        content_parts = []
        tool_calls_acc = {}   # index -> {id, name, arguments}
        emitted = ''
        hold_buffer = ''    # contenido retenido por si es JSON inline
        HOLD_LIMIT = 300    # chars antes de asumir que no es payload

        for chunk in stream:
            try:
                choices = getattr(chunk, 'choices', None) or []
                choice = choices[0] if choices else None
            except Exception:
                continue
            if not choice:
                continue
            delta = getattr(choice, 'delta', None)
            if not delta:
                continue

            # Deltas de tool calls
            for tc in getattr(delta, 'tool_calls', None) or []:
                idx = getattr(tc, 'index', 0) or 0
                acc = tool_calls_acc.setdefault(
                    idx, {'id': None, 'name': None, 'arguments': ''})
                if getattr(tc, 'id', None):
                    acc['id'] = tc.id
                fn = getattr(tc, 'function', None)
                if fn:
                    if getattr(fn, 'name', None):
                        acc['name'] = fn.name
                    if getattr(fn, 'arguments', None):
                        acc['arguments'] += fn.arguments

            # Deltas de contenido
            piece = getattr(delta, 'content', None)
            if not piece:
                continue
            content_parts.append(piece)

            if tool_calls_acc:
                # El modelo está emitiendo tool calls: no emitir contenido
                continue

            if not emitted:
                hold_buffer += piece
                stripped = hold_buffer.lstrip()
                if not stripped:
                    continue
                if stripped[0] in '{[' and len(hold_buffer) < HOLD_LIMIT:
                    # Posible payload JSON inline: retener
                    continue
                yield {
                    'content': hold_buffer,
                    'is_complete': False,
                    'source': 'assistant',
                    'format': 'markdown'
                }
                emitted += hold_buffer
                hold_buffer = ''
            else:
                yield {
                    'content': piece,
                    'is_complete': False,
                    'source': 'assistant',
                    'format': 'markdown'
                }
                emitted += piece

        content = ''.join(content_parts)
        tool_calls = None
        if tool_calls_acc:
            tool_calls = [
                SimpleNamespace(
                    id=acc['id'] or str(uuid.uuid4()),
                    type='function',
                    function=SimpleNamespace(
                        name=acc['name'], arguments=acc['arguments'])
                )
                for _idx, acc in sorted(tool_calls_acc.items())
            ]
        return content, tool_calls, emitted


    def _generate_fallback_response_with_data(
        self,
        user_message: str,
        last_tool_result,
        has_data: bool,
        response_ready: Optional[bool] = None
    ) -> str:
        """Genera respuesta fallback inteligente basada en datos disponibles"""

        if has_data and isinstance(last_tool_result, dict):
            if 'resultados' in last_tool_result:
                total = len(last_tool_result['resultados'])
                return (
                    f"Encontré información relacionada con tu consulta \"{user_message}\".\n\n"
                    f"Se identificaron {total} elementos relevantes en el SIIED. Aunque no pude procesar completamente la búsqueda, "
                    "estos datos están disponibles en el sistema.\n\n"
                    "¿Te gustaría que reformule tu consulta de manera más específica para obtener mejores resultados?"
                )

            if 'datos' in last_tool_result:
                return (
                    f"He consultado el SIIED sobre \"{user_message}\" y encontré información estructural disponible.\n\n"
                    "El sistema tiene datos organizados, pero necesito que seas más específico en tu consulta para darte la respuesta "
                    "exacta que buscas.\n\n"
                    "Por ejemplo, puedes preguntar por:\n"
                    "- Un dominio específico\n"
                    "- Un indicador particular\n"
                    "- Un período de tiempo concreto"
                )

        if response_ready:
            return (
                f"Intenté generar una respuesta final para \"{user_message}\", pero el servicio externo está temporalmente saturado.\n\n"
                "Mientras se restablece, puedes reformular la consulta o explorar otras preguntas relacionadas con los indicadores disponibles."
            )

        return (
            f"No encontré información específica para \"{user_message}\" en el SIIED en este momento.\n\n"
            "Esto puede ocurrir por varias razones:\n"
            "- Los términos de búsqueda pueden ser muy generales o muy específicos\n"
            "- Los datos pueden estar organizados con nombres diferentes\n"
            "- Puede ser información que no está disponible públicamente\n\n"
            "Te sugiero reformular tu consulta con términos más específicos o preguntarme sobre las categorías disponibles en el sistema."
        )

    def generate_response_stream(self, user_message, relevant_data=None, conversation_history=None):
        """
        VERSIÓN CORREGIDA que evita bypass del MCP
        """
        logger.info("[STREAM_FIX] Iniciando generate_response_stream")
        
        if not user_message or not isinstance(user_message, str) or not user_message.strip():
            yield {
                "content": "Por favor, proporciona un mensaje válido.",
                'is_complete': True,
                'source': 'system'
            }
            return
        
        user_message = user_message.strip()
        
        try:
            clean_history = self._clean_conversation_history(conversation_history)
            max_history = get_config('MAX_HISTORY_MESSAGES', 8)
            clean_history = clean_history[-max_history:]
            
            intent_analysis = self._analyze_query_intent(user_message)
            logger.info(f"[STREAM_FIX] Análisis: {intent_analysis}")
            
            # USAR HERRAMIENTAS - sin bypass
            if self._should_use_tools(user_message):
                logger.info("[STREAM_FIX] Usando herramientas MCP - SIN BYPASS")
                
                try:
                    # USAR SOLO el flujo MCP - no alternativas
                    for chunk in self._generate_with_tools_stream(user_message, clean_history):
                        # VERIFICAR que no enviamos tool call payloads
                        if isinstance(chunk, dict) and 'content' in chunk:
                            content = chunk.get('content', '')
                            if content and self._looks_like_tool_call_payload(content):
                                logger.warning(f"[STREAM_FIX] PAYLOAD FILTRADO: {content[:50]}")
                                continue  # NO enviar este chunk
                        
                        yield chunk
                        
                except Exception as e:
                    logger.error(f"[STREAM_FIX] Error en MCP: {e}", exc_info=True)
                    
                    # Fallback simple SIN herramientas
                    error_msg = "Tuve un problema procesando tu solicitud. ¿Podrías reformularla de manera más específica?"
                    updated_history = clean_history + [
                        {'role': 'user', 'content': user_message},
                        {'role': 'assistant', 'content': error_msg}
                    ]
                    
                    yield {"content": error_msg, "is_complete": False}
                    yield {'is_complete': True, 'updated_history': updated_history}
            else:
                # Respuestas simples sin herramientas (conversación casual)
                logger.info("[STREAM_FIX] Conversación casual detectada por clasificador - sin herramientas")
                
                # Confiar en el clasificador, NO hardcodear saludos
                # El LLM manejará saludos, despedidas y conversación casual naturalmente
                try:
                    full_response = ""
                    for chunk in self._generate_traditional_stream(user_message, relevant_data, clean_history):
                        if 'content' in chunk and chunk['content']:
                            full_response += chunk['content']
                        yield chunk
                    
                    if full_response:
                        updated_history = clean_history + [
                            {'role': 'user', 'content': user_message},
                            {'role': 'assistant', 'content': full_response}
                        ]
                        yield {'is_complete': True, 'updated_history': updated_history}
                        
                except Exception as e:
                    logger.error(f"[STREAM_FIX] Error en conversación casual: {e}")
                    error_msg = "Error procesando solicitud."
                    yield {"content": error_msg, "is_complete": True}
                        
        except Exception as e:
            logger.error(f"[STREAM_FIX] Error general: {e}", exc_info=True)
            yield {"content": "Error inesperado.", "is_complete": True, 'error': True}
        finally:
            logger.info("[STREAM_FIX] Finalizado generate_response_stream")

    def format_tool_results_for_display(self, tool_results: Dict[str, Any]) -> str:
        """
        Formatea los resultados de las herramientas para mostrarlos al usuario.
        
        Args:
            tool_results: Resultados de la herramienta a formatear
            
        Returns:
            str: Texto formateado para mostrar al usuario
        """
        if not tool_results:
            return "No se encontraron resultados."
            
        # Si es un string, devolverlo directamente
        if isinstance(tool_results, str):
            return tool_results
            
        # Si es un diccionario con un error
        if isinstance(tool_results, dict) and 'error' in tool_results:
            return f"Error: {tool_results['error']}"
            
        # Si es una lista de resultados
        if isinstance(tool_results, list):
            if not tool_results:
                return "No se encontraron resultados."
                
            if all(isinstance(item, dict) for item in tool_results):
                lines = ["🔎 **Resultados encontrados:**"]
                for i, item in enumerate(tool_results[:20], 1):
                    nombre = item.get('nombre') or item.get('titulo') or 'Sin nombre'
                    descripcion = item.get('descripcion') or item.get('resumen') or ''
                    tema = item.get('tema') or ''
                    dominio = item.get('dominio') or ''
                    unidad = item.get('unidad_medida') or ''
                    similitud = item.get('similitud')
                    lines.append(f"{i}. **{nombre}**")
                    if descripcion:
                        lines.append(f"   {descripcion[:200]}" + ('…' if len(descripcion) > 200 else ''))
                    if tema or dominio:
                        lines.append(f"   Clasificación: {tema or 'N/A'} / {dominio or 'N/A'}")
                    if unidad:
                        lines.append(f"   Unidad: {unidad}")
                    if similitud is not None:
                        lines.append(f"   Similitud: {similitud}")
                    lines.append("")
                if len(tool_results) > 20:
                    lines.append(f"Mostrando 20 de {len(tool_results)} resultados. Afina tu consulta para obtener resultados más específicos.")
                return "\n".join(lines)

        if isinstance(tool_results, dict):
            if not tool_results:
                return "No se obtuvo información de la herramienta."
            if 'error' in tool_results:
                return f"⚠️ La herramienta reportó un error: {tool_results['error']}"

            mensaje = tool_results.get('mensaje')
            resultados = tool_results.get('resultados')
            total = tool_results.get('total_encontrados')
            metodo = tool_results.get('metodo_busqueda')
            resultados_semanticos = tool_results.get('resultados_semanticos')

            lines = []
            if mensaje:
                lines.append(mensaje)
            if metodo:
                lines.append(f"Método de búsqueda utilizado: {metodo}.")
            if total is not None:
                lines.append(f"Total de indicadores encontrados: {total}.")

            def _render_items(items, titulo):
                if not items:
                    return
                lines.append("")
                lines.append(titulo)
                for i, item in enumerate(items[:20], 1):
                    nombre = item.get('nombre') or item.get('titulo') or 'Sin nombre'
                    descripcion = item.get('descripcion') or item.get('resumen') or 'Sin descripción'
                    tema = item.get('tema') or ''
                    dominio = item.get('dominio') or ''
                    similitud = item.get('similitud')
                    lines.append(f"{i}. **{nombre}**")
                    if descripcion:
                        lines.append(f"   {descripcion[:200]}" + ('…' if len(descripcion) > 200 else ''))
                    if tema or dominio:
                        lines.append(f"   Clasificación: {tema or 'N/A'} / {dominio or 'N/A'}")
                    if similitud is not None:
                        lines.append(f"   Similitud: {similitud}")
                    lines.append("")
                if len(items) > 20:
                    lines.append(f"Mostrando 20 de {len(items)} entradas disponibles.")

            if isinstance(resultados, list) and resultados:
                _render_items(resultados, "🔎 **Indicadores encontrados:**")
            elif isinstance(resultados_semanticos, list) and resultados_semanticos:
                lines.append("No se hallaron resultados que cumplieran los filtros. Se muestran coincidencias semánticas relevantes:")
                _render_items(resultados_semanticos, "📌 **Sugerencias semánticas:**")
            else:
                lines.append("No se encontraron indicadores para la búsqueda solicitada.")

            return "\n".join(lines)

        return str(tool_results)


    def _generate_traditional_stream(self, user_message: str, relevant_data=None, conversation_history=None):
        """
        Generación tradicional con streaming real corregido
        
        Args:
            user_message: Mensaje del usuario
            relevant_data: Datos relevantes para el contexto (opcional)
            conversation_history: Historial de la conversación (opcional)
            
        Yields:
            Dict con los chunks de la respuesta y metadatos, incluyendo el historial actualizado
        """
        # Crear una copia del historial para no modificar el original
        updated_history = conversation_history.copy() if conversation_history else []
        
        try:
            # Construir contexto conversacional
            system_context = self._get_conversational_context()
            messages = [{"role": "system", "content": system_context}]
            
            # Integrar datos relevantes si existen
            if relevant_data:
                context_data = self._format_relevant_data_for_context(relevant_data)
                if context_data:
                    messages.append({
                        "role": "system", 
                        "content": get_context('relevant_data_template', data=context_data)
                    })
            
            # Agregar historial optimizado
            if updated_history:
                max_history = get_config('MAX_HISTORY_MESSAGES', 8)
                max_length = get_config('MAX_MESSAGE_LENGTH', 1000)
                recent_history = updated_history[-max_history:]
                for msg in recent_history:
                    if msg.get('content') and msg.get('role') in ['user', 'assistant']:
                        content = msg['content'][:max_length]
                        messages.append({"role": msg['role'], "content": content})
            
            # Mensaje del usuario
            messages.append({"role": "user", "content": user_message})
            
            # Agregar el mensaje del usuario al historial actualizado
            updated_history.append({
                'role': 'user',
                'content': user_message
            })
            
            # VERIFICAR que tenemos un cliente válido
            if not self.client:
                logger.error("Cliente Cerebras no inicializado")
                error_msg = "Error: Cliente no disponible"
                updated_history.append({
                    'role': 'assistant',
                    'content': error_msg
                })
                yield {
                    "content": error_msg, 
                    "is_complete": True, 
                    "source": "client_error",
                    'updated_history': updated_history
                }
                return
            
            try:
                # Llamada streaming a Cerebras con fallback
                stream = self._call_llm_with_fallback(
                    messages=messages,
                    model=self.model_config["model"],
                    max_tokens=self.model_config["max_tokens"], 
                    temperature=self.model_config["temperature"],
                    top_p=self.model_config["top_p"],
                    stream=True  # CRÍTICO: Asegurar que stream=True
                )
                
                provider = self.fallback_config.get('base_url', 'fallback').replace('https://', '').replace('http://', '').split('/')[0] if self.using_fallback else "Cerebras"
                logger.info(f"✅ Stream iniciado desde {provider}")
                
                # Procesar streaming con manejo robusto de errores y timeout
                chunk_count = 0
                full_response = ""
                import time
                start_time = time.time()
                timeout = get_config('OLLAMA_STREAM_TIMEOUT_SECONDS', 180)
                
                for chunk in stream:
                    # Verificar timeout
                    if time.time() - start_time > timeout:
                        logger.error(f"⏱️ Timeout en streaming después de {timeout}s")
                        raise TimeoutError(f"Stream timeout después de {timeout} segundos")
                    
                    try:
                        if chunk and chunk.choices and len(chunk.choices) > 0:
                            choice = chunk.choices[0]
                            if hasattr(choice, 'delta') and choice.delta and hasattr(choice.delta, 'content'):
                                content = choice.delta.content
                                if content:
                                    chunk_count += 1
                                    if chunk_count == 1:
                                        logger.info(f"📥 Primer chunk recibido de {provider}")
                                    full_response += content
                                    yield {
                                        "content": content, 
                                        "is_complete": False, 
                                        "source": "traditional",
                                        "chunk_number": chunk_count
                                    }
                    except Exception as chunk_error:
                        logger.warning(f"⚠️ Error procesando chunk: {chunk_error}")
                        continue
                
                logger.info(f"Stream completado. Total chunks: {chunk_count}")
                
                # Agregar la respuesta al historial actualizado
                if full_response:
                    updated_history.append({
                        'role': 'assistant',
                        'content': full_response
                    })
                
                # Devolver el historial actualizado como parte del último chunk
                yield {
                    'is_complete': True,
                    'updated_history': updated_history
                }
                
            except Exception as api_error:
                logger.error(f"Error en API Cerebras: {api_error}", exc_info=True)
                error_msg = "Lo siento, ocurrió un error al procesar tu solicitud. Por favor, inténtalo de nuevo más tarde."
                updated_history.append({
                    'role': 'assistant',
                    'content': error_msg
                })
                yield {
                    "content": error_msg, 
                    "is_complete": True, 
                    "source": "api_error",
                    'updated_history': updated_history
                }
                
        except Exception as e:
            logger.error(f"Error inesperado en _generate_traditional_stream: {e}", exc_info=True)
            error_msg = "Lo siento, ocurrió un error inesperado. Por favor, inténtalo de nuevo más tarde."
            updated_history.append({
                'role': 'assistant',
                'content': error_msg
            })
            yield {
                "content": error_msg,
                "is_complete": True,
                "source": "error",
                'updated_history': updated_history
            }

    def _format_relevant_data_for_context(self, relevant_data: dict) -> str:
        """Formatea los datos relevantes para incluir en el contexto"""
        if not relevant_data:

            return ""
        
        formatted_parts = []
        
        # Formatear dominios
        if 'dominios' in relevant_data and relevant_data['dominios']:
            formatted_parts.append("DOMINIOS DEL SIIED:")
            for i, dominio in enumerate(relevant_data['dominios'], 1):
                nombre = dominio.get('nombre', 'Sin nombre')
                descripcion = dominio.get('descripcion', 'Sin descripción')
                formatted_parts.append(f"{i}. {nombre}")
                if descripcion and descripcion != 'Sin descripción':
                    formatted_parts.append(f"   Descripción: {descripcion}")
                formatted_parts.append("")  # Línea en blanco
        
        # Formatear indicadores
        if 'indicadores' in relevant_data and relevant_data['indicadores']:
            formatted_parts.append("INDICADORES DISPONIBLES:")
            for i, indicador in enumerate(relevant_data['indicadores'], 1):
                nombre = indicador.get('nombre', 'Sin nombre')
                descripcion = indicador.get('descripcion', '')
                unidad = indicador.get('unidad_medida', '')
                subtema = indicador.get('subtema__nombre', '')
                
                formatted_parts.append(f"{i}. {nombre}")
                if descripcion:
                    formatted_parts.append(f"   Descripción: {descripcion}")
                if unidad:
                    formatted_parts.append(f"   Unidad: {unidad}")
                if subtema:
                    formatted_parts.append(f"   Subtema: {subtema}")
                formatted_parts.append("")  # Línea en blanco
        
        # Formatear eventos
        if 'eventos' in relevant_data and relevant_data['eventos']:
            formatted_parts.append("EVENTOS PRÓXIMOS:")
            for i, evento in enumerate(relevant_data['eventos'], 1):
                nombre = evento.get('nombre', 'Sin nombre')
                fecha = evento.get('fecha_inicio', '')
                lugar = evento.get('lugar', '')
                
                formatted_parts.append(f"{i}. {nombre}")
                if fecha:
                    formatted_parts.append(f"   Fecha: {fecha}")
                if lugar:
                    formatted_parts.append(f"   Lugar: {lugar}")
                formatted_parts.append("")  # Línea en blanco
        
        # Formatear documentos
        if 'documentos' in relevant_data and relevant_data['documentos']:
            formatted_parts.append("DOCUMENTOS RELACIONADOS:")
            for i, doc in enumerate(relevant_data['documentos'], 1):
                nombre = doc.get('nombre', 'Sin nombre')
                descripcion = doc.get('descripcion', '')
                tipo = doc.get('tipo_documento', '')
                
                formatted_parts.append(f"{i}. {nombre}")
                if descripcion:
                    formatted_parts.append(f"   Descripción: {descripcion}")
                if tipo:
                    formatted_parts.append(f"   Tipo: {tipo}")
                formatted_parts.append("")  # Línea en blanco
        
        return "\n".join(formatted_parts) if formatted_parts else ""

    def _get_conversational_context(self) -> str:
        """Contexto optimizado para conversación sin herramientas"""
        return get_context('conversational')
    def _calcular_similitud(self, vec1: List[float], vec2: List[float]) -> Optional[float]:
        """Calcula la similitud del coseno entre dos vectores"""
        try:
 
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            
            norma1 = np.linalg.norm(vec1)
            norma2 = np.linalg.norm(vec2)
            
            if norma1 == 0 or norma2 == 0:
                return 0.0
                
            return float(np.dot(vec1, vec2) / (norma1 * norma2))
            
        except Exception as e:
            logger.error(f"Error al calcular similitud: {str(e)}")
            return None
   
    def search_relevant_data(self, query: str, top_k: int = None) -> Dict:
        """
        Busca documentos relevantes usando embeddings semánticos.
        
        Args:
            query: Texto de búsqueda
            top_k: Número máximo de resultados a devolver (None para sin límite)
            
        Returns:
            Dict con los resultados de búsqueda enriquecidos
        """
        try:
 
     
       
            
            logger.info(f"Iniciando búsqueda semántica para: {query}")
            # Singleton: reutiliza el modelo ya cargado en el proceso
            embedding_service = get_embedding_service()

            # Obtener el embedding de la consulta
            query_embedding = embedding_service.get_embedding(query)
            if not query_embedding:
                error_msg = "No se pudo generar el embedding de la consulta"
                logger.error(error_msg)
                return {"results": [], "error": error_msg}

            # Inicializar diccionario para agrupar resultados por tipo
            resultados_por_tipo = {
                'dominio': [],
                'tema': [],
                'subtema': [],
                'indicador': [],
                'documento': []
            }

            # Búsqueda con pgvector (CosineDistance en BD con índice) en lugar
            # de iterar todos los vectores y calcular coseno en Python.
            from pgvector.django import CosineDistance

            limite_total = (top_k or 10) * 10  # candidatos suficientes por tipo
            max_data_length = get_config('MAX_RELEVANT_DATA_LENGTH', 500)

            documentos = (
                DocumentoVector.objects
                .exclude(Q(embedding__isnull=True) | Q(contenido__isnull=True) | Q(contenido=''))
                .annotate(distancia=CosineDistance('embedding', query_embedding))
                .filter(distancia__lt=0.9)  # equivalente a similitud > 0.1
                .order_by('distancia')[:limite_total]
            )
            logger.info(f"Recuperados {len(documentos)} candidatos vía pgvector")

            # Metadatos de indicadores en una sola consulta (evita N+1)
            ref_ids = [d.referencia_id for d in documentos if d.tipo == 'indicador']
            indicadores_map = {
                ind.id: ind for ind in Indicador.objects.filter(id__in=ref_ids)
            } if ref_ids else {}

            for doc in documentos:
                try:
                    similarity = 1 - float(doc.distancia)
                    resultado = {
                        'id': doc.id,
                        'tipo': doc.tipo,
                        'referencia_id': doc.referencia_id,
                        'similitud': similarity,
                        'contenido': doc.contenido[:max_data_length] + '...' if len(doc.contenido) > max_data_length else doc.contenido,
                        'metadata': doc.metadata or {}
                    }

                    if doc.tipo == 'indicador':
                        indicador = indicadores_map.get(doc.referencia_id)
                        if indicador:
                            resultado.update({
                                'nombre': getattr(indicador, 'nombre', ''),
                                'descripcion': getattr(indicador, 'descripcion', ''),
                                'unidad_medida': getattr(indicador, 'unidad_medida', ''),
                                'fuente': getattr(indicador, 'fuente', ''),
                            })

                    if doc.tipo in resultados_por_tipo:
                        resultados_por_tipo[doc.tipo].append(resultado)
                    else:
                        resultados_por_tipo['documento'].append(resultado)

                except Exception as e:
                    logger.error(f"Error procesando documento {getattr(doc, 'id', 'unknown')}: {str(e)}", exc_info=True)
                    continue

            # Ordenar resultados por similitud (de mayor a menor)
            for tipo in resultados_por_tipo:
                resultados_por_tipo[tipo].sort(key=lambda x: x['similitud'], reverse=True)
                
                # Aplicar límite si se especificó
                if top_k is not None and top_k > 0:
                    resultados_por_tipo[tipo] = resultados_por_tipo[tipo][:top_k]
            
            # Calcular estadísticas
            total_resultados = sum(len(v) for v in resultados_por_tipo.values())
            logger.info(f"Búsqueda completada. Total de resultados: {total_resultados}")
            
            # Crear respuesta final
            response = {
                'query': query,
                'total_resultados': total_resultados,
                'resultados_por_tipo': resultados_por_tipo,
                'estadisticas': {
                    tipo: len(resultados) for tipo, resultados in resultados_por_tipo.items()
                },
                'timestamp': timezone.now().isoformat()
            }
            
            return response

        except Exception as e:
            error_msg = f"Error en search_relevant_data: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'error': error_msg,
                'query': query,
                'results': []
            }


    def _analyze_query_intent(self, query: str) -> dict:
        """
        Analiza la intención de la consulta del usuario y detecta el tipo de búsqueda.
        
        Returns:
            dict: Diccionario con banderas que indican el tipo de búsqueda
                - is_search: Si es una búsqueda general
                - is_question: Si es una pregunta
                - seeks_domains: Si busca dominios/áreas
                - seeks_themes: Si busca temas
                - seeks_subthemes: Si busca subtemas
                - seeks_indicators: Si busca indicadores
                - seeks_documents: Si busca documentos
                - seeks_geography: Si busca información geográfica
                - seeks_operations: Si busca operaciones estadísticas
                - seeks_events: Si busca eventos o noticias
                - seeks_conjunto_datos: Si busca conjuntos_datos o datasets
                - query: La consulta original
                - query_terms: Términos individuales de la consulta para búsquedas
        """
        query = query.lower().strip()
        
        # Palabras clave generales de búsqueda
        search_keywords = [
            'buscar', 'encontrar', 'mostrar', 'ver', 'datos de', 'información sobre',
            'estadísticas de', 'necesito información', 'quién tiene', 'dónde está',
            'cuántos', 'cuántas', 'cuál es', 'cuáles son', 'lista de', 'mostrar',
            'listar', 'consultar', 'obtener', 'traer', 'necesito', 'quiero ver',
            'muéstrame', 'dame', 'muestra', 'busco', 'estoy buscando'
        ]
        
        # Palabras clave específicas por tipo de búsqueda
        domain_keywords = [
            'dominio', 'dominios', 'área', 'áreas', 'categoría', 'categorías',
            'clasificación', 'estructura', 'organización', 'sector', 'sectores'
        ]
        
        theme_keywords = [
            'tema', 'temas', 'eje temático', 'eje', 'tema principal', 'temas principales',
            'categoría principal', 'categorías principales', 'área temática'
        ]
        
        subtheme_keywords = [
            'subtema', 'subtemas', 'subcategoría', 'subcategorías', 'subárea',
            'subáreas', 'tema específico', 'temas específicos'
        ]
        
        indicator_keywords = [
            'indicador', 'indicadores', 'estadística', 'estadísticas', 'dato', 'datos',
            'métrica', 'métricas', 'medición', 'mediciones', 'kpi', 'kpis',
            'indicador clave', 'indicadores clave'
        ]
        
        document_keywords = [
            'documento', 'documentos', 'informe', 'informes', 'reporte', 'reportes',
            'publicación', 'publicaciones', 'archivo', 'archivos', 'pdf', 'word',
            'excel', 'presentación', 'estudio', 'estudios', 'análisis', 'análisis',
            'investigación', 'investigaciones'
        ]
        
        geography_keywords = [
            'geográfico', 'geográfica', 'geográficos', 'geográficas', 'ubicación',
            'ubicaciones', 'región', 'regiones', 'departamento', 'departamentos',
            'municipio', 'municipios', 'ciudad', 'ciudades', 'localidad', 'localidades',
            'barrio', 'barrios', 'vereda', 'veredas', 'zona', 'zonas', 'territorio',
            'territorios', 'mapa', 'mapas', 'espacial', 'espaciales'
        ]
        
        operation_keywords = [
            'operación', 'operaciones', 'encuesta', 'encuestas', 'censo',
            'estudio', 'estudios', 'investigación', 'recopilación'
        ]
        
        event_keywords = [
            'evento', 'eventos', 'noticia', 'noticias', 'novedad', 'novedades',
            'actividad', 'actividades', 'calendario', 'agenda', 'próximos eventos'
        ]
        
        conjunto_datos_keywords = [
            'microdato', 'conjuntos_datos', 'datos crudos', 'dataset', 'datasets',
            'base de datos', 'datos abiertos', 'conjunto de datos'
        ]
        
        # Preguntas comunes
        question_words = ['qué', 'cuándo', 'dónde', 'cómo', 'por qué', 'quién', 'cuál', 'cuáles']
        
        # Determinar si es una búsqueda
        is_search = (
            any(keyword in query for keyword in search_keywords) or
            query.split()[0] in question_words or
            len(query.split()) > 3  # Consultas más largas probablemente sean búsquedas
        )
        
        # Detección de tipos específicos de búsqueda
        seeks_domains = any(term in query for term in domain_keywords)
        seeks_themes = any(term in query for term in theme_keywords)
        seeks_subthemes = any(term in query for term in subtheme_keywords)
        seeks_indicators = any(term in query for term in indicator_keywords)
        seeks_documents = any(term in query for term in document_keywords)
        seeks_geography = any(term in query for term in geography_keywords)
        seeks_operations = any(term in query for term in operation_keywords)
        seeks_events = any(term in query for term in event_keywords)
        seeks_conjunto_datos = any(term in query for term in conjunto_datos_keywords)
        

        
        try:
            # Tokenizar y limpiar la consulta
            stop_words = set(stopwords.words('spanish'))
            tokens = word_tokenize(query.lower(), language='spanish')
            query_terms = [word for word in tokens if word.isalnum() and word not in stop_words and word not in string.punctuation]
        except:
            # En caso de error, usar un enfoque simple
            query_terms = [word for word in query.lower().split() if len(word) > 2]
        
        # Si no se detectó un tipo específico pero hay términos de búsqueda, asumir que busca indicadores
        if is_search and not any([seeks_domains, seeks_themes, seeks_subthemes, 
                                seeks_indicators, seeks_documents, seeks_geography,
                                seeks_operations, seeks_events, seeks_conjunto_datos]):
            seeks_indicators = True
        
        return {
            'is_search': is_search,
            'is_question': any(query.startswith(q) for q in question_words),
            'seeks_domains': seeks_domains,
            'seeks_themes': seeks_themes,
            'seeks_subthemes': seeks_subthemes,
            'seeks_indicators': seeks_indicators,
            'seeks_documents': seeks_documents,
            'seeks_geography': seeks_geography,
            'seeks_operations': seeks_operations,
            'seeks_events': seeks_events,
            'seeks_conjunto_datos': seeks_conjunto_datos,
            'query': query,
            'query_terms': query_terms
        }

    def _search_dominios(self, query: str, analysis: dict):
        """Búsqueda mejorada de dominios con manejo de casos especiales"""
        try:
            # Búsqueda base
            dominios_query = MenuDominio.objects.filter(activo=True)
            
            # Filtros por términos específicos
            search_terms = analysis.get('query_terms', [])
            if search_terms:
                q_objects = Q()
                for term in search_terms:
                    if len(term) > 2:  # Solo buscar términos con más de 2 caracteres
                        q_objects |= Q(nombre__icontains=term) | Q(descripcion__icontains=term)
                
                if q_objects:  # Solo aplicar filtro si hay condiciones válidas
                    dominios_query = dominios_query.filter(q_objects)
            
            # Ordenar por orden y luego por nombre
            dominios = dominios_query.values(
                'id', 'nombre', 'descripcion', 'orden'
            ).order_by('orden', 'nombre')[:10]  # Aumentar límite a 10
            
            dominios_list = list(dominios)
            
            # Si no hay resultados, verificar si hay algún problema con los datos
            if not dominios_list:
                logger.warning(f"No se encontraron dominios activos. Total en BD: {MenuDominio.objects.count()}")
                
            return dominios_list
            
        except Exception as e:
            logger.error(f"Error buscando dominios: {e}", exc_info=True)
            return []

    def _search_temas_subtemas(self, query: str, analysis: dict) -> dict:
        """Búsqueda mejorada de temas y subtemas con más flexibilidad"""
        result = {'temas': [], 'subtemas': []}
        
        try:
            search_terms = analysis.get('query_terms', [])
            
            # Si no hay términos de búsqueda pero se piden "todos" o similar
            if not search_terms and any(word in query.lower() for word in ['todos', 'listar', 'mostrar', 'ver']):
                search_terms = ['']
            
            # Buscar temas
            temas_q = Q(activo=True)
            if search_terms:
                temas_search = Q()
                for term in search_terms:
                    if term:  # Solo buscar términos no vacíos
                        temas_search |= (
                            Q(nombre__icontains=term) | 
                            Q(descripcion__icontains=term)
                        )
                temas_q &= temas_search
            
            temas = MenuTema.objects.filter(temas_q).select_related('dominio').values(
                'id', 'nombre', 'descripcion', 'dominio__nombre', 'orden'
            ).order_by('dominio__orden', 'orden', 'nombre')[:10]  # Aumentar límite a 10
            
            result['temas'] = list(temas)
            
            # Buscar subtemas
            subtemas_q = Q(activo=True)
            if search_terms:
                subtemas_search = Q()
                for term in search_terms:
                    if term:  # Solo buscar términos no vacíos
                        subtemas_search |= (
                            Q(nombre__icontains=term) | 
                            Q(descripcion__icontains=term) |
                            Q(tema__nombre__icontains=term) |
                            Q(tema__dominio__nombre__icontains=term)
                        )
                subtemas_q &= subtemas_search
            
            subtemas = MenuSubtema.objects.filter(subtemas_q).select_related(
                'tema__dominio'
            ).values(
                'id', 'nombre', 'descripcion', 'tema__nombre', 
                'tema__dominio__nombre', 'orden', 'tema__orden'
            ).order_by('tema__dominio__orden', 'tema__orden', 'orden', 'nombre')[:10]
            
            result['subtemas'] = list(subtemas)
            
            # Log de depuración
            if not result['temas'] and not result['subtemas']:
                logger.debug(f"No se encontraron temas/subtemas para: {query}")
            
            return result
                
        except Exception as e:
            logger.error(f"Error buscando temas/subtemas: {e}", exc_info=True)
            return {'error': str(e)}

    def _search_indicadores(self, query: str, analysis: dict, limit: int = 10, offset: int = 0) -> dict:
        """Búsqueda avanzada de indicadores con mejoras de rendimiento y relevancia"""
        logger.info(f"[SEARCH_INDICADORES] Iniciando búsqueda con query: '{query}'")
        logger.debug(f"[SEARCH_INDICADORES] Análisis recibido: {analysis}")
        
        try:

            # Lista ampliada de stop words
            stop_words = {
                'que', 'qué', 'cual', 'cuál', 'como', 'cómo', 'donde', 'dónde', 'cuando', 
                'cuándo', 'porque', 'por qué', 'está', 'estan', 'están', 'disponible', 'disponibles',
                'los', 'las', 'un', 'una', 'unos', 'unas', 'de', 'del', 'al', 'el', 'la', 'los', 
                'las', 'y', 'o', 'pero', 'a', 'ante', 'bajo', 'cabe', 'con', 'contra', 'de', 'desde',
                'en', 'entre', 'hacia', 'hasta', 'mediante', 'para', 'por', 'según', 'sin', 'so', 'sobre',
                'tras', 'durante', 'mediante', 'versus', 'vía', 'son', 'es', 'sea', 'sean', 'fue', 'fueron',
                'ha', 'han', 'he', 'hemos', 'haber', 'tiene', 'tienen', 'tener', 'tuvo', 'tuvieron', 'tener',
                'cada', 'con', 'entre', 'este', 'esta', 'estos', 'estas', 'ese', 'esa', 'esos', 'esas',
                'aquel', 'aquella', 'aquellos', 'aquellas', 'otro', 'otra', 'otros', 'otras', 'tal', 'tales',
                'cual', 'cuales', 'cuanto', 'cuanta', 'cuantos', 'cuantas', 'donde', 'cuando', 'como',
                'más', 'menos', 'poco', 'mucho', 'todo', 'nada', 'algo', 'alguno', 'alguna', 'algunos',
                'algunas', 'ninguno', 'ninguna', 'ningunos', 'ningunas', 'ambos', 'ambas', 'varios', 'varias',
                'cualquier', 'cualesquiera', 'demás', 'mismo', 'misma', 'mismos', 'mismas', 'tan', 'tanto',
                'tanta', 'tantos', 'tantas', 'suyo', 'suya', 'suyos', 'suyas', 'mío', 'mía', 'míos', 'mías',
                'tuyo', 'tuya', 'tuyos', 'tuyas', 'nuestro', 'nuestra', 'nuestros', 'nuestras', 'vuestro',
                'vuestra', 'vuestros', 'vuestras', 'cuyo', 'cuya', 'cuyos', 'cuyas', 'cuánto', 'cuánta',
                'cuántos', 'cuántas', 'cuándo', 'dónde', 'cómo', 'por qué', 'para qué', 'sin embargo',
                'no obstante', 'aunque', 'aun cuando', 'a pesar de', 'pese a', 'debido a', 'gracias a',
                'además', 'también', 'así mismo', 'igualmente', 'de igual manera', 'de igual forma',
                'por ejemplo', 'es decir', 'o sea', 'en otras palabras', 'en resumen', 'en conclusión',
                'finalmente', 'por último', 'por otra parte', 'por otro lado', 'en cambio', 'por el contrario',
                'ahora bien', 'no obstante', 'sin embargo', 'a pesar de', 'aunque', 'aun cuando',
                'por lo tanto', 'por consiguiente', 'en consecuencia', 'así que', 'de manera que',
                'por eso', 'por lo que', 'de modo que', 'con el fin de', 'para que', 'a fin de que',
                'con el propósito de', 'pues', 'porque', 'ya que', 'dado que', 'puesto que',
                'a causa de', 'debido a', 'gracias a', 'por culpa de', 'a través de', 'por medio de',
                'por intermedio de', 'en cuanto a', 'con respecto a', 'en relación con', 'acerca de',
                'sobre', 'acerca de', 'según', 'conforme a', 'de acuerdo con', 'en cuanto', 'tan pronto como',
                'en cuanto que', 'siempre que', 'a menos que', 'a no ser que', 'con tal que', 'para que',
                'a fin de que', 'de modo que', 'de manera que', 'así que', 'por lo que', 'por lo tanto',
                'por consiguiente', 'en consecuencia', 'por eso', 'por esta razón', 'de ahí que',
                'por ende', 'de modo que', 'de manera que', 'así que', 'por lo que', 'por lo tanto',
                'por consiguiente', 'en consecuencia', 'por eso', 'por esta razón', 'de ahí que',
                'por ende', 'además', 'también', 'así mismo', 'igualmente', 'de igual manera',
                'de igual forma', 'del mismo modo', 'de la misma manera', 'de igual modo', 'de la misma forma',
                'de la misma manera', 'de igual forma', 'de igual modo', 'de la misma manera',
                'de la misma forma', 'de igual modo', 'de la misma manera', 'de la misma forma',
                'de igual modo', 'de la misma manera', 'de la misma forma', 'de igual modo',
                'de la misma manera', 'de la misma forma', 'de igual modo', 'de la misma manera',
                'de la misma forma', 'de igual modo', 'de la misma manera', 'de la misma forma',
                'de igual modo', 'de la misma manera', 'de la misma forma', 'de igual modo',
                'de la misma manera', 'de la misma forma', 'de igual modo', 'de la misma manera',
                'de la misma forma', 'de igual modo', 'de la misma manera', 'de la misma forma',
                'de igual modo', 'de la misma manera', 'de la misma forma', 'de igual modo'
            }
            
            # Extraer palabras significativas de la consulta
            words = re.findall(r'\b\w+\b', query.lower())
            search_terms = [word for word in words if len(word) > 2 and word not in stop_words]
            
            # Si no hay términos de búsqueda, usar la consulta completa (sin stop words)
            if not search_terms:
                search_terms = [word for word in words if word not in stop_words]
            
            logger.info(f"[SEARCH_INDICADORES] Términos de búsqueda finales: {search_terms}")
                       
            # Construir query con múltiples campos y ponderación
            q_objects = Q(activo=True)
            
            # Si hay términos de búsqueda, aplicarlos
            if search_terms:
                search_q = Q()
                for term in search_terms:
                    # Búsqueda en campos principales con mayor peso
                    # Solo buscar en campos existentes del modelo
                    term_q = (
                        Q(nombre__icontains=term) | 
                        Q(descripcion__icontains=term) |
                        Q(notas__icontains=term) |
                        Q(formula__icontains=term) |
                        Q(fuente_datos__icontains=term) |
                        Q(entidad_recopiladora__icontains=term) |
                        Q(unidad_medida__icontains=term) |
                        # Búsqueda en relaciones jerárquicas
                        # (subtema principal + subtemas adicionales M2M)
                        Q(subtema__nombre__icontains=term) |
                        Q(subtemas_adicionales__nombre__icontains=term) |
                        Q(subtema__tema__nombre__icontains=term) |
                        Q(subtemas_adicionales__tema__nombre__icontains=term) |
                        Q(subtema__tema__dominio__nombre__icontains=term) |
                        Q(subtemas_adicionales__tema__dominio__nombre__icontains=term) |
                        Q(operacion__nombre__icontains=term) |
                        Q(operacion__descripcion__icontains=term)
                    )
                    search_q |= term_q  # Usar OR entre términos
                
                q_objects &= search_q
                logger.info(f"[SEARCH_INDICADORES] Filtros de búsqueda aplicados: {q_objects}")
            else:
                logger.info("[SEARCH_INDICADORES] Sin términos de búsqueda, devolviendo todos los indicadores activos")
            
            # Consulta base con select_related para optimización
            indicadores_query = Indicador.objects.filter(q_objects).select_related(
                'subtema__tema__dominio'
            ).distinct()
            
            # Log de la consulta SQL generada
            logger.debug(f"[SEARCH_INDICADORES] SQL generada: {str(indicadores_query.query)}")
            
            # Contar total antes de aplicar filtros adicionales
            total_inicial = indicadores_query.count()
            logger.info(f"[SEARCH_INDICADORES] Total de indicadores iniciales: {total_inicial}")
            
            # Aplicar filtros adicionales
            if analysis.get('is_geographic'):
                # Usar el campo existente para filtrar por desagregación geográfica
                indicadores_query = indicadores_query.filter(
                    dominios_desagregacion_geografica__isnull=False
                ).distinct()
                logger.info("[SEARCH_INDICADORES] Aplicado filtro geográfico (dominios_desagregacion_geografica)")
            
            # Calcular relevancia basada en los términos de búsqueda
            if search_terms:
                # Anotar con puntuación de relevancia
                
                # Crear expresiones de coincidencia para cada término
                relevance_expressions = []
                for term in search_terms:
                    # Peso más alto para coincidencias exactas en nombre
                    name_match = Case(
                        When(nombre__iexact=term, then=Value(10.0)),
                        When(nombre__istartswith=term, then=Value(7.0)),
                        When(nombre__icontains=term, then=Value(5.0)),
                        default=Value(0.0),
                        output_field=FloatField()
                    )
                    
                    # Peso medio para descripción
                    desc_match = Case(
                        When(descripcion__icontains=term, then=Value(3.0)),
                        default=Value(0.0),
                        output_field=FloatField()
                    )
                    
                    # Peso para relaciones jerárquicas
                    # (principal pesa más que los subtemas adicionales)
                    subtema_match = Case(
                        When(subtema__nombre__icontains=term, then=Value(4.0)),
                        When(subtemas_adicionales__nombre__icontains=term, then=Value(3.0)),
                        default=Value(0.0),
                        output_field=FloatField()
                    )
                    
                    tema_match = Case(
                        When(subtema__tema__nombre__icontains=term, then=Value(3.0)),
                        When(subtemas_adicionales__tema__nombre__icontains=term, then=Value(2.0)),
                        default=Value(0.0),
                        output_field=FloatField()
                    )
                    
                    dominio_match = Case(
                        When(subtema__tema__dominio__nombre__icontains=term, then=Value(2.0)),
                        When(subtemas_adicionales__tema__dominio__nombre__icontains=term, then=Value(1.5)),
                        default=Value(0.0),
                        output_field=FloatField()
                    )
                    
                    # Sumar todas las coincidencias para este término
                    term_relevance = (
                        name_match + 
                        desc_match + 
                        subtema_match + 
                        tema_match + 
                        dominio_match
                    )
                    
                    relevance_expressions.append(term_relevance)
                
                # Sumar la relevancia de todos los términos
                total_relevance = sum(relevance_expressions[1:], relevance_expressions[0]) if relevance_expressions else Value(0.0)
                
                # Anotar con la relevancia calculada
                indicadores_query = indicadores_query.annotate(
                    relevance=total_relevance
                )
                
                # Ordenar por relevancia descendente y luego por fecha de actualización
                order_by = ['-relevance', '-fecha_actualizacion']
            else:
                # Ordenar solo por fecha de actualización si no hay términos de búsqueda
                order_by = ['-fecha_actualizacion']
            
            # Anotar con información de jerarquía para ordenamiento
            try:
                indicadores = indicadores_query.annotate(
                    ruta_completa=Concat(
                        'subtema__tema__dominio__nombre',
                        Value(' > '),
                        'subtema__tema__nombre',
                        Value(' > '),
                        'subtema__nombre',
                        output_field=models.CharField()
                    )
                ).values(
                    'id', 'nombre', 'descripcion', 'unidad_medida',
                    'subtema__nombre', 'subtema__tema__nombre', 
                    'subtema__tema__dominio__nombre', 'ruta_completa',
                    'fecha_actualizacion', 'dominios_desagregacion_geografica'
                ).distinct()
                
                # Aplicar ordenamiento
                if 'relevance' in [f.name for f in Indicador._meta.get_fields()]:
                    indicadores = indicadores.order_by(*order_by)
                
                # Log de resultados
                logger.info(f"[SEARCH_INDICADORES] Consulta final: {str(indicadores.query) if hasattr(indicadores, 'query') else 'QuerySet evaluado'}")
                logger.info(f"[SEARCH_INDICADORES] Total de resultados encontrados: {indicadores.count()}")
                
                # Aplicar paginación
                total = indicadores.count()
                resultados = list(indicadores[offset:offset + limit])
                
                logger.info(f"[SEARCH_INDICADORES] Resultados paginados: {len(resultados)} de {total}")
                
                return {
                    'resultados': resultados,
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                    'search_terms': search_terms
                }
                
            except Exception as e:
                logger.error(f"[SEARCH_INDICADORES] Error en la consulta: {str(e)}", exc_info=True)
                return {
                    'resultados': [],
                    'total': 0,
                    'error': str(e),
                    'query': query,
                    'search_terms': search_terms
                }
                
        except Exception as e:
            logger.error(f"[SEARCH_INDICADORES] Error inesperado: {str(e)}", exc_info=True)
            return {
                'resultados': [],
                'total': 0,
                'error': str(e),
                'query': query
            }

    def _search_operaciones(self, query: str, analysis: dict, limit: int = 10, offset: int = 0) -> dict:
        """Búsqueda avanzada de operaciones estadísticas con mejoras de rendimiento"""
        try:
            search_terms = [term for term in analysis.get('query_terms', []) if len(term) > 2]
            
            # Si no hay términos de búsqueda pero se piden "todas" o similar
            if not search_terms and not any(word in query.lower() for word in ['todas', 'listar', 'mostrar', 'ver']):
                return []
            
     
  
            
            # Construir query con múltiples campos
            q_objects = Q(activo=True)
            
            if search_terms:
                search_q = Q()
                for term in search_terms:
                    # Búsqueda en campos principales
                    term_q = (
                        Q(nombre__icontains=term) |
                        Q(descripcion__icontains=term) |
                        Q(entidad_recopiladora__icontains=term) |
                        Q(objetivo__icontains=term) |
                        Q(cobertura_geografica__icontains=term)
                    )
                    search_q &= term_q
                
                q_objects &= search_q
            
            # Aplicar filtros adicionales del análisis
            if analysis.get('is_geographic'):
                q_objects &= Q(cobertura_geografica__isnull=False)
                
            if analysis.get('is_temporal'):
                q_objects &= Q(periodicidad__isnull=False)
            
            # Consulta base
            operaciones_query = OperacionEstadistica.objects.filter(q_objects)
            
            # Ordenamiento por relevancia o fecha
            order_by = ['-fecha_inicio']
            if not search_terms:
                # Si no hay términos, ordenar por frecuencia de consulta o fecha de actualización
                order_by = ['-fecha_actualizacion', '-fecha_inicio']
            
            # Anotar con información adicional
            operaciones = operaciones_query.annotate(
                nombre_entidad=Case(
                    When(entidad_recopiladora='', then=Value('Sin entidad especificada')),
                    default=F('entidad_recopiladora'),
                    output_field=models.CharField()
                )
            ).values(
                'id', 'nombre', 'descripcion', 'periodicidad',
                'entidad_recopiladora', 'fecha_inicio', 'fecha_fin',
                'objetivo', 'cobertura_geografica', 'metodologia',
                'fecha_actualizacion'
            ).order_by(*order_by)
            
            # Aplicar paginación
            total = operaciones.count()
            resultados = list(operaciones[offset:offset + limit])
            
            return {
                'resultados': resultados,
                'total': total,
                'limit': limit,
                'offset': offset
            }
                
        except Exception as e:
            logger.error(f"Error buscando operaciones: {e}", exc_info=True)
            return {
                'resultados': [],
                'total': 0,
                'error': str(e)
            }

    def _search_eventos_noticias(self, query: str, analysis: dict, limit: int = 5, offset: int = 0) -> dict:
        """Búsqueda mejorada de eventos y noticias con paginación y relevancia"""
        result = {'eventos': [], 'noticias': [], 'total': 0}
        
        try:
            search_terms = [term for term in analysis.get('query_terms', []) if len(term) > 2]
   

            
            # Si no hay términos de búsqueda pero se piden "todos" o similar
            show_all = not search_terms and any(word in query.lower() for word in ['todos', 'listar', 'mostrar', 'ver'])
            
            # Búsqueda de eventos
            try:
                eventos_query = Evento.objects.filter(
                    activo=True
                ).annotate(
                    es_futuro=Case(
                        When(fecha_inicio__gte=Now(), then=Value(1)),
                        default=Value(0),
                        output_field=models.IntegerField()
                    )
                )
                
                if not show_all:
                    # Si no es "mostrar todos", solo eventos futuros
                    eventos_query = eventos_query.filter(fecha_inicio__gte=Now())
                    
                    if search_terms:
                        search_q = Q()
                        for term in search_terms:
                            search_q &= (
                                Q(nombre__icontains=term) | 
                                Q(descripcion__icontains=term) |
                                Q(lugar__icontains=term)
                            )
                        eventos_query = eventos_query.filter(search_q)
                
                # Ordenar: futuros primero, luego por fecha más cercana
                eventos = eventos_query.order_by(
                    '-es_futuro', 'fecha_inicio'
                ).values(
                    'id', 'nombre', 'descripcion', 'fecha_inicio', 'fecha_fin',
                    'lugar', 'imagen', 'url_mas_info'
                )[offset:offset + limit]
                
                result['eventos'] = list(eventos)
                result['total_eventos'] = eventos.count()
                
            except Exception as e:
                logger.warning(f"Error buscando eventos: {e}", exc_info=True)
            
            # Búsqueda de noticias
            try:
                noticias_query = NoticiaBanner.objects.filter(
                    activa=True
                )
                
                if not show_all and search_terms:
                    search_q = Q()
                    for term in search_terms:
                        search_q &= (
                            Q(titulo__icontains=term) | 
                            Q(contenido__icontains=term) |
                            Q(resumen__icontains=term)
                        )
                    noticias_query = noticias_query.filter(search_q)
                
                noticias = noticias_query.order_by(
                    '-fecha_publicacion'
                ).values(
                    'id', 'titulo', 'contenido', 'resumen', 'fecha_publicacion',
                    'imagen', 'url_noticia', 'fuente'
                )[offset:offset + limit]
                
                result['noticias'] = list(noticias)
                result['total_noticias'] = noticias.count()
                
            except Exception as e:
                logger.warning(f"Error buscando noticias: {e}", exc_info=True)
            
            # Calcular total general
            result['total'] = result.get('total_eventos', 0) + result.get('total_noticias', 0)
            result['limit'] = limit
            result['offset'] = offset
                
        except Exception as e:
            logger.error(f"Error en _search_eventos_noticias: {e}", exc_info=True)
            result['error'] = str(e)
        
        return result

    def _search_documentos(self, query: str, analysis: dict, limit: int = 10, offset: int = 0) -> dict:
        """Búsqueda avanzada de documentos con mejoras de rendimiento y relevancia"""
        try:
            search_terms = [term for term in analysis.get('query_terms', []) if len(term) > 2]
            
            # Si no hay términos de búsqueda pero se piden "todos" o similar
            if not search_terms and not any(word in query.lower() for word in ['todos', 'listar', 'mostrar', 'ver']):
                return {
                    'resultados': [],
                    'total': 0,
                    'sugerencias': [
                        "Intenta con términos más específicos",
                        "Usa palabras clave relacionadas con el documento que buscas",
                        "Prueba con el tipo de documento o tema"
                    ]
                }
                       
            # Construir query con múltiples campos
            q_objects = Q(activo=True)
            
            if search_terms:
                search_q = Q()
                for term in search_terms:
                    # Búsqueda en campos principales con ponderación
                    term_q = (
                        Q(nombre__icontains=term) |
                        Q(descripcion__icontains=term) |
                        Q(tipo_documento__icontains=term) |
                        Q(grupo_documento__nombre__icontains=term) |
                        Q(palabras_clave__icontains=term)
                    )
                    search_q &= term_q
                
                q_objects &= search_q
            
            # Aplicar filtros adicionales del análisis
            if analysis.get('is_temporal'):
                q_objects &= Q(fecha_publicacion__isnull=False)
                
            # Consulta base con select_related para optimización
            documentos_query = DocumentoInfraestructura.objects.filter(q_objects).select_related(
                'grupo_documento'
            )
            
            # Ordenamiento por relevancia o fecha
            order_by = ['-fecha_publicacion']
            if search_terms:
                # Si hay términos de búsqueda, priorizar por coincidencias en el nombre
                documentos_query = documentos_query.annotate(
                    relevancia=Case(
                        When(nombre__icontains=search_terms[0], then=Value(1)),
                        default=Value(0),
                        output_field=models.IntegerField()
                    )
                )
                order_by = ['-relevancia', '-fecha_publicacion']
            
            # Anotar con información adicional
            documentos = documentos_query.annotate(
                tipo_documento_nombre=Case(
                    When(tipo_documento='', then=Value('Sin tipo especificado')),
                    default=F('tipo_documento'),
                    output_field=models.CharField()
                )
            ).values(
                'id', 'nombre', 'descripcion', 'tipo_documento', 'tipo_documento_nombre',
                'grupo_documento__nombre', 'fecha_publicacion', 'archivo', 'tamaño_archivo',
                'formato', 'idioma', 'version', 'palabras_clave'
            ).order_by(*order_by)
            
            # Aplicar paginación
            total = documentos.count()
            resultados = list(documentos[offset:offset + limit])
            
            return {
                'resultados': resultados,
                'total': total,
                'limit': limit,
                'offset': offset,
                'sugerencias': self._generar_sugerencias_busqueda(search_terms) if not resultados else []
            }
                
        except Exception as e:
            logger.error(f"Error buscando documentos: {e}", exc_info=True)
            return {
                'resultados': [],
                'total': 0,
                'error': str(e),
                'sugerencias': ["Ocurrió un error al buscar documentos. Por favor, inténtalo de nuevo."]
            }

    def _generar_sugerencias_busqueda(self, search_terms):
        """Genera sugerencias de búsqueda basadas en términos no encontrados"""
        sugerencias = []
        
        if not search_terms:
            sugerencias.append("Prueba con términos más específicos")
            sugerencias.append("Usa palabras clave relacionadas con el documento que buscas")
        else:
            sugerencias.append(f"Revisa la ortografía de: {', '.join(search_terms)}")
            sugerencias.append("Intenta con sinónimos o términos más generales")
        
        return sugerencias

    def _search_microdatos(self, query: str, analysis: dict, limit: int = 10, offset: int = 0) -> dict:
        """Búsqueda avanzada de conjuntos_datos con mejoras de rendimiento y relevancia"""
        try:
            # Filtrar términos de búsqueda cortos
            search_terms = [term for term in analysis.get('query_terms', []) if len(term) > 2]
            
            # Si no hay términos de búsqueda pero se piden "todos" o similar
            if not search_terms and not any(word in query.lower() for word in ['todos', 'listar', 'mostrar', 'ver']):
                return {
                    'resultados': [],
                    'total': 0,
                    'sugerencias': [
                        "Especifica términos de búsqueda más concretos",
                        "Prueba con el nombre de la operación o tema",
                        "Usa palabras clave relacionadas con los conjuntos_datos que buscas"
                    ]
                }

            
            # Construir query con múltiples campos
            q_objects = Q()
            
            if search_terms:
                search_q = Q()
                for term in search_terms:
                    # Búsqueda en campos principales con ponderación
                    term_q = (
                        Q(nombre__icontains=term) |
                        Q(descripcion__icontains=term) |
                        Q(operacion__nombre__icontains=term) |
                        Q(operacion__codigo__icontains=term) |
                        Q(palabras_clave__icontains=term)
                    )
                    search_q &= term_q
                
                q_objects &= search_q
            
            # Aplicar filtros adicionales del análisis
            if analysis.get('is_temporal'):
                q_objects &= Q(fecha_carga__isnull=False)
                
            # Consulta base con select_related para optimización
            microdatos_query = ConjuntoDatos.objects.filter(q_objects).select_related(
                'operacion'
            )
            
            # Ordenamiento por relevancia o fecha
            order_by = ['-fecha_carga']
            if search_terms:
                # Priorizar coincidencias en el nombre y descripción
                microdatos_query = microdatos_query.annotate(
                    relevancia=Case(
                        When(nombre__icontains=search_terms[0], then=Value(2)),
                        When(descripcion__icontains=search_terms[0], then=Value(1)),
                        default=Value(0),
                        output_field=models.IntegerField()
                    )
                )
                order_by = ['-relevancia', '-fecha_carga']
            
            # Anotar con información adicional
            conjuntos_datos = microdatos_query.annotate(
                operacion_nombre=Coalesce('operacion__nombre', Value('Sin operación asociada')),
                operacion_codigo=Coalesce('operacion__codigo', Value(''))
            ).values(
                'id', 'nombre', 'descripcion', 'fecha_carga',
                'operacion_nombre', 'operacion_codigo',
                'formato', 'tamaño_archivo', 'estado_procesamiento',
                'fecha_actualizacion', 'version', 'licencia'
            ).order_by(*order_by)
            
            # Aplicar paginación
            total = conjuntos_datos.count()
            resultados = list(conjuntos_datos[offset:offset + limit])
            
            # Formatear tamaño de archivo para mejor legibilidad
            for resultado in resultados:
                if 'tamaño_archivo' in resultado and resultado['tamaño_archivo']:
                    resultado['tamaño_formateado'] = self._formatear_tamano_archivo(resultado['tamaño_archivo'])
            
            return {
                'resultados': resultados,
                'total': total,
                'limit': limit,
                'offset': offset,
                'sugerencias': self._generar_sugerencias_microdatos(search_terms) if not resultados else []
            }
                
        except Exception as e:
            logger.error(f"Error buscando conjuntos_datos: {e}", exc_info=True)
            return {
                'resultados': [],
                'total': 0,
                'error': str(e),
                'sugerencias': ["Ocurrió un error al buscar conjuntos_datos. Por favor, inténtalo de nuevo."]
            }

    def _generar_sugerencias_microdatos(self, search_terms):
        """Genera sugerencias de búsqueda específicas para conjuntos_datos"""
        
        sugerencias = []
        
        if not search_terms:
            # Sugerencias para búsquedas vacías
            sugerencias.append("Prueba con términos más específicos")
            sugerencias.append("Busca por nombre de operación o tema")
            
            # Obtener operaciones estadísticas populares
            try:
                operaciones_populares = OperacionEstadistica.objects.filter(
                    activo=True
                ).annotate(
                    num_microdatos=Count('conjunto_datos')
                ).order_by('-num_microdatos')[:3]
                
                if operaciones_populares:
                    sugerencias.append("Operaciones populares: " + 
                        ", ".join([op.nombre for op in operaciones_populares]))
            except Exception as e:
                logger.warning(f"Error obteniendo operaciones populares: {e}")
        else:
            # Sugerencias para búsquedas sin resultados
            sugerencias.append(f"Revisa la ortografía de: {', '.join(search_terms)}")
            sugerencias.append("Intenta con términos más generales o específicos")
            
            # Sugerir formatos disponibles
            try:
                formatos = ConjuntoDatos.objects.values_list('formato', flat=True).distinct()
                if formatos:
                    sugerencias.append(f"Formatos disponibles: {', '.join(sorted(set(f for f in formatos if f)))}")
            except Exception as e:
                logger.warning(f"Error obteniendo formatos: {e}")
        
        return sugerencias

    def _formatear_tamano_archivo(self, tamano_bytes):
        """Formatea el tamaño del archivo en unidades legibles"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if tamano_bytes < 1024.0:
                return f"{tamano_bytes:.1f} {unit}"
            tamano_bytes /= 1024.0
        return f"{tamano_bytes:.1f} PB"

    def _search_contextual_info(self, query: str) -> dict:
        """Búsqueda de información contextual cuando no hay coincidencias específicas"""
        try:
            result = {}
            
            # Si pregunta por información general del SIIED
            if any(term in query for term in ['siied', 'sistema', 'información', 'estadística']):
                # Obtener estadísticas generales
                result['estadisticas_generales'] = {
                    'total_dominios': MenuDominio.objects.filter(activo=True).count(),
                    'total_temas': MenuTema.objects.filter(activo=True).count(),
                    'total_subtemas': MenuSubtema.objects.filter(activo=True).count(),
                    'total_indicadores': Indicador.objects.filter(activo=True).count(),
                    'total_operaciones': OperacionEstadistica.objects.filter(activo=True).count()
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error en búsqueda contextual: {e}")
            return {}

    def get_system_context(self):
        """Contexto del sistema con caché optimizado"""
        cache_key = get_config('CONTEXT_CACHE_KEY', 'chat_system_context_v6')
        context = cache.get(cache_key)
        
        if not context:
            try:
                # Estadísticas básicas
                stats = self._get_basic_stats()
                
                # Contexto base mejorado usando configuración centralizada
                context = get_context(
                    'don_datico_base',
                    dominios=stats.get('dominios', 0),
                    temas=stats.get('temas', 0),
                    subtemas=stats.get('subtemas', 0),
                    indicadores=stats.get('indicadores', 0),
                    taxonomia=self._get_taxonomia_texto()
                )
                
                # Guardar en caché
                cache_timeout = get_config('CONTEXT_CACHE_TIMEOUT', 60 * 60 * 6)
                cache.set(cache_key, context, cache_timeout)
                
            except Exception as e:
                logger.error(f"Error generando contexto: {e}")
                context = self._get_fallback_context()
        
        return context

    def _get_basic_stats(self):
        """Obtiene estadísticas básicas del sistema"""
        try:
            return {
                'dominios': MenuDominio.objects.filter(activo=True).count(),
                'temas': MenuTema.objects.filter(activo=True).count(),
                'subtemas': MenuSubtema.objects.filter(activo=True).count(),
                'indicadores': Indicador.objects.filter(activo=True).count()
            }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas básicas: {e}")
            return {'dominios': 0, 'temas': 0, 'subtemas': 0, 'indicadores': 0}

    def _get_taxonomia_texto(self):
        """Construye un texto compacto dominio → temas para el system prompt.

        Con solo los conteos, el modelo no puede responder 'qué dominios y
        temas hay' sin herramientas (y caía en loops de buscar_indicadores).
        """
        try:
            dominios = MenuDominio.objects.filter(activo=True).order_by('orden')
            lineas = []
            for d in dominios:
                temas = list(
                    MenuTema.objects.filter(dominio=d, activo=True)
                    .order_by('orden')
                    .values_list('nombre', flat=True)
                )
                if temas:
                    lineas.append(f"- {d.nombre}: {', '.join(temas)}")
                else:
                    lineas.append(f"- {d.nombre}")
            if not lineas:
                return ''
            return "DOMINIOS Y TEMAS DISPONIBLES EN EL SIIED:\n" + "\n".join(lineas)
        except Exception as e:
            logger.error(f"Error construyendo taxonomía: {e}")
            return ''

    def _get_fallback_context(self):
        """Contexto de respaldo mínimo"""
        return get_context('fallback')

    # Mantener métodos de compatibilidad
    def count_tokens(self, text):
        """Estimación de tokens para compatibilidad"""
        if not text:
            return 0
        return max(1, len(str(text)) // 4)

    def count_message_tokens(self, message):
        """Cuenta tokens de mensaje para compatibilidad"""
        if not message or not isinstance(message, dict):
            return 0
        content = message.get('content', '')
        role = message.get('role', '')
        return self.count_tokens(content) + self.count_tokens(role)

    def trim_messages_to_token_limit(self, messages, max_tokens):
        """Recorta mensajes para límite de tokens"""
        if not messages:
            return []
        
        # Implementación simplificada
        total_tokens = sum(self.count_message_tokens(msg) for msg in messages)
        
        if total_tokens <= max_tokens:
            return messages
        
        # Mantener mensaje del sistema y recortar el resto
        system_msgs = [msg for msg in messages if msg.get('role') == 'system']
        other_msgs = [msg for msg in messages if msg.get('role') != 'system']
        
        # Reducir mensajes hasta cumplir el límite
        while other_msgs and total_tokens > max_tokens:
            removed = other_msgs.pop(0)
            total_tokens -= self.count_message_tokens(removed)
        
        return system_msgs + other_msgs
        return system_msgs + other_msgs
