from django import template
from django.utils import timezone
from ..models import Evento

register = template.Library()

@register.simple_tag
def get_eventos_proximos(limit=6, days_prior=7):
    """Obtiene los próximos eventos activos, incluyendo eventos recientes"""
    now = timezone.now()
    from datetime import timedelta
    
    # Incluir eventos desde 7 días antes hasta el futuro
    start_date = now - timedelta(days=days_prior)
    
    return Evento.objects.filter(
        activo=True,
        fecha_inicio__gte=start_date
    ).order_by('fecha_inicio')[:limit]

@register.simple_tag
def get_eventos_destacados(limit=3):
    """Obtiene los eventos destacados próximos"""
    now = timezone.now()
    return Evento.objects.filter(
        activo=True,
        destacado=True,
        fecha_inicio__gte=now
    ).order_by('fecha_inicio')[:limit]
