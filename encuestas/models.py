"""
Modelo de datos de encuestas, sondeos y censos (plan §5.1).

Un Formulario tiene secciones (páginas) ordenadas, preguntas con tipo y
config JSON, y opciones para las de selección. La estructura queda
bloqueada con la primera respuesta recibida (regla de integridad §5.4).

Distribución: `modos_diligenciamiento` combina `autodiligenciado`
(usuarios con rol diligenciador), `encuestador` y `publico`.
`modo_identificacion` decide si se captura un Respondiente.
"""
import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Formulario(models.Model):
    TIPO_CHOICES = [
        ('encuesta', 'Encuesta'),
        ('sondeo', 'Sondeo'),
        ('censo', 'Censo'),
    ]
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('publicado', 'Publicado'),
        ('cerrado', 'Cerrado'),
        ('archivado', 'Archivado'),
    ]
    IDENTIFICACION_CHOICES = [
        ('anonimo', 'Anónimo'),
        ('identificado', 'Identificado'),
    ]
    MODO_AUTODILIGENCIADO = 'autodiligenciado'
    MODO_ENCUESTADOR = 'encuestador'
    MODO_PUBLICO = 'publico'
    MODOS_DILIGENCIAMIENTO = [MODO_AUTODILIGENCIADO, MODO_ENCUESTADOR,
                              MODO_PUBLICO]

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    titulo = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True,
                          help_text='URL pública del formulario')
    descripcion = models.TextField(blank=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES,
                            default='encuesta')
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES,
                              default='borrador', db_index=True)

    # Distribución e identificación
    modo_identificacion = models.CharField(
        max_length=15, choices=IDENTIFICACION_CHOICES, default='anonimo')
    campos_identificacion = models.JSONField(
        default=dict, blank=True,
        help_text='Campos pedidos en modo identificado y si son obligatorios: '
                  '{"nombres": true, "documento": true, "correo": false…}')
    modos_diligenciamiento = models.JSONField(
        default=list,
        help_text='Combinación de: autodiligenciado, encuestador, publico')
    una_respuesta_por_respondiente = models.BooleanField(
        default=True,
        help_text='Un solo envío por usuario (autodiligenciado) o documento '
                  '(identificado)')
    permite_editar_tras_envio = models.BooleanField(
        default=False,
        help_text='El respondiente puede corregir su envío ya enviado')
    texto_tratamiento_datos = models.TextField(
        blank=True,
        help_text='Autorización Ley 1581/2012 mostrada antes de capturar '
                  'datos personales')
    limite_envios_por_ip = models.PositiveSmallIntegerField(
        default=5,
        help_text='Máximo de envíos públicos desde la misma IP')

    ventana = models.ForeignKey(
        'gestion.VentanaDiligenciamiento', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='formularios_encuesta')
    version = models.PositiveSmallIntegerField(default=1)
    creador = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='formularios_creados')
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Formulario'
        verbose_name_plural = 'Formularios'
        ordering = ['-actualizado']

    def __str__(self):
        return f'{self.titulo} ({self.get_estado_display()})'

    @property
    def estructura_bloqueada(self):
        """Con respuestas recibidas, la estructura queda bloqueada (§5.4)."""
        return self.envios.filter(estado='enviado').exists()

    @property
    def acepta_respuestas(self):
        return self.estado == 'publicado'


class Seccion(models.Model):
    """Página del formulario (puede ser una sola)."""
    formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE,
                                   related_name='secciones')
    orden = models.PositiveSmallIntegerField(default=0)
    titulo = models.CharField(max_length=200, blank=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ['orden', 'id']
        unique_together = [('formulario', 'orden')]

    def __str__(self):
        return f'{self.formulario.slug} · s{self.orden} {self.titulo}'


class Pregunta(models.Model):
    """Pregunta tipada; `config` guarda validación extra (min, max,
    regex, escala…). `codigo` es la columna estable al exportar."""
    seccion = models.ForeignKey(Seccion, on_delete=models.CASCADE,
                                related_name='preguntas')
    orden = models.PositiveSmallIntegerField(default=0)
    tipo = models.CharField(max_length=20)
    enunciado = models.CharField(max_length=500)
    ayuda = models.CharField(max_length=300, blank=True)
    obligatoria = models.BooleanField(default=False)
    codigo = models.CharField(
        max_length=40, blank=True,
        help_text='Código estable para exportar (ej. P1)')
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['orden', 'id']
        unique_together = [('seccion', 'orden')]

    def __str__(self):
        return f'{self.codigo or self.pk}: {self.enunciado[:60]}'


class Opcion(models.Model):
    pregunta = models.ForeignKey(Pregunta, on_delete=models.CASCADE,
                                 related_name='opciones')
    orden = models.PositiveSmallIntegerField(default=0)
    texto = models.CharField(max_length=300)
    valor = models.CharField(
        max_length=100, blank=True,
        help_text='Valor exportado; vacío = el texto')
    es_otro = models.BooleanField(
        default=False,
        help_text='Abre el campo «¿Cuál?» al elegirla')

    class Meta:
        ordering = ['orden', 'id']

    def __str__(self):
        return self.texto


class Asignacion(models.Model):
    """Formulario ↔ usuario (diligenciador o encuestador)."""
    ROL_CHOICES = [('diligenciador', 'Diligenciador'),
                   ('encuestador', 'Encuestador')]
    formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE,
                                   related_name='asignaciones')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE,
                                related_name='asignaciones_encuesta')
    rol = models.CharField(max_length=15, choices=ROL_CHOICES)
    meta = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Meta de encuestas para el encuestador')
    ventana = models.ForeignKey(
        'gestion.VentanaDiligenciamiento', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('formulario', 'usuario', 'rol')]

    def __str__(self):
        return f'{self.usuario.username} → {self.formulario.slug} ({self.rol})'

    def envios_hechos(self):
        return self.formulario.envios.filter(
            diligenciado_por=self.usuario, estado='enviado').count()


class Respondiente(models.Model):
    """Datos de identificación capturados en modo identificado.

    `documento_norm` (normalizado) detecta duplicados. No hay FK a User
    cuando lo captura un encuestador."""
    nombres = models.CharField(max_length=150, blank=True)
    apellidos = models.CharField(max_length=150, blank=True)
    tipo_documento = models.CharField(max_length=10, blank=True)
    documento = models.CharField(max_length=30, blank=True)
    documento_norm = models.CharField(max_length=30, db_index=True,
                                      blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(blank=True)
    territorio = models.CharField(
        max_length=120, blank=True,
        help_text='Municipio o localidad')
    organismo = models.ForeignKey(
        'indicadores.Organismo', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    autoriza_datos = models.BooleanField(
        default=False,
        help_text='Autorización de tratamiento de datos (Ley 1581/2012)')
    creado = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.documento_norm = ''.join(
            c for c in (self.documento or '') if c.isalnum()).lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.nombres} {self.apellidos}'.strip() \
            or self.documento or f'Respondiente {self.pk}'


class Invitacion(models.Model):
    """Acceso público por invitación con token único."""
    ESTADO_CHOICES = [('pendiente', 'Pendiente'), ('enviada', 'Enviada'),
                      ('usada', 'Usada'), ('vencida', 'Vencida')]
    formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE,
                                   related_name='invitaciones')
    correo = models.EmailField()
    token = models.CharField(max_length=40, unique=True, db_index=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES,
                              default='pendiente')
    enviada = models.DateTimeField(null=True, blank=True)
    recordatorio = models.DateTimeField(null=True, blank=True)
    usada = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.correo} → {self.formulario.slug}'


class Envio(models.Model):
    """Un envío del formulario (borrador o enviado)."""
    ESTADO_CHOICES = [('borrador', 'En progreso'), ('enviado', 'Enviado'),
                      ('anulado', 'Anulado')]
    formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE,
                                   related_name='envios')
    version = models.PositiveSmallIntegerField(default=1)
    diligenciado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='envios_diligenciados',
        help_text='Diligenciador o encuestador; vacío si es público')
    respondiente = models.ForeignKey(
        Respondiente, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='envios')
    modo = models.CharField(
        max_length=15,
        choices=[('auto', 'Autodiligenciado'), ('encuestador', 'Encuestador'),
                 ('publico', 'Público')], default='auto')
    token = models.CharField(
        max_length=40, db_index=True, blank=True,
        help_text='Sesión anónima para continuar un borrador público')
    offline_id = models.CharField(
        max_length=40, unique=True, null=True, blank=True,
        help_text='UUID del cliente offline: deduplica envíos sincronizados')
    invitacion = models.ForeignKey(
        Invitacion, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='envios')
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES,
                              default='borrador', db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)
    geolocalizacion = models.JSONField(
        null=True, blank=True,
        help_text='Opcional, trabajo de campo: {"lat":…, "lon":…}')
    creado = models.DateTimeField(auto_now_add=True)
    enviado = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-creado']
        indexes = [
            models.Index(fields=['formulario', 'estado']),
            models.Index(fields=['diligenciado_por', 'estado']),
        ]

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(16)
        if self.estado == 'enviado' and not self.enviado:
            self.enviado = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.formulario.slug} · envío {self.pk} ({self.estado})'


class RespuestaItem(models.Model):
    """Respuesta de una pregunta dentro de un envío. `valor` es JSON
    (texto, número, lista de opciones, {"otro": "…"}…)."""
    envio = models.ForeignKey(Envio, on_delete=models.CASCADE,
                              related_name='respuestas')
    pregunta = models.ForeignKey(Pregunta, on_delete=models.CASCADE,
                                 related_name='respuestas')
    valor = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = [('envio', 'pregunta')]
        indexes = [models.Index(fields=['envio', 'pregunta'])]

    def __str__(self):
        return f'envío {self.envio_id} · {self.pregunta_id}'
