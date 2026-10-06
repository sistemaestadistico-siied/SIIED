# Manual de Configuración del Chat IA - Don Datico

## 📖 Índice

1. [Introducción](#1-introducción)
2. [Acceso al Sistema](#2-acceso-al-sistema)
3. [Configuración de Parámetros](#3-configuración-de-parámetros)
4. [Edición de Contextos](#4-edición-de-contextos)
5. [Casos de Uso](#5-casos-de-uso)
6. [Solución de Problemas](#6-solución-de-problemas)
7. [FAQ](#7-preguntas-frecuentes)

---

## 1. Introducción

### 1.1 ¿Qué es este sistema?

Sistema de administración visual para configurar el agente de IA **Don Datico** desde el panel de Django, sin editar código ni reiniciar el servidor.

### 1.2 ¿Qué puedes configurar?

- **Parámetros técnicos:** Límites, timeouts, caché
- **Contextos:** Personalidad, instrucciones, comportamiento

### 1.3 Requisitos

- Usuario con permisos de **administrador** (is_staff=True)
- Acceso al panel de Django admin

---

## 2. Acceso al Sistema

### 2.1 Iniciar Sesión

1. Navega a: `http://localhost:8000/admin/`
2. Ingresa credenciales de administrador
3. Click en "Iniciar sesión"

### 2.2 Localizar Configuración

Busca la sección con fondo morado:

```
🤖 Configuración del Agente IA - Don Datico
```

### 2.3 Opciones Disponibles

**A) Configurar Parámetros** → `/admin/chat-config/`
- Límites técnicos, timeouts, caché

**B) Editar Contextos** → `/admin/chat-contexts/`
- Personalidad y prompts del agente

---

## 3. Configuración de Parámetros

### 3.1 Historial de Conversación

#### MAX_HISTORY_MESSAGES
- **Función:** Mensajes que el agente recuerda
- **Rango:** 1-50
- **Actual:** 8
- **Cuándo aumentar:** Conversaciones largas
- **Cuándo disminuir:** Ahorrar memoria

#### MAX_MESSAGE_LENGTH
- **Función:** Caracteres máximos por mensaje
- **Rango:** 100-5000
- **Actual:** 1000
- **Recomendado:** 1000-2000

### 3.2 Herramientas (Tools)

#### MAX_TOOL_ROUNDS
- **Función:** Rondas de uso de herramientas
- **Rango:** 1-10
- **Actual:** 5
- **Aumentar si:** Consultas complejas
- **Disminuir si:** Respuestas más rápidas

#### TOOL_TIMEOUT_SECONDS
- **Función:** Timeout de herramientas
- **Rango:** 30-300
- **Actual:** 120
- **Recomendado:** 120 segundos

#### MAX_TOOL_CHAIN_LENGTH
- **Función:** Herramientas encadenadas
- **Rango:** 1-15
- **Actual:** 6
- **Recomendado:** 4-8

### 3.3 Caché y Rendimiento

#### CONTEXT_CACHE_TIMEOUT
- **Función:** Tiempo de vida del caché
- **Rango:** 300-86400 segundos
- **Actual:** 21600 (6 horas)
- **Conversión:** 3600=1h, 21600=6h, 86400=24h

#### CONTEXT_CACHE_KEY
- **Función:** ID del caché
- **Actual:** `chat_system_context_v6`
- **Cambiar para:** Forzar regeneración

### 3.4 Gestión de Requests

#### REQUEST_MAX_AGE_MINUTES
- **Rango:** 1-60
- **Actual:** 5

#### CLEANUP_MAX_TIME
- **Rango:** 0.5-10.0
- **Actual:** 3.0

#### MAX_ACTIVE_SESSIONS
- **Rango:** 10-100
- **Actual:** 30

### 3.5 Búsqueda

#### MAX_RELEVANT_DATA_LENGTH
- **Rango:** 100-2000
- **Actual:** 500

#### SEARCH_TOP_K
- **Rango:** 1-50 o vacío
- **Actual:** vacío (sin límite)

#### MIN_SIMILARITY_THRESHOLD
- **Rango:** 0.0-1.0
- **Actual:** 0.25
- **Escala:**
  - 0.0-0.2: Muy permisivo
  - 0.2-0.3: Balance (recomendado)
  - 0.3-0.5: Restrictivo
  - 0.5-1.0: Muy restrictivo

### 3.6 Memoria

#### ENABLE_CONTEXT_MEMORY
- **Tipo:** Boolean
- **Actual:** True
- **Recomendado:** Mantener activado

### 3.7 Guardar Cambios

1. Revisa valores
2. Click "💾 Guardar Configuración"
3. Verás: "✅ Configuración guardada"
4. Cambios aplicados inmediatamente

---

## 4. Edición de Contextos

### 4.1 Acceso

URL: `/admin/chat-contexts/`

### 4.2 Contextos Disponibles

#### 1. Base (don_datico_base)
- **Función:** Personalidad fundamental
- **Variables:** {dominios}, {temas}, {subtemas}, {indicadores}
- **Editar para:** Cambiar tono, misión, directrices

#### 2. Ronda 1 (tools_round_1)
- **Función:** Primera ronda con herramientas
- **Variables:** Ninguna
- **Editar para:** Metodología de trabajo

#### 3. Rondas N (tools_round_n)
- **Función:** Rondas subsiguientes
- **Variables:** {round}, {max_rounds}, {tools_used}, {has_data}
- **Editar para:** Estrategia de refinamiento

#### 4. Conversacional (conversational)
- **Función:** Sin herramientas
- **Variables:** Ninguna
- **Editar para:** Tono casual

#### 5. Mejorado (enhanced_tools)
- **Función:** Instrucciones detalladas
- **Variables:** Ninguna
- **Editar para:** Ejemplos de uso

#### 6. Respaldo (fallback)
- **Función:** Emergencia
- **Variables:** Ninguna
- **Editar:** Solo si necesario

### 4.3 Proceso de Edición

1. Click en contexto del menú lateral
2. Edita contenido en el editor
3. Verifica llaves balanceadas: `{variable}`
4. Click "💾 Guardar Contexto"
5. Verás: "✅ Contexto guardado"

### 4.4 Validaciones

- Contexto no vacío
- Llaves balanceadas
- Sin comillas triples dentro

---

## 5. Casos de Uso

### 5.1 Agente muy verboso

**Problema:** Respuestas demasiado largas

**Solución:**
1. `/admin/chat-contexts/` → Base
2. Modificar DIRECTRICES:
   ```
   - Respuestas concisas (máximo 3 párrafos)
   - Evita explicaciones innecesarias
   ```
3. Guardar

### 5.2 Sin rondas suficientes

**Problema:** "Límite de rondas alcanzado"

**Solución:**
1. `/admin/chat-config/`
2. MAX_TOOL_ROUNDS: 5 → 7
3. Guardar

### 5.3 Resultados irrelevantes

**Problema:** Búsquedas traen datos no relacionados

**Solución:**
1. `/admin/chat-config/`
2. MIN_SIMILARITY_THRESHOLD: 0.25 → 0.35
3. Guardar

### 5.4 Olvida contexto

**Problema:** No recuerda mensajes previos

**Solución:**
1. `/admin/chat-config/`
2. MAX_HISTORY_MESSAGES: 8 → 12
3. Guardar

### 5.5 Cambiar saludo

**Problema:** Modificar estilo de saludo

**Solución:**
1. `/admin/chat-contexts/` → Ronda 1
2. Editar línea de saludo
3. Guardar

### 5.6 Optimizar recursos

**Problema:** Servidor sobrecargado

**Solución:**
1. `/admin/chat-config/`
2. Ajustar:
   - MAX_ACTIVE_SESSIONS: 30 → 15
   - MAX_TOOL_ROUNDS: 5 → 3
   - TOOL_TIMEOUT_SECONDS: 120 → 60
3. Guardar

---

## 6. Solución de Problemas

### 6.1 No puedo acceder

**Síntomas:** Error 403

**Solución:**
- Verificar is_staff=True
- Reiniciar sesión
- Contactar administrador

### 6.2 Cambios no se aplican

**Solución:**
```bash
# Verificar archivo
cat indicadores/chat_config.py | grep MAX_TOOL_ROUNDS

# Reiniciar servidor
python3 manage.py runserver

# Limpiar caché
find . -type d -name __pycache__ -exec rm -r {} +
```

### 6.3 Permission denied

**Solución:**
```bash
chmod 664 indicadores/chat_config.py
```

### 6.4 Llaves no balanceadas

**Solución:**
- Contar `{` y `}`
- Deben ser iguales
- Corregir y guardar

### 6.5 Contexto se ve raro

**Solución:**
```bash
git checkout indicadores/chat_config.py
```

### 6.6 No encuentra nada

**Solución:**
- Bajar MIN_SIMILARITY_THRESHOLD
- De 0.5 → 0.3 → 0.25

---

## 7. Preguntas Frecuentes

### ¿Requiere reiniciar?
No. Cambios inmediatos.

### ¿Se guardan versiones?
No automático. Usar Git:
```bash
git log indicadores/chat_config.py
git checkout HEAD~1 indicadores/chat_config.py
```

### ¿Configuración por usuario?
No. Es singleton (una para todos).

### ¿Edición concurrente?
No hay bloqueo. Último sobrescribe.

### ¿Exportar configuración?
```bash
cp indicadores/chat_config.py backup_$(date +%Y%m%d).py
```

### ¿Valores por defecto?
```bash
git checkout origin/main indicadores/chat_config.py
```

### ¿Agregar parámetros?
Requiere modificar código en:
- forms_chat_config.py
- views_chat_config.py
- chat_config.html

### ¿Soporta Markdown?
Sí, en contextos.

---

## Fin del Manual

Para soporte adicional, contacta al equipo de desarrollo.
