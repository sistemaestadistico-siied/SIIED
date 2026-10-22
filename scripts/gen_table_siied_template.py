#!/usr/bin/env python3
"""Genera el form template table-SIIED para conjuntos de datos
(schema 'table' del OM Editor) en el directorio de plantillas del
editor. Las secciones replican la ficha del modelo ConjuntoDatos y
table_columns expone la ficha técnica de VariableConjuntoDatos como
grilla (type 'array', igual que el template core).

Reutiliza las especificaciones de campos del template core
(table_form_template.json / table_template_ihsn.json) para que tipo,
props, display_type y prop_key coincidan con lo que el renderer
espera; los campos sin spec core se emiten como string/text.

Uso:
    python3 scripts/gen_table_siied_template.py \
        --editor-path /home/amiranda/Descargas/OPENMETADATA/editor
"""

import argparse
import json
from pathlib import Path

# (key, titulo, ayuda, requerido) — sección → campos
SECTIONS = [
    ('1. Identificación', [
        ('table_description.title_statement.title',
         'Nombre del Conjunto de Datos', '', True),
        ('table_description.title_statement.idno',
         'Identificador (IDNo)',
         'Identificador único del conjunto (ej. agencia:código)', False),
        ('table_description.version', 'Versión',
         'Versión del conjunto de datos', False),
        ('table_description.title_statement.alternate_title',
         'Cita bibliográfica / DOI', 'Cita recomendada o DOI', False),
        ('additional.idioma', 'Idioma', 'Código ISO 639', False),
        ('tags', 'Palabras clave', 'Palabras clave del conjunto', False),
    ]),
    ('2. Producción y Difusión', [
        ('table_description.authoring_entity', 'Organismo productor',
         'Entidad productora del conjunto', False),
        ('additional.financiamiento', 'Financiamiento',
         'Agencia o fuente de financiamiento', False),
        ('table_description.publisher', 'Entidad distribuidora',
         'Entidad que distribuye el conjunto', False),
        ('table_description.contacts', 'Contacto',
         'Persona o área de contacto', False),
        ('additional.operacion_estadistica', 'Operación estadística',
         'OOEE que origina el conjunto', False),
    ]),
    ('3. Cobertura', [
        ('table_description.universe', 'Universo',
         'Universo o población cubierta por los datos', False),
        ('table_description.unit_observation', 'Unidad de análisis',
         'Unidad de análisis (personas, hogares…)', False),
        ('additional.cobertura_geografica', 'Cobertura geográfica',
         'Extensión territorial del conjunto', False),
        ('additional.cobertura_temporal', 'Cobertura temporal',
         'Período de referencia (ej. 2015-2024)', False),
        ('table_description.time_periods', 'Períodos de trabajo de campo',
         'Inicio y fin de recolección', False),
    ]),
    ('4. Metodología', [
        ('additional.tipo_estudio', 'Tipo de estudio',
         'Encuesta, censo, registro administrativo, agregado', False),
        ('additional.metodo_muestreo', 'Método de muestreo',
         'Método de muestreo aplicado', False),
        ('additional.modo_coleccion', 'Modo de recolección',
         'Entrevista presencial, web, extracción administrativa…',
         False),
        ('additional.instrumento', 'Instrumento',
         'Cuestionario o formulario de recolección', False),
        ('additional.ponderacion', 'Ponderación',
         'Metodología de ponderación o factores de expansión', False),
        ('table_description.notes', 'Notas de procesamiento',
         'Operaciones de limpieza e imputación', False),
    ]),
    ('5. Acceso y Derechos', [
        ('additional.condiciones_acceso', 'Condiciones de acceso',
         'Condiciones de acceso y uso', False),
        ('additional.derechos_uso', 'Derechos de uso',
         'Licencia y derechos de uso', False),
        ('additional.confidencialidad', 'Confidencialidad',
         'Declaración de anonimización / protección de datos', False),
    ]),
]

# Grilla table_columns = ficha técnica VariableConjuntoDatos
COLUMN_PROPS = [
    ('var_name', 'Código'),
    ('label', 'Nombre de la variable'),
    ('definicion', 'Definición conceptual'),
    ('poblacion_objetivo', 'Población objetivo'),
    ('cobertura_geografica', 'Cobertura geográfica'),
    ('desagregacion_geografica', 'Desagregación geográfica'),
    ('desagregacion_tematica', 'Desagregación temática'),
    ('tipo_dato', 'Tipo de dato'),
    ('dominio_dato', 'Dominio del dato'),
    ('unidad_medida', 'Unidad de medida'),
    ('tipo_variable', 'Tipo de variable estadística'),
    ('fuente_datos', 'Fuente de datos'),
    ('periodicidad', 'Periodicidad'),
    ('observaciones', 'Observaciones'),
    ('referencias', 'Referencias (APA 7)'),
    ('organismo_productor', 'Organismo productor'),
    ('universo', 'Universo (DDI)'),
    ('concepto', 'Concepto (DDI)'),
    ('pregunta', 'Pregunta literal (DDI qstn)'),
    ('tipo_representacion', 'Tipo de representación (DDI reprType)'),
    ('categoria_estadistica', 'Categoría estadística (DDI catStat)'),
    ('sello_calidad', 'Sello de calidad'),
    ('orden', 'Orden'),
]


def load_core_specs(editor_path):
    """Mapa key -> spec de campo de los templates core 'table'."""
    specs = {}
    tpl_dir = (Path(editor_path) / 'application/views/metadata_editor/'
               'metadata_editor_templates')
    for f in tpl_dir.glob('*table*.json'):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue

        def walk(items):
            for it in items or []:
                if not isinstance(it, dict):
                    continue
                if it.get('key') and it.get('type') not in (
                        'section', 'section_container'):
                    specs.setdefault(it['key'], it)
                walk(it.get('items'))
        walk(data.get('items'))
    return specs


def field_item(key, title, help_text, required, specs):
    core = specs.get(key)
    if core:
        field = json.loads(json.dumps(core))  # copia profunda
        field['title'] = title
        if help_text:
            field['help_text'] = help_text
    else:
        field = {
            'key': key,
            'title': title,
            'type': 'string',
            'prop_key': key,
            'display_type': 'text',
            'help_text': help_text,
        }
    if required:
        field['required'] = True
        field['class'] = 'required'
    return field


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--editor-path', required=True)
    args = ap.parse_args()
    specs = load_core_specs(args.editor_path)

    items = []
    for si, (title, fields) in enumerate(SECTIONS):
        items.append({
            'type': 'section_container',
            'key': f'sec_{si}',
            'title': title,
            'expanded': si == 0,
            'items': [{
                'type': 'section',
                'key': f'sec_{si}_0',
                'title': title,
                'items': [
                    field_item(k, t, h, req, specs)
                    for k, t, h, req in fields
                ],
            }],
        })

    # table_columns como grilla 'array' (mismo tipo que el core) con
    # las props declaradas del schema + la ficha SIIED extendida.
    col_props = [
        {
            'key': k,
            'title': t,
            'type': 'string',
            'prop_key': f'table_description.table_columns.{k}',
            'display_type': 'text',
        }
        for k, t in COLUMN_PROPS
    ]
    items.append({
        'type': 'section_container',
        'key': 'sec_vars',
        'title': '6. Ficha Técnica de Variables (columnas)',
        'expanded': False,
        'items': [{
            'type': 'section',
            'key': 'sec_vars_0',
            'title': 'Columnas del conjunto',
            'items': [{
                'key': 'table_description.table_columns',
                'title': 'Variables del conjunto de datos',
                'type': 'array',
                'help_text': 'Ficha técnica de cada variable '
                             '(VariableConjuntoDatos del SIIED)',
                'props': col_props,
            }],
        }],
    })

    tpl = {
        'type': 'template',
        'title': 'SIIED - Ficha de Conjunto de Datos (tabla)',
        'items': items,
    }
    out = (Path(args.editor_path) / 'application/views/metadata_editor/'
           'metadata_editor_templates/table_siied_form_template.json')
    out.write_text(json.dumps(tpl, ensure_ascii=False, indent=2))
    n = sum(len(s['items'][0]['items']) for s in items)
    print(f'{out.name}: {len(items)} secciones, {n} campos '
          f'(+{len(COLUMN_PROPS)} props de columna)')


if __name__ == '__main__':
    main()
