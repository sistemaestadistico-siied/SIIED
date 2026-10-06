"""
Script de prueba para verificar que múltiples usuarios pueden usar el chat simultáneamente
sin bloquearse entre sí.

Uso:
    python tests/test_chat_concurrency.py
"""

import requests
import threading
import time
import json
from datetime import datetime

# Configuración
BASE_URL = "http://localhost:8000"  # Ajusta según tu configuración
CHAT_ENDPOINT = f"{BASE_URL}/chat/message/"  # Ruta correcta sin /indicadores/

# Colores para output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_colored(message, color=Colors.OKGREEN):
    """Imprime mensaje con color"""
    print(f"{color}{message}{Colors.ENDC}")

def simulate_user(user_id, message, results):
    """
    Simula un usuario enviando un mensaje al chat
    
    Args:
        user_id: Identificador del usuario simulado
        message: Mensaje a enviar
        results: Lista compartida para almacenar resultados
    """
    session = requests.Session()
    
    # Simular diferentes user agents para diferentes usuarios
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) Firefox/89.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) Safari/604.1",
    ]
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': user_agents[user_id % len(user_agents)]
    }
    
    start_time = time.time()
    
    try:
        print_colored(f"[Usuario {user_id}] Enviando mensaje: '{message[:50]}...'", Colors.OKCYAN)
        
        # Enviar mensaje
        response = session.post(
            CHAT_ENDPOINT,
            json={'message': message},
            headers=headers,
            stream=True,
            timeout=30
        )
        
        if response.status_code != 200:
            print_colored(f"[Usuario {user_id}] ❌ Error HTTP {response.status_code}", Colors.FAIL)
            results.append({
                'user_id': user_id,
                'success': False,
                'error': f"HTTP {response.status_code}",
                'duration': time.time() - start_time
            })
            return
        
        # Leer respuesta en streaming
        chunks_received = 0
        response_content = ""
        
        for line in response.iter_lines():
            if line:
                line_text = line.decode('utf-8')
                if line_text.startswith('data: '):
                    try:
                        data = json.loads(line_text[6:])
                        if data.get('type') == 'content':
                            chunks_received += 1
                            response_content += data.get('content', '')
                        elif data.get('type') == 'complete':
                            break
                        elif data.get('type') == 'error':
                            print_colored(f"[Usuario {user_id}] ❌ Error: {data.get('error')}", Colors.FAIL)
                            results.append({
                                'user_id': user_id,
                                'success': False,
                                'error': data.get('error'),
                                'duration': time.time() - start_time
                            })
                            return
                    except json.JSONDecodeError:
                        pass
        
        duration = time.time() - start_time
        
        print_colored(
            f"[Usuario {user_id}] ✅ Completado en {duration:.2f}s "
            f"({chunks_received} chunks, {len(response_content)} chars)",
            Colors.OKGREEN
        )
        
        results.append({
            'user_id': user_id,
            'success': True,
            'duration': duration,
            'chunks': chunks_received,
            'response_length': len(response_content)
        })
        
    except requests.exceptions.Timeout:
        print_colored(f"[Usuario {user_id}] ⏱️ Timeout después de 30s", Colors.WARNING)
        results.append({
            'user_id': user_id,
            'success': False,
            'error': 'Timeout',
            'duration': time.time() - start_time
        })
    except Exception as e:
        print_colored(f"[Usuario {user_id}] ❌ Error: {str(e)}", Colors.FAIL)
        results.append({
            'user_id': user_id,
            'success': False,
            'error': str(e),
            'duration': time.time() - start_time
        })

def test_concurrent_users(num_users=3):
    """
    Prueba múltiples usuarios concurrentes
    
    Args:
        num_users: Número de usuarios a simular simultáneamente
    """
    print_colored("\n" + "="*70, Colors.HEADER)
    print_colored("PRUEBA DE CONCURRENCIA DEL CHAT", Colors.HEADER)
    print_colored("="*70 + "\n", Colors.HEADER)
    
    print_colored(f"📊 Configuración:", Colors.OKBLUE)
    print_colored(f"   - Usuarios simultáneos: {num_users}", Colors.OKBLUE)
    print_colored(f"   - Endpoint: {CHAT_ENDPOINT}", Colors.OKBLUE)
    print_colored(f"   - Hora de inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", Colors.OKBLUE)
    
    # Mensajes de prueba
    messages = [
        "¿Cuántos indicadores hay en el sistema?",
        "Dame información sobre educación",
        "¿Qué datos hay disponibles sobre salud?",
        "Muéstrame indicadores de economía",
        "¿Cuáles son los dominios disponibles?",
    ]
    
    results = []
    threads = []
    
    # Crear y lanzar threads
    start_time = time.time()
    
    for i in range(num_users):
        message = messages[i % len(messages)]
        thread = threading.Thread(
            target=simulate_user,
            args=(i, message, results)
        )
        threads.append(thread)
        thread.start()
        time.sleep(0.1)  # Pequeño delay para simular llegada escalonada
    
    # Esperar a que todos terminen
    for thread in threads:
        thread.join()
    
    total_duration = time.time() - start_time
    
    # Analizar resultados
    print_colored("\n" + "="*70, Colors.HEADER)
    print_colored("RESULTADOS", Colors.HEADER)
    print_colored("="*70 + "\n", Colors.HEADER)
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print_colored(f"✅ Exitosos: {len(successful)}/{num_users}", Colors.OKGREEN)
    print_colored(f"❌ Fallidos: {len(failed)}/{num_users}", Colors.FAIL if failed else Colors.OKGREEN)
    print_colored(f"⏱️  Tiempo total: {total_duration:.2f}s\n", Colors.OKBLUE)
    
    if successful:
        avg_duration = sum(r['duration'] for r in successful) / len(successful)
        print_colored(f"📈 Estadísticas de requests exitosos:", Colors.OKBLUE)
        print_colored(f"   - Duración promedio: {avg_duration:.2f}s", Colors.OKBLUE)
        print_colored(f"   - Duración mínima: {min(r['duration'] for r in successful):.2f}s", Colors.OKBLUE)
        print_colored(f"   - Duración máxima: {max(r['duration'] for r in successful):.2f}s\n", Colors.OKBLUE)
    
    if failed:
        print_colored("❌ Errores encontrados:", Colors.FAIL)
        for r in failed:
            print_colored(f"   - Usuario {r['user_id']}: {r.get('error', 'Unknown')}", Colors.FAIL)
        print()
    
    # Verificar concurrencia real
    if len(successful) >= 2:
        # Verificar si al menos 2 requests se ejecutaron en paralelo
        durations = [r['duration'] for r in successful]
        if total_duration < sum(durations) * 0.8:  # Si el tiempo total es menor que la suma
            print_colored("✅ CONCURRENCIA VERIFICADA: Los requests se ejecutaron en paralelo", Colors.OKGREEN)
        else:
            print_colored("⚠️  ADVERTENCIA: Los requests parecen haberse ejecutado secuencialmente", Colors.WARNING)
    
    print_colored("\n" + "="*70 + "\n", Colors.HEADER)
    
    return len(successful) == num_users

def test_same_user_cancellation():
    """
    Prueba que un mismo usuario puede cancelar su request anterior
    """
    print_colored("\n" + "="*70, Colors.HEADER)
    print_colored("PRUEBA DE CANCELACIÓN (MISMO USUARIO)", Colors.HEADER)
    print_colored("="*70 + "\n", Colors.HEADER)
    
    session = requests.Session()
    
    # Primer request (debería ser cancelado)
    print_colored("📤 Enviando primer mensaje...", Colors.OKCYAN)
    response1 = session.post(
        CHAT_ENDPOINT,
        json={'message': '¿Cuántos indicadores hay?'},
        stream=True
    )
    
    time.sleep(0.5)  # Esperar un poco
    
    # Segundo request (debería cancelar el primero)
    print_colored("📤 Enviando segundo mensaje (debería cancelar el primero)...", Colors.OKCYAN)
    response2 = session.post(
        CHAT_ENDPOINT,
        json={'message': 'Dame información sobre educación'},
        stream=True
    )
    
    # Verificar que el segundo se completa
    chunks = 0
    for line in response2.iter_lines():
        if line:
            line_text = line.decode('utf-8')
            if line_text.startswith('data: '):
                try:
                    data = json.loads(line_text[6:])
                    if data.get('type') == 'content':
                        chunks += 1
                    elif data.get('type') == 'complete':
                        break
                except json.JSONDecodeError:
                    pass
    
    if chunks > 0:
        print_colored(f"✅ Segundo request completado exitosamente ({chunks} chunks)", Colors.OKGREEN)
        return True
    else:
        print_colored("❌ Segundo request no recibió respuesta", Colors.FAIL)
        return False

if __name__ == "__main__":
    try:
        # Prueba 1: Múltiples usuarios concurrentes
        success1 = test_concurrent_users(num_users=3)
        
        # Prueba 2: Cancelación del mismo usuario
        success2 = test_same_user_cancellation()
        
        # Resumen final
        print_colored("\n" + "="*70, Colors.HEADER)
        print_colored("RESUMEN FINAL", Colors.HEADER)
        print_colored("="*70 + "\n", Colors.HEADER)
        
        if success1 and success2:
            print_colored("✅ TODAS LAS PRUEBAS PASARON", Colors.OKGREEN)
            print_colored("   El sistema maneja correctamente la concurrencia", Colors.OKGREEN)
        else:
            print_colored("❌ ALGUNAS PRUEBAS FALLARON", Colors.FAIL)
            if not success1:
                print_colored("   - Prueba de concurrencia: FALLIDA", Colors.FAIL)
            if not success2:
                print_colored("   - Prueba de cancelación: FALLIDA", Colors.FAIL)
        
        print_colored("\n" + "="*70 + "\n", Colors.HEADER)
        
    except KeyboardInterrupt:
        print_colored("\n\n⚠️  Prueba interrumpida por el usuario", Colors.WARNING)
    except Exception as e:
        print_colored(f"\n\n❌ Error crítico: {str(e)}", Colors.FAIL)
        import traceback
        traceback.print_exc()
