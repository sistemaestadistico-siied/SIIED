"""
Importa el dump MySQL `pet_catalogo.sql` (catálogo de variables del antiguo
portal de planestadistico.cali.gov.co) a los modelos CV* del SIIED.

Uso:
    python manage.py importar_catalogo_variables ../pet_catalogo.sql
    python manage.py importar_catalogo_variables ../pet_catalogo.sql --fresh

`--fresh` borra previamente todas las tablas CV* (en orden FK-seguro).
El parser entiende el formato mysqldump (VALUES con escapes \' \\ \n \r \t,
NULL y tuplas separadas por comas), suficiente para este dump.
"""

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from indicadores.models import (
    CVAreaInformacion, CVUnidadAnalisis, CVTipoDato, CVTipoVariableEstadistica,
    CVTipoValoresDominio, CVGeografia, CVVariable, CVValor, CVNoticia,
)


INSERT_LINE_RE = re.compile(
    r"^INSERT INTO `?(?P<table>\w+)`?(?: \((?P<cols>[^)]+)\))? VALUES (?P<values>.*);?\s*$"
)

CREATE_RE = re.compile(
    r"CREATE TABLE `?(?P<table>\w+)`? \((?P<body>.*?)\)\s*ENGINE",
    re.DOTALL,
)

COL_DEF_RE = re.compile(r"^\s*`(?P<col>\w+)`", re.MULTILINE)


def _unescape(s: str) -> str:
    """Decodifica las secuencias de escape de mysqldump."""
    return (s.replace('\\\\', '\\')
             .replace("\\'", "'")
             .replace('\\"', '"')
             .replace('\\n', '\n')
             .replace('\\r', '\r')
             .replace('\\t', '\t')
             .replace('\\0', '\0'))


def _parse_values(blob: str):
    """Itera sobre las tuplas de un bloque VALUES de mysqldump."""
    i, n = 0, len(blob)
    while i < n:
        # localizar paréntesis de apertura de tupla
        while i < n and blob[i] != '(':
            i += 1
        if i >= n:
            break
        i += 1
        row, field, in_str = [], [], False
        while i < n:
            ch = blob[i]
            if in_str:
                if ch == '\\' and i + 1 < n:
                    field.append(blob[i:i + 2])
                    i += 2
                    continue
                if ch == "'":
                    in_str = False
                else:
                    field.append(ch)
                i += 1
                continue
            if ch == "'":
                in_str = True
            elif ch in (',', ')'):
                token = ''.join(field).strip() if field else ''
                row.append(None if field == [] or token.upper() == 'NULL' else token)
                field = []
                if ch == ')':
                    i += 1
                    break
            else:
                field.append(ch)
            i += 1
        # decodificar escapes solo en valores string (los que llevaron comillas
        # ya llegan sin ellas; distinguir no es necesario porque el token raw
        # numérico no contiene backslashes en este dump)
        yield [_unescape(v) if isinstance(v, str) else v for v in row]


def _parse_dump(path: str):
    """Devuelve {tabla: [dict(col=valor), ...]} del dump."""
    with open(path, encoding='utf-8', errors='replace') as fh:
        text = fh.read()

    # Orden de columnas por tabla (los INSERT de este dump no las declaran)
    table_cols = {
        m.group('table'): COL_DEF_RE.findall(m.group('body'))
        for m in CREATE_RE.finditer(text)
    }

    data = {}
    for line in text.splitlines():
        m = INSERT_LINE_RE.match(line)
        if not m:
            continue
        table = m.group('table')
        if m.group('cols'):
            cols = [c.strip().strip('`') for c in m.group('cols').split(',')]
        else:
            cols = table_cols.get(table)
            if not cols:
                continue
        rows = [
            dict(zip(cols, tup))
            for tup in _parse_values(m.group('values'))
        ]
        data.setdefault(table, []).extend(rows)
    return data


class Command(BaseCommand):
    help = 'Importa el dump pet_catalogo.sql a los modelos CV* del SIIED'

    def add_arguments(self, parser):
        parser.add_argument('dump_path', type=str, help='Ruta al pet_catalogo.sql')
        parser.add_argument(
            '--fresh', action='store_true',
            help='Borra los datos CV* existentes antes de importar')

    @transaction.atomic
    def handle(self, dump_path, fresh, **opts):
        try:
            data = _parse_dump(dump_path)
        except FileNotFoundError:
            raise CommandError(f'No se encontró el dump: {dump_path}')

        esperadas = {
            'areas_informacion', 'geografias', 'noticias', 'tipos_datos',
            'tipos_valores_dominio', 'tipos_variables_estadisticas',
            'unidades_analisis', 'valores', 'variables',
        }
        faltantes = esperadas - set(data)
        if faltantes:
            raise CommandError(f'Tablas sin INSERT en el dump: {sorted(faltantes)}')

        if fresh:
            self.stdout.write('Limpiando tablas CV*...')
            CVValor.objects.all().delete()
            CVVariable.objects.all().delete()
            for m in (CVGeografia, CVNoticia, CVTipoDato, CVTipoValoresDominio,
                      CVTipoVariableEstadistica, CVUnidadAnalisis, CVAreaInformacion):
                m.objects.all().delete()

        # --- Tablas de referencia (sin dependencias) ---
        areas = {}
        for r in data['areas_informacion']:
            obj = CVAreaInformacion(
                id_area=int(r['id_area']),
                nombre_area=r['nombre_area'],
                descripcion_area=r['descripcion_area'] or '',
            )
            obj.save()
            areas[obj.id_area] = obj
        self.stdout.write(f'  areas_informacion: {len(areas)}')

        unidades = {}
        for r in data['unidades_analisis']:
            obj = CVUnidadAnalisis(
                id_unidad_analisis=int(r['id_unidad_analisis']),
                nombre_unidad_analisis=r['nombre_unidad_analisis'],
            )
            obj.save()
            unidades[obj.id_unidad_analisis] = obj
        self.stdout.write(f'  unidades_analisis: {len(unidades)}')

        tipos_datos = {}
        for r in data['tipos_datos']:
            obj = CVTipoDato(
                id_tipo_dato=int(r['id_tipo_dato']),
                nombre_tipo_dato=r['nombre_tipo_dato'],
            )
            obj.save()
            tipos_datos[obj.id_tipo_dato] = obj
        self.stdout.write(f'  tipos_datos: {len(tipos_datos)}')

        tipos_variables = {}
        for r in data['tipos_variables_estadisticas']:
            obj = CVTipoVariableEstadistica(
                id_tipo_variable=int(r['id_tipo_variable']),
                nombre_tipo_variable=r['nombre_tipo_variable'],
            )
            obj.save()
            tipos_variables[obj.id_tipo_variable] = obj
        self.stdout.write(f'  tipos_variables_estadisticas: {len(tipos_variables)}')

        tipos_valores = {}
        for r in data['tipos_valores_dominio']:
            obj = CVTipoValoresDominio(
                id_tipo_valores_dominio=int(r['id_tipo_valores_dominio']),
                nombre_tipo_valores_dominio=r['nombre_tipo_valores_dominio'],
                longitud_tipo_valores_dominio=int(r['longitud_tipo_valores_dominio'] or 0),
            )
            obj.save()
            tipos_valores[obj.id_tipo_valores_dominio] = obj
        self.stdout.write(f'  tipos_valores_dominio: {len(tipos_valores)}')

        geografias = [
            CVGeografia(
                id_geografia=int(r['id_geografia']),
                tipo_geografia=r['tipo_geografia'] or '',
                codigo_geografia=int(r['codigo_geografia']),
                geografia_padre=r['geografia_padre'] or '',
                nombre_geografia=r['nombre_geografia'] or '',
            )
            for r in data['geografias']
        ]
        CVGeografia.objects.bulk_create(geografias)
        self.stdout.write(f'  geografias: {len(geografias)}')

        noticias = []
        for r in data['noticias']:
            noticias.append(CVNoticia(
                id_noticia=int(r['idNoticia']),
                titulo_noticia=r['tituloNoticia'] or '',
                anho_noticia=int(r['anhoNoticia']) if r['anhoNoticia'] else None,
                fecha_noticia=r['fechaNoticia'] or None,
                texto_noticia=r['textoNoticia'] or '',
                carpeta_imagenes_noticia=r['carpetaImagenesNoticia'] or '',
                imagenes_noticia=r['imagenesNoticia'],
            ))
        CVNoticia.objects.bulk_create(noticias)
        self.stdout.write(f'  noticias: {len(noticias)}')

        # --- Variables (FKs a las tablas anteriores) ---
        omitidas = []
        creadas = 0
        for r in data['variables']:
            try:
                CVVariable(
                    id_variable=r['id_variable'],
                    nombre=r['nombre'] or '',
                    descripcion=r['descripcion'] or '',
                    unidad_analisis=unidades.get(int(r['id_unidad_analisis'] or 0)),
                    tipo_dato=tipos_datos.get(int(r['id_tipo_dato'] or 0)),
                    tipo_variable_estadistica=tipos_variables.get(int(r['id_tipo_variable_estadistica'] or 0)),
                    area_informacion=areas.get(int(r['id_area_informacion'] or 0)),
                    tipo_valores=tipos_valores.get(int(r['id_tipo_valores'])) if r['id_tipo_valores'] else None,
                    llave_primaria=r['llave_primaria'] or '',
                    campo_obligatorio=r['campo_obligatorio'] or '',
                    longitud_campo=r['longitud_campo'] or '',
                    reglas_consistencia=r['reglas_consistencia'] or '',
                    reglas_validacion_lenguaje_natural=r['reglas_validacion_lenguaje_natural'] or '',
                    forma_pregunta=r['forma_pregunta'] or '',
                    opciones_respuesta=r['opciones_respuesta'] or '',
                ).save()
                creadas += 1
            except (KeyError, ValueError) as exc:
                omitidas.append((r['id_variable'], str(exc)))
        self.stdout.write(f'  variables: {creadas}')
        for vid, motivo in omitidas:
            self.stdout.write(self.style.WARNING(
                f'  variable omitida {vid}: {motivo}'))

        # --- Valores de dominio ---
        ids_variables = set(CVVariable.objects.values_list('id_variable', flat=True))
        valores, valores_omitidos = [], 0
        for r in data['valores']:
            vid = r['id_variable']
            if vid not in ids_variables:
                valores_omitidos += 1
                continue
            valores.append(CVValor(
                id_valor=int(r['id_valor']),
                descripcion_valor=r['descripcion_valor'] or '',
                variable_id=vid,
            ))
        CVValor.objects.bulk_create(valores)
        self.stdout.write(f'  valores: {len(valores)}')
        if valores_omitidos:
            self.stdout.write(self.style.WARNING(
                f'  valores omitidos (variable inexistente): {valores_omitidos}'))

        self.stdout.write(self.style.SUCCESS('Importación completada.'))
