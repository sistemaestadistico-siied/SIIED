# 1. BASE TECNOLÓGICA

## Stack Tecnológico Completo

### Backend Framework
- **Django 3.2.12** - Framework web principal
- **Python 3.x** - Lenguaje de programación base
- **WSGI Application** - Servidor de aplicaciones

### Base de Datos
- **PostgreSQL** - Base de datos principal
  - Database: `indicadores`
  - Usuario: `amiranda`
  - Host: `localhost:5432`
- **pgvector** - Extensión para búsqueda vectorial (embeddings)

### Inteligencia Artificial y ML
- **Cerebras Cloud SDK (1.50.1)** - LLM para chat
  - Modelo: `gpt-oss-120b`
  - Max tokens: 14,200
  - Temperature: 0.15
- **sentence-transformers (5.1.1)** - Generación de embeddings
  - Modelo: `all-MiniLM-L6-v2` (384 dimensiones)
- **transformers (4.56.2)** - Hugging Face transformers
- **torch (2.8.0+cpu)** - PyTorch para modelos ML
- **MoritzLaurer/mDeBERTa-v3-base-mnli-xnli** - Clasificación zero-shot

### Frontend
- **JavaScript vanilla** - Interactividad del cliente
- **Plotly (6.3.0)** - Visualización de gráficos interactivos
- **Leaflet** - Mapas interactivos (referenciado en código)
- **CKEditor 5** - Editor de texto enriquecido
- **Bootstrap/CSS** - Framework de UI

### Procesamiento de Datos
- **pandas (2.3.2)** - Manipulación de datos
- **numpy (2.2.6)** - Operaciones numéricas
- **scikit-learn (1.7.2)** - Machine learning
- **scipy (1.15.3)** - Computación científica

### Archivos Estáticos
- **WhiteNoise (6.11.0)** - Servir archivos estáticos
  - Storage: `CompressedManifestStaticFilesStorage`
  - Max age: 1 año en producción, 0 en desarrollo

### Sistema de Caché
- **Django Local Memory Cache** - Caché por defecto
  - Backend: `django.core.cache.backends.locmem.LocMemCache`
  - Location: `unique-snowflake`
- **Timeouts configurados:**
  - Page cache: 15 minutos
  - API cache: 30 minutos
  - Query cache: 60 minutos

### Utilidades y Herramientas
- **django-extensions (4.1)** - Comandos útiles de gestión
- **django-dbbackup (5.0.0)** - Respaldos de base de datos
- **humanize (4.13.0)** - Formateo de datos legibles
- **requests (2.32.5)** - HTTP client
- **psycopg2-binary (2.9.10)** - Adaptador PostgreSQL
- **python-dotenv (1.1.1)** - Variables de entorno
- **xmltodict (1.0.2)** - Procesamiento XML

### Text-to-Speech
- **TTS (0.13.3)** - Síntesis de voz

### Geoespacial
- **pyproj** - Transformaciones de coordenadas (importación opcional)
  - CRS por defecto: MAGNA_Cali_Valle_del_Cauca_2009

## Arquitectura de Software

### Patrón MTV (Model-Template-View)
```
┌─────────────────────────────────────────────┐
│              USUARIO / CLIENTE               │
└──────────────────┬──────────────────────────┘
                   │ HTTP Request
                   ▼
┌─────────────────────────────────────────────┐
│              URLs (myproject/urls.py)        │
│  - /admin/                                   │
│  - /chat/                                    │
│  - /dominios/                                │
│  - /api/                                     │
└──────────────────┬──────────────────────────┘
                   │ Routing
                   ▼
┌─────────────────────────────────────────────┐
│         MIDDLEWARE LAYER                     │
│  - SecurityMiddleware                        │
│  - WhiteNoiseMiddleware                      │
│  - SessionMiddleware                         │
│  - ChatRateLimitMiddleware (custom)          │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│         VIEWS (indicadores/views.py)         │
│  - 9,153 líneas de código                    │
│  - ~180 funciones/vistas                     │
│  - Lógica de negocio                         │
└──────────────────┬──────────────────────────┘
                   │ Queries
                   ▼
┌─────────────────────────────────────────────┐
│         MODELS (indicadores/models.py)       │
│  - 33+ modelos Django ORM                    │
│  - Relaciones complejas                      │
└──────────────────┬──────────────────────────┘
                   │ SQL
                   ▼
┌─────────────────────────────────────────────┐
│              PostgreSQL Database             │
│  + pgvector extension                        │
└─────────────────────────────────────────────┘
```

### Configuración de Aplicaciones Instaladas

```python
INSTALLED_APPS = [
    'django.contrib.admin',           # Panel administrativo
    'django.contrib.auth',            # Autenticación
    'django.contrib.contenttypes',    # Content types
    'django.contrib.sessions',        # Sesiones
    'django.contrib.messages',        # Mensajes
    'django.contrib.staticfiles',     # Archivos estáticos
    'django.contrib.humanize',        # Filtros humanize
    'django_ckeditor_5',              # Editor CKEditor 5
    'django_extensions',              # Extensiones Django
    'dbbackup',                       # Backups DB
    'whitenoise.runserver_nostatic',  # WhiteNoise
    'indicadores',                    # App principal
]
```

### Middleware Stack

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'indicadores.middleware.ChatRateLimitMiddleware',  # Custom
]
```

## Configuraciones Críticas

### Seguridad (⚠️ PROBLEMAS IDENTIFICADOS)

```python
# ❌ CRÍTICO: SECRET_KEY expuesta
SECRET_KEY = '***REMOVED***'

# ❌ CRÍTICO: DEBUG activado
DEBUG = True

# ❌ CRÍTICO: Credenciales de BD en texto plano
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'indicadores',
        'USER': 'amiranda',
        'PASSWORD': '***REMOVED***',  # ⚠️ Expuesta
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# ⚠️ ALLOWED_HOSTS muy restrictivo
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
```

### Logging

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        }
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'filename': 'logs/chat.log',
        },
        'tools_file': {
            'level': 'DEBUG',
            'filename': 'logs/tools.log',
        },
        'console': {
            'level': 'DEBUG',
        }
    },
    'loggers': {
        'indicadores': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
        },
        'indicadores.tools': {
            'handlers': ['tools_file', 'console'],
            'level': 'DEBUG',
        }
    }
}
```

### Configuración de Tokens (Chat)

```python
TOKENS_PER_CHAR = 0.25              # 1 token ≈ 4 caracteres
MAX_CONTEXT_TOKENS = 8000           # Límite total de contexto
MAX_HISTORY_TOKENS = 2000           # Límite para historial
```

### Internacionalización

```python
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True
```

## Dependencias Completas (142 paquetes)

### Core Django
- Django==3.2.12
- asgiref==3.9.2
- sqlparse==0.5.3

### Bases de Datos
- psycopg2-binary==2.9.10
- pgvector==0.4.1

### Machine Learning & AI
- cerebras_cloud_sdk==1.50.1
- sentence-transformers==5.1.1
- transformers==4.56.2
- torch==2.8.0+cpu
- scikit-learn==1.7.2
- scipy==1.15.3
- numpy==2.2.6

### Procesamiento de Datos
- pandas==2.3.2
- narwhals==2.5.0
- openpyxl (implícito para Excel)

### Editor y Contenido
- django-ckeditor==6.7.3
- django-ckeditor-5==0.2.18
- django-js-asset==3.1.2

### Utilidades
- humanize==4.13.0
- python-dotenv==1.1.1
- requests==2.32.5
- xmltodict==1.0.2

### Text-to-Speech
- TTS==0.13.3

### Backup
- django-dbbackup==5.0.0

### Servidor Estático
- whitenoise==6.11.0

### Desarrollo
- django-extensions==4.1
- pytest==8.4.2
- pytest-django==4.11.1

## Análisis de Versiones

### ⚠️ Versiones Desactualizadas

| Paquete | Versión Actual | Última Estable | Estado |
|---------|----------------|----------------|--------|
| Django | 3.2.12 | 4.2.x (LTS) | ⚠️ Antigua |
| certifi | 2020.6.20 | 2024.x | ⚠️ Muy antigua |
| requests | 2.32.5 | 2.32.x | ✅ Actualizada |
| numpy | 2.2.6 | 2.x | ✅ Actualizada |

### Recomendaciones de Actualización

1. **Django 3.2 → 4.2 LTS**
   - Mejoras de seguridad
   - Mejor rendimiento
   - Async views nativas

2. **Actualizar certifi**
   - Crítico para verificación SSL/TLS

3. **Revisar dependencias de sistema**
   - Muchas dependencias del sistema (ubuntu-drivers-common, etc.)
   - Considerar dockerizar la aplicación

## Conclusiones Técnicas

### ✅ Fortalezas
- Stack moderno y robusto
- Integración avanzada de IA
- Buena separación de responsabilidades
- Uso de pgvector para búsqueda semántica

### ❌ Debilidades
- Versión de Django no es la LTS más reciente
- Credenciales hardcodeadas
- DEBUG=True en configuración
- Sin containerización evidente
- Mezcla de dependencias del sistema

### 💡 Recomendaciones
1. Migrar a Django 4.2 LTS
2. Usar variables de entorno para todas las credenciales
3. Implementar diferentes settings por entorno (dev/prod)
4. Dockerizar la aplicación
5. Implementar CI/CD
