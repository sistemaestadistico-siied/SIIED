"""
Motor de cálculo del ICED — Índice de Capacidad Estadística y de Datos.

Estructura jerárquica oficial:
  36 indicadores individuales → 9 subdimensiones → 4 dimensiones → 1 puntaje global

Fórmula:
  ICED = promedio simple de 4 dimensiones (25% cada una)

Dimensiones:
  1. Entorno Institucional (25%) → 1.1 Marco institucional, 1.2 Gestión del conocimiento
  2. Infraestructura (25%)      → 2.1 Herramientas, 2.2 Recursos
  3. Metodología Estadística (25%) → 3.1 OOEE, 3.2 Indicadores, 3.3 Analítica
  4. Accesibilidad y Uso (25%)  → 4.1 Disponibilidad, 4.2 Accesibilidad

Escala: 0-100% en cada nivel. Promedios simples dentro de cada nivel jerárquico.
Módulo A no puntúa (solo identificación).

Referencia: docs/ICED_resultados_referencia_2024_2025.csv
"""

import json as _json
import logging
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

D = Decimal


# =============================================================================
# CONSTANTES
# =============================================================================

PESOS_DIMENSIONES = {
    '1': D('0.25'),  # Entorno Institucional
    '2': D('0.25'),  # Infraestructura
    '3': D('0.25'),  # Metodología Estadística
    '4': D('0.25'),  # Accesibilidad y Uso
}

NIVELES_CAPACIDAD = [
    (90, 'muy_alto', 'Muy Alto'),
    (75, 'alto', 'Alto'),
    (60, 'medio', 'Medio'),
    (0, 'bajo', 'Bajo'),
]

# Estructura oficial del ICED: 36 indicadores agrupados en subdimensiones
ESTRUCTURA_ICED = {
    '1': {
        'nombre': 'Entorno Institucional',
        'peso': 25,
        'subdimensiones': {
            '1.1': {
                'nombre': 'Marco institucional',
                'indicadores': ['1.1.1', '1.1.2', '1.1.3', '1.1.4'],
            },
            '1.2': {
                'nombre': 'Gestión del conocimiento',
                'indicadores': ['1.2.1', '1.2.2', '1.2.3'],
            },
        },
    },
    '2': {
        'nombre': 'Infraestructura',
        'peso': 25,
        'subdimensiones': {
            '2.1': {
                'nombre': 'Uso de herramientas de gestión y procesamiento de datos',
                'indicadores': ['2.1.1', '2.1.2', '2.1.3'],
            },
            '2.2': {
                'nombre': 'Recursos humanos, tecnológicos y financieros',
                'indicadores': ['2.2.1', '2.2.2', '2.2.3', '2.2.4', '2.2.5', '2.2.6'],
            },
        },
    },
    '3': {
        'nombre': 'Metodología Estadística',
        'peso': 25,
        'subdimensiones': {
            '3.1': {
                'nombre': 'Operaciones estadísticas',
                'indicadores': ['3.1.1', '3.1.2', '3.1.3', '3.1.4', '3.1.5', '3.1.6'],
            },
            '3.2': {
                'nombre': 'Indicadores',
                'indicadores': ['3.2.1', '3.2.2', '3.2.3'],
            },
            '3.3': {
                'nombre': 'Analítica de datos',
                'indicadores': ['3.3.1', '3.3.2', '3.3.3'],
            },
        },
    },
    '4': {
        'nombre': 'Accesibilidad y uso',
        'peso': 25,
        'subdimensiones': {
            '4.1': {
                'nombre': 'Disponibilidad y uso',
                'indicadores': ['4.1.1', '4.1.2', '4.1.3', '4.1.4'],
            },
            '4.2': {
                'nombre': 'Accesibilidad',
                'indicadores': ['4.2.1', '4.2.2', '4.2.3', '4.2.4'],
            },
        },
    },
}

INDICADOR_LABELS = {
    '1.1.1': 'Funciones relacionadas',
    '1.1.2': 'Procedimientos relacionados',
    '1.1.3': 'Herramientas de planificación procesamiento',
    '1.1.4': 'Herramientas de planificación mejoramiento',
    '1.2.1': 'Fortalecimiento de competencias estadísticas',
    '1.2.2': 'Participación en instancias de coordinación interinstitucional',
    '1.2.3': 'Trazabilidad y continuidad en los procesos estadísticos',
    '2.1.1': 'Herramientas de procesamiento de datos',
    '2.1.2': 'Uso de gestores de bases de datos',
    '2.1.3': 'Uso de herramientas de visualización y/o monitoreo de datos',
    '2.2.1': 'Percepción suficiencia herramientas de procesamiento y visualización',
    '2.2.2': 'Existencia de grupo interno de trabajo estadístico',
    '2.2.3': 'Recurso humano disponible en cada etapa del proceso estadístico',
    '2.2.4': 'Percepción suficiencia del recurso humano',
    '2.2.5': 'Recursos destinados de Hardware, Software y personas',
    '2.2.6': 'Percepción suficiencia en la asignación de recursos financieros',
    '3.1.1': 'Existencia de documentos metodológicos de las OOEE',
    '3.1.2': 'Existencia de fichas metodológicas de las OOEE',
    '3.1.3': 'Existencia de manuales operativos, diccionario de datos y documentos de consistencia',
    '3.1.4': 'Implementación de acciones de fortalecimiento y mejoramiento de las OOEE',
    '3.1.5': 'Uso de lineamientos, normas y estándares para producción de estadísticas',
    '3.1.6': 'Mecanismos para detección de necesidades misionales o estadísticas',
    '3.2.1': 'Proceso de análisis de indicadores de resultado',
    '3.2.2': 'Articulación entre organismos para seguimiento de indicadores de producto',
    '3.2.3': 'Articulación entre organismos líderes de indicadores',
    '3.3.1': 'Implementación de lineamientos metodológicos',
    '3.3.2': 'Uso de modelos de analítica de datos',
    '3.3.3': 'Uso de herramientas de analítica avanzada disponibles en la entidad',
    '4.1.1': 'Uso de los indicadores del organismo',
    '4.1.2': 'Principales usuarios de la información',
    '4.1.3': 'Difusión de resultados estadísticos',
    '4.1.4': 'Publicación de las OOEE en el SICODE',
    '4.2.1': 'Uso de medios para la difusión de los resultados estadísticos',
    '4.2.2': 'Publicación de elementos en la página web',
    '4.2.3': 'Evaluación de la satisfacción de necesidades de información',
    '4.2.4': 'Uso de mecanismos para la medición de la satisfacción',
}

# Mapeo pregunta → (label legible, campo en el JSON de respuestas)
# Usado por la vista de validación para mostrar detalle por pregunta
PREGUNTA_LABELS = {
    'p6': ('P6. Funciones estadísticas establecidas', 'p6_funciones_estadisticas'),
    'p7': ('P7. Procedimientos documentados (MOP)', 'p7_procedimientos'),
    'p8': ('P8. Herramientas de planificación', 'p8_herramientas_planificacion'),
    'p9': ('P9. Herramientas de mejoramiento', 'p9_herramientas_mejoramiento'),
    'p10': ('P10. Participación en capacitación', 'p10_participacion'),
    'p11': ('P11. Instancias de coordinación', 'p11_instancias_coordinacion'),
    'p12': ('P12. Trazabilidad y continuidad', 'p12_trazabilidad'),
    'p13': ('P13. Herramientas de procesamiento', 'p13_herramientas_procesamiento'),
    'p14': ('P14. Gestores de bases de datos', 'p14_gestores_bd'),
    'p15': ('P15. Herramientas de visualización', 'p15_herramientas_visualizacion'),
    'p17': ('P17. Suficiencia herramientas TI', 'p17_suficiencia_herramientas'),
    'p18': ('P18. Estructura de RRHH', 'p18_estructura_rrhh'),
    'p19': ('P19. Detalle de RRHH', 'p19_rrhh_list'),
    'p20': ('P20. Suficiencia recurso humano', 'p20_suficiencia_rrhh'),
    'p21': ('P21. Asignación presupuestal', 'p21_presupuesto_hardware'),
    'p22': ('P22. Suficiencia financiera', 'p22_suficiencia_financiera'),
    'p23': ('P23. Operaciones estadísticas', 'p23_operaciones_estadisticas'),
    'p24': ('P24. Lineamientos aplicados', 'p24_lineamientos'),
    'p25': ('P25. Mecanismos de necesidades', 'p25_mecanismos_necesidades'),
    'p26': ('P26. Estructura de análisis', 'p26_estructura_analisis'),
    'p27': ('P27. Articulación con políticas', 'p27_articulacion'),
    'p28': ('P28. Cómo se articulan', 'p28_como_articulan'),
    'p29': ('P29. Rol en políticas públicas', 'p29_rol_politicas'),
    'p30': ('P30. Lineamientos metodológicos', 'p30_lineamientos_metodologicos'),
    'p31': ('P31. Tipo de analítica', 'p31_tipo_analitica'),
    'p32': ('P32. Analítica DATIC', 'p32_analitica_datic'),
    'p36': ('P36. Uso de indicadores', 'p36_uso_indicadores'),
    'p37': ('P37. Usuarios de la información', 'p37_usuarios'),
    'p38': ('P38. Productos de difusión', 'p38_productos_difusion'),
    'p39': ('P39. Medios de difusión', 'p39_medios_difusion'),
    'p40': ('P40. Elementos web', 'p40_elementos_web'),
    'p41': ('P41. ¿Indaga satisfacción?', 'p41_indaga_satisfaccion'),
}

# Mapeo indicador → (pregunta_id, field_key, modulo_json)
# Usado por la vista de validación para mostrar la respuesta real de cada pregunta
INDICADOR_PREGUNTA = {
    '1.1.1': ('p6', 'p6_funciones_estadisticas', 'b'),
    '1.1.2': ('p7', 'p7_procedimientos', 'b'),
    '1.1.3': ('p8', 'p8_herramientas_planificacion', 'b'),
    '1.1.4': ('p9', 'p9_herramientas_mejoramiento', 'b'),
    '1.2.1': ('p10', 'p10_participacion', 'b'),
    '1.2.2': ('p11', 'p11_instancias_coordinacion', 'b'),
    '1.2.3': ('p12', 'p12_trazabilidad', 'b'),
    '2.1.1': ('p13', 'p13_herramientas_procesamiento', 'c'),
    '2.1.2': ('p14', 'p14_gestores_bd', 'c'),
    '2.1.3': ('p15', 'p15_herramientas_visualizacion', 'c'),
    '2.2.1': ('p17', 'p17_suficiencia_herramientas', 'c'),
    '2.2.2': ('p18', 'p18_estructura_rrhh', 'c'),
    '2.2.3': ('p19', 'p19_rrhh_list', 'c'),
    '2.2.4': ('p20', 'p20_suficiencia_rrhh', 'c'),
    '2.2.5': ('p21', 'p21_hw_servidores', 'c'),
    '2.2.6': ('p22', 'p22_suficiencia_financiera', 'c'),
    '3.1.1': ('p23', 'p23_operaciones_estadisticas', 'd'),
    '3.1.2': ('p23', 'p23_operaciones_estadisticas', 'd'),
    '3.1.3': ('p23', 'p23_operaciones_estadisticas', 'd'),
    '3.1.4': ('p23', 'p23_operaciones_estadisticas', 'd'),
    '3.1.5': ('p24', 'p24_lineamientos', 'd'),
    '3.1.6': ('p25', 'p25_mecanismos_necesidades', 'd'),
    '3.2.1': ('p26', 'p26_estructura_analisis', 'd'),
    '3.2.2': ('p27', 'p27_articulacion', 'd'),
    '3.2.3': ('p29', 'p29_rol_politicas', 'd'),
    '3.3.1': ('p30', 'p30_lineamientos_metodologicos', 'd'),
    '3.3.2': ('p31', 'p31_tipo_analitica', 'd'),
    '3.3.3': ('p32', 'p32_analitica_datic', 'd'),
    '4.1.1': ('p36', 'p36_uso_indicadores', 'e'),
    '4.1.2': ('p37', 'p37_usuarios', 'e'),
    '4.1.3': ('p38', 'p38_productos_difusion', 'e'),
    '4.1.4': ('p23', 'p23_operaciones_estadisticas', 'd'),
    '4.2.1': ('p39', 'p39_medios_difusion', 'e'),
    '4.2.2': ('p40', 'p40_elementos_web', 'e'),
    '4.2.3': ('p41', 'p41_indaga_satisfaccion', 'e'),
    '4.2.4': ('p41', 'p41_1_mecanismos', 'e'),
}

# Encabezados CSV oficiales para exportación
CSV_HEADERS = [
    'AÑO', 'Organismo', 'Nivel organismo',
    'Índice de Capacidad Estadística Organismo',
    '1. Entorno Institucional', '2. Infraestructura',
    '3. Metodología Estadística', '4. Accesibilidad y uso',
    '1.1. Marco institucional', '1.2.Gestión del conocimiento',
    '2.1. Uso de herramientas de gestión y procesamiento de datos',
    '2.2. Recursos humanos, tecnológicos y financieros',
    '3.1. Operaciones estadísticas', '3.2. Indicadores',
    '3.3. Analítica de datos',
    '4.1. Disponibilidad y uso', '4.2. Accesibilidad',
] + [f'{k}. {v}' for k, v in INDICADOR_LABELS.items()]


def determinar_nivel(puntaje):
    """Nivel de capacidad dado un puntaje 0-100."""
    p = float(puntaje) if puntaje is not None else 0
    for umbral, codigo, nombre in NIVELES_CAPACIDAD:
        if p >= umbral:
            return (codigo, nombre)
    return ('bajo', 'Bajo')


def _normalizar_respuestas(respuestas):
    """
    Normaliza claves de respuestas eliminando prefijos de paso del wizard.
    Ej: 'entorno-p6_funciones_estadisticas' → 'p6_funciones_estadisticas'
    """
    if not respuestas:
        return {}
    norm = {}
    for key, value in respuestas.items():
        if '-' in key:
            parts = key.split('-', 1)
            field = parts[1] if len(parts) > 1 else key
            norm[field] = value
        else:
            norm[key] = value
    return norm


# =============================================================================
# FUNCIONES AUXILIARES — Escala 0-100 (porcentaje)
# =============================================================================

def _bool(valor):
    """Sí=100, No=0."""
    if valor in (True, 'si', 'Si', 'Sí', 'sí', '1', 1):
        return 100
    return 0


def _escala_ordinal(valor, n_opciones):
    """Radio ordinal: opción 1=mejor=100, última=0. Interpolación lineal."""
    try:
        v = int(valor)
    except (TypeError, ValueError):
        return 0
    if n_opciones <= 1:
        return 100 if v == 1 else 0
    paso = 100 / (n_opciones - 1)
    return max(0, round(100 - (v - 1) * paso))


def _escala_directa(valor, mapa):
    """Mapeo explícito valor→puntaje (0-100)."""
    if valor is None:
        return 0
    s = str(valor)
    return mapa.get(s, 0)


def _completitud_tabla(valor, max_filas=5):
    """Completitud de tabla JSON (0-100)."""
    if not valor:
        return 0
    if isinstance(valor, str):
        try:
            valor = _json.loads(valor)
        except (ValueError, TypeError):
            return 0
    if isinstance(valor, dict):
        items = valor.get('filas', valor.get('items', []))
    elif isinstance(valor, list):
        items = valor
    else:
        return 0
    llenas = sum(1 for f in items if _fila_ok(f))
    if max_filas <= 0:
        return 0
    return min(100, round(llenas / max_filas * 100))


def _fila_ok(fila):
    if not fila:
        return False
    if isinstance(fila, dict):
        return any(v for v in fila.values() if v and str(v).strip())
    return bool(fila)


def _promedio(valores):
    """Promedio de lista numérica, ignorando None. Retorna 0 si vacía."""
    filtrados = [v for v in valores if v is not None]
    if not filtrados:
        return 0
    return round(sum(filtrados) / len(filtrados))


def _promedio_exacto(valores):
    """Promedio sin redondeo intermedio (para cálculos finales)."""
    filtrados = [v for v in valores if v is not None]
    if not filtrados:
        return 0.0
    return sum(filtrados) / len(filtrados)


def _seleccionadas(valor, exclusiva=None):
    """Cuenta opciones válidas seleccionadas. Soporta lista y dict. Retorna (k, tiene_exclusiva)."""
    if not valor:
        return 0, False
    if isinstance(valor, str):
        try:
            valor = _json.loads(valor)
        except (ValueError, TypeError):
            return 0, False
    if isinstance(valor, (list, tuple)):
        tiene_ex = exclusiva in valor if exclusiva else False
        k = len([v for v in valor if v != exclusiva]) if exclusiva else len(valor)
        return k, tiene_ex
    if isinstance(valor, dict):
        k = 0
        tiene_ex = False
        for codigo, datos in valor.items():
            marcado = False
            if isinstance(datos, dict) and datos.get('seleccion'):
                marcado = True
            elif datos is True:
                marcado = True
            if marcado:
                if codigo == exclusiva:
                    tiene_ex = True
                else:
                    k += 1
        return k, tiene_ex
    return 0, False


def _proporcional_normalizada(valor, exclusiva=None):
    """Selección proporcional normalizada: 100% si hay al menos una válida marcada."""
    k, tiene_ex = _seleccionadas(valor, exclusiva)
    if tiene_ex or k == 0:
        return 0
    return 100


def _distribuida_fija(valor, peso_por_opcion, exclusiva=None):
    """Suma pesos fijos por cada opción válida seleccionada. Ej: 25% por opción."""
    if not valor:
        return 0
    if isinstance(valor, str):
        try:
            valor = _json.loads(valor)
        except (ValueError, TypeError):
            return 0
    total = 0
    if isinstance(valor, (list, tuple)):
        if exclusiva and exclusiva in valor:
            return 0
        for v in valor:
            if v != exclusiva:
                total += peso_por_opcion.get(v, 0)
        return min(100, total)
    if isinstance(valor, dict):
        for codigo, datos in valor.items():
            marcado = False
            if isinstance(datos, dict) and datos.get('seleccion'):
                marcado = True
            elif datos is True:
                marcado = True
            if marcado:
                if codigo == exclusiva:
                    return 0
                total += peso_por_opcion.get(codigo, 0)
        return min(100, total)
    return 0


def _asignacion_progresiva(valor, exclusiva=None):
    """P38/P39: asignación progresiva por número de productos válidos."""
    k, tiene_ex = _seleccionadas(valor, exclusiva)
    if tiene_ex or k == 0:
        return 0
    if k == 1:
        return round(100.0 / 3.0, 2)
    elif k == 2:
        return round(200.0 / 3.0, 2)
    return 100


def _escala_cantidad(valor, umbrales=None):
    """P40: escala por cantidad de elementos seleccionados."""
    if umbrales is None:
        umbrales = [(0, 0), (3, 25), (6, 50), (9, 75), (99999, 100)]
    k, _ = _seleccionadas(valor)
    for limite, puntaje in umbrales:
        if k <= limite:
            return puntaje
    return 100


def _grupos_proporcional(resp, grupos, total_por_grupo):
    """
    P21: múltiples grupos de campos numéricos. Cada grupo con k>0 aporta total_por_grupo.
    """
    puntaje = 0
    for campos in grupos:
        positivos = sum(1 for c in campos if _valor_numerico_positivo(resp.get(c)))
        if positivos > 0:
            puntaje += total_por_grupo
    return min(100, puntaje)


def _regla_p37(valor):
    """P37: 37.1 (organismos_misma) = 50% si marcada. Resto comparten 50%."""
    if not valor:
        return 0
    if isinstance(valor, str):
        try:
            valor = _json.loads(valor)
        except (ValueError, TypeError):
            return 0
    if isinstance(valor, (list, tuple)):
        if 'ninguno' in valor:
            return 0
        tiene_37_1 = 'organismos_misma' in valor
        k2 = len([v for v in valor if v not in ('organismos_misma', 'ninguno')])
        total = 0
        if tiene_37_1:
            total += 50
        if k2 > 0:
            total += 50
        return total
    if isinstance(valor, dict):
        seleccionados = []
        tiene_ex = False
        for codigo, datos in valor.items():
            marcado = False
            if isinstance(datos, dict) and datos.get('seleccion'):
                marcado = True
            elif datos is True:
                marcado = True
            if marcado:
                if codigo == 'ninguno':
                    tiene_ex = True
                else:
                    seleccionados.append(codigo)
        if tiene_ex:
            return 0
        tiene_37_1 = 'organismos_misma' in seleccionados
        k2 = len([s for s in seleccionados if s != 'organismos_misma'])
        total = 0
        if tiene_37_1:
            total += 50
        if k2 > 0:
            total += 50
        return total
    return 0


def _p38_tiene_ninguna(resp_e):
    """Verifica si P38 tiene seleccionada la opción 'ninguna' (no difunde)."""
    val = resp_e.get('p38_productos_difusion')
    if not val:
        return False
    if isinstance(val, str):
        try:
            val = _json.loads(val)
        except (ValueError, TypeError):
            return False
    if isinstance(val, dict):
        for codigo, datos in val.items():
            marcado = False
            if isinstance(datos, dict) and datos.get('seleccion'):
                marcado = True
            elif datos is True:
                marcado = True
            if marcado and codigo == 'ninguna':
                return True
    return False


# =============================================================================
# CÁLCULO DE LOS 36 INDICADORES INDIVIDUALES
# =============================================================================

def _calcular_indicadores(resp_b, resp_c, resp_d, resp_e):
    """
    Calcula los 36 indicadores individuales del ICED (escala 0-100).
    
    Retorna dict: {'1.1.1': valor, '1.1.2': valor, ..., '4.2.4': valor}
    """
    ind = {}

    # =========================================================================
    # DIMENSIÓN 1: Entorno Institucional (preguntas P6-P12)
    # =========================================================================

    ind['1.1.1'] = _bool(resp_b.get('p6_funciones_estadisticas'))
    ind['1.1.2'] = _bool(resp_b.get('p7_procedimientos'))

    # P8: distribuida fija 25% por opción
    peso_p8 = {o: 25 for o in ['planes_trabajo', 'planes_accion', 'programas', 'proyectos']}
    ind['1.1.3'] = _distribuida_fija(resp_b.get('p8_herramientas_planificacion'), peso_p8, 'no_se_incluyen')

    # P9: distribuida fija 25% por opción
    peso_p9 = {o: 25 for o in ['planes_trabajo', 'planes_accion', 'programas', 'proyectos']}
    ind['1.1.4'] = _distribuida_fija(resp_b.get('p9_herramientas_mejoramiento'), peso_p9, 'no_se_incluyen')

    ind['1.2.1'] = _escala_ordinal(resp_b.get('p10_participacion'), 4)

    # P11: distribuida fija 25% por opción
    peso_p11 = {o: 25 for o in ['comisiones', 'comites', 'mesas', 'observatorios', 'otros']}
    ind['1.2.2'] = _distribuida_fija(resp_b.get('p11_instancias_coordinacion'), peso_p11, 'no_participa')

    # P12 tiene solo 3 opciones (1=formal, 2=informal, 3=no existen)
    ind['1.2.3'] = _escala_ordinal(resp_b.get('p12_trazabilidad'), 3)

    # =========================================================================
    # DIMENSIÓN 2: Infraestructura (preguntas P13-P22)
    # =========================================================================

    # P13, P14: proporcional normalizada
    ind['2.1.1'] = _proporcional_normalizada(resp_c.get('p13_herramientas_procesamiento'), 'ninguna')
    ind['2.1.2'] = _proporcional_normalizada(resp_c.get('p14_gestores_bd'), 'ninguno')

    # P15 + P15.1 + P16
    p15 = _bool(resp_c.get('p15_herramientas_visualizacion'))
    if p15 > 0 and resp_c.get('p15_herramientas_visualizacion') in ('si', 'Si', 'Sí', True, '1'):
        p15_1 = _proporcional_normalizada(resp_c.get('p15_1_herramientas_tableros'), 'ninguna')
        p16 = _completitud_tabla(resp_c.get('p16_reportes_tableros'), 3)
        ind['2.1.3'] = _promedio([p15, p15_1, p16])
    else:
        ind['2.1.3'] = 0

    ind['2.2.1'] = _escala_ordinal(resp_c.get('p17_suficiencia_herramientas'), 5)
    ind['2.2.2'] = _escala_directa(resp_c.get('p18_estructura_rrhh'),
                                    {'1': 100, '2': 100, '3': 100, '4': 0})

    # P19
    p19_raw = resp_c.get('p19_rrhh_list', '')
    try:
        personas = _json.loads(p19_raw) if isinstance(p19_raw, str) and p19_raw else (p19_raw or [])
    except (ValueError, TypeError):
        personas = []
    if isinstance(personas, list) and personas:
        n_personas = len([p for p in personas if isinstance(p, dict) and p.get('nombre_completo', '').strip()])
        etapas_set = set()
        for p in personas:
            if isinstance(p, dict):
                for e in (p.get('etapas_proceso') or []):
                    etapas_set.add(e)
        cobertura = min(100, round(len(etapas_set) / 8 * 100))
        cantidad = min(100, round(n_personas / 5 * 100))
        ind['2.2.3'] = _promedio([cantidad, cobertura])
    else:
        ind['2.2.3'] = 0

    ind['2.2.4'] = _escala_ordinal(resp_c.get('p20_suficiencia_rrhh'), 5)

    # P21: 3 grupos × 33%
    G1 = ['p21_hw_servidores', 'p21_hw_computadoras', 'p21_hw_moviles', 'p21_hw_almacenamiento']
    G2 = ['p21_sw_estadistico', 'p21_sw_bd', 'p21_sw_encuestas', 'p21_sw_visualizacion', 'p21_sw_seguridad']
    G3 = ['p21_per_contratacion', 'p21_per_capacitacion', 'p21_per_consultorias', 'p21_per_mantenimiento']
    # 3 grupos × 100/3 para que el máximo sea 100 (33×3=99 dejaba tope en 99)
    ind['2.2.5'] = _grupos_proporcional(resp_c, [G1, G2, G3], 100.0 / 3.0)

    ind['2.2.6'] = _escala_ordinal(resp_c.get('p22_suficiencia_financiera'), 5)

    # =========================================================================
    # DIMENSIÓN 3: Metodología Estadística (preguntas P23-P35)
    # =========================================================================

    ooee = _parse_ooee(resp_d.get('p23_operaciones_estadisticas'))
    # Las OOEE marcadas vigente='no' no puntúan: el widget deshabilita el
    # resto de columnas para esas filas, por lo que contarlas en el
    # denominador penalizaría operaciones ya descontinuadas.
    ooee = [oe for oe in ooee if not _oe_es_no(oe, 'vigente')]
    n_ooee = len(ooee) if ooee else 0

    if n_ooee > 0:
        ind['3.1.1'] = round(sum(1 for oe in ooee if _oe_tiene(oe, 'doc_metodologico')) / n_ooee * 100)
        ind['3.1.2'] = round(sum(1 for oe in ooee if _oe_tiene(oe, 'ficha_metodologica')) / n_ooee * 100)
        docs_por_oe = []
        for oe in ooee:
            tiene = sum([
                _oe_tiene(oe, 'manual_operativo'),
                _oe_tiene(oe, 'diccionario_datos'),
                _oe_tiene(oe, 'doc_consistencia'),
            ])
            docs_por_oe.append(tiene / 3 * 100)
        ind['3.1.3'] = round(sum(docs_por_oe) / n_ooee)
        ind['3.1.4'] = round(sum(1 for oe in ooee if _oe_tiene_texto(oe, 'acciones_fortalecimiento')) / n_ooee * 100)
    else:
        ind['3.1.1'] = 0
        ind['3.1.2'] = 0
        ind['3.1.3'] = 0
        ind['3.1.4'] = 0

    # P24-P27, P30: proporcional normalizada
    ind['3.1.5'] = _proporcional_normalizada(resp_d.get('p24_lineamientos'), 'ninguna')
    ind['3.1.6'] = _proporcional_normalizada(resp_d.get('p25_mecanismos_necesidades'), 'ninguno')
    ind['3.2.1'] = _proporcional_normalizada(resp_d.get('p26_estructura_analisis'), 'no_realiza')

    # P27 + P28
    p27_val = resp_d.get('p27_articulacion')
    p27 = _escala_directa(str(p27_val), {'1': 100, '2': 100, '3': 100, '4': 0})

    if str(p27_val) == '3':
        # Regla especial documento: si 27.3 marcada → 28.10 = 100%
        p28 = 100
    else:
        p28_sel = resp_d.get('p28_como_articulan')
        _, es_no_necesario = _seleccionadas(p28_sel, 'no_es_necesario')
        if es_no_necesario:
            # 28.10 "No es necesario...": articulación no requerida → 100%
            p28 = 100
        else:
            p28 = _proporcional_normalizada(p28_sel, 'no_articulan')

    ind['3.2.2'] = _promedio([p27, p28])

    # P29 + subpreguntas
    p29 = _escala_directa(resp_d.get('p29_rol_politicas'),
                          {'1': 100, '2': 67, '4': 33, '3': 0})
    if str(resp_d.get('p29_rol_politicas')) == '1':
        sub_scores = [p29]
        if resp_d.get('p29_1_metodologia'):
            sub_scores.append(_proporcional_normalizada(resp_d.get('p29_1_metodologia'), None))
        if resp_d.get('p29_3_medios_divulgacion'):
            sub_scores.append(_proporcional_normalizada(resp_d.get('p29_3_medios_divulgacion'), None))
        if resp_d.get('p29_4_acciones'):
            sub_scores.append(_proporcional_normalizada(resp_d.get('p29_4_acciones'), 'ninguna'))
        ind['3.2.3'] = _promedio(sub_scores)
    else:
        ind['3.2.3'] = p29

    ind['3.3.1'] = _proporcional_normalizada(resp_d.get('p30_lineamientos_metodologicos'), 'ninguno')

    # P31: mapeo radio a grupos documento (1,2 → 50%; 3,4,5 → 100%)
    ind['3.3.2'] = _escala_directa(resp_d.get('p31_tipo_analitica'),
                                    {'1': 50, '2': 50, '3': 100, '4': 100, '5': 100})
    ind['3.3.3'] = _escala_directa(resp_d.get('p32_analitica_datic'),
                                    {'5': 100, '4': 100, '3': 100, '2': 50, '1': 25, '6': 0})

    # =========================================================================
    # DIMENSIÓN 4: Accesibilidad y Uso (preguntas P36-P42)
    # =========================================================================

    # P36: distribuida fija 25% por opción
    peso_p36 = {o: 25 for o in ['diagnostico_pdd', 'rendicion_cuentas', 'pot', 'evaluar_pp']}
    ind['4.1.1'] = _distribuida_fija(resp_e.get('p36_uso_indicadores'), peso_p36, None)

    # P37: regla especial
    ind['4.1.2'] = _regla_p37(resp_e.get('p37_usuarios'))

    # P38: asignación progresiva
    ind['4.1.3'] = _asignacion_progresiva(resp_e.get('p38_productos_difusion'), 'ninguna')

    # 4.1.4: cross-dimensional from P23
    if n_ooee > 0:
        ind['4.1.4'] = round(sum(1 for oe in ooee if _oe_tiene(oe, 'publicado_sicode')) / n_ooee * 100)
    else:
        ind['4.1.4'] = 0

    # P39, P40, P41: condicionales por P38.7 (ninguna)
    p38_ninguna = _p38_tiene_ninguna(resp_e)

    if p38_ninguna:
        ind['4.2.1'] = 0
        ind['4.2.2'] = 0
        ind['4.2.3'] = 0
        ind['4.2.4'] = 0
    else:
        # P39: progresiva sobre 3 opciones
        ind['4.2.1'] = _asignacion_progresiva(resp_e.get('p39_medios_difusion'), None)

        # P40: escala por cantidad (14 opciones posibles)
        ind['4.2.2'] = _escala_cantidad(resp_e.get('p40_elementos_web'))

        # P41
        p41 = _bool(resp_e.get('p41_indaga_satisfaccion'))
        ind['4.2.3'] = p41

        # 4.2.4: si p41='no' (41.2 marcada) → 0.
        # Si p41='si' y k>0 mecanismos → 100 (cada uno 100/k, suma = 100).
        # Si no hay mecanismos → 0.
        if not p41:
            ind['4.2.4'] = 0
        else:
            k41, _ = _seleccionadas(resp_e.get('p41_1_mecanismos'))
            ind['4.2.4'] = 100 if k41 > 0 else 0

    return ind


def _valor_numerico_positivo(val):
    """Retorna True si val es numérico y > 0."""
    try:
        return float(val or 0) > 0
    except (TypeError, ValueError):
        return False


def _parse_ooee(valor):
    """Parsea la tabla de OOEE (P23) desde JSON."""
    if not valor:
        return []
    if isinstance(valor, str):
        try:
            valor = _json.loads(valor)
        except (ValueError, TypeError):
            return []
    if isinstance(valor, dict):
        return valor.get('filas', valor.get('items', []))
    if isinstance(valor, list):
        return [oe for oe in valor if isinstance(oe, dict) and oe.get('nombre_oe', '').strip()]
    return []


def _oe_tiene(oe, campo):
    """Verifica si una OE tiene un campo booleano en 'si'."""
    v = oe.get(campo, '')
    return v in ('si', 'Si', 'Sí', True, '1', 1)


def _oe_es_no(oe, campo):
    """Verifica si una OE tiene un campo booleano marcado explícitamente en 'no'."""
    v = oe.get(campo, '')
    return v in ('no', 'No', 'NO', False, '0', 0)


def _oe_tiene_texto(oe, campo):
    """Verifica si una OE tiene un campo de texto con contenido."""
    v = oe.get(campo, '')
    return bool(v and str(v).strip())


# =============================================================================
# AGREGACIÓN JERÁRQUICA
# =============================================================================

def _agregar_subdimensiones(indicadores):
    """
    Agrega indicadores en subdimensiones según la ESTRUCTURA_ICED.
    Retorna dict: {'1.1': valor, '1.2': valor, ..., '4.2': valor}
    """
    subdims = {}
    for dim_key, dim_info in ESTRUCTURA_ICED.items():
        for sub_key, sub_info in dim_info['subdimensiones'].items():
            valores = [indicadores.get(ind_key, 0) for ind_key in sub_info['indicadores']]
            subdims[sub_key] = _promedio(valores)
    return subdims


def _agregar_dimensiones(subdimensiones):
    """
    Agrega subdimensiones en dimensiones (promedio simple de sus subdimensiones).
    Retorna dict: {'1': valor, '2': valor, '3': valor, '4': valor}
    """
    dims = {}
    for dim_key, dim_info in ESTRUCTURA_ICED.items():
        sub_keys = list(dim_info['subdimensiones'].keys())
        valores = [subdimensiones.get(sk, 0) for sk in sub_keys]
        dims[dim_key] = _promedio(valores)
    return dims


def _calcular_global(dimensiones):
    """Calcula el puntaje global ponderado."""
    total = 0.0
    for dim_key, peso in PESOS_DIMENSIONES.items():
        total += dimensiones.get(dim_key, 0) * float(peso)
    return round(total)


# =============================================================================
# FUNCIÓN PRINCIPAL DE CÁLCULO
# =============================================================================

def calcular_iced(formulario):
    """
    Calcula el ICED completo para un ICEDFormulario.

    Retorna dict con la jerarquía completa:
    - 36 indicadores individuales (0-100%)
    - 9 subdimensiones (promedio de indicadores)
    - 4 dimensiones (promedio de subdimensiones)
    - 1 puntaje global (promedio simple: D1×25% + D2×25% + D3×25% + D4×25%)
    - nivel de capacidad
    """
    resp_b = _normalizar_respuestas(formulario.respuestas_b)
    resp_c = _normalizar_respuestas(formulario.respuestas_c)
    resp_d = _normalizar_respuestas(formulario.respuestas_d)
    resp_e = _normalizar_respuestas(formulario.respuestas_e)

    # Paso 1: Calcular los 36 indicadores individuales
    indicadores = _calcular_indicadores(resp_b, resp_c, resp_d, resp_e)

    # Paso 2: Agregar en subdimensiones
    subdimensiones = _agregar_subdimensiones(indicadores)

    # Paso 3: Agregar en dimensiones
    dimensiones = _agregar_dimensiones(subdimensiones)

    # Paso 4: Calcular global ponderado
    puntaje_global = _calcular_global(dimensiones)

    # Paso 5: Determinar nivel
    nivel = determinar_nivel(puntaje_global)

    return {
        'puntaje_global': puntaje_global,
        'nivel_codigo': nivel[0],
        'nivel_nombre': nivel[1],
        'dimensiones': dimensiones,
        'subdimensiones': subdimensiones,
        'indicadores': indicadores,
        # Compatibilidad con campos del modelo
        'puntaje_b': dimensiones.get('1', 0),
        'puntaje_c': dimensiones.get('2', 0),
        'puntaje_d': dimensiones.get('3', 0),
        'puntaje_e': dimensiones.get('4', 0),
        # Detalle para almacenamiento
        'detalle': {
            dim_key: {
                'nombre': dim_info['nombre'],
                'puntaje': dimensiones.get(dim_key, 0),
                'peso': dim_info['peso'],
                'nivel': determinar_nivel(dimensiones.get(dim_key, 0)),
                'subdimensiones': {
                    sk: {'nombre': si['nombre'], 'puntaje': subdimensiones.get(sk, 0)}
                    for sk, si in dim_info['subdimensiones'].items()
                },
            }
            for dim_key, dim_info in ESTRUCTURA_ICED.items()
        },
    }


def aplicar_puntajes(formulario):
    """Calcula y persiste los puntajes en el ICEDFormulario.
    
    Nota: el modelo almacena puntajes en escala 0-1 (DecimalField max_digits=5, decimal_places=4),
    pero calcular_iced() retorna en escala 0-100. Se convierte aquí.
    """
    resultado = calcular_iced(formulario)

    # Convertir de 0-100 a 0-1 para el modelo
    formulario.puntaje_b = D(str(resultado['puntaje_b'])) / D('100')
    formulario.puntaje_c = D(str(resultado['puntaje_c'])) / D('100')
    formulario.puntaje_d = D(str(resultado['puntaje_d'])) / D('100')
    formulario.puntaje_e = D(str(resultado['puntaje_e'])) / D('100')
    formulario.puntaje_global = D(str(resultado['puntaje_global'])) / D('100')
    formulario.puntajes_detalle = {
        'indicadores': resultado['indicadores'],
        'subdimensiones': resultado['subdimensiones'],
        'dimensiones': resultado['dimensiones'],
        'detalle': resultado['detalle'],
    }
    formulario.save(update_fields=[
        'puntaje_b', 'puntaje_c', 'puntaje_d', 'puntaje_e',
        'puntaje_global', 'puntajes_detalle',
    ])

    return resultado


# =============================================================================
# EXPORTACIÓN CSV
# =============================================================================

def resultado_a_fila_csv(formulario, resultado=None):
    """
    Convierte un resultado ICED a una fila CSV con el formato oficial.

    Args:
        formulario: instancia de ICEDFormulario
        resultado: dict de calcular_iced() (se calcula si no se proporciona)

    Returns:
        list con los valores de la fila en el orden de CSV_HEADERS
    """
    if resultado is None:
        resultado = calcular_iced(formulario)

    ind = resultado['indicadores']
    sub = resultado['subdimensiones']
    dim = resultado['dimensiones']
    glob = resultado['puntaje_global']

    # Obtener nivel del organismo (si el modelo tiene ese campo)
    organismo = formulario.organismo
    nivel_org = getattr(organismo, 'nivel', getattr(organismo, 'descripcion', ''))

    fila = [
        formulario.periodo,
        organismo.nombre,
        nivel_org or '',
        f"{glob}%",
        # 4 dimensiones
        f"{dim.get('1', 0)}%",
        f"{dim.get('2', 0)}%",
        f"{dim.get('3', 0)}%",
        f"{dim.get('4', 0)}%",
        # 9 subdimensiones
        f"{sub.get('1.1', 0)}%",
        f"{sub.get('1.2', 0)}%",
        f"{sub.get('2.1', 0)}%",
        f"{sub.get('2.2', 0)}%",
        f"{sub.get('3.1', 0)}%",
        f"{sub.get('3.2', 0)}%",
        f"{sub.get('3.3', 0)}%",
        f"{sub.get('4.1', 0)}%",
        f"{sub.get('4.2', 0)}%",
        # 36 indicadores individuales
    ]

    for ind_key in INDICADOR_LABELS.keys():
        fila.append(f"{ind.get(ind_key, 0)}%")

    return fila


def exportar_csv_periodo(formularios, periodo=None):
    """
    Genera el contenido CSV completo para un conjunto de formularios.

    Args:
        formularios: queryset o lista de ICEDFormulario
        periodo: filtro opcional de periodo

    Returns:
        str con contenido CSV completo (header + filas)
    """
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADERS)

    errores = []
    for formulario in formularios:
        try:
            resultado = calcular_iced(formulario)
            fila = resultado_a_fila_csv(formulario, resultado)
            writer.writerow(fila)
        except Exception as e:
            # IC-04: registrar el error en vez de omitir el formulario en silencio
            logger.error(
                'ICED export CSV: error calculando formulario %s (organismo=%s, periodo=%s): %s',
                formulario.pk, formulario.organismo_id, formulario.periodo, e,
                exc_info=True,
            )
            errores.append({'formulario_id': formulario.pk, 'error': str(e)})

    if errores:
        logger.warning(
            'ICED export CSV: %d formulario(s) omitidos por errores de cálculo: %s',
            len(errores), errores,
        )

    return output.getvalue()
