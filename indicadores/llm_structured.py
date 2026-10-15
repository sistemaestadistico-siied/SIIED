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
