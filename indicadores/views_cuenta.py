"""
Cuenta del usuario: cambio de contraseña (obligatorio si tiene una
contraseña temporal).
"""
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .cuentas import debe_cambiar_password, marcar_cambio_password


@login_required(login_url='indicadores:delegado_login')
def cambiar_contrasena(request):
    obligatorio = debe_cambiar_password(request.user)
    destino = request.POST.get('next') or request.GET.get('next') or ''
    if not url_has_allowed_host_and_scheme(
            destino, allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        destino = ''

    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            marcar_cambio_password(user, False)
            messages.success(request, 'Su contraseña fue actualizada.')
            return redirect(destino or 'indicadores:acceso_modulos')
    else:
        form = PasswordChangeForm(request.user)

    for campo in form.fields.values():
        campo.widget.attrs['class'] = (
            'block w-full px-4 py-3 border border-slate-200 rounded-xl '
            'bg-white focus:outline-none focus:ring-2 focus:ring-cyan-400 '
            'focus:border-cyan-400 transition-colors')

    return render(request, 'cuenta/cambiar_contrasena.html', {
        'form': form,
        'obligatorio': obligatorio,
        'next': destino,
    })
