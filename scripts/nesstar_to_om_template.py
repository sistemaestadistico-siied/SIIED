#!/usr/bin/env python3
"""Convierte plantillas Nesstar (XML) del DANE/IHSN a form templates
JSON del OpenMetadata Editor.

Mapeo estructural:
    TabGroup (CustomLabel)  -> section_container
    Tab (Name)              -> section
    Item (ID/Label/Description/Mandatory) -> campo {key,title,help_text,...}

Los IDs Nesstar se mapean a las claves DDI del schema del editor via
ITEM_KEY_MAP. Para cada clave se reutiliza la especificacion del
template core (type/props/enum/rules) y se sobreescribe
title/help_text/required con lo del XML.

Los items VarDoc_* van a una plantilla separada de VARIABLES
(microdata_variable_template) con claves var_*.

Uso:
    python3 scripts/nesstar_to_om_template.py \
        IHSN_1.6_es_aj_RRAA_20160309.NesstarTemplate.xml \
        --editor-path /home/amiranda/Descargas/OPENMETADATA/editor
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ------------------------------------------------------------------
# Mapeo Nesstar Item ID -> clave OM (paths del schema microdata)
# ------------------------------------------------------------------
ITEM_KEY_MAP = {
    # ---- DocumentDescription -> doc_desc
    'DocumentDescription_Citation_ProductionStatement_Producers':
        'doc_desc.producers',
    'DocumentDescription_Citation_ProductionStatement_ProductionDate':
        'doc_desc.prod_date',
    'DocumentDescription_Citation_Version_Type':
        'doc_desc.version',
    'DocumentDescription_Citation_TitleStatement_IDNumber':
        'doc_desc.idno',
    # ---- StudyDescription.Citation -> study_desc
    'StudyDescription_Citation_TitleStatement_Title':
        'study_desc.title_statement.title',
    'StudyDescription_Citation_TitleStatement_SubTitle':
        'study_desc.title_statement.sub_title',
    'StudyDescription_Citation_TitleStatement_AlternativeTitle':
        'study_desc.title_statement.alt_title',
    'StudyDescription_Citation_TitleStatement_ParallelTitle':
        'study_desc.title_statement.par_title',
    'StudyDescription_Citation_TitleStatement_IDNumber':
        'study_desc.title_statement.idno',
    'StudyDescription_Citation_SeriesName':
        'study_desc.series_statement.series_name',
    'StudyDescription_Citation_SeriesInformation':
        'study_desc.series_statement.series_info',
    'StudyDescription_Citation_Notes':
        'study_desc.notes',
    'StudyDescription_Citation_Holdings_Text':
        'study_desc.holdings',
    'StudyDescription_Citation_Authors':
        'study_desc.authoring_entity',
    'StudyDescription_Citation_Acknowledgments':
        'study_desc.oth_id',
    'StudyDescription_Citation_ProductionStatement_Producers':
        'study_desc.production_statement.producers',
    'StudyDescription_Citation_ProductionStatement_Fundings':
        'study_desc.production_statement.funding_agencies',
    'StudyDescription_Citation_ProductionStatement_Copyright':
        'study_desc.production_statement.copyright',
    'StudyDescription_Citation_DistributorStatement_Contacts':
        'study_desc.distribution_statement.contact',
    # ---- StudyDescription.Scope -> study_desc.study_info
    'StudyDescription_Scope_Abstract':
        'study_desc.study_info.abstract',
    'StudyDescription_Scope_SummaryDataDescription_AnalysisUnit':
        'study_desc.study_info.analysis_unit',
    'StudyDescription_Scope_SummaryDataDescription_DataKind':
        'study_desc.study_info.data_kind',
    'StudyDescription_Scope_SummaryDataDescription_Universe':
        'study_desc.study_info.universe',
    'StudyDescription_Scope_SummaryDataDescription_Countries':
        'study_desc.study_info.nation',
    'StudyDescription_Scope_SummaryDataDescription_GeographicCoverage':
        'study_desc.study_info.geog_coverage',
    'StudyDescription_Scope_SummaryDataDescription_GeographicUnit':
        'study_desc.study_info.geog_unit',
    'StudyDescription_Scope_SummaryDataDescription_CollectionDates':
        'study_desc.study_info.coll_dates',
    'StudyDescription_Scope_SummaryDataDescription_TimePeriods':
        'study_desc.study_info.time_periods',
    'StudyDescription_Scope_Keywords':
        'study_desc.study_info.keywords',
    'StudyDescription_Scope_TopicClassifications':
        'study_desc.study_info.topics',
    'StudyDescription_Scope_Notes':
        'study_desc.study_info.notes',
    # ---- StudyDescription.Methodology -> study_desc.method
    'StudyDescription_Methodology_ResearchInstrument':
        'study_desc.method.data_collection.research_instrument',
    'StudyDescription_Methodology_Sampling':
        'study_desc.method.data_collection.sampling_procedure',
    'StudyDescription_Methodology_Deviations':
        'study_desc.method.data_collection.sampling_deviation',
    'StudyDescription_Methodology_ResponseRate':
        'study_desc.method.analysis_info.response_rate',
    'StudyDescription_Methodology_Weighting':
        'study_desc.method.data_collection.weight',
    'StudyDescription_Methodology_CollectionMethod':
        'study_desc.method.data_collection.coll_mode',
    'StudyDescription_Methodology_CollectionSituation':
        'study_desc.method.data_collection.coll_situation',
    'StudyDescription_Methodology_MinimizeLossActions':
        'study_desc.method.data_collection.act_min',
    'StudyDescription_Methodology_DataCollectors':
        'study_desc.method.data_collection.data_collectors',
    'StudyDescription_Methodology_CleaningOperations':
        'study_desc.method.data_collection.cleaning_operations',
    'StudyDescription_Methodology_Notes':
        'study_desc.method.method_notes',
    'StudyDescription_Methodology_SamplingErrorEstimates':
        'study_desc.method.analysis_info.sampling_error_estimates',
    'StudyDescription_Methodology_DataAppraisal':
        'study_desc.method.analysis_info.data_appraisal',
    # ---- StudyDescription.AccessConditions -> study_desc.data_access
    'StudyDescription_AccessConditions_Notes':
        'study_desc.data_access.notes',
    'StudyDescription_AccessConditions_UseStatement_Contacts':
        'study_desc.data_access.dataset_use.contact',
    'StudyDescription_AccessConditions_UseStatement_'
    'ConfidentialityDeclaration_Text':
        'study_desc.data_access.dataset_use.conf_dec',
    'StudyDescription_AccessConditions_UseStatement_Conditions':
        'study_desc.data_access.dataset_use.conditions',
    'StudyDescription_AccessConditions_UseStatement_'
    'CitationRequirement':
        'study_desc.data_access.dataset_use.cit_req',
    'StudyDescription_AccessConditions_UseStatement_Disclaimer':
        'study_desc.data_access.dataset_use.disclaimer',
}

# VarDoc -> plantilla de variables (claves del variable-schema del editor)
VARDOC_KEY_MAP = {
    'VarDoc_Text': 'var_txt',
    'VarDoc_Universe': 'var_universe',
    'VarDoc_ResponseUnit': 'var_respunit',
    'VarDoc_PreQuestion': 'var_qstn_preqtxt',
    'VarDoc_LiteralQuestion': 'var_qstn_qstnlit',
    'VarDoc_PostQuestion': 'var_qstn_postqtxt',
    'VarDoc_InterviewerInstructions': 'var_qstn_ivulnstr',
    'VarDoc_Imputation': 'var_imputation',
    'VarDoc_CodingInstructions': 'var_codinstr',
    'VarDoc_Security': 'var_security',
    'VarDoc_Notes': 'var_notes',
}

# Tipos de item Nesstar -> tipo OM por defecto (si el core no provee spec)
DEFAULT_TYPE_BY_TAG = {
    'TextItem': 'textarea',
    'UnicodeAttributeItem': 'text',
    'AttributeItem': 'text',
    'DateItem': 'date',
    'VocabItem': 'dropdown',
    'KWVocabItem': 'nested_array',
    'KeywordsItem': 'nested_array',
    'CountriesItem': 'nested_array',
    'ProducersItem': 'nested_array',
    'AuthorsItem': 'nested_array',
    'FundingsItem': 'nested_array',
    'DataCollectorsItem': 'nested_array',
    'ContactsItem': 'nested_array',
    'AcknowledgmentsItem': 'nested_array',
    'TimeSpansItem': 'nested_array',
    'LinkedTextItem': 'textarea',
    'LinkedTextListItem': 'textarea',
    'UniverseItem': 'textarea',
}

FIELD_TAGS = set(DEFAULT_TYPE_BY_TAG)


def load_core_specs(editor_path):
    """Indexa los items de los templates core por clave, para reutilizar
    sus especificaciones (type/props/enum/rules)."""
    specs = {}
    tpl_dir = (Path(editor_path) / 'application/views/metadata_editor/'
               'metadata_editor_templates')
    for f in tpl_dir.glob('*.json'):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue

        def walk(items):
            for it in items or []:
                if not isinstance(it, dict):
                    continue
                if it.get('key') and it.get('type') not in (
                        'section', 'section_container', 'tab', 'tabs'):
                    specs.setdefault(it['key'], it)
                walk(it.get('items'))
        walk(data.get('items'))
    return specs


def item_text(el, tag):
    node = el.find(tag)
    if node is None:
        return ''
    return (node.text or '').strip()


def item_help(el):
    node = el.find('Description')
    if node is not None and node.text:
        return node.text.strip()
    return ''


def convert_item(item, key, specs, warnings):
    """Construye el campo OM a partir del Item Nesstar."""
    core = specs.get(key, {})
    field_tag = next(
        (ch.tag for ch in item if ch.tag in FIELD_TAGS), None)
    field = {
        'key': key,
        'title': item.get('Label') or item.get('ID'),
        'type': core.get('type') or DEFAULT_TYPE_BY_TAG.get(
            field_tag, 'text'),
        'help_text': item_help(item),
    }
    for attr in ('props', 'enum', 'rules', 'display_type',
                 'is_recommended', 'name', 'prop_key'):
        if attr in core:
            field[attr] = core[attr]
    if item.get('Mandatory', '').upper() == 'TRUE':
        field['class'] = 'required'
        field['required'] = True
        base_rules = field.get('rules', '')
        field['rules'] = ('required|' + base_rules) if base_rules \
            and 'required' not in base_rules else (
                base_rules or 'required')
    elif core.get('class'):
        field['class'] = core['class']
    if key not in specs:
        warnings.append(f'sin spec core: {key} ({item.get("ID")})')
    return field


def find_tab_context(xml_root, item_el):
    """Ubica el Tab/TabGroup padre de un Item recorriendo el árbol."""
    for tg in xml_root.iter('TabGroup'):
        for tab in tg.findall('Tab'):
            for it in tab.iter('Item'):
                if it is item_el:
                    return (
                        tg.get('CustomLabel') or 'General',
                        tab.get('Name') or 'General')
    return 'General', 'General'


def convert(xml_path, specs):
    root = ET.parse(xml_path).getroot()
    tpl = root.find('Template')
    name = tpl.get('Name', Path(xml_path).stem)

    sections = {}   # (tabgroup) -> {tab -> [fields]}
    var_sections = {}
    warnings, skipped_files = [], []

    for item in root.iter('Item'):
        iid = item.get('ID', '')
        if iid in VARDOC_KEY_MAP:
            tgroup, tab = find_tab_context(root, item)
            field = convert_item(
                item, VARDOC_KEY_MAP[iid], specs, warnings)
            var_sections.setdefault(tab, []).append(field)
        elif iid in ITEM_KEY_MAP:
            tgroup, tab = find_tab_context(root, item)
            field = convert_item(
                item, ITEM_KEY_MAP[iid], specs, warnings)
            sections.setdefault(tgroup, {}).setdefault(
                tab, []).append(field)
        elif iid.startswith('FileDescription_'):
            skipped_files.append(iid)
        else:
            warnings.append(f'sin mapeo: {iid}')

    project_tpl = {
        'type': 'template',
        'title': f'{name} - SIIED (proyecto)',
        'items': [
            {
                'type': 'section_container',
                'key': f'sec_{i}',
                'title': tg_label,
                'expanded': i == 0,
                'items': [
                    {
                        'type': 'section',
                        'key': f'sec_{i}_{j}',
                        'title': tab_label,
                        'items': fields,
                    }
                    for j, (tab_label, fields)
                    in enumerate(tabs.items())
                ],
            }
            for i, (tg_label, tabs) in enumerate(sections.items())
        ],
    }
    var_tpl = {
        'type': 'template',
        'title': f'{name} - SIIED (variables)',
        'items': [
            {
                'type': 'section',
                'key': f'varsec_{i}',
                'title': tab_label,
                'expanded': True,
                'items': fields,
            }
            for i, (tab_label, fields)
            in enumerate(var_sections.items())
        ],
    }
    return project_tpl, var_tpl, warnings, skipped_files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xml')
    ap.add_argument('--editor-path', required=True)
    ap.add_argument('--out-dir', default=None,
                    help='directorio de salida (default: '
                         '<editor>/application/views/metadata_editor/'
                         'metadata_editor_templates)')
    args = ap.parse_args()

    specs = load_core_specs(args.editor_path)
    out_dir = Path(args.out_dir) if args.out_dir else (
        Path(args.editor_path) / 'application/views/metadata_editor/'
        'metadata_editor_templates')

    proj, var, warnings, skipped = convert(args.xml, specs)

    stem = Path(args.xml).stem.replace('.NesstarTemplate', '')
    proj_file = out_dir / f'{stem.lower()}_siied_form_template.json'
    var_file = out_dir / f'{stem.lower()}_siied_variable_template.json'
    proj_file.write_text(json.dumps(
        proj, ensure_ascii=False, indent=2))
    var_file.write_text(json.dumps(
        var, ensure_ascii=False, indent=2))

    n_fields = sum(
        len(t['items']) for sc in proj['items']
        for t in sc['items'])
    print(f'OK proyecto: {proj_file.name} '
          f'({len(proj["items"])} secciones, {n_fields} campos)')
    print(f'OK variables: {var_file.name} '
          f'({len(var["items"])} secciones, '
          f'{sum(len(s["items"]) for s in var["items"])} campos)')
    if skipped:
        print(f'omitidos (nivel archivo): {len(skipped)}')
    for w in warnings:
        print('  WARN', w)


if __name__ == '__main__':
    main()
