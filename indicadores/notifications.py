"""
Sistema de notificaciones transaccionales via Brevo API.
"""

import logging
logger = logging.getLogger(__name__)

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


def _get_site_url():
    """Retorna la URL base del sitio para construir links absolutos."""
    site_url = getattr(settings, 'SITE_URL', '')
    if site_url:
        return site_url.rstrip('/')
    allowed = getattr(settings, 'ALLOWED_HOSTS', [])
    if allowed and allowed[0] != '*':
        return f"https://{allowed[0]}"
    return ''


def _is_valid_email(email):
    """Valida formato de email usando validador de Django."""
    if not email or not isinstance(email, str):
        return False
    try:
        validate_email(email)
        return True
    except ValidationError:
        return False


BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _get_api_key():
    return getattr(settings, 'BREVO_API_KEY', '')


def _send_email(to_email, to_name, subject, html_content):
    """Envia un email transaccional via Brevo API.
    Retorna dict con: success (bool), status_code, message_id, error."""
    result = {'success': False, 'status_code': None, 'message_id': None, 'error': None}

    if not _is_valid_email(to_email):
        result['error'] = f"Email destinatario inválido: {to_email}"
        logger.warning(f"[NOTIF] {_send_email.__name__}: {result['error']}")
        return result

    api_key = _get_api_key()
    if not api_key:
        logger.warning(f"[NOTIF] {_send_email.__name__}: No hay API key de Brevo. Intentando send_mail de Django...")
        try:
            sender = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@siied.gov.co')
            send_mail(
                subject=subject,
                message='',  # plaintext vacío; Brevo solo usaba HTML
                from_email=sender,
                recipient_list=[to_email],
                html_message=html_content,
                fail_silently=False,
            )
            result['success'] = True
            logger.info(f"[NOTIF] Email enviado via Django send_mail a {to_email}")
        except Exception as e:
            result['error'] = f"Brevo no configurado y send_mail falló: {str(e)}"
            logger.error(f"[NOTIF] {_send_email.__name__}: {result['error']}")
        return result

    payload = {
        "sender": {
            "name": "SIIED - Sistema de Indicadores",
            "email": getattr(settings, 'BREVO_SENDER_EMAIL', 'no-reply@siied.gov.co')
        },
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html_content,
    }

    try:
        logger.info(f"[NOTIF] Enviando email individual a {to_email}: {subject}")
        resp = requests.post(
            BREVO_API_URL,
            json=payload,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        result['status_code'] = resp.status_code

        if resp.status_code == 201:
            try:
                body = resp.json()
                result['message_id'] = body.get('messageId')
            except ValueError:
                pass
            result['success'] = True
            logger.info(f"[NOTIF] Email enviado exitosamente a {to_email}. MessageId: {result['message_id']}")
        else:
            try:
                body = resp.json()
                result['error'] = f"Brevo error {resp.status_code}: {body.get('message', resp.text[:200])}"
            except ValueError:
                result['error'] = f"Brevo error {resp.status_code}: {resp.text[:200]}"
            logger.error(f"[NOTIF] {_send_email.__name__}: {result['error']}")

    except requests.exceptions.Timeout:
        result['error'] = "Timeout al conectar con Brevo API"
        logger.error(f"[NOTIF] {_send_email.__name__}: {result['error']}")
    except requests.exceptions.ConnectionError:
        result['error'] = "Error de conexión con Brevo API"
        logger.error(f"[NOTIF] {_send_email.__name__}: {result['error']}")
    except Exception as e:
        result['error'] = f"Excepción inesperada: {str(e)}"
        logger.error(f"[NOTIF] {_send_email.__name__}: {result['error']}")

    return result


def _get_admin_emails():
    """Retorna SOLO emails de administradores (staff) para notificaciones
de recolección interna que van directo al wizard (sin validación)."""
    from django.contrib.auth.models import User

    emails = set()
    admins = User.objects.filter(is_staff=True, is_active=True).exclude(email='')
    logger.info(f"[NOTIF] Buscando admins: {admins.count()} encontrados")
    for user in admins:
        if user.email:
            emails.add(user.email)
            logger.info(f"[NOTIF] Admin email: {user.email}")

    # Emails adicionales desde settings (opcional)
    extra = getattr(settings, 'BREVO_NOTIFY_EMAILS', [])
    if isinstance(extra, str):
        extra = [e.strip() for e in extra.split(',') if e.strip()]
    for e in extra:
        if e:
            emails.add(e)
            logger.info(f"[NOTIF] Email extra desde settings: {e}")

    logger.info(f"[NOTIF] Total emails admin: {len(emails)}")
    return sorted(emails)


def _get_notify_emails():
    """Retorna emails de validadores + administradores para notificaciones
del flujo de delegados que SÍ requieren validación antes del wizard."""
    from django.contrib.auth.models import User
    from .models import PerfilRecolector

    emails = set()

    # Admins (staff)
    admins = User.objects.filter(is_staff=True, is_active=True).exclude(email='')
    for user in admins:
        if user.email:
            emails.add(user.email)

    # Validadores (PerfilRecolector con rol='validador')
    validadores = PerfilRecolector.objects.filter(rol='validador', activo=True).select_related('user')
    for perfil in validadores:
        if perfil.user.email:
            emails.add(perfil.user.email)

    # Emails adicionales desde settings (opcional)
    extra = getattr(settings, 'BREVO_NOTIFY_EMAILS', [])
    if isinstance(extra, str):
        extra = [e.strip() for e in extra.split(',') if e.strip()]
    for e in extra:
        if e:
            emails.add(e)

    logger.info(f"[NOTIF] Total emails validadores+admins: {len(emails)}")
    return sorted(emails)


def _send_bulk_email(recipients, subject, html_content):
    """Envia un email a múltiples destinatarios via Brevo API.
    Retorna dict con: success (bool), status_code, message_id, error, recipients_count."""
    result = {'success': False, 'status_code': None, 'message_id': None, 'error': None, 'recipients_count': len(recipients)}

    # Filtrar emails inválidos
    valid_recipients = [(email, name) for email, name in recipients if _is_valid_email(email)]
    invalid_count = len(recipients) - len(valid_recipients)
    if invalid_count:
        logger.warning(f"[NOTIF] {_send_bulk_email.__name__}: {invalid_count} emails inválidos descartados")

    if not valid_recipients:
        result['error'] = "No hay destinatarios válidos para enviar email"
        logger.error(f"[NOTIF] {_send_bulk_email.__name__}: {result['error']}")
        return result

    api_key = _get_api_key()
    logger.info(f"[NOTIF] {_send_bulk_email.__name__}: {len(valid_recipients)} destinatarios válidos (de {len(recipients)} total)")
    logger.info(f"[NOTIF] API Key configurada: {'SÍ' if api_key else 'NO'}")

    if not api_key:
        logger.warning(f"[NOTIF] {_send_bulk_email.__name__}: No hay API key de Brevo. Intentando send_mail de Django...")
        try:
            sender = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@siied.gov.co')
            emails_list = [email for email, name in valid_recipients]
            send_mail(
                subject=subject,
                message='',
                from_email=sender,
                recipient_list=emails_list,
                html_message=html_content,
                fail_silently=False,
            )
            result['success'] = True
            result['recipients_count'] = len(emails_list)
            logger.info(f"[NOTIF] Email bulk enviado via Django send_mail a {len(emails_list)} destinatarios")
        except Exception as e:
            result['error'] = f"Brevo no configurado y send_mail falló: {str(e)}"
            logger.error(f"[NOTIF] {_send_bulk_email.__name__}: {result['error']}")
        return result

    payload = {
        "sender": {
            "name": "SIIED - Sistema de Indicadores",
            "email": getattr(settings, 'BREVO_SENDER_EMAIL', 'no-reply@siied.gov.co')
        },
        "to": [{"email": email, "name": name} for email, name in valid_recipients],
        "subject": subject,
        "htmlContent": html_content,
    }

    try:
        logger.info(f"[NOTIF] Enviando email bulk a Brevo API: {subject}")
        resp = requests.post(
            BREVO_API_URL,
            json=payload,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        result['status_code'] = resp.status_code

        if resp.status_code == 201:
            try:
                body = resp.json()
                result['message_id'] = body.get('messageId')
            except ValueError:
                pass
            result['success'] = True
            logger.info(f"[NOTIF] Email bulk enviado exitosamente. MessageId: {result['message_id']}")
        elif resp.status_code == 429:
            result['error'] = f"Brevo rate limit (429): demasiadas peticiones. Body: {resp.text[:200]}"
            logger.error(f"[NOTIF] {_send_bulk_email.__name__}: {result['error']}")
        elif resp.status_code == 401:
            result['error'] = f"Brevo autenticación fallida (401): verifique la API key. Body: {resp.text[:200]}"
            logger.error(f"[NOTIF] {_send_bulk_email.__name__}: {result['error']}")
        else:
            try:
                body = resp.json()
                result['error'] = f"Brevo error {resp.status_code}: {body.get('message', resp.text[:200])}"
            except ValueError:
                result['error'] = f"Brevo error {resp.status_code}: {resp.text[:200]}"
            logger.error(f"[NOTIF] {_send_bulk_email.__name__}: {result['error']}")

    except requests.exceptions.Timeout:
        result['error'] = "Timeout al conectar con Brevo API"
        logger.error(f"[NOTIF] {_send_bulk_email.__name__}: {result['error']}")
    except requests.exceptions.ConnectionError:
        result['error'] = "Error de conexión con Brevo API"
        logger.error(f"[NOTIF] {_send_bulk_email.__name__}: {result['error']}")
    except Exception as e:
        result['error'] = f"Excepción inesperada: {str(e)}"
        logger.error(f"[NOTIF] {_send_bulk_email.__name__}: {result['error']}")

    return result


def notificar_validadores_nueva_carga_serie(carga):
    """Notifica a validadores/administradores que un delegado envió una carga de serie."""
    notify_emails = _get_notify_emails()
    if not notify_emails:
        return False

    organismo = ""
    if hasattr(carga.usuario, 'perfil_recolector') and carga.usuario.perfil_recolector.organismo:
        organismo = carga.usuario.perfil_recolector.organismo.nombre

    indicador_nombre = carga.indicador.nombre if carga.indicador else "Sin indicador"
    codigo = carga.codigo_evidencia
    delegado_nombre = carga.usuario.get_full_name() or carga.usuario.username

    subject = f"[SIIED] Nueva carga de serie pendiente: {codigo}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#6366f1;padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Nueva carga pendiente de validación</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p><strong>Código de evidencia:</strong> {codigo}</p>
            <p><strong>Indicador:</strong> {indicador_nombre}</p>
            <p><strong>Organismo:</strong> {organismo or 'No asignado'}</p>
            <p><strong>Delegado:</strong> {delegado_nombre}</p>
            <p><strong>Fecha de envío:</strong> {carga.fecha_carga.strftime('%d/%m/%Y %H:%M')}</p>
            <p style="margin-top:20px;">
                <a href="{_get_site_url()}/validacion/serie/{carga.id}/"
                   style="background:#6366f1;color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;">
                    Revisar carga
                </a>
            </p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                Este es un mensaje automático del SIIED. Tienes cargas pendientes de revisión en el panel de validación.
            </p>
        </div>
    </div>
    """

    recipients = [(email, "Validador SIIED") for email in notify_emails]
    return _send_bulk_email(recipients, subject, html).get('success', False)


def notificar_validadores_nueva_carga_conjunto_datos(carga):
    """Notifica a validadores/administradores que un delegado envió una carga de conjunto_datos."""
    notify_emails = _get_notify_emails()
    if not notify_emails:
        return False

    organismo = ""
    if hasattr(carga.usuario, 'perfil_recolector') and carga.usuario.perfil_recolector.organismo:
        organismo = carga.usuario.perfil_recolector.organismo.nombre

    conjunto_datos_nombre = carga.conjunto_datos.nombre if carga.conjunto_datos else "Nueva conjunto_datos"
    codigo = carga.codigo_evidencia
    delegado_nombre = carga.usuario.get_full_name() or carga.usuario.username

    subject = f"[SIIED] Nueva carga de conjunto_datos pendiente: {codigo}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#6366f1;padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Nueva carga pendiente de validación</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p><strong>Código de evidencia:</strong> {codigo}</p>
            <p><strong>conjunto_datos:</strong> {conjunto_datos_nombre}</p>
            <p><strong>Organismo:</strong> {organismo or 'No asignado'}</p>
            <p><strong>Delegado:</strong> {delegado_nombre}</p>
            <p><strong>Fecha de envío:</strong> {carga.fecha_carga.strftime('%d/%m/%Y %H:%M')}</p>
            <p style="margin-top:20px;">
                <a href="{_get_site_url()}/validacion/conjunto_datos/{carga.id}/"
                   style="background:#6366f1;color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;">
                    Revisar carga
                </a>
            </p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                Este es un mensaje automático del SIIED. Tienes cargas pendientes de revisión en el panel de validación.
            </p>
        </div>
    </div>
    """

    recipients = [(email, "Validador SIIED") for email in notify_emails]
    return _send_bulk_email(recipients, subject, html).get('success', False)


def notificar_admins_nueva_carga_recoleccion_serie(carga):
    """Notifica a admins que el equipo de recolección subió una serie para procesar en el wizard.
    Este flujo va directo al wizard (sin validación), por eso usa _get_admin_emails()."""
    logger.info(f"[NOTIF] notificar_admins_nueva_carga_recoleccion_serie llamada para carga {carga.codigo_evidencia}")

    notify_emails = _get_admin_emails()
    if not notify_emails:
        logger.error("[NOTIF] ERROR: No hay destinatarios admin para notificar carga de recolección serie")
        return False

    indicador_nombre = carga.indicador.nombre if carga.indicador else "Sin indicador"
    codigo = carga.codigo_evidencia
    recolector_nombre = carga.usuario.get_full_name() or carga.usuario.username

    subject = f"[SIIED] Nueva serie para wizard: {codigo}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#0891b2;padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Nueva carga desde recolección interna</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p><strong>Código de evidencia:</strong> {codigo}</p>
            <p><strong>Indicador:</strong> {indicador_nombre}</p>
            <p><strong>Subido por:</strong> {recolector_nombre}</p>
            <p><strong>Fecha:</strong> {carga.fecha_carga.strftime('%d/%m/%Y %H:%M')}</p>
            <p style="margin-top:20px;">
                <a href="{_get_site_url()}/admin/wizard/"
                   style="background:#0891b2;color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;">
                    Ir al wizard de administración
                </a>
            </p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                Este es un mensaje automático del SIIED. La carga está lista para ser procesada en el wizard.
            </p>
        </div>
    </div>
    """

    recipients = [(email, "Admin SIIED") for email in notify_emails]
    return _send_bulk_email(recipients, subject, html).get('success', False)


def notificar_admins_nueva_carga_recoleccion_conjunto_datos(carga):
    """Notifica a admins que el equipo de recolección subió conjunto_datos para procesar en el wizard.
    Este flujo va directo al wizard (sin validación), por eso usa _get_admin_emails()."""
    logger.info(f"[NOTIF] notificar_admins_nueva_carga_recoleccion_conjunto_datos llamada para carga {carga.codigo_evidencia}")

    notify_emails = _get_admin_emails()
    if not notify_emails:
        logger.error("[NOTIF] ERROR: No hay destinatarios admin para notificar carga de recolección conjunto_datos")
        return False

    conjunto_datos_nombre = carga.conjunto_datos.nombre if carga.conjunto_datos else "Nueva conjunto_datos"
    codigo = carga.codigo_evidencia
    recolector_nombre = carga.usuario.get_full_name() or carga.usuario.username

    subject = f"[SIIED] Nueva conjunto_datos para wizard: {codigo}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#0891b2;padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Nueva carga desde recolección interna</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p><strong>Código de evidencia:</strong> {codigo}</p>
            <p><strong>conjunto_datos:</strong> {conjunto_datos_nombre}</p>
            <p><strong>Subido por:</strong> {recolector_nombre}</p>
            <p><strong>Fecha:</strong> {carga.fecha_carga.strftime('%d/%m/%Y %H:%M')}</p>
            <p style="margin-top:20px;">
                <a href="{_get_site_url()}/admin/wizard/"
                   style="background:#0891b2;color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;">
                    Ir al wizard de administración
                </a>
            </p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                Este es un mensaje automático del SIIED. La carga está lista para ser procesada en el wizard.
            </p>
        </div>
    </div>
    """

    recipients = [(email, "Admin SIIED") for email in notify_emails]
    return _send_bulk_email(recipients, subject, html)


def notificar_delegado_serie(carga, accion, observaciones=""):
    """Notifica al delegado sobre la decisión del validador en una carga de serie."""
    usuario = carga.usuario
    if not usuario.email:
        return False

    indicador_nombre = carga.indicador.nombre if carga.indicador else "Sin indicador"
    codigo = carga.codigo_evidencia

    estados = {
        'aprobado': ("aprobada", "#16a34a"),
        'rechazado': ("rechazada", "#dc2626"),
        'correcciones_solicitadas': ("devuelta con correcciones", "#d97706"),
    }
    estado_texto, color = estados.get(accion, ("actualizada", "#6b7280"))

    subject = f"[SIIED] Carga {codigo} {estado_texto}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:{color};padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Carga {estado_texto.title()}</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p><strong>Código de evidencia:</strong> {codigo}</p>
            <p><strong>Indicador:</strong> {indicador_nombre}</p>
            <p><strong>Fecha de carga:</strong> {carga.fecha_carga.strftime('%d/%m/%Y %H:%M')}</p>
            {f'<div style="background:#fef3c7;border-left:4px solid {color};padding:12px;margin:16px 0;"><strong>Observaciones del validador:</strong><br>{observaciones}</div>' if observaciones else ''}
            <p style="margin-top:20px;">
                <a href="{_get_site_url()}/delegado/serie/{carga.id}/"
                   style="background:{color};color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;">
                    Ver detalle de la carga
                </a>
            </p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                Este es un mensaje automático del Sistema Integrado de Indicadores Estadísticos Distritales (SIIED).
                Por favor no responda a este correo.
            </p>
        </div>
    </div>
    """

    return _send_email(usuario.email, usuario.get_full_name() or usuario.username, subject, html).get('success', False)


def notificar_delegado_conjunto_datos(carga, accion, observaciones=""):
    """Notifica al delegado sobre la decisión del validador en una carga de conjunto_datos."""
    usuario = carga.usuario
    if not usuario.email:
        return False

    conjunto_datos_nombre = carga.conjunto_datos.nombre if carga.conjunto_datos else "Nueva conjunto_datos"
    codigo = carga.codigo_evidencia

    estados = {
        'aprobado': ("aprobada", "#16a34a"),
        'rechazado': ("rechazada", "#dc2626"),
        'correcciones_solicitadas': ("devuelta con correcciones", "#d97706"),
    }
    estado_texto, color = estados.get(accion, ("actualizada", "#6b7280"))

    subject = f"[SIIED] Carga {codigo} {estado_texto}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:{color};padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Carga {estado_texto.title()}</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p><strong>Código de evidencia:</strong> {codigo}</p>
            <p><strong>conjunto_datos:</strong> {conjunto_datos_nombre}</p>
            <p><strong>Fecha de carga:</strong> {carga.fecha_carga.strftime('%d/%m/%Y %H:%M')}</p>
            {f'<div style="background:#fef3c7;border-left:4px solid {color};padding:12px;margin:16px 0;"><strong>Observaciones del validador:</strong><br>{observaciones}</div>' if observaciones else ''}
            <p style="margin-top:20px;">
                <a href="{_get_site_url()}/delegado/conjunto_datos/{carga.id}/"
                   style="background:{color};color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;">
                    Ver detalle de la carga
                </a>
            </p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                Este es un mensaje automático del Sistema Integrado de Indicadores Estadísticos Distritales (SIIED).
                Por favor no responda a este correo.
            </p>
        </div>
    </div>
    """

    return _send_email(usuario.email, usuario.get_full_name() or usuario.username, subject, html).get('success', False)


def notificar_recolector_correccion_solicitada(carga, observaciones=""):
    """Notifica al recolector que el admin solicita correcciones en una carga desde el wizard."""
    usuario = carga.usuario
    if not usuario or not usuario.email:
        logger.warning("[NOTIF] notificar_recolector_correccion_solicitada: usuario sin email")
        return False

    codigo = getattr(carga, 'codigo_evidencia', 'N/A')
    indicador_nombre = carga.indicador.nombre if carga.indicador else "Sin indicador"

    subject = f"[SIIED] Corrección solicitada: {codigo}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#d97706;padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Corrección solicitada</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p><strong>Código de evidencia:</strong> {codigo}</p>
            <p><strong>Indicador:</strong> {indicador_nombre}</p>
            <p><strong>Estado:</strong> El administrador ha revisado tu carga y solicita correcciones.</p>
            {f'<div style="background:#fef3c7;border-left:4px solid #d97706;padding:12px;margin:16px 0;"><strong>Observaciones del administrador:</strong><br>{observaciones}</div>' if observaciones else ''}
            <p style="margin-top:20px;">
                <a href="{_get_site_url()}/recoleccion/serie/{carga.id}/"
                   style="background:#d97706;color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;">
                    Ver detalle y corregir
                </a>
            </p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                Este es un mensaje automático del SIIED. Por favor revise y corrija la carga indicada.
            </p>
        </div>
    </div>
    """

    return _send_email(
        usuario.email,
        usuario.get_full_name() or usuario.username,
        subject,
        html
    ).get('success', False)


def notificar_usuario_carga_procesada(carga):
    """Notifica al usuario (recolector/delegado) que su carga fue procesada por el wizard."""
    usuario = carga.usuario
    if not usuario or not usuario.email:
        logger.warning("[NOTIF] notificar_usuario_carga_procesada: usuario sin email")
        return False

    codigo = getattr(carga, 'codigo_evidencia', 'N/A')
    estado = getattr(carga, 'estado', 'unknown')
    es_serie = hasattr(carga, 'indicador')

    if estado in ('exitoso', 'procesado'):
        estado_texto = "procesada exitosamente"
        color = "#16a34a"
        resumen = "Tu carga fue integrada al sistema correctamente."
    elif estado == 'error':
        estado_texto = "procesada con errores"
        color = "#dc2626"
        mensaje_error = getattr(carga, 'mensaje_error', 'Error desconocido')
        resumen = f"Ocurrió un error durante el procesamiento: {mensaje_error}"
    else:
        logger.info(f"[NOTIF] Estado '{estado}' no requiere notificación de procesamiento")
        return False

    tipo = "Serie de datos" if es_serie else "Microdatos"
    indicador_nombre = carga.indicador.nombre if es_serie and carga.indicador else (
        carga.conjunto_datos.nombre if not es_serie and carga.conjunto_datos else "Sin nombre"
    )
    detalle_url = f"{_get_site_url()}/{'recoleccion' if not getattr(carga, 'es_carga_delegado', True) else 'delegado'}/{'serie' if es_serie else 'conjunto_datos'}/{carga.id}/"

    subject = f"[SIIED] Carga {codigo} {estado_texto}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:{color};padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Carga {estado_texto.title()}</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p><strong>Código de evidencia:</strong> {codigo}</p>
            <p><strong>Tipo:</strong> {tipo}</p>
            <p><strong>Indicador/conjunto_datos:</strong> {indicador_nombre}</p>
            <p><strong>Estado:</strong> {estado}</p>
            <p>{resumen}</p>
            <p style="margin-top:20px;">
                <a href="{detalle_url}"
                   style="background:{color};color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;">
                    Ver detalle de la carga
                </a>
            </p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                Este es un mensaje automático del Sistema Integrado de Indicadores Estadísticos Distritales (SIIED).
                Por favor no responda a este correo.
            </p>
        </div>
    </div>
    """

    return _send_email(
        usuario.email,
        usuario.get_full_name() or usuario.username,
        subject,
        html
    ).get('success', False)


# =============================================================================
# NOTIFICACIONES ICED (FICED)
# =============================================================================

def notificar_validadores_nuevo_iced(formulario):
    """Notifica a validadores/administradores que un organismo envió un formulario ICED."""
    notify_emails = _get_notify_emails()
    if not notify_emails:
        logger.warning("[NOTIF] notificar_validadores_nuevo_iced: sin destinatarios")
        return False

    organismo = formulario.organismo.nombre if formulario.organismo else 'No asignado'
    delegado = formulario.usuario_diligencia
    delegado_nombre = (delegado.get_full_name() or delegado.username) if delegado else 'No registrado'
    fecha_envio = formulario.fecha_envio.strftime('%d/%m/%Y %H:%M') if formulario.fecha_envio else '—'

    subject = f"[SIIED] Formulario ICED {formulario.periodo} enviado: {organismo}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#6366f1;padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Formulario ICED pendiente de validación</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p><strong>Organismo:</strong> {organismo}</p>
            <p><strong>Periodo:</strong> {formulario.periodo}</p>
            <p><strong>Diligenciado por:</strong> {delegado_nombre}</p>
            <p><strong>Fecha de envío:</strong> {fecha_envio}</p>
            <p style="margin-top:20px;">
                <a href="{_get_site_url()}/validacion/iced/{formulario.pk}/"
                   style="background:#6366f1;color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;">
                    Revisar formulario ICED
                </a>
            </p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                Este es un mensaje automático del SIIED. Revise las respuestas, ejecute el cálculo
                del índice y registre su decisión en el panel de validación.
            </p>
        </div>
    </div>
    """

    recipients = [(email, "Validador SIIED") for email in notify_emails]
    return _send_bulk_email(recipients, subject, html).get('success', False)


def notificar_delegado_iced(formulario, accion, observaciones=""):
    """Notifica al delegado la decisión del validador sobre su formulario ICED
    (accion: 'validado' o 'devuelto')."""
    usuario = formulario.usuario_diligencia
    if not usuario or not usuario.email:
        logger.warning(f"[NOTIF] notificar_delegado_iced: formulario {formulario.pk} sin usuario/email")
        return False

    organismo = formulario.organismo.nombre if formulario.organismo else ''

    if accion == 'validado':
        estado_texto = "validado y publicado"
        color = "#16a34a"
        pct = round(float(formulario.puntaje_global) * 100) if formulario.puntaje_global else 0
        resumen = (
            f"Su formulario ICED {formulario.periodo} fue aprobado por el equipo técnico del SIIED. "
            f"Puntaje global obtenido: <strong>{pct}%</strong> ({formulario.nivel_global_display})."
        )
        cta_url = f"{_get_site_url()}/iced/resultado/{formulario.pk}/"
        cta_texto = "Ver resultado detallado"
    elif accion == 'devuelto':
        estado_texto = "devuelto para corrección"
        color = "#d97706"
        resumen = (
            f"Su formulario ICED {formulario.periodo} fue devuelto por el equipo técnico del SIIED. "
            "Revise las observaciones, realice las correcciones indicadas y vuelva a enviarlo."
        )
        cta_url = f"{_get_site_url()}/iced/"
        cta_texto = "Retomar formulario"
    else:
        logger.info(f"[NOTIF] notificar_delegado_iced: acción '{accion}' no notificable")
        return False

    subject = f"[SIIED] Formulario ICED {formulario.periodo} {estado_texto}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:{color};padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Formulario ICED {estado_texto}</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p><strong>Organismo:</strong> {organismo}</p>
            <p><strong>Periodo:</strong> {formulario.periodo}</p>
            <p>{resumen}</p>
            {f'<div style="background:#fef3c7;border-left:4px solid {color};padding:12px;margin:16px 0;"><strong>Observaciones del validador:</strong><br>{observaciones}</div>' if observaciones else ''}
            <p style="margin-top:20px;">
                <a href="{cta_url}"
                   style="background:{color};color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;">
                    {cta_texto}
                </a>
            </p>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                Este es un mensaje automático del Sistema Integrado de Información Estadística Distrital (SIIED).
                Por favor no responda a este correo.
            </p>
        </div>
    </div>
    """

    return _send_email(
        usuario.email,
        usuario.get_full_name() or usuario.username,
        subject,
        html
    ).get('success', False)
