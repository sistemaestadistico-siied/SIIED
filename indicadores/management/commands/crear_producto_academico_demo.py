"""
Crea un ProductoAcademico de demostración que usa TODOS los bloques del módulo.
Sirve para verificar visualmente cada componente después de migraciones o deploy.

Uso:
    python manage.py crear_producto_academico_demo
    python manage.py crear_producto_academico_demo --delete
"""

import os
import json
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from indicadores.models import (
    ProductoAcademico,
    SeccionPaper,
    Indicador,
    ConjuntoDatos,
    DocumentoInfraestructura,
    SistemaInformacion,
    OperacionEstadistica,
    MenuSubtema,
    Organismo,
)


class Command(BaseCommand):
    help = 'Crea un producto académico demo con todos los bloques del módulo para verificación visual.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            dest='delete',
            default=False,
            help='Eliminar el producto demo existente antes de crearlo.',
        )

    def handle(self, *args, **options):
        slug_demo = 'demo-producto-estadistico-cali-2024'

        # ------------------------------------------------------------------
        # Borrar si existe y --delete
        # ------------------------------------------------------------------
        if options['delete']:
            self.stdout.write(self.style.WARNING(f'Buscando producto con slug {slug_demo}...'))
            existing = ProductoAcademico.objects.filter(slug=slug_demo).first()
            if existing:
                count = existing.secciones.count()
                existing.delete()
                self.stdout.write(self.style.SUCCESS(f'Eliminado producto demo y {count} secciones.'))
            else:
                self.stdout.write('No existía producto demo.')

        # ------------------------------------------------------------------
        # Validar prerequisitos
        # ------------------------------------------------------------------
        indicadores = list(Indicador.objects.filter(activo=True).order_by('id')[:3])
        conjunto_datos = ConjuntoDatos.objects.order_by('id').first()
        documento = DocumentoInfraestructura.objects.order_by('id').first()
        sistema = SistemaInformacion.objects.order_by('id').first()
        operacion = OperacionEstadistica.objects.order_by('id').first()
        organismo = Organismo.objects.order_by('id').first()
        subtemas = list(MenuSubtema.objects.order_by('id')[:3])

        self.stdout.write('Prerequisitos encontrados:')
        self.stdout.write(f'  - Indicadores activos: {len(indicadores)}')
        self.stdout.write(f'  - conjunto_datos: {conjunto_datos.nombre if conjunto_datos else "NINGUNA"}')
        self.stdout.write(f'  - DocumentoInfra: {documento.nombre if documento else "NINGUNO"}')
        self.stdout.write(f'  - SistemaInfo: {sistema.nombre if sistema else "NINGUNO"}')
        self.stdout.write(f'  - OperacionEstadistica: {operacion.nombre if operacion else "NINGUNA"}')
        self.stdout.write(f'  - Subtemas: {len(subtemas)}')

        # ------------------------------------------------------------------
        # Crear / reutilizar ProductoAcademico
        # ------------------------------------------------------------------
        producto, created = ProductoAcademico.objects.update_or_create(
            slug=slug_demo,
            defaults={
                'titulo': 'Censo de Población y Vivienda — Santiago de Cali 2024',
                'resumen': (
                    'El Censo de Población y Vivienda 2024 del Distrito de Santiago de Cali '
                    'se realizó entre febrero y marzo de 2024. Participaron más de 2.800 '
                    'empadronadores que recorrieron las 22 comunas del distrito para obtener '
                    'información sobre población, hogares y viviendas.'
                ),
                'palabras_clave': 'censo, población, vivienda, Cali, demografía, CPV 2024',
                'area_tematica': 'Demografía · Estadística Social',
                'autor': 'Subdirección de Estadística — DAPD',
                'institucion': 'Departamento Administrativo de Planeación Distrital (DAPD)',
                'estado': 'publicado',
                # --- campos nuevos del modo INEGI ---
                'es_producto_estadistico': True,
                'cobertura_geografica': 'Distrito de Santiago de Cali',
                'periodo_referencia': '15 de febrero – 15 de marzo de 2024',
                'diseno_conceptual': (
                    '<p>El censo se basa en un <strong>diseño de enumeración completa</strong> de '
                    'viviendas, hogares y personas. Se aplicó un cuestionario censal básico (CCB) '
                    'a todas las viviendas y un cuestionario censal ampliado (CCA) al 15 % con '
                    'muestreo estratificado por comuna.</p>'
                ),
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'Producto creado: {producto.titulo}'))
        else:
            self.stdout.write(self.style.WARNING(f'Producto actualizado: {producto.titulo}'))

        # Asignar relaciones (solo si existen)
        if operacion:
            producto.operacion = operacion
        if organismo:
            producto.organismo = organismo
        if subtemas:
            producto.temas_relacionados.set(subtemas)
        if indicadores:
            producto.indicadores_derivados.set(indicadores)
        producto.save()

        # ------------------------------------------------------------------
        # Crear secciones — una por tipo de bloque
        # ------------------------------------------------------------------
        SECCIONES_CONFIG = [
            # (tipo_bloque, tipo_seccion, orden, subnumero, titulo, kwargs extras)
            {
                'tipo_bloque': 'texto',
                'tipo_seccion': 'introduccion',
                'orden': 1,
                'titulo': 'Importancia',
                'contenido': (
                    '<p>El CPV 2024 constituye la principal fuente de información sobre la '
                    'población, los hogares y las viviendas del Distrito de Santiago de Cali. '
                    'Sus resultados son insumo indispensable para la planificación del desarrollo, '
                    'la asignación de recursos públicos y el diseño de políticas sociales y urbanas.</p>'
                ),
            },
            {
                'tipo_bloque': 'texto',
                'tipo_seccion': 'introduccion',
                'orden': 2,
                'titulo': 'Antecedentes',
                'contenido': (
                    '<p>El último censo distrital se realizó en 2018. Desde entonces, la ciudad '
                    'ha experimentado transformaciones demográficas significativas: crecimiento '
                    'poblacional acelerado en comunas periféricas y envejecimiento en sectores '
                    'tradicionales.</p>'
                ),
            },
            {
                'tipo_bloque': 'texto',
                'tipo_seccion': 'introduccion',
                'orden': 3,
                'titulo': 'Objetivos',
                'contenido': (
                    '<ul><li>Determinar el tamaño, distribución y estructura de la población calidense.</li>'
                    '<li>Identificar condiciones de vivienda y acceso a servicios públicos domiciliarios.</li>'
                    '<li>Generar insumos para los ODS locales y el Plan de Desarrollo Distrital.</li></ul>'
                ),
            },
            {
                'tipo_bloque': 'resultado_destacado',
                'tipo_seccion': 'resultados',
                'orden': 4,
                'titulo': 'Población total del Distrito',
                'indicador': indicadores[0] if indicadores else None,
                'config': json.dumps({'anio_default': 2024}),
            },
            {
                'tipo_bloque': 'grafico_indicador',
                'tipo_seccion': 'resultados',
                'orden': 5,
                'subnumero': '4.1',
                'titulo': 'Población por comuna',
                'indicador': indicadores[0] if indicadores else None,
                'config': json.dumps({'tipo': 'barras', 'anio_default': 2024}),
            },
            {
                'tipo_bloque': 'mapa_indicador',
                'tipo_seccion': 'resultados',
                'orden': 6,
                'subnumero': '4.2',
                'titulo': 'Mapa de densidad poblacional',
                'indicador': indicadores[0] if indicadores else None,
                'config': json.dumps({'tipo_mapa': 'choropleth', 'anio_default': 2024}),
            },
            {
                'tipo_bloque': 'tabla_datos_indicador',
                'tipo_seccion': 'resultados',
                'orden': 7,
                'subnumero': '4.3',
                'titulo': 'Tabulado de población por comuna',
                'indicador': indicadores[0] if indicadores else None,
                'config': json.dumps({'limite_filas': 50, 'anio_default': 2024}),
            },
            {
                'tipo_bloque': 'tabla_microdata',
                'tipo_seccion': 'resultados',
                'orden': 8,
                'subnumero': '4.4',
                'titulo': 'Muestra de conjunto_datos — CPV 2024',
                'conjunto_datos': conjunto_datos,
                'config': json.dumps({'limite_filas': 20}),
            },
            {
                'tipo_bloque': 'ficha_indicador',
                'tipo_seccion': 'resultados',
                'orden': 9,
                'subnumero': '4.5',
                'titulo': 'Ficha técnica del indicador',
                'indicador': indicadores[0] if indicadores else None,
            },
            {
                'tipo_bloque': 'documento_infraestructura',
                'tipo_seccion': 'metodologia',
                'orden': 10,
                'titulo': 'Metodología del censo',
                'documento': documento,
            },
            {
                'tipo_bloque': 'sistema_informacion',
                'tipo_seccion': 'metodologia',
                'orden': 11,
                'titulo': 'Herramientas de consulta',
                'sistema': sistema,
            },
            {
                'tipo_bloque': 'publicacion_relacionada',
                'tipo_seccion': 'referencias',
                'orden': 12,
                'titulo': 'Publicaciones relacionadas',
                # Las publicaciones se asignan después si hay otro ProductoAcademico
            },
            {
                'tipo_bloque': 'formula',
                'tipo_seccion': 'anexo',
                'orden': 13,
                'titulo': 'Fórmula de crecimiento poblacional',
                'contenido': (
                    '<p>La tasa de crecimiento anual se calcula como:</p>'
                    '<p style="text-align:center;font-size:1.2rem;">'
                    '<strong>r = ln(P<sub>t</sub> / P<sub>0</sub>) / t</strong></p>'
                    '<p>Donde <em>P<sub>t</sub></em> es la población final, '
                    '<em>P<sub>0</sub></em> la población inicial y <em>t</em> el número de años.</p>'
                ),
            },
            {
                'tipo_bloque': 'tabla_datos',
                'tipo_seccion': 'anexo',
                'orden': 14,
                'titulo': 'Cuadro resumen de indicadores',
                'contenido': (
                    '<table><thead><tr><th>Indicador</th><th>Valor</th><th>Año</th></tr></thead>'
                    '<tbody><tr><td>Población total</td><td>2.634.317</td><td>2024</td></tr>'
                    '<tr><td>Hogares</td><td>845.791</td><td>2024</td></tr>'
                    '<tr><td>Viviendas</td><td>912.234</td><td>2024</td></tr></tbody></table>'
                ),
            },
        ]

        # Limpiar secciones viejas del producto (si las hay) para evitar duplicados
        producto.secciones.all().delete()

        for cfg in SECCIONES_CONFIG:
            seccion = SeccionPaper.objects.create(
                producto=producto,
                tipo_seccion=cfg['tipo_seccion'],
                numero_orden=cfg['orden'],
                subnumero=cfg.get('subnumero', ''),
                titulo=cfg['titulo'],
                tipo_bloque=cfg['tipo_bloque'],
                contenido=cfg.get('contenido', ''),
                indicador_vinculado=cfg.get('indicador'),
                conjunto_datos_vinculado=cfg.get('conjunto_datos'),
                documento_vinculado=cfg.get('documento'),
                sistema_vinculado=cfg.get('sistema'),
                configuracion_grafico=cfg.get('config'),
            )

            # Publicaciones relacionadas (M2M)
            if cfg['tipo_bloque'] == 'publicacion_relacionada':
                otros_productos = list(
                    ProductoAcademico.objects.exclude(id=producto.id).order_by('-created_at')[:3]
                )
                if otros_productos:
                    seccion.publicaciones_relacionadas.set(otros_productos)
                    self.stdout.write(f'  → Seccion "{seccion.titulo}": vinculadas {len(otros_productos)} publicaciones')
                else:
                    self.stdout.write(self.style.WARNING(f'  → Seccion "{seccion.titulo}": no hay otros ProductoAcademico para vincular'))

            self.stdout.write(f'  ✓ Seccion {seccion.numero_orden}: {seccion.titulo} ({seccion.tipo_bloque})')

        # ------------------------------------------------------------------
        # Resumen
        # ------------------------------------------------------------------
        total_secciones = producto.secciones.count()
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Producto demo listo: {producto.titulo}'
        ))
        self.stdout.write(f'   Slug: {producto.slug}')
        self.stdout.write(f'   URL: {producto.get_absolute_url()}')
        self.stdout.write(f'   Secciones creadas: {total_secciones}')
        self.stdout.write(f'   Modo INEGI: {producto.es_producto_estadistico}')
        self.stdout.write(f'   Indicadores vinculados: {producto.indicadores_derivados.count()}')
        self.stdout.write(f'   Temas relacionados: {producto.temas_relacionados.count()}')

        if not indicadores:
            self.stdout.write(self.style.WARNING('\n⚠️  ADVERTENCIA: No hay indicadores activos. Algunos bloques quedarán vacíos.'))
        if not conjunto_datos:
            self.stdout.write(self.style.WARNING('⚠️  ADVERTENCIA: No hay conjunto_datos. Bloque tabla_microdata quedará vacío.'))
        if not documento:
            self.stdout.write(self.style.WARNING('⚠️  ADVERTENCIA: No hay DocumentoInfraestructura. Bloque documento quedará vacío.'))
        if not sistema:
            self.stdout.write(self.style.WARNING('⚠️  ADVERTENCIA: No hay SistemaInformacion. Bloque sistema quedará vacío.'))
