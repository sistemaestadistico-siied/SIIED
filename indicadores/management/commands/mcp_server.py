# -*- coding: utf-8 -*-
"""Sirve el servidor MCP del SIIED (streamable HTTP, capa pública).

    python manage.py mcp_server                  # 127.0.0.1:8001
    python manage.py mcp_server --host 0.0.0.0 --port 9000

El endpoint queda en http://<host>:<port>/mcp (JSON-RPC MCP, sin sesión).
En producción: correr como proceso aparte y enrutar /mcp desde el proxy.
"""
import uvicorn
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Levanta el servidor MCP del SIIED (streamable HTTP en /mcp)'

    def add_arguments(self, parser):
        parser.add_argument('--host', default='127.0.0.1')
        parser.add_argument('--port', type=int, default=8001)

    def handle(self, *args, **options):
        from indicadores.mcp_server import server
        app = server.streamable_http_app(
            streamable_http_path='/mcp',
            json_response=True,
            stateless_http=True,
            host=options['host'],
        )
        self.stdout.write(self.style.SUCCESS(
            f"MCP SIIED en http://{options['host']}:{options['port']}/mcp "
            "(capa pública, sin auth)"))
        uvicorn.run(app, host=options['host'], port=options['port'],
                    log_level='info')
