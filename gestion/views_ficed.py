"""
Submódulo FICED de Gestión (plan §3).

Dashboard de avance, usuarios (rol + subrol, matriz por organismo),
organismos (sin_pp/sin_obs), formularios (reabrir/reiniciar/restaurar)
y ventanas del periodo. Toda mutación queda en la bitácora.
"""
import secrets

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from indicadores.decorators import gestor_required
from indicadores.models import Organismo, PerfilRecolector
from indicadores.models_iced import ICEDFormulario

from .models import AccionGestion, ProrrogaVentana, VentanaDiligenciamiento
from .services import registrar_accion
from .services.avance_iced import (EQUIPOS_ICED, avance_iced,
                                   equipos_requeridos_iced, periodos_iced)
from .services.formularios_iced import (copia_formulario, reabrir_formulario,
                                        reiniciar_formulario,
                                        restaurar_formulario)
from .services.usuarios import (ROLES_FICED, actualizar_usuario_ficed,
                                 crear_usuario_ficed, relevo_usuario_ficed,
                                 restablecer_password,
                                 procesar_csv_usuarios)

ROLES_ETQ = dict(PerfilRecolector.ROL_CHOICES)
SUBROLES_ETQ = dict(PerfilRecolector.SUBROL_FICED_CHOICES)


def _organismo_sel(request):
    oid = request.GET.get('organismo')
    return int(oid) if oid and oid.isdigit() else None


# =============================================================================
# Dashboard de avance (§3.1)
# =============================================================================

@gestor_required
def dashboard(request):
    periodos = periodos_iced()
    periodo_sel = request.GET.get('periodo') or (periodos[0] if periodos else '')
    filas, stats = avance_iced(periodo_sel)

    f_org = _organismo_sel(request)
    f_estado = request.GET.get('estado', '')
    if f_org:
        filas = [r for r in filas if r['organismo'].id == f_org]
    if f_estado:
        filas = [r for r in filas
                 if r['consolidado'] and r['consolidado']['f'].estado == f_estado]

    return render(request, 'gestion/ficed/dashboard.html', {
        'pestana_activa': 'ficed',
        'filas': filas, 'stats': stats,
        'periodos': periodos, 'periodo_sel': periodo_sel,
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
        'filtros': {'organismo': f_org, 'estado': f_estado},
        'estados': ICEDFormulario.ESTADO_CHOICES,
    })


# =============================================================================
# Usuarios FICED (§3.2)
# =============================================================================

@gestor_required
def usuarios(request):
    """Lista filtrable + vista matriz por organismo."""
    qs = (PerfilRecolector.objects
          .filter(rol__in=ROLES_FICED, equipo_taller__isnull=True)
          .exclude(rol='delegado', subrol_ficed='')
          .select_related('user', 'organismo').order_by(
              'organismo__nombre', 'rol', 'user__username'))

    f_org = _organismo_sel(request)
    f_rol = request.GET.get('rol', '')
    f_subrol = request.GET.get('subrol', '')
    f_activo = request.GET.get('activo', '')
    f_q = request.GET.get('q', '').strip()

    if f_org:
        qs = qs.filter(organismo_id=f_org)
    if f_rol in ROLES_FICED:
        qs = qs.filter(rol=f_rol)
    if f_subrol:
        qs = qs.filter(subrol_ficed=f_subrol)
    if f_activo in ('0', '1'):
        qs = qs.filter(activo=f_activo == '1')
    if f_q:
        qs = (qs.filter(user__username__icontains=f_q)
              | qs.filter(user__first_name__icontains=f_q)
              | qs.filter(user__last_name__icontains=f_q)
              | qs.filter(user__email__icontains=f_q))

    # Matriz: columnas = 5 equipos + validador del organismo
    matriz = []
    if request.GET.get('vista') == 'matriz':
        orgs = (Organismo.objects.filter(activo=True)
                .order_by('nombre'))
        if f_org:
            orgs = orgs.filter(pk=f_org)
        perfiles = {p.id: p for p in qs}
        por_org = {}
        for p in qs:
            por_org.setdefault(p.organismo_id, {}).setdefault(
                (p.rol, p.subrol_ficed), []).append(p)
        for org in orgs:
            slots = {eq: [] for eq in EQUIPOS_ICED}
            validador = []
            otros = []
            for (rol, sub), ps in por_org.get(org.id, {}).items():
                if rol == 'delegado' and sub in slots:
                    slots[sub].extend(ps)
                elif rol == 'delegado':
                    otros.extend(ps)  # delegado sin subrol (formulario completo)
                elif rol == 'validador_organismo':
                    validador.extend(ps)
                else:
                    otros.extend(ps)
            requeridos = set(equipos_requeridos_iced(org))
            matriz.append({
                'organismo': org,
                'equipos': [
                    {'codigo': eq, 'usuarios': slots[eq],
                     'requerido': eq in requeridos}
                    for eq in EQUIPOS_ICED],
                'validador': validador,
                'otros': otros,
            })

    paginador = Paginator(qs, 100)
    pagina = paginador.get_page(request.GET.get('page'))

    return render(request, 'gestion/ficed/usuarios.html', {
        'pestana_activa': 'ficed',
        'pagina': pagina,
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
        'roles_ficed': [(r, ROLES_ETQ.get(r, r)) for r in ROLES_FICED],
        'subroles': [(c, t) for c, t in PerfilRecolector.SUBROL_FICED_CHOICES if c],
        'filtros': {'organismo': f_org, 'rol': f_rol, 'subrol': f_subrol,
                    'activo': f_activo, 'q': f_q},
        'vista': request.GET.get('vista', 'lista'),
        'matriz': matriz,
    })


def _usuario_gestionado(pk):
    return get_object_or_404(
        User.objects.select_related('perfil_recolector__organismo')
        .filter(perfil_recolector__rol__in=ROLES_FICED,
                perfil_recolector__equipo_taller__isnull=True)
        .exclude(perfil_recolector__rol='delegado',
                 perfil_recolector__subrol_ficed=''), pk=pk)


@gestor_required
def usuario_crear(request):
    if request.method == 'POST':
        d = request.POST
        try:
            organismo = (Organismo.objects.get(pk=d.get('organismo'))
                         if d.get('organismo') else None)
            user, estado_correo = crear_usuario_ficed(
                username=d.get('username', '').strip(),
                email=d.get('email', '').strip(),
                first_name=d.get('first_name', '').strip(),
                last_name=d.get('last_name', '').strip(),
                rol=d.get('rol', ''),
                subrol=d.get('subrol_ficed', ''),
                organismo=organismo,
                activo=d.get('activo') == '1',
                enviar_correo=d.get('enviar_correo') == '1')
        except ValidationError as e:
            for errs in e.message_dict.values():
                for m in errs:
                    messages.error(request, m)
        else:
            registrar_accion(
                request, modulo='ficed', accion='crear_usuario',
                objeto_tipo='User', objeto_id=user.pk,
                despues={'username': user.username, 'rol': d.get('rol'),
                         'subrol': d.get('subrol_ficed'),
                         'organismo_id': d.get('organismo'),
                         'correo': estado_correo})
            msg = f'Usuario {user.username} creado.'
            if estado_correo == 'enviado':
                msg += ' Credenciales enviadas por correo.'
            elif estado_correo == 'fallido':
                msg += ' ATENCIÓN: el correo falló — el usuario quedó ' \
                       'sin contraseña usable; reintente el envío.'
            elif estado_correo == 'sin_correo':
                msg += ' Sin correo registrado: no se enviaron credenciales.'
            messages.success(request, msg)
            return redirect('gestion:ficed_usuarios')

    return render(request, 'gestion/ficed/usuario_form.html', {
        'pestana_activa': 'ficed',
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
        'roles_ficed': [(r, ROLES_ETQ.get(r, r)) for r in ROLES_FICED],
        'subroles': PerfilRecolector.SUBROL_FICED_CHOICES,
        'usuario': None,
        'perfil': None,
        'post': request.POST if request.method == 'POST' else {},
    })


@gestor_required
def usuario_editar(request, user_id):
    user = _usuario_gestionado(user_id)
    perfil = user.perfil_recolector
    tiene_formularios = ICEDFormulario.objects.filter(
        usuario_diligencia=user).exists()

    if request.method == 'POST':
        d = request.POST
        org_id = d.get('organismo', '')
        organismo = (Organismo.objects.get(pk=org_id) if org_id
                     else (None if 'organismo' in d else '-'))
        try:
            antes, despues, cambios, estado_correo = actualizar_usuario_ficed(
                user,
                first_name=d.get('first_name', '').strip(),
                last_name=d.get('last_name', '').strip(),
                email=d.get('email', '').strip(),
                rol=d.get('rol') or None,
                subrol=d.get('subrol_ficed', ''),
                organismo=organismo,
                activo=d.get('activo') == '1',
                aviso_correo=d.get('aviso_correo') == '1')
        except ValidationError as e:
            for errs in e.message_dict.values():
                for m in errs:
                    messages.error(request, m)
        else:
            registrar_accion(
                request, modulo='ficed', accion='editar_usuario',
                objeto_tipo='User', objeto_id=user.pk,
                antes=antes, despues=despues,
                motivo=d.get('motivo', '').strip())
            msg = f'{user.username} actualizado.'
            if estado_correo == 'enviado':
                msg += ' Se avisó del cambio por correo.'
            elif estado_correo == 'fallido':
                msg += ' (El correo de aviso falló.)'
            messages.success(request, msg)
            return redirect('gestion:ficed_usuarios')

    return render(request, 'gestion/ficed/usuario_form.html', {
        'pestana_activa': 'ficed',
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
        'roles_ficed': [(r, ROLES_ETQ.get(r, r)) for r in ROLES_FICED],
        'subroles': PerfilRecolector.SUBROL_FICED_CHOICES,
        'usuario': user,
        'perfil': perfil,
        'tiene_formularios': tiene_formularios,
        'post': request.POST if request.method == 'POST' else {},
    })


@require_POST
@gestor_required
def usuario_accion(request, user_id):
    """Activar/desactivar, restablecer contraseña, relevo, enviar correo."""
    user = _usuario_gestionado(user_id)
    perfil = user.perfil_recolector
    accion = request.POST.get('accion', '')

    if accion in ('activar', 'desactivar'):
        activo = accion == 'activar'
        antes = {'activo': perfil.activo, 'user_is_active': user.is_active}
        perfil.activo = activo
        perfil.save(update_fields=['activo'])
        user.is_active = activo
        user.save(update_fields=['is_active'])
        registrar_accion(
            request, modulo='ficed', accion=accion,
            objeto_tipo='User', objeto_id=user.pk,
            antes=antes, despues={'activo': activo},
            motivo=request.POST.get('motivo', '').strip())
        messages.success(
            request,
            f'{user.username} {"activado" if activo else "desactivado"}.')

    elif accion == 'restablecer':
        estado = restablecer_password(user)
        registrar_accion(
            request, modulo='ficed', accion='restablecer_password',
            objeto_tipo='User', objeto_id=user.pk,
            despues={'resultado': estado})
        if estado == 'enviado':
            messages.success(request, 'Nueva contraseña temporal enviada.')
        elif estado == 'sin_correo':
            messages.error(request, 'El usuario no tiene correo registrado.')
        else:
            messages.error(request, 'El envío falló; la contraseña no cambió.')

    elif accion == 'relevo':
        try:
            estado = relevo_usuario_ficed(
                user,
                first_name=request.POST.get('first_name', '').strip(),
                last_name=request.POST.get('last_name', '').strip(),
                email=request.POST.get('email', '').strip(),
                enviar_correo=request.POST.get('enviar_correo') == '1')
        except ValidationError as e:
            for errs in e.message_dict.values():
                for m in errs:
                    messages.error(request, m)
        else:
            registrar_accion(
                request, modulo='ficed', accion='relevo_persona',
                objeto_tipo='User', objeto_id=user.pk,
                despues={'nombre': user.get_full_name(), 'correo': estado})
            messages.success(
                request,
                f'Relevo registrado. Credenciales: {estado}.')
    else:
        messages.error(request, 'Acción no reconocida.')

    return redirect(request.POST.get('next') or 'gestion:ficed_usuarios')


@require_POST
@gestor_required
def correos_masivos(request):
    """Envía credenciales a una selección de perfiles (plan §3.2)."""
    ids = request.POST.getlist('perfil')
    enviados, fallidos, sin = [], [], []
    for p in (PerfilRecolector.objects
              .filter(pk__in=ids).select_related('user')):
        estado = restablecer_password(p.user)
        registrar_accion(
            request, modulo='ficed', accion='enviar_correo_acceso',
            objeto_tipo='User', objeto_id=p.user_id,
            despues={'resultado': estado})
        {'enviado': enviados, 'fallido': fallidos,
         'sin_correo': sin}[estado].append(p.user.username)
    if enviados:
        messages.success(request, f'Correos enviados: {", ".join(enviados)}.')
    if fallidos:
        messages.error(
            request, f'Falló el envío (contraseña intacta): {", ".join(fallidos)}.')
    if sin:
        messages.warning(request, f'Sin correo registrado: {", ".join(sin)}.')
    return redirect('gestion:ficed_usuarios')


# =============================================================================
# Organismos — flags sin_pp / sin_obs (§3.3)
# =============================================================================

@gestor_required
def organismos(request):
    return render(request, 'gestion/ficed/organismos.html', {
        'pestana_activa': 'ficed',
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
    })


@require_POST
@gestor_required
def organismo_flags(request, organismo_id):
    org = get_object_or_404(Organismo, pk=organismo_id)
    antes = {'sin_pp': org.sin_pp, 'sin_obs': org.sin_obs}
    org.sin_pp = request.POST.get('sin_pp') == '1'
    org.sin_obs = request.POST.get('sin_obs') == '1'
    org.save(update_fields=['sin_pp', 'sin_obs'])
    registrar_accion(
        request, modulo='ficed', accion='editar_organismo_flags',
        objeto_tipo='Organismo', objeto_id=org.pk,
        antes=antes,
        despues={'sin_pp': org.sin_pp, 'sin_obs': org.sin_obs},
        motivo=request.POST.get('motivo', '').strip())
    messages.success(request, f'{org.nombre}: flags actualizadas.')
    return redirect('gestion:ficed_organismos')


# =============================================================================
# Formularios: reabrir / reiniciar / restaurar (§3.4)
# =============================================================================

@gestor_required
def formularios(request):
    qs = (ICEDFormulario.objects
          .select_related('organismo', 'usuario_diligencia')
          .order_by('-periodo', 'organismo__nombre', 'equipo'))
    f_periodo = request.GET.get('periodo', '')
    f_org = _organismo_sel(request)
    f_estado = request.GET.get('estado', '')
    if f_periodo:
        qs = qs.filter(periodo=f_periodo)
    if f_org:
        qs = qs.filter(organismo_id=f_org)
    if f_estado:
        qs = qs.filter(estado=f_estado)

    paginador = Paginator(qs, 50)
    pagina = paginador.get_page(request.GET.get('page'))
    return render(request, 'gestion/ficed/formularios.html', {
        'pestana_activa': 'ficed',
        'pagina': pagina,
        'periodos': periodos_iced(),
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
        'estados': ICEDFormulario.ESTADO_CHOICES,
        'filtros': {'periodo': f_periodo, 'organismo': f_org,
                    'estado': f_estado},
    })


@require_POST
@gestor_required
def formulario_accion(request, formulario_id):
    f = get_object_or_404(
        ICEDFormulario.objects.select_related('organismo'), pk=formulario_id)
    accion = request.POST.get('accion', '')
    org_nombre = f.organismo.nombre

    try:
        if accion == 'reabrir':
            antes, despues = reabrir_formulario(f)
            registrar_accion(
                request, modulo='ficed', accion='reabrir_formulario',
                objeto_tipo='ICEDFormulario', objeto_id=f.pk,
                antes=antes, despues=despues)
            messages.success(
                request, f'Formulario de {org_nombre} ({f.get_equipo_display()}) '
                         'reabierto como borrador.')

        elif accion == 'reiniciar':
            if request.POST.get('confirmar', '').strip() != org_nombre:
                messages.error(
                    request,
                    'Escriba el nombre del organismo para confirmar el reinicio.')
                return redirect('gestion:ficed_formularios')
            motivo = request.POST.get('motivo', '').strip()
            if not motivo:
                messages.error(request, 'El motivo es obligatorio para reiniciar.')
                return redirect('gestion:ficed_formularios')
            copia = reiniciar_formulario(f)
            registrar_accion(
                request, modulo='ficed', accion='reiniciar_formulario',
                objeto_tipo='ICEDFormulario', objeto_id=f.pk,
                antes=copia, despues=None, motivo=motivo)
            messages.success(
                request,
                f'Formulario de {org_nombre} ({f.get_equipo_display()}) '
                'reiniciado. La copia quedó en la bitácora.')

        elif accion == 'restaurar':
            accion_id = request.POST.get('accion_id')
            reg = get_object_or_404(AccionGestion, pk=accion_id,
                                  accion='reiniciar_formulario')
            nuevo = restaurar_formulario(reg.antes)
            registrar_accion(
                request, modulo='ficed', accion='restaurar_formulario',
                objeto_tipo='ICEDFormulario', objeto_id=nuevo.pk,
                antes=None,
                despues={'restaurado_de_accion': reg.pk},
                motivo=request.POST.get('motivo', '').strip())
            messages.success(request, f'Formulario restaurado (#{nuevo.pk}).')
        else:
            messages.error(request, 'Acción no reconocida.')
    except ValidationError as e:
        messages.error(request, '; '.join(e.messages))

    return redirect('gestion:ficed_formularios')


# =============================================================================
# Ventanas FICED (§3.5)
# =============================================================================

@gestor_required
def ventanas(request):
    qs = (VentanaDiligenciamiento.objects
          .filter(modulo='ficed')
          .prefetch_related('prorrogas__organismo')
          .order_by('-fecha_cierre'))
    hoy = timezone.localdate()
    for v in qs:
        v.estado = 'abierta' if v.esta_abierta(hoy=hoy) else 'cerrada'
        v.prorrogas_vigentes = [p for p in v.prorrogas.all()
                                if p.fecha_cierre_extendida >= hoy]
    return render(request, 'gestion/ficed/ventanas.html', {
        'pestana_activa': 'ficed',
        'ventanas': qs, 'hoy': hoy,
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
    })


@require_POST
@gestor_required
def ventana_guardar(request):
    """Crea o actualiza la ventana FICED de un periodo."""
    from django.utils.dateparse import parse_date
    referencia = request.POST.get('referencia', '').strip()
    apertura = parse_date(request.POST.get('fecha_apertura', ''))
    cierre = parse_date(request.POST.get('fecha_cierre', ''))
    activa = request.POST.get('activa') == '1'

    if not referencia or not apertura or not cierre:
        messages.error(request, 'Referencia y fechas son obligatorias.')
        return redirect('gestion:ficed_ventanas')
    if cierre < apertura:
        messages.error(request, 'El cierre no puede ser anterior a la apertura.')
        return redirect('gestion:ficed_ventanas')

    ventana, creada = VentanaDiligenciamiento.objects.update_or_create(
        modulo='ficed', referencia=referencia,
        defaults={'fecha_apertura': apertura, 'fecha_cierre': cierre,
                  'activa': activa,
                  'mensaje_cerrado': request.POST.get('mensaje_cerrado', '')})
    registrar_accion(
        request, modulo='ficed', accion='crear_ventana' if creada else 'editar_ventana',
        objeto_tipo='VentanaDiligenciamiento', objeto_id=ventana.pk,
        despues={'referencia': referencia, 'apertura': str(apertura),
                 'cierre': str(cierre), 'activa': activa},
        motivo=request.POST.get('motivo', '').strip())
    messages.success(
        request,
        f'Ventana {referencia} {"creada" if creada else "actualizada"}.')
    return redirect('gestion:ficed_ventanas')


@require_POST
@gestor_required
def prorroga_crear(request, ventana_id):
    from django.utils.dateparse import parse_date
    ventana = get_object_or_404(VentanaDiligenciamiento, pk=ventana_id,
                                modulo='ficed')
    organismo = get_object_or_404(Organismo, pk=request.POST.get('organismo'))
    extendida = parse_date(request.POST.get('fecha_cierre_extendida', ''))
    motivo = request.POST.get('motivo', '').strip()

    try:
        if not extendida or not motivo:
            raise ValidationError('La nueva fecha y el motivo son obligatorios.')
        prorroga, creada = ProrrogaVentana.objects.update_or_create(
            ventana=ventana, organismo=organismo,
            defaults={'fecha_cierre_extendida': extendida, 'motivo': motivo,
                      'creado_por': request.user})
        if not creada:
            prorroga.full_clean()
            prorroga.save()
        else:
            prorroga.full_clean()
    except ValidationError as e:
        messages.error(request, '; '.join(e.messages))
        return redirect('gestion:ficed_ventanas')

    registrar_accion(
        request, modulo='ficed', accion='prorroga_ventana',
        objeto_tipo='VentanaDiligenciamiento', objeto_id=ventana.pk,
        despues={'organismo': organismo.nombre,
                 'hasta': str(extendida)},
        motivo=motivo)
    messages.success(
        request,
        f'Prórroga para {organismo.nombre} hasta {extendida:%d/%m/%Y}.')
    return redirect('gestion:ficed_ventanas')


# =============================================================================
# Carga masiva de usuarios por CSV (§3.2)
# =============================================================================

@gestor_required
def carga_masiva(request):
    """CSV → validación previa (dry-run) → aplicar por fila."""
    ctx = {'pestana_activa': 'ficed',
           'ejemplo': 'username,nombres,apellidos,correo,organismo,rol,'
                      'subrol_ficed,activo,enviar_correo'}
    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        aplicar = request.POST.get('aplicar') == '1'
        if not archivo:
            messages.error(request, 'Adjunte un archivo CSV.')
        elif not archivo.name.lower().endswith('.csv'):
            messages.error(request, 'El archivo debe ser .csv.')
        else:
            try:
                filas = procesar_csv_usuarios(archivo, aplicar=aplicar)
            except Exception as e:
                messages.error(request, f'No se pudo leer el CSV: {e}')
            else:
                n_ok = sum(1 for f in filas if f['estado'] in ('ok', 'creado'))
                n_err = sum(1 for f in filas if f['estado'] == 'error')
                if aplicar:
                    creados = [f for f in filas if f['estado'] == 'creado']
                    registrar_accion(
                        request, modulo='ficed', accion='carga_masiva',
                        objeto_tipo='User', objeto_id='csv',
                        despues={'creados': len(creados),
                                 'errores': n_err,
                                 'usernames': [f['datos']['username']
                                              for f in creados]},
                        motivo=request.POST.get('motivo', '').strip())
                    messages.success(
                        request,
                        f'{len(creados)} usuario(s) creados, '
                        f'{n_err} fila(s) con error.')
                ctx.update({'filas': filas, 'n_ok': n_ok, 'n_err': n_err,
                            'aplicado': aplicar})
    return render(request, 'gestion/ficed/carga_masiva.html', ctx)


@gestor_required
def usuarios_plantilla(request):
    """Plantilla CSV descargable de usuarios FICED."""
    import csv as _csv
    import io as _io
    from django.http import HttpResponse
    out = _io.StringIO()
    w = _csv.writer(out)
    w.writerow(['username', 'nombres', 'apellidos', 'correo',
                'organismo', 'rol', 'subrol_ficed', 'activo',
                'enviar_correo'])
    w.writerow(['delegado_etpp_org', 'Nombre', 'Apellido',
                'delegado@org.gov.co', 'ETPP', 'delegado', 'ETPP',
                '1', '1'])
    r = HttpResponse(out.getvalue(),
                     content_type='text/csv; charset=utf-8')
    r['Content-Disposition'] = (
        'attachment; filename="plantilla_usuarios_ficed.csv"')
    return r
