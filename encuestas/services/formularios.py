"""
Ciclo de vida y estructura de formularios (plan §5.3-§5.4).

Reglas:
- Solo `publicado` acepta envíos; `cerrado` deja de aceptar pero se
  puede reabrir; `archivado` es terminal en la UI.
- Duplicar un formulario crea un borrador con toda la estructura;
  con respuestas solo puede duplicarse para seguir editando (§5.4).
- La estructura queda bloqueada con la primera respuesta enviada.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from ..models import (FichaMetodologica, Formulario, Opcion, Pregunta,
                      Seccion)


def slug_unico(base):
    base = slugify(base or 'formulario')[:60] or 'formulario'
    slug, i = base, 2
    while Formulario.objects.filter(slug=slug).exists():
        slug = f'{base}-{i}'
        i += 1
    return slug


def crear_formulario(*, titulo, tipo, creador=None, descripcion=''):
    if not titulo:
        raise ValidationError({'titulo': 'El título es obligatorio.'})
    f = Formulario.objects.create(
        titulo=titulo, tipo=tipo, descripcion=descripcion,
        slug=slug_unico(titulo), creador=creador,
        modos_diligenciamiento=[Formulario.MODO_AUTODILIGENCIADO])
    Seccion.objects.create(formulario=f, orden=0, titulo='')
    return f


def publicar(f):
    """borrador → publicado. Requiere al menos una pregunta con dato
    y la metadata mínima de la ficha metodológica (NTC PE 1000)."""
    if f.estado == 'publicado':
        return f
    if f.estado == 'archivado':
        raise ValidationError('Un formulario archivado no se publica.')
    n_preguntas = (Pregunta.objects.filter(seccion__formulario=f)
                   .exclude(tipo='informativo').count())
    if n_preguntas == 0:
        raise ValidationError('No puede publicarse sin al menos una '
                              'pregunta con datos.')
    from . import ficha as sficha
    sficha.validar_para_publicar(f)
    f.estado = 'publicado'
    f.save(update_fields=['estado', 'actualizado'])
    return f


def cerrar(f):
    """publicado → cerrado. Deja de aceptar respuestas."""
    if f.estado != 'publicado':
        raise ValidationError(
            'Solo se cierra un formulario publicado.')
    f.estado = 'cerrado'
    f.save(update_fields=['estado', 'actualizado'])
    return f


def reabrir(f):
    """cerrado → publicado."""
    if f.estado != 'cerrado':
        raise ValidationError('Solo se reabre un formulario cerrado.')
    f.estado = 'publicado'
    f.save(update_fields=['estado', 'actualizado'])
    return f


def archivar(f):
    f.estado = 'archivado'
    f.save(update_fields=['estado', 'actualizado'])
    return f


def duplicar(f, titulo=None):
    """Clona formulario + secciones + preguntas + opciones a borrador.

    Con respuestas es la única vía para seguir editando (estructura
    bloqueada, §5.4)."""
    with transaction.atomic():
        nuevo = Formulario.objects.create(
            titulo=titulo or f'{f.titulo} (copia)',
            slug=slug_unico(f'{f.slug}-copia'),
            descripcion=f.descripcion, tipo=f.tipo,
            modo_identificacion=f.modo_identificacion,
            campos_identificacion=f.campos_identificacion,
            modos_diligenciamiento=f.modos_diligenciamiento,
            una_respuesta_por_respondiente=f.una_respuesta_por_respondiente,
            permite_editar_tras_envio=f.permite_editar_tras_envio,
            texto_tratamiento_datos=f.texto_tratamiento_datos,
            limite_envios_por_ip=f.limite_envios_por_ip,
            creador=f.creador)
        mapa_preguntas = {}
        for sec in f.secciones.all():
            nueva = Seccion.objects.create(
                formulario=nuevo, orden=sec.orden, titulo=sec.titulo,
                descripcion=sec.descripcion)
            for p in sec.preguntas.all():
                np = Pregunta.objects.create(
                    seccion=nueva, orden=p.orden, tipo=p.tipo,
                    enunciado=p.enunciado, ayuda=p.ayuda,
                    obligatoria=p.obligatoria, codigo=p.codigo,
                    config=p.config)
                mapa_preguntas[p.id] = np
                for o in p.opciones.all():
                    Opcion.objects.create(
                        pregunta=np, orden=o.orden, texto=o.texto,
                        valor=o.valor, es_otro=o.es_otro)
        # La ficha metodológica viaja con la copia (misma operación)
        ficha = getattr(f, 'ficha', None)
        if ficha:
            from django.forms.models import model_to_dict
            datos = {k: v for k, v in model_to_dict(ficha).items()
                     if k not in ('id', 'formulario')}
            FichaMetodologica.objects.create(formulario=nuevo, **datos)
    return nuevo


def cambiar_estructura(f, *, fn):
    """Ejecuta `fn()` bloqueando la edición si hay respuestas (§5.4)."""
    if f.estructura_bloqueada:
        raise ValidationError(
            'La estructura está bloqueada: el formulario ya recibió '
            'respuestas. Duplique el formulario para seguir editando.')
    return fn()


def agregar_seccion(f, titulo=''):
    if f.estructura_bloqueada:
        raise ValidationError('Estructura bloqueada: hay respuestas.')
    orden = (f.secciones.order_by('-orden')
             .values_list('orden', flat=True).first() or 0) + 1
    return Seccion.objects.create(formulario=f, orden=orden,
                                  titulo=titulo)


def agregar_pregunta(sec, *, tipo, enunciado, **kw):
    if sec.formulario.estructura_bloqueada:
        raise ValidationError('Estructura bloqueada: hay respuestas.')
    orden = (sec.preguntas.order_by('-orden')
             .values_list('orden', flat=True).first() or 0) + 1
    return Pregunta.objects.create(
        seccion=sec, orden=orden, tipo=tipo, enunciado=enunciado, **kw)


def borrar_pregunta(p):
    if p.seccion.formulario.estructura_bloqueada:
        raise ValidationError('Estructura bloqueada: hay respuestas.')
    p.delete()


def mover_pregunta(p, *, seccion, orden):
    if p.seccion.formulario.estructura_bloqueada:
        raise ValidationError('Estructura bloqueada: hay respuestas.')
    p.seccion = seccion
    p.orden = orden
    p.save(update_fields=['seccion', 'orden'])
