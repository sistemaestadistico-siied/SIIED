# 3. CORE DEL SISTEMA

## Arquitectura MVC (MTV en Django)

### Estructura de Archivos Principal

```
myproject/
├── myproject/
│   ├── settings.py        # Configuración global (323 líneas)
│   ├── urls.py            # URLs raíz (50 líneas)
│   └── wsgi.py            # WSGI application
│
└── indicadores/
    ├── models.py          # 33 modelos (1,073 líneas)
    ├── views.py           # Lógica principal (9,153 líneas) ⚠️
    ├── urls.py            # 83 URLs (83 líneas)
    ├── admin.py           # Configuración admin (1,018 líneas)
    ├── middleware.py      # Rate limiting (40 líneas)
    ├── cache_utils.py     # Sistema de caché (264 líneas)
    ├── embeddings.py      # Servicio de embeddings (256 líneas)
    ├── search.py          # Búsqueda semántica (54 líneas)
    ├── data_validation.py # Validaciones (431 líneas)
    ├── schema_detection.py# Detección esquemas (559 líneas)
    ├── background.py      # Workers (159 líneas)
    ├── utils.py           # Utilidades (4,310 bytes)
    └── management/commands/
        ├── procesar_microdata_cartesiano.py (857 líneas)
        ├── diagnosticar_microdata.py (33,300 bytes)
        ├── generar_embeddings.py (2,032 bytes)
        ├── preload_cache.py (4,948 bytes)
        ├── cargar_elementos_geo.py (16,031 bytes)
        └── validate_data.py (3,018 bytes)
```

## Flujo de Datos Principal

### 1. Request → Response Flow

```
┌─────────────────────────────────────────────────────────────┐
│  1. Cliente HTTP Request                                     │
│     GET /dominios/desarrollo-social/educacion/               │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Django URL Dispatcher (urls.py)                          │
│     path('dominios/<slug>/<slug>/', views.tema_detalle)      │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Middleware Stack                                         │
│     ├─ SecurityMiddleware                                   │
│     ├─ WhiteNoiseMiddleware (archivos estáticos)            │
│     ├─ SessionMiddleware                                    │
│     ├─ CsrfViewMiddleware                                   │
│     ├─ AuthenticationMiddleware                             │
│     └─ ChatRateLimitMiddleware (custom)                     │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  4. View Function (views.py)                                 │
│     def tema_detalle(request, dominio_slug, tema_slug):      │
│         - Validar parámetros                                 │
│         - Consultar caché                                    │
│         - Si no existe en caché: Query DB                    │
│         - Procesar datos                                     │
│         - Cachear resultado                                  │
│         - Renderizar template                                │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  5. ORM Queries (models.py)                                  │
│     MenuTema.objects.get(slug=tema_slug, dominio__slug=...)  │
│     - Ejecuta SQL optimizado                                 │
│     - Usa select_related/prefetch_related                    │
│     - Aplica índices de BD                                   │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  6. PostgreSQL Database                                      │
│     - Ejecuta query con índices                              │
│     - Retorna resultados                                     │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  7. Template Rendering                                       │
│     render(request, 'indicadores/tema_detalle.html', ctx)    │
│     - Procesa template con Django Template Language         │
│     - Incluye archivos estáticos (CSS, JS)                  │
│     - Genera HTML final                                      │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  8. HTTP Response                                            │
│     - Status: 200 OK                                         │
│     - Content-Type: text/html                                │
│     - Body: HTML renderizado                                 │
└─────────────────────────────────────────────────────────────┘
```

### 2. API Flow (JSON Responses)

```
Cliente JS → fetch('/api/get_graficos/123/')
                ↓
         URL: path('api/get_graficos/<int:indicador_id>/')
                ↓
         View: get_graficos(request, indicador_id)
                ↓
         1. Verifica caché (@cache_grafico_data)
         2. Si miss: Query Grafico.objects.filter(...)
         3. Serializa a JSON
         4. Cachea resultado
         5. Return JsonResponse(data)
                ↓
         Cliente recibe JSON y renderiza con Plotly
```

## Sistema de Caché (cache_utils.py)

### Estrategia de Caché Multi-Nivel

```python
# Nivel 1: Page Cache (15 minutos)
CACHE_TIMEOUT_PAGE = 15 * 60

# Nivel 2: API Cache (30 minutos)
CACHE_TIMEOUT_API = 30 * 60

# Nivel 3: Query Cache (60 minutos)
CACHE_TIMEOUT_QUERY = 60 * 60
```

### Funciones Principales de Caché

#### 1. **generate_cache_key()**
```python
def generate_cache_key(prefix, *args, **kwargs):
    """
    Genera clave única MD5 basada en parámetros
    Ejemplo: "grafico_get_graficos_abc123456789"
    """
    key_data = {'args': args, 'kwargs': sorted(kwargs.items())}
    key_string = json.dumps(key_data, sort_keys=True)
    key_hash = hashlib.md5(key_string.encode()).hexdigest()[:12]
    return f"{prefix}_{key_hash}"
```

#### 2. **@cache_grafico_data** (Decorador)
```python
@cache_grafico_data(timeout=CACHE_TIMEOUT_API)
def get_graficos(request, indicador_id):
    # Extrae filtros de request.GET
    # Genera clave única por indicador + filtros
    # Si existe en caché: retorna inmediatamente
    # Si no: ejecuta función y cachea resultado
```

Uso en views.py:
- `get_graficos()` - Datos de gráficos
- `get_desagregaciones()` - Desagregaciones disponibles
- `geojson_indicador()` - Datos geoespaciales

#### 3. **@cache_query_result** (Decorador)
```python
@cache_query_result(timeout=CACHE_TIMEOUT_QUERY)
def get_cached_indicadores_by_subtema(subtema_id):
    # Cachea resultados de queries complejas
```

#### 4. **Funciones de Ayuda**
```python
# Cachea lista de indicadores por subtema
get_cached_indicadores_by_subtema(subtema_id)

# Cachea desagregaciones de un indicador
get_cached_desagregaciones(indicador_id)
```

### Invalidación Automática de Caché

**Signals implementados:**
```python
@receiver(post_save, sender='indicadores.Dato')
def invalidate_dato_cache(sender, instance, **kwargs):
    invalidate_indicator_cache(instance.indicador_id)

@receiver(post_delete, sender='indicadores.Dato')
def invalidate_dato_cache_on_delete(sender, instance, **kwargs):
    invalidate_indicator_cache(instance.indicador_id)

@receiver(post_save, sender='indicadores.Indicador')
def invalidate_indicador_cache(sender, instance, **kwargs):
    invalidate_indicator_cache(instance.id)
    invalidate_subtema_cache(instance.subtema_id)

@receiver(post_save, sender='indicadores.Grafico')
def invalidate_grafico_cache(sender, instance, **kwargs):
    invalidate_indicator_cache(instance.indicador_id)
```

**Limitación actual:**
```python
# ⚠️ No implementado completamente
# Django cache framework nativo no soporta delete_pattern
# Se requeriría Redis con django-redis para implementación completa
```

## Gestión de Sesiones

### Configuración de Sesiones

```python
# En settings.py (implícito)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # Default
SESSION_COOKIE_AGE = 1209600  # 2 semanas
SESSION_SAVE_EVERY_REQUEST = False
```

### Uso en Chat

```python
# En views.py - chat_message()
if not request.session.session_key:
    request.session.create()
    request.session.modified = True

if 'conversation' not in request.session:
    request.session['conversation'] = []

# Almacena historial de conversación
request.session['conversation'].append({
    'role': 'user',
    'content': user_message
})
request.session.modified = True
request.session.save()
```

### Control de Requests Activos

```python
# Diccionario en memoria para tracking
active_requests = {}
active_requests_lock = threading.Lock()

# Registrar nuevo request
with active_requests_lock:
    active_requests[session_id] = {
        'timestamp': timezone.now(),
        'request_id': request_id,
        'active': True,
        'cancelled': False
    }

# Limpiar requests antiguos
def cleanup_old_requests():
    cutoff = timezone.now() - timedelta(minutes=5)
    for sid, req in list(active_requests.items()):
        if req['timestamp'] < cutoff:
            del active_requests[sid]
```

## Middleware Personalizado

### ChatRateLimitMiddleware

**Ubicación:** `indicadores/middleware.py`

**Funcionalidad:**
```python
class ChatRateLimitMiddleware:
    """
    Limita requests al chat a 5 mensajes por minuto por IP
    """
    
    def __call__(self, request):
        if request.path.startswith('/chat/message/'):
            ip = self.get_client_ip(request)
            cache_key = f'chat_rate_limit_{ip}'
            current_count = cache.get(cache_key, 0)
            
            if current_count >= 5:
                return JsonResponse({
                    'error': 'Demasiadas consultas. Espera un momento.',
                    'retry_after': 60
                }, status=429)
            
            cache.set(cache_key, current_count + 1, 60)
        
        return self.get_response(request)
```

**Características:**
- Usa caché de Django para contar requests
- TTL de 60 segundos
- Límite: 5 requests/minuto/IP
- Considera X-Forwarded-For para proxies

## Procesamiento de Background

### Sistema de Workers (background.py)

**Arquitectura:**
```python
┌─────────────────────────────────────────┐
│  Admin: Click "Procesar Datos"          │
└────────────────┬────────────────────────┘
                 ▼
┌─────────────────────────────────────────┐
│  Crea ProcesoExtraccion (estado=pending)│
└────────────────┬────────────────────────┘
                 ▼
┌─────────────────────────────────────────┐
│  lanzar_procesamiento_en_background()   │
│  - Inicia Thread daemon                 │
│  - Retorna inmediatamente               │
└────────────────┬────────────────────────┘
                 ▼
┌─────────────────────────────────────────┐
│  Thread: _run_command_in_thread()       │
│  1. Actualiza estado a 'procesando'     │
│  2. Ejecuta subprocess manage.py cmd    │
│  3. Captura stdout/stderr en tiempo real│
│  4. Escribe logs en batch (10 líneas)   │
│  5. Al terminar: estado='completado'    │
└────────────────┬────────────────────────┘
                 ▼
┌─────────────────────────────────────────┐
│  Usuario ve logs en tiempo real vía     │
│  polling AJAX a /api/procesos/.../logs/ │
└─────────────────────────────────────────┘
```

**Características Clave:**
```python
# Buffering de logs para reducir I/O
FLUSH_EVERY_N = 10       # Cada 10 líneas
FLUSH_EVERY_SEC = 0.5    # O cada 500ms

# Reintentos automáticos con backoff exponencial
def _with_retry(func, attempts=5, base_sleep=0.2):
    for intento in range(attempts):
        try:
            return func()
        except OperationalError:
            close_old_connections()
            time.sleep(base_sleep * (2 ** intento))

# Proceso hijo con unbuffered output
env = os.environ.copy()
env['PYTHONUNBUFFERED'] = '1'
```

**Limitaciones:**
- ⚠️ Usa threads en lugar de Celery/queue system
- ⚠️ No persistente (se pierde al reiniciar servidor)
- ⚠️ No escalable horizontalmente
- ✅ Funcional para cargas pequeñas/medianas

## Sistema de Logging

### Configuración en settings.py

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    
    'formatters': {
        'verbose': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'simple': {
            'format': '[%(levelname)s] %(message)s'
        },
    },
    
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'logs/chat.log',
            'formatter': 'verbose',
        },
        'tools_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'logs/tools.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'indicadores': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
        },
        'indicadores.views': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
        },
        'indicadores.tools': {
            'handlers': ['tools_file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
```

### Uso en el Código

```python
import logging
logger = logging.getLogger(__name__)

# En views.py
logger.info(f"Nueva consulta - Session: {session_id}, Mensaje: {msg}")
logger.error(f"Error en event stream: {e}", exc_info=True)
logger.debug(f"Cache HIT: {cache_key}")

# En embeddings.py
logger.error(f"Error al generar embedding: {str(e)}")
logger.warning(f"Indicador {doc.referencia_id} no encontrado")
```

## Gestión de Archivos Estáticos

### Configuración WhiteNoise

```python
# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Después de Security
    # ...
]

# Storage
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Paths
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Caché
WHITENOISE_MAX_AGE = 31536000 if not DEBUG else 0  # 1 año en prod
WHITENOISE_USE_FINDERS = True
WHITENOISE_MANIFEST_STRICT = False
WHITENOISE_ALLOW_ALL_ORIGINS = True
```

**Proceso de Compilación:**
```bash
python manage.py collectstatic
# Copia archivos de:
# - indicadores/static/ 
# - django admin static files
# Hacia: staticfiles/
# WhiteNoise comprime y genera manifest.json
```

## Gestión de Archivos Media

```python
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# En urls.py
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

**Archivos subidos:**
- `microdata/` - Archivos CSV de microdata
- `infraestructura/documentos/` - PDFs y Word

## Seguridad Implementada

### CSRF Protection
```python
# Middleware activo
'django.middleware.csrf.CsrfViewMiddleware'

# Excepciones para APIs externas
@csrf_exempt
def chat_message(request):
    # API para chat requiere exención
```

### Clickjacking Protection
```python
'django.middleware.clickjacking.XFrameOptionsMiddleware'
```

### SQL Injection Protection
```python
# Django ORM previene SQL injection automáticamente
# Uso de queries parametrizadas
Indicador.objects.filter(id=indicador_id)  # ✅ Seguro
```

### XSS Protection
```python
# Django templates auto-escapean HTML
{{ indicador.nombre }}  # ✅ Escapado automáticamente

# Para HTML confiable
{{ documento.contenido|safe }}  # CKEditor genera HTML seguro
```

## Problemas Encontrados en el Core

### 🔴 Críticos

1. **views.py Monolítico (9,153 líneas)**
   - Dificulta mantenimiento
   - Complica testing
   - Aumenta riesgo de bugs

2. **Sin Queue System**
   - Procesamiento en threads no escalable
   - Pérdida de trabajos al reiniciar

3. **Credenciales Hardcodeadas**
   - SECRET_KEY, DB passwords, API keys en código

### 🟡 Moderados

1. **Cache Invalidation Incompleta**
   - No hay delete_pattern
   - Requiere Redis para implementación completa

2. **Sin Monitoreo de Performance**
   - No hay APM integrado
   - Dificulta detectar cuellos de botella

3. **Logging a Archivos Locales**
   - No centralizado
   - Dificulta debugging en producción

### 🟢 Menores

1. **Sin Compression HTTP**
   - GZipMiddleware no configurado

2. **Session Backend en DB**
   - Podría usar Redis para mejor performance

## Recomendaciones

1. **Refactorizar views.py** en módulos por funcionalidad
2. **Implementar Celery** para trabajos en background
3. **Migrar caché a Redis** para invalidación avanzada
4. **Variables de entorno** para todas las credenciales
5. **Implementar APM** (Sentry, New Relic, etc.)
6. **Centralizar logs** (ELK stack, CloudWatch, etc.)
