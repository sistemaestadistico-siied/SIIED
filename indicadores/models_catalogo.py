"""Módulo Catálogo de Datos — inventario institucional de activos de información.

Módulo propio del SIIED (no es el catálogo de consulta de indicadores, que es
`CatalogoConsulta`). Contiene:

  - FuenteDatos / FuenteOrigen / VariableFuente: caracterización F1 de las
    fuentes levantada en el taller de gestión de datos — es la entrada viva del
    catálogo por organismo/suborganismo/equipo.
  - EvaluacionSeguridad (F3): valoración de seguridad y privacidad por fuente.
  - BaseCatalogo / CampoCatalogo: catálogo de bases de datos del Data Lake
    (antes hardcodeado en `formulario/taller/catalogo_data.py`), administrable
    desde el admin.

Portado del proyecto independiente `formulario/` (taller técnico DAP 2026).
"""

from django.db import models

from .models_taller import InscripcionTaller, OpcionTaller, Semaforo, SiNo, SiNoNoAplica, SiNoNoSeNoAplica


class FuenteDatos(models.Model):
    """F1. Caracterización de una fuente o conjunto de datos institucional."""

    class Rol(models.TextChoices):
        PRODUCTOR = 'productor', 'Productor: genera, captura o administra directamente los datos'
        USUARIO = 'usuario', 'Usuario: consulta o utiliza datos producidos por otros organismos'
        AMBOS = 'ambos', 'Ambos: produce y también consume datos de esta fuente'

    class Georref(models.TextChoices):
        SI = 'si', 'Sí'
        NO = 'no', 'No'
        PARCIAL = 'parcial', 'Parcial (algunos registros)'

    inscripcion = models.ForeignKey(InscripcionTaller, on_delete=models.CASCADE, related_name='fuentes')

    # 1. Información general
    nombre = models.CharField('Nombre de la fuente o conjunto de datos', max_length=200)
    descripcion = models.TextField('Descripción breve del contenido')
    relaciones = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+', verbose_name='Relación con el conjunto de datos',
        limit_choices_to={'categoria': OpcionTaller.Categoria.RELACION_FUENTE})
    relacion_otra = models.CharField('Otra relación, ¿cuál?', max_length=200, blank=True)
    instrumentos = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+', verbose_name='Instrumento o proceso de recolección',
        limit_choices_to={'categoria': OpcionTaller.Categoria.INSTRUMENTO})
    instrumento_otro = models.CharField('Otro instrumento, ¿cuál?', max_length=200, blank=True)
    mecanismos = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+', verbose_name='Mecanismo de consolidación',
        limit_choices_to={'categoria': OpcionTaller.Categoria.MECANISMO})
    mecanismo_otro = models.CharField('Otro mecanismo, ¿cuál?', max_length=200, blank=True)
    fecha_inicio = models.DateField('Fecha en que comenzó a utilizarse la fuente', null=True, blank=True)
    fecha_actualizacion = models.DateField('Fecha de última actualización', null=True, blank=True)
    periodicidades = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+', verbose_name='Periodicidad de actualización',
        limit_choices_to={'categoria': OpcionTaller.Categoria.PERIODICIDAD})
    periodicidad_otra = models.CharField('Otra periodicidad, ¿cuál?', max_length=200, blank=True)
    desagregaciones = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+', verbose_name='Nivel de desagregación geográfica',
        limit_choices_to={'categoria': OpcionTaller.Categoria.DESAGREGACION})
    desagregacion_otra = models.CharField('Otro nivel, ¿cuál?', max_length=200, blank=True)
    num_registros = models.PositiveIntegerField('Número aproximado de registros', null=True, blank=True)
    num_registros_fecha = models.DateField('Fecha a la que corresponde esa cantidad', null=True, blank=True)
    num_registros_desconocido = models.BooleanField('No se conoce la cantidad de registros', default=False)
    tiene_diccionario = models.CharField('¿Existe diccionario de variables, manual u otro documento?',
                                         max_length=5, choices=SiNo.choices, blank=True)
    diccionario_ubicacion = models.CharField('Nombre o ubicación institucional del diccionario',
                                             max_length=250, blank=True)
    archivo_diccionario = models.FileField(
        'Archivo del diccionario de datos (Excel)', upload_to='diccionarios/',
        blank=True, null=True,
        help_text='Suba el archivo Excel (.xlsx o .xls) con el diccionario completo de variables.')

    # Rol del organismo frente a la fuente
    rol = models.CharField('Rol del organismo frente a la fuente', max_length=10, choices=Rol.choices, blank=True)

    # 2. Propósito y utilidad institucional
    decisiones_apoya = models.TextField(
        '¿Qué decisiones institucionales apoya?', blank=True,
        help_text='Ej. priorización de subsidios, asignación de recursos, atención de emergencias, planificación territorial.')
    unidades_analisis = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+', verbose_name='Unidad de análisis principal',
        limit_choices_to={'categoria': OpcionTaller.Categoria.UNIDAD_ANALISIS})
    unidad_analisis_otra = models.CharField('Otra unidad, ¿cuál?', max_length=200, blank=True)

    # 5. Calidad y cobertura
    georreferenciacion = models.CharField('¿Existe georreferenciación?', max_length=10,
                                          choices=Georref.choices, blank=True)
    niveles_georref = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+', verbose_name='Nivel de georreferenciación',
        limit_choices_to={'categoria': OpcionTaller.Categoria.NIVEL_GEORREF})
    nivel_georref_otro = models.CharField('Otro nivel, ¿cuál?', max_length=200, blank=True)
    problemas_calidad = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+', verbose_name='Principales problemas de calidad',
        limit_choices_to={'categoria': OpcionTaller.Categoria.PROBLEMA_CALIDAD})
    problema_calidad_otro = models.CharField('Otro problema, ¿cuál?', max_length=200, blank=True)
    tiene_validacion = models.CharField('¿Se han realizado procesos de validación o limpieza?',
                                        max_length=5, choices=SiNo.choices, blank=True)
    validacion_descripcion = models.TextField('Describa brevemente los procesos de validación aplicados', blank=True)

    class Meta:
        verbose_name = 'Catálogo · Fuente de datos'
        verbose_name_plural = 'Catálogo · Fuentes de datos'

    def __str__(self):
        return self.nombre

    @property
    def organismo(self):
        return self.inscripcion.organismo


class FuenteOrigen(models.Model):
    """F1. Fuentes de origen cuando el rol es Usuario o Ambos."""

    fuente = models.ForeignKey(FuenteDatos, on_delete=models.CASCADE, related_name='fuentes_origen')
    nombre = models.CharField('Fuente de origen', max_length=200)
    organismo_productor = models.CharField('Organismo o entidad productora', max_length=200)

    class Meta:
        verbose_name = 'Catálogo · Fuente de origen'
        verbose_name_plural = 'Catálogo · Fuentes de origen'

    def __str__(self):
        return f'{self.nombre} ({self.organismo_productor})'


class VariableFuente(models.Model):
    """F1. Estructura y variables principales de una fuente (máximo 10)."""

    class TipoDato(models.TextChoices):
        TEXTO = 'texto', 'Texto'
        NUMERO = 'numero', 'Número'
        FECHA = 'fecha', 'Fecha'
        GEOGRAFICO = 'geografico', 'Geográfico'

    fuente = models.ForeignKey(FuenteDatos, on_delete=models.CASCADE, related_name='variables')
    nombre = models.CharField('Nombre del campo', max_length=120)
    tipo = models.CharField('Tipo de dato', max_length=15, choices=TipoDato.choices)
    descripcion = models.CharField('Descripción breve', max_length=250, blank=True)
    es_identificador = models.BooleanField('¿Es un identificador único?', default=False)

    class Meta:
        verbose_name = 'Catálogo · Variable de fuente'
        verbose_name_plural = 'Catálogo · Variables de fuente'

    def __str__(self):
        return self.nombre


class EvaluacionSeguridad(models.Model):
    """F3. Seguridad y privacidad de la información — una por fuente (activo de información)."""

    fuente = models.OneToOneField(FuenteDatos, on_delete=models.CASCADE, related_name='seguridad')

    # 6. Datos personales y acceso
    contiene_datos_personales = models.CharField(
        '¿Este conjunto contiene datos personales que permitan identificar a una persona?',
        max_length=5, choices=SiNo.choices, blank=True)
    variables_identificadoras = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+',
        verbose_name='Variables que permiten identificar a las personas',
        limit_choices_to={'categoria': OpcionTaller.Categoria.VARIABLE_IDENTIFICADORA})
    variable_identificadora_otra = models.CharField('Otra variable, ¿cuál?', max_length=200, blank=True)
    datos_sensibles = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+',
        verbose_name='Información que requiere especial cuidado (Ley 1712 de 2014 y Ley 1581 de 2012)',
        limit_choices_to={'categoria': OpcionTaller.Categoria.DATO_SENSIBLE})
    dato_sensible_otro = models.CharField('Otra información, ¿cuál?', max_length=200, blank=True)
    base_legitima = models.CharField(
        '¿Cuenta con una base legítima para acceder a los datos y utilizarlos?',
        max_length=10, choices=SiNoNoAplica.choices, blank=True)
    base_legitima_porque = models.CharField('¿Por qué?', max_length=300, blank=True)

    # 6. Uso y protección de los datos
    proveedor_base_legitima = models.CharField(
        'En caso de ser usuario, ¿el proveedor de datos tiene una base legítima para recolectar y brindar acceso a los datos?',
        max_length=10, choices=SiNoNoSeNoAplica.choices, blank=True,
        help_text='Principio de debida diligencia.')
    proveedor_base_legitima_porque = models.CharField('¿Por qué?', max_length=300, blank=True)
    finalidad_especifica = models.CharField(
        '¿La finalidad del uso de datos está definida de la forma más específica y restringida razonablemente posible?',
        max_length=10, choices=SiNoNoSeNoAplica.choices, blank=True)
    finalidad_especifica_porque = models.CharField('¿Por qué?', max_length=300, blank=True)
    datos_necesarios = models.CharField(
        '¿Todos los datos que utilizará son necesarios y no excesivos?',
        max_length=10, choices=SiNoNoSeNoAplica.choices, blank=True,
        help_text='Límite personas, variables, área geográfica, periodo temporal y metadatos a lo estrictamente necesario.')
    datos_necesarios_porque = models.CharField('¿Por qué?', max_length=300, blank=True)
    conservacion_limitada = models.CharField(
        '¿Los datos se conservarán únicamente durante el tiempo necesario?',
        max_length=10, choices=SiNoNoSeNoAplica.choices, blank=True,
        help_text='Defina eliminación o destrucción cuando dejen de ser necesarios para la finalidad especificada.')
    conservacion_limitada_porque = models.CharField('¿Por qué?', max_length=300, blank=True)
    salvaguardas = models.CharField(
        '¿Existen salvaguardas técnicas, administrativas y físicas apropiadas y razonables?',
        max_length=10, choices=SiNoNoSeNoAplica.choices, blank=True)
    salvaguardas_porque = models.CharField('¿Por qué?', max_length=300, blank=True)
    transparencia = models.CharField(
        '¿Ha comunicado o comunicará el uso de los datos a titulares, público u otras partes interesadas apropiadas?',
        max_length=10, choices=SiNoNoSeNoAplica.choices, blank=True,
        help_text='Principio de transparencia.')
    transparencia_porque = models.CharField('¿Por qué?', max_length=300, blank=True)

    # 6. Divulgación y medidas de protección
    riesgos_publicacion = models.CharField(
        '¿Los riesgos/daños de publicar datos o informes son desproporcionadamente altos frente a los beneficios?',
        max_length=10, choices=SiNoNoSeNoAplica.choices, blank=True,
        help_text='Considere granularidad, agregación y efecto mosaico que pueda volver identificables a personas o grupos.')
    riesgos_publicacion_porque = models.CharField('¿Por qué?', max_length=300, blank=True)
    terceros_estandares = models.CharField(
        '¿Los socios/terceros con quien intercambia información cumplen estándares de privacidad y protección de datos al menos equivalentes?',
        max_length=10, choices=SiNoNoSeNoAplica.choices, blank=True,
        help_text='Revise diligencia debida, contratos, historial de incidentes, nube, seguridad y ubicación/transfronterización de los datos.')
    terceros_estandares_porque = models.CharField('¿Por qué?', max_length=300, blank=True)
    riesgo_dano = models.CharField(
        '¿El uso de datos plantea riesgos de daño para personas o grupos, sean identificables o no?',
        max_length=10, choices=SiNoNoSeNoAplica.choices, blank=True,
        help_text='Ej. fuga, brecha, divulgación no autorizada, uso indebido, reidentificación, baja calidad, sesgo.')
    riesgo_dano_porque = models.CharField('¿Por qué?', max_length=300, blank=True)
    medidas_proteccion = models.ManyToManyField(
        OpcionTaller, blank=True, related_name='+',
        verbose_name='Medidas que se aplican para proteger la información personal',
        limit_choices_to={'categoria': OpcionTaller.Categoria.MEDIDA_PROTECCION})
    medida_proteccion_otra = models.CharField('Otras medidas / Ninguna, ¿por qué?', max_length=300, blank=True)

    # 6.1 Valoración de los activos de información
    susceptible_fraude = models.CharField(
        '¿El activo es susceptible a fraude o corrupción? (Ley 1474 - Estatuto Anticorrupción)',
        max_length=5, choices=SiNo.choices, blank=True,
        help_text='¿El activo puede ser usado para beneficio personal sobre el interés general?')
    organismo_custodio = models.CharField(
        '¿Qué organismo / suborganismo se encuentra custodiando el conjunto de datos?',
        max_length=250, blank=True)
    confidencialidad = models.CharField(
        'Nivel de clasificación de Confidencialidad', max_length=10, choices=Semaforo.choices, blank=True,
        help_text='Verde: pública. Amarillo: pública clasificada (semiprivados). Rojo: pública reservada (exceptuada por ley).')
    integridad = models.CharField(
        'Nivel de clasificación de Integridad', max_length=10, choices=Semaforo.choices, blank=True,
        help_text='Establezca el nivel de clasificación de Integridad conforme al impacto que puede representar '
                  'para la entidad (impacto económico, reputacional, legal) y las personas '
                  '(daños causados/vulneración de derechos) no contar con los datos exactos, completos '
                  'y que representen la realidad de los hechos.')
    disponibilidad = models.CharField(
        'Nivel de clasificación de Disponibilidad', max_length=10, choices=Semaforo.choices, blank=True,
        help_text='Establezca el nivel de clasificación de Disponibilidad conforme al impacto que puede representar '
                  'para la entidad (impacto económico, reputacional, legal) y las personas '
                  '(daños causados/vulneración de derechos) al no contar con los datos disponibles '
                  'para su uso o finalidad para la cual fueron recolectados.')
    criticidad = models.CharField(
        'Resultado valoración de criticidad', max_length=10, choices=Semaforo.choices, blank=True)

    # Nivel de clasificación (aplica Sí/No por nivel)
    aplica_publica = models.CharField(
        'Pública: información que puede ser divulgada sin restricciones (ej. estadísticas agregadas)',
        max_length=5, choices=SiNo.choices, blank=True)
    aplica_semiprivada = models.CharField(
        'Semiprivada: información financiera, socioeconómica, laboral o comercial',
        max_length=5, choices=SiNo.choices, blank=True)
    aplica_privada = models.CharField(
        'Privada o de circulación restringida: datos personales, dirección, teléfono, composición familiar, ubicación exacta',
        max_length=5, choices=SiNo.choices, blank=True)
    aplica_sensible = models.CharField(
        'Sensible: datos de salud, origen étnico, discapacidad, biométricos o que puedan generar discriminación',
        max_length=5, choices=SiNo.choices, blank=True)
    aplica_reservada = models.CharField(
        'Reservada: información exceptuada por ley (seguridad, investigaciones, reserva legal, población víctima)',
        max_length=5, choices=SiNo.choices, blank=True)

    class Meta:
        verbose_name = 'Catálogo · Evaluación de seguridad'
        verbose_name_plural = 'Catálogo · Evaluaciones de seguridad'

    def __str__(self):
        return f'Seguridad · {self.fuente}'

    def calcular_criticidad(self):
        """Regla del instrumento: reservada/rojo en confidencialidad o integridad/disponibilidad grave => crítico."""
        valores = {self.confidencialidad, self.integridad, self.disponibilidad}
        if Semaforo.ROJO in valores:
            return Semaforo.ROJO
        if Semaforo.AMARILLO in valores:
            return Semaforo.AMARILLO
        if valores == {Semaforo.VERDE}:
            return Semaforo.VERDE
        return ''

    def calcular_factores_riesgo_ocha(self):
        """Metodología OCHA-Naciones Unidas: evalúa 13 criterios de riesgo de privacidad."""
        factores = [
            {
                'pregunta': '¿Utilizará datos que identifiquen directamente a personas?',
                'orientacion': 'Ej.: nombre, identificación, fecha de nacimiento, ubicación, teléfono, correo, IP, identificadores de dispositivos.',
                'respuesta': self.contiene_datos_personales,
                'regla': 'Riesgo si = Sí',
                'es_riesgo': self.contiene_datos_personales == 'si',
            },
            {
                'pregunta': '¿Utilizará datos no directamente identificativos que podrían permitir individualizar o reidentificar a una persona?',
                'orientacion': 'Considere medios y tecnologías razonablemente accesibles, tiempo, costo y otras fuentes disponibles.',
                'respuesta': 'sí' if self.variables_identificadoras.exists() else '',
                'regla': 'Riesgo si = Sí',
                'es_riesgo': self.variables_identificadoras.exists(),
            },
            {
                'pregunta': '¿Utilizará datos sensibles?',
                'orientacion': 'Incluye, entre otros, salud, biometría, niños, finanzas, origen racial/étnico, opiniones políticas, religión, orientación sexual, procesos judiciales o personas/grupos expuestos a daño.',
                'respuesta': 'sí' if self.datos_sensibles.exists() else '',
                'regla': 'Riesgo si = Sí',
                'es_riesgo': self.datos_sensibles.exists(),
            },
            {
                'pregunta': '¿Cuenta con una base legítima para acceder a los datos y utilizarlos?',
                'orientacion': 'Considere consentimiento, habilitación legal, mandato institucional o protección de intereses vitales, según el contexto y la normativa aplicable.',
                'respuesta': self.base_legitima,
                'regla': 'Riesgo si = No',
                'es_riesgo': self.base_legitima == 'no',
            },
            {
                'pregunta': '¿El proveedor de datos tiene una base legítima para dar acceso a los datos para los fines del proyecto?',
                'orientacion': 'Realice diligencia debida sobre la forma en que el tercero recolectó y comparte la información.',
                'respuesta': self.proveedor_base_legitima,
                'regla': 'Riesgo si = No',
                'es_riesgo': self.proveedor_base_legitima == 'no',
            },
            {
                'pregunta': '¿La finalidad del uso de datos está definida de la forma más específica y restringida razonablemente posible?',
                'orientacion': 'La finalidad debe ser legítima, específica y estar definida a más tardar al acceder o recolectar los datos.',
                'respuesta': self.finalidad_especifica,
                'regla': 'Riesgo si = No',
                'es_riesgo': self.finalidad_especifica == 'no',
            },
            {
                'pregunta': '¿Todos los datos que utilizará son necesarios y no excesivos?',
                'orientacion': 'Limite personas, variables, área geográfica, periodo temporal y metadatos a lo estrictamente necesario.',
                'respuesta': self.datos_necesarios,
                'regla': 'Riesgo si = No',
                'es_riesgo': self.datos_necesarios == 'no',
            },
            {
                'pregunta': '¿Los datos se conservarán únicamente durante el tiempo necesario?',
                'orientacion': 'Defina eliminación o destrucción cuando dejen de ser necesarios para la finalidad especificada.',
                'respuesta': self.conservacion_limitada,
                'regla': 'Riesgo si = No',
                'es_riesgo': self.conservacion_limitada == 'no',
            },
            {
                'pregunta': '¿Existen salvaguardas técnicas, administrativas y físicas apropiadas y razonables?',
                'orientacion': 'Considere control de acceso, cifrado, desidentificación, capacitación, vulnerabilidades, notificación de brechas, terceros y retención.',
                'respuesta': self.salvaguardas,
                'regla': 'Riesgo si = No',
                'es_riesgo': self.salvaguardas == 'no',
            },
            {
                'pregunta': '¿Ha comunicado o comunicará el uso de los datos a titulares, público u otras partes interesadas apropiadas?',
                'orientacion': 'Informe, cuando proceda, sobre uso, políticas y mecanismos de acceso, rectificación o eliminación.',
                'respuesta': self.transparencia,
                'regla': 'Riesgo si = No / No sé',
                'es_riesgo': self.transparencia in ('no', 'no_se'),
            },
            {
                'pregunta': '¿Los riesgos/daños de publicar datos o informes son desproporcionadamente altos frente a los beneficios?',
                'orientacion': 'Considere granularidad, agregación y efecto mosaico que pueda volver identificables a personas o grupos.',
                'respuesta': self.riesgos_publicacion,
                'regla': 'Riesgo si = Sí',
                'es_riesgo': self.riesgos_publicacion == 'si',
            },
            {
                'pregunta': '¿Los socios/terceros cumplen estándares de privacidad y protección de datos al menos equivalentes?',
                'orientacion': 'Revise diligencia debida, contratos, historial de incidentes, nube, seguridad y ubicación/transfronterización de datos.',
                'respuesta': self.terceros_estandares,
                'regla': 'Riesgo si = No',
                'es_riesgo': self.terceros_estandares == 'no',
            },
            {
                'pregunta': '¿El uso de datos plantea riesgos de daño para personas o grupos, sean identificables o no?',
                'orientacion': 'Ej.: fuga, brecha, divulgación no autorizada, uso indebido, reidentificación, baja calidad, sesgo o creación de nuevos conjuntos.',
                'respuesta': self.riesgo_dano,
                'regla': 'Riesgo si = Sí',
                'es_riesgo': self.riesgo_dano == 'si',
            },
        ]
        total_riesgos = sum(1 for f in factores if f['es_riesgo'])
        return {'factores': factores, 'total_riesgos': total_riesgos, 'total_criterios': len(factores)}

    def save(self, *args, **kwargs):
        if not self.criticidad:
            self.criticidad = self.calcular_criticidad()
        super().save(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────────
# Catálogo de bases del Data Lake (antes `catalogo_data.py` hardcodeado)
# ──────────────────────────────────────────────────────────────────────────

class BaseCatalogo(models.Model):
    """Base de datos del Data Lake publicada en el catálogo (capa Gold y dimensiones)."""

    slug = models.SlugField('Identificador', max_length=60, unique=True,
                            help_text='Identificador técnico de la base (ej. fact_personas)')
    nombre = models.CharField('Nombre', max_length=200)
    descripcion = models.TextField('Descripción', blank=True)
    organismo = models.ForeignKey(
        'indicadores.Organismo', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bases_catalogo', verbose_name='Organismo custodio')
    organismo_texto = models.CharField(
        'Organismo (texto)', max_length=200, blank=True,
        help_text='Texto original del organigrama cuando no hay Organismo SIIED asociado')
    frecuencia = models.CharField('Frecuencia de actualización', max_length=100, blank=True)
    cobertura = models.CharField('Cobertura', max_length=100, blank=True)
    activa = models.BooleanField('Activa', default=True)
    orden = models.PositiveSmallIntegerField('Orden', default=0)

    class Meta:
        verbose_name = 'Catálogo · Base de datos'
        verbose_name_plural = 'Catálogo · Bases de datos'
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre

    def get_organismo_display(self):
        if self.organismo:
            return self.organismo.nombre
        return self.organismo_texto

    def campos_cruzables(self):
        return self.campos.filter(es_llave_cruce=True)


class CampoCatalogo(models.Model):
    """Campo/columna documentado dentro de una BaseCatalogo."""

    class Tipo(models.TextChoices):
        TEXTO = 'texto', 'Texto'
        NUMERO = 'numero', 'Número'
        ENTERO = 'entero', 'Entero'
        FECHA = 'fecha', 'Fecha'
        GEOGRAFICO = 'geografico', 'Geográfico'

    class Sensibilidad(models.TextChoices):
        PUBLICO = '', 'Público'
        SENSIBLE = 'sensible', 'Sensible (dato personal)'
        ADMIN = 'admin', 'Restringido (solo administración)'

    base = models.ForeignKey(BaseCatalogo, on_delete=models.CASCADE, related_name='campos')
    nombre = models.CharField('Nombre del campo', max_length=120)
    tipo = models.CharField('Tipo de dato', max_length=15, choices=Tipo.choices, default=Tipo.TEXTO)
    descripcion = models.CharField('Descripción', max_length=250, blank=True)
    es_llave_cruce = models.BooleanField(
        '¿Es llave de cruce?', default=False,
        help_text='Si el campo permite cruzar esta base con otras bases del catálogo')
    sensibilidad = models.CharField('Sensibilidad', max_length=10,
                                    choices=Sensibilidad.choices, default=Sensibilidad.PUBLICO, blank=True)
    categoria = models.CharField('Categoría temática', max_length=200, blank=True,
                                 help_text='Agrupación dentro de la base (ej. 2. Identificación y demografía)')
    orden = models.PositiveSmallIntegerField('Orden', default=0)

    class Meta:
        verbose_name = 'Catálogo · Campo de base'
        verbose_name_plural = 'Catálogo · Campos de base'
        ordering = ['base', 'orden', 'nombre']
        unique_together = [('base', 'nombre')]

    def __str__(self):
        return f'{self.base.slug}.{self.nombre}'
