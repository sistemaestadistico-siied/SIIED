"""Definición declarativa de los pasos del formulario wizard del taller."""

from dataclasses import dataclass, field
from typing import Callable, Optional

from . import forms_taller as forms
from .models_taller import InscripcionTaller as Inscripcion, RetoAnalisis
from .models_catalogo import EvaluacionSeguridad, FuenteDatos


def _get_inscripcion(inscripcion):
    return inscripcion


def _get_fuente(inscripcion):
    """Fallback — la vista gestiona la selección de fuente activa vía sesión."""
    fuente = FuenteDatos.objects.filter(inscripcion=inscripcion).first()
    if fuente is None:
        fuente = FuenteDatos.objects.create(inscripcion=inscripcion, nombre='', descripcion='')
    return fuente


def _get_reto(inscripcion):
    reto, _ = RetoAnalisis.objects.get_or_create(inscripcion=inscripcion)
    return reto


def _get_seguridad(inscripcion):
    """Fallback — la vista resuelve la fuente activa vía sesión; F3 es por fuente."""
    fuente = FuenteDatos.objects.filter(inscripcion=inscripcion).first()
    if fuente is None:
        fuente = FuenteDatos.objects.create(inscripcion=inscripcion, nombre='', descripcion='')
    seguridad, _ = EvaluacionSeguridad.objects.get_or_create(fuente=fuente)
    return seguridad


@dataclass(frozen=True)
class Paso:
    slug: str
    titulo: str
    seccion: str
    fase: str  # 'inicio', 'f1', 'f2', 'f3'
    get_instance: Callable
    form_class: Optional[type] = None
    formset_class: Optional[type] = None
    descripcion: str = ''


FASES = {
    'inicio': {'nombre': 'Identificación', 'color': '#e6f7ff', 'borde': '#b3e0ff'},
    'f1': {'nombre': 'F1 · Caracterización', 'color': '#fff3e6', 'borde': '#ffccb3'},
    'f2': {'nombre': 'F2 · Integración y uso', 'color': '#ebfaeb', 'borde': '#c2f0c2'},
    'f3': {'nombre': 'F3 · Seguridad y privacidad', 'color': '#fce8f3', 'borde': '#f9b8d9'},
}

PASOS = [
    Paso(
        slug='identificacion',
        titulo='Información general del organismo',
        seccion='Identificación',
        fase='inicio',
        get_instance=_get_inscripcion,
        form_class=forms.IdentificacionForm,
        descripcion='Datos del organismo, suborganismo, equipo responsable y persona de contacto.',
    ),
    Paso(
        slug='fuente-general',
        titulo='F1 · La fuente de datos',
        seccion='1. Información general de la fuente',
        fase='f1',
        get_instance=_get_inscripcion,
        formset_class=forms.FuenteDatosFormSet,
        descripcion='Identifique las fuentes o conjuntos de datos, su contenido y cómo se recolectan. '
                     'Puede agregar múltiples fuentes.',
    ),
    Paso(
        slug='fuente-actualizacion',
        titulo='F1 · Actualización y cobertura',
        seccion='1. Información general de la fuente',
        fase='f1',
        get_instance=_get_fuente,
        form_class=forms.FuenteActualizacionForm,
        descripcion='Periodicidad, desagregación geográfica, volumen de registros y documentación. Seleccione la fuente a editar en el menú desplegable.'
    ),
    Paso(
        slug='fuente-rol',
        titulo='F1 · Rol del organismo frente a la fuente',
        seccion='1. Rol del organismo',
        fase='f1',
        get_instance=_get_fuente,
        form_class=forms.FuenteRolForm,
        formset_class=forms.FuenteOrigenFormSet,
        descripcion='Si el rol es "Usuario" o "Ambos", indique las fuentes de origen y su organismo productor. Seleccione la fuente a editar en el menú desplegable.'
    ),
    Paso(
        slug='fuente-proposito',
        titulo='F1 · Propósito y utilidad institucional',
        seccion='2. Propósito y utilidad institucional',
        fase='f1',
        get_instance=_get_fuente,
        form_class=forms.FuentePropositoForm,
        descripcion='Decisiones que apoya la fuente y unidad de análisis principal. Seleccione la fuente a editar en el menú desplegable.'
    ),
    Paso(
        slug='fuente-variables',
        titulo='F1 · Estructura y variables principales',
        seccion='3-4. Estructura y variables',
        fase='f1',
        get_instance=_get_fuente,
        formset_class=forms.VariableFuenteFormSet,
        descripcion='Describa brevemente las variables o campos más relevantes de la fuente (máximo 10).',
    ),
    Paso(
        slug='fuente-calidad',
        titulo='F1 · Calidad y cobertura de los datos',
        seccion='5. Calidad y cobertura',
        fase='f1',
        get_instance=_get_fuente,
        form_class=forms.FuenteCalidadForm,
        descripcion='Georreferenciación, problemas de calidad y procesos de validación. Seleccione la fuente a editar en el menú desplegable.'
    ),
    Paso(
        slug='fuente-diccionario',
        titulo='F1 · Diccionario completo de variables',
        seccion='3-4. Estructura y variables',
        fase='f1',
        get_instance=_get_fuente,
        form_class=forms.FuenteDiccionarioForm,
        formset_class=forms.VariableFuenteCompletoFormSet,
        descripcion='Agregue todas las variables de la fuente de datos y suba el archivo Excel del diccionario. Puede agregar o eliminar registros sin límite. Seleccione la fuente a editar en el menú desplegable.',
    ),
    Paso(
        slug='reto-definicion',
        titulo='F2 · Definición del reto de análisis',
        seccion='1.1 - 1.4',
        fase='f2',
        get_instance=_get_reto,
        form_class=forms.RetoDefinicionForm,
        descripcion='Diligencie una ficha por cada propuesta de análisis, formulada con base en las fuentes caracterizadas. '
                    'Nota: F2 es una sola por inscripción — si ya la diligenció, verá sus respuestas anteriores y puede '
                    'actualizarlas; no se diligencia por cada fuente.',
    ),
    Paso(
        slug='reto-unidades',
        titulo='F2 · Unidades y desagregación del análisis',
        seccion='1.5 - 1.6',
        fase='f2',
        get_instance=_get_reto,
        form_class=forms.RetoUnidadesForm,
        descripcion='Población, objeto o unidad de análisis que se observará y nivel geográfico.',
    ),
    Paso(
        slug='reto-fuentes',
        titulo='F2 · Fuentes requeridas para el reto',
        seccion='1.7 - 1.9',
        fase='f2',
        get_instance=_get_reto,
        formset_class=forms.FuenteRequeridaFormSet,
        descripcion='1.7 ¿Qué fuentes de caracterización se requieren? Relacione hasta 3 fuentes por nombre y organismo custodio, con sus variables y llaves de relación.',
    ),
    Paso(
        slug='reto-tratamiento',
        titulo='F2 · Tratamiento analítico y resultados',
        seccion='1.10 - 1.15',
        fase='f2',
        get_instance=_get_reto,
        form_class=forms.RetoTratamientoForm,
        descripcion='Procesos analíticos, resultado mínimo viable, capacidades del SIPDI y enfoques diferenciales.',
    ),
    Paso(
        slug='seguridad-datos',
        titulo='F3 · Datos personales y acceso',
        seccion='6. Datos personales y acceso',
        fase='f3',
        get_instance=_get_seguridad,
        form_class=forms.SeguridadDatosForm,
        descripcion='Identificación de datos personales, información de especial cuidado y base legítima. '
                    'Nota: F3 es una sola por inscripción — si ya la diligenció, verá sus respuestas anteriores y puede '
                    'actualizarlas; no se diligencia por cada fuente.',
    ),
    Paso(
        slug='seguridad-uso',
        titulo='F3 · Uso y protección de los datos',
        seccion='6. Uso y protección',
        fase='f3',
        get_instance=_get_seguridad,
        form_class=forms.SeguridadUsoForm,
        descripcion='Marque una opción por pregunta. Explique si responde «No aplica».',
    ),
    Paso(
        slug='seguridad-divulgacion',
        titulo='F3 · Divulgación y medidas de protección',
        seccion='6. Divulgación y medidas',
        fase='f3',
        get_instance=_get_seguridad,
        form_class=forms.SeguridadDivulgacionForm,
        descripcion='Riesgos de publicación, terceros y medidas aplicadas para proteger la información personal.',
    ),
    Paso(
        slug='seguridad-valoracion',
        titulo='F3 · Valoración de los activos de información',
        seccion='6.1 Valoración de criticidad',
        fase='f3',
        get_instance=_get_seguridad,
        form_class=forms.SeguridadValoracionForm,
        descripcion=(
            'Clasifique confidencialidad, integridad y disponibilidad con el semáforo. '
            'La criticidad se calcula automáticamente: si alguna variable es ROJA el activo es crítico y debe priorizarse '
            'para análisis de riesgo; si alguna es AMARILLA debe decidirse según escenarios; si las tres son verdes, '
            'el activo es información pública, no crítico. Recuerde: la valoración del activo primario regula la de los '
            'activos de soporte (hardware, software, recurso humano, disco duro, nube, redes).'
        ),
    ),
]

PASOS_POR_SLUG = {p.slug: p for p in PASOS}


def indice(slug):
    for i, paso in enumerate(PASOS):
        if paso.slug == slug:
            return i
    return -1


def paso_siguiente(slug):
    i = indice(slug)
    if 0 <= i < len(PASOS) - 1:
        return PASOS[i + 1]
    return None


def paso_anterior(slug):
    i = indice(slug)
    if i > 0:
        return PASOS[i - 1]
    return None


def paso_siguiente_ficha(slug, ficha_inicial='f1'):
    """Como paso_siguiente pero salta F1 si ficha_inicial='f2'."""
    if slug == 'identificacion' and ficha_inicial == 'f2':
        return PASOS_POR_SLUG['reto-definicion']
    return paso_siguiente(slug)


def paso_anterior_ficha(slug, ficha_inicial='f1'):
    """Como paso_anterior pero salta F1 si ficha_inicial='f2'."""
    if slug == 'reto-definicion' and ficha_inicial == 'f2':
        return PASOS_POR_SLUG['identificacion']
    return paso_anterior(slug)
