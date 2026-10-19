# -*- coding: utf-8 -*-
"""Sirve el MCP del SIIED por transporte stdio (para clientes de escritorio).

A diferencia de `mcp_server` (HTTP), stdio lo SPAWNEA el propio cliente:
no hay que mantener ningún proceso corriendo. Cada conexión levanta una
instancia del servidor MCP hablando JSON-RPC por stdin/stdout.

Config en clientes tipo Claude Desktop / Gemini CLI (~/.gemini/settings.json):

    "mcpServers": {
      "siied": {
        "command": "<ruta_venv>/bin/python",
        "args": ["<proyecto>/manage.py", "mcp_stdio"],
        "env": {"SIIED_MCP_TOKEN": "<token opcional para capa por roles>"}
      }
    }

Nota para Devin Desktop / Windsurf (~/.config/devin/mcp_config.json):
preferir el entry point `indicadores.mcp_stdio_entry` (silencia el ruido
de setup antes de que corra este comando) y usar "env.PYTHONPATH" con la
raíz del proyecto — el schema de estos clientes NO soporta "cwd". Ver
docstring de indicadores/mcp_stdio_entry.py para la config verificada.

IMPORTANTE: por stdio no hay headers HTTP; la identidad se toma de la
variable de entorno SIIED_MCP_TOKEN (si el cliente la define) — sin ella
la sesión queda en capa pública.
"""
import asyncio
import os

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Sirve el MCP del SIIED por stdio (clientes de escritorio)'

    def handle(self, *args, **options):
        import sys

        # El import de mcp_server hace django.setup() e instancia servicios
        # que imprimen a stdout (warnings, banners de TTS/ML). Todo eso rompe
        # el framing JSON-RPC: redirigir stdout→stderr durante el setup.
        real_stdout = sys.stdout
        sys.stdout = sys.stderr
        try:
            from indicadores.mcp_server import server
        finally:
            sys.stdout = real_stdout
        # A partir de aquí solo el SDK escribe por stdout (él mismo desvía
        # sys.stdout para proteger el canal durante la sesión).
        asyncio.run(server.run_stdio_async())
