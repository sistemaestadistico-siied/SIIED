from django.core.management.base import BaseCommand
from indicadores.models import Indicador, MenuSubtema, ConjuntoDatos, VariableConjuntoDatos, resolver_organismo_por_nombre
from django.core.files.base import ContentFile
import csv
import os


class Command(BaseCommand):
    help = 'Crea items de conjunto_datos (con CSV vacío) y sus Variables desde ficha_tecnica_conjunto_datos.csv'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-path',
            type=str,
            default='docs/insumos/ficha_tecnica_conjunto_datos.csv',
            help='Ruta al archivo CSV de ficha técnica de conjunto_datos'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Ejecutar sin guardar cambios (solo mostrar lo que se haría)'
        )
        parser.add_argument(
            '--limpiar',
            action='store_true',
            help='Eliminar conjunto_datos y variables existentes antes de crear'
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
            self.style.SUCCESS(f'Procesando desde: {csv_path}')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY-RUN: No se guardarán cambios')
            )
        
        # Estadísticas
        indicadores_procesados = set()
        conjunto_datos_creados = 0
        variables_creadas = 0
        indicadores_no_encontrados = []
        errores = []
        
        # Leer el CSV y agrupar por indicador
        datos_por_indicador = {}
        
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                codigo_indicador = row.get('Codigo_Indicador', '').strip()
                nombre_indicador = row.get('Nombre_Indicador', '').strip()
                codigo_variable = row.get('Codigo_Variable', '').strip()
                
                if not codigo_indicador or not codigo_variable:
                    continue
                
                if codigo_indicador not in datos_por_indicador:
                    datos_por_indicador[codigo_indicador] = {
                        'nombre': nombre_indicador,
                        'variables': []
                    }
                
                datos_por_indicador[codigo_indicador]['variables'].append(row)
        
        # Procesar cada indicador
        for codigo_indicador, info in datos_por_indicador.items():
            nombre_indicador = info['nombre']
            variables = info['variables']
            
            self.stdout.write(f'\n{"="*70}')
            self.stdout.write(f'Procesando: {codigo_indicador}')
            self.stdout.write(f'Nombre: {nombre_indicador}')
            self.stdout.write(f'Variables: {len(variables)}')
            
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
            indicadores_subtema = Indicador.objects.filter(subtema=subtema, activo=True)
            
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
            
            # Limpiar si se solicita
            if limpiar and not dry_run:
                variables_eliminadas = VariableConjuntoDatos.objects.filter(indicador=indicador).count()
                conjunto_datos_eliminados = 0
                
                VariableConjuntoDatos.objects.filter(indicador=indicador).delete()
                
                if indicador.conjunto_datos:
                    conjunto_datos_eliminados = 1
                    indicador.conjunto_datos.delete()
                
                if variables_eliminadas > 0 or conjunto_datos_eliminados > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  🗑️  Eliminados: {conjunto_datos_eliminados} conjunto_datos, {variables_eliminadas} variables'
                        )
                    )
            
            # PASO 1: Crear conjunto_datos (si no existe)
            conjunto_datos = None
            
            if not dry_run:
                # Verificar si ya existe conjunto_datos
                if hasattr(indicador, 'conjunto_datos') and indicador.conjunto_datos:
                    conjunto_datos = indicador.conjunto_datos
                    self.stdout.write(
                        self.style.WARNING(f'  ℹ️  conjunto_datos ya existe: {conjunto_datos.nombre}')
                    )
                else:
                    # Crear CSV vacío con headers basados en las variables
                    csv_headers = ['Codigo_Variable'] + [v.get('Codigo_Variable', '') for v in variables]
                    csv_content = ','.join(csv_headers) + '\n'
                    
                    # Crear el objeto conjunto_datos
                    conjunto_datos = ConjuntoDatos.objects.create(
                        nombre=f'conjunto_datos - {nombre_indicador}',
                        descripcion=f'Archivo de conjunto_datos para el indicador: {nombre_indicador}'
                    )
                    
                    # Crear archivo CSV vacío
                    csv_filename = f'conjunto_datos_{codigo_indicador}.csv'
                    conjunto_datos.archivo_csv.save(
                        csv_filename,
                        ContentFile(csv_content.encode('utf-8')),
                        save=True
                    )
                    
                    # Asociar al indicador
                    indicador.conjunto_datos = conjunto_datos
                    indicador.save()
                    
                    conjunto_datos_creados += 1
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ conjunto_datos creado: {conjunto_datos.nombre}')
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f'    Archivo: {csv_filename} (vacío, listo para subir datos)')
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(f'  [DRY-RUN] Se crearía conjunto_datos: {nombre_indicador}')
                )
                conjunto_datos_creados += 1
            
            # PASO 2: Crear Variables de conjunto_datos
            for idx, variable_info in enumerate(variables, start=1):
                try:
                    if not dry_run:
                        VariableConjuntoDatos.objects.create(
                            indicador=indicador,
                            codigo_variable=variable_info.get('Codigo_Variable', '').strip(),
                            nombre_variable=variable_info.get('Nombre_Variable', '').strip(),
                            definicion_conceptual=variable_info.get('Definicion_Conceptual', '').strip(),
                            poblacion_objetivo=variable_info.get('Poblacion_Objetivo', '').strip() or None,
                            cobertura_geografica=variable_info.get('Cobertura_Geografica', '').strip() or None,
                            desagregacion_geografica=variable_info.get('Desagregacion_Geografica', '').strip() or None,
                            desagregacion_tematica=variable_info.get('Desagregacion_Tematica', '').strip() or None,
                            tipo_dato=variable_info.get('Tipo_Dato', '').strip() or None,
                            dominio_dato=variable_info.get('Dominio_Dato', '').strip() or None,
                            unidad_medida=variable_info.get('Unidad_Medida', '').strip() or None,
                            tipo_variable_estadistica=variable_info.get('Tipo_Variable_Estadistica', '').strip() or None,
                            fuente_datos=variable_info.get('Fuente_Datos', '').strip() or None,
                            periodicidad=variable_info.get('Periodicidad', '').strip() or None,
                            observaciones=variable_info.get('Observaciones', '').strip() or None,
                            referencias=variable_info.get('Referencias', '').strip() or None,
                            organismo_productor=resolver_organismo_por_nombre(variable_info.get('Organismo_Productor', '').strip()),
                            organismo_productor_legado=(
                                '' if resolver_organismo_por_nombre(variable_info.get('Organismo_Productor', '').strip())
                                else variable_info.get('Organismo_Productor', '').strip()
                            ),
                            orden=idx
                        )
                    
                    variables_creadas += 1
                    
                except Exception as e:
                    errores.append(f'{codigo_indicador} - {variable_info.get("Codigo_Variable")}: {str(e)}')
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Error en variable {variable_info.get("Codigo_Variable")}: {str(e)}')
                    )
            
            if not dry_run:
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Creadas {len(variables)} variables')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'  [DRY-RUN] Se crearían {len(variables)} variables')
                )
        
        # Resumen final
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('\n📊 RESUMEN DE EJECUCIÓN'))
        self.stdout.write('='*70)
        self.stdout.write(
            self.style.SUCCESS(f'✓ Indicadores procesados: {len(indicadores_procesados)}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'✓ conjunto_datos creados: {conjunto_datos_creados}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'✓ Variables creadas: {variables_creadas}')
        )
        
        if indicadores_no_encontrados:
            self.stdout.write('\n' + '='*70)
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  Indicadores no encontrados: {len(indicadores_no_encontrados)}'
                )
            )
            self.stdout.write('='*70)
            for codigo in indicadores_no_encontrados[:15]:
                self.stdout.write(f'  - {codigo}')
            if len(indicadores_no_encontrados) > 15:
                self.stdout.write(f'  ... y {len(indicadores_no_encontrados) - 15} más')
        
        if errores:
            self.stdout.write('\n' + '='*70)
            self.stdout.write(
                self.style.ERROR(f'❌ Errores encontrados: {len(errores)}')
            )
            self.stdout.write('='*70)
            for error in errores[:10]:
                self.stdout.write(f'  - {error}')
            if len(errores) > 10:
                self.stdout.write(f'  ... y {len(errores) - 10} más')
        
        self.stdout.write('\n' + '='*70)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  Esto fue un DRY-RUN. Ejecute sin --dry-run para guardar los cambios.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ ¡Proceso completado exitosamente!')
            )
            self.stdout.write('\n📝 Próximos pasos:')
            self.stdout.write('   1. Los archivos CSV de conjunto_datos están vacíos (solo headers)')
            self.stdout.write('   2. Suba los datos reales desde el admin de Django')
            self.stdout.write('   3. Vaya a: /admin/indicadores/conjunto_datos/')
            self.stdout.write('   4. Edite cada conjunto_datos y suba el archivo CSV con datos')
        self.stdout.write('='*70 + '\n')
