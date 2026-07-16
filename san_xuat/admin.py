from django.contrib import admin

from san_xuat.models import BomLine, BomVersion, CostingSnapshot, ProcessStep, ProductTechDoc


class BomLineInline(admin.TabularInline):
    model = BomLine
    extra = 0
    autocomplete_fields = ('material',)


class ProcessStepInline(admin.TabularInline):
    model = ProcessStep
    extra = 0


@admin.register(ProductTechDoc)
class ProductTechDocAdmin(admin.ModelAdmin):
    list_display = ('product_code', 'product_name', 'is_active', 'updated_at')
    search_fields = ('product_code', 'product_name')
    list_filter = ('is_active',)


@admin.register(BomVersion)
class BomVersionAdmin(admin.ModelAdmin):
    list_display = ('tech_doc', 'version_label', 'status', 'overhead_pct', 'updated_at')
    list_filter = ('status',)
    search_fields = ('tech_doc__product_code', 'version_label')
    inlines = [BomLineInline, ProcessStepInline]


@admin.register(CostingSnapshot)
class CostingSnapshotAdmin(admin.ModelAdmin):
    list_display = ('bom', 'total_cost', 'sell_price', 'margin', 'created_at')
    readonly_fields = (
        'material_cost',
        'labor_cost',
        'overhead_cost',
        'total_cost',
        'sell_price',
        'margin',
        'created_at',
    )
