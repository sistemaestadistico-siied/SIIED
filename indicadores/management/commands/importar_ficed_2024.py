"""
Importa un FICED diligenciado en el instrumento Excel 2024 (*.xlsm) al
formato digital de ICEDFormulario, como si hubiera sido procesado.

- Lee las respuestas de la hoja 'BD_Registro' (tabla No | Pregunta | Respuestas)
  y la hoja 'RRHH' (recurso humano en formato horizontal).
- Mapea cada bloque numerado (1-42) a los campos p<N>_* del wizard digital,
  reproduciendo los formatos JSON de los widgets (checkbox-tabla, tabla-simple,
  estructura-mop, rrhh-tabla, desplegables-multiples).
- Lee los puntajes del Excel de resultados (hoja 'A. Resultado global' y
  'B. Resultado por dimensiones') y los persiste como autoritativos.
- Además corre calcular_iced() sobre las respuestas importadas y reporta la
  diferencia contra el Excel para validación.
- Materializa ICEDPersonaContacto e ICEDRecursoHumano igual que el wizard.

Uso:
    python manage.py importar_ficed_2024 \
        --ficed 'FICED_DAP_2024.xlsm' \
        --resultado 'RESULTADO_ICED_DAP_2024.xlsx' \
        --periodo 2024 --estado validado [--dry-run]
"""
import json
import re
from decimal import Decimal

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from indicadores.models_iced import (
    ICEDFormulario, ICEDPersonaContacto, ICEDRecursoHumano,
)

HOJA_RESP = 'BD_Registro'
HOJA_RRHH = 'RRHH'

# Etapas del proceso estadístico (columnas fijas de la hoja RRHH, cols 24-31)
ETAPAS_ORDEN = ['DN', 'D', 'C', 'R', 'P', 'A', 'DI', 'E']
# Nivel de formación (cols 33-38)
NIVELES_ORDEN = ['B', 'TT', 'P', 'E', 'M', 'D']


def _s(v):
    return str(v).strip() if v is not None else ''


def _marc(v):
    """Celda marcada (X / x / Sí)."""
    return _s(v).lower() in ('x', 'sí', 'si', 'yes', '1')


def _si_no(v):
    s = _s(v).lower()
    if s in ('sí', 'si', 'x'):
        return 'si'
    if s in ('no',):
        return 'no'
    return ''


def _num(v):
    """Parsea números del Excel (float o '1,5' decimal-coma)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = _s(v).replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


class _BD:
    """Acceso indexado a las filas de BD_Registro, en orden de hoja."""

    def __init__(self, ws):
        self.rows = []  # [(num, pregunta, resp)]
        for row in ws.iter_rows(min_row=2, max_col=3, values_only=True):
            n, p, r = (list(row) + [None] * 3)[:3]
            if n is None:
                continue
            self.rows.append((str(n).strip(), _s(p), r))
        self._by_num = {}
        for n, p, r in self.rows:
            self._by_num.setdefault(n, (p, r))

    def get(self, num):
        return self._by_num.get(str(num), (None, None))[1]

    def texto(self, num):
        v = self.get(num)
        return '' if v in (None, '#N/A') else _s(v)

    def marcado(self, num):
        return _marc(self.get(num))

    def elegida(self, prefijo, n_opciones):
        """Índice (1..n) de la primera opción marcada del bloque prefijo.N."""
        for i in range(1, n_opciones + 1):
            if self.marcado(f'{prefijo}.{i}'):
                return i
        return None

    def elegidas(self, prefijo, n_opciones):
        """Índices marcados del bloque."""
        return [i for i in range(1, n_opciones + 1)
                if self.marcado(f'{prefijo}.{i}')]


class Command(BaseCommand):
    help = 'Importa FICED 2024 (xlsm) + resultados (xlsx) a ICEDFormulario como procesado'
    # El check de URLs importa views.py → openai/torch; cada invocación
    # tardaba ~1 min y los procesos morían interrumpidos.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--ficed', required=True, help='xlsm del instrumento diligenciado')
        parser.add_argument('--resultado', help='xlsx de resultados (opcional)')
        parser.add_argument('--organismo', help='Nombre/fragmento del organismo (default: respuesta P1)')
        parser.add_argument('--periodo', default='2024')
        parser.add_argument('--equipo', default='')
        parser.add_argument('--estado', default='validado',
                            choices=[c for c, _ in ICEDFormulario.ESTADO_CHOICES])
        parser.add_argument('--dry-run', action='store_true')

    # ------------------------------------------------------------------
    def handle(self, *args, **o):
        wb = openpyxl.load_workbook(o['ficed'], read_only=True, data_only=True)
        if HOJA_RESP not in wb.sheetnames:
            raise CommandError(f'Sin hoja {HOJA_RESP}: {wb.sheetnames}')
        bd = _BD(wb[HOJA_RESP])
        # La hoja varía de nombre entre versiones ('RRHH' 2024, 'Anexo 3. RRHH'
        # 2025); evitar las de registro ('RrHh_Registro').
        ws_rrhh = next((wb[n] for n in wb.sheetnames
                        if 'rrhh' in n.lower() and 'registro' not in n.lower()), None)
        rrhh = self._parse_rrhh(ws_rrhh) if ws_rrhh is not None else []

        resp_a = self._modulo_a(bd)
        resp_b = self._modulo_b(bd)
        resp_c = self._modulo_c(bd, rrhh)
        resp_d = self._modulo_d(bd)
        resp_e = self._modulo_e(bd)

        org = self._buscar_organismo(o['organismo'] or resp_a.get('p1_nombre_organismo'))
        self.stdout.write(f'Organismo: {org} | periodo {o["periodo"]} | estado {o["estado"]}')

        with transaction.atomic():
            form, created = ICEDFormulario.objects.update_or_create(
                organismo=org, periodo=o['periodo'], equipo=o['equipo'],
                defaults={
                    'estado': o['estado'],
                    'respuestas_a': resp_a,
                    'respuestas_b': resp_b,
                    'respuestas_c': resp_c,
                    'respuestas_d': resp_d,
                    'respuestas_e': resp_e,
                    'paso_actual': 'revision',
                    'fecha_envio': timezone.now(),
                    'fecha_validacion': timezone.now() if o['estado'] == 'validado' else None,
                },
            )
            self._materializar_contactos(form)
            self._materializar_rrhh(form)

            # Puntajes: calculados sobre las respuestas importadas
            from indicadores.calcular_iced import calcular_iced
            calc = calcular_iced(form)
            form.puntajes_detalle = {
                'indicadores': calc['indicadores'],
                'subdimensiones': calc['subdimensiones'],
                'dimensiones': calc['dimensiones'],
                'detalle': calc['detalle'],
            }
            if o['resultado']:
                self._leer_resultados(o['resultado'], form, calc)
            else:
                for f, k in (('puntaje_b', 'puntaje_b'), ('puntaje_c', 'puntaje_c'),
                             ('puntaje_d', 'puntaje_d'), ('puntaje_e', 'puntaje_e'),
                             ('puntaje_global', 'puntaje_global')):
                    setattr(form, f, Decimal(str(calc[k])) / Decimal('100'))
            form.save()

            if o['dry_run']:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('DRY-RUN: nada guardado.'))

        self._reporte(form, calc, created)

    # ------------------------------------------------------------------
    # MÓDULO A
    def _modulo_a(self, bd):
        def partes(celda):
            """'1. Ana; 2. Luis' → ['Ana', 'Luis']; sin enumeración → [celda]."""
            items = [p.strip(' \t;:,') for p in re.split(r'\d+\s*[.)]', _s(celda))]
            return [p for p in items if p]

        nombres = partes(bd.get('2'))
        cargos = partes(bd.get('3'))
        correos = partes(bd.get('4'))
        telefonos = partes(bd.get('5'))
        contactos = []
        for i, nom in enumerate(nombres):
            cargo = cargos[i] if i < len(cargos) else (cargos[0] if cargos else '')
            contactos.append({
                'nombre_completo': nom,
                'tipo_vinculacion': 'contratista' if 'contrat' in cargo.lower() else 'nombrado',
                'cargo': cargo,
                'correo': correos[i] if i < len(correos) else '',
                'telefono': telefonos[i] if i < len(telefonos) else '',
                'orden': i,
            })
        return {
            'p1_nombre_organismo': bd.texto('1'),
            'p1_nombre_organismo_display': bd.texto('1'),
            'personas_contacto_json': json.dumps(contactos, ensure_ascii=False),
        }

    # ------------------------------------------------------------------
    # MÓDULO B (P6-P12)
    def _modulo_b(self, bd):
        r = {
            'p6_funciones_estadisticas': _si_no(bd.get('6')),
            'p6_descripcion': bd.texto('6.1'),
            'p7_procedimientos': _si_no(bd.get('7')),
            'p7_info_definiciones': '',
            'p7_estructura_mop': json.dumps(self._parse_mop(bd), ensure_ascii=False),
        }
        # P8 / P9 — checkbox-tabla {codigo: {seleccion, documento}}
        for pref, campo in (('8', 'p8_herramientas_planificacion'),
                            ('9', 'p9_herramientas_mejoramiento')):
            datos = {}
            for i, code in enumerate(['planes_trabajo', 'planes_accion', 'programas', 'proyectos'], 1):
                datos[code] = {'seleccion': bd.marcado(f'{pref}.{i}')}
                if datos[code]['seleccion']:
                    datos[code]['documento'] = bd.texto(f'{pref}.{i}.1')
            datos['no_se_incluyen'] = {'seleccion': bd.marcado(f'{pref}.5')}
            r[campo] = json.dumps(datos, ensure_ascii=False)

        # P10
        sel10 = bd.elegida('10', 4)
        r['p10_participacion'] = str(sel10) if sel10 else ''
        r['p10_motivo_no'] = bd.texto('10.4.1') if sel10 == 4 else ''
        acts = []
        if sel10 in (1, 2, 3):
            t = bd.texto(f'10.{sel10}.1')
            if t:
                acts.append({'actividad': t, 'fecha': '', 'organismo': ''})
        r['p10_actividades'] = json.dumps(acts, ensure_ascii=False)

        # P11 — instancias
        datos = {}
        for i, code in enumerate(['comisiones', 'comites', 'mesas', 'observatorios', 'otros'], 1):
            datos[code] = {'seleccion': bd.marcado(f'11.{i}')}
            if datos[code]['seleccion']:
                datos[code]['internas'] = bd.texto(f'11.{i}.1')
                datos[code]['externas'] = bd.texto(f'11.{i}.2')
        datos['no_participa'] = {'seleccion': bd.marcado('11.6')}
        r['p11_instancias_coordinacion'] = json.dumps(datos, ensure_ascii=False)

        # P12
        sel12 = bd.elegida('12', 3)
        r['p12_trazabilidad'] = str(sel12) if sel12 else ''
        r['p12_descripcion_mecanismo'] = (bd.texto(f'12.{sel12}.1') if sel12 in (1, 2) else '')
        return r

    # ------------------------------------------------------------------
    # MÓDULO C (P13-P22)
    def _modulo_c(self, bd, rrhh):
        r = {}
        # P13 — herramientas procesamiento
        map13 = {1: 'hojas_calculo', 2: 'r', 3: 'sas', 4: 'spss', 5: 'stata',
                 6: 'propias', 7: 'python', 8: 'gis', 9: 'otra', 10: 'ninguna'}
        datos = {}
        for i, code in map13.items():
            datos[code] = {'seleccion': bd.marcado(f'13.{i}')}
            if datos[code]['seleccion'] and code in ('propias', 'otra'):
                datos[code]['cual'] = bd.texto(f'13.{i}.1')
        r['p13_herramientas_procesamiento'] = json.dumps(datos, ensure_ascii=False)

        # P14 — gestores BD
        map14 = {1: 'oracle', 2: 'postgresql', 3: 'sqlserver', 4: 'mysql',
                 5: 'sybase', 6: 'otro', 7: 'ninguno'}
        datos = {}
        for i, code in map14.items():
            datos[code] = {'seleccion': bd.marcado(f'14.{i}')}
            if datos[code]['seleccion'] and code == 'otro':
                datos[code]['cual'] = bd.texto('14.6.1')
        r['p14_gestores_bd'] = json.dumps(datos, ensure_ascii=False)

        # P15
        r['p15_herramientas_visualizacion'] = '1' if bd.marcado('15.1') else ('2' if bd.marcado('15.2') else '')
        map15 = {1: 'tableau', 2: 'powerbi', 3: 'looker', 4: 'qlik', 5: 'sap',
                 6: 'excel', 7: 'ibm', 8: 'otros', 9: 'ninguna'}
        datos = {}
        for i, code in map15.items():
            datos[code] = {'seleccion': bd.marcado(f'15.1.{i}')}
            if datos[code]['seleccion'] and code == 'otros':
                datos[code]['cual'] = bd.texto('15.1.8.1')
        r['p15_1_herramientas_tableros'] = json.dumps(datos, ensure_ascii=False)

        # P16 — reportes/tableros nombre+url
        rep = []
        for i in range(1, 11):
            nombre, url = bd.texto(f'16.{i}'), bd.texto(f'16.{i}.1')
            if nombre or url:
                rep.append({'nombre': nombre, 'url': url})
        r['p16_reportes_tableros'] = json.dumps(rep, ensure_ascii=False)

        for pref, campo, n in (('17', 'p17_suficiencia_herramientas', 5),
                               ('18', 'p18_estructura_rrhh', 4),
                               ('20', 'p20_suficiencia_rrhh', 5),
                               ('22', 'p22_suficiencia_financiera', 5)):
            sel = bd.elegida(pref, n)
            r[campo] = str(sel) if sel else ''

        r['p19_rrhh_list'] = json.dumps(rrhh, ensure_ascii=False)

        # P21 — presupuesto: el xlsm trae fracción (0.112) → porcentaje (11.2)
        keys21 = ['p21_hw_servidores', 'p21_hw_computadoras', 'p21_hw_moviles',
                  'p21_hw_almacenamiento', 'p21_sw_estadistico', 'p21_sw_bd',
                  'p21_sw_encuestas', 'p21_sw_visualizacion', 'p21_sw_seguridad',
                  'p21_per_contratacion', 'p21_per_capacitacion',
                  'p21_per_consultorias', 'p21_per_mantenimiento']
        for i, k in enumerate(keys21, 1):
            v = _num(bd.get(f'21.{i}'))
            r[k] = round(v * 100, 4) if v is not None else None
        return r

    # ------------------------------------------------------------------
    # MÓDULO D (P23-P35)
    def _modulo_d(self, bd):
        r = {'p23_operaciones_estadisticas': json.dumps(self._parse_ooee(bd),
                                                       ensure_ascii=False)}
        # P24 — lineamientos (match por texto)
        datos = {c: {'seleccion': False} for c in
                 ('lineamientos_sen', 'ntc_pe_1000', 'nomenclaturas',
                  'conceptos_estandarizados', 'ninguna')}
        kw24 = [('sen', 'lineamientos_sen'), ('ntc', 'ntc_pe_1000'),
                ('nomenclatur', 'nomenclaturas'), ('conceptos', 'conceptos_estandarizados')]
        for i in range(1, 5):
            p, resp = bd._by_num.get(f'24.{i}', ('', None))
            if not _marc(resp):
                continue
            t = p.lower()
            for kw, code in kw24:
                if kw in t:
                    datos[code]['seleccion'] = True
                    break
        if bd.marcado('24.5'):
            datos['ninguna']['seleccion'] = True
        r['p24_lineamientos'] = json.dumps(datos, ensure_ascii=False)
        r['p24_nomenclaturas'] = json.dumps(self._parse_nomenclaturas(bd),
                                           ensure_ascii=False)
        r['p24_1_conceptos_estandarizados'] = json.dumps({})

        # P25-P28
        map25 = ['encuestas', 'reuniones_expertos', 'reuniones_partes', 'mesas',
                 'solicitudes', 'documentos_pp', 'planes', 'proyectos',
                 'consultas_ref', 'otro', 'ninguno']
        r['p25_mecanismos_necesidades'] = [
            map25[i - 1] for i in bd.elegidas('25', len(map25))]
        r['p25_otro_especificar'] = bd.texto('25.10.1')

        map26 = ['analisis_interno', 'colaboracion', 'plataformas_digitales',
                 'otro', 'no_aplica', 'no_realiza']
        r['p26_estructura_analisis'] = [
            map26[i - 1] for i in bd.elegidas('26', len(map26))]
        r['p26_otro_especificar'] = bd.texto('26.4.1')

        sel27 = bd.elegida('27', 4)
        r['p27_articulacion'] = str(sel27) if sel27 else ''

        map28 = ['reuniones', 'actas', 'metodologia', 'comite', 'informes',
                 'talleres', 'nube', 'sistema_centralizado', 'otro', 'no_articulan']
        r['p28_como_articulan'] = [
            map28[i - 1] for i in bd.elegidas('28', len(map28)) if i <= len(map28)]
        r['p28_otro_especificar'] = ''

        # P29 (+ subpreguntas, solo si rol=1 líder)
        sel29 = bd.elegida('29', 4)
        if len(bd.elegidas('29', 4)) > 1:
            self.stderr.write(f'  ⚠ P29 tiene varias opciones marcadas {bd.elegidas("29",4)} — se toma la primera')
        r['p29_rol_politicas'] = str(sel29) if sel29 else ''
        r['p29_otro_especificar'] = ''
        map291 = ['cuantitativo', 'cualitativo', 'mixto', 'resultados',
                  'participativas', 'sistemas', 'encuestas', 'otro']
        r['p29_1_metodologia'] = [
            map291[i - 1] for i in bd.elegidas('29.1', len(map291))]
        map292 = ['mensual', 'trimestral', 'semestral', 'anual']
        r['p29_2_frecuencia'] = [
            map292[i - 1] for i in bd.elegidas('29.2', len(map292))]
        map293 = ['informes', 'web', 'redes', 'boletines', 'presentaciones',
                  'conferencias', 'dashboards', 'otro']
        r['p29_3_medios_divulgacion'] = [
            map293[i - 1] for i in bd.elegidas('29.3', len(map293))]
        map294 = ['presentacion_directiva', 'distribucion_informes',
                  'retroalimentacion', 'ajuste_estrategias', 'recomendaciones',
                  'capacitacion', 'divulgacion_publica', 'monitoreo_continuo',
                  'investigacion', 'otro', 'ninguna']
        r['p29_4_acciones'] = [
            map294[i - 1] for i in bd.elegidas('29.4', len(map294)) if i <= len(map294)]

        # P30 — lineamientos metodológicos (posicional)
        map30 = ['alcaldia_cali', 'dnp', 'dane', 'dafp', 'internacionales',
                 'otros', 'ninguno']
        datos = {}
        for i, code in enumerate(map30, 1):
            datos[code] = {'seleccion': bd.marcado(f'30.{i}')}
        r['p30_lineamientos_metodologicos'] = json.dumps(datos, ensure_ascii=False)
        r['p30_tabla_alcaldia'] = json.dumps([])

        # P31-P32
        sel31 = bd.elegida('31', 5)
        r['p31_tipo_analitica'] = str(sel31) if sel31 else ''
        r['p31_descripcion_productos'] = ''
        r['p31_url'] = ''
        sel32 = bd.elegida('32', 6)
        r['p32_analitica_datic'] = str(sel32) if sel32 else ''
        r['p32_caso_uso'] = bd.texto('32.7')

        # P33-P35 — observatorios
        r['p33_tiene_observatorio'] = _si_no(bd.get('33'))
        obs = []
        for i in range(1, 5):
            t = bd.texto(f'33.{i}')
            if t and t not in obs:
                obs.append(t)
        r['p33_observatorios'] = json.dumps(obs, ensure_ascii=False)
        r['p34_info_observatorios'] = json.dumps([])
        docs = []
        url35 = bd.texto('35')
        if url35:
            docs.append({
                'tipo_documento': 'otro',
                'nombre_documento': 'Documentación metodológica del observatorio',
                'codigo_mop': '', 'url': url35,
                'descripcion': 'Documentación metodológica existente del observatorio (importado del instrumento FICED 2024)',
            })
        r['p35_documentacion_observatorio'] = json.dumps(docs, ensure_ascii=False)
        return r

    # ------------------------------------------------------------------
    # MÓDULO E (P36-P42)
    def _modulo_e(self, bd):
        r = {}
        map36 = ['diagnostico_pdd', 'rendicion_cuentas', 'pot', 'evaluar_pp']
        datos = {}
        for i, code in enumerate(map36, 1):
            datos[code] = {'seleccion': bd.marcado(f'36.{i}')}
            if datos[code]['seleccion']:
                datos[code]['url'] = bd.texto(f'36.{i}.1')
        r['p36_uso_indicadores'] = json.dumps(datos, ensure_ascii=False)

        map37 = ['organismos_misma', 'organismos_intl', 'presidencia',
                 'ministerios', 'control', 'otras_nacional', 'territorial',
                 'gremios', 'privadas', 'academia', 'publico', 'otro', 'ninguno']
        datos = {}
        for i, code in enumerate(map37, 1):
            datos[code] = {'seleccion': bd.marcado(f'37.{i}')}
            if datos[code]['seleccion'] and code != 'ninguno':
                datos[code]['cual'] = bd.texto(f'37.{i}.1')
        r['p37_usuarios'] = json.dumps(datos, ensure_ascii=False)

        map38 = ['cuadros_salida', 'boletin', 'anuario', 'mapas_sig',
                 'bases_interactivas', 'otro', 'ninguna']
        datos = {}
        for i, code in enumerate(map38, 1):
            datos[code] = {'seleccion': bd.marcado(f'38.{i}')}
            if datos[code]['seleccion'] and code == 'otro':
                datos[code]['cual'] = bd.texto('38.6.1')
        r['p38_productos_difusion'] = json.dumps(datos, ensure_ascii=False)

        map39 = ['web', 'fisico', 'electronico', 'otro']
        datos = {}
        for i, code in enumerate(map39, 1):
            datos[code] = {'seleccion': bd.marcado(f'39.{i}')}
            if datos[code]['seleccion']:
                if code == 'web':
                    datos[code]['url'] = bd.texto('39.1.1')
                elif code == 'otro':
                    datos[code]['cual'] = bd.texto('39.4.1')
        r['p39_medios_difusion'] = json.dumps(datos, ensure_ascii=False)

        map40 = ['bd_anonimizadas', 'resultados_indicadores', 'ficha_tecnica',
                 'resultados_indicadores_2', 'georreferenciadas',
                 'series_historicas', 'ficha_metodologica', 'doc_metodologico',
                 'cuadros_salida', 'calendario', 'desagregacion_geo',
                 'desagregacion_tematica', 'microdatos', 'observatorios']
        datos = {}
        for i, code in enumerate(map40, 1):
            datos[code] = {'seleccion': bd.marcado(f'40.{i}')}
            if datos[code]['seleccion']:
                datos[code]['url'] = bd.texto(f'40.{i}.1')
        r['p40_elementos_web'] = json.dumps(datos, ensure_ascii=False)

        # P41
        r['p41_indaga_satisfaccion'] = 'si' if bd.marcado('41.1') else ('no' if bd.marcado('41.2') else '')
        map411 = ['encuestas', 'entrevistas', 'grupos_focales', 'comentarios',
                  'indicadores_uso', 'otro']
        r['p41_1_mecanismos'] = [
            map411[i - 1] for i in bd.elegidas('41.1', len(map411))]
        r['p41_1_especificar'] = bd.texto('41.1.6.1')
        r['p41_2_matriz_satisfaccion'] = json.dumps({})
        r['p42_observaciones'] = bd.texto('42')
        return r

    # ------------------------------------------------------------------
    # Parsers especiales
    def _parse_mop(self, bd):
        """Grupos 7.N → filas estructura-mop del widget."""
        grupos = {}
        for num, preg, resp in bd.rows:
            m = re.match(r'^7\.(\d+)\.', num)
            if not m:
                continue
            grupos.setdefault(int(m.group(1)), []).append((num, preg, resp))
        filas = []
        for g in sorted(grupos):
            n_mp = c_mp = n_pr = c_pr = n_sp = c_sp = ''
            pcs = []
            pend = None
            for num, preg, resp in grupos[g]:
                t = preg.lower()
                if 'codigo' in t or 'código' in t:
                    if 'macroproceso' in t:
                        c_mp = _s(resp)
                    elif 'proceso' in t and 'subproceso' not in t and 'proce' not in t.split('codigo')[0]:
                        c_pr = _s(resp)
                    elif 'subproceso' in t:
                        c_sp = _s(resp)
                    else:
                        if resp not in (None, '#N/A') and _s(resp):
                            pcs.append(_s(resp))
                    continue
                if 'macroproceso' in t:
                    n_mp = _s(resp)
                elif 'subproceso' in t:
                    n_sp = _s(resp)
                elif 'proceso' in t and 'rocedim' not in t:
                    n_pr = _s(resp)
            if c_mp:
                filas.append({
                    'macroproceso_id': c_mp,
                    'proceso_id': c_pr,
                    'subproceso_id': c_sp,
                    'procedimientos': pcs,
                })
        return filas

    def _parse_ooee(self, bd):
        """Bloque 23: agrupa secuencialmente cada 'Nombre operación estadística'."""
        cols = [
            ('nombre operación', 'nombre_oe'),
            ('vigente', 'vigente'),
            ('documento metodológico', 'doc_metodologico'),
            ('ficha metodológica', 'ficha_metodologica'),
            ('manual operativo', 'manual_operativo'),
            ('diccionario', 'diccionario_datos'),
            ('consistencia', 'doc_consistencia'),
            ('fortalecimiento', 'acciones_fortalecimiento'),
            ('sicode', 'publicado_sicode'),
        ]
        ooee, cur = [], None
        for num, preg, resp in bd.rows:
            if not num.startswith('23.'):
                continue
            t = preg.lower()
            if 'nombre operación' in t or 'nombre operacion' in t:
                cur = {}
                ooee.append(cur)
                cur['nombre_oe'] = _s(resp)
                continue
            if cur is None:
                continue
            for kw, col in cols[1:]:
                if kw in t:
                    v = _s(resp).lower()
                    cur[col] = {'sí': 'si', 'si': 'si', 'no': 'no',
                                'na': 'na', 'n/a': 'na'}.get(v, v)
                    break
        return [oe for oe in ooee if oe.get('nombre_oe')]

    def _parse_nomenclaturas(self, bd):
        """Filas sueltas (número entero, texto de clasificación) → p24_nomenclaturas."""
        from indicadores.forms_iced import ICEDModuloD1Form
        cfg = ICEDModuloD1Form().fields['p24_nomenclaturas'].widget.attrs
        opciones = {o['texto'].strip().lower(): o['codigo']
                    for o in json.loads(cfg['data-config']).get('opciones', [])}
        # Solo filas de número entero DESPUÉS de la pregunta 42 (bloque final
        # de clasificaciones; las filas 6/7/33 son preguntas, no nomenclaturas)
        post42 = False
        datos = {}
        for num, preg, resp in bd.rows:
            if num == '42':
                post42 = True
                continue
            if not post42 or '.' in num or not preg or not _marc(resp):
                continue
            t = re.sub(r'\s+', '', preg.strip().lower())
            code = next((c for txt, c in opciones.items()
                         if re.sub(r'\s+', '', txt) == t), None)
            if code is None:  # match difuso: mismo prefijo de 25 chars
                code = next((c for txt, c in opciones.items()
                             if txt[:25] == t[:25]), None)
            if code is None:  # match difuso: similitud global
                import difflib
                mejor = max(
                    ((difflib.SequenceMatcher(None, t, txt).ratio(), c)
                     for txt, c in opciones.items()),
                    key=lambda x: x[0], default=(0, None))
                if mejor[0] >= 0.75:
                    code = mejor[1]
            if code:
                datos[code] = {'seleccion': True}
            else:
                self.stderr.write(f'  ⚠ Nomenclatura sin código: {preg[:60]}')
        return datos

    def _parse_rrhh(self, ws):
        """Hoja RRHH horizontal: encabezados en filas 18-20, datos desde 21.
        OJO: en read_only, ws.cell() re-parsea el XML completo por acceso —
        por eso las categorías (fila 20) se capturan en la misma iteración."""
        rows = list(ws.iter_rows(min_row=18, values_only=True))
        if len(rows) < 3:
            return []
        cat_row = [_s(v) for v in rows[2]] + [''] * 40  # fila 20: códigos de categoría
        personas = []
        for row in rows[3:]:
            vals = [_s(v) for v in row] + [''] * 40
            if not vals[3]:  # nombre completo
                continue
            # Vinculación: nombrado cols 8-18 (cat), contratista cols 19-23
            tipo, cat = '', ''
            for j in range(8, 19):
                if _marc(vals[j]):
                    tipo, cat = 'nombrado', cat_row[j]
                    break
            if not tipo:
                for j in range(19, 24):
                    if _marc(vals[j]):
                        tipo, cat = 'contratista', cat_row[j]
                        break
            etapas = [ETAPAS_ORDEN[j - 24] for j in range(24, 32) if _marc(vals[j])]
            nivel = next((NIVELES_ORDEN[j - 33] for j in range(33, 39)
                          if _marc(vals[j])), '')
            personas.append({
                'nombre_completo': vals[3],
                'grupo': vals[2],
                'correo': vals[4],
                'telefono': vals[5],
                'anios_experiencia': int(_num(vals[6]) or 0),
                'inicio_participacion': vals[7],
                'tipo_vinculacion': tipo,
                'categoria_cargo': _s(cat),
                'nivel_formacion': nivel,
                'etapas_proceso': etapas,
                'funciones_estadisticas': vals[32].lower() in ('si', 'sí', 'x'),
            })
        return personas

    # ------------------------------------------------------------------
    # Resultados / materialización / utilidades
    def _leer_resultados(self, path, form, calc):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb['A. Resultado global']
        dims = {'entorno': 'puntaje_b', 'infraestructura': 'puntaje_c',
                'metodología': 'puntaje_d', 'accesibilidad': 'puntaje_e'}
        for row in ws.iter_rows(values_only=True):
            nums = [x for x in row if isinstance(x, (int, float)) and x <= 1.5]
            if not nums:
                continue
            for v in row:
                t = _s(v).lower()
                if 'resultado del índice' in t or t == 'ri':
                    form.puntaje_global = Decimal(str(nums[-1]))
                    break
                for kw, campo in dims.items():
                    if t.startswith(kw):
                        # Ponderación, Obtenido, Ponderado → penúltimo = obtenido
                        if len(nums) >= 2:
                            setattr(form, campo, Decimal(str(nums[-2])))
                        break

        # Subdimensiones oficiales (hoja B) → sobreescriben el detalle calculado
        subdims = self._leer_subdimensiones(wb)
        if subdims and form.puntajes_detalle:
            det = form.puntajes_detalle
            det.setdefault('dimensiones', {}).update({
                '1': round(float(form.puntaje_b) * 100, 2),
                '2': round(float(form.puntaje_c) * 100, 2),
                '3': round(float(form.puntaje_d) * 100, 2),
                '4': round(float(form.puntaje_e) * 100, 2),
            })
            det.get('subdimensiones', {}).update(subdims)
            for dk, dinfo in det.get('detalle', {}).items():
                punt = det['dimensiones'].get(dk)
                if punt is not None:
                    dinfo['puntaje'] = punt
                for sk, sinfo in dinfo.get('subdimensiones', {}).items():
                    if sk in subdims:
                        sinfo['puntaje'] = subdims[sk]

        self.stdout.write(self.style.SUCCESS(
            f'  Puntajes Excel → B={form.puntaje_b} C={form.puntaje_c} '
            f'D={form.puntaje_d} E={form.puntaje_e} G={form.puntaje_global}'))
        self.stdout.write(
            f'  Calc. import → B={calc["puntaje_b"]} C={calc["puntaje_c"]} '
            f'D={calc["puntaje_d"]} E={calc["puntaje_e"]} G={calc["puntaje_global"]} (0-100)')

    def _leer_subdimensiones(self, wb):
        """Lee 'B. Resultado por dimensiones' → {sub_key: puntaje_0_100}."""
        from indicadores.calcular_iced import ESTRUCTURA_ICED
        nombre_a_key = {}
        for dk, dinfo in ESTRUCTURA_ICED.items():
            for sk, sinfo in dinfo['subdimensiones'].items():
                nombre_a_key[sk] = sinfo['nombre'].lower()
        ws = wb['B. Resultado por dimensiones']
        out = {}
        for row in ws.iter_rows(values_only=True):
            vals = [v for v in row]
            # La subdimensión está en col3 y el resultado en la última col numérica
            nums = [x for x in vals if isinstance(x, (int, float)) and x <= 1.5]
            if not nums:
                continue
            for v in vals:
                t = _s(v).lower()
                if not t or len(t) < 6:
                    continue
                for sk, nombre in nombre_a_key.items():
                    # match por primeras 2 palabras del nombre oficial
                    if ' '.join(nombre.split()[:2]) in t or ' '.join(t.split()[:2]) in nombre:
                        out[sk] = round(float(nums[-1]) * 100, 2)
        return out

    def _materializar_contactos(self, form):
        raw = (form.respuestas_a or {}).get('personas_contacto_json', '[]')
        try:
            personas = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except (ValueError, TypeError):
            personas = []
        form.personas_contacto.all().delete()
        for i, p in enumerate(personas):
            if not isinstance(p, dict) or not (p.get('nombre_completo') or '').strip():
                continue
            ICEDPersonaContacto.objects.create(
                formulario=form,
                nombre_completo=p['nombre_completo'][:255],
                cargo=(p.get('cargo') or '')[:150],
                correo=(p.get('correo') or '')[:254],
                telefono=(p.get('telefono') or '')[:20],
                orden=p.get('orden', i),
            )

    def _materializar_rrhh(self, form):
        raw = (form.respuestas_c or {}).get('p19_rrhh_list', '')
        try:
            personas = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except (ValueError, TypeError):
            personas = []
        form.recursos_humanos.all().delete()
        for p in personas:
            if not isinstance(p, dict) or not (p.get('nombre_completo') or '').strip():
                continue
            ICEDRecursoHumano.objects.create(
                formulario=form,
                nombre_completo=p['nombre_completo'][:200],
                correo=(p.get('correo') or '')[:254],
                telefono=(p.get('telefono') or '')[:20],
                grupo=(p.get('grupo') or '')[:100],
                anios_experiencia=max(0, int(p.get('anios_experiencia') or 0)),
                inicio_participacion=(p.get('inicio_participacion') or '')[:10],
                tipo_vinculacion=p.get('tipo_vinculacion') or 'contratista',
                categoria_cargo=(p.get('categoria_cargo') or '')[:5],
                nivel_formacion=(p.get('nivel_formacion') or '')[:5],
                etapas_proceso=p.get('etapas_proceso') or [],
                funciones_estadisticas=bool(p.get('funciones_estadisticas')),
            )

    def _buscar_organismo(self, nombre):
        """Match tolerante: sin tildes/case, espacios colapsados, difflib.
        Error explícito si hay empate entre candidatos."""
        import difflib
        import unicodedata
        from indicadores.models import Organismo

        def norm(t):
            t = unicodedata.normalize('NFD', t or '')
            t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
            return re.sub(r'\s+', ' ', t.lower()).strip()

        objetivo = norm(nombre)
        orgs = list(Organismo.objects.all())
        # Exacto normalizado
        hits = [o for o in orgs if norm(o.nombre) == objetivo]
        if len(hits) == 1:
            return hits[0]
        # Similitud
        scored = sorted(
            ((difflib.SequenceMatcher(None, objetivo, norm(o.nombre)).ratio(), o)
             for o in orgs),
            key=lambda x: -x[0])
        best, segundo = scored[0], scored[1]
        if best[0] >= 0.85 and best[0] - segundo[0] > 0.03:
            if objetivo != norm(best[1].nombre):
                self.stderr.write(
                    f'  ⚠ Organismo por similitud ({best[0]:.0%}): '
                    f'{nombre!r} → {best[1].nombre!r}')
            return best[1]
        candidatos = ', '.join(f'{o.pk}:{o.nombre} ({r:.0%})'
                               for r, o in scored[:3])
        raise CommandError(
            f'Organismo ambiguo/no encontrado: {nombre!r}. '
            f'Candidatos: {candidatos}. Use --organismo.')

    def _reporte(self, form, calc, created):
        n_pc = len(json.loads(form.respuestas_d.get('p23_operaciones_estadisticas') or '[]'))
        n_rr = len(json.loads(form.respuestas_c.get('p19_rrhh_list') or '[]'))
        n_mop = len(json.loads(form.respuestas_b.get('p7_estructura_mop') or '[]'))
        self.stdout.write(self.style.SUCCESS(
            f'\n{"CREADO" if created else "ACTUALIZADO"}: {form}\n'
            f'  OOEE: {n_pc} | RRHH: {n_rr} | MOP filas: {n_mop}\n'
            f'  Puntajes: B={form.puntaje_b} C={form.puntaje_c} '
            f'D={form.puntaje_d} E={form.puntaje_e} Global={form.puntaje_global}\n'
            f'  Nivel: {form.nivel_global_display}'))
