from django.urls import path

from . import views, views_ficed

app_name = 'gestion'

urlpatterns = [
    path('login/', views.gestion_login, name='login'),
    path('logout/', views.gestion_logout, name='logout'),
    path('', views.hub, name='hub'),
    path('bitacora/', views.bitacora, name='bitacora'),

    # FICED
    path('ficed/', views_ficed.dashboard, name='ficed_dashboard'),
    path('ficed/usuarios/', views_ficed.usuarios, name='ficed_usuarios'),
    path('ficed/usuarios/crear/', views_ficed.usuario_crear,
         name='ficed_usuario_crear'),
    path('ficed/usuarios/<int:user_id>/editar/', views_ficed.usuario_editar,
         name='ficed_usuario_editar'),
    path('ficed/usuarios/<int:user_id>/accion/', views_ficed.usuario_accion,
         name='ficed_usuario_accion'),
    path('ficed/usuarios/correos/', views_ficed.correos_masivos,
         name='ficed_correos_masivos'),
    path('ficed/organismos/', views_ficed.organismos,
         name='ficed_organismos'),
    path('ficed/organismos/<int:organismo_id>/flags/',
         views_ficed.organismo_flags, name='ficed_organismo_flags'),
    path('ficed/formularios/', views_ficed.formularios,
         name='ficed_formularios'),
    path('ficed/formularios/<int:formulario_id>/accion/',
         views_ficed.formulario_accion, name='ficed_formulario_accion'),
    path('ficed/ventanas/', views_ficed.ventanas, name='ficed_ventanas'),
    path('ficed/ventanas/guardar/', views_ficed.ventana_guardar,
         name='ficed_ventana_guardar'),
    path('ficed/ventanas/<int:ventana_id>/prorroga/',
         views_ficed.prorroga_crear, name='ficed_prorroga'),
]
