import os
import sys
import threading
import subprocess
import time
from datetime import datetime
from typing import Optional

from django.utils import timezone
from django.db import close_old_connections, transaction
from django.db.utils import OperationalError

from .models import ProcesoExtraccion, ProcesoLog


def _with_retry(func, attempts: int = 5, base_sleep: float = 0.2):
    for intento in range(attempts):
        try:
            return func()
        except OperationalError:
            # Backoff exponencial ante "database is locked"
            close_old_connections()
            time.sleep(base_sleep * (2 ** intento))
        except Exception:
            # No propagar otros errores en el hilo de logging/estado
            break


def _escribir_log(proceso: ProcesoExtraccion, mensaje: str, nivel: str = 'INFO') -> None:
    # Método de respaldo para eventos puntuales
    def _do():
        ProcesoLog.objects.create(proceso=proceso, nivel=nivel, mensaje=mensaje[:4000])
    _with_retry(_do)


def _run_command_in_thread(proceso_id: int) -> None:
    # Separar conexión del hilo principal
    close_old_connections()

    try:
        proceso = ProcesoExtraccion.objects.select_related('indicador').get(id=proceso_id)
    except ProcesoExtraccion.DoesNotExist:
        return

    # Actualizar estado a procesando (con reintentos)
    proceso.estado = 'procesando'
    proceso.started_at = timezone.now()
    _with_retry(lambda: proceso.save(update_fields=['estado', 'started_at']))

    indicador_id = proceso.indicador_id

    # Construir ruta a manage.py
    base_dir = None
    try:
        from django.conf import settings
        base_dir = getattr(settings, 'BASE_DIR', None)
    except Exception:
        base_dir = None

    if not base_dir:
        # /app/indicadores/background.py -> subir dos niveles
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    manage_py_path = os.path.join(base_dir, 'manage.py')

    cmd = [
        sys.executable,
        manage_py_path,
        'procesar_conjunto_datos_cartesiano',
        '--indicador-id', str(indicador_id),
        '--eliminar-datos-previos',
        '-v', '3',  # habilitar verbosity 3 para ver logs detallados
    ]

    _escribir_log(proceso, f"Iniciando proceso de extracción para indicador {indicador_id}")

    # Buffer de logs para escrituras en lote
    logs_buffer = []
    last_flush = time.time()
    FLUSH_EVERY_N = 10   # cantidad de líneas
    FLUSH_EVERY_SEC = 0.5  # o cada 500ms

    def flush_buffer():
        nonlocal logs_buffer, last_flush
        if not logs_buffer:
            return
        payload = [ProcesoLog(proceso=proceso, nivel=nivel, mensaje=mensaje[:4000]) for nivel, mensaje in logs_buffer]

        def _do_bulk():
            # Una sola transacción corta
            with transaction.atomic():
                ProcesoLog.objects.bulk_create(payload, ignore_conflicts=False)
        _with_retry(_do_bulk)
        logs_buffer = []
        last_flush = time.time()

    # Forzar salida sin buffer del proceso hijo para streaming inmediato
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'

    try:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
        ) as p:
            # Leer línea a línea
            if p.stdout is not None:
                for line in p.stdout:
                    if not line:
                        continue
                    # Normalizar y guardar
                    msg = line.rstrip('\n')
                    logs_buffer.append(('INFO', msg))
                    now = time.time()
                    if len(logs_buffer) >= FLUSH_EVERY_N or (now - last_flush) >= FLUSH_EVERY_SEC:
                        flush_buffer()
            return_code = p.wait()

        # Flush final de logs pendientes
        flush_buffer()

        proceso.exit_code = return_code
        proceso.finished_at = timezone.now()
        if return_code == 0:
            proceso.estado = 'completado'
            _escribir_log(proceso, 'Proceso completado correctamente.')
        else:
            proceso.estado = 'error'
            proceso.error_message = f"El proceso finalizó con código {return_code}"
            _escribir_log(proceso, proceso.error_message, nivel='ERROR')
        _with_retry(lambda: proceso.save(update_fields=['exit_code', 'finished_at', 'estado', 'error_message']))

    except Exception as e:
        # Capturar excepción y marcar como error
        try:
            proceso.exit_code = -1
            proceso.finished_at = timezone.now()
            proceso.estado = 'error'
            proceso.error_message = str(e)
            _with_retry(lambda: proceso.save(update_fields=['exit_code', 'finished_at', 'estado', 'error_message']))
            _escribir_log(proceso, f"Excepción: {e}", nivel='ERROR')
        except Exception:
            pass


def lanzar_procesamiento_en_background(proceso_id: int) -> threading.Thread:
    """
    Lanza un hilo que ejecuta el comando de procesamiento y escribe logs en DB.
    Retorna el objeto Thread para referencia.
    """
    t = threading.Thread(target=_run_command_in_thread, args=(proceso_id,), daemon=True)
    t.start()
    return t
