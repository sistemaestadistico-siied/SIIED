# Generated manually per project convention (migrations written by hand).
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('indicadores', '0145_perfil_unicidad_validador_delegado'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AccionGestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('modulo', models.CharField(choices=[('gestion', 'Gestión (general)'), ('ficed', 'FICED'), ('taller', 'Taller de Gestión de Datos'), ('encuestas', 'Encuestas')], db_index=True, max_length=15)),
                ('accion', models.CharField(db_index=True, help_text='Verbo de la acción: crear_usuario, desactivar, enviar_correo, reiniciar_formulario, prorroga…', max_length=60)),
                ('objeto_tipo', models.CharField(blank=True, default='', help_text='Nombre del modelo afectado (p. ej. PerfilRecolector)', max_length=60)),
                ('objeto_id', models.CharField(blank=True, default='', help_text='Identificador del objeto afectado (texto para admitir uuid)', max_length=60)),
                ('antes', models.JSONField(blank=True, help_text='Estado previo (copia completa en acciones destructivas)', null=True)),
                ('despues', models.JSONField(blank=True, help_text='Estado posterior o detalle del resultado', null=True)),
                ('motivo', models.TextField(blank=True, default='', help_text='Obligatorio en acciones destructivas')),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('usuario', models.ForeignKey(blank=True, help_text='Quien ejecutó la acción', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acciones_gestion', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Acción de gestión',
                'verbose_name_plural': 'Bitácora de gestión',
                'ordering': ['-fecha'],
            },
        ),
        migrations.CreateModel(
            name='VentanaDiligenciamiento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('modulo', models.CharField(choices=[('gestion', 'Gestión (general)'), ('ficed', 'FICED'), ('taller', 'Taller de Gestión de Datos'), ('encuestas', 'Encuestas')], max_length=15)),
                ('referencia', models.CharField(help_text='Periodo FICED, edición del taller o id de formulario', max_length=40)),
                ('fecha_apertura', models.DateField()),
                ('fecha_cierre', models.DateField(help_text='Último día de diligenciamiento (inclusive)')),
                ('activa', models.BooleanField(default=True, help_text='Permite suspender la ventana sin borrarla')),
                ('mensaje_cerrado', models.TextField(blank=True, default='', help_text='Texto que se muestra cuando la ventana está cerrada. Vacío = mensaje predeterminado')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Ventana de diligenciamiento',
                'verbose_name_plural': 'Ventanas de diligenciamiento',
                'ordering': ['-fecha_cierre'],
            },
        ),
        migrations.CreateModel(
            name='ProrrogaVentana',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_cierre_extendida', models.DateField(help_text='Nuevo último día para este organismo (inclusive)')),
                ('motivo', models.TextField()),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('creado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('organismo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prorrogas', to='indicadores.organismo')),
                ('ventana', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prorrogas', to='gestion.ventanadiligenciamiento')),
            ],
            options={
                'verbose_name': 'Prórroga de ventana',
                'verbose_name_plural': 'Prórrogas de ventanas',
                'ordering': ['-fecha_cierre_extendida'],
            },
        ),
        migrations.AddIndex(
            model_name='acciongestion',
            index=models.Index(fields=('modulo', 'accion'), name='gestion_acc_modulo_ebebf6_idx'),
        ),
        migrations.AddIndex(
            model_name='acciongestion',
            index=models.Index(fields=('objeto_tipo', 'objeto_id'), name='gestion_acc_objeto__8c3381_idx'),
        ),
        migrations.AddConstraint(
            model_name='ventanadiligenciamiento',
            constraint=models.UniqueConstraint(fields=('modulo', 'referencia'), name='uniq_ventana_modulo_referencia'),
        ),
        migrations.AddConstraint(
            model_name='prorrogaventana',
            constraint=models.UniqueConstraint(fields=('ventana', 'organismo'), name='uniq_prorroga_ventana_organismo'),
        ),
    ]
