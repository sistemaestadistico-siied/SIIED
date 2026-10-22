# Arquitectura de metadatos: OpenMetadata vs Metadata Editor (NADA)

> Estado: decisión de arquitectura acordada. Los conjuntos de metadatos del
> SIIED se catalogan en **OpenMetadata**; solo las **Operaciones
> Estadísticas** consolidadas se publican en **NADA** vía **Metadata Editor**.

## 1. Los dos softwares (no confundir)

| | **Metadata Editor** (IHSN / Banco Mundial) | **OpenMetadata** (Linux Foundation) |
|---|---|---|
| Repositorio local | `OPENMETADATA/` (nombre histórico engañoso) | Aún no desplegado |
| Qué es | Herramienta de **autoría** de metadatos estadísticos | Plataforma de **catálogo y gobierno de datos** sobre infraestructura viva |
| Estándares | DDI-Codebook, SDMX/MSD, Dublin Core, ISO 19139 | API propia (API-first), tags, glossary, lineage |
| Cómo funciona | Formularios + API REST; el humano escribe el metadato | **Conectores automáticos** a Postgres, Airflow, dbt, dashboards… |
| No hace | No se conecta a bases de datos, no descubre ni perfila | No habla DDI/SDMX; no es catálogo de publicación |
| Producto | Registro **publicable** en NADA (citable, idno/DOI) | Catálogo **operativo** continuo (linaje, calidad, ownership) |

## 2. División de trabajo

```
Camino A — Gobierno de datos (equipo de la Alcaldía)   Camino B — Metodológico (SIIED)
───────────────────────────────────────────────────    ────────────────────────────────────
Taller anual (DADII) → fuentes censadas                Fuentes → acompañamiento metodológico
        │                                                      │
        ▼                                                      ▼
Conexión e integración bronce → plata → gold           Fuente → Operación Estadística validada
        │                                                      │
        ▼                                                      ▼
   OPENMETADATA                                     METADATA EDITOR → NADA
   (catálogo vivo: linaje, calidad,                  (DDI publicado, citable —
    certificación Bronze/Silver/Gold)                 evento editorial, no proceso)
```

Las dos vías corren en paralelo **a distinta velocidad por fuente**: una
fuente puede alcanzar gold de *integración* sin estar lista para
*publicación* como OE. Nada llega a NADA sin madurar antes en el catálogo.

## 3. Mapa de conjuntos SIIED → entidad OpenMetadata

| Activo SIIED | Entidad OpenMetadata | Notas |
|---|---|---|
| Fuentes del taller (bronce) | Assets via REST API | Push desde el taller |
| Bases del datalake (plata/gold) | Tables (conector Postgres) | Ingesta automática |
| `CampoCatalogo` | Columns + tags | Descripciones por columna |
| Capa bronce/plata/gold | **Certifications** (nativas: Bronze/Silver/Gold) | Encaje literal |
| Categorías temáticas | Glossary terms / Tags | Registro, Identificación… |
| Dominios SIIED | **Domains** | Entidad nativa |
| `ConjuntoDatos` | **Data Products** | Activos agrupados por dominio |
| Relaciones fuente→base (grafo 3D) | **Lineage** | Automático vía pipelines |
| `Indicador` | Chart/Dashboard o Data Product | Sin entidad estadística nativa* |
| Organismos | Teams / Owners | Gobierno |
| Calidad de datos | Profiler + Data Quality tests | Nativo |

\* Los indicadores no tienen entidad estadística nativa en OpenMetadata:
se registran como activos de consumo (chart/data product) con metadato
mínimo; el rigor metodológico SDMX se conserva en el SIIED y solo iría a
NADA (tipo `indicator`/MSD) si algún día se publica externamente.

## 4. Qué queda en el Metadata Editor / NADA

- **Solo `OperacionEstadistica`** (tipo `microdata`, DDI-Codebook).
- Dirección principal: **pull** — el inventario SIIED se alimenta de las
  OEs reales en ADDA/NADA (importador existente).
- Push solo cuando una OE del ciclo taller→gold quede lista para su DDI;
  nunca skeletons que pisen los DDI reales (esa fue la razón original de
  desactivar el set `operaciones` en `sync_om`).
- Los sets `conjuntos`, `indicadores` y `fuentes` quedaron **retirados**
  del sync: son activos del catálogo vivo (OpenMetadata), no registros de
  publicación.

## 5. Integración técnica prevista

- OpenMetadata es API-first; la ingesta corre sobre Airflow
  (`openmetadata-ingestion`). Patrón: pipeline Airflow → API abierta del
  SIIED → creación/actualización de entidades (tables, tags, glossary,
  domains, data products, certifications).
- El catálogo unificado de variables del taller
  (`catalogo_variables_ecosistema`, `_norm_var`, capas) es la **capa de
  gobierno previa**; su rol a futuro lo absorbe OpenMetadata.
- Referencia en código: `indicadores/om_sync.py` (serializadores),
  `indicadores/management/commands/sync_om.py` (sync restringida).
