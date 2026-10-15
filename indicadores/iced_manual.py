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
        'titulo': 'A. Identificación del organismo (P1-P5)',
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
            'El cargo debe describir el rol de la persona '
            '(ej: "Profesional especializado en estadística").',
        ],
        'errores_comunes': [
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
            'P8/P9 (herramientas de planificación): marque la herramienta '
            '(PEI, Plan de Acción, PMD...) y complete el documento y la '
            'sección donde aparece la actividad estadística.',
            'P10 (capacitación): si responde opciones 1-3, la tabla de '
            'actividades es obligatoria: actividad, fecha (selector de '
            'calendario) y organismo encargado.',
            'P7 (procedimientos): el widget MOP muestra la estructura de '
            'Manuales de Operación conocidos; marque los que apliquen y '
            'complete la información solicitada.',
            'Las descripciones tienen un máximo de 2000-3000 caracteres.',
        ],
        'errores_comunes': [
            'Marcar una herramienta en P8/P9 sin indicar documento '
            'y sección.',
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
            'P13-P14: marque todas las herramientas que USE de verdad; '
            '"Otros" exige escribir cuál.',
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
            'P19: cada fila es una persona. Complete nombre, correo '
            'válido, teléfono (10 dígitos o +57), años de experiencia '
            '(número), inicio de participación en formato MM/AAAA '
            '(ej: 03/2024).',
            'Tipo de vinculación y nivel de formación se eligen de las '
            'listas desplegables.',
            'Etapas del proceso: marque en cuáles participa la persona '
            '(puede ser varias).',
            'Si no existe equipo dedicado (P18="No"), puede indicarlo '
            'y la tabla queda vacía.',
        ],
        'errores_comunes': [
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
            'P23: una fila por operación estadística. Marque los '
            'documentos metodológicos existentes (ficha, manual, '
            'diccionario, consistencia) y escriba las acciones de '
            'fortalecimiento.',
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
            'y complete las subpreguntas 28.1/28.2 según lo marcado.',
            'P29 (políticas públicas): si el organismo es líder '
            '(opción 1), responda metodología, frecuencia, medios de '
            'divulgación y acciones de seguimiento.',
            'P30: seleccione los lineamientos MOP de la Alcaldía que '
            'implementa y describa brevemente cada uno.',
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
            'verdad; la evidencia (URL y descripción de productos) debe '
            'ser consistente con ese nivel.',
            'La URL de evidencia debe ser completa '
            '(https://...) y verificable.',
            'P31.1 (frecuencia de uso) solo aplica si usa modelos '
            'avanzados.',
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
            'Observatorios del organismo o en los que participa, su '
            'información y documentación metodológica.'
        ),
        'tips': [
            'P33: si tiene observatorio propio, selecciónelo de la lista '
            'o escríbalo en "Otro".',
            'P34: una fila por observatorio — nombre, fecha de creación '
            '(selector de calendario), tema, área temática, si tiene '
            'documentos MOP y cuáles produce.',
            'P35 (documentación): tipo, nombre, código MOP, URL y '
            'descripción son obligatorios por fila que empiece a '
            'diligenciar; la URL debe ser válida.',
        ],
        'errores_comunes': [
            'Filas de P35 con URL inválida o campos vacíos.',
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
            'P36/P39/P40: las URLs de evidencia se validan una por una; '
            'varias se separan por coma y deben ser completas '
            '(https://...).',
            'P38: si marca "Ninguna", las preguntas de difusión se '
            'omiten (y P41 no aplica).',
            'P41.2 (matriz de satisfacción): por cada indicador marque '
            'el nivel de satisfacción y pegue las URLs de las '
            'mediciones.',
            'P42 es de observaciones generales (máx. 4000 caracteres); '
            'úslelo para aclarar respuestas, no para repetirlas.',
        ],
        'errores_comunes': [
            'Pegar rutas internas o nombres de archivo en vez de URLs '
            'públicas.',
            'Responder "indaga satisfacción = sí" sin completar la '
            'matriz P41.2.',
        ],
    },
    'revision': {
        'titulo': 'Revisión y Envío',
        'resumen': (
            'Resumen de todas las respuestas antes de enviar a '
            'validación. Revise cada sección desplegable.'
        ),
        'tips': [
            'Si una sección dice "no tiene respuestas diligenciadas", '
            'use «Anterior» para volver y completarla — los pasos vacíos '
            'pueden ser causa de devolución.',
            'Al confirmar el envío el formulario pasa al equipo '
            'validador del SIIED; mientras esté enviado no se puede '
            'editar.',
            'Si el validador devuelve el formulario, sus observaciones '
            'aparecen al retomar el FICED.',
        ],
        'errores_comunes': [
            'Enviar sin revisar pasos con respuestas vacías.',
            'Pensar que el envío es editable: solo un validador puede '
            'devolverlo para corrección.',
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
