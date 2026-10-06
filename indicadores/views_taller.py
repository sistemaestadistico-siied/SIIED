"""
Vistas para el sistema de talleres de identificación del ecosistema de datos.
Usa JsonResponse directamente, sin Django REST Framework.
"""
import csv
import json
import logging
import random
import re
import secrets
import zipfile
from datetime import datetime
from io import BytesIO, StringIO
from functools import wraps

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt, xframe_options_sameorigin
from django.db.models import Count, Q, Prefetch
from django.utils import timezone
from django.core.cache import cache
from django.core.exceptions import PermissionDenied

# ReportLab imports
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

import xml.etree.ElementTree as ET

from .models import (
    SesionTaller, ParticipanteTaller, FamiliaRol, RolEcosistema,
    PreguntaQuiz, OpcionQuiz, RespuestaQuiz, FichaDatosPersonal,
    SubsistemaOrganismo, FlujoDatos, ClasificacionDato, Organismo,
    DatoEcosistema, ValidacionEcosistema, RelacionDato
)


# ============================================================================
# CONSTANTES
# ============================================================================

ACTIVIDADES_VALIDAS = [
    'espera', 'quiz', 'roles', 'subsistemas', 
    'ficha_p1', 'flujos', 'ficha_p2', 'mapa3d', 'validacion', 'cierre'
]

AREAS_COMUNES_PREDEFINIDAS = [
    'Dirección',
    'Subdirección de Planeación',
    'Subdirección de Desarrollo Integral',
    'Subdirección Administrativa y Financiera',
    'Oficina de Control Interno',
    'Oficina Asesora Jurídica',
    'Oficina de Comunicaciones',
    'Oficina de Sistemas',
    'Secretaría General',
    'Área Técnica',
    'Área Operativa',
    'Área Misional',
]

# Logger del módulo
logger = logging.getLogger(__name__)


# ============================================================================
# DECORADORES DE SEGURIDAD
# ============================================================================

def requiere_facilitador(view_func):
    """
    Decorador que verifica que el request provenga del facilitador de la sesión.
    Usa el header X-Facilitador-Token o verifica la sesión del request.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Obtener sesion_id de kwargs o del request
        sesion_id = kwargs.get('sesion_id')
        if not sesion_id and request.method == 'POST':
            try:
                data = json.loads(request.body)
                sesion_id = data.get('sesion_id')
            except:
                pass
        
        if not sesion_id:
            return JsonResponse({'error': 'Sesión no especificada'}, status=400)
        
        # Verificar token de facilitador en header
        facilitador_token = request.headers.get('X-Facilitador-Token')
        if not facilitador_token:
            return JsonResponse({'error': 'Token de facilitador requerido'}, status=403)
        
        try:
            sesion = SesionTaller.objects.get(id=sesion_id)
            # El código de acceso de la sesión actúa como token de facilitador
            if facilitador_token != sesion.codigo_acceso:
                return JsonResponse({'error': 'Token de facilitador inválido'}, status=403)
        except SesionTaller.DoesNotExist:
            return JsonResponse({'error': 'Sesión no encontrada'}, status=404)
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def requiere_participante_activo(view_func):
    """
    Decorador que verifica que el participante tenga un token válido y esté activo.
    Extrae el token del body JSON.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            token = data.get('token')
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"Token no encontrado en body JSON - {view_func.__name__}")
            return JsonResponse({'error': 'Token requerido en body JSON'}, status=400)
        
        if not token:
            logger.warning(f"Token vacío en body JSON - {view_func.__name__}")
            return JsonResponse({'error': 'Token de participante requerido'}, status=400)
        
        # Buscar participante por token
        try:
            participante = ParticipanteTaller.objects.get(token_sesion=token)
        except ParticipanteTaller.DoesNotExist:
            logger.warning(f"Token no encontrado en BD: {token[:20]}... - {view_func.__name__}")
            return JsonResponse({
                'error': 'Token inválido',
                'debug': f'Token recibido: {token[:20]}...'
            }, status=403)
        
        # Verificar que esté activo (presente)
        if not participante.presente:
            logger.warning(f"Participante {participante.id} no está activo (presente=False) - {view_func.__name__}")
            return JsonResponse({
                'error': 'Participante no activo',
                'participante_id': participante.id
            }, status=403)
        
        # Adjuntar participante al request para uso posterior
        request.participante = participante
        logger.info(f"Participante {participante.id} ({participante.nombre_completo}) autenticado - {view_func.__name__}")
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def rate_limit_polling(max_requests=20, window_seconds=60):
    """
    Decorador de rate limiting para endpoints de polling.
    Limita a max_requests por window_seconds por IP.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Obtener IP del cliente
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            # Crear cache key
            cache_key = f'rate_limit_polling_{ip}_{view_func.__name__}'
            
            # Obtener contador actual
            request_count = cache.get(cache_key, 0)
            
            if request_count >= max_requests:
                logger.warning(f"Rate limit exceeded for IP {ip} on {view_func.__name__}")
                return JsonResponse({
                    'error': 'Demasiadas solicitudes. Por favor espera un momento.',
                    'retry_after': window_seconds
                }, status=429)
            
            # Incrementar contador
            cache.set(cache_key, request_count + 1, window_seconds)
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


# ============================================================================
# VISTAS DE PARTICIPANTE (autenticación por token de sesión)
# ============================================================================

@require_GET
def taller_obtener_areas(request):
    """
    Obtiene las áreas/dependencias disponibles para un código de sesión.
    """
    codigo = request.GET.get('codigo', '').strip().upper()
    
    if not codigo:
        return JsonResponse({'error': 'Falta código'}, status=400)
    
    try:
        sesion = SesionTaller.objects.select_related('organismo').get(codigo_acceso=codigo)
    except SesionTaller.DoesNotExist:
        return JsonResponse({'error': 'Código inválido'}, status=404)
    
    # Obtener áreas únicas de participantes previos de este organismo
    areas_previas = ParticipanteTaller.objects.filter(
        sesion__organismo=sesion.organismo
    ).values_list('area_funcional', flat=True).distinct().order_by('area_funcional')
    
    # Combinar y eliminar duplicados
    todas_areas = list(set(list(areas_previas) + AREAS_COMUNES_PREDEFINIDAS))
    todas_areas.sort()
    
    return JsonResponse({
        'success': True,
        'organismo': sesion.organismo.nombre,
        'organismo_id': sesion.organismo.id,
        'areas': todas_areas
    })


@csrf_exempt
def taller_unirse(request):
    """
    Página para que participantes se unan a una sesión con código de acceso.
    GET: muestra formulario
    POST: registra participante y genera token
    
    NOTA: Este endpoint requiere @csrf_exempt porque es el punto de entrada
    público donde los participantes se registran. Se valida con código de sesión.
    """
    if request.method == 'GET':
        return render(request, 'indicadores/taller/unirse.html')
    
    # POST: registrar participante
    codigo = request.POST.get('codigo_acceso', '').strip().upper()
    
    # Datos personales completos
    primer_nombre = request.POST.get('primer_nombre', '').strip()
    segundo_nombre = request.POST.get('segundo_nombre', '').strip()
    primer_apellido = request.POST.get('primer_apellido', '').strip()
    segundo_apellido = request.POST.get('segundo_apellido', '').strip()
    email = request.POST.get('email', '').strip()
    numero_contacto = request.POST.get('numero_contacto', '').strip()
    
    # Generar nombre completo
    nombre_completo = request.POST.get('nombre_completo', '').strip()
    if not nombre_completo:
        nombre_completo = f"{primer_nombre} {segundo_nombre} {primer_apellido} {segundo_apellido}".replace('  ', ' ').strip()
    
    cargo = request.POST.get('cargo', '').strip()
    tipo_vinculacion = request.POST.get('tipo_vinculacion', '').strip()
    
    # Jerarquía organizacional (suborganismo OBLIGATORIO, equipo opcional)
    suborganismo_id = request.POST.get('suborganismo_id', '').strip()
    equipo_id = request.POST.get('equipo_id', '').strip()
    
    # Autorización de datos personales
    autoriza = request.POST.get('autoriza_datos_personales', '').lower() == 'true'
    
    # Debug logging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Registro taller - codigo: {codigo}, nombre: {primer_nombre} {primer_apellido}, suborganismo_id: {suborganismo_id}, equipo_id: {equipo_id}")
    
    if not all([codigo, primer_nombre, primer_apellido, tipo_vinculacion, suborganismo_id]):
        logger.warning(f"Faltan datos - codigo: {bool(codigo)}, nombre: {bool(primer_nombre)}, apellido: {bool(primer_apellido)}, tipo_vinc: {bool(tipo_vinculacion)}, suborganismo: {bool(suborganismo_id)}")
        return JsonResponse({
            'error': 'Faltan datos requeridos (código, nombres, tipo de vinculación, subdirección)'
        }, status=400)
    
    if not autoriza:
        return JsonResponse({
            'error': 'Debes autorizar el tratamiento de datos personales para continuar'
        }, status=400)
    
    try:
        sesion = SesionTaller.objects.get(codigo_acceso=codigo)
    except SesionTaller.DoesNotExist:
        return JsonResponse({
            'error': 'Código de acceso inválido'
        }, status=404)
    
    if sesion.estado not in ['preparacion', 'activa']:
        return JsonResponse({
            'error': 'Esta sesión ya finalizó'
        }, status=400)
    
    # Generar token único
    token = secrets.token_urlsafe(48)
    
    # Crear participante con datos completos
    participante = ParticipanteTaller.objects.create(
        sesion=sesion,
        primer_nombre=primer_nombre,
        segundo_nombre=segundo_nombre,
        primer_apellido=primer_apellido,
        segundo_apellido=segundo_apellido,
        nombre_completo=nombre_completo,
        email=email,
        numero_contacto=numero_contacto,
        cargo=cargo,
        area_funcional='',  # Ya no se usa - usar jerarquía estructurada
        tipo_vinculacion=tipo_vinculacion,
        suborganismo_id=suborganismo_id if suborganismo_id else None,
        equipo_id=equipo_id if equipo_id else None,
        autoriza_datos_personales=autoriza,
        fecha_autorizacion=timezone.now() if autoriza else None,
        token_sesion=token,
        presente=True
    )
    
    # Crear respuesta con cookies HttpOnly para seguridad
    response = JsonResponse({
        'success': True,
        'participante_id': participante.id,
        'sesion_id': sesion.id,
        'organismo': sesion.organismo.nombre,
        'actividad_actual': sesion.actividad_actual
    })
    
    # Configurar cookies HttpOnly (más seguro que localStorage)
    response.set_cookie(
        'taller_token',
        value=token,
        max_age=86400,  # 24 horas
        httponly=True,  # No accesible desde JavaScript
        secure=False,  # TODO: Cambiar a True en producción con HTTPS
        samesite='Lax'  # Protección CSRF
    )
    
    response.set_cookie(
        'taller_sesion_id',
        value=str(sesion.id),
        max_age=86400,
        httponly=False,  # Necesario para JavaScript
        secure=False,
        samesite='Lax'
    )
    
    response.set_cookie(
        'taller_participante_id',
        value=str(participante.id),
        max_age=86400,
        httponly=False,
        secure=False,
        samesite='Lax'
    )
    
    return response


@require_GET
@rate_limit_polling(max_requests=60, window_seconds=60)
def taller_estado_sesion(request, sesion_id):
    """
    Retorna el estado actual de la sesión (actividad, participantes, etc).
    Usado por el frontend para polling cada 3 segundos.
    Rate limited: 60 requests por minuto por IP (permite polling cada 1 segundo).
    """
    cache_key = f'sesion_estado_{sesion_id}'
    datos = cache.get(cache_key)
    if datos is None:
        sesion = get_object_or_404(SesionTaller, id=sesion_id)
        datos = {
            'sesion_id': sesion.id,
            'estado': sesion.estado,
            'actividad_actual': sesion.actividad_actual,
            'num_participantes': sesion.participantes.filter(presente=True).count()
        }
        cache.set(cache_key, datos, timeout=3)
    return JsonResponse(datos)


@csrf_exempt
@require_POST
def taller_cambiar_actividad(request, sesion_id):
    """
    Cambia la actividad actual de la sesión.
    Usado por el facilitador desde la pantalla principal.
    REQUIERE: Header X-Facilitador-Token con el código de la sesión.
    """
    # Verificar token de facilitador
    facilitador_token = request.headers.get('X-Facilitador-Token')
    if not facilitador_token:
        return JsonResponse({'error': 'Token de facilitador requerido'}, status=403)
    
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    # Validar que el token coincida con el código de la sesión
    if facilitador_token != sesion.codigo_acceso:
        return JsonResponse({'error': 'Token de facilitador inválido'}, status=403)
    
    try:
        data = json.loads(request.body)
        nueva_actividad = data.get('actividad')
        
        if not nueva_actividad:
            return JsonResponse({'error': 'Falta actividad'}, status=400)
        
        # Validar que la actividad sea válida usando constante
        if nueva_actividad not in ACTIVIDADES_VALIDAS:
            return JsonResponse({'error': 'Actividad inválida'}, status=400)
        
        # Actualizar la actividad
        sesion.actividad_actual = nueva_actividad
        sesion.save()
        cache.delete(f'sesion_estado_{sesion_id}')
        
        return JsonResponse({
            'success': True,
            'actividad_actual': sesion.actividad_actual
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)


# ============================================================================
# QUIZ INTERACTIVO
# ============================================================================

@require_GET
def quiz_preguntas(request):
    """Lista todas las preguntas activas del quiz con sus opciones."""
    preguntas = PreguntaQuiz.objects.filter(activa=True).prefetch_related('opciones').order_by('orden', 'numero')
    
    data = []
    for p in preguntas:
        data.append({
            'id': p.id,
            'numero': p.numero,
            'texto': p.texto,
            'tipo': p.tipo,
            'opciones': [
                {
                    'id': o.id,
                    'letra': o.letra,
                    'texto': o.texto
                }
                for o in p.opciones.all().order_by('orden')
            ]
        })
    
    return JsonResponse(data, safe=False)


@require_POST
@requiere_participante_activo
def quiz_responder(request):
    """
    Registra la respuesta de un participante a una pregunta del quiz.
    Body: {token, pregunta_id, opcion_id}
    REQUIERE: Token de participante válido en el body JSON.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    
    pregunta_id = data.get('pregunta_id')
    opcion_id = data.get('opcion_id')
    
    if not all([pregunta_id, opcion_id]):
        return JsonResponse({'error': 'Faltan parámetros (pregunta_id, opcion_id)'}, status=400)
    
    try:
        participante = request.participante
        pregunta = PreguntaQuiz.objects.get(id=pregunta_id)
        opcion = OpcionQuiz.objects.get(id=opcion_id, pregunta=pregunta)
    except (PreguntaQuiz.DoesNotExist, OpcionQuiz.DoesNotExist):
        return JsonResponse({'error': 'Datos inválidos'}, status=404)
    
    # Crear o actualizar respuesta
    RespuestaQuiz.objects.update_or_create(
        participante=participante,
        pregunta=pregunta,
        defaults={'opcion_seleccionada': opcion}
    )
    
    return JsonResponse({'success': True})


@require_GET
def quiz_resultados(request, sesion_id, pregunta_id):
    """
    Obtiene los resultados en tiempo real de una pregunta para una sesión.
    Usado por la pantalla de proyección.
    """
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    pregunta = get_object_or_404(PreguntaQuiz, id=pregunta_id)
    
    # Contar respuestas por opción
    participantes_ids = sesion.participantes.filter(presente=True).values_list('id', flat=True)
    respuestas = RespuestaQuiz.objects.filter(
        participante_id__in=participantes_ids,
        pregunta=pregunta
    ).values('opcion_seleccionada__letra', 'opcion_seleccionada__texto').annotate(
        count=Count('id')
    )
    
    total_participantes = len(participantes_ids)
    total_respuestas = sum(r['count'] for r in respuestas)
    
    resultados = []
    for r in respuestas:
        resultados.append({
            'letra': r['opcion_seleccionada__letra'],
            'texto': r['opcion_seleccionada__texto'],
            'count': r['count'],
            'porcentaje': round((r['count'] / total_respuestas * 100) if total_respuestas > 0 else 0, 1)
        })
    
    return JsonResponse({
        'pregunta_id': pregunta.id,
        'pregunta_texto': pregunta.texto,
        'total_participantes': total_participantes,
        'total_respuestas': total_respuestas,
        'resultados': resultados
    })


# ============================================================================
# SELECTOR DE ROLES
# ============================================================================

@require_GET
def roles_familias(request):
    """Lista todas las familias de roles con sus roles."""
    familias = FamiliaRol.objects.prefetch_related('roles').order_by('codigo')
    
    data = []
    for f in familias:
        data.append({
            'codigo': f.codigo,
            'nombre': f.nombre,
            'descripcion': f.descripcion,
            'color_hex': f.color_hex,
            'icono': f.icono,
            'imagen_url': f.imagen_url,
            'roles': [
                {
                    'id': r.id,
                    'numero': r.numero,
                    'nombre': r.nombre,
                    'descripcion_narrativa': r.descripcion_narrativa,
                    'descripcion_completa': r.descripcion_completa,
                    'icono': r.icono,
                    'imagen_url': r.imagen_url
                }
                for r in f.roles.all().order_by('numero')
            ]
        })
    
    return JsonResponse(data, safe=False)


@csrf_exempt
@require_POST
@requiere_participante_activo
def roles_asignar(request):
    """
    Asigna un rol primario (y opcionalmente secundario) a un participante.
    Body: {token, rol_primario_id, rol_secundario_id?}
    REQUIERE: Token de participante válido en el body JSON.
    """
    try:
        data = json.loads(request.body)
        rol_primario_id = data.get('rol_primario_id')
        rol_secundario_id = data.get('rol_secundario_id')
        
        participante = request.participante
        
        participante.rol_primario_id = rol_primario_id
        if rol_secundario_id:
            participante.rol_secundario_id = rol_secundario_id
        participante.save()
        
        return JsonResponse({'success': True})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)


@require_GET
def roles_mural(request, sesion_id):
    """
    Obtiene el estado del mural de roles para una sesión.
    Muestra participantes agrupados por familia.
    """
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    # Participantes presentes con rol asignado
    participantes = sesion.participantes.filter(
        presente=True,
        rol_primario__isnull=False
    ).select_related('rol_primario__familia', 'rol_secundario')
    
    # Agrupar por familia
    familias_data = {}
    for p in participantes:
        familia_codigo = p.rol_primario.familia.codigo
        if familia_codigo not in familias_data:
            familias_data[familia_codigo] = {
                'codigo': familia_codigo,
                'nombre': p.rol_primario.familia.nombre,
                'color_hex': p.rol_primario.familia.color_hex,
                'participantes': []
            }
        
        familias_data[familia_codigo]['participantes'].append({
            'nombre': p.nombre_completo,
            'area': p.area_funcional,
            'rol_primario': p.rol_primario.nombre,
            'rol_secundario': p.rol_secundario.nombre if p.rol_secundario else None
        })
    
    # Roles huérfanos (sin nadie asignado)
    roles_asignados = set(participantes.values_list('rol_primario_id', flat=True))
    roles_huerfanos = RolEcosistema.objects.exclude(id__in=roles_asignados).select_related('familia')
    
    return JsonResponse({
        'sesion_id': sesion.id,
        'total_participantes': participantes.count(),
        'familias': list(familias_data.values()),
        'roles_huerfanos': [
            {
                'id': r.id,
                'nombre': r.nombre,
                'familia': r.familia.nombre
            }
            for r in roles_huerfanos
        ]
    })


# ============================================================================
# SUBSISTEMAS DEL ORGANISMO
# ============================================================================

@require_GET
def subsistemas_listar(request, sesion_id):
    """
    Lista todos los subsistemas de una sesión (predefinidos + identificados en taller).
    Para que participantes y facilitador vean la lista completa.
    """
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    subsistemas = SubsistemaOrganismo.objects.filter(sesion=sesion).order_by('nombre')
    
    return JsonResponse({
        'subsistemas': [
            {
                'id': s.id,
                'nombre': s.nombre,
                'tipo': s.get_tipo_display(),
                'tipo_codigo': s.tipo,
                'descripcion': s.descripcion or '',
                'identificado_en_taller': s.identificado_en_taller,
                'aprobado': True  # Los que están en BD ya están aprobados
            }
            for s in subsistemas
        ]
    })


@require_POST
@requiere_participante_activo
def subsistema_proponer(request):
    """
    Participante propone un nuevo subsistema que falta.
    Queda pendiente de aprobación del facilitador.
    Body: {token, nombre, tipo, descripcion}
    REQUIERE: Token de participante válido en el body JSON.
    """
    try:
        data = json.loads(request.body)
        nombre = data.get('nombre', '').strip()
        tipo = data.get('tipo', 'otro')
        descripcion = data.get('descripcion', '').strip()
        
        if not nombre:
            return JsonResponse({'error': 'Nombre requerido'}, status=400)
        
        participante = request.participante
        
        # Crear subsistema con identificado_en_taller=True
        subsistema = SubsistemaOrganismo.objects.create(
            sesion=participante.sesion,
            nombre=nombre,
            tipo=tipo,
            descripcion=descripcion or f"Propuesto por {participante.nombre_completo}",
            identificado_en_taller=True
        )
        
        return JsonResponse({
            'success': True,
            'subsistema': {
                'id': subsistema.id,
                'nombre': subsistema.nombre,
                'tipo': subsistema.get_tipo_display()
            }
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)


@require_POST
@requiere_facilitador
def subsistema_validar(request, sesion_id):
    """
    Facilitador valida/aprueba subsistemas propuestos por participantes.
    Body: {subsistema_id, accion: 'aprobar'|'rechazar'}
    REQUIERE: Header X-Facilitador-Token con el código de la sesión.
    """
    try:
        data = json.loads(request.body)
        subsistema_id = data.get('subsistema_id')
        accion = data.get('accion')
        
        sesion = get_object_or_404(SesionTaller, id=sesion_id)
        subsistema = get_object_or_404(SubsistemaOrganismo, id=subsistema_id, sesion=sesion)
        
        if accion == 'rechazar':
            subsistema.delete()
            return JsonResponse({'success': True, 'mensaje': 'Subsistema rechazado'})
        
        # Si es 'aprobar', ya está creado, solo confirmamos
        return JsonResponse({
            'success': True,
            'mensaje': 'Subsistema aprobado',
            'subsistema': {
                'id': subsistema.id,
                'nombre': subsistema.nombre
            }
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)


# ============================================================================
# FICHA DE DATOS PERSONAL
# ============================================================================

@require_POST
@requiere_participante_activo
def ficha_guardar(request):
    """
    Guarda la ficha de caracterización de un participante (4 preguntas).
    Body: {token, datos_que_manejo, que_hago_con_ellos, a_quien_entrego, de_quien_recibo}
    REQUIERE: Token de participante válido en el body JSON.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    
    participante = request.participante
    
    # Crear o actualizar ficha
    ficha, created = FichaDatosPersonal.objects.update_or_create(
        participante=participante,
        defaults={
            'datos_que_manejo': data.get('datos_que_manejo', ''),
            'que_hago_con_ellos': data.get('que_hago_con_ellos', ''),
            'a_quien_entrego': data.get('a_quien_entrego', ''),
            'de_quien_recibo': data.get('de_quien_recibo', ''),
            'sistemas_mencionados': data.get('sistemas_mencionados', '')
        }
    )
    
    return JsonResponse({
        'success': True,
        'ficha_id': ficha.id,
        'created': created
    })


# ============================================================================
# FLUJOS DE DATOS
# ============================================================================

@require_POST
@requiere_participante_activo
def flujo_registrar(request):
    """
    Registra un flujo de datos manejado por un participante.
    
    Modelo: [De dónde recibo] → [Participante con Rol X] → [A dónde envío]
    
    Body: {token, tipo, rol_usado, recibe_de_*, envia_a_*, descripcion_datos, frecuencia?, formato?}
    REQUIERE: Token de participante válido en el body JSON.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    
    # Validar que tenga dato o descripción
    if not data.get('dato_id') and not data.get('descripcion_datos'):
        return JsonResponse({'error': 'Falta dato o descripción de datos'}, status=400)
    
    participante = request.participante
    
    # Resolver DatoEcosistema por id
    dato_obj = None
    if data.get('dato_id'):
        try:
            dato_obj = DatoEcosistema.objects.get(
                id=data['dato_id'],
                sesion=participante.sesion,
                es_maestro=True
            )
        except DatoEcosistema.DoesNotExist:
            return JsonResponse({'error': 'Dato no encontrado en esta sesión'}, status=400)
    
    # Extraer datos específicos de la descripción (legacy/complemento)
    descripcion = data.get('descripcion_datos', '') or (dato_obj.nombre if dato_obj else '')
    datos_especificos = [d.strip() for d in re.split(r'[,;\n]+', descripcion) if d.strip()]
    
    # RECIBE DE
    recibe_de_org = None
    recibe_de_sociedad_civil = data.get('recibe_de_sociedad_civil', False)
    recibe_de_entidad_externa = data.get('recibe_de_entidad_externa', '')
    recibe_de_tipo_entidad = data.get('recibe_de_tipo_entidad', '')
    
    # Si viene organismo_id, buscar el organismo
    if data.get('recibe_de_organismo_id'):
        try:
            recibe_de_org = Organismo.objects.get(id=data.get('recibe_de_organismo_id'), activo=True)
        except Organismo.DoesNotExist:
            pass
    
    # ENVÍA A
    envia_a_org = None
    envia_a_sociedad_civil = data.get('envia_a_sociedad_civil', False)
    envia_a_entidad_externa = data.get('envia_a_entidad_externa', '')
    envia_a_tipo_entidad = data.get('envia_a_tipo_entidad', '')
    
    # Si viene organismo_id, buscar el organismo
    if data.get('envia_a_organismo_id'):
        try:
            envia_a_org = Organismo.objects.get(id=data.get('envia_a_organismo_id'), activo=True)
        except Organismo.DoesNotExist:
            pass
    
    # Crear flujo con participante en el centro
    flujo = FlujoDatos.objects.create(
        sesion=participante.sesion,
        participante=participante,  # Obligatorio - centro del flujo
        tipo=data.get('tipo', 'interno'),
        rol_usado=data.get('rol_usado', 'primario'),
        # De dónde recibe
        recibe_de_participante_id=data.get('recibe_de_participante_id'),
        recibe_de_subsistema_id=data.get('recibe_de_subsistema_id'),
        recibe_de_sociedad_civil=recibe_de_sociedad_civil,
        recibe_de_organismo=recibe_de_org,
        recibe_de_entidad_externa=recibe_de_entidad_externa,
        recibe_de_tipo_entidad=recibe_de_tipo_entidad,
        # A dónde envía
        envia_a_participante_id=data.get('envia_a_participante_id'),
        envia_a_subsistema_id=data.get('envia_a_subsistema_id'),
        envia_a_sociedad_civil=envia_a_sociedad_civil,
        envia_a_organismo=envia_a_org,
        envia_a_entidad_externa=envia_a_entidad_externa,
        envia_a_tipo_entidad=envia_a_tipo_entidad,
        # Dato como nodo (Torres 2026)
        dato=dato_obj,
        # Caracterización
        descripcion_datos=descripcion,
        datos_especificos=datos_especificos,
        frecuencia=data.get('frecuencia'),
        formato=data.get('formato'),
        # Tipo de interacción (Torres/ODI)
        tipo_interaccion_recibe=data.get('tipo_interaccion_recibe', ''),
        tipo_interaccion_envia=data.get('tipo_interaccion_envia', '')
    )
    
    return JsonResponse({
        'success': True,
        'flujo_id': flujo.id
    })


@require_GET
def flujos_sesion(request, sesion_id):
    """
    Obtiene todos los flujos de una sesión para el mapa 3D.
    
    Modelo: [De dónde recibe] → [Participante con Rol X] → [A dónde envía]
    """
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    flujos = sesion.flujos.select_related(
        'participante', 
        'participante__rol_primario',
        'participante__rol_secundario',
        'recibe_de_participante', 
        'recibe_de_subsistema',
        'envia_a_participante', 
        'envia_a_subsistema',
        'dato'
    )
    
    data = []
    for f in flujos:
        # Determinar de dónde recibe
        if f.recibe_de_participante:
            recibe_de = f.recibe_de_participante.nombre_completo
            recibe_de_tipo = 'participante'
            recibe_de_id = f.recibe_de_participante.id
        elif f.recibe_de_subsistema:
            recibe_de = f.recibe_de_subsistema.nombre
            recibe_de_tipo = 'subsistema'
            recibe_de_id = f.recibe_de_subsistema.id
        else:
            # Priorizar campos nuevos sobre los viejos
            recibe_de = f.recibe_de_entidad_externa or f.recibe_de_externo or 'N/A'
            recibe_de_tipo = 'externo'
            recibe_de_id = None
        
        # Determinar a dónde envía
        if f.envia_a_participante:
            envia_a = f.envia_a_participante.nombre_completo
            envia_a_tipo = 'participante'
            envia_a_id = f.envia_a_participante.id
        elif f.envia_a_subsistema:
            envia_a = f.envia_a_subsistema.nombre
            envia_a_tipo = 'subsistema'
            envia_a_id = f.envia_a_subsistema.id
        else:
            # Priorizar campos nuevos sobre los viejos
            envia_a = f.envia_a_entidad_externa or f.envia_a_externo or 'N/A'
            envia_a_tipo = 'externo'
            envia_a_id = None
        
        # Determinar rol usado
        rol_usado = f.participante.rol_primario if f.rol_usado == 'primario' else f.participante.rol_secundario
        rol_nombre = rol_usado.nombre if rol_usado else 'Sin rol'
        
        data.append({
            'id': f.id,
            'tipo': f.tipo,
            # Participante que maneja el flujo (centro)
            'participante': {
                'id': f.participante.id,
                'nombre': f.participante.nombre_completo,
                'token': f.participante.token_sesion,
                'rol_usado': f.rol_usado,
                'rol_nombre': rol_nombre
            },
            # De dónde recibe
            'recibe_de': recibe_de,
            'recibe_de_tipo': recibe_de_tipo,
            'recibe_de_id': recibe_de_id,
            # A dónde envía
            'envia_a': envia_a,
            'envia_a_tipo': envia_a_tipo,
            'envia_a_id': envia_a_id,
            # Dato como nodo (Torres 2026)
            'dato': {
                'id': f.dato.id,
                'nombre': f.dato.nombre,
                'nivel': f.dato.nivel,
                'sensibilidad': f.dato.sensibilidad,
            } if f.dato else None,
            # Caracterización
            'descripcion_datos': f.descripcion_datos,
            'frecuencia': f.frecuencia,
            'formato': f.formato,
            # Tipo de interacción (Torres/ODI)
            'tipo_interaccion_recibe': f.tipo_interaccion_recibe,
            'tipo_interaccion_envia': f.tipo_interaccion_envia,
            # Para compatibilidad con vistas anteriores
            'origen': recibe_de,
            'destino': envia_a
        })
    
    return JsonResponse({'flujos': data})


# ============================================================================
# CLASIFICACIÓN DE DATOS (O/T/E)
# ============================================================================

@require_POST
@requiere_participante_activo
def clasificacion_guardar(request):
    """
    Guarda una clasificación de dato (operativo/táctico/estratégico).
    Body: {token, nombre_dato, nivel, para_que_se_usa?, valor_publico?}
    REQUIERE: Token de participante válido en el body JSON.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    
    participante = request.participante
    
    # Resolver DatoEcosistema por id
    dato_obj = None
    if data.get('dato_id'):
        try:
            dato_obj = DatoEcosistema.objects.get(
                id=data['dato_id'],
                sesion=participante.sesion,
                es_maestro=True
            )
        except DatoEcosistema.DoesNotExist:
            return JsonResponse({'error': 'Dato no encontrado en esta sesión'}, status=400)
    
    nivel = data.get('nivel')
    sensibilidad = data.get('sensibilidad')
    principales_usuarios = data.get('principales_usuarios', '')
    proposito_detallado = data.get('proposito_detallado', '')
    valor_publico = data.get('valor_publico', '')
    
    clasificacion = ClasificacionDato.objects.create(
        sesion=participante.sesion,
        participante=participante,
        dato=dato_obj,
        nombre_dato=data.get('nombre_dato', '') or (dato_obj.nombre if dato_obj else ''),
        nivel=nivel,
        sensibilidad=sensibilidad,
        para_que_se_usa=data.get('para_que_se_usa'),
        valor_publico=valor_publico,
        # Sección C — Conexiones (Torres)
        principales_usuarios=principales_usuarios,
        proposito_detallado=proposito_detallado
    )
    
    # Sincronizar clasificación al nodo-dato (la última clasificación gana)
    if dato_obj:
        updated_fields = []
        if nivel and not dato_obj.nivel:
            dato_obj.nivel = nivel
            updated_fields.append('nivel')
        if sensibilidad and not dato_obj.sensibilidad:
            dato_obj.sensibilidad = sensibilidad
            updated_fields.append('sensibilidad')
        if principales_usuarios and not dato_obj.principales_usuarios:
            dato_obj.principales_usuarios = principales_usuarios
            updated_fields.append('principales_usuarios')
        if proposito_detallado and not dato_obj.proposito_detallado:
            dato_obj.proposito_detallado = proposito_detallado
            updated_fields.append('proposito_detallado')
        if valor_publico and not dato_obj.valor_publico:
            dato_obj.valor_publico = valor_publico
            updated_fields.append('valor_publico')
        if updated_fields:
            dato_obj.save(update_fields=updated_fields)
    
    return JsonResponse({
        'success': True,
        'clasificacion_id': clasificacion.id,
        'dato_actualizado': bool(dato_obj)
    })


@require_GET
def clasificaciones_sesion(request, sesion_id):
    """Obtiene todas las clasificaciones de una sesión."""
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    clasificaciones = sesion.clasificaciones.select_related('dato').all()
    clasificaciones_list = []
    for c in clasificaciones:
        clasificaciones_list.append({
            'id': c.id,
            'nombre_dato': c.nombre_dato or (c.dato.nombre if c.dato else ''),
            'nivel': c.nivel,
            'sensibilidad': c.sensibilidad,
            'para_que_se_usa': c.para_que_se_usa,
            'principales_usuarios': c.principales_usuarios,
            'proposito_detallado': c.proposito_detallado,
            'dato': {
                'id': c.dato.id,
                'nombre': c.dato.nombre,
                'nivel': c.dato.nivel,
            } if c.dato else None,
        })
    
    # Contar por nivel
    stats = sesion.clasificaciones.values('nivel').annotate(count=Count('id'))
    
    return JsonResponse({
        'clasificaciones': clasificaciones_list,
        'stats': {s['nivel']: s['count'] for s in stats}
    })


# ============================================================================
# VALIDACIÓN GRUPAL DEL ECOSISTEMA
# ============================================================================

@csrf_exempt
@require_POST
@requiere_participante_activo
def validacion_registrar(request):
    """
    Registra observaciones de validación grupal de un participante.
    Body: {token, sugerencias_roles, flujos_validados, flujos_faltantes, 
           datos_faltantes, actores_faltantes, observacion_general}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    
    participante = request.participante
    
    validacion, created = ValidacionEcosistema.objects.update_or_create(
        sesion=participante.sesion,
        participante=participante,
        defaults={
            'sugerencias_roles': data.get('sugerencias_roles', []),
            'flujos_validados': data.get('flujos_validados', []),
            'flujos_faltantes': data.get('flujos_faltantes', ''),
            'datos_faltantes': data.get('datos_faltantes', ''),
            'actores_faltantes': data.get('actores_faltantes', ''),
            'observacion_general': data.get('observacion_general', ''),
        }
    )
    
    return JsonResponse({
        'success': True,
        'validacion_id': validacion.id,
        'created': created
    })


@require_GET
@requiere_facilitador
def validacion_resumen(request, sesion_id):
    """
    Resumen de validaciones grupales de una sesión para el facilitador.
    """
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    validaciones = sesion.validaciones.select_related('participante').all()
    
    data = []
    for v in validaciones:
        data.append({
            'participante': v.participante.nombre_completo,
            'sugerencias_roles': v.sugerencias_roles,
            'flujos_validados': v.flujos_validados,
            'flujos_faltantes': v.flujos_faltantes,
            'datos_faltantes': v.datos_faltantes,
            'actores_faltantes': v.actores_faltantes,
            'observacion_general': v.observacion_general,
            'fecha': v.fecha.isoformat() if v.fecha else None,
        })
    
    return JsonResponse({
        'total_participantes': sesion.participantes.filter(presente=True).count(),
        'total_validaciones': validaciones.count(),
        'validaciones': data
    })


# ============================================================================
# MAPA 3D DEL ECOSISTEMA (datos completos)
# ============================================================================

@require_GET
@requiere_facilitador
def api_ecosistema_grafo(request, sesion_id):
    """
    Retorna datos del ecosistema para renderizar el mapa 3D.
    Incluye participantes, subsistemas, flujos y clasificaciones.
    Optimizado con select_related para reducir queries con 30+ participantes.
    """
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    # Participantes con sus roles (optimizado con select_related)
    participantes = sesion.participantes.filter(presente=True).select_related(
        'rol_primario__familia',
        'rol_secundario'
    ).values(
        'id', 'nombre_completo', 'area_funcional', 'cargo',
        'rol_primario__id', 'rol_primario__nombre', 'rol_primario__familia__codigo', 'rol_primario__familia__color_hex',
        'rol_secundario__id', 'rol_secundario__nombre'
    )
    
    # Subsistemas
    subsistemas = sesion.subsistemas.values(
        'id', 'nombre', 'tipo', 'pos_x', 'pos_y', 'pos_z'
    )
    
    # Flujos con nuevo modelo (optimizado con select_related para todos los FK)
    flujos_data = []
    for f in sesion.flujos.select_related(
        'participante', 'participante__rol_primario', 'participante__rol_secundario',
        'recibe_de_participante', 'recibe_de_subsistema', 'recibe_de_organismo',
        'envia_a_participante', 'envia_a_subsistema', 'envia_a_organismo',
        'dato'
    ):
        # Determinar rol usado
        rol = f.participante.rol_primario if f.rol_usado == 'primario' else f.participante.rol_secundario
        
        flujos_data.append({
            'id': f.id,
            'tipo': f.tipo,
            # Participante central que maneja el flujo
            'participante_id': f.participante.id,
            'participante_nombre': f.participante.nombre_completo,
            'rol_usado': f.rol_usado,
            'rol_nombre': rol.nombre if rol else 'Sin rol',
            # De dónde recibe
            'recibe_de_participante_id': f.recibe_de_participante_id,
            'recibe_de_subsistema_id': f.recibe_de_subsistema_id,
            'recibe_de_sociedad_civil': f.recibe_de_sociedad_civil,
            'recibe_de_organismo_id': f.recibe_de_organismo_id,
            'recibe_de_organismo_nombre': f.recibe_de_organismo.nombre if f.recibe_de_organismo else None,
            'recibe_de_entidad_externa': f.recibe_de_entidad_externa,
            'recibe_de_tipo_entidad': f.recibe_de_tipo_entidad,
            # A dónde envía
            'envia_a_participante_id': f.envia_a_participante_id,
            'envia_a_subsistema_id': f.envia_a_subsistema_id,
            'envia_a_sociedad_civil': f.envia_a_sociedad_civil,
            'envia_a_organismo_id': f.envia_a_organismo_id,
            'envia_a_organismo_nombre': f.envia_a_organismo.nombre if f.envia_a_organismo else None,
            'envia_a_entidad_externa': f.envia_a_entidad_externa,
            'envia_a_tipo_entidad': f.envia_a_tipo_entidad,
            # Dato como nodo (Torres 2026)
            'dato_id': f.dato_id,
            'dato_nombre': f.dato.nombre if f.dato else None,
            'dato_nivel': f.dato.nivel if f.dato else None,
            # Tipo de interacción (Torres 2026)
            'tipo_interaccion_recibe': f.tipo_interaccion_recibe,
            'tipo_interaccion_envia': f.tipo_interaccion_envia,
            # Caracterización
            'descripcion_datos': f.descripcion_datos,
            'frecuencia': f.frecuencia,
            'formato': f.formato
        })
    
    # DATOS como nodos del grafo (Torres 2026)
    datos_qs = DatoEcosistema.objects.filter(
        sesion=sesion, es_maestro=True
    ).annotate(
        num_flujos=Count('flujos'),
    )
    datos_nodos = [{
        'id': d.id,
        'nombre': d.nombre,
        'nivel': d.nivel,
        'sensibilidad': d.sensibilidad,
        'origen': d.origen,
        'periodicidad': d.periodicidad,
        'num_flujos': d.num_flujos,
        'es_huerfano': d.num_flujos == 0,
        'es_critico': d.num_flujos >= 5,
    } for d in datos_qs]
    
    # Clasificaciones de datos (legacy para compatibilidad)
    clasificaciones = sesion.clasificaciones.values(
        'nombre_dato', 'nivel', 'sensibilidad'
    )
    dict_clasificaciones = {c['nombre_dato']: {'nivel': c['nivel'], 'sensibilidad': c['sensibilidad']} for c in clasificaciones}
    
    # Clasificaciones por nivel para stats
    clasificaciones_stats = sesion.clasificaciones.values('nivel').annotate(count=Count('id'))
    
    # Relaciones entre datos (linaje) - todas las relaciones de la sesión
    relaciones_datos = []
    for r in RelacionDato.objects.filter(sesion=sesion).select_related('dato_origen', 'dato_destino'):
        relaciones_datos.append({
            'id': r.id,
            'tipo_relacion': r.tipo_relacion,
            'tipo_relacion_display': r.get_tipo_relacion_display(),
            'descripcion': r.descripcion,
            'dato_origen_id': r.dato_origen_id,
            'dato_origen_nombre': r.dato_origen.nombre,
            'dato_origen_nivel': r.dato_origen.nivel,
            'dato_destino_id': r.dato_destino_id,
            'dato_destino_nombre': r.dato_destino.nombre,
            'dato_destino_nivel': r.dato_destino.nivel,
            'proceso_transformacion': r.proceso_transformacion,
            'periodicidad': r.periodicidad_transformacion,
            'es_validada': r.es_validada,
        })
    
    return JsonResponse({
        'sesion_id': sesion.id,
        'organismo': sesion.organismo.nombre,
        'participantes': list(participantes),
        'subsistemas': list(subsistemas),
        'datos_nodos': datos_nodos,
        'flujos': flujos_data,
        'clasificaciones_detalle': dict_clasificaciones,
        'clasificaciones_stats': {s['nivel']: s['count'] for s in clasificaciones_stats},
        'relaciones_datos': relaciones_datos,
        'stats_relaciones': {
            'total_relaciones': len(relaciones_datos),
            'relaciones_validadas': sum(1 for r in relaciones_datos if r['es_validada'])
        }
    })


# ============================================================================
# API ENDPOINTS PARA JERARQUÍA ORGANIZACIONAL
# ============================================================================

@require_GET
def api_suborganismos(request, organismo_id):
    """
    Lista suborganismos activos de un organismo.
    Usado en formularios de taller y satisfacción.
    """
    from .models import Suborganismo
    
    suborganismos = Suborganismo.objects.filter(
        organismo_id=organismo_id,
        activo=True
    ).values('id', 'nombre', 'tipo', 'codigo').order_by('orden', 'nombre')
    
    return JsonResponse(list(suborganismos), safe=False)


@require_GET
def api_equipos_suborganismo(request, suborganismo_id):
    """
    Lista equipos activos de un suborganismo.
    Usado en formularios de taller y satisfacción.
    """
    from .models import EquipoOrganismo
    
    equipos = EquipoOrganismo.objects.filter(
        suborganismo_id=suborganismo_id,
        activo=True
    ).values('id', 'nombre', 'codigo').order_by('nombre')
    
    return JsonResponse(list(equipos), safe=False)


@require_GET
def api_equipos_organismo(request, organismo_id):
    """
    Lista todos los equipos de un organismo (con o sin suborganismo).
    Usado como fallback si no se selecciona suborganismo.
    """
    from .models import EquipoOrganismo
    
    equipos = EquipoOrganismo.objects.filter(
        organismo_id=organismo_id,
        activo=True
    ).select_related('suborganismo').values(
        'id', 'nombre', 'codigo', 
        'suborganismo__id', 'suborganismo__nombre'
    ).order_by('suborganismo__nombre', 'nombre')
    
    return JsonResponse(list(equipos), safe=False)


# ============================================================================
# VISTAS DE TEMPLATE (HTML)
# ============================================================================

def taller_pantalla_principal(request, sesion_id):
    """Pantalla de proyección para el facilitador."""
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    return render(request, 'indicadores/taller/pantalla_principal.html', {
        'sesion': sesion
    })


def taller_participante(request):
    """Interfaz del participante (móvil)."""
    # Primero intentar obtener token de las cookies (configuradas al registrarse)
    token = request.COOKIES.get('taller_token')
    
    # Fallback: también aceptar token por GET para compatibilidad
    if not token:
        token = request.GET.get('token')
    
    if not token:
        return redirect('indicadores:taller_unirse')
    
    try:
        participante = ParticipanteTaller.objects.select_related('sesion').get(token_sesion=token)
    except ParticipanteTaller.DoesNotExist:
        return redirect('indicadores:taller_unirse')
    
    return render(request, 'indicadores/taller/participante.html', {
        'participante': participante,
        'sesion': participante.sesion
    })


@require_POST
@requiere_participante_activo
def clasificacion_registrar(request):
    """Registra una clasificación de dato por parte de un participante.
    REQUIERE: Token de participante válido en el body JSON.
    """
    try:
        data = json.loads(request.body)
        
        participante = request.participante
        
        clasificacion = ClasificacionDato.objects.create(
            sesion=participante.sesion,
            participante=participante,  # Guardar quién clasificó
            nombre_dato=data.get('nombre_dato'),
            nivel=data.get('nivel'),  # Nivel estratégico/táctico/operativo
            sensibilidad=data.get('sensibilidad'),  # Nivel de sensibilidad público/interno/confidencial/crítico
            para_que_se_usa=data.get('justificacion', ''),
            mecanismo_recoleccion=data.get('mecanismo_recoleccion', ''),
            valor_publico=data.get('valor_publico', '')
        )
        
        # Enriquecer DatoEcosistema con la clasificación (Torres 2026)
        dato_id = data.get('dato_id')
        if dato_id:
            try:
                dato = DatoEcosistema.objects.get(id=dato_id, sesion=participante.sesion)
                dato.nivel = data.get('nivel', '') or dato.nivel
                dato.sensibilidad = data.get('sensibilidad', '') or dato.sensibilidad
                dato.mecanismo_recoleccion = data.get('mecanismo_recoleccion', '') or dato.mecanismo_recoleccion
                dato.valor_publico = data.get('valor_publico', '') or dato.valor_publico
                dato.principales_usuarios = data.get('principales_usuarios', '') or dato.principales_usuarios
                dato.proposito_detallado = data.get('proposito_detallado', '') or dato.proposito_detallado
                dato.save(update_fields=[
                    'nivel', 'sensibilidad', 'mecanismo_recoleccion',
                    'valor_publico', 'principales_usuarios', 'proposito_detallado'
                ])
                logger.info(f"DatoEcosistema {dato_id} enriquecido con clasificación por participante {participante.id}")
            except DatoEcosistema.DoesNotExist:
                logger.warning(f"DatoEcosistema {dato_id} no encontrado para enriquecer")
        
        return JsonResponse({
            'success': True,
            'clasificacion_id': clasificacion.id
        })
        
    except Exception as e:
        logger.error(f"Error en clasificacion_registrar: {e}", exc_info=True)
        return JsonResponse({
            'error': str(e)
        }, status=400)


def organismos_lista(request):
    """Lista todos los organismos activos para autocompletado en flujos."""
    from .models import Organismo
    
    organismos = Organismo.objects.filter(activo=True).values('id', 'nombre', 'codigo')
    return JsonResponse({
        'organismos': list(organismos)
    })


@xframe_options_sameorigin
def taller_mapa_3d(request, sesion_id):
    """Mapa 3D del ecosistema (para iframe en pantalla principal y participante)."""
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    return render(request, 'indicadores/taller/mapa_ecosistema_3d.html', {
        'sesion': sesion
    })


# ============================================================================
# MAPA DEL DATO — Vista centrada en un dato/conjunto de datos (Torres 2026)
# ============================================================================

@xframe_options_sameorigin
def taller_mapa_dato(request, dato_id):
    """Renderiza el Mapa 3D centrado en un dato específico del ecosistema."""
    dato = get_object_or_404(DatoEcosistema, id=dato_id, es_maestro=True)
    sesion = dato.sesion
    return render(request, 'indicadores/taller/mapa_dato_3d.html', {
        'dato': dato,
        'sesion': sesion
    })


@require_GET
def api_dato_grafo(request, dato_id):
    """
    API que retorna todos los actores y conexiones de un dato específico
    para renderizar el Mapa del Dato centrado en órbitas.
    
    Órbitas:
      Centro: El dato
      Ó1: Subsistemas de información
      Ó2: Roles/participantes
      Ó3: Organismos de la Alcaldía
      Ó4: Entidades externas
      Ó5: Sociedad civil
    """
    dato = get_object_or_404(DatoEcosistema, id=dato_id, es_maestro=True)
    sesion = dato.sesion
    
    # Todos los flujos que involucran este dato
    flujos = FlujoDatos.objects.filter(dato=dato).select_related(
        'participante', 'participante__rol_primario', 'participante__rol_primario__familia',
        'participante__rol_secundario',
        'recibe_de_participante', 'recibe_de_participante__rol_primario',
        'recibe_de_participante__rol_primario__familia',
        'envia_a_participante', 'envia_a_participante__rol_primario',
        'envia_a_participante__rol_primario__familia',
        'recibe_de_subsistema', 'envia_a_subsistema',
        'recibe_de_organismo', 'envia_a_organismo',
    )
    
    # Clasificaciones de este dato
    clasificaciones = ClasificacionDato.objects.filter(dato=dato).select_related('participante')
    
    # Recopilar actores por tipo
    participantes_map = {}
    subsistemas_map = {}
    organismos_map = {}
    entidades_externas_map = {}
    hay_sociedad_civil = False
    flujos_data = []
    
    for f in flujos:
        # Participante central
        p = f.participante
        if p.id not in participantes_map:
            rol = p.rol_primario
            participantes_map[p.id] = {
                'id': p.id,
                'nombre': p.nombre_completo,
                'cargo': p.cargo or '',
                'area': p.area_funcional or '',
                'rol_nombre': rol.nombre if rol else 'Sin rol',
                'familia_codigo': rol.familia.codigo if rol and rol.familia else '',
                'familia_color': rol.familia.color_hex if rol and rol.familia else '#6B7280',
            }
        
        # Recibe de
        if f.recibe_de_participante and f.recibe_de_participante.id not in participantes_map:
            rp = f.recibe_de_participante
            rol_rp = rp.rol_primario
            participantes_map[rp.id] = {
                'id': rp.id, 'nombre': rp.nombre_completo,
                'cargo': rp.cargo or '', 'area': rp.area_funcional or '',
                'rol_nombre': rol_rp.nombre if rol_rp else 'Sin rol',
                'familia_codigo': rol_rp.familia.codigo if rol_rp and rol_rp.familia else '',
                'familia_color': rol_rp.familia.color_hex if rol_rp and rol_rp.familia else '#6B7280',
            }
        if f.recibe_de_subsistema and f.recibe_de_subsistema.id not in subsistemas_map:
            sub = f.recibe_de_subsistema
            subsistemas_map[sub.id] = {'id': sub.id, 'nombre': sub.nombre, 'tipo': sub.tipo}
        if f.recibe_de_organismo and f.recibe_de_organismo.id not in organismos_map:
            org = f.recibe_de_organismo
            organismos_map[org.id] = {'id': org.id, 'nombre': org.nombre}
        if f.recibe_de_sociedad_civil:
            hay_sociedad_civil = True
        if f.recibe_de_entidad_externa:
            nombre = f.recibe_de_entidad_externa
            if nombre not in entidades_externas_map:
                entidades_externas_map[nombre] = {
                    'nombre': nombre,
                    'tipo': f.recibe_de_tipo_entidad or 'otro'
                }
        
        # Envía a
        if f.envia_a_participante and f.envia_a_participante.id not in participantes_map:
            ep = f.envia_a_participante
            rol_ep = ep.rol_primario
            participantes_map[ep.id] = {
                'id': ep.id, 'nombre': ep.nombre_completo,
                'cargo': ep.cargo or '', 'area': ep.area_funcional or '',
                'rol_nombre': rol_ep.nombre if rol_ep else 'Sin rol',
                'familia_codigo': rol_ep.familia.codigo if rol_ep and rol_ep.familia else '',
                'familia_color': rol_ep.familia.color_hex if rol_ep and rol_ep.familia else '#6B7280',
            }
        if f.envia_a_subsistema and f.envia_a_subsistema.id not in subsistemas_map:
            sub = f.envia_a_subsistema
            subsistemas_map[sub.id] = {'id': sub.id, 'nombre': sub.nombre, 'tipo': sub.tipo}
        if f.envia_a_organismo and f.envia_a_organismo.id not in organismos_map:
            org = f.envia_a_organismo
            organismos_map[org.id] = {'id': org.id, 'nombre': org.nombre}
        if f.envia_a_sociedad_civil:
            hay_sociedad_civil = True
        if f.envia_a_entidad_externa:
            nombre = f.envia_a_entidad_externa
            if nombre not in entidades_externas_map:
                entidades_externas_map[nombre] = {
                    'nombre': nombre,
                    'tipo': f.envia_a_tipo_entidad or 'otro'
                }
        
        # Serializar flujo
        rol_f = p.rol_primario if f.rol_usado == 'primario' else p.rol_secundario
        flujos_data.append({
            'id': f.id,
            'tipo': f.tipo,
            'participante_id': f.participante_id,
            'rol_usado': f.rol_usado,
            'rol_nombre': rol_f.nombre if rol_f else 'Sin rol',
            'recibe_de_participante_id': f.recibe_de_participante_id,
            'recibe_de_subsistema_id': f.recibe_de_subsistema_id,
            'recibe_de_organismo_id': f.recibe_de_organismo_id,
            'recibe_de_sociedad_civil': f.recibe_de_sociedad_civil,
            'recibe_de_entidad_externa': f.recibe_de_entidad_externa,
            'envia_a_participante_id': f.envia_a_participante_id,
            'envia_a_subsistema_id': f.envia_a_subsistema_id,
            'envia_a_organismo_id': f.envia_a_organismo_id,
            'envia_a_sociedad_civil': f.envia_a_sociedad_civil,
            'envia_a_entidad_externa': f.envia_a_entidad_externa,
            'descripcion_datos': f.descripcion_datos,
            'frecuencia': f.frecuencia or '',
            'formato': f.formato or '',
            'tipo_interaccion_recibe': f.tipo_interaccion_recibe,
            'tipo_interaccion_envia': f.tipo_interaccion_envia,
        })
    
    # Clasificaciones serializadas
    clasif_data = [{
        'id': c.id,
        'nivel': c.nivel,
        'sensibilidad': c.sensibilidad,
        'participante': c.participante.nombre_completo if c.participante else None,
    } for c in clasificaciones]
    
    return JsonResponse({
        'dato': {
            'id': dato.id,
            'nombre': dato.nombre,
            'descripcion': dato.descripcion,
            'nivel': dato.nivel,
            'sensibilidad': dato.sensibilidad,
            'origen': dato.origen,
            'periodicidad': dato.periodicidad,
            'proposito': dato.proposito,
            'principales_usuarios': dato.principales_usuarios,
            'valor_publico': dato.valor_publico,
        },
        'sesion': {
            'id': sesion.id,
            'organismo': sesion.organismo.nombre if sesion.organismo else '',
        },
        'participantes': list(participantes_map.values()),
        'subsistemas': list(subsistemas_map.values()),
        'organismos': list(organismos_map.values()),
        'entidades_externas': list(entidades_externas_map.values()),
        'hay_sociedad_civil': hay_sociedad_civil,
        'flujos': flujos_data,
        'clasificaciones': clasif_data,
        'stats': {
            'total_flujos': len(flujos_data),
            'total_participantes': len(participantes_map),
            'total_subsistemas': len(subsistemas_map),
            'total_organismos': len(organismos_map),
            'total_entidades_externas': len(entidades_externas_map),
        },
        # Relaciones entre datos (linaje)
        'relaciones_salientes': [
            {
                'id': r.id,
                'tipo_relacion': r.tipo_relacion,
                'tipo_relacion_display': r.get_tipo_relacion_display(),
                'descripcion': r.descripcion,
                'dato_destino': {
                    'id': r.dato_destino.id,
                    'nombre': r.dato_destino.nombre,
                    'nivel': r.dato_destino.nivel,
                },
                'proceso_transformacion': r.proceso_transformacion,
                'periodicidad': r.periodicidad_transformacion,
            }
            for r in RelacionDato.objects.filter(dato_origen=dato).select_related('dato_destino')
        ],
        'relaciones_entrantes': [
            {
                'id': r.id,
                'tipo_relacion': r.tipo_relacion,
                'tipo_relacion_display': r.get_tipo_relacion_display(),
                'descripcion': r.descripcion,
                'dato_origen': {
                    'id': r.dato_origen.id,
                    'nombre': r.dato_origen.nombre,
                    'nivel': r.dato_origen.nivel,
                },
                'proceso_transformacion': r.proceso_transformacion,
                'periodicidad': r.periodicidad_transformacion,
            }
            for r in RelacionDato.objects.filter(dato_destino=dato).select_related('dato_origen')
        ],
    })


# ============================================================================
# DATOS DEL ECOSISTEMA (FICHA P1 Y CURADURÍA)
# ============================================================================

@requiere_facilitador
def api_datos_ecosistema(request, sesion_id):
    """API para gestionar datos del ecosistema.
    GET: Retorna todos los datos maestros para usar en dropdowns de flujos
    POST: Participante crea un nuevo dato (requiere token en body)
    REQUIERE: Header X-Facilitador-Token para facilitador, o token de participante para POST.
    """
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    if request.method == 'GET':
        # Retornar todos los datos maestros como nodos del ecosistema
        datos = DatoEcosistema.objects.filter(
            sesion=sesion, es_maestro=True
        ).select_related('creado_por').annotate(
            num_flujos=Count('flujos'),
            num_clasificaciones=Count('clasificaciones'),
        )
        data = [{
            'id': d.id,
            'nombre': d.nombre,
            'descripcion': d.descripcion,
            'creado_por': d.creado_por.nombre_completo if d.creado_por else 'Anónimo',
            # Sección A
            'origen': d.origen,
            'mecanismo_recoleccion': d.mecanismo_recoleccion,
            'periodicidad': d.periodicidad,
            'proposito': d.proposito,
            # Sección B
            'nivel': d.nivel,
            'sensibilidad': d.sensibilidad,
            'capas_involucradas': d.capas_involucradas,
            # Sección C
            'principales_usuarios': d.principales_usuarios,
            'proposito_detallado': d.proposito_detallado,
            'valor_publico': d.valor_publico,
            # Métricas de conectividad
            'num_flujos': d.num_flujos,
            'num_clasificaciones': d.num_clasificaciones,
            'es_huerfano': d.num_flujos == 0,
            'es_critico': d.num_flujos >= 5,
        } for d in datos]
        return JsonResponse({'datos': data})
        
    elif request.method == 'POST':
        # Participante crea un nuevo dato
        try:
            body = json.loads(request.body)
            nombre = body.get('nombre')
            token = body.get('token')
            
            if not nombre or not token:
                return JsonResponse({'error': 'Faltan datos'}, status=400)
                
            participante = get_object_or_404(ParticipanteTaller, token_sesion=token)
            
            nuevo_dato = DatoEcosistema.objects.create(
                sesion=sesion,
                nombre=nombre,
                creado_por=participante,
                es_maestro=True  # Por defecto es maestro hasta que se fusione
            )
            
            return JsonResponse({
                'success': True, 
                'dato': {
                    'id': nuevo_dato.id,
                    'nombre': nuevo_dato.nombre
                }
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

@require_POST
@requiere_facilitador
def api_fusionar_datos(request, sesion_id):
    """El facilitador fusiona un dato en otro (Dato 1 se fusiona en Dato Maestro)
    REQUIERE: Header X-Facilitador-Token con el código de la sesión.
    """
    try:
        body = json.loads(request.body)
        dato_origen_id = body.get('dato_origen_id')
        dato_maestro_id = body.get('dato_maestro_id')
        
        dato_origen = get_object_or_404(DatoEcosistema, id=dato_origen_id, sesion_id=sesion_id)
        dato_maestro = get_object_or_404(DatoEcosistema, id=dato_maestro_id, sesion_id=sesion_id)
        
        # Marcar como no maestro y vincular
        dato_origen.es_maestro = False
        dato_origen.fusionado_con = dato_maestro
        dato_origen.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@require_http_methods(['DELETE'])
@requiere_facilitador
def api_eliminar_dato(request, sesion_id, dato_id):
    """Elimina un dato del ecosistema.
    REQUIERE: Header X-Facilitador-Token con el código de la sesión.
    """
    dato = get_object_or_404(DatoEcosistema, id=dato_id, sesion_id=sesion_id)
    dato.delete()
    return JsonResponse({'success': True})

# ============================================================================
# MAPA DE CIUDAD (todos los organismos juntos)
# ============================================================================

@require_GET
def ecosistema_grafo_ciudad(request):
    """
    Agrega los flujos de TODAS las sesiones en un grafo de ciudad.
    Nodos: organismos (cada sesión activa/finalizada), sociedad civil, entidades externas.
    Aristas: flujos inter-organismo (recibe_de_organismo / envia_a_organismo).
    DATOS como nodos satélites: cada organismo tiene sus datos orbitando alrededor (Torres 2026).
    """
    from django.db.models import Count
    
    sesiones = SesionTaller.objects.filter(
        estado__in=['activa', 'finalizada']
    ).select_related('organismo').prefetch_related(
        'flujos',
        'flujos__participante',
        'flujos__recibe_de_organismo',
        'flujos__envia_a_organismo',
    )

    # Nodos: un nodo por organismo con sesión
    organismos = {}
    for sesion in sesiones:
        if not sesion.organismo:
            continue
        oid = sesion.organismo.id
        if oid not in organismos:
            organismos[oid] = {
                'id': oid,
                'nombre': sesion.organismo.nombre,
                'codigo': getattr(sesion.organismo, 'codigo', ''),
                'sesiones': [],
                'num_participantes': 0,
                'num_flujos': 0,
            }
        organismos[oid]['sesiones'].append(sesion.id)
        organismos[oid]['num_participantes'] += sesion.participantes.filter(presente=True).count()
        organismos[oid]['num_flujos'] += sesion.flujos.count()

    # Aristas: flujos que cruzan organismos
    flujos_ciudad = []
    entidades_externas_dict = {}  # Deduplicar por nombre exacto
    hay_sociedad_civil = False

    # Obtener clasificaciones para estilos de flujo
    clasificaciones_map = {}
    for sesion in sesiones:
        for c in sesion.clasificaciones.all():
            clasificaciones_map[c.nombre_dato] = {
                'nivel': c.nivel,
                'sensibilidad': c.sensibilidad
            }
    
    for sesion in sesiones:
        if not sesion.organismo:
            continue
        sesion_org_id = sesion.organismo.id
        sesion_org_nombre = sesion.organismo.nombre

        for f in sesion.flujos.all():
            if f.recibe_de_sociedad_civil or f.envia_a_sociedad_civil:
                hay_sociedad_civil = True
            if f.recibe_de_entidad_externa:
                # Deduplicar: usar nombre como clave
                nombre = f.recibe_de_entidad_externa.strip()
                if nombre and nombre not in entidades_externas_dict:
                    entidades_externas_dict[nombre] = {
                        'nombre': nombre,
                        'tipo_entidad': f.recibe_de_tipo_entidad or 'otro',
                    }
            if f.envia_a_entidad_externa:
                # También agregar entidades que reciben datos de este organismo
                nombre = f.envia_a_entidad_externa.strip()
                if nombre and nombre not in entidades_externas_dict:
                    entidades_externas_dict[nombre] = {
                        'nombre': nombre,
                        'tipo_entidad': f.envia_a_tipo_entidad or 'otro',
                    }
            # Flujo: sociedad civil → este organismo
            if f.recibe_de_sociedad_civil:
                clasificacion = clasificaciones_map.get(f.descripcion_datos, {})
                flujos_ciudad.append({
                    'id': f'f{f.id}_sc_in',
                    'origen_tipo': 'sociedad_civil',
                    'origen_id': 'sociedad_civil',
                    'origen_nombre': 'Sociedad Civil / Ciudadanía',
                    'destino_tipo': 'organismo',
                    'destino_id': sesion_org_id,
                    'destino_nombre': sesion_org_nombre,
                    'descripcion_datos': f.descripcion_datos,
                    'tipo': f.tipo,
                    'frecuencia': f.frecuencia,
                    'formato': f.formato,
                    'nivel': clasificacion.get('nivel', 'operativo'),
                    'sensibilidad': clasificacion.get('sensibilidad', None),
                    # Torres 2026: tipo de interacción
                    'tipo_interaccion': f.tipo_interaccion_recibe or f.tipo_interaccion_envia or 'IF',
                })
            # Flujo: este organismo → sociedad civil
            if f.envia_a_sociedad_civil:
                clasificacion = clasificaciones_map.get(f.descripcion_datos, {})
                flujos_ciudad.append({
                    'id': f'f{f.id}_sc_out',
                    'origen_tipo': 'organismo',
                    'origen_id': sesion_org_id,
                    'origen_nombre': sesion_org_nombre,
                    'destino_tipo': 'sociedad_civil',
                    'destino_id': 'sociedad_civil',
                    'destino_nombre': 'Sociedad Civil / Ciudadanía',
                    'descripcion_datos': f.descripcion_datos,
                    'tipo': f.tipo,
                    'frecuencia': f.frecuencia,
                    'formato': f.formato,
                    'nivel': clasificacion.get('nivel', 'operativo'),
                    'sensibilidad': clasificacion.get('sensibilidad', None),
                    # Torres 2026: tipo de interacción
                    'tipo_interaccion': f.tipo_interaccion_recibe or f.tipo_interaccion_envia or 'IF',
                })
            # Flujo: entidad externa → este organismo
            if f.recibe_de_entidad_externa:
                clasificacion = clasificaciones_map.get(f.descripcion_datos, {})
                flujos_ciudad.append({
                    'id': f'f{f.id}_ext_in',
                    'origen_tipo': 'entidad_externa',
                    'origen_id': None,
                    'origen_nombre': f.recibe_de_entidad_externa,
                    'origen_tipo_entidad': f.recibe_de_tipo_entidad or 'otro',
                    'destino_tipo': 'organismo',
                    'destino_id': sesion_org_id,
                    'destino_nombre': sesion_org_nombre,
                    'descripcion_datos': f.descripcion_datos,
                    'tipo': f.tipo,
                    'frecuencia': f.frecuencia,
                    'formato': f.formato,
                    'nivel': clasificacion.get('nivel', 'operativo'),
                    'sensibilidad': clasificacion.get('sensibilidad', None),
                })
            # Flujo: este organismo → entidad externa
            if f.envia_a_entidad_externa:
                clasificacion = clasificaciones_map.get(f.descripcion_datos, {})
                flujos_ciudad.append({
                    'id': f'f{f.id}_ext_out',
                    'origen_tipo': 'organismo',
                    'origen_id': sesion_org_id,
                    'origen_nombre': sesion_org_nombre,
                    'destino_tipo': 'entidad_externa',
                    'destino_id': None,
                    'destino_nombre': f.envia_a_entidad_externa,
                    'destino_tipo_entidad': f.envia_a_tipo_entidad or 'otro',
                    'descripcion_datos': f.descripcion_datos,
                    'tipo': f.tipo,
                    'frecuencia': f.frecuencia,
                    'formato': f.formato,
                    'nivel': clasificacion.get('nivel', 'operativo'),
                    'sensibilidad': clasificacion.get('sensibilidad', None),
                    # Torres 2026: tipo de interacción
                    'tipo_interaccion': f.tipo_interaccion_recibe or f.tipo_interaccion_envia or 'IF',
                })
    
    # DATOS como nodos satélites (Torres 2026)
    # Agregar datos de cada sesión agrupados por organismo
    from .models import DatoEcosistema
    datos_por_organismo = {}
    for sesion in sesiones:
        if not sesion.organismo:
            continue
        oid = sesion.organismo.id
        if oid not in datos_por_organismo:
            datos_por_organismo[oid] = []
        
        # Obtener datos de esta sesión
        datos_sesion = DatoEcosistema.objects.filter(
            sesion=sesion, es_maestro=True
        ).annotate(num_flujos=Count('flujos'))
        
        for dato in datos_sesion:
            datos_por_organismo[oid].append({
                'id': dato.id,
                'nombre': dato.nombre,
                'nivel': dato.nivel,
                'sensibilidad': dato.sensibilidad,
                'num_flujos': dato.num_flujos,
                'es_huerfano': dato.num_flujos == 0,
                'es_critico': dato.num_flujos >= 5,
                'sesion_id': sesion.id,
            })

    return JsonResponse({
        'organismos': list(organismos.values()),
        'flujos': flujos_ciudad,
        'hay_sociedad_civil': hay_sociedad_civil,
        'entidades_externas': list(entidades_externas_dict.values()),
        'datos_por_organismo': datos_por_organismo,  # Torres 2026: datos como nodos satélites
    })


@require_GET
def ecosistema_ciudad_expandido(request):
    """
    API expandida: retorna datos completos de cada organismo para vista expandida.
    Incluye participantes, subsistemas, y flujos internos de cada sesión.
    """
    sesiones = SesionTaller.objects.filter(
        estado__in=['activa', 'finalizada']
    ).select_related('organismo').prefetch_related(
        'participantes', 'participantes__rol_primario', 'participantes__rol_secundario',
        'subsistemas', 'flujos'
    )

    organismos_expandidos = []
    
    for sesion in sesiones:
        if not sesion.organismo:
            continue
            
        # Participantes
        participantes = []
        for p in sesion.participantes.filter(presente=True):
            participantes.append({
                'id': p.id,
                'nombre': p.nombre_completo,
                'rol_primario': p.rol_primario.nombre if p.rol_primario else '',
                'rol_primario_id': p.rol_primario.id if p.rol_primario else None,
                'rol_secundario': p.rol_secundario.nombre if p.rol_secundario else '',
                'rol_secundario_id': p.rol_secundario.id if p.rol_secundario else None,
            })
        
        # Subsistemas
        subsistemas = []
        for s in sesion.subsistemas.all():
            subsistemas.append({
                'id': s.id,
                'nombre': s.nombre,
                'descripcion': s.descripcion or '',
            })
        
        # Flujos internos (dentro del organismo)
        flujos_internos = []
        
        # Obtener clasificaciones para nivel y sensibilidad
        clasificaciones_map = {}
        for c in sesion.clasificaciones.all():
            clasificaciones_map[c.nombre_dato] = {
                'nivel': c.nivel,
                'sensibilidad': c.sensibilidad
            }
        
        for f in sesion.flujos.all():
            clasificacion = clasificaciones_map.get(f.descripcion_datos, {})
            flujos_internos.append({
                'id': f.id,
                'participante_id': f.participante.id if f.participante else None,
                'recibe_de_participante_id': f.recibe_de_participante_id,
                'recibe_de_subsistema_id': f.recibe_de_subsistema_id,
                'recibe_de_sociedad_civil': f.recibe_de_sociedad_civil,
                'recibe_de_organismo_id': f.recibe_de_organismo_id,
                'recibe_de_entidad_externa': f.recibe_de_entidad_externa,
                'recibe_de_tipo_entidad': f.recibe_de_tipo_entidad,
                'envia_a_participante_id': f.envia_a_participante_id,
                'envia_a_subsistema_id': f.envia_a_subsistema_id,
                'envia_a_sociedad_civil': f.envia_a_sociedad_civil,
                'envia_a_organismo_id': f.envia_a_organismo_id,
                'envia_a_entidad_externa': f.envia_a_entidad_externa,
                'envia_a_tipo_entidad': f.envia_a_tipo_entidad,
                'descripcion_datos': f.descripcion_datos,
                'tipo': f.tipo,
                # Torres 2026: Categorización de flujos
                'tipo_interaccion': f.tipo_interaccion_recibe or f.tipo_interaccion_envia or 'IF',
                'nivel': clasificacion.get('nivel', 'operativo'),
                'sensibilidad': clasificacion.get('sensibilidad', None),
            })
        
        organismos_expandidos.append({
            'sesion_id': sesion.id,
            'organismo_id': sesion.organismo.id,
            'organismo_nombre': sesion.organismo.nombre,
            'participantes': participantes,
            'subsistemas': subsistemas,
            'flujos': flujos_internos,
        })
    
    return JsonResponse({
        'organismos': organismos_expandidos,
    })


def taller_mapa_ciudad(request):
    """Pantalla 'Mapa de Ciudad': todos los organismos y sus flujos inter-organismo."""
    return render(request, 'indicadores/taller/mapa_ciudad.html', {})


# ============================================================================
# VISTA INSTITUCIONAL — CONSULTA NIVEL ESTRATÉGICO
# ============================================================================

def ecosistema_institucional_ciudad(request):
    """Vista institucional del Mapa de Ciudad: fondo blanco, estilo profesional."""
    return render(request, 'indicadores/taller/institucional/mapa_ciudad_institucional.html', {})


def ecosistema_institucional_organismo(request, sesion_id):
    """Vista institucional del ecosistema de un organismo específico."""
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    return render(request, 'indicadores/taller/institucional/mapa_organismo_institucional.html', {
        'sesion': sesion
    })


# ============================================================================
# EXPORTACIÓN GEXF (Gephi)
# ============================================================================

@require_GET
def ecosistema_export_gexf(request, sesion_id):
    """
    Exporta el grafo de una sesión en formato GEXF para importar en Gephi.
    """
    import xml.etree.ElementTree as ET
    from django.utils.timezone import now

    sesion = get_object_or_404(SesionTaller, id=sesion_id)

    # Reuse ecosistema_grafo logic
    participantes = list(sesion.participantes.filter(presente=True).select_related(
        'rol_primario__familia', 'rol_secundario__familia'
    ).values('id', 'nombre_completo', 'area_funcional',
             'rol_primario__nombre', 'rol_primario__familia__codigo'))

    subsistemas = list(sesion.subsistemas.values('id', 'nombre', 'tipo'))

    flujos = []
    for f in sesion.flujos.select_related(
        'participante', 'participante__rol_primario',
        'recibe_de_participante', 'recibe_de_subsistema', 'recibe_de_organismo',
        'envia_a_participante', 'envia_a_subsistema', 'envia_a_organismo'
    ):
        rol = f.participante.rol_primario if f.rol_usado == 'primario' else f.participante.rol_secundario
        flujos.append({
            'id': f.id,
            'participante_id': f.participante.id,
            'recibe_de_participante_id': f.recibe_de_participante_id,
            'recibe_de_subsistema_id': f.recibe_de_subsistema_id,
            'recibe_de_sociedad_civil': f.recibe_de_sociedad_civil,
            'recibe_de_organismo_id': f.recibe_de_organismo_id,
            'recibe_de_organismo_nombre': f.recibe_de_organismo.nombre if f.recibe_de_organismo else None,
            'recibe_de_entidad_externa': f.recibe_de_entidad_externa,
            'recibe_de_tipo_entidad': f.recibe_de_tipo_entidad,
            'envia_a_participante_id': f.envia_a_participante_id,
            'envia_a_subsistema_id': f.envia_a_subsistema_id,
            'envia_a_sociedad_civil': f.envia_a_sociedad_civil,
            'envia_a_organismo_id': f.envia_a_organismo_id,
            'envia_a_organismo_nombre': f.envia_a_organismo.nombre if f.envia_a_organismo else None,
            'envia_a_entidad_externa': f.envia_a_entidad_externa,
            'envia_a_tipo_entidad': f.envia_a_tipo_entidad,
            'descripcion_datos': f.descripcion_datos,
            'tipo': f.tipo,
            'frecuencia': f.frecuencia or '',
            'formato': f.formato or '',
            'rol_nombre': rol.nombre if rol else 'Sin rol',
        })

    # Build GEXF
    gexf = ET.Element('gexf', {
        'xmlns': 'http://gexf.net/1.3',
        'xmlns:viz': 'http://gexf.net/1.3/viz',
        'version': '1.3',
    })
    meta = ET.SubElement(gexf, 'meta', lastmodifieddate=now().strftime('%Y-%m-%d'))
    ET.SubElement(meta, 'creator').text = 'Sistema de Talleres de Datos'
    ET.SubElement(meta, 'description').text = f'Ecosistema de datos - {sesion.organismo.nombre if sesion.organismo else sesion.nombre_sesion}'

    graph = ET.SubElement(gexf, 'graph', defaultedgetype='directed', mode='static')

    # Attributes
    attribs = ET.SubElement(graph, 'attributes', {'class': 'node', 'mode': 'static'})
    ET.SubElement(attribs, 'attribute', id='tipo', title='Tipo de nodo', type='string')
    ET.SubElement(attribs, 'attribute', id='rol', title='Rol', type='string')
    ET.SubElement(attribs, 'attribute', id='area', title='Área funcional', type='string')

    edge_attribs = ET.SubElement(graph, 'attributes', {'class': 'edge', 'mode': 'static'})
    ET.SubElement(edge_attribs, 'attribute', id='tipo_flujo', title='Tipo de flujo', type='string')
    ET.SubElement(edge_attribs, 'attribute', id='datos', title='Descripción de datos', type='string')
    ET.SubElement(edge_attribs, 'attribute', id='frecuencia', title='Frecuencia', type='string')
    ET.SubElement(edge_attribs, 'attribute', id='formato', title='Formato', type='string')

    nodes_el = ET.SubElement(graph, 'nodes')
    edges_el = ET.SubElement(graph, 'edges')

    node_ids = set()

    def add_node(node_id, label, tipo, rol='', area='', color=None):
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        n = ET.SubElement(nodes_el, 'node', id=str(node_id), label=label)
        av = ET.SubElement(n, 'attvalues')
        ET.SubElement(av, 'attvalue', **{'for': 'tipo', 'value': tipo})
        ET.SubElement(av, 'attvalue', **{'for': 'rol', 'value': rol})
        ET.SubElement(av, 'attvalue', **{'for': 'area', 'value': area})
        if color:
            viz = ET.SubElement(n, '{http://gexf.net/1.3/viz}color')
            viz.set('r', str(color[0]))
            viz.set('g', str(color[1]))
            viz.set('b', str(color[2]))

    # Add participant nodes
    for p in participantes:
        add_node(f"p_{p['id']}", p['nombre_completo'], 'participante',
                 rol=p['rol_primario__nombre'] or '', area=p['area_funcional'] or '')

    # Add subsystem nodes
    for s in subsistemas:
        add_node(f"sub_{s['id']}", s['nombre'], 'subsistema')

    # Add special nodes and edges from flujos
    edge_counter = 0
    for f in flujos:
        # Determine origin node
        if f['recibe_de_participante_id']:
            origen_id = f"p_{f['recibe_de_participante_id']}"
        elif f['recibe_de_subsistema_id']:
            origen_id = f"sub_{f['recibe_de_subsistema_id']}"
        elif f['recibe_de_sociedad_civil']:
            add_node('sociedad_civil', 'Sociedad Civil / Ciudadanía', 'sociedad_civil', color=(59, 130, 246))
            origen_id = 'sociedad_civil'
        elif f['recibe_de_organismo_id']:
            nid = f"org_{f['recibe_de_organismo_id']}"
            add_node(nid, f['recibe_de_organismo_nombre'] or nid, 'organismo_alcaldia', color=(245, 158, 11))
            origen_id = nid
        elif f['recibe_de_entidad_externa']:
            safe = f['recibe_de_entidad_externa'].replace(' ', '_')
            add_node(f"ext_{safe}", f['recibe_de_entidad_externa'], 'entidad_externa')
            origen_id = f"ext_{safe}"
        else:
            origen_id = None

        # Determine destination node
        if f['envia_a_participante_id']:
            destino_id = f"p_{f['envia_a_participante_id']}"
        elif f['envia_a_subsistema_id']:
            destino_id = f"sub_{f['envia_a_subsistema_id']}"
        elif f['envia_a_sociedad_civil']:
            add_node('sociedad_civil', 'Sociedad Civil / Ciudadanía', 'sociedad_civil', color=(59, 130, 246))
            destino_id = 'sociedad_civil'
        elif f['envia_a_organismo_id']:
            nid = f"org_{f['envia_a_organismo_id']}"
            add_node(nid, f['envia_a_organismo_nombre'] or nid, 'organismo_alcaldia', color=(245, 158, 11))
            destino_id = nid
        elif f['envia_a_entidad_externa']:
            safe = f['envia_a_entidad_externa'].replace(' ', '_')
            add_node(f"ext_{safe}", f['envia_a_entidad_externa'], 'entidad_externa')
            destino_id = f"ext_{safe}"
        else:
            destino_id = None

        centro_id = f"p_{f['participante_id']}"

        # Edge: origin → participant
        if origen_id:
            e = ET.SubElement(edges_el, 'edge', id=str(edge_counter),
                              source=origen_id, target=centro_id,
                              label=f['descripcion_datos'][:80])
            av = ET.SubElement(e, 'attvalues')
            ET.SubElement(av, 'attvalue', **{'for': 'tipo_flujo', 'value': f['tipo']})
            ET.SubElement(av, 'attvalue', **{'for': 'datos', 'value': f['descripcion_datos']})
            ET.SubElement(av, 'attvalue', **{'for': 'frecuencia', 'value': f['frecuencia'] or ''})
            ET.SubElement(av, 'attvalue', **{'for': 'formato', 'value': f['formato'] or ''})
            edge_counter += 1

        # Edge: participant → destination
        if destino_id:
            e = ET.SubElement(edges_el, 'edge', id=str(edge_counter),
                              source=centro_id, target=destino_id,
                              label=f['descripcion_datos'][:80])
            av = ET.SubElement(e, 'attvalues')
            ET.SubElement(av, 'attvalue', **{'for': 'tipo_flujo', 'value': f['tipo']})
            ET.SubElement(av, 'attvalue', **{'for': 'datos', 'value': f['descripcion_datos']})
            ET.SubElement(av, 'attvalue', **{'for': 'frecuencia', 'value': f['frecuencia'] or ''})
            ET.SubElement(av, 'attvalue', **{'for': 'formato', 'value': f['formato'] or ''})
            edge_counter += 1

    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(gexf, encoding='unicode')
    nombre_archivo = f"ecosistema_{sesion.organismo.nombre if sesion.organismo else sesion.id}.gexf"
    nombre_archivo = nombre_archivo.replace(' ', '_').replace('/', '-')

    from django.http import HttpResponse
    response = HttpResponse(xml_str, content_type='application/gexf+xml; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    return response


@require_GET
def ecosistema_ciudad_export_gexf(request):
    """
    Exporta el grafo de ciudad completo (todos los organismos) en formato GEXF.
    """
    import xml.etree.ElementTree as ET
    from django.http import HttpResponse
    from django.utils.timezone import now

    sesiones = SesionTaller.objects.filter(
        estado__in=['activa', 'finalizada']
    ).select_related('organismo').prefetch_related(
        'flujos', 'flujos__recibe_de_organismo', 'flujos__envia_a_organismo'
    )

    gexf = ET.Element('gexf', {
        'xmlns': 'http://gexf.net/1.3',
        'xmlns:viz': 'http://gexf.net/1.3/viz',
        'version': '1.3',
    })
    meta = ET.SubElement(gexf, 'meta', lastmodifieddate=now().strftime('%Y-%m-%d'))
    ET.SubElement(meta, 'creator').text = 'Sistema de Talleres de Datos'
    ET.SubElement(meta, 'description').text = 'Mapa de Ciudad - Ecosistema Distrital de Datos'

    graph = ET.SubElement(gexf, 'graph', defaultedgetype='directed', mode='static')

    attribs = ET.SubElement(graph, 'attributes', {'class': 'node', 'mode': 'static'})
    ET.SubElement(attribs, 'attribute', id='tipo', title='Tipo de nodo', type='string')
    ET.SubElement(attribs, 'attribute', id='num_participantes', title='Participantes', type='integer')
    ET.SubElement(attribs, 'attribute', id='num_flujos', title='Flujos', type='integer')

    edge_attribs = ET.SubElement(graph, 'attributes', {'class': 'edge', 'mode': 'static'})
    ET.SubElement(edge_attribs, 'attribute', id='datos', title='Descripción de datos', type='string')
    ET.SubElement(edge_attribs, 'attribute', id='tipo_flujo', title='Tipo de flujo', type='string')

    nodes_el = ET.SubElement(graph, 'nodes')
    edges_el = ET.SubElement(graph, 'edges')

    node_ids = set()
    edge_counter = 0

    def add_node_ciudad(node_id, label, tipo, num_p=0, num_f=0, color=None):
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        n = ET.SubElement(nodes_el, 'node', id=str(node_id), label=label)
        av = ET.SubElement(n, 'attvalues')
        ET.SubElement(av, 'attvalue', **{'for': 'tipo', 'value': tipo})
        ET.SubElement(av, 'attvalue', **{'for': 'num_participantes', 'value': str(num_p)})
        ET.SubElement(av, 'attvalue', **{'for': 'num_flujos', 'value': str(num_f)})
        if color:
            viz = ET.SubElement(n, '{http://gexf.net/1.3/viz}color')
            viz.set('r', str(color[0]))
            viz.set('g', str(color[1]))
            viz.set('b', str(color[2]))

    for sesion in sesiones:
        if not sesion.organismo:
            continue
        oid = f"org_{sesion.organismo.id}"
        num_p = sesion.participantes.filter(presente=True).count()
        num_f = sesion.flujos.count()
        add_node_ciudad(oid, sesion.organismo.nombre, 'organismo', num_p, num_f, color=(74, 124, 44))

        for f in sesion.flujos.all():
            if f.recibe_de_sociedad_civil or f.envia_a_sociedad_civil:
                add_node_ciudad('sociedad_civil', 'Sociedad Civil / Ciudadanía',
                                'sociedad_civil', color=(59, 130, 246))
            if f.recibe_de_entidad_externa:
                safe = f.recibe_de_entidad_externa.replace(' ', '_')
                add_node_ciudad(f'ext_{safe}', f.recibe_de_entidad_externa,
                                'entidad_externa', color=(136, 136, 136))
            if f.envia_a_entidad_externa:
                safe = f.envia_a_entidad_externa.replace(' ', '_')
                add_node_ciudad(f'ext_{safe}', f.envia_a_entidad_externa,
                                'entidad_externa', color=(136, 136, 136))

            def add_edge(src, tgt, desc, tipo):
                nonlocal edge_counter
                e = ET.SubElement(edges_el, 'edge', id=str(edge_counter),
                                  source=src, target=tgt, label=desc[:80])
                av = ET.SubElement(e, 'attvalues')
                ET.SubElement(av, 'attvalue', **{'for': 'datos', 'value': desc})
                ET.SubElement(av, 'attvalue', **{'for': 'tipo_flujo', 'value': tipo})
                edge_counter += 1

            if f.recibe_de_organismo_id and f.recibe_de_organismo:
                add_edge(f'org_{f.recibe_de_organismo_id}', oid,
                         f.descripcion_datos, f.tipo)
            if f.envia_a_organismo_id and f.envia_a_organismo:
                add_edge(oid, f'org_{f.envia_a_organismo_id}',
                         f.descripcion_datos, f.tipo)
            if f.recibe_de_sociedad_civil:
                add_edge('sociedad_civil', oid, f.descripcion_datos, f.tipo)
            if f.envia_a_sociedad_civil:
                add_edge(oid, 'sociedad_civil', f.descripcion_datos, f.tipo)
            if f.recibe_de_entidad_externa:
                safe = f.recibe_de_entidad_externa.replace(' ', '_')
                add_edge(f'ext_{safe}', oid, f.descripcion_datos, f.tipo)
            if f.envia_a_entidad_externa:
                safe = f.envia_a_entidad_externa.replace(' ', '_')
                add_edge(oid, f'ext_{safe}', f.descripcion_datos, f.tipo)

    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(gexf, encoding='unicode')
    response = HttpResponse(xml_str, content_type='application/gexf+xml; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="mapa_ciudad_ecosistema.gexf"'
    return response


@require_GET
def ecosistema_ciudad_expandido_export_gexf(request):
    """
    Exporta el grafo de ciudad expandido (todos los sub-ecosistemas) en formato GEXF.
    SIN nodos de organismo - solo participantes, subsistemas, sociedad civil y entidades externas.
    Hace matching de flujos inter-organismo por nombre de dato.
    """
    import xml.etree.ElementTree as ET
    from django.http import HttpResponse
    from django.utils.timezone import now

    sesiones = SesionTaller.objects.filter(
        estado__in=['activa', 'finalizada']
    ).select_related('organismo').prefetch_related(
        'participantes', 'participantes__rol_primario', 'participantes__rol_secundario',
        'subsistemas', 'flujos'
    )

    gexf = ET.Element('gexf', {
        'xmlns': 'http://gexf.net/1.3',
        'xmlns:viz': 'http://gexf.net/1.3/viz',
        'version': '1.3',
    })
    meta = ET.SubElement(gexf, 'meta', lastmodifieddate=now().strftime('%Y-%m-%d'))
    ET.SubElement(meta, 'creator').text = 'Sistema de Talleres de Datos'
    ET.SubElement(meta, 'description').text = 'Mapa de Ciudad Expandido - Ecosistema Distrital de Datos (sin nodos organismo)'

    graph = ET.SubElement(gexf, 'graph', defaultedgetype='directed', mode='static')

    attribs = ET.SubElement(graph, 'attributes', {'class': 'node', 'mode': 'static'})
    ET.SubElement(attribs, 'attribute', id='tipo', title='Tipo de nodo', type='string')
    ET.SubElement(attribs, 'attribute', id='organismo', title='Organismo', type='string')
    ET.SubElement(attribs, 'attribute', id='rol', title='Rol', type='string')

    edge_attribs = ET.SubElement(graph, 'attributes', {'class': 'edge', 'mode': 'static'})
    ET.SubElement(edge_attribs, 'attribute', id='datos', title='Descripción de datos', type='string')
    ET.SubElement(edge_attribs, 'attribute', id='tipo_flujo', title='Tipo de flujo', type='string')
    ET.SubElement(edge_attribs, 'attribute', id='nivel', title='Nivel estratégico', type='string')
    ET.SubElement(edge_attribs, 'attribute', id='sensibilidad', title='Sensibilidad', type='string')
    ET.SubElement(edge_attribs, 'attribute', id='matched', title='Flujo matched entre organismos', type='boolean')

    nodes_el = ET.SubElement(graph, 'nodes')
    edges_el = ET.SubElement(graph, 'edges')

    node_ids = set()
    edge_counter = 0
    
    # Obtener clasificaciones
    clasificaciones_map = {}
    for sesion in sesiones:
        for c in sesion.clasificaciones.all():
            clasificaciones_map[c.nombre_dato] = {
                'nivel': c.nivel,
                'sensibilidad': c.sensibilidad
            }

    def add_node_exp(node_id, label, tipo, organismo='', rol='', color=None):
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        n = ET.SubElement(nodes_el, 'node', id=str(node_id), label=label)
        av = ET.SubElement(n, 'attvalues')
        ET.SubElement(av, 'attvalue', **{'for': 'tipo', 'value': tipo})
        ET.SubElement(av, 'attvalue', **{'for': 'organismo', 'value': organismo})
        ET.SubElement(av, 'attvalue', **{'for': 'rol', 'value': rol})
        if color:
            viz = ET.SubElement(n, '{http://gexf.net/1.3/viz}color')
            viz.set('r', str(color[0]))
            viz.set('g', str(color[1]))
            viz.set('b', str(color[2]))

    # Nodo de sociedad civil
    add_node_exp('sociedad_civil', 'Sociedad Civil / Ciudadanía', 'sociedad_civil', color=(59, 130, 246))

    # Entidades externas deduplicadas
    entidades_externas = set()
    for sesion in sesiones:
        for f in sesion.flujos.all():
            if f.recibe_de_entidad_externa:
                entidades_externas.add(f.recibe_de_entidad_externa.strip())
            if f.envia_a_entidad_externa:
                entidades_externas.add(f.envia_a_entidad_externa.strip())
    
    for ent in entidades_externas:
        safe = ent.replace(' ', '_')
        add_node_exp(f'ext_{safe}', ent, 'entidad_externa', color=(136, 136, 136))

    # Crear índice de flujos salientes por nombre de dato y organismo destino
    # Para hacer matching: {nombre_dato: {organismo_destino_id: [flujos_que_envian]}}
    flujos_salientes_por_dato = {}
    
    # Crear índice de flujos entrantes por nombre de dato y organismo origen
    # Para hacer matching: {nombre_dato: {organismo_origen_id: [flujos_que_reciben]}}
    flujos_entrantes_por_dato = {}

    # Nodos de cada organismo y sus sub-ecosistemas (SIN nodo organismo)
    for sesion in sesiones:
        if not sesion.organismo:
            continue
        
        org_nombre = sesion.organismo.nombre
        
        # Participantes
        for p in sesion.participantes.filter(presente=True):
            rol = p.rol_primario.nombre if p.rol_primario else ''
            add_node_exp(f'p_{sesion.id}_{p.id}', p.nombre_completo, 'participante', 
                        organismo=org_nombre, rol=rol, color=(16, 185, 129))
        
        # Subsistemas
        for s in sesion.subsistemas.all():
            add_node_exp(f'sub_{sesion.id}_{s.id}', s.nombre, 'subsistema',
                        organismo=org_nombre, color=(14, 165, 233))
        
        # Indexar flujos inter-organismo para matching
        for f in sesion.flujos.all():
            if f.envia_a_organismo_id:
                # Este flujo envía a otro organismo
                dato_key = f.descripcion_datos.strip().lower() if f.descripcion_datos else ''
                if dato_key:
                    if dato_key not in flujos_salientes_por_dato:
                        flujos_salientes_por_dato[dato_key] = {}
                    if f.envia_a_organismo_id not in flujos_salientes_por_dato[dato_key]:
                        flujos_salientes_por_dato[dato_key][f.envia_a_organismo_id] = []
                    flujos_salientes_por_dato[dato_key][f.envia_a_organismo_id].append({
                        'flujo': f,
                        'sesion_id': sesion.id,
                        'participante_id': f.participante_id
                    })
            
            if f.recibe_de_organismo_id:
                # Este flujo recibe de otro organismo
                dato_key = f.descripcion_datos.strip().lower() if f.descripcion_datos else ''
                if dato_key:
                    if dato_key not in flujos_entrantes_por_dato:
                        flujos_entrantes_por_dato[dato_key] = {}
                    if f.recibe_de_organismo_id not in flujos_entrantes_por_dato[dato_key]:
                        flujos_entrantes_por_dato[dato_key][f.recibe_de_organismo_id] = []
                    flujos_entrantes_por_dato[dato_key][f.recibe_de_organismo_id].append({
                        'flujo': f,
                        'sesion_id': sesion.id,
                        'participante_id': f.participante_id
                    })
    
    # Procesar flujos y crear edges
    flujos_matched = set()  # Para evitar duplicados
    
    for sesion in sesiones:
        if not sesion.organismo:
            continue
        
        for f in sesion.flujos.all():
            clasificacion = clasificaciones_map.get(f.descripcion_datos, {})
            nivel = clasificacion.get('nivel', 'operativo')
            sensibilidad = clasificacion.get('sensibilidad', '')
            
            # Determinar origen
            origen_id = None
            if f.recibe_de_participante_id:
                origen_id = f'p_{sesion.id}_{f.recibe_de_participante_id}'
            elif f.recibe_de_subsistema_id:
                origen_id = f'sub_{sesion.id}_{f.recibe_de_subsistema_id}'
            elif f.recibe_de_sociedad_civil:
                origen_id = 'sociedad_civil'
            elif f.recibe_de_entidad_externa:
                safe = f.recibe_de_entidad_externa.strip().replace(' ', '_')
                origen_id = f'ext_{safe}'
            elif f.recibe_de_organismo_id:
                # Flujo inter-organismo: buscar matching por nombre de dato
                dato_key = f.descripcion_datos.strip().lower() if f.descripcion_datos else ''
                if dato_key and dato_key in flujos_salientes_por_dato:
                    # Buscar flujos del organismo origen que envíen este dato a este organismo
                    if sesion.organismo.id in flujos_salientes_por_dato[dato_key]:
                        # Hay match! Conectar con el participante que envía
                        flujos_origen = flujos_salientes_por_dato[dato_key][sesion.organismo.id]
                        if flujos_origen:
                            # Tomar el primer match (podría haber múltiples)
                            flujo_origen = flujos_origen[0]
                            origen_id = f'p_{flujo_origen["sesion_id"]}_{flujo_origen["participante_id"]}'
            
            # Determinar destino
            destino_id = None
            if f.envia_a_participante_id:
                destino_id = f'p_{sesion.id}_{f.envia_a_participante_id}'
            elif f.envia_a_subsistema_id:
                destino_id = f'sub_{sesion.id}_{f.envia_a_subsistema_id}'
            elif f.envia_a_sociedad_civil:
                destino_id = 'sociedad_civil'
            elif f.envia_a_entidad_externa:
                safe = f.envia_a_entidad_externa.strip().replace(' ', '_')
                destino_id = f'ext_{safe}'
            elif f.envia_a_organismo_id:
                # Flujo inter-organismo: buscar matching por nombre de dato
                dato_key = f.descripcion_datos.strip().lower() if f.descripcion_datos else ''
                if dato_key and dato_key in flujos_entrantes_por_dato:
                    # Buscar flujos del organismo destino que reciban este dato de este organismo
                    if sesion.organismo.id in flujos_entrantes_por_dato[dato_key]:
                        # Hay match! Conectar con el participante que recibe
                        flujos_destino = flujos_entrantes_por_dato[dato_key][sesion.organismo.id]
                        if flujos_destino:
                            # Tomar el primer match
                            flujo_destino = flujos_destino[0]
                            destino_id = f'p_{flujo_destino["sesion_id"]}_{flujo_destino["participante_id"]}'
            
            centro_id = f'p_{sesion.id}_{f.participante_id}'
            is_matched = bool(f.recibe_de_organismo_id or f.envia_a_organismo_id)
            
            # Crear aristas
            if origen_id and centro_id:
                edge_key = f'{origen_id}_{centro_id}_{f.descripcion_datos}'
                if edge_key not in flujos_matched:
                    flujos_matched.add(edge_key)
                    e = ET.SubElement(edges_el, 'edge', id=str(edge_counter),
                                    source=origen_id, target=centro_id, label=(f.descripcion_datos or '')[:80])
                    av = ET.SubElement(e, 'attvalues')
                    ET.SubElement(av, 'attvalue', **{'for': 'datos', 'value': f.descripcion_datos or ''})
                    ET.SubElement(av, 'attvalue', **{'for': 'tipo_flujo', 'value': f.tipo or ''})
                    ET.SubElement(av, 'attvalue', **{'for': 'nivel', 'value': nivel or ''})
                    ET.SubElement(av, 'attvalue', **{'for': 'sensibilidad', 'value': sensibilidad or ''})
                    ET.SubElement(av, 'attvalue', **{'for': 'matched', 'value': str(is_matched).lower()})
                    edge_counter += 1
            
            if centro_id and destino_id:
                edge_key = f'{centro_id}_{destino_id}_{f.descripcion_datos}'
                if edge_key not in flujos_matched:
                    flujos_matched.add(edge_key)
                    e = ET.SubElement(edges_el, 'edge', id=str(edge_counter),
                                    source=centro_id, target=destino_id, label=(f.descripcion_datos or '')[:80])
                    av = ET.SubElement(e, 'attvalues')
                    ET.SubElement(av, 'attvalue', **{'for': 'datos', 'value': f.descripcion_datos or ''})
                    ET.SubElement(av, 'attvalue', **{'for': 'tipo_flujo', 'value': f.tipo or ''})
                    ET.SubElement(av, 'attvalue', **{'for': 'nivel', 'value': nivel or ''})
                    ET.SubElement(av, 'attvalue', **{'for': 'sensibilidad', 'value': sensibilidad or ''})
                    ET.SubElement(av, 'attvalue', **{'for': 'matched', 'value': str(is_matched).lower()})
                    edge_counter += 1

    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(gexf, encoding='unicode')
    response = HttpResponse(xml_str, content_type='application/gexf+xml; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="mapa_ciudad_expandido_ecosistema.gexf"'
    return response


@require_GET
def api_datos_participante(request, sesion_id):
    """Devuelve los datos creados por un participante específico para que los clasifique en la Ficha P2."""
    import logging
    logger = logging.getLogger(__name__)
    
    token = request.GET.get('token')
    if not token:
        return JsonResponse({'error': 'Falta token'}, status=400)
        
    participante = get_object_or_404(ParticipanteTaller, token_sesion=token, sesion_id=sesion_id)
    
    # Obtener los datos maestros que este participante haya creado (o donde su dato original haya terminado)
    # Por simplicidad, obtenemos los datos que él creó directamente. Si se fusionaron, traemos el maestro al que apuntan.
    datos_creados = DatoEcosistema.objects.filter(creado_por=participante)
    
    logger.info(f"[FICHA P2] Participante {participante.nombre_completo} (token={token[:8]}...)")
    logger.info(f"[FICHA P2] Datos creados en DatoEcosistema: {datos_creados.count()}")
    
    # Construir dict {id: dato_obj} de datos maestros a clasificar
    datos_a_clasificar = {}
    for d in datos_creados:
        logger.info(f"[FICHA P2]   - Dato: '{d.nombre}' (es_maestro={d.es_maestro}, fusionado_con={d.fusionado_con})")
        if d.es_maestro:
            datos_a_clasificar[d.id] = d
        elif d.fusionado_con:
            datos_a_clasificar[d.fusionado_con.id] = d.fusionado_con
    
    logger.info(f"[FICHA P2] Total datos a clasificar: {len(datos_a_clasificar)}")
            
    # Filtrar los que ya clasificó (por dato FK o nombre legacy)
    datos_ids = list(datos_a_clasificar.keys())
    datos_nombres = [d.nombre for d in datos_a_clasificar.values()]
    
    clasificados_ids = set(
        ClasificacionDato.objects.filter(
            sesion_id=sesion_id, 
            dato_id__in=datos_ids
        ).values_list('dato_id', flat=True)
    )
    # También buscar por nombre (legacy sin FK)
    clasificados_nombres = set(
        ClasificacionDato.objects.filter(
            sesion_id=sesion_id,
            nombre_dato__in=datos_nombres,
            dato__isnull=True
        ).values_list('nombre_dato', flat=True)
    )
    
    pendientes = []
    clasificados = []
    for dato_id, dato_obj in datos_a_clasificar.items():
        item = {'id': dato_obj.id, 'nombre': dato_obj.nombre, 'nivel': dato_obj.nivel or ''}
        if dato_id in clasificados_ids or dato_obj.nombre in clasificados_nombres:
            clasificados.append(item)
        else:
            pendientes.append(item)
    
    logger.info(f"[FICHA P2] Pendientes: {len(pendientes)}, Clasificados: {len(clasificados)}")
    
    return JsonResponse({
        'pendientes': pendientes,
        'clasificados': clasificados
    })


# ============================================================================
# CIERRE DEL TALLER - REPORTES Y EXPORTACIONES
# ============================================================================

@require_GET
def api_clasificaciones_sesion(request, sesion_id):
    """Obtiene todas las clasificaciones de una sesión para estadísticas de cierre."""
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    clasificaciones = ClasificacionDato.objects.filter(sesion=sesion).select_related(
        'participante'
    ).values(
        'id',
        'nombre_dato',
        'nivel',
        'sensibilidad',
        'mecanismo_recoleccion',
        'para_que_se_usa',
        'participante__nombre_completo'
    )
    
    return JsonResponse({
        'clasificaciones': list(clasificaciones)
    })


# ============================================================================
# HELPERS PARA GENERACIÓN DE REPORTES PDF
# ============================================================================

def _crear_estilos_pdf():
    """Crea y retorna los estilos personalizados para los PDFs."""
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2d5016'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2d5016'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    return {
        'title': title_style,
        'heading': heading_style,
        'normal': styles['Normal']
    }


def _crear_encabezado_pdf(sesion, estilos):
    """Crea el encabezado común para todos los reportes PDF."""
    story = []
    story.append(Paragraph(f"🌴 Taller del Ecosistema de Datos", estilos['title']))
    story.append(Paragraph(f"{sesion.organismo.nombre}", estilos['heading']))
    story.append(Paragraph(f"Sesión: {sesion.nombre_sesion}", estilos['normal']))
    story.append(Paragraph(f"Fecha: {sesion.fecha.strftime('%d/%m/%Y')}", estilos['normal']))
    story.append(Paragraph(f"Facilitador: {sesion.facilitador}", estilos['normal']))
    story.append(Spacer(1, 0.3*inch))
    return story


def _crear_pie_pagina_pdf(estilos):
    """Crea el pie de página común para todos los reportes PDF."""
    story = []
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph("_______________________________________________", estilos['normal']))
    story.append(Paragraph(f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}", estilos['normal']))
    story.append(Paragraph("Sistema SIIED - Subdirección de Desarrollo Integral", estilos['normal']))
    story.append(Paragraph("Departamento Administrativo de Planeación Distrital", estilos['normal']))
    story.append(Paragraph("Santiago de Cali, Colombia 🌴", estilos['normal']))
    return story


def _generar_reporte_ejecutivo(sesion, participantes, datos, flujos, clasificaciones, estilos):
    """Genera el contenido del reporte ejecutivo."""
    story = []
    story.append(Paragraph("📈 Reporte Ejecutivo", estilos['heading']))
    story.append(Spacer(1, 0.2*inch))
    
    # Métricas principales
    story.append(Paragraph("<b>Resumen de Participación</b>", estilos['normal']))
    story.append(Spacer(1, 0.1*inch))
    
    metricas_data = [
        ['Métrica', 'Valor'],
        ['Participantes', str(participantes.count())],
        ['Áreas representadas', str(participantes.values('area_funcional').distinct().count())],
        ['Roles identificados', str(participantes.filter(rol_primario__isnull=False).count())],
        ['Datos creados', str(datos.count())],
        ['Flujos mapeados', str(flujos.count())],
        ['Datos clasificados', str(clasificaciones.count())]
    ]
    
    tabla_metricas = Table(metricas_data, colWidths=[3*inch, 2*inch])
    tabla_metricas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d5016')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(tabla_metricas)
    story.append(Spacer(1, 0.3*inch))
    
    # Top 10 roles
    story.append(Paragraph("<b>Top 10 Roles Identificados</b>", estilos['normal']))
    story.append(Spacer(1, 0.1*inch))
    
    roles_count = {}
    for p in participantes.filter(rol_primario__isnull=False):
        rol_nombre = p.rol_primario.nombre
        roles_count[rol_nombre] = roles_count.get(rol_nombre, 0) + 1
    
    top_roles = sorted(roles_count.items(), key=lambda x: x[1], reverse=True)[:10]
    
    if top_roles:
        roles_data = [['Rol', 'Cantidad']]
        for rol, count in top_roles:
            roles_data.append([rol, str(count)])
        
        tabla_roles = Table(roles_data, colWidths=[4*inch, 1*inch])
        tabla_roles.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d5016')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(tabla_roles)
    
    return story


def _generar_reporte_tecnico(sesion, participantes, flujos, clasificaciones, estilos):
    """Genera el contenido del reporte técnico."""
    story = []
    story.append(Paragraph("🔧 Reporte Técnico", estilos['heading']))
    story.append(Spacer(1, 0.2*inch))
    
    # Análisis por familia de roles
    story.append(Paragraph("<b>Análisis por Familia de Roles</b>", estilos['normal']))
    story.append(Spacer(1, 0.1*inch))
    
    familias = FamiliaRol.objects.all().order_by('codigo')
    familias_data = [['Familia', 'Roles Asignados']]
    
    for familia in familias:
        count = participantes.filter(rol_primario__familia=familia).count()
        familias_data.append([f"{familia.codigo}: {familia.nombre}", str(count)])
    
    tabla_familias = Table(familias_data, colWidths=[4*inch, 1.5*inch])
    tabla_familias.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d5016')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(tabla_familias)
    story.append(Spacer(1, 0.3*inch))
    
    # Matriz de flujos
    story.append(Paragraph("<b>Matriz de Flujos de Datos</b>", estilos['normal']))
    story.append(Spacer(1, 0.1*inch))
    
    flujos_internos = flujos.filter(tipo='interno').count()
    flujos_inter = flujos.filter(tipo='inter_sub').count()
    flujos_externos = flujos.filter(tipo='externo').count()
    
    flujos_data = [
        ['Tipo de Flujo', 'Cantidad'],
        ['Internos (mismo subsistema)', str(flujos_internos)],
        ['Inter-subsistemas', str(flujos_inter)],
        ['Externos (entidades, sociedad civil)', str(flujos_externos)],
        ['TOTAL', str(flujos.count())]
    ]
    
    tabla_flujos = Table(flujos_data, colWidths=[4*inch, 1.5*inch])
    tabla_flujos.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d5016')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FFD700')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(tabla_flujos)
    story.append(Spacer(1, 0.3*inch))
    
    # Clasificación de datos
    story.append(Paragraph("<b>Clasificación de Datos</b>", estilos['normal']))
    story.append(Spacer(1, 0.1*inch))
    
    clasif_operativo = clasificaciones.filter(nivel='operativo').count()
    clasif_tactico = clasificaciones.filter(nivel='tactico').count()
    clasif_estrategico = clasificaciones.filter(nivel='estrategico').count()
    
    clasif_data = [
        ['Nivel de Importancia', 'Cantidad'],
        ['Operativo', str(clasif_operativo)],
        ['Táctico', str(clasif_tactico)],
        ['Estratégico', str(clasif_estrategico)]
    ]
    
    tabla_clasif = Table(clasif_data, colWidths=[4*inch, 1.5*inch])
    tabla_clasif.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d5016')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(tabla_clasif)
    
    return story


def _generar_reporte_organismo(sesion, participantes, datos, flujos, clasificaciones, estilos):
    """Genera el contenido del reporte para el organismo."""
    story = []
    story.append(Paragraph("🏢 Reporte para el Organismo", estilos['heading']))
    story.append(Spacer(1, 0.2*inch))
    
    story.append(Paragraph("<b>Ecosistema de Datos Identificado</b>", estilos['normal']))
    story.append(Spacer(1, 0.1*inch))
    
    resumen_text = f"""
    Durante el taller se identificaron <b>{participantes.count()} participantes</b> de diferentes áreas funcionales,
    quienes mapearon <b>{datos.count()} datos del ecosistema</b> y <b>{flujos.count()} flujos de información</b>.
    Se clasificaron <b>{clasificaciones.count()} datos</b> según su nivel de importancia estratégica y sensibilidad.
    """
    story.append(Paragraph(resumen_text, estilos['normal']))
    story.append(Spacer(1, 0.2*inch))
    
    story.append(Paragraph("<b>Fortalezas Identificadas</b>", estilos['normal']))
    story.append(Spacer(1, 0.1*inch))
    
    fortalezas = [
        f"• Alta participación de áreas funcionales ({participantes.values('area_funcional').distinct().count()} áreas)",
        f"• Identificación de {datos.count()} datos clave del ecosistema",
        f"• Mapeo de {flujos.count()} flujos de información",
        "• Compromiso del equipo en la gestión de datos"
    ]
    
    for fortaleza in fortalezas:
        story.append(Paragraph(fortaleza, estilos['normal']))
    
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("<b>Próximos Pasos Sugeridos</b>", estilos['normal']))
    story.append(Spacer(1, 0.1*inch))
    
    pasos = [
        "1. Revisar y validar los datos identificados con cada área",
        "2. Implementar controles de calidad en los flujos críticos",
        "3. Establecer políticas de acceso según clasificación de sensibilidad",
        "4. Capacitar al equipo en gestión de datos según roles identificados",
        "5. Monitorear y actualizar el ecosistema de datos periódicamente"
    ]
    
    for paso in pasos:
        story.append(Paragraph(paso, estilos['normal']))
    
    return story


@require_GET
def generar_reporte_pdf(request, sesion_id, tipo):
    """
    Genera un reporte PDF del taller según el tipo solicitado.
    Tipos: 'ejecutivo', 'tecnico', 'organismo'
    """
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    # Obtener datos del taller con optimización de queries
    participantes = ParticipanteTaller.objects.filter(
        sesion=sesion, presente=True
    ).select_related('rol_primario', 'rol_primario__familia', 'rol_secundario')
    
    datos = DatoEcosistema.objects.filter(sesion=sesion, es_maestro=True)
    flujos = FlujoDatos.objects.filter(sesion=sesion)
    clasificaciones = ClasificacionDato.objects.filter(sesion=sesion)
    
    # Crear buffer para el PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Crear estilos
    estilos = _crear_estilos_pdf()
    
    # Construir contenido del documento
    story = _crear_encabezado_pdf(sesion, estilos)
    
    # Agregar contenido según tipo de reporte
    if tipo == 'ejecutivo':
        story.extend(_generar_reporte_ejecutivo(sesion, participantes, datos, flujos, clasificaciones, estilos))
    elif tipo == 'tecnico':
        story.extend(_generar_reporte_tecnico(sesion, participantes, flujos, clasificaciones, estilos))
    elif tipo == 'organismo':
        story.extend(_generar_reporte_organismo(sesion, participantes, datos, flujos, clasificaciones, estilos))
    else:
        return JsonResponse({'error': 'Tipo de reporte inválido'}, status=400)
    
    # Agregar pie de página
    story.extend(_crear_pie_pagina_pdf(estilos))
    
    # Construir PDF
    doc.build(story)
    
    # Preparar respuesta
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="reporte_{tipo}_sesion_{sesion_id}.pdf"'
    
    return response


@require_GET
def exportar_datos_csv(request, sesion_id, tipo):
    """
    Exporta datos del taller en formato CSV.
    Tipos: 'participantes', 'roles', 'datos', 'flujos', 'clasificaciones'
    """
    import csv
    from django.http import HttpResponse
    
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{tipo}_sesion_{sesion_id}.csv"'
    response.write('\ufeff')  # BOM para Excel
    
    writer = csv.writer(response)
    
    if tipo == 'participantes':
        writer.writerow(['Nombre', 'Área Funcional', 'Cargo', 'Rol Primario', 'Rol Secundario', 'Presente'])
        participantes = ParticipanteTaller.objects.filter(sesion=sesion).select_related('rol_primario', 'rol_secundario')
        for p in participantes:
            writer.writerow([
                p.nombre_completo,
                p.area_funcional,
                p.cargo,
                p.rol_primario.nombre if p.rol_primario else '',
                p.rol_secundario.nombre if p.rol_secundario else '',
                'Sí' if p.presente else 'No'
            ])
    
    elif tipo == 'roles':
        writer.writerow(['Participante', 'Rol Primario', 'Familia', 'Rol Secundario'])
        participantes = ParticipanteTaller.objects.filter(sesion=sesion, rol_primario__isnull=False).select_related('rol_primario', 'rol_secundario')
        for p in participantes:
            writer.writerow([
                p.nombre_completo,
                p.rol_primario.nombre,
                f"{p.rol_primario.familia.codigo}: {p.rol_primario.familia.nombre}",
                p.rol_secundario.nombre if p.rol_secundario else ''
            ])
    
    elif tipo == 'datos':
        writer.writerow(['Nombre del Dato', 'Creado Por', 'Es Maestro', 'Fusionado Con', 'Fecha Creación'])
        datos = DatoEcosistema.objects.filter(sesion=sesion).select_related('creado_por', 'fusionado_con')
        for d in datos:
            writer.writerow([
                d.nombre,
                d.creado_por.nombre_completo,
                'Sí' if d.es_maestro else 'No',
                d.fusionado_con.nombre if d.fusionado_con else '',
                d.fecha_creacion.strftime('%d/%m/%Y %H:%M')
            ])
    
    elif tipo == 'flujos':
        writer.writerow(['Participante', 'Tipo', 'Datos', 'Origen', 'Destino', 'Frecuencia', 'Formato'])
        flujos = FlujoDatos.objects.filter(sesion=sesion).select_related('participante')
        for f in flujos:
            origen = f.recibe_de_participante or f.recibe_de_subsistema or f.recibe_de_externo or 'N/A'
            destino = f.envia_a_participante or f.envia_a_subsistema or f.envia_a_externo or 'N/A'
            writer.writerow([
                f.participante.nombre_completo,
                f.tipo,
                f.descripcion_datos,
                str(origen),
                str(destino),
                f.frecuencia,
                f.formato
            ])
    
    elif tipo == 'clasificaciones':
        writer.writerow(['Dato', 'Participante', 'Nivel Importancia', 'Sensibilidad', 'Mecanismo Recolección', 'Para qué se usa'])
        clasificaciones = ClasificacionDato.objects.filter(sesion=sesion).select_related('participante')
        for c in clasificaciones:
            writer.writerow([
                c.nombre_dato,
                c.participante.nombre_completo,
                c.nivel,
                c.sensibilidad,
                c.mecanismo_recoleccion,
                c.para_que_se_usa
            ])
    
    return response


@require_GET
def exportar_completo_zip(request, sesion_id):
    """Exporta todos los datos del taller en un archivo ZIP con múltiples CSVs."""
    import zipfile
    from io import BytesIO, StringIO
    import csv
    from django.http import HttpResponse
    
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    # Crear buffer para el ZIP
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Función helper para crear CSV
        def crear_csv(nombre_archivo, headers, datos):
            csv_buffer = StringIO()
            csv_buffer.write('\ufeff')  # BOM
            writer = csv.writer(csv_buffer)
            writer.writerow(headers)
            for fila in datos:
                writer.writerow(fila)
            zip_file.writestr(nombre_archivo, csv_buffer.getvalue().encode('utf-8'))
        
        # 1. Participantes
        participantes = ParticipanteTaller.objects.filter(sesion=sesion).select_related('rol_primario', 'rol_secundario')
        datos_participantes = []
        for p in participantes:
            datos_participantes.append([
                p.nombre_completo, p.area_funcional, p.cargo,
                p.rol_primario.nombre if p.rol_primario else '',
                p.rol_secundario.nombre if p.rol_secundario else '',
                'Sí' if p.presente else 'No'
            ])
        crear_csv('participantes.csv', ['Nombre', 'Área', 'Cargo', 'Rol Primario', 'Rol Secundario', 'Presente'], datos_participantes)
        
        # 2. Datos del ecosistema
        datos = DatoEcosistema.objects.filter(sesion=sesion).select_related('creado_por', 'fusionado_con')
        datos_datos = []
        for d in datos:
            datos_datos.append([
                d.nombre, d.creado_por.nombre_completo,
                'Sí' if d.es_maestro else 'No',
                d.fusionado_con.nombre if d.fusionado_con else '',
                d.fecha_creacion.strftime('%d/%m/%Y %H:%M')
            ])
        crear_csv('datos_ecosistema.csv', ['Nombre', 'Creado Por', 'Es Maestro', 'Fusionado Con', 'Fecha'], datos_datos)
        
        # 3. Flujos
        flujos = FlujoDatos.objects.filter(sesion=sesion).select_related('participante')
        datos_flujos = []
        for f in flujos:
            origen = f.recibe_de_participante or f.recibe_de_subsistema or f.recibe_de_externo or 'N/A'
            destino = f.envia_a_participante or f.envia_a_subsistema or f.envia_a_externo or 'N/A'
            datos_flujos.append([
                f.participante.nombre_completo, f.tipo, f.descripcion_datos,
                str(origen), str(destino), f.frecuencia, f.formato
            ])
        crear_csv('flujos.csv', ['Participante', 'Tipo', 'Datos', 'Origen', 'Destino', 'Frecuencia', 'Formato'], datos_flujos)
        
        # 4. Clasificaciones
        clasificaciones = ClasificacionDato.objects.filter(sesion=sesion).select_related('participante')
        datos_clasif = []
        for c in clasificaciones:
            datos_clasif.append([
                c.nombre_dato, c.participante.nombre_completo,
                c.nivel, c.sensibilidad, c.mecanismo_recoleccion, c.para_que_se_usa
            ])
        crear_csv('clasificaciones.csv', ['Dato', 'Participante', 'Nivel', 'Sensibilidad', 'Mecanismo', 'Uso'], datos_clasif)
        
        # 5. Resumen del taller
        resumen = [
            ['Métrica', 'Valor'],
            ['Organismo', sesion.organismo.nombre],
            ['Sesión', sesion.nombre_sesion],
            ['Fecha', sesion.fecha.strftime('%d/%m/%Y')],
            ['Facilitador', sesion.facilitador],
            ['Participantes', str(participantes.count())],
            ['Datos creados', str(datos.count())],
            ['Flujos mapeados', str(flujos.count())],
            ['Datos clasificados', str(clasificaciones.count())]
        ]
        crear_csv('resumen.csv', ['Métrica', 'Valor'], resumen[1:])
    
    # Preparar respuesta
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="taller_completo_sesion_{sesion_id}.zip"'
    
    return response


# ============================================================================
# RELACIONES ENTRE DATOS (Dato → Dato)
# ============================================================================

@require_POST
@requiere_participante_activo
def relacion_dato_crear(request):
    """
    Crea una relación directa entre dos datos del ecosistema.
    
    Modelo: [Dato Origen] → [Tipo Relación] → [Dato Destino]
    
    Body: {
        token,
        dato_origen_id: int,
        dato_destino_id: int,
        tipo_relacion: str,
        descripcion?: str,
        proceso_transformacion?: str,
        periodicidad_transformacion?: str
    }
    REQUIERE: Token de participante válido en el body JSON.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    
    participante = request.participante
    sesion = participante.sesion
    
    # Validar datos requeridos
    dato_origen_id = data.get('dato_origen_id')
    dato_destino_id = data.get('dato_destino_id')
    tipo_relacion = data.get('tipo_relacion')
    
    if not all([dato_origen_id, dato_destino_id, tipo_relacion]):
        return JsonResponse({
            'error': 'Faltan campos requeridos: dato_origen_id, dato_destino_id, tipo_relacion'
        }, status=400)
    
    # Validar que los datos existan en la sesión
    try:
        dato_origen = DatoEcosistema.objects.get(id=dato_origen_id, sesion=sesion)
        dato_destino = DatoEcosistema.objects.get(id=dato_destino_id, sesion=sesion)
    except DatoEcosistema.DoesNotExist:
        return JsonResponse({'error': 'Uno o ambos datos no existen en esta sesión'}, status=400)
    
    # Evitar auto-relación
    if dato_origen_id == dato_destino_id:
        return JsonResponse({'error': 'Un dato no puede relacionarse consigo mismo'}, status=400)
    
    # Crear la relación
    from indicadores.models import RelacionDato
    
    try:
        relacion = RelacionDato.objects.create(
            sesion=sesion,
            creado_por=participante,
            dato_origen=dato_origen,
            dato_destino=dato_destino,
            tipo_relacion=tipo_relacion,
            descripcion=data.get('descripcion', ''),
            proceso_transformacion=data.get('proceso_transformacion', ''),
            periodicidad_transformacion=data.get('periodicidad_transformacion', '')
        )
        
        return JsonResponse({
            'success': True,
            'relacion_id': relacion.id,
            'mensaje': f'Relación creada: {dato_origen.nombre} → {relacion.get_tipo_relacion_display()} → {dato_destino.nombre}',
            'es_circular': relacion.es_circular,
            'cadena': relacion.cadena_relaciones
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_GET
def relaciones_dato_sesion(request, sesion_id):
    """
    Obtiene todas las relaciones entre datos de una sesión.
    
    Usado por el mapa 3D para renderizar el grafo de linaje de datos.
    """
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    from indicadores.models import RelacionDato
    
    relaciones = RelacionDato.objects.filter(sesion=sesion).select_related(
        'dato_origen', 'dato_destino', 'creado_por'
    )
    
    data = []
    for r in relaciones:
        data.append({
            'id': r.id,
            'dato_origen': {
                'id': r.dato_origen.id,
                'nombre': r.dato_origen.nombre,
                'nivel': r.dato_origen.nivel,
                'sensibilidad': r.dato_origen.sensibilidad,
            },
            'tipo_relacion': r.tipo_relacion,
            'tipo_relacion_display': r.get_tipo_relacion_display(),
            'descripcion': r.descripcion,
            'dato_destino': {
                'id': r.dato_destino.id,
                'nombre': r.dato_destino.nombre,
                'nivel': r.dato_destino.nivel,
                'sensibilidad': r.dato_destino.sensibilidad,
            },
            'creado_por': r.creado_por.nombre_completo,
            'proceso_transformacion': r.proceso_transformacion,
            'periodicidad': r.periodicidad_transformacion,
            'es_validada': r.es_validada,
            'es_circular': r.es_circular,
            'cadena': r.cadena_relaciones,
            'fecha_creacion': r.fecha_creacion.isoformat()
        })
    
    return JsonResponse({'relaciones': data, 'total': len(data)})


@require_POST
@requiere_facilitador
def relacion_dato_validar(request, sesion_id):
    """
    Facilitador valida una relación entre datos.
    
    Body: {relacion_id, es_validada: bool}
    REQUIERE: Header X-Facilitador-Token con el código de la sesión.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    from indicadores.models import RelacionDato
    
    try:
        relacion = RelacionDato.objects.get(id=data.get('relacion_id'), sesion=sesion)
        relacion.es_validada = data.get('es_validada', True)
        relacion.save()
        
        return JsonResponse({
            'success': True,
            'relacion_id': relacion.id,
            'es_validada': relacion.es_validada
        })
    except RelacionDato.DoesNotExist:
        return JsonResponse({'error': 'Relación no encontrada'}, status=404)


@require_GET
def api_datos_linaje(request, sesion_id):
    """
    Retorna datos con su linaje completo (relaciones entrantes y salientes).
    
    Útil para visualizar el árbol de derivación de datos.
    """
    sesion = get_object_or_404(SesionTaller, id=sesion_id)
    
    from indicadores.models import RelacionDato
    
    datos = sesion.datos_ecosistema.all()
    
    data = []
    for d in datos:
        relaciones_salientes = RelacionDato.objects.filter(dato_origen=d).values(
            'id', 'tipo_relacion', 'dato_destino__id', 'dato_destino__nombre', 'descripcion'
        )
        relaciones_entrantes = RelacionDato.objects.filter(dato_destino=d).values(
            'id', 'tipo_relacion', 'dato_origen__id', 'dato_origen__nombre', 'descripcion'
        )
        
        data.append({
            'id': d.id,
            'nombre': d.nombre,
            'nivel': d.nivel,
            'sensibilidad': d.sensibilidad,
            'es_maestro': d.es_maestro,
            'relaciones_salientes': list(relaciones_salientes),
            'relaciones_entrantes': list(relaciones_entrantes),
            'total_relaciones': len(relaciones_salientes) + len(relaciones_entrantes)
        })
    
    return JsonResponse({
        'datos': data,
        'total': len(data),
        'con_relaciones': len([d for d in data if d['total_relaciones'] > 0])
    })
