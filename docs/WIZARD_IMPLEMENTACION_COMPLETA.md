# Wizard Admin Unificado - Implementación Completa

## ✅ Estado: IMPLEMENTADO

**Fecha:** 3 de Noviembre de 2025  
**Versión:** 1.0

---

## 📋 Resumen

Se ha eliminado el wizard viejo y completado la implementación del Wizard Admin Unificado en la ruta `/admin/wizard/`. Este wizard proporciona un flujo adaptativo para procesar indicadores desde diferentes fuentes.

---

## 🗑️ Eliminaciones Realizadas

### Wizard Viejo (ELIMINADO)

- **Ruta eliminada:** `/admin/indicadores/indicador/wizard/crear/`
- **Archivos eliminados:**
  - `indicadores/wizard_views.py`
  - `indicadores/wizard_forms.py`
  - `indicadores/templates/admin/wizard_indicador.html`
  - `indicadores/templates/admin/wizard_resumen.html`
- **URL eliminada de:** `indicadores/admin.py` (línea 897)

---

## ✨ Implementación Nueva

### 1. Ruta Principal

**URL:** `http://127.0.0.1:8000/admin/wizard/`

Definida en `/myproject/urls.py` línea 39:
```python
path('admin/wizard/', views_recoleccion.wizard_admin_unificado, name='wizard_admin_unificado'),
```

### 2. Archivos Principales

#### A. Vista Principal
**Archivo:** `indicadores/views_recoleccion.py` (líneas 1081-1122)
- Función: `wizard_admin_unificado(request)`
- Detecta parámetros GET para pre-seleccionar cargas
- Configura almacenamiento temporal de archivos
- Instancia el wizard con formularios dinámicos

#### B. Clase del Wizard
**Archivo:** `indicadores/wizard_admin_unificado.py`
- Clase: `WizardAdminUnificado(SessionWizardView)`
- **Flujos soportados:**
  - **Flujo A:** Con Microdata (procesamiento cartesiano)
  - **Flujo B:** Solo Serie de Datos (importación directa)
  - **Flujo C:** Completo (Microdata + Serie para validación)
  - **Flujo D:** Actualizar Indicador Existente

#### C. Formularios
**Archivo:** `indicadores/wizard_unificado_forms.py`
- `FormSeleccionFuente` (Paso 1 - Común)
- `FormPreviewSerie` (Flujo B - Paso 2)
- `FormConfigIndicadorSerie` (Flujo B - Paso 3)
- `FormCargarMetadata` (Flujo B - Paso 4)
- `FormVerificarDesagregaciones` (Multi-flujo)
- `FormMapeoColumnas` (Flujo B - Paso 6)
- `FormConfirmacionSerie` (Flujo B - Paso 7)
- `FormPreviewMicrodata` (Flujo A - Paso 2)
- `FormConfigMicrodata` (Flujo A - Paso 3)
- `FormMetadataVariables` (Flujo A - Paso 4)
- `FormConfigIndicador` (Multi-flujo)
- `FormReglaExtraccion` (Flujos A y C)
- `FormDiagnostico` (Flujos A y C)
- `FormPreviewAmbos` (Flujo C)
- `FormValidarSerie` (Flujo C)
- `FormSeleccionarIndicador` (Flujo D)
- `FormSeleccionarCarga` (Flujo D)
- `FormCompararMetadata` (Flujo D)
- `FormConfirmarCambios` (Flujo D)
- `FormGraficos` (Común)
- `FormConfirmacion` (Final)

#### D. Utilidades
**Archivo:** `indicadores/utils_wizard.py`
- `DiagnosticoMicrodata`: Diagnóstico pre-procesamiento
- `ParseadorMetadata`: Parse de archivos metadata CSV
- `DetectorDesagregaciones`: Detección automática
- `AplicadorMetadata`: Aplicar metadata a indicadores
- `generar_output_diagnostico_html()`: Formatter para UI

#### E. Procesamiento Normalizado (NUEVO)
**Archivo:** `indicadores/procesamiento_normalizado.py`
- `procesar_microdata_a_indicador()`: Wrapper del comando cartesiano
- `procesar_serie_a_indicador()`: Importación directa de series
- `diagnosticar_microdata()`: Wrapper del comando diagnóstico
- `crear_graficos_automaticos()`: Generación automática de gráficos

### 3. Templates

**Directorio:** `indicadores/templates/admin/wizard_unificado/`

Archivos existentes:
- `base.html` (template base)
- `seleccion_fuente.html` (Paso 1)
- `preview_serie.html` (Flujo B)
- `config_indicador_serie.html`
- `cargar_metadata.html`
- `verificar_desag_b.html`
- `mapeo_columnas.html`
- `confirmacion_serie.html`
- `preview_microdata.html` (Flujo A)
- `config_microdata.html`
- `metadata_variables.html`
- `config_indicador.html`
- `verificar_desag_a.html`
- `regla_extraccion.html`
- `diagnostico.html`
- `seleccionar_indicador.html` (Flujo D)
- `seleccionar_carga.html`
- `comparar_metadata.html`
- `confirmar_cambios.html`

### 4. Integración con Sistema Existente

#### Comandos Reutilizados

El wizard envuelve estos comandos management existentes:

```bash
# Procesamiento cartesiano
python manage.py procesar_microdata_cartesiano --regla-id=<ID>

# Diagnóstico
python manage.py diagnosticar_microdata --microdata-id=<ID>
```

#### Modelos Utilizados

- `CargaMicrodata` (del módulo de recolección)
- `CargaSerieIndicador` (del módulo de recolección)
- `Microdata`
- `Indicador`
- `ReglaExtraccion`
- `VariableMicrodata`
- `Desagregacion`
- `DominioDesagregacion`
- `Grafico`
- `GraficoSerie`
- `MenuSubtema`
- `OperacionEstadistica`
- `Dato`

---

## 🔄 Flujos Implementados

### Flujo B: Solo Serie de Datos (MÁS SIMPLE)

```
Paso 1: Selección de Fuente
   ↓
Paso 2: Preview Serie (Univer.js)
   ↓
Paso 3: Configurar Indicador
   ↓
Paso 4: Cargar Metadata
   ↓
Paso 5: Verificar Desagregaciones
   ↓
Paso 6: Mapeo de Columnas
   ↓
Paso 7: Confirmación
   ↓
PROCESAMIENTO: Importación Directa
   ↓
Redirección: /admin/indicadores/indicador/<ID>/change/
```

**Resultado:**
- Indicador creado o actualizado
- Datos importados desde CSV
- Gráfico de línea generado automáticamente

### Flujo A: Con Microdata (PRODUCTO CARTESIANO)

```
Paso 1: Selección de Fuente
   ↓
Paso 2: Preview Microdata (Univer.js)
   ↓
Paso 3: Configurar Microdata
   ↓
Paso 4: Metadata de Variables
   ↓
Paso 5: Configurar Indicador
   ↓
Paso 6: Verificar Desagregaciones
   ↓
Paso 7: Crear Regla de Extracción
   ↓
Paso 8: Diagnóstico
   ↓
PROCESAMIENTO: Producto Cartesiano
   ↓
Redirección: /indicadores/procesos/<ID>/ (logs en vivo)
```

**Resultado:**
- Microdata registrada
- Variables de microdata cargadas
- Indicador creado o actualizado
- ReglaExtraccion creada
- Datos generados por producto cartesiano
- Proceso de extracción visible en vivo

### Flujo C: Completo (MICRODATA + VALIDACIÓN)

```
Paso 1: Selección de Fuente
   ↓
Paso 2: Preview Ambos Archivos
   ↓
Pasos 3-8: Igual que Flujo A
   ↓
PROCESAMIENTO: Producto Cartesiano
   ↓
Paso 9: Validar con Serie (comparación visual)
   ↓
Redirección
```

**Resultado:**
- Todo lo del Flujo A
- Validación cruzada con serie agregada
- Metadata del indicador desde CargaSerieIndicador

### Flujo D: Actualizar Existente

```
Paso 1: Selección de Fuente
   ↓
Paso 2: Seleccionar Indicador
   ↓
Paso 3: Seleccionar Nueva Carga
   ↓
Paso 4: Comparar Metadata (diff viewer)
   ↓
Paso 5: Confirmar Cambios
   ↓
PROCESAMIENTO: Actualización
   ↓
Redirección
```

**Resultado:**
- Indicador actualizado
- Datos: mantener/reemplazar/agregar (según selección)
- Metadata actualizada selectivamente

---

## 🎯 Características Implementadas

### 1. Detección Dinámica de Flujo

El wizard detecta automáticamente el flujo según la selección del usuario en el Paso 1:

```python
if carga_microdata and carga_serie:
    tipo_flujo = 'flujo_c'  # Completo
elif carga_microdata:
    tipo_flujo = 'flujo_a'  # Solo microdata
elif carga_serie:
    tipo_flujo = 'flujo_b'  # Solo serie
```

### 2. Preview con Univer.js

Integración con Univer.js para visualización interactiva de CSV/Excel antes del procesamiento.

### 3. Detección Automática

- **Encoding:** UTF-8, Latin-1, ISO-8859-1, CP1252
- **Delimitadores:** Automático con csv.Sniffer
- **Columna fecha:** Por palabras clave
- **Desagregaciones:** Por análisis de valores únicos

### 4. Validación Pre-Procesamiento

- Verificación de columnas fuente
- Detección de desagregaciones faltantes
- Diagnóstico completo antes del procesamiento cartesiano

### 5. Procesamiento Transaccional

Todo el procesamiento usa `transaction.atomic()` para garantizar consistencia.

### 6. Logs en Vivo

Para procesamiento cartesiano (Flujos A y C), se redirige a `/indicadores/procesos/<ID>/` donde se pueden ver logs en tiempo real.

### 7. Códigos de Evidencia

Las cargas desde el módulo de recolección generan códigos únicos:
- `CSIND-YYYYMMDD-HHMMSS` (Series)
- `CMIC-YYYYMMDD-HHMMSS` (Microdata)

---

## 📊 Integración con Módulo de Recolección

### Desde Dashboard de Cargas

Los administradores pueden acceder al wizard con cargas pre-seleccionadas:

```
/admin/cargas-dashboard/
   ↓ (clic en "Procesar en Wizard")
   ↓
/admin/wizard/?carga_microdata=<ID>
/admin/wizard/?carga_serie=<ID>
/admin/wizard/?carga_microdata=<ID>&carga_serie=<ID>
```

El wizard detecta estos parámetros GET y pre-llena el formulario.

---

## 🔧 Configuración Técnica

### Almacenamiento Temporal

```python
temp_storage_path = os.path.join(settings.MEDIA_ROOT, 'wizard_temp')
```

Los archivos subidos en el wizard se almacenan temporalmente aquí.

### Session Storage

El wizard usa `SessionWizardView` de `formtools`, almacenando datos intermedios en sesión del usuario.

### Verbosity Levels

El procesamiento cartesiano soporta niveles de verbosity:
- `0`: Sin output
- `1`: Básico (por defecto)
- `2`: Progreso cada 100 filas
- `3`: Detallado (cada dato creado)

---

## 🚀 Uso

### Para Administradores

1. Ir a `/admin/wizard/`
2. Seleccionar fuente (carga pendiente o subir nuevo)
3. Seguir pasos del wizard
4. Revisar resumen y confirmar
5. Ver procesamiento en vivo (si aplica)

### Desde Dashboard de Cargas

1. Ir a `/dashboard-cargas/`
2. Buscar carga pendiente
3. Clic en "Procesar en Wizard"
4. Wizard se abre con carga pre-seleccionada

### Desde Código

```python
from indicadores.procesamiento_normalizado import procesar_microdata_a_indicador

resultado = procesar_microdata_a_indicador(
    carga_microdata_id=1,
    regla_extraccion_id=5,
    eliminar_datos_previos=True,
    verbosity=2
)

if resultado['exitoso']:
    print(f"{resultado['registros_exitosos']} datos creados")
else:
    print(f"Error: {resultado['mensaje']}")
```

---

## 📝 Próximos Pasos (Opcionales)

### Mejoras Sugeridas

1. **Procesamiento Asíncrono:**
   - Integrar Celery para procesamiento en background
   - Actualizar estado vía WebSockets

2. **Wizard de Gráficos:**
   - Paso adicional para configurar múltiples gráficos
   - Formsets para series con desagregaciones

3. **Validación Cruzada Automática:**
   - Comparación automática microdata vs serie
   - Generación de reportes de discrepancias

4. **Auto-creación de Desagregaciones:**
   - Crear automáticamente desagregaciones faltantes
   - Asignar a dominios sugeridos

5. **Exportación de Configuración:**
   - Guardar configuración del wizard como JSON
   - Reutilizar en procesamiento futuro

---

## 🐛 Debugging

### Activar Logs Detallados

```python
# settings.py
LOGGING = {
    'loggers': {
        'indicadores': {
            'level': 'DEBUG',
        }
    }
}
```

### Ver Storage del Wizard

```python
# En template o view
{{ wizard.storage.extra_data }}
{{ wizard.storage.data }}
```

### Limpiar Sesión del Wizard

```python
# En shell
from django.contrib.sessions.models import Session
Session.objects.all().delete()
```

---

## ✅ Checklist de Implementación

- [x] Eliminar wizard viejo
- [x] Crear procesamiento_normalizado.py
- [x] Implementar WizardAdminUnificado
- [x] Crear todos los formularios
- [x] Implementar get_form_list() dinámico
- [x] Implementar process_step()
- [x] Implementar get_context_data()
- [x] Implementar done() con procesamiento
- [x] Implementar _procesar_flujo_a()
- [x] Implementar _procesar_flujo_b()
- [x] Implementar _procesar_flujo_c()
- [x] Implementar _procesar_flujo_d()
- [x] Crear templates para todos los pasos
- [x] Integrar con módulo de recolección
- [x] Documentar implementación

---

## 📚 Referencias

- **Documentación Original:** `docs/WIZARD_FLUJO_DINAMICO.md`
- **Django Form Tools:** https://django-formtools.readthedocs.io/
- **Univer.js:** https://univer.ai/
- **Comando Cartesiano:** `management/commands/procesar_microdata_cartesiano.py`
- **Flujo de Datos:** `docs/FLUJO_DATOS_RECOLECCION.md`

---

**Fin del Documento**
