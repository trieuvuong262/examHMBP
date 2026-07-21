"""Trang quản trị thông báo đẩy (Quản trị hệ thống)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from assessment.decorators import module_perm_required_methods
from hrm.module_permissions import MODULE_AUDIT
from utilities.models import MealPushSubscription, PortalPushConsentLog
from utilities.push_service import webpush_configured


@module_perm_required_methods(MODULE_AUDIT, get='view', post='update')
@require_http_methods(['GET', 'POST'])
def push_config_page(request):
    """Tổng quan và quản lý thiết bị đã đăng ký thông báo đẩy portal."""

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()

        if action == 'delete_subscription':
            pk = request.POST.get('pk') or ''
            try:
                sub = MealPushSubscription.objects.get(pk=int(pk))
                user_label = str(sub.user)
                sub.delete()
                messages.success(request, f'Đã xóa thiết bị đăng ký của {user_label}.')
            except (MealPushSubscription.DoesNotExist, ValueError):
                messages.error(request, 'Không tìm thấy thiết bị.')
            return redirect('audit:push_config')

        if action == 'delete_consent':
            pk = request.POST.get('pk') or ''
            try:
                log = PortalPushConsentLog.objects.get(pk=int(pk))
                user_label = str(log.user)
                log.delete()
                messages.success(request, f'Đã xóa nhật ký đồng ý của {user_label}.')
            except (PortalPushConsentLog.DoesNotExist, ValueError):
                messages.error(request, 'Không tìm thấy bản ghi.')
            return redirect('audit:push_config')

        if action == 'delete_all_expired':
            # Xóa subscription có endpoint trùng lặp hoặc cũ (không xác minh được)
            # Trong portal, subscription hết hạn tự bị xóa khi gửi push thất bại.
            # Ở đây chỉ cho xóa theo user thôi.
            messages.info(request, 'Dùng nút xóa từng thiết bị hoặc liên hệ IT để dọn dẹp hàng loạt.')
            return redirect('audit:push_config')

        messages.error(request, 'Hành động không hợp lệ.')
        return redirect('audit:push_config')

    User = get_user_model()
    subscriptions = (
        MealPushSubscription.objects
        .select_related('user', 'user__profile')
        .order_by('-created_at')
    )
    consent_logs = (
        PortalPushConsentLog.objects
        .select_related('user', 'user__profile')
        .order_by('-updated_at')
    )

    total_subs = subscriptions.count()
    total_users = subscriptions.values('user').distinct().count()
    total_granted = consent_logs.filter(browser_permission='granted').count()
    total_denied = consent_logs.filter(browser_permission='denied').count()

    return render(request, 'audit/push_config.html', {
        'subscriptions': subscriptions,
        'consent_logs': consent_logs,
        'total_subs': total_subs,
        'total_users': total_users,
        'total_granted': total_granted,
        'total_denied': total_denied,
        'push_configured': webpush_configured(),
    })
