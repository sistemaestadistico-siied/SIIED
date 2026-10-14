# Migración escrita a mano: el venv de producción tiene Django 3.2.12 y
# ninguno de los entornos locales coincide — se evita correr
# makemigrations con otra versión.
#
# Cambio estructural: el indicador puede pertenecer a varios subtemas de
# dominios distintos.
#   - `subtema` (FK existente) queda como subtema PRINCIPAL / ruta canónica.
#   - `subtemas_adicionales` (M2M nuevo, blank) añade las demás
#     clasificaciones. No requiere migración de datos: la FK se conserva.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0113_alter_icedformulario_estado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='indicador',
            name='subtema',
            field=models.ForeignKey(
                help_text='Clasificación canónica del indicador (dominio › tema › subtema).',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='indicadores',
                to='indicadores.menusubtema',
                verbose_name='Subtema principal',
            ),
        ),
        migrations.AddField(
            model_name='indicador',
            name='subtemas_adicionales',
            field=models.ManyToManyField(
                blank=True,
                help_text='Otros subtemas (de cualquier dominio) bajo los que también se clasifica este indicador.',
                related_name='indicadores_adicionales',
                to='indicadores.menusubtema',
                verbose_name='Subtemas adicionales',
            ),
        ),
    ]
