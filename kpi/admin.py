from django.contrib import admin

from .models import MonthlyKpi, MonthlyKpiItem


class MonthlyKpiItemInline(admin.TabularInline):
    model = MonthlyKpiItem
    extra = 0
    fields = (
        'sort_order', 'work_group', 'weightage', 'indicator',
        'self_actual', 'self_score', 'mgr_actual', 'mgr_score',
    )


@admin.register(MonthlyKpi)
class MonthlyKpiAdmin(admin.ModelAdmin):
    list_display = ('employee_name', 'year', 'month', 'manager_name', 'imported_at')
    list_filter = ('year', 'month')
    search_fields = (
        'employee__username',
        'employee__profile__full_name',
        'employee__profile__employee_code',
    )
    autocomplete_fields = ('employee', 'direct_manager', 'imported_by')
    inlines = [MonthlyKpiItemInline]

    @admin.display(description='Nhân viên')
    def employee_name(self, obj):
        profile = getattr(obj.employee, 'profile', None)
        return profile.full_name if profile and profile.full_name else obj.employee.username

    @admin.display(description='Quản lý')
    def manager_name(self, obj):
        if not obj.direct_manager_id:
            return '—'
        profile = getattr(obj.direct_manager, 'profile', None)
        return profile.full_name if profile and profile.full_name else obj.direct_manager.username
