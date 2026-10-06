"""
Migration to convert json columns to jsonb in ICEDRespuesta.

Root cause fix: Django 4.2's JSONField expects PostgreSQL 'jsonb' type.
The columns were created as 'json' type, causing psycopg2 to auto-deserialize
values to Python objects. Then Django's from_db_value() tries json.loads()
on already-deserialized objects → TypeError.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0073_alter_equipoorganismo_options_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                'ALTER TABLE indicadores_icedrespuesta ALTER COLUMN respuesta_opciones_multiples TYPE jsonb USING respuesta_opciones_multiples::jsonb;',
                'ALTER TABLE indicadores_icedrespuesta ALTER COLUMN respuesta_tabla TYPE jsonb USING respuesta_tabla::jsonb;',
            ],
            reverse_sql=[
                'ALTER TABLE indicadores_icedrespuesta ALTER COLUMN respuesta_opciones_multiples TYPE json USING respuesta_opciones_multiples::json;',
                'ALTER TABLE indicadores_icedrespuesta ALTER COLUMN respuesta_tabla TYPE json USING respuesta_tabla::json;',
            ],
        ),
    ]
