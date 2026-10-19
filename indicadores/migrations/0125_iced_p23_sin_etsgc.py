# Ajuste de asignación (feedback): para ETSGC el formulario debe pasar de
# la pregunta 22 directo a observaciones; P23 (OOEE) no le corresponde.

from django.db import migrations


def quitar(apps, schema_editor):
    ICEDPreguntaEquipo = apps.get_model('indicadores', 'ICEDPreguntaEquipo')
    ICEDPreguntaEquipo.objects.filter(codigo='23', equipo='ETSGC').delete()


def restaurar(apps, schema_editor):
    ICEDPreguntaEquipo = apps.get_model('indicadores', 'ICEDPreguntaEquipo')
    ICEDPreguntaEquipo.objects.get_or_create(codigo='23', equipo='ETSGC')


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0124_iced_p23_todos_equipos'),
    ]

    operations = [
        migrations.RunPython(quitar, restaurar),
    ]
