# Instrucciones para Cargar Ficha Técnica de Indicadores

## Resumen
Se ha creado un comando de Django para cargar automáticamente los datos de la ficha técnica desde el archivo CSV a los indicadores existentes en la base de datos.

## Archivo de Origen
**Ruta**: `docs/insumos/ficha_tecnica_indicadores.csv`

Este archivo contiene 21 campos por indicador que se mapean al modelo `Indicador`.

## Comando de Carga

### Sintaxis Básica
```bash
python3 manage.py cargar_ficha_tecnica
```

### Opciones Disponibles

#### 1. Especificar ruta del CSV (opcional)
```bash
python3 manage.py cargar_ficha_tecnica --csv-path=/ruta/al/archivo.csv
```
Por defecto usa: `docs/insumos/ficha_tecnica_indicadores.csv`

#### 2. Modo Dry-Run (recomendado para primera ejecución)
```bash
python3 manage.py cargar_ficha_tecnica --dry-run
```
Este modo **NO guarda cambios** en la base de datos, solo muestra qué se actualizaría.

### Ejemplo de Uso Completo

**Paso 1**: Ejecutar en modo dry-run para verificar
```bash
python3 manage.py cargar_ficha_tecnica --dry-run
```

**Paso 2**: Si todo se ve bien, ejecutar sin dry-run
```bash
python3 manage.py cargar_ficha_tecnica
```

## Cómo Funciona

### Mapeo de Campos CSV → Modelo

| Campo CSV | Campo Modelo | Tipo |
|-----------|--------------|------|
| Codigo_Indicador | codigo_indicador | CharField |
| Sigla | sigla | CharField |
| Grupo_Indicador | grupo_indicador | CharField |
| Nombre_Indicador | descripcion | TextField |
| Definiciones_Conceptos | definiciones_conceptos | CKEditor5Field |
| Objetivo | objetivo | CKEditor5Field |
| Justificacion | justificacion | CKEditor5Field |
| Metodo_Medicion | metodo_medicion | CKEditor5Field |
| Formula | formula_ficha | TextField |
| Variables | variables | CKEditor5Field |
| Unidad_Medida | unidad_medida | CharField |
| Valores_Referencia | valores_referencia | CKEditor5Field |
| Linea_Base | linea_base | CharField |
| Desagregacion_Tematica | desagregacion_tematica_texto | TextField |
| Desagregacion_Geografica | desagregacion_geografica_texto | TextField |
| Periodicidad | periodicidad | CharField |
| Fuente_Datos | fuente_datos | CharField |
| Responsable | responsable | CharField |
| Observaciones | observaciones | CKEditor5Field |
| Fecha_Elaboracion | fecha_elaboracion | DateField |
| Fecha_Actualizacion | fecha_actualizacion | DateField |

### Lógica de Búsqueda de Indicadores

El script busca indicadores en este orden:
1. **Por código**: Busca por `codigo_indicador` (campo único)
2. **Por nombre**: Si no encuentra por código, busca por `nombre` exacto

Si no encuentra el indicador, lo registra en la lista de "no encontrados" y continúa con el siguiente.

## Visualización en el Frontend

### Ficha Técnica Actualizada
La ficha técnica en `subtema_detalle.html` ahora muestra **21 campos** (anteriormente solo 7).

### Ocultamiento Automático de Campos Vacíos
**Importante**: Los campos que no tengan valor en el CSV **NO se mostrarán** en la ficha técnica del frontend.

La lógica implementada oculta campos que:
- Sean `null`
- Sean `undefined`
- Sean cadenas vacías `""`
- Sean la cadena `"None"` o `"null"`

### Ejemplo de Visualización
Si un indicador solo tiene estos campos llenos:
- Código del Indicador
- Sigla
- Descripción
- Unidad de Medida
- Fuente de Datos

Solo esos 5 campos aparecerán en la tabla de ficha técnica.

## API Actualizada

El endpoint `/api/get_indicadores_simple/?indicador_id=X` ahora retorna todos los 21 campos de la ficha técnica.

### Ejemplo de Respuesta
```json
[
  {
    "id": 1,
    "nombre": "Tasa de mortalidad de niños menores de 5 años",
    "codigo_indicador": "ICET_SAL_DEM_MOR_02",
    "sigla": "TMM5",
    "grupo_indicador": "ICET",
    "descripcion": "...",
    "definiciones_conceptos": "...",
    "objetivo": "...",
    "justificacion": "...",
    "metodo_medicion": "...",
    "formula_ficha": "TMM5 = (V₁ / V₂) × 1.000",
    "variables": "...",
    "unidad_medida": "Número de muertes por cada 1.000 nacidos vivos",
    "valores_referencia": "...",
    "linea_base": "Valor año 2022: 10,89",
    "desagregacion_tematica_texto": "Grupo de edad",
    "desagregacion_geografica_texto": "Distrital",
    "periodicidad": "Anual",
    "fuente_datos": "Calculos propios con base en datos del DANE",
    "responsable": "Departamento Administrativo de Planeación",
    "observaciones": "...",
    "fecha_elaboracion": "2025-09-16",
    "fecha_actualizacion": "2025-09-16"
  }
]
```

## Descarga de Ficha Técnica

Los usuarios pueden descargar la ficha técnica completa en dos formatos:
- **CSV**: Botón "Descargar Ficha Técnica CSV"
- **Excel**: Botón "Descargar Ficha Técnica en Microsoft Excel"

Ambos formatos incluyen todos los campos disponibles (solo los que tienen valor).

## Notas Importantes

1. **Códigos Únicos**: Asegúrese de que cada indicador tenga un `codigo_indicador` único en el CSV
2. **Formato de Fechas**: Las fechas deben estar en formato `YYYY-MM-DD` (ej: 2025-09-16)
3. **Campos Vacíos**: Los campos vacíos en el CSV se guardarán como `NULL` en la base de datos
4. **Backup**: Recomendado hacer backup de la base de datos antes de ejecutar la carga
5. **Indicadores Nuevos**: Este script solo actualiza indicadores existentes, no crea nuevos

## Solución de Problemas

### Indicador No Encontrado
Si el script reporta que no encuentra un indicador:
1. Verifique que el `Codigo_Indicador` en el CSV coincida con el campo `codigo_indicador` en la BD
2. Si el indicador no tiene código, verifique que el `Nombre_Indicador` coincida exactamente
3. Verifique que el indicador esté marcado como `activo=True`

### Error de Formato de Fecha
Si hay error al parsear fechas:
- Asegúrese de que las fechas estén en formato `YYYY-MM-DD`
- Ejemplo correcto: `2025-09-16`
- Ejemplo incorrecto: `16/09/2025` o `2025-9-16`

### Campos con HTML
Los campos tipo `CKEditor5Field` aceptan HTML. Si el CSV contiene HTML, se guardará correctamente.

## Mantenimiento

Para actualizar la ficha técnica de indicadores:
1. Edite el archivo CSV `docs/insumos/ficha_tecnica_indicadores.csv`
2. Ejecute el comando: `python3 manage.py cargar_ficha_tecnica`
3. Los cambios se reflejarán inmediatamente en el frontend
