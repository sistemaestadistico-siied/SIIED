# Seed de la asignación pregunta ↔ equipo técnico del FICED.
# Fuente: matriz "Relación pregunta_equipos_tec_2025" (CSV) ya conciliada
# con los campos reales del wizard (pN_*). Se embebe aquí para no depender
# del CSV en producción.

from django.db import migrations

# codigo_pregunta → [equipos técnicos asignados]
PREGUNTA_EQUIPO = {
    '1': ['ETGIE', 'ETOBS', 'ETPP', 'ETSGC', 'ETUAG_PSP'],
    '6': ['ETSGC'],
    '7': ['ETSGC'],
    '8': ['ETGIE', 'ETOBS', 'ETPP', 'ETUAG_PSP'],
    '9': ['ETGIE', 'ETOBS', 'ETPP', 'ETUAG_PSP'],
    '10': ['ETGIE', 'ETOBS', 'ETPP', 'ETSGC', 'ETUAG_PSP'],
    '11': ['ETGIE', 'ETOBS', 'ETPP'],
    '12': ['ETSGC'],
    '13': ['ETGIE', 'ETOBS', 'ETPP'],
    '14': ['ETGIE', 'ETOBS', 'ETPP'],
    '15': ['ETGIE', 'ETOBS', 'ETPP'],
    '15.1': ['ETGIE', 'ETOBS', 'ETPP'],
    '16': ['ETGIE', 'ETOBS', 'ETPP'],
    '17': ['ETGIE', 'ETOBS', 'ETPP', 'ETSGC', 'ETUAG_PSP'],
    '18': ['ETSGC', 'ETUAG_PSP'],
    '19': ['ETGIE', 'ETOBS', 'ETPP'],
    '20': ['ETGIE', 'ETOBS', 'ETPP', 'ETSGC', 'ETUAG_PSP'],
    '21': ['ETUAG_PSP'],
    '22': ['ETGIE', 'ETOBS', 'ETPP', 'ETSGC', 'ETUAG_PSP'],
    '23': ['ETGIE'],
    '24': ['ETGIE', 'ETOBS', 'ETPP'],
    '24.1': ['ETGIE', 'ETOBS', 'ETPP'],
    '25': ['ETGIE', 'ETOBS', 'ETPP'],
    '26': ['ETPP', 'ETUAG_PSP'],
    '27': ['ETPP', 'ETUAG_PSP'],
    '28': ['ETPP', 'ETUAG_PSP'],
    '28.1': ['ETPP', 'ETUAG_PSP'],
    '28.2': ['ETPP', 'ETUAG_PSP'],
    '29': ['ETPP'],
    '29.1': ['ETPP'],
    '29.2': ['ETPP'],
    '29.3': ['ETPP'],
    '29.4': ['ETPP'],
    '30': ['ETGIE', 'ETOBS', 'ETPP'],
    '31': ['ETGIE', 'ETOBS', 'ETPP'],
    '31.1': ['ETGIE', 'ETOBS', 'ETPP'],
    '32': ['ETGIE', 'ETOBS', 'ETPP'],
    '33': ['ETOBS'],
    '34': ['ETOBS'],
    '35': ['ETOBS'],
    '36': ['ETGIE', 'ETOBS', 'ETPP', 'ETUAG_PSP'],
    '37': ['ETGIE', 'ETOBS', 'ETPP'],
    '38': ['ETGIE', 'ETOBS', 'ETPP'],
    '39': ['ETGIE', 'ETOBS', 'ETPP'],
    '40': ['ETGIE', 'ETOBS', 'ETPP'],
    '41': ['ETGIE'],
    '41.1': ['ETGIE'],
    '41.2': ['ETGIE'],
    '42': ['ETGIE', 'ETOBS', 'ETPP', 'ETSGC', 'ETUAG_PSP'],
}


def seed(apps, schema_editor):
    ICEDPreguntaEquipo = apps.get_model('indicadores', 'ICEDPreguntaEquipo')
    for codigo, equipos in PREGUNTA_EQUIPO.items():
        for equipo in equipos:
            ICEDPreguntaEquipo.objects.get_or_create(
                codigo=codigo, equipo=equipo
            )


def unseed(apps, schema_editor):
    ICEDPreguntaEquipo = apps.get_model('indicadores', 'ICEDPreguntaEquipo')
    for codigo, equipos in PREGUNTA_EQUIPO.items():
        ICEDPreguntaEquipo.objects.filter(
            codigo=codigo, equipo__in=equipos
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0111_iced_equipos'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
