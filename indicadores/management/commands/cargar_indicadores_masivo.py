#!/usr/bin/env python3
"""
Carga masiva de indicadores desde CSV SIN duplicar dominios, temas ni subtemas.

Uso (primero dry-run):
    python manage.py cargar_indicadores_masivo --csv /tmp/nuevos_indicadores_cec.csv --dry-run

Si todo OK, ejecutar en serio:
    python manage.py cargar_indicadores_masivo --csv /tmp/nuevos_indicadores_cec.csv

Por defecto asigna dominio="Cali En Cifras" y grupo_indicador="CEC".
Ajusta con --dominio y --grupo si es necesario.
"""

import csv
import os
import sys
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.db import transaction


class Command(BaseCommand):
    help = "Carga indicadores desde CSV sin duplicar jerarquía existente"

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            type=str,
            required=True,
            help='Ruta al archivo CSV con los nuevos indicadores',
        )
        parser.add_argument(
            '--dominio',
            type=str,
            default='Cali En Cifras',
            help='Nombre del dominio padre para los nuevos indicadores (default: "Cali En Cifras")',
        )
        parser.add_argument(
            '--grupo',
            type=str,
            default='CEC',
            help='Valor del campo grupo_indicador (default: CEC)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo simula, NO escribe en la base de datos',
        )
        parser.add_argument(
            '--encoding',
            type=str,
            default='utf-8-sig',
            help='Codificación del CSV (default: utf-8-sig)',
        )
        parser.add_argument(
            '--delimiter',
            type=str,
            default=',',
            help='Separador de columnas (default: ,)',
        )

    def handle(self, *args, **options):
        csv_path = options['csv']
        dominio_nombre = options['dominio']
        grupo = options['grupo']
        dry_run = options['dry_run']
        encoding = options['encoding']
        delimiter = options['delimiter']

        if not os.path.exists(csv_path):
            self.stdout.write(self.style.ERROR(f"No existe el archivo: {csv_path}"))
            sys.exit(1)

        mode = "DRY-RUN (simulación)" if dry_run else "REAL (escritura a BD)"
        self.stdout.write(self.style.WARNING(f"Modo: {mode}"))
        self.stdout.write(f"CSV: {csv_path}")
        self.stdout.write(f"Dominio: {dominio_nombre}")
        self.stdout.write(f"Grupo indicador: {grupo}")
        self.stdout.write("-" * 60)

        from indicadores.models import MenuDominio, MenuTema, MenuSubtema, Indicador

        # estadísticas
        stats = {
            'filas_leidas': 0,
            'indicadores_nuevos': 0,
            'indicadores_existentes': 0,
            'subtemas_nuevos': 0,
            'subtemas_reutilizados': 0,
            'temas_nuevos': 0,
            'temas_reutilizados': 0,
            'dominios_nuevos': 0,
            'dominios_reutilizados': 0,
            'errores': 0,
        }

        # cache para evitar consultas repetidas
        cache = {
            'dominios': {},
            'temas': {},
            'subtemas': {},
            'indicadores': {},
        }

        def get_or_create_dominio(nombre):
            slug = slugify(nombre)
            if slug in cache['dominios']:
                return cache['dominios'][slug], False

            # 1) Buscar por slug exacto
            try:
                obj = MenuDominio.objects.get(slug=slug)
                cache['dominios'][slug] = obj
                stats['dominios_reutilizados'] += 1
                self.stdout.write(f"  [DOMINIO REUTILIZADO] {obj.nombre} (slug={slug})")
                return obj, False
            except MenuDominio.DoesNotExist:
                pass

            # 2) Buscar por nombre exacto (case-insensitive) para evitar duplicado
            try:
                obj = MenuDominio.objects.get(nombre__iexact=nombre)
                cache['dominios'][slug] = obj
                stats['dominios_reutilizados'] += 1
                self.stdout.write(
                    f"  [DOMINIO REUTILIZADO] {obj.nombre} (slug={obj.slug}) — encontrado por nombre"
                )
                return obj, False
            except (MenuDominio.DoesNotExist, MenuDominio.MultipleObjectsReturned):
                pass

            # 3) Crear nuevo
            obj = MenuDominio.objects.create(nombre=nombre, slug=slug, activo=True)
            cache['dominios'][slug] = obj
            stats['dominios_nuevos'] += 1
            self.stdout.write(f"  [DOMINIO NUEVO] {nombre} (slug={slug})")
            return obj, True

        def _slug_unico(model, slug_base):
            """Genera un slug que no colisione globalmente."""
            slug = slug_base
            counter = 1
            while model.objects.filter(slug=slug).exists():
                slug = f"{slug_base}-{counter}"
                counter += 1
            return slug

        def get_or_create_tema(nombre, dominio):
            slug_base = slugify(nombre)
            cache_key = f"{dominio.id}:{slug_base}"
            if cache_key in cache['temas']:
                return cache['temas'][cache_key], False

            # 1) Buscar por slug exacto en el dominio objetivo
            try:
                obj = MenuTema.objects.get(slug=slug_base, dominio=dominio)
                cache['temas'][cache_key] = obj
                stats['temas_reutilizados'] += 1
                self.stdout.write(f"  [TEMA REUTILIZADO] {obj.nombre} (slug={slug_base})")
                return obj, False
            except MenuTema.DoesNotExist:
                pass

            # 2) Buscar por nombre exacto (case-insensitive) en el dominio
            try:
                obj = MenuTema.objects.get(nombre__iexact=nombre, dominio=dominio)
                cache['temas'][cache_key] = obj
                stats['temas_reutilizados'] += 1
                self.stdout.write(
                    f"  [TEMA REUTILIZADO] {obj.nombre} (slug={obj.slug}) — encontrado por nombre"
                )
                return obj, False
            except (MenuTema.DoesNotExist, MenuTema.MultipleObjectsReturned):
                pass

            # 3) Buscar por contenido: tema existente cuyo nombre CONTENGA el del CSV
            #    o viceversa (útil cuando CSV dice "Generalidades" y existe "Cap 1 - Generalidades")
            if len(nombre) >= 5:
                q1 = MenuTema.objects.filter(dominio=dominio, nombre__icontains=nombre)
                q2 = MenuTema.objects.filter(dominio=dominio, nombre__isnull=False)
                # filtrar los que el nombre del CSV contenga el nombre existente
                for t in q2:
                    if t.nombre.lower() in nombre.lower() or nombre.lower() in t.nombre.lower():
                        if t not in list(q1):
                            q1 = list(q1) + [t]
                if q1:
                    # Tomar el más parecido (menor diferencia de longitud)
                    candidatos = list(q1) if isinstance(q1, list) else list(q1)
                    if len(candidatos) == 1:
                        obj = candidatos[0]
                    else:
                        obj = min(candidatos, key=lambda t: abs(len(t.nombre) - len(nombre)))
                    cache['temas'][cache_key] = obj
                    stats['temas_reutilizados'] += 1
                    self.stdout.write(
                        f"  [TEMA REUTILIZADO] {obj.nombre} (slug={obj.slug}) — coincidencia parcial"
                    )
                    return obj, False

            # 4) Crear nuevo (evitar colisión global de slug)
            slug_nuevo = _slug_unico(MenuTema, slug_base)
            if not dry_run:
                obj = MenuTema.objects.create(
                    nombre=nombre,
                    slug=slug_nuevo,
                    dominio=dominio,
                    activo=True,
                )
            else:
                obj = MenuTema(id=-(stats['temas_nuevos']+1), nombre=nombre, slug=slug_nuevo, dominio=dominio)
            cache['temas'][cache_key] = obj
            stats['temas_nuevos'] += 1
            self.stdout.write(f"  [TEMA NUEVO] {nombre} (slug={slug_nuevo})")
            return obj, True

        def get_or_create_subtema(nombre, tema):
            slug_base = slugify(nombre)
            cache_key = f"{tema.id}:{slug_base}"
            if cache_key in cache['subtemas']:
                return cache['subtemas'][cache_key], False

            # 1) Buscar por slug exacto en el tema objetivo
            try:
                obj = MenuSubtema.objects.get(slug=slug_base, tema=tema)
                cache['subtemas'][cache_key] = obj
                stats['subtemas_reutilizados'] += 1
                self.stdout.write(f"  [SUBTEMA REUTILIZADO] {obj.nombre} (slug={slug_base})")
                return obj, False
            except MenuSubtema.DoesNotExist:
                pass

            # 2) Buscar por nombre exacto (case-insensitive) en el tema
            try:
                obj = MenuSubtema.objects.get(nombre__iexact=nombre, tema=tema)
                cache['subtemas'][cache_key] = obj
                stats['subtemas_reutilizados'] += 1
                self.stdout.write(
                    f"  [SUBTEMA REUTILIZADO] {obj.nombre} (slug={obj.slug}) — encontrado por nombre"
                )
                return obj, False
            except (MenuSubtema.DoesNotExist, MenuSubtema.MultipleObjectsReturned):
                pass

            # 3) Buscar por contenido en el tema
            if len(nombre) >= 5:
                q1 = MenuSubtema.objects.filter(tema=tema, nombre__icontains=nombre)
                q2 = MenuSubtema.objects.filter(tema=tema, nombre__isnull=False)
                candidatos = list(q1)
                for s in q2:
                    if s.nombre.lower() in nombre.lower() or nombre.lower() in s.nombre.lower():
                        if s not in candidatos:
                            candidatos.append(s)
                if candidatos:
                    if len(candidatos) == 1:
                        obj = candidatos[0]
                    else:
                        obj = min(candidatos, key=lambda s: abs(len(s.nombre) - len(nombre)))
                    cache['subtemas'][cache_key] = obj
                    stats['subtemas_reutilizados'] += 1
                    self.stdout.write(
                        f"  [SUBTEMA REUTILIZADO] {obj.nombre} (slug={obj.slug}) — coincidencia parcial"
                    )
                    return obj, False

            # 4) Crear nuevo (evitar colisión global de slug)
            slug_nuevo = _slug_unico(MenuSubtema, slug_base)
            if not dry_run:
                obj = MenuSubtema.objects.create(
                    nombre=nombre,
                    slug=slug_nuevo,
                    tema=tema,
                    activo=True,
                )
            else:
                obj = MenuSubtema(id=-(stats['subtemas_nuevos']+1), nombre=nombre, slug=slug_nuevo, tema=tema)
            cache['subtemas'][cache_key] = obj
            stats['subtemas_nuevos'] += 1
            self.stdout.write(f"  [SUBTEMA NUEVO] {nombre} (slug={slug_nuevo})")
            return obj, True

        def crear_indicador(codigo, nombre, subtema, fuente):
            cache_key = codigo or f"{subtema.id}:{slugify(nombre)}"
            if cache_key in cache['indicadores']:
                return cache['indicadores'][cache_key], False

            # 1) Buscar por código exacto
            if codigo:
                try:
                    obj = Indicador.objects.get(codigo_indicador=codigo)
                    cache['indicadores'][cache_key] = obj
                    stats['indicadores_existentes'] += 1
                    self.stdout.write(f"  [INDICADOR EXISTENTE] {codigo} — {nombre}")
                    return obj, False
                except Indicador.DoesNotExist:
                    pass

            # 2) Buscar por nombre exacto (case-insensitive) dentro del mismo subtema
            try:
                obj = Indicador.objects.get(nombre__iexact=nombre, subtema=subtema)
                cache['indicadores'][cache_key] = obj
                stats['indicadores_existentes'] += 1
                self.stdout.write(
                    f"  [INDICADOR EXISTENTE] {codigo or ''} — {nombre} — encontrado por nombre"
                )
                return obj, False
            except (Indicador.DoesNotExist, Indicador.MultipleObjectsReturned):
                pass

            # 3) Buscar por contenido del nombre en el subtema
            if len(nombre) >= 5:
                candidatos = list(Indicador.objects.filter(subtema=subtema, nombre__icontains=nombre))
                for i in Indicador.objects.filter(subtema=subtema, nombre__isnull=False):
                    if i.nombre.lower() in nombre.lower() or nombre.lower() in i.nombre.lower():
                        if i not in candidatos:
                            candidatos.append(i)
                if candidatos:
                    if len(candidatos) == 1:
                        obj = candidatos[0]
                    else:
                        obj = min(candidatos, key=lambda i: abs(len(i.nombre) - len(nombre)))
                    cache['indicadores'][cache_key] = obj
                    stats['indicadores_existentes'] += 1
                    self.stdout.write(
                        f"  [INDICADOR EXISTENTE] {codigo or ''} — {obj.nombre} — coincidencia parcial"
                    )
                    return obj, False

            # 4) Crear nuevo
            if not dry_run:
                obj = Indicador.objects.create(
                    nombre=nombre,
                    codigo_indicador=codigo or None,
                    subtema=subtema,
                    grupo_indicador=grupo,
                    fuente_datos=fuente or None,
                    activo=True,
                )
            else:
                obj = Indicador(id=-(stats['indicadores_nuevos']+1), nombre=nombre, codigo_indicador=codigo, subtema=subtema)
            cache['indicadores'][cache_key] = obj
            stats['indicadores_nuevos'] += 1
            self.stdout.write(f"  [INDICADOR NUEVO] {codigo or ''} — {nombre}")
            return obj, True

        # ------------------------------------------------------------------
        # Procesar CSV
        # ------------------------------------------------------------------
        with open(csv_path, newline='', encoding=encoding) as f:
            reader = csv.reader(f, delimiter=delimiter)
            header = next(reader, None)
            if header is None:
                self.stdout.write(self.style.ERROR("El CSV está vacío"))
                sys.exit(1)

            self.stdout.write(f"Columnas detectadas ({len(header)}): {header}")
            self.stdout.write("-" * 60)

            for row in reader:
                stats['filas_leidas'] += 1
                if not row or all(not c.strip() for c in row):
                    continue

                # Intentar mapear por posición (ajustar si tu CSV tiene otra estructura)
                # Asume: codigo, capitulo_num, tema, subtema, nombre, fuente
                try:
                    if len(row) >= 6:
                        codigo = row[0].strip() if row[0].strip() else None
                        tema_nombre = row[2].strip()
                        subtema_nombre = row[3].strip()
                        nombre_indicador = row[4].strip()
                        fuente = row[5].strip() if len(row) > 5 else None
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"Fila {stats['filas_leidas']}: tiene {len(row)} columnas, se esperan al menos 6. Saltando."
                        ))
                        stats['errores'] += 1
                        continue
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Fila {stats['filas_leidas']}: error parseando: {e}"))
                    stats['errores'] += 1
                    continue

                if not nombre_indicador:
                    self.stdout.write(self.style.WARNING(f"Fila {stats['filas_leidas']}: nombre vacío. Saltando."))
                    stats['errores'] += 1
                    continue

                self.stdout.write(f"\nFila {stats['filas_leidas']}: {codigo or 'SIN_CODIGO'} — {nombre_indicador}")

                # 1) Dominio
                dominio, _ = get_or_create_dominio(dominio_nombre)

                # 2) Tema
                tema, _ = get_or_create_tema(tema_nombre, dominio)

                # 3) Subtema
                subtema, _ = get_or_create_subtema(subtema_nombre, tema)

                # 4) Indicador
                crear_indicador(codigo, nombre_indicador, subtema, fuente)

        # ------------------------------------------------------------------
        # Resumen final
        # ------------------------------------------------------------------
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.NOTICE("RESUMEN"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Filas leídas:        {stats['filas_leidas']}")
        self.stdout.write(f"Indicadores nuevos:  {stats['indicadores_nuevos']}")
        self.stdout.write(f"Indicadores existentes (saltados): {stats['indicadores_existentes']}")
        self.stdout.write(f"Subtemas nuevos:     {stats['subtemas_nuevos']}")
        self.stdout.write(f"Subtemas reutilizados: {stats['subtemas_reutilizados']}")
        self.stdout.write(f"Temas nuevos:        {stats['temas_nuevos']}")
        self.stdout.write(f"Temas reutilizados:  {stats['temas_reutilizados']}")
        self.stdout.write(f"Dominios nuevos:     {stats['dominios_nuevos']}")
        self.stdout.write(f"Dominios reutilizados: {stats['dominios_reutilizados']}")
        self.stdout.write(f"Errores / saltados:  {stats['errores']}")
        self.stdout.write("=" * 60)

        if dry_run:
            self.stdout.write(self.style.WARNING("\nEsto fue un DRY-RUN. Nada se escribió en la base de datos."))
            self.stdout.write(self.style.NOTICE("Para ejecutar en serio quita --dry-run"))
        else:
            self.stdout.write(self.style.SUCCESS("\nCarga completada exitosamente."))
