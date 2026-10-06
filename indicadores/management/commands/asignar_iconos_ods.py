from django.core.management.base import BaseCommand
from indicadores.models import MenuSubtema, MenuDominio


class Command(BaseCommand):
    help = 'Asigna iconos Font Awesome a los subtemas de Objetivos de Desarrollo Sostenible'
    
    # Mapeo de ODS a iconos Font Awesome (17 Objetivos)
    ICONOS_ODS = {
        'Objetivo 1': 'fas fa-hand-holding-heart',  # Fin de la pobreza
        'Objetivo 2': 'fas fa-seedling',  # Hambre cero
        'Objetivo 3': 'fas fa-heartbeat',  # Salud y bienestar
        'Objetivo 4': 'fas fa-graduation-cap',  # Educación de calidad
        'Objetivo 5': 'fas fa-venus',  # Igualdad de género
        'Objetivo 6': 'fas fa-tint',  # Agua limpia y saneamiento
        'Objetivo 7': 'fas fa-bolt',  # Energía asequible y no contaminante
        'Objetivo 8': 'fas fa-briefcase',  # Trabajo decente y crecimiento económico
        'Objetivo 9': 'fas fa-industry',  # Industria, innovación e infraestructura
        'Objetivo 10': 'fas fa-balance-scale',  # Reducción de las desigualdades
        'Objetivo 11': 'fas fa-city',  # Ciudades y comunidades sostenibles
        'Objetivo 12': 'fas fa-recycle',  # Producción y consumo responsables
        'Objetivo 13': 'fas fa-cloud-sun-rain',  # Acción por el clima
        'Objetivo 14': 'fas fa-water',  # Vida submarina
        'Objetivo 15': 'fas fa-tree',  # Vida de ecosistemas terrestres
        'Objetivo 16': 'fas fa-gavel',  # Paz, justicia e instituciones sólidas
        'Objetivo 17': 'fas fa-handshake',  # Alianzas para lograr los objetivos
    }
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Ejecutar sin guardar cambios (solo mostrar lo que se haría)'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY-RUN: No se guardarán cambios\n')
            )
        
        # Obtener el dominio de ODS
        try:
            dominio = MenuDominio.objects.get(id=5)  # Objetivos de Desarrollo Sostenible
        except MenuDominio.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('No se encontró el dominio de Objetivos de Desarrollo Sostenible')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'Dominio: {dominio.nombre}\n')
        )
        
        # Obtener todos los subtemas del dominio ODS
        subtemas = MenuSubtema.objects.filter(tema__dominio=dominio).order_by('tema__nombre', 'nombre')
        
        # Estadísticas
        total_subtemas = subtemas.count()
        actualizados = 0
        sin_icono = 0
        
        # Agrupar por tema (ODS)
        subtemas_por_ods = {}
        for subtema in subtemas:
            tema_nombre = subtema.tema.nombre
            if tema_nombre not in subtemas_por_ods:
                subtemas_por_ods[tema_nombre] = []
            subtemas_por_ods[tema_nombre].append(subtema)
        
        # Procesar cada ODS
        for ods_nombre in sorted(subtemas_por_ods.keys()):
            icono = self.ICONOS_ODS.get(ods_nombre)
            
            if not icono:
                self.stdout.write(
                    self.style.WARNING(f'\n⚠️  {ods_nombre}: No tiene icono asignado')
                )
                sin_icono += len(subtemas_por_ods[ods_nombre])
                continue
            
            self.stdout.write(
                self.style.SUCCESS(f'\n✓ {ods_nombre}: {icono}')
            )
            
            # Actualizar todos los subtemas de este ODS
            for subtema in subtemas_por_ods[ods_nombre]:
                if not dry_run:
                    subtema.icono = icono
                    subtema.save(update_fields=['icono'])
                    actualizados += 1
                else:
                    actualizados += 1
                
                self.stdout.write(
                    f'  - {subtema.nombre[:70]}...' if len(subtema.nombre) > 70 else f'  - {subtema.nombre}'
                )
        
        # Resumen
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('\n📊 RESUMEN'))
        self.stdout.write('='*70)
        self.stdout.write(f'Total de subtemas: {total_subtemas}')
        self.stdout.write(
            self.style.SUCCESS(f'✓ Subtemas actualizados: {actualizados}')
        )
        
        if sin_icono > 0:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Subtemas sin icono: {sin_icono}')
            )
        
        self.stdout.write('\n' + '='*70)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️  Esto fue un DRY-RUN. Ejecute sin --dry-run para guardar los cambios.')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ ¡Iconos asignados exitosamente!')
            )
        
        self.stdout.write('='*70 + '\n')
        
        # Mostrar tabla de iconos asignados
        self.stdout.write('\n📋 TABLA DE ICONOS ASIGNADOS:\n')
        self.stdout.write('='*70)
        for ods_nombre in sorted(self.ICONOS_ODS.keys()):
            icono = self.ICONOS_ODS[ods_nombre]
            count = len(subtemas_por_ods.get(ods_nombre, []))
            self.stdout.write(f'{ods_nombre:20} | {icono:30} | {count:3} subtemas')
        self.stdout.write('='*70 + '\n')
