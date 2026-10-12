"""URLconf del Wizard de Carga de Capas Geográficas.

Se incluye en myproject/urls.py ANTES de `admin.site.urls` (catch-all).
Namespace propio ('capas') para no duplicar el de la app principal (urls.W005).
"""

from django.urls import path
from . import views_capas

app_name = 'capas'

urlpatterns = [
    path('', views_capas.wizard_capas, name='wizard_capas'),
    path('asociar/', views_capas.wizard_capas_asociar, name='wizard_capas_asociar'),
    path('aplicar/', views_capas.wizard_capas_aplicar, name='wizard_capas_aplicar'),
]
