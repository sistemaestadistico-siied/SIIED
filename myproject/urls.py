"""myproject URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.urls import re_path
from indicadores import views, views_monitoring, views_chat_config, views_recoleccion, views_satisfaccion

urlpatterns = [
    # URLs de monitoreo (antes del admin)
    path('admin/monitoring', views_monitoring.monitoring_dashboard, name='monitoring_dashboard'),
    path('admin/monitoring/', views_monitoring.monitoring_dashboard, name='monitoring_dashboard_slash'),
    path('admin/monitoring/api/system-stats/', views_monitoring.api_system_stats, name='api_system_stats'),
    path('admin/monitoring/api/cache-metrics/', views_monitoring.api_cache_metrics, name='api_cache_metrics'),
    path('admin/monitoring/api/data-quality/', views_monitoring.api_data_quality, name='api_data_quality'),
    path('admin/monitoring/api/performance-trends/', views_monitoring.api_performance_trends, name='api_performance_trends'),
    path('admin/monitoring/api/page-visits-stats/', views_monitoring.api_page_visits_stats, name='api_page_visits_stats'),
    path('admin/monitoring/api/page-visits-recent/', views_monitoring.api_page_visits_recent, name='api_page_visits_recent'),
    
    # URLs de configuración del chat (antes del admin)
    path('admin/chat-config/', views_chat_config.chat_config_view, name='admin_chat_config'),
    path('admin/chat-contexts/', views_chat_config.chat_contexts_view, name='admin_chat_contexts'),
    path('admin/chat-suggestions/', views_chat_config.chat_suggestions_view, name='admin_chat_suggestions'),
    path('admin/update-embeddings/', views_chat_config.update_embeddings_view, name='admin_update_embeddings'),
    
    # Workspace unificado y Wizard Admin
    path('workspace/', views.workspace_dashboard, name='workspace_dashboard'),
    path('admin/wizard/dashboard/', views_recoleccion.wizard_dashboard, name='wizard_dashboard'),
    path('admin/wizard/', views_recoleccion.wizard_admin_unificado, name='wizard_admin_unificado'),
    path('admin/wizard/diagnostico-ajax/', views_recoleccion.wizard_diagnostico_ajax, name='wizard_diagnostico_ajax'),
    path('admin/wizard/solicitar-correccion/<int:carga_id>/', views_recoleccion.wizard_solicitar_correccion, name='wizard_solicitar_correccion'),

    # Reiniciar servicios (Admin) - Antes del admin para evitar conflictos
    path('admin/restart-services/', views_recoleccion.restart_services, name='restart_services'),
    
    # URLs de satisfacción (antes del admin para evitar conflictos)
    path('admin/satisfaccion/dashboard/', views_satisfaccion.satisfaccion_dashboard, name='satisfaccion_dashboard'),
    path('admin/satisfaccion/organismos/', views_satisfaccion.satisfaccion_organismos, name='satisfaccion_organismos'),
    path('admin/satisfaccion/organismos/<int:organismo_id>/editar/', views_satisfaccion.satisfaccion_organismo_editar, name='satisfaccion_organismo_editar'),
    path('admin/satisfaccion/exportar/', views_satisfaccion.satisfaccion_exportar, name='satisfaccion_exportar'),
    path('admin/satisfaccion/exportar-rapidas-csv/', views_satisfaccion.exportar_respuestas_rapidas_csv, name='exportar_respuestas_rapidas_csv'),
    path('admin/satisfaccion/exportar-completas-csv/', views_satisfaccion.exportar_respuestas_completas_csv, name='exportar_respuestas_completas_csv'),
    
    # Wizard de Normalización de Desagregaciones (antes del admin para no caer en catch_all_view)
    path('admin/normalizacion-desagregaciones/', include('indicadores.urls_normalizacion', namespace='indicadores')),
    # Wizard de Carga de Capas Geográficas
    path('admin/cargar-capa-geo/', include('indicadores.urls_capas', namespace='indicadores')),

    # CKEditor y Admin
    path('ckeditor5/', include('django_ckeditor_5.urls')),
    path('admin/', admin.site.urls),
    
    # URLs de la aplicación indicadores
    path('', include('indicadores.urls', namespace='indicadores')),
]

# Configuración para servir archivos estáticos y de medios en desarrollo
if settings.DEBUG:
    # Servir archivos estáticos en desarrollo
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # Servir archivos de medios en desarrollo
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # En producción, WhiteNoise se encargará de los archivos estáticos
    # Solo necesitamos servir archivos de medios
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {
            'document_root': settings.MEDIA_ROOT,
        }),
    ]
