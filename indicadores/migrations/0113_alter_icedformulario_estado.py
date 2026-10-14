from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0112_seed_iced_pregunta_equipo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='icedformulario',
            name='estado',
            field=models.CharField(choices=[('borrador', 'Borrador'), ('enviado', 'Enviado'), ('validado', 'Validado'), ('devuelto', 'Devuelto para corrección'), ('rechazado', 'Rechazado')], default='borrador', max_length=15),
        ),
    ]
