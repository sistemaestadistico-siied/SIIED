"""
Template filters para serialización JSON
"""
from django import template
import json

register = template.Library()

@register.filter(name='tojson')
def tojson(value):
    """Convierte un objeto Python a JSON string"""
    if value is None:
        return '{}'
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return '{}'
