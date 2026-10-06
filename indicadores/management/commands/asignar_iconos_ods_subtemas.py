from django.core.management.base import BaseCommand
from indicadores.models import MenuSubtema, MenuDominio


class Command(BaseCommand):
    help = 'Asigna iconos Font Awesome individuales a cada subtema de Objetivos de Desarrollo Sostenible'
    
    # Mapeo de ID de subtema a icono Font Awesome (86 subtemas únicos)
    ICONOS_SUBTEMAS = {
        # Objetivo 1 - Fin de la pobreza
        137: 'fas fa-chart-line',  # Brecha de pobreza extrema urbano-rural
        104: 'fas fa-hand-holding-usd',  # Incidencia de la Pobreza Monetaria
        105: 'fas fa-exclamation-triangle',  # Incidencia de la Pobreza Monetaria Extrema
        138: 'fas fa-layer-group',  # Índice de Pobreza Multidimensional
        139: 'fas fa-poll',  # Medida de pobreza multidimensional Censal
        144: 'fas fa-child',  # Porcentaje de niñas y niños en primera infancia
        140: 'fas fa-globe-americas',  # Porcentaje de población umbral internacional pobreza extrema
        147: 'fas fa-utensils',  # Tasa de cobertura del Programa de Alimentación Escolar
        
        # Objetivo 3 - Salud y bienestar
        156: 'fas fa-syringe',  # Incidencia de la hepatitis B
        141: 'fas fa-mosquito',  # Incidencia de malaria
        87: 'fas fa-lungs',  # Incidencia de tuberculosis
        124: 'fas fa-hourglass-half',  # La esperanza de vida al nacer
        88: 'fas fa-bug',  # Letalidad por dengue
        89: 'fas fa-user-md',  # Número de médicos
        90: 'fas fa-shield-alt',  # Porcentaje de menores de 1 año con tercera dosis de pentavalente
        142: 'fas fa-baby',  # Porcentaje de mujeres 15-19 años con embarazo subsiguiente
        143: 'fas fa-female',  # Porcentaje de mujeres 15-19 años madres o embarazadas
        91: 'fas fa-hospital',  # Porcentaje de partos atendidos por personal calificado
        145: 'fas fa-wine-bottle',  # Porcentaje de personas con consumo de riesgo de alcohol
        146: 'fas fa-pills',  # Porcentaje con tratamiento hepatitis C
        92: 'fas fa-id-card',  # Porcentaje de población afiliada al sistema de salud
        164: 'fas fa-baby-carriage',  # Porcentaje de transmisión materno-infantil hepatitis B
        93: 'fas fa-notes-medical',  # Porcentaje niños con vacunación triple viral
        161: 'fas fa-heartbeat',  # Razón de mortalidad materna (42 días)
        103: 'fas fa-chart-area',  # Tasa de fecundidad específica en mujeres adolescentes
        94: 'fas fa-sad-tear',  # Tasa de mortalidad de niños menores de 5 años
        163: 'fas fa-baby',  # Tasa de mortalidad infantil
        122: 'fas fa-heart-broken',  # Tasa de mortalidad neonatal
        95: 'fas fa-apple-alt',  # Tasa de mortalidad por desnutrición en menores de 5 años
        101: 'fas fa-user-times',  # Tasa de mortalidad por lesiones auto infligidas
        96: 'fas fa-ribbon',  # Tasa de mortalidad por tumores malignos en menores de 18 años
        97: 'fas fa-viruses',  # Tasa de mortalidad por VIH/SIDA
        98: 'fas fa-lungs-virus',  # Tasa de mortalidad prematura enfermedades vías respiratorias
        99: 'fas fa-disease',  # Tasa de mortalidad prematura por cáncer
        100: 'fas fa-heartbeat',  # Tasa de mortalidad prematura por diabetes
        148: 'fas fa-procedures',  # Tasa de mortalidad prematura por enfermedades no transmisibles
        117: 'fas fa-car-crash',  # Tasa General de mortalidad por accidentes de tránsito
        123: 'fas fa-user-nurse',  # Tasa mortalidad materna
        
        # Objetivo 4 - Educación de calidad
        133: 'fas fa-map-marked-alt',  # Brecha entre cobertura neta urbano-rural en educación
        83: 'fas fa-university',  # Cobertura en educación superior
        134: 'fas fa-wifi',  # Porcentaje de matrícula oficial con conexión a internet
        109: 'fas fa-book-reader',  # Tasa de analfabetismo
        110: 'fas fa-school',  # Tasa de cobertura bruta en educación media
        111: 'fas fa-child',  # Tasa de cobertura bruta en transición
        162: 'fas fa-door-open',  # Tasa de deserción intra-anual
        
        # Objetivo 5 - Igualdad de género
        136: 'fas fa-money-bill-wave',  # Brecha de ingreso mensual entre hombres y mujeres
        129: 'fas fa-map',  # Hectáreas de pequeña y mediana propiedad rural
        149: 'fas fa-hand-paper',  # Porcentaje de mujeres con violencia física
        82: 'fas fa-female',  # Porcentaje de mujeres en cargos directivos
        131: 'fas fa-home',  # Predios con catastro multipropósito
        135: 'fas fa-briefcase',  # Tasa de Ocupacion Femenina
        
        # Objetivo 6 - Agua limpia y saneamiento
        158: 'fas fa-faucet',  # Acceso a agua potable adecuado
        125: 'fas fa-water',  # Porcentaje de aguas residuales urbanas tratadas
        160: 'fas fa-toilet',  # Porcentaje de población con acceso a saneamiento
        
        # Objetivo 7 - Energía asequible
        159: 'fas fa-lightbulb',  # Cobertura de energía eléctrica
        
        # Objetivo 8 - Trabajo decente
        112: 'fas fa-user-graduate',  # Porcentaje de jóvenes que no estudian y no tienen empleo
        113: 'fas fa-user-slash',  # Tasa de desempleo
        114: 'fas fa-file-contract',  # Tasa de formalidad laboral
        115: 'fas fa-child',  # Tasa de trabajo infantil
        
        # Objetivo 9 - Industria e infraestructura
        154: 'fas fa-car',  # Parque automotor por municipio
        153: 'fas fa-chart-line',  # Valor agregado por municipio
        
        # Objetivo 10 - Reducción de desigualdades
        106: 'fas fa-balance-scale-right',  # Coeficiente de Gini
        116: 'fas fa-arrow-up',  # Tasa de crecimiento de ingresos per cápita
        
        # Objetivo 11 - Ciudades sostenibles
        132: 'fas fa-map-marked',  # Cociente entre tasa de consumo de tierras
        155: 'fas fa-city',  # Grado de urbanización
        85: 'fas fa-house-damage',  # Hogares urbanos con déficit cualitativo de vivienda
        86: 'fas fa-home',  # Hogares urbanos con déficit cuantitativo de vivienda
        126: 'fas fa-smog',  # Porcentaje de estaciones que cumplen guías calidad del aire
        79: 'fas fa-recycle',  # Porcentaje de residuos sólidos efectivamente aprovechados
        152: 'fas fa-dumpster',  # Porcentaje de residuos sólidos urbanos dispuestos adecuadamente
        128: 'fas fa-biohazard',  # Residuos peligrosos aprovechados y tratados
        107: 'fas fa-exclamation-circle',  # Tasa de personas afectadas por eventos recurrentes
        80: 'fas fa-sync-alt',  # Tasa de reciclaje y nueva utilización
        130: 'fas fa-map-signs',  # Vocación de uso del suelo
        
        # Objetivo 12 - Producción y consumo responsables
        127: 'fas fa-leaf',  # Negocios verdes verificados
        
        # Objetivo 16 - Paz y justicia
        81: 'fas fa-chart-bar',  # Índice de desempeño institucional
        157: 'fas fa-car-side',  # Número de robos de vehículos motorizados
        118: 'fas fa-venus-mars',  # Tasa de feminicidio
        119: 'fas fa-skull-crossbones',  # Tasa de homicidios
        84: 'fas fa-user-injured',  # Tasa de víctimas directas de homicidio y desaparición forzada
        120: 'fas fa-user-secret',  # Tasa de victimización de hurto a personas
        121: 'fas fa-fist-raised',  # Tasa de violencia interpersonal
        150: 'fas fa-hands-helping',  # Víctimas con atención psicosocial
        151: 'fas fa-hand-holding-heart',  # Víctimas que superaron vulnerabilidad
        
        # Objetivo 17 - Alianzas
        108: 'fas fa-coins',  # Porcentaje de presupuesto municipal financiado con recursos propios
        102: 'fas fa-users',  # Total población
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
            dominio = MenuDominio.objects.get(id=5)
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
        
        # Agrupar por tema para mejor visualización
        subtemas_por_ods = {}
        for subtema in subtemas:
            tema_nombre = subtema.tema.nombre
            if tema_nombre not in subtemas_por_ods:
                subtemas_por_ods[tema_nombre] = []
            subtemas_por_ods[tema_nombre].append(subtema)
        
        # Procesar cada ODS
        for ods_nombre in sorted(subtemas_por_ods.keys()):
            self.stdout.write(
                self.style.SUCCESS(f'\n{"="*70}')
            )
            self.stdout.write(
                self.style.SUCCESS(f'{ods_nombre}')
            )
            self.stdout.write(
                self.style.SUCCESS(f'{"="*70}')
            )
            
            # Procesar cada subtema
            for subtema in subtemas_por_ods[ods_nombre]:
                icono = self.ICONOS_SUBTEMAS.get(subtema.id)
                
                if not icono:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️  ID {subtema.id:3} | SIN ICONO | {subtema.nombre[:60]}')
                    )
                    sin_icono += 1
                    continue
                
                if not dry_run:
                    subtema.icono = icono
                    subtema.save(update_fields=['icono'])
                
                actualizados += 1
                
                nombre_truncado = subtema.nombre[:55] + '...' if len(subtema.nombre) > 55 else subtema.nombre
                self.stdout.write(
                    self.style.SUCCESS(f'✓ ID {subtema.id:3} | {icono:25} | {nombre_truncado}')
                )
        
        # Resumen
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('\n📊 RESUMEN'))
        self.stdout.write('='*70)
        self.stdout.write(f'Total de subtemas en ODS: {total_subtemas}')
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
                self.style.SUCCESS('✅ ¡Iconos asignados exitosamente a cada subtema!')
            )
        
        self.stdout.write('='*70 + '\n')
