"""
Catálogo de Variables (ex aplicación PHP de planestadistico.cali.gov.co).

- Vistas públicas: buscador con filtros + ficha completa de variable.
- Vistas de gestión: dentro del módulo de Validación, solo equipo SIIED
  (validador_sistema_required): CRUD de variables, valores de dominio y
  tablas de referencia.
"""

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import validador_sistema_required, taller_login_required
from .models import (
    CVAreaInformacion, CVUnidadAnalisis, CVTipoDato, CVTipoVariableEstadistica,
    CVTipoValoresDominio, CVGeografia, CVVariable, CVValor, CVNoticia,
    DominioDesagregacion, Desagregacion,
    NivelGeografico, CapaGeo, ElementoGeo,
    ConjuntoDatos, VariableConjuntoDatos,
    FuenteDatos, VariableFuente, BaseCatalogo, CampoCatalogo,
    Organismo, RetoAnalisis,
)

POR_PAGINA = 20


# ======================================================================
# PARTE PÚBLICA
# ======================================================================

def _filtros_catalogo(request):
    """Extrae y aplica los filtros del buscador público."""
    qs = CVVariable.objects.select_related(
        'unidad_analisis', 'tipo_dato', 'tipo_variable_estadistica',
        'area_informacion', 'tipo_valores',
    )

    params = {
        'q': request.GET.get('q', '').strip(),
        'unidad': request.GET.get('unidad', ''),
        'tipo_dato': request.GET.get('tipo_dato', ''),
        'tipo_variable': request.GET.get('tipo_variable', ''),
        'area': request.GET.get('area', ''),
    }

    if params['q']:
        qs = qs.filter(
            Q(id_variable__icontains=params['q']) |
            Q(nombre__icontains=params['q']) |
            Q(descripcion__icontains=params['q'])
        )
    if params['unidad']:
        qs = qs.filter(unidad_analisis_id=params['unidad'])
    if params['tipo_dato']:
        qs = qs.filter(tipo_dato_id=params['tipo_dato'])
    if params['tipo_variable']:
        qs = qs.filter(tipo_variable_estadistica_id=params['tipo_variable'])
    if params['area']:
        qs = qs.filter(area_informacion_id=params['area'])

    return qs.order_by('id_variable'), params


def _contexto_filtros():
    return {
        'unidades': CVUnidadAnalisis.objects.annotate(
            n=Count('variables')).all(),
        'tipos_datos': CVTipoDato.objects.annotate(
            n=Count('variables')).all(),
        'tipos_variables': CVTipoVariableEstadistica.objects.annotate(
            n=Count('variables')).all(),
        'areas': CVAreaInformacion.objects.annotate(
            n=Count('variables')).all(),
    }


def catalogo_variables_home(request):
    """Buscador del catálogo de variables (equivalente a consulta del PHP)."""
    variables, params = _filtros_catalogo(request)
    paginador = Paginator(variables, POR_PAGINA)
    pagina = paginador.get_page(request.GET.get('page'))

    querystring_sin_pagina = request.GET.copy()
    querystring_sin_pagina.pop('page', None)

    context = {
        'pagina': pagina,
        'params': params,
        'qs_base': querystring_sin_pagina.urlencode(),
        'total': paginador.count,
        **_contexto_filtros(),
    }
    return render(request, 'catalogo_variables/home.html', context)


def catalogo_variables_ficha(request, id_variable):
    """Ficha completa de una variable (equivalente a consultarFicha del PHP)."""
    variable = get_object_or_404(
        CVVariable.objects.select_related(
            'unidad_analisis', 'tipo_dato', 'tipo_variable_estadistica',
            'area_informacion', 'tipo_valores',
        ),
        pk=id_variable,
    )
    context = {
        'variable': variable,
        'valores': variable.valores.all(),
    }
    return render(request, 'catalogo_variables/ficha.html', context)


def catalogo_variables_geografias(request):
    """Niveles y capas geográficas del SIIED con sus elementos."""
    nivel_id = request.GET.get('nivel', '').strip()
    capa_id = request.GET.get('capa', '').strip()

    niveles = NivelGeografico.objects.prefetch_related(
        'capas', 'capas__elementos').order_by('nombre')
    if nivel_id.isdigit():
        niveles = niveles.filter(pk=int(nivel_id))

    capa_sel = None
    elementos = None
    if capa_id.isdigit():
        capa_sel = get_object_or_404(
            CapaGeo.objects.select_related('nivel_geografico'), pk=int(capa_id))
        paginador = Paginator(
            capa_sel.elementos.order_by('codigo'), POR_PAGINA)
        elementos = paginador.get_page(request.GET.get('page'))

    return render(request, 'catalogo_variables/geografias.html', {
        'niveles': niveles,
        'todos_niveles': NivelGeografico.objects.order_by('nombre'),
        'nivel_id': nivel_id,
        'capa_sel': capa_sel,
        'elementos': elementos,
        'total_niveles': NivelGeografico.objects.count(),
        'total_capas': CapaGeo.objects.count(),
        'total_elementos': ElementoGeo.objects.count(),
    })


# ======================================================================
# GESTIÓN (módulo de Validación — solo equipo SIIED)
# ======================================================================

class CVVariableForm(forms.ModelForm):
    class Meta:
        model = CVVariable
        fields = [
            'id_variable', 'nombre', 'descripcion',
            'unidad_analisis', 'tipo_dato', 'tipo_variable_estadistica',
            'area_informacion', 'tipo_valores',
            'llave_primaria', 'campo_obligatorio', 'longitud_campo',
            'reglas_consistencia', 'reglas_validacion_lenguaje_natural',
            'forma_pregunta', 'opciones_respuesta',
        ]
        widgets = {
            'id_variable': forms.TextInput(attrs={'class': 'cv-input'}),
            'nombre': forms.TextInput(attrs={'class': 'cv-input'}),
            'longitud_campo': forms.TextInput(attrs={'class': 'cv-input'}),
            'llave_primaria': forms.Select(choices=(('', '—'), ('SI', 'Sí'), ('NO', 'No')), attrs={'class': 'cv-input'}),
            'campo_obligatorio': forms.Select(choices=(('', '—'), ('SI', 'Sí'), ('NO', 'No')), attrs={'class': 'cv-input'}),
        }


class CVValorForm(forms.ModelForm):
    class Meta:
        model = CVValor
        fields = ['descripcion_valor']
        widgets = {
            'descripcion_valor': forms.Textarea(attrs={'rows': 2, 'class': 'cv-input'}),
        }


def _base_gestion_context(request):
    return {
        'es_validador_organismo': False,
        'es_validador_sistema': True,
    }


@validador_sistema_required
def gestion_catalogo_variables(request):
    """Panel de gestión: métricas + listado/búsqueda de variables."""
    variables, params = _filtros_catalogo(request)
    paginador = Paginator(variables, POR_PAGINA)
    pagina = paginador.get_page(request.GET.get('page'))

    querystring_sin_pagina = request.GET.copy()
    querystring_sin_pagina.pop('page', None)

    context = {
        'pagina': pagina,
        'params': params,
        'qs_base': querystring_sin_pagina.urlencode(),
        'total': paginador.count,
        'stats': {
            'variables': CVVariable.objects.count(),
            'valores': CVValor.objects.count(),
            'geografias': CVGeografia.objects.count(),
            'areas': CVAreaInformacion.objects.count(),
            'noticias': CVNoticia.objects.count(),
        },
        **_base_gestion_context(request),
        **_contexto_filtros(),
    }
    return render(request, 'validacion/catalogo_variables/index.html', context)


@validador_sistema_required
def gestion_catalogo_variable_crear(request):
    if request.method == 'POST':
        form = CVVariableForm(request.POST)
        if form.is_valid():
            variable = form.save()
            messages.success(request, f'Variable «{variable.id_variable}» creada.')
            return redirect('indicadores:gestion_catalogo_variables')
    else:
        form = CVVariableForm()
    return render(request, 'validacion/catalogo_variables/variable_form.html', {
        'form': form,
        'accion': 'Crear variable',
        **_base_gestion_context(request),
    })


@validador_sistema_required
def gestion_catalogo_variable_editar(request, id_variable):
    variable = get_object_or_404(CVVariable, pk=id_variable)
    if request.method == 'POST':
        form = CVVariableForm(request.POST, instance=variable)
        if form.is_valid():
            form.save()
            messages.success(request, f'Variable «{variable.id_variable}» actualizada.')
            return redirect('indicadores:gestion_catalogo_variables')
    else:
        form = CVVariableForm(instance=variable)
    return render(request, 'validacion/catalogo_variables/variable_form.html', {
        'form': form,
        'variable': variable,
        'accion': f'Editar «{variable.id_variable}»',
        **_base_gestion_context(request),
    })


@validador_sistema_required
def gestion_catalogo_variable_eliminar(request, id_variable):
    variable = get_object_or_404(CVVariable, pk=id_variable)
    if request.method == 'POST':
        vid = variable.id_variable
        variable.delete()
        messages.success(request, f'Variable «{vid}» eliminada con sus valores.')
        return redirect('indicadores:gestion_catalogo_variables')
    return render(request, 'validacion/catalogo_variables/variable_eliminar.html', {
        'variable': variable,
        **_base_gestion_context(request),
    })


@validador_sistema_required
def gestion_catalogo_variable_valores(request, id_variable):
    """Gestión de los valores de dominio de una variable."""
    variable = get_object_or_404(CVVariable, pk=id_variable)

    if request.method == 'POST':
        if 'eliminar_valor' in request.POST:
            valor = get_object_or_404(
                CVValor, pk=request.POST['eliminar_valor'], variable=variable)
            valor.delete()
            messages.success(request, 'Valor eliminado.')
            return redirect('indicadores:gestion_catalogo_variable_valores',
                            id_variable=id_variable)
        form = CVValorForm(request.POST)
        if form.is_valid():
            valor = form.save(commit=False)
            valor.variable = variable
            valor.save()
            messages.success(request, 'Valor agregado.')
            return redirect('indicadores:gestion_catalogo_variable_valores',
                            id_variable=id_variable)
    else:
        form = CVValorForm()

    return render(request, 'validacion/catalogo_variables/variable_valores.html', {
        'variable': variable,
        'valores': variable.valores.all(),
        'form': form,
        **_base_gestion_context(request),
    })


# --- Tablas de referencia (CRUD genérico) ---

TABLAS_REFERENCIA = {
    'areas': (CVAreaInformacion, ['nombre_area', 'descripcion_area']),
    'unidades': (CVUnidadAnalisis, ['nombre_unidad_analisis']),
    'tipos-datos': (CVTipoDato, ['nombre_tipo_dato']),
    'tipos-variables': (CVTipoVariableEstadistica, ['nombre_tipo_variable']),
    'tipos-valores': (CVTipoValoresDominio,
                      ['nombre_tipo_valores_dominio', 'longitud_tipo_valores_dominio']),
    'geografias': (CVGeografia, ['tipo_geografia', 'codigo_geografia',
                                 'geografia_padre', 'nombre_geografia']),
    'noticias': (CVNoticia, ['titulo_noticia', 'anho_noticia', 'fecha_noticia',
                             'texto_noticia', 'carpeta_imagenes_noticia',
                             'imagenes_noticia']),
}


def _modelo_referencia(clave):
    cfg = TABLAS_REFERENCIA.get(clave)
    if not cfg:
        return None, None
    modelo, campos = cfg

    class _Form(forms.ModelForm):
        class Meta:
            model = modelo
            fields = campos
    return modelo, _Form


@validador_sistema_required
def gestion_catalogo_referencia(request, tabla):
    modelo, _ = _modelo_referencia(tabla)
    if not modelo:
        messages.error(request, 'Tabla de referencia desconocida.')
        return redirect('indicadores:gestion_catalogo_variables')

    objetos = modelo.objects.all()
    paginador = Paginator(objetos, 50)
    pagina = paginador.get_page(request.GET.get('page'))

    return render(request, 'validacion/catalogo_variables/referencia_list.html', {
        'tabla': tabla,
        'titulo': modelo._meta.verbose_name_plural,
        'pagina': pagina,
        'total': paginador.count,
        **_base_gestion_context(request),
    })


@validador_sistema_required
def gestion_catalogo_referencia_form(request, tabla, pk=None):
    modelo, form_cls = _modelo_referencia(tabla)
    if not modelo:
        messages.error(request, 'Tabla de referencia desconocida.')
        return redirect('indicadores:gestion_catalogo_variables')

    objeto = get_object_or_404(modelo, pk=pk) if pk else None
    if request.method == 'POST':
        form = form_cls(request.POST, instance=objeto)
        if form.is_valid():
            form.save()
            messages.success(request, 'Registro guardado.')
            return redirect('indicadores:gestion_catalogo_referencia', tabla=tabla)
    else:
        form = form_cls(instance=objeto)

    return render(request, 'validacion/catalogo_variables/referencia_form.html', {
        'tabla': tabla,
        'titulo': modelo._meta.verbose_name_plural,
        'objeto': objeto,
        'form': form,
        **_base_gestion_context(request),
    })


@validador_sistema_required
def gestion_catalogo_referencia_eliminar(request, tabla, pk):
    modelo, _ = _modelo_referencia(tabla)
    if not modelo:
        messages.error(request, 'Tabla de referencia desconocida.')
        return redirect('indicadores:gestion_catalogo_variables')

    objeto = get_object_or_404(modelo, pk=pk)
    if request.method == 'POST':
        try:
            objeto.delete()
            messages.success(request, 'Registro eliminado.')
        except Exception as exc:
            messages.error(
                request,
                f'No se pudo eliminar: hay registros que lo referencian. ({exc})')
        return redirect('indicadores:gestion_catalogo_referencia', tabla=tabla)
    return redirect('indicadores:gestion_catalogo_referencia', tabla=tabla)


# ======================================================================
# OTROS CONJUNTOS DE VARIABLES (públicos)
# ======================================================================

def catalogo_variables_dominios(request):
    """Dominios de desagregación de indicadores como conjunto de variables."""
    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '').strip()

    dominios = DominioDesagregacion.objects.filter(
        en_catalogo=True).annotate(
        n_valores=Count('desagregaciones')).select_related(
        'nivel_geografico', 'dominio_padre')
    if q:
        dominios = dominios.filter(
            Q(nombre__icontains=q) | Q(desagregaciones__nombre__icontains=q)
        ).distinct()
    if tipo in ('tematica', 'geografica'):
        dominios = dominios.filter(tipo=tipo)

    paginador = Paginator(dominios.order_by('tipo', 'nombre'), 30)
    pagina = paginador.get_page(request.GET.get('page'))

    qs = request.GET.copy()
    qs.pop('page', None)

    return render(request, 'catalogo_variables/dominios.html', {
        'pagina': pagina, 'q': q, 'tipo': tipo,
        'qs_base': qs.urlencode(), 'total': paginador.count,
    })


def catalogo_variables_dominio_detalle(request, pk):
    dominio = get_object_or_404(
        DominioDesagregacion.objects.select_related(
            'nivel_geografico', 'dominio_padre').annotate(
            n_valores=Count('desagregaciones')), pk=pk)
    desagregaciones = dominio.desagregaciones.select_related(
        'capa_geo', 'desagregacion_padre').order_by('nombre')
    paginador = Paginator(desagregaciones, 50)
    pagina = paginador.get_page(request.GET.get('page'))
    return render(request, 'catalogo_variables/dominio_detalle.html', {
        'dominio': dominio, 'pagina': pagina,
    })


def catalogo_variables_conjuntos(request):
    """Variables de los conjuntos de datos del SIIED."""
    q = request.GET.get('q', '').strip()
    conjunto_id = request.GET.get('conjunto', '').strip()
    solo_curadas = request.GET.get('curadas') == '1'

    variables = VariableConjuntoDatos.objects.select_related(
        'conjunto_datos', 'organismo_productor')
    if q:
        variables = variables.filter(
            Q(nombre_variable__icontains=q) |
            Q(codigo_variable__icontains=q) |
            Q(definicion_conceptual__icontains=q))
    if conjunto_id.isdigit():
        variables = variables.filter(conjunto_datos_id=int(conjunto_id))
    if solo_curadas:
        # Excluir filas autogeneradas desde headers CSV:
        # su definicion es literal 'Columna "X" del archivo…'
        variables = variables.exclude(
            definicion_conceptual__startswith='Columna "')

    paginador = Paginator(
        variables.order_by('conjunto_datos__nombre', 'orden', 'codigo_variable'),
        POR_PAGINA)
    pagina = paginador.get_page(request.GET.get('page'))

    qs = request.GET.copy()
    qs.pop('page', None)

    return render(request, 'catalogo_variables/conjuntos_vars.html', {
        'pagina': pagina, 'q': q, 'conjunto_id': conjunto_id,
        'solo_curadas': solo_curadas,
        'qs_base': qs.urlencode(), 'total': paginador.count,
        'total_curadas': VariableConjuntoDatos.objects.exclude(
            definicion_conceptual__startswith='Columna "').count(),
        'conjuntos': ConjuntoDatos.objects.annotate(
            n=Count('variables')).order_by('nombre'),
    })


def catalogo_variables_variable_conjunto(request, pk):
    variable = get_object_or_404(
        VariableConjuntoDatos.objects.select_related(
            'conjunto_datos', 'organismo_productor'), pk=pk)
    return render(request, 'catalogo_variables/variable_conjunto.html', {
        'variable': variable,
    })


# ======================================================================
# ECOSISTEMA TALLER + DATA LAKE (solo usuarios autenticados)
# ======================================================================

CAPA_BADGE = {
    'bronce': ('Bronce', 'bg-amber-100 text-amber-800'),
    'plata': ('Plata', 'bg-slate-200 text-slate-700'),
    'gold': ('Gold', 'bg-yellow-100 text-yellow-800'),
}


CAPA_ORDEN = {'bronce': 0, 'plata': 1, 'gold': 2}


@taller_login_required
def catalogo_variables_ecosistema(request):
    """Variables unificadas del Taller de Gestión de Datos — Datalake.

    Agrupa por nombre normalizado (``_norm_var``, el mismo criterio con el
    que el grafo del ecosistema crea las aristas ``matching_variable`` y
    ``variables_compartidas``) las variables reportadas en las fuentes del
    taller y los campos de las bases del Data Lake. Una variable unificada
    puede pertenecer a varias fuentes y a varias bases/dimensiones del
    lake; su calificación (bronce/plata/gold) es la capa más alta de
    todas sus fuentes y dimensiones.
    """
    from collections import Counter
    from .views_taller import _norm_var

    capa = request.GET.get('capa', '').strip()
    origen = request.GET.get('origen', '').strip()  # taller | lake | ambos
    q = request.GET.get('q', '').strip()
    organismo_id = request.GET.get('organismo', '').strip()
    reto_id = request.GET.get('reto', '').strip()
    fuente_id = request.GET.get('fuente', '').strip()

    # --- Campos del Data Lake indexados por nombre normalizado ---
    todos_campos = list(CampoCatalogo.objects.select_related(
        'base', 'base__organismo',
        'base__fuente_origen__inscripcion__organismo'))
    campos_norm = {}  # vnorm -> [CampoCatalogo]
    for c in todos_campos:
        campos_norm.setdefault(_norm_var(c.nombre), []).append(c)

    def _match_campos(vn):
        """Mismo criterio del grafo del ecosistema: exacto normalizado o
        substring en cualquier dirección (mínimo 4 caracteres)."""
        if vn in campos_norm:
            return list(campos_norm[vn])
        if len(vn) < 4:
            return []
        res = []
        for cnorm, clist in campos_norm.items():
            if len(cnorm) >= 4 and (vn in cnorm or cnorm in vn):
                res.extend(clist)
        return res

    # --- Grupos por nombre normalizado ---
    grupos = {}  # vnorm -> {'vars': [...], 'campos': [...]}
    variables = list(VariableFuente.objects.select_related(
        'fuente__inscripcion__organismo',
        'fuente__inscripcion__reto',
        'fuente__base_catalogo').all())
    campos_vistos = set()

    for v in variables:
        vn = _norm_var(v.nombre)
        if not vn:
            continue
        g = grupos.setdefault(vn, {'vars': [], 'campos': []})
        g['vars'].append(v)
        for c in _match_campos(vn):
            if c.pk not in campos_vistos and all(
                    cc.pk != c.pk for cc in g['campos']):
                g['campos'].append(c)
            campos_vistos.add(c.pk)

    # Campos del lake sin variable del taller: grupo propio
    for c in todos_campos:
        vn = _norm_var(c.nombre)
        if not vn:
            continue
        g = grupos.setdefault(vn, {'vars': [], 'campos': []})
        if not any(cc.pk == c.pk for cc in g['campos']):
            g['campos'].append(c)

    # --- Filas unificadas ---
    filas = []
    q_norm = _norm_var(q)
    for vn, g in grupos.items():
        fuentes_unicas = {}
        fuente_ids = set()
        retos_ids = set()
        org_ids = set()
        org_nombres = {}
        for v in g['vars']:
            fte = v.fuente
            fuentes_unicas[fte.pk] = fte
            fuente_ids.add(fte.pk)
            insc = getattr(fte, 'inscripcion', None)
            if insc:
                if insc.organismo_id:
                    org_ids.add(insc.organismo_id)
                    org_nombres[insc.organismo_id] = insc.organismo.nombre
                try:
                    reto = insc.reto  # OneToOne reverso desde RetoAnalisis
                except Exception:
                    reto = None
                if reto:
                    retos_ids.add(reto.pk)
        bases_unicas = {}
        for c in g['campos']:
            bases_unicas[c.base.pk] = c.base
            for oid in (c.base.organismo_id,
                        getattr(c.base.fuente_origen, 'inscripcion', None)
                        and c.base.fuente_origen.inscripcion.organismo_id):
                if oid:
                    org_ids.add(oid)
                    org_nombres.setdefault(
                        oid, c.base.organismo.nombre if c.base.organismo
                        else c.base.get_organismo_display())

        niveles = [CAPA_ORDEN.get(f.capa, 0) for f in fuentes_unicas.values()]
        if g['campos']:
            niveles.append(CAPA_ORDEN['gold'])  # el lake es capa gold
        nivel_max = max(niveles) if niveles else 0
        capa_max = next(k for k, v2 in CAPA_ORDEN.items() if v2 == nivel_max)
        en_taller = bool(g['vars'])
        en_lake = bool(g['campos'])
        origen_fila = ('ambos' if en_taller and en_lake
                       else 'taller' if en_taller else 'lake')
        nombre = (g['vars'][0].nombre if g['vars']
                  else g['campos'][0].nombre)

        # Categoría temática: la más frecuente entre los campos del lake
        # relacionados (CampoCatalogo.categoria); sin match → 'Sin categoría'.
        cats = [c.categoria for c in g['campos'] if c.categoria]
        categoria = (Counter(cats).most_common(1)[0][0] if cats
                     else 'Sin categoría temática')

        filas.append({
            'vn': vn, 'nombre': nombre, 'vars': g['vars'],
            'campos': g['campos'],
            'fuentes': sorted(fuentes_unicas.values(),
                              key=lambda f: f.nombre),
            'bases': sorted(bases_unicas.values(), key=lambda b: b.slug),
            'fuente_ids': fuente_ids, 'reto_ids': retos_ids,
            'org_ids': org_ids, 'org_nombres': sorted(org_nombres.values()),
            'capa_max': capa_max, 'nivel': nivel_max, 'origen': origen_fila,
            'categoria': categoria,
        })

    # --- Filtros sobre la fila unificada (muestra TODOS sus miembros) ---
    def _pasa(f):
        if capa in CAPA_BADGE and f['capa_max'] != capa:
            return False
        if origen == 'taller' and not f['vars']:
            return False
        if origen == 'lake' and not f['campos']:
            return False
        if origen == 'ambos' and f['origen'] != 'ambos':
            return False
        if organismo_id.isdigit() and int(organismo_id) not in f['org_ids']:
            return False
        if fuente_id.isdigit() and int(fuente_id) not in f['fuente_ids']:
            return False
        if reto_id.isdigit() and int(reto_id) not in f['reto_ids']:
            return False
        if q:
            hay_pila = [f['vn'], f['nombre']]
            hay_pila += [v.nombre + ' ' + (v.descripcion or '')
                         + ' ' + v.fuente.nombre for v in f['vars']]
            hay_pila += [c.nombre + ' ' + (c.descripcion or '')
                         + ' ' + c.base.nombre + ' ' + c.base.slug
                         for c in f['campos']]
            if not any(q.lower() in h.lower() or
                       (q_norm and q_norm in _norm_var(h))
                       for h in hay_pila):
                return False
        return True

    filas = [f for f in filas if _pasa(f)]
    filas.sort(key=lambda f: (f['categoria'], -f['nivel'],
                              f['nombre'].lower()))

    # Secciones por categoría temática (desplegables); 'Sin categoría' al final
    por_cat = {}
    for f in filas:
        por_cat.setdefault(f['categoria'], []).append(f)
    secciones = [
        {'categoria': cat, 'filas': fs}
        for cat, fs in sorted(
            por_cat.items(),
            key=lambda kv: (kv[0] == 'Sin categoría temática', kv[0]))
    ]

    qs = request.GET.copy()
    qs.pop('page', None)

    # Filtros auxiliares
    fuentes = FuenteDatos.objects.select_related(
        'inscripcion__organismo').order_by('nombre')
    retos = RetoAnalisis.objects.filter(
        fusionado_en__isnull=True).select_related(
        'inscripcion__organismo').order_by('nombre')
    organismos = (Organismo.objects.filter(
        inscripciones_taller__isnull=False).distinct().order_by('nombre'))

    return render(request, 'catalogo_variables/ecosistema.html', {
        'secciones': secciones, 'qs_base': qs.urlencode(),
        'total': len(filas),
        'capa': capa, 'origen': origen, 'q': q,
        'organismo_id': organismo_id, 'reto_id': reto_id, 'fuente_id': fuente_id,
        'fuentes': fuentes, 'retos': retos, 'organismos': organismos,
        'capa_badge': CAPA_BADGE,
        'stats': {
            'taller': VariableFuente.objects.count(),
            'lake': CampoCatalogo.objects.count(),
            'fuentes': FuenteDatos.objects.count(),
            'bases': BaseCatalogo.objects.count(),
            'unificadas': len(grupos),
        },
    })


@taller_login_required
def catalogo_variables_ecosistema_fuente(request, pk):
    """Detalle de una variable del taller con todas sus conexiones."""
    variable = get_object_or_404(
        VariableFuente.objects.select_related(
            'fuente__inscripcion__organismo',
            'fuente__inscripcion__reto',
            'fuente__base_catalogo',
            'fuente__fusionada_en'), pk=pk)
    fuente = variable.fuente
    inscripcion = fuente.inscripcion
    try:
        reto = inscripcion.reto
    except Exception:
        reto = None
    base_gold = fuente.base_catalogo
    campos_match = []
    if base_gold:
        campos_match = base_gold.campos.filter(
            nombre__iexact=variable.nombre)
    return render(request, 'catalogo_variables/ecosistema_fuente.html', {
        'variable': variable, 'fuente': fuente, 'inscripcion': inscripcion,
        'reto': reto, 'base_gold': base_gold, 'campos_match': campos_match,
        'capa_badge': CAPA_BADGE,
    })


@taller_login_required
def catalogo_variables_ecosistema_campo(request, pk):
    """Detalle de un campo del Data Lake y su trazabilidad al taller."""
    campo = get_object_or_404(
        CampoCatalogo.objects.select_related(
            'base', 'base__organismo',
            'base__fuente_origen__inscripcion__organismo',
            'base__fuente_origen__inscripcion__reto',
            'base__operacion'), pk=pk)
    base = campo.base
    fuente = base.fuente_origen
    inscripcion = fuente.inscripcion if fuente else None
    try:
        reto = inscripcion.reto if inscripcion else None
    except Exception:
        reto = None
    # Variables del taller de la fuente origen que podrían mapear a este campo
    variables_match = []
    if fuente:
        variables_match = fuente.variables.filter(nombre__iexact=campo.nombre)
    return render(request, 'catalogo_variables/ecosistema_campo.html', {
        'campo': campo, 'base': base, 'fuente': fuente,
        'inscripcion': inscripcion, 'reto': reto,
        'variables_match': variables_match,
        'capa_badge': CAPA_BADGE,
    })
