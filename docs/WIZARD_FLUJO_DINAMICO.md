# Diseño del Wizard Admin Unificado - Flujo Dinámico

## 🎯 Objetivo
Wizard adaptativo que cambia sus pasos según el caso de uso detectado.

---

## 📊 Diagrama de Flujo Principal

```mermaid
flowchart TD
    START([Inicio del Wizard]) --> PASO1[Paso 1: Selección de Fuente]
    
    PASO1 --> DECISION1{¿Qué tipo de fuente?}
    
    DECISION1 -->|Carga Pendiente| DECISION2{¿Qué tipo de carga?}
    DECISION1 -->|Subir Ahora| DECISION3{¿Qué tipo de archivo?}
    DECISION1 -->|Indicador Existente| FLUJO_ACTUALIZAR
    
    DECISION2 -->|CargaMicrodata| FLUJO_MICRODATA
    DECISION2 -->|CargaSerieIndicador| FLUJO_SERIE
    DECISION2 -->|Ambas| FLUJO_COMPLETO
    
    DECISION3 -->|Microdata| FLUJO_MICRODATA
    DECISION3 -->|Serie de Datos| FLUJO_SERIE
    
    %% FLUJO 1: Con Microdata
    FLUJO_MICRODATA[FLUJO A: Con Microdata]
    FLUJO_MICRODATA --> P2A[Paso 2A: Preview Microdata Univer]
    P2A --> P3A[Paso 3A: Config Microdata]
    P3A --> P4A[Paso 4A: Metadata Variables]
    P4A --> P5A[Paso 5A: Config Indicador]
    P5A --> P6A[Paso 6A: Verificar Desagregaciones]
    P6A --> P7A[Paso 7A: Crear Regla Extracción]
    P7A --> P8A[Paso 8A: Diagnóstico]
    P8A --> FINAL_A{¿Diagnóstico OK?}
    FINAL_A -->|Sí| PROCESO_A[Procesamiento Cartesiano]
    FINAL_A -->|No| P7A
    PROCESO_A --> P9A[Paso 9A: Configurar Gráficos]
    P9A --> END([Fin: Ver Logs en Vivo])
    
    %% FLUJO 2: Solo Serie
    FLUJO_SERIE[FLUJO B: Solo Serie de Datos]
    FLUJO_SERIE --> P2B[Paso 2B: Preview Serie Univer]
    P2B --> P3B[Paso 3B: Config Indicador]
    P3B --> P4B[Paso 4B: Cargar Metadata]
    P4B --> P5B[Paso 5B: Verificar Desagregaciones]
    P5B --> P6B[Paso 6B: Mapeo de Columnas]
    P6B --> P7B[Paso 7B: Confirmación]
    P7B --> PROCESO_B[Importación Directa]
    PROCESO_B --> P8B[Paso 8B: Configurar Gráficos]
    P8B --> END
    
    %% FLUJO 3: Completo (Microdata + Serie)
    FLUJO_COMPLETO[FLUJO C: Microdata + Serie]
    FLUJO_COMPLETO --> P2C[Paso 2C: Preview Ambos Univer]
    P2C --> P3C[Paso 3C: Config Microdata]
    P3C --> P4C[Paso 4C: Metadata Variables]
    P4C --> P5C[Paso 5C: Config Indicador]
    P5C --> P6C[Paso 6C: Cargar Metadata Indicador]
    P6C --> P7C[Paso 7C: Verificar Desagregaciones]
    P7C --> P8C[Paso 8C: Crear Regla Extracción]
    P8C --> P9C[Paso 9C: Diagnóstico]
    P9C --> FINAL_C{¿Diagnóstico OK?}
    FINAL_C -->|Sí| PROCESO_C[Procesamiento Cartesiano]
    FINAL_C -->|No| P8C
    PROCESO_C --> P10C[Paso 10C: Validar con Serie Univer]
    P10C --> P11C[Paso 11C: Configurar Gráficos]
    P11C --> END
    
    %% FLUJO 4: Actualizar Existente
    FLUJO_ACTUALIZAR[FLUJO D: Actualizar Existente]
    FLUJO_ACTUALIZAR --> P2D[Paso 2D: Seleccionar Indicador]
    P2D --> P3D[Paso 3D: Seleccionar Carga Nueva]
    P3D --> DECISION4{¿Tipo de carga?}
    DECISION4 -->|Serie| P4D_SERIE[Paso 4D: Comparar Metadata]
    DECISION4 -->|Microdata| P4D_MICRO[Paso 4D: Actualizar Microdata]
    P4D_SERIE --> P5D[Paso 5D: Confirmar Cambios]
    P4D_MICRO --> P5D
    P5D --> PROCESO_D[Actualizar y Procesar]
    PROCESO_D --> END
    
    style START fill:#4caf50,color:#fff
    style END fill:#2196f3,color:#fff
    style FLUJO_MICRODATA fill:#ff9800,color:#fff
    style FLUJO_SERIE fill:#9c27b0,color:#fff
    style FLUJO_COMPLETO fill:#f44336,color:#fff
    style FLUJO_ACTUALIZAR fill:#00bcd4,color:#fff
```

---

## 🔍 Detalle de Cada Paso

### Paso 1: Selección de Fuente (Común a Todos)

```mermaid
flowchart LR
    PASO1[Paso 1: Selección de Fuente]
    
    PASO1 --> OPT1[Opción 1: Cargas Pendientes]
    PASO1 --> OPT2[Opción 2: Subir Ahora]
    PASO1 --> OPT3[Opción 3: Actualizar Existente]
    
    OPT1 --> TABLA1[Tabla: CargaMicrodata pendientes]
    OPT1 --> TABLA2[Tabla: CargaSerieIndicador pendientes]
    OPT1 --> COMBO[Combo: Seleccionar ambas]
    
    OPT2 --> UPLOAD1[Upload: Microdata + Metadata Variables]
    OPT2 --> UPLOAD2[Upload: Serie + Metadata Indicador]
    
    OPT3 --> SELECT[Select: Indicador existente]
    SELECT --> UPLOAD3[Upload: Nueva carga]
```

---

## 📋 Pasos del Flujo A (Con Microdata)

```mermaid
flowchart TD
    P2A[Paso 2A: Preview Microdata con Univer]
    P2A --> UNIVER1[Cargar Univer.js dinámicamente]
    P2A --> UNIVER2[Renderizar hoja de cálculo interactiva]
    P2A --> UNIVER3[Mostrar estadísticas: filas, columnas, tamaño]
    P2A --> UNIVER4[Botones: Exportar Excel/CSV]
    
    P3A[Paso 3A: Configurar Microdata]
    P3A --> RADIO1{¿Crear nueva o asociar?}
    RADIO1 -->|Crear| FORM1[Nombre, Descripción, Operación]
    RADIO1 -->|Asociar| SELECT1[Select: Microdata existente]
    
    P4A[Paso 4A: Metadata de Variables]
    P4A --> PARSE[Parsear metadata_variables.csv]
    P4A --> TABLE[Tabla: Variables detectadas]
    P4A --> CHECK[Checkbox: Cargar automáticamente]
    
    P5A[Paso 5A: Configurar Indicador]
    P5A --> RADIO2{¿Crear nuevo o asociar?}
    RADIO2 -->|Crear| FORM2[Código, Nombre, Sigla, Subtema]
    RADIO2 -->|Asociar| SELECT2[Select: Indicador existente]
    P5A --> PARSE2[Parsear metadata.csv si existe]
    P5A --> PREVIEW[Preview: Metadata detectada]
    P5A --> CHECK2[Checkbox: Cargar metadata completa]
    
    P6A[Paso 6A: Verificar Desagregaciones]
    P6A --> ANALIZAR[Analizar columnas del CSV]
    P6A --> DETECTAR[Detectar desagregaciones mencionadas]
    P6A --> COMPARAR[Comparar con BD]
    P6A --> MOSTRAR_GEO[Lista: Geográficas existentes/faltantes]
    P6A --> MOSTRAR_TEM[Lista: Temáticas existentes/faltantes]
    P6A --> SUGERIR[Sugerir dominios para faltantes]
    P6A --> BTN_CREAR[Botón: Crear faltantes automáticamente]
    
    P7A[Paso 7A: Crear Regla de Extracción]
    P7A --> FORM3[Columna fecha]
    P7A --> FORM4[Columnas fuente]
    P7A --> FORM5[Fórmula]
    P7A --> FORM6[Filtros JSON]
    P7A --> FORM7[Orden desagregaciones]
    
    P8A[Paso 8A: Diagnóstico]
    P8A --> EJECUTAR[Ejecutar diagnosticar_microdata]
    P8A --> OUTPUT[Mostrar salida en consola]
    P8A --> VALIDAR{¿Hay errores?}
    VALIDAR -->|Sí| ALERT[Mostrar errores y volver a P7A]
    VALIDAR -->|No| BTN_CONFIRMAR[Botón: Confirmar y Procesar]
```

---

## 📋 Pasos del Flujo B (Solo Serie)

```mermaid
flowchart TD
    P2B[Paso 2B: Preview Serie con Univer]
    P2B --> UNIVER1[Cargar Univer.js dinámicamente]
    P2B --> UNIVER2[Renderizar hoja de cálculo interactiva]
    P2B --> DETECT1[Detectar columnas de desagregación]
    P2B --> DETECT2[Detectar columna de fecha]
    P2B --> DETECT3[Detectar columna de valor]
    P2B --> UNIVER3[Botones: Exportar Excel/CSV]
    
    P3B[Paso 3B: Configurar Indicador]
    P3B --> RADIO{¿Crear nuevo o asociar?}
    RADIO -->|Crear| FORM[Código, Nombre, Sigla, Subtema]
    RADIO -->|Asociar| SELECT[Select: Indicador existente]
    
    P4B[Paso 4B: Cargar Metadata]
    P4B --> PARSE[Parsear metadata.csv]
    P4B --> PREVIEW[Preview: Metadata detectada]
    P4B --> CHECK[Checkbox: Cargar metadata completa]
    P4B --> CAMPOS[Mostrar campos que se cargarán]
    
    P5B[Paso 5B: Verificar Desagregaciones]
    P5B --> ANALIZAR[Analizar valores únicos en columnas]
    P5B --> DETECTAR[Detectar desagregaciones]
    P5B --> COMPARAR[Comparar con BD]
    P5B --> MOSTRAR[Lista: Existentes/Faltantes]
    P5B --> BTN_CREAR[Botón: Crear faltantes]
    
    P6B[Paso 6B: Mapeo de Columnas]
    P6B --> MAP1[Mapear: Columna fecha → fecha_dato]
    P6B --> MAP2[Mapear: Columna valor → valor_dato]
    P6B --> MAP3[Mapear: Columnas desag geo]
    P6B --> MAP4[Mapear: Columnas desag tem]
    P6B --> PREVIEW2[Preview: Cómo se importarán]
    
    P7B[Paso 7B: Confirmación]
    P7B --> RESUMEN[Resumen de configuración]
    P7B --> CHECKBOX[Checkbox: Eliminar datos existentes]
    P7B --> BTN[Botón: Importar Datos]
```

---

## 📋 Pasos del Flujo C (Completo: Microdata + Serie)

**Caso de Uso:** El equipo técnico subió AMBAS cargas:
- `CargaMicrodata` (microdata.csv + metadata_variables.csv)
- `CargaSerieIndicador` (datos.csv + metadata.csv)

**Objetivo:** 
1. Procesar microdata con producto cartesiano
2. Cargar metadata del indicador desde `CargaSerieIndicador`
3. Validar que los datos procesados coincidan con la serie original

### Uso de Archivos en Flujo C

```mermaid
graph LR
    subgraph CargaMicrodata
        A1[microdata.csv]
        A2[metadata_variables.csv]
    end
    
    subgraph CargaSerieIndicador
        B1[datos.csv]
        B2[metadata.csv]
    end
    
    A1 -->|Paso 2C| PREVIEW1[Preview Univer Tab 1]
    A2 -->|Paso 4C| VARS[Crear VariableMicrodata]
    
    B1 -->|Paso 2C| PREVIEW2[Preview Univer Tab 2]
    B2 -->|Paso 6C| META[Cargar Metadata Indicador]
    
    A1 -->|Paso 8C| REGLA[Crear ReglaExtraccion]
    REGLA -->|Paso 9C| DIAG[Diagnóstico]
    DIAG -->|OK| PROC[Procesamiento Cartesiano]
    
    PROC -->|Genera| DATOS_PROC[Datos Procesados]
    B1 -->|Serie Original| DATOS_ORIG[Datos Originales]
    
    DATOS_PROC -->|Paso 10C| VALIDAR[Validar con Univer]
    DATOS_ORIG -->|Paso 10C| VALIDAR
    
    style A1 fill:#e1f5ff
    style A2 fill:#e1f5ff
    style B1 fill:#fff4e1
    style B2 fill:#fff4e1
    style VALIDAR fill:#e8f5e9
```

```mermaid
flowchart TD
    P2C[Paso 2C: Preview Ambos con Univer]
    P2C --> TABS[Tabs: Microdata | Serie]
    P2C --> TAB1[Tab Microdata: Univer con microdata]
    P2C --> TAB2[Tab Serie: Univer con serie]
    P2C --> STATS[Estadísticas de ambos archivos]
    
    P3C[Paso 3C: Config Microdata]
    P3C --> IGUAL_3C[Igual que Paso 3A del Flujo A]
    
    P4C[Paso 4C: Metadata Variables]
    P4C --> PARSE_VAR[Parsear metadata_variables.csv]
    P4C --> TABLA_VAR[Tabla: Variables detectadas]
    P4C --> CHECK_VAR[Checkbox: Cargar automáticamente]
    
    P5C[Paso 5C: Config Indicador]
    P5C --> RADIO{¿Crear nuevo o asociar?}
    RADIO -->|Crear| FORM[Código, Nombre, Sigla, Subtema]
    RADIO -->|Asociar| SELECT[Select: Indicador existente]
    
    P6C[Paso 6C: Cargar Metadata Indicador]
    P6C --> PARSE_IND[Parsear metadata.csv de CargaSerieIndicador]
    P6C --> PREVIEW_IND[Preview: Metadata detectada]
    P6C --> CAMPOS_IND[Mostrar todos los campos de ficha técnica]
    P6C --> CHECK_IND[Checkbox: Cargar metadata completa]
    P6C --> INFO_IND[Info: Datos vienen de CargaSerieIndicador]
    
    P7C[Paso 7C: Verificar Desagregaciones]
    P7C --> ANALIZAR[Analizar columnas de microdata Y serie]
    P7C --> DETECTAR[Detectar desagregaciones en ambos]
    P7C --> COMPARAR[Comparar con BD]
    P7C --> MOSTRAR[Lista: Existentes/Faltantes]
    P7C --> BTN_CREAR[Botón: Crear faltantes]
    
    P8C[Paso 8C: Crear Regla Extracción]
    P8C --> IGUAL_8C[Igual que Paso 7A del Flujo A]
    
    P9C[Paso 9C: Diagnóstico]
    P9C --> IGUAL_9C[Igual que Paso 8A del Flujo A]
    
    P10C[Paso 10C: Validar con Serie Univer]
    P10C --> TABS2[Tabs: Datos Procesados | Serie Original]
    P10C --> TAB3[Tab 1: Univer con datos procesados]
    P10C --> TAB4[Tab 2: Univer con serie original]
    P10C --> INFO[Info: Comparar visualmente a ojo]
    P10C --> NOTA[Nota: No hay comparación automática]
    P10C --> AYUDA[Ayuda: Verificar que fórmula sea correcta]
    
    P11C[Paso 11C: Configurar Gráficos]
    P11C --> IGUAL2[Ver sección de Gráficos abajo]
```

---

## 📋 Pasos del Flujo D (Actualizar Existente)

```mermaid
flowchart TD
    P2D[Paso 2D: Seleccionar Indicador]
    P2D --> SEARCH[Buscador de indicadores]
    P2D --> FILTROS[Filtros: Dominio, Tema, Subtema]
    P2D --> SELECT[Select: Indicador]
    P2D --> PREVIEW[Preview: Info actual del indicador]
    
    P3D[Paso 3D: Seleccionar Carga Nueva]
    P3D --> RADIO{¿Qué actualizar?}
    RADIO -->|Serie| TABLA1[Tabla: CargaSerieIndicador pendientes]
    RADIO -->|Microdata| TABLA2[Tabla: CargaMicrodata pendientes]
    
    P4D[Paso 4D: Comparar Metadata]
    P4D --> DIFF[Diff viewer: Metadata actual vs nueva]
    P4D --> HIGHLIGHT[Highlight: Campos que cambiarán]
    P4D --> CHECKBOXES[Checkboxes: Seleccionar qué actualizar]
    
    P5D[Paso 5D: Confirmar Cambios]
    P5D --> RESUMEN[Resumen de cambios]
    P5D --> WARNING[Warning: Datos existentes]
    P5D --> RADIO2{¿Qué hacer con datos?}
    RADIO2 -->|Mantener| KEEP[Mantener datos existentes]
    RADIO2 -->|Reemplazar| REPLACE[Eliminar y recargar]
    RADIO2 -->|Agregar| APPEND[Agregar nuevos datos]
```

---

## 🎨 Componentes Visuales Clave

### Selector de Cargas Pendientes

```mermaid
graph TD
    SELECTOR[Selector de Cargas]
    
    SELECTOR --> FILTRO1[Filtro: Fecha]
    SELECTOR --> FILTRO2[Filtro: Usuario]
    SELECTOR --> FILTRO3[Filtro: Estado]
    
    SELECTOR --> CARD1[Card: Carga 1]
    CARD1 --> INFO1[Código: CMIC-20250120-143055]
    CARD1 --> INFO2[Usuario: jperez]
    CARD1 --> INFO3[Fecha: 2025-01-20]
    CARD1 --> INFO4[Archivos: 2]
    CARD1 --> BTN1[Botón: Seleccionar]
    
    SELECTOR --> CARD2[Card: Carga 2]
    CARD2 --> INFO5[...]
```

### Verificador de Desagregaciones

```mermaid
graph LR
    VERIFICADOR[Verificador de Desagregaciones]
    
    VERIFICADOR --> SECCION1[Sección: Geográficas]
    SECCION1 --> BADGE1[Badge: 5 existentes]
    SECCION1 --> BADGE2[Badge: 2 faltantes]
    SECCION1 --> LISTA1[Lista: Comuna 22, Barrio X]
    SECCION1 --> SUGERENCIA1[Sugerencia: Dominio 'Comunas']
    SECCION1 --> BTN1[Botón: Crear faltantes]
    
    VERIFICADOR --> SECCION2[Sección: Temáticas]
    SECCION2 --> BADGE3[Badge: 8 existentes]
    SECCION2 --> BADGE4[Badge: 0 faltantes]
```

---

## 🔄 Navegación Entre Pasos

```mermaid
stateDiagram-v2
    [*] --> Paso1
    Paso1 --> Paso2A: Flujo A
    Paso1 --> Paso2B: Flujo B
    Paso1 --> Paso2C: Flujo C
    Paso1 --> Paso2D: Flujo D
    
    Paso2A --> Paso3A: Siguiente
    Paso3A --> Paso2A: Anterior
    Paso3A --> Paso4A: Siguiente
    Paso4A --> Paso3A: Anterior
    
    note right of Paso1
        Siempre se puede:
        - Ir al paso anterior
        - Cancelar wizard
        - Ver resumen parcial
    end note
    
    note right of Paso8A
        Diagnóstico puede:
        - Volver a P7A si hay errores
        - Continuar si todo OK
    end note
```

---

## 📊 Estado del Wizard (Session Data)

```mermaid
classDiagram
    class WizardSession {
        +str tipo_flujo
        +int carga_microdata_id
        +int carga_serie_id
        +int indicador_id
        +dict metadata_indicador
        +dict metadata_indicador_desde_serie
        +list variables_detectadas
        +dict desagregaciones_analisis
        +dict configuracion_regla
        +bool cargar_metadata_auto
        +bool cargar_metadata_indicador_auto
        +bool crear_desag_faltantes
        +list graficos_configurados
    }
    
    class FlujoDinamico {
        +list pasos_actuales
        +int paso_actual
        +dict datos_acumulados
        +determinar_pasos()
        +puede_avanzar()
        +puede_retroceder()
        +get_archivos_disponibles()
    }
    
    WizardSession --> FlujoDinamico
    
    note for WizardSession "En Flujo C:\n- metadata_indicador: de CargaSerieIndicador\n- variables_detectadas: de CargaMicrodata"
```

---

## 🎯 Decisiones de Diseño

### 1. ¿Por qué pasos dinámicos?
- **Flexibilidad:** Se adapta al caso de uso real
- **Simplicidad:** Usuario solo ve pasos relevantes
- **Eficiencia:** No pierde tiempo en pasos innecesarios

### 2. ¿Por qué separar flujos?
- **Claridad:** Cada flujo tiene su lógica específica
- **Mantenibilidad:** Más fácil modificar un flujo sin afectar otros
- **Testing:** Se puede probar cada flujo independientemente

### 3. ¿Por qué validar desagregaciones?
- **Prevención:** Evita errores en procesamiento
- **Automatización:** Crea elementos faltantes automáticamente
- **Transparencia:** Usuario ve qué falta antes de procesar

---

## 📊 Detalle: Integración de Univer.js

### ¿Qué es Univer?
**Univer** (https://univer.ai/) es una librería JavaScript de código abierto que renderiza hojas de cálculo tipo Excel en el navegador con funcionalidades completas.

### Características que usaremos:
- ✅ Renderizado de datos CSV como hoja de cálculo interactiva
- ✅ Scroll, zoom, navegación con teclado
- ✅ Edición de celdas (opcional, solo para exploración)
- ✅ Fórmulas básicas (SUM, AVERAGE, COUNT)
- ✅ Exportación a Excel y CSV
- ✅ Formato visual (colores, negrita, alineación)
- ✅ Redimensionamiento de filas y columnas

### Implementación en el Wizard

```mermaid
sequenceDiagram
    participant User as Usuario
    participant Wizard as Wizard
    participant Univer as Univer.js
    participant Backend as Backend Django
    
    User->>Wizard: Llega a paso de preview
    Wizard->>Backend: Solicitar datos CSV
    Backend-->>Wizard: Retorna datos CSV
    Wizard->>Univer: Cargar scripts dinámicamente
    Univer-->>Wizard: Scripts cargados
    Wizard->>Univer: Inicializar con datos CSV
    Univer-->>User: Renderiza hoja de cálculo
    User->>Univer: Explora, scroll, zoom
    User->>Univer: Click "Exportar Excel"
    Univer-->>User: Descarga archivo Excel
    User->>Wizard: Click "Siguiente paso"
```

### Código de Integración (Ejemplo)

```javascript
// Cargar Univer dinámicamente
async function loadUniver() {
    const scripts = [
        'https://unpkg.com/@univerjs/presets/lib/umd/index.js',
        'https://unpkg.com/@univerjs/preset-sheets-core/lib/umd/index.js'
    ];
    
    for (const src of scripts) {
        await loadScript(src);
    }
}

// Inicializar Univer con datos CSV
function initUniver(csvData) {
    const { createUniver } = window.UniverPresets;
    
    const univer = createUniver({
        locale: 'en-US',
        container: 'univer-container',
        data: parseCSVToUniverFormat(csvData)
    });
    
    return univer;
}

// Exportar a Excel
function exportToExcel(univerInstance) {
    const data = univerInstance.getSheetData();
    const worksheet = XLSX.utils.aoa_to_sheet(data);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Datos');
    XLSX.writeFile(workbook, 'datos.xlsx');
}
```

---

## 🎨 Detalle: Configuración de Gráficos

### Paso Final: Configurar Gráficos (Todos los Flujos)

```mermaid
flowchart TD
    INICIO[Paso Final: Configurar Gráficos]
    
    INICIO --> INFO[Info: Datos ya procesados/importados]
    INFO --> OPCIONAL{¿Crear gráficos ahora?}
    
    OPCIONAL -->|Sí| CREAR[Crear Gráficos]
    OPCIONAL -->|No| SKIP[Saltar - Crear después desde admin]
    
    CREAR --> FORM1[Formulario: Gráfico 1]
    FORM1 --> CAMPOS1[Campos del Gráfico]
    
    CAMPOS1 --> NOMBRE[Nombre del gráfico]
    CAMPOS1 --> TIPO[Tipo: line, bar, area, pie, etc.]
    CAMPOS1 --> TITULO[Título y subtítulo]
    CAMPOS1 --> EJES[Títulos de ejes X e Y]
    CAMPOS1 --> CONFIG[Configuración visual]
    
    CONFIG --> LEYENDA[Mostrar leyenda: Sí/No]
    CONFIG --> POSICION[Posición leyenda: top/bottom/left/right]
    CONFIG --> CUADRICULA[Mostrar cuadrícula: Sí/No]
    CONFIG --> VALORES[Mostrar valores en puntos: Sí/No]
    CONFIG --> ALTURA[Altura del gráfico: 200-1000px]
    CONFIG --> ZERO[Comenzar en cero: Sí/No]
    
    CAMPOS1 --> DESAG[Desagregaciones Predeterminadas]
    DESAG --> DESAG_GEO[Seleccionar desag. geográficas]
    DESAG --> DESAG_TEM[Seleccionar desag. temáticas]
    
    CAMPOS1 --> SERIES[Configurar Series]
    SERIES --> SERIE1[Serie 1]
    SERIE1 --> S1_DESAG_GEO[Desagregación geográfica]
    SERIE1 --> S1_DESAG_TEM[Desagregación temática]
    SERIE1 --> S1_NOMBRE[Nombre personalizado opcional]
    SERIE1 --> S1_COLOR[Color de la serie]
    
    SERIES --> BTN_ADD[Botón: Agregar otra serie]
    BTN_ADD --> SERIE2[Serie 2, 3, 4...]
    
    FORM1 --> PREVIEW[Preview del Gráfico]
    PREVIEW --> RENDER[Renderizar con Plotly.js]
    RENDER --> MUESTRA[Muestra con datos reales]
    
    FORM1 --> BTN_OTRO{¿Crear otro gráfico?}
    BTN_OTRO -->|Sí| FORM2[Formulario: Gráfico 2]
    BTN_OTRO -->|No| RESUMEN[Resumen de Gráficos Creados]
    
    FORM2 --> FORM1
    RESUMEN --> FIN[Finalizar Wizard]
    SKIP --> FIN
```

### Modelo de Datos de Gráficos

```mermaid
classDiagram
    class Grafico {
        +int id
        +ForeignKey indicador
        +str nombre
        +str tipo_grafico
        +bool activo
        +str titulo
        +str subtitulo
        +str eje_x_titulo
        +str eje_y_titulo
        +bool mostrar_leyenda
        +str posicion_leyenda
        +bool mostrar_cuadricula
        +bool mostrar_valores
        +int altura_grafico
        +bool begin_at_zero
        +float rango_personalizado_min
        +float rango_personalizado_max
        +int orden
        +M2M desagregaciones_geograficas_predeterminadas
        +M2M desagregaciones_tematicas_predeterminadas
    }
    
    class GraficoSerie {
        +int id
        +ForeignKey grafico
        +ForeignKey desagregacion_geografica
        +ForeignKey desagregacion_tematica
        +str nombre_personalizado
        +str color
        +int orden
    }
    
    Grafico "1" --> "*" GraficoSerie : tiene
```

### Formulario de Gráfico en el Wizard

```python
class FormularioGrafico(forms.Form):
    """Formulario para crear un gráfico en el wizard"""
    
    # Básico
    nombre = forms.CharField(max_length=255, label="Nombre del Gráfico")
    tipo_grafico = forms.ChoiceField(
        choices=Grafico.TIPO_GRAFICO_CHOICES,
        label="Tipo de Gráfico"
    )
    activo = forms.BooleanField(initial=True, required=False)
    
    # Títulos
    titulo = forms.CharField(max_length=255, required=False)
    subtitulo = forms.CharField(max_length=255, required=False)
    eje_x_titulo = forms.CharField(max_length=255, required=False)
    eje_y_titulo = forms.CharField(max_length=255, required=False)
    
    # Configuración visual
    mostrar_leyenda = forms.BooleanField(initial=True, required=False)
    posicion_leyenda = forms.ChoiceField(
        choices=Grafico.POSICION_LEYENDA_CHOICES,
        initial='right'
    )
    mostrar_cuadricula = forms.BooleanField(initial=True, required=False)
    mostrar_valores = forms.BooleanField(initial=False, required=False)
    altura_grafico = forms.IntegerField(
        initial=400,
        min_value=200,
        max_value=1000
    )
    begin_at_zero = forms.BooleanField(initial=True, required=False)
    
    # Desagregaciones predeterminadas
    desagregaciones_geograficas = forms.ModelMultipleChoiceField(
        queryset=Desagregacion.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )
    desagregaciones_tematicas = forms.ModelMultipleChoiceField(
        queryset=Desagregacion.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )
    
    def __init__(self, *args, **kwargs):
        indicador = kwargs.pop('indicador', None)
        super().__init__(*args, **kwargs)
        
        if indicador:
            # Filtrar desagregaciones según dominios del indicador
            self.fields['desagregaciones_geograficas'].queryset = \
                Desagregacion.objects.filter(
                    dominio__in=indicador.dominios_desagregacion_geografica.all()
                )
            self.fields['desagregaciones_tematicas'].queryset = \
                Desagregacion.objects.filter(
                    dominio__in=indicador.dominios_desagregacion_tematica.all()
                )
```

### Formset para Series del Gráfico

```python
from django.forms import formset_factory

class FormularioSerie(forms.Form):
    """Formulario para una serie del gráfico"""
    
    desagregacion_geografica = forms.ModelChoiceField(
        queryset=Desagregacion.objects.none(),
        required=False
    )
    desagregacion_tematica = forms.ModelChoiceField(
        queryset=Desagregacion.objects.none(),
        required=False
    )
    nombre_personalizado = forms.CharField(
        max_length=255,
        required=False,
        help_text="Opcional: nombre personalizado para la serie"
    )
    color = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'type': 'color'})
    )
    orden = forms.IntegerField(initial=0, widget=forms.HiddenInput())

# Crear formset con mínimo 1 serie, máximo 10
SerieFormSet = formset_factory(
    FormularioSerie,
    extra=1,
    min_num=1,
    max_num=10,
    validate_min=True
)
```

### Vista del Paso de Gráficos

```html
<div class="wizard-step graficos">
    <h2>Configurar Gráficos para el Indicador</h2>
    
    <div class="info-box">
        <i class="fas fa-info-circle"></i>
        <p>Los gráficos son opcionales. Puedes crearlos ahora o más tarde desde el admin.</p>
    </div>
    
    <div class="graficos-container">
        <!-- Formulario del gráfico -->
        <div class="grafico-form">
            <h3>Gráfico 1</h3>
            
            {{ form.nombre }}
            {{ form.tipo_grafico }}
            
            <div class="form-section">
                <h4>Títulos</h4>
                {{ form.titulo }}
                {{ form.subtitulo }}
                {{ form.eje_x_titulo }}
                {{ form.eje_y_titulo }}
            </div>
            
            <div class="form-section">
                <h4>Configuración Visual</h4>
                <div class="form-row">
                    {{ form.mostrar_leyenda }}
                    {{ form.posicion_leyenda }}
                </div>
                <div class="form-row">
                    {{ form.mostrar_cuadricula }}
                    {{ form.mostrar_valores }}
                </div>
                {{ form.altura_grafico }}
                {{ form.begin_at_zero }}
            </div>
            
            <div class="form-section">
                <h4>Desagregaciones Predeterminadas</h4>
                <div class="desag-columns">
                    <div class="desag-geo">
                        <h5>Geográficas</h5>
                        {{ form.desagregaciones_geograficas }}
                    </div>
                    <div class="desag-tem">
                        <h5>Temáticas</h5>
                        {{ form.desagregaciones_tematicas }}
                    </div>
                </div>
            </div>
            
            <div class="form-section">
                <h4>Series del Gráfico</h4>
                <div id="series-formset">
                    {{ serie_formset.management_form }}
                    {% for serie_form in serie_formset %}
                    <div class="serie-form">
                        <h5>Serie {{ forloop.counter }}</h5>
                        {{ serie_form.desagregacion_geografica }}
                        {{ serie_form.desagregacion_tematica }}
                        {{ serie_form.nombre_personalizado }}
                        {{ serie_form.color }}
                        {{ serie_form.orden }}
                    </div>
                    {% endfor %}
                </div>
                <button type="button" id="add-serie">
                    <i class="fas fa-plus"></i> Agregar Serie
                </button>
            </div>
        </div>
        
        <!-- Preview del gráfico -->
        <div class="grafico-preview">
            <h3>Vista Previa</h3>
            <div id="preview-chart"></div>
            <p class="text-muted">El gráfico se actualizará al cambiar opciones</p>
        </div>
    </div>
    
    <div class="wizard-actions">
        <button type="button" class="btn-secondary" id="skip-graficos">
            Saltar - Crear Después
        </button>
        <button type="button" class="btn-primary" id="add-otro-grafico">
            <i class="fas fa-plus"></i> Crear Otro Gráfico
        </button>
        <button type="submit" class="btn-success">
            <i class="fas fa-check"></i> Finalizar
        </button>
    </div>
</div>
```

---

## 🚀 Próximos Pasos

Una vez aprobado este diseño:
1. Implementar clase `WizardAdminUnificado`
2. Crear formularios para cada paso
3. Implementar lógica de pasos dinámicos
4. Integrar Univer.js en pasos de preview
5. Crear formularios y formsets de gráficos
6. Crear templates con componentes visuales
7. Integrar con procesamiento normalizado (Fase 1)

---

**Estado:** 🎨 Diseño en Revisión  
**Fecha:** 2025-01-20  
**Actualizado:** Agregado Univer.js y Gráficos  
**Pendiente:** Aprobación y ajustes del usuario
