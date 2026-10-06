# -*- coding: utf-8 -*-
"""
Migración de datos: campos legacy → campos estándar MSD (DANE).

Mapeo aplicado (solo cuando el destino está vacío, para no pisar datos):
    definiciones_conceptos        → descripcion_indicador      (2.2)
    desagregacion_tematica_texto  → alcance_tematico           (2.8)
    desagregacion_geografica_texto → cobertura_geografica      (2.10)
    periodicidad                  → frecuencia_difusion        (3.2)
    fecha_actualizacion           → fecha_publicacion_metadatos (1.5)
    responsable / entidad_recopiladora → entidad_responsable   (1.1)

Campos huérfanos (sin equivalente MSD) se concatenan dentro de
comentarios_adicionales (4 MSD) conservando su contenido:
    observaciones, justificacion, valores_referencia, linea_base,
    entidad_recopiladora (si difiere de responsable), fecha_elaboracion

La reversa restaura los campos principales desde sus destinos MSD;
el contenido volcado en comentarios_adicionales NO se desarma (se
documenta en la reversa como pérdida de estructura aceptable).
"""
from django.db import migrations


def _v(valor):
    """Normaliza: None/''/solo espacios → cadena vacía."""
    if valor is None:
        return ''
    return str(valor).strip()


def _anexar(base, titulo, contenido):
    """Anexa contenido a un bloque HTML de comentarios con encabezado."""
    contenido = _v(contenido)
    if not contenido:
        return base
    bloque = f"<p><strong>{titulo}:</strong> {contenido}</p>"
    return (base or '') + bloque


def migrar_a_msd(apps, schema_editor):
    Indicador = apps.get_model('indicadores', 'Indicador')
    migrados = 0
    for ind in Indicador.objects.all().iterator():
        dirty = False

        # --- Reemplazos directos (solo si destino vacío) ---
        pares = [
            ('definiciones_conceptos', 'descripcion_indicador'),
            ('desagregacion_tematica_texto', 'alcance_tematico'),
            ('desagregacion_geografica_texto', 'cobertura_geografica'),
            ('periodicidad', 'frecuencia_difusion'),
        ]
        for viejo, nuevo in pares:
            if _v(getattr(ind, nuevo)) == '' and _v(getattr(ind, viejo)):
                setattr(ind, nuevo, getattr(ind, viejo))
                dirty = True

        # Fechas
        if ind.fecha_publicacion_metadatos is None and ind.fecha_actualizacion:
            ind.fecha_publicacion_metadatos = ind.fecha_actualizacion
            dirty = True

        # 1.1 Entidad responsable: prioriza 'responsable', fallback entidad_recopiladora
        if _v(ind.entidad_responsable) == '':
            candidato = _v(ind.responsable) or _v(ind.entidad_recopiladora)
            if candidato:
                ind.entidad_responsable = candidato[:255]
                dirty = True

        # --- Huérfanos → comentarios_adicionales ---
        comentarios = ind.comentarios_adicionales or ''
        if _v(ind.observaciones):
            comentarios = _anexar(comentarios, 'Observaciones', ind.observaciones)
        if _v(ind.justificacion):
            comentarios = _anexar(comentarios, 'Justificación', ind.justificacion)
        if _v(ind.valores_referencia):
            comentarios = _anexar(comentarios, 'Valores de referencia', ind.valores_referencia)
        if _v(ind.linea_base):
            comentarios = _anexar(comentarios, 'Línea base', ind.linea_base)
        # entidad_recopiladora solo si aporta algo distinto a lo ya migrado
        if _v(ind.entidad_recopiladora) and _v(ind.entidad_recopiladora) != _v(ind.responsable):
            comentarios = _anexar(comentarios, 'Entidad recopiladora', ind.entidad_recopiladora)
        if ind.fecha_elaboracion:
            comentarios = _anexar(
                comentarios, 'Fecha de elaboración de la ficha',
                ind.fecha_elaboracion.isoformat())

        if comentarios != (ind.comentarios_adicionales or ''):
            ind.comentarios_adicionales = comentarios
            dirty = True

        if dirty:
            ind.save()
            migrados += 1

    print(f'\n  → {migrados} indicadores migrados a campos MSD.')


def revertir(apps, schema_editor):
    """Restaura los campos legacy desde sus destinos MSD (si el legacy está vacío)."""
    Indicador = apps.get_model('indicadores', 'Indicador')
    for ind in Indicador.objects.all().iterator():
        dirty = False
        pares = [
            ('descripcion_indicador', 'definiciones_conceptos'),
            ('alcance_tematico', 'desagregacion_tematica_texto'),
            ('cobertura_geografica', 'desagregacion_geografica_texto'),
            ('frecuencia_difusion', 'periodicidad'),
            ('entidad_responsable', 'responsable'),
        ]
        for nuevo, viejo in pares:
            if _v(getattr(ind, viejo)) == '' and _v(getattr(ind, nuevo)):
                setattr(ind, viejo, getattr(ind, nuevo))
                dirty = True
        if ind.fecha_actualizacion is None and ind.fecha_publicacion_metadatos:
            ind.fecha_actualizacion = ind.fecha_publicacion_metadatos
            dirty = True
        if dirty:
            ind.save()


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0101_campo_entidad_responsable_msd'),
    ]

    operations = [
        migrations.RunPython(migrar_a_msd, revertir),
    ]
