from django.contrib import admin

from .models import Device, MaintenanceLog


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'status', 'managed_by', 'serial_number', 'usage_department_label', 'created_at')
    list_filter = ('status', 'category', 'managed_by')
    search_fields = ('name', 'serial_number', 'hostname', 'model_number')


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = ('device', 'reported_by', 'is_resolved', 'created_at')
    list_filter = ('is_resolved',)
