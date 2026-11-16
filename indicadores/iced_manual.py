"""
Manual focalizado del FICED — guía breve por cada paso del wizard.

Cada entrada resume qué pide la sección, consejos prácticos por pregunta y
los errores más comunes (incluidas las reglas de formato estrictas de la
Fase 1). `manual_texto_paso` devuelve la sección como texto plano para el
chat asistente de Don Datico (Fase 3).

Las claves coinciden con ICED_WIZARD_FORMS / ICED_STEP_LABELS en
forms_iced.py.
"""

MANUAL_POR_PASO = {
    'identificacion': {
        'titulo': 'A. Identificación del organismo (P1 y contactos)',
        'resumen': (
            'Datos de contacto del organismo. El nombre se pre-llena '
            'automáticamente; aquí se registran las personas de contacto '
            'para el ejercicio FICED.'
        ),
        'tips': [
            'Registre al menos UNA persona de contacto; puede agregar '
            'todas las que necesite con el botón "Agregar persona".',
            'Correo electrónico: formato nombre@dominio.com '
            '(ej: nombre@cali.gov.co). Se valida automáticamente.',
            'Teléfono: máximo 10 dígitos, o 12 si usa prefijo +57 '
            '(ej: 3001234567 o +573001234567). Sin letras ni extensión.',
            'Por persona son obligatorios: nombre completo, tipo de '
            'vinculación, cargo y correo. El cargo se elige de la lista, '
            'que cambia según el tipo de vinculación (nombrado o '
            'contratista); el teléfono es opcional.',
        ],
        'errores_comunes': [
            'Dejar el cargo en "— Seleccione —" (al cambiar el tipo de '
            'vinculación el cargo se reinicia y hay que elegirlo de '
            'nuevo).',
            'Correos sin "@" o sin dominio.',
            'Teléfonos con extensión o texto ("3001234567 ext 123" '
            '→ registre solo 3001234567).',
            'Dejar la tabla de personas vacía.',
        ],
    },
    'entorno': {
        'titulo': 'B. Entorno Institucional (P6-P12)',
        'resumen': (
            'Marco institucional: funciones estadísticas del organismo, '
            'procedimientos documentados (MOP), herramientas de '
            'planificación, capacitación y mecanismos de trazabilidad.'
        ),
        'tips': [
            'P8/P9 (herramientas de planificación/mejoramiento): marque '
            'cada herramienta que aplique (Planes de trabajo, Planes de '
            'acción, Programas, Proyectos) e indique, obligatoriamente, '
            'el documento con su sección o actividad; use "+ Agregar" '
            'si son varios documentos. Si ninguna aplica, marque "No se '
            'incluyen" (no pide documento).',
            'P11 (instancias de coordinación): por cada tipo de '
            'instancia marcado escriba las instancias internas y/o '
            'externas — basta con una de las dos columnas, pero no '
            'ambas vacías. Si no participa, marque "No participa".',
            'P10 (capacitación): si responde opciones 1-3, la tabla de '
            'actividades es obligatoria: actividad, fecha (selector de '
            'calendario) y organismo encargado.',
            'P7 (procedimientos): el widget MOP muestra la estructura de '
            'Manuales de Operación conocidos; marque los que apliquen y '
            'complete la información solicitada.',
            'Las descripciones admiten textos largos (hasta 10.000 '
            'caracteres según el campo); sea concreto y cite documentos '
            'y secciones.',
        ],
        'errores_comunes': [
            'Dejar P8/P9 sin filas y sin marcar "No se incluyen" '
            '(una de las dos es obligatoria).',
            'Marcar una herramienta en P8/P9 sin indicar documento '
            'y sección.',
            'P11: marcar una instancia y dejar vacías tanto internas '
            'como externas.',
            'Responder "sí participa" en P10 y dejar la tabla de '
            'actividades vacía.',
            'P12: elegir un nivel de trazabilidad que no coincide con '
            'la descripción escrita.',
        ],
    },
    'infraestructura_c1': {
        'titulo': 'C1. Herramientas tecnológicas (P13-P17)',
        'resumen': (
            'Herramientas de procesamiento, gestores de bases de datos, '
            'herramientas de visualización y tableros/reportes '
            'publicados.'
        ),
        'tips': [
            'P13-P14-P15.1: marque todas las herramientas que USE de '
            'verdad; "Otro(s)" y "Desarrolladas por el organismo" '
            'exigen escribir cuál.',
            'Si en P15 responde que Sí usa herramientas de '
            'visualización, P16 es obligatoria: al menos un reporte con '
            'nombre y URL.',
            'P16 (reportes/tableros): incluya la URL de cada reporte. '
            'Las URLs deben tener formato completo '
            '(https://sitio.com/ruta); varias se separan por coma.',
            'P17 califica la suficiencia de las herramientas: responda '
            'según la realidad, no la aspiración.',
        ],
        'errores_comunes': [
            'URLs sin https:// o incompletas en P16.',
            'Marcar "Otros" sin especificar la herramienta.',
        ],
    },
    'infraestructura_c2': {
        'titulo': 'C2. Recurso Humano (P18-P20)',
        'resumen': (
            'Equipo que produce información estadística: tabla de '
            'personas con su vinculación, experiencia y etapas del '
            'proceso en que participan.'
        ),
        'tips': [
            'P19 es obligatoria si P18 es 1, 2 o 3: registre al menos '
            'una persona. Cada tarjeta es una persona.',
            'Por persona son obligatorios: nombre completo, categoría '
            'del cargo, nivel de formación, inicio de participación '
            '(MM/AAAA, ej: 03/2024), si sus funciones describen '
            'actividades estadísticas (Sí/No) y al menos una etapa del '
            'proceso.',
            'Correo, teléfono (10 dígitos o +57), grupo y años de '
            'experiencia (número) son opcionales, pero si se escriben '
            'deben tener formato válido.',
            'Si no existe persona ni grupo dedicado (P18 opción 4), la '
            'tabla se oculta y el flujo pasa directo a la P20.',
        ],
        'errores_comunes': [
            'P18 en opción 1-3 y P19 sin personas, o tarjetas '
            'agregadas y dejadas en blanco.',
            'No marcar ninguna etapa del proceso en una persona.',
            'Inicio de participación en formatos distintos a MM/AAAA.',
            'Años de experiencia con texto ("cinco" → use 5).',
            'Correos institucionales incompletos.',
        ],
    },
    'infraestructura_c3': {
        'titulo': 'C3. Recursos Financieros (P21-P22)',
        'resumen': (
            'Distribución PORCENTUAL del presupuesto anual del organismo '
            'en hardware, software y personal/capacitación para la '
            'actividad estadística.'
        ),
        'tips': [
            'Todos los valores de P21 son PORCENTAJES de 0 a 100 '
            '(ej: 25.5 significa 25.5% del presupuesto anual).',
            'La suma de todos los rubros NO puede superar 100%. '
            'Si no hay gasto en un rubro, deje 0.',
            'No escribir el símbolo % ni el valor en pesos: solo el '
            'número.',
            'P22 califica la suficiencia de los recursos: sea realista, '
            'la calificación contrasta con lo reportado en P21.',
        ],
        'errores_comunes': [
            'Escribir pesos en vez de porcentajes (50000000 → error).',
            'Que los rubros sumen más de 100%.',
            'Valores negativos o mayores a 100 por rubro.',
        ],
    },
    'metodologia_d1': {
        'titulo': 'D1. Operaciones Estadísticas (P23-P25)',
        'resumen': (
            'Las operaciones estadísticas del organismo y sus insumos '
            'metodológicos: documentos, fichas, manuales, diccionarios; '
            'nomenclaturas y mecanismos para identificar necesidades.'
        ),
        'tips': [
            'P23: las operaciones estadísticas vienen precargadas y '
            'TODAS deben diligenciarse: en cada fila responda Vigente '
            '(solo Sí o No, no admite NA) y, '
            'si está vigente, Sí/No/NA en cada columna (documentos '
            'metodológicos, ficha, manual, diccionario, consistencia, '
            'acciones de fortalecimiento, SICODE). Si Vigente = NO, '
            'las columnas quedan en NA y la razón de no vigencia es '
            'obligatoria.',
            'P24/P24.1: seleccione nomenclaturas/estándares usados '
            '(CIUU, CIIU, DANE...) y de dónde provienen los conceptos.',
            'P25: si el organismo usa el Banco de Programas y Proyectos, '
            'escriba los códigos BP separados por coma '
            '(ej: 2023100012345) y la URL del proyecto si existe.',
            '"Especifique"/"Otro" tienen máximo 300 caracteres.',
        ],
        'errores_comunes': [
            'Códigos BP con texto o en formato libre.',
            'Operaciones estadísticas sin marcar ningún documento '
            'metodológico cuando sí existen.',
        ],
    },
    'metodologia_d2': {
        'titulo': 'D2. Indicadores y articulación (P26-P30)',
        'resumen': (
            'Cómo se estructura el análisis de indicadores, la '
            'articulación con otros organismos y el rol del organismo '
            'con las políticas públicas.'
        ),
        'tips': [
            'P26: "No aplica"/"No se realiza" no pueden combinarse con '
            'otras opciones.',
            'P27-P28 forman cadena: si existe articulación (opciones '
            '1-3), indique cómo se articulan (reuniones, metodología...) '
            'y complete las subpreguntas 28.1/28.2 según lo marcado '
            '(28.1 frecuencia de reuniones admite varias: Mensual, '
            'Bimensual, Trimestral, Cuatrimestral, Semestral, Anual).',
            'P29 (políticas públicas): si el organismo es líder '
            '(opción 1), responda metodología, frecuencia, medios de '
            'divulgación y acciones de seguimiento (29.2 frecuencia '
            'admite varias opciones).',
            'Todo "Otro (especifique)" marcado exige escribir el texto.',
            'P30: si marca "Lineamientos de la Alcaldía", agregue en '
            'la tabla una fila por lineamiento (máx. 10) eligiendo el '
            'código MOP de la lista; la descripción se completa sola.',
        ],
        'errores_comunes': [
            'Marcar articulación en P27 pero dejar P28 vacío.',
            'Combinar opciones excluyentes ("No aplica" + otras).',
            'Subpreguntas condicionales sin responder.',
        ],
    },
    'metodologia_d3': {
        'titulo': 'D3. Analítica de datos (P31-P32)',
        'resumen': (
            'Nivel de analítica del organismo (descriptiva, predictiva '
            'con IA/ML) y uso de las herramientas DATIC del SIIED.'
        ),
        'tips': [
            'P31: elija el nivel MÁS avanzado que el organismo usa de '
            'verdad. Con las opciones 2-5 la tabla de productos es '
            'obligatoria: al menos un producto con su URL de evidencia '
            '(una fila en blanco no cuenta).',
            'La URL de evidencia debe ser completa '
            '(https://...) y verificable.',
            'P31.1 (frecuencia de uso) aparece con las opciones 2-5 y '
            'admite varias frecuencias.',
            'P32: describa el caso de uso de analítica DATIC aunque sea '
            'potencial.',
        ],
        'errores_comunes': [
            'Declarar analítica predictiva sin URL de evidencia.',
            'URL rota o de página genérica sin evidencia del producto.',
        ],
    },
    'metodologia_d4': {
        'titulo': 'D4. Observatorios (P33-P35)',
        'resumen': (
            'Observatorios que el organismo lidera, su información y su '
            'documentación metodológica. P34 y P35 solo aparecen si en '
            'P33 responde que SÍ cuenta con observatorio.'
        ),
        'tips': [
            'P33: si responde "Sí", seleccione (obligatorio) hasta 3 '
            'observatorios del listado de referencia del distrito, o '
            'escriba otro en el campo "Otro"; P34 y P35 pasan a ser '
            'obligatorias. Si responde "No", la sección salta a la '
            'siguiente.',
            'P34: una fila por observatorio QUE LIDERA (máx. 5). '
            'Fecha de creación con el selector de calendario; al elegir '
            'el tema principal el área temática se autocompleta. Si '
            'marca que produce documentos, investigaciones y/o reportes, '
            '"¿Cuáles?" es obligatorio.',
            'P35 (documentación): por fila son obligatorios tipo, '
            'nombre y descripción, y además la URL y/o la codificación '
            'MOP — al menos una de las dos (si pone URL, debe ser '
            'válida).',
        ],
        'errores_comunes': [
            'Registrar en P34 observatorios en los que solo participa '
            '(son solo los que lidera el organismo).',
            'Marcar en P34 que produce documentos y dejar "¿Cuáles?" '
            'vacío.',
            'Filas de P35 sin URL ni codificación MOP, con URL inválida '
            'o con campos obligatorios vacíos.',
            'Fecha de creación escrita a mano en vez de usar el '
            'selector de calendario.',
        ],
    },
    'accesibilidad': {
        'titulo': 'E. Accesibilidad y Uso (P36-P42)',
        'resumen': (
            'Cómo se usan los indicadores, quiénes son los usuarios, '
            'medios de difusión, elementos web publicados y medición de '
            'satisfacción.'
        ),
        'tips': [
            'P36 y P37 son obligatorias: marque al menos una opción.',
            'P36/P40: la URL de evidencia es obligatoria en cada opción '
            'marcada; use "+ Agregar URL" para anexar más (todas '
            'completas, https://...).',
            'P37: la opción "No tiene ningún otro usuario de '
            'información" es una respuesta válida y excluyente — no se '
            'combina con las demás; en las opciones con "¿Cuál(es)?" '
            'el texto es obligatorio.',
            'P39: "Página web" y "Otro" exigen ¿cuál? y URL (las URLs '
            'se separan por coma).',
            'P38: si marca "No se realiza difusión — continúe en la '
            'pregunta 42", las preguntas 39, 40 y 41 se omiten por '
            'completo.',
            'P41.2 (matriz de satisfacción): marque el nivel de '
            'satisfacción en los 3 indicadores y relacione mínimo una '
            'URL de evidencia de las mediciones; con "+ Agregar URL" '
            'puede anexar más.',
            'P42 es de observaciones generales (máx. 4000 caracteres): '
            'anteponer el número de la pregunta al comentario (ej: '
            '"P10 — la capacitación fue en mayo"); si no hay '
            'observaciones, se deja en blanco.',
        ],
        'errores_comunes': [
            'Pegar rutas internas o nombres de archivo en vez de URLs '
            'públicas.',
            'Marcar "No se realiza difusión" junto con otros productos '
            '(la opción es excluyente).',
            'Marcar una opción en P36, P39 (web/otro) o P40 sin su '
            'URL.',
            'Responder "indaga satisfacción = sí" sin completar la '
            'matriz P41.2 (los 3 indicadores y al menos una URL).',
        ],
    },
    'revision': {
        'titulo': 'Revisión y Envío',
        'resumen': (
            'Resumen de todas las respuestas antes de enviar a '
            'validación. Revise cada sección desplegable.'
        ),
        'tips': [
            'El formulario se guarda como borrador: "Guardar borrador" '
            'lo registra en cualquier momento y al retomar el FICED se '
            'reanuda en el paso donde quedó.',
            'Si una sección dice "no tiene respuestas diligenciadas", '
            'use «Anterior» para volver y completarla — los pasos vacíos '
            'pueden ser causa de devolución.',
            'Al confirmar el envío el formulario pasa al validador de '
            'su organismo (recibe un correo de aviso); mientras esté '
            'enviado no se puede editar.',
            'El validador de su organismo puede devolver el formulario '
            'a su equipo con observaciones: llega un correo de aviso y '
            'las observaciones aparecen al retomar el FICED.',
        ],
        'errores_comunes': [
            'Enviar sin revisar pasos con respuestas vacías.',
            'Pensar que el envío es editable: solo el validador del '
            'organismo puede devolverlo para corrección.',
        ],
    },
}


def manual_texto_paso(step_key):
    """Sección del manual como texto plano (para el prompt del chat)."""
    m = MANUAL_POR_PASO.get(step_key)
    if not m:
        return ''
    lineas = [
        m['titulo'],
        m['resumen'],
        'CONSEJOS:',
    ]
    lineas += [f'- {t}' for t in m['tips']]
    lineas.append('ERRORES COMUNES:')
    lineas += [f'- {e}' for e in m['errores_comunes']]
    return '\n'.join(lineas)


def resumen_manual():
    """Índice breve de todas las secciones (contexto general del chat)."""
    return '\n'.join(
        f'{v["titulo"]}: {v["resumen"]}' for v in MANUAL_POR_PASO.values())
