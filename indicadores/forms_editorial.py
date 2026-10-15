"""
Formularios del Módulo Editorial
"""

import json

from django import forms
from django.forms import inlineformset_factory
from indicadores.forms_iced import _error_telefono
from indicadores.models import (
    Evento, NoticiaBanner, EstadisticaNoticia, EnlaceNoticia,
    CalendarioDifusion, ProductoAcademico, ProductoEducativo,
    SeccionPaper, SeccionEducativa, ImagenSeccion, ArchivoSeccion,
    CategoriaInformacion, SistemaInformacion,
    CategoriaProyecto, ProyectoInformacion,
    AreaInfraestructura, CategoriaInfraestructura,
    SubcategoriaInfraestructura, GrupoDocumento,
    DocumentoInfraestructura,
    Grafico, GraficoSerie, Desagregacion,
    CatalogoConsulta, Indicador, MenuDominio,
    ConjuntoDatos, Organismo, OperacionEstadistica, MenuSubtema,
)


# ============================================================================
# FORMULARIOS DE EVENTOS
# ============================================================================

class EventoForm(forms.ModelForm):
    """Formulario para crear/editar eventos"""
    
    class Meta:
        model = Evento
        fields = [
            'nombre', 'slug', 'descripcion', 'fecha_inicio', 'fecha_fin',
            'lugar', 'imagen_url', 'url_externa', 'activo', 'destacado'
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Nombre del evento'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'slug-del-evento'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'rows': 4,
                'placeholder': 'Descripción del evento'
            }),
            'fecha_inicio': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'type': 'datetime-local'
            }),
            'fecha_fin': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'type': 'datetime-local'
            }),
            'lugar': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Ubicación del evento'
            }),
            'imagen_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'https://...'
            }),
            'url_externa': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'https://...'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500'
            }),
            'destacado': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500'
            })
        }
        labels = {
            'nombre': 'Nombre del Evento',
            'slug': 'Slug (URL)',
            'descripcion': 'Descripción',
            'fecha_inicio': 'Fecha y Hora de Inicio',
            'fecha_fin': 'Fecha y Hora de Fin',
            'lugar': 'Lugar',
            'imagen_url': 'URL de Imagen',
            'url_externa': 'Enlace Externo',
            'activo': 'Evento Activo',
            'destacado': 'Destacar Evento'
        }


# ============================================================================
# FORMULARIOS DE NOTICIAS
# ============================================================================

class NoticiaBannerForm(forms.ModelForm):
    """Formulario para crear/editar noticias"""
    
    class Meta:
        model = NoticiaBanner
        fields = [
            'titulo', 'subtitulo', 'descripcion', 'enlace_principal',
            'texto_enlace_principal', 'imagen_url', 'fecha_publicacion',
            'orden', 'activa'
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Título de la noticia'
            }),
            'subtitulo': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Subtítulo (opcional)'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'rows': 4,
                'placeholder': 'Descripción detallada de la noticia'
            }),
            'enlace_principal': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'https://...'
            }),
            'texto_enlace_principal': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Leer más'
            }),
            'imagen_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'https://...'
            }),
            'orden': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'min': 0
            }),
            'activa': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500'
            })
        }
        labels = {
            'titulo': 'Título',
            'subtitulo': 'Subtítulo',
            'descripcion': 'Descripción',
            'enlace_principal': 'Enlace Principal',
            'texto_enlace_principal': 'Texto del Botón',
            'imagen_url': 'URL de Imagen',
            'fecha_publicacion': 'Fecha de Publicación',
            'orden': 'Orden de Visualización',
            'activa': 'Noticia Activa'
        }


class EstadisticaNoticiaForm(forms.ModelForm):
    """Formulario para estadísticas inline de noticias"""
    
    class Meta:
        model = EstadisticaNoticia
        fields = ['titulo', 'valor', 'descripcion', 'orden']
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Ej: Usuarios activos'
            }),
            'valor': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Ej: 1,234'
            }),
            'descripcion': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Descripción adicional (opcional)'
            }),
            'orden': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'min': 0
            })
        }


class EnlaceNoticiaForm(forms.ModelForm):
    """Formulario para enlaces inline de noticias"""
    
    class Meta:
        model = EnlaceNoticia
        fields = ['titulo', 'url', 'descripcion', 'orden']
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Título del enlace'
            }),
            'url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'https://...'
            }),
            'descripcion': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Descripción (opcional)'
            }),
            'orden': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'min': 0
            })
        }


# Formsets para noticias
EstadisticaNoticiaFormSet = inlineformset_factory(
    NoticiaBanner,
    EstadisticaNoticia,
    form=EstadisticaNoticiaForm,
    extra=1,
    can_delete=True
)

EnlaceNoticiaFormSet = inlineformset_factory(
    NoticiaBanner,
    EnlaceNoticia,
    form=EnlaceNoticiaForm,
    extra=1,
    can_delete=True
)


# ============================================================================
# FORMULARIOS DE CALENDARIO DE DIFUSIÓN
# ============================================================================

class CalendarioDifusionForm(forms.ModelForm):
    """Formulario para calendario de difusión"""
    
    class Meta:
        model = CalendarioDifusion
        fields = [
            'organismo', 'observatorio', 'producto', 'tipo_cifras',
            'periodicidad', 'fecha_publicacion', 'periodo_referencia', 'activo'
        ]
        widgets = {
            'organismo': forms.Select(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all'
            }),
            'observatorio': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Nombre del observatorio (opcional)'
            }),
            'producto': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'rows': 3,
                'placeholder': 'Nombre del producto estadístico'
            }),
            'tipo_cifras': forms.Select(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all'
            }),
            'periodicidad': forms.Select(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all'
            }),
            'fecha_publicacion': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Ej: 20 de cada mes, Abril y Octubre'
            }),
            'periodo_referencia': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Ej: 2026, dic-26'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500'
            })
        }
        labels = {
            'organismo': 'Organismo',
            'observatorio': 'Observatorio',
            'producto': 'Producto Estadístico',
            'tipo_cifras': 'Tipo de Cifras',
            'periodicidad': 'Periodicidad',
            'fecha_publicacion': 'Fecha de Publicación',
            'periodo_referencia': 'Período de Referencia',
            'activo': 'Activo'
        }


# ============================================================================
# FORMULARIOS DE PRODUCTOS (para wizard)
# ============================================================================

class ProductoAcademicoBasicoForm(forms.ModelForm):
    """Formulario básico para productos académicos (paso 1 del wizard)"""
    
    class Meta:
        model = ProductoAcademico
        fields = ['titulo', 'slug', 'autor', 'institucion']
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Título del producto'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'slug-del-producto'
            }),
            'autor': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Nombre del autor'
            }),
            'institucion': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Institución'
            })
        }


class ProductoEducativoBasicoForm(forms.ModelForm):
    """Formulario básico para productos educativos (paso 1 del wizard)"""
    
    class Meta:
        model = ProductoEducativo
        fields = ['titulo', 'slug', 'autor', 'publico']
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Título del producto'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'slug-del-producto'
            }),
            'autor': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all',
                'placeholder': 'Nombre del autor'
            }),
            'publico': forms.Select(attrs={
                'class': 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all'
            })
        }


# ============================================================================
# FORMULARIOS DE SISTEMAS DE INFORMACIÓN
# ============================================================================

WIDGET_CLASSES = 'w-full px-4 py-3 bg-white border-2 border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all'
CHECKBOX_CLASSES = 'w-5 h-5 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500'


class CategoriaInformacionForm(forms.ModelForm):
    """Formulario para categorías de sistemas de información"""
    
    class Meta:
        model = CategoriaInformacion
        fields = ['nombre', 'slug', 'descripcion', 'icono', 'color', 'orden', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre de la categoría'}),
            'slug': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'slug-categoria'}),
            'descripcion': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 3, 'placeholder': 'Descripción breve'}),
            'icono': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'fas fa-server'}),
            'color': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': '#6366f1'}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }


class SistemaInformacionForm(forms.ModelForm):
    """Formulario para sistemas de información"""
    
    class Meta:
        model = SistemaInformacion
        fields = [
            'nombre', 'descripcion', 'categoria', 'tipo_enlace', 'url',
            'abrir_nueva_ventana', 'icono', 'imagen_url', 'orden', 'activo',
            'desarrollador', 'version', 'requiere_autenticacion'
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre del sistema'}),
            'descripcion': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 3, 'placeholder': 'Descripción del sistema'}),
            'categoria': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'tipo_enlace': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'url': forms.URLInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'https://...'}),
            'abrir_nueva_ventana': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'icono': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'fas fa-database'}),
            'imagen_url': forms.URLInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'https://...'}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'desarrollador': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Entidad responsable'}),
            'version': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'v1.0'}),
            'requiere_autenticacion': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }


# ============================================================================
# FORMULARIOS DE PRODUCTOS DE INFORMACIÓN
# ============================================================================

class CategoriaProyectoForm(forms.ModelForm):
    """Formulario para categorías de productos de información"""
    
    class Meta:
        model = CategoriaProyecto
        fields = ['nombre', 'slug', 'descripcion', 'icono', 'color', 'orden', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre de la categoría'}),
            'slug': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'slug-categoria'}),
            'descripcion': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 3, 'placeholder': 'Descripción breve'}),
            'icono': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'fas fa-eye'}),
            'color': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': '#14b8a6'}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }


class ProyectoInformacionForm(forms.ModelForm):
    """Formulario para productos/proyectos de información"""
    
    class Meta:
        model = ProyectoInformacion
        fields = [
            'nombre', 'descripcion', 'categoria', 'tipo_enlace', 'url',
            'abrir_nueva_ventana', 'icono', 'imagen_url', 'orden', 'activo',
            'dependencia_responsable', 'contacto_email', 'contacto_telefono',
            'estado', 'fecha_inicio', 'objetivos', 'poblacion_objetivo'
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre del producto'}),
            'descripcion': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 3, 'placeholder': 'Descripción'}),
            'categoria': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'tipo_enlace': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'url': forms.URLInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'https://...'}),
            'abrir_nueva_ventana': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'icono': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'fas fa-chart-line'}),
            'imagen_url': forms.URLInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'https://...'}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'dependencia_responsable': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Secretaría o entidad'}),
            'contacto_email': forms.EmailInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'correo@cali.gov.co'}),
            'contacto_telefono': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': '(602) 000-0000'}),
            'estado': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'fecha_inicio': forms.DateInput(attrs={'class': WIDGET_CLASSES, 'type': 'date'}),
            'objetivos': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 3, 'placeholder': 'Objetivos principales'}),
            'poblacion_objetivo': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Población o sector'}),
        }

    def clean_contacto_telefono(self):
        telefono = self.cleaned_data.get('contacto_telefono')
        err = _error_telefono(telefono)
        if err:
            raise forms.ValidationError(err)
        return telefono


# ============================================================================
# FORMULARIOS DE DOCUMENTOS DE INFRAESTRUCTURA
# ============================================================================

class DocumentoInfraestructuraForm(forms.ModelForm):
    """Formulario para documentos de infraestructura"""
    
    class Meta:
        model = DocumentoInfraestructura
        fields = [
            'nombre', 'slug', 'descripcion', 'grupo_documento', 'tipo_documento',
            'contenido', 'estado', 'version', 'destacado',
            'autor', 'fecha_revision',
            'archivo_pdf', 'archivo_word',
            'icono', 'orden', 'activo', 'palabras_clave', 'resumen_ejecutivo'
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre del documento'}),
            'slug': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'slug-documento'}),
            'descripcion': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 3, 'placeholder': 'Descripción breve'}),
            'grupo_documento': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'tipo_documento': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'estado': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'version': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'v1.0'}),
            'destacado': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'autor': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Autor o responsable'}),
            'fecha_revision': forms.DateInput(attrs={'class': WIDGET_CLASSES, 'type': 'date'}),
            'icono': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'fas fa-file-alt'}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'palabras_clave': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'palabra1, palabra2, ...'}),
            'resumen_ejecutivo': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 4, 'placeholder': 'Resumen ejecutivo'}),
        }


# ============================================================================
# FORMULARIOS DE JERARQUÍA DE INFRAESTRUCTURA
# ============================================================================

class AreaInfraestructuraForm(forms.ModelForm):
    """Formulario para áreas de infraestructura (Nivel 1)"""
    
    class Meta:
        model = AreaInfraestructura
        fields = ['nombre', 'slug', 'descripcion', 'icono', 'color', 'orden', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre del área'}),
            'slug': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'slug-area'}),
            'descripcion': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 2, 'placeholder': 'Descripción breve'}),
            'icono': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'fas fa-cogs'}),
            'color': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': '#6366f1'}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }


class CategoriaInfraestructuraForm(forms.ModelForm):
    """Formulario para categorías de infraestructura (Nivel 2)"""
    
    class Meta:
        model = CategoriaInfraestructura
        fields = ['area', 'nombre', 'slug', 'descripcion', 'icono', 'imagen_url', 'orden', 'activo']
        widgets = {
            'area': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'nombre': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre de la categoría'}),
            'slug': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'slug-categoria'}),
            'descripcion': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 2, 'placeholder': 'Descripción breve'}),
            'icono': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'fas fa-sitemap'}),
            'imagen_url': forms.URLInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'https://...'}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }


class SubcategoriaInfraestructuraForm(forms.ModelForm):
    """Formulario para subcategorías de infraestructura (Nivel 3)"""
    
    class Meta:
        model = SubcategoriaInfraestructura
        fields = ['categoria', 'nombre', 'slug', 'descripcion', 'icono', 'imagen_url', 'orden', 'activo']
        widgets = {
            'categoria': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'nombre': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre de la subcategoría'}),
            'slug': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'slug-subcategoria'}),
            'descripcion': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 2, 'placeholder': 'Descripción breve'}),
            'icono': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'fas fa-folder'}),
            'imagen_url': forms.URLInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'https://...'}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }


class GrupoDocumentoForm(forms.ModelForm):
    """Formulario para grupos de documentos (Nivel 4)"""
    
    class Meta:
        model = GrupoDocumento
        fields = ['subcategoria', 'nombre', 'slug', 'descripcion', 'icono', 'imagen_url', 'orden', 'activo']
        widgets = {
            'subcategoria': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'nombre': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre del grupo'}),
            'slug': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'slug-grupo'}),
            'descripcion': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 2, 'placeholder': 'Descripción breve'}),
            'icono': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'fas fa-layer-group'}),
            'imagen_url': forms.URLInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'https://...'}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }


# ============================================================================
# FORMULARIOS DE GRÁFICOS
# ============================================================================

class GraficoForm(forms.ModelForm):
    """Formulario para crear/editar gráficos de indicadores"""

    class Meta:
        model = Grafico
        fields = [
            'nombre', 'descripcion', 'tipo_grafico', 'activo', 'orden',
            'titulo', 'subtitulo',
            'eje_x_titulo', 'eje_y_titulo', 'mostrar_eje_y2', 'eje_y2_titulo',
            'mostrar_leyenda', 'posicion_leyenda',
            'mostrar_cuadricula', 'mostrar_valores', 'mostrar_linea_tendencia',
            'ancho_completo', 'altura_grafico', 'margen_derecho', 'margen_inferior',
            'begin_at_zero', 'rango_personalizado_min', 'rango_personalizado_max',
            'mostrar_todas_etiquetas_x',
            'rango_anios_min', 'rango_anios_max',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre del gráfico'}),
            'descripcion': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 2, 'placeholder': 'Descripción opcional'}),
            'tipo_grafico': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'titulo': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título visible del gráfico'}),
            'subtitulo': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Subtítulo visible'}),
            'eje_x_titulo': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título eje X'}),
            'eje_y_titulo': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título eje Y'}),
            'eje_y2_titulo': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título eje Y secundario'}),
            'mostrar_eje_y2': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'mostrar_leyenda': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'posicion_leyenda': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'mostrar_cuadricula': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'mostrar_valores': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'mostrar_linea_tendencia': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'ancho_completo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'altura_grafico': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 200, 'max': 1000}),
            'margen_derecho': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0, 'max': 200}),
            'margen_inferior': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0, 'max': 200}),
            'begin_at_zero': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'rango_personalizado_min': forms.NumberInput(attrs={'class': WIDGET_CLASSES}),
            'rango_personalizado_max': forms.NumberInput(attrs={'class': WIDGET_CLASSES}),
            'mostrar_todas_etiquetas_x': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'rango_anios_min': forms.NumberInput(attrs={'class': WIDGET_CLASSES}),
            'rango_anios_max': forms.NumberInput(attrs={'class': WIDGET_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        indicador = kwargs.pop('indicador', None)
        super().__init__(*args, **kwargs)

        # Desagregaciones predeterminadas: un multi-select por dominio del
        # indicador (padres primero), replicando los filtros del portal.
        # Se consolidan en los dos M2M del modelo al guardar (_save_m2m).
        self.campos_predeterminados = []
        if indicador:
            dominios = (
                list(indicador.dominios_desagregacion_geografica.all())
                + list(indicador.dominios_desagregacion_tematica.all())
            )
            dominios.sort(key=lambda d: (d.dominio_padre_id or d.id, d.id))

            predet_ids = set()
            if self.instance and self.instance.pk:
                predet_ids = (
                    set(self.instance.desagregaciones_geograficas_predeterminadas.values_list('id', flat=True))
                    | set(self.instance.desagregaciones_tematicas_predeterminadas.values_list('id', flat=True))
                )

            for dom in dominios:
                fname = f'predet_dom_{dom.id}'
                qs = dom.desagregaciones.order_by('nombre')
                self.fields[fname] = forms.ModelMultipleChoiceField(
                    queryset=qs,
                    required=False,
                    label=f'{dom.nombre} ({dom.get_tipo_display()})',
                    widget=forms.SelectMultiple(attrs={'class': WIDGET_CLASSES, 'size': 6}),
                    initial=[d.id for d in qs if d.id in predet_ids],
                )
                self.campos_predeterminados.append((dom, self[fname]))

    def _save_m2m(self):
        super()._save_m2m()
        # Consolidar los selects por dominio en los dos M2M del modelo,
        # separados por tipo de dominio.
        geo_ids, tem_ids = [], []
        for name in self.fields:
            if not name.startswith('predet_dom_'):
                continue
            for desag in self.cleaned_data.get(name) or []:
                if desag.dominio and desag.dominio.tipo == 'geografica':
                    geo_ids.append(desag.id)
                else:
                    tem_ids.append(desag.id)
        self.instance.desagregaciones_geograficas_predeterminadas.set(geo_ids)
        self.instance.desagregaciones_tematicas_predeterminadas.set(tem_ids)


class GraficoSerieForm(forms.ModelForm):
    """
    Formulario para series individuales de un gráfico.
    Una serie = conjunto de filtros de desagregación: un select por cada
    dominio del indicador (campos dinámicos dom_<id>), que se consolidan
    en el M2M `desagregaciones` y se replican a los FKs legacy.
    """

    class Meta:
        model = GraficoSerie
        fields = ['nombre_personalizado', 'color', 'orden']
        widgets = {
            'nombre_personalizado': forms.TextInput(
                attrs={'class': WIDGET_CLASSES, 'placeholder': 'Nombre visible de la serie'}
            ),
            'color': forms.TextInput(attrs={'type': 'color', 'class': WIDGET_CLASSES}),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        indicador = kwargs.pop('indicador', None)
        super().__init__(*args, **kwargs)
        # Todos los campos son opcionales para permitir formsets vacíos/extras
        self.fields['nombre_personalizado'].required = False
        self.fields['color'].required = False
        self.fields['orden'].required = False
        self.fields['orden'].initial = 0

        # Fallback: para forms de instancias existentes el indicador se puede
        # derivar del gráfico de la serie.
        if indicador is None and self.instance and self.instance.pk:
            indicador = self.instance.grafico.indicador

        self.dominio_fields = []
        if indicador:
            dominios = (
                list(indicador.dominios_desagregacion_geografica.all())
                + list(indicador.dominios_desagregacion_tematica.all())
            )
            dominios.sort(key=lambda d: (d.dominio_padre_id or d.id, d.id))

            # Valores actuales de la serie: M2M primero, FKs legacy de respaldo
            actuales = {}
            if self.instance and self.instance.pk:
                for d in self.instance.desagregaciones.all():
                    actuales[d.dominio_id] = d
                if not actuales:
                    for d in (self.instance.desagregacion_geografica,
                              self.instance.desagregacion_tematica):
                        if d:
                            actuales[d.dominio_id] = d

            for dom in dominios:
                fname = f'dom_{dom.id}'
                self.fields[fname] = forms.ModelChoiceField(
                    queryset=dom.desagregaciones.order_by('nombre'),
                    required=False,
                    label=f'{dom.nombre} ({dom.get_tipo_display()})',
                    empty_label='— Sin filtro —',
                    widget=forms.Select(attrs={'class': WIDGET_CLASSES}),
                    initial=actuales.get(dom.id),
                )
                self.dominio_fields.append(self[fname])

    def _save_m2m(self):
        super()._save_m2m()
        desags = []
        for name in self.fields:
            if name.startswith('dom_'):
                d = self.cleaned_data.get(name)
                if d:
                    desags.append(d)
        self.instance.desagregaciones.set(desags)
        self.instance.sincronizar_fks_legacy(desags)


# Inline formset para series de gráfico
GraficoSerieFormSet = inlineformset_factory(
    Grafico, GraficoSerie,
    form=GraficoSerieForm,
    extra=0, can_delete=True
)


class SectionGraficoConfigForm(forms.Form):
    """Formulario para configurar gráficos embebidos en secciones de productos académicos."""

    TIPO_GRAFICO_CHOICES = [
        ('line', 'Línea'),
        ('bar', 'Barras'),
        ('bar_horizontal', 'Barras Horizontales'),
        ('area', 'Área'),
        ('barras_apiladas', 'Barras Apiladas'),
        ('areas_apiladas', 'Áreas Apiladas'),
        ('pie', 'Circular'),
        ('piramide_poblacional', 'Pirámide Poblacional'),
        ('treemap', 'Treemap'),
        ('sin_grafico', 'Sin gráfico (solo tabla de datos)'),
        ('tabla_dinamica', 'Tabla dinámica (pivotada)'),
    ]

    POSICION_LEYENDA_CHOICES = [
        ('top', 'Arriba'),
        ('bottom', 'Abajo'),
        ('left', 'Izquierda'),
        ('right', 'Derecha'),
    ]

    tipo_grafico = forms.ChoiceField(
        choices=TIPO_GRAFICO_CHOICES, initial='line',
        widget=forms.Select(attrs={'class': WIDGET_CLASSES})
    )
    titulo = forms.CharField(
        required=False, max_length=255,
        widget=forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título visible del gráfico'})
    )
    subtitulo = forms.CharField(
        required=False, max_length=255,
        widget=forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Subtítulo visible'})
    )
    eje_x_titulo = forms.CharField(
        required=False, max_length=255,
        widget=forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título eje X'})
    )
    eje_y_titulo = forms.CharField(
        required=False, max_length=255,
        widget=forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título eje Y'})
    )
    mostrar_eje_y2 = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES})
    )
    eje_y2_titulo = forms.CharField(
        required=False, max_length=255,
        widget=forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título eje Y secundario'})
    )
    mostrar_leyenda = forms.BooleanField(
        required=False, initial=True,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES})
    )
    posicion_leyenda = forms.ChoiceField(
        choices=POSICION_LEYENDA_CHOICES, initial='right',
        widget=forms.Select(attrs={'class': WIDGET_CLASSES})
    )
    mostrar_cuadricula = forms.BooleanField(
        required=False, initial=True,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES})
    )
    mostrar_valores = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES})
    )
    mostrar_linea_tendencia = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES})
    )
    altura_grafico = forms.IntegerField(
        initial=400, min_value=200, max_value=1000,
        widget=forms.NumberInput(attrs={'class': WIDGET_CLASSES})
    )
    margen_derecho = forms.IntegerField(
        initial=50, min_value=0, max_value=200,
        widget=forms.NumberInput(attrs={'class': WIDGET_CLASSES})
    )
    margen_inferior = forms.IntegerField(
        initial=50, min_value=0, max_value=200,
        widget=forms.NumberInput(attrs={'class': WIDGET_CLASSES})
    )
    begin_at_zero = forms.BooleanField(
        required=False, initial=True,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES})
    )
    rango_personalizado_min = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={'class': WIDGET_CLASSES})
    )
    rango_personalizado_max = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={'class': WIDGET_CLASSES})
    )
    mostrar_todas_etiquetas_x = forms.BooleanField(
        required=False, initial=True,
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES})
    )
    rango_anios_min = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': WIDGET_CLASSES})
    )
    rango_anios_max = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': WIDGET_CLASSES})
    )
    desagregaciones_geograficas_predeterminadas = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={'class': WIDGET_CLASSES})
    )
    desagregaciones_tematicas_predeterminadas = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={'class': WIDGET_CLASSES})
    )
    series_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )

    def __init__(self, *args, **kwargs):
        indicador = kwargs.pop('indicador', None)
        super().__init__(*args, **kwargs)
        if indicador:
            from .models import Desagregacion
            geo_qs = Desagregacion.objects.filter(
                dominio__in=indicador.dominios_desagregacion_geografica.all()
            ).distinct()
            tem_qs = Desagregacion.objects.filter(
                dominio__in=indicador.dominios_desagregacion_tematica.all()
            ).distinct()
            self.fields['desagregaciones_geograficas_predeterminadas'].choices = [
                (d.id, d.nombre) for d in geo_qs
            ]
            self.fields['desagregaciones_tematicas_predeterminadas'].choices = [
                (d.id, d.nombre) for d in tem_qs
            ]
        else:
            self.fields['desagregaciones_geograficas_predeterminadas'].choices = []
            self.fields['desagregaciones_tematicas_predeterminadas'].choices = []

    def to_config(self):
        """Convierte los datos limpios del formulario a un dict de configuración JSON."""
        cleaned = self.cleaned_data
        config = {
            'tipo_grafico': cleaned.get('tipo_grafico', 'line'),
            'titulo': cleaned.get('titulo', ''),
            'subtitulo': cleaned.get('subtitulo', ''),
            'eje_x_titulo': cleaned.get('eje_x_titulo', ''),
            'eje_y_titulo': cleaned.get('eje_y_titulo', ''),
            'mostrar_eje_y2': cleaned.get('mostrar_eje_y2', False),
            'eje_y2_titulo': cleaned.get('eje_y2_titulo', ''),
            'mostrar_leyenda': cleaned.get('mostrar_leyenda', True),
            'posicion_leyenda': cleaned.get('posicion_leyenda', 'right'),
            'mostrar_cuadricula': cleaned.get('mostrar_cuadricula', True),
            'mostrar_valores': cleaned.get('mostrar_valores', False),
            'mostrar_linea_tendencia': cleaned.get('mostrar_linea_tendencia', False),
            'altura_grafico': cleaned.get('altura_grafico', 400),
            'margen_derecho': cleaned.get('margen_derecho', 50),
            'margen_inferior': cleaned.get('margen_inferior', 50),
            'begin_at_zero': cleaned.get('begin_at_zero', True),
            'rango_personalizado_min': cleaned.get('rango_personalizado_min'),
            'rango_personalizado_max': cleaned.get('rango_personalizado_max'),
            'mostrar_todas_etiquetas_x': cleaned.get('mostrar_todas_etiquetas_x', True),
            'rango_anios_min': cleaned.get('rango_anios_min'),
            'rango_anios_max': cleaned.get('rango_anios_max'),
            'desagregaciones_geograficas_predeterminadas': [int(v) for v in cleaned.get('desagregaciones_geograficas_predeterminadas', []) if v],
            'desagregaciones_tematicas_predeterminadas': [int(v) for v in cleaned.get('desagregaciones_tematicas_predeterminadas', []) if v],
            'series': [],
        }
        series_json = cleaned.get('series_json', '[]')
        try:
            series = json.loads(series_json) if series_json else []
            if isinstance(series, list):
                config['series'] = series
        except json.JSONDecodeError:
            config['series'] = []
        return config

    def from_config(self, config):
        """Carga los valores de un dict de configuración en el formulario."""
        if not config:
            return
        if isinstance(config, str):
            try:
                config = json.loads(config.strip()) if config.strip() else {}
            except (json.JSONDecodeError, ValueError):
                config = {}
        if not isinstance(config, dict):
            return
        initial = {
            'tipo_grafico': config.get('tipo_grafico', 'line'),
            'titulo': config.get('titulo', ''),
            'subtitulo': config.get('subtitulo', ''),
            'eje_x_titulo': config.get('eje_x_titulo', ''),
            'eje_y_titulo': config.get('eje_y_titulo', ''),
            'mostrar_eje_y2': config.get('mostrar_eje_y2', False),
            'eje_y2_titulo': config.get('eje_y2_titulo', ''),
            'mostrar_leyenda': config.get('mostrar_leyenda', True),
            'posicion_leyenda': config.get('posicion_leyenda', 'right'),
            'mostrar_cuadricula': config.get('mostrar_cuadricula', True),
            'mostrar_valores': config.get('mostrar_valores', False),
            'mostrar_linea_tendencia': config.get('mostrar_linea_tendencia', False),
            'altura_grafico': config.get('altura_grafico', 400),
            'margen_derecho': config.get('margen_derecho', 50),
            'margen_inferior': config.get('margen_inferior', 50),
            'begin_at_zero': config.get('begin_at_zero', True),
            'rango_personalizado_min': config.get('rango_personalizado_min'),
            'rango_personalizado_max': config.get('rango_personalizado_max'),
            'mostrar_todas_etiquetas_x': config.get('mostrar_todas_etiquetas_x', True),
            'rango_anios_min': config.get('rango_anios_min'),
            'rango_anios_max': config.get('rango_anios_max'),
            'desagregaciones_geograficas_predeterminadas': [str(v) for v in config.get('desagregaciones_geograficas_predeterminadas', [])],
            'desagregaciones_tematicas_predeterminadas': [str(v) for v in config.get('desagregaciones_tematicas_predeterminadas', [])],
            'series_json': json.dumps(config.get('series', []), ensure_ascii=False),
        }
        for field_name, value in initial.items():
            if field_name in self.fields:
                self.fields[field_name].initial = value


# ============================================================================
# FORMULARIOS DE CATÁLOGO DE CONSULTA
# ============================================================================

class CatalogoConsultaForm(forms.ModelForm):
    """
    Conjunto del catálogo de consulta (directorios/listados tipo anuario CEC).
    El archivo se parsea en la vista para poblar columnas + filas (JSON).
    """

    class Meta:
        model = CatalogoConsulta
        fields = [
            'nombre', 'descripcion', 'tipo_consulta', 'dominio',
            'archivo', 'orden', 'activo',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': WIDGET_CLASSES,
                'placeholder': 'Ej: Teatros de Santiago de Cali'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': WIDGET_CLASSES, 'rows': 3,
                'placeholder': 'Descripción del conjunto de datos de consulta'
            }),
            'tipo_consulta': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'dominio': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'archivo': forms.ClearableFileInput(attrs={
                'class': WIDGET_CLASSES,
                'accept': '.csv,.xlsx,.xls'
            }),
            'orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if archivo and hasattr(archivo, 'name'):
            ext = archivo.name.rsplit('.', 1)[-1].lower() if '.' in archivo.name else ''
            if ext not in ('csv', 'xlsx', 'xls'):
                raise forms.ValidationError(
                    'Solo se aceptan archivos CSV o Excel (.xlsx / .xls).'
                )
        return archivo


class CatalogoConsultaEnlazarIndicadoresForm(forms.Form):
    """
    Multi-select de indicadores para enlazar a un conjunto del catálogo.
    Filtrado al dominio del conjunto + CEC (los consulta viven en CEC).
    """

    indicadores = forms.ModelMultipleChoiceField(
        queryset=Indicador.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': WIDGET_CLASSES,
            'size': '18',
        })
    )

    def __init__(self, *args, catalogo=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Indicador.objects.select_related(
            'subtema__tema__dominio'
        ).order_by('subtema__tema__dominio__nombre', 'nombre')
        if catalogo is not None:
            # Candidatos: indicadores del dominio elegido + los del dominio CEC,
            # excluyendo los ya enlazados a OTRO conjunto
            qs = qs.filter(
                models_q_dominio(catalogo)
            ).exclude(
                catalogo_consulta__isnull=False
            )
            qs = qs | Indicador.objects.filter(
                pk__in=catalogo.indicadores_enlazados.values_list('pk', flat=True)
            )
            self.fields['indicadores'].initial = catalogo.indicadores_enlazados.all()
        self.fields['indicadores'].queryset = qs.distinct()
        self.fields['indicadores'].label_from_instance = (
            lambda ind: f"{ind.nombre} · [{ind.subtema.tema.dominio.nombre} › {ind.subtema.nombre}]"
            if ind.subtema and ind.subtema.tema and ind.subtema.tema.dominio
            else ind.nombre
        )


def models_q_dominio(catalogo):
    """Q para filtrar indicadores del dominio del catálogo o del dominio CEC.

    Un indicador puede colgar del dominio por su subtema principal (FK)
    o por subtemas adicionales (M2M) — se unen ambas vías.
    """
    cec = MenuDominio.objects.filter(slug__iexact='CEC').first()
    q = Indicador.q_por_dominio(catalogo.dominio)
    if cec:
        q |= Indicador.q_por_dominio(cec)
    return q


# ============================================================================
# PRODUCTOS ACADÉMICOS — EDICIÓN COMPLETA
# ============================================================================

class ProductoAcademicoForm(forms.ModelForm):
    """Edición completa de un ProductoAcademico desde editorial.

    Cubre metadatos bibliográficos, modo producto estadístico (INEGI),
    vinculaciones (organismo, operación, conjunto de datos, indicadores)
    y estado de publicación.
    """

    class Meta:
        model = ProductoAcademico
        fields = [
            'titulo', 'slug', 'autor', 'institucion', 'estado',
            'fecha_publicacion',
            'resumen', 'palabras_clave', 'area_tematica',
            'organismo', 'operacion', 'es_producto_estadistico',
            'cobertura_geografica', 'periodo_referencia',
            'logo', 'diseno_conceptual',
            'conjunto_datos_principal', 'indicadores_derivados',
            'temas_relacionados',
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título completo del paper'}),
            'slug': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'slug-del-producto'}),
            'autor': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Autor principal'}),
            'institucion': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Institución o dependencia'}),
            'estado': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'fecha_publicacion': forms.DateInput(attrs={'class': WIDGET_CLASSES, 'type': 'date'}),
            'resumen': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 4, 'placeholder': 'Resumen / abstract del paper'}),
            'palabras_clave': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'palabra1, palabra2, ...'}),
            'area_tematica': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Ej: Demografía computacional · Estadística aplicada'}),
            'organismo': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'operacion': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'es_producto_estadistico': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'cobertura_geografica': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Ej: Distrito de Santiago de Cali'}),
            'periodo_referencia': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Ej: 15 de febrero – 15 de marzo de 2024'}),
            'logo': forms.ClearableFileInput(attrs={'class': WIDGET_CLASSES}),
            'conjunto_datos_principal': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'indicadores_derivados': forms.SelectMultiple(attrs={'class': WIDGET_CLASSES, 'size': 6}),
            'temas_relacionados': forms.SelectMultiple(attrs={'class': WIDGET_CLASSES, 'size': 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # diseno_conceptual es CKEditor5Field: el widget lo provee el campo
        self.fields['diseno_conceptual'].required = False
        self.fields['indicadores_derivados'].queryset = (
            Indicador.objects.filter(activo=True).order_by('nombre'))
        self.fields['indicadores_derivados'].required = False
        self.fields['temas_relacionados'].required = False


class ProductoEducativoForm(forms.ModelForm):
    """Edición completa de un ProductoEducativo (deriva gamificada
    infantil/adolescente de un ProductoAcademico)."""

    class Meta:
        model = ProductoEducativo
        fields = [
            'titulo', 'slug', 'autor', 'estado', 'fecha_publicacion',
            'producto_origen', 'publico',
            'resumen_infantil', 'palabras_clave',
            'organismo', 'temas_relacionados',
            'imagen_portada',
            'personaje_guia', 'mensaje_bienvenida',
            'paleta_colores', 'nivel_gamificacion',
            'tiene_recompensas', 'puntos_totales',
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título adaptado al público'}),
            'slug': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'slug-del-producto'}),
            'autor': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Autor / adaptador'}),
            'estado': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'fecha_publicacion': forms.DateInput(attrs={'class': WIDGET_CLASSES, 'type': 'date'}),
            'producto_origen': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'publico': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'resumen_infantil': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 4, 'placeholder': 'Resumen en lenguaje simple y atractivo'}),
            'palabras_clave': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'palabra1, palabra2, ...'}),
            'organismo': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'temas_relacionados': forms.SelectMultiple(attrs={'class': WIDGET_CLASSES, 'size': 6}),
            'imagen_portada': forms.ClearableFileInput(attrs={'class': WIDGET_CLASSES}),
            'personaje_guia': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'mensaje_bienvenida': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 3, 'placeholder': 'Mensaje de bienvenida del personaje guía'}),
            'paleta_colores': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'nivel_gamificacion': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'tiene_recompensas': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'puntos_totales': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['temas_relacionados'].required = False
        self.fields['producto_origen'].queryset = (
            ProductoAcademico.objects.all().order_by('titulo'))
        self.fields['producto_origen'].required = False


# ============================================================================
# SECCIONES — PRODUCTO ACADÉMICO (SeccionPaper)
# ============================================================================

class SeccionPaperForm(forms.ModelForm):
    """Crear/editar una sección de ProductoAcademico con todos los
    campos condicionales por tipo_bloque (el template los muestra/oculta
    con JS según la selección)."""

    class Meta:
        model = SeccionPaper
        fields = [
            'tipo_seccion', 'numero_orden', 'subnumero', 'titulo',
            'tipo_bloque', 'contenido',
            'indicador_vinculado', 'configuracion_grafico',
            'conjunto_datos_vinculado', 'documento_vinculado',
            'sistema_vinculado', 'publicaciones_relacionadas',
            'indicadores_preseleccionados',
            'video_url', 'acordeon_items',
        ]
        widgets = {
            'tipo_seccion': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'numero_orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'subnumero': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Ej: 2.1, 4.2'}),
            'titulo': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título de la sección o subsección'}),
            'tipo_bloque': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'indicador_vinculado': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'configuracion_grafico': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 3, 'placeholder': '{"tipo": "barras|lineas|piramide", "anio_default": 2025}'}),
            'conjunto_datos_vinculado': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'documento_vinculado': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'sistema_vinculado': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'publicaciones_relacionadas': forms.SelectMultiple(attrs={'class': WIDGET_CLASSES, 'size': 5}),
            'indicadores_preseleccionados': forms.SelectMultiple(attrs={'class': WIDGET_CLASSES, 'size': 5}),
            'video_url': forms.URLInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'https://youtube.com/watch?v=...'}),
            'acordeon_items': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 4, 'placeholder': '[{"titulo": "Pregunta", "contenido": "Respuesta"}]'}),
        }

    def __init__(self, *args, **kwargs):
        producto = kwargs.pop('producto', None)
        super().__init__(*args, **kwargs)
        self.fields['contenido'].required = False
        self.fields['subnumero'].required = False
        self.fields['configuracion_grafico'].required = False
        self.fields['acordeon_items'].required = False
        self.fields['indicador_vinculado'].queryset = (
            Indicador.objects.filter(activo=True).order_by('nombre'))
        self.fields['indicadores_preseleccionados'].queryset = (
            Indicador.objects.filter(activo=True).order_by('nombre'))
        self.fields['publicaciones_relacionadas'].queryset = (
            ProductoAcademico.objects.all().order_by('titulo'))
        # Orden sugerido: siguiente número libre del producto
        if producto is not None and not self.instance.pk:
            ultimo = producto.secciones.order_by('-numero_orden').first()
            self.fields['numero_orden'].initial = (
                ultimo.numero_orden + 1 if ultimo else 1)

    def clean_configuracion_grafico(self):
        data = self.cleaned_data.get('configuracion_grafico')
        if data in (None, ''):
            return None
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                raise forms.ValidationError(
                    'La configuración del gráfico debe ser JSON válido.')
        return data

    def clean_acordeon_items(self):
        data = self.cleaned_data.get('acordeon_items')
        if data in (None, ''):
            return None
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                raise forms.ValidationError(
                    'Los items del acordeón deben ser JSON válido '
                    '(lista de {"titulo": ..., "contenido": ...}).')
        return data


# ============================================================================
# SECCIONES — PRODUCTO EDUCATIVO (SeccionEducativa)
# ============================================================================

class SeccionEducativaForm(forms.ModelForm):
    """Crear/editar una sección de ProductoEducativo con sus bloques
    interactivos gamificados."""

    class Meta:
        model = SeccionEducativa
        fields = [
            'numero_orden', 'titulo', 'icono_emoji',
            'tipo_bloque', 'contenido', 'configuracion_bloque',
            'indicador_vinculado', 'conjunto_datos_vinculado',
        ]
        widgets = {
            'numero_orden': forms.NumberInput(attrs={'class': WIDGET_CLASSES, 'min': 0}),
            'titulo': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Título de la sección'}),
            'icono_emoji': forms.TextInput(attrs={'class': WIDGET_CLASSES, 'placeholder': 'Ej: 🎯, 🌟, 🎨'}),
            'tipo_bloque': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'configuracion_bloque': forms.Textarea(attrs={'class': WIDGET_CLASSES, 'rows': 4, 'placeholder': '{"pregunta": "...", "opciones": [...], "respuesta_correcta": 0}'}),
            'indicador_vinculado': forms.Select(attrs={'class': WIDGET_CLASSES}),
            'conjunto_datos_vinculado': forms.Select(attrs={'class': WIDGET_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        producto = kwargs.pop('producto', None)
        super().__init__(*args, **kwargs)
        self.fields['contenido'].required = False
        self.fields['icono_emoji'].required = False
        self.fields['configuracion_bloque'].required = False
        self.fields['indicador_vinculado'].queryset = (
            Indicador.objects.filter(activo=True).order_by('nombre'))
        if producto is not None and not self.instance.pk:
            ultimo = producto.secciones.order_by('-numero_orden').first()
            self.fields['numero_orden'].initial = (
                ultimo.numero_orden + 1 if ultimo else 1)

    def clean_configuracion_bloque(self):
        data = self.cleaned_data.get('configuracion_bloque')
        if data in (None, ''):
            return None
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                raise forms.ValidationError(
                    'La configuración del bloque debe ser JSON válido.')
        return data
