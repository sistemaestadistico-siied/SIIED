"""Vistas del módulo Catálogo de Datos del SIIED.

Inventario institucional de activos de información:
  - catálogo público de conjuntos de datos (bases del Data Lake + F1 del taller)
  - ficha de conjunto individual
  - API de fuentes para el wizard del taller
"""

import json

from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from .decorators import taller_login_required
from django.views.decorators.http import require_GET

from .catalogo_datalake import get_bases, get_campos_cruzables
from .models import Organismo, Suborganismo
from .models_taller import InscripcionTaller as Inscripcion, RetoAnalisis
from .models_catalogo import (
    EvaluacionSeguridad, FuenteDatos, FuenteOrigen, VariableFuente,
)


@taller_login_required
@require_GET
def api_fuentes_catalogo(request):
    """Retorna nombres de bases del catálogo y fuentes ya registradas para autocomplete."""
    from .catalogo_datalake import get_bases
    bases = get_bases()
    resultado = [{'nombre': b['nombre'], 'organismo': b.get('organismo', '')}
                 for b in bases]
    # Añadir fuentes ya registradas por otros usuarios
    fuentes_registradas = FuenteDatos.objects.exclude(
        nombre='').exclude(nombre__isnull=True).values('nombre', 'inscripcion__organismo__nombre').distinct()
    for f in fuentes_registradas:
        resultado.append({'nombre': f['nombre'], 'organismo': f.get('inscripcion__organismo__nombre') or ''})
    return JsonResponse(resultado, safe=False)




def catalogo_datos(request):
    import json
    from .catalogo_datalake import get_bases, get_campos_cruzables
    bases = get_bases()
    cruzables = get_campos_cruzables()
    context = {
        'bases_json': json.dumps(bases, ensure_ascii=False),
        'cruzables_json': json.dumps(cruzables, ensure_ascii=False),
        'bases': bases,
        'cruzables': cruzables,
    }
    return render(request, 'taller/catalogo_datos.html', context)


@taller_login_required
def ficha_conjunto(request, fuente_id):
    """Muestra la ficha completa de un conjunto de datos (FuenteDatos)."""
    from .models import (EvaluacionSeguridad, FuenteOrigen, RetoAnalisis,
                         VariableFuente)
    fuente = get_object_or_404(FuenteDatos, pk=fuente_id)
    variables = fuente.variables.all().order_by('id')
    fuentes_origen = fuente.fuentes_origen.all()
    inscripcion = fuente.inscripcion
    reto = getattr(inscripcion, 'reto', None) if hasattr(inscripcion, 'reto') else None
    seguridad = getattr(fuente, 'seguridad', None) if hasattr(fuente, 'seguridad') else None

    # Construir todas las secciones con todos los campos
    secciones = []

    # --- Identificación del organismo ---
    secciones.append({
        'titulo': 'Identificación del organismo',
        'items': [
            ('Organismo', inscripcion.organismo.nombre if inscripcion.organismo else '—'),
            ('Suborganismo', inscripcion.suborganismo.nombre if inscripcion.suborganismo else '—'),
            ('Equipo responsable', inscripcion.equipo_responsable or '—'),
            ('Persona de contacto', inscripcion.nombre_completo or '—'),
            ('Correo', inscripcion.correo or '—'),
            ('Teléfono', inscripcion.telefono or '—'),
        ],
    })

    # --- 1. Información general de la fuente ---
    secciones.append({
        'titulo': '1. Información general de la fuente',
        'items': [
            ('Nombre', fuente.nombre),
            ('Descripción', fuente.descripcion or '—'),
            ('Relaciones', ', '.join(str(o) for o in fuente.relaciones.all()) or '—'),
            ('Otra relación', fuente.relacion_otra or '—'),
            ('Instrumentos', ', '.join(str(o) for o in fuente.instrumentos.all()) or '—'),
            ('Otro instrumento', fuente.instrumento_otro or '—'),
            ('Mecanismos', ', '.join(str(o) for o in fuente.mecanismos.all()) or '—'),
            ('Otro mecanismo', fuente.mecanismo_otro or '—'),
            ('Fecha de inicio', fuente.fecha_inicio.strftime('%Y-%m-%d') if fuente.fecha_inicio else '—'),
        ],
    })

    # --- Actualización y cobertura ---
    secciones.append({
        'titulo': 'Actualización y cobertura',
        'items': [
            ('Fecha de última actualización', fuente.fecha_actualizacion.strftime('%Y-%m-%d') if fuente.fecha_actualizacion else '—'),
            ('Periodicidad', ', '.join(str(o) for o in fuente.periodicidades.all()) or '—'),
            ('Otra periodicidad', fuente.periodicidad_otra or '—'),
            ('Desagregación geográfica', ', '.join(str(o) for o in fuente.desagregaciones.all()) or '—'),
            ('Otra desagregación', fuente.desagregacion_otra or '—'),
            ('Número de registros', str(fuente.num_registros) if fuente.num_registros else '—'),
            ('No se conoce la cantidad', 'Sí' if fuente.num_registros_desconocido else 'No'),
            ('Fecha de la cantidad', fuente.num_registros_fecha.strftime('%Y-%m-%d') if fuente.num_registros_fecha else '—'),
            ('¿Existe diccionario?', fuente.get_tiene_diccionario_display() if fuente.tiene_diccionario else '—'),
            ('Ubicación del diccionario', fuente.diccionario_ubicacion or '—'),
        ],
    })

    # --- Rol del organismo ---
    secciones.append({
        'titulo': 'Rol del organismo frente a la fuente',
        'items': [
            ('Rol', fuente.get_rol_display() if fuente.rol else '—'),
        ],
    })

    # Fuentes de origen
    if fuentes_origen:
        origen_items = []
        for fo in fuentes_origen:
            origen_items.append((f'Fuente: {fo.nombre}', f'Productor: {fo.organismo_productor}'))
        secciones.append({
            'titulo': 'Fuentes de origen',
            'items': origen_items,
        })

    # --- 2. Propósito y utilidad ---
    secciones.append({
        'titulo': '2. Propósito y utilidad institucional',
        'items': [
            ('Decisiones que apoya', fuente.decisiones_apoya or '—'),
            ('Unidad de análisis principal', ', '.join(str(o) for o in fuente.unidades_analisis.all()) or '—'),
            ('Otra unidad', fuente.unidad_analisis_otra or '—'),
        ],
    })

    # --- 3-4. Estructura y variables ---
    var_items = []
    for v in variables:
        var_items.append((v.nombre, f'{v.get_tipo_display()} · {v.descripcion or "—"}{" · Identificador" if v.es_identificador else ""}'))
    secciones.append({
        'titulo': '3-4. Estructura y variables principales',
        'items': var_items or [('—', 'Sin variables registradas')],
    })

    # --- 5. Calidad y cobertura ---
    secciones.append({
        'titulo': '5. Calidad y cobertura',
        'items': [
            ('Georreferenciación', fuente.get_georreferenciacion_display() if fuente.georreferenciacion else '—'),
            ('Nivel de georreferenciación', ', '.join(str(o) for o in fuente.niveles_georref.all()) or '—'),
            ('Otro nivel', fuente.nivel_georref_otro or '—'),
            ('Problemas de calidad', ', '.join(str(o) for o in fuente.problemas_calidad.all()) or '—'),
            ('Otro problema', fuente.problema_calidad_otro or '—'),
            ('¿Tiene validación?', fuente.get_tiene_validacion_display() if fuente.tiene_validacion else '—'),
            ('Descripción de validación', fuente.validacion_descripcion or '—'),
        ],
    })

    # --- F2: Reto de análisis (si existe) ---
    if reto:
        secciones.append({
            'titulo': 'F2 · Reto de análisis',
            'items': [
                ('Nombre del reto', reto.nombre or '—'),
                ('Análisis propuesto', reto.analisis_propuesto or '—'),
                ('Resultado esperado', reto.resultado_esperado or '—'),
                ('Decisión que apoya', reto.decision_apoya or '—'),
                ('Unidad principal', str(reto.unidad_principal) if reto.unidad_principal else '—'),
                ('Otra unidad', reto.unidad_principal_otra or '—'),
                ('Unidades a relacionar', ', '.join(str(o) for o in reto.unidades_relacionar.all()) or '—'),
                ('Otra unidad a relacionar', reto.unidades_relacionar_otra or '—'),
                ('Vínculo entre unidades', reto.vinculo_unidades or '—'),
                ('Nivel de desagregación', ', '.join(str(o) for o in reto.desagregaciones.all()) or '—'),
                ('Otra desagregación', reto.desagregacion_otra or '—'),
                ('Tratamientos', ', '.join(str(o) for o in reto.tratamientos.all()) or '—'),
                ('Otro tratamiento', reto.tratamiento_otro or '—'),
                ('Resultado MVP', ', '.join(str(o) for o in reto.resultados_mvp.all()) or '—'),
                ('Otro resultado', reto.resultado_mvp_otro or '—'),
                ('Capacidades SIPDI', ', '.join(str(o) for o in reto.capacidades_sipdi.all()) or '—'),
                ('Otra capacidad', reto.capacidad_sipdi_otra or '—'),
                ('Variables a enriquecer', reto.variables_enriquecer or '—'),
                ('Usuario del resultado', reto.usuario_resultado or '—'),
                ('Enfoques diferenciales', ', '.join(str(o) for o in reto.enfoques_diferenciales.all()) or '—'),
                ('Otro enfoque', reto.enfoque_diferencial_otro or '—'),
            ],
        })

    # --- F3: Seguridad (si existe) ---
    if seguridad:
        secciones.append({
            'titulo': 'F3 · Seguridad y privacidad',
            'items': [
                ('¿Contiene datos personales?', seguridad.get_contiene_datos_personales_display() if seguridad.contiene_datos_personales else '—'),
                ('Variables identificadoras', ', '.join(str(o) for o in seguridad.variables_identificadoras.all()) or '—'),
                ('Otra variable identificadora', seguridad.variable_identificadora_otra or '—'),
                ('Datos sensibles', ', '.join(str(o) for o in seguridad.datos_sensibles.all()) or '—'),
                ('Otro dato sensible', seguridad.dato_sensible_otro or '—'),
                ('Base legítima', seguridad.get_base_legitima_display() if seguridad.base_legitima else '—'),
                ('Justificación base legítima', seguridad.base_legitima_porque or '—'),
                ('Susceptible a fraude', seguridad.get_susceptible_fraude_display() if seguridad.susceptible_fraude else '—'),
                ('Organismo custodio', seguridad.organismo_custodio or '—'),
                ('Confidencialidad', seguridad.get_confidencialidad_display() if seguridad.confidencialidad else '—'),
                ('Integridad', seguridad.get_integridad_display() if seguridad.integridad else '—'),
                ('Disponibilidad', seguridad.get_disponibilidad_display() if seguridad.disponibilidad else '—'),
                ('Criticidad', seguridad.criticidad or '—'),
            ],
        })

    context = {
        'fuente': fuente,
        'secciones': secciones,
    }
    return render(request, 'taller/ficha_conjunto.html', context)
