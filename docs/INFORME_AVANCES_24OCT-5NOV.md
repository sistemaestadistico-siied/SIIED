# Informe de avances de desarrollo — SIIED

**Periodo:** viernes 24 de octubre → miércoles 5 de noviembre de 2026
**Proyecto:** Sistema Integrado de Información Estadística Distrital (SIIED)
**Repositorio:** [sistemaestadistico-siied/SIIED](https://github.com/sistemaestadistico-siied/SIIED)
**Alcance:** commits [`c6b67f8`](https://github.com/sistemaestadistico-siied/SIIED/commit/c6b67f8) → [`ebe07bb`](https://github.com/sistemaestadistico-siied/SIIED/commit/ebe07bb) (6 commits funcionales)

---

## 1. Resumen ejecutivo

Periodo centrado en **madurar dos frentes de producción**: la georreferenciación
de la analítica y el ciclo de validación del FICED.

- **Geo + SIIED BI**: los mapas de toda la plataforma adoptan la escala
  coroplética institucional unificada; los polígonos WKT se materializan como
  GeoJSON servible (JOINs en datasets virtuales de Superset / choropleth
  deck.gl) y cada tablero puede descargar sus capas geográficas por nivel en
  Excel o CSV.
- **FICED — validación en dos etapas**: se rediseñó el flujo completo. El
  validador del organismo revisa y concilia las respuestas de sus equipos **sin
  ver puntajes** y deja el formulario en `prevalidado`; el equipo SIIED edita el
  consolidado, ve puntajes y toma la decisión final. La cifra de resultado solo
  se publica al organismo cuando el formulario queda `validado`.
- **Calidad de datos y UX**: eliminado el campo muerto `formula_ficha`, el
  wizard admite columnas con comas en el nombre (separador `;`), la tabla de
  operaciones estadísticas del FICED deja de truncarse y el catálogo de
  datasets de SIIED BI ahora agrupa sus 7 categorías en secciones plegables.
- **5 de noviembre — QA de diligenciamiento FICED y trazabilidad**: ronda de
  8 correcciones sobre el formulario (widgets, validaciones condicionales y
  textos), nuevo histórico de respuestas por pregunta que Don Datico cita
  como evidencia verificable, y rediseño visual del módulo público ICED y de
  la hoja de vida de los organismos.

## 2. Métricas del periodo

| Métrica | Valor |
|---|---|
| Commits funcionales | 6 |
| Archivos tocados | ~250 |
| Líneas añadidas / eliminadas | +10 857 / −4 433 |
| Migraciones nuevas | 2 (0134 quita `formula_ficha`; 0135 pre-validación FICED) |
| Preguntas documentadas en manual FICED | 42 |
| Métodos nuevos de API Superset (charts) | 4 |
| `manage.py check` | 0 issues |

## 3. Avances por día

### Jueves 23 (cierre) — Capa Apple Design

[`c6b67f8`](https://github.com/sistemaestadistico-siied/SIIED/commit/c6b67f8) · 55 archivos · +291/−137

- Feedback `:active` en elementos interactivos, `transition` restringida a
  propiedades del compositor (sin reflow), `prefers-reduced-motion` global.
- Navegación translúcida y tracking tipográfico — auditoría CSS aplicada a
  templates de todos los módulos.

### Lunes 27 — Geo para Superset

[`4a11d67`](https://github.com/sistemaestadistico-siied/SIIED/commit/4a11d67) · 161 archivos · +4 363/−2 594

- **Escala coroplética SIIED centralizada** (`window.SIIED_COLORSCALE` en
  `base.html`): mínimo `#9fc9ea` visible sobre fondo blanco; reemplaza
  literales duplicados en `subtema_detalle`, `producto_academico` y laboratorio.

[`9800eff`](https://github.com/sistemaestadistico-siied/SIIED/commit/9800eff) · 6 archivos · +339/−123

- Modelo **`CapaGeoJSON`** + comando `export_geojson_superset`: materializa
  `ElementoGeo.geom_wkt` → GeoJSON para JOIN en datasets virtuales de Superset
  (choropleth deck.gl). Utilidad `wkt_to_geo` extraída a `utils_geo.wkt_to_geojson`.

[`545cd46`](https://github.com/sistemaestadistico-siied/SIIED/commit/545cd46) · 4 archivos · +246/−1

- **Descarga de capas geográficas por nivel** (Excel/CSV) desde tableros:
  vistas `analitica_geo_descargas`/`geo_exportar`, botón en la navegación.
  XLSX omite geometrías geojson >32k celdas con flag `geojson_excede`;
  el CSV siempre exporta completo.

### Miércoles 5 de noviembre — FICED en dos etapas + limpieza de datos

[`d42183a`](https://github.com/sistemaestadistico-siied/SIIED/commit/d42183a) · 54 archivos · +2 872/−520

**FICED — reforma del flujo de validación**

- Nuevo estado `prevalidado` con auditoría (`prevalidado_por`,
  `fecha_prevalidacion`) — migración 0135.
- **Validador del organismo**: revisa las respuestas de los equipos técnicos,
  concilia divergencias y pre-valida — sin acceso a puntajes ni aprobación.
- **Validador SIIED**: edita el consolidado enviado o pre-validado desde el
  wizard (autosave habilitado sin cambiar estado), ve puntajes y decide
  aprobar/rechazar — ya no hay devolución al organismo.
- **Conciliación**: selección múltiple se une entre equipos; selección única
  elige un equipo ganador. Las tarjetas separan campos de decisión vs.
  complementarios, con criterio de consolidación y opciones numeradas.
- **Colas por rol** en el dashboard de validación; puntajes ocultos al
  validador del organismo en `revisar_iced.html`.
- **Productos de cumplimiento imprimibles**: organismo (desde pre-validación,
  sin puntaje) y SIIED (desde validado, con puntaje).
- `iced_resultado` solo expone puntajes cuando `estado='validado'`.
- Subrol FICED derivado del username; el landing oculta "iniciar otro
  formulario" cuando el usuario ya tiene el suyo del período.
- Fix truncado tabla OOEE (P23): `min-width` por tipo de columna + scroll-x.

**Analítica / SIIED BI**

- `superset_service`: `charts_de_dashboard`, `charts_de_dataset`,
  `chart_en_dashboard`, `eliminar_chart` — el admin elimina el activo en
  Superset al borrar `TableroBI`/dataset.
- Selector de visibilidad del tablero en Don Datico; `superset_embed_bare.html`
  para embebidos sin chrome.
- Catálogo de datasets: 7 categorías plegables (`<details>`) con contador; el
  filtro despliega automáticamente la categoría del resultado.

**Datos y calidad**

- Eliminado `Indicador.formula_ficha` de modelo, formularios de metadata
  (delegado + recolección), `om_sync`, embeddings y esquemas LLM — migración 0134.
- Wizard: `columnas_fuente` con separador `;` (soporta columnas cuyo nombre
  contiene comas, p. ej. encabezados con nombre de organismo); split con
  compatibilidad hacia `,` en valores previos. Corregido bug latente: el
  diagnóstico de recolección recibía el texto crudo en vez de la lista.
- `utils_geo.wkt_to_geo` + comando `reproyectar_geom_wkt`; `planeación.png`
  recortado (306→178 KB).

**Documentación**

- Manuales HTML actualizados: delegado (post-envío FICED) y validación (colas
  por rol, dos etapas, productos).
- Nuevo `docs/MANUAL_DILIGENCIAMIENTO_FICED.md`: guía de diligenciamiento por
  módulos y preguntas P1–P42 con instructivos, tipos de respuesta, campos
  condicionales, conciliación y roles.

**5 de noviembre — QA de diligenciamiento, evidencia y rediseño**

*FICED (8 correcciones)*

- P23: «Acciones de fortalecimiento» pasa de texto libre a select Sí/No/NA,
  alineado con las respuestas ya importadas.
- P30: se retira la columna de descripción editable; el widget deriva el
  texto de la opción MOP seleccionada (`campo_derivado`).
- URLs múltiples: control «+» para agregar/quitar enlaces por celda, persistidos
  con separador `;` (validación acepta `,` y `;`).
- P9: `help_text` placeholder («Misma estructura que P8») reemplazado por la
  instrucción real del instrumento.
- «Pregunta compartida»: los campos de respuestas de otros equipos se ordenan
  por posición de declaración en el wizard (la pregunta principal antes que
  sus sub-campos), no por orden de inserción del JSON.
- P25: el banner informativo readonly (`p25_proyectos_bp_link`) ya no se
  valida como URL — regla explícita `texto` en `REGLAS_CAMPOS_FICED`.
- Campos condicionales `data-show-if`: cuando la condición no se cumple se
  descarta el valor y no se valida (antes un valor «stale» en un campo
  oculto bloqueaba el avance del paso, p. ej. al desmarcar «proyectos»).
- Confirmación post-envío con dos botones: volver al módulo delegado e ir al
  módulo ICED.

*Don Datico FICED y evidencia verificable*

- El chat solo consulta formularios de años anteriores con contenido real
  (`validado`, `enviado`, `prevalidado`, `devuelto`), prefiriendo el
  consolidado del organismo o el del propio equipo del delegado.
- Nueva vista `/iced/historico/`: respuestas por pregunta × período con
  filtros `?q=N` y `?modulo=x`, etiquetas reales del instrumento y badges de
  estado. El chat la referencia con el enlace exacto de la pregunta para que
  el delegado verifique la evidencia citada (URLs linkificadas en `mdToHtml`).

*Rediseño visual y privacidad*

- `/iced/modulo/` y la hoja de vida `/hall-capacidad/<codigo>/` rediseñadas
  con el sistema visual limpio (fuente de sistema, superficie clara, segmented
  tabs, pills de período, badges semánticos).
- Corrección de puntajes ICED: el modelo los guarda en escala 0–1 y la hoja
  de vida los renderizaba crudos — donut y barras salían vacíos. La vista
  expone ahora `ficed_pct`/`ficed_hist_pct` en porcentaje.
- Correcciones de métricas: «fuentes con origen declarado» ya no muestra
  `densidad_red`; `total_indicadores` cuenta el total real (antes cortado a 10).
- Privacidad en página pública: se retiran nombres de inscritos al taller y
  del usuario diligenciante del FICED.
- Reparado `})` huérfano en `views.documentacion` (SyntaxError que tumbaba el
  servidor de desarrollo) y nombre correcto de la dependencia en el login
  delegado («Departamento Administrativo de Planeación»).
- Cierre de sesión universal `/logout/` (`auth_logout_global`): item «Cerrar
  sesión» en el navbar global visible solo con sesión activa — queda expuesto
  en acceso a módulos, todo el módulo ICED, histórico y demás páginas que
  extienden `base.html`.

*Carga de datos FICED*

- `importar_ficed_2024` y `seed_iced_mop`: importados los 27 organismos del
  FICED 2024 y 2025 con 472 filas de RRHH; DACDI reclasificada a «Instrucción».

## 4. Avances por eje

| Eje | Entregable |
|---|---|
| FICED | Validación organismo→SIIED en dos etapas, conciliación por equipos, productos de cumplimiento |
| FICED — QA | 8 correcciones de diligenciamiento, condicionales que no bloquean, histórico verificable por el chat |
| Geo | GeoJSON materializado, descarga de capas por nivel, escala coroplética unificada |
| Analítica/BI | Ciclo de vida de charts sincronizado con el admin; datasets plegables; embed bare |
| Datos | `formula_ficha` retirado de todo el pipeline; `columnas_fuente` tolera comas en nombres |
| UX | Acordeones con contadores, tabla P23 con scroll horizontal, manuales al día; rediseño limpio de módulo ICED público y hoja de vida de organismos |

## 5. Estado actual

- `main` sincronizado con `origin/main` (`ebe07bb`) — todo el trabajo pendiente empujado.
- Migraciones 0134 y 0135 generadas; **pendiente aplicarlas en producción**.
- `manage.py check`: 0 issues.

## 6. Pantallazos sugeridos para anexar

- Dashboard de validación mostrando la cola ICED con el botón correspondiente al rol.
- Pantalla de conciliación con campos de decisión vs. complementarios.
- Producto de cumplimiento del organismo (sin puntaje) y el de SIIED (con puntaje).
- Catálogo de datasets de SIIED BI con categorías plegadas.
- Tabla P23 del FICED con scroll horizontal.

## 7. Próximos pasos naturales

- Aplicar migraciones 0134/0135 en producción y validar el flujo FICED de extremo a extremo con datos reales.
- Verificar la publicación del enlace público de Superset sin login (`SUPERSET_PUBLIC_URL`, dominios permitidos del SDK embebido) y poner `TableroBI.visibilidad='publico'`.
- Comunicar a los organismos el nuevo separador `;` en `columnas_fuente` del wizard.
- Rotación de secretos y verificación del fix del logo del navbar.
