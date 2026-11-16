from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0144_perfil_roles_gestion_debe_cambiar_password'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='perfilrecolector',
            constraint=models.UniqueConstraint(
                condition=models.Q(('activo', True), ('rol', 'validador_organismo')),
                fields=('organismo',),
                name='uniq_validador_organismo_activo',
                violation_error_message=(
                    'Este organismo ya tiene un validador del organismo '
                    'activo. Desactive el actual antes de asignar otro.'),
            ),
        ),
        migrations.AddConstraint(
            model_name='perfilrecolector',
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ('activo', True), ('rol', 'delegado'),
                    models.Q(('subrol_ficed', ''), _negated=True)),
                fields=('organismo', 'subrol_ficed'),
                name='uniq_delegado_subrol_activo',
                violation_error_message=(
                    'Este organismo ya tiene un delegado activo para ese '
                    'equipo técnico FICED. Desactive el actual antes de '
                    'asignar otro.'),
            ),
        ),
    ]
