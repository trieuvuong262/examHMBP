from django.contrib import admin

from .models import (
    Approval,
    ApprovalCondition,
    Attachment,
    AuditLog,
    DesignVersion,
    Handover,
    HandoverReceipt,
    ModuleSetting,
    ProductDevelopment,
    SampleEvaluation,
    SampleVersion,
    Task,
)


class DesignVersionInline(admin.TabularInline):
    model = DesignVersion
    extra = 0
    fields = ('version_no', 'state', 'is_current', 'created_by', 'created_at')
    readonly_fields = fields
    can_delete = False
    show_change_link = True


class SampleVersionInline(admin.TabularInline):
    model = SampleVersion
    extra = 0
    fields = ('version_no', 'state', 'is_current', 'design_version', 'maker', 'completed_date')
    readonly_fields = fields
    can_delete = False
    show_change_link = True


@admin.register(ProductDevelopment)
class ProductDevelopmentAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'status', 'product_group', 'owner', 'approver', 'official_product_code', 'is_demo')
    list_filter = ('status', 'product_group', 'priority', 'is_demo')
    search_fields = ('code', 'name', 'official_product_code')
    raw_id_fields = ('proposer', 'owner', 'approver', 'designer', 'technician', 'sample_maker', 'qa_user', 'costing_user')
    readonly_fields = ('code', 'status', 'status_changed_at', 'approved_design_version', 'final_sample_version',
                       'approved_at', 'closed_at', 'created_at', 'updated_at')
    inlines = [DesignVersionInline, SampleVersionInline]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'dossier', 'step', 'role', 'assignee', 'due_at', 'state')
    list_filter = ('state', 'step', 'role')
    search_fields = ('title', 'dossier__code')
    raw_id_fields = ('dossier', 'assignee', 'completed_by', 'receipt', 'condition')


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'dossier', 'kind', 'design_version', 'sample_version', 'is_current', 'is_deleted')
    list_filter = ('kind', 'is_current', 'is_deleted')
    search_fields = ('original_name', 'dossier__code')
    raw_id_fields = ('dossier', 'design_version', 'sample_version', 'colorway', 'uploaded_by', 'deleted_by')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'dossier', 'actor', 'action', 'summary')
    list_filter = ('action',)
    search_fields = ('dossier__code', 'summary')
    raw_id_fields = ('dossier', 'actor')


admin.site.register(Approval)
admin.site.register(ApprovalCondition)
admin.site.register(SampleEvaluation)
admin.site.register(Handover)
admin.site.register(HandoverReceipt)
admin.site.register(ModuleSetting)
