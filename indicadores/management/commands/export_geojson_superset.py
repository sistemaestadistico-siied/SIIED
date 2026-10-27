import json

from django.core.management.base import BaseCommand
from django.db import transaction

from indicadores.models import CapaGeo, ElementoGeo, CapaGeoJSON
from indicadores.utils_geo import wkt_to_geojson


class Command(BaseCommand):
    help = (
        "Materializa geometrías de ElementoGeo (WKT) en la tabla CapaGeoJSON "
        "como GeoJSON, para que Superset las consuma vía su conexión a la BD "
        "(JOIN por codigo o nombre en datasets virtuales → gráfico deck.gl "
        "Polygon / choropleth).\n"
        "Idempotente: hace upsert por (capa_geo, codigo) y elimina filas "
        "obsoletas de cada capa procesada."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--capa-id",
            type=int,
            default=None,
            help="ID de una CapaGeo específica (por defecto: todas las capas).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo muestra qué se exportaría, sin escribir en BD.",
        )

    def handle(self, *args, **options):
        capa_id = options["capa_id"]
        dry_run = options["dry_run"]

        capas = CapaGeo.objects.all().order_by("id")
        if capa_id:
            capas = capas.filter(id=capa_id)
            if not capas.exists():
                self.stderr.write(self.style.ERROR(f"CapaGeo id={capa_id} no existe"))
                return

        total_ok, total_sin_geom, total_error = 0, 0, 0

        for capa in capas:
            ok, sin_geom, error = 0, 0, 0
            vistos = set()
            elementos = ElementoGeo.objects.filter(capa_geo=capa).only(
                "codigo", "nombre", "geom_wkt"
            )

            with transaction.atomic():
                for el in elementos.iterator():
                    geom = wkt_to_geojson(el.geom_wkt)
                    if geom is None:
                        if not (el.geom_wkt or "").strip():
                            sin_geom += 1
                        else:
                            error += 1
                            self.stderr.write(
                                self.style.WARNING(
                                    f"  [capa {capa.id}] WKT inválido en "
                                    f"{el.codigo} - {el.nombre}"
                                )
                            )
                        continue
                    vistos.add(el.codigo)
                    if not dry_run:
                        CapaGeoJSON.objects.update_or_create(
                            capa_geo=capa,
                            codigo=el.codigo,
                            defaults={
                                "nombre": el.nombre,
                                "geojson": json.dumps(
                                    geom, ensure_ascii=False, separators=(",", ":")
                                ),
                            },
                        )
                    ok += 1

                # Eliminar filas exportadas que ya no existen en ElementoGeo
                stale = 0
                if not dry_run:
                    stale, _ = (
                        CapaGeoJSON.objects.filter(capa_geo=capa)
                        .exclude(codigo__in=vistos)
                        .delete()
                    )

            total_ok += ok
            total_sin_geom += sin_geom
            total_error += error
            tag = "[DRY-RUN] " if dry_run else ""
            self.stdout.write(
                f"{tag}Capa {capa.id} «{capa.nombre}»: "
                f"{ok} exportados, {sin_geom} sin geometría, "
                f"{error} con WKT inválido, {stale} obsoletos eliminados"
            )

        estilo = self.style.SUCCESS if total_error == 0 else self.style.WARNING
        self.stdout.write(
            estilo(
                f"Total: {total_ok} elementos exportados, "
                f"{total_sin_geom} sin geometría, {total_error} errores."
            )
        )
