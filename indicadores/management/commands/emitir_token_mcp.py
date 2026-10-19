# -*- coding: utf-8 -*-
"""Emite un token MCP personal para un usuario del sistema.

    python manage.py emitir_token_mcp --username jdoe --nombre "Claude desktop"
    python manage.py emitir_token_mcp --username jdoe --nombre "bot" --dias 90

El token en claro se imprime UNA sola vez — en la BD solo queda su SHA-256.
El nivel de acceso lo define el PerfilRecolector del usuario en cada request:
sin perfil activo el token solo da acceso a la capa pública de consulta.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Emite un token Bearer MCP para un usuario'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)
        parser.add_argument('--nombre', required=True,
                            help='Descripción del cliente (ej: Claude desktop)')
        parser.add_argument('--dias', type=int, default=None,
                            help='Días de vigencia (vacío = sin caducidad)')

    def handle(self, *args, **options):
        from indicadores.models import MCPApiToken

        try:
            user = User.objects.get(username=options['username'])
        except User.DoesNotExist:
            raise CommandError(
                f"Usuario '{options['username']}' no existe.")

        expira_en = None
        if options['dias']:
            expira_en = timezone.now() + timezone.timedelta(
                days=options['dias'])

        instancia, raw = MCPApiToken.issue(
            user, options['nombre'], expira_en=expira_en)

        perfil = getattr(user, 'perfil_recolector', None)
        rol = perfil.rol if (perfil and perfil.activo) else 'publico'

        self.stdout.write(self.style.SUCCESS(
            f"Token emitido para {user.username} (rol actual: {rol})"))
        self.stdout.write(f"  nombre:    {instancia.nombre}")
        self.stdout.write(f"  expira:    {expira_en or 'nunca'}")
        self.stdout.write(self.style.WARNING(
            "\n  TOKEN (solo se muestra ahora — guárdalo):\n"))
        self.stdout.write(f"  {raw}\n")
        self.stdout.write(
            "Config del cliente: Authorization: Bearer <token> "
            "en http://<host>:<puerto>/mcp")
