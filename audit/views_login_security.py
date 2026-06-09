from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from assessment.decorators import module_perm_required
from audit.login_security import (
    blacklist_suggestions,
    format_ip_list,
    get_security_config,
    save_login_security_config,
    unlock_ip_block,
    unlock_user_account,
)
from audit.models import IpLoginBlock, UserLoginLock
from hrm.module_permissions import MODULE_AUDIT, user_can_export_module


@module_perm_required(MODULE_AUDIT, 'view')
def login_security_page(request):
    tab = request.GET.get('tab', 'accounts')
    if tab not in ('accounts', 'bots', 'config'):
        tab = 'accounts'

    locked_users = (
        UserLoginLock.objects.filter(locked_at__isnull=False, unlocked_at__isnull=True)
        .select_related('user', 'user__profile', 'unlocked_by')
        .order_by('-locked_at')
    )
    blocked_ips = (
        IpLoginBlock.objects.filter(blocked_at__isnull=False, unlocked_at__isnull=True)
        .select_related('unlocked_by')
        .order_by('-blocked_at')
    )
    recent_user_locks = (
        UserLoginLock.objects.filter(locked_at__isnull=False)
        .select_related('user', 'user__profile', 'unlocked_by')
        .order_by('-locked_at')[:20]
    )
    recent_ip_blocks = IpLoginBlock.objects.order_by('-last_failed_at')[:30]
    security_config = get_security_config()

    return render(request, 'audit/login_security.html', {
        'tab': tab,
        'locked_users': locked_users,
        'blocked_ips': blocked_ips,
        'recent_user_locks': recent_user_locks,
        'recent_ip_blocks': recent_ip_blocks,
        'can_unlock': user_can_export_module(request.user, MODULE_AUDIT),
        'security_config': security_config,
        'wan_whitelist_text': format_ip_list(security_config.wan_whitelist_ips),
        'ip_blacklist_text': format_ip_list(security_config.ip_blacklist),
        'blacklist_suggestions': blacklist_suggestions(),
        'stats': {
            'locked_count': locked_users.count(),
            'blocked_ip_count': blocked_ips.count(),
        },
    })


@module_perm_required(MODULE_AUDIT, 'export')
@require_POST
def save_login_security_config_view(request):
    _, invalid_wan, invalid_blacklist = save_login_security_config(
        wan_whitelist_text=request.POST.get('wan_whitelist_ips', ''),
        ip_blacklist_text=request.POST.get('ip_blacklist', ''),
        admin_user=request.user,
    )
    if invalid_wan:
        messages.error(
            request,
            f'IP WAN không hợp lệ: {", ".join(invalid_wan[:5])}',
        )
    if invalid_blacklist:
        messages.error(
            request,
            'Blacklist chứa IP không hợp lệ hoặc trùng whitelist: '
            f'{", ".join(invalid_blacklist[:5])}',
        )
    if not invalid_wan and not invalid_blacklist:
        messages.success(request, 'Đã lưu cấu hình whitelist / blacklist IP.')
    return redirect(reverse('audit:login_security') + '?tab=config')


@module_perm_required(MODULE_AUDIT, 'export')
@require_POST
def unlock_user_login(request, pk):
    lock = get_object_or_404(UserLoginLock.objects.select_related('user'), pk=pk)
    if not lock.is_locked:
        messages.info(request, 'Tài khoản này không còn bị khóa.')
        return redirect('audit:login_security')

    unlock_user_account(lock=lock, admin_user=request.user)
    messages.success(
        request,
        f'Đã mở khóa đăng nhập cho {lock.user.username}.',
    )
    return redirect('audit:login_security')


@module_perm_required(MODULE_AUDIT, 'export')
@require_POST
def unlock_ip_login(request, pk):
    block = get_object_or_404(IpLoginBlock, pk=pk)
    if not block.is_blocked:
        messages.info(request, 'IP này không còn bị chặn.')
        return redirect(reverse('audit:login_security') + '?tab=bots')

    unlock_ip_block(block=block, admin_user=request.user)
    messages.success(request, f'Đã bỏ chặn IP {block.ip_address}.')
    return redirect(reverse('audit:login_security') + '?tab=bots')
