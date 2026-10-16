import os
import sys
import django
import logging

# Agregar el directorio padre al path de Python
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# Configurar el módulo de configuración de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

try:
    django.setup()
except Exception as e:
    print(f"Error al configurar Django: {e}")
    sys.exit(1)

from indicadores.views import CerebrasToolsService

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_tools_basic():
    """Test básico de inicialización de tools"""
    try:
        # Usar tu API key
        api_key = os.environ.get('CEREBRAS_API_KEY') or os.environ.get('OLLAMA_API_KEY', '')
        service = CerebrasToolsService(api_key)
        
        print("✅ Servicio inicializado correctamente")
        
        # Verificar que las tools estén definidas
        tools = service.get_tools_definition()
        print(f"✅ Tools definidas: {len(tools)}")
        for tool in tools:
            print(f"   - {tool['function']['name']}")
        
        return service
        
    except Exception as e:
        print(f"❌ Error inicializando servicio: {e}")
        return None

def test_api_endpoint(service):
    """Test directo de un endpoint de API"""
    try:
        print("\n🧪 Probando endpoint get_dominios...")
        result = service.call_api_endpoint("get_dominios")
        
        if "error" in result:
            print(f"❌ Error en API: {result['error']}")
        else:
            print(f"✅ API responde correctamente")
            print(f"   Datos recibidos: {len(str(result))} caracteres")
            if isinstance(result, list):
                print(f"   Dominios encontrados: {len(result)}")
            
        return result
        
    except Exception as e:
        print(f"❌ Error probando API: {e}")
        return None

def test_simple_tool_call(service):
    """Test de una tool call simple"""
    try:
        print("\n🧪 Probando tool call simple...")
        
        # Simular una tool call
        class MockToolCall:
            def __init__(self):
                self.function = MockFunction()
        
        class MockFunction:
            def __init__(self):
                self.name = "get_dominios_siied"
                self.arguments = '{"buscar": "salud"}'
        
        mock_call = MockToolCall()
        result = service.execute_tool_call(mock_call)
        
        print(f"✅ Tool call ejecutada")
        print(f"   Resultado: {result[:200]}...")
        
        return result
        
    except Exception as e:
        print(f"❌ Error en tool call: {e}")
        return None

if __name__ == "__main__":
    print("🚀 Iniciando pruebas de Cerebras Tools...")
    
    # Test 1: Inicialización
    service = test_tools_basic()
    if not service:
        print("❌ No se puede continuar sin servicio inicializado")
        exit(1)
    
    # Test 2: API directa
    api_result = test_api_endpoint(service)
    
    # Test 3: Tool call simulada
    tool_result = test_simple_tool_call(service)
    
    print("\n✅ Pruebas completadas. Si todo salió bien, puedes probar en el chat.")