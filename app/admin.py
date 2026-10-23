from django.contrib import admin
from .models import Campo, Lote, CicloCultivo, Insumo, MovimientoStock


@admin.register(Campo)
class CampoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "ubicacion", "superficie_total_ha")
    search_fields = ("nombre", "ubicacion")


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "campo", "superficie_ha", "tipo_suelo", "activo")
    list_filter = ("campo", "activo")
    search_fields = ("nombre", "campo__nombre")


@admin.register(CicloCultivo)
class CicloCultivoAdmin(admin.ModelAdmin):
    list_display = ("campana", "cultivo", "lote", "variedad_hibrido", "estado", "fecha_siembra", "rinde_obtenido_qq_ha")
    list_filter = ("campana", "cultivo", "estado")
    search_fields = ("variedad_hibrido", "lote__nombre", "campana")


@admin.register(Insumo)
class InsumoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "stock_actual", "unidad_medida", "deposito_habitual")
    list_filter = ("categoria", "unidad_medida")
    search_fields = ("nombre", "deposito_habitual")


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    list_display = ("fecha", "insumo", "tipo_movimiento", "cantidad", "lote", "ciclo_cultivo", "labor_realizada", "operario")
    list_filter = ("tipo_movimiento", "insumo__categoria", "lote__campo", "fecha")
    search_fields = ("insumo__nombre", "labor_realizada", "maquinaria", "operario", "lote__nombre")
    date_hierarchy = "fecha"
