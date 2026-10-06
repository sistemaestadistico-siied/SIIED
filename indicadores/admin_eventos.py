# Administración de Eventos
from django.contrib import admin
from django.utils import timezone
from django_ckeditor_5.widgets import CKEditor5Widget
from .models import Evento

@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'lugar', 'fecha_inicio', 'fecha_fin', 'activo', 'destacado', 'fecha_actualizacion')
    list_filter = ('activo', 'destacado', 'fecha_inicio', 'lugar')
    search_fields = ('nombre', 'descripcion', 'lugar')
    list_editable = ('activo', 'destacado')
    prepopulated_fields = {'slug': ('nombre',)}
    ordering = ('fecha_inicio',)
    date_hierarchy = 'fecha_inicio'
    
    fieldsets = (
        ('Información básica', {
            'fields': ('nombre', 'slug', 'lugar', 'activo', 'destacado')
        }),
        ('Fechas y horarios', {
            'fields': ('fecha_inicio', 'fecha_fin'),
            'classes': ('wide',)
        }),
        ('Contenido', {
            'fields': ('descripcion', 'imagen_url', 'url_externa'),
            'classes': ('wide',)
        }),
    )
    
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    
    def get_queryset(self, request):
        """Mostrar eventos futuros primero"""
        qs = super().get_queryset(request)
        return qs.extra(
            select={'is_future': "fecha_inicio > '%s'" % timezone.now().strftime('%Y-%m-%d %H:%M:%S')},
            order_by=['-is_future', 'fecha_inicio']
        )
    
    class Media:
        css = {
            'all': ('admin/css/ckeditor_custom.css',)
        }
