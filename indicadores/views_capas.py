"""Wizard de Carga de Capas Geográficas — solo admin (is_staff).

Reemplaza al flujo "un script por capa":

- PASO 1 (index):  subir archivo (.geojson/.json/.kml/.kmz/.zip-shp/.csv) y
  ver las capas existentes. Al subir se parsea y se pasa a campos.
- PASO 2 (campos): elegir campos de código y nombre (con sugerencia
  automática), elegir/crear la CapaGeo (+NivelGeografico) y el
  DominioDesagregacion geográfica al que se asociará.
- PASO 3 (asociar): tabla elemento↔desagregación con auto-match por código
  normalizado (el mismo criterio del renderer de mapas) y por nombre;
  cada elemento puede mapearse a una desag existente, crear una nueva o
  no asociarse.
- APLICAR: transaction.atomic() — upsert de ElementoGeo, capa_geo en las
  desags, creación de desags nuevas y log en audit_conciliacion_log.

Estado entre pasos: archivos temporales en MEDIA_ROOT/_geo_wizard/<token>/.
"""

import json
import os
import shutil
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection, transaction
from django.shortcuts import redirect, render

from .models import (CapaGeo, Desagregacion, DominioDesagregacion,
                     ElementoGeo, NivelGeografico)
from .utils_geo import (detect_and_parse, extract_records, guess_field,
                        norm_code, normaliza, shapefile)
from .views_normalizacion import _audit


def _wdir(token: str) -> str:
    base = os.path.join(settings.MEDIA_ROOT, '_geo_wizard')
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, token)
    os.makedirs(path, exist_ok=True)
    return path


def _load_meta(token: str) -> dict:
    with open(os.path.join(_wdir(token), 'meta.json'), encoding='utf-8') as f:
        return json.load(f)


def _save_json(token: str, name: str, data) -> None:
    with open(os.path.join(_wdir(token), name), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────────
# PASO 1: subir archivo + listado de capas
# ──────────────────────────────────────────────────────────────────────────

@staff_member_required
def wizard_capas(request):
    if request.method == 'POST' and request.FILES.get('archivo'):
        up = request.FILES['archivo']
        raw = up.read()
        if len(raw) > 80 * 1024 * 1024:
            messages.error(request, 'Archivo demasiado grande (máx. 80 MB).')
            return redirect('indicadores:wizard_capas')
        try:
            formato, parsed = detect_and_parse(up.name, raw)
        except (ValueError, KeyError, Exception) as e:
            messages.error(request, f'No se pudo leer "{up.name}": {e}')
            return redirect('indicadores:wizard_capas')
        if not parsed['features']:
            messages.error(request, f'"{up.name}" no contiene features.')
            return redirect('indicadores:wizard_capas')

        token = uuid.uuid4().hex
        with open(os.path.join(_wdir(token), 'input.bin'), 'wb') as f:
            f.write(raw)
        _save_json(token, 'meta.json', {
            'formato': formato, 'src_name': up.name,
            'fields': parsed['fields'], 'n_features': len(parsed['features']),
        })
        _save_json(token, 'parsed.json', parsed)

        fields = parsed['fields']
        sug_cod = guess_field(fields, 'code')
        sug_nom = guess_field(fields, 'name')
        preview = []
        for f in parsed['features'][:10]:
            props = f.get('props') or {}
            preview.append({k: props.get(k) for k in fields[:6]})
        return render(request, 'indicadores/capas/campos.html', {
            'token': token, 'formato': formato, 'src_name': up.name,
            'fields': fields, 'n_features': len(parsed['features']),
            'sug_cod': sug_cod or fields[0] if fields else '',
            'sug_nom': sug_nom or (fields[1] if len(fields) > 1 else (fields[0] if fields else '')),
            'preview': preview, 'preview_cols': fields[:6],
            'n_con_geom': sum(1 for f in parsed['features'] if f.get('geom')),
            'capas': CapaGeo.objects.select_related('nivel_geografico').order_by('nombre'),
            'niveles': NivelGeografico.objects.order_by('nombre'),
            'dominios': DominioDesagregacion.objects.filter(
                tipo='geografica').order_by('nombre'),
        })

    # GET: formulario + capas existentes
    capas = (CapaGeo.objects
             .select_related('nivel_geografico')
             .prefetch_related('elementos', 'desagregaciones')
             .order_by('nombre'))
    rows = [{'id': c.id, 'nombre': c.nombre, 'nivel': c.nivel_geografico.nombre,
             'n_elems': len(c.elementos.all()),
             'n_desags': len(c.desagregaciones.all())} for c in capas]
    return render(request, 'indicadores/capas/index.html', {
        'capas': rows, 'pyshp_ok': shapefile is not None,
    })


# ──────────────────────────────────────────────────────────────────────────
# PASO 2→3: campos+capa+dominio elegidos → tabla de asociación
# ──────────────────────────────────────────────────────────────────────────

@staff_member_required
def wizard_capas_asociar(request):
    if request.method != 'POST':
        return redirect('indicadores:wizard_capas')
    token = request.POST['token']
    meta = _load_meta(token)
    with open(os.path.join(_wdir(token), 'parsed.json'), encoding='utf-8') as f:
        parsed = json.load(f)

    code_field = request.POST.get('code_field') or None
    name_field = request.POST.get('name_field') or None
    if not code_field or not name_field:
        messages.error(request, 'Debes elegir campo de código y de nombre.')
        return redirect('indicadores:wizard_capas')

    # Traducir los radios del form: capa_mode ex|nueva, dom_mode ex|nuevo
    capa_mode = request.POST.get('capa_mode', 'ex')
    capa_ex = request.POST.get('capa_ex')
    capa_nombre = (request.POST.get('capa_nombre') or '').strip()
    if capa_mode == 'ex' and capa_ex:
        capa_src = f'ex_{capa_ex}'
    elif capa_mode == 'nueva' or not capa_ex:
        capa_src = 'nueva'
        if not capa_nombre:
            capa_nombre = os.path.splitext(meta['src_name'])[0]
    else:
        messages.error(request, 'Selecciona una capa existente o crea una nueva.')
        return redirect('indicadores:wizard_capas')

    dom_mode = request.POST.get('dom_mode', 'ex')
    dominio_ex = request.POST.get('dominio_ex')
    dominio_nombre = (request.POST.get('dominio_nombre') or '').strip()
    if dom_mode == 'ex' and dominio_ex:
        dominio_src = f'ex_{dominio_ex}'
    elif dom_mode == 'nuevo' or not dominio_ex:
        dominio_src = 'nuevo'
        if not dominio_nombre:
            dominio_nombre = capa_nombre
    else:
        messages.error(request, 'Selecciona un dominio existente o crea uno nuevo.')
        return redirect('indicadores:wizard_capas')

    records = extract_records(parsed, code_field, name_field)
    meta.update({
        'code_field': code_field, 'name_field': name_field,
        'capa_src': capa_src,
        'capa_nombre': capa_nombre,
        'nivel_id': request.POST.get('nivel_id'),           # 'ex_<id>' | 'nueva'
        'nivel_nombre': (request.POST.get('nivel_nombre') or '').strip(),
        'dominio_src': dominio_src,
        'dominio_nombre': dominio_nombre,
    })
    _save_json(token, 'meta.json', meta)
    _save_json(token, 'records.json', records)

    # Desags del dominio destino (si existente) para el match
    desags = []
    if (meta['dominio_src'] or '').startswith('ex_'):
        dom_id = int(meta['dominio_src'][3:])
        desags = list(Desagregacion.objects.filter(dominio_id=dom_id)
                      .order_by('nombre').values('id', 'codigo', 'nombre'))
    by_code, by_name = {}, {}
    for d in desags:
        by_code[norm_code(d['codigo'])] = d['id']
        by_name[normaliza(d['nombre'])] = d['id']

    filas = []
    usados = set()
    for i, r in enumerate(records):
        sugerido = None
        c = norm_code(r['codigo'])
        if c and c in by_code:
            sugerido = by_code[c]
        elif normaliza(r['nombre']) in by_name:
            sugerido = by_name[normaliza(r['nombre'])]
        if sugerido in usados:
            sugerido = None
        if sugerido:
            usados.add(sugerido)
        filas.append({'i': i, 'codigo': r['codigo'], 'nombre': r['nombre'],
                      'wkt': bool(r['wkt']), 'valido': r['valido'],
                      'sugerido': sugerido})

    sin_match_desags = [d for d in desags if d['id'] not in usados]
    n_invalidos = sum(1 for r in records if not r['valido'])

    return render(request, 'indicadores/capas/asociar.html', {
        'token': token, 'meta': meta, 'filas': filas, 'desags': desags,
        'sin_match_desags': sin_match_desags, 'n_invalidos': n_invalidos,
        'n_validos': sum(1 for r in records if r['valido']),
        'dominio_nombre': (DominioDesagregacion.objects.get(
            pk=int(meta['dominio_src'][3:])).nombre
            if (meta['dominio_src'] or '').startswith('ex_')
            else meta['dominio_nombre'] + ' (nuevo)'),
        'capa_display': (CapaGeo.objects.get(
            pk=int(meta['capa_src'][3:])).nombre
            if (meta['capa_src'] or '').startswith('ex_')
            else meta['capa_nombre'] + ' (nueva)'),
    })


# ──────────────────────────────────────────────────────────────────────────
# PASO 4: aplicar carga + asociación en transacción
# ──────────────────────────────────────────────────────────────────────────

@staff_member_required
def wizard_capas_aplicar(request):
    if request.method != 'POST':
        return redirect('indicadores:wizard_capas')
    token = request.POST['token']
    meta = _load_meta(token)
    with open(os.path.join(_wdir(token), 'records.json'), encoding='utf-8') as f:
        records = json.load(f)

    mapping = {}
    for k, v in request.POST.items():
        if k.startswith('m_') and k[2:].isdigit():
            mapping[int(k[2:])] = v   # 'd_<id>' | 'nueva' | 'skip'

    stats = {'elems_nuevos': 0, 'elems_upd': 0, 'elems_skip': 0,
             'asociadas': 0, 'desags_nuevas': 0}
    try:
        with transaction.atomic():
            # 1) CapaGeo (existente o nueva con su nivel)
            if (meta.get('capa_src') or '').startswith('ex_'):
                capa = CapaGeo.objects.get(pk=int(meta['capa_src'][3:]))
            else:
                if (meta.get('nivel_id') or '').startswith('ex_'):
                    nivel = NivelGeografico.objects.get(pk=int(meta['nivel_id'][3:]))
                else:
                    nivel, _ = NivelGeografico.objects.get_or_create(
                        nombre=meta['nivel_nombre'] or 'Sin nivel')
                capa, _ = CapaGeo.objects.get_or_create(
                    nombre=meta['capa_nombre'] or meta['src_name'],
                    nivel_geografico=nivel)
            # 2) Dominio geográfica
            if (meta.get('dominio_src') or '').startswith('ex_'):
                dom = DominioDesagregacion.objects.get(pk=int(meta['dominio_src'][3:]))
            else:
                dom = DominioDesagregacion.objects.create(
                    nombre=meta['dominio_nombre'] or meta['capa_nombre'],
                    tipo='geografica',
                    nivel_geografico=capa.nivel_geografico)
            # 3) Upsert de elementos
            for r in records:
                if not r['valido']:
                    stats['elems_skip'] += 1
                    continue
                el = ElementoGeo.objects.filter(
                    capa_geo=capa, codigo=r['codigo']).first()
                if el is None:
                    ElementoGeo.objects.create(
                        capa_geo=capa, codigo=r['codigo'],
                        nombre=r['nombre'], geom_wkt=r['wkt'])
                    stats['elems_nuevos'] += 1
                else:
                    changed = False
                    if el.nombre != r['nombre']:
                        el.nombre = r['nombre']; changed = True
                    if r['wkt'] and el.geom_wkt != r['wkt']:
                        el.geom_wkt = r['wkt']; changed = True
                    if changed:
                        el.save(update_fields=['nombre', 'geom_wkt'])
                        stats['elems_upd'] += 1
            # 4) Asociación elemento → desagregación
            for i, r in enumerate(records):
                sel = mapping.get(i)
                if not r['valido'] or not sel or sel == 'skip':
                    continue
                if sel == 'nueva':
                    Desagregacion.objects.create(
                        dominio=dom, nombre=r['nombre'],
                        codigo=r['codigo'], capa_geo=capa)
                    stats['desags_nuevas'] += 1
                    stats['asociadas'] += 1
                elif sel.startswith('d_'):
                    Desagregacion.objects.filter(
                        pk=int(sel[2:])).update(capa_geo=capa)
                    stats['asociadas'] += 1
            _audit(capa.nombre, 'carga_capa', 0, stats['asociadas'],
                   f"Capa '{capa.nombre}' ({meta['formato']}, {meta['src_name']}): "
                   f"{stats['elems_nuevos']} elems nuevos, {stats['elems_upd']} actualizados, "
                   f"{stats['asociadas']} desags asociadas ({stats['desags_nuevas']} creadas) "
                   f"en dominio '{dom.nombre}'")
    except Exception as e:
        messages.error(request, f'Error aplicando la carga (rollback): {e}')
        return redirect('indicadores:wizard_capas')

    shutil.rmtree(_wdir(token), ignore_errors=True)
    messages.success(request,
        f"Capa '{capa.nombre}' cargada: {stats['elems_nuevos']} elementos nuevos, "
        f"{stats['elems_upd']} actualizados, {stats['elems_skip']} omitidos; "
        f"{stats['asociadas']} desagregaciones asociadas "
        f"({stats['desags_nuevas']} creadas) en dominio '{dom.nombre}'.")
    return redirect('indicadores:wizard_capas')
