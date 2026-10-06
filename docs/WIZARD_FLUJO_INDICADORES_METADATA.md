# 📊 Wizard: Determinación de Indicadores y Carga de Metadata

## 🎯 Determinación del Indicador en Cada Flujo

### **FLUJO A: Con Microdata (Procesamiento Cartesiano)**

**Paso donde se determina:** `PASO_CONFIG_INDICADOR_A` (Paso 5A)

```python
# FormConfigIndicador - 2 opciones:

1. CREAR NUEVO INDICADOR
   - Campos requeridos:
     * codigo_indicador (opcional)
     * nombre (requerido)
     * sigla (opcional)
     * subtema (requerido - FK a MenuSubtema)
   
   - Resultado:
     indicador = Indicador.objects.create(
         codigo=paso_5_data.get('codigo_indicador', ''),
         nombre=paso_5_data['nombre'],
         sigla=paso_5_data.get('sigla', ''),
         subtema=paso_5_data['subtema'],
         activo=True
     )

2. ASOCIAR INDICADOR EXISTENTE
   - Campo: indicador_existente (ModelChoiceField)
   - Dropdown con todos los indicadores activos
   
   - Resultado:
     indicador = paso_5_data['indicador_existente']
     indicador.datos.all().delete()  # Limpia datos anteriores
```

**Flujo completo:**
```
Paso 1: Selección de fuente → Detecta flujo_a
Paso 2A: Preview Microdata
Paso 3A: Configurar Microdata (crear/asociar)
Paso 4A: Metadata de Variables ← PARSEA metadata_variables.csv
Paso 5A: Configurar Indicador ← AQUÍ SE DETERMINA EL INDICADOR
Paso 6A: Verificar Desagregaciones
Paso 7A: Crear Regla de Extracción
Paso 8A: Diagnóstico
Procesamiento: Crea/asocia indicador + ReglaExtraccion + Procesamiento cartesiano
```

---

### **FLUJO B: Solo Serie de Datos**

**Paso donde se determina:** `PASO_CONFIG_INDICADOR_B` (Paso 3B)

```python
# Mismo FormConfigIndicador - 2 opciones:

1. CREAR NUEVO INDICADOR
2. ASOCIAR INDICADOR EXISTENTE

# Diferencia con Flujo A:
# - Se determina MÁS TEMPRANO (paso 3 vs paso 5)
# - Luego carga metadata desde CargaSerieIndicador
```

**Flujo completo:**
```
Paso 1: Selección de fuente → Detecta flujo_b
Paso 2B: Preview Serie
Paso 3B: Configurar Indicador ← AQUÍ SE DETERMINA EL INDICADOR
Paso 4B: Cargar Metadata ← PARSEA metadata.csv
Paso 5B: Verificar Desagregaciones
Paso 6B: Mapeo de Columnas
Paso 7B: Confirmación
Procesamiento: Crea/asocia indicador + Importación directa
```

---

### **FLUJO C: Microdata + Serie (Completo)**

**Paso donde se determina:** `PASO_CONFIG_INDICADOR_C` (Paso 5C)

```python
# Mismo proceso que Flujo A
# Pero además carga metadata desde CargaSerieIndicador

1. Crea o asocia indicador (paso 5C)
2. Carga metadata de variables desde CargaMicrodata
3. Carga metadata del indicador desde CargaSerieIndicador
4. Procesa microdata con producto cartesiano
5. Valida con serie original
```

**Flujo completo:**
```
Paso 1: Selección de fuente → Detecta flujo_c
Paso 2C: Preview Ambos archivos
Paso 3C: Configurar Microdata
Paso 4C: Metadata de Variables ← PARSEA metadata_variables.csv
Paso 5C: Configurar Indicador ← AQUÍ SE DETERMINA EL INDICADOR
Paso 6C: Cargar Metadata Indicador ← PARSEA metadata.csv
Paso 7C: Verificar Desagregaciones
Paso 8C: Crear Regla de Extracción
Paso 9C: Diagnóstico
Paso 10C: Validar con Serie
Procesamiento: Completo con validación
```

---

### **FLUJO D: Actualizar Existente**

**Paso donde se determina:** `PASO_SELECCIONAR_INDICADOR` (Paso 2D)

```python
# FormSeleccionarIndicador - Solo 1 opción:

SELECCIONAR INDICADOR EXISTENTE
- Campo: indicador (ModelChoiceField)
- Dropdown con TODOS los indicadores (no solo activos)
- Campo de búsqueda: buscar_nombre

# Resultado:
indicador = paso_2_data['indicador']  # Ya existe, no se crea

# Luego decide qué hacer con los datos:
accion_datos = paso_5_data['accion_datos']
- 'mantener' → No toca datos existentes
- 'reemplazar' → indicador.datos.all().delete() + carga nuevos
- 'agregar' → Agrega nuevos sin eliminar existentes
```

**Flujo completo:**
```
Paso 1: Selección de fuente → Detecta flujo_d
Paso 2D: Seleccionar Indicador ← AQUÍ SE DETERMINA EL INDICADOR
Paso 3D: Seleccionar Carga nueva (serie o microdata)
Paso 4D: Comparar Metadata (diff viewer)
Paso 5D: Confirmar Cambios (mantener/reemplazar/agregar)
Procesamiento: Actualización inteligente
```

---

## 📋 Carga de Metadata - Estado Actual

### **✅ LO QUE YA FUNCIONA:**

#### **1. Parseo de Metadata**

**En `utils_wizard.py`:**

```python
class ParseadorMetadata:
    @staticmethod
    def parsear_metadata_indicador(archivo_path: str) -> Dict[str, Any]:
        """
        Parsea metadata.csv del indicador
        Formato esperado: clave,valor
        
        Returns:
            {
                'exitoso': True,
                'metadata': {
                    'Codigo_Indicador': 'IND-001',
                    'Sigla': 'TD',
                    'Nombre_Indicador': 'Tasa de Desempleo',
                    'Definiciones_Conceptos': '...',
                    'Formula': '...',
                    ...
                },
                'campos_encontrados': 15
            }
        """
    
    @staticmethod
    def parsear_metadata_variables(archivo_path: str) -> Dict[str, Any]:
        """
        Parsea metadata_variables.csv
        Formato esperado: nombre_variable,tipo,descripcion,...
        
        Returns:
            {
                'exitoso': True,
                'variables': [
                    {
                        'nombre_variable': 'edad',
                        'tipo': 'numerico',
                        'descripcion': 'Edad del individuo',
                        ...
                    },
                    ...
                ],
                'total_variables': 10
            }
        """
```

#### **2. Aplicación de Metadata**

**Nueva clase `AplicadorMetadata` en `utils_wizard.py`:**

```python
class AplicadorMetadata:
    @staticmethod
    def aplicar_metadata_indicador(indicador, metadata_dict: Dict[str, str]):
        """
        Aplica metadata parseada a un indicador
        Basado en cargar_ficha_tecnica.py
        
        Campos que actualiza:
        - codigo_indicador, sigla, grupo_indicador
        - descripcion, definiciones_conceptos, objetivo, justificacion
        - metodo_medicion, formula_ficha, variables
        - unidad_medida, valores_referencia, linea_base
        - desagregacion_tematica_texto, desagregacion_geografica_texto
        - periodicidad, fuente_datos, responsable, observaciones
        - fecha_elaboracion, fecha_actualizacion
        
        Returns:
            {
                'exitoso': True,
                'campos_actualizados': ['sigla', 'descripcion', ...],
                'total_campos': 12,
                'errores': []
            }
        """
    
    @staticmethod
    def aplicar_metadata_variables(microdata, variables_list: List[Dict]):
        """
        Aplica metadata de variables a una microdata
        Basado en crear_microdata_y_variables.py
        
        Crea/actualiza VariableMicrodata:
        - nombre, tipo, descripcion
        - unidad_medida, valores_permitidos
        - es_obligatoria
        
        Returns:
            {
                'exitoso': True,
                'variables_creadas': 5,
                'variables_actualizadas': 3,
                'total_procesadas': 8,
                'errores': []
            }
        """
```

---

### **🔧 CÓMO SE USA EN EL WIZARD:**

#### **Flujo A - Paso 4A (Metadata Variables):**

```python
# En wizard_admin_unificado.py - get_context_data()

from .utils_wizard import ParseadorMetadata

carga_microdata = CargaMicrodata.objects.get(id=carga_microdata_id)

if carga_microdata.archivo_metadata_variables_csv:
    # 1. PARSEAR
    resultado = ParseadorMetadata.parsear_metadata_variables(
        carga_microdata.archivo_metadata_variables_csv.path
    )
    
    # 2. MOSTRAR EN TEMPLATE
    context['variables_detectadas'] = resultado['variables']
    context['total_variables'] = resultado['total_variables']
    
    # 3. APLICAR (en procesamiento)
    # En _procesar_flujo_a():
    from .utils_wizard import AplicadorMetadata
    
    resultado_aplicacion = AplicadorMetadata.aplicar_metadata_variables(
        microdata, 
        resultado['variables']
    )
```

#### **Flujo B - Paso 4B (Metadata Indicador):**

```python
# En wizard_admin_unificado.py - get_context_data()

from .utils_wizard import ParseadorMetadata

carga_serie = CargaSerieIndicador.objects.get(id=carga_serie_id)

if carga_serie.archivo_metadata_csv:
    # 1. PARSEAR
    resultado = ParseadorMetadata.parsear_metadata_indicador(
        carga_serie.archivo_metadata_csv.path
    )
    
    # 2. MOSTRAR EN TEMPLATE
    context['metadata_detectada'] = resultado['metadata']
    context['campos_encontrados'] = resultado['campos_encontrados']
    
    # 3. APLICAR (en procesamiento)
    # En _procesar_flujo_b():
    from .utils_wizard import AplicadorMetadata
    
    resultado_aplicacion = AplicadorMetadata.aplicar_metadata_indicador(
        indicador,
        resultado['metadata']
    )
```

---

### **⚠️ LO QUE FALTA POR INTEGRAR:**

#### **1. Aplicar metadata en el procesamiento**

Actualmente el wizard **parsea y muestra** la metadata, pero **NO la aplica automáticamente**.

**Necesitas agregar en `_procesar_flujo_a()` y `_procesar_flujo_b()`:**

```python
# Después de crear el indicador:

# Aplicar metadata del indicador (si existe)
if metadata_parseada:
    from .utils_wizard import AplicadorMetadata
    
    resultado = AplicadorMetadata.aplicar_metadata_indicador(
        indicador,
        metadata_parseada
    )
    
    if not resultado['exitoso']:
        # Log errores pero no fallar
        print(f"Advertencia: {resultado.get('error')}")

# Aplicar metadata de variables (si existe)
if variables_parseadas:
    resultado = AplicadorMetadata.aplicar_metadata_variables(
        microdata,
        variables_parseadas
    )
```

#### **2. Guardar metadata parseada en storage**

Para poder usarla en el procesamiento:

```python
# En get_context_data() después de parsear:

# Guardar en storage para usar en procesamiento
self.storage.extra_data['metadata_indicador'] = resultado['metadata']
self.storage.extra_data['variables_microdata'] = resultado['variables']
```

#### **3. Recuperar y aplicar en procesamiento:**

```python
# En _procesar_flujo_a() o _procesar_flujo_b():

metadata_indicador = self.storage.extra_data.get('metadata_indicador')
variables_microdata = self.storage.extra_data.get('variables_microdata')

if metadata_indicador:
    AplicadorMetadata.aplicar_metadata_indicador(indicador, metadata_indicador)

if variables_microdata:
    AplicadorMetadata.aplicar_metadata_variables(microdata, variables_microdata)
```

---

## 📊 Resumen Visual

```
┌─────────────────────────────────────────────────────────────┐
│                    FLUJO DE METADATA                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. CARGA DE ARCHIVOS                                       │
│     ├─ CargaMicrodata.archivo_metadata_variables_csv        │
│     └─ CargaSerieIndicador.archivo_metadata_csv             │
│                                                             │
│  2. PARSEO (en get_context_data)                            │
│     ├─ ParseadorMetadata.parsear_metadata_variables()       │
│     │  └─ Returns: {'variables': [...], 'total': 10}        │
│     └─ ParseadorMetadata.parsear_metadata_indicador()       │
│        └─ Returns: {'metadata': {...}, 'campos': 15}        │
│                                                             │
│  3. MOSTRAR EN TEMPLATE                                     │
│     ├─ context['variables_detectadas']                      │
│     └─ context['metadata_detectada']                        │
│                                                             │
│  4. GUARDAR EN STORAGE (FALTA IMPLEMENTAR)                  │
│     ├─ self.storage.extra_data['metadata_indicador']        │
│     └─ self.storage.extra_data['variables_microdata']       │
│                                                             │
│  5. APLICAR EN PROCESAMIENTO (FALTA IMPLEMENTAR)            │
│     ├─ AplicadorMetadata.aplicar_metadata_indicador()       │
│     │  └─ Actualiza 19 campos del indicador                 │
│     └─ AplicadorMetadata.aplicar_metadata_variables()       │
│        └─ Crea/actualiza VariableMicrodata                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ Comandos Existentes (Referencia)

### **cargar_ficha_tecnica.py**
```bash
python manage.py cargar_ficha_tecnica --csv-path=metadata.csv
```
- Carga metadata de indicadores desde CSV
- Busca indicador por subtema
- Actualiza 19 campos

### **cargar_ficha_tecnica_microdata.py**
```bash
python manage.py cargar_ficha_tecnica_microdata --microdata-id=1
```
- Carga metadata de microdata
- Actualiza campos descriptivos

### **crear_microdata_y_variables.py**
```bash
python manage.py crear_microdata_y_variables --csv-path=variables.csv
```
- Crea microdata y sus variables
- Parsea metadata_variables.csv

---

## 🎯 Próximos Pasos

1. **Guardar metadata parseada en storage** (5 min)
2. **Aplicar metadata en procesamiento** (10 min)
3. **Testing con archivos reales** (30 min)
4. **Documentar formato esperado de CSV** (15 min)

**Total estimado: 1 hora**
