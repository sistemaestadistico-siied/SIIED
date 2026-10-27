# ============================================================================
# VISTAS: PRODUCTOS EDUCATIVOS (NIÑOS Y ADOLESCENTES)
# ============================================================================

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import ProductoEducativo, SeccionEducativa, LogroEducativo, ProgresoUsuarioEducativo
import json


def producto_educativo(request, slug):
    """Vista principal del producto educativo (infantil o adolescente).
    Público solo ve publicados; staff puede previsualizar cualquier estado."""
    if request.user.is_authenticated and request.user.is_staff:
        producto = get_object_or_404(ProductoEducativo, slug=slug)
    else:
        producto = get_object_or_404(ProductoEducativo, slug=slug, estado='publicado')
    secciones = producto.secciones.all().order_by('numero_orden')
    
    # Seleccionar template según público
    if producto.publico == 'infantil':
        template = 'indicadores/producto_educativo_infantil.html'
    else:  # adolescente
        template = 'indicadores/producto_educativo_adolescente.html'
    
    # Menú propio compartido: los productos educativos (infantil y
    # adolescente) se enlazan entre sí, separados de los académicos.
    otros_qs = ProductoEducativo.objects.exclude(pk=producto.pk)
    if not (request.user.is_authenticated and request.user.is_staff):
        otros_qs = otros_qs.filter(estado='publicado')
    otros_educativos = otros_qs.order_by('publico', 'titulo')

    context = {
        'producto': producto,
        'secciones': secciones,
        'otros_educativos': otros_educativos,
        'page': 'educativos',
    }
    
    return render(request, template, context)


@require_http_methods(["POST"])
def api_completar_seccion(request, seccion_id):
    """API para marcar una sección como completada y otorgar puntos"""
    try:
        seccion = get_object_or_404(SeccionEducativa, id=seccion_id)
        session_key = request.session.session_key
        
        if not session_key:
            return JsonResponse({'error': 'Sesión no válida'}, status=400)
        
        progreso = get_object_or_404(
            ProgresoUsuarioEducativo,
            session_key=session_key,
            producto=seccion.producto
        )
        
        # Verificar si ya estaba completada
        if seccion in progreso.secciones_completadas.all():
            return JsonResponse({
                'success': True,
                'message': 'Sección ya completada',
                'puntos_obtenidos': progreso.puntos_obtenidos
            })
        
        # Marcar como completada y otorgar puntos
        progreso.secciones_completadas.add(seccion)
        progreso.puntos_obtenidos += seccion.puntos_seccion
        progreso.save()
        
        # Verificar logros desbloqueados
        logros_nuevos = []
        for logro in LogroEducativo.objects.all():
            if (progreso.puntos_obtenidos >= logro.puntos_requeridos and
                logro not in progreso.logros_desbloqueados.all()):
                progreso.logros_desbloqueados.add(logro)
                logros_nuevos.append({
                    'nombre': logro.nombre,
                    'icono': logro.icono_emoji,
                    'descripcion': logro.descripcion
                })
        
        # Verificar si completó el producto
        total_secciones = seccion.producto.secciones.count()
        secciones_completadas = progreso.secciones_completadas.count()
        if secciones_completadas >= total_secciones and not progreso.completado:
            progreso.completado = True
            progreso.save()
        
        return JsonResponse({
            'success': True,
            'puntos_obtenidos': progreso.puntos_obtenidos,
            'puntos_ganados': seccion.puntos_seccion,
            'logros_nuevos': logros_nuevos,
            'completado': progreso.completado,
            'progreso_porcentaje': int((secciones_completadas / total_secciones) * 100) if total_secciones > 0 else 0
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def api_responder_quiz(request, seccion_id):
    """API para validar respuesta de quiz y otorgar puntos"""
    try:
        data = json.loads(request.body)
        seccion = get_object_or_404(SeccionEducativa, id=seccion_id, tiene_quiz=True)
        
        # Obtener configuración del quiz desde JSON
        config = seccion.configuracion_bloque or {}
        respuesta_correcta = config.get('respuesta_correcta', 0)
        respuesta_usuario = data.get('respuesta', -1)
        
        es_correcta = (respuesta_usuario == respuesta_correcta)
        
        # Si es correcta, marcar sección como completada
        if es_correcta:
            session_key = request.session.session_key
            if session_key:
                progreso = ProgresoUsuarioEducativo.objects.filter(
                    session_key=session_key,
                    producto=seccion.producto
                ).first()
                
                if progreso and seccion not in progreso.secciones_completadas.all():
                    progreso.secciones_completadas.add(seccion)
                    progreso.puntos_obtenidos += seccion.puntos_seccion
                    progreso.save()
        
        return JsonResponse({
            'correcta': es_correcta,
            'respuesta_correcta': respuesta_correcta,
            'explicacion': config.get('explicacion', ''),
            'puntos_ganados': seccion.puntos_seccion if es_correcta else 0
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_progreso_usuario(request, producto_slug):
    """API para obtener el progreso actual del usuario en un producto"""
    try:
        producto = get_object_or_404(ProductoEducativo, slug=producto_slug)
        session_key = request.session.session_key
        
        if not session_key:
            return JsonResponse({
                'puntos_obtenidos': 0,
                'puntos_totales': producto.puntos_totales,
                'secciones_completadas': [],
                'logros': [],
                'completado': False
            })
        
        progreso = ProgresoUsuarioEducativo.objects.filter(
            session_key=session_key,
            producto=producto
        ).first()
        
        if not progreso:
            return JsonResponse({
                'puntos_obtenidos': 0,
                'puntos_totales': producto.puntos_totales,
                'secciones_completadas': [],
                'logros': [],
                'completado': False
            })
        
        return JsonResponse({
            'puntos_obtenidos': progreso.puntos_obtenidos,
            'puntos_totales': producto.puntos_totales,
            'secciones_completadas': list(progreso.secciones_completadas.values_list('id', flat=True)),
            'logros': list(progreso.logros_desbloqueados.values('id', 'nombre', 'icono_emoji', 'descripcion')),
            'completado': progreso.completado,
            'progreso_porcentaje': int((progreso.puntos_obtenidos / producto.puntos_totales) * 100) if producto.puntos_totales > 0 else 0
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
