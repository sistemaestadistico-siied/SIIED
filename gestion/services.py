"""
Servicios del módulo Gestión: auditoría y ventanas de diligenciamiento.

La lógica de negocio vive aquí, fuera de las vistas, para testearla sin
HTTP y reutilizarla desde validación y los wizards de FICED/Taller.
"""
from dataclasses import dataclass
from typing import Optional

from django.utils import timezone

from .models import AccionGestion, VentanaDiligenciamiento


def _ip_de(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def registrar_accion(request=None, *, modulo, accion, objeto_tipo='',
                     objeto_id='', antes=None, despues=None, motivo='',
                     usuario=None):
    """Escribe una acción del módulo en la bitácora.

    Uso: pasar `request` (saca usuario e IP) o `usuario` directamente
    (comandos, tareas). Devuelve el registro creado.
    """
    ip = _ip_de(request) if request is not None else None
    if usuario is None and request is not None:
        u = request.user
        usuario = u if getattr(u, 'is_authenticated', False) else None
    return AccionGestion.objects.create(
        usuario=usuario, ip=ip, modulo=modulo, accion=accion,
        objeto_tipo=objeto_tipo,
        objeto_id=str(objeto_id) if objeto_id not in (None, '') else '',
        antes=antes, despues=despues, motivo=motivo or '')


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


def serializar(obj):
    """Serializa un objeto a dict JSON para guardarlo en la bitácora."""
    from django.forms.models import model_to_dict
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    try:
        data = model_to_dict(obj)
        return {k: (str(v) if not isinstance(
            v, (int, float, bool, str, list, dict, type(None))) else v)
            for k, v in data.items()}
    except Exception:
        return {'str': str(obj)}
