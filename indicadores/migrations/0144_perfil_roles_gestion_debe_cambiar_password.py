from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0143_organismo_sin_pp_sin_obs'),
    ]

    operations = [
        migrations.AlterField(
            model_name='perfilrecolector',
            name='rol',
            field=models.CharField(
                choices=[
                    ('recolector', 'Recolector de Datos'),
                    ('consultor', 'Consultor de Reportes'),
                    ('ambos', 'Recolector y Consultor'),
                    ('delegado', 'Delegado de Organismo'),
                    ('validador', 'Validador Estadístico (SIIED)'),
                    ('editor', 'Editor de Contenidos'),
                    ('analista', 'Analista (Editorial + Reportes + Recolección + Validación + Analítica)'),
                    ('analista_organismo', 'Analista BI del Organismo (SIIED BI / Don Datico BI)'),
                    ('validador_organismo', 'Validador del Organismo (pre-validación)'),
                    ('gestor_formularios', 'Gestor de Talleres y Formularios'),
                    ('diligenciador', 'Diligenciador (responde encuestas a su nombre)'),
                    ('encuestador', 'Encuestador (diligencia encuestas por varias personas)'),
                ],
                default='recolector',
                help_text='Define a qué módulos tiene acceso el usuario',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='perfilrecolector',
            name='debe_cambiar_password',
            field=models.BooleanField(
                default=False,
                help_text='Tiene una contraseña temporal: debe cambiarla al ingresar',
            ),
        ),
    ]
