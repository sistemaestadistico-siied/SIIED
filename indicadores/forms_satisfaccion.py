from django import forms
from .models import RespuestaSatisfaccionCompleta, Organismo


class RespuestaSatisfaccionCompletaForm(forms.ModelForm):
    """
    Formulario completo de satisfacción ciudadana
    """
    
    class Meta:
        model = RespuestaSatisfaccionCompleta
        fields = [
            'fecha_respuesta_solicitud',
            'utilidad_tiempo_respuesta',
            'utilidad_claridad',
            'relevancia_periodicidad',
            'relevancia_concordancia',
            'accesibilidad_canal',
            'accesibilidad_formato',
            'razon_insatisfaccion',
        ]
        
        widgets = {
            'fecha_respuesta_solicitud': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                    'required': True
                }
            ),
            'utilidad_tiempo_respuesta': forms.RadioSelect(
                attrs={'class': 'form-check-input'},
                choices=[]
            ),
            'utilidad_claridad': forms.RadioSelect(
                attrs={'class': 'form-check-input'},
                choices=[]
            ),
            'relevancia_periodicidad': forms.RadioSelect(
                attrs={'class': 'form-check-input'},
                choices=[]
            ),
            'relevancia_concordancia': forms.RadioSelect(
                attrs={'class': 'form-check-input'},
                choices=[]
            ),
            'accesibilidad_canal': forms.RadioSelect(
                attrs={'class': 'form-check-input'},
                choices=[]
            ),
            'accesibilidad_formato': forms.RadioSelect(
                attrs={'class': 'form-check-input'},
                choices=[]
            ),
            'razon_insatisfaccion': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 4,
                    'required': False,
                    'disabled': True,
                    'placeholder': 'Este campo se habilitará automáticamente si selecciona 1, 2 o 3 en alguna pregunta'
                }
            ),
        }
        
        labels = {
            'fecha_respuesta_solicitud': 'Fecha en la cual realizó la solicitud de información',
            'utilidad_tiempo_respuesta': 'Tiempo de respuesta al requerimiento de información estadística adecuado, teniendo en cuenta sus necesidades',
            'utilidad_claridad': 'Claridad, precisión y facilidad de uso de la información estadística recibida',
            'relevancia_periodicidad': 'Correspondencia entre la periodicidad de la información estadística entregada y la solicitada',
            'relevancia_concordancia': 'Concordancia entre la solicitud de información estadística realizada y la entregada',
            'accesibilidad_canal': 'Canal utilizado para realizar la solicitud de información estadística. <em>Considere aspectos como facilidad de acceso, rapidez y atención recibida.</em>',
            'accesibilidad_formato': 'Formato en el que se le suministró la información estadística',
            'razon_insatisfaccion': 'Si en los ítems evaluados anteriormente, usted seleccionó Muy Insatisfecho, Insatisfecho o Neutral, por favor, indique la razón principal de su valoración',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Agregar clases CSS a todos los campos de calificación
        calificacion_fields = [
            'utilidad_tiempo_respuesta',
            'utilidad_claridad',
            'relevancia_periodicidad',
            'relevancia_concordancia',
            'accesibilidad_canal',
            'accesibilidad_formato',
        ]
        
        for field_name in calificacion_fields:
            # Hacer el campo OBLIGATORIO para evitar valores None
            self.fields[field_name].required = True
            
            # Obtener las choices del modelo (1-5) sin la opción vacía
            from .models import RespuestaSatisfaccionCompleta
            model_choices = RespuestaSatisfaccionCompleta._meta.get_field(field_name).choices
            
            # Asignar las choices al widget (sin opción vacía)
            self.fields[field_name].widget.choices = model_choices
            
            # NO establecer initial para que no venga preseleccionado
            self.fields[field_name].initial = None
            
            self.fields[field_name].widget.attrs.update({
                'class': 'rating-radio'
            })


class OrganismoForm(forms.ModelForm):
    """
    Formulario para crear/editar organismos
    """
    
    class Meta:
        model = Organismo
        fields = [
            'nombre',
            'codigo',
            'descripcion',
            'activo',
            'email_contacto',
            'responsable',
        ]
        
        widgets = {
            'nombre': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej: Secretaría de Educación'
                }
            ),
            'codigo': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej: educacion (sin espacios ni caracteres especiales)'
                }
            ),
            'descripcion': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Descripción breve del organismo'
                }
            ),
            'activo': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}
            ),
            'email_contacto': forms.EmailInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'correo@cali.gov.co'
                }
            ),
            'responsable': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nombre del responsable'
                }
            ),
        }
        
        labels = {
            'nombre': 'Nombre del organismo',
            'codigo': 'Código único',
            'descripcion': 'Descripción',
            'activo': 'Activo',
            'email_contacto': 'Email de contacto',
            'responsable': 'Responsable',
        }
        
        help_texts = {
            'codigo': 'Este código se usará en la URL. Use solo letras minúsculas, números y guiones.',
            'activo': 'Si está desmarcado, no se podrán registrar nuevas calificaciones.',
        }
