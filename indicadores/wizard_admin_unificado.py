"""
Wizard Admin Unificado para procesamiento de indicadores.
Implementa flujos dinámicos según el caso de uso.
"""

import os
from collections import OrderedDict
from django.shortcuts import redirect
from django.urls import reverse
from formtools.wizard.views import SessionWizardView
from django.contrib import messages

from .models import (
    CargaConjuntoDatos, CargaSerieIndicador, ConjuntoDatos, Indicador,
    VariableConjuntoDatos, ReglaExtraccion, Desagregacion, DominioDesagregacion,
    Grafico, GraficoSerie, MenuSubtema, OperacionEstadistica, Dato
)
from .notifications import notificar_usuario_carga_procesada


def _leer_csv_auto_sep(path_or_buffer):
    """Lee un CSV auto-detectando el separador (coma, punto y coma, tab)."""
    import pandas as pd
    mejor_df = None
    mejor_cols = 0
    for sep in (',', ';', '\t'):
        try:
            df = pd.read_csv(path_or_buffer, sep=sep)
            if len(df.columns) > mejor_cols:
                mejor_df = df
                mejor_cols = len(df.columns)
            if hasattr(path_or_buffer, 'seek'):
                path_or_buffer.seek(0)
        except Exception:
            if hasattr(path_or_buffer, 'seek'):
                path_or_buffer.seek(0)
            continue
    return mejor_df if mejor_df is not None else pd.read_csv(path_or_buffer)


def _limpiar_valor_numerico(valor):
    """
    Limpia un valor para conversión numérica.
    Retorna (float_value, es_sin_dato) donde:
      - float_value es el número limpio o None
      - es_sin_dato es True si el valor original indica ausencia de dato (guión, vacío, N/A)
    Maneja separadores de miles (comas) y guiones como "sin dato".
    """
    import pandas as pd
    if pd.isna(valor):
        return None, True
    if isinstance(valor, (int, float)):
        if isinstance(valor, float) and valor != valor:  # NaN
            return None, True
        return float(valor), False
    s = str(valor).strip()
    if s in ('', '-', '--', '...', 'N/A', 'n/a', 'N/D', 'n/d', 'nan', 'NaN'):
        return None, True
    # Quitar separador de miles (coma) si el formato es 122,619
    s_clean = s.replace(',', '')
    try:
        return float(s_clean), False
    except (ValueError, TypeError):
        return None, False  # es_sin_dato=False → error real de conversión


def _parsear_fecha_dato(valor):
    """
    Convierte el valor de una celda de fecha/año en un date.

    Soporta: año como int/float/string ('2023', 2023, 2023.0, '2023.0')
    → date(año, 12, 31); fechas completas en string o Timestamp; date/datetime.

    IMPORTANTE: pd.to_datetime() recibiendo un número lo interpreta como
    nanosegundos desde epoch (cualquier año numérico queda en 1970), por
    eso los números se manejan antes de llegar a pandas.

    Retorna None si el valor no se puede interpretar (el llamador lo
    cuenta como registro con error, no crea un Dato en año erróneo).
    """
    import pandas as pd
    import re as _re
    from datetime import date as _date_cls, datetime as _dt_cls

    if valor is None:
        return None
    if isinstance(valor, _dt_cls):
        return valor.date()
    if isinstance(valor, _date_cls):
        return valor
    # pandas Timestamp / numpy datetime64 u objetos con .date()
    if not isinstance(valor, (str, bytes)) and hasattr(valor, 'date'):
        try:
            d = valor.date()
            if isinstance(d, _date_cls):
                return d
        except Exception:
            pass
    if isinstance(valor, (int, float)):
        f = float(valor)
        if f != f:  # NaN
            return None
        if f.is_integer() and 1900 <= f <= 2200:
            return _date_cls(int(f), 12, 31)
        return None  # número que no parece año: evitar epoch 1970
    s = str(valor).strip()
    if not s or s.lower() in ('nan', 'nat', 'none', '-'):
        return None
    # Año como string, con o sin '.0' ('2023', '2023.0')
    m = _re.fullmatch(r'(\d{4})(\.0+)?', s)
    if m and 1900 <= int(m.group(1)) <= 2200:
        return _date_cls(int(m.group(1)), 12, 31)
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


# Columnas del template de series que son metadata del archivo y nunca
# deben convertirse en dominios de desagregación (Bug D: caían como un
# grupo "indefinido" etiquetando todos los datos con el código/nombre
# del propio indicador).
_COLUMNAS_SISTEMA_SERIE = {
    'codigo_indicador', 'nombre_indicador', 'codigo_variable',
    'nombre_variable', 'codigo', 'sigla_indicador',
}


def _es_columna_sistema(col_name):
    """True si la columna es metadata del archivo o un artefacto de
    lectura ('Unnamed: 3'), no una desagregación."""
    cl = str(col_name).strip().lower()
    return cl in _COLUMNAS_SISTEMA_SERIE or cl.startswith('unnamed')


def _columna_tiene_valores(df, col_name):
    """True si la columna tiene al menos una celda no-vacía real."""
    try:
        serie = df[col_name].dropna().astype(str).str.strip()
        serie = serie[~serie.isin(('', 'nan', 'NaN', 'None', '-'))]
        return len(serie) > 0
    except Exception:
        return False


def _normalizar_nombre_desagregacion(valor):
    """Normaliza el nombre de una desagregación leída de una celda: recorta
    espacios extremos y colapsa espacios internos repetidos."""
    import re as _re
    return _re.sub(r'\s+', ' ', str(valor).strip())


def _get_or_create_desagregacion(nombre_celda, dominio, columna_origen):
    """
    Busca una Desagregacion dentro del dominio ignorando mayúsculas y
    espacios extra; si no existe la crea con el nombre normalizado.
    Evita duplicados tipo '0-4 años' / '0-4  años' / '0-4 Años' cuando
    distintos usuarios cargan el mismo dominio con variantes de texto.
    """
    nombre_norm = _normalizar_nombre_desagregacion(nombre_celda)
    desag = Desagregacion.objects.filter(
        dominio=dominio, nombre__iexact=nombre_norm
    ).first()
    if desag is None:
        desag = Desagregacion.objects.create(
            nombre=nombre_norm,
            dominio=dominio,
            codigo=nombre_norm[:100],
            descripcion=f'Creada automáticamente desde columna {columna_origen}',
        )
        return desag, True
    return desag, False


class WizardAdminUnificado(SessionWizardView):
    """
    Wizard adaptativo que cambia sus pasos según el caso de uso detectado.
    
    Flujos soportados:
    - Flujo A: Con conjunto_datos (CargaConjuntoDatos)
    - Flujo B: Solo Serie (CargaSerieIndicador)
    - Flujo C: Completo (conjunto_datos + Serie para validación)
    - Flujo D: Actualizar indicador existente
    """
    
    # Configuración de almacenamiento de archivos
    file_storage = None  # Se configurará en la vista
    
    # Lista inicial de formularios se define en get_form_list()
    # No se puede definir aquí porque necesitamos importar dinámicamente
    
    # Nombres de pasos base (comunes a todos los flujos)
    PASO_SELECCION_FUENTE = 'seleccion_fuente'

    # Pasos Flujo B (Solo Serie)
    PASO_PREVIEW_SERIE = 'preview_serie'
    PASO_CONFIG_INDICADOR = 'config_indicador'
    PASO_CARGAR_METADATA = 'cargar_metadata'
    PASO_VERIFICAR_DESAG = 'verificar_desag'
    PASO_MAPEO_COLUMNAS = 'mapeo_columnas'
    PASO_CONFIRMACION_SERIE = 'confirmacion_serie'

    PASO_CONFIRMACION = 'confirmacion'

    # Pasos del Flujo A (Con conjunto_datos)
    PASO_PREVIEW_MICRODATA = 'preview_conjunto_datos'
    PASO_CONFIG_MICRODATA = 'config_conjunto_datos'
    PASO_METADATA_VARIABLES = 'metadata_variables'
    PASO_CONFIG_INDICADOR_A = 'config_indicador'
    PASO_VERIFICAR_DESAG_A = 'verificar_desag'
    PASO_REGLA_EXTRACCION = 'regla_extraccion'
    PASO_DIAGNOSTICO = 'diagnostico'

    # Pasos del Flujo C (Completo: conjunto_datos + Serie)
    PASO_PREVIEW_AMBOS = 'preview_ambos'
    PASO_CONFIG_MICRODATA_C = 'config_conjunto_datos'
    PASO_METADATA_VARIABLES_C = 'metadata_variables'
    PASO_CONFIG_INDICADOR_C = 'config_indicador'
    PASO_CARGAR_METADATA_INDICADOR = 'cargar_metadata_indicador'
    PASO_VERIFICAR_DESAG_C = 'verificar_desag'
    PASO_REGLA_EXTRACCION_C = 'regla_extraccion'
    PASO_DIAGNOSTICO_C = 'diagnostico'
    PASO_VALIDAR_CON_SERIE = 'validar_con_serie'

    # Pasos del Flujo D (Actualizar Existente)
    PASO_SELECCIONAR_INDICADOR = 'seleccionar_indicador'
    PASO_SELECCIONAR_CARGA = 'seleccionar_carga'
    PASO_COMPARAR_METADATA = 'comparar_metadata'
    PASO_CONFIRMAR_CAMBIOS = 'confirmar_cambios'
    
    template_name = 'admin/wizard_unificado/base.html'
    
    def get_template_names(self):
        """Retorna el template específico para cada paso"""
        return [f'admin/wizard_unificado/{self.steps.current}.html']
    
    def get_form_initial(self, step):
        """Pre-llena el formulario con datos de sesión si existen"""
        initial = super().get_form_initial(step)
        
        # En el paso de selección de fuente, pre-seleccionar cargas desde sesión
        if step == self.PASO_SELECCION_FUENTE:
            carga_conjunto_datos_id = self.request.session.get('wizard_carga_conjunto_datos_id')
            carga_serie_id = self.request.session.get('wizard_carga_serie_id')
            
            if carga_conjunto_datos_id and carga_serie_id:
                # Ambas cargas: Flujo C
                initial['tipo_fuente'] = 'carga_pendiente'
                initial['carga_conjunto_datos'] = carga_conjunto_datos_id
                initial['carga_serie'] = carga_serie_id
            elif carga_conjunto_datos_id:
                # Solo conjunto_datos: Flujo A
                initial['tipo_fuente'] = 'carga_pendiente'
                initial['carga_conjunto_datos'] = carga_conjunto_datos_id
            elif carga_serie_id:
                # Solo serie: Flujo B
                initial['tipo_fuente'] = 'carga_pendiente'
                initial['carga_serie'] = carga_serie_id
        
        return initial

    def get(self, request, *args, **kwargs):
        """
        Auto-skip del paso 1 (seleccion_fuente) cuando viene con una carga
        pre-seleccionada desde el dashboard. Construye el formulario del paso 1
        con los datos de sesion, lo valida, ejecuta process_step, y avanza
        directamente al paso 2 sin mostrar la pantalla de seleccion.
        """
        if self.steps.current == self.PASO_SELECCION_FUENTE:
            carga_conjunto_datos_id = self.request.session.get('wizard_carga_conjunto_datos_id')
            carga_serie_id = self.request.session.get('wizard_carga_serie_id')

            if carga_conjunto_datos_id or carga_serie_id:
                from . import wizard_unificado_forms as wizard_forms

                # Construir datos del formulario con el prefijo del wizard
                prefix = self.get_form_prefix()
                form_data = {'tipo_fuente': 'carga_pendiente'}
                if carga_conjunto_datos_id:
                    form_data['carga_conjunto_datos'] = carga_conjunto_datos_id
                if carga_serie_id:
                    form_data['carga_serie'] = carga_serie_id

                # Crear y validar el formulario del paso 1
                form = wizard_forms.FormSeleccionFuente(form_data, prefix=prefix)
                if form.is_valid():
                    # Procesar el paso (determina tipo_flujo y guarda en storage)
                    self.storage.set_step_data(
                        self.steps.current, self.process_step(form)
                    )
                    self.storage.set_step_files(
                        self.steps.current, self.process_step_files(form)
                    )

                    # Limpiar sesion para evitar re-skip en refrescos o navegacion
                    self.request.session.pop('wizard_carga_conjunto_datos_id', None)
                    self.request.session.pop('wizard_carga_serie_id', None)

                    # Avanzar al siguiente paso del flujo detectado
                    return self.render_next_step(form)

        return super().get(request, *args, **kwargs)

    def get_form_list(self):
        """Retorna la lista de formularios según el flujo detectado"""
        from collections import OrderedDict
        from . import wizard_unificado_forms as wizard_forms
        
        # Siempre empezamos con el paso de selección
        form_list = OrderedDict([
            (self.PASO_SELECCION_FUENTE, wizard_forms.FormSeleccionFuente),
        ])
        
        # Si ya se determinó el flujo, agregar pasos correspondientes
        tipo_flujo = self.storage.extra_data.get('tipo_flujo')
        
        if tipo_flujo == 'flujo_b':
            # Flujo B: Solo Serie
            # Orden: preview → config → metadata → mapeo (fecha/valor) → desag (restantes) → confirmación
            form_list[self.PASO_PREVIEW_SERIE] = wizard_forms.FormPreviewSerie
            form_list[self.PASO_CONFIG_INDICADOR] = wizard_forms.FormConfigIndicadorSerie
            form_list[self.PASO_CARGAR_METADATA] = wizard_forms.FormCargarMetadata
            form_list[self.PASO_MAPEO_COLUMNAS] = wizard_forms.FormMapeoColumnas
            form_list[self.PASO_VERIFICAR_DESAG] = wizard_forms.FormVerificarDesagregaciones
            form_list[self.PASO_CONFIRMACION_SERIE] = wizard_forms.FormConfirmacionSerie
        
        elif tipo_flujo == 'flujo_a':
            # Flujo A: Con conjunto_datos
            form_list[self.PASO_PREVIEW_MICRODATA] = wizard_forms.FormPreviewconjunto_datos
            form_list[self.PASO_CONFIG_MICRODATA] = wizard_forms.FormConfigconjunto_datos
            form_list[self.PASO_METADATA_VARIABLES] = wizard_forms.FormMetadataVariables
            form_list[self.PASO_CONFIG_INDICADOR_A] = wizard_forms.FormConfigIndicador
            form_list[self.PASO_VERIFICAR_DESAG_A] = wizard_forms.FormVerificarDesagregaciones
            form_list[self.PASO_REGLA_EXTRACCION] = wizard_forms.FormReglaExtraccion
            form_list[self.PASO_DIAGNOSTICO] = wizard_forms.FormDiagnostico
        
        elif tipo_flujo == 'flujo_c':
            es_calculo_complejo = self.storage.extra_data.get('es_calculo_complejo', False)
            # Flujo C: Completo (conjunto_datos + Serie)
            # Si es_calculo_complejo=True: omitir regla de extracción y diagnóstico cartesiano
            form_list[self.PASO_PREVIEW_AMBOS] = wizard_forms.FormPreviewconjunto_datos
            form_list[self.PASO_CONFIG_MICRODATA_C] = wizard_forms.FormConfigconjunto_datos
            form_list[self.PASO_METADATA_VARIABLES_C] = wizard_forms.FormMetadataVariables
            form_list[self.PASO_CONFIG_INDICADOR_C] = wizard_forms.FormConfigIndicador
            form_list[self.PASO_CARGAR_METADATA_INDICADOR] = wizard_forms.FormMetadataIndicador
            form_list[self.PASO_VERIFICAR_DESAG_C] = wizard_forms.FormVerificarDesagregaciones
            if not es_calculo_complejo:
                # Sólo agregar extracción cartesiana si el cálculo no es complejo
                form_list[self.PASO_REGLA_EXTRACCION_C] = wizard_forms.FormReglaExtraccion
                form_list[self.PASO_DIAGNOSTICO_C] = wizard_forms.FormDiagnostico
            form_list[self.PASO_VALIDAR_CON_SERIE] = wizard_forms.FormPreviewSerie
        
        elif tipo_flujo == 'flujo_d':
            # Flujo D: Actualizar Existente
            # El indicador ya fue seleccionado en el paso 1 (seleccion_fuente → indicador_existente)
            form_list[self.PASO_SELECCIONAR_CARGA] = wizard_forms.FormSeleccionarCarga
            form_list[self.PASO_COMPARAR_METADATA] = wizard_forms.FormCompararMetadata
            form_list[self.PASO_CONFIRMAR_CAMBIOS] = wizard_forms.FormConfirmarCambios
        
        return form_list

    def get_cleaned_data_for_step(self, step):
        """
        Override para usar la lista dinámica de formularios (get_form_list())
        en lugar de self.form_list estático, que solo contiene el paso inicial.
        """
        form_list = self.get_form_list()
        if step in form_list:
            form_class = form_list[step]
            kwargs = self.get_form_kwargs(step)
            kwargs.update({
                'data': self.storage.get_step_data(step),
                'files': self.storage.get_step_files(step),
                'prefix': self.get_form_prefix(step, form_class),
                'initial': self.get_form_initial(step),
            })
            form = form_class(**kwargs)
            if form.is_valid():
                return form.cleaned_data
        return None

    def process_step(self, form):
        """Procesa cada paso después de la validación"""
        # Guardar datos del formulario en storage
        form_data = self.get_form_step_data(form)
        
        # Si es el paso de selección de fuente, determinar el tipo de flujo
        if self.steps.current == self.PASO_SELECCION_FUENTE:
            cleaned_data = form.cleaned_data
            tipo_fuente = cleaned_data.get('tipo_fuente')
            carga_conjunto_datos = cleaned_data.get('carga_conjunto_datos')
            carga_serie = cleaned_data.get('carga_serie')
            
            # Determinar tipo de flujo
            if tipo_fuente == 'carga_pendiente':
                if carga_conjunto_datos and carga_serie:
                    tipo_flujo = 'flujo_c'  # Completo
                elif carga_conjunto_datos:
                    tipo_flujo = 'flujo_a'  # Solo conjunto_datos
                elif carga_serie:
                    tipo_flujo = 'flujo_b'  # Solo serie
                else:
                    tipo_flujo = 'desconocido'
            elif tipo_fuente == 'actualizar_existente':
                tipo_flujo = 'flujo_d'
            else:
                tipo_flujo = 'desconocido'
            
            # Validación preventiva: verificar que se haya seleccionado una opción válida
            if tipo_flujo == 'desconocido':
                from django.core.exceptions import ValidationError
                raise ValidationError(
                    "Por favor selecciona una opción válida. Debes seleccionar al menos una carga pendiente "
                    "(conjunto_datos o serie) o seleccionar un indicador existente para actualizar."
                )
            
            # Detectar es_calculo_complejo desde la carga de serie
            es_calculo_complejo = False
            if carga_serie:
                try:
                    es_calculo_complejo = CargaSerieIndicador.objects.get(
                        id=carga_serie.id
                    ).es_calculo_complejo
                except Exception:
                    pass

            # Guardar en storage
            self.storage.extra_data['tipo_flujo'] = tipo_flujo
            self.storage.extra_data['tipo_fuente'] = tipo_fuente
            self.storage.extra_data['carga_conjunto_datos_id'] = carga_conjunto_datos.id if carga_conjunto_datos else None
            self.storage.extra_data['carga_serie_id'] = carga_serie.id if carga_serie else None
            self.storage.extra_data['es_calculo_complejo'] = es_calculo_complejo
            
            # Para Flujo D: guardar el indicador seleccionado en paso 1
            indicador_existente = cleaned_data.get('indicador_existente')
            if indicador_existente:
                self.storage.extra_data['indicador_existente_id'] = indicador_existente.id
        
        return form_data
    
    def post(self, *args, **kwargs):
        """
        Fallback robusto para PASO_VERIFICAR_DESAG en flujo_b:
        Si el campo hidden columnas_desagregacion_json está vacío (el JS no lo sincronizó),
        leemos los radios col_accion_* directamente del POST y reconstruimos el JSON.
        """
        if self.steps.current == self.PASO_VERIFICAR_DESAG:
            tipo_flujo = self.storage.extra_data.get('tipo_flujo')
            if tipo_flujo == 'flujo_b':
                import json
                post = self.request.POST.copy()
                prefix = self.get_form_prefix() or ''
                field_name = f"{prefix}-columnas_desagregacion_json" if prefix else "columnas_desagregacion_json"
                
                current_val = post.get(field_name, '').strip()
                if not current_val:
                    # Reconstruir decisiones desde los radios col_accion_* del POST
                    decisiones = []
                    columnas_restantes = self.storage.extra_data.get('columnas_detectadas_restantes', [])
                    if columnas_restantes:
                        for idx, col_name in enumerate(columnas_restantes):
                            action = post.get(f'col_accion_{idx}', 'ignorar')
                            if action == 'usar':
                                dominio_existente_id = self.storage.extra_data.get(f'dominio_match_{idx}')
                                if dominio_existente_id:
                                    decisiones.append({
                                        'columna': col_name,
                                        'accion': 'asociar',
                                        'dominio_id': dominio_existente_id,
                                        'dominio_nombre': col_name,
                                        'tipo': None
                                    })
                                else:
                                    tipo_col = post.get(f'tipo_dominio_{idx}', 'tematica')
                                    decisiones.append({
                                        'columna': col_name,
                                        'accion': 'crear',
                                        'dominio_id': None,
                                        'dominio_nombre': col_name,
                                        'tipo': tipo_col
                                    })
                            else:
                                decisiones.append({
                                    'columna': col_name,
                                    'accion': 'ignorar',
                                    'dominio_id': None,
                                    'dominio_nombre': None,
                                    'tipo': None
                                })
                        
                        post[field_name] = json.dumps(decisiones)
                        self.request.POST = post
                        print(f"[SIIED DEBUG] Reconstruido desde POST radios: {decisiones}")
        
        return super().post(*args, **kwargs)

    def _notificar_carga_procesada(self, carga):
        """Envia notificación al usuario y muestra advertencia en UI si falla."""
        from django.contrib import messages
        ok = notificar_usuario_carga_procesada(carga)
        if not ok and self.request:
            messages.warning(
                self.request,
                "⚠️ No se pudo enviar la notificación por correo al usuario. "
                "Revise la configuración de Brevo o los logs del servidor."
            )
        return ok

    def get_context_data(self, form, **kwargs):
        """Agrega contexto adicional a los templates"""
        context = super().get_context_data(form=form, **kwargs)
        
        # Información del flujo actual
        context['tipo_flujo'] = self.storage.extra_data.get('tipo_flujo', 'desconocido')
        context['paso_actual'] = self.steps.current
        context['paso_numero'] = self.steps.step1
        context['total_pasos'] = self.steps.count
        context['es_calculo_complejo'] = self.storage.extra_data.get('es_calculo_complejo', False)

        # Datos acumulados
        context['carga_conjunto_datos_id'] = self.storage.extra_data.get('carga_conjunto_datos_id')
        context['carga_serie_id'] = self.storage.extra_data.get('carga_serie_id')

        # Cargar objetos si existen
        if context['carga_conjunto_datos_id']:
            try:
                context['carga_conjunto_datos'] = CargaConjuntoDatos.objects.get(
                    id=context['carga_conjunto_datos_id']
                )
            except CargaConjuntoDatos.DoesNotExist:
                pass
        
        if context['carga_serie_id']:
            try:
                context['carga_serie'] = CargaSerieIndicador.objects.get(
                    id=context['carga_serie_id']
                )
            except CargaSerieIndicador.DoesNotExist:
                pass
        
        # Contexto específico para Paso 2B: Preview Serie
        if self.steps.current == self.PASO_PREVIEW_SERIE:
            carga_serie_id = self.storage.extra_data.get('carga_serie_id')
            if carga_serie_id:
                try:
                    import pandas as pd
                    import os
                    
                    carga_serie = CargaSerieIndicador.objects.get(id=carga_serie_id)
                    context['carga_serie'] = carga_serie
                    
                    # Leer CSV
                    archivo_path = carga_serie.archivo_datos_csv.path if carga_serie.archivo_datos_csv else carga_serie.archivo_datos_xlsx.path
                    
                    # Si es Excel, convertir a CSV temporalmente
                    if archivo_path.endswith(('.xlsx', '.xls')):
                        df = pd.read_excel(archivo_path)
                        csv_data = df.to_csv(index=False)
                    else:
                        with open(archivo_path, 'r', encoding='utf-8') as f:
                            csv_data = f.read()
                    
                    # Estadísticas
                    df = _leer_csv_auto_sep(pd.io.common.StringIO(csv_data))
                    csv_data = df.to_csv(index=False)
                    context['csv_data'] = csv_data
                    context['filas_count'] = len(df)
                    context['columnas_count'] = len(df.columns)
                    context['archivo_size'] = f"{os.path.getsize(archivo_path) / 1024:.2f} KB"
                    
                    # Guardar columnas y estadísticas para pasos posteriores
                    self.storage.extra_data['columnas_detectadas'] = list(df.columns)
                    self.storage.extra_data['filas_count'] = len(df)
                    self.storage.extra_data['columnas_count'] = len(df.columns)
                    self.storage.extra_data.save()

                except Exception as e:
                    context['error'] = f"Error al cargar datos: {str(e)}"
        
        # Contexto para Paso 4B: Cargar Metadata
        elif self.steps.current == self.PASO_CARGAR_METADATA:
            from .utils_wizard import ParseadorMetadata
            
            carga_serie_id = self.storage.extra_data.get('carga_serie_id')
            
            if carga_serie_id:
                try:
                    carga_serie = CargaSerieIndicador.objects.get(id=carga_serie_id)
                    
                    # Parsear metadata desde CSV o XLSX
                    _archivo_meta = None
                    if carga_serie.archivo_metadata_csv:
                        _archivo_meta = carga_serie.archivo_metadata_csv.path
                    elif getattr(carga_serie, 'archivo_metadata_xlsx', None) and carga_serie.archivo_metadata_xlsx:
                        _archivo_meta = carga_serie.archivo_metadata_xlsx.path

                    if _archivo_meta:
                        resultado = ParseadorMetadata.parsear_metadata_indicador(_archivo_meta)
                        if resultado['exitoso']:
                            context['metadata_detectada'] = resultado['metadata']
                            context['campos_encontrados'] = resultado['campos_encontrados']
                        else:
                            context['metadata_detectada'] = {}
                            context['error_metadata'] = resultado.get('error', 'Error desconocido')
                    else:
                        context['metadata_detectada'] = {}
                        context['info_metadata'] = 'No se cargó archivo de metadata'
                
                except Exception as e:
                    context['metadata_detectada'] = {}
                    context['error_metadata'] = str(e)
            else:
                context['metadata_detectada'] = {}
        
        # Contexto para Paso 6B (antes 5B): Verificar Desagregaciones
        elif self.steps.current == self.PASO_VERIFICAR_DESAG:
            import pandas as pd, tempfile, os as _os, json as _json
            from .models import Desagregacion, DominioDesagregacion
            from django.db.models import Count
            
            # Catálogo de dominios existentes para referencia del usuario
            context['catalogo_dominios'] = DominioDesagregacion.objects.annotate(
                num_desagregaciones=Count('desagregaciones')
            ).order_by('tipo', 'nombre')
            
            tipo_flujo = self.storage.extra_data.get('tipo_flujo')
            carga_serie_id = self.storage.extra_data.get('carga_serie_id')
            carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
            
            # --- Flujo B: detectar columnas restantes como potenciales dominios ---
            if tipo_flujo == 'flujo_b' and carga_serie_id:
                try:
                    _cs = CargaSerieIndicador.objects.get(id=carga_serie_id)
                    _ap = _cs.archivo_datos_csv.path if _cs.archivo_datos_csv else _cs.archivo_datos_xlsx.path
                    _csv_path = _ap
                    if _ap.endswith(('.xlsx', '.xls')):
                        _df = pd.read_excel(_ap)
                        _tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8')
                        _df.to_csv(_tmp.name, index=False)
                        _tmp.close()
                        _csv_path = _tmp.name
                    
                    _df = _leer_csv_auto_sep(_csv_path)
                    columnas_csv = list(_df.columns)
                    
                    if _csv_path != _ap:
                        _os.unlink(_csv_path)
                    
                    self.storage.extra_data['columnas_detectadas'] = columnas_csv
                    
                    # Obtener columnas ya asignadas como fecha/valor del paso anterior
                    paso_mapeo = self.get_cleaned_data_for_step(self.PASO_MAPEO_COLUMNAS) or {}
                    col_fecha = paso_mapeo.get('columna_fecha', '')
                    col_valor = paso_mapeo.get('columna_valor', '')
                    
                    # Columnas restantes = potenciales dominios de desagregación.
                    # Excluir columnas de sistema (codigo/nombre indicador) y
                    # columnas totalmente vacías (no producen desagregaciones).
                    columnas_restantes = [
                        c for c in columnas_csv
                        if c not in (col_fecha, col_valor)
                        and not _es_columna_sistema(c)
                        and _columna_tiene_valores(_df, c)
                    ]

                    # Para cada columna restante, detectar si hay un dominio existente
                    columnas_detectadas = []
                    for col in columnas_restantes:
                        col_lower = col.strip().lower()
                        # Buscar dominio por coincidencia exacta (case-insensitive)
                        dominio_match = DominioDesagregacion.objects.filter(
                            nombre__iexact=col.strip()
                        ).first()
                        
                        # Leer valores únicos de la columna (máx 50 para UI)
                        valores_unicos = sorted(_df[col].dropna().astype(str).unique().tolist())
                        valores_preview = valores_unicos[:50]
                        
                        info = {
                            'columna': col,
                            'valores_unicos': valores_preview,
                            'total_valores': len(valores_unicos),
                            'dominio_existente': None,
                            'dominio_id': None,
                            'tipo_dominio': None,
                            'desagregaciones_existentes': [],
                            'desagregaciones_faltantes': [],
                        }
                        
                        if dominio_match:
                            info['dominio_existente'] = dominio_match.nombre
                            info['dominio_id'] = dominio_match.id
                            info['tipo_dominio'] = dominio_match.tipo
                            # Verificar cuáles valores ya existen como desagregaciones
                            desag_existentes = set(
                                Desagregacion.objects.filter(dominio=dominio_match)
                                .values_list('nombre', flat=True)
                            )
                            info['desagregaciones_existentes'] = [
                                v for v in valores_unicos if v in desag_existentes
                            ]
                            info['desagregaciones_faltantes'] = [
                                v for v in valores_unicos if v not in desag_existentes
                            ]
                        
                        columnas_detectadas.append(info)
                    
                    # Guardar en storage para reconstrucción POST fallback
                    self.storage.extra_data['columnas_detectadas_restantes'] = [i['columna'] for i in columnas_detectadas]
                    print(f"[SIIED DEBUG] get_context_data: columnas_detectadas_restantes guardado = {self.storage.extra_data['columnas_detectadas_restantes']}")
                    for _idx2, _info2 in enumerate(columnas_detectadas):
                        if _info2['dominio_id']:
                            self.storage.extra_data[f'dominio_match_{_idx2}'] = _info2['dominio_id']
                        elif f'dominio_match_{_idx2}' in self.storage.extra_data:
                            del self.storage.extra_data[f'dominio_match_{_idx2}']
                    
                    context['columnas_restantes'] = columnas_detectadas
                    context['col_fecha'] = col_fecha
                    context['col_valor'] = col_valor
                    context['columnas_csv'] = columnas_csv
                    
                except Exception as e:
                    context['error'] = str(e)
                    context['columnas_restantes'] = []
            
            # --- Flujos A/C: lógica anterior de verificación ---
            elif carga_conjunto_datos_id:
                try:
                    _cm = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
                    archivo_csv = _cm.archivo_microdata_csv.path if _cm.archivo_microdata_csv else None
                    if archivo_csv:
                        _df = _leer_csv_auto_sep(archivo_csv)
                        columnas_csv = list(_df.columns)
                        self.storage.extra_data['columnas_detectadas'] = columnas_csv
                        
                        cleaned_data = self.get_cleaned_data_for_step(self.PASO_VERIFICAR_DESAG)
                        dominios_geo = cleaned_data.get('dominios_desagregacion_geografica', []) if cleaned_data else []
                        dominios_tem = cleaned_data.get('dominios_desagregacion_tematica', []) if cleaned_data else []
                        
                        verificacion_geo = None
                        verificacion_tematica = None
                        
                        if dominios_geo:
                            desagregaciones_geo = Desagregacion.objects.filter(dominio__in=dominios_geo)
                            dominios_geo_objs = DominioDesagregacion.objects.filter(id__in=[d.id for d in dominios_geo]) if dominios_geo and hasattr(dominios_geo[0], 'id') else dominios_geo
                            
                            columnas_encontradas_geo = []
                            desagregaciones_sin_columna_geo = []
                            dominios_en_columna_geo = []
                            
                            # Validar formato Largo (Nombre del dominio es columna)
                            for dom in dominios_geo_objs:
                                # Búsqueda case-insensitive flexible
                                dom_col = next((c for c in columnas_csv if dom.nombre.lower() in c.lower() or c.lower() in dom.nombre.lower()), None)
                                if dom_col:
                                    dominios_en_columna_geo.append(f"{dom.nombre} (columna: {dom_col})")
                                else:
                                    # Si no es formato largo, validar formato Ancho (Desagregaciones son columnas)
                                    desags = desagregaciones_geo.filter(dominio=dom)
                                    for d in desags:
                                        if d.nombre in columnas_csv:
                                            columnas_encontradas_geo.append(d.nombre)
                                        else:
                                            desagregaciones_sin_columna_geo.append(d.nombre)
                            
                            verificacion_geo = {
                                'dominios_en_columna': dominios_en_columna_geo,
                                'columnas_encontradas': columnas_encontradas_geo,
                                'desagregaciones_sin_columna': desagregaciones_sin_columna_geo,
                                'errores': len(desagregaciones_sin_columna_geo) > 0
                            }
                        
                        if dominios_tem:
                            desagregaciones_tem = Desagregacion.objects.filter(dominio__in=dominios_tem)
                            dominios_tem_objs = DominioDesagregacion.objects.filter(id__in=[d.id for d in dominios_tem]) if dominios_tem and hasattr(dominios_tem[0], 'id') else dominios_tem
                            
                            columnas_encontradas_tem = []
                            desagregaciones_sin_columna_tem = []
                            dominios_en_columna_tem = []
                            
                            for dom in dominios_tem_objs:
                                dom_col = next((c for c in columnas_csv if dom.nombre.lower() in c.lower() or c.lower() in dom.nombre.lower()), None)
                                if dom_col:
                                    dominios_en_columna_tem.append(f"{dom.nombre} (columna: {dom_col})")
                                else:
                                    desags = desagregaciones_tem.filter(dominio=dom)
                                    for d in desags:
                                        if d.nombre in columnas_csv:
                                            columnas_encontradas_tem.append(d.nombre)
                                        else:
                                            desagregaciones_sin_columna_tem.append(d.nombre)
                                            
                            verificacion_tematica = {
                                'dominios_en_columna': dominios_en_columna_tem,
                                'columnas_encontradas': columnas_encontradas_tem,
                                'desagregaciones_sin_columna': desagregaciones_sin_columna_tem,
                                'errores': len(desagregaciones_sin_columna_tem) > 0
                            }
                        
                        context['verificacion_geo'] = verificacion_geo
                        context['verificacion_tematica'] = verificacion_tematica
                        context['columnas_csv'] = columnas_csv
                except Exception as e:
                    context['error'] = str(e)
                    context['verificacion_geo'] = None
                    context['verificacion_tematica'] = None
        
        # Contexto para Paso 6B: Mapeo de Columnas
        elif self.steps.current == self.PASO_MAPEO_COLUMNAS:
            columnas = self.storage.extra_data.get('columnas_detectadas', [])
            context['columnas_detectadas'] = columnas
        
        # Contexto para Paso 7B: Confirmación
        elif self.steps.current == self.PASO_CONFIRMACION_SERIE:
            # Recopilar datos de todos los pasos
            paso_3_data = self.get_cleaned_data_for_step(self.PASO_CONFIG_INDICADOR) or {}
            paso_6_data = self.get_cleaned_data_for_step(self.PASO_MAPEO_COLUMNAS) or {}
            
            context['indicador_config'] = {
                'codigo': paso_3_data.get('codigo_indicador'),
                'nombre': paso_3_data.get('nombre_indicador'),
                'subtema': paso_3_data.get('subtema'),
            }
            context['mapeo'] = {
                'columna_fecha': paso_6_data.get('columna_fecha'),
                'columna_valor': paso_6_data.get('columna_valor'),
            }
            context['filas_count'] = self.storage.extra_data.get('filas_count', 0)
            context['columnas_count'] = self.storage.extra_data.get('columnas_count', 0)
            context['desag_geograficas_count'] = 0  # TODO
            context['desag_tematicas_count'] = 0  # TODO
            context['desag_faltantes_count'] = 0  # TODO
        
        # ============ CONTEXTOS FLUJO A ============
        
        # Contexto para Paso 2A: Preview conjunto_datos
        elif self.steps.current == self.PASO_PREVIEW_MICRODATA:
            carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
            if carga_conjunto_datos_id:
                try:
                    import pandas as pd
                    import os
                    
                    carga_conjunto_datos = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
                    context['carga_conjunto_datos'] = carga_conjunto_datos
                    
                    # Leer CSV
                    archivo_path = carga_conjunto_datos.archivo_microdata_csv.path if carga_conjunto_datos.archivo_microdata_csv else carga_conjunto_datos.archivo_microdata_xlsx.path
                    
                    if archivo_path.endswith(('.xlsx', '.xls')):
                        df = pd.read_excel(archivo_path)
                        csv_data = df.to_csv(index=False)
                    else:
                        with open(archivo_path, 'r', encoding='utf-8') as f:
                            csv_data = f.read()
                    
                    df = _leer_csv_auto_sep(pd.io.common.StringIO(csv_data))
                    csv_data = df.to_csv(index=False)
                    context['csv_data'] = csv_data
                    context['filas_count'] = len(df)
                    context['columnas_count'] = len(df.columns)
                    context['archivo_size'] = f"{os.path.getsize(archivo_path) / 1024:.2f} KB"
                    
                    # Guardar columnas para pasos posteriores
                    self.storage.extra_data['columnas_disponibles'] = list(df.columns)
                    
                except Exception as e:
                    context['error'] = f"Error al cargar datos: {str(e)}"
        
        # Contexto para Paso 4A: Metadata Variables
        elif self.steps.current == self.PASO_METADATA_VARIABLES:
            from .utils_wizard import ParseadorMetadata
            
            carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
            
            if carga_conjunto_datos_id:
                try:
                    carga_conjunto_datos = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
                    
                    # Intentar parsear metadata_variables.csv si existe
                    if carga_conjunto_datos.archivo_metadata_variables_csv:
                        resultado = ParseadorMetadata.parsear_metadata_variables(
                            carga_conjunto_datos.archivo_metadata_variables_csv.path
                        )
                        
                        if resultado['exitoso']:
                            context['variables_detectadas'] = resultado['variables']
                            context['total_variables'] = resultado['total_variables']
                        else:
                            context['variables_detectadas'] = []
                            context['error_metadata'] = resultado.get('error', 'Error desconocido')
                    else:
                        context['variables_detectadas'] = []
                        context['info_metadata'] = 'No se cargó archivo de metadata de variables'
                
                except Exception as e:
                    context['variables_detectadas'] = []
                    context['error_metadata'] = str(e)
            else:
                context['variables_detectadas'] = []
        
        # Contexto para Paso 6A: Verificar Desagregaciones
        elif self.steps.current == self.PASO_VERIFICAR_DESAG:
            from .utils_wizard import DetectorDesagregaciones
            
            carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
            
            if carga_conjunto_datos_id:
                try:
                    carga_conjunto_datos = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
                    archivo_csv = carga_conjunto_datos.archivo_microdata_csv.path if carga_conjunto_datos.archivo_microdata_csv else None
                    
                    if archivo_csv:
                        # Obtener columnas del CSV
                        import pandas as pd
                        _df = _leer_csv_auto_sep(archivo_csv)
                        columnas_csv = list(_df.columns)
                        
                        # Guardar columnas para verificación
                        self.storage.extra_data['columnas_detectadas'] = columnas_csv
                        
                        # Obtener dominios seleccionados (si ya se seleccionaron)
                        cleaned_data = self.get_cleaned_data_for_step(self.PASO_VERIFICAR_DESAG)
                        dominios_geo = cleaned_data.get('dominios_desagregacion_geografica', []) if cleaned_data else []
                        dominios_tem = cleaned_data.get('dominios_desagregacion_tematica', []) if cleaned_data else []
                        
                        # Generar verificación
                        from .models import Desagregacion
                        verificacion_geo = None
                        verificacion_tematica = None
                        
                        if dominios_geo:
                            desagregaciones_geo = Desagregacion.objects.filter(dominio__in=dominios_geo)
                            columnas_encontradas_geo = [d.nombre for d in desagregaciones_geo if d.nombre in columnas_csv]
                            desagregaciones_sin_columna_geo = [d.nombre for d in desagregaciones_geo if d.nombre not in columnas_csv]
                            verificacion_geo = {
                                'columnas_encontradas': columnas_encontradas_geo,
                                'desagregaciones_sin_columna': desagregaciones_sin_columna_geo,
                                'errores': len(desagregaciones_sin_columna_geo) > 0
                            }
                        
                        if dominios_tem:
                            desagregaciones_tem = Desagregacion.objects.filter(dominio__in=dominios_tem)
                            columnas_encontradas_tem = [d.nombre for d in desagregaciones_tem if d.nombre in columnas_csv]
                            desagregaciones_sin_columna_tem = [d.nombre for d in desagregaciones_tem if d.nombre not in columnas_csv]
                            verificacion_tematica = {
                                'columnas_encontradas': columnas_encontradas_tem,
                                'desagregaciones_sin_columna': desagregaciones_sin_columna_tem,
                                'errores': len(desagregaciones_sin_columna_tem) > 0
                            }
                        
                        context['verificacion_geo'] = verificacion_geo
                        context['verificacion_tematica'] = verificacion_tematica
                        context['columnas_csv'] = columnas_csv
                    else:
                        context['error'] = 'No se encontró archivo CSV'
                        context['verificacion_geo'] = None
                        context['verificacion_tematica'] = None
                
                except Exception as e:
                    context['desag_geograficas'] = {'detectadas': [], 'total': 0}
                    context['desag_tematicas'] = {'detectadas': [], 'total': 0}
                    context['error'] = str(e)
            else:
                context['desag_geograficas'] = {'detectadas': [], 'total': 0}
                context['desag_tematicas'] = {'detectadas': [], 'total': 0}
        
        # Contexto para Paso 7A: Regla de Extracción
        elif self.steps.current == self.PASO_REGLA_EXTRACCION:
            columnas = self.storage.extra_data.get('columnas_disponibles', [])
            context['columnas_disponibles'] = columnas
            context['carga_conjunto_datos_id'] = self.storage.extra_data.get('carga_conjunto_datos_id')

        # Contexto para Paso 8C: Regla de Extracción (flujo C)
        elif self.steps.current == self.PASO_REGLA_EXTRACCION_C:
            columnas = self.storage.extra_data.get('columnas_disponibles', [])
            context['columnas_disponibles'] = columnas
            context['carga_conjunto_datos_id'] = self.storage.extra_data.get('carga_conjunto_datos_id')
        
        # Contexto para Paso 8A: Diagnóstico
        elif self.steps.current == self.PASO_DIAGNOSTICO:
            from .utils_wizard import DiagnosticoConjuntoDatos, generar_output_diagnostico_html
            
            # Obtener datos de pasos anteriores
            paso_3_data = self.get_cleaned_data_for_step(self.PASO_CONFIG_MICRODATA) or {}
            paso_5_data = self.get_cleaned_data_for_step(self.PASO_CONFIG_INDICADOR_A) or {}
            paso_7_data = self.get_cleaned_data_for_step(self.PASO_REGLA_EXTRACCION) or {}
            
            # Ejecutar diagnóstico real
            carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
            
            if carga_conjunto_datos_id:
                try:
                    carga_conjunto_datos = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
                    archivo_csv = carga_conjunto_datos.archivo_microdata_csv.path if carga_conjunto_datos.archivo_microdata_csv else None
                    
                    if archivo_csv:
                        # Crear objeto de diagnóstico
                        diagnostico = DiagnosticoConjuntoDatos(archivo_csv)
                        
                        # Crear regla temporal para diagnóstico
                        from .models import ReglaExtraccion, Indicador, DominioDesagregacion
                        
                        # Parsear columnas fuente
                        columnas_fuente_str = paso_7_data.get('columnas_fuente', '')
                        columnas_fuente = [c.strip() for c in columnas_fuente_str.split(',') if c.strip()]
                        
                        # Obtener dominios del paso anterior
                        paso_desag_data = self.get_cleaned_data_for_step(self.PASO_VERIFICAR_DESAG_A) or {}
                        dominios_geo_ids = [d.id if hasattr(d, 'id') else d for d in paso_desag_data.get('dominios_desagregacion_geografica', [])]
                        dominios_tem_ids = [d.id if hasattr(d, 'id') else d for d in paso_desag_data.get('dominios_desagregacion_tematica', [])]
                        
                        dominios_geo = DominioDesagregacion.objects.filter(id__in=dominios_geo_ids)
                        dominios_tem = DominioDesagregacion.objects.filter(id__in=dominios_tem_ids)
                        
                        # Crear objetos temporales para diagnóstico
                        class ReglaTemp:
                            def __init__(self, columnas):
                                self.columnas_fuente = columnas
                        
                        class IndicadorTemp:
                            def __init__(self, d_geo, d_tem):
                                self.dominios_desagregacion_geografica = d_geo
                                self.dominios_desagregacion_tematica = d_tem
                        
                        regla_temp = ReglaTemp(columnas_fuente)
                        indicador_temp = IndicadorTemp(dominios_geo, dominios_tem)
                        
                        # Ejecutar diagnóstico
                        resultado = diagnostico.ejecutar_diagnostico_completo(regla_temp, indicador_temp)
                        
                        context['diagnostico_exitoso'] = resultado['exitoso']
                        context['diagnostico_output'] = generar_output_diagnostico_html(resultado)
                        
                        # Guardar resultado en storage para usar en procesamiento
                        self.storage.extra_data['diagnostico_resultado'] = resultado
                    else:
                        context['diagnostico_exitoso'] = False
                        context['diagnostico_output'] = "Error: No se encontró archivo CSV"
                
                except Exception as e:
                    context['diagnostico_exitoso'] = False
                    context['diagnostico_output'] = f"Error al ejecutar diagnóstico: {str(e)}"
            else:
                context['diagnostico_exitoso'] = False
                context['diagnostico_output'] = "Error: No se encontró carga de conjunto_datos"
            
            # Resumen
            context['conjunto_datos_nombre'] = paso_3_data.get('nombre_conjunto_datos', 'N/A')
            context['indicador_nombre'] = paso_5_data.get('nombre', 'N/A')
            context['formula'] = paso_7_data.get('formula', 'N/A')
            context['columna_fecha'] = paso_7_data.get('columna_fecha', 'N/A')
            context['columnas_fuente'] = paso_7_data.get('columnas_fuente', 'N/A')
            context['total_desagregaciones'] = 0
        
        # ============ CONTEXTOS FLUJO C ============

        # Contexto para Paso 2C: Preview Ambos Archivos
        elif self.steps.current == self.PASO_PREVIEW_AMBOS:
            import pandas as pd, os
            for _cid, _cls, _key_csv, _key_xlsx, _ctx_csv, _ctx_filas, _ctx_cols, _storage_key in [
                (self.storage.extra_data.get('carga_conjunto_datos_id'), CargaConjuntoDatos,
                 'archivo_microdata_csv', 'archivo_microdata_xlsx',
                 'csv_data_micro', 'filas_micro', 'columnas_micro', 'columnas_disponibles'),
                (self.storage.extra_data.get('carga_serie_id'), CargaSerieIndicador,
                 'archivo_datos_csv', 'archivo_datos_xlsx',
                 'csv_data_serie', 'filas_serie', 'columnas_serie', 'columnas_detectadas'),
            ]:
                if _cid:
                    try:
                        _obj = _cls.objects.get(id=_cid)
                        _ap = getattr(_obj, _key_csv, None)
                        _ap = _ap.path if _ap else getattr(_obj, _key_xlsx).path
                        if _ap.endswith(('.xlsx', '.xls')):
                            _df = pd.read_excel(_ap)
                            _csvd = _df.to_csv(index=False)
                        else:
                            with open(_ap, 'r', encoding='utf-8') as _f:
                                _csvd = _f.read()
                            _df = _leer_csv_auto_sep(pd.io.common.StringIO(_csvd))
                        context[_ctx_csv] = _csvd
                        context[_ctx_filas] = len(_df)
                        context[_ctx_cols] = len(_df.columns)
                        self.storage.extra_data[_storage_key] = list(_df.columns)
                    except Exception as _e:
                        context[f'error_{_ctx_filas}'] = str(_e)

        # Contexto para Paso 4C: Metadata Variables
        elif self.steps.current == self.PASO_METADATA_VARIABLES_C:
            from .utils_wizard import ParseadorMetadata
            carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
            if carga_conjunto_datos_id:
                try:
                    _cm = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
                    if _cm.archivo_metadata_variables_csv:
                        resultado = ParseadorMetadata.parsear_metadata_variables(_cm.archivo_metadata_variables_csv.path)
                        context['variables_detectadas'] = resultado.get('variables', [])
                        context['total_variables'] = resultado.get('total_variables', 0)
                    else:
                        context['variables_detectadas'] = []
                        context['info_metadata'] = 'No se cargó archivo de metadata de variables'
                except Exception as e:
                    context['variables_detectadas'] = []
                    context['error_metadata'] = str(e)

        # Contexto para Paso 6C: Metadata del Indicador
        elif self.steps.current == self.PASO_CARGAR_METADATA_INDICADOR:
            from .utils_wizard import ParseadorMetadata
            carga_serie_id = self.storage.extra_data.get('carga_serie_id')
            if carga_serie_id:
                try:
                    _cs = CargaSerieIndicador.objects.get(id=carga_serie_id)
                    _am = None
                    if _cs.archivo_metadata_csv:
                        _am = _cs.archivo_metadata_csv.path
                    elif getattr(_cs, 'archivo_metadata_xlsx', None) and _cs.archivo_metadata_xlsx:
                        _am = _cs.archivo_metadata_xlsx.path
                    if _am:
                        resultado = ParseadorMetadata.parsear_metadata_indicador(_am)
                        context['metadata_detectada'] = resultado.get('metadata', {})
                        context['campos_encontrados'] = resultado.get('campos_encontrados', 0)
                    else:
                        context['metadata_detectada'] = {}
                        context['info_metadata'] = 'No se cargó archivo de metadata'
                except Exception as e:
                    context['metadata_detectada'] = {}
                    context['error_metadata'] = str(e)

        # Contexto para Paso 7C: Verificar Desagregaciones
        elif self.steps.current == self.PASO_VERIFICAR_DESAG:
            from .utils_wizard import DetectorDesagregaciones
            import pandas as pd, tempfile, os as _os
            carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
            if carga_conjunto_datos_id:
                try:
                    _cm = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
                    _ap = _cm.archivo_microdata_csv.path if _cm.archivo_microdata_csv else _cm.archivo_microdata_xlsx.path
                    _csv_path = _ap
                    if _ap.endswith(('.xlsx', '.xls')):
                        _df = pd.read_excel(_ap)
                        _tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8')
                        _df.to_csv(_tmp.name, index=False)
                        _tmp.close()
                        _csv_path = _tmp.name
                    
                    # Obtener columnas del CSV
                    _df = _leer_csv_auto_sep(_csv_path)
                    columnas_csv = list(_df.columns)
                    
                    if _csv_path != _ap:
                        _os.unlink(_csv_path)
                    
                    # Guardar columnas para verificación
                    self.storage.extra_data['columnas_detectadas'] = columnas_csv
                    
                    # Obtener dominios seleccionados (si ya se seleccionaron)
                    cleaned_data = self.get_cleaned_data_for_step(self.PASO_VERIFICAR_DESAG)
                    dominios_geo = cleaned_data.get('dominios_desagregacion_geografica', []) if cleaned_data else []
                    dominios_tem = cleaned_data.get('dominios_desagregacion_tematica', []) if cleaned_data else []
                    
                    # Generar verificación
                    from .models import Desagregacion
                    verificacion_geo = None
                    verificacion_tematica = None
                    
                    if dominios_geo:
                        desagregaciones_geo = Desagregacion.objects.filter(dominio__in=dominios_geo)
                        columnas_encontradas_geo = [d.nombre for d in desagregaciones_geo if d.nombre in columnas_csv]
                        desagregaciones_sin_columna_geo = [d.nombre for d in desagregaciones_geo if d.nombre not in columnas_csv]
                        verificacion_geo = {
                            'columnas_encontradas': columnas_encontradas_geo,
                            'desagregaciones_sin_columna': desagregaciones_sin_columna_geo,
                            'errores': len(desagregaciones_sin_columna_geo) > 0
                        }
                    
                    if dominios_tem:
                        desagregaciones_tem = Desagregacion.objects.filter(dominio__in=dominios_tem)
                        columnas_encontradas_tem = [d.nombre for d in desagregaciones_tem if d.nombre in columnas_csv]
                        desagregaciones_sin_columna_tem = [d.nombre for d in desagregaciones_tem if d.nombre not in columnas_csv]
                        verificacion_tematica = {
                            'columnas_encontradas': columnas_encontradas_tem,
                            'desagregaciones_sin_columna': desagregaciones_sin_columna_tem,
                            'errores': len(desagregaciones_sin_columna_tem) > 0
                        }
                    
                    context['verificacion_geo'] = verificacion_geo
                    context['verificacion_tematica'] = verificacion_tematica
                    context['columnas_csv'] = columnas_csv
                    
                except Exception as e:
                    context['error'] = str(e)
                    context['verificacion_geo'] = None
                    context['verificacion_tematica'] = None

        # Contexto para Paso 8C: Regla de Extracción
        elif self.steps.current == self.PASO_REGLA_EXTRACCION_C:
            context['columnas_disponibles'] = self.storage.extra_data.get('columnas_disponibles', [])

        # Contexto para Paso 9C: Diagnóstico
        elif self.steps.current == self.PASO_DIAGNOSTICO_C:
            from .utils_wizard import DiagnosticoConjuntoDatos, generar_output_diagnostico_html
            paso_regla_data = self.get_cleaned_data_for_step(self.PASO_REGLA_EXTRACCION_C) or {}
            carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
            if carga_conjunto_datos_id:
                try:
                    _cm = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
                    _archivo_csv = _cm.archivo_microdata_csv.path if _cm.archivo_microdata_csv else None
                    if _archivo_csv:
                        diagnostico = DiagnosticoConjuntoDatos(_archivo_csv)
                        columnas_fuente = [c.strip() for c in paso_regla_data.get('columnas_fuente', '').split(',') if c.strip()]
                        
                        # Obtener dominios del paso anterior
                        from .models import DominioDesagregacion
                        paso_desag_data = self.get_cleaned_data_for_step(self.PASO_VERIFICAR_DESAG_C) or {}
                        dominios_geo_ids = [d.id if hasattr(d, 'id') else d for d in paso_desag_data.get('dominios_desagregacion_geografica', [])]
                        dominios_tem_ids = [d.id if hasattr(d, 'id') else d for d in paso_desag_data.get('dominios_desagregacion_tematica', [])]
                        
                        dominios_geo = DominioDesagregacion.objects.filter(id__in=dominios_geo_ids)
                        dominios_tem = DominioDesagregacion.objects.filter(id__in=dominios_tem_ids)
                        
                        class _ReglaTemp:
                            def __init__(self, cols): self.columnas_fuente = cols
                        class _IndTemp:
                            def __init__(self, d_geo, d_tem):
                                self.dominios_desagregacion_geografica = d_geo
                                self.dominios_desagregacion_tematica = d_tem
                        resultado = diagnostico.ejecutar_diagnostico_completo(_ReglaTemp(columnas_fuente), _IndTemp(dominios_geo, dominios_tem))
                        context['diagnostico_exitoso'] = resultado['exitoso']
                        context['diagnostico_output'] = generar_output_diagnostico_html(resultado)
                    else:
                        context['diagnostico_exitoso'] = False
                        context['diagnostico_output'] = 'No se encontró archivo CSV de conjunto_datos'
                except Exception as e:
                    context['diagnostico_exitoso'] = False
                    context['diagnostico_output'] = f'Error al ejecutar diagnóstico: {str(e)}'

        # Contexto para Paso 10C: Validar con Serie
        elif self.steps.current == self.PASO_VALIDAR_CON_SERIE:
            carga_serie_id = self.storage.extra_data.get('carga_serie_id')
            if carga_serie_id:
                try:
                    import pandas as pd
                    _cs = CargaSerieIndicador.objects.get(id=carga_serie_id)
                    _ap = _cs.archivo_datos_csv.path if _cs.archivo_datos_csv else _cs.archivo_datos_xlsx.path
                    _df = pd.read_excel(_ap) if _ap.endswith(('.xlsx', '.xls')) else _leer_csv_auto_sep(_ap)
                    context['filas_serie'] = len(_df)
                    context['columnas_serie'] = list(_df.columns)
                    context['csv_data_serie'] = _df.to_csv(index=False)
                except Exception as e:
                    context['error'] = str(e)

        # ============ CONTEXTOS FLUJO D ============
        
        # Contexto para Paso 2D: Seleccionar Carga
        elif self.steps.current == self.PASO_SELECCIONAR_CARGA:
            # Mostrar indicador seleccionado en paso 1
            indicador_id = self.storage.extra_data.get('indicador_existente_id')
            if indicador_id:
                try:
                    context['indicador'] = Indicador.objects.get(id=indicador_id)
                except Indicador.DoesNotExist:
                    pass
            context['cargas_serie'] = CargaSerieIndicador.objects.filter(estado__in=['pendiente', 'aprobado']).order_by('-fecha_carga')[:10]
            context['cargas_conjuntos_datos'] = CargaConjuntoDatos.objects.filter(estado__in=['pendiente', 'aprobado']).order_by('-fecha_carga')[:10]
        
        # Contexto para Paso 4D: Comparar Metadata
        elif self.steps.current == self.PASO_COMPARAR_METADATA:
            # TODO: Comparar metadata actual vs nueva
            context['metadata_diff'] = {}
        
        # Contexto para Paso 5D: Confirmar Cambios
        elif self.steps.current == self.PASO_CONFIRMAR_CAMBIOS:
            paso_3_data = self.get_cleaned_data_for_step(self.PASO_SELECCIONAR_CARGA) or {}
            
            # Indicador fue seleccionado en paso 1 (seleccion_fuente)
            indicador = None
            indicador_id = self.storage.extra_data.get('indicador_existente_id')
            if indicador_id:
                try:
                    indicador = Indicador.objects.get(id=indicador_id)
                except Indicador.DoesNotExist:
                    pass
            tipo_carga = paso_3_data.get('tipo_carga')
            
            if indicador:
                context['indicador'] = indicador
                context['datos_actuales_count'] = indicador.datos.count()
            
            context['tipo_carga'] = tipo_carga
            
            if tipo_carga == 'serie':
                carga = paso_3_data.get('carga_serie')
                if carga:
                    context['carga'] = carga
                    context['archivo_nombre'] = carga.archivo_datos_xlsx.name
                    context['datos_nuevos_count'] = 0  # TODO: Contar filas del CSV
            elif tipo_carga == 'conjunto_datos':
                carga = paso_3_data.get('carga_conjunto_datos')
                if carga:
                    context['carga'] = carga
                    context['archivo_nombre'] = carga.archivo_microdata_xlsx.name
                    context['datos_nuevos_count'] = 0  # TODO: Estimar datos del producto cartesiano
            
            context['cambios_metadata'] = []  # TODO: Lista de cambios
        
        return context
    
    def get_form_kwargs(self, step=None):
        """Agrega kwargs adicionales a los formularios"""
        kwargs = super().get_form_kwargs(step)
        
        # Para el formulario de mapeo de columnas, pasar las columnas detectadas
        if step == self.PASO_MAPEO_COLUMNAS:
            columnas = self.storage.extra_data.get('columnas_detectadas', [])
            kwargs['columnas'] = columnas
        
        # Para el formulario de regla de extracción, pasar el indicador
        if step in [self.PASO_REGLA_EXTRACCION, self.PASO_REGLA_EXTRACCION_C]:
            indicador_id = self.storage.extra_data.get('indicador_id')
            if indicador_id:
                try:
                    from .models import Indicador
                    indicador = Indicador.objects.get(id=indicador_id)
                    kwargs['indicador'] = indicador
                except Indicador.DoesNotExist:
                    pass
        
        return kwargs
    
    def done(self, form_list, **kwargs):
        """
        Ejecuta cuando el wizard se completa.
        Procesa todos los datos acumulados según el flujo.
        """
        # Recopilar todos los datos del wizard
        all_data = {}
        for form in form_list:
            all_data.update(form.cleaned_data)
        
        tipo_flujo = self.storage.extra_data.get('tipo_flujo')
        
        try:
            if tipo_flujo == 'flujo_a':
                resultado = self._procesar_flujo_a(all_data)
            elif tipo_flujo == 'flujo_b':
                resultado = self._procesar_flujo_b(all_data)
            elif tipo_flujo == 'flujo_c':
                resultado = self._procesar_flujo_c(all_data)
            elif tipo_flujo == 'flujo_d':
                resultado = self._procesar_flujo_d(all_data)
            else:
                raise ValueError(
                    "No se pudo determinar el tipo de flujo. Por favor, regresa al paso de selección de fuente "
                    "y selecciona una opción válida. Si el problema persiste, contacta al soporte técnico."
                )

            # ============================================================
            # T3: TRAZABILIDAD — Registrar cambio en audit trail
            # ============================================================
            from .utils_wizard import crear_registro_cambio
            indicador_id = resultado.get('indicador_id')
            if indicador_id:
                try:
                    indicador = Indicador.objects.get(id=indicador_id)
                    usuario = self.request.user if self.request.user.is_authenticated else None

                    # Mapeo flujo → tipo_evento
                    tipo_evento_map = {
                        'flujo_a': 'carga_conjunto_datos_wizard',
                        'flujo_b': 'carga_serie_wizard',
                        'flujo_c': 'carga_completa_wizard',
                        'flujo_d': 'actualizacion_manual_admin',
                    }
                    tipo_evento = tipo_evento_map.get(tipo_flujo, 'carga_serie_wizard')

                    # Contar datos actuales del indicador como proxy de filas afectadas
                    filas = indicador.datos.count()

                    # Nombre del archivo relacionado (si aplica)
                    archivo = ''
                    if tipo_flujo == 'flujo_a':
                        carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
                        if carga_conjunto_datos_id:
                            _cm = CargaConjuntoDatos.objects.filter(id=carga_conjunto_datos_id).first()
                            if _cm and _cm.archivo_microdata_xlsx:
                                archivo = os.path.basename(_cm.archivo_microdata_xlsx.name)
                    elif tipo_flujo == 'flujo_b':
                        carga_serie_id = self.storage.extra_data.get('carga_serie_id')
                        if carga_serie_id:
                            _cs = CargaSerieIndicador.objects.filter(id=carga_serie_id).first()
                            if _cs and _cs.archivo_datos_xlsx:
                                archivo = os.path.basename(_cs.archivo_datos_xlsx.name)
                    elif tipo_flujo == 'flujo_c':
                        _cm = self.storage.extra_data.get('carga_conjunto_datos_id')
                        _cs = self.storage.extra_data.get('carga_serie_id')
                        nombres = []
                        if _cm:
                            _cmo = CargaConjuntoDatos.objects.filter(id=_cm).first()
                            if _cmo and _cmo.archivo_microdata_xlsx:
                                nombres.append(os.path.basename(_cmo.archivo_microdata_xlsx.name))
                        if _cs:
                            _cso = CargaSerieIndicador.objects.filter(id=_cs).first()
                            if _cso and _cso.archivo_datos_xlsx:
                                nombres.append(os.path.basename(_cso.archivo_datos_xlsx.name))
                        archivo = ' + '.join(nombres)
                    elif tipo_flujo == 'flujo_d':
                        paso_3 = self.get_cleaned_data_for_step(self.PASO_SELECCIONAR_CARGA) or {}
                        tipo_carga = paso_3.get('tipo_carga', 'serie')
                        if tipo_carga == 'serie':
                            _cs = paso_3.get('carga_serie')
                            if _cs and _cs.archivo_datos_xlsx:
                                archivo = os.path.basename(_cs.archivo_datos_xlsx.name)
                        else:
                            _cm = paso_3.get('carga_conjunto_datos')
                            if _cm and _cm.archivo_microdata_xlsx:
                                archivo = os.path.basename(_cm.archivo_microdata_xlsx.name)

                    crear_registro_cambio(
                        indicador=indicador,
                        usuario=usuario,
                        tipo_evento=tipo_evento,
                        filas_afectadas=filas,
                        archivo_relacionado=archivo or None
                    )
                except Exception as audit_err:
                    # El audit trail no debe romper el wizard; solo loggear
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"No se pudo crear RegistroCambio para indicador {indicador_id}: {audit_err}")

            messages.success(
                self.request,
                f'✅ Wizard completado exitosamente. {resultado["mensaje"]}'
            )
            
            # Redirigir según el resultado
            if resultado.get('proceso_id'):
                # Si se creó un proceso, redirigir al visor en vivo
                return redirect('indicadores:proceso_en_vivo', proceso_id=resultado['proceso_id'])
            elif resultado.get('indicador_id'):
                # Si se creó/actualizó un indicador, redirigir al admin
                return redirect('admin:indicadores_indicador_change', resultado['indicador_id'])
            else:
                # Por defecto, redirigir a la lista de indicadores
                return redirect('admin:indicadores_indicador_changelist')
        
        except Exception as e:
            messages.error(
                self.request,
                f'❌ Error al procesar wizard: {str(e)}'
            )
            return redirect('admin:indicadores_indicador_changelist')
    
    def _procesar_flujo_a(self, data):
        """Procesa Flujo A: Con conjunto_datos - Procesamiento Cartesiano"""
        from django.db import transaction
        from django.utils import timezone
        import os
        
        carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
        
        if not carga_conjunto_datos_id:
            raise ValueError(
                "No se encontró la información de la carga de conjunto_datos. Por favor, regresa al paso de selección "
                "de fuente y selecciona una carga válida. Si el problema persiste, verifica que la carga exista en el sistema."
            )
        
        try:
            carga_conjunto_datos = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
            
            # Marcar como en proceso
            carga_conjunto_datos.estado = 'procesando'
            carga_conjunto_datos.save()
            
            # Obtener datos de los pasos
            paso_3_data = self.get_cleaned_data_for_step(self.PASO_CONFIG_MICRODATA) or {}
            paso_5_data = self.get_cleaned_data_for_step(self.PASO_CONFIG_INDICADOR_A) or {}
            paso_7_data = self.get_cleaned_data_for_step(self.PASO_REGLA_EXTRACCION) or {}
            
            with transaction.atomic():
                # 1. Crear o asociar conjunto_datos
                if paso_3_data.get('opcion') == 'crear_nueva':
                    conjunto_datos = ConjuntoDatos.objects.create(
                        nombre=paso_3_data['nombre_conjunto_datos'],
                        descripcion=paso_3_data.get('descripcion_conjunto_datos', ''),
                        operacion=paso_3_data.get('operacion_estadistica'),
                        archivo_csv=carga_conjunto_datos.archivo_microdata_csv
                    )
                else:
                    if 'conjunto_datos_existente' not in paso_3_data:
                        raise ValueError("No se seleccionó una conjunto_datos existente. Por favor, completa el paso de configuración de conjunto_datos.")
                    conjunto_datos = paso_3_data['conjunto_datos_existente']
                
                # 2. Crear o asociar Indicador
                if paso_5_data.get('opcion') == 'crear_nuevo':
                    indicador = Indicador.objects.create(
                        codigo_indicador=paso_5_data.get('codigo_indicador', ''),
                        nombre=paso_5_data['nombre'],
                        sigla=paso_5_data.get('sigla', ''),
                        subtema=paso_5_data['subtema'],
                        conjunto_datos=conjunto_datos,
                        activo=True
                    )
                    indicador.subtemas_adicionales.set(
                        paso_5_data.get('subtemas_adicionales') or [])
                else:
                    if 'indicador_existente' not in paso_5_data:
                        raise ValueError("No se seleccionó un indicador existente. Por favor, completa el paso de configuración del indicador.")
                    indicador = paso_5_data['indicador_existente']
                    # Eliminar datos existentes
                    indicador.datos.all().delete()
                    # Actualizar relación con conjunto_datos
                    indicador.conjunto_datos = conjunto_datos
                    indicador.save()
                    # .add() y no .set(): no pisar clasificaciones del
                    # indicador existente que el usuario no vio en el paso
                    adic = paso_5_data.get('subtemas_adicionales')
                    if adic:
                        indicador.subtemas_adicionales.add(*adic)
                
                # 3. Asignar dominios de desagregación seleccionados en el wizard
                #    SIEMPRE aplicar .set() — selección vacía limpia dominios anteriores.
                paso_6_data = self.get_cleaned_data_for_step(self.PASO_VERIFICAR_DESAG) or {}
                indicador.dominios_desagregacion_geografica.set(
                    paso_6_data.get('dominios_desagregacion_geografica') or []
                )
                indicador.dominios_desagregacion_tematica.set(
                    paso_6_data.get('dominios_desagregacion_tematica') or []
                )
                
                # 4. Crear ReglaExtraccion
                from .models import ReglaExtraccion
                import json
                
                # Parsear columnas fuente
                columnas_fuente_str = paso_7_data['columnas_fuente']
                columnas_fuente = [c.strip() for c in columnas_fuente_str.split(',')]
                
                # Parsear orden de desagregaciones
                orden_desag_str = paso_7_data.get('orden_desagregaciones', '')
                orden_desag = [d.strip() for d in orden_desag_str.split(',') if d.strip()]
                
                regla = ReglaExtraccion.objects.create(
                    indicador=indicador,
                    columna_fecha=paso_7_data['columna_fecha'],
                    columnas_fuente=columnas_fuente,
                    formula=paso_7_data['formula'],
                    filtros=json.loads(paso_7_data.get('filtros_json', '{}')),
                    orden_desagregaciones=orden_desag,
                    activo=True
                )
                
                # 4. Ejecutar procesamiento cartesiano
                from .procesamiento_normalizado import procesar_conjunto_datos_a_indicador
                
                # Obtener opción de crear faltantes del paso 6 (Verificar Desagregaciones)
                crear_faltantes = paso_6_data.get('crear_faltantes_auto', True)
                
                resultado = procesar_conjunto_datos_a_indicador(
                    carga_conjunto_datos_id=carga_conjunto_datos.id,
                    regla_extraccion_id=regla.id,
                    crear_faltantes=crear_faltantes
                )
                
                # 5. Crear/actualizar gráfico y sus series cartesianas
                self._crear_series_grafico(indicador)

                # 6. Actualizar carga
                carga_conjunto_datos.estado = 'exitoso'
                carga_conjunto_datos.fecha_procesamiento = timezone.now()
                carga_conjunto_datos.registros_procesados = resultado.get('registros_procesados', 0)
                carga_conjunto_datos.registros_exitosos = resultado.get('registros_exitosos', 0)
                carga_conjunto_datos.registros_error = resultado.get('registros_error', 0)
                carga_conjunto_datos.conjunto_datos = conjunto_datos
                carga_conjunto_datos.save()
                self._notificar_carga_procesada(carga_conjunto_datos)

            nombre_archivo = os.path.basename(carga_conjunto_datos.archivo_microdata_xlsx.name)
            
            return {
                'mensaje': f'conjunto_datos "{nombre_archivo}" procesada exitosamente. {resultado.get("registros_exitosos", 0)} datos generados.',
                'carga_id': carga_conjunto_datos.id,
                'indicador_id': indicador.id,
                'regla_id': regla.id
            }
            
        except Exception as e:
            # Marcar como error
            carga_conjunto_datos.estado = 'error'
            carga_conjunto_datos.mensaje_error = str(e)
            carga_conjunto_datos.save()
            self._notificar_carga_procesada(carga_conjunto_datos)
            raise ValueError(
                f"Error al procesar la conjunto_datos: {str(e)}. Por favor, verifica que el archivo esté en el formato correcto "
                "y que todos los datos requeridos estén presentes. Si el problema persiste, contacta al soporte técnico."
            )
    
    def _procesar_flujo_b(self, data):
        """Procesa Flujo B: Solo Serie - Importación directa de datos"""
        from django.db import transaction
        from django.utils import timezone
        import pandas as pd
        import os
        
        carga_serie_id = self.storage.extra_data.get('carga_serie_id')
        
        if not carga_serie_id:
            raise ValueError(
                "No se encontró la información de la carga de serie. Por favor, regresa al paso de selección "
                "de fuente y selecciona una carga válida. Si el problema persiste, verifica que la carga exista en el sistema."
            )
        
        try:
            carga_serie = CargaSerieIndicador.objects.get(id=carga_serie_id)
            
            # Marcar como en proceso
            carga_serie.estado = 'procesando'
            carga_serie.save()
            
            # Obtener datos de los pasos
            paso_3_data = self.get_cleaned_data_for_step(self.PASO_CONFIG_INDICADOR) or {}
            paso_6_data = self.get_cleaned_data_for_step(self.PASO_MAPEO_COLUMNAS) or {}
            paso_7_data = self.get_cleaned_data_for_step(self.PASO_CONFIRMACION_SERIE) or {}
            
            with transaction.atomic():
                # 1. Crear o asociar indicador
                if paso_3_data.get('opcion') == 'crear_nuevo':
                    indicador = Indicador.objects.create(
                        codigo_indicador=paso_3_data['codigo_indicador'],
                        nombre=paso_3_data['nombre_indicador'],
                        sigla=paso_3_data.get('sigla', ''),
                        subtema=paso_3_data['subtema'],
                        activo=True
                    )
                    indicador.subtemas_adicionales.set(
                        paso_3_data.get('subtemas_adicionales') or [])
                else:
                    if 'indicador_existente' not in paso_3_data:
                        raise ValueError("No se seleccionó un indicador existente. Por favor, completa el paso de configuración del indicador.")
                    indicador = paso_3_data['indicador_existente']
                    # .add() y no .set(): no pisar clasificaciones previas
                    adic = paso_3_data.get('subtemas_adicionales')
                    if adic:
                        indicador.subtemas_adicionales.add(*adic)
                    
                    # Si se debe eliminar datos existentes
                    if paso_7_data.get('eliminar_datos_existentes'):
                        indicador.datos.all().delete()

                # 2. Asignar dominios de desagregación seleccionados en el wizard
                #    SIEMPRE aplicar .set() — si la selección está vacía, se limpian
                #    los dominios anteriores del indicador.
                paso_desag_data = self.get_cleaned_data_for_step(self.PASO_VERIFICAR_DESAG) or {}
                print(f"[SIIED DEBUG] paso_desag_data keys: {list(paso_desag_data.keys()) if paso_desag_data else 'None'}")
                indicador.dominios_desagregacion_geografica.set(
                    paso_desag_data.get('dominios_desagregacion_geografica') or []
                )
                indicador.dominios_desagregacion_tematica.set(
                    paso_desag_data.get('dominios_desagregacion_tematica') or []
                )
                
                # 2b. Procesar columnas como dominios de desagregación (Flujo B enhanced)
                import json as _json
                from .models import DominioDesagregacion, Desagregacion

                # --- Leer preferencias del recolector (arriba de todo) ---
                tipos_recolector = {}  # {columna_lower: tipo}
                padres_recolector = {}  # {columna_lower: 'col:X' | 'dom:ID'}
                masiva_origen = carga_serie.carga_masiva_origen.first()
                if masiva_origen and masiva_origen.resumen_json:
                    for dom_info in masiva_origen.resumen_json.get('dominios_detectados', []):
                        tipos_recolector[dom_info['columna'].lower()] = dom_info.get('tipo_sugerido', 'tematica')
                        if dom_info.get('padre_sugerido'):
                            padres_recolector[dom_info['columna'].lower()] = dom_info['padre_sugerido']
                print(f"[SIIED DEBUG] Tipos recolector (global): {tipos_recolector}")
                print(f"[SIIED DEBUG] Padres recolector (global): {padres_recolector}")

                columnas_desag_json = paso_desag_data.get('columnas_desagregacion_json', '')
                print(f"[SIIED DEBUG] columnas_desagregacion_json raw: {repr(columnas_desag_json)}")
                columnas_desag = []
                if columnas_desag_json:
                    try:
                        columnas_desag = _json.loads(columnas_desag_json)
                        print(f"[SIIED DEBUG] columnas_desag parseado: {columnas_desag}")
                    except (ValueError, TypeError) as e:
                        print(f"[SIIED DEBUG] Error parseando JSON: {e}")
                        columnas_desag = []
                
                # FALLBACK NIVEL 1: Reconstruir desde step_data raw (POST almacenado)
                if not columnas_desag:
                    columnas_restantes_names = self.storage.extra_data.get('columnas_detectadas_restantes', [])
                    print(f"[SIIED DEBUG] Fallback 1: columnas_detectadas_restantes = {columnas_restantes_names}")
                    if columnas_restantes_names:
                        step_data = self.storage.get_step_data(self.PASO_VERIFICAR_DESAG) or {}
                        print(f"[SIIED DEBUG] step_data keys (primeras 20): {list(step_data.keys())[:20]}")
                        
                        for idx, col_name in enumerate(columnas_restantes_names):
                            action = step_data.get(f'col_accion_{idx}', 'ignorar')
                            print(f"[SIIED DEBUG] col={col_name} idx={idx} action={action}")
                            if action == 'usar':
                                padre_col = step_data.get(f'padre_dominio_{idx}', '') or None
                                dominio_existente_id = self.storage.extra_data.get(f'dominio_match_{idx}')
                                if dominio_existente_id:
                                    columnas_desag.append({
                                        'columna': col_name,
                                        'accion': 'asociar',
                                        'dominio_id': dominio_existente_id,
                                        'tipo': None,
                                        'padre': padre_col
                                    })
                                else:
                                    tipo_col = step_data.get(f'tipo_dominio_{idx}', 'tematica')
                                    columnas_desag.append({
                                        'columna': col_name,
                                        'accion': 'crear',
                                        'dominio_id': None,
                                        'tipo': tipo_col,
                                        'padre': padre_col
                                    })
                        print(f"[SIIED DEBUG] Decisiones reconstruidas (Fallback 1): {columnas_desag}")
                
                # FALLBACK NIVEL 2: Si aún no hay decisiones pero hay columnas restantes en el archivo,
                # crear dominios automáticamente para todas las columnas que no son fecha/valor
                if not columnas_desag:
                    columna_fecha = paso_6_data.get('columna_fecha', '')
                    columna_valor = paso_6_data.get('columna_valor', '')
                    archivo_path_check = carga_serie.archivo_datos_csv.path if carga_serie.archivo_datos_csv else carga_serie.archivo_datos_xlsx.path
                    if archivo_path_check.endswith(('.xlsx', '.xls')):
                        _df_check = pd.read_excel(archivo_path_check)
                    else:
                        _df_check = _leer_csv_auto_sep(archivo_path_check)
                    
                    todas_columnas = list(_df_check.columns)
                    columnas_extra = [
                        c for c in todas_columnas
                        if c not in (columna_fecha, columna_valor)
                        and not _es_columna_sistema(c)
                        and _columna_tiene_valores(_df_check, c)
                    ]
                    print(f"[SIIED DEBUG] Fallback 2: columnas_extra del archivo = {columnas_extra}")
                    
                    # Intentar leer tipos del step_data (selección del usuario)
                    step_data_fb2 = self.storage.get_step_data(self.PASO_VERIFICAR_DESAG) or {}
                    
                    if columnas_extra:
                        for idx_fb2, col_name in enumerate(columnas_extra):
                            # Verificar si ya existe un dominio con ese nombre
                            dominio_existente = DominioDesagregacion.objects.filter(
                                nombre__iexact=col_name.strip()
                            ).first()
                            # Prioridad: recolector > tipo existente > step_data > default
                            tipo_preferido = tipos_recolector.get(
                                col_name.lower(),
                                step_data_fb2.get(f'tipo_dominio_{idx_fb2}', None)
                            )
                            if dominio_existente:
                                tipo_final = tipo_preferido or dominio_existente.tipo
                                # Si el tipo preferido difiere del existente, creamos uno nuevo
                                # con el tipo correcto (get_or_create por nombre+tipo)
                                if tipo_preferido and tipo_preferido != dominio_existente.tipo:
                                    columnas_desag.append({
                                        'columna': col_name,
                                        'accion': 'crear',
                                        'dominio_id': None,
                                        'tipo': tipo_final
                                    })
                                else:
                                    columnas_desag.append({
                                        'columna': col_name,
                                        'accion': 'asociar',
                                        'dominio_id': dominio_existente.id,
                                        'tipo': tipo_final
                                    })
                            else:
                                tipo_final = tipo_preferido or 'tematica'
                                columnas_desag.append({
                                    'columna': col_name,
                                    'accion': 'crear',
                                    'dominio_id': None,
                                    'tipo': tipo_final
                                })
                        print(f"[SIIED DEBUG] Decisiones auto-generadas (Fallback 2): {columnas_desag}")
                
                # ═══════════════════════════════════════════════════════════════
                # CORRECCIÓN CRÍTICA: Forzar tipos del recolector sobre cualquier
                # decisión ya tomada (JSON del form, Fallback 1, o Fallback 2).
                # Si el recolector dijo 'geografica' y la decisión dice 'asociar'
                # un dominio 'tematica', cambiamos a 'crear' uno nuevo.
                # ═══════════════════════════════════════════════════════════════
                for decision in columnas_desag:
                    col_name = decision.get('columna', '')
                    tipo_recolector = tipos_recolector.get(col_name.lower())
                    if tipo_recolector:
                        tipo_actual = decision.get('tipo')
                        if tipo_actual != tipo_recolector:
                            print(f"[SIIED DEBUG] CORRECCIÓN tipo '{col_name}': {tipo_actual} -> {tipo_recolector}")
                            decision['tipo'] = tipo_recolector
                            if decision.get('accion') == 'asociar':
                                print(f"[SIIED DEBUG] CORRECCIÓN acción '{col_name}': asociar -> crear (tipo cambió)")
                                decision['accion'] = 'crear'
                                decision['dominio_id'] = None
                print(f"[SIIED DEBUG] Decisiones finales tras corrección recolector: {columnas_desag}")

                # Aplicar padres del recolector a decisiones que no traen padre explícito
                for decision in columnas_desag:
                    if decision.get('accion') == 'ignorar':
                        continue
                    if not decision.get('padre'):
                        padre_rec = padres_recolector.get(decision.get('columna', '').lower())
                        if padre_rec:
                            decision['padre'] = padre_rec
                            print(f"[SIIED DEBUG] Padre recolector aplicado a '{decision['columna']}': {padre_rec}")

                # Tracking de dominios y desagregaciones nuevas vs existentes
                dominios_nuevos = set()
                dominios_existentes = set()
                desagregaciones_nuevas = set()
                desagregaciones_existentes = set()

                # Mapeo: columna → {dominio, tipo, desag_map: {valor→Desagregacion}}
                col_dominio_map = {}
                for decision in columnas_desag:
                    if decision.get('accion') == 'ignorar':
                        print(f"[SIIED DEBUG] Ignorando columna '{decision.get('columna')}' según decisión del usuario")
                        continue
                    col_name = decision['columna']
                    dominio = None
                    
                    dominio_existente_usado = False
                    if decision['accion'] == 'asociar' and decision.get('dominio_id'):
                        # Usar dominio existente TAL CUAL (sin modificar su tipo global)
                        try:
                            dominio = DominioDesagregacion.objects.get(id=decision['dominio_id'])
                            dominio_existente_usado = True
                        except DominioDesagregacion.DoesNotExist:
                            print(f"[SIIED DEBUG] Dominio id={decision['dominio_id']} no existe, creando nuevo")
                            dominio = None
                    
                    if decision['accion'] == 'crear' or (decision['accion'] == 'asociar' and dominio is None):
                        # Crear nuevo dominio — busca por (nombre, tipo) para NO tocar
                        # dominios existentes de otros usuarios con tipo diferente.
                        tipo = decision.get('tipo') or 'tematica'
                        dominio, _created = DominioDesagregacion.objects.get_or_create(
                            nombre=col_name.strip(),
                            tipo=tipo,
                            defaults={'tipo_agregacion_total': 'suma'}
                        )
                        if _created:
                            print(f"[SIIED DEBUG] Dominio CREADO: '{col_name.strip()}' tipo={tipo}")
                            dominios_nuevos.add(dominio.nombre)
                        else:
                            print(f"[SIIED DEBUG] Dominio reutilizado: '{dominio.nombre}' tipo={dominio.tipo}")
                            dominios_existentes.add(dominio.nombre)
                    else:
                        if dominio_existente_usado and dominio:
                            dominios_existentes.add(dominio.nombre)
                    
                    if dominio:
                        # Asociar dominio al indicador en la M2M correcta
                        # y removerlo de la M2M opuesta por si cambió de tipo
                        if dominio.tipo == 'tematica':
                            indicador.dominios_desagregacion_tematica.add(dominio)
                            indicador.dominios_desagregacion_geografica.remove(dominio)
                        else:
                            indicador.dominios_desagregacion_geografica.add(dominio)
                            indicador.dominios_desagregacion_tematica.remove(dominio)
                        print(f"[SIIED DEBUG] Dominio '{dominio.nombre}' asociado al indicador como {dominio.tipo}")
                        
                        # Pre-construir mapa de desagregaciones
                        col_dominio_map[col_name] = {
                            'dominio': dominio,
                            'desag_map': {}
                        }

                print(f"[SIIED DEBUG] col_dominio_map final: {list(col_dominio_map.keys())}")
                print(f"[SIIED DEBUG] Total columnas con dominio asignado: {len(col_dominio_map)}")

                # ═══════════════════════════════════════════════════════════════
                # JERARQUÍA: resolver dominio_padre entre dominios.
                # decision['padre'] puede ser 'col:<columna>' (otra columna del
                # archivo) o 'dom:<id>' (dominio existente en BD).
                # ═══════════════════════════════════════════════════════════════
                for decision in columnas_desag:
                    if decision.get('accion') == 'ignorar':
                        continue
                    col_name = decision.get('columna')
                    padre_ref = decision.get('padre')
                    info = col_dominio_map.get(col_name)
                    if not padre_ref or not info:
                        continue
                    dominio_hijo = info['dominio']
                    dominio_padre = None
                    if padre_ref.startswith('col:'):
                        padre_col = padre_ref[4:]
                        padre_info = col_dominio_map.get(padre_col)
                        if padre_info:
                            dominio_padre = padre_info['dominio']
                        else:
                            print(f"[SIIED DEBUG] Padre '{padre_col}' de '{col_name}' no está en col_dominio_map (ignorada o sin dominio)")
                    elif padre_ref.startswith('dom:'):
                        try:
                            dominio_padre = DominioDesagregacion.objects.get(id=int(padre_ref[4:]))
                        except (DominioDesagregacion.DoesNotExist, ValueError):
                            print(f"[SIIED DEBUG] Dominio padre id={padre_ref[4:]} no existe")
                    if dominio_padre and dominio_padre.id != dominio_hijo.id:
                        if dominio_hijo.dominio_padre_id != dominio_padre.id:
                            dominio_hijo.dominio_padre = dominio_padre
                            dominio_hijo.save(update_fields=['dominio_padre'])
                            print(f"[SIIED DEBUG] Jerarquía: '{dominio_hijo.nombre}' -> padre '{dominio_padre.nombre}'")
                        info['padre_col'] = padre_ref[4:] if padre_ref.startswith('col:') else None

                # Aplicar metadata del archivo y campos manuales al indicador
                paso_4_data = self.get_cleaned_data_for_step(self.PASO_CARGAR_METADATA) or {}
                self._aplicar_metadata_a_indicador(indicador, paso_4_data, carga_serie)

                # 4. Leer archivo CSV
                archivo_path = carga_serie.archivo_datos_csv.path if carga_serie.archivo_datos_csv else carga_serie.archivo_datos_xlsx.path
                
                if archivo_path.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(archivo_path)
                else:
                    df = _leer_csv_auto_sep(archivo_path)
                
                # 5. Importar datos con desagregaciones
                columna_fecha = paso_6_data['columna_fecha']
                columna_valor = paso_6_data['columna_valor']
                
                registros_exitosos = 0
                registros_error = 0
                _debug_first_row = True
                
                for index, row in df.iterrows():
                    try:
                        fecha_valor = row[columna_fecha]
                        valor = row[columna_valor]
                        
                        # Convertir fecha (año int/float/string o fecha completa)
                        fecha_dato = _parsear_fecha_dato(fecha_valor)
                        if fecha_dato is None:
                            registros_error += 1
                            continue

                        # Limpiar valor numérico
                        valor_limpio, es_sin_dato = _limpiar_valor_numerico(valor)
                        if valor_limpio is None:
                            if not es_sin_dato:
                                registros_error += 1
                            # Sin dato (guión/vacío): no crear registro
                            continue
                        
                        # Crear dato
                        from .models import Dato
                        dato = Dato.objects.create(
                            indicador=indicador,
                            fecha_dato=fecha_dato,
                            valor_dato=valor_limpio
                        )
                        
                        # Asignar desagregaciones desde columnas detectadas
                        desag_tematicas = []
                        desag_geograficas = []
                        
                        for col_name, info in col_dominio_map.items():
                            if col_name not in df.columns:
                                continue
                            valor_celda = str(row[col_name]).strip() if pd.notna(row[col_name]) else ''
                            if not valor_celda:
                                continue
                            
                            dominio = info['dominio']
                            desag_map = info['desag_map']
                            
                            # Buscar o crear la desagregación (nombre
                            # normalizado + match case-insensitive en el
                            # dominio para no duplicar variantes de texto)
                            if valor_celda not in desag_map:
                                desag_obj, desag_created = _get_or_create_desagregacion(
                                    valor_celda, dominio, col_name
                                )
                                if desag_created:
                                    desagregaciones_nuevas.add(f"{dominio.nombre}: {valor_celda}")
                                else:
                                    desagregaciones_existentes.add(f"{dominio.nombre}: {valor_celda}")
                                desag_map[valor_celda] = desag_obj
                            
                            desag_obj = desag_map[valor_celda]

                            # Inferir desagregacion_padre: si este dominio tiene
                            # padre declarado vía otra columna del archivo, vincular
                            # el valor hijo con el valor padre de la misma fila.
                            padre_col = info.get('padre_col')
                            if padre_col and padre_col in df.columns:
                                valor_padre = str(row[padre_col]).strip() if pd.notna(row[padre_col]) else ''
                                padre_info = col_dominio_map.get(padre_col)
                                if valor_padre and padre_info:
                                    padre_desag_map = padre_info['desag_map']
                                    if valor_padre not in padre_desag_map:
                                        padre_desag_map[valor_padre], _ = _get_or_create_desagregacion(
                                            valor_padre, padre_info['dominio'], padre_col
                                        )
                                    desag_padre_obj = padre_desag_map[valor_padre]
                                    if desag_obj.desagregacion_padre_id != desag_padre_obj.id:
                                        desag_obj.desagregacion_padre = desag_padre_obj
                                        desag_obj.save(update_fields=['desagregacion_padre'])

                            if dominio.tipo == 'tematica':
                                desag_tematicas.append(desag_obj)
                            else:
                                desag_geograficas.append(desag_obj)
                        
                        # Asignar M2M
                        if desag_tematicas:
                            dato.desagregaciones_tematicas.set(desag_tematicas)
                        if desag_geograficas:
                            dato.desagregaciones_geograficas.set(desag_geograficas)
                        
                        if _debug_first_row:
                            print(f"[SIIED DEBUG] Primera fila: desag_tematicas={[d.nombre for d in desag_tematicas]}, desag_geograficas={[d.nombre for d in desag_geograficas]}")
                            _debug_first_row = False
                        
                        registros_exitosos += 1
                        
                    except Exception as e:
                        registros_error += 1
                        continue
                
                # 4. Crear/actualizar gráfico y sus series cartesianas
                #    DESPUÉS de importar datos para que las desagregaciones ya existan
                #    Se pasan preferencias del recolector si existen
                self._crear_series_grafico(indicador, carga_serie=carga_serie)

                # 5. Actualizar carga
                carga_serie.estado = 'procesado'
                carga_serie.fecha_procesamiento = timezone.now()
                carga_serie.registros_procesados = len(df)
                carga_serie.registros_exitosos = registros_exitosos
                carga_serie.registros_error = registros_error
                carga_serie.indicador = indicador
                carga_serie.log_procesamiento = (
                    f"Dominios nuevos ({len(dominios_nuevos)}): {', '.join(sorted(dominios_nuevos))}\n"
                    f"Dominios reutilizados ({len(dominios_existentes)}): {', '.join(sorted(dominios_existentes))}\n"
                    f"Desagregaciones nuevas ({len(desagregaciones_nuevas)}): {', '.join(sorted(desagregaciones_nuevas))}\n"
                    f"Desagregaciones reutilizadas ({len(desagregaciones_existentes)}): {', '.join(sorted(desagregaciones_existentes))}"
                )
                carga_serie.save()
                self._notificar_carga_procesada(carga_serie)
            
            nombre_archivo = os.path.basename(carga_serie.archivo_datos_xlsx.name)
            
            dominios_nuevos = sorted(dominios_nuevos)
            dominios_existentes = sorted(dominios_existentes)
            desagregaciones_nuevas = sorted(desagregaciones_nuevas)
            desagregaciones_existentes = sorted(desagregaciones_existentes)

            mensaje = f'Serie "{nombre_archivo}" importada exitosamente. {registros_exitosos} registros creados.'
            if dominios_nuevos or dominios_existentes:
                mensaje += f' Dominios: {len(dominios_nuevos)} nuevos, {len(dominios_existentes)} reutilizados.'
            if desagregaciones_nuevas or desagregaciones_existentes:
                mensaje += f' Desagregaciones: {len(desagregaciones_nuevas)} nuevas, {len(desagregaciones_existentes)} reutilizadas.'

            return {
                'mensaje': mensaje,
                'carga_id': carga_serie.id,
                'indicador_id': indicador.id,
                'dominios_nuevos': dominios_nuevos,
                'dominios_existentes': dominios_existentes,
                'desagregaciones_nuevas': desagregaciones_nuevas,
                'desagregaciones_existentes': desagregaciones_existentes,
            }
            
        except Exception as e:
            # Marcar como error
            carga_serie.estado = 'error'
            carga_serie.mensaje_error = str(e)
            carga_serie.save()
            self._notificar_carga_procesada(carga_serie)
            raise ValueError(
                f"Error al procesar la serie de datos: {str(e)}. Por favor, verifica que el archivo esté en el formato correcto "
                "y que las columnas de fecha y valor estén presentes. Si el problema persiste, contacta al soporte técnico."
            )
    
    def _procesar_flujo_c(self, data):
        """Procesa Flujo C: Completo (conjunto_datos + Serie) - Procesamiento Cartesiano + Validación"""
        from django.db import transaction
        from django.utils import timezone
        import os
        
        carga_conjunto_datos_id = self.storage.extra_data.get('carga_conjunto_datos_id')
        carga_serie_id = self.storage.extra_data.get('carga_serie_id')
        
        if not carga_conjunto_datos_id or not carga_serie_id:
            raise ValueError(
                "No se encontró la información de las cargas de conjunto_datos y serie. Por favor, regresa al paso de selección "
                "de fuente y selecciona ambas cargas válidas. Si el problema persiste, verifica que las cargas existan en el sistema."
            )
        
        try:
            carga_conjunto_datos = CargaConjuntoDatos.objects.get(id=carga_conjunto_datos_id)
            carga_serie = CargaSerieIndicador.objects.get(id=carga_serie_id)
            
            # Marcar ambas como en proceso
            carga_conjunto_datos.estado = 'procesando'
            carga_conjunto_datos.save()
            carga_serie.estado = 'procesando'
            carga_serie.save()
            
            # Obtener datos de los pasos
            paso_3_data = self.get_cleaned_data_for_step(self.PASO_CONFIG_MICRODATA) or {}
            paso_5_data = self.get_cleaned_data_for_step(self.PASO_CONFIG_INDICADOR_C) or {}
            paso_7_data = self.get_cleaned_data_for_step(self.PASO_REGLA_EXTRACCION_C) or {}
            paso_desag_data = self.get_cleaned_data_for_step(self.PASO_VERIFICAR_DESAG) or {}
            
            with transaction.atomic():
                # 1. Crear o asociar conjunto_datos
                if paso_3_data.get('opcion') == 'crear_nueva':
                    conjunto_datos = ConjuntoDatos.objects.create(
                        nombre=paso_3_data['nombre_conjunto_datos'],
                        descripcion=paso_3_data.get('descripcion_conjunto_datos', ''),
                        operacion=paso_3_data.get('operacion_estadistica'),
                        archivo_csv=carga_conjunto_datos.archivo_microdata_csv
                    )
                else:
                    if 'conjunto_datos_existente' not in paso_3_data:
                        raise ValueError("No se seleccionó una conjunto_datos existente. Por favor, completa el paso de configuración de conjunto_datos.")
                    conjunto_datos = paso_3_data['conjunto_datos_existente']
                
                # 2. Crear o asociar Indicador
                if paso_5_data.get('opcion') == 'crear_nuevo':
                    indicador = Indicador.objects.create(
                        codigo_indicador=paso_5_data.get('codigo_indicador', ''),
                        nombre=paso_5_data['nombre'],
                        sigla=paso_5_data.get('sigla', ''),
                        subtema=paso_5_data['subtema'],
                        conjunto_datos=conjunto_datos,
                        activo=True
                    )
                    indicador.subtemas_adicionales.set(
                        paso_5_data.get('subtemas_adicionales') or [])
                else:
                    if 'indicador_existente' not in paso_5_data:
                        raise ValueError("No se seleccionó un indicador existente. Por favor, completa el paso de configuración del indicador.")
                    indicador = paso_5_data['indicador_existente']
                    indicador.datos.all().delete()
                    indicador.conjunto_datos = conjunto_datos
                    indicador.save()
                    # .add() y no .set(): no pisar clasificaciones previas
                    adic = paso_5_data.get('subtemas_adicionales')
                    if adic:
                        indicador.subtemas_adicionales.add(*adic)
                
                # 3. Asignar dominios de desagregación seleccionados en el wizard
                #    SIEMPRE aplicar .set() — selección vacía limpia dominios anteriores.
                indicador.dominios_desagregacion_geografica.set(
                    paso_desag_data.get('dominios_desagregacion_geografica') or []
                )
                indicador.dominios_desagregacion_tematica.set(
                    paso_desag_data.get('dominios_desagregacion_tematica') or []
                )
                
                # 4. Cargar metadata del indicador desde CargaSerieIndicador
                # TODO: Parsear metadata.csv de carga_serie y aplicar al indicador
                
                es_calculo_complejo = self.storage.extra_data.get('es_calculo_complejo', False)

                if es_calculo_complejo:
                    # ==============================================================
                    # CÁLCULO COMPLEJO: importar serie precalculada + enlazar conjunto_datos
                    # SIN aplicar reglas de extracción cartesiana.
                    # El organismo ya realizó el cálculo externamente.
                    # ==============================================================
                    import pandas as pd

                    archivo_path = (
                        carga_serie.archivo_datos_csv.path
                        if carga_serie.archivo_datos_csv
                        else carga_serie.archivo_datos_xlsx.path
                    )
                    if archivo_path.endswith(('.xlsx', '.xls')):
                        df_serie = pd.read_excel(archivo_path)
                    else:
                        df_serie = _leer_csv_auto_sep(archivo_path)

                    registros_exitosos = 0
                    registros_error = 0
                    paso_mapeo = self.get_cleaned_data_for_step(self.PASO_VALIDAR_CON_SERIE) or {}
                    _kw_fecha = {'año', 'anio', 'year', 'fecha', 'date', 'periodo'}
                    columna_fecha = paso_mapeo.get('columna_fecha') or next(
                        (col for col in df_serie.columns if col.lower().strip() in _kw_fecha),
                        df_serie.columns[0]
                    )
                    columna_valor = paso_mapeo.get('columna_valor') or next(
                        (col for col in df_serie.columns if col.lower() == 'valor'),
                        next((col for col in df_serie.columns if col != columna_fecha), df_serie.columns[-1])
                    )

                    from .models import Dato
                    for _, row in df_serie.iterrows():
                        try:
                            fecha_val = row[columna_fecha]
                            fecha_dato = _parsear_fecha_dato(fecha_val)
                            if fecha_dato is None:
                                registros_error += 1
                                continue
                            valor_limpio, es_sin_dato = _limpiar_valor_numerico(row[columna_valor])
                            if valor_limpio is None:
                                if not es_sin_dato:
                                    registros_error += 1
                                continue
                            Dato.objects.create(
                                indicador=indicador,
                                fecha_dato=fecha_dato,
                                valor_dato=valor_limpio
                            )
                            registros_exitosos += 1
                        except Exception:
                            registros_error += 1

                    # Asociar conjunto_datos como referencia (sin procesar extracción)
                    indicador.conjunto_datos = conjunto_datos
                    indicador.save()

                    # Marcar conjunto_datos como procesada pero sin extracción
                    carga_conjunto_datos.estado = 'procesado'
                    carga_conjunto_datos.fecha_procesamiento = timezone.now()
                    carga_conjunto_datos.log_procesamiento = (
                        'Cálculo complejo: conjunto_datos enlazada como referencia sin extracción cartesiana.'
                    )
                    carga_conjunto_datos.conjunto_datos = conjunto_datos
                    carga_conjunto_datos.registros_procesados = len(df_serie)
                    carga_conjunto_datos.registros_exitosos = registros_exitosos
                    carga_conjunto_datos.registros_error = registros_error
                    carga_conjunto_datos.save()
                    self._notificar_carga_procesada(carga_conjunto_datos)

                    carga_serie.estado = 'procesado'
                    carga_serie.fecha_procesamiento = timezone.now()
                    carga_serie.registros_procesados = len(df_serie)
                    carga_serie.registros_exitosos = registros_exitosos
                    carga_serie.registros_error = registros_error
                    carga_serie.indicador = indicador
                    carga_serie.save()
                    self._notificar_carga_procesada(carga_serie)

                    regla = None  # Sin regla de extracción para cálculos complejos
                    resultado = {'registros_exitosos': registros_exitosos, 'registros_procesados': len(df_serie)}

                else:
                    # ==============================================================
                    # FLUJO NORMAL: extracción cartesiana desde conjunto_datos
                    # ==============================================================
                    from .models import ReglaExtraccion
                    import json

                    columnas_fuente_str = paso_7_data['columnas_fuente']
                    columnas_fuente = [c.strip() for c in columnas_fuente_str.split(',')]
                    orden_desag_str = paso_7_data.get('orden_desagregaciones', '')
                    orden_desag = [d.strip() for d in orden_desag_str.split(',') if d.strip()]

                    regla = ReglaExtraccion.objects.create(
                        indicador=indicador,
                        columna_fecha=paso_7_data['columna_fecha'],
                        columnas_fuente=columnas_fuente,
                        formula=paso_7_data['formula'],
                        filtros=json.loads(paso_7_data.get('filtros_json', '{}')),
                        orden_desagregaciones=orden_desag,
                        activo=True
                    )

                    from .procesamiento_normalizado import procesar_conjunto_datos_a_indicador
                    
                    crear_faltantes = paso_6_data.get('crear_faltantes_auto', True)
                    
                    resultado = procesar_conjunto_datos_a_indicador(
                        carga_conjunto_datos_id=carga_conjunto_datos.id,
                        regla_extraccion_id=regla.id,
                        crear_faltantes=crear_faltantes
                    )

                    # Crear/actualizar gráfico y sus series cartesianas
                    self._crear_series_grafico(indicador)

                    carga_conjunto_datos.estado = 'exitoso'
                    carga_conjunto_datos.fecha_procesamiento = timezone.now()
                    carga_conjunto_datos.registros_procesados = resultado.get('registros_procesados', 0)
                    carga_conjunto_datos.registros_exitosos = resultado.get('registros_exitosos', 0)
                    carga_conjunto_datos.registros_error = resultado.get('registros_error', 0)
                    carga_conjunto_datos.conjunto_datos = conjunto_datos
                    carga_conjunto_datos.save()
                    self._notificar_carga_procesada(carga_conjunto_datos)

                    carga_serie.estado = 'exitoso'
                    carga_serie.fecha_procesamiento = timezone.now()
                    carga_serie.indicador = indicador
                    carga_serie.save()
                    self._notificar_carga_procesada(carga_serie)

            nombre_archivo_micro = os.path.basename(
                carga_conjunto_datos.archivo_microdata_xlsx.name
                if carga_conjunto_datos.archivo_microdata_xlsx else '(sin archivo)'
            )
            nombre_archivo_serie = os.path.basename(
                carga_serie.archivo_datos_xlsx.name
                if carga_serie.archivo_datos_xlsx else '(sin archivo)'
            )
            modo = 'cálculo complejo (serie precalculada)' if es_calculo_complejo else 'extracción cartesiana'

            return_data = {
                'mensaje': (
                    f'Procesamiento exitoso [{modo}]. '
                    f'conjunto_datos "{nombre_archivo_micro}" y serie "{nombre_archivo_serie}". '
                    f'{resultado.get("registros_exitosos", 0)} datos cargados.'
                ),
                'carga_conjunto_datos_id': carga_conjunto_datos.id,
                'carga_serie_id': carga_serie.id,
                'indicador_id': indicador.id,
            }
            if regla:
                return_data['regla_id'] = regla.id
            return return_data
            
        except Exception as e:
            # Marcar ambas como error
            carga_conjunto_datos.estado = 'error'
            carga_conjunto_datos.mensaje_error = str(e)
            carga_conjunto_datos.save()
            self._notificar_carga_procesada(carga_conjunto_datos)
            carga_serie.estado = 'error'
            carga_serie.mensaje_error = str(e)
            carga_serie.save()
            self._notificar_carga_procesada(carga_serie)
            raise ValueError(
                f"Error al procesar el flujo completo: {str(e)}. Por favor, verifica que ambos archivos estén en el formato correcto "
                "y que todos los datos requeridos estén presentes. Si el problema persiste, contacta al soporte técnico."
            )
    
    def _procesar_flujo_d(self, data):
        """Procesa Flujo D: Actualizar Existente - Actualización de indicador con nuevos datos"""
        from django.db import transaction
        from django.utils import timezone
        import pandas as pd
        import os
        
        # Obtener datos de los pasos
        paso_3_data = self.get_cleaned_data_for_step(self.PASO_SELECCIONAR_CARGA)
        paso_5_data = self.get_cleaned_data_for_step(self.PASO_CONFIRMAR_CAMBIOS)
        
        # Indicador fue seleccionado en paso 1 (seleccion_fuente → indicador_existente)
        indicador_id = self.storage.extra_data.get('indicador_existente_id')
        if not indicador_id:
            raise ValueError(
                "No se encontró el indicador seleccionado. Por favor, regresa al paso de selección "
                "de fuente y selecciona un indicador existente."
            )
        indicador = Indicador.objects.get(id=indicador_id)
        tipo_carga = paso_3_data['tipo_carga']
        accion_datos = paso_5_data['accion_datos']
        
        try:
            with transaction.atomic():
                # Determinar qué tipo de carga es
                if tipo_carga == 'serie':
                    carga_serie = paso_3_data['carga_serie']
                    
                    # Marcar como en proceso
                    carga_serie.estado = 'procesando'
                    carga_serie.save()
                    
                    # Manejar acción sobre datos existentes
                    if accion_datos == 'reemplazar':
                        indicador.datos.all().delete()
                    
                    # Leer archivo
                    archivo_path = carga_serie.archivo_datos_csv.path if carga_serie.archivo_datos_csv else carga_serie.archivo_datos_xlsx.path
                    
                    if archivo_path.endswith(('.xlsx', '.xls')):
                        df = pd.read_excel(archivo_path)
                    else:
                        df = _leer_csv_auto_sep(archivo_path)
                    
                    # Importar datos (asumiendo columnas estándar)
                    # TODO: Usar mapeo de columnas si está disponible
                    registros_exitosos = 0
                    registros_error = 0
                    
                    # Detectar columnas compatibles con plantilla estándar (Año, Valor)
                    _kw_fecha_d = {'año', 'anio', 'year', 'fecha', 'date', 'periodo'}
                    fecha_col = next(
                        (col for col in df.columns if col.lower().strip() in _kw_fecha_d),
                        df.columns[0]
                    )
                    valor_col = next(
                        (col for col in df.columns if 'valor' in col.lower() or col.lower() in {'dato', 'resultado'}),
                        df.columns[1]
                    )

                    if accion_datos != 'mantener':
                        for index, row in df.iterrows():
                            try:
                                from .models import Dato
                                
                                fecha_valor = row[fecha_col]
                                valor = row[valor_col]
                                
                                fecha_dato = _parsear_fecha_dato(fecha_valor)
                                if fecha_dato is None:
                                    registros_error += 1
                                    continue

                                Dato.objects.create(
                                    indicador=indicador,
                                    fecha_dato=fecha_dato,
                                    valor_dato=float(valor)
                                )
                                registros_exitosos += 1
                                
                            except Exception as e:
                                registros_error += 1
                                continue
                    
                    # Actualizar carga
                    carga_serie.estado = 'exitoso'
                    carga_serie.fecha_procesamiento = timezone.now()
                    carga_serie.registros_procesados = len(df)
                    carga_serie.registros_exitosos = registros_exitosos
                    carga_serie.registros_error = registros_error
                    carga_serie.indicador = indicador
                    carga_serie.save()
                    self._notificar_carga_procesada(carga_serie)
                    
                    nombre_archivo = os.path.basename(carga_serie.archivo_datos_xlsx.name)
                    mensaje = f'Indicador "{indicador.nombre}" actualizado con serie "{nombre_archivo}". {registros_exitosos} registros procesados.'
                    carga_id = carga_serie.id
                    
                elif tipo_carga == 'conjunto_datos':
                    carga_conjunto_datos = paso_3_data['carga_conjunto_datos']
                    
                    # Marcar como en proceso
                    carga_conjunto_datos.estado = 'procesando'
                    carga_conjunto_datos.save()
                    
                    # Manejar acción sobre datos existentes
                    if accion_datos == 'reemplazar':
                        indicador.datos.all().delete()
                    
                    # Para conjunto_datos, necesitamos una regla de extracción existente
                    from .models import ReglaExtraccion
                    
                    regla = ReglaExtraccion.objects.filter(indicador=indicador, activo=True).first()
                    
                    if not regla:
                        raise ValueError("No se encontró una regla de extracción activa para este indicador")
                    
                    if accion_datos != 'mantener':
                        # Ejecutar procesamiento cartesiano
                        from .procesamiento_normalizado import procesar_conjunto_datos_a_indicador
                        
                        resultado = procesar_conjunto_datos_a_indicador(
                            carga_conjunto_datos_id=carga_conjunto_datos.id,
                            regla_extraccion_id=regla.id
                        )
                        
                        registros_exitosos = resultado.get('registros_exitosos', 0)
                        registros_error = resultado.get('registros_error', 0)
                    else:
                        registros_exitosos = 0
                        registros_error = 0
                    
                    # Actualizar carga
                    carga_conjunto_datos.estado = 'exitoso'
                    carga_conjunto_datos.fecha_procesamiento = timezone.now()
                    carga_conjunto_datos.registros_procesados = resultado.get('registros_procesados', 0) if accion_datos != 'mantener' else 0
                    carga_conjunto_datos.registros_exitosos = registros_exitosos
                    carga_conjunto_datos.registros_error = registros_error
                    carga_conjunto_datos.save()
                    self._notificar_carga_procesada(carga_conjunto_datos)
                    
                    nombre_archivo = os.path.basename(carga_conjunto_datos.archivo_microdata_xlsx.name)
                    mensaje = f'Indicador "{indicador.nombre}" actualizado con conjunto_datos "{nombre_archivo}". {registros_exitosos} registros procesados.'
                    carga_id = carga_conjunto_datos.id
                
                return {
                    'mensaje': mensaje,
                    'indicador_id': indicador.id,
                    'carga_id': carga_id,
                    'accion': accion_datos
                }
                
        except Exception as e:
            # Marcar carga como error
            if tipo_carga == 'serie':
                carga_serie.estado = 'error'
                carga_serie.mensaje_error = str(e)
                carga_serie.save()
                self._notificar_carga_procesada(carga_serie)
            else:
                carga_conjunto_datos.estado = 'error'
                carga_conjunto_datos.mensaje_error = str(e)
                carga_conjunto_datos.save()
                self._notificar_carga_procesada(carga_conjunto_datos)
            
            raise ValueError(
                f"Error al actualizar el indicador: {str(e)}. Por favor, verifica que los datos estén correctos "
                "y que la carga seleccionada sea válida. Si el problema persiste, contacta al soporte técnico."
            )

    def _crear_series_grafico(self, indicador, carga_serie=None):
        """
        Crea o actualiza el Gráfico por defecto del indicador y genera GraficoSeries
        a partir de las COMBINACIONES REALES de desagregaciones presentes en los
        datos del indicador (una desagregación por dominio en cada serie).

        Esto reemplaza al antiguo producto cartesiano geo × temática:
        - Respeta la jerarquía de dominios implícitamente: un valor de dominio
          hijo (ej. Barrio) solo aparece combinado con su padre real (Comuna),
          nunca en un producto cruzado inválido.
        - Nunca genera series sin datos: cada serie corresponde a una tupla de
          desagregaciones que efectivamente existe en al menos un Dato.
        - Si el indicador no tiene datos/desagregaciones, crea una serie "Total".

        Si carga_serie tiene preferencias_grafico (del recolector), se usan como defaults.
        """
        # Obtener preferencias del recolector si existen
        prefs = {}
        if carga_serie and hasattr(carga_serie, 'preferencias_grafico') and carga_serie.preferencias_grafico:
            prefs = carga_serie.preferencias_grafico

        tipo_grafico = prefs.get('tipo_grafico', 'line')
        titulo = prefs.get('titulo', indicador.nombre)
        eje_x = prefs.get('eje_x', 'Año')
        eje_y = prefs.get('eje_y', indicador.unidad_medida or '')

        grafico = indicador.graficos.filter(activo=True).first()
        if not grafico:
            grafico = Grafico.objects.create(
                indicador=indicador,
                nombre=f'Gráfico - {indicador.nombre}',
                titulo=titulo,
                tipo_grafico=tipo_grafico,
                eje_x_titulo=eje_x,
                eje_y_titulo=eje_y,
                activo=True,
            )
        else:
            # Si ya existía el gráfico pero no tenía título, se lo asignamos
            if not grafico.titulo:
                grafico.titulo = titulo
                grafico.save(update_fields=['titulo'])

        # ── Combinaciones REALES: cada serie corresponde exactamente a una
        # combinación de desagregaciones que existe en los Dato del indicador.
        # (Antes se hacía producto cartesiano con TODAS las desagregaciones
        # del dominio, incluyendo valores de otros indicadores del mismo
        # dominio, lo que creaba series "fantasma" sin datos.)
        from itertools import chain

        datos_qs = (
            Dato.objects.filter(indicador=indicador)
            .prefetch_related('desagregaciones_geograficas', 'desagregaciones_tematicas')
        )

        combos_vistos = {}
        # iterator() tras prefetch_related() exige chunk_size (Django ≥4.2);
        # el prefetch se aplica por lote, así se mantiene el streaming.
        for dato in datos_qs.iterator(chunk_size=2000):
            desags = list(chain(
                dato.desagregaciones_geograficas.all(),
                dato.desagregaciones_tematicas.all(),
            ))
            if not desags:
                continue
            # Orden determinista por dominio+nombre para nombres estables
            desags.sort(key=lambda d: (d.dominio_id or 0, d.nombre))
            key = tuple(d.id for d in desags)
            combos_vistos.setdefault(key, desags)

        combos = list(combos_vistos.values())
        if not combos:
            combos = [()]

        print(f"[SIIED DEBUG] _crear_series_grafico: {len(combos)} combinaciones reales encontradas")

        # Eliminar series generadas automáticamente previamente
        grafico.series.all().delete()

        for orden, combo in enumerate(combos):
            serie = GraficoSerie.objects.create(
                grafico=grafico,
                nombre_personalizado=' - '.join(d.nombre for d in combo) or 'Total',
                orden=orden,
            )
            if combo:
                serie.desagregaciones.set(combo)
                serie.sincronizar_fks_legacy(combo)

        print(f"[SIIED DEBUG] _crear_series_grafico: {len(combos)} series creadas")

        return grafico

    def _aplicar_metadata_a_indicador(self, indicador, paso_form_data, carga_serie=None):
        """Aplica metadata al indicador desde el archivo de metadata y/o los campos manuales del formulario."""
        from .utils_wizard import ParseadorMetadata

        MAPA_CAMPOS = {
            # MSD + aliases legacy (archivos antiguos siguen importando)
            'Descripcion_Indicador': 'descripcion_indicador',
            'Definiciones_Conceptos': 'descripcion_indicador',
            'Objetivo': 'objetivo',
            'Metodo_Medicion': 'metodo_medicion',
            'Formula': 'formula_ficha',
            'Variables': 'variables',
            'Unidad_Medida': 'unidad_medida',
            'Alcance_Tematico': 'alcance_tematico',
            'Desagregacion_Tematica': 'alcance_tematico',
            'Cobertura_Geografica': 'cobertura_geografica',
            'Desagregacion_Geografica': 'cobertura_geografica',
            'Nomenclaturas_Clasificaciones': 'nomenclaturas_clasificaciones',
            'Poblacion_Objetivo': 'poblacion_objetivo',
            'Periodo_Referencia': 'periodo_referencia',
            'Periodo_Base': 'periodo_base',
            'Frecuencia_Difusion': 'frecuencia_difusion',
            'Periodicidad': 'frecuencia_difusion',
            'Serie_Historica_Disponible': 'serie_historica_disponible',
            'Medios_Difusion': 'medios_difusion',
            'Fuente_Datos': 'fuente_datos',
            'Entidad_Responsable': 'entidad_responsable',
            'Responsable': 'entidad_responsable',
            'Comentarios_Adicionales': 'comentarios_adicionales',
            'Observaciones': 'comentarios_adicionales',
            'Correo_Contacto': 'correo_contacto',
            'Telefono_Contacto': 'telefono_contacto',
            'Grupo_Indicador': 'grupo_indicador',
            'Nombre_Conjunto_conjunto_datos': 'nombre_conjunto_datos',
            'Nombre_Conjunto_Datos': 'nombre_conjunto_datos',
            'Referencias': 'referencias',
            'Nombre_Responsable_Validacion': 'nombre_responsable_validacion',
            'Cargo_Responsable_Validacion': 'cargo_responsable_validacion',
            'Correo_Responsable_Validacion': 'correo_responsable_validacion',
            'Celular_Responsable_Validacion': 'celular_responsable_validacion',
        }
        MAPA_FECHAS = {
            'Fecha_Publicacion_Metadatos': 'fecha_publicacion_metadatos',
            'Fecha_Actualizacion': 'fecha_publicacion_metadatos',  # alias legacy → MSD 1.5
        }

        changed = False

        # 1. Parsear desde archivo (CSV o XLSX)
        if paso_form_data.get('cargar_metadata_auto', True) and carga_serie:
            import pandas as pd
            archivo_path = None
            if getattr(carga_serie, 'archivo_metadata_csv', None) and carga_serie.archivo_metadata_csv:
                archivo_path = carga_serie.archivo_metadata_csv.path
            elif getattr(carga_serie, 'archivo_metadata_xlsx', None) and carga_serie.archivo_metadata_xlsx:
                archivo_path = carga_serie.archivo_metadata_xlsx.path

            if archivo_path:
                resultado = ParseadorMetadata.parsear_metadata_indicador(archivo_path)
                if resultado['exitoso']:
                    meta = resultado['metadata']
                    # Normalizar encabezados al esquema canónico: acepta la
                    # plantilla oficial (ID_Indicador_SIIED, Cálculo del
                    # indicador…) además del MSD numerado viejo.
                    from .views_recoleccion import (
                        _normalizar_columnas_metadata,
                        _resolver_subtema_desde_texto,
                    )

                    def _canon(k):
                        return _normalizar_columnas_metadata([k])[0]

                    canon = {}
                    for _k, _v in meta.items():
                        canon.setdefault(_canon(_k), _v)

                    for col, campo in MAPA_CAMPOS.items():
                        val = (meta.get(col, '') or '').strip()
                        if not val:
                            val = str(canon.get(_canon(col), '') or '').strip()
                        if val and val != 'nan':
                            setattr(indicador, campo, val)
                            changed = True
                    for col, campo in MAPA_FECHAS.items():
                        val = (meta.get(col, '') or '').strip()
                        if not val:
                            val = str(canon.get(_canon(col), '') or '').strip()
                        if val and val != 'nan':
                            try:
                                setattr(indicador, campo, pd.to_datetime(val).date())
                                changed = True
                            except Exception:
                                pass
                    # Taxonomía oficial: Dominio/Tema/Subtema → subtema FK
                    subtema = _resolver_subtema_desde_texto(
                        canon.get('subtema'), canon.get('tema'),
                        canon.get('dominio'))
                    if subtema and indicador.subtema_id != subtema.id:
                        indicador.subtema = subtema
                        changed = True

                    # FKs por nombre — paridad con _actualizar_metadata_indicador_masiva
                    from .models import (Organismo, Suborganismo,
                                         OperacionEstadistica, normalizar_ascii)

                    def _buscar_por_nombre(qs, nombre):
                        nombre = str(nombre or '').strip()
                        if not nombre:
                            return None
                        obj = qs.filter(nombre__iexact=nombre).first()
                        if not obj:
                            norm = normalizar_ascii(nombre.lower())
                            obj = next((o for o in qs
                                        if normalizar_ascii(o.nombre.lower().strip()) == norm), None)
                        if not obj:
                            obj = qs.filter(nombre__icontains=nombre).first()
                        return obj

                    organismo = _buscar_por_nombre(
                        Organismo.objects.filter(activo=True),
                        canon.get('organismo_responsable'))
                    if organismo and indicador.organismo_responsable_id != organismo.id:
                        indicador.organismo_responsable = organismo
                        changed = True
                        sub = _buscar_por_nombre(
                            Suborganismo.objects.filter(
                                organismo=organismo, activo=True),
                            canon.get('suborganismo'))
                        if sub and indicador.suborganismo_id != sub.id:
                            indicador.suborganismo = sub
                            changed = True
                    operacion = _buscar_por_nombre(
                        OperacionEstadistica.objects.all(),
                        canon.get('operacion'))
                    if operacion and indicador.operacion_id != operacion.id:
                        indicador.operacion = operacion
                        changed = True
                    nombre_equipo = str(canon.get('equipo_responsable') or '').strip()
                    if nombre_equipo:
                        from .models import EquipoOrganismo
                        eq_qs = EquipoOrganismo.objects.filter(activo=True)
                        # Acotar al suborganismo/organismo ya resuelto
                        if indicador.suborganismo_id:
                            eq_qs = eq_qs.filter(suborganismo=indicador.suborganismo)
                        elif indicador.organismo_responsable_id:
                            eq_qs = eq_qs.filter(
                                suborganismo__organismo=indicador.organismo_responsable)
                        equipo = _buscar_por_nombre(eq_qs, nombre_equipo)
                        if equipo and indicador.equipo_responsable_id != equipo.id:
                            indicador.equipo_responsable = equipo
                            changed = True

        # 2. Campos manuales del formulario (tienen precedencia sobre el archivo)
        MAPA_FORM = {
            'definicion': 'descripcion_indicador',
            'interpretacion': 'comentarios_adicionales',
            'metodologia': 'metodo_medicion',
        }
        for form_field, modelo_campo in MAPA_FORM.items():
            val = (paso_form_data.get(form_field) or '').strip()
            if val:
                setattr(indicador, modelo_campo, val)
                changed = True

        if changed:
            indicador.save()
