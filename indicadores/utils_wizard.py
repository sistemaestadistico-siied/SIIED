"""
Utilidades para el Wizard Unificado
Funciones reutilizables para diagnóstico, parseo y detección
"""
import csv
import json
from typing import Dict, List, Tuple, Set, Any, Optional
from django.core.files.uploadedfile import UploadedFile
import pandas as pd
import numpy as np


class DiagnosticoConjuntoDatos:
    """Clase para diagnosticar conjunto_datos antes del procesamiento"""
    
    def __init__(self, archivo_csv_path: str):
        self.archivo_csv_path = archivo_csv_path
        self.encoding, self.delimiter = self._detectar_encoding_y_delimitador()
        self.headers = self._leer_headers()
        self.resultado = {
            'exitoso': True,
            'errores': [],
            'advertencias': [],
            'info': {}
        }
    
    def _detectar_encoding_y_delimitador(self) -> Tuple[str, str]:
        """Detecta el encoding y delimitador del archivo CSV"""
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(self.archivo_csv_path, 'r', encoding=encoding) as file:
                    sample = file.read(1024)
                    file.seek(0)
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(sample)
                    return encoding, dialect.delimiter
            except (UnicodeDecodeError, csv.Error):
                continue
        
        return 'utf-8', ','
    
    def _leer_headers(self) -> List[str]:
        """Lee los encabezados del CSV"""
        with open(self.archivo_csv_path, 'r', encoding=self.encoding) as csvfile:
            reader = csv.reader(csvfile, delimiter=self.delimiter)
            return next(reader)
    
    def verificar_columnas_fuente(self, columnas_fuente: List[str]) -> Dict[str, Any]:
        """Verifica que las columnas fuente existan en el CSV"""
        columnas_encontradas = [col for col in columnas_fuente if col in self.headers]
        columnas_faltantes = [col for col in columnas_fuente if col not in self.headers]
        
        resultado = {
            'encontradas': columnas_encontradas,
            'faltantes': columnas_faltantes,
            'exitoso': len(columnas_faltantes) == 0
        }
        
        if columnas_faltantes:
            self.resultado['exitoso'] = False
            self.resultado['errores'].append(
                f"Columnas fuente faltantes: {', '.join(columnas_faltantes)}"
            )
        
        return resultado
    
    def detectar_columna_fecha(self) -> Optional[str]:
        """Detecta la columna que contiene fecha/año"""
        palabras_clave = ['fecha', 'año', 'anio', 'year', 'date', 'periodo']
        
        for header in self.headers:
            header_lower = header.lower()
            for palabra in palabras_clave:
                if palabra in header_lower:
                    self.resultado['info']['columna_fecha'] = header
                    return header
        
        self.resultado['advertencias'].append("No se detectó columna de fecha/año")
        return None
    
    def obtener_valores_unicos(self, columna: str, max_filas: int = 1000) -> Set[str]:
        """Obtiene valores únicos de una columna"""
        valores = set()
        
        with open(self.archivo_csv_path, 'r', encoding=self.encoding) as csvfile:
            reader = csv.reader(csvfile, delimiter=self.delimiter)
            headers = next(reader)
            
            try:
                columna_index = headers.index(columna)
            except ValueError:
                return valores
            
            for i, row in enumerate(reader):
                if i >= max_filas:
                    break
                if len(row) > columna_index and row[columna_index]:
                    valores.add(row[columna_index])
        
        return valores
    
    def detectar_desagregaciones_geograficas(self, dominios_geo) -> Dict[str, Any]:
        """Detecta desagregaciones geográficas en el CSV"""
        resultado = {}
        
        for dominio in dominios_geo:
            # Buscar columnas que contengan el nombre del dominio
            columnas_encontradas = [
                h for h in self.headers 
                if dominio.nombre.lower() in h.lower()
            ]
            
            desagregaciones_definidas = set(
                desag.nombre for desag in dominio.desagregaciones.all()
            )
            
            valores_encontrados = {}
            for columna in columnas_encontradas:
                valores = self.obtener_valores_unicos(columna)
                valores_coincidentes = valores.intersection(desagregaciones_definidas)
                valores_no_definidos = valores.difference(desagregaciones_definidas)
                
                valores_encontrados[columna] = {
                    'total': len(valores),
                    'coincidentes': list(valores_coincidentes),
                    'no_definidos': list(valores_no_definidos)
                }
            
            resultado[dominio.nombre] = {
                'columnas': columnas_encontradas,
                'desagregaciones_definidas': list(desagregaciones_definidas),
                'valores': valores_encontrados
            }
        
        return resultado
    
    def detectar_desagregaciones_tematicas(self, dominios_tema, columna_fecha: Optional[str] = None) -> Dict[str, Any]:
        """Detecta desagregaciones temáticas en el CSV"""
        resultado = {}
        
        # Excluir columnas de fecha y geográficas
        columnas_excluidas = []
        if columna_fecha:
            columnas_excluidas.append(columna_fecha)
        
        headers_filtrados = [h for h in self.headers if h not in columnas_excluidas]
        
        for dominio in dominios_tema:
            desagregaciones = dominio.desagregaciones.all()
            columnas_encontradas = []
            
            for desag in desagregaciones:
                for header in headers_filtrados:
                    if desag.es_rango and desag.valores_rango:
                        # Buscar valores del rango
                        for valor_rango in desag.valores_rango:
                            if str(valor_rango).lower() in header.lower():
                                columnas_encontradas.append(header)
                                break
                    else:
                        # Buscar nombre de desagregación
                        if desag.nombre.lower() == header.lower():
                            columnas_encontradas.append(header)
                        elif desag.nombre.lower() in header.lower():
                            columnas_encontradas.append(header)
            
            resultado[dominio.nombre] = {
                'columnas': list(set(columnas_encontradas)),
                'desagregaciones_count': desagregaciones.count()
            }
        
        return resultado
    
    def ejecutar_diagnostico_completo(self, regla_extraccion, indicador) -> Dict[str, Any]:
        """Ejecuta diagnóstico completo"""
        # 1. Verificar columnas fuente
        columnas_fuente_result = self.verificar_columnas_fuente(regla_extraccion.columnas_fuente)
        
        # 2. Detectar columna fecha
        columna_fecha = self.detectar_columna_fecha()
        
        # 3. Detectar desagregaciones geográficas
        desag_geo = self.detectar_desagregaciones_geograficas(
            indicador.dominios_desagregacion_geografica.all()
        )
        
        # 4. Detectar desagregaciones temáticas
        desag_tema = self.detectar_desagregaciones_tematicas(
            indicador.dominios_desagregacion_tematica.all(),
            columna_fecha
        )
        
        # Construir resultado
        self.resultado['info'].update({
            'total_columnas': len(self.headers),
            'columnas_fuente': columnas_fuente_result,
            'desagregaciones_geograficas': desag_geo,
            'desagregaciones_tematicas': desag_tema,
            'encoding': self.encoding,
            'delimiter': self.delimiter
        })
        
        return self.resultado


class ParseadorMetadata:
    """Clase para parsear archivos de metadata"""
    
    @staticmethod
    def parsear_metadata_indicador(archivo_path: str) -> Dict[str, Any]:
        """
        Parsea metadata del indicador desde CSV o XLSX.
        Formato esperado: encabezados en fila 1, una fila de datos en fila 2 (formato columnar).
        """
        try:
            import pandas as pd
            if archivo_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(archivo_path, sheet_name=0, nrows=2)
            else:
                encoding = ParseadorMetadata._detectar_encoding(archivo_path)
                df = pd.read_csv(archivo_path, encoding=encoding, nrows=2)

            if df.empty:
                return {'exitoso': False, 'error': 'Archivo de metadata vacío', 'metadata': {}}

            row = df.iloc[0]
            metadata = {}
            for col in df.columns:
                val = row[col]
                if pd.notna(val):
                    metadata[str(col).strip()] = str(val).strip()

            return {
                'exitoso': True,
                'metadata': metadata,
                'campos_encontrados': len(metadata)
            }

        except Exception as e:
            return {
                'exitoso': False,
                'error': str(e),
                'metadata': {}
            }
    
    @staticmethod
    def parsear_metadata_variables(archivo_path: str) -> Dict[str, Any]:
        """
        Parsea metadata_variables desde CSV o XLSX.
        Formato esperado: encabezados en fila 1, una fila por variable.
        """
        try:
            import pandas as pd
            if archivo_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(archivo_path, sheet_name=0)
            else:
                encoding = ParseadorMetadata._detectar_encoding(archivo_path)
                df = pd.read_csv(archivo_path, encoding=encoding)

            variables = []
            for _, row in df.iterrows():
                var_dict = {}
                for col in df.columns:
                    val = row[col]
                    if pd.notna(val):
                        var_dict[str(col).strip()] = str(val).strip()
                if var_dict:
                    variables.append(var_dict)

            return {
                'exitoso': True,
                'variables': variables,
                'total_variables': len(variables)
            }

        except Exception as e:
            return {
                'exitoso': False,
                'error': str(e),
                'variables': []
            }
    
    @staticmethod
    def _detectar_encoding(archivo_path: str) -> str:
        """Detecta el encoding del archivo"""
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(archivo_path, 'r', encoding=encoding) as file:
                    file.read()
                return encoding
            except UnicodeDecodeError:
                continue
        
        return 'utf-8'


class DetectorDesagregaciones:
    """Clase para detectar desagregaciones automáticamente"""
    
    @staticmethod
    def detectar_desde_csv(archivo_csv_path: str, max_filas: int = 1000) -> Dict[str, Any]:
        """
        Detecta posibles desagregaciones analizando columnas del CSV
        """
        from indicadores.models import DominioDesagregacion, Desagregacion
        
        # Leer CSV
        diagnostico = DiagnosticoConjuntoDatos(archivo_csv_path)
        
        # Excluir columnas numéricas y de fecha
        columnas_candidatas = []
        columna_fecha = diagnostico.detectar_columna_fecha()
        
        for header in diagnostico.headers:
            if header == columna_fecha:
                continue
            
            # Obtener valores únicos
            valores = diagnostico.obtener_valores_unicos(header, max_filas)
            
            # Si tiene pocos valores únicos, podría ser una desagregación
            if 2 <= len(valores) <= 50:
                columnas_candidatas.append({
                    'columna': header,
                    'valores_unicos': list(valores),
                    'total_valores': len(valores)
                })
        
        # Intentar clasificar como geográfica o temática
        geograficas = []
        tematicas = []
        
        palabras_geo = ['comuna', 'region', 'provincia', 'ciudad', 'pais', 'zona', 'territorio']
        
        for candidata in columnas_candidatas:
            columna_lower = candidata['columna'].lower()
            es_geografica = any(palabra in columna_lower for palabra in palabras_geo)
            
            if es_geografica:
                geograficas.append(candidata)
            else:
                tematicas.append(candidata)
        
        return {
            'geograficas': geograficas,
            'tematicas': tematicas,
            'total_detectadas': len(columnas_candidatas)
        }
    
    @staticmethod
    def comparar_con_bd(valores_csv: List[str], dominio_id: int) -> Dict[str, Any]:
        """
        Compara valores del CSV con desagregaciones existentes en BD
        """
        from indicadores.models import DominioDesagregacion
        
        try:
            dominio = DominioDesagregacion.objects.get(id=dominio_id)
            desagregaciones_bd = set(
                desag.nombre for desag in dominio.desagregaciones.all()
            )
            
            valores_set = set(valores_csv)
            existentes = valores_set.intersection(desagregaciones_bd)
            faltantes = valores_set.difference(desagregaciones_bd)
            
            return {
                'existentes': list(existentes),
                'faltantes': list(faltantes),
                'total_existentes': len(existentes),
                'total_faltantes': len(faltantes)
            }
        
        except Exception as e:
            return {
                'error': str(e),
                'existentes': [],
                'faltantes': valores_csv
            }


def generar_output_diagnostico_html(resultado: Dict[str, Any]) -> str:
    """
    Genera output HTML formateado del diagnóstico para mostrar en el wizard
    """
    html = []
    
    html.append('<div class="diagnostico-output">')
    
    # Estado general
    if resultado['exitoso']:
        html.append('<div class="alert alert-success">')
        html.append('<i class="fas fa-check-circle"></i> ')
        html.append('<strong>Diagnóstico exitoso</strong>')
        html.append('</div>')
    else:
        html.append('<div class="alert alert-danger">')
        html.append('<i class="fas fa-times-circle"></i> ')
        html.append('<strong>Diagnóstico con errores</strong>')
        html.append('</div>')
    
    # Errores
    if resultado['errores']:
        html.append('<div class="errores-section">')
        html.append('<h4>Errores:</h4>')
        html.append('<ul>')
        for error in resultado['errores']:
            html.append(f'<li class="text-danger">{error}</li>')
        html.append('</ul>')
        html.append('</div>')
    
    # Advertencias
    if resultado['advertencias']:
        html.append('<div class="advertencias-section">')
        html.append('<h4>Advertencias:</h4>')
        html.append('<ul>')
        for adv in resultado['advertencias']:
            html.append(f'<li class="text-warning">{adv}</li>')
        html.append('</ul>')
        html.append('</div>')
    
    # Información
    if 'info' in resultado:
        info = resultado['info']
        html.append('<div class="info-section">')
        html.append('<h4>Información:</h4>')
        html.append(f'<p><strong>Total de columnas:</strong> {info.get("total_columnas", 0)}</p>')
        
        if 'columna_fecha' in info:
            html.append(f'<p><strong>Columna de fecha:</strong> {info["columna_fecha"]}</p>')
        
        html.append('</div>')
    
    html.append('</div>')
    
    return '\n'.join(html)


class AplicadorMetadata:
    """Clase para aplicar metadata a indicadores"""
    
    @staticmethod
    def aplicar_metadata_indicador(indicador, metadata_dict: Dict[str, str]) -> Dict[str, Any]:
        """
        Aplica metadata parseada a un indicador
        Basado en cargar_ficha_tecnica.py
        
        Args:
            indicador: Instancia de Indicador
            metadata_dict: Diccionario con metadata parseada (clave: valor)
        
        Returns:
            Dict con resultado de la operación
        """
        from datetime import datetime
        
        campos_actualizados = []
        errores = []
        
        # Mapeo de claves del CSV a campos del modelo
        mapeo_campos = {
            'Codigo_Indicador': 'codigo_indicador',
            'Sigla': 'sigla',
            'Grupo_Indicador': 'grupo_indicador',
            'Nombre_Indicador': 'nombre',
            # MSD + aliases legacy (archivos antiguos siguen importando)
            'Descripcion_Indicador': 'descripcion_indicador',
            'Definiciones_Conceptos': 'descripcion_indicador',
            'Objetivo': 'objetivo',
            'Metodo_Medicion': 'metodo_medicion',
            'Formula': 'formula_ficha',
            'Variables': 'variables',
            'Unidad_Medida': 'unidad_medida',
            'Alcance_Tematico': 'alcance_tematico',
            'Desagregacion_Tematica': 'alcance_tematico',
            'Cobertura_Geografica': 'cobertura_geografica',
            'Desagregacion_Geografica': 'cobertura_geografica',
            'Nomenclaturas_Clasificaciones': 'nomenclaturas_clasificaciones',
            'Poblacion_Objetivo': 'poblacion_objetivo',
            'Periodo_Referencia': 'periodo_referencia',
            'Periodo_Base': 'periodo_base',
            'Frecuencia_Difusion': 'frecuencia_difusion',
            'Periodicidad': 'frecuencia_difusion',
            'Serie_Historica_Disponible': 'serie_historica_disponible',
            'Medios_Difusion': 'medios_difusion',
            'Fuente_Datos': 'fuente_datos',
            'Entidad_Responsable': 'entidad_responsable',
            'Responsable': 'entidad_responsable',
            'Comentarios_Adicionales': 'comentarios_adicionales',
            'Observaciones': 'comentarios_adicionales',
            'Correo_Contacto': 'correo_contacto',
            'Telefono_Contacto': 'telefono_contacto',
            'Referencias': 'referencias',
            'Nombre_Responsable_Validacion': 'nombre_responsable_validacion',
            'Cargo_Responsable_Validacion': 'cargo_responsable_validacion',
            'Correo_Responsable_Validacion': 'correo_responsable_validacion',
            'Celular_Responsable_Validacion': 'celular_responsable_validacion',
        }
        
        # Aplicar campos de texto
        for clave_csv, campo_modelo in mapeo_campos.items():
            if clave_csv in metadata_dict:
                valor = metadata_dict[clave_csv].strip()
                if valor:
                    setattr(indicador, campo_modelo, valor)
                    campos_actualizados.append(campo_modelo)
        
        # Equipo responsable: resolver por nombre en catálogo (SDMX)
        equipo_txt = metadata_dict.get('Equipo_Responsable', '').strip()
        if equipo_txt:
            from indicadores.models import EquipoOrganismo
            eq_qs = EquipoOrganismo.objects.filter(nombre__iexact=equipo_txt, activo=True)
            if indicador.suborganismo_id:
                eq_qs = eq_qs.filter(suborganismo_id=indicador.suborganismo_id)
            eq = eq_qs.first()
            if eq:
                indicador.equipo_responsable = eq
                campos_actualizados.append('equipo_responsable')

        # Aplicar fechas (MSD 1.5 — acepta alias legacy Fecha_Actualizacion)
        if 'Fecha_Publicacion_Metadatos' in metadata_dict or 'Fecha_Actualizacion' in metadata_dict:
            try:
                fecha_str = (metadata_dict.get('Fecha_Publicacion_Metadatos') or metadata_dict.get('Fecha_Actualizacion') or '').strip()
                if fecha_str:
                    indicador.fecha_publicacion_metadatos = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                    campos_actualizados.append('fecha_publicacion_metadatos')
            except ValueError as e:
                errores.append(f'Fecha de publicación de metadatos inválida: {str(e)}')
        
        # Guardar
        try:
            indicador.save()
            return {
                'exitoso': True,
                'campos_actualizados': campos_actualizados,
                'total_campos': len(campos_actualizados),
                'errores': errores
            }
        except Exception as e:
            return {
                'exitoso': False,
                'error': str(e),
                'campos_actualizados': [],
                'errores': errores
            }
    
    @staticmethod
    def aplicar_metadata_variables(conjunto_datos, variables_list: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Aplica metadata de variables a una conjunto_datos
        Basado en crear_conjunto_datos_y_variables.py
        
        Args:
            conjunto_datos: Instancia de ConjuntoDatos
            variables_list: Lista de diccionarios con metadata de variables
        
        Returns:
            Dict con resultado de la operación
        """
        from indicadores.models import VariableConjuntoDatos
        
        variables_creadas = 0
        variables_actualizadas = 0
        errores = []
        
        for var_data in variables_list:
            try:
                nombre = var_data.get('nombre_variable', var_data.get('nombre', '')).strip()
                if not nombre:
                    continue
                
                # Buscar o crear variable
                variable, created = VariableConjuntoDatos.objects.get_or_create(
                    conjunto_datos=conjunto_datos,
                    nombre=nombre,
                    defaults={
                        'tipo': var_data.get('tipo', 'texto'),
                        'descripcion': var_data.get('descripcion', ''),
                        'unidad_medida': var_data.get('unidad_medida', ''),
                        'valores_permitidos': var_data.get('valores_permitidos', ''),
                        'es_obligatoria': var_data.get('es_obligatoria', 'false').lower() == 'true'
                    }
                )
                
                if created:
                    variables_creadas += 1
                else:
                    # Actualizar campos
                    variable.tipo = var_data.get('tipo', variable.tipo)
                    variable.descripcion = var_data.get('descripcion', variable.descripcion)
                    variable.unidad_medida = var_data.get('unidad_medida', variable.unidad_medida)
                    variable.valores_permitidos = var_data.get('valores_permitidos', variable.valores_permitidos)
                    variable.save()
                    variables_actualizadas += 1
            
            except Exception as e:
                errores.append(f"Error con variable '{nombre}': {str(e)}")
        
        return {
            'exitoso': len(errores) == 0,
            'variables_creadas': variables_creadas,
            'variables_actualizadas': variables_actualizadas,
            'total_procesadas': variables_creadas + variables_actualizadas,
            'errores': errores
        }


class ValidadorDatos:
    """
    Valida archivos de datos CSV/XLSX antes de procesarlos en el wizard.
    Detecta problemas estructurales y de contenido en tiempo real.
    """

    SEVERIDAD_ERROR = 'error'
    SEVERIDAD_WARNING = 'warning'
    SEVERIDAD_INFO = 'info'

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.problemas: List[Dict[str, Any]] = []

    def validar_todo(self) -> Dict[str, Any]:
        """Ejecuta todas las validaciones y retorna resultado estructurado."""
        self.problemas = []
        self._validar_encabezados_duplicados()
        self._validar_columnas_vacias()
        self._validar_filas_vacias()
        self._validar_tipos_datos()
        self._validar_filas_duplicadas()
        self._validar_outliers()
        self._validar_desagregaciones_candidatas()

        errores = [p for p in self.problemas if p['severidad'] == self.SEVERIDAD_ERROR]
        warnings = [p for p in self.problemas if p['severidad'] == self.SEVERIDAD_WARNING]
        info = [p for p in self.problemas if p['severidad'] == self.SEVERIDAD_INFO]

        return {
            'errores': errores,
            'warnings': warnings,
            'info': info,
            'bloqueado': len(errores) > 0,
            'resumen': {
                'filas': len(self.df),
                'columnas': len(self.df.columns),
                'total_errores': len(errores),
                'total_warnings': len(warnings),
                'total_info': len(info)
            }
        }

    def _agregar(self, codigo: str, severidad: str, mensaje: str, detalle: Any = None):
        self.problemas.append({
            'codigo': codigo,
            'severidad': severidad,
            'mensaje': mensaje,
            'detalle': detalle
        })

    def _validar_encabezados_duplicados(self):
        duplicados = self.df.columns[self.df.columns.duplicated()].tolist()
        if duplicados:
            self._agregar('V1', self.SEVERIDAD_ERROR,
                          f'Columnas con nombre duplicado: {", ".join(duplicados)}',
                          duplicados)

    def _validar_columnas_vacias(self):
        vacias = [c for c in self.df.columns if pd.isna(c) or str(c).strip() == '']
        if vacias:
            self._agregar('V2', self.SEVERIDAD_WARNING,
                          f'Columnas sin nombre detectadas: {len(vacias)}',
                          vacias)

    def _validar_filas_vacias(self):
        filas_vacias = self.df.isna().all(axis=1).sum()
        if filas_vacias > 0:
            self._agregar('V3', self.SEVERIDAD_WARNING,
                          f'{filas_vacias} fila(s) completamente vacía(s)',
                          {'filas_vacias': int(filas_vacias)})

    def _validar_tipos_datos(self):
        for col in self.df.columns:
            if self.df[col].dtype == 'object':
                no_numericos = 0
                for val in self.df[col].dropna():
                    try:
                        float(val)
                    except (ValueError, TypeError):
                        no_numericos += 1
                if no_numericos == 0 and len(self.df[col].dropna()) > 0:
                    # Todos los valores son numéricos pero la columna es object
                    self._agregar('V4', self.SEVERIDAD_INFO,
                                  f'Columna "{col}" parece numérica pero está como texto',
                                  {'columna': col, 'tipo_detectado': 'numérica'})

    def _validar_filas_duplicadas(self):
        duplicadas = self.df.duplicated().sum()
        if duplicadas > 0:
            self._agregar('V7', self.SEVERIDAD_WARNING,
                          f'{duplicadas} fila(s) duplicada(s)',
                          {'filas_duplicadas': int(duplicadas)})

    def _validar_outliers(self):
        for col in self.df.select_dtypes(include=[np.number]).columns:
            valores = self.df[col].dropna()
            if len(valores) < 4:
                continue
            q1 = valores.quantile(0.25)
            q3 = valores.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            limite_inferior = q1 - 1.5 * iqr
            limite_superior = q3 + 1.5 * iqr
            outliers = valores[(valores < limite_inferior) | (valores > limite_superior)]
            if len(outliers) > 0:
                self._agregar('V6', self.SEVERIDAD_WARNING,
                              f'Columna "{col}": {len(outliers)} valor(es) atípico(s) (IQR)',
                              {
                                  'columna': col,
                                  'outliers_count': int(len(outliers)),
                                  'min': float(valores.min()),
                                  'max': float(valores.max()),
                                  'outliers': [float(v) for v in outliers.head(5)]
                              })

    def _validar_desagregaciones_candidatas(self):
        for col in self.df.select_dtypes(include=['object']).columns:
            unicos = self.df[col].dropna().unique()
            if 2 <= len(unicos) <= 50:
                self._agregar('V8', self.SEVERIDAD_INFO,
                              f'Columna "{col}" podría ser una desagregación ({len(unicos)} valores únicos)',
                              {'columna': col, 'valores_unicos': int(len(unicos)),
                               'muestra': list(unicos[:5])})


def estimar_series_grafico(dominios_geo_ids, dominios_tem_ids):
    """
    Calcula cuántas GraficoSerie se crearían con los dominios seleccionados.
    Réplica exacta de la lógica de _crear_series_grafico().

    Args:
        dominios_geo_ids: lista de IDs de DominioDesagregacion tipo 'geografica'
        dominios_tem_ids: lista de IDs de DominioDesagregacion tipo 'tematica'

    Returns:
        dict con total_series, geo_count, tem_count, desglose, alerta
    """
    from indicadores.models import Desagregacion, DominioDesagregacion

    count_geo = Desagregacion.objects.filter(
        dominio__id__in=dominios_geo_ids
    ).distinct().count()

    count_tem = Desagregacion.objects.filter(
        dominio__id__in=dominios_tem_ids
    ).distinct().count()

    if count_geo > 0 and count_tem > 0:
        total = count_geo * count_tem
    elif count_geo > 0:
        total = count_geo
    elif count_tem > 0:
        total = count_tem
    else:
        total = 1

    # Alerta según umbrales
    if total <= 50:
        alerta = 'verde'
    elif total <= 200:
        alerta = 'amarillo'
    elif total <= 1000:
        alerta = 'naranja'
    else:
        alerta = 'rojo'

    # Desglose por dominio: un dominio es "hoja" si ningún otro dominio
    # seleccionado desciende de él (jerarquía dominio_padre)
    dominios_sel = list(DominioDesagregacion.objects.filter(
        id__in=list(dominios_geo_ids) + list(dominios_tem_ids)
    ))
    padres_map = dict(
        DominioDesagregacion.objects.values_list('id', 'dominio_padre_id')
    )
    sel_ids = {d.id for d in dominios_sel}
    ancestros_sel = set()
    for d in dominios_sel:
        p = padres_map.get(d.id)
        while p:
            if p in sel_ids:
                ancestros_sel.add(p)
            p = padres_map.get(p)

    desglose = []
    for d in dominios_sel:
        desglose.append({
            'id': d.id,
            'nombre': d.nombre,
            'tipo': d.tipo,
            'valores': d.desagregaciones.count(),
            'hoja': d.id not in ancestros_sel,
        })

    return {
        'total_series': total,
        'geo_count': count_geo,
        'tem_count': count_tem,
        'desglose': desglose,
        'alerta': alerta
    }


def crear_registro_cambio(indicador, usuario, tipo_evento,
                          diff_json=None, snapshot_metadatos=None,
                          filas_afectadas=0, archivo_relacionado=None):
    """
    Crea un RegistroCambio resolviendo automáticamente los organismos
    a partir del usuario (PerfilRecolector) y del indicador.

    Args:
        indicador: Instancia de Indicador
        usuario: Instancia de User (puede ser None)
        tipo_evento: str, uno de RegistroCambio.TIPO_EVENTO
        diff_json: dict opcional con cambios detectados
        snapshot_metadatos: dict opcional con estado completo del indicador
        filas_afectadas: int, número de filas/datos afectados
        archivo_relacionado: str, nombre del archivo cargado

    Returns:
        RegistroCambio creado
    """
    from indicadores.models import RegistroCambio, Organismo

    # Resolver organismos
    organismo_origen = None
    if usuario:
        perfil = getattr(usuario, 'perfil_recolector', None)
        if perfil and perfil.organismo:
            organismo_origen = perfil.organismo

    organismo_responsable = getattr(indicador, 'organismo_responsable', None)

    return RegistroCambio.objects.create(
        indicador=indicador,
        usuario=usuario,
        organismo_origen=organismo_origen,
        organismo_responsable=organismo_responsable,
        tipo_evento=tipo_evento,
        diff_json=diff_json or {},
        snapshot_metadatos=snapshot_metadatos or {},
        filas_afectadas=filas_afectadas,
        archivo_relacionado=archivo_relacionado
    )
