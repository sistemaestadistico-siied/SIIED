from django.urls import path

from . import views

app_name = 'gestion'

urlpatterns = [
    path('login/', views.gestion_login, name='login'),
    path('logout/', views.gestion_logout, name='logout'),
    path('', views.hub, name='hub'),
    path('bitacora/', views.bitacora, name='bitacora'),
]
