"""Helpers del catálogo de bases del Data Lake.

Reemplaza el antiguo `catalogo_data.py` hardcodeado del taller: ahora las
bases y sus campos viven en BD (`BaseCatalogo`/`CampoCatalogo`). Expone las
mismas firmas `get_bases()` / `get_campos_cruzables()` que usaban las vistas
y plantillas portadas, devolviendo dicts con la forma original.
"""

from .models_catalogo import BaseCatalogo


def _campo_dict(c):
    return {
        'nombre': c.nombre,
        'tipo': c.tipo,
        'descripcion': c.descripcion,
        'cruzar': c.es_llave_cruce,
        'sensible': c.sensibilidad or '',
        'categoria': c.categoria or '',
    }


def get_bases():
    """Bases activas del catálogo como lista de dicts (forma de BASES original)."""
    bases = []
    for b in BaseCatalogo.objects.filter(activa=True).prefetch_related('campos'):
        bases.append({
            'id': b.slug,
            'nombre': b.nombre,
            'descripcion': b.descripcion,
            'organismo': b.get_organismo_display(),
            'organismo_id': b.organismo_id,
            'frecuencia': b.frecuencia,
            'cobertura': b.cobertura,
            'campos': [_campo_dict(c) for c in b.campos.all()],
        })
    return bases


def get_campos_cruzables():
    """Dict campo → lista de bases que lo tienen (solo si aparece en >1 base).
    Matching case-insensitive (igual que la versión original)."""
    resultado = {}
    for base in get_bases():
        for campo in base['campos']:
            if campo['cruzar']:
                key = campo['nombre'].lower()
                resultado.setdefault(key, []).append(base['id'])
    return {k: v for k, v in resultado.items() if len(v) > 1}
