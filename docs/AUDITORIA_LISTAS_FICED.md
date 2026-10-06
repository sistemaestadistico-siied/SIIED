# Auditoría de listas de selección FICED vs ejercicio análogo 2025

**Fecha:** 2026-09-22
**Fuente de verdad:** `docs/insumos/Uso_Interno_Consolidado_ICED_2025.xlsx` (HojaMaestra — respuestas reales del ejercicio análogo)
**Objeto auditado:** `indicadores/forms_iced.py` (wizard FICED, P8-P42)

## Resultado general

La gran mayoría de las listas de selección del formulario web **sí corresponden a datos reales** del ejercicio análogo. Se verificaron ~40 listas; solo 4 presentan divergencias materiales y 3 menores.

## Listas verificadas como correctas (coinciden con el análogo)

| Pregunta | Contenido | Análogo |
|---|---|---|
| P13 | 10 herramientas de procesamiento | 13.1-13.10 ✓ |
| P14 | 7 gestores de BD | 14.1-14.7 ✓ |
| P15.1 | Herramientas de visualización | 15.1.2-15.1.9 ✓ |
| P17 / P20 / P22 | Escala de suficiencia (5 niveles) | 17.x / 20.x / 22.x ✓ |
| P18 | 4 opciones de RRHH | 18.1-18.4 ✓ |
| P21 | 13 rubros presupuestales | 21.1-21.13 ✓ |
| P24 | 5 lineamientos/normas | 24.1-24.5 ✓ |
| P24.1 | 6 fuentes de conceptos | 24.1.1-24.1.6 ✓ |
| P25 | 11 mecanismos de detección de necesidades | 25.1-25.11 ✓ |
| P26 | 6 mecanismos de consolidación | 26.1-26.6 ✓ |
| P27 | 4 roles de articulación | 27.1-27.4 ✓ |
| P28 | 10 mecanismos + frecuencias + analítica | 28.1-28.10 ✓ |
| P29 | 4 roles + sub-opciones (8/4/8/11) | 29.1-29.4 ✓ |
| P30 | 7 opciones de lineamientos | 30.1-30.7 ✓ |
| P31 | 5 tipos de analítica | 31.1-31.5 ✓ |
| P32 | 6 estados herramientas DATIC | 32.1-32.6 ✓ |
| P36 | 4 usos de indicadores | 36.1-36.4 ✓ |
| P37 | 13 tipos de usuarios | 37.1-37.13 ✓ |
| P38 | 7 productos de difusión | 38.1-38.7 ✓ |
| P39 | 4 medios de difusión | 39.1-39.4 ✓ |
| P40 | 14 elementos publicados en web | 40.1-40.14 ✓ |
| P41.1 | 6 mecanismos de satisfacción | 41.1.1-41.1.6 ✓ |
| P9 / P10 / P11 / P12 | Herramientas fortalecimiento, participación, instancias, trazabilidad | 9.x-12.x ✓ |

## Divergencias materiales (mockup confirmado)

### 1. P30 `p30_tabla_alcaldia` — códigos MOP inventados (CRÍTICO)

`forms_iced.py` líneas 1258-1270: select hardcodeado `MEDE01.05.02.P025.F001`-`F010` con descripciones genéricas ("Guía de validación estadística", "Manual de calidad del dato", etc.). **Solo F001 es real.**

Códigos MOP reales observados en el análogo (30.1.1-30.1.9, ~20 distintos):

- `MEDE01.05.02.P025.F001` — Plan de trabajo por proceso
- `MEDE01.05.02.P025.G001` — Guía técnica para la formulación, medición, seguimiento
- `MEDE01.07.01.P001.I001` — Instructivo de diligenciamiento del formulario
- `MEDE01.07.01.P003.F001` — Autorización AMDA
- `MEDE01.07.01.P003.G001` — Guía para documentación de una Operación Estadística
- `MEDE01.07.01.P003.G002` — Guía para la documentación de sistemas de información
- `MEDE01.07.01.P003.G003` — Guía para construcción de diccionario de datos
- `MEDE01.07.01.P005.F002` — Ficha Técnica de Formulación de Indicadores
- `MEDE01.07.01.P005.F003` — Registro de Metadatos de indicadores
- `MEDE01.07.01.P005.F005` — Ficha Técnica de Seguimiento de Indicadores
- `MEDE01.07.01.P005.I002` — Instructivo para el diligenciamiento de las fichas técnicas
- `MEDE01.07.01.P008.G002` — Guía para el diseño e implementación de observatorios
- `MEDE01.07.01.P009.G002` — Guía metodológica para recopilación sistemática de datos
- `MEDE01.07.01.P009.G003` — Guía técnica para recopilación sistemática de datos
- `MEDE01.07.01.P009.G004` — Guía de uso y aplicación del marco geoestadístico
- `MEDE01.07.01.18.P008` — Guía para el diseño e implementación de observatorios
- `MEDE01.07.01.18P009` — Guía para documentación de una Operación Estadística
- `MEDE01.07.01.18.P05.F02` — Ficha Técnica de Formulación de Indicadores
- `MEDE01.07.01.18.P05.F04` — Ficha Técnica de Seguimiento de Indicadores de Trámite
- `MEDE01.07.01.18.P05.F05` — Ficha Técnica de Seguimiento de Indicadores

**Corrección propuesta:** reemplazar el select por la lista real + opción "Otro (especificar código)" con campo de texto libre, ya que el análogo también registró entradas sin código MOP.

### 2. P19 RRHH — pérdida de granularidad en "nombrado"

El análogo usa categorías `PU1`-`PU6` (Profesional Universitario grados 1-6) + `AA`, `TO`, `TA`, `PE`, `AS`. El web colapsa todo en una sola categoría `P` (Profesional). Se pierde el detalle de grados que el ejercicio real sí capturó.

**Corrección propuesta:** expandir la columna de nivel de nombrado a PU1-PU6 + AA/TO/TA/PE/AS, o confirmar con el equipo estadístico si la simplificación fue deliberada.

### 3. P33/P34 lista de observatorios — parcialmente inventada

El web tiene 15 nombres hardcodeados. El análogo observó estos nombres reales que el web **omite**:

- Observatorio de Vivienda y Hábitat
- Observatorio de la Educación Distrito Especial de Santiago de Cali
- Observatorio de la Secretaría de Cultura de Cali
- Observatorio de Ordenamiento Territorial – Expediente Municipal

Y el web incluye nombres **no observados** en el ejercicio real: Cáncer, Salud Ambiental, Salud Mental, ODRAF, Salud Pública, "Seguridad Vial y Movilidad Sostenible" (duplica MOVIS).

Nombres con redacción distinta: "Paz y Cultura Ciudadana" vs real "Paz, Derechos Humanos y Cultura ciudadana"; "Turismo" vs "Turístico"; "Salud Pública" vs "Salud del distrito de Santiago de Cali".

**Corrección propuesta:** alinear la lista con los nombres reales observados + mantener `permitir_otro` (ya existe). Idealmente la lista debería venir de una tabla de referencia en BD, no hardcodeada.

### 4. P8 — opción incorrecta ('programas' en vez de 'actividades')

Análogo 8.x (generación): PlanDeTrabajo, PlanDeAccion, **Actividades**, Proyectos, No_Incluye.
Web P8: planes_trabajo, planes_accion, **programas**, proyectos, no_se_incluyen.

P9 (fortalecimiento) sí usa 'programas' correctamente (análogo 9.3 = `ind_programas_fortalecimiento`). Probable error de copiar P9→P8.

**Corrección propuesta:** cambiar la opción de P8 a 'actividades' ("Actividades").

## Divergencias menores

- **P31.1 frecuencia:** web agrega 'Bimestralmente' (5 opciones); análogo solo tiene 4 (Mensual/Trimestral/Semestral/Anual). Decidir si se conserva.
- **P35 `tipo_documento`:** select (metodología/protocolo/manual/guía/instructivo/otro) no existe en el análogo (era texto libre). Razonable como mejora UX, pero es inventado.
- **P41.2 matriz de satisfacción:** no aparece en el dump análogo (posible adición web o en otra hoja del instrumento). 3 indicadores × 5 niveles.
- **P24.0 nomenclaturas:** lista de 35 clasificaciones DANE no verificable contra el análogo (24.3 era solo flag X), pero corresponde al catálogo oficial DANE. OK.
- **P30 nombres DANE/DNP:** el análogo tenía los nombres de variable intercambiados (30.2 `IMPLEMENTA_GuiaIndicadoresDANE` preguntaba por DNP). El web los tiene correctos — el bug era del análogo.

## Recomendación

Corregir los 4 items materiales (P30 MOP, P19 grados, P33/P34 observatorios, P8 actividades). Los demás son decisiones de diseño a confirmar con el equipo estadístico.
