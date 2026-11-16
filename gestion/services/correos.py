"""Correos del módulo de gestión (sobre notifications._send_email)."""
from django.utils.html import escape

from indicadores.notifications import _send_email


def aviso_cambio_cuenta(user, cambios):
    """Avisa al usuario que su rol, subrol u organismo cambió.

    `cambios`: lista de tuplas (etiqueta, antes, después).
    Retorna (ok, error)."""
    if not user.email:
        return False, 'El usuario no tiene correo registrado.'

    filas = ''.join(
        f'<tr><td style="padding:8px 12px;background:#f0fdfa;'
        f'border:1px solid #ccfbf1;color:#374151;width:38%;">{escape(str(etq))}</td>'
        f'<td style="padding:8px 12px;border:1px solid #ccfbf1;color:#94a3b8;'
        f'text-decoration:line-through;">{escape(str(a) or "—")}</td>'
        f'<td style="padding:8px 12px;border:1px solid #ccfbf1;">'
        f'<strong>{escape(str(d) or "—")}</strong></td></tr>'
        for etq, a, d in cambios)

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#0d9488;padding:16px;border-radius:8px 8px 0 0;">
            <h2 style="color:#fff;margin:0;">Su cuenta SIIED fue actualizada</h2>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <p>Hola <strong>{escape(user.get_full_name() or user.username)}</strong>,</p>
            <p>El equipo SIIED modificó su cuenta. Los cambios son:</p>
            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
                <tr>
                    <th style="padding:8px 12px;text-align:left;background:#f8fafc;color:#64748b;">Dato</th>
                    <th style="padding:8px 12px;text-align:left;background:#f8fafc;color:#64748b;">Antes</th>
                    <th style="padding:8px 12px;text-align:left;background:#f8fafc;color:#64748b;">Ahora</th>
                </tr>
                {filas}
            </table>
            <p style="color:#6b7280;font-size:13px;">
                Si no esperaba este cambio o tiene dudas sobre su acceso,
                contacte al equipo SIIED.
            </p>
        </div>
    </div>"""
    r = _send_email(user.email, user.get_full_name() or user.username,
                    '[SIIED] Su cuenta fue actualizada', html)
    return r['success'], r.get('error')
