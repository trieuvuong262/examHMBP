from django.contrib import admin

from .models import (
    Device,
    DeviceCategory,
    DeviceStatus,
    MaintenanceLog,
)


class MaintenanceLogInline(admin.TabularInline):
    model = MaintenanceLog
    extra = 0
    fields = ('reported_by', 'issue_description', 'is_resolved', 'cost', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        'device_code',
        'name',
        'category',
        'status',
        'assigned_user',
        'usage_department',
        'hostname',
        'ip_address',
        'serial_number',
        'last_scan_date',
    )
    list_filter = ('status', 'category', 'managed_department')
    search_fields = (
        'device_code',
        'name',
        'serial_number',
        'hostname',
        'model_number',
        'assigned_user_text',
        'usage_department_text',
        'assigned_user__username',
        'assigned_user__profile__full_name',
    )
    list_select_related = ('usage_department', 'assigned_user', 'assigned_user__profile')
    raw_id_fields = ('usage_department', 'assigned_user')
    readonly_fields = ('total_price', 'created_at', 'updated_at', 'last_scan_date')
    inlines = [MaintenanceLogInline]
    fieldsets = (
        ('Thiết bị', {
            'fields': ('device_code', 'name', 'category', 'status', 'managed_department', 'description', 'photo'),
        }),
        ('Người dùng & phòng ban', {
            'fields': (
                'assigned_user',
                'assigned_user_text',
                'usage_department',
                'usage_department_text',
                'usage_room',
                'contact_email',
                'handover_date',
            ),
        }),
        ('Kỹ thuật', {
            'fields': (
                'model_number',
                'serial_number',
                'hostname',
                'ip_address',
                'configuration',
                'windows_version',
                'windows_license',
                'last_scan_date',
            ),
        }),
        ('Tài chính & QR', {
            'fields': ('quantity', 'unit_price', 'total_price', 'qr_code'),
        }),
        ('Hệ thống', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(DeviceCategory)
class DeviceCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'group', 'import_profile', 'sort_order', 'is_active', 'is_system')
    list_filter = ('group', 'import_profile', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('group', 'sort_order', 'name')


@admin.register(DeviceStatus)
class DeviceStatusAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'sort_order', 'is_active', 'is_system')
    list_filter = ('is_active', 'is_system')
    search_fields = ('code', 'name')
    ordering = ('sort_order', 'name')


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = ('device', 'reported_by', 'is_resolved', 'cost', 'created_at')
    list_filter = ('is_resolved',)
    search_fields = ('device__name', 'reported_by', 'issue_description')
    raw_id_fields = ('device', 'service_request')
    readonly_fields = ('created_at',)
