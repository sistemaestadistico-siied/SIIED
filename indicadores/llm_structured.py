"""
Schemas y system prompts para respuestas estructuradas del LLM.

Punto de extensión: cada nuevo uso (noticias, eventos, metadata, etc.)
agrega aquí su JSON Schema + prompt, y la vista correspondiente llama
a ChatService.generate_structured(prompt_usuario, SCHEMA, system_prompt=...).
"""

# ---------------------------------------------------------------------------
# NoticiaBanner (editorial) — el formulario tiene muchos campos que el
# operario normalmente no llena; el LLM los redacta todos y el humano revisa.
# ---------------------------------------------------------------------------

NOTICIA_SCHEMA = {
    'type': 'object',
    'properties': {
        'titulo': {
            'type': 'string',
            'description': 'Titular llamativo y periodístico, máx. 80 caracteres',
        },
        'subtitulo': {
            'type': 'string',
            'description': 'Bajada/entradilla de una línea que amplía el titular',
        },
        'descripcion': {
            'type': 'string',
            'description': 'Cuerpo completo de la noticia, 3 a 5 párrafos '
                           'separados por doble salto de línea',
        },
        'enlace_principal': {
            'type': 'string',
            'description': 'URL del enlace principal si aplica; cadena vacía '
                           'si no hay',
        },
        'texto_enlace_principal': {
            'type': 'string',
            'description': 'Texto del botón del enlace principal '
                           '(ej. "Leer informe", "Ver datos")',
        },
        'imagen_url': {
            'type': 'string',
            'description': 'URL de imagen SOLO si el usuario la proporcionó '
                           'en su prompt; en caso contrario cadena vacía',
        },
        'sugerencia_imagen': {
            'type': 'string',
            'description': 'Descripción de la imagen ideal para el carrusel '
                           'del home: horizontal 16:9 que se muestra como '
                           'banner sobre la tarjeta de la noticia — sujeto '
                           'centrado (se recorta con object-cover), sin texto '
                           'incrustado, tema y paleta sugeridos',
        },
        'orden': {
            'type': 'integer',
            'description': 'Prioridad editorial 0-10; mayor = más destacada. '
                           'Usa 5 si no hay indicación',
        },
        'estadisticas': {
            'type': 'array',
            'description': 'Cifras destacadas de la noticia (0 a 4)',
            'items': {
                'type': 'object',
                'properties': {
                    'titulo': {'type': 'string',
                               'description': 'Nombre corto de la cifra'},
                    'valor': {'type': 'string',
                              'description': 'El valor con unidad '
                                             '(ej. "45%", "12.300")'},
                    'descripcion': {'type': 'string'},
                    'orden': {'type': 'integer'},
                },
                'required': ['titulo', 'valor'],
                'additionalProperties': False,
            },
        },
        'enlaces': {
            'type': 'array',
            'description': 'Enlaces relacionados (0 a 4): informes, '
                           'catálogos, fuentes',
            'items': {
                'type': 'object',
                'properties': {
                    'titulo': {'type': 'string'},
                    'url': {'type': 'string'},
                    'descripcion': {'type': 'string'},
                    'orden': {'type': 'integer'},
                },
                'required': ['titulo', 'url'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['titulo', 'subtitulo', 'descripcion'],
    'additionalProperties': False,
}

# Identidad compartida con el chat: Don Datico es el asistente oficial del
# SIIED para audiencia y operadores. En las tareas estructuradas adopta
# roles profesionales (redactor jefe, documentalista...) sin perder nombre.
DONDATICO_IDENTITY = (
    'Eres Don Datico, asistente oficial de IA del Sistema Integrado de '
    'Información Estadística Distrital (SIIED) de Santiago de Cali. '
)

NOTICIA_SYSTEM_PROMPT = (
    DONDATICO_IDENTITY +
    'En esta tarea actúas como redactor jefe del portal de datos. Tu trabajo es tomar '
    'las instrucciones del operador editorial y producir una noticia completa '
    'y lista para publicar: titular periodístico, bajada, cuerpo bien '
    'redactado en español neutro con tono institucional pero ágil, cifras '
    'destacadas como estadísticas cuando el texto las mencione, y enlaces '
    'relacionados plausibles SOLO si el operador los dio o son internos '
    'obvios del portal (no inventes URLs externas; si dudas, deja el array '
    'vacío). Para la imagen piensa en el slot del carrusel del home: '
    'banner horizontal 16:9 sobre la tarjeta — peso liviano, sujeto '
    'centrado, sin texto incrustado. Nunca inventes cifras que el '
    'operador no mencionó: si no hay datos concretos, deja "estadisticas" '
    'vacío antes que fabricar números.'
)


# ---------------------------------------------------------------------------
# Metadata de indicador (recolección) — el operario describe el indicador en
# lenguaje natural y Don Datico redacta los campos MSD/SDMX del formulario.
# Los nombres de propiedad coinciden con los name="" del template
# cargar_metadata_form.html (y con las claves del xlsx de metadata).
# ---------------------------------------------------------------------------

METADATA_SCHEMA = {
    'type': 'object',
    'properties': {
        'Nombre_Indicador': {
            'type': 'string',
            'description': 'Nombre oficial del indicador, claro y conciso',
        },
        'Sigla': {
            'type': 'string',
            'description': 'Sigla o abreviatura usual (ej. TMI, IPM). Vacío '
                           'si no se infiere con seguridad',
        },
        'Grupo_Indicador': {
            'type': 'string',
            'description': 'Grupo/sistema al que pertenece (ej. ICET, SIIET). '
                           'Vacío si no se menciona',
        },
        'Descripcion_Indicador': {
            'type': 'string',
            'description': 'Descripción formal del indicador: qué mide, para '
                           'qué sirve y cómo se interpreta. 2-4 oraciones en '
                           'español institucional',
        },
        'Metodo_Medicion': {
            'type': 'string',
            'description': 'Método de medición/cálculo en prosa: cómo se '
                           'obtiene el numerador y denominador, agregaciones '
                           'y tratamiento de datos',
        },
        'Formula': {
            'type': 'string',
            'description': 'Fórmula matemática del indicador si se infiere '
                           '(ej. "TMI = (defunciones <1 año / nacidos vivos) '
                           '× 1.000"). Vacío si no aplica',
        },
        'Variables': {
            'type': 'string',
            'description': 'Variables o desagregaciones que componen el '
                           'indicador, separadas por coma (ej. "edad, sexo, '
                           'comuna")',
        },
        'Nombre_Conjunto_conjunto_datos': {
            'type': 'string',
            'description': 'Nombre sugerido del conjunto de datos '
                           '(ej. "Encuesta de Calidad de Vida 2024"). Vacío '
                           'si no se puede inferir',
        },
        'Unidad_Medida': {
            'type': 'string',
            'description': 'Unidad de medida del resultado: %, tasa por '
                           '100.000 hab., índice, pesos, etc.',
        },
        'Fuente_Datos': {
            'type': 'string',
            'description': 'Fuente primaria de los datos (encuesta, registro '
                           'administrativo, sistema de información)',
        },
        'Operacion_Estadistica': {
            'type': 'string',
            'description': 'Nombre de la operación estadística que produce '
                           'los datos (ej. "Encuesta de Calidad de Vida", '
                           '"Registro Civil de Defunciones")',
        },
        'Nomenclaturas_Clasificaciones': {
            'type': 'string',
            'description': 'Nomenclaturas/clasificaciones usadas (ej. CIE-10, '
                           'DIVIPOLA, CIIU). Vacío si no se mencionan',
        },
        'Alcance_Tematico': {
            'type': 'string',
            'description': 'Alcance temático: áreas/dimensiones que cubre '
                           'el indicador',
        },
        'Poblacion_Objetivo': {
            'type': 'string',
            'description': 'Población a la que refiere el indicador '
                           '(ej. "Residentes de Santiago de Cali", '
                           '"Menores de 5 años")',
        },
        'Cobertura_Geografica': {
            'type': 'string',
            'description': 'Cobertura geográfica (ej. "Santiago de Cali, '
                           'desagregado por comuna")',
        },
        'Periodo_Referencia': {
            'type': 'string',
            'description': 'Periodo al que refieren los datos (ej. "2024", '
                           '"2020-2024")',
        },
        'Periodo_Base': {
            'type': 'string',
            'description': 'Año o periodo base si es un índice. Vacío si '
                           'no aplica',
        },
        'Serie_Historica_Disponible': {
            'type': 'string',
            'description': 'Rango de la serie disponible (ej. "2010-2024"). '
                           'Vacío si no se menciona',
        },
        'Frecuencia_Difusion': {
            'type': 'string',
            'enum': ['Diaria', 'Semanal', 'Mensual', 'Bimensual',
                     'Trimestral', 'Semestral', 'Anual', 'Bienal',
                     'Quinquenal', 'A demanda'],
            'description': 'Periodicidad de publicación; elegir la más '
                           'plausible según la descripción',
        },
        'Medios_Difusion': {
            'type': 'string',
            'description': 'Canales de difusión (default razonable: '
                           '"Portal SIIED, internet")',
        },
        'Referencias': {
            'type': 'string',
            'description': 'Referencias metodológicas o normativas '
                           'mencionadas por el operador. Vacío si no hay',
        },
        'Comentarios_Adicionales': {
            'type': 'string',
            'description': 'Notas o salvedades relevantes no cubiertas por '
                           'otros campos. Vacío si no aplica',
        },
    },
    'required': ['Descripcion_Indicador', 'Unidad_Medida'],
    'additionalProperties': False,
}

METADATA_SYSTEM_PROMPT = (
    DONDATICO_IDENTITY +
    'En esta tarea actúas como documentalista estadístico experto en '
    'metadatos de indicadores (estándar MSD/SDMX colombiano). El operador '
    'de recolección te describe un indicador en lenguaje natural — a veces '
    'de forma incompleta o desordenada — y tú produces la metadata formal '
    'del formulario. Reglas: redacción institucional en tercera persona, '
    'sin primera persona ni muletillas; los campos que no puedas inferir '
    'con seguridad déjalos vacíos antes que inventar; las fórmulas usa '
    'notación clara (V₁/V₂ o palabras); Frecuencia_Difusion debe ser una '
    'de las opciones válidas; si el operador da el nombre de un indicador '
    'existente del SIIED, respétalo. Nunca inventes cifras, periodos ni '
    'fuentes que el operador no mencionó o no sean deducibles del contexto.'
)
