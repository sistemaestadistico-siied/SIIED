#!/usr/bin/env python3
"""
Exporta todo el catálogo existente (indicadores, temas, subtemas, dominios)
a archivos CSV/Excel para que el usuario pueda ver qué ya está cargado
antes de crear nuevos indicadores.

Uso en producción:
    python manage.py exportar_catalogo_existente --output-dir /tmp/catalogo

Genera:
    1. indicadores_existentes.csv      — todos los indicadores con código, nombre, tema, subtema, dominios
    2. temas_existentes.csv            — temas ya creados
    3. subtemas_existentes.csv         — subtemas ya creados
    4. dominios_desagregacion.csv      — dominios de desagregación ya creados
    5. catalogo_completo.xlsx          — todas las hojas anteriores en un solo Excel
"""

import os
import csv
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Exporta el catálogo existente de indicadores, temas, subtemas y dominios a CSV/Excel"

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default=os.path.join(settings.BASE_DIR, 'tmp_catalogo'),
            help='Directorio donde se guardarán los archivos',
        )
        parser.add_argument(
            '--formato',
            type=str,
            choices=['csv', 'excel', 'ambos'],
            default='ambos',
            help='Formato de salida: csv, excel o ambos',
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        formato = options['formato']
        os.makedirs(output_dir, exist_ok=True)

        self.stdout.write(self.style.NOTICE(f"Exportando catálogo a: {output_dir}"))

        # CSVs
        if formato in ('csv', 'ambos'):
            self._exportar_csv(output_dir)

        # Excel
        if formato in ('excel', 'ambos'):
            self._exportar_excel(output_dir)

        self.stdout.write(self.style.SUCCESS("Exportación completada."))

    def _exportar_csv(self, output_dir):
        from indicadores.models import (
            Indicador, MenuTema, MenuSubtema, DominioDesagregacion
        )

        # -------------------------------------------------------------------
        # 1. Indicadores existentes
        # -------------------------------------------------------------------
        csv_path = os.path.join(output_dir, 'indicadores_existentes.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'codigo_indicador', 'nombre', 'sigla', 'grupo_indicador',
                'dominio', 'tema', 'subtema', 'slug_subtema',
                'subtemas_adicionales',
                'dominios_tematicos', 'dominios_geograficos',
                'alcance_tematico', 'cobertura_geografica',
                'unidad_medida', 'frecuencia_difusion', 'fuente_datos',
                'organismo_responsable', 'activo'
            ])

            for ind in Indicador.objects.select_related(
                'subtema__tema__dominio', 'organismo_responsable'
            ).prefetch_related(
                'subtemas_adicionales',
                'dominios_desagregacion_tematica',
                'dominios_desagregacion_geografica'
            ).order_by('subtema__tema__dominio__nombre', 'subtema__tema__nombre', 'subtema__nombre', 'nombre'):

                dominios_t = '|'.join(
                    d.nombre for d in ind.dominios_desagregacion_tematica.all()
                )
                dominios_g = '|'.join(
                    d.nombre for d in ind.dominios_desagregacion_geografica.all()
                )

                writer.writerow([
                    ind.id,
                    ind.codigo_indicador or '',
                    ind.nombre,
                    ind.sigla or '',
                    ind.grupo_indicador or '',
                    ind.subtema.tema.dominio.nombre if ind.subtema else '',
                    ind.subtema.tema.nombre if ind.subtema else '',
                    ind.subtema.nombre if ind.subtema else '',
                    ind.subtema.slug if ind.subtema else '',
                    '; '.join(s.nombre for s in ind.subtemas_adicionales.all()),
                    dominios_t,
                    dominios_g,
                    ind.alcance_tematico or '',
                    ind.cobertura_geografica or '',
                    ind.unidad_medida or '',
                    ind.frecuencia_difusion or '',
                    ind.fuente_datos or '',
                    ind.organismo_responsable.nombre if ind.organismo_responsable else '',
                    'Sí' if ind.activo else 'No',
                ])

        self.stdout.write(f"  {self.style.SUCCESS('✓')} indicadores_existentes.csv")

        # -------------------------------------------------------------------
        # 2. Temas existentes
        # -------------------------------------------------------------------
        csv_path = os.path.join(output_dir, 'temas_existentes.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'nombre', 'slug', 'dominio', 'dominio_slug', 'descripcion', 'orden', 'activo'])
            for t in MenuTema.objects.select_related('dominio').order_by('dominio__nombre', 'nombre'):
                writer.writerow([
                    t.id, t.nombre, t.slug,
                    t.dominio.nombre if t.dominio else '',
                    t.dominio.slug if t.dominio else '',
                    t.descripcion or '', t.orden, 'Sí' if t.activo else 'No'
                ])
        self.stdout.write(f"  {self.style.SUCCESS('✓')} temas_existentes.csv")

        # -------------------------------------------------------------------
        # 3. Subtemas existentes
        # -------------------------------------------------------------------
        csv_path = os.path.join(output_dir, 'subtemas_existentes.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'nombre', 'slug', 'tema', 'tema_slug',
                'dominio', 'descripcion', 'orden', 'activo'
            ])
            for st in MenuSubtema.objects.select_related('tema__dominio').order_by(
                'tema__dominio__nombre', 'tema__nombre', 'nombre'
            ):
                writer.writerow([
                    st.id, st.nombre, st.slug,
                    st.tema.nombre if st.tema else '',
                    st.tema.slug if st.tema else '',
                    st.tema.dominio.nombre if st.tema and st.tema.dominio else '',
                    st.descripcion or '', st.orden,
                    'Sí' if st.activo else 'No',
                ])
        self.stdout.write(f"  {self.style.SUCCESS('✓')} subtemas_existentes.csv")

        # -------------------------------------------------------------------
        # 4. Dominios de desagregación existentes
        # -------------------------------------------------------------------
        csv_path = os.path.join(output_dir, 'dominios_desagregacion.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'nombre', 'tipo', 'nivel_geografico', 'tipo_agregacion_total'])
            for d in DominioDesagregacion.objects.order_by('tipo', 'nombre'):
                writer.writerow([
                    d.id, d.nombre, d.tipo,
                    d.nivel_geografico.nombre if d.nivel_geografico else '',
                    d.tipo_agregacion_total,
                ])
        self.stdout.write(f"  {self.style.SUCCESS('✓')} dominios_desagregacion.csv")

    def _exportar_excel(self, output_dir):
        try:
            import pandas as pd
        except ImportError:
            self.stdout.write(self.style.ERROR("pandas no está instalado. Se omite Excel."))
            return

        from indicadores.models import (
            Indicador, MenuTema, MenuSubtema, DominioDesagregacion
        )

        xlsx_path = os.path.join(output_dir, 'catalogo_completo.xlsx')

        # --- Hoja 1: Indicadores ---
        rows = []
        for ind in Indicador.objects.select_related(
            'subtema__tema__dominio', 'organismo_responsable'
        ).prefetch_related(
            'subtemas_adicionales',
            'dominios_desagregacion_tematica',
            'dominios_desagregacion_geografica'
        ).order_by('subtema__tema__dominio__nombre', 'subtema__tema__nombre', 'subtema__nombre', 'nombre'):

            dominios_t = '|'.join(d.nombre for d in ind.dominios_desagregacion_tematica.all())
            dominios_g = '|'.join(d.nombre for d in ind.dominios_desagregacion_geografica.all())

            rows.append({
                'id': ind.id,
                'codigo_indicador': ind.codigo_indicador or '',
                'nombre': ind.nombre,
                'sigla': ind.sigla or '',
                'grupo_indicador': ind.grupo_indicador or '',
                'dominio': ind.subtema.tema.dominio.nombre if ind.subtema else '',
                'tema': ind.subtema.tema.nombre if ind.subtema else '',
                'subtema': ind.subtema.nombre if ind.subtema else '',
                'slug_subtema': ind.subtema.slug if ind.subtema else '',
                'subtemas_adicionales': '; '.join(
                    s.nombre for s in ind.subtemas_adicionales.all()),
                'dominios_tematicos': dominios_t,
                'dominios_geograficos': dominios_g,
                'alcance_tematico': ind.alcance_tematico or '',
                'cobertura_geografica': ind.cobertura_geografica or '',
                'unidad_medida': ind.unidad_medida or '',
                'periodicidad': ind.frecuencia_difusion or '',
                'fuente_datos': ind.fuente_datos or '',
                'organismo_responsable': ind.organismo_responsable.nombre if ind.organismo_responsable else '',
                'activo': 'Sí' if ind.activo else 'No',
            })

        df_ind = pd.DataFrame(rows)

        # --- Hoja 2: Temas ---
        df_temas = pd.DataFrame([
            {
                'id': t.id, 'nombre': t.nombre, 'slug': t.slug,
                'dominio': t.dominio.nombre if t.dominio else '',
                'dominio_slug': t.dominio.slug if t.dominio else '',
                'descripcion': t.descripcion or '',
                'orden': t.orden,
                'activo': 'Sí' if t.activo else 'No',
            }
            for t in MenuTema.objects.select_related('dominio').order_by('dominio__nombre', 'nombre')
        ])

        # --- Hoja 3: Subtemas ---
        df_subtemas = pd.DataFrame([
            {
                'id': st.id, 'nombre': st.nombre, 'slug': st.slug,
                'tema': st.tema.nombre if st.tema else '',
                'tema_slug': st.tema.slug if st.tema else '',
                'dominio': st.tema.dominio.nombre if st.tema and st.tema.dominio else '',
                'descripcion': st.descripcion or '',
                'orden': st.orden,
                'activo': 'Sí' if st.activo else 'No',
            }
            for st in MenuSubtema.objects.select_related('tema__dominio').order_by(
                'tema__dominio__nombre', 'tema__nombre', 'nombre'
            )
        ])

        # --- Hoja 4: Dominios ---
        df_dominios = pd.DataFrame([
            {
                'id': d.id, 'nombre': d.nombre, 'tipo': d.tipo,
                'nivel_geografico': d.nivel_geografico.nombre if d.nivel_geografico else '',
                'tipo_agregacion_total': d.tipo_agregacion_total,
            }
            for d in DominioDesagregacion.objects.order_by('tipo', 'nombre')
        ])

        with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
            df_ind.to_excel(writer, sheet_name='Indicadores', index=False)
            df_temas.to_excel(writer, sheet_name='Temas', index=False)
            df_subtemas.to_excel(writer, sheet_name='Subtemas', index=False)
            df_dominios.to_excel(writer, sheet_name='Dominios', index=False)

        self.stdout.write(f"  {self.style.SUCCESS('✓')} catalogo_completo.xlsx")
