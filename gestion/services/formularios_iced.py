"""
Acciones sobre ICEDFormulario (plan §3.4).

- reabrir: `enviado`/`devuelto` → `borrador` (alternativa no destructiva).
- reiniciar: borra el formulario guardando una copia completa en la
  bitácora. Si el consolidado del organismo está prevalidado/validado se
  bloquea: hay que revertirlo primero (acción aparte, auditada).
- restaurar: recrea el formulario desde la copia `antes` de la bitácora,
  si el organismo/equipo/periodo no fue recreado después.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import model_to_dict

from indicadores.models_iced import ICEDFormulario

ESTADOS_CONGELADOS = ('prevalidado', 'validado')
REABRIBLES = ('enviado', 'correcciones')


def _consolidado_bloqueante(formulario):
    """Consolidado del organismo que impide reiniciar un equipo."""
    if formulario.equipo == '':          # el consolidado mismo
        return None
    return (ICEDFormulario.objects
            .filter(organismo=formulario.organismo,
                    periodo=formulario.periodo, equipo='',
                    estado__in=ESTADOS_CONGELADOS)
            .first())


def copia_formulario(f):
    """Respaldo JSON completo: cabecera + tablas relacionadas propias."""
    data = model_to_dict(f)
    data['fecha_creacion'] = str(f.fecha_creacion) \
        if getattr(f, 'fecha_creacion', None) else None
    data['fecha_actualizacion'] = str(f.fecha_actualizacion) \
        if getattr(f, 'fecha_actualizacion', None) else None
    for campo in ('puntaje_b', 'puntaje_c', 'puntaje_d',
                  'puntaje_e', 'puntaje_global'):
        if data.get(campo) is not None:
            data[campo] = str(data[campo])
    for rel in ('recursos_humanos', 'personas_contacto'):
        data[rel] = [model_to_dict(o) for o in getattr(f, rel).all()]
    return data


def reabrir_formulario(f):
    """`enviado`/`correcciones` → `borrador`. Devuelve (antes, despues)."""
    if f.estado not in REABRIBLES:
        raise ValidationError(
            f'No se puede reabrir un formulario en estado '
            f'«{f.get_estado_display()}»; solo enviado o con correcciones.')
    antes = {'estado': f.estado}
    f.estado = 'borrador'
    f.save(update_fields=['estado'])
    return antes, {'estado': f.estado}


def reiniciar_formulario(f):
    """Borra el formulario. Devuelve la copia para AccionGestion.antes.

    La vista exige motivo + escribir el nombre del organismo antes de
    llamar esta función."""
    bloqueo = _consolidado_bloqueante(f)
    if bloqueo:
        raise ValidationError(
            'El consolidado del organismo está '
            f'«{bloqueo.get_estado_display()}». Para reiniciar este equipo '
            'primero hay que revertir el consolidado (acción aparte).')
    copia = copia_formulario(f)
    with transaction.atomic():
        f.delete()
    return copia


def restaurar_formulario(copia):
    """Recrea el formulario desde la copia de la bitácora.

    Falla si ya existe un formulario para la misma
    organismo/periodo/equipo (no pisa datos nuevos)."""
    ya = ICEDFormulario.objects.filter(
        organismo_id=copia.get('organismo'),
        periodo=copia.get('periodo'),
        equipo=copia.get('equipo', '')).exists()
    if ya:
        raise ValidationError(
            'Ya existe un formulario para ese organismo/periodo/equipo; '
            'no se restaura para no pisar datos nuevos.')

    # model_to_dict guarda la FK como 'organismo' con la PK; al recrear
    # hay que usar el attname ('organismo_id').
    nombres = {}  # name del campo -> attname para el constructor
    for c in ICEDFormulario._meta.get_fields():
        if getattr(c, 'concrete', False) and not c.auto_created:
            nombres[c.name] = c.attname
    datos = {nombres[k]: v for k, v in copia.items()
             if k in nombres and k != 'id'}
    rel_rh = copia.get('recursos_humanos', [])
    rel_pc = copia.get('personas_contacto', [])
    with transaction.atomic():
        nuevo = ICEDFormulario.objects.create(**datos)
        if rel_rh:
            from indicadores.models_iced import ICEDRecursoHumano
            campos_rh = {c.name for c in ICEDRecursoHumano._meta.get_fields()
                         if getattr(c, 'concrete', False)
                         and not c.auto_created}
            for d in rel_rh:
                ICEDRecursoHumano.objects.create(
                    formulario=nuevo,
                    **{k: v for k, v in d.items()
                       if k in campos_rh and k not in ('id', 'formulario')})
        if rel_pc:
            from indicadores.models_iced import ICEDPersonaContacto
            campos_pc = {c.name for c in ICEDPersonaContacto._meta.get_fields()
                         if getattr(c, 'concrete', False)
                         and not c.auto_created}
            for d in rel_pc:
                ICEDPersonaContacto.objects.create(
                    formulario=nuevo,
                    **{k: v for k, v in d.items()
                       if k in campos_pc and k not in ('id', 'formulario')})
    return nuevo
