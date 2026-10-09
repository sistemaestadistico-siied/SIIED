# Migración: campos de organismo en metadatos pasan a llave foránea
# - Indicador.entidad_responsable (CharField) -> entidad_responsable_legado;
#   el campo oficial queda siendo organismo_responsable (FK ya existente).
# - ConjuntoDatos.productor -> productor_legado + nuevo FK organismo_productor.
# - VariableConjuntoDatos.organismo_productor -> organismo_productor_legado
#   + nuevo FK organismo_productor.

import unicodedata
from django.db import migrations, models
import django.db.models.deletion


def _norm(texto):
    return unicodedata.normalize('NFKD', texto or '').encode(
        'ascii', 'ignore').decode().strip().lower()


def _resolver_organismo(Organismo, nombre):
    """Réplica de resolver_organismo_por_nombre usando modelos históricos."""
    texto = (nombre or '').strip()
    if not texto:
        return None
    qs = Organismo.objects.filter(activo=True)
    org = qs.filter(nombre__iexact=texto).first()
    if not org:
        objetivo = _norm(texto)
        for o in qs:
            if _norm(o.nombre) == objetivo:
                org = o
                break
    if not org:
        org = qs.filter(nombre__icontains=texto[:60]).first()
    if not org:
        # Coincidencia inversa: nombre del organismo contenido en el
        # texto (solo nombres >= 10 chars para evitar falsos positivos)
        objetivo = _norm(texto)
        mejor = None
        for o in qs:
            n = _norm(o.nombre)
            if len(n) >= 10 and n in objetivo and (
                    mejor is None or len(n) > len(_norm(mejor.nombre))):
                mejor = o
        org = mejor
    return org


def resolver_organismos(apps, schema_editor):
    Organismo = apps.get_model('indicadores', 'Organismo')
    Indicador = apps.get_model('indicadores', 'Indicador')
    ConjuntoDatos = apps.get_model('indicadores', 'ConjuntoDatos')
    VariableConjuntoDatos = apps.get_model('indicadores', 'VariableConjuntoDatos')

    # Indicador: completar organismo_responsable desde el texto legado
    for ind in Indicador.objects.filter(
            organismo_responsable__isnull=True,
    ).exclude(entidad_responsable_legado__isnull=True).exclude(
            entidad_responsable_legado=''):
        org = _resolver_organismo(Organismo, ind.entidad_responsable_legado)
        if org:
            ind.organismo_responsable = org
            ind.save(update_fields=['organismo_responsable'])

    # ConjuntoDatos: productor_legado -> organismo_productor
    for cd in ConjuntoDatos.objects.filter(
            organismo_productor__isnull=True,
    ).exclude(productor_legado__isnull=True).exclude(productor_legado=''):
        org = _resolver_organismo(Organismo, cd.productor_legado)
        if org:
            cd.organismo_productor = org
            cd.save(update_fields=['organismo_productor'])

    # VariableConjuntoDatos: organismo_productor_legado -> organismo_productor
    for var in VariableConjuntoDatos.objects.filter(
            organismo_productor__isnull=True,
    ).exclude(organismo_productor_legado__isnull=True).exclude(
            organismo_productor_legado=''):
        org = _resolver_organismo(Organismo, var.organismo_productor_legado)
        if org:
            var.organismo_productor = org
            var.save(update_fields=['organismo_productor'])


def noop_reverse(apps, schema_editor):
    # Reversible hacia atrás solo a nivel de esquema; los textos legados
    # permanecen y los FK se pierden con la reversa del AddField.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores',
         '0108_basecatalogo_campocatalogo_evaluacionseguridad_and_more'),
    ]

    operations = [
        # ---- Indicador ----
        migrations.RenameField(
            model_name='indicador',
            old_name='entidad_responsable',
            new_name='entidad_responsable_legado',
        ),
        migrations.AlterField(
            model_name='indicador',
            name='entidad_responsable_legado',
            field=models.CharField(
                blank=True, max_length=255, null=True,
                verbose_name='1.1 Entidad Responsable (texto legado)',
                help_text="Texto libre heredado. El campo oficial es la llave "
                          "'organismo_responsable'. Este texto se conserva solo "
                          "como referencia cuando no pudo resolverse a un Organismo."),
        ),
        migrations.AlterField(
            model_name='indicador',
            name='organismo_responsable',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='indicadores_responsables',
                to='indicadores.organismo',
                verbose_name='1.1 Entidad u Organismo Responsable',
                help_text="Organismo productor del indicador. Llave a la tabla "
                          "Organismo (usado también para el portal de delegados). "
                          "Los textos antiguos quedaron en 'entidad_responsable_legado'."),
        ),
        # ---- ConjuntoDatos ----
        migrations.RenameField(
            model_name='conjuntodatos',
            old_name='productor',
            new_name='productor_legado',
        ),
        migrations.AddField(
            model_name='conjuntodatos',
            name='organismo_productor',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='conjuntos_producidos',
                to='indicadores.organismo',
                verbose_name='Organismo productor',
                help_text='DDI producer — Llave a la tabla Organismo'),
        ),
        # ---- VariableConjuntoDatos ----
        migrations.RenameField(
            model_name='variableconjuntodatos',
            old_name='organismo_productor',
            new_name='organismo_productor_legado',
        ),
        migrations.AddField(
            model_name='variableconjuntodatos',
            name='organismo_productor',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='variables_producidas',
                to='indicadores.organismo',
                verbose_name='Organismo productor',
                help_text='Llave a la tabla Organismo'),
        ),
        # ---- Data migration ----
        migrations.RunPython(resolver_organismos, noop_reverse),
    ]
