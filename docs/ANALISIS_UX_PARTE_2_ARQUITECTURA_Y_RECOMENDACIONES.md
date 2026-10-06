# 🎨 Análisis UX Crítico - Parte 2: Arquitectura y Recomendaciones

**Fecha:** 3 de Noviembre de 2025  
**Rol:** UX Designer  
**Enfoque:** Arquitectura de información, patrones de diseño y roadmap de mejoras

---

## 🏗️ Arquitectura de Información Actual

### **Estructura de URLs (163 rutas)**

#### **Área Pública (26 rutas)**
```
/                                    # Home
/dominio/                            # Lista dominios
/dominio/<slug>/                     # Detalle dominio
/dominio/<slug>/<slug>/              # Tema
/dominio/<slug>/<slug>/<slug>/       # Subtema
/visor-comparativo/                  # Comparador
/microdata/explorer/                 # Explorador
/chat/                               # Chat semántico
/infraestructura/                    # Infraestructura info
...
```

#### **Área Recolección (14 rutas)**
```
/recoleccion/login/
/recoleccion/                        # Dashboard
/recoleccion/cargar-serie/
/recoleccion/cargar-microdata/
/recoleccion/historial-series/
...
```

#### **Área Reportes (8 rutas) - DUPLICADO**
```
/reportes/login/
/reportes/                           # Dashboard casi idéntico
/reportes/indicadores/
/reportes/microdata/
...
```

#### **Admin (120+ rutas)**
```
/admin/
/admin/wizard/                       # Wizard unificado
/procesos/<id>/                      # Proceso en vivo
/dashboard-cargas/
...
```

### 🚨 **PROBLEMA DE ARQUITECTURA #1: Duplicación Recolección/Reportes**

**Análisis:**
- 22 rutas (14 + 8) hacen básicamente lo mismo
- Dos logins separados innecesarios
- Código duplicado en `views_recoleccion.py` y `views_reportes.py`

**Impacto:**
- Mantenimiento doble
- Confusión de usuarios con ambos roles
- Inconsistencias entre módulos

**Solución propuesta:**
```python
# ANTES (duplicado)
/recoleccion/login/
/reportes/login/

# DESPUÉS (unificado)
/workspace/login/
/workspace/                          # Dashboard único
/workspace/upload/                   # Cargar (si tiene permiso)
/workspace/reports/                  # Reportes (si tiene permiso)
/workspace/history/                  # Historial
```

**Beneficios:**
- 50% menos rutas
- Un solo login
- Menú dinámico según permisos
- Código DRY

---

## 🎯 Patrones de Diseño Detectados

### **Patrón 1: Wizard Multi-Step** ✅
**Usado en:** Wizard Admin Unificado
**Fortalezas:**
- Descompone tarea compleja
- Validación por paso
- Progreso visual

**Debilidades:**
- 11+ pasos es demasiado
- Sin skip para expertos
- Sin guardado intermedio

**Recomendación:**
```
MODO BÁSICO (actual): 11 pasos guiados
MODO EXPERTO (nuevo): 3 pasos
  1. Subir archivos
  2. Configuración rápida (formulario compacto)
  3. Procesar
```

---

### **Patrón 2: Proceso en Vivo** ✅
**Usado en:** `/procesos/<id>/`
**Fortalezas:**
- Feedback tiempo real
- Logs visibles
- Auto-refresh con polling

**Debilidades:**
- Usuario debe estar en página
- Sin notificaciones externas
- Sin historial de procesos

**Recomendación:**
```javascript
// Agregar Web Push API
if ('Notification' in window) {
  // Solicitar permiso
  Notification.requestPermission().then(permission => {
    if (permission === 'granted') {
      // Enviar notificación cuando proceso termine
      fetch('/api/procesos/${id}/subscribe/', {
        method: 'POST',
        body: JSON.stringify({endpoint: subscription})
      });
    }
  });
}
```

---

### **Patrón 3: Chat Semántico** ✅
**Usado en:** `/chat/`
**Fortalezas:**
- RAG con embeddings
- Tools para búsqueda
- Streaming de respuestas

**Debilidades:**
- No prominente en UI
- Solo desktop
- Sin historial persistente

**Recomendación:**
```html
<!-- Bot flotante siempre visible -->
<div id="chat-bubble" class="fixed bottom-4 right-4 z-50">
  <button class="w-16 h-16 bg-cyan-500 rounded-full shadow-lg">
    <i class="fas fa-comment-dots"></i>
  </button>
</div>

<!-- Panel desplegable -->
<div id="chat-panel" class="fixed bottom-20 right-4 w-96 h-[600px] 
     bg-white rounded-lg shadow-2xl hidden">
  <!-- Chat interface -->
</div>
```

---

## 📊 Propuesta de Reorganización

### **Nuevo Mapa de Sitio**

```
PÚBLICO
├── Home (/)
├── Explorar Indicadores
│   ├── Por Dominio (/dominios/)
│   ├── Por Tema (/temas/)
│   ├── Búsqueda (/buscar/)
│   └── ODS (/ods/)
├── Herramientas
│   ├── Visor Comparativo (/visor/)
│   ├── Explorador Microdata (/explorador/)
│   └── Mapas Interactivos (/mapas/)
└── Recursos
    ├── Chat Don Datico 🦜 (siempre visible)
    ├── API Docs (/api-docs/)
    └── Infraestructura (/infraestructura/)

WORKSPACE (Unificado - requiere login)
├── Dashboard (/workspace/)
├── Cargar Datos (/workspace/upload/)
│   ├── Serie de Indicador
│   └── Microdata
├── Reportes (/workspace/reports/)
│   ├── Indicadores
│   └── Microdata
├── Mi Actividad (/workspace/history/)
└── Ayuda (/workspace/help/)

ADMIN (Staff only)
├── Dashboard (/admin/)
├── Wizard de Procesamiento (/admin/wizard/)
│   ├── Modo Básico (11 pasos)
│   └── Modo Experto (3 pasos) [NUEVO]
├── Gestión de Datos
│   ├── Indicadores
│   ├── Dominios
│   ├── Desagregaciones
│   └── Microdata
├── Monitoreo
│   ├── Procesos Activos (/admin/procesos/)
│   ├── Dashboard de Cargas (/admin/cargas/)
│   └── Logs del Sistema
├── Configuración
│   ├── Chat IA (Don Datico)
│   ├── Usuarios y Permisos
│   └── Sistema
└── Diagnóstico [NUEVO]
    ├── Diagnosticar Microdata (UI)
    └── Validador de Reglas
```

---

## 🎨 Propuesta de Diseño Visual

### **Sistema de Design Tokens**

```css
/* Colores Semánticos */
--color-primary: #0891b2;        /* Cyan-600 (actual) */
--color-secondary: #06b6d4;      /* Cyan-500 */
--color-success: #10b981;        /* Green-500 */
--color-warning: #f59e0b;        /* Amber-500 */
--color-danger: #ef4444;         /* Red-500 */
--color-info: #3b82f6;           /* Blue-500 */

/* Colores por Rol */
--color-ciudadano: #0891b2;      /* Cyan */
--color-recolector: #6b7280;     /* Gray */
--color-consultor: #10b981;      /* Green */
--color-admin: #8b5cf6;          /* Purple */

/* Espaciado Consistente */
--spacing-xs: 0.25rem;           /* 4px */
--spacing-sm: 0.5rem;            /* 8px */
--spacing-md: 1rem;              /* 16px */
--spacing-lg: 1.5rem;            /* 24px */
--spacing-xl: 2rem;              /* 32px */
--spacing-2xl: 3rem;             /* 48px */

/* Tipografía */
--font-family: 'Inter', system-ui, sans-serif;
--font-size-xs: 0.75rem;         /* 12px */
--font-size-sm: 0.875rem;        /* 14px */
--font-size-base: 1rem;          /* 16px */
--font-size-lg: 1.125rem;        /* 18px */
--font-size-xl: 1.25rem;         /* 20px */
--font-size-2xl: 1.5rem;         /* 24px */
--font-size-3xl: 1.875rem;       /* 30px */
--font-size-4xl: 2.25rem;        /* 36px */
```

---

### **Componentes Reutilizables**

#### **Componente: Card de Indicador**
```html
<div class="indicator-card">
  <div class="indicator-card__header">
    <span class="indicator-card__tag">{{ subtema }}</span>
    <h3 class="indicator-card__title">{{ nombre }}</h3>
  </div>
  
  <div class="indicator-card__body">
    <div class="indicator-card__stat">
      <span class="indicator-card__value">{{ valor_actual }}</span>
      <span class="indicator-card__unit">{{ unidad }}</span>
    </div>
    
    <div class="indicator-card__trend">
      {% if tendencia == 'up' %}
        <i class="fas fa-arrow-up text-success"></i>
      {% else %}
        <i class="fas fa-arrow-down text-danger"></i>
      {% endif %}
      <span>{{ cambio_porcentual }}%</span>
    </div>
  </div>
  
  <div class="indicator-card__footer">
    <a href="{{ url_detalle }}" class="btn btn-sm btn-primary">
      Ver detalles
    </a>
  </div>
</div>
```

#### **Componente: Alert Contextual**
```html
<div class="alert alert--{{ type }}" role="alert">
  <div class="alert__icon">
    {% if type == 'success' %}
      <i class="fas fa-check-circle"></i>
    {% elif type == 'warning' %}
      <i class="fas fa-exclamation-triangle"></i>
    {% elif type == 'error' %}
      <i class="fas fa-times-circle"></i>
    {% else %}
      <i class="fas fa-info-circle"></i>
    {% endif %}
  </div>
  
  <div class="alert__content">
    <h4 class="alert__title">{{ title }}</h4>
    <p class="alert__message">{{ message }}</p>
    {% if action_text %}
      <a href="{{ action_url }}" class="alert__action">
        {{ action_text }} →
      </a>
    {% endif %}
  </div>
  
  <button class="alert__close" aria-label="Cerrar">
    <i class="fas fa-times"></i>
  </button>
</div>
```

---

## 🚀 Roadmap de Implementación

### **FASE 1: Quick Wins (1-2 semanas)**

**1.1. Mejorar Home**
- [ ] Reducir sliders de 4 a 2
- [ ] Destacar 3 acciones principales
- [ ] Agregar buscador prominente
- [ ] Bot flotante Don Datico

**1.2. Chat Semántico Visible**
- [ ] Implementar bot flotante
- [ ] Versión móvil
- [ ] Historial persistente en localStorage

**1.3. Feedback Visual**
- [ ] Tooltips en términos técnicos
- [ ] Alerts consistentes (componente)
- [ ] Loading states en todas las acciones

**1.4. Diagnóstico en UI**
- [ ] Botón "Diagnosticar" en paso de regla
- [ ] Output HTML formateado
- [ ] Explicación de tipos de CSV

---

### **FASE 2: Unificación Workspace (2-3 semanas)**

**2.1. Merge Recolección + Reportes**
- [ ] Crear nuevo módulo `/workspace/`
- [ ] Login único con permisos
- [ ] Migrar funcionalidad de recolección
- [ ] Migrar funcionalidad de reportes
- [ ] Dashboard dinámico según rol

**2.2. Preview de Datos**
- [ ] Integrar Univer.js en carga de series
- [ ] Validación client-side antes de submit
- [ ] Preview de errores con sugerencias

**2.3. Notificaciones**
- [ ] Web Push API para procesos
- [ ] Email cuando proceso termina
- [ ] Dashboard de procesos en ejecución

---

### **FASE 3: Wizard Optimizado (3-4 semanas)**

**3.1. Modo Experto**
- [ ] Formulario compacto todo-en-uno
- [ ] Detección automática maximizada
- [ ] Skip de pasos opcionales

**3.2. Guardado de Progreso**
- [ ] Auto-save en sesión cada 30s
- [ ] Opción "Guardar como borrador"
- [ ] "Continuar más tarde"

**3.3. Rollback de Errores**
- [ ] Transacciones atómicas completas
- [ ] Log de operaciones para rollback
- [ ] Botón "Deshacer último proceso"

---

### **FASE 4: Gestión Masiva (2-3 semanas)**

**4.1. Importar Desagregaciones**
- [ ] CSV upload para crear múltiples
- [ ] Generador de rangos (ej: edades 0-99)
- [ ] Preview antes de crear

**4.2. Preview de Impacto**
- [ ] Mostrar indicadores afectados al editar
- [ ] Validar relaciones antes de eliminar
- [ ] Reasignar desagregaciones huérfanas

---

### **FASE 5: Móvil First (4-5 semanas)**

**5.1. Visor Comparativo Touch**
- [ ] Gestos táctiles para zoom/pan
- [ ] Gráficos optimizados para móvil
- [ ] Layout responsivo mejorado

**5.2. Chat Móvil**
- [ ] Panel full-screen en móvil
- [ ] Teclado optimizado
- [ ] Voz to text

**5.3. Dashboard Móvil**
- [ ] Cards adaptativas
- [ ] Navegación bottom-sheet
- [ ] Filtros en sidebar deslizante

---

## 📏 Métricas de Éxito Propuestas

### **Métricas Cuantitativas**

```javascript
// Google Analytics Events
gtag('event', 'wizard_completed', {
  'flow_type': 'A|B|C|D',
  'duration_seconds': tiempo_total,
  'steps_skipped': pasos_saltados,
  'errors_encountered': errores
});

gtag('event', 'chat_interaction', {
  'query_type': 'indicador|microdata|general',
  'response_helpful': true|false,
  'session_length': tiempo
});

gtag('event', 'upload_success', {
  'file_type': 'serie|microdata',
  'file_size_mb': tamaño,
  'validation_errors': errores
});
```

**KPIs:**
- **Tasa de completación wizard:** >80% (actual: desconocido)
- **Tiempo promedio wizard:** <10 min (actual: estimado 20+ min)
- **Errores por proceso:** <2 (actual: desconocido)
- **Satisfacción chat:** >4/5 (nueva métrica)
- **Usuarios activos workspace:** tracking unificado
- **Bounce rate home:** <40% (actual: desconocido)

### **Métricas Cualitativas**

**Encuesta Post-Proceso:**
```html
<div class="satisfaction-survey">
  <h3>¿Cómo fue tu experiencia?</h3>
  
  <div class="rating">
    <button data-rating="1">😞</button>
    <button data-rating="2">🙁</button>
    <button data-rating="3">😐</button>
    <button data-rating="4">🙂</button>
    <button data-rating="5">😄</button>
  </div>
  
  <textarea placeholder="¿Qué podríamos mejorar?"></textarea>
  
  <button class="btn btn-primary">Enviar feedback</button>
</div>
```

---

## 🎓 Recomendaciones de Accesibilidad

### **WCAG 2.1 AA Compliance**

**A1: Contraste de Color**
```css
/* Todos los textos deben cumplir ratio 4.5:1 */
/* Verificar con herramientas como WebAIM */

.text-muted {
  color: #6b7280; /* ✅ Pasa con fondo blanco */
}

.alert--warning {
  background: #fef3c7;
  color: #92400e; /* ✅ Contraste suficiente */
}
```

**A2: Navegación por Teclado**
```javascript
// Todos los interactivos deben ser accesibles por tab
document.querySelectorAll('.interactive-element').forEach(el => {
  if (!el.hasAttribute('tabindex')) {
    console.warn('Elemento sin tabindex:', el);
  }
});

// Focus visible
*:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
```

**A3: ARIA Labels**
```html
<!-- Iconos sin texto -->
<button aria-label="Cerrar ventana">
  <i class="fas fa-times"></i>
</button>

<!-- Gráficos -->
<div role="img" aria-label="Gráfico de barras mostrando población por comuna">
  <canvas id="chart"></canvas>
</div>

<!-- Estados dinámicos -->
<div aria-live="polite" aria-atomic="true">
  <span class="sr-only">Procesando, por favor espere...</span>
</div>
```

**A4: Formularios Semánticos**
```html
<form>
  <div class="form-group">
    <label for="nombre-indicador">
      Nombre del Indicador
      <span class="required" aria-label="requerido">*</span>
    </label>
    
    <input 
      type="text" 
      id="nombre-indicador"
      name="nombre"
      required
      aria-describedby="nombre-help"
      aria-invalid="false">
    
    <small id="nombre-help" class="form-text">
      Nombre descriptivo del indicador (máximo 255 caracteres)
    </small>
    
    <div class="invalid-feedback" role="alert">
      El nombre es requerido
    </div>
  </div>
</form>
```

---

## 🔐 Recomendaciones de Seguridad UX

**S1: Confirmaciones Destructivas**
```html
<!-- Doble confirmación para acciones críticas -->
<button onclick="deleteIndicator()" class="btn btn-danger">
  Eliminar Indicador
</button>

<script>
function deleteIndicator() {
  const name = document.getElementById('indicator-name').textContent;
  
  if (confirm(`¿Seguro que deseas eliminar "${name}"?`)) {
    if (confirm('Esta acción es PERMANENTE. ¿Continuar?')) {
      // Ejecutar eliminación
    }
  }
}
</script>
```

**S2: Preview de Cambios Sensibles**
```html
<!-- Mostrar qué se afectará antes de confirmar -->
<div class="impact-preview">
  <h4>⚠️ Esta acción afectará:</h4>
  <ul>
    <li>{{ affected_indicators_count }} indicadores</li>
    <li>{{ affected_datos_count }} registros de datos</li>
    <li>{{ affected_graphs_count }} gráficos</li>
  </ul>
  
  <button class="btn btn-danger">
    Entiendo, continuar
  </button>
</div>
```

**S3: Timeouts Informativos**
```javascript
// Avisar antes de que expire sesión
let timeoutWarning;
let sessionTimeout;

function resetSessionTimer() {
  clearTimeout(timeoutWarning);
  clearTimeout(sessionTimeout);
  
  // Avisar 5 min antes
  timeoutWarning = setTimeout(() => {
    showToast('Tu sesión expirará en 5 minutos', 'warning');
  }, 25 * 60 * 1000);
  
  // Expirar a los 30 min
  sessionTimeout = setTimeout(() => {
    window.location = '/workspace/login/?timeout=true';
  }, 30 * 60 * 1000);
}

// Reset en cada interacción
document.addEventListener('click', resetSessionTimer);
document.addEventListener('keypress', resetSessionTimer);
```

---

## 📱 Responsive Breakpoints

```css
/* Mobile First Approach */

/* Extra Small (móvil vertical) */
@media (max-width: 575px) {
  .wizard-steps { flex-direction: column; }
  .data-table { overflow-x: auto; }
  .sidebar { display: none; }
}

/* Small (móvil horizontal, tablet vertical) */
@media (min-width: 576px) and (max-width: 767px) {
  .card-grid { grid-template-columns: repeat(2, 1fr); }
}

/* Medium (tablet horizontal) */
@media (min-width: 768px) and (max-width: 991px) {
  .sidebar { display: block; width: 200px; }
  .card-grid { grid-template-columns: repeat(3, 1fr); }
}

/* Large (desktop) */
@media (min-width: 992px) and (max-width: 1199px) {
  .container { max-width: 960px; }
}

/* Extra Large (desktop grande) */
@media (min-width: 1200px) {
  .container { max-width: 1140px; }
  .card-grid { grid-template-columns: repeat(4, 1fr); }
}
```

---

## 🎯 Conclusiones y Próximos Pasos

### **Resumen Ejecutivo**

**Fortalezas de la Plataforma:**
✅ Wizard unificado moderno y funcional
✅ Chat semántico con IA avanzada
✅ Visualizaciones 3D únicas (Don Datico)
✅ Procesamiento robusto de microdata
✅ APIs bien documentadas

**Áreas de Mejora Críticas:**
🔴 **Duplicación Recolección/Reportes** → Unificar en Workspace
🔴 **Wizard sin guardado** → Implementar auto-save
🔴 **Experiencia móvil deficiente** → Rediseño responsive
🔴 **Falta notificaciones** → Web Push + Email

**Priorización Recomendada:**
1. **FASE 1 (Quick Wins)** → 2 semanas → ROI inmediato
2. **FASE 2 (Workspace)** → 3 semanas → Simplifica arquitectura
3. **FASE 3 (Wizard)** → 4 semanas → Mejora productividad admin
4. **FASE 4 (Gestión)** → 3 semanas → Reduce errores
5. **FASE 5 (Móvil)** → 5 semanas → Amplía audiencia

**Estimación Total:** 17 semanas (~4 meses)

### **Métricas de Impacto Esperado**

| Métrica | Actual | Meta | Impacto |
|---------|--------|------|---------|
| Tiempo wizard | ~20 min | <10 min | -50% |
| Tasa completación | ? | >80% | +Productividad |
| Bounce rate home | ? | <40% | +Engagement |
| Usuarios móviles | Bajo | +200% | +Alcance |
| Satisfacción NPS | ? | >60 | +Calidad |

---

**FIN DEL ANÁLISIS UX CRÍTICO**

**Documento elaborado por:** UX Designer  
**Para:** Equipo de Desarrollo Sistema de Indicadores  
**Próximo paso:** Priorizar fases con stakeholders y comenzar implementación
