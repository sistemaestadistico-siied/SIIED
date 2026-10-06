# Generated manually: permite que ICEDProcedimiento cuelgue de un Proceso
# (el MOP real tiene procesos con procedimientos directos, sin subprocesos).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0094_graficoserie_desagregaciones'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='icedprocedimiento',
            options={
                'ordering': ['codigo'],
                'verbose_name': 'Procedimiento ICED',
                'verbose_name_plural': 'Procedimientos ICED',
            },
        ),
        migrations.AlterField(
            model_name='icedprocedimiento',
            name='subproceso',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='procedimientos',
                to='indicadores.icedsubproceso',
            ),
        ),
        migrations.AddField(
            model_name='icedprocedimiento',
            name='proceso',
            field=models.ForeignKey(
                blank=True,
                help_text='Solo para procedimientos que cuelgan directamente del proceso (sin subproceso)',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='procedimientos_directos',
                to='indicadores.icedproceso',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='icedprocedimiento',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='icedprocedimiento',
            constraint=models.CheckConstraint(
                check=models.Q(
                    ('subproceso__isnull', False),
                    ('proceso__isnull', False),
                    _connector='OR',
                ),
                name='iced_procedimiento_padre_requerido',
            ),
        ),
    ]
