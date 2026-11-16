"""
Captura offline del encuestador.

El gestor (o el encuestador con sesión) descarga una plantilla HTML
autocontenida por formulario que incluye la estructura + todo el JS.
Funciona sin internet, guarda envíos en localStorage, exporta un
respaldo `.json` y sincroniza al volver la conexión.

Seguridad:
- Cada plantilla lleva un `sincro_token` = HMAC(usuario|formulario|
  version) — solo ese encuestador y ese formulario pueden usarla.
- El servidor revalida cada respuesta con el registro de `tipos.py`
  (misma ruta de validación que el formulario web).
- `offline_id` (UUID del cliente) deduplica envíos: sincronizar dos
  veces el mismo respaldo no duplica registros.
"""
import hashlib
import hmac
import json

from django.conf import settings
from django.core.exceptions import ValidationError

from ..models import Asignacion, Envio, Formulario, Respondiente
from ..tipos import tipo_de

_SALIDA = 'encuestas-offline-v1'


def sincro_token(formulario, usuario):
    """HMAC que ata la plantilla offline al encuestador y al formulario."""
    base = f'{_SALIDA}|{usuario.pk}|{formulario.pk}|{formulario.version}'
    return hmac.new(
        settings.SECRET_KEY.encode(), base.encode(),
        hashlib.sha256).hexdigest()[:40]


def verificar_sincro(token, formulario, usuario):
    return hmac.compare_digest(
        token or '', sincro_token(formulario, usuario))


def estructura_json(formulario):
    """Estructura serializable para incrustar en la plantilla offline."""
    secciones = []
    for sec in formulario.secciones.prefetch_related(
            'preguntas__opciones'):
        secciones.append({
            'orden': sec.orden, 'titulo': sec.titulo,
            'descripcion': sec.descripcion,
            'preguntas': [{
                'id': p.pk, 'tipo': p.tipo, 'enunciado': p.enunciado,
                'ayuda': p.ayuda, 'obligatoria': p.obligatoria,
                'codigo': p.codigo, 'config': p.config,
                'opciones': [{'id': o.id, 'texto': o.texto,
                              'es_otro': o.es_otro}
                             for o in p.opciones.all()],
            } for p in sec.preguntas.all()],
        })
    return {
        'id': formulario.pk, 'slug': formulario.slug,
        'titulo': formulario.titulo, 'descripcion': formulario.descripcion,
        'modo_identificacion': formulario.modo_identificacion,
        'texto_tratamiento_datos': formulario.texto_tratamiento_datos,
        'version': formulario.version,
        'secciones': secciones,
    }


# =============================================================================
# Importación de envíos sincronizados
# =============================================================================

CAMPOS_RESPONDIENTE = ('nombres', 'apellidos', 'tipo_documento',
                     'documento', 'telefono', 'correo', 'territorio')


def _limpiar_valor(pregunta, bruto):
    """Revalida el valor con el tipo registrado. Devuelve
    (valor_limpio, errores)."""
    errores = []

    class _F:
        def add_error(self, msg):
            errores.append(msg)

    valor = tipo_de(pregunta)().limpiar(bruto, pregunta, _F())
    if pregunta.obligatoria and valor is None and not errores:
        errores.append('Obligatoria sin respuesta.')
    return valor, errores


def importar_envios(formulario, usuario, token, envios):
    """Importa un lote de envíos del respaldo offline.

    Devuelve [{offline_id, estado: 'importado'|'duplicado'|'error',
               detalle}]. Nunca revienta por una entrada mala."""
    if not verificar_sincro(token, formulario, usuario):
        raise ValidationError('Token de sincronización inválido.')
    if not Asignacion.objects.filter(
            formulario=formulario, usuario=usuario,
            rol='encuestador').exists():
        raise ValidationError(
            'No tiene asignación de encuestador en este formulario.')

    from ..models import Pregunta, RespuestaItem
    preguntas = {
        p.pk: p
        for p in Pregunta.objects.filter(seccion__formulario=formulario)}
    resultados = []

    for item in envios:
        oid = str(item.get('offline_id') or '').strip()[:40]
        if not oid:
            resultados.append({
                'offline_id': oid,
                'estado': 'error', 'detalle': 'sin offline_id'})
            continue
        if Envio.objects.filter(offline_id=oid).exists():
            resultados.append({
                'offline_id': oid, 'estado': 'duplicado',
                'detalle': 'ya sincronizado'})
            continue

        # Respondiente (modo identificado)
        respondiente = None
        datos_r = item.get('respondiente') or {}
        if formulario.modo_identificacion == 'identificado':
            try:
                respondiente = Respondiente(
                    autoriza_datos=bool(datos_r.get('autoriza_datos')),
                    **{c: str(datos_r.get(c) or '')[:200]
                       for c in CAMPOS_RESPONDIENTE})
                if formulario.texto_tratamiento_datos and \
                        not respondiente.autoriza_datos:
                    raise ValidationError('sin autorización de datos')
                respondiente.save()
            except ValidationError as e:
                resultados.append({
                    'offline_id': oid, 'estado': 'error',
                    'detalle': f'respondiente: {"; ".join(e.messages)}'})
                continue

        # Validar respuestas antes de crear el envío
        respuestas = item.get('respuestas') or {}
        limpias = {}
        fallos = []
        for pid_s, bruto in respuestas.items():
            try:
                p = preguntas[int(pid_s)]
            except (KeyError, ValueError):
                continue  # pregunta eliminada del formulario: se ignora
            valor, errs = _limpiar_valor(p, bruto)
            if errs:
                fallos.append(f"{p.codigo or p.pk}: {'; '.join(errs)}")
            limpias[p.pk] = valor
        # Obligatorias no respondidas
        for p in preguntas.values():
            if p.obligatoria and p.pk not in limpias and \
                    tipo_de(p).clave != 'informativo':
                fallos.append(
                    f"{p.codigo or p.pk}: obligatoria sin respuesta")

        if fallos:
            resultados.append({
                'offline_id': oid, 'estado': 'error',
                'detalle': ' | '.join(fallos)[:400]})
            if respondiente:
                respondiente.delete()
            continue

        envio = Envio.objects.create(
            formulario=formulario, modo='encuestador',
            diligenciado_por=usuario, respondiente=respondiente,
            estado='enviado', offline_id=oid,
            geolocalizacion=item.get('geo'),
            version=formulario.version)
        RespuestaItem.objects.bulk_create([
            RespuestaItem(envio=envio, pregunta_id=pid, valor=v)
            for pid, v in limpias.items()])
        resultados.append({
            'offline_id': oid, 'estado': 'importado',
            'detalle': f'envío {envio.pk}'})

    return resultados
