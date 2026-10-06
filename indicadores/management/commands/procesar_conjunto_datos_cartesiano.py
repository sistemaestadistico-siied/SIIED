from django.core.management.base import BaseCommand
from indicadores.models import ConjuntoDatos, Indicador, ReglaExtraccion, Desagregacion, Dato
import csv
import itertools
from datetime import datetime
from django.db import transaction
import ast
import re
import unicodedata


class Command(BaseCommand):
    help = 'Procesa conjunto_datos generando el producto cartesiano de desagregaciones temáticas'
    
    def add_arguments(self, parser):
        parser.add_argument('--conjunto_datos-id', type=int, help='ID del conjunto_datos a procesar')
        parser.add_argument('--indicador-id', type=int, help='ID del indicador a procesar')
        parser.add_argument('--regla-id', type=int, help='ID de la regla de extracción a usar')
        parser.add_argument('--eliminar-datos-previos', action='store_true', 
                          help='Eliminar datos previos del indicador antes de procesar')
        parser.add_argument('--crear-faltantes', action='store_true',
                          help='Crear automáticamente las desagregaciones que no existan en la BD')
        parser.add_argument('--limitar-filas', type=int, 
                          help='Limitar el número de filas a procesar (para pruebas)')
    
    def handle(self, *args, **options):
        conjunto_datos_id = options.get('conjunto_datos_id')
        indicador_id = options.get('indicador_id')
        regla_id = options.get('regla_id')
        eliminar_datos_previos = options.get('eliminar_datos_previos')
        limitar_filas = options.get('limitar_filas')
        self.crear_faltantes = options.get('crear_faltantes', False)
        # Guardar verbosity para controlar el nivel de logs
        self.verbosity = int(options.get('verbosity', 1) or 1)
        
        if not conjunto_datos_id and not indicador_id and not regla_id:
            self.stdout.write(
                self.style.ERROR('Debe especificar --conjunto_datos-id, --indicador-id o --regla-id')
            )
            return
        
        # Obtener el conjunto_datos, el indicador y la regla
        try:
            if regla_id:
                regla = ReglaExtraccion.objects.get(id=regla_id)
                indicador = regla.indicador
                conjunto_datos = indicador.conjunto_datos
                if not conjunto_datos:
                    self.stdout.write(
                        self.style.ERROR('No se encontró conjunto_datos para el indicador especificado')
                    )
                    return
            elif conjunto_datos_id:
                conjunto_datos = ConjuntoDatos.objects.get(id=conjunto_datos_id)
                if indicador_id:
                    # Si se especifica ambos, usar el indicador especificado
                    indicador = Indicador.objects.get(id=indicador_id)
                    if indicador.conjunto_datos != conjunto_datos:
                        self.stdout.write(
                            self.style.ERROR('El indicador especificado no está asociado al conjunto_datos')
                        )
                        return
                else:
                    # Si solo se especifica conjunto_datos, usar el primer indicador asociado
                    indicador = Indicador.objects.filter(conjunto_datos=conjunto_datos).first()
                    if not indicador:
                        self.stdout.write(
                            self.style.ERROR('No se encontró indicador asociado al conjunto_datos especificado')
                        )
                        return
            else:  # Solo indicador_id
                indicador = Indicador.objects.get(id=indicador_id)
                conjunto_datos = indicador.conjunto_datos
                if not conjunto_datos:
                    self.stdout.write(
                        self.style.ERROR('No se encontró conjunto_datos para el indicador especificado')
                    )
                    return
            
            # Obtener la regla de extracción
            try:
                if not regla_id:
                    regla = ReglaExtraccion.objects.get(indicador=indicador)
            except ReglaExtraccion.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR('No se encontró regla de extracción para el indicador')
                )
                return
        except (ConjuntoDatos.DoesNotExist, Indicador.DoesNotExist, ReglaExtraccion.DoesNotExist):
            self.stdout.write(
                self.style.ERROR('No se encontró el conjunto_datos, indicador o regla especificado')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'Procesando conjunto_datos para indicador: {indicador.nombre}')
        )
        
        # Eliminar datos previos si se solicita
        if eliminar_datos_previos:
            self.stdout.write('Eliminando datos previos...')
            Dato.objects.filter(indicador=indicador).delete()
            self.stdout.write(self.style.SUCCESS('Datos previos eliminados'))
        
        # Procesar el CSV
        self.procesar_csv(conjunto_datos, indicador, regla, limitar_filas)
    
    def procesar_csv(self, ConjuntoDatos, indicador, regla, limitar_filas=None):
        """Procesa el archivo CSV y genera datos con producto cartesiano de desagregaciones"""
        if not conjunto_datos.archivo_csv:
            self.stdout.write(
                self.style.ERROR('No se ha definido un archivo CSV para este conjunto_datos')
            )
            return
        
        # Abrir el archivo CSV
        archivo_csv = conjunto_datos.archivo_csv.path
        
        # Detectar encoding y delimitador
        encoding, delimiter = self.detectar_encoding_y_delimitador(archivo_csv)
        
        # Leer el archivo CSV
        with open(archivo_csv, 'r', encoding=encoding) as csvfile:
            reader = csv.reader(csvfile, delimiter=delimiter)
            headers = next(reader)
            
            # Procesar filas
            filas_procesadas = 0
            datos_creados = 0
            # Intervalo de progreso según verbosity (más frecuente con mayor verbosity)
            progress_interval = 100 if getattr(self, 'verbosity', 1) >= 2 else 1000
            
            for row in reader:
                if limitar_filas and filas_procesadas >= limitar_filas:
                    break
                
                # Procesar cada fila
                creados = self.procesar_fila(headers, row, indicador, regla)
                datos_creados += creados
                filas_procesadas += 1
                
                # Mostrar progreso cada N filas (controlado por verbosity)
                if filas_procesadas % progress_interval == 0:
                    self.stdout.write(f'Procesadas {filas_procesadas} filas, {datos_creados} datos creados')
                
                # Log por fila: para todas las filas cuando verbosity >= 2
                if getattr(self, 'verbosity', 1) >= 2:
                    self.stdout.write(f'  Fila {filas_procesadas}: {creados} datos creados')
            
            self.stdout.write(
                self.style.SUCCESS(f'Procesamiento completado: {filas_procesadas} filas, {datos_creados} datos creados')
            )
    
    def detectar_encoding_y_delimitador(self, archivo_csv):
        """Detecta el encoding y delimitador del archivo CSV"""
        import csv
        
        # Intentar con diferentes encodings comunes
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(archivo_csv, 'r', encoding=encoding) as file:
                    # Leer una muestra para detectar el delimitador
                    sample = file.read(1024)
                    file.seek(0)
                    
                    # Usar el sniffer de csv para detectar el delimitador
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(sample)
                    delimiter = dialect.delimiter
                    
                    # Si llegamos aquí, el encoding funciona
                    self.stdout.write(f"Encoding detectado: {encoding}, Delimitador: '{delimiter}'")
                    return encoding, delimiter
            except (UnicodeDecodeError, csv.Error):
                continue
        
        # Si no se pudo detectar, usar valores por defecto
        self.stdout.write(
            self.style.WARNING("No se pudo detectar encoding/delimitador. Usando utf-8 y ','")
        )
        return 'utf-8', ','
    
    def procesar_fila(self, headers, row, indicador, regla):
        """Procesa una fila del CSV y crea datos con producto cartesiano de desagregaciones"""
        # Crear un diccionario para acceder fácilmente a los valores por encabezado
        fila_dict = dict(zip(headers, row))
        
        # Aplicar filtros definidos en la regla (si existen). Si no cumple, omitir fila.
        if getattr(regla, 'filtros', None):
            for clave, esperado in (regla.filtros or {}).items():
                # Buscar el header correspondiente (case-insensitive, permite coincidencia parcial)
                header_match = next((h for h in fila_dict.keys() if h.lower() == str(clave).lower()), None)
                if not header_match:
                    header_match = next((h for h in fila_dict.keys() if str(clave).lower() in h.lower()), None)
                if not header_match:
                    return 0
                valor_fila = fila_dict.get(header_match)
                if isinstance(esperado, (list, tuple, set)):
                    if valor_fila not in esperado:
                        return 0
                else:
                    if str(valor_fila).strip() != str(esperado).strip():
                        return 0
        
        # Obtener el valor de la fecha/año
        columna_fecha = self.resolver_columna_fecha(headers, regla)
        if not columna_fecha or columna_fecha not in fila_dict:
            self.stdout.write(self.style.WARNING('No se encontró columna de fecha/año en la fila'))
            return 0
        
        try:
            # Convertir el valor de fecha a objeto datetime o entero
            valor_fecha = fila_dict[columna_fecha]
            if valor_fecha.isdigit():
                fecha_dato = datetime(int(valor_fecha), 1, 1)  # Asumir 1 de enero para años
            else:
                # Intentar parsear como fecha
                try:
                    fecha_dato = datetime.strptime(valor_fecha, '%Y-%m-%d')
                except ValueError:
                    try:
                        fecha_dato = datetime.strptime(valor_fecha, '%d/%m/%Y')
                    except ValueError:
                        self.stdout.write(self.style.WARNING(f'No se pudo parsear la fecha: {valor_fecha}'))
                        return 0
        except (ValueError, KeyError):
            self.stdout.write(self.style.WARNING(f'Error al procesar la fecha: {valor_fecha}'))
            return 0
        
        # Obtener las desagregaciones geográficas de la fila
        desagregaciones_geograficas = self.obtener_desagregaciones_geograficas(fila_dict, indicador)
        
        # Obtener las desagregaciones temáticas posibles de la fila
        desagregaciones_tematicas_posibles = self.obtener_desagregaciones_tematicas_posibles(fila_dict, indicador, headers)
        
        # Generar el producto cartesiano de las desagregaciones temáticas
        combinaciones_tematicas = self.generar_producto_cartesiano(desagregaciones_tematicas_posibles)
        
        # Logs detallados de combinaciones pueden activarse por verbosity si se requiere
        # (evitar referencias a columnas específicas como 'AÑO')
        
        # Crear datos para cada combinación
        datos_creados = 0
        
        # Si no hay desagregaciones geográficas, crear al menos un dato
        if not desagregaciones_geograficas:
            desagregaciones_geograficas = [None]
        
        # Si no hay combinaciones temáticas, crear al menos un dato
        if not combinaciones_tematicas:
            combinaciones_tematicas = [()]
        
        # Construir mapeo de columnas a desagregaciones para esta fila
        mapeo_columnas = self.construir_mapeo_columnas(headers, indicador, regla)

        for desag_geo in desagregaciones_geograficas:
            for combinacion_tematica in combinaciones_tematicas:
                # Para combinaciones que incluyan 'Total' en algún dominio temático,
                # verificar la estrategia de agregación configurada en el dominio
                if any(self.es_desag_total(dt) for dt in combinacion_tematica):
                    # Identificar el dominio que tiene el Total
                    dominio_con_total = None
                    for dt in combinacion_tematica:
                        if self.es_desag_total(dt):
                            dominio_con_total = dt.dominio
                            break
                    
                    # Obtener estrategia de agregación del dominio
                    tipo_agregacion = getattr(dominio_con_total, 'tipo_agregacion_total', 'suma')
                    
                    if tipo_agregacion == 'ninguno':
                        # NO calcular sumando: buscar 'Total' directamente en CSV como una desagregación más
                        valor = self.obtener_valor_para_combinacion(fila_dict, mapeo_columnas, combinacion_tematica, regla)
                        if getattr(self, 'verbosity', 1) >= 2 and valor is not None:
                            self.stdout.write(
                                f"  [TOTAL-DIRECTO] Dominio '{dominio_con_total.nombre}': "
                                f"Extraído directamente del CSV = {valor}"
                            )
                    else:
                        # Estrategia 'suma' (default): calcular sumando desagregaciones
                        valor = self.calcular_total_desde_columnas(fila_dict, mapeo_columnas, combinacion_tematica, regla)
                        if getattr(self, 'verbosity', 1) >= 2 and valor is not None:
                            self.stdout.write(
                                f"  [TOTAL-SUMA] Dominio '{dominio_con_total.nombre}': "
                                f"Sumado de desagregaciones = {valor}"
                            )
                    
                    # Si existe una fórmula y usa 'valor_celda', aplícala al total (ya sea sumado o extraído)
                    if valor is not None and regla.formula and regla.formula.strip() not in ("", "valor_celda"):
                        try:
                            res = self._eval_formula_segura(regla.formula.strip(), fila_dict, extra_vars={"valor_celda": valor})
                            if res is not None:
                                valor = float(res)
                                if getattr(self, 'verbosity', 1) >= 2:
                                    self.stdout.write(
                                        f"  [FÓRMULA] Aplicada sobre Total: resultado = {valor}"
                                    )
                        except Exception:
                            pass
                else:
                    # Obtener valor específico para la combinación (seleccionando la columna correcta)
                    valor = self.obtener_valor_para_combinacion(fila_dict, mapeo_columnas, combinacion_tematica, regla)
                
                if valor is not None:
                    # Crear el objeto Dato
                    dato = Dato(
                        indicador=indicador,
                        valor_dato=valor,
                        fecha_dato=fecha_dato
                    )
                    dato.save()
                    
                    # Asignar desagregaciones geográficas si existen
                    if desag_geo:
                        dato.desagregaciones_geograficas.add(desag_geo)
                    
                    # Asignar desagregaciones temáticas de la combinación
                    for desag_tema in combinacion_tematica:
                        dato.desagregaciones_tematicas.add(desag_tema)
                    
                    # Log detallado por dato cuando verbosity >= 3, incluyendo año y desagregaciones
                    if getattr(self, 'verbosity', 1) >= 3:
                        try:
                            geo_desc = f"{desag_geo.dominio.nombre}:{desag_geo.nombre}" if desag_geo else "(sin geo)"
                        except Exception:
                            geo_desc = "(sin geo)"
                        temas_desc = ", ".join([f"{d.dominio.nombre}:{d.nombre}" for d in combinacion_tematica]) if combinacion_tematica else "(sin temáticas)"
                        try:
                            ano = fecha_dato.year
                        except Exception:
                            ano = str(fecha_dato)
                        self.stdout.write(f"    [dato] año={ano} geo={geo_desc} temas=[{temas_desc}] valor={valor}")

                    datos_creados += 1
        
        return datos_creados
    
    def inferir_columna_fecha(self, headers):
        """Infiere la columna que contiene la fecha o año"""
        # Palabras clave para identificar columnas de fecha/año
        palabras_clave_fecha = ['fecha', 'año', 'anio', 'year', 'date']
        
        for header in headers:
            header_lower = header.lower()
            # Verificar coincidencia exacta o parcial con las palabras clave
            for palabra in palabras_clave_fecha:
                if palabra in header_lower:
                    return header
        
        # Si no se encuentra, devolver None
        return None
    
    def resolver_columna_fecha(self, headers, regla):
        """Resuelve la columna de fecha prefiriendo la definida en la regla si existe."""
        try:
            if regla and getattr(regla, 'columna_fecha', None):
                objetivo = regla.columna_fecha.strip().lower()
                # Coincidencia exacta (case-insensitive)
                for h in headers:
                    if h.lower() == objetivo:
                        return h
                # Coincidencia parcial
                for h in headers:
                    if objetivo in h.lower():
                        return h
        except Exception:
            pass
        return self.inferir_columna_fecha(headers)
    
    def obtener_desagregaciones_geograficas(self, fila_dict, indicador):
        """Obtiene las desagregaciones geográficas de una fila"""
        desagregaciones = []
        
        # Para cada dominio geográfico del indicador
        for dominio in indicador.dominios_desagregacion_geografica.all():
            # Buscar columnas que contengan el nombre del dominio
            for columna, valor in fila_dict.items():
                if not valor or str(valor).strip() == '':
                    continue
                if dominio.nombre.lower() in columna.lower():
                    # Buscar una desagregación que coincida con el valor
                    try:
                        desag = Desagregacion.objects.get(
                            dominio=dominio,
                            nombre__iexact=valor.strip()
                        )
                        desagregaciones.append(desag)
                    except Desagregacion.DoesNotExist:
                        if getattr(self, 'crear_faltantes', False):
                            desag, created = Desagregacion.objects.get_or_create(
                                dominio=dominio,
                                nombre=valor.strip(),
                                defaults={
                                    'codigo': str(valor).strip()[:100],
                                    'descripcion': f'Creada automáticamente en proceso cartesiano'
                                }
                            )
                            desagregaciones.append(desag)
                            if getattr(self, 'verbosity', 1) >= 2:
                                self.stdout.write(self.style.SUCCESS(f'Creada desagregación geográfica "{valor}" para dominio "{dominio.nombre}"'))
                        else:
                            # Si no se encuentra, crear una entrada en el log
                            self.stdout.write(
                                self.style.WARNING(f'No se encontró desagregación geográfica "{valor}" para dominio "{dominio.nombre}"')
                            )
        
        return desagregaciones
    
    def detectar_ubicacion_dominio_tematico(self, dominio, headers, fila_dict):
        """
        Detecta si un dominio temático está en COLUMNAS (como geográfico) o en HEADERS.
        
        Estrategia:
        1. Buscar columna con nombre del dominio
        2. Verificar que los valores coincidan con desagregaciones del dominio
        3. Si coincidencia > 50%, es COLUMNA
        4. Si no, buscar en headers (estrategia actual)
        
        Returns:
            dict: {
                'tipo': 'columna' | 'header',
                'columna': str | None,
                'confianza': float
            }
        """
        dominio_nombre_lower = dominio.nombre.lower()
        
        # OPCIÓN 1: Buscar columna con nombre del dominio
        for columna in headers:
            columna_lower = columna.lower()
            # ¿El nombre del dominio está en la columna?
            if dominio_nombre_lower in columna_lower or columna_lower in dominio_nombre_lower:
                # Verificar que el VALOR de la fila coincida con alguna desagregación
                valor_columna = str(fila_dict.get(columna, '')).strip()
                if not valor_columna:
                    continue
                
                # Buscar coincidencia con desagregaciones del dominio
                desagregaciones_bd = dominio.desagregaciones.all()
                for desag in desagregaciones_bd:
                    if desag.nombre.lower() == valor_columna.lower():
                        # ¡Coincidencia! Esta columna contiene desagregaciones
                        if getattr(self, 'verbosity', 1) >= 2:
                            self.stdout.write(
                                f"[DETECCIÓN] Dominio '{dominio.nombre}' detectado en COLUMNA '{columna}' "
                                f"(valor: '{valor_columna}' → desag: '{desag.nombre}')"
                            )
                        return {
                            'tipo': 'columna',
                            'columna': columna,
                            'confianza': 1.0
                        }
        
        # OPCIÓN 2: Buscar en headers (comportamiento actual)
        desagregaciones_bd = list(dominio.desagregaciones.all())
        headers_con_desag = 0
        
        for header in headers:
            header_lower = header.lower()
            for desag in desagregaciones_bd:
                if desag.nombre and desag.nombre.lower() in header_lower:
                    headers_con_desag += 1
                    break
        
        if headers_con_desag > 0:
            if getattr(self, 'verbosity', 1) >= 2:
                self.stdout.write(
                    f"[DETECCIÓN] Dominio '{dominio.nombre}' detectado en HEADERS "
                    f"({headers_con_desag} headers coincidentes)"
                )
            return {
                'tipo': 'header',
                'columna': None,
                'confianza': headers_con_desag / len(headers) if headers else 0.0
            }
        
        # Por defecto: header (comportamiento actual)
        if getattr(self, 'verbosity', 1) >= 2:
            self.stdout.write(
                self.style.WARNING(
                    f"[DETECCIÓN] Dominio '{dominio.nombre}' no detectado claramente, "
                    f"asumiendo HEADERS por defecto"
                )
            )
        return {
            'tipo': 'header',
            'columna': None,
            'confianza': 0.0
        }
    
    def obtener_desagregaciones_tematicas_posibles(self, fila_dict, indicador, headers):
        """Obtiene las desagregaciones temáticas posibles por dominio para una fila.
        
        MODIFICADO: Ahora detecta si cada dominio está en COLUMNAS o HEADERS.
        - Si está en columna: retorna lista de 1 elemento (la desagregación del valor)
        - Si está en headers: retorna lista de N elementos (todas las encontradas)
        
        Esto permite soportar ambos formatos CSV:
        - CSV Ancho (wide): desagregaciones en headers → producto cartesiano
        - CSV Largo (long): desagregaciones en columnas → lectura directa
        """
        desagregaciones_por_dominio = {}
        
        # Para cada dominio temático del indicador
        for dominio in indicador.dominios_desagregacion_tematica.all():
            # NUEVO: Detectar ubicación del dominio (columna vs header)
            ubicacion = self.detectar_ubicacion_dominio_tematico(dominio, headers, fila_dict)
            
            if ubicacion['tipo'] == 'columna':
                # CASO NUEVO: Dominio en COLUMNA (como geográfico)
                # Leer el VALOR de esa columna y buscar la desagregación
                columna = ubicacion['columna']
                valor_columna = str(fila_dict.get(columna, '')).strip()
                
                if valor_columna:
                    try:
                        # Buscar desagregación que coincida con el valor
                        desag = Desagregacion.objects.get(
                            dominio=dominio,
                            nombre__iexact=valor_columna
                        )
                        desagregaciones_por_dominio[dominio] = [desag]  # Lista de 1 elemento
                        
                        if getattr(self, 'verbosity', 1) >= 3:
                            self.stdout.write(
                                f"  [TEMÁTICA-COLUMNA] Dominio '{dominio.nombre}': "
                                f"columna='{columna}', valor='{valor_columna}' → desag='{desag.nombre}'"
                            )
                    except Desagregacion.DoesNotExist:
                        if getattr(self, 'crear_faltantes', False):
                            desag, created = Desagregacion.objects.get_or_create(
                                dominio=dominio,
                                nombre=valor_columna,
                                defaults={
                                    'codigo': valor_columna[:100],
                                    'descripcion': f'Creada automáticamente en proceso cartesiano'
                                }
                            )
                            desagregaciones_por_dominio[dominio] = [desag]
                            if getattr(self, 'verbosity', 1) >= 2:
                                self.stdout.write(self.style.SUCCESS(f"Creada desagregación temática '{valor_columna}' para dominio '{dominio.nombre}'"))
                        else:
                            if getattr(self, 'verbosity', 1) >= 1:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'No se encontró desagregación "{valor_columna}" '
                                        f'para dominio "{dominio.nombre}" (columna: {columna})'
                                    )
                                )
                continue  # Pasar al siguiente dominio
            
            # CASO EXISTENTE: Dominio en HEADERS (búsqueda en encabezados)
            desagregaciones_posibles = []
            
            # Para cada desagregación del dominio
            desags_dominio = list(dominio.desagregaciones.all())
            hay_rangos = any(getattr(d, 'es_rango', False) and getattr(d, 'valores_rango', None) for d in desags_dominio)
            if hay_rangos:
                # Cuando el dominio define rangos, incluir todos los rangos;
                # el valor se calculará sumando columnas que caen dentro del rango.
                for d in desags_dominio:
                    if getattr(d, 'es_rango', False) and getattr(d, 'valores_rango', None):
                        desagregaciones_posibles.append(d)
                # Además, incluir desagregaciones no de rango que aparezcan en headers/valores (p.ej., '85 y más')
                for desag in desags_dominio:
                    if not (getattr(desag, 'es_rango', False) and getattr(desag, 'valores_rango', None)):
                        nombre_low = (desag.nombre or '').lower()
                        if not nombre_low:
                            continue
                        for columna, valor in fila_dict.items():
                            if nombre_low in columna.lower() or nombre_low in str(valor).lower():
                                desagregaciones_posibles.append(desag)
                                break
            else:
                # Para desagregaciones no de rango, buscar coincidencia exacta o parcial
                for desag in desags_dominio:
                    for columna, valor in fila_dict.items():
                        nombre_low = (desag.nombre or '').lower()
                        if nombre_low and (
                            nombre_low in columna.lower() or
                            nombre_low in str(valor).lower()
                        ):
                            desagregaciones_posibles.append(desag)
                            break
            
            # Incluir 'Total' del dominio para permitir su cálculo por suma aunque no aparezca explícitamente
            try:
                total_dom = next(d for d in dominio.desagregaciones.all() if (d.nombre or '').strip().lower() == 'total')
                if total_dom not in desagregaciones_posibles:
                    desagregaciones_posibles.append(total_dom)
            except StopIteration:
                pass

            if desagregaciones_posibles:
                desagregaciones_por_dominio[dominio] = desagregaciones_posibles
                
                if getattr(self, 'verbosity', 1) >= 3:
                    self.stdout.write(
                        f"  [TEMÁTICA-HEADER] Dominio '{dominio.nombre}': "
                        f"{len(desagregaciones_posibles)} desagregaciones detectadas en headers"
                    )
        
        return desagregaciones_por_dominio

    def generar_producto_cartesiano(self, desagregaciones_por_dominio):
        """Genera el producto cartesiano de las desagregaciones temáticas"""
        if not desagregaciones_por_dominio:
            return []
        listas_desagregaciones = list(desagregaciones_por_dominio.values())
        combinaciones = list(itertools.product(*listas_desagregaciones))
        return combinaciones

    def calcular_valor(self, fila_dict, regla, columna=None):
        """Calcula el valor del dato usando la fórmula de la regla"""
        try:
            if regla.formula and regla.formula.strip() != '':
                # Si hay una fórmula definida, evaluarla
                if regla.formula.strip() == 'valor_celda' and columna:
                    # Caso especial para 'valor_celda' - usar el valor de la columna especificada
                    if columna in fila_dict:
                        valor = fila_dict[columna]
                        parsed = self._parsear_numero(valor)
                        if parsed is not None:
                            return float(parsed)
                else:
                    # Evaluación segura de fórmulas con soporte de:
                    # - Referencias directas a variables sanitizadas de headers (p.ej., Hombres_0_4)
                    # - Función col("Nombre de Columna Exacto") para headers con espacios/símbolos
                    formula = regla.formula.strip()
                    extra = None
                    if columna and columna in fila_dict:
                        v = self._parsear_numero(fila_dict[columna])
                        if v is not None:
                            extra = {"valor_celda": v}
                    resultado = self._eval_formula_segura(formula, fila_dict, extra_vars=extra)
                    if resultado is not None:
                        return float(resultado)
            elif getattr(regla, 'columnas_fuente', None):
                # Si no hay fórmula pero hay columnas fuente, usar la primera
                primera_columna = regla.columnas_fuente[0]
                if primera_columna in fila_dict:
                    parsed = self._parsear_numero(fila_dict[primera_columna])
                    if parsed is not None:
                        return float(parsed)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Error al calcular valor: {str(e)}'))
            return None
        return None

    def es_desag_total(self, desag):
        """Devuelve True si la desagregación representa un 'Total' (case-insensitive)."""
        try:
            return desag.nombre and desag.nombre.strip().lower() == 'total'
        except Exception:
            return False

    def construir_mapeo_columnas(self, headers, indicador, regla):
        """Construye un mapeo: header -> {dominio: desag} para desagregaciones temáticas detectables por nombre.
        Prioriza las columnas definidas en la regla si existen.
        """
        columnas_candidatas = []
        if getattr(regla, 'columnas_fuente', None):
            columnas_candidatas = [c for c in regla.columnas_fuente if c in headers]
        else:
            columnas_candidatas = list(headers)

        mapeo = {}
        dominios = list(indicador.dominios_desagregacion_tematica.all())
        for header in columnas_candidatas:
            mapeo_dom = {}
            header_low = header.lower()
            # Extraer número (p.ej., edad) del header si existe
            numero_en_header = None
            try:
                import re
                nums = re.findall(r"\d+", header)
                if nums:
                    numero_en_header = int(nums[-1])
            except Exception:
                numero_en_header = None
            for dominio in dominios:
                mejor_match = None
                mejor_len = -1
                desags_dominio = list(dominio.desagregaciones.all())
                # Primero, si el dominio maneja rangos y hay número en el header, asignar por pertenencia al rango
                asignado_por_rango = False
                for desag in desags_dominio:
                    if getattr(desag, 'es_rango', False) and getattr(desag, 'valores_rango', None) and numero_en_header is not None:
                        try:
                            valores = [int(v) for v in desag.valores_rango]
                            if numero_en_header in valores:
                                mejor_match = desag
                                asignado_por_rango = True
                                break
                        except Exception:
                            continue
                if not asignado_por_rango:
                    for desag in desags_dominio:
                        # Ignorar 'Total' al mapear columnas específicas
                        if self.es_desag_total(desag):
                            continue
                        nombre_low = (desag.nombre or '').lower()
                        if nombre_low and nombre_low in header_low:
                            if len(nombre_low) > mejor_len:
                                mejor_match = desag
                                mejor_len = len(nombre_low)
                if mejor_match:
                    mapeo_dom[dominio] = mejor_match
            if mapeo_dom:
                mapeo[header] = mapeo_dom
                if getattr(self, 'verbosity', 1) >= 3:
                    detalles = ", ".join([f"{d.nombre}:{mapeo_dom[d].nombre}" for d in mapeo_dom])
                    self.stdout.write(f"[mapeo] {header} -> {detalles}")
        return mapeo

    def calcular_total_desde_columnas(self, fila_dict, mapeo_columnas, combinacion_tematica, regla):
        """Calcula el valor para una combinación que incluye 'Total' SUMANDO las columnas
        de las otras desagregaciones del mismo dominio, respetando las selecciones de los
        demás dominios de la combinación.
        
        NOTA: Solo suma. Si necesitas promedios, tasas ponderadas u otros cálculos complejos,
        usa la fórmula de la regla de extracción que operará sobre las sumas de cada variable."""
        # Construir selección por dominio a partir de la combinación
        seleccion_por_dominio = {}
        for desag in combinacion_tematica:
            seleccion_por_dominio[desag.dominio] = desag

        suma = 0.0
        usados = 0
        for header, mapping in mapeo_columnas.items():
            coincide = True
            for dominio, desag_sel in seleccion_por_dominio.items():
                if self.es_desag_total(desag_sel):
                    # Si es 'Total', solo exigir que exista alguna desag para este dominio en el header
                    if dominio not in mapping or mapping[dominio] is None:
                        coincide = False
                        break
                else:
                    # Debe coincidir exactamente con la desagregación seleccionada
                    if mapping.get(dominio) != desag_sel:
                        coincide = False
                        break
            if coincide:
                valor = self._parsear_numero(fila_dict.get(header))
                if valor is not None:
                    suma += valor
                    usados += 1
        return suma if usados > 0 else None

    def obtener_valor_para_combinacion(self, fila_dict, mapeo_columnas, combinacion_tematica, regla):
        """Obtiene el valor de la fila para una combinación.
        
        MODIFICADO: Detecta automáticamente si es CSV tipo columnas o headers.
        
        Estrategia:
        1. Intentar buscar headers que coincidan (CSV tipo headers/ancho)
        2. Si no hay coincidencias, detectar columna de valor (CSV tipo columnas/largo)
        3. Aplicar fórmula sobre el valor encontrado
        
        CSV Tipo 1 (headers): Desagregaciones en encabezados
          Año,Comuna,H_0_4,M_0_4,H_5_9,M_5_9
          2024,Cali,100,150,120,180
          
        CSV Tipo 2 (columnas): Desagregaciones en columnas
          Año,Comuna,Sexo,Edad,Valor
          2024,Cali,H,0-4,100
          2024,Cali,M,0-4,150
        """
        # Construir selección por dominio a partir de la combinación
        seleccion_por_dominio = {desag.dominio: desag for desag in combinacion_tematica}

        # INTENTO 1: Buscar headers que coincidan (CSV tipo headers)
        headers_match = []
        for header, mapping in mapeo_columnas.items():
            ok = True
            for dominio, desag_sel in seleccion_por_dominio.items():
                if mapping.get(dominio) != desag_sel:
                    ok = False
                    break
            if ok:
                headers_match.append(header)

        if headers_match:
            # CSV TIPO 1 (HEADERS): Comportamiento actual
            suma = 0.0
            usados = 0
            if getattr(self, 'verbosity', 1) >= 3:
                combo_desc = ', '.join([f"{d.dominio.nombre}:{d.nombre}" for d in combinacion_tematica])
                self.stdout.write(f"    [CSV-HEADERS] Combo {combo_desc} -> headers: {headers_match}")
            for h in headers_match:
                v = self._parsear_numero(fila_dict.get(h))
                if getattr(self, 'verbosity', 1) >= 3:
                    self.stdout.write(f"      {h} = {fila_dict.get(h)} -> {v}")
                if v is not None:
                    suma += v
                    usados += 1
            return suma if usados > 0 else None

        # INTENTO 2: Detectar columna de valor (CSV tipo columnas)
        # Excluir columnas que ya sabemos que no son de valor
        columnas_excluidas = set()
        
        # Excluir columna de fecha
        if regla.columna_fecha:
            columnas_excluidas.add(regla.columna_fecha)
        
        # Excluir columnas geográficas (detectar por nombre de dominio)
        try:
            for dominio_geo in regla.indicador.dominios_desagregacion_geografica.all():
                for header in fila_dict.keys():
                    if dominio_geo.nombre.lower() in header.lower():
                        columnas_excluidas.add(header)
        except Exception:
            pass
        
        # Excluir columnas temáticas (detectar por nombre de dominio)
        try:
            for dominio_tema in regla.indicador.dominios_desagregacion_tematica.all():
                for header in fila_dict.keys():
                    if dominio_tema.nombre.lower() in header.lower():
                        columnas_excluidas.add(header)
        except Exception:
            pass
        
        # Buscar primera columna numérica no excluida
        for header in fila_dict.keys():
            if header not in columnas_excluidas:
                valor = self._parsear_numero(fila_dict[header])
                if valor is not None:
                    # ¡Encontramos columna de valor!
                    if getattr(self, 'verbosity', 1) >= 3:
                        combo_desc = ', '.join([f"{d.dominio.nombre}:{d.nombre}" for d in combinacion_tematica])
                        self.stdout.write(
                            f"    [CSV-COLUMNAS] Combo {combo_desc} -> "
                            f"columna_valor: '{header}', valor_raw: {fila_dict[header]} -> {valor}"
                        )
                    
                    # Aplicar fórmula si existe
                    if regla.formula and regla.formula.strip() not in ("", "valor_celda"):
                        try:
                            valor_formula = self._eval_formula_segura(
                                regla.formula.strip(), 
                                fila_dict, 
                                extra_vars={"valor_celda": valor}
                            )
                            if valor_formula is not None:
                                if getattr(self, 'verbosity', 1) >= 3:
                                    self.stdout.write(
                                        f"      Fórmula aplicada: {regla.formula} -> {valor_formula}"
                                    )
                                return float(valor_formula)
                        except Exception as e:
                            if getattr(self, 'verbosity', 1) >= 2:
                                self.stdout.write(
                                    self.style.WARNING(f"      Error al aplicar fórmula: {e}")
                                )
                    
                    return float(valor)
        
        # FALLBACK: Comportamiento por defecto basado en regla/columnas_fuente
        if getattr(self, 'verbosity', 1) >= 2:
            self.stdout.write(
                self.style.WARNING(
                    "    [FALLBACK] No se encontró valor ni por headers ni por columna, "
                    "usando columnas_fuente"
                )
            )
        columna = None
        if getattr(regla, 'columnas_fuente', None):
            columna = regla.columnas_fuente[0]
        return self.calcular_valor(fila_dict, regla, columna)

    def _parsear_numero(self, valor):
        """Intenta convertir un valor a float manejando formato LATAM/EN:
        - "1.234,56" -> 1234.56
        - "1,234.56" -> 1234.56
        - "1234,56"  -> 1234.56
        - "1234.56"  -> 1234.56
        También limpia espacios y símbolos no numéricos comunes.
        """
        if valor is None:
            return None
        try:
            s = str(valor).strip()
            if s == '':
                return None
            # Valores faltantes comunes
            if s in {'-', '—', '–', 'N/A', 'NA', 'n/a', 'na'}:
                return None
            # Normalizar espacios y signos Unicode
            s = s.replace(' ', '').replace('\xa0', '')
            s = s.replace('−', '-')  # signo menos Unicode
            # Detectar porcentaje y paréntesis negativos
            es_porcentaje = '%' in s
            if es_porcentaje:
                s = s.replace('%', '')
            negativo_parentesis = s.startswith('(') and s.endswith(')')
            if negativo_parentesis:
                s = s[1:-1]
            # Mantener solo dígitos, signos y separadores
            permitido = set('0123456789-.,')
            s = ''.join(ch for ch in s if ch in permitido)
            if ',' in s and '.' in s:
                # Ambos presentes: el último separador define el decimal
                if s.rfind(',') > s.rfind('.'):
                    # coma decimal
                    s = s.replace('.', '')
                    s = s.replace(',', '.')
                else:
                    # punto decimal
                    s = s.replace(',', '')
            elif ',' in s:
                partes = s.split(',')
                if len(partes) == 2 and 1 <= len(partes[1]) <= 2:
                    # Probable decimal con coma
                    s = partes[0].replace('.', '') + '.' + partes[1]
                else:
                    # Probable separador de miles
                    s = s.replace(',', '')
            elif '.' in s:
                partes = s.split('.')
                if len(partes) == 2 and 1 <= len(partes[1]) <= 2:
                    # Decimal con punto (dejamos tal cual)
                    pass
                else:
                    # Probable separador de miles
                    s = s.replace('.', '')
            numero = float(s)
            if negativo_parentesis:
                numero = -numero
            if es_porcentaje:
                numero = numero / 100.0
            return numero
        except Exception:
            return None

    # =========================
    # Soporte de fórmulas seguras
    # =========================
    def _deaccent(self, text: str) -> str:
        if text is None:
            return ''
        text = str(text)
        nfkd = unicodedata.normalize('NFKD', text)
        return ''.join(c for c in nfkd if not unicodedata.combining(c))

    def _sanitizar_ident(self, nombre):
        """Convierte un header a un identificador seguro (letras/números/_), sin colisiones obvias,
        eliminando acentos y normalizando espacios a '_'."""
        if nombre is None:
            return ''
        s = self._deaccent(str(nombre)).strip().lower()
        s = re.sub(r"[^0-9a-zA-Z_ ]+", "_", s)  # quitar símbolos raros
        s = s.replace(' ', '_')
        s = re.sub(r"_+", "_", s).strip('_')
        if not s:
            s = "col"
        if s[0].isdigit():
            s = f"c_{s}"
        return s

    def _eval_formula_segura(self, formula, fila_dict, extra_vars=None):
        """Evalúa una fórmula de forma segura, permitiendo:
        - Operadores aritméticos básicos (+, -, *, /, //, %, **)
        - Números y paréntesis
        - Nombres de variables que corresponden a headers sanitizados
        - Llamadas a col("Nombre Exacto de Columna")
        - Funciones básicas: abs, min, max, round, pow
        Devuelve float o None.
        """
        # Construir variables desde headers
        variables = {}
        usados = set()
        header_to_var = {}
        for header, valor in fila_dict.items():
            base = self._sanitizar_ident(header)
            key = base
            idx = 2
            while key in usados:
                key = f"{base}_{idx}"
                idx += 1
            usados.add(key)
            num = self._parsear_numero(valor)
            variables[key] = float(num) if num is not None else 0.0
            header_to_var[str(header)] = key

        # Log de variables disponibles y mapeo header->ident cuando verbosity alta
        if getattr(self, 'verbosity', 1) >= 3:
            try:
                self.stdout.write(f"[formula] variables disponibles: {len(variables)}")
                # Mostrar hasta 20 mapeos para evitar ruido excesivo
                for h, v in list(header_to_var.items())[:20]:
                    val = variables.get(v)
                    self.stdout.write(f"  - '{h}' -> {v} = {val}")
                restantes = max(0, len(header_to_var) - 20)
                if restantes:
                    self.stdout.write(f"  ... y {restantes} mapeos más")
            except Exception:
                pass

        def col_fn(nombre_col):
            v = self._parsear_numero(fila_dict.get(nombre_col))
            return float(v) if v is not None else 0.0

        env = {
            'col': col_fn,
            'abs': abs,
            'min': min,
            'max': max,
            'round': round,
            'pow': pow,
            **variables,
        }

        # Inyectar variables adicionales seguras (p.ej., valor_celda)
        if extra_vars:
            for k, v in extra_vars.items():
                try:
                    env[str(k)] = float(v)
                except Exception:
                    env[str(k)] = 0.0

        allowed_binops = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
        allowed_unary = (ast.UAdd, ast.USub)
        allowed_names = set(env.keys())
        allowed_calls = {'col', 'abs', 'min', 'max', 'round', 'pow'}

        def _check(node):
            if isinstance(node, ast.Expression):
                _check(node.body)
            elif isinstance(node, ast.BinOp):
                if not isinstance(node.op, allowed_binops):
                    raise ValueError('Operador no permitido')
                _check(node.left); _check(node.right)
            elif isinstance(node, ast.UnaryOp):
                if not isinstance(node.op, allowed_unary):
                    raise ValueError('Operador unario no permitido')
                _check(node.operand)
            elif isinstance(node, ast.Num):
                pass
            elif isinstance(node, ast.Constant):
                # Constantes numéricas permitidas. Constantes string solo se permiten
                # como argumento de col(), validado en la rama ast.Call más abajo.
                if not isinstance(node.value, (int, float)):
                    raise ValueError('Constante no numérica')
            elif isinstance(node, ast.Name):
                if node.id not in allowed_names:
                    raise ValueError(f'Variable no permitida: {node.id}')
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in allowed_calls:
                    func_name = node.func.id
                    if func_name == 'col':
                        # col() requiere exactamente 1 argumento string literal
                        if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                            raise ValueError('col() requiere un único argumento string literal')
                        # no recursar sobre el literal string
                    else:
                        for a in node.args:
                            _check(a)
                    if node.keywords:
                        raise ValueError('Argumentos con nombre no permitidos')
                else:
                    raise ValueError('Llamada no permitida')
            elif isinstance(node, (ast.Load,)):
                pass
            else:
                raise ValueError('Expresión no permitida')

        try:
            # Normalizaciones simples de sintaxis
            # Soportar '^' como potencia -> '**'
            formula_norm = formula.replace('^', '**')

            if getattr(self, 'verbosity', 1) >= 3:
                self.stdout.write(f"[formula] original: {formula}")
                if formula_norm != formula:
                    self.stdout.write(f"[formula] normalizada: {formula_norm}")

            # Reescritura: sustituir nombres de headers (con espacios/acentos) por variables sanitizadas
            # Proteger literales string (p.ej., col("Nombre Exacto")) para no alterar su contenido
            str_pattern = r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')'
            str_lits = []
            def _mask_str(m):
                str_lits.append(m.group(0))
                return f"__STR{len(str_lits)-1}__"
            formula_masked = re.sub(str_pattern, _mask_str, formula_norm)

            # Trabajar sobre una versión sin acentos del texto enmascarado para emparejar flexible
            formula_deacc = self._deaccent(formula_masked)
            # Ordenar headers por longitud descendente para evitar reemplazos parciales
            for header, var in sorted(header_to_var.items(), key=lambda kv: len(self._deaccent(kv[0])), reverse=True):
                h = self._deaccent(header)
                if not h:
                    continue
                # Convertir el header en patrón que acepta espacios o underscores
                # Ej: 'Hombres 85 y mas' -> r'Hombres(?:[ _]+)85(?:[ _]+)y(?:[ _]+)mas'
                tokens = [re.escape(tok) for tok in re.split(r"[\s_]+", h) if tok]
                if not tokens:
                    continue
                pattern = r'(?<![0-9A-Za-z_])' + r'(?:[ _]+)'.join(tokens) + r'(?![0-9A-Za-z_])'
                formula_deacc = re.sub(pattern, var, formula_deacc, flags=re.IGNORECASE)

            # Restaurar literales string en la fórmula reescrita
            for i, lit in enumerate(str_lits):
                placeholder = f"__STR{i}__"
                formula_deacc = formula_deacc.replace(placeholder, lit)

            if getattr(self, 'verbosity', 1) >= 3:
                self.stdout.write(f"[formula] reescrita: {formula_deacc}")

            # Usamos la fórmula reescrita sin acentos para el parseo seguro
            tree = ast.parse(formula_deacc, mode='eval')
            _check(tree)
            value = eval(compile(tree, '<formula>', 'eval'), {"__builtins__": {}}, env)
            return float(value)
        except Exception as e:
            # Mostrar ayuda cuando hay error si verbosity alta
            if getattr(self, 'verbosity', 1) >= 2:
                self.stdout.write(self.style.WARNING(f"Fórmula inválida: '{formula}'. Error: {e}"))
                if getattr(self, 'verbosity', 1) >= 3:
                    try:
                        self.stdout.write(self.style.WARNING(f"  Reescrita: '{formula_deacc}'"))
                        nombres = sorted(list(allowed_names))
                        preview = nombres[:20]
                        restantes = max(0, len(nombres) - 20)
                        self.stdout.write(self.style.WARNING(f"  Variables permitidas: {preview}{' ...' if restantes else ''}"))
                    except Exception:
                        pass
            return None
