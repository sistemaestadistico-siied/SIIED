"""
Vistas del módulo Encuestas (plan §5).

Dos frentes:
- Gestión (`gestor_required`, montadas bajo /gestion/encuestas/):
  lista, crear, constructor de estructura con autoguardado JSON,
  distribución (modos + asignaciones + invitaciones), publicar/cerrar/
  duplicar, resultados y exportación.
- Respuesta (montadas bajo /encuestas/): pendientes del diligenciador,
  captura del encuestador y el enlace público por slug/invitación.
"""
import csv
import io
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import (FileResponse, Http404, HttpResponse,
                         JsonResponse)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from gestion.models import VentanaDiligenciamiento
from gestion.services import registrar_accion, serializar
from indicadores.decorators import gestor_required
from indicadores.models import Organismo, PerfilRecolector

from .models import (Adjunto, Asignacion, Envio, Formulario, Invitacion,
                     Opcion, Pregunta, Respondiente, RespuestaItem, Seccion)
from .services import envios as se
from .services import exportar as sx
from .services import formularios as sf
from .services import offline as so
from .tipos import TIPOS, choices as tipos_choices, tipo_de


# =============================================================================
# Gestión — lista y ciclo de vida
# =============================================================================

def _gestion_ctx(request):
    return {'pestana_activa': 'encuestas'}


@gestor_required
def lista(request):
    qs = Formulario.objects.select_related('ventana').order_by('-actualizado')
    f_estado = request.GET.get('estado', '')
    f_tipo = request.GET.get('tipo', '')
    f_q = request.GET.get('q', '').strip()
    if f_estado:
        qs = qs.filter(estado=f_estado)
    if f_tipo:
        qs = qs.filter(tipo=f_tipo)
    if f_q:
        qs = qs.filter(titulo__icontains=f_q) | qs.filter(slug__icontains=f_q)

    paginador = Paginator(qs, 25)
    pagina = paginador.get_page(request.GET.get('page'))
    ctx = _gestion_ctx(request)
    ctx.update({
        'pagina': pagina,
        'tipos': Formulario.TIPO_CHOICES,
        'estados': Formulario.ESTADO_CHOICES,
        'filtros': {'estado': f_estado, 'tipo': f_tipo, 'q': f_q},
    })
    return render(request, 'gestion/encuestas/lista.html', ctx)


@gestor_required
def crear(request):
    if request.method == 'POST':
        try:
            f = sf.crear_formulario(
                titulo=request.POST.get('titulo', '').strip(),
                tipo=request.POST.get('tipo', 'encuesta'),
                descripcion=request.POST.get('descripcion', '').strip(),
                creador=request.user)
        except ValidationError as e:
            for errs in e.message_dict.values():
                for m in errs:
                    messages.error(request, m)
        else:
            registrar_accion(
                request, modulo='encuesta', accion='crear_formulario',
                objeto_tipo='encuestas.Formulario', objeto_id=f.pk,
                despues={'titulo': f.titulo, 'slug': f.slug})
            return redirect('gestion:encuestas_constructor', formulario_id=f.pk)
    ctx = _gestion_ctx(request)
    ctx['tipos'] = Formulario.TIPO_CHOICES
    ctx['post'] = request.POST if request.method == 'POST' else {}
    return render(request, 'gestion/encuestas/crear.html', ctx)


@require_POST
@gestor_required
def accion(request, formulario_id):
    f = get_object_or_404(Formulario, pk=formulario_id)
    accion = request.POST.get('accion', '')
    try:
        if accion == 'publicar':
            sf.publicar(f)
            registrar_accion(request, modulo='encuesta',
                             accion='publicar_formulario',
                             objeto_tipo='encuestas.Formulario',
                             objeto_id=f.pk)
            messages.success(request, f'«{f.titulo}» publicado.')
        elif accion == 'cerrar':
            sf.cerrar(f)
            registrar_accion(request, modulo='encuesta',
                             accion='cerrar_formulario',
                             objeto_tipo='encuestas.Formulario',
                             objeto_id=f.pk,
                             motivo=request.POST.get('motivo', '').strip())
            messages.success(request, f'«{f.titulo}» cerrado.')
        elif accion == 'reabrir':
            sf.reabrir(f)
            registrar_accion(request, modulo='encuesta',
                             accion='reabrir_formulario',
                             objeto_tipo='encuestas.Formulario',
                             objeto_id=f.pk)
            messages.success(request, f'«{f.titulo}» reabierto.')
        elif accion == 'archivar':
            sf.archivar(f)
            registrar_accion(request, modulo='encuesta',
                             accion='archivar_formulario',
                             objeto_tipo='encuestas.Formulario',
                             objeto_id=f.pk,
                             motivo=request.POST.get('motivo', '').strip())
            messages.success(request, f'«{f.titulo}» archivado.')
        elif accion == 'duplicar':
            nuevo = sf.duplicar(f)
            registrar_accion(
                request, modulo='encuesta', accion='duplicar_formulario',
                objeto_tipo='encuestas.Formulario', objeto_id=f.pk,
                despues={'nuevo_id': nuevo.pk})
            messages.success(
                request, f'Copia «{nuevo.titulo}» creada como borrador.')
            return redirect('gestion:encuestas_constructor',
                            formulario_id=nuevo.pk)
        else:
            messages.error(request, 'Acción no reconocida.')
    except ValidationError as e:
        messages.error(request, '; '.join(e.messages))
    return redirect('gestion:encuestas_lista')


# =============================================================================
# Gestión — constructor de estructura (§5.4)
# =============================================================================

def _estructura_json(f):
    secciones = []
    for sec in f.secciones.prefetch_related('preguntas__opciones'):
        secciones.append({
            'id': sec.pk, 'orden': sec.orden,
            'titulo': sec.titulo, 'descripcion': sec.descripcion,
            'preguntas': [{
                'id': p.pk, 'orden': p.orden, 'tipo': p.tipo,
                'enunciado': p.enunciado, 'ayuda': p.ayuda,
                'obligatoria': p.obligatoria, 'codigo': p.codigo,
                'config': p.config,
                'opciones': [{
                    'id': o.pk, 'orden': o.orden, 'texto': o.texto,
                    'es_otro': o.es_otro} for o in p.opciones.all()],
            } for p in sec.preguntas.all()],
        })
    return {
        'id': f.pk, 'slug': f.slug, 'titulo': f.titulo,
        'estado': f.estado, 'bloqueada': f.estructura_bloqueada,
        'secciones': secciones,
    }


@gestor_required
def constructor(request, formulario_id):
    f = get_object_or_404(Formulario, pk=formulario_id)
    ctx = _gestion_ctx(request)
    ctx.update({
        'f': f,
        'estructura': _estructura_json(f),
        'tipos_pregunta': [{'clave': c, 'etiqueta': e}
                           for c, e in tipos_choices()],
        'tipos_con_opciones': [
            k for k, t in TIPOS.items() if t.tiene_opciones],
    })
    return render(request, 'gestion/encuestas/constructor.html', ctx)


def _jpost(request):
    try:
        return json.loads(request.body.decode() or '{}')
    except json.JSONDecodeError:
        return {}


@gestor_required
def api_estructura(request, formulario_id):
    """GET: estructura completa. POST: mutación atómica de una operación.

    Operaciones: editar_formulario, agregar_seccion, editar_seccion,
    borrar_seccion, agregar_pregunta, editar_pregunta, borrar_pregunta,
    mover_pregunta, agregar_opcion, editar_opcion, borrar_opcion."""
    f = get_object_or_404(Formulario, pk=formulario_id)
    if request.method == 'GET':
        return JsonResponse(_estructura_json(f))
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    d = _jpost(request)
    op = d.get('op', '')
    try:
        if f.estructura_bloqueada and op != 'editar_formulario':
            raise ValidationError(
                'La estructura está bloqueada: el formulario ya recibió '
                'respuestas.')

        if op == 'editar_formulario':
            for campo in ('titulo', 'descripcion',
                          'modo_identificacion', 'campos_identificacion',
                          'modos_diligenciamiento',
                          'una_respuesta_por_respondiente',
                          'permite_editar_tras_envio',
                          'texto_tratamiento_datos',
                          'limite_envios_por_ip'):
                if campo in d:
                    setattr(f, campo, d[campo])
            f.save()

        elif op == 'agregar_seccion':
            sec = sf.agregar_seccion(f, titulo=d.get('titulo', ''))
            return JsonResponse({'ok': True, 'seccion_id': sec.pk})

        elif op == 'editar_seccion':
            sec = get_object_or_404(Seccion, pk=d['seccion_id'],
                                    formulario=f)
            sec.titulo = d.get('titulo', sec.titulo)
            sec.descripcion = d.get('descripcion', sec.descripcion)
            sec.save()

        elif op == 'borrar_seccion':
            get_object_or_404(Seccion, pk=d['seccion_id'],
                              formulario=f).delete()

        elif op == 'agregar_pregunta':
            sec = get_object_or_404(Seccion, pk=d['seccion_id'],
                                    formulario=f)
            p = sf.agregar_pregunta(
                sec, tipo=d.get('tipo', 'texto_corto'),
                enunciado=d.get('enunciado', ''),
                ayuda=d.get('ayuda', ''),
                obligatoria=bool(d.get('obligatoria')),
                codigo=d.get('codigo', ''),
                config=d.get('config', {}))
            return JsonResponse({'ok': True, 'pregunta_id': p.pk})

        elif op == 'editar_pregunta':
            p = get_object_or_404(Pregunta, pk=d['pregunta_id'],
                                  seccion__formulario=f)
            for campo in ('tipo', 'enunciado', 'ayuda', 'obligatoria',
                          'codigo', 'config'):
                if campo in d:
                    setattr(p, campo, d[campo])
            p.save()

        elif op == 'borrar_pregunta':
            p = get_object_or_404(Pregunta, pk=d['pregunta_id'],
                                  seccion__formulario=f)
            sf.borrar_pregunta(p)

        elif op == 'mover_pregunta':
            p = get_object_or_404(Pregunta, pk=d['pregunta_id'],
                                  seccion__formulario=f)
            sec = get_object_or_404(Seccion, pk=d['seccion_id'],
                                    formulario=f)
            sf.mover_pregunta(p, seccion=sec, orden=int(d.get('orden', 0)))

        elif op == 'agregar_opcion':
            p = get_object_or_404(Pregunta, pk=d['pregunta_id'],
                                  seccion__formulario=f)
            o = Opcion.objects.create(
                pregunta=p, orden=int(d.get('orden', 0)),
                texto=d.get('texto', ''), es_otro=bool(d.get('es_otro')))
            return JsonResponse({'ok': True, 'opcion_id': o.pk})

        elif op == 'editar_opcion':
            o = get_object_or_404(Opcion, pk=d['opcion_id'],
                                  pregunta__seccion__formulario=f)
            for campo in ('texto', 'es_otro', 'orden', 'valor'):
                if campo in d:
                    setattr(o, campo, d[campo])
            o.save()

        elif op == 'borrar_opcion':
            get_object_or_404(Opcion, pk=d['opcion_id'],
                              pregunta__seccion__formulario=f).delete()

        else:
            return JsonResponse({'error': 'Operación desconocida'},
                                status=400)
    except ValidationError as e:
        return JsonResponse({'error': '; '.join(e.messages)}, status=400)

    if op != 'editar_formulario':
        # Cada cambio estructural incrementa la version del instrumento.
        f.version += 1
        f.save(update_fields=['version'])
    registrar_accion(
        request, modulo='encuesta', accion=f'editar_estructura_{op}',
        objeto_tipo='encuestas.Formulario', objeto_id=f.pk,
        despues=d)
    return JsonResponse({'ok': True, 'estructura': _estructura_json(f)})


@gestor_required
def vista_previa(request, formulario_id):
    f = get_object_or_404(Formulario.objects.prefetch_related(
        'secciones__preguntas__opciones'), pk=formulario_id)
    ctx = _gestion_ctx(request)
    ctx.update({
        'f': f,
        'es_vista_previa': True,
        'tipo_de': tipo_de,
        'valores': {},
        'envio': None,
        'modo': 'publico',
        'invitacion': None,
    })
    return render(request, 'encuestas/responder.html', ctx)


# =============================================================================
# Gestión — distribución (§5.5) e invitaciones (§5.6)
# =============================================================================

@gestor_required
def distribucion(request, formulario_id):
    f = get_object_or_404(Formulario.objects.prefetch_related(
        'asignaciones__usuario', 'invitaciones'), pk=formulario_id)
    candidatos = (PerfilRecolector.objects
                  .filter(activo=True,
                          rol__in=('delegado', 'analista', 'diligenciador',
                                   'encuestador'))
                  .select_related('user').order_by('user__username'))
    ctx = _gestion_ctx(request)
    ctx.update({
        'f': f,
        'asignaciones': f.asignaciones.all(),
        'invitaciones': f.invitaciones.all(),
        'candidatos': candidatos,
        'url_publica': request.build_absolute_uri(
            reverse('encuestas:responder_publico', args=[f.slug])),
        'modos_disponibles': [
            ('autodiligenciado', 'Autodiligenciado (usuarios asignados)'),
            ('encuestador', 'Encuestador de campo'),
            ('publico', 'Enlace público')],
    })
    return render(request, 'gestion/encuestas/distribucion.html', ctx)


@require_POST
@gestor_required
def distribucion_accion(request, formulario_id):
    f = get_object_or_404(Formulario, pk=formulario_id)
    op = request.POST.get('op', '')
    try:
        if op == 'guardar_modos':
            modos = request.POST.getlist('modo')
            f.modos_diligenciamiento = modos
            for campo in ('modo_identificacion', 'permite_editar_tras_envio',
                          'una_respuesta_por_respondiente',
                          'texto_tratamiento_datos', 'limite_envios_por_ip'):
                if campo in request.POST:
                    setattr(f, campo, request.POST[campo])
            f.una_respuesta_por_respondiente = (
                request.POST.get('una_respuesta') == '1')
            f.permite_editar_tras_envio = (
                request.POST.get('permite_editar') == '1')
            f.save()
            registrar_accion(
                request, modulo='encuesta', accion='editar_modos',
                objeto_tipo='encuestas.Formulario', objeto_id=f.pk,
                despues={'modos': modos})
            messages.success(request, 'Modos actualizados.')

        elif op == 'asignar':
            usuario = get_object_or_404(User, pk=request.POST.get('usuario'))
            rol = request.POST.get('rol', 'diligenciador')
            meta = request.POST.get('meta') or None
            _, creada = Asignacion.objects.update_or_create(
                formulario=f, usuario=usuario, rol=rol,
                defaults={'meta': int(meta) if meta else None})
            registrar_accion(
                request, modulo='encuesta',
                accion='asignar' if creada else 'reasignar',
                objeto_tipo='encuestas.Asignacion', objeto_id=rol,
                despues={'usuario': usuario.username, 'rol': rol,
                         'meta': meta})
            messages.success(request, f'{usuario.username} asignado ({rol}).')

        elif op == 'quitar_asignacion':
            a = get_object_or_404(Asignacion, pk=request.POST.get('asignacion'),
                                formulario=f)
            antes = serializar(a)
            a.delete()
            registrar_accion(
                request, modulo='encuesta', accion='quitar_asignacion',
                objeto_tipo='encuestas.Asignacion', objeto_id=antes.get('id'),
                antes=antes)
            messages.success(request, 'Asignación quitada.')

        elif op == 'invitar':
            correos = [c.strip() for c in
                       request.POST.get('correos', '').split(',') if c.strip()]
            creadas = 0
            for correo in correos:
                _, c = Invitacion.objects.get_or_create(
                    formulario=f, correo=correo)
                creadas += c
            registrar_accion(
                request, modulo='encuesta', accion='invitar',
                objeto_tipo='encuestas.Formulario', objeto_id=f.pk,
                despues={'correos': correos})
            messages.success(request, f'{creadas} invitación(es) creadas.')

        else:
            messages.error(request, 'Operación no reconocida.')
    except ValidationError as e:
        messages.error(request, '; '.join(e.messages))
    return redirect('gestion:encuestas_distribucion', formulario_id=f.pk)


@require_POST
@gestor_required
def invitacion_marcar_enviada(request, invitacion_id):
    inv = get_object_or_404(Invitacion, pk=invitacion_id)
    inv.estado = 'enviada'
    inv.enviada = timezone.now()
    inv.save(update_fields=['estado', 'enviada'])
    registrar_accion(request, modulo='encuesta', accion='enviar_invitacion',
                     objeto_tipo='encuestas.Invitacion', objeto_id=inv.pk)
    return JsonResponse({'ok': True})


# =============================================================================
# Gestión — resultados y exportación (§5.8)
# =============================================================================

@gestor_required
def resultados(request, formulario_id):
    f = get_object_or_404(Formulario, pk=formulario_id)
    resumen, envios = sx.resumen(f)
    ctx = _gestion_ctx(request)
    ctx.update({
        'f': f,
        'resumen': resumen,
        'envios': envios,
        'n_enviados': envios.count(),
        'n_borrador': f.envios.filter(estado='borrador').count(),
        'n_anulados': f.envios.filter(estado='anulado').count(),
    })
    return render(request, 'gestion/encuestas/resultados.html', ctx)


@gestor_required
def exportar(request, formulario_id):
    f = get_object_or_404(Formulario, pk=formulario_id)
    formato = request.GET.get('formato', 'pivot')
    contenido = (sx.csv_largo(f) if formato == 'largo'
                 else sx.csv_pivot(f))
    r = HttpResponse(contenido, content_type='text/csv; charset=utf-8')
    r['Content-Disposition'] = (
        f'attachment; filename="{f.slug}_{formato}.csv"')
    registrar_accion(request, modulo='encuesta', accion='exportar',
                     objeto_tipo='encuestas.Formulario', objeto_id=f.pk,
                     despues={'formato': formato})
    return r


@require_POST
@gestor_required
def envio_accion(request, envio_id):
    envio = get_object_or_404(Envio.objects.select_related('formulario'),
                              pk=envio_id)
    op = request.POST.get('op', '')
    if op == 'anular':
        antes = serializar(envio)
        se.anular(envio)
        registrar_accion(request, modulo='encuesta', accion='anular_envio',
                         objeto_tipo='encuestas.Envio', objeto_id=envio.pk,
                         antes=antes, despues={'estado': 'anulado'},
                         motivo=request.POST.get('motivo', '').strip())
        messages.success(request, f'Envío {envio.pk} anulado.')
    elif op == 'eliminar':
        antes = serializar(envio)
        se.eliminar_envio(envio)
        registrar_accion(request, modulo='encuesta', accion='eliminar_envio',
                         objeto_tipo='encuestas.Envio', objeto_id=envio.pk,
                         antes=antes,
                         motivo=request.POST.get('motivo', '').strip())
        messages.success(request, f'Envío {envio.pk} eliminado.')
    return redirect('gestion:encuestas_resultados',
                    formulario_id=envio.formulario_id)


@gestor_required
def envio_detalle(request, envio_id):
    """Detalle de un envio: metadata + respuestas una a una (gestor)."""
    envio = get_object_or_404(
        Envio.objects.select_related(
            'formulario', 'respondiente', 'invitacion',
            'diligenciado_por'),
        pk=envio_id)
    respuestas = list(
        envio.respuestas.select_related('pregunta')
        .order_by('pregunta__seccion__orden', 'pregunta__orden'))
    items = [{'p': r.pregunta, 'valor': sx._texto_valor(r.valor)}
             for r in respuestas]
    ctx = _gestion_ctx(request)
    ctx.update({'f': envio.formulario, 'envio': envio,
                'items': items,
                'adjuntos': list(envio.adjuntos.all())})
    return render(request, 'gestion/encuestas/envio_detalle.html', ctx)


@gestor_required
def descargar_adjunto(request, adjunto_id):
    """Descarga un adjunto solo siendo gestor."""
    adj = get_object_or_404(Adjunto.objects.select_related('envio'),
                            pk=adjunto_id)
    return FileResponse(adj.archivo.open('rb'), as_attachment=True,
                        filename=adj.nombre_original)


# =============================================================================
# Respuesta — pendientes, diligenciador, encuestador, público (§5.5-§5.6)
# =============================================================================

def _envio_de_formulario(request, f, modo, invitacion=None):
    """Devuelve el envío activo del usuario/respondiente para este modo."""
    usuario = request.user if request.user.is_authenticated else None
    if modo == 'auto' and usuario:
        return se._envio_activo(f, usuario=usuario)
    if invitacion:
        return Envio.objects.filter(formulario=f, invitacion=invitacion) \
            .exclude(estado='anulado').first()
    return None


def _responder(request, f, *, modo, invitacion=None):
    """Flujo común de diligenciamiento: GET renderiza, POST guarda
    borrador o envía."""
    if request.method == 'POST':
        accion = request.POST.get('_accion', 'guardar')
        envio = _envio_de_formulario(request, f, modo, invitacion)
        try:
            if envio is None:
                respondiente = _crear_respondiente(request, f)
                envio = se.crear_envio(
                    f, modo=modo,
                    usuario=request.user if request.user.is_authenticated
                    else None,
                    respondiente=respondiente,
                    invitacion=invitacion,
                    request=request)
            else:
                _actualizar_respondiente(request, envio)
            if accion == 'borrador':
                errores = se.guardar_borrador(envio, request.POST,
                                              request.FILES)
                if errores:
                    for msgs in errores.values():
                        for m in msgs:
                            messages.error(request, m)
                else:
                    messages.info(request, 'Borrador guardado.')
            else:
                try:
                    se.enviar(envio, request.POST, request.FILES)
                except se.ErroresEnvio as e:
                    for msgs in e.errores.values():
                        for m in msgs:
                            messages.error(request, m)
                else:
                    messages.success(request, 'Respuesta enviada. ¡Gracias!')
                    return redirect(_gracias_url(f, envio))
        except ValidationError as e:
            messages.error(request, '; '.join(e.messages))

    ctx = {
        'f': f,
        'tipo_de': tipo_de,
        'envio': _envio_de_formulario(request, f, modo, invitacion),
        'invitacion': invitacion,
        'modo': modo,
        'es_vista_previa': False,
        'valores': {},
    }
    # Valores actuales para pintar (borrador/edicion)
    envio = ctx['envio']
    if envio:
        ctx['valores'] = {r.pregunta_id: r.valor
                          for r in envio.respuestas.all()}
    return render(request, 'encuestas/responder.html', ctx)


def _gracias_url(f, envio):
    return (f"{reverse('encuestas:gracias', args=[envio.pk])}"
            f"?t={envio.token}")


@require_GET
def gracias(request, envio_id):
    envio = get_object_or_404(Envio.objects.select_related('formulario'),
                              pk=envio_id)
    # Sin el token del envio no se confirma su existencia (404 uniforme).
    if request.GET.get('t') != envio.token:
        raise Http404
    return render(request, 'encuestas/gracias.html', {
        'f': envio.formulario, 'envio': envio})


def _campos_identificacion(f):
    """Lista de (campo, obligatorio) del modo identificado."""
    configurados = f.campos_identificacion or {}
    por_defecto = {
        'nombres': True, 'apellidos': True, 'correo': True,
        'telefono': False, 'tipo_documento': True, 'documento': True,
        'territorio': False}
    campos = []
    for campo, defecto in por_defecto.items():
        if campo in configurados:
            req = bool(configurados[campo])
        else:
            req = defecto
        campos.append((campo, req))
    return campos


def _crear_respondiente(request, f):
    """Respondiente del modo identificado, o None en anónimo."""
    if f.modo_identificacion != 'identificado':
        return None
    d = request.POST
    autoriza = d.get('autoriza_datos') == '1'
    if f.texto_tratamiento_datos and not autoriza:
        raise ValidationError(
            'Debe autorizar el tratamiento de datos personales.')
    respondiente = Respondiente(
        nombres=d.get('id_nombres', '').strip(),
        apellidos=d.get('id_apellidos', '').strip(),
        tipo_documento=d.get('id_tipo_documento', ''),
        documento=d.get('id_documento', '').strip(),
        telefono=d.get('id_telefono', '').strip(),
        correo=d.get('id_correo', '').strip(),
        territorio=d.get('id_territorio', '').strip(),
        autoriza_datos=autoriza)
    org = d.get('id_organismo')
    if org:
        respondiente.organismo_id = org
    for campo, req in _campos_identificacion(f):
        valor = getattr(respondiente, campo, '')
        if req and not valor:
            raise ValidationError(
                f'El campo «{campo}» es obligatorio en el registro.')
    respondiente.save()
    return respondiente


def _actualizar_respondiente(request, envio):
    """Actualiza los datos del respondiente si el envío ya existe."""
    if envio.respondiente_id is None:
        return None
    r = envio.respondiente
    d = request.POST
    for campo in ('nombres', 'apellidos', 'tipo_documento', 'documento',
                  'telefono', 'correo', 'territorio'):
        if f'id_{campo}' in d:
            setattr(r, campo, d[f'id_{campo}'].strip())
    r.save()
    return r


def responder_publico(request, slug):
    f = get_object_or_404(Formulario, slug=slug)
    return _responder(request, f, modo='publico')


def responder_invitacion(request, slug, token):
    f = get_object_or_404(Formulario, slug=slug)
    inv = get_object_or_404(Invitacion, formulario=f, token=token)
    return _responder(request, f, modo='publico', invitacion=inv)


@login_required
def responder_asignado(request, formulario_id):
    f = get_object_or_404(Formulario, pk=formulario_id)
    return _responder(request, f, modo='auto')


@login_required
def responder_encuestador(request, formulario_id):
    f = get_object_or_404(Formulario, pk=formulario_id)
    return _responder(request, f, modo='encuestador')


@login_required
def pendientes(request):
    """Formularios asignados al usuario como diligenciador o encuestador."""
    asignaciones = (Asignacion.objects
                    .filter(usuario=request.user)
                    .select_related('formulario')
                    .order_by('formulario__titulo'))
    return render(request, 'encuestas/pendientes.html', {
        'asignaciones': asignaciones})


# =============================================================================
# Captura offline del encuestador
# =============================================================================

@login_required
def descargar_offline(request, formulario_id, usuario_id=None):
    """Descarga la plantilla HTML autocontenida para captura en campo.

    Un encuestador la descarga para sí mismo; el gestor puede generarla
    para cualquier usuario con asignación de encuestador."""
    f = get_object_or_404(Formulario, pk=formulario_id)
    if usuario_id and request.user.perfil_recolector.es_gestor():
        encuestador = get_object_or_404(User, pk=usuario_id)
    else:
        encuestador = request.user
    if not Asignacion.objects.filter(
            formulario=f, usuario=encuestador,
            rol='encuestador').exists():
        messages.error(
            request,
            f'{encuestador.username} no es encuestador de este formulario.')
        return redirect('gestion:encuestas_distribucion',
                        formulario_id=f.pk)

    expira = (timezone.now().date()
              + timezone.timedelta(days=so.DIAS_VALIDEZ_TOKEN)).isoformat()
    meta = {
        'encuestador': encuestador.username,
        'encuestador_id': encuestador.pk,
        'sincro_token': so.sincro_token(f, encuestador, expira),
        'sincro_expira': expira,
        'url_sync': request.build_absolute_uri(
            reverse('encuestas:sincronizar')),
    }
    contenido = render(request, 'encuestas/offline.html', {
        'f': f,
        'formulario_json': json.dumps(so.estructura_json(f),
                                      ensure_ascii=False)
                            .replace('</', '<\\/'),
        'meta_json': json.dumps(meta).replace('</', '<\\/'),
    }).content
    resp = HttpResponse(contenido, content_type='text/html; charset=utf-8')
    resp['Content-Disposition'] = (
        f'attachment; filename="{f.slug}_offline_{encuestador.username}.html"')
    registrar_accion(
        request, modulo='encuesta', accion='descargar_offline',
        objeto_tipo='encuestas.Formulario', objeto_id=f.pk,
        despues={'encuestador': encuestador.username})
    return resp


from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
@require_POST
def sincronizar(request):
    """Recibe el lote de envíos offline (sin sesión: el sincro_token
    HMAC autentica la carga)."""
    try:
        d = json.loads(request.body.decode() or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    f = get_object_or_404(Formulario, pk=d.get('formulario_id'))
    encuestador = get_object_or_404(User, pk=d.get('encuestador_id'))
    try:
        resultados = so.importar_envios(
            f, encuestador, d.get('sincro_token', ''),
            d.get('envios') or [],
            expira=d.get('sincro_expira', ''))
    except ValidationError as e:
        return JsonResponse({'error': '; '.join(e.messages)}, status=403)
    n_ok = sum(1 for r in resultados if r['estado'] == 'importado')
    # La bitácora sin sesión se registra con el encuestador como actor
    from gestion.models import AccionGestion
    AccionGestion.objects.create(
        usuario=encuestador, modulo='encuesta', accion='sincronizar_offline',
        objeto_tipo='encuestas.Formulario', objeto_id=f.pk,
        despues={'importados': n_ok,
                 'total': len(resultados)})
    return JsonResponse({'resultados': resultados})


# =============================================================================
# Ficha metodológica (DANE/SEN — metadata de la operación)
# =============================================================================

@gestor_required
def ficha(request, formulario_id):
    from .services import ficha as sficha
    f = get_object_or_404(Formulario, pk=formulario_id)
    fi = sficha.ficha_de(f)
    if request.method == 'POST':
        antes = serializar(fi)
        sficha.actualizar_ficha(fi, request.POST)
        registrar_accion(
            request, modulo='encuesta', accion='editar_ficha',
            objeto_tipo='encuestas.Formulario', objeto_id=f.pk,
            antes={k: str(v)[:120] for k, v in antes.items()},
            despues={'faltantes_minima': sficha.faltantes_minimos(fi)})
        messages.success(request, 'Ficha metodológica actualizada.')
        return redirect('gestion:encuestas_ficha', formulario_id=f.pk)
    ctx = _gestion_ctx(request)
    ctx.update({
        'f': f, 'fi': fi,
        'bloques': sficha.BLOQUES,
        'minima_campos': {c for c, _ in sficha.MINIMA},
        'faltantes_minima': sficha.faltantes_minimos(fi),
        'pendientes_rec': sficha.pendientes_recomendados(fi),
        'completitud': sficha.completitud_minima(fi),
        'tipos_op': dict(fi.TIPO_OP_CHOICES),
        'periodicidades': dict(fi.PERIODICIDAD_CHOICES),
        'marcos': dict(fi.MARCO_CHOICES),
        'metodos': fi.METODOS_CHOICES,
    })
    return render(request, 'gestion/encuestas/ficha.html', ctx)
