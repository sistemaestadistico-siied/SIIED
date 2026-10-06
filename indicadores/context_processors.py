"""
Context processors para la aplicación indicadores.

Este módulo proporciona context processors que añaden variables
globales a todos los templates de la aplicación.
"""

from django.conf import settings


def script_name(request):
    """
    Context processor que expone FORCE_SCRIPT_NAME en todos los templates.
    
    Esto permite usar {{ SCRIPT_NAME }} en templates para construir URLs
    que funcionen correctamente detrás de un proxy reverso.
    
    Ejemplo en template:
        <a href="{{ SCRIPT_NAME }}/mi-ruta/">Link</a>
        
    En desarrollo: SCRIPT_NAME = ''
    En producción: SCRIPT_NAME = '/proxy.php'
    
    Returns:
        dict: Diccionario con la variable SCRIPT_NAME
    """
    return {
        'SCRIPT_NAME': getattr(settings, 'FORCE_SCRIPT_NAME', ''),
    }
