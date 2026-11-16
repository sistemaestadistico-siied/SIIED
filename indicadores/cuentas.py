"""
Servicios de cuentas de usuario: emisión de contraseñas temporales y
cambio obligatorio en el primer ingreso.
"""
import secrets

from .models import PerfilRecolector
from .notifications import notificar_acceso_usuario


def emitir_password_temporal(user):
    """Genera una contraseña temporal, la envía por correo y SOLO si el
    envío fue exitoso la guarda y marca el perfil para que el usuario la
    cambie al ingresar. La temporal no vence: sirve hasta que la cambie.

    Retorna 'enviado', 'sin_correo' o 'fallido'."""
    if not user.email:
        return 'sin_correo'
    pwd = secrets.token_urlsafe(9)
    if not notificar_acceso_usuario(user, pwd):
        return 'fallido'
    user.set_password(pwd)
    user.save(update_fields=['password'])
    marcar_cambio_password(user, True)
    return 'enviado'


def marcar_cambio_password(user, valor):
    """Activa o limpia el flag debe_cambiar_password del perfil (si existe)."""
    PerfilRecolector.objects.filter(user=user).update(
        debe_cambiar_password=valor)


def debe_cambiar_password(user):
    if not user or not user.is_authenticated:
        return False
    perfil = getattr(user, 'perfil_recolector', None)
    return bool(perfil and perfil.debe_cambiar_password)
