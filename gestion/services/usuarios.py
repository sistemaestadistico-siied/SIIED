"""
Gestión de usuarios FICED (plan §3.2).

Reglas:
- `delegado` y `validador_organismo` exigen organismo.
- Un solo `validador_organismo` activo por organismo (BD + servicio).
- Un solo delegado activo por organismo × subrol (BD + servicio).
- `subrol_ficed` solo aplica a `delegado`; vacío = formulario completo
  (requiere confirmar en la vista).
- Nunca se borra: activar/desactivar. Los User sin perfil no se tocan.
- Las credenciales usan `emitir_password_temporal` (solo se guardan si
  el correo sale) y marcan `debe_cambiar_password`.
- Toda mutación devuelve los datos para que la vista registre la
  bitácora con antes/después.
"""
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from indicadores.cuentas import emitir_password_temporal
from indicadores.models import PerfilRecolector

from .correos import aviso_cambio_cuenta

ROLES_FICED = ('delegado', 'validador_organismo', 'validador')

_SUBROLES = {c for c, _ in PerfilRecolector.SUBROL_FICED_CHOICES}


def _validar(rol, subrol, organismo):
    errores = {}
    if rol not in ROLES_FICED:
        errores['rol'] = f'El rol {rol!r} no se gestiona desde FICED.'
    if rol in ('delegado', 'validador_organismo') and not organismo:
        errores['organismo'] = (
            'Delegado y validador del organismo exigen un organismo.')
    if rol != 'delegado' and subrol:
        errores['subrol_ficed'] = 'El subrol solo aplica a delegados.'
    if subrol and subrol not in _SUBROLES:
        errores['subrol_ficed'] = f'Equipo técnico inválido: {subrol!r}.'
    if errores:
        raise ValidationError(errores)


def _conflicto_unicidad(perfil, excluir_id=None):
    """Texto del duplicado que violaría las restricciones, o None."""
    qs = PerfilRecolector.objects.filter(
        activo=True, organismo=perfil.organismo)
    if excluir_id:
        qs = qs.exclude(pk=excluir_id)
    if perfil.rol == 'validador_organismo':
        otro = qs.filter(rol='validador_organismo').select_related('user').first()
        if otro:
            return (f'{otro.user.get_full_name() or otro.user.username} ya es '
                    f'validador del organismo. Desactívelo primero.')
    if perfil.rol == 'delegado' and perfil.subrol_ficed:
        otro = qs.filter(rol='delegado',
                         subrol_ficed=perfil.subrol_ficed
                         ).select_related('user').first()
        if otro:
            return (f'{otro.user.get_full_name() or otro.user.username} ya es '
                    f'delegado de {perfil.subrol_ficed} en ese organismo.')
    return None


def crear_usuario_ficed(*, username, email='', first_name='', last_name='',
                        rol, subrol='', organismo=None, activo=True,
                        enviar_correo=True):
    """Crea User + PerfilRecolector. Devuelve (user, correo_estado).

    `correo_estado`: 'enviado' | 'sin_correo' | 'fallido' | 'omitido'.
    La contraseña temporal solo se guarda si el correo sale; si el envío
    falla el usuario se crea igual pero queda sin contraseña usable
    (el gestor puede reintentar el correo luego)."""
    _validar(rol, subrol, organismo)
    if User.objects.filter(username=username).exists():
        raise ValidationError({'username': 'Ese nombre de usuario ya existe.'})
    if email and User.objects.filter(email=email).exists():
        raise ValidationError(
            {'email': f'Otro usuario ya usa el correo {email}.'})

    user = User.objects.create_user(
        username=username, email=email,
        first_name=first_name, last_name=last_name,
        password=User.objects.make_random_password())
    user.is_active = activo
    user.set_unusable_password()  # la real solo llega por correo
    user.save()

    perfil = PerfilRecolector(
        user=user, rol=rol, subrol_ficed=subrol,
        organismo=organismo, activo=activo)
    conflicto = _conflicto_unicidad(perfil)
    if conflicto:
        user.delete()
        raise ValidationError({'rol': conflicto})
    try:
        with transaction.atomic():
            perfil.save()
    except IntegrityError:
        raise ValidationError({'rol': 'Violación de unicidad: ya hay un '
                                      'activo con ese rol/organismo/subrol.'})

    estado = 'omitido'
    if enviar_correo and activo:
        estado = emitir_password_temporal(user)
    return user, estado


def _etq_subrol(perfil):
    return (dict(PerfilRecolector.SUBROL_FICED_CHOICES)
            .get(perfil.subrol_ficed) or 'Formulario completo')


def actualizar_usuario_ficed(user, *, first_name=None, last_name=None,
                             email=None, rol=None, subrol=None,
                             organismo='-', activo=None, motivo='',
                             aviso_correo=True):
    """Edita usuario y perfil con las reglas FICED.

    Devuelve (antes, despues, cambios) donde `cambios` son las tuplas
    (etiqueta, antes, después) para el correo de aviso y la bitácora.
    `organismo='-'` (default) = no tocar; None = limpiar.
    """
    perfil = user.perfil_recolector
    antes = {
        'rol': perfil.rol, 'subrol_ficed': perfil.subrol_ficed,
        'organismo_id': perfil.organismo_id, 'activo': perfil.activo,
        'email': user.email,
        'first_name': user.first_name, 'last_name': user.last_name,
    }

    nuevo_rol = rol if rol is not None else perfil.rol
    nuevo_subrol = subrol if subrol is not None else perfil.subrol_ficed
    nuevo_org = perfil.organismo if organismo == '-' else organismo
    nuevo_activo = activo if activo is not None else perfil.activo
    _validar(nuevo_rol, nuevo_subrol, nuevo_org)

    borrador = PerfilRecolector(
        rol=nuevo_rol, subrol_ficed=nuevo_subrol,
        organismo=nuevo_org, activo=nuevo_activo)
    if nuevo_activo:
        conflicto = _conflicto_unicidad(borrador, excluir_id=perfil.pk)
        if conflicto:
            raise ValidationError({'rol': conflicto})

    cambios = []
    if nuevo_rol != perfil.rol:
        cambios.append(('Rol', perfil.get_rol_display(),
                        dict(PerfilRecolector.ROL_CHOICES).get(nuevo_rol, nuevo_rol)))
    if nuevo_subrol != perfil.subrol_ficed:
        cambios.append(('Equipo técnico FICED', _etq_subrol(perfil),
                        _etq_subrol(borrador)))
    if nuevo_org != perfil.organismo:
        cambios.append(('Organismo',
                        perfil.organismo.nombre if perfil.organismo else '—',
                        nuevo_org.nombre if nuevo_org else '—'))
    if email is not None and email != user.email:
        cambios.append(('Correo', user.email, email))
    if nuevo_activo != perfil.activo:
        cambios.append(('Cuenta', 'activa' if perfil.activo else 'inactiva',
                        'activa' if nuevo_activo else 'inactiva'))

    with transaction.atomic():
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if email is not None:
            user.email = email
        user.is_active = nuevo_activo
        user.save()
        perfil.rol = nuevo_rol
        perfil.subrol_ficed = nuevo_subrol
        perfil.organismo = nuevo_org
        perfil.activo = nuevo_activo
        try:
            perfil.save()
        except IntegrityError:
            raise ValidationError(
                {'rol': 'Violación de unicidad: ya hay un activo con ese '
                        'rol/organismo/subrol.'})

    despues = {
        'rol': perfil.rol, 'subrol_ficed': perfil.subrol_ficed,
        'organismo_id': perfil.organismo_id, 'activo': perfil.activo,
        'email': user.email,
        'first_name': user.first_name, 'last_name': user.last_name,
    }

    correo_estado = 'omitido'
    if aviso_correo and cambios and user.email:
        ok, _ = aviso_cambio_cuenta(user, cambios)
        correo_estado = 'enviado' if ok else 'fallido'

    return antes, despues, cambios, correo_estado


def relevo_usuario_ficed(user, *, first_name, last_name, email,
                         enviar_correo=True):
    """Relevo de la persona detrás de una cuenta institucional.

    Cambia nombre y correo y emite credenciales nuevas; la cuenta, el
    organismo y su formulario se conservan (plan §3.2).
    """
    if email and User.objects.exclude(pk=user.pk).filter(email=email).exists():
        raise ValidationError({'email': f'Otro usuario ya usa {email}.'})
    user.first_name = first_name
    user.last_name = last_name
    user.email = email
    user.save()
    estado = emitir_password_temporal(user) if enviar_correo else 'omitido'
    return estado


def restablecer_password(user):
    """Nueva temporal por correo; el perfil queda marcado para cambiarla."""
    return emitir_password_temporal(user)


# =============================================================================
# Carga masiva CSV (§3.2)
# =============================================================================

def _parsear_csv_usuarios(archivo):
    """Lee el CSV de carga. Columnas esperadas (encabezados libres por
    nombre): username, nombres, apellidos, correo, organismo, rol,
    subrol_ficed, activo, enviar_correo."""
    import csv
    import io
    texto = archivo.read().decode('utf-8-sig')
    lector = csv.DictReader(io.StringIO(texto))
    filas = []
    for n, fila in enumerate(lector, start=2):  # fila 1 = encabezados
        filas.append((n, {k.strip().lower(): (v or '').strip()
                          for k, v in fila.items() if k}))
    return filas


def _organismo_csv(texto, cache):
    key = (texto or '').strip().lower()
    if not key:
        return None
    if key not in cache:
        from indicadores.models import Organismo
        cache[key] = (Organismo.objects
                      .filter(nombre__iexact=texto.strip()).first()
                      or Organismo.objects
                      .filter(codigo__iexact=texto.strip()).first())
    return cache[key]


def validar_fila_usuario(fila, cache_org):
    """Errores de una fila sin escribir. Devuelve (datos, errores)."""
    errores = []
    username = fila.get('username', '').strip()
    rol = fila.get('rol', '').strip() or 'delegado'
    subrol = fila.get('subrol_ficed', '').strip().upper()
    organismo = _organismo_csv(fila.get('organismo', ''), cache_org)
    correo = fila.get('correo', '').strip()

    if not username:
        errores.append('username vacío')
    elif User.objects.filter(username=username).exists():
        errores.append('username ya existe')
    if correo and User.objects.filter(email=correo).exists():
        errores.append('correo ya usado por otro usuario')
    if rol not in ROLES_FICED:
        errores.append(f'rol inválido: {rol or "(vacío)"}')
    if fila.get('organismo') and not organismo:
        errores.append(f'organismo no encontrado: {fila["organismo"]}')
    if subrol and subrol not in _SUBROLES:
        errores.append(f'equipo inválido: {subrol}')
    try:
        _validar(rol, subrol, organismo)
    except ValidationError as e:
        errores.extend(m for msgs in e.message_dict.values() for m in msgs)

    datos = {
        'username': username,
        'first_name': fila.get('nombres', ''),
        'last_name': fila.get('apellidos', ''),
        'email': correo,
        'rol': rol, 'subrol': subrol,
        'organismo': organismo,
        'activo': fila.get('activo', '1').strip() in ('1', 'si', 'sí', 'true'),
        'enviar_correo': fila.get('enviar_correo', '1').strip() in
        ('1', 'si', 'sí', 'true'),
    }
    return datos, errores


def procesar_csv_usuarios(archivo, aplicar=False):
    """Dry-run o aplicación por fila. Devuelve filas con resultado.

    Cada fila: {n, datos, estado: 'ok'|'creado'|'error', errores: []}.
    En `aplicar`, los errores son por fila: las válidas se crean."""
    filas = _parsear_csv_usuarios(archivo)
    cache_org = {}
    resultado = []
    for n, fila in filas:
        datos, errores = validar_fila_usuario(fila, cache_org)
        estado = 'ok'
        if not errores and aplicar:
            try:
                user, correo_estado = crear_usuario_ficed(
                    **datos)
                estado = 'creado'
                if correo_estado == 'fallido':
                    errores.append('correo falló: credenciales no enviadas')
            except ValidationError as e:
                estado = 'error'
                errores.extend(m for msgs in e.message_dict.values()
                               for m in msgs)
        elif errores:
            estado = 'error'
        resultado.append({'n': n, 'datos': datos, 'estado': estado,
                          'errores': errores})
    return resultado
