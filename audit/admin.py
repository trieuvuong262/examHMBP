from django.contrib import admin

from .models import UserActivityLog


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'username',
        'action',
        'module_label',
        'method',
        'path',
        'status_code',
        'ip_address',
    )
    list_filter = ('action', 'module_key', 'method', 'status_code', 'created_at')
    search_fields = ('username', 'full_name', 'summary', 'path', 'ip_address')
    readonly_fields = [f.name for f in UserActivityLog._meta.fields]
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
