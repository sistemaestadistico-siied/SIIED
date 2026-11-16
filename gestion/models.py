"""
Módulo Gestión de Talleres y Formularios.

Tres modelos transversales:
- AccionGestion: bitácora de toda mutación del módulo (auditoría).
- VentanaDiligenciamiento: apertura/cierre de diligenciamiento por
  módulo (FICED, Taller, encuestas) y referencia (periodo/edición/id).
- ProrrogaVentana: extensión del cierre para un organismo concreto.

Regla del proyecto: nada se borra; las entidades se desactivan.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from indicadores.models import Organismo


class AccionGestion(models.Model):
    """Bitácora de auditoría del módulo de gestión.

    Toda mutación (crear, editar, desactivar, enviar correo, reiniciar,
    abrir/cerrar ventana, otorgar prórroga…) pasa por
    `gestion.services.registrar_accion`, que llena este registro.
    `antes`/`despues` guardan copias JSON del objeto afectado; en acciones
    destructivas `antes` contiene la copia completa para poder restaurar.
    """

    MODULO_CHOICES = [
        ('gestion', 'Gestión (general)'),
        ('ficed', 'FICED'),
        ('taller', 'Taller de Gestión de Datos'),
        ('encuestas', 'Encuestas'),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='acciones_gestion',
        help_text='Quien ejecutó la acción')
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    modulo = models.CharField(
        max_length=15, choices=MODULO_CHOICES, db_index=True)
    accion = models.CharField(
        max_length=60, db_index=True,
        help_text='Verbo de la acción: crear_usuario, desactivar, '
                  'enviar_correo, reiniciar_formulario, prorroga…')
    objeto_tipo = models.CharField(
        max_length=60, blank=True, default='',
        help_text='Nombre del modelo afectado (p. ej. PerfilRecolector)')
    objeto_id = models.CharField(
        max_length=60, blank=True, default='',
        help_text='Identificador del objeto afectado (texto para admitir uuid)')
    antes = models.JSONField(
        null=True, blank=True,
        help_text='Estado previo (copia completa en acciones destructivas)')
    despues = models.JSONField(
        null=True, blank=True,
        help_text='Estado posterior o detalle del resultado')
    motivo = models.TextField(
        blank=True, default='',
        help_text='Obligatorio en acciones destructivas')
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = 'Acción de gestión'
        verbose_name_plural = 'Bitácora de gestión'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['modulo', 'accion']),
            models.Index(fields=['objeto_tipo', 'objeto_id']),
        ]

    def __str__(self):
        u = self.usuario.username if self.usuario else 'sistema'
        return f'[{self.get_modulo_display()}] {self.accion} por {u}'


class VentanaDiligenciamiento(models.Model):
    """Ventana de apertura/cierre para diligenciar un módulo.

    Una ventana por (modulo, referencia): FICED usa el periodo (vigencia),
    el Taller la edición (año) y las encuestas el id del formulario.
    Sin ventana configurada el módulo se comporta como hoy (abierto).
    """

    MODULO_CHOICES = AccionGestion.MODULO_CHOICES

    modulo = models.CharField(max_length=15, choices=MODULO_CHOICES)
    referencia = models.CharField(
        max_length=40,
        help_text='Periodo FICED, edición del taller o id de formulario')
    fecha_apertura = models.DateField()
    fecha_cierre = models.DateField(
        help_text='Último día de diligenciamiento (inclusive)')
    activa = models.BooleanField(
        default=True,
        help_text='Permite suspender la ventana sin borrarla')
    mensaje_cerrado = models.TextField(
        blank=True, default='',
        help_text='Texto que se muestra cuando la ventana está cerrada. '
                  'Vacío = mensaje predeterminado')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ventana de diligenciamiento'
        verbose_name_plural = 'Ventanas de diligenciamiento'
        ordering = ['-fecha_cierre']
        constraints = [
            models.UniqueConstraint(
                fields=['modulo', 'referencia'],
                name='uniq_ventana_modulo_referencia'),
        ]

    def __str__(self):
        return f'{self.get_modulo_display()} · {self.referencia} ' \
               f'({self.fecha_apertura} → {self.fecha_cierre})'

    def cierre_vigente(self, organismo=None):
        """Fecha de cierre aplicable hoy para `organismo`.

        Es la mayor entre el cierre general y las prórrogas vigentes del
        organismo. Las prórrogas no acortan la ventana."""
        from django.db.models import Max
        cierre = self.fecha_cierre
        if organismo is not None:
            ext = self.prorrogas.filter(
                organismo=organismo,
                fecha_cierre_extendida__gt=cierre,
            ).aggregate(m=Max('fecha_cierre_extendida'))['m']
            if ext:
                cierre = ext
        return cierre

    def esta_abierta(self, organismo=None, hoy=None):
        """Regla única de evaluación usada por servicios y vistas."""
        if not self.activa:
            return False
        hoy = hoy or timezone.localdate()
        return self.fecha_apertura <= hoy <= self.cierre_vigente(organismo)


class ProrrogaVentana(models.Model):
    """Extensión del cierre de una ventana para un organismo concreto."""

    ventana = models.ForeignKey(
        VentanaDiligenciamiento, on_delete=models.CASCADE,
        related_name='prorrogas')
    organismo = models.ForeignKey(
        Organismo, on_delete=models.CASCADE, related_name='prorrogas')
    fecha_cierre_extendida = models.DateField(
        help_text='Nuevo último día para este organismo (inclusive)')
    motivo = models.TextField()
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Prórroga de ventana'
        verbose_name_plural = 'Prórrogas de ventanas'
        ordering = ['-fecha_cierre_extendida']
        constraints = [
            models.UniqueConstraint(
                fields=['ventana', 'organismo'],
                name='uniq_prorroga_ventana_organismo'),
        ]

    def __str__(self):
        return f'{self.organismo} → {self.fecha_cierre_extendida}'

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if (self.ventana_id and self.fecha_cierre_extendida
                and self.fecha_cierre_extendida <= self.ventana.fecha_cierre):
            raise ValidationError({
                'fecha_cierre_extendida':
                    'La prórroga debe ser posterior al cierre general '
                    f'({self.ventana.fecha_cierre}).'})
