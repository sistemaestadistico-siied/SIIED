"""Reproyecta ElementoGeo.geom_wkt que quedó en coordenadas planas.

Causa: si al cargar una capa (cargar_elementos_geo) no había pyproj o el
.zip no traía .prj, el WKT se guardó en metros del CRS de origen. Luego
wkt_to_geojson aplica una aproximación lineal para el área de Cali que
desplaza los polígonos ~20 km. Este comando corrige el dato en la fuente:
EPSG plano -> WGS84 (EPSG:4326), solo en filas cuyas coordenadas claramente
no son grados (|x|>180 o |y|>90).

CRS nativo confirmado por el GeoServer oficial de IDESC
(ws-idesc.cali.gov.co, capa dapm:pdt_dpa_corregimientos): EPSG:6249
(MAGNA-SIRGAS malla urbana de Cali / Farallones). EPSG:3115 también 'cae'
en la zona pero introduce hasta ~19 m de error.

Uso:
    manage.py reproyectar_geom_wkt             # dry-run, solo cuenta
    manage.py reproyectar_geom_wkt --apply     # aplica en BD
    manage.py reproyectar_geom_wkt --srid 6249 --apply   # otro origen

Después de --apply regenerar el cache:
    manage.py export_geojson_superset
"""

import logging
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from indicadores.models import ElementoGeo

logger = logging.getLogger(__name__)

try:
    from pyproj import Transformer
except ImportError:  # pragma: no cover
    Transformer = None

# Par "x y" dentro del WKT. La coma/paréntesis entre pares impide que el
# regex cruce de un vértice al siguiente (no usa lookahead de separadores).
PAIR = re.compile(
    r'(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+'
    r'(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)')


class Command(BaseCommand):
    help = ("Reproyecta geom_wkt en coordenadas planas (default EPSG:6249 = "
            "malla urbana Cali/Farallones, CRS nativo de IDESC) a WGS84.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Escribe los cambios (sin esta bandera solo reporta).')
        parser.add_argument(
            '--srid', type=int, default=6249,
            help='EPSG del CRS de origen (default 6249).')

    def handle(self, *args, **options):
        if Transformer is None:
            self.stderr.write(
                self.style.ERROR('pyproj no instalado: pip install pyproj'))
            return

        srid = options['srid']
        transformer = Transformer.from_crs(
            f'EPSG:{srid}', 'EPSG:4326', always_xy=True)
        apply = options['apply']

        def reproyectar(wkt):
            def rep(m):
                x, y = float(m.group(1)), float(m.group(2))
                if abs(x) > 180 or abs(y) > 90:
                    lon, lat = transformer.transform(x, y)
                    return f'{lon:.7f} {lat:.7f}'
                return m.group(0)
            return PAIR.sub(rep, wkt)

        cambiados = 0
        qs = ElementoGeo.objects.exclude(
            geom_wkt__isnull=True).exclude(geom_wkt='')
        with transaction.atomic():
            for el in qs:
                nuevo = reproyectar(el.geom_wkt)
                if nuevo != el.geom_wkt:
                    cambiados += 1
                    if apply:
                        el.geom_wkt = nuevo
                        el.save(update_fields=['geom_wkt'])
            if not apply:
                transaction.set_rollback(True)

        verbo = 'reproyectados' if apply else 'pendientes de reproyectar'
        self.stdout.write(self.style.SUCCESS(
            f'{cambiados} geom_wkt {verbo} (EPSG:{srid} -> EPSG:4326).'))
        if apply:
            self.stdout.write(
                'Regenera el cache: manage.py export_geojson_superset')
