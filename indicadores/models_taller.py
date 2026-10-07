"""Módulo Taller de Ecosistemas — instrumento de levantamiento de información.

Portado del proyecto independiente `formulario/` (taller técnico DAP 2026).
Reemplaza al viejo taller gamificado (sesiones/quiz/murales), cuyos modelos
fueron eliminados.

Estructura:
  - InscripcionTaller: identificación del diligenciante (organismo real SIIED,
    suborganismo, equipo responsable, contacto).
  - OpcionTaller: catálogo administrable de opciones para las fichas F1/F2/F3.
  - RetoAnalisis (F2): reto analítico del equipo + FuenteRequerida.

La caracterización de fuentes (F1: FuenteDatos) y la evaluación de seguridad
(F3) viven en `models_catalogo.py` — el Catálogo de Datos es un módulo propio
del SIIED, no un anexo del taller.
"""

import uuid

from django.conf import settings
from django.db import models


class OpcionTaller(models.Model):
    """Catálogo de opciones para preguntas de selección, administrable desde el admin."""

    class Categoria(models.TextChoices):
        RELACION_FUENTE = 'relacion_fuente', 'F1 · Relación con el conjunto de datos'
        INSTRUMENTO = 'instrumento', 'F1 · Instrumento o proceso de recolección'
        MECANISMO = 'mecanismo', 'F1 · Mecanismo de consolidación'
        PERIODICIDAD = 'periodicidad', 'F1 · Periodicidad de actualización'
        DESAGREGACION = 'desagregacion', 'F1/F2 · Nivel de desagregación geográfica'
        UNIDAD_ANALISIS = 'unidad_analisis', 'F1/F2 · Unidad de análisis'
        NIVEL_GEORREF = 'nivel_georref', 'F1 · Nivel de georreferenciación'
        PROBLEMA_CALIDAD = 'problema_calidad', 'F1 · Problemas de calidad'
        TRATAMIENTO = 'tratamiento', 'F2 · Tratamiento o proceso analítico'
        RESULTADO_MVP = 'resultado_mvp', 'F2 · Resultado mínimo viable'
        CAPACIDAD_SIPDI = 'capacidad_sipdi', 'F2 · Capacidad del SIPDI'
        ENFOQUE_DIFERENCIAL = 'enfoque_diferencial', 'F2 · Enfoque diferencial'
        VARIABLE_IDENTIFICADORA = 'variable_identificadora', 'F3 · Variable que identifica personas'
        DATO_SENSIBLE = 'dato_sensible', 'F3 · Información de especial cuidado'
        MEDIDA_PROTECCION = 'medida_proteccion', 'F3 · Medida de protección'

    categoria = models.CharField('Categoría', max_length=40, choices=Categoria.choices, db_index=True)
    etiqueta = models.CharField('Etiqueta', max_length=120)
    orden = models.PositiveSmallIntegerField('Orden', default=0)
    activa = models.BooleanField('Activa', default=True)

    class Meta:
        verbose_name = 'Taller · Opción de catálogo'
        verbose_name_plural = 'Taller · Opciones de catálogo'
        ordering = ['categoria', 'orden', 'etiqueta']
        unique_together = [('categoria', 'etiqueta')]

    def __str__(self):
        return self.etiqueta


class SiNo(models.TextChoices):
    SI = 'si', 'Sí'
    NO = 'no', 'No'


class SiNoNoAplica(models.TextChoices):
    SI = 'si', 'Sí'
    NO = 'no', 'No'
    NO_APLICA = 'no_aplica', 'No aplica'


class SiNoNoSeNoAplica(models.TextChoices):
    SI = 'si', 'Sí'
    NO = 'no', 'No'
    NO_SE = 'no_se', 'No sé'
    NO_APLICA = 'no_aplica', 'No aplica'


class Semaforo(models.TextChoices):
    VERDE = 'verde', 'Verde (impacto nulo o bajo)'
    AMARILLO = 'amarillo', 'Amarillo (impacto moderado)'
    ROJO = 'rojo', 'Rojo (impacto grave)'


class InscripcionTaller(models.Model):
    """Diligenciamiento del taller: identificación + F1 + F2 + F3."""

    class Estado(models.TextChoices):
        EN_PROGRESO = 'en_progreso', 'En progreso'
        COMPLETADA = 'completada', 'Completada'

    class FichaInicial(models.TextChoices):
        F1 = 'f1', 'F1 · Caracterización de datos'
        F2 = 'f2', 'F2 · Reto de análisis'

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='Usuario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='inscripciones_taller')
    estado = models.CharField('Estado', max_length=15, choices=Estado.choices, default=Estado.EN_PROGRESO)
    ficha_inicial = models.CharField(
        'Ficha por la que inicia', max_length=5, choices=FichaInicial.choices,
        default=FichaInicial.F1)
    paso_actual = models.CharField('Último paso completado', max_length=40, blank=True)
    creado = models.DateTimeField('Creado', auto_now_add=True)
    actualizado = models.DateTimeField('Actualizado', auto_now=True)

    # Identificación (F1 sección 1) — usa las tablas reales del SIIED
    organismo = models.ForeignKey(
        'indicadores.Organismo', verbose_name='Nombre del organismo',
        on_delete=models.PROTECT, related_name='inscripciones_taller')
    suborganismo = models.ForeignKey(
        'indicadores.Suborganismo', verbose_name='Nombre del suborganismo',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inscripciones_taller')
    equipo = models.ForeignKey(
        'indicadores.EquipoOrganismo', verbose_name='Equipo de trabajo responsable',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inscripciones_taller',
        help_text='Equipo normalizado contra la tabla EquipoOrganismo del SIIED')
    equipo_responsable = models.CharField(
        'Equipo de trabajo responsable (texto original)', max_length=200, blank=True,
        help_text='Valor digitado en el taller; `equipo` guarda la versión reconciliada')
    nombre_completo = models.CharField('Nombre completo', max_length=150)
    correo = models.EmailField('Correo electrónico')
    telefono = models.CharField('Teléfono', max_length=30, blank=True)

    class Meta:
        verbose_name = 'Taller · Inscripción'
        verbose_name_plural = 'Taller · Inscripciones'
        ordering = ['-creado']

    def __str__(self):
        return f'{self.nombre_completo} · {self.organismo.nombre}'


class RetoAnalisis(models.Model):
    """F2. Formulación del reto de análisis de información."""

    inscripcion = models.OneToOneField(InscripcionTaller, on_delete=models.CASCADE, related_name='reto')

    # 1.1 - 1.4
    nombre = models.CharField('1.1 Nombre breve del reto de análisis', max_length=250,
                              help_text='¿Quiénes?, ¿cuántos?, ¿dónde?, ¿cuándo?, ¿qué diferencias?, ¿qué relación?, ¿qué falta?')
    analisis_propuesto = models.TextField('1.2 ¿Qué análisis se propone realizar?',
                                          help_text='Cruzar, caracterizar, comparar, localizar, priorizar, validar, detectar duplicidades, medir brechas, hacer seguimiento o visualizar.')
    resultado_esperado = models.TextField('1.3 ¿Qué resultado se espera obtener?',
                                          help_text='El conocimiento o clasificación que produciría el análisis, no el sistema que se utilizará.')
    decision_apoya = models.TextField('1.4 ¿Qué decisión o acción podría apoyar?',
                                      help_text='La acción concreta que podría orientarse con el resultado.')

    # 1.5 - 1.6
    unidad_principal = models.ForeignKey(
        'indicadores.OpcionTaller', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
        verbose_name='1.5 Unidad principal de análisis',
        limit_choices_to={'categoria': OpcionTaller.Categoria.UNIDAD_ANALISIS})
    unidad_principal_otra = models.CharField('Otra unidad principal, ¿cuál?', max_length=200, blank=True)
    unidades_relacionar = models.ManyToManyField(
        'indicadores.OpcionTaller', blank=True, related_name='+', verbose_name='Unidades que desea relacionar',
        limit_choices_to={'categoria': OpcionTaller.Categoria.UNIDAD_ANALISIS})
    unidades_relacionar_otra = models.CharField('Otra unidad a relacionar, ¿cuál?', max_length=200, blank=True)
    vinculo_unidades = models.TextField('Si se relacionan varias unidades, indique cómo se vinculan', blank=True)
    desagregaciones = models.ManyToManyField(
        'indicadores.OpcionTaller', blank=True, related_name='+',
        verbose_name='1.6 Nivel de desagregación geográfica del análisis',
        limit_choices_to={'categoria': OpcionTaller.Categoria.DESAGREGACION})
    desagregacion_otra = models.CharField('Otro nivel, ¿cuál?', max_length=200, blank=True)

    # 1.10 - 1.15
    tratamientos = models.ManyToManyField(
        'indicadores.OpcionTaller', blank=True, related_name='+',
        verbose_name='1.10 Tratamiento o proceso analítico a aplicar',
        limit_choices_to={'categoria': OpcionTaller.Categoria.TRATAMIENTO})
    tratamiento_otro = models.CharField('Otro tratamiento, ¿cuál?', max_length=200, blank=True)
    resultados_mvp = models.ManyToManyField(
        'indicadores.OpcionTaller', blank=True, related_name='+',
        verbose_name='1.11 Resultado mínimo viable del análisis',
        limit_choices_to={'categoria': OpcionTaller.Categoria.RESULTADO_MVP})
    resultado_mvp_otro = models.CharField('Otro resultado, ¿cuál?', max_length=200, blank=True)
    capacidades_sipdi = models.ManyToManyField(
        'indicadores.OpcionTaller', blank=True, related_name='+',
        verbose_name='1.12 Capacidad del SIPDI que podría utilizarse',
        limit_choices_to={'categoria': OpcionTaller.Categoria.CAPACIDAD_SIPDI})
    capacidad_sipdi_otra = models.CharField('Otra capacidad, ¿cuál?', max_length=200, blank=True)
    variables_enriquecer = models.TextField(
        '1.13 ¿Qué variables se desean enriquecer o validar mediante el SIPDI?', blank=True,
        help_text='Ej. estrato, clasificación SISBEN, datos socioeconómicos.')
    variables_enriquecer_otro = models.CharField('1.13 Otros, ¿cuál?', max_length=200, blank=True)
    usuario_resultado = models.TextField(
        '1.14 ¿Quién utilizará el resultado?', blank=True,
        help_text='Organismo, equipo o instancia que tomará decisiones o realizará seguimiento. Ej. Gestión del Riesgo, Bienestar Social, Planeación y PMU.')
    enfoques_diferenciales = models.ManyToManyField(
        'indicadores.OpcionTaller', blank=True, related_name='+',
        verbose_name='1.15 Enfoques diferenciales requeridos',
        limit_choices_to={'categoria': OpcionTaller.Categoria.ENFOQUE_DIFERENCIAL})
    enfoque_diferencial_otro = models.CharField('Otro enfoque, ¿cuál?', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Taller · F2 Reto de análisis'
        verbose_name_plural = 'Taller · F2 Retos de análisis'

    def __str__(self):
        return self.nombre


class FuenteRequerida(models.Model):
    """F2 1.7-1.9. Fuentes caracterizadas requeridas para el reto (hasta 3)."""

    reto = models.ForeignKey(RetoAnalisis, on_delete=models.CASCADE, related_name='fuentes_requeridas')
    nombre = models.CharField('Nombre de la fuente de datos', max_length=200)
    organismo = models.CharField('Organismo custodio', max_length=200)
    variables = models.TextField(
        '1.8 Variables necesarias de esta fuente', blank=True,
        help_text='Código de hogar, estado de afectación, tipo de vivienda, barrio, comuna, ayuda recibida, fecha y tipo de apoyo.')
    llave_relacion = models.TextField(
        '1.9 Llave o relación con las demás fuentes', blank=True,
        help_text='Documento, hogar, predio, vivienda, edificio, dirección, coordenadas, código territorial o relación espacial.')

    class Meta:
        verbose_name = 'Taller · Fuente requerida'
        verbose_name_plural = 'Taller · Fuentes requeridas'

    def __str__(self):
        return f'{self.nombre} ({self.organismo})'
