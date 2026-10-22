#!/usr/bin/env python3
"""Genera el form template MSD-SIIED para indicadores (tipo indicator
/ schema timeseries) del OpenMetadata Editor.

Las secciones replican la ficha MSD del modelo Indicador del SIIED
(secciones 0-6). Las claves coinciden con lo que envia
om_sync.serialize_indicador.

Uso:
    python3 scripts/gen_msd_siied_template.py \
        --editor-path /home/amiranda/Descargas/OPENMETADATA/editor
"""

import argparse
import json
from pathlib import Path

# (key, titulo MSD, tipo, ayuda, requerido)
SECTIONS = [
    ('0. Identificación', [
        ('series_description.name', '0.1 Nombre del Indicador',
         'text', 'Nombre del indicador (MSD 2.1)', True),
        ('series_description.database_id', '0.2 Código del Indicador',
         'text', 'Código único del indicador (ej: ICET_SAL_DEM_MOR_02)',
         False),
        ('series_description.abbreviation', '0.3 Sigla',
         'text', 'Sigla o acrónimo del indicador (ej: TMM5)', False),
        ('additional.grupo_indicador', '0.4 Grupo Indicador',
         'text', 'Grupo al que pertenece (ICET/SIIET)', False),
        ('additional.clasificacion',
         'Clasificación (dominio › tema › subtema)', 'text',
         'Ruta temática del indicador en el SIIED', False),
    ]),
    ('1. Contacto Institucional', [
        ('series_description.authoring_entity',
         '1.1 Entidad u Organismo Responsable', 'nested_array',
         'Entidad productora: name=organismo, affiliation=área, '
         'email=contacto (MSD 1.1-1.4)', True),
        ('additional.telefono_contacto', '1.5 Número Telefónico',
         'text', 'Teléfono de atención al ciudadano', False),
        ('metadata_information.prod_date',
         '1.6 Fecha de Publicación de los Metadatos', 'date',
         'Fecha más reciente de difusión de los metadatos MSD', False),
    ]),
    ('2. Características del Indicador', [
        ('series_description.definition_long',
         '2.2 Descripción del Indicador', 'textarea',
         'Descripción general del indicador (MSD 2.2)', False),
        ('additional.objetivo', '2.3 Objetivo', 'textarea',
         'Objetivo del indicador (MSD 2.3)', False),
        ('series_description.statistical_concept',
         '2.4 Cálculo del Indicador / Método de Medición', 'textarea',
         'Descripción del método de medición y cálculo (MSD 2.4)',
         False),
        ('additional.formula', '2.5 Fórmula', 'textarea',
         'Fórmula matemática del indicador', False),
        ('additional.variables_descripcion', '2.6 Variables',
         'textarea', 'Descripción de las variables de la fórmula',
         False),
        ('series_description.measurement_unit',
         '2.7 Unidad de Medida', 'text', 'Unidad de medida (MSD 2.7)',
         False),
        ('series_description.data_collection.data_source',
         '2.8 Fuente de la Información', 'text',
         'Fuente de datos del indicador (MSD 2.8)', False),
        ('additional.operacion_estadistica',
         '2.9 Nombre de la Operación Estadística', 'text',
         'Operación estadística que alimenta el indicador', False),
        ('additional.conjunto_datos', '2.10 Nombre del Conjunto de Datos',
         'text', 'Conjunto de datos al que pertenecen las variables',
         False),
        ('additional.nomenclaturas_clasificaciones',
         '2.11 Nomenclaturas y Clasificaciones', 'textarea',
         'Clasificaciones o nomenclaturas utilizadas (MSD 2.11)', False),
        ('additional.alcance_tematico', '2.12 Alcance Temático',
         'textarea', 'Sectores o temas cubiertos (MSD 2.12)', False),
        ('series_description.universe', '2.13 Población Objetivo',
         'textarea', 'Población objetivo del conjunto de datos (MSD 2.13)',
         False),
        ('additional.cobertura_geografica', '2.14 Cobertura Geográfica',
         'textarea', 'Extensión territorial del indicador (MSD 2.14)',
         False),
        ('series_description.data_collection.period',
         '2.15 Período de Referencia', 'text',
         'Período de la observación medida (MSD 2.15)', False),
        ('series_description.base_period', '2.16 Período Base',
         'text', 'Período base de un índice o serie constante (MSD 2.16)',
         False),
    ]),
    ('3. Difusión', [
        ('additional.serie_historica_disponible',
         '3.1 Serie Histórica Disponible', 'text',
         'Períodos en que el indicador está disponible (MSD 3.1)', False),
        ('series_description.periodicity', '3.2 Frecuencia de Difusión',
         'text', 'Frecuencia de difusión de los datos (MSD 3.2)', False),
        ('additional.medios_difusion', '3.3 Medios de Difusión',
         'textarea', 'Medios de difusión (internet, impreso…) (MSD 3.3)',
         False),
    ]),
    ('4. Comentarios y Referencias', [
        ('data_notes.note', '4.1 Comentarios Adicionales', 'textarea',
         'Información adicional sobre datos o metadatos (MSD 4.1)', False),
        ('series_description.definition_references',
         '5.1 Referencias (APA 7)', 'nested_array',
         'Fuentes bibliográficas, normativas y metodológicas (SDMX)',
         False),
    ]),
    ('5. Responsabilidad Institucional', [
        ('additional.equipo_responsable', '6.3 Equipo Responsable',
         'text', 'Equipo encargado de producir el indicador (SDMX)',
         False),
        ('additional.responsable_validacion.nombre',
         'Nombre del responsable técnico de validación', 'text',
         'Persona responsable técnica del indicador', False),
        ('additional.responsable_validacion.cargo',
         'Cargo del responsable técnico de validación', 'text',
         'Cargo de la persona responsable técnica', False),
        ('additional.responsable_validacion.correo',
         'Correo del responsable técnico de validación', 'text',
         'Correo electrónico del responsable técnico', False),
        ('additional.responsable_validacion.celular',
         'Celular del responsable técnico de validación', 'text',
         'Celular del responsable técnico', False),
    ]),
]


def load_core_specs(editor_path):
    specs = {}
    tpl_dir = (Path(editor_path) / 'application/views/metadata_editor/'
               'metadata_editor_templates')
    for f in tpl_dir.glob('*timeseries*.json'):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--editor-path', required=True)
    args = ap.parse_args()
    specs = load_core_specs(args.editor_path)

    items = []
    for si, (title, fields) in enumerate(SECTIONS):
        sec_fields = []
        for key, ftitle, ftype, help_text, req in fields:
            core = specs.get(key, {})
            field = {
                'key': key,
                'title': ftitle,
                'type': core.get('type', ftype),
                'help_text': help_text,
            }
            for attr in ('props', 'enum', 'rules', 'display_type'):
                if attr in core:
                    field[attr] = core[attr]
            if req:
                field['class'] = 'required'
                field['required'] = True
            elif core.get('class'):
                field['class'] = core['class']
            sec_fields.append(field)
        items.append({
            'type': 'section_container',
            'key': f'sec_{si}',
            'title': title,
            'expanded': si == 0,
            'items': [{
                'type': 'section',
                'key': f'sec_{si}_0',
                'title': title,
                'items': sec_fields,
            }],
        })

    tpl = {
        'type': 'template',
        'title': 'SIIED MSD - Ficha de Indicador',
        'items': items,
    }
    out = (Path(args.editor_path) / 'application/views/metadata_editor/'
           'metadata_editor_templates/indicator_msd_siied_form_template.json')
    out.write_text(json.dumps(tpl, ensure_ascii=False, indent=2))
    n = sum(len(s['items'][0]['items']) for s in items)
    print(f'{out.name}: {len(items)} secciones, {n} campos')


if __name__ == '__main__':
    main()
