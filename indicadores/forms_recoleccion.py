"""
Formularios para el módulo de recolección.
"""

from django import forms
from .models import CargaMasivaSerie, Grafico


class CargarMasivaForm(forms.ModelForm):
    """
    Formulario para cargar archivos maestros con datos y/o metadata de múltiples indicadores.
    Muestra/oculta campos de archivo según el tipo de carga seleccionado.
    """
    class Meta:
        model = CargaMasivaSerie
        fields = ['tipo_carga', 'archivo_maestro_datos', 'archivo_maestro_metadata']
        widgets = {
            'tipo_carga': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
                'id': 'id_tipo_carga',
            }),
            'archivo_maestro_datos': forms.ClearableFileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
                'accept': '.xlsx,.xls,.csv',
            }),
            'archivo_maestro_metadata': forms.ClearableFileInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
                'accept': '.xlsx,.xls,.csv',
            }),
        }
        labels = {
            'tipo_carga': '¿Qué desea cargar?',
            'archivo_maestro_datos': 'Archivo maestro de datos',
            'archivo_maestro_metadata': 'Archivo maestro de metadata',
        }
        help_texts = {
            'tipo_carga': 'Seleccione si desea cargar solo datos, solo metadata o ambos.',
            'archivo_maestro_datos': 'Excel o CSV con columna codigo_indicador y los datos de serie (una fila por dato).',
            'archivo_maestro_metadata': 'Excel o CSV con columna codigo_indicador y los campos de metadata (una fila por indicador).',
        }

    def clean(self):
        cleaned_data = super().clean()
        tipo_carga = cleaned_data.get('tipo_carga')
        archivo_datos = cleaned_data.get('archivo_maestro_datos')
        archivo_metadata = cleaned_data.get('archivo_maestro_metadata')

        if tipo_carga == 'datos' and not archivo_datos:
            self.add_error('archivo_maestro_datos', 'Debe subir el archivo maestro de datos.')
        if tipo_carga == 'metadata' and not archivo_metadata:
            self.add_error('archivo_maestro_metadata', 'Debe subir el archivo maestro de metadata.')
        if tipo_carga == 'ambos':
            if not archivo_datos:
                self.add_error('archivo_maestro_datos', 'Debe subir el archivo maestro de datos.')
            if not archivo_metadata:
                self.add_error('archivo_maestro_metadata', 'Debe subir el archivo maestro de metadata.')

        # Validar extensiones de archivo
        valid_extensions = ('.xlsx', '.xls', '.csv')
        if archivo_datos and not archivo_datos.name.lower().endswith(valid_extensions):
            self.add_error('archivo_maestro_datos', 'El archivo debe ser Excel (.xlsx, .xls) o CSV (.csv).')
        if archivo_metadata and not archivo_metadata.name.lower().endswith(valid_extensions):
            self.add_error('archivo_maestro_metadata', 'El archivo debe ser Excel (.xlsx, .xls) o CSV (.csv).')

        return cleaned_data


class GraficoMasivaForm(forms.Form):
    """
    Formulario para configurar el gráfico de un indicador durante la carga masiva.
    Este formulario se usa como parte de un formset en la vista de configuración masiva.
    """
    indicador_id = forms.IntegerField(widget=forms.HiddenInput)
    nombre = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
            'placeholder': 'Ej: Evolución anual del indicador',
        }),
        label='Nombre del gráfico'
    )
    tipo_grafico = forms.ChoiceField(
        choices=Grafico.TIPO_GRAFICO_CHOICES,
        initial='line',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
        }),
        label='Tipo de gráfico'
    )
    eje_x_titulo = forms.CharField(
        max_length=255,
        required=False,
        initial='Año',
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
            'placeholder': 'Ej: Año, Periodo, Mes',
        }),
        label='Título del eje X (horizontal)'
    )
    eje_y_titulo = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
            'placeholder': 'Ej: Porcentaje (%), Tasa por 100.000 hab.',
        }),
        label='Unidad de medida / Título del eje Y (vertical)'
    )
