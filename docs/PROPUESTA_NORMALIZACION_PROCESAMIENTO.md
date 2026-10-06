# Propuesta: Normalización del Procesamiento de Indicadores

## 🎯 Objetivo
Unificar los puntos de entrada al procesamiento cartesiano para que SIEMPRE muestren diagnóstico y logs en tiempo real.

---

## 📊 Situación Actual

### Punto 1: Desde ReglaExtraccion (✅ Correcto)
**Ubicación:** Tabla de Reglas de Extracción → Botón "Procesar Datos"

**Flujo:**
```python
# admin.py - ReglaExtraccionAdmin.procesar_datos()
1. GET: Ejecuta comando diagnosticar_microdata
2. Muestra salida del diagnóstico
3. Pide confirmación al usuario
4. POST: Crea ProcesoExtraccion
5. Lanza procesamiento en background
6. Redirige a visor en vivo (proceso_en_vivo)
```

**✅ Ventajas:**
- Muestra diagnóstico previo
- Usuario puede revisar antes de procesar
- Logs en tiempo real
- Experiencia completa

---

### Punto 2: Desde Indicador (❌ Incompleto)
**Ubicación:** Tabla de Indicadores → Botón "Procesar Microdata"

**Flujo:**
```python
# admin.py - IndicadorAdmin.procesar_microdata()
1. Ejecuta directamente procesar_microdata_para_indicador()
2. No muestra diagnóstico
3. No hay confirmación
4. No redirige a visor de logs
5. Solo muestra mensaje de éxito/error
```

**❌ Problemas:**
- No hay diagnóstico previo
- Procesamiento directo sin revisión
- No se ven logs en tiempo real
- Experiencia incompleta

---

## ✅ Solución Propuesta

### Unificar Ambos Puntos al Mismo Flujo

**Cambios en `IndicadorAdmin`:**

```python
# indicadores/admin.py

class IndicadorAdmin(admin.ModelAdmin):
    # ... código existente ...
    
    def procesar_microdata_button(self, obj):
        """Botón para procesar microdata del indicador"""
        from django.urls import reverse
        if obj.id and obj.microdata:
            # CAMBIO: Redirigir al mismo flujo que ReglaExtraccion
            url = reverse('admin:indicador_diagnostico_procesamiento', args=[obj.id])
            return format_html(
                '<a class="button" href="{}" style="background: #4caf50; color: white;">🔄 Procesar Microdata</a>', 
                url
            )
        return ""
    procesar_microdata_button.short_description = 'Procesar'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            # NUEVO: Ruta unificada para diagnóstico y procesamiento
            path(
                'diagnostico-procesamiento/<int:indicador_id>/',
                self.admin_site.admin_view(self.diagnostico_y_procesamiento),
                name='indicador_diagnostico_procesamiento'
            ),
            # ... otras rutas existentes ...
        ]
        return custom_urls + urls
    
    def diagnostico_y_procesamiento(self, request, indicador_id):
        """
        Vista unificada para diagnóstico y procesamiento
        Igual que ReglaExtraccionAdmin.procesar_datos()
        """
        from django.http import HttpResponse, HttpResponseRedirect
        from django.template.response import TemplateResponse
        from django.urls import reverse
        import subprocess
        import sys
        import os
        
        try:
            indicador = Indicador.objects.get(id=indicador_id)
            
            # Verificar que tenga microdata y regla de extracción
            if not indicador.microdata:
                messages.error(request, '❌ El indicador no tiene microdata asociado')
                return HttpResponseRedirect('../../')
            
            try:
                regla = ReglaExtraccion.objects.get(indicador=indicador)
            except ReglaExtraccion.DoesNotExist:
                messages.error(
                    request,
                    '❌ No existe una Regla de Extracción para este indicador. '
                    'Créala primero desde el menú "Reglas de Extracción".'
                )
                return HttpResponseRedirect('../../')
            
            # Ejecutar diagnóstico
            manage_py_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'manage.py'
            )
            cmd = [
                sys.executable,
                manage_py_path,
                'diagnosticar_microdata',
                '--indicador-id',
                str(indicador.id)
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()
            diagnostic_output = stdout + stderr
            
            # POST: Usuario confirmó, iniciar procesamiento
            if request.method == 'POST':
                from .background import lanzar_procesamiento_en_background
                
                proceso = ProcesoExtraccion.objects.create(
                    indicador=indicador,
                    regla=regla,
                    estado='pendiente'
                )
                
                lanzar_procesamiento_en_background(proceso.id)
                
                messages.info(
                    request,
                    f'✅ Proceso #{proceso.id} iniciado para {indicador.nombre}. '
                    f'Será redirigido al visor en vivo.'
                )
                
                return HttpResponseRedirect(
                    reverse('indicadores:proceso_en_vivo', args=[proceso.id])
                )
            
            # GET: Mostrar diagnóstico y pedir confirmación
            context = {
                'title': f'Diagnóstico para {indicador.nombre}',
                'diagnostic_output': diagnostic_output,
                'indicador': indicador,
                'regla': regla,
                'opts': self.model._meta,
                'original': indicador,
                'has_view_permission': True,
                'has_change_permission': True,
            }
            
            return TemplateResponse(
                request,
                'admin/diagnostic_confirmation.html',
                context
            )
            
        except Indicador.DoesNotExist:
            messages.error(request, 'Indicador no encontrado')
            return HttpResponseRedirect('../../')
        except Exception as e:
            messages.error(request, f'Error al ejecutar diagnóstico: {str(e)}')
            return HttpResponseRedirect('../../')
```

---

## 📝 Template Reutilizable

El template `admin/diagnostic_confirmation.html` ya existe y funciona para ReglaExtraccion. Solo necesitamos asegurarnos de que sea genérico:

```html
<!-- indicadores/templates/admin/diagnostic_confirmation.html -->
{% extends "admin/base_site.html" %}
{% load i18n static %}

{% block extrastyle %}
<style>
.diagnostic-output {
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 20px;
    border-radius: 8px;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
    max-height: 600px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
}

.diagnostic-output .success { color: #4caf50; }
.diagnostic-output .error { color: #f44336; }
.diagnostic-output .warning { color: #ff9800; }
.diagnostic-output .info { color: #2196f3; }

.confirmation-box {
    background: #fff3cd;
    border: 2px solid #ffc107;
    border-radius: 8px;
    padding: 20px;
    margin: 20px 0;
}

.action-buttons {
    display: flex;
    gap: 15px;
    margin-top: 20px;
}

.btn-process {
    background: #4caf50;
    color: white;
    padding: 12px 24px;
    border: none;
    border-radius: 6px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s;
}

.btn-process:hover {
    background: #45a049;
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
}

.btn-cancel {
    background: #f44336;
    color: white;
    padding: 12px 24px;
    border: none;
    border-radius: 6px;
    font-size: 16px;
    font-weight: 600;
    text-decoration: none;
    display: inline-block;
    transition: all 0.3s;
}

.btn-cancel:hover {
    background: #da190b;
    text-decoration: none;
    color: white;
}
</style>
{% endblock %}

{% block content %}
<div class="diagnostic-container">
    <h1>{{ title }}</h1>
    
    <div class="info-box" style="background: #e3f2fd; border-left: 4px solid #2196f3; padding: 15px; margin: 20px 0;">
        <p style="margin: 0;">
            <strong>📊 Indicador:</strong> {{ indicador.nombre }}<br>
            {% if regla %}
            <strong>⚙️ Regla:</strong> {{ regla }}<br>
            {% endif %}
            <strong>📂 Microdata:</strong> {{ indicador.microdata.nombre }}
        </p>
    </div>
    
    <h2>Resultado del Diagnóstico</h2>
    <div class="diagnostic-output">{{ diagnostic_output }}</div>
    
    <div class="confirmation-box">
        <h3>⚠️ Confirmación Requerida</h3>
        <p>
            Revise el diagnóstico anterior. Si todo está correcto, puede proceder con el procesamiento.
            <br><br>
            <strong>Nota:</strong> El procesamiento se ejecutará en segundo plano y podrá ver los logs en tiempo real.
        </p>
        
        <form method="post" class="action-buttons">
            {% csrf_token %}
            <button type="submit" class="btn-process">
                ✅ Confirmar y Procesar
            </button>
            <a href="../../" class="btn-cancel">
                ❌ Cancelar
            </a>
        </form>
    </div>
</div>
{% endblock %}
```

---

## 🔄 Resultado Final

### Flujo Unificado

```
DESDE CUALQUIER PUNTO:
├─ Tabla de Reglas de Extracción → Botón "Procesar Datos"
│  └─ admin:reglaextraccion_procesar_datos
│     └─ ReglaExtraccionAdmin.procesar_datos()
│
└─ Tabla de Indicadores → Botón "Procesar Microdata"
   └─ admin:indicador_diagnostico_procesamiento
      └─ IndicadorAdmin.diagnostico_y_procesamiento()

AMBOS EJECUTAN EL MISMO FLUJO:
1. GET: Ejecutar diagnosticar_microdata
2. Mostrar salida en pantalla
3. Pedir confirmación
4. POST: Crear ProcesoExtraccion
5. Lanzar en background
6. Redirigir a indicadores:proceso_en_vivo
7. Ver logs en tiempo real
```

---

## 📋 Checklist de Implementación

- [ ] Modificar `IndicadorAdmin.procesar_microdata_button()` para cambiar URL
- [ ] Crear método `IndicadorAdmin.diagnostico_y_procesamiento()`
- [ ] Agregar ruta en `IndicadorAdmin.get_urls()`
- [ ] Verificar que template `diagnostic_confirmation.html` sea genérico
- [ ] Probar flujo desde tabla de Indicadores
- [ ] Probar flujo desde tabla de Reglas de Extracción
- [ ] Verificar que ambos redirijan a visor en vivo
- [ ] Documentar cambios

---

## 🎨 Mejora Visual Opcional

Diferenciar visualmente los botones según su función:

```python
def procesar_microdata_button(self, obj):
    if obj.id and obj.microdata:
        url = reverse('admin:indicador_diagnostico_procesamiento', args=[obj.id])
        
        # Verificar si tiene regla de extracción
        tiene_regla = ReglaExtraccion.objects.filter(indicador=obj).exists()
        
        if tiene_regla:
            # Verde: Todo listo para procesar
            return format_html(
                '<a class="button" href="{}" style="background: #4caf50; color: white;">'
                '🔄 Procesar Microdata</a>',
                url
            )
        else:
            # Naranja: Falta configuración
            return format_html(
                '<span style="background: #ff9800; color: white; padding: 5px 10px; border-radius: 4px;">'
                '⚠️ Falta Regla</span>'
            )
    return ""
```

---

## ✅ Beneficios

1. **Consistencia:** Misma experiencia desde cualquier punto
2. **Seguridad:** Siempre hay diagnóstico previo
3. **Transparencia:** Logs en tiempo real
4. **Mantenibilidad:** Un solo flujo que mantener
5. **UX mejorada:** Usuario siempre sabe qué está pasando

---

**Fecha:** 2025-01-20  
**Estado:** Propuesta  
**Prioridad:** Alta
