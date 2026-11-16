# Equipo permanente del Taller de Gestión de Datos en el perfil,
# poblado desde la inscripción más reciente de cada usuario.
from django.db import migrations, models


def poblar_equipo_taller(apps, schema_editor):
    """equipo_taller <- equipo de la inscripción más reciente del usuario.

    `equipo_taller_edicion` queda con la edición de esa inscripción:
    la confirmación para la edición nueva la hace el gestor o el delegado.
    """
    Perfil = apps.get_model('indicadores', 'PerfilRecolector')
    Inscripcion = apps.get_model('indicadores', 'InscripcionTaller')
    db_alias = schema_editor.connection.alias

    recientes = {}
    for ins in (Inscripcion.objects.using(db_alias)
                .filter(user__isnull=False, equipo__isnull=False)
                .order_by('user_id', '-edicion', '-creado')
                .values('user_id', 'equipo_id', 'edicion')):
        recientes.setdefault(ins['user_id'],
                             (ins['equipo_id'], ins['edicion']))
    if not recientes:
        return
    for perfil in Perfil.objects.using(db_alias).filter(
            user_id__in=recientes):
        equipo_id, edicion = recientes[perfil.user_id]
        perfil.equipo_taller_id = equipo_id
        perfil.equipo_taller_edicion = edicion
        perfil.save(update_fields=['equipo_taller_id',
                                   'equipo_taller_edicion'])


def revertir(apps, schema_editor):
    Perfil = apps.get_model('indicadores', 'PerfilRecolector')
    Perfil.objects.using(schema_editor.connection.alias).update(
        equipo_taller=None, equipo_taller_edicion=None)


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0145_perfil_unicidad_validador_delegado'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfilrecolector',
            name='equipo_taller',
            field=models.ForeignKey(
                blank=True,
                help_text='Equipo de trabajo del Taller (Organismo → Suborganismo → Equipo)',
                null=True, on_delete=models.deletion.SET_NULL,
                related_name='miembros_permanentes',
                to='indicadores.equipoorganismo'),
        ),
        migrations.AddField(
            model_name='perfilrecolector',
            name='equipo_taller_edicion',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text='Última edición del taller en que se confirmó este equipo',
                null=True),
        ),
        migrations.RunPython(poblar_equipo_taller, revertir),
    ]
