from django.core.management.base import BaseCommand
from indicadores.models import Indicador, MenuSubtema, Dato, Grafico, GraficoSerie
from datetime import datetime
import csv
import os


class Command(BaseCommand):
    help = 'Carga los datos de los indicadores desde el CSV y genera gráficos automáticamente'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-path',
            type=str,
            default='docs/insumos/series_datos_indicadores.csv',
            help='Ruta al archivo CSV de datos de indicadores'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Ejecutar sin guardar cambios (solo mostrar lo que se haría)'
        )
        parser.add_argument(
            '--limpiar',
            action='store_true',
            help='Eliminar datos y gráficos existentes antes de cargar'
        )
    
    def handle(self, *args, **options):
        csv_path = options['csv_path']
        dry_run = options['dry_run']
        limpiar = options['limpiar']
        
        # Verificar que el archivo existe
        if not os.path.exists(csv_path):
            self.stdout.write(
                self.style.ERROR(f'El archivo {csv_path} no existe')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'Cargando datos desde: {csv_path}')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY-RUN: No se guardarán cambios')
            )
        
        # Estadísticas
        indicadores_procesados = set()
        datos_creados = 0
        graficos_creados = 0
        series_creadas = 0
        indicadores_no_encontrados = []
        errores = []
        
        # Leer el CSV y agrupar por indicador
        datos_por_indicador = {}
        
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                codigo_indicador = row.get('Codigo_Indicador', '').strip()
                nombre_indicador = row.get('Nombre_Indicador', '').strip()
                anio = row.get('Anio', '').strip()
                valor = row.get('Valor', '').strip()
                
                if not codigo_indicador or not anio or not valor:
                    continue
                
                if codigo_indicador not in datos_por_indicador:
                    datos_por_indicador[codigo_indicador] = {
                        'nombre': nombre_indicador,
                        'datos': []
                    }
                
                datos_por_indicador[codigo_indicador]['datos'].append({
                    'anio': anio,
                    'valor': valor
                })
        
        # Procesar cada indicador
        for codigo_indicador, info in datos_por_indicador.items():
            nombre_indicador = info['nombre']
            datos = info['datos']
            
            self.stdout.write(f'\nProcesando: {codigo_indicador} - {nombre_indicador}')
            self.stdout.write(f'  Datos a cargar: {len(datos)}')
            
            # Buscar el subtema por slug (código del indicador)
            try:
                subtema = MenuSubtema.objects.get(slug=codigo_indicador)
            except MenuSubtema.DoesNotExist:
                indicadores_no_encontrados.append(f'{codigo_indicador} (subtema no existe)')
                self.stdout.write(
                    self.style.WARNING(f'  ⚠ Subtema no encontrado: {codigo_indicador}')
                )
                continue
            
            # Obtener el único indicador del subtema
            indicadores_subtema = subtema.indicadores_todos()  # principal FK + adicionales M2M
            
            if indicadores_subtema.count() == 0:
                indicadores_no_encontrados.append(f'{codigo_indicador} (sin indicadores activos)')
                self.stdout.write(
                    self.style.WARNING(f'  ⚠ No hay indicadores activos en subtema: {subtema.nombre}')
                )
                continue
            elif indicadores_subtema.count() > 1:
                indicadores_no_encontrados.append(f'{codigo_indicador} ({indicadores_subtema.count()} indicadores)')
                self.stdout.write(
                    self.style.WARNING(
                        f'  ⚠ Subtema tiene {indicadores_subtema.count()} indicadores. Saltando por seguridad.'
                    )
                )
                continue
            
            indicador = indicadores_subtema.first()
            indicadores_procesados.add(indicador.id)
            
            # Limpiar datos existentes si se solicita
            if limpiar and not dry_run:
                datos_eliminados = Dato.objects.filter(indicador=indicador).count()
                graficos_eliminados = Grafico.objects.filter(indicador=indicador).count()
                
                Dato.objects.filter(indicador=indicador).delete()
                Grafico.objects.filter(indicador=indicador).delete()
                
                self.stdout.write(
                    self.style.WARNING(
                        f'  🗑️  Eliminados: {datos_eliminados} datos, {graficos_eliminados} gráficos'
                    )
                )
            
            # Crear los datos
            for dato_info in datos:
                try:
                    anio = int(dato_info['anio'])
                    valor = float(dato_info['valor'])
                    fecha_dato = datetime(anio, 12, 31).date()  # Usar 31 de diciembre del año
                    
                    if not dry_run:
                        Dato.objects.create(
                            indicador=indicador,
                            fecha_dato=fecha_dato,
                            valor_dato=valor
                        )
                    
                    datos_creados += 1
                    
                except (ValueError, TypeError) as e:
                    errores.append(f'{codigo_indicador} - Año {dato_info["anio"]}: {str(e)}')
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Error en dato: {str(e)}')
                    )
            
            # Crear el gráfico automáticamente
            if not dry_run:
                # Verificar si ya existe un gráfico para este indicador
                grafico_existente = Grafico.objects.filter(indicador=indicador).first()
                
                if not grafico_existente or limpiar:
                    grafico = Grafico.objects.create(
                        indicador=indicador,
                        nombre=f'Evolución de {indicador.nombre}',
                        descripcion=f'Serie temporal de {indicador.nombre}',
                        tipo_grafico='line',
                        activo=True,
                        titulo=indicador.nombre,
                        eje_x_titulo='Año',
                        eje_y_titulo=indicador.unidad_medida or 'Valor',
                        mostrar_leyenda=True,
                        posicion_leyenda='right',
                        mostrar_cuadricula=True,
                        begin_at_zero=False,
                        orden=1
                    )
                    
                    graficos_creados += 1
                    
                    # Crear la serie del gráfico (sin desagregaciones)
                    GraficoSerie.objects.create(
                        grafico=grafico,
                        nombre_personalizado=indicador.nombre,
                        orden=1
                    )
                    
                    series_creadas += 1
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Gráfico creado: {grafico.nombre}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠ Gráfico ya existe, no se creó uno nuevo')
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(f'  [DRY-RUN] Se crearía gráfico para: {indicador.nombre}')
                )
                graficos_creados += 1
                series_creadas += 1
            
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Procesado: {len(datos)} datos cargados')
            )
        
        # Resumen
        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS(f'\nIndicadores procesados: {len(indicadores_procesados)}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'Datos creados: {datos_creados}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'Gráficos creados: {graficos_creados}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'Series creadas: {series_creadas}')
        )
        
        if indicadores_no_encontrados:
            self.stdout.write(
                self.style.WARNING(
                    f'\nIndicadores no encontrados: {len(indicadores_no_encontrados)}'
                )
            )
            for codigo in indicadores_no_encontrados[:10]:
                self.stdout.write(f'  - {codigo}')
            if len(indicadores_no_encontrados) > 10:
                self.stdout.write(f'  ... y {len(indicadores_no_encontrados) - 10} más')
        
        if errores:
            self.stdout.write(
                self.style.ERROR(f'\nErrores encontrados: {len(errores)}')
            )
            for error in errores[:10]:
                self.stdout.write(f'  - {error}')
            if len(errores) > 10:
                self.stdout.write(f'  ... y {len(errores) - 10} más')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\nEsto fue un DRY-RUN. Ejecute sin --dry-run para guardar los cambios.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('\n¡Carga completada exitosamente!')
            )
