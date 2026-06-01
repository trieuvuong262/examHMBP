from django.contrib import admin

from .models import (
    ProcurementLineItem,
    RecurringItemCatalog,
    RequestType,
    RequestTypeStepTemplate,
    ServiceRequest,
    ServiceRequestAttachment,
    ServiceRequestLog,
    ServiceRequestStep,
)


class RequestTypeStepTemplateInline(admin.TabularInline):
    model = RequestTypeStepTemplate
    extra = 0
    ordering = ('step_order',)


@admin.register(RequestType)
class RequestTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    inlines = [RequestTypeStepTemplateInline]


class ServiceRequestStepInline(admin.TabularInline):
    model = ServiceRequestStep
    extra = 0
    readonly_fields = ('step_order', 'step_code', 'name', 'status', 'assignee', 'completed_at')
    can_delete = False


class ProcurementLineItemInline(admin.TabularInline):
    model = ProcurementLineItem
    extra = 0
    readonly_fields = ('description', 'quantity_requested', 'quantity_confirmed', 'unit')


@admin.register(RecurringItemCatalog)
class RecurringItemCatalogAdmin(admin.ModelAdmin):
    list_display = ('name', 'unit', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'request_type', 'requester', 'status', 'selected_total_amount', 'created_at')
    list_filter = ('status', 'request_type', 'is_from_catalog')
    search_fields = ('title', 'requester__username')
    raw_id_fields = ('requester', 'goods_receiver', 'recurring_item')
    inlines = [ServiceRequestStepInline, ProcurementLineItemInline]


@admin.register(ServiceRequestLog)
class ServiceRequestLogAdmin(admin.ModelAdmin):
    list_display = ('request', 'action', 'actor', 'created_at')
    list_filter = ('action',)
