# -*- coding: utf-8 -*-
"""Entry point stdio del MCP del SIIED para clientes de escritorio.

Uso (el cliente spawn-ea el proceso — no hay servidor que mantener):

    python -m indicadores.mcp_stdio_entry          # desde la raíz del proyecto
    python indicadores/mcp_stdio_entry.py          # equivalente

Config verificada — Devin Desktop / Windsurf
(~/.config/devin/mcp_config.json; legacy: ~/.codeium/windsurf/mcp_config.json):

    "mcpServers": {
      "siied": {
        "command": "<venv>/bin/python",
        "args": ["-m", "indicadores.mcp_stdio_entry"],
        "env": {
          "PYTHONPATH": "<raíz del proyecto SIIED>",
          "SIIED_MCP_TOKEN": "<token opcional — capa por roles>"
        }
      }
    }

OJO: el schema de Devin/Windsurf NO soporta "cwd" (additionalProperties:
false) — el campo se ignora en silencio, el proceso muere con
ModuleNotFoundError y el cliente reporta "transport closed". PYTHONPATH
en env es la forma soportada de hacer `indicadores` importable.
Claude Desktop sí acepta "cwd" en lugar de PYTHONPATH.

Por qué existe este archivo y no solo `manage.py mcp_stdio`: manage.py
ejecuta django.setup() antes de que el comando pueda silenciar stdout,
y los prints de setup (TTS, ML, warnings) corrompen el framing JSON-RPC.
Aquí redirigimos stdout → stderr ANTES de importar nada del proyecto.
"""
import asyncio
import os
import sys


def main():
    # sys.stdout → stderr SOLO durante el import: los prints de setup
    # (TTS, ML, warnings) no deben salir por fd 1. DESPUÉS hay que
    # restaurar el sys.stdout real, porque el SDK MCP decide el canal:
    # si sys.stdout está respaldado por fd 1, lo clama para JSON-RPC y
    # desvía el resto a stderr él mismo; si no (p.ej. ya redirigido a
    # stderr), escribe el JSON-RPC en el buffer de ese stream — y con
    # stderr las respuestas nunca llegan al cliente.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr

    # Lo mismo a nivel de descriptor para ruido de extensiones en C
    # (torch, libs nativas) que escriben a fd 1 sin pasar por sys.stdout.
    saved_fd1 = os.dup(1)
    try:
        os.dup2(2, 1)
        from indicadores.mcp_server import server  # noqa: E402
    finally:
        os.dup2(saved_fd1, 1)      # fd 1 de vuelta al wire
        os.close(saved_fd1)
        sys.stdout = real_stdout   # objeto respaldado por fd 1 otra vez

    asyncio.run(server.run_stdio_async())


if __name__ == '__main__':
    main()
