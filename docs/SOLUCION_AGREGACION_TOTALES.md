# 🎯 Solución: Agregación de Totales en Microdata

**Fecha:** 3 de Noviembre de 2025  
**Problema:** Totales calculados incorrectamente cuando no son simples sumas  
**Solución:** Campo `tipo_agregacion_total` en modelo `DominioDesagregacion`

---

## 🚨 Problema Identificado

### **Comportamiento Actual (Incorrecto)**
Cuando se procesa microdata con producto cartesiano, el comando **SIEMPRE suma** las desagregaciones para calcular el "Total":

```python
# Línea 699-715 (antes)
def calcular_total_desde_columnas(...):
    suma = 0.0  # ⚠️ SIEMPRE suma
    for header, mapping in mapeo_columnas.items():
        # ... lógica de coincidencia ...
        suma += valor
    return suma
```

**Casos que fallan:**

| Indicador | Desagregaciones | Total Real | Total Calculado (Incorrecto) |
|-----------|-----------------|------------|------------------------------|
| Tasa de Desempleo | Sector1: 5.2%, Sector2: 8.1%, Sector3: 6.7% | **6.5%** (promedio ponderado) | ❌ **20.0%** (suma) |
| Edad Promedio | 0-14: 7, 15-64: 35, 65+: 72 | **38 años** (promedio) | ❌ **114 años** (suma) |
| PIB Total | PIB1: 100M, PIB2: 150M, PIB3: 80M | **350M** (viene calculado) | ❌ **330M** (suma parcial) |
| Coeficiente Gini | Por quintil: 0.3, 0.4, 0.5, 0.6, 0.7 | **0.504** (cálculo complejo) | ❌ **2.5** (suma) |

---

## ✅ Solución Implementada

### **Filosofía: Separación de Responsabilidades**

1. **El modelo dominio** define SI se calcula o no el Total
2. **La fórmula de la regla** define CÓMO se calcula (si es complejo)

### **Campo Nuevo en Modelo**

```python
# indicadores/models.py

class DominioDesagregacion(models.Model):
    # ... campos existentes ...
    
    tipo_agregacion_total = models.CharField(
        max_length=20,
        choices=[
            ('suma', 'Sumar desagregaciones (default)'),
            ('ninguno', 'No calcular - Extraer del CSV'),
        ],
        default='suma',
        help_text=(
            "Estrategia para calcular 'Total':\n"
            "• SUMA: Calcula sumando todas las desagregaciones (población, conteos)\n"
            "• NINGUNO: No calcula, busca 'Total' directamente en el CSV (tasas, índices precalculados)"
        )
    )
```

---

## 🔄 Flujo de Procesamiento

### **Caso A: `tipo_agregacion_total = 'suma'` (Default)**

```
CSV:
Año,Comuna,Hombres,Mujeres
2024,Cali,1000000,1200000

Dominio: Sexo
Desagregaciones: Hombres, Mujeres, Total
tipo_agregacion_total: suma

PROCESO:
1. ✅ Sumar desagregaciones: 1000000 + 1200000 = 2200000
2. ✅ Si hay fórmula, aplicarla: valor_celda / 1000 = 2200
3. ✅ Guardar dato con desagregación "Total"

RESULTADO: Total = 2200 (miles de personas) ✅
```

### **Caso B: `tipo_agregacion_total = 'ninguno'`**

```
CSV:
Año,Comuna,Desempleo_Sector1,Desempleo_Sector2,Desempleo_Sector3,Desempleo_Total
2024,Cali,5.2,8.1,6.7,6.5

Dominio: Sector Económico
Desagregaciones: Sector1, Sector2, Sector3, Total
tipo_agregacion_total: ninguno

PROCESO:
1. ✅ NO sumar (5.2 + 8.1 + 6.7 = 20.0 ❌)
2. ✅ Buscar columna "Desempleo_Total" en CSV
3. ✅ Extraer valor: 6.5
4. ✅ Si hay fórmula, aplicarla: valor_celda (sin cambios)
5. ✅ Guardar dato con desagregación "Total"

RESULTADO: Total = 6.5% ✅
```

---

## 🧮 Cálculos Complejos: Usar Fórmulas

### **Ejemplo 1: Promedio Simple**

**Problema:** Edad promedio NO es suma de grupos etarios

```python
# Configuración
Dominio: Grupo Etario
tipo_agregacion_total: 'suma'  # Suma primero

# Regla de extracción
formula: "valor_celda / 3"  # Divide suma entre 3 grupos
```

**Flujo:**
```
CSV:
Año,Comuna,Edad_0_14,Edad_15_64,Edad_65plus
2024,Cali,7,35,72

1. Suma: 7 + 35 + 72 = 114
2. Fórmula: 114 / 3 = 38
3. Total = 38 años ✅
```

---

### **Ejemplo 2: Promedio Ponderado por Población**

**Problema:** Tasa de desempleo total debe ponderar por población de cada sector

```python
# Configuración
Dominio: Sector Económico
tipo_agregacion_total: 'suma'  # Suma primero (numerador y denominador por separado)

# CSV debe tener MÚLTIPLES VARIABLES
Año,Comuna,Desempleados_S1,Poblacion_S1,Desempleados_S2,Poblacion_S2,Desempleados_S3,Poblacion_S3
2024,Cali,2600,50000,6480,80000,2010,30000

# Regla de extracción (CLAVE: fórmula compleja)
formula: "(Desempleados_S1 + Desempleados_S2 + Desempleados_S3) / (Poblacion_S1 + Poblacion_S2 + Poblacion_S3) * 100"
```

**Flujo:**
```
1. Suma cada variable:
   - Total Desempleados = 2600 + 6480 + 2010 = 11090
   - Total Población = 50000 + 80000 + 30000 = 160000

2. Fórmula opera sobre totales:
   - (11090 / 160000) * 100 = 6.93%

3. Total = 6.93% ✅
```

**⚠️ IMPORTANTE:** La fórmula debe referenciar TODAS las variables del CSV, no `valor_celda`.

---

### **Ejemplo 3: Índice Precalculado (Gini, IDH, etc.)**

**Problema:** Coeficiente Gini total viene calculado por la fuente, NO se puede sumar

```python
# Configuración
Dominio: Quintil de Ingreso
tipo_agregacion_total: 'ninguno'  # NO calcular, extraer directo

# CSV
Año,Comuna,Gini_Q1,Gini_Q2,Gini_Q3,Gini_Q4,Gini_Q5,Gini_Total
2024,Cali,0.30,0.40,0.50,0.60,0.70,0.504

# Regla de extracción
formula: "valor_celda"  # Sin cambios
```

**Flujo:**
```
1. NO suma: 0.30 + 0.40 + ... = 2.5 ❌
2. Busca columna "Gini_Total" en CSV
3. Extrae: 0.504
4. Fórmula no modifica: 0.504
5. Total = 0.504 ✅
```

---

## 📋 Guía de Configuración

### **¿Cuándo usar `tipo_agregacion_total = 'suma'`?**

✅ **Conteos absolutos:**
- Población total
- Número de estudiantes
- Cantidad de empresas
- Hectáreas de cultivo

✅ **Conteos que se suman:**
- Ingresos totales (si son aditivos)
- Gastos totales
- Empleos creados

✅ **Cuando hay fórmula simple sobre suma:**
- Promedio: `valor_celda / cantidad`
- Tasa: `(numerador_total / denominador_total) * 100`

---

### **¿Cuándo usar `tipo_agregacion_total = 'ninguno'`?**

✅ **Tasas y porcentajes precalculados:**
- Tasa de desempleo total (si viene calculada)
- Porcentaje de pobreza total
- Tasa de cobertura

✅ **Índices compuestos:**
- Coeficiente de Gini
- IDH (Índice de Desarrollo Humano)
- Índice de precios
- NBI (Necesidades Básicas Insatisfechas)

✅ **Promedios no simples:**
- Media geométrica
- Mediana
- Moda

✅ **Valores que no se pueden derivar:**
- PIB per cápita (si no tienes población)
- Cualquier métrica que requiera datos adicionales no presentes

---

## 🛠️ Implementación Técnica

### **Cambios en Código**

**1. Modelo (líneas 192-214):**
```python
# Nuevo campo
tipo_agregacion_total = models.CharField(
    max_length=20,
    choices=TIPO_AGREGACION_TOTAL_CHOICES,
    default='suma',
    help_text="..."
)
```

**2. Comando cartesiano (líneas 259-298):**
```python
# Verificar tipo de agregación
tipo_agregacion = getattr(dominio_con_total, 'tipo_agregacion_total', 'suma')

if tipo_agregacion == 'ninguno':
    # Buscar Total en CSV directamente
    valor = self.obtener_valor_para_combinacion(...)
else:
    # Calcular sumando (comportamiento actual)
    valor = self.calcular_total_desde_columnas(...)
```

**3. Logs mejorados:**
```
[TOTAL-SUMA] Dominio 'Sexo': Sumado de desagregaciones = 2200000
[TOTAL-DIRECTO] Dominio 'Sector': Extraído directamente del CSV = 6.5
[FÓRMULA] Aplicada sobre Total: resultado = 2200
```

---

## 📝 Migración Django

### **Crear migración:**
```bash
python manage.py makemigrations indicadores
```

**Archivo generado:** `indicadores/migrations/000X_dominiodesagregacion_tipo_agregacion.py`

```python
# Generated migration

from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('indicadores', '000X_previous_migration'),
    ]

    operations = [
        migrations.AddField(
            model_name='dominiodesagregacion',
            name='tipo_agregacion_total',
            field=models.CharField(
                choices=[
                    ('suma', 'Sumar desagregaciones (default)'),
                    ('ninguno', 'No calcular - Extraer del CSV')
                ],
                default='suma',
                help_text='Estrategia para calcular \'Total\':\n...',
                max_length=20
            ),
        ),
    ]
```

### **Aplicar migración:**
```bash
python manage.py migrate indicadores
```

**Resultado:**
```
Running migrations:
  Applying indicadores.000X_dominiodesagregacion_tipo_agregacion... OK
```

---

## 🧪 Testing

### **Test Case 1: Suma Simple**
```python
def test_total_suma_poblacion():
    # Setup
    dominio = DominioDesagregacion.objects.create(
        nombre='Sexo',
        tipo='tematica',
        tipo_agregacion_total='suma'  # Default
    )
    
    # ... crear desagregaciones y microdata ...
    
    # Execute
    call_command('procesar_microdata_cartesiano', ...)
    
    # Assert
    dato_total = Dato.objects.get(
        indicador=indicador,
        desagregaciones_tematicas__nombre='Total'
    )
    assert dato_total.valor_dato == 2200000  # Suma de H + M
```

### **Test Case 2: Extracción Directa**
```python
def test_total_ninguno_tasa():
    # Setup
    dominio = DominioDesagregacion.objects.create(
        nombre='Sector',
        tipo='tematica',
        tipo_agregacion_total='ninguno'  # No calcular
    )
    
    # CSV con columna "Total" explícita
    csv_content = """
    Año,Comuna,Sector1,Sector2,Sector3,Total
    2024,Cali,5.2,8.1,6.7,6.5
    """
    
    # Execute
    call_command('procesar_microdata_cartesiano', ...)
    
    # Assert
    dato_total = Dato.objects.get(
        indicador=indicador,
        desagregaciones_tematicas__nombre='Total'
    )
    assert dato_total.valor_dato == 6.5  # NO es 20.0 (suma)
```

### **Test Case 3: Fórmula sobre Total**
```python
def test_total_con_formula():
    # Setup
    dominio = DominioDesagregacion.objects.create(
        nombre='Grupo Etario',
        tipo='tematica',
        tipo_agregacion_total='suma'
    )
    
    regla = ReglaExtraccion.objects.create(
        formula='valor_celda / 3'  # Promedio simple
    )
    
    # CSV: edades 7, 35, 72
    
    # Execute
    call_command('procesar_microdata_cartesiano', ...)
    
    # Assert
    dato_total = Dato.objects.get(
        indicador=indicador,
        desagregaciones_tematicas__nombre='Total'
    )
    # (7 + 35 + 72) / 3 = 38
    assert round(dato_total.valor_dato) == 38
```

---

## 🎓 Capacitación para Usuarios Admin

### **Checklist al Crear Dominio:**

1. **Identificar naturaleza del indicador:**
   ```
   ¿Los valores de las desagregaciones se pueden SUMAR para obtener el total?
   
   SI → tipo_agregacion_total = 'suma'
   Ejemplos: población, conteos, cantidades físicas
   
   NO → tipo_agregacion_total = 'ninguno'
   Ejemplos: tasas, porcentajes, índices, promedios complejos
   ```

2. **Si usas 'ninguno', verificar CSV:**
   ```
   ¿El CSV incluye una columna/valor para "Total"?
   
   SI → ✅ Proceder
   NO → ❌ Cambiar a 'suma' y usar fórmula compleja
   ```

3. **Si usas 'suma' con cálculo complejo:**
   ```
   Configura la fórmula de la regla de extracción:
   - Promedio: valor_celda / cantidad
   - Tasa ponderada: (var1*peso1 + var2*peso2) / (peso1 + peso2)
   ```

---

## 📊 Auditoría de Dominios Existentes

### **Script de Revisión:**
```python
# Script one-time para auditar dominios

from indicadores.models import DominioDesagregacion, Indicador

# Identificar dominios sospechosos (probablemente NO son sumas)
keywords_no_suma = [
    'tasa', 'porcentaje', 'índice', 'indice', 'coeficiente',
    'promedio', 'media', 'mediana', 'ratio', 'proporción'
]

dominios = DominioDesagregacion.objects.filter(
    tipo='tematica',
    tipo_agregacion_total='suma'  # Default, posiblemente incorrecto
)

print("🔍 AUDITORÍA DE DOMINIOS\n")
print("Dominios que probablemente necesitan tipo_agregacion_total='ninguno':\n")

for dominio in dominios:
    nombre_lower = dominio.nombre.lower()
    sospechoso = any(kw in nombre_lower for kw in keywords_no_suma)
    
    if sospechoso:
        indicadores = Indicador.objects.filter(
            dominios_desagregacion_tematica=dominio
        )
        
        print(f"⚠️  {dominio.nombre}")
        print(f"   Indicadores afectados: {indicadores.count()}")
        
        if indicadores.exists():
            print(f"   Ejemplos:")
            for ind in indicadores[:3]:
                print(f"     - {ind.nombre}")
        
        print(f"   Acción sugerida: Revisar si debe ser 'ninguno'\n")
```

**Output esperado:**
```
🔍 AUDITORÍA DE DOMINIOS

Dominios que probablemente necesitan tipo_agregacion_total='ninguno':

⚠️  Sector Económico (Tasa Desempleo)
   Indicadores afectados: 5
   Ejemplos:
     - Tasa de desempleo por sector
     - Tasa de informalidad laboral
     - Tasa de ocupación sectorial
   Acción sugerida: Revisar si debe ser 'ninguno'

⚠️  Quintil de Ingreso (Coeficiente)
   Indicadores afectados: 2
   Ejemplos:
     - Coeficiente de Gini
     - Índice de concentración
   Acción sugerida: Revisar si debe ser 'ninguno'
```

---

## 🎯 Beneficios de la Solución

✅ **Precisión:** Totales correctos según naturaleza del indicador  
✅ **Flexibilidad:** Fórmulas complejas en regla de extracción  
✅ **Simplicidad:** Solo 2 opciones (suma o ninguno)  
✅ **Mantenible:** Lógica centralizada en un campo  
✅ **Retrocompatible:** Default='suma' mantiene comportamiento actual  
✅ **Observable:** Logs claros de qué estrategia se usó  
✅ **Escalable:** Fácil agregar más opciones si se necesita

---

## 📚 Documentación Relacionada

- `docs/PROPUESTA_DESAGREGACIONES_TEMATICAS_EN_COLUMNAS.md`
- `docs/WIZARD_IMPLEMENTACION_COMPLETA.md`
- `indicadores/management/commands/procesar_microdata_cartesiano.py`
- `indicadores/models.py` (líneas 186-221)

---

**Fin de la documentación**  
**Próximo paso:** Ejecutar migración y testear con casos reales
