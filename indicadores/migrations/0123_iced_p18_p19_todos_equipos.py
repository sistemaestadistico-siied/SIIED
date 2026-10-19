# Corrección de asignación pregunta ↔ equipo (feedback de diligenciamiento):
# P18 y P19 deben responderse por TODOS los equipos. Antes P18 estaba en
# ETSGC/ETUAG_PSP y P19 en ETGIE/ETOBS/ETPP, de modo que P19 (que se
# despliega según la respuesta de P18) nunca aparecía junto a su disparador.

from django.db import migrations

EQUIPOS = ['ETUAG_PSP', 'ETOBS', 'ETPP', 'ETSGC', 'ETGIE']
PREGUNTAS = ['18', '19']
# Asignación previa, para revertir
ANTERIOR = {
    '18': ['ETSGC', 'ETUAG_PSP'],
    '19': ['ETGIE', 'ETOBS', 'ETPP'],
}


def asignar(apps, schema_editor):
    ICEDPreguntaEquipo = apps.get_model('indicadores', 'ICEDPreguntaEquipo')
    for codigo in PREGUNTAS:
        for equipo in EQUIPOS:
            ICEDPreguntaEquipo.objects.get_or_create(codigo=codigo, equipo=equipo)


def revertir(apps, schema_editor):
    ICEDPreguntaEquipo = apps.get_model('indicadores', 'ICEDPreguntaEquipo')
    for codigo in PREGUNTAS:
        ICEDPreguntaEquipo.objects.filter(codigo=codigo).exclude(
            equipo__in=ANTERIOR[codigo]
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0122_etiquetafuente_basecatalogo_fuente_origen_and_more'),
    ]

    operations = [
        migrations.RunPython(asignar, revertir),
    ]
