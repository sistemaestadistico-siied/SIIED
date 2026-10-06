# Revisión semántica: textos FICED original (Excel) vs formulario web

**Fecha:** 2026-09-22
**Motivo:** queja del Departamento de Planeación por "sutiles" diferencias en los textos.
**Fuente original:** `docs/insumos/Uso_Interno_Consolidado_ICED_2025.xlsx` → HojaMaestra, columna "Pregunta" (texto exacto que vieron los respondentes).
**Comparado contra:** `indicadores/forms_iced.py` (labels y choices).

## A. Error propio ya revertido

- **P8**: había cambiado `'programas'`→`'actividades'` guiado por el nombre de variable `ind_Actividades_generacion`. El texto real de la pregunta 8.3 es *"Tiene **programas** con actividades específicas de generación…"*. **Revertido** en `forms_iced.py` y `calcular_iced.py` (peso_p8).

## B. Diferencias semánticas sustantivas (cambian alcance o significado)

| # | Pregunta | Original | Web | Impacto |
|---|---|---|---|---|
| B1 | **P34** | "observatorios **que lidera**" | "observatorios que el organismo **lidera o en los que participa** del proceso de producción" | Amplía el universo de respuesta: el original solo pedía los que lidera. |
| B2 | **P33** | Nombre de observatorio = **texto libre** | Lista cerrada de 15 observatorios (+otro) | Restringe respuestas; aunque tiene "otro", sesga hacia la lista. |
| B3 | **P21.10** | "Contratación de **expertos** en análisis de datos (estadísticos, científicos de datos)" | "Contratación de **personas** para el análisis de datos (**analistas**, estadísticos, científicos de datos)" | "expertos"→"personas" y agrega "analistas": cambia el perfil descrito. |
| B4 | **P31** | Opciones 2-4 con ejemplos: "(como regresiones, análisis de varianza, entre otros)", "(como series de tiempo, modelos de panel…)", "(como redes neuronales, árboles de decisión…)" | Ejemplos eliminados | Los ejemplos ayudaban a clasificar; P28.2 sí los conserva → inconsistencia interna. |
| B5 | **P31.1** | 4 frecuencias: mensual, trimestral, semestral, anual | 5: agrega **Bimestralmente** | Opción no existente en el instrumento. |
| B6 | **P10** | "Participa activamente / ocasionalmente / de manera limitada / No participa en actividades de fortalecimiento de competencias estadísticas" | Cada opción expandida con cláusulas ("el organismo asiste y se involucra en todas las actividades de fortalecimiento disponibles"…) | Texto explicativo añadido que puede condicionar la respuesta. |
| B7 | **P41.1** | "Encuestas de satisfacción. / Entrevistas en profundidad. / Grupos focales. / Análisis de comentarios y sugerencias. / Indicadores de uso / otros" | Cada mecanismo con descripción larga añadida ("Cuestionarios estructurados que pueden incluir preguntas de opción múltiple y abiertas…") | Definiciones añadidas no presentes en el original. |
| B8 | **P29.1** | Metodologías (nombres cortos) | Cada metodología con descripción añadida ("uso de estadísticas y datos numéricos para evaluar resultados"…) | Mismo patrón de expansión. |

## C. Diferencias menores de redacción (mismo significado)

| # | Pregunta | Original → Web |
|---|---|---|
| C1 | P6 | Web agrega "(Decreto 0516 de 2016)" al final |
| C2 | P7 | "procedimientos relacionad**as**" (error del original) → "relacionad**os**" (corregido) |
| C3 | P11 | "comisiones **estadísticas** / comités **estadísticos** / mesas **estadísticas** / observatorios **estadísticos**" → web omite el calificativo |
| C4 | P12, P27, P32 | Web agrega prefijos "Sí," / "No," / "Sí, pero de manera parcial:" a las opciones |
| C5 | P13 | "**Phyton**" (typo del original) → "Python"; "Programas de datos geográficos" → "Programas de procesamiento de datos geográficos (ArcGIS, QGIS, entre otros)"; "Desarrolladas por el organismo" → "Herramientas desarrolladas por el mismo organismo" |
| C6 | P17/P20/P22 | "no dificulta"→"no dificultan", "causa dificultades"→"causan dificultades" (concordancia plural) |
| C7 | P18 | Opciones de frase completa → "Una persona / Un grupo / Varios grupos / No existe" |
| C8 | P26 | Opciones abreviadas ("Los indicadores de resultado son de análisis interno exclusivo" → "Análisis interno exclusivo") |
| C9 | P27 op.4 | "No existe un proceso de articulación" → "No — Pase a la pregunta 29" (hint de navegación reemplaza el texto de respuesta) |
| C10 | P28 | Opciones abreviadas + hints "— Pase a la pregunta 28.1/28.2"; "a través de un comité interinstitucional"→"Coordinación a través de un comité interinstitucional"; "talleres"→"Talleres con partes interesadas"; "herramientas en la nube (drive)"→"Uso de herramientas en la nube (Drive)" |
| C11 | P30 | "No implementa ningún lineamiento"→"Ninguno"; "otros lineamientos"→"Otro(s)" |
| C12 | P36 | Web agrega "(Producto, Resultado, Políticas, Objetivos Desarrollo Sostenible)" al enunciado |
| C13 | P38 | "otros productos"→"Otro(s)"; "No se realiza difusión"→"No realiza difusión — ¡Fin del formulario! Pase a Registrar Respuesta" |
| C14 | P41 | "indaga **sí**… **satisfacen**" (typos del original) → "indaga **si**… **satisface**" (corregido) |
| C15 | P23 | "Documento metodológico"→"La OE cuenta con documento metodológico"; "ficha metodológica"→"La OE cuenta con ficha metodológica"; "Publicado en SICODE"→"¿Publicado en SICODE?" |
| C16 | P21 | "e.g.,"→"ej." (21.5, 21.8); headers "Del presupuesto ANUAL Hardware:"→"Costos de Hardware" |

## D. Casos donde el WEB está mejor que el original (errores del Excel)

- **P30**: el consolidado tenía los nombres de variable DANE/DNP cruzados (30.2 `IMPLEMENTA_GuiaIndicadoresDANE` preguntaba por DNP). El web asigna correctamente cada guía a su entidad según el texto de pregunta.
- **P40.10**: el consolidado duplicaba el texto de 40.1 ("bases de datos anonimizadas") cuando la variable era `PublicaWeb_CalendarioDifusion`. El web tiene "Calendario de difusión" correcto.
- Typos del original corregidos: "Phyton"→Python, "relacionadas"→relacionados, "sí"→si, "satisfacen"→satisface, "política públicas"→políticas públicas, "analísis"→análisis, "segumiento"→seguimiento, "analítca"→analítica.

## Recomendación

- **Alinear B1-B8**: son las diferencias que probablemente motivaron la queja (cambian qué se pregunta o cómo se interpreta). Especialmente P34 (lidera vs participa), P21.10 (expertos vs personas), P31 (ejemplos eliminados), P31.1 (bimestral añadido).
- **Decidir política para C**: si Planeación exige fidelidad literal, restaurar textos originales; si aceptan mejoras editoriales, documentar las desviaciones como "adecuaciones de redacción aprobadas".
- **Conservar D**: son correcciones de errores del propio instrumento.

---

## ESTADO: Restauración por fidelidad literal aplicada (2026-09-22)

Decisión del usuario: la queja es por fidelidad literal → se restauraron los textos originales del instrumento.

**Restaurado en `forms_iced.py`:**

- **P6**: eliminada cita "(Decreto 0516 de 2016)" añadida.
- **P8**: revertido a 'programas' (error previo inducido por nombre de variable).
- **P10**: opciones cortas originales (sin expansiones explicativas).
- **P11**: calificativo "estadísticas/estadísticos" restaurado; "Otros"→"Otras instancias".
- **P12**: prefijos "Sí,/No,/Sí, pero de manera parcial:" eliminados.
- **P13**: "Desarrolladas por el organismo", "Programas de datos geográficos", "Otras herramientas", "Ninguna herramienta de procesamiento", "STATA".
- **P14**: "Ningún gestor".
- **P18**: frases completas originales restauradas.
- **P21**: "Contratación de **expertos** en análisis de datos (estadísticos, científicos de datos)"; encabezados "Del presupuesto ANUAL — Hardware/Software/Personal y capacitación"; "e.g.,".
- **P23**: "Documento metodológico", "Ficha metodológica", "Publicado en SICODE".
- **P24**: "No implementa lineamientos, normas y estándares"; asterisco eliminado de "Conceptos estandarizados".
- **P24.1**: frases completas "Los conceptos que usa provienen de…".
- **P26**: frases completas "Los indicadores de resultado…".
- **P27**: prefijos "Sí," eliminados; opción 4 → "No existe un proceso de articulación".
- **P28**: opción **28.10 restaurada** ("No es necesario porque el indicador de resultado no tiene articulación con otro organismo") — el web la había fusionado con "No se articulan"; textos originales del resto de opciones.
- **P28.1, P29.2**: formas adverbiales (Mensualmente, etc.).
- **P29**: opción 4 → "Otro rol en relación con las políticas públicas vigentes".
- **P29.4**: "No desarrolla ninguna de las anteriores".
- **P30**: "Otros lineamientos", "No implementa ningún lineamiento".
- **P31**: ejemplos parentéticos restaurados en opciones 1-4.
- **P31.1**: eliminada opción "Bimestralmente" (no existía) y conteos parentéticos → 4 frecuencias originales.
- **P32**: prefijos "Sí,/No," eliminados.
- **P34**: "observatorios que el organismo **lidera**" (el web había añadido "o en los que participa").
- **P36**: paréntesis "(Producto, Resultado, Políticas, ODS)" eliminado.
- **P38**: "Otros productos", "No se realiza difusión".
- **P41.1**: descripciones añadidas eliminadas → nombres cortos originales.
- **P42**: "Observaciones generales".

**Scoring (`calcular_iced.py`):**

- `peso_p8` revertido a 'programas'.
- P28: nueva opción `no_es_necesario` puntúa 100% (articulación no requerida, misma regla que 27.3); `no_articulan` sigue como exclusiva → 0%.

**Conservado deliberadamente (correcciones del original):**

- Typos del Excel: "Phyton"→Python, "relacionadas"→relacionados, "sí"→si, "satisfacen"→satisface, "política públicas"→políticas públicas, "analísis/segumiento/analítca" corregidos.
- Concordancia plural en P17/P20/P22 ("dificultan/causan" — el original usaba singular incorrecto).
- P30 DANE/DNP correctamente asignados (el consolidado los tenía cruzados).
- P40.10 "Calendario de difusión" (el consolidado duplicaba el texto de 40.1).
- Hints de navegación "— Pase a la pregunta X" conservados como ayuda de UX (no alteran el texto de la respuesta).

**Pendiente de confirmación con Planeación:**

- **P14 'sybase'**: el consolidado salta de 14.4 a 14.6 — existía una opción 14.5 no observada. Se conserva 'sybase' como candidato plausible; confirmar cuál era la opción real.
- **P33**: el original era texto libre para nombres de observatorios; el web usa lista cerrada + "otro". Funcionalmente equivalente pero sesga hacia la lista — decidir si se mantiene.
- **P2-P5**: el original pedía "Cargo" como texto libre; el web usa select con categorías de vinculación (nombrado/contratista). Decisión de diseño, no de texto.

---

## CORRECCIÓN (2026-09-28): el Excel consolidado NO es el instrumento fiel

La restauración del 2026-09-22 tomó como "original" la columna "Pregunta" de
`Uso_Interno_Consolidado_ICED_2025.xlsx` (HojaMaestra). Comparación directa
contra el cuestionario FICED real (captura del instrumento, provista por el
usuario) muestra que **ese Excel abrevia las opciones**: el instrumento real
usa textos largos con cláusulas explicativas.

Ejemplo verificado — P10:

- **Instrumento real**: "Sí, participa activamente: el personal del organismo
  asiste y se involucra en todas las actividades disponibles, como cursos y
  talleres relacionados con la gestión y producción de información
  estadística." (y equivalentes largos para las opciones 2-4)
- **Excel consolidado**: "Participa activamente actividades de
  fortalecimiento de competencias estadísticas" (abreviado)
- **Dev/prod original**: parafraseo intermedio ("el organismo asiste y se
  involucra en todas las actividades de fortalecimiento disponibles")

**Acción:** P10 restaurado al texto del instrumento real en
`forms_iced.py` (`P10_CHOICES`). Valores '1'-'4' sin cambio → scoring intacto.

**Implicación:** todas las "restauraciones" del 2026-09-22 (P6, P11, P12,
P13, P14, P18, P21, P23, P24, P26-P32, P34, P36, P38, P41.1, P42) pueden
estar abreviadas igual si el Excel resume el cuestionario. Se requiere el
documento del instrumento oficial para una pasada literal completa — el
Excel consolidado ya no puede tratarse como fuente de fidelidad textual.

**Patrón adicional detectado:** el instrumento usa "el personal del
organismo" donde el web dice "el organismo" (P11 oficial visible en captura:
"…onal del organismo participa en instancias de coordinación"). Posible
acortamiento sistemático del sujeto en los enunciados.
