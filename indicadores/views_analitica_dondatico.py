"""
Don Datico × Superset — asistencia de IA sobre los datasets de Superset.

Submódulo del módulo Analítica e IA (rol 'analista'). A diferencia de
Consulta y Tableros (laboratorio), aquí cada capacidad es una petición
independiente:

- ``dondatico_consultar``: input semántico → consultas agregadas sobre
  los datasets → respuesta en prosa + tablas + fuentes.
- ``dondatico_analizar``: igual pero con prompt de análisis interpretivo.
- ``dondatico_generar``: input semántico → spec de charts → creación real
  del dashboard en Superset (charts + layout), ahorrándole al usuario la
  interfaz del BI.

El acceso a Superset usa ``SupersetService`` (API REST), que expone la
misma superficie de capacidades que el ``mcp_service`` de Superset —
si la instancia habilita MCP, el transporte puede cambiarse sin tocar
esta lógica.
"""

import json
import logging
import re

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .chat_config import get_config
from .decorators import analista_required
from .llm_structured import (
    SUPERSET_ANALISIS_PROMPT, SUPERSET_CONSULTA_PROMPT,
    SUPERSET_CONSULTA_SCHEMA, SUPERSET_PROSA_PROMPT,
    SUPERSET_PROSA_SCHEMA, SUPERSET_TABLERO_PROMPT,
    SUPERSET_TABLERO_SCHEMA,
)
from .superset_service import SupersetService

logger = logging.getLogger(__name__)

_MAX_CONSULTA_CHARS = 3000
_MAX_CONSULTAS_SPEC = 3
_MAX_CHARTS = 6
_CACHE_KEY_DATASETS = 'ddss_datasets_ctx'
_CACHE_TTL = 600

# Métricas de agregación permitidas en specs (whitelist anti-inyección:
# estas cadenas viajan dentro de params/chart data de Superset).
_RE_METRICA = re.compile(
    r'^(SUM|AVG|MIN|MAX|COUNT)\s*\(\s*([A-Za-z0-9_.*]+)\s*\)$',
    re.IGNORECASE)


def _int_seguro(valor, default):
    """int() tolerante: el LLM a veces devuelve strings o nulls."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return default


_OPS_FILTRO = {'=', '!=', '>', '>=', '<', '<=', 'IN', 'LIKE'}
_OP_A_ADHOC = {'=': '==', '!=': '!=', '>': '>', '>=': '>=',
               '<': '<', '<=': '<=', 'IN': 'IN', 'LIKE': 'LIKE'}


# ----------------------------------------------------------------------
# Catálogo de datasets (contexto para el LLM y validación server-side)
# ----------------------------------------------------------------------

def _datasets_contexto(service):
    """Catálogo de datasets de Superset con sus columnas, cacheado.

    El LLM lo usa para elegir fuente/columnas; el servidor lo usa para
    validar que la spec no invente datasets ni columnas.
    """
    ctx = cache.get(_CACHE_KEY_DATASETS)
    if ctx is not None:
        return ctx
    ctx = []
    for d in service.listar_datasets()[:60]:
        info = service.info_dataset(d['id']) or {}
        ctx.append({
            'id': d['id'],
            'tabla': d.get('table_name', ''),
            'tipo': d.get('kind', ''),
            'columnas': [
                {'nombre': c['nombre'], 'tipo': c['tipo'],
                 'temporal': c['temporal']}
                for c in (info.get('columnas') or [])[:40]
            ],
        })
    cache.set(_CACHE_KEY_DATASETS, ctx, _CACHE_TTL)
    return ctx


def _dataset_por_id(ctx, dataset_id):
    for d in ctx:
        try:
            if int(d['id']) == int(dataset_id):
                return d
        except (TypeError, ValueError):
            continue
    return None


def _columnas_validas(dataset):
    return {c['nombre'] for c in (dataset.get('columnas') or [])}


# ----------------------------------------------------------------------
# Saneo de specs del LLM
# ----------------------------------------------------------------------

def _sanear_filtros(filtros, columnas_ok):
    """Filtros {col, op, val} → formato adhoc de Superset chart/data."""
    saneados = []
    for f in (filtros or [])[:20]:
        if not isinstance(f, dict):
            continue
        col = str(f.get('col') or '')
        op = str(f.get('op') or '').upper()
        if col not in columnas_ok or op not in _OPS_FILTRO:
            continue
        saneados.append({
            'col': col,
            'op': _OP_A_ADHOC[op],
            'val': f.get('val'),
        })
    return saneados


def _sanear_columnas(cols, columnas_ok, limite=5):
    return [str(c) for c in (cols or [])
            if isinstance(c, str) and c in columnas_ok][:limite]


def _metrica_count():
    """COUNT(*) como métrica adhoc (los charts/queries de Superset no
    aceptan la cadena plana: la buscarían como métrica guardada)."""
    return {'expressionType': 'SQL', 'sqlExpression': 'COUNT(*)',
            'label': 'COUNT(*)', 'hasCustomLabel': False}


def _sanear_metricas(metricas, columnas_ok, limite=4):
    """'SUM(col)' → métrica adhoc de Superset.

    - SIMPLE sobre la columna real del dataset (case-insensitive):
      Superset la envuelve en el SQL con el quoting correcto.
    - COUNT(*) se emite como expresión SQL adhoc.
    - Cualquier otra cosa se descarta (whitelist anti-inyección).
    """
    out = []
    for m in (metricas or []):
        if not isinstance(m, str):
            continue
        match = _RE_METRICA.match(m.strip().replace(' ', ''))
        if not match:
            continue
        agg, col = match.group(1).upper(), match.group(2)
        if col == '*':
            out.append(_metrica_count())
        else:
            real = next((c for c in columnas_ok
                         if c.lower() == col.lower()), None)
            if not real:
                continue
            out.append({
                'expressionType': 'SIMPLE',
                'column': {'column_name': real},
                'aggregate': agg,
                'label': f'{agg}({real})',
                'hasCustomLabel': False,
            })
        if len(out) >= limite:
            break
    return out


def _sanear_consulta_spec(spec, ctx):
    """Valida una consulta agregada contra el catálogo real."""
    if not isinstance(spec, dict):
        return None, 'spec invalida'
    ds = _dataset_por_id(ctx, spec.get('dataset_id'))
    if not ds:
        return None, 'dataset no encontrado'
    columnas_ok = _columnas_validas(ds)
    metricas = _sanear_metricas(spec.get('metricas'), columnas_ok)
    # orden: solo sobre una columna real o el label de una métrica
    # adhoc ya saneada (cualquier otro string sería rechazado por
    # Superset igual que una métrica inexistente).
    orden = None
    if spec.get('orden_col'):
        oc = str(spec['orden_col'])
        labels = {m['label'] for m in metricas if 'label' in m}
        if oc in columnas_ok:
            orden = (oc, bool(spec.get('orden_desc')))
        elif oc in labels:
            orden = (next(m for m in metricas if m['label'] == oc),
                     bool(spec.get('orden_desc')))
    return {
        'dataset_id': ds['id'],
        'dataset_tabla': ds['tabla'],
        'columnas': _sanear_columnas(spec.get('columnas'), columnas_ok),
        'metricas': metricas,
        'filtros': _sanear_filtros(spec.get('filtros'), columnas_ok),
        'orden': orden,
        'limite': max(1, min(_int_seguro(spec.get('limite'), 100), 500)),
        'titulo': str(spec.get('titulo') or '')[:120],
    }, None


# ----------------------------------------------------------------------
# Charts de Superset a partir de la spec del LLM
# ----------------------------------------------------------------------

# Viz types registrados en Superset 4.x (los legacy como 'echarts_bar'
# o 'dist_bar' ya no existen → "Item with key ... is not registered").
_VIZ_SUPERSET = {
    'line': 'echarts_timeseries_line',
    'bar': 'echarts_timeseries_bar',
    'pie': 'pie',
    'big_number': 'big_number_total',
    'table': 'table',
}


def _adhoc_filters(filtros):
    """Convierte filtros chart/data → adhoc_filters de chart params."""
    out = []
    for f in (filtros or []):
        op = f.get('op')
        item = {
            'expressionType': 'SIMPLE',
            'subject': f.get('col'),
            'operator': op,
            'comparator': f.get('val'),
            'clause': 'WHERE',
            'sqlExpression': None,
            'isExtra': False,
            'isNew': False,
            'datasourceWarning': False,
            'filterOptionName': None,
        }
        out.append(item)
    return out


def _chart_params(viz, chart, columnas, metricas, filtros, limite):
    """Construye (viz_type, params) para POST /api/v1/chart/."""
    viz_type = _VIZ_SUPERSET[viz]
    x = chart.get('x')
    groupby = [g for g in columnas if g != x]
    adhoc = _adhoc_filters(filtros)
    base = {
        'datasource': f"{chart['dataset_id']}__table",
        'slice_id': None,
        'viz_type': viz_type,
        'adhoc_filters': adhoc,
        'row_limit': limite,
        'row_limit_label': limite,
        'color_scheme': 'supersetColors',
        'annotation_layers': [],
        'extra_form_data': {},
    }
    if viz == 'big_number':
        base.update({'metric': metricas[0] if metricas else _metrica_count(),
                     'subheader': '', 'y_axis_format': 'SMART_NUMBER'})
    elif viz == 'pie':
        base.update({
            'groupby': [x] if x else columnas[:1],
            'metric': metricas[0] if metricas else _metrica_count(),
            'row_limit': min(limite, 25),
            'show_labels': True, 'label_type': 'key_value_percent',
            'number_format': 'SMART_NUMBER', 'show_legend': True,
        })
    elif viz == 'bar':
        base.update({
            'x_axis': x or (columnas[0] if columnas else None),
            'metrics': metricas or [_metrica_count()],
            'groupby': groupby[:1],
            'orientation': 'vertical',
            'order_desc': True,
            'show_legend': bool(groupby),
            'y_axis_format': 'SMART_NUMBER',
        })
    elif viz == 'line':
        if not x:
            raise ValueError('un chart de lineas requiere un eje X')
        base.update({
            'x_axis': x,
            'time_grain_sqla': 'P1Y',
            'metrics': metricas or [_metrica_count()],
            'groupby': groupby[:1],
            'show_legend': bool(groupby),
            'rich_tooltip': True,
            'x_axis_time_format': 'smart_date',
            'y_axis_format': 'SMART_NUMBER',
        })
    elif viz == 'table':
        base.update({
            'query_mode': 'aggregate',
            'groupby': columnas[:5],
            'metrics': (metricas
                        or ([_metrica_count()] if not columnas else [])),
            'percent_metrics': [],
            'order_by_cols': [],
            'row_limit': max(limite, 100),
            'include_time': False,
            'show_cell_bars': True,
        })
    return viz_type, base


def _position_json(titulo, charts):
    """Layout del dashboard: header + filas de máximo 2 charts (grid 12)."""
    import json as _json
    position = {
        'DASHBOARD_VERSION_KEY': 'v2',
        'DASHBOARD_ROOT_ID': 'ROOT_ID',
        'DASHBOARD_GRID_ID': 'GRID_ID',
        'DASHBOARD_HEADER_ID': 'HEADER_ID',
        'ROOT_ID': {'type': 'ROOT', 'id': 'ROOT_ID',
                    'children': ['GRID_ID']},
        'HEADER_ID': {'type': 'HEADER', 'id': 'HEADER_ID',
                      'meta': {'text': str(titulo)[:250]}},
        'GRID_ID': {'type': 'GRID', 'id': 'GRID_ID',
                    'parents': ['ROOT_ID'], 'children': []},
    }
    filas = [charts[i:i + 2] for i in range(0, len(charts), 2)]
    for ri, fila in enumerate(filas):
        row_key = f'ROW-{ri}'
        row = {'type': 'ROW', 'id': row_key,
               'parents': ['ROOT_ID', 'GRID_ID'],
               'children': [],
               'meta': {'background': 'BACKGROUND_TRANSPARENT'}}
        for ci, chart in enumerate(fila):
            chart_key = f'CHART-{ri}-{ci}'
            position[chart_key] = {
                'type': 'CHART', 'id': chart_key,
                'parents': ['ROOT_ID', 'GRID_ID', row_key],
                'children': [],
                'meta': {
                    'width': 12 if len(fila) == 1 else 6,
                    'height': 50,
                    'chartId': chart['chart_id'],
                    'sliceName': chart['titulo'],
                    'uuid': str(chart['chart_id']),
                },
            }
            row['children'].append(chart_key)
        position[row_key] = row
        position['GRID_ID']['children'].append(row_key)
    return _json.dumps(position)


# ----------------------------------------------------------------------
# Helpers comunes
# ----------------------------------------------------------------------

def _body_json(request):
    try:
        return json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return None


def _llm(request, prompt, schema, system_prompt, schema_name,
         max_seconds=60):
    from .views_chat import ChatService
    return ChatService(request=request).generate_structured(
        prompt,
        schema,
        system_prompt=system_prompt,
        schema_name=schema_name,
        max_seconds=max_seconds,
        reasoning_effort=get_config(
            'LLM_TABLERO_REASONING_EFFORT', 'high'),
    )


def _ctx_prompt(ctx):
    return ('\n\nDATASETS DISPONIBLES EN SUPERSET (contexto real):\n'
            + json.dumps(ctx, ensure_ascii=False)[:14000])


def _ejecutar_consultas(service, ctx, consultas):
    """Ejecuta las consultas saneadas contra Superset chart/data."""
    resultados = []
    for spec in (consultas or [])[:_MAX_CONSULTAS_SPEC]:
        saneada, err = _sanear_consulta_spec(spec, ctx)
        if not saneada:
            resultados.append({
                'titulo': str((spec or {}).get('titulo') or 'Consulta'),
                'ok': False, 'error': err or 'spec invalida',
                'columnas': [], 'filas': []})
            continue
        res = service.consultar_dataset(
            saneada['dataset_id'],
            columnas=saneada['columnas'],
            metricas=saneada['metricas'],
            filtros=saneada['filtros'],
            orden=saneada['orden'],
            limite=saneada['limite'])
        resultados.append({
            'titulo': saneada['titulo'] or saneada['dataset_tabla'],
            'dataset': saneada['dataset_tabla'],
            'ok': res['ok'], 'error': res['error'],
            'columnas': res['columnas'], 'filas': res['filas'],
        })
    return resultados


def _resumen_resultados(resultados):
    """Texto compacto de los resultados para la pasada de prosa."""
    resumen = []
    for r in resultados:
        resumen.append({
            'titulo': r['titulo'],
            'dataset': r.get('dataset'),
            'ok': r['ok'],
            'error': r['error'],
            'columnas': r['columnas'],
            'filas': (r['filas'] or [])[:40],
        })
    return json.dumps(resumen, ensure_ascii=False, default=str)[:12000]


# ----------------------------------------------------------------------
# Vistas
# ----------------------------------------------------------------------

@analista_required
def dondatico_home(request):
    """Portada del submódulo: consulta, análisis y creación de tableros."""
    service = SupersetService()
    disponible = service.health_check()
    datasets = service.listar_datasets()[:60] if disponible else []
    return render(request, 'analitica/dondatico.html', {
        'superset_disponible': disponible,
        'datasets': datasets,
    })


@analista_required
@require_http_methods(['POST'])
def dondatico_consultar(request):
    """Consulta semántica → prosa + tablas + fuentes."""
    return _consulta_o_analisis(request, modo='consulta')


@analista_required
@require_http_methods(['POST'])
def dondatico_analizar(request):
    """Análisis semántico → prosa interpretativa + tablas + fuentes."""
    return _consulta_o_analisis(request, modo='analisis')


def _consulta_o_analisis(request, modo):
    body = _body_json(request)
    consulta = str((body or {}).get('consulta') or '').strip()
    if not 5 <= len(consulta) <= _MAX_CONSULTA_CHARS:
        return JsonResponse(
            {'error': 'La consulta debe tener entre 5 y 3000 caracteres'},
            status=400)

    service = SupersetService()
    if not service.health_check():
        return JsonResponse(
            {'error': 'Superset no está disponible en este momento.'},
            status=503)

    ctx = _datasets_contexto(service)
    if not ctx:
        return JsonResponse(
            {'error': 'No hay datasets en Superset. '
                      'Usa «Sincronizar SIIED» primero.'}, status=400)

    prompt = consulta + _ctx_prompt(ctx)
    system = (SUPERSET_CONSULTA_PROMPT if modo == 'consulta'
              else SUPERSET_ANALISIS_PROMPT)
    try:
        plan = _llm(request, prompt, SUPERSET_CONSULTA_SCHEMA, system,
                    schema_name=f'superset_{modo}', max_seconds=60)
    except Exception as e:
        logger.exception('DonDatico×Superset: error en pasada de consulta')
        return JsonResponse(
            {'error': f'El asistente no respondió correctamente: {e}'},
            status=502)

    if not isinstance(plan, dict) or not plan.get('consultas'):
        return JsonResponse({
            'ok': False,
            'error': ('No encontré datasets que respondan esa consulta '
                      'con lo integrado en Superset.'),
            'fuentes': plan.get('fuentes', [])
            if isinstance(plan, dict) else [],
        })

    resultados = _ejecutar_consultas(service, ctx, plan['consultas'])
    if not any(r['ok'] for r in resultados):
        return JsonResponse({
            'ok': False,
            'error': 'Las consultas a Superset fallaron.',
            'tablas': resultados,
            'fuentes': plan.get('fuentes') or [],
        })

    # Pasada 2: prosa con las cifras reales
    prompt2 = (
        f"PETICION DEL USUARIO: {consulta}\n\n"
        f"RESULTADOS DE LAS CONSULTAS (datos reales de Superset):\n"
        + _resumen_resultados(resultados))
    try:
        prosa = _llm(request, prompt2, SUPERSET_PROSA_SCHEMA,
                     SUPERSET_PROSA_PROMPT,
                     schema_name='superset_prosa', max_seconds=60)
    except Exception:
        logger.exception('DonDatico×Superset: fallo pasada de prosa')
        prosa = {}

    return JsonResponse({
        'ok': True,
        'entendido': str(plan.get('entendido') or '')[:500],
        'respuesta': str((prosa or {}).get('respuesta') or '')[:6000],
        'notas': [str(n)[:300] for n in
                  ((prosa or {}).get('notas') or [])][:4],
        'tablas': resultados,
        'fuentes': [str(f)[:200] for f in (plan.get('fuentes') or [])][:10],
    })


@analista_required
@require_http_methods(['POST'])
def dondatico_generar(request):
    """Genera un dashboard real en Superset a partir de lenguaje natural."""
    body = _body_json(request)
    consulta = str((body or {}).get('consulta') or '').strip()
    if not 5 <= len(consulta) <= _MAX_CONSULTA_CHARS:
        return JsonResponse(
            {'error': 'La descripción debe tener entre 5 y 3000 caracteres'},
            status=400)

    service = SupersetService()
    if not service.health_check():
        return JsonResponse(
            {'error': 'Superset no está disponible en este momento.'},
            status=503)

    ctx = _datasets_contexto(service)
    if not ctx:
        return JsonResponse(
            {'error': 'No hay datasets en Superset. '
                      'Usa «Sincronizar SIIED» primero.'}, status=400)

    prompt = consulta + _ctx_prompt(ctx)
    try:
        spec = _llm(request, prompt, SUPERSET_TABLERO_SCHEMA,
                    SUPERSET_TABLERO_PROMPT,
                    schema_name='superset_tablero', max_seconds=90)
    except Exception as e:
        logger.exception('DonDatico×Superset: error en spec de tablero')
        return JsonResponse(
            {'error': f'El asistente no respondió correctamente: {e}'},
            status=502)

    if not isinstance(spec, dict) or not spec.get('charts'):
        return JsonResponse({
            'ok': False,
            'error': ('No pude armar un tablero con los datasets '
                      'disponibles en Superset.'),
            'advertencias': spec.get('advertencias', [])
            if isinstance(spec, dict) else [],
        })

    titulo = str(spec.get('titulo') or 'Tablero Don Datico')[:120]

    # 1) Dashboard vacío → 2) charts asociados → 3) layout
    dash = service.crear_dashboard(titulo, publicar=False)
    if not dash['ok']:
        return JsonResponse(
            {'error': 'No se pudo crear el dashboard en Superset: '
                      f"{dash['error']}"}, status=502)
    dashboard_id = dash['dashboard_id']

    charts_result = []
    for chart in (spec.get('charts') or [])[:_MAX_CHARTS]:
        titulo_chart = str(chart.get('titulo') or 'Chart')[:120]
        ds = _dataset_por_id(ctx, chart.get('dataset_id'))
        viz = chart.get('viz')
        if not ds or viz not in _VIZ_SUPERSET:
            charts_result.append({
                'titulo': titulo_chart, 'ok': False,
                'error': 'dataset o tipo de gráfico inválido'})
            continue
        columnas_ok = _columnas_validas(ds)
        x = str(chart.get('x') or '')
        columnas = _sanear_columnas(
            [x] + list(chart.get('groupby') or []), columnas_ok)
        if x and x in columnas_ok:
            columnas = [x] + [c for c in columnas if c != x]
        elif x:
            x = None
        metricas = _sanear_metricas(
            [chart['metrica']] if chart.get('metrica') else [],
            columnas_ok)
        filtros = _sanear_filtros(chart.get('filtros'), columnas_ok)
        limite = max(1, min(_int_seguro(chart.get('limite'), 25), 500))

        # Sonda: el LLM elige datasets por nombre/metadata, sin saber si
        # tienen filas. Ejecutar la misma consulta primero evita crear
        # charts que luego renderizan "No hay datos".
        sonda = service.consultar_dataset(
            ds['id'], columnas=columnas, metricas=metricas,
            filtros=filtros, limite=2)
        if not sonda.get('ok'):
            charts_result.append({
                'titulo': titulo_chart, 'ok': False,
                'error': f"consulta previa falló: {sonda.get('error')}"})
            continue
        def _celda(fila):
            return (fila.values() if isinstance(fila, dict) else fila)
        con_valor = any(
            v is not None
            for fila in (sonda.get('filas') or [])
            for v in _celda(fila))
        if not con_valor:
            charts_result.append({
                'titulo': titulo_chart, 'ok': False,
                'error': (f"el dataset '{ds['tabla']}' no tiene datos "
                          '(o todos nulos) para esta combinación de '
                          'columnas/filtros')})
            continue

        chart_spec = {'dataset_id': ds['id'], 'x': x}
        try:
            viz_type, params = _chart_params(
                viz, chart_spec, columnas, metricas, filtros, limite)
        except Exception as e:
            charts_result.append({
                'titulo': titulo_chart, 'ok': False,
                'error': f'params inválidos: {e}'})
            continue

        creado = service.crear_chart(
            titulo_chart, ds['id'], viz_type, params,
            dashboards=[dashboard_id])
        charts_result.append({
            'titulo': titulo_chart, 'ok': creado['ok'],
            'chart_id': creado['chart_id'], 'viz': viz,
            'dataset': ds['tabla'], 'error': creado['error']})

    creados = [c for c in charts_result if c['ok'] and c.get('chart_id')]
    if creados:
        service.actualizar_dashboard(dashboard_id, {
            'dashboard_title': titulo,
            'position_json': _position_json(titulo, creados),
        })

    url_publica = service.obtener_url_publica_dashboard(dashboard_id)
    return JsonResponse({
        'ok': bool(creados),
        'dashboard_id': dashboard_id,
        'titulo': titulo,
        'url_dashboard': url_publica or '',
        'charts': charts_result,
        'fuentes': [str(f)[:200] for f in (spec.get('fuentes') or [])][:10],
        'indicadores': [str(i)[:200] for i in
                        (spec.get('indicadores') or [])][:15],
        'advertencias': [str(a)[:300] for a in
                         (spec.get('advertencias') or [])][:8],
        'error': (None if creados else
                  'El dashboard se creó pero ningún chart pudo '
                  'generarse; revísalo en Superset.'),
    })
