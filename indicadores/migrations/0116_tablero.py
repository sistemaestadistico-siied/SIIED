# Generated manually — Laboratorio de Datos Don Datico
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0115_dominiodesagregacion_en_catalogo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Tablero',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=300)),
                ('descripcion', models.TextField(blank=True, default='')),
                ('consulta_original', models.TextField(blank=True, default='', help_text='Peticion en lenguaje natural que genero el tablero')),
                ('spec', models.JSONField(default=dict, help_text='Spec declarativa del tablero: lista de tiles con fuente, dimension, medida, agregacion y filtros')),
                ('estado', models.CharField(choices=[('borrador', 'Borrador'), ('publicado', 'Publicado')], default='borrador', max_length=20)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('autor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tableros', to=settings.AUTH_USER_MODEL)),
                ('organismo', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tableros', to='indicadores.organismo')),
            ],
            options={
                'verbose_name': 'Tablero',
                'verbose_name_plural': 'Tableros (Laboratorio Don Datico)',
                'ordering': ['-fecha_actualizacion'],
            },
        ),
    ]
