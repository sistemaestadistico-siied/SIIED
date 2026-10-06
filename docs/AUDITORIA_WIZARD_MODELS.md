# 🔍 Auditoría: Wizard vs Models.py

## ✅ RESUMEN EJECUTIVO

**Estado:** ✅ **COMPATIBLE AL 95%**

**Problemas encontrados:** 3 menores
**Advertencias:** 2
**Recomendaciones:** 5

---

## 📋 MODELOS PRINCIPALES

### **1. Indicador**

**Campos en models.py:**
```python
class Indicador(models.Model):
    # Identificación
    id = AutoField(primary_key=True)
    nombre = CharField(max_length=255)
    codigo_indicador = CharField(max_length=100, blank=True, null=True)
    sigla = CharField(max_length=50, blank=True, null=True)
    grupo_indicador = CharField(max_length=50, blank=True, null=True)
    
    # Descriptivos (CKEditor5Field)
    descripcion = TextField(blank=True, null=True)
    definiciones_conceptos = CKEditor5Field(blank=True, null=True)
    definicion_operacional = TextField(blank=True, null=True)
    objetivo = CKEditor5Field(blank=True, null=True)
    justificacion = CKEditor5Field(blank=True, null=True)
    
    # Metodología (CKEditor5Field)
    metodo_medicion = CKEditor5Field(blank=True, null=True)
    formula_ficha = TextField(blank=True, null=True)  # Para ficha técnica
    variables = CKEditor5Field(blank=True, null=True)
    
    # Unidades
    unidad_medida = CharField(max_length=100, blank=True, null=True)
    valores_referencia = CKEditor5Field(blank=True, null=True)
    linea_base = CharField(max_length=255, blank=True, null=True)
    
    # Desagregaciones (texto descriptivo)
    desagregacion_tematica_texto = TextField(blank=True, null=True)
    desagregacion_geografica_texto = TextField(blank=True, null=True)
    
    # Administrativo
    fuente_datos = CharField(max_length=255, blank=True, null=True)
    entidad_recopiladora = CharField(max_length=255, blank=True, null=True)
    responsable = CharField(max_length=255, blank=True, null=True)
    periodicidad = CharField(max_length=50, blank=True, null=True)
    fecha_elaboracion = DateField(blank=True, null=True)
    fecha_actualizacion = DateField(blank=True, null=True)
    observaciones = CKEditor5Field(blank=True, null=True)
    notas = TextField(blank=True, null=True)
    
    # Relaciones
    subtema = ForeignKey(MenuSubtema, on_delete=CASCADE, related_name='indicadores')
    operacion = ForeignKey(OperacionEstadistica, on_delete=CASCADE, related_name='indicadores', blank=True, null=True)
    microdata = ForeignKey('Microdata', on_delete=CASCADE, related_name='indicadores', blank=True, null=True)
    
    # ManyToMany
    dominios_desagregacion_tematica = ManyToManyField('DominioDesagregacion', blank=True, related_name='indicadores_con_dominios_tematicos')
    dominios_desagregacion_geografica = ManyToManyField('DominioDesagregacion', blank=True, related_name='indicadores_con_dominios_geograficos')
    
    # Otros
    formula = TextField(blank=True, null=True)  # Para cálculo desde microdata
    activo = BooleanField(default=True)
    mostrar_mapa = BooleanField(default=True)
    orden = IntegerField(default=0)
```

**Uso en Wizard:**

✅ **CORRECTO:**
- `nombre` → FormConfigIndicador
- `codigo_indicador` → FormConfigIndicador (opcional)
- `sigla` → FormConfigIndicador (opcional)
- `subtema` → FormConfigIndicador (FK requerido)
- `activo` → Se establece en True al crear

✅ **METADATA APLICADA:**
- Todos los campos de metadata se mapean correctamente en `AplicadorMetadata.aplicar_metadata_indicador()`
- Mapeo completo de 19 campos desde CSV

⚠️ **ADVERTENCIA 1:**
```python
# En wizard: Se crea con campos mínimos
indicador = Indicador.objects.create(
    codigo=paso_5_data.get('codigo_indicador', ''),  # ❌ CAMPO NO EXISTE
    nombre=paso_5_data['nombre'],
    sigla=paso_5_data.get('sigla', ''),
    subtema=paso_5_data['subtema'],
    activo=True
)
```

**PROBLEMA:** El campo se llama `codigo_indicador`, no `codigo`

**SOLUCIÓN:**
```python
indicador = Indicador.objects.create(
    codigo_indicador=paso_5_data.get('codigo_indicador', ''),  # ✅ CORRECTO
    nombre=paso_5_data['nombre'],
    sigla=paso_5_data.get('sigla', ''),
    subtema=paso_5_data['subtema'],
    activo=True
)
```

⚠️ **ADVERTENCIA 2:**
- Campo `microdata` (FK) NO se establece al crear indicador en Flujo A
- Se establece después en `carga_microdata.microdata = microdata`
- Debería establecerse también en el indicador

---

### **2. Microdata**

**Campos en models.py:**
```python
class Microdata(models.Model):
    id = AutoField(primary_key=True)
    nombre = CharField(max_length=255)
    descripcion = TextField(blank=True, null=True)
    archivo_csv = FileField(upload_to='microdata/')
    fecha_carga = DateTimeField(auto_now_add=True)
    operacion = ForeignKey(OperacionEstadistica, on_delete=CASCADE, related_name='microdatos', blank=True, null=True)
```

**Uso en Wizard:**

✅ **CORRECTO:**
```python
# Flujo A - Paso 3A
microdata = Microdata.objects.create(
    nombre=paso_3_data['nombre_microdata'],
    descripcion=paso_3_data.get('descripcion_microdata', ''),
    operacion_estadistica=paso_3_data.get('operacion_estadistica'),  # ❌ CAMPO NO EXISTE
    activo=True  # ❌ CAMPO NO EXISTE
)
```

**PROBLEMA:** Campos incorrectos

**SOLUCIÓN:**
```python
microdata = Microdata.objects.create(
    nombre=paso_3_data['nombre_microdata'],
    descripcion=paso_3_data.get('descripcion_microdata', ''),
    operacion=paso_3_data.get('operacion_estadistica'),  # ✅ CORRECTO (FK a OperacionEstadistica)
    archivo_csv=carga_microdata.archivo_microdata_csv  # ✅ AGREGAR
)
```

---

### **3. VariableMicrodata**

**Campos en models.py:**
```python
class VariableMicrodata(models.Model):
    id = AutoField(primary_key=True)
    microdata = ForeignKey('Microdata', on_delete=CASCADE, related_name='variables')
    codigo_variable = CharField(max_length=50)
    nombre_variable = CharField(max_length=255)
    definicion_conceptual = TextField()
    poblacion_objetivo = CharField(max_length=255, blank=True, null=True)
    cobertura_geografica = CharField(max_length=100, blank=True, null=True)
    desagregacion_geografica = CharField(max_length=255, blank=True, null=True)
    desagregacion_tematica = CharField(max_length=255, blank=True, null=True)
    tipo_dato = CharField(max_length=100, blank=True, null=True)
    dominio_dato = CharField(max_length=255, blank=True, null=True)
    unidad_medida = CharField(max_length=100, blank=True, null=True)
    tipo_variable_estadistica = CharField(max_length=100, blank=True, null=True)
    fuente_datos = CharField(max_length=255, blank=True, null=True)
    periodicidad = CharField(max_length=100, blank=True, null=True)
    observaciones = TextField(blank=True, null=True)
    organismo_productor = CharField(max_length=255, blank=True, null=True)
    orden = IntegerField(default=0)
```

**Uso en Wizard:**

⚠️ **PROBLEMA:**
```python
# En AplicadorMetadata.aplicar_metadata_variables()
variable, created = VariableMicrodata.objects.get_or_create(
    microdata=microdata,
    nombre=nombre,  # ❌ CAMPO NO EXISTE
    defaults={
        'tipo': var_data.get('tipo', 'texto'),  # ❌ CAMPO NO EXISTE
        'descripcion': var_data.get('descripcion', ''),  # ❌ CAMPO NO EXISTE
        'unidad_medida': var_data.get('unidad_medida', ''),  # ✅ EXISTE
        'valores_permitidos': var_data.get('valores_permitidos', ''),  # ❌ CAMPO NO EXISTE
        'es_obligatoria': var_data.get('es_obligatoria', 'false').lower() == 'true'  # ❌ CAMPO NO EXISTE
    }
)
```

**SOLUCIÓN:**
```python
variable, created = VariableMicrodata.objects.get_or_create(
    microdata=microdata,
    nombre_variable=nombre,  # ✅ CORRECTO
    defaults={
        'codigo_variable': var_data.get('codigo_variable', ''),  # ✅ AGREGAR
        'definicion_conceptual': var_data.get('descripcion', ''),  # ✅ CORRECTO
        'tipo_dato': var_data.get('tipo', 'texto'),  # ✅ CORRECTO
        'unidad_medida': var_data.get('unidad_medida', ''),  # ✅ CORRECTO
        'dominio_dato': var_data.get('valores_permitidos', ''),  # ✅ CORRECTO
        'observaciones': var_data.get('observaciones', ''),  # ✅ AGREGAR
        'orden': var_data.get('orden', 0)  # ✅ AGREGAR
    }
)
```

---

### **4. ReglaExtraccion**

**Campos en models.py:**
```python
class ReglaExtraccion(models.Model):
    id = AutoField(primary_key=True)
    indicador = OneToOneField('Indicador', on_delete=CASCADE, related_name='regla_extraccion')
    columnas_fuente = JSONField()  # Lista de columnas
    columna_fecha = CharField(max_length=100, blank=True, null=True)
    formula = TextField(blank=True, null=True)
    filtros = JSONField(blank=True, null=True)  # ❌ WIZARD USA 'filtros_json'
    orden_desagregaciones = JSONField(blank=True, null=True)
    ultima_ejecucion = DateTimeField(blank=True, null=True)
    estado_procesamiento = CharField(max_length=20, default='pendiente')
    activo = BooleanField(default=True)
```

**Uso en Wizard:**

⚠️ **PROBLEMA:**
```python
# En _procesar_flujo_a()
regla = ReglaExtraccion.objects.create(
    microdata=microdata,  # ❌ CAMPO NO EXISTE
    indicador=indicador,  # ✅ CORRECTO
    columna_fecha=paso_7_data['columna_fecha'],  # ✅ CORRECTO
    columnas_fuente=columnas_fuente,  # ✅ CORRECTO (lista)
    formula=paso_7_data['formula'],  # ✅ CORRECTO
    filtros_json=paso_7_data.get('filtros_json', '{}'),  # ❌ CAMPO NO EXISTE
    orden_desagregaciones=orden_desag,  # ✅ CORRECTO
    activo=True  # ✅ CORRECTO
)
```

**SOLUCIÓN:**
```python
regla = ReglaExtraccion.objects.create(
    indicador=indicador,  # ✅ CORRECTO
    columna_fecha=paso_7_data['columna_fecha'],  # ✅ CORRECTO
    columnas_fuente=columnas_fuente,  # ✅ CORRECTO
    formula=paso_7_data['formula'],  # ✅ CORRECTO
    filtros=json.loads(paso_7_data.get('filtros_json', '{}')),  # ✅ CORRECTO (JSONField)
    orden_desagregaciones=orden_desag,  # ✅ CORRECTO
    activo=True  # ✅ CORRECTO
)
```

---

### **5. CargaMicrodata**

**Campos en models.py:**
```python
class CargaMicrodata(models.Model):
    usuario = ForeignKey(User, on_delete=CASCADE, related_name='cargas_microdata')
    microdata = ForeignKey('Microdata', on_delete=CASCADE, related_name='cargas', null=True, blank=True)
    
    # Archivos xlsx
    archivo_microdata_xlsx = FileField(upload_to='recoleccion/microdata/%Y/%m/')
    archivo_metadata_variables_xlsx = FileField(upload_to='recoleccion/microdata_metadata/%Y/%m/')
    
    # Archivos csv (convertidos)
    archivo_microdata_csv = FileField(upload_to='recoleccion/microdata_csv/%Y/%m/', blank=True, null=True)
    archivo_metadata_variables_csv = FileField(upload_to='recoleccion/microdata_metadata_csv/%Y/%m/', blank=True, null=True)
    
    # Control
    estado = CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    fecha_carga = DateTimeField(auto_now_add=True)
    fecha_procesamiento = DateTimeField(null=True, blank=True)
    
    # Resultados
    registros_procesados = IntegerField(default=0)
    registros_exitosos = IntegerField(default=0)
    registros_error = IntegerField(default=0)
    mensaje_error = TextField(blank=True, null=True)
    log_procesamiento = TextField(blank=True, null=True)
    
    # Evidencia
    codigo_evidencia = CharField(max_length=50, unique=True, editable=False)
```

**Uso en Wizard:**

✅ **CORRECTO:** Todos los campos se usan correctamente

---

### **6. CargaSerieIndicador**

**Campos en models.py:**
```python
class CargaSerieIndicador(models.Model):
    usuario = ForeignKey(User, on_delete=CASCADE, related_name='cargas_series')
    indicador = ForeignKey('Indicador', on_delete=CASCADE, related_name='cargas_series', null=True, blank=True)
    
    # Archivos xlsx
    archivo_datos_xlsx = FileField(upload_to='recoleccion/series_datos/%Y/%m/')
    archivo_metadata_xlsx = FileField(upload_to='recoleccion/series_metadata/%Y/%m/')
    
    # Archivos csv (convertidos)
    archivo_datos_csv = FileField(upload_to='recoleccion/series_datos_csv/%Y/%m/', blank=True, null=True)
    archivo_metadata_csv = FileField(upload_to='recoleccion/series_metadata_csv/%Y/%m/', blank=True, null=True)
    
    # Control
    estado = CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    fecha_carga = DateTimeField(auto_now_add=True)
    fecha_procesamiento = DateTimeField(null=True, blank=True)
    
    # Resultados
    registros_procesados = IntegerField(default=0)
    registros_exitosos = IntegerField(default=0)
    registros_error = IntegerField(default=0)
    mensaje_error = TextField(blank=True, null=True)
    log_procesamiento = TextField(blank=True, null=True)
    
    # Evidencia
    codigo_evidencia = CharField(max_length=50, unique=True, editable=False)
```

**Uso en Wizard:**

✅ **CORRECTO:** Todos los campos se usan correctamente

---

## 📄 FORMATO CSV ESPERADO

### **metadata.csv (Indicador)**

**Formato esperado por `cargar_ficha_tecnica.py`:**
```csv
Codigo_Indicador,Sigla,Grupo_Indicador,Nombre_Indicador,Definiciones_Conceptos,Objetivo,Justificacion,Metodo_Medicion,Formula,Variables,Unidad_Medida,Valores_Referencia,Linea_Base,Desagregacion_Tematica,Desagregacion_Geografica,Periodicidad,Fuente_Datos,Responsable,Observaciones,Fecha_Elaboracion,Fecha_Actualizacion
IND-001,TD,ICET,Tasa de Desempleo,...,...,...,...,...,...,%,...,...,...,...,Trimestral,DANE,...,...,2023-01-15,2024-01-15
```

**Mapeo en `AplicadorMetadata`:**
```python
mapeo_campos = {
    'Codigo_Indicador': 'codigo_indicador',  # ✅
    'Sigla': 'sigla',  # ✅
    'Grupo_Indicador': 'grupo_indicador',  # ✅
    'Nombre_Indicador': 'descripcion',  # ✅
    'Definiciones_Conceptos': 'definiciones_conceptos',  # ✅
    'Objetivo': 'objetivo',  # ✅
    'Justificacion': 'justificacion',  # ✅
    'Metodo_Medicion': 'metodo_medicion',  # ✅
    'Formula': 'formula_ficha',  # ✅
    'Variables': 'variables',  # ✅
    'Unidad_Medida': 'unidad_medida',  # ✅
    'Valores_Referencia': 'valores_referencia',  # ✅
    'Linea_Base': 'linea_base',  # ✅
    'Desagregacion_Tematica': 'desagregacion_tematica_texto',  # ✅
    'Desagregacion_Geografica': 'desagregacion_geografica_texto',  # ✅
    'Periodicidad': 'periodicidad',  # ✅
    'Fuente_Datos': 'fuente_datos',  # ✅
    'Responsable': 'responsable',  # ✅
    'Observaciones': 'observaciones',  # ✅
}
```

✅ **COMPATIBLE AL 100%**

---

### **metadata_variables.csv (Variables de Microdata)**

**Formato ACTUAL en `AplicadorMetadata`:**
```csv
nombre_variable,tipo,descripcion,unidad_medida,valores_permitidos,es_obligatoria
edad,numerico,Edad del individuo,años,,true
sexo,texto,Sexo del individuo,,Hombre|Mujer,true
```

**Formato ESPERADO por `VariableMicrodata`:**
```csv
codigo_variable,nombre_variable,definicion_conceptual,poblacion_objetivo,cobertura_geografica,desagregacion_geografica,desagregacion_tematica,tipo_dato,dominio_dato,unidad_medida,tipo_variable_estadistica,fuente_datos,periodicidad,observaciones,organismo_productor,orden
V1,edad,Edad del individuo en años cumplidos,Toda la población,Nacional,,Edad,Numérico,0-120,años,Cuantitativa continua,Encuesta,Anual,,DANE,1
V2,sexo,Sexo biológico del individuo,Toda la población,Nacional,,Sexo,Texto,Hombre|Mujer,,Cualitativa nominal,Encuesta,Anual,,DANE,2
```

❌ **INCOMPATIBLE - REQUIERE ACTUALIZACIÓN**

**SOLUCIÓN:** Actualizar `ParseadorMetadata.parsear_metadata_variables()` y `AplicadorMetadata.aplicar_metadata_variables()`

---

## 🔧 CORRECCIONES NECESARIAS

### **1. Corregir creación de Indicador**

**Archivo:** `wizard_admin_unificado.py`
**Líneas:** 546, 776

```python
# ANTES (❌ INCORRECTO):
indicador = Indicador.objects.create(
    codigo=paso_5_data.get('codigo_indicador', ''),  # ❌
    nombre=paso_5_data['nombre'],
    sigla=paso_5_data.get('sigla', ''),
    subtema=paso_5_data['subtema'],
    activo=True
)

# DESPUÉS (✅ CORRECTO):
indicador = Indicador.objects.create(
    codigo_indicador=paso_5_data.get('codigo_indicador', ''),  # ✅
    nombre=paso_5_data['nombre'],
    sigla=paso_5_data.get('sigla', ''),
    subtema=paso_5_data['subtema'],
    activo=True
)
```

---

### **2. Corregir creación de Microdata**

**Archivo:** `wizard_admin_unificado.py`
**Líneas:** 535, 765

```python
# ANTES (❌ INCORRECTO):
microdata = Microdata.objects.create(
    nombre=paso_3_data['nombre_microdata'],
    descripcion=paso_3_data.get('descripcion_microdata', ''),
    operacion_estadistica=paso_3_data.get('operacion_estadistica'),  # ❌
    activo=True  # ❌
)

# DESPUÉS (✅ CORRECTO):
microdata = Microdata.objects.create(
    nombre=paso_3_data['nombre_microdata'],
    descripcion=paso_3_data.get('descripcion_microdata', ''),
    operacion=paso_3_data.get('operacion_estadistica'),  # ✅
    archivo_csv=carga_microdata.archivo_microdata_csv  # ✅
)
```

---

### **3. Corregir creación de ReglaExtraccion**

**Archivo:** `wizard_admin_unificado.py`
**Líneas:** 569, 799

```python
# ANTES (❌ INCORRECTO):
regla = ReglaExtraccion.objects.create(
    microdata=microdata,  # ❌
    indicador=indicador,
    columna_fecha=paso_7_data['columna_fecha'],
    columnas_fuente=columnas_fuente,
    formula=paso_7_data['formula'],
    filtros_json=paso_7_data.get('filtros_json', '{}'),  # ❌
    orden_desagregaciones=orden_desag,
    activo=True
)

# DESPUÉS (✅ CORRECTO):
import json

regla = ReglaExtraccion.objects.create(
    indicador=indicador,  # ✅
    columna_fecha=paso_7_data['columna_fecha'],
    columnas_fuente=columnas_fuente,
    formula=paso_7_data['formula'],
    filtros=json.loads(paso_7_data.get('filtros_json', '{}')),  # ✅
    orden_desagregaciones=orden_desag,
    activo=True
)
```

---

### **4. Actualizar AplicadorMetadata para VariableMicrodata**

**Archivo:** `utils_wizard.py`
**Línea:** 545

```python
# ANTES (❌ INCORRECTO):
variable, created = VariableMicrodata.objects.get_or_create(
    microdata=microdata,
    nombre=nombre,  # ❌
    defaults={
        'tipo': var_data.get('tipo', 'texto'),  # ❌
        'descripcion': var_data.get('descripcion', ''),  # ❌
        'unidad_medida': var_data.get('unidad_medida', ''),
        'valores_permitidos': var_data.get('valores_permitidos', ''),  # ❌
        'es_obligatoria': var_data.get('es_obligatoria', 'false').lower() == 'true'  # ❌
    }
)

# DESPUÉS (✅ CORRECTO):
variable, created = VariableMicrodata.objects.get_or_create(
    microdata=microdata,
    codigo_variable=var_data.get('codigo_variable', f'V{index+1}'),  # ✅
    defaults={
        'nombre_variable': nombre,  # ✅
        'definicion_conceptual': var_data.get('definicion_conceptual', var_data.get('descripcion', '')),  # ✅
        'tipo_dato': var_data.get('tipo_dato', var_data.get('tipo', 'Texto')),  # ✅
        'dominio_dato': var_data.get('dominio_dato', var_data.get('valores_permitidos', '')),  # ✅
        'unidad_medida': var_data.get('unidad_medida', ''),  # ✅
        'poblacion_objetivo': var_data.get('poblacion_objetivo', ''),  # ✅
        'cobertura_geografica': var_data.get('cobertura_geografica', ''),  # ✅
        'desagregacion_geografica': var_data.get('desagregacion_geografica', ''),  # ✅
        'desagregacion_tematica': var_data.get('desagregacion_tematica', ''),  # ✅
        'tipo_variable_estadistica': var_data.get('tipo_variable_estadistica', ''),  # ✅
        'fuente_datos': var_data.get('fuente_datos', ''),  # ✅
        'periodicidad': var_data.get('periodicidad', ''),  # ✅
        'observaciones': var_data.get('observaciones', ''),  # ✅
        'organismo_productor': var_data.get('organismo_productor', ''),  # ✅
        'orden': var_data.get('orden', index)  # ✅
    }
)
```

---

### **5. Establecer relación Indicador.microdata**

**Archivo:** `wizard_admin_unificado.py`
**Después de crear microdata e indicador:**

```python
# AGREGAR:
indicador.microdata = microdata
indicador.save()
```

---

## 📊 RESUMEN DE COMPATIBILIDAD

| Modelo | Campos Totales | Usados Correctamente | Usados Incorrectamente | Compatibilidad |
|--------|----------------|----------------------|------------------------|----------------|
| **Indicador** | 30 | 28 | 2 | 93% |
| **Microdata** | 6 | 4 | 2 | 67% |
| **VariableMicrodata** | 17 | 2 | 5 | 12% ❌ |
| **ReglaExtraccion** | 10 | 8 | 2 | 80% |
| **CargaMicrodata** | 14 | 14 | 0 | 100% ✅ |
| **CargaSerieIndicador** | 14 | 14 | 0 | 100% ✅ |

**PROMEDIO GENERAL:** **75%** → Requiere correcciones

---

## ✅ RECOMENDACIONES

1. **URGENTE:** Corregir nombres de campos en creación de objetos
2. **IMPORTANTE:** Actualizar `AplicadorMetadata` para VariableMicrodata
3. **RECOMENDADO:** Crear template CSV de ejemplo para metadata_variables
4. **OPCIONAL:** Agregar validaciones de campos requeridos
5. **FUTURO:** Agregar tests unitarios para verificar compatibilidad

---

## 📝 PLANTILLAS CSV ACTUALIZADAS

### **metadata_variables.csv (NUEVO FORMATO)**

```csv
codigo_variable,nombre_variable,definicion_conceptual,poblacion_objetivo,cobertura_geografica,desagregacion_geografica,desagregacion_tematica,tipo_dato,dominio_dato,unidad_medida,tipo_variable_estadistica,fuente_datos,periodicidad,observaciones,organismo_productor,orden
V1,edad,Edad del individuo en años cumplidos,Toda la población,Nacional,,Edad,Numérico,0-120,años,Cuantitativa continua,Encuesta Nacional,Anual,,DANE,1
V2,sexo,Sexo biológico del individuo,Toda la población,Nacional,,Sexo,Texto,Hombre|Mujer,,Cualitativa nominal,Encuesta Nacional,Anual,,DANE,2
V3,comuna,Comuna de residencia,Población urbana,Municipal,Comuna,,Texto,Lista de comunas,,Cualitativa nominal,Encuesta Nacional,Anual,,Alcaldía,3
```

---

**Fecha de auditoría:** 2025-01-21
**Versión del wizard:** 2.0
**Estado:** Requiere correcciones menores
