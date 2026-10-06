# 📊 ANÁLISIS COMPLETO: Estructura y Flujo del Chat

## 🏗️ ARQUITECTURA DEL SISTEMA DE CHAT

### **Componentes Principales**

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Usuario)                        │
│                    chat.html / chat.js                       │
└──────────────────────┬──────────────────────────────────────┘
                       │ WebSocket/SSE
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   VISTA PRINCIPAL                            │
│                  chat_stream (views_chat.py)                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   SERVICIO PRINCIPAL                         │
│            ChatService (views_chat.py:1680-1820)             │
│                                                              │
│  ┌────────────────────────────────────────────────┐         │
│  │  Cliente Principal: Cerebras API               │         │
│  │  - Base URL: https://api.cerebras.ai/v1       │         │
│  │  - API Key: PARAMETRIZABLE ✅                  │         │
│  │  - Modelo: PARAMETRIZABLE ✅                   │         │
│  │  - Max Tokens: PARAMETRIZABLE ✅               │         │
│  │  - Temperature: PARAMETRIZABLE ✅              │         │
│  │  - Top P: PARAMETRIZABLE ✅                    │         │
│  └────────────────────────────────────────────────┘         │
│                                                              │
│  ┌────────────────────────────────────────────────┐         │
│  │  Cliente Fallback: Ollama Local                │         │
│  │  - Base URL: http://localhost:11434/v1 ⚠️      │         │
│  │  - API Key: "ollama" (fijo)                    │         │
│  │  - Timeout: 120.0 segundos ⚠️                  │         │
│  │  - Modelo: PARAMETRIZABLE ✅                   │         │
│  │  - Max Tokens: PARAMETRIZABLE ✅               │         │
│  │  - Temperature: PARAMETRIZABLE ✅              │         │
│  │  - Top P: PARAMETRIZABLE ✅                    │         │
│  └────────────────────────────────────────────────┘         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│            SERVICIO DE HERRAMIENTAS (TOOLS)                  │
│      CerebrasToolsService (views_chat.py:85-1602)            │
│                                                              │
│  - Base URL: https://api.cerebras.ai/v1 ⚠️                  │
│  - API Key: Heredada de ChatService                         │
│  - Fallback Base URL: http://127.0.0.1:8000 ⚠️             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 VARIABLES HARDCODEADAS ENCONTRADAS

### **❌ CRÍTICAS - Deben parametrizarse**

#### 1. **URLs de API**
```python
# Línea 98: CerebrasToolsService.__init__
base_url="https://api.cerebras.ai/v1"  # ⚠️ Hardcoded

# Línea 1705: ChatService.__init__
base_url="https://api.cerebras.ai/v1"  # ⚠️ Hardcoded

# Línea 1711: ChatService.__init__ (Ollama)
base_url="http://localhost:11434/v1"  # ⚠️ Hardcoded
```

**Impacto:** Si cambia la URL de Cerebras o Ollama está en otro puerto/host, hay que modificar código.

**Solución:** Agregar a `chat_config.py`:
- `CEREBRAS_BASE_URL`
- `OLLAMA_BASE_URL`

---

#### 2. **Timeouts**
```python
# Línea 1652: CerebrasToolsService._call_tool_endpoint
timeout=30  # ⚠️ Hardcoded - Para llamadas HTTP a herramientas

# Línea 1712: ChatService.__init__
timeout=120.0  # ⚠️ Hardcoded - Timeout del cliente Ollama

# Línea 3269: ChatService.chat_stream
timeout = 180  # ⚠️ Hardcoded - Timeout de streaming para Ollama en CPU
```

**Impacto:** En servidores lentos, puede cortar respuestas. En servidores rápidos, espera innecesariamente.

**Solución:** Agregar a `chat_config.py`:
- `HTTP_TOOLS_TIMEOUT_SECONDS` (30 seg)
- `OLLAMA_CLIENT_TIMEOUT_SECONDS` (120 seg)
- `OLLAMA_STREAM_TIMEOUT_SECONDS` (180 seg)

---

#### 3. **Límites de Contexto y Truncado**
```python
# Línea 1789: ChatService._call_llm_with_fallback
if approx_tokens > 100000:  # ⚠️ Hardcoded - Límite de tokens para Ollama
    messages = messages[-10:]  # ⚠️ Hardcoded - Número de mensajes a mantener
```

**Impacto:** Puede truncar demasiado o poco según el modelo y hardware.

**Solución:** Agregar a `chat_config.py`:
- `OLLAMA_MAX_CONTEXT_TOKENS` (100000)
- `OLLAMA_TRUNCATE_MESSAGES_COUNT` (10)

---

#### 4. **Base URL de Fallback para Tools**
```python
# Línea 92: CerebrasToolsService.__init__
self.base_url = base_url or "http://127.0.0.1:8000"  # ⚠️ Hardcoded
```

**Impacto:** Si el servidor está en otro puerto, las herramientas fallan.

**Solución:** Usar `request.build_absolute_uri()` siempre o parametrizar.

---

### **⚠️ MENORES - Recomendado parametrizar**

#### 5. **Número de Chunks a Procesar**
```python
# Múltiples lugares en streaming
chunk_count = 0
# Sin límite explícito configurado
```

**Solución:** Agregar `MAX_STREAM_CHUNKS` si se desea limitar.

---

#### 6. **Códigos de Error para Fallback**
```python
# Línea 1752-1760: ChatService._call_llm_with_fallback
should_fallback = (
    "429" in error_str or 
    "401" in error_str or 
    "403" in error_str or
    "rate" in error_str.lower() or 
    "quota" in error_str.lower() or
    "wrong api key" in error_str.lower() or
    "unauthorized" in error_str.lower()
)
```

**Impacto:** Si se agregan nuevos códigos de error, hay que modificar código.

**Solución:** Crear lista configurable `CEREBRAS_FALLBACK_ERROR_CODES`.

---

## 🔄 FLUJOS DE DATOS DETALLADOS

### **Flujo 1: Conversación Normal (Sin Tools)**

```
1. Usuario envía mensaje
   ↓
2. chat_stream recibe mensaje
   ↓
3. ChatService.chat_stream() 
   - Limpia historial (get_config('MAX_HISTORY_MESSAGES'))
   - Genera contexto del sistema
   ↓
4. _call_llm_with_fallback()
   - Intenta: Cerebras API (https://api.cerebras.ai/v1) ✅
   - Si falla (429, 401, 403): Ollama (http://localhost:11434/v1) ⚠️
   ↓
5. Stream de respuesta
   - Timeout: 180 segundos ⚠️
   - Chunks ilimitados
   ↓
6. Retorna al usuario
```

**Parámetros Usados:**
- ✅ `MAX_HISTORY_MESSAGES`
- ✅ `CEREBRAS_MODEL`
- ✅ `CEREBRAS_MAX_TOKENS`
- ✅ `CEREBRAS_TEMPERATURE`
- ✅ `CEREBRAS_TOP_P`
- ✅ `OLLAMA_MODEL`
- ✅ `OLLAMA_MAX_TOKENS`
- ✅ `OLLAMA_TEMPERATURE`
- ✅ `OLLAMA_TOP_P`
- ⚠️ Hardcoded: URLs, timeouts

---

### **Flujo 2: Conversación con Tools**

```
1. Usuario envía mensaje que requiere datos
   ↓
2. chat_stream detecta que necesita tools
   ↓
3. _generate_with_tools_stream()
   - Max rondas: get_config('MAX_TOOL_ROUNDS', 3) ✅
   - Timeout total: get_config('TOOL_TIMEOUT_SECONDS', 120) ✅
   ↓
4. CerebrasToolsService.stream_with_tools()
   - Endpoint: https://api.cerebras.ai/v1 ⚠️
   - Define herramientas (buscar_indicadores, obtener_datos, etc.)
   ↓
5. Por cada ronda de tools:
   a) LLM decide qué herramienta usar
   b) Ejecuta herramienta HTTP (timeout 30 seg) ⚠️
   c) Retorna resultado al LLM
   d) LLM genera respuesta o solicita otra tool
   ↓
6. Si Cerebras falla:
   - Cambia a Ollama (http://localhost:11434/v1) ⚠️
   - Ollama SÍ soporta tools con cogito
   - Contexto truncado si > 100K tokens ⚠️
   - Mantiene últimos 10 mensajes si trunca ⚠️
   ↓
7. Stream de respuesta final
   ↓
8. Retorna al usuario
```

**Parámetros Usados:**
- ✅ `MAX_TOOL_ROUNDS`
- ✅ `TOOL_TIMEOUT_SECONDS`
- ✅ `MAX_TOOL_CHAIN_LENGTH`
- ✅ Todos los parámetros de modelo
- ⚠️ Hardcoded: URLs, timeouts HTTP, límites de truncado

---

### **Flujo 3: Fallback Completo (Cerebras Falla)**

```
1. ChatService intenta Cerebras API
   ↓
2. Error detectado:
   - 429 (Rate Limit)
   - 401 (API Key inválida)
   - 403 (Sin permisos)
   - "rate", "quota", "unauthorized" en mensaje
   ↓
3. Activa using_fallback = True
   ↓
4. Cambia a Ollama:
   - URL: http://localhost:11434/v1 ⚠️
   - Timeout: 120 segundos ⚠️
   - Modelo: cogito:3b (o configurado) ✅
   ↓
5. Verifica tamaño del contexto:
   - Si > 100K tokens: trunca a últimos 10 mensajes ⚠️
   ↓
6. Ejecuta con Ollama
   - Soporta tools (mantiene funcionalidad)
   - Stream timeout: 180 segundos ⚠️
   ↓
7. Si Ollama también falla:
   - Error al usuario
   - Log del error
```

**Condiciones de Fallback:**
- ⚠️ Códigos de error hardcodeados
- ✅ Modelo configurable
- ⚠️ URL y timeouts hardcodeados
- ⚠️ Límites de truncado hardcodeados

---

## 📋 RECOMENDACIONES DE PARAMETRIZACIÓN

### **🔴 PRIORIDAD ALTA (Crítico)**

1. **URLs de API**
   ```python
   'CEREBRAS_BASE_URL': 'https://api.cerebras.ai/v1'
   'OLLAMA_BASE_URL': 'http://localhost:11434/v1'
   ```

2. **Timeouts**
   ```python
   'HTTP_TOOLS_TIMEOUT_SECONDS': 30
   'OLLAMA_CLIENT_TIMEOUT_SECONDS': 120
   'OLLAMA_STREAM_TIMEOUT_SECONDS': 180
   ```

3. **Límites de Contexto (Ollama)**
   ```python
   'OLLAMA_MAX_CONTEXT_TOKENS': 100000
   'OLLAMA_TRUNCATE_MESSAGES_COUNT': 10
   ```

---

### **🟡 PRIORIDAD MEDIA (Recomendado)**

4. **Fallback URL Base (Tools)**
   ```python
   'TOOLS_FALLBACK_BASE_URL': 'http://127.0.0.1:8000'
   ```

5. **Códigos de Error para Fallback**
   ```python
   'CEREBRAS_FALLBACK_ERROR_CODES': ['429', '401', '403', '500', '502', '503']
   'CEREBRAS_FALLBACK_ERROR_KEYWORDS': ['rate', 'quota', 'unauthorized', 'wrong api key']
   ```

---

### **🟢 PRIORIDAD BAJA (Opcional)**

6. **Límites de Streaming**
   ```python
   'MAX_STREAM_CHUNKS': None  # None = ilimitado
   'STREAM_CHUNK_DELAY_MS': 0  # Delay entre chunks (para throttling)
   ```

7. **Métricas y Logging**
   ```python
   'ENABLE_PERFORMANCE_LOGGING': True
   'LOG_TOKEN_USAGE': True
   ```

---

## 🎯 CAMBIOS PROPUESTOS EN CÓDIGO

### **chat_config.py**
```python
CHAT_CONFIG = {
    # ... configuración existente ...
    
    # URLs de API
    'CEREBRAS_BASE_URL': 'https://api.cerebras.ai/v1',
    'OLLAMA_BASE_URL': 'http://localhost:11434/v1',
    'TOOLS_FALLBACK_BASE_URL': 'http://127.0.0.1:8000',
    
    # Timeouts
    'HTTP_TOOLS_TIMEOUT_SECONDS': 30,
    'OLLAMA_CLIENT_TIMEOUT_SECONDS': 120,
    'OLLAMA_STREAM_TIMEOUT_SECONDS': 180,
    
    # Límites de Contexto (Ollama)
    'OLLAMA_MAX_CONTEXT_TOKENS': 100000,
    'OLLAMA_TRUNCATE_MESSAGES_COUNT': 10,
    
    # Fallback
    'CEREBRAS_FALLBACK_ERROR_CODES': ['429', '401', '403', '500', '502', '503'],
    'CEREBRAS_FALLBACK_ERROR_KEYWORDS': ['rate', 'quota', 'unauthorized', 'wrong api key'],
}
```

### **views_chat.py (Cambios)**

#### CerebrasToolsService.__init__
```python
self.client = OpenAI(
    api_key=api_key,
    base_url=get_config('CEREBRAS_BASE_URL', 'https://api.cerebras.ai/v1')
)

self.base_url = base_url or get_config('TOOLS_FALLBACK_BASE_URL', 'http://127.0.0.1:8000')
```

#### ChatService.__init__
```python
self.client = OpenAI(
    api_key=self.api_key,
    base_url=get_config('CEREBRAS_BASE_URL', 'https://api.cerebras.ai/v1')
)

self.fallback_client = OpenAI(
    api_key="ollama",
    base_url=get_config('OLLAMA_BASE_URL', 'http://localhost:11434/v1'),
    timeout=get_config('OLLAMA_CLIENT_TIMEOUT_SECONDS', 120.0)
)
```

#### _call_tool_endpoint
```python
response = requests.get(
    url, 
    params=params, 
    timeout=get_config('HTTP_TOOLS_TIMEOUT_SECONDS', 30)
)
```

#### _call_llm_with_fallback
```python
max_context = get_config('OLLAMA_MAX_CONTEXT_TOKENS', 100000)
truncate_count = get_config('OLLAMA_TRUNCATE_MESSAGES_COUNT', 10)

if approx_tokens > max_context:
    logger.warning(f"⚠️ Contexto muy grande ({approx_tokens} tokens), truncando mensajes...")
    messages = messages[-truncate_count:]
```

#### chat_stream
```python
timeout = get_config('OLLAMA_STREAM_TIMEOUT_SECONDS', 180)
```

---

## 📊 RESUMEN EJECUTIVO

### **Estado Actual**

| Componente | Parametrizado | Hardcoded |
|------------|--------------|-----------|
| API Keys | ✅ Sí | - |
| Modelos IA | ✅ Sí | - |
| Max Tokens | ✅ Sí | - |
| Temperature/Top-P | ✅ Sí | - |
| URLs de API | ❌ No | ⚠️ Sí |
| Timeouts | ❌ No | ⚠️ Sí |
| Límites de Contexto | ❌ No | ⚠️ Sí |
| Fallback Config | ⚠️ Parcial | ⚠️ Parcial |

### **Riesgo de Configuración Actual**

- 🔴 **Alto:** URLs hardcodeadas impiden cambios sin código
- 🟡 **Medio:** Timeouts fijos pueden causar fallos en hardware lento/rápido
- 🟢 **Bajo:** Límites de truncado generalmente funcionan

### **Beneficios de Parametrización Completa**

1. ✅ **Portabilidad:** Funciona en cualquier entorno sin cambios de código
2. ✅ **Mantenibilidad:** Cambios desde admin, sin despliegues
3. ✅ **Flexibilidad:** Ajustar según hardware y carga
4. ✅ **Debugging:** Experimentar con configuraciones sin riesgo
5. ✅ **Escalabilidad:** Múltiples instancias con configuraciones distintas

---

## 🚀 PLAN DE IMPLEMENTACIÓN

### **Fase 1: Crítico (Hoy)**
- [ ] Parametrizar URLs (Cerebras, Ollama, Tools)
- [ ] Parametrizar todos los timeouts
- [ ] Actualizar formularios del admin

### **Fase 2: Recomendado (Esta semana)**
- [ ] Parametrizar límites de contexto Ollama
- [ ] Parametrizar códigos de error fallback
- [ ] Actualizar templates admin

### **Fase 3: Opcional (Futuro)**
- [ ] Agregar métricas y logging configurable
- [ ] Dashboard de estado de fallback
- [ ] Alertas automáticas de fallas

---

**Generado:** 2025-10-19  
**Versión:** 1.0  
**Autor:** Análisis Automatizado de Código
