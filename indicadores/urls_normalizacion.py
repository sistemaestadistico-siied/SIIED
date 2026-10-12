"""URLconf del Wizard de Normalización de Desagregaciones.

Se incluye en myproject/urls.py ANTES de `admin.site.urls` para que
`/admin/normalizacion-desagregaciones/` no caiga en el catch-all del admin.
El app_name 'indicadores' conserva el namespace de las plantillas.
"""

from django.urls import path
from . import views_normalizacion

app_name = 'indicadores'

urlpatterns = [
    path('', views_normalizacion.wizard_normalizacion, name='wizard_normalizacion'),
    path('equivalencias/', views_normalizacion.wizard_equivalencias, name='wizard_normalizacion_equivalencias'),
    path('preview/', views_normalizacion.wizard_preview, name='wizard_normalizacion_preview'),
    path('aplicar/', views_normalizacion.wizard_aplicar, name='wizard_normalizacion_aplicar'),
    path('eliminar/', views_normalizacion.wizard_eliminar_aplicar, name='wizard_normalizacion_eliminar'),
    path('dominio/<int:dominio_id>/', views_normalizacion.wizard_dominio_detalle, name='wizard_normalizacion_dominio'),
]
