"""
Decoradores personalizados para control de acceso por roles
"""
from functools import wraps
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required


def recolector_required(view_func):
    """
    Decorador que verifica que el usuario tenga permisos de recolector.
    Permite acceso a:
    - Usuarios staff (administradores)
    - Usuarios con perfil de recolector activo y rol 'recolector' o 'ambos'
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Si no está autenticado, redirigir al login
        if not request.user.is_authenticated:
            return redirect('indicadores:recoleccion_login')
        
        # Los administradores (staff) tienen acceso total
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Verificar si tiene perfil de recolector
        if hasattr(request.user, 'perfil_recolector'):
            perfil = request.user.perfil_recolector
            if perfil.puede_recolectar():
                return view_func(request, *args, **kwargs)
        
        # Si no tiene permisos, agregar mensaje solo si no existe ya
        storage = messages.get_messages(request)
        mensaje_existe = any('No tiene permisos de recolector' in str(m) for m in storage)
        if not mensaje_existe:
            messages.error(request, 'No tiene permisos de recolector')
        
        return redirect('indicadores:acceso_modulos')
    
    return wrapper


def consultor_reportes_required(view_func):
    """
    Decorador que verifica que el usuario tenga permisos de consultor de reportes.
    Permite acceso a:
    - Usuarios staff (administradores)
    - Usuarios con perfil activo y rol 'consultor' o 'ambos'
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Si no está autenticado, redirigir al login
        if not request.user.is_authenticated:
            return redirect('indicadores:reportes_login')
        
        # Los administradores (staff) tienen acceso total
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Verificar si tiene perfil con permisos de consultor
        if hasattr(request.user, 'perfil_recolector'):
            perfil = request.user.perfil_recolector
            if perfil.puede_consultar_reportes():
                return view_func(request, *args, **kwargs)
        
        # Si no tiene permisos, agregar mensaje solo si no existe ya
        storage = messages.get_messages(request)
        mensaje_existe = any('No tiene permisos para acceder al módulo de reportes' in str(m) for m in storage)
        if not mensaje_existe:
            messages.error(request, 'No tiene permisos para acceder al módulo de reportes')
        
        return redirect('indicadores:acceso_modulos')
    
    return wrapper


def delegado_required(view_func):
    """
    Decorador para el portal del Delegado de Organismo.
    Permite acceso a usuarios con rol 'delegado' activo.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('indicadores:delegado_login')
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        if hasattr(request.user, 'perfil_recolector'):
            perfil = request.user.perfil_recolector
            if perfil.es_delegado():
                return view_func(request, *args, **kwargs)
        messages.error(request, 'No tiene permisos de delegado de organismo.')
        return redirect('indicadores:delegado_login')
    return wrapper


def validador_required(view_func):
    """
    Decorador para el panel de Validación (Estadísticos SIIED).
    Permite acceso a usuarios con rol 'validador' o staff.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('indicadores:validacion_login')
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        if hasattr(request.user, 'perfil_recolector'):
            perfil = request.user.perfil_recolector
            if perfil.es_validador():
                return view_func(request, *args, **kwargs)
        messages.error(request, 'No tiene permisos de validador estadístico.')
        return redirect('indicadores:validacion_login')
    return wrapper


def admin_required(view_func):
    """
    Decorador que verifica que el usuario sea staff (administrador).
    Solo permite acceso a usuarios con is_staff=True
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Si no está autenticado, redirigir al login de admin
        if not request.user.is_authenticated:
            return redirect('/admin/login/')
        
        # Verificar si es staff
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Si no es staff, agregar mensaje solo si no existe ya
        storage = messages.get_messages(request)
        mensaje_existe = any('Debe ser administrador' in str(m) for m in storage)
        if not mensaje_existe:
            messages.error(request, 'Debe ser administrador para acceder a esta sección')
        
        return redirect('indicadores:acceso_modulos')
    
    return wrapper


def editor_required(view_func):
    """
    Decorador para el módulo Editorial.
    Permite acceso a usuarios con rol 'editor' activo o staff.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Debe iniciar sesión para acceder al módulo editorial.')
            return redirect('indicadores:editorial_login')
        
        # Los administradores (staff) tienen acceso total
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Verificar si tiene perfil de editor
        if hasattr(request.user, 'perfil_recolector'):
            perfil = request.user.perfil_recolector
            if perfil.puede_editar_contenidos():
                return view_func(request, *args, **kwargs)
        
        messages.error(request, 'No tiene permisos para acceder al módulo editorial.')
        return redirect('indicadores:index')
    
    return wrapper


def taller_login_required(view_func):
    """
    Módulo taller/catálogo: requiere usuario autenticado de cualquier rol
    (delegado, recolector, validador, staff...). Redirige al login del
    portal delegado (la entrada pública de autenticación).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('indicadores:delegado_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def taller_staff_required(view_func):
    """
    Dashboard/reportes del taller: solo usuarios staff o superusuarios.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('indicadores:delegado_login')
        if not request.user.is_staff:
            messages.error(request, 'Esta sección es solo para el equipo del SIIED.')
            return redirect('indicadores:taller_landing')
        return view_func(request, *args, **kwargs)
    return wrapper


def laboratorio_login_required(view_func):
    """
    Consulta y Tableros: la herramienta es de uso público, pero guardar y
    consultar tableros requiere sesión iniciada.

    - Peticiones POST/fetch: responde JSON 401 con la URL de login (el front
      muestra el aviso en el chat en lugar de recibir un HTML de login).
    - Peticiones GET: redirige al login del portal conservando ?next= para
      volver al tablero tras autenticarse.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)

        if request.method == 'POST':
            # El next debe ser la pagina origen (Referer), no este endpoint
            # POST — tras el login redirigir a el daria 405.
            origen = request.META.get('HTTP_REFERER', '')
            next_path = request.path  # fallback razonable
            if origen:
                from urllib.parse import urlparse
                parsed = urlparse(origen)
                if parsed.netloc == request.get_host():
                    next_path = parsed.path or request.path
            login_url = (
                f"{reverse('indicadores:delegado_login')}?next={next_path}")
            return JsonResponse(
                {
                    'ok': False,
                    'error': 'Inicia sesión para guardar y consultar tableros.',
                    'login_url': login_url,
                },
                status=401)
        return redirect(
            f"{reverse('indicadores:delegado_login')}"
            f"?next={request.get_full_path()}")
    return wrapper
