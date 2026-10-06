"""
Template tags para manejar URLs con prefijo de proxy.

Este módulo proporciona template tags que facilitan la construcción
de URLs que funcionen correctamente detrás de un proxy reverso.
"""

from django import template
from django.conf import settings
from django.urls import reverse

register = template.Library()


@register.simple_tag
def proxy_url(viewname, *args, **kwargs):
    """
    Template tag que genera una URL con el prefijo FORCE_SCRIPT_NAME.
    
    Es equivalente a {% url %} pero añade automáticamente el prefijo del proxy.
    
    Uso en templates:
        {% load proxy_tags %}
        <a href="{% proxy_url 'indicadores:home' %}">Inicio</a>
        <a href="{% proxy_url 'indicadores:dominio_detalle' slug='economia' %}">Economía</a>
    
    Args:
        viewname: Nombre de la vista (igual que en {% url %})
        *args: Argumentos posicionales para la URL
        **kwargs: Argumentos con nombre para la URL
        
    Returns:
        str: URL completa con el prefijo del proxy
    """
    script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
    url = reverse(viewname, args=args, kwargs=kwargs)
    
    # Si ya tiene el prefijo, no lo duplicamos
    if script_name and url.startswith(script_name):
        return url
    
    return f"{script_name}{url}"


@register.simple_tag
def proxy_static(path):
    """
    Template tag para URLs de archivos estáticos con prefijo de proxy.
    
    Uso en templates:
        {% load proxy_tags %}
        <img src="{% proxy_static 'indicadores/images/logo.png' %}">
        <link rel="stylesheet" href="{% proxy_static 'css/style.css' %}">
    
    Args:
        path: Ruta relativa del archivo estático
        
    Returns:
        str: URL completa del archivo estático con prefijo del proxy
    """
    from django.templatetags.static import static
    return static(path)


@register.simple_tag
def proxy_media(path):
    """
    Template tag para URLs de archivos media con prefijo de proxy.
    
    Uso en templates:
        {% load proxy_tags %}
        <img src="{% proxy_media 'uploads/foto.jpg' %}">
    
    Args:
        path: Ruta relativa del archivo media
        
    Returns:
        str: URL completa del archivo media con prefijo del proxy
    """
    script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
    media_url = settings.MEDIA_URL
    
    # MEDIA_URL ya incluye el script_name por configuración en settings
    return f"{media_url}{path}"


@register.simple_tag
def script_prefix():
    """
    Template tag que retorna el prefijo del script (FORCE_SCRIPT_NAME).
    
    Útil para construir URLs personalizadas en JavaScript o HTML.
    
    Uso en templates:
        {% load proxy_tags %}
        <script>
            const SCRIPT_PREFIX = "{% script_prefix %}";
            const apiUrl = SCRIPT_PREFIX + "/api/data/";
        </script>
        
    Returns:
        str: El valor de FORCE_SCRIPT_NAME ('' en desarrollo, '/proxy.php' en producción)
    """
    return getattr(settings, 'FORCE_SCRIPT_NAME', '')


@register.filter
def add_proxy_prefix(url):
    """
    Filtro que añade el prefijo del proxy a una URL.
    
    Uso en templates:
        {% load proxy_tags %}
        <a href="{{ my_url|add_proxy_prefix }}">Link</a>
        
    Args:
        url: URL a la que añadir el prefijo
        
    Returns:
        str: URL con el prefijo del proxy
    """
    if not url:
        return url
        
    script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
    
    # Si ya tiene el prefijo, no lo duplicamos
    if script_name and url.startswith(script_name):
        return url
    
    # Si la URL es absoluta (empieza con http:// o https://), no añadimos prefijo
    if url.startswith(('http://', 'https://', '//')):
        return url
    
    # Si la URL no empieza con /, la añadimos
    if not url.startswith('/'):
        url = f'/{url}'
    
    return f"{script_name}{url}"
