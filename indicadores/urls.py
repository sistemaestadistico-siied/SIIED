from django.urls import path, include, register_converter
from django.conf import settings
from django.conf.urls.static import static

from . import views
from . import views_monitoring
from . import views_recoleccion
from . import views_reportes
from . import views_satisfaccion
from . import views_delegado
from . import views_validacion
from . import views_iced
from . import views_educativos
from . import views_editorial
from . import views_taller
from . import views_catalogo

# Custom path converter for organismo codes with accented characters
class OrganismoCodeConverter:
    regex = r'[a-zA-ZáéíóúñüÁÉÍÓÚÑÜ0-9_-]+'
    
    def to_python(self, value):
        return value
    
    def to_url(self, value):
        return value

register_converter(OrganismoCodeConverter, 'orgcode')

app_name = 'indicadores'

urlpatterns = [
    path('', views.home, name='home'),
    path('acceso-modulos/', views.acceso_modulos, name='acceso_modulos'),
    path('dominio/', views.dominios, name='dominios'),
    path('modelo/', views.modelo_datos, name='modelo_datos'),
    path('presentacion/', views.presentacion, name='presentacion'),
    path('documentacion/', views.documentacion, name='documentacion'),
    path('dominio/<slug:slug>/', views.dominio_detalle, name='dominio_detalle'),
    path('dominio/<slug:dominio_slug>/<slug:tema_slug>/', views.tema_detalle, name='tema_detalle'),
    path('dominio/<slug:dominio_slug>/<slug:tema_slug>/<slug:subtema_slug>/', views.subtema_detalle, name='subtema_detalle'),
    path('dominios/<slug:tema_slug>/<slug:subtema_slug>/', views.subtema_detalle_2, name='subtema_detalle_2'),
    path('dominio/<slug:dominio_slug>/<slug:tema_slug>/<slug:subtema_slug>/3d/', views.subtema_detalle_3d, name='subtema_detalle_3d'),
    # URLs para versiones 3D
    path('dominios-3d/', views.dominios_3d, name='dominios_3d'),
    path('dominios-3d/<slug:slug>/', views.dominio_detalle_3d, name='dominio_detalle_3d'),
    path('dominios-3d/<slug:dominio_slug>/<slug:tema_slug>/', views.tema_detalle_3d, name='tema_detalle_3d'),
    path('inventario-operaciones/', views.inventario_operaciones, name='inventario_operaciones'),
    path('inventario-operaciones/<int:pk>/', views.operacion_detalle, name='operacion_detalle'),
    path('visor-comparativo/', views.visor_comparativo, name='visor_comparativo'),
    path('sistemas-informacion/', views.sistemas_informacion, name='sistemas_informacion'),
    path('catalogos/', views.catalogos_dominios, name='catalogos_dominios'),
    path('catalogos/<int:pk>/', views.catalogo_detalle, name='catalogo_detalle'),
    # Catálogo de Consulta (directorios/listados de referencia, ex-anuario CEC)
    path('catalogo-consulta/', views.catalogo_consulta_listado, name='catalogo_consulta_listado'),
    path('catalogo-consulta/<int:pk>/', views.catalogo_consulta_detalle, name='catalogo_consulta_detalle'),
    path('proyectos-informacion/', views.proyectos_informacion, name='proyectos_informacion'),
    path('aliado/<slug:slug>/', views.aliado_detalle, name='aliado_detalle'),
    path('eventos/', views.eventos_lista, name='eventos'),
    path('evento/<slug:slug>/', views.evento_detalle, name='evento_detalle'),
    path('noticias/', views.noticias_lista, name='noticias_lista'),
    # URLs para Infraestructura de Información
    path('infraestructura/', views.infraestructura_index, name='infraestructura_index'),
    path('infraestructura/<slug:area_slug>/', views.infraestructura_area, name='infraestructura_area'),
    path('infraestructura/<slug:area_slug>/<slug:categoria_slug>/', views.infraestructura_categoria, name='infraestructura_categoria'),
    path('infraestructura/<slug:area_slug>/<slug:categoria_slug>/<slug:subcategoria_slug>/', views.infraestructura_subcategoria, name='infraestructura_subcategoria'),
    path('infraestructura/<slug:area_slug>/<slug:categoria_slug>/<slug:subcategoria_slug>/<slug:grupo_slug>/', views.infraestructura_grupo, name='infraestructura_grupo'),
    path('infraestructura/<slug:area_slug>/<slug:categoria_slug>/<slug:subcategoria_slug>/<slug:grupo_slug>/<slug:documento_slug>/', views.infraestructura_documento, name='infraestructura_documento'),
    # Productos Académicos
    path('productos-academicos/<slug:slug>/', views.producto_academico, name='producto_academico'),
    # Productos Educativos (Niños y Adolescentes)
    path('educativos/<slug:slug>/', views_educativos.producto_educativo, name='producto_educativo'),
    path('api/educativos/completar-seccion/<int:seccion_id>/', views_educativos.api_completar_seccion, name='api_completar_seccion_educativa'),
    path('api/educativos/responder-quiz/<int:seccion_id>/', views_educativos.api_responder_quiz, name='api_responder_quiz_educativo'),
    path('api/educativos/progreso/<slug:producto_slug>/', views_educativos.api_progreso_usuario, name='api_progreso_educativo'),
    # Visualizador de Microdatos (eliminado)
    path('api/conjuntos-datos/list/', views.api_conjunto_datos_list, name='api_conjunto_datos_list'),
    path('api/conjuntos-datos/rows/', views.api_conjunto_datos_rows, name='api_conjunto_datos_rows'),
    path('api/conjuntos-datos/headers/', views.api_conjunto_datos_headers, name='api_conjunto_datos_headers'),
    path('api/get_dominios/', views.get_dominios, name='get_dominios'),
    path('api/get_temas/', views.get_temas, name='get_temas'),
    path('api/get_subtemas/', views.get_subtemas, name='get_subtemas'),
    path('api/get_dominios_desagregacion/', views.get_dominios_desagregacion, name='get_dominios_desagregacion'),
    path('api/get_indicadores/', views.get_indicadores, name='get_indicadores'),
    path('api/get_indicadores_simple/', views.get_indicadores_simple, name='get_indicadores_simple'),
    # API endpoints
    path('api/get_graficos/<int:indicador_id>/', views.get_graficos, name='api_get_graficos'),
    path('api/get_grafico/<int:grafico_id>/', views.get_grafico, name='api_get_grafico'),
    path('api/get_desagregaciones/<int:indicador_id>/', views.get_desagregaciones, name='api_get_desagregaciones'),
    path('api/get_mapa/<int:indicador_id>/', views.get_mapa, name='api_get_mapa'),
    path('api/geojson/indicador/<int:indicador_id>/', views.geojson_indicador, name='api_geojson_indicador'),
    path('api/get_datos_indicadores/', views.get_datos_indicadores, name='api_get_datos_indicadores'),
    path('api/get_niveles_geograficos/', views.get_niveles_geograficos, name='api_get_niveles_geograficos'),
    path('api/get_capas_geograficas/', views.get_capas_geograficas, name='api_get_capas_geograficas'),
    path('api/wizard/contar-series-grafico/', views.api_contar_series_grafico, name='api_contar_series_grafico'),
    path('api/wizard/validar-datos/', views.api_validar_datos, name='api_validar_datos'),
    path('api/test_valores_geo/<int:indicador_id>/', views.test_valores_geo, name='api_test_valores_geo'),
    path('api/valores_geo/<int:indicador_id>/', views.valores_geo, name='api_valores_geo'),
    # Monitoring dashboard - URLs removidas de aquí para evitar duplicados
    # Support both indicador_id and conjunto_datos_id parameters
    path('api/get_conjuntos-datos_csv/indicador/<int:indicador_id>/', views.get_conjunto_datos_csv, name='get_conjunto_datos_csv_indicador'),
    path('api/get_conjuntos-datos_csv/conjuntos-datos/<int:conjunto_datos_id>/', views.get_conjunto_datos_csv, name='get_conjunto_datos_csv_conjunto'),
    # Keep the old URL for backward compatibility
    path('api/get_conjuntos-datos_csv/<int:indicador_id>/', views.get_conjunto_datos_csv, name='get_conjunto_datos_csv'),
    # Ficha técnica de conjunto_datos
    path('api/ficha-tecnica-conjuntos-datos/<int:indicador_id>/', views.get_ficha_tecnica_conjunto_datos, name='get_ficha_tecnica_conjunto_datos'),
    # Comentadas temporalmente - funciones no existen
    # path('api/get_unified_data/<int:indicador_id>/', views.get_unified_visualization_data, name='unified_visualization_data'),
    # path('api/unified_geo/<int:indicador_id>/', get_unified_geo_data, name='unified_geo_data'),
    # Procesos en vivo (logs en tiempo real por polling)
    path('admin/procesos/', views.admin_procesos_dashboard, name='admin_procesos_dashboard'),
    path('procesos/<int:proceso_id>/', views.proceso_en_vivo, name='proceso_en_vivo'),
    path('api/procesos/<int:proceso_id>/status/', views.api_proceso_status, name='api_proceso_status'),
    path('api/procesos/<int:proceso_id>/logs/', views.api_proceso_logs, name='api_proceso_logs'),
    # API Documentation
    path('api-documentation/', views.api_documentation, name='api_documentation'),
    # conjunto_datos views
    path('conjuntos-datos/indicador/<int:indicador_id>/', views.conjunto_datos_detalle, name='conjunto_datos_detalle'),
    path('conjuntos-datos/explorer/', views.conjuntos_datos_explorer, name='conjuntos_datos_explorer'),
    path('api/conjuntos-datos/datasets/', views.api_conjunto_datos_datasets, name='api_conjunto_datos_datasets'),
    path('api/conjuntos-datos/datasets/hierarchical/', views.api_conjunto_datos_datasets_hierarchical, name='api_conjunto_datos_datasets_hierarchical'),
    path('api/datasets/all/', views.api_conjunto_datos_all, name='api_conjunto_datos_all'),
    path('api/conjuntos-datos/<int:conjunto_datos_id>/', views.api_conjunto_datos_detail, name='api_conjunto_datos_detail'),


    # Reiniciar servicios (Admin)
    path('admin/restart-services/', views_recoleccion.restart_services, name='restart_services'),

    # Chat
    path('chat/', views.chat_view, name='chat'),
    path('chat/message/', views.chat_message, name='chat_message'),
    path('chat/stream/', views.chat_stream, name='chat_stream'),
    path('chat/suggestions/', views.chat_suggestions, name='chat_suggestions'),
    path('tts/', views.text_to_speech, name='tts'),

    # Busqueda semántica
    path('api/buscar/', views.buscar_semantico, name='buscar_semantico'),
    path('api/buscar_indicadores/', views.api_buscar_indicadores, name='api_buscar_indicadores'),
    path('api/indicador-metadata/', views.api_indicador_metadata, name='api_indicador_metadata'),
    path('api/grafico-seccion/', views.api_get_grafico_seccion, name='api_get_grafico_seccion'),

    # ========================================================================
    # MÓDULO DE RECOLECCIÓN Y REPORTES
    # ========================================================================
    
    # Autenticación
    path('recoleccion/login/', views_recoleccion.recoleccion_login, name='recoleccion_login'),
    path('recoleccion/logout/', views_recoleccion.recoleccion_logout, name='recoleccion_logout'),
    
    # Dashboard
    path('recoleccion/', views_recoleccion.recoleccion_dashboard, name='recoleccion_dashboard'),
    
    # Carga de series de indicadores
    path('recoleccion/cargar-serie/', views_recoleccion.cargar_serie_indicador, name='cargar_serie_indicador'),
    path('recoleccion/serie/<int:carga_id>/', views_recoleccion.detalle_carga_serie, name='detalle_carga_serie'),
    path('recoleccion/historial-series/', views_recoleccion.historial_cargas_series, name='historial_cargas_series'),
    
    # Carga masiva de series
    path('recoleccion/cargar-masiva/', views_recoleccion.cargar_masiva_series, name='cargar_masiva_series'),
    path('recoleccion/masiva/<int:carga_masiva_id>/revisar/', views_recoleccion.revisar_masiva, name='revisar_masiva'),
    path('recoleccion/masiva/<int:carga_masiva_id>/graficos/', views_recoleccion.configurar_graficos_masiva, name='configurar_graficos_masiva'),
    path('recoleccion/masiva/<int:carga_masiva_id>/confirmar/', views_recoleccion.confirmar_masiva, name='confirmar_masiva'),
    path('recoleccion/api/indicadores/', views_recoleccion.buscar_indicadores_masiva, name='buscar_indicadores_masiva'),
    path('recoleccion/catalogos/dominios/', views_recoleccion.descargar_catalogo_dominios, name='descargar_catalogo_dominios'),
    
    # Deconstruir tabla dinámica
    path('recoleccion/deconstruir-tabla/', views_recoleccion.deconstruir_tabla, name='deconstruir_tabla'),
    
    # Creación simplificada de gráficos
    path('recoleccion/crear-grafico/<int:indicador_id>/', views_recoleccion.crear_grafico_simplificado, name='crear_grafico_simplificado'),
    
    # Carga de conjunto_datos
    path('recoleccion/cargar-conjuntos-datos/', views_recoleccion.cargar_conjunto_datos, name='cargar_conjunto_datos'),
    path('recoleccion/conjuntos-datos/<int:carga_id>/', views_recoleccion.detalle_carga_conjunto_datos, name='detalle_carga_conjunto_datos'),
    path('recoleccion/historial-conjuntos-datos/', views_recoleccion.historial_cargas_conjuntos_datos, name='historial_cargas_conjuntos_datos'),
    
    # Reportes - Indicadores
    path('recoleccion/reportes/indicadores/', views_recoleccion.reportes_indicadores, name='reportes_indicadores'),
    path('recoleccion/reportes/indicadores/<int:indicador_id>/datos/', views_recoleccion.descargar_datos_indicador, name='descargar_datos_indicador'),
    path('recoleccion/reportes/indicadores/datos-masivo/', views_recoleccion.descargar_datos_indicador, name='descargar_datos_indicador_masivo'),
    path('recoleccion/reportes/indicadores/<int:indicador_id>/metadata/', views_recoleccion.descargar_metadata_indicador, name='descargar_metadata_indicador'),
    path('recoleccion/reportes/indicadores/metadata-masivo/', views_recoleccion.descargar_metadata_indicador, name='descargar_metadata_indicador_masivo'),
    
    # Reportes - conjunto_datos
    path('recoleccion/reportes/conjuntos-datos/', views_recoleccion.reportes_conjuntos_datos, name='reportes_conjuntos_datos'),
    path('recoleccion/reportes/conjuntos-datos/<int:conjunto_datos_id>/datos/', views_recoleccion.descargar_conjunto_datos, name='descargar_conjunto_datos'),
    path('recoleccion/reportes/conjuntos-datos/<int:conjunto_datos_id>/metadata/', views_recoleccion.descargar_metadata_variables, name='descargar_metadata_variables'),
    
    # Ingreso inline y formularios web (complementario a carga por archivo)
    path('recoleccion/serie-inline/', views_recoleccion.cargar_serie_inline, name='cargar_serie_inline'),
    path('recoleccion/metadata-form/', views_recoleccion.cargar_metadata_form, name='cargar_metadata_form'),
    path('recoleccion/variables-form/', views_recoleccion.cargar_variables_form, name='cargar_variables_form'),
    path('recoleccion/actualizar-existente/', views_recoleccion.actualizar_existente, name='actualizar_existente'),

    # Plantillas de ejemplo e instrucciones
    path('recoleccion/plantillas/serie-datos/', views_recoleccion.descargar_plantilla_serie_datos, name='descargar_plantilla_serie_datos'),
    path('recoleccion/plantillas/metadata-indicador/', views_recoleccion.descargar_plantilla_metadata_indicador, name='descargar_plantilla_metadata_indicador'),
    path('recoleccion/plantillas/masiva-datos/', views_recoleccion.descargar_plantilla_masiva_datos, name='descargar_plantilla_masiva_datos'),
    path('recoleccion/plantillas/masiva-metadata/', views_recoleccion.descargar_plantilla_masiva_metadata, name='descargar_plantilla_masiva_metadata'),
    path('recoleccion/plantillas/conjuntos-datos/', views_recoleccion.descargar_plantilla_conjunto_datos, name='descargar_plantilla_conjunto_datos'),
    path('recoleccion/plantillas/metadata-variables/', views_recoleccion.descargar_plantilla_metadata_variables, name='descargar_plantilla_metadata_variables'),
    path('recoleccion/instrucciones-conjuntos-datos/', views_recoleccion.instrucciones_conjuntos_datos, name='instrucciones_conjuntos_datos'),
    path('recoleccion/manual/', views_recoleccion.recoleccion_manual, name='recoleccion_manual'),

    # Dashboard Admin - Cargas del equipo
    path('dashboard-cargas/', views_recoleccion.admin_cargas_dashboard, name='cargas_dashboard'),
    path('dashboard-cargas/serie/<int:carga_id>/datos.csv', views_recoleccion.descargar_csv_serie_datos, name='descargar_csv_serie_datos'),
    path('dashboard-cargas/serie/<int:carga_id>/metadata.csv', views_recoleccion.descargar_csv_serie_metadata, name='descargar_csv_serie_metadata'),
    path('dashboard-cargas/conjuntos-datos/<int:carga_id>/conjuntos-datos.csv', views_recoleccion.descargar_csv_conjunto_datos, name='descargar_csv_conjunto_datos'),
    path('dashboard-cargas/conjuntos-datos/<int:carga_id>/metadata.csv', views_recoleccion.descargar_csv_metadata_variables, name='descargar_csv_metadata_variables'),
    
    # ========================================================================
    # MÓDULO DE REPORTES (INDEPENDIENTE)
    # ========================================================================
    
    # Autenticación
    path('reportes/login/', views_reportes.reportes_login, name='reportes_login'),
    path('reportes/logout/', views_reportes.reportes_logout, name='reportes_logout'),
    
    # Dashboard
    path('reportes/', views_reportes.reportes_dashboard, name='reportes_dashboard'),
    
    # Reportes - Indicadores
    path('reportes/indicadores/', views_reportes.reportes_indicadores, name='reportes_indicadores'),
    path('reportes/indicadores/<int:indicador_id>/datos/', views_reportes.descargar_datos_indicador, name='reportes_descargar_datos_indicador'),
    path('reportes/indicadores/datos-masivo/', views_reportes.descargar_datos_indicador, name='reportes_descargar_datos_indicador_masivo'),
    path('reportes/indicadores/<int:indicador_id>/metadata/', views_reportes.descargar_metadata_indicador, name='reportes_descargar_metadata_indicador'),
    path('reportes/indicadores/metadata-masivo/', views_reportes.descargar_metadata_indicador, name='reportes_descargar_metadata_indicador_masivo'),
    
    # Reportes - conjunto_datos
    path('reportes/conjuntos-datos/', views_reportes.reportes_conjuntos_datos, name='reportes_conjuntos_datos'),
    path('reportes/conjuntos-datos/<int:conjunto_datos_id>/datos/', views_reportes.descargar_conjunto_datos, name='reportes_descargar_conjunto_datos'),
    path('reportes/conjuntos-datos/<int:conjunto_datos_id>/metadata/', views_reportes.descargar_metadata_variables, name='reportes_descargar_metadata_variables'),

    # Reportes - Trazabilidad
    path('reportes/trazabilidad/', views_reportes.reportes_trazabilidad, name='reportes_trazabilidad'),
    path('reportes/trazabilidad/exportar/', views_reportes.exportar_trazabilidad_excel, name='exportar_trazabilidad_excel'),

    # Reportes - Operaciones (pipeline de cargas)
    path('reportes/operaciones/', views_reportes.reportes_operaciones, name='reportes_operaciones'),

    # Reportes - Producción Mensual (informe de control)
    path('reportes/produccion-mensual/', views_reportes.reportes_produccion_mensual, name='reportes_produccion_mensual'),
    path('reportes/produccion-mensual/exportar-excel/', views_reportes.reportes_produccion_mensual_exportar_excel, name='reportes_produccion_mensual_exportar_excel'),

    # Reportes - Visitas a páginas
    path('reportes/visitas/', views_reportes.reportes_visitas, name='reportes_visitas'),
    path('reportes/visitas/exportar-excel/', views_reportes.reportes_visitas_exportar_excel, name='reportes_visitas_exportar_excel'),

    # ============================================================================
    # URLs SISTEMA DE SATISFACCIÓN CIUDADANA
    # ============================================================================
    
    # Instructivo para empleados
    path('satisfaccion/instructivo/', views_satisfaccion.satisfaccion_instructivo, name='satisfaccion_instructivo'),
    path('satisfaccion/banners/', views_satisfaccion.satisfaccion_banners_suborganismo, name='satisfaccion_banners_suborganismo'),

    # Formularios públicos sin equipo: las rutas literales (rapida, gracias)
    # van ANTES del catch-all <slug:codigo_equipo> para no ser capturadas como equipo
    path('satisfaccion/<orgcode:codigo_organismo>/rapida/', views_satisfaccion.satisfaccion_rapida, name='satisfaccion_rapida'),
    path('satisfaccion/<orgcode:codigo_organismo>/gracias/', views_satisfaccion.satisfaccion_gracias_completa, name='satisfaccion_gracias_completa'),

    # Formularios públicos con equipo
    path('satisfaccion/<orgcode:codigo_organismo>/<slug:codigo_equipo>/rapida/', views_satisfaccion.satisfaccion_rapida, name='satisfaccion_rapida_equipo'),
    path('satisfaccion/<orgcode:codigo_organismo>/<slug:codigo_equipo>/gracias/', views_satisfaccion.satisfaccion_gracias_completa, name='satisfaccion_gracias_completa_equipo'),
    path('satisfaccion/<orgcode:codigo_organismo>/<slug:codigo_equipo>/', views_satisfaccion.satisfaccion_formulario, name='satisfaccion_formulario_equipo'),
    path('satisfaccion/<orgcode:codigo_organismo>/', views_satisfaccion.satisfaccion_formulario, name='satisfaccion_formulario'),
    
    # Admin - Dashboard y gestión
    path('admin/satisfaccion/dashboard/', views_satisfaccion.satisfaccion_dashboard, name='satisfaccion_dashboard'),
    path('admin/satisfaccion/organismos/', views_satisfaccion.satisfaccion_organismos, name='satisfaccion_organismos'),
    path('admin/satisfaccion/organismos/<int:organismo_id>/editar/', views_satisfaccion.satisfaccion_organismo_editar, name='satisfaccion_organismo_editar'),
    path('admin/satisfaccion/exportar/', views_satisfaccion.satisfaccion_exportar, name='satisfaccion_exportar'),
    path('admin/satisfaccion/exportar-rapidas-csv/', views_satisfaccion.exportar_respuestas_rapidas_csv, name='exportar_respuestas_rapidas_csv'),
    path('admin/satisfaccion/exportar-completas-csv/', views_satisfaccion.exportar_respuestas_completas_csv, name='exportar_respuestas_completas_csv'),

    # ================================================================
    # TALLER DE GESTIÓN DE DATOS INSTITUCIONALES (instrumento F1/F2/F3)
    # ================================================================
    path('taller/', views_taller.landing_page, name='taller_landing'),
    path('taller/cartel/', views_taller.cartel, name='taller_cartel'),
    path('taller/api/suborganismos/<int:organismo_id>/', views_taller.api_suborganismos, name='taller_api_suborganismos'),
    path('taller/api/ecosistema/', views_taller.api_ecosistema, name='taller_api_ecosistema'),
    path('taller/inscripcion/', views_taller.wizard_inicio, name='taller_wizard'),
    path('taller/inscripcion/paso/<slug:slug>/', views_taller.wizard_paso, name='taller_wizard_paso'),
    path('taller/inscripcion/confirmacion/', views_taller.wizard_confirmacion, name='taller_wizard_confirmacion'),
    path('taller/dashboard/', views_taller.dashboard, name='taller_dashboard'),
    path('taller/dashboard/exportar/', views_taller.dashboard_export, name='taller_dashboard_export'),
    path('taller/dashboard/exportar-excel/', views_taller.dashboard_export_excel, name='taller_dashboard_export_excel'),
    path('taller/dashboard/exportar-variables/', views_taller.dashboard_export_variables, name='taller_dashboard_export_variables'),
    path('taller/dashboard/informe/', views_taller.dashboard_informe, name='taller_dashboard_informe'),
    path('taller/dashboard/presentacion/', views_taller.presentacion, name='taller_presentacion'),
    path('taller/dashboard/casos-f2/', views_taller.casos_f2, name='taller_casos_f2'),
    path('taller/dashboard/casos-f2/excel/', views_taller.casos_f2_excel, name='taller_casos_f2_excel'),
    path('taller/dashboard/informe-excel/', views_taller.reporte_excel, name='taller_reporte_excel'),
    path('taller/nubes/<str:nombre>.svg', views_taller.nube_svg, name='taller_nube_svg'),
    path('taller/ecosistema/', views_taller.ecosistema, name='taller_ecosistema'),
    path('taller/ecosistema/gexf/', views_taller.ecosistema_gexf, name='taller_ecosistema_gexf'),
    path('taller/ecosistema/svg/', views_taller.ecosistema_svg, name='taller_ecosistema_svg'),
    path('taller/ecosistema/metodologia/', views_taller.ecosistema_metodologia, name='taller_ecosistema_metodologia'),
    path('taller/ecosistema/modelo-datos/', views_taller.modelo_datos, name='taller_modelo_datos'),

    # ================================================================
    # CATÁLOGO DE DATOS (módulo independiente)
    # ================================================================
    path('catalogo/', views_catalogo.catalogo_datos, name='catalogo_datos'),
    path('catalogo/ficha/<int:fuente_id>/', views_catalogo.ficha_conjunto, name='catalogo_ficha'),
    path('catalogo/api/fuentes/', views_catalogo.api_fuentes_catalogo, name='catalogo_api_fuentes'),

    # ========================================================================
    # PORTAL DEL DELEGADO DE ORGANISMO
    # ========================================================================

    # Autenticación
    path('delegado/login/', views_delegado.delegado_login, name='delegado_login'),
    path('delegado/logout/', views_delegado.delegado_logout, name='delegado_logout'),

    # Dashboard
    path('delegado/', views_delegado.delegado_dashboard, name='delegado_dashboard'),

    # Indicadores del organismo
    path('delegado/mis-indicadores/', views_delegado.delegado_mis_indicadores, name='delegado_mis_indicadores'),

    # Carga de series
    path('delegado/cargar-serie/', views_delegado.delegado_cargar_serie, name='delegado_cargar_serie'),
    path('delegado/serie/<int:carga_id>/', views_delegado.delegado_detalle_serie, name='delegado_detalle_serie'),

    # Carga de conjunto_datos
    path('delegado/cargar-conjuntos-datos/', views_delegado.delegado_cargar_conjunto_datos, name='delegado_cargar_conjunto_datos'),
    path('delegado/conjuntos-datos/<int:carga_id>/', views_delegado.delegado_detalle_conjunto_datos, name='delegado_detalle_conjunto_datos'),

    # Completar cargas parciales
    path('delegado/serie/<int:carga_id>/completar/', views_delegado.delegado_completar_serie, name='delegado_completar_serie'),
    path('delegado/conjuntos-datos/<int:carga_id>/completar/', views_delegado.delegado_completar_conjunto_datos, name='delegado_completar_conjunto_datos'),

    # Historial
    path('delegado/historial/', views_delegado.delegado_historial, name='delegado_historial'),

    # Ingreso inline y formularios web del delegado (complementario a carga por archivo)
    path('delegado/serie-inline/', views_delegado.delegado_cargar_serie_inline, name='delegado_cargar_serie_inline'),
    path('delegado/metadata-form/', views_delegado.delegado_cargar_metadata_form, name='delegado_cargar_metadata_form'),
    path('delegado/variables-form/', views_delegado.delegado_cargar_variables_form, name='delegado_cargar_variables_form'),
    path('delegado/actualizar-existente/', views_delegado.delegado_actualizar_existente, name='delegado_actualizar_existente'),

    # Manual y plantillas
    path('delegado/manual/', views_delegado.delegado_manual, name='delegado_manual'),
    path('delegado/plantillas/', views_delegado.delegado_plantillas, name='delegado_plantillas'),

    # FICED — Formulario de Capacidad Estadística Distrital
    path('delegado/ficed/', views_delegado.delegado_ficed, name='delegado_ficed'),

    # ========================================================================
    # PANEL DE VALIDACIÓN (EQUIPO TÉCNICO SIIED)
    # ========================================================================

    # Autenticación
    path('validacion/login/', views_validacion.validacion_login, name='validacion_login'),
    path('validacion/logout/', views_validacion.validacion_logout, name='validacion_logout'),

    # Dashboard
    path('validacion/', views_validacion.validacion_dashboard, name='validacion_dashboard'),

    # Revisión de cargas
    path('validacion/serie/<int:carga_id>/', views_validacion.validacion_revisar_serie, name='validacion_revisar_serie'),
    path('validacion/serie/<int:carga_id>/decidir/', views_validacion.validacion_decidir_serie, name='validacion_decidir_serie'),
    
    # Creación simplificada de gráficos
    path('validacion/crear-grafico/<int:indicador_id>/', views_validacion.crear_grafico_simplificado_validacion, name='crear_grafico_simplificado_validacion'),
    path('validacion/conjuntos-datos/<int:carga_id>/', views_validacion.validacion_revisar_conjunto_datos, name='validacion_revisar_conjunto_datos'),
    path('validacion/conjuntos-datos/<int:carga_id>/decidir/', views_validacion.validacion_decidir_conjunto_datos, name='validacion_decidir_conjunto_datos'),

    # Historial
    path('validacion/historial/', views_validacion.validacion_historial, name='validacion_historial'),

    # ICED
    path('validacion/iced/<int:formulario_id>/', views_validacion.validacion_revisar_iced, name='validacion_revisar_iced'),
    path('validacion/iced/<int:formulario_id>/calcular/', views_validacion.validacion_calcular_iced, name='validacion_calcular_iced'),
    path('validacion/iced/<int:formulario_id>/decidir/', views_validacion.validacion_decidir_iced, name='validacion_decidir_iced'),

    # Manual
    path('validacion/manual/', views_validacion.validacion_manual, name='validacion_manual'),

    # Wizard de conciliación de desagregaciones (compartido con el admin,
    # con los estilos del módulo)
    path('validacion/conciliacion/', views_validacion.validacion_conciliacion, name='validacion_conciliacion'),
    path('validacion/conciliacion/manual/', views_validacion.validacion_conciliacion_manual, name='validacion_conciliacion_manual'),
    path('validacion/conciliacion/equivalencias/', views_validacion.validacion_conciliacion_equivalencias, name='validacion_conciliacion_equivalencias'),
    path('validacion/conciliacion/preview/', views_validacion.validacion_conciliacion_preview, name='validacion_conciliacion_preview'),
    path('validacion/conciliacion/aplicar/', views_validacion.validacion_conciliacion_aplicar, name='validacion_conciliacion_aplicar'),
    path('validacion/conciliacion/eliminar/', views_validacion.validacion_conciliacion_eliminar, name='validacion_conciliacion_eliminar'),
    path('validacion/conciliacion/dominio/<int:dominio_id>/', views_validacion.validacion_conciliacion_dominio, name='validacion_conciliacion_dominio'),

    # ========================================================================
    # HALL DE CAPACIDAD ESTADÍSTICA
    # ========================================================================
    
    # Vista principal del hall
    path('hall-capacidad/', views.hall_capacidad_estadistica, name='hall_capacidad_estadistica'),
    
    # Vista detallada de cada organismo
    path('hall-capacidad/<str:codigo>/', views.organismo_detalle, name='organismo_detalle'),

    # ========================================================================
    # CALENDARIO DE DIFUSIÓN ESTADÍSTICA
    # ========================================================================
    path('calendario-difusion/', views.calendario_difusion, name='calendario_difusion'),

    # ========================================================================
    # MÓDULO ICED PÚBLICO — Índice de Capacidad Estadística Distrital
    # ========================================================================
    path('iced/modulo/', views.modulo_iced, name='modulo_iced'),

    # ========================================================================
    # MÓDULO ICED — Índice de Capacidad Estadística y de Datos
    # ========================================================================
    path('iced/', views_iced.iced_landing, name='iced_landing'),
    path('iced/formulario/', views_iced.ICEDWizardView.as_view(views_iced.ICED_WIZARD_FORMS), name='iced_formulario_nuevo'),
    path('iced/formulario/<int:formulario_id>/', views_iced.ICEDWizardView.as_view(views_iced.ICED_WIZARD_FORMS), name='iced_formulario_retomar'),
    path('iced/confirmacion/<int:formulario_id>/', views_iced.iced_confirmacion, name='iced_confirmacion'),
    path('iced/resultado/<int:formulario_id>/', views_iced.iced_resultado, name='iced_resultado'),
    path('iced/guardar-parcial/', views_iced.iced_guardar_parcial, name='iced_guardar_parcial'),
    path('iced/exportar-csv/', views_iced.iced_exportar_csv, name='iced_exportar_csv'),

    # ========================================================================
    # MÓDULO EDITORIAL — Gestión de Contenidos
    # ========================================================================
    path('editorial/login/', views_editorial.editorial_login, name='editorial_login'),
    path('editorial/logout/', views_editorial.editorial_logout, name='editorial_logout'),

    path('editorial/', views_editorial.editorial_dashboard, name='editorial_dashboard'),
    path('editorial/manual/', views_editorial.editorial_manual, name='editorial_manual'),
    
    # Productos Académicos
    path('editorial/productos/', views_editorial.productos_listado, name='editorial_productos'),
    path('editorial/productos/wizard/', views_editorial.productos_wizard, name='editorial_productos_wizard'),
    path('editorial/productos/<slug:slug>/editar/', views_editorial.producto_editar, name='editorial_producto_editar'),
    path('editorial/productos/<slug:slug>/secciones/', views_editorial.producto_secciones, name='editorial_producto_secciones'),
    path('editorial/productos/<slug:slug>/preview/', views_editorial.producto_preview, name='editorial_producto_preview'),
    path('editorial/secciones/<int:seccion_id>/grafico/', views_editorial.editorial_seccion_grafico, name='editorial_seccion_grafico'),
    
    # Eventos
    path('editorial/eventos/', views_editorial.eventos_listado, name='editorial_eventos'),
    path('editorial/eventos/crear/', views_editorial.evento_crear, name='editorial_evento_crear'),
    path('editorial/eventos/<int:pk>/editar/', views_editorial.evento_editar, name='editorial_evento_editar'),
    path('editorial/eventos/<int:pk>/eliminar/', views_editorial.evento_eliminar, name='editorial_evento_eliminar'),
    path('editorial/eventos/calendario/', views_editorial.eventos_calendario, name='editorial_eventos_calendario'),
    
    # Calendario de Difusión
    path('editorial/calendario-difusion/', views_editorial.calendario_difusion_listado, name='editorial_calendario_difusion'),
    path('editorial/calendario-difusion/crear/', views_editorial.calendario_difusion_crear, name='editorial_calendario_difusion_crear'),
    path('editorial/calendario-difusion/<int:pk>/editar/', views_editorial.calendario_difusion_editar, name='editorial_calendario_difusion_editar'),
    path('editorial/calendario-difusion/exportar/', views_editorial.calendario_difusion_exportar, name='editorial_calendario_difusion_exportar'),
    
    # Noticias
    path('editorial/noticias/', views_editorial.noticias_listado, name='editorial_noticias'),
    path('editorial/noticias/crear/', views_editorial.noticia_crear, name='editorial_noticia_crear'),
    path('editorial/noticias/<int:pk>/editar/', views_editorial.noticia_editar, name='editorial_noticia_editar'),
    path('editorial/noticias/<int:pk>/eliminar/', views_editorial.noticia_eliminar, name='editorial_noticia_eliminar'),
    path('editorial/noticias/<int:pk>/preview/', views_editorial.noticia_preview, name='editorial_noticia_preview'),
    
    # Sistemas de Información
    path('editorial/sistemas/', views_editorial.sistemas_listado, name='editorial_sistemas'),
    path('editorial/sistemas/crear/', views_editorial.sistema_crear, name='editorial_sistema_crear'),
    path('editorial/sistemas/<int:pk>/editar/', views_editorial.sistema_editar, name='editorial_sistema_editar'),
    path('editorial/sistemas/<int:pk>/eliminar/', views_editorial.sistema_eliminar, name='editorial_sistema_eliminar'),
    path('editorial/sistemas/categorias/crear/', views_editorial.categoria_sistema_crear, name='editorial_categoria_sistema_crear'),
    path('editorial/sistemas/categorias/<int:pk>/editar/', views_editorial.categoria_sistema_editar, name='editorial_categoria_sistema_editar'),
    
    # Productos de Información
    path('editorial/proyectos-info/', views_editorial.proyectos_listado, name='editorial_proyectos_info'),
    path('editorial/proyectos-info/crear/', views_editorial.proyecto_crear, name='editorial_proyecto_info_crear'),
    path('editorial/proyectos-info/<int:pk>/editar/', views_editorial.proyecto_editar, name='editorial_proyecto_info_editar'),
    path('editorial/proyectos-info/<int:pk>/eliminar/', views_editorial.proyecto_eliminar, name='editorial_proyecto_info_eliminar'),
    path('editorial/proyectos-info/categorias/crear/', views_editorial.categoria_proyecto_crear, name='editorial_categoria_proyecto_crear'),
    path('editorial/proyectos-info/categorias/<int:pk>/editar/', views_editorial.categoria_proyecto_editar, name='editorial_categoria_proyecto_editar'),
    
    # Documentos de Infraestructura
    path('editorial/documentos/', views_editorial.documentos_listado, name='editorial_documentos'),
    path('editorial/documentos/crear/', views_editorial.documento_crear, name='editorial_documento_crear'),
    path('editorial/documentos/<int:pk>/editar/', views_editorial.documento_editar, name='editorial_documento_editar'),
    path('editorial/documentos/<int:pk>/eliminar/', views_editorial.documento_eliminar, name='editorial_documento_eliminar'),
    
    # Árbol jerárquico de Infraestructura
    path('editorial/infraestructura/arbol/', views_editorial.infraestructura_arbol, name='editorial_infraestructura_arbol'),
    # Áreas (Nivel 1)
    path('editorial/infraestructura/areas/crear/', views_editorial.infra_area_crear, name='editorial_infra_area_crear'),
    path('editorial/infraestructura/areas/<int:pk>/editar/', views_editorial.infra_area_editar, name='editorial_infra_area_editar'),
    path('editorial/infraestructura/areas/<int:pk>/eliminar/', views_editorial.infra_area_eliminar, name='editorial_infra_area_eliminar'),
    # Categorías (Nivel 2)
    path('editorial/infraestructura/categorias/crear/', views_editorial.infra_categoria_crear, name='editorial_infra_categoria_crear'),
    path('editorial/infraestructura/categorias/<int:pk>/editar/', views_editorial.infra_categoria_editar, name='editorial_infra_categoria_editar'),
    path('editorial/infraestructura/categorias/<int:pk>/eliminar/', views_editorial.infra_categoria_eliminar, name='editorial_infra_categoria_eliminar'),
    # Subcategorías (Nivel 3)
    path('editorial/infraestructura/subcategorias/crear/', views_editorial.infra_subcategoria_crear, name='editorial_infra_subcategoria_crear'),
    path('editorial/infraestructura/subcategorias/<int:pk>/editar/', views_editorial.infra_subcategoria_editar, name='editorial_infra_subcategoria_editar'),
    path('editorial/infraestructura/subcategorias/<int:pk>/eliminar/', views_editorial.infra_subcategoria_eliminar, name='editorial_infra_subcategoria_eliminar'),
    # Grupos (Nivel 4)
    path('editorial/infraestructura/grupos/crear/', views_editorial.infra_grupo_crear, name='editorial_infra_grupo_crear'),
    path('editorial/infraestructura/grupos/<int:pk>/editar/', views_editorial.infra_grupo_editar, name='editorial_infra_grupo_editar'),
    path('editorial/infraestructura/grupos/<int:pk>/eliminar/', views_editorial.infra_grupo_eliminar, name='editorial_infra_grupo_eliminar'),

    # Gráficos de Indicadores
    path('editorial/graficos/', views_editorial.editorial_graficos_listado, name='editorial_graficos_listado'),
    path('editorial/graficos/<int:indicador_pk>/crear/', views_editorial.editorial_grafico_crear, name='editorial_grafico_crear'),
    path('editorial/graficos/<int:pk>/editar/', views_editorial.editorial_grafico_editar, name='editorial_grafico_editar'),
    path('editorial/graficos/<int:pk>/eliminar/', views_editorial.editorial_grafico_eliminar, name='editorial_grafico_eliminar'),
    path('editorial/api/buscar-graficos/', views_editorial.api_buscar_graficos, name='api_buscar_graficos'),
    # Catálogo de Consulta (directorios / listados de referencia)
    path('editorial/catalogo-consulta/', views_editorial.catalogo_consulta_listado, name='editorial_catalogo_consulta'),
    path('editorial/catalogo-consulta/crear/', views_editorial.catalogo_consulta_crear, name='editorial_catalogo_consulta_crear'),
    path('editorial/catalogo-consulta/<int:pk>/editar/', views_editorial.catalogo_consulta_editar, name='editorial_catalogo_consulta_editar'),
    path('editorial/catalogo-consulta/<int:pk>/eliminar/', views_editorial.catalogo_consulta_eliminar, name='editorial_catalogo_consulta_eliminar'),
]
