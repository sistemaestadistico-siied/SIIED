"""
Template filters personalizados para la configuración del chat
"""
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Obtiene un item de un diccionario usando una clave
    Uso: {{ dict|get_item:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)
