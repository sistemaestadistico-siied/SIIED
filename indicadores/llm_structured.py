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
                'Encuadre inicial del tablero en prosa: que se esta '
                'midiendo, por que importa y como leerlo (2-4 oraciones). '
                'Aparece arriba de los tiles.'),
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
    'abre el tablero explicando que se mide y por que importa; tiles '
    'ordenados de lo general (kpi/serie) a lo detallado '
    '(tabla/desagregaciones); explicacion clara de que muestra cada '
    'cosa.\n\n'
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
                'Analisis del tablero en prosa (2-5 oraciones): '
                'hallazgos, tendencias y comparaciones usando '
                'SOLO las cifras del resumen proporcionado'),
        },
        'insights': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': (
                'Lectura de cada tile en el MISMO orden que la lista '
                'de tiles recibida (una oracion con el dato clave real; '
                'string vacio si el tile no aporta lectura)'),
        },
    },
    'required': ['analisis'],
    'additionalProperties': False,
}

TABLERO_ANALISIS_PROMPT = (
    'Eres DON DATICO, analista de datos senior del SIIED. Ya generaste un '
    'tablero y el sistema resolvio sus tiles contra datos reales. Ahora '
    'recibes un RESUMEN de esos datos (titulo, tipo y cifras agregadas de '
    'cada tile).\n\n'
    'TU TAREA: escribir el ANALISIS del tablero en prosa clara y directa, '
    'como analista que ya vio los numeros: hallazgo principal, tendencia o '
    'comparacion destacada, y una lectura honesta de limitaciones si el '
    'dato es debil.\n\n'
    'REGLAS:\n'
    '- SOLO cifras que aparecen en el resumen. NUNCA inventes numeros, '
    'porcentajes ni anos.\n'
    '- insights: una lectura corta por tile, en el mismo orden recibido. '
    'Con el dato clave real si el resumen lo trae; "" si no hay lectura '
    'util (ej: tile de texto).\n'
    '- Tono ejecutivo pero cercano; sin relleno ni generalidades.'
)
