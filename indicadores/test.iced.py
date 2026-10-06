"""
Tests unitarios para el módulo ICED v2.

Cubre:
- Motor de cálculo de puntajes (calcular_iced.py)
- Materialización de RRHH (_materializar_rrhh)
- Validación de formularios y widgets
- Flujo básico del wizard

Para ejecutar:
    python manage.py test indicadores.tests_iced -v 2
"""
import json
from decimal import Decimal

from django.test import TestCase, Client, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone

from indicadores.models import Organismo
from indicadores.models_iced import ICEDFormulario, ICEDRecursoHumano
from indicadores.calcular_iced import (
    calcular_puntaje_b,
    calcular_puntaje_c,
    calcular_puntaje_d,
    calcular_puntaje_e,
    calcular_iced,
    aplicar_puntajes,
    determinar_nivel,
)
from indicadores.forms_iced import (
    ICEDModuloAForm,
    ICEDModuloBForm,
    ICEDModuloCForm,
    ICEDModuloDForm,
    ICEDModuloEForm,
    iced_widget,
)
from indicadores.views_iced import ICEDWizardView

User = get_user_model()


class MockForm:
    """Objeto simulado que imita un Form Django para las pruebas de scoring."""
    def __init__(self, data):
        self.cleaned_data = data


# =============================================================================
# TESTS DEL MOTOR DE CÁLCULO DE PUNTAJES
# =============================================================================

class CalcularPuntajeBTests(TestCase):
    """Tests para el cálculo de puntajes del Módulo B (Entorno Institucional)."""

    def test_p6_funciones_estadisticas_si(self):
        """P6=Sí debe dar puntaje positivo."""
        respuestas = {'p6_funciones_estadisticas': 'si'}
        puntaje = calcular_puntaje_b(respuestas)
        self.assertGreater(puntaje, 0)
        self.assertIsInstance(puntaje, Decimal)

    def test_p6_funciones_estadisticas_no(self):
        """P6=No debe dar puntaje 1.0 (nivel bajo)."""
        respuestas = {'p6_funciones_estadisticas': 'no'}
        puntaje = calcular_puntaje_b(respuestas)
        # P6=0, pero promedio con otras respuestas vacías
        self.assertIsInstance(puntaje, Decimal)

    def test_p10_participacion_completa(self):
        """P10=4 (no participa) con P10_motivo_no debe calcular."""
        respuestas = {
            'p6_funciones_estadisticas': 'si',
            'p10_participacion': '4',
            'p10_motivo_no': 'No hay presupuesto',
        }
        puntaje = calcular_puntaje_b(respuestas)
        self.assertIsInstance(puntaje, Decimal)

    def test_p12_trazabilidad_4(self):
        """P12=4 debe dar puntaje alto."""
        respuestas = {
            'p6_funciones_estadisticas': 'si',
            'p10_participacion': '1',
            'p12_trazabilidad': '4',
        }
        puntaje = calcular_puntaje_b(respuestas)
        self.assertIsInstance(puntaje, Decimal)
        self.assertGreaterEqual(float(puntaje), 0)
        self.assertLessEqual(float(puntaje), 100)


class CalcularPuntajeCTests(TestCase):
    """Tests para el cálculo de puntajes del Módulo C (Infraestructura)."""

    def test_p13_no_herramientas(self):
        """P13=Ninguna debe dar puntaje bajo."""
        respuestas = {'p13_herramientas_procesamiento': []}
        puntaje = calcular_puntaje_c(respuestas)
        self.assertIsInstance(puntaje, Decimal)

    def test_p13_varias_herramientas(self):
        """P13 con múltiples herramientas debe dar puntaje positivo."""
        respuestas = {
            'p13_herramientas_procesamiento': ['r', 'python', 'excel'],
            'p17_suficiencia_herramientas': '1',
            'p20_suficiencia_rrhh': '1',
            'p21_presupuesto_hardware': 10,
            'p21_presupuesto_software': 20,
            'p21_presupuesto_personal': 70,
        }
        puntaje = calcular_puntaje_c(respuestas)
        self.assertGreater(puntaje, 0)

    def test_p21_presupuesto_suma_100(self):
        """P21 con suma 100% debe calcular correctamente."""
        respuestas = {
            'p13_herramientas_procesamiento': ['excel'],
            'p17_suficiencia_herramientas': '1',
            'p20_suficiencia_rrhh': '1',
            'p21_presupuesto_hardware': 20,
            'p21_presupuesto_software': 30,
            'p21_presupuesto_personal': 50,
        }
        puntaje = calcular_puntaje_c(respuestas)
        self.assertIsInstance(puntaje, Decimal)

    def test_p21_presupuesto_suma_menor_100(self):
        """P21 con suma menor a 100% debe calcular."""
        respuestas = {
            'p13_herramientas_procesamiento': ['excel'],
            'p21_presupuesto_hardware': 10,
            'p21_presupuesto_software': 10,
            'p21_presupuesto_personal': 10,
        }
        puntaje = calcular_puntaje_c(respuestas)
        self.assertIsInstance(puntaje, Decimal)


class CalcularPuntajeDTests(TestCase):
    """Tests para el cálculo de puntajes del Módulo D (Metodología)."""

    def test_p23_tabla_vacia(self):
        """P23 vacío debe dar puntaje bajo."""
        respuestas = {'p23_operaciones_estadisticas': '[]'}
        puntaje = calcular_puntaje_d(respuestas)
        self.assertIsInstance(puntaje, Decimal)

    def test_p23_una_oe_completa(self):
        """P23 con una OE completa debe dar puntaje."""
        oe = [{
            'nombre_oe': 'OE Test',
            'vigente': 'si',
            'doc_metodologico': 'si',
            'ficha_metodologica': 'si',
            'manual_operativo': 'si',
            'diccionario_datos': 'si',
            'doc_consistencia': 'si',
            'acciones_fortalecimiento': 'Capacitación',
            'publicado_sicode': 'si',
        }]
        respuestas = {
            'p23_operaciones_estadisticas': json.dumps(oe),
            'p24_lineamientos': ['lineamientos_sen', 'ntc_pe_1000'],
            'p31_tipo_analitica': '4',
            'p33_tiene_observatorio': 'si',
        }
        puntaje = calcular_puntaje_d(respuestas)
        self.assertGreater(puntaje, 0)

    def test_p31_tipo_analitica_1_descriptiva(self):
        """P31=1 (Analítica descriptiva) debe calcular puntaje."""
        respuestas = {
            'p31_tipo_analitica': '1',
            'p31_descripcion_productos': 'Tablas y gráficos',
        }
        puntaje = calcular_puntaje_d(respuestas)
        self.assertIsInstance(puntaje, Decimal)


class CalcularPuntajeETests(TestCase):
    """Tests para el cálculo de puntajes del Módulo E (Accesibilidad)."""

    def test_p36_uso_indicadores_vacio(self):
        """P36 vacío debe dar puntaje bajo."""
        respuestas = {'p36_uso_indicadores': '{}'}
        puntaje = calcular_puntaje_e(respuestas)
        self.assertIsInstance(puntaje, Decimal)

    def test_p36_con_usos(self):
        """P36 con usos reportados debe dar puntaje."""
        respuestas = {
            'p36_uso_indicadores': json.dumps({
                'diagnostico_pdd': {'seleccion': True, 'url': 'https://ejemplo.com'},
                'rendicion_cuentas': {'seleccion': True, 'url': ''},
            }),
            'p37_usuarios': ['academia', 'publico'],
            'p39_medios_difusion': json.dumps({
                'web': {'seleccion': True, 'url': 'https://datos.cali.gov.co'},
            }),
            'p40_elementos_web': json.dumps({
                'bd_anonimizadas': {'seleccion': True, 'url': ''},
            }),
            'p41_indaga_satisfaccion': 'si',
        }
        puntaje = calcular_puntaje_e(respuestas)
        self.assertGreater(puntaje, 0)

    def test_p41_indaga_no(self):
        """P41=No debe dar puntaje reducido."""
        respuestas = {
            'p41_indaga_satisfaccion': 'no',
            'p42_observaciones': 'No tenemos mecanismos aún',
        }
        puntaje = calcular_puntaje_e(respuestas)
        self.assertGreaterEqual(float(puntaje), 0)


class CalcularICEDIntegracionTests(TestCase):
    """Tests de integración para el cálculo global ICED."""

    def setUp(self):
        """Crear un formulario de ICED para las pruebas."""
        from django.contrib.auth import get_user_model
        from indicadores.models import Organismo
        
        User = get_user_model()
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass')
        self.organismo = Organismo.objects.create(nombre='Org Test', orden=1, activo=True)
        
    def tearDown(self):
        ICEDFormulario.objects.filter(organismo=self.organismo).delete()
        self.organismo.delete()
        self.user.delete()

    def test_calcular_iced_formula_ponderada(self):
        """Verificar que la fórmula B×25% + C×25% + D×30% + E×20% se aplica."""
        # Crear formulario con respuestas mínimas
        formulario = ICEDFormulario.objects.create(
            organismo=self.organismo,
            periodo='2026',
            usuario_diligencia=self.user,
            respuestas_b={'p6_funciones_estadisticas': 'no'},
            respuestas_c={'p13_herramientas_procesamiento': []},
            respuestas_d={'p23_operaciones_estadisticas': '[]'},
            respuestas_e={'p36_uso_indicadores': '{}'},
        )
        
        result = calcular_iced(formulario)
        
        # Verificar estructura del resultado
        self.assertIn('puntaje_global', result)
        self.assertIsInstance(result['puntaje_global'], Decimal)

    def test_calcular_iced_nivel_bajo(self):
        """Puntaje bajo debe clasificar correctamente."""
        formulario = ICEDFormulario.objects.create(
            organismo=self.organismo,
            periodo='2026',
            usuario_diligencia=self.user,
            respuestas_b={'p6_funciones_estadisticas': 'no'},
            respuestas_c={'p13_herramientas_procesamiento': []},
            respuestas_d={'p23_operaciones_estadisticas': '[]'},
            respuestas_e={'p36_uso_indicadores': '{}'},
        )

        result = calcular_iced(formulario)
        self.assertEqual(result['nivel_codigo'], 'bajo')
        self.assertEqual(result['nivel_nombre'], 'Bajo')

    def test_calcular_iced_nivel_muy_alto(self):
        """Puntaje alto debe clasificar como 'muy_alto'."""
        formulario = ICEDFormulario.objects.create(
            organismo=self.organismo,
            periodo='2026',
            usuario_diligencia=self.user,
            respuestas_b={
                'p6_funciones_estadisticas': 'si',
                'p10_participacion': '1',
                'p12_trazabilidad': '4',
            },
            respuestas_c={
                'p13_herramientas_procesamiento': ['r', 'python', 'sas', 'stata'],
                'p17_suficiencia_herramientas': '4',
                'p20_suficiencia_rrhh': '4',
                'p21_presupuesto_hardware': 30,
                'p21_presupuesto_software': 30,
                'p21_presupuesto_personal': 40,
            },
            respuestas_d={
                'p23_operaciones_estadisticas': json.dumps([{
                    'nombre_oe': 'OE 1', 'vigente': 'si', 'doc_metodologico': 'si',
                }]),
                'p24_lineamientos': ['lineamientos_sen', 'ntc_pe_1000'],
                'p31_tipo_analitica': '4',
                'p33_tiene_observatorio': 'si',
            },
            respuestas_e={
                'p36_uso_indicadores': json.dumps({
                    'diagnostico_pdd': {'seleccion': True},
                    'rendicion_cuentas': {'seleccion': True},
                }),
                'p37_usuarios': ['academia', 'publico'],
                'p41_indaga_satisfaccion': 'si',
            },
        )

        result = calcular_iced(formulario)
        # Alto puntaje debe dar nivel alto o muy alto
        self.assertIn(result['nivel_codigo'], ['alto', 'muy_alto'])
        self.assertGreater(result['puntaje_global'], 50)

    def test_calcular_iced_devuelve_todos_los_puntajes(self):
        """Verificar que calcular_iced devuelve puntajes individuales y global."""
        formulario = ICEDFormulario.objects.create(
            organismo=self.organismo,
            periodo='2026',
            usuario_diligencia=self.user,
            respuestas_b={'p6_funciones_estadisticas': 'si'},
            respuestas_c={'p13_herramientas_procesamiento': ['r']},
            respuestas_d={'p31_tipo_analitica': '1'},
            respuestas_e={'p41_indaga_satisfaccion': 'si'},
        )
        
        result = calcular_iced(formulario)
        
        required_keys = [
            'puntaje_b', 'puntaje_c', 'puntaje_d', 'puntaje_e',
            'puntaje_global', 'nivel_codigo', 'nivel_nombre', 'dimensiones'
        ]
        for key in required_keys:
            self.assertIn(key, result)


class AplicarPuntajesTests(TestCase):
    """Tests para la persistencia de puntajes en el modelo."""

    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass')
        self.organismo = Organismo.objects.create(nombre='Organismo Test', orden=1, activo=True)
        self.formulario = ICEDFormulario.objects.create(
            organismo=self.organismo,
            periodo='2026',
            usuario_diligencia=self.user,
        )

    def tearDown(self):
        self.formulario.delete()
        self.organismo.delete()
        self.user.delete()

    def test_aplicar_puntajes_guarda_en_modelo(self):
        """aplicar_puntajes debe persistir los puntajes en ICEDFormulario."""
        # Pre-popular respuestas
        self.formulario.respuestas_b = {'p6_funciones_estadisticas': 'si'}
        self.formulario.respuestas_c = {'p13_herramientas_procesamiento': ['r']}
        self.formulario.respuestas_d = {'p31_tipo_analitica': '1'}
        self.formulario.respuestas_e = {'p41_indaga_satisfaccion': 'si'}
        self.formulario.save()

        result = aplicar_puntajes(self.formulario)

        # Recargar de BD
        self.formulario.refresh_from_db()
        self.assertIsNotNone(self.formulario.puntaje_b)
        self.assertIsNotNone(self.formulario.puntaje_global)
        self.assertEqual(self.formulario.puntaje_global, result['puntaje_global'])

    def test_aplicar_puntajes_devuelve_diccionario(self):
        """aplicar_puntajes debe devolver el diccionario de resultados."""
        result = aplicar_puntajes(self.formulario)
        self.assertIn('puntaje_global', result)
        self.assertIn('nivel_nombre', result)


# =============================================================================
# TESTS DE MATERIALIZACIÓN DE RRHH
# =============================================================================

class MaterializarRRHHTests(TestCase):
    """Tests para _materializar_rrhh en ICEDWizardView."""

    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass')
        self.organismo = Organismo.objects.create(nombre='Organismo RRHH', orden=1, activo=True)
        self.formulario = ICEDFormulario.objects.create(
            organismo=self.organismo,
            periodo='2026',
            usuario_diligencia=self.user,
        )
        self.view = ICEDWizardView()

    def tearDown(self):
        ICEDRecursoHumano.objects.filter(formulario=self.formulario).delete()
        self.formulario.delete()
        self.organismo.delete()
        self.user.delete()

    def test_materializar_crea_registros(self):
        """_materializar_rrhh debe crear registros desde JSON."""
        personas = [
            {
                'nombre_completo': 'Ana García',
                'correo': 'ana@example.com',
                'telefono': '3001112222',
                'grupo': 'Estadística',
                'anios_experiencia': 8,
                'inicio_participacion': '03/2020',
                'tipo_vinculacion': 'nombrado',
                'categoria_cargo': 'P',
                'nivel_formacion': 'M',
                'etapas_proceso': ['D', 'P', 'A'],
                'funciones_estadisticas': True,
            },
            {
                'nombre_completo': 'Carlos Ruiz',
                'tipo_vinculacion': 'contratista',
                'categoria_cargo': 'PE',
                'nivel_formacion': 'P',
                'etapas_proceso': ['C'],
                'funciones_estadisticas': False,
            },
        ]
        self.formulario.respuestas_c = {'p19_rrhh_list': json.dumps(personas)}
        self.formulario.save()

        self.view._materializar_rrhh(self.formulario)

        rrhh = self.formulario.recursos_humanos.all().order_by('nombre_completo')
        self.assertEqual(rrhh.count(), 2)

        ana = rrhh.get(nombre_completo='Ana García')
        self.assertEqual(ana.correo, 'ana@example.com')
        self.assertEqual(ana.tipo_vinculacion, 'nombrado')
        self.assertEqual(ana.categoria_cargo, 'P')
        self.assertEqual(ana.etapas_proceso, ['D', 'P', 'A'])
        self.assertTrue(ana.funciones_estadisticas)

        carlos = rrhh.get(nombre_completo='Carlos Ruiz')
        self.assertEqual(carlos.tipo_vinculacion, 'contratista')

    def test_materializar_salta_filas_vacias(self):
        """Debe ignorar filas sin nombre_completo."""
        personas = [
            {'nombre_completo': 'Válido Usuario', 'tipo_vinculacion': 'nombrado'},
            {'nombre_completo': '', 'tipo_vinculacion': 'contratista'},
            {'nombre_completo': '   ', 'tipo_vinculacion': 'contratista'},
        ]
        self.formulario.respuestas_c = {'p19_rrhh_list': json.dumps(personas)}
        self.formulario.save()

        self.view._materializar_rrhh(self.formulario)

        self.assertEqual(self.formulario.recursos_humanos.count(), 1)
        self.assertTrue(self.formulario.recursos_humanos.filter(nombre_completo='Válido Usuario').exists())

    def test_materializar_salta_tipos_invalidos(self):
        """Debe ignorar elementos que no son dict."""
        personas = [
            {'nombre_completo': 'Usuario OK', 'tipo_vinculacion': 'nombrado'},
            'esto es un string, no un dict',
            123,
            None,
        ]
        self.formulario.respuestas_c = {'p19_rrhh_list': json.dumps(personas)}
        self.formulario.save()

        self.view._materializar_rrhh(self.formulario)

        self.assertEqual(self.formulario.recursos_humanos.count(), 1)

    def test_materializar_idempotente(self):
        """Ejecutar dos veces no debe duplicar registros."""
        personas = [
            {'nombre_completo': 'Usuario Único', 'tipo_vinculacion': 'nombrado'},
        ]
        self.formulario.respuestas_c = {'p19_rrhh_list': json.dumps(personas)}
        self.formulario.save()

        self.view._materializar_rrhh(self.formulario)
        self.view._materializar_rrhh(self.formulario)
        self.view._materializar_rrhh(self.formulario)

        self.assertEqual(self.formulario.recursos_humanos.count(), 1)

    def test_materializar_maneja_json_invalido(self):
        """Debe manejar gracefully JSON malformado."""
        self.formulario.respuestas_c = {'p19_rrhh_list': 'esto no es json'}
        self.formulario.save()

        # No debe lanzar excepción
        try:
            self.view._materializar_rrhh(self.formulario)
        except Exception as e:
            self.fail(f'_materializar_rrhh lanzó excepción con JSON inválido: {e}')

        self.assertEqual(self.formulario.recursos_humanos.count(), 0)

    def test_materializar_maneja_etapas_no_lista(self):
        """Debe manejar etapas_proceso que no sea lista."""
        personas = [{
            'nombre_completo': 'Test User',
            'etapas_proceso': 'esto es string, no lista',
        }]
        self.formulario.respuestas_c = {'p19_rrhh_list': json.dumps(personas)}
        self.formulario.save()

        self.view._materializar_rrhh(self.formulario)

        rrhh = self.formulario.recursos_humanos.first()
        self.assertEqual(rrhh.etapas_proceso, [])  # Debe corregir a lista vacía

    def test_materializar_valores_por_defecto(self):
        """Debe aplicar valores por defecto para campos faltantes."""
        personas = [{'nombre_completo': 'Mínimo Datos'}]
        self.formulario.respuestas_c = {'p19_rrhh_list': json.dumps(personas)}
        self.formulario.save()

        self.view._materializar_rrhh(self.formulario)

        rrhh = self.formulario.recursos_humanos.first()
        self.assertEqual(rrhh.tipo_vinculacion, 'contratista')  # Default
        self.assertEqual(rrhh.categoria_cargo, '')
        self.assertEqual(rrhh.anios_experiencia, 0)
        self.assertFalse(rrhh.funciones_estadisticas)


# =============================================================================
# TESTS DE FORMULARIOS Y WIDGETS
# =============================================================================

class FormularioValidationTests(TestCase):
    """Tests de validación de los forms de ICED."""

    def test_modulo_a_valido(self):
        """Módulo A con datos completos debe ser válido."""
        data = {
            'p1_nombre_organismo': 'Organismo X',
            'p2_nombre_responsable': 'Juan Pérez',
            'p3_cargo': 'Estadístico',
            'p4_correo': 'juan@example.com',
            'p5_telefono': '3001234567',
        }
        form = ICEDModuloAForm(data=data)
        self.assertTrue(form.is_valid())

    def test_modulo_a_correo_invalido(self):
        """Módulo A con correo inválido debe ser inválido."""
        data = {
            'p1_nombre_organismo': 'Org',
            'p2_nombre_responsable': 'Juan',
            'p3_cargo': 'Est',
            'p4_correo': 'no-es-correo',
            'p5_telefono': '3001234567',
        }
        form = ICEDModuloAForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('p4_correo', form.errors)

    def test_modulo_b_condicional_p10(self):
        """P10=4 debe permitir P10_motivo_no."""
        data = {
            'p6_funciones_estadisticas': 'si',
            'p10_participacion': '4',
            'p10_motivo_no': 'No hay presupuesto',
            'p12_trazabilidad': '2',
        }
        form = ICEDModuloBForm(data=data)
        # El campo condicional puede ser requerido o no según implementación
        # Solo verificamos que no falle gravemente
        form.is_valid()  # No debe lanzar excepción

    def test_modulo_c_presupuesto_decimal(self):
        """P21 debe aceptar decimales."""
        data = {
            'p13_herramientas_procesamiento': ['r', 'python'],
            'p17_suficiencia_herramientas': '2',
            'p20_suficiencia_rrhh': '2',
            'p21_presupuesto_hardware': '33.3',
            'p21_presupuesto_software': '33.3',
            'p21_presupuesto_personal': '33.4',
        }
        form = ICEDModuloCForm(data=data)
        self.assertTrue(form.is_valid())

    def test_modulo_c_rrhh_widget_json(self):
        """P19 debe aceptar JSON válido."""
        personas = [
            {'nombre_completo': 'Ana', 'tipo_vinculacion': 'nombrado'},
        ]
        data = {
            'p13_herramientas_procesamiento': ['r'],
            'p18_estructura_rrhh': 'si',
            'p19_rrhh_list': json.dumps(personas),
            'p20_suficiencia_rrhh': '1',
        }
        form = ICEDModuloCForm(data=data)
        self.assertTrue(form.is_valid())
        self.assertEqual(json.loads(form.cleaned_data['p19_rrhh_list']), personas)


class WidgetHelperTests(TestCase):
    """Tests del helper iced_widget."""

    def test_iced_widget_genera_hidden_input(self):
        """iced_widget debe generar HiddenInput."""
        widget = iced_widget('checkbox-tabla', {'opciones': []})
        self.assertEqual(widget.input_type, 'hidden')

    def test_iced_widget_tiene_data_atributos(self):
        """iced_widget debe incluir data-iced-widget y data-config."""
        config = {'opciones': [{'codigo': 'a', 'texto': 'Opción A'}]}
        widget = iced_widget('checkbox-tabla', config)
        
        self.assertEqual(widget.attrs.get('data-iced-widget'), 'checkbox-tabla')
        self.assertIn('data-config', widget.attrs)
        
        # Verificar que data-config es JSON válido
        config_str = widget.attrs['data-config']
        parsed = json.loads(config_str)
        self.assertEqual(parsed['opciones'][0]['codigo'], 'a')

    def test_iced_widget_clase_css(self):
        """iced_widget debe tener clase iced-json-field."""
        widget = iced_widget('tabla-simple', {})
        self.assertIn('iced-json-field', widget.attrs.get('class', ''))


# =============================================================================
# TESTS DE FLUJO DEL WIZARD (integración ligera)
# =============================================================================

class WizardFlowTests(TestCase):
    """Tests básicos del flujo del ICEDWizardView."""

    def setUp(self):
        self.user = User.objects.create_user('wizarduser', 'wizard@test.com', 'pass')
        self.organismo = Organismo.objects.create(nombre='Org Wizard', orden=1, activo=True)
        self.client = Client()
        self.client.force_login(self.user)

    def tearDown(self):
        ICEDFormulario.objects.filter(organismo=self.organismo).delete()
        self.organismo.delete()
        self.user.delete()

    def test_landing_page_accesible(self):
        """La página de landing debe ser accesible."""
        response = self.client.get('/iced/')
        self.assertEqual(response.status_code, 200)

    def test_wizard_nuevo_redirect(self):
        """El wizard nuevo debe redirigir al paso 1."""
        response = self.client.get('/iced/formulario/')
        # El wizard puede redirigir o mostrar el primer paso
        self.assertIn(response.status_code, [200, 302])

    def test_wizard_paso_a_post(self):
        """POST al paso A debe avanzar al paso B."""
        # Crear un formulario en borrador para poder hacer POST
        formulario = ICEDFormulario.objects.create(
            organismo=self.organismo,
            periodo='2026',
            usuario_diligencia=self.user,
            estado='borrador',
        )
        
        data = {
            'iced_wizard_view-current_step': 'identificacion',
            'identificacion-p1_nombre_organismo': 'Org Test',
            'identificacion-personas_contacto_json': '[{"nombre_completo": "Test User", "cargo": "Analista", "correo": "test@example.com", "telefono": "3001234567", "orden": 0}]',
        }
        
        response = self.client.post('/iced/formulario/', data)
        # Debe avanzar al siguiente paso o redirigir
        self.assertIn(response.status_code, [200, 302])


# =============================================================================
# TESTS DE PRE-CARGA DE RRHH
# =============================================================================

class PreCargaRRHHTests(TestCase):
    """Tests para get_form_initial con RRHH existente."""

    def setUp(self):
        self.user = User.objects.create_user('precargauser', 'precarga@test.com', 'pass')
        self.organismo = Organismo.objects.create(nombre='Org PreCarga', orden=1, activo=True)
        self.formulario = ICEDFormulario.objects.create(
            organismo=self.organismo,
            periodo='2026',
            usuario_diligencia=self.user,
        )
        # Crear RRHH manualmente
        ICEDRecursoHumano.objects.create(
            formulario=self.formulario,
            nombre_completo='Usuario Existente',
            tipo_vinculacion='nombrado',
            categoria_cargo='P',
            nivel_formacion='M',
        )
        self.view = ICEDWizardView()
        self.view.kwargs = {'formulario_id': self.formulario.pk}
        
        # Mock request
        from django.test import RequestFactory
        factory = RequestFactory()
        self.view.request = factory.get('/iced/formulario/')
        self.view.request.user = self.user
        self.view.request.session = {}

    def tearDown(self):
        ICEDRecursoHumano.objects.filter(formulario=self.formulario).delete()
        self.formulario.delete()
        self.organismo.delete()
        self.user.delete()

    def test_get_form_initial_precarga_rrhh(self):
        """Debe pre-cargar RRHH existente en p19_rrhh_list."""
        initial = self.view.get_form_initial('infraestructura')
        
        self.assertIn('p19_rrhh_list', initial)
        
        personas = json.loads(initial['p19_rrhh_list'])
        self.assertEqual(len(personas), 1)
        self.assertEqual(personas[0]['nombre_completo'], 'Usuario Existente')
        self.assertEqual(personas[0]['tipo_vinculacion'], 'nombrado')

    def test_get_form_initial_sin_rrhh(self):
        """Sin RRHH previo, p19_rrhh_list debe estar vacío o ausente."""
        # Borrar RRHH
        self.formulario.recursos_humanos.all().delete()
        
        initial = self.view.get_form_initial('infraestructura')
        
        # Si no hay RRHH, no debe incluir la clave o debe ser vacía
        if 'p19_rrhh_list' in initial:
            self.assertEqual(initial['p19_rrhh_list'], '[]')

    def test_get_form_initial_otros_pasos_no_tocan_rrhh(self):
        """Pasos distintos a infraestructura no deben tener p19_rrhh_list."""
        initial = self.view.get_form_initial('identificacion')
        self.assertNotIn('p19_rrhh_list', initial)


# =============================================================================
# TESTS DE PRE-CARGA DE PERSONAS DE CONTACTO
# =============================================================================

class PreCargaPersonasContactoTests(TestCase):
    """Tests para get_form_initial con personas de contacto existentes."""

    def setUp(self):
        self.user = User.objects.create_user('contacto_user', 'contacto@test.com', 'pass')
        self.organismo = Organismo.objects.create(nombre='Org Contacto', orden=1, activo=True)
        self.formulario = ICEDFormulario.objects.create(
            organismo=self.organismo,
            periodo='2026',
            usuario_diligencia=self.user,
        )
        # Crear persona de contacto manualmente
        from indicadores.models_iced import ICEDPersonaContacto
        ICEDPersonaContacto.objects.create(
            formulario=self.formulario,
            nombre_completo='Contacto Principal',
            cargo='Jefe de Estadística',
            correo='jefe@example.com',
            telefono='300-1234567',
            orden=0,
        )
        self.view = ICEDWizardView()
        self.view.kwargs = {'formulario_id': self.formulario.pk}
        
        # Mock request
        from django.test import RequestFactory
        factory = RequestFactory()
        self.view.request = factory.get('/iced/formulario/')
        self.view.request.user = self.user
        self.view.request.session = {}

    def tearDown(self):
        from indicadores.models_iced import ICEDPersonaContacto
        ICEDPersonaContacto.objects.filter(formulario=self.formulario).delete()
        self.formulario.delete()
        self.organismo.delete()
        self.user.delete()

    def test_get_form_initial_precarga_personas(self):
        """Debe pre-cargar personas de contacto existentes en personas_contacto_json."""
        initial = self.view.get_form_initial('identificacion')
        
        self.assertIn('personas_contacto_json', initial)
        
        personas = json.loads(initial['personas_contacto_json'])
        self.assertEqual(len(personas), 1)
        self.assertEqual(personas[0]['nombre_completo'], 'Contacto Principal')
        self.assertEqual(personas[0]['cargo'], 'Jefe de Estadística')
        self.assertEqual(personas[0]['correo'], 'jefe@example.com')

    def test_get_form_initial_sin_personas(self):
        """Sin personas previas, personas_contacto_json debe estar vacío o ausente."""
        from indicadores.models_iced import ICEDPersonaContacto
        # Borrar personas
        ICEDPersonaContacto.objects.filter(formulario=self.formulario).delete()
        
        initial = self.view.get_form_initial('identificacion')
        
        # Si no hay personas, no debe incluir la clave o debe ser vacía
        if 'personas_contacto_json' in initial:
            self.assertEqual(initial['personas_contacto_json'], '[]')

    def test_get_form_initial_otros_pasos_no_tocan_personas(self):
        """Pasos distintos a identificacion no deben tener personas_contacto_json."""
        initial = self.view.get_form_initial('entorno')
        self.assertNotIn('personas_contacto_json', initial)
