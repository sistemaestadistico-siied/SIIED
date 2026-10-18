"""
Formularios para configuración del chat sin usar modelos de BD
"""
from django import forms
from django.core.exceptions import ValidationError


class ChatConfigForm(forms.Form):
    """Formulario para configurar parámetros del chat"""
    
    # Historial de conversación
    MAX_HISTORY_MESSAGES = forms.IntegerField(
        label="Máximo de mensajes en historial",
        min_value=1,
        max_value=50,
        help_text="Número máximo de mensajes que se mantienen en el historial de conversación"
    )
    
    MAX_MESSAGE_LENGTH = forms.IntegerField(
        label="Longitud máxima de mensaje",
        min_value=100,
        max_value=5000,
        help_text="Longitud máxima de cada mensaje en caracteres"
    )
    
    # Herramientas (Tools)
    MAX_TOOL_ROUNDS = forms.IntegerField(
        label="Máximo de rondas de herramientas",
        min_value=1,
        max_value=10,
        help_text="Número máximo de rondas que el agente puede usar herramientas"
    )
    
    TOOL_TIMEOUT_SECONDS = forms.IntegerField(
        label="Timeout de herramientas (segundos)",
        min_value=30,
        max_value=300,
        help_text="Tiempo máximo de espera para la ejecución de herramientas"
    )
    
    MAX_TOOL_CHAIN_LENGTH = forms.IntegerField(
        label="Longitud máxima de cadena de herramientas",
        min_value=1,
        max_value=15,
        help_text="Número máximo de herramientas que se pueden encadenar"
    )
    
    # Caché
    CONTEXT_CACHE_TIMEOUT = forms.IntegerField(
        label="Timeout de caché de contexto (segundos)",
        min_value=300,
        max_value=86400,
        help_text="Tiempo de vida del caché de contexto (3600 = 1 hora, 21600 = 6 horas)"
    )
    
    CONTEXT_CACHE_KEY = forms.CharField(
        label="Clave de caché de contexto",
        max_length=100,
        help_text="Identificador único para el caché de contexto del sistema"
    )
    
    # Gestión de requests
    REQUEST_MAX_AGE_MINUTES = forms.IntegerField(
        label="Edad máxima de requests (minutos)",
        min_value=1,
        max_value=60,
        help_text="Tiempo máximo que un request puede estar activo"
    )
    
    CLEANUP_MAX_TIME = forms.FloatField(
        label="Tiempo máximo de limpieza (segundos)",
        min_value=0.5,
        max_value=10.0,
        help_text="Tiempo máximo permitido para operaciones de limpieza"
    )
    
    MAX_ACTIVE_SESSIONS = forms.IntegerField(
        label="Máximo de sesiones activas",
        min_value=10,
        max_value=100,
        help_text="Número máximo de sesiones de chat activas simultáneas"
    )
    
    # Búsqueda y datos relevantes
    MAX_RELEVANT_DATA_LENGTH = forms.IntegerField(
        label="Longitud máxima de datos relevantes",
        min_value=100,
        max_value=2000,
        help_text="Longitud máxima de datos relevantes a incluir en el contexto"
    )
    
    SEARCH_TOP_K = forms.IntegerField(
        label="Top K resultados de búsqueda",
        required=False,
        min_value=1,
        max_value=50,
        help_text="Número de resultados de búsqueda (dejar vacío para sin límite)"
    )
    
    # Memoria y contexto conversacional
    ENABLE_CONTEXT_MEMORY = forms.BooleanField(
        label="Habilitar memoria de contexto",
        required=False,
        help_text="Activar memoria de contexto entre mensajes"
    )
    
    MIN_SIMILARITY_THRESHOLD = forms.FloatField(
        label="Umbral mínimo de similitud",
        min_value=0.0,
        max_value=1.0,
        help_text="Umbral mínimo de similitud para búsquedas semánticas (0.0 - 1.0)"
    )
    
    # Configuración de Modelos IA - API Principal
    CEREBRAS_API_KEY = forms.CharField(
        label="API Key Principal",
        max_length=200,
        widget=forms.PasswordInput(render_value=True),
        help_text="Clave de API para el servicio principal (ej: Cerebras, OpenAI)"
    )
    
    CEREBRAS_BASE_URL = forms.URLField(
        label="URL Base Principal",
        initial='https://api.cerebras.ai/v1',
        help_text="URL base de la API principal (ej: https://api.cerebras.ai/v1)"
    )
    
    CEREBRAS_MODEL = forms.CharField(
        label="Modelo Principal",
        max_length=100,
        help_text="Nombre del modelo a utilizar (ej: gpt-oss-120b, gpt-4)"
    )
    
    CEREBRAS_MAX_TOKENS = forms.IntegerField(
        label="Max Tokens Principal",
        min_value=1000,
        max_value=128000,
        help_text="Número máximo de tokens que puede generar el modelo principal"
    )
    
    CEREBRAS_TEMPERATURE = forms.FloatField(
        label="Temperature Principal",
        min_value=0.0,
        max_value=2.0,
        help_text="Creatividad del modelo (0.0 = determinista, 2.0 = muy creativo)"
    )
    
    CEREBRAS_TOP_P = forms.FloatField(
        label="Top P Principal",
        min_value=0.0,
        max_value=1.0,
        help_text="Nucleus sampling (0.0 - 1.0, recomendado: 0.9-0.95)"
    )

    LLM_REASONING_EFFORT = forms.ChoiceField(
        label="Nivel de razonamiento (chat)",
        choices=[
            ('minimal', 'Minimal'), ('low', 'Low'),
            ('medium', 'Medium'), ('high', 'High'),
        ],
        initial='low',
        help_text="Cuánto 'piensa' el modelo en el chat. 'low' responde rápido; "
                  "'high' tarda más pero es más consistente."
    )

    CEREBRAS_TIMEOUT_SECONDS = forms.FloatField(
        label="Timeout API Principal (segundos)",
        min_value=5.0,
        max_value=300.0,
        help_text="Timeout HTTP de cada llamada al proveedor principal"
    )

    CEREBRAS_TOOL_ROUND_MAX_TOKENS = forms.IntegerField(
        label="Max tokens por ronda de tools",
        min_value=500,
        max_value=20000,
        help_text="Techo de tokens en las llamadas intermedias con herramientas "
                  "(la respuesta final usa Max Tokens Principal)"
    )

    # Resiliencia y streaming del LLM
    LLM_PRIMARY_COOLDOWN_SECONDS = forms.IntegerField(
        label="Cooldown del primario (segundos)",
        min_value=30,
        max_value=7200,
        help_text="Si el proveedor principal falla, se usa el respaldo directo "
                  "durante este tiempo sin reintentar el primario"
    )

    LLM_STREAM_KEEPALIVE_SECONDS = forms.FloatField(
        label="Keep-alive del stream (segundos)",
        min_value=5.0,
        max_value=120.0,
        help_text="Intervalo de señales keep-alive en el stream SSE para que "
                  "proxies/gateways no cierren la conexión"
    )

    LLM_STRUCTURED_MAX_SECONDS = forms.FloatField(
        label="Presupuesto generación estructurada (segundos)",
        min_value=10.0,
        max_value=300.0,
        help_text="Tiempo total para generate_structured (tableros, reglas de "
                  "extracción, metadata, noticias, quizzes)"
    )

    LLM_STRUCTURED_REASONING_EFFORT = forms.ChoiceField(
        label="Razonamiento en generación estructurada",
        choices=[
            ('minimal', 'Minimal'), ('low', 'Low'),
            ('medium', 'Medium'), ('high', 'High'),
        ],
        initial='high',
        help_text="Nivel de razonamiento para specs JSON (tableros, reglas). "
                  "'high' da specs más consistentes"
    )

    MAX_ACTIVE_USERS = forms.IntegerField(
        label="Máximo de usuarios activos",
        min_value=5,
        max_value=500,
        help_text="Número máximo de usuarios activos simultáneos en el chat"
    )

    LLM_FORCE_IPV4 = forms.BooleanField(
        label="Forzar IPv4 en llamadas al LLM",
        required=False,
        help_text="Evita stalls de ~40s en hosts sin IPv6 funcional. Desactivar "
                  "solo si el servidor tiene IPv6 operativo"
    )

    # Voz (TTS)
    TTS_MODEL = forms.CharField(
        label="Modelo TTS preferido",
        max_length=100,
        required=False,
        help_text="Modelo de voz (ej. pico2wave, coqui XTTS). Vacío = automático"
    )

    TTS_SPEAKER_WAV = forms.CharField(
        label="WAV de referencia TTS",
        max_length=300,
        required=False,
        help_text="Ruta al .wav de referencia para clonar voz (solo Coqui XTTS)"
    )

    # Configuración de Modelos IA - API Respaldo
    OLLAMA_API_KEY = forms.CharField(
        label="API Key Respaldo",
        max_length=200,
        required=False,
        widget=forms.PasswordInput(render_value=True),
        help_text="Clave de API para el servicio de respaldo (opcional para Ollama local)"
    )
    
    OLLAMA_BASE_URL = forms.URLField(
        label="URL Base Respaldo",
        initial='http://localhost:11434/v1',
        help_text="URL base del servicio de respaldo (ej: http://localhost:11434/v1)"
    )
    
    OLLAMA_MODEL = forms.CharField(
        label="Modelo Respaldo",
        max_length=100,
        help_text="Nombre del modelo de respaldo (ej: cogito:3b, llama2)"
    )
    
    OLLAMA_MAX_TOKENS = forms.IntegerField(
        label="Max Tokens Respaldo",
        min_value=500,
        max_value=128000,
        help_text="Número máximo de tokens para el modelo de respaldo"
    )
    
    OLLAMA_TEMPERATURE = forms.FloatField(
        label="Temperature Respaldo",
        min_value=0.0,
        max_value=2.0,
        help_text="Creatividad del modelo de respaldo"
    )
    
    OLLAMA_TOP_P = forms.FloatField(
        label="Top P Respaldo",
        min_value=0.0,
        max_value=1.0,
        help_text="Nucleus sampling para respaldo"
    )
    
    OLLAMA_CLIENT_TIMEOUT_SECONDS = forms.IntegerField(
        label="Timeout Cliente Ollama (segundos)",
        min_value=30,
        max_value=300,
        help_text="Timeout del cliente HTTP de Ollama"
    )
    
    OLLAMA_STREAM_TIMEOUT_SECONDS = forms.IntegerField(
        label="Timeout Stream Ollama (segundos)",
        min_value=60,
        max_value=600,
        help_text="Timeout para streaming de respuestas de Ollama (CPU puede ser lento)"
    )
    
    OLLAMA_MAX_CONTEXT_TOKENS = forms.IntegerField(
        label="Max Tokens de Contexto (Ollama)",
        min_value=10000,
        max_value=128000,
        help_text="Límite máximo de tokens de contexto antes de truncar (Cogito soporta 128K)"
    )
    
    OLLAMA_TRUNCATE_MESSAGES_COUNT = forms.IntegerField(
        label="Mensajes a Mantener al Truncar",
        min_value=5,
        max_value=50,
        help_text="Número de mensajes recientes a mantener cuando se trunca el contexto"
    )
    
    # Timeouts y Límites HTTP
    HTTP_TOOLS_TIMEOUT_SECONDS = forms.IntegerField(
        label="Timeout HTTP de Herramientas (segundos)",
        min_value=10,
        max_value=120,
        help_text="Timeout para llamadas HTTP a herramientas (búsqueda, datos, etc.)"
    )
    
    TOOLS_FALLBACK_BASE_URL = forms.URLField(
        label="URL Base de Fallback para Herramientas",
        initial='http://127.0.0.1:8000',
        help_text="URL base de fallback cuando no se puede obtener dinámicamente"
    )


class ChatContextForm(forms.Form):
    """Formulario para editar contextos del sistema"""
    
    CONTEXT_CHOICES = [
        ('don_datico_base', 'Contexto Base de Don Datico'),
        ('tools_round_1', 'Primera Ronda con Herramientas'),
        ('tools_round_n', 'Rondas Subsiguientes'),
        ('conversational', 'Contexto Conversacional'),
        ('enhanced_tools', 'Contexto Mejorado con Herramientas'),
        ('fallback', 'Contexto de Respaldo'),
    ]
    
    context_key = forms.ChoiceField(
        label="Seleccionar Contexto",
        choices=CONTEXT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control', 'onchange': 'this.form.submit()'})
    )
    
    context_content = forms.CharField(
        label="Contenido del Contexto",
        widget=forms.Textarea(attrs={
            'rows': 25,
            'class': 'form-control',
            'style': 'font-family: monospace; font-size: 13px;'
        }),
        help_text="Edita el contenido del contexto seleccionado. Puedes usar variables con {variable}."
    )
    
    def clean_context_content(self):
        """Valida que el contenido del contexto sea válido"""
        content = self.cleaned_data.get('context_content')
        
        # Verificar que no esté vacío
        if not content or not content.strip():
            raise ValidationError("El contexto no puede estar vacío")
        
        # Verificar que las llaves estén balanceadas
        open_braces = content.count('{')
        close_braces = content.count('}')
        
        if open_braces != close_braces:
            raise ValidationError(
                f"Las llaves no están balanceadas: {open_braces} abiertas, {close_braces} cerradas"
            )
        
        return content


class ChatSuggestionsForm(forms.Form):
    """Formulario para editar las consultas sugeridas del chat"""
    
    CATEGORY_CHOICES = [
        ('exploratorias', '🔍 Exploratorias'),
        ('especificas', '🎯 Específicas'),
        ('comparativas', '📊 Comparativas'),
        ('datos_completos', '📁 Datos Completos'),
    ]
    
    category = forms.ChoiceField(
        label="Categoría",
        choices=CATEGORY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control', 'onchange': 'this.form.submit()'})
    )
    
    suggestions = forms.CharField(
        label="Consultas Sugeridas",
        widget=forms.Textarea(attrs={
            'rows': 12,
            'class': 'form-control',
            'style': 'font-family: monospace; font-size: 13px;',
            'placeholder': 'Una consulta por línea...'
        }),
        help_text="Ingresa una consulta sugerida por línea. Máximo 5 consultas por categoría."
    )
    
    def clean_suggestions(self):
        """Valida las consultas sugeridas"""
        content = self.cleaned_data.get('suggestions', '')
        
        if not content or not content.strip():
            raise ValidationError("Debe haber al menos una consulta sugerida")
        
        # Separar por líneas y limpiar
        lines = [line.strip() for line in content.strip().split('\n') if line.strip()]
        
        if len(lines) > 5:
            raise ValidationError("Máximo 5 consultas por categoría")
        
        if len(lines) < 1:
            raise ValidationError("Debe haber al menos una consulta sugerida")
        
        # Verificar longitud mínima de cada consulta
        for i, line in enumerate(lines, 1):
            if len(line) < 10:
                raise ValidationError(f"La consulta {i} es muy corta (mínimo 10 caracteres)")
            if len(line) > 150:
                raise ValidationError(f"La consulta {i} es muy larga (máximo 150 caracteres)")
        
        return lines  # Retornamos la lista limpia
