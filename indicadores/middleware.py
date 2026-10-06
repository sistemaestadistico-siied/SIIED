import time
import threading
from django.http import JsonResponse
from django.core.cache import cache


def _log_visit_async(path, user_id, ip, user_agent, referer):
    """Guarda la visita en un thread separado para no bloquear la respuesta."""
    from indicadores.models import PageVisit
    try:
        PageVisit.objects.create(
            path=path,
            user_id=user_id,
            ip_address=ip,
            user_agent=user_agent,
            referer=referer,
        )
    except Exception:
        pass  # Silenciar errores de logging para no afectar al usuario


class PageVisitMiddleware:
    """
    Middleware que registra visitas a páginas HTML del sitio.
    Ignora requests a archivos estáticos, media, APIs internas y POST/PUT/DELETE.
    Usa un throttle de 5 segundos por IP + path para evitar saturar la DB.
    """

    SKIP_PATHS = (
        # Archivos estáticos y media
        '/static/', '/media/', '/admin/static/',
        # APIs internas (AJAX)
        '/api/', '/admin/monitoring/api/',
        '/recoleccion/api/', '/api/wizard/',
        # Admin de Django (navegación interna, no visitas públicas)
        '/admin/',
        # Dashboard de visitas (self-referencia)
        '/reportes/visitas/',
        # Monitoring dashboard
        '/monitoring/',
        # Archivos misceláneos
        '/favicon.ico', '/robots.txt', '/sitemap.xml',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._maybe_log(request)
        return self.get_response(request)

    def _maybe_log(self, request):
        # Solo GET
        if request.method != 'GET':
            return

        path = request.path

        # Ignorar paths de archivos estáticos y APIs
        if any(path.startswith(p) for p in self.SKIP_PATHS):
            return

        ip = self._get_client_ip(request)

        # Throttle: max 1 registro cada 5 segundos por IP + path
        throttle_key = f'pagevisit_throttle_{ip}_{path}'
        if cache.get(throttle_key):
            return
        cache.set(throttle_key, True, 5)

        user_id = request.user.id if request.user.is_authenticated else None
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:512]
        referer = request.META.get('HTTP_REFERER', '')[:2048]

        threading.Thread(
            target=_log_visit_async,
            args=(path, user_id, ip, user_agent, referer),
            daemon=True,
        ).start()

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class ChatRateLimitMiddleware:
    """Middleware simple para limitar requests al chat"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/chat/message/'):
            # Obtener IP del cliente
            ip = self.get_client_ip(request)
            
            # Clave de cache para rate limiting
            cache_key = f'chat_rate_limit_{ip}'
            
            # Verificar límite (5 mensajes por minuto por IP)
            current_count = cache.get(cache_key, 0)
            
            if current_count >= 5:
                return JsonResponse({
                    'error': 'Demasiadas consultas. Espera un momento antes de continuar.',
                    'retry_after': 60
                }, status=429)
            
            # Incrementar contador
            cache.set(cache_key, current_count + 1, 60)

        return self.get_response(request)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
