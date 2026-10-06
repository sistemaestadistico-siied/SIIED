from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Permite acceder a un diccionario con una clave dinámica en templates."""
    if dictionary is None:
        return None
    return dictionary.get(key)
