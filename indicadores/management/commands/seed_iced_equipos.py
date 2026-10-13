"""
Carga la asignación pregunta ↔ equipo técnico del FICED desde un CSV.

Formato esperado (exportado de la matriz "Relación pregunta_equipos"):
    N,Pregunta,ETUAG_PSP,ETOBS,ETPP,ETSGC,ETGIE,PERFILES RESPONDE
    17,"Considera que las herramientas...",X,X,X,X,X,5

Uso:
    python manage.py seed_iced_equipos --csv 'ruta/al/archivo.csv'
    python manage.py seed_iced_equipos --csv 'ruta.csv' --limpiar   # borra asignaciones previas
"""
import csv

from django.core.management.base import BaseCommand

from indicadores.models_iced import ICEDPreguntaEquipo

EQUIPOS = ['ETUAG_PSP', 'ETOBS', 'ETPP', 'ETSGC', 'ETGIE']


class Command(BaseCommand):
    help = 'Siembra ICEDPreguntaEquipo (pregunta → equipo técnico) desde CSV'

    def add_arguments(self, parser):
        parser.add_argument('--csv', required=True, help='Ruta al CSV de relación')
        parser.add_argument(
            '--limpiar', action='store_true',
            help='Eliminar todas las asignaciones antes de cargar',
        )

    def handle(self, *args, **options):
        if options['limpiar']:
            n, _ = ICEDPreguntaEquipo.objects.all().delete()
            self.stdout.write(f'Eliminadas {n} asignaciones previas')

        with open(options['csv'], encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            faltantes = [e for e in EQUIPOS if e not in (reader.fieldnames or [])]
            if faltantes:
                self.stderr.write(
                    self.style.ERROR(
                        f'El CSV no tiene columnas de equipo: {faltantes}. '
                        f'Columnas halladas: {reader.fieldnames}'
                    )
                )
                return

            creadas, saltadas = 0, 0
            for row in reader:
                codigo = (row.get('N') or '').strip()
                if not codigo:
                    saltadas += 1
                    continue
                for equipo in EQUIPOS:
                    if (row.get(equipo) or '').strip().upper() == 'X':
                        _, created = ICEDPreguntaEquipo.objects.get_or_create(
                            codigo=codigo, equipo=equipo
                        )
                        creadas += int(created)

        por_equipo = {
            e: ICEDPreguntaEquipo.objects.filter(equipo=e).count()
            for e in EQUIPOS
        }
        self.stdout.write(self.style.SUCCESS(
            f'Asignaciones: {creadas} nuevas, {saltadas} filas sin código. '
            f'Total por equipo: {por_equipo}'
        ))
