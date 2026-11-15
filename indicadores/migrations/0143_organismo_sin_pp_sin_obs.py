from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0142_datasetbi_titulo'),
    ]

    operations = [
        migrations.AddField(
            model_name='organismo',
            name='sin_pp',
            field=models.BooleanField(
                default=False,
                help_text="FICED: sin equipo de políticas públicas (ETPP); el "
                          "validador confirma P29 = 'No está involucrado' en la "
                          "conciliación.",
            ),
        ),
        migrations.AddField(
            model_name='organismo',
            name='sin_obs',
            field=models.BooleanField(
                default=False,
                help_text="FICED: sin equipo de observatorios (ETOBS); el "
                          "validador confirma P33 = 'No' en la conciliación.",
            ),
        ),
    ]
