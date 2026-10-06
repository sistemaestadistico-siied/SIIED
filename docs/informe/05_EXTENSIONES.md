# 5. EXTENSIONES Y HERRAMIENTAS

## Comandos de Gestión Django

### 1. procesar_microdata_cartesiano.py

**Ubicación:** `indicadores/management/commands/procesar_microdata_cartesiano.py`  
**Tamaño:** 857 líneas

**Propósito:**
Procesa archivos CSV de microdata aplicando el algoritmo cartesiano para generar todas las combinaciones posibles de desagregaciones.

**Argumentos:**
```bash
python manage.py procesar_microdata_cartesiano \
    --microdata-id 1 \
    --indicador-id 5 \
    --regla-id 3 \
    --eliminar-datos-previos \
    --limitar-filas 1000 \
    -v 3
```

**Funcionalidad Principal:**
```python
def procesar_fila(headers, row, indicador, regla):
    """
    1. Aplica filtros de la regla
    2. Extrae fecha del registro
    3. Identifica desagregaciones en los nombres de columnas
    4. Genera producto cartesiano de desagregaciones
    5. Evalúa fórmula para cada combinación
    6. Crea registro Dato con sus M2M
    """
```

**Características Avanzadas:**
- Detección automática de encoding y delimitador
- Normalización de texto (quita tildes, espacios)
- Mapeo inteligente de columnas a desagregaciones
- Soporte para desagregaciones de rango
- Progress reporting configurable por verbosity
- Manejo robusto de errores

**Ejemplo de Procesamiento:**
```python
# CSV con columnas:
# Año, Comuna, Sexo_M, Sexo_F, Edad_0_4, Edad_5_9

# Genera combinaciones:
# (Comuna=1, Sexo=M, Edad=0-4)
# (Comuna=1, Sexo=M, Edad=5-9)
# (Comuna=1, Sexo=F, Edad=0-4)
# (Comuna=1, Sexo=F, Edad=5-9)
# ... para cada comuna
```

### 2. diagnosticar_microdata.py

**Tamaño:** 33,300 bytes

**Propósito:**
Diagnóstico completo antes de procesar microdata. Identifica problemas potenciales.

**Funcionalidad:**
- Valida existencia de archivos
- Analiza estructura del CSV
- Verifica compatibilidad de regla de extracción
- Identifica columnas problemáticas
- Sugiere correcciones
- Estima cantidad de datos a generar

**Output Ejemplo:**
```
✓ Archivo CSV encontrado: microdata/poblacion_2023.csv
✓ Encoding detectado: UTF-8
✓ Delimitador: ,
✓ Headers encontrados: 45 columnas

Análisis de Regla de Extracción:
✓ Columna fecha 'Año' encontrada
✓ Columnas fuente: ['Total_M', 'Total_F']
✗ ADVERTENCIA: Columna 'Total_M' no encontrada exactamente
  → Coincidencia parcial: 'Total Hombres'

Desagregaciones Configuradas:
✓ Sexo (2 valores)
✓ Edad (18 rangos)
✓ Comuna (22 elementos)

Estimación:
- Filas en CSV: 264
- Combinaciones por fila: ~792
- Total de registros Dato a crear: ~209,088

⚠️ Recomendaciones:
1. Verificar nombres de columnas en regla de extracción
2. Considerar límite de filas para prueba inicial
3. Hacer backup de BD antes de procesar
```

### 3. generar_embeddings.py

**Tamaño:** 2,032 bytes

**Propósito:**
Genera y almacena embeddings vectoriales para búsqueda semántica.

**Funcionalidad:**
```python
def handle(self, *args, **options):
    """
    1. Carga modelo sentence-transformers
    2. Itera sobre indicadores, temas, dominios
    3. Genera embedding de 384 dimensiones
    4. Guarda en DocumentoVector con pgvector
    5. Reporta progreso y estadísticas
    """
```

**Tipos de Documentos Indexados:**
- Indicadores (nombre + descripción)
- Temas (nombre + descripción)
- Subtemas (nombre + descripción)
- Dominios (nombre + descripción)

**Ejemplo de Ejecución:**
```bash
python manage.py generar_embeddings

Cargando modelo all-MiniLM-L6-v2...
✓ Modelo cargado

Procesando Indicadores...
[1/150] Población total por sexo... ✓
[2/150] Tasa de natalidad... ✓
...

Procesando Temas...
[1/25] Educación... ✓
...

Resumen:
- Indicadores indexados: 150
- Temas indexados: 25
- Subtemas indexados: 75
- Dominios indexados: 5
Total: 255 documentos
```

### 4. preload_cache.py

**Tamaño:** 4,948 bytes

**Propósito:**
Precarga el caché con datos frecuentemente accedidos para mejorar performance inicial.

**Funcionalidad:**
```python
def handle(self):
    """
    1. Cachea lista de dominios
    2. Cachea temas por cada dominio
    3. Cachea indicadores por subtema
    4. Cachea desagregaciones por indicador
    5. Precarga datos de gráficos populares
    """
```

**Estrategia de Precarga:**
- Dominios y temas (acceso frecuente)
- Indicadores destacados o populares
- Primeras páginas de datos
- Desagregaciones disponibles

**Uso:**
```bash
python manage.py preload_cache

Precargando caché del sistema...
✓ Dominios (5 items)
✓ Temas (25 items)
✓ Indicadores por subtema (75 subtemas)
✓ Desagregaciones (50 indicadores)

Caché precargado: 155 entradas
Tiempo: 12.5 segundos
```

### 5. cargar_elementos_geo.py

**Tamaño:** 16,031 bytes

**Propósito:**
Importa elementos geográficos desde shapefiles u otros formatos geoespaciales.

**Funcionalidad:**
```python
def handle(self, shapefile_path, capa_id):
    """
    1. Lee shapefile con geopandas/fiona
    2. Extrae geometrías y atributos
    3. Convierte a WKT
    4. Crea/actualiza ElementoGeo
    5. Asocia a CapaGeo correspondiente
    """
```

**Formatos Soportados:**
- Shapefiles (.shp)
- GeoJSON (.geojson)
- KML (.kml)

**Ejemplo:**
```bash
python manage.py cargar_elementos_geo \
    --shapefile docs/corregimientos/Corregimientos.shp \
    --capa-id 2 \
    --codigo-field CODIGO \
    --nombre-field NOMBRE

Leyendo shapefile...
CRS detectado: PROJCS["MAGNA_Cali_Valle_del_Cauca_2009",...]
Elementos encontrados: 15

Importando:
[1/15] Corregimiento 1 - La Elvira... ✓
[2/15] Corregimiento 2 - La Buitrera... ✓
...

Resumen:
- Creados: 12
- Actualizados: 3
- Errores: 0
```

### 6. validate_data.py

**Tamaño:** 3,018 bytes

**Propósito:**
Ejecuta validaciones automáticas de calidad de datos.

**Funcionalidad:**
```python
def handle(self, indicador_id=None):
    """
    Ejecuta DataValidator.validate_all()
    Genera reporte de validación
    Opcionalmente envía alertas
    """
```

**Validaciones Ejecutadas:**
- Valores nulos
- Valores negativos
- Fechas inconsistentes
- Duplicados
- Outliers estadísticos
- Consistencia temporal
- Completitud geográfica
- Rangos de porcentajes
- Frescura de datos

## Utilidades y Helpers

### cache_utils.py

**Funciones Principales:**
```python
generate_cache_key(prefix, *args, **kwargs)
    → Genera MD5 hash único

@cache_grafico_data(timeout)
    → Decorador para cachear datos de gráficos

@cache_query_result(timeout)
    → Decorador para cachear queries DB

get_cached_indicadores_by_subtema(subtema_id)
    → Helper específico

get_cached_desagregaciones(indicador_id)
    → Helper específico

invalidate_indicator_cache(indicador_id)
    → Invalida caché de indicador

# Signals para auto-invalidación
@receiver(post_save, sender='indicadores.Dato')
@receiver(post_save, sender='indicadores.Indicador')
@receiver(post_save, sender='indicadores.Grafico')
```

### embeddings.py

**Clase Principal:**
```python
class EmbeddingService:
    """
    Servicio centralizado para embeddings
    """
    
    def __init__(model_name='all-MiniLM-L6-v2'):
        # Carga modelo local o descarga
        # Caché en ~/.cache/sentence-transformers/
    
    def get_embedding(text: str) → List[float]:
        # Genera embedding de 384 dims
    
    def search_relevant_data(query, top_k=5, threshold=0.6):
        # Búsqueda semántica con filtro de similitud
    
    def _enrich_result_data(doc):
        # Agrega datos contextuales
```

### search.py

**Clase Principal:**
```python
class SemanticSearch:
    """
    Wrapper de alto nivel para búsqueda semántica
    """
    
    def __init__():
        self.embedding_service = EmbeddingService()
    
    def buscar_similar(consulta, tipo_doc=None, top_k=5, umbral=0.6):
        # Usa pgvector CosineDistance
        # Filtra por tipo de documento
        # Retorna resultados ordenados
```

### data_validation.py

**Clases Principales:**
```python
class DataValidationResult:
    """Resultado de una validación"""
    validation_type: str
    status: str  # 'success', 'warning', 'error'
    message: str
    affected_records: int
    details: Dict

class DataValidator:
    """Ejecutor de validaciones"""
    
    def validate_all(indicador_id=None):
        # Ejecuta 10 validaciones
        # Retorna lista de resultados
    
    # Validaciones privadas:
    _validate_null_values()
    _validate_negative_values()
    _validate_date_consistency()
    _validate_duplicate_records()
    _validate_outliers()
    _validate_temporal_consistency()
    _validate_geographic_completeness()
    _validate_population_constraints()
    _validate_percentage_bounds()
    _validate_data_freshness()
```

### schema_detection.py

**Clase Principal:**
```python
class SchemaDetector:
    """
    Detector automático de esquemas en archivos
    """
    
    def analyze_file_with_context(file_path, indicador_context, sample_rows=1000):
        # Lee archivo (CSV/Excel)
        # Analiza cada columna
        # Clasifica tipos
        # Genera sugerencias
        # Valida compatibilidad cartesiana
    
    def _analyze_column(series, column_name):
        # Detecta tipo por nombre
        # Valida con datos
        # Retorna confianza
    
    def _detect_indicator_type(context, df):
        # Usa patrones conocidos
        # Analiza nombres de columnas
    
    def _suggest_contextual_extraction_rules(schema, df, type, context):
        # Genera reglas automáticas
        # Sugiere fórmulas
        # Mapea desagregaciones
```

### background.py

**Funciones:**
```python
def lanzar_procesamiento_en_background(proceso_id):
    """
    Lanza thread daemon para procesamiento
    No bloquea request HTTP
    """
    t = threading.Thread(target=_run_command_in_thread, args=(proceso_id,), daemon=True)
    t.start()
    return t

def _run_command_in_thread(proceso_id):
    """
    1. Actualiza estado a 'procesando'
    2. Ejecuta subprocess manage.py
    3. Captura stdout/stderr
    4. Escribe logs en batch
    5. Actualiza estado final
    """

def _with_retry(func, attempts=5, base_sleep=0.2):
    """Reintenta operaciones con backoff exponencial"""
```

## Sistema de Admin Personalizado

### CustomAdmins Implementados

**ReglaExtraccionAdmin:**
```python
- Custom change_view con manual de fórmulas
- Botón "Procesar Datos"
- Vista de confirmación con diagnóstico
- Redirección a visor en vivo
- Fieldsets organizados
- Help text contextual
```

**GraficoAdmin:**
```python
- Inlines para GraficoSerie
- Preview de configuración
- Widgets personalizados (ColorWidget)
```

**DocumentoInfraestructuraAdmin:**
```python
- CKEditor5 con configuración 'infraestructura'
- Upload de archivos (PDF, Word)
- Control de versiones
- Estados de publicación
```

## Middleware Personalizado

### ChatRateLimitMiddleware

```python
class ChatRateLimitMiddleware:
    """
    Rate limiting para endpoints de chat
    
    Límites:
    - 5 requests por minuto por IP
    - Cache key: 'chat_rate_limit_{ip}'
    - TTL: 60 segundos
    
    Response:
    - 429 Too Many Requests si excede
    - Header 'retry_after': 60
    """
```

## Integración con Servicios Externos

### Cerebras Cloud SDK

```python
from cerebras.cloud.sdk import Cerebras

client = Cerebras(api_key='csk-...')

# Chat completion
response = client.chat.completions.create(
    model="gpt-oss-120b",
    messages=[...],
    max_tokens=14200,
    stream=True
)

# Tools/Functions
tools = [
    {
        "type": "function",
        "function": {
            "name": "buscar_indicadores",
            "description": "Busca indicadores por criterios",
            "parameters": {...}
        }
    }
]
```

### Sentence Transformers

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
embedding = model.encode("texto a vectorizar")
# → array[384] float32
```

### pgvector

```python
from pgvector.django import VectorField, CosineDistance

# En modelo
embedding = VectorField(dimensions=384)

# En query
DocumentoVector.objects.annotate(
    distancia=CosineDistance('embedding', query_embedding)
).order_by('distancia')[:5]
```

## Conclusiones de Extensiones

### ✅ Fortalezas
- Comandos bien estructurados y documentados
- Sistema de validación robusto
- Detección inteligente de esquemas
- Integración avanzada de IA
- Helpers reutilizables

### ⚠️ Áreas de Mejora
- Comandos podrían tener más opciones
- Falta documentación de uso
- Sin manejo de errores en algunos casos
- Podrían agregarse más validaciones
- Sistema de background limitado (threads vs Celery)

### 💡 Recomendaciones
1. Documentar cada comando con --help detallado
2. Agregar tests para comandos críticos
3. Migrar background processing a Celery
4. Implementar sistema de plugins
5. Crear CLI interactivo para operaciones comunes
