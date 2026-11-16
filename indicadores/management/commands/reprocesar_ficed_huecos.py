"""Reprocesa los .xlsm FICED originales y rellena en los consolidados
(equipo='') los campos que `importar_ficed_2024` dejó vacíos:

    p24_1_conceptos_estandarizados   (respuestas_d; dict checkbox-tabla)
    p28_1_frecuencia_reuniones       (respuestas_e; lista)
    p28_2_modelos_estadisticos       (respuestas_e; lista)
    p28_2_especificar                (respuestas_e; texto)
    p28_otro_especificar             (respuestas_e; texto)
    p31_1_frecuencia                 (respuestas_e; lista)
    p31_productos                    (respuestas_e; tabla producto/url)

Solo escribe cuando el Excel trae marcas/texto; no pisa campos ya
diligenciados salvo que el Excel tenga datos y el consolidado esté vacío
({} / [] / '').

Uso:
    python manage.py reprocesar_ficed_huecos --periodo 2024 --dry-run
    python manage.py reprocesar_ficed_huecos --periodo all
"""

import json
import os
import unicodedata
from pathlib import Path

import openpyxl
from django.core.management.base import BaseCommand

from indicadores.management.commands.importar_ficed_2024 import (
    HOJA_RESP, _BD, _marc, _s)
from indicadores.models_iced import ICEDFormulario

BASE = Path(__file__).resolve().parents[3].parent  # ../<repo>/ → carpeta SIIED


def _norm(s):
    s = unicodedata.normalize('NFD', str(s or '').lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ' '.join(''.join(c for c in s if c.isalnum() or c.isspace()).split())


def _sim(a, b):
    ta, tb = set(a.split()), set(b.split())
    return len(ta & tb) / max(1, len(ta | tb))


# sigla de carpeta → fragmento del nombre del organismo, para archivos
# cuyo p1_nombre_organismo viene vacío (DADII/ST 2025).
SIGLA_FALLBACK = {
    'dadii': 'innovacion institucional',
    'st': 'turismo',
    'dacdi': 'control disciplinario',
    'daci': 'control interno',
    'dacp': 'contratacion publica',
    'dagma': 'gestion del medio ambiente',
    'dah': 'hacienda',
    'dap': 'planeacion',
    'datic': 'tecnologias de la informacion',
    'sbs': 'bienestar social',
    'sc': 'secretaria de cultura',
    'sde': 'desarrollo economico',
    'sdr': 'deporte y la recreacion',
    'sdtpc': 'desarrollo territorial',
    'se': 'secretaria de educacion',
    'sg': 'secretaria de gobierno',
    'sgred': 'gestion del riesgo',
    'si': 'secretaria de infraestructura',
    'sm': 'movilidad',
    'spcc': 'paz y cultura ciudadana',
    'ssj': 'seguridad y justicia',
    'sspd': 'salud publica',
    'svsh': 'vivienda social',
    'uaepa': 'proteccion animal',
    'uaesbys': 'gestion de bienes y servicios',
    'uaesp': 'servicios publicos',
}


def _marcado(bd, num):
    return _marc(bd._by_num.get(str(num), (None, None))[1])


def _code_por_kw(texto, mapa):
    t = _norm(texto)
    for kw, code in mapa:
        if kw in t:
            return code
    return None


def extraer_huecos(bd):
    """Devuelve {'d': {...}, 'e': {...}} con los campos hueco parseados."""
    out = {'d': {}, 'e': {}}

    # ---- P24.1 procedencia de conceptos estandarizados (solo si hay marcas)
    map241 = [('dane', 'dane'), ('organismos internacionales', 'organismos_intl'),
              ('otra entidad de orden nacional', 'otra_nacional'),
              ('leyes', 'leyes_decretos'), ('creacion propia', 'creacion_propia'),
              ('otra fuente', 'otra')]
    datos = {}
    for i in range(1, 7):
        p, _ = bd._by_num.get(f'24.1.{i}', ('', None))
        if not _marcado(bd, f'24.1.{i}'):
            continue
        code = _code_por_kw(p, map241)
        if not code:
            continue
        fila = {'seleccion': True}
        cual = bd.texto(f'24.1.{i}.1')
        if cual:
            fila['cual'] = cual
        datos[code] = fila
    if datos:
        out['d']['p24_1_conceptos_estandarizados'] = json.dumps(
            datos, ensure_ascii=False)

    # ---- P28.1 frecuencia de reuniones
    map281 = [('bimensual', 'bimensual'), ('cuatrimentr', 'cuatrimestral'),
              ('trimestr', 'trimestral'), ('semestr', 'semestral'),
              ('anual', 'anual'), ('mensual', 'mensual')]
    fr = []
    for i in range(1, 7):
        p, _ = bd._by_num.get(f'28.1.{i}', ('', None))
        if not _marcado(bd, f'28.1.{i}'):
            continue
        code = _code_por_kw(p, map281)
        if code and code not in fr:
            fr.append(code)
    if fr:
        out['e']['p28_1_frecuencia_reuniones'] = fr

    # ---- P28.2 modelos estadísticos/econométricos + especificar
    map282 = [('basicos', 'basicos'), ('descriptiva', 'descriptiva'),
              ('diagnostica', 'diagnostica'), ('predictiva', 'predictiva'),
              ('prescriptiva', 'prescriptiva'), ('otro', 'otro')]
    mod = []
    for i in range(1, 7):
        p, _ = bd._by_num.get(f'28.2.{i}', ('', None))
        if not _marcado(bd, f'28.2.{i}'):
            continue
        code = _code_por_kw(p, map282)
        if code and code not in mod:
            mod.append(code)
    if mod:
        out['e']['p28_2_modelos_estadisticos'] = mod
        if 'otro' in mod:
            # la fila "cuáles modelos" es la primera hija del otro (x.x.1)
            for i in range(6, 8):
                t = bd.texto(f'28.2.{i}.1')
                if t:
                    out['e']['p28_2_especificar'] = t
                    break

    # ---- P28 otro mecanismo de articulación (texto libre 28.9.1)
    otro28 = bd.texto('28.9.1')
    if otro28:
        out['e']['p28_otro_especificar'] = otro28

    # ---- P31.1 frecuencia de uso de modelos avanzados
    # códigos del formulario: 1 mensual, 5 bimensual, 2 trimestral,
    # 6 cuatrimestral, 3 semestral, 4 anual. El xlsm rotula
    # 'bimestralmente' para la opción bimensual.
    map311 = [('cuatrimentr', '6'), ('bimestr', '5'), ('trimestr', '2'),
              ('semestr', '3'), ('anual', '4'), ('mensual', '1')]
    f31 = []
    for i in range(1, 7):
        p, _ = bd._by_num.get(f'31.1.{i}', ('', None))
        if not _marcado(bd, f'31.1.{i}'):
            continue
        code = _code_por_kw(p, map311)
        if code and code not in f31:
            f31.append(code)
    if f31:
        out['e']['p31_1_frecuencia'] = f31

    # ---- P31 productos + URL de evidencia (subfilas de 31.2–31.5)
    # Se captura aunque la opción madre no esté marcada: hay Excels con
    # texto en 31.x.1 sin la X en 31.x (el texto es dato verificable).
    prods = []
    for i in range(2, 6):
        prod = bd.texto(f'31.{i}.1')
        url = bd.texto(f'31.{i}.2')
        if prod or url:
            prods.append({'producto': prod, 'url': url})
    if prods:
        out['e']['p31_productos'] = json.dumps(prods, ensure_ascii=False)

    return out


def pick_files(periodo, raiz):
    """[(path, sigla_carpeta)] — un xlsm por carpeta de organismo."""
    files = []
    if periodo == '2024':
        base = raiz / 'FICEDS - 2024'
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            cand = [f for f in d.glob('*.xlsm')
                    if 'NO ABRIR' not in f.name.upper()]
            if cand:
                files.append((sorted(cand, key=lambda p: p.name)[-1],
                              d.name.lower()))
        # Cultura 2024: su instrumento quedó en la carpeta 2025/SC
        sc = raiz / 'FICEDS - 2025' / 'SC'
        if sc.is_dir():
            for f in sc.glob('*CULTURA*.xlsm'):
                files.append((f, 'sc'))
    else:
        base = raiz / f'FICEDS - {periodo}'
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            cand = [f for f in d.glob('*.xlsm')
                    if 'NO ABRIR' not in f.name.upper()
                    and '2024' not in f.name
                    and '20250227' not in f.name]  # ese es el FICED 2024 de SC
            if cand:
                files.append((sorted(cand, key=lambda p: p.name)[-1],
                              d.name.lower()))
    return files


class Command(BaseCommand):
    help = 'Rellena en los consolidados los campos que el importador FICED dejó vacíos'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--periodo', default='all',
                            choices=['2024', '2025', 'all'])
        parser.add_argument('--raiz', default=str(BASE),
                            help='Carpeta que contiene "FICEDS - 2024/2025"')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--sobreescribir', action='store_true',
                            help='Pisar campos ya diligenciados si el Excel difiere')

    def handle(self, *args, **o):
        periodos = ['2024', '2025'] if o['periodo'] == 'all' else [o['periodo']]
        raiz = Path(o['raiz'])
        for per in periodos:
            self._reprocesar(per, raiz, o)

    def _reprocesar(self, periodo, raiz, o):
        cons = {}
        for f in ICEDFormulario.objects.filter(
                periodo=periodo, equipo='').select_related('organismo'):
            cons[_norm(f.organismo.nombre)] = f

        files = pick_files(periodo, raiz)
        self.stdout.write(f'===== {periodo}: {len(files)} archivos, '
                          f'{len(cons)} consolidados =====')

        for path, sigla in files:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb[HOJA_RESP] if HOJA_RESP in wb.sheetnames \
                else wb[wb.sheetnames[0]]
            bd = _BD(ws)
            nombre = bd.texto('1')
            cn = _norm(nombre)

            if cn and cn in cons:
                key = cn
            elif cn:
                key = max(cons, key=lambda dn: _sim(cn, dn))
                if _sim(cn, key) < 0.45:
                    key = self._por_sigla(sigla, cons)
            else:
                key = self._por_sigla(sigla, cons)

            if not key or key not in cons:
                self.stderr.write(
                    f'!! {sigla} ({path.name}): sin consolidado '
                    f'para "{nombre}"')
                continue

            form = cons[key]
            huecos = extraer_huecos(bd)
            cambios = []
            for bl, campos in huecos.items():
                attr = f'respuestas_{bl}'
                resp = getattr(form, attr) or {}
                for k, v in campos.items():
                    viejo = resp.get(k)
                    vacio = viejo in (None, '', '{}', '[]')
                    if vacio or (o['sobreescribir'] and viejo != v):
                        resp[k] = v
                        cambios.append((k, viejo, v))
            if not cambios:
                self.stdout.write(f'-- {sigla} → {form.organismo}: sin datos nuevos')
                continue

            self.stdout.write(f'-- {sigla} → {form.organismo}:')
            for k, viejo, nuevo in cambios:
                self.stdout.write(
                    f'     {k}: {str(viejo)[:40]} → {str(nuevo)[:120]}')
            if o['dry_run']:
                continue
            form.save(update_fields=['respuestas_d', 'respuestas_e',
                                     'actualizado_en']
                      if hasattr(form, 'actualizado_en') else None)
            self.stdout.write('     GUARDADO')

    def _por_sigla(self, sigla, cons):
        frag = SIGLA_FALLBACK.get(sigla)
        if not frag:
            return None
        for dn in cons:
            if frag in dn:
                return dn
        return None
