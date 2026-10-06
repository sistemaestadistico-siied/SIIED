import os
import re
from typing import List, Optional, Tuple, Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from indicadores.models import NivelGeografico, CapaGeo, ElementoGeo

try:
    import shapefile  # pyshp
except Exception as e:  # pragma: no cover
    shapefile = None

# Reproyección opcional con pyproj
try:  # pragma: no cover
    from pyproj import CRS, Transformer
except Exception:  # pragma: no cover
    CRS = None
    Transformer = None


def normalize(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).strip()


def guess_field(field_names: List[str], target: str) -> Optional[str]:
    """
    Heurística simple para identificar el campo de código o nombre en atributos del shapefile.
    """
    fns = [f.lower() for f in field_names]

    if target == "code":
        patterns = [
            r"^cod(_|$)",
            r"^codigo$",
            r"^cod_dane$",
            r"^cod_dpto$",
            r"^cod_mpio$",
            r"^mpio_ccdgo$",
            r"^objectid$",
            r"^gid$",
            r"^id$",
        ]
    else:  # name
        patterns = [
            r"^nombre$",
            r"^nom(_|$)",
            r"^nom_mpio$",
            r"^mpio_cnmbre$",
            r"^mpio_cnmbrenm$",
            r"^name$",
            r"^municipio$",
            r"^cabecera$",
            r"^centro$",
            r"^area$",
        ]

    # scoring: first exact regex match wins; else contains substrings as fallback
    for pat in patterns:
        for fn in fns:
            if re.match(pat, fn):
                return fn

    # fallback contains
    contains = [
        "cod" if target == "code" else "nom",
        "dane" if target == "code" else "nombre",
    ]
    for needle in contains:
        for fn in fns:
            if needle in fn:
                return fn

    return None


def _transform_coords(coords, transformer):
    """
    Aplica transformación a coordenadas anidadas (Point, LineString, Polygon, Multi*).
    Espera y devuelve listas con estructura GeoJSON.
    """
    if transformer is None:
        return coords
    # Detect depth by nesting
    # Point: [x, y]
    if isinstance(coords, (list, tuple)) and len(coords) >= 2 and not isinstance(coords[0], (list, tuple)):
        x, y = coords[0], coords[1]
        try:
            lon, lat = transformer.transform(x, y)
            # Conservar valores extra si existieran (z, m)
            rest = list(coords[2:]) if len(coords) > 2 else []
            return [lon, lat] + rest
        except Exception:
            return list(coords)
    # LineString / LinearRing: [[x,y], ...]
    if coords and isinstance(coords[0], (list, tuple)) and coords and coords and not (coords and isinstance(coords[0][0], (list, tuple))):
        return [_transform_coords(pt, transformer) for pt in coords]
    # Polygon: [ring1, ring2, ...], MultiLineString: [line1, line2, ...]
    if coords and isinstance(coords[0], (list, tuple)) and coords and isinstance(coords[0][0], (list, tuple)) and not (isinstance(coords[0][0][0], (list, tuple))):
        return [_transform_coords(ring, transformer) for ring in coords]
    # MultiPolygon: [[[ring]]]
    if coords and isinstance(coords[0], (list, tuple)) and isinstance(coords[0][0], (list, tuple)) and isinstance(coords[0][0][0], (list, tuple)):
        return [_transform_coords(poly, transformer) for poly in coords]
    return coords


def reproject_geojson_geom(geom: Optional[dict], transformer: Optional["Transformer"]) -> Optional[dict]:
    """
    Reproyecta una geometría GeoJSON al objetivo del transformer (por defecto EPSG:4326).
    Si no hay transformer, retorna la geometría original.
    """
    if not geom or not isinstance(geom, dict):
        return geom
    if transformer is None:
        return geom
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not gtype or coords is None:
        return geom
    try:
        new_coords = _transform_coords(coords, transformer)
        return {"type": gtype, "coordinates": new_coords}
    except Exception:
        return geom


def _ring_to_wkt(coords: List[List[float]]) -> str:
    # coords = [[x, y], ...]
    return ", ".join([f"{float(x)} {float(y)}" for x, y in coords])


def _polygon_to_wkt(coords: List[List[List[float]]]) -> str:
    # coords = [ exterior_ring, hole1, hole2, ... ] where ring is [[x,y],...]
    rings = []
    for ring in coords:
        rings.append(f"({_ring_to_wkt(ring)})")
    return f"POLYGON ({', '.join(rings)})"


def _multipolygon_to_wkt(coords: List[List[List[List[float]]]]) -> str:
    # coords = [ [ polygon1_rings ], [ polygon2_rings ], ... ]
    polys = []
    for poly in coords:
        rings = []
        for ring in poly:
            rings.append(f"({_ring_to_wkt(ring)})")
        polys.append(f"({', '.join(rings)})")
    return f"MULTIPOLYGON ({', '.join(polys)})"


def _linestring_to_wkt(coords: List[List[float]]) -> str:
    return f"LINESTRING ({_ring_to_wkt(coords)})"


def _multilinestring_to_wkt(coords: List[List[List[float]]]) -> str:
    parts = []
    for line in coords:
        parts.append(f"({_ring_to_wkt(line)})")
    return f"MULTILINESTRING ({', '.join(parts)})"


def _point_to_wkt(coords: List[float]) -> str:
    x, y = coords
    return f"POINT ({float(x)} {float(y)})"


def _multipoint_to_wkt(coords: List[List[float]]) -> str:
    pts = []
    for x, y in coords:
        pts.append(f"{float(x)} {float(y)}")
    return f"MULTIPOINT ({', '.join(pts)})"


def geojson_to_wkt(geom: dict) -> Optional[str]:
    """Convierte un dict GeoJSON a WKT simple (Point/Line/Polygon/Multi*)."""
    if not geom:
        return None
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not gtype or coords is None:
        return None
    gtype_u = gtype.upper()
    try:
        if gtype_u == "POINT":
            return _point_to_wkt(coords)
        if gtype_u == "MULTIPOINT":
            return _multipoint_to_wkt(coords)
        if gtype_u == "LINESTRING":
            return _linestring_to_wkt(coords)
        if gtype_u == "MULTILINESTRING":
            return _multilinestring_to_wkt(coords)
        if gtype_u == "POLYGON":
            return _polygon_to_wkt(coords)
        if gtype_u == "MULTIPOLYGON":
            return _multipolygon_to_wkt(coords)
    except Exception:
        return None
    return None


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
