"""
Envíos y respuestas (plan §5.5-§5.6).

- `modo` decide quién captura: autodiligenciado (usuario con asignación
  'diligenciador'), encuestador (captura respondiente ajeno) y público
  (sin login, por slug/invitación).
- Una respuesta por respondiente si está activo; edición tras envío
  solo si `permite_editar_tras_envio`.
- IP guardada como hash (privacidad); límite de envíos por IP en público.
- Los valores JSON se normalizan por el registro de `tipos.py`.
"""
import hashlib

from django.core.exceptions import ValidationError
from django.db import transaction

from gestion.services.ventanas import ventana_abierta

from ..models import (Asignacion, Envio, Formulario, Invitacion,
                      Respondiente, RespuestaItem)
from ..tipos import tipo_de


def ip_hash(request):
    ip = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
          or request.META.get('REMOTE_ADDR', ''))
    return hashlib.sha256(ip.encode()).hexdigest()[:32] if ip else ''


def _asignacion(formulario, usuario, rol):
    return (Asignacion.objects
            .filter(formulario=formulario, usuario=usuario, rol=rol)
            .first())


def puede_responder(formulario, usuario, modo):
    """(ok, detalle) — quién puede crear envío en cada modo."""
    if not formulario.acepta_respuestas:
        return False, 'El formulario no está publicado.'
    if modo == 'auto':
        if not usuario.is_authenticated:
            return False, 'Inicia sesión para diligenciar.'
        if Formulario.MODO_AUTODILIGENCIADO not in \
                formulario.modos_diligenciamiento:
            return False, 'El autodiligenciamiento no está habilitado.'
        if not _asignacion(formulario, usuario, 'diligenciador'):
            return False, 'No tienes este formulario asignado.'
        return True, ''
    if modo == 'encuestador':
        if not usuario.is_authenticated:
            return False, 'Inicia sesión como encuestador.'
        if Formulario.MODO_ENCUESTADOR not in \
                formulario.modos_diligenciamiento:
            return False, 'El modo encuestador no está habilitado.'
        if not _asignacion(formulario, usuario, 'encuestador'):
            return False, 'No tienes este formulario asignado.'
        return True, ''
    if modo == 'publico':
        if Formulario.MODO_PUBLICO not in \
                formulario.modos_diligenciamiento:
            return False, 'El acceso público no está habilitado.'
        return True, ''
    return False, 'Modo inválido.'


def _ventana_formulario(formulario, organismo=None):
    """Ventana de la encuesta: `ventana` del formulario si existe, si no
    una ventana `encuesta` por el año actual (referencia libre)."""
    if formulario.ventana_id:
        return ventana_abierta(
            'encuesta', formulario.ventana.referencia, organismo)
    # Sin ventana vinculada: la referencia por defecto es el slug
    return ventana_abierta('encuesta', formulario.slug, organismo)


def _envio_activo(formulario, usuario=None, respondiente_doc=None,
                  token=None):
    """Envío existente (borrador o enviado) para las reglas de unicidad."""
    qs = Envio.objects.filter(formulario=formulario) \
        .exclude(estado='anulado')
    if usuario is not None:
        return qs.filter(diligenciado_por=usuario).first()
    if respondiente_doc:
        return qs.filter(
            respondiente__documento_norm=respondiente_doc).first()
    if token:
        return qs.filter(token=token).first()
    return None


def crear_envio(formulario, *, modo, usuario=None, respondiente=None,
                invitacion=None, request=None):
    """Crea el envío en borrador aplicando las reglas de negocio."""
    ok, detalle = puede_responder(formulario, usuario, modo)
    if not ok:
        raise ValidationError(detalle)

    organismo = respondiente.organismo if respondiente else None
    ev = _ventana_formulario(formulario, organismo)
    if not ev.abierta:
        raise ValidationError(ev.mensaje)

    doc_norm = (respondiente.documento_norm
                if respondiente else None)
    if formulario.una_respuesta_por_respondiente and \
            modo in ('auto', 'publico', 'encuestador'):
        existente = _envio_activo(
            formulario,
            usuario=usuario if modo == 'auto' else None,
            respondiente_doc=doc_norm if modo != 'auto' else None)
        if existente:
            if existente.estado == 'borrador':
                return existente
            if not formulario.permite_editar_tras_envio:
                raise ValidationError(
                    'Ya existe un envío registrado. '
                    'Una sola respuesta por respondiente.')

    if modo == 'publico' and request is not None:
        h = ip_hash(request)
        limite = formulario.limite_envios_por_ip or 5
        n = Envio.objects.filter(formulario=formulario, ip_hash=h) \
            .exclude(estado='anulado').count()
        if n >= limite:
            raise ValidationError(
                'Se alcanzó el límite de envíos desde esta conexión.')

    envio = Envio.objects.create(
        formulario=formulario, modo=modo,
        diligenciado_por=usuario if modo in ('auto', 'encuestador') else None,
        respondiente=respondiente, invitacion=invitacion,
        ip_hash=ip_hash(request) if request else '',
        user_agent=(request.META.get('HTTP_USER_AGENT', '')[:500]
                    if request else ''),
        version=formulario.version)
    if invitacion:
        invitacion.estado = 'usada'
        invitacion.save(update_fields=['estado'])
    return envio


class ErroresEnvio(Exception):
    """Errores de validación de respuestas por pregunta."""
    def __init__(self, errores):
        super().__init__('Respuestas con errores')
        self.errores = errores  # {pregunta_id: [msg,...]}


def _guardar_respuestas(envio, post, *, validar_obligatorias=True):
    """Limpia y guarda las respuestas del POST.

    `post` es QueryDict; los campos llegan como `p_{pk}`. Devuelve
    (errores, n_guardadas)."""
    errores = {}

    class _F:
        def __init__(self, pid):
            self.pid = pid
        def add_error(self, msg):
            errores.setdefault(self.pid, []).append(msg)

    for pregunta in envio.formulario.secciones.prefetch_related(
            'preguntas__opciones'):
        for p in pregunta.preguntas.all():
            tipo = tipo_de(p)
            key = f'p_{p.pk}'
            if tipo.clave == 'informativo':
                continue
            if tipo.clave == 'seleccion_multiple':
                bruto = post.getlist(key)
            else:
                bruto = post.get(key)
            fake = _F(p.pk)
            valor = tipo().limpiar(bruto, p, fake)
            if p.obligatoria and validar_obligatorias and valor is None:
                errores.setdefault(p.pk, []).append(
                    'Esta pregunta es obligatoria.')
                continue
            if errores.get(p.pk):
                continue
            RespuestaItem.objects.update_or_create(
                envio=envio, pregunta=p,
                defaults={'valor': valor})
    return errores


def guardar_borrador(envio, post):
    """Guarda respuestas sin exigir obligatorias (seguir luego)."""
    if envio.estado != 'borrador':
        raise ValidationError('El envío ya fue enviado.')
    return _guardar_respuestas(envio, post, validar_obligatorias=False)


def enviar(envio, post, *, respondiente=None):
    """Valida obligatorias, guarda y marca el envío como enviado."""
    if envio.estado == 'enviado' and \
            not envio.formulario.permite_editar_tras_envio:
        raise ValidationError('Este envío ya fue enviado.')
    errores = _guardar_respuestas(envio, post,
                                  validar_obligatorias=True)
    if errores:
        raise ErroresEnvio(errores)
    envio.estado = 'enviado'
    envio.save()
    return envio


def anular(envio):
    """Gestor marca el envío como anulado (no se cuenta en resultados)."""
    envio.estado = 'anulado'
    envio.save(update_fields=['estado'])
    return envio
