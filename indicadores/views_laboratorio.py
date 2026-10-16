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
import re

import pandas as pd
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from django.urls import reverse

from .chat_config import get_config
from .llm_structured import (
    QUIZ_PROMPT, QUIZ_SCHEMA,
    TABLERO_ANALISIS_PROMPT, TABLERO_ANALISIS_SCHEMA,
    TABLERO_SCHEMA, TABLERO_SYSTEM_PROMPT,
)
from .models import (
    CatalogoConsulta, ConjuntoDatos, Dato, Indicador, Tablero,
    VariableConjuntoDatos,
)

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def api_quiz_indicador(request, indicador_id):
    """Mini-quiz del libro 3D: 3 preguntas (1 real + 3 falsas) + resumen kids.

    Se genera con el LLM en cada llamada para que cada partida tenga
    preguntas distintas. El modelo solo recibe metadata limpia y una
    muestra breve de datos reales; nada mas.
    """
    ind = get_object_or_404(Indicador, pk=indicador_id, activo=True)

    def _limpia(texto, limite=400):
        if not texto:
            return ''
        plano = re.sub(r'<[^>]+>', ' ', str(texto))
        plano = re.sub(r'\s+', ' ', plano).strip()
        return plano[:limite]

    meta_lineas = [
        f'Nombre: {ind.nombre}',
        f'Unidad de medida: {ind.unidad_medida or "no especificada"}',
        f'Fuente: {ind.fuente_datos or "no especificada"}',
    ]
    sub = getattr(ind, 'subtema', None)
    if sub and getattr(sub, 'tema', None):
        meta_lineas.append(f'Tema: {sub.tema.nombre}')
        if getattr(sub.tema, 'dominio', None):
            meta_lineas.append(f'Dominio: {sub.tema.dominio.nombre}')
    for campo, etiqueta in (
        ('objetivo', 'Objetivo'),
        ('descripcion_indicador', 'Descripción'),
        ('metodo_medicion', 'Método de medición'),
    ):
        txt = _limpia(getattr(ind, campo, ''))
        if txt:
            meta_lineas.append(f'{etiqueta}: {txt}')

    datos = (ind.datos.order_by('-fecha_dato')
             .prefetch_related('desagregaciones_geograficas',
                               'desagregaciones_tematicas')[:20])
    muestra = []
    for d in datos:
        partes = [d.fecha_dato.strftime('%Y-%m-%d'),
                  f'valor={d.valor_dato}']
        geo = ', '.join(x.nombre for x in d.desagregaciones_geograficas.all())
        tem = ', '.join(x.nombre for x in d.desagregaciones_tematicas.all())
        if geo:
            partes.append(f'zona: {geo}')
        if tem:
            partes.append(f'categoría: {tem}')
        muestra.append(' | '.join(partes))

    prompt = (
        'INDICADOR:\n' + '\n'.join(meta_lineas) +
        '\n\nMUESTRA DE DATOS REALES (más recientes):\n' +
        ('\n'.join(muestra) if muestra else '(sin datos numéricos)') +
        '\n\nGenera el quiz completo siguiendo el schema.'
    )

    try:
        from .views_chat import ChatService
        data = ChatService(request=request).generate_structured(
            prompt,
            QUIZ_SCHEMA,
            system_prompt=QUIZ_PROMPT,
            schema_name='quiz_indicador',
            max_seconds=45,
        )
    except Exception as exc:
        logger.warning(
            f'[QUIZ] LLM falló para indicador {indicador_id}: {exc}')
        return JsonResponse(
            {'error': 'No se pudo generar el quiz, inténtalo de nuevo.'},
            status=502)

    preguntas = data.get('preguntas') or []
    validas = [
        p for p in preguntas
        if isinstance(p, dict)
        and p.get('pregunta') and p.get('correcta')
        and isinstance(p.get('falsas'), list) and len(p['falsas']) >= 3
    ]
    if len(validas) < 3:
        return JsonResponse(
            {'error': 'El quiz llegó incompleto, inténtalo de nuevo.'},
            status=502)

    return JsonResponse({
        'indicador_id': ind.id,
        'indicador_nombre': ind.nombre,
        'resumen_meta': data.get('resumen_meta') or '',
        'preguntas': validas[:3],
        'felicitacion': data.get('felicitacion') or '¡Excelente trabajo!',
        'animo': data.get('animo') or '¡Casi! Inténtalo otra vez.',
    })

AGREGACIONES = {
    'suma': 'sum', 'promedio': 'mean', 'conteo': 'count',
    'max': 'max', 'min': 'min',
}
TIPOS_TILE = {'line', 'bar', 'pie', 'kpi', 'tabla', 'mapa', 'texto'}
MAX_TILES = 8
MAX_FILAS_CSV = 200_000
MAX_CONSULTA = 3000


# ----------------------------------------------------------------------
# Helpers de contexto y seguridad
# ----------------------------------------------------------------------

def _organismo_del_usuario(request):
    perfil = getattr(request.user, 'perfil_recolector', None)
    return getattr(perfil, 'organismo', None)


_LAB_STOPWORDS = {
    'a', 'al', 'como', 'con', 'cual', 'cuales', 'dame', 'de', 'del',
    'donde', 'e', 'el', 'en', 'entre', 'es', 'esa', 'ese', 'eso', 'esta',
    'este', 'esto', 'genera', 'generar', 'grafica', 'grafico', 'hay',
    'la', 'las', 'lo', 'los', 'mas', 'me', 'mi', 'muestra', 'muestrame',
    'muy', 'no', 'o', 'para', 'por', 'que', 'quiero', 'se', 'si', 'sin',
    'sobre', 'su', 'sus', 'tablero', 'tabla', 'todos',
    'u', 'un', 'una', 'unas', 'unos', 'ver', 'y', 'ya',
}


def _norm(texto):
    """Minusculas sin acentos — para match robusto contra nombres."""
    import unicodedata
    return ''.join(
        c for c in unicodedata.normalize('NFKD', (texto or '').lower())
        if not unicodedata.combining(c))


def _terminos_consulta(consulta):
    """Palabras clave de la consulta: sin stopwords ni ruido."""
    return [
        t for t in re.findall(r'[a-z0-9]+', _norm(consulta))
        if t not in _LAB_STOPWORDS and len(t) >= 3
    ]


def _contexto_fuentes(request, consulta=''):
    """
    Fuentes reales que el LLM puede usar en la spec: conjuntos de datos
    (con codigos de variables exactos), cuadros del catalogo de consulta
    e indicadores activos (con forma: serie / registro / corte).

    Para no-staff con organismo, los conjuntos se acotan a los del
    organismo; los indicadores son catalogo general del SIIED.

    Cuando hay ``consulta`` los indicadores se ordenan por relevancia
    semantica (misma busqueda vectorial del chat) — sin esto solo se
    enviaban los primeros 40 por orden alfabetico y el LLM no podia
    usar indicadores fuera de ese tramo (ej: 'Poblacion total').
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

    # Cuadros del catalogo de consulta: tablas oficiales listas para
    # graficar (columnas + filas ya cargadas, sin CSV)
    catalogos = [
        {
            'id': cc.id,
            'nombre': cc.nombre,
            'descripcion': (cc.descripcion or '')[:200],
            'columnas': list(cc.columnas or [])[:15],
        }
        for cc in CatalogoConsulta.objects
        .filter(activo=True).order_by('orden')[:10]
    ]

    # Indicadores con forma de sus datos: cuantos anios cubre la serie
    # y cuantas filas tiene — una "foto" de un solo anio con muchas
    # filas suele ser un registro de entidades, no una serie agregable.
    from django.db.models import Count
    stats_dato = {
        r['indicador_id']: r for r in
        Dato.objects.filter(indicador__activo=True)
        .values('indicador_id')
        .annotate(anios=Count('fecha_dato__year', distinct=True),
                  filas=Count('id'))
    }
    base = list(Indicador.objects
                .filter(activo=True, datos__isnull=False)
                .distinct().order_by('nombre')
                .values('id', 'nombre', 'unidad_medida'))

    # Ranking por relevancia a la consulta. La frase cruda del usuario
    # ('dame el grafico de...') diluye el embedding y nunca matchea en
    # icontains: primero se extraen los terminos clave y se busca por
    # ellos (acento-insensible); la semantica corre sobre la consulta
    # ya limpia. La union preserva ambos: texto primero, semantica tras.
    ids_ranked = []
    if consulta:
        terminos = _terminos_consulta(consulta)
        if terminos:
            scored = []
            for ind in base:
                n = _norm(ind['nombre'])
                hits = sum(1 for t in terminos if t in n)
                if hits:
                    scored.append((-hits, ind['id']))
            scored.sort()
            ids_ranked = [i for _, i in scored[:20]]
        consulta_sem = ' '.join(terminos) or consulta
        try:
            from .search import SemanticSearch
            resultados_sem = SemanticSearch().buscar_similar(
                consulta=consulta_sem, tipo_doc='indicador',
                top_k=30, umbral=0.3)
            ids_sem = [r['referencia_id'] for r in resultados_sem
                       if r.get('referencia_id')]
            ids_ranked = list(dict.fromkeys(ids_ranked + ids_sem))
        except Exception:
            logger.warning(
                'Laboratorio: busqueda semantica de indicadores fallo',
                exc_info=True)

    # Primero los relevantes, luego el resto alfabetico para rellenar.
    if ids_ranked:
        ranked_set = set(ids_ranked)
        por_id = {ind['id']: ind for ind in base}
        ordenados = [por_id[i] for i in ids_ranked if i in por_id]
        ordenados += [ind for ind in base if ind['id'] not in ranked_set]
    else:
        ordenados = base

    indicadores = []
    for ind in ordenados[:40]:
        s = stats_dato.get(ind['id']) or {}
        anios = s.get('anios') or 0
        filas = s.get('filas') or 0
        if anios >= 2:
            forma = 'serie'  # mediciones en varios anios
        elif filas > 30:
            forma = 'registro'  # foto de entidades, no agregable
        else:
            forma = 'corte'  # pocos datos de un solo anio
        indicadores.append({
            'id': ind['id'],
            'nombre': ind['nombre'],
            'unidad_medida': ind['unidad_medida'],
            'forma': forma,
            'anios': anios,
            'filas': filas,
        })

    return {
        'organismo': org.nombre if org else None,
        'conjuntos_datos': conjuntos,
        'indicadores': indicadores,
        'catalogo_consulta': catalogos,
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

    return _resolver_df(df, tile, cd.nombre)


def _resolver_tile_catalogo(tile):
    """Resuelve contra un cuadro del catálogo de consulta (filas JSON)."""
    cc = CatalogoConsulta.objects.filter(
        id=tile['fuente_id'], activo=True).first()
    if not cc:
        return {'error': 'Cuadro del catalogo de consulta no encontrado'}
    if not cc.filas:
        return {'error': f"El cuadro '{cc.nombre}' no tiene filas cargadas"}
    df = pd.DataFrame(cc.filas)
    return _resolver_df(df, tile, cc.nombre)


def _resolver_df(df, tile, fuente_nombre):
    """Agrega un DataFrame ya cargado según dimension/medida del tile."""
    dimension = (tile.get('dimension') or '').strip()
    medida = (tile.get('medida') or '').strip()
    filtros = tile.get('filtros') or {}
    agg = tile.get('agregacion', 'suma')
    limite = max(1, min(int(tile.get('limite') or 10), 50))

    df.columns = [str(c).strip() for c in df.columns]

    # Validar contra columnas reales antes de indexar el DataFrame
    if medida and medida not in df.columns:
        return {'error': f"La columna '{medida}' no esta en "
                         f"'{fuente_nombre}'"}
    if dimension and dimension not in df.columns:
        return {'error': f"La columna '{dimension}' no esta en "
                         f"'{fuente_nombre}'"}
    for col in filtros:
        if col not in df.columns:
            return {'error': f"La columna de filtro '{col}' no esta "
                             f"en '{fuente_nombre}'"}

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
        if tile['tipo'] == 'tabla':
            # Sin dimension: tabla de filas crudas (primeras N filas).
            cols = [medida] if medida and medida in df.columns else []
            cols += [c for c in df.columns if c not in cols]
            cols = cols[:6]
            sub = df[cols].head(limite)
            filas = [
                ['' if pd.isna(v) else str(v) for v in fila]
                for fila in sub.itertuples(index=False)
            ]
            return {'plotly': {'tabla': {'headers': cols, 'filas': filas}}}
        return {'error': 'Este tipo de tile requiere una dimension'}
    if dimension not in df.columns:
        return {'error': f"La columna '{dimension}' no esta en la fuente"}

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

    datos = list(qs.prefetch_related('desagregaciones_tematicas',
                                     'desagregaciones_geograficas')[:5000])
    if not datos:
        return {'error': 'El indicador no tiene datos cargados'}

    es_anio = dimension in ('anio', 'año', '') or tile['tipo'] == 'kpi'
    if es_anio:
        # Preferir la fila "total": sin desagregaciones o con todas las
        # desagregaciones en etiqueta 'Total' — evita doble conteo al
        # sumar totales + componentes (ej. Total + Cabecera + Centros).
        def _solo_totales(d):
            desags = (list(d.desagregaciones_tematicas.all())
                      + list(d.desagregaciones_geograficas.all()))
            if not desags:
                return True
            return all('total' in dt.nombre.lower() for dt in desags)
        totales = [d for d in datos if _solo_totales(d)]
        if totales:
            datos = totales
        else:
            # ¿Registro por entidad? Cuando cada fila es un CAMPO de un
            # registro (teléfono, código, camas…), las magnitudes por
            # "desagregación" son incompatibles: teléfonos ~1e9 junto a
            # conteos ~1e2. Si las sumas por nombre dentro del mismo año
            # difieren en más de 100×, no hay una medición agregable.
            sumas_campo = {}
            for d in datos:
                if d.valor_dato is None:
                    continue
                anio_d = d.fecha_dato.year if d.fecha_dato else None
                for dt in d.desagregaciones_tematicas.all():
                    k = (anio_d, dt.nombre)
                    sumas_campo[k] = sumas_campo.get(k, 0.0) + float(d.valor_dato)
            por_anio = {}
            for (anio_d, _), v in sumas_campo.items():
                por_anio.setdefault(anio_d, []).append(v)
            for sums in por_anio.values():
                pos = [s for s in sums if s > 0]
                if len(pos) > 1 and max(pos) / min(pos) > 100:
                    return {'error': (
                        'Este indicador contiene registros por entidad '
                        '(cada fila es un campo de un registro, no una '
                        'medición agregable); no se puede resumir en una '
                        'cifra ni en una serie.')}

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
    if tile.get('tipo') == 'texto':
        # Bloque de prosa: nada que resolver, el cuerpo ya viene en la spec
        return {'texto': tile.get('texto') or ''}
    fuente_tipo = tile.get('fuente_tipo')
    if fuente_tipo == 'conjunto_datos':
        return _resolver_tile_conjunto(tile)
    if fuente_tipo == 'catalogo_consulta':
        return _resolver_tile_catalogo(tile)
    return _resolver_tile_indicador(tile)


def _url_fuente_tile(tile):
    """URL pública donde el usuario puede consultar la fuente del tile."""
    fid = tile.get('fuente_id')
    try:
        if tile.get('fuente_tipo') == 'indicador' and fid:
            # La ficha de conjuntos del indicador muestra sus datos
            return reverse('indicadores:conjunto_datos_detalle',
                           args=[fid])
        if tile.get('fuente_tipo') == 'conjunto_datos' and fid:
            return reverse('indicadores:conjuntos_datos_explorer')
        if tile.get('fuente_tipo') == 'catalogo_consulta' and fid:
            return reverse('indicadores:catalogo_consulta_detalle',
                           args=[fid])
    except Exception:
        pass
    return None


def _resolver_spec(spec):
    """Resuelve todos los tiles de una spec → lista con payload Plotly."""
    resueltos = []
    for i, tile in enumerate(spec.get('tiles') or []):
        try:
            res = _resolver_tile(tile)
        except Exception as e:
            logger.exception('Laboratorio: error resolviendo tile')
            res = {'error': str(e)[:200]}
        url = _url_fuente_tile(tile)
        if url:
            res['fuente_url'] = url
        resueltos.append({**tile, 'id': f'tile-{i}', **res})
    _ajustar_tamanos(resueltos)
    return resueltos


def _ajustar_tamanos(resueltos):
    """Ancho automático de tiles según lo que realmente resolvieron.

    La spec del LLM trae 'tamano' pero no siempre acierta: con los datos
    ya resueltos sabemos si el gráfico necesita aire. Solo se amplía,
    nunca se reduce lo que el LLM pidió amplio.
    """
    for r in resueltos:
        if r.get('tamano') == 'amplio' or r.get('error'):
            continue
        if r.get('tipo') == 'texto':
            r['tamano'] = 'amplio'
            continue
        # Los mapas necesitan todo el ancho para la malla de comunas
        if (r.get('viz') or {}).get('tipo') == 'mapa':
            r['tamano'] = 'amplio'
            continue
        p = r.get('plotly') or {}
        if 'kpi' in p:
            continue  # los KPI se ven bien a media columna
        data = p.get('data') or []
        puntos = max((len(tr.get('x') or tr.get('labels') or [])
                      for tr in data), default=0)
        filas = len((p.get('tabla') or {}).get('filas') or [])
        # Serie con ≥8 puntos, multi-serie o tabla larga → ancho completo
        if puntos >= 8 or len(data) > 2 or filas > 15:
            r['tamano'] = 'amplio'


def _sanitizar_spec(data):
    """Limpia la respuesta del LLM a una spec segura y acotada."""
    spec = {
        'titulo': str(data.get('titulo') or 'Tablero')[:120],
        'descripcion': str(data.get('descripcion') or '')[:500],
        'tiles': [],
    }
    spec['contexto'] = str(data.get('contexto') or '')[:2000]
    for t in (data.get('tiles') or [])[:MAX_TILES]:
        if not isinstance(t, dict):
            continue
        comunes = {
            'tipo': t.get('tipo') if t.get('tipo') in TIPOS_TILE else 'bar',
            'titulo': str(t.get('titulo') or 'Tile')[:80],
            'insight': str(t.get('insight') or '')[:600],
            'tamano': (t.get('tamano')
                       if t.get('tamano') in ('mitad', 'amplio')
                       else 'mitad'),
        }
        if comunes['tipo'] == 'texto':
            # Los tiles de prosa no requieren fuente ni agregacion
            comunes['texto'] = str(t.get('texto') or '')[:2000]
            spec['tiles'].append(comunes)
            continue
        fuente_tipo = t.get('fuente_tipo')
        try:
            fuente_id = int(t.get('fuente_id'))
        except (TypeError, ValueError):
            continue
        if fuente_tipo not in ('conjunto_datos', 'indicador',
                               'catalogo_consulta'):
            continue
        # Los conjuntos de datos siempre se muestran como TABLA
        # (regla de UX: no graficar conjuntos de datos).
        if fuente_tipo == 'conjunto_datos':
            comunes['tipo'] = 'tabla'
        spec['tiles'].append({
            **comunes,
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


def _segunda_pasada_analisis(request, spec, resueltos):
    """Pasada 2: prosa post-datos — analisis del tablero + insight por tile.

    Solo ve el resumen de lo ya resuelto (nunca los datos crudos) y solo
    devuelve lectura. Falla silenciosa: si el LLM no responde, el tablero
    queda con los insights de la primera pasada.
    """
    resumen = []
    for i, r in enumerate(resueltos):
        item = {'indice': i, 'titulo': r.get('titulo'), 'tipo': r.get('tipo')}
        p = r.get('plotly') or {}
        if 'kpi' in p:
            item['datos'] = {
                'valor': p['kpi'].get('valor'),
                'unidad': p['kpi'].get('unidad'),
                'nota': p['kpi'].get('nota'),
            }
        elif 'tabla' in p:
            item['datos'] = {
                'headers': p['tabla'].get('headers'),
                'filas': (p['tabla'].get('filas') or [])[:8],
            }
        elif p.get('data'):
            d0 = p['data'][0] or {}
            item['datos'] = {
                'x': (d0.get('x') or [])[:12],
                'y': (d0.get('y') or [])[:12],
            }
        elif r.get('viz'):
            item['datos'] = {'viz': r['viz'].get('tipo')}
        elif r.get('error'):
            item['datos'] = {'error': r['error']}
        elif r.get('tipo') == 'texto':
            item['datos'] = {'texto': (r.get('texto') or '')[:300]}
        resumen.append(item)

    if not resumen:
        return {}

    prompt = (
        'TABLERO: ' + (spec.get('titulo') or '') + ' — '
        + (spec.get('descripcion') or '') + '\n\n'
        'RESUMEN DE DATOS RESUELTOS (por tile, en orden):\n'
        + json.dumps(resumen, ensure_ascii=False)[:8000])

    from .views_chat import ChatService
    try:
        data = ChatService(request=request).generate_structured(
            prompt,
            TABLERO_ANALISIS_SCHEMA,
            system_prompt=TABLERO_ANALISIS_PROMPT,
            schema_name='tablero_analisis',
            max_seconds=40,
            reasoning_effort=get_config(
                'LLM_TABLERO_REASONING_EFFORT', 'high'),
        )
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.warning('Laboratorio: segunda pasada de analisis fallo',
                       exc_info=True)
        return {}


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

    ctx = _contexto_fuentes(request, consulta)
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

    # Pasada 2: analisis en prosa con cifras reales (no fatal si falla).
    # Se funde en la spec para que persista al guardar el tablero.
    analisis = _segunda_pasada_analisis(request, spec, resueltos)
    if analisis:
        spec['analisis'] = str(analisis.get('analisis') or '')[:2000]
        insights = analisis.get('insights')
        if isinstance(insights, list):
            for i, ins in enumerate(insights):
                if not isinstance(ins, str) or not ins.strip():
                    continue
                ins = ins.strip()[:600]
                if i < len(spec['tiles']):
                    spec['tiles'][i]['insight'] = ins
                if i < len(resueltos):
                    resueltos[i]['insight'] = ins

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
