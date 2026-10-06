# Corrección semántica: "microdata" -> "conjunto de datos".
# Metodológicamente la microdata estricta son los registros individuales de
# censos/registros administrativos (planestadistico.cali.gov.co/amda); los
# archivos que carga SIIED son conjuntos de datos (pueden o no ser agregados).
#
# RenameModel/RenameField conservan tablas, columnas y datos existentes.
# Los valores persistidos en choices (tipo_evento 'carga_microdata_wizard',
# tipo_bloque 'tabla_microdata', 'tabla_dinamica_microdata') y los directorios
# de media (upload_to='microdata/...') NO se renombran: son legado en disco/BD.

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0098_limpiar_decimales_valor_dato'),
    ]

    operations = [
        # ---- Renombrar modelos ----
        migrations.RenameModel(
            old_name='Microdata',
            new_name='ConjuntoDatos',
        ),
        migrations.RenameModel(
            old_name='VariableMicrodata',
            new_name='VariableConjuntoDatos',
        ),
        migrations.RenameModel(
            old_name='CargaMicrodata',
            new_name='CargaConjuntoDatos',
        ),

        # ---- Renombrar campos FK hacia ConjuntoDatos ----
        migrations.RenameField(
            model_name='indicador',
            old_name='microdata',
            new_name='conjunto_datos',
        ),
        migrations.RenameField(
            model_name='indicador',
            old_name='nombre_conjunto_microdata',
            new_name='nombre_conjunto_datos',
        ),
        migrations.RenameField(
            model_name='variableconjuntodatos',
            old_name='microdata',
            new_name='conjunto_datos',
        ),
        migrations.RenameField(
            model_name='cargaconjuntodatos',
            old_name='microdata',
            new_name='conjunto_datos',
        ),
        migrations.RenameField(
            model_name='productoacademico',
            old_name='microdata_principal',
            new_name='conjunto_datos_principal',
        ),
        migrations.RenameField(
            model_name='seccionpaper',
            old_name='microdata_vinculada',
            new_name='conjunto_datos_vinculado',
        ),
        migrations.RenameField(
            model_name='seccioneducativa',
            old_name='microdata_vinculada',
            new_name='conjunto_datos_vinculado',
        ),

        # ---- Actualizar estado (Meta / verbose / related_names / help_texts) ----
        migrations.AlterModelOptions(
            name='conjuntodatos',
            options={'verbose_name': 'Conjunto de Datos', 'verbose_name_plural': 'Conjuntos de Datos'},
        ),
        migrations.AlterModelOptions(
            name='variableconjuntodatos',
            options={
                'ordering': ['conjunto_datos', 'orden', 'codigo_variable'],
                'verbose_name': 'Variable de Conjunto de Datos',
                'verbose_name_plural': 'Variables de Conjuntos de Datos',
            },
        ),
        migrations.AlterModelOptions(
            name='cargaconjuntodatos',
            options={
                'ordering': ['-fecha_carga'],
                'verbose_name': 'Carga de Conjunto de Datos',
                'verbose_name_plural': 'Cargas de Conjuntos de Datos',
            },
        ),
        migrations.AlterUniqueTogether(
            name='variableconjuntodatos',
            unique_together={('conjunto_datos', 'codigo_variable')},
        ),
        # related_names que cambiaron
        migrations.AlterField(
            model_name='conjuntodatos',
            name='operacion',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name='conjuntos_datos', to='indicadores.operacionestadistica'),
        ),
        migrations.AlterField(
            model_name='cargaconjuntodatos',
            name='usuario',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                    related_name='cargas_conjuntos_datos', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='cargaconjuntodatos',
            name='validado_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='conjuntos_datos_validados', to=settings.AUTH_USER_MODEL,
                                    help_text='Validador que aprobó o rechazó esta carga'),
        ),
        migrations.AlterField(
            model_name='indicador',
            name='nombre_conjunto_datos',
            field=models.CharField(
                blank=True, max_length=255, null=True,
                help_text='Nombre del conjunto de datos al que pertenecen las variables. '
                          'Si coincide con un conjunto de datos existente, se asocia automáticamente. '
                          'No aparece en la ficha técnica pública.',
                verbose_name='Nombre del conjunto de datos'),
        ),
        migrations.AlterField(
            model_name='seccionpaper',
            name='conjunto_datos_vinculado',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    help_text='Conjunto de datos a mostrar en tabla de muestra (solo para bloques de tabla_microdata)',
                                    to='indicadores.conjuntodatos'),
        ),
        migrations.AlterField(
            model_name='seccioneducativa',
            name='conjunto_datos_vinculado',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    help_text='Conjunto de datos a explorar (para laboratorio de datos)',
                                    to='indicadores.conjuntodatos'),
        ),
        migrations.AlterField(
            model_name='productoacademico',
            name='conjunto_datos_principal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    help_text='Conjunto de datos principal de referencia (ej: población proyectada Cali 2042)',
                                    to='indicadores.conjuntodatos'),
        ),
    ]
