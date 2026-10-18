"""Vistas del submódulo Analítica → Taller de Gestión de Datos Institucionales.

Reúne dentro del módulo de Analítica todo lo que antes vivía en el
dashboard del taller, organizado por secciones:

  - Reportes del taller (el antiguo dashboard, restilizado).
  - Fuentes de información: explorador, interconectividad de variables,
    conciliación de duplicados, etiquetas y avances de formalización.
  - Retos de análisis (F2): clasificación y unificación.
  - Organismos: fuentes, retos y variables por entidad.
  - Seguridad de la información (F3).
  - Ecosistema 3D y Catálogo de datos (embebidos).

Pipeline medallón de fuentes:
  bronce (reportada en el taller) → plata (prevalidada por el analista)
  → gold (validada en el módulo de Validación → BaseCatalogo del Data Lake).

Detección de duplicados con `difflib` (stdlib): sin dependencias nuevas.
"""

import difflib
import re
import unicodedata
from collections import Counter, defaultdict

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST

from .decorators import analista_required
from .models import Organismo
from .models_taller import (
    FuenteRequerida, InscripcionTaller, RetoAnalisis,
)
from .models_catalogo import (
    AvanceFormalizacion, BaseCatalogo, CampoCatalogo, EtiquetaFuente,
    EvaluacionSeguridad, FuenteDatos, VariableFuente,
)
from . import views_taller


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _norm(texto):
    """Normaliza un nombre para comparación: minúsculas, sin tildes ni símbolos."""
    t = unicodedata.normalize('NFKD', texto or '')
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9 ]+', ' ', t.lower()).strip()


def _ediciones():
    """Años de edición del taller presentes en las inscripciones."""
    return (InscripcionTaller.objects.values_list('edicion', flat=True)
            .distinct().order_by('-edicion'))


def _filtro_edicion(request, qs, campo='inscripcion__edicion'):
    """Aplica el filtro ?edicion=AAAA cuando viene en la URL."""
    edicion = request.GET.get('edicion', '')
    if edicion.isdigit():
        qs = qs.filter(**{campo: int(edicion)})
    return qs, edicion


def _mapa_variables(fuentes):
    """nombre normalizado → [(fuente_id, nombre_original)] para las fuentes dadas."""
    mapa = defaultdict(list)
    for v in (VariableFuente.objects.filter(fuente__in=fuentes)
              .values('fuente_id', 'nombre')):
        mapa[_norm(v['nombre'])].append((v['fuente_id'], v['nombre']))
    return mapa


def _mapa_campos_catalogo():
    """nombre normalizado → [slug_base] para los campos del catálogo del Data Lake."""
    mapa = defaultdict(list)
    for c in (CampoCatalogo.objects.filter(base__activa=True)
              .values('nombre', 'base__slug', 'es_llave_cruce')):
        mapa[_norm(c['nombre'])].append((c['base__slug'], c['es_llave_cruce']))
    return mapa


def _variables_compartidas(fuente, mapa_vars, mapa_campos):
    """Para una fuente: variables que también existen en otras fuentes o en
    el catálogo (interconectividad). Retorna lista de dicts por variable."""
    compartidas = []
    for v in fuente.variables.all().order_by('id'):
        clave = _norm(v.nombre)
        otras_fuentes = {
            fid for fid, _ in mapa_vars.get(clave, []) if fid != fuente.id}
        bases = mapa_campos.get(clave, [])
        compartidas.append({
            'variable': v,
            'otras_fuentes': sorted(otras_fuentes),
            'bases': sorted({b for b, _ in bases}),
            'es_llave': v.es_identificador or any(l for _, l in bases),
            'compartida': bool(otras_fuentes or bases),
        })
    return compartidas


def _detectar_duplicados(fuentes, umbral=0.78):
    """Pares de fuentes activas con nombre muy similar (difflib, stdlib).

    También cuenta variables compartidas entre el par para dar evidencia."""
    datos = []
    for f in fuentes:
        org = f.inscripcion.organismo.nombre if f.inscripcion.organismo else ''
        datos.append((f.id, _norm(f.nombre), f.nombre, org,
                      {_norm(v) for v in f.variables.values_list('nombre', flat=True)}))
    pares = []
    for i in range(len(datos)):
        for j in range(i + 1, len(datos)):
            ida, norma, na, oa, va = datos[i]
            idb, normb, nb, ob, vb = datos[j]
            if not norma or not normb:
                continue
            ratio = difflib.SequenceMatcher(None, norma, normb).ratio()
            comunes = len(va & vb)
            # Nombre casi igual, o nombre igual aunque sea otro organismo,
            # o solapamiento fuerte de variables (≥3 y ≥60%)
            solape = comunes / min(len(va), len(vb)) if va and vb else 0
            if ratio >= umbral or (comunes >= 3 and solape >= 0.6):
                pares.append({
                    'a_id': ida, 'a_nombre': na, 'a_org': oa,
                    'b_id': idb, 'b_nombre': nb, 'b_org': ob,
                    'ratio': round(max(ratio, solape) * 100),
                    'variables_comunes': comunes,
                })
    return sorted(pares, key=lambda p: -p['ratio'])


# ──────────────────────────────────────────────────────────────────────────
# Reportes del taller (dashboard migrado)
# ──────────────────────────────────────────────────────────────────────────

@analista_required
def taller_reportes(request):
    """Reportes del taller de gestión de datos: el antiguo dashboard,
    renderizado dentro del módulo de Analítica."""
    context = views_taller._dashboard_context(request)
    return render(request, 'analitica/taller_reportes.html', context)


# Descargas reutilizadas del taller, re-gateadas con el permiso de analista
# (los originales exigen is_staff; el analista puede no ser staff).
taller_export_csv = analista_required(views_taller.dashboard_export.__wrapped__)
taller_export_excel = analista_required(views_taller.dashboard_export_excel.__wrapped__)
taller_export_variables = analista_required(views_taller.dashboard_export_variables.__wrapped__)
taller_informe = analista_required(views_taller.dashboard_informe.__wrapped__)
taller_casos_f2 = analista_required(views_taller.casos_f2.__wrapped__)
taller_casos_f2_excel = analista_required(views_taller.casos_f2_excel.__wrapped__)
taller_reporte_excel = analista_required(views_taller.reporte_excel.__wrapped__)
taller_presentacion = analista_required(views_taller.presentacion.__wrapped__)
taller_modelo_datos = analista_required(views_taller.modelo_datos.__wrapped__)


# ──────────────────────────────────────────────────────────────────────────
# Ecosistema 3D y Catálogo de datos (embebidos)
# ──────────────────────────────────────────────────────────────────────────

@analista_required
def taller_ecosistema(request):
    """Ecosistema 3D del taller embebido + accesos a sus exportaciones."""
    return render(request, 'analitica/taller_ecosistema.html')


@analista_required
def taller_catalogo(request):
    """Catálogo de datos del Data Lake embebido dentro de Analítica."""
    return render(request, 'analitica/taller_catalogo.html')


# ──────────────────────────────────────────────────────────────────────────
# Fuentes de información
# ──────────────────────────────────────────────────────────────────────────

@analista_required
def taller_fuentes(request):
    """Explorador de fuentes de información levantadas en el taller.

    Filtros: búsqueda libre, organismo, capa, etiqueta y edición.
    Incluye panel de posibles duplicados y chip de interconectividad
    (variables compartidas con otras fuentes o con el catálogo)."""
    qs = (FuenteDatos.objects.exclude(nombre='')
          .select_related('inscripcion__organismo', 'inscripcion__suborganismo',
                          'seguridad', 'fusionada_en', 'base_catalogo')
          .prefetch_related('variables', 'etiquetas', 'avances')
          .order_by('inscripcion__organismo__nombre', 'nombre'))

    solo_activas = request.GET.get('absorbidas') != 'si'
    if solo_activas:
        qs = qs.filter(fusionada_en__isnull=True)
    qs, edicion = _filtro_edicion(request, qs)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(descripcion__icontains=q))
    organismo_id = request.GET.get('organismo', '')
    if organismo_id.isdigit():
        qs = qs.filter(inscripcion__organismo_id=int(organismo_id))
    capa = request.GET.get('capa', '')
    if capa in dict(FuenteDatos.Capa.choices):
        qs = qs.filter(capa=capa)
    etiqueta_id = request.GET.get('etiqueta', '')
    if etiqueta_id.isdigit():
        qs = qs.filter(etiquetas__id=int(etiqueta_id))

    fuentes = list(qs)

    # Interconectividad: nº de variables de cada fuente que aparecen en
    # otras fuentes o en campos del catálogo del Data Lake.
    mapa_vars = _mapa_variables(FuenteDatos.objects.filter(fusionada_en__isnull=True))
    mapa_campos = _mapa_campos_catalogo()
    for f in fuentes:
        n = 0
        for v in f.variables.all():
            clave = _norm(v.nombre)
            if ({fid for fid, _ in mapa_vars.get(clave, [])} - {f.id}) or mapa_campos.get(clave):
                n += 1
        f.n_compartidas = n

    duplicados = _detectar_duplicados(
        [f for f in fuentes if f.fusionada_en_id is None])

    context = {
        'fuentes': fuentes,
        'q': q, 'edicion': edicion,
        'organismo_id': organismo_id, 'capa_sel': capa, 'etiqueta_id': etiqueta_id,
        'absorbidas': request.GET.get('absorbidas') == 'si',
        'organismos': (Organismo.objects.filter(inscripciones_taller__isnull=False)
                       .distinct().order_by('nombre')),
        'capas': FuenteDatos.Capa.choices,
        'etiquetas': EtiquetaFuente.objects.all(),
        'ediciones': _ediciones(),
        'duplicados': duplicados,
        'totales': {
            'fuentes': len(fuentes),
            'plata': sum(1 for f in fuentes if f.capa == 'plata'),
            'gold': sum(1 for f in fuentes if f.capa == 'gold'),
            'absorbidas': FuenteDatos.objects.filter(fusionada_en__isnull=False).count(),
        },
    }
    return render(request, 'analitica/taller_fuentes.html', context)


@analista_required
def taller_fuente_detalle(request, pk):
    """Ficha analítica de una fuente: F1, variables e interconectividad,
    F3, avances de formalización y acciones del analista."""
    fuente = get_object_or_404(
        FuenteDatos.objects
        .select_related('inscripcion__organismo', 'inscripcion__suborganismo',
                        'inscripcion__equipo', 'seguridad', 'fusionada_en',
                        'base_catalogo', 'prevalidada_por')
        .prefetch_related('variables', 'etiquetas', 'avances__usuario',
                          'relaciones', 'instrumentos', 'mecanismos',
                          'periodicidades', 'desagregaciones', 'unidades_analisis',
                          'fuentes_origen', 'fuentes_absorbidas'),
        pk=pk)

    mapa_vars = _mapa_variables(
        FuenteDatos.objects.filter(fusionada_en__isnull=True))
    mapa_campos = _mapa_campos_catalogo()
    compartidas = _variables_compartidas(fuente, mapa_vars, mapa_campos)
    nombres_otras = {f.id: f.nombre for f in
                     FuenteDatos.objects.filter(
                         pk__in={o for c in compartidas for o in c['otras_fuentes']})}
    for c in compartidas:
        c['otras'] = sorted(
            [{'id': fid, 'nombre': nombres_otras.get(fid, f'#{fid}')}
             for fid in c['otras_fuentes']],
            key=lambda x: x['nombre'])

    # Posibles duplicados de esta fuente en concreto
    candidatos = (FuenteDatos.objects
                  .filter(fusionada_en__isnull=True).exclude(pk=fuente.pk)
                  .select_related('inscripcion__organismo')
                  .prefetch_related('variables'))
    dup = _detectar_duplicados([fuente] + list(candidatos))
    similares = [p for p in dup if fuente.id in (p['a_id'], p['b_id'])][:8]

    # Retos F2 que la requieren (match por nombre normalizado)
    norm_f = _norm(fuente.nombre)
    retos_relacionados = []
    for fr in (FuenteRequerida.objects.exclude(nombre='')
               .select_related('reto__inscripcion__organismo')):
        if _norm(fr.nombre) == norm_f:
            retos_relacionados.append(fr.reto)

    seguridad = getattr(fuente, 'seguridad', None)
    factores = (seguridad.calcular_factores_riesgo_ocha()
                if seguridad else None)

    context = {
        'fuente': fuente,
        'compartidas': compartidas,
        'n_compartidas': sum(1 for c in compartidas if c['compartida']),
        'nombres_otras': nombres_otras,
        'similares': similares,
        'retos_relacionados': retos_relacionados,
        'seguridad': seguridad,
        'factores': factores,
        'etiquetas': EtiquetaFuente.objects.all(),
        'hitos': AvanceFormalizacion.Hito.choices,
        'avances': fuente.avances.all(),
        'absorbidas': fuente.fuentes_absorbidas.all(),
    }
    return render(request, 'analitica/taller_fuente_detalle.html', context)


@analista_required
@require_POST
def taller_fuente_accion(request, pk):
    """Acciones del analista sobre una fuente: etiquetas, avances de
    formalización, prevalidación (bronce→plata) y notas."""
    fuente = get_object_or_404(FuenteDatos, pk=pk)
    accion = request.POST.get('accion')

    if accion == 'etiquetas':
        ids = [i for i in request.POST.getlist('etiquetas') if i.isdigit()]
        fuente.etiquetas.set(EtiquetaFuente.objects.filter(pk__in=ids))
        nueva = request.POST.get('etiqueta_nueva', '').strip()
        if nueva:
            etiqueta, _ = EtiquetaFuente.objects.get_or_create(nombre=nueva[:60])
            fuente.etiquetas.add(etiqueta)
        messages.success(request, 'Etiquetas actualizadas.')

    elif accion == 'avance':
        hito = request.POST.get('hito', '')
        nota = request.POST.get('nota', '').strip()
        if hito not in dict(AvanceFormalizacion.Hito.choices):
            messages.error(request, 'Hito de formalización no válido.')
        else:
            AvanceFormalizacion.objects.create(
                fuente=fuente, hito=hito, nota=nota, usuario=request.user)
            messages.success(request, 'Avance de formalización registrado.')

    elif accion == 'prevalidar':
        if fuente.capa != FuenteDatos.Capa.BRONCE:
            messages.warning(request, 'Solo una fuente en capa bronce puede prevalidarse.')
        else:
            fuente.capa = FuenteDatos.Capa.PLATA
            fuente.prevalidada_por = request.user
            fuente.fecha_prevalidacion = timezone.now()
            fuente.save(update_fields=['capa', 'prevalidada_por', 'fecha_prevalidacion'])
            messages.success(
                request,
                'Fuente prevalidada (capa plata). Queda en la cola del '
                'módulo de Validación para su paso a gold.')

    elif accion == 'revertir_plata':
        if fuente.capa == FuenteDatos.Capa.PLATA:
            fuente.capa = FuenteDatos.Capa.BRONCE
            fuente.prevalidada_por = None
            fuente.fecha_prevalidacion = None
            fuente.save(update_fields=['capa', 'prevalidada_por', 'fecha_prevalidacion'])
            messages.success(request, 'Fuente devuelta a capa bronce.')

    elif accion == 'notas':
        fuente.notas_analista = request.POST.get('notas', '').strip()
        fuente.save(update_fields=['notas_analista'])
        messages.success(request, 'Notas del analista guardadas.')

    else:
        messages.error(request, 'Acción no reconocida.')

    return redirect('indicadores:analitica_taller_fuente', pk=pk)


_CAMPOS_MERGE_FUENTE = [
    'descripcion', 'relacion_otra', 'instrumento_otro', 'mecanismo_otro',
    'fecha_inicio', 'fecha_actualizacion', 'periodicidad_otra',
    'desagregacion_otra', 'num_registros', 'num_registros_fecha',
    'diccionario_ubicacion', 'rol', 'decisiones_apoya', 'unidad_analisis_otra',
    'georreferenciacion', 'nivel_georref_otro', 'problema_calidad_otro',
    'tiene_validacion', 'validacion_descripcion', 'tiene_diccionario',
]
_M2M_MERGE_FUENTE = [
    'relaciones', 'instrumentos', 'mecanismos', 'periodicidades',
    'desagregaciones', 'niveles_georref', 'problemas_calidad',
    'unidades_analisis', 'etiquetas',
]


@analista_required
def taller_conciliar(request):
    """Conciliación de dos fuentes reportadas por duplicado en el taller.

    GET: comparador lado a lado (preselección con ?a=&b=).
    POST: `mantener` absorbe a `absorbida` — se mueven variables no
    duplicadas, orígenes, seguridad (si la mantenida no tiene), M2M,
    avances y notas; la absorbida queda apuntando a la mantenida.
    """
    activas = (FuenteDatos.objects.exclude(nombre='')
               .filter(fusionada_en__isnull=True)
               .select_related('inscripcion__organismo', 'seguridad')
               .prefetch_related('variables')
               .order_by('inscripcion__organismo__nombre', 'nombre'))

    if request.method == 'POST':
        mantener = get_object_or_404(FuenteDatos, pk=request.POST.get('mantener'))
        absorber = get_object_or_404(FuenteDatos, pk=request.POST.get('absorbida'))
        if mantener.pk == absorber.pk or absorber.fusionada_en_id:
            messages.error(request, 'Par de fuentes no válido para conciliar.')
            return redirect('indicadores:analitica_taller_conciliar')

        with transaction.atomic():
            # Completar campos escalares vacíos de la mantenida
            for campo in _CAMPOS_MERGE_FUENTE:
                if not getattr(mantener, campo) and getattr(absorber, campo):
                    setattr(mantener, campo, getattr(absorber, campo))
            if not mantener.notas_analista and absorber.notas_analista:
                mantener.notas_analista = absorber.notas_analista
            mantener.save()

            # Unir M2M
            for rel in _M2M_MERGE_FUENTE:
                getattr(mantener, rel).add(*getattr(absorber, rel).all())

            # Variables: mover las que no existan ya (por nombre normalizado)
            existentes = {_norm(n) for n in
                          mantener.variables.values_list('nombre', flat=True)}
            for v in absorber.variables.all():
                if _norm(v.nombre) in existentes:
                    v.delete()
                else:
                    v.fuente = mantener
                    v.save(update_fields=['fuente'])

            # Orígenes y avances: mover siempre
            absorber.fuentes_origen.update(fuente=mantener)
            absorber.avances.update(fuente=mantener)

            # Seguridad: solo si la mantenida no la tiene
            if not hasattr(mantener, 'seguridad') and hasattr(absorber, 'seguridad'):
                seg = absorber.seguridad
                seg.fuente = mantener
                seg.save(update_fields=['fuente'])

            absorber.fusionada_en = mantener
            absorber.save(update_fields=['fusionada_en'])

            AvanceFormalizacion.objects.create(
                fuente=mantener, hito=AvanceFormalizacion.Hito.OTRO,
                nota=(f'Conciliación: se absorbió la fuente duplicada '
                      f'#{absorber.pk} «{absorber.nombre}» '
                      f'({absorber.inscripcion.organismo}).'),
                usuario=request.user)

        messages.success(
            request,
            f'«{absorber.nombre}» quedó fusionada en «{mantener.nombre}».')
        return redirect('indicadores:analitica_taller_fuente', pk=mantener.pk)

    # GET: comparador
    a_id = request.GET.get('a', '')
    b_id = request.GET.get('b', '')
    fuente_a = (activas.filter(pk=a_id).first() if a_id.isdigit() else None)
    fuente_b = (activas.filter(pk=b_id).first() if b_id.isdigit() else None)

    duplicados = _detectar_duplicados(list(activas))

    context = {
        'activas': activas,
        'fuente_a': fuente_a, 'fuente_b': fuente_b,
        'a_id': a_id, 'b_id': b_id,
        'duplicados': duplicados[:30],
    }
    return render(request, 'analitica/taller_conciliar.html', context)


# ──────────────────────────────────────────────────────────────────────────
# Retos de análisis (F2)
# ──────────────────────────────────────────────────────────────────────────

@analista_required
def taller_retos(request):
    """Apartado de retos F2: clasificación por línea, seguimiento y
    unificación de retos duplicados."""
    casos = views_taller._clasificar_retos()
    retos = {r.pk: r for r in
             (RetoAnalisis.objects
              .select_related('inscripcion__organismo', 'fusionado_en')
              .prefetch_related('fuentes_requeridas'))}
    for c in casos:
        r = retos.get(c['id'])
        c['estado'] = r.estado_seguimiento if r else 'propuesto'
        c['fusionado_en'] = r.fusionado_en_id if r else None
        c['edicion'] = r.inscripcion.edicion if r else None

    # Filtros
    linea = request.GET.get('linea', '')
    estado = request.GET.get('estado', '')
    organismo_q = request.GET.get('organismo', '')
    if linea:
        casos = [c for c in casos if c['primaria'] == linea]
    if estado == 'activos':
        casos = [c for c in casos if not c['fusionado_en']]
    elif estado in dict(RetoAnalisis.EstadoSeguimiento.choices):
        casos = [c for c in casos if c['estado'] == estado]
    if organismo_q:
        casos = [c for c in casos if organismo_q.lower() in c['organismo'].lower()]

    # Posibles duplicados entre retos por similitud de nombre
    nombres = [(c['id'], _norm(c['nombre']), c['nombre'], c['organismo'])
               for c in casos if not c['fusionado_en']]
    similares = []
    for i in range(len(nombres)):
        for j in range(i + 1, len(nombres)):
            ida, na, oa_nom, oa = nombres[i][0], nombres[i][1], nombres[i][2], nombres[i][3]
            idb, nb, ob_nom, ob = nombres[j][0], nombres[j][1], nombres[j][2], nombres[j][3]
            if not na or not nb:
                continue
            ratio = difflib.SequenceMatcher(None, na, nb).ratio()
            if ratio >= 0.72:
                similares.append({
                    'a_id': ida, 'a_nombre': oa_nom, 'a_org': oa,
                    'b_id': idb, 'b_nombre': ob_nom, 'b_org': ob,
                    'ratio': round(ratio * 100)})

    por_linea = Counter(c['primaria'] or 'SIN' for c in casos)
    lineas_cards = [{'code': code, 'label': label, 'count': por_linea.get(code, 0)}
                    for code, label in views_taller.LINEAS_F2.items()]

    context = {
        'casos': casos,
        'lineas_cards': lineas_cards,
        'sin_clasificar': por_linea.get('SIN', 0),
        'linea_sel': linea, 'estado_sel': estado, 'organismo_q': organismo_q,
        'estados': RetoAnalisis.EstadoSeguimiento.choices,
        'similares': sorted(similares, key=lambda s: -s['ratio'])[:20],
        'ediciones': _ediciones(),
    }
    return render(request, 'analitica/taller_retos.html', context)


@analista_required
def taller_reto_detalle(request, pk):
    """Ficha completa del reto F2: formulación (1.1–1.4), unidades y
    desagregaciones (1.5–1.6), fuentes requeridas (1.7–1.9), tratamiento y
    resultado (1.10–1.15), ficha de origen, seguimiento y unificación."""
    reto = get_object_or_404(
        RetoAnalisis.objects
        .select_related('inscripcion__organismo',
                        'inscripcion__suborganismo',
                        'inscripcion__equipo',
                        'inscripcion__user',
                        'fusionado_en__inscripcion__organismo',
                        'unidad_principal')
        .prefetch_related('fuentes_requeridas',
                          'unidades_relacionar', 'desagregaciones',
                          'tratamientos', 'resultados_mvp',
                          'capacidades_sipdi', 'enfoques_diferenciales',
                          'retos_absorbidos__inscripcion__organismo'),
        pk=pk)

    # Clasificación por línea temática (mismo pipeline del listado)
    caso = next((c for c in views_taller._clasificar_retos()
                 if c['id'] == reto.pk), None)

    # Fuentes F1 reportadas por la misma ficha de inscripción
    fuentes_ficha = (FuenteDatos.objects
                     .filter(inscripcion=reto.inscripcion)
                     .select_related('seguridad')
                     .prefetch_related('variables')
                     .order_by('nombre'))

    # Candidatos para unificar (activos, distintos de este)
    retos_activos = (RetoAnalisis.objects
                     .filter(fusionado_en__isnull=True)
                     .exclude(pk=pk)
                     .select_related('inscripcion__organismo')
                     .order_by('id'))

    return render(request, 'analitica/taller_reto_detalle.html', {
        'reto': reto,
        'caso': caso,
        'fuentes_ficha': fuentes_ficha,
        'retos_activos': retos_activos,
        'estados': RetoAnalisis.EstadoSeguimiento.choices,
        'lineas_f2': views_taller.LINEAS_F2,
    })


@analista_required
@require_POST
def taller_reto_accion(request, pk):
    """Acciones del analista sobre un reto: cambiar seguimiento o unificarlo."""
    reto = get_object_or_404(RetoAnalisis, pk=pk)
    accion = request.POST.get('accion')

    if accion == 'seguimiento':
        estado = request.POST.get('estado', '')
        if estado not in dict(RetoAnalisis.EstadoSeguimiento.choices):
            messages.error(request, 'Estado de seguimiento no válido.')
        else:
            reto.estado_seguimiento = estado
            nota = request.POST.get('nota', '').strip()
            if nota:
                marca = timezone.now().strftime('%d/%m/%Y')
                reto.notas_seguimiento = (
                    f'[{marca}] {nota}\n' + (reto.notas_seguimiento or '')).strip()
            reto.save(update_fields=['estado_seguimiento', 'notas_seguimiento'])
            messages.success(request, 'Seguimiento del reto actualizado.')

    elif accion == 'unificar':
        absorbido = get_object_or_404(RetoAnalisis, pk=request.POST.get('absorbido'))
        if absorbido.pk == reto.pk or absorbido.fusionado_en_id:
            messages.error(request, 'Reto no válido para unificar.')
        else:
            absorbido.fusionado_en = reto
            absorbido.save(update_fields=['fusionado_en'])
            messages.success(
                request,
                f'«{absorbido.nombre[:60]}» quedó unificado en este reto.')

    elif accion == 'reactivar':
        if reto.fusionado_en_id:
            reto.fusionado_en = None
            reto.save(update_fields=['fusionado_en'])
            messages.success(request, 'Reto reactivado (ya no está unificado).')

    else:
        messages.error(request, 'Acción no reconocida.')

    return redirect('indicadores:analitica_taller_reto', pk=reto.pk)


# ──────────────────────────────────────────────────────────────────────────
# Organismos
# ──────────────────────────────────────────────────────────────────────────

@analista_required
def taller_organismos(request):
    """Listado de organismos participantes con conteos de fuentes, retos,
    variables y criticidad."""
    organismos = (Organismo.objects
                  .filter(inscripciones_taller__isnull=False)
                  .distinct()
                  .annotate(
                      n_inscripciones=Count('inscripciones_taller', distinct=True),
                      n_fuentes=Count('inscripciones_taller__fuentes', distinct=True),
                      n_variables=Count('inscripciones_taller__fuentes__variables',
                                        distinct=True),
                      n_retos=Count('inscripciones_taller__reto', distinct=True))
                  .order_by('nombre'))

    datos = []
    for o in organismos:
        fuentes = FuenteDatos.objects.filter(inscripcion__organismo=o)
        criticos = EvaluacionSeguridad.objects.filter(
            fuente__in=fuentes, criticidad='rojo').count()
        datos.append({
            'org': o,
            'n_inscripciones': o.n_inscripciones,
            'n_fuentes': o.n_fuentes,
            'n_variables': o.n_variables,
            'n_retos': o.n_retos,
            'criticos': criticos,
            'gold': fuentes.filter(capa='gold').count(),
            'plata': fuentes.filter(capa='plata').count(),
        })

    return render(request, 'analitica/taller_organismos.html', {
        'datos': datos, 'ediciones': _ediciones()})


@analista_required
def taller_organismo_detalle(request, pk):
    """Detalle de un organismo: inscripciones, fuentes, retos, variables y
    seguridad reportada en el taller."""
    organismo = get_object_or_404(Organismo, pk=pk)
    inscripciones = (InscripcionTaller.objects
                     .filter(organismo=organismo)
                     .select_related('suborganismo', 'equipo', 'reto', 'user')
                     .prefetch_related('fuentes__variables',
                                       'fuentes__seguridad',
                                       'reto__fuentes_requeridas')
                     .order_by('edicion', '-creado'))

    # Estructura jerárquica completa del organismo (conteos vivos)
    suborganismos = (organismo.suborganismos
                     .prefetch_related('equipos')
                     .order_by('orden', 'nombre'))
    n_equipos = sum(s.equipos.all().__len__() for s in suborganismos)
    n_equipos_activos = sum(
        1 for s in suborganismos for e in s.equipos.all() if e.activo)

    fuentes = (FuenteDatos.objects
               .filter(inscripcion__organismo=organismo)
               .select_related('inscripcion', 'seguridad')
               .prefetch_related('variables', 'etiquetas')
               .order_by('-capa', 'nombre'))
    retos = (RetoAnalisis.objects
             .filter(inscripcion__organismo=organismo)
             .select_related('inscripcion')
             .prefetch_related('fuentes_requeridas'))
    variables = (VariableFuente.objects
                 .filter(fuente__inscripcion__organismo=organismo)
                 .select_related('fuente'))

    # Variables más frecuentes del organismo (normalizadas)
    conteo = Counter(_norm(v.nombre) for v in variables if v.nombre)
    top_variables = [{'nombre': n, 'total': t}
                     for n, t in conteo.most_common(15)]

    context = {
        'organismo': organismo,
        'inscripciones': inscripciones,
        'fuentes': fuentes,
        'retos': retos,
        'suborganismos': suborganismos,
        'n_equipos': n_equipos,
        'n_equipos_activos': n_equipos_activos,
        'n_variables': variables.count(),
        'top_variables': top_variables,
        'estados_reto': RetoAnalisis.EstadoSeguimiento.choices,
    }
    return render(request, 'analitica/taller_organismo_detalle.html', context)


# ──────────────────────────────────────────────────────────────────────────
# Seguridad de la información (F3)
# ──────────────────────────────────────────────────────────────────────────

@analista_required
def taller_seguridad(request):
    """Panorama F3: CIA, factores de riesgo OCHA, clasificación y
    criticidad por fuente."""
    evals = (EvaluacionSeguridad.objects
             .select_related('fuente__inscripcion__organismo')
             .prefetch_related('variables_identificadoras', 'datos_sensibles',
                               'medidas_proteccion')
             .order_by('fuente__inscripcion__organismo__nombre',
                       'fuente__nombre'))
    evals, edicion = _filtro_edicion(
        request, evals, campo='fuente__inscripcion__edicion')

    def dist(field):
        d = Counter()
        for v, c in evals.values_list(field).annotate(c=Count('id')):
            d[v or '—'] = c
        return d

    cia = [{'label': lbl, 'd': dist(f)}
           for lbl, f in [('Confidencialidad', 'confidencialidad'),
                          ('Integridad', 'integridad'),
                          ('Disponibilidad', 'disponibilidad'),
                          ('Criticidad', 'criticidad')]]

    clasificacion = [{'label': lbl, 'total': evals.filter(**{f: 'si'}).count()}
                     for lbl, f in [('Pública', 'aplica_publica'),
                                    ('Semiprivada', 'aplica_semiprivada'),
                                    ('Privada / restringida', 'aplica_privada'),
                                    ('Sensible', 'aplica_sensible'),
                                    ('Reservada', 'aplica_reservada')]]

    # Tabla por fuente con factores OCHA y criticidad
    filas = []
    for e in evals:
        riesgo = e.calcular_factores_riesgo_ocha()
        filas.append({
            'eval': e,
            'fuente': e.fuente,
            'riesgos': riesgo['total_riesgos'],
            'total_criterios': riesgo['total_criterios'],
        })
    filas.sort(key=lambda f: ({'rojo': 0, 'amarillo': 1, 'verde': 2}.get(
        f['eval'].criticidad, 3), -f['riesgos']))

    medidas = Counter()
    for e in evals:
        for o in e.medidas_proteccion.all():
            medidas[o.etiqueta] += 1

    context = {
        'evals': evals,
        'filas': filas,
        'cia': cia,
        'clasificacion': clasificacion,
        'medidas': medidas.most_common(10),
        'n_criticos': evals.filter(criticidad='rojo').count(),
        'n_datos_personales': evals.filter(contiene_datos_personales='si').count(),
        'n_sensibles': evals.filter(datos_sensibles__isnull=False).distinct().count(),
        'ediciones': _ediciones(), 'edicion': edicion,
    }
    return render(request, 'analitica/taller_seguridad.html', context)
