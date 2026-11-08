"""Reorganiza los sistemas de consulta (/sistemas-informacion/) en la nueva
taxonomía de 8 categorías.

- Crea/actualiza las 8 categorías nuevas con su ícono y orden.
- Reasigna los sistemas existentes por reglas de coincidencia sobre el
  nombre (normalizado: minúsculas, sin tildes). Primer match gana.
- Los sistemas que no coincidan con ninguna regla permanecen en su
  categoría actual (no se pierde nada visible).
- Desactiva las categorías antiguas SOLO si quedaron sin sistemas
  activos; si en prod hay ítems sin regla, su categoría sigue visible.
- El template oculta categorías vacías, así que las nuevas vacías
  (Geovisores, Observatorios…) no muestran "Sin ítems".
"""

import unicodedata

from django.db import migrations


def _norm(s):
    return ''.join(
        c for c in unicodedata.normalize('NFD', s or '')
        if unicodedata.category(c) != 'Mn'
    ).lower()


NUEVAS = [
    # (slug, nombre, icono, orden)
    ('sistemas-y-aplicaciones', 'Sistemas y Aplicaciones', 'fas fa-gears', 1),
    ('portales-de-datos-abiertos', 'Portales de Datos Abiertos', 'fas fa-chart-line', 2),
    ('geovisores-y-cartografia', 'Geovisores y Cartografía', 'fas fa-map-location-dot', 3),
    ('bases-de-datos-y-acervo', 'Bases de Datos y Acervo digital', 'fas fa-database', 4),
    ('analitica-avanzada', 'Analítica avanzada', 'fas fa-brain', 5),
    ('para-desarrolladores', 'Para desarrolladores', 'fas fa-code', 6),
    ('observatorios-academicos', 'Observatorios Académicos e Institucionales', 'fas fa-building-columns', 7),
    ('observatorios-publicos', 'Observatorios Públicos Distritales', 'fas fa-eye', 8),
]

# Reglas ordenadas: primer substring (normalizado) contenido en el nombre
# del sistema decide su categoría destino.
REGLAS = [
    # Analítica avanzada (antes: 'don datico bi' contiene 'datico')
    ('don datico bi', 'analitica-avanzada'),
    ('siied bi', 'analitica-avanzada'),
    ('visor comparativo', 'analitica-avanzada'),
    ('consulta y tableros', 'analitica-avanzada'),
    ('libro digital', 'analitica-avanzada'),
    ('microdata', 'analitica-avanzada'),
    # Portales de Datos Abiertos
    ('explorador de conjuntos', 'portales-de-datos-abiertos'),
    ('datos abiertos', 'portales-de-datos-abiertos'),
    # Geovisores y Cartografía
    ('geovisor', 'geovisores-y-cartografia'),
    ('mapa interactivo', 'geovisores-y-cartografia'),
    ('datos espaciales', 'geovisores-y-cartografia'),
    ('cartografia', 'geovisores-y-cartografia'),
    # Bases de Datos y Acervo digital
    ('catalogo de variables', 'bases-de-datos-y-acervo'),
    ('base de datos', 'bases-de-datos-y-acervo'),
    ('estadisticas vitales', 'bases-de-datos-y-acervo'),
    ('cali en cifras', 'bases-de-datos-y-acervo'),
    ('archivo distrital', 'bases-de-datos-y-acervo'),
    # Para desarrolladores
    ('api', 'para-desarrolladores'),
    ('documentacion', 'para-desarrolladores'),
    ('codigo abierto', 'para-desarrolladores'),
    ('codigo fuente', 'para-desarrolladores'),
    ('servidor mcp', 'para-desarrolladores'),
    ('mcp', 'para-desarrolladores'),
    # Observatorios
    ('observatorio', 'observatorios-publicos'),
    ('cidse', 'observatorios-academicos'),
    ('cienfi', 'observatorios-academicos'),
    ('cinara', 'observatorios-academicos'),
    ('cisalva', 'observatorios-academicos'),
    # Sistemas y Aplicaciones (genéricas al final)
    ('datico', 'sistemas-y-aplicaciones'),
    ('inventario de operaciones', 'sistemas-y-aplicaciones'),
    ('capacidad estadistica', 'sistemas-y-aplicaciones'),
    ('iced', 'sistemas-y-aplicaciones'),
    ('hoja de vida', 'sistemas-y-aplicaciones'),
    ('taller', 'sistemas-y-aplicaciones'),
    ('satisfaccion', 'sistemas-y-aplicaciones'),
    ('calendario', 'sistemas-y-aplicaciones'),
    ('indicadores ods', 'sistemas-y-aplicaciones'),
    ('saul', 'sistemas-y-aplicaciones'),
]

# Categorías previas a esta reorganización (por slug o nombre normalizado)
VIEJAS = {
    'herramientas-de-consulta', 'instrumentos-del-sistema',
    'conectividad-y-acceso-abierto',
    'herramientas de consulta', 'instrumentos del sistema',
    'conectividad y acceso abierto',
}

NUEVOS_SLUGS = {slug for slug, *_ in NUEVAS}


def _destino(nombre):
    n = _norm(nombre)
    for regla, slug in REGLAS:
        if regla in n:
            return slug
    return None


def reorganizar(apps, schema_editor):
    Cat = apps.get_model('indicadores', 'CategoriaInformacion')
    Sis = apps.get_model('indicadores', 'SistemaInformacion')

    cats = {}
    for slug, nombre, icono, orden in NUEVAS:
        cat, _ = Cat.objects.get_or_create(slug=slug, defaults={'nombre': nombre})
        cat.nombre = nombre
        cat.icono = icono
        cat.orden = orden
        cat.activo = True
        cat.save(update_fields=['nombre', 'icono', 'orden', 'activo'])
        cats[slug] = cat

    orden_por_cat = {slug: 0 for slug in NUEVOS_SLUGS}
    for sis in Sis.objects.select_related('categoria'):
        slug = _destino(sis.nombre)
        if slug and sis.categoria_id != cats[slug].id:
            sis.categoria = cats[slug]
            orden_por_cat[slug] += 1
            sis.orden = orden_por_cat[slug]
            sis.save(update_fields=['categoria', 'orden'])

    # Desactivar categorías antiguas únicamente si quedaron vacías de
    # sistemas activos (no aplica a las nuevas aunque estén vacías).
    for cat in Cat.objects.exclude(slug__in=NUEVOS_SLUGS):
        if _norm(cat.slug) in VIEJAS or _norm(cat.nombre) in VIEJAS:
            if not cat.sistemas.filter(activo=True).exists() and cat.activo:
                cat.activo = False
                cat.save(update_fields=['activo'])


def revertir(apps, schema_editor):
    Cat = apps.get_model('indicadores', 'CategoriaInformacion')
    # Best-effort: reactivar las antiguas y desactivar las nuevas vacías.
    # La pertenencia de sistemas no se restaura (no es posible saber el
    # estado previo sin histórico); re-ejecutar la reorganización manual
    # desde Editorial corrige cualquier caso.
    for cat in Cat.objects.all():
        if _norm(cat.slug) in VIEJAS or _norm(cat.nombre) in VIEJAS:
            if not cat.activo:
                cat.activo = True
                cat.save(update_fields=['activo'])


class Migration(migrations.Migration):

    dependencies = [
        ('indicadores', '0136_conexionbi'),
    ]

    operations = [
        migrations.RunPython(reorganizar, revertir),
    ]
