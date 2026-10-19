# Corrección de asignación (feedback de diligenciamiento): P23 (tabla de
# operaciones estadísticas) solo estaba asignada a ETGIE, así que el resto
# de equipos no veía la pregunta ("no sale nada"). Cada equipo debe
# relacionar sus operaciones vigentes; se incorpora a todos.

from django.db import migrations

EQUIPOS = ['ETUAG_PSP', 'ETOBS', 'ETPP', 'ETSGC', 'ETGIE']
ANTERIOR = ['ETGIE']  # asignación previa, para revertir


def asignar(apps, schema_editor):
    ICEDPreguntaEquipo = apps.get_model('indicadores', 'ICEDPreguntaEquipo')
    for equipo in EQUIPOS:
        ICEDPreguntaEquipo.objects.get_or_create(codigo='23', equipo=equipo)


def revertir(apps, schema_editor):
    ICEDPreguntaEquipo = apps.get_model('indicadores', 'ICEDPreguntaEquipo')
    ICEDPreguntaEquipo.objects.filter(codigo='23').exclude(
        equipo__in=ANTERIOR
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0123_iced_p18_p19_todos_equipos'),
    ]

    operations = [
        migrations.RunPython(asignar, revertir),
    ]
