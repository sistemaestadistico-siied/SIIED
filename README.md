# SIIED — Sistema Integrado de Información Estadística Distrital

**Plataforma estadística del Distrito de Santiago de Cali** — publicación, consulta y visualización de indicadores, conjuntos de datos y documentación técnica de la Alcaldía.

Desarrollada por el equipo de estadística del Departamento Administrativo de Planeación. En producción: [indicadores.cali.gov.co](https://indicadores.cali.gov.co)

---

## Módulos principales

| Módulo | Descripción |
|---|---|
| **Catálogo estadístico** | Navegación jerárquica dominios → temas → subtemas → indicadores, con gráficos Plotly, mapas georreferenciados y fichas técnicas |
| **Don Datico** 🦜 | Asistente de chat con IA (LLM principal vía endpoint OpenAI-compatible + respaldo Cerebras) que consulta la plataforma mediante tools: búsqueda de indicadores, comparativos, ICED, ecosistema de datos, documentos |
| **Consulta y Tableros** (`/laboratorio/`) | Explorador de conjuntos de datos y constructor de tableros con gráficos, mapas y KPIs — integración con **Apache Superset** |
| **Catálogo de consulta** | Directorios y listados de referencia (instituciones, establecimientos, nomencladores) con búsqueda y descarga |
| **Sistemas y Proyectos de información** | Directorio de visualizadores, geovisores, observatorios y plataformas sectoriales del Distrito |
| **Infraestructura de información** | Repositorio documental navegable: normas, metodologías, guías y procesos estadísticos |
| **Inventario de operaciones** | Registro de operaciones estadísticas (OOEE) con enlaces ADDA/AMDA |
| **Dominios 3D / Visor comparativo** | Visualizaciones inmersivas y comparación entre indicadores |
| **Backoffice** | Wizard de creación de indicadores, recolección de datos, flujos de validación, gestión editorial y panel de configuración del chat |

## Stack

- **Backend**: Python 3.12 · Django 3.2 · PostgreSQL (+ pgvector para búsqueda semántica)
- **Visualización**: Plotly · Leaflet · TailwindCSS · Swiper
- **IA**: OpenAI SDK (Gemini/OpenAI-compatible + Cerebras) · sentence-transformers · transformers (clasificación zero-shot)
- **Analítica embebida**: Apache Superset
- **Otros**: WhiteNoise · django-ckeditor-5 · django-dbbackup · pandas/openpyxl

## Instalación (desarrollo)

```bash
git clone https://github.com/AMIRANDA9112/SIIED.git
cd SIIED

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # base
pip install -r requirements-ml.txt       # IA/embeddings (opcional pero recomendado)

cp .env.example .env                     # completar valores
python manage.py migrate
python manage.py collectstatic
python manage.py createsuperuser
python manage.py runserver
```

> En producción usar `requirements-production.txt` y `.env` basado en `.env.production.example`.

## Variables de entorno

Los secretos viven en `.env` (no versionado). Ver [`.env.example`](.env.example) para la lista completa:

| Grupo | Variables |
|---|---|
| Django | `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `FORCE_SCRIPT_NAME` |
| Base de datos | `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` |
| Email/Brevo | `BREVO_API_KEY`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `SITE_URL` |
| Superset | `SUPERSET_BASE_URL`, `SUPERSET_PUBLIC_URL`, `SUPERSET_ADMIN_USERNAME`, `SUPERSET_ADMIN_PASSWORD`, `SUPERSET_SHARED_PASSWORD` |
| Chat IA | `CEREBRAS_API_KEY`, `CEREBRAS_BASE_URL`, `CEREBRAS_MODEL`, `OLLAMA_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |

## API

Endpoints JSON públicos bajo `/api/`:

```
/api/get_dominios/              → dominios
/api/get_temas/                 → temas
/api/get_subtemas/              → subtemas
/api/get_indicadores/           → indicadores
/api/get_graficos/<id>/         → configuraciones de gráficos
/api/get_mapa/<id>/             → datos de mapa
/api/geojson/indicador/<id>/    → geometrías GeoJSON
/api/conjuntos-datos/list/      → conjuntos de datos
/api/conjuntos-datos/rows/      → filas de un conjunto
/api/valores_geo/<id>/          → valores georreferenciados
/api/get_unified_data/<id>/     → datos unificados de indicador
```

## Estructura

```
myproject/            # Configuración Django (settings.py lee .env)
indicadores/          # App principal
├── models.py         # Dominios, temas, indicadores, conjuntos, ICED…
├── views*.py         # vistas, chat, laboratorio, editorial, recolección,
│                     # validación, delegados, reportes
├── chat_config.py    # Configuración de Don Datico (contextos, límites)
├── tools*.py         # Tools disponibles para el LLM
├── templates/        # Plantillas (Tailwind + componentes compartidos)
└── static/           # CSS, imágenes, JS
docs/                 # Documentación técnica e insumos de importación
requirements*.txt     # base / dev / ml / production
```

## Seguridad

- Todas las credenciales se leen de variables de entorno — nunca del código.
- `DEBUG=False`, cookies seguras y `FORCE_SCRIPT_NAME` para proxy reverso en producción.
- Rate limiting en el chat (`ChatRateLimitMiddleware`) y tracking de visitas.

---

*Departamento Administrativo de Planeación — Alcaldía de Santiago de Cali*
