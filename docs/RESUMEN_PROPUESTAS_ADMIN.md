# Resumen Ejecutivo: Mejoras al Flujo de Administración

## 🎯 Contexto

El equipo técnico utiliza el **módulo de recolección** para subir:
- Series de datos de indicadores (datos.xlsx + metadata.xlsx)
- Archivos de microdata (microdata.xlsx + metadata_variables.xlsx)

El **administrador** debe procesar estos archivos para:
1. Crear/actualizar indicadores
2. Cargar metadata automáticamente
3. Crear reglas de extracción (si hay microdata)
4. Procesar datos (cartesiano o importación directa)

---

## 🔴 Problemas Actuales

### 1. Botones de Procesamiento Inconsistentes

**Desde Reglas de Extracción:**
- ✅ Muestra diagnóstico
- ✅ Pide confirmación
- ✅ Logs en tiempo real

**Desde Indicadores:**
- ❌ No muestra diagnóstico
- ❌ Procesa directamente
- ❌ Sin logs en tiempo real

### 2. Wizard Actual No Encaja

El wizard existente (`wizard_views.py`):
- ❌ Asume flujo lineal rígido
- ❌ No aprovecha cargas del módulo de recolección
- ❌ No contempla caso "solo series sin microdata"
- ❌ No carga metadata automáticamente

### 3. Múltiples Pestañas Abiertas

El admin debe:
- Abrir cargas pendientes
- Crear microdata
- Crear variables manualmente
- Crear indicador
- Copiar/pegar metadata
- Crear regla de extracción
- Procesar datos

**Resultado:** Proceso tedioso y propenso a errores

---

## ✅ Soluciones Propuestas

### Propuesta 1: Normalizar Botones de Procesamiento (Prioridad ALTA)

**Objetivo:** Que ambos botones usen el mismo flujo con diagnóstico y logs.

**Cambios:**
```python
# admin.py - IndicadorAdmin

def procesar_microdata_button(self, obj):
    # ANTES: Redirigía a procesar_microdata() directo
    # AHORA: Redirige a diagnostico_y_procesamiento()
    url = reverse('admin:indicador_diagnostico_procesamiento', args=[obj.id])
    return format_html('<a class="button" href="{}">🔄 Procesar Microdata</a>', url)

def diagnostico_y_procesamiento(self, request, indicador_id):
    """
    Flujo unificado:
    1. GET: Ejecutar diagnóstico
    2. Mostrar salida
    3. Pedir confirmación
    4. POST: Crear ProcesoExtraccion
    5. Lanzar en background
    6. Redirigir a visor en vivo
    """
    # Implementación igual que ReglaExtraccionAdmin.procesar_datos()
```

**Beneficio:** Experiencia consistente, siempre con diagnóstico y logs.

**Archivo:** `docs/PROPUESTA_NORMALIZACION_PROCESAMIENTO.md`

---

### Propuesta 2: Wizard Admin Unificado (Prioridad MEDIA)

**Objetivo:** Wizard adaptativo que se ajusta al caso de uso y carga metadata automáticamente.

**Casos de Uso:**

#### Caso 1: Indicador con Microdata
```
1. Seleccionar CargaMicrodata pendiente
2. Preview de microdata
3. Crear/asociar Microdata
4. Cargar VariableMicrodata automáticamente desde metadata_variables.csv
5. Crear/asociar Indicador
6. Cargar metadata del indicador automáticamente desde metadata.csv
7. Verificar dominios y desagregaciones (crear faltantes)
8. Crear ReglaExtraccion
9. Diagnóstico
10. Procesamiento con logs
```

#### Caso 2: Indicador sin Microdata (Solo Series)
```
1. Seleccionar CargaSerieIndicador pendiente
2. Preview de datos
3. Crear/asociar Indicador
4. Cargar metadata automáticamente desde metadata.csv
5. Verificar desagregaciones (crear faltantes)
6. Importar datos directamente con matching de desagregaciones
```

#### Caso 3: Actualizar Indicador Existente
```
1. Seleccionar indicador existente
2. Seleccionar nueva carga
3. Mostrar diferencias de metadata
4. Actualizar metadata
5. Importar nuevos datos
```

**Características Clave:**
- ✅ Pasos dinámicos según caso de uso
- ✅ Carga automática de metadata desde CSV
- ✅ Verificación de desagregaciones con sugerencias
- ✅ Creación asistida de elementos faltantes
- ✅ Integración con cargas del módulo de recolección

**Beneficio:** Proceso guiado que reduce errores y tiempo.

---

### Propuesta 3: Panel de Cargas Pendientes (Prioridad MEDIA)

**Objetivo:** Vista centralizada de todas las cargas pendientes con acceso directo al wizard.

**Ubicación:** Admin → Dashboard o menú lateral

**Contenido:**
```
┌─────────────────────────────────────────────────────┐
│ 📥 Cargas Pendientes del Módulo de Recolección      │
├─────────────────────────────────────────────────────┤
│                                                      │
│ 🗂️ Microdata (3 pendientes)                         │
│ ┌──────────────────────────────────────────────┐   │
│ │ CMIC-20250120-143055                         │   │
│ │ Usuario: jperez | Fecha: 2025-01-20          │   │
│ │ Archivos: microdata.csv, metadata_vars.csv   │   │
│ │ [🔄 Procesar con Wizard]                     │   │
│ └──────────────────────────────────────────────┘   │
│                                                      │
│ 📊 Series de Indicadores (5 pendientes)             │
│ ┌──────────────────────────────────────────────┐   │
│ │ CSIND-20250120-145511                        │   │
│ │ Usuario: mgarcia | Fecha: 2025-01-20         │   │
│ │ Archivos: datos.csv, metadata.csv            │   │
│ │ [🔄 Procesar con Wizard]                     │   │
│ └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Beneficio:** Punto de entrada claro para procesar cargas.

---

## 📋 Plan de Implementación

### Fase 1: Normalización (1-2 días) ⭐ PRIORIDAD
- [ ] Modificar `IndicadorAdmin.procesar_microdata_button()`
- [ ] Crear `IndicadorAdmin.diagnostico_y_procesamiento()`
- [ ] Probar ambos flujos
- [ ] Documentar

### Fase 2: Wizard Unificado (1 semana)
- [ ] Diseñar estructura de pasos dinámicos
- [ ] Implementar FormSeleccionFuente
- [ ] Implementar parsers de CSV (metadata indicador, metadata variables)
- [ ] Implementar verificación de desagregaciones
- [ ] Implementar creación asistida de elementos faltantes
- [ ] Integrar con procesamiento unificado (Fase 1)
- [ ] Testing completo de casos de uso

### Fase 3: Panel de Cargas (2-3 días)
- [ ] Crear vista de cargas pendientes
- [ ] Agregar al dashboard admin
- [ ] Botones de acceso rápido al wizard
- [ ] Filtros y búsqueda

---

## 🎨 Mockups Visuales

### Botón Normalizado
```
┌─────────────────────────────────────────────────────┐
│ Indicadores                                          │
├──────────┬─────────┬───────┬────────┬──────────────┤
│ Nombre   │ Subtema │ Orden │ Activo │ Acciones     │
├──────────┼─────────┼───────┼────────┼──────────────┤
│ TMM5     │ Mortal. │ 1     │ ✓      │ [🔄 Procesar]│
│          │         │       │        │ [📥 Importar]│
│          │         │       │        │ [📊 Datos]   │
└──────────┴─────────┴───────┴────────┴──────────────┘

Al hacer clic en "🔄 Procesar":
1. Ejecuta diagnóstico
2. Muestra resultado
3. Pide confirmación
4. Procesa con logs en vivo
```

### Wizard - Paso 1
```
┌─────────────────────────────────────────────────────┐
│ Wizard de Procesamiento - Paso 1 de 5               │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                      │
│ ¿Qué deseas procesar?                               │
│                                                      │
│ ┌──────────────┐ ┌──────────────┐                  │
│ │ 📥 Cargas    │ │ 📤 Subir     │                  │
│ │ Pendientes   │ │ Ahora        │                  │
│ │              │ │              │                  │
│ │ 8 pendientes │ │ Nuevo archivo│                  │
│ └──────────────┘ └──────────────┘                  │
│                                                      │
│ Si seleccionas "Cargas Pendientes":                 │
│ ┌────────────────────────────────────────────┐     │
│ │ CMIC-20250120-143055                       │     │
│ │ ○ Usuario: jperez | Fecha: 2025-01-20     │     │
│ │   microdata.csv (2.5 MB)                   │     │
│ │   metadata_variables.csv (50 KB)           │     │
│ └────────────────────────────────────────────┘     │
│                                                      │
│ [Cancelar] [Siguiente →]                            │
└─────────────────────────────────────────────────────┘
```

### Wizard - Verificación de Desagregaciones
```
┌─────────────────────────────────────────────────────┐
│ Wizard de Procesamiento - Paso 4 de 5               │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                      │
│ Verificación de Desagregaciones                     │
│                                                      │
│ 📍 Desagregaciones Geográficas                      │
│ ✅ 5 existentes | ⚠️ 2 faltantes                    │
│                                                      │
│ Faltantes:                                          │
│ • Comuna 22 (sugerido: Dominio "Comunas")          │
│ • Barrio El Refugio (sugerido: Dominio "Barrios")  │
│                                                      │
│ [✨ Crear Faltantes Automáticamente]                │
│                                                      │
│ 🏷️ Desagregaciones Temáticas                        │
│ ✅ 8 existentes | ⚠️ 0 faltantes                    │
│                                                      │
│ [← Anterior] [Siguiente →]                          │
└─────────────────────────────────────────────────────┘
```

---

## 💡 Beneficios Esperados

### Para el Administrador
- ⏱️ **Reducción de tiempo:** De 30 min a 5 min por indicador
- 🎯 **Menos errores:** Validaciones automáticas
- 🧠 **Menos carga cognitiva:** Proceso guiado
- 📊 **Visibilidad:** Siempre sabe qué está pasando

### Para el Sistema
- 🔄 **Consistencia:** Un solo flujo bien probado
- 🛠️ **Mantenibilidad:** Código centralizado
- 📈 **Escalabilidad:** Fácil agregar nuevos casos de uso
- 🐛 **Debugging:** Logs completos de cada paso

---

## 🚀 Recomendación

**Implementar en orden:**

1. **AHORA (Fase 1):** Normalizar botones de procesamiento
   - Impacto: Alto
   - Esfuerzo: Bajo
   - Tiempo: 1-2 días

2. **PRÓXIMO (Fase 2):** Wizard unificado
   - Impacto: Muy Alto
   - Esfuerzo: Medio
   - Tiempo: 1 semana

3. **DESPUÉS (Fase 3):** Panel de cargas
   - Impacto: Medio
   - Esfuerzo: Bajo
   - Tiempo: 2-3 días

---

**Fecha:** 2025-01-20  
**Autor:** Análisis del Sistema SIIED  
**Estado:** Propuesta para revisión
