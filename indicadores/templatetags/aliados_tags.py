from django import template
from ..models import Aliado

register = template.Library()

@register.simple_tag
def get_aliados():
    """Obtiene todos los aliados activos ordenados por orden"""
    return Aliado.objects.filter(activo=True).order_by('orden', 'nombre')
