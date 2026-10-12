import os
from typing import List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from indicadores.models import NivelGeografico, CapaGeo, ElementoGeo
from indicadores.utils_geo import (
    normalize, guess_field, reproject_geojson_geom, geojson_to_wkt,
    shapefile, CRS, Transformer,
)


class Command(BaseCommand):
    help = (
        "Carga elementos geográficos (ElementoGeo) desde un shapefile (.shp) en una CapaGeo del NivelGeografico indicado.\n"
        "Detecta automáticamente campos de código y nombre, con opción de sobreescritura."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--shp",
            required=True,
            help="Ruta al archivo .shp (por ejemplo: 'docs/perimetro urbano/Perimetro_urbano.shp')",
        )
        parser.add_argument(
            "--nivel",
            default="Área Geográfica",
            help="Nombre del NivelGeografico a usar/crear (por defecto: 'Área Geográfica')",
        )
        parser.add_argument(
            "--capa",
            required=True,
            help="Nombre de la CapaGeo a usar/crear (por ejemplo: 'Cabecera Municipal' o 'Centros Poblados')",
        )
        parser.add_argument(
            "--code-field",
            dest="code_field",
            default=None,
            help="Nombre del campo de código en el shapefile (si se omite, se intenta detectar)",
        )
        parser.add_argument(
            "--name-field",
            dest="name_field",
            default=None,
            help="Nombre del campo de nombre en el shapefile (si se omite, se intenta detectar)",
        )
        parser.add_argument(
            "--encoding",
            default="latin1",
            help="Codificación para leer el DBF (por defecto: latin1)",
        )
        parser.add_argument(
            "--skip-reproject",
            action="store_true",
            help="No intenta reproyectar a WGS84 (EPSG:4326) incluso si hay .prj y pyproj.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No guarda cambios en BD, solo muestra lo que haría",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Procesa solo los primeros N registros (útil para pruebas)",
        )

    def handle(self, *args, **options):
        if shapefile is None:
            raise CommandError(
                "El paquete 'pyshp' no está disponible. Instálalo con: pip install pyshp"
            )

        shp_path = options["shp"]
        nivel_nombre = options["nivel"].strip()
        capa_nombre = options["capa"].strip()
        code_field_opt = options.get("code_field")
        name_field_opt = options.get("name_field")
        encoding = options["encoding"]
        dry_run = options["dry_run"]
        limit = options.get("limit")
        skip_reproject = options.get("skip_reproject", False)

        if not os.path.isfile(shp_path):
            raise CommandError(f"No se encontró el archivo .shp en: {shp_path}")

        self.stdout.write(self.style.MIGRATE_HEADING("==> Leyendo shapefile"))
        self.stdout.write(f"Archivo: {shp_path}")
        self.stdout.write(f"Encoding DBF: {encoding}")

        try:
            r = shapefile.Reader(shp_path, encoding=encoding)
        except Exception as e:
            raise CommandError(f"Error leyendo shapefile: {e}")

        # Intentar preparar transformer desde .prj a WGS84
        transformer = None
        prj_path = os.path.splitext(shp_path)[0] + ".prj"
        if not skip_reproject and os.path.isfile(prj_path) and CRS is not None and Transformer is not None:
            try:
                with open(prj_path, "r", encoding="utf-8", errors="ignore") as f:
                    prj_wkt = f.read()
                src_crs = CRS.from_wkt(prj_wkt)
                dst_crs = CRS.from_epsg(4326)
                transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
                self.stdout.write(self.style.MIGRATE_HEADING("==> Reproyección activada"))
                self.stdout.write(f"Desde: {src_crs.to_string()} -> Hacia: EPSG:4326 (WGS84)")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"No se pudo configurar reproyección desde .prj: {e}"))
        else:
            if not os.path.isfile(prj_path):
                self.stdout.write(self.style.WARNING("No se encontró .prj; se asumirán coordenadas en WGS84."))
            elif skip_reproject:
                self.stdout.write(self.style.WARNING("Reproyección omitida por --skip-reproject."))
            else:
                self.stdout.write(self.style.WARNING("pyproj no disponible; no se reproyectará (usar pip install pyproj)."))

        # Nombres de campos (omitir el primer campo de borrado)
        raw_fields: List[Tuple[str, str, int, int]] = r.fields[1:]
        field_names: List[str] = [f[0] for f in raw_fields]
        lower_names: List[str] = [f.lower() for f in field_names]

        self.stdout.write(self.style.SQL_TABLE("Campos disponibles:"))
        for nm in field_names:
            self.stdout.write(f" - {nm}")

        # Detectar campos
        code_field = (code_field_opt or guess_field(field_names, target="code"))
        name_field = (name_field_opt or guess_field(field_names, target="name"))

        if code_field is None:
            raise CommandError(
                "No se pudo detectar el campo de código. Usa --code-field para especificarlo explícitamente."
            )
        if name_field is None:
            raise CommandError(
                "No se pudo detectar el campo de nombre. Usa --name-field para especificarlo explícitamente."
            )

        code_field_l = code_field.lower()
        name_field_l = name_field.lower()
        if code_field_l not in lower_names:
            raise CommandError(f"El campo de código '{code_field}' no existe en el DBF")
        if name_field_l not in lower_names:
            raise CommandError(f"El campo de nombre '{name_field}' no existe en el DBF")

        code_idx = lower_names.index(code_field_l)
        name_idx = lower_names.index(name_field_l)

        self.stdout.write(self.style.SUCCESS(f"Campo de código: {field_names[code_idx]}"))
        self.stdout.write(self.style.SUCCESS(f"Campo de nombre: {field_names[name_idx]}"))

        total = 0
        creados = 0
        actualizados = 0
        omitidos_sin_codigo = 0
        omitidos_sin_nombre = 0

        # Preparar/obtener nivel y capa
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN activo: no se guardarán cambios."))
            nivel = None
            capa = None
        else:
            nivel, _ = NivelGeografico.objects.get_or_create(
                nombre=nivel_nombre, defaults={"descripcion": ""}
            )
            capa, _ = CapaGeo.objects.get_or_create(
                nombre=capa_nombre, nivel_geografico=nivel, defaults={"descripcion": ""}
            )

        # Recorrer registros y geometrías
        def process_record(values: List, wkt_geom: Optional[str]):
            nonlocal total, creados, actualizados, omitidos_sin_codigo, omitidos_sin_nombre
            total += 1
            codigo = normalize(values[code_idx])
            nombre = normalize(values[name_idx])

            if not codigo:
                omitidos_sin_codigo += 1
                return
            if not nombre:
                omitidos_sin_nombre += 1
                return

            if dry_run:
                # Mostrar ejemplo para las primeras filas
                if total <= 5:
                    msg = f"[DRY-RUN] {codigo} -> {nombre}"
                    if wkt_geom:
                        msg += " | geom: " + wkt_geom.split("(")[0]
                    self.stdout.write(msg)
                return

            elem, created = ElementoGeo.objects.get_or_create(
                codigo=str(codigo), capa_geo=capa, defaults={"nombre": str(nombre)}
            )
            if created:
                creados += 1
            else:
                if normalize(elem.nombre) != normalize(nombre):
                    elem.nombre = str(nombre)
                    elem.save(update_fields=["nombre"])
            # Actualizar geom_wkt si cambió y tenemos geometría
            if not dry_run and wkt_geom:
                if normalize(elem.geom_wkt) != normalize(wkt_geom):
                    elem.geom_wkt = wkt_geom
                    elem.save(update_fields=["geom_wkt"])
                    actualizados += 1

        # Iterar con límite opcional, recorriendo shapes y records juntos
        count = 0
        for shprec in r.iterShapeRecords():
            values = list(shprec.record)
            geom = None
            try:
                geom = getattr(shprec.shape, "__geo_interface__", None)
                # Reproyectar a WGS84 si es posible
                if geom and transformer is not None:
                    geom = reproject_geojson_geom(geom, transformer)
                wkt = geojson_to_wkt(geom) if geom else None
            except Exception:
                wkt = None
            process_record(values, wkt)
            count += 1
            if limit is not None and count >= limit:
                break

        self.stdout.write(self.style.MIGRATE_HEADING("==> Resumen"))
        self.stdout.write(f"Registros leídos: {total}")
        self.stdout.write(f"Omitidos sin código: {omitidos_sin_codigo}")
        self.stdout.write(f"Omitidos sin nombre: {omitidos_sin_nombre}")
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Creados: {creados}"))
            self.stdout.write(self.style.SUCCESS(f"Actualizados: {actualizados}"))
        else:
            self.stdout.write(self.style.WARNING("Sin cambios aplicados (DRY-RUN)"))
