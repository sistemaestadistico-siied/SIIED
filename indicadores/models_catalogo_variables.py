"""
Modelos del Catálogo de Variables (ex aplicación PHP de planestadistico.cali.gov.co).

Reconstruye la base `pet_catalogo` (9 tablas) como parte del módulo SIIED.
El prefijo CV (Catálogo de Variables) evita colisiones con los modelos del
catálogo de conjuntos de datos (models_catalogo.py).
"""

from django.db import models


class CVAreaInformacion(models.Model):
    id_area = models.AutoField(primary_key=True)
    nombre_area = models.CharField(max_length=20, unique=True)
    descripcion_area = models.TextField()

    class Meta:
        db_table = 'cv_areas_informacion'
        verbose_name = 'Área de información'
        verbose_name_plural = 'Áreas de información'
        ordering = ['nombre_area']

    def __str__(self):
        return self.nombre_area


class CVUnidadAnalisis(models.Model):
    id_unidad_analisis = models.AutoField(primary_key=True)
    nombre_unidad_analisis = models.CharField(max_length=10, unique=True)

    class Meta:
        db_table = 'cv_unidades_analisis'
        verbose_name = 'Unidad de análisis'
        verbose_name_plural = 'Unidades de análisis'
        ordering = ['nombre_unidad_analisis']

    def __str__(self):
        return self.nombre_unidad_analisis


class CVTipoDato(models.Model):
    id_tipo_dato = models.AutoField(primary_key=True)
    nombre_tipo_dato = models.CharField(max_length=15)

    class Meta:
        db_table = 'cv_tipos_datos'
        verbose_name = 'Tipo de dato'
        verbose_name_plural = 'Tipos de datos'
        ordering = ['nombre_tipo_dato']

    def __str__(self):
        return self.nombre_tipo_dato


class CVTipoVariableEstadistica(models.Model):
    id_tipo_variable = models.AutoField(primary_key=True)
    nombre_tipo_variable = models.CharField(max_length=30)

    class Meta:
        db_table = 'cv_tipos_variables_estadisticas'
        verbose_name = 'Tipo de variable estadística'
        verbose_name_plural = 'Tipos de variables estadísticas'
        ordering = ['nombre_tipo_variable']

    def __str__(self):
        return self.nombre_tipo_variable


class CVTipoValoresDominio(models.Model):
    id_tipo_valores_dominio = models.AutoField(primary_key=True)
    nombre_tipo_valores_dominio = models.CharField(max_length=20)
    longitud_tipo_valores_dominio = models.IntegerField(default=0)

    class Meta:
        db_table = 'cv_tipos_valores_dominio'
        verbose_name = 'Tipo de valores de dominio'
        verbose_name_plural = 'Tipos de valores de dominio'
        ordering = ['nombre_tipo_valores_dominio']

    def __str__(self):
        return self.nombre_tipo_valores_dominio


class CVGeografia(models.Model):
    """Geografías de referencia del catálogo (barrio, comuna, etc.)."""
    id_geografia = models.AutoField(primary_key=True)
    tipo_geografia = models.CharField(max_length=20)
    codigo_geografia = models.IntegerField()
    geografia_padre = models.CharField(max_length=200, blank=True, default='')
    nombre_geografia = models.CharField(max_length=200)

    class Meta:
        db_table = 'cv_geografias'
        verbose_name = 'Geografía'
        verbose_name_plural = 'Geografías'
        ordering = ['tipo_geografia', 'nombre_geografia']

    def __str__(self):
        return f'{self.nombre_geografia} ({self.tipo_geografia})'


class CVVariable(models.Model):
    """Variable estadística del catálogo (ficha completa)."""
    id_variable = models.CharField(primary_key=True, max_length=20)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField()

    unidad_analisis = models.ForeignKey(
        CVUnidadAnalisis, on_delete=models.PROTECT,
        db_column='id_unidad_analisis', related_name='variables')
    tipo_dato = models.ForeignKey(
        CVTipoDato, on_delete=models.PROTECT,
        db_column='id_tipo_dato', related_name='variables')
    tipo_variable_estadistica = models.ForeignKey(
        CVTipoVariableEstadistica, on_delete=models.PROTECT,
        db_column='id_tipo_variable_estadistica', related_name='variables')
    area_informacion = models.ForeignKey(
        CVAreaInformacion, on_delete=models.PROTECT,
        db_column='id_area_informacion', related_name='variables',
        null=True, blank=True)
    tipo_valores = models.ForeignKey(
        CVTipoValoresDominio, on_delete=models.PROTECT,
        db_column='id_tipo_valores', related_name='variables', null=True, blank=True)

    llave_primaria = models.CharField(max_length=2, blank=True, default='')
    campo_obligatorio = models.CharField(max_length=2, blank=True, default='')
    longitud_campo = models.CharField(max_length=10, blank=True, default='')
    reglas_consistencia = models.TextField(blank=True, default='')
    reglas_validacion_lenguaje_natural = models.TextField(blank=True, default='')
    forma_pregunta = models.TextField(blank=True, default='')
    opciones_respuesta = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'cv_variables'
        verbose_name = 'Variable del catálogo'
        verbose_name_plural = 'Variables del catálogo'
        ordering = ['id_variable']

    def __str__(self):
        return f'{self.id_variable}: {self.nombre}'

    @property
    def es_llave_primaria(self):
        return self.llave_primaria.strip().upper() in ('SI', 'SÍ', 'S', '1')

    @property
    def es_obligatorio(self):
        return self.campo_obligatorio.strip().upper() in ('SI', 'SÍ', 'S', '1')


class CVValor(models.Model):
    """Valor de dominio de una variable (catálogos de respuesta)."""
    id_valor = models.AutoField(primary_key=True)
    descripcion_valor = models.TextField()
    variable = models.ForeignKey(
        CVVariable, on_delete=models.CASCADE,
        db_column='id_variable', related_name='valores')

    class Meta:
        db_table = 'cv_valores'
        verbose_name = 'Valor de dominio'
        verbose_name_plural = 'Valores de dominio'

    def __str__(self):
        return self.descripcion_valor[:60]


class CVNoticia(models.Model):
    """Noticias del antiguo portal del plan estadístico (histórico)."""
    id_noticia = models.AutoField(primary_key=True)
    titulo_noticia = models.CharField(max_length=200)
    anho_noticia = models.IntegerField(null=True, blank=True)
    fecha_noticia = models.DateField(null=True, blank=True)
    texto_noticia = models.TextField(blank=True, default='')
    carpeta_imagenes_noticia = models.TextField(blank=True, default='')
    imagenes_noticia = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'cv_noticias'
        verbose_name = 'Noticia histórica del plan estadístico'
        verbose_name_plural = 'Noticias históricas del plan estadístico'
        ordering = ['-fecha_noticia']

    def __str__(self):
        return self.titulo_noticia
