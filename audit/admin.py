from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse

from .models import UserActivityLog

_BULK_DELETE_SESSION_KEY = 'audit_admin_bulk_delete_pks'
_DELETE_BATCH_SIZE = 500


@admin.action(description='Xóa hàng loạt (hỗ trợ hàng nghìn dòng)')
def bulk_delete_logs(modeladmin, request, queryset):
    """Lưu danh sách ID vào session, chuyển sang trang xác nhận (tránh lỗi 400)."""
    pks = list(queryset.values_list('pk', flat=True))
    if not pks:
        modeladmin.message_user(request, 'Không có nhật ký nào được chọn.', level=messages.WARNING)
        return None

    request.session[_BULK_DELETE_SESSION_KEY] = pks
    request.session.modified = True
    return redirect(reverse('admin:audit_useractivitylog_bulk_delete_confirm'))


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'username',
        'action',
        'module_label',
        'method',
        'machine_name',
        'ip_address',
        'path',
        'status_code',
    )
    list_filter = ('action', 'module_key', 'method', 'status_code', 'created_at')
    search_fields = ('username', 'full_name', 'summary', 'path', 'machine_name', 'ip_address')
    readonly_fields = [f.name for f in UserActivityLog._meta.fields]
    date_hierarchy = 'created_at'
    actions = [bulk_delete_logs]

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path(
                'bulk-delete/confirm/',
                self.admin_site.admin_view(self.bulk_delete_confirm_view),
                name='%s_%s_bulk_delete_confirm' % info,
            ),
        ]
        return custom + urls

    def bulk_delete_confirm_view(self, request):
        if not request.user.is_superuser:
            messages.error(request, 'Chỉ superuser mới được xóa nhật ký.')
            return redirect('admin:audit_useractivitylog_changelist')

        pks = request.session.get(_BULK_DELETE_SESSION_KEY)
        if not pks:
            messages.error(
                request,
                'Không tìm thấy phiên xóa. Vui lòng chọn nhật ký và dùng action '
                '「Xóa hàng loạt (hỗ trợ hàng nghìn dòng)」.',
            )
            return redirect('admin:audit_useractivitylog_changelist')

        count = len(pks)

        if request.method == 'POST' and request.POST.get('confirm') == 'yes':
            total = 0
            for start in range(0, len(pks), _DELETE_BATCH_SIZE):
                chunk = pks[start:start + _DELETE_BATCH_SIZE]
                deleted, _ = UserActivityLog.objects.filter(pk__in=chunk).delete()
                total += deleted
            request.session.pop(_BULK_DELETE_SESSION_KEY, None)
            messages.success(request, f'Đã xóa {total:,} nhật ký thao tác.')
            return redirect('admin:audit_useractivitylog_changelist')

        context = {
            **self.admin_site.each_context(request),
            'title': 'Xác nhận xóa nhật ký thao tác',
            'opts': self.model._meta,
            'count': count,
        }
        return render(request, 'admin/audit/bulk_delete_confirmation.html', context)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def delete_queryset(self, request, queryset):
        """Xóa theo lô DB — tránh timeout khi queryset lớn."""
        pks = list(queryset.values_list('pk', flat=True))
        total = 0
        for start in range(0, len(pks), _DELETE_BATCH_SIZE):
            chunk = pks[start:start + _DELETE_BATCH_SIZE]
            deleted, _ = UserActivityLog.objects.filter(pk__in=chunk).delete()
            total += deleted
        messages.success(request, f'Đã xóa {total:,} nhật ký thao tác.')
