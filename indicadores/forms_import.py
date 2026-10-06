"""
Formularios para importación masiva de Indicadores y Datos desde CSV
"""
from django import forms
from django.core.exceptions import ValidationError
import pandas as pd
import io


class ImportarIndicadoresForm(forms.Form):
    """
    Formulario para importar múltiples indicadores desde un archivo CSV
    """
    archivo_csv = forms.FileField(
        label="Archivo CSV",
        help_text="Archivo CSV con los indicadores a importar. Debe incluir las columnas requeridas.",
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )
    
    eliminar_existentes = forms.BooleanField(
        label="Eliminar indicadores existentes",
        required=False,
        initial=False,
        help_text="⚠️ Si se marca, se eliminarán todos los indicadores existentes antes de importar"
    )
    
    actualizar_existentes = forms.BooleanField(
        label="Actualizar indicadores existentes",
        required=False,
        initial=True,
        help_text="Si un indicador con el mismo nombre ya existe, se actualizará en lugar de crear uno nuevo"
    )
    
    def clean_archivo_csv(self):
        archivo = self.cleaned_data['archivo_csv']
        
        # Validar que sea un archivo CSV
        if not archivo.name.endswith('.csv'):
            raise ValidationError('El archivo debe ser un CSV (.csv)')
        
        # Intentar leer el archivo
        try:
            # Leer el contenido del archivo
            contenido = archivo.read()
            archivo.seek(0)  # Volver al inicio para que se pueda leer después
            
            # Intentar parsear como CSV
            df = pd.read_csv(io.BytesIO(contenido))
            
            # Validar columnas requeridas
            columnas_requeridas = ['nombre', 'subtema']
            columnas_faltantes = [col for col in columnas_requeridas if col not in df.columns]
            
            if columnas_faltantes:
                raise ValidationError(
                    f'Faltan las siguientes columnas requeridas: {", ".join(columnas_faltantes)}'
                )
            
            # Validar que haya al menos una fila
            if len(df) == 0:
                raise ValidationError('El archivo CSV está vacío')
            
            # Validar que no haya filas completamente vacías
            filas_vacias = df[df['nombre'].isna()].index.tolist()
            if filas_vacias:
                raise ValidationError(
                    f'Hay filas sin nombre en las posiciones: {", ".join(map(str, [i+2 for i in filas_vacias]))}'
                )
            
        except pd.errors.EmptyDataError:
            raise ValidationError('El archivo CSV está vacío')
        except pd.errors.ParserError as e:
            raise ValidationError(f'Error al parsear el CSV: {str(e)}')
        except Exception as e:
            raise ValidationError(f'Error al procesar el archivo: {str(e)}')
        
        return archivo


class ImportarDatosForm(forms.Form):
    """
    Formulario para importar múltiples datos desde un archivo CSV
    """
    archivo_csv = forms.FileField(
        label="Archivo CSV",
        help_text="Archivo CSV con los datos a importar. Debe incluir las columnas requeridas.",
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )
    
    indicador = forms.ModelChoiceField(
        queryset=None,  # Se establecerá en __init__
        label="Indicador",
        required=False,
        help_text="Si se especifica, todos los datos se asociarán a este indicador. Si no, debe haber una columna 'indicador' en el CSV."
    )
    
    eliminar_datos_previos = forms.BooleanField(
        label="Eliminar datos previos del indicador",
        required=False,
        initial=False,
        help_text="⚠️ Si se marca, se eliminarán todos los datos existentes del indicador antes de importar"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Indicador
        self.fields['indicador'].queryset = Indicador.objects.filter(activo=True).order_by('nombre')
    
    def clean_archivo_csv(self):
        archivo = self.cleaned_data['archivo_csv']
        
        # Validar que sea un archivo CSV
        if not archivo.name.endswith('.csv'):
            raise ValidationError('El archivo debe ser un CSV (.csv)')
        
        # Intentar leer el archivo
        try:
            contenido = archivo.read()
            archivo.seek(0)
            
            df = pd.read_csv(io.BytesIO(contenido))
            
            # Validar columnas requeridas
            columnas_requeridas = ['fecha_dato', 'valor_dato']
            columnas_faltantes = [col for col in columnas_requeridas if col not in df.columns]
            
            if columnas_faltantes:
                raise ValidationError(
                    f'Faltan las siguientes columnas requeridas: {", ".join(columnas_faltantes)}'
                )
            
            # Validar que haya al menos una fila
            if len(df) == 0:
                raise ValidationError('El archivo CSV está vacío')
            
        except pd.errors.EmptyDataError:
            raise ValidationError('El archivo CSV está vacío')
        except pd.errors.ParserError as e:
            raise ValidationError(f'Error al parsear el CSV: {str(e)}')
        except Exception as e:
            raise ValidationError(f'Error al procesar el archivo: {str(e)}')
        
        return archivo
    
    def clean(self):
        cleaned_data = super().clean()
        indicador = cleaned_data.get('indicador')
        archivo_csv = cleaned_data.get('archivo_csv')
        
        # Si no se especifica indicador, el CSV debe tener una columna 'indicador'
        if not indicador and archivo_csv:
            try:
                contenido = archivo_csv.read()
                archivo_csv.seek(0)
                df = pd.read_csv(io.BytesIO(contenido))
                
                if 'indicador' not in df.columns:
                    raise ValidationError(
                        'Debe especificar un indicador o incluir una columna "indicador" en el CSV'
                    )
            except:
                pass
        
        return cleaned_data
