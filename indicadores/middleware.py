import re
import time
import threading
from django.http import JsonResponse
from django.core.cache import cache


def _normalizar_path(path):
    """Normaliza un path para conteo correcto: minúsculas, colapsa
    slashes repetidos y sin slash final (salvo la raíz)."""
    p = re.sub(r'/+', '/', path).strip().lower()
    if len(p) > 1 and p.endswith('/'):
        p = p.rstrip('/')
    return p or '/'


def _categoria_visita(path):
    """Clasifica un path ya normalizado en pagina | api | mcp.
    Devuelve None si el path no debe registrarse (ruido/interno)."""
    from indicadores.models import PageVisit
    C = PageVisit.Categoria

    # MCP (Streamable HTTP — usa POST, no solo GET)
    if path == '/mcp' or path.startswith('/mcp/'):
        return C.MCP

    # Nunca registrar: interno, estático o ruido de bots/navegadores
    SKIP_PREFIXES = (
        '/static/', '/media/', '/admin/',
        '/monitoring/', '/reportes/visitas/',
        '/recoleccion/api/', '/api/wizard/', '/api/educativos/',
        '/api/test_', '/admin/monitoring/api/',
        '/.well-known/', '/favicon', '/robots', '/sitemap',
        '/apple-touch-icon', '/wp-', '/.env', '/phpmyadmin',
        '/chat/message/', '/chat/api/',
    )
    if path == '/api' or any(path.startswith(p) for p in SKIP_PREFIXES):
        return None
    # Archivos sueltos (favicons colados, assets, sondas de bots)
    if re.search(r'\.(png|jpe?g|gif|ico|svg|css|js|map|woff2?|ttf|eot|'
                 r'txt|xml|pdf|zip|php\d?|env)$', path):
        return None

    # API abierta: endpoints públicos /api/... y documentación
    if (path.startswith('/api/')
            or path.startswith('/api-docs') or path.startswith('/apidocs')
            or path.startswith('/api-documentation')):
        return C.API

    return C.PAGINA


def _log_visit_async(path, categoria, user_id, ip, user_agent, referer):
    """Guarda la visita en un thread separado para no bloquear la respuesta."""
    from indicadores.models import PageVisit
    try:
        PageVisit.objects.create(
            path=path,
            categoria=categoria,
            user_id=user_id,
            ip_address=ip,
            user_agent=user_agent,
            referer=referer,
        )
    except Exception:
        pass  # Silenciar errores de logging para no afectar al usuario


class PageVisitMiddleware:
    """
    Middleware que registra visitas del sitio en tres categorías:
    pagina (HTML), api (endpoints de la API abierta) y mcp.
    Ignora estáticos, media, admin, APIs internas y ruido de bots.
    Usa un throttle de 5 segundos por IP + path para no saturar la DB.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._maybe_log(request)
        return self.get_response(request)

    def _maybe_log(self, request):
        from indicadores.models import PageVisit

        path = _normalizar_path(request.path)
        categoria = _categoria_visita(path)
        if categoria is None:
            return

        # Solo GET — excepto MCP, que es JSON-RPC sobre POST
        if request.method != 'GET' and categoria != PageVisit.Categoria.MCP:
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
            args=(path, categoria, user_id, ip, user_agent, referer),
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
