"""Auditoría transversal: toda mutación del módulo queda en AccionGestion."""
from ..models import AccionGestion


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
