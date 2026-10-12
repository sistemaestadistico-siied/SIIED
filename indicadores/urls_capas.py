"""URLconf del Wizard de Carga de Capas Geográficas.

Se incluye en myproject/urls.py ANTES de `admin.site.urls` (catch-all).
El app_name 'indicadores' conserva el namespace de las plantillas.
"""

from django.urls import path
from . import views_capas

app_name = 'indicadores'

urlpatterns = [
    path('', views_capas.wizard_capas, name='wizard_capas'),
    path('asociar/', views_capas.wizard_capas_asociar, name='wizard_capas_asociar'),
    path('aplicar/', views_capas.wizard_capas_aplicar, name='wizard_capas_aplicar'),
]
