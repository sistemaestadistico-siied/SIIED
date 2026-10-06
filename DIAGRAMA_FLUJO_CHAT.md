# 🔄 DIAGRAMA DE FLUJO DEL SISTEMA DE CHAT

## 📊 Diagrama Principal: Arquitectura Completa

```mermaid
graph TB
    %% Estilos
    classDef frontend fill:#e3f2fd,stroke:#2196f3,stroke-width:3px
    classDef view fill:#fff3e0,stroke:#ff9800,stroke-width:3px
    classDef service fill:#f3e5f5,stroke:#9c27b0,stroke-width:3px
    classDef config fill:#e8f5e9,stroke:#4caf50,stroke-width:3px
    classDef api fill:#fce4ec,stroke:#e91e63,stroke-width:3px
    classDef db fill:#e0f2f1,stroke:#009688,stroke-width:3px
    
    %% Frontend
    USER[👤 Usuario]:::frontend
    CHAT_HTML[chat.html<br/>Frontend Template]:::frontend
    CHAT_JS[chat.js<br/>WebSocket Handler]:::frontend
    
    %% Vista Principal
    CHAT_STREAM[chat_stream<br/>views_chat.py:4400<br/>Vista Principal SSE]:::view
    
    %% Servicios
    CHAT_SERVICE[ChatService<br/>views_chat.py:1680<br/>Servicio Principal]:::service
    TOOLS_SERVICE[CerebrasToolsService<br/>views_chat.py:85<br/>Servicio de Herramientas]:::service
    
    %% Configuración
    CHAT_CONFIG[chat_config.py<br/>CHAT_CONFIG<br/>Configuración Central]:::config
    FORMS[forms_chat_config.py<br/>ChatConfigForm<br/>Formulario Admin]:::config
    
    %% APIs Externas
    CEREBRAS[Cerebras API<br/>api.cerebras.ai/v1<br/>Modelo Principal]:::api
    OLLAMA[Ollama API<br/>localhost:11434/v1<br/>Modelo Fallback]:::api
    
    %% Base de Datos
    DJANGO_DB[(Django DB<br/>Historial/Sesiones)]:::db
    CACHE[(Django Cache<br/>Contextos)]:::db
    
    %% Flujo Principal
    USER -->|1. Envía mensaje| CHAT_JS
    CHAT_JS -->|2. SSE Request| CHAT_STREAM
    CHAT_STREAM -->|3. Inicializa| CHAT_SERVICE
    
    %% Configuración
    CHAT_SERVICE -->|Lee config| CHAT_CONFIG
    CHAT_CONFIG <-->|Edita| FORMS
    
    %% Flujo Normal (Sin Tools)
    CHAT_SERVICE -->|4a. Mensaje simple| CEREBRAS
    CEREBRAS -->|5a. Stream respuesta| CHAT_SERVICE
    
    %% Flujo con Tools
    CHAT_SERVICE -->|4b. Necesita datos| TOOLS_SERVICE
    TOOLS_SERVICE -->|5b. Call LLM| CEREBRAS
    CEREBRAS -->|6b. Tool call| TOOLS_SERVICE
    TOOLS_SERVICE -->|7b. Ejecuta tool| CHAT_STREAM
    CHAT_STREAM -->|8b. HTTP API| DJANGO_DB
    DJANGO_DB -->|9b. Datos| CHAT_STREAM
    CHAT_STREAM -->|10b. Tool result| TOOLS_SERVICE
    TOOLS_SERVICE -->|11b. Genera respuesta| CEREBRAS
    CEREBRAS -->|12b. Stream final| TOOLS_SERVICE
    
    %% Fallback
    CHAT_SERVICE -.->|Error/Rate Limit| OLLAMA
    OLLAMA -.->|Respuesta fallback| CHAT_SERVICE
    
    %% Cache
    CHAT_SERVICE <-->|Contexto| CACHE
    
    %% Retorno
    CHAT_SERVICE -->|Stream chunks| CHAT_STREAM
    CHAT_STREAM -->|SSE Events| CHAT_JS
    CHAT_JS -->|Renderiza| USER
```

---

## 🔀 Diagrama: Flujo de Conversación Normal (Sin Herramientas)

```mermaid
sequenceDiagram
    participant U as 👤 Usuario
    participant JS as chat.js
    participant V as chat_stream()<br/>views_chat.py
    participant CS as ChatService<br/>__init__
    participant CFG as chat_config.py<br/>CHAT_CONFIG
    participant C as Cerebras API<br/>api.cerebras.ai
    participant DB as Django DB
    
    U->>JS: Escribe mensaje
    JS->>V: POST /chat/stream/<br/>{message, history}
    
    rect rgb(240, 240, 255)
        Note over V,CS: Inicialización
        V->>CS: new ChatService(request)
        CS->>CFG: get_config('CEREBRAS_API_KEY')
        CFG-->>CS: API Key
        CS->>CFG: get_config('CEREBRAS_BASE_URL')
        CFG-->>CS: https://api.cerebras.ai/v1
        CS->>CFG: get_config('CEREBRAS_MODEL')
        CFG-->>CS: gpt-oss-120b
    end
    
    rect rgb(255, 245, 240)
        Note over V,DB: Preparación
        V->>V: clean_history()<br/>MAX_HISTORY_MESSAGES
        V->>DB: Guarda sesión
        V->>V: get_system_context()
    end
    
    rect rgb(240, 255, 240)
        Note over CS,C: Generación LLM
        CS->>CS: chat_stream(message, history)
        CS->>CS: _call_llm_with_fallback()
        CS->>C: client.chat.completions.create()<br/>stream=True
        
        loop Streaming
            C-->>CS: chunk
            CS->>CS: Procesa chunk
            CS-->>V: yield chunk
            V-->>JS: SSE: data: {content}
            JS-->>U: Renderiza chunk
        end
    end
    
    rect rgb(255, 240, 255)
        Note over V: Finalización
        V->>DB: Actualiza historial
        V-->>JS: SSE: [DONE]
        JS-->>U: Muestra respuesta completa
    end
```

---

## 🛠️ Diagrama: Flujo con Herramientas (Tools)

```mermaid
sequenceDiagram
    participant U as 👤 Usuario
    participant V as chat_stream()<br/>views_chat.py
    participant CS as ChatService
    participant TS as CerebrasToolsService
    participant CFG as chat_config.py
    participant C as Cerebras API
    participant API as Django API<br/>Endpoints
    participant DB as Database
    
    U->>V: "Muéstrame datos de población 2024"
    
    rect rgb(255, 250, 240)
        Note over V,CS: Detección de Necesidad de Tools
        V->>CS: chat_stream(message)
        CS->>CS: Detecta keywords:<br/>"datos", "población"
        CS->>CS: use_tools = True
    end
    
    rect rgb(240, 255, 250)
        Note over CS,TS: Inicialización Tools
        CS->>TS: new CerebrasToolsService(api_key)
        TS->>CFG: get_config('CEREBRAS_BASE_URL')
        CFG-->>TS: https://api.cerebras.ai/v1
        TS->>CFG: get_config('TOOLS_FALLBACK_BASE_URL')
        CFG-->>TS: http://127.0.0.1:8000
        TS->>TS: get_tools_definition()
    end
    
    rect rgb(255, 240, 240)
        Note over CS,C: Ronda 1: Búsqueda de Indicadores
        CS->>TS: stream_with_tools()
        TS->>CFG: get_config('MAX_TOOL_ROUNDS')
        CFG-->>TS: 5 rondas
        TS->>C: chat.completions.create()<br/>tools=[buscar_indicadores, ...]
        C-->>TS: tool_call: buscar_indicadores_inteligente<br/>{consulta: "población", año: 2024}
        
        TS->>TS: _call_tool_endpoint()<br/>"buscar_indicadores_inteligente"
        TS->>CFG: get_config('HTTP_TOOLS_TIMEOUT_SECONDS')
        CFG-->>TS: 30 segundos
        TS->>API: GET /api/buscar_indicadores_inteligente/<br/>?consulta=población&año=2024
        API->>DB: Query indicadores
        DB-->>API: Resultados (10 indicadores)
        API-->>TS: {indicadores: [...], count: 10}
        TS-->>V: yield {type: 'tool_result'}
        V-->>U: 🔍 Buscando indicadores...
    end
    
    rect rgb(240, 255, 240)
        Note over TS,C: Ronda 2: Obtención de Datos
        TS->>C: Envía tool_result + new prompt
        C-->>TS: tool_call: obtener_datos_indicador_completo<br/>{id: 123, año_inicio: 2024}
        
        TS->>API: GET /api/obtener_datos_indicador_completo/<br/>?id=123&año_inicio=2024
        API->>DB: Query datos con filtros
        DB-->>API: Datos (500 registros)
        API-->>TS: {datos: [...], metadata: {...}}
        TS-->>V: yield {type: 'tool_result'}
        V-->>U: 📊 Obteniendo datos...
    end
    
    rect rgb(240, 240, 255)
        Note over TS,C: Ronda 3: Generación Respuesta Final
        TS->>C: Envía todos los tool_results
        C-->>TS: response: "Según los datos..."<br/>finish_reason: 'stop'
        
        loop Streaming Final
            TS-->>V: yield {content: chunk}
            V-->>U: Renderiza respuesta
        end
    end
    
    V->>DB: Guarda historial con tools
    V-->>U: ✅ Respuesta completa
```

---

## ⚡ Diagrama: Flujo de Fallback (Cerebras → Ollama)

```mermaid
sequenceDiagram
    participant U as 👤 Usuario
    participant CS as ChatService
    participant CFG as chat_config.py
    participant C as Cerebras API
    participant O as Ollama API<br/>localhost:11434
    
    U->>CS: Mensaje del usuario
    
    rect rgb(255, 240, 240)
        Note over CS,C: Intento con Cerebras
        CS->>CS: _call_llm_with_fallback()
        CS->>CFG: get_config('CEREBRAS_BASE_URL')
        CFG-->>CS: https://api.cerebras.ai/v1
        CS->>C: client.chat.completions.create()
        C-->>CS: ❌ Error 429: Rate Limit Exceeded
    end
    
    rect rgb(255, 250, 240)
        Note over CS: Detección de Error
        CS->>CS: Analiza error_str
        CS->>CS: "429" in error_str?<br/>✅ Sí → Activar fallback
        CS->>CS: self.using_fallback = True
    end
    
    rect rgb(240, 255, 240)
        Note over CS,CFG: Configuración Fallback
        CS->>CFG: get_config('OLLAMA_BASE_URL')
        CFG-->>CS: http://localhost:11434/v1
        CS->>CFG: get_config('OLLAMA_MODEL')
        CFG-->>CS: cogito:3b
        CS->>CFG: get_config('OLLAMA_MAX_TOKENS')
        CFG-->>CS: 8000
        CS->>CFG: get_config('OLLAMA_CLIENT_TIMEOUT_SECONDS')
        CFG-->>CS: 120 segundos
    end
    
    rect rgb(240, 240, 255)
        Note over CS: Verificación de Contexto
        CS->>CS: Cuenta tokens aproximados
        CS->>CFG: get_config('OLLAMA_MAX_CONTEXT_TOKENS')
        CFG-->>CS: 100000 tokens
        
        alt Contexto > 100K tokens
            CS->>CFG: get_config('OLLAMA_TRUNCATE_MESSAGES_COUNT')
            CFG-->>CS: 10 mensajes
            CS->>CS: Trunca: messages[-10:]
            CS-->>U: ⚠️ Contexto truncado
        else Contexto OK
            CS->>CS: Mantiene contexto completo
        end
    end
    
    rect rgb(255, 240, 255)
        Note over CS,O: Ejecución con Ollama
        CS->>O: fallback_client.chat.completions.create()<br/>model=cogito:3b, stream=True
        CS->>CFG: get_config('OLLAMA_STREAM_TIMEOUT_SECONDS')
        CFG-->>CS: 180 segundos
        
        loop Streaming con Timeout
            O-->>CS: chunk
            CS->>CS: Verifica: time < 180s?
            CS-->>U: Renderiza chunk
        end
    end
    
    rect rgb(240, 255, 240)
        Note over CS: Finalización
        CS->>CS: using_fallback = True (mantiene estado)
        CS-->>U: ✅ Respuesta completa (vía Ollama)
        Note over U: Próximas peticiones también usarán Ollama
    end
```

---

## 📁 Diagrama: Estructura de Archivos y Clases

```mermaid
classDiagram
    %% Archivos principales
    class views_chat_py {
        <<module>>
        +chat_stream(request) : StreamingHttpResponse
        +ChatService
        +CerebrasToolsService
    }
    
    class chat_config_py {
        <<module>>
        +CHAT_CONFIG : dict
        +CHAT_CONTEXTS : dict
        +get_config(key, default)
        +get_context(key, **kwargs)
    }
    
    class forms_chat_config_py {
        <<module>>
        +ChatConfigForm
        +ChatContextForm
    }
    
    class views_chat_config_py {
        <<module>>
        +admin_chat_config(request)
        +admin_chat_contexts(request)
    }
    
    %% Clases principales
    class ChatService {
        -api_key : str
        -client : OpenAI
        -fallback_client : OpenAI
        -model_config : dict
        -fallback_config : dict
        -using_fallback : bool
        -tools_service : CerebrasToolsService
        -tools_enabled : bool
        +__init__(request)
        +chat_stream(message, history) : Generator
        +_call_llm_with_fallback(messages, stream) : Response
        +_generate_with_tools_stream(message, history) : Generator
        -_clean_history(history) : list
        -_get_system_context() : str
    }
    
    class CerebrasToolsService {
        -api_key : str
        -base_url : str
        -client : OpenAI
        +__init__(api_key, base_url, request)
        +get_tools_definition() : list
        +stream_with_tools(messages, max_rounds) : Generator
        -_call_tool_endpoint(endpoint, params) : dict
        -_execute_tool_call(tool_call) : dict
    }
    
    class ChatConfigForm {
        +MAX_HISTORY_MESSAGES : IntegerField
        +MAX_MESSAGE_LENGTH : IntegerField
        +MAX_TOOL_ROUNDS : IntegerField
        +CEREBRAS_API_KEY : CharField
        +CEREBRAS_BASE_URL : URLField
        +CEREBRAS_MODEL : ChoiceField
        +OLLAMA_BASE_URL : URLField
        +OLLAMA_MODEL : ChoiceField
        +HTTP_TOOLS_TIMEOUT_SECONDS : IntegerField
        +OLLAMA_CLIENT_TIMEOUT_SECONDS : IntegerField
        +OLLAMA_STREAM_TIMEOUT_SECONDS : IntegerField
        +OLLAMA_MAX_CONTEXT_TOKENS : IntegerField
        +OLLAMA_TRUNCATE_MESSAGES_COUNT : IntegerField
        +TOOLS_FALLBACK_BASE_URL : URLField
    }
    
    %% Relaciones
    views_chat_py --> ChatService : define
    views_chat_py --> CerebrasToolsService : define
    
    ChatService --> chat_config_py : lee config con get_config()
    CerebrasToolsService --> chat_config_py : lee config con get_config()
    
    ChatService --> CerebrasToolsService : usa para tools
    
    forms_chat_config_py --> ChatConfigForm : define
    views_chat_config_py --> forms_chat_config_py : usa
    views_chat_config_py --> chat_config_py : actualiza
```

---

## 🔄 Diagrama: Ciclo de Vida de una Sesión de Chat

```mermaid
stateDiagram-v2
    [*] --> Inicio: Usuario abre chat
    
    Inicio --> ConfigurandoServicio: Inicializa ChatService
    
    state ConfigurandoServicio {
        [*] --> LeyendoConfig: Leer chat_config.py
        LeyendoConfig --> CreandoClienteCerebras: get_config(CEREBRAS_*)
        CreandoClienteCerebras --> CreandoClienteOllama: OpenAI(base_url=cerebras)
        CreandoClienteOllama --> InicializandoTools: OpenAI(base_url=ollama)
        InicializandoTools --> [*]: CerebrasToolsService
    }
    
    ConfigurandoServicio --> EsperandoMensaje: Servicio listo
    
    EsperandoMensaje --> AnalizandoMensaje: Usuario envía mensaje
    
    state AnalizandoMensaje {
        [*] --> VerificandoHistorial: Limpiar historial
        VerificandoHistorial --> DetectandoNecesidad: MAX_HISTORY_MESSAGES
        
        DetectandoNecesidad --> NecesitaTools: Detecta keywords de datos
        DetectandoNecesidad --> NoNecesitaTools: Conversación simple
    }
    
    state ProcesandoSinTools {
        [*] --> LlamandoCerebras
        LlamandoCerebras --> StreamingRespuesta: Éxito
        LlamandoCerebras --> ActivandoFallback: Error 429/401/403
        
        state ActivandoFallback {
            [*] --> VerificandoContexto: using_fallback = True
            VerificandoContexto --> TruncandoSiNecesario: approx_tokens > MAX_CONTEXT
            VerificandoContexto --> ManteniendoContexto: approx_tokens <= MAX_CONTEXT
            TruncandoSiNecesario --> LlamandoOllama: messages[-TRUNCATE_COUNT:]
            ManteniendoContexto --> LlamandoOllama
            LlamandoOllama --> [*]
        }
        
        ActivandoFallback --> StreamingRespuesta
        StreamingRespuesta --> [*]: chunks al usuario
    }
    
    state ProcesandoConTools {
        [*] --> InicializandoRonda: Ronda 1
        
        state InicializandoRonda {
            [*] --> VerificandoLimites: MAX_TOOL_ROUNDS
            VerificandoLimites --> VerificandoTimeout: TOOL_TIMEOUT_SECONDS
            VerificandoTimeout --> [*]
        }
        
        InicializandoRonda --> LlamandoLLMConTools: Definir tools
        LlamandoLLMConTools --> EjecutandoTool: LLM decide tool
        
        state EjecutandoTool {
            [*] --> ParseandoToolCall
            ParseandoToolCall --> LlamandoAPI: HTTP_TOOLS_TIMEOUT
            LlamandoAPI --> ProcesandoResultado
            ProcesandoResultado --> [*]: tool_result
        }
        
        EjecutandoTool --> NecesitaOtraTool: finish_reason = 'tool_calls'
        EjecutandoTool --> GenerandoRespuestaFinal: finish_reason = 'stop'
        
        NecesitaOtraTool --> InicializandoRonda: Ronda N+1
        GenerandoRespuestaFinal --> [*]: Stream respuesta
    }
    
    AnalizandoMensaje --> ProcesandoSinTools: No necesita tools
    AnalizandoMensaje --> ProcesandoConTools: Necesita tools
    
    ProcesandoSinTools --> GuardandoSesion: Respuesta completa
    ProcesandoConTools --> GuardandoSesion: Respuesta completa
    
    GuardandoSesion --> EsperandoMensaje: Actualiza DB
    
    EsperandoMensaje --> [*]: Usuario cierra chat
```

---

## 🎯 Diagrama: Puntos de Configuración y sus Efectos

```mermaid
graph LR
    %% Estilos
    classDef config fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    classDef effect fill:#fff3e0,stroke:#ff9800,stroke-width:2px
    classDef critical fill:#ffebee,stroke:#f44336,stroke-width:3px
    
    subgraph CONFIGURACION["⚙️ CONFIGURACIÓN (chat_config.py)"]
        API_KEYS[CEREBRAS_API_KEY<br/>CEREBRAS_BASE_URL<br/>OLLAMA_BASE_URL]:::critical
        
        MODELS[CEREBRAS_MODEL<br/>OLLAMA_MODEL<br/>MAX_TOKENS<br/>TEMPERATURE<br/>TOP_P]:::config
        
        TIMEOUTS[HTTP_TOOLS_TIMEOUT_SECONDS<br/>OLLAMA_CLIENT_TIMEOUT_SECONDS<br/>OLLAMA_STREAM_TIMEOUT_SECONDS]:::config
        
        LIMITS[OLLAMA_MAX_CONTEXT_TOKENS<br/>OLLAMA_TRUNCATE_MESSAGES_COUNT<br/>MAX_TOOL_ROUNDS<br/>TOOL_TIMEOUT_SECONDS]:::config
        
        URLS[TOOLS_FALLBACK_BASE_URL]:::config
    end
    
    subgraph EFECTOS["💡 EFECTOS EN EL SISTEMA"]
        CONN[Conectividad<br/>a APIs]:::effect
        QUAL[Calidad de<br/>Respuestas]:::effect
        PERF[Performance<br/>y Velocidad]:::effect
        RELIAB[Confiabilidad<br/>y Errores]:::effect
        PORT[Portabilidad<br/>Multi-entorno]:::effect
    end
    
    API_KEYS -->|Determina| CONN
    API_KEYS -->|Afecta| PORT
    
    MODELS -->|Define| QUAL
    MODELS -->|Impacta| PERF
    
    TIMEOUTS -->|Controla| PERF
    TIMEOUTS -->|Mejora| RELIAB
    
    LIMITS -->|Optimiza| PERF
    LIMITS -->|Previene| RELIAB
    
    URLS -->|Habilita| PORT
    URLS -->|Garantiza| CONN
```

---

## 📈 Métricas del Sistema

### Configuraciones Totales: **24 parámetros**

| Categoría | Parámetros | Criticidad |
|-----------|------------|------------|
| **APIs y Conexiones** | 4 | 🔴 Alta |
| **Modelos IA** | 8 | 🟡 Media |
| **Timeouts** | 4 | 🔴 Alta |
| **Límites y Control** | 6 | 🟡 Media |
| **Caché y Performance** | 2 | 🟢 Baja |

### Archivos Principales: **4**
- `views_chat.py` (4,559 líneas)
- `chat_config.py` (314 líneas)
- `forms_chat_config.py` (236 líneas)
- `views_chat_config.py` (Admin handlers)

### Clases Clave: **2**
- `ChatService` (Principal)
- `CerebrasToolsService` (Herramientas)

### Flujos de Datos: **3**
1. Conversación Normal (Sin Tools)
2. Conversación con Herramientas (Tools)
3. Fallback Automático (Cerebras → Ollama)

---

**Generado:** 2025-10-19  
**Versión:** 1.0  
**Formato:** Mermaid Diagrams
