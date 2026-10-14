"""
Formularios para el Wizard Admin Unificado.
Cada formulario representa un paso específico del wizard adaptativo.
"""

from django import forms
from django.core.exceptions import ValidationError
from .models import (
    CargaConjuntoDatos, CargaSerieIndicador, ConjuntoDatos, Indicador,
    MenuSubtema, OperacionEstadistica, VariableConjuntoDatos,
    DominioDesagregacion, Desagregacion, ReglaExtraccion,
    Grafico, GraficoSerie
)
import pandas as pd
import json


class CargaSerieChoiceField(forms.ModelChoiceField):
    """ModelChoiceField para CargaSerieIndicador con estado visible en el label."""
    def label_from_instance(self, obj):
        estado = obj.get_estado_display()
        indicador = f" → {obj.indicador.nombre}" if obj.indicador else ""
        fecha = obj.fecha_carga.strftime('%d/%m/%Y')
        return f"[{estado}] {obj.codigo_evidencia} - {obj.usuario.username} ({fecha}){indicador}"


class CargaConjuntoDatosChoiceField(forms.ModelChoiceField):
    """ModelChoiceField para CargaConjuntoDatos con estado visible en el label."""
    def label_from_instance(self, obj):
        estado = obj.get_estado_display()
        nombre = f" • {obj.nombre}" if hasattr(obj, 'nombre') and obj.nombre else ""
        fecha = obj.fecha_carga.strftime('%d/%m/%Y')
        return f"[{estado}] {obj.codigo_evidencia} - {obj.usuario.username} ({fecha}){nombre}"


class IndicadorChoiceField(forms.ModelChoiceField):
    """ModelChoiceField que muestra [código] nombre • subtema en las opciones."""
    def label_from_instance(self, obj):
        codigo = f"[{obj.codigo_indicador}] " if obj.codigo_indicador else ""
        subtema = f" • {obj.subtema.nombre}" if obj.subtema else ""
        return f"{codigo}{obj.nombre}{subtema}"


# ============================================================================
# PASO 1: SELECCIÓN DE FUENTE (Común a todos los flujos)
# ============================================================================

class FormSeleccionFuente(forms.Form):
    """
    Paso 1: Permite seleccionar desde dónde iniciar el procesamiento.
    Este paso determina qué flujo (A, B, C o D) se ejecutará.
    """
    
    TIPO_FUENTE_CHOICES = [
        ('carga_pendiente', 'Cargas Pendientes del Módulo de Recolección'),
        ('actualizar_existente', 'Actualizar Indicador Existente'),
    ]
    
    tipo_fuente = forms.ChoiceField(
        label="¿Qué deseas procesar?",
        choices=TIPO_FUENTE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'tipo-fuente-radio'}),
        help_text="Selecciona el tipo de procesamiento que deseas realizar"
    )
    
    # Si selecciona 'carga_pendiente'
    carga_conjunto_datos = CargaConjuntoDatosChoiceField(
        queryset=CargaConjuntoDatos.objects.filter(
            estado__in=['pendiente', 'aprobado']
        ).select_related('usuario').order_by('-fecha_carga'),
        required=False,
        label="Seleccionar Carga de conjunto_datos",
        widget=forms.Select(attrs={
            'class': 'carga-select',
            'style': 'min-width: 300px;'
        }),
        help_text="Cargas de conjunto_datos pendientes de procesar",
        empty_label="--- Seleccionar conjunto_datos ---"
    )
    
    carga_serie = CargaSerieChoiceField(
        queryset=CargaSerieIndicador.objects.filter(
            estado__in=['pendiente', 'aprobado']
        ).select_related('usuario', 'indicador').order_by('-fecha_carga'),
        required=False,
        label="Seleccionar Carga de Serie",
        widget=forms.Select(attrs={
            'class': 'carga-select',
            'style': 'min-width: 300px;'
        }),
        help_text="Cargas de series de datos pendientes de procesar",
        empty_label="--- Seleccionar Serie ---"
    )
    
    # Si selecciona 'actualizar_existente'
    indicador_existente = forms.ModelChoiceField(
        queryset=Indicador.objects.all(),
        required=False,
        label="Seleccionar Indicador",
        widget=forms.Select(attrs={'class': 'indicador-select'}),
        help_text="Indicador existente que deseas actualizar"
    )
    
    # Si selecciona 'nuevo_conjunto_datos' o 'nueva_serie'
    archivo_conjunto_datos = forms.FileField(
        required=False,
        label="Archivo de conjunto_datos (CSV/Excel)",
        help_text="Archivo con los conjuntos_datos"
    )
    
    archivo_metadata_variables = forms.FileField(
        required=False,
        label="Archivo de Metadata de Variables (CSV/Excel)",
        help_text="Archivo con la metadata de las variables"
    )
    
    archivo_datos = forms.FileField(
        required=False,
        label="Archivo de Datos (CSV/Excel)",
        help_text="Archivo con la serie de datos del indicador"
    )
    
    archivo_metadata_indicador = forms.FileField(
        required=False,
        label="Archivo de Metadata del Indicador (CSV/Excel)",
        help_text="Archivo con la ficha técnica del indicador"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        tipo_fuente = cleaned_data.get('tipo_fuente')
        
        if tipo_fuente == 'carga_pendiente':
            # Debe seleccionar al menos una carga
            if not cleaned_data.get('carga_conjunto_datos') and not cleaned_data.get('carga_serie'):
                raise ValidationError(
                    "Debes seleccionar al menos una carga pendiente (conjunto_datos o serie)"
                )
        
        elif tipo_fuente == 'actualizar_existente':
            # Debe seleccionar un indicador
            if not cleaned_data.get('indicador_existente'):
                raise ValidationError("Debes seleccionar un indicador existente")
        
        return cleaned_data


# ============================================================================
# FLUJO B: SOLO SERIE DE DATOS
# ============================================================================

class FormPreviewSerie(forms.Form):
    """Paso 2B: Preview de serie con Univer.js"""
    
    confirmar_preview = forms.BooleanField(
        required=True,
        label="He revisado los datos y deseo continuar",
        widget=forms.CheckboxInput(attrs={'class': 'confirm-checkbox'})
    )


class FormConfigIndicadorSerie(forms.Form):
    """Paso 3B: Configurar Indicador para serie"""
    
    OPCION_CHOICES = [
        ('crear_nuevo', 'Crear Nuevo Indicador'),
        ('asociar_existente', 'Asociar Indicador Existente'),
    ]
    
    opcion = forms.ChoiceField(
        label="¿Qué deseas hacer?",
        choices=OPCION_CHOICES,
        widget=forms.RadioSelect,
        initial='crear_nuevo'
    )
    
    # Si crear nuevo
    codigo_indicador = forms.CharField(
        max_length=50,
        required=False,
        label="Código del Indicador",
        widget=forms.TextInput(attrs={'placeholder': 'Ej: IND-001'})
    )
    
    nombre_indicador = forms.CharField(
        max_length=500,
        required=False,
        label="Nombre del Indicador",
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Tasa de Desempleo'})
    )
    
    sigla = forms.CharField(
        max_length=50,
        required=False,
        label="Sigla",
        widget=forms.TextInput(attrs={'placeholder': 'Ej: TD'})
    )
    
    subtema = forms.ModelChoiceField(
        queryset=MenuSubtema.objects.all(),
        required=False,
        label="Subtema",
        help_text="Subtema principal (ruta canónica dominio › tema › subtema)"
    )

    subtemas_adicionales = forms.ModelMultipleChoiceField(
        queryset=MenuSubtema.objects.all(),
        required=False,
        label="Subtemas adicionales",
        help_text="Otros subtemas (de cualquier dominio) bajo los que "
                  "también se clasifica el indicador"
    )
    
    # Si asociar existente
    indicador_existente = IndicadorChoiceField(
        queryset=Indicador.objects.select_related('subtema').order_by('nombre'),
        required=False,
        label="Seleccionar Indicador Existente",
        widget=forms.Select(attrs={'class': 'indicador-select'})
    )

    def clean(self):
        cleaned_data = super().clean()
        opcion = cleaned_data.get('opcion')
        
        if opcion == 'crear_nuevo':
            if not cleaned_data.get('codigo_indicador'):
                raise ValidationError("El código del indicador es obligatorio")
            if not cleaned_data.get('nombre_indicador'):
                raise ValidationError("El nombre del indicador es obligatorio")
            if not cleaned_data.get('subtema'):
                raise ValidationError("Debes seleccionar un subtema")
        
        elif opcion == 'asociar_existente':
            if not cleaned_data.get('indicador_existente'):
                raise ValidationError("Debes seleccionar un indicador existente")
        
        return cleaned_data


class FormCargarMetadata(forms.Form):
    """Paso 4B: Cargar Metadata del Indicador"""
    
    cargar_metadata_auto = forms.BooleanField(
        required=False,
        initial=True,
        label="Cargar metadata automáticamente desde el archivo",
        help_text="Si está disponible, se extraerá la ficha técnica del CSV/Excel"
    )
    
    # Campos opcionales para editar metadata
    definicion = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Definición"
    )
    
    interpretacion = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Interpretación"
    )
    
    metodologia = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Metodología"
    )


class FormVerificarDesagregaciones(forms.Form):
    """Paso 5B: Configurar clasificaciones del indicador"""
    
    crear_faltantes_auto = forms.BooleanField(
        required=False,
        initial=True,
        label="Crear clasificaciones faltantes automáticamente",
        help_text="Si hay categorías en tu archivo que no existen en el sistema, se crearán automáticamente."
    )


class FormMapeoColumnas(forms.Form):
    """Paso 6B: Identificar las columnas de fecha y valor en tu archivo"""
    
    columna_fecha = forms.ChoiceField(
        label="¿Qué columna contiene las fechas?",
        help_text="Selecciona la columna de tu archivo que tiene las fechas (ej: Año, Periodo, Fecha)"
    )
    
    columna_valor = forms.ChoiceField(
        label="¿Qué columna contiene los valores del indicador?",
        help_text="Selecciona la columna de tu archivo que tiene los valores numéricos del indicador"
    )
    
    def __init__(self, *args, **kwargs):
        columnas = kwargs.pop('columnas', [])
        super().__init__(*args, **kwargs)
        
        if columnas:
            choices = [(col, col) for col in columnas]
            self.fields['columna_fecha'].choices = choices
            self.fields['columna_valor'].choices = choices


class FormConfirmacionSerie(forms.Form):
    """Paso 7B: Confirmación final antes de importar"""
    
    eliminar_datos_existentes = forms.BooleanField(
        required=False,
        initial=False,
        label="Eliminar datos existentes del indicador",
        help_text="Si está marcado, se eliminarán todos los datos actuales antes de importar"
    )
    
    confirmar_importacion = forms.BooleanField(
        required=True,
        label="Confirmo que deseo importar los datos",
        widget=forms.CheckboxInput(attrs={'class': 'confirm-checkbox'})
    )


# ============================================================================
# FLUJO A: CON MICRODATA
# ============================================================================

class FormPreviewconjunto_datos(forms.Form):
    """Paso 2A: Preview de conjunto_datos con Univer.js"""
    
    # Este formulario no tiene campos editables
    # Solo muestra el preview con Univer.js
    confirmar_preview = forms.BooleanField(
        required=True,
        label="He revisado los datos y deseo continuar",
        widget=forms.CheckboxInput(attrs={'class': 'confirm-checkbox'})
    )


class FormConfigconjunto_datos(forms.Form):
    """Paso 3A: Configurar o crear registro de conjunto_datos"""
    
    OPCION_CHOICES = [
        ('crear_nueva', 'Crear Nueva conjunto_datos'),
        ('asociar_existente', 'Asociar conjunto_datos Existente'),
    ]
    
    opcion = forms.ChoiceField(
        label="¿Qué deseas hacer?",
        choices=OPCION_CHOICES,
        widget=forms.RadioSelect,
        initial='crear_nueva'
    )
    
    # Si crear nueva
    nombre_conjunto_datos = forms.CharField(
        max_length=255,
        required=False,
        label="Nombre de la conjunto_datos",
        widget=forms.TextInput(attrs={'placeholder': 'Ej: conjunto_datos Encuesta de Hogares 2024'})
    )
    
    descripcion_conjunto_datos = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Descripción"
    )
    
    operacion_estadistica = forms.ModelChoiceField(
        queryset=OperacionEstadistica.objects.all(),
        required=False,
        label="Operación Estadística"
    )
    
    # Si asociar existente
    conjunto_datos_existente = forms.ModelChoiceField(
        queryset=ConjuntoDatos.objects.all(),
        required=False,
        label="Seleccionar conjunto_datos Existente"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        opcion = cleaned_data.get('opcion')
        
        if opcion == 'crear_nueva':
            if not cleaned_data.get('nombre_conjunto_datos'):
                raise ValidationError("Debes proporcionar un nombre para la conjunto_datos")
        elif opcion == 'asociar_existente':
            if not cleaned_data.get('conjunto_datos_existente'):
                raise ValidationError("Debes seleccionar una conjunto_datos existente")
        
        return cleaned_data


class FormMetadataVariables(forms.Form):
    """Paso 4A: Cargar automáticamente metadata de variables desde CSV"""
    
    cargar_automaticamente = forms.BooleanField(
        initial=True,
        required=False,
        label="Cargar metadata de variables automáticamente desde CSV",
        help_text="Si está marcado, se crearán las variables automáticamente"
    )
    
    # Campo oculto para almacenar las variables detectadas (JSON)
    variables_detectadas_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )


class FormConfigIndicador(forms.Form):
    """Paso 5A/3B/5C: Configurar o crear indicador"""
    
    OPCION_CHOICES = [
        ('crear_nuevo', 'Crear Nuevo Indicador'),
        ('asociar_existente', 'Asociar Indicador Existente'),
    ]
    
    opcion = forms.ChoiceField(
        label="¿Qué deseas hacer?",
        choices=OPCION_CHOICES,
        widget=forms.RadioSelect,
        initial='crear_nuevo'
    )
    
    # Si crear nuevo
    codigo_indicador = forms.CharField(
        max_length=100,
        required=False,
        label="Código del Indicador",
        widget=forms.TextInput(attrs={'placeholder': 'Ej: IND-001'})
    )
    
    nombre = forms.CharField(
        max_length=255,
        required=False,
        label="Nombre del Indicador",
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Tasa de Desempleo'})
    )
    
    sigla = forms.CharField(
        max_length=50,
        required=False,
        label="Sigla",
        widget=forms.TextInput(attrs={'placeholder': 'Ej: TD'})
    )
    
    subtema = forms.ModelChoiceField(
        queryset=MenuSubtema.objects.all(),
        required=False,
        label="Subtema",
        help_text="Subtema principal (ruta canónica dominio › tema › subtema)"
    )

    subtemas_adicionales = forms.ModelMultipleChoiceField(
        queryset=MenuSubtema.objects.all(),
        required=False,
        label="Subtemas adicionales",
        help_text="Otros subtemas (de cualquier dominio) bajo los que "
                  "también se clasifica el indicador"
    )
    
    # Si asociar existente
    indicador_existente = forms.ModelChoiceField(
        queryset=Indicador.objects.all(),
        required=False,
        label="Seleccionar Indicador Existente"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        opcion = cleaned_data.get('opcion')
        
        if opcion == 'crear_nuevo':
            if not cleaned_data.get('nombre'):
                raise ValidationError("Debes proporcionar un nombre para el indicador")
            if not cleaned_data.get('subtema'):
                raise ValidationError("Debes seleccionar un subtema")
        elif opcion == 'asociar_existente':
            if not cleaned_data.get('indicador_existente'):
                raise ValidationError("Debes seleccionar un indicador existente")
        
        return cleaned_data


class FormMetadataIndicador(forms.Form):
    """Paso 4B/6C: Cargar metadata completa del indicador desde CSV"""
    
    cargar_metadata_completa = forms.BooleanField(
        initial=True,
        required=False,
        label="Cargar metadata completa desde CSV (ficha técnica)",
        help_text="Si está marcado, se cargarán todos los campos de la ficha técnica"
    )
    
    # Campo oculto para almacenar la metadata detectada (JSON)
    metadata_detectada_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )


class FormVerificarDesagregaciones(forms.Form):
    """Paso 6A/5B/7C: Seleccionar clasificaciones del indicador"""
    
    from .models import DominioDesagregacion
    
    dominios_desagregacion_geografica = forms.ModelMultipleChoiceField(
        queryset=DominioDesagregacion.objects.filter(tipo='geografica'),
        required=False,
        label="Clasificaciones por ubicación (Departamento, Municipio, etc.)",
        widget=forms.CheckboxSelectMultiple,
        help_text="Selecciona las clasificaciones geográficas que usa tu indicador (ej: por departamento, por municipio)."
    )
    
    dominios_desagregacion_tematica = forms.ModelMultipleChoiceField(
        queryset=DominioDesagregacion.objects.filter(tipo='tematica'),
        required=False,
        label="Clasificaciones por categoría (Sexo, Edad, etc.)",
        widget=forms.CheckboxSelectMultiple,
        help_text="Selecciona las clasificaciones temáticas que usa tu indicador (ej: por sexo, por edad, por nivel educativo)."
    )
    
    crear_faltantes_auto = forms.BooleanField(
        initial=True,
        required=False,
        label="Crear clasificaciones faltantes automáticamente",
        help_text="Si hay categorías en tu archivo que no existen en el sistema, se crearán automáticamente."
    )
    
    # Campos ocultos para almacenar el análisis (JSON)
    analisis_geograficas_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    
    analisis_tematicas_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    
    columnas_csv_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
        help_text="JSON con las columnas detectadas en el CSV para verificación"
    )
    
    # JSON con decisiones del usuario sobre columnas restantes como dominios de desagregación
    # Formato: [{"columna": "Sexo", "accion": "crear"|"asociar"|"ignorar", "dominio_id": null|int, "tipo": "tematica"|"geografica"}]
    columnas_desagregacion_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
        help_text="JSON con mapeo de columnas restantes a dominios de desagregación"
    )


class FormReglaExtraccion(forms.Form):
    """Paso 7A/8C: Crear regla de extracción"""
    
    columna_fecha = forms.CharField(
        max_length=100,
        label="Columna de Fecha",
        widget=forms.TextInput(attrs={'placeholder': 'Ej: fecha, anio, periodo'})
    )
    
    columnas_fuente = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Ej: poblacion, nacimientos, defunciones'}),
        label="Columnas Fuente (separadas por comas)",
        help_text="Columnas del CSV que se usarán en la fórmula"
    )
    
    formula = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ej: (nacimientos / poblacion) * 1000'}),
        label="Fórmula de Cálculo",
        help_text="Fórmula Python para calcular el indicador"
    )
    
    def __init__(self, *args, **kwargs):
        indicador = kwargs.pop('indicador', None)
        super().__init__(*args, **kwargs)
        
        # Agregar hints sobre tipo_agregacion_total si hay dominios temáticos
        if indicador:
            dominios_suma = []
            dominios_ninguno = []
            
            for dominio in indicador.dominios_desagregacion_tematica.all():
                tipo_agg = getattr(dominio, 'tipo_agregacion_total', 'suma')
                if tipo_agg == 'suma':
                    dominios_suma.append(dominio.nombre)
                elif tipo_agg == 'ninguno':
                    dominios_ninguno.append(dominio.nombre)
            
            hints = []
            
            if dominios_suma:
                hints.append(
                    f'<div style="background: #ecfdf5; border-left: 4px solid #10b981; padding: 10px; margin: 10px 0;">'
                    f'<strong style="color: #059669;">✅ Dominios con SUMA:</strong> '
                    f'{", ".join(dominios_suma)}<br>'
                    f'<small>Los Totales se calcularán sumando desagregaciones. '
                    f'Si necesitas promedios ponderados, usa fórmulas que operen sobre las sumas.</small>'
                    f'</div>'
                )
            
            if dominios_ninguno:
                hints.append(
                    f'<div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 10px; margin: 10px 0;">'
                    f'<strong style="color: #d97706;">⚠️ Dominios con EXTRACCIÓN DIRECTA:</strong> '
                    f'{", ".join(dominios_ninguno)}<br>'
                    f'<small>Los Totales NO se calcularán, se extraerán directamente del CSV. '
                    f'Asegúrate que el CSV incluya columnas "Total" para estos dominios.</small>'
                    f'</div>'
                )
            
            if hints:
                from django.utils.safestring import mark_safe
                current_help = self.fields['formula'].help_text or ''
                self.fields['formula'].help_text = mark_safe(
                    current_help + '<br>' + ''.join(hints)
                )
    
    filtros_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': '{"edad": ">= 18", "sexo": "F"}'}),
        required=False,
        label="Filtros (JSON)",
        help_text="Filtros opcionales en formato JSON"
    )
    
    orden_desagregaciones = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'comuna, sexo, grupo_edad'}),
        required=False,
        label="Orden de Desagregaciones (separadas por comas)",
        help_text="Orden en que se aplicarán las desagregaciones"
    )
    
    def clean_filtros_json(self):
        filtros = self.cleaned_data.get('filtros_json', '').strip()
        if filtros:
            try:
                json.loads(filtros)
            except json.JSONDecodeError:
                raise ValidationError("El formato JSON de los filtros no es válido")
        return filtros


class FormDiagnostico(forms.Form):
    """Paso 8A/9C: Ejecutar diagnóstico y mostrar resultado"""
    
    # Este formulario no tiene campos editables
    # Solo muestra el resultado del diagnóstico
    confirmar_procesamiento = forms.BooleanField(
        required=True,
        label="He revisado el diagnóstico y deseo procesar",
        widget=forms.CheckboxInput(attrs={'class': 'confirm-checkbox'})
    )
    
    # Campo oculto para almacenar la salida del diagnóstico
    diagnostic_output = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )




class FormConfirmacionB(forms.Form):
    """Paso 7B: Confirmación antes de importar"""
    
    eliminar_datos_existentes = forms.BooleanField(
        initial=False,
        required=False,
        label="Eliminar datos existentes del indicador antes de importar",
        help_text="⚠️ Cuidado: esto eliminará todos los datos actuales"
    )
    
    confirmar_importacion = forms.BooleanField(
        required=True,
        label="Confirmo que deseo importar los datos",
        widget=forms.CheckboxInput(attrs={'class': 'confirm-checkbox'})
    )


# ============================================================================
# FLUJO C: COMPLETO (MICRODATA + SERIE)
# ============================================================================

class FormPreviewAmbos(forms.Form):
    """Paso 2C: Preview de ambos archivos con Univer.js"""
    
    confirmar_preview = forms.BooleanField(
        required=True,
        label="He revisado ambos archivos y deseo continuar",
        widget=forms.CheckboxInput(attrs={'class': 'confirm-checkbox'})
    )


class FormValidarSerie(forms.Form):
    """Paso 10C: Validar datos procesados con serie original usando Univer.js"""
    
    # Este formulario no tiene campos editables
    # Solo muestra ambos datasets en tabs con Univer.js para comparación visual
    confirmar_validacion = forms.BooleanField(
        required=True,
        label="He comparado los datos y deseo continuar",
        widget=forms.CheckboxInput(attrs={'class': 'confirm-checkbox'})
    )


# ============================================================================
# FLUJO D: ACTUALIZAR EXISTENTE
# ============================================================================

class FormSeleccionarIndicador(forms.Form):
    """Paso 2D: Seleccionar indicador a actualizar"""
    
    indicador = forms.ModelChoiceField(
        queryset=Indicador.objects.all(),
        label="Seleccionar Indicador",
        widget=forms.Select(attrs={'class': 'indicador-select'})
    )
    
    # Filtros de búsqueda
    buscar_nombre = forms.CharField(
        max_length=255,
        required=False,
        label="Buscar por nombre",
        widget=forms.TextInput(attrs={'placeholder': 'Buscar...'})
    )


class FormSeleccionarCarga(forms.Form):
    """Paso 3D: Seleccionar nueva carga para actualizar"""
    
    TIPO_CARGA_CHOICES = [
        ('serie', 'Serie de Datos'),
        ('conjunto_datos', 'Conjunto de Datos'),
    ]
    
    tipo_carga = forms.ChoiceField(
        label="Tipo de Carga",
        choices=TIPO_CARGA_CHOICES,
        widget=forms.RadioSelect
    )
    
    carga_serie = forms.ModelChoiceField(
        queryset=CargaSerieIndicador.objects.filter(estado__in=['pendiente', 'aprobado']),
        required=False,
        label="Seleccionar Carga de Serie"
    )
    
    carga_conjunto_datos = forms.ModelChoiceField(
        queryset=CargaConjuntoDatos.objects.filter(estado__in=['pendiente', 'aprobado']),
        required=False,
        label="Seleccionar Carga de conjunto_datos"
    )


class FormCompararMetadata(forms.Form):
    """Paso 4D: Comparar metadata actual vs nueva"""
    
    # Este formulario muestra un diff viewer
    # Los campos seleccionables indican qué actualizar
    actualizar_nombre = forms.BooleanField(required=False, label="Actualizar Nombre")
    actualizar_descripcion = forms.BooleanField(required=False, label="Actualizar Descripción")
    actualizar_formula = forms.BooleanField(required=False, label="Actualizar Fórmula")
    # ... más campos según necesidad


class FormConfirmarCambios(forms.Form):
    """Paso 5D: Confirmar cambios a realizar"""
    
    ACCION_DATOS_CHOICES = [
        ('mantener', 'Mantener datos existentes'),
        ('reemplazar', 'Eliminar y recargar todos los datos'),
        ('agregar', 'Agregar solo datos nuevos'),
    ]
    
    accion_datos = forms.ChoiceField(
        label="¿Qué hacer con los datos existentes?",
        choices=ACCION_DATOS_CHOICES,
        widget=forms.RadioSelect,
        initial='mantener'
    )
    
    confirmar_actualizacion = forms.BooleanField(
        required=True,
        label="Confirmo que deseo actualizar el indicador",
        widget=forms.CheckboxInput(attrs={'class': 'confirm-checkbox'})
    )


# ============================================================================
# PASO FINAL: CONFIGURACIÓN DE GRÁFICOS (Común a flujos A, B, C)
# ============================================================================

class FormGraficos(forms.Form):
    """Paso final: Configurar gráficos (opcional)"""
    
    crear_graficos = forms.BooleanField(
        initial=False,
        required=False,
        label="¿Deseas crear gráficos ahora?",
        help_text="Puedes crear gráficos más tarde desde el admin"
    )
    
    # Si decide crear gráficos, se mostrarán campos adicionales
    # (Implementación completa en siguiente paso con formsets)


# ============================================================================
# PASO FINAL: CONFIRMACIÓN (Común a todos los flujos)
# ============================================================================

class FormConfirmacion(forms.Form):
    """Paso final: Confirmación general antes de ejecutar"""
    
    confirmar_final = forms.BooleanField(
        required=True,
        label="Confirmo que toda la información es correcta y deseo finalizar",
        widget=forms.CheckboxInput(attrs={'class': 'confirm-checkbox-final'})
    )
