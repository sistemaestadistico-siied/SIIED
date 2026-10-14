"""
Modelos para el módulo ICED v2 — Índice de Capacidad Estadística y de Datos.

Arquitectura simplificada (Torres 2026):
- ICEDFormulario: 1 registro por organismo por período, respuestas en JSONField por módulo
- ICEDRecursoHumano: tabla auxiliar para P19 (personal vinculado a producción estadística)

Reemplaza los 15+ modelos de v1 eliminados en migración 0101.
"""

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class ICEDFormulario(models.Model):
    """
    Un formulario FICED por organismo por período.
    
    Almacena las respuestas de los 5 módulos (A-E) como JSONFields,
    junto con los puntajes calculados por dimensión y el puntaje global.
    
    Fórmula ICED = B×25% + C×25% + D×25% + E×25%
    (Módulo A no puntúa — solo datos de identificación)
    """
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('enviado', 'Enviado'),
        ('validado', 'Validado'),
        ('devuelto', 'Devuelto para corrección'),
        ('rechazado', 'Rechazado'),
    ]

    EQUIPO_CHOICES = [
        ('', 'Consolidado / Completo'),
        ('ETUAG_PSP', 'ETUAG_PSP'),
        ('ETOBS', 'ETOBS'),
        ('ETPP', 'ETPP'),
        ('ETSGC', 'ETSGC'),
        ('ETGIE', 'ETGIE'),
    ]

    organismo = models.ForeignKey(
        'indicadores.Organismo',
        on_delete=models.CASCADE,
        related_name='formularios_iced'
    )
    periodo = models.CharField(
        max_length=10,
        help_text="Vigencia del formulario, ej: '2026'"
    )
    equipo = models.CharField(
        max_length=15,
        choices=EQUIPO_CHOICES,
        blank=True,
        default='',
        help_text="Equipo técnico que responde este FICED (vacío = consolidado/completo)"
    )
    estado = models.CharField(
        max_length=15,
        choices=ESTADO_CHOICES,
        default='borrador'
    )

    # =========================================================================
    # RESPUESTAS POR MÓDULO (JSONField — almacena cleaned_data del Form)
    # =========================================================================
    respuestas_a = models.JSONField(
        default=dict, blank=True,
        help_text="Módulo A: Identificación (P1-P5)"
    )
    respuestas_b = models.JSONField(
        default=dict, blank=True,
        help_text="Módulo B: Entorno Institucional (P6-P12)"
    )
    respuestas_c = models.JSONField(
        default=dict, blank=True,
        help_text="Módulo C: Infraestructura (P13-P22)"
    )
    respuestas_d = models.JSONField(
        default=dict, blank=True,
        help_text="Módulo D: Metodología Estadística (P23-P35)"
    )
    respuestas_e = models.JSONField(
        default=dict, blank=True,
        help_text="Módulo E: Accesibilidad y Uso (P36-P42)"
    )

    # =========================================================================
    # PUNTAJES CALCULADOS (0-100 por dimensión)
    # =========================================================================
    puntaje_b = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        help_text="Puntaje Entorno Institucional (0-1)"
    )
    puntaje_c = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        help_text="Puntaje Infraestructura (0-1)"
    )
    puntaje_d = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        help_text="Puntaje Metodología Estadística (0-1)"
    )
    puntaje_e = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        help_text="Puntaje Accesibilidad y Uso (0-1)"
    )
    puntaje_global = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        help_text="ICED = B×25% + C×25% + D×25% + E×25% (escala 0-1)"
    )
    puntajes_detalle = models.JSONField(
        default=dict, blank=True,
        help_text="Detalle granular: puntajes por dimensión, subdimensión y pregunta (0-1)"
    )

    # =========================================================================
    # AUDITORÍA
    # =========================================================================
    usuario_diligencia = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='formularios_iced_diligenciados',
        help_text="Usuario que diligencia el formulario (delegado del organismo)"
    )
    paso_actual = models.CharField(
        max_length=20,
        default='identificacion',
        help_text="Último paso completado del wizard"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    fecha_envio = models.DateTimeField(
        null=True, blank=True,
        help_text="Fecha en que se envió para validación"
    )
    fecha_validacion = models.DateTimeField(
        null=True, blank=True,
        help_text="Fecha en que fue validado por el equipo SIIED"
    )
    observaciones_validador = models.TextField(
        blank=True, default='',
        help_text="Observaciones del validador al devolver o aprobar"
    )

    class Meta:
        unique_together = ['organismo', 'periodo', 'equipo']
        ordering = ['-periodo', 'organismo__nombre', 'equipo']
        verbose_name = 'Formulario ICED'
        verbose_name_plural = 'Formularios ICED'

    def __str__(self):
        eq = f" [{self.equipo}]" if self.equipo else ""
        return f"ICED {self.periodo} — {self.organismo.nombre}{eq} ({self.get_estado_display()})"

    @property
    def nivel_global(self):
        """Nivel de capacidad según puntaje global (escala 0-1).

        Delega en `calcular_iced.determinar_nivel` para mantener una sola
        fuente de verdad de los umbrales de clasificación (IC-02).
        """
        if self.puntaje_global is None:
            return None
        from .calcular_iced import determinar_nivel
        codigo, _nombre = determinar_nivel(float(self.puntaje_global) * 100)
        return codigo

    @property
    def nivel_global_display(self):
        labels = {
            'muy_alto': 'Muy Alto',
            'alto': 'Alto',
            'medio': 'Medio',
            'bajo': 'Bajo',
        }
        return labels.get(self.nivel_global, '—')

    @property
    def completitud(self):
        """Porcentaje de módulos con respuestas."""
        modulos = [self.respuestas_a, self.respuestas_b, self.respuestas_c,
                   self.respuestas_d, self.respuestas_e]
        llenos = sum(1 for m in modulos if m)
        return round((llenos / 5) * 100)


class ICEDRecursoHumano(models.Model):
    """
    Tabla auxiliar para P19: personal vinculado a producción estadística.
    
    Cada registro representa una persona que participa en la producción
    de información estadística dentro del organismo.
    """
    TIPO_VINCULACION_CHOICES = [
        ('nombrado', 'Nombrado'),
        ('contratista', 'Contratista'),
    ]

    NIVEL_FORMACION_CHOICES = [
        ('B', 'Bachiller'),
        ('TT', 'Técnico-Tecnológico'),
        ('P', 'Profesional'),
        ('E', 'Especialidad'),
        ('M', 'Maestría'),
        ('D', 'Doctorado'),
    ]

    CATEGORIA_NOMBRADO_CHOICES = [
        ('AA', 'Asistencial Administrativo'),
        ('TO', 'Técnico Operativo'),
        ('TA', 'Técnico Administrativo'),
        ('PU1', 'Profesional Universitario 1'),
        ('PE', 'Profesional Especializado'),
        ('AS', 'Asesor'),
    ]

    CATEGORIA_CONTRATISTA_CHOICES = [
        ('AA', 'Asistencial Administrativo'),
        ('T', 'Técnico'),
        ('P', 'Profesional'),
        ('PE', 'Profesional Especializado'),
        ('AS', 'Asesor'),
    ]

    ETAPA_PROCESO_CHOICES = [
        ('DN', 'Detección y análisis de necesidades'),
        ('D', 'Diseño'),
        ('C', 'Construcción'),
        ('R', 'Recolección/Acopio'),
        ('P', 'Procesamiento'),
        ('A', 'Análisis'),
        ('DI', 'Difusión'),
        ('E', 'Evaluación'),
    ]

    formulario = models.ForeignKey(
        ICEDFormulario,
        on_delete=models.CASCADE,
        related_name='recursos_humanos'
    )
    nombre_completo = models.CharField(max_length=200)
    correo = models.EmailField(blank=True, default='')
    telefono = models.CharField(max_length=20, blank=True, default='')
    grupo = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Grupo al que pertenece dentro del organismo"
    )
    anios_experiencia = models.PositiveIntegerField(
        default=0,
        help_text="Años de experiencia profesional"
    )
    inicio_participacion = models.CharField(
        max_length=10, blank=True, default='',
        help_text="Inicio de participación en el proceso (mm/aaaa)"
    )
    tipo_vinculacion = models.CharField(
        max_length=20,
        choices=TIPO_VINCULACION_CHOICES,
        default='contratista'
    )
    categoria_cargo = models.CharField(
        max_length=5, blank=True, default='',
        help_text="Categoría del cargo (según tipo de vinculación)"
    )
    nivel_formacion = models.CharField(
        max_length=5, blank=True, default='',
        choices=NIVEL_FORMACION_CHOICES
    )
    etapas_proceso = models.JSONField(
        default=list, blank=True,
        help_text='Lista de códigos de etapas: ["DN","D","C","R","P","A","DI","E"]'
    )
    funciones_estadisticas = models.BooleanField(
        default=False,
        help_text="¿Dentro de funciones/actividades contractuales se describe la realización de actividades de producción o gestión de información estadística?"
    )

    class Meta:
        verbose_name = 'Recurso Humano ICED'
        verbose_name_plural = 'Recursos Humanos ICED'
        ordering = ['formulario', 'nombre_completo']

    def __str__(self):
        return f"{self.nombre_completo} — {self.formulario}"


class ICEDPersonaContacto(models.Model):
    """
    Tabla auxiliar para P2-P5 del Módulo A: personas de contacto.
    
    Permite agregar múltiples personas responsables de suministrar
    la información del formulario FICED (inline forms).
    """
    formulario = models.ForeignKey(
        ICEDFormulario,
        on_delete=models.CASCADE,
        related_name='personas_contacto'
    )
    nombre_completo = models.CharField(
        max_length=255,
        help_text="Nombre completo de quien suministra la información"
    )
    cargo = models.CharField(
        max_length=150,
        help_text="Cargo del responsable"
    )
    correo = models.EmailField(
        help_text="Correo electrónico institucional"
    )
    telefono = models.CharField(
        max_length=20,
        blank=True, default='',
        help_text="Teléfono de contacto (Ej: 602-8856789)"
    )
    orden = models.PositiveIntegerField(
        default=0,
        help_text="Orden de visualización (la primera es la principal)"
    )

    class Meta:
        verbose_name = 'Persona de Contacto ICED'
        verbose_name_plural = 'Personas de Contacto ICED'
        ordering = ['orden', 'id']

    def __str__(self):
        return f"{self.nombre_completo} ({self.cargo}) — {self.formulario}"


# =============================================================================
# ESTRUCTURA MOP - MacroProcesos, Procesos, Subprocesos, Procedimientos
# =============================================================================

class ICEDMacroProceso(models.Model):
    """
    MacroProcesos del Sistema Integrado de Gestión de Calidad (MOP).
    Datos maestros para P7 del Módulo B.
    """
    codigo = models.CharField(max_length=20, unique=True, help_text="Código del macroproceso (ej: MMDS01)")
    nombre = models.CharField(max_length=200, help_text="Nombre del macroproceso")
    descripcion = models.TextField(blank=True, help_text="Descripción del macroproceso")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'MacroProceso ICED'
        verbose_name_plural = 'MacroProcesos ICED'
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class ICEDProceso(models.Model):
    """
    Procesos asociados a un MacroProceso.
    Datos maestros para P7 del Módulo B.
    """
    macroproceso = models.ForeignKey(
        ICEDMacroProceso,
        on_delete=models.CASCADE,
        related_name='procesos'
    )
    codigo = models.CharField(max_length=20, help_text="Código del proceso")
    nombre = models.CharField(max_length=200, help_text="Nombre del proceso")
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Proceso ICED'
        verbose_name_plural = 'Procesos ICED'
        ordering = ['macroproceso', 'codigo']
        unique_together = ['macroproceso', 'codigo']

    def __str__(self):
        return f"{self.codigo} - {self.nombre} ({self.macroproceso.codigo})"


class ICEDSubproceso(models.Model):
    """
    Subprocesos asociados a un Proceso.
    Datos maestros para P7 del Módulo B.
    """
    proceso = models.ForeignKey(
        ICEDProceso,
        on_delete=models.CASCADE,
        related_name='subprocesos'
    )
    codigo = models.CharField(max_length=20, help_text="Código del subproceso")
    nombre = models.CharField(max_length=200, help_text="Nombre del subproceso")
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Subproceso ICED'
        verbose_name_plural = 'Subprocesos ICED'
        ordering = ['proceso', 'codigo']
        unique_together = ['proceso', 'codigo']

    def __str__(self):
        return f"{self.codigo} - {self.nombre} ({self.proceso.codigo})"


class ICEDProcedimiento(models.Model):
    """
    Procedimientos del MOP. Pueden colgar de un Subproceso o directamente
    de un Proceso (en el MOP real hay procesos sin subprocesos que solo
    tienen procedimientos).
    Datos maestros para P7 del Módulo B.
    """
    subproceso = models.ForeignKey(
        ICEDSubproceso,
        on_delete=models.CASCADE,
        related_name='procedimientos',
        null=True,
        blank=True
    )
    proceso = models.ForeignKey(
        ICEDProceso,
        on_delete=models.CASCADE,
        related_name='procedimientos_directos',
        null=True,
        blank=True,
        help_text="Solo para procedimientos que cuelgan directamente del proceso (sin subproceso)"
    )
    codigo = models.CharField(max_length=20, help_text="Código del procedimiento")
    nombre = models.CharField(max_length=200, help_text="Nombre del procedimiento")
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Procedimiento ICED'
        verbose_name_plural = 'Procedimientos ICED'
        ordering = ['codigo']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(subproceso__isnull=False)
                    | models.Q(proceso__isnull=False)
                ),
                name='iced_procedimiento_padre_requerido',
            ),
        ]

    def __str__(self):
        padre = self.subproceso.codigo if self.subproceso_id else (
            self.proceso.codigo if self.proceso_id else '?'
        )
        return f"{self.codigo} - {self.nombre} ({padre})"


# =============================================================================
# ASIGNACIÓN PREGUNTA ↔ EQUIPO TÉCNICO (subrol del delegado)
# =============================================================================

class ICEDPreguntaEquipo(models.Model):
    """
    Asigna cada pregunta del FICED a uno o varios equipos técnicos.

    El delegado con subrol_ficed='X' solo responde las preguntas cuyo
    código tenga un registro con equipo='X'. Preguntas asignadas a varios
    equipos se responden independientemente por cada equipo y luego se
    concilian en el módulo de validación.

    `codigo` es el número de pregunta del CSV ("17", "15.1", "24.1"...),
    que corresponde a los campos del wizard `p{codigo}_*` (p.ej. '15.1' →
    campos que empiezan por 'p15_1_').
    """
    EQUIPO_CHOICES = ICEDFormulario.EQUIPO_CHOICES[1:]  # sin la opción vacía

    codigo = models.CharField(
        max_length=10,
        help_text="Número de pregunta: '1', '15.1', '28.2', ..."
    )
    equipo = models.CharField(max_length=15, choices=EQUIPO_CHOICES)

    class Meta:
        unique_together = ['codigo', 'equipo']
        ordering = ['codigo', 'equipo']
        verbose_name = 'Asignación Pregunta-Equipo ICED'
        verbose_name_plural = 'Asignaciones Pregunta-Equipo ICED'

    def __str__(self):
        return f"P{self.codigo} → {self.equipo}"

    @classmethod
    def equipos_de_pregunta(cls, codigo):
        """Equipos asignados a una pregunta; vacío = nadie la tiene asignada."""
        return set(
            cls.objects.filter(codigo=str(codigo)).values_list('equipo', flat=True)
        )

    @classmethod
    def preguntas_de_equipo(cls, equipo):
        """Códigos de pregunta asignados a un equipo técnico."""
        return set(
            cls.objects.filter(equipo=equipo).values_list('codigo', flat=True)
        )

    @staticmethod
    def codigo_de_campo(field_name):
        """'p15_1_herramientas' → '15.1'; 'p17_suficiencia' → '17'; otro → None.

        El segundo grupo numérico (subpregunta) solo cuenta si va seguido de
        '_' para distinguir 'p15_1_x' (pregunta 15.1) de campos como 'p10_x'.
        """
        import re
        m = re.match(r'^p(\d+)(?:_(\d+))?(?:_|$)', field_name)
        if not m:
            return None
        return m.group(1) + ('.' + m.group(2) if m.group(2) else '')

    @classmethod
    def campo_pertenece_a_equipo(cls, field_name, equipo):
        """
        True si el campo del wizard ('p15_1_herramientas_tableros') pertenece
        a una pregunta asignada al equipo. Sin asignaciones para la pregunta
        → pertenece a todos (comportamiento legacy).
        """
        codigo = cls.codigo_de_campo(field_name)
        if codigo is None:
            return True  # campos auxiliares (json internos, display) → siempre
        asignados = cls.equipos_de_pregunta(codigo)
        return not asignados or equipo in asignados
