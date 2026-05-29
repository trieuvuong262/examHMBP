from django.contrib import admin

from .models import (
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
    readonly_fields = ('step_order', 'name', 'status', 'assignee', 'completed_at')
    can_delete = False


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'request_type', 'requester', 'status', 'created_at')
    list_filter = ('status', 'request_type')
    search_fields = ('title', 'requester__username')
    raw_id_fields = ('requester',)
    inlines = [ServiceRequestStepInline]


@admin.register(ServiceRequestLog)
class ServiceRequestLogAdmin(admin.ModelAdmin):
    list_display = ('request', 'action', 'actor', 'created_at')
    list_filter = ('action',)
