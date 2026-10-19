"""Template filters para renderizar respuestas ICED de forma legible en el panel de validación."""

import json
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape

register = template.Library()


# =============================================================================
# Etiquetas derivadas de forms_iced.py (fuente única de verdad)
# =============================================================================
# _ESCALAS[field_key]        = {valor: texto} para ChoiceField (radio/select)
# _OPCIONES_CAMPO[field_key] = {codigo: texto} para MultipleChoiceField y
#                              opciones de widgets checkbox-tabla
# _FIELD_LABELS[field_key]   = label legible del campo
_ESCALAS = {}
_OPCIONES_CAMPO = {}
_FIELD_LABELS = {}


def _build_field_maps():
    """Construye los mapas de etiquetas desde los forms del wizard ICED.

    Se ejecuta de forma perezosa para no depender del orden de imports.
    """
    if _FIELD_LABELS:
        return
    try:
        from django import forms as dj_forms
        from indicadores.forms_iced import ICED_WIZARD_FORMS
    except Exception:
        return

    for _step, form_cls in ICED_WIZARD_FORMS:
        for name, field in form_cls.base_fields.items():
            if field.label:
                _FIELD_LABELS[name] = str(field.label)

            # Radio/select/multiple con choices explícitos
            choices = getattr(field, 'choices', None)
            if choices:
                mapa = {}
                for val, texto in choices:
                    if val == '':
                        continue
                    mapa[str(val)] = str(texto)
                if mapa:
                    if isinstance(field, dj_forms.ChoiceField) and not isinstance(field, dj_forms.MultipleChoiceField):
                        _ESCALAS[name] = mapa
                    _OPCIONES_CAMPO[name] = mapa

            # Widgets JSON (checkbox-tabla): opciones dentro de data-config
            cfg_raw = field.widget.attrs.get('data-config') if hasattr(field.widget, 'attrs') else None
            if cfg_raw:
                try:
                    cfg = json.loads(cfg_raw)
                except (ValueError, TypeError):
                    cfg = {}
                opciones = cfg.get('opciones') if isinstance(cfg, dict) else None
                if opciones:
                    _OPCIONES_CAMPO[name] = {
                        str(o.get('codigo')): str(o.get('texto'))
                        for o in opciones if isinstance(o, dict) and o.get('codigo')
                    }


@register.filter(name='iced_field_label')
def iced_field_label(field_key):
    """Label legible de un campo del FICED (fallback: el propio key)."""
    _build_field_maps()
    return _FIELD_LABELS.get(field_key, field_key)


# Mapas de opciones legibles por pregunta
_OPCIONES = {
    # P8 / P9 - Herramientas de planificación/mejoramiento
    'planes_trabajo': 'Planes de trabajo',
    'planes_accion': 'Planes de acción',
    'programas': 'Programas',
    'proyectos': 'Proyectos',
    'no_se_incluyen': 'No se incluyen',
    # P11 - Coordinación
    'no_participa': 'No participa',
    'observatorios': 'Observatorios',
    'mesas': 'Mesas de trabajo',
    'comites': 'Comités',
    'grupos': 'Grupos de trabajo',
    'comisiones': 'Comisiones',
    # P13 - Herramientas procesamiento
    'ninguna': 'Ninguna',
    'excel': 'Excel',
    'spss': 'SPSS',
    'stata': 'Stata',
    'r': 'R',
    'python': 'Python',
    'sas': 'SAS',
    'power_bi': 'Power BI',
    'tableau': 'Tableau',
    'qgis': 'QGIS/ArcGIS',
    # P14 - Gestores BD
    'ninguno': 'Ninguno',
    'sql_server': 'SQL Server',
    'postgresql': 'PostgreSQL',
    'mysql': 'MySQL',
    'oracle': 'Oracle',
    'mongodb': 'MongoDB',
    'access': 'Access',
    # P36 - Uso indicadores
    'diagnostico_pdd': 'Diagnóstico PDD',
    'rendicion_cuentas': 'Rendición de cuentas',
    'pot': 'POT',
    'politicas_publicas': 'Políticas públicas',
    # P37 - Usuarios
    'publico': 'Público general',
    'academia': 'Academia',
    'sector_privado': 'Sector privado',
    'gobierno': 'Gobierno',
    'organizaciones': 'Organizaciones',
    'medios': 'Medios de comunicación',
    'otro': 'Otro',
    # P38 - Productos difusión
    'cuadros_salida': 'Cuadros de salida',
    'boletines': 'Boletines',
    'anuarios': 'Anuarios',
    'infografias': 'Infografías',
    'dashboards': 'Dashboards',
    'documentos_tecnicos': 'Documentos técnicos',
    'presentaciones': 'Presentaciones',
    # P39 - Medios difusión
    'web': 'Página web',
    'redes_sociales': 'Redes sociales',
    'correo': 'Correo electrónico',
    'eventos': 'Eventos',
    # P40 - Elementos web
    'bd_anonimizadas': 'BD anonimizadas',
    'metadatos': 'Metadatos',
    'visualizaciones': 'Visualizaciones',
    'api': 'API',
    'documentacion': 'Documentación',
    # P41.1 - Mecanismos satisfacción
    'encuestas': 'Encuestas',
    'grupos_focales': 'Grupos focales',
    'buzones': 'Buzones',
    'entrevistas': 'Entrevistas',
    'pqrs': 'PQRS',
}

def _parse_json(value):
    """Intenta parsear string JSON, retorna el original si falla."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _label(code, field_key=None):
    """Convierte un código de opción a texto legible."""
    if field_key:
        mapa = _OPCIONES_CAMPO.get(field_key) or _ESCALAS.get(field_key)
        if mapa and code in mapa:
            return mapa[code]
    return _OPCIONES.get(code, code.replace('_', ' ').title())


def _render_bool(value):
    if str(value).lower() in ('si', 'sí', '1', 'true'):
        return '<span class="text-emerald-700 font-semibold">✓ Sí</span>'
    return '<span class="text-red-600 font-semibold">✗ No</span>'


def _render_escala(value, field_key):
    v = str(value)
    label = _label(v, field_key)
    if label == v.replace('_', ' ').title() and v not in _OPCIONES:
        label = f'Opción {v}'
    return f'<span class="font-medium">{escape(label)}</span> <span class="text-slate-400 text-[10px]">(opción {escape(v)})</span>'


def _render_checkbox_tabla(value, field_key=None):
    """Renderiza JSON tipo {"opcion": {"seleccion": true/false, ...}}"""
    data = _parse_json(value)
    if not isinstance(data, dict):
        return escape(str(value)) if value else '—'

    items = []
    for code, info in data.items():
        selected = False
        extras = {}
        if isinstance(info, dict):
            selected = info.get('seleccion', False)
            extras = {k: v for k, v in info.items() if k != 'seleccion' and v}
        elif info is True:
            selected = True

        if not selected:
            continue

        label = _label(code, field_key)
        extra_parts = []
        for ek, ev in extras.items():
            ek_label = ek.replace('_', ' ').capitalize()
            if str(ev).startswith('http'):
                extra_parts.append(f'{ek_label}: <a href="{escape(str(ev))}" target="_blank" class="text-indigo-600 underline">{escape(str(ev))}</a>')
            else:
                extra_parts.append(f'{ek_label}: {escape(str(ev))}')

        line = f'<span class="text-emerald-700">✓</span> <span class="font-medium">{escape(label)}</span>'
        if extra_parts:
            line += ' <span class="text-slate-400">— ' + ', '.join(extra_parts) + '</span>'
        items.append(line)

    if not items:
        return '<span class="text-slate-400 italic">Ninguna opción seleccionada</span>'
    return '<br>'.join(items)


def _render_lista(value, field_key=None):
    """Renderiza listas tipo ["opcion1", "opcion2"]."""
    data = _parse_json(value)
    if not isinstance(data, list):
        return escape(str(value)) if value else '—'
    items = [f'<span class="text-emerald-700">✓</span> {escape(_label(str(v), field_key))}' for v in data if v]
    return '<br>'.join(items) if items else '<span class="text-slate-400 italic">Vacío</span>'


def _render_tabla(value, max_rows=10):
    """Renderiza tablas tipo [{"campo": "valor"}, ...] como tabla HTML."""
    data = _parse_json(value)
    if isinstance(data, dict):
        items = data.get('filas', data.get('items', data.get('matriz', [])))
        if isinstance(items, dict):
            # Matriz clave-valor (e.g. satisfacción)
            rows = []
            for k, v in items.items():
                rows.append(f'<tr><td class="px-2 py-1 border-b border-slate-100 text-slate-700">{escape(str(k))}</td>'
                           f'<td class="px-2 py-1 border-b border-slate-100 font-medium">{escape(str(v))}</td></tr>')
            if rows:
                return f'<table class="w-full text-xs"><tbody>{"".join(rows[:max_rows])}</tbody></table>'
        elif isinstance(items, list):
            data = items
        else:
            return escape(str(value))

    if not isinstance(data, list) or not data:
        return escape(str(value)) if value else '—'

    # Obtener columnas de la primera fila. Los campos auxiliares '*_otro' se
    # fusionan en su columna padre ("Otro: <texto>") en lugar de mostrarse
    # como columna aparte.
    if isinstance(data[0], dict):
        cols = [c for c in data[0].keys() if not c.endswith('_otro')]
        header = ''.join(f'<th class="px-2 py-1 text-left bg-slate-100 text-slate-600 font-semibold border-b border-slate-200">{escape(c.replace("_", " ").title())}</th>' for c in cols)
        rows = []
        for row in data[:max_rows]:
            cells = ''
            for c in cols:
                val = str(row.get(c, '') or '')
                otro = str(row.get(c + '_otro', '') or '').strip()
                if val == 'Otro' and otro:
                    val = f'Otro: {otro}'
                if val.startswith('http'):
                    cell = f'<a href="{escape(val)}" target="_blank" class="text-indigo-600 underline break-all">{escape(val)}</a>'
                else:
                    cell = escape(val)
                cells += f'<td class="px-2 py-1 border-b border-slate-50 text-slate-700">{cell}</td>'
            rows.append(f'<tr>{cells}</tr>')
        extra = f'<tr><td colspan="{len(cols)}" class="px-2 py-1 text-center text-slate-400 italic">... y {len(data) - max_rows} filas más</td></tr>' if len(data) > max_rows else ''
        return f'<div class="overflow-x-auto"><table class="w-full text-xs border-collapse"><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}{extra}</tbody></table></div>'

    # Lista simple
    return _render_lista(data)


def _render_numerico_rubros(value, field_key, respuestas_dim):
    """Renderiza P21 mostrando rubros presupuestales con valores."""
    campos = [
        ('p21_hw_servidores', 'Hardware — Servidores'),
        ('p21_hw_computadoras', 'Hardware — Computadoras'),
        ('p21_hw_moviles', 'Hardware — Dispositivos móviles'),
        ('p21_hw_almacenamiento', 'Hardware — Almacenamiento'),
        ('p21_sw_estadistico', 'Software — Estadístico'),
        ('p21_sw_bd', 'Software — Bases de datos'),
        ('p21_sw_encuestas', 'Software — Encuestas'),
        ('p21_sw_visualizacion', 'Software — Visualización'),
        ('p21_sw_seguridad', 'Software — Seguridad'),
        ('p21_per_contratacion', 'Personal — Contratación'),
        ('p21_per_capacitacion', 'Personal — Capacitación'),
        ('p21_per_consultorias', 'Personal — Consultorías'),
        ('p21_per_mantenimiento', 'Personal — Mantenimiento'),
    ]
    items = []
    for campo, label in campos:
        val = respuestas_dim.get(campo, '')
        try:
            num = float(val) if val else 0
        except (TypeError, ValueError):
            num = 0
        icon = '✓' if num > 0 else '✗'
        color = 'text-emerald-700' if num > 0 else 'text-slate-300'
        items.append(f'<span class="{color}">{icon}</span> {escape(label)}: <span class="font-medium">{num:.1f}%</span>' if num > 0 else f'<span class="{color}">{icon}</span> {escape(label)}: <span class="text-slate-400">—</span>')
    return '<br>'.join(items)


@register.filter(name='render_iced_respuesta')
def render_iced_respuesta(preg_info, respuestas_dim=None):
    """
    Filtro principal: recibe un dict con {score, label, respuesta, field_key}
    y renderiza la respuesta de forma legible según el tipo de pregunta.
    """
    if not isinstance(preg_info, dict):
        return str(preg_info)

    resp = preg_info.get('respuesta', '')
    field_key = preg_info.get('field_key', '')

    if not resp or resp == '—':
        return mark_safe('<span class="text-slate-400 italic">Sin respuesta</span>')

    _build_field_maps()

    # Booleanos
    if field_key in ('p6_funciones_estadisticas', 'p7_procedimientos',
                     'p15_herramientas_visualizacion', 'p33_tiene_observatorio',
                     'p41_indaga_satisfaccion'):
        return mark_safe(_render_bool(resp))

    # Escalas ordinales (choices reales del form)
    if field_key in _ESCALAS:
        return mark_safe(_render_escala(resp, field_key))

    # Checkbox-tabla JSON
    if field_key in ('p8_herramientas_planificacion', 'p9_herramientas_mejoramiento',
                     'p11_instancias_coordinacion', 'p13_herramientas_procesamiento',
                     'p14_gestores_bd', 'p15_1_herramientas_tableros',
                     'p24_lineamientos', 'p24_nomenclaturas',
                     'p24_1_conceptos_estandarizados',
                     'p30_lineamientos_metodologicos',
                     'p36_uso_indicadores', 'p37_usuarios',
                     'p38_productos_difusion', 'p39_medios_difusion',
                     'p40_elementos_web'):
        return mark_safe(_render_checkbox_tabla(resp, field_key))

    # Listas checkbox simples
    if field_key in ('p25_mecanismos_necesidades',
                     'p26_estructura_analisis', 'p28_como_articulan',
                     'p28_1_frecuencia_reuniones', 'p28_2_modelos_estadisticos',
                     'p29_1_metodologia', 'p29_2_frecuencia',
                     'p29_3_medios_divulgacion', 'p29_4_acciones',
                     'p33_observatorios', 'p41_1_mecanismos'):
        parsed = _parse_json(resp)
        if isinstance(parsed, list):
            return mark_safe(_render_lista(parsed, field_key))
        if isinstance(parsed, dict):
            return mark_safe(_render_checkbox_tabla(parsed, field_key))
        return mark_safe(escape(str(resp)))

    # Tablas JSON
    if field_key in ('p7_estructura_mop', 'p10_actividades',
                     'p16_reportes_tableros', 'p19_rrhh_list',
                     'p23_operaciones_estadisticas', 'p30_tabla_alcaldia',
                     'p34_info_observatorios', 'p35_documentacion_observatorio',
                     'p41_2_matriz_satisfaccion'):
        return mark_safe(_render_tabla(resp))

    # Fallback genérico por estructura JSON (campos no clasificados arriba):
    # - dict con entradas {seleccion: ...}  -> checkbox-tabla
    # - lista de dicts                      -> tabla
    # - lista simple                        -> lista
    parsed = _parse_json(resp)
    if isinstance(parsed, dict):
        if any(isinstance(v, dict) and 'seleccion' in v for v in parsed.values()):
            return mark_safe(_render_checkbox_tabla(parsed, field_key))
        tabla = _render_tabla(parsed)
        if tabla and tabla != escape(str(resp)):
            return mark_safe(tabla)
    elif isinstance(parsed, list):
        if parsed and all(isinstance(v, dict) for v in parsed):
            return mark_safe(_render_tabla(parsed))
        return mark_safe(_render_lista(parsed, field_key))

    # Texto libre / fallback
    resp_str = str(resp)
    if len(resp_str) > 300:
        resp_str = resp_str[:300] + '…'
    return mark_safe(f'<span>{escape(resp_str)}</span>')
