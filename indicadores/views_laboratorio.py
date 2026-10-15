"""
Laboratorio de Datos de Don Datico — tableros de control generados por IA.

Flujo:
  1. ``laboratorio_home`` renderiza el template con el contexto de fuentes
     reales (conjuntos de datos con sus variables + indicadores).
  2. ``laboratorio_generar`` (POST JSON {consulta, spec_actual?}) construye
     el contexto, llama ``ChatService.generate_structured`` con
     ``TABLERO_SCHEMA`` y resuelve cada tile del spec a un payload
     Plotly-ready. El LLM jamas ve ni devuelve datos: solo la spec.
  3. ``laboratorio_guardar`` persiste unicamente la spec en ``Tablero``.
  4. ``laboratorio_ver`` re-resuelve un tablero guardado contra los datos
     vigentes (el tablero siempre refleja informacion fresca).
"""
import json
import logging
import os

import pandas as pd
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .chat_config import get_config
from .llm_structured import TABLERO_SCHEMA, TABLERO_SYSTEM_PROMPT
from .models import (
    ConjuntoDatos, Dato, Indicador, Tablero, VariableConjuntoDatos,
)

logger = logging.getLogger(__name__)

AGREGACIONES = {
    'suma': 'sum', 'promedio': 'mean', 'conteo': 'count',
    'max': 'max', 'min': 'min',
}
TIPOS_TILE = {'line', 'bar', 'pie', 'kpi', 'tabla', 'mapa'}
MAX_TILES = 6
MAX_FILAS_CSV = 200_000
MAX_CONSULTA = 3000


# ----------------------------------------------------------------------
# Helpers de contexto y seguridad
# ----------------------------------------------------------------------

def _organismo_del_usuario(request):
    perfil = getattr(request.user, 'perfil_recolector', None)
    return getattr(perfil, 'organismo', None)


def _contexto_fuentes(request):
    """
    Fuentes reales que el LLM puede usar en la spec: conjuntos de datos
    (con codigos de variables exactos) e indicadores activos.

    Para no-staff con organismo, los conjuntos se acotan a los del
    organismo; los indicadores son catalogo general del SIIED.
    """
    org = _organismo_del_usuario(request)

    conjuntos_qs = (
        ConjuntoDatos.objects
        .exclude(archivo_csv='')
        .exclude(archivo_csv__isnull=True))
    if org and not request.user.is_staff:
        conjuntos_qs = conjuntos_qs.filter(organismo_productor=org)

    conjuntos = []
    for cd in conjuntos_qs.order_by('-fecha_carga'):
        # Sin archivo en disco el tile no resuelve; sin variables el
        # LLM no conoce columnas validas — no ofrecerlos como fuente
        if not os.path.exists(cd.archivo_csv.path):
            continue
        variables = list(
            VariableConjuntoDatos.objects
            .filter(conjunto_datos=cd).order_by('orden')[:30])
        if not variables:
            continue
        # La metadata puede registrar columnas que el CSV no trae
        # (ej: codigos V8/V9 cuando el archivo solo tiene V1,V2).
        # Solo se ofrecen al LLM columnas que existen de verdad.
        try:
            with cd.archivo_csv.open('rb') as f:
                headers = {str(c).strip()
                           for c in pd.read_csv(f, nrows=0).columns}
        except Exception:
            continue
        variables = [
            v for v in variables
            if v.codigo_variable.strip() in headers
        ]
        if not variables:
            continue
        conjuntos.append({
            'id': cd.id,
            'nombre': cd.nombre,
            'descripcion': (cd.descripcion or '')[:200],
            'variables': [
                {
                    'codigo': v.codigo_variable,
                    'nombre': v.nombre_variable,
                    'tipo_dato': v.tipo_dato,
                }
                for v in variables
            ],
        })
        if len(conjuntos) >= 15:
            break

    indicadores = list(
        Indicador.objects.filter(activo=True)
        .order_by('nombre')[:40]
        .values('id', 'nombre', 'unidad_medida'))

    return {
        'organismo': org.nombre if org else None,
        'conjuntos_datos': conjuntos,
        'indicadores': indicadores,
    }


# ----------------------------------------------------------------------
# Resolucion de tiles → payload Plotly-ready (los datos nunca pasan
# por el LLM; se calculan en el servidor y van directo al navegador)
# ----------------------------------------------------------------------

def _agregar(vals, agg):
    vals = list(vals)
    if not vals:
        return 0.0
    if agg == 'promedio':
        return sum(vals) / len(vals)
    if agg == 'conteo':
        return float(len(vals))
    if agg == 'max':
        return max(vals)
    if agg == 'min':
        return min(vals)
    return sum(vals)


def _trace_xy(tipo, x, y, nombre=''):
    """Construye el trace Plotly segun el tipo de tile."""
    if tipo == 'pie':
        return {'type': 'pie', 'labels': x, 'values': y, 'name': nombre}
    if tipo == 'line':
        return {'type': 'scatter', 'mode': 'lines+markers',
                'x': x, 'y': y, 'name': nombre}
    return {'type': 'bar', 'x': x, 'y': y, 'name': nombre}


def _resolver_tile_conjunto(tile):
    """Lee ``ConjuntoDatos.archivo_csv`` con pandas y agrega por dimension."""
    cd = ConjuntoDatos.objects.filter(id=tile['fuente_id']).first()
    if not cd or not cd.archivo_csv:
        return {'error': 'Conjunto de datos no encontrado o sin archivo CSV'}

    cols_validas = set(
        VariableConjuntoDatos.objects
        .filter(conjunto_datos=cd)
        .values_list('codigo_variable', flat=True))

    dimension = (tile.get('dimension') or '').strip()
    medida = (tile.get('medida') or '').strip()
    filtros = tile.get('filtros') or {}
    agg = tile.get('agregacion', 'suma')
    limite = max(1, min(int(tile.get('limite') or 10), 50))

    # Anti-alucinacion: solo columnas registradas en la metadata
    if dimension and dimension not in cols_validas:
        return {'error': f"Columna '{dimension}' no existe en '{cd.nombre}'"}
    if medida and medida not in cols_validas:
        return {'error': f"Columna '{medida}' no existe en '{cd.nombre}'"}
    for col in filtros:
        if col not in cols_validas:
            return {'error': f"Columna de filtro '{col}' no existe"}

    try:
        with cd.archivo_csv.open('rb') as f:
            df = pd.read_csv(f, low_memory=False, nrows=MAX_FILAS_CSV,
                             encoding='utf-8', encoding_errors='replace')
    except FileNotFoundError:
        logger.warning('Laboratorio: CSV no existe en disco, conjunto %s', cd.id)
        return {'error': 'El archivo de datos no está en el servidor '
                         '(conjunto subido sin archivo)'}
    except Exception as e:
        logger.warning('Laboratorio: error leyendo CSV %s: %s', cd.id, e)
        return {'error': 'No se pudo leer el archivo de datos'}

    df.columns = [str(c).strip() for c in df.columns]

    # La metadata puede tener codigos que el CSV real no tiene:
    # validar contra el archivo antes de indexar el DataFrame
    if medida and medida not in df.columns:
        return {'error': f"La columna '{medida}' no esta en el CSV "
                         f"de '{cd.nombre}'"}
    if dimension and dimension not in df.columns:
        return {'error': f"La columna '{dimension}' no esta en el CSV "
                         f"de '{cd.nombre}'"}
    for col in filtros:
        if col not in df.columns:
            return {'error': f"La columna de filtro '{col}' no esta "
                             f"en el CSV de '{cd.nombre}'"}

    # Filtros columna -> valor literal (comparacion como string)
    for col, val in filtros.items():
        df = df[df[col].astype(str).str.strip() == str(val).strip()]

    if df.empty:
        return {'error': 'Sin datos despues de aplicar los filtros'}

    if medida:
        df[medida] = pd.to_numeric(df[medida], errors='coerce')

    pd_agg = AGREGACIONES.get(agg, 'sum')

    # --- KPI ---
    if tile['tipo'] == 'kpi':
        if medida:
            serie = df[medida].dropna()
            valor = float(_agregar(serie.tolist(), agg)) if len(serie) else 0.0
            unidad = medida
        else:
            valor = float(len(df))
            unidad = 'registros'
        return {'plotly': {'kpi': {'valor': valor, 'unidad': unidad}}}

    if not dimension:
        return {'error': 'Este tipo de tile requiere una dimension'}
    if dimension not in df.columns:
        return {'error': f"La columna '{dimension}' no esta en el CSV"}

    if medida and medida in df.columns:
        grupos = (df.groupby(dimension, dropna=False)[medida]
                  .agg(pd_agg).reset_index().dropna())
        medida_col = medida
    else:
        grupos = (df.groupby(dimension, dropna=False).size()
                  .reset_index(name='conteo'))
        medida_col = 'conteo'

    # Serie temporal / orden natural vs ranking por valor
    if tile['tipo'] == 'line':
        grupos = grupos.sort_values(dimension)
    else:
        grupos = grupos.sort_values(medida_col, ascending=False)
    grupos = grupos.head(limite)

    x = grupos[dimension].astype(str).tolist()
    y = [float(v) for v in grupos[medida_col].tolist()]

    if tile['tipo'] == 'tabla':
        return {'plotly': {'tabla': {
            'headers': [dimension, medida_col],
            'filas': [[xv, yv] for xv, yv in zip(x, y)],
        }}}

    return {'plotly': {
        'data': [_trace_xy(tile['tipo'], x, y)],
        'layout': {'margin': {'t': 10, 'b': 60, 'l': 55, 'r': 15}},
    }}


def _resolver_tile_indicador(tile):
    """Agrupa ``Dato`` del indicador por anio o por desagregacion tematica."""
    ind = Indicador.objects.filter(id=tile['fuente_id'], activo=True).first()
    if not ind:
        return {'error': 'Indicador no encontrado o inactivo'}

    # El mapa se renderiza en el cliente via los endpoints geo existentes
    if tile['tipo'] == 'mapa':
        return {'viz': {
            'tipo': 'mapa',
            'indicador_id': ind.id,
            'titulo': tile.get('titulo') or ind.nombre,
        }}

    dimension = (tile.get('dimension') or 'anio').strip()
    filtros = tile.get('filtros') or {}
    agg = tile.get('agregacion', 'suma')
    limite = max(1, min(int(tile.get('limite') or 10), 50))

    qs = Dato.objects.filter(indicador=ind).order_by('fecha_dato')
    anio_filtro = filtros.get('anio')
    if anio_filtro:
        try:
            qs = qs.filter(fecha_dato__year=int(anio_filtro))
        except (TypeError, ValueError):
            pass

    datos = list(qs.prefetch_related('desagregaciones_tematicas')[:5000])
    if not datos:
        return {'error': 'El indicador no tiene datos cargados'}

    agrupado = {}
    for d in datos:
        if d.valor_dato is None:
            continue
        val = float(d.valor_dato)
        if dimension in ('anio', 'año', '') or tile['tipo'] == 'kpi':
            clave = d.fecha_dato.year if d.fecha_dato else None
        else:
            # Cualquier otra dimension = agrupar por desagregacion tematica
            tnames = [dt.nombre for dt in d.desagregaciones_tematicas.all()]
            clave = tnames[0] if tnames else 'Sin desagregacion'
        if clave is None:
            continue
        agrupado.setdefault(clave, []).append(val)

    if not agrupado:
        return {'error': 'Sin valores numericos en el indicador'}

    # --- KPI: ultimo anio disponible ---
    if tile['tipo'] == 'kpi':
        anios = [k for k in agrupado if isinstance(k, int)]
        if not anios:
            return {'error': 'Sin datos por anio para el KPI'}
        anio = max(anios)
        valor = _agregar(agrupado[anio], agg)
        return {'plotly': {'kpi': {
            'valor': valor,
            'unidad': ind.unidad_medida or '',
            'nota': f'Anio {anio}',
        }}}

    if tile['tipo'] in ('bar', 'pie', 'tabla'):
        items = sorted(agrupado.items(), key=lambda kv: -_agregar(kv[1], agg))
    else:  # line: orden temporal
        items = sorted(agrupado.items(),
                       key=lambda kv: kv[0] if isinstance(kv[0], int) else 0)
    items = items[:limite]

    x = [str(k) for k, _ in items]
    y = [float(_agregar(v, agg)) for _, v in items]

    if tile['tipo'] == 'tabla':
        return {'plotly': {'tabla': {
            'headers': [dimension if dimension else 'categoria', 'valor'],
            'filas': [[xv, yv] for xv, yv in zip(x, y)],
        }}}

    return {'plotly': {
        'data': [_trace_xy(tile['tipo'], x, y, ind.nombre)],
        'layout': {
            'margin': {'t': 10, 'b': 60, 'l': 55, 'r': 15},
            'yaxis': {'title': ind.unidad_medida or ''},
        },
    }}


def _resolver_tile(tile):
    if tile.get('fuente_tipo') == 'conjunto_datos':
        return _resolver_tile_conjunto(tile)
    return _resolver_tile_indicador(tile)


def _resolver_spec(spec):
    """Resuelve todos los tiles de una spec → lista con payload Plotly."""
    resueltos = []
    for i, tile in enumerate(spec.get('tiles') or []):
        try:
            res = _resolver_tile(tile)
        except Exception as e:
            logger.exception('Laboratorio: error resolviendo tile')
            res = {'error': str(e)[:200]}
        resueltos.append({**tile, 'id': f'tile-{i}', **res})
    return resueltos


def _sanitizar_spec(data):
    """Limpia la respuesta del LLM a una spec segura y acotada."""
    spec = {
        'titulo': str(data.get('titulo') or 'Tablero')[:120],
        'descripcion': str(data.get('descripcion') or '')[:500],
        'tiles': [],
    }
    for t in (data.get('tiles') or [])[:MAX_TILES]:
        if not isinstance(t, dict):
            continue
        fuente_tipo = t.get('fuente_tipo')
        try:
            fuente_id = int(t.get('fuente_id'))
        except (TypeError, ValueError):
            continue
        if fuente_tipo not in ('conjunto_datos', 'indicador'):
            continue
        spec['tiles'].append({
            'tipo': t.get('tipo') if t.get('tipo') in TIPOS_TILE else 'bar',
            'titulo': str(t.get('titulo') or 'Tile')[:80],
            'fuente_tipo': fuente_tipo,
            'fuente_id': fuente_id,
            'dimension': str(t.get('dimension') or '')[:100],
            'medida': str(t.get('medida') or '')[:100],
            'agregacion': (t.get('agregacion')
                           if t.get('agregacion') in AGREGACIONES else 'suma'),
            'filtros': (t.get('filtros')
                        if isinstance(t.get('filtros'), dict) else {}),
            'limite': t.get('limite') or 10,
        })
    return spec


# ----------------------------------------------------------------------
# Vistas
# ----------------------------------------------------------------------

@login_required
def laboratorio_home(request):
    """Laboratorio vacio: chat lateral + canvas listo para generar."""
    return render(request, 'laboratorio/laboratorio.html', {
        'fuentes_ctx': _contexto_fuentes(request),
    })


@login_required
@require_http_methods(['POST'])
def laboratorio_generar(request):
    """Genera/ajusta un tablero a partir de una consulta en lenguaje natural.

    Devuelve la spec saneada + cada tile resuelto a payload Plotly.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'JSON invalido'}, status=400)

    consulta = (body.get('consulta') or '').strip()
    if not 5 <= len(consulta) <= MAX_CONSULTA:
        return JsonResponse(
            {'error': 'La consulta debe tener entre 5 y 3000 caracteres'},
            status=400)

    ctx = _contexto_fuentes(request)
    if not ctx['conjuntos_datos'] and not ctx['indicadores']:
        return JsonResponse(
            {'error': 'No hay fuentes de datos disponibles para tu perfil'},
            status=400)

    prompt = consulta
    spec_actual = body.get('spec_actual')
    if isinstance(spec_actual, dict) and spec_actual.get('tiles'):
        prompt += (
            '\n\nTablero actual (ajustalo segun la nueva instruccion, '
            'conserva lo que sirva):\n'
            + json.dumps(spec_actual, ensure_ascii=False)[:3000])
    prompt += ('\n\nFUENTES DISPONIBLES (contexto real):\n'
               + json.dumps(ctx, ensure_ascii=False))

    from .views_chat import ChatService
    try:
        data = ChatService(request=request).generate_structured(
            prompt,
            TABLERO_SCHEMA,
            system_prompt=TABLERO_SYSTEM_PROMPT,
            schema_name='tablero_dondatico',
            reasoning_effort=get_config(
                'LLM_TABLERO_REASONING_EFFORT', 'high'),
        )
    except Exception as e:
        logger.exception('Laboratorio: error en generate_structured')
        return JsonResponse(
            {'error': f'El LLM no respondio correctamente: {e}'}, status=502)

    if not isinstance(data, dict) or not data.get('tiles'):
        return JsonResponse({
            'ok': False,
            'error': ('Don Datico no pudo armar un tablero con esa '
                      'consulta y las fuentes disponibles.'),
            'explicacion': str(data.get('explicacion') or '')
            if isinstance(data, dict) else '',
        }, status=200)

    spec = _sanitizar_spec(data)
    resueltos = _resolver_spec(spec)

    return JsonResponse({
        'ok': True,
        'tablero': spec,
        'tiles': resueltos,
        'explicacion': str(data.get('explicacion') or ''),
        'advertencias': [
            str(a)[:300] for a in (data.get('advertencias') or [])][:8],
    })


@login_required
@require_http_methods(['POST'])
def laboratorio_guardar(request):
    """Persiste la spec del tablero (los datos NO se guardan)."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'JSON invalido'}, status=400)

    spec = body.get('spec')
    if not isinstance(spec, dict) or not spec.get('tiles'):
        return JsonResponse({'error': 'Spec vacia o invalida'}, status=400)

    tablero_id = body.get('tablero_id')
    if tablero_id:
        tablero = get_object_or_404(Tablero, id=tablero_id)
        if tablero.autor and tablero.autor != request.user \
                and not request.user.is_staff:
            return JsonResponse(
                {'error': 'Solo el autor puede modificar este tablero'},
                status=403)
        tablero.titulo = str(spec.get('titulo') or tablero.titulo)[:300]
        tablero.descripcion = str(spec.get('descripcion') or '')
        tablero.spec = spec
        tablero.save()
    else:
        tablero = Tablero.objects.create(
            titulo=str(spec.get('titulo') or 'Tablero')[:300],
            descripcion=str(spec.get('descripcion') or '')[:500],
            consulta_original=str(body.get('consulta') or '')[:3000],
            spec=spec,
            organismo=_organismo_del_usuario(request),
            autor=request.user,
        )

    return JsonResponse({'ok': True, 'tablero_id': tablero.id})


@login_required
def laboratorio_listar(request):
    """Lista de tableros propios (+ del organismo)."""
    qs = Tablero.objects.select_related('autor', 'organismo')
    if not request.user.is_staff:
        org = _organismo_del_usuario(request)
        filtro = Q(autor=request.user)
        if org:
            filtro |= Q(organismo=org)
        qs = qs.filter(filtro)
    return render(request, 'laboratorio/listar.html', {
        'tableros': qs[:50],
    })


@login_required
def laboratorio_ver(request, tablero_id):
    """Renderiza un tablero guardado re-resolviendo sus tiles en vivo."""
    tablero = get_object_or_404(Tablero, id=tablero_id)

    if not request.user.is_staff and tablero.autor != request.user:
        org = _organismo_del_usuario(request)
        if not org or tablero.organismo != org:
            return JsonResponse(
                {'error': 'No tienes acceso a este tablero'}, status=403)

    resueltos = _resolver_spec(tablero.spec or {})
    return render(request, 'laboratorio/laboratorio.html', {
        'fuentes_ctx': _contexto_fuentes(request),
        'tablero': tablero,
        'tiles_resueltos': resueltos,
    })
