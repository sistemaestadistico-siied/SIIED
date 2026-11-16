"""Servicios del módulo Gestión (lógica fuera de las vistas)."""
from .auditoria import registrar_accion, serializar  # noqa: F401
from .ventanas import EstadoVentana, ventana_abierta  # noqa: F401
