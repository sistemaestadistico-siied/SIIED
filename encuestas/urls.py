from django.urls import path

from . import views

app_name = 'encuestas'

urlpatterns = [
    # Respuesta pública e invitación
    path('e/<slug:slug>/', views.responder_publico,
         name='responder_publico'),
    path('e/<slug:slug>/t/<str:token>/', views.responder_invitacion,
         name='responder_invitacion'),
    path('gracias/<int:envio_id>/', views.gracias, name='gracias'),
    # Diligenciador y encuestador (con login)
    path('pendientes/', views.pendientes, name='pendientes'),
    path('diligenciar/<int:formulario_id>/', views.responder_asignado,
         name='responder_asignado'),
    path('encuestador/<int:formulario_id>/', views.responder_encuestador,
         name='responder_encuestador'),
    # Captura offline del encuestador
    path('offline/<int:formulario_id>/', views.descargar_offline,
         name='descargar_offline'),
    path('offline/<int:formulario_id>/u/<int:usuario_id>/',
         views.descargar_offline, name='descargar_offline_para'),
    path('sincronizar/', views.sincronizar, name='sincronizar'),
]
