"""Ventanas de diligenciamiento: evaluación única para vistas y wizards."""
from dataclasses import dataclass
from typing import Optional

from django.utils import timezone

from ..models import VentanaDiligenciamiento


@dataclass
class EstadoVentana:
    """Resultado de evaluar `ventana_abierta`."""
    abierta: bool
    configurada: bool          # False si no existe ventana para la referencia
    ventana: Optional[VentanaDiligenciamiento] = None
    prorroga: object = None    # ProrrogaVentana vigente, si aplica
    cierre_vigente: object = None
    mensaje: str = ''


def ventana_abierta(modulo, referencia, organismo=None, hoy=None):
    """Evalúa si el diligenciamiento está abierto.

    Reglas (plan §3.5):
    - Sin ventana configurada para (modulo, referencia): ABIERTA
      (mantiene el comportamiento actual de FICED y Taller).
    - Ventana inactiva, o hoy fuera de [apertura, cierre vigente]: cerrada.
    - El cierre vigente es el mayor entre `fecha_cierre` y las prórrogas
      del organismo; las prórrogas no acortan la ventana.
    - `organismo=None` evalúa solo la ventana general.
    """
    ventana = (VentanaDiligenciamiento.objects
               .filter(modulo=modulo, referencia=referencia)
               .first())
    if ventana is None:
        return EstadoVentana(abierta=True, configurada=False)

    hoy = hoy or timezone.localdate()
    cierre = ventana.cierre_vigente(organismo)
    prorroga = None
    if organismo is not None and cierre > ventana.fecha_cierre:
        prorroga = (ventana.prorrogas
                    .filter(organismo=organismo,
                            fecha_cierre_extendida=cierre)
                    .first())

    abierta = ventana.esta_abierta(organismo=organismo, hoy=hoy)
    mensaje = '' if abierta else (
        ventana.mensaje_cerrado
        or 'El periodo de diligenciamiento está cerrado. '
           'Si necesita una prórroga, contacte al equipo SIIED.')
    return EstadoVentana(
        abierta=abierta, configurada=True, ventana=ventana,
        prorroga=prorroga, cierre_vigente=cierre, mensaje=mensaje)
