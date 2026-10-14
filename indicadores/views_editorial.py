"""
Vistas del Módulo Editorial
Sistema de gestión de contenidos para editores estadísticos del SIIED
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.db.models import Count, Q
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
from indicadores.decorators import editor_required
from indicadores.models import (
    ProductoAcademico, ProductoEducativo, SeccionPaper, SeccionEducativa,
    Evento, CalendarioDifusion, NoticiaBanner, EstadisticaNoticia, EnlaceNoticia,
    Indicador, Organismo, Grafico, GraficoSerie, Desagregacion,
    CategoriaInformacion, SistemaInformacion,
    CategoriaProyecto, ProyectoInformacion,
    AreaInfraestructura, CategoriaInfraestructura,
    SubcategoriaInfraestructura, GrupoDocumento,
    DocumentoInfraestructura,
    CatalogoConsulta, MenuDominio
)
from indicadores.forms_editorial import (
    EventoForm, NoticiaBannerForm, CalendarioDifusionForm,
    EstadisticaNoticiaFormSet, EnlaceNoticiaFormSet,
    CategoriaInformacionForm, SistemaInformacionForm,
    CategoriaProyectoForm, ProyectoInformacionForm,
    DocumentoInfraestructuraForm,
    AreaInfraestructuraForm, CategoriaInfraestructuraForm,
    SubcategoriaInfraestructuraForm, GrupoDocumentoForm,
    GraficoForm, GraficoSerieFormSet,
    SectionGraficoConfigForm,
    CatalogoConsultaForm, CatalogoConsultaEnlazarIndicadoresForm
)

import logging
logger = logging.getLogger(__name__)


# ============================================================================
# AUTENTICACIÓN
# ============================================================================

def editorial_login(request):
    """Vista de login para el módulo editorial"""
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('indicadores:editorial_dashboard')
        elif hasattr(request.user, 'perfil_recolector') and request.user.perfil_recolector.puede_editar_contenidos():
            return redirect('indicadores:editorial_dashboard')
        else:
            auth_logout(request)
            messages.warning(request, 'No tiene permisos para acceder al módulo editorial. Por favor inicie sesión con una cuenta autorizada.')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_staff:
                auth_login(request, user)
                messages.success(request, f'Bienvenido Administrador {user.get_full_name() or user.username}')
                return redirect('indicadores:editorial_dashboard')
            elif hasattr(user, 'perfil_recolector') and user.perfil_recolector.puede_editar_contenidos():
                auth_login(request, user)
                messages.success(request, f'Bienvenido {user.get_full_name() or user.username}')
                return redirect('indicadores:editorial_dashboard')
            else:
                messages.error(request, 'No tiene permisos para acceder al módulo editorial o su cuenta está inactiva')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos')

    return render(request, 'editorial/login.html')


def editorial_logout(request):
    """Vista de logout para el módulo editorial"""
    auth_logout(request)
    messages.success(request, 'Sesión cerrada exitosamente')
    return redirect('indicadores:editorial_login')


@editor_required
def editorial_manual(request):
    """Manual de uso del módulo editorial"""
    return render(request, 'editorial/manual.html')


# ============================================================================
# DASHBOARD EDITORIAL
# ============================================================================

@editor_required
def editorial_dashboard(request):
    """Dashboard principal del módulo editorial"""
    
    # Estadísticas de productos académicos
    productos_stats = {
        'total': ProductoAcademico.objects.count(),
        'publicados': ProductoAcademico.objects.filter(estado='publicado').count(),
        'borradores': ProductoAcademico.objects.filter(estado='borrador').count(),
        'en_revision': ProductoAcademico.objects.filter(estado='revision').count(),
    }
    
    # Productos educativos
    educativos_stats = {
        'total': ProductoEducativo.objects.count(),
        'infantiles': ProductoEducativo.objects.filter(publico='infantil').count(),
        'adolescentes': ProductoEducativo.objects.filter(publico='adolescente').count(),
    }
    
    # Eventos próximos
    now = timezone.now()
    eventos_proximos = Evento.objects.filter(
        fecha_inicio__gte=now,
        activo=True
    ).order_by('fecha_inicio')[:5]
    
    # Calendario de difusión (próximas publicaciones)
    calendario_stats = {
        'total': CalendarioDifusion.objects.filter(activo=True).count(),
        'por_organismo': CalendarioDifusion.objects.filter(activo=True).values('organismo__nombre').annotate(count=Count('id')).order_by('-count')[:5]
    }
    
    # Noticias activas
    noticias_stats = {
        'total': NoticiaBanner.objects.count(),
        'activas': NoticiaBanner.objects.filter(activa=True).count(),
        'recientes': NoticiaBanner.objects.filter(activa=True).order_by('-fecha_publicacion')[:5]
    }
    
    # Productos recientes (últimos 10)
    productos_recientes = ProductoAcademico.objects.all().order_by('-updated_at')[:10]
    
    # Sistemas de información
    sistemas_stats = {
        'total': SistemaInformacion.objects.count(),
        'activos': SistemaInformacion.objects.filter(activo=True).count(),
        'categorias': CategoriaInformacion.objects.filter(activo=True).count(),
    }
    
    # Productos de información
    proyectos_info_stats = {
        'total': ProyectoInformacion.objects.count(),
        'activos': ProyectoInformacion.objects.filter(activo=True, estado='activo').count(),
        'categorias': CategoriaProyecto.objects.filter(activo=True).count(),
    }
    
    # Documentos de infraestructura
    documentos_stats = {
        'total': DocumentoInfraestructura.objects.count(),
        'publicados': DocumentoInfraestructura.objects.filter(estado='publicado').count(),
        'borradores': DocumentoInfraestructura.objects.filter(estado='borrador').count(),
    }
    
    context = {
        'productos_stats': productos_stats,
        'educativos_stats': educativos_stats,
        'eventos_proximos': eventos_proximos,
        'calendario_stats': calendario_stats,
        'noticias_stats': noticias_stats,
        'productos_recientes': productos_recientes,
        'sistemas_stats': sistemas_stats,
        'proyectos_info_stats': proyectos_info_stats,
        'documentos_stats': documentos_stats,
    }
    
    return render(request, 'editorial/dashboard.html', context)


# ============================================================================
# PRODUCTOS ACADÉMICOS
# ============================================================================

@editor_required
def productos_listado(request):
    """Listado de productos académicos con filtros"""
    
    productos = ProductoAcademico.objects.all().order_by('-updated_at')
    
    # Filtros
    estado = request.GET.get('estado')
    if estado:
        productos = productos.filter(estado=estado)
    
    tipo = request.GET.get('tipo')
    if tipo == 'educativo':
        productos_educativos = ProductoEducativo.objects.all().order_by('-updated_at')
        context = {
            'productos': productos_educativos,
            'tipo_filtro': tipo,
            'es_educativo': True,
        }
        return render(request, 'editorial/productos_listado.html', context)
    
    context = {
        'productos': productos,
        'estado_filtro': estado,
        'tipo_filtro': tipo,
        'es_educativo': False,
    }
    
    return render(request, 'editorial/productos_listado.html', context)


@editor_required
def productos_wizard(request):
    """Wizard paso a paso para crear productos académicos"""
    
    # Obtener paso actual (default: 1, rango válido: 1-4)
    try:
        paso = int(request.GET.get('paso', 1))
        if paso < 1 or paso > 4:
            paso = 1
    except (ValueError, TypeError):
        paso = 1
    
    # Datos guardados en sesión
    wizard_data = request.session.get('wizard_producto', {})
    
    if request.method == 'POST':
        # Guardar datos del paso actual
        if paso == 1:
            wizard_data['tipo_producto'] = request.POST.get('tipo_producto')
            wizard_data['titulo'] = request.POST.get('titulo')
            wizard_data['slug'] = request.POST.get('slug')
            wizard_data['autor'] = request.POST.get('autor')
            wizard_data['institucion'] = request.POST.get('institucion', '')
            wizard_data['publico'] = request.POST.get('publico', 'infantil')
            request.session['wizard_producto'] = wizard_data
            return redirect(f"{request.path}?paso=2")
        
        elif paso == 2:
            # Selección de indicadores
            wizard_data['indicadores'] = request.POST.getlist('indicadores')
            request.session['wizard_producto'] = wizard_data
            return redirect(f"{request.path}?paso=3")
        
        elif paso == 3:
            # Selección de plantilla
            wizard_data['plantilla'] = request.POST.get('plantilla')
            request.session['wizard_producto'] = wizard_data
            return redirect(f"{request.path}?paso=4")
        
        elif paso == 4:
            # Confirmación y creación
            if not wizard_data.get('titulo') or not wizard_data.get('slug'):
                messages.error(request, 'Faltan datos obligatorios del producto. Por favor complete el paso 1.')
                return redirect(f"{request.path}?paso=1")

            try:
                producto = crear_producto_desde_wizard(wizard_data, request.user)
                request.session.pop('wizard_producto', None)
                messages.success(request, f'Producto "{producto.titulo}" creado exitosamente.')
                return redirect('indicadores:editorial_producto_editar', slug=producto.slug)
            except Exception as e:
                messages.error(request, f'Error al crear producto: {str(e)}')
    
    context = {
        'paso': paso,
        'wizard_data': wizard_data,
        'total_pasos': 4,
    }
    
    # Cargar datos específicos del paso
    if paso == 2:
        context['indicadores'] = Indicador.objects.filter(activo=True).order_by('nombre')
    elif paso == 3:
        context['plantillas'] = [
            {'id': 'censo', 'nombre': 'Censo/Encuesta', 'descripcion': 'Producto estadístico oficial'},
            {'id': 'paper', 'nombre': 'Paper Académico', 'descripcion': 'Estructura académica clásica'},
            {'id': 'informe', 'nombre': 'Informe Ejecutivo', 'descripcion': 'Para tomadores de decisión'},
            {'id': 'infantil', 'nombre': 'Educativo Infantil', 'descripcion': 'Niños 6-11 años'},
            {'id': 'adolescente', 'nombre': 'Educativo Adolescente', 'descripcion': 'Adolescentes 12-17 años'},
        ]
    
    return render(request, 'editorial/productos_wizard.html', context)


@editor_required
def producto_editar(request, slug):
    """Editar un producto académico existente"""
    # Intentar ProductoAcademico primero, luego ProductoEducativo
    producto = ProductoAcademico.objects.filter(slug=slug).first()
    es_educativo = False
    if not producto:
        producto = get_object_or_404(ProductoEducativo, slug=slug)
        es_educativo = True
    
    # TODO: Implementar formulario de edición
    context = {
        'producto': producto,
        'es_educativo': es_educativo,
    }
    
    return render(request, 'editorial/producto_editar.html', context)


@editor_required
def producto_secciones(request, slug):
    """Gestionar secciones de un producto"""
    # Intentar ProductoAcademico primero, luego ProductoEducativo
    producto = ProductoAcademico.objects.filter(slug=slug).first()
    es_educativo = False
    if not producto:
        producto = get_object_or_404(ProductoEducativo, slug=slug)
        es_educativo = True
    
    secciones = producto.secciones.all().order_by('numero_orden', 'subnumero')
    
    context = {
        'producto': producto,
        'secciones': secciones,
        'es_educativo': es_educativo,
    }
    
    return render(request, 'editorial/producto_secciones.html', context)


@editor_required
def editorial_seccion_grafico(request, seccion_id):
    """
    Configura el gráfico embebido de una sección de producto académico.
    Guarda la configuración en seccion.configuracion_grafico como JSON.
    """
    from .models import SeccionPaper
    seccion = get_object_or_404(SeccionPaper, id=seccion_id)
    producto = seccion.producto
    indicador = seccion.indicador_vinculado

    if not indicador:
        messages.error(request, 'Esta sección no tiene un indicador vinculado. Primero vincule un indicador desde el admin.')
        return redirect('indicadores:editorial_producto_secciones', slug=producto.slug)

    config_actual = seccion.configuracion_grafico or {}
    if isinstance(config_actual, str):
        try:
            config_actual = json.loads(config_actual) if config_actual.strip() else {}
        except (json.JSONDecodeError, ValueError):
            config_actual = {}

    if request.method == 'POST':
        form = SectionGraficoConfigForm(request.POST, indicador=indicador)
        if form.is_valid():
            nueva_config = form.to_config()
            seccion.configuracion_grafico = nueva_config
            seccion.save(update_fields=['configuracion_grafico'])
            messages.success(request, 'Configuración del gráfico guardada.')
            return redirect('indicadores:editorial_producto_secciones', slug=producto.slug)
    else:
        form = SectionGraficoConfigForm(indicador=indicador)
        if config_actual:
            form.from_config(config_actual)

    # Desagregaciones disponibles para el indicador (para el UI de series)
    desagregaciones_geo = list(Desagregacion.objects.filter(
        dominio__in=indicador.dominios_desagregacion_geografica.all()
    ).distinct().values('id', 'nombre'))
    desagregaciones_tem = list(Desagregacion.objects.filter(
        dominio__in=indicador.dominios_desagregacion_tematica.all()
    ).distinct().values('id', 'nombre'))

    context = {
        'seccion': seccion,
        'producto': producto,
        'indicador': indicador,
        'form': form,
        'config_json': json.dumps(config_actual, ensure_ascii=False),
        'desagregaciones_geo': desagregaciones_geo,
        'desagregaciones_tem': desagregaciones_tem,
        'tipos_grafico': SectionGraficoConfigForm.TIPO_GRAFICO_CHOICES,
    }
    return render(request, 'editorial/seccion_grafico_config.html', context)


@editor_required
def producto_preview(request, slug):
    """Preview del producto antes de publicar"""
    # Intentar ProductoAcademico primero, luego ProductoEducativo
    producto = ProductoAcademico.objects.filter(slug=slug).first()
    if producto:
        return redirect('indicadores:producto_academico', slug=slug)
    
    producto = get_object_or_404(ProductoEducativo, slug=slug)
    return redirect('indicadores:producto_educativo', slug=slug)


# ============================================================================
# EVENTOS
# ============================================================================

@editor_required
def eventos_listado(request):
    """Listado de eventos"""
    eventos = Evento.objects.all().order_by('-fecha_inicio')
    
    # Filtro por estado
    estado = request.GET.get('estado')
    now = timezone.now()
    if estado == 'proximos':
        eventos = eventos.filter(fecha_inicio__gte=now, activo=True)
    elif estado == 'pasados':
        eventos = eventos.filter(fecha_fin__lt=now)
    elif estado == 'activos':
        eventos = eventos.filter(activo=True)
    
    context = {
        'eventos': eventos,
        'estado_filtro': estado,
    }
    
    return render(request, 'editorial/eventos_listado.html', context)


@editor_required
def eventos_calendario(request):
    """Vista de calendario visual de eventos"""
    from datetime import datetime
    import calendar
    
    # Obtener mes y año actual o del query string
    mes = int(request.GET.get('mes', datetime.now().month))
    anio = int(request.GET.get('anio', datetime.now().year))
    
    # Obtener eventos del mes
    eventos = Evento.objects.filter(
        fecha_inicio__year=anio,
        fecha_inicio__month=mes,
        activo=True
    ).order_by('fecha_inicio')
    
    # Preparar datos para el calendario
    cal = calendar.monthcalendar(anio, mes)
    
    # Agrupar eventos por día
    eventos_por_dia = {}
    for evento in eventos:
        dia = evento.fecha_inicio.day
        if dia not in eventos_por_dia:
            eventos_por_dia[dia] = []
        eventos_por_dia[dia].append(evento)
    
    context = {
        'mes': mes,
        'anio': anio,
        'calendario': cal,
        'eventos_por_dia': eventos_por_dia,
        'mes_nombre': calendar.month_name[mes],
    }
    
    return render(request, 'editorial/eventos_calendario.html', context)


@editor_required
def evento_crear(request):
    """Crear un nuevo evento"""
    if request.method == 'POST':
        form = EventoForm(request.POST, request.FILES)
        if form.is_valid():
            evento = form.save()
            messages.success(request, f'Evento "{evento.nombre}" creado exitosamente.')
            return redirect('indicadores:editorial_eventos')
    else:
        form = EventoForm()
    
    context = {'form': form}
    return render(request, 'editorial/evento_form.html', context)


@editor_required
def evento_editar(request, pk):
    """Editar un evento existente"""
    evento = get_object_or_404(Evento, pk=pk)
    
    if request.method == 'POST':
        form = EventoForm(request.POST, request.FILES, instance=evento)
        if form.is_valid():
            form.save()
            messages.success(request, f'Evento "{evento.nombre}" actualizado exitosamente.')
            return redirect('indicadores:editorial_eventos')
    else:
        form = EventoForm(instance=evento)
    
    context = {'form': form, 'evento': evento}
    return render(request, 'editorial/evento_form.html', context)


@editor_required
def evento_eliminar(request, pk):
    """Eliminar un evento"""
    evento = get_object_or_404(Evento, pk=pk)
    if request.method == 'POST':
        evento.delete()
        messages.success(request, f'Evento "{evento.nombre}" eliminado exitosamente.')
        return redirect('indicadores:editorial_eventos')
    
    context = {'evento': evento}
    return render(request, 'editorial/evento_confirmar_eliminar.html', context)


# ============================================================================
# CALENDARIO DE DIFUSIÓN
# ============================================================================

@editor_required
def calendario_difusion_listado(request):
    """Listado del calendario de difusión"""
    calendario = CalendarioDifusion.objects.all().order_by('organismo__nombre', 'producto')
    
    # Filtro por organismo
    organismo_id = request.GET.get('organismo')
    if organismo_id:
        calendario = calendario.filter(organismo_id=organismo_id)
    
    organismos = Organismo.objects.all().order_by('nombre')
    
    context = {
        'calendario': calendario,
        'organismos': organismos,
        'organismo_filtro': organismo_id,
    }
    
    return render(request, 'editorial/calendario_difusion_listado.html', context)


@editor_required
def calendario_difusion_crear(request):
    """Crear entrada en calendario de difusión"""
    if request.method == 'POST':
        form = CalendarioDifusionForm(request.POST)
        if form.is_valid():
            entrada = form.save()
            messages.success(request, f'Producto "{entrada.producto}" agregado al calendario.')
            return redirect('indicadores:editorial_calendario_difusion')
    else:
        form = CalendarioDifusionForm()
    
    context = {'form': form}
    return render(request, 'editorial/calendario_difusion_form.html', context)


@editor_required
def calendario_difusion_editar(request, pk):
    """Editar entrada del calendario"""
    entrada = get_object_or_404(CalendarioDifusion, pk=pk)
    
    if request.method == 'POST':
        form = CalendarioDifusionForm(request.POST, instance=entrada)
        if form.is_valid():
            form.save()
            messages.success(request, f'Producto "{entrada.producto}" actualizado exitosamente.')
            return redirect('indicadores:editorial_calendario_difusion')
    else:
        form = CalendarioDifusionForm(instance=entrada)
    
    context = {'form': form, 'entrada': entrada}
    return render(request, 'editorial/calendario_difusion_form.html', context)


@editor_required
def calendario_difusion_exportar(request):
    """Exportar calendario de difusión"""
    # TODO: Implementar exportación a Excel/PDF
    messages.info(request, 'Exportación en desarrollo.')
    return redirect('indicadores:editorial_calendario_difusion')


# ============================================================================
# NOTICIAS
# ============================================================================

@editor_required
def noticias_listado(request):
    """Listado de noticias con filtros"""
    noticias = NoticiaBanner.objects.all().order_by('-orden', '-fecha_publicacion')
    
    # Filtros
    estado = request.GET.get('estado')
    if estado == 'activas':
        noticias = noticias.filter(activa=True)
    elif estado == 'inactivas':
        noticias = noticias.filter(activa=False)
    
    context = {
        'noticias': noticias,
        'estado_filtro': estado,
    }
    
    return render(request, 'editorial/noticias_listado.html', context)


@editor_required
def noticia_crear(request):
    """Crear una nueva noticia"""
    if request.method == 'POST':
        form = NoticiaBannerForm(request.POST, request.FILES)
        estadisticas_formset = EstadisticaNoticiaFormSet(request.POST, prefix='estadisticas')
        enlaces_formset = EnlaceNoticiaFormSet(request.POST, prefix='enlaces')
        
        if form.is_valid() and estadisticas_formset.is_valid() and enlaces_formset.is_valid():
            noticia = form.save()
            
            # Guardar estadísticas
            estadisticas = estadisticas_formset.save(commit=False)
            for estadistica in estadisticas:
                estadistica.noticia = noticia
                estadistica.save()
            
            # Guardar enlaces
            enlaces = enlaces_formset.save(commit=False)
            for enlace in enlaces:
                enlace.noticia = noticia
                enlace.save()
            
            messages.success(request, f'Noticia "{noticia.titulo}" creada exitosamente.')
            return redirect('indicadores:editorial_noticias')
    else:
        form = NoticiaBannerForm()
        estadisticas_formset = EstadisticaNoticiaFormSet(prefix='estadisticas')
        enlaces_formset = EnlaceNoticiaFormSet(prefix='enlaces')
    
    context = {
        'form': form,
        'estadisticas_formset': estadisticas_formset,
        'enlaces_formset': enlaces_formset
    }
    return render(request, 'editorial/noticia_form.html', context)


@editor_required
@require_http_methods(['POST'])
def noticia_generar_ia(request):
    """Genera los campos de una noticia a partir de un prompt libre (LLM).

    No persiste nada: devuelve el JSON de campos para que el formulario
    se precargue y el editor revise/ajuste antes de guardar.
    """
    from .llm_structured import NOTICIA_SCHEMA, NOTICIA_SYSTEM_PROMPT

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Cuerpo JSON inválido.'}, status=400)

    prompt = (payload.get('prompt') or '').strip()
    if len(prompt) < 10:
        return JsonResponse(
            {'error': 'Describe la noticia con al menos una frase.'},
            status=400)
    if len(prompt) > 4000:
        return JsonResponse(
            {'error': 'La descripción es demasiado larga (máx. 4000 caracteres).'},
            status=400)

    # Importación perezosa: views_chat arrastra dependencias pesadas
    from .views_chat import ChatService
    try:
        data = ChatService(request=request).generate_structured(
            prompt, NOTICIA_SCHEMA,
            system_prompt=NOTICIA_SYSTEM_PROMPT,
            schema_name='noticia_banner')
    except Exception as e:
        logger.error(f'Error generando noticia con IA: {e}')
        return JsonResponse(
            {'error': 'El asistente no pudo generar la noticia. '
                      'Inténtalo de nuevo en unos segundos.'},
            status=502)

    try:
        orden = int(data.get('orden'))
    except (TypeError, ValueError):
        orden = 5

    # Sanitizar a los campos que el formulario espera
    noticia = {
        'titulo': str(data.get('titulo') or '')[:255],
        'subtitulo': str(data.get('subtitulo') or '')[:255],
        'descripcion': str(data.get('descripcion') or ''),
        'enlace_principal': str(data.get('enlace_principal') or ''),
        'texto_enlace_principal':
            str(data.get('texto_enlace_principal') or 'Leer más')[:100],
        'imagen_url': str(data.get('imagen_url') or ''),
        'sugerencia_imagen': str(data.get('sugerencia_imagen') or ''),
        'orden': max(0, min(10, orden)),
        'estadisticas': [
            {
                'titulo': str(est.get('titulo') or '')[:100],
                'valor': str(est.get('valor') or '')[:50],
                'descripcion': str(est.get('descripcion') or '')[:255],
            }
            for est in (data.get('estadisticas') or [])[:4]
            if isinstance(est, dict)
        ],
        'enlaces': [
            {
                'titulo': str(enl.get('titulo') or '')[:100],
                'url': str(enl.get('url') or ''),
                'descripcion': str(enl.get('descripcion') or '')[:255],
            }
            for enl in (data.get('enlaces') or [])[:4]
            if isinstance(enl, dict)
        ],
    }
    return JsonResponse({'ok': True, 'noticia': noticia})


@editor_required
def noticia_editar(request, pk):
    """Editar una noticia existente"""
    noticia = get_object_or_404(NoticiaBanner, pk=pk)
    
    if request.method == 'POST':
        form = NoticiaBannerForm(request.POST, request.FILES, instance=noticia)
        estadisticas_formset = EstadisticaNoticiaFormSet(request.POST, instance=noticia, prefix='estadisticas')
        enlaces_formset = EnlaceNoticiaFormSet(request.POST, instance=noticia, prefix='enlaces')
        
        if form.is_valid() and estadisticas_formset.is_valid() and enlaces_formset.is_valid():
            form.save()
            estadisticas_formset.save()
            enlaces_formset.save()
            
            messages.success(request, f'Noticia "{noticia.titulo}" actualizada exitosamente.')
            return redirect('indicadores:editorial_noticias')
    else:
        form = NoticiaBannerForm(instance=noticia)
        estadisticas_formset = EstadisticaNoticiaFormSet(instance=noticia, prefix='estadisticas')
        enlaces_formset = EnlaceNoticiaFormSet(instance=noticia, prefix='enlaces')
    
    context = {
        'form': form,
        'noticia': noticia,
        'estadisticas_formset': estadisticas_formset,
        'enlaces_formset': enlaces_formset
    }
    return render(request, 'editorial/noticia_form.html', context)


@editor_required
def noticia_eliminar(request, pk):
    """Eliminar una noticia"""
    noticia = get_object_or_404(NoticiaBanner, pk=pk)
    if request.method == 'POST':
        noticia.delete()
        messages.success(request, f'Noticia "{noticia.titulo}" eliminada exitosamente.')
        return redirect('indicadores:editorial_noticias')
    
    context = {'noticia': noticia}
    return render(request, 'editorial/noticia_confirmar_eliminar.html', context)


@editor_required
def noticia_preview(request, pk):
    """Preview de la noticia"""
    noticia = get_object_or_404(NoticiaBanner, pk=pk)
    context = {'noticia': noticia}
    return render(request, 'editorial/noticia_preview.html', context)


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def crear_producto_desde_wizard(wizard_data, user):
    """Crea un producto académico o educativo a partir de los datos del wizard"""
    tipo = wizard_data.get('tipo_producto')
    plantilla = wizard_data.get('plantilla')

    # Crear producto base
    if tipo == 'educativo':
        publico = wizard_data.get('publico', 'infantil')
        producto = ProductoEducativo.objects.create(
            titulo=wizard_data['titulo'],
            slug=wizard_data['slug'],
            autor=wizard_data['autor'],
            publico=publico,
            estado='borrador',
        )
    else:
        producto = ProductoAcademico.objects.create(
            titulo=wizard_data['titulo'],
            slug=wizard_data['slug'],
            autor=wizard_data['autor'],
            institucion=wizard_data.get('institucion', ''),
            es_producto_estadistico=(plantilla == 'censo'),
            estado='borrador',
        )

    # Vincular indicadores (solo ProductoAcademico tiene M2M indicadores_derivados)
    indicadores_ids = wizard_data.get('indicadores', [])
    if indicadores_ids and hasattr(producto, 'indicadores_derivados'):
        indicadores = Indicador.objects.filter(id__in=indicadores_ids)
        producto.indicadores_derivados.set(indicadores)
    else:
        indicadores = []

    # Crear secciones según plantilla y tipo de producto
    crear_secciones_desde_plantilla(producto, tipo, plantilla, list(indicadores) if indicadores_ids else [])

    return producto


def crear_secciones_desde_plantilla(producto, tipo, plantilla, indicadores):
    """Crea secciones predefinidas según la plantilla y tipo de producto seleccionado"""
    if tipo == 'educativo':
        _crear_secciones_educativas(producto, plantilla, indicadores)
    else:
        _crear_secciones_academicas(producto, plantilla, indicadores)


def _crear_secciones_academicas(producto, plantilla, indicadores):
    """Crea SeccionPaper para productos académicos"""
    if plantilla == 'censo':
        secciones = [
            {'numero_orden': 1, 'tipo_seccion': 'resumen', 'tipo_bloque': 'texto', 'titulo': 'Resumen ejecutivo'},
            {'numero_orden': 2, 'tipo_seccion': 'introduccion', 'tipo_bloque': 'texto', 'titulo': 'Introducción'},
            {'numero_orden': 3, 'tipo_seccion': 'resultados', 'tipo_bloque': 'resultado_destacado', 'titulo': 'Resultado destacado', 'indicador': indicadores[0] if indicadores else None},
            {'numero_orden': 4, 'tipo_seccion': 'resultados', 'tipo_bloque': 'grafico_indicador', 'titulo': 'Gráfico principal', 'indicador': indicadores[0] if indicadores else None, 'config': {'tipo': 'barras'}},
            {'numero_orden': 5, 'tipo_seccion': 'metodologia', 'tipo_bloque': 'texto', 'titulo': 'Metodología'},
        ]
    elif plantilla == 'paper':
        secciones = [
            {'numero_orden': 1, 'tipo_seccion': 'resumen', 'tipo_bloque': 'texto', 'titulo': 'Abstract'},
            {'numero_orden': 2, 'tipo_seccion': 'introduccion', 'tipo_bloque': 'texto', 'titulo': '1. Introducción'},
            {'numero_orden': 3, 'tipo_seccion': 'antecedentes', 'tipo_bloque': 'texto', 'titulo': '2. Marco teórico'},
            {'numero_orden': 4, 'tipo_seccion': 'metodologia', 'tipo_bloque': 'texto', 'titulo': '3. Metodología'},
            {'numero_orden': 5, 'tipo_seccion': 'resultados', 'tipo_bloque': 'texto', 'titulo': '4. Resultados'},
            {'numero_orden': 6, 'tipo_seccion': 'discusion', 'tipo_bloque': 'texto', 'titulo': '5. Discusión'},
            {'numero_orden': 7, 'tipo_seccion': 'conclusiones', 'tipo_bloque': 'texto', 'titulo': '6. Conclusiones'},
        ]
    else:
        # Plantilla informe u otra básica
        secciones = [
            {'numero_orden': 1, 'tipo_seccion': 'resumen', 'tipo_bloque': 'texto', 'titulo': 'Resumen'},
            {'numero_orden': 2, 'tipo_seccion': 'introduccion', 'tipo_bloque': 'texto', 'titulo': 'Introducción'},
            {'numero_orden': 3, 'tipo_seccion': 'resultados', 'tipo_bloque': 'texto', 'titulo': 'Resultados'},
        ]

    for seccion_data in secciones:
        indicador = seccion_data.pop('indicador', None)
        config = seccion_data.pop('config', None)

        SeccionPaper.objects.create(
            producto=producto,
            indicador_vinculado=indicador,
            configuracion_grafico=config,
            **seccion_data
        )


def _crear_secciones_educativas(producto, plantilla, indicadores):
    """Crea SeccionEducativa para productos educativos"""
    secciones = [
        {'numero_orden': 1, 'titulo': 'Bienvenida', 'tipo_bloque': 'narrativa_guiada', 'icono_emoji': '👋'},
        {'numero_orden': 2, 'titulo': '¿Qué son los datos?', 'tipo_bloque': 'texto_adaptado', 'icono_emoji': '📊'},
        {'numero_orden': 3, 'titulo': 'Explora el indicador', 'tipo_bloque': 'dato_interactivo', 'icono_emoji': '🔍'},
        {'numero_orden': 4, 'titulo': 'Descubre más', 'tipo_bloque': 'grafico_interactivo', 'icono_emoji': '📈'},
        {'numero_orden': 5, 'titulo': 'Pon a prueba tu conocimiento', 'tipo_bloque': 'quiz_recompensa', 'icono_emoji': '🎯'},
        {'numero_orden': 6, 'titulo': 'Reto final', 'tipo_bloque': 'reto_final', 'icono_emoji': '🏆'},
    ]

    for seccion_data in secciones:
        SeccionEducativa.objects.create(
            producto=producto,
            **seccion_data
        )


# ============================================================================
# SISTEMAS DE INFORMACIÓN
# ============================================================================

@editor_required
def sistemas_listado(request):
    """Listado de sistemas de información organizados por categorías"""
    categorias = CategoriaInformacion.objects.filter(activo=True).prefetch_related('sistemas').order_by('orden', 'nombre')
    sistemas = SistemaInformacion.objects.select_related('categoria').order_by('categoria__orden', 'orden', 'nombre')
    
    # Filtro por categoría
    cat_id = request.GET.get('categoria')
    if cat_id:
        sistemas = sistemas.filter(categoria_id=cat_id)
    
    context = {
        'categorias': categorias,
        'sistemas': sistemas,
        'categoria_filtro': cat_id,
    }
    return render(request, 'editorial/sistemas_listado.html', context)


@editor_required
def sistema_crear(request):
    """Crear un nuevo sistema de información"""
    if request.method == 'POST':
        form = SistemaInformacionForm(request.POST)
        if form.is_valid():
            sistema = form.save()
            messages.success(request, f'Sistema "{sistema.nombre}" creado exitosamente.')
            return redirect('indicadores:editorial_sistemas')
    else:
        form = SistemaInformacionForm()
    
    context = {'form': form, 'titulo_form': 'Nuevo Sistema de Información'}
    return render(request, 'editorial/sistema_form.html', context)


@editor_required
def sistema_editar(request, pk):
    """Editar un sistema de información"""
    sistema = get_object_or_404(SistemaInformacion, pk=pk)
    
    if request.method == 'POST':
        form = SistemaInformacionForm(request.POST, instance=sistema)
        if form.is_valid():
            form.save()
            messages.success(request, f'Sistema "{sistema.nombre}" actualizado.')
            return redirect('indicadores:editorial_sistemas')
    else:
        form = SistemaInformacionForm(instance=sistema)
    
    context = {'form': form, 'sistema': sistema, 'titulo_form': f'Editar: {sistema.nombre}'}
    return render(request, 'editorial/sistema_form.html', context)


@editor_required
def sistema_eliminar(request, pk):
    """Eliminar un sistema de información"""
    sistema = get_object_or_404(SistemaInformacion, pk=pk)
    if request.method == 'POST':
        nombre = sistema.nombre
        sistema.delete()
        messages.success(request, f'Sistema "{nombre}" eliminado.')
        return redirect('indicadores:editorial_sistemas')
    
    context = {'objeto': sistema, 'tipo': 'sistema de información', 'nombre': sistema.nombre, 'url_listado': 'indicadores:editorial_sistemas'}
    return render(request, 'editorial/confirmar_eliminar_generico.html', context)


@editor_required
def categoria_sistema_crear(request):
    """Crear una nueva categoría de sistemas"""
    if request.method == 'POST':
        form = CategoriaInformacionForm(request.POST)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f'Categoría "{cat.nombre}" creada.')
            return redirect('indicadores:editorial_sistemas')
    else:
        form = CategoriaInformacionForm()
    
    context = {'form': form, 'titulo_form': 'Nueva Categoría de Sistemas'}
    return render(request, 'editorial/categoria_form.html', context)


@editor_required
def categoria_sistema_editar(request, pk):
    """Editar una categoría de sistemas"""
    categoria = get_object_or_404(CategoriaInformacion, pk=pk)
    
    if request.method == 'POST':
        form = CategoriaInformacionForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, f'Categoría "{categoria.nombre}" actualizada.')
            return redirect('indicadores:editorial_sistemas')
    else:
        form = CategoriaInformacionForm(instance=categoria)
    
    context = {'form': form, 'categoria': categoria, 'titulo_form': f'Editar categoría: {categoria.nombre}'}
    return render(request, 'editorial/categoria_form.html', context)


# ============================================================================
# PRODUCTOS DE INFORMACIÓN
# ============================================================================

@editor_required
def proyectos_listado(request):
    """Listado de productos de información organizados por categorías"""
    categorias = CategoriaProyecto.objects.filter(activo=True).prefetch_related('proyectos').order_by('orden', 'nombre')
    proyectos = ProyectoInformacion.objects.select_related('categoria').order_by('categoria__orden', 'orden', 'nombre')
    
    # Filtro por categoría
    cat_id = request.GET.get('categoria')
    if cat_id:
        proyectos = proyectos.filter(categoria_id=cat_id)
    
    # Filtro por estado
    estado = request.GET.get('estado')
    if estado:
        proyectos = proyectos.filter(estado=estado)
    
    context = {
        'categorias': categorias,
        'proyectos': proyectos,
        'categoria_filtro': cat_id,
        'estado_filtro': estado,
    }
    return render(request, 'editorial/proyectos_info_listado.html', context)


@editor_required
def proyecto_crear(request):
    """Crear un nuevo producto de información"""
    if request.method == 'POST':
        form = ProyectoInformacionForm(request.POST)
        if form.is_valid():
            proyecto = form.save()
            messages.success(request, f'Producto "{proyecto.nombre}" creado exitosamente.')
            return redirect('indicadores:editorial_proyectos_info')
    else:
        form = ProyectoInformacionForm()
    
    context = {'form': form, 'titulo_form': 'Nuevo Producto de Información'}
    return render(request, 'editorial/proyecto_form.html', context)


@editor_required
def proyecto_editar(request, pk):
    """Editar un producto de información"""
    proyecto = get_object_or_404(ProyectoInformacion, pk=pk)
    
    if request.method == 'POST':
        form = ProyectoInformacionForm(request.POST, instance=proyecto)
        if form.is_valid():
            form.save()
            messages.success(request, f'Producto "{proyecto.nombre}" actualizado.')
            return redirect('indicadores:editorial_proyectos_info')
    else:
        form = ProyectoInformacionForm(instance=proyecto)
    
    context = {'form': form, 'proyecto': proyecto, 'titulo_form': f'Editar: {proyecto.nombre}'}
    return render(request, 'editorial/proyecto_form.html', context)


@editor_required
def proyecto_eliminar(request, pk):
    """Eliminar un producto de información"""
    proyecto = get_object_or_404(ProyectoInformacion, pk=pk)
    if request.method == 'POST':
        nombre = proyecto.nombre
        proyecto.delete()
        messages.success(request, f'Producto "{nombre}" eliminado.')
        return redirect('indicadores:editorial_proyectos_info')
    
    context = {'objeto': proyecto, 'tipo': 'producto de información', 'nombre': proyecto.nombre, 'url_listado': 'indicadores:editorial_proyectos_info'}
    return render(request, 'editorial/confirmar_eliminar_generico.html', context)


@editor_required
def categoria_proyecto_crear(request):
    """Crear una nueva categoría de productos"""
    if request.method == 'POST':
        form = CategoriaProyectoForm(request.POST)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f'Categoría "{cat.nombre}" creada.')
            return redirect('indicadores:editorial_proyectos_info')
    else:
        form = CategoriaProyectoForm()
    
    context = {'form': form, 'titulo_form': 'Nueva Categoría de Productos'}
    return render(request, 'editorial/categoria_form.html', context)


@editor_required
def categoria_proyecto_editar(request, pk):
    """Editar una categoría de productos"""
    categoria = get_object_or_404(CategoriaProyecto, pk=pk)
    
    if request.method == 'POST':
        form = CategoriaProyectoForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, f'Categoría "{categoria.nombre}" actualizada.')
            return redirect('indicadores:editorial_proyectos_info')
    else:
        form = CategoriaProyectoForm(instance=categoria)
    
    context = {'form': form, 'categoria': categoria, 'titulo_form': f'Editar categoría: {categoria.nombre}'}
    return render(request, 'editorial/categoria_form.html', context)


# ============================================================================
# DOCUMENTOS DE INFRAESTRUCTURA
# ============================================================================

@editor_required
def documentos_listado(request):
    """Listado de documentos de infraestructura"""
    documentos = DocumentoInfraestructura.objects.select_related(
        'grupo_documento__subcategoria__categoria__area'
    ).order_by('grupo_documento__subcategoria__categoria__area__orden', 'grupo_documento__orden', 'orden')
    
    # Filtro por estado
    estado = request.GET.get('estado')
    if estado:
        documentos = documentos.filter(estado=estado)
    
    # Filtro por tipo
    tipo = request.GET.get('tipo')
    if tipo:
        documentos = documentos.filter(tipo_documento=tipo)
    
    # Filtro por grupo
    grupo_id = request.GET.get('grupo')
    if grupo_id:
        documentos = documentos.filter(grupo_documento_id=grupo_id)
    
    grupos = GrupoDocumento.objects.select_related('subcategoria__categoria__area').filter(activo=True).order_by('subcategoria__categoria__area__orden', 'orden')
    
    context = {
        'documentos': documentos,
        'grupos': grupos,
        'estado_filtro': estado,
        'tipo_filtro': tipo,
        'grupo_filtro': grupo_id,
    }
    return render(request, 'editorial/documentos_listado.html', context)


@editor_required
def documento_crear(request):
    """Crear un nuevo documento de infraestructura"""
    if request.method == 'POST':
        form = DocumentoInfraestructuraForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save()
            messages.success(request, f'Documento "{doc.nombre}" creado exitosamente.')
            return redirect('indicadores:editorial_documentos')
    else:
        form = DocumentoInfraestructuraForm()
        # Pre-seleccionar grupo si viene por query string
        grupo_id = request.GET.get('grupo')
        if grupo_id:
            form.fields['grupo_documento'].initial = grupo_id
    
    context = {'form': form, 'titulo_form': 'Nuevo Documento de Infraestructura'}
    return render(request, 'editorial/documento_form.html', context)


@editor_required
def documento_editar(request, pk):
    """Editar un documento de infraestructura"""
    documento = get_object_or_404(DocumentoInfraestructura, pk=pk)
    
    if request.method == 'POST':
        form = DocumentoInfraestructuraForm(request.POST, request.FILES, instance=documento)
        if form.is_valid():
            form.save()
            messages.success(request, f'Documento "{documento.nombre}" actualizado.')
            return redirect('indicadores:editorial_documentos')
    else:
        form = DocumentoInfraestructuraForm(instance=documento)
    
    context = {'form': form, 'documento': documento, 'titulo_form': f'Editar: {documento.nombre}'}
    return render(request, 'editorial/documento_form.html', context)


@editor_required
def documento_eliminar(request, pk):
    """Eliminar un documento de infraestructura"""
    documento = get_object_or_404(DocumentoInfraestructura, pk=pk)
    if request.method == 'POST':
        nombre = documento.nombre
        documento.delete()
        messages.success(request, f'Documento "{nombre}" eliminado.')
        return redirect('indicadores:editorial_documentos')
    
    context = {'objeto': documento, 'tipo': 'documento de infraestructura', 'nombre': documento.nombre, 'url_listado': 'indicadores:editorial_documentos'}
    return render(request, 'editorial/confirmar_eliminar_generico.html', context)


# ============================================================================
# ÁRBOL DE INFRAESTRUCTURA (Gestión jerárquica completa)
# ============================================================================

@editor_required
def infraestructura_arbol(request):
    """Vista de árbol jerárquico: Área > Categoría > Subcategoría > Grupo > Documentos"""
    areas = AreaInfraestructura.objects.prefetch_related(
        'categorias__subcategorias__grupos_documentos__documentos'
    ).order_by('orden', 'nombre')
    
    context = {
        'areas': areas,
    }
    return render(request, 'editorial/infraestructura_arbol.html', context)


# --- Áreas (Nivel 1) ---

@editor_required
def infra_area_crear(request):
    """Crear un área de infraestructura"""
    if request.method == 'POST':
        form = AreaInfraestructuraForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Área "{form.instance.nombre}" creada.')
            return redirect('indicadores:editorial_infraestructura_arbol')
    else:
        form = AreaInfraestructuraForm()
    
    context = {'form': form, 'titulo_form': 'Nueva Área de Infraestructura', 'nivel': 'Nivel 1', 'url_volver': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/infra_nodo_form.html', context)


@editor_required
def infra_area_editar(request, pk):
    """Editar un área de infraestructura"""
    area = get_object_or_404(AreaInfraestructura, pk=pk)
    if request.method == 'POST':
        form = AreaInfraestructuraForm(request.POST, instance=area)
        if form.is_valid():
            form.save()
            messages.success(request, f'Área "{area.nombre}" actualizada.')
            return redirect('indicadores:editorial_infraestructura_arbol')
    else:
        form = AreaInfraestructuraForm(instance=area)
    
    context = {'form': form, 'titulo_form': f'Editar Área: {area.nombre}', 'nivel': 'Nivel 1', 'url_volver': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/infra_nodo_form.html', context)


@editor_required
def infra_area_eliminar(request, pk):
    """Eliminar un área de infraestructura"""
    area = get_object_or_404(AreaInfraestructura, pk=pk)
    if request.method == 'POST':
        area.delete()
        messages.success(request, f'Área "{area.nombre}" eliminada.')
        return redirect('indicadores:editorial_infraestructura_arbol')
    
    context = {'objeto': area, 'tipo': 'área de infraestructura', 'nombre': area.nombre, 'url_listado': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/confirmar_eliminar_generico.html', context)


# --- Categorías (Nivel 2) ---

@editor_required
def infra_categoria_crear(request):
    """Crear una categoría de infraestructura"""
    if request.method == 'POST':
        form = CategoriaInfraestructuraForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Categoría "{form.instance.nombre}" creada.')
            return redirect('indicadores:editorial_infraestructura_arbol')
    else:
        form = CategoriaInfraestructuraForm()
        # Pre-seleccionar área si viene por query string
        area_id = request.GET.get('area')
        if area_id:
            form.fields['area'].initial = area_id
    
    context = {'form': form, 'titulo_form': 'Nueva Categoría', 'nivel': 'Nivel 2', 'url_volver': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/infra_nodo_form.html', context)


@editor_required
def infra_categoria_editar(request, pk):
    """Editar una categoría de infraestructura"""
    cat = get_object_or_404(CategoriaInfraestructura, pk=pk)
    if request.method == 'POST':
        form = CategoriaInfraestructuraForm(request.POST, instance=cat)
        if form.is_valid():
            form.save()
            messages.success(request, f'Categoría "{cat.nombre}" actualizada.')
            return redirect('indicadores:editorial_infraestructura_arbol')
    else:
        form = CategoriaInfraestructuraForm(instance=cat)
    
    context = {'form': form, 'titulo_form': f'Editar Categoría: {cat.nombre}', 'nivel': 'Nivel 2', 'url_volver': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/infra_nodo_form.html', context)


@editor_required
def infra_categoria_eliminar(request, pk):
    """Eliminar una categoría de infraestructura"""
    cat = get_object_or_404(CategoriaInfraestructura, pk=pk)
    if request.method == 'POST':
        cat.delete()
        messages.success(request, f'Categoría "{cat.nombre}" eliminada.')
        return redirect('indicadores:editorial_infraestructura_arbol')
    
    context = {'objeto': cat, 'tipo': 'categoría de infraestructura', 'nombre': str(cat), 'url_listado': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/confirmar_eliminar_generico.html', context)


# --- Subcategorías (Nivel 3) ---

@editor_required
def infra_subcategoria_crear(request):
    """Crear una subcategoría de infraestructura"""
    if request.method == 'POST':
        form = SubcategoriaInfraestructuraForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Subcategoría "{form.instance.nombre}" creada.')
            return redirect('indicadores:editorial_infraestructura_arbol')
    else:
        form = SubcategoriaInfraestructuraForm()
        cat_id = request.GET.get('categoria')
        if cat_id:
            form.fields['categoria'].initial = cat_id
    
    context = {'form': form, 'titulo_form': 'Nueva Subcategoría', 'nivel': 'Nivel 3', 'url_volver': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/infra_nodo_form.html', context)


@editor_required
def infra_subcategoria_editar(request, pk):
    """Editar una subcategoría de infraestructura"""
    subcat = get_object_or_404(SubcategoriaInfraestructura, pk=pk)
    if request.method == 'POST':
        form = SubcategoriaInfraestructuraForm(request.POST, instance=subcat)
        if form.is_valid():
            form.save()
            messages.success(request, f'Subcategoría "{subcat.nombre}" actualizada.')
            return redirect('indicadores:editorial_infraestructura_arbol')
    else:
        form = SubcategoriaInfraestructuraForm(instance=subcat)
    
    context = {'form': form, 'titulo_form': f'Editar Subcategoría: {subcat.nombre}', 'nivel': 'Nivel 3', 'url_volver': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/infra_nodo_form.html', context)


@editor_required
def infra_subcategoria_eliminar(request, pk):
    """Eliminar una subcategoría de infraestructura"""
    subcat = get_object_or_404(SubcategoriaInfraestructura, pk=pk)
    if request.method == 'POST':
        subcat.delete()
        messages.success(request, f'Subcategoría "{subcat.nombre}" eliminada.')
        return redirect('indicadores:editorial_infraestructura_arbol')
    
    context = {'objeto': subcat, 'tipo': 'subcategoría', 'nombre': str(subcat), 'url_listado': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/confirmar_eliminar_generico.html', context)


# --- Grupos de Documentos (Nivel 4) ---

@editor_required
def infra_grupo_crear(request):
    """Crear un grupo de documentos"""
    if request.method == 'POST':
        form = GrupoDocumentoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Grupo "{form.instance.nombre}" creado.')
            return redirect('indicadores:editorial_infraestructura_arbol')
    else:
        form = GrupoDocumentoForm()
        subcat_id = request.GET.get('subcategoria')
        if subcat_id:
            form.fields['subcategoria'].initial = subcat_id
    
    context = {'form': form, 'titulo_form': 'Nuevo Grupo de Documentos', 'nivel': 'Nivel 4', 'url_volver': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/infra_nodo_form.html', context)


@editor_required
def infra_grupo_editar(request, pk):
    """Editar un grupo de documentos"""
    grupo = get_object_or_404(GrupoDocumento, pk=pk)
    if request.method == 'POST':
        form = GrupoDocumentoForm(request.POST, instance=grupo)
        if form.is_valid():
            form.save()
            messages.success(request, f'Grupo "{grupo.nombre}" actualizado.')
            return redirect('indicadores:editorial_infraestructura_arbol')
    else:
        form = GrupoDocumentoForm(instance=grupo)
    
    context = {'form': form, 'titulo_form': f'Editar Grupo: {grupo.nombre}', 'nivel': 'Nivel 4', 'url_volver': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/infra_nodo_form.html', context)


@editor_required
def infra_grupo_eliminar(request, pk):
    """Eliminar un grupo de documentos"""
    grupo = get_object_or_404(GrupoDocumento, pk=pk)
    if request.method == 'POST':
        grupo.delete()
        messages.success(request, f'Grupo "{grupo.nombre}" eliminado.')
        return redirect('indicadores:editorial_infraestructura_arbol')
    
    context = {'objeto': grupo, 'tipo': 'grupo de documentos', 'nombre': str(grupo), 'url_listado': 'indicadores:editorial_infraestructura_arbol'}
    return render(request, 'editorial/confirmar_eliminar_generico.html', context)


# ============================================================================
# GRÁFICOS DE INDICADORES
# ============================================================================

@editor_required
def editorial_graficos_listado(request):
    """
    Listado de indicadores con al menos un gráfico.
    Permite seleccionar un indicador para ver/editar sus gráficos.
    """
    # Filtros
    q = request.GET.get('q', '')
    indicadores = Indicador.objects.filter(graficos__isnull=False).distinct()
    if q:
        indicadores = indicadores.filter(
            Q(nombre__icontains=q) | Q(codigo_indicador__icontains=q)
        )
    indicadores = indicadores.order_by('nombre')

    context = {
        'indicadores': indicadores,
        'q': q,
    }
    return render(request, 'editorial/graficos_listado.html', context)


# Umbral de series editables en el editor: cada serie renderiza un
# <select> por dominio del indicador con TODAS sus desagregaciones como
# opciones. Con miles de series el HTML pesa gigabytes y el POST supera
# DATA_UPLOAD_MAX_NUMBER_FIELDS. Por encima del umbral solo se permite
# editar la metadata del gráfico (nombre, tipo_grafico, etc.).
MAX_SERIES_EDITOR = 100


@editor_required
def editorial_grafico_editar(request, pk):
    """Editar un gráfico existente con series inline"""
    grafico = get_object_or_404(Grafico, pk=pk)
    indicador = grafico.indicador

    n_series = grafico.series.count()
    series_bloqueadas = n_series > MAX_SERIES_EDITOR

    if request.method == 'POST':
        form = GraficoForm(request.POST, instance=grafico, indicador=indicador)
        if series_bloqueadas:
            # El formset nunca se renderizó ni puede llegar en el POST;
            # solo se guarda la metadata del gráfico.
            if form.is_valid():
                form.save()
                messages.success(request, f'Gráfico "{grafico.nombre}" actualizado exitosamente.')
                return redirect('indicadores:editorial_grafico_editar', pk=grafico.pk)
            messages.error(request, 'Por favor corrige los errores en el formulario.')
            formset = None
        else:
            formset = GraficoSerieFormSet(
                request.POST, instance=grafico,
                form_kwargs={'indicador': indicador},
            )
            if form.is_valid() and formset.is_valid():
                form.save()
                formset.save()
                messages.success(request, f'Gráfico "{grafico.nombre}" actualizado exitosamente.')
                return redirect('indicadores:editorial_grafico_editar', pk=grafico.pk)
            else:
                messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = GraficoForm(instance=grafico, indicador=indicador)
        formset = None if series_bloqueadas else GraficoSerieFormSet(
            instance=grafico,
            form_kwargs={'indicador': indicador},
        )

    context = {
        'grafico': grafico,
        'indicador': indicador,
        'form': form,
        'formset': formset,
        'es_nuevo': False,
        'n_series': n_series,
        'series_bloqueadas': series_bloqueadas,
    }
    return render(request, 'editorial/grafico_form.html', context)


@editor_required
def editorial_grafico_crear(request, indicador_pk):
    """Crear un nuevo gráfico para un indicador (requiere que tenga al menos uno ya)"""
    indicador = get_object_or_404(Indicador, pk=indicador_pk)

    # Solo permitir si el indicador ya tiene al menos un gráfico
    if not indicador.graficos.exists():
        messages.warning(request, 'Este indicador no tiene gráficos aún. Crea el primero desde el admin del indicador.')
        return redirect('indicadores:editorial_graficos_listado')

    if request.method == 'POST':
        form = GraficoForm(request.POST, indicador=indicador)
        if form.is_valid():
            grafico = form.save(commit=False)
            grafico.indicador = indicador
            grafico.save()
            form.save_m2m()
            messages.success(request, f'Gráfico "{grafico.nombre}" creado. Ahora configura sus series.')
            return redirect('indicadores:editorial_grafico_editar', pk=grafico.pk)
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = GraficoForm(indicador=indicador)

    context = {
        'indicador': indicador,
        'form': form,
        'es_nuevo': True,
    }
    return render(request, 'editorial/grafico_form.html', context)


@editor_required
def editorial_grafico_eliminar(request, pk):
    """Eliminar un gráfico"""
    grafico = get_object_or_404(Grafico, pk=pk)
    indicador_pk = grafico.indicador.pk
    if request.method == 'POST':
        nombre = grafico.nombre
        grafico.delete()
        messages.success(request, f'Gráfico "{nombre}" eliminado.')
        return redirect('indicadores:editorial_graficos_listado')

    context = {
        'objeto': grafico,
        'tipo': 'gráfico',
        'nombre': grafico.nombre,
        'url_listado': 'indicadores:editorial_graficos_listado',
    }
    return render(request, 'editorial/confirmar_eliminar_generico.html', context)


@editor_required
@require_http_methods(["GET"])
def api_buscar_graficos(request):
    """
    API endpoint para busqueda semantica de graficos.
    Usa SemanticSearch sobre indicadores y organiza resultados por
    dominio -> tema -> subtema -> indicador -> graficos.
    """
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'success': False, 'error': 'Consulta requerida'}, status=400)

    try:
        from indicadores.search import SemanticSearch
        from indicadores.models import Indicador, Grafico
        from django.db.models import Q

        # 1. Busqueda por palabra clave en indicador y grafico
        indicadores_keyword = set(
            Indicador.objects.filter(
                Q(nombre__icontains=query) | Q(codigo_indicador__icontains=query),
                activo=True
            ).values_list('id', flat=True)
        )
        graficos_keyword = set(
            Grafico.objects.filter(
                Q(nombre__icontains=query) | Q(descripcion__icontains=query),
                activo=True
            ).values_list('indicador_id', flat=True)
        )
        indicadores_ids_keyword = indicadores_keyword | graficos_keyword

        # 2. Busqueda semantica de indicadores (misma tecnologia que home)
        search_service = SemanticSearch()
        resultados_semanticos = search_service.buscar_similar(
            consulta=query,
            tipo_doc='indicador',
            top_k=15,
            umbral=0.4
        )
        indicadores_ids_semantic = {r['referencia_id'] for r in resultados_semanticos}

        # 3. Union de IDs
        todos_ids = indicadores_ids_keyword | indicadores_ids_semantic

        if not todos_ids:
            return JsonResponse({'success': True, 'jerarquia': [], 'total': 0})

        # 4. Recuperar indicadores con graficos
        indicadores = Indicador.objects.filter(
            id__in=todos_ids,
            activo=True
        ).select_related('subtema__tema__dominio').prefetch_related(
            'graficos', 'subtemas_adicionales__tema__dominio'
        )

        # 5. Organizar jerarquia: dominio -> tema -> subtema -> indicador -> graficos
        #    Un indicador con subtemas adicionales aparece en CADA rama.
        jerarquia = {}
        total_graficos = 0

        for ind in indicadores:
            graficos_list = []
            for g in ind.graficos.filter(activo=True):
                graficos_list.append({
                    'id': g.id,
                    'nombre': g.nombre,
                    'tipo': g.tipo_grafico,
                    'tipo_display': g.get_tipo_grafico_display(),
                    'activo': g.activo,
                    'series_count': g.series.count(),
                    'url_editar': f"/editorial/graficos/{g.id}/editar/"
                })
                total_graficos += 1

            if not graficos_list:
                continue

            # Subtemas del indicador: principal (FK) + adicionales (M2M)
            subtemas_ind = ([ind.subtema] if ind.subtema else []) + \
                list(ind.subtemas_adicionales.all())

            for subtema in subtemas_ind:
                if not subtema.tema or not subtema.tema.dominio:
                    continue
                dominio = subtema.tema.dominio
                tema = subtema.tema

                d_key = dominio.slug
                if d_key not in jerarquia:
                    jerarquia[d_key] = {
                        'nombre': dominio.nombre,
                        'slug': dominio.slug,
                        'temas': {}
                    }

                t_key = tema.slug
                if t_key not in jerarquia[d_key]['temas']:
                    jerarquia[d_key]['temas'][t_key] = {
                        'nombre': tema.nombre,
                        'slug': tema.slug,
                        'subtemas': {}
                    }

                s_key = subtema.slug
                if s_key not in jerarquia[d_key]['temas'][t_key]['subtemas']:
                    jerarquia[d_key]['temas'][t_key]['subtemas'][s_key] = {
                        'nombre': subtema.nombre,
                        'slug': subtema.slug,
                        'indicadores': {}
                    }

                jerarquia[d_key]['temas'][t_key]['subtemas'][s_key]['indicadores'][ind.id] = {
                    'id': ind.id,
                    'nombre': ind.nombre,
                    'codigo': ind.codigo_indicador,
                    'graficos': graficos_list
                }

        # Convertir a listas para JSON
        jerarquia_lista = []
        for d_key in sorted(jerarquia.keys()):
            dom = jerarquia[d_key]
            temas_lista = []
            for t_key in sorted(dom['temas'].keys()):
                tem = dom['temas'][t_key]
                subtemas_lista = []
                for s_key in sorted(tem['subtemas'].keys()):
                    sub = tem['subtemas'][s_key]
                    indicadores_lista = list(sub['indicadores'].values())
                    if indicadores_lista:
                        subtemas_lista.append({
                            'nombre': sub['nombre'],
                            'slug': sub['slug'],
                            'indicadores': indicadores_lista
                        })
                if subtemas_lista:
                    temas_lista.append({
                        'nombre': tem['nombre'],
                        'slug': tem['slug'],
                        'subtemas': subtemas_lista
                    })
            if temas_lista:
                jerarquia_lista.append({
                    'nombre': dom['nombre'],
                    'slug': dom['slug'],
                    'temas': temas_lista
                })

        return JsonResponse({
            'success': True,
            'jerarquia': jerarquia_lista,
            'total': total_graficos
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ============================================================================
# CATÁLOGO DE CONSULTA (directorios / listados tipo anuario CEC)
# ============================================================================

def _importar_archivo_catalogo(catalogo):
    """
    Parsea catalogo.archivo (CSV/Excel) y puebla columnas + filas (JSON).
    Devuelve el número de filas importadas. Lanza la excepción original si falla.
    """
    import math
    from .views_recoleccion import _leer_archivo_datos

    df = _leer_archivo_datos(catalogo.archivo.path)
    df = df.where(df.notna(), None)  # NaN -> None para JSONField

    def _limpiar(v):
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if hasattr(v, 'isoformat'):
            return v.isoformat()
        return v

    catalogo.columnas = [str(c) for c in df.columns]
    catalogo.filas = [
        {str(col): _limpiar(val) for col, val in fila.items()}
        for fila in df.to_dict(orient='records')
    ]
    return len(catalogo.filas)


@editor_required
def catalogo_consulta_listado(request):
    """Listado de conjuntos del catálogo de consulta, filtrable por dominio."""
    dominios = MenuDominio.objects.filter(activo=True).order_by('orden', 'nombre')
    conjuntos = CatalogoConsulta.objects.select_related('dominio').annotate(
        n_indicadores=Count('indicadores_enlazados')
    ).order_by('dominio__orden', 'orden', 'nombre')

    dom_id = request.GET.get('dominio')
    if dom_id:
        conjuntos = conjuntos.filter(dominio_id=dom_id)

    context = {
        'dominios': dominios,
        'conjuntos': conjuntos,
        'dominio_filtro': dom_id,
    }
    return render(request, 'editorial/catalogo_consulta_listado.html', context)


@editor_required
def catalogo_consulta_crear(request):
    """Crear un conjunto del catálogo de consulta con su archivo de datos."""
    if request.method == 'POST':
        form = CatalogoConsultaForm(request.POST, request.FILES)
        if form.is_valid():
            catalogo = form.save()
            if catalogo.archivo:
                try:
                    n = _importar_archivo_catalogo(catalogo)
                    catalogo.save(update_fields=['columnas', 'filas'])
                    messages.success(
                        request,
                        f'Conjunto "{catalogo.nombre}" creado con {n} filas importadas.'
                    )
                except Exception as e:
                    messages.warning(
                        request,
                        f'Conjunto creado pero el archivo no pudo parsearse: {e}. '
                        'Puede re-subirlo desde la edición.'
                    )
            else:
                messages.success(request, f'Conjunto "{catalogo.nombre}" creado (sin datos aún).')
            return redirect('indicadores:editorial_catalogo_consulta_editar', pk=catalogo.pk)
    else:
        form = CatalogoConsultaForm()

    context = {'form': form, 'titulo_form': 'Nuevo Conjunto del Catálogo de Consulta'}
    return render(request, 'editorial/catalogo_consulta_form.html', context)


@editor_required
def catalogo_consulta_editar(request, pk):
    """Editar conjunto: metadata, re-carga de archivo y enlaces a indicadores."""
    catalogo = get_object_or_404(
        CatalogoConsulta.objects.prefetch_related('indicadores_enlazados'), pk=pk
    )

    if request.method == 'POST':
        if 'guardar_enlaces' in request.POST:
            enlaces_form = CatalogoConsultaEnlazarIndicadoresForm(
                request.POST, catalogo=catalogo
            )
            if enlaces_form.is_valid():
                seleccionados = set(enlaces_form.cleaned_data['indicadores'])
                actuales = set(catalogo.indicadores_enlazados.all())
                for ind in seleccionados - actuales:
                    ind.catalogo_consulta = catalogo
                    ind.save(update_fields=['catalogo_consulta'])
                for ind in actuales - seleccionados:
                    ind.catalogo_consulta = None
                    ind.save(update_fields=['catalogo_consulta'])
                messages.success(
                    request,
                    f'Enlaces actualizados: {len(seleccionados)} indicador(es) enlazados.'
                )
                return redirect('indicadores:editorial_catalogo_consulta_editar', pk=pk)
        else:
            form = CatalogoConsultaForm(request.POST, request.FILES, instance=catalogo)
            if form.is_valid():
                nuevo_archivo = bool(request.FILES.get('archivo'))
                catalogo = form.save()
                if nuevo_archivo:
                    try:
                        n = _importar_archivo_catalogo(catalogo)
                        catalogo.save(update_fields=['columnas', 'filas'])
                        messages.success(
                            request,
                            f'Archivo re-importado: {n} filas en el cuadro de consulta.'
                        )
                    except Exception as e:
                        messages.error(request, f'El archivo no pudo parsearse: {e}')
                else:
                    messages.success(request, f'Conjunto "{catalogo.nombre}" actualizado.')
                return redirect('indicadores:editorial_catalogo_consulta_editar', pk=pk)

    form = CatalogoConsultaForm(instance=catalogo)
    enlaces_form = CatalogoConsultaEnlazarIndicadoresForm(catalogo=catalogo)
    # Filas de preview como listas de valores alineadas al orden de `columnas`
    columnas = catalogo.columnas or []
    preview_filas = [
        [fila.get(col) for col in columnas]
        for fila in (catalogo.filas or [])[:10]
    ]

    context = {
        'form': form,
        'enlaces_form': enlaces_form,
        'catalogo': catalogo,
        'preview_filas': preview_filas,
        'titulo_form': f'Editar: {catalogo.nombre}',
    }
    return render(request, 'editorial/catalogo_consulta_form.html', context)


@editor_required
def catalogo_consulta_eliminar(request, pk):
    """Eliminar conjunto (los indicadores enlazados quedan desligados por SET_NULL)."""
    catalogo = get_object_or_404(CatalogoConsulta, pk=pk)
    if request.method == 'POST':
        nombre = catalogo.nombre
        catalogo.delete()
        messages.success(request, f'Conjunto "{nombre}" eliminado del catálogo de consulta.')
        return redirect('indicadores:editorial_catalogo_consulta')

    context = {
        'objeto': catalogo,
        'tipo': 'conjunto del catálogo de consulta',
        'nombre': catalogo.nombre,
        'url_listado': 'indicadores:editorial_catalogo_consulta',
        'aviso_extra': 'Los indicadores enlazados quedarán sin conjunto asociado (volverán a comportarse como indicadores normales).',
    }
    return render(request, 'editorial/confirmar_eliminar_generico.html', context)
