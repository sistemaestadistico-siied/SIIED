# 2. MODELO DE BASE DE DATOS

## Esquema Completo - 33 Modelos Django

### Jerarquía de Navegación (Menús)

#### 1. **MenuDominio**
```python
- id (PK)
- nombre: CharField(255)
- slug: SlugField(unique)
- descripcion: TextField
- icono: CharField(100)
- color: CharField(100)
- imagen_url: URLField
- orden: IntegerField
- activo: BooleanField
```
**Relaciones:**
- `temas` → MenuTema (one-to-many)

#### 2. **MenuTema**
```python
- id (PK)
- nombre: CharField(255)
- slug: SlugField(unique)
- descripcion: TextField
- imagen_url: URLField
- icono: CharField(100)
- orden: IntegerField
- activo: BooleanField
- dominio: ForeignKey(MenuDominio)
```
**Relaciones:**
- `subtemas` → MenuSubtema (one-to-many)
- Pertenece a: MenuDominio

#### 3. **MenuSubtema**
```python
- id (PK)
- nombre: CharField(255)
- slug: SlugField(unique)
- descripcion: TextField
- icono: CharField(100)
- imagen_url: URLField
- orden: IntegerField
- activo: BooleanField
- tema: ForeignKey(MenuTema)
- vista_django: CharField(255)
- url: URLField
```
**Relaciones:**
- `indicadores` → Indicador (one-to-many)
- Pertenece a: MenuTema

---

### Operaciones Estadísticas

#### 4. **OperacionEstadistica**
```python
- id (PK)
- codigo: CharField(50, unique)
- nombre: CharField(255)
- descripcion: TextField
- tipo_operacion: CharField(100)
- periodicidad: CharField(50)
- fecha_inicio: DateField
- fecha_fin: DateField
- entidad_recopiladora: CharField(255)
- metodologia: TextField
- url: URLField
- activo: BooleanField

# Campos extendidos del CSV OOEE ICED (35+ campos adicionales)
- c_organismo, organismo, suborganismo
- area_tem, tema, unidad_observ
- objetivo, descripcion_proceso
- principales_resultados
- enfoque_diferencial
- desagregacion_resultados
- doc_met, ficha_met, manual_op
- diccionario_datos, doc_cons_valid
- acciones_fortalecimiento
- sicode, cod_cg, estr_org
- tipo_oe_i, num, p_bp, proyecto
- fun_org, fun_sub, mop, pe
- adda_1, cant_amda, link_adda, link_pe
- amda_clas, anio_adda, anio_act_pe
- nombre_tematico, correo_tematico, celular_tematico
- nombre_coordinador, correo_coordinador, celular_coordinador
- grupo_productor, pdd
- responsable_actualizacion, estado_actualizacion
- pendiente, observaciones
```
**Relaciones:**
- `indicadores` → Indicador (one-to-many)
- `microdatos` → Microdata (one-to-many)

---

### Geografía y Desagregaciones

#### 5. **NivelGeografico**
```python
- id (PK)
- nombre: CharField(255)
- descripcion: TextField
```
**Relaciones:**
- `capas` → CapaGeo (one-to-many)
- `dominios_desagregacion` → DominioDesagregacion (one-to-many)

#### 6. **CapaGeo**
```python
- id (PK)
- nombre: CharField(255)
- descripcion: TextField
- nivel_geografico: ForeignKey(NivelGeografico)
```
**Relaciones:**
- `elementos` → ElementoGeo (one-to-many)
- `desagregaciones` → Desagregacion (one-to-many)

#### 7. **ElementoGeo**
```python
- id (PK)
- codigo: CharField(100)
- nombre: CharField(255)
- geom_wkt: TextField  # Geometría en WKT
- capa_geo: ForeignKey(CapaGeo)
```

#### 8. **DominioDesagregacion**
```python
- id (PK)
- nombre: CharField(255)
- tipo: CharField(20)  # CHOICES: 'tematica', 'geografica'
- nivel_geografico: ForeignKey(NivelGeografico, optional)
```
**Relaciones:**
- `desagregaciones` → Desagregacion (one-to-many)
- M2M inverso con Indicador (2 relaciones)

#### 9. **Desagregacion**
```python
- id (PK)
- nombre: CharField(255)
- codigo: CharField(100)
- descripcion: TextField
- dominio: ForeignKey(DominioDesagregacion)
- capa_geo: ForeignKey(CapaGeo, optional)
# Para desagregaciones temáticas de rangos
- es_rango: BooleanField
- valores_rango: JSONField
```
**Relaciones:**
- M2M con Dato (2 relaciones: geograficas y tematicas)
- M2M con Grafico (2 relaciones: predeterminadas)

---

### Indicadores y Datos

#### 10. **Indicador**
```python
- id (PK)
- nombre: CharField(255)
- descripcion: TextField
- definicion_operacional: TextField
- unidad_medida: CharField(100)
- fuente_datos: CharField(255)
- entidad_recopiladora: CharField(255)
- periodicidad: CharField(50)
- fecha_actualizacion: DateField
- notas: TextField
- subtema: ForeignKey(MenuSubtema)
- operacion: ForeignKey(OperacionEstadistica, optional)
- activo: BooleanField
- dominios_desagregacion_tematica: ManyToManyField(DominioDesagregacion)
- dominios_desagregacion_geografica: ManyToManyField(DominioDesagregacion)
- formula: TextField
- microdata: ForeignKey(Microdata, optional)
- mostrar_mapa: BooleanField
- orden: IntegerField
```
**Índices:**
```python
- ['subtema', 'orden', 'nombre']
- ['nombre']
- ['activo', 'subtema']
```
**Relaciones:**
- `datos` → Dato (one-to-many)
- `graficos` → Grafico (one-to-many)
- `regla_extraccion` → ReglaExtraccion (one-to-one)
- `procesos_extraccion` → ProcesoExtraccion (one-to-many)

#### 11. **Dato**
```python
- id (PK)
- indicador: ForeignKey(Indicador)
- fecha_dato: DateField
- valor_dato: DecimalField(20, 6)
- desagregaciones_geograficas: ManyToManyField(Desagregacion)
- desagregaciones_tematicas: ManyToManyField(Desagregacion)
```
**Índices:**
```python
- ['indicador', '-fecha_dato']  # Más común
- ['fecha_dato']
- ['indicador', 'fecha_dato', 'valor_dato']  # Comparativo
```

---

### Microdata y Procesamiento

#### 12. **Microdata**
```python
- id (PK)
- nombre: CharField(255)
- descripcion: TextField
- archivo_csv: FileField(upload_to='microdata/')
- fecha_carga: DateTimeField(auto_now_add)
- operacion: ForeignKey(OperacionEstadistica, optional)
```
**Relaciones:**
- `indicadores` → Indicador (one-to-many inverso)

#### 13. **ReglaExtraccion**
```python
- id (PK)
- indicador: OneToOneField(Indicador)
- columnas_fuente: JSONField  # Lista de columnas CSV
- columna_fecha: CharField(100, optional)
- formula: TextField
- filtros: JSONField
- orden_desagregaciones: JSONField
- ultima_ejecucion: DateTimeField
- estado_procesamiento: CharField(20)
  # CHOICES: 'pendiente', 'procesando', 'completado', 'error'
```
**Propiedades computadas:**
- `desagregaciones_asociadas` - Desagregaciones vinculadas via dominios

#### 14. **ProcesoExtraccion**
```python
- id (PK)
- indicador: ForeignKey(Indicador)
- regla: ForeignKey(ReglaExtraccion, optional)
- estado: CharField(20)
  # CHOICES: 'pendiente', 'procesando', 'completado', 'error'
- exit_code: IntegerField
- error_message: TextField
- created_at: DateTimeField(auto_now_add)
- started_at: DateTimeField
- finished_at: DateTimeField
```
**Índices:**
```python
- ['-created_at', 'estado']
- ['indicador', '-created_at']
```
**Relaciones:**
- `logs` → ProcesoLog (one-to-many)

#### 15. **ProcesoLog**
```python
- id (PK)
- proceso: ForeignKey(ProcesoExtraccion)
- nivel: CharField(10)  # CHOICES: 'INFO', 'ERROR', 'WARN', 'DEBUG'
- mensaje: TextField
- creado_en: DateTimeField(auto_now_add)
```
**Índices:**
```python
- ['proceso', '-creado_en']
- ['nivel', '-creado_en']
```

---

### Visualización

#### 16. **Grafico**
```python
- id (PK)
- indicador: ForeignKey(Indicador)
- nombre: CharField(255)
- descripcion: TextField
- tipo_grafico: CharField(20)
  # CHOICES: 'line', 'bar', 'bar_horizontal', 'area', 
  #          'barras_apiladas', 'areas_apiladas', 'pie',
  #          'piramide_poblacional', 'treemap'
- activo: BooleanField
- titulo, subtitulo: CharField(255)
- eje_x_titulo, eje_y_titulo: CharField(255)
- mostrar_eje_y2: BooleanField
- eje_y2_titulo: CharField(255)
- mostrar_leyenda: BooleanField
- posicion_leyenda: CharField(10)  # 'top', 'bottom', 'left', 'right'
- mostrar_cuadricula: BooleanField
- mostrar_valores: BooleanField
- mostrar_linea_tendencia: BooleanField
- ancho_completo: BooleanField
- altura_grafico: IntegerField(default=400, min=200, max=1000)
- margen_derecho, margen_inferior: IntegerField
- orden: IntegerField
- begin_at_zero: BooleanField
- rango_personalizado_min, rango_personalizado_max: FloatField
- mostrar_todas_etiquetas_x: BooleanField
- rango_anios_min, rango_anios_max: IntegerField
- desagregaciones_geograficas_predeterminadas: M2M(Desagregacion)
- desagregaciones_tematicas_predeterminadas: M2M(Desagregacion)
```
**Métodos:**
- `get_desagregaciones_geograficas_disponibles()`
- `get_desagregaciones_tematicas_disponibles()`

**Relaciones:**
- `series` → GraficoSerie (one-to-many)

#### 17. **GraficoSerie**
```python
- id (PK)
- grafico: ForeignKey(Grafico)
- desagregacion_geografica: ForeignKey(Desagregacion, optional)
- desagregacion_tematica: ForeignKey(Desagregacion, optional)
- nombre_personalizado: CharField(255)
- color: CharField(50)
- orden: IntegerField
```

---

### Contenidos y Noticias

#### 18. **NoticiaBanner**
```python
- id (PK)
- titulo: CharField(255)
- subtitulo: CharField(255)
- descripcion: TextField
- enlace_principal: URLField
- texto_enlace_principal: CharField(100, default="Leer más")
- imagen_url: URLField
- activa: BooleanField
- fecha_publicacion: DateTimeField(auto_now_add)
- fecha_actualizacion: DateTimeField(auto_now)
- orden: IntegerField
```
**Ordering:** `['-orden', '-fecha_publicacion']`
**Relaciones:**
- `estadisticas` → EstadisticaNoticia (one-to-many)
- `enlaces` → EnlaceNoticia (one-to-many)

#### 19. **EstadisticaNoticia**
```python
- noticia: ForeignKey(NoticiaBanner)
- titulo: CharField(100)
- valor: CharField(50)
- descripcion: CharField(255)
- orden: IntegerField
```

#### 20. **EnlaceNoticia**
```python
- noticia: ForeignKey(NoticiaBanner)
- titulo: CharField(100)
- url: URLField
- descripcion: CharField(255)
- orden: IntegerField
```

---

### Sistemas y Proyectos

#### 21. **CategoriaInformacion**
```python
- id (PK)
- nombre: CharField(255)
- slug: SlugField(unique)
- descripcion: TextField
- icono: CharField(100)
- color: CharField(50)
- orden: IntegerField
- activo: BooleanField
```
**Relaciones:**
- `sistemas` → SistemaInformacion (one-to-many)

#### 22. **SistemaInformacion**
```python
- id (PK)
- nombre: CharField(255)
- descripcion: TextField
- categoria: ForeignKey(CategoriaInformacion)
- tipo_enlace: CharField(20)
  # CHOICES: 'interno', 'externo', 'modal', 'descarga'
- url: URLField(500)
- abrir_nueva_ventana: BooleanField
- icono: CharField(100)
- imagen_url: URLField
- orden: IntegerField
- activo: BooleanField
- desarrollador: CharField(255)
- version: CharField(50)
- fecha_actualizacion: DateTimeField(auto_now)
- requiere_autenticacion: BooleanField
```

#### 23. **CategoriaProyecto**
```python
- id (PK)
- nombre: CharField(255)
- slug: SlugField(unique)
- descripcion: TextField
- icono: CharField(100)
- color: CharField(50)
- orden: IntegerField
- activo: BooleanField
```
**Relaciones:**
- `proyectos` → ProyectoInformacion (one-to-many)

#### 24. **ProyectoInformacion**
```python
- id (PK)
- nombre: CharField(255)
- descripcion: TextField
- categoria: ForeignKey(CategoriaProyecto)
- tipo_enlace: CharField(20)  # CHOICES igual que SistemaInformacion
- url: URLField(500)
- abrir_nueva_ventana: BooleanField
- icono, imagen_url: CharField/URLField
- orden: IntegerField
- activo: BooleanField
- dependencia_responsable: CharField(255)
- contacto_email: EmailField
- contacto_telefono: CharField(50)
- estado: CharField(20)
  # CHOICES: 'activo', 'en_desarrollo', 'mantenimiento', 'inactivo'
- fecha_inicio: DateField
- fecha_actualizacion: DateTimeField(auto_now)
- objetivos: TextField
- poblacion_objetivo: CharField(255)
```

---

### Infraestructura de Información (5 Niveles)

#### 25. **AreaInfraestructura** (Nivel 1)
```python
- id (PK)
- nombre: CharField(255)
- slug: SlugField(unique)
- descripcion: TextField
- icono: CharField(100)
- color: CharField(50)
- orden: IntegerField
- activo: BooleanField
```
**Relaciones:**
- `categorias` → CategoriaInfraestructura (one-to-many)

#### 26. **CategoriaInfraestructura** (Nivel 2)
```python
- id (PK)
- area: ForeignKey(AreaInfraestructura)
- nombre: CharField(255)
- slug: SlugField
- descripcion: TextField
- icono: CharField(100)
- imagen_url: URLField
- orden: IntegerField
- activo: BooleanField
```
**unique_together:** `['area', 'slug']`
**Relaciones:**
- `subcategorias` → SubcategoriaInfraestructura (one-to-many)

#### 27. **SubcategoriaInfraestructura** (Nivel 3)
```python
- id (PK)
- categoria: ForeignKey(CategoriaInfraestructura)
- nombre: CharField(255)
- slug: SlugField
- descripcion: TextField
- icono: CharField(100)
- imagen_url: URLField
- orden: IntegerField
- activo: BooleanField
```
**unique_together:** `['categoria', 'slug']`
**Relaciones:**
- `grupos_documentos` → GrupoDocumento (one-to-many)

#### 28. **GrupoDocumento** (Nivel 4)
```python
- id (PK)
- subcategoria: ForeignKey(SubcategoriaInfraestructura)
- nombre: CharField(255)
- slug: SlugField
- descripcion: TextField
- icono: CharField(100)
- imagen_url: URLField
- orden: IntegerField
- activo: BooleanField
- fecha_creacion: DateTimeField(auto_now_add)
- fecha_actualizacion: DateTimeField(auto_now)
```
**unique_together:** `['subcategoria', 'slug']`
**Relaciones:**
- `documentos` → DocumentoInfraestructura (one-to-many)

#### 29. **DocumentoInfraestructura** (Nivel 5)
```python
- id (PK)
- grupo_documento: ForeignKey(GrupoDocumento)
- nombre: CharField(255)
- slug: SlugField
- descripcion: TextField
- contenido: CKEditor5Field  # Contenido enriquecido HTML
- tipo_documento: CharField(20)
  # CHOICES: 'proceso', 'subproceso', 'procedimiento', 'herramienta',
  #          'metodologia', 'guia', 'manual', 'formato', 'otro'
- estado: CharField(20)
  # CHOICES: 'borrador', 'revision', 'aprobado', 'publicado', 'archivado'
- version: CharField(50)
- autor: CharField(255)
- fecha_creacion, fecha_actualizacion: DateTimeField
- fecha_publicacion: DateTimeField
- fecha_revision: DateField
- archivo_pdf, archivo_word: FileField
- icono: CharField(100)
- orden: IntegerField
- activo, destacado: BooleanField
- palabras_clave: CharField(500)
- resumen_ejecutivo: TextField
```
**unique_together:** `['grupo_documento', 'slug']`
**Métodos:**
- `get_absolute_url()` - Genera URL con 5 slugs en jerarquía

---

### Aliados y Eventos

#### 30. **Aliado**
```python
- id (PK)
- nombre: CharField(255)
- slug: SlugField(unique)
- logo_url: URLField
- descripcion: CKEditor5Field
- url_externa: URLField
- orden: IntegerField
- activo: BooleanField
- fecha_inicio_alianza, fecha_fin_alianza: DateField
- fecha_creacion, fecha_actualizacion: DateTimeField
```
**Métodos:**
- `get_absolute_url()`

#### 31. **Evento**
```python
- id (PK)
- nombre: CharField(255)
- slug: SlugField(unique)
- descripcion: CKEditor5Field
- lugar: CharField(255)
- fecha_inicio, fecha_fin: DateTimeField
- imagen_url: URLField
- url_externa: URLField
- activo, destacado: BooleanField
- fecha_creacion, fecha_actualizacion: DateTimeField
```
**Ordering:** `['fecha_inicio']`
**Propiedades computadas:**
- `duracion_horas` - Calcula duración en horas
- `es_evento_pasado` - Boolean si ya terminó
- `es_evento_actual` - Boolean si está ocurriendo ahora

---

### Búsqueda Semántica

#### 32. **DocumentoVector**
```python
- tipo: CharField(20)
  # CHOICES: 'indicador', 'tema', 'subtema', 'dominio'
- referencia_id: IntegerField
- contenido: TextField
- embedding: VectorField(dimensions=384)  # pgvector
- metadata: JSONField
- fecha_creacion, fecha_actualizacion: DateTimeField
- vector: JSONField  # Backup del embedding
```
**Índices:**
```python
- ['tipo']
- ['id', 'tipo']
- ['tipo', 'referencia_id']
```

---

## Diagrama de Relaciones Principal

```
MenuDominio (1)
    ↓ 1:N
MenuTema (1)
    ↓ 1:N
MenuSubtema (1)
    ↓ 1:N
Indicador (10) ←─────┐
    ↓ 1:N            │
Dato (11) ←──────────┤ M:N desagregaciones
    ↑                │
    └─── M:N ────────┴─→ Desagregacion (9)
                            ↑ N:1
                     DominioDesagregacion (8)
                            ↑ N:1
                     NivelGeografico (5)
                            ↓ 1:N
                         CapaGeo (6)
                            ↓ 1:N
                     ElementoGeo (7)

Indicador (10)
    ├─ 1:N → Grafico (16)
    │          ↓ 1:N
    │       GraficoSerie (17)
    │
    ├─ 1:1 → ReglaExtraccion (13)
    │
    ├─ 1:N → ProcesoExtraccion (14)
    │          ↓ 1:N
    │       ProcesoLog (15)
    │
    ├─ N:1 → Microdata (12)
    │
    └─ N:1 → OperacionEstadistica (4)
```

## Estadísticas del Modelo

- **Total de modelos:** 33
- **Relaciones ForeignKey:** 45+
- **Relaciones ManyToMany:** 8+
- **Relaciones OneToOne:** 1
- **Campos con índices:** 15+ índices personalizados
- **Campos JSONField:** 6 campos
- **Campos con choices:** 12+ campos
- **Campos CKEditor5:** 3 campos
- **Campos FileField:** 4 campos
- **unique_together:** 4 restricciones

## Observaciones Importantes

### ✅ Buenas Prácticas Encontradas
1. **Índices bien pensados** - Optimizados para queries comunes
2. **Normalización adecuada** - Pocas redundancias
3. **Uso de JSONField** - Para datos flexibles (filtros, metadatos)
4. **Soft deletes** - Campo `activo` en lugar de borrado físico
5. **Auditoría temporal** - Campos created_at/updated_at
6. **Restricciones de integridad** - unique_together, choices

### ⚠️ Áreas de Mejora
1. **Falta documentación inline** en algunos modelos
2. **Sin validadores personalizados** en campos críticos
3. **Podría beneficiarse de modelos abstractos** para reducir duplicación
4. **Falta soft delete en algunos modelos** críticos como Dato
5. **Sin versionado de datos** (auditoría de cambios)
