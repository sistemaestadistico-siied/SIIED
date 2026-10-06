from django import template
from django.conf import settings

register = template.Library()

@register.inclusion_tag('indicadores/chat_widget.html')
def chat_widget():
    """Incluye el widget de chat en cualquier template"""
    return {
        'chat_enabled': hasattr(settings, 'OPENROUTER_API_KEY') and settings.OPENROUTER_API_KEY
    }

@register.simple_tag
def chat_script():
    """Incluye el script del chat"""
    return """
    <script>
        // Configuración global del chat
        window.ChatConfig = {
            apiUrl: '/chat/',
            enabled: true
        };
    </script>
    """

