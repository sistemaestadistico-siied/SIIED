---
name: siied-api-abierta
description: >-
  Consulta la API abierta del SIIED (Sistema Integrado de Información
  Estadística Distrital de Santiago de Cali): indicadores, series
  estadísticas, conjuntos de datos (microdata), catálogos de consulta,
  estructura dominio-tema-subtema, geografía y metadatos. Usa esta skill
  cuando el usuario pregunte por datos estadísticos de Cali, busque
  indicadores del SIIED, o necesite consumir la API abierta del portal
  desde código o análisis.
license: Uso abierto — datos públicos del Distrito de Santiago de Cali.
metadata:
  portal: SIIED — Sistema Distrital de Información Estadística
  contacto: sistemaestadistico@cali.gov.co
---

# SIIED · API Abierta

## Qué es

API REST **abierta y gratuita** del catálogo estadístico del Distrito de
Santiago de Cali (Colombia). No requiere autenticación ni API key para
la consulta pública. Todas las respuestas son JSON; las desagregaciones
geográficas usan GeoJSON. El contenido del portal está en **español**:
responde siempre en el idioma del usuario.

## URL base

```
https://indicadores.cali.gov.co
```

Si el SIIED corre en otro host (entornos locales o réplicas), usa la URL
del portal que te indique el usuario — los endpoints son los mismos.

## Reglas de oro (evita errores)

1. **Primero explora, después consulta.** Nunca asumas el `id` de un
   indicador o conjunto: usa los endpoints de búsqueda/estructura y
   trabaja con los IDs reales que devuelven.
2. **Los indicadores enlazados al "catálogo de consulta" NO tienen
   series.** Si `get_graficos` o `get_desagregaciones` devuelven vacío
   para un indicador, su dato son las **filas del catálogo**: usa
   `api/catalogo-consulta/<pk>/`.
3. **Paginación:** los endpoints de filas usan `limit`/`offset`
   (máx. ~10.000). Para volcados completos itera con `offset`.
4. **No hay endpoints de escritura en la API abierta.** La carga de
   datos se hace por el módulo de recolección web o por MCP con token.
5. Si un endpoint 404 devuelve HTML, el `id` no existe o la ruta está
   mal escrita — no reintentes con el mismo id.

## Mapa de endpoints

### Descubrimiento y estructura

| Endpoint | Qué devuelve | Parámetros clave |
|---|---|---|
| `POST /api/buscar/` | Búsqueda semántica en todo el portal | body JSON `{"q": "…"}` |
| `GET /api/buscar_indicadores/` | Indicadores por texto | `q`, `limit` |
| `GET /api/get_dominios/` | Dominios de desagregación (sectores) | — |
| `GET /api/get_temas/` | Temas por dominio | `dominios` (IDs separados por coma) |
| `GET /api/get_subtemas/` | Subtemas (contienen los indicadores) | `temas` (IDs separados por coma) |
| `GET /api/get_indicadores/` | Indicadores filtrables | `subtemas` (IDs por coma), `q` |
| `GET /api/get_indicadores_simple/` | Lista ligera id+ nombre | `subtema_id` |
| `GET /api/indicador-metadata/` | Ficha técnica del indicador | `indicador_id` |

### Series y visualización (por `indicador_id`)

| Endpoint | Qué devuelve |
|---|---|
| `GET /api/get_graficos/<id>/` | Definiciones de gráficos configurados |
| `GET /api/get_desagregaciones/<id>/` | Desagregaciones + `catalogo_consulta` si aplica |
| `GET /api/get_mapa/<id>/` | Datos para mapa |
| `GET /api/geojson/indicador/<id>/` | GeoJSON del indicador |
| `GET /api/valores_geo/<id>/` | Valores por territorio/comuna |
| `GET /api/get_datos_indicadores/` | Series de varios indicadores (comparativo) |

### Conjuntos de datos (microdata / CSV)

| Endpoint | Qué devuelve | Parámetros clave |
|---|---|---|
| `GET /api/conjuntos-datos/list/` | Catálogo de conjuntos | — |
| `GET /api/conjuntos-datos/<id>/` | Detalle + variables | — |
| `GET /api/datasets/all/` | Todos los datasets | — |
| `GET /api/conjuntos-datos/datasets/` | Datasets filtrados | — |
| `GET /api/conjuntos-datos/datasets/hierarchical/` | Árbol dominio→tema→dataset | — |
| `GET /api/conjuntos-datos/rows/` | **Filas del CSV** | `file` (req.), `limit`, `offset`, `columns`, `anio_inicio`, `anio_fin`, `encoding` |
| `GET /api/conjuntos-datos/headers/` | Columnas del CSV | `file` (req.), `encoding` |
| `GET /api/ficha-tecnica-conjuntos-datos/<id>/` | Ficha técnica del conjunto | — |
| `GET /api/get_conjuntos-datos_csv/<id>/` | Descarga CSV por indicador | — |

### Catálogo de consulta (tablas de referencia)

| Endpoint | Qué devuelve | Parámetros clave |
|---|---|---|
| `GET /api/catalogo-consulta/` | Lista de catálogos activos | `dominio`, `tipo`, `q`, `incluir_filas` |
| `GET /api/catalogo-consulta/<pk>/` | Catálogo con filas paginadas | `q`, `pagina`, `page_size` (`'todas'` = todo) |

### Geografía

| Endpoint | Qué devuelve |
|---|---|
| `GET /api/get_niveles_geograficos/` | Niveles territoriales disponibles |
| `GET /api/get_capas_geograficas/` | Capas geográficas |

## Flujos típicos

### A. "¿Qué datos hay sobre X?"

1. `GET /api/buscar/?q=<tema>` o `buscar_indicadores` → obtén IDs.
2. `GET /api/indicador-metadata/?indicador_id=<id>` → ficha y contexto.
3. Si necesitas la serie: `get_desagregaciones`/`get_graficos` → si el
   indicador es de catálogo de consulta, pasa al flujo C.

### B. Trabajar un conjunto de datos

1. `conjuntos-datos/list/` → elige el conjunto, toma el valor `file`.
2. `conjuntos-datos/headers/?file=<file>` → columnas disponibles.
3. `conjuntos-datos/rows/?file=<file>&limit=100&offset=0` → filas;
   itera con `offset` hasta `total`.

### C. Indicador enlazado a catálogo de consulta

1. `get_desagregaciones/<id>/` → el payload incluye `catalogo_consulta`
   con `id`, columnas y `total_filas`.
2. `catalogo-consulta/<pk>/` → filas paginadas con `q`/`pagina`.

## Ejemplos concretos

```bash
# Buscar indicadores de empleo
curl "https://indicadores.cali.gov.co/api/buscar_indicadores/?q=empleo"

# Filas de un dataset (primeras 50)
curl "https://indicadores.cali.gov.co/api/conjuntos-datos/rows/?file=<FILE>.csv&limit=50"

# Filtrar por rango de años y elegir columnas
curl "…/rows/?file=<FILE>.csv&anio_inicio=2019&anio_fin=2023&columns=anio,comuna,valor"
```

## Formato de respuesta por endpoint

### Estructura dominio → tema → subtema

`get_dominios`, `get_temas`, `get_subtemas` → **array JSON plano**
(según el endpoint incluye `icono` o `dominio_id`/`tema_id`):

```json
[{"id": 1, "nombre": "Salud, Bienestar Social y Demografía", "icono": "fas fa-heartbeat"}]
```

Sin envoltura, sin paginación, sin `results` — el array llega directo.

### Indicadores

`buscar_indicadores` → objeto con envoltura `success`:

```json
{"success": true, "resultados": [
  {"id": 140, "nombre": "…", "codigo": "CEC_3_JyS_S_26",
   "similitud": 1.0,
   "dominio_slug": "economia", "dominio_nombre": "Economía",
   "tema_slug": "turismo", "tema_nombre": "Turismo",
   "subtema_slug": "…", "subtema_nombre": "…"}
]}
```

`get_indicadores_simple` → array plano `[{"id": 507, "nombre": "…"}]`.

`indicador-metadata` → `{"success": true, "metadata": {…}}` con la
ficha técnica: `Grupo_Indicador`, `Dominio`, `Tema`, `Subtema`,
`Codigo_Indicador`, `Nombre_Indicador`, `Sigla`, `Descripcion_Indicador`,
`Objetivo`, `Justificacion`, `Metodo_Medicion`, `Formula`, `Variables`,
`Unidad_Medida` (los campos pueden venir vacíos `\"\"`).

### Series y gráficos

`get_graficos/<id>/` → array de gráficos configurados:

```json
[{"id": 218, "nombre": "Gráfico - Abigeato", "tipo_grafico": "line",
  "series": [{"x": ["1987","1988",…], "y": ["16","10",…]}]}]
```

`x` e `y` llegan como **strings** — convierte a número antes de operar.

`get_desagregaciones/<id>/` → objeto:

```json
{"dominios": [], "desagregaciones_geograficas": [],
 "desagregaciones_tematicas": [],
 "rango_anios": {"min": 1987, "max": 2022,
   "min_disponible": 1987, "max_disponible": 2022}}
```

`get_datos_indicadores/` → comparativo paginado (`indicadores` = lista
de IDs por coma):

```json
{"datos": [{"Año": 1987, "Indicador": "Abigeato", "Valor": 16.0,
   "Desagregaciones Geográficas": "", "Desagregaciones Temáticas": ""}],
 "indicadores": [{"id": 1569, "nombre": "Abigeato",
   "unidad_medida": null, "catalogo_consulta_id": null}],
 "total": 35, "limit": 2, "offset": 0}
```

### Conjuntos de datos

`conjuntos-datos/list/` → `{"datasets": [{"file": "…csv", "label": "…", "size": 4214}]}`

`conjuntos-datos/headers/` → `{"file": "…", "columns": ["Año", "Ciudad", …]}`

`conjuntos-datos/rows/` →

```json
{"file": "…", "columns": ["Año", "Ciudad", "Nacimientos"],
 "rows": [{"Año": "1998", "Ciudad": "Cali", "Nacimientos": "35134"}],
 "total": 108, "limit": 2, "offset": 0}
```

Los valores de `rows` vienen como **strings** (CSV crudo); puede incluir
separadores de miles (`\"34.701\"`).

### Catálogo de consulta

`catalogo-consulta/` (lista) → array plano:

```json
[{"tipo": "catalogo_consulta", "id": 15, "nombre": "…",
  "descripcion": "…", "tipo_consulta": "capacidad",
  "tipo_display": "Inventario de capacidad instalada",
  "dominio": "…", "columnas": ["valor", "anio"], "total_filas": 36,
  "url": "/catalogo-consulta/15/", "url_api": "/api/catalogo-consulta/15/"}]
```

`catalogo-consulta/<pk>/` → el mismo objeto + `filas` + `paginacion`:

```json
{"…campos de la lista…", "indicadores_enlazados": [{"id": 1476, "nombre": "…"}],
 "filas": [{"valor": "…", "anio": "…"}],
 "paginacion": {"pagina": 1, "total_paginas": 1,
   "total_filas": 36, "page_size": 500}}
```

### Geografía

`get_niveles_geograficos/` → `[{"id": 1, "nombre": "Área Geográfica"}]`
`get_capas_geograficas/` → `[{"id": 7, "nombre": "Comuna 1", "nivel_geografico_id": 4}]`
`geojson/indicador/<id>/` → GeoJSON estándar (`FeatureCollection`).

### Reglas generales

- Errores: 404 si el recurso no existe; 400 ante parámetros faltantes
  (el mensaje indica cuál); 405 si usas GET en `/api/buscar/` (es POST).
- Los campos `nombre`, `descripcion` y la ficha técnica están en español.
- Arrays planos en endpoints de estructura; objetos con `total`/`limit`/
  `offset` en endpoints de filas paginadas.

## Soporte

Dudas sobre datos o acceso: **sistemaestadistico@cali.gov.co** —
también por la burbuja de chat del portal (esquina inferior derecha).
