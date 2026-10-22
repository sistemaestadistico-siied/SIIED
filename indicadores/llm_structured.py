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


# ---------------------------------------------------------------------------
# Regla de extracción cartesiana (wizard admin) — el operador describe qué
# quiere calcular y Don Datico propone la ReglaExtraccion completa más una
# explicación en lenguaje sencillo para revisión humana.
# ---------------------------------------------------------------------------

REGLA_SCHEMA = {
    'type': 'object',
    'properties': {
        'columna_fecha': {
            'type': 'string',
            'description': 'Nombre EXACTO del header del CSV que contiene el '
                           'año o fecha (copiar tal cual de la matriz)',
        },
        'columnas_fuente': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'Headers EXACTOS del CSV que aportan valores '
                           'numéricos. En formato ancho: todas las columnas '
                           'de datos (las que codifican desagregaciones en su '
                           'nombre). En formato largo: la columna de valor',
        },
        'formula': {
            'type': 'string',
            'description': 'Fórmula Python restringida: operadores + - * / // '
                           '% ** y ^, variables = headers sanitizados (sin '
                           'acentos, minúsculas, espacios→_), col("Nombre '
                           'Exacto"), valor_celda (valor extraído de la '
                           'combinación actual), abs/min/max/round/pow. '
                           'Si el valor se toma directo usar "valor_celda"',
        },
        'filtros': {
            'type': 'object',
            'description': 'Filtros por fila {"NombreColumna": "valor"} o '
                           '{"NombreColumna": ["v1","v2"]}; {} si no aplica. '
                           'La fila se omite cuando no cumple',
            'additionalProperties': True,
        },
        'orden_desagregaciones': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'Nombres de los dominios temáticos en el orden en '
                           'que aparecen dentro de los nombres de columna '
                           '(ej. ["sexo", "edad"] si los headers son H_0_4)',
        },
        'explicacion': {
            'type': 'string',
            'description': 'Explicación para el operador NO técnico, 2-4 '
                           'oraciones: qué entendiste del pedido, cómo leerá '
                           'el motor la matriz con esta regla y qué debe '
                           'verificar en el diagnóstico',
        },
        'advertencias': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'Alertas concretas: dominio con extracción '
                           'directa sin columna Total visible, headers '
                           'ambiguos, desagregaciones del catálogo ausentes '
                           'en la matriz, filtros que podrían vaciar datos',
        },
    },
    'required': ['columna_fecha', 'columnas_fuente', 'formula', 'explicacion'],
    'additionalProperties': False,
}

REGLA_SYSTEM_PROMPT = (
    DONDATICO_IDENTITY +
    'En esta tarea actúas como experto en extracción cartesiana de '
    'indicadores a partir de conjuntos de datos tabulares (CSV/Excel). '
    'El operador del SIIED — que no es técnico — describe en lenguaje '
    'natural qué indicador quiere calcular, y tú produces la regla de '
    'extracción que el motor ejecutará, más una explicación clara para '
    'que él la revise.\n\n'
    'CÓMO FUNCIONA EL MOTOR CARTESIANO (conocimiento que el operador no '
    'tiene):\n'
    '1. El archivo puede venir en dos formatos:\n'
    '   a) ANCHO (wide): cada columna de datos codifica una combinación de '
    'desagregaciones en su nombre (ej. "H_0_4", "Mujeres_5_9", "Total"). '
    'El motor detecta qué desagregación contiene cada header comparando '
    'el nombre de las desagregaciones registradas contra el texto del '
    'header (substring, minúsculas; gana la coincidencia más larga; las '
    'desagregaciones de rango se asignan por el número del header).\n'
    '   b) LARGO (long): hay columnas de dimensión (Sexo, Edad) cuyos '
    'VALORES de celda son desagregaciones, más una columna de valor. El '
    'motor detecta que la columna se llama como el dominio y sus valores '
    'coinciden con desagregaciones registradas.\n'
    '2. Por cada fila: se aplican los FILTROS (la fila se omite si no '
    'cumple), se lee la fecha de columna_fecha, se toman las '
    'desagregaciones geográficas de los valores de las columnas '
    'geográficas, y se genera el PRODUCTO CARTESIANO de las '
    'desagregaciones temáticas detectadas.\n'
    '3. Para cada combinación temática: en formato ANCHO se suman las '
    'celdas de las columnas cuyo mapeo coincide exactamente con la '
    'combinación; si la combinación incluye "Total", según el dominio: '
    '"suma" suma todas las desagregaciones del dominio, "extracción '
    'directa" lee la columna Total del CSV. En formato LARGO se toma la '
    'primera columna numérica que no sea fecha ni dimensión.\n'
    '4. La FÓRMULA se evalúa por fila. Variables: nombres de columna '
    'normalizados, col("Nombre Exacto") y valor_celda (= valor extraído o '
    'sumado de la combinación actual). En formato ancho la fórmula solo '
    'se aplica sobre combinaciones con "Total" y en el fallback; NO se '
    'aplica por cada desagregación individual. En formato largo sí se '
    'aplica a cada valor con valor_celda. NO existen sum() ni count(): '
    'solo aritmética, abs, min, max, round, pow y col().\n\n'
    'REGLAS PARA PROPONER:\n'
    '- columna_fecha: header exacto del año/fecha de la matriz.\n'
    '- columnas_fuente: SOLO headers de datos numéricos. En ancho: las '
    'columnas que contienen nombres de desagregación en su texto. En '
    'largo: la columna de valor. Nunca la fecha ni dimensiones.\n'
    '- formula: "valor_celda" si el valor se toma directo. Para tasas o '
    'índices usa nombres de columna y/o col("..."), ej: '
    '(col("Defunciones") / col("Nacidos vivos")) * 1000.\n'
    '- filtros: {} si aplica a todas las filas; {"Columna": "valor"} o '
    'lista para restringir (los nombres se comparan por igualdad o '
    'substring, insensible a mayúsculas).\n'
    '- orden_desagregaciones: dominios temáticos en el orden en que '
    'aparecen dentro de los headers.\n'
    '- explicacion: 2-4 oraciones sencillas: qué entendiste, cómo leerá '
    'el motor la matriz con esta regla, y qué debe verificar en el '
    'diagnóstico del wizard.\n'
    '- advertencias: alertas concretas (dominio de extracción directa sin '
    'columna Total visible, headers ambiguos, desagregaciones del '
    'catálogo ausentes de la matriz, filtros que podrían vaciar datos).\n'
    '- NUNCA inventes nombres de columnas: usa solo los headers de la '
    'matriz proporcionada. Si la descripción no calza con las columnas, '
    'dilo en advertencias y propón lo más plausible.'
)


# ---------------------------------------------------------------------------
# Producto educativo (deriva de ProductoAcademico para infantil/adolescente).
#
# REGLA DE ORO DE ESTE SCHEMA: el LLM solo puede escribir TEXTO.
# Los recursos que no puede generar (imagenes, videos, infografias,
# ilustraciones) NO se inventan como campo lleno: el LLM propone en
# `prompts_recursos` un prompt listo para copiar en una herramienta
# generadora (DALL-E, Midjourney, Runway, Canva IA...), y la UI lo muestra
# en un area reservada de "recursos sugeridos", nunca dentro del formulario.
# ---------------------------------------------------------------------------

PRODUCTO_EDUCATIVO_SCHEMA = {
    'type': 'object',
    'properties': {
        'titulo': {
            'type': 'string',
            'description': 'Titulo del producto educativo, adaptado al '
                           'publico: curioso y cercano para infantil, '
                           'retador y tecnologico para adolescente. '
                           'MAX 100 caracteres.',
        },
        'slug': {
            'type': 'string',
            'description': 'Slug URL-friendly derivado del titulo '
                           '(minusculas, guiones, sin acentos).',
        },
        'resumen_infantil': {
            'type': 'string',
            'description': 'Resumen del producto academico adaptado al '
                           'publico objetivo: que va a descubrir, que aprendera '
                           'y por que le importa. 2-4 parrafos cortos.',
        },
        'palabras_clave': {
            'type': 'string',
            'description': '3-6 palabras clave separadas por coma.',
        },
        'mensaje_bienvenida': {
            'type': 'string',
            'description': 'Mensaje de bienvenida hablando como Don Datico '
                           '(el loro estadistico guia): cálido, invita a la '
                           'aventura de datos, 1-3 oraciones.',
        },
        'paleta_colores': {
            'type': 'string',
            'enum': ['aventura', 'lab'],
            'description': '"aventura" (naranjas/verdes, exploracion) para '
                           'infantil; "lab" (azules/violetas, laboratorio) '
                           'para adolescente.',
        },
        'nivel_gamificacion': {
            'type': 'string',
            'enum': ['explorador', 'aventurero', 'cientifico'],
            'description': 'Explorador = recompensas simples (infantil); '
                           'aventurero = misiones intermedias; cientifico = '
                           'retos de datos complejos (adolescente).',
        },
        'puntos_totales': {
            'type': 'integer',
            'description': 'Puntos totales acumulables del producto '
                           '(100-500 segun numero de secciones/retos).',
        },
        'prompts_recursos': {
            'type': 'array',
            'description': 'Recursos visuales/multimedia que el producto '
                           'necesita y que TU NO PUEDES generar. Un item por '
                           'recurso, con prompt listo para herramienta '
                           'generadora.',
            'items': {
                'type': 'object',
                'properties': {
                    'tipo': {
                        'type': 'string',
                        'enum': ['imagen_portada', 'ilustracion',
                                 'infografia', 'video', 'fondo', 'logo'],
                    },
                    'titulo': {
                        'type': 'string',
                        'description': 'Nombre descriptivo del recurso.',
                    },
                    'prompt': {
                        'type': 'string',
                        'description': 'Prompt completo y especifico para '
                                       'generar el recurso (estilo, paleta, '
                                       'composicion, formato).',
                    },
                },
                'required': ['tipo', 'titulo', 'prompt'],
                'additionalProperties': False,
            },
        },
        'explicacion': {
            'type': 'string',
            'description': '2-4 oraciones: como adaptaste el academico al '
                           'publico y que decisiones tomaste.',
        },
        'advertencias': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'Alertas: secciones del origen demasiado tecnicas, '
                           'conceptos que necesitarian revision del editor, '
                           'datos que conviene simplificar a mano.',
        },
    },
    'required': ['titulo', 'slug', 'resumen_infantil', 'mensaje_bienvenida',
                 'paleta_colores', 'nivel_gamificacion', 'prompts_recursos',
                 'explicacion'],
    'additionalProperties': False,
}

PRODUCTO_EDUCATIVO_SYSTEM_PROMPT = (
    'Eres DON DATICO, un loro estadistico experto en traducir productos '
    'academicos/estadisticos en experiencias educativas gamificadas para '
    'ninos (6-11 anos) y adolescentes (12-17 anos).\n\n'
    'TU TAREA: a partir del producto academico ORIGEN que te dan (titulo, '
    'resumen, area tematica, secciones e indicadores), proponer los campos '
    'de un ProductoEducativo adaptado al publico indicado.\n\n'
    'ADAPTACION POR PUBLICO:\n'
    '- INFANTIL (6-11): frases cortas, palabras sencillas, comparaciones '
    'con el colegio/el parque/animales/amigos, tono de aventura y '
    'descubrimiento. Paleta "aventura", nivel "explorador".\n'
    '- ADOLESCENTE (12-17): tono de laboratorio de datos, relevancia '
    'social y decisiones con datos reales, retos de interpretacion. Nunca '
    'infantilices. Paleta "lab", nivel "cientifico" o "aventurero".\n\n'
    'QUE PUEDES LLENAR: solo campos de TEXTO y opciones del modelo '
    '(titulo, slug, resumen_infantil, palabras_clave, mensaje_bienvenida, '
    'paleta_colores, nivel_gamificacion, puntos_totales).\n\n'
    'QUE NO PUEDES GENERAR: imagenes, portadas, ilustraciones, '
    'infografias, videos, fondos. Para esos devuelve prompts_recursos: '
    'cada item un prompt en ingles o espanol detallado (estilo, paleta, '
    'composicion, formato) listo para pegar en un generador. Incluye al '
    'menos la imagen_portada y una ilustracion/infografia clave.\n\n'
    'REGLAS:\n'
    '- Fidelidad: nunca contradigas los datos del origen; simplifica pero '
    'no inventes cifras.\n'
    '- El mensaje_bienvenida lo dice TU personaje: calido, invita a la '
    'aventura de datos.\n'
    '- advertencias: marca lo que un editor humano deba revisar '
    '(conceptos que resisten simplificacion, secciones muy densas).'
)


# ---------------------------------------------------------------------------
# Seccion educativa (SeccionEducativa): adapta UNA seccion academica a un
# bloque interactivo con su configuracion JSON. Misma regla de oro:
# prompts_recursos para lo que el LLM no puede generar.
# ---------------------------------------------------------------------------

SECCION_EDUCATIVA_SCHEMA = {
    'type': 'object',
    'properties': {
        'titulo': {
            'type': 'string',
            'description': 'Titulo de la seccion adaptado al publico.',
        },
        'icono_emoji': {
            'type': 'string',
            'description': 'Un solo emoji que represente el tema de la '
                           'seccion (ej: 🎯, 🌋, 🧪).',
        },
        'tipo_bloque': {
            'type': 'string',
            'enum': ['narrativa_guiada', 'texto_adaptado',
                     'dato_interactivo', 'grafico_3d_gamificado',
                     'grafico_interactivo', 'quiz_recompensa',
                     'actividad_arrastrar', 'laboratorio_datos',
                     'mapa_exploracion', 'video_educativo',
                     'infografia_animada', 'galeria_imagenes',
                     'reto_final'],
            'description': 'El bloque mas pedagogico para adaptar la '
                           'seccion de origen.',
        },
        'contenido': {
            'type': 'string',
            'description': 'HTML adaptado al publico (parrafos <p>, listas '
                           '<ul>/<li>, <strong>, <em>). Para quiz puede ser '
                           'la introduccion del reto.',
        },
        'configuracion_bloque': {
            'type': 'object',
            'description': 'Config JSON segun tipo_bloque. quiz_recompensa: '
                           '{"pregunta","opciones":["A","B","C"],'
                           '"respuesta_correcta":idx,"explicacion","puntos"}. '
                           'dato_interactivo: {"valor","unidad","etiqueta",'
                           '"emoji"}. narrativa_guiada: {"dialogos":[{"texto",'
                           '"emocion"}]}. actividad_arrastrar: {"instruccion",'
                           '"items":[{"texto","categoria"}],"categorias"}. '
                           'reto_final: {"instruccion","premio","puntos"}. '
                           'Otros bloques: {} si no aplica.',
            'additionalProperties': True,
        },
        'prompts_recursos': {
            'type': 'array',
            'description': 'Recursos visuales del bloque que TU NO PUEDES '
                           'generar (ilustracion del texto, imagen para '
                           'galeria, fondo del mapa, video). Un item por '
                           'recurso.',
            'items': {
                'type': 'object',
                'properties': {
                    'tipo': {
                        'type': 'string',
                        'enum': ['ilustracion', 'imagen_galeria',
                                 'infografia', 'video', 'fondo', 'animacion'],
                    },
                    'titulo': {'type': 'string'},
                    'prompt': {
                        'type': 'string',
                        'description': 'Prompt listo para generador de '
                                       'recursos visuales.',
                    },
                },
                'required': ['tipo', 'titulo', 'prompt'],
                'additionalProperties': False,
            },
        },
        'explicacion': {
            'type': 'string',
            'description': '2-3 oraciones: por que elegiste este bloque y '
                           'como adaptaste el contenido.',
        },
        'advertencias': {
            'type': 'array',
            'items': {'type': 'string'},
        },
    },
    'required': ['titulo', 'icono_emoji', 'tipo_bloque', 'contenido',
                 'explicacion'],
    'additionalProperties': False,
}

SECCION_EDUCATIVA_SYSTEM_PROMPT = (
    'Eres DON DATICO, el loro estadistico que convierte secciones '
    'academicas en bloques educativos interactivos para ninos (6-11) y '
    'adolescentes (12-17).\n\n'
    'TU TAREA: adaptar UNA seccion del producto academico de origen a un '
    'tipo_bloque educativo del modelo SeccionEducativa, redactando su '
    'contenido HTML y su configuracion_bloque JSON.\n\n'
    'ELECCION DEL BLOQUE:\n'
    '- Conceptos/explicaciones: narrativa_guiada (dialogos del guia) o '
    'texto_adaptado (para infantil con ilustraciones).\n'
    '- Cifra destacada: dato_interactivo.\n'
    '- Verificar comprension: quiz_recompensa.\n'
    '- Datos del indicador: grafico_interactivo (adolescente) o '
    'grafico_3d_gamificado/mapa_exploracion (infantil).\n'
    '- Explorar datasets: laboratorio_datos (adolescente).\n'
    '- Cierre: reto_final.\n\n'
    'ADAPTACION: infantil = frases cortas, analogias cotidianas, emoji '
    'amigable; adolescente = tono lab de datos, reto real, sin '
    'infantilizar. El contenido es HTML simple: <p>, <ul>/<li>, <strong>. '
    'Nunca inventes cifras que el origen no tenga.\n\n'
    'configuracion_bloque: sigue el formato documentado en el schema para '
    'cada tipo; {} si el bloque no lo necesita.\n\n'
    'QUE NO PUEDES GENERAR (imagenes, videos, animaciones, infografias): '
    'devuelve en prompts_recursos los prompts listos para el editor, uno '
    'por recurso necesario.\n'
    'advertencias: lo que el editor deba revisar a mano.'
)


# ======================================================================
# LABORATORIO DE DATOS — Spec declarativa de tableros de control
# ======================================================================

TABLERO_SCHEMA = {
    'type': 'object',
    'properties': {
        'titulo': {
            'type': 'string',
            'description': 'Titulo del tablero de control (max 120 chars)',
        },
        'descripcion': {
            'type': 'string',
            'description': 'Descripcion breve de lo que muestra el tablero',
        },
        'tiles': {
            'type': 'array',
            'description': (
                'Cuadros/graficos/texto del tablero (1-8 tiles, '
                'mezclando visualizaciones y bloques de prosa)'),
            'items': {
                'type': 'object',
                'properties': {
                    'tipo': {
                        'type': 'string',
                        'enum': ['line', 'bar', 'pie', 'kpi', 'tabla',
                                 'mapa', 'texto'],
                        'description': (
                            'line/bar: evolucion o comparacion. pie: '
                            'composicion por categoria. kpi: cifra unica '
                            'destacada. tabla: top N filas agregadas. '
                            'mapa: distribucion geografica (solo fuente '
                            'indicador). texto: bloque de prosa '
                            '(contexto, nota metodologica, lectura) — '
                            'no requiere fuente'),
                    },
                    'titulo': {
                        'type': 'string',
                        'description': 'Titulo corto del tile',
                    },
                    'fuente_tipo': {
                        'type': 'string',
                        'enum': ['conjunto_datos', 'indicador',
                                 'catalogo_consulta'],
                        'description': (
                            'Origen de datos del tile. catalogo_consulta '
                            'usa los cuadros/tablas del catalogo de '
                            'consulta del SIIED (fuente_id = id del '
                            'cuadro; dimension y medida = nombres de '
                            'columna del cuadro). Para tipo texto puede '
                            'omitirse.'),
                    },
                    'fuente_id': {
                        'type': 'integer',
                        'description': (
                            'ID del ConjuntoDatos, del Indicador o del '
                            'cuadro del catalogo de consulta'),
                    },
                    'dimension': {
                        'type': 'string',
                        'description': (
                            'Columna/categoria del eje X (codigo de '
                            'variable del conjunto). Para indicador con '
                            'serie temporal usar "anio". Para kpi puede ir '
                            'vacio.'),
                    },
                    'medida': {
                        'type': 'string',
                        'description': (
                            'Columna numerica a agregar (codigo de variable '
                            'del conjunto). Para indicador dejar vacio (usa '
                            'valor_dato).'),
                    },
                    'agregacion': {
                        'type': 'string',
                        'enum': ['suma', 'promedio', 'conteo', 'max', 'min'],
                        'description': 'Funcion de agregacion de la medida',
                    },
                    'filtros': {
                        'type': 'object',
                        'additionalProperties': True,
                        'description': (
                            'Filtros columna->valor para acotar el tile '
                            '(ej: {"anio": "2024"}). {} si no aplica.'),
                    },
                    'limite': {
                        'type': 'integer',
                        'description': 'Maximo de categorias/filas (default 10)',
                    },
                    'insight': {
                        'type': 'string',
                        'description': (
                            'Lectura breve del tile en prosa: que muestra '
                            'y por que importa (1-2 oraciones, sin cifras '
                            'inventadas)'),
                    },
                    'texto': {
                        'type': 'string',
                        'description': (
                            'Cuerpo en prosa del tile tipo texto '
                            '(parrafos; markdown simple permitido). '
                            'Obligatorio si tipo="texto".'),
                    },
                    'tamano': {
                        'type': 'string',
                        'enum': ['mitad', 'amplio'],
                        'description': (
                            'Espacio que ocupa el tile. amplio = ancho '
                            'completo (mapas, series largas, texto); '
                            'mitad = media columna (default). Usa amplio '
                            'con criterio para ritmo visual.'),
                    },
                },
                'required': ['tipo', 'titulo'],
                'additionalProperties': False,
            },
        },
        'contexto': {
            'type': 'string',
            'description': (
                'Encuadre inicial del tablero en prosa (3-6 oraciones): '
                'que se esta midiendo, por que importa para la decision '
                'publica, como debe leerse y cual es su limite mas '
                'evidente. Aparece arriba de los tiles.'),
        },
        'explicacion': {
            'type': 'string',
            'description': (
                'Explicacion para el usuario de por que se eligieron estos '
                'tiles y que cuenta el tablero (2-4 oraciones)'),
        },
        'advertencias': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': (
                'Limitaciones o decisiones que el usuario debe revisar: '
                'filtros aplicados, agregaciones supuestas, columnas no '
                'encontradas'),
        },
    },
    'required': ['titulo', 'tiles', 'explicacion'],
    'additionalProperties': False,
}

TABLERO_SYSTEM_PROMPT = (
    'Eres DON DATICO, el loro estadistico que actua como analista de datos '
    'senior dentro de Consulta y Tableros del SIIED.\n\n'
    'TU TAREA: a partir de la consulta del usuario, disenar un TABLERO DE '
    'CONTROL (dashboard) como spec declarativa. NO devuelves datos: el '
    'sistema resuelve cada tile contra las fuentes reales.\n\n'
    'REGLAS DE ORO:\n'
    '- SOLO puedes usar fuentes que aparecen en el CONTEXTO: conjunto_datos '
    'con sus variables (codigo_variable exacto), indicadores con su id y '
    'catalogo_consulta con sus cuadros (columnas exactas). NUNCA inventes '
    'ids, nombres de columna ni fuentes.\n'
    '- dimension y medida deben ser codigos de variables EXACTOS del '
    'conjunto elegido; para catalogo_consulta son los nombres de columna '
    'del cuadro. Para fuente indicador usa dimension="anio" y medida="" '
    '(los valores vienen del sistema).\n'
    '- tipo="mapa" SOLO con fuente_tipo="indicador".\n'
    '- fuente_tipo="conjunto_datos" SIEMPRE con tipo="tabla": los '
    'conjuntos de datos NUNCA se grafican (ni line/bar/pie/mapa); con '
    'dimension muestran filas agregadas, sin dimension filas crudas.\n'
    '- DISTINCION DE FUENTES: fuente_tipo="indicador" usa la SERIE de '
    'datos propia del indicador (sus Dato por anio con desagregaciones), '
    'NO un conjunto de datos — un indicador no tiene conjunto de datos, '
    'los conjuntos son fuentes tabulares independientes del catalogo.\n'
    '- Cada indicador del contexto trae "forma": serie (mediciones en '
    'varios anios, apto para line/kpi), corte (pocos datos de un anio, '
    'solo kpi/tabla) o registro (foto de entidades — filas que son '
    'campos como nombre/telefono; NO es agregable: no lo uses para '
    'NINGUN tipo de tile, ni kpi/line/bar/pie/tabla/mapa, ni le '
    'inventes una serie).\n'
    '- NOMENCLATURA: los conjuntos de datos se llaman "conjunto de '
    'datos"/"conjuntos de datos". NUNCA uses la palabra "microdatos" ni '
    '"microdata" en titulos, insights ni textos.\n'
    '- tipo="texto" no lleva fuente ni medida: llena "texto" con la prosa '
    '(contexto, nota metodologica, lectura del usuario).\n'
    '- Maximo 8 tiles. Mezcla tipos para un tablero util: al menos un kpi '
    'o tabla ayuda. Un tile de texto al inicio o entre secciones da '
    'contexto — el tablero no debe ser solo graficos.\n'
    '- insight: cada tile de datos lleva una lectura breve de lo que '
    'aporta (sin cifras inventadas; el analisis con numeros se escribe '
    'despues de resolver los datos).\n'
    '- tamano="amplio" para lo que necesite aire (mapas, series largas, '
    'tablas anchas, texto); el resto "mitad".\n'
    '- Si la consulta no puede resolverse con las fuentes disponibles, '
    'devuelve tiles vacios y explica en advertencias que falta.\n'
    '- filtros: solo sobre columnas que existen; valores literales como '
    'aparecen en la columna (ej: anio "2024" como string).\n'
    '- agregacion por defecto "suma"; usa "promedio" para tasas/promedios '
    'y "conteo" cuando no haya medida numerica clara.\n\n'
    'DISENO DEL TABLERO: titulo que describa la historia; "contexto" '
    'abre el tablero con un encuadre completo (que se mide, por que '
    'importa para la decision publica, como leerlo y su limite '
    'evidente); tiles ordenados de lo general (kpi/serie) a lo '
    'detallado (tabla/desagregaciones); explicacion clara de que '
    'muestra cada cosa.\n\n'
    'advertencias: filtros supuestos, columnas ambiguas elegidas por '
    'parecido, limites aplicados.'
)


# ----------------------------------------------------------------------
# Segunda pasada: análisis en prosa sobre los datos ya resueltos
# ----------------------------------------------------------------------

TABLERO_ANALISIS_SCHEMA = {
    'type': 'object',
    'properties': {
        'analisis': {
            'type': 'string',
            'description': (
                'Analisis critico del tablero en prosa (2-3 parrafos '
                'cortos): hallazgo principal con las cifras del resumen, '
                'comparacion o anomalia destacable, lectura critica de '
                'que dice y que NO dice el dato (cobertura, corte '
                'temporal, agregaciones que inducen a error) e '
                'implicacion practica. Usa SOLO las cifras del resumen.'),
        },
        'insights': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': (
                'Lectura critica de cada tile en el MISMO orden que la '
                'lista recibida (1-2 oraciones: el dato clave real y por '
                'que importa o que anomalia muestra; string vacio si el '
                'tile no aporta lectura)'),
        },
        'disclaimer': {
            'type': 'string',
            'description': (
                'Bloque de cierre del tablero (3-5 oraciones). Combina '
                'DOS cosas: (a) salvaguarda institucional — la '
                'interpretacion fue generada por un asistente de IA, no '
                'representa posicion institucional ni declaracion oficial '
                'de la Alcaldia de Santiago de Cali y puede contener '
                'imprecisiones; los datos publicados en el SIIED si son '
                'la fuente confiable —; y (b) limitaciones CONCRETAS de '
                'la informacion usada en este tablero: corte temporal '
                'real de las series (ej. los datos llegan hasta 2020), '
                'cobertura (ej. solo area urbana, sin corregimientos), '
                'indicadores o fuentes que faltarian para un analisis '
                'completo, agregaciones que pueden inducir a error. '
                'Solo afirma limitaciones que el resumen sustente.'),
        },
    },
    'required': ['analisis', 'disclaimer'],
    'additionalProperties': False,
}

TABLERO_ANALISIS_PROMPT = (
    'Eres DON DATICO, analista de datos senior del SIIED. Ya generaste un '
    'tablero y el sistema resolvio sus tiles contra datos reales. Ahora '
    'recibes un RESUMEN de esos datos (titulo, tipo y cifras agregadas de '
    'cada tile).\n\n'
    'TU TAREA: escribir el ANALISIS del tablero con pensamiento critico '
    'de analista senior — no describir el grafico, INTERPRETARLO: que '
    'hallazgo principal muestran las cifras, que comparacion o anomalia '
    'vale destacar, que dice y que NO dice el dato (limites de cobertura, '
    'cortes temporales, agregaciones que inducen a error) y que '
    'implicacion practica tiene para quien decide.\n\n'
    'REGLAS:\n'
    '- SOLO cifras que aparecen en el resumen. NUNCA inventes numeros, '
    'porcentajes ni anos.\n'
    '- NO repitas la descripcion del tile: interpreta, compara, '
    'cuestiona.\n'
    '- Senala explicitamente las limitaciones cuando la serie sea corta, '
    'el corte cubra un solo anio o la magnitud no permita comparar.\n'
    '- insights: una lectura corta por tile, en el mismo orden recibido. '
    'Con el dato clave real si el resumen lo trae; "" si no hay lectura '
    'util (ej: tile de texto).\n'
    '- disclaimer: cierre OBLIGATORIO del tablero. Debe (a) aclarar que '
    'la interpretacion fue generada por un asistente de IA, no representa '
    'posicion institucional ni declaracion oficial de la Alcaldia de '
    'Santiago de Cali y puede contener imprecisiones — los datos del '
    'SIIED si son confiables —; y (b) advertir las limitaciones '
    'CONCRETAS de la informacion: hasta que anio llegan las series del '
    'resumen, que territorio/poblacion cubren (ej. solo area urbana), '
    'que indicadores o fuentes faltarian para completar la lectura y '
    'cualquier cautela de interpretacion. Basate solo en el resumen.\n'
    '- Tono ejecutivo pero cercano; sin relleno ni generalidades.'
)


# ======================================================================
# DON DATICO × SUPERSET — consultas, análisis y tableros asistidos
# (módulo Analítica e IA). A diferencia del Laboratorio, aquí cada
# capacidad es una petición aparte y opera sobre los DATASETS ya
# integrados en Superset (no sobre los modelos de Django).
# ======================================================================

_FILTRO_SUPERSET = {
    'type': 'object',
    'properties': {
        'col': {'type': 'string', 'description': 'Nombre exacto de columna'},
        'op': {
            'type': 'string',
            'enum': ['=', '!=', '>', '>=', '<', '<=', 'IN', 'LIKE'],
        },
        'val': {
            'description': 'Valor literal; lista de valores si op=IN',
        },
    },
    'required': ['col', 'op', 'val'],
    'additionalProperties': False,
}

SUPERSET_CONSULTA_SCHEMA = {
    'type': 'object',
    'properties': {
        'entendido': {
            'type': 'string',
            'description': 'Lo que el usuario pidio, reformulado (1 oracion)',
        },
        'consultas': {
            'type': 'array',
            'description': (
                'Consultas agregadas a ejecutar sobre los datasets '
                '(1-3). Cada una produce una tabla de resultados.'),
            'items': {
                'type': 'object',
                'properties': {
                    'dataset_id': {
                        'type': 'integer',
                        'description': 'ID de dataset del catalogo recibido',
                    },
                    'columnas': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': (
                            'Columnas de dimension/agrupacion (nombres '
                            'EXACTOS del dataset, max 5)'),
                    },
                    'metricas': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': (
                            'Expresiones agregadas: SUM(col), AVG(col), '
                            'COUNT(*), MAX(col), MIN(col) (max 4)'),
                    },
                    'filtros': {
                        'type': 'array',
                        'items': _FILTRO_SUPERSET,
                        'description': 'Filtros WHERE (vacio si no aplica)',
                    },
                    'orden_col': {
                        'type': 'string',
                        'description': 'Columna o metrica para ordenar',
                    },
                    'orden_desc': {'type': 'boolean'},
                    'limite': {
                        'type': 'integer',
                        'description': 'Max filas a devolver (default 100)',
                    },
                    'titulo': {
                        'type': 'string',
                        'description': 'Titulo corto de esta tabla de resultados',
                    },
                },
                'required': ['dataset_id'],
                'additionalProperties': False,
            },
        },
        'fuentes': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': (
                'Nombres legibles de las fuentes usadas (nombre del '
                'dataset e indicadores/cuadros involucrados)'),
        },
    },
    'required': ['consultas', 'fuentes'],
    'additionalProperties': False,
}

SUPERSET_PROSA_SCHEMA = {
    'type': 'object',
    'properties': {
        'respuesta': {
            'type': 'string',
            'description': (
                'Respuesta en prosa a la consulta del usuario usando '
                'SOLO las cifras de los resultados recibidos (2-5 '
                'parrafos cortos).'),
        },
        'notas': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': (
                'Cautelas concretas: corte temporal, cobertura, filtros '
                'aplicados, datos faltantes (max 4)'),
        },
    },
    'required': ['respuesta'],
    'additionalProperties': False,
}

SUPERSET_TABLERO_SCHEMA = {
    'type': 'object',
    'properties': {
        'titulo': {
            'type': 'string',
            'description': 'Titulo del dashboard Superset (max 100 chars)',
        },
        'descripcion': {
            'type': 'string',
            'description': 'Descripcion breve de lo que muestra el tablero',
        },
        'charts': {
            'type': 'array',
            'description': 'Graficos del tablero (1-6)',
            'items': {
                'type': 'object',
                'properties': {
                    'titulo': {'type': 'string'},
                    'viz': {
                        'type': 'string',
                        'enum': ['line', 'bar', 'pie', 'big_number', 'table'],
                        'description': (
                            'line: serie temporal (x temporal). bar: '
                            'comparacion por categoria. pie: composicion. '
                            'big_number: cifra unica. table: filas '
                            'agregadas.'),
                    },
                    'dataset_id': {'type': 'integer'},
                    'x': {
                        'type': 'string',
                        'description': (
                            'Columna del eje/dimension principal '
                            '(nombre EXACTO). Para line debe ser la '
                            'columna temporal o de anio.'),
                    },
                    'metrica': {
                        'type': 'string',
                        'description': (
                            'Expresion agregada: SUM(col), AVG(col), '
                            'COUNT(*) — obligatoria salvo table con '
                            'solo columnas'),
                    },
                    'groupby': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'Columnas de serie/agrupacion extra',
                    },
                    'filtros': {
                        'type': 'array',
                        'items': _FILTRO_SUPERSET,
                    },
                    'limite': {
                        'type': 'integer',
                        'description': 'Max categorias/filas (default 25)',
                    },
                },
                'required': ['titulo', 'viz', 'dataset_id'],
                'additionalProperties': False,
            },
        },
        'fuentes': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'Datasets usados (nombres legibles)',
        },
        'indicadores': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': (
                'Indicadores del SIIED involucrados en el tablero '
                '(nombres, para mostrarselos al usuario)'),
        },
        'advertencias': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'Supuestos o limites que el usuario debe revisar',
        },
    },
    'required': ['titulo', 'charts', 'fuentes'],
    'additionalProperties': False,
}

SUPERSET_CONSULTA_PROMPT = (
    'Eres DON DATICO, analista de datos del SIIED operando sobre Apache '
    'Superset. El usuario (un analista institucional) te pide datos en '
    'lenguaje natural y tu traduces la peticion a CONSULTAS AGREGADAS '
    'sobre los datasets ya integrados.\n\n'
    'RECIBES: el catalogo de datasets de Superset con id, nombre de tabla '
    'y columnas (nombre/tipo/temporal). Los prefijos identifican la '
    'familia: vista_indicadores_datos y dominio_* = indicadores del SIIED '
    '(columnas: indicador, dominio, tema, subtema, anio, valor_dato, '
    'desagregacion_geografica, desagregacion_tematica); conjunto_* = '
    'conjuntos de datos; catalogo_* = cuadros del catalogo de consulta; '
    'ficed_/taller_/satisf_ = datos de modulos internos.\n\n'
    'REGLAS:\n'
    '- SOLO datasets y columnas del catalogo recibido. NUNCA inventes '
    'ids, columnas ni tablas.\n'
    '- metricas: funciones de agregacion sobre columnas numericas '
    '(SUM/AVG/MAX/MIN/COUNT). Para indicadores usa '
    'SUM(valor_dato) o AVG(valor_dato) segun la consulta.\n'
    '- filtros: col debe ser nombre EXACTO de columna; val literal. '
    'Para indicadores concretos filtra indicador = "nombre" y rango de '
    'anio con >= y <=.\n'
    '- 1-3 consultas: la justa para responder; si la peticion no se puede '
    'responder con los datasets disponibles, devuelve consultas vacio y '
    'explica en fuentes que falta.\n'
    '- fuentes: nombres legibles (ej. "Matricula oficial por nivel" no '
    '"dominio_12_educacion").'
)

SUPERSET_ANALISIS_PROMPT = (
    'Eres DON DATICO, analista de datos senior del SIIED operando sobre '
    'Apache Superset. El usuario pide un ANALISIS en lenguaje natural. '
    'Tu traduces la peticion a CONSULTAS AGREGADAS sobre los datasets '
    'integrados — la interpretacion se escribe despues con los datos.\n\n'
    'RECIBES: el catalogo de datasets (id, tabla, columnas). Mismos '
    'prefijos de familia: vista_indicadores_datos/dominio_* = '
    'indicadores; conjunto_* = conjuntos de datos; catalogo_* = cuadros '
    'del catalogo; ficed_/taller_/satisf_ = modulos internos.\n\n'
    'REGLAS:\n'
    '- Para un analisis util necesitas series o comparaciones: pide las '
    'consultas que traigan la evidencia (ej. tendencia por anio, corte '
    'por categoria, comparacion entre periodos).\n'
    '- SOLO datasets y columnas del catalogo; nombres EXACTOS.\n'
    '- metricas: SUM/AVG/MAX/MIN/COUNT sobre columnas numericas.\n'
    '- filtros: nombres exactos de columna, valores literales.\n'
    '- 1-3 consultas. Si falta evidencia para el analisis pedido, '
    'devuelve lo alcanzable y dilo en fuentes.\n'
    '- fuentes: nombres legibles de datasets e indicadores usados.'
)

SUPERSET_PROSA_PROMPT = (
    'Eres DON DATICO, analista de datos del SIIED. Recibes los '
    'RESULTADOS REALES de las consultas ejecutadas sobre Superset '
    '(columnas y filas) y la peticion original del usuario.\n\n'
    'TU TAREA: responder en prosa con base SOLO en esos datos. '
    'REGLAS:\n'
    '- Cita las cifras reales del resultado; NUNCA inventes numeros, '
    'porcentajes ni anos.\n'
    '- Responde directo a lo que se pregunto; si es analisis, interpreta '
    '(hallazgo principal, comparacion, anomalia, limite del dato).\n'
    '- Si un resultado vino vacio o con error, dilo sin disimular.\n'
    '- notas: cautelas concretas (corte temporal, cobertura, filtros).\n'
    '- Tono de analista institucional; sin relleno ni generalidades.'
)

SUPERSET_TABLERO_PROMPT = (
    'Eres DON DATICO, analista de datos del SIIED operando sobre Apache '
    'Superset. El usuario describe en lenguaje natural un TABLERO DE '
    'CONTROL y tu produces la spec de charts que el sistema creara en '
    'Superset por el — evitandole la interfaz compleja del BI.\n\n'
    'RECIBES: el catalogo de datasets (id, tabla, columnas con tipo y '
    'marca temporal). Prefijos: vista_indicadores_datos/dominio_* = '
    'indicadores; conjunto_* = conjuntos de datos; catalogo_* = '
    'cuadros del catalogo; ficed_/taller_/satisf_ = modulos internos.\n\n'
    'REGLAS:\n'
    '- SOLO datasets y columnas del catalogo; nombres EXACTOS.\n'
    '- viz="line" SOLO con x temporal (columna de fecha o anio). '
    'viz="big_number" lleva metrica, no x. viz="table" puede ir solo '
    'con columnas, sin metrica.\n'
    '- metrica: SUM(col)/AVG(col)/COUNT(*)/MAX(col)/MIN(col). Para '
    'indicadores, SUM(valor_dato) o AVG(valor_dato).\n'
    '- filtros: columnas exactas, valores literales (anio como numero).\n'
    '- 1-6 charts ordenados de lo general (cifra/serie) a lo detallado '
    '(tabla/desagregaciones).\n'
    '- indicadores: lista los indicadores del SIIED que alimentan el '
    'tablero por nombre — el usuario necesita saberlos con claridad.\n'
    '- advertencias: supuestos (filtros, agregaciones) o fuentes que '
    'faltarian para el tablero ideal.\n'
    '- Si la peticion no se puede armar con los datasets disponibles, '
    'devuelve charts vacio y explica en advertencias que falta.'
)


# ----------------------------------------------------------------------
# Quiz del libro 3D — Don Datico pregunta al ganar el juego (11-14 años)
# ----------------------------------------------------------------------

QUIZ_SCHEMA = {
    'type': 'object',
    'properties': {
        'resumen_meta': {
            'type': 'string',
            'description': 'Explicación sencilla para niños de qué mide '
                           'el indicador, usando su metadata real',
        },
        'preguntas': {
            'type': 'array',
            'minItems': 3,
            'maxItems': 3,
            'items': {
                'type': 'object',
                'properties': {
                    'pregunta': {'type': 'string'},
                    'correcta': {
                        'type': 'string',
                        'description': 'La respuesta verdadera, tomada de '
                                       'la metadata o la muestra de datos',
                    },
                    'falsas': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'minItems': 3,
                        'maxItems': 3,
                        'description': 'Exactamente 3 opciones incorrectas '
                                       'pero plausibles',
                    },
                },
                'required': ['pregunta', 'correcta', 'falsas'],
                'additionalProperties': False,
            },
        },
        'felicitacion': {
            'type': 'string',
            'description': 'Texto de celebración si acierta las 3',
        },
        'animo': {
            'type': 'string',
            'description': 'Texto motivador para volver a intentarlo',
        },
    },
    'required': ['resumen_meta', 'preguntas', 'felicitacion', 'animo'],
    'additionalProperties': False,
}

QUIZ_PROMPT = (
    'Eres DON DATICO, el loro estadístico del SIIED de Santiago de Cali. '
    'Un niño de 11 a 14 años acaba de GANAR un juego educativo en 3D sobre '
    'un indicador estadístico y tú llegas volando a felicitarlo con un '
    'mini-quiz de premio: 3 preguntas de selección múltiple sobre ESE '
    'indicador, usando la metadata y la muestra de datos recibida.\n\n'
    'REGLAS:\n'
    '- Lenguaje sencillo y alegre para niños; nada de tecnicismos.\n'
    '- Cada pregunta tiene: "pregunta", "correcta" (la respuesta '
    'verdadera, tomada de la metadata o la muestra) y "falsas" '
    '(exactamente 3 opciones incorrectas pero plausibles).\n'
    '- Las falsas deben ser del mismo tipo que la correcta (si es un año, '
    'las falsas son años; si es un valor, valores cercanos pero '
    'distintos; si es un concepto, conceptos parecidos). NUNCA pongas '
    'como falsa algo que también sea verdadero.\n'
    '- resumen_meta: 2-3 frases que expliquen qué mide el indicador como '
    'si se lo contaras a un chico de 12 años; incluye un dato real de la '
    'muestra si ayuda a entender.\n'
    '- felicitacion: 1-2 frases de celebración en personaje (humor de '
    'loro permitido: "¡eso sí es picotear el conocimiento!").\n'
    '- animo: 1-2 frases motivadoras para volver a intentarlo.\n'
    '- NUNCA inventes cifras que no estén en la información entregada.'
)
