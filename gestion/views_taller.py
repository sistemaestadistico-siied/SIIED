"""
Submódulo Taller de Gestión de Datos (plan §4).

- Dashboard: mismo contexto de `views_taller._dashboard_context`,
  bajo `gestor_required` (decisión 7: gestor y validadores lo ven con
  la visibilidad existente).
- Estructura: árbol Organismo → Suborganismo → Equipo (activar/
  desactivar, renombrar, crear; nada se borra).
- Usuarios Taller: delegados con `equipo_taller` permanente en perfil y
  analistas SIIED. Cuentas personales, separadas del FICED.
- Inscripciones: lista por edición/organismo; reasignar, reabrir,
  reiniciar (con copia) y conciliación de equipos.
- Ventanas del taller por edición (año).
"""
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from indicadores.decorators import gestor_required
from indicadores.models import (EquipoOrganismo, Organismo,
                                PerfilRecolector, Suborganismo)
from indicadores.models_taller import InscripcionTaller
from .models import ProrrogaVentana, VentanaDiligenciamiento
from .services import registrar_accion, serializar
from .services import taller as st
from .services.usuarios import restablecer_password

ROLES_ETQ = dict(PerfilRecolector.ROL_CHOICES)


def _ediciones():
    return (InscripcionTaller.objects
            .order_by('-edicion')
            .values_list('edicion', flat=True).distinct())


# =============================================================================
# Dashboard (reutiliza el contexto del taller, decisión 7)
# =============================================================================

@gestor_required
def dashboard(request):
    """Delega en el reporte del taller de Analítica (misma visibilidad)."""
    url = reverse('indicadores:analitica_taller_reportes')
    alcance = request.GET.get('alcance')
    if alcance:
        url += f'?alcance={alcance}'
    return redirect(url)


# =============================================================================
# Estructura Organismo → Suborganismo → Equipo (§4.0)
# =============================================================================

@gestor_required
def estructura(request):
    organismos = (Organismo.objects
                  .prefetch_related('suborganismos__equipos')
                  .order_by('nombre'))
    return render(request, 'gestion/taller/estructura.html', {
        'pestana_activa': 'taller',
        'organismos': organismos,
    })


@require_POST
@gestor_required
def estructura_accion(request):
    """Crea/renombra/activa/desactiva nodos del árbol."""
    accion = request.POST.get('accion', '')
    try:
        if accion == 'crear_suborganismo':
            org = get_object_or_404(Organismo,
                                    pk=request.POST.get('organismo'))
            sub = st.crear_suborganismo(
                organismo=org,
                nombre=request.POST.get('nombre', '').strip())
            registrar_accion(
                request, modulo='taller', accion='crear_suborganismo',
                objeto_tipo='Suborganismo', objeto_id=sub.pk,
                despues={'nombre': sub.nombre, 'organismo': org.nombre})
            messages.success(request, f'Suborganismo «{sub.nombre}» creado.')

        elif accion == 'crear_equipo':
            sub = get_object_or_404(Suborganismo,
                                    pk=request.POST.get('suborganismo'))
            eq = st.crear_equipo(
                suborganismo=sub,
                nombre=request.POST.get('nombre', '').strip())
            registrar_accion(
                request, modulo='taller', accion='crear_equipo',
                objeto_tipo='EquipoOrganismo', objeto_id=eq.pk,
                despues={'nombre': eq.nombre, 'suborganismo': sub.nombre})
            messages.success(request, f'Equipo «{eq.nombre}» creado.')

        elif accion in ('renombrar_suborganismo', 'renombrar_equipo'):
            modelo = (Suborganismo if 'suborganismo' in accion
                      else EquipoOrganismo)
            obj = get_object_or_404(modelo, pk=request.POST.get('pk'))
            antes = st.renombrar(obj, request.POST.get('nombre', '').strip())
            registrar_accion(
                request, modulo='taller', accion=accion,
                objeto_tipo=modelo.__name__, objeto_id=obj.pk,
                antes={'nombre': antes}, despues={'nombre': obj.nombre})
            messages.success(request, f'«{antes}» → «{obj.nombre}».')

        elif accion in ('desactivar_suborganismo', 'activar_suborganismo'):
            sub = get_object_or_404(Suborganismo,
                                    pk=request.POST.get('pk'))
            if accion.startswith('desactivar'):
                st.desactivar_suborganismo(sub)
            else:
                st.activar_suborganismo(sub)
            registrar_accion(
                request, modulo='taller', accion=accion,
                objeto_tipo='Suborganismo', objeto_id=sub.pk,
                despues={'activo': sub.activo})
            messages.success(request, f'«{sub.nombre}» actualizado.')

        elif accion in ('desactivar_equipo', 'activar_equipo'):
            eq = get_object_or_404(EquipoOrganismo,
                                   pk=request.POST.get('pk'))
            if accion.startswith('desactivar'):
                st.desactivar_equipo(eq)
            else:
                st.activar_equipo(eq)
            registrar_accion(
                request, modulo='taller', accion=accion,
                objeto_tipo='EquipoOrganismo', objeto_id=eq.pk,
                despues={'activo': eq.activo})
            messages.success(request, f'«{eq.nombre}» actualizado.')
        else:
            messages.error(request, 'Acción no reconocida.')
    except ValidationError as e:
        messages.error(request, '; '.join(e.messages))
    return redirect('gestion:taller_estructura')


# =============================================================================
# Usuarios Taller (§4) — delegados con equipo permanente + analistas
# =============================================================================

@gestor_required
def usuarios(request):
    qs = (PerfilRecolector.objects
          .filter(rol__in=('delegado', 'analista'))
          .exclude(rol='delegado', equipo_taller__isnull=True)
          .select_related('user', 'organismo',
                          'equipo_taller__suborganismo__organismo')
          .order_by('organismo__nombre', 'user__username'))

    f_org = request.GET.get('organismo', '')
    f_eq = request.GET.get('equipo', '')
    f_q = request.GET.get('q', '').strip()
    if f_org.isdigit():
        qs = qs.filter(organismo_id=f_org)
    if f_eq.isdigit():
        qs = qs.filter(equipo_taller_id=f_eq)
    if f_q:
        qs = (qs.filter(user__username__icontains=f_q)
              | qs.filter(user__first_name__icontains=f_q)
              | qs.filter(user__last_name__icontains=f_q)
              | qs.filter(user__email__icontains=f_q))

    paginador = Paginator(qs, 100)
    pagina = paginador.get_page(request.GET.get('page'))
    return render(request, 'gestion/taller/usuarios.html', {
        'pestana_activa': 'taller',
        'pagina': pagina,
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
        'equipos': (EquipoOrganismo.objects
                    .select_related('suborganismo__organismo')
                    .order_by('suborganismo__organismo__nombre', 'nombre')),
        'filtros': {'organismo': f_org, 'equipo': f_eq, 'q': f_q},
    })


def _usuarios_taller_post(request, crear=True, user=None):
    """Crea o edita un usuario del taller. Devuelve (ok, user, estado)."""
    d = request.POST
    org = (Organismo.objects.get(pk=d.get('organismo'))
           if d.get('organismo') else None)
    eq = (EquipoOrganismo.objects.get(pk=d.get('equipo'))
          if d.get('equipo') else None)
    edicion = d.get('edicion') or timezone.now().year
    try:
        edicion = int(edicion)
    except (TypeError, ValueError):
        edicion = timezone.now().year

    if crear:
        return st.crear_usuario_taller(
            username=d.get('username', '').strip(),
            email=d.get('email', '').strip(),
            first_name=d.get('first_name', '').strip(),
            last_name=d.get('last_name', '').strip(),
            rol=d.get('rol', 'delegado'),
            organismo=org, equipo=eq, edicion=edicion,
            activo=d.get('activo') == '1',
            enviar_correo=d.get('enviar_correo') == '1') + (None,)

    # Edición: nombre/correo + perfil
    perfil = user.perfil_recolector
    antes = serializar(perfil)
    antes.update({'first_name': user.first_name,
                  'last_name': user.last_name, 'email': user.email})
    try:
        st._validar_taller(perfil.rol, org or perfil.organismo, eq,
                           perfil.subrol_ficed)
    except ValidationError:
        raise
    user.first_name = d.get('first_name', '').strip()
    user.last_name = d.get('last_name', '').strip()
    user.email = d.get('email', '').strip()
    user.is_active = d.get('activo') == '1'
    user.save()
    if org and org.pk != perfil.organismo_id:
        st.cambiar_organismo_taller(perfil, org)
    if eq is not None and eq.pk != perfil.equipo_taller_id:
        st.asignar_equipo_taller(perfil, eq, edicion)
    elif eq is None and perfil.equipo_taller_id:
        st.asignar_equipo_taller(perfil, None, None)
    if d.get('rol') and d.get('rol') != perfil.rol:
        perfil.rol = d.get('rol')
        perfil.save(update_fields=['rol'])
    perfil.activo = user.is_active
    perfil.save(update_fields=['activo'])
    return user, 'omitido', antes


@gestor_required
def usuario_crear(request):
    if request.method == 'POST':
        try:
            user, estado_correo, _ = _usuarios_taller_post(request, crear=True)
        except ValidationError as e:
            for errs in e.message_dict.values():
                for m in errs:
                    messages.error(request, m)
        else:
            registrar_accion(
                request, modulo='taller', accion='crear_usuario',
                objeto_tipo='User', objeto_id=user.pk,
                despues={'username': user.username,
                         'equipo': request.POST.get('equipo'),
                         'correo': estado_correo})
            msg = f'Usuario {user.username} creado.'
            if estado_correo == 'enviado':
                msg += ' Credenciales enviadas.'
            elif estado_correo == 'fallido':
                msg += ' El correo falló; reintente el envío.'
            messages.success(request, msg)
            return redirect('gestion:taller_usuarios')

    edicion_sel = request.GET.get('edicion') or timezone.now().year
    return render(request, 'gestion/taller/usuario_form.html', {
        'pestana_activa': 'taller',
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
        'edicion': edicion_sel,
        'usuario': None, 'perfil': None,
        'post': request.POST if request.method == 'POST' else {},
        'roles_taller': [('delegado', 'Delegado (diligencia el taller)'),
                         ('analista', 'Analista SIIED (revisa)')],
    })


@gestor_required
def usuario_editar(request, user_id):
    user = get_object_or_404(
        User.objects.select_related('perfil_recolector__organismo',
                                    'perfil_recolector__equipo_taller')
        .filter(perfil_recolector__rol__in=('delegado', 'analista'))
        .exclude(perfil_recolector__rol='delegado',
                 perfil_recolector__equipo_taller__isnull=True),
        pk=user_id)
    perfil = user.perfil_recolector
    inscripciones = user.inscripciones_taller.count()

    if request.method == 'POST':
        try:
            _, _, antes = _usuarios_taller_post(request, crear=False,
                                                user=user)
        except ValidationError as e:
            for errs in e.message_dict.values():
                for m in errs:
                    messages.error(request, m)
        else:
            registrar_accion(
                request, modulo='taller', accion='editar_usuario',
                objeto_tipo='User', objeto_id=user.pk,
                antes=antes, despues=serializar(perfil),
                motivo=request.POST.get('motivo', '').strip())
            if inscripciones:
                messages.warning(
                    request,
                    f'{user.username} tiene {inscripciones} inscripción(es) '
                    'histórica(s): el cambio de equipo no las reasigna.')
            messages.success(request, f'{user.username} actualizado.')
            return redirect('gestion:taller_usuarios')

    return render(request, 'gestion/taller/usuario_form.html', {
        'pestana_activa': 'taller',
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
        'edicion': perfil.equipo_taller_edicion or timezone.now().year,
        'usuario': user, 'perfil': perfil,
        'inscripciones': inscripciones,
        'post': request.POST if request.method == 'POST' else {},
        'roles_taller': [('delegado', 'Delegado (diligencia el taller)'),
                         ('analista', 'Analista SIIED (revisa)')],
    })


@require_POST
@gestor_required
def usuario_accion(request, user_id):
    user = get_object_or_404(
        User.objects.filter(
            perfil_recolector__rol__in=('delegado', 'analista'))
        .exclude(perfil_recolector__rol='delegado',
                 perfil_recolector__equipo_taller__isnull=True),
        pk=user_id)
    accion = request.POST.get('accion', '')
    perfil = user.perfil_recolector

    if accion in ('activar', 'desactivar'):
        activo = accion == 'activar'
        perfil.activo = activo
        perfil.save(update_fields=['activo'])
        user.is_active = activo
        user.save(update_fields=['is_active'])
        registrar_accion(
            request, modulo='taller', accion=accion,
            objeto_tipo='User', objeto_id=user.pk,
            despues={'activo': activo})
        messages.success(
            request, f'{user.username} {"activado" if activo else "desactivado"}.')
    elif accion == 'restablecer':
        estado = restablecer_password(user)
        registrar_accion(
            request, modulo='taller', accion='restablecer_password',
            objeto_tipo='User', objeto_id=user.pk,
            despues={'resultado': estado})
        messages.success(request, f'Resultado del envío: {estado}.')
    else:
        messages.error(request, 'Acción no reconocida.')
    return redirect('gestion:taller_usuarios')


# API para el selector en cascada Organismo → Suborganismo → Equipo
@gestor_required
def api_suborganismos(request, organismo_id):
    from django.http import JsonResponse
    data = list(Suborganismo.objects
                .filter(organismo_id=organismo_id, activo=True)
                .order_by('nombre').values('id', 'nombre'))
    return JsonResponse({'suborganismos': data})


@gestor_required
def api_equipos(request, suborganismo_id):
    from django.http import JsonResponse
    data = list(EquipoOrganismo.objects
                .filter(suborganismo_id=suborganismo_id, activo=True)
                .order_by('nombre').values('id', 'nombre'))
    return JsonResponse({'equipos': data})


# =============================================================================
# Inscripciones (§4)
# =============================================================================

@gestor_required
def inscripciones(request):
    qs = (InscripcionTaller.objects
          .select_related('organismo', 'suborganismo', 'equipo', 'user')
          .order_by('-edicion', 'organismo__nombre', '-creado'))
    f_edicion = request.GET.get('edicion', '')
    f_org = request.GET.get('organismo', '')
    f_estado = request.GET.get('estado', '')
    f_sin_equipo = request.GET.get('sin_equipo', '')
    if f_edicion.isdigit():
        qs = qs.filter(edicion=int(f_edicion))
    if f_org.isdigit():
        qs = qs.filter(organismo_id=int(f_org))
    if f_estado:
        qs = qs.filter(estado=f_estado)
    if f_sin_equipo == '1':
        qs = qs.filter(equipo__isnull=True)

    paginador = Paginator(qs, 50)
    pagina = paginador.get_page(request.GET.get('page'))
    return render(request, 'gestion/taller/inscripciones.html', {
        'pestana_activa': 'taller',
        'pagina': pagina,
        'ediciones': _ediciones(),
        'organismos': Organismo.objects.order_by('nombre'),
        'estados': InscripcionTaller.Estado.choices,
        'n_sin_equipo': st.inscripciones_sin_equipo().count(),
        'filtros': {'edicion': f_edicion, 'organismo': f_org,
                    'estado': f_estado, 'sin_equipo': f_sin_equipo},
    })


@require_POST
@gestor_required
def inscripcion_accion(request, inscripcion_id):
    ins = get_object_or_404(
        InscripcionTaller.objects.select_related('organismo'),
        pk=inscripcion_id)
    accion = request.POST.get('accion', '')
    try:
        if accion == 'reabrir':
            antes, despues = st.reabrir_inscripcion(ins)
            registrar_accion(
                request, modulo='taller', accion='reabrir_inscripcion',
                objeto_tipo='InscripcionTaller', objeto_id=ins.pk,
                antes=antes, despues=despues)
            messages.success(request, 'Inscripción reabierta.')

        elif accion == 'reiniciar':
            if request.POST.get('confirmar', '').strip() != ins.organismo.nombre:
                messages.error(
                    request,
                    'Escriba el nombre del organismo para confirmar el reinicio.')
                return redirect('gestion:taller_inscripciones')
            motivo = request.POST.get('motivo', '').strip()
            if not motivo:
                messages.error(request, 'El motivo es obligatorio para reiniciar.')
                return redirect('gestion:taller_inscripciones')
            copia = st.reiniciar_inscripcion(ins)
            registrar_accion(
                request, modulo='taller', accion='reiniciar_inscripcion',
                objeto_tipo='InscripcionTaller', objeto_id=ins.pk,
                antes=copia, despues=None, motivo=motivo)
            messages.success(request, 'Inscripción reiniciada; copia en bitácora.')

        elif accion == 'reasignar':
            org = (Organismo.objects.get(pk=request.POST.get('organismo'))
                   if request.POST.get('organismo') else None)
            eq_id = request.POST.get('equipo', '')
            eq = (EquipoOrganismo.objects.get(pk=eq_id)
                  if eq_id else None)
            antes, despues = st.reasignar_inscripcion(
                ins, organismo=org, equipo=eq)
            registrar_accion(
                request, modulo='taller', accion='reasignar_inscripcion',
                objeto_tipo='InscripcionTaller', objeto_id=ins.pk,
                antes=antes, despues=despues,
                motivo=request.POST.get('motivo', '').strip())
            messages.success(request, 'Inscripción reasignada.')

        elif accion == 'asignar_equipo':
            eq = get_object_or_404(EquipoOrganismo,
                                   pk=request.POST.get('equipo'))
            antes, despues = st.reasignar_inscripcion(ins, equipo=eq)
            registrar_accion(
                request, modulo='taller', accion='conciliar_equipo',
                objeto_tipo='InscripcionTaller', objeto_id=ins.pk,
                antes=antes, despues=despues)
            messages.success(request, f'Equipo «{eq.nombre}» asignado.')
        else:
            messages.error(request, 'Acción no reconocida.')
    except ValidationError as e:
        messages.error(request, '; '.join(e.messages))
    return redirect(request.POST.get('next') or 'gestion:taller_inscripciones')


@gestor_required
def conciliacion(request):
    """Inscripciones con `equipo_responsable` en texto, sin equipo FK."""
    qs = st.inscripciones_sin_equipo(
        int(request.GET['edicion']) if request.GET.get('edicion', '').isdigit()
        else None)
    return render(request, 'gestion/taller/conciliacion.html', {
        'pestana_activa': 'taller',
        'inscripciones': qs,
        'ediciones': _ediciones(),
        'equipos': (EquipoOrganismo.objects
                    .select_related('suborganismo__organismo')
                    .order_by('suborganismo__organismo__nombre', 'nombre')),
        'edicion_sel': request.GET.get('edicion', ''),
    })


# =============================================================================
# Ventanas del taller por edición (§4)
# =============================================================================

@gestor_required
def ventanas(request):
    qs = (VentanaDiligenciamiento.objects
          .filter(modulo='taller')
          .prefetch_related('prorrogas__organismo')
          .order_by('-fecha_cierre'))
    hoy = timezone.localdate()
    for v in qs:
        v.estado = ('abierta' if v.esta_abierta(hoy=hoy)
              else ('programada' if v.activa and v.fecha_apertura > hoy
                    else 'cerrada'))
        v.prorrogas_vigentes = [p for p in v.prorrogas.all()
                                if p.fecha_cierre_extendida >= hoy]
    return render(request, 'gestion/taller/ventanas.html', {
        'pestana_activa': 'taller',
        'ventanas': qs, 'hoy': hoy,
        'organismos': Organismo.objects.filter(activo=True).order_by('nombre'),
        'ediciones': _ediciones(),
    })


@require_POST
@gestor_required
def ventana_guardar(request):
    from django.utils.dateparse import parse_date
    referencia = request.POST.get('referencia', '').strip()
    apertura = parse_date(request.POST.get('fecha_apertura', ''))
    cierre = parse_date(request.POST.get('fecha_cierre', ''))
    activa = request.POST.get('activa') == '1'
    if not referencia or not apertura or not cierre:
        messages.error(request, 'Referencia y fechas son obligatorias.')
        return redirect('gestion:taller_ventanas')
    ventana, creada = VentanaDiligenciamiento.objects.update_or_create(
        modulo='taller', referencia=referencia,
        defaults={'fecha_apertura': apertura, 'fecha_cierre': cierre,
                  'activa': activa,
                  'mensaje_cerrado': request.POST.get('mensaje_cerrado', '')})
    registrar_accion(
        request, modulo='taller',
        accion='crear_ventana' if creada else 'editar_ventana',
        objeto_tipo='VentanaDiligenciamiento', objeto_id=ventana.pk,
        despues={'referencia': referencia, 'apertura': str(apertura),
                 'cierre': str(cierre), 'activa': activa},
        motivo=request.POST.get('motivo', '').strip())
    messages.success(
        request, f'Ventana {referencia} guardada.')
    return redirect('gestion:taller_ventanas')


@require_POST
@gestor_required
def prorroga_crear(request, ventana_id):
    from django.utils.dateparse import parse_date
    ventana = get_object_or_404(VentanaDiligenciamiento, pk=ventana_id,
                                modulo='taller')
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
        prorroga.full_clean()
        prorroga.save()
    except ValidationError as e:
        messages.error(request, '; '.join(e.messages))
        return redirect('gestion:taller_ventanas')
    registrar_accion(
        request, modulo='taller', accion='prorroga_ventana',
        objeto_tipo='VentanaDiligenciamiento', objeto_id=ventana.pk,
        despues={'organismo': organismo.nombre, 'hasta': str(extendida)},
        motivo=motivo)
    messages.success(request, f'Prórroga para {organismo.nombre}.')
    return redirect('gestion:taller_ventanas')


# =============================================================================
# Carga masiva de usuarios por CSV
# =============================================================================

@gestor_required
def carga_masiva(request):
    """CSV → validación previa (dry-run) → aplicar por fila."""
    ctx = {'pestana_activa': 'taller',
           'ejemplo': 'username,nombres,apellidos,correo,organismo,'
                      'equipo,rol,edicion,activo,enviar_correo'}
    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        aplicar = request.POST.get('aplicar') == '1'
        if not archivo:
            messages.error(request, 'Adjunte un archivo CSV.')
        elif not archivo.name.lower().endswith('.csv'):
            messages.error(request, 'El archivo debe ser .csv.')
        else:
            try:
                filas = st.procesar_csv_usuarios_taller(archivo,
                                                        aplicar=aplicar)
            except Exception as e:
                messages.error(request, f'No se pudo leer el CSV: {e}')
            else:
                n_ok = sum(1 for f in filas
                           if f['estado'] in ('ok', 'creado'))
                n_err = sum(1 for f in filas if f['estado'] == 'error')
                if aplicar:
                    creados = [f for f in filas if f['estado'] == 'creado']
                    registrar_accion(
                        request, modulo='taller', accion='carga_masiva',
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
    return render(request, 'gestion/taller/carga_masiva.html', ctx)


@gestor_required
def usuarios_plantilla(request):
    """Plantilla CSV descargable de usuarios del taller."""
    import csv as _csv
    import io as _io
    from django.http import HttpResponse
    out = _io.StringIO()
    w = _csv.writer(out)
    w.writerow(['username', 'nombres', 'apellidos', 'correo',
                'organismo', 'equipo', 'rol', 'edicion', 'activo',
                'enviar_correo'])
    w.writerow(['ana.gomez', 'Ana', 'Gómez', 'ana@org.gov.co',
                'ETPP', 'Equipos TIC', 'delegado', '2026', '1', '1'])
    r = HttpResponse(out.getvalue(),
                     content_type='text/csv; charset=utf-8')
    r['Content-Disposition'] = (
        'attachment; filename="plantilla_usuarios_taller.csv"')
    return r
