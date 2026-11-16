"""
Vistas del módulo Gestión de Talleres y Formularios.

Hub con pestañas FICED · Taller · Encuestas y la bitácora de acciones.
El acceso lo controla `gestor_required` (staff + gestor_formularios
activo); el resto del sitio usa la sesión estándar de Django.
"""
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, \
    logout as auth_logout
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from indicadores.decorators import gestor_required

from .models import AccionGestion, VentanaDiligenciamiento


def _perfil(user):
    return getattr(user, 'perfil_recolector', None)


def gestion_login(request):
    """Login del módulo (mismo patrón que validación)."""
    siguiente = request.POST.get('next') or request.GET.get('next') or ''
    if not url_has_allowed_host_and_scheme(
            siguiente, allowed_hosts={request.get_host()}):
        siguiente = ''

    if request.user.is_authenticated:
        perfil = _perfil(request.user)
        if request.user.is_staff or (perfil and perfil.es_gestor()):
            return redirect(siguiente or 'gestion:hub')
        auth_logout(request)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            perfil = _perfil(user)
            if user.is_staff or (perfil and perfil.es_gestor()):
                auth_login(request, user)
                messages.success(
                    request,
                    f'Bienvenido/a, {user.get_full_name() or user.username}')
                return redirect(siguiente or 'gestion:hub')
            messages.error(
                request,
                'Tu cuenta no tiene permisos de gestión de formularios. '
                'Contacta al administrador.')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'gestion/login.html', {'next': siguiente})


def gestion_logout(request):
    auth_logout(request)
    messages.success(request, 'Sesión cerrada.')
    return redirect('gestion:login')


@gestor_required
def hub(request):
    """Entrada del módulo: estado de ventanas y accesos a los submódulos."""
    ventanas = (VentanaDiligenciamiento.objects
                .prefetch_related('prorrogas')
                .order_by('modulo', '-fecha_cierre'))
    hoy = timezone.localdate()
    for v in ventanas:
        v.estado = 'abierta' if v.esta_abierta(hoy=hoy) else 'cerrada'
        v.n_prorrogas = v.prorrogas.filter(
            fecha_cierre_extendida__gte=hoy).count()
    return render(request, 'gestion/hub.html', {
        'pestana_activa': 'hub',
        'ventanas': ventanas,
        'hoy': hoy,
    })


@gestor_required
def bitacora(request):
    """Bitácora de acciones del módulo, filtrable."""
    qs = AccionGestion.objects.select_related('usuario')

    f_modulo = request.GET.get('modulo', '')
    f_accion = request.GET.get('accion', '').strip()
    f_usuario = request.GET.get('usuario', '').strip()
    f_objeto = request.GET.get('objeto', '').strip()
    f_desde = request.GET.get('desde', '')
    f_hasta = request.GET.get('hasta', '')

    if f_modulo in dict(AccionGestion.MODULO_CHOICES):
        qs = qs.filter(modulo=f_modulo)
    if f_accion:
        qs = qs.filter(accion__icontains=f_accion)
    if f_usuario:
        qs = qs.filter(usuario__username__icontains=f_usuario)
    if f_objeto:
        qs = qs.filter(objeto_id__icontains=f_objeto) \
             | qs.filter(objeto_tipo__icontains=f_objeto)
    if f_desde:
        qs = qs.filter(fecha__date__gte=f_desde)
    if f_hasta:
        qs = qs.filter(fecha__date__lte=f_hasta)

    paginador = Paginator(qs, 50)
    pagina = paginador.get_page(request.GET.get('page'))

    # Conservar los filtros en la paginación
    params = request.GET.copy()
    params.pop('page', None)
    qs_params = params.urlencode()

    return render(request, 'gestion/bitacora.html', {
        'pestana_activa': 'bitacora',
        'pagina': pagina,
        'filtros': {
            'modulo': f_modulo, 'accion': f_accion, 'usuario': f_usuario,
            'objeto': f_objeto, 'desde': f_desde, 'hasta': f_hasta,
        },
        'modulos': AccionGestion.MODULO_CHOICES,
        'qs_params': qs_params,
    })
