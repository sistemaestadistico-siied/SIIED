"""
Formulario simplificado para creación de gráficos desde los módulos
de recolección y validación.

Captura solo la información básica que luego el admin complementará
con la configuración avanzada (márgenes, rangos, desagregaciones, etc.)
"""

from django import forms
from .models import Grafico, Indicador


class GraficoSimplificadoForm(forms.ModelForm):
    """
    Formulario con los campos esenciales para pre-configurar un gráfico.
    El admin completará los detalles avanzados desde el panel de administración.
    """

    class Meta:
        model = Grafico
        fields = [
            'nombre',
            'tipo_grafico',
            'eje_x_titulo',
            'eje_y_titulo',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
                'placeholder': 'Ej: Evolución anual del indicador',
            }),
            'tipo_grafico': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
            }),
            'eje_x_titulo': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
                'placeholder': 'Ej: Año, Periodo, Mes',
            }),
            'eje_y_titulo': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition',
                'placeholder': 'Ej: Porcentaje (%), Tasa por 100.000 hab., Número',
            }),
        }
        labels = {
            'nombre': 'Nombre del gráfico',
            'tipo_grafico': 'Tipo de gráfico',
            'eje_x_titulo': 'Título del eje X (horizontal)',
            'eje_y_titulo': 'Unidad de medida / Título del eje Y (vertical)',
        }
        help_texts = {
            'nombre': 'Un nombre descriptivo para identificar este gráfico.',
            'tipo_grafico': 'Seleccione el tipo de visualización más adecuado para los datos.',
            'eje_x_titulo': 'Generalmente es "Año" o "Periodo".',
            'eje_y_titulo': 'La unidad en que se expresan los valores (ej: %, tasa, número, pesos).',
        }

    def __init__(self, *args, indicador=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._indicador = indicador

        # Pre-llenar nombre si tenemos indicador
        if indicador and not self.instance.pk:
            self.initial.setdefault('nombre', indicador.nombre)
            # Pre-llenar eje_y con unidad_medida del indicador si existe
            if indicador.unidad_medida:
                self.initial.setdefault('eje_y_titulo', indicador.unidad_medida)
            # Pre-llenar eje_x con "Año" por defecto
            self.initial.setdefault('eje_x_titulo', 'Año')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self._indicador:
            instance.indicador = self._indicador
        # Configurar defaults razonables para campos avanzados
        instance.activo = True
        instance.mostrar_leyenda = True
        instance.mostrar_cuadricula = True
        instance.begin_at_zero = True
        if commit:
            instance.save()
        return instance
