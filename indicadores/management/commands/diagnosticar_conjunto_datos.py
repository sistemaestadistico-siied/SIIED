from django.core.management.base import BaseCommand
from indicadores.models import ConjuntoDatos, Indicador, ReglaExtraccion, Desagregacion, DominioDesagregacion
import csv

class Command(BaseCommand):
    help = 'Diagnostica la correspondencia entre conjunto_datos y desagregaciones antes del procesamiento'
    
    def add_arguments(self, parser):
        parser.add_argument('--conjunto_datos-id', type=int, help='ID del conjunto_datos a diagnosticar')
        parser.add_argument('--indicador-id', type=int, help='ID del indicador a diagnosticar')
        parser.add_argument('--regla-id', type=int, help='ID de la regla de extracción a diagnosticar')
    
    def handle(self, *args, **options):
        conjunto_datos_id = options.get('conjunto_datos_id')
        indicador_id = options.get('indicador_id')
        regla_id = options.get('regla_id')
        
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
            self.style.SUCCESS(f'Diagnóstico para indicador: {indicador.nombre}')
        )
        
        # Diagnosticar el conjunto_datos
        self.diagnosticar_conjunto_datos(conjunto_datos, indicador, regla)
    
    def diagnosticar_conjunto_datos(self, ConjuntoDatos, indicador, regla):
        """Diagnostica la correspondencia entre conjunto_datos y desagregaciones"""
        if not conjunto_datos.archivo_csv:
            self.stdout.write(
                self.style.ERROR('No se ha definido un archivo CSV para este conjunto_datos')
            )
            return
        
        # Abrir el archivo CSV
        archivo_csv = conjunto_datos.archivo_csv.path
        
        # Detectar encoding y delimitador
        encoding, delimiter = self.detectar_encoding_y_delimitador(archivo_csv)
        
        # Leer encabezados
        with open(archivo_csv, 'r', encoding=encoding) as csvfile:
            reader = csv.reader(csvfile, delimiter=delimiter)
            headers = next(reader)
        
        self.stdout.write(f'\nEncabezados del CSV ({len(headers)} columnas):')
        for i, header in enumerate(headers[:10]):
            self.stdout.write(f'  {i+1}. {header}')
        if len(headers) > 10:
            self.stdout.write(f'  ... y {len(headers) - 10} más')
        
        # 1. Obtener la lista de columnas fuente de la regla de extracción
        self.stdout.write(f"\n=== DIAGNÓSTICO DE COLUMNAS FUENTE ===")
        columnas_fuente = regla.columnas_fuente
        self.stdout.write("Columnas fuente definidas en la regla:")
        for col in columnas_fuente:
            self.stdout.write(f"  - {col}")
        
        # Verificar si las columnas fuente existen en el CSV
        columnas_encontradas = [col for col in columnas_fuente if col in headers]
        columnas_faltantes = [col for col in columnas_fuente if col not in headers]
        
        if columnas_encontradas:
            self.stdout.write("Columnas fuente encontradas en el CSV:")
            for col in columnas_encontradas:
                self.stdout.write(f"  - {col}")
        
        if columnas_faltantes:
            self.stdout.write(self.style.ERROR("Columnas fuente faltantes en el CSV:"))
            for col in columnas_faltantes:
                self.stdout.write(f"  - {col}")
        
        # 2. Verificar si todas esas columnas existen en la conjunto_datos del indicador
        self.stdout.write(f"\n=== VERIFICACIÓN DE COLUMNAS FUENTE ===")
        if not columnas_faltantes:
            self.stdout.write(self.style.SUCCESS("✓ Todas las columnas fuente existen en el CSV"))
        else:
            self.stdout.write(self.style.ERROR("✗ Hay columnas fuente faltantes en el CSV"))
        
        # 3. Ubicar la columna con la fecha o el "Año"
        columna_fecha = self.inferir_columna_fecha(headers)
        self.stdout.write(f"\n=== DETECCIÓN DE COLUMNA DE FECHA/AÑO ===")
        if columna_fecha:
            self.stdout.write(f"Columna de fecha/año detectada: {columna_fecha}")
            # Mostrar valores disponibles en la columna de fecha
            valores_fecha = self.obtener_valores_fecha(archivo_csv, encoding, delimiter, columna_fecha)
            self.stdout.write(f"Valores de fecha/año disponibles ({len(valores_fecha)} valores):")
            for i, valor in enumerate(sorted(valores_fecha)[:10]):  # Mostrar solo los primeros 10
                self.stdout.write(f"  - {valor}")
            if len(valores_fecha) > 10:
                self.stdout.write(f"  ... y {len(valores_fecha) - 10} más")
        else:
            self.stdout.write(self.style.WARNING("No se detectó columna de fecha/año"))
        
        # 4. Con base a los dominios de desagregación de tipo geográfico del indicador
        #    debe detectar los encabezados en el .csv
        self.diagnosticar_desagregaciones_geograficas(headers, indicador)
        
        # 5. Con base a la columnas de desagregaciones geográficas detectadas
        #    se debe recorrer las columnas en el csv para revisar si los valores
        #    corresponden con las desagregaciones del dominio de desagregaciones
        #    de tipo geográfico al que hace referencia
        self.verificar_valores_desagregaciones_geograficas(archivo_csv, encoding, delimiter, indicador)
        
        # 6. NUEVO: Detectar tipo de CSV (columnas vs headers) para dominios temáticos
        self.detectar_tipo_csv_dominios_tematicos(archivo_csv, encoding, delimiter, headers, indicador)
        
        # 7. Buscar desagregaciones temáticas en los demás encabezados
        #    (exceptuando fecha/año y dominios geográficos)
        self.diagnosticar_desagregaciones_tematicas_avanzado(headers, indicador, columna_fecha)
        
        # 8. Verificar los valores en las columnas temáticas
        self.verificar_valores_desagregaciones_tematicas(archivo_csv, encoding, delimiter, indicador, headers)
        
        # Mostrar resumen
        self.mostrar_resumen(headers, indicador, regla, columna_fecha)
    
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
                    self.stdout.write(f"\nEncoding detectado: {encoding}, Delimitador: '{delimiter}'")
                    return encoding, delimiter
            except (UnicodeDecodeError, csv.Error):
                continue
        
        # Si no se pudo detectar, usar valores por defecto
        self.stdout.write(
            self.style.WARNING("\nNo se pudo detectar encoding/delimitador. Usando utf-8 y ','")
        )
        return 'utf-8', ','
    
    def diagnosticar_desagregaciones_geograficas(self, headers, indicador):
        """Diagnostica las desagregaciones geográficas"""
        self.stdout.write("\n=== DIAGNÓSTICO DE DESAGREGACIONES GEOGRÁFICAS ===")
        
        # Obtener dominios geográficos del indicador
        dominios_geo = indicador.dominios_desagregacion_geografica.all()
        
        if not dominios_geo:
            self.stdout.write("No se encontraron dominios geográficos para este indicador")
            return
        
        for dominio in dominios_geo:
            self.stdout.write(f"\nDominio geográfico: {dominio.nombre}")
            
            # Obtener desagregaciones definidas
            desagregaciones = dominio.desagregaciones.all()
            self.stdout.write(f"  Desagregaciones definidas ({len(desagregaciones)}):")
            for desag in desagregaciones:
                self.stdout.write(f"    - {desag.nombre}")
            
            # Buscar encabezados que contengan el nombre del dominio
            encabezados_coincidentes = [h for h in headers if dominio.nombre.lower() in h.lower()]
            self.stdout.write(f"  Encabezados que contienen \"{dominio.nombre}\":")
            for encabezado in encabezados_coincidentes:
                self.stdout.write(f"    - {encabezado}")
            
            # Para desagregaciones geográficas, no buscamos coincidencias con nombres individuales de desagregaciones
            # Solo mostramos los encabezados que contienen el nombre del dominio
    
    def diagnosticar_desagregaciones_tematicas(self, headers, indicador):
        """Diagnostica las desagregaciones temáticas definidas en el indicador"""
        self.stdout.write("\n=== DIAGNÓSTICO DE DESAGREGACIONES TEMÁTICAS DEFINIDAS ===")
        
        # Obtener dominios temáticos del indicador
        dominios_tema = indicador.dominios_desagregacion_tematica.all()
        
        if not dominios_tema:
            self.stdout.write("No se encontraron dominios temáticos definidos para este indicador")
            return
        
        for dominio in dominios_tema:
            self.stdout.write(f"\nDominio temático: {dominio.nombre}")
            
            # Obtener desagregaciones definidas
            desagregaciones = dominio.desagregaciones.all()
            self.stdout.write(f"  Desagregaciones definidas ({len(desagregaciones)}):")
            for desag in desagregaciones:
                self.stdout.write(f"    - {desag.nombre}")
            
            # Buscar encabezados que contengan los nombres de las desagregaciones
            encabezados_coincidentes = []
            for desag in desagregaciones:
                # Buscar coincidencias más precisas
                coincidencias = []
                for header in headers:
                    # Para desagregaciones específicas, buscar coincidencias más exactas
                    if desag.nombre.lower() == header.lower():
                        coincidencias.append(header)
                    # Para evitar falsos positivos, verificar que la desagregación no esté contenida como substring
                    # en una palabra más larga
                    elif desag.nombre.lower() == "total" and header.lower().startswith("total_"):
                        # No considerar "Total_XX" como coincidencia para "Total"
                        pass
                    elif desag.nombre.lower() in header.lower() and len(header) > len(desag.nombre):
                        # Solo considerar coincidencias si el encabezado es más largo que la desagregación
                        # y no es un caso especial como "Total_XX"
                        if not (desag.nombre.lower() == "total" and "_" in header):
                            coincidencias.append(header)
                if coincidencias:
                    encabezados_coincidentes.extend(coincidencias)
            
            self.stdout.write(f"  Encabezados que contienen nombres de desagregaciones:")
            for encabezado in set(encabezados_coincidentes):  # Usar set para eliminar duplicados
                self.stdout.write(f"    - {encabezado}")
    
    def diagnosticar_desagregaciones_tematicas_avanzado(self, headers, indicador, columna_fecha):
        """Diagnostica las desagregaciones temáticas avanzadas excluyendo fecha y geográficas"""
        self.stdout.write("\n=== DIAGNÓSTICO DE DESAGREGACIONES TEMÁTICAS AVANZADO ===")
        
        # Obtener dominios temáticos del indicador
        dominios_tema = indicador.dominios_desagregacion_tematica.all()
        
        if not dominios_tema:
            self.stdout.write("No se encontraron dominios temáticos definidos para este indicador")
            return
        
        # Excluir columnas de fecha/año y columnas geográficas de la búsqueda
        columnas_excluidas = []
        
        # Agregar columna de fecha si existe
        if columna_fecha:
            columnas_excluidas.append(columna_fecha)
        
        # Agregar columnas geográficas
        for dominio_geo in indicador.dominios_desagregacion_geografica.all():
            for header in headers:
                if dominio_geo.nombre.lower() in header.lower():
                    columnas_excluidas.append(header)
        
        # Filtrar encabezados excluyendo las columnas identificadas
        headers_filtrados = [h for h in headers if h not in columnas_excluidas]
        
        self.stdout.write(f"Columnas excluidas de la búsqueda temática: {columnas_excluidas}")
        self.stdout.write(f"Columnas restantes para búsqueda temática: {len(headers_filtrados)}")
        
        # Para cada dominio temático, verificar si sus desagregaciones aparecen en los encabezados filtrados
        for dominio in dominios_tema:
            self.stdout.write(f"\nDominio temático: {dominio.nombre}")
            
            # Obtener desagregaciones del dominio
            desagregaciones = dominio.desagregaciones.all()
            self.stdout.write(f"  Desagregaciones definidas ({len(desagregaciones)}):")
            for desag in desagregaciones:
                if desag.es_rango and desag.valores_rango:
                    self.stdout.write(f"    - {desag.nombre} (RANGO: {desag.valores_rango})")
                else:
                    self.stdout.write(f"    - {desag.nombre}")
            
            # Buscar encabezados que contengan los nombres de las desagregaciones
            encabezados_coincidentes = []
            desagregaciones_coincidentes = []
            
            for desag in desagregaciones:
                # Buscar coincidencias más precisas
                coincidencias = []
                for header in headers_filtrados:
                    if desag.es_rango and desag.valores_rango:
                        # Para desagregaciones de tipo rango, buscar los valores del rango en los encabezados
                        for valor_rango in desag.valores_rango:
                            # Verificar coincidencia exacta con valores del rango
                            if str(valor_rango).lower() == header.lower():
                                coincidencias.append(header)
                                break
                            # Verificar coincidencia parcial con valores del rango
                            elif str(valor_rango).lower() in header.lower():
                                coincidencias.append(header)
                                break
                    else:
                        # Para desagregaciones normales, buscar el nombre de la desagregación
                        # Verificar coincidencia exacta
                        if desag.nombre.lower() == header.lower():
                            coincidencias.append(header)
                        # Casos especiales para evitar falsos positivos
                        elif desag.nombre.lower() == "total" and header.lower().startswith("total_"):
                            # No considerar "Total_XX" como coincidencia para "Total"
                            pass
                        # Verificar coincidencia parcial más precisa
                        elif desag.nombre.lower() in header.lower() and len(header) > len(desag.nombre):
                            # Solo considerar coincidencias si el encabezado es más largo que la desagregación
                            # y no es un caso especial como "Total_XX"
                            if not (desag.nombre.lower() == "total" and "_" in header):
                                coincidencias.append(header)
                        # Verificar coincidencia parcial (encabezado en la desagregación) solo para casos específicos
                        elif header.lower() in desag.nombre.lower() and len(header) < len(desag.nombre) and len(header) > 1:
                            # Solo para encabezados más cortos que la desagregación
                            coincidencias.append(header)
                
                if coincidencias:
                    encabezados_coincidentes.extend(coincidencias)
                    desagregaciones_coincidentes.append(desag.nombre)
            
            if encabezados_coincidentes:
                self.stdout.write(f"  Desagregaciones encontradas en encabezados ({len(set(desagregaciones_coincidentes))}):")
                for desag_nombre in set(desagregaciones_coincidentes):
                    self.stdout.write(f"    - {desag_nombre}")
                
                self.stdout.write(f"  Encabezados que contienen estas desagregaciones:")
                for encabezado in set(encabezados_coincidentes):
                    self.stdout.write(f"    - {encabezado}")
                
                # Verificar si en los encabezados hay múltiples desagregaciones separadas por "_"
                self.stdout.write(f"  Análisis de combinaciones múltiples:")
                for encabezado in set(encabezados_coincidentes):
                    if "_" in encabezado and encabezado not in desagregaciones_coincidentes:
                        partes = encabezado.split("_")
                        partes_coincidentes = [p for p in partes if any(
                            (p.lower() in desag.nombre.lower()) or 
                            (desag.es_rango and desag.valores_rango and any(p.lower() == str(valor).lower() for valor in desag.valores_rango))
                            for desag in desagregaciones)]
                        if partes_coincidentes:
                            self.stdout.write(f"    - {encabezado} contiene múltiples desagregaciones: {partes_coincidentes}")
            else:
                self.stdout.write(f"  No se encontraron coincidencias para este dominio")
    
    def verificar_valores_desagregaciones_geograficas(self, archivo_csv, encoding, delimiter, indicador):
        """Verifica que los valores en las columnas geográficas correspondan a las desagregaciones definidas"""
        self.stdout.write("\n=== VERIFICACIÓN DE VALORES DE DESAGREGACIONES GEOGRÁFICAS ===")
        
        # Obtener dominios geográficos del indicador
        dominios_geo = indicador.dominios_desagregacion_geografica.all()
        
        if not dominios_geo:
            self.stdout.write("No se encontraron dominios geográficos para verificar")
            return
        
        # Leer el archivo CSV para obtener los valores
        with open(archivo_csv, 'r', encoding=encoding) as csvfile:
            reader = csv.reader(csvfile, delimiter=delimiter)
            headers = next(reader)
            # Leer algunas filas para analizar
            filas = list(reader)[:100]  # Limitar a 100 filas para el análisis
        
        for dominio in dominios_geo:
            self.stdout.write(f"\nDominio geográfico: {dominio.nombre}")
            
            # Obtener desagregaciones definidas
            desagregaciones_definidas = set(desag.nombre for desag in dominio.desagregaciones.all())
            self.stdout.write(f"  Desagregaciones definidas ({len(desagregaciones_definidas)}):")
            for desag_nombre in sorted(desagregaciones_definidas):
                self.stdout.write(f"    - {desag_nombre}")
            
            # Buscar encabezados que contengan el nombre del dominio
            encabezados_coincidentes = [h for h in headers if dominio.nombre.lower() in h.lower()]
            
            if not encabezados_coincidentes:
                self.stdout.write(f"  No se encontraron columnas para este dominio en el CSV")
                continue
            
            # Para cada encabezado coincidente, obtener los valores únicos en el CSV
            for encabezado in encabezados_coincidentes:
                try:
                    columna_index = headers.index(encabezado)
                    valores_en_csv = set(row[columna_index] for row in filas if len(row) > columna_index and row[columna_index])
                    
                    self.stdout.write(f"  Columna '{encabezado}' valores únicos ({len(valores_en_csv)}):")
                    for valor in sorted(valores_en_csv)[:10]:  # Mostrar solo los primeros 10
                        self.stdout.write(f"    - {valor}")
                    if len(valores_en_csv) > 10:
                        self.stdout.write(f"    ... y {len(valores_en_csv) - 10} más")
                    
                    # Verificar si los valores en el CSV corresponden a las desagregaciones definidas
                    valores_coincidentes = valores_en_csv.intersection(desagregaciones_definidas)
                    valores_no_definidos = valores_en_csv.difference(desagregaciones_definidas)
                    
                    if valores_coincidentes:
                        self.stdout.write(f"  Valores que coinciden con desagregaciones definidas ({len(valores_coincidentes)}):")
                        for valor in sorted(valores_coincidentes):
                            self.stdout.write(f"    - {valor}")
                    
                    if valores_no_definidos:
                        self.stdout.write(self.style.WARNING(f"  Valores no definidos en las desagregaciones ({len(valores_no_definidos)}):"))
                        for valor in sorted(valores_no_definidos):
                            self.stdout.write(f"    - {valor}")
                    
                except ValueError:
                    self.stdout.write(f"  Error: No se encontró la columna '{encabezado}' en los encabezados")
    
    def verificar_valores_desagregaciones_tematicas(self, archivo_csv, encoding, delimiter, indicador, headers):
        """Verifica que los valores en las columnas temáticas correspondan a las desagregaciones definidas"""
        self.stdout.write("\n=== VERIFICACIÓN DE VALORES DE DESAGREGACIONES TEMÁTICAS ===")
        
        # Obtener dominios temáticos del indicador
        dominios_tema = indicador.dominios_desagregacion_tematica.all()
        
        if not dominios_tema:
            self.stdout.write("No se encontraron dominios temáticos para verificar")
            return
        
        # Leer el archivo CSV para obtener los valores
        with open(archivo_csv, 'r', encoding=encoding) as csvfile:
            reader = csv.reader(csvfile, delimiter=delimiter)
            headers_csv = next(reader)
            # Leer algunas filas para analizar
            filas = list(reader)[:100]  # Limitar a 100 filas para el análisis
        
        # Excluir columnas de fecha/año y columnas geográficas
        columnas_excluidas = []
        
        # Agregar columna de fecha si existe
        columna_fecha = self.inferir_columna_fecha(headers)
        if columna_fecha:
            columnas_excluidas.append(columna_fecha)
        
        # Agregar columnas geográficas
        for dominio_geo in indicador.dominios_desagregacion_geografica.all():
            for header in headers:
                if dominio_geo.nombre.lower() in header.lower():
                    columnas_excluidas.append(header)
        
        # Filtrar encabezados excluyendo las columnas identificadas
        headers_filtrados = [h for h in headers if h not in columnas_excluidas]
        
        for dominio in dominios_tema:
            self.stdout.write(f"\nDominio temático: {dominio.nombre}")
            
            # Obtener desagregaciones definidas
            desagregaciones_definidas = dominio.desagregaciones.all()
            self.stdout.write(f"  Desagregaciones definidas ({len(desagregaciones_definidas)}):")
            
            # Crear un conjunto de valores a buscar (nombres de desagregaciones y valores de rango)
            valores_a_buscar = set()
            for desag in desagregaciones_definidas:
                if desag.es_rango and desag.valores_rango:
                    self.stdout.write(f"    - {desag.nombre} (RANGO: {desag.valores_rango})")
                    # Agregar los valores del rango al conjunto de búsqueda
                    for valor_rango in desag.valores_rango:
                        valores_a_buscar.add(str(valor_rango))
                else:
                    self.stdout.write(f"    - {desag.nombre}")
                    valores_a_buscar.add(desag.nombre)
            
            # Para cada encabezado filtrado, obtener los valores únicos en el CSV
            for encabezado in headers_filtrados:
                try:
                    columna_index = headers_csv.index(encabezado)
                    valores_en_csv = set(row[columna_index] for row in filas if len(row) > columna_index and row[columna_index])
                    
                    self.stdout.write(f"  Columna '{encabezado}' valores únicos ({len(valores_en_csv)}):")
                    for valor in sorted(valores_en_csv)[:10]:  # Mostrar solo los primeros 10
                        self.stdout.write(f"    - {valor}")
                    if len(valores_en_csv) > 10:
                        self.stdout.write(f"    ... y {len(valores_en_csv) - 10} más")
                    
                    # Verificar si los valores en el CSV corresponden a las desagregaciones definidas
                    valores_coincidentes = valores_en_csv.intersection(valores_a_buscar)
                    valores_no_definidos = valores_en_csv.difference(valores_a_buscar)
                    
                    if valores_coincidentes:
                        self.stdout.write(f"  Valores que coinciden con desagregaciones definidas ({len(valores_coincidentes)}):")
                        for valor in sorted(valores_coincidentes):
                            self.stdout.write(f"    - {valor}")
                    
                    if valores_no_definidos:
                        self.stdout.write(self.style.WARNING(f"  Valores no definidos en las desagregaciones ({len(valores_no_definidos)}):"))
                        for valor in sorted(valores_no_definidos):
                            self.stdout.write(f"    - {valor}")
                    
                except ValueError:
                    self.stdout.write(f"  Error: No se encontró la columna '{encabezado}' en los encabezados")
    
    def detectar_tipo_csv_dominios_tematicos(self, archivo_csv, encoding, delimiter, headers, indicador):
        """
        NUEVO: Detecta si cada dominio temático está en COLUMNAS (long format) o HEADERS (wide format).
        Esta es la misma lógica que usa el comando procesar_conjunto_datos_cartesiano.
        """
        self.stdout.write("\n=== DETECCIÓN DE TIPO DE CSV PARA DOMINIOS TEMÁTICOS ===")
        self.stdout.write("Detectando si las desagregaciones temáticas están en columnas o headers...\n")
        
        # Leer primera fila de datos para análisis
        with open(archivo_csv, 'r', encoding=encoding) as csvfile:
            reader = csv.reader(csvfile, delimiter=delimiter)
            headers_csv = next(reader)
            primera_fila = next(reader, None)
            if not primera_fila:
                self.stdout.write(self.style.WARNING("  El CSV no tiene datos para analizar"))
                return
        
        fila_dict = dict(zip(headers_csv, primera_fila))
        
        for dominio in indicador.dominios_desagregacion_tematica.all():
            self.stdout.write(f"\nDominio temático: '{dominio.nombre}'")
            
            # Mostrar configuración de agregación de totales
            tipo_agg = getattr(dominio, 'tipo_agregacion_total', 'suma')
            if tipo_agg == 'suma':
                self.stdout.write(self.style.SUCCESS(
                    f"  📦 Configuración de Totales: SUMA (se calculará sumando desagregaciones)"
                ))
            elif tipo_agg == 'ninguno':
                self.stdout.write(self.style.WARNING(
                    f"  ⚠️  Configuración de Totales: NINGUNO (se extraerá directamente del CSV)"
                ))
                self.stdout.write(self.style.WARNING(
                    f"     IMPORTANTE: Asegúrate que el CSV incluya columnas 'Total' para este dominio"
                ))
            
            # Buscar columna con nombre del dominio
            columna_detectada = None
            valor_ejemplo = None
            
            for columna in headers:
                columna_lower = columna.lower()
                dominio_lower = dominio.nombre.lower()
                
                if dominio_lower in columna_lower or columna_lower in dominio_lower:
                    # Verificar que el VALOR coincida con una desagregación
                    valor_columna = str(fila_dict.get(columna, '')).strip()
                    if valor_columna:
                        for desag in dominio.desagregaciones.all():
                            if desag.nombre.lower() == valor_columna.lower():
                                columna_detectada = columna
                                valor_ejemplo = valor_columna
                                break
                    if columna_detectada:
                        break
            
            if columna_detectada:
                # TIPO: COLUMNAS (long format)
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ Tipo detectado: COLUMNAS (long format)"
                ))
                self.stdout.write(f"  Columna: '{columna_detectada}'")
                self.stdout.write(f"  Valor ejemplo: '{valor_ejemplo}'")
                self.stdout.write(f"  Modo de procesamiento: Lectura directa (1 fila → 1 dato)")
            else:
                # TIPO: HEADERS (wide format)
                # Buscar cuántos headers contienen desagregaciones de este dominio
                headers_con_desag = 0
                ejemplos = []
                
                for header in headers:
                    header_lower = header.lower()
                    for desag in dominio.desagregaciones.all():
                        if desag.nombre and desag.nombre.lower() in header_lower:
                            headers_con_desag += 1
                            if len(ejemplos) < 3:
                                ejemplos.append(header)
                            break
                
                if headers_con_desag > 0:
                    self.stdout.write(self.style.SUCCESS(
                        f"  ✓ Tipo detectado: HEADERS (wide format)"
                    ))
                    self.stdout.write(f"  Headers detectados: {headers_con_desag}")
                    self.stdout.write(f"  Ejemplos: {', '.join(ejemplos[:3])}")
                    self.stdout.write(f"  Modo de procesamiento: Producto cartesiano (1 fila → N datos)")
                else:
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠ No se detectó claramente (asumirá HEADERS por defecto)"
                    ))
        
        self.stdout.write("\n" + "="*70)
        self.stdout.write("RESUMEN DE TIPOS DETECTADOS:")
        self.stdout.write("  - CSV COLUMNAS (long): Cada fila = 1 combinación específica")
        self.stdout.write("  - CSV HEADERS (wide): Cada fila = múltiples combinaciones")
        self.stdout.write("="*70)
    
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
    
    def obtener_valores_fecha(self, archivo_csv, encoding, delimiter, columna_fecha):
        """Obtiene los valores únicos de la columna de fecha"""
        valores = set()
        
        with open(archivo_csv, 'r', encoding=encoding) as csvfile:
            reader = csv.reader(csvfile, delimiter=delimiter)
            headers = next(reader)
            
            # Encontrar el índice de la columna de fecha
            try:
                columna_index = headers.index(columna_fecha)
            except ValueError:
                return valores
            
            # Leer las filas y obtener los valores
            for row in reader:
                if len(row) > columna_index and row[columna_index]:
                    valores.add(row[columna_index])
        
        return valores
    
    # Este método se reemplaza con diagnosticar_desagregaciones_tematicas_avanzado
    
    # Eliminando este método ya que lo integramos en el método principal
    
    def mostrar_resumen(self, headers, indicador, regla, columna_fecha):
        """Muestra un resumen del diagnóstico"""
        self.stdout.write("\n=== RESUMEN DEL DIAGNÓSTICO ===")
        
        # Contar desagregaciones
        total_geo = sum(dominio.desagregaciones.count() for dominio in indicador.dominios_desagregacion_geografica.all())
        total_tema = sum(dominio.desagregaciones.count() for dominio in indicador.dominios_desagregacion_tematica.all())
        
        self.stdout.write(f"Total de desagregaciones geográficas definidas: {total_geo}")
        self.stdout.write(f"Total de desagregaciones temáticas definidas: {total_tema}")
        self.stdout.write(f"Total de columnas en el CSV: {len(headers)}")
        
        if columna_fecha:
            self.stdout.write(f"Columna de fecha/año detectada: {columna_fecha}")
        
        # Recomendaciones
        self.stdout.write("\n=== RECOMENDACIONES ===")
        
        # Verificar si todo está listo para procesar
        columnas_fuente = regla.columnas_fuente
        columnas_faltantes = [col for col in columnas_fuente if col not in headers]
        
        if not columnas_faltantes:
            self.stdout.write(self.style.SUCCESS("✓ El conjunto_datos parece listo para procesar"))
            self.stdout.write("Puede ejecutar el comando procesar_conjunto_datos_cartesiano para procesar los datos")
        else:
            self.stdout.write(self.style.ERROR("✗ Hay columnas fuente faltantes en el CSV"))

    def diagnosticar_desagregaciones_potenciales(self, headers, indicador):
        """Diagnostica desagregaciones potenciales basadas en los encabezados del CSV"""
        self.stdout.write("\n=== DIAGNÓSTICO DE DESAGREGACIONES POTENCIALES ===")
        
        # Excluir columnas que ya identificamos como fecha o geográficas
        columnas_excluidas = []
        
        # Agregar columnas geográficas
        for dominio_geo in indicador.dominios_desagregacion_geografica.all():
            for header in headers:
                if dominio_geo.nombre.lower() in header.lower():
                    columnas_excluidas.append(header)
        
        # Filtrar encabezados
        headers_filtrados = [h for h in headers if h not in columnas_excluidas]
        
        self.stdout.write(f"Encabezados filtrados para búsqueda de desagregaciones potenciales: {len(headers_filtrados)}")
        
        # Mostrar algunos encabezados filtrados como posibles desagregaciones
        self.stdout.write("Algunos encabezados que podrían representar desagregaciones temáticas:")
        for header in headers_filtrados[:10]:  # Mostrar solo los primeros 10
            self.stdout.write(f"  - {header}")
        if len(headers_filtrados) > 10:
            self.stdout.write(f"  ... y {len(headers_filtrados) - 10} más")
