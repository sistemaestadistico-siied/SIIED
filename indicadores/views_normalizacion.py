"""Wizard de Normalización de Desagregaciones — solo admin (is_staff).

Dos operaciones sobre indicadores_dominiodesagregacion:

- CONCILIAR  N dominios → 1: verificación manual de equivalencias entre
  desagregaciones para que el redireccionamiento de referencias sea acertado.
- ELIMINAR   1 dominio + sus desagregaciones SIN borrar los Dato relacionados:
  solo se cortan las etiquetas M2M (datos, series, predeterminadas) y los FKs
  legacy quedan en NULL. Los Dato permanecen, sin esa dimensión.

Estado entre pasos: parámetros POST (sin sesión). Todo se ejecuta en
transaction.atomic() y se audita en audit_conciliacion_log.
"""

import json
import unicodedata

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection, transaction
from django.shortcuts import redirect, render

from .models import DominioDesagregacion, Desagregacion


def _normaliza(s):
    """Normalización para match automático: sin tildes, minúsculas, espacios
    colapsados, sin puntuación."""
    if not s:
        return ''
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = ''.join(ch if ch.isalnum() else ' ' for ch in s)
    return ' '.join(s.split())


def _desag_refs_count(cur, desag_ids):
    """Conteos de referencias por desagregación: datos (tem+geo), series M2M,
    series FK legacy, predeterminadas (tem+geo), hijas."""
    if not desag_ids:
        return {}
    ids = tuple(desag_ids)
    refs = {i: {'datos': 0, 'series': 0, 'fks': 0, 'pred': 0, 'hijas': 0} for i in desag_ids}
    cur.execute(f"""
        SELECT d.id, d.datos + COALESCE(d.datos_g,0), d.series, d.fks, d.pred + COALESCE(d.pred_g,0), d.hijas FROM (
            SELECT ds.id,
              (SELECT count(*) FROM indicadores_dato_desagregaciones_tematicas x WHERE x.desagregacion_id=ds.id) AS datos,
              (SELECT count(*) FROM indicadores_dato_desagregaciones_geograficas x WHERE x.desagregacion_id=ds.id) AS datos_g,
              (SELECT count(*) FROM indicadores_graficoserie_desagregaciones x WHERE x.desagregacion_id=ds.id) AS series,
              (SELECT count(*) FROM indicadores_graficoserie x WHERE x.desagregacion_tematica_id=ds.id OR x.desagregacion_geografica_id=ds.id) AS fks,
              (SELECT count(*) FROM indicadores_grafico_desagregaciones_tematicas_predeterminadas x WHERE x.desagregacion_id=ds.id) AS pred,
              (SELECT count(*) FROM indicadores_grafico_desagregaciones_geograficas_predeterminadas x WHERE x.desagregacion_id=ds.id) AS pred_g,
              (SELECT count(*) FROM indicadores_desagregacion h WHERE h.desagregacion_padre_id=ds.id) AS hijas
            FROM indicadores_desagregacion ds WHERE ds.id IN %s
        ) d
    """, [ids])
    for rid, datos, series, fks, pred, hijas in cur.fetchall():
        refs[rid] = {'datos': datos, 'series': series, 'fks': fks, 'pred': pred, 'hijas': hijas}
    return refs


def _dominio_stats(cur, dom_id):
    cur.execute("""
        SELECT
          (SELECT count(*) FROM indicadores_desagregacion WHERE dominio_id=%s),
          (SELECT count(*) FROM indicadores_indicador_dominios_desagregacion_tematica WHERE dominiodesagregacion_id=%s)
        + (SELECT count(*) FROM indicadores_indicador_dominios_desagregacion_geografica WHERE dominiodesagregacion_id=%s),
          (SELECT count(*) FROM indicadores_desagregacion WHERE dominio_id=%s AND capa_geo_id IS NOT NULL),
          (SELECT count(*) FROM indicadores_catalogodominio WHERE dominio_id=%s)
    """, [dom_id, dom_id, dom_id, dom_id, dom_id])
    n_desags, n_links, n_capa, n_cat = cur.fetchone()
    cur.execute("""
        SELECT i.id, i.nombre FROM indicadores_indicador i WHERE i.id IN (
          SELECT indicador_id FROM indicadores_indicador_dominios_desagregacion_tematica WHERE dominiodesagregacion_id=%s
          UNION
          SELECT indicador_id FROM indicadores_indicador_dominios_desagregacion_geografica WHERE dominiodesagregacion_id=%s
        ) ORDER BY i.id LIMIT 12
    """, [dom_id, dom_id])
    indicadores = cur.fetchall()
    return {'n_desags': n_desags, 'n_links': n_links, 'n_capa': n_capa,
            'n_catalogos': n_cat, 'indicadores': indicadores}


def _repuntar_desag(cur, src_id, dst_id):
    """Redirige todas las referencias de src→dst con dedup (para equivalencias).
    Las filas M2M conflictivas ya existentes se borran en origen."""
    # datos: insertar en tabla del lado correcto del dst, dedup, borrar origen
    for tabla in ('indicadores_dato_desagregaciones_tematicas',
                  'indicadores_dato_desagregaciones_geograficas'):
        cur.execute(f"""
            INSERT INTO {tabla} (dato_id, desagregacion_id)
            SELECT dato_id, %s FROM {tabla} WHERE desagregacion_id = %s
            ON CONFLICT DO NOTHING;
            DELETE FROM {tabla} WHERE desagregacion_id = %s;
        """, [dst_id, src_id, src_id])
    # series M2M
    cur.execute("""
        INSERT INTO indicadores_graficoserie_desagregaciones (graficoserie_id, desagregacion_id)
        SELECT graficoserie_id, %s FROM indicadores_graficoserie_desagregaciones WHERE desagregacion_id=%s
        ON CONFLICT DO NOTHING;
        DELETE FROM indicadores_graficoserie_desagregaciones WHERE desagregacion_id=%s;
    """, [dst_id, src_id, src_id])
    # FKs legacy (ambos lados: el tipo del dominio dst manda al resincronizar)
    cur.execute("""
        UPDATE indicadores_graficoserie SET desagregacion_tematica_id=%s WHERE desagregacion_tematica_id=%s;
        UPDATE indicadores_graficoserie SET desagregacion_geografica_id=%s WHERE desagregacion_geografica_id=%s;
    """, [dst_id, src_id, dst_id, src_id])
    # predeterminadas
    for tabla in ('indicadores_grafico_desagregaciones_tematicas_predeterminadas',
                  'indicadores_grafico_desagregaciones_geograficas_predeterminadas'):
        cur.execute(f"""
            INSERT INTO {tabla} (grafico_id, desagregacion_id)
            SELECT grafico_id, %s FROM {tabla} WHERE desagregacion_id=%s
            ON CONFLICT DO NOTHING;
            DELETE FROM {tabla} WHERE desagregacion_id=%s;
        """, [dst_id, src_id, src_id])
    # hijas (padre jerárquico)
    cur.execute("""
        UPDATE indicadores_desagregacion SET desagregacion_padre_id=%s
        WHERE desagregacion_padre_id=%s;
    """, [dst_id, src_id])
    # capa_geo: si el origen tenía y el destino no, transferir
    cur.execute("""
        UPDATE indicadores_desagregacion dst SET capa_geo_id = src.capa_geo_id
        FROM indicadores_desagregacion src
        WHERE dst.id=%s AND src.id=%s AND src.capa_geo_id IS NOT NULL AND dst.capa_geo_id IS NULL;
    """, [dst_id, src_id])


def _borrar_refs_desag(cur, desag_ids):
    """Corta TODAS las referencias de un conjunto de desags sin borrar los Dato."""
    if not desag_ids:
        return
    ids = tuple(desag_ids)
    for tabla, col in [
        ('indicadores_dato_desagregaciones_tematicas', 'desagregacion_id'),
        ('indicadores_dato_desagregaciones_geograficas', 'desagregacion_id'),
        ('indicadores_graficoserie_desagregaciones', 'desagregacion_id'),
        ('indicadores_grafico_desagregaciones_tematicas_predeterminadas', 'desagregacion_id'),
        ('indicadores_grafico_desagregaciones_geograficas_predeterminadas', 'desagregacion_id'),
    ]:
        cur.execute(f"DELETE FROM {tabla} WHERE {col} IN %s", [ids])
    cur.execute("UPDATE indicadores_graficoserie SET desagregacion_tematica_id=NULL WHERE desagregacion_tematica_id IN %s", [ids])
    cur.execute("UPDATE indicadores_graficoserie SET desagregacion_geografica_id=NULL WHERE desagregacion_geografica_id IN %s", [ids])
    cur.execute("UPDATE indicadores_desagregacion SET desagregacion_padre_id=NULL WHERE desagregacion_padre_id IN %s", [ids])


def _mover_links_dominio(cur, src_id, dst_id):
    """Fusiona los vínculos dominio↔indicador de origen en destino (dedup)."""
    for tabla in ('indicadores_indicador_dominios_desagregacion_tematica',
                  'indicadores_indicador_dominios_desagregacion_geografica'):
        cur.execute(f"""
            INSERT INTO {tabla} (indicador_id, dominiodesagregacion_id)
            SELECT indicador_id, %s FROM {tabla} WHERE dominiodesagregacion_id=%s
            ON CONFLICT DO NOTHING;
            DELETE FROM {tabla} WHERE dominiodesagregacion_id=%s;
        """, [dst_id, src_id, src_id])


def _borrar_links_dominio(cur, dom_id):
    for tabla in ('indicadores_indicador_dominios_desagregacion_tematica',
                  'indicadores_indicador_dominios_desagregacion_geografica'):
        cur.execute(f"DELETE FROM {tabla} WHERE dominiodesagregacion_id=%s", [dom_id])


def _resync_fks_legacy(cur):
    """Resincroniza los FKs legacy de TODAS las series desde el M2M
    (primera desag por lado). Idempotente."""
    cur.execute("""
        UPDATE indicadores_graficoserie gs SET desagregacion_tematica_id = sub.desag_id
        FROM (SELECT DISTINCT ON (sdd.graficoserie_id) sdd.graficoserie_id, sdd.desagregacion_id AS desag_id
              FROM indicadores_graficoserie_desagregaciones sdd
              JOIN indicadores_desagregacion ds ON ds.id=sdd.desagregacion_id
              JOIN indicadores_dominiodesagregacion d ON d.id=ds.dominio_id
              WHERE d.tipo='tematica' ORDER BY sdd.graficoserie_id, sdd.desagregacion_id) sub
        WHERE gs.id=sub.graficoserie_id;
        UPDATE indicadores_graficoserie gs SET desagregacion_tematica_id = NULL
        WHERE NOT EXISTS (SELECT 1 FROM indicadores_graficoserie_desagregaciones sdd
          JOIN indicadores_desagregacion ds ON ds.id=sdd.desagregacion_id
          JOIN indicadores_dominiodesagregacion d ON d.id=ds.dominio_id
          WHERE sdd.graficoserie_id=gs.id AND d.tipo='tematica');
        UPDATE indicadores_graficoserie gs SET desagregacion_geografica_id = sub.desag_id
        FROM (SELECT DISTINCT ON (sdd.graficoserie_id) sdd.graficoserie_id, sdd.desagregacion_id AS desag_id
              FROM indicadores_graficoserie_desagregaciones sdd
              JOIN indicadores_desagregacion ds ON ds.id=sdd.desagregacion_id
              JOIN indicadores_dominiodesagregacion d ON d.id=ds.dominio_id
              WHERE d.tipo='geografica' ORDER BY sdd.graficoserie_id, sdd.desagregacion_id) sub
        WHERE gs.id=sub.graficoserie_id;
        UPDATE indicadores_graficoserie gs SET desagregacion_geografica_id = NULL
        WHERE NOT EXISTS (SELECT 1 FROM indicadores_graficoserie_desagregaciones sdd
          JOIN indicadores_desagregacion ds ON ds.id=sdd.desagregacion_id
          JOIN indicadores_dominiodesagregacion d ON d.id=ds.dominio_id
          WHERE sdd.graficoserie_id=gs.id AND d.tipo='geografica');
    """)


def _audit(concepto, tipo, dominios_abs, desags_mov, detalle):
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO audit_conciliacion_log (concepto, tipo, dominios_absorbidos, desags_movidas, detalle)
            VALUES (%s, %s, %s, %s, %s)
        """, [concepto, tipo, dominios_abs, desags_mov, detalle])


# ──────────────────────────────────────────────────────────────────────────
# PASO 1: selección de dominios
# ──────────────────────────────────────────────────────────────────────────

@staff_member_required
def wizard_normalizacion(request):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT d.id, d.nombre, d.tipo,
              (SELECT count(*) FROM indicadores_desagregacion x WHERE x.dominio_id=d.id) AS n_desags,
              (SELECT count(*) FROM indicadores_indicador_dominios_desagregacion_tematica m WHERE m.dominiodesagregacion_id=d.id)
            + (SELECT count(*) FROM indicadores_indicador_dominios_desagregacion_geografica m WHERE m.dominiodesagregacion_id=d.id) AS n_indicadores,
              (SELECT count(*) FROM indicadores_desagregacion x WHERE x.dominio_id=d.id AND x.capa_geo_id IS NOT NULL) AS n_capa,
              (SELECT count(*) FROM indicadores_catalogodominio c WHERE c.dominio_id=d.id) AS n_cat
            FROM indicadores_dominiodesagregacion d ORDER BY d.tipo, d.nombre
        """)
        cols = [c[0] for c in cur.description]
        dominios = [dict(zip(cols, r)) for r in cur.fetchall()]
        # referencias totales por dominio (sumando por desag)
        cur.execute("""
            SELECT ds.dominio_id, count(*) FROM (
              SELECT desagregacion_id FROM indicadores_dato_desagregaciones_tematicas
              UNION ALL SELECT desagregacion_id FROM indicadores_dato_desagregaciones_geograficas
              UNION ALL SELECT desagregacion_id FROM indicadores_graficoserie_desagregaciones
            ) x JOIN indicadores_desagregacion ds ON ds.id=x.desagregacion_id
            GROUP BY ds.dominio_id
        """)
        refs_por_dom = dict(cur.fetchall())
    for d in dominios:
        d['n_refs'] = refs_por_dom.get(d['id'], 0)
    return render(request, 'indicadores/normalizacion/paso1.html', {'dominios': dominios})


# ──────────────────────────────────────────────────────────────────────────
# PASO 2: equivalencias (conciliar) — o redirige a preview (eliminar)
# ──────────────────────────────────────────────────────────────────────────

@staff_member_required
def wizard_equivalencias(request):
    if request.method != 'POST':
        return render(request, 'indicadores/normalizacion/paso1.html',
                      {'error': 'Acceso directo no permitido. Usa el paso 1.',
                       'dominios': []})
    accion = request.POST.get('accion')
    dominio_ids = request.POST.getlist('dominios')

    if accion == 'eliminar':
        return _preview_eliminar(request, dominio_ids)
    if accion != 'conciliar':
        messages.error(request, 'Acción desconocida.')
        return wizard_normalizacion(request)

    destino_id = request.POST.get('destino')
    if not destino_id or len(dominio_ids) < 1:
        messages.error(request, 'Selecciona dominio(s) origen y un destino.')
        return wizard_normalizacion(request)
    destino_id = int(destino_id)
    origenes = [int(d) for d in dominio_ids if int(d) != destino_id]
    if not origenes:
        messages.error(request, 'Los orígenes no pueden incluir el destino.')
        return wizard_normalizacion(request)

    dom = DominioDesagregacion.objects.get(pk=destino_id)
    origenes_dom = DominioDesagregacion.objects.filter(pk__in=origenes)
    for od in origenes_dom:
        if od.tipo != dom.tipo:
            messages.error(request,
                f'Tipo incompatible: "{od.nombre}" es {od.tipo} pero "{dom.nombre}" es {dom.tipo}. '
                'Corrige el tipo antes de conciliar.')
            return wizard_normalizacion(request)

    dst_desags = list(Desagregacion.objects.filter(dominio_id=destino_id).order_by('nombre'))
    dst_norm = {_normaliza(d.nombre): d.id for d in dst_desags}

    filas = []
    with connection.cursor() as cur:
        for od in origenes_dom.order_by('id'):
            desags = list(Desagregacion.objects.filter(dominio_id=od.id).order_by('nombre'))
            ids = [d.id for d in desags]
            refs = _desag_refs_count(cur, ids)
            for d in desags:
                r = refs[d.id]
                filas.append({
                    'dominio_origen': od.id,
                    'dominio_origen_nombre': od.nombre,
                    'desag_id': d.id, 'desag_nombre': d.nombre,
                    'capa_geo': bool(d.capa_geo_id),
                    'refs': r,
                    'sugerido': dst_norm.get(_normaliza(d.nombre)),
                })
    return render(request, 'indicadores/normalizacion/paso2.html', {
        'destino': dom, 'origenes': origenes_dom, 'dst_desags': dst_desags,
        'filas': filas, 'origen_ids': ','.join(str(i) for i in origenes),
    })


# ──────────────────────────────────────────────────────────────────────────
# PASO 3: preview conciliación
# ──────────────────────────────────────────────────────────────────────────

@staff_member_required
def wizard_preview(request):
    if request.method != 'POST':
        return wizard_normalizacion(request)
    accion = request.POST.get('accion')
    if accion == 'eliminar_confirmar':
        return _preview_eliminar(request, request.POST.getlist('dominios'),
                                 confirmado=True)
    if accion != 'aplicar_conciliar':
        return wizard_normalizacion(request)
    destino_id = int(request.POST['destino'])
    origenes = [int(i) for i in request.POST['origen_ids'].split(',') if i]

    # mapping desde el formulario: map_<desag_id> = 'eq_<id>' | 'nuevo' | 'descartar'
    mapping = {}
    for k, v in request.POST.items():
        if k.startswith('map_'):
            mapping[int(k[4:])] = v

    resumen = {'equiv': 0, 'nuevo': 0, 'descartar': 0, 'refs_movidas': 0, 'refs_descartadas': 0}
    detalles = []
    with connection.cursor() as cur:
        refs = _desag_refs_count(cur, list(mapping.keys()))
        for did, decision in mapping.items():
            d = Desagregacion.objects.get(pk=did)
            r = refs[did]
            total = r['datos'] + r['series'] + r['fks'] + r['pred']
            if decision.startswith('eq_'):
                tgt = Desagregacion.objects.get(pk=int(decision[3:]))
                resumen['equiv'] += 1
                resumen['refs_movidas'] += total
                detalles.append(f'{d.nombre} → {tgt.nombre} ({total} refs)')
            elif decision == 'nuevo':
                resumen['nuevo'] += 1
                detalles.append(f'{d.nombre} → [mover tal cual]')
            else:
                resumen['descartar'] += 1
                resumen['refs_descartadas'] += total
                detalles.append(f'{d.nombre} → [descartar, {total} refs se cortan]')

    dom = DominioDesagregacion.objects.get(pk=destino_id)
    origenes_dom = DominioDesagregacion.objects.filter(pk__in=origenes)
    stats_origen = {}
    with connection.cursor() as cur:
        for od in origenes_dom:
            stats_origen[od.id] = _dominio_stats(cur, od.id)
    return render(request, 'indicadores/normalizacion/paso3.html', {
        'destino': dom, 'origenes': origenes_dom, 'resumen': resumen,
        'detalles': detalles, 'stats_origen': stats_origen,
        'payload': json.dumps({k: v for k, v in request.POST.items()
                               if k.startswith('map_')}),
        'origen_ids': request.POST['origen_ids'],
    })


# ──────────────────────────────────────────────────────────────────────────
# PASO 4: aplicar conciliación
# ──────────────────────────────────────────────────────────────────────────

@staff_member_required
def wizard_aplicar(request):
    if request.method != 'POST':
        return wizard_normalizacion(request)
    destino_id = int(request.POST['destino'])
    origenes = [int(i) for i in request.POST['origen_ids'].split(',') if i]
    mapping = {int(k[4:]): v for k, v in json.loads(request.POST['payload']).items()
               if k.startswith('map_') and k[4:].isdigit()}

    stats = {'equiv': 0, 'movidas': 0, 'descartadas': 0, 'dominios': 0}
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                for src_id in origenes:
                    desags = list(Desagregacion.objects.filter(dominio_id=src_id))
                    for d in desags:
                        decision = mapping.get(d.id, 'nuevo')
                        if decision.startswith('eq_'):
                            _repuntar_desag(cur, d.id, int(decision[3:]))
                            cur.execute("DELETE FROM indicadores_desagregacion WHERE id=%s", [d.id])
                            stats['equiv'] += 1
                        elif decision == 'nuevo':
                            cur.execute("UPDATE indicadores_desagregacion SET dominio_id=%s WHERE id=%s",
                                        [destino_id, d.id])
                            stats['movidas'] += 1
                        else:
                            _borrar_refs_desag(cur, [d.id])
                            cur.execute("DELETE FROM indicadores_desagregacion WHERE id=%s", [d.id])
                            stats['descartadas'] += 1
                    _mover_links_dominio(cur, src_id, destino_id)
                    cur.execute("DELETE FROM indicadores_dominiodesagregacion WHERE id=%s", [src_id])
                    stats['dominios'] += 1
                _resync_fks_legacy(cur)
            _audit('wizard', 'conciliacion', stats['dominios'],
                   stats['movidas'] + stats['equiv'],
                   f"→ dominio {destino_id}; equiv={stats['equiv']} movidas={stats['movidas']} descartadas={stats['descartadas']}")
    except Exception as e:
        messages.error(request, f'Error en conciliación (rollback aplicado): {e}')
        return wizard_normalizacion(request)

    messages.success(request,
        f'Conciliación aplicada: {stats["dominios"]} dominio(s) absorbidos, '
        f'{stats["equiv"]} equivalencias, {stats["movidas"]} movidas, '
        f'{stats["descartadas"]} descartadas.')
    return wizard_normalizacion(request)


# ──────────────────────────────────────────────────────────────────────────
# ELIMINAR dominio (sin borrar datos)
# ──────────────────────────────────────────────────────────────────────────

def _preview_eliminar(request, dominio_ids, confirmado=False):
    if len(dominio_ids) != 1:
        messages.error(request, 'La eliminación opera sobre un dominio a la vez.')
        return wizard_normalizacion(request)
    dom_id = int(dominio_ids[0])
    dom = DominioDesagregacion.objects.get(pk=dom_id)
    desags = list(Desagregacion.objects.filter(dominio_id=dom_id).order_by('nombre'))
    with connection.cursor() as cur:
        stats = _dominio_stats(cur, dom_id)
        refs = _desag_refs_count(cur, [d.id for d in desags])
        tot = {k: sum(r[k] for r in refs.values()) for k in ('datos', 'series', 'fks', 'pred', 'hijas')}
        # subdominios que lo tienen como padre
        cur.execute("SELECT id, nombre FROM indicadores_dominiodesagregacion WHERE dominio_padre_id=%s", [dom_id])
        subdominios = cur.fetchall()
    return render(request, 'indicadores/normalizacion/eliminar.html', {
        'dominio': dom, 'desags': desags, 'stats': stats, 'tot': tot,
        'subdominios': subdominios, 'confirmado': confirmado,
    })


@staff_member_required
def wizard_eliminar_aplicar(request):
    if request.method != 'POST' or request.POST.get('confirmar') != 'si':
        messages.error(request, 'Eliminación no confirmada.')
        return wizard_normalizacion(request)
    dom_id = int(request.POST['dominio_id'])
    dom = DominioDesagregacion.objects.get(pk=dom_id)
    desag_ids = list(Desagregacion.objects.filter(dominio_id=dom_id).values_list('id', flat=True))
    nombre = dom.nombre
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                _borrar_refs_desag(cur, desag_ids)
                _borrar_links_dominio(cur, dom_id)
                cur.execute("UPDATE indicadores_dominiodesagregacion SET dominio_padre_id=NULL WHERE dominio_padre_id=%s", [dom_id])
                cur.execute("DELETE FROM indicadores_desagregacion WHERE dominio_id=%s", [dom_id])
                cur.execute("DELETE FROM indicadores_catalogodominio WHERE dominio_id=%s", [dom_id])
                cur.execute("DELETE FROM indicadores_dominiodesagregacion WHERE id=%s", [dom_id])
                _resync_fks_legacy(cur)
            _audit(nombre, 'eliminacion', 1, len(desag_ids),
                   f'Dominio "{nombre}" (id {dom_id}) + {len(desag_ids)} desags eliminados; datos intactos')
    except Exception as e:
        messages.error(request, f'Error en eliminación (rollback aplicado): {e}')
        return wizard_normalizacion(request)
    messages.success(request,
        f'Dominio "{nombre}" y sus {len(desag_ids)} desagregaciones eliminadas. '
        'Los datos permanecen intactos.')
    return wizard_normalizacion(request)


# ──────────────────────────────────────────────────────────────────────────
# DETALLE de dominio: inspección de desagregaciones + renombrar
# ──────────────────────────────────────────────────────────────────────────

@staff_member_required
def wizard_dominio_detalle(request, dominio_id):
    """Ficha del dominio: stats, indicadores vinculados, listado completo de
    desagregaciones con conteo de referencias, subdominios y renombrado."""
    dom = DominioDesagregacion.objects.get(pk=dominio_id)

    if request.method == 'POST' and request.POST.get('accion') == 'renombrar':
        nuevo = (request.POST.get('nuevo_nombre') or '').strip()
        if not nuevo or nuevo == dom.nombre:
            messages.error(request, 'Nombre vacío o sin cambios.')
        else:
            viejo = dom.nombre
            duplicado = DominioDesagregacion.objects.filter(
                nombre__iexact=nuevo).exclude(pk=dom.id).first()
            dom.nombre = nuevo
            dom.save(update_fields=['nombre'])
            _audit(nuevo, 'renombrar', 0, 0,
                   f'Dominio id {dom.id}: "{viejo}" → "{nuevo}"')
            messages.success(request, f'Dominio renombrado: "{viejo}" → "{nuevo}".')
            if duplicado:
                messages.warning(request,
                    f'Ojo: ya existe otro dominio llamado "{duplicado.nombre}" '
                    f'(id {duplicado.id}, tipo {duplicado.tipo}). Considera conciliarlos.')
            return redirect('normalizacion:wizard_normalizacion_dominio', dominio_id=dom.id)

    desags = list(Desagregacion.objects.filter(dominio_id=dominio_id).order_by('nombre'))
    with connection.cursor() as cur:
        stats = _dominio_stats(cur, dominio_id)
        refs = _desag_refs_count(cur, [d.id for d in desags])
        cur.execute("SELECT id, nombre FROM indicadores_dominiodesagregacion WHERE dominio_padre_id=%s", [dominio_id])
        subdominios = cur.fetchall()
    tot = {k: sum(r[k] for r in refs.values())
           for k in ('datos', 'series', 'fks', 'pred', 'hijas')}
    for d in desags:
        d.refs = refs[d.id]
    return render(request, 'indicadores/normalizacion/dominio.html', {
        'dominio': dom, 'desags': desags, 'stats': stats,
        'subdominios': subdominios, 'tot': tot,
        'padre': dom.dominio_padre,
    })
