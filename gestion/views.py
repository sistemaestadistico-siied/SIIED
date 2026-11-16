"""
Vistas del módulo Gestión de Talleres y Formularios.

Hub con pestañas FICED · Taller · Encuestas y la bitácora de acciones.
El acceso lo controla `gestor_required` (staff + gestor_formularios
activo); el resto del sitio usa la sesión estándar de Django.
"""
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, \
    logout as auth_logout
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from indicadores.decorators import gestor_required
from indicadores.models import Organismo

from .models import (AccionGestion, ProrrogaVentana,
                     VentanaDiligenciamiento)
from .services import registrar_accion


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
        # Throttle por IP + usuario: 10 intentos fallidos / 5 min
        from django.core.cache import cache
        ip = (request.META.get('HTTP_X_FORWARDED_FOR', '')
              .split(',')[0].strip()
              or request.META.get('REMOTE_ADDR', ''))
        clave = f'login_gestion:{ip}:{username}'
        if (cache.get(clave) or 0) >= 10:
            messages.error(
                request,
                'Demasiados intentos. Espere unos minutos e intente de nuevo.')
            return render(request, 'gestion/login.html',
                          {'next': siguiente})
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
            cache.set(clave, (cache.get(clave) or 0) + 1, 300)
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


# =============================================================================
# Ventanas de diligenciamiento — administración transversal (antes solo admin)
# =============================================================================

@gestor_required
def ventanas(request):
    """Lista todas las ventanas (cualquier módulo) con sus prórrogas."""
    qs = (VentanaDiligenciamiento.objects
          .prefetch_related('prorrogas__organismo')
          .order_by('modulo', '-fecha_cierre'))
    hoy = timezone.localdate()
    for v in qs:
        v.estado = 'abierta' if v.esta_abierta(hoy=hoy) else 'cerrada'
        v.prorrogas_vigentes = [p for p in v.prorrogas.all()
                                if p.fecha_cierre_extendida >= hoy]
    from encuestas.models import Formulario
    return render(request, 'gestion/ventanas.html', {
        'pestana_activa': 'hub',
        'ventanas': qs, 'hoy': hoy,
        'modulos': VentanaDiligenciamiento.MODULO_CHOICES,
        'organismos': Organismo.objects.filter(activo=True)
                                     .order_by('nombre'),
        'formularios': Formulario.objects.filter(estado='publicado')
                                       .order_by('-pk')[:20],
    })


@require_POST
@gestor_required
def ventana_guardar(request):
    """Crea o actualiza una ventana (módulo + referencia)."""
    modulo = request.POST.get('modulo', '')
    referencia = request.POST.get('referencia', '').strip()
    apertura = parse_date(request.POST.get('fecha_apertura', ''))
    cierre = parse_date(request.POST.get('fecha_cierre', ''))
    activa = request.POST.get('activa') == '1'

    modulos_validos = dict(VentanaDiligenciamiento.MODULO_CHOICES)
    if modulo not in modulos_validos or modulo == 'gestion':
        messages.error(request, 'Módulo inválido para la ventana.')
        return redirect('gestion:ventanas')
    if not referencia or not apertura or not cierre:
        messages.error(request, 'Referencia y fechas son obligatorias.')
        return redirect('gestion:ventanas')
    if cierre < apertura:
        messages.error(request,
                       'El cierre no puede ser anterior a la apertura.')
        return redirect('gestion:ventanas')

    ventana, creada = VentanaDiligenciamiento.objects.update_or_create(
        modulo=modulo, referencia=referencia,
        defaults={'fecha_apertura': apertura, 'fecha_cierre': cierre,
                  'activa': activa,
                  'mensaje_cerrado': request.POST.get('mensaje_cerrado',
                                                      '')})
    registrar_accion(
        request, modulo='gestion',
        accion='crear_ventana' if creada else 'editar_ventana',
        objeto_tipo='gestion.VentanaDiligenciamiento', objeto_id=ventana.pk,
        despues={'modulo': modulo, 'referencia': referencia,
                 'apertura': str(apertura), 'cierre': str(cierre),
                 'activa': activa},
        motivo=request.POST.get('motivo', '').strip())
    messages.success(
        request,
        f'Ventana {modulo}/{referencia} '
        f'{"creada" if creada else "actualizada"}.')
    return redirect('gestion:ventanas')


@require_POST
@gestor_required
def ventana_prorroga(request, ventana_id):
    """Otorga o actualiza la prórroga de una ventana para un organismo."""
    ventana = get_object_or_404(VentanaDiligenciamiento, pk=ventana_id)
    organismo = get_object_or_404(Organismo,
                                  pk=request.POST.get('organismo'))
    extendida = parse_date(request.POST.get('fecha_cierre_extendida', ''))
    motivo = request.POST.get('motivo', '').strip()

    try:
        if not extendida or not motivo:
            raise ValidationError(
                'La nueva fecha y el motivo son obligatorios.')
        prorroga, creada = ProrrogaVentana.objects.update_or_create(
            ventana=ventana, organismo=organismo,
            defaults={'fecha_cierre_extendida': extendida,
                      'motivo': motivo, 'creado_por': request.user})
        prorroga.full_clean()
    except ValidationError as e:
        messages.error(request, '; '.join(e.messages))
        return redirect('gestion:ventanas')

    registrar_accion(
        request, modulo='gestion', accion='prorroga_ventana',
        objeto_tipo='gestion.VentanaDiligenciamiento', objeto_id=ventana.pk,
        despues={'organismo': organismo.nombre, 'hasta': str(extendida)},
        motivo=motivo)
    messages.success(
        request,
        f'Prórroga para {organismo.nombre} hasta {extendida:%d/%m/%Y}.')
    return redirect('gestion:ventanas')


@require_POST
@gestor_required
def ventana_borrar(request, ventana_id):
    """Elimina una ventana (el módulo queda abierto, comportamiento por
    defecto)."""
    ventana = get_object_or_404(VentanaDiligenciamiento, pk=ventana_id)
    datos = {'modulo': ventana.modulo, 'referencia': ventana.referencia}
    ventana.delete()
    registrar_accion(
        request, modulo='gestion', accion='eliminar_ventana',
        objeto_tipo='gestion.VentanaDiligenciamiento', objeto_id=ventana_id,
        antes=datos, motivo=request.POST.get('motivo', '').strip())
    messages.success(
        request,
        f'Ventana {datos["modulo"]}/{datos["referencia"]} eliminada.')
    return redirect('gestion:ventanas')


@gestor_required
def usuarios_diccionario(request):
    """Diccionario CSV descargable con los valores válidos para la
    carga masiva del módulo indicado con `?modulo=`:
    ficed → organismos + roles + subroles;
    taller → organismos + roles + equipos;
    encuestas → roles."""
    import csv as _csv
    import io as _io
    from django.http import HttpResponse
    from indicadores.models import EquipoOrganismo, PerfilRecolector

    modulo = request.GET.get('modulo', 'ficed')
    if modulo not in ('ficed', 'taller', 'encuestas'):
        modulo = 'ficed'

    out = _io.StringIO()
    w = _csv.writer(out)
    w.writerow(['seccion', 'codigo', 'nombre', 'detalle'])

    if modulo in ('ficed', 'taller'):
        for o in Organismo.objects.filter(activo=True).order_by('nombre'):
            w.writerow(['organismo', o.codigo, o.nombre,
                        'Use nombre o codigo en la columna organismo'])

    roles = {
        'ficed': [
            ('delegado', 'Delegado del organismo'),
            ('validador_organismo', 'Pre-validación del organismo'),
            ('validador', 'Validador estadístico'),
        ],
        'taller': [
            ('delegado', 'Delegado del organismo (requiere equipo)'),
            ('analista', 'Analista SIIED'),
        ],
        'encuestas': [
            ('diligenciador', 'Responde encuestas a su nombre'),
            ('encuestador', 'Captura por varias personas'),
        ],
    }
    for codigo, detalle in roles[modulo]:
        w.writerow(['rol', codigo, codigo, detalle])

    if modulo == 'ficed':
        for codigo, nombre in PerfilRecolector.SUBROL_FICED_CHOICES:
            w.writerow(['subrol_ficed', codigo or '(vacio)',
                        nombre or 'Todos los equipos',
                        'Solo aplica a delegados'])

    if modulo == 'taller':
        for eq in (EquipoOrganismo.objects
                   .filter(activo=True)
                   .select_related('suborganismo__organismo')
                   .order_by('suborganismo__organismo__nombre',
                             'suborganismo__nombre', 'nombre')):
            w.writerow(['equipo', eq.codigo, eq.nombre,
                        f'{eq.suborganismo.organismo.nombre} / '
                        f'{eq.suborganismo.nombre}'])

    r = HttpResponse(out.getvalue(),
                     content_type='text/csv; charset=utf-8')
    r['Content-Disposition'] = (
        f'attachment; filename="diccionario_usuarios_{modulo}.csv"')
    return r
