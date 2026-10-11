# Auditoría y saneamiento de dominios de desagregación

**Fecha:** 2026-10-11 · **Ambiente:** desarrollo (BD `indicadores` restaurada desde
`backups_prod/default-siamda-ap-bd-prd-2026-10-11-160502.psql.bin`)
**Decisión del equipo:** saneamiento por **duplicación** de desagregaciones por indicador.

---

## 1. Mapa de relaciones (verificado contra la BD restaurada)

### Entidades

| Tabla | Rol | Campos clave |
|---|---|---|
| `indicadores_dominiodesagregacion` | Eje de desagregación ("Sexo", "Comuna") | `nombre`, `tipo` (`tematica`/`geografica`), `nivel_geografico_id`, `dominio_padre_id` (self-FK), `tipo_agregacion_total` |
| `indicadores_desagregacion` | Valor de un dominio ("Mujer", "Comuna 3") | `nombre`, `codigo`, `descripcion`, `dominio_id` → dominio (CASCADE), `capa_geo_id`, `desagregacion_padre_id` (self-FK, SET_NULL), `es_rango`, `valores_rango` |

### Aristas que APUNTAN a `indicadores_desagregacion` (8)

| Tabla / columna | Naturaleza | Volumen en prod |
|---|---|---|
| `indicadores_dato_desagregaciones_tematicas` | M2M Dato↔Desag (temática) — **verdad terrenal**: qué usa cada observación | — |
| `indicadores_dato_desagregaciones_geograficas` | M2M Dato↔Desag (geográfica) | — |
| `indicadores_graficoserie_desagregaciones` | M2M serie↔desag (filtros de cada serie) | 14.555 filas |
| `indicadores_graficoserie.desagregacion_geografica_id` | FK legacy directo en la serie | 4.861 series |
| `indicadores_graficoserie.desagregacion_tematica_id` | FK legacy directo en la serie | 9.602 series |
| `indicadores_grafico_desagregaciones_tematicas_predeterminadas` | M2M filtros por defecto del gráfico | 29 filas |
| `indicadores_grafico_desagregaciones_geograficas_predeterminadas` | M2M filtros por defecto del gráfico | 20 filas |
| `indicadores_desagregacion.desagregacion_padre_id` | self-FK en cascada (barrio→comuna) | 10 desags |

### Aristas que APUNTAN a `indicadores_dominiodesagregacion` (5)

| Tabla / columna | Naturaleza | Volumen en prod |
|---|---|---|
| `indicadores_desagregacion.dominio_id` | Una desag. pertenece a **un solo** dominio (CASCADE: borrar dominio borra sus desags) | 2.890 |
| `indicadores_indicador_dominios_desagregacion_tematica` | M2M Indicador↔Dominio | — |
| `indicadores_indicador_dominios_desagregacion_geografica` | M2M Indicador↔Dominio | — |
| `indicadores_catalogodominio.dominio_id` | Catálogos públicos publicados sobre un dominio | **0** (ninguno montado) |
| `indicadores_dominiodesagregacion.dominio_padre_id` | Jerarquía de dominios (subdominio de otro) | solo 2 |

> `Indicador` **no tiene FKs directos a Desagregacion** — solo los dos M2M a dominios.

### Tablas con nombre engañoso — **NO tocar** (no apuntan a `Desagregacion`)

- `indicadores_fuentedatos_desagregaciones` → `(fuentedatos_id, opciontaller_id)`
- `indicadores_retoanalisis_desagregaciones` → `(retoanalisis_id, opciontaller_id)`
- `indicadores_evaluacionseguridad_datos_sensibles` → `(evaluacionseguridad_id, opciontaller_id)`

Las tres son M2M hacia `OpcionTaller` del módulo taller — nombres parecidos, sin relación.

---

## 2. Causa raíz del daño (a nivel de código)

- `views_recoleccion.py:867-869` — la plantilla maestra de carga masiva usa nombres de
  columna **genéricos**: `Desagregacion_Geografica`, `Desagregacion_Tematica_1`,
  `Desagregacion_Tematica_2`.
- `wizard_admin_unificado.py:1830` — `DominioDesagregacion.objects.get_or_create(
  nombre=col_name.strip(), tipo=tipo)`: todos los archivos con la misma columna caen
  en el **mismo dominio** y acumulan sus valores distintos → dominio inflado.
- `wizard_helpers.py:198-201` — `filter(nombre__iexact, tipo)` — mismo patrón por nombre.
- `wizard_admin_unificado.py:1848-1853` — al reusar un dominio con otro `tipo`, lo
  remueve de la M2M opuesta (origen de dominios mal tipados, ej. id 91).

---

## 3. Cómo se consume (por qué duele)

- `Grafico.get_desagregaciones_{tematicas,geograficas}_disponibles()`
  (`models.py:957-972`): `Desagregacion.filter(dominio__in=indicador.dominios_*)` —
  un dominio inflado = **547 opciones en el filtro del frontend** para un indicador
  que solo usa 2-3.
- `ReglaExtraccion.desagregaciones_asociadas` (`models.py:878`): misma derivación —
  la extracción del CSV se contamina con candidatos ajenos.
- `GraficoSerie.get_desagregaciones()` (`models.py:1005`): M2M `desagregaciones`
  primero; si vacío, FKs legacy. `sincronizar_fks_legacy()` los mantiene alineados.
- `views.py:795-905`: el detalle filtra `Dato` por IDs de desagregación del GET.

---

## 4. Estado real medido en producción

| Dominio | id | Desags | Indicadores | Uso por indicador (min/avg/max) |
|---|---|---|---|---|
| `desagregacion_tematica_2` | 50 | **547** | 65 | 0 / 2.3 / 32 |
| `desagregacion_tematica_1` | 63 | **487** | 51 | 0 / 12.1 / 74 |
| `desagregacion_geografica_1` | 69 | **313** | 17 | 0 / 27.4 / 108 |
| `comunas` (geográfica) | 96 | 431 | 3 | 24 / 152 / 365 |
| `nombre_indicador` | 80 | 144 | 139 | 0 / 0.9 / 1 (dominio degenerado) |
| `Concepto` | 14 | 25 | 39 | 1 / 1.7 / 8 |
| `Municipio` | 3 | **1** | 174 | 0 / 0 / 0 — quedó **vacío/quebrado** |
| `Área Geográfica` | 4 | 7 | 28 | 0 / 2.1 / 4 |

Otros hallazgos:

- **Inconsistencia inversa: 0** — ningún `Dato` referencia una desag. cuyo dominio no
  esté vinculado al indicador. Las M2M son "superset-consistentes": el saneamiento no
  pierde referencias si tomamos el set real desde `dato`/`serie`/`predeterminada`.
- **436 de 1.022 indicadores activos no tienen `Dato`** → su set real se infiere de
  series y predeterminadas (o quedan sin dominio si tampoco las tienen).
- Duplicados de nombre: `desagregacion_tematica_1` existe como temática (63) **y**
  geográfica (91); `comuna`/`comunas`, `hora`, `día`, `ciudad` duplicadas entre tipos;
  variantes con tilde (`subclase_vehiculo`/`subclase_vehículo`); `sexos` (id 40, vacío)
  vs `Sexo` (id 2).
- Jerarquía padre: solo 2 dominios (`derecho`→`componente`, `esperanza_de_vida`→`Sexo`)
  y 10 desags con `desagregacion_padre` — manejar explícito, no descubrir a mitad.

---

## 5. Cirugía por DUPLICACIÓN — diseño

Por cada indicador (orden: activos primero), por cada **dominio-origen efectivamente usado**:

### 5.1 Set real del indicador

```
set_real(ind, lado) =
    desags de sus datos     (dato_desagregaciones_{tematicas|geograficas} via dato.indicador_id)
  ∪ desags de sus series    (graficoserie_desagregaciones + FKs legacy de sus gráficos)
  ∪ desags predeterminadas  (grafico_desagregaciones_*_predeterminadas de sus gráficos)
```
Agrupar el set por `desagregacion.dominio` origen → una celda de cirugía por
(indicador, dominio-origen). Un indicador puede usar 2 dominios temáticos → 2 dominios nuevos.

### 5.2 Crear dominio nuevo

- `nombre = "{origen.nombre} · {indicador}"` (o patrón acordado)
- Copiar: `tipo` (del **lado M2M donde se vinculará**, no del dominio origen — corrige
  los mal tipados), `nivel_geografico`, `tipo_agregacion_total`
- `dominio_padre`: si el dominio origen tenía padre y el padre también se divide por
  indicador → apuntar a la copia del padre de este indicador; si no, al padre original.

### 5.3 Duplicar desagregaciones del set

Copia por fila: `nombre`, `codigo`, `descripcion`, `capa_geo`, `es_rango`,
`valores_rango`. Nuevo `dominio_id` = dominio nuevo.
`desagregacion_padre` → el **duplicado del padre creado para este mismo indicador**
si el padre está en su set; si no, se conserva apuntando al original.

> Sin constraint UNIQUE en (dominio, nombre): duplicar nombres entre dominios es seguro.
> La deduplicación es a nivel app: `(dominio, nombre__iexact)`.

### 5.4 Reapuntar referencias (solo las del indicador)

| Referencia | Acción |
|---|---|
| `dato_desagregaciones_{tem,geo}` de sus `Dato` | `UPDATE desagregacion_id = dup WHERE dato_id IN (datos del indicador) AND desagregacion_id = orig` |
| `graficoserie_desagregaciones` de sus `Grafico` | idem por `graficoserie_id` |
| `graficoserie.desagregacion_{geo,tem}_id` | remap al duplicado (luego `sincronizar_fks_legacy`) |
| `grafico_desagregaciones_*_predeterminadas` de sus gráficos | idem |
| M2M `indicador_dominios_*` | `remove(dominio_gordo)`, `add(dominio_nuevo)` |

### 5.5 No tocar / dejar pendiente

- `CatalogoDominio`: 0 filas — sin acción.
- Dominios viejos y sus desags **no reclamadas**: quedan huérfanas hasta revisión; el
  CASCADE de `desagregacion.dominio` recuerda que borrar un dominio borra sus desags.
- `dominio_padre` / `desagregacion_padre`: solo 2+10 casos — tratar a mano y verificar
  los filtros en cascada resultantes.

### 5.6 Seguridad operativa

- Todo por transacción por indicador (`BEGIN`…`COMMIT` por celda); abortar un
  indicador no compromete a los demás.
- Tabla de auditoría `audit_duplicacion_desagregacion(indicador_id, desag_orig_id,
  desag_dup_id, dominio_nuevo_id)` — permite deshacer y genera el reporte final.
- Dry-run primero: reporte CSV por indicador (set real, dominio nuevo, duplicados,
  filas a reapuntar) **sin escribir nada**.
- Recuperable: `backups_prod/indicadores_dev_previa_20261011_172127.dump`.

### 5.7 Conciliación posterior (fase 2)

Con dominios ya por-indicador: comparar sets entre dominios del mismo concepto;
diferencia simétrica ≤ 2 → fusión en dominio compartido (mover desags duplicadas al
dominio sobreviviente o elegir canónica y redireccionar — detalle a decidir en fase 2).

---

## 6. Checklist de verificación post-cirugía

- [x] Ningún indicador activo enlazado a un dominio "gordo"
- [ ] Filtro del frontend lista solo las desags reales del indicador (verificación visual pendiente)
- [x] Conteo de filas reapuntadas = filas previstas por el dry-run (sin huérfanos)
- [x] `dato_desagregaciones_*` del indicador solo referencia ids de sus dominios
- [x] Legacy FKs de series resincronizados (`sincronizar_fks_legacy`)
- [ ] Jerarquías padre (2 dominios, 10 desags) verificadas visualmente en el filtro
- [ ] `ReglaExtraccion.desagregaciones_asociadas` devuelve el set limpio

---

## 7. Resultados ejecutados (2026-10-11)

### 7.1 Purga de `nombre_indicador` (dominio id 80)

Dominio degenerado eliminado por decisión del equipo:
- 144 desags eliminadas, 12.017 filas `dato_desagregaciones_tematicas`,
  1.080 referencias de series (M2M + FK legacy), 139 vínculos indicador↔dominio
- Snapshots: `audit_d80_desags`, `audit_d80_links`, `audit_d80_series_fk`

### 7.2 Cirugía por duplicación (`cirugia_dominios.psql`)

- **1.022/1.022 indicadores activos procesados, 0 fallos**
- 407 dominios nuevos (`origen · ind-<id>`), 5.797 desags duplicadas
- 186.301 filas reapuntadas (159.494 dato M2M · 13.475 serie M2M ·
  13.383 serie FK legacy · 49 predeterminadas)
- 744 vínculos viejos quitados → 407 nuevos
- 0 indicadores activos en dominios gordos; 0 inconsistencias inversas
- Guardia de idempotencia por indicador; transacción por CALL
- Auditoría: `audit_duplicacion_desagregacion`, `audit_cirugia_log`

### 7.3 Eliminación de dominios huérfanos

- **85 dominios eliminados** + 2.235 desags (criterio: sin vínculos y sin
  desags con datos relacionados ni `capa_geo`)
- Sobreviven 5 viejos por protecciones: `Sexo`(2) y `componente`(116) por ser
  `dominio_padre`, `Área Geográfica`(4) y otros con datos de inactivos
- Snapshots: `audit_dominios_eliminados`, `audit_desags_eliminadas`

### 7.4 Conciliación fase 2 (`conciliacion_dominios.psql`)

- **215 dominios absorbidos** en clusters con diff ≤2 por nombre normalizado;
  1 saltado (dominio 187, padre de otros — guardia correcta)
- Canónico preferido: dominio viejo si existe (ej. `Sexo` id 2 absorbió miembros);
  si no, el cluster forma dominio con nombre limpio del concepto o `#N`
- Resultado: **178 dominios totales / 3.524 desags**
- 0 links rotos, 0 refs rotas a desags tras la fusión
- 19 dominios `· ind-` restantes (difiere >2 de todo canónico del grupo)
- Auditoría: `audit_conciliacion`, `audit_conciliacion_log`
- Dominios más compartidos post-fusión: `desagregacion_tematica_2 #3` (21 ind.),
  `Área Geográfica #2` (16), `desagregacion_tematica_2 #14` (15), `Sexo` (12)

### 7.5 Notas operativas

- Scripts: `dry_run_dominios.psql` (reportes), `cirugia_dominios.psql`
  (`sanea_indicador`), `conciliacion_dominios.psql` (`concilia_grupo`)
- Los 6 indicadores inactivos no fueron procesados
- `documentovector` sigue pendiente: requiere `CREATE EXTENSION vector` como
  superuser y restauración quirúrgica desde el backup

### 7.6 Renombrado de dominios genéricos

- **90 dominios renombrados** según el contenido real de sus desags:
  `Barrio` (335 desags barriales), `Comuna` ×6, `Vereda` ×2, `Grupo de edad` ×3,
  `Centro de salud`, `IPS` ×3, `Clínica`, `Uso del suelo` ×3, `Tipo de obra` ×3,
  `Ciudad` ×2, `Municipio`, `Ámbito geográfico` ×2, `División de gasto` ×4,
  `Tipo de emergencia` ×5, `Estrato`, `Entidad bancaria`, `Producto`,
  `Causa de mortalidad` ×2, `Institución de educación superior` ×2, `Asignatura`,
  `Modalidad`, `Nivel de formación`, `Sexo`, `Categoría hotelera`,
  `Número de hogares`, `Zona de expansión`, `Tipo de suscriptor` ×2,
  `Tipo de hurto`, `Tipo de maltrato`, `Tipo de dengue`, `Estado catastral`,
  `Variable de cálculo` ×2, `Variable de salud` ×2, `Variable de población`,
  `Variable de educación`, `Variable` ×3, `Valor` ×2, `Total`, `Expansión`,
  `Suelo urbano/rural`, `Altura sobre el nivel del mar`, `Temperatura promedio`,
  `Precipitación promedio anual`, `Humedad relativa media anual`,
  `Esperanza de vida al nacer`, `Tipo de unidad de salud`,
  `Tipo de servicio de salud`, `Centro de atención IPS`,
  `Naturaleza de la institución`, `Medida de población estudiantil` ×3,
  `Medida de desempeño`, `Ámbito`, `Ámbito y grado`
- **Dominio `desagregacion_tematica_1` (id 63) eliminado**: último dominio gordo
  sobreviviente, vinculado solo a ind-1528 (inactivo, 0 datos). Sus 487 desags
  no tenían referencias ni `capa_geo` → purgadas, vínculo quitado, dominio borrado.
  Snapshots: `audit_d63_desags`, `audit_d63_link`
- **Estado final: 177 dominios / 3.037 desags / 0 nombres genéricos**
- Los 4 dominios `Grupo de edad` coexisten con nombre correcto (clusters por
  formato de rango, no se fusionaron por diff>2)

### 7.7 Desags sin relación con ningún indicador

Búsqueda de desags sin referencias ni vínculo indirecto → 17 encontradas:

- **`componente` (id 116) eliminado**: quedó huérfano cuando su hijo `derecho`
  (115) se eliminó en la criba. 11 desags con 0 refs/0 capa_geo/0 hijas →
  dominio + desags borrados. Snapshot: `audit_d116_componente`
- **`Sexo` (id 2)**: `Hombre`(101) y `Mujer`(103) eliminadas — nadie las usa
  (los datos usan `Hombres`/`Mujeres`/`Total`). Queda con 3 desags
- **`Área Geográfica` (id 4)**: `Sin Información`, `Área Metropolitana de Cali`,
  `Nacional`, `Cali` eliminadas (sin capa_geo ni refs). Queda con las 3
  desags con `capa_geo` (`Cabecera Municipal`, `Centros Poblados y Rural
  Disperso`, `Total`)
- Snapshot sueltas: `audit_desags_sueltas`. 0 refs rotas

**Estado final: 176 dominios / 3.020 desags**
