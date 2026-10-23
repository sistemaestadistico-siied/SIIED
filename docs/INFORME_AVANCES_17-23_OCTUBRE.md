# Informe de avances de desarrollo — SIIED

**Periodo:** sábado 17 → viernes 23 de octubre de 2026
**Proyecto:** Sistema Integrado de Información Estadística Distrital (SIIED)
**Repositorio:** [sistemaestadistico-siied/SIIED](https://github.com/sistemaestadistico-siied/SIIED)
**Alcance:** commits [`635d1bd`](https://github.com/sistemaestadistico-siied/SIIED/commit/635d1bd) → [`faa1b2f`](https://github.com/sistemaestadistico-siied/SIIED/commit/faa1b2f) (7 commits)

---

## 1. Resumen ejecutivo

Semana de consolidación de la plataforma como **ecosistema abierto de datos**: se
entregó el servidor MCP completo (puerta de entrada para clientes de IA), el módulo
de analítica BI sobre Apache Superset con tableros embebibles por nivel de
visibilidad, el catálogo de variables con sincronización a OpenMetadata, la
licencia pública GPLv3 y la reconexión de **Sistemas de Consulta** al módulo
Editorial con un nuevo estilo de directorio plano.

## 2. Métricas del periodo

| Métrica | Valor |
|---|---|
| Commits | 7 |
| Archivos tocados (commiteado) | ~185 |
| Líneas añadidas / eliminadas (commiteado) | +21 545 / −2 588 |
| Commits del viernes 23 | `faa1b2f` — 34 archivos, +3 migraciones |
| Herramientas expuestas por MCP | 17 |
| Rutas nuevas de analítica/BI | 9 |
| Ítems nuevos en Sistemas de Consulta | 18 (3 categorías) |
| `manage.py check` | 0 issues |

## 3. Avances por día

### Sábado 17 — Navegación y acceso

[`635d1bd`](https://github.com/sistemaestadistico-siied/SIIED/commit/635d1bd) · 9 archivos · +396/−19

- Cuatro páginas de acceso directo en la navegación (Herramientas, Instrumentos,
  Conectividad, Sistemas).
- Lógica de ocultamiento: indicadores, subtemas y catálogos **sin datos ya no se
  muestran** — la navegación solo expone lo que tiene contenido real.

### Domingo 18 — Analítica + MCP (día más productivo)

[`6412351`](https://github.com/sistemaestadistico-siied/SIIED/commit/6412351) · 64 archivos · +7 705/−1 905 — **Módulo de Analítica completo**

- Integración con Apache Superset: servicio `superset_service.py`, listado de
  dashboards, creación, subida de CSV, exploración y detalle.
- Taller de gestión de datos **granular**: retos, organismos y fuentes como
  entidades separadas, con validación.
- Chat HTMX: conversación en línea dentro del módulo.

[`8ec7c61`](https://github.com/sistemaestadistico-siied/SIIED/commit/8ec7c61) · 48 archivos · +3 887/−479 — **Servidor MCP completo**

- `mcp_server.py`: transporte **stdio y HTTP**, listo para Claude Desktop,
  VS Code y cualquier cliente MCP.
- **17 herramientas** de solo lectura sobre los datos abiertos: indicadores
  (búsqueda, ficha, matrices, comparativo), estructura dominios→temas→subtemas,
  conjuntos de datos, catálogo de consulta, sistemas de información, operaciones
  estadísticas, ecosistema por organismo, productos académicos, documentos de
  infraestructura, satisfacción, ICED/FICED.
- Modelos `MCPApiToken` y `MCPAuditLog`: acceso por token con trazabilidad.
- Página instructivo `/mcp-instructivo/` con guía de conexión por cliente.
- ICED/FICED: cobertura de periodos 2018–2023; módulo de visitas.

### Jueves 22 — BI embebible + catálogo + licencia

[`4de31d2`](https://github.com/sistemaestadistico-siied/SIIED/commit/4de31d2) · 15 archivos · +3 349/−121 — **Rebranding analítica**

- **SIIED BI** y **Don Datico BI**: identidad propia sobre Superset
  (plantillas, marca, pantallas dedicadas).

[`318fe7e`](https://github.com/sistemaestadistico-siied/SIIED/commit/318fe7e) · 48 archivos · +5 534/−64 — **Catálogo de variables + OpenMetadata**

- Catálogo de variables navegable.
- Sincronización con **OpenMetadata** (fuente de verdad de metadatos).
- Ajustes varios de UI.

[`e78259f`](https://github.com/sistemaestadistico-siied/SIIED/commit/e78259f) · +674 — **Licencia GPLv3**

- Oferta pública del código: el SIIED queda como proyecto **open source**.

### Viernes 23 — Sistemas de Consulta editorial + BI por visibilidad

[`faa1b2f`](https://github.com/sistemaestadistico-siied/SIIED/commit/faa1b2f) · 34 archivos · +1 177/−491

- **Sistemas de Consulta reconectado a Editorial.** Respaldado el histórico en
  `evidencias/respaldo_sistemas_consulta_editorial.txt` (8 categorías / 48 ítems
  con URLs, iconos y orden), reemplazado por **3 categorías con 18 ítems**
  derivados del home. La vista vuelve a leer `CategoriaInformacion` /
  `SistemaInformacion` y el template renderiza el directorio plano estilo INEGI
  desde esos datos — ya no hay contenido quemado en HTML.
- **Renombre en todo el módulo Editorial**: "Sistemas de Información" →
  "Sistemas de Consulta" (sidebar, dashboard, listado, formularios, manual,
  strings de vistas y docstrings).
- **Home reorganizado**: Libro Digital 3D movido a Herramientas; sección de
  Conectividad reparada (bloque malformado); navegación consolidada en un solo
  enlace a Sistemas de Consulta; eliminadas las 3 páginas standalone redundantes.
- **Tableros BI por visibilidad** (`TableroBI`, `DatasetBI` — migraciones
  0130–0132): `bi/<id>/` emite **guest tokens** de Superset según nivel
  público/autenticado/organismo/interno; SDK `superset-embedded-sdk.js`
  vendorizado; `docs/MANUAL_DESPLIEGUE_SUPERSET.md` (Superset 6.1.0, venv en
  `/opt/superset`, rebrand versionable).

## 4. Avances por eje

| Eje | Entregado |
|---|---|
| **Acceso abierto / IA** | Servidor MCP stdio+HTTP con 17 tools, tokens con auditoría, instructivo de clientes; Don Datico con ecosistema por organismo; skill de API abierta |
| **Analítica / BI** | Módulo Superset completo; SIIED BI y Don Datico BI con marca propia; embed con guest tokens por visibilidad; manual de despliegue |
| **Metadatos** | Catálogo de variables; sync OpenMetadata; auditorías de dominios y listas FICED |
| **Portal / navegación** | Ocultamiento de nodos sin datos; Sistemas de Consulta como directorio plano editorial; home reorganizado |
| **Editorial** | Catálogo "Sistemas de Consulta" operativo de punta a punta (18 ítems, iconos, orden, target, tooltip) |
| **Datos / gobernanza** | ICED/FICED p18–23; taller granular (retos/organismos/fuentes); módulo de visitas |
| **Legal / despliegue** | GPLv3; manual operativo de Superset |

## 5. Estado actual

- Trabajo del viernes ya en `main` ([`faa1b2f`](https://github.com/sistemaestadistico-siied/SIIED/commit/faa1b2f)).
- `/sistemas-informacion/` → 200, 3 bloques de categoría, 18 enlaces, URLs
  internas verificadas vía `reverse`.
- `manage.py check` → sin issues.
- Sin residuos de la nomenclatura anterior en Editorial.

## 6. Pantallazos sugeridos para anexar

1. Home con las tres secciones de acceso (Herramientas / Instrumentos / Conectividad).
2. `/sistemas-informacion/` — directorio plano con las 3 categorías.
3. Dashboard de Editorial mostrando la card **Sistemas de Consulta** y el listado.
4. `/analitica/superset/` — SIIED BI con un tablero embebido (guest token).
5. `/mcp-instructivo/` — guía de clientes MCP.
6. Catálogo de variables.

## 7. Próximos pasos naturales

- Publicar la oferta open source (repo público bajo GPLv3).
- Publicar el instructivo MCP a clientes externos.
