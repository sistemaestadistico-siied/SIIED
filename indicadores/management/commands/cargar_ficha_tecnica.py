from django.core.management.base import BaseCommand
from indicadores.models import Indicador, MenuSubtema, EquipoOrganismo
import csv
import os
from datetime import datetime


class Command(BaseCommand):
    help = 'Carga los datos de la ficha técnica desde el CSV a los indicadores existentes'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-path',
            type=str,
            default='docs/insumos/ficha_tecnica_indicadores.csv',
            help='Ruta al archivo CSV de ficha técnica'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Ejecutar sin guardar cambios (solo mostrar lo que se haría)'
        )
    
    def handle(self, *args, **options):
        csv_path = options['csv_path']
        dry_run = options['dry_run']
        
        # Verificar que el archivo existe
        if not os.path.exists(csv_path):
            self.stdout.write(
                self.style.ERROR(f'El archivo {csv_path} no existe')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'Cargando ficha técnica desde: {csv_path}')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY-RUN: No se guardarán cambios')
            )
        
        # Leer el CSV
        indicadores_actualizados = 0
        indicadores_no_encontrados = []
        subtemas_con_multiples_indicadores = []
        
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                codigo_indicador = row.get('Codigo_Indicador', '').strip()
                nombre_indicador = row.get('Nombre_Indicador', '').strip()
                
                if not codigo_indicador:
                    self.stdout.write(
                        self.style.WARNING(f'Fila sin código de indicador, saltando...')
                    )
                    continue
                
                # El Codigo_Indicador es el slug del subtema
                # Buscar el subtema por slug
                try:
                    subtema = MenuSubtema.objects.get(slug=codigo_indicador)
                except MenuSubtema.DoesNotExist:
                    indicadores_no_encontrados.append(f'{codigo_indicador} (subtema no existe)')
                    self.stdout.write(
                        self.style.WARNING(
                            f'Subtema no encontrado con slug: {codigo_indicador}'
                        )
                    )
                    continue
                
                # Obtener los indicadores activos de ese subtema
                indicadores_subtema = Indicador.objects.filter(subtema=subtema, activo=True)
                
                if indicadores_subtema.count() == 0:
                    indicadores_no_encontrados.append(f'{codigo_indicador} (sin indicadores activos)')
                    self.stdout.write(
                        self.style.WARNING(
                            f'No hay indicadores activos en subtema: {subtema.nombre} ({codigo_indicador})'
                        )
                    )
                    continue
                elif indicadores_subtema.count() > 1:
                    subtemas_con_multiples_indicadores.append(
                        f'{codigo_indicador} ({indicadores_subtema.count()} indicadores)'
                    )
                    self.stdout.write(
                        self.style.WARNING(
                            f'Subtema {subtema.nombre} tiene {indicadores_subtema.count()} indicadores. Saltando por seguridad.'
                        )
                    )
                    continue
                
                # Tomar el único indicador del subtema
                indicador = indicadores_subtema.first()
                
                # Actualizar campos del indicador
                self.stdout.write(f'\nActualizando: {indicador.nombre}')
                
                # Mapeo de campos CSV a modelo
                indicador.codigo_indicador = codigo_indicador
                indicador.sigla = row.get('Sigla', '').strip()
                indicador.grupo_indicador = row.get('Grupo_Indicador', '').strip()
                
                # Campos descriptivos
                # NOTA: El campo 'descripcion' fue eliminado del modelo
                # Si 'Nombre_Indicador' del CSV tiene contenido descriptivo adicional,
                # se puede agregar a definiciones_conceptos
                indicador.descripcion_indicador = row.get('Descripcion_Indicador', row.get('Definiciones_Conceptos', '')).strip()
                indicador.objetivo = row.get('Objetivo', '').strip()
                                
                # Metodología
                indicador.metodo_medicion = row.get('Metodo_Medicion', '').strip()
                indicador.formula_ficha = row.get('Formula', '').strip()
                indicador.variables = row.get('Variables', '').strip()
                
                # Unidades y referencias
                indicador.unidad_medida = row.get('Unidad_Medida', '').strip()
                                                
                # Desagregaciones
                indicador.alcance_tematico = row.get('Alcance_Tematico', row.get('Desagregacion_Tematica', '')).strip()
                indicador.cobertura_geografica = row.get('Cobertura_Geografica', row.get('Desagregacion_Geografica', '')).strip()
                
                # Información administrativa
                indicador.frecuencia_difusion = row.get('Frecuencia_Difusion', row.get('Periodicidad', '')).strip()
                indicador.fuente_datos = row.get('Fuente_Datos', '').strip()
                indicador.entidad_responsable = row.get('Entidad_Responsable', row.get('Responsable', '')).strip()
                indicador.comentarios_adicionales = row.get('Comentarios_Adicionales', row.get('Observaciones', '')).strip()
                # SDMX: referencias y responsabilidad institucional
                indicador.referencias = row.get('Referencias', '').strip()
                indicador.nombre_responsable_validacion = row.get('Nombre_Responsable_Validacion', '').strip()
                indicador.cargo_responsable_validacion = row.get('Cargo_Responsable_Validacion', '').strip()
                indicador.correo_responsable_validacion = row.get('Correo_Responsable_Validacion', '').strip()
                indicador.celular_responsable_validacion = row.get('Celular_Responsable_Validacion', '').strip()
                equipo_txt = row.get('Equipo_Responsable', '').strip()
                if equipo_txt:
                    eq_qs = EquipoOrganismo.objects.filter(nombre__iexact=equipo_txt, activo=True)
                    if indicador.suborganismo_id:
                        eq_qs = eq_qs.filter(suborganismo_id=indicador.suborganismo_id)
                    eq = eq_qs.first()
                    if eq:
                        indicador.equipo_responsable = eq
                
                # Fechas
                
                
                fecha_actualizacion_str = (row.get('Fecha_Publicacion_Metadatos', '') or row.get('Fecha_Actualizacion', '')).strip()
                if fecha_actualizacion_str:
                    try:
                        indicador.fecha_publicacion_metadatos = datetime.strptime(
                            fecha_actualizacion_str, '%Y-%m-%d'
                        ).date()
                    except ValueError:
                        self.stdout.write(
                            self.style.WARNING(
                                f'  Fecha de publicación inválida: {fecha_actualizacion_str}'
                            )
                        )
                
                # Guardar si no es dry-run
                if not dry_run:
                    indicador.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Actualizado: {indicador.codigo_indicador}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'  [DRY-RUN] Se actualizaría: {indicador.codigo_indicador}')
                    )
                
                indicadores_actualizados += 1
        
        # Resumen
        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS(f'\nIndicadores actualizados: {indicadores_actualizados}')
        )
        
        if subtemas_con_multiples_indicadores:
            self.stdout.write(
                self.style.WARNING(
                    f'\nSubtemas con múltiples indicadores (saltados por seguridad): {len(subtemas_con_multiples_indicadores)}'
                )
            )
            for info in subtemas_con_multiples_indicadores[:10]:
                self.stdout.write(f'  - {info}')
            if len(subtemas_con_multiples_indicadores) > 10:
                self.stdout.write(f'  ... y {len(subtemas_con_multiples_indicadores) - 10} más')
        
        if indicadores_no_encontrados:
            self.stdout.write(
                self.style.WARNING(
                    f'\nSubtemas/Indicadores no encontrados: {len(indicadores_no_encontrados)}'
                )
            )
            for codigo in indicadores_no_encontrados[:10]:  # Mostrar solo los primeros 10
                self.stdout.write(f'  - {codigo}')
            if len(indicadores_no_encontrados) > 10:
                self.stdout.write(f'  ... y {len(indicadores_no_encontrados) - 10} más')
        
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
