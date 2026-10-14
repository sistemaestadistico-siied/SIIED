from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django_ckeditor_5.fields import CKEditor5Field

import numpy as np
from sentence_transformers import SentenceTransformer
from django.db import transaction





class MenuDominio(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    descripcion = models.TextField(blank=True, null=True)
    icono = models.CharField(max_length=100, blank=True, null=True)
    color = models.CharField(max_length=100, blank=True, null=True)
    imagen_url = models.URLField(blank=True, null=True, help_text="URL de la imagen del dominio")
    orden = models.IntegerField(default=0)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Menú Dominio"
        verbose_name_plural = "Menús Dominio"


class MenuTema(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    descripcion = models.TextField(blank=True, null=True)
    imagen_url = models.URLField(blank=True, null=True, help_text="URL de la imagen del tema")
    icono = models.CharField(max_length=100, blank=True, null=True)
    orden = models.IntegerField(default=0)
    activo = models.BooleanField(default=True)
    dominio = models.ForeignKey(MenuDominio, on_delete=models.CASCADE, related_name='temas')

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Menú Tema"
        verbose_name_plural = "Menús Tema"


class MenuSubtema(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    descripcion = models.TextField(blank=True, null=True)
    icono = models.CharField(max_length=100, blank=True, null=True)
    imagen_url = models.URLField(blank=True, null=True, help_text="URL de la imagen del subtema")
    orden = models.IntegerField(default=0)
    activo = models.BooleanField(default=True)
    tema = models.ForeignKey(MenuTema, on_delete=models.CASCADE, related_name='subtemas')
    vista_django = models.CharField(max_length=255, blank=True, null=True)
    url = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        if self.url:
            return self.url
        if self.vista_django:
            try:
                from django.urls import reverse
                return reverse(self.vista_django)
            except Exception:
                pass
        return ''

    class Meta:
        verbose_name = "Menú Subtema"
        verbose_name_plural = "Menús Subtema"
        ordering = ['nombre']


class OperacionEstadistica(models.Model):
    id = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    tipo_operacion = models.CharField(max_length=100)
    periodicidad = models.CharField(max_length=50)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(blank=True, null=True)
    entidad_recopiladora = models.CharField(max_length=255)
    metodologia = models.TextField(blank=True, null=True)
    url = models.URLField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    # Campos adicionales provenientes del CSV OOEE
    c_organismo = models.CharField(max_length=100, blank=True, null=True)
    organismo = models.CharField(max_length=255, blank=True, null=True)
    suborganismo = models.CharField(max_length=255, blank=True, null=True)
    area_tem = models.CharField(max_length=255, blank=True, null=True)
    tema = models.CharField(max_length=255, blank=True, null=True)
    unidad_observ = models.CharField(max_length=255, blank=True, null=True)
    objetivo = models.TextField(blank=True, null=True)
    descripcion_proceso = models.TextField(blank=True, null=True)
    principales_resultados = models.TextField(blank=True, null=True)
    enfoque_diferencial = models.CharField(max_length=255, blank=True, null=True)
    desagregacion_resultados = models.TextField(blank=True, null=True)
    doc_met = models.CharField(max_length=255, blank=True, null=True)
    ficha_met = models.CharField(max_length=255, blank=True, null=True)
    manual_op = models.CharField(max_length=255, blank=True, null=True)
    diccionario_datos = models.CharField(max_length=255, blank=True, null=True)
    doc_cons_valid = models.CharField(max_length=255, blank=True, null=True)
    acciones_fortalecimiento = models.CharField(max_length=255, blank=True, null=True)
    sicode = models.CharField(max_length=100, blank=True, null=True)
    cod_cg = models.CharField(max_length=100, blank=True, null=True)
    estr_org = models.CharField(max_length=100, blank=True, null=True)
    tipo_oe_i = models.CharField(max_length=100, blank=True, null=True)
    num = models.CharField(max_length=50, blank=True, null=True)
    p_bp = models.CharField(max_length=50, blank=True, null=True)
    proyecto = models.CharField(max_length=255, blank=True, null=True)
    fun_org = models.CharField(max_length=255, blank=True, null=True)
    fun_sub = models.CharField(max_length=255, blank=True, null=True)
    mop = models.CharField(max_length=255, blank=True, null=True)
    pe = models.CharField(max_length=255, blank=True, null=True)
    adda_1 = models.CharField(max_length=255, blank=True, null=True)
    cant_amda = models.IntegerField(blank=True, null=True)
    link_adda = models.URLField(blank=True, null=True)
    link_pe = models.URLField(blank=True, null=True)
    amda_clas = models.CharField(max_length=100, blank=True, null=True)
    anio_adda = models.IntegerField(blank=True, null=True)
    anio_act_pe = models.IntegerField(blank=True, null=True)
    nombre_tematico = models.CharField(max_length=255, blank=True, null=True)
    correo_tematico = models.CharField(max_length=255, blank=True, null=True)
    celular_tematico = models.CharField(max_length=100, blank=True, null=True)
    nombre_coordinador = models.CharField(max_length=255, blank=True, null=True)
    correo_coordinador = models.CharField(max_length=255, blank=True, null=True)
    celular_coordinador = models.CharField(max_length=100, blank=True, null=True)
    grupo_productor = models.CharField(max_length=255, blank=True, null=True)
    pdd = models.CharField(max_length=255, blank=True, null=True)
    responsable_actualizacion = models.CharField(max_length=255, blank=True, null=True)
    estado_actualizacion = models.CharField(max_length=255, blank=True, null=True)
    pendiente = models.CharField(max_length=255, blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Operación Estadística"
        verbose_name_plural = "Operaciones Estadísticas"


class NivelGeografico(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Nivel Geográfico"
        verbose_name_plural = "Niveles Geográficos"


class CapaGeo(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    nivel_geografico = models.ForeignKey(NivelGeografico, on_delete=models.CASCADE, related_name='capas')

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Capa Geográfica"
        verbose_name_plural = "Capas Geográficas"


class ElementoGeo(models.Model):
    id = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=100)
    nombre = models.CharField(max_length=255)
    geom_wkt = models.TextField(blank=True, null=True)
    capa_geo = models.ForeignKey(CapaGeo, on_delete=models.CASCADE, related_name='elementos')

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    class Meta:
        verbose_name = "Elemento Geográfico"
        verbose_name_plural = "Elementos Geográficos"


class DominioDesagregacion(models.Model):
    TIPO_CHOICES = [
        ('tematica', 'Temática'),
        ('geografica', 'Geográfica'),
    ]
    
    TIPO_AGREGACION_TOTAL_CHOICES = [
        ('suma', 'Sumar desagregaciones (default)'),
        ('ninguno', 'No calcular - Extraer del CSV'),
    ]
    
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    nivel_geografico = models.ForeignKey(NivelGeografico, on_delete=models.CASCADE, 
                                       related_name='dominios_desagregacion', 
                                       blank=True, null=True)
    
    # Jerarquía entre dominios: permite marcar un dominio como subcategoría de otro
    # (ej: 'Barrio' como subdominio de 'Comuna', 'Estrato' como subdominio de 'Zona').
    dominio_padre = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        related_name='subdominios',
        blank=True, null=True,
        help_text="Dominio del cual este dominio es subcategoría. Si se define, el filtro de este dominio se despliega como subordinado al dominio padre."
    )

    # NUEVO: Cómo calcular el 'Total' cuando no está explícito en CSV
    tipo_agregacion_total = models.CharField(
        max_length=20,
        choices=TIPO_AGREGACION_TOTAL_CHOICES,
        default='suma',
        help_text=(
            "Estrategia para calcular 'Total':\n"
            "• SUMA: Calcula sumando todas las desagregaciones (población, conteos)\n"
            "• NINGUNO: No calcula, busca 'Total' directamente en el CSV (tasas, índices precalculados)"
        )
    )

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Dominio de Desagregación"
        verbose_name_plural = "Dominios de Desagregación"


class Desagregacion(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    codigo = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    dominio = models.ForeignKey(DominioDesagregacion, on_delete=models.CASCADE, related_name='desagregaciones')
    capa_geo = models.ForeignKey(CapaGeo, on_delete=models.CASCADE, 
                               related_name='desagregaciones', 
                               blank=True, null=True)
    
    # Jerarquía entre desagregaciones: vincula cada valor de un dominio hijo
    # con el valor del dominio padre al que pertenece (ej: barrio -> comuna).
    # Permite filtros en cascada en el frontend.
    desagregacion_padre = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        related_name='subdesagregaciones',
        blank=True, null=True,
        help_text="Desagregación del dominio padre a la que pertenece este valor (para filtros en cascada)."
    )

    # Campos para desagregaciones temáticas de rangos
    es_rango = models.BooleanField(default=False, 
                                  help_text="Indica si esta desagregación representa un rango de valores")
    valores_rango = models.JSONField(blank=True, null=True,
                                    help_text="Lista de valores que conforman este rango (ej: ['0', '1', '2', '3', '4'])")

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Desagregación"
        verbose_name_plural = "Desagregaciones"


def normalizar_ascii(texto):
    """Pliega tildes y diacríticos a ASCII vía NFKD (stdlib).

    Reemplazo local de 'unidecode': suficiente para texto en español
    y sin dependencia externa — unidecode no está instalada en el
    venv de producción.
    """
    import unicodedata
    return ''.join(
        c for c in unicodedata.normalize('NFKD', str(texto))
        if not unicodedata.combining(c))


def resolver_organismo_por_nombre(nombre):
    """Resuelve un Organismo activo a partir de un nombre de texto libre.

    Estrategia: coincidencia exacta (iexact) → normalizada (sin tildes,
    minúsculas) → contenido parcial. Devuelve None si no hay match.
    """
    texto = (nombre or '').strip()
    if not texto:
        return None
    qs = Organismo.objects.filter(activo=True)
    organismo = qs.filter(nombre__iexact=texto).first()
    norm = lambda s: normalizar_ascii(s).lower().strip()
    if not organismo:
        objetivo = norm(texto)
        for org in qs:
            if norm(org.nombre) == objetivo:
                organismo = org
                break
    if not organismo:
        organismo = qs.filter(nombre__icontains=texto[:60]).first()
    if not organismo:
        # Coincidencia inversa: el nombre del organismo aparece dentro
        # del texto (p. ej. "Secretaría de Educación Municipal de
        # Santiago de Cali" → "Secretaría de Educación Municipal").
        # Solo nombres de al menos 10 caracteres para evitar falsos
        # positivos (siglas cortas, "DANE", etc.).
        objetivo = norm(texto)
        mejor = None
        for org in qs:
            n = norm(org.nombre)
            if len(n) >= 10 and n in objetivo and (mejor is None or len(n) > len(norm(mejor.nombre))):
                mejor = org
        organismo = mejor
    return organismo


class Indicador(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255,
        verbose_name="0.1 Nombre del Indicador",
        help_text="Nombre del indicador (2.1 MSD)")
    codigo_indicador = models.CharField(max_length=100, blank=True, null=True,
                                       verbose_name="0.2 Código del Indicador",
                                       help_text="Código único del indicador (ej: ICET_SAL_DEM_MOR_02)")
    sigla = models.CharField(max_length=50, blank=True, null=True,
                            verbose_name="0.3 Sigla",
                            help_text="Sigla o acrónimo del indicador (ej: TMM5)")
    grupo_indicador = models.CharField(max_length=50, blank=True, null=True,
                                      verbose_name="0.4 Grupo Indicador",
                                      help_text="Grupo al que pertenece (ICET/SIIET)")
    
    # Campos descriptivos y conceptuales (MSD)
    objetivo = CKEditor5Field(blank=True, null=True,
                             verbose_name="2.3 Objetivo",
                             help_text="Objetivo del indicador (2.3 MSD)")

    # Metodología y cálculo
    metodo_medicion = CKEditor5Field(blank=True, null=True,
                                    verbose_name="2.4 Cálculo del Indicador / Método de Medición",
                                    help_text="Descripción del método de medición y cálculo (2.4 MSD)")
    formula_ficha = models.TextField(blank=True, null=True,
                                    verbose_name="2.5 Fórmula",
                                    help_text="Fórmula matemática del indicador para la ficha técnica")
    variables = CKEditor5Field(blank=True, null=True,
                              verbose_name="2.6 Variables",
                              help_text="Descripción de las variables utilizadas en la fórmula")

    # Unidades y fuente
    unidad_medida = models.CharField(max_length=100, blank=True, null=True,
        verbose_name="2.7 Unidad de Medida",
        help_text="Unidad de medida del indicador (2.7 MSD)")
    fuente_datos = models.CharField(max_length=255, blank=True, null=True,
        verbose_name="2.8 Fuente de la Información",
        help_text="Fuente de datos del indicador (2.8 MSD)")
    notas = models.TextField(blank=True, null=True,
                            verbose_name="Notas internas",
                            help_text="Notas de uso interno (no se muestran en ficha técnica)")

    # ============================================================================
    # ESTÁNDAR MSD — Metadatos de Series de Datos (DANE)
    # ============================================================================

    # Sección 1: Contacto Institucional
    entidad_responsable_legado = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="1.1 Entidad Responsable (texto legado)",
        help_text="Texto libre heredado. El campo oficial es la llave "
                  "'organismo_responsable'. Este texto se conserva solo "
                  "como referencia cuando no pudo resolverse a un Organismo."
    )
    suborganismo = models.ForeignKey(
        'Suborganismo',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='indicadores',
        verbose_name="1.3 Área o Dependencia Responsable",
        help_text="Área o dependencia dentro de la entidad (1.3 MSD)"
    )
    correo_contacto = models.EmailField(
        blank=True, null=True,
        verbose_name="1.4 Correo Electrónico de Contacto",
        help_text="Dirección de correo de la entidad (1.4 MSD)"
    )
    telefono_contacto = models.CharField(
        max_length=50, blank=True, null=True,
        verbose_name="1.5 Número Telefónico",
        help_text="Teléfono de atención al ciudadano (1.5 MSD)"
    )
    fecha_publicacion_metadatos = models.DateField(
        blank=True, null=True,
        verbose_name="1.6 Fecha de Publicación de los Metadatos",
        help_text="Fecha más reciente de difusión de los metadatos de referencia MSD (1.6 MSD)"
    )
    # Trazabilidad del Excel de metadatos (no son campos MSD numerados:
    # el jefe los incluyó en la hoja de referencia como campos técnicos)
    fecha_elaboracion = models.DateField(
        blank=True, null=True,
        verbose_name="Fecha de elaboración de la ficha",
        help_text="Fecha en que se diligenció por primera vez la ficha técnica "
                  "(columna Fecha_Elaboracion de la plantilla Excel)"
    )
    fecha_actualizacion_ficha = models.DateField(
        blank=True, null=True,
        verbose_name="Fecha de última actualización de la ficha",
        help_text="Fecha de la última actualización manual de la ficha técnica "
                  "(columna Fecha_Actualizacion de la plantilla Excel). "
                  "Se llama fecha_actualizacion_ficha para no colisionar con "
                  "los auto_now de otros modelos."
    )

    # Sección 2: Características del Indicador (campos nuevos / reemplazos MSD)
    descripcion_indicador = CKEditor5Field(
        blank=True, null=True,
        verbose_name="2.2 Descripción del Indicador",
        help_text="Descripción general del indicador (2.2 MSD). Reemplaza 'Definiciones y conceptos' en la ficha."
    )
    nomenclaturas_clasificaciones = models.TextField(
        blank=True, null=True,
        verbose_name="2.11 Nomenclaturas y Clasificaciones",
        help_text="Clasificaciones o nomenclaturas utilizadas para la producción del indicador (2.11 MSD)"
    )
    poblacion_objetivo = CKEditor5Field(
        blank=True, null=True,
        verbose_name="2.13 Población Objetivo",
        help_text="Población objetivo del conjunto de datos (2.13 MSD)"
    )
    alcance_tematico = models.TextField(
        blank=True, null=True,
        verbose_name="2.12 Alcance Temático",
        help_text="Sectores o temas cubiertos por el conjunto de datos estadísticos (2.12 MSD). "
                  "Reemplaza 'Desagregación temática (texto)' en la ficha."
    )
    cobertura_geografica = models.TextField(
        blank=True, null=True,
        verbose_name="2.14 Cobertura Geográfica",
        help_text="Extensión territorial del indicador (2.14 MSD). "
                  "Reemplaza 'Desagregación geográfica (texto)' en la ficha."
    )
    periodo_referencia = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="2.15 Período de Referencia",
        help_text="Período de tiempo al que se refiere la observación medida (2.15 MSD)"
    )
    periodo_base = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="2.16 Período Base",
        help_text="Período base de un índice o serie constante (2.16 MSD)"
    )

    # Sección 3: Difusión
    serie_historica_disponible = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="3.1 Serie Histórica Disponible",
        help_text="Períodos de tiempo en que el indicador se encuentra disponible (3.1 MSD)"
    )
    frecuencia_difusion = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="3.2 Frecuencia de Difusión",
        help_text="Frecuencia con la que se difunden los datos (mensual, trimestral, anual...) (3.2 MSD)"
    )
    medios_difusion = CKEditor5Field(
        blank=True, null=True,
        verbose_name="3.3 Medios de Difusión",
        help_text="Medios de difusión (internet, impreso, etc.) (3.3 MSD)"
    )

    # Sección 4: Comentarios adicionales
    comentarios_adicionales = CKEditor5Field(
        blank=True, null=True,
        verbose_name="4.1 Comentarios Adicionales",
        help_text="Información adicional relacionada con los datos o metadatos (4 MSD). "
                  "Reemplaza 'Observaciones' en la ficha."
    )

    # Sección 5: Referencias (SDMX)
    referencias = CKEditor5Field(
        blank=True, null=True,
        verbose_name="5.1 Referencias (APA 7)",
        help_text="Fuentes bibliográficas, normativas y metodológicas del indicador "
                  "en normas APA 7.ª edición, con enlaces oficiales o DOI (SDMX)"
    )

    # Sección 6: Responsabilidad institucional (SDMX)
    equipo_responsable = models.ForeignKey(
        'EquipoOrganismo',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='indicadores_responsables',
        verbose_name="6.3 Equipo Responsable",
        help_text="Equipo del suborganismo encargado de producir o recolectar "
                  "la información del indicador (SDMX)"
    )
    nombre_responsable_validacion = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="Nombre del responsable técnico de validación",
        help_text="Persona responsable técnica de producir o recolectar "
                  "la información del indicador (SDMX)"
    )
    cargo_responsable_validacion = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="Cargo del responsable técnico de validación",
        help_text="Cargo de la persona responsable técnica del indicador (SDMX)"
    )
    correo_responsable_validacion = models.EmailField(
        blank=True, null=True,
        verbose_name="Correo del responsable técnico de validación",
        help_text="Correo electrónico de la persona responsable técnica del indicador (SDMX)"
    )
    celular_responsable_validacion = models.CharField(
        max_length=50, blank=True, null=True,
        verbose_name="Celular del responsable técnico de validación",
        help_text="Celular de la persona responsable técnica del indicador (SDMX)"
    )

    # Campo interno: nombre del conjunto de datos asociado.
    # No se muestra en la ficha técnica pública. Si existe, se usa como nombre
    # del ConjuntoDatos al crear/actualizar desde variables; si ya existe un
    # ConjuntoDatos con ese nombre, se reutiliza en lugar de crear uno nuevo.
    nombre_conjunto_datos = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="2.10 Nombre del Conjunto de Datos",
        help_text="Nombre del conjunto de datos al que pertenecen las variables. "
                  "Si coincide con un conjunto de datos existente, se asocia automáticamente. "
                  "No aparece en la ficha técnica pública."
    )

    # Relaciones
    subtema = models.ForeignKey(MenuSubtema, on_delete=models.CASCADE, related_name='indicadores')
    operacion = models.ForeignKey(OperacionEstadistica, on_delete=models.CASCADE,
                                related_name='indicadores', blank=True, null=True,
                                verbose_name="2.9 Nombre de la Operación Estadística")
    # Organismo responsable — llave oficial a la tabla Organismo
    # (metadato MSD 1.1 "Entidad o Institución Responsable" / 6.1)
    organismo_responsable = models.ForeignKey(
        'Organismo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='indicadores_responsables',
        verbose_name="1.1 Entidad u Organismo Responsable",
        help_text="Organismo productor del indicador. Llave a la tabla "
                  "Organismo (usado también para el portal de delegados). "
                  "Los textos antiguos quedaron en 'entidad_responsable_legado'."
    )

    @property
    def entidad_responsable(self):
        """MSD 1.1: nombre de la entidad responsable. Lee del FK
        organismo_responsable; cae al texto legado si no hay llave."""
        if self.organismo_responsable_id:
            return self.organismo_responsable.nombre
        return self.entidad_responsable_legado or ''

    @entidad_responsable.setter
    def entidad_responsable(self, value):
        """Asignar texto resuelve el Organismo por nombre (exacto /
        normalizado / contenido). Si no se resuelve, queda como texto legado."""
        nombre = (value or '').strip()
        if not nombre:
            return
        organismo = resolver_organismo_por_nombre(nombre)
        if organismo:
            self.organismo_responsable = organismo
        else:
            self.entidad_responsable_legado = nombre
    activo = models.BooleanField(default=True)
    # Dominios de desagregación temática asociados al indicador (muchos a muchos)
    dominios_desagregacion_tematica = models.ManyToManyField(
        'DominioDesagregacion', 
        blank=True, 
        related_name='indicadores_con_dominios_tematicos',
        limit_choices_to={'tipo': 'tematica'}
    )
    # Dominios de desagregación geográfica asociados al indicador (muchos a muchos)
    dominios_desagregacion_geografica = models.ManyToManyField(
        'DominioDesagregacion', 
        blank=True, 
        related_name='indicadores_con_dominios_geograficos',
        limit_choices_to={'tipo': 'geografica'}
    )
    # Conjunto de datos base del indicador
    # Relación uno a muchos con ConjuntoDatos
    conjunto_datos = models.ForeignKey('ConjuntoDatos', on_delete=models.CASCADE, 
                                       related_name='indicadores', blank=True, null=True)
    # Enlace al catálogo de consulta: si está definido, el indicador no
    # consulta sus Datos: renderiza el cuadro de consulta del conjunto enlazado.
    # Se conserva toda la metadata y la posición en la taxonomía (CEC).
    catalogo_consulta = models.ForeignKey(
        'CatalogoConsulta', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='indicadores_enlazados',
        verbose_name="Conjunto del catálogo de consulta",
        help_text="Si está enlazado, el indicador muestra el cuadro de consulta "
                  "de este conjunto en lugar de sus datos estadísticos"
    )
    # Campo para controlar si se muestra el botón de mapa
    mostrar_mapa = models.BooleanField(default=True, 
                                     help_text="Indica si se debe mostrar el botón de mapa para este indicador")
    # Campo para ordenar los indicadores
    orden = models.IntegerField(default=0, help_text="Orden de visualización del indicador")

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Indicador"
        verbose_name_plural = "Indicadores"
        indexes = [
            # Listado de indicadores por subtema (subtema_detalle.html)
            models.Index(
                fields=['subtema', 'orden', 'nombre'],
                name='indicador_subtema_orden_idx'
            ),
            # Búsquedas por nombre en admin
            models.Index(
                fields=['nombre'],
                name='indicador_nombre_idx'
            ),
            # Filtros por estado activo
            models.Index(
                fields=['activo', 'subtema'],
                name='indicador_activo_subtema_idx'
            ),
        ]


class Dato(models.Model):
    id = models.AutoField(primary_key=True)
    indicador = models.ForeignKey(Indicador, on_delete=models.CASCADE, related_name='datos')
    fecha_dato = models.DateField()
    valor_dato = models.DecimalField(max_digits=20, decimal_places=6)
    desagregaciones_geograficas = models.ManyToManyField(
        'Desagregacion',
        blank=True,
        limit_choices_to={'dominio__tipo': 'geografica'},
        related_name='datos_geograficos'
    )
    desagregaciones_tematicas = models.ManyToManyField(
        'Desagregacion',
        blank=True,
        limit_choices_to={'dominio__tipo': 'tematica'},
        related_name='datos_tematicos'
    )

    def __str__(self):
        return f"{self.indicador.nombre} - {self.fecha_dato}: {self.valor_dato}"

    def save(self, *args, **kwargs):
        # La columna real en BD es numeric ilimitado (sin escala), así que un
        # float entraría con artefactos binarios (52.299999999999997158) que el
        # admin rechaza por exceder decimal_places=6. Normalizar: float ->
        # Decimal vía str (repr exacta), redondear a 6 decimales y quitar
        # ceros de relleno. format(...,'f') evita notación científica.
        v = self.valor_dato
        if v is not None:
            try:
                d = Decimal(str(v))
            except Exception:
                d = None
            if d is not None and d.is_finite():
                if d.as_tuple().exponent < -6:
                    d = d.quantize(Decimal('1e-6'))
                self.valor_dato = Decimal(format(d.normalize(), 'f'))
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Dato"
        verbose_name_plural = "Datos"
        indexes = [
            # Consultas por indicador específico (más común en subtema_detalle)
            models.Index(
                fields=['indicador', '-fecha_dato'],
                name='dato_indicador_fecha_idx'
            ),
            # Filtros por rango de fechas
            models.Index(
                fields=['fecha_dato'],
                name='dato_fecha_idx'
            ),
            # Consultas del visor comparativo (múltiples indicadores)
            models.Index(
                fields=['indicador', 'fecha_dato', 'valor_dato'],
                name='dato_comparativo_idx'
            ),
        ]


class ConjuntoDatos(models.Model):
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    archivo_csv = models.FileField(upload_to='microdata/')
    fecha_carga = models.DateTimeField(auto_now_add=True)
    operacion = models.ForeignKey(OperacionEstadistica, on_delete=models.CASCADE,
                                related_name='conjuntos_datos', blank=True, null=True)

    # ── ESTÁNDAR DDI — Identificación ──
    identificador = models.CharField(max_length=100, blank=True, null=True,
        help_text="DDI IDNo — Identificador único del conjunto (ej. agencia:código estudio)")
    version = models.CharField(max_length=50, blank=True, null=True,
        help_text="DDI version — Versión del conjunto de datos")
    doi_citacion = models.TextField(blank=True, null=True,
        help_text="DDI citation — Cita bibliográfica recomendada o DOI")
    idioma = models.CharField(max_length=50, blank=True, null=True, default='es',
        help_text="DDI — Idioma del conjunto (código ISO 639)")
    palabras_clave = models.CharField(max_length=500, blank=True, null=True,
        help_text="DDI keyword — Palabras clave separadas por comas")

    # ── ESTÁNDAR DDI — Producción y difusión ──
    organismo_productor = models.ForeignKey(
        'Organismo', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='conjuntos_producidos',
        verbose_name="Organismo productor",
        help_text="DDI producer — Llave a la tabla Organismo")
    productor_legado = models.CharField(max_length=255, blank=True, null=True,
                                        help_text="DDI producer — texto libre heredado "
                                                  "(entidad externa no registrada como Organismo)")
    financiamiento = models.CharField(max_length=255, blank=True, null=True,
        help_text="DDI fundAg — Agencia o fuente de financiamiento")
    distribuidor = models.CharField(max_length=255, blank=True, null=True,
        help_text="DDI distributor — Entidad distribuidora")
    contacto_nombre = models.CharField(max_length=255, blank=True, null=True,
        help_text="DDI contact — Persona/área de contacto")
    contacto_email = models.EmailField(blank=True, null=True,
        help_text="DDI contact — Correo de contacto")

    # ── ESTÁNDAR DDI — Cobertura ──
    universo = models.TextField(blank=True, null=True,
        help_text="DDI universe — Universo o población cubierta por los datos")
    unidad_analisis = models.CharField(max_length=255, blank=True, null=True,
        help_text="DDI analysisUnit — Unidad de análisis (ej. personas, hogares, empresas)")
    cobertura_geografica = models.CharField(max_length=255, blank=True, null=True,
        help_text="DDI geogCover — Cobertura geográfica del conjunto")
    cobertura_temporal = models.CharField(max_length=255, blank=True, null=True,
        help_text="DDI timePrd — Periodo temporal de referencia (ej. 2015–2024)")

    # ── ESTÁNDAR DDI — Metodología ──
    tipo_estudio = models.CharField(max_length=100, blank=True, null=True,
        help_text="DDI serinfo/stdyClas — Tipo de estudio (encuesta, censo, registro administrativo, agregado)")
    metodo_muestreo = models.CharField(max_length=255, blank=True, null=True,
        help_text="DDI sampMeth — Método de muestreo")
    modo_coleccion = models.CharField(max_length=255, blank=True, null=True,
        help_text="DDI collMode — Modo de recolección (entrevista presencial, web, extracción administrativa)")
    instrumento = models.CharField(max_length=255, blank=True, null=True,
        help_text="DDI instrument — Instrumento de recolección (cuestionario, formulario)")
    periodo_campo_inicio = models.DateField(blank=True, null=True,
        help_text="DDI collDate — Inicio del trabajo de campo / extracción")
    periodo_campo_fin = models.DateField(blank=True, null=True,
        help_text="DDI collDate — Fin del trabajo de campo / extracción")
    ponderacion = models.TextField(blank=True, null=True,
        help_text="DDI weight — Metodología de ponderación o factores de expansión")
    notas_procesamiento = models.TextField(blank=True, null=True,
        help_text="DDI cleanOps/notes — Operaciones de procesamiento, limpieza e imputación")

    # ── ESTÁNDAR DDI — Acceso y derechos ──
    condiciones_acceso = models.TextField(blank=True, null=True,
        help_text="DDI useStmt/conditions — Condiciones de acceso y uso")
    derechos_uso = models.TextField(blank=True, null=True,
        help_text="DDI copyright/restrctn — Licencia y derechos de uso")
    confidencialidad = models.TextField(blank=True, null=True,
        help_text="DDI confidentiality — Declaración de anonimización/protección de datos")

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Conjunto de Datos"
        verbose_name_plural = "Conjuntos de Datos"


class VariableConjuntoDatos(models.Model):
    """
    Modelo para almacenar la ficha técnica de cada variable de un conjunto de datos.
    Las variables pertenecen al conjunto de datos, no al indicador.
    Múltiples indicadores pueden usar las mismas variables de un conjunto de datos.
    """
    id = models.AutoField(primary_key=True)
    conjunto_datos = models.ForeignKey('ConjuntoDatos', on_delete=models.CASCADE, related_name='variables', blank=True, null=True)
    codigo_variable = models.CharField(max_length=50, help_text="Código de la variable (ej: V1, V2)")
    nombre_variable = models.CharField(max_length=255, help_text="Nombre descriptivo de la variable")
    definicion_conceptual = models.TextField(help_text="Definición conceptual de la variable")
    poblacion_objetivo = models.CharField(max_length=255, blank=True, null=True)
    cobertura_geografica = models.CharField(max_length=100, blank=True, null=True)
    desagregacion_geografica = models.CharField(max_length=255, blank=True, null=True)
    desagregacion_tematica = models.CharField(max_length=255, blank=True, null=True)
    tipo_dato = models.CharField(max_length=100, blank=True, null=True)
    dominio_dato = models.CharField(max_length=255, blank=True, null=True)
    unidad_medida = models.CharField(max_length=100, blank=True, null=True)
    tipo_variable_estadistica = models.CharField(max_length=100, blank=True, null=True)
    fuente_datos = models.CharField(max_length=255, blank=True, null=True)
    periodicidad = models.CharField(max_length=100, blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)
    referencias = models.TextField(blank=True, null=True,
        help_text="Referencias bibliográficas, normativas y metodológicas de la variable (APA 7 — SDMX)")
    organismo_productor = models.ForeignKey(
        'Organismo', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='variables_producidas',
        verbose_name="Organismo productor",
        help_text="Llave a la tabla Organismo")
    organismo_productor_legado = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Texto libre heredado cuando no se resolvió a un Organismo")
    orden = models.IntegerField(default=0, help_text="Orden de presentación de la variable")

    # ── ESTÁNDAR DDI — Campos a nivel variable ──
    pregunta = models.TextField(blank=True, null=True,
        help_text="DDI qstn — Pregunta literal del instrumento que origina la variable")
    universo = models.TextField(blank=True, null=True,
        help_text="DDI universe — Universo al que aplica esta variable (si difiere del conjunto)")
    concepto = models.CharField(max_length=255, blank=True, null=True,
        help_text="DDI concept — Concepto estándar asociado (ej. vocabulario controlado)")
    tipo_representacion = models.CharField(max_length=50, blank=True, null=True,
        help_text="DDI reprType — Tipo de representación: texto, código, numérico, fecha, etc.")
    categoria_estadistica = models.CharField(max_length=100, blank=True, null=True,
        help_text="DDI catStat — Clasificación estadística de la variable")

    def __str__(self):
        return f"{self.codigo_variable} - {self.nombre_variable}"
    
    class Meta:
        verbose_name = "Variable de Conjunto de Datos"
        verbose_name_plural = "Variables de Conjuntos de Datos"
        ordering = ['conjunto_datos', 'orden', 'codigo_variable']
        unique_together = ['conjunto_datos', 'codigo_variable']


class ReglaExtraccion(models.Model):
    id = models.AutoField(primary_key=True)
    indicador = models.OneToOneField('Indicador', on_delete=models.CASCADE, related_name='regla_extraccion')
    # Definición de columnas a usar para el cálculo
    columnas_fuente = models.JSONField(
        help_text="Lista de columnas del CSV que se usarán para el cálculo, en formato JSON. Ejemplo: ['Hombres_0', 'Hombres_1', 'Mujeres_0', 'Mujeres_1']"
    )
    # Columna de fecha/año en el CSV
    columna_fecha = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Nombre de la columna que contiene la fecha o año en el archivo CSV. Si se deja vacío, se intentará detectar automáticamente."
    )
    # Fórmula de cálculo
    formula = models.TextField(
        help_text="Fórmula para calcular el valor final. Puede incluir nombres de columnas y operaciones matemáticas. Ejemplo: 'valor_celda * 100' o 'Hombres_0 + Mujeres_0'",
        blank=True,
        null=True
    )
    # Filtros para aplicar durante el procesamiento
    filtros = models.JSONField(
        help_text="Filtros para aplicar durante el procesamiento, en formato JSON. Ejemplo: {'Ciudad': 'Santiago de Cali'}",
        blank=True,
        null=True
    )
    
    # Dominios de desagregación asociados al indicador
    orden_desagregaciones = models.JSONField(
        help_text="Mapeo del orden de búsqueda de desagregaciones temáticas en las columnas del CSV. Ejemplo: {'sexo': 1, 'edad': 2}",
        blank=True, 
        null=True
    )

    ultima_ejecucion = models.DateTimeField(blank=True, null=True, verbose_name="Última Ejecución")
    estado_procesamiento = models.CharField(
        max_length=20,
        choices=[
            ('pendiente', 'Pendiente'),
            ('procesando', 'Procesando'),
            ('completado', 'Completado'),
            ('error', 'Error')
        ],
        default='pendiente',
        verbose_name="Estado de Procesamiento"
    )
    activo = models.BooleanField(default=True, verbose_name="Activo", help_text="Si está desactivado, no se procesará automáticamente")
    
    @property
    def desagregaciones_asociadas(self):
        """Obtiene todas las desagregaciones asociadas a través de los dominios del indicador"""
        from .models import Desagregacion
        # Infiero las desagregaciones de los dominios asociados al indicador
        doms_t = self.indicador.dominios_desagregacion_tematica.all()
        doms_g = self.indicador.dominios_desagregacion_geografica.all()
        return Desagregacion.objects.filter(
            dominio__in=list(doms_t) + list(doms_g)
        ).distinct()
    
    def __str__(self):
        return f"Regla para {self.indicador.nombre}"

    class Meta:
        verbose_name = "Regla de Extracción"
        verbose_name_plural = "Reglas de Extracción"


class Grafico(models.Model):
    TIPO_GRAFICO_CHOICES = [
        ('line', 'Línea'),
        ('bar', 'Barras'),
        ('bar_horizontal', 'Barras Horizontales'),
        ('area', 'Área'),
        ('barras_apiladas', 'Barras Apiladas'),
        ('areas_apiladas', 'Áreas Apiladas'),
        ('pie', 'Circular'),
        ('piramide_poblacional', 'Pirámide Poblacional'),
        ('treemap', 'Treemap'),
        ('sin_grafico', 'Sin gráfico (solo tabla de datos)'),
        ('tabla_dinamica', 'Tabla dinámica (pivotada)'),
    ]

    POSICION_LEYENDA_CHOICES = [
        ('top', 'Arriba'),
        ('bottom', 'Abajo'),
        ('left', 'Izquierda'),
        ('right', 'Derecha'),
    ]
    
    id = models.AutoField(primary_key=True)
    indicador = models.ForeignKey(Indicador, on_delete=models.CASCADE, related_name='graficos')
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    tipo_grafico = models.CharField(max_length=20, choices=TIPO_GRAFICO_CHOICES, default='line')
    activo = models.BooleanField(default=True)
    titulo = models.CharField(max_length=255, blank=True, null=True)
    subtitulo = models.CharField(max_length=255, blank=True, null=True)
    eje_x_titulo = models.CharField(max_length=255, blank=True, null=True)
    eje_y_titulo = models.CharField(max_length=255, blank=True, null=True)
    mostrar_eje_y2 = models.BooleanField(default=False)
    eje_y2_titulo = models.CharField(max_length=255, blank=True, null=True)
    mostrar_leyenda = models.BooleanField(default=True)
    posicion_leyenda = models.CharField(max_length=10, choices=POSICION_LEYENDA_CHOICES, default='right')
    mostrar_cuadricula = models.BooleanField(default=True)
    mostrar_valores = models.BooleanField(default=False)
    mostrar_linea_tendencia = models.BooleanField(default=False)
    ancho_completo = models.BooleanField(default=False)
    altura_grafico = models.IntegerField(default=400, validators=[MinValueValidator(200), MaxValueValidator(1000)])
    margen_derecho = models.IntegerField(default=50, validators=[MinValueValidator(0), MaxValueValidator(200)])
    margen_inferior = models.IntegerField(default=50, validators=[MinValueValidator(0), MaxValueValidator(200)])
    orden = models.IntegerField(default=0)
    begin_at_zero = models.BooleanField(default=True, help_text="Indica si el eje Y del gráfico debe comenzar en cero")
    rango_personalizado_min = models.FloatField(blank=True, null=True, help_text="Valor mínimo personalizado para el eje Y. Si se especifica, se usará en lugar del cálculo automático.")
    rango_personalizado_max = models.FloatField(blank=True, null=True, help_text="Valor máximo personalizado para el eje Y. Si se especifica, se usará en lugar del cálculo automático.")
    mostrar_todas_etiquetas_x = models.BooleanField(default=True, help_text="Indica si se deben mostrar todas las etiquetas en el eje X. Si es False, se mostrarán solo algunas etiquetas para evitar congestionamiento.")
    
    # Campos para rango predeterminado de años
    rango_anios_min = models.IntegerField(blank=True, null=True, help_text="Valor mínimo predeterminado para el rango de años. Si se especifica, se usará como valor inicial en el control deslizante.")
    rango_anios_max = models.IntegerField(blank=True, null=True, help_text="Valor máximo predeterminado para el rango de años. Si se especifica, se usará como valor final en el control deslizante.")
    
    # Campos para desagregaciones predeterminadas
    desagregaciones_geograficas_predeterminadas = models.ManyToManyField(
        'Desagregacion', related_name='graficos_geograficos_predeterminados', blank=True
    )
    desagregaciones_tematicas_predeterminadas = models.ManyToManyField(
        'Desagregacion', related_name='graficos_tematicos_predeterminados', blank=True
    )
    
    def get_desagregaciones_geograficas_disponibles(self):
        """
        Obtiene todas las desagregaciones geográficas disponibles para este gráfico
        basadas en los dominios asociados al indicador
        """
        return Desagregacion.objects.filter(
            dominio__in=self.indicador.dominios_desagregacion_geografica.all()
        ).distinct()
    
    def get_desagregaciones_tematicas_disponibles(self):
        """
        Obtiene todas las desagregaciones temáticas disponibles para este gráfico
        basadas en los dominios asociados al indicador
        """
        return Desagregacion.objects.filter(
            dominio__in=self.indicador.dominios_desagregacion_tematica.all()
        ).distinct()

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Gráfico"
        verbose_name_plural = "Gráficos"

 

class GraficoSerie(models.Model):
    id = models.AutoField(primary_key=True)
    grafico = models.ForeignKey(Grafico, on_delete=models.CASCADE, related_name='series')
    # Filtros de la serie: una desagregación por dominio (ej. Comuna=3, Sexo=Mujer).
    # Campo principal desde que existen múltiples dominios por tipo.
    desagregaciones = models.ManyToManyField(
        Desagregacion, related_name='series', blank=True,
        help_text="Filtros de la serie: máximo una desagregación por dominio."
    )
    # LEGACY: se mantienen sincronizadas (primera desag. de cada tipo) para
    # compatibilidad con consumidores antiguos (configs JSON, mapas, etc.).
    desagregacion_geografica = models.ForeignKey(Desagregacion, on_delete=models.CASCADE,
                                               related_name='series_geograficas',
                                               blank=True, null=True)
    desagregacion_tematica = models.ForeignKey(Desagregacion, on_delete=models.CASCADE,
                                             related_name='series_tematicas',
                                             blank=True, null=True)
    nombre_personalizado = models.CharField(max_length=255, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    orden = models.IntegerField(default=0)

    def get_desagregaciones(self):
        """
        Devuelve la lista de desagregaciones que filtran esta serie.
        Prioriza el M2M `desagregaciones`; si está vacío, usa los FKs legacy.
        """
        if self.pk:
            m2m = list(self.desagregaciones.select_related('dominio').all())
            if m2m:
                return m2m
        legacy = [d for d in (self.desagregacion_geografica, self.desagregacion_tematica) if d]
        return legacy

    def sincronizar_fks_legacy(self, desags=None):
        """
        Sincroniza los FKs legacy con el M2M: primera desagregación geográfica
        y primera temática de la lista. Guarda solo los dos campos FK.
        """
        if desags is None:
            desags = list(self.desagregaciones.select_related('dominio').all()) if self.pk else []
        geo = next((d for d in desags if d.dominio and d.dominio.tipo == 'geografica'), None)
        tem = next((d for d in desags if d.dominio and d.dominio.tipo == 'tematica'), None)
        self.desagregacion_geografica = geo
        self.desagregacion_tematica = tem
        if self.pk:
            self.save(update_fields=['desagregacion_geografica', 'desagregacion_tematica'])

    def __str__(self):
        return f"{self.grafico.nombre} - Serie {self.orden}"

    class Meta:
        verbose_name = "Serie de Gráfico"
        verbose_name_plural = "Series de Gráficos"




class ProcesoExtraccion(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('procesando', 'Procesando'),
        ('completado', 'Completado'),
        ('error', 'Error'),
    ]

    id = models.AutoField(primary_key=True)
    indicador = models.ForeignKey('Indicador', on_delete=models.CASCADE, related_name='procesos_extraccion')
    regla = models.ForeignKey('ReglaExtraccion', on_delete=models.SET_NULL, null=True, blank=True, related_name='procesos')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    exit_code = models.IntegerField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Proceso {self.id} - {self.indicador.nombre} ({self.estado})"

    class Meta:
        verbose_name = "Proceso de Extracción"
        verbose_name_plural = "Procesos de Extracción"
        indexes = [
            # Monitoreo de procesos recientes
            models.Index(
                fields=['-created_at', 'estado'],
                name='proceso_fecha_estado_idx'
            ),
            # Procesos por indicador
            models.Index(
                fields=['indicador', '-created_at'],
                name='proceso_indicador_fecha_idx'
            ),
        ]


class ProcesoLog(models.Model):
    NIVEL_CHOICES = [
        ('INFO', 'INFO'),
        ('ERROR', 'ERROR'),
        ('WARN', 'WARN'),
        ('DEBUG', 'DEBUG'),
    ]

    id = models.AutoField(primary_key=True)
    proceso = models.ForeignKey('ProcesoExtraccion', on_delete=models.CASCADE, related_name='logs')
    nivel = models.CharField(max_length=10, choices=NIVEL_CHOICES, default='INFO')
    mensaje = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.nivel}] Proceso {self.proceso_id} - {self.mensaje[:50]}"

    class Meta:
        verbose_name = "Log de Proceso"
        verbose_name_plural = "Logs de Proceso"
        indexes = [
            # Logs por proceso (visor en tiempo real)
            models.Index(
                fields=['proceso', '-creado_en'],
                name='log_proceso_fecha_idx'
            ),
            # Filtros por nivel de error
            models.Index(
                fields=['nivel', '-creado_en'],
                name='log_nivel_fecha_idx'
            ),
        ]
        ordering = ['id']


class NoticiaBanner(models.Model):
    id = models.AutoField(primary_key=True)
    titulo = models.CharField(max_length=255, help_text="Título principal de la noticia")
    subtitulo = models.CharField(max_length=255, blank=True, null=True, help_text="Subtítulo o descripción corta")
    descripcion = models.TextField(help_text="Descripción detallada de la noticia")
    enlace_principal = models.URLField(blank=True, null=True, help_text="URL del enlace principal")
    texto_enlace_principal = models.CharField(max_length=100, default="Leer más", help_text="Texto del botón principal")
    imagen_url = models.URLField(blank=True, null=True, help_text="URL de la imagen de la noticia")
    activa = models.BooleanField(default=True, help_text="Si la noticia está activa para mostrar")
    fecha_publicacion = models.DateTimeField(
        default=timezone.now,
        help_text="Fecha de publicación. Editable para archivar noticias históricas con su fecha original"
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    orden = models.IntegerField(default=0, help_text="Orden de prioridad (mayor número = mayor prioridad)")
    evento_origen = models.OneToOneField(
        'indicadores.Evento', on_delete=models.SET_NULL,
        blank=True, null=True, related_name='noticia_archivada',
        help_text="Evento del calendario archivado como noticia (archivo histórico)"
    )

    def __str__(self):
        return self.titulo

    class Meta:
        verbose_name = "Noticia Banner"
        verbose_name_plural = "Noticias Banner"
        ordering = ['-orden', '-fecha_publicacion']


class EstadisticaNoticia(models.Model):
    noticia = models.ForeignKey(NoticiaBanner, on_delete=models.CASCADE, related_name='estadisticas')
    titulo = models.CharField(max_length=100, help_text="Título de la estadística")
    valor = models.CharField(max_length=50, help_text="Valor de la estadística")
    descripcion = models.CharField(max_length=255, blank=True, null=True, help_text="Descripción adicional")
    orden = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.noticia.titulo} - {self.titulo}: {self.valor}"

    class Meta:
        verbose_name = "Estadística de Noticia"
        verbose_name_plural = "Estadísticas de Noticias"
        ordering = ['orden']


class EnlaceNoticia(models.Model):
    noticia = models.ForeignKey(NoticiaBanner, on_delete=models.CASCADE, related_name='enlaces')
    titulo = models.CharField(max_length=100, help_text="Título del enlace")
    url = models.URLField(help_text="URL del enlace")
    descripcion = models.CharField(max_length=255, blank=True, null=True, help_text="Descripción del enlace")
    orden = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.noticia.titulo} - {self.titulo}"

    class Meta:
        verbose_name = "Enlace de Noticia"
        verbose_name_plural = "Enlaces de Noticias"
        ordering = ['orden']


class CategoriaInformacion(models.Model):
    """Categorías para organizar los sistemas de consulta"""
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255, help_text="Ej: Sistemas y aplicaciones, Visualizadores de datos")
    slug = models.SlugField(unique=True)
    descripcion = models.TextField(blank=True, null=True)
    icono = models.CharField(max_length=100, blank=True, null=True, help_text="Clase CSS del ícono (ej: fas fa-chart-bar)")
    color = models.CharField(max_length=50, blank=True, null=True, help_text="Color hexadecimal o CSS")
    orden = models.IntegerField(default=0, help_text="Orden de aparición en el menú")
    activo = models.BooleanField(default=True)
    
    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Categoría de Consulta"
        verbose_name_plural = "Categorías de Consulta"
        ordering = ['orden', 'nombre']


class SistemaInformacion(models.Model):
    """Sistemas de consulta individuales dentro de cada categoría"""
    TIPO_ENLACE_CHOICES = [
        ('interno', 'Enlace interno'),
        ('externo', 'Enlace externo'),
        ('modal', 'Modal/Popup'),
        ('descarga', 'Descarga de archivo'),
    ]
    
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255, help_text="Ej: Cali en Cifras, Geovisor IDESC")
    descripcion = models.TextField(blank=True, null=True)
    categoria = models.ForeignKey(CategoriaInformacion, on_delete=models.CASCADE, related_name='sistemas')
    
    # Configuración del enlace
    tipo_enlace = models.CharField(max_length=20, choices=TIPO_ENLACE_CHOICES, default='interno')
    url = models.URLField(max_length=500, help_text="URL completa o ruta relativa")
    abrir_nueva_ventana = models.BooleanField(default=False, help_text="Abrir en nueva pestaña/ventana")
    
    # Metadatos
    icono = models.CharField(max_length=100, blank=True, null=True, help_text="Clase CSS del ícono")
    imagen_url = models.URLField(blank=True, null=True, help_text="URL de la imagen representativa del sistema")
    orden = models.IntegerField(default=0, help_text="Orden dentro de la categoría")
    activo = models.BooleanField(default=True)
    
    # Información adicional
    desarrollador = models.CharField(max_length=255, blank=True, null=True, help_text="Entidad o persona responsable")
    version = models.CharField(max_length=50, blank=True, null=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    requiere_autenticacion = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.nombre} ({self.categoria.nombre})"
    
    class Meta:
        verbose_name = "Sistema de Consulta"
        verbose_name_plural = "Sistemas de Consulta"
        ordering = ['categoria__orden', 'orden', 'nombre']


class CategoriaProyecto(models.Model):
    """Categorías para organizar los proyectos de información"""
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255, help_text="Ej: Observatorios, Sistemas de información sectoriales")
    slug = models.SlugField(unique=True)
    descripcion = models.TextField(blank=True, null=True)
    icono = models.CharField(max_length=100, blank=True, null=True, help_text="Clase CSS del ícono (ej: fas fa-eye)")
    color = models.CharField(max_length=50, blank=True, null=True, help_text="Color hexadecimal o CSS")
    orden = models.IntegerField(default=0, help_text="Orden de aparición en el menú")
    activo = models.BooleanField(default=True)
    
    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Categoría de Proyecto"
        verbose_name_plural = "Categorías de Proyectos"
        ordering = ['orden', 'nombre']


class ProyectoInformacion(models.Model):
    """Proyectos de información (observatorios y sistemas sectoriales) de otras dependencias"""
    TIPO_ENLACE_CHOICES = [
        ('interno', 'Enlace interno'),
        ('externo', 'Enlace externo'),
        ('modal', 'Modal/Popup'),
        ('descarga', 'Descarga de archivo'),
    ]
    
    ESTADO_CHOICES = [
        ('activo', 'Activo'),
        ('en_desarrollo', 'En desarrollo'),
        ('mantenimiento', 'En mantenimiento'),
        ('inactivo', 'Inactivo'),
    ]
    
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255, help_text="Ej: Observatorio de Seguridad, Sistema de Salud")
    descripcion = models.TextField(blank=True, null=True)
    categoria = models.ForeignKey(CategoriaProyecto, on_delete=models.CASCADE, related_name='proyectos')
    
    # Configuración del enlace
    tipo_enlace = models.CharField(max_length=20, choices=TIPO_ENLACE_CHOICES, default='externo')
    url = models.URLField(max_length=500, help_text="URL completa o ruta relativa")
    abrir_nueva_ventana = models.BooleanField(default=True, help_text="Abrir en nueva pestaña/ventana")
    
    # Metadatos del proyecto
    icono = models.CharField(max_length=100, blank=True, null=True, help_text="Clase CSS del ícono")
    imagen_url = models.URLField(blank=True, null=True, help_text="URL del logo o imagen del proyecto")
    orden = models.IntegerField(default=0, help_text="Orden dentro de la categoría")
    activo = models.BooleanField(default=True)
    
    # Información institucional
    dependencia_responsable = models.CharField(max_length=255, blank=True, null=True, help_text="Secretaría o entidad responsable")
    contacto_email = models.EmailField(blank=True, null=True, help_text="Email de contacto del proyecto")
    contacto_telefono = models.CharField(max_length=50, blank=True, null=True, help_text="Teléfono de contacto")
    
    # Estado y fechas
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='activo')
    fecha_inicio = models.DateField(blank=True, null=True, help_text="Fecha de inicio del proyecto")
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    # Información adicional
    objetivos = models.TextField(blank=True, null=True, help_text="Objetivos principales del proyecto")
    poblacion_objetivo = models.CharField(max_length=255, blank=True, null=True, help_text="Población o sector objetivo")
    
    def __str__(self):
        return f"{self.nombre} ({self.dependencia_responsable or self.categoria.nombre})"
    
    class Meta:
        verbose_name = "Proyecto de Información"
        verbose_name_plural = "Proyectos de Información"
        ordering = ['categoria__orden', 'orden', 'nombre']


class AreaInfraestructura(models.Model):
    """Nivel 1: Áreas principales de infraestructura (ej: Normas y estándares)"""
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255, help_text="Ej: Normas y estándares, Lineamientos técnicos")
    slug = models.SlugField(unique=True)
    descripcion = models.TextField(blank=True, null=True)
    icono = models.CharField(max_length=100, blank=True, null=True, help_text="Clase CSS del ícono")
    color = models.CharField(max_length=50, blank=True, null=True, help_text="Color hexadecimal o CSS")
    orden = models.IntegerField(default=0, help_text="Orden de aparición")
    activo = models.BooleanField(default=True)
    
    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Área de Infraestructura"
        verbose_name_plural = "Áreas de Infraestructura"
        ordering = ['orden', 'nombre']


class CategoriaInfraestructura(models.Model):
    """Nivel 2: Categorías dentro de cada área (ej: Procesos y subprocesos, Planificación estadística)"""
    id = models.AutoField(primary_key=True)
    area = models.ForeignKey(AreaInfraestructura, on_delete=models.CASCADE, related_name='categorias')
    nombre = models.CharField(max_length=255, help_text="Ej: Procesos y subprocesos, Planificación estadística")
    slug = models.SlugField()
    descripcion = models.TextField(blank=True, null=True)
    icono = models.CharField(max_length=100, blank=True, null=True, help_text="Clase CSS del ícono")
    imagen_url = models.URLField(blank=True, null=True, help_text="URL de la imagen representativa")
    orden = models.IntegerField(default=0, help_text="Orden dentro del área")
    activo = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.area.nombre} - {self.nombre}"
    
    class Meta:
        verbose_name = "Categoría de Infraestructura"
        verbose_name_plural = "Categorías de Infraestructura"
        ordering = ['area__orden', 'orden', 'nombre']
        unique_together = ['area', 'slug']


class SubcategoriaInfraestructura(models.Model):
    """Nivel 3: Subcategorías (ej: Herramientas de planificación, Capacitaciones)"""
    id = models.AutoField(primary_key=True)
    categoria = models.ForeignKey(CategoriaInfraestructura, on_delete=models.CASCADE, related_name='subcategorias')
    nombre = models.CharField(max_length=255, help_text="Ej: Herramientas de planificación, Capacitaciones")
    slug = models.SlugField()
    descripcion = models.TextField(blank=True, null=True)
    icono = models.CharField(max_length=100, blank=True, null=True, help_text="Clase CSS del ícono")
    imagen_url = models.URLField(blank=True, null=True, help_text="URL de la imagen representativa")
    orden = models.IntegerField(default=0, help_text="Orden dentro de la categoría")
    activo = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.categoria.nombre} - {self.nombre}"
    
    class Meta:
        verbose_name = "Subcategoría de Infraestructura"
        verbose_name_plural = "Subcategorías de Infraestructura"
        ordering = ['categoria__orden', 'orden', 'nombre']
        unique_together = ['categoria', 'slug']


class GrupoDocumento(models.Model):
    """Nivel 4: Grupos de documentos dentro de cada subcategoría"""
    id = models.AutoField(primary_key=True)
    subcategoria = models.ForeignKey(SubcategoriaInfraestructura, on_delete=models.CASCADE, related_name='grupos_documentos')
    nombre = models.CharField(max_length=255, help_text="Ej: Documentos de planificación, Formatos de registro")
    slug = models.SlugField()
    descripcion = models.TextField(blank=True, null=True, help_text="Descripción del grupo de documentos")
    icono = models.CharField(max_length=100, blank=True, null=True, help_text="Clase CSS del ícono")
    imagen_url = models.URLField(blank=True, null=True, help_text="URL de la imagen representativa")
    orden = models.IntegerField(default=0, help_text="Orden dentro de la subcategoría")
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.subcategoria.nombre} - {self.nombre}"
    
    class Meta:
        verbose_name = "Grupo de Documento"
        verbose_name_plural = "Grupos de Documentos"
        ordering = ['subcategoria__orden', 'orden', 'nombre']
        unique_together = ['subcategoria', 'slug']


class DocumentoInfraestructura(models.Model):
    """Nivel 5: Documentos finales con contenido enriquecido"""
    TIPO_DOCUMENTO_CHOICES = [
        ('proceso', 'Proceso'),
        ('subproceso', 'Subproceso'),
        ('procedimiento', 'Procedimiento'),
        ('herramienta', 'Herramienta'),
        ('metodologia', 'Metodología'),
        ('guia', 'Guía'),
        ('manual', 'Manual'),
        ('formato', 'Formato'),
        ('otro', 'Otro'),
    ]
    
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('revision', 'En revisión'),
        ('aprobado', 'Aprobado'),
        ('publicado', 'Publicado'),
        ('archivado', 'Archivado'),
    ]
    
    id = models.AutoField(primary_key=True)
    grupo_documento = models.ForeignKey(GrupoDocumento, on_delete=models.CASCADE, related_name='documentos')
    nombre = models.CharField(max_length=255, help_text="Ej: Criterios técnicos de priorización para OOEE")
    slug = models.SlugField()
    descripcion = models.TextField(blank=True, null=True, help_text="Descripción breve del documento")
    
    # Contenido enriquecido
    contenido = CKEditor5Field(config_name='infraestructura', help_text="Contenido principal del documento con formato HTML")
    
    # Metadatos del documento
    tipo_documento = models.CharField(max_length=20, choices=TIPO_DOCUMENTO_CHOICES, default='proceso')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    version = models.CharField(max_length=50, blank=True, null=True, help_text="Ej: v1.0, v2.1")
    
    # Información de autoría y fechas
    autor = models.CharField(max_length=255, blank=True, null=True, help_text="Autor o responsable del documento")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    fecha_publicacion = models.DateTimeField(blank=True, null=True)
    fecha_revision = models.DateField(blank=True, null=True, help_text="Próxima fecha de revisión")
    
    # Archivos adjuntos
    archivo_pdf = models.FileField(upload_to='infraestructura/documentos/', blank=True, null=True, help_text="Archivo PDF del documento")
    archivo_word = models.FileField(upload_to='infraestructura/documentos/', blank=True, null=True, help_text="Archivo Word del documento")
    
    # Configuración
    icono = models.CharField(max_length=100, blank=True, null=True, help_text="Clase CSS del ícono")
    orden = models.IntegerField(default=0, help_text="Orden dentro del grupo de documentos")
    activo = models.BooleanField(default=True)
    destacado = models.BooleanField(default=False, help_text="Mostrar como documento destacado")
    
    # SEO y metadatos
    palabras_clave = models.CharField(max_length=500, blank=True, null=True, help_text="Palabras clave separadas por comas")
    resumen_ejecutivo = models.TextField(blank=True, null=True, help_text="Resumen ejecutivo del documento")
    
    def __str__(self):
        return f"{self.grupo_documento.nombre} - {self.nombre}"
    
    def get_absolute_url(self):
        from django.urls import reverse
        try:
            area_slug = self.grupo_documento.subcategoria.categoria.area.slug
            categoria_slug = self.grupo_documento.subcategoria.categoria.slug
            subcategoria_slug = self.grupo_documento.subcategoria.slug
            grupo_slug = self.grupo_documento.slug
        except AttributeError:
            return ''
        return reverse('indicadores:infraestructura_documento', kwargs={
            'area_slug': area_slug,
            'categoria_slug': categoria_slug,
            'subcategoria_slug': subcategoria_slug,
            'grupo_slug': grupo_slug,
            'documento_slug': self.slug
        })
    
    class Meta:
        verbose_name = "Documento de Infraestructura"
        verbose_name_plural = "Documentos de Infraestructura"
        ordering = ['grupo_documento__orden', 'orden', 'nombre']
        unique_together = ['grupo_documento', 'slug']


# ============================================================================
# MÓDULO DE PRODUCTOS ACADÉMICOS
# ============================================================================

class ProductoAcademico(models.Model):
    """Paper académico enriquecido que documenta el proceso de producción de indicadores"""
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('revision', 'En revisión'),
        ('publicado', 'Publicado'),
    ]

    id = models.AutoField(primary_key=True)
    organismo = models.ForeignKey(
        'Organismo',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Organismo responsable del producto académico"
    )
    conjunto_datos_principal = models.ForeignKey(
        'ConjuntoDatos',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Conjunto de datos principal de referencia (ej: población proyectada Cali 2042)"
    )
    indicadores_derivados = models.ManyToManyField(
        'Indicador',
        blank=True,
        help_text="Indicadores derivados que se documentan en este paper"
    )

    titulo = models.CharField(max_length=500, help_text="Título completo del paper")
    slug = models.SlugField(unique=True, help_text="URL amigable")
    resumen = models.TextField(blank=True, help_text="Resumen / abstract del paper")
    palabras_clave = models.CharField(max_length=255, blank=True, help_text="Palabras clave separadas por comas")
    area_tematica = models.CharField(max_length=255, blank=True, help_text="Ej: Demografía computacional · Estadística aplicada")

    # -------------------------------------------------------------------------
    # Metadatos de producto estadístico (modo INEGI)
    # -------------------------------------------------------------------------
    es_producto_estadistico = models.BooleanField(
        default=False,
        help_text="Si es True, la UI muestra tabs (Presentación, Resultados, Documentación, etc.) como un producto estadístico integrado."
    )
    logo = models.ImageField(
        upload_to='productos/logos/',
        blank=True, null=True,
        help_text="Logo o insignia del producto (máx. 500×500 px)"
    )
    operacion = models.ForeignKey(
        'OperacionEstadistica',
        on_delete=models.SET_NULL,
        blank=True, null=True,
        help_text="Operación estadística de la que deriva este producto"
    )
    cobertura_geografica = models.CharField(
        max_length=255, blank=True,
        help_text="Ej: Distrito de Santiago de Cali"
    )
    periodo_referencia = models.CharField(
        max_length=255, blank=True,
        help_text="Ej: 15 de febrero – 15 de marzo de 2024"
    )
    diseno_conceptual = CKEditor5Field(
        config_name='infraestructura',
        blank=True, null=True,
        help_text="Diseño conceptual, metodología o maestro de muestra del producto"
    )
    temas_relacionados = models.ManyToManyField(
        'MenuSubtema',
        blank=True,
        help_text="Temas / subtemas estadísticos relacionados con este producto"
    )

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    autor = models.CharField(max_length=255, blank=True, help_text="Autor principal")
    institucion = models.CharField(max_length=255, blank=True, help_text="Institución o dependencia")
    fecha_publicacion = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto Académico"
        verbose_name_plural = "Productos Académicos"
        ordering = ['-created_at']

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('indicadores:producto_academico', kwargs={'slug': self.slug})


class SeccionPaper(models.Model):
    """Secciones individuales que componen un Producto Académico"""
    TIPO_SECCION = [
        ('resumen', 'Resumen'),
        ('introduccion', 'Introducción'),
        ('antecedentes', 'Antecedentes / Marco teórico'),
        ('contexto', 'Contexto / Condiciones del caso'),
        ('metodologia', 'Metodología'),
        ('resultados', 'Resultados / Validación'),
        ('discusion', 'Discusión'),
        ('conclusiones', 'Conclusiones'),
        ('referencias', 'Referencias'),
        ('anexo', 'Anexo técnico'),
    ]

    TIPO_BLOQUE = [
        ('texto', 'Texto enriquecido'),
        ('grafico_indicador', 'Gráfico dinámico de indicador'),
        ('tabla_datos', 'Tabla de datos (HTML estático)'),
        ('mapa_indicador', 'Mapa geográfico de indicador'),
        ('tabla_datos_indicador', 'Tabla dinámica de datos de indicador'),
        ('tabla_microdata', 'Tabla de muestra de conjunto de datos'),
        ('ficha_indicador', 'Ficha técnica de indicador'),
        ('documento_infraestructura', 'Documento de infraestructura'),
        ('sistema_informacion', 'Sistema / herramienta de información'),
        ('publicacion_relacionada', 'Publicación relacionada'),
        ('resultado_destacado', 'Resultado destacado (KPI)'),
        ('formula', 'Bloque de fórmulas / LaTeX'),
        ('visor_comparativo', 'Visor comparativo de indicadores'),
        ('tabla_dinamica_microdata', 'Tabla dinámica de conjunto de datos'),
        ('video_embed', 'Video embebido (YouTube/Vimeo)'),
        ('galeria_imagenes', 'Galería de imágenes'),
        ('carrusel', 'Carrusel / Slider'),
        ('infografia', 'Infografía / Imagen grande'),
        ('acordeon', 'Acordeón / Preguntas frecuentes'),
        ('descarga_archivo', 'Descarga de archivos'),
    ]

    id = models.AutoField(primary_key=True)
    producto = models.ForeignKey(
        ProductoAcademico,
        on_delete=models.CASCADE,
        related_name='secciones'
    )
    tipo_seccion = models.CharField(max_length=30, choices=TIPO_SECCION, default='introduccion')
    numero_orden = models.PositiveSmallIntegerField(default=0, help_text="Orden de aparición en el paper")
    subnumero = models.CharField(max_length=10, blank=True, help_text="Ej: 2.1, 4.2")
    titulo = models.CharField(max_length=300, blank=True, help_text="Título de la sección o subsección")

    tipo_bloque = models.CharField(max_length=30, choices=TIPO_BLOQUE, default='texto')
    contenido = CKEditor5Field(config_name='infraestructura', blank=True, help_text="Contenido principal (texto, tablas, etc.)")

    # Solo aplica si tipo_bloque == 'grafico_indicador'
    indicador_vinculado = models.ForeignKey(
        'Indicador',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Indicador a visualizar (solo para bloques de gráfico)"
    )
    configuracion_grafico = models.JSONField(
        blank=True,
        null=True,
        help_text='Configuración del gráfico o mapa: {"tipo": "barras|lineas|piramide", "anio_default": 2025, "mostrar_desagregaciones": true, "tipo_mapa": "choropleth"}'
    )

    # Solo aplica si tipo_bloque == 'tabla_microdata'
    conjunto_datos_vinculado = models.ForeignKey(
        'ConjuntoDatos',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Conjunto de datos a mostrar en tabla de muestra (solo para bloques de tabla_microdata)"
    )

    # Solo aplica si tipo_bloque == 'documento_infraestructura'
    documento_vinculado = models.ForeignKey(
        'DocumentoInfraestructura',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Documento de infraestructura a mostrar (metodología, manual, guía)"
    )

    # Solo aplica si tipo_bloque == 'sistema_informacion'
    sistema_vinculado = models.ForeignKey(
        'SistemaInformacion',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Sistema o herramienta de información a vincular"
    )

    # Solo aplica si tipo_bloque == 'publicacion_relacionada'
    publicaciones_relacionadas = models.ManyToManyField(
        'ProductoAcademico',
        blank=True,
        symmetrical=False,
        related_name='secciones_que_me_citan',
        help_text="Otros productos académicos relacionados con esta sección"
    )

    # Solo aplica si tipo_bloque == 'visor_comparativo'
    indicadores_preseleccionados = models.ManyToManyField(
        'Indicador',
        blank=True,
        symmetrical=False,
        related_name='secciones_comparativas',
        help_text="Indicadores a mostrar en el visor comparativo embebido"
    )

    # Solo aplica si tipo_bloque == 'video_embed'
    video_url = models.URLField(
        blank=True,
        null=True,
        help_text="URL del video de YouTube o Vimeo (solo para bloques de video)"
    )

    # Solo aplica si tipo_bloque == 'acordeon'
    acordeon_items = models.JSONField(
        blank=True,
        null=True,
        help_text='Items del acordeón: [{"titulo": "...", "contenido": "..."}]'
    )

    class Meta:
        verbose_name = "Sección del Paper"
        verbose_name_plural = "Secciones del Paper"
        ordering = ['numero_orden', 'subnumero']

    def __str__(self):
        label = f"{self.numero_orden}"
        if self.subnumero:
            label = self.subnumero
        return f"{label}. {self.titulo or self.get_tipo_seccion_display()}"


class ImagenSeccion(models.Model):
    """Imágenes para galerías, carruseles e infografías dentro de una sección."""
    TIPO_USO = [
        ('galeria', 'Galería'),
        ('carrusel', 'Carrusel'),
        ('infografia', 'Infografía'),
    ]
    id = models.AutoField(primary_key=True)
    seccion = models.ForeignKey(SeccionPaper, on_delete=models.CASCADE, related_name='imagenes')
    tipo_uso = models.CharField(max_length=20, choices=TIPO_USO, default='galeria')
    imagen = models.ImageField(upload_to='productos_academicos/imagenes/')
    titulo = models.CharField(max_length=255, blank=True, help_text="Título o leyenda de la imagen")
    descripcion = models.TextField(blank=True, help_text="Descripción o pie de foto")
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden']
        verbose_name = "Imagen de sección"
        verbose_name_plural = "Imágenes de sección"

    def __str__(self):
        return f"{self.titulo or self.imagen.name} ({self.get_tipo_uso_display()})"


class ArchivoSeccion(models.Model):
    """Archivos descargables genéricos vinculados a una sección."""
    id = models.AutoField(primary_key=True)
    seccion = models.ForeignKey(SeccionPaper, on_delete=models.CASCADE, related_name='archivos')
    archivo = models.FileField(upload_to='productos_academicos/archivos/')
    nombre = models.CharField(max_length=255, blank=True, help_text="Nombre visible del archivo")
    descripcion = models.TextField(blank=True)
    icono = models.CharField(max_length=50, blank=True, default='fas fa-file', help_text="Clase de FontAwesome (ej: fas fa-file-pdf)")
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden']
        verbose_name = "Archivo de sección"
        verbose_name_plural = "Archivos de sección"

    def __str__(self):
        return self.nombre or self.archivo.name


class Aliado(models.Model):
    """Aliados que aparecen en el pie de página"""
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255, help_text="Nombre del aliado")
    slug = models.SlugField(unique=True, help_text="URL amigable para el aliado")
    logo_url = models.URLField(blank=True, null=True, help_text="URL del logo del aliado (preferiblemente PNG sin fondo)")
    descripcion = CKEditor5Field(config_name='default', help_text="Descripción detallada de la alianza con formato HTML")
    url_externa = models.URLField(blank=True, null=True, help_text="Sitio web del aliado (opcional)")
    orden = models.IntegerField(default=0, help_text="Orden de aparición en el pie de página")
    activo = models.BooleanField(default=True, help_text="Si el aliado está activo para mostrar")
    fecha_inicio_alianza = models.DateField(blank=True, null=True, help_text="Fecha de inicio de la alianza")
    fecha_fin_alianza = models.DateField(blank=True, null=True, help_text="Fecha de fin de la alianza (opcional)")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.nombre
    
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('indicadores:aliado_detalle', kwargs={'slug': self.slug})
    
    class Meta:
        verbose_name = "Aliado"
        verbose_name_plural = "Aliados"
        ordering = ['orden', 'nombre']


class Evento(models.Model):
    """Eventos para el calendario en la página principal"""
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255, help_text="Nombre del evento")
    slug = models.SlugField(unique=True, help_text="URL amigable para el evento")
    descripcion = CKEditor5Field(config_name='default', help_text="Descripción detallada del evento")
    lugar = models.CharField(max_length=255, help_text="Lugar donde se realizará el evento")
    fecha_inicio = models.DateTimeField(help_text="Fecha y hora de inicio del evento")
    fecha_fin = models.DateTimeField(help_text="Fecha y hora de finalización del evento")
    imagen_url = models.URLField(blank=True, null=True, help_text="URL de la imagen representativa del evento (opcional)")
    url_externa = models.URLField(blank=True, null=True, help_text="Enlace externo para más información (opcional)")
    activo = models.BooleanField(default=True, help_text="Si el evento está activo para mostrar")
    destacado = models.BooleanField(default=False, help_text="Si el evento debe destacarse en el calendario")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.nombre} - {self.fecha_inicio.strftime('%d/%m/%Y %H:%M')}"
    
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('indicadores:evento_detalle', kwargs={'slug': self.slug})
    
    @property
    def duracion_horas(self):
        """Calcula la duración del evento en horas"""
        if self.fecha_fin and self.fecha_inicio:
            delta = self.fecha_fin - self.fecha_inicio
            return round(delta.total_seconds() / 3600, 1)
        return 0
    
    @property
    def es_evento_pasado(self):
        """Verifica si el evento ya pasó"""
        from django.utils import timezone
        return self.fecha_fin < timezone.now() if self.fecha_fin else False
    
    @property
    def es_evento_actual(self):
        """Verifica si el evento está ocurriendo ahora"""
        from django.utils import timezone
        now = timezone.now()
        return self.fecha_inicio <= now <= self.fecha_fin if self.fecha_fin else False
    
    class Meta:
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"
        ordering = ['fecha_inicio']

from pgvector.django import VectorField

class DocumentoVector(models.Model):
    """
    Almacena los embeddings de los documentos para búsqueda semántica.
    """
    TIPO_DOC_CHOICES = [
        ('indicador', 'Indicador'),
        ('tema', 'Tema'),
        ('subtema', 'Subtema'),
        ('dominio', 'Dominio'),
        ('producto_academico', 'Producto Académico'),
        ('documento_infraestructura', 'Documento de Infraestructura'),
        ('catalogo_consulta', 'Catálogo de Consulta'),
    ]
    
    tipo = models.CharField(max_length=30, choices=TIPO_DOC_CHOICES)
    referencia_id = models.IntegerField()
    contenido = models.TextField()
    embedding = VectorField(dimensions=384)  # Usando un modelo más ligero (all-MiniLM-L6-v2)
    metadata = models.JSONField(default=dict, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    vector = models.JSONField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['tipo']),
            models.Index(fields=['id', 'tipo']),
            models.Index(fields=['tipo', 'referencia_id']),
        ]
        verbose_name = "Documento Vectorial"
        verbose_name_plural = "Documentos Vectoriales"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.referencia_id}"


# ============================================================================
# MODELOS PARA MÓDULO DE RECOLECCIÓN Y REPORTES
# ============================================================================

class PerfilRecolector(models.Model):
    """Perfil extendido para usuarios con roles específicos del sistema"""
    
    ROL_CHOICES = [
        ('recolector', 'Recolector de Datos'),
        ('consultor', 'Consultor de Reportes'),
        ('ambos', 'Recolector y Consultor'),
        ('delegado', 'Delegado de Organismo'),
        ('validador', 'Validador Estadístico (SIIED)'),
        ('editor', 'Editor de Contenidos'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil_recolector')
    rol = models.CharField(
        max_length=20, 
        choices=ROL_CHOICES, 
        default='recolector',
        help_text="Define a qué módulos tiene acceso el usuario"
    )
    institucion = models.CharField(max_length=255, help_text="Institución u organismo al que pertenece")
    cargo = models.CharField(max_length=255, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    # Vínculo a organismo (requerido para delegados, opcional para otros roles)
    organismo = models.ForeignKey(
        'Organismo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delegados',
        help_text="Organismo al que pertenece (obligatorio para delegados)"
    )

    # Subrol de equipo técnico FICED: cada delegado responde solo las
    # preguntas asignadas a su equipo. Vacío = responde todo el formulario.
    SUBROL_FICED_CHOICES = [
        ('', 'Todos los equipos (formulario completo)'),
        ('ETUAG_PSP', 'ETUAG_PSP'),
        ('ETOBS', 'ETOBS'),
        ('ETPP', 'ETPP'),
        ('ETSGC', 'ETSGC'),
        ('ETGIE', 'ETGIE'),
    ]
    subrol_ficed = models.CharField(
        max_length=15,
        choices=SUBROL_FICED_CHOICES,
        blank=True,
        default='',
        help_text="Equipo técnico FICED del delegado (vacío = responde todo)"
    )
    
    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuarios"
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_rol_display()}"
    
    def puede_recolectar(self):
        """Verifica si el usuario puede acceder al módulo de recolección"""
        return self.activo and self.rol in ['recolector', 'ambos']
    
    def puede_consultar_reportes(self):
        """Verifica si el usuario puede acceder al módulo de reportes"""
        return self.activo and self.rol in ['consultor', 'ambos']
    
    def es_delegado(self):
        """Verifica si es delegado de organismo"""
        return self.activo and self.rol == 'delegado'
    
    def es_validador(self):
        """Verifica si es validador estadístico del SIIED"""
        return self.activo and self.rol == 'validador'
    
    def puede_editar_contenidos(self):
        """Verifica si el usuario puede acceder al módulo editorial"""
        return self.activo and self.rol == 'editor'


class CargaSerieIndicador(models.Model):
    """Registro de cargas de series de datos de indicadores"""
    ESTADO_CHOICES = [
        # Estados legacy (módulo recolección interno)
        ('pendiente', 'Pendiente'),
        ('procesando', 'Procesando'),
        ('exitoso', 'Exitoso'),
        ('error', 'Error'),
        # Estados del nuevo flujo delegado → validador → admin
        ('borrador', 'Borrador (no enviado)'),
        ('enviado', 'Enviado para validación'),
        ('en_revision', 'En revisión por validador'),
        ('aprobado', 'Aprobado - listo para procesar'),
        ('rechazado', 'Rechazado por validador'),
        ('correcciones_solicitadas', 'Correcciones solicitadas'),
        ('procesado', 'Procesado e integrado al sistema'),
    ]
    
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cargas_series')
    indicador = models.ForeignKey('Indicador', on_delete=models.CASCADE, related_name='cargas_series', null=True, blank=True)
    
    # Archivos originales (xlsx) — opcionales para soportar cargas parciales/incrementales
    archivo_datos_xlsx = models.FileField(
        upload_to='recoleccion/series_datos/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'csv'])],
        blank=True,
        null=True,
        help_text="Archivo Excel o CSV con la serie de datos del indicador"
    )
    archivo_metadata_xlsx = models.FileField(
        upload_to='recoleccion/series_metadata/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'csv'])],
        blank=True,
        null=True,
        help_text="Archivo Excel o CSV con la metadata del indicador (puede entregarse por separado)"
    )
    
    # Archivos convertidos (csv)
    archivo_datos_csv = models.FileField(
        upload_to='recoleccion/series_datos_csv/%Y/%m/',
        blank=True,
        null=True
    )
    archivo_metadata_csv = models.FileField(
        upload_to='recoleccion/series_metadata_csv/%Y/%m/',
        blank=True,
        null=True
    )
    
    # Control
    estado = models.CharField(max_length=30, choices=ESTADO_CHOICES, default='pendiente')
    fecha_carga = models.DateTimeField(auto_now_add=True)
    fecha_procesamiento = models.DateTimeField(null=True, blank=True)
    
    # Resultados
    registros_procesados = models.IntegerField(default=0)
    registros_exitosos = models.IntegerField(default=0)
    registros_error = models.IntegerField(default=0)
    mensaje_error = models.TextField(blank=True, null=True)
    log_procesamiento = models.TextField(blank=True, null=True)
    
    # Evidencia para cuenta de cobro
    codigo_evidencia = models.CharField(max_length=50, unique=True, editable=False)
    
    # Campos del nuevo flujo de validación (delegado → validador → admin)
    es_carga_delegado = models.BooleanField(
        default=False,
        help_text="True si fue subida por un delegado de organismo"
    )
    validado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='series_validadas',
        help_text="Validador que aprobó o rechazó esta carga"
    )
    fecha_validacion = models.DateTimeField(null=True, blank=True)
    observaciones_validador = models.TextField(
        blank=True,
        null=True,
        help_text="Observaciones del validador (visibles para el delegado)"
    )
    es_calculo_complejo = models.BooleanField(
        default=False,
        help_text="Marcado por el validador: el cálculo no puede hacerse desde extracción cartesiana. "
                  "El wizard solo cargará la serie precalculada y enlazará el conjunto de datos sin procesar reglas de extracción."
    )

    # Preferencias de gráfico del recolector (se usan como sugerencia en el wizard)
    preferencias_grafico = models.JSONField(
        blank=True,
        null=True,
        help_text="Preferencias de gráfico definidas por el recolector: {tipo_grafico, titulo, eje_x, eje_y}"
    )

    # Observaciones del admin al solicitar correcciones
    observaciones_admin = models.TextField(
        blank=True,
        null=True,
        help_text="Observaciones del administrador al solicitar correcciones desde el wizard"
    )

    # Propiedades de completitud para cargas parciales
    @property
    def tiene_datos(self):
        return bool(self.archivo_datos_xlsx and self.archivo_datos_xlsx.name)

    @property
    def tiene_metadata(self):
        return bool(self.archivo_metadata_xlsx and self.archivo_metadata_xlsx.name)

    @property
    def esta_completa(self):
        return self.tiene_datos and self.tiene_metadata

    @property
    def porcentaje_completitud(self):
        partes = [self.tiene_datos, self.tiene_metadata]
        return int(sum(partes) / len(partes) * 100)

    @property
    def badge_antiguedad(self):
        from django.utils import timezone
        from datetime import timedelta
        if not self.fecha_carga:
            return None
        delta = timezone.now() - self.fecha_carga
        if delta < timedelta(hours=24):
            return 'nueva'
        if delta > timedelta(days=7):
            return 'urgente'
        return None

    class Meta:
        verbose_name = "Carga de Serie de Indicador"
        verbose_name_plural = "Cargas de Series de Indicadores"
        ordering = ['-fecha_carga']
    
    def __str__(self):
        return f"Carga {self.codigo_evidencia} - {self.usuario.username} - {self.fecha_carga.strftime('%Y-%m-%d')}"
    
    def save(self, *args, **kwargs):
        if not self.codigo_evidencia:
            # Generar código único: CSIND-YYYYMMDD-HHMMSS-XXXX
            import uuid
            from django.utils import timezone
            now = timezone.now()
            self.codigo_evidencia = f"CSIND-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        super().save(*args, **kwargs)


class CargaConjuntoDatos(models.Model):
    """Registro de cargas de archivos de conjuntos de datos"""
    ESTADO_CHOICES = [
        # Estados legacy (módulo recolección interno)
        ('pendiente', 'Pendiente'),
        ('procesando', 'Procesando'),
        ('exitoso', 'Exitoso'),
        ('error', 'Error'),
        # Estados del nuevo flujo delegado → validador → admin
        ('borrador', 'Borrador (no enviado)'),
        ('enviado', 'Enviado para validación'),
        ('en_revision', 'En revisión por validador'),
        ('aprobado', 'Aprobado - listo para procesar'),
        ('rechazado', 'Rechazado por validador'),
        ('correcciones_solicitadas', 'Correcciones solicitadas'),
        ('procesado', 'Procesado e integrado al sistema'),
    ]
    
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cargas_conjuntos_datos')
    conjunto_datos = models.ForeignKey('ConjuntoDatos', on_delete=models.CASCADE, related_name='cargas', null=True, blank=True)
    
    # Archivos originales (xlsx) — opcionales para soportar cargas parciales/incrementales
    archivo_microdata_xlsx = models.FileField(
        upload_to='recoleccion/microdata/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])],
        blank=True,
        null=True,
        help_text="Archivo Excel con los microdatos (puede entregarse por separado de la metadata)"
    )
    archivo_metadata_variables_xlsx = models.FileField(
        upload_to='recoleccion/microdata_metadata/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])],
        blank=True,
        null=True,
        help_text="Archivo Excel con la metadata de las variables (puede entregarse por separado)"
    )
    
    # Archivos convertidos (csv)
    archivo_microdata_csv = models.FileField(
        upload_to='recoleccion/microdata_csv/%Y/%m/',
        blank=True,
        null=True
    )
    archivo_metadata_variables_csv = models.FileField(
        upload_to='recoleccion/microdata_metadata_csv/%Y/%m/',
        blank=True,
        null=True
    )
    
    # Control
    estado = models.CharField(max_length=30, choices=ESTADO_CHOICES, default='pendiente')
    fecha_carga = models.DateTimeField(auto_now_add=True)
    fecha_procesamiento = models.DateTimeField(null=True, blank=True)
    
    # Resultados
    registros_procesados = models.IntegerField(default=0)
    registros_exitosos = models.IntegerField(default=0)
    registros_error = models.IntegerField(default=0)
    mensaje_error = models.TextField(blank=True, null=True)
    log_procesamiento = models.TextField(blank=True, null=True)
    
    # Evidencia para cuenta de cobro
    codigo_evidencia = models.CharField(max_length=50, unique=True, editable=False)
    
    # Campos del nuevo flujo de validación (delegado → validador → admin)
    es_carga_delegado = models.BooleanField(
        default=False,
        help_text="True si fue subida por un delegado de organismo"
    )
    validado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conjuntos_datos_validados',
        help_text="Validador que aprobó o rechazó esta carga"
    )
    fecha_validacion = models.DateTimeField(null=True, blank=True)
    observaciones_validador = models.TextField(
        blank=True,
        null=True,
        help_text="Observaciones del validador (visibles para el delegado)"
    )

    # Propiedades de completitud para cargas parciales
    @property
    def tiene_conjunto_datos(self):
        return bool(self.archivo_microdata_xlsx and self.archivo_microdata_xlsx.name)

    @property
    def tiene_metadata_variables(self):
        return bool(self.archivo_metadata_variables_xlsx and self.archivo_metadata_variables_xlsx.name)

    @property
    def esta_completa(self):
        return self.tiene_conjunto_datos and self.tiene_metadata_variables

    @property
    def porcentaje_completitud(self):
        partes = [self.tiene_conjunto_datos, self.tiene_metadata_variables]
        return int(sum(partes) / len(partes) * 100)

    @property
    def badge_antiguedad(self):
        from django.utils import timezone
        from datetime import timedelta
        if not self.fecha_carga:
            return None
        delta = timezone.now() - self.fecha_carga
        if delta < timedelta(hours=24):
            return 'nueva'
        if delta > timedelta(days=7):
            return 'urgente'
        return None

    class Meta:
        verbose_name = "Carga de Conjunto de Datos"
        verbose_name_plural = "Cargas de Conjuntos de Datos"
        ordering = ['-fecha_carga']
    
    def __str__(self):
        return f"Carga {self.codigo_evidencia} - {self.usuario.username} - {self.fecha_carga.strftime('%Y-%m-%d')}"
    
    def save(self, *args, **kwargs):
        if not self.codigo_evidencia:
            # Generar código único: CMIC-YYYYMMDD-HHMMSS-ID
            from django.utils import timezone
            now = timezone.now()
            self.codigo_evidencia = f"CMIC-{now.strftime('%Y%m%d-%H%M%S')}"
        super().save(*args, **kwargs)


class CargaMasivaSerie(models.Model):
    """Registro de cargas masivas de series de indicadores"""
    TIPO_CARGA_CHOICES = [
        ('datos', 'Solo datos'),
        ('metadata', 'Solo metadata'),
        ('ambos', 'Datos y metadata'),
    ]
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('procesando', 'Procesando'),
        ('validacion_recolector', 'Validación del recolector'),
        ('despachada', 'Despachada al administrador'),
        ('finalizada', 'Finalizada'),
        ('error', 'Error'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cargas_masivas_series')

    archivo_maestro_datos = models.FileField(
        upload_to='recoleccion/masiva/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'csv'])],
        blank=True, null=True,
        help_text="Archivo maestro con datos de series de múltiples indicadores"
    )

    archivo_maestro_metadata = models.FileField(
        upload_to='recoleccion/masiva/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'csv'])],
        blank=True, null=True,
        help_text="Archivo maestro con metadata de múltiples indicadores (una fila por indicador)"
    )

    tipo_carga = models.CharField(max_length=20, choices=TIPO_CARGA_CHOICES, default='ambos')
    estado = models.CharField(max_length=30, choices=ESTADO_CHOICES, default='pendiente')

    fecha_carga = models.DateTimeField(auto_now_add=True)
    fecha_procesamiento = models.DateTimeField(null=True, blank=True)

    log_procesamiento = models.TextField(blank=True, null=True)
    mensaje_error = models.TextField(blank=True, null=True)

    codigo_evidencia = models.CharField(max_length=50, unique=True, editable=False)

    # Relaciones para trazabilidad
    indicadores_afectados = models.ManyToManyField(
        'Indicador',
        blank=True,
        related_name='cargas_masivas'
    )
    cargas_series = models.ManyToManyField(
        'CargaSerieIndicador',
        blank=True,
        related_name='carga_masiva_origen'
    )

    # Resultados del parsing (indicadores detectados, dominios, etc.)
    resumen_json = models.JSONField(
        blank=True,
        null=True,
        help_text="Resumen estructurado de indicadores detectados, dominios, errores"
    )

    class Meta:
        verbose_name = "Carga Masiva de Series"
        verbose_name_plural = "Cargas Masivas de Series"
        ordering = ['-fecha_carga']

    def __str__(self):
        return f"Carga Masiva {self.codigo_evidencia} - {self.usuario.username} - {self.fecha_carga.strftime('%Y-%m-%d')}"

    def save(self, *args, **kwargs):
        if not self.codigo_evidencia:
            import uuid
            from django.utils import timezone
            now = timezone.now()
            self.codigo_evidencia = f"CMS-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        super().save(*args, **kwargs)


# ============================================================================
# MODELOS PARA SISTEMA DE SATISFACCIÓN CIUDADANA
# ============================================================================

class Organismo(models.Model):
    """
    Organismos y dependencias de la Alcaldía que responden consultas ciudadanas
    """
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(
        max_length=255,
        help_text="Nombre completo del organismo o dependencia"
    )
    codigo = models.SlugField(
        unique=True,
        max_length=100,
        help_text="Código único para generar URL (ej: 'planeacion', 'salud')"
    )
    descripcion = models.TextField(
        blank=True,
        null=True,
        help_text="Descripción breve del organismo"
    )
    activo = models.BooleanField(
        default=True,
        help_text="Si está activo para recibir calificaciones"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    # Contacto (opcional)
    email_contacto = models.EmailField(blank=True, null=True)
    responsable = models.CharField(max_length=255, blank=True, null=True)

    # Organigrama oficial de la Alcaldía (fuente de verdad, consulta sep-2026)
    codigo_organigrama = models.CharField(
        max_length=10, blank=True, null=True, unique=True,
        help_text="ID oficial del organigrama (ej: O01, O24). Vacío si no aplica."
    )
    tipo_organigrama = models.CharField(
        max_length=60, blank=True, null=True,
        choices=[
            ('secretaria', 'Secretaría'),
            ('departamento_administrativo', 'Departamento administrativo'),
            ('unidad_administrativa_especial', 'Unidad administrativa especial'),
            ('entidad_descentralizada', 'Entidad Descentralizada'),
            ('otro', 'Otro'),
        ],
        help_text="Tipo de organismo según el organigrama oficial"
    )
    nombre_menu = models.CharField(
        max_length=100, blank=True,
        help_text="Nombre corto del organigrama para menús"
    )

    class Meta:
        verbose_name = "Organismo"
        verbose_name_plural = "Organismos"
        ordering = ['nombre']
    
    def __str__(self):
        return self.nombre
    
    def get_url_satisfaccion_rapida(self):
        """Retorna la URL base para calificación rápida"""
        from django.urls import reverse
        return reverse('indicadores:satisfaccion_rapida', kwargs={'codigo_organismo': self.codigo})
    
    def get_url_formulario_completo(self):
        """Retorna la URL del formulario completo"""
        from django.urls import reverse
        return reverse('indicadores:satisfaccion_formulario', kwargs={'codigo_organismo': self.codigo})
    


class Suborganismo(models.Model):
    """
    Subdirecciones, Oficinas o Grupos dentro de un Organismo.
    Nivel intermedio entre Organismo y Equipo de Trabajo.
    Pregunta 7.3 del formulario metodológico.
    """
    id = models.AutoField(primary_key=True)
    
    organismo = models.ForeignKey(
        Organismo,
        on_delete=models.CASCADE,
        related_name='suborganismos',
        help_text="Organismo al que pertenece este suborganismo"
    )
    
    nombre = models.CharField(
        max_length=200,
        help_text="Ej: Subdirección de Desarrollo Integral, Oficina de Planeación"
    )
    
    codigo = models.SlugField(
        max_length=100,
        help_text="Código único del suborganismo para URLs"
    )
    
    tipo = models.CharField(
        max_length=50,
        choices=[
            ('subdireccion', 'Subdirección'),
            ('subsecretaria', 'Subsecretaría'),
            ('oficina', 'Oficina'),
            ('unidad_apoyo', 'Unidad de apoyo a la gestión'),
            ('despacho', 'Despacho'),
            ('contaduria', 'Contaduría'),
            ('centros_cali', 'Centros CALI (agrupación)'),
            ('grupo', 'Grupo de Trabajo'),
            ('departamento', 'Departamento'),
            ('otro', 'Otro'),
        ],
        default='subdireccion',
        help_text="Tipo de estructura organizacional"
    )

    codigo_organigrama = models.CharField(
        max_length=10, blank=True, null=True, unique=True,
        help_text="ID de dependencia del organigrama oficial (ej: S067)"
    )
    
    descripcion = models.TextField(
        blank=True,
        help_text="Descripción de las funciones del suborganismo"
    )
    
    activo = models.BooleanField(
        default=True,
        help_text="Si está inactivo, no aparecerá en formularios"
    )
    
    orden = models.IntegerField(
        default=0,
        help_text="Orden de visualización en listados"
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Suborganismo"
        verbose_name_plural = "Suborganismos"
        ordering = ['organismo', 'orden', 'nombre']
        unique_together = [['organismo', 'codigo']]
        indexes = [
            models.Index(fields=['organismo', 'activo']),
        ]
    
    def __str__(self):
        return f"{self.organismo.nombre} - {self.nombre}"
    
    def get_total_equipos(self):
        """Total de equipos activos en este suborganismo"""
        return self.equipos.filter(activo=True).count()
    


class EquipoOrganismo(models.Model):
    """
    Equipos de trabajo dentro de un Suborganismo.
    Jerarquía: Organismo → Suborganismo → Equipo
    Usado en módulos de Taller y Satisfacción.
    """
    id = models.AutoField(primary_key=True)
    
    # Relación directa con Suborganismo (obligatoria)
    suborganismo = models.ForeignKey(
        'Suborganismo',
        on_delete=models.CASCADE,
        related_name='equipos',
        help_text="Suborganismo al que pertenece este equipo"
    )
    
    nombre = models.CharField(
        max_length=200,
        help_text="Nombre del equipo de trabajo"
    )
    
    codigo = models.SlugField(
        max_length=100,
        help_text="Código único del equipo (para URLs)"
    )
    
    activo = models.BooleanField(
        default=True,
        help_text="Si está inactivo, no se podrán registrar nuevas calificaciones"
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Equipo de Trabajo"
        verbose_name_plural = "Equipos de Trabajo"
        ordering = ['nombre']  # Simplificado para evitar errores con suborganismo=None
        unique_together = [['suborganismo', 'codigo']]
    
    def __str__(self):
        if self.suborganismo:
            return f"{self.suborganismo.organismo.nombre} - {self.suborganismo.nombre} - {self.nombre}"
        return f"Equipo: {self.nombre} (sin suborganismo asignado)"
    
    @property
    def organismo(self):
        """Helper para obtener el organismo desde el suborganismo"""
        if self.suborganismo:
            return self.suborganismo.organismo
        return None
    
    def get_total_respuestas(self):
        """Total de respuestas de satisfacción para este equipo"""
        return self.respuestas_rapidas.count() + self.respuestas_completas.count()
    
    def get_promedio_satisfaccion(self):
        """Promedio de calificaciones rápidas del equipo"""
        from django.db.models import Avg
        resultado = self.respuestas_rapidas.aggregate(promedio=Avg('calificacion'))
        return resultado['promedio'] or 0


class RespuestaSatisfaccionRapida(models.Model):
    """
    Calificaciones rápidas (1 clic desde email)
    """
    CALIFICACION_CHOICES = [
        (1, 'Muy insatisfecho'),
        (2, 'Insatisfecho'),
        (3, 'Neutral'),
        (4, 'Satisfecho'),
        (5, 'Muy satisfecho'),
    ]
    
    id = models.AutoField(primary_key=True)
    
    # Relación con equipo (nuevo flujo)
    equipo = models.ForeignKey(
        EquipoOrganismo,
        on_delete=models.CASCADE,
        related_name='respuestas_rapidas',
        null=True,
        blank=True,
        help_text="Equipo que recibió la calificación"
    )
    
    # Relación con organismo (mantener por compatibilidad)
    organismo = models.ForeignKey(
        Organismo,
        on_delete=models.CASCADE,
        related_name='respuestas_rapidas_organismo'
    )
    
    calificacion = models.IntegerField(
        choices=CALIFICACION_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    
    # Metadatos de la respuesta
    fecha_registro = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    # Indica si el usuario amplió la respuesta
    ampliada = models.BooleanField(
        default=False,
        help_text="Si el usuario completó el formulario detallado"
    )
    
    class Meta:
        verbose_name = "Respuesta Rápida"
        verbose_name_plural = "Respuestas Rápidas"
        ordering = ['-fecha_registro']
    
    def __str__(self):
        return f"{self.organismo.nombre} - {self.get_calificacion_display()} - {self.fecha_registro.strftime('%Y-%m-%d')}"


class RespuestaSatisfaccionCompleta(models.Model):
    """
    Respuestas completas del formulario de satisfacción
    Basado en el cuestionario oficial de la Alcaldía
    """
    CALIFICACION_CHOICES = [
        (1, 'Muy insatisfecho'),
        (2, 'Insatisfecho'),
        (3, 'Neutral'),
        (4, 'Satisfecho'),
        (5, 'Muy satisfecho'),
    ]
    
    RAZON_INSATISFACCION_CHOICES = [
        ('tiempo_excesivo', 'Tiempo de respuesta excesivo'),
        ('informacion_incompleta', 'Información incompleta'),
        ('informacion_incorrecta', 'Información incorrecta'),
        ('formato_inadecuado', 'Formato inadecuado'),
        ('canal_inaccesible', 'Canal de acceso difícil'),
        ('no_corresponde', 'No corresponde a lo solicitado'),
        ('otra', 'Otra razón'),
    ]
    
    id = models.AutoField(primary_key=True)
    
    # Relación con respuesta rápida (si existe)
    respuesta_rapida = models.OneToOneField(
        RespuestaSatisfaccionRapida,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='respuesta_completa'
    )
    
    # Relación con equipo (nuevo flujo)
    equipo = models.ForeignKey(
        EquipoOrganismo,
        on_delete=models.CASCADE,
        related_name='respuestas_completas',
        null=True,
        blank=True,
        help_text="Equipo que recibió la evaluación"
    )
    
    # Relación con organismo (mantener por compatibilidad)
    organismo = models.ForeignKey(
        Organismo,
        on_delete=models.CASCADE,
        related_name='respuestas_completas_organismo'
    )
    
    # Fecha de la respuesta a la solicitud
    fecha_respuesta_solicitud = models.DateField(
        help_text="Fecha en que se dio respuesta a la solicitud"
    )
    
    # A. MÓDULO DE SATISFACCIÓN DEL USUARIO (escala 1-5)
    # 3. UTILIDAD
    utilidad_tiempo_respuesta = models.IntegerField(
        choices=CALIFICACION_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="3.1 Tiempo de respuesta adecuado"
    )
    utilidad_claridad = models.IntegerField(
        choices=CALIFICACION_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="3.2 Claridad, precisión y facilidad de uso"
    )
    
    # 4. RELEVANCIA
    relevancia_periodicidad = models.IntegerField(
        choices=CALIFICACION_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="4.1 Periodicidad de la información"
    )
    relevancia_concordancia = models.IntegerField(
        choices=CALIFICACION_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="4.2 Concordancia con la solicitud"
    )
    
    # 5. ACCESIBILIDAD
    accesibilidad_canal = models.IntegerField(
        choices=CALIFICACION_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="5.1 Canal utilizado para realizar la solicitud"
    )
    accesibilidad_formato = models.IntegerField(
        choices=CALIFICACION_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="5.2 Formato de la información"
    )
    
    # 6. Razón principal de insatisfacción (si aplica)
    razon_insatisfaccion = models.TextField(
        blank=True,
        null=True,
        help_text="Si seleccionó 1, 2 o 3 en alguna pregunta, indique la razón principal"
    )
    
    # Metadatos
    fecha_registro = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = "Respuesta Completa"
        verbose_name_plural = "Respuestas Completas"
        ordering = ['-fecha_registro']
    
    def __str__(self):
        return f"{self.organismo.nombre} - {self.fecha_respuesta_solicitud}"
    
    def calcular_promedio_satisfaccion(self):
        """Calcula el promedio de todas las calificaciones"""
        calificaciones = [
            self.utilidad_tiempo_respuesta,
            self.utilidad_claridad,
            self.relevancia_periodicidad,
            self.relevancia_concordancia,
            self.accesibilidad_canal,
            self.accesibilidad_formato,
        ]
        # Filtrar valores None por seguridad
        calificaciones = [c for c in calificaciones if c is not None]
        if not calificaciones:
            return 0
        return sum(calificaciones) / len(calificaciones)
    
    def calcular_promedio_utilidad(self):
        """Promedio de la dimensión Utilidad"""
        valores = [self.utilidad_tiempo_respuesta, self.utilidad_claridad]
        valores = [v for v in valores if v is not None]
        if not valores:
            return 0
        return sum(valores) / len(valores)
    
    def calcular_promedio_relevancia(self):
        """Promedio de la dimensión Relevancia"""
        valores = [self.relevancia_periodicidad, self.relevancia_concordancia]
        valores = [v for v in valores if v is not None]
        if not valores:
            return 0
        return sum(valores) / len(valores)
    
    def calcular_promedio_accesibilidad(self):
        """Promedio de la dimensión Accesibilidad"""
        valores = [self.accesibilidad_canal, self.accesibilidad_formato]
        valores = [v for v in valores if v is not None]
        if not valores:
            return 0
        return sum(valores) / len(valores)
    
    def save(self, *args, **kwargs):
        # Si viene de una respuesta rápida, marcarla como ampliada
        if self.respuesta_rapida and not self.respuesta_rapida.ampliada:
            self.respuesta_rapida.ampliada = True
            self.respuesta_rapida.save()
        super().save(*args, **kwargs)


class RegistroCambio(models.Model):
    """
    Audit trail central para trazabilidad de cambios en indicadores y conjuntos de datos.
    Resuelve organismo origen (usuario) y organismo responsable (indicador).
    """
    # NOTA: las claves (carga_microdata_wizard, procesamiento_microdata) son legado
    # persistido en BD; no renombrar sin data migration.
    TIPO_EVENTO = [
        ('carga_serie_wizard', 'Carga de Serie vía Wizard'),
        ('carga_microdata_wizard', 'Carga de Conjunto de Datos vía Wizard'),
        ('carga_completa_wizard', 'Carga Completa vía Wizard'),
        ('actualizacion_manual_admin', 'Actualización manual en Admin'),
        ('procesamiento_microdata', 'Procesamiento de Conjunto de Datos'),
        ('cambio_desagregaciones', 'Cambio de desagregaciones'),
        ('cambio_metadatos', 'Cambio de metadatos'),
        ('eliminacion_datos', 'Eliminación de datos'),
    ]

    id = models.AutoField(primary_key=True)
    indicador = models.ForeignKey(
        'Indicador',
        on_delete=models.CASCADE,
        related_name='registros_cambio',
        help_text="Indicador afectado por el cambio"
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='registros_cambio',
        help_text="Usuario que realizó el cambio"
    )

    # Trazabilidad de organismos
    organismo_origen = models.ForeignKey(
        'Organismo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cambios_originados',
        help_text="Organismo del usuario que realizó el cambio"
    )
    organismo_responsable = models.ForeignKey(
        'Organismo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cambios_recibidos',
        help_text="Organismo responsable del indicador afectado"
    )

    tipo_evento = models.CharField(
        max_length=40,
        choices=TIPO_EVENTO,
        help_text="Tipo de evento que generó el registro"
    )
    fecha = models.DateTimeField(auto_now_add=True)

    # Diff: solo lo que cambió (ligero)
    diff_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Diccionario de cambios: {campo: [antes, despues]}"
    )
    # Snapshot: estado completo del indicador en ese momento (para restaurar)
    snapshot_metadatos = models.JSONField(
        default=dict,
        blank=True,
        help_text="Snapshot completo de metadatos del indicador"
    )

    # Datos asociados (no duplicar Dato, solo referencia de conteo)
    filas_afectadas = models.IntegerField(
        default=0,
        help_text="Número de filas/Dato afectados"
    )
    archivo_relacionado = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Nombre del archivo cargado"
    )

    class Meta:
        ordering = ['-fecha']
        verbose_name = "Registro de Cambio"
        verbose_name_plural = "Registros de Cambios"
        indexes = [
            models.Index(fields=['indicador', '-fecha'], name='registro_indicador_fecha_idx'),
            models.Index(fields=['organismo_responsable', '-fecha'], name='registro_org_resp_fecha_idx'),
            models.Index(fields=['organismo_origen', '-fecha'], name='registro_org_orig_fecha_idx'),
            models.Index(fields=['tipo_evento', '-fecha'], name='registro_tipo_fecha_idx'),
            models.Index(fields=['usuario', '-fecha'], name='registro_usuario_fecha_idx'),
        ]

    def __str__(self):
        return f"{self.get_tipo_evento_display()} — {self.indicador.nombre[:40]} ({self.fecha.strftime('%Y-%m-%d %H:%M')})"

    def resolver_organismo_origen(self):
        """Resuelve el organismo origen a partir del usuario vinculado."""
        if self.usuario:
            perfil = getattr(self.usuario, 'perfil_recolector', None)
            if perfil and perfil.organismo:
                return perfil.organismo
        return None

    def resolver_organismo_responsable(self):
        """Resuelve el organismo responsable a partir del indicador vinculado."""
        if self.indicador and self.indicador.organismo_responsable:
            return self.indicador.organismo_responsable
        return None

    def save(self, *args, **kwargs):
        # Auto-resolver organismos si no están seteados
        if not self.organismo_origen_id:
            org = self.resolver_organismo_origen()
            if org:
                self.organismo_origen = org
        if not self.organismo_responsable_id:
            org = self.resolver_organismo_responsable()
            if org:
                self.organismo_responsable = org
        super().save(*args, **kwargs)


class CalendarioDifusion(models.Model):
    """
    Calendario de Difusión Estadística.
    Registro de productos estadísticos, observatorios y fechas de publicación
    por organismo de la Administración Distrital.
    """
    TIPO_CIFRAS_CHOICES = [
        ('final', 'Final'),
        ('preliminar', 'Preliminar'),
    ]

    PERIODICIDAD_CHOICES = [
        ('mensual', 'Mensual'),
        ('trimestral', 'Trimestral'),
        ('semestral', 'Semestral'),
        ('anual', 'Anual'),
        ('bienal', 'Bienal'),
        ('eventual', 'Eventual'),
    ]

    organismo = models.ForeignKey(
        Organismo,
        on_delete=models.CASCADE,
        related_name='calendario_difusion',
        help_text="Organismo que produce y publica el producto estadístico"
    )

    observatorio = models.CharField(
        max_length=255,
        blank=True,
        help_text="Nombre del observatorio al que pertenece el producto"
    )

    producto = models.TextField(
        help_text="Proceso de producción o nombre del producto estadístico"
    )

    tipo_cifras = models.CharField(
        max_length=20,
        choices=TIPO_CIFRAS_CHOICES,
        default='final',
        help_text="Tipo de cifras publicadas"
    )

    periodicidad = models.CharField(
        max_length=20,
        choices=PERIODICIDAD_CHOICES,
        help_text="Periodicidad de publicación"
    )

    fecha_publicacion = models.CharField(
        max_length=100,
        blank=True,
        help_text="Fecha(s) de publicación esperada (texto libre, ej: '20 de cada mes', 'Abril, Agosto, Diciembre')"
    )

    periodo_referencia = models.CharField(
        max_length=100,
        blank=True,
        help_text="Período de referencia de los datos (ej: '2026', 'dic-26', 'nov-26')"
    )

    activo = models.BooleanField(
        default=True,
        help_text="Si está inactivo no aparecerá en el calendario público"
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Calendario de Difusión"
        verbose_name_plural = "Calendarios de Difusión"
        ordering = ['organismo__nombre', 'observatorio', 'producto']

    def __str__(self):
        return f"{self.organismo.nombre} — {self.producto[:60]}"


# ============================================================================
# CONFIGURACIÓN DEL SISTEMA (chat, embeddings, etc.)
# ============================================================================

class ConfiguracionSistema(models.Model):
    """Almacena configuración dinámica del sistema (chat, APIs, etc.)"""

    clave = models.CharField(
        max_length=100,
        unique=True,
        help_text="Nombre de la variable de configuración (ej: CEREBRAS_MODEL)"
    )
    valor = models.JSONField(
        default=None,
        null=True,
        blank=True,
        help_text="Valor almacenado como JSON (strings, ints, floats, booleans, null)"
    )
    descripcion = models.TextField(
        blank=True,
        help_text="Descripción interna del propósito de esta variable"
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración del Sistema"
        verbose_name_plural = "Configuraciones del Sistema"
        ordering = ['clave']

    def __str__(self):
        return f"{self.clave} = {self.valor}"


# ============================================================================
# MÓDULO DE PRODUCTOS EDUCATIVOS (NIÑOS Y ADOLESCENTES)
# ============================================================================

class ProductoEducativo(models.Model):
    """Producto educativo gamificado derivado de un producto académico técnico"""
    
    PUBLICO_CHOICES = [
        ('infantil', 'Infantil (6-11 años)'),
        ('adolescente', 'Adolescente (12-17 años)'),
    ]
    
    PALETA_CHOICES = [
        ('aventura', 'Aventura de Datos (Infantil)'),
        ('lab', 'Lab de Datos (Adolescente)'),
    ]
    
    NIVEL_GAMIFICACION_CHOICES = [
        ('explorador', 'Explorador'),
        ('aventurero', 'Aventurero'),
        ('cientifico', 'Científico'),
    ]
    
    PERSONAJE_CHOICES = [
        ('don_datico', 'Don Datico (loro estadístico)'),
    ]
    
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('revision', 'En revisión'),
        ('publicado', 'Publicado'),
    ]
    
    id = models.AutoField(primary_key=True)
    
    # Vinculación con producto técnico origen
    producto_origen = models.ForeignKey(
        'ProductoAcademico',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='versiones_educativas',
        help_text="Producto académico técnico del cual deriva este contenido educativo"
    )
    
    # Configuración del público objetivo
    publico = models.CharField(
        max_length=20,
        choices=PUBLICO_CHOICES,
        default='infantil',
        help_text="Público objetivo del producto educativo"
    )
    
    # Identidad visual y narrativa
    titulo = models.CharField(max_length=500, help_text="Título adaptado para el público objetivo")
    slug = models.SlugField(unique=True, help_text="URL amigable")
    resumen_infantil = models.TextField(
        blank=True,
        help_text="Resumen en lenguaje simple y atractivo para el público objetivo"
    )
    imagen_portada = models.ImageField(
        upload_to='productos_educativos/portadas/',
        blank=True,
        null=True,
        help_text="Imagen de portada colorida y atractiva"
    )
    
    # Personaje guía
    personaje_guia = models.CharField(
        max_length=30,
        choices=PERSONAJE_CHOICES,
        default='don_datico',
        help_text="Personaje que guía la experiencia educativa"
    )
    mensaje_bienvenida = models.TextField(
        blank=True,
        help_text="Mensaje de bienvenida del personaje guía"
    )
    
    # Configuración visual
    paleta_colores = models.CharField(
        max_length=20,
        choices=PALETA_CHOICES,
        default='aventura',
        help_text="Paleta de colores del producto"
    )
    
    # Gamificación
    nivel_gamificacion = models.CharField(
        max_length=20,
        choices=NIVEL_GAMIFICACION_CHOICES,
        default='explorador',
        help_text="Nivel de complejidad de las mecánicas de juego"
    )
    tiene_recompensas = models.BooleanField(
        default=True,
        help_text="Habilita sistema de logros y certificados"
    )
    puntos_totales = models.PositiveIntegerField(
        default=100,
        help_text="Puntos totales que se pueden obtener completando el producto"
    )
    
    # Metadatos
    organismo = models.ForeignKey(
        'Organismo',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Organismo responsable"
    )
    temas_relacionados = models.ManyToManyField(
        'MenuSubtema',
        blank=True,
        help_text="Temas estadísticos relacionados"
    )
    palabras_clave = models.CharField(
        max_length=255,
        blank=True,
        help_text="Palabras clave separadas por comas"
    )
    
    # Estado y publicación
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    autor = models.CharField(max_length=255, blank=True, help_text="Autor/adaptador del contenido")
    fecha_publicacion = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Producto Educativo"
        verbose_name_plural = "Productos Educativos"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.titulo} ({self.get_publico_display()})"
    
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('indicadores:producto_educativo', kwargs={'slug': self.slug})


class SeccionEducativa(models.Model):
    """Secciones que componen un Producto Educativo con bloques interactivos"""
    
    TIPO_BLOQUE = [
        ('narrativa_guiada', 'Narrativa guiada (Don Datico explica)'),
        ('texto_adaptado', 'Texto adaptado con ilustraciones'),
        ('dato_interactivo', 'Dato interactivo (KPI animado)'),
        ('grafico_3d_gamificado', 'Gráfico 3D gamificado (ciudad virtual)'),
        ('grafico_interactivo', 'Gráfico interactivo (Plotly educativo)'),
        ('quiz_recompensa', 'Quiz con recompensa'),
        ('actividad_arrastrar', 'Actividad de arrastrar y soltar'),
        ('laboratorio_datos', 'Laboratorio de datos (explorador)'),
        ('mapa_exploracion', 'Mapa de exploración'),
        ('video_educativo', 'Video educativo'),
        ('infografia_animada', 'Infografía animada'),
        ('galeria_imagenes', 'Galería de imágenes'),
        ('reto_final', 'Reto final con certificado'),
    ]
    
    id = models.AutoField(primary_key=True)
    producto = models.ForeignKey(
        ProductoEducativo,
        on_delete=models.CASCADE,
        related_name='secciones'
    )
    
    numero_orden = models.PositiveSmallIntegerField(
        default=0,
        help_text="Orden de aparición en el producto"
    )
    titulo = models.CharField(
        max_length=300,
        help_text="Título de la sección"
    )
    icono_emoji = models.CharField(
        max_length=10,
        blank=True,
        help_text="Emoji representativo (ej: 🎯, 🌟, 🎨)"
    )
    
    tipo_bloque = models.CharField(
        max_length=30,
        choices=TIPO_BLOQUE,
        default='texto_adaptado'
    )
    
    # Contenido principal
    contenido = CKEditor5Field(
        config_name='infraestructura',
        blank=True,
        help_text="Contenido principal del bloque"
    )
    
    # Configuración específica por tipo de bloque
    configuracion_bloque = models.JSONField(
        blank=True,
        null=True,
        help_text='Configuración JSON del bloque: {"pregunta": "...", "opciones": [...], "respuesta_correcta": 0, etc.}'
    )
    
    # Vinculación con datos reales (hereda de ProductoAcademico)
    indicador_vinculado = models.ForeignKey(
        'Indicador',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Indicador a visualizar (para bloques de gráficos/mapas)"
    )
    conjunto_datos_vinculado = models.ForeignKey(
        'ConjuntoDatos',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Conjunto de datos a explorar (para laboratorio de datos)"
    )
    
    # Gamificación
    puntos_seccion = models.PositiveIntegerField(
        default=10,
        help_text="Puntos que otorga completar esta sección"
    )
    tiene_quiz = models.BooleanField(
        default=False,
        help_text="Esta sección incluye un quiz evaluativo"
    )
    
    class Meta:
        verbose_name = "Sección Educativa"
        verbose_name_plural = "Secciones Educativas"
        ordering = ['numero_orden']
    
    def __str__(self):
        return f"{self.numero_orden}. {self.titulo}"


class LogroEducativo(models.Model):
    """Logros/insignias que se pueden obtener al completar productos educativos"""
    
    TIPO_LOGRO = [
        ('completar_producto', 'Completar producto completo'),
        ('quiz_perfecto', 'Quiz perfecto (100% aciertos)'),
        ('explorador_rapido', 'Explorador rápido (tiempo récord)'),
        ('coleccionista_datos', 'Coleccionista de datos (todos los chontaduros)'),
        ('cientifico_junior', 'Científico junior (nivel avanzado)'),
    ]
    
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=200, help_text="Nombre del logro")
    descripcion = models.TextField(help_text="Descripción del logro")
    tipo = models.CharField(max_length=30, choices=TIPO_LOGRO, default='completar_producto')
    icono_emoji = models.CharField(
        max_length=10,
        default='🏆',
        help_text="Emoji del logro (ej: 🏆, 🎖️, ⭐)"
    )
    puntos_requeridos = models.PositiveIntegerField(
        default=100,
        help_text="Puntos necesarios para desbloquear este logro"
    )
    
    class Meta:
        verbose_name = "Logro Educativo"
        verbose_name_plural = "Logros Educativos"
        ordering = ['puntos_requeridos']
    
    def __str__(self):
        return f"{self.icono_emoji} {self.nombre}"


class ProgresoUsuarioEducativo(models.Model):
    """Seguimiento del progreso de un usuario en productos educativos (opcional, requiere autenticación)"""
    
    id = models.AutoField(primary_key=True)
    # Si el sistema tiene usuarios autenticados, descomentar:
    # usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    session_key = models.CharField(
        max_length=100,
        help_text="Clave de sesión para usuarios anónimos"
    )
    producto = models.ForeignKey(ProductoEducativo, on_delete=models.CASCADE)
    
    secciones_completadas = models.ManyToManyField(
        SeccionEducativa,
        blank=True,
        help_text="Secciones que el usuario ha completado"
    )
    puntos_obtenidos = models.PositiveIntegerField(default=0)
    logros_desbloqueados = models.ManyToManyField(
        LogroEducativo,
        blank=True,
        help_text="Logros que el usuario ha desbloqueado"
    )
    
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_ultima_actividad = models.DateTimeField(auto_now=True)
    completado = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Progreso de Usuario"
        verbose_name_plural = "Progresos de Usuarios"
        # Si se usa usuario autenticado: unique_together = [['usuario', 'producto']]
        unique_together = [['session_key', 'producto']]
    
    def __str__(self):
        return f"Progreso en {self.producto.titulo} - {self.puntos_obtenidos} pts"


class PageVisit(models.Model):
    """
    Registro de visitas a páginas del sitio.
    """
    path = models.CharField(max_length=2048, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    referer = models.URLField(max_length=2048, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Visita a página"
        verbose_name_plural = "Visitas a páginas"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['path', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
        ]

    def __str__(self):
        user_label = self.user.username if self.user else 'Anónimo'
        return f"{self.path} — {user_label} @ {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class CatalogoDominio(models.Model):
    """
    Catálogo de datos asociado a un dominio de desagregación.
    Permite publicar directorios/listados de referencia (ej: hospitales,
    teatros, colegios) como archivos CSV o Excel visibles en el sitio.
    """
    id = models.AutoField(primary_key=True)
    dominio = models.ForeignKey(
        DominioDesagregacion, on_delete=models.CASCADE,
        related_name='catalogos',
        help_text="Dominio de desagregación al que pertenece este catálogo"
    )
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    archivo = models.FileField(
        upload_to='catalogos_dominios/',
        help_text="Archivo de datos del catálogo (CSV o Excel .xlsx/.xls)"
    )
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Catálogo de Dominio"
        verbose_name_plural = "Catálogos de Dominios"
        ordering = ['dominio__nombre', 'orden', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.dominio.nombre})"

    @property
    def extension(self):
        nombre = self.archivo.name if self.archivo else ''
        return nombre.rsplit('.', 1)[-1].lower() if '.' in nombre else ''


class CatalogoConsulta(models.Model):
    """
    Conjunto de datos del catálogo de consulta: directorios y listados de
    referencia (nomencladores, directorios con contacto, inventarios de
    capacidad instalada, fichas técnicas territoriales) que antes vivían
    impresos en el anuario "Cali en Cifras".

    NO confundir con CatalogoDominio (el futuro "catálogo de datos"): este
    módulo es el catálogo de consulta, agrupado bajo los dominios visibles
    del menú de indicadores (los 4 activos).

    Un indicador puede enlazarse a un conjunto mediante Indicador.catalogo_consulta:
    conserva toda su metadata y su lugar en la taxonomía CEC, pero en lugar de
    consultar Datos renderiza el cuadro de consulta de este conjunto.
    """
    TIPO_NOMENCLADOR = 'nomenclador'
    TIPO_DIRECTORIO = 'directorio'
    TIPO_CAPACIDAD = 'capacidad'
    TIPO_FICHA = 'ficha_territorial'
    TIPOS_CONSULTA = [
        (TIPO_NOMENCLADOR, 'Nomenclador (código ↔ territorio)'),
        (TIPO_DIRECTORIO, 'Directorio (ubicación y contacto)'),
        (TIPO_CAPACIDAD, 'Inventario de capacidad instalada'),
        (TIPO_FICHA, 'Ficha técnica territorial'),
    ]

    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    tipo_consulta = models.CharField(
        max_length=20, choices=TIPOS_CONSULTA, default=TIPO_DIRECTORIO,
        help_text="Clasificación técnica del conjunto: define el layout del cuadro de consulta"
    )
    dominio = models.ForeignKey(
        MenuDominio, on_delete=models.PROTECT,
        related_name='catalogos_consulta',
        limit_choices_to={'activo': True},
        help_text="Dominio visible del menú de indicadores bajo el que se publica"
    )
    archivo = models.FileField(
        upload_to='catalogo_consulta/', blank=True, null=True,
        help_text="Archivo fuente del conjunto (CSV o Excel .xlsx/.xls)"
    )
    columnas = models.JSONField(
        default=list, blank=True,
        help_text="Nombres de columnas del cuadro de consulta (orden de la tabla)"
    )
    filas = models.JSONField(
        default=list, blank=True,
        help_text="Filas del cuadro: lista de objetos {columna: valor}"
    )
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conjunto del Catálogo de Consulta"
        verbose_name_plural = "Catálogo de Consulta"
        ordering = ['dominio__orden', 'orden', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.dominio.nombre})"

    @property
    def extension(self):
        nombre = self.archivo.name if self.archivo else ''
        return nombre.rsplit('.', 1)[-1].lower() if '.' in nombre else ''

    @property
    def total_filas(self):
        return len(self.filas or [])


# ======================================================================
# MÓDULO TALLER DE GESTIÓN DE DATOS INSTITUCIONALES + CATÁLOGO DE DATOS (portado de formulario/)
# Se importan aquí para que makemigrations los detecte sin depender del
# orden de autodiscovery del admin.
# ======================================================================
from .models_taller import (  # noqa: E402,F401
    OpcionTaller, InscripcionTaller, RetoAnalisis, FuenteRequerida,
)
from .models_catalogo import (  # noqa: E402,F401
    FuenteDatos, FuenteOrigen, VariableFuente, EvaluacionSeguridad,
    BaseCatalogo, CampoCatalogo,
)
