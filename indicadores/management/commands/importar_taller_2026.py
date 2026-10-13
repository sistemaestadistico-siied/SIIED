"""Importa los datos del taller de gestión de datos institucionales 2026 desde el proyecto `formulario/` (SQLite).

Uso:
    python manage.py importar_taller_2026 [--sqlite /ruta/a/db.sqlite3]

Qué hace:
  1. Replica el catálogo de OpcionTaller (conserva pks para las tablas M2M).
  2. Reconcilia organismos/suborganismos del organigrama oficial contra las
     tablas Organismo/Suborganismo del SIIED (por codigo_organigrama o nombre
     normalizado; crea los que falten — el organigrama es la fuente de verdad).
  3. Migra todos los usuarios del taller como User + PerfilRecolector rol
     'delegado' (el hash de password pbkdf2 de Django es portable entre
     SQLite y PostgreSQL, se copia tal cual).
  4. Normaliza `equipo_responsable` (texto) hacia EquipoOrganismo.
  5. Copia InscripcionTaller + FuenteDatos (F1) + RetoAnalisis/FuenteRequerida
     (F2) + EvaluacionSeguridad (F3), incluidas las relaciones M2M.
  6. Carga las BASES del catálogo de datos (antes hardcodeadas en
     formulario/taller/catalogo_data.py) a BaseCatalogo/CampoCatalogo.

Idempotente: las inscripciones se identifican por uuid; correr dos veces
no duplica.
"""

import importlib.util
import re
import sqlite3
import unicodedata
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import slugify

from indicadores.models import (
    Organismo, Suborganismo, EquipoOrganismo, PerfilRecolector,
)
from indicadores.models_taller import (
    OpcionTaller, InscripcionTaller, RetoAnalisis, FuenteRequerida,
)
from indicadores.models_catalogo import (
    FuenteDatos, FuenteOrigen, VariableFuente, EvaluacionSeguridad,
    BaseCatalogo, CampoCatalogo,
)

DEFAULT_DB = Path('/home/amiranda/Descargas/SIIED/formulario/db.sqlite3')
CATALOGO_DATA = Path('/home/amiranda/Descargas/SIIED/formulario/taller/catalogo_data.py')

# Tabla M2M sqlite -> nombre del campo en el modelo nuevo
M2M_FUENTE = {
    'taller_fuentedatos_relaciones': 'relaciones',
    'taller_fuentedatos_instrumentos': 'instrumentos',
    'taller_fuentedatos_mecanismos': 'mecanismos',
    'taller_fuentedatos_periodicidades': 'periodicidades',
    'taller_fuentedatos_desagregaciones': 'desagregaciones',
    'taller_fuentedatos_unidades_analisis': 'unidades_analisis',
    'taller_fuentedatos_niveles_georref': 'niveles_georref',
    'taller_fuentedatos_problemas_calidad': 'problemas_calidad',
}
M2M_RETO = {
    'taller_retoanalisis_unidades_relacionar': 'unidades_relacionar',
    'taller_retoanalisis_desagregaciones': 'desagregaciones',
    'taller_retoanalisis_tratamientos': 'tratamientos',
    'taller_retoanalisis_resultados_mvp': 'resultados_mvp',
    'taller_retoanalisis_capacidades_sipdi': 'capacidades_sipdi',
    'taller_retoanalisis_enfoques_diferenciales': 'enfoques_diferenciales',
}
M2M_SEGURIDAD = {
    'taller_evaluacionseguridad_variables_identificadoras': 'variables_identificadoras',
    'taller_evaluacionseguridad_datos_sensibles': 'datos_sensibles',
    'taller_evaluacionseguridad_medidas_proteccion': 'medidas_proteccion',
}

TIPO_SUB_MAP = {
    'subdireccion': 'subdireccion',
    'subsecretaria': 'subsecretaria',
    'oficina': 'oficina',
    'unidad de apoyo a la gestion': 'unidad_apoyo',
    'despacho': 'despacho',
    'contaduria': 'contaduria',
    'centros cali agrupacion': 'centros_cali',
}

TIPO_ORG_MAP = {
    'secretaria': 'secretaria',
    'departamento administrativo': 'departamento_administrativo',
    'unidad administrativa especial': 'unidad_administrativa_especial',
    'entidad descentralizada': 'entidad_descentralizada',
}

# Alias nombre-organigrama -> nombre-SIIED para coincidencias que la
# normalización simple no resuelve.
ALIAS_ORGANISMO = {
    'alcaldia santiago cali': 'alcaldia de santiago de cali',
}

# Alias para custodios de bases del catálogo (nombres cortos/externos
# del data lake -> Organismo SIIED normalizado)
ALIAS_BASE_ORG = {
    'dap': 'departamento administrativo planeacion municipal',
    'idesc': 'departamento administrativo planeacion municipal',
    'secretaria planeacion': 'departamento administrativo planeacion municipal',
    'secretaria salud': 'secretaria salud publica',
    'secretaria bienestar social': 'secretaria bienestar social',
}


def norm(texto):
    """Normaliza un nombre para comparación: sin tildes, minúsculas, sin ruido."""
    if not texto:
        return ''
    s = unicodedata.normalize('NFKD', texto)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    s = re.sub(r'\b(de|del|la|el|los|las|en|y|e|o|para|al)\b', ' ', s)
    return ' '.join(s.split())


def dt(valor):
    if not valor:
        return None
    d = parse_datetime(str(valor))
    if d and timezone.is_naive(d):
        d = timezone.make_aware(d)
    return d


def df(valor):
    if not valor:
        return None
    return parse_date(str(valor)[:10])


class Command(BaseCommand):
    help = 'Importa los datos del taller de gestión de datos institucionales 2026 (formulario/db.sqlite3) al SIIED'

    def add_arguments(self, parser):
        parser.add_argument('--sqlite', default=str(DEFAULT_DB),
                            help='Ruta al db.sqlite3 del proyecto formulario')

    def handle(self, *args, **options):
        db_path = Path(options['sqlite'])
        if not db_path.exists():
            raise CommandError(f'No existe la base SQLite: {db_path}')

        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.warn = []
        self.fuente_map = {}  # sqlite fuente_id -> FuenteDatos

        self.importar_opciones()
        org_map = self.reconciliar_organismos()
        sub_map = self.reconciliar_suborganismos(org_map)
        equipo_map = {}  # (suborganismo_id, norm) -> EquipoOrganismo
        user_map = self.importar_usuarios(org_map)
        insc_map = self.importar_inscripciones(org_map, sub_map, equipo_map, user_map)
        self.importar_fuentes(insc_map)
        self.importar_retos(insc_map)
        self.importar_seguridad(insc_map)
        self.importar_bases_catalogo()

        self.stdout.write(self.style.SUCCESS('\n=== RESUMEN ==='))
        for label, model in [
            ('Opciones de catálogo', OpcionTaller),
            ('Inscripciones taller', InscripcionTaller),
            ('Fuentes de datos (F1)', FuenteDatos),
            ('Retos de análisis (F2)', RetoAnalisis),
            ('Evaluaciones de seguridad (F3)', EvaluacionSeguridad),
            ('Bases del catálogo', BaseCatalogo),
            ('Campos del catálogo', CampoCatalogo),
        ]:
            self.stdout.write(f'  {label}: {model.objects.count()}')

        if self.warn:
            self.stdout.write(self.style.WARNING('\n=== ADVERTENCIAS ==='))
            for w in self.warn:
                self.stdout.write(f'  - {w}')

    # ------------------------------------------------------------------
    def rows(self, tabla):
        return list(self.conn.execute(f'SELECT * FROM {tabla}'))

    # ------------------------------------------------------------------
    def importar_opciones(self):
        """Copia taller_opcion conservando el pk (las M2M referencian por id)."""
        existentes = set(OpcionTaller.objects.values_list('id', flat=True))
        nuevas = []
        for r in self.rows('taller_opcion'):
            if r['id'] in existentes:
                continue
            nuevas.append(OpcionTaller(
                id=r['id'], categoria=r['categoria'], etiqueta=r['etiqueta'],
                orden=r['orden'], activa=bool(r['activa']),
            ))
        OpcionTaller.objects.bulk_create(nuevas)
        self.stdout.write(f'Opciones: {len(nuevas)} nuevas, {len(existentes)} ya existían')

    # ------------------------------------------------------------------
    def _norm_index(self, qs, campo='nombre'):
        idx = {}
        for obj in qs:
            idx.setdefault(norm(getattr(obj, campo)), []).append(obj)
        return idx

    def reconciliar_organismos(self):
        org_idx = self._norm_index(Organismo.objects.all())
        por_codigo = {o.codigo_organigrama: o for o in Organismo.objects.all() if o.codigo_organigrama}
        org_map = {}

        for r in self.rows('taller_organismo'):
            codigo = r['id_organismo']
            tipo_txt = norm(r['tipo'])
            tipo = TIPO_ORG_MAP.get(tipo_txt, 'otro')
            nombre = r['nombre']
            clave = ALIAS_ORGANISMO.get(norm(nombre), norm(nombre))

            org = por_codigo.get(codigo) or (org_idx.get(clave) or [None])[0]
            if org:
                cambios = []
                if org.codigo_organigrama != codigo:
                    org.codigo_organigrama = codigo
                    cambios.append('codigo_organigrama')
                if not org.tipo_organigrama:
                    org.tipo_organigrama = tipo
                    cambios.append('tipo_organigrama')
                if r['nombre_menu'] and not org.nombre_menu:
                    org.nombre_menu = r['nombre_menu']
                    cambios.append('nombre_menu')
                if cambios:
                    org.save(update_fields=cambios)
                self.stdout.write(f'  Org {codigo} reconciliado: {org.nombre}')
            else:
                slug = slugify(nombre)[:90] or f'org-{codigo.lower()}'
                base, i = slug, 2
                while Organismo.objects.filter(codigo=slug).exists():
                    slug = f'{base}-{i}'
                    i += 1
                org = Organismo.objects.create(
                    nombre=nombre, codigo=slug, activo=True,
                    codigo_organigrama=codigo, tipo_organigrama=tipo,
                    nombre_menu=r['nombre_menu'] or '',
                )
                self.warn.append(f'Organismo creado (no existía en SIIED): {nombre}')

            org_map[r['id']] = org
            org_idx.setdefault(norm(nombre), []).append(org)

        self.stdout.write(f'Organismos reconciliados: {len(org_map)}')
        return org_map

    # ------------------------------------------------------------------
    def reconciliar_suborganismos(self, org_map):
        sub_idx = {}
        for s in Suborganismo.objects.select_related('organismo'):
            sub_idx.setdefault((s.organismo_id, norm(s.nombre)), s)
        por_codigo = {s.codigo_organigrama: s for s in Suborganismo.objects.all()
                      if s.codigo_organigrama}
        sub_map = {}

        for r in self.rows('taller_suborganismo'):
            org = org_map.get(r['organismo_id'])
            if not org:
                self.warn.append(f'Suborganismo {r["id_dependencia"]} sin organismo mapeado')
                continue

            codigo = r['id_dependencia']
            tipo = TIPO_SUB_MAP.get(norm(r['tipo']), 'otro')
            nombre = r['nombre']

            sub = por_codigo.get(codigo) or sub_idx.get((org.id, norm(nombre)))
            if sub:
                if sub.codigo_organigrama != codigo:
                    sub.codigo_organigrama = codigo
                    sub.save(update_fields=['codigo_organigrama'])
            else:
                slug = slugify(nombre)[:90] or f'sub-{codigo.lower()}'
                base, i = slug, 2
                while Suborganismo.objects.filter(organismo=org, codigo=slug).exists():
                    slug = f'{base}-{i}'
                    i += 1
                orden = (Suborganismo.objects.filter(organismo=org)
                         .order_by('-orden').values_list('orden', flat=True).first() or 0) + 1
                sub = Suborganismo.objects.create(
                    organismo=org, nombre=nombre[:200], codigo=slug,
                    tipo=tipo, activo=True, orden=orden,
                    codigo_organigrama=codigo,
                )
                self.warn.append(f'Suborganismo creado: {org.nombre} / {nombre}')

            sub_map[r['id']] = sub
            sub_idx[(org.id, norm(nombre))] = sub

        self.stdout.write(f'Suborganismos reconciliados: {len(sub_map)}')
        return sub_map

    # ------------------------------------------------------------------
    def _equipo(self, equipo_map, suborganismo, texto):
        """Devuelve EquipoOrganismo normalizado para el texto digitado."""
        clave = (suborganismo.id if suborganismo else None, norm(texto))
        if not texto or not suborganismo:
            return None
        if clave in equipo_map:
            return equipo_map[clave]

        nombre = ' '.join(texto.split()).strip()
        eq = EquipoOrganismo.objects.filter(
            suborganismo=suborganismo,
            nombre__iexact=nombre,
        ).first()
        if not eq:
            candidatos = {norm(e.nombre): e for e in suborganismo.equipos.all()}
            eq = candidatos.get(norm(nombre))
        if not eq:
            slug = slugify(nombre)[:90] or 'equipo'
            base, i = slug, 2
            while EquipoOrganismo.objects.filter(suborganismo=suborganismo, codigo=slug).exists():
                slug = f'{base}-{i}'
                i += 1
            eq = EquipoOrganismo.objects.create(
                suborganismo=suborganismo, nombre=nombre[:200], codigo=slug)
            self.warn.append(f'Equipo creado: {suborganismo.nombre} / {nombre}')

        equipo_map[clave] = eq
        return eq

    # ------------------------------------------------------------------
    def importar_usuarios(self, org_map):
        """Todos los usuarios del taller -> User + PerfilRecolector rol delegado."""
        # organismo por usuario desde su primera inscripción
        org_por_user = {}
        for r in self.conn.execute(
                'SELECT DISTINCT user_id, organismo_id FROM taller_inscripcion WHERE user_id IS NOT NULL'):
            org_por_user.setdefault(r['user_id'], r['organismo_id'])

        user_map = {}
        creados = 0
        for r in self.rows('auth_user'):
            user = User.objects.filter(username=r['username']).first()
            if not user:
                user = User.objects.create(
                    username=r['username'],
                    email=r['email'] or '',
                    first_name=r['first_name'] or '',
                    last_name=r['last_name'] or '',
                    is_staff=bool(r['is_staff']),
                    is_superuser=bool(r['is_superuser']),
                    is_active=bool(r['is_active']),
                )
                # El hash pbkdf2 de Django es portable: se copia tal cual
                user.password = r['password']
                user.save(update_fields=['password'])
                if r['last_login']:
                    User.objects.filter(pk=user.pk).update(last_login=dt(r['last_login']))
                if r['date_joined']:
                    User.objects.filter(pk=user.pk).update(date_joined=dt(r['date_joined']))
                creados += 1

            org = org_map.get(org_por_user.get(r['id']))
            perfil, _ = PerfilRecolector.objects.get_or_create(
                user=user,
                defaults={
                    'rol': 'delegado',
                    'institucion': org.nombre if org else 'Alcaldía de Santiago de Cali',
                    'organismo': org,
                    'activo': True,
                },
            )
            if perfil.rol != 'delegado' and not perfil.user.is_staff:
                perfil.rol = 'delegado'
                if org and not perfil.organismo:
                    perfil.organismo = org
                perfil.save()

            user_map[r['id']] = user

        self.stdout.write(f'Usuarios: {creados} creados, {len(user_map) - creados} existentes')
        return user_map

    # ------------------------------------------------------------------
    def importar_inscripciones(self, org_map, sub_map, equipo_map, user_map):
        insc_map = {}
        creadas = 0
        for r in self.rows('taller_inscripcion'):
            existente = InscripcionTaller.objects.filter(uuid=r['uuid']).first()
            if existente:
                insc_map[r['id']] = existente
                continue

            org = org_map.get(r['organismo_id'])
            if not org:
                self.warn.append(f'Inscripción {r["id"]} sin organismo mapeado, omitida')
                continue
            sub = sub_map.get(r['suborganismo_id'])
            equipo = self._equipo(equipo_map, sub, r['equipo_responsable'])

            ins = InscripcionTaller.objects.create(
                uuid=r['uuid'],
                user=user_map.get(r['user_id']),
                estado=r['estado'],
                ficha_inicial=r['ficha_inicial'] or 'f1',
                paso_actual=r['paso_actual'] or '',
                organismo=org,
                suborganismo=sub,
                equipo=equipo,
                equipo_responsable=r['equipo_responsable'] or '',
                nombre_completo=r['nombre_completo'] or '',
                correo=r['correo'] or '',
                telefono=r['telefono'] or '',
            )
            # auto_now/auto_now_add no respetan el valor original en create()
            InscripcionTaller.objects.filter(pk=ins.pk).update(
                creado=dt(r['creado']), actualizado=dt(r['actualizado']))
            insc_map[r['id']] = ins
            creadas += 1

        self.stdout.write(f'Inscripciones: {creadas} creadas, {len(insc_map) - creadas} existentes')
        return insc_map

    # ------------------------------------------------------------------
    def _set_m2m(self, tabla, col_owner, col_opcion, objetos, campo):
        """Copia relaciones M2M preservando ids de opciones."""
        relaciones = {}
        for r in self.conn.execute(f'SELECT {col_owner}, {col_opcion} FROM {tabla}'):
            relaciones.setdefault(r[col_owner], []).append(r[col_opcion])
        for owner_id, opciones in relaciones.items():
            obj = objetos.get(owner_id)
            if obj is not None:
                getattr(obj, campo).set(opciones)

    def importar_fuentes(self, insc_map):
        # Las filas sqlite pueden repetir (inscripción, nombre) — se
        # reconcilian por índice de ocurrencia para no perder duplicados.
        ocurrencias = {}
        for r in self.conn.execute('SELECT * FROM taller_fuentedatos ORDER BY id'):
            ins = insc_map.get(r['inscripcion_id'])
            if not ins:
                continue
            key = (ins.pk, r['nombre'][:200])
            n = ocurrencias.get(key, 0)
            ocurrencias[key] = n + 1
            existentes = list(FuenteDatos.objects.filter(
                inscripcion=ins, nombre=r['nombre'][:200]).order_by('id'))
            if n < len(existentes):
                f = existentes[n]
            else:
                f = None
            if f is None:
                f = FuenteDatos.objects.create(
                    inscripcion=ins,
                    nombre=r['nombre'][:200],
                    descripcion=r['descripcion'] or '',
                    relacion_otra=r['relacion_otra'] or '',
                    instrumento_otro=r['instrumento_otro'] or '',
                    mecanismo_otro=r['mecanismo_otro'] or '',
                    fecha_inicio=df(r['fecha_inicio']),
                    fecha_actualizacion=df(r['fecha_actualizacion']),
                    periodicidad_otra=r['periodicidad_otra'] or '',
                    desagregacion_otra=r['desagregacion_otra'] or '',
                    num_registros=r['num_registros'],
                    num_registros_fecha=df(r['num_registros_fecha']),
                    num_registros_desconocido=bool(r['num_registros_desconocido']),
                    tiene_diccionario=r['tiene_diccionario'] or '',
                    diccionario_ubicacion=r['diccionario_ubicacion'] or '',
                    archivo_diccionario=r['archivo_diccionario'] or None,
                    rol=r['rol'] or '',
                    decisiones_apoya=r['decisiones_apoya'] or '',
                    unidad_analisis_otra=r['unidad_analisis_otra'] or '',
                    georreferenciacion=r['georreferenciacion'] or '',
                    nivel_georref_otro=r['nivel_georref_otro'] or '',
                    problema_calidad_otro=r['problema_calidad_otro'] or '',
                    tiene_validacion=r['tiene_validacion'] or '',
                    validacion_descripcion=r['validacion_descripcion'] or '',
                )
            self.fuente_map[r['id']] = f

        for tabla, campo in M2M_FUENTE.items():
            self._set_m2m(tabla, 'fuentedatos_id', 'opcion_id', self.fuente_map, campo)

        n_origen = n_var = 0
        for r in self.rows('taller_fuenteorigen'):
            f = self.fuente_map.get(r['fuente_id'])
            if f:
                _, c = FuenteOrigen.objects.get_or_create(
                    fuente=f, nombre=r['nombre'][:200],
                    defaults={'organismo_productor': r['organismo_productor'] or ''})
                n_origen += c
        for r in self.rows('taller_variablefuente'):
            f = self.fuente_map.get(r['fuente_id'])
            if f:
                _, c = VariableFuente.objects.get_or_create(
                    fuente=f, nombre=r['nombre'][:120],
                    defaults={
                        'tipo': r['tipo'] or 'texto',
                        'descripcion': r['descripcion'] or '',
                        'es_identificador': bool(r['es_identificador']),
                    })
                n_var += c

        self.stdout.write(f'Fuentes F1: {len(self.fuente_map)} | orígenes: {n_origen} | variables: {n_var}')

    # ------------------------------------------------------------------
    def importar_retos(self, insc_map):
        r_map = {}
        for r in self.rows('taller_retoanalisis'):
            ins = insc_map.get(r['inscripcion_id'])
            if not ins or hasattr(ins, 'reto'):
                continue
            reto = RetoAnalisis.objects.create(
                inscripcion=ins,
                nombre=r['nombre'][:250],
                analisis_propuesto=r['analisis_propuesto'] or '',
                resultado_esperado=r['resultado_esperado'] or '',
                decision_apoya=r['decision_apoya'] or '',
                unidad_principal_id=r['unidad_principal_id'],
                unidad_principal_otra=r['unidad_principal_otra'] or '',
                unidades_relacionar_otra=r['unidades_relacionar_otra'] or '',
                vinculo_unidades=r['vinculo_unidades'] or '',
                desagregacion_otra=r['desagregacion_otra'] or '',
                tratamiento_otro=r['tratamiento_otro'] or '',
                resultado_mvp_otro=r['resultado_mvp_otro'] or '',
                capacidad_sipdi_otra=r['capacidad_sipdi_otra'] or '',
                variables_enriquecer=r['variables_enriquecer'] or '',
                variables_enriquecer_otro=r['variables_enriquecer_otro'] or '',
                usuario_resultado=r['usuario_resultado'] or '',
                enfoque_diferencial_otro=r['enfoque_diferencial_otro'] or '',
            )
            r_map[r['id']] = reto

        for tabla, campo in M2M_RETO.items():
            self._set_m2m(tabla, 'retoanalisis_id', 'opcion_id', r_map, campo)

        n_fr = 0
        for r in self.rows('taller_fuenterequerida'):
            reto = r_map.get(r['reto_id'])
            if reto:
                _, c = FuenteRequerida.objects.get_or_create(
                    reto=reto, nombre=r['nombre'][:200],
                    defaults={
                        'organismo': r['organismo'] or '',
                        'variables': r['variables'] or '',
                        'llave_relacion': r['llave_relacion'] or '',
                    })
                n_fr += c

        self.stdout.write(f'Retos F2: {len(r_map)} | fuentes requeridas: {n_fr}')

    # ------------------------------------------------------------------
    def importar_seguridad(self, insc_map):
        e_map = {}
        for r in self.rows('taller_evaluacionseguridad'):
            fuente = self.fuente_map.get(r['fuente_id'])
            if not fuente or hasattr(fuente, 'seguridad'):
                continue
            ev = EvaluacionSeguridad.objects.create(
                fuente=fuente,
                contiene_datos_personales=r['contiene_datos_personales'] or '',
                variable_identificadora_otra=r['variable_identificadora_otra'] or '',
                dato_sensible_otro=r['dato_sensible_otro'] or '',
                base_legitima=r['base_legitima'] or '',
                base_legitima_porque=r['base_legitima_porque'] or '',
                proveedor_base_legitima=r['proveedor_base_legitima'] or '',
                proveedor_base_legitima_porque=r['proveedor_base_legitima_porque'] or '',
                finalidad_especifica=r['finalidad_especifica'] or '',
                finalidad_especifica_porque=r['finalidad_especifica_porque'] or '',
                datos_necesarios=r['datos_necesarios'] or '',
                datos_necesarios_porque=r['datos_necesarios_porque'] or '',
                conservacion_limitada=r['conservacion_limitada'] or '',
                conservacion_limitada_porque=r['conservacion_limitada_porque'] or '',
                salvaguardas=r['salvaguardas'] or '',
                salvaguardas_porque=r['salvaguardas_porque'] or '',
                transparencia=r['transparencia'] or '',
                transparencia_porque=r['transparencia_porque'] or '',
                riesgos_publicacion=r['riesgos_publicacion'] or '',
                riesgos_publicacion_porque=r['riesgos_publicacion_porque'] or '',
                terceros_estandares=r['terceros_estandares'] or '',
                terceros_estandares_porque=r['terceros_estandares_porque'] or '',
                riesgo_dano=r['riesgo_dano'] or '',
                riesgo_dano_porque=r['riesgo_dano_porque'] or '',
                medida_proteccion_otra=r['medida_proteccion_otra'] or '',
                susceptible_fraude=r['susceptible_fraude'] or '',
                organismo_custodio=r['organismo_custodio'] or '',
                confidencialidad=r['confidencialidad'] or '',
                integridad=r['integridad'] or '',
                disponibilidad=r['disponibilidad'] or '',
                aplica_publica=r['aplica_publica'] or '',
                aplica_semiprivada=r['aplica_semiprivada'] or '',
                aplica_privada=r['aplica_privada'] or '',
                aplica_sensible=r['aplica_sensible'] or '',
                aplica_reservada=r['aplica_reservada'] or '',
            )
            e_map[r['id']] = ev

        for tabla, campo in M2M_SEGURIDAD.items():
            self._set_m2m(tabla, 'evaluacionseguridad_id', 'opcion_id', e_map, campo)

        self.stdout.write(f'Evaluaciones F3: {len(e_map)}')

    # ------------------------------------------------------------------
    def importar_bases_catalogo(self):
        """Carga las bases del data lake (antes catalogo_data.py hardcodeado)."""
        if not CATALOGO_DATA.exists():
            self.warn.append(f'No se encontró {CATALOGO_DATA}; se omite importación de BASES')
            return

        spec = importlib.util.spec_from_file_location('catalogo_data_taller', CATALOGO_DATA)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        org_idx = self._norm_index(Organismo.objects.all())

        for i, base in enumerate(mod.BASES):
            organismo = None
            for parte in re.split(r'[/,]', base.get('organismo') or ''):
                clave = norm(parte)
                candidato = (ALIAS_BASE_ORG.get(clave)
                             or ALIAS_ORGANISMO.get(clave) or clave)
                encontrado = org_idx.get(candidato)
                if not encontrado:
                    # Fallback: contención ('secretaria salud' ⊂ 'secretaria salud publica')
                    encontrado = [o for k, objs in org_idx.items()
                                  if candidato and candidato in k
                                  for o in objs][:1]
                if encontrado:
                    organismo = encontrado[0]
                    break

            obj, _ = BaseCatalogo.objects.update_or_create(
                slug=base['id'],
                defaults={
                    'nombre': base.get('nombre') or base['id'],
                    'descripcion': base.get('descripcion') or '',
                    'organismo': organismo,
                    'organismo_texto': base.get('organismo') or '',
                    'frecuencia': base.get('frecuencia') or '',
                    'cobertura': base.get('cobertura') or '',
                    'activa': True,
                    'orden': i,
                })
            if organismo is None and base.get('organismo'):
                self.warn.append(f'Base {base["id"]}: organismo "{base["organismo"]}" sin match SIIED')

            for j, campo in enumerate(base.get('campos', [])):
                CampoCatalogo.objects.update_or_create(
                    base=obj, nombre=campo['nombre'][:120],
                    defaults={
                        'tipo': campo.get('tipo') or 'texto',
                        'descripcion': campo.get('descripcion') or '',
                        'es_llave_cruce': bool(campo.get('cruzar')),
                        'sensibilidad': campo.get('sensible') or '',
                        'categoria': campo.get('categoria') or '',
                        'orden': j,
                    })

        self.stdout.write(f'Bases del catálogo importadas: {len(mod.BASES)}')
