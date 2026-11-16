from django.contrib import admin

from .models import AccionGestion, ProrrogaVentana, VentanaDiligenciamiento


@admin.register(AccionGestion)
class AccionGestionAdmin(admin.ModelAdmin):
    """Bitácora: solo lectura, se escribe desde registrar_accion."""
    list_display = ('fecha', 'usuario', 'modulo', 'accion',
                    'objeto_tipo', 'objeto_id')
    list_filter = ('modulo', 'accion')
    search_fields = ('usuario__username', 'objeto_id', 'objeto_tipo',
                     'motivo')
    readonly_fields = ('usuario', 'fecha', 'modulo', 'accion',
                       'objeto_tipo', 'objeto_id', 'antes', 'despues',
                       'motivo', 'ip')
    date_hierarchy = 'fecha'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ProrrogaInline(admin.TabularInline):
    model = ProrrogaVentana
    extra = 0
    readonly_fields = ('fecha_creacion', 'creado_por')


@admin.register(VentanaDiligenciamiento)
class VentanaDiligenciamientoAdmin(admin.ModelAdmin):
    list_display = ('modulo', 'referencia', 'fecha_apertura',
                    'fecha_cierre', 'activa')
    list_filter = ('modulo', 'activa')
    search_fields = ('referencia',)
    inlines = [ProrrogaInline]


@admin.register(ProrrogaVentana)
class ProrrogaVentanaAdmin(admin.ModelAdmin):
    list_display = ('ventana', 'organismo', 'fecha_cierre_extendida',
                    'creado_por', 'fecha_creacion')
    list_filter = ('ventana__modulo',)
    search_fields = ('organismo__nombre', 'motivo')
