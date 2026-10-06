"""
Migra los indicadores CEC que son datos de consulta (directorios, nomencladores,
fichas territoriales) a conjuntos del Catálogo de Consulta.

Por cada indicador candidato:
  1. Crea un CatalogoConsulta con tipo y dominio de destino asignados.
  2. Vuelca sus Dato + desagregaciones a `filas` (JSON) del cuadro.
  3. Enlaza el indicador (indicador.catalogo_consulta) — conserva metadata y
     posición en la taxonomía CEC.
  4. Con --apply elimina los Dato del indicador ("se deja sin datos");
     --keep-datos los conserva congelados.

Uso:
    python manage.py migrar_consulta_cec              # dry-run
    python manage.py migrar_consulta_cec --apply
    python manage.py migrar_consulta_cec --apply --keep-datos
"""
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from indicadores.models import (
    Indicador, Dato, MenuDominio, CatalogoConsulta,
)


# Mapa indicador_id -> (tipo_consulta, slug de MenuDominio destino)
# Clasificación técnica acordada:
#   nomenclador        = tabla de equivalencias código ↔ territorio
#   directorio         = entidad con ubicación/contacto ("páginas amarillas")
#   capacidad          = inventario de capacidad instalada
#   ficha_territorial  = escalar de referencia del municipio
GEO = 'geografia-medio-ambiente-planificacion-y-ordenamiento-territorial'
SAL = 'salud-bienestar-social-y-demografia'
ECO = 'economia'
GOB = 'gobierno-seguridad-y-paz'

CANDIDATOS = {
    # ---- Nomencladores (Cap. 1 Generalidades) ----
    1492: ('nomenclador', GEO),       # Código único barrio/urbanización
    1493: ('nomenclador', GEO),       # Código único vereda/sector
    1494: ('nomenclador', GEO),       # Código único área de expansión
    # ---- Ficha técnica territorial (Cap. 1) ----
    1476: ('ficha_territorial', GEO), # Longitud oeste
    1478: ('ficha_territorial', GEO), # Superficie total
    1480: ('ficha_territorial', GEO), # Corregimientos (ha)
    # ---- Directorios con datos (Cap. 3) ----
    1547: ('directorio', GOB),        # Inspecciones de policía rural
    # ---- Directorios / capacidad, conchas del anuario (Cap. 4 y 5) ----
    1645: ('directorio', ECO),        # Plazas de mercado
    1648: ('directorio', SAL),        # Teatros
    1650: ('directorio', SAL),        # Museos
    1651: ('directorio', SAL),        # Bibliotecas
    1653: ('capacidad', SAL),         # Salas convenciones/auditorios
    1655: ('directorio', SAL),        # Salas de cine
    1657: ('directorio', SAL),        # Nombre teatros
    1658: ('capacidad', SAL),         # Capacidad sillas teatros
    1659: ('directorio', SAL),        # Grupos de teatro
    1660: ('directorio', SAL),        # Teatrinos
    1662: ('directorio', SAL),        # Nombre museos
    1663: ('directorio', SAL),        # Videotecas
    1664: ('directorio', SAL),        # Bibliotecas/centros de documentación
    1665: ('directorio', SAL),        # Salas de exposición y galerías
    1666: ('capacidad', SAL),         # Auditorios y salas para conferencias
    1667: ('directorio', SAL),        # Cadenas radiales y emisoras
    1668: ('directorio', SAL),        # Radio FM
    1669: ('directorio', SAL),        # Radio AM
    1670: ('directorio', SAL),        # Unidades recreativas
    1671: ('capacidad', ECO),         # Hoteles: cantidad/clasificación
    1672: ('capacidad', ECO),         # Hoteles: habitaciones
    1673: ('capacidad', ECO),         # Hoteles: camas
    1674: ('capacidad', ECO),         # Apartahoteles: cantidad/clasificación
    1675: ('capacidad', ECO),         # Apartahoteles: habitaciones
    1676: ('capacidad', ECO),         # Apartahoteles: camas
    1677: ('capacidad', ECO),         # Hostales: cantidad/clasificación
    1678: ('capacidad', ECO),         # Hostales: habitaciones
    1679: ('capacidad', ECO),         # Hostales: camas
    1680: ('directorio', ECO),        # Nombre hoteles/apartahoteles/hostales
    1681: ('capacidad', ECO),         # Habitaciones por unidad registrada
    1682: ('capacidad', ECO),         # Camas hoteles/apartahoteles/hostales
    1683: ('capacidad', ECO),         # Salas de conferencias por unidad
    1684: ('capacidad', ECO),         # Asientos de conferencias por unidad
    1685: ('capacidad', ECO),         # Ocupación hotel por categoría
    1686: ('capacidad', ECO),         # Tarifa promedio hotel por categoría
    # ---- Otros directorios ----
    1774: ('directorio', ECO),        # Oficinas bancarias
}

# Dominios de desagregación genéricos que no aportan columna al cuadro
DOMINIOS_IGNORAR = {'nombre_indicador'}


def _num(valor):
    """Decimal -> int/float serializable a JSON."""
    if valor is None:
        return None
    f = float(valor)
    return int(f) if f.is_integer() else f


def _dato_a_fila(dato, tipo):
    """Convierte un Dato (+ desagregaciones) en fila del cuadro de consulta."""
    fila = {}
    for desag in list(dato.desagregaciones_geograficas.all()) + \
                list(dato.desagregaciones_tematicas.all()):
        dom = desag.dominio.nombre if desag.dominio else 'desagregacion'
        if dom in DOMINIOS_IGNORAR:
            continue
        col = dom
        i = 2
        while col in fila:  # mismo dominio dos veces -> sufijo
            col = f'{dom}_{i}'
            i += 1
        fila[col] = desag.nombre

    if tipo == 'nomenclador':
        fila['codigo'] = _num(dato.valor_dato)
    else:
        fila['valor'] = _num(dato.valor_dato)

    if dato.fecha_dato:
        fila['anio'] = dato.fecha_dato.year
    return fila


class Command(BaseCommand):
    help = 'Migra indicadores CEC de consulta al Catálogo de Consulta (dry-run por defecto)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Aplica los cambios (sin este flag solo muestra el plan)'
        )
        parser.add_argument(
            '--keep-datos', action='store_true',
            help='No borra los Dato del indicador tras enlazarlo'
        )
        parser.add_argument(
            '--dominio', type=str, default=None,
            help='Slug de MenuDominio destino forzado para TODOS los conjuntos'
        )

    def handle(self, *args, **options):
        apply_ = options['apply']
        keep = options['keep_datos']
        forzar_dominio = options['dominio']

        dominios = {d.slug: d for d in MenuDominio.objects.filter(activo=True)}
        cec = MenuDominio.objects.filter(slug__iexact='CEC').first()

        self.stdout.write(
            '== Migración a Catálogo de Consulta =='
            + (' [APPLY]' if apply_ else ' [DRY-RUN]')
        )

        for ind_id, (tipo, slug_destino) in sorted(CANDIDATOS.items()):
            try:
                ind = Indicador.objects.get(pk=ind_id)
            except Indicador.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'ind{ind_id}: NO EXISTE — omitido'))
                continue

            slug = forzar_dominio or slug_destino
            dominio = dominios.get(slug)
            if not dominio:
                self.stdout.write(self.style.ERROR(
                    f'ind{ind_id}: dominio destino {slug!r} no existe/activo — omitido'
                ))
                continue

            n_datos = ind.datos.count()
            ya_enlazado = bool(ind.catalogo_consulta_id)
            self.stdout.write(
                f'ind{ind_id} {ind.nombre[:60]!r}\n'
                f'   tipo={tipo} dominio={dominio.nombre!r} datos={n_datos} '
                f'{"YA ENLAZADO" if ya_enlazado else ""}'
            )

            if not apply_:
                continue

            with transaction.atomic():
                conjunto, creado = CatalogoConsulta.objects.get_or_create(
                    nombre=ind.nombre[:255],
                    dominio=dominio,
                    defaults={
                        'descripcion': ind.descripcion_indicador or ind.nombre,
                        'tipo_consulta': tipo,
                        'activo': True,
                    },
                )
                if not creado:
                    conjunto.tipo_consulta = tipo

                # Convertir Dato + desags -> filas del cuadro
                filas = [
                    _dato_a_fila(d, tipo)
                    for d in ind.datos.prefetch_related(
                        'desagregaciones_geograficas__dominio',
                        'desagregaciones_tematicas__dominio',
                    ).order_by('fecha_dato')
                ]
                # Columnas en orden de aparición
                columnas = []
                for f in filas:
                    for k in f:
                        if k not in columnas:
                            columnas.append(k)
                conjunto.columnas = columnas
                conjunto.filas = filas
                conjunto.save()

                # Enlazar indicador
                ind.catalogo_consulta = conjunto
                ind.save(update_fields=['catalogo_consulta'])

                # "Se deja sin datos": limpiar Dato salvo --keep-datos
                if n_datos and not keep:
                    ind.datos.all().delete()

                self.stdout.write(self.style.SUCCESS(
                    f'   -> conjunto cat{conjunto.pk} {"creado" if creado else "reusado"} '
                    f'con {len(filas)} filas; indicador enlazado'
                    + ('' if keep or not n_datos else f'; {n_datos} Dato eliminados')
                ))

        if not apply_:
            self.stdout.write(self.style.NOTICE(
                '\nDry-run: nada se modificó. Usa --apply para ejecutar.'
            ))
