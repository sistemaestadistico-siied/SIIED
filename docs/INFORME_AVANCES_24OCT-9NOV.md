# Informe de avances de desarrollo — SIIED

**Periodo:** viernes 24 de octubre → domingo 9 de noviembre de 2026
**Proyecto:** Sistema Integrado de Información Estadística Distrital (SIIED)
**Repositorio:** [sistemaestadistico-siied/SIIED](https://github.com/sistemaestadistico-siied/SIIED)
**Alcance:** commits [`c6b67f8`](https://github.com/sistemaestadistico-siied/SIIED/commit/c6b67f8) → [`07b43bb`](https://github.com/sistemaestadistico-siied/SIIED/commit/07b43bb) (75 commits funcionales)

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
- **5 de noviembre (tarde) — FICED operativo en producción**: con los FICED
  2024 y 2025 cargados en el servidor se verificó el circuito completo de
  consulta y se resolvieron los problemas que impedían explotar los datos:
  los resultados de formularios importados ya abren, la evidencia que cita
  el asistente es legible, la navegación del delegado es coherente y los
  resultados validados quedaron consultables por todo el organismo.
- **6–7 de noviembre — plataforma de datos vivos**: «Subir datos» crece a
  Excel/TSV, Google Sheets públicos y conexiones a bases de datos externas
  como datasets vivos de Superset; correcciones de gestión de usuarios y
  roles, y auditoría de credenciales (DROP por `database_id`).
- **8–9 de noviembre — FICED: flujo real con devoluciones en cadena**: el
  rechazo terminal desaparece — el formulario puede devolverse en cada
  escalón con correos automáticos con marca institucional; auditoría de
  conciliación y cálculo de puntajes (multi-equipo), y la guía de
  diligenciamiento llega a v003 trazada al flujo real.

## 2. Métricas del periodo

| Métrica | Valor |
|---|---|
| Commits funcionales | 75 |
| Archivos tocados | 257 |
| Líneas añadidas / eliminadas | +15 381 / −4 911 |
| Migraciones nuevas | 2 (0134 quita `formula_ficha`; 0135 pre-validación FICED) |
| Preguntas documentadas en guía FICED | 42 (v003, trazada al flujo real) |
| Métodos nuevos de API Superset | 4 (charts) + conexiones BD/datasets vivos |
| Correos automáticos del flujo FICED | 5 escalones notificados |
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
- Hoja de vida — auditoría de métricas: «Orígenes externos» contaba **filas**
  `FuenteOrigen` (una misma entidad repetida por cada fuente) y clasificaba
  interno/externo con `nombre.split()[0]` (para DAP = «Departamento»,
  cualquier productor con esa palabra entraba como interno). Ahora cuenta
  **productores distintos normalizados** (sin tildes, comparación con nombre
  completo/nombre_menu/código) y la UI muestra sus nombres — el número es
  verificable. Pills de flujos usan totales reales (antes el largo de la
  lista cortada a 10); indicadores muestran «N a cargo · mostrando M».
- Logo de `/hall-capacidad/`: imagen remota i.ibb.co → `logo_hoja_vida.png`
  local (el del card del home).
- P19 «Pregunta compartida»: la tabla RRHH de otros equipos desbordaba la
  caja — el grid padre estiraba al ancho de la tabla (`min-width:auto`),
  neutralizando el `overflow-x` interno. Fix: `min-width:0` + scroll propio
  en el item. Celdas con listas se formatean `DN, D, C` (antes repr Python
  `['DN','D','C']`).
- Tarjeta «Indicadores y Operaciones»: deja de ser una pared plana de filas —
  se agrupa por operación estadística con encabezado y conteo, cada fila es
  enlace directo a la ficha del indicador (`conjunto_datos_detalle`) con
  chevrón y hover, y el subtítulo muestra «N a cargo · mostrando M».

*Carga de datos FICED*

- `importar_ficed_2024` y `seed_iced_mop`: importados los 27 organismos del
  FICED 2024 y 2025 con 472 filas de RRHH; DACDI reclasificada a «Instrucción».

**5 de noviembre (tarde) — el FICED ya funciona de extremo a extremo en producción**

Cargados los formularios en el servidor se recorrió el circuito completo
como lo vive el delegado —abrir el módulo, consultar resultados, verificar
evidencia— y se resolvieron los cinco problemas que lo bloqueaban:

- **Quedaron cargados los organismos que habían quedado por fuera**.
  Algunos archivos no podían identificarse por nombre: DACDI aparece como
  dos dependencias distintas y tres formularios venían con la celda de
  identificación vacía. El importador ahora acepta indicar el organismo por
  su ID, lo que permitió resolver manualmente esos casos y completar la
  cobertura ([`ff4598d`](https://github.com/sistemaestadistico-siied/SIIED/commit/ff4598d)).
- **Los resultados de los FICED importados ya se pueden consultar.**
  «Ver resultado» fallaba con un error interno en todos los formularios
  traídos de años anteriores (estos registros no tienen usuario
  diligenciante asociado). Corregido el detalle de la ficha; los 54
  resultados validados consultan sin error
  ([`e72824a`](https://github.com/sistemaestadistico-siied/SIIED/commit/e72824a)).
- **La evidencia que cita el asistente ahora es legible y real.**
  El histórico mostraba las respuestas como texto técnico crudo (JSON) y,
  al no interpretarlas, el asistente llegaba a reportar «sin registros» en
  preguntas que sí tenían datos. Ahora muestra las opciones marcadas, las
  tablas y los valores en el formato del instrumento, y el asistente
  recibe las respuestas resumidas de forma entendible
  ([`3a4274a`](https://github.com/sistemaestadistico-siied/SIIED/commit/3a4274a)).
- **La navegación del delegado es coherente.** El botón FICED del panel
  lleva ahora a la página del módulo —con el estado de sus formularios y
  las acciones disponibles— en vez de entrar de frente al formulario, lo
  que dejaba al usuario en una pantalla sin salida al volver
  ([`2dd1281`](https://github.com/sistemaestadistico-siied/SIIED/commit/2dd1281)).
- **Los resultados validados son consultables por todo el organismo.**
  Cada equipo solo veía sus propios formularios; ahora la página del
  módulo muestra además los FICED validados de cualquier equipo del
  organismo. Lo enviado o en borrador de otros equipos sigue siendo
  privado ([`11270fe`](https://github.com/sistemaestadistico-siied/SIIED/commit/11270fe)).

### 5 de noviembre (noche) — última ronda: validaciones FICED, reportes y marca ICED

*FICED — 3 correcciones de validación*

- URLs múltiples en celdas: el validador solo dividía por `;`/`,` y URLs
  separadas por espacio fallaban como un solo token (P39 reportado). Ahora
  divide por coma, punto y coma o whitespace
  ([`87da13a`](https://github.com/sistemaestadistico-siied/SIIED/commit/87da13a)).
- Condicionales `data-show-if` sobre campos JSON (checkbox-tabla): el
  comparador evaluaba el JSON crudo contra el código esperado y borraba
  valores; ahora parsea y busca el código en opciones con `seleccion=true`
  (P24/P25/P30)
  ([`940b97a`](https://github.com/sistemaestadistico-siied/SIIED/commit/940b97a)).
- Respuestas compartidas visibles también en el consolidado del organismo —
  la anotación estaba dentro de `if equipo:`
  ([`82b391e`](https://github.com/sistemaestadistico-siied/SIIED/commit/82b391e)).

*Reportes y exportes*

- Excel de visitas: timestamps salían en UTC (5 h adelante de Bogotá) —
  `tz_convert` a la zona de Django antes de quitar la tz
  ([`32adb8f`](https://github.com/sistemaestadistico-siied/SIIED/commit/32adb8f)).
- 2 errores 500 en producción: exportar producción mensual usaba un lookup
  inexistente; exportar visitas fallaba con caracteres de control en
  paths/user-agents de escáneres — sanitizado con
  `ILLEGAL_CHARACTERS_RE` de openpyxl
  ([`db32153`](https://github.com/sistemaestadistico-siied/SIIED/commit/db32153)).

*Marca ICED alineada*

- Nombre oficial corregido a «Índice de Capacidad Estadística Distrital» y
  paleta unificada navy `#14405D` + verde `#2B7D59` en módulo, hoja de
  vida y Hall de Capacidad
  ([`79977c3`](https://github.com/sistemaestadistico-siied/SIIED/commit/79977c3),
  [`e3b175c`](https://github.com/sistemaestadistico-siied/SIIED/commit/e3b175c),
  [`85feb4d`](https://github.com/sistemaestadistico-siied/SIIED/commit/85feb4d)).

### 6 de noviembre — gestión Superset y «Subir datos»

*Superset: usuarios y roles*

- `crear_usuario`: roles por ID y campo `active` correcto
  ([`cdc8980`](https://github.com/sistemaestadistico-siied/SIIED/commit/cdc8980)).
- Búsqueda de usuario: filtro rison con valor escapado
  ([`e936fba`](https://github.com/sistemaestadistico-siied/SIIED/commit/e936fba)).
- Auditoría rol analista: sync de rol en usuarios existentes + PUT fusionado
  ([`5814d21`](https://github.com/sistemaestadistico-siied/SIIED/commit/5814d21)).
- Prevalidadores de organismo no veían los FICED pendientes
  ([`69e5beb`](https://github.com/sistemaestadistico-siied/SIIED/commit/69e5beb)).

*Subir datos*

- Excel habilitado + fix delimitador TSV
  ([`2e9de0b`](https://github.com/sistemaestadistico-siied/SIIED/commit/2e9de0b)).
- `analista_organismo`: queryset ya sliceado no se filtraba
  ([`95d3a76`](https://github.com/sistemaestadistico-siied/SIIED/commit/95d3a76)).

*ICED — P25/P29/P41*

- P25: se retira el campo falso del link de BP que se almacenaba
  ([`514b231`](https://github.com/sistemaestadistico-siied/SIIED/commit/514b231)).
- P29: opción múltiple + texto corregido; P29.2 gana «Bimensual» y
  «Cuatrimestral» en frecuencia
  ([`2bd19db`](https://github.com/sistemaestadistico-siied/SIIED/commit/2bd19db),
  [`596abe5`](https://github.com/sistemaestadistico-siied/SIIED/commit/596abe5)).
- Parches de compatibilidad post-P25/P29
  ([`28319d0`](https://github.com/sistemaestadistico-siied/SIIED/commit/28319d0)).
- Fix condicional P41 + logo ICED legible sobre chip claro sin duplicar el
  nombre
  ([`077916c`](https://github.com/sistemaestadistico-siied/SIIED/commit/077916c),
  [`263392b`](https://github.com/sistemaestadistico-siied/SIIED/commit/263392b)).

### 7 de noviembre — datasets vivos, seguridad y guía FICED v002

*Plataforma de datos vivos*

- **Conexiones a bases de datos externas** desde Analítica — datasets vivos
  de Superset alimentados por BD del organismo
  ([`a371eaa`](https://github.com/sistemaestadistico-siied/SIIED/commit/a371eaa)).
- **Google Sheet público como dataset vivo** (shillelagh)
  ([`73b866e`](https://github.com/sistemaestadistico-siied/SIIED/commit/73b866e)).
- Auditoría conexiones BD: guard `DROP` por `database_id` + hardening
  ([`2dcb557`](https://github.com/sistemaestadistico-siied/SIIED/commit/2dcb557)).

*FICED*

- Guía de diligenciamiento **v002** (MEDE01.07.01.P001.G001) y
  sincronización de manuales con el formulario real
  ([`580c393`](https://github.com/sistemaestadistico-siied/SIIED/commit/580c393),
  [`952e351`](https://github.com/sistemaestadistico-siied/SIIED/commit/952e351)).
- Permisos de validadores alineados con el modelo correcto
  ([`97f82c3`](https://github.com/sistemaestadistico-siied/SIIED/commit/97f82c3)).
- P6 «Describa» sube de 3 000 a 8 000 caracteres; se quita la nota de ficha
  técnica bajo Registro MOP
  ([`4e69133`](https://github.com/sistemaestadistico-siied/SIIED/commit/4e69133),
  [`203787c`](https://github.com/sistemaestadistico-siied/SIIED/commit/203787c)).
- Nota de confirmación refleja el flujo validador organismo → facilitador
  SIIED ([`4baae56`](https://github.com/sistemaestadistico-siied/SIIED/commit/4baae56)).

*Libro Digital 3D y portal*

- Ecosistema 3D: fixes de enlaces y de reconstrucción de escena
  ([`9519650`](https://github.com/sistemaestadistico-siied/SIIED/commit/9519650)).
- Usuario logueado visible en el nav del portal y del taller
  ([`ad70501`](https://github.com/sistemaestadistico-siied/SIIED/commit/ad70501)).

### 8 de noviembre — auditoría de conciliación ICED y catálogo de sistemas

- **Puntaje 0 en preguntas de varios equipos** (P8, P9, P11…): corregido el
  cálculo del consolidado
  ([`6d7ee01`](https://github.com/sistemaestadistico-siied/SIIED/commit/6d7ee01)).
- Auditoría conciliación/cálculo: 4 correcciones adicionales
  ([`f9fcd29`](https://github.com/sistemaestadistico-siied/SIIED/commit/f9fcd29)).
- **Sistemas de Consulta: nueva taxonomía de 8 categorías**
  ([`bcdbc51`](https://github.com/sistemaestadistico-siied/SIIED/commit/bcdbc51)).
- Editorial: `imagen_url` acepta rutas internas + error visible; idem en
  URL de sistemas/proyectos
  ([`7491515`](https://github.com/sistemaestadistico-siied/SIIED/commit/7491515),
  [`88a4044`](https://github.com/sistemaestadistico-siied/SIIED/commit/88a4044)).

### 9 de noviembre — FICED con devoluciones en cadena y notificaciones

*Flujo de validación — 10 commits*

- **Sin rechazo terminal**: las devoluciones ocurren en cadena entre
  delegado → validador organismo → facilitador SIIED
  ([`009f163`](https://github.com/sistemaestadistico-siied/SIIED/commit/009f163)).
- **Correos automáticos en cada escalón** del flujo, con marca
  institucional en todos los envíos; al validar, la medición se anuncia a
  todos los correos del organismo
  ([`4bffe4d`](https://github.com/sistemaestadistico-siied/SIIED/commit/4bffe4d),
  [`318165e`](https://github.com/sistemaestadistico-siied/SIIED/commit/318165e),
  [`dce56a2`](https://github.com/sistemaestadistico-siied/SIIED/commit/dce56a2)).
- Rol renombrado a «facilitador del equipo SIIED» + plazo de devolución
  ([`0dbae5f`](https://github.com/sistemaestadistico-siied/SIIED/commit/0dbae5f)).
- El SIIED puede corregir y cerrar el consolidado devuelto; su dashboard
  sigue mostrándolo
  ([`52032d9`](https://github.com/sistemaestadistico-siied/SIIED/commit/52032d9),
  [`bf52439`](https://github.com/sistemaestadistico-siied/SIIED/commit/bf52439)).
- Consolidado congelado tras envío a la cola SIIED
  ([`0115b3d`](https://github.com/sistemaestadistico-siied/SIIED/commit/0115b3d)).
- Conciliación: opciones exclusivas ya no se suman con respuestas reales
  ([`340b38e`](https://github.com/sistemaestadistico-siied/SIIED/commit/340b38e)).
- Vaciado de campos condicionales con `!=` corregido (P41 bloqueado)
  ([`998f050`](https://github.com/sistemaestadistico-siied/SIIED/commit/998f050)).
- Producto de cumplimiento: negrita solo en el organismo + mención del
  facilitador SIIED
  ([`b8280d1`](https://github.com/sistemaestadistico-siied/SIIED/commit/b8280d1)).

*Documentación*

- **Guía de diligenciamiento v003**: retrazada al flujo real con
  devoluciones en cadena y correos
  ([`b8881f3`](https://github.com/sistemaestadistico-siied/SIIED/commit/b8881f3),
  [`1110eb9`](https://github.com/sistemaestadistico-siied/SIIED/commit/1110eb9),
  [`11fe5cf`](https://github.com/sistemaestadistico-siied/SIIED/commit/11fe5cf),
  [`07b43bb`](https://github.com/sistemaestadistico-siied/SIIED/commit/07b43bb)).

*Varios*

- Templates del taller: fallback de nombre de usuario → `username`
  ([`d742d7b`](https://github.com/sistemaestadistico-siied/SIIED/commit/d742d7b)).
- Mensaje de edición SIIED sin la instrucción de recálculo (no aplica al
  flujo) ([`b413246`](https://github.com/sistemaestadistico-siied/SIIED/commit/b413246)).

## 4. Avances por eje

| Eje | Entregable |
|---|---|
| FICED | Validación organismo→SIIED en dos etapas, conciliación por equipos, productos de cumplimiento |
| FICED — QA | 8+3 correcciones de diligenciamiento, condicionales (incl. sobre JSON) que no bloquean, histórico verificable por el chat |
| FICED — producción | Carga completa de organismos, resultados de importados consultables, evidencia legible, navegación del delegado y resultados validados compartidos por organismo |
| FICED — flujo | Devoluciones en cadena (sin rechazo terminal), correos automáticos con marca en cada escalón, rol «facilitador SIIED», consolidado congelado, guía v003 |
| FICED — cálculo | Auditoría de conciliación: puntaje 0 multi-equipo corregido, opciones exclusivas no se suman |
| Geo | GeoJSON materializado, descarga de capas por nivel, escala coroplética unificada |
| Analítica/BI | Ciclo de vida de charts sincronizado con el admin; datasets plegables; embed bare; usuarios/roles Superset corregidos |
| Datos vivos | Excel/TSV en «Subir datos», Google Sheet público, conexiones a BD externas con guard `DROP` |
| Datos | `formula_ficha` retirado de todo el pipeline; `columnas_fuente` tolera comas en nombres |
| Reportes | Fix zona horaria Excel visitas, 2 errores 500 en exportes sanitizados |
| Catálogo | Sistemas de Consulta con taxonomía de 8 categorías |
| Marca | Paleta ICED navy+verde y nombre oficial en módulo, hoja de vida y Hall |
| UX | Acordeones con contadores, tabla P23 con scroll horizontal, manuales al día; rediseño limpio de módulo ICED público y hoja de vida de organismos; usuario logueado en el nav |

## 5. Estado actual

- `main` en `07b43bb` — 60 commits funcionales adicionales sobre la base del informe anterior.
- Migraciones 0134 y 0135 generadas; **pendiente aplicarlas en producción**.
- **Pendiente despliegue en producción**: actualizar el servidor (`git pull` + reinicio del servicio) para publicar los commits posteriores a la carga de FICED — incluye ahora el flujo de devoluciones en cadena, los correos automáticos y las auditorías de conciliación/cálculo.
- Verificación recomendada pre-despliegue: configuración SMTP/correos del flujo FICED en el servidor y revisión de destinatarios por organismo.
- `manage.py check`: 0 issues.

## 6. Pantallazos sugeridos para anexar

- Dashboard de validación mostrando la cola ICED con el botón correspondiente al rol.
- Pantalla de conciliación con campos de decisión vs. complementarios.
- Producto de cumplimiento del organismo (sin puntaje) y el de SIIED (con puntaje).
- Correo automático de notificación del flujo FICED con la marca institucional.
- Diálogo de devolución en cadena con plazo indicado.
- Catálogo de datasets de SIIED BI con categorías plegadas.
- «Subir datos» con Google Sheet / conexión a BD externa como dataset vivo.
- Taxonomía de 8 categorías en Sistemas de Consulta.
- Tabla P23 del FICED con scroll horizontal.
- Página del módulo `/iced/` mostrando formularios validados de distintos equipos del organismo.
- Histórico `/iced/historico/` con las respuestas de años anteriores renderizadas (opciones marcadas, tablas).

## 7. Próximos pasos naturales

- Desplegar en producción los commits publicados (`git pull` + reinicio), aplicar migraciones 0134/0135 y validar el flujo FICED de extremo a extremo con datos reales — incluida una **devolución en cadena de prueba** para verificar los correos automáticos.
- Configurar/verificar SMTP en el servidor (los 5 correos del flujo FICED dependen de ello) y los destinatarios por organismo.
- Verificar la publicación del enlace público de Superset sin login (`SUPERSET_PUBLIC_URL`, dominios permitidos del SDK embebido) y poner `TableroBI.visibilidad='publico'`.
- Probar un dataset vivo de BD externa y un Google Sheet público contra la instancia de Superset de producción.
- Comunicar a los organismos el nuevo separador `;` en `columnas_fuente` del wizard y el rol «facilitador del equipo SIIED».
- Rotación de secretos y verificación del fix del logo del navbar.
