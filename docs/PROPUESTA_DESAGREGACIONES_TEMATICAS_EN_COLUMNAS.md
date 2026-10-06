# Propuesta: Desagregaciones Temáticas en Columnas

**Fecha:** 3 de Noviembre de 2025  
**Problema:** Evolución del comando `procesar_microdata_cartesiano` para soportar desagregaciones temáticas en columnas (no solo en encabezados)

---

## 📋 Análisis del Problema

### Situación Actual

El comando `procesar_microdata_cartesiano.py` funciona con dos tipos de desagregaciones:

#### 1. **Desagregaciones Geográficas** → Busca en COLUMNAS
```python
# Líneas 339-361
def obtener_desagregaciones_geograficas(self, fila_dict, indicador):
    for dominio in indicador.dominios_desagregacion_geografica.all():
        for columna, valor in fila_dict.items():
            if dominio.nombre.lower() in columna.lower():
                # Busca el VALOR de esa columna en la BD
                desag = Desagregacion.objects.get(dominio=dominio, nombre__iexact=valor)
```

**Ejemplo CSV:**
```csv
Año,Comuna,Valor_Total
2024,Cali,1500
2024,Palmira,800
```
- Columna "Comuna" → Dominio geográfico "Comuna"
- Valor "Cali" → Desagregación "Cali" del dominio "Comuna"

#### 2. **Desagregaciones Temáticas** → Busca en ENCABEZADOS (headers)
```python
# Líneas 363-416
def obtener_desagregaciones_tematicas_posibles(self, fila_dict, indicador, headers):
    for dominio in indicador.dominios_desagregacion_tematica.all():
        for desag in desags_dominio:
            for columna, valor in fila_dict.items():
                if desag.nombre.lower() in columna.lower():
                    # Busca NOMBRE de desagregación en el HEADER
```

**Ejemplo CSV:**
```csv
Año,Comuna,Hombres_0_4,Mujeres_0_4,Hombres_5_9,Mujeres_5_9
2024,Cali,100,150,120,180
```
- Header "Hombres_0_4" → Dominio "Sexo" (Hombres) + Dominio "Edad" (0-4)
- Se genera **producto cartesiano**: [Hombres, Mujeres] × [0-4, 5-9] = 4 combinaciones
- Para cada combinación, busca la columna correspondiente y toma su valor

### Flujo de Procesamiento Actual

```
Por cada FILA del CSV:
  1. Leer fecha
  2. Obtener desagregaciones GEOGRÁFICAS (de columnas)
     → [Comuna: Cali]
  3. Obtener desagregaciones TEMÁTICAS posibles (de headers)
     → [Sexo: Hombres, Mujeres] × [Edad: 0-4, 5-9]
  4. Generar PRODUCTO CARTESIANO
     → [(Hombres, 0-4), (Hombres, 5-9), (Mujeres, 0-4), (Mujeres, 5-9)]
  5. Por cada COMBINACIÓN:
     a. Buscar header que coincida (línea 470-527: construir_mapeo_columnas)
        → "Hombres_0_4" coincide con (Hombres, 0-4)
     b. Tomar valor de esa columna → 100
     c. Aplicar fórmula si existe
     d. Crear Dato con esa combinación
```

**Resultado:** De 1 fila del CSV se generan 4 objetos Dato (producto cartesiano)

---

## 🚨 El Problema

### Caso de Uso 2: Desagregaciones Temáticas en COLUMNAS

Usuario tiene este CSV:

```csv
Año,Comuna,Sexo,Edad,Valor
2024,Cali,Masculino,0-4,100
2024,Cali,Femenino,0-4,150
2024,Cali,Masculino,5-9,120
2024,Cali,Femenino,5-9,180
```

**Características:**
- "Comuna" → Desagregación geográfica (en columna) ✅
- "Sexo" → Desagregación temática (en columna) ❌
- "Edad" → Desagregación temática (en columna) ❌
- "Valor" → Dato numérico

**Problema:**
- El comando busca desagregaciones temáticas en HEADERS
- No encuentra "Masculino", "Femenino", "0-4", "5-9" en headers
- No puede generar producto cartesiano
- No procesa los datos

### Workaround Actual (Manual)

1. Cambiar el tipo del dominio "Sexo" de `temático` a `geográfico` en BD
2. Cambiar el tipo del dominio "Edad" de `temático` a `geográfico` en BD
3. Reiniciar wizard para que detecte los dominios
4. Procesar

**Problemas del workaround:**
- ❌ No es semánticamente correcto (Sexo no es geográfico)
- ❌ Requiere intervención manual cada vez
- ❌ Requiere reiniciar el wizard
- ❌ Confunde la clasificación conceptual de desagregaciones

---

## 🧩 Diferencias Conceptuales Clave

### CSV Tipo 1: Headers Temáticos (Actual)
```csv
Año,Comuna,H_0_4,M_0_4,H_5_9,M_5_9
2024,Cali,100,150,120,180
```

**Características:**
- Cada fila representa MÚLTIPLES combinaciones (comprimidas)
- Headers contienen las combinaciones pre-calculadas
- Sistema genera producto cartesiano y busca columnas
- De 1 fila → N datos (según combinaciones)

### CSV Tipo 2: Columnas Temáticas (Nuevo)
```csv
Año,Comuna,Sexo,Edad,Valor
2024,Cali,H,0-4,100
2024,Cali,M,0-4,150
2024,Cali,H,5-9,120
2024,Cali,M,5-9,180
```

**Características:**
- Cada fila representa UNA SOLA combinación (explícita)
- Columnas contienen las desagregaciones individuales
- Sistema lee desagregaciones directamente
- De 1 fila → 1 dato

**Diferencia fundamental:** 
- Tipo 1 = Datos "anchos" (wide format) → Producto cartesiano
- Tipo 2 = Datos "largos" (long format) → Lectura directa

---

## 🎯 Propuesta de Solución

### Estrategia: Detección Automática Dual

El comando debe detectar automáticamente cuál estrategia usar para cada dominio temático:

```python
Por cada dominio temático:
  ¿Existe una columna con el nombre del dominio?
    SÍ → Estrategia COLUMNA (leer valores de esa columna)
    NO → Estrategia HEADER (buscar nombres de desagregaciones en headers)
```

### Implementación Propuesta

#### Paso 1: Nueva función de detección

```python
def detectar_ubicacion_dominio_tematico(self, dominio, headers, fila_dict):
    """
    Detecta si un dominio temático está en columnas o headers.
    
    Returns:
        dict: {
            'tipo': 'columna' | 'header',
            'columna': str | None,  # Nombre de la columna si tipo='columna'
            'confianza': float      # 0.0 - 1.0
        }
    """
    dominio_nombre_lower = dominio.nombre.lower()
    
    # OPCIÓN 1: ¿Hay una columna con el nombre exacto o muy similar del dominio?
    for columna in headers:
        if dominio_nombre_lower in columna.lower():
            # Verificar que los valores de esa columna coincidan con desagregaciones
            valores_columna = set(str(fila_dict[columna]).lower() for fila in todas_las_filas)
            desagregaciones_bd = set(d.nombre.lower() for d in dominio.desagregaciones.all())
            
            coincidencias = valores_columna.intersection(desagregaciones_bd)
            porcentaje = len(coincidencias) / len(valores_columna) if valores_columna else 0
            
            if porcentaje > 0.5:  # Más del 50% de coincidencia
                return {
                    'tipo': 'columna',
                    'columna': columna,
                    'confianza': porcentaje
                }
    
    # OPCIÓN 2: ¿Hay headers que contienen nombres de desagregaciones de este dominio?
    desagregaciones_bd = set(d.nombre.lower() for d in dominio.desagregaciones.all())
    headers_con_desag = 0
    
    for header in headers:
        header_lower = header.lower()
        for desag_nombre in desagregaciones_bd:
            if desag_nombre in header_lower:
                headers_con_desag += 1
                break
    
    if headers_con_desag > 0:
        return {
            'tipo': 'header',
            'columna': None,
            'confianza': headers_con_desag / len(headers)
        }
    
    # Por defecto: header (comportamiento actual)
    return {
        'tipo': 'header',
        'columna': None,
        'confianza': 0.0
    }
```

#### Paso 2: Modificar `obtener_desagregaciones_tematicas_posibles`

```python
def obtener_desagregaciones_tematicas_posibles(self, fila_dict, indicador, headers):
    """
    MODIFICADO: Distingue entre dominios en columnas vs headers
    """
    desagregaciones_por_dominio = {}
    
    for dominio in indicador.dominios_desagregacion_tematica.all():
        # NUEVO: Detectar ubicación del dominio
        ubicacion = self.detectar_ubicacion_dominio_tematico(dominio, headers, fila_dict)
        
        if ubicacion['tipo'] == 'columna':
            # NUEVO CASO: Dominio en columna
            columna = ubicacion['columna']
            valor_columna = fila_dict.get(columna)
            
            # Buscar desagregación que coincida con el valor
            try:
                desag = Desagregacion.objects.get(
                    dominio=dominio,
                    nombre__iexact=valor_columna
                )
                desagregaciones_por_dominio[dominio] = [desag]  # Solo UNA desagregación
            except Desagregacion.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'No se encontró desagregación "{valor_columna}" para dominio "{dominio.nombre}"')
                )
        
        else:
            # CASO EXISTENTE: Dominio en headers (búsqueda en encabezados)
            desagregaciones_posibles = []
            
            for desag in dominio.desagregaciones.all():
                for columna, valor in fila_dict.items():
                    nombre_low = (desag.nombre or '').lower()
                    if nombre_low and (
                        nombre_low in columna.lower() or
                        nombre_low in str(valor).lower()
                    ):
                        desagregaciones_posibles.append(desag)
                        break
            
            if desagregaciones_posibles:
                desagregaciones_por_dominio[dominio] = desagregaciones_posibles
    
    return desagregaciones_por_dominio
```

#### Paso 3: El resto del flujo funciona igual

El producto cartesiano sigue funcionando:
- Si un dominio está en **columna** → Retorna lista de 1 elemento
- Si un dominio está en **header** → Retorna lista de N elementos
- `itertools.product()` combina ambas listas correctamente

**Ejemplo:**
```python
# CSV Tipo 2 (columnas)
# Fila: Año=2024, Comuna=Cali, Sexo=Masculino, Edad=0-4, Valor=100

desagregaciones_por_dominio = {
    Dominio(Sexo): [Desagregacion(Masculino)],     # 1 elemento (de columna)
    Dominio(Edad): [Desagregacion(0-4)]            # 1 elemento (de columna)
}

# Producto cartesiano
combinaciones = itertools.product(
    [Masculino],  # 1 opción
    [0-4]         # 1 opción
)
# Resultado: [(Masculino, 0-4)] → 1 combinación

# Se crea 1 dato
```

**Ejemplo Mixto:**
```python
# CSV Mixto
# Fila: Año=2024, Comuna=Cali, Sexo=Masculino, H_0_4=10, H_5_9=20

desagregaciones_por_dominio = {
    Dominio(Sexo): [Desagregacion(Masculino)],              # 1 elemento (de columna)
    Dominio(Edad): [Desagregacion(0-4), Desagregacion(5-9)] # 2 elementos (de headers)
}

# Producto cartesiano
combinaciones = itertools.product(
    [Masculino],     # 1 opción
    [0-4, 5-9]       # 2 opciones
)
# Resultado: [(Masculino, 0-4), (Masculino, 5-9)] → 2 combinaciones
```

---

## 🔧 El Tema de las Fórmulas

### Problema con Fórmulas en Caso 2

En el **CSV Tipo 2** (columnas temáticas):
- No hay headers con combinaciones (ej: "Hombres_0_4")
- Solo hay una columna "Valor" con el dato final
- La fórmula no puede buscar "Hombres_0_4" porque no existe

### Solución: Detección de Columna de Valor

```python
def obtener_valor_para_combinacion(self, fila_dict, mapeo_columnas, combinacion_tematica, regla):
    """
    MODIFICADO: Detecta si es CSV tipo columnas y usa columna de valor directa
    """
    
    # NUEVO: ¿Es un CSV tipo columnas? (todas las desagregaciones temáticas son de 1 elemento)
    # Esto significa que cada fila ya representa UNA combinación específica
    es_csv_columnas = True  # Asumir que sí hasta que se demuestre lo contrario
    
    # Verificar si hay headers que coincidan con la combinación (CSV tipo headers)
    seleccion_por_dominio = {desag.dominio: desag for desag in combinacion_tematica}
    headers_match = []
    
    for header, mapping in mapeo_columnas.items():
        ok = True
        for dominio, desag_sel in seleccion_por_dominio.items():
            if mapping.get(dominio) != desag_sel:
                ok = False
                break
        if ok:
            headers_match.append(header)
            es_csv_columnas = False  # Hay headers que coinciden, es tipo headers
    
    if headers_match:
        # CSV TIPO 1 (headers): Comportamiento actual
        suma = 0.0
        usados = 0
        for h in headers_match:
            v = self._parsear_numero(fila_dict.get(h))
            if v is not None:
                suma += v
                usados += 1
        return suma if usados > 0 else None
    
    # CSV TIPO 2 (columnas): Usar columna de valor directa
    if es_csv_columnas:
        # Buscar columna de valor (primera que no sea fecha, geo o temática)
        columnas_excluidas = set()
        
        # Excluir columna de fecha
        if regla.columna_fecha:
            columnas_excluidas.add(regla.columna_fecha)
        
        # Excluir columnas geográficas (nombres de dominios)
        for dominio in self.indicador.dominios_desagregacion_geografica.all():
            for header in fila_dict.keys():
                if dominio.nombre.lower() in header.lower():
                    columnas_excluidas.add(header)
        
        # Excluir columnas temáticas (nombres de dominios)
        for dominio in self.indicador.dominios_desagregacion_tematica.all():
            for header in fila_dict.keys():
                if dominio.nombre.lower() in header.lower():
                    columnas_excluidas.add(header)
        
        # Buscar columna de valor
        for header in fila_dict.keys():
            if header not in columnas_excluidas:
                # Intentar parsear como número
                valor = self._parsear_numero(fila_dict[header])
                if valor is not None:
                    # Aplicar fórmula si existe
                    if regla.formula and regla.formula.strip() not in ("", "valor_celda"):
                        try:
                            valor = self._eval_formula_segura(
                                regla.formula.strip(), 
                                fila_dict, 
                                extra_vars={"valor_celda": valor}
                            )
                        except Exception:
                            pass
                    return float(valor) if valor is not None else None
    
    # Fallback: comportamiento por defecto
    columna = None
    if getattr(regla, 'columnas_fuente', None):
        columna = regla.columnas_fuente[0]
    return self.calcular_valor(fila_dict, regla, columna)
```

### Simplificación con Nuevo Campo en ReglaExtraccion (Opcional)

Si queremos ser más explícitos, podemos agregar un campo:

```python
class ReglaExtraccion(models.Model):
    # ... campos existentes ...
    
    # NUEVO CAMPO (Opcional)
    columna_valor = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Nombre de la columna que contiene el valor final (para CSV tipo columnas). Si se deja vacío, se detecta automáticamente."
    )
```

Y en el wizard, detectar automáticamente:
```python
# En paso de mapeo de columnas
columnas_excluidas = [fecha, geo1, geo2, sexo, edad]
columnas_restantes = [c for c in headers if c not in columnas_excluidas]

if len(columnas_restantes) == 1:
    columna_valor = columnas_restantes[0]
    # Pre-llenar en formulario
```

---

## 📊 Comparación de Estrategias

| Aspecto | CSV Tipo 1 (Headers) | CSV Tipo 2 (Columnas) |
|---------|---------------------|----------------------|
| **Formato** | Wide (ancho) | Long (largo) |
| **Filas → Datos** | 1 → N | 1 → 1 |
| **Desag. Temáticas** | En headers | En columnas |
| **Producto Cartesiano** | Necesario | No necesario (implícito) |
| **Búsqueda de Valor** | Por coincidencia de headers | Columna de valor directa |
| **Fórmula** | Sobre headers específicos | Sobre columna valor |
| **Uso de `columnas_fuente`** | Lista de headers con datos | Nombre de columna valor |

---

## ✅ Ventajas de la Solución Propuesta

### 1. **Detección Automática**
- No requiere configuración manual
- El wizard detecta el tipo automáticamente
- Sin intervención del usuario

### 2. **Sin Cambios en el Modelo (Inicialmente)**
- Funciona con los campos existentes de `ReglaExtraccion`
- `columnas_fuente` se adapta a ambos casos
- `formula` funciona igual en ambos casos

### 3. **Backward Compatible**
- CSV tipo 1 (actual) sigue funcionando igual
- No rompe procesamiento existente
- Migración gradual

### 4. **Semánticamente Correcto**
- Los dominios mantienen su tipo correcto (temático)
- No hay que hacer workarounds
- Clasificación conceptual intacta

### 5. **Flexible**
- Soporta CSV mixtos (algunos dominios en columnas, otros en headers)
- Se adapta a diferentes estructuras
- Extensible a futuros casos

---

## 🚀 Plan de Implementación

### Fase 1: Detección (Sin cambios en modelo)
1. Implementar `detectar_ubicacion_dominio_tematico()`
2. Modificar `obtener_desagregaciones_tematicas_posibles()`
3. Modificar `obtener_valor_para_combinacion()`
4. Probar con ambos tipos de CSV

### Fase 2: Integración con Wizard
1. En paso de "Verificar Desagregaciones":
   - Mostrar detección automática
   - Permitir ajustes manuales si es necesario
2. En paso de "Regla de Extracción":
   - Auto-detectar `columna_valor` para CSV tipo 2
   - Pre-llenar formulario

### Fase 3: Optimización (Opcional)
1. Agregar campo `columna_valor` a `ReglaExtraccion`
2. Agregar campo `mapeo_dominios_tematicos` (JSON) para cache de detección
3. Crear UI para visualizar/editar mapeo

### Fase 4: Diagnóstico Mejorado
1. En comando `diagnosticar_microdata`:
   - Mostrar detección de tipo de CSV
   - Mostrar ubicación de cada dominio
   - Advertir sobre ambigüedades

---

## 🎯 Resumen Ejecutivo

**Problema:** Desagregaciones temáticas en columnas no son detectadas.

**Causa:** El comando asume que temáticas están en headers.

**Solución:** Detección automática dual (columnas vs headers) por dominio.

**Implementación:** Modificar 3 funciones sin cambiar el modelo (inicialmente).

**Impacto:** Soporta ambos casos de uso sin intervención manual.

**Riesgo:** Bajo (backward compatible, sin cambios en BD).

**Esfuerzo:** Medio (3-4 horas de desarrollo + testing).

---

## 📝 Siguiente Paso

Una vez aprobada esta propuesta, proceder a:
1. Implementar `detectar_ubicacion_dominio_tematico()`
2. Crear tests con ambos tipos de CSV
3. Integrar con wizard
4. Actualizar documentación

**Pendiente de Decisión:**
- ¿Agregar campo `columna_valor` a `ReglaExtraccion`? (Opcional, mejora explicitez)
- ¿Agregar cache de detección en `ReglaExtraccion`? (Opcional, mejora performance)

---

**Fin del Documento**
