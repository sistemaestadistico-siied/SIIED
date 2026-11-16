"""Filtros del renderizador dinámico de formularios."""
from django import template

from ..tipos import tipo_de

register = template.Library()


@register.filter
def widget_partial(pregunta):
    """Plantilla del widget del tipo de la pregunta."""
    return tipo_de(pregunta).partial


@register.filter
def get(diccionario, clave):
    """Acceso a dict desde plantilla: `valores|get:p.pk`."""
    if not hasattr(diccionario, 'get'):
        return None
    return diccionario.get(clave)


@register.filter
def ficha_valor(objeto, campo):
    """Atributo de un objeto por nombre: `fi|ficha_valor:'objetivo'`."""
    return getattr(objeto, campo, '')


@register.filter
def seleccionado(valor, opcion_id):
    """¿La opción (id) está dentro del valor guardado?"""
    if valor is None:
        return False
    if isinstance(valor, dict):
        return valor.get('opcion_id') == opcion_id
    if isinstance(valor, list):
        return any(isinstance(v, dict) and v.get('opcion_id') == opcion_id
                   for v in valor)
    return False
