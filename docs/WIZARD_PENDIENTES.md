# Tareas Pendientes para Completar el Wizard Admin Unificado

## ✅ Completado

1. **Clase Base del Wizard** (`wizard_admin_unificado.py`)
   - Lógica de pasos dinámicos
   - Soporte para 4 flujos (A, B, C, D)
   - Métodos de procesamiento

2. **Formularios** (`wizard_unificado_forms.py`)
   - 20+ formularios para todos los pasos
   - Validaciones específicas por flujo

3. **Parsers de CSV** (`wizard_parsers.py`)
   - Parser de metadata de variables
   - Parser de metadata de indicadores
   - Analizador de desagregaciones

4. **Helpers** (`wizard_helpers.py`)
   - Creador de desagregaciones faltantes
   - Creador de variables desde metadata
   - Actualizador de metadata de indicadores

5. **UI en Admin Index**
   - Sección destacada con acceso al wizard
   - Descripción de flujos y características

## 🔴 Pendiente para Funcionalidad Completa

### 1. Agregar URL del Wizard

**Archivo:** `indicadores/urls.py`

```python
from .wizard_admin_unificado import WizardAdminUnificado

urlpatterns = [
    # ... otras rutas ...
    path('admin/wizard/', WizardAdminUnificado.as_view(), name='wizard_admin_unificado'),
]
```

### 2. Crear Templates Base

**Archivos necesarios:**
- `indicadores/templates/admin/wizard_unificado/base.html`
- `indicadores/templates/admin/wizard_unificado/seleccion_fuente.html`
- Templates para cada paso de cada flujo (20+ templates)

### 3. Integrar Univer.js en Templates de Preview

**Templates que necesitan Univer.js:**
- `preview_microdata.html`
- `preview_serie.html`
- `preview_ambos.html`
- `validar_serie.html`

### 4. Implementar Métodos de Procesamiento Final

**En `wizard_admin_unificado.py`:**
- `_procesar_flujo_a()`: Crear microdata, indicador, regla, ejecutar procesamiento
- `_procesar_flujo_b()`: Crear indicador, importar datos directamente
- `_procesar_flujo_c()`: Combinar ambos + validación
- `_procesar_flujo_d()`: Actualizar indicador existente

### 5. Implementar Formsets de Gráficos

**Archivo:** `wizard_unificado_forms.py`

Agregar:
- `FormularioGrafico` completo con todos los campos
- `FormularioSerie` para series del gráfico
- `SerieFormSet` con formset_factory

### 6. Integrar con Fase 1 (Procesamiento Normalizado)

**Conectar con:**
- `diagnostico_y_procesamiento()` del admin
- Método `diagnosticar_microdata` existente
- Creación de `ProcesoExtraccion` y logs en vivo

## 📝 Notas Importantes

### Sobre Microdata → Indicadores

**Relación:** 1 Microdata → N Indicadores

**Flujo correcto:**
1. Usuario ejecuta wizard con `CargaMicrodata` pendiente
2. En Paso 3A: Selecciona "Crear Nueva Microdata" o "Asociar Existente"
3. En Paso 5A: Selecciona "Crear Nuevo Indicador" o "Asociar Existente"
4. Si quiere crear OTRO indicador de la MISMA microdata:
   - Ejecuta wizard nuevamente
   - Selecciona "Asociar Microdata Existente"
   - Crea nuevo indicador con diferente ReglaExtraccion

**Ejemplo real (Población):**
- 1 Microdata: "Proyecciones de Población 2024"
- Indicador 1: "Población Total por Comuna"
  - ReglaExtraccion: `SUM(poblacion) GROUP BY comuna`
- Indicador 2: "Población por Sexo y Grupo de Edad"
  - ReglaExtraccion: `SUM(poblacion) GROUP BY sexo, grupo_edad`
- Indicador 3: "Densidad Poblacional"
  - ReglaExtraccion: `SUM(poblacion) / area_km2 GROUP BY comuna`

### Prioridad de Implementación

**Alta Prioridad (para MVP):**
1. URL del wizard
2. Template base + selección de fuente
3. Templates de Flujo A (con microdata)
4. Método `_procesar_flujo_a()` completo
5. Integración con diagnóstico existente

**Media Prioridad:**
1. Templates de Flujo B y C
2. Métodos de procesamiento B y C
3. Formsets de gráficos

**Baja Prioridad:**
1. Flujo D (actualizar existente)
2. Optimizaciones de UI
3. Tests automatizados

## 🚀 Siguiente Paso Recomendado

Crear la URL y el template base para poder probar el wizard end-to-end, aunque sea con funcionalidad parcial.
