# 🎨 Análisis UX Crítico - Parte 1: Usuarios y Flujos

**Fecha:** 3 de Noviembre de 2025  
**Rol:** UX Designer  
**Alcance:** Análisis exhaustivo de casos de uso y experiencia del usuario

---

## 📊 Mapa de Usuarios y Perfiles

### **Usuario 1: Ciudadano / Público General**
**Objetivos:**
- Consultar indicadores de la ciudad
- Entender datos estadísticos
- Descargar información pública
- Conocer el estado de la ciudad

**Puntos de acceso:**
- Home pública (`/`)
- Dominios (`/dominio/`)
- Visor comparativo (`/visor-comparativo/`)
- Explorador de microdata (`/microdata/explorer/`)
- Chat semántico (`/chat/`)

**Nivel técnico:** Bajo a medio
**Frecuencia de uso:** Ocasional

---

### **Usuario 2: Recolector de Datos**
**Objetivos:**
- Cargar series de indicadores
- Cargar archivos de microdata
- Seguimiento de cargas realizadas
- Cumplir con plazos de entrega

**Puntos de acceso:**
- Login recolección (`/recoleccion/login/`)
- Dashboard recolección (`/recoleccion/`)
- Cargar serie (`/recoleccion/cargar-serie/`)
- Cargar microdata (`/recoleccion/cargar-microdata/`)
- Historial (`/recoleccion/historial-series/`)

**Nivel técnico:** Medio
**Frecuencia de uso:** Alta (diaria/semanal)

---

### **Usuario 3: Consultor de Reportes**
**Objetivos:**
- Generar reportes de indicadores
- Descargar datos masivos
- Exportar metadata
- Análisis de información

**Puntos de acceso:**
- Login reportes (`/reportes/login/`)
- Dashboard reportes (`/reportes/`)
- Reportes indicadores (`/reportes/indicadores/`)
- Reportes microdata (`/reportes/microdata/`)

**Nivel técnico:** Medio a alto
**Frecuencia de uso:** Media (semanal/mensual)

---

### **Usuario 4: Administrador / Staff**
**Objetivos:**
- Gestionar indicadores completos
- Procesar microdata a indicadores
- Configurar dominios y desagregaciones
- Administrar usuarios y permisos
- Monitorear calidad de datos

**Puntos de acceso:**
- Django Admin (`/admin/`)
- Wizard unificado (`/admin/wizard/`)
- Diagnóstico (`diagnosticar_microdata`)
- Proceso en vivo (`/procesos/<id>/`)
- Dashboard de cargas (`/dashboard-cargas/`)

**Nivel técnico:** Alto
**Frecuencia de uso:** Alta (diaria)

---

## 🔀 Análisis Crítico de Flujos por Usuario

### **FLUJO A: Ciudadano Consulta Indicador**

#### Path Happy:
```
Home → Dominios → Tema → Subtema → Indicador → Visualización
```

#### ✅ Fortalezas:
1. **Jerarquía clara:** Dominio > Tema > Subtema > Indicador (lógica)
2. **Home atractivo:** Sliders con datos destacados, visual impactante
3. **Múltiples puntos de entrada:** 
   - Visor comparativo
   - Explorador de microdata
   - Chat semántico
   - ODS directos

#### ❌ Problemas Críticos:

**P1: Sobrecarga cognitiva en Home**
- **Qué:** Demasiados elementos compitiendo por atención
- **Impacto:** Usuario no sabe por dónde empezar
- **Evidencia:** 
  - Slider con 6 diapositivas
  - 3 cards de acceso rápido
  - Noticias institucionales
  - Banners promocionales
  - Footer con múltiples secciones
- **Recomendación:** Jerarquizar contenido, reducir opciones iniciales

**P2: Navegación inconsistente**
- **Qué:** Rutas largas y complejas
- **Ejemplo:** `/dominio/<slug:dominio_slug>/<slug:tema_slug>/<slug:subtema_slug>/`
- **Problema:** Usuario pierde contexto en navegación profunda
- **Recomendación:** Breadcrumbs persistentes, migas de pan claras

**P3: Falta de ayuda contextual**
- **Qué:** No hay tooltips, onboarding ni guías
- **Impacto:** Usuario con nivel bajo no entiende qué es "microdata", "desagregación", etc.
- **Recomendación:** Glosario flotante, tooltips, tour guiado opcional

**P4: Chat semántico escondido**
- **Qué:** Herramienta poderosa pero no prominente
- **Ubicación actual:** Link en menú
- **Recomendación:** Bot flotante siempre visible (estilo ChatGPT)

**P5: Versiones 3D sin propósito claro**
- **Qué:** Existen rutas `-3d` pero no se explica cuándo usarlas
- **Ejemplo:** `/dominios-3d/`, `/dominio-detalle-3d/`
- **Problema:** Funcionalidad duplicada confunde
- **Recomendación:** Toggle en misma vista o eliminar si no aporta valor

---

### **FLUJO B: Recolector Carga Serie**

#### Path Happy:
```
Login Recolección → Dashboard → Cargar Serie → Upload CSV + Metadata → Validación → Confirmación
```

#### ✅ Fortalezas:
1. **Módulo separado:** No interfiere con admin principal
2. **Plantillas descargables:** Facilita tarea del recolector
3. **Historial claro:** Puede ver sus cargas previas

#### ❌ Problemas Críticos:

**P6: Doble módulo confuso (Recolección vs Reportes)**
- **Qué:** Dos logins, dos dashboards casi idénticos
- **URLs:**
  - `/recoleccion/login/` vs `/reportes/login/`
  - `/recoleccion/` vs `/reportes/`
- **Problema:** Usuario con ambos roles debe hacer login 2 veces
- **Evidencia código:**
  ```python
  # urls.py línea 97-98 vs 144-145
  path('recoleccion/login/', views_recoleccion.recoleccion_login)
  path('reportes/login/', views_reportes.reportes_login)
  ```
- **Recomendación:** **UNIFICAR** en un solo módulo con permisos dinámicos

**P7: Sin preview de datos antes de subir**
- **Qué:** No puede ver si su CSV es correcto antes de cargar
- **Impacto:** Carga con errores, debe reiniciar
- **Recomendación:** Vista previa con Univer.js (como en wizard admin)

**P8: Feedback de errores genérico**
- **Qué:** Si falla validación, mensajes poco descriptivos
- **Ejemplo:** "Error en fila 45" (¿qué error?)
- **Recomendación:** Mensajes específicos con sugerencias de corrección

**P9: No hay progreso de carga**
- **Qué:** Upload de archivos grandes sin indicador visual
- **Impacto:** Usuario no sabe si se está procesando o colgó
- **Recomendación:** Barra de progreso, estimación de tiempo

---

### **FLUJO C: Administrador Procesa Microdata → Indicador**

#### Path Actualizado (con Wizard Unificado):
```
Admin → Wizard Unificado → Seleccionar Fuente → Config Microdata → 
Config Indicador → Cargar Metadata → Verificar Desagregaciones → 
Regla Extracción → Diagnóstico → Mapeo Columnas → Confirmación → 
Proceso en Vivo
```

#### ✅ Fortalezas:
1. **Wizard modernizado:** Elimina wizard viejo, interfaz mejorada
2. **Detección automática:** Encoding, delimitadores, columnas
3. **Diagnóstico integrado:** Valida antes de procesar
4. **Logs en vivo:** Usuario ve progreso en tiempo real
5. **Preview con Univer.js:** Visualización moderna de Excel/CSV
6. **Múltiples flujos:** A, B, C, D según caso de uso

#### ❌ Problemas Críticos:

**P10: Complejidad del Wizard (11+ pasos)**
- **Qué:** Flujo A tiene 11 pasos mínimo
- **Problema:** Usuario experto se frustra con tantos pasos
- **Recomendación:** Modo "Express" para usuarios avanzados

**P11: Sin guardado de progreso**
- **Qué:** Si se cierra navegador, se pierde todo
- **Impacto:** Usuario debe empezar de cero
- **Recomendación:** Auto-save en sesión, opción "continuar más tarde"

**P12: Falta explicación de detección automática CSV**
- **Qué:** Nueva funcionalidad (columnas vs headers) no documentada en UI
- **Contexto:** Acabamos de implementar detección dual
- **Problema:** Usuario no sabe qué significa "CSV tipo columnas" vs "CSV tipo headers"
- **Recomendación:** 
  - Tooltip explicativo en paso de diagnóstico
  - Ejemplo visual de ambos formatos
  - Link a documentación

**P13: Diagnóstico oculto**
- **Qué:** `diagnosticar_microdata` es comando, no UI clara
- **Impacto:** Usuario no sabe que puede diagnosticar antes de procesar
- **Recomendación:** 
  - Botón "Diagnosticar" visible en paso de regla de extracción
  - Output de diagnóstico en UI (no solo terminal)

**P14: Proceso en vivo sin notificaciones**
- **Qué:** Usuario debe estar en la página viendo logs
- **Problema:** Procesos largos (10+ min) requieren atención constante
- **Recomendación:** 
  - Notificaciones por email al terminar
  - Notificaciones web push
  - Dashboard de procesos en ejecución

**P15: Sin rollback de errores**
- **Qué:** Si proceso falla a mitad, datos quedan inconsistentes
- **Problema:** Puede crear datos parciales que deben limpiarse manualmente
- **Recomendación:** Transacciones atómicas completas (revisar código)

---

### **FLUJO D: Administrador Gestiona Desagregaciones**

#### Path Happy:
```
Admin → Dominios Desagregación → Crear/Editar Dominio → 
Agregar Desagregaciones → Asignar a Indicador
```

#### ✅ Fortalezas:
1. **CRUD completo:** Todas las operaciones disponibles
2. **Jerarquía clara:** Dominio → Desagregación

#### ❌ Problemas Críticos:

**P16: No hay validación de duplicados**
- **Qué:** Puede crear desagregaciones con mismo nombre
- **Impacto:** Confusión en selección, datos ambiguos
- **Recomendación:** Validación unique_together en modelo

**P17: Sin gestión masiva**
- **Qué:** Crear 50 desagregaciones una por una (ej: edades 0-99)
- **Impacto:** Tarea tediosa, propensa a errores
- **Recomendación:** 
  - Importar desde CSV
  - Generador automático para rangos

**P18: Desagregaciones huérfanas**
- **Qué:** Puede eliminar dominio con desagregaciones asignadas a indicadores
- **Problema:** Indicadores quedan rotos
- **Recomendación:** 
  - Validar antes de eliminar
  - Reasignar o impedir eliminación

**P19: No hay preview de impacto**
- **Qué:** Al editar desagregación, no se muestra qué indicadores afecta
- **Impacto:** Cambios ciegos pueden romper datos
- **Recomendación:** Vista de "Indicadores afectados" antes de confirmar

---

##  📱 Análisis de Dispositivos

### Desktop (Administrador)
✅ **Bien diseñado:** Django Admin responsivo
✅ **Wizard funcional:** Pasos claros
❌ **Problema:** Tablas largas sin paginación optimizada

### Tablet (Consultor/Recolector)
⚠️ **Medio:** Funciona pero no optimizado
❌ **Problema:** Formularios muy largos en vertical
❌ **Problema:** Preview Univer.js puede ser lento

### Móvil (Ciudadano)
❌ **CRÍTICO:** Experiencia pobre
- Home con slider funciona
- **Problema P20:** Visor comparativo no es touch-friendly
- **Problema P21:** Gráficos interactivos difíciles de manipular
- **Problema P22:** Chat semántico no tiene versión móvil optimizada
- **Problema P23:** Don Datico 3D funciona bien (¡victoria!)

---

## 🎯 Resumen de Problemas por Severidad

### 🔴 **CRÍTICOS (Bloqueadores)**
1. **P6:** Doble módulo Recolección/Reportes confunde
2. **P10:** Wizard muy largo sin guardado
3. **P15:** Sin rollback de errores en procesamiento
4. **P20-23:** Experiencia móvil deficiente

### 🟠 **ALTOS (Impactan productividad)**
5. **P1:** Sobrecarga cognitiva en Home
6. **P7:** Sin preview de datos en recolección
7. **P12:** Detección CSV dual no explicada
8. **P14:** Proceso en vivo sin notificaciones
9. **P17:** Sin gestión masiva de desagregaciones
10. **P19:** Sin preview de impacto al editar

### 🟡 **MEDIOS (Mejoras UX)**
11. **P2:** Navegación inconsistente
12. **P3:** Falta ayuda contextual
13. **P8:** Feedback de errores genérico
14. **P11:** Sin guardado de progreso
15. **P16:** Sin validación de duplicados

### 🟢 **BAJOS (Nice to have)**
16. **P4:** Chat no prominente
17. **P5:** Versiones 3D confusas
18. **P9:** Sin barra de progreso upload
19. **P13:** Diagnóstico no visible en UI
20. **P18:** Desagregaciones huérfanas no validadas

---

**Siguiente parte:** Arquitectura de información y recomendaciones de diseño
