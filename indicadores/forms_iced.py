"""
Formularios Django para el módulo ICED v2 — 5 módulos (A-E), 42 preguntas.

Cada módulo es un Form independiente que se usa como paso del SessionWizardView.
Las respuestas de cada Form se serializan como JSON en el campo correspondiente
de ICEDFormulario (respuestas_a ... respuestas_e).

Referencia completa: docs/ficed_blueprint_completo.yaml
"""

import json
import re

from django import forms
from django.core.validators import URLValidator, validate_email


# =============================================================================
# WIDGETS REUTILIZABLES
# =============================================================================

def iced_widget(tipo, config):
    """
    Devuelve un HiddenInput con los atributos data-* para que iced_widgets.js
    renderice un widget interactivo (checkbox-tabla, tabla-simple, etc.).
    
    El JS lee `data-iced-widget`, `data-config` y `data-target` del contenedor
    padre (div.iced-table-builder); aquí los ponemos en el input para que el
    template los copie al contenedor.
    """
    attrs = {
        'class': 'iced-json-field',
        'data-iced-widget': tipo,
        'data-config': json.dumps(config, ensure_ascii=False),
    }
    # Si hay condicionalidad en la config, agregarla a los attrs para que el template la detecte
    if 'data-show-if' in config:
        attrs['data-show-if'] = config['data-show-if']
    return forms.HiddenInput(attrs=attrs)


class JsonTextarea(forms.Textarea):
    """Textarea para campos que almacenan JSON (tablas dinámicas)."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('attrs', {})
        kwargs['attrs'].setdefault('class', 'iced-json-textarea hidden')
        super().__init__(*args, **kwargs)


def _validar_urls_json(valor):
    """Valida el formato de las URLs dentro de campos JSON de widgets.

    Estructuras soportadas:
      - checkbox-tabla:        {codigo: {seleccion: bool, url: str, ...}}
      - tabla-simple/compleja: [{col: str, url: str, ...}]
      - matriz-satisfaccion:   {matriz: {...}, urls: [str]}
    Las celdas admiten varias URLs separadas por coma.
    """
    if not valor:
        return valor
    try:
        data = json.loads(valor) if isinstance(valor, str) else valor
    except (ValueError, TypeError):
        return valor

    urls = []

    def _recolectar(obj, clave_padre=''):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and 'url' in k.lower() and v.strip():
                    urls.append(v)
                elif isinstance(v, (dict, list)):
                    _recolectar(v, k)
        elif isinstance(obj, list):
            # Listas bajo claves 'url(s)' contienen strings directos (matriz-satisfaccion)
            if 'url' in clave_padre.lower():
                for item in obj:
                    if isinstance(item, str) and item.strip():
                        urls.append(item)
                    elif isinstance(item, (dict, list)):
                        _recolectar(item, clave_padre)
            else:
                for item in obj:
                    _recolectar(item, clave_padre)

    _recolectar(data)

    invalidas = []
    for u in urls:
        for parte in u.split(','):
            parte = parte.strip()
            if not parte:
                continue
            try:
                URLValidator()(parte)
            except forms.ValidationError:
                invalidas.append(parte)
    if invalidas:
        raise forms.ValidationError(
            f"Formato de URL inválido: {', '.join(invalidas[:3])}. "
            "Use el formato https://ejemplo.com/ruta"
        )
    return valor


def _error_telefono(telefono):
    """Devuelve mensaje de error si el teléfono no cumple el formato, o None.

    Reglas: solo dígitos con '+' inicial opcional; máx. 10 dígitos,
    o 12 con prefijo internacional '+'.
    """
    import re as _re
    tel_limpio = _re.sub(r'[\s\-()]', '', (telefono or '').strip())
    if not tel_limpio:
        return None
    if not _re.fullmatch(r'\+?\d+', tel_limpio):
        return "Teléfono solo debe contener dígitos (opcionalmente con '+' inicial)"
    digitos = tel_limpio.lstrip('+')
    max_dig = 12 if tel_limpio.startswith('+') else 10
    if len(digitos) > max_dig:
        return (
            f"Teléfono admite máximo {max_dig} dígitos"
            + (" con prefijo '+'" if tel_limpio.startswith('+') else " (o 12 dígitos con prefijo '+')")
        )
    return None


def _error_fecha_mmaaaa(fecha):
    """Devuelve mensaje de error si la fecha no cumple MM/AAAA, o None."""
    import re as _re
    f = (fecha or '').strip()
    if not f:
        return None
    if not _re.fullmatch(r'\d{2}/\d{4}', f):
        return "Inicio de participación debe tener formato MM/AAAA (ej: 03/2024)"
    if not (1 <= int(f[:2]) <= 12):
        return "El mes de inicio de participación debe estar entre 01 y 12"
    return None


# =============================================================================
# VALIDACIÓN ESTRICTA DE FORMATOS (Fase 1 FICED)
# =============================================================================
# El delegado no debe poder guardar valores con formato imposible (correos
# sin @, teléfonos con letras, URLs sin dominio, fechas que no son fechas).
# Reglas por tipo para campos escalares + inferencia por nombre de clave
# para las celdas de los widgets dinámicos (JSON).

_MAX_CELDA_JSON = 500     # caracteres máximos por celda de widget
_MAX_FILAS_JSON = 50      # tope de filas por widget dinámico
_MAX_TEXTO = 3000         # textos largos (descripciones, observaciones)
_MAX_TEXTO_CORTO = 300    # campos "especifique" / respuestas cortas


def _es_email(valor):
    try:
        validate_email(valor.strip())
        return True
    except forms.ValidationError:
        return False


def _es_url_valida(valor):
    try:
        URLValidator()(valor.strip())
        return True
    except forms.ValidationError:
        return False


def _err_fecha_iso(valor):
    """AAAA-MM-DD — los widgets tipo 'fecha' usan input type=date."""
    import datetime as _dt
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', valor.strip()):
        return "La fecha debe tener formato AAAA-MM-DD"
    try:
        _dt.date.fromisoformat(valor.strip())
    except ValueError:
        return "La fecha no existe"
    return None


def _err_aaaa(valor):
    if not re.fullmatch(r'(19|20)\d{2}', valor.strip()):
        return "El año debe tener formato AAAA (ej: 2024)"
    return None


def _err_urls_multi(valor):
    """URLs separadas por coma."""
    malas = [p.strip() for p in valor.split(',')
             if p.strip() and not _es_url_valida(p.strip())]
    if malas:
        return ("Formato de URL inválido: " + ', '.join(malas[:3]) +
                ". Use el formato https://ejemplo.com/ruta")
    return None


def _err_codigos_bp(valor):
    if not re.fullmatch(
            r'[\w\-]+(\s*[,;]\s*[\w\-]+)*', valor.strip()):
        return ("Códigos BP separados por coma "
                "(ej: 2023100012345, 2024100067890)")
    return None


def _err_entero(valor):
    v = valor.strip()
    if not re.fullmatch(r'\d{1,3}', v):
        return "Debe ser un número entero"
    if not (0 <= int(v) <= 80):
        return "Debe estar entre 0 y 80"
    return None


def _err_nombre_persona(valor):
    v = valor.strip()
    if len(v) < 3:
        return "Muy corto para ser un nombre"
    if not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' \.\-]+", v):
        return "Solo letras, espacios y guiones"
    return None


_REGLAS = {
    'email': lambda v: None if _es_email(v)
        else "Correo electrónico no tiene un formato válido",
    'telefono': _error_telefono,
    'mmaaaa': _error_fecha_mmaaaa,
    'fecha': _err_fecha_iso,
    'aaaa': _err_aaaa,
    'url_multi': _err_urls_multi,
    'codigos_bp': _err_codigos_bp,
    'nombre': _err_nombre_persona,
    'entero': _err_entero,
    'texto_corto': lambda v: (
        f"Máximo {_MAX_TEXTO_CORTO} caracteres"
        if len(v) > _MAX_TEXTO_CORTO else None),
    'texto': lambda v: (
        f"Máximo {_MAX_TEXTO} caracteres"
        if len(v) > _MAX_TEXTO else None),
}

# Inferencia por nombre de clave/campo (orden importa: específico primero)
_CLAVES_TIPO = [
    (re.compile(r'correo|email', re.I), 'email'),
    (re.compile(r'telefono|celular', re.I), 'telefono'),
    (re.compile(r'url|link|enlace|sitio_web|pagina_web', re.I), 'url_multi'),
    (re.compile(r'inicio_participacion|mmaaaa', re.I), 'mmaaaa'),
    (re.compile(r'anios?_experiencia', re.I), 'entero'),
    (re.compile(r'fecha', re.I), 'fecha'),
    (re.compile(r'\banio|\bano\b|vigencia', re.I), 'aaaa'),
    (re.compile(r'nombre_completo', re.I), 'nombre'),
]

# Reglas explícitas para campos escalares (texto plano del wizard)
REGLAS_CAMPOS_FICED = {
    'p25_proyectos_bp': 'codigos_bp',
}


def _tipo_por_clave(clave):
    for rx, tipo in _CLAVES_TIPO:
        if rx.search(clave):
            return tipo
    return None


def _tipo_por_nombre_campo(name):
    for rx, tipo in _CLAVES_TIPO:
        if rx.search(name):
            return tipo
    if '_especificar' in name or name.endswith('_otro'):
        return 'texto_corto'
    return 'texto'


def _validar_filas_json(valor, etiqueta='Fila'):
    """Recorre el JSON de los widgets dinámicos y valida cada celda de
    texto según el tipo inferido por el nombre de la clave. Devuelve la
    lista de errores encontrados (vacía = OK)."""
    try:
        data = json.loads(valor) if isinstance(valor, str) else valor
    except (ValueError, TypeError):
        return []
    errores = []
    n_filas = 0

    def check_cell(clave, v, ctx):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            v = str(v)
        if not isinstance(v, str) or not v.strip():
            return
        tipo = _tipo_por_clave(clave)
        if tipo:
            err = _REGLAS[tipo](v.strip())
            if err:
                errores.append(f"{ctx}, '{clave}': {err}")
                return
        if len(v) > _MAX_CELDA_JSON:
            errores.append(
                f"{ctx}, '{clave}': máximo {_MAX_CELDA_JSON} caracteres")

    def walk(obj, ctx):
        nonlocal n_filas
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    check_cell(k, v, ctx)
                elif isinstance(v, dict):
                    walk(v, ctx)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str):
                            check_cell(k, item, ctx)
                        elif isinstance(item, (dict, list)):
                            walk(item, ctx)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    n_filas += 1
                    walk(item, f'Fila #{n_filas}')
                elif isinstance(item, str):
                    check_cell('', item, ctx)

    walk(data, etiqueta)
    if n_filas > _MAX_FILAS_JSON:
        errores.append(f'Máximo {_MAX_FILAS_JSON} filas por tabla')
    return errores


class ICEDBaseForm(forms.Form):
    """Base de los pasos del wizard FICED: validación estricta de formatos
    sobre campos escalares y sobre las celdas JSON de los widgets
    dinámicos (checkbox-tabla, tabla-simple/compleja, matriz, personas,
    rrhh). Los clean_* específicos y los clean() condicionales de cada
    módulo siguen aplicando encima de esta capa."""

    def clean(self):
        cleaned = super().clean()
        for name, valor in list(cleaned.items()):
            if name not in self.fields or valor in (None, '', [], {}):
                continue
            if isinstance(valor, str) and valor[:1] in '[{':
                for err in _validar_filas_json(valor, name)[:6]:
                    self.add_error(name, err)
                continue
            if isinstance(valor, str) and valor.strip():
                tipo = (REGLAS_CAMPOS_FICED.get(name)
                        or _tipo_por_nombre_campo(name))
                err = _REGLAS[tipo](valor.strip())
                if err:
                    self.add_error(name, err)
        return cleaned


# =============================================================================
# MÓDULO A: IDENTIFICACIÓN — Form con múltiples personas de contacto
# =============================================================================

class ICEDModuloAForm(ICEDBaseForm):
    """
    Módulo A: Identificación del organismo y personas de contacto.
    Las personas se almacenan como JSON en `personas_contacto_json`.
    """
    step_name = 'identificacion'

    # Campo visible (solo lectura visual) + campo oculto para enviar el valor
    p1_nombre_organismo_display = forms.CharField(
        max_length=255,
        label="1. Nombre del organismo",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input',
            'readonly': 'readonly',
            'disabled': 'disabled',
            'placeholder': 'Se pre-llena automáticamente',
            'style': 'background-color: #f3f4f6; cursor: not-allowed;'
        })
    )
    p1_nombre_organismo = forms.CharField(
        max_length=255,
        widget=forms.HiddenInput()
    )
    
    # P2-P5: Múltiples personas de contacto (JSON)
    personas_contacto_json = forms.CharField(
        required=True,
        widget=forms.HiddenInput(attrs={
            'class': 'iced-json-field',
            'data-iced-widget': 'personas-contacto-inline',
            'data-config': json.dumps({
                'min': 1,
                'categorias_nombrado': [
                    {'valor': 'AA', 'texto': 'Asistencial Administrativo'},
                    {'valor': 'TO', 'texto': 'Técnico Operativo'},
                    {'valor': 'TA', 'texto': 'Técnico Administrativo'},
                    {'valor': 'PU1', 'texto': 'Profesional Universitario 1'},
                    {'valor': 'PE', 'texto': 'Profesional Especializado'},
                    {'valor': 'AS', 'texto': 'Asesor'},
                ],
                'categorias_contratista': [
                    {'valor': 'A', 'texto': 'Asistencial'},
                    {'valor': 'T', 'texto': 'Técnico'},
                    {'valor': 'P', 'texto': 'Profesional'},
                    {'valor': 'PE', 'texto': 'Profesional Especializado'},
                ],
            }, ensure_ascii=False),
        }),
        label="Personas de contacto",
        help_text="Mínimo 1 persona de contacto. Puede agregar tantas como necesite."
    )
    
    def clean_personas_contacto_json(self):
        """Validar que haya al menos 1 persona de contacto."""
        import json as _json
        raw = self.cleaned_data.get('personas_contacto_json', '[]')
        try:
            personas = _json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            raise forms.ValidationError("Formato JSON inválido.")
        
        if not isinstance(personas, list):
            raise forms.ValidationError("Debe ser una lista de personas.")
        
        # Filtrar vacíos
        personas_validas = [
            p for p in personas 
            if isinstance(p, dict) and (p.get('nombre_completo') or '').strip()
        ]
        
        if len(personas_validas) < 1:
            raise forms.ValidationError("Debe registrar al menos una persona de contacto.")
        
        # Validar campos requeridos por persona
        for i, p in enumerate(personas_validas):
            errores = []
            if not (p.get('nombre_completo') or '').strip():
                errores.append("Nombre completo es requerido")
            if not (p.get('cargo') or '').strip():
                errores.append("Cargo es requerido")
            correo = (p.get('correo') or '').strip()
            if not correo:
                errores.append("Correo electrónico es requerido")
            else:
                try:
                    validate_email(correo)
                except forms.ValidationError:
                    errores.append("Correo electrónico no tiene un formato válido")
            err_tel = _error_telefono(p.get('telefono'))
            if err_tel:
                errores.append(err_tel)

            if errores:
                raise forms.ValidationError(f"Persona #{i+1}: {', '.join(errores)}")
        
        return _json.dumps(personas_validas, ensure_ascii=False)


# =============================================================================
# MÓDULO B: ENTORNO INSTITUCIONAL (P6-P12) — Peso 25%
# =============================================================================

P10_CHOICES = [
    ('1', 'Sí, participa activamente: el personal del organismo asiste y se involucra en todas las actividades disponibles, como cursos y talleres relacionados con la gestión y producción de información estadística.'),
    ('2', 'Sí, participa ocasionalmente: el personal del organismo asiste solo a algunas de las actividades de fortalecimiento cuando son relevantes o se considera necesario.'),
    ('3', 'Sí, pero de manera limitada: el personal del organismo participa en actividades de fortalecimiento en casos específicos y cuando el tiempo de los equipos de trabajo lo permite.'),
    ('4', 'No, actualmente no participa: el personal del organismo no asiste ni se involucra en actividades relacionadas con la producción de información estadística.'),
]

P12_CHOICES = [
    ('1', 'Existe de manera formal un mecanismo de trazabilidad con herramientas o procedimientos para registrar y rastrear cada etapa de producción de la información estadística.'),
    ('2', 'Existen algunos mecanismos informales para la trazabilidad, pero no se aplican a todos los procesos de información estadística.'),
    ('3', 'No existen mecanismos de trazabilidad: el organismo no cuenta con ningún mecanismo específico para asegurar la trazabilidad en sus procesos de información estadística.'),
]


class ICEDModuloBForm(ICEDBaseForm):
    """Módulo B: Entorno Institucional (P6-P12)."""
    step_name = 'entorno'

    # P6: ¿Funciones relacionadas con info estadística?
    p6_funciones_estadisticas = forms.ChoiceField(
        choices=[('si', 'Sí'), ('no', 'No')],
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="6. ¿En las funciones del organismo se contemplan funciones relacionadas con generación, procesamiento, reporte o difusión de información estadística?",
        help_text=(
            "<strong>Definiciones:</strong><br>"
            "<strong>Generación:</strong> recolección de datos primarios en formatos o aplicativos de captura.<br>"
            "<strong>Procesamiento:</strong> transformación de datos primarios recolectados; el producto final son bases de datos depuradas, las estadísticas o indicadores.<br>"
            "<strong>Reporte:</strong> transmisión de datos, indicadores o estadísticas entre entidades.<br>"
            "<strong>Difusión:</strong> poner a disposición de la ciudadanía, empresas, investigadores, organizaciones públicas y privadas, medios de comunicación, así como de las administraciones públicas, la información estadística que produce y que resulta necesaria para la correcta toma de decisiones."
        )
    )
    p6_descripcion = forms.CharField(
        max_length=3000,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'iced-textarea', 'rows': 3,
            'placeholder': 'Describa las funciones relacionadas con la gestión de información estadística',
            'data-show-if': 'p6_funciones_estadisticas=si',
        }),
        label="Describa"
    )

    # P7: ¿Cuenta con procedimientos?
    p7_procedimientos = forms.ChoiceField(
        choices=[('si', 'Sí'), ('no', 'No')],
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="7. ¿El organismo cuenta con procedimientos relacionados con generación, procesamiento, reporte o difusión de información estadística?",
        help_text="Si responde Sí, seleccione los macroprocesos, procesos, subprocesos y procedimientos según la relación con el MOP."
    )

    # Bloque informativo: definiciones (se renderiza como separador entre P7 y P8)
    p7_info_definiciones = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={
            'data-show-if': 'p7_procedimientos=si',
        }),
        label="Definiciones",
        help_text=(
            "<strong>Información estadística:</strong> es el conjunto de resultados y documentación que los soporta, los cuales se obtienen de las operaciones estadísticas y que describen o expresan características sobre un elemento, fenómeno u objeto de estudio.<br><br>"
            "<strong>Operación estadística:</strong> es la aplicación del conjunto de procesos y actividades que comprende la identificación de necesidades, diseño, construcción, recolección o acopio, procesamiento, análisis, difusión y evaluación, la cual conduce a la producción de información estadística sobre un tema de interés nacional o territorial.<br><br>"
            "<strong>Proceso estadístico:</strong> es el conjunto sistemático de actividades encaminadas a la producción de estadísticas, entre las cuales están comprendidas: la detección de necesidades de información, el diseño, la construcción, la recolección, el procesamiento, el análisis, la difusión y la evaluación.<br><br>"
            "<em>Fuente: Ley 2335 del 03 de octubre de 2023. Por la cual se expiden disposiciones sobre las estadísticas oficiales en el país. DANE.</em>"
        )
    )

    p7_estructura_mop = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={
            'class': 'iced-json-field',
            'data-iced-widget': 'estructura-mop',
            'data-config': json.dumps({'min': 1}, ensure_ascii=False),
            'data-show-if': 'p7_procedimientos=si',
        }),
        label="Estructura MOP",
        help_text="Agregue subprocesos seleccionando previamente el macroproceso y proceso, y los procedimientos correspondientes."
    )

    # P8: Herramientas de planificación (generación/procesamiento/reporte/difusión)
    P8_OPCIONES = [
        ('planes_trabajo', 'Planes de trabajo'),
        ('planes_accion', 'Planes de acción'),
        ('programas', 'Programas'),
        ('proyectos', 'Proyectos'),
        ('no_se_incluyen', 'No se incluyen'),
    ]
    p8_herramientas_planificacion = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'exclusiva': 'no_se_incluyen',
            'columnas': [
                {'name': 'documento', 'label': 'Documento', 'tipo': 'texto', 'placeholder': 'Nombre del documento'},
                {'name': 'seccion', 'label': 'Sección / Actividad', 'tipo': 'texto', 'placeholder': 'Sección específica'},
            ],
            'opciones': [
                {'codigo': 'planes_trabajo', 'texto': 'Planes de trabajo'},
                {'codigo': 'planes_accion', 'texto': 'Planes de acción'},
                {'codigo': 'programas', 'texto': 'Programas'},
                {'codigo': 'proyectos', 'texto': 'Proyectos'},
                {'codigo': 'no_se_incluyen', 'texto': 'No se incluyen'},
            ],
        }),
        label="8. Señale dentro de cuáles herramientas de planificación se incluyen actividades específicas de generación, procesamiento, reporte o difusión de información estadística",
        help_text="Para cada herramienta seleccionada, describa el documento y sección específica"
    )

    # P9: Herramientas de planificación (mejoramiento/fortalecimiento)
    p9_herramientas_mejoramiento = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'exclusiva': 'no_se_incluyen',
            'columnas': [
                {'name': 'documento', 'label': 'Documento', 'tipo': 'texto'},
                {'name': 'seccion', 'label': 'Sección / Actividad', 'tipo': 'texto'},
            ],
            'opciones': [
                {'codigo': 'planes_trabajo', 'texto': 'Planes de trabajo'},
                {'codigo': 'planes_accion', 'texto': 'Planes de acción'},
                {'codigo': 'programas', 'texto': 'Programas'},
                {'codigo': 'proyectos', 'texto': 'Proyectos'},
                {'codigo': 'no_se_incluyen', 'texto': 'No se incluyen'},
            ],
        }),
        label="9. Señale dentro de cuáles herramientas de planificación se incluyen actividades específicas para el mejoramiento o fortalecimiento de la información estadística",
        help_text="Misma estructura que P8"
    )

    # P10: Participación en actividades de fortalecimiento
    p10_participacion = forms.ChoiceField(
        choices=P10_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="10. ¿Participa el organismo en actividades de fortalecimiento de capacidades y competencias, como cursos y talleres de sensibilización, que mejoren la gestión y producción de información estadística?"
    )
    p10_motivo_no = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'iced-textarea',
            'rows': 2,
            'data-show-if': 'p10_participacion=4',
            'placeholder': 'Indique por qué no participa'
        }),
        label="Si su respuesta fue 'no', indique por qué"
    )
    p10_actividades = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={
            'class': 'iced-json-field',
            'data-iced-widget': 'tabla-simple',
            'data-config': json.dumps({
                'min_filas': 1,
                'max_filas': 10,
                'columnas': [
                    {'name': 'actividad', 'label': 'Actividad / Curso / Taller', 'tipo': 'texto'},
                    {'name': 'fecha', 'label': 'Fecha', 'tipo': 'fecha'},
                    {'name': 'organismo', 'label': 'Organismo encargado', 'tipo': 'organismo'},
                ],
            }, ensure_ascii=False),
            'data-show-if': 'p10_participacion=1,2,3',
        }),
        label="Relacione las actividades en las que participó, la fecha y el organismo encargado de la actividad",
        help_text="Complete esta tabla solo si seleccionó opciones 1, 2 o 3"
    )

    # P11: Instancias de coordinación
    p11_instancias_coordinacion = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'exclusiva': 'no_participa',
            'columnas': [
                {'name': 'internas', 'label': 'Instancias internas', 'tipo': 'texto', 'placeholder': 'Instancias internas'},
                {'name': 'externas', 'label': 'Instancias externas', 'tipo': 'texto', 'placeholder': 'Instancias externas'},
            ],
            'opciones': [
                {'codigo': 'comisiones', 'texto': 'Comisiones estadísticas'},
                {'codigo': 'comites', 'texto': 'Comités estadísticos'},
                {'codigo': 'mesas', 'texto': 'Mesas estadísticas'},
                {'codigo': 'observatorios', 'texto': 'Observatorios estadísticos'},
                {'codigo': 'otros', 'texto': 'Otras instancias'},
                {'codigo': 'no_participa', 'texto': 'No participa'},
            ],
        }),
        label="11. ¿El organismo participa en instancias de coordinación (entidades/organismos externos y/o internos) en materia de estadística?",
        help_text="Seleccione las instancias en las que participa y especifique las instancias internas y externas correspondientes."
    )

    # P12: Trazabilidad
    p12_trazabilidad = forms.ChoiceField(
        choices=P12_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="12. ¿El organismo cuenta con mecanismos para asegurar la trazabilidad y continuidad en los procesos de generación, procesamiento, reporte o difusión de información estadística?"
    )
    p12_descripcion_mecanismo = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'iced-textarea',
            'rows': 3,
            'data-show-if': 'p12_trazabilidad=1,2',
            'placeholder': 'Describa mediante qué mecanismo'
        }),
        label="Describa mediante qué mecanismo"
    )


# =============================================================================
# MÓDULO C: INFRAESTRUCTURA (P13-P22) — Peso 25%
# =============================================================================

P17_CHOICES = [
    ('1', 'Suficientes y facilitan las actividades'),
    ('2', 'Limitadas pero no dificultan las actividades'),
    ('3', 'Limitadas y causan dificultades en las actividades'),
    ('4', 'Muy limitadas para desarrollar las actividades'),
    ('5', 'Nulas, no permiten desarrollar las actividades'),
]

P18_CHOICES = [
    ('1', 'Existe una persona que produce, coordina o centraliza los indicadores o estadísticas relevantes para la toma de decisiones'),
    ('2', 'Existe un grupo que produzca, coordine o centralice los indicadores o estadísticas relevantes para la toma de decisiones'),
    ('3', 'Existen varios grupos que produzcan, coordinen o centralicen los indicadores o estadísticas relevantes para la toma de decisiones'),
    ('4', 'No existe una persona, grupo o grupos que produzcan, coordinen o centralicen los indicadores o estadísticas relevantes para la toma de decisiones — Pase a la pregunta 20'),
]

P20_CHOICES = [
    ('1', 'Suficiente y facilita las actividades'),
    ('2', 'Limitado pero no dificulta las actividades'),
    ('3', 'Limitado y causa dificultades en las actividades'),
    ('4', 'Muy limitado para desarrollar las actividades'),
    ('5', 'Nulo, no permite desarrollar las actividades'),
]

P22_CHOICES = [
    ('1', 'Suficientes y facilitan las actividades'),
    ('2', 'Limitados pero no dificultan las actividades'),
    ('3', 'Limitados y causan dificultades en las actividades'),
    ('4', 'Muy limitados para desarrollar las actividades'),
    ('5', 'Nulos, no permiten desarrollar las actividades'),
]


class ICEDModuloC1Form(ICEDBaseForm):
    """Módulo C1: Infraestructura - Herramientas (P13-P17)."""
    step_name = 'infraestructura_c1'

    # --- C1: Herramientas ---

    # P13: Herramientas de procesamiento (checkbox-tabla con columna ¿Cuál(es)?)
    p13_herramientas_procesamiento = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'exclusiva': 'ninguna',
            'con_detalle': ['propias', 'otra'],  # Solo estas opciones tienen campo de texto
            'columnas': [
                {'name': 'cual', 'label': '¿Cuál(es)?', 'tipo': 'texto', 'placeholder': 'Especifique'},
            ],
            'opciones': [
                {'codigo': 'hojas_calculo', 'texto': 'Hojas de cálculo'},
                {'codigo': 'r', 'texto': 'R'},
                {'codigo': 'sas', 'texto': 'SAS'},
                {'codigo': 'spss', 'texto': 'SPSS'},
                {'codigo': 'stata', 'texto': 'STATA'},
                {'codigo': 'propias', 'texto': 'Desarrolladas por el organismo'},
                {'codigo': 'python', 'texto': 'Python'},
                {'codigo': 'gis', 'texto': 'Programas de datos geográficos'},
                {'codigo': 'otra', 'texto': 'Otras herramientas'},
                {'codigo': 'ninguna', 'texto': 'Ninguna herramienta de procesamiento'},
            ],
        }),
        label="13. ¿Cuáles de las siguientes herramientas de procesamiento de datos estadísticos utiliza el organismo?",
        help_text="Seleccione las herramientas que utiliza. Solo para 'Desarrolladas por el organismo' y 'Otras herramientas' debe especificar cuál(es)."
    )

    # P14: Gestores de bases de datos (checkbox-tabla con columna ¿Cuál(es)?)
    p14_gestores_bd = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'exclusiva': 'ninguno',
            'con_detalle': ['otro'],  # Solo 'Otro' tiene campo de texto
            'columnas': [
                {'name': 'cual', 'label': '¿Cuál(es)?', 'tipo': 'texto', 'placeholder': 'Especifique'},
            ],
            'opciones': [
                {'codigo': 'oracle', 'texto': 'Oracle'},
                {'codigo': 'postgresql', 'texto': 'PostgreSQL'},
                {'codigo': 'sqlserver', 'texto': 'SQL Server'},
                {'codigo': 'mysql', 'texto': 'MySQL'},
                {'codigo': 'sybase', 'texto': 'Sybase'},
                {'codigo': 'otro', 'texto': 'Otro'},
                {'codigo': 'ninguno', 'texto': 'Ningún gestor'},
            ],
        }),
        label="14. ¿Cuáles de los siguientes gestores de bases de datos utiliza el organismo para administrar la información estadística que genera?",
        help_text="Seleccione los gestores que utiliza. Solo para 'Otro' debe especificar cuál(es)."
    )

    # P15: ¿Utiliza herramientas de visualización?
    p15_herramientas_visualizacion = forms.ChoiceField(
        choices=[('1', 'Sí — Pase a la pregunta 15.1'), ('2', 'No — Pase a la pregunta 17')],
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="15. ¿Utiliza alguna herramienta de visualización y/o monitoreo de cifras, datos o indicadores?"
    )

    # P15.1: Herramientas de tableros de control (checkbox-tabla, condicional: P15=Sí)
    p15_1_herramientas_tableros = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={
            'class': 'iced-json-field',
            'data-iced-widget': 'checkbox-tabla',
            'data-config': json.dumps({
                'exclusiva': 'ninguna',
                'con_detalle': ['otros'],  # Solo 'Otros' tiene campo de texto
                'columnas': [
                    {'name': 'cual', 'label': '¿Cuál(es)?', 'tipo': 'texto', 'placeholder': 'Especifique'},
                ],
                'opciones': [
                    {'codigo': 'tableau', 'texto': 'Tableau'},
                    {'codigo': 'powerbi', 'texto': 'Power BI'},
                    {'codigo': 'looker', 'texto': 'Google Data Studio (Looker Studio)'},
                    {'codigo': 'qlik', 'texto': 'Qlik Sense'},
                    {'codigo': 'sap', 'texto': 'SAP BusinessObjects Dashboards'},
                    {'codigo': 'excel', 'texto': 'Microsoft Excel (con paneles personalizados)'},
                    {'codigo': 'ibm', 'texto': 'IBM Cognos Analytics'},
                    {'codigo': 'otros', 'texto': 'Otros'},
                    {'codigo': 'ninguna', 'texto': 'Ninguna'},
                ],
            }, ensure_ascii=False),
            'data-show-if': 'p15_herramientas_visualizacion=1',
        }),
        label="15.1 ¿Cuáles de las siguientes herramientas utiliza para el desarrollo de tableros de control?",
        help_text="Seleccione las herramientas que utiliza. Solo para 'Otros' debe especificar cuál(es)."
    )

    # P16: Reportes de tableros de control (condicional: solo si P15=Sí)
    p16_reportes_tableros = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={
            'class': 'iced-json-field',
            'data-iced-widget': 'tabla-simple',
            'data-config': json.dumps({
                'min_filas': 1,
                'max_filas': 10,
                'columnas': [
                    {'name': 'nombre', 'label': 'Nombre reporte', 'tipo': 'texto'},
                    {'name': 'url', 'label': 'URL', 'tipo': 'url', 'placeholder': 'https://...'},
                ],
            }, ensure_ascii=False),
            'data-show-if': 'p15_herramientas_visualizacion=1',
        }),
        label="16. Relacione a continuación los reportes que son extraídos de estos tableros de control con el URL de acceso en caso de estar disponible",
        help_text="Ingrese el nombre del reporte y su URL correspondiente (solo si utiliza herramientas de visualización)"
    )

    # P17: Suficiencia de herramientas
    p17_suficiencia_herramientas = forms.ChoiceField(
        choices=P17_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="17. Considera que las herramientas de procesamiento y visualización de datos con las que cuenta el organismo son:"
    )

    def clean_p16_reportes_tableros(self):
        return _validar_urls_json(self.cleaned_data.get('p16_reportes_tableros'))


# =============================================================================
# MÓDULO C2: INFRAESTRUCTURA - RECURSO HUMANO (P18-P20)
# =============================================================================

class ICEDModuloC2Form(ICEDBaseForm):
    """Módulo C2: Infraestructura - Recurso Humano (P18-P20)."""
    step_name = 'infraestructura_c2'

    # P18: Estructura organizacional para estadística
    p18_estructura_rrhh = forms.ChoiceField(
        choices=P18_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="18. ¿Existe en su estructura organizacional una persona, grupo o varios grupos internos de trabajo que produzcan, coordinen o centralicen los indicadores o estadísticas relevantes para la toma de decisiones?",
        help_text="<strong>Nota:</strong> Indicadores o estadísticas relevantes hace referencia a las que permiten evaluar los resultados, hacer seguimiento y formular políticas, planes y proyectos."
    )

    # P19: Datos de recurso humano (tabla auxiliar — widget interactivo)
    # Se serializa como lista JSON y en done() se materializa a ICEDRecursoHumano.
    # Nota visual: Al finalizar pase a la pregunta 20
    p19_rrhh_list = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={
            'class': 'iced-json-field',
            'data-iced-widget': 'rrhh-tabla',
            'data-config': json.dumps({
                'min_filas': 0,
                'max_filas': 50,
                'categorias_nombrado': [
                    {'valor': 'AA', 'texto': 'Asistente Administrativo'},
                    {'valor': 'TO', 'texto': 'Técnico Operativo'},
                    {'valor': 'TA', 'texto': 'Técnico Administrativo'},
                    {'valor': 'PU', 'texto': 'Profesional Universitario'},
                    {'valor': 'PE', 'texto': 'Profesional Especializado'},
                    {'valor': 'AS', 'texto': 'Asesor'},
                ],
                'categorias_contratista': [
                    {'valor': 'AA', 'texto': 'Asistente Administrativo'},
                    {'valor': 'T', 'texto': 'Técnico'},
                    {'valor': 'P', 'texto': 'Profesional'},
                    {'valor': 'PE', 'texto': 'Profesional Especializado'},
                    {'valor': 'AS', 'texto': 'Asesor'},
                ],
                'niveles_formacion': [
                    {'valor': 'B', 'texto': 'Bachiller'},
                    {'valor': 'TT', 'texto': 'Técnico-Tecnológico'},
                    {'valor': 'P', 'texto': 'Profesional'},
                    {'valor': 'E', 'texto': 'Especialización'},
                    {'valor': 'M', 'texto': 'Maestría'},
                    {'valor': 'D', 'texto': 'Doctorado'},
                ],
                'etapas': [
                    {'valor': 'DN', 'texto': 'Detección de necesidades'},
                    {'valor': 'D', 'texto': 'Diseño'},
                    {'valor': 'C', 'texto': 'Construcción'},
                    {'valor': 'R', 'texto': 'Recolección/Acopio'},
                    {'valor': 'P', 'texto': 'Procesamiento'},
                    {'valor': 'A', 'texto': 'Análisis'},
                    {'valor': 'DI', 'texto': 'Difusión'},
                    {'valor': 'E', 'texto': 'Evaluación'},
                ],
            }, ensure_ascii=False),
            'data-show-if': 'p18_estructura_rrhh=1,2,3',
        }),
        label="19. Registre la información del recurso humano vinculado a la producción estadística",
        help_text=(
            "<strong>Descripción fases del proceso estadístico - DANE:</strong><br><br>"
            "<strong>1. Detección y análisis de necesidades:</strong> permite confirmar la necesidad de realizar la operación estadística, así como determinar su viabilidad técnica y económica.<br><br>"
            "<strong>2. Diseño:</strong> se estructura técnicamente la operación estadística y se elaboran los documentos metodológicos correspondientes.<br><br>"
            "<strong>3. Construcción:</strong> se desarrollan y prueban los mecanismos, los instrumentos o las herramientas, así como los procesos y actividades.<br><br>"
            "<strong>4. Recolección/Acopio:</strong> se ejecutan todas las acciones planeadas, diseñadas y construidas en las fases anteriores con el fin de obtener los datos.<br><br>"
            "<strong>5. Procesamiento:</strong> se desarrollan actividades que garantizan el adecuado procesamiento de los datos de entrada y su preparación para ser analizados.<br><br>"
            "<strong>6. Análisis:</strong> se verifica la coherencia y la consistencia de los resultados con el fin de asegurar su calidad y posibilitar el análisis.<br><br>"
            "<strong>7. Difusión:</strong> se pone a disposición de los usuarios la información estadística generada como resultado de la operación estadística.<br><br>"
            "<strong>8. Evaluación:</strong> se determina el cumplimiento de los objetivos (basados en las necesidades de información) en contraste con los resultados de la operación estadística.<br><br>"
            "<em>Al finalizar pase a la pregunta 20.</em> Agregue una tarjeta por cada persona."
        )
    )

    # P20: Suficiencia de recurso humano
    p20_suficiencia_rrhh = forms.ChoiceField(
        choices=P20_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="20. Considera que el recurso humano para desarrollar las actividades de procesamiento, análisis y difusión de información estadística es:"
    )

    def clean_p19_rrhh_list(self):
        """Validar correo, teléfono y fecha en cada fila del recurso humano."""
        valor = self.cleaned_data.get('p19_rrhh_list')
        if not valor:
            return valor
        try:
            filas = json.loads(valor) if isinstance(valor, str) else valor
        except (ValueError, TypeError):
            return valor
        if isinstance(filas, list):
            for i, fila in enumerate(filas):
                if isinstance(fila, dict):
                    correo = (fila.get('correo') or '').strip()
                    if correo:
                        try:
                            validate_email(correo)
                        except forms.ValidationError:
                            raise forms.ValidationError(
                                f"Persona #{i+1}: Correo electrónico no tiene un formato válido"
                            )
                    err = _error_telefono(fila.get('telefono')) or _error_fecha_mmaaaa(fila.get('inicio_participacion'))
                    if err:
                        raise forms.ValidationError(f"Persona #{i+1}: {err}")
        return valor


# =============================================================================
# MÓDULO C3: INFRAESTRUCTURA - RECURSOS FINANCIEROS (P21-P22)
# =============================================================================

class ICEDModuloC3Form(ICEDBaseForm):
    """Módulo C3: Infraestructura - Recursos Financieros (P21-P22)."""
    step_name = 'infraestructura_c3'

    # P21: Porcentaje de presupuesto ANUAL desglosado por rubros
    p21_intro = forms.CharField(
        required=False,
        initial='⚠️ IMPORTANTE: Ingrese los valores en PORCENTAJE (%). Ejemplo: 25.5 significa 25.5% del presupuesto.',
        widget=forms.Textarea(attrs={
            'class': 'iced-textarea',
            'readonly': 'readonly',
            'rows': 2,
            'style': 'background: #fef3c7; border: 1px solid #f59e0b; color: #92400e; font-weight: 500; font-size: 0.9rem; resize: none;'
        }),
        label="21. Del presupuesto ANUAL total asignado al organismo, qué porcentaje aproximado se asigna a los siguientes rubros:"
    )

    # Costos de Hardware (4 items)
    p21_hw_header = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label="Del presupuesto ANUAL — Hardware"
    )
    p21_hw_servidores = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Adquisición de servidores para almacenamiento y procesamiento de datos estadísticos"
    )
    p21_hw_computadoras = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Computadoras de alto rendimiento para análisis estadístico avanzado"
    )
    p21_hw_moviles = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Dispositivos móviles (tabletas, smartphones) para recolección de datos en campo"
    )
    p21_hw_almacenamiento = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Sistemas de almacenamiento externos (discos duros, sistemas en la nube)"
    )

    # Costos de Software (5 items)
    p21_sw_header = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label="Del presupuesto ANUAL — Software"
    )
    p21_sw_estadistico = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Software estadístico especializado (e.g., SPSS, R, STATA, Python)"
    )
    p21_sw_bd = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Licencias de bases de datos y herramientas para la gestión de datos (SQL, Oracle)"
    )
    p21_sw_encuestas = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Sistemas de gestión de encuestas (CAPI, CATI, CAWI) para recolección de datos"
    )
    p21_sw_visualizacion = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Software de visualización de datos (e.g., Tableau, Power BI)"
    )
    p21_sw_seguridad = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Sistemas de protección de datos y ciberseguridad para garantizar la seguridad de la información"
    )

    # Costos de Personal y Capacitación (4 items)
    p21_per_header = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label="Del presupuesto ANUAL — Personal y capacitación"
    )
    p21_per_contratacion = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Contratación de expertos en análisis de datos (estadísticos, científicos de datos)"
    )
    p21_per_capacitacion = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Capacitación del personal en uso de herramientas estadísticas y tecnológicas"
    )
    p21_per_consultorias = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Consultorías externas para el desarrollo de metodologías estadísticas"
    )
    p21_per_mantenimiento = forms.DecimalField(
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'iced-input iced-percentage-input', 'step': '0.1', 'placeholder': '% Ej: 25.5', 'style': 'min-width: 120px;'}),
        label="Mantenimiento técnico de los sistemas y herramientas tecnológicas"
    )

    def clean(self):
        cleaned = super().clean()
        campos_p21 = [
            'p21_hw_servidores', 'p21_hw_computadoras', 'p21_hw_moviles', 'p21_hw_almacenamiento',
            'p21_sw_estadistico', 'p21_sw_bd', 'p21_sw_encuestas', 'p21_sw_visualizacion', 'p21_sw_seguridad',
            'p21_per_contratacion', 'p21_per_capacitacion', 'p21_per_consultorias', 'p21_per_mantenimiento',
        ]
        total = 0
        for nombre in campos_p21:
            val = cleaned.get(nombre)
            if val is not None:
                total += float(val)
        # Los rubros son categorías del presupuesto: su suma no puede superar
        # 100%, pero sí puede ser menor (gastos en rubros no listados o
        # diligenciamiento parcial). Solo se bloquea el caso imposible (>100%).
        if total > 100.01:
            raise forms.ValidationError(
                f"La suma de los porcentajes en la pregunta 21 no puede superar 100%. Actualmente suma {total:.1f}%."
            )
        return cleaned

    # P22: Suficiencia de recursos financieros
    p22_suficiencia_financiera = forms.ChoiceField(
        choices=P22_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="22. Considera que los recursos financieros asignados para desarrollar las actividades de procesamiento, análisis y difusión de información estadística son:"
    )


# =============================================================================
# MÓDULO D: METODOLOGÍA ESTADÍSTICA (P23-P35) — Peso 30%
# =============================================================================

P27_CHOICES = [
    ('1', 'Como organismo líder de indicadores de resultado se han realizado ejercicios de articulación con los organismos líderes de indicadores de producto'),
    ('2', 'Como organismo líder del indicador de producto, se han promovido ejercicios de articulación por parte de los organismos líderes de los indicadores de resultado'),
    ('3', 'No es necesario porque el indicador de resultado no tiene articulación con otro organismo'),
    ('4', 'No existe un proceso de articulación — Pase a la pregunta 29'),
]

P28_1_CHOICES = [
    ('1', 'Mensual'),
    ('2', 'Trimestral'),
    ('3', 'Semestral'),
    ('4', 'Anual'),
]

P28_2_CHOICES = [
    ('1', 'Análisis de datos básicos (reportes, tabulaciones y gráficos, sin modelos avanzados)'),
    ('2', 'Analítica descriptiva con modelos estadísticos tradicionales (regresiones, análisis de varianza)'),
    ('3', 'Analítica diagnóstica con modelos econométricos (series de tiempo, modelos de panel)'),
    ('4', 'Analítica predictiva con modelos de IA o machine learning'),
    ('5', 'Analítica prescriptiva con modelos de optimización o simulación'),
    ('6', 'Otro (especificar)'),
]

P29_CHOICES = [
    ('1', 'Coordinador líder y responsable de la implementación, facilitando la comunicación y articulación entre diferentes actores. — Pase a la pregunta 29.1'),
    ('2', 'Co-ejecutor del plan de acción en la implementación de la política.'),
    ('3', 'No está involucrado con las políticas públicas actuales'),
    ('4', 'Otro rol en relación con las políticas públicas vigentes (especificar)'),
]

P29_2_CHOICES = [
    ('1', 'Mensualmente'),
    ('2', 'Trimestralmente'),
    ('3', 'Semestralmente'),
    ('4', 'Anualmente'),
]

P31_CHOICES = [
    ('1', 'Realiza análisis de datos básicos (como generación de reportes, tabulaciones y gráficos, sin aplicar modelos avanzados o técnicas de analítica sofisticada)'),
    ('2', 'Realiza analítica descriptiva con modelos estadísticos tradicionales (como regresiones, análisis de varianza, entre otros)'),
    ('3', 'Realiza analítica diagnóstica con modelos econométricos (como series de tiempo, modelos de panel, entre otros)'),
    ('4', 'Realiza analítica predictiva con modelos de inteligencia artificial o machine learning (como redes neuronales, árboles de decisión, entre otros)'),
    ('5', 'Realiza analítica prescriptiva con modelos de optimización o simulación'),
]

P31_1_CHOICES = [
    ('1', 'Mensualmente'),
    ('2', 'Trimestralmente'),
    ('3', 'Semestralmente'),
    ('4', 'Anualmente'),
]

P32_CHOICES = [
    ('1', 'Conoce las herramientas de analítica avanzada pero no hace uso de ellas'),
    ('2', 'Conoce las herramientas de analítica avanzada y tiene planeado realizar la articulación con DATIC para desarrollar un caso de uso'),
    ('3', 'Tiene formulado un proyecto de analítica avanzada con DATIC para desarrollar un caso de uso'),
    ('4', 'Tiene implementado un proyecto de analítica avanzada con DATIC con un caso de uso'),
    ('5', 'Tiene desplegado un caso de uso con DATIC'),
    ('6', 'Desconoce la existencia de herramientas de analítica avanzada en DATIC'),
]


class ICEDModuloD1Form(ICEDBaseForm):
    """Módulo D1: Metodología Estadística - Operaciones Estadísticas (P23-P25)."""
    step_name = 'metodologia_d1'

    # --- D1: Operaciones Estadísticas ---

    # P23: Tabla de operaciones estadísticas (OOEE)
    p23_intro = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label="23. A continuación, se relacionan las operaciones estadísticas (OOEE) que actualmente se tienen identificadas dentro del Plan Estadístico Distrital. Por favor, complete la información correspondiente para cada una. Si hay alguna operación estadística que ya no se genere, marque la opción NO en la columna vigente, y en las demás opciones NA (no aplica)"
    )
    p23_operaciones_estadisticas = forms.CharField(
        required=False,
        widget=iced_widget('tabla-compleja', {
            'min_filas': 1,
            'max_filas': 30,
            # nombre_oe se llena por inyección desde OperacionEstadistica (inventario)
            'columnas': [
                {'name': 'nombre_oe', 'label': 'Nombre de la operación estadística', 'tipo': 'select', 'opciones': []},
                {'name': 'vigente', 'label': 'Vigente', 'tipo': 'booleano'},
                {'name': 'doc_metodologico', 'label': 'Documento metodológico', 'tipo': 'booleano'},
                {'name': 'ficha_metodologica', 'label': 'Ficha metodológica', 'tipo': 'booleano'},
                {'name': 'manual_operativo', 'label': 'Manual operativo', 'tipo': 'booleano'},
                {'name': 'diccionario_datos', 'label': 'Diccionario de datos', 'tipo': 'booleano'},
                {'name': 'doc_consistencia', 'label': 'Documento consistencia y validación', 'tipo': 'booleano'},
                {'name': 'acciones_fortalecimiento', 'label': 'Acciones de fortalecimiento', 'tipo': 'texto'},
                {'name': 'publicado_sicode', 'label': 'Publicado en SICODE', 'tipo': 'booleano'},
            ],
            # El instrumento pide opción NA en las columnas Sí/No
            'opcion_na': True,
            # Si vigente='no', las demás columnas quedan en NA deshabilitadas.
            'control_bloqueo': [
                {
                    'campo': 'vigente',
                    'valor': 'no',
                    'excluir': ['nombre_oe', 'vigente'],
                    'valor_bloqueado': 'na',
                },
            ],
        }),
        label="Operaciones Estadísticas",
        help_text="Complete la información para cada operación estadística identificada en el Plan Estadístico Distrital."
    )

    # P24: Lineamientos, normas y estándares (checkbox-tabla)
    p24_lineamientos = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'exclusiva': 'ninguna',
            'columnas': [],  # Sin columnas de detalle aquí, usamos campo separado para nomenclaturas
            'opciones': [
                {'codigo': 'lineamientos_sen', 'texto': 'Lineamientos para el proceso estadístico en el Sistema Estadístico Nacional'},
                {'codigo': 'ntc_pe_1000', 'texto': 'Norma Técnica de Calidad del Proceso Estadístico NTC PE 1000:2020'},
                {'codigo': 'nomenclaturas', 'texto': 'Nomenclaturas y clasificaciones — Pase a la tabla inferior'},
                {'codigo': 'conceptos_estandarizados', 'texto': 'Conceptos estandarizados — Pase a la pregunta 24.1'},
                {'codigo': 'ninguna', 'texto': 'No implementa lineamientos, normas y estándares'},
            ],
        }),
        label="24. ¿Cuáles de las siguientes nomenclaturas, normas, estándares o lineamientos técnicos/metodológicos emplea el organismo en la producción de información estadística?",
        help_text="Seleccione las opciones que correspondan."
    )

    # P24.0: Tabla de nomenclaturas y clasificaciones (condicional)
    p24_nomenclaturas = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'exclusiva': 'ninguna',
            'con_detalle': ['otra'],  # Solo 'Otra(s)' tiene campo de texto
            'columnas': [
                {'name': 'cual', 'label': 'Especifique', 'tipo': 'texto', 'placeholder': '¿Cuál nomenclatura?'},
            ],
            'opciones': [
                {'codigo': 'balanza_pagos', 'texto': 'Clasificación Ampliada de la Balanza de Pagos de Servicios'},
                {'codigo': 'ccp', 'texto': 'Clasificación Central de Productos'},
                {'codigo': 'ccp_colombia', 'texto': 'Clasificación Central de Productos Adaptada para Colombia'},
                {'codigo': 'copac', 'texto': 'Clasificación de Actividades de Protección Ambiental'},
                {'codigo': 'cagape', 'texto': 'Clasificación de Actividades y Gastos de Protección del Medio Ambiente'},
                {'codigo': 'fines_lucro', 'texto': 'Clasificación de las Finalidades de las Instituciones sin Fines de Lucro que sirven a los hogares'},
                {'codigo': 'cog', 'texto': 'Clasificación de las Funciones del Gobierno'},
                {'codigo': 'cog_colombia', 'texto': 'Clasificación de las Funciones del Gobierno Adaptada para Colombia'},
                {'codigo': 'comercio_exterior', 'texto': 'Clasificación del Comercio Exterior según Uso o Destino Económico'},
                {'codigo': 'cofog', 'texto': 'Clasificación del Consumo Individual por Finalidades'},
                {'codigo': 'cofog_colombia', 'texto': 'Clasificación del Consumo Individual por Finalidades Adaptada para Colombia'},
                {'codigo': 'cie_10', 'texto': 'Clasificación Estadística Internacional de Enfermedades y Problemas Relacionados con la Salud'},
                {'codigo': 'cer', 'texto': 'Clasificación Europea de Residuos para Estadísticas'},
                {'codigo': 'ciiu', 'texto': 'Clasificación Industrial Internacional Uniforme de todas las actividades económicas'},
                {'codigo': 'ciiu_colombia', 'texto': 'Clasificación Industrial Internacional Uniforme de todas las actividades económicas Adaptada para Colombia'},
                {'codigo': 'citu', 'texto': 'Clasificación Internacional de Actividades para Estadísticas de Uso del Tiempo'},
                {'codigo': 'citu_colombia', 'texto': 'Clasificación Internacional de Actividades para Estadísticas de Uso del Tiempo Adaptada para Colombia'},
                {'codigo': 'cidfpe', 'texto': 'Clasificación Internacional de Delitos con Fines Estadísticos'},
                {'codigo': 'cidfpe_colombia', 'texto': 'Clasificación Internacional de Delitos con Fines Estadísticos Adaptada para Colombia'},
                {'codigo': 'ci_intervenciones', 'texto': 'Clasificación Internacional de Intervenciones de Salud'},
                {'codigo': 'ci_situacion', 'texto': 'Clasificación Internacional de la Situación en el Empleo'},
                {'codigo': 'ci_ocupacion', 'texto': 'Clasificación Internacional de la Ocupación Adaptada para Colombia'},
                {'codigo': 'ci_funcionamiento', 'texto': 'Clasificación Internacional del Funcionamiento, la Discapacidad y la Salud'},
                {'codigo': 'cin_educacion', 'texto': 'Clasificación Internacional Normalizada de la Educación'},
                {'codigo': 'cin_educacion_campos', 'texto': 'Clasificación Internacional Normalizada de la Educación - Campos de educación y formación Adaptada para Colombia'},
                {'codigo': 'cin_educacion_niveles', 'texto': 'Clasificación Internacional Normalizada de la Educación - Niveles de educación Adaptada para Colombia'},
                {'codigo': 'cin_educacion_general', 'texto': 'Clasificación Internacional Normalizada de la Educación Adaptada para Colombia'},
                {'codigo': 'cin_ocupaciones', 'texto': 'Clasificación Internacional Uniforme de Ocupaciones Adaptada para Colombia'},
                {'codigo': 'categorias_economicas', 'texto': 'Clasificación por Grandes Categorías Económicas'},
                {'codigo': 'cuoc', 'texto': 'Clasificación Única de Ocupaciones para Colombia'},
                {'codigo': 'cuci', 'texto': 'Clasificación Uniforme para el Comercio Internacional'},
                {'codigo': 'm49', 'texto': 'Códigos estándar de país o área para uso estadístico (M49)'},
                {'codigo': 'dpa', 'texto': 'División Político Administrativa de Colombia'},
                {'codigo': 'nutecca', 'texto': 'Nomenclatura de las Unidades Territoriales Estadísticas de la Comunidad Andina'},
                {'codigo': 'sadym', 'texto': 'Sistema Armonizado de Designación y Codificación de Mercancías'},
                {'codigo': 'otra', 'texto': 'Otra(s)'},
            ],
            'data-show-if': 'p24_lineamientos=nomenclaturas',
        }),
        label="Nomenclaturas y/o clasificaciones",
        help_text="Seleccione las nomenclaturas y clasificaciones que emplea. Para 'Otra(s)' especifique cuál(es)."
    )

    # P24.1: Proveniencia de conceptos estandarizados (condicional)
    p24_1_intro = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={
            'data-show-if': 'p24_lineamientos=conceptos_estandarizados',
        }),
        label="24.1 ¿De dónde provienen estos conceptos estandarizados?"
    )
    p24_1_conceptos_estandarizados = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={
            'class': 'iced-json-field',
            'data-iced-widget': 'checkbox-tabla',
            'data-config': json.dumps({
                'columnas': [
                    {'name': 'cual', 'label': '¿Cuál(es)?', 'tipo': 'texto', 'placeholder': 'Especifique'},
                ],
                'opciones': [
                    {'codigo': 'dane', 'texto': 'Los conceptos que usa provienen del DANE'},
                    {'codigo': 'organismos_intl', 'texto': 'Los conceptos que usa provienen de Organismos Internacionales'},
                    {'codigo': 'otra_nacional', 'texto': 'Los conceptos que usa provienen de otra entidad de orden nacional'},
                    {'codigo': 'leyes_decretos', 'texto': 'Los conceptos que usa provienen de leyes, decretos, etc.'},
                    {'codigo': 'creacion_propia', 'texto': 'Los conceptos que usa son de creación propia'},
                    {'codigo': 'otra', 'texto': 'Los conceptos que usa provienen de otra fuente'},
                ],
            }, ensure_ascii=False),
            'data-show-if': 'p24_lineamientos=conceptos_estandarizados',
        }),
        label="Procedencia de conceptos estandarizados",
        help_text="Seleccione las fuentes de los conceptos estandarizados y especifique cuáles"
    )

    # P25: Mecanismos de detección de necesidades
    P25_OPCIONES = [
        ('encuestas', 'Encuestas'),
        ('reuniones_expertos', 'Reuniones con expertos en la temática de la operación estadística'),
        ('reuniones_partes', 'Reuniones de trabajo con partes interesadas especializadas'),
        ('mesas', 'Mesas intersectoriales'),
        ('solicitudes', 'Solicitudes directas de información estadística'),
        ('documentos_pp', 'Documentos de política pública'),
        ('planes', 'Planes (estratégicos, de acción, o de mejora)'),
        ('proyectos', 'Proyectos de inversión'),
        ('consultas_ref', 'Consultas de referentes (nacionales o internacionales)'),
        ('otro', 'Otro(s)'),
        ('ninguno', 'Ninguno'),
    ]
    p25_mecanismos_necesidades = forms.MultipleChoiceField(
        choices=P25_OPCIONES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'iced-checkbox'}),
        required=False,
        label="25. ¿Cuáles mecanismos se utilizan en el organismo para la detección de necesidades misionales o estadísticas?"
    )
    p25_proyectos_bp_link = forms.CharField(
        max_length=500,
        required=False,
        initial='🔗 Consulte los BP asociados aquí: https://www.cali.gov.co/planeacion/publicaciones/115111/programas_proyectos_ejecucion_dapm/',
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p25_mecanismos_necesidades=proyectos',
            'readonly': 'readonly',
            'style': 'background: #e0f2fe; border: 1px solid #0ea5e9; color: #0369a1; font-size: 0.85rem;'
        }),
        label=""
    )
    p25_proyectos_bp = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p25_mecanismos_necesidades=proyectos',
            'placeholder': 'Ej: 2024001, 2024002, 2024015'
        }),
        label="BP asociados",
        help_text="Separe los números de BP por comas. Ejemplo: 2024001, 2024002, 2024015"
    )
    p25_otro_especificar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p25_mecanismos_necesidades=otro',
            'placeholder': 'Especifique'
        }),
        label="Especifique otro mecanismo"
    )


# =============================================================================
# MÓDULO D2: METODOLOGÍA ESTADÍSTICA - DISEÑO Y FORMULACIÓN DE INDICADORES (P26-P30)
# =============================================================================

class ICEDModuloD2Form(ICEDBaseForm):
    """Módulo D2: Metodología Estadística - Diseño y Formulación de Indicadores (P26-P30)."""
    step_name = 'metodologia_d2'

    # P26: Estructura de análisis de indicadores
    P26_OPCIONES = [
        ('analisis_interno', 'Los indicadores de resultado son de análisis interno exclusivo'),
        ('colaboracion', 'Los indicadores de resultado se analizan en colaboración con otros organismos'),
        ('plataformas_digitales', 'Los indicadores de resultado se analizan con el uso de plataformas digitales para la recopilación de datos'),
        ('otro', 'El análisis se estructura de otra manera'),
        ('no_aplica', 'No aplica'),
        ('no_realiza', 'No se realiza consolidación de la información'),
    ]
    p26_estructura_analisis = forms.MultipleChoiceField(
        choices=P26_OPCIONES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'iced-checkbox'}),
        required=False,
        label="26. ¿Cómo se estructura el proceso de análisis de indicadores de resultado liderados por su organismo?"
    )
    p26_otro_especificar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p26_estructura_analisis=otro',
            'placeholder': 'Especifique'
        }),
        label="Especifique"
    )

    # P27: Articulación entre organismos
    p27_articulacion = forms.ChoiceField(
        choices=P27_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="27. ¿Existe un proceso de articulación entre organismos para realizar seguimiento a los indicadores de producto y su aporte a los indicadores de resultado?"
    )

    # P28: Cómo se articulan (condicional: P27 != 4)
    P28_OPCIONES = [
        ('reuniones', 'Reuniones periódicas para realizar acuerdo, seguimiento a los resultados — Pase a la pregunta 28.1'),
        ('actas', 'Registros de actas de reunión'),
        ('metodologia', 'Creación de una metodología para la consolidación y análisis de información — Pase a la pregunta 28.2'),
        ('comite', 'A través de un comité interinstitucional'),
        ('informes', 'Informes anuales sobre resultados y recomendaciones'),
        ('talleres', 'Talleres'),
        ('nube', 'Herramientas en la nube (Drive)'),
        ('sistema_centralizado', 'Sistema centralizado de información'),
        ('otro', 'Otras herramientas'),
        ('no_es_necesario', 'No es necesario porque el indicador de resultado no tiene articulación con otro organismo'),
        ('no_articulan', 'No se articulan'),
    ]
    p28_como_articulan = forms.MultipleChoiceField(
        choices=P28_OPCIONES,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'iced-checkbox iced-conditional',
            'data-show-if': 'p27_articulacion=1,2,3'
        }),
        required=False,
        label="28. ¿Cómo se articulan los diferentes organismos que tienen indicadores de producto con los organismos líderes de los indicadores de resultado para realizar un análisis integral del logro de resultados?"
    )
    p28_otro_especificar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p27_articulacion=1,2,3 p28_como_articulan=otro',
            'placeholder': 'Especifique'
        }),
        label="Especifique"
    )

    # P28.1: Frecuencia de reuniones (condicional: P27 != 4 y P28 incluye 'reuniones')
    P28_1_OPCIONES = [
        ('mensual', 'Mensualmente'),
        ('trimestral', 'Trimestralmente'),
        ('semestral', 'Semestralmente'),
        ('anual', 'Anualmente'),
    ]
    p28_1_frecuencia_reuniones = forms.MultipleChoiceField(
        choices=P28_1_OPCIONES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'iced-checkbox iced-conditional',
            'data-show-if': 'p27_articulacion=1,2,3 p28_como_articulan=reuniones'
        }),
        label="28.1 ¿Con qué frecuencia?"
    )

    # P28.2: Modelos estadísticos/econométricos (condicional: P27 != 4 y P28 incluye 'metodologia')
    P28_2_OPCIONES = [
        ('basicos', 'Realiza análisis de datos básicos (como generación de reportes, tabulaciones y gráficos, sin aplicar modelos avanzados o técnicas de analítica sofisticada)'),
        ('descriptiva', 'Analítica descriptiva con modelos estadísticos tradicionales (como regresiones, análisis de varianza, entre otros)'),
        ('diagnostica', 'Analítica diagnóstica con modelos econométricos (como series de tiempo, modelos de panel, entre otros)'),
        ('predictiva', 'Analítica predictiva con modelos de inteligencia artificial o machine learning (como redes neuronales, árboles de decisión, entre otros)'),
        ('prescriptiva', 'Analítica prescriptiva con modelos de optimización o simulación para recomendar acciones'),
        ('otro', 'Otro (especificar)'),
    ]
    p28_2_modelos_estadisticos = forms.MultipleChoiceField(
        choices=P28_2_OPCIONES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'iced-checkbox iced-conditional',
            'data-show-if': 'p27_articulacion=1,2,3 p28_como_articulan=metodologia'
        }),
        label="28.2 ¿Qué modelos estadísticos o econométricos aplica su organismo para evaluar la efectividad de los indicadores de producto y su relación con indicadores de resultado?"
    )
    p28_2_especificar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p27_articulacion=1,2,3 p28_2_modelos_estadisticos=otro',
            'placeholder': 'Especifique'
        }),
        label="Especifique otro modelo"
    )

    # P29: Rol con políticas públicas
    p29_rol_politicas = forms.ChoiceField(
        choices=P29_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="29. ¿Cuál es el rol de su organismo con las políticas públicas vigentes aprobadas en la Alcaldía Distrital de Santiago de Cali y/o de orden nacional?"
    )
    p29_otro_especificar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p29_rol_politicas=4',
            'placeholder': 'Especifique'
        }),
        label="Especifique"
    )

    # P29.1: Metodología de seguimiento (condicional: P29=1)
    P29_1_OPCIONES = [
        ('cuantitativo', 'Análisis cuantitativo: uso de estadísticas y datos numéricos para evaluar resultados.'),
        ('cualitativo', 'Análisis cualitativo: recolección y análisis de información no numérica, como entrevistas y grupos focales.'),
        ('mixto', 'Método mixto: combinación de análisis cuantitativo y cualitativo para una evaluación integral.'),
        ('resultados', 'Monitoreo basado en resultados: enfoque en indicadores de producto del Plan de Desarrollo Distrital y sus resultados específicos con la política pública.'),
        ('participativas', 'Evaluaciones participativas: involucrar a las partes interesadas en la evaluación del resultado y la efectividad.'),
        ('sistemas', 'Sistemas de información de política pública: uso de herramientas basadas en sistemas de información para recopilar y analizar datos en contextos específicos de política pública.'),
        ('encuestas', 'Encuestas y cuestionarios: recopilación de datos a través de encuestas estructuradas para medir percepciones y resultados.'),
        ('otro', 'Otro(s) (especificar)'),
    ]
    p29_1_metodologia = forms.MultipleChoiceField(
        choices=P29_1_OPCIONES,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'iced-checkbox iced-conditional',
            'data-show-if': 'p29_rol_politicas=1'
        }),
        required=False,
        label="29.1 Como organismo líder y responsable de la implementación y/o de recopilador de datos para la realización de seguimiento y análisis de resultados, ¿qué metodología usa para el seguimiento de las políticas públicas?"
    )
    p29_1_especificar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p29_rol_politicas=1 p29_1_metodologia=otro',
            'placeholder': 'Especifique'
        }),
        label="Especifique"
    )

    # P29.2: Frecuencia de seguimiento (condicional: P29=1)
    P29_2_OPCIONES = [
        ('mensual', 'Mensual'),
        ('trimestral', 'Trimestral'),
        ('semestral', 'Semestral'),
        ('anual', 'Anual'),
    ]
    p29_2_frecuencia = forms.MultipleChoiceField(
        choices=P29_2_OPCIONES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'iced-checkbox iced-conditional',
            'data-show-if': 'p29_rol_politicas=1'
        }),
        label="29.2 ¿Con qué frecuencia realiza el seguimiento y análisis de los resultados de las políticas públicas?"
    )

    # P29.3: Medios de divulgación (condicional: P29=1)
    P29_3_OPCIONES = [
        ('informes', 'Informes técnicos: publicación de informes detallados que presentan los resultados y análisis.'),
        ('web', 'Sitio Web Oficial: disponibilidad de información en línea a través del sitio web del organismo.'),
        ('redes', 'Redes sociales: uso de plataformas como Facebook, X(Twitter) e Instagram para compartir resultados y actualizaciones.'),
        ('boletines', 'Boletines informativos: envío regular de boletines a suscriptores con resúmenes de resultados y análisis.'),
        ('presentaciones', 'Presentaciones y talleres: organización de eventos presenciales o virtuales para presentar resultados a las partes interesadas.'),
        ('conferencias', 'Conferencias y seminarios: participación en eventos académicos o profesionales para discutir hallazgos y recomendaciones.'),
        ('dashboards', 'Plataformas interactivas: uso de herramientas digitales interactivas (como dashboards) que permiten a los usuarios explorar datos en tiempo real.'),
        ('otro', 'Otro(s) (especificar)'),
    ]
    p29_3_medios_divulgacion = forms.MultipleChoiceField(
        choices=P29_3_OPCIONES,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'iced-checkbox iced-conditional',
            'data-show-if': 'p29_rol_politicas=1'
        }),
        required=False,
        label="29.3 ¿Por qué medios realiza la divulgación del seguimiento y análisis de los resultados de las políticas públicas?"
    )
    p29_3_especificar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p29_rol_politicas=1 p29_3_medios_divulgacion=otro',
            'placeholder': 'Especifique'
        }),
        label="Especifique"
    )

    # P29.4: Acciones post-seguimiento (condicional: P29=1)
    P29_4_OPCIONES = [
        ('presentacion_directiva', 'Presentación de los resultados del seguimiento a la parte directiva responsable de la política pública.'),
        ('distribucion_informes', 'Distribución de informes que resumen los hallazgos del seguimiento a los organismos partícipes de la política.'),
        ('retroalimentacion', 'Reuniones de retroalimentación: organización de reuniones con partes interesadas para discutir los resultados y recibir comentarios.'),
        ('ajuste_estrategias', 'Ajuste de estrategias: modificación de las estrategias y acciones implementadas con base en los resultados obtenidos.'),
        ('recomendaciones', 'Formulación de recomendaciones: desarrollo de recomendaciones basadas en el análisis para mejorar la efectividad de la política.'),
        ('capacitacion', 'Capacitación del personal: capacitación y actualización del personal sobre los hallazgos y nuevas estrategias.'),
        ('divulgacion_publica', 'Divulgación pública: comunicación de los resultados a través de medios oficiales, redes sociales y eventos públicos.'),
        ('monitoreo_continuo', 'Monitoreo continuo: establecimiento de un sistema para el monitoreo continuo y la evaluación periódica de la política pública.'),
        ('investigacion', 'Investigación adicional: realización de estudios complementarios para profundizar en aspectos específicos identificados durante el seguimiento.'),
        ('otro', 'Otras acciones (especificar)'),
        ('ninguna', 'No desarrolla ninguna de las anteriores'),
    ]
    p29_4_acciones = forms.MultipleChoiceField(
        choices=P29_4_OPCIONES,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'iced-checkbox iced-conditional',
            'data-show-if': 'p29_rol_politicas=1'
        }),
        required=False,
        label="29.4 ¿Qué acciones realiza una vez generado el seguimiento a la política pública?"
    )
    p29_4_especificar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p29_rol_politicas=1 p29_4_acciones=otro',
            'placeholder': 'Especifique'
        }),
        label="Especifique"
    )

    # P30: Lineamientos metodológicos
    p30_lineamientos_metodologicos = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'exclusiva': 'ninguno',
            'con_detalle': ['internacionales', 'otros'],  # Array de códigos que tienen input de detalle
            'columnas': [
                {'name': 'cual', 'label': '¿Cuál(es)?', 'tipo': 'texto', 'placeholder': 'Especifique'},
            ],
            'opciones': [
                {'codigo': 'alcaldia_cali', 'texto': 'Lineamientos de la Alcaldía de Santiago de Cali — Pase a la tabla inferior'},
                {'codigo': 'dnp', 'texto': 'Guía para la Construcción y Análisis de Indicadores — Departamento Nacional de Planeación (DNP)'},
                {'codigo': 'dane', 'texto': 'Guía para Diseño, Construcción e Interpretación de Indicadores — Departamento Administrativo Nacional de Estadística (DANE)'},
                {'codigo': 'dafp', 'texto': 'Guía para la construcción y el análisis de Indicadores de Gestión — Departamento Administrativo de la Función Pública (DAFP)'},
                {'codigo': 'internacionales', 'texto': 'Referentes internacionales (OCDE, PNUD, FAO)'},
                {'codigo': 'otros', 'texto': 'Otros lineamientos'},
                {'codigo': 'ninguno', 'texto': 'No implementa ningún lineamiento'},
            ],
        }),
        label="30. Indique cuáles de los siguientes lineamientos metodológicos implementa el organismo:",
        help_text="Seleccione los lineamientos que aplica. Si selecciona 'Lineamientos de la Alcaldía de Santiago de Cali', debe completar la tabla inferior."
    )

    # Tabla condicional de lineamientos de la Alcaldía (sin número de pregunta, se muestra inline)
    p30_tabla_alcaldia = forms.CharField(
        required=False,
        widget=iced_widget('tabla-compleja', {
            'min_filas': 1,
            'max_filas': 10,
            'columnas': [
                {'name': 'codigo_mop', 'label': 'Código MOP / ID', 'tipo': 'select', 'opciones': [
                    {'valor': '', 'texto': '--- Seleccione ---'},
                    {'valor': 'MEDE01.05.02.P025.F001', 'texto': 'MEDE01.05.02.P025.F001 | Plan de trabajo por proceso'},
                    {'valor': 'MEDE01.05.02.P025.G001', 'texto': 'MEDE01.05.02.P025.G001 | Guía técnica para la formulación, medición y seguimiento'},
                    {'valor': 'MEDE01.07.01.P001.I001', 'texto': 'MEDE01.07.01.P001.I001 | Instructivo de diligenciamiento del formulario'},
                    {'valor': 'MEDE01.07.01.P003.F001', 'texto': 'MEDE01.07.01.P003.F001 | Autorización AMDA'},
                    {'valor': 'MEDE01.07.01.P003.G001', 'texto': 'MEDE01.07.01.P003.G001 | Guía para documentación de una Operación Estadística'},
                    {'valor': 'MEDE01.07.01.P003.G002', 'texto': 'MEDE01.07.01.P003.G002 | Guía para la documentación de sistemas de información'},
                    {'valor': 'MEDE01.07.01.P003.G003', 'texto': 'MEDE01.07.01.P003.G003 | Guía para construcción de diccionario de datos'},
                    {'valor': 'MEDE01.07.01.P005.F002', 'texto': 'MEDE01.07.01.P005.F002 | Ficha Técnica de Formulación de Indicadores'},
                    {'valor': 'MEDE01.07.01.P005.F003', 'texto': 'MEDE01.07.01.P005.F003 | Registro de Metadatos de indicadores'},
                    {'valor': 'MEDE01.07.01.P005.F005', 'texto': 'MEDE01.07.01.P005.F005 | Ficha Técnica de Seguimiento de Indicadores'},
                    {'valor': 'MEDE01.07.01.P005.I002', 'texto': 'MEDE01.07.01.P005.I002 | Instructivo para el diligenciamiento de las fichas técnicas'},
                    {'valor': 'MEDE01.07.01.P008.G002', 'texto': 'MEDE01.07.01.P008.G002 | Guía para el diseño e implementación de observatorios'},
                    {'valor': 'MEDE01.07.01.P009.G002', 'texto': 'MEDE01.07.01.P009.G002 | Guía metodológica para recopilación sistemática de datos'},
                    {'valor': 'MEDE01.07.01.P009.G003', 'texto': 'MEDE01.07.01.P009.G003 | Guía técnica para recopilación sistemática de datos'},
                    {'valor': 'MEDE01.07.01.P009.G004', 'texto': 'MEDE01.07.01.P009.G004 | Guía de uso y aplicación del marco geoestadístico'},
                    {'valor': 'MEDE01.07.01.18.P008', 'texto': 'MEDE01.07.01.18.P008 | Guía para el diseño e implementación de observatorios'},
                    {'valor': 'MEDE01.07.01.18P009', 'texto': 'MEDE01.07.01.18P009 | Guía para documentación de una Operación Estadística'},
                    {'valor': 'MEDE01.07.01.18.P05.F02', 'texto': 'MEDE01.07.01.18.P05.F02 | Ficha Técnica de Formulación de Indicadores'},
                    {'valor': 'MEDE01.07.01.18.P05.F04', 'texto': 'MEDE01.07.01.18.P05.F04 | Ficha Técnica de Seguimiento de Indicadores de Trámite'},
                    {'valor': 'MEDE01.07.01.18.P05.F05', 'texto': 'MEDE01.07.01.18.P05.F05 | Ficha Técnica de Seguimiento de Indicadores'},
                    {'valor': 'otro', 'texto': 'Otro (especificar código en la descripción)'},
                ]},
                {'name': 'descripcion', 'label': 'Descripción del lineamiento', 'tipo': 'texto', 'placeholder': 'Ej: Plan de trabajo por proceso'},
            ],
            'data-show-if': 'p30_lineamientos_metodologicos=alcaldia_cali',
        }),
        label="Seleccione los lineamientos de la Alcaldía que implementa:",
        help_text="Agregue una fila por cada lineamiento de la Alcaldía que implementa. Puede agregar hasta 10 lineamientos."
    )

    def _err(self, field, message):
        """add_error tolerante a campos eliminados por el filtro de equipos."""
        if field in self.fields:
            self.add_error(field, message)

    def clean(self):
        """Validaciones condicionales del módulo D2 (P26-P30).

        Los campos condicionales usan required=False + data-show-if en el
        frontend, así que aquí se exige su respuesta cuando el disparador
        (pregunta padre) así lo indica.
        """
        cleaned = super().clean()

        # El wizard puede haber eliminado campos por equipo (get_form);
        # _err valida solo los que siguen presentes para evitar
        # ValueError 'has no field named ...'.

        # --- P26: estructura de análisis ---
        p26 = cleaned.get('p26_estructura_analisis') or []
        if not p26:
            self._err('p26_estructura_analisis',
                           'Debe seleccionar al menos una opción.')
        else:
            if ({'no_aplica', 'no_realiza'} & set(p26)) and len(p26) > 1:
                self._err(
                    'p26_estructura_analisis',
                    'Las opciones "No aplica" / "No se realiza consolidación" '
                    'no pueden combinarse con otras opciones.'
                )
            if 'otro' in p26 and not (cleaned.get('p26_otro_especificar') or '').strip():
                self._err('p26_otro_especificar', 'Especifique la otra forma de análisis.')

        # --- P27→P28: cadena de articulación ---
        p27 = cleaned.get('p27_articulacion')
        if p27 in ('1', '2', '3'):
            p28 = cleaned.get('p28_como_articulan') or []
            if not p28:
                self._err('p28_como_articulan',
                               'Debe seleccionar al menos una opción.')
            else:
                if ({'no_es_necesario', 'no_articulan'} & set(p28)) and len(p28) > 1:
                    self._err(
                        'p28_como_articulan',
                        '"No es necesario" / "No se articulan" no pueden '
                        'combinarse con otras opciones.'
                    )
                if 'reuniones' in p28 and not cleaned.get('p28_1_frecuencia_reuniones'):
                    self._err('p28_1_frecuencia_reuniones',
                                   'Indique la frecuencia de las reuniones.')
                if 'metodologia' in p28 and not cleaned.get('p28_2_modelos_estadisticos'):
                    self._err('p28_2_modelos_estadisticos',
                                   'Indique el modelo estadístico o econométrico utilizado.')
                if 'otro' in p28 and not (cleaned.get('p28_otro_especificar') or '').strip():
                    self._err('p28_otro_especificar', 'Especifique la otra herramienta.')

            p28_2 = cleaned.get('p28_2_modelos_estadisticos') or []
            if 'otro' in p28_2 and not (cleaned.get('p28_2_especificar') or '').strip():
                self._err('p28_2_especificar', 'Especifique el otro modelo.')

        # --- P29: cadena de políticas públicas ---
        p29 = cleaned.get('p29_rol_politicas')
        if p29 == '4' and not (cleaned.get('p29_otro_especificar') or '').strip():
            self._err('p29_otro_especificar', 'Especifique el otro rol.')

        if p29 == '1':
            # P29.1 metodología (obligatoria + especificar si 'otro')
            if not cleaned.get('p29_1_metodologia'):
                self._err('p29_1_metodologia',
                               'Indique la metodología de seguimiento utilizada.')
            elif 'otro' in cleaned.get('p29_1_metodologia', []) \
                    and not (cleaned.get('p29_1_especificar') or '').strip():
                self._err('p29_1_especificar', 'Especifique la otra metodología.')

            # P29.2 frecuencia (obligatoria)
            if not cleaned.get('p29_2_frecuencia'):
                self._err('p29_2_frecuencia',
                               'Indique la frecuencia del seguimiento.')

            # P29.3 medios de divulgación (obligatoria + especificar si 'otro')
            if not cleaned.get('p29_3_medios_divulgacion'):
                self._err('p29_3_medios_divulgacion',
                               'Indique los medios de divulgación.')
            elif 'otro' in cleaned.get('p29_3_medios_divulgacion', []) \
                    and not (cleaned.get('p29_3_especificar') or '').strip():
                self._err('p29_3_especificar', 'Especifique el otro medio.')

            # P29.4 acciones (obligatoria + especificar si 'otro' + 'ninguna' exclusiva)
            p29_4 = cleaned.get('p29_4_acciones') or []
            if not p29_4:
                self._err('p29_4_acciones',
                               'Indique las acciones realizadas o "No desarrolla ninguna".')
            else:
                if 'ninguna' in p29_4 and len(p29_4) > 1:
                    self._err(
                        'p29_4_acciones',
                        '"No desarrolla ninguna de las anteriores" no puede '
                        'combinarse con otras opciones.'
                    )
                if 'otro' in p29_4 and not (cleaned.get('p29_4_especificar') or '').strip():
                    self._err('p29_4_especificar', 'Especifique la otra acción.')

        # --- P30: lineamientos metodológicos (JSON checkbox-tabla) ---
        p30_raw = cleaned.get('p30_lineamientos_metodologicos')
        p30_data = {}
        if p30_raw:
            try:
                p30_data = json.loads(p30_raw) if isinstance(p30_raw, str) else p30_raw
            except (ValueError, TypeError):
                p30_data = {}
        seleccionados = [
            cod for cod, row in (p30_data.items() if isinstance(p30_data, dict) else [])
            if isinstance(row, dict) and row.get('seleccion')
        ]
        if not seleccionados:
            self._err('p30_lineamientos_metodologicos',
                           'Debe seleccionar al menos un lineamiento o "No implementa ningún lineamiento".')
        else:
            if 'ninguno' in seleccionados and len(seleccionados) > 1:
                self._err(
                    'p30_lineamientos_metodologicos',
                    '"No implementa ningún lineamiento" no puede combinarse con otras opciones.'
                )
            # Detalle 'cual' obligatorio para internacionales y otros
            for cod in ('internacionales', 'otros'):
                if cod in seleccionados:
                    row = p30_data.get(cod) or {}
                    if not (row.get('cual') or '').strip():
                        self._err(
                            'p30_lineamientos_metodologicos',
                            f'Debe especificar cuál(es) en la opción '
                            f'"{"Referentes internacionales" if cod == "internacionales" else "Otros lineamientos"}".'
                        )
            # Tabla Alcaldía: requerida si se marcó alcaldia_cali
            if 'alcaldia_cali' in seleccionados:
                tabla_raw = cleaned.get('p30_tabla_alcaldia')
                try:
                    filas = json.loads(tabla_raw) if isinstance(tabla_raw, str) else (tabla_raw or [])
                except (ValueError, TypeError):
                    filas = []
                filas_validas = [
                    f for f in filas
                    if isinstance(f, dict) and (f.get('codigo_mop') or '').strip()
                ]
                if not filas_validas:
                    self._err(
                        'p30_tabla_alcaldia',
                        'Seleccionó "Lineamientos de la Alcaldía de Santiago de Cali": '
                        'agregue al menos un lineamiento en la tabla.'
                    )

        return cleaned


# =============================================================================
# MÓDULO D3: METODOLOGÍA ESTADÍSTICA - ANALÍTICA DE DATOS (P31-P32)
# =============================================================================

class ICEDModuloD3Form(ICEDBaseForm):
    """Módulo D3: Metodología Estadística - Analítica de Datos (P31-P32)."""
    step_name = 'metodologia_d3'

    # P31: Tipo de analítica
    p31_tipo_analitica = forms.ChoiceField(
        choices=P31_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="31. ¿Qué tipo de analítica y modelos utiliza su organismo para optimizar los procesos de recolección, análisis y toma de decisiones?"
    )
    p31_descripcion_productos = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'iced-textarea iced-conditional',
            'rows': 3,
            'data-show-if': 'p31_tipo_analitica=2,3,4,5',
            'placeholder': 'Describa los productos obtenidos'
        }),
        label="Describa los productos obtenidos"
    )
    p31_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p31_tipo_analitica=2,3,4,5',
            'placeholder': 'https://...'
        }),
        label="URL de evidencia"
    )

    # P31.1: Frecuencia de uso de modelos avanzados (condicional: P31 in [2,3,4,5])
    p31_1_frecuencia = forms.ChoiceField(
        choices=[('', '---')] + P31_1_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'iced-select iced-conditional',
            'data-show-if': 'p31_tipo_analitica=2,3,4,5'
        }),
        label="31.1 ¿Con qué frecuencia se utilizan los modelos avanzados para apoyar la toma de decisiones?"
    )

    # P32: Herramientas de analítica avanzada DATIC
    p32_analitica_datic = forms.ChoiceField(
        choices=P32_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="32. ¿Actualmente conoce o hace uso de las herramientas de analítica avanzada con las que cuenta la entidad por medio de DATIC?"
    )
    p32_caso_uso = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'iced-textarea iced-conditional', 'rows': 3,
            'data-show-if': 'p32_analitica_datic!=6',
            'placeholder': 'Describa cuál es/sería el caso de uso de analítica avanzada con DATIC'
        }),
        label="Por favor describa cual es/seria el caso de uso de analítica avanzada con DATIC"
    )


# =============================================================================
# MÓDULO D4: METODOLOGÍA ESTADÍSTICA - OBSERVATORIOS (P33-P35)
# =============================================================================

# P34: Temas principales de observatorios y su área temática asociada.
# Cada tema principal determina un única área temática.
P34_TEMAS_AMBIENTAL = [
    'Asentamientos Humanos y Salud Ambiental',
    'Condiciones y Calidad Ambiental',
    'Eventos Extremos y Desastres',
    'Protección Ambiental, Gestión y Participación/Acción Ciudadana',
    'Recursos Ambientales y Su Uso',
    'Residuos',
]
P34_TEMAS_ECONOMICA = [
    'Agricultura, Ganadería y Pesca',
    'Comercio',
    'Construcción',
    'Cuentas Económicas',
    'Finanzas Públicas y Estadísticas Fiscales',
    'Índices de Precios y Costos',
    'Industria',
    'Minero Energético',
    'Moneda, Banca y Finanzas',
    'Servicios (Turismo, Hoteles, Restaurantes y Otros)',
    'Tecnologías de la Información y las Comunicaciones',
    'Transporte',
]
P34_TEMAS_SOCIODEMOGRAFICA = [
    'Actividad Política y Asociativa',
    'Administración Pública',
    'Cultura',
    'Demografía y Población',
    'Deporte y Recreación',
    'Educación, Ciencia, Tecnología E Innovación',
    'Justicia',
    'Mercado Laboral y Seguridad Social',
    'Nivel, Calidad y Condiciones de Vida',
    'Salud',
    'Seguridad y Defensa',
    'Servicios Públicos Domiciliarios',
]
P34_TEMAS = P34_TEMAS_AMBIENTAL + P34_TEMAS_ECONOMICA + P34_TEMAS_SOCIODEMOGRAFICA
P34_AREAS = ['Ambiental', 'Económica', 'Sociodemográfica']
# Mapa tema_principal -> area_tematica
P34_TEMA_AREA = (
    {t: 'Ambiental' for t in P34_TEMAS_AMBIENTAL}
    | {t: 'Económica' for t in P34_TEMAS_ECONOMICA}
    | {t: 'Sociodemográfica' for t in P34_TEMAS_SOCIODEMOGRAFICA}
)


class ICEDModuloD4Form(ICEDBaseForm):
    """Módulo D4: Metodología Estadística - Observatorios (P33-P35)."""
    step_name = 'metodologia_d4'

    # P33: ¿Cuenta con observatorio?
    p33_tiene_observatorio = forms.ChoiceField(
        choices=[('si', 'Sí'), ('no', 'No')],
        widget=forms.RadioSelect(attrs={'class': 'iced-radio'}),
        label="33. ¿El organismo actualmente cuenta con un observatorio?"
    )
    p33_observatorios = forms.CharField(
        required=False,
        widget=iced_widget('desplegables-multiples', {
            'cantidad': 3,
            'permitir_otro': True,
            'data-show-if': 'p33_tiene_observatorio=si',
            'opciones': [
                'Observatorio Ambiental',
                'Observatorio Turístico de la Alcaldía Distrital de Santiago de Cali',
                'Observatorio de Espacio Público',
                'Observatorio de Hacienda Pública Distrital',
                'Observatorio de Movilidad Sostenible y Seguridad Vial',
                'Observatorio de Movilidad Sostenible - MOVIS',
                'Observatorio de Paz, Derechos Humanos y Cultura Ciudadana',
                'Observatorio de Políticas Públicas Sociales',
                'Observatorio de Salud del Distrito de Santiago de Cali',
                'Observatorio de Seguridad',
                'Observatorio de Vivienda y Hábitat',
                'Observatorio de la Educación Distrito Especial de Santiago de Cali',
                'Observatorio de la Secretaría de Cultura de Cali',
                'Observatorio del Inmobiliario Catastral',
                'Observatorio de Ordenamiento Territorial – Expediente Municipal',
            ],
        }),
        label="Observatorios seleccionados",
        help_text="Hasta 3 observatorios desde tabla de referencia"
    )

    # P34: Tabla de información de observatorios
    p34_info_observatorios = forms.CharField(
        required=False,
        widget=iced_widget('tabla-compleja', {
            'min_filas': 1,
            'max_filas': 5,
            'columnas': [
                {'name': 'nombre_observatorio', 'label': 'Nombre del Observatorio', 'tipo': 'select', 'opciones': [
                    {'valor': '', 'texto': '--- Seleccione ---'},
                    {'valor': 'ambiental', 'texto': 'Observatorio Ambiental'},
                    {'valor': 'turistico', 'texto': 'Observatorio Turístico de la Alcaldía Distrital de Santiago de Cali'},
                    {'valor': 'espacio_publico', 'texto': 'Observatorio de Espacio Público'},
                    {'valor': 'hacienda', 'texto': 'Observatorio de Hacienda Pública Distrital'},
                    {'valor': 'movilidad_sostenible', 'texto': 'Observatorio de Movilidad Sostenible y Seguridad Vial'},
                    {'valor': 'movis', 'texto': 'Observatorio de Movilidad Sostenible - MOVIS'},
                    {'valor': 'paz', 'texto': 'Observatorio de Paz, Derechos Humanos y Cultura Ciudadana'},
                    {'valor': 'politicas_publicas', 'texto': 'Observatorio de Políticas Públicas Sociales'},
                    {'valor': 'salud', 'texto': 'Observatorio de Salud del Distrito de Santiago de Cali'},
                    {'valor': 'seguridad', 'texto': 'Observatorio de Seguridad'},
                    {'valor': 'vivienda', 'texto': 'Observatorio de Vivienda y Hábitat'},
                    {'valor': 'educacion', 'texto': 'Observatorio de la Educación Distrito Especial de Santiago de Cali'},
                    {'valor': 'cultura', 'texto': 'Observatorio de la Secretaría de Cultura de Cali'},
                    {'valor': 'inmobiliario', 'texto': 'Observatorio del Inmobiliario Catastral'},
                    {'valor': 'ordenamiento', 'texto': 'Observatorio de Ordenamiento Territorial – Expediente Municipal'},
                    {'valor': 'otro', 'texto': 'Otro (especificar en columna ¿Cuáles?)'},
                ]},
                {'name': 'fecha_creacion', 'label': 'Fecha de creación', 'tipo': 'fecha'},
                {'name': 'tema_principal', 'label': 'Tema principal', 'tipo': 'select', 'opciones': P34_TEMAS},
                {'name': 'area_tematica', 'label': 'Área temática', 'tipo': 'select', 'opciones': P34_AREAS},
                {'name': 'tiene_documentos_mop', 'label': '¿Cuenta con documentación metodológica relacionada en el MOP?', 'tipo': 'booleano'},
                {'name': 'produce_documentos', 'label': '¿Produce documentos, investigaciones y/o reportes con información estadística?', 'tipo': 'booleano'},
                {'name': 'cuales_documentos', 'label': '¿Cuáles?', 'tipo': 'texto'},
            ],
            # Al elegir tema_principal se autollenar area_tematica según el mapa
            'autollenado': {
                'campo_origen': 'tema_principal',
                'campo_destino': 'area_tematica',
                'mapa': P34_TEMA_AREA,
            },
            'data-show-if': 'p33_tiene_observatorio=si',
        }),
        label="34. A continuación, por favor, relacione la información correspondiente a los observatorios que el organismo lidera:",
        help_text="Seleccione el observatorio de la lista y complete la información solicitada."
    )

    # P35: Documentación metodológica del observatorio
    p35_documentacion_observatorio = forms.CharField(
        required=False,
        widget=iced_widget('tabla-compleja', {
            'min_filas': 1,
            'max_filas': 10,
            'columnas': [
                {'name': 'tipo_documento', 'label': 'Tipo de documento', 'tipo': 'select', 'requerido': True, 'opciones': [
                    {'valor': '', 'texto': '--- Seleccione ---'},
                    {'valor': 'metodologia', 'texto': 'Metodología'},
                    {'valor': 'protocolo', 'texto': 'Protocolo'},
                    {'valor': 'manual', 'texto': 'Manual'},
                    {'valor': 'guia', 'texto': 'Guía'},
                    {'valor': 'instructivo', 'texto': 'Instructivo'},
                    {'valor': 'otro', 'texto': 'Otro'},
                ]},
                {'name': 'nombre_documento', 'label': 'Nombre del documento', 'tipo': 'texto', 'requerido': True, 'placeholder': 'Nombre del documento'},
                {'name': 'codigo_mop', 'label': 'Codificación en el MOP', 'tipo': 'texto', 'placeholder': 'Ej: MEDE01.05.02.P025.F001'},
                {'name': 'url', 'label': 'URL', 'tipo': 'url', 'placeholder': 'https://...'},
                {'name': 'descripcion', 'label': 'Descripción', 'tipo': 'textarea', 'rows': 4, 'requerido': True, 'placeholder': 'Describa el documento con el nivel de detalle requerido'},
            ],
            'data-show-if': 'p33_tiene_observatorio=si',
        }),
        label="35. Relacione la documentación metodológica existente del observatorio (URL y/o Codificación en el MOP)",
        help_text="Agregue una fila por cada documento metodológico. Tipo, nombre y descripción son obligatorios; codificación MOP y URL son opcionales. Puede agregar hasta 10 documentos."
    )

    def clean_p35_documentacion_observatorio(self):
        valor = _validar_urls_json(self.cleaned_data.get('p35_documentacion_observatorio'))
        # Validar campos obligatorios por fila (tipo, nombre, descripción)
        try:
            filas = json.loads(valor) if isinstance(valor, str) else valor
        except (ValueError, TypeError):
            return valor
        if isinstance(filas, list):
            obligatorios = [
                ('tipo_documento', 'Tipo de documento'),
                ('nombre_documento', 'Nombre del documento'),
                ('descripcion', 'Descripción'),
            ]
            for i, fila in enumerate(filas):
                if not isinstance(fila, dict):
                    continue
                # Solo validar filas que tengan algún dato diligenciado
                if not any((v or '').strip() for v in fila.values()):
                    continue
                faltantes = [lbl for k, lbl in obligatorios if not (fila.get(k) or '').strip()]
                if faltantes:
                    raise forms.ValidationError(
                        f"Documento #{i+1}: falta {', '.join(faltantes)}."
                    )
        return valor


# =============================================================================
# MÓDULO E: ACCESIBILIDAD Y USO (P36-P42) — Peso 25%
# NOTA: la fuente de verdad de las ponderaciones es PESOS_DIMENSIONES en
# calcular_iced.py (0.25 por dimensión). El 20% documentado aquí era un error
# de documentación (IC-01); pendiente confirmación metodológica.
# =============================================================================

class ICEDModuloEForm(ICEDBaseForm):
    """Módulo E: Accesibilidad y Uso de la Información Estadística (P36-P42)."""
    step_name = 'accesibilidad'

    # P36: Uso de indicadores
    p36_uso_indicadores = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'columnas': [
                {'name': 'url', 'label': 'Relacione URL evidencia', 'tipo': 'url', 'placeholder': ''},
            ],
            'opciones': [
                {'codigo': 'diagnostico_pdd', 'texto': 'Hacer diagnóstico, seguimiento o evaluación al Plan de Desarrollo Distrital'},
                {'codigo': 'rendicion_cuentas', 'texto': 'Presentar informes de rendición de cuentas'},
                {'codigo': 'pot', 'texto': 'Formular o actualizar el Plan de Ordenamiento Territorial POT vigente.'},
                {'codigo': 'evaluar_pp', 'texto': 'Evaluar las políticas públicas'},
            ],
        }),
        label="36. Los indicadores existentes en su organismo, ¿se usaron para?",
        help_text="Seleccione las opciones y proporcione la URL de evidencia para cada una."
    )

    # P37: Principales usuarios (checkbox-tabla con columna ¿Cuál(es)?)
    p37_usuarios = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'exclusiva': 'ninguno',
            'con_detalle': ['organismos_misma', 'organismos_intl', 'presidencia', 'ministerios', 'control', 'otras_nacional', 'territorial', 'gremios', 'privadas', 'academia', 'otro'],
            'columnas': [
                {'name': 'cual', 'label': '¿Cuál(es)?', 'tipo': 'texto', 'placeholder': 'Especifique'},
            ],
            'opciones': [
                {'codigo': 'organismos_misma', 'texto': 'Organismos de la misma entidad'},
                {'codigo': 'organismos_intl', 'texto': 'Organismos internacionales'},
                {'codigo': 'presidencia', 'texto': 'Presidencia de la República'},
                {'codigo': 'ministerios', 'texto': 'Ministerios'},
                {'codigo': 'control', 'texto': 'Organismos de Control'},
                {'codigo': 'otras_nacional', 'texto': 'Otras entidades del orden Nacional'},
                {'codigo': 'territorial', 'texto': 'Entidades de orden Territorial'},
                {'codigo': 'gremios', 'texto': 'Gremios'},
                {'codigo': 'privadas', 'texto': 'Entidades privadas'},
                {'codigo': 'academia', 'texto': 'Academia'},
                {'codigo': 'publico', 'texto': 'Público en general'},
                {'codigo': 'otro', 'texto': 'Otro(s)'},
                {'codigo': 'ninguno', 'texto': 'No tiene ningún otro usuario de información'},
            ],
        }),
        label="37. Señale cuáles son los principales usuarios de la información estadística que produce el organismo",
        help_text="Seleccione los usuarios y especifique cuáles en la columna correspondiente cuando aplique."
    )

    # P38: Productos de difusión (checkbox-tabla con exclusiva 'ninguna')
    p38_productos_difusion = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'exclusiva': 'ninguna',
            'con_detalle': ['otro'],  # Solo 'Otro(s)' tiene campo de detalle
            'columnas': [
                {'name': 'cual', 'label': '¿Cuál(es)?', 'tipo': 'texto', 'placeholder': 'Especifique'},
            ],
            'opciones': [
                {'codigo': 'cuadros_salida', 'texto': 'Cuadros de salida (tablas)'},
                {'codigo': 'boletin', 'texto': 'Boletín estadístico'},
                {'codigo': 'anuario', 'texto': 'Anuario (Cali en cifras)'},
                {'codigo': 'mapas_sig', 'texto': 'Mapas estadísticos elaborados a través de sistemas de información geográfica para georreferenciar y difundir los datos (indicadores o estadísticas agregadas)'},
                {'codigo': 'bases_interactivas', 'texto': 'Bases de datos interactivas que permite a los usuarios consultar, actualizar y manipular datos de manera dinámica'},
                {'codigo': 'otro', 'texto': 'Otros productos'},
                {'codigo': 'ninguna', 'texto': 'No se realiza difusión — ¡Fin del formulario! Pase a Registrar Respuesta'},
            ],
        }),
        label="38. ¿Cuáles productos utiliza para difundir los resultados estadísticos?",
        help_text="Seleccione las opciones que correspondan. Para 'Otro(s)' especifique en la columna."
    )

    # P39: Medios de difusión (condicional: P38 no incluye 'ninguna')
    p39_medios_difusion = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'con_detalle': ['web', 'otro'],  # Solo web y otro tienen campos de detalle
            'columnas': [
                {'name': 'cual', 'label': '¿Cuál(es)?', 'tipo': 'texto', 'placeholder': 'Especifique'},
                {'name': 'url', 'label': 'Relacione URL', 'tipo': 'url', 'placeholder': 'https://... Separe con coma si son varios'},
            ],
            'opciones': [
                {'codigo': 'web', 'texto': 'Página web (SIS, ADDA, Página Web organismo, SICODE)'},
                {'codigo': 'fisico', 'texto': 'Medio físico'},
                {'codigo': 'electronico', 'texto': 'Medio electrónico'},
                {'codigo': 'otro', 'texto': 'Otro'},
            ],
            'data-show-if': 'p38_productos_difusion!=ninguna',
        }),
        label="39. ¿A través de qué medio(s) difunde los resultados estadísticos (agregados, indicadores), a los usuarios?",
        help_text="Seleccione los medios y complete la información solicitada. Para la opción 'Página web' y 'Otro', especifique y relacione la(s) URL(s) separando con coma si son varios."
    )

    # P40: Elementos publicados en web (condicional: P38 no incluye 'ninguna')
    p40_elementos_web = forms.CharField(
        required=False,
        widget=iced_widget('checkbox-tabla', {
            'columnas': [
                {'name': 'url', 'label': 'URL:', 'tipo': 'url', 'placeholder': ''},
            ],
            'opciones': [
                {'codigo': 'bd_anonimizadas', 'texto': 'Las bases de datos anonimizadas de las operaciones estadísticas'},
                {'codigo': 'resultados_indicadores', 'texto': 'Resultados de los indicadores de producto, ODS y de políticas públicas'},
                {'codigo': 'ficha_tecnica', 'texto': 'Ficha técnica de indicadores'},
                {'codigo': 'resultados_indicadores_2', 'texto': 'Resultados de los indicadores'},
                {'codigo': 'georreferenciadas', 'texto': 'Indicadores o estadísticas agregadas georreferenciadas'},
                {'codigo': 'series_historicas', 'texto': 'Resultados de indicadores con sus series históricas'},
                {'codigo': 'ficha_metodologica', 'texto': 'Ficha metodológica de operaciones estadísticas'},
                {'codigo': 'doc_metodologico', 'texto': 'Documento metodológico de operaciones estadísticas'},
                {'codigo': 'cuadros_salida', 'texto': 'Cuadros de salida y series históricas de las operaciones estadísticas'},
                {'codigo': 'calendario', 'texto': 'Calendario de difusión'},
                {'codigo': 'desagregacion_geo', 'texto': 'Indicadores o estadísticas con desagregación geográfica'},
                {'codigo': 'desagregacion_tematica', 'texto': 'Indicadores o estadísticas con desagregación temática o enfoque diferencia e intersectorial'},
                {'codigo': 'microdatos', 'texto': 'Microdatos'},
                {'codigo': 'observatorios', 'texto': 'Documentos y/o resultados asociados a los observatorios'},
            ],
            'data-show-if': 'p38_productos_difusion!=ninguna',
        }),
        label="40. De los siguientes elementos, cuáles se publican en página web o micrositios de la entidad para disposición de los grupos de interés:",
        help_text="Seleccione los elementos y proporcione la URL para cada uno."
    )

    # P41: ¿Indaga satisfacción de usuarios? (condicional: P38 no incluye 'ninguna')
    p41_indaga_satisfaccion = forms.ChoiceField(
        choices=[('si', 'Sí'), ('no', 'No')],
        required=False,
        widget=forms.RadioSelect(attrs={
            'class': 'iced-radio',
            'data-show-if': 'p38_productos_difusion!=ninguna',
        }),
        label="41. ¿El organismo indaga si la información disponible en sus plataformas o canales de difusión satisface las necesidades de los usuarios?"
    )

    # P41.1: Mecanismos de medición (condicional: P41=Sí)
    P41_1_OPCIONES = [
        ('encuestas', 'Encuestas de satisfacción'),
        ('entrevistas', 'Entrevistas en profundidad'),
        ('grupos_focales', 'Grupos focales'),
        ('comentarios', 'Análisis de comentarios y sugerencias'),
        ('indicadores_uso', 'Indicadores de uso'),
        ('otro', 'Otros mecanismos'),
    ]
    p41_1_mecanismos = forms.MultipleChoiceField(
        choices=P41_1_OPCIONES,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'iced-checkbox iced-conditional',
            'data-show-if': 'p38_productos_difusion!=ninguna p41_indaga_satisfaccion=si'
        }),
        required=False,
        label="41.1 ¿Qué mecanismo utiliza para medir la satisfacción de las necesidades de los usuarios de la información estadística producida?"
    )
    p41_1_especificar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'iced-input iced-conditional',
            'data-show-if': 'p38_productos_difusion!=ninguna p41_1_mecanismos=otro',
            'placeholder': 'Especifique'
        }),
        label="¿Cuál(es)?"
    )

    # P41.2: Matriz de satisfacción (condicional: P38 no incluye 'ninguna' y P41=Sí)
    p41_2_matriz_satisfaccion = forms.CharField(
        required=False,
        widget=iced_widget('matriz-satisfaccion', {
            'indicadores': [
                'La accesibilidad de la información estadística difundida',
                'La oportunidad y puntualidad de la información estadística difundida',
                'La relevancia de la información estadística difundida por el organismo',
            ],
            'niveles': [
                'Muy satisfechos',
                'Satisfechos',
                'Indiferentes',
                'Insatisfechos',
                'Muy insatisfechos',
            ],
            'urls': 2,
            'data-show-if': 'p38_productos_difusion!=ninguna p41_indaga_satisfaccion=si',
        }),
        label="41.2 De acuerdo con las mediciones de satisfacción realizadas, indique con una (X) la satisfacción de los usuarios frente a la calidad referente a:",
        help_text="Matriz: 3 indicadores × 5 niveles de satisfacción. Luego relacione las evidencias disponibles con 2 URLs."
    )

    # P42: Observaciones generales
    p42_observaciones = forms.CharField(
        max_length=4000,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'iced-textarea', 'rows': 5,
            'placeholder': 'Describa las observaciones relacionadas con particularidades en la aplicación del FICED'
        }),
        label="42. Observaciones generales"
    )

    def clean_p36_uso_indicadores(self):
        return _validar_urls_json(self.cleaned_data.get('p36_uso_indicadores'))

    def clean_p39_medios_difusion(self):
        return _validar_urls_json(self.cleaned_data.get('p39_medios_difusion'))

    def clean_p40_elementos_web(self):
        return _validar_urls_json(self.cleaned_data.get('p40_elementos_web'))

    def clean_p41_2_matriz_satisfaccion(self):
        return _validar_urls_json(self.cleaned_data.get('p41_2_matriz_satisfaccion'))

    def _err(self, field, message):
        """add_error tolerante a campos eliminados por el filtro de equipos."""
        if field in self.fields:
            self.add_error(field, message)

    def clean(self):
        cleaned = super().clean()
        # P41 solo aplica si el organismo difunde (P38 sin 'ninguna').
        # El campo es opcional a nivel de widget porque el JS lo oculta y lo
        # vacía cuando P38 = 'ninguna'; aquí se exige en el caso contrario.
        p38_raw = cleaned.get('p38_productos_difusion') or ''
        try:
            p38 = json.loads(p38_raw) if isinstance(p38_raw, str) and p38_raw else (p38_raw or {})
        except (ValueError, TypeError):
            p38 = {}
        difunde = True
        if isinstance(p38, dict):
            ninguna = p38.get('ninguna')
            if ninguna is True or (isinstance(ninguna, dict) and ninguna.get('seleccion')):
                difunde = False
        if difunde and not cleaned.get('p41_indaga_satisfaccion'):
            self._err('p41_indaga_satisfaccion', 'Este campo es obligatorio.')
        return cleaned


# =============================================================================
# DEFINICIÓN DE PASOS DEL WIZARD
# =============================================================================

class ICEDRevisionForm(ICEDBaseForm):
    """Paso final: revisión del resumen de respuestas y confirmación de envío."""
    step_name = 'revision'

    confirmar_envio = forms.BooleanField(
        required=True,
        label='Confirmo que la información diligenciada es correcta y autorizo el envío del formulario para validación.',
        error_messages={'required': 'Debe confirmar el envío para finalizar.'},
    )


ICED_WIZARD_FORMS = [
    ('identificacion', ICEDModuloAForm),
    ('entorno', ICEDModuloBForm),
    ('infraestructura_c1', ICEDModuloC1Form),
    ('infraestructura_c2', ICEDModuloC2Form),
    ('infraestructura_c3', ICEDModuloC3Form),
    ('metodologia_d1', ICEDModuloD1Form),
    ('metodologia_d2', ICEDModuloD2Form),
    ('metodologia_d3', ICEDModuloD3Form),
    ('metodologia_d4', ICEDModuloD4Form),
    ('accesibilidad', ICEDModuloEForm),
    ('revision', ICEDRevisionForm),
]

ICED_STEP_LABELS = {
    'identificacion': 'A. Identificación',
    'entorno': 'B. Entorno Institucional',
    'infraestructura_c1': 'C1. Herramientas',
    'infraestructura_c2': 'C2. Recurso Humano',
    'infraestructura_c3': 'C3. Recursos Financieros',
    'metodologia_d1': 'D1. Operaciones Estadísticas',
    'metodologia_d2': 'D2. Indicadores',
    'metodologia_d3': 'D3. Analítica',
    'metodologia_d4': 'D4. Observatorios',
    'accesibilidad': 'E. Accesibilidad y Uso',
    'revision': 'Revisión y Envío',
}
