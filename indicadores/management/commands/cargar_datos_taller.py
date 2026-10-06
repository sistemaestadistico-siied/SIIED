"""
Management command para precargar los datos iniciales del sistema de talleres:
- 6 familias de roles (A-F)
- 28 roles del ecosistema
- 11 preguntas del quiz con sus opciones

Uso: python manage.py cargar_datos_taller
"""
from django.core.management.base import BaseCommand
from indicadores.models import FamiliaRol, RolEcosistema, PreguntaQuiz, OpcionQuiz


class Command(BaseCommand):
    help = 'Carga los datos iniciales para el sistema de talleres del ecosistema de datos'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Iniciando carga de datos del sistema de talleres...'))
        
        # Cargar familias de roles
        self.cargar_familias()
        
        # Cargar roles del ecosistema
        self.cargar_roles()
        
        # Cargar preguntas del quiz
        self.cargar_quiz()
        
        self.stdout.write(self.style.SUCCESS('✅ Datos cargados exitosamente'))

    def cargar_familias(self):
        """Carga las 6 familias de roles."""
        self.stdout.write('Cargando familias de roles...')
        
        familias = [
            {
                'codigo': 'A',
                'nombre': 'Producción y calidad del dato',
                'descripcion': 'Captura, garantiza y responde por la calidad de los datos',
                'color_hex': '#F59E0B',
                'icono': 'fa-solid fa-database',
                'orden': 1
            },
            {
                'codigo': 'B',
                'nombre': 'Gestión y gobierno del dato',
                'descripcion': 'Define reglas, alinea estrategias y cuida la privacidad',
                'color_hex': '#F97316',
                'icono': 'fa-solid fa-shield-halved',
                'orden': 2
            },
            {
                'codigo': 'C',
                'nombre': 'Infraestructura y tecnología',
                'descripcion': 'Asegura plataformas, servidores y bases de datos',
                'color_hex': '#3B82F6',
                'icono': 'fa-solid fa-server',
                'orden': 3
            },
            {
                'codigo': 'D',
                'nombre': 'Análisis, narrativa y visibilidad',
                'descripcion': 'Transforma datos en conocimiento y lo comunica',
                'color_hex': '#8B5CF6',
                'icono': 'fa-solid fa-chart-line',
                'orden': 4
            },
            {
                'codigo': 'E',
                'nombre': 'Intermediación, servicios y apertura',
                'descripcion': 'Facilita el acceso, promueve el uso y conecta actores',
                'color_hex': '#10B981',
                'icono': 'fa-solid fa-handshake',
                'orden': 5
            },
            {
                'codigo': 'F',
                'nombre': 'Estrategia y diseño',
                'descripcion': 'Lidera la visión, diseña procesos y toma decisiones',
                'color_hex': '#EF4444',
                'icono': 'fa-solid fa-compass',
                'orden': 6
            }
        ]
        
        for fam_data in familias:
            familia, created = FamiliaRol.objects.update_or_create(
                codigo=fam_data['codigo'],
                defaults=fam_data
            )
            if created:
                self.stdout.write(f'  ✓ Creada familia {familia.codigo}: {familia.nombre}')
            else:
                self.stdout.write(f'  ↻ Actualizada familia {familia.codigo}: {familia.nombre}')

    def cargar_roles(self):
        """Carga los 28 roles del ecosistema."""
        self.stdout.write('Cargando roles del ecosistema...')
        
        roles = [
            # Familia A: Producción y calidad del dato
            {'familia': 'A', 'numero': 1, 'nombre': 'Recolector/a de datos', 'descripcion': 'Soy quien captura y registra datos en campo o en sistemas'},
            {'familia': 'A', 'numero': 2, 'nombre': 'Productor/a de datos', 'descripcion': 'Soy quien genera datos desde procesos misionales o administrativos'},
            {'familia': 'A', 'numero': 3, 'nombre': 'Validador/a de calidad', 'descripcion': 'Soy quien verifica, limpia y asegura la calidad de los datos'},
            {'familia': 'A', 'numero': 4, 'nombre': 'Curador/a de datos', 'descripcion': 'Soy quien organiza, documenta y preserva los datos en el tiempo'},
            
            # Familia B: Gestión y gobierno del dato
            {'familia': 'B', 'numero': 5, 'nombre': 'Administrador/a de datos', 'descripcion': 'Soy quien define políticas, estándares y reglas de uso de datos'},
            {'familia': 'B', 'numero': 6, 'nombre': 'Oficial de privacidad', 'descripcion': 'Soy quien protege datos personales y garantiza habeas data'},
            {'familia': 'B', 'numero': 7, 'nombre': 'Gestor/a de metadatos', 'descripcion': 'Soy quien documenta el significado, origen y contexto de los datos'},
            {'familia': 'B', 'numero': 8, 'nombre': 'Auditor/a de datos', 'descripcion': 'Soy quien verifica el cumplimiento de normas y procedimientos'},
            
            # Familia C: Infraestructura y tecnología
            {'familia': 'C', 'numero': 9, 'nombre': 'Administrador/a de sistemas', 'descripcion': 'Soy quien mantiene servidores, redes y plataformas tecnológicas'},
            {'familia': 'C', 'numero': 10, 'nombre': 'Administrador/a de bases de datos', 'descripcion': 'Soy quien gestiona, optimiza y respalda las bases de datos'},
            {'familia': 'C', 'numero': 11, 'nombre': 'Desarrollador/a de software', 'descripcion': 'Soy quien crea aplicaciones y sistemas para gestionar datos'},
            {'familia': 'C', 'numero': 12, 'nombre': 'Arquitecto/a de datos', 'descripcion': 'Soy quien diseña la estructura y flujo de datos en la organización'},
            
            # Familia D: Análisis, narrativa y visibilidad
            {'familia': 'D', 'numero': 13, 'nombre': 'Analista articulador/a', 'descripcion': 'Soy quien cruza datos de diferentes fuentes para generar conocimiento'},
            {'familia': 'D', 'numero': 14, 'nombre': 'Diseñador/a de datos', 'descripcion': 'Soy quien crea visualizaciones, dashboards y reportes'},
            {'familia': 'D', 'numero': 15, 'nombre': 'Científico/a de datos', 'descripcion': 'Soy quien aplica modelos estadísticos y machine learning'},
            {'familia': 'D', 'numero': 16, 'nombre': 'Comunicador/a de datos', 'descripcion': 'Soy quien traduce datos técnicos en narrativas comprensibles'},
            {'familia': 'D', 'numero': 17, 'nombre': 'Consumidor/a estratégico', 'descripcion': 'Soy quien usa datos para tomar decisiones de alto nivel'},
            
            # Familia E: Intermediación, servicios y apertura
            {'familia': 'E', 'numero': 18, 'nombre': 'Intermediario/a de datos', 'descripcion': 'Soy quien conecta productores y consumidores de datos'},
            {'familia': 'E', 'numero': 19, 'nombre': 'Promotor/a de apertura', 'descripcion': 'Soy quien impulsa la publicación y reutilización de datos abiertos'},
            {'familia': 'E', 'numero': 20, 'nombre': 'Gestor/a de servicios', 'descripcion': 'Soy quien administra APIs, catálogos y portales de datos'},
            {'familia': 'E', 'numero': 21, 'nombre': 'Enlace territorial', 'descripcion': 'Soy quien articula datos entre el nivel central y territorial'},
            {'familia': 'E', 'numero': 22, 'nombre': 'Capacitador/a en datos', 'descripcion': 'Soy quien forma y acompaña a otros en el uso de datos'},
            
            # Familia F: Estrategia y diseño
            {'familia': 'F', 'numero': 23, 'nombre': 'Líder de gestión de información', 'descripcion': 'Soy quien dirige la estrategia de datos del organismo'},
            {'familia': 'F', 'numero': 24, 'nombre': 'Diseñador/a de procesos', 'descripcion': 'Soy quien define flujos de trabajo y procedimientos de datos'},
            {'familia': 'F', 'numero': 25, 'nombre': 'Planificador/a estratégico', 'descripcion': 'Soy quien alinea los datos con los objetivos institucionales'},
            {'familia': 'F', 'numero': 26, 'nombre': 'Tomador/a de decisiones', 'descripcion': 'Soy quien usa evidencia de datos para definir políticas públicas'},
            {'familia': 'F', 'numero': 27, 'nombre': 'Documentador/a de procesos', 'descripcion': 'Soy quien registra y estandariza procedimientos de datos'},
            {'familia': 'F', 'numero': 28, 'nombre': 'Evaluador/a de impacto', 'descripcion': 'Soy quien mide el valor y efecto de los datos en la gestión'},
        ]
        
        for rol_data in roles:
            familia = FamiliaRol.objects.get(codigo=rol_data['familia'])
            rol, created = RolEcosistema.objects.update_or_create(
                familia=familia,
                numero=rol_data['numero'],
                defaults={
                    'nombre': rol_data['nombre'],
                    'descripcion_narrativa': rol_data['descripcion']
                }
            )
            if created:
                self.stdout.write(f'  ✓ Creado rol {rol.numero}: {rol.nombre}')

    def cargar_quiz(self):
        """Carga las 11 preguntas del quiz con sus opciones."""
        self.stdout.write('Cargando preguntas del quiz...')
        
        preguntas = [
            {
                'numero': 1,
                'texto': '¿Qué tan importante son los datos en tu trabajo diario?',
                'tipo': 'opcion_unica',
                'orden': 1,
                'opciones': [
                    {'letra': 'A', 'texto': 'Son fundamentales, no puedo trabajar sin ellos', 'orden': 1},
                    {'letra': 'B', 'texto': 'Son importantes pero no indispensables', 'orden': 2},
                    {'letra': 'C', 'texto': 'Los uso ocasionalmente', 'orden': 3},
                    {'letra': 'D', 'texto': 'Casi nunca trabajo con datos', 'orden': 4},
                ]
            },
            {
                'numero': 2,
                'texto': '¿Con qué frecuencia produces o generas datos nuevos?',
                'tipo': 'opcion_unica',
                'orden': 2,
                'opciones': [
                    {'letra': 'A', 'texto': 'Diariamente', 'orden': 1},
                    {'letra': 'B', 'texto': 'Semanalmente', 'orden': 2},
                    {'letra': 'C', 'texto': 'Mensualmente', 'orden': 3},
                    {'letra': 'D', 'texto': 'Rara vez o nunca', 'orden': 4},
                ]
            },
            {
                'numero': 3,
                'texto': 'En tu día a día, los datos te sirven más para:',
                'tipo': 'opcion_unica',
                'orden': 3,
                'opciones': [
                    {'letra': 'A', 'texto': 'Cumplir con reportes y obligaciones formales', 'orden': 1},
                    {'letra': 'B', 'texto': 'Hacer preguntas nuevas y explorar problemas de fondo', 'orden': 2},
                    {'letra': 'C', 'texto': 'Ambas cosas por igual', 'orden': 3},
                ]
            },
            {
                'numero': 4,
                'texto': '¿Qué tan fácil es para ti acceder a los datos que necesitas?',
                'tipo': 'opcion_unica',
                'orden': 4,
                'opciones': [
                    {'letra': 'A', 'texto': 'Muy fácil, los tengo disponibles', 'orden': 1},
                    {'letra': 'B', 'texto': 'Requiere algo de esfuerzo pero es posible', 'orden': 2},
                    {'letra': 'C', 'texto': 'Es difícil, hay muchas barreras', 'orden': 3},
                    {'letra': 'D', 'texto': 'Casi imposible', 'orden': 4},
                ]
            },
            {
                'numero': 5,
                'texto': '¿Compartes datos con otras áreas o personas?',
                'tipo': 'opcion_unica',
                'orden': 5,
                'opciones': [
                    {'letra': 'A', 'texto': 'Sí, frecuentemente', 'orden': 1},
                    {'letra': 'B', 'texto': 'Sí, ocasionalmente', 'orden': 2},
                    {'letra': 'C', 'texto': 'Rara vez', 'orden': 3},
                    {'letra': 'D', 'texto': 'Nunca', 'orden': 4},
                ]
            },
            {
                'numero': 6,
                'texto': '¿Recibes datos de otras áreas o personas?',
                'tipo': 'opcion_unica',
                'orden': 6,
                'opciones': [
                    {'letra': 'A', 'texto': 'Sí, frecuentemente', 'orden': 1},
                    {'letra': 'B', 'texto': 'Sí, ocasionalmente', 'orden': 2},
                    {'letra': 'C', 'texto': 'Rara vez', 'orden': 3},
                    {'letra': 'D', 'texto': 'Nunca', 'orden': 4},
                ]
            },
            {
                'numero': 7,
                'texto': '¿Crees que existe un "ecosistema de datos" en tu organismo?',
                'tipo': 'opcion_unica',
                'orden': 7,
                'opciones': [
                    {'letra': 'A', 'texto': 'Sí, claramente identificado', 'orden': 1},
                    {'letra': 'B', 'texto': 'Sí, pero es informal y poco visible', 'orden': 2},
                    {'letra': 'C', 'texto': 'No estoy seguro/a', 'orden': 3},
                    {'letra': 'D', 'texto': 'No, cada quien trabaja aislado', 'orden': 4},
                ]
            },
            {
                'numero': 8,
                'texto': '¿Conoces quién más en tu organismo trabaja con datos similares a los tuyos?',
                'tipo': 'opcion_unica',
                'orden': 8,
                'opciones': [
                    {'letra': 'A', 'texto': 'Sí, conozco a varias personas', 'orden': 1},
                    {'letra': 'B', 'texto': 'Conozco a algunas', 'orden': 2},
                    {'letra': 'C', 'texto': 'Muy pocas', 'orden': 3},
                    {'letra': 'D', 'texto': 'No conozco a nadie', 'orden': 4},
                ]
            },
            {
                'numero': 9,
                'texto': '¿Qué tan documentados están los procesos de datos en tu área?',
                'tipo': 'opcion_unica',
                'orden': 9,
                'opciones': [
                    {'letra': 'A', 'texto': 'Muy bien documentados', 'orden': 1},
                    {'letra': 'B', 'texto': 'Parcialmente documentados', 'orden': 2},
                    {'letra': 'C', 'texto': 'Poco documentados', 'orden': 3},
                    {'letra': 'D', 'texto': 'Nada documentados', 'orden': 4},
                ]
            },
            {
                'numero': 10,
                'texto': 'El mayor reto con los datos en tu organismo es:',
                'tipo': 'opcion_unica',
                'orden': 10,
                'opciones': [
                    {'letra': 'A', 'texto': 'Acceso (conseguir los datos)', 'orden': 1},
                    {'letra': 'B', 'texto': 'Calidad (confiar en los datos)', 'orden': 2},
                    {'letra': 'C', 'texto': 'Uso (saber qué hacer con ellos)', 'orden': 3},
                    {'letra': 'D', 'texto': 'Cultura (que la gente valore los datos)', 'orden': 4},
                ]
            },
            {
                'numero': 11,
                'texto': '¿Te gustaría conocer mejor el ecosistema de datos de tu organismo?',
                'tipo': 'opcion_unica',
                'orden': 11,
                'opciones': [
                    {'letra': 'A', 'texto': 'Sí, mucho', 'orden': 1},
                    {'letra': 'B', 'texto': 'Sí, algo', 'orden': 2},
                    {'letra': 'C', 'texto': 'No mucho', 'orden': 3},
                    {'letra': 'D', 'texto': 'No me interesa', 'orden': 4},
                ]
            },
        ]
        
        for preg_data in preguntas:
            opciones_data = preg_data.pop('opciones')
            
            pregunta, created = PreguntaQuiz.objects.update_or_create(
                numero=preg_data['numero'],
                defaults=preg_data
            )
            
            if created:
                self.stdout.write(f'  ✓ Creada pregunta {pregunta.numero}')
            
            # Crear opciones
            for opc_data in opciones_data:
                OpcionQuiz.objects.update_or_create(
                    pregunta=pregunta,
                    letra=opc_data['letra'],
                    defaults={
                        'texto': opc_data['texto'],
                        'orden': opc_data['orden']
                    }
                )
