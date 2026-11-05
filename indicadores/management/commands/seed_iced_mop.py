"""
Carga la estructura del MOP (Mapa de Procesos) del FICED desde el
inventario del archivo Excel del instrumento.

Formato esperado: hoja 'inventario' del DADII_FICED (*.xlsm/*.xlsx) con
columnas en este orden (fila 1 = encabezado):

    NOMBRE DEL MACROPROCESO | CÓDIGO DEL MACROPROCESO |
    NOMBRE DEL PROCESO | CÓDIGO DEL PROCESO |
    NOMBRE DEL SUBPROCESO | CÓDIGO DEL SUBPROCESO |
    NOMBRE DEL PROCEDIMIENTO | CÓDIGO DEL PROCEDIMIENTO |
    NOMBRE DEL ÁREA ...

Filas donde el subproceso dice "No cuenta con subproceso vigente" crean
procedimientos que cuelgan directamente del proceso (procedimientos_directos).

Uso:
    python manage.py seed_iced_mop --xlsx 'ruta/DADII_FICED 2025-10-15_VF_V3.xlsm'
    python manage.py seed_iced_mop --xlsx 'ruta.xlsm' --limpiar  # borra todo antes
"""
import openpyxl

from django.core.management.base import BaseCommand
from django.db import transaction

from indicadores.models_iced import (
    ICEDMacroProceso, ICEDProceso, ICEDSubproceso, ICEDProcedimiento,
)

HOJA = 'inventario'
SIN_SUBPROCESO = 'no cuenta con subproceso'


def _txt(v):
    return str(v).strip() if v is not None else ''


class Command(BaseCommand):
    help = 'Siembra la estructura MOP (macroprocesos, procesos, subprocesos y procedimientos) desde el xlsm del FICED'

    def add_arguments(self, parser):
        parser.add_argument('--xlsx', required=True, help='Ruta al xlsm/xlsx del FICED')
        parser.add_argument('--sheet', default=HOJA, help=f'Hoja del inventario (default: {HOJA})')
        parser.add_argument(
            '--limpiar', action='store_true',
            help='Eliminar la estructura MOP existente antes de cargar',
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        wb = openpyxl.load_workbook(opts['xlsx'], read_only=True, data_only=True)
        if opts['sheet'] not in wb.sheetnames:
            self.stderr.write(self.style.ERROR(
                f"La hoja '{opts['sheet']}' no existe. Hojas: {wb.sheetnames}"
            ))
            return
        ws = wb[opts['sheet']]
        rows = ws.iter_rows(min_row=2, values_only=True)

        if opts['limpiar']:
            for m in (ICEDProcedimiento, ICEDSubproceso, ICEDProceso, ICEDMacroProceso):
                m.objects.all().delete()
            self.stdout.write('Estructura MOP anterior eliminada.')

        macros = {}     # codigo -> obj
        procesos = {}   # (macro_cod, codigo) -> obj
        subprocesos = {}  # (proc_cod, codigo) -> obj
        proc_vistos = set()   # (parent_cod, codigo)
        n_proc = 0
        n_filas = 0

        for row in rows:
            vals = [_txt(v) for v in list(row)[:8]] + [''] * 8
            n_mp, c_mp, n_pr, c_pr, n_sp, c_sp, n_pc, c_pc = vals[:8]
            if not c_mp:
                continue
            n_filas += 1

            mp = macros.get(c_mp)
            if mp is None:
                mp, _ = ICEDMacroProceso.objects.update_or_create(
                    codigo=c_mp, defaults={'nombre': n_mp[:200], 'activo': True}
                )
                macros[c_mp] = mp

            pr = None
            if c_pr:
                key = (c_mp, c_pr)
                pr = procesos.get(key)
                if pr is None:
                    pr, _ = ICEDProceso.objects.update_or_create(
                        macroproceso=mp, codigo=c_pr,
                        defaults={'nombre': n_pr[:200], 'activo': True},
                    )
                    procesos[key] = pr

            sp = None
            es_sin_sp = SIN_SUBPROCESO in n_sp.lower() or SIN_SUBPROCESO in c_sp.lower()
            if pr is not None and c_sp and not es_sin_sp:
                key = (c_pr, c_sp)
                sp = subprocesos.get(key)
                if sp is None:
                    sp, _ = ICEDSubproceso.objects.update_or_create(
                        proceso=pr, codigo=c_sp,
                        defaults={'nombre': n_sp[:200], 'activo': True},
                    )
                    subprocesos[key] = sp

            if c_pc:
                parent_cod = c_sp if sp is not None else c_pr
                key = (parent_cod, c_pc)
                if key in proc_vistos:
                    continue
                proc_vistos.add(key)
                defaults = {'nombre': n_pc[:200], 'activo': True}
                if sp is not None:
                    ICEDProcedimiento.objects.update_or_create(
                        subproceso=sp, codigo=c_pc, defaults=defaults,
                    )
                elif pr is not None:
                    ICEDProcedimiento.objects.update_or_create(
                        proceso=pr, subproceso=None, codigo=c_pc, defaults=defaults,
                    )
                else:
                    self.stderr.write(self.style.WARNING(
                        f'Fila {n_filas}: procedimiento {c_pc} sin proceso — omitido'
                    ))
                    continue
                n_proc += 1

        self.stdout.write(self.style.SUCCESS(
            f'MOP cargado desde {opts["xlsx"]} ({n_filas} filas):\n'
            f'  {len(macros)} macroprocesos\n'
            f'  {len(procesos)} procesos\n'
            f'  {len(subprocesos)} subprocesos\n'
            f'  {n_proc} procedimientos'
        ))
