import io
import pandas as pd
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import InMemoryUploadedFile

from indicadores.views_recoleccion import (
    _dt_prepare_block_melted,
    _dt_process_sheet,
    _dt_analyze_sheet,
    _dt_read_raw,
    _dt_find_header_row,
    _dt_split_groups,
    _dt_clean_val,
    _dt_clean_numeric_val,
    _dt_detect_double_header,
    _dt_prepare_crossed_melted,
)
from indicadores.wizard_admin_unificado import _limpiar_valor_numerico

User = get_user_model()


class DeconstruirTablaHelperTests(TestCase):
    """Tests directos de las funciones helper de deconstruir_tabla."""

    def test_prepare_block_melted_basic(self):
        """Un solo grupo con años en columnas se funde correctamente."""
        df = pd.DataFrame({
            'Zona': ['Bogotá', 'Medellín'],
            '2020': [10, 20],
            '2021': [11, 21],
        })
        result = _dt_prepare_block_melted(df, ['Zona', '2020', '2021'], 'Desagregacion_Geografica')

        self.assertIsNotNone(result)
        self.assertIn('Desagregacion_Geografica', result.columns)
        self.assertIn('Año', result.columns)
        self.assertIn('Valor', result.columns)
        self.assertNotIn('Zona', result.columns)  # renombrada
        self.assertEqual(len(result), 4)  # 2 zonas × 2 años

    def test_prepare_block_melted_no_year_cols(self):
        """Sin columnas-año debe retornar None."""
        df = pd.DataFrame({
            'Foo': ['A', 'B'],
            'Bar': [1, 2],
        })
        result = _dt_prepare_block_melted(df, ['Foo', 'Bar'], 'Grupo')
        self.assertIsNone(result)

    def test_prepare_block_melted_empty_values_filtered(self):
        """Filas con valor vacío deben descartarse."""
        df = pd.DataFrame({
            'Sexo': ['Hombre', 'Mujer'],
            '2020': [10, ''],
        })
        result = _dt_prepare_block_melted(df, ['Sexo', '2020'], 'Desagregacion_Tematica_1')
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]['Desagregacion_Tematica_1'], 'Hombre')

    def test_prepare_block_melted_year_cleaning(self):
        """La columna Año debe limpiarse a string entero."""
        df = pd.DataFrame({
            'Cat': ['A'],
            '2020.0': [5],
        })
        result = _dt_prepare_block_melted(df, ['Cat', '2020.0'], 'Grupo')
        self.assertIn('Año', result.columns)
        self.assertEqual(str(result.iloc[0]['Año']), '2020')


class DeconstruirTablaProcessSheetTests(TestCase):
    """Tests de _dt_process_sheet con archivos reales en memoria."""

    def _build_excel(self, sheets_data):
        """Crea un Excel en memoria. sheets_data = {sheet_name: DataFrame}."""
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            for name, df in sheets_data.items():
                df.to_excel(writer, sheet_name=name, index=False, header=False)
        buffer.seek(0)
        # _dt_read_raw necesita .name para elegir el engine
        buffer.name = 'test.xlsx'
        return buffer

    def test_process_sheet_single_group(self):
        """Hoja con un solo grupo de desagregación."""
        df = pd.DataFrame([
            ['Localidad', '2020', '2021'],
            ['Bogotá', 100, 110],
            ['Medellín', 200, 210],
        ])
        buf = self._build_excel({'Datos': df})

        result = _dt_process_sheet(
            buf, 'Datos',
            {'0': 'Desagregacion_Geografica'},
            codigo_indicador='ICET_TEST_01',
            nombre_indicador='Indicador de prueba'
        )

        self.assertIsNotNone(result)
        self.assertIn('Codigo_Indicador', result.columns)
        self.assertIn('Nombre_Indicador', result.columns)
        self.assertEqual(result.iloc[0]['Codigo_Indicador'], 'ICET_TEST_01')
        self.assertEqual(result.iloc[0]['Nombre_Indicador'], 'Indicador de prueba')
        self.assertIn('Desagregacion_Geografica', result.columns)
        self.assertIn('Año', result.columns)
        self.assertIn('Valor', result.columns)
        # Verificar orden de columnas
        self.assertEqual(list(result.columns)[0], 'Codigo_Indicador')
        self.assertEqual(list(result.columns)[1], 'Nombre_Indicador')
        self.assertEqual(list(result.columns)[2], 'Año')

    def test_process_sheet_multiple_groups(self):
        """Hoja con dos grupos separados por fila en blanco."""
        # Simular dos bloques separados por fila vacía
        df = pd.DataFrame([
            ['Localidad', '2020', '2021'],
            ['Bogotá', 100, 110],
            ['Medellín', 200, 210],
            [None, None, None],  # fila separadora
            ['Sexo', '2020', '2021'],
            ['Hombre', 50, 55],
            ['Mujer', 60, 65],
        ])
        buf = self._build_excel({'Datos': df})

        result = _dt_process_sheet(
            buf, 'Datos',
            {'0': 'Desagregacion_Geografica', '1': 'Desagregacion_Tematica_1'},
            codigo_indicador='ICET_TEST_02',
            nombre_indicador='Indicador multiple'
        )

        self.assertIsNotNone(result)
        self.assertIn('Desagregacion_Geografica', result.columns)
        self.assertIn('Desagregacion_Tematica_1', result.columns)
        self.assertEqual(list(result.columns)[0], 'Codigo_Indicador')
        self.assertEqual(list(result.columns)[1], 'Nombre_Indicador')
        self.assertEqual(list(result.columns)[2], 'Año')

    def test_process_sheet_masivo_mode(self):
        """Modo masivo: usa nombre de hoja como código si no empieza con 'Hoja'."""
        df = pd.DataFrame([
            ['Zona', '2020'],
            ['Norte', 15],
        ])
        buf = self._build_excel({'ICET_MAS_01': df})

        result = _dt_process_sheet(buf, 'ICET_MAS_01', {'0': 'Desagregacion_Geografica'}, codigo_indicador='ICET_MAS_01')
        self.assertIsNotNone(result)
        self.assertEqual(result.iloc[0]['Codigo_Indicador'], 'ICET_MAS_01')


@override_settings(DEBUG=True)
class DeconstruirTablaViewTests(TestCase):
    """Tests de integración de la vista deconstruir_tabla."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser', password='testpass', is_staff=True
        )
        self.client.force_login(self.user)

    def _build_uploaded_file(self, filename='test.xlsx', sheets_data=None):
        if sheets_data is None:
            sheets_data = {'Hoja1': pd.DataFrame([
                ['Localidad', '2020', '2021'],
                ['Bogotá', 10, 20],
            ])}
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            for name, df in sheets_data.items():
                df.to_excel(writer, sheet_name=name, index=False, header=False)
        buffer.seek(0)
        return InMemoryUploadedFile(
            buffer, 'archivo', filename,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            buffer.getbuffer().nbytes, None
        )

    def test_get_page_loads(self):
        """La página carga correctamente."""
        response = self.client.get('/recoleccion/deconstruir-tabla/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Deconstruir Tabla')

    def test_upload_individual_creates_wizard(self):
        """Subir archivo en modo individual crea sesión wizard paso 2."""
        archivo = self._build_uploaded_file()
        response = self.client.post('/recoleccion/deconstruir-tabla/', {
            'action': 'upload',
            'modo': 'individual',
            'archivo': archivo,
        })
        # Debe redirigir a GET con la sesión wizard en paso 2
        self.assertEqual(response.status_code, 302)

    def test_upload_masivo_creates_wizard(self):
        """Subir archivo en modo masivo crea sesión wizard paso 2."""
        archivo = self._build_uploaded_file(sheets_data={
            'ICET_01': pd.DataFrame([['Zona', '2020'], ['Norte', 5]]),
            'ICET_02': pd.DataFrame([['Sexo', '2020'], ['Hombre', 3]]),
        })
        response = self.client.post('/recoleccion/deconstruir-tabla/', {
            'action': 'upload',
            'modo': 'masivo',
            'archivo': archivo,
        })
        self.assertEqual(response.status_code, 302)

    def test_permission_required(self):
        """Usuario sin permisos es rechazado."""
        User.objects.filter(username='testuser').update(is_staff=False)
        response = self.client.get('/recoleccion/deconstruir-tabla/')
        self.assertEqual(response.status_code, 302)  # redirect a login o acceso_modulos


class CleanValTests(TestCase):
    """Tests para _dt_clean_val con guiones y valores especiales."""

    def test_dash_treated_as_empty(self):
        self.assertEqual(_dt_clean_val('-'), '')

    def test_double_dash_treated_as_empty(self):
        self.assertEqual(_dt_clean_val('--'), '')

    def test_na_treated_as_empty(self):
        self.assertEqual(_dt_clean_val('N/A'), '')

    def test_normal_string_preserved(self):
        self.assertEqual(_dt_clean_val('  Livianos  '), 'Livianos')

    def test_float_as_int(self):
        self.assertEqual(_dt_clean_val(2020.0), 2020)

    def test_nan_is_empty(self):
        self.assertEqual(_dt_clean_val(float('nan')), '')


class CleanNumericValTests(TestCase):
    """Tests para _dt_clean_numeric_val: separadores de miles, guiones, etc."""

    def test_dash_returns_none(self):
        self.assertIsNone(_dt_clean_numeric_val('-'))

    def test_empty_returns_none(self):
        self.assertIsNone(_dt_clean_numeric_val(''))

    def test_thousands_separator_comma(self):
        self.assertEqual(_dt_clean_numeric_val('122,619'), 122619)

    def test_plain_integer(self):
        self.assertEqual(_dt_clean_numeric_val('773'), 773)

    def test_plain_zero(self):
        self.assertEqual(_dt_clean_numeric_val('0'), 0)

    def test_float_passthrough(self):
        self.assertEqual(_dt_clean_numeric_val(3.14), 3.14)

    def test_int_passthrough(self):
        self.assertEqual(_dt_clean_numeric_val(42), 42)

    def test_nan_returns_none(self):
        self.assertIsNone(_dt_clean_numeric_val(float('nan')))

    def test_non_numeric_string_returns_none(self):
        self.assertIsNone(_dt_clean_numeric_val('abc'))


class LimpiarValorNumericoTests(TestCase):
    """Tests para _limpiar_valor_numerico del wizard."""

    def test_dash_is_sin_dato(self):
        val, es_sin_dato = _limpiar_valor_numerico('-')
        self.assertIsNone(val)
        self.assertTrue(es_sin_dato)

    def test_empty_is_sin_dato(self):
        val, es_sin_dato = _limpiar_valor_numerico('')
        self.assertIsNone(val)
        self.assertTrue(es_sin_dato)

    def test_non_numeric_is_error(self):
        val, es_sin_dato = _limpiar_valor_numerico('abc')
        self.assertIsNone(val)
        self.assertFalse(es_sin_dato)  # error real, no "sin dato"

    def test_thousands_separator(self):
        val, es_sin_dato = _limpiar_valor_numerico('122,619')
        self.assertEqual(val, 122619.0)
        self.assertFalse(es_sin_dato)

    def test_normal_float(self):
        val, es_sin_dato = _limpiar_valor_numerico(3.5)
        self.assertEqual(val, 3.5)
        self.assertFalse(es_sin_dato)


class DoubleHeaderDetectionTests(TestCase):
    """Tests para detección de doble header y melt cruzado con 3 dominios."""

    def _build_crossed_df(self):
        """Simula la estructura del CSV prueba.csv: doble header + jerarquía padre/hijo."""
        # Row 0: header con años (repetidos)
        # Row 1: sub-categorías
        # Row 2: fila vacía (separadora)
        # Row 3: TOTAL (padre grupo 1)
        # Row 4: fila vacía (separadora)
        # Row 5: Livianos (padre grupo 2)
        # Row 6: Automóvil (hijo)
        # Row 7: Camioneta (hijo)
        data = [
            ['Clase de vehículo', 1987, 1987, 1987, 1987, '', 1988, 1988, 1988, 1988],
            ['', 'Particular', 'Oficial', 'Público', 'Total', '', 'Particular', 'Oficial', 'Público', 'Total'],
            [None, None, None, None, None, None, None, None, None, None],
            ['TOTAL', '122,619', '6,903', '14,504', '144,026', '', '140,218', '7,381', '17,098', '164,697'],
            [None, None, None, None, None, None, None, None, None, None],
            ['Livianos', '78,060', '5,142', '-', '83,202', '', '90,503', '5,700', '-', '96,203'],
            ['Automóvil', '51,320', '4,213', '-', '55,533', '', '58,892', '4,650', '-', '63,542'],
            ['Camioneta', '16,100', '1,809', '603', '18,512', '', '16,760', '2,323', '608', '19,691'],
        ]
        return pd.DataFrame(data)

    def test_detect_double_header(self):
        """Detecta correctamente el doble header."""
        df = self._build_crossed_df()
        is_double, sub_idx = _dt_detect_double_header(df, 0)
        self.assertTrue(is_double)
        self.assertEqual(sub_idx, 1)

    def test_crossed_melted_3_domains(self):
        """El melt cruzado produce 3 dominios: padre, hijo, header2."""
        df = self._build_crossed_df()
        result = _dt_prepare_crossed_melted(
            df, 0, 1, 'Clase_Vehiculo', 'Subclase_Vehiculo', 'Tipo_Servicio'
        )

        self.assertIsNotNone(result)
        self.assertIn('Año', result.columns)
        self.assertIn('Clase_Vehiculo', result.columns)
        self.assertIn('Subclase_Vehiculo', result.columns)
        self.assertIn('Tipo_Servicio', result.columns)
        self.assertIn('Valor', result.columns)

        # 5 columnas en total
        self.assertEqual(len(result.columns), 5)

    def test_parent_filldown(self):
        """Los hijos heredan el padre correcto (fill-down)."""
        df = self._build_crossed_df()
        result = _dt_prepare_crossed_melted(
            df, 0, 1, 'Clase', 'Subclase', 'Servicio'
        )

        # Automóvil y Camioneta deben tener padre "Livianos"
        automovil_rows = result[result['Subclase'] == 'Automóvil']
        self.assertTrue(len(automovil_rows) > 0)
        self.assertTrue((automovil_rows['Clase'] == 'Livianos').all())

        camioneta_rows = result[result['Subclase'] == 'Camioneta']
        self.assertTrue(len(camioneta_rows) > 0)
        self.assertTrue((camioneta_rows['Clase'] == 'Livianos').all())

    def test_parent_rows_excluded(self):
        """Las filas padre (TOTAL, Livianos) no aparecen como hijos."""
        df = self._build_crossed_df()
        result = _dt_prepare_crossed_melted(
            df, 0, 1, 'Clase', 'Subclase', 'Servicio'
        )

        # Livianos no debe aparecer como Subclase
        self.assertFalse((result['Subclase'] == 'Livianos').any())
        # TOTAL no debe aparecer como Subclase
        self.assertFalse((result['Subclase'] == 'TOTAL').any())

    def test_dash_values_omitted(self):
        """Guiones se tratan como null y no generan filas."""
        df = self._build_crossed_df()
        result = _dt_prepare_crossed_melted(
            df, 0, 1, 'Clase', 'Subclase', 'Servicio'
        )

        # Automóvil + Público + 1987 = dash → no debe existir
        auto_pub_87 = result[
            (result['Subclase'] == 'Automóvil') &
            (result['Servicio'] == 'Público') &
            (result['Año'] == '1987')
        ]
        self.assertEqual(len(auto_pub_87), 0)

    def test_thousands_separator_cleaned(self):
        """Valores con comas de miles se limpian correctamente."""
        df = self._build_crossed_df()
        result = _dt_prepare_crossed_melted(
            df, 0, 1, 'Clase', 'Subclase', 'Servicio'
        )

        auto_part_87 = result[
            (result['Subclase'] == 'Automóvil') &
            (result['Servicio'] == 'Particular') &
            (result['Año'] == '1987')
        ]
        self.assertEqual(len(auto_part_87), 1)
        self.assertEqual(auto_part_87.iloc[0]['Valor'], 51320)

    def test_empty_columns_ignored(self):
        """Las columnas vacías (separadores visuales) no generan datos."""
        df = self._build_crossed_df()
        result = _dt_prepare_crossed_melted(
            df, 0, 1, 'Clase', 'Subclase', 'Servicio'
        )
        empty_service = result[result['Servicio'] == '']
        self.assertEqual(len(empty_service), 0)

    def test_no_double_header_for_unique_years(self):
        """No detecta doble header si los años no se repiten."""
        df = pd.DataFrame([
            ['Zona', 2020, 2021, 2022],
            ['Bogotá', 10, 20, 30],
        ])
        is_double, _ = _dt_detect_double_header(df, 0)
        self.assertFalse(is_double)

    def test_analyze_sheet_3_groups(self):
        """_dt_analyze_sheet en modo cruzado detecta 3 grupos."""
        df = self._build_crossed_df()
        # Guardar como Excel en memoria
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Hoja1', index=False, header=False)
        buf.seek(0)
        buf.name = 'test.xlsx'

        analysis = _dt_analyze_sheet(buf, sheet_name='Hoja1')
        self.assertTrue(analysis.get('is_crossed'))
        self.assertEqual(analysis['num_groups'], 3)
        # Grupo 0 = padres (TOTAL, Livianos)
        self.assertEqual(analysis['groups_info'][0]['total'], 2)
        # Grupo 1 = hijos (Automóvil, Camioneta)
        self.assertEqual(analysis['groups_info'][1]['total'], 2)
        # Grupo 2 = segundo header (Particular, Oficial, Público, Total)
        self.assertEqual(analysis['groups_info'][2]['total'], 4)

    def test_fallback_all_parents_no_children(self):
        """Si todas las filas son padres sin hijos, se incluyen directamente."""
        data = [
            ['Clase', 2020, 2020, 2020],
            ['', 'A', 'B', 'C'],
            [None, None, None, None],
            ['Solo1', 10, 20, 30],
            [None, None, None, None],
            ['Solo2', 40, 50, 60],
        ]
        df = pd.DataFrame(data)
        result = _dt_prepare_crossed_melted(df, 0, 1, 'Clase', 'Subclase', 'Cat')

        self.assertIsNotNone(result)
        # Cada padre genera 3 filas (3 sub-categorías), 2 padres = 6 filas
        self.assertEqual(len(result), 6)
        # En fallback, parent_name y child_name llevan el mismo valor
        solo1 = result[result['Clase'] == 'Solo1']
        self.assertTrue((solo1['Subclase'] == 'Solo1').all())
        self.assertEqual(solo1.iloc[0]['Valor'], 10)
        self.assertEqual(solo1.iloc[0]['Cat'], 'A')

    def test_process_sheet_crossed_mode(self):
        """_dt_process_sheet en modo cruzado produce el formato completo con codigo."""
        df = self._build_crossed_df()
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Hoja1', index=False, header=False)
        buf.seek(0)
        buf.name = 'test.xlsx'

        result = _dt_process_sheet(
            buf, 'Hoja1',
            {'0': 'Clase_Vehiculo', '1': 'Subclase_Vehiculo', '2': 'Tipo_Servicio'},
            codigo_indicador='ICET_TEST',
            nombre_indicador='Test',
        )
        self.assertIsNotNone(result)
        self.assertIn('Codigo_Indicador', result.columns)
        self.assertIn('Nombre_Indicador', result.columns)
        self.assertEqual(result.iloc[0]['Codigo_Indicador'], 'ICET_TEST')
        self.assertEqual(result.iloc[0]['Nombre_Indicador'], 'Test')
        self.assertIn('Clase_Vehiculo', result.columns)
        self.assertIn('Subclase_Vehiculo', result.columns)
        self.assertIn('Tipo_Servicio', result.columns)
        self.assertIn('Año', result.columns)
        self.assertIn('Valor', result.columns)


class CSVReadTests(TestCase):
    """Tests para _dt_read_raw con archivos CSV."""

    def test_read_csv_comma_separated(self):
        """Lee CSV con coma como separador."""
        content = b'a,b,c\n1,2,3\n4,5,6'
        buf = io.BytesIO(content)
        buf.name = 'test.csv'
        df = _dt_read_raw(buf)
        self.assertEqual(len(df.columns), 3)
        self.assertEqual(len(df), 3)  # header + 2 data rows (no header mode)

    def test_read_csv_semicolon_separated(self):
        """Lee CSV con punto y coma como separador."""
        content = b'a;b;c\n1;2;3\n4;5;6'
        buf = io.BytesIO(content)
        buf.name = 'test.csv'
        df = _dt_read_raw(buf)
        self.assertEqual(len(df.columns), 3)

    def test_analyze_csv_works(self):
        """_dt_analyze_sheet funciona con CSV."""
        content = b'Zona,2020,2021\nBogota,10,20\nMedellin,30,40'
        buf = io.BytesIO(content)
        buf.name = 'data.csv'
        analysis = _dt_analyze_sheet(buf, sheet_name=0)
        self.assertNotIn('error', analysis)
        self.assertTrue(analysis.get('has_years', False))


class DesagregacionFiltroTests(TestCase):
    """
    Regresión del bug de filtros: seleccionar 'Hombres' + '0-5' (dominios
    distintos) debe ser AND, no OR; seleccionar dos valores del mismo
    dominio debe ser OR.
    """

    def setUp(self):
        from indicadores.models import (
            MenuDominio, MenuTema, MenuSubtema, Indicador, Dato,
            DominioDesagregacion, Desagregacion,
        )
        from datetime import date

        md = MenuDominio.objects.create(nombre='Dom', slug='dom-test')
        mt = MenuTema.objects.create(nombre='Tema', slug='tema-test', dominio=md)
        st = MenuSubtema.objects.create(nombre='Sub', slug='sub-test', tema=mt)
        self.indicador = Indicador.objects.create(
            nombre='Ind test', codigo_indicador='TEST_01', subtema=st, activo=True
        )

        self.dom_sexo = DominioDesagregacion.objects.create(nombre='Sexo', tipo='tematica')
        self.dom_edad = DominioDesagregacion.objects.create(nombre='Edad', tipo='tematica')

        self.hombres = Desagregacion.objects.create(nombre='Hombres', codigo='H', dominio=self.dom_sexo)
        self.mujeres = Desagregacion.objects.create(nombre='Mujeres', codigo='M', dominio=self.dom_sexo)
        self.edad_0_5 = Desagregacion.objects.create(nombre='0-5', codigo='0-5', dominio=self.dom_edad)
        self.edad_5_10 = Desagregacion.objects.create(nombre='5-10', codigo='5-10', dominio=self.dom_edad)

        # Desagregación de OTRO indicador en el mismo dominio (no debe colarse)
        self.edad_otro = Desagregacion.objects.create(nombre='10-15', codigo='10-15', dominio=self.dom_edad)

        def mk(valor, tems=()):
            d = Dato.objects.create(
                indicador=self.indicador, fecha_dato=date(2023, 12, 31), valor_dato=valor
            )
            if tems:
                d.desagregaciones_tematicas.set(tems)
            return d

        # Datos: solo combinaciones reales del indicador
        self.d_h_05 = mk(10, [self.hombres, self.edad_0_5])
        self.d_h_510 = mk(20, [self.hombres, self.edad_5_10])
        self.d_m_05 = mk(30, [self.mujeres, self.edad_0_5])
        self.d_h_total = mk(40, [self.hombres])  # fila total por sexo

    def test_or_dentro_del_mismo_dominio(self):
        """Seleccionar Hombres y Mujeres (mismo dominio) trae ambos."""
        from indicadores.views import filtrar_datos_por_desagregaciones
        from indicadores.models import Dato
        qs = filtrar_datos_por_desagregaciones(
            Dato.objects.filter(indicador=self.indicador),
            tem_ids=[self.hombres.id, self.mujeres.id],
        )
        self.assertEqual(qs.count(), 4)

    def test_and_entre_dominios(self):
        """Hombres + 0-5 (dominios distintos) = solo la celda Hombres×0-5."""
        from indicadores.views import filtrar_datos_por_desagregaciones
        from indicadores.models import Dato
        qs = filtrar_datos_por_desagregaciones(
            Dato.objects.filter(indicador=self.indicador),
            tem_ids=[self.hombres.id, self.edad_0_5.id],
        )
        self.assertEqual(list(qs), [self.d_h_05])

    def test_seleccion_simple_trae_todas_las_edades(self):
        """Seleccionar solo 'Hombres' trae hombres de todas las edades."""
        from indicadores.views import filtrar_datos_por_desagregaciones
        from indicadores.models import Dato
        qs = filtrar_datos_por_desagregaciones(
            Dato.objects.filter(indicador=self.indicador),
            tem_ids=[self.hombres.id],
        )
        self.assertEqual(
            set(qs), {self.d_h_05, self.d_h_510, self.d_h_total}
        )

    def test_serie_exacta_no_absorbe_desgloses(self):
        """Una serie 'Hombres' no debe incluir 'Hombres-0-5' ni 'Hombres-5-10'."""
        from indicadores.views import _filtrar_datos_por_serie
        from indicadores.models import Dato, Grafico, GraficoSerie

        grafico = Grafico.objects.create(
            indicador=self.indicador, nombre='G', tipo_grafico='line', activo=True
        )
        serie = GraficoSerie.objects.create(grafico=grafico, orden=0)
        serie.desagregaciones.set([self.hombres])

        qs = _filtrar_datos_por_serie(
            Dato.objects.filter(indicador=self.indicador), serie
        )
        self.assertEqual(list(qs), [self.d_h_total])

    def test_serie_combinacion_exacta(self):
        """Una serie 'Hombres - 0-5' solo trae esa combinación exacta."""
        from indicadores.views import _filtrar_datos_por_serie
        from indicadores.models import Dato, Grafico, GraficoSerie

        grafico = Grafico.objects.create(
            indicador=self.indicador, nombre='G2', tipo_grafico='line', activo=True
        )
        serie = GraficoSerie.objects.create(grafico=grafico, orden=0)
        serie.desagregaciones.set([self.hombres, self.edad_0_5])

        qs = _filtrar_datos_por_serie(
            Dato.objects.filter(indicador=self.indicador), serie
        )
        self.assertEqual(list(qs), [self.d_h_05])


class CrearSeriesGraficoTests(TestCase):
    """
    Regresión del bug del wizard: _crear_series_grafico generaba el producto
    cartesiano de TODAS las desagregaciones del dominio (incluidas las de
    otros indicadores). Ahora solo crea series para combinaciones reales.
    """

    def setUp(self):
        from indicadores.models import (
            MenuDominio, MenuTema, MenuSubtema, Indicador, Dato,
            DominioDesagregacion, Desagregacion,
        )
        from datetime import date

        md = MenuDominio.objects.create(nombre='Dom2', slug='dom2-test')
        mt = MenuTema.objects.create(nombre='Tema2', slug='tema2-test', dominio=md)
        st = MenuSubtema.objects.create(nombre='Sub2', slug='sub2-test', tema=mt)
        self.indicador = Indicador.objects.create(
            nombre='Ind test2', codigo_indicador='TEST_02', subtema=st, activo=True
        )

        self.dom_edad = DominioDesagregacion.objects.create(nombre='Edad2', tipo='tematica')
        self.e1 = Desagregacion.objects.create(nombre='0-4 años', codigo='a', dominio=self.dom_edad)
        self.e2 = Desagregacion.objects.create(nombre='5-9 años', codigo='b', dominio=self.dom_edad)
        # Desagregación "fantasma": existe en el dominio pero el indicador no la usa
        self.e3 = Desagregacion.objects.create(nombre='0-5', codigo='c', dominio=self.dom_edad)

        for val, desag in [(1, self.e1), (2, self.e2)]:
            d = Dato.objects.create(
                indicador=self.indicador, fecha_dato=date(2023, 12, 31), valor_dato=val
            )
            d.desagregaciones_tematicas.set([desag])

    def test_series_solo_combinaciones_reales(self):
        """No se crean series para desagregaciones que el indicador no usa."""
        from indicadores.wizard_admin_unificado import WizardAdminUnificado
        grafico = WizardAdminUnificado()._crear_series_grafico(self.indicador)

        nombres = set(grafico.series.values_list('nombre_personalizado', flat=True))
        self.assertEqual(nombres, {'0-4 años', '5-9 años'})
        self.assertNotIn('0-5', nombres)
        self.assertEqual(grafico.series.count(), 2)

    def test_serie_total_sin_desagregaciones(self):
        """Indicador sin desagregaciones en los datos → una serie 'Total'."""
        from indicadores.wizard_admin_unificado import WizardAdminUnificado
        from indicadores.models import Dato
        from datetime import date

        Dato.objects.create(
            indicador=self.indicador, fecha_dato=date(2024, 12, 31), valor_dato=5
        )
        # Eliminar los datos con desagregaciones para este caso
        Dato.objects.filter(indicador=self.indicador).exclude(valor_dato=5).delete()

        grafico = WizardAdminUnificado()._crear_series_grafico(self.indicador)
        self.assertEqual(grafico.series.count(), 1)
        self.assertEqual(grafico.series.first().nombre_personalizado, 'Total')


class NormalizarDesagregacionTests(TestCase):
    """_get_or_create_desagregacion no debe duplicar variantes de texto."""

    def test_no_duplica_por_espacios_o_case(self):
        from indicadores.models import DominioDesagregacion, Desagregacion
        from indicadores.wizard_admin_unificado import _get_or_create_desagregacion

        dom = DominioDesagregacion.objects.create(nombre='EdadN', tipo='tematica')
        d1, c1 = _get_or_create_desagregacion('0-4 años', dom, 'col')
        d2, c2 = _get_or_create_desagregacion('  0-4   Años ', dom, 'col')
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(d1.id, d2.id)
        self.assertEqual(Desagregacion.objects.filter(dominio=dom).count(), 1)
