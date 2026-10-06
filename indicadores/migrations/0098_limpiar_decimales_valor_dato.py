# Migración de datos: limpia artefactos float en indicadores_dato.valor_dato
#
# La columna real en producción es `numeric` ilimitado (sin escala), aunque el
# modelo declara DecimalField(max_digits=20, decimal_places=6). Los cargadores
# que pasan float() guardaron literales binarios tipo 52.299999999999997158,
# que el admin rechaza al editar ("no más de 6 decimales") bloqueando el
# guardado del indicador.
#
# round(v,6) elimina el artefacto; trim_scale() quita ceros de relleno
# (2.500000 -> 2.5) para que el admin muestre el valor corto.
# NaN/Infinity quedan intactos (la comparación <> devuelve NULL para ellos).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0097_alter_noticiabanner_fecha_publicacion'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                UPDATE indicadores_dato
                SET valor_dato = trim_scale(round(valor_dato, 6))
                WHERE valor_dato IS NOT NULL
                  AND trim_scale(round(valor_dato, 6)) <> valor_dato;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
