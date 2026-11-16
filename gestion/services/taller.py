"""
Submódulo Taller de Gestión de Datos (plan §4).

Identidad del taller: Organismo → Suborganismo → EquipoOrganismo.
El equipo es permanente en el perfil (`equipo_taller` +
`equipo_taller_edicion`); la inscripción conserva su copia por edición.

Reglas:
- Cuentas separadas del FICED: una cuenta con `subrol_ficed` no puede
  tener equipo de taller y viceversa.
- Integridad: equipo.suborganismo.organismo == perfil.organismo.
- Nada se borra: suborganismos/equipos se desactivan.
- Relevo = usuario nuevo (las cuentas del taller son personales).
"""
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import model_to_dict

from indicadores.cuentas import emitir_password_temporal
from indicadores.models import (EquipoOrganismo, Organismo,
                                PerfilRecolector, Suborganismo)
from indicadores.models_taller import InscripcionTaller

ROLES_TALLER = ('delegado', 'analista')


# ── Usuarios ─────────────────────────────────────────────────────────

def _validar_taller(rol, organismo, equipo, subrol_ficed):
    errores = {}
    if rol not in ROLES_TALLER:
        errores['rol'] = f'El rol {rol!r} no se gestiona desde el Taller.'
    if rol == 'delegado' and not organismo:
        errores['organismo'] = 'El delegado del taller exige organismo.'
    if equipo:
        if subrol_ficed:
            errores['equipo_taller'] = (
                'Cuentas separadas: un usuario con equipo FICED '
                '(subrol) no puede tener equipo de taller.')
        if organismo and equipo.suborganismo_id and \
                equipo.suborganismo.organismo_id != organismo.id:
            errores['equipo_taller'] = (
                'El equipo no pertenece al organismo asignado: '
                f'«{equipo.suborganismo.organismo.nombre}» ≠ '
                f'«{organismo.nombre}».')
    if errores:
        raise ValidationError(errores)


def crear_usuario_taller(*, username, email='', first_name='', last_name='',
                         rol, organismo=None, equipo=None, edicion=None,
                         activo=True, enviar_correo=True):
    """Crea User + PerfilRecolector del taller.

    `equipo` (EquipoOrganismo) queda permanente en el perfil con la
    edición en que se asignó; las cuentas del taller son personales.
    Devuelve (user, correo_estado)."""
    _validar_taller(rol, organismo, equipo, '')
    if User.objects.filter(username=username).exists():
        raise ValidationError({'username': 'Ese nombre de usuario ya existe.'})
    if email and User.objects.filter(email=email).exists():
        raise ValidationError(
            {'email': f'Otro usuario ya usa el correo {email}.'})

    user = User.objects.create_user(
        username=username, email=email,
        first_name=first_name, last_name=last_name)
    user.is_active = activo
    user.set_unusable_password()
    user.save()

    PerfilRecolector.objects.create(
        user=user, rol=rol, organismo=organismo,
        equipo_taller=equipo,
        equipo_taller_edicion=edicion if equipo else None,
        activo=activo)

    estado = 'omitido'
    if enviar_correo and activo:
        estado = emitir_password_temporal(user)
    return user, estado


def asignar_equipo_taller(perfil, equipo, edicion):
    """Asigna o actualiza el equipo permanente con regla de integridad.

    Devuelve (antes, despues). La edición confirma cuándo se fijó;
    al abrir una edición nueva se llama de nuevo con el año nuevo."""
    _validar_taller(perfil.rol, perfil.organismo, equipo,
                    perfil.subrol_ficed)
    antes = {'equipo_taller_id': perfil.equipo_taller_id,
             'equipo_taller_edicion': perfil.equipo_taller_edicion}
    perfil.equipo_taller = equipo
    perfil.equipo_taller_edicion = edicion if equipo else None
    perfil.save(update_fields=['equipo_taller', 'equipo_taller_edicion'])
    return antes, {'equipo_taller_id': perfil.equipo_taller_id,
                   'equipo_taller_edicion': perfil.equipo_taller_edicion}


def confirmar_equipo_edicion(perfil, edicion):
    """El equipo permanente se confirma para la edición actual."""
    perfil.equipo_taller_edicion = edicion
    perfil.save(update_fields=['equipo_taller_edicion'])


def cambiar_organismo_taller(perfil, organismo):
    """Cambio de organismo: si hay equipo, valida la integridad."""
    _validar_taller(perfil.rol, organismo, perfil.equipo_taller,
                    perfil.subrol_ficed)
    antes = {'organismo_id': perfil.organismo_id}
    perfil.organismo = organismo
    perfil.save(update_fields=['organismo'])
    return antes, {'organismo_id': perfil.organismo_id}


# ── Estructura: Organismo → Suborganismo → Equipo ─────────────────────

def crear_suborganismo(*, organismo, nombre, codigo='', tipo='', orden=0):
    if not nombre:
        raise ValidationError({'nombre': 'El nombre es obligatorio.'})
    if not codigo:
        import uuid as _uuid
        codigo = f'sub-{_uuid.uuid4().hex[:8]}'
    return Suborganismo.objects.create(
        organismo=organismo, nombre=nombre, codigo=codigo,
        tipo=tipo, orden=orden, activo=True)


def crear_equipo(*, suborganismo, nombre, codigo=''):
    if not nombre:
        raise ValidationError({'nombre': 'El nombre es obligatorio.'})
    if not codigo:
        import uuid as _uuid
        codigo = f'eq-{_uuid.uuid4().hex[:8]}'
    return EquipoOrganismo.objects.create(
        suborganismo=suborganismo, nombre=nombre, codigo=codigo,
        activo=True)


def _tiene_uso_suborganismo(sub):
    return InscripcionTaller.objects.filter(suborganismo=sub).exists() \
        or sub.equipos.filter(
            inscripciones_taller__isnull=False).exists() \
        or sub.equipos.filter(
            miembros_permanentes__isnull=False).exists()


def _tiene_uso_equipo(equipo):
    return InscripcionTaller.objects.filter(equipo=equipo).exists() \
        or equipo.miembros_permanentes.exists()


def desactivar_suborganismo(sub):
    if _tiene_uso_suborganismo(sub):
        return 'desactivado'      # con uso: solo se apaga, nunca se borra
    sub.activo = False
    sub.save(update_fields=['activo'])
    return 'desactivado'


def desactivar_equipo(equipo):
    equipo.activo = False
    equipo.save(update_fields=['activo'])
    return 'desactivado'


def activar_suborganismo(sub):
    sub.activo = True
    sub.save(update_fields=['activo'])


def activar_equipo(equipo):
    equipo.activo = True
    equipo.save(update_fields=['activo'])


def renombrar(obj, nombre):
    antes = obj.nombre
    obj.nombre = nombre
    obj.save(update_fields=['nombre'])
    return antes


# ── Inscripciones ─────────────────────────────────────────────────────

def copia_inscripcion(ins):
    """Respaldo JSON de la inscripción y sus fichas relacionadas."""
    data = model_to_dict(ins)
    data['creado'] = str(ins.creado)
    data['actualizado'] = str(ins.actualizado)
    for rel in ('reto',):
        try:
            obj = getattr(ins, rel)
        except Exception:
            obj = None
        if obj is not None:
            data[rel] = model_to_dict(obj)
    return data


def reabrir_inscripcion(ins):
    """completada → en_progreso (reversible)."""
    if ins.estado != InscripcionTaller.Estado.COMPLETADA:
        raise ValidationError(
            f'La inscripción está en «{ins.get_estado_display()}»; '
            'solo se reabre una completada.')
    antes = {'estado': ins.estado}
    ins.estado = InscripcionTaller.Estado.EN_PROGRESO
    ins.save(update_fields=['estado'])
    return antes, {'estado': ins.estado}


def reasignar_inscripcion(ins, *, organismo=None, suborganismo='-',
                          equipo='-', user=None):
    """Reasigna organismo/equipo/usuario de una inscripción.

    `'-'` = no tocar; `None` = limpiar. Integridad:
    equipo.suborganismo.organismo == organismo final."""
    org_final = organismo if organismo is not None else ins.organismo
    eq_final = ins.equipo if equipo == '-' else equipo
    if eq_final and eq_final.suborganismo_id and \
            eq_final.suborganismo.organismo_id != org_final.pk:
        raise ValidationError(
            'El equipo no pertenece al organismo de la inscripción.')

    antes = {'organismo_id': ins.organismo_id,
             'suborganismo_id': ins.suborganismo_id,
             'equipo_id': ins.equipo_id, 'user_id': ins.user_id}
    with transaction.atomic():
        if organismo is not None:
            ins.organismo = organismo
        if suborganismo != '-':
            ins.suborganismo = suborganismo
        if equipo != '-':
            ins.equipo = equipo
        if user is not None:
            ins.user = user
        ins.save()
    return antes, {'organismo_id': ins.organismo_id,
                   'suborganismo_id': ins.suborganismo_id,
                   'equipo_id': ins.equipo_id, 'user_id': ins.user_id}


def reiniciar_inscripcion(ins):
    """Borra la inscripción guardando copia (misma regla que FICED)."""
    copia = copia_inscripcion(ins)
    with transaction.atomic():
        ins.delete()
    return copia


def inscripciones_sin_equipo(edicion=None):
    """Conciliación: inscripciones con texto en `equipo_responsable`
    pero sin equipo normalizado asignado."""
    qs = (InscripcionTaller.objects
          .filter(equipo__isnull=True)
          .exclude(equipo_responsable='')
          .select_related('organismo', 'user')
          .order_by('organismo__nombre', 'equipo_responsable'))
    if edicion:
        qs = qs.filter(edicion=edicion)
    return qs
