# 4. FEATURES Y CAPACIDADES

## 1. Sistema de Visualización de Indicadores

### Navegación Jerárquica
- **Dominio → Tema → Subtema → Indicador**
- Slugs únicos para URLs amigables
- Sistema de breadcrumbs automático
- Ordenamiento configurable

### Tipos de Gráficos (9 tipos)
1. **Línea** (`line`) - Series temporales
2. **Barras** (`bar`) - Comparaciones categóricas
3. **Barras Horizontales** (`bar_horizontal`)
4. **Área** (`area`) - Tendencias acumuladas
5. **Barras Apiladas** (`barras_apiladas`)
6. **Áreas Apiladas** (`areas_apiladas`)
7. **Circular** (`pie`) - Proporciones
8. **Pirámide Poblacional** (`piramide_poblacional`)
9. **Treemap** - Jerarquías

### Configuración Avanzada de Gráficos
```python
# Modelo Grafico tiene 25+ campos configurables:
- Títulos y subtítulos personalizables
- Ejes X/Y con títulos propios
- Soporte para eje Y secundario
- Leyenda configurable (posición, visibilidad)
- Cuadrícula on/off
- Valores sobre barras
- Línea de tendencia
- Rango personalizado min/max
- Control de altura (200-1000px)
- Márgenes personalizables
- Rangos de años predeterminados
- Desagregaciones predeterminadas
```

### Filtros Dinámicos
- Filtro por rango de años (slider)
- Selección múltiple de desagregaciones geográficas
- Selección múltiple de desagregaciones temáticas
- Actualización automática vía AJAX
- Estado persistente en URL params

## 2. Sistema de Mapas Geoespaciales

### Capacidades
- **Mapas coropletas** con Leaflet
- **Reproyección automática** de coordenadas
  - CRS origen: `MAGNA_Cali_Valle_del_Cauca_2009`
  - CRS destino: `EPSG:4326` (WGS84)
- **Geometrías WKT** almacenadas en ElementoGeo
- **GeoJSON dinámico** generado on-the-fly
- **Escalas de color** de Plotly configurables

### Flujo de Datos Geoespaciales
```python
def geojson_indicador(request, indicador_id):
    # 1. Obtener dominios geográficos del indicador
    # 2. Para cada CapaGeo: obtener ElementoGeo
    # 3. Transformar geom_wkt a WGS84 si es necesario
    # 4. Buscar datos asociados a cada elemento
    # 5. Generar FeatureCollection GeoJSON
    # 6. Cachear resultado
```

### Configuración CRS
```python
# settings.py
GEO_SOURCE_CRS_DEFAULT = 'PROJCS["MAGNA_Cali_Valle_del_Cauca_2009",...]'
GEO_SOURCE_CRS_BY_CAPA_ID = {}  # Override por capa
GEO_SOURCE_CRS_BY_CAPA_NAME = {}  # Override por nombre
```

## 3. Procesamiento de Microdata

### Algoritmo Cartesiano

**Comando:** `procesar_microdata_cartesiano.py`

**Capacidades:**
```python
# Genera producto cartesiano automático de desagregaciones
# Ejemplo: Sexo (M/F) × Edad (0-4, 5-9, ...) × Comuna (1-22)
#         = 2 × 18 × 22 = 792 combinaciones

# Features:
- Detección automática de encoding (utf-8, latin-1, iso-8859-1, cp1252)
- Detección automática de delimitador (CSV Sniffer)
- Aplicación de filtros configurables
- Normalización de nombres (quitar tildes, espacios)
- Mapeo inteligente de columnas a desagregaciones
- Generación masiva de registros Dato
- Logging detallado con verbosity configurable
- Límite de filas para testing
- Eliminación de datos previos opcional
```

**Fórmulas Soportadas:**
```python
# Suma simple
"SUM(columna)"

# Fórmulas con múltiples columnas
"Hombres_0 + Hombres_1 + Mujeres_0 + Mujeres_1"

# Tasas
"(defunciones / poblacion) * 1000"

# Porcentajes
"(valor / SUM(total)) * 100"

# Expresiones Python evaluadas
"valor_celda * 100"
```

### Detección de Esquemas

**Módulo:** `schema_detection.py`

**Capacidades:**
```python
class SchemaDetector:
    """
    Analiza automáticamente archivos CSV/Excel:
    - Detecta tipos de columnas (fecha, numérico, categórico, geográfico)
    - Identifica desagregaciones
    - Sugiere reglas de extracción
    - Valida compatibilidad con algoritmo cartesiano
    """
    
    # Patrones de detección:
    date_patterns = ['fecha', 'año', 'year', 'date', 'periodo']
    geographic_patterns = ['comuna', 'barrio', 'localidad', 'municipio']
    demographic_patterns = ['sexo', 'género', 'edad', 'estrato']
    value_patterns = ['total', 'cantidad', 'número', 'valor', 'población']
```

**Análisis Contextual:**
```python
# Detecta tipo de indicador por contexto
indicator_patterns = {
    'poblacion': {
        'keywords': ['población', 'habitantes'],
        'formula_type': 'sum',
        'expected_disaggregations': ['sexo', 'edad', 'comuna']
    },
    'tasa_mortalidad': {
        'keywords': ['tasa', 'mortalidad'],
        'formula_type': 'rate',
        'validation_rules': ['rate_bounds', 'no_negative']
    }
}
```

**Output:**
```python
{
    'file_info': { 'total_columns': 50, 'sample_rows': 1000 },
    'column_analysis': { 'Año': {'likely_type': 'date', 'confidence': 0.95} },
    'suggested_mappings': {
        'date_columns': ['Año'],
        'value_columns': ['Total', 'Hombres', 'Mujeres'],
        'geographic_disaggregations': ['Comuna'],
        'thematic_disaggregations': ['Sexo', 'Edad']
    },
    'extraction_suggestions': {
        'recommended_date_column': 'Año',
        'cartesian_formula': "df.groupby(disaggregations)['Total'].sum()",
        'confidence_score': 0.9
    },
    'cartesian_compatibility': {
        'is_compatible': True,
        'issues': [],
        'recommendations': []
    }
}
```

## 4. Chat con Inteligencia Artificial

### Arquitectura del Chat

**Modelo:** Cerebras GPT-OSS-120B
```python
class ChatService:
    model_config = {
        "model": "gpt-oss-120b",
        "max_tokens": 14200,
        "temperature": 0.15,
        "top_p": 0.92
    }
```

### Clasificación Zero-Shot
```python
# Modelo: MoritzLaurer/mDeBERTa-v3-base-mnli-xnli
labels = ["casual", "consulta"]

# Decide si usar tools o responder directamente
def _should_use_tools(user_message):
    result = classifier(user_message, candidate_labels=labels)
    return result["labels"][0] == 'consulta'
```

### Sistema de Tools (MCP)
```python
# Tools disponibles vía Cerebras:
- buscar_indicadores(criterios)
- obtener_datos_indicador(id, filtros)
- listar_dominios()
- listar_temas(dominio)
- consultar_operaciones_estadisticas()
```

### Streaming con SSE
```python
def chat_message(request):
    """
    Server-Sent Events para streaming de respuesta
    """
    def event_stream():
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        for chunk in response_generator:
            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
        
        yield f"data: {json.dumps({'type': 'complete'})}\n\n"
    
    return StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
```

### Gestión de Historial
```python
# Limpieza automática
def _clean_conversation_history(history):
    - Elimina duplicados
    - Trunca mensajes largos (>1000 chars)
    - Mantiene últimos 10 mensajes (5 intercambios)
    - Valida estructura de mensajes
```

### Rate Limiting
```python
# ChatRateLimitMiddleware
- 5 mensajes por minuto por IP
- Cache de 60 segundos
- Response 429 si excede límite
```

## 5. Búsqueda Semántica

### Stack Tecnológico
- **pgvector** - Almacenamiento de embeddings
- **sentence-transformers** - Generación de embeddings
- **Modelo:** all-MiniLM-L6-v2 (384 dimensiones)

### Flujo de Búsqueda
```python
1. Usuario ingresa query
2. EmbeddingService.get_embedding(query) → vector[384]
3. Búsqueda por similitud coseno en PostgreSQL:
   SELECT *, 1 - (embedding <=> query_embedding) as similarity
   FROM DocumentoVector
   ORDER BY similarity DESC
   LIMIT 5
4. Filtrar por threshold (default: 0.6)
5. Enriquecer resultados con datos del modelo referenciado
6. Retornar JSON ordenado por similitud
```

### Indexación
```python
# Tipos de documentos indexados:
- 'indicador' → Indicador
- 'tema' → MenuTema
- 'subtema' → MenuSubtema
- 'dominio' → MenuDominio

# Comando para regenerar índice:
python manage.py generar_embeddings
```

### Enriquecimiento de Resultados
```python
def _enrich_result_data(doc):
    """
    Agrega información contextual:
    - Para indicadores: nombre, descripción, unidad, fuente, jerarquía
    - Para temas: nombre, descripción, dominio padre
    - Para dominios: nombre, descripción
    """
```

## 6. Visor Comparativo

### Funcionalidad
- Comparar múltiples indicadores simultáneamente
- Filtros sincronizados (años, desagregaciones)
- Visualización en múltiples gráficos
- Exportación de datos
- URLs compartibles con estado

### Implementación
```python
# Template: visor_comparativo_standalone.html
# JavaScript dinámico:
- Carga de dominios/temas/indicadores vía AJAX
- Generación dinámica de gráficos Plotly
- Sincronización de filtros
- Manejo de estado en localStorage
```

## 7. Sistema de Infraestructura

### 5 Niveles Jerárquicos
```
Área de Infraestructura (Nivel 1)
└── Categoría (Nivel 2)
    └── Subcategoría (Nivel 3)
        └── Grupo de Documentos (Nivel 4)
            └── Documento (Nivel 5) [CKEditor content]
```

### Editor CKEditor 5
```python
CKEDITOR_5_CONFIGS = {
    'infraestructura': {
        'toolbar': [
            'heading', 'bold', 'italic', 'underline', 'strikethrough',
            'subscript', 'superscript', 'link', 'bulletedList', 
            'numberedList', 'blockQuote', 'fontSize', 'fontFamily',
            'fontColor', 'fontBackgroundColor', 'alignment',
            'insertTable', 'imageUpload', 'mediaEmbed',
            'code', 'codeBlock', 'sourceEditing', 'removeFormat'
        ],
        'height': 600,
        'language': 'es'
    }
}
```

### Control de Versiones
```python
# DocumentoInfraestructura
- version: CharField(50)  # v1.0, v2.1, etc.
- estado: 'borrador', 'revision', 'aprobado', 'publicado', 'archivado'
- fecha_revision: DateField  # Próxima revisión
- autor: CharField(255)
```

## 8. Validación Automática de Datos

### Sistema de Validaciones
```python
class DataValidator:
    """
    10 validaciones automáticas:
    1. Valores nulos
    2. Valores negativos (en indicadores poblacionales)
    3. Consistencia de fechas
    4. Duplicados
    5. Valores atípicos (outliers >3σ)
    6. Consistencia temporal (cambios >500%)
    7. Completitud geográfica
    8. Restricciones poblacionales
    9. Rangos de porcentajes (0-100)
    10. Frescura de datos (<5 años)
    """
```

### Ejecución
```python
# Manual
from indicadores.data_validation import run_automatic_validations
results = run_automatic_validations(indicador_id=123)

# Automático (durante ingesta)
# Se ejecuta en procesar_microdata_cartesiano
```

### Output
```python
{
    'status': 'completed',
    'total_validations': 10,
    'errors': 2,
    'warnings': 3,
    'results': [
        {
            'type': 'null_values',
            'status': 'warning',
            'message': 'Se encontraron 15 valores nulos (2.3% del total)',
            'affected_records': 15
        }
    ]
}
```

## 9. Dashboard de Monitoring

### Métricas del Sistema
```python
# views_monitoring.py
def api_system_stats():
    """
    - Uso de CPU (psutil)
    - Uso de memoria
    - Uso de disco
    - Conexiones de BD activas
    - Uptime del sistema
    """

def api_cache_metrics():
    """
    - Hit rate del caché
    - Tamaño del caché
    - Entradas cacheadas
    - Backend de caché
    """

def api_data_quality():
    """
    - Total de indicadores
    - Total de datos
    - Datos con valores nulos
    - Datos recientes vs antiguos
    - Cobertura geográfica
    """

def api_performance_trends():
    """
    - Tiempos de respuesta promedio
    - Queries más lentas
    - Endpoints más usados
    """
```

### Visualización
- Dashboard con Plotly
- Auto-refresh cada 30 segundos
- Gráficos de tendencias
- Alertas configurables

## 10. Panel de Administración Django

### Personalizaciones

**Inline Editing:**
```python
class EstadisticaNoticiaInline(admin.TabularInline)
class EnlaceNoticiaInline(admin.TabularInline)
class GraficoSerieInline(admin.TabularInline)
```

**Custom Actions:**
```python
# ReglaExtraccionAdmin
- Botón "Procesar Datos"
- Vista de confirmación con diagnóstico
- Redirección a visor en vivo
```

**Widgets Personalizados:**
```python
ColorWidget  # Input type=color para campos de color
CKEditor5Widget  # Editor enriquecido
FilteredSelectMultiple  # Select múltiple mejorado
```

**Autocomplete:**
```python
autocomplete_fields = ['dominio', 'nivel_geografico', 'indicador']
```

## 11. Comandos de Gestión

### Comandos Disponibles
1. **procesar_microdata_cartesiano** - Procesa archivos CSV
2. **diagnosticar_microdata** - Análisis previo de archivos
3. **generar_embeddings** - Indexa documentos para búsqueda
4. **preload_cache** - Precarga caché para performance
5. **cargar_elementos_geo** - Importa geometrías desde shapefiles
6. **validate_data** - Ejecuta validaciones automáticas

## Conclusión de Features

### ✅ Fortalezas
- Sistema completo y funcional
- Alta configurabilidad
- IA integrada avanzada
- Procesamiento automático inteligente
- Validaciones robustas

### ⚠️ Áreas de Mejora
- Falta documentación de usuario
- Sin API REST documentada (OpenAPI/Swagger)
- Sin tests automatizados
- Algunas features podrían modularizarse
