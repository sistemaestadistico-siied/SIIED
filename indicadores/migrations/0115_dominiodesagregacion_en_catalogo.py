from django.db import migrations, models


def marcar_existentes_en_catalogo(apps, schema_editor):
    """Baseline: los dominios que ya existen forman el catálogo oficial.
    A partir de aquí, los nuevos nacen como pendientes (en_catalogo=False)."""
    DominioDesagregacion = apps.get_model('indicadores', 'DominioDesagregacion')
    DominioDesagregacion.objects.update(en_catalogo=True)


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0114_indicador_subtemas_adicionales'),
    ]

    operations = [
        migrations.AddField(
            model_name='dominiodesagregacion',
            name='en_catalogo',
            field=models.BooleanField(
                default=False,
                help_text='Los dominios del catálogo son los que se ofrecen para '
                          "'asociar' en el wizard. Los pendientes esperan la decisión "
                          'del validador (catalogar / conciliar / eliminar).',
                verbose_name='En catálogo oficial',
            ),
        ),
        migrations.RunPython(
            marcar_existentes_en_catalogo,
            migrations.RunPython.noop,
        ),
    ]
