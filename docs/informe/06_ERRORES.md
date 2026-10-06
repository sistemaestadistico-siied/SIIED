# 6. ANÁLISIS DE ERRORES Y PROBLEMAS

## 🔴 ERRORES CRÍTICOS

### 1. Seguridad - Credenciales Expuestas

**Archivo:** `myproject/settings.py`

**Problema:**
```python
# ❌ CRÍTICO: SECRET_KEY hardcodeada
SECRET_KEY = '***REMOVED***'

# ❌ CRÍTICO: Credenciales de base de datos en texto plano
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'indicadores',
        'USER': 'amiranda',
        'PASSWORD': '***REMOVED***',  # ⚠️ Contraseña expuesta
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

**Archivo:** `indicadores/views.py` (línea 5512)
```python
# ❌ CRÍTICO: API Key de Cerebras hardcodeada
self.api_key = '***REMOVED***'
```

**Impacto:**
- 🔥 Acceso no autorizado a la base de datos
- 🔥 Compromiso de la SECRET_KEY permite:
  - Falsificación de tokens CSRF
  - Falsificación de cookies de sesión
  - Desencriptación de datos
- 🔥 Uso indebido de API Key de Cerebras (costos no autorizados)

**Solución Recomendada:**
```python
# settings.py
import os
from dotenv import load_dotenv
load_dotenv()

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# views.py
class ChatService:
    def __init__(self):
        self.api_key = os.environ.get('CEREBRAS_API_KEY')
```

---

### 2. Configuración de Producción Insegura

**Archivo:** `myproject/settings.py`

**Problemas:**
```python
# ❌ CRÍTICO: DEBUG activado
DEBUG = True

# ⚠️ ALLOWED_HOSTS muy restrictivo para producción
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
```

**Impacto:**
- 🔥 DEBUG=True expone:
  - Stack traces detallados a usuarios
  - Variables de entorno
  - Configuración del sistema
  - Rutas del servidor
- ⚠️ Servidor no accesible desde otras IPs

**Solución:**
```python
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')

# Configuración diferenciada por entorno
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
```

---

### 3. Falta de Tests Automatizados

**Archivo:** `indicadores/tests.py`
```python
from django.test import TestCase

# Create your tests here.
```

**Impacto:**
- ❌ Sin cobertura de código
- ❌ Imposible detectar regresiones
- ❌ Refactoring arriesgado
- ❌ Confianza baja en despliegues

**Líneas de código sin tests:**
- `views.py`: 9,153 líneas
- `models.py`: 1,073 líneas  
- `admin.py`: 1,018 líneas
- Comandos: ~50,000 bytes
- **Total:** ~15,000+ líneas sin tests

**Solución:**
```python
# tests/test_models.py
class IndicadorTestCase(TestCase):
    def setUp(self):
        self.dominio = MenuDominio.objects.create(...)
        self.indicador = Indicador.objects.create(...)
    
    def test_crear_indicador(self):
        self.assertEqual(self.indicador.activo, True)
    
    def test_calcular_datos_agregados(self):
        # ...

# tests/test_views.py
class ViewsTestCase(TestCase):
    def test_home_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

# Objetivo: >80% coverage
```

---

## 🟡 ERRORES MODERADOS

### 4. Archivo views.py Monolítico

**Archivo:** `indicadores/views.py`
**Tamaño:** 9,153 líneas

**Problema:**
Un solo archivo con todas las vistas, servicios, helpers y clases.

**Impacto:**
- ⚠️ Difícil de mantener
- ⚠️ Dificulta code review
- ⚠️ Alto riesgo de conflictos en Git
- ⚠️ Imposible de testear eficientemente
- ⚠️ Violación del principio de responsabilidad única

**Solución:**
```
indicadores/
├── views/
│   ├── __init__.py
│   ├── home.py           # Vista de inicio
│   ├── indicadores.py    # Vistas de indicadores
│   ├── mapas.py          # Vistas geoespaciales
│   ├── chat.py           # Vistas de chat
│   └── api.py            # Endpoints API
├── services/
│   ├── __init__.py
│   ├── chat_service.py
│   ├── embedding_service.py
│   └── validation_service.py
└── utils/
    ├── __init__.py
    ├── cache.py
    └── helpers.py
```

---

### 5. Sistema de Background Jobs Limitado

**Archivo:** `indicadores/background.py`

**Problema:**
```python
def lanzar_procesamiento_en_background(proceso_id):
    t = threading.Thread(target=_run_command_in_thread, args=(proceso_id,), daemon=True)
    t.start()
    return t
```

**Impacto:**
- ⚠️ No persistente (se pierde al reiniciar servidor)
- ⚠️ No escalable horizontalmente
- ⚠️ Sin retry automático en caso de fallo
- ⚠️ Sin priorización de tareas
- ⚠️ Difícil de monitorear

**Solución:**
```python
# Migrar a Celery
# requirements.txt
celery==5.3.4
redis==5.0.1

# tasks.py
from celery import shared_task

@shared_task(bind=True, max_retries=3)
def procesar_microdata(self, proceso_id):
    try:
        # Procesamiento
        pass
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

# Lanzar tarea
from tasks import procesar_microdata
procesar_microdata.delay(proceso_id)
```

---

### 6. Invalidación de Caché Incompleta

**Archivo:** `indicadores/cache_utils.py`

**Problema:**
```python
def invalidate_indicator_cache(indicador_id):
    """
    Invalida todas las entradas de caché relacionadas con un indicador.
    """
    # Patrones de claves a invalidar
    patterns = [
        f"grafico_*_{indicador_id}_*",
        f"query_*_{indicador_id}_*",
    ]
    
    # ❌ En Django cache framework no hay delete_pattern nativo
    logger.info(f"Cache invalidation requested for indicator {indicador_id}")
    
    # ❌ No se invalida realmente
```

**Impacto:**
- ⚠️ Datos obsoletos en caché
- ⚠️ Usuarios ven información desactualizada
- ⚠️ Necesidad de limpiar caché manualmente

**Solución:**
```python
# Migrar a Redis con django-redis
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Con django-redis
from django.core.cache import cache
cache.delete_pattern(f"*_{indicador_id}_*")
```

---

### 7. Versión de Django Desactualizada

**Archivo:** `requirements.txt`

**Problema:**
```python
Django==3.2.12
```

**Impacto:**
- ⚠️ No es la versión LTS más reciente (4.2.x)
- ⚠️ Pierde mejoras de seguridad
- ⚠️ Pierde mejoras de performance
- ⚠️ No tiene async views nativas

**Solución:**
```bash
# Actualizar a Django 4.2 LTS
pip install Django==4.2.11

# Revisar breaking changes:
# https://docs.djangoproject.com/en/4.2/releases/4.0/
# https://docs.djangoproject.com/en/4.2/releases/4.1/
# https://docs.djangoproject.com/en/4.2/releases/4.2/
```

---

## 🟢 PROBLEMAS MENORES

### 8. Código Duplicado

**Ejemplo 1:** Validación de parámetros repetida
```python
# En múltiples vistas
if not indicador_id:
    return JsonResponse({'error': 'indicador_id requerido'}, status=400)

try:
    indicador = Indicador.objects.get(id=indicador_id)
except Indicador.DoesNotExist:
    return JsonResponse({'error': 'Indicador no encontrado'}, status=404)
```

**Solución:**
```python
# decorators.py
def require_indicador(view_func):
    @wraps(view_func)
    def wrapper(request, indicador_id, *args, **kwargs):
        try:
            indicador = Indicador.objects.get(id=indicador_id, activo=True)
            return view_func(request, indicador, *args, **kwargs)
        except Indicador.DoesNotExist:
            return JsonResponse({'error': 'Indicador no encontrado'}, status=404)
    return wrapper

# Uso
@require_indicador
def get_graficos(request, indicador):
    # indicador ya validado y cargado
```

---

### 9. Queries N+1 Potenciales

**Ubicación:** Varias vistas

**Problema:**
```python
# En subtema_detalle
subtema = get_object_or_404(MenuSubtema, slug=subtema_slug)
indicadores = subtema.indicadores.filter(activo=True)

for indicador in indicadores:
    # ❌ Query adicional por cada indicador
    operacion = indicador.operacion
    # ❌ Query adicional por cada indicador
    graficos = indicador.graficos.all()
```

**Solución:**
```python
subtema = get_object_or_404(
    MenuSubtema.objects.select_related('tema__dominio'),
    slug=subtema_slug
)

indicadores = subtema.indicadores.filter(activo=True).select_related(
    'operacion'
).prefetch_related(
    'graficos',
    'dominios_desagregacion_tematica',
    'dominios_desagregacion_geografica'
)
```

---

### 10. Falta de Paginación

**Problema:**
```python
# En algunas vistas que retornan listas grandes
def api_microdata_datasets(request):
    datasets = Microdata.objects.all()  # ❌ Sin límite
    return JsonResponse({'datasets': list(datasets.values())})
```

**Impacto:**
- ⚠️ Respuestas muy grandes
- ⚠️ Consumo excesivo de memoria
- ⚠️ Tiempo de respuesta lento

**Solución:**
```python
from django.core.paginator import Paginator

def api_microdata_datasets(request):
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    
    datasets = Microdata.objects.all()
    paginator = Paginator(datasets, page_size)
    page_obj = paginator.get_page(page)
    
    return JsonResponse({
        'datasets': list(page_obj.object_list.values()),
        'page': page_obj.number,
        'total_pages': paginator.num_pages,
        'total_items': paginator.count
    })
```

---

### 11. Logging Inconsistente

**Problema:**
```python
# Algunos lugares usan print
print(f"Procesando fila {i}")

# Otros usan self.stdout.write
self.stdout.write(f"Datos creados: {count}")

# Otros usan logger
logger.info(f"Cache HIT: {key}")
```

**Solución:**
```python
# Estandarizar en logger siempre
import logging
logger = logging.getLogger(__name__)

# En comandos, usar logger + verbosity
if self.verbosity >= 2:
    logger.debug(f"Procesando fila {i}")
```

---

### 12. Sin Documentación API

**Problema:**
- ❌ Sin OpenAPI/Swagger
- ❌ Sin documentación de endpoints
- ❌ Sin ejemplos de uso

**Solución:**
```python
# Implementar drf-spectacular
pip install drf-spectacular

# settings.py
INSTALLED_APPS += ['drf_spectacular']

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# urls.py
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns += [
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
```

---

### 13. Manejo de Errores Inconsistente

**Problema:**
```python
# Algunos lugares
try:
    # código
except Exception as e:
    return JsonResponse({'error': str(e)})

# Otros lugares
try:
    # código  
except Exception:
    pass  # ❌ Silencia errores

# Otros lugares
try:
    # código
except:  # ❌ Bare except
    logger.error("Error")
```

**Solución:**
```python
# Usar excepciones específicas
try:
    dato = Dato.objects.get(id=dato_id)
except Dato.DoesNotExist:
    return JsonResponse({'error': 'Dato no encontrado'}, status=404)
except ValidationError as e:
    return JsonResponse({'error': str(e)}, status=400)
except Exception as e:
    logger.exception("Error inesperado")
    return JsonResponse({'error': 'Error interno'}, status=500)
```

---

## 📊 RESUMEN DE ERRORES

| Categoría | Críticos | Moderados | Menores | Total |
|-----------|----------|-----------|---------|-------|
| **Seguridad** | 3 | 0 | 0 | 3 |
| **Arquitectura** | 0 | 2 | 1 | 3 |
| **Performance** | 0 | 1 | 2 | 3 |
| **Calidad** | 1 | 1 | 4 | 6 |
| **Mantenibilidad** | 0 | 1 | 0 | 1 |
| **TOTAL** | **4** | **5** | **7** | **16** |

---

## 🎯 PLAN DE ACCIÓN RECOMENDADO

### Fase 1: Urgente (Semana 1-2)
1. ✅ Migrar credenciales a variables de entorno
2. ✅ Configurar DEBUG=False para producción
3. ✅ Rotar SECRET_KEY y API keys
4. ✅ Configurar ALLOWED_HOSTS correctamente
5. ✅ Implementar HTTPS y cookies seguras

### Fase 2: Crítico (Semana 3-4)
1. ✅ Implementar tests unitarios básicos (>50% coverage)
2. ✅ Refactorizar views.py en módulos
3. ✅ Migrar a Redis para caché
4. ✅ Implementar Celery para background jobs
5. ✅ Actualizar Django a 4.2 LTS

### Fase 3: Importante (Mes 2)
1. ✅ Optimizar queries (eliminar N+1)
2. ✅ Implementar paginación
3. ✅ Estandarizar logging
4. ✅ Documentar API con Swagger
5. ✅ Implementar CI/CD

### Fase 4: Mejoras (Mes 3+)
1. ✅ Aumentar cobertura de tests a >80%
2. ✅ Implementar APM (Sentry)
3. ✅ Optimizar frontend
4. ✅ Implementar rate limiting avanzado
5. ✅ Dockerizar aplicación

---

## 💡 BUENAS PRÁCTICAS ENCONTRADAS

A pesar de los errores, el código también tiene fortalezas:

✅ Uso de Django ORM (previene SQL injection)  
✅ CSRF protection habilitado  
✅ Sistema de caché implementado  
✅ Índices de base de datos optimizados  
✅ Uso de signals para automatización  
✅ Validaciones de datos robustas  
✅ Logging estructurado (aunque inconsistente)  
✅ Separación de concerns en algunos módulos  

---

## 🔍 HERRAMIENTAS RECOMENDADAS

### Análisis de Código
```bash
# Linting
pip install pylint black isort
pylint indicadores/
black --check .
isort --check-only .

# Security
pip install bandit safety
bandit -r indicadores/
safety check

# Complexity
pip install radon
radon cc indicadores/views.py -a
```

### Testing
```bash
pip install pytest pytest-cov pytest-django
pytest --cov=indicadores --cov-report=html
```

### Performance
```bash
pip install django-debug-toolbar django-silk
# Monitorear queries y tiempos de respuesta
```

---

**FIN DEL ANÁLISIS DE ERRORES**
