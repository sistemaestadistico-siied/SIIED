from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.urls import reverse, path
from django.utils.html import format_html
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django import forms
import csv
from django_ckeditor_5.widgets import CKEditor5Widget
from .models import (
    MenuDominio, MenuTema, MenuSubtema, Indicador, 
    Desagregacion, DominioDesagregacion, NivelGeografico, CapaGeo, ElementoGeo,
    Dato, OperacionEstadistica, CategoriaInformacion, SistemaInformacion,
    NoticiaBanner, EstadisticaNoticia, EnlaceNoticia, CategoriaProyecto, ProyectoInformacion,
    AreaInfraestructura, CategoriaInfraestructura, SubcategoriaInfraestructura, GrupoDocumento, DocumentoInfraestructura,
    ReglaExtraccion, ProcesoExtraccion, ProcesoLog, Grafico, GraficoSerie, ConjuntoDatos, VariableConjuntoDatos, Aliado, Evento,
    Organismo, Suborganismo, EquipoOrganismo, RespuestaSatisfaccionRapida, RespuestaSatisfaccionCompleta,
    OpcionTaller, InscripcionTaller, RetoAnalisis, FuenteRequerida,
    FuenteDatos, FuenteOrigen, VariableFuente, EvaluacionSeguridad,
    BaseCatalogo, CampoCatalogo,
    ProductoAcademico, SeccionPaper, ImagenSeccion, ArchivoSeccion, CalendarioDifusion,
    ProductoEducativo, SeccionEducativa, LogroEducativo, ProgresoUsuarioEducativo,
    CatalogoDominio, CatalogoConsulta,
    PageVisit)
from .admin_eventos import EventoAdmin
from django.contrib.admin.models import LogEntry

# Widget para selector de color
class ColorWidget(forms.TextInput):
    input_type = 'color'
    
    def __init__(self, attrs=None):
        default_attrs = {'style': 'width: 50px; height: 40px; padding: 2px; border: 1px solid #ccc;'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

class DesagregacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'dominio', 'desagregacion_padre', 'descripcion')
    list_filter = ('dominio',)
    search_fields = ('nombre', 'descripcion')
    autocomplete_fields = ('dominio', 'desagregacion_padre')


class NivelGeograficoAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)


class DominioDesagregacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'en_catalogo', 'nivel_geografico', 'dominio_padre', 'tipo_agregacion_total', 'count_desagregaciones')
    list_filter = ('tipo', 'en_catalogo', 'nivel_geografico', 'tipo_agregacion_total')
    search_fields = ('nombre',)
    autocomplete_fields = ('nivel_geografico', 'dominio_padre')
    actions = ('admitir_al_catalogo',)

    @admin.action(description='Admitir dominios seleccionados al catálogo oficial')
    def admitir_al_catalogo(self, request, queryset):
        n = queryset.filter(en_catalogo=False).update(en_catalogo=True)
        self.message_user(request, f'{n} dominio(s) admitidos al catálogo.')

    fieldsets = (
        ('Información Básica', {
            'fields': ('nombre', 'tipo', 'nivel_geografico')
        }),
        ('Catálogo', {
            'fields': ('en_catalogo',),
            'description': (
                'Los dominios del catálogo oficial son los que se ofrecen para '
                '"asociar" en el wizard de cargas. Los creados por cargas nacen '
                'como pendientes (sin marcar) hasta que el validador decide '
                'admitirlos o conciliarlos con uno existente.'
            )
        }),
        ('Jerarquía', {
            'fields': ('dominio_padre',),
            'description': (
                'Si este dominio es subcategoría de otro (ej: "Barrio" dentro de "Comuna"), '
                'seleccione el dominio padre. El filtro de este dominio se mostrará subordinado '
                'y sus opciones se filtrarán en cascada según la selección del padre.'
            )
        }),
        ('Configuración de Totales', {
            'fields': ('tipo_agregacion_total',),
            'description': (
                '<div style="background: #f0f8ff; padding: 15px; border-left: 4px solid #0891b2; margin-bottom: 15px;">' 
                '<strong style="color: #0891b2;">🎯 ¿Cómo calcular el "Total" de este dominio?</strong><br><br>'
                '<strong>SUMA (default):</strong> El Total se calcula sumando todas las desagregaciones.<br>'
                '&nbsp;&nbsp;📊 <em>Ejemplo:</em> Población Total = Hombres + Mujeres + Otro<br>'
                '&nbsp;&nbsp;✅ <em>Usar cuando:</em> Conteos, poblaciones, cantidades físicas<br><br>'
                '<strong>NINGUNO:</strong> El Total NO se calcula, se extrae directamente del CSV.<br>'
                '&nbsp;&nbsp;📊 <em>Ejemplo:</em> Tasa de Desempleo Total (viene precalculada en el CSV)<br>'
                '&nbsp;&nbsp;✅ <em>Usar cuando:</em> Tasas, porcentajes, índices, promedios complejos<br><br>'
                '<strong>💡 Tip:</strong> Si necesitas cálculos complejos (ej: promedio ponderado), '
                'usa SUMA y configura la fórmula en la Regla de Extracción.<br>'
                '<a href="/static/admin/docs/SOLUCION_AGREGACION_TOTALES.md" target="_blank" style="color: #0891b2; font-weight: bold;">'
                '📖 Ver documentación completa →</a>'
                '</div>'
            )
        }),
    )
    
    def count_desagregaciones(self, obj):
        count = obj.desagregaciones.count()
        if count == 0:
            return format_html('<span style="color: #ef4444;">⚠️ 0</span>')
        return count
    count_desagregaciones.short_description = 'Desagregaciones'
    count_desagregaciones.admin_order_field = 'desagregaciones__count'


# --- Widgets y formularios personalizados ---
# Escalas de color de Plotly (curado para choropleth)
PLOTLY_COLOR_SCALES = [
    # Perceptuales
    'Viridis', 'Plasma', 'Inferno', 'Magma', 'Cividis', 'Turbo',
    # Secuenciales
    'Blues', 'Greens', 'Greys', 'Oranges', 'Purples', 'Reds',
    'YlGn', 'YlGnBu', 'YlOrBr', 'YlOrRd', 'BuGn', 'BuPu', 'GnBu', 'OrRd', 'PuBu', 'PuBuGn', 'PuRd', 'RdPu',
    # Divergentes
    'Bluered', 'RdBu', 'RdGy', 'RdYlBu', 'RdYlGn', 'Spectral',
    # Clásicas
    'Picnic', 'Portland', 'Jet', 'Hot', 'Blackbody', 'Earth', 'Electric', 'Rainbow',
]

COLOR_INPUT = forms.TextInput(attrs={'type': 'color'})

class MenuDominioForm(forms.ModelForm):
    class Meta:
        model = MenuDominio
        fields = '__all__'
        widgets = {
            'color': COLOR_INPUT,
        }

class GraficoSerieForm(forms.ModelForm):
    class Meta:
        model = GraficoSerie
        fields = '__all__'
        widgets = {
            'color': COLOR_INPUT,
        }



    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class DesagregacionPorDominioMultipleField(forms.ModelMultipleChoiceField):
    """M2M de desagregaciones etiquetadas con su dominio: 'Comuna › 3'."""
    def label_from_instance(self, obj):
        dom = getattr(obj, 'dominio', None)
        return f"{dom.nombre} › {obj.nombre}" if dom else obj.nombre


# Register your models here.
class MenuDominioAdmin(admin.ModelAdmin):
    form = MenuDominioForm

admin.site.register(MenuDominio, MenuDominioAdmin)
admin.site.register(MenuTema)


class IndicadoresAdicionalesInline(admin.TabularInline):
    """Indicadores que cuelgan de este subtema como clasificación
    ADICIONAL (los del subtema principal están en la lista normal)."""
    model = Indicador.subtemas_adicionales.through
    fk_name = 'menusubtema'
    autocomplete_fields = ('indicador',)
    extra = 1
    verbose_name = 'Indicador con este subtema adicional'
    verbose_name_plural = 'Indicadores adicionales (pertenecen también a otros subtemas)'


class MenuSubtemaAdmin(admin.ModelAdmin):
    # search_fields requerido por el autocomplete de los inlines M2M
    search_fields = ('nombre', 'tema__nombre', 'tema__dominio__nombre')
    list_display = ('nombre', 'tema', 'dominio', 'activo', 'orden')
    list_filter = ('tema__dominio', 'tema', 'activo')
    inlines = [IndicadoresAdicionalesInline]

    def dominio(self, obj):
        return obj.tema.dominio if obj.tema else None
    dominio.short_description = 'Dominio'
    dominio.admin_order_field = 'tema__dominio__nombre'


admin.site.register(MenuSubtema, MenuSubtemaAdmin)

@admin.register(OperacionEstadistica)
class OperacionEstadisticaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'organismo', 'suborganismo', 'periodicidad', 'activo', 'sicode')
    list_filter = ('activo', 'organismo', 'periodicidad', 'tipo_oe_i')
    search_fields = ('codigo', 'nombre', 'organismo', 'suborganismo', 'tema', 'sicode')
    list_editable = ('activo',)
    
    fieldsets = (
        ('Identificación', {
            'fields': ('codigo', 'nombre', 'sicode', 'activo')
        }),
        ('Clasificación', {
            'fields': ('organismo', 'suborganismo', 'area_tem', 'tema', 'tipo_oe_i', 'tipo_operacion')
        }),
        ('Descripción', {
            'fields': ('descripcion', 'objetivo', 'descripcion_proceso', 'principales_resultados'),
            'classes': ('collapse',)
        }),
        ('Metodología', {
            'fields': ('metodologia', 'unidad_observ', 'periodicidad', 'fecha_inicio', 'fecha_fin', 
                      'entidad_recopiladora', 'enfoque_diferencial', 'desagregacion_resultados'),
            'classes': ('collapse',)
        }),
        ('Documentación', {
            'fields': ('doc_met', 'ficha_met', 'manual_op', 'diccionario_datos', 'doc_cons_valid'),
            'classes': ('collapse',)
        }),
        ('Enlaces', {
            'fields': ('url', 'link_adda', 'link_pe'),
            'classes': ('collapse',)
        }),
        ('Alineación Institucional', {
            'fields': ('mop', 'pdd', 'pe', 'proyecto', 'fun_org', 'fun_sub', 'estr_org', 'p_bp', 'num'),
            'classes': ('collapse',)
        }),
        ('Información de Contacto', {
            'fields': ('nombre_tematico', 'correo_tematico', 'celular_tematico', 
                      'nombre_coordinador', 'correo_coordinador', 'celular_coordinador'),
            'classes': ('collapse',),
            'description': '<div style="background:#fff3cd; border-left:4px solid #ffc107; padding:12px; margin-bottom:10px;">'
                          '<strong>⚠️ Datos Personales Protegidos:</strong> Esta información NO se muestra en el portal público '
                          'por cumplimiento de la Ley 1581/2012 de Protección de Datos Personales. '
                          'Solo es visible para administradores del sistema.</div>'
        }),
        ('Metadatos Adicionales', {
            'fields': ('grupo_productor', 'adda_1', 'cant_amda', 'amda_clas', 'anio_adda', 'anio_act_pe',
                      'responsable_actualizacion', 'estado_actualizacion', 'acciones_fortalecimiento',
                      'pendiente', 'observaciones', 'c_organismo', 'cod_cg'),
            'classes': ('collapse',)
        }),
    )
# admin.site.register(Grafico)  # Reemplazado por GraficoAdmin
# admin.site.register(GraficoSerie)  # Reemplazado por GraficoSerieInline
# admin.site.register(Dato) - Removido para evitar duplicados
class ConjuntoDatosAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'operacion', 'organismo_productor', 'tipo_estudio', 'fecha_carga')
    list_filter = ('operacion', 'tipo_estudio', 'organismo_productor')
    search_fields = ('nombre', 'descripcion', 'identificador', 'palabras_clave')
    ordering = ('nombre',)
    readonly_fields = ('fecha_carga',)
    
    fieldsets = (
        ('Identificación (DDI)', {
            'fields': ('nombre', 'descripcion', 'operacion', 'identificador',
                      'version', 'doi_citacion', 'idioma', 'palabras_clave')
        }),
        ('Productor y Distribución', {
            'fields': ('organismo_productor', 'productor_legado', 'financiamiento',
                      'distribuidor', 'contacto_nombre', 'contacto_email')
        }),
        ('Universo y Cobertura', {
            'fields': ('universo', 'unidad_analisis', 'cobertura_geografica',
                      'cobertura_temporal')
        }),
        ('Metodología', {
            'fields': ('tipo_estudio', 'metodo_muestreo', 'modo_coleccion',
                      'instrumento', 'periodo_campo_inicio', 'periodo_campo_fin',
                      'ponderacion', 'notas_procesamiento')
        }),
        ('Acceso y Uso', {
            'fields': ('condiciones_acceso', 'derechos_uso', 'confidencialidad')
        }),
        ('Archivo', {
            'fields': ('archivo_csv', 'fecha_carga'),
            'classes': ('collapse',)
        }),
    )

admin.site.register(ConjuntoDatos, ConjuntoDatosAdmin)
# admin.site.register(NivelGeografico)  # Reemplazado por NivelGeograficoAdmin
admin.site.register(CapaGeo)
admin.site.register(ElementoGeo)
# admin.site.register(DominioDesagregacion)  # Reemplazado por DominioDesagregacionAdmin
# admin.site.register(Desagregacion)  # Reemplazado por DesagregacionAdmin


class VariableConjuntoDatosAdmin(admin.ModelAdmin):
    list_display = ('codigo_variable', 'nombre_variable', 'conjunto_datos', 'unidad_medida', 'tipo_variable_estadistica', 'orden')
    list_filter = ('conjunto_datos', 'tipo_variable_estadistica', 'periodicidad')
    search_fields = ('codigo_variable', 'nombre_variable', 'definicion_conceptual', 'conjunto_datos__nombre')
    ordering = ('conjunto_datos', 'orden', 'codigo_variable')
    readonly_fields = ('id',)
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('conjunto_datos', 'codigo_variable', 'nombre_variable', 'orden')
        }),
        ('Definición', {
            'fields': ('definicion_conceptual', 'poblacion_objetivo')
        }),
        ('Cobertura y Desagregación', {
            'fields': ('cobertura_geografica', 'desagregacion_geografica', 'desagregacion_tematica')
        }),
        ('Características del Dato', {
            'fields': ('tipo_dato', 'dominio_dato', 'unidad_medida', 'tipo_variable_estadistica')
        }),
        ('Fuente y Periodicidad', {
            'fields': ('fuente_datos', 'periodicidad', 'organismo_productor',
                      'organismo_productor_legado')
        }),
        ('Detalle Estadístico', {
            'fields': ('pregunta', 'universo', 'concepto',
                      'tipo_representacion', 'categoria_estadistica'),
            'classes': ('collapse',)
        }),
        ('Observaciones', {
            'fields': ('observaciones', 'referencias'),
            'classes': ('collapse',)
        }),
    )

admin.site.register(VariableConjuntoDatos, VariableConjuntoDatosAdmin)


class MenuTemaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'dominio', 'activo', 'imagen_url', 'icono')
    list_filter = ('dominio', 'activo')
    search_fields = ('nombre', 'descripcion')
    prepopulated_fields = {'slug': ('nombre',)}
    fieldsets = (
        (None, {
            'fields': ('nombre', 'slug', 'descripcion', 'dominio', 'activo', 'orden')
        }),
        ('Apariencia', {
            'fields': ('icono', 'imagen_url'),
            'classes': ('collapse',)
        }),

    )

class ReglaExtraccionAdmin(admin.ModelAdmin):
    list_display = ('indicador', 'columna_fecha', 'estado_badge', 'ultima_ejecucion_formatted', 'activo', 'procesar_datos_button')
    list_filter = ('estado_procesamiento', 'activo', 'indicador__subtema__tema__dominio')
    readonly_fields = ('ultima_ejecucion', 'estado_procesamiento')
    search_fields = ('indicador__nombre', 'indicador__subtema__nombre')
    list_editable = ('activo',)
    
    def estado_badge(self, obj):
        """Muestra el estado con un badge colorido"""
        colores = {
            'pendiente': '#ffc107',
            'procesando': '#2196f3',
            'completado': '#4caf50',
            'error': '#f44336'
        }
        iconos = {
            'pendiente': '⏳',
            'procesando': '🔄',
            'completado': '✅',
            'error': '❌'
        }
        color = colores.get(obj.estado_procesamiento, '#666')
        icono = iconos.get(obj.estado_procesamiento, '❓')
        return format_html(
            '<span style="background:{}; color:white; padding:4px 12px; border-radius:12px; font-weight:500; font-size:12px;">{} {}</span>',
            color, icono, obj.get_estado_procesamiento_display()
        )
    estado_badge.short_description = 'Estado'
    estado_badge.admin_order_field = 'estado_procesamiento'
    
    def ultima_ejecucion_formatted(self, obj):
        """Muestra la última ejecución formateada"""
        if obj.ultima_ejecucion:
            from django.utils import timezone
            from django.utils.timesince import timesince
            tiempo_transcurrido = timesince(obj.ultima_ejecucion, timezone.now())
            return format_html(
                '<span title="{}">{} atrás</span>',
                obj.ultima_ejecucion.strftime('%Y-%m-%d %H:%M:%S'),
                tiempo_transcurrido
            )
        return format_html('<span style="color:#999;">Nunca</span>')
    ultima_ejecucion_formatted.short_description = 'Última Ejecución'
    ultima_ejecucion_formatted.admin_order_field = 'ultima_ejecucion'
    
    fieldsets = (
        ('Información General', {
            'fields': ('indicador',)
        }),
        ('Configuración de Extracción', {
            'fields': ('columnas_fuente', 'columna_fecha', 'formula', 'filtros'),
            'description': 'Configura cómo extraer y calcular los datos del archivo CSV.'
        }),
        ('Configuración Avanzada', {
            'fields': ('orden_desagregaciones',),
            'classes': ('collapse',)
        }),
        ('Estado', {
            'fields': ('activo', 'estado_procesamiento', 'ultima_ejecucion'),
            'classes': ('collapse',)
        }),
    )
    
    class Media:
        css = {
            'all': ('admin/css/forms.css',)
        }

    def clean(self):

        from django.core.exceptions import ValidationError
        import pandas as pd
        
        # Validar que columnas existen en CSV
        if self.indicador.conjunto_datos and self.indicador.conjunto_datos.archivo_csv:
            try:
                df = pd.read_csv(self.indicador.conjunto_datos.archivo_csv.path, nrows=1, sep=';')
                columnas_csv = set(df.columns)
                columnas_regla = set(self.columnas_fuente or [])
                
                faltantes = columnas_regla - columnas_csv
                if faltantes:
                    raise ValidationError({
                        'columnas_fuente': f'❌ Columnas no encontradas en CSV: {", ".join(faltantes)}'
                    })
            except Exception as e:
                raise ValidationError(f'Error leyendo CSV: {e}')
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        
        # Añadir ayuda contextual para el campo formula
        if 'formula' in form.base_fields:
            form.base_fields['formula'].help_text = (
                'Fórmula para calcular el valor final. '
                'Consulta el manual de fórmulas más abajo para ejemplos y sintaxis completa.'
            )
        
        # Añadir ayuda contextual para el campo filtros
        if 'filtros' in form.base_fields:
            form.base_fields['filtros'].help_text = (
                'Filtros en formato JSON para seleccionar subconjuntos de datos. '
                'Consulta el manual de filtros más abajo para ejemplos y sintaxis completa.'
            )
        
        return form
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_formula_manual'] = True
        extra_context['show_filter_manual'] = True
        return super().change_view(request, object_id, form_url, extra_context)
    
    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_formula_manual'] = True
        extra_context['show_filter_manual'] = True
        return super().add_view(request, form_url, extra_context)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "indicador":
            # Mostrar indicadores ordenados por dominio, tema y subtema
            kwargs["queryset"] = Indicador.objects.select_related(
                'subtema__tema__dominio'
            ).order_by(
                'subtema__tema__dominio__nombre',
                'subtema__tema__nombre',
                'subtema__nombre',
                'nombre'
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def procesar_datos_button(self, obj):
        from django.urls import reverse
        if obj.id:
            url = reverse('admin:reglaextraccion_procesar_datos', args=[obj.id])
            return format_html('<a class="button" href="{}">Procesar Datos</a>', url)
        return ""
    procesar_datos_button.short_description = 'Acciones'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('procesar-datos/<int:regla_id>/', self.admin_site.admin_view(self.procesar_datos), name='reglaextraccion_procesar_datos'),
        ]
        return custom_urls + urls
    
    def procesar_datos(self, request, regla_id):
        # Importar las funciones necesarias
        from django.http import HttpResponse
        from django.template.response import TemplateResponse
        from django.urls import reverse
        from django.utils.safestring import mark_safe
        import subprocess
        import sys
        import os
        
        try:
            regla = ReglaExtraccion.objects.get(id=regla_id)
            
            # Ejecutar el comando de diagnóstico y capturar la salida
            manage_py_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'manage.py')
            cmd = [sys.executable, manage_py_path, 'diagnosticar_conjunto_datos', '--indicador-id', str(regla.indicador.id)]
            
            # Ejecutar el comando y capturar la salida
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            
            # Combinar la salida estándar y de error
            diagnostic_output = stdout + stderr
            
            # Si es una solicitud POST, significa que el usuario confirmó continuar
            if request.method == 'POST':
                # Crear proceso y lanzar en background, luego redirigir a visor en vivo
                from .background import lanzar_procesamiento_en_background
                proceso = ProcesoExtraccion.objects.create(indicador=regla.indicador, regla=regla, estado='pendiente')
                lanzar_procesamiento_en_background(proceso.id)
                messages.info(request, f'Proceso #{proceso.id} iniciado para {regla.indicador.nombre}. Será redirigido al visor en vivo.')
                return HttpResponseRedirect(reverse('indicadores:proceso_en_vivo', args=[proceso.id]))
            
            # Si es una solicitud GET, mostrar el diagnóstico y pedir confirmación
            context = {
                'title': f'Diagnóstico para {regla.indicador.nombre}',
                'diagnostic_output': diagnostic_output,
                'regla': regla,
                'opts': self.model._meta,
                'original': regla,
                'has_view_permission': True,
                'has_change_permission': True,
            }
            
            return TemplateResponse(request, 'admin/diagnostic_confirmation.html', context)
            
        except ReglaExtraccion.DoesNotExist:
            messages.error(request, 'Regla de extracción no encontrada')
            return HttpResponseRedirect('../')
        except Exception as e:
            messages.error(request, f'Error al ejecutar diagnóstico: {str(e)}')
            return HttpResponseRedirect('../')

admin.site.register(ReglaExtraccion, ReglaExtraccionAdmin)

class ProcesoExtraccionAdmin(admin.ModelAdmin):
    list_display = ('id', 'indicador', 'regla', 'estado', 'created_at', 'finished_at', 'exit_code')
    list_filter = ('estado', 'created_at', 'indicador__subtema__tema__dominio')
    search_fields = ('indicador__nombre', 'regla__indicador__nombre')
    readonly_fields = ('created_at', 'started_at', 'finished_at', 'exit_code', 'error_message')
    ordering = ('-created_at',)

admin.site.register(ProcesoExtraccion, ProcesoExtraccionAdmin)

class ProcesoLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'proceso', 'nivel', 'mensaje_truncado', 'creado_en')
    list_filter = ('nivel', 'creado_en', 'proceso__estado')
    search_fields = ('mensaje', 'proceso__indicador__nombre')
    readonly_fields = ('proceso', 'nivel', 'mensaje', 'creado_en')
    ordering = ('-creado_en',)
    
    def mensaje_truncado(self, obj):
        return obj.mensaje[:100] + '...' if len(obj.mensaje) > 100 else obj.mensaje
    mensaje_truncado.short_description = 'Mensaje'

admin.site.register(ProcesoLog, ProcesoLogAdmin)

class EstadisticaNoticiaInline(admin.TabularInline):
    model = EstadisticaNoticia
    extra = 1
    fields = ('titulo', 'valor', 'descripcion', 'orden')

class EnlaceNoticiaInline(admin.TabularInline):
    model = EnlaceNoticia
    extra = 1
    fields = ('titulo', 'url', 'descripcion', 'orden')

class NoticiaBannerAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'activa', 'orden', 'fecha_publicacion', 'fecha_actualizacion')
    list_filter = ('activa', 'fecha_publicacion')
    search_fields = ('titulo', 'subtitulo', 'descripcion')
    list_editable = ('activa', 'orden')
    ordering = ['-orden', '-fecha_publicacion']
    inlines = [EstadisticaNoticiaInline, EnlaceNoticiaInline]
    
    fieldsets = (
        ('Información Principal', {
            'fields': ('titulo', 'subtitulo', 'descripcion', 'imagen_url')
        }),
        ('Enlace Principal', {
            'fields': ('enlace_principal', 'texto_enlace_principal')
        }),
        ('Configuración', {
            'fields': ('activa', 'orden')
        }),
    )

admin.site.register(NoticiaBanner, NoticiaBannerAdmin)


class DatoAdmin(admin.ModelAdmin):
    list_display = ('indicador_con_ruta', 'fecha_dato', 'valor_dato', 'mostrar_desagregaciones')
    list_filter = (
        'indicador__subtema__tema__dominio',
        'indicador__subtema__tema',
        'indicador__subtema',
        'indicador',
        'fecha_dato'
    )
    search_fields = (
        'indicador__nombre', 
        'indicador__subtema__nombre',
        'indicador__subtema__tema__nombre',
        'indicador__subtema__tema__dominio__nombre'
    )
    readonly_fields = ('mostrar_desagregaciones',)
    
    def get_form(self, request, obj=None, **kwargs):
        """Usar formulario personalizado con checkboxes"""
        form = super().get_form(request, obj, **kwargs)
        
        # Si estamos editando un dato existente, filtrar desagregaciones
        if obj:
            indicador = obj.indicador
            
            # Filtrar desagregaciones geográficas
            dominios_geo = indicador.dominios_desagregacion_geografica.all()
            form.base_fields['desagregaciones_geograficas'].queryset = Desagregacion.objects.filter(dominio__in=dominios_geo)
            form.base_fields['desagregaciones_geograficas'].widget = forms.CheckboxSelectMultiple()
            
            # Filtrar desagregaciones temáticas
            dominios_tem = indicador.dominios_desagregacion_tematica.all()
            form.base_fields['desagregaciones_tematicas'].queryset = Desagregacion.objects.filter(dominio__in=dominios_tem)
            form.base_fields['desagregaciones_tematicas'].widget = forms.CheckboxSelectMultiple()
        else:
            # Para nuevos datos, usar checkboxes pero sin filtrar (se filtrará al seleccionar indicador)
            form.base_fields['desagregaciones_geograficas'].widget = forms.CheckboxSelectMultiple()
            form.base_fields['desagregaciones_tematicas'].widget = forms.CheckboxSelectMultiple()
        
        return form
    
    def indicador_con_ruta(self, obj):
        indicador = obj.indicador
        return f"{indicador.subtema.tema.dominio.nombre} > {indicador.subtema.tema.nombre} > {indicador.subtema.nombre} > {indicador.nombre}"
    indicador_con_ruta.short_description = 'Indicador (Dominio > Tema > Subtema > Indicador)'
    indicador_con_ruta.admin_order_field = 'indicador__subtema__tema__dominio__nombre'
    
    def mostrar_desagregaciones(self, obj):
        desagregaciones = obj.desagregaciones_tematicas.all() | obj.desagregaciones_geograficas.all()
        return ", ".join([d.nombre for d in desagregaciones])
    mostrar_desagregaciones.short_description = 'Desagregaciones'
    
    # Ordenar por defecto por dominio, tema, subtema, indicador y fecha
    ordering = (
        'indicador__subtema__tema__dominio__nombre',
        'indicador__subtema__tema__nombre',
        'indicador__subtema__nombre',
        'indicador__nombre',
        '-fecha_dato'
    )

admin.site.register(Dato, DatoAdmin)


# ============================================================================
# INLINES PARA INDICADOR
# ============================================================================

class DatoInlineForm(forms.ModelForm):
    """Formulario personalizado para el inline de Dato con checkboxes"""
    desagregaciones_geograficas = forms.ModelMultipleChoiceField(
        queryset=Desagregacion.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Desagregaciones Geográficas'
    )
    desagregaciones_tematicas = forms.ModelMultipleChoiceField(
        queryset=Desagregacion.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Desagregaciones Temáticas'
    )
    
    class Meta:
        model = Dato
        fields = ['fecha_dato', 'valor_dato', 'desagregaciones_geograficas', 'desagregaciones_tematicas']
    
    def __init__(self, *args, **kwargs):
        # Extraer el indicador si viene en initial
        indicador = None
        if 'initial' in kwargs and 'indicador' in kwargs['initial']:
            indicador = kwargs['initial']['indicador']
            # Remover del initial para que no cause problemas
            del kwargs['initial']['indicador']
        
        super().__init__(*args, **kwargs)
        
        # Si no vino en initial, intentar obtenerlo del instance
        if not indicador and self.instance and self.instance.pk:
            indicador = self.instance.indicador
        
        # Filtrar desagregaciones según los dominios del indicador
        if indicador:
            dominios_geo = indicador.dominios_desagregacion_geografica.all()
            self.fields['desagregaciones_geograficas'].queryset = Desagregacion.objects.filter(dominio__in=dominios_geo)
            
            dominios_tem = indicador.dominios_desagregacion_tematica.all()
            self.fields['desagregaciones_tematicas'].queryset = Desagregacion.objects.filter(dominio__in=dominios_tem)
        else:
            # Si no hay indicador, mostrar todas (esto pasa al crear el primer form vacío)
            self.fields['desagregaciones_geograficas'].queryset = Desagregacion.objects.all()
            self.fields['desagregaciones_tematicas'].queryset = Desagregacion.objects.all()


class DatoInline(admin.TabularInline):
    """Inline para gestionar datos del indicador directamente"""
    model = Dato
    form = DatoInlineForm
    extra = 0  # No mostrar filas vacías (usar botón "Agregar otro Dato")
    fields = ('fecha_dato', 'valor_dato', 'desagregaciones_geograficas', 'desagregaciones_tematicas')
    can_delete = True
    show_change_link = True
    verbose_name = "Dato del Indicador"
    verbose_name_plural = "📊 Datos del Indicador (Mostrando 10 por página)"
    fk_name = 'indicador'  # Especificar explícitamente la FK
    
    # Configuración de paginación
    per_page = 10
    
    def get_formset(self, request, obj=None, **kwargs):
        """Sobreescribir para tener acceso al objeto indicador"""
        # Guardar el objeto indicador para usarlo en get_queryset
        self._current_obj = obj
        
        # Obtener el formset
        formset = super().get_formset(request, obj, **kwargs)
        
        # Pasar el indicador al formulario para que pueda filtrar las desagregaciones
        if obj:
            # Modificar el __init__ del form para pasar el indicador
            original_init = formset.form.__init__
            
            def new_init(form_self, *args, **kwargs):
                # Agregar el indicador a initial si no existe
                if 'initial' not in kwargs:
                    kwargs['initial'] = {}
                kwargs['initial']['indicador'] = obj
                original_init(form_self, *args, **kwargs)
            
            formset.form.__init__ = new_init
        
        return formset
    
    def get_queryset(self, request):
        """Obtener queryset con paginación manual"""
        # Obtener el queryset base
        qs = super().get_queryset(request)
        
        # IMPORTANTE: Filtrar explícitamente por el indicador actual
        if hasattr(self, '_current_obj') and self._current_obj:
            qs = qs.filter(indicador=self._current_obj)
        
        # Debug: verificar si está filtrado
        total_sin_filtro = self.model.objects.count()
        total_con_filtro = qs.count()
        
        print(f"\n{'='*60}")
        print(f"DEBUG DatoInline.get_queryset - Filtrado")
        print(f"  Total datos en BD: {total_sin_filtro}")
        print(f"  Total datos filtrados: {total_con_filtro}")
        if hasattr(self, '_current_obj') and self._current_obj:
            print(f"  Indicador: {self._current_obj.id} - {self._current_obj.nombre}")
        
        # Ordenar por fecha descendente
        qs = qs.order_by('-fecha_dato')
        
        # Obtener página actual
        page = request.GET.get('datos_page', 1)
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1
        
        # Calcular offset y limit
        offset = (page - 1) * self.per_page
        limit = offset + self.per_page
        
        print(f"  Página: {page}")
        print(f"  Offset: {offset}")
        print(f"  Limit: {limit}")
        print(f"  Per page: {self.per_page}")
        
        # IMPORTANTE: Obtener los IDs primero (antes de hacer slice)
        # Esto evita el error "Cannot filter a query once a slice has been taken"
        ids_page = list(qs.values_list('id', flat=True)[offset:limit])
        
        print(f"  IDs obtenidos: {ids_page}")
        print(f"  Cantidad de IDs: {len(ids_page)}")
        
        # Ahora filtrar por esos IDs y mantener el orden
        if ids_page:
            # Preservar el orden usando CASE WHEN
            from django.db.models import Case, When, IntegerField
            preserved = Case(*[When(id=pk, then=pos) for pos, pk in enumerate(ids_page)], output_field=IntegerField())
            qs_final = self.model.objects.filter(id__in=ids_page).order_by(preserved)
            print(f"  Queryset final count: {qs_final.count()}")
            print(f"{'='*60}\n")
            return qs_final
        
        print(f"  No hay IDs, retornando queryset vacío")
        print(f"{'='*60}\n")
        return qs.none()
    
    def has_add_permission(self, request, obj=None):
        """Siempre permitir agregar datos"""
        return True
    
    def has_change_permission(self, request, obj=None):
        """Siempre permitir editar datos"""
        return True
    
    def has_delete_permission(self, request, obj=None):
        """Siempre permitir eliminar datos"""
        return True
    
    def mostrar_desagregaciones_inline(self, obj):
        if obj.pk:
            desagregaciones = list(obj.desagregaciones_tematicas.all()) + list(obj.desagregaciones_geograficas.all())
            if desagregaciones:
                return ", ".join([d.nombre for d in desagregaciones])
            return "Sin desagregaciones"
        return "-"
    mostrar_desagregaciones_inline.short_description = 'Desagregaciones'


class IndicadorAdminForm(forms.ModelForm):
    """Formulario personalizado para el admin de Indicador"""
    class Meta:
        model = Indicador
        fields = '__all__'
        # Nombres de la plantilla oficial de metadatos (Metadatos_SDMX):
        # no existe 'Objetivo' ni 'Método de medición' como campos propios —
        # el cálculo del indicador los integra en un solo metadato.
        labels = {
            'metodo_medicion': 'Cálculo del indicador (fórmula + método de medición)',
            'formula_ficha': 'Fórmula del indicador',
            'objetivo': 'Objetivo (legado — fuera de la plantilla oficial)',
        }
        # Especificar widgets Textarea para TODOS los campos de texto (sin CKEditor)
        widgets = {
            # Campos descriptivos (MSD)
            'descripcion_indicador': forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            'objetivo': forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            # Metodología
            'metodo_medicion': forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            'formula_ficha': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
            'variables': forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            # Cobertura (MSD)
            'alcance_tematico': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
            'cobertura_geografica': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
            'poblacion_objetivo': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
            'nomenclaturas_clasificaciones': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
            'medios_difusion': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
            # Comentarios (MSD) y notas internas
            'comentarios_adicionales': forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            'notas': forms.Textarea(attrs={'rows': 3, 'cols': 80}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si el indicador ya existe y tiene conjunto_datos, mostrar info
        if self.instance.pk and self.instance.conjunto_datos:
            conjunto_datos = self.instance.conjunto_datos
            if conjunto_datos.archivo_csv:
                import os
                filename = os.path.basename(conjunto_datos.archivo_csv.name)
                size_mb = conjunto_datos.archivo_csv.size / (1024 * 1024)
                # Formatear el tamaño antes de pasarlo a format_html
                size_formatted = f"{size_mb:.2f}"
                help_text = format_html(
                    '<div style="margin-top: 10px; padding: 10px; background: #e8f5e9; border-left: 4px solid #4caf50; border-radius: 4px; color: #1b5e20;">'
                    '<strong style="color: #1b5e20;">📄 Archivo actual:</strong> {}<br>'
                    '<strong style="color: #1b5e20;">📊 Tamaño:</strong> {} MB</div>',
                    filename,
                    size_formatted
                )
                self.fields['conjunto_datos'].help_text = help_text


class SubtemasAdicionalesInline(admin.TabularInline):
    """Subtemas ADICIONALES del indicador (pueden ser de cualquier
    dominio). El subtema principal sigue en el campo FK de arriba."""
    model = Indicador.subtemas_adicionales.through
    fk_name = 'indicador'
    autocomplete_fields = ('menusubtema',)
    extra = 1
    verbose_name = 'Subtema adicional'
    verbose_name_plural = 'Subtemas adicionales (el indicador también aparece bajo estos)'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'menusubtema__tema__dominio')


class IndicadorAdmin(admin.ModelAdmin):
    form = IndicadorAdminForm
    change_form_template = 'admin/indicadores/indicador/change_form.html'
    list_display = ('nombre', 'subtema', 'orden', 'activo', 'procesar_conjunto_datos_button', 'descargar_conjunto_datos_button', 'descargar_csv_button', 'importar_datos_button', 'actualizar_desagregaciones_button', 'validar_datos_button')
    list_filter = ('activo', 'subtema__tema__dominio', 'subtema__tema', 'subtema')
    search_fields = ('nombre', 'codigo_indicador', 'sigla', 'subtema__nombre', 'subtema__tema__nombre', 'subtema__tema__dominio__nombre')
    list_editable = ('orden',)
    inlines = [DatoInline, SubtemasAdicionalesInline]

    fieldsets = (
        ('0. Identificación del Indicador', {
            'fields': ('nombre', 'codigo_indicador', 'sigla', 'grupo_indicador',
                      'subtema', 'activo', 'orden'),
            'description': 'Campos 0.1–0.4 del estándar MSD + clasificación: '
                          'el subtema principal define la ruta canónica; los '
                          'subtemas adicionales se gestionan en el inline de '
                          'abajo (cualquier dominio).'
        }),
        ('1. Contacto Institucional (MSD)', {
            'fields': ('organismo_responsable', 'entidad_responsable_legado', 'suborganismo',
                       'correo_contacto', 'telefono_contacto', 'fecha_publicacion_metadatos'),
            'description': 'Campos 1.1–1.6 del estándar MSD.'
        }),
        ('2. Características del Indicador (MSD)', {
            'fields': ('descripcion_indicador', 'metodo_medicion', 'formula_ficha',
                      'variables', 'unidad_medida', 'fuente_datos', 'operacion',
                      'nombre_conjunto_datos',
                      'nomenclaturas_clasificaciones', 'alcance_tematico', 'poblacion_objetivo',
                      'cobertura_geografica', 'periodo_referencia', 'periodo_base'),
            'description': 'Campos de la plantilla oficial de metadatos '
                          '(Metadatos_SDMX). En esa plantilla el "Cálculo del '
                          'indicador" integra fórmula y método de medición.'
        }),
        ('Campos del estándar anterior (legado)', {
            'fields': ('objetivo',),
            'classes': ('collapse',),
            'description': 'La plantilla oficial ya no incluye "Objetivo" como '
                          'metadato: se conserva por compatibilidad con datos '
                          'históricos, pero no se usa en fichas nuevas.'
        }),
        ('3. Difusión (MSD)', {
            'fields': ('serie_historica_disponible', 'frecuencia_difusion', 'medios_difusion'),
            'classes': ('collapse',),
            'description': 'Campos 3.1–3.3 del estándar MSD.'
        }),
        ('4. Comentarios (MSD)', {
            'fields': ('comentarios_adicionales',),
            'classes': ('collapse',),
            'description': 'Campo 4.1 del estándar MSD.'
        }),
        ('5. Referencias', {
            'fields': ('referencias',),
            'classes': ('collapse',),
            'description': 'Campo 5.1 — referencias en normas APA 7.ª edición.'
        }),
        ('6. Responsabilidad Institucional', {
            'fields': ('equipo_responsable',
                      'nombre_responsable_validacion', 'cargo_responsable_validacion',
                      'correo_responsable_validacion', 'celular_responsable_validacion'),
            'classes': ('collapse',),
            'description': 'Campo 6.3 (equipo) + responsable técnico de validación. '
                          '6.1/6.2 (organismo/suborganismo) se gestionan en la sección 1.'
        }),
        ('Trazabilidad de la ficha', {
            'fields': ('fecha_elaboracion', 'fecha_actualizacion_ficha'),
            'classes': ('collapse',),
            'description': 'Columnas Fecha_Elaboracion / Fecha_Actualizacion de la plantilla Excel.'
        }),
        ('Gestión de Datos', {
            'fields': ('conjunto_datos',),
            'classes': ('collapse',),
            'description': format_html(
                '<div style="padding: 15px; background: #e3f2fd; border-left: 4px solid #2196f3; border-radius: 4px; margin-bottom: 15px;">'
                '<strong style="font-size: 14px; color: #1565c0;">💡 Opciones para gestionar datos:</strong><br>'
                '<ul style="margin: 10px 0; color: #1565c0;">'
                '<li><strong>Crear datos manualmente:</strong> Use la tabla "Datos del Indicador" abajo</li>'
                '<li><strong>Importar datos masivamente:</strong> Use el botón "📥 Importar Datos CSV" al final de esta página</li>'
                '<li><strong>Procesar desde conjunto_datos:</strong> Configure conjunto_datos abajo y use "Procesar conjunto_datos" en la lista</li>'
                '</ul></div>'
            )
        }),
        ('Configuración interna', {
            'fields': ('catalogo_consulta', 'mostrar_mapa',
                      'dominios_desagregacion_tematica', 'dominios_desagregacion_geografica',
                      'notas'),
            'classes': ('collapse',),
            'description': 'Campos internos: no aparecen en la ficha técnica pública.'
        }),
    )
    
    def changelist_view(self, request, extra_context=None):
        """Agregar botones del wizard e importación al changelist"""
        extra_context = extra_context or {}
        extra_context['show_wizard_button'] = True
        extra_context['show_import_button'] = True
        return super().changelist_view(request, extra_context=extra_context)
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Agregar botón de importación de datos y paginación en el formulario de edición"""
        extra_context = extra_context or {}
        extra_context['show_import_datos_button'] = True
        extra_context['indicador_id'] = object_id
        
        # Calcular información de paginación para datos
        try:
            indicador = Indicador.objects.get(id=object_id)
            total_datos = indicador.datos.count()
            per_page = 10
            total_pages = max(1, (total_datos + per_page - 1) // per_page)  # Mínimo 1 página
            
            # Obtener página actual
            current_page = request.GET.get('datos_page', 1)
            try:
                current_page = int(current_page)
            except (ValueError, TypeError):
                current_page = 1
            
            # Asegurar que la página esté en rango válido
            if current_page < 1:
                current_page = 1
            elif current_page > total_pages:
                current_page = total_pages
            
            pagination_data = {
                'current_page': current_page,
                'total_pages': total_pages,
                'total_datos': total_datos,
                'per_page': per_page,
                'has_previous': current_page > 1,
                'has_next': current_page < total_pages,
                'previous_page': current_page - 1,
                'next_page': current_page + 1,
            }
            
            # Debug: Imprimir en consola
            print(f"DEBUG Paginación: {pagination_data}")
            
            extra_context['datos_pagination'] = pagination_data
        except Indicador.DoesNotExist:
            print(f"DEBUG: Indicador {object_id} no encontrado")
            pass
        except Exception as e:
            print(f"DEBUG: Error en paginación: {e}")
            pass
        
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        """Interceptar guardado para registrar cambios manuales en audit trail."""
        from indicadores.utils_wizard import crear_registro_cambio

        # Guardar snapshot previo si es edición
        snapshot_previo = {}
        if change and obj.pk:
            try:
                old = Indicador.objects.get(pk=obj.pk)
                campos_track = [
                    'nombre', 'codigo_indicador', 'sigla', 'subtema_id',
                    'fuente_datos', 'entidad_responsable',
                    'frecuencia_difusion', 'unidad_medida', 'objetivo', 'formula_ficha',
                    'descripcion_indicador', 'comentarios_adicionales',
                    'conjunto_datos_id', 'organismo_responsable_id',
                    'referencias', 'equipo_responsable_id',
                    'nombre_responsable_validacion', 'cargo_responsable_validacion',
                    'correo_responsable_validacion', 'celular_responsable_validacion',
                ]
                for campo in campos_track:
                    snapshot_previo[campo] = str(getattr(old, campo, '') or '')
            except Exception:
                pass

        super().save_model(request, obj, form, change)

        # Crear registro de cambio
        if change:
            # Calcular diff simple
            diff = {}
            for campo, valor_antes in snapshot_previo.items():
                valor_despues = str(getattr(obj, campo, '') or '')
                if valor_antes != valor_despues:
                    diff[campo] = [valor_antes, valor_despues]

            tipo = 'cambio_metadatos' if diff else 'actualizacion_manual_admin'
            crear_registro_cambio(
                indicador=obj,
                usuario=request.user if request.user.is_authenticated else None,
                tipo_evento=tipo,
                diff_json=diff,
                snapshot_metadatos=snapshot_previo if diff else {}
            )

    def delete_model(self, request, obj):
        """Interceptar eliminación para registrar en audit trail antes de borrar."""
        from indicadores.utils_wizard import crear_registro_cambio
        try:
            crear_registro_cambio(
                indicador=obj,
                usuario=request.user if request.user.is_authenticated else None,
                tipo_evento='eliminacion_datos',
                filas_afectadas=obj.datos.count()
            )
        except Exception:
            pass
        super().delete_model(request, obj)

    def procesar_conjunto_datos_button(self, obj):
        """Botón para procesar conjunto_datos con diagnóstico y logs en tiempo real"""
        from django.urls import reverse
        if obj.id and obj.conjunto_datos:
            # Verificar si tiene regla de extracción
            tiene_regla = ReglaExtraccion.objects.filter(indicador=obj).exists()
            
            if tiene_regla:
                # Verde: Todo listo para procesar con diagnóstico
                url = reverse('admin:indicador_diagnostico_procesamiento', args=[obj.id])
                return format_html(
                    '<a class="button" href="{}" style="background: #4caf50; color: white; padding: 5px 10px; border-radius: 4px;">'
                    '🔄 Procesar conjunto_datos</a>',
                    url
                )
            else:
                # Naranja: Falta configuración
                return format_html(
                    '<span style="background: #ff9800; color: white; padding: 5px 10px; border-radius: 4px;" '
                    'title="Debe crear una Regla de Extracción primero">'
                    '⚠️ Falta Regla</span>'
                )
        elif obj.id:
            # Gris: Sin conjunto_datos
            return format_html(
                '<span style="background: #9e9e9e; color: white; padding: 5px 10px; border-radius: 4px;" '
                'title="Este indicador no tiene conjunto_datos asociado">'
                '📂 Sin conjunto_datos</span>'
            )
        return ""
    procesar_conjunto_datos_button.short_description = 'Procesar'
    procesar_conjunto_datos_button.allow_tags = True
    
    def actualizar_desagregaciones_button(self, obj):
        from django.urls import reverse
        if obj.id:
            url = reverse('admin:indicador_actualizar_desagregaciones', args=[obj.id])
            return format_html('<a class="button" href="{}">Actualizar Desagregaciones</a>', url)
        return ""
        
    actualizar_desagregaciones_button.short_description = 'Actualizar Desagregaciones'
    actualizar_desagregaciones_button.allow_tags = True
    
    def descargar_conjunto_datos_button(self, obj):
        from django.urls import reverse
        if obj.id and hasattr(obj, 'conjunto_datos') and obj.conjunto_datos and obj.conjunto_datos.archivo_csv:
            url = reverse('admin:indicador_descargar_conjunto_datos', args=[obj.id])
            return format_html('<a class="button" href="{}">Descargar conjunto_datos</a>', url)
        return ""
    descargar_conjunto_datos_button.short_description = 'conjunto_datos'
    
    def descargar_csv_button(self, obj):
        from django.urls import reverse
        if obj.id:
            url = reverse('admin:indicador_descargar_csv', args=[obj.id])
            return format_html('<a class="button" href="{}">Descargar CSV</a>', url)
        return ""
    descargar_csv_button.short_description = 'Datos CSV'
    
    def validar_datos_button(self, obj):
        from django.urls import reverse
        if obj.id:
            url = reverse('admin:indicador_validar_datos', args=[obj.id])
            return format_html('<a class="button" href="{}">🔍 Validar Datos</a>', url)
        return ""
    validar_datos_button.short_description = 'Validaciones'
    validar_datos_button.allow_tags = True
    
    def importar_datos_button(self, obj):
        from django.urls import reverse
        if obj.id:
            url = reverse('admin:indicador_importar_datos', args=[obj.id])
            return format_html('<a class="button" href="{}">📥 Importar Datos CSV</a>', url)
        return ""
    importar_datos_button.short_description = 'Importar Datos'
    importar_datos_button.allow_tags = True
    
    def get_urls(self):
        from .views_import import importar_indicadores
        from .views_recoleccion import wizard_admin_unificado
        urls = super().get_urls()
        custom_urls = [
            path('wizard/', self.admin_site.admin_view(wizard_admin_unificado), name='wizard_admin_unificado'),
            path('importar/', self.admin_site.admin_view(importar_indicadores), name='importar_indicadores'),
            # NUEVO: Ruta unificada para diagnóstico y procesamiento (igual que ReglaExtraccion)
            path('diagnostico-procesamiento/<int:indicador_id>/', self.admin_site.admin_view(self.diagnostico_y_procesamiento), name='indicador_diagnostico_procesamiento'),
            # DEPRECADO: Mantener por compatibilidad pero redirigir al nuevo flujo
            path('procesar-conjunto_datos/<int:indicador_id>/', self.admin_site.admin_view(self.procesar_conjunto_datos_redirect), name='indicador_procesar_conjunto_datos'),
            path('descargar-conjunto_datos/<int:indicador_id>/', self.admin_site.admin_view(self.descargar_conjunto_datos), name='indicador_descargar_conjunto_datos'),
            path('descargar-csv/<int:indicador_id>/', self.admin_site.admin_view(self.descargar_csv), name='indicador_descargar_csv'),
            path('importar-datos/<int:indicador_id>/', self.admin_site.admin_view(self.importar_datos_csv), name='indicador_importar_datos'),
            path('actualizar-desagregaciones/<int:indicador_id>/', self.admin_site.admin_view(self.actualizar_desagregaciones), name='indicador_actualizar_desagregaciones'),
            path('validar-datos/<int:indicador_id>/', self.admin_site.admin_view(self.validar_datos), name='indicador_validar_datos'),
        ]
        return custom_urls + urls
    
    def procesar_conjunto_datos_redirect(self, request, indicador_id):
        """Redirige al nuevo flujo unificado (mantener por compatibilidad)"""
        from django.urls import reverse
        messages.info(request, '🔄 Redirigiendo al flujo de procesamiento con diagnóstico...')
        return HttpResponseRedirect(reverse('admin:indicador_diagnostico_procesamiento', args=[indicador_id]))
    
    def diagnostico_y_procesamiento(self, request, indicador_id):
        """
        Vista unificada para diagnóstico y procesamiento de conjunto_datos.
        Flujo idéntico a ReglaExtraccionAdmin.procesar_datos():
        1. GET: Ejecutar diagnóstico y mostrar resultado
        2. Pedir confirmación al usuario
        3. POST: Crear ProcesoExtraccion y lanzar en background
        4. Redirigir a visor de logs en tiempo real
        """
        from django.http import HttpResponse, HttpResponseRedirect
        from django.template.response import TemplateResponse
        from django.urls import reverse
        import subprocess
        import sys
        import os
        
        try:
            indicador = Indicador.objects.get(id=indicador_id)
            
            # Verificar que tenga conjunto_datos
            if not indicador.conjunto_datos:
                messages.error(request, '❌ El indicador no tiene conjunto_datos asociado')
                return HttpResponseRedirect('../../')
            
            # Verificar que exista regla de extracción
            try:
                regla = ReglaExtraccion.objects.get(indicador=indicador)
            except ReglaExtraccion.DoesNotExist:
                messages.error(
                    request,
                    '❌ No existe una Regla de Extracción para este indicador. '
                    'Créala primero desde el menú "Reglas de Extracción".'
                )
                return HttpResponseRedirect('../../')
            
            # Ejecutar comando de diagnóstico
            manage_py_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'manage.py'
            )
            cmd = [
                sys.executable,
                manage_py_path,
                'diagnosticar_conjunto_datos',
                '--indicador-id',
                str(indicador.id)
            ]
            
            # Ejecutar el comando y capturar la salida
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()
            
            # Combinar la salida estándar y de error
            diagnostic_output = stdout + stderr
            
            # Si es una solicitud POST, significa que el usuario confirmó continuar
            if request.method == 'POST':
                # Crear proceso y lanzar en background, luego redirigir a visor en vivo
                from .background import lanzar_procesamiento_en_background
                
                proceso = ProcesoExtraccion.objects.create(
                    indicador=indicador,
                    regla=regla,
                    estado='pendiente'
                )
                
                lanzar_procesamiento_en_background(proceso.id)
                
                messages.info(
                    request,
                    f'✅ Proceso #{proceso.id} iniciado para {indicador.nombre}. '
                    f'Será redirigido al visor en vivo.'
                )
                
                return HttpResponseRedirect(
                    reverse('indicadores:proceso_en_vivo', args=[proceso.id])
                )
            
            # Si es una solicitud GET, mostrar el diagnóstico y pedir confirmación
            context = {
                'title': f'Diagnóstico para {indicador.nombre}',
                'diagnostic_output': diagnostic_output,
                'indicador': indicador,
                'regla': regla,
                'opts': self.model._meta,
                'original': indicador,
                'has_view_permission': True,
                'has_change_permission': True,
            }
            
            return TemplateResponse(
                request,
                'admin/diagnostic_confirmation.html',
                context
            )
            
        except Indicador.DoesNotExist:
            messages.error(request, 'Indicador no encontrado')
            return HttpResponseRedirect('../../')
        except Exception as e:
            messages.error(request, f'Error al ejecutar diagnóstico: {str(e)}')
            return HttpResponseRedirect('../../')
    
    def descargar_conjunto_datos(self, request, indicador_id):
        try:
            indicador = Indicador.objects.get(id=indicador_id)
            
            # Verificar que el indicador tenga conjunto_datos asociado
            if not hasattr(indicador, 'conjunto_datos') or not indicador.conjunto_datos:
                messages.error(request, f'El indicador {indicador.nombre} no tiene conjunto_datos asociado')
                return HttpResponseRedirect('../')
            
            # Verificar que el conjunto_datos tenga archivo CSV
            if not indicador.conjunto_datos.archivo_csv:
                messages.error(request, f'El conjunto_datos {indicador.conjunto_datos.nombre} no tiene archivo CSV')
                return HttpResponseRedirect('../')
            
            # Crear la respuesta HTTP para descargar el archivo
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            filename = f"{indicador.nombre}_conjunto_datos.csv"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            # Leer el archivo de conjunto_datos y enviarlo como respuesta
            with open(indicador.conjunto_datos.archivo_csv.path, 'rb') as f:
                response.write(f.read())
            
            messages.success(request, f'conjunto_datos descargado exitosamente para {indicador.nombre}')
            return response
            
        except Indicador.DoesNotExist:
            messages.error(request, 'Indicador no encontrado')
            return HttpResponseRedirect('../')
        except FileNotFoundError:
            messages.error(request, 'Archivo de conjunto_datos no encontrado en el sistema')
            return HttpResponseRedirect('../')
        except Exception as e:
            messages.error(request, f'Error al descargar conjunto_datos: {str(e)}')
            return HttpResponseRedirect('../')
    
    def descargar_csv(self, request, indicador_id):
        try:
            indicador = Indicador.objects.get(id=indicador_id)
            
            # Crear la respuesta HTTP con el tipo de contenido CSV
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{indicador.nombre}_datos.csv"'
            
            # Agregar BOM para UTF-8 (para Excel)
            response.write('\ufeff')
            
            writer = csv.writer(response)
            
            # Escribir encabezados
            headers = [
                'Indicador',
                'Dominio', 
                'Tema',
                'Subtema',
                'Año',
                'Valor',
                'Desagregaciones Geográficas',
                'Desagregaciones Temáticas'
            ]
            writer.writerow(headers)
            
            # Obtener todos los datos del indicador con desagregaciones
            datos = Dato.objects.filter(indicador=indicador).select_related(
                'indicador__subtema__tema__dominio'
            ).prefetch_related(
                'desagregaciones_geograficas',
                'desagregaciones_tematicas'
            ).order_by('fecha_dato')
            
            # Escribir datos
            for dato in datos:
                # Obtener desagregaciones como texto
                desag_geo = ', '.join([d.nombre for d in dato.desagregaciones_geograficas.all()])
                desag_tem = ', '.join([d.nombre for d in dato.desagregaciones_tematicas.all()])
                
                row = [
                    indicador.nombre,
                    indicador.subtema.tema.dominio.nombre,
                    indicador.subtema.tema.nombre,
                    indicador.subtema.nombre,
                    dato.fecha_dato.year if dato.fecha_dato else '',
                    dato.valor_dato,
                    desag_geo,
                    desag_tem
                ]
                writer.writerow(row)
            
            messages.success(request, f'CSV descargado exitosamente para {indicador.nombre}')
            return response
            
        except Indicador.DoesNotExist:
            messages.error(request, 'Indicador no encontrado')
            return HttpResponseRedirect('../')
        except Exception as e:
            messages.error(request, f'Error al generar CSV: {str(e)}')
            return HttpResponseRedirect('../')
    
    def importar_datos_csv(self, request, indicador_id):
        """
        Vista para importar datos desde un archivo CSV para un indicador específico.
        Formato esperado del CSV:
        - fecha_dato (YYYY-MM-DD o YYYY)
        - valor_dato (numérico)
        - desagregaciones_geograficas (opcional, nombres separados por coma)
        - desagregaciones_tematicas (opcional, nombres separados por coma)
        """
        import pandas as pd
        import io
        from datetime import datetime
        
        indicador = get_object_or_404(Indicador, id=indicador_id)
        
        if request.method == 'POST':
            if 'archivo_csv' not in request.FILES:
                messages.error(request, 'No se proporcionó ningún archivo CSV')
                return HttpResponseRedirect(request.path)
            
            archivo_csv = request.FILES['archivo_csv']
            eliminar_existentes = request.POST.get('eliminar_existentes') == 'on'
            
            try:
                # Leer CSV
                df = pd.read_csv(archivo_csv)
                
                # Validar columnas requeridas
                columnas_requeridas = ['fecha_dato', 'valor_dato']
                columnas_faltantes = [col for col in columnas_requeridas if col not in df.columns]
                
                if columnas_faltantes:
                    messages.error(request, f'Faltan columnas requeridas: {", ".join(columnas_faltantes)}')
                    return HttpResponseRedirect(request.path)
                
                # Procesar importación
                with transaction.atomic():
                    # Eliminar datos existentes si se solicita
                    if eliminar_existentes:
                        count = Dato.objects.filter(indicador=indicador).delete()[0]
                        messages.info(request, f'🗑️ Eliminados {count} datos existentes')
                    
                    creados = 0
                    errores = 0
                    log = []
                    
                    for index, row in df.iterrows():
                        try:
                            # Parsear fecha (año int/float/string o fecha completa)
                            from .wizard_admin_unificado import _parsear_fecha_dato
                            fecha_dato = _parsear_fecha_dato(row['fecha_dato'])
                            if fecha_dato is None:
                                raise ValueError(f"Fecha no interpretable: {row['fecha_dato']!r}")
                            
                            # Crear dato
                            dato = Dato.objects.create(
                                indicador=indicador,
                                fecha_dato=fecha_dato,
                                valor_dato=float(row['valor_dato'])
                            )
                            
                            # Procesar desagregaciones geográficas
                            if 'desagregaciones_geograficas' in row and pd.notna(row['desagregaciones_geograficas']):
                                nombres = [n.strip() for n in str(row['desagregaciones_geograficas']).split(',')]
                                for nombre in nombres:
                                    desag = Desagregacion.objects.filter(nombre__iexact=nombre).first()
                                    if desag:
                                        dato.desagregaciones_geograficas.add(desag)
                            
                            # Procesar desagregaciones temáticas
                            if 'desagregaciones_tematicas' in row and pd.notna(row['desagregaciones_tematicas']):
                                nombres = [n.strip() for n in str(row['desagregaciones_tematicas']).split(',')]
                                for nombre in nombres:
                                    desag = Desagregacion.objects.filter(nombre__iexact=nombre).first()
                                    if desag:
                                        dato.desagregaciones_tematicas.add(desag)
                            
                            creados += 1
                            log.append(f'✅ Fila {index+2}: Creado dato para {fecha_dato}')
                            
                        except Exception as e:
                            errores += 1
                            log.append(f'❌ Fila {index+2}: Error - {str(e)}')
                    
                    # Mostrar resultados
                    if errores > 0:
                        messages.warning(
                            request,
                            f'Importación completada con errores. Creados: {creados}, Errores: {errores}'
                        )
                    else:
                        messages.success(
                            request,
                            f'✅ Importación exitosa! Creados: {creados} datos'
                        )
                    
                    # Guardar log en sesión
                    request.session['import_log'] = log[:100]  # Limitar a 100 líneas
                
                return HttpResponseRedirect(f'../../{indicador_id}/change/')
                
            except Exception as e:
                messages.error(request, f'Error al procesar el archivo: {str(e)}')
                return HttpResponseRedirect(request.path)
        
        # GET: Mostrar formulario
        context = {
            'indicador': indicador,
            'title': f'Importar Datos CSV para: {indicador.nombre}',
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
        }
        
        return render(request, 'admin/importar_datos_indicador.html', context)
    
    def actualizar_desagregaciones(self, request, indicador_id):
        """
        Actualiza las desagregaciones de todos los datos Y GRÁFICOS de un indicador
        basándose en el tipo actual de sus dominios de desagregación.
        """
        try:
            indicador = Indicador.objects.get(id=indicador_id)
            datos_actualizados = 0
            series_actualizadas = 0
            errores = 0
            
            with transaction.atomic():
                # ========== ACTUALIZAR DATOS (código existente) ==========
                for dato in datos:
                    try:
                        # Obtener todas las desagregaciones actuales del dato
                        desag_geograficas_actuales = list(dato.desagregaciones_geograficas.all())
                        desag_tematicas_actuales = list(dato.desagregaciones_tematicas.all())
                        
                        # Listas para las nuevas asignaciones
                        nuevas_geograficas = []
                        nuevas_tematicas = []
                        
                        # Procesar desagregaciones geográficas actuales
                        for desag in desag_geograficas_actuales:
                            if desag.dominio.tipo == 'geografica':
                                nuevas_geograficas.append(desag)
                            elif desag.dominio.tipo == 'tematica':
                                nuevas_tematicas.append(desag)
                        
                        # Procesar desagregaciones temáticas actuales
                        for desag in desag_tematicas_actuales:
                            if desag.dominio.tipo == 'tematica':
                                nuevas_tematicas.append(desag)
                            elif desag.dominio.tipo == 'geografica':
                                nuevas_geograficas.append(desag)
                        
                        # Actualizar las relaciones M2M
                        dato.desagregaciones_geograficas.set(nuevas_geograficas)
                        dato.desagregaciones_tematicas.set(nuevas_tematicas)
                        
                        datos_actualizados += 1
                        
                    except Exception as e:
                        errores += 1
                        print(f"Error procesando dato {dato.id}: {str(e)}")
                
                # ========== ACTUALIZAR GRÁFICOS Y SERIES (NUEVO) ==========
                graficos = Grafico.objects.filter(indicador=indicador).prefetch_related('series')
                
                for grafico in graficos:

                    desag_geo_actuales = list(grafico.desagregaciones_geograficas_predeterminadas.all())
                    desag_tem_actuales = list(grafico.desagregaciones_tematicas_predeterminadas.all())
                    
                    nuevas_geo = [d for d in desag_geo_actuales if d.dominio.tipo == 'geografica']
                    nuevas_geo += [d for d in desag_tem_actuales if d.dominio.tipo == 'geografica']
                    
                    nuevas_tem = [d for d in desag_tem_actuales if d.dominio.tipo == 'tematica']
                    nuevas_tem += [d for d in desag_geo_actuales if d.dominio.tipo == 'tematica']
                    
                    grafico.desagregaciones_geograficas_predeterminadas.set(nuevas_geo)
                    grafico.desagregaciones_tematicas_predeterminadas.set(nuevas_tem)

                    for serie in grafico.series.all():
                        try:
                            cambio_realizado = False
                            
                            # Revisar desagregacion_geografica
                            if serie.desagregacion_geografica:
                                if serie.desagregacion_geografica.dominio.tipo != 'geografica':
                                    # Está mal clasificada → Mover a desagregacion_tematica
                                    serie.desagregacion_tematica = serie.desagregacion_geografica
                                    serie.desagregacion_geografica = None
                                    cambio_realizado = True
                            
                            # Revisar desagregacion_tematica
                            if serie.desagregacion_tematica:
                                if serie.desagregacion_tematica.dominio.tipo != 'tematica':
                                    # Está mal clasificada → Mover a desagregacion_geografica
                                    serie.desagregacion_geografica = serie.desagregacion_tematica
                                    serie.desagregacion_tematica = None
                                    cambio_realizado = True
                            
                            if cambio_realizado:
                                serie.save()
                                # Sincronizar el M2M con los FKs corregidos
                                ids = [d for d in (serie.desagregacion_geografica_id,
                                                   serie.desagregacion_tematica_id) if d]
                                serie.desagregaciones.set(ids)
                                series_actualizadas += 1
                                
                        except Exception as e:
                            errores += 1
                            print(f"Error procesando serie {serie.id}: {str(e)}")
            
            # Mensaje de éxito actualizado
            messages.success(
                request, 
                f'Actualización completada para {indicador.nombre}. '
                f'Datos actualizados: {datos_actualizados}, '
                f'Series de gráficos actualizadas: {series_actualizadas}, '
                f'Errores: {errores}'
            )
            
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        
        return HttpResponseRedirect('../')

    def validar_datos(self, request, indicador_id):
        """Vista para ejecutar validaciones automáticas de datos"""
        indicador = get_object_or_404(Indicador, id=indicador_id)
        
        if request.method == 'POST':
            # Ejecutar validaciones
            try:
                validation_data = run_automatic_validations(indicador_id)
                
                # Extraer los resultados del diccionario retornado
                results = validation_data['results']
                total_validations = validation_data['total_validations']
                errors = validation_data['errors']
                warnings = validation_data['warnings']
                success = total_validations - errors - warnings
                
                if errors > 0:
                    messages.error(request, f'Validación completada con {errors} errores, {warnings} advertencias y {success} validaciones exitosas.')
                elif warnings > 0:
                    messages.warning(request, f'Validación completada con {warnings} advertencias y {success} validaciones exitosas.')
                else:
                    messages.success(request, f'Todas las {total_validations} validaciones fueron exitosas.')
                
                # Renderizar página de resultados
                context = {
                    'indicador': indicador,
                    'results': results,
                    'total_validations': total_validations,
                    'errors': errors,
                    'warnings': warnings,
                    'success': success,
                    'title': f'Resultados de Validación - {indicador.nombre}',
                    'opts': self.model._meta,
                    'has_view_permission': True,
                }
                return render(request, 'admin/indicadores/validation_results.html', context)
                
            except Exception as e:
                messages.error(request, f'Error ejecutando validaciones: {str(e)}')
                return HttpResponseRedirect(reverse('admin:indicadores_indicador_changelist'))
        
        # GET request - mostrar página de confirmación
        context = {
            'indicador': indicador,
            'title': f'Validar Datos - {indicador.nombre}',
            'opts': self.model._meta,
            'has_view_permission': True,
        }
        return render(request, 'admin/indicadores/validation_confirm.html', context)
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        Sobrescribir para forzar el uso de Textarea en TODOS los campos de texto
        en lugar de CKEditor
        """
        from django.db import models
        from django_ckeditor_5.fields import CKEditor5Field
        
        # TODOS los campos de texto deben usar Textarea simple (sin CKEditor)
        if isinstance(db_field, (models.TextField, CKEditor5Field)):
            # Remover cualquier widget que pueda venir en kwargs
            kwargs.pop('widget', None)
            # Forzar el widget Textarea simple
            return forms.CharField(
                widget=forms.Textarea(attrs={'rows': 4, 'cols': 80}),
                required=not db_field.blank,
                help_text=db_field.help_text,
                label=db_field.verbose_name or db_field.name.replace('_', ' ').title()
            )
        
        # Para el resto de campos, usar el comportamiento por defecto
        return super().formfield_for_dbfield(db_field, request, **kwargs)

admin.site.register(Indicador, IndicadorAdmin)
admin.site.register(DominioDesagregacion, DominioDesagregacionAdmin)
admin.site.register(Desagregacion, DesagregacionAdmin)
admin.site.register(NivelGeografico, NivelGeograficoAdmin)


class CatalogoDominioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'dominio', 'extension', 'activo', 'orden', 'fecha_actualizacion')
    list_filter = ('dominio', 'activo')
    search_fields = ('nombre', 'descripcion', 'dominio__nombre')
    autocomplete_fields = ('dominio',)
    list_editable = ('activo', 'orden')


admin.site.register(CatalogoDominio, CatalogoDominioAdmin)


class IndicadoresEnlazadosInline(admin.TabularInline):
    model = Indicador
    fk_name = 'catalogo_consulta'
    fields = ('nombre', 'subtema', 'activo')
    readonly_fields = ('nombre', 'subtema', 'activo')
    extra = 0
    can_delete = False
    verbose_name = "Indicador enlazado"
    verbose_name_plural = "Indicadores enlazados (muestran este cuadro)"

    def has_add_permission(self, request, obj=None):
        return False


class CatalogoConsultaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'dominio', 'tipo_consulta', 'total_filas', 'n_indicadores', 'activo', 'orden', 'fecha_actualizacion')
    list_filter = ('dominio', 'tipo_consulta', 'activo')
    search_fields = ('nombre', 'descripcion')
    list_editable = ('activo', 'orden')
    inlines = (IndicadoresEnlazadosInline,)

    def n_indicadores(self, obj):
        return obj.indicadores_enlazados.count()
    n_indicadores.short_description = "Indicadores enlazados"


admin.site.register(CatalogoConsulta, CatalogoConsultaAdmin)


# Umbral de series renderizables en el admin inline: cada fila renderiza un
# SelectMultiple con todas las desagregaciones del indicador como opciones.
# Con miles de series el HTML pesa gigabytes y el request nunca termina.
MAX_SERIES_INLINE_ADMIN = 100


class GraficoSerieInline(admin.TabularInline):
    model = GraficoSerie
    extra = 1
    max_num = MAX_SERIES_INLINE_ADMIN
    fields = ('desagregaciones', 'nombre_personalizado', 'color', 'orden')
    form = GraficoSerieForm

    def has_add_permission(self, request, obj=None):
        if obj and obj.series.count() > MAX_SERIES_INLINE_ADMIN:
            return False
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        # Sin permiso de cambio para el inline cuando hay demasiadas series:
        # solo se renderizan max_num filas y un POST las sobreescribiría.
        # Con change=False el admin renderiza el inline en modo lectura…
        # pero mejor ocultarlo por completo vía get_formsets (más abajo en
        # GraficoAdmin.get_inlines). Aquí no se permite añadir/cambiar.
        if obj and obj.series.count() > MAX_SERIES_INLINE_ADMIN:
            return False
        return super().has_change_permission(request, obj)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # 'desagregaciones': una serie = un filtro por dominio. Se limita a los
        # dominios del indicador del gráfico y se etiqueta 'Dominio › valor'.
        if db_field.name == 'desagregaciones':
            grafico_id = None
            if hasattr(request, 'resolver_match') and request.resolver_match:
                grafico_id = request.resolver_match.kwargs.get('object_id')

            qs = Desagregacion.objects.select_related('dominio')
            if grafico_id:
                grafico = Grafico.objects.filter(pk=grafico_id).select_related('indicador').first()
                if grafico:
                    dominios = list(grafico.indicador.dominios_desagregacion_geografica.all()) \
                             + list(grafico.indicador.dominios_desagregacion_tematica.all())
                    qs = qs.filter(dominio__in=dominios)
            qs = qs.order_by('dominio__nombre', 'nombre').distinct()

            return DesagregacionPorDominioMultipleField(
                queryset=qs,
                required=False,
                label='Desagregaciones (una por dominio)',
                widget=forms.SelectMultiple(attrs={'size': 10, 'style': 'min-width: 280px;'}),
            )
        return super().formfield_for_manytomany(db_field, request, **kwargs)



class GraficoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'indicador', 'tipo_grafico', 'activo', 'orden', 'vista_previa_button')
    list_filter = ('tipo_grafico', 'activo', 'indicador')
    search_fields = ('nombre', 'indicador__nombre')
    list_editable = ('orden', 'activo')
    autocomplete_fields = ['indicador']
    inlines = [GraficoSerieInline]
    readonly_fields = ('preview_grafico_widget', 'series_count_aviso')

    def get_inlines(self, request, obj=None):
        # Gráficos con demasiadas series: el inline generaría un SelectMultiple
        # por serie × todas las desagregaciones del indicador → HTML de GB.
        # Se oculta el inline y se informa: la metadata del gráfico sigue editable.
        if obj and obj.pk and obj.series.count() > MAX_SERIES_INLINE_ADMIN:
            return []
        return super().get_inlines(request, obj)

    def series_count_aviso(self, obj):
        if obj and obj.pk:
            n = obj.series.count()
            if n > MAX_SERIES_INLINE_ADMIN:
                return format_html(
                    '<div style="background:#fff3e0; border-left:4px solid #ff9800; padding:12px; '
                    'border-radius:4px; max-width:720px;">'
                    '<strong>⚠️ {} series</strong> — el editor inline de series se desactivó por volumen. '
                    'Las series no se modifican ni se pierden al guardar; aquí solo puedes editar la '
                    'configuración del gráfico (tipo, ejes, visual…).'
                    '</div>', n)
        return ''
    series_count_aviso.short_description = 'Series'
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('series_count_aviso', 'nombre', 'indicador', 'descripcion', 'tipo_grafico', 'activo', 'orden')
        }),
        ('Vista Previa', {
            'fields': ('preview_grafico_widget',),
            'classes': ('collapse',),
            'description': 'Vista previa del gráfico con datos reales. Los cambios se reflejarán al guardar.'
        }),
        ('Configuración Visual', {
            'fields': (
                'titulo', 'subtitulo', 'eje_x_titulo', 'eje_y_titulo',
                'mostrar_eje_y2', 'eje_y2_titulo',
                'mostrar_leyenda', 'posicion_leyenda',
                'mostrar_cuadricula', 'mostrar_valores', 'mostrar_linea_tendencia'
            ),
            'classes': ('collapse',)
        }),
        ('Dimensiones y Márgenes', {
            'fields': (
                'ancho_completo', 'altura_grafico',
                'margen_derecho', 'margen_inferior'
            ),
            'classes': ('collapse',)
        }),
        ('Configuración de Ejes', {
            'fields': (
                'begin_at_zero',
                'rango_personalizado_min', 'rango_personalizado_max',
                'mostrar_todas_etiquetas_x'
            ),
            'classes': ('collapse',)
        }),
        ('Valores Predeterminados', {
            'fields': (
                'rango_anios_min', 'rango_anios_max',
                'desagregaciones_geograficas_predeterminadas',
                'desagregaciones_tematicas_predeterminadas'
            ),
            'classes': ('collapse',)
        }),
    )
    
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # Predeterminadas: limitar a las desagregaciones de los dominios del
        # indicador y etiquetarlas 'Dominio › valor' para reflejar la
        # estructura por dominios que ve el usuario en el portal.
        if db_field.name in ('desagregaciones_geograficas_predeterminadas',
                             'desagregaciones_tematicas_predeterminadas'):
            tipo = 'geografica' if 'geograficas' in db_field.name else 'tematica'
            qs = Desagregacion.objects.select_related('dominio')

            grafico_id = None
            if hasattr(request, 'resolver_match') and request.resolver_match:
                grafico_id = request.resolver_match.kwargs.get('object_id')
            if grafico_id:
                grafico = Grafico.objects.filter(pk=grafico_id).select_related('indicador').first()
                if grafico:
                    attr = ('dominios_desagregacion_geografica' if tipo == 'geografica'
                            else 'dominios_desagregacion_tematica')
                    qs = qs.filter(dominio__in=getattr(grafico.indicador, attr).all())
            else:
                qs = qs.filter(dominio__tipo=tipo)
            qs = qs.order_by('dominio__nombre', 'nombre').distinct()

            return DesagregacionPorDominioMultipleField(
                queryset=qs,
                required=False,
                label=db_field.verbose_name.capitalize(),
                widget=forms.SelectMultiple(attrs={'size': 12}),
            )
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def vista_previa_button(self, obj):
        if obj.id:
            url = reverse('admin:grafico_vista_previa', args=[obj.id])
            return format_html(
                '<a class="button" href="{}" target="_blank">👁️ Vista Previa</a>',
                url
            )
        return "Guarda primero"
    vista_previa_button.short_description = 'Vista Previa'
    
    def preview_grafico_widget(self, obj):
        if not obj.id:
            return format_html(
                '<div style="background:#f0f8ff; padding:20px; border-left:4px solid #2196f3; border-radius:4px;"'
                ' class="text-center"<p style="color:#666; font-size:14px;">'
                '💡 <strong>Guarda el gráfico primero</strong> para ver la vista previa con datos reales.'
                '</p></div>'
            )
        
        series_count = obj.series.count()
        datos_count = obj.indicador.datos.count() if obj.indicador else 0

        # Volumen inmanejable: no lanzar el fetch (la respuesta sería de
        # cientos de MB y el browser/admin quedarían congelados).
        if series_count > MAX_SERIES_INLINE_ADMIN:
            html = f'''
            <div style="background:#f5f5f5; padding:20px; border-left:4px solid #9e9e9e; border-radius:4px;">
                <h3 style="margin:0 0 10px 0; color:#333;">📊 Estado del Gráfico</h3>
                <p style="margin:5px 0; color:#666;"><strong>Tipo:</strong> {obj.get_tipo_grafico_display()}</p>
                <p style="margin:5px 0; color:#666;"><strong>Series configuradas:</strong> {series_count}</p>
                <p style="margin:5px 0; color:#666;"><strong>Datos disponibles:</strong> {datos_count:,}</p>
                <p style="margin:8px 0 0; color:#555;">Vista previa no disponible para este volumen de series.</p>
                <a href="{reverse('admin:grafico_vista_previa', args=[obj.id])}" target="_blank"
                   style="display:inline-block; margin-top:10px; padding:8px 16px; background:#2196f3; color:white; text-decoration:none; border-radius:4px; font-size:13px;">
                    🔍 Abrir vista previa completa (puede tardar)
                </a>
            </div>
            '''
            return format_html(html)

        if series_count == 0:
            estado = 'error'
            mensaje_estado = '❌ Sin series configuradas'
            color_borde = '#f44336'
            bg_color = '#ffebee'
        elif datos_count == 0:
            estado = 'warning'
            mensaje_estado = '⚠️ Sin datos disponibles'
            color_borde = '#ff9800'
            bg_color = '#fff3e0'
        else:
            estado = 'ok'
            mensaje_estado = '✅ Gráfico listo'
            color_borde = '#4caf50'
            bg_color = '#e8f5e9'
        
        html = f'''
        <div style="background:{bg_color}; padding:20px; border-left:4px solid {color_borde}; border-radius:4px; margin-bottom:20px;">
            <div style="display:flex; justify-content:space-between; align-items:start; margin-bottom:15px;">
                <div>
                    <h3 style="margin:0 0 10px 0; color:#333;">📊 Estado del Gráfico</h3>
                    <p style="margin:5px 0; color:#666;"><strong>Tipo:</strong> {obj.get_tipo_grafico_display()}</p>
                    <p style="margin:5px 0; color:#666;"><strong>Series configuradas:</strong> {series_count}</p>
                    <p style="margin:5px 0; color:#666;"><strong>Datos disponibles:</strong> {datos_count:,}</p>
                    <p style="margin:5px 0;"><strong>{mensaje_estado}</strong></p>
                </div>
            </div>
        '''
        
        if series_count == 0:
            html += '''
                <div style="background:#fff; padding:15px; border-radius:4px; border:1px solid #ddd; margin-top:15px;">
                    <p style="color:#d32f2f; margin:0;">⚠️ <strong>Acción requerida:</strong> Agrega al menos una serie en la sección "Series de Gráficos" más abajo.</p>
                </div>
            '''
        elif datos_count == 0:
            html += '''
                <div style="background:#fff; padding:15px; border-radius:4px; border:1px solid #ddd; margin-top:15px;">
                    <p style="color:#f57c00; margin:0;">⚠️ <strong>Nota:</strong> El indicador no tiene datos procesados. Procesa el conjunto_datos desde el admin de Indicadores.</p>
                </div>
            '''
        else:
            # Mostrar preview del gráfico usando Plotly
            html += f'''
                <div style="background:#fff; padding:15px; border-radius:4px; border:1px solid #ddd; margin-top:15px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                        <h4 style="margin:0; color:#333;">Vista Previa (últimos 5 años)</h4>
                        <a href="{reverse('admin:grafico_vista_previa', args=[obj.id])}" target="_blank" 
                           style="padding:8px 16px; background:#2196f3; color:white; text-decoration:none; border-radius:4px; font-size:13px;">
                            🔍 Ver Completo
                        </a>
                    </div>
                    <div id="preview-grafico-{obj.id}" style="height:400px; width:100%;"></div>
                    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
                    <script>
                        fetch('/api/get_graficos/{obj.indicador.id}/')
                            .then(response => response.json())
                            .then(data => {{
                                const graficoData = data.find(g => g.id === {obj.id});
                                if (graficoData) {{
                                    const layout = {{
                                        ...graficoData.layout,
                                        height: 400,
                                        margin: {{ t: 40, b: 40, l: 50, r: 50 }}
                                    }};
                                    const config = {{
                                        responsive: true,
                                        displayModeBar: true,
                                        displaylogo: false,
                                        locale: 'es'
                                    }};
                                    Plotly.newPlot('preview-grafico-{obj.id}', graficoData.series, layout, config);
                                }}
                            }})
                            .catch(error => {{
                                document.getElementById('preview-grafico-{obj.id}').innerHTML = 
                                    '<div style="text-align:center; padding:40px; color:#f44336;">❌ Error al cargar vista previa: ' + error.message + '</div>';
                            }});
                    </script>
                </div>
            '''
        
        html += '</div>'
        return format_html(html)
    
    preview_grafico_widget.short_description = 'Vista Previa del Gráfico'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('vista-previa/<int:grafico_id>/', 
                 self.admin_site.admin_view(self.vista_previa_completa), 
                 name='grafico_vista_previa'),
        ]
        return custom_urls + urls
    
    def vista_previa_completa(self, request, grafico_id):
        """Vista completa del gráfico en página separada"""
        grafico = get_object_or_404(Grafico, id=grafico_id)
        
        context = {
            'title': f'Vista Previa: {grafico.nombre}',
            'grafico': grafico,
            'indicador': grafico.indicador,
            'site_header': 'Vista Previa de Gráfico',
        }
        
        return render(request, 'admin/grafico_preview.html', context)

admin.site.register(Grafico, GraficoAdmin)


@admin.register(PageVisit)
class PageVisitAdmin(admin.ModelAdmin):
    list_display = ('path', 'user', 'ip_address', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('path', 'ip_address', 'user_agent')
    readonly_fields = ('path', 'user', 'ip_address', 'user_agent', 'referer', 'timestamp')
    ordering = ('-timestamp',)
    date_hierarchy = 'timestamp'


# Personalización del Admin: títulos y encabezados
admin.site.site_header = "Módulo de Administración del Sistema Integrado de Información Estadística Distrital de Santiago de Cali"
admin.site.site_title = "SIIED Cali — Administración"
admin.site.index_title = "Panel de Administración"

@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('action_time', 'user', 'content_type', 'object_repr', 'action_flag', 'change_message')
    list_filter = ('action_time', 'user', 'content_type', 'action_flag')
    search_fields = ('object_repr', 'change_message')
    date_hierarchy = 'action_time'
    readonly_fields = ('action_time', 'user', 'content_type', 'object_id', 'object_repr', 'action_flag', 'change_message')


# Administración de Sistemas de Consulta
class SistemaInformacionInline(admin.TabularInline):
    model = SistemaInformacion
    extra = 0
    fields = ('nombre', 'url', 'tipo_enlace', 'abrir_nueva_ventana', 'activo', 'orden')
    readonly_fields = ('fecha_actualizacion',)


@admin.register(CategoriaInformacion)
class CategoriaInformacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'orden', 'activo', 'count_sistemas')
    list_filter = ('activo',)
    search_fields = ('nombre', 'descripcion')
    prepopulated_fields = {'slug': ('nombre',)}
    ordering = ('orden', 'nombre')
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'color':
            kwargs['widget'] = ColorWidget()
        return super().formfield_for_dbfield(db_field, request, **kwargs)
    
    def count_sistemas(self, obj):
        return obj.sistemas.count()
    count_sistemas.short_description = 'Sistemas activos'


@admin.register(SistemaInformacion)
class SistemaInformacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'tipo_enlace', 'url_preview', 'activo', 'orden')
    list_filter = ('categoria', 'tipo_enlace', 'activo', 'requiere_autenticacion')
    search_fields = ('nombre', 'descripcion', 'desarrollador')
    list_editable = ('orden', 'activo')
    
    fieldsets = (
        ('Información básica', {
            'fields': ('nombre', 'descripcion', 'categoria')
        }),
        ('Configuración del enlace', {
            'fields': ('tipo_enlace', 'url', 'abrir_nueva_ventana')
        }),
        ('Presentación', {
            'fields': ('icono', 'orden', 'activo')
        }),
        ('Metadatos', {
            'fields': ('desarrollador', 'version', 'requiere_autenticacion'),
            'classes': ('collapse',)
        })
    )
    
    def url_preview(self, obj):
        if obj.url:
            return f"{obj.url[:50]}..." if len(obj.url) > 50 else obj.url
        return "-"
    url_preview.short_description = 'URL'


# Administración de Proyectos de Información
class ProyectoInformacionInline(admin.TabularInline):
    model = ProyectoInformacion
    extra = 0
    fields = ('nombre', 'url', 'dependencia_responsable', 'estado', 'activo', 'orden')
    readonly_fields = ('fecha_actualizacion',)


@admin.register(CategoriaProyecto)
class CategoriaProyectoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'orden', 'activo', 'count_proyectos')
    list_filter = ('activo',)
    search_fields = ('nombre', 'descripcion')
    prepopulated_fields = {'slug': ('nombre',)}
    inlines = [ProyectoInformacionInline]
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'color':
            kwargs['widget'] = ColorWidget()
        return super().formfield_for_dbfield(db_field, request, **kwargs)
    
    def count_proyectos(self, obj):
        return obj.proyectos.count()
    count_proyectos.short_description = 'Proyectos activos'


@admin.register(ProyectoInformacion)
class ProyectoInformacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'dependencia_responsable', 'estado', 'url_preview', 'activo', 'orden')
    list_filter = ('categoria', 'estado', 'activo', 'dependencia_responsable')
    search_fields = ('nombre', 'descripcion', 'dependencia_responsable', 'objetivos')
    list_editable = ('orden', 'activo', 'estado')
    
    fieldsets = (
        ('Información básica', {
            'fields': ('nombre', 'descripcion', 'categoria', 'estado')
        }),
        ('Configuración del enlace', {
            'fields': ('tipo_enlace', 'url', 'abrir_nueva_ventana')
        }),
        ('Información institucional', {
            'fields': ('dependencia_responsable', 'contacto_email', 'contacto_telefono')
        }),
        ('Presentación', {
            'fields': ('icono', 'orden', 'activo')
        }),
        ('Detalles del proyecto', {
            'fields': ('objetivos', 'poblacion_objetivo', 'fecha_inicio'),
            'classes': ('collapse',)
        })
    )
    
    def url_preview(self, obj):
        if obj.url:
            return f"{obj.url[:50]}..." if len(obj.url) > 50 else obj.url
        return "-"
    url_preview.short_description = 'URL'


# Administración de Infraestructura de Información
class CategoriaInfraestructuraInline(admin.TabularInline):
    model = CategoriaInfraestructura
    extra = 0
    fields = ('nombre', 'slug', 'descripcion', 'icono', 'orden', 'activo')
    prepopulated_fields = {'slug': ('nombre',)}


class SubcategoriaInfraestructuraInline(admin.TabularInline):
    model = SubcategoriaInfraestructura
    extra = 0
    fields = ('nombre', 'slug', 'descripcion', 'icono', 'orden', 'activo')
    prepopulated_fields = {'slug': ('nombre',)}


class GrupoDocumentoInline(admin.TabularInline):
    model = GrupoDocumento
    extra = 0
    fields = ('nombre', 'slug', 'descripcion', 'icono', 'orden', 'activo')
    prepopulated_fields = {'slug': ('nombre',)}


class DocumentoInfraestructuraInline(admin.TabularInline):
    model = DocumentoInfraestructura
    extra = 0
    fields = ('nombre', 'slug', 'tipo_documento', 'estado', 'orden', 'activo')
    prepopulated_fields = {'slug': ('nombre',)}
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')




@admin.register(AreaInfraestructura)
class AreaInfraestructuraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'orden', 'activo', 'count_categorias')
    list_filter = ('activo',)
    search_fields = ('nombre', 'descripcion')
    prepopulated_fields = {'slug': ('nombre',)}
    ordering = ('orden', 'nombre')
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'color':
            kwargs['widget'] = ColorWidget()
        return super().formfield_for_dbfield(db_field, request, **kwargs)
    
    def count_categorias(self, obj):
        return obj.categorias.count()
    count_categorias.short_description = 'Categorías activas'


@admin.register(CategoriaInfraestructura)
class CategoriaInfraestructuraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'area', 'slug', 'orden', 'activo', 'count_subcategorias')
    list_filter = ('area', 'activo')
    search_fields = ('nombre', 'descripcion', 'area__nombre')
    prepopulated_fields = {'slug': ('nombre',)}
    inlines = [SubcategoriaInfraestructuraInline]
    
    def count_subcategorias(self, obj):
        return obj.subcategorias.filter(activo=True).count()
    count_subcategorias.short_description = 'Subcategorías activas'


@admin.register(SubcategoriaInfraestructura)
class SubcategoriaInfraestructuraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'slug', 'orden', 'activo', 'count_grupos')
    list_filter = ('categoria__area', 'categoria', 'activo')
    search_fields = ('nombre', 'descripcion', 'categoria__nombre')
    prepopulated_fields = {'slug': ('nombre',)}
    inlines = [GrupoDocumentoInline]
    
    def count_grupos(self, obj):
        return obj.grupos_documentos.filter(activo=True).count()
    count_grupos.short_description = 'Grupos activos'


@admin.register(GrupoDocumento)
class GrupoDocumentoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'subcategoria', 'slug', 'orden', 'activo', 'count_documentos')
    list_filter = ('subcategoria__categoria__area', 'subcategoria__categoria', 'subcategoria', 'activo')
    search_fields = ('nombre', 'descripcion', 'subcategoria__nombre')
    prepopulated_fields = {'slug': ('nombre',)}
    inlines = [DocumentoInfraestructuraInline]
    
    def count_documentos(self, obj):
        return obj.documentos.filter(activo=True).count()
    count_documentos.short_description = 'Documentos activos'


@admin.register(DocumentoInfraestructura)
class DocumentoInfraestructuraAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'grupo_documento', 'tipo_documento', 'estado', 'version', 'autor', 'fecha_actualizacion', 'activo', 'destacado', 'orden')
    list_filter = ('grupo_documento__subcategoria__categoria__area', 'grupo_documento__subcategoria__categoria', 'grupo_documento__subcategoria', 'tipo_documento', 'estado', 'activo', 'destacado')
    search_fields = ('nombre', 'descripcion', 'autor', 'palabras_clave', 'contenido')
    list_editable = ('estado', 'activo', 'destacado', 'orden')
    prepopulated_fields = {'slug': ('nombre',)}
    
    fieldsets = (
        ('Información básica', {
            'fields': ('nombre', 'slug', 'descripcion', 'grupo_documento', 'tipo_documento')
        }),
        ('Contenido', {
            'fields': ('contenido',),
            'classes': ('wide',)
        }),
        ('Estado y versión', {
            'fields': ('estado', 'version', 'destacado')
        }),
        ('Autoría y fechas', {
            'fields': ('autor', 'fecha_publicacion', 'fecha_revision')
        }),
        ('Archivos adjuntos', {
            'fields': ('archivo_pdf', 'archivo_word'),
            'classes': ('collapse',)
        }),
        ('Presentación', {
            'fields': ('icono', 'orden', 'activo')
        }),
        ('SEO y metadatos', {
            'fields': ('palabras_clave', 'resumen_ejecutivo'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    
    class Media:
        css = {
            'all': ('admin/css/ckeditor_custom.css',)
        }


# ============================================================================
# Administración de Productos Académicos
# ============================================================================

class SeccionPaperInline(admin.StackedInline):
    """Inline compacto para crear/editar metadatos básicos de secciones.
    El contenido pesado (CKEditor, gráficos) se edita en SeccionPaperAdmin."""
    model = SeccionPaper
    extra = 1
    ordering = ['numero_orden', 'subnumero']
    fields = ['numero_orden', 'subnumero', 'tipo_seccion', 'titulo', 'tipo_bloque']
    show_change_link = True
    classes = ['collapse']


@admin.register(ProductoAcademico)
class ProductoAcademicoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'organismo', 'autor', 'estado', 'es_producto_estadistico', 'fecha_publicacion', 'created_at')
    list_editable = ('estado',)
    list_filter = ('estado', 'es_producto_estadistico', 'area_tematica', 'organismo')
    search_fields = ('titulo', 'resumen', 'autor', 'palabras_clave')
    prepopulated_fields = {'slug': ('titulo',)}
    filter_horizontal = ('indicadores_derivados', 'temas_relacionados')
    inlines = [SeccionPaperInline]
    change_list_template = 'admin/indicadores/productoacademico/change_list.html'

    fieldsets = (
        ('Identificación', {
            'fields': ('titulo', 'slug', 'autor', 'institucion')
        }),
        ('Clasificación', {
            'fields': ('area_tematica', 'palabras_clave', 'resumen', 'temas_relacionados')
        }),
        ('Metadatos del producto estadístico', {
            'fields': ('es_producto_estadistico', 'logo', 'operacion', 'cobertura_geografica', 'periodo_referencia', 'diseno_conceptual'),
            'classes': ('collapse',),
            'description': 'Campos adicionales para productos con formato INEGI (tabs, metadatos, resultados integrados)'
        }),
        ('Vinculación de datos', {
            'fields': ('organismo', 'conjunto_datos_principal', 'indicadores_derivados')
        }),
        ('Publicación', {
            'fields': ('estado', 'fecha_publicacion')
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('manual/', self.admin_site.admin_view(self.manual_view), name='productoacademico_manual'),
        ]
        return custom_urls + urls

    def manual_view(self, request):
        return render(request, 'admin/indicadores/productoacademico/manual.html', {
            'title': 'Manual de Productos Académicos',
            'has_permission': self.has_view_permission(request),
        })


class ImagenSeccionInline(admin.TabularInline):
    model = ImagenSeccion
    extra = 1
    fields = ['tipo_uso', 'imagen', 'titulo', 'descripcion', 'orden']

class ArchivoSeccionInline(admin.TabularInline):
    model = ArchivoSeccion
    extra = 1
    fields = ['archivo', 'nombre', 'descripcion', 'icono', 'orden']

@admin.register(SeccionPaper)
class SeccionPaperAdmin(admin.ModelAdmin):
    """Admin independiente para edición completa de secciones con espacio total."""
    list_display = ('__str__', 'producto', 'tipo_seccion', 'tipo_bloque', 'numero_orden')
    list_filter = ('tipo_seccion', 'tipo_bloque', 'producto')
    search_fields = ('titulo', 'contenido', 'producto__titulo')
    list_editable = ('numero_orden',)
    autocomplete_fields = ['indicador_vinculado', 'producto', 'documento_vinculado', 'sistema_vinculado']
    filter_horizontal = ('publicaciones_relacionadas', 'indicadores_preseleccionados')
    inlines = [ImagenSeccionInline, ArchivoSeccionInline]

    fieldsets = (
        ('Identificación', {
            'fields': ('producto', 'tipo_seccion', 'numero_orden', 'subnumero', 'titulo')
        }),
        ('Contenido', {
            'fields': ('tipo_bloque', 'contenido')
        }),
        ('Recurso vinculado', {
            'fields': ('indicador_vinculado', 'conjunto_datos_vinculado', 'documento_vinculado', 'sistema_vinculado', 'publicaciones_relacionadas', 'configuracion_grafico'),
            'classes': ('collapse',),
            'description': ('Indicador: para gráficos, mapas, tablas dinámicas y fichas. '
                           'conjunto_datos: solo para tablas de conjunto_datos. '
                           'Documento: para metodologías, manuales y guías. '
                           'Sistema: para herramientas y visores. '
                           'Publicaciones: otros productos académicos relacionados. '
                           'Configuración: JSON con {tipo, anio_default, mostrar_desagregaciones, tipo_mapa}')
        }),
        ('Nuevos bloques', {
            'fields': ('indicadores_preseleccionados', 'video_url', 'acordeon_items'),
            'classes': ('collapse',),
            'description': ('Visor comparativo: seleccione indicadores previamente. '
                           'Video: URL de YouTube/Vimeo. '
                           'Acordeón: JSON [{"titulo": "...", "contenido": "..."}]. '
                           'Galería/Carrusel/Infografía/Descargas: use los inlines de Imágenes y Archivos.')
        }),
    )


# Administración de Aliados
@admin.register(Aliado)
class AliadoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'orden', 'fecha_inicio_alianza', 'fecha_fin_alianza', 'fecha_actualizacion')
    list_filter = ('activo', 'fecha_inicio_alianza', 'fecha_fin_alianza')
    search_fields = ('nombre', 'descripcion')
    list_editable = ('activo', 'orden')
    prepopulated_fields = {'slug': ('nombre',)}
    ordering = ('orden', 'nombre')
    
    fieldsets = (
        ('Información básica', {
            'fields': ('nombre', 'slug', 'logo_url', 'activo', 'orden')
        }),
        ('Descripción de la alianza', {
            'fields': ('descripcion',),
            'classes': ('wide',)
        }),
        ('Enlaces y fechas', {
            'fields': ('url_externa', 'fecha_inicio_alianza', 'fecha_fin_alianza')
        }),
    )
    
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    
    class Media:
        css = {
            'all': ('admin/css/ckeditor_custom.css',)
        }

from .models import PerfilRecolector, CargaSerieIndicador, CargaConjuntoDatos

@admin.register(PerfilRecolector)
class PerfilRecolectorAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_nombre_completo', 'rol', 'institucion', 'get_organismo', 'subrol_ficed', 'cargo', 'activo', 'fecha_creacion')
    list_filter = ('activo', 'rol', 'organismo', 'subrol_ficed')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'institucion', 'cargo')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    autocomplete_fields = ['organismo']
    
    fieldsets = (
        ('Usuario', {
            'fields': ('user',)
        }),
        ('Rol y Permisos', {
            'fields': ('rol', 'activo'),
            'description': 'delegado = Portal de Organismos | validador = Panel de Validación SIIED | recolector/consultor/ambos = módulos internos'
        }),
        ('Vínculo a Organismo', {
            'fields': ('organismo', 'subrol_ficed'),
            'description': 'Obligatorio para delegados. Define qué indicadores puede ver y cargar. '
                           'subrol_ficed = equipo técnico FICED que responde el delegado '
                           '(ETUAG_PSP/ETOBS/ETPP/ETSGC/ETGIE; vacío = formulario completo).'
        }),
        ('Información Institucional', {
            'fields': ('institucion', 'cargo', 'telefono')
        }),
        ('Fechas', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        }),
    )
    
    def get_organismo(self, obj):
        return obj.organismo.nombre if obj.organismo else '—'
    get_organismo.short_description = 'Organismo'
    get_organismo.admin_order_field = 'organismo__nombre'
    
    def get_nombre_completo(self, obj):
        """Muestra el nombre completo del usuario"""
        return obj.user.get_full_name() or obj.user.username
    get_nombre_completo.short_description = 'Nombre Completo'
    get_nombre_completo.admin_order_field = 'user__first_name'

@admin.register(CargaSerieIndicador)
class CargaSerieIndicadorAdmin(admin.ModelAdmin):
    list_display = ('codigo_evidencia', 'usuario', 'indicador', 'estado', 'es_carga_delegado', 'fecha_carga', 'registros_procesados', 'validado_por')
    list_filter = ('estado', 'es_carga_delegado', 'fecha_carga')
    search_fields = ('codigo_evidencia', 'usuario__username', 'indicador__nombre', 'indicador__codigo_indicador')
    readonly_fields = ('codigo_evidencia', 'fecha_carga', 'fecha_procesamiento', 'fecha_validacion')
    autocomplete_fields = ['indicador', 'usuario', 'validado_por']
    fieldsets = (
        ('Identificación', {'fields': ('codigo_evidencia', 'usuario', 'indicador')}),
        ('Archivos', {'fields': ('archivo_datos_xlsx', 'archivo_metadata_xlsx', 'archivo_datos_csv', 'archivo_metadata_csv')}),
        ('Estado', {'fields': ('estado', 'es_carga_delegado', 'fecha_carga', 'fecha_procesamiento', 'registros_procesados', 'registros_exitosos', 'registros_error')}),
        ('Validación', {'fields': ('validado_por', 'fecha_validacion', 'observaciones_validador', 'es_calculo_complejo')}),
        ('Logs', {'fields': ('mensaje_error', 'log_procesamiento'), 'classes': ('collapse',)}),
    )

@admin.register(CargaConjuntoDatos)
class CargaConjuntoDatosAdmin(admin.ModelAdmin):
    list_display = ('codigo_evidencia', 'usuario', 'conjunto_datos', 'estado', 'es_carga_delegado', 'fecha_carga', 'registros_procesados', 'validado_por')
    list_filter = ('estado', 'es_carga_delegado', 'fecha_carga')
    search_fields = ('codigo_evidencia', 'usuario__username', 'conjunto_datos__nombre')
    readonly_fields = ('codigo_evidencia', 'fecha_carga', 'fecha_procesamiento', 'fecha_validacion')
    fieldsets = (
        ('Identificación', {'fields': ('codigo_evidencia', 'usuario', 'conjunto_datos')}),
        ('Archivos', {'fields': ('archivo_microdata_xlsx', 'archivo_metadata_variables_xlsx', 'archivo_microdata_csv', 'archivo_metadata_variables_csv')}),
        ('Estado', {'fields': ('estado', 'es_carga_delegado', 'fecha_carga', 'fecha_procesamiento', 'registros_procesados', 'registros_exitosos', 'registros_error')}),
        ('Validación', {'fields': ('validado_por', 'fecha_validacion', 'observaciones_validador')}),
        ('Logs', {'fields': ('mensaje_error', 'log_procesamiento'), 'classes': ('collapse',)}),
    )

from .models import ConfiguracionSistema

@admin.register(ConfiguracionSistema)
class ConfiguracionSistemaAdmin(admin.ModelAdmin):
    list_display = ('clave', 'valor', 'fecha_actualizacion')
    list_filter = ('fecha_actualizacion',)
    search_fields = ('clave', 'descripcion')
    readonly_fields = ('fecha_actualizacion',)
    fields = ('clave', 'valor', 'descripcion', 'fecha_actualizacion')


# Personalizar el AdminSite para agregar estadísticas de usuarios
from django.contrib.admin import AdminSite as BaseAdminSite
from django.contrib.auth.models import User

class CustomAdminSite(BaseAdminSite):
    def index(self, request, extra_context=None):
        """
        Sobrescribe el index para agregar estadísticas de usuarios
        """
        extra_context = extra_context or {}
        
        # Calcular estadísticas de usuarios
        from .models import PerfilRecolector
        
        user_stats = {
            'staff_count': User.objects.filter(is_staff=True).count(),
            'recolector_count': PerfilRecolector.objects.filter(rol='recolector', activo=True).count(),
            'consultor_count': PerfilRecolector.objects.filter(rol='consultor', activo=True).count(),
            'validador_count': PerfilRecolector.objects.filter(rol='validador', activo=True).count(),
            'delegado_count': PerfilRecolector.objects.filter(rol='delegado', activo=True).count(),
            'editor_count': PerfilRecolector.objects.filter(rol='editor', activo=True).count(),
            'ambos_count': PerfilRecolector.objects.filter(rol='ambos', activo=True).count(),
        }
        
        extra_context['user_stats'] = user_stats

        # Métricas del flujo delegado/validación
        from .models import CargaSerieIndicador, CargaConjuntoDatos
        try:
            delegado_stats = {
                'series_pendientes': CargaSerieIndicador.objects.filter(
                    es_carga_delegado=True, estado__in=['enviado', 'en_revision']
                ).count(),
                'series_aprobadas': CargaSerieIndicador.objects.filter(
                    es_carga_delegado=True, estado='aprobado'
                ).count(),
                'series_procesadas': CargaSerieIndicador.objects.filter(
                    es_carga_delegado=True, estado='procesado'
                ).count(),
                'series_correcciones': CargaSerieIndicador.objects.filter(
                    es_carga_delegado=True,
                    estado__in=['rechazado', 'correcciones_solicitadas']
                ).count(),
                'series_calculo_complejo': CargaSerieIndicador.objects.filter(
                    es_carga_delegado=True, es_calculo_complejo=True, estado='aprobado'
                ).count(),
                'conjunto_datos_pendientes': CargaConjuntoDatos.objects.filter(
                    es_carga_delegado=True, estado__in=['enviado', 'en_revision']
                ).count(),
                'conjunto_datos_aprobadas': CargaConjuntoDatos.objects.filter(
                    es_carga_delegado=True, estado='aprobado'
                ).count(),
                'conjunto_datos_procesadas': CargaConjuntoDatos.objects.filter(
                    es_carga_delegado=True, estado='procesado'
                ).count(),
                'series_exitoso': CargaSerieIndicador.objects.filter(
                    es_carga_delegado=True, estado='exitoso'
                ).count(),
                'conjunto_datos_exitoso': CargaConjuntoDatos.objects.filter(
                    es_carga_delegado=True, estado='exitoso'
                ).count(),
                'total_pendientes': (
                    CargaSerieIndicador.objects.filter(
                        es_carga_delegado=True, estado__in=['enviado', 'en_revision']
                    ).count() +
                    CargaConjuntoDatos.objects.filter(
                        es_carga_delegado=True, estado__in=['enviado', 'en_revision']
                    ).count()
                ),
                'borradores_incompletos': CargaSerieIndicador.objects.filter(
                    es_carga_delegado=True, estado='borrador'
                ).count() + CargaConjuntoDatos.objects.filter(
                    es_carga_delegado=True, estado='borrador'
                ).count(),
            }
        except Exception:
            delegado_stats = {}
        extra_context['delegado_stats'] = delegado_stats

        # Estadísticas del módulo editorial
        from .models import ProductoAcademico, NoticiaBanner, Evento
        try:
            editorial_stats = {
                'productos_count': ProductoAcademico.objects.count(),
                'productos_borrador': ProductoAcademico.objects.filter(estado='borrador').count(),
                'productos_publicados': ProductoAcademico.objects.filter(estado='publicado').count(),
                'noticias_count': NoticiaBanner.objects.filter(activa=True).count(),
                'eventos_count': Evento.objects.count(),
            }
        except Exception:
            editorial_stats = {}
        extra_context['editorial_stats'] = editorial_stats

        # Datos de Suborganismos y Equipos para el admin index
        from .models import Suborganismo, EquipoOrganismo
        extra_context['suborganismos_list'] = Suborganismo.objects.filter(activo=True).select_related('organismo').order_by('organismo__nombre', 'orden', 'nombre')[:10]
        extra_context['equipos_list'] = EquipoOrganismo.objects.filter(activo=True).select_related('suborganismo', 'suborganismo__organismo').order_by('suborganismo__organismo__nombre', 'suborganismo__orden', 'nombre')[:10]

        return super().index(request, extra_context)

# Reemplazar el site admin por defecto
admin.site.__class__ = CustomAdminSite


# ============================================================================
# ADMIN PARA SISTEMA DE SATISFACCIÓN CIUDADANA
# ============================================================================

# ============================================================================
# INLINES PARA JERARQUÍA ORGANIZACIONAL
# ============================================================================

class SuborganismoInline(admin.TabularInline):
    model = Suborganismo
    extra = 0
    fields = ('nombre', 'codigo', 'tipo', 'orden', 'activo')
    ordering = ('orden', 'nombre')
    show_change_link = True


@admin.register(Organismo)
class OrganismoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'activo', 'responsable', 'fecha_creacion', 'total_suborganismos', 'total_equipos', 'total_respuestas')
    list_filter = ('activo', 'fecha_creacion')
    search_fields = ('nombre', 'codigo', 'responsable')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion', 'url_satisfaccion_rapida', 'url_formulario_completo')
    inlines = [SuborganismoInline]
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('nombre', 'codigo', 'descripcion', 'activo')
        }),
        ('Contacto', {
            'fields': ('email_contacto', 'responsable')
        }),
        ('URLs Generadas', {
            'fields': ('url_satisfaccion_rapida', 'url_formulario_completo'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        }),
    )
    
    def total_suborganismos(self, obj):
        total = obj.suborganismos.filter(activo=True).count()
        return format_html('<span style="font-weight: bold; color: #17a2b8;">{}</span>', total)
    total_suborganismos.short_description = 'Suborganismos'
    
    def total_equipos(self, obj):
        # Contar equipos a través de suborganismos (ya no hay FK directa)
        total = EquipoOrganismo.objects.filter(
            suborganismo__organismo=obj,
            activo=True
        ).count()
        return format_html('<span style="font-weight: bold; color: #28a745;">{}</span>', total)
    total_equipos.short_description = 'Equipos'
    
    def total_respuestas(self, obj):
        total = obj.respuestas_rapidas_organismo.count() + obj.respuestas_completas_organismo.count()
        return format_html('<span style="font-weight: bold; color: #007bff;">{}</span>', total)
    total_respuestas.short_description = 'Respuestas'
    
    def url_satisfaccion_rapida(self, obj):
        if obj.pk:
            url = self.request.build_absolute_uri(obj.get_url_satisfaccion_rapida())
            return format_html('<input type="text" value="{}" readonly style="width: 100%; font-family: monospace;">', url)
        return '-'
    url_satisfaccion_rapida.short_description = 'URL Calificación Rápida'
    
    def url_formulario_completo(self, obj):
        if obj.pk:
            url = self.request.build_absolute_uri(obj.get_url_formulario_completo())
            return format_html('<input type="text" value="{}" readonly style="width: 100%; font-family: monospace;">', url)
        return '-'
    url_formulario_completo.short_description = 'URL Formulario Completo'
    
    def get_queryset(self, request):
        self.request = request
        return super().get_queryset(request)


class EquipoOrganismoInline(admin.TabularInline):
    model = EquipoOrganismo
    extra = 0
    fields = ('nombre', 'codigo', 'activo')
    ordering = ('nombre',)
    show_change_link = True


@admin.register(Suborganismo)
class SuborganismoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'organismo', 'tipo', 'codigo', 'orden', 'activo', 'total_equipos', 'total_participantes')
    list_filter = ('activo', 'tipo', 'organismo')
    search_fields = ('nombre', 'codigo', 'organismo__nombre', 'descripcion')
    readonly_fields = ('fecha_creacion', 'fecha_modificacion')
    ordering = ('organismo', 'orden', 'nombre')
    inlines = [EquipoOrganismoInline]
    # Habilitar autocomplete para usar en otros admins
    autocomplete_fields = []
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('organismo', 'nombre', 'codigo', 'tipo', 'activo')
        }),
        ('Descripción', {
            'fields': ('descripcion',)
        }),
        ('Orden', {
            'fields': ('orden',),
            'description': 'Orden de visualización en listados (menor = primero)'
        }),
        ('Metadatos', {
            'fields': ('fecha_creacion', 'fecha_modificacion'),
            'classes': ('collapse',)
        }),
    )
    
    def total_equipos(self, obj):
        total = obj.equipos.filter(activo=True).count()
        return format_html('<span style="font-weight: bold; color: #28a745;">{}</span>', total)
    total_equipos.short_description = 'Equipos'
    
    def total_participantes(self, obj):
        total = obj.inscripciones_taller.count()
        if total > 0:
            return format_html('<span style="font-weight: bold; color: #007bff;">{}</span>', total)
        return '-'
    total_participantes.short_description = 'Participantes Taller'


@admin.register(EquipoOrganismo)
class EquipoOrganismoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'get_organismo', 'suborganismo', 'codigo', 'activo', 'total_respuestas', 'total_participantes_taller', 'promedio_satisfaccion')
    list_filter = ('activo', 'suborganismo__organismo', 'suborganismo', 'fecha_creacion')
    search_fields = ('nombre', 'codigo', 'suborganismo__nombre', 'suborganismo__organismo__nombre')
    autocomplete_fields = ['suborganismo']
    readonly_fields = ('fecha_creacion', 'fecha_modificacion', 'get_organismo')
    
    fieldsets = (
        ('Jerarquía Organizacional', {
            'fields': ('suborganismo', 'get_organismo'),
            'description': 'Subdirección/oficina a la que pertenece este equipo'
        }),
        ('Información del Equipo', {
            'fields': ('nombre', 'codigo', 'activo')
        }),
        ('Metadatos', {
            'fields': ('fecha_creacion', 'fecha_modificacion'),
            'classes': ('collapse',)
        }),
    )
    
    def total_respuestas(self, obj):
        total = obj.get_total_respuestas()
        if total > 0:
            return format_html('<span style="font-weight: bold; color: #007bff;">{}</span>', total)
        return '-'
    total_respuestas.short_description = 'Respuestas Satisfacción'
    
    def total_participantes_taller(self, obj):
        total = obj.inscripciones_taller.count()
        if total > 0:
            return format_html('<span style="font-weight: bold; color: #17a2b8;">{}</span>', total)
        return '-'
    total_participantes_taller.short_description = 'Participantes Taller'
    
    def get_organismo(self, obj):
        return obj.organismo.nombre
    get_organismo.short_description = 'Organismo'
    get_organismo.admin_order_field = 'suborganismo__organismo__nombre'
    
    def promedio_satisfaccion(self, obj):
        promedio = obj.get_promedio_satisfaccion()
        if promedio > 0:
            color = '#28a745' if promedio >= 4 else '#ffc107' if promedio >= 3 else '#dc3545'
            promedio_str = f"{promedio:.2f}"
            return format_html('<span style="font-weight: bold; color: {};">{}</span>', color, promedio_str)
        return '-'
    promedio_satisfaccion.short_description = 'Promedio Satisfacción'


@admin.register(CalendarioDifusion)
class CalendarioDifusionAdmin(admin.ModelAdmin):
    list_display = ('organismo', 'observatorio', 'producto_corto', 'tipo_cifras', 'periodicidad', 'fecha_publicacion', 'periodo_referencia', 'activo')
    list_filter = ('activo', 'tipo_cifras', 'periodicidad', 'organismo')
    search_fields = ('organismo__nombre', 'observatorio', 'producto')
    autocomplete_fields = ['organismo']
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')

    fieldsets = (
        ('Organismo y Observatorio', {
            'fields': ('organismo', 'observatorio')
        }),
        ('Producto Estadístico', {
            'fields': ('producto', 'tipo_cifras', 'periodicidad')
        }),
        ('Calendario de Publicación', {
            'fields': ('fecha_publicacion', 'periodo_referencia')
        }),
        ('Estado', {
            'fields': ('activo',)
        }),
        ('Metadatos', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        }),
    )

    def producto_corto(self, obj):
        return obj.producto[:80] + '...' if len(obj.producto) > 80 else obj.producto
    producto_corto.short_description = 'Producto'


@admin.register(RespuestaSatisfaccionRapida)
class RespuestaSatisfaccionRapidaAdmin(admin.ModelAdmin):
    list_display = ('id', 'organismo', 'calificacion_display', 'fecha_registro', 'ampliada', 'ip_address')
    list_filter = ('calificacion', 'ampliada', 'fecha_registro', 'organismo')
    search_fields = ('organismo__nombre', 'ip_address')
    readonly_fields = ('fecha_registro', 'ip_address', 'user_agent')
    date_hierarchy = 'fecha_registro'
    
    fieldsets = (
        ('Calificación', {
            'fields': ('organismo', 'calificacion', 'ampliada')
        }),
        ('Metadatos', {
            'fields': ('fecha_registro', 'ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )
    
    def calificacion_display(self, obj):
        colors = {
            1: '#dc3545',
            2: '#fd7e14',
            3: '#ffc107',
            4: '#28a745',
            5: '#20c997'
        }
        emojis = {
            1: '😞',
            2: '😕',
            3: '😐',
            4: '🙂',
            5: '😄'
        }
        color = colors.get(obj.calificacion, '#6c757d')
        emoji = emojis.get(obj.calificacion, '')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 10px; border-radius: 4px; font-weight: bold;">{} {} - {}</span>',
            color, emoji, obj.calificacion, obj.get_calificacion_display()
        )
    calificacion_display.short_description = 'Calificación'
    
    def has_add_permission(self, request):
        return False


@admin.register(RespuestaSatisfaccionCompleta)
class RespuestaSatisfaccionCompletaAdmin(admin.ModelAdmin):
    list_display = ('id', 'organismo', 'equipo', 'fecha_respuesta_solicitud', 'promedio_display', 'fecha_registro')
    list_filter = ('organismo', 'fecha_registro', 'fecha_respuesta_solicitud')
    search_fields = ('organismo__nombre', 'equipo__nombre', 'razon_insatisfaccion')
    readonly_fields = ('fecha_registro', 'ip_address', 'user_agent', 'promedio_satisfaccion', 'promedio_utilidad', 'promedio_relevancia', 'promedio_accesibilidad')
    date_hierarchy = 'fecha_registro'
    
    fieldsets = (
        ('Información General', {
            'fields': ('organismo', 'fecha_respuesta_solicitud', 'respuesta_rapida')
        }),
        ('Utilidad', {
            'fields': ('utilidad_tiempo_respuesta', 'utilidad_claridad', 'promedio_utilidad')
        }),
        ('Relevancia', {
            'fields': ('relevancia_periodicidad', 'relevancia_concordancia', 'promedio_relevancia')
        }),
        ('Accesibilidad', {
            'fields': ('accesibilidad_canal', 'accesibilidad_formato', 'promedio_accesibilidad')
        }),
        ('Insatisfacción', {
            'fields': ('razon_insatisfaccion',),
            'classes': ('collapse',)
        }),
        ('Promedios', {
            'fields': ('promedio_satisfaccion',),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('fecha_registro', 'ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )
    
    def promedio_display(self, obj):
        promedio = obj.calcular_promedio_satisfaccion()
        if promedio >= 4:
            color = '#28a745'
            emoji = '😄'
        elif promedio >= 3:
            color = '#ffc107'
            emoji = '😐'
        else:
            color = '#dc3545'
            emoji = '😞'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 10px; border-radius: 4px; font-weight: bold;">{} {}/5.0</span>',
            color, emoji, f"{promedio:.2f}"
        )
    promedio_display.short_description = 'Promedio'
    
    def promedio_satisfaccion(self, obj):
        return f"{obj.calcular_promedio_satisfaccion():.2f}"
    promedio_satisfaccion.short_description = 'Promedio General'
    
    def promedio_utilidad(self, obj):
        return f"{obj.calcular_promedio_utilidad():.2f}"
    promedio_utilidad.short_description = 'Promedio Utilidad'
    
    def promedio_relevancia(self, obj):
        return f"{obj.calcular_promedio_relevancia():.2f}"
    promedio_relevancia.short_description = 'Promedio Relevancia'
    
    def promedio_accesibilidad(self, obj):
        return f"{obj.calcular_promedio_accesibilidad():.2f}"
    promedio_accesibilidad.short_description = 'Promedio Accesibilidad'
    
    def has_add_permission(self, request):
        return False


# =============================================================================
# TALLER DE GESTIÓN DE DATOS INSTITUCIONALES + CATÁLOGO DE DATOS (módulos nuevos)
# =============================================================================

@admin.register(OpcionTaller)
class OpcionTallerAdmin(admin.ModelAdmin):
    list_display = ['etiqueta', 'categoria', 'orden', 'activa']
    list_filter = ['categoria', 'activa']
    list_editable = ['orden', 'activa']
    search_fields = ['etiqueta']


class FuenteDatosInline(admin.TabularInline):
    model = FuenteDatos
    extra = 0
    max_num = 10
    show_change_link = True
    fields = ['nombre', 'rol', 'fecha_inicio']


@admin.register(InscripcionTaller)
class InscripcionTallerAdmin(admin.ModelAdmin):
    list_display = ['nombre_completo', 'organismo', 'equipo', 'correo', 'estado', 'paso_actual', 'actualizado']
    list_filter = ['estado', 'organismo']
    search_fields = ['nombre_completo', 'organismo__nombre', 'equipo__nombre', 'correo']
    readonly_fields = ['uuid', 'creado', 'actualizado']
    date_hierarchy = 'creado'
    inlines = [FuenteDatosInline]


class FuenteOrigenInline(admin.TabularInline):
    model = FuenteOrigen
    extra = 0


class VariableFuenteInline(admin.TabularInline):
    model = VariableFuente
    extra = 0
    max_num = 10


@admin.register(FuenteDatos)
class FuenteDatosAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'inscripcion', 'rol', 'georreferenciacion', 'tiene_validacion']
    list_filter = ['rol', 'georreferenciacion', 'tiene_validacion', 'inscripcion__organismo']
    search_fields = ['nombre', 'descripcion', 'inscripcion__organismo__nombre']
    filter_horizontal = ['relaciones', 'instrumentos', 'mecanismos', 'periodicidades',
                         'desagregaciones', 'unidades_analisis', 'niveles_georref',
                         'problemas_calidad']
    inlines = [FuenteOrigenInline, VariableFuenteInline]


class FuenteRequeridaInline(admin.TabularInline):
    model = FuenteRequerida
    extra = 0
    max_num = 3


@admin.register(RetoAnalisis)
class RetoAnalisisAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'inscripcion', 'unidad_principal']
    list_filter = ['inscripcion__organismo']
    search_fields = ['nombre', 'analisis_propuesto', 'inscripcion__organismo__nombre']
    filter_horizontal = ['unidades_relacionar', 'desagregaciones', 'tratamientos',
                         'resultados_mvp', 'capacidades_sipdi', 'enfoques_diferenciales']
    inlines = [FuenteRequeridaInline]


@admin.register(EvaluacionSeguridad)
class EvaluacionSeguridadAdmin(admin.ModelAdmin):
    list_display = ['fuente', 'contiene_datos_personales', 'confidencialidad',
                    'integridad', 'disponibilidad', 'criticidad']
    list_filter = ['contiene_datos_personales', 'confidencialidad', 'integridad',
                   'disponibilidad', 'criticidad']
    search_fields = ['fuente__nombre', 'fuente__inscripcion__organismo__nombre',
                     'fuente__inscripcion__nombre_completo']
    filter_horizontal = ['variables_identificadoras', 'datos_sensibles', 'medidas_proteccion']


class CampoCatalogoInline(admin.TabularInline):
    model = CampoCatalogo
    extra = 0


@admin.register(BaseCatalogo)
class BaseCatalogoAdmin(admin.ModelAdmin):
    list_display = ['slug', 'nombre', 'organismo', 'frecuencia', 'cobertura', 'activa', 'orden']
    list_filter = ['activa', 'organismo']
    list_editable = ['orden', 'activa']
    search_fields = ['nombre', 'slug', 'descripcion']
    prepopulated_fields = {'slug': ('nombre',)}
    inlines = [CampoCatalogoInline]


@admin.register(CampoCatalogo)
class CampoCatalogoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'base', 'tipo', 'es_llave_cruce', 'sensibilidad', 'categoria']
    list_filter = ['base', 'tipo', 'es_llave_cruce', 'sensibilidad']
    list_editable = ['tipo', 'es_llave_cruce', 'sensibilidad']
    search_fields = ['nombre', 'descripcion', 'base__nombre']


# =============================================================================
# MÓDULO ICED — Índice de Capacidad Estadística y de Datos v2
# =============================================================================

from .models_iced import (
    ICEDFormulario, ICEDRecursoHumano, ICEDPersonaContacto,
    ICEDMacroProceso, ICEDProceso, ICEDSubproceso, ICEDProcedimiento,
    ICEDPreguntaEquipo
)


@admin.register(ICEDPreguntaEquipo)
class ICEDPreguntaEquipoAdmin(admin.ModelAdmin):
    """Asignación pregunta ↔ equipo técnico del FICED (seed: seed_iced_equipos)."""
    list_display = ('codigo', 'equipo')
    list_filter = ('equipo',)
    search_fields = ('codigo',)
    ordering = ('codigo', 'equipo')


class ICEDRecursoHumanoInline(admin.TabularInline):
    model = ICEDRecursoHumano
    extra = 0
    fields = ('nombre_completo', 'tipo_vinculacion', 'categoria_cargo', 'nivel_formacion',
              'anios_experiencia', 'funciones_estadisticas')
    readonly_fields = ('nombre_completo',)


class ICEDPersonaContactoInline(admin.TabularInline):
    model = ICEDPersonaContacto
    extra = 0
    fields = ('nombre_completo', 'cargo', 'correo', 'telefono', 'orden')


@admin.register(ICEDFormulario)
class ICEDFormularioAdmin(admin.ModelAdmin):
    list_display = (
        'organismo', 'periodo', 'equipo', 'estado', 'puntaje_global_colored',
        'usuario_diligencia', 'fecha_envio', 'completitud'
    )
    list_filter = ('estado', 'periodo', 'equipo', 'organismo')
    search_fields = ('organismo__nombre', 'usuario_diligencia__username', 'observaciones_validador')
    readonly_fields = (
        'puntaje_b', 'puntaje_c', 'puntaje_d', 'puntaje_e', 'puntaje_global',
        'puntajes_detalle',
        'fecha_creacion', 'fecha_actualizacion', 'fecha_envio', 'fecha_validacion'
    )
    inlines = [ICEDPersonaContactoInline, ICEDRecursoHumanoInline]
    fieldsets = (
        ('Identificación', {
            'fields': ('organismo', 'periodo', 'equipo', 'estado', 'usuario_diligencia', 'paso_actual')
        }),
        ('Respuestas por módulo', {
            'fields': ('respuestas_a', 'respuestas_b', 'respuestas_c', 'respuestas_d', 'respuestas_e'),
            'classes': ('collapse',)
        }),
        ('Puntajes calculados', {
            'fields': ('puntaje_b', 'puntaje_c', 'puntaje_d', 'puntaje_e', 'puntaje_global', 'puntajes_detalle'),
        }),
        ('Auditoría', {
            'fields': ('fecha_creacion', 'fecha_actualizacion', 'fecha_envio', 'fecha_validacion'),
        }),
        ('Validación', {
            'fields': ('observaciones_validador',),
        }),
    )
    actions = ['calcular_puntajes', 'marcar_validado', 'devolver_correccion']

    @admin.display(description='Puntaje ICED')
    def puntaje_global_colored(self, obj):
        if obj.puntaje_global is None:
            return format_html('<span style="color: #94a3b8;">—</span>')
        colores = {
            'muy_alto': '#064e3b',
            'alto': '#059669',
            'medio': '#d97706',
            'bajo': '#dc2626',
        }
        color = colores.get(obj.nivel_global, '#64748b')
        pct = round(float(obj.puntaje_global) * 100, 1)
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}%</span> — {}',
            color, pct, obj.nivel_global_display
        )

    @admin.action(description='Calcular/recalcular puntajes ICED')
    def calcular_puntajes(self, request, queryset):
        from .calcular_iced import aplicar_puntajes
        for formulario in queryset:
            aplicar_puntajes(formulario)
        self.message_user(request, f'Se calcularon puntajes para {queryset.count()} formulario(s).')

    @admin.action(description='Marcar como Validado')
    def marcar_validado(self, request, queryset):
        from django.utils import timezone
        queryset.update(estado='validado', fecha_validacion=timezone.now())
        self.message_user(request, f'{queryset.count()} formulario(s) marcado(s) como Validado.')

    @admin.action(description='Devolver para corrección')
    def devolver_correccion(self, request, queryset):
        queryset.update(estado='devuelto')
        self.message_user(request, f'{queryset.count()} formulario(s) devuelto(s) para corrección.')


@admin.register(ICEDRecursoHumano)
class ICEDRecursoHumanoAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'formulario', 'tipo_vinculacion', 'nivel_formacion',
                    'anios_experiencia', 'funciones_estadisticas')
    list_filter = ('tipo_vinculacion', 'nivel_formacion', 'funciones_estadisticas',
                   'formulario__organismo', 'formulario__periodo')
    search_fields = ('nombre_completo', 'correo', 'grupo', 'formulario__organismo__nombre')
    autocomplete_fields = ['formulario']


@admin.register(ICEDPersonaContacto)
class ICEDPersonaContactoAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'cargo', 'correo', 'telefono', 'formulario', 'orden')
    list_filter = ('formulario__organismo', 'formulario__periodo')
    search_fields = ('nombre_completo', 'cargo', 'correo', 'formulario__organismo__nombre')
    autocomplete_fields = ['formulario']


# =============================================================================
# ICED — Estructura MOP (MacroProceso / Proceso / Subproceso / Procedimiento)
# =============================================================================

class ICEDProcesoInline(admin.TabularInline):
    model = ICEDProceso
    extra = 0
    fields = ('codigo', 'nombre', 'activo')
    show_change_link = True


class ICEDSubprocesoInline(admin.TabularInline):
    model = ICEDSubproceso
    extra = 0
    fields = ('codigo', 'nombre', 'activo')
    show_change_link = True


class ICEDProcedimientoInline(admin.TabularInline):
    model = ICEDProcedimiento
    extra = 0
    fields = ('codigo', 'nombre', 'activo')


class ICEDProcedimientoDirectoInline(admin.TabularInline):
    """Procedimientos que cuelgan directamente del Proceso (sin subproceso)."""
    model = ICEDProcedimiento
    fk_name = 'proceso'
    extra = 0
    fields = ('codigo', 'nombre', 'activo')
    verbose_name = 'Procedimiento directo'
    verbose_name_plural = 'Procedimientos directos (sin subproceso)'


@admin.register(ICEDMacroProceso)
class ICEDMacroProcesoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'activo', 'num_procesos')
    list_filter = ('activo',)
    search_fields = ('codigo', 'nombre')
    inlines = [ICEDProcesoInline]

    @admin.display(description='Procesos')
    def num_procesos(self, obj):
        return obj.procesos.count()


@admin.register(ICEDProceso)
class ICEDProcesoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'macroproceso', 'activo', 'num_subprocesos')
    list_filter = ('activo', 'macroproceso')
    search_fields = ('codigo', 'nombre', 'macroproceso__nombre')
    inlines = [ICEDSubprocesoInline, ICEDProcedimientoDirectoInline]

    @admin.display(description='Subprocesos')
    def num_subprocesos(self, obj):
        return obj.subprocesos.count()


@admin.register(ICEDSubproceso)
class ICEDSubprocesoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'proceso', 'activo', 'num_procedimientos')
    list_filter = ('activo', 'proceso__macroproceso')
    search_fields = ('codigo', 'nombre', 'proceso__nombre')
    inlines = [ICEDProcedimientoInline]

    @admin.display(description='Procedimientos')
    def num_procedimientos(self, obj):
        return obj.procedimientos.count()


@admin.register(ICEDProcedimiento)
class ICEDProcedimientoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'subproceso', 'proceso', 'activo')
    list_filter = ('activo', 'subproceso__proceso__macroproceso', 'proceso__macroproceso')
    search_fields = ('codigo', 'nombre', 'subproceso__nombre', 'proceso__nombre')


# ============================================================================
# ADMIN: PRODUCTOS EDUCATIVOS (NIÑOS Y ADOLESCENTES)
# ============================================================================

class SeccionEducativaInline(admin.TabularInline):
    model = SeccionEducativa
    extra = 1
    fields = ('numero_orden', 'titulo', 'icono_emoji', 'tipo_bloque', 'puntos_seccion', 'tiene_quiz')
    ordering = ['numero_orden']


@admin.register(ProductoEducativo)
class ProductoEducativoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'publico', 'estado', 'nivel_gamificacion', 'puntos_totales', 'fecha_publicacion', 'updated_at')
    list_filter = ('publico', 'estado', 'nivel_gamificacion', 'paleta_colores', 'tiene_recompensas')
    search_fields = ('titulo', 'resumen_infantil', 'palabras_clave', 'autor')
    prepopulated_fields = {'slug': ('titulo',)}
    filter_horizontal = ('temas_relacionados',)
    inlines = [SeccionEducativaInline]
    date_hierarchy = 'fecha_publicacion'
    
    fieldsets = (
        ('📚 Información básica', {
            'fields': ('titulo', 'slug', 'publico', 'estado')
        }),
        ('🎨 Identidad visual', {
            'fields': ('imagen_portada', 'paleta_colores', 'resumen_infantil')
        }),
        ('🦜 Personaje guía', {
            'fields': ('personaje_guia', 'mensaje_bienvenida')
        }),
        ('🎮 Gamificación', {
            'fields': ('nivel_gamificacion', 'tiene_recompensas', 'puntos_totales'),
            'description': 'Configuración de mecánicas de juego y recompensas'
        }),
        ('🔗 Vinculación con contenido técnico', {
            'fields': ('producto_origen', 'organismo', 'temas_relacionados'),
            'classes': ('collapse',)
        }),
        ('📝 Metadatos', {
            'fields': ('palabras_clave', 'autor', 'fecha_publicacion'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['publicar_productos', 'enviar_a_revision', 'clonar_producto']
    
    def publicar_productos(self, request, queryset):
        count = queryset.update(estado='publicado')
        self.message_user(request, f'{count} producto(s) publicado(s) exitosamente.')
    publicar_productos.short_description = "✅ Publicar productos seleccionados"
    
    def enviar_a_revision(self, request, queryset):
        count = queryset.update(estado='revision')
        self.message_user(request, f'{count} producto(s) enviado(s) a revisión.')
    enviar_a_revision.short_description = "📋 Enviar a revisión"
    
    def clonar_producto(self, request, queryset):
        for producto in queryset:
            secciones_originales = list(producto.secciones.all())
            producto.pk = None
            producto.slug = f"{producto.slug}-copia"
            producto.titulo = f"{producto.titulo} (Copia)"
            producto.estado = 'borrador'
            producto.save()
            
            for seccion in secciones_originales:
                seccion.pk = None
                seccion.producto = producto
                seccion.save()
        
        self.message_user(request, f'{queryset.count()} producto(s) clonado(s) exitosamente.')
    clonar_producto.short_description = "📋 Clonar producto(s)"


@admin.register(SeccionEducativa)
class SeccionEducativaAdmin(admin.ModelAdmin):
    list_display = ('numero_orden', 'titulo', 'producto', 'tipo_bloque', 'puntos_seccion', 'tiene_quiz')
    list_display_links = ('titulo',)
    list_filter = ('tipo_bloque', 'tiene_quiz', 'producto__publico')
    search_fields = ('titulo', 'contenido', 'producto__titulo')
    list_editable = ('numero_orden', 'puntos_seccion')
    
    fieldsets = (
        ('📍 Ubicación', {
            'fields': ('producto', 'numero_orden', 'titulo', 'icono_emoji')
        }),
        ('🎨 Tipo de bloque', {
            'fields': ('tipo_bloque', 'contenido')
        }),
        ('⚙️ Configuración específica', {
            'fields': ('configuracion_bloque',),
            'description': 'JSON con configuración del bloque (preguntas, opciones, etc.)',
            'classes': ('collapse',)
        }),
        ('📊 Vinculación con datos', {
            'fields': ('indicador_vinculado', 'conjunto_datos_vinculado'),
            'classes': ('collapse',)
        }),
        ('🎮 Gamificación', {
            'fields': ('puntos_seccion', 'tiene_quiz')
        }),
    )


@admin.register(LogroEducativo)
class LogroEducativoAdmin(admin.ModelAdmin):
    list_display = ('icono_emoji', 'nombre', 'tipo', 'puntos_requeridos')
    list_filter = ('tipo',)
    search_fields = ('nombre', 'descripcion')
    list_editable = ('puntos_requeridos',)


@admin.register(ProgresoUsuarioEducativo)
class ProgresoUsuarioEducativoAdmin(admin.ModelAdmin):
    list_display = ('session_key', 'producto', 'puntos_obtenidos', 'completado', 'fecha_ultima_actividad')
    list_filter = ('completado', 'producto__publico', 'fecha_inicio')
    search_fields = ('session_key', 'producto__titulo')
    filter_horizontal = ('secciones_completadas', 'logros_desbloqueados')
    readonly_fields = ('fecha_inicio', 'fecha_ultima_actividad')
    
    fieldsets = (
        ('👤 Usuario', {
            'fields': ('session_key', 'producto')
        }),
        ('📊 Progreso', {
            'fields': ('puntos_obtenidos', 'completado', 'secciones_completadas')
        }),
        ('🏆 Logros', {
            'fields': ('logros_desbloqueados',)
        }),
        ('📅 Fechas', {
            'fields': ('fecha_inicio', 'fecha_ultima_actividad'),
            'classes': ('collapse',)
        }),
    )


# ============================================================================
# MCP — tokens de acceso y auditoría
# ============================================================================

from .models import MCPApiToken, MCPAuditLog


@admin.register(MCPApiToken)
class MCPApiTokenAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'user', 'rol_actual', 'activo', 'expira_en',
                    'ultimo_uso', 'fecha_creacion')
    list_filter = ('activo', 'fecha_creacion')
    search_fields = ('nombre', 'user__username', 'user__email')
    readonly_fields = ('token_hash', 'ultimo_uso', 'ip_ultimo_uso',
                       'fecha_creacion')
    exclude = ('token',)
    fieldsets = (
        ('Token', {
            'description': 'El token en claro solo se muestra al emitirse '
                           '(manage.py emitir_token_mcp). Aquí nunca es '
                           'recuperable.',
            'fields': ('nombre', 'user', 'token_hash')
        }),
        ('Vigencia', {'fields': ('activo', 'expira_en')}),
        ('Uso', {'fields': ('ultimo_uso', 'ip_ultimo_uso', 'fecha_creacion')}),
    )

    @admin.display(description='Rol actual')
    def rol_actual(self, obj):
        perfil = getattr(obj.user, 'perfil_recolector', None)
        return perfil.get_rol_display() if perfil else '— (solo capa pública)'

    def save_model(self, request, obj, form, change):
        # El admin no permite crear tokens a mano: usar emitir_token_mcp
        if not change and not obj.token_hash:
            raise ValueError(
                'Los tokens MCP se emiten con `manage.py emitir_token_mcp`.')
        super().save_model(request, obj, form, change)


@admin.register(MCPAuditLog)
class MCPAuditLogAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'usuario', 'rol', 'tool', 'exito',
                    'duracion_ms', 'ip')
    list_filter = ('exito', 'rol', 'tool', 'fecha')
    search_fields = ('usuario__username', 'tool', 'ip')
    readonly_fields = ('usuario', 'rol', 'tool', 'argumentos', 'exito',
                       'duracion_ms', 'error', 'ip', 'fecha')
    date_hierarchy = 'fecha'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
