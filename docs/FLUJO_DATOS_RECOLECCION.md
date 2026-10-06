# Flujo de Datos del Módulo de Recolección - Sistema SIIED
## Análisis Completo del Sistema de Recolección, Roles y Procesamiento Cartesiano

---

## 📋 Tabla de Contenidos

1. [Actores y Roles del Sistema](#1-actores-y-roles-del-sistema)
2. [Estructura de Datos](#2-estructura-de-datos)
3. [Flujo de Recolección de Indicadores](#3-flujo-de-recolección-de-indicadores)
4. [Flujo de Recolección de Microdata](#4-flujo-de-recolección-de-microdata)
5. [Procesamiento Cartesiano](#5-procesamiento-cartesiano)
6. [Diagrama de Flujo General](#6-diagrama-de-flujo-general)

---

## 1. Actores y Roles del Sistema

### 1.1 Administradores (Staff)
- **Campo:** `User.is_staff = True`
- **Responsabilidades:**
  - Configurar jerarquía: Dominios → Temas → Subtemas → Indicadores
  - Crear dominios y desagregaciones (temáticas y geográficas)
  - Gestionar operaciones estadísticas y microdata
  - Crear y administrar perfiles de usuarios
  - Aprobar y procesar cargas de datos
  - Configurar reglas de extracción desde microdata
- **Acceso:** Panel Admin + Recolección + Reportes

### 1.2 Recolectores de Datos
- **Modelo:** `PerfilRecolector` con `rol='recolector'` o `rol='ambos'`
- **Responsabilidades:**
  - Cargar series de indicadores (datos agregados + metadata)
  - Cargar archivos de microdata (datos crudos + diccionario de variables)
  - Ver historial de cargas propias
  - Generar códigos de evidencia para cuenta de cobro
- **Acceso:** Solo módulo de recolección (`/recoleccion/`)
- **Típicamente:** Personal de instituciones, organismos productores

### 1.3 Consultores de Reportes
- **Modelo:** `PerfilRecolector` con `rol='consultor'` o `rol='ambos'`
- **Responsabilidades:**
  - Descargar datos de indicadores con desagregaciones
  - Exportar metadata (fichas técnicas)
  - Acceder a microdata para análisis
  - Generar reportes masivos
- **Acceso:** Solo módulo de reportes (`/reportes/`)
- **Típicamente:** Analistas, investigadores, consultores externos

---

## 2. Estructura de Datos

### 2.1 Jerarquía de Indicadores

```
MenuDominio (Ej: "Salud, Bienestar Social y Demografía")
    ↓
MenuTema (Ej: "Demografía y Población")
    ↓
MenuSubtema (Ej: "Mortalidad")
    ↓
Indicador (Ej: "Tasa de mortalidad menores de 5 años" - ICET_SAL_DEM_MOR_02)
    ↓
Dato (Valores con combinaciones de desagregaciones)
```

**Campos clave del Indicador:**
- `codigo_indicador`: ID único (ICET_SAL_DEM_MOR_02)
- `dominios_desagregacion_tematica`: M2M (sexo, edad, etc.)
- `dominios_desagregacion_geografica`: M2M (comunas, barrios, etc.)
- `microdata`: FK opcional a fuente de microdatos
- `formula`: Fórmula de cálculo desde microdata

### 2.2 Sistema de Desagregaciones

```
DominioDesagregacion (Ej: "Sexo", tipo='tematica')
    ↓
Desagregacion
    - "Hombre" (codigo: H)
    - "Mujer" (codigo: M)

DominioDesagregacion (Ej: "Grupo de Edad", tipo='tematica')
    ↓
Desagregacion
    - "0-1 años" (es_rango=True, valores_rango=['0','1'])
    - "2-4 años" (es_rango=True, valores_rango=['2','3','4'])
```

### 2.3 Modelo Dato (Registro de Valor del Indicador)

```python
class Dato:
    indicador: FK → Indicador
    fecha_dato: DateField (año)
    valor_dato: Decimal (valor calculado)
    desagregaciones_geograficas: M2M → Desagregacion
    desagregaciones_tematicas: M2M → Desagregacion
```

**Clave:** Un `Dato` representa un valor específico del indicador para una combinación única de desagregaciones.

### 2.4 Microdata y Variables

```
Microdata (archivo CSV con registros individuales)
    ↓
VariableMicrodata (definición de cada columna)
    - codigo_variable: "Edad"
    - nombre_variable: "Edad del fallecido"
    - definicion_conceptual: "Edad en años cumplidos al momento de la defunción"
    - tipo_dato: "Entero"
    - dominio_dato: "0-120"
```

---

## 3. Flujo de Recolección de Indicadores

### FASE 1: Configuración Previa (Administrador)

#### Paso 1: Crear Jerarquía
```
Admin → Menús Dominio → "Salud, Bienestar Social y Demografía"
Admin → Menús Tema → "Demografía y Población"
Admin → Menús Subtema → "Mortalidad"
```

#### Paso 2: Crear Dominios de Desagregación
```
Admin → Dominios → "Sexo" (tipo: temática)
Admin → Dominios → "Grupo de Edad" (tipo: temática)
Admin → Dominios → "Comunas" (tipo: geográfica, con NivelGeografico)
```

#### Paso 3: Crear Desagregaciones
```
"Sexo" → Hombre (H), Mujer (M)
"Grupo de Edad" → 0-1 años (rango=['0','1']), 2-4 años (rango=['2','3','4'])
"Comunas" → Comuna 1, Comuna 2, ... (asociadas a CapaGeo)
```

#### Paso 4: Crear Indicador
```
Admin → Indicadores → Crear:
  - codigo_indicador: ICET_SAL_DEM_MOR_02
  - nombre: "Tasa de mortalidad de niños menores de 5 años"
  - sigla: TMM5
  - subtema: Mortalidad
  - formula: "(V₁ / V₂) × 1.000"
  - dominios_desagregacion_tematica: [Sexo, Grupo de Edad]
  - dominios_desagregacion_geografica: [Comunas]
```

---

### FASE 2: Carga de Datos (Recolector)

#### Paso 1: Acceso
```
URL: /recoleccion/login/
Decorador: @recolector_required
Validación: User.is_staff OR perfil.puede_recolectar()
```

#### Paso 2: Preparar Archivos Excel

**Archivo 1: datos.xlsx (Serie de Datos Agregados)**
| Codigo_Indicador | Nombre | Anio | Desag_Geo | Desag_Tem_1 | Desag_Tem_2 | Valor |
|------------------|--------|------|-----------|-------------|-------------|-------|
| ICET_SAL_DEM_MOR_02 | Tasa mortalidad... | 2022 | Comuna 1 | Hombre | 0-1 años | 10.89 |
| ICET_SAL_DEM_MOR_02 | Tasa mortalidad... | 2022 | Comuna 1 | Mujer | 0-1 años | 11.25 |
| ICET_SAL_DEM_MOR_02 | Tasa mortalidad... | 2022 | Comuna 2 | Hombre | 2-4 años | 9.75 |

**Archivo 2: metadata.xlsx (Ficha Técnica)**
| Grupo | Dominio | Tema | Subtema | Codigo | Nombre | Sigla | Formula | Unidad | ... |
|-------|---------|------|---------|--------|--------|-------|---------|--------|-----|
| ICET | Salud... | Demografía | Mortalidad | ICET_SAL... | Tasa... | TMM5 | (V₁/V₂)×1000 | Muertes/1000 | ... |

#### Paso 3: Upload
```
Recolección → Cargar Serie de Indicador
  1. Seleccionar indicador (dropdown)
  2. Upload datos.xlsx
  3. Upload metadata.xlsx
  4. Submit
```

#### Paso 4: Procesamiento Backend
```python
# views_recoleccion.py - cargar_serie_indicador()

1. Crear CargaSerieIndicador:
   - usuario = request.user
   - archivo_datos_xlsx = datos.xlsx
   - archivo_metadata_xlsx = metadata.xlsx
   - estado = 'procesando'
   - codigo_evidencia = "CSIND-20250120-143055" (auto)

2. procesar_serie_indicador(carga):
   - pd.read_excel(datos.xlsx) → df_datos
   - df_datos.to_csv(datos.csv)
   - pd.read_excel(metadata.xlsx) → df_metadata
   - df_metadata.to_csv(metadata.csv)
   - estado = 'pendiente'
   - registros_procesados = len(df_datos)

3. Retornar código de evidencia al recolector
```

---

### FASE 3: Alimentación de Datos (Administrador - Propuesta)

> **NOTA:** Esta fase está pendiente de implementación completa. Actualmente el sistema convierte XLSX→CSV y almacena, pero no crea registros Dato automáticamente.

#### Proceso Propuesto de Alimentación:

```python
# Pseudocódigo - Procesar CSV y crear registros Dato

df = pd.read_csv(carga.archivo_datos_csv.path)

for index, row in df.iterrows():
    # 1. Obtener indicador
    indicador = Indicador.objects.get(
        codigo_indicador=row['Codigo_Indicador']
    )
    
    # 2. Crear registro Dato base
    dato = Dato.objects.create(
        indicador=indicador,
        fecha_dato=date(int(row['Anio']), 1, 1),
        valor_dato=Decimal(row['Valor'])
    )
    
    # 3. Matching de desagregación geográfica
    if pd.notna(row['Desag_Geo']):
        desag_geo = Desagregacion.objects.get(
            nombre=row['Desag_Geo'],
            dominio__tipo='geografica',
            dominio__in=indicador.dominios_desagregacion_geografica.all()
        )
        dato.desagregaciones_geograficas.add(desag_geo)
    
    # 4. Matching de desagregaciones temáticas
    columnas_tematicas = ['Desag_Tem_1', 'Desag_Tem_2', 'Desag_Tem_3']
    for col in columnas_tematicas:
        if col in row and pd.notna(row[col]):
            desag_tem = Desagregacion.objects.get(
                nombre=row[col],
                dominio__tipo='tematica',
                dominio__in=indicador.dominios_desagregacion_tematica.all()
            )
            dato.desagregaciones_tematicas.add(desag_tem)
    
    # 5. Guardar
    dato.save()

# Actualizar estado de carga
carga.estado = 'exitoso'
carga.registros_exitosos = len(df)
carga.save()
```

**Resultado:** Tabla `Dato` poblada con valores y sus combinaciones de desagregaciones.

---

## 4. Flujo de Recolección de Microdata

### FASE 1: Configuración (Administrador)

#### Paso 1: Crear Operación Estadística
```
Admin → Operaciones Estadísticas → Crear:
  - codigo: "OP-DEFUNCIONES-2024"
  - nombre: "Registro de Defunciones"
  - tipo_operacion: "Registro administrativo"
  - entidad_recopiladora: "DANE"
```

#### Paso 2: Indicadores Relacionados
Los indicadores que usarán esta microdata deben existir previamente (Ej: TMM5).

---

### FASE 2: Carga (Recolector)

#### Paso 1: Preparar Archivos

**Archivo 1: microdata_defunciones.xlsx (Registros Individuales)**
| ID | Anio | Mes | Departamento | Municipio | Sexo | Edad | Causa_Muerte | ... |
|----|------|-----|--------------|-----------|------|------|--------------|-----|
| 1 | 2022 | 01 | Valle | Cali | H | 0 | Natural | ... |
| 2 | 2022 | 01 | Valle | Cali | M | 1 | Natural | ... |
| 3 | 2022 | 02 | Valle | Cali | H | 3 | Accidente | ... |

**Archivo 2: metadata_variables.xlsx (Diccionario de Datos)**
| Codigo | Nombre | Definicion | Tipo_Dato | Dominio | ... |
|--------|--------|------------|-----------|---------|-----|
| ID | Identificador | ID único del registro | Entero | 1-999999 | ... |
| Sexo | Sexo | Sexo del fallecido | Texto | H, M | ... |
| Edad | Edad | Edad en años | Entero | 0-120 | ... |

#### Paso 2: Upload
```
Recolección → Cargar Microdata
  1. Upload microdata_defunciones.xlsx
  2. Upload metadata_variables.xlsx
  3. Indicar IDs de indicadores relacionados: "45, 67, 89"
  4. Submit
```

#### Paso 3: Procesamiento
```python
# views_recoleccion.py - cargar_microdata()

1. Crear CargaMicrodata:
   - usuario = request.user
   - archivo_microdata_xlsx = microdata.xlsx
   - archivo_metadata_variables_xlsx = metadata.xlsx
   - estado = 'procesando'
   - codigo_evidencia = "CMIC-20250120-144511"

2. procesar_microdata(carga):
   - pd.read_excel(microdata.xlsx) → df_microdata
   - df_microdata.to_csv(microdata.csv)
   - pd.read_excel(metadata.xlsx) → df_variables
   - df_variables.to_csv(metadata_variables.csv)
   - estado = 'pendiente'

3. Retornar código de evidencia
```

---

### FASE 3: Integración (Administrador)

#### Paso 1: Crear Registro de Microdata
```
Admin → Microdata → Crear:
  - nombre: "Defunciones Cali 2022"
  - archivo_csv: (asociar CSV de la carga)
  - operacion: OP-DEFUNCIONES-2024
```

#### Paso 2: Crear Variables
```
Admin → Variables de Microdata → Crear para cada variable:
  - microdata: "Defunciones Cali 2022"
  - codigo_variable: "Edad"
  - nombre_variable: "Edad del fallecido"
  - definicion_conceptual: "Edad en años cumplidos..."
  - tipo_dato: "Entero"
  - dominio_dato: "0-120"
```

#### Paso 3: Asociar a Indicador
```
Admin → Indicadores → Editar TMM5:
  - microdata: "Defunciones Cali 2022"
  - formula: "COUNT(Edad < 5) / Nacidos_vivos * 1000"
```

#### Paso 4: Crear Regla de Extracción
```
Admin → Reglas de Extracción → Crear:
  - indicador: TMM5
  - columnas_fuente: ["Sexo", "Edad", "Municipio"]
  - columna_fecha: "Anio"
  - filtros: {"Municipio": "Cali", "Edad": {"$lt": 5}}
  - orden_desagregaciones: {"Sexo": 1, "Edad": 2}
  - activo: True
```

---

## 5. Procesamiento Cartesiano

### 5.1 Definición

**Procesamiento cartesiano** = Generar todas las combinaciones posibles de desagregaciones configuradas para un indicador.

### 5.2 Ejemplo

**Indicador:** TMM5 con:
- **Desag. Temáticas:** Sexo (Hombre, Mujer) × Grupo de Edad (0-1 años, 2-4 años)
- **Desag. Geográficas:** Comunas (Comuna 1, Comuna 2)

**Producto cartesiano:** 2 × 2 × 2 = **8 combinaciones**

```
1. Comuna 1 × Hombre × 0-1 años → Valor A
2. Comuna 1 × Hombre × 2-4 años → Valor B
3. Comuna 1 × Mujer  × 0-1 años → Valor C
4. Comuna 1 × Mujer  × 2-4 años → Valor D
5. Comuna 2 × Hombre × 0-1 años → Valor E
6. Comuna 2 × Hombre × 2-4 años → Valor F
7. Comuna 2 × Mujer  × 0-1 años → Valor G
8. Comuna 2 × Mujer  × 2-4 años → Valor H
```

### 5.3 Aplicación: Desde Series Agregadas

El recolector sube un CSV donde cada fila = una combinación:

```csv
Codigo,Anio,Desag_Geo,Desag_Tem_1,Desag_Tem_2,Valor
TMM5,2022,Comuna 1,Hombre,0-1 años,10.89
TMM5,2022,Comuna 1,Mujer,0-1 años,11.25
...
```

El sistema crea un `Dato` por cada fila, asociando las desagregaciones correspondientes.

### 5.4 Aplicación: Desde Microdata (Propuesta)

```python
# Pseudocódigo - Extracción desde microdata con producto cartesiano

# 1. Obtener microdata
df = pd.read_csv(microdata.archivo_csv.path)

# 2. Obtener todas las desagregaciones del indicador
dominios_geo = indicador.dominios_desagregacion_geografica.all()
dominios_tem = indicador.dominios_desagregacion_tematica.all()

desag_geo_list = []
for dominio in dominios_geo:
    desag_geo_list.extend(dominio.desagregaciones.all())

desag_tem_list = []
for dominio in dominios_tem:
    desag_tem_list.extend(dominio.desagregaciones.all())

# 3. Producto cartesiano
from itertools import product
combinaciones = product(desag_geo_list, desag_tem_list)

# 4. Para cada combinación, calcular valor
for (desag_geo, *desag_tems) in combinaciones:
    # Filtrar microdata según combinación
    df_filtrado = df[df['Municipio'] == desag_geo.nombre]
    
    for desag_tem in desag_tems:
        if desag_tem.es_rango:
            # Rango de edad: Edad in [0, 1]
            df_filtrado = df_filtrado[
                df_filtrado['Edad'].astype(str).isin(desag_tem.valores_rango)
            ]
        else:
            # Valor exacto: Sexo = 'H'
            df_filtrado = df_filtrado[
                df_filtrado['Sexo'] == desag_tem.codigo
            ]
    
    # Calcular valor según fórmula del indicador
    count_defunciones = len(df_filtrado)
    nacidos_vivos = obtener_nacidos_vivos(desag_geo, year)
    valor = (count_defunciones / nacidos_vivos) * 1000 if nacidos_vivos > 0 else 0
    
    # 5. Crear Dato
    dato = Dato.objects.create(
        indicador=indicador,
        fecha_dato=date(year, 1, 1),
        valor_dato=Decimal(str(valor))
    )
    dato.desagregaciones_geograficas.add(desag_geo)
    for dt in desag_tems:
        dato.desagregaciones_tematicas.add(dt)
    dato.save()
```

**Resultado:** Generación automática de registros `Dato` para todas las combinaciones configuradas.

### 5.5 Ventajas

- ✅ **Completitud:** Datos para todas las combinaciones de análisis
- ✅ **Flexibilidad:** Usuarios pueden filtrar cualquier cruce
- ✅ **Consistencia:** Estructura uniforme independiente de la fuente
- ✅ **Análisis multidimensional:** Queries OLAP-like sobre los datos

### 5.6 Optimizaciones

```python
# 1. Índices en BD
class Dato:
    class Meta:
        indexes = [
            models.Index(fields=['indicador', '-fecha_dato']),
            models.Index(fields=['fecha_dato']),
        ]

# 2. Bulk create
datos_batch = []
for combinacion in combinaciones:
    dato = Dato(...)
    datos_batch.append(dato)

Dato.objects.bulk_create(datos_batch, batch_size=1000)

# 3. Procesamiento asíncrono con Celery
@shared_task
def procesar_microdata_async(regla_id):
    regla = ReglaExtraccion.objects.get(id=regla_id)
    # ... procesamiento cartesiano ...
```

---

## 6. Diagrama de Flujo General

```
┌─────────────────────────────────────────────────────────────┐
│                   CONFIGURACIÓN INICIAL                      │
│                    (Administrador)                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  1. Crear Jerarquía: Dominio → Tema → Subtema               │
│  2. Crear Dominios de Desagregación (Temáticas/Geográficas) │
│  3. Crear Desagregaciones dentro de cada Dominio            │
│  4. Crear Indicador y asociar Dominios                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
       ┌───────────────┴──────────────┐
       │                               │
       ▼                               ▼
┌──────────────────┐         ┌─────────────────────┐
│   OPCIÓN A:      │         │   OPCIÓN B:         │
│ Series Agregadas │         │   Microdata         │
│   (Recolector)   │         │   (Recolector)      │
└────────┬─────────┘         └──────────┬──────────┘
         │                               │
         │ 1. Upload datos.xlsx          │ 1. Upload microdata.xlsx
         │ 2. Upload metadata.xlsx       │ 2. Upload metadata_vars.xlsx
         │                               │ 3. Indicar IDs indicadores
         ▼                               ▼
┌─────────────────────┐       ┌──────────────────────────┐
│ CargaSerieIndicador │       │    CargaMicrodata        │
│                     │       │                          │
│ - XLSX → CSV        │       │ - XLSX → CSV             │
│ - estado: pendiente │       │ - estado: pendiente      │
│ - código evidencia  │       │ - código evidencia       │
└─────────┬───────────┘       └──────────┬───────────────┘
          │                               │
          │                               │
          ▼                               ▼
┌──────────────────────────────────────────────────────────────┐
│               PROCESAMIENTO (Administrador)                  │
└─────────┬──────────────────────────┬─────────────────────────┘
          │                           │
          ▼                           ▼
┌─────────────────────────┐  ┌────────────────────────────────┐
│ Parser CSV Series       │  │ 1. Crear Microdata             │
│                         │  │ 2. Crear VariableMicrodata     │
│ Para cada fila:         │  │ 3. Asociar a Indicador         │
│   - Crear Dato          │  │ 4. Crear ReglaExtraccion       │
│   - Match desag. geo    │  │ 5. Ejecutar procesamiento      │
│   - Match desag. tems   │  │    cartesiano                  │
│   - Asociar M2M         │  │                                │
└─────────┬───────────────┘  └──────────────┬─────────────────┘
          │                                  │
          │                                  │
          └──────────────┬───────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │   TABLA DATO         │
              │                      │
              │ Registros con:       │
              │ - indicador          │
              │ - fecha_dato         │
              │ - valor_dato         │
              │ - desag_geograficas  │
              │ - desag_tematicas    │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  VISUALIZACIÓN       │
              │                      │
              │ - Gráficos           │
              │ - Mapas              │
              │ - Tablas dinámicas   │
              │ - Exportación        │
              └──────────────────────┘
```

---

## Resumen Ejecutivo

### Flujo de Indicadores
1. **Admin** configura: Jerarquía + Desagregaciones + Indicador
2. **Recolector** sube: datos.xlsx + metadata.xlsx
3. **Sistema** convierte: XLSX → CSV (estado: pendiente)
4. **Admin** procesa: CSV → Registros Dato (matching desagregaciones)
5. **Resultado:** Tabla Dato poblada para visualización

### Flujo de Microdata
1. **Admin** configura: Operación Estadística + Indicador
2. **Recolector** sube: microdata.xlsx + metadata_vars.xlsx + IDs indicadores
3. **Sistema** convierte: XLSX → CSV (estado: pendiente)
4. **Admin** integra: Crear Microdata + Variables + Regla Extracción
5. **Sistema** ejecuta: Procesamiento cartesiano (filtros + agregación)
6. **Resultado:** Tabla Dato generada automáticamente

### Procesamiento Cartesiano
- **Desde series:** Cada fila del CSV = 1 Dato con sus desagregaciones
- **Desde microdata:** Se generan Datos para TODAS las combinaciones posibles de desagregaciones configuradas en el indicador
- **Ventaja:** Análisis multidimensional completo y flexible

---

## Estado Actual vs. Implementación Pendiente

### ✅ Implementado
- Sistema de roles y autenticación
- Upload de archivos XLSX
- Conversión XLSX → CSV
- Almacenamiento de cargas con código de evidencia
- Estructura de modelos completa
- Dashboard de recolección

### ⏳ Pendiente
- Parser automático de CSV → Tabla Dato
- Matching automático de desagregaciones por nombre
- Ejecución de ReglaExtraccion (procesamiento cartesiano desde microdata)
- Validación de integridad de datos
- Notificaciones de estado de procesamiento
- API para procesamiento asíncrono (Celery)

---

**Fecha de análisis:** 2025-01-20  
**Versión del sistema:** SIIED v1.0  
**Analista:** Windsurf Cascade AI
