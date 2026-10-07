from django import forms
from django.forms import inlineformset_factory

from .models import Organismo, Suborganismo
from .models_taller import (
    FuenteRequerida,
    InscripcionTaller as Inscripcion,
    OpcionTaller as Opcion,
    RetoAnalisis,
)
from .models_catalogo import (
    EvaluacionSeguridad,
    FuenteDatos,
    FuenteOrigen,
    VariableFuente,
)


class BaseWizardForm(forms.ModelForm):
    """Aplica widgets consistentes: checkboxes para M2M, radios para choices."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field, forms.ModelMultipleChoiceField):
                field.widget = forms.CheckboxSelectMultiple()
                if hasattr(field.queryset.model, 'activa'):
                    field.queryset = field.queryset.filter(activa=True)
            elif isinstance(field, forms.ModelChoiceField):
                field.widget = forms.RadioSelect()
                if hasattr(field.queryset.model, 'activa'):
                    field.queryset = field.queryset.filter(activa=True)
                field.empty_label = None
            elif isinstance(field, forms.TypedChoiceField) or (
                isinstance(field, forms.ChoiceField) and not isinstance(field, forms.ModelChoiceField)
            ):
                choices = [c for c in field.choices if c[0] != '']
                field.widget = forms.RadioSelect(choices=choices)
                field.choices = choices
                field.required = field.required
            elif isinstance(field, forms.CharField) and isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault('rows', 3)


# ---------------------------------------------------------------------------
# Paso 1 · Identificación
# ---------------------------------------------------------------------------

class IdentificacionForm(BaseWizardForm):
    class Meta:
        model = Inscripcion
        fields = ['organismo', 'suborganismo', 'equipo_responsable',
                  'nombre_completo', 'correo', 'telefono', 'ficha_inicial']
        widgets = {
            'organismo': forms.Select(attrs={'id': 'id_organismo'}),
            'suborganismo': forms.Select(attrs={'id': 'id_suborganismo'}),
            'ficha_inicial': forms.RadioSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['organismo'].widget = forms.Select(attrs={'id': 'id_organismo'})
        self.fields['organismo'].queryset = Organismo.objects.filter(activo=True).order_by('nombre')
        self.fields['organismo'].empty_label = '— Seleccione un organismo —'
        self.fields['suborganismo'].widget = forms.Select(attrs={'id': 'id_suborganismo'})
        self.fields['suborganismo'].empty_label = '— Seleccione un suborganismo —'
        self.fields['ficha_inicial'].label = '¿Por qué ficha desea iniciar?'
        self.fields['ficha_inicial'].help_text = (
            'F1 · Caracterización de datos: describa sus fuentes y conjuntos de datos. '
            'F2 · Reto de análisis: formule directamente un reto de análisis '
            '(podrá caracterizar fuentes después si lo desea).'
        )

        # On POST, use the submitted organismo to populate the queryset so validation passes
        submitted_org = None
        if self.is_bound and self.data.get('organismo'):
            submitted_org = self.data.get('organismo')
        elif self.instance and self.instance.organismo_id:
            submitted_org = self.instance.organismo_id

        if submitted_org:
            self.fields['suborganismo'].queryset = Suborganismo.objects.filter(
                organismo_id=submitted_org, activo=True).order_by('orden', 'nombre')
        else:
            self.fields['suborganismo'].queryset = Suborganismo.objects.none()


# ---------------------------------------------------------------------------
# F1 · Caracterización de datos
# ---------------------------------------------------------------------------

class FuenteGeneralForm(BaseWizardForm):
    FECHA_MIN = '2026-08-10'
    FECHA_MAX = '2026-09-14'

    class Meta:
        model = FuenteDatos
        fields = ['nombre', 'descripcion', 'relaciones', 'relacion_otra',
                  'instrumentos', 'instrumento_otro', 'mecanismos', 'mecanismo_otro',
                  'fecha_inicio']
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'min': '2026-08-10', 'max': '2026-09-14'}, format='%Y-%m-%d'),
        }
        labels = {
            'nombre': 'Nombre de la fuente de datos o conjunto de datos',
            'descripcion': 'Describa brevemente el contenido de la fuente de datos o conjunto de datos',
            'relaciones': 'Describa la opción que mejor defina la relación del organismo con la fuente de los datos',
            'relacion_otra': '¿Otra, cuál?',
            'instrumentos': '¿Mediante qué instrumento o proceso se recolectan los datos?',
            'instrumento_otro': 'Otro, ¿cuál?',
            'mecanismos': '¿Bajo qué mecanismo se consolidan los datos?',
            'mecanismo_otro': 'Otro, ¿cuál?',
            'fecha_inicio': '¿En qué fecha comenzó a utilizarse esta fuente para alimentar el conjunto de datos?',
        }
        help_texts = {
            'nombre': 'Indique el nombre del formulario, registro, sistema, archivo u otra fuente.',
            'descripcion': 'Ej. caracterización poblacional, registro de ayudas, seguimiento a viviendas, gestión de riesgos.',
            'relaciones': 'Selección múltiple.',
            'fecha_inicio': 'Seleccione una fecha entre el 10 de agosto y el 14 de septiembre de 2026.',
        }

    def clean_fecha_inicio(self):
        from datetime import date
        fecha = self.cleaned_data.get('fecha_inicio')
        if fecha:
            minimo = date(2026, 8, 10)
            maximo = date(2026, 9, 14)
            if fecha < minimo or fecha > maximo:
                raise forms.ValidationError(
                    'La fecha debe estar entre el 10 de agosto y el 14 de septiembre de 2026.')
        return fecha


FuenteDatosFormSet = inlineformset_factory(
    Inscripcion, FuenteDatos,
    form=FuenteGeneralForm,
    fields=['nombre', 'descripcion', 'relaciones', 'relacion_otra',
            'instrumentos', 'instrumento_otro', 'mecanismos', 'mecanismo_otro',
            'fecha_inicio'],
    extra=1, max_num=10, can_delete=False,
)


class FuenteActualizacionForm(BaseWizardForm):
    class Meta:
        model = FuenteDatos
        fields = ['fecha_actualizacion', 'periodicidades', 'periodicidad_otra',
                  'desagregaciones', 'desagregacion_otra',
                  'num_registros', 'num_registros_fecha', 'num_registros_desconocido',
                  'tiene_diccionario', 'diccionario_ubicacion']
        widgets = {
            'fecha_actualizacion': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'num_registros_fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }
        labels = {
            'fecha_actualizacion': '¿Cuál es la fecha de última actualización de los datos?',
            'desagregaciones': 'Indique el nivel de desagregación geográfica de los datos (selección múltiple)',
            'desagregacion_otra': 'Otro, ¿cuál?',
            'periodicidad_otra': 'Otra, ¿cuál?',
            'num_registros': '¿Cuántos registros contiene aproximadamente? (número)',
            'num_registros_fecha': 'Fecha a la que corresponde esa cantidad',
            'tiene_diccionario': '¿Existe un diccionario de variables, manual u otro documento que explique el conjunto de datos?',
            'diccionario_ubicacion': 'Si existe, indique su nombre o ubicación institucional',
        }

    def clean(self):
        cleaned = super().clean()
        num = cleaned.get('num_registros')
        desconocido = cleaned.get('num_registros_desconocido')
        if num and desconocido:
            raise forms.ValidationError(
                'Si indica una cantidad de registros, no marque "No se conoce la cantidad de registros".')
        tiene_dict = cleaned.get('tiene_diccionario')
        ubicacion = (cleaned.get('diccionario_ubicacion') or '').strip()
        if tiene_dict == 'si' and not ubicacion:
            self.add_error('diccionario_ubicacion',
                           'Cuando responde "Sí", debe indicar el nombre o ubicación del diccionario.')
        if tiene_dict == 'no':
            cleaned['diccionario_ubicacion'] = ''
        return cleaned


class FuenteRolForm(BaseWizardForm):
    class Meta:
        model = FuenteDatos
        fields = ['rol']
        labels = {'rol': 'Seleccione la opción que mejor describa la relación del organismo con esta fuente de datos'}

    def clean_rol(self):
        rol = self.cleaned_data.get('rol')
        if not rol:
            raise forms.ValidationError('Seleccione el rol del organismo frente a la fuente.')
        return rol


class FuenteOrigenForm(forms.ModelForm):
    """Form para fuentes de origen con organismo de alcaldía (select) o entidad externa (text)."""

    TIPO_CHOICES = [('alcaldia', 'Organismo de alcaldía'), ('externa', 'Entidad externa')]
    tipo_origen = forms.ChoiceField(
        choices=TIPO_CHOICES, widget=forms.RadioSelect(),
        label='Tipo de organismo productor', initial='alcaldia')
    organismo_alcaldia = forms.ModelChoiceField(
        queryset=Organismo.objects.all(), required=False,
        label='Organismo de alcaldía', empty_label='— Seleccione —')

    class Meta:
        model = FuenteOrigen
        fields = ['nombre', 'organismo_productor']
        labels = {
            'nombre': 'Nombre de la fuente de origen',
            'organismo_productor': 'Entidad externa (nombre)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['organismo_alcaldia'].widget.attrs.update({'class': 'select-organismo'})
        self.fields['organismo_productor'].required = False
        # Detectar si el valor actual corresponde a un organismo de alcaldía
        if self.instance and self.instance.organismo_productor:
            org = Organismo.objects.filter(nombre=self.instance.organismo_productor).first()
            if org:
                self.fields['tipo_origen'].initial = 'alcaldia'
                self.fields['organismo_alcaldia'].initial = org
            else:
                self.fields['tipo_origen'].initial = 'externa'

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo_origen')
        if tipo == 'alcaldia':
            org = cleaned.get('organismo_alcaldia')
            if org:
                cleaned['organismo_productor'] = org.nombre
            else:
                self.add_error('organismo_alcaldia',
                               'Seleccione un organismo de alcaldía.')
        elif tipo == 'externa':
            if not cleaned.get('organismo_productor'):
                self.add_error('organismo_productor',
                               'Ingrese el nombre de la entidad externa.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        tipo = self.cleaned_data.get('tipo_origen')
        if tipo == 'alcaldia':
            org = self.cleaned_data.get('organismo_alcaldia')
            if org:
                instance.organismo_productor = org.nombre
        if commit:
            instance.save()
        return instance


FuenteOrigenFormSet = inlineformset_factory(
    FuenteDatos, FuenteOrigen,
    form=FuenteOrigenForm,
    fields=['nombre', 'organismo_productor'],
    extra=1, max_num=5, can_delete=True,
)


class FuentePropositoForm(BaseWizardForm):
    class Meta:
        model = FuenteDatos
        fields = ['decisiones_apoya', 'unidades_analisis', 'unidad_analisis_otra']
        widgets = {'decisiones_apoya': forms.Textarea(attrs={'rows': 4})}
        labels = {
            'decisiones_apoya': '¿Qué decisiones institucionales apoya?',
            'unidades_analisis': '¿Cuál es la unidad de análisis principal?',
            'unidad_analisis_otra': 'Otro, ¿cuál?',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Reemplazar M2M (checkboxes) por selección única (radio)
        self.fields['unidades_analisis'] = forms.ModelChoiceField(
            queryset=Opcion.objects.filter(
                categoria=Opcion.Categoria.UNIDAD_ANALISIS, activa=True),
            widget=forms.RadioSelect(),
            required=False, empty_label=None,
            label='¿Cuál es la unidad de análisis principal?',
        )
        # Cargar valor inicial desde el M2M existente
        if self.instance and self.instance.pk:
            existing = self.instance.unidades_analisis.first()
            if existing:
                self.fields['unidades_analisis'].initial = existing

    def save(self, commit=True):
        instance = super().save(commit=False)
        # unidades_analisis se reemplazó por ModelChoiceField (radio): lo sacamos
        # de cleaned_data para que save_m2m() no haga .set() con un valor único
        unidad = self.cleaned_data.pop('unidades_analisis', None)
        if commit:
            instance.save()
        if unidad:
            instance.unidades_analisis.set([unidad])
        else:
            instance.unidades_analisis.clear()
        return instance


VariableFuenteFormSet = inlineformset_factory(
    FuenteDatos, VariableFuente,
    fields=['nombre', 'tipo', 'descripcion', 'es_identificador'],
    extra=10, max_num=10, validate_max=True, can_delete=False,
)

VariableFuenteCompletoFormSet = inlineformset_factory(
    FuenteDatos, VariableFuente,
    fields=['nombre', 'tipo', 'descripcion', 'es_identificador'],
    extra=0, max_num=1000, can_delete=True,
)


class FuenteDiccionarioForm(BaseWizardForm):
    """Formulario para subir el archivo Excel del diccionario de datos."""

    class Meta:
        model = FuenteDatos
        fields = ['archivo_diccionario']
        widgets = {
            'archivo_diccionario': forms.FileInput(attrs={'accept': '.xlsx,.xls'}),
        }

    def clean_archivo_diccionario(self):
        archivo = self.cleaned_data.get('archivo_diccionario')
        if archivo:
            nombre = archivo.name.lower()
            if not (nombre.endswith('.xlsx') or nombre.endswith('.xls')):
                raise forms.ValidationError('Solo se permiten archivos Excel (.xlsx o .xls).')
        return archivo


class FuenteCalidadForm(BaseWizardForm):
    class Meta:
        model = FuenteDatos
        fields = ['georreferenciacion', 'niveles_georref', 'nivel_georref_otro',
                  'problemas_calidad', 'problema_calidad_otro',
                  'tiene_validacion', 'validacion_descripcion']
        widgets = {'validacion_descripcion': forms.Textarea(attrs={'rows': 3})}
        labels = {
            'problemas_calidad': 'Principales problemas de calidad identificados (marque los que apliquen)',
            'problema_calidad_otro': 'Otro, ¿cuál?',
            'nivel_georref_otro': 'Otro, ¿cuál?',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # niveles_georref: selección única (radio) en vez de M2M (checkboxes)
        self.fields['niveles_georref'] = forms.ModelChoiceField(
            queryset=Opcion.objects.filter(
                categoria=Opcion.Categoria.NIVEL_GEORREF, activa=True),
            widget=forms.RadioSelect(),
            required=False, empty_label=None,
            label='Nivel de georreferenciación',
        )
        if self.instance and self.instance.pk:
            existing = self.instance.niveles_georref.first()
            if existing:
                self.fields['niveles_georref'].initial = existing

    def save(self, commit=True):
        instance = super().save(commit=False)
        # niveles_georref se reemplazó por ModelChoiceField (radio): lo sacamos
        # de cleaned_data para que save_m2m() no haga .set() con un valor único
        nivel = self.cleaned_data.pop('niveles_georref', None)
        if commit:
            instance.save()
            self.save_m2m()  # persiste problemas_calidad y demás M2M
        if nivel:
            instance.niveles_georref.set([nivel])
        else:
            instance.niveles_georref.clear()
        return instance

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('tiene_validacion') == 'no':
            cleaned['validacion_descripcion'] = ''
        return cleaned


# ---------------------------------------------------------------------------
# F2 · Reto de análisis
# ---------------------------------------------------------------------------

class RetoDefinicionForm(BaseWizardForm):
    class Meta:
        model = RetoAnalisis
        fields = ['nombre', 'analisis_propuesto', 'resultado_esperado', 'decision_apoya']
        widgets = {
            'analisis_propuesto': forms.Textarea(attrs={'rows': 3}),
            'resultado_esperado': forms.Textarea(attrs={'rows': 3}),
            'decision_apoya': forms.Textarea(attrs={'rows': 3}),
        }


class RetoUnidadesForm(BaseWizardForm):
    class Meta:
        model = RetoAnalisis
        fields = ['unidad_principal', 'unidad_principal_otra',
                  'unidades_relacionar', 'unidades_relacionar_otra',
                  'vinculo_unidades', 'desagregaciones', 'desagregacion_otra']
        widgets = {'vinculo_unidades': forms.Textarea(attrs={'rows': 2})}
        labels = {
            'unidad_principal': '1.5 ¿Qué población, objeto o unidad de análisis se observará? Seleccione la unidad principal de análisis',
            'unidad_principal_otra': 'Otro, ¿cuál?',
            'unidades_relacionar': 'Seleccione las unidades que desea relacionar',
            'unidades_relacionar_otra': 'Otro, ¿cuál?',
            'desagregaciones': '1.6 ¿Cuál es el nivel de desagregación geográfica del análisis de información?',
            'desagregacion_otra': 'Otro, ¿cuál?',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # desagregaciones: selección única (radio) en vez de M2M (checkboxes)
        self.fields['desagregaciones'] = forms.ModelChoiceField(
            queryset=Opcion.objects.filter(
                categoria=Opcion.Categoria.DESAGREGACION, activa=True),
            widget=forms.RadioSelect(),
            required=False, empty_label=None,
            label='1.6 ¿Cuál es el nivel de desagregación geográfica del análisis de información?',
        )
        if self.instance and self.instance.pk:
            existing = self.instance.desagregaciones.first()
            if existing:
                self.fields['desagregaciones'].initial = existing

    def save(self, commit=True):
        instance = super().save(commit=False)
        # desagregaciones se reemplazó por ModelChoiceField (radio): lo sacamos
        # de cleaned_data para que save_m2m() no haga .set() con un valor único
        desag = self.cleaned_data.pop('desagregaciones', None)
        if commit:
            instance.save()
            self.save_m2m()  # persiste unidades_relacionar y demás M2M
        if desag:
            instance.desagregaciones.set([desag])
        else:
            instance.desagregaciones.clear()
        return instance


FuenteRequeridaFormSet = inlineformset_factory(
    RetoAnalisis, FuenteRequerida,
    fields=['nombre', 'organismo', 'variables', 'llave_relacion'],
    extra=1, max_num=3, validate_max=True, can_delete=True,
    widgets={
        'variables': forms.Textarea(attrs={'rows': 2}),
        'llave_relacion': forms.Textarea(attrs={'rows': 2}),
    },
)


class CollapsibleCheckboxWidget(forms.CheckboxSelectMultiple):
    """CheckboxSelectMultiple pero colapsable: renderiza dentro de <details>
    para que el usuario despliegue cada grupo manualmente."""

    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.safestring import mark_safe
        from django.utils.encoding import force_str
        import json

        # Generar el HTML de los checkboxes como lo haría CheckboxSelectMultiple
        checkbox_html = super().render(name, value, attrs, renderer)

        # Contar seleccionados para mostrar en el resumen
        selected_values = []
        if value:
            selected_values = [force_str(v) for v in value] if not isinstance(value, str) else [value]
        count = len(selected_values)

        summary = f'{count} variable(s) seleccionada(s)' if count else 'Sin variables seleccionadas — clic para desplegar'

        html = f'''<details class="collapsible-variables">
  <summary class="collapsible-summary">{summary}</summary>
  <div class="collapsible-content">
    {checkbox_html}
  </div>
</details>'''
        return mark_safe(html)


class RetoTratamientoForm(BaseWizardForm):
    class Meta:
        model = RetoAnalisis
        fields = ['tratamientos', 'tratamiento_otro',
                  'resultados_mvp', 'resultado_mvp_otro',
                  'capacidades_sipdi', 'capacidad_sipdi_otra',
                  'variables_enriquecer_otro',
                  'usuario_resultado',
                  'enfoques_diferenciales', 'enfoque_diferencial_otro']
        widgets = {
            'usuario_resultado': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'tratamientos': '1.10 ¿Qué tratamiento o proceso analítico se aplicará a los datos?',
            'tratamiento_otro': 'Otro, ¿cuál?',
            'resultados_mvp': '1.11 ¿Cuál es el resultado mínimo viable del análisis?',
            'resultado_mvp_otro': 'Otro, ¿cuál?',
            'capacidades_sipdi': '1.12 ¿Qué capacidad del SIPDI podría utilizarse? ¿Qué tipo de operación se requiere con esta fuente? (marque todas las que apliquen)',
            'capacidad_sipdi_otra': 'Otro, ¿cuál?',
            'variables_enriquecer_otro': '1.13 · 5. Otros, ¿cuál?',
            'usuario_resultado': '1.14 ¿Qué organismos utilizarán el resultado?',
            'enfoque_diferencial_otro': 'Otro, ¿cuál?',
        }
        help_texts = {
            'tratamientos': 'Marque uno o varios procesos según el análisis propuesto. Inicie por la integración y calidad de datos cuando sea necesario. Seleccione técnicas avanzadas únicamente cuando la disponibilidad, calidad, cobertura y estructura de los datos permitan su aplicación.',
            'resultados_mvp': 'Describa el procedimiento en orden: integración, depuración, cruce, cálculo, análisis, visualización o recomendación.',
            'capacidades_sipdi': 'Seleccione la operación que podría apoyar el análisis. La selección queda sujeta a la validación técnica, funcional y de seguridad.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # variables_enriquecer: 4 grupos técnicos de variables del catálogo SIPDI
        from .catalogo_datalake import get_bases
        GRUPOS = [
            ('1', '1. Información de registro, fuente y vinculación institucional'),
            ('2', '2. Identificación, datos biográficos y características demográficas'),
            ('3', '3. Localización territorial, residencia y canales de contacto'),
            ('4', '4. Condiciones socioeconómicas, enfoques diferenciales, salud y vulnerabilidad'),
        ]
        # Variables prioritarias por grupo (selección curada para el taller SIPDI)
        VARIABLES_PRIORITARIAS = {
            '1': ['num_ficha', 'nombre_fuente', 'id_vivienda'],
            '2': ['num_doc', 'nombre1', 'apellido1', 'edad', 'sexo', 'estado_civil'],
            '3': ['depto_re', 'munic_re', 'comuna_re', 'barrio_re', 'direc_re', 'estrato_re'],
            '4': ['etnia', 'niv_escola', 'ocupacion', 'salud', 'discapacid', 'clasificacion', 'grupo'],
        }
        # Recolectar variables agrupadas por prefijo de categoría
        vars_por_grupo = {g[0]: [] for g in GRUPOS}
        vistos = {g[0]: set() for g in GRUPOS}
        for base in get_bases():
            for campo in base['campos']:
                cat = campo.get('categoria', '')
                for gnum, _ in GRUPOS:
                    if cat.startswith(gnum + '.'):
                        # Filtrar solo variables prioritarias y deduplicar
                        if campo['nombre'] in VARIABLES_PRIORITARIAS.get(gnum, []):
                            if campo['nombre'] not in vistos[gnum]:
                                etiqueta = campo['nombre']
                                if campo.get('descripcion'):
                                    etiqueta += ' — ' + campo['descripcion']
                                vars_por_grupo[gnum].append((campo['nombre'], etiqueta))
                                vistos[gnum].add(campo['nombre'])
                        break
        # Preservar valores existentes que no estén en el catálogo
        existentes = []
        if self.instance and self.instance.variables_enriquecer:
            existentes = [v.strip() for v in self.instance.variables_enriquecer.split(',') if v.strip()]
        todas_claves = [c[0] for g in vars_por_grupo.values() for c in g]
        for v in existentes:
            if v not in todas_claves:
                vars_por_grupo['4'].append((v, v + ' (personalizado)'))
        # Crear 4 campos de selección múltiple colapsables
        for gnum, glabel in GRUPOS:
            field_name = f'variables_grupo_{gnum}'
            self.fields[field_name] = forms.MultipleChoiceField(
                choices=vars_por_grupo[gnum],
                widget=CollapsibleCheckboxWidget(),
                required=False,
                label=f'1.13 {glabel}',
            )
            if existentes:
                self.fields[field_name].initial = [
                    v for v in existentes if v in [c[0] for c in vars_por_grupo[gnum]]
                ]
        # Mover variables_enriquecer_otro después de los 4 grupos
        if 'variables_enriquecer_otro' in self.fields:
            ot = self.fields.pop('variables_enriquecer_otro')
            self.fields['variables_enriquecer_otro'] = ot
        # usuario_resultado: selección múltiple de organismos existentes
        self.fields['usuario_resultado'] = forms.MultipleChoiceField(
            choices=[(o.nombre, o.nombre) for o in Organismo.objects.all().order_by('nombre')],
            widget=forms.CheckboxSelectMultiple(),
            required=False,
            label='1.14 ¿Qué organismos utilizarán el resultado?',
        )
        # Preservar valores existentes que no estén en la lista de organismos
        if self.instance and self.instance.usuario_resultado:
            existentes_usr = [v.strip() for v in self.instance.usuario_resultado.split(',') if v.strip()]
            claves = [c[0] for c in self.fields['usuario_resultado'].choices]
            for v in existentes_usr:
                if v not in claves:
                    self.fields['usuario_resultado'].choices = list(self.fields['usuario_resultado'].choices) + [(v, v + ' (personalizado)')]
            self.fields['usuario_resultado'].initial = existentes_usr
        # Reordenar campos según numeración de preguntas
        orden = [
            'tratamientos', 'tratamiento_otro',
            'resultados_mvp', 'resultado_mvp_otro',
            'capacidades_sipdi', 'capacidad_sipdi_otra',
            'variables_grupo_1', 'variables_grupo_2',
            'variables_grupo_3', 'variables_grupo_4',
            'variables_enriquecer_otro',
            'usuario_resultado',
            'enfoques_diferenciales', 'enfoque_diferencial_otro',
        ]
        from collections import OrderedDict
        nuevos = OrderedDict()
        for key in orden:
            if key in self.fields:
                nuevos[key] = self.fields[key]
        self.fields = nuevos

    def save(self, commit=True):
        instance = super().save(commit=False)
        variables = []
        for gnum in ['1', '2', '3', '4']:
            variables.extend(self.cleaned_data.get(f'variables_grupo_{gnum}', []))
        instance.variables_enriquecer = ', '.join(variables) if variables else ''
        organismos = self.cleaned_data.get('usuario_resultado')
        instance.usuario_resultado = ', '.join(organismos) if organismos else ''
        if commit:
            instance.save()
            self.save_m2m()  # persiste tratamientos, resultados_mvp, etc.
        return instance


# ---------------------------------------------------------------------------
# F3 · Seguridad y privacidad
# ---------------------------------------------------------------------------

class SeguridadDatosForm(BaseWizardForm):
    class Meta:
        model = EvaluacionSeguridad
        fields = ['contiene_datos_personales', 'variables_identificadoras',
                  'variable_identificadora_otra', 'datos_sensibles', 'dato_sensible_otro',
                  'base_legitima', 'base_legitima_porque']
        labels = {
            'contiene_datos_personales': '¿Este conjunto contiene datos personales que permitan identificar a una persona, directamente o al combinarlos con otra información?',
            'variables_identificadoras': 'Si respondió "Sí", ¿qué variables permiten identificar a las personas?',
            'variable_identificadora_otra': 'Otro, ¿cuál?',
            'datos_sensibles': '¿El conjunto contiene información que requiere especial cuidado? (Conforme Ley 1712 del 2014 y Ley 1581 del 2012)',
            'dato_sensible_otra': 'Otra, ¿cuál?',
        }
        help_texts = {
            'contiene_datos_personales': 'Guía para responder: marque una opción. En variables e información de especial cuidado puede marcar varias.',
        }

    def clean(self):
        cleaned = super().clean()
        bl = cleaned.get('base_legitima')
        bl_porque = cleaned.get('base_legitima_porque', '').strip()
        if bl in ('no', 'no_aplica') and not bl_porque:
            self.add_error('base_legitima_porque',
                           'Cuando la respuesta es "No" o "No aplica", debe explicar por qué.')
        return cleaned


class SeguridadUsoForm(BaseWizardForm):
    class Meta:
        model = EvaluacionSeguridad
        fields = ['proveedor_base_legitima', 'proveedor_base_legitima_porque',
                  'finalidad_especifica', 'finalidad_especifica_porque',
                  'datos_necesarios', 'datos_necesarios_porque',
                  'conservacion_limitada', 'conservacion_limitada_porque',
                  'salvaguardas', 'salvaguardas_porque',
                  'transparencia', 'transparencia_porque']

    _PAREJAS = [
        ('proveedor_base_legitima', 'proveedor_base_legitima_porque'),
        ('finalidad_especifica', 'finalidad_especifica_porque'),
        ('datos_necesarios', 'datos_necesarios_porque'),
        ('conservacion_limitada', 'conservacion_limitada_porque'),
        ('salvaguardas', 'salvaguardas_porque'),
        ('transparencia', 'transparencia_porque'),
    ]

    def clean(self):
        cleaned = super().clean()
        for pregunta, porque in self._PAREJAS:
            resp = cleaned.get(pregunta)
            just = (cleaned.get(porque) or '').strip()
            if resp in ('no', 'no_aplica') and not just:
                self.add_error(porque,
                               'Cuando la respuesta es "No" o "No aplica", debe explicar por qué.')
        return cleaned


class SeguridadDivulgacionForm(BaseWizardForm):
    class Meta:
        model = EvaluacionSeguridad
        fields = ['riesgos_publicacion', 'riesgos_publicacion_porque',
                  'terceros_estandares', 'terceros_estandares_porque',
                  'riesgo_dano', 'riesgo_dano_porque',
                  'medidas_proteccion', 'medida_proteccion_otra']
        labels = {
            'medidas_proteccion': '¿Qué medidas se aplican para proteger la información personal?',
            'medida_proteccion_otra': 'Si marcó «Otras», «Ninguna» o «No aplica», ¿por qué? / ¿cuáles?',
        }
        help_texts = {
            'riesgos_publicacion': 'Marque una opción por pregunta y varias medidas, si aplica. Considere granularidad, agregación y efecto mosaico que pueda volver identificables a personas o grupos.',
        }

    _PAREJAS = [
        ('riesgos_publicacion', 'riesgos_publicacion_porque'),
        ('terceros_estandares', 'terceros_estandares_porque'),
        ('riesgo_dano', 'riesgo_dano_porque'),
    ]

    def clean(self):
        cleaned = super().clean()
        for pregunta, porque in self._PAREJAS:
            resp = cleaned.get(pregunta)
            just = (cleaned.get(porque) or '').strip()
            if resp in ('no', 'no_aplica') and not just:
                self.add_error(porque,
                               'Cuando la respuesta es "No" o "No aplica", debe explicar por qué.')
        return cleaned


class SeguridadValoracionForm(BaseWizardForm):
    class Meta:
        model = EvaluacionSeguridad
        fields = ['susceptible_fraude', 'organismo_custodio',
                  'confidencialidad', 'integridad', 'disponibilidad',
                  'aplica_publica', 'aplica_semiprivada', 'aplica_privada',
                  'aplica_sensible', 'aplica_reservada']

    CONFIDENCIALIDAD_CHOICES = [
        ('verde', 'Verde · Pública: información que puede ser divulgada sin restricciones (ej. estadísticas agregadas).'),
        ('amarillo', 'Amarillo · Pública Clasificada (datos semiprivados): información financiera, socioeconómica, laboral o comercial, datos que representan a varias personas. Datos privados: dirección, teléfono, composición familiar, ubicación exacta.'),
        ('rojo', 'Rojo · Pública Reservada: información exceptuada por ley (seguridad, investigaciones, reserva legal, macroeconomía del territorio, información de población víctima). Datos de salud, origen étnico, discapacidad, biométricos, o que puedan generar discriminación.'),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # organismo_custodio: select de organismos existentes
        self.fields['organismo_custodio'] = forms.ChoiceField(
            choices=[('', '— Seleccione —')] + [(o.nombre, o.nombre) for o in Organismo.objects.all().order_by('nombre')],
            required=False,
            label='¿Qué organismo / suborganismo se encuentra custodiando el conjunto de datos?',
        )
        # Preservar valor existente si no está en la lista
        if self.instance and self.instance.organismo_custodio:
            claves = [c[0] for c in self.fields['organismo_custodio'].choices]
            if self.instance.organismo_custodio not in claves:
                self.fields['organismo_custodio'].choices = list(self.fields['organismo_custodio'].choices) + [(self.instance.organismo_custodio, self.instance.organismo_custodio + ' (personalizado)')]
            self.fields['organismo_custodio'].initial = self.instance.organismo_custodio
        self.fields['confidencialidad'].choices = self.CONFIDENCIALIDAD_CHOICES
        self.fields['confidencialidad'].help_text = (
            'Establezca el nivel de clasificación de Confidencialidad conforme a las respuestas anteriores del F1. '
            'La información del conjunto de datos es: Ley 1581 del 2012.')
        if self.instance and self.instance.contiene_datos_personales == 'si':
            self.fields['confidencialidad'].choices = [
                ('amarillo', 'Amarillo · Pública Clasificada (datos semiprivados): información financiera, '
                             'socioeconómica, laboral o comercial, datos que representan a varias personas. '
                             'Datos privados: dirección, teléfono, composición familiar, ubicación exacta.'),
                ('rojo', 'Rojo · Pública Reservada: información exceptuada por ley (seguridad, investigaciones, '
                        'reserva legal, macroeconomía del territorio, información de población víctima). '
                        'Datos de salud, origen étnico, discapacidad, biométricos, o que puedan generar discriminación.'),
            ]
            if not self.instance.confidencialidad or self.instance.confidencialidad == 'verde':
                self.fields['confidencialidad'].initial = 'amarillo'
        # Si susceptible_fraude=si, integridad no puede ser verde
        if self.instance and self.instance.susceptible_fraude == 'si':
            self.fields['integridad'].choices = [
                ('amarillo', 'Amarillo · Integridad media: verificación parcial.'),
                ('rojo', 'Rojo · Integridad alta: verificación estricta obligatoria.'),
            ]
            if not self.instance.integridad or self.instance.integridad == 'verde':
                self.fields['integridad'].initial = 'amarillo'

    def save(self, commit=True):
        instancia = super().save(commit=False)
        instancia.criticidad = instancia.calcular_criticidad()
        if commit:
            instancia.save()
            self.save_m2m()
        return instancia
