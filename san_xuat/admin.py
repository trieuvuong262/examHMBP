from django.contrib import admin

from san_xuat.models import BomLine, BomVersion, CostingSnapshot, ProcessStep, ProductTechDoc, TechDocDesignFile
from san_xuat.ie_models import (
    SxMachine,
    SxOperation,
    SxOperationGroup,
    SxProcessStage,
    SxRouting,
    SxRoutingLine,
    SxSkillLevel,
    SxSmvSource,
    SxStitchClass,
    SxTimeStudy,
)


class BomLineInline(admin.TabularInline):
    model = BomLine
    extra = 0
    autocomplete_fields = ('material',)


class ProcessStepInline(admin.TabularInline):
    model = ProcessStep
    extra = 0


class TechDocDesignFileInline(admin.TabularInline):
    model = TechDocDesignFile
    extra = 0
    readonly_fields = ('uploaded_at', 'uploaded_by')


@admin.register(ProductTechDoc)
class ProductTechDocAdmin(admin.ModelAdmin):
    list_display = ('product_code', 'product_name', 'is_active', 'updated_at')
    search_fields = ('product_code', 'product_name')
    list_filter = ('is_active',)
    inlines = [TechDocDesignFileInline]


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


# --- IE / Master data mã công đoạn sản xuất ---


class _RefAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    list_editable = ('sort_order', 'is_active')


admin.site.register(SxMachine, _RefAdmin)
admin.site.register(SxStitchClass, _RefAdmin)
admin.site.register(SxSkillLevel, _RefAdmin)
admin.site.register(SxSmvSource, _RefAdmin)
admin.site.register(SxProcessStage, _RefAdmin)


@admin.register(SxOperationGroup)
class SxOperationGroupAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'process_stage_label', 'default_work_center_code', 'is_active')
    list_filter = ('is_active', 'process_stage_label')
    search_fields = ('code', 'name')


@admin.register(SxOperation)
class SxOperationAdmin(admin.ModelAdmin):
    list_display = ('op_code', 'op_rev', 'name_vi', 'group', 'machine_code', 'base_smv_min', 'status')
    list_filter = ('status', 'group', 'process_stage_label')
    search_fields = ('op_code', 'name_vi', 'name_en')
    autocomplete_fields = ('group',)
    list_select_related = ('group',)


class SxRoutingLineInline(admin.TabularInline):
    model = SxRoutingLine
    extra = 0
    fields = ('seq_no', 'op_code', 'op_rev', 'qty_per_garment', 'applied_unit_smv', 'total_operation_smv', 'work_center_code', 'machine_code')
    readonly_fields = ('total_operation_smv',)


@admin.register(SxRouting)
class SxRoutingAdmin(admin.ModelAdmin):
    list_display = ('routing_id', 'style_code', 'routing_rev', 'approval_status', 'is_active', 'updated_at')
    list_filter = ('is_active', 'product_family')
    search_fields = ('routing_id', 'style_code', 'style_name')
    inlines = [SxRoutingLineInline]


@admin.register(SxTimeStudy)
class SxTimeStudyAdmin(admin.ModelAdmin):
    list_display = ('study_id', 'op_code', 'style_code', 'obs_no', 'calculated_smv', 'current_routing_smv', 'variance_pct', 'approval_status')
    list_filter = ('approval_status', 'style_code')
    search_fields = ('study_id', 'op_code', 'op_name_vi', 'operator_id')
    readonly_fields = ('net_observed_sec', 'normal_time_sec', 'standard_time_sec', 'calculated_smv', 'variance_pct')
