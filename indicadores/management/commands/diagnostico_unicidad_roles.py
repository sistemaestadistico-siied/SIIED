"""
Lista organismos con más de un validador del organismo activo, o con más
de un delegado activo para el mismo subrol FICED. Deben resolverse
(desactivando los sobrantes) antes de aplicar la restricción de unicidad.

Solo lectura: no modifica nada.

    python manage.py diagnostico_unicidad_roles
"""
from django.core.management.base import BaseCommand
from django.db.models import Count

from indicadores.models import PerfilRecolector


class Command(BaseCommand):
    help = 'Diagnóstico de duplicados: validador del organismo y delegado × subrol'

    def handle(self, *args, **options):
        activos = PerfilRecolector.objects.filter(
            activo=True, organismo__isnull=False)

        grupos = [
            ('Validador del organismo',
             activos.filter(rol='validador_organismo')
             .values('organismo', 'organismo__nombre')
             .annotate(n=Count('id')).filter(n__gt=1),
             lambda g: activos.filter(
                 rol='validador_organismo', organismo=g['organismo'])),
            ('Delegado × subrol FICED',
             activos.filter(rol='delegado').exclude(subrol_ficed='')
             .values('organismo', 'organismo__nombre', 'subrol_ficed')
             .annotate(n=Count('id')).filter(n__gt=1),
             lambda g: activos.filter(
                 rol='delegado', organismo=g['organismo'],
                 subrol_ficed=g['subrol_ficed'])),
        ]

        total = 0
        for titulo, qs, detalle in grupos:
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n{titulo}'))
            if not qs:
                self.stdout.write(self.style.SUCCESS('  Sin duplicados.'))
                continue
            for g in qs:
                total += 1
                sub = f" · {g['subrol_ficed']}" if 'subrol_ficed' in g else ''
                self.stdout.write(self.style.WARNING(
                    f"  {g['organismo__nombre']}{sub}: {g['n']} activos"))
                for p in detalle(g).select_related('user'):
                    u = p.user
                    self.stdout.write(
                        f"    - {u.username} ({u.get_full_name() or 's/n'}, "
                        f"{u.email or 'sin correo'}, "
                        f"último ingreso: {u.last_login or 'nunca'})")

        if total:
            self.stdout.write(self.style.ERROR(
                f'\n{total} grupo(s) con duplicados: desactive los sobrantes '
                'antes de aplicar la restricción.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                '\nListo para aplicar la restricción de unicidad.'))
