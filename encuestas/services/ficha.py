"""
Ficha metodológica y metadata mínima (NTC PE 1000 §4.4.2: la
documentación debe estar disponible ANTES de iniciar la recolección).

`MINIMA` es el subconjunto de campos de la ficha exigible para poder
publicar un formulario: sin ellos la operación no está documentada.
"""
from django.core.exceptions import ValidationError

from ..models import FichaMetodologica

# (campo, etiqueta amigable) — mínimo exigible para publicar
MINIMA = [
    ('tipo_operacion', 'Tipo de operación estadística'),
    ('entidad_responsable', 'Entidad responsable'),
    ('objetivo_general', 'Objetivo general'),
    ('unidad_observacion', 'Unidad de observación'),
    ('poblacion_objetivo', 'Población objetivo'),
    ('cobertura_geografica', 'Cobertura geográfica'),
    ('periodo_referencia', 'Período de referencia'),
    ('periodo_recoleccion', 'Período de recolección'),
    ('metodos_recoleccion', 'Método de recolección'),
]

# Recomendada (no bloqueante, se muestra como pendiente)
RECOMENDADA = [
    ('sigla', 'Sigla de la operación'),
    ('responsable_operacion', 'Responsable de la operación'),
    ('objetivos_especificos', 'Objetivos específicos'),
    ('variables_principales', 'Variables principales'),
    ('estandares', 'Estándares estadísticos'),
    ('universo', 'Universo de estudio'),
    ('fuentes_datos', 'Fuentes de datos'),
    ('periodicidad', 'Periodicidad'),
    ('temas_subtemas', 'Temas y subtemas'),
    ('palabras_clave', 'Palabras clave'),
]

# Campos de muestra: solo exigibles si el tipo de operación es muestreo
MUESTRA = [
    ('tamano_muestra', 'Tamaño de muestra'),
    ('diseno_muestral', 'Diseño muestral'),
    ('unidad_muestreo', 'Unidad de muestreo'),
]
TIPOS_MUESTREO = ('muestreo_prob', 'muestreo_no_prob')


def ficha_de(formulario):
    """Ficha del formulario, creándola vacía si no existe."""
    ficha, _ = FichaMetodologica.objects.get_or_create(
        formulario=formulario)
    return ficha


def faltantes_minimos(ficha):
    """Campos mínimos pendientes de la ficha (lista de etiquetas)."""
    faltan = [etq for campo, etq in MINIMA
              if not getattr(ficha, campo)]
    if ficha.tipo_operacion in TIPOS_MUESTREO:
        faltan += [etq for campo, etq in MUESTRA
                   if not getattr(ficha, campo)]
    return faltan


def pendientes_recomendados(ficha):
    return [etq for campo, etq in RECOMENDADA
            if not getattr(ficha, campo)]


def completitud_minima(ficha):
    """Porcentaje 0-100 de la metadata mínima diligenciada."""
    campos = MINIMA + (MUESTRA if ficha.tipo_operacion in TIPOS_MUESTREO
                       else [])
    total = len(campos)
    if not total:
        return 100
    llenos = sum(1 for c, _ in campos if getattr(ficha, c))
    return round(llenos * 100 / total)


def validar_para_publicar(formulario):
    """Bloquea publicar sin la metadata mínima (NTC §4.4.2)."""
    ficha = getattr(formulario, 'ficha', None)
    if ficha is None:
        raise ValidationError(
            'Antes de publicar diligencie la ficha metodológica '
            '(documentación previa a la recolección).')
    faltan = faltantes_minimos(ficha)
    if faltan:
        raise ValidationError(
            'Ficha metodológica incompleta. Faltan: ' +
            ', '.join(faltan) + '.')


# Campos editables desde la pantalla de ficha, agrupados por bloque
BLOQUES = [
    ('Identificación', [
        ('sigla', 'texto'), ('entidad_responsable', 'texto'),
        ('tipo_operacion', 'select'), ('responsable_operacion', 'texto'),
    ]),
    ('Objetivos y alcance', [
        ('antecedentes', 'textarea'), ('objetivo_general', 'textarea'),
        ('objetivos_especificos', 'textarea'),
        ('alcance_tematico', 'textarea'),
        ('variables_principales', 'textarea'),
        ('indicadores', 'textarea'), ('parametros', 'textarea'),
        ('estandares', 'textarea'), ('temas_subtemas', 'texto'),
        ('palabras_clave', 'texto'),
    ]),
    ('Diseño', [
        ('universo', 'textarea'), ('poblacion_objetivo', 'textarea'),
        ('unidad_observacion', 'texto'), ('unidad_muestreo', 'texto'),
        ('unidad_analisis', 'texto'), ('marco_tipo', 'select'),
        ('marco_descripcion', 'textarea'), ('fuentes_datos', 'textarea'),
    ]),
    ('Muestra (si aplica)', [
        ('tamano_muestra', 'textarea'), ('diseno_muestral', 'textarea'),
        ('precision', 'textarea'), ('mantenimiento_muestra', 'textarea'),
        ('informacion_auxiliar', 'textarea'),
    ]),
    ('Recolección y difusión', [
        ('cobertura_geografica', 'textarea'),
        ('periodo_referencia', 'texto'), ('periodo_recoleccion', 'texto'),
        ('periodicidad', 'select'), ('metodos_recoleccion', 'multi'),
        ('desagregacion', 'textarea'), ('difusion', 'textarea'),
    ]),
]


ETIQUETAS = {
    'sigla': 'Sigla de la operación',
    'entidad_responsable': 'Entidad responsable',
    'tipo_operacion': 'Tipo de operación estadística',
    'responsable_operacion': 'Responsable de la operación',
    'antecedentes': 'Antecedentes',
    'objetivo_general': 'Objetivo general',
    'objetivos_especificos': 'Objetivos específicos',
    'alcance_tematico': 'Alcance temático',
    'variables_principales': 'Variables principales',
    'indicadores': 'Indicadores',
    'parametros': 'Parámetros',
    'estandares': 'Estándares estadísticos empleados',
    'temas_subtemas': 'Temas y subtemas',
    'palabras_clave': 'Palabras clave',
    'universo': 'Universo de estudio',
    'poblacion_objetivo': 'Población objetivo',
    'unidad_observacion': 'Unidad de observación',
    'unidad_muestreo': 'Unidad de muestreo',
    'unidad_analisis': 'Unidad de análisis',
    'marco_tipo': 'Tipo de marco estadístico',
    'marco_descripcion': 'Descripción del marco',
    'fuentes_datos': 'Fuentes de datos',
    'tamano_muestra': 'Tamaño de muestra',
    'diseno_muestral': 'Diseño muestral',
    'precision': 'Precisión de los resultados',
    'mantenimiento_muestra': 'Mantenimiento y rotación de la muestra',
    'informacion_auxiliar': 'Información auxiliar',
    'cobertura_geografica': 'Cobertura geográfica',
    'periodo_referencia': 'Período de referencia',
    'periodo_recoleccion': 'Período de recolección',
    'periodicidad': 'Periodicidad',
    'metodos_recoleccion': 'Métodos de recolección',
    'desagregacion': 'Desagregación geográfica y temática',
    'difusion': 'Difusión y productos estadísticos',
}


def actualizar_ficha(ficha, post):
    """Aplica los campos del POST a la ficha. Devuelve la ficha."""
    for _, campos in BLOQUES:
        for campo, tipo in campos:
            if tipo == 'multi':
                ficha.metodos_recoleccion = [
                    m for m in post.getlist(f'f_{campo}')
                    if m in dict(FichaMetodologica.METODOS_CHOICES)]
            elif tipo == 'select':
                setattr(ficha, campo, post.get(f'f_{campo}', '').strip())
            else:
                setattr(ficha, campo,
                        post.get(f'f_{campo}', '').strip())
    ficha.save()
    return ficha
