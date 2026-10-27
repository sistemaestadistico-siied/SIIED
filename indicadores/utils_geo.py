"""Utilidades geográficas compartidas: conversión GeoJSON→WKT, parsers de
formatos (GeoJSON, KML/KMZ, CSV, Shapefile via pyshp) y helpers de match.

Usado por el wizard de carga de capas (views_capas.py) y por el comando
`cargar_elementos_geo`.
"""

import csv
import io
import json
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

try:
    import shapefile  # pyshp
except Exception:
    shapefile = None

try:
    from pyproj import CRS, Transformer
except Exception:
    CRS = None
    Transformer = None


# ── Normalización ──────────────────────────────────────────────────────

def normaliza(s: Optional[str]) -> str:
    """Sin tildes, minúsculas, espacios colapsados, sin puntuación."""
    if not s:
        return ''
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = ''.join(ch if ch.isalnum() else ' ' for ch in s)
    return ' '.join(s.split())


def norm_code(code) -> Optional[str]:
    """Normalizador de códigos — IDÉNTICO al usado por el renderer de mapas
    en views.py (raw + normalizado se prueban ambos al emparejar)."""
    if code is None:
        return None
    s = str(code).strip()
    if not s:
        return None
    for ch in [' ', '-', '_', '.']:
        s = s.replace(ch, '')
    s = s.upper().lstrip('0') or '0'
    return s


def normalize(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).strip()


# ── Detección de campos código/nombre ─────────────────────────────────

def guess_field(field_names: List[str], target: str) -> Optional[str]:
    """Heurística para identificar el campo de código o nombre."""
    fns = [f.lower() for f in field_names]

    if target == "code":
        patterns = [
            r"^cod(_|$)", r"^codigo$", r"^cod_dane$", r"^cod_dpto$",
            r"^cod_mpio$", r"^mpio_ccdgo$", r"^objectid$", r"^gid$", r"^id$",
        ]
    else:
        patterns = [
            r"^nombre$", r"^nom(_|$)", r"^nom_mpio$", r"^mpio_cnmbre$",
            r"^mpio_cnmbrenm$", r"^name$", r"^municipio$", r"^cabecera$",
            r"^centro$", r"^area$",
        ]

    for pat in patterns:
        for fn in fns:
            if re.match(pat, fn):
                return fn
    contains = ["cod" if target == "code" else "nom",
                "dane" if target == "code" else "nombre"]
    for needle in contains:
        for fn in fns:
            if needle in fn:
                return fn
    return None


# ── Reproyección (opcional, requiere pyproj) ──────────────────────────

def _transform_coords(coords, transformer):
    if transformer is None:
        return coords
    if isinstance(coords, (list, tuple)) and len(coords) >= 2 and not isinstance(coords[0], (list, tuple)):
        x, y = coords[0], coords[1]
        try:
            lon, lat = transformer.transform(x, y)
            rest = list(coords[2:]) if len(coords) > 2 else []
            return [lon, lat] + rest
        except Exception:
            return list(coords)
    if coords and isinstance(coords[0], (list, tuple)) and not isinstance(coords[0][0], (list, tuple)):
        return [_transform_coords(pt, transformer) for pt in coords]
    if coords and isinstance(coords[0], (list, tuple)) and isinstance(coords[0][0], (list, tuple)) and not isinstance(coords[0][0][0], (list, tuple)):
        return [_transform_coords(ring, transformer) for ring in coords]
    if coords and isinstance(coords[0], (list, tuple)) and isinstance(coords[0][0], (list, tuple)) and isinstance(coords[0][0][0], (list, tuple)):
        return [_transform_coords(poly, transformer) for poly in coords]
    return coords


def reproject_geojson_geom(geom: Optional[dict], transformer) -> Optional[dict]:
    if not geom or not isinstance(geom, dict) or transformer is None:
        return geom
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not gtype or coords is None:
        return geom
    try:
        return {"type": gtype, "coordinates": _transform_coords(coords, transformer)}
    except Exception:
        return geom


# ── GeoJSON → WKT ─────────────────────────────────────────────────────

def _ring_to_wkt(coords: List[List[float]]) -> str:
    return ", ".join([f"{float(x)} {float(y)}" for x, y in coords])


def _polygon_to_wkt(coords) -> str:
    rings = [f"({_ring_to_wkt(ring)})" for ring in coords]
    return f"POLYGON ({', '.join(rings)})"


def _multipolygon_to_wkt(coords) -> str:
    polys = []
    for poly in coords:
        rings = [f"({_ring_to_wkt(ring)})" for ring in poly]
        polys.append(f"({', '.join(rings)})")
    return f"MULTIPOLYGON ({', '.join(polys)})"


def geojson_to_wkt(geom: Optional[dict]) -> Optional[str]:
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
            return f"POINT ({float(coords[0])} {float(coords[1])})"
        if gtype_u == "MULTIPOINT":
            pts = ", ".join(f"{float(x)} {float(y)}" for x, y in coords)
            return f"MULTIPOINT ({pts})"
        if gtype_u == "LINESTRING":
            return f"LINESTRING ({_ring_to_wkt(coords)})"
        if gtype_u == "MULTILINESTRING":
            parts = ", ".join(f"({_ring_to_wkt(line)})" for line in coords)
            return f"MULTILINESTRING ({parts})"
        if gtype_u == "POLYGON":
            return _polygon_to_wkt(coords)
        if gtype_u == "MULTIPOLYGON":
            return _multipolygon_to_wkt(coords)
    except Exception:
        return None
    return None


# ── Parsers de formatos ───────────────────────────────────────────────
# Todos devuelven: {'fields': [...], 'features': [{props:{}, geom:{geojson}|None}]}

def parse_geojson(raw: bytes) -> dict:
    data = json.loads(raw.decode('utf-8-sig'))
    feats = []
    if data.get('type') == 'FeatureCollection':
        items = data.get('features', [])
    elif data.get('type') == 'Feature':
        items = [data]
    else:
        raise ValueError('GeoJSON sin FeatureCollection/Feature.')
    fields = []
    for f in items:
        props = f.get('properties') or {}
        for k in props.keys():
            if k not in fields:
                fields.append(k)
        feats.append({'props': props, 'geom': f.get('geometry')})
    return {'fields': fields, 'features': feats}


def _kml_coords_to_list(text: str) -> List[List[float]]:
    """'lon,lat,alt lon,lat,alt ...' → [[lon,lat],...] (alt descartado)."""
    pts = []
    for tok in (text or '').replace('\n', ' ').split():
        parts = tok.split(',')
        if len(parts) >= 2:
            try:
                pts.append([float(parts[0]), float(parts[1])])
            except ValueError:
                pass
    return pts


def _kml_geom(el) -> Optional[dict]:
    """GeoJSON-ish geometry dict desde un Placemark KML (el = Element)."""
    ns = '{http://www.opengis.net/kml/2.2}'
    def findall_any(parent, tag):
        return (parent.findall(f'.//{ns}{tag}') +
                parent.findall(f'.//{tag}'))
    # Polygon: [outer ring, inner rings...]
    polys = findall_any(el, 'Polygon')
    if polys:
        all_rings = []
        for p in polys:
            rings = []
            outer = p.find(f'.//{ns}outerBoundaryIs/{ns}LinearRing/{ns}coordinates') \
                or p.find('.//outerBoundaryIs/LinearRing/coordinates')
            if outer is not None and outer.text:
                rings.append(_kml_coords_to_list(outer.text))
            for inner in (p.findall(f'.//{ns}innerBoundaryIs/{ns}LinearRing/{ns}coordinates') +
                          p.findall('.//innerBoundaryIs/LinearRing/coordinates')):
                if inner.text:
                    rings.append(_kml_coords_to_list(inner.text))
            if rings:
                all_rings.append(rings)
        if len(all_rings) == 1:
            return {'type': 'Polygon', 'coordinates': all_rings[0]}
        if all_rings:
            return {'type': 'MultiPolygon', 'coordinates': all_rings}
    lines = findall_any(el, 'LineString')
    if lines:
        segs = []
        for ln in lines:
            c = ln.find(f'{ns}coordinates') or ln.find('coordinates')
            if c is not None and c.text:
                segs.append(_kml_coords_to_list(c.text))
        if len(segs) == 1:
            return {'type': 'LineString', 'coordinates': segs[0]}
        if segs:
            return {'type': 'MultiLineString', 'coordinates': segs}
    pts = findall_any(el, 'Point')
    if pts:
        coords = []
        for pt in pts:
            c = pt.find(f'{ns}coordinates') or pt.find('coordinates')
            if c is not None and c.text:
                coords += _kml_coords_to_list(c.text)
        if len(coords) == 1:
            return {'type': 'Point', 'coordinates': coords[0]}
        if coords:
            return {'type': 'MultiPoint', 'coordinates': coords}
    return None


def parse_kml(raw: bytes) -> dict:
    root = ET.fromstring(raw)
    ns = '{http://www.opengis.net/kml/2.2}'
    placemarks = root.findall(f'.//{ns}Placemark') or root.findall('.//Placemark')
    feats, fields = [], []
    for pm in placemarks:
        props = {}
        nm = pm.find(f'{ns}name') or pm.find('name')
        if nm is not None and nm.text:
            props['name'] = nm.text.strip()
        for d in (pm.findall(f'.//{ns}ExtendedData/{ns}Data') +
                  pm.findall('.//ExtendedData/Data')):
            key = d.get('name')
            v = d.find(f'{ns}value') or d.find('value')
            if key:
                props[key] = v.text.strip() if v is not None and v.text else ''
                if key not in fields:
                    fields.append(key)
        if 'name' in props and 'name' not in fields:
            fields.insert(0, 'name')
        feats.append({'props': props, 'geom': _kml_geom(pm)})
    return {'fields': fields, 'features': feats}


def parse_csv_geo(raw: bytes) -> dict:
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin1')
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    fields = list(reader.fieldnames or [])
    feats = []
    lower = {f.lower(): f for f in fields}
    wkt_col = next((lower[k] for k in ('wkt', 'geom', 'geometry', 'the_geom') if k in lower), None)
    lon_col = next((lower[k] for k in ('lon', 'lng', 'longitud', 'longitude', 'x') if k in lower), None)
    lat_col = next((lower[k] for k in ('lat', 'latitud', 'latitude', 'y') if k in lower), None)
    for row in reader:
        geom = None
        wkt_txt = normalize(row.get(wkt_col)) if wkt_col else ''
        if wkt_txt and re.match(r'^(POINT|LINE|POLY|MULTI|GEOM)', wkt_txt.upper()):
            geom = {'type': '__WKT__', 'wkt': wkt_txt}  # passthrough
        elif lon_col and lat_col:
            try:
                lon = float(normalize(row.get(lon_col)).replace(',', '.') or 'nan')
                lat = float(normalize(row.get(lat_col)).replace(',', '.') or 'nan')
                if lon == lon and lat == lat:
                    geom = {'type': 'Point', 'coordinates': [lon, lat]}
            except ValueError:
                pass
        feats.append({'props': dict(row), 'geom': geom})
    return {'fields': fields, 'features': feats}


def parse_shapefile_zip(raw: bytes, encoding: str = 'latin1') -> dict:
    """Shapefile dentro de un .zip. Requiere pyshp; reproyecta si hay .prj+pyproj."""
    if shapefile is None:
        raise ValueError(
            "Formato Shapefile requiere 'pyshp': pip install pyshp "
            "(y pyproj para reproyección si el .prj no es WGS84).")
    zf = zipfile.ZipFile(io.BytesIO(raw))
    names = {n.lower().split('/')[-1]: n for n in zf.namelist()}
    shp_name = next((n for n in names.values() if n.lower().endswith('.shp')), None)
    if not shp_name:
        raise ValueError('El .zip no contiene un archivo .shp')
    base = shp_name[:-4]
    shp_bytes = io.BytesIO(zf.read(shp_name))
    dbf_bytes = io.BytesIO(zf.read(names.get(base.lower() + '.dbf', base + '.dbf'))
                           ) if (base.lower() + '.dbf') in names or (base + '.dbf') in names else None
    prj_member = names.get(base.lower() + '.prj')
    prj_text = zf.read(prj_member).decode('utf-8', errors='ignore') if prj_member else None

    transformer = None
    if prj_text and CRS is not None and Transformer is not None:
        try:
            transformer = Transformer.from_crs(
                CRS.from_wkt(prj_text), CRS.from_epsg(4326), always_xy=True)
        except Exception:
            transformer = None

    reader_kw = {'shp': shp_bytes}
    if dbf_bytes:
        reader_kw['dbf'] = dbf_bytes
    r = shapefile.Reader(**reader_kw, encoding=encoding)
    field_names = [f[0] for f in r.fields[1:]]
    feats = []
    for shprec in r.iterShapeRecords():
        geom = getattr(shprec.shape, '__geo_interface__', None)
        if geom and transformer:
            geom = reproject_geojson_geom(geom, transformer)
        feats.append({'props': dict(zip(field_names, list(shprec.record))),
                      'geom': geom})
    return {'fields': field_names, 'features': feats}


def detect_and_parse(filename: str, raw: bytes) -> Tuple[str, dict]:
    """Detecta formato por extensión+contenido y devuelve (formato, parsed)."""
    low = (filename or '').lower()
    if low.endswith(('.geojson', '.json')) or raw.lstrip()[:1] == b'{':
        return 'geojson', parse_geojson(raw)
    if low.endswith(('.kml',)):
        return 'kml', parse_kml(raw)
    if low.endswith(('.kmz', '.zip')):
        zf = zipfile.ZipFile(io.BytesIO(raw))
        names = [n.lower() for n in zf.namelist()]
        kml_member = next((n for n in zf.namelist()
                           if n.lower().endswith('.kml') and n == 'doc.kml'
                           or n.lower().endswith('.kml')), None)
        if kml_member:
            return 'kmz', parse_kml(zf.read(kml_member))
        if any(n.endswith('.shp') for n in names):
            return 'shp', parse_shapefile_zip(raw)
        raise ValueError('El .zip no contiene .kml ni .shp')
    if low.endswith(('.shp',)):
        raise ValueError('Sube el shapefile comprimido en .zip (con .dbf y .prj).')
    return 'csv', parse_csv_geo(raw)


def _coords_from_ring(txt: str) -> List[List[float]]:
    """Parsea un anillo WKT 'x y, x y, ...' a lista [[lng, lat], ...].

    Detecta coordenadas proyectadas (UTM) y las convierte a lat/lng aproximado
    para el área de Cali. Para precisión cartográfica usar reproyección formal.
    """
    pts = []
    for pair in txt.split(','):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split()
        if len(parts) < 2:
            continue
        try:
            x = float(parts[0])
            y = float(parts[1])

            # Transform projected coordinates to geographic (lat/lng)
            # Assuming UTM Zone 18N (EPSG:32618) to WGS84 (EPSG:4326)
            # Simple approximation for Cali, Colombia area
            if x > 180 or y > 90:  # Detect projected coordinates
                # Convert UTM to approximate lat/lng for Cali area
                # UTM Zone 18N false easting: 500000, false northing: 0
                # Cali is approximately at 3.4°N, 76.5°W

                # Simple linear transformation (approximation)
                # This is a rough conversion - for production use proper coordinate transformation
                lng = -76.5 + (x - 1000000) / 111320  # Rough conversion
                lat = 3.4 + (y - 900000) / 110540    # Rough conversion

                # Clamp to valid ranges
                lng = max(-180, min(180, lng))
                lat = max(-90, min(90, lat))

                pts.append([lng, lat])
            else:
                pts.append([x, y])
        except Exception:
            continue
    return pts


def wkt_to_geojson(geom_wkt) -> Optional[dict]:
    """Convierte un geom en WKT (POINT/LINESTRING/POLYGON/MULTIPOLYGON) a
    geometría GeoJSON dict. Devuelve None si no se puede parsear.

    Misma lógica que usaba geojson_indicador; extraída aquí para reuso
    (p. ej. export_geojson_superset).
    """
    if not geom_wkt or not isinstance(geom_wkt, str):
        return None
    txt = geom_wkt.strip()
    if not txt:
        return None
    upper = txt.upper()
    try:
        if upper.startswith('MULTIPOLYGON'):
            inner = txt[len('MULTIPOLYGON'):].strip()
            # Espera formato: (( (x y, ...), (hole...) ), ( ( ... ) ))
            # Quitamos el primer y último paréntesis
            if inner.startswith('(') and inner.endswith(')'):
                inner = inner[1:-1]
            polys = []
            depth = 0
            cur = ''
            # Particionar por polígonos de primer nivel
            for ch in inner:
                if ch == '(':
                    depth += 1
                if ch == ')':
                    depth -= 1
                cur += ch
                if depth == 0 and cur.strip():
                    poly_txt = cur.strip()
                    if poly_txt.startswith('(') and poly_txt.endswith(')'):
                        poly_txt = poly_txt[1:-1]
                    # Ahora poly_txt contiene: (ring1),(ring2)...
                    rings = []
                    ring_depth = 0
                    ring_cur = ''
                    for ch2 in poly_txt:
                        if ch2 == '(':
                            ring_depth += 1
                        if ch2 == ')':
                            ring_depth -= 1
                        ring_cur += ch2
                        if ring_depth == 0 and ring_cur.strip():
                            ring_txt = ring_cur.strip()
                            if ring_txt.startswith('(') and ring_txt.endswith(')'):
                                ring_txt = ring_txt[1:-1]
                            rings.append(_coords_from_ring(ring_txt))
                            ring_cur = ''
                    polys.append(rings)
                    cur = ''
            return {'type': 'MultiPolygon', 'coordinates': polys}

        if upper.startswith('POLYGON'):
            inner = txt[len('POLYGON'):].strip()
            if inner.startswith('(') and inner.endswith(')'):
                inner = inner[1:-1]
            rings = []
            depth = 0
            cur = ''
            for ch in inner:
                if ch == '(':
                    depth += 1
                if ch == ')':
                    depth -= 1
                cur += ch
                if depth == 0 and cur.strip():
                    ring_txt = cur.strip()
                    if ring_txt.startswith('(') and ring_txt.endswith(')'):
                        ring_txt = ring_txt[1:-1]
                    rings.append(_coords_from_ring(ring_txt))
                    cur = ''
            return {'type': 'Polygon', 'coordinates': rings}

        if upper.startswith('LINESTRING'):
            inner = txt[len('LINESTRING'):].strip()
            if inner.startswith('(') and inner.endswith(')'):
                inner = inner[1:-1]
            return {'type': 'LineString', 'coordinates': _coords_from_ring(inner)}

        if upper.startswith('POINT'):
            inner = txt[len('POINT'):].strip()
            if inner.startswith('(') and inner.endswith(')'):
                inner = inner[1:-1]
            parts = [p for p in inner.replace(',', ' ').split() if p]
            if len(parts) >= 2:
                return {'type': 'Point', 'coordinates': [float(parts[0]), float(parts[1])]}
    except Exception:
        return None
    return None


def extract_records(parsed: dict, code_field: str, name_field: str) -> List[dict]:
    """De un parsed de parse_*: [{codigo, nombre, wkt}] listos para ElementoGeo."""
    out = []
    for f in parsed['features']:
        props = f.get('props') or {}
        codigo = normalize(props.get(code_field)) if code_field else ''
        nombre = normalize(props.get(name_field)) if name_field else ''
        geom = f.get('geom')
        if geom and geom.get('type') == '__WKT__':
            wkt = geom.get('wkt')
        else:
            wkt = geojson_to_wkt(geom) if geom else None
        out.append({'codigo': codigo, 'nombre': nombre, 'wkt': wkt,
                    'valido': bool(codigo and nombre)})
    return out
