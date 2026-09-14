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
from hrm.menu_permissions import user_can_export_menu, user_can_update_menu
from hrm.module_permissions import MODULE_AUDIT, MODULE_HRM


def _locked_users_qs():
    return (
        UserLoginLock.objects.filter(locked_at__isnull=False, unlocked_at__isnull=True)
        .select_related('user', 'user__profile', 'unlocked_by')
        .order_by('-locked_at')
    )


@module_perm_required(MODULE_HRM, 'view')
def locked_accounts_page(request):
    locked_users = _locked_users_qs()
    return render(request, 'assessment/admin/locked_accounts.html', {
        'locked_users': locked_users,
        'can_unlock': user_can_update_menu(request.user, MODULE_HRM, 'locked_accounts'),
        'locked_count': locked_users.count(),
    })


@module_perm_required(MODULE_AUDIT, 'view')
def login_security_page(request):
    tab = request.GET.get('tab', 'bots')
    if tab == 'accounts':
        return redirect('locked_accounts')
    if tab not in ('bots', 'config', 'filescan'):
        tab = 'bots'

    blocked_ips = (
        IpLoginBlock.objects.filter(blocked_at__isnull=False, unlocked_at__isnull=True)
        .select_related('unlocked_by')
        .order_by('-blocked_at')
    )
    recent_ip_blocks = IpLoginBlock.objects.order_by('-last_failed_at')[:30]
    security_config = get_security_config()

    ctx = {
        'tab': tab,
        'blocked_ips': blocked_ips,
        'recent_ip_blocks': recent_ip_blocks,
        'can_unlock': user_can_export_menu(request.user, MODULE_AUDIT, 'login_security'),
        'security_config': security_config,
        'wan_whitelist_text': format_ip_list(security_config.wan_whitelist_ips),
        'ip_blacklist_text': format_ip_list(security_config.ip_blacklist),
        'blacklist_suggestions': blacklist_suggestions(),
        'stats': {
            'blocked_ip_count': blocked_ips.count(),
        },
    }

    # Chỉ ping clamd khi thực sự mở tab đó — tránh thêm I/O mạng cho 2 tab kia.
    if tab == 'filescan':
        from audit.file_scan_config import (
            configured_allowed_extensions,
            get_config,
            scanner_status,
            upload_limits_mb,
        )
        from audit.models import UserActivityLog

        cfg = get_config()
        ctx['file_scan_config'] = cfg
        ctx['scanner'] = scanner_status()
        ctx['allowed_exts'] = configured_allowed_extensions()
        ctx['allowed_exts_text'] = '\n'.join(ctx['allowed_exts'])
        ctx['extensions_is_custom'] = bool(getattr(cfg, 'allowed_extensions', None))
        ctx['upload_limits_mb'] = upload_limits_mb()
        ctx['upload_block_logs'] = (
            UserActivityLog.objects
            .filter(object_type='upload_rejected')
            .order_by('-created_at')[:50]
        )

    return render(request, 'audit/login_security.html', ctx)


@module_perm_required(MODULE_AUDIT, 'export')
@require_POST
def save_file_scan_config_view(request):
    """Lưu công tắc quét virus + giới hạn dung lượng upload."""
    from audit.file_scan_config import force_off, save_config, upload_limits_mb

    enabled = request.POST.get('enabled') == 'on'
    fail_closed = request.POST.get('fail_closed') == 'on'
    defaults = upload_limits_mb()
    save_config(
        enabled=enabled,
        fail_closed=fail_closed,
        admin_user=request.user,
        max_mb_image=request.POST.get('max_mb_image', defaults['image']),
        max_mb_doc=request.POST.get('max_mb_doc', defaults['doc']),
        max_mb_archive=request.POST.get('max_mb_archive', defaults['archive']),
        max_mb_design=request.POST.get('max_mb_design', defaults['design']),
        max_mb_video=request.POST.get('max_mb_video', defaults['video']),
    )

    if enabled:
        from nas_storage.av_scan import ping

        if force_off():
            messages.warning(
                request,
                'Đã lưu, nhưng AV_SCAN_FORCE_OFF đang bật trong .env nên vẫn KHÔNG quét. '
                'Bỏ biến đó rồi deploy lại.',
            )
        elif not ping():
            messages.warning(
                request,
                'Đã bật công tắc, nhưng chưa liên lạc được ClamAV nên file vẫn chưa '
                'được quét. Kiểm tra container: AV_SCAN_ENABLED=1 trong .env rồi '
                '"docker compose up -d clamav". Lần đầu tải signature mất vài phút.',
            )
        else:
            messages.success(request, 'Đã bật quét virus file upload và lưu giới hạn dung lượng.')
    else:
        messages.success(request, 'Đã tắt quét virus file upload. Đã lưu giới hạn dung lượng.')

    return redirect(reverse('audit:login_security') + '?tab=filescan')


@module_perm_required(MODULE_AUDIT, 'export')
@require_POST
def save_file_scan_extensions_view(request):
    """Lưu / khôi phục danh sách đuôi file được phép upload."""
    from audit.file_scan_config import parse_extensions_input, save_allowed_extensions

    if request.POST.get('reset_default') == '1':
        save_allowed_extensions(extensions=[], admin_user=request.user, reset_default=True)
        messages.success(request, 'Đã khôi phục danh sách định dạng mặc định trong mã.')
        return redirect(reverse('audit:login_security') + '?tab=filescan')

    valid, rejected = parse_extensions_input(request.POST.get('allowed_extensions', ''))
    if not valid:
        messages.error(
            request,
            'Danh sách trống hoặc không hợp lệ. Giữ ít nhất một đuôi an toàn, '
            'hoặc dùng «Khôi phục mặc định».',
        )
        return redirect(reverse('audit:login_security') + '?tab=filescan')

    save_allowed_extensions(extensions=valid, admin_user=request.user)
    msg = f'Đã lưu {len(valid)} định dạng được phép.'
    if rejected:
        msg += f' Bỏ qua (nguy hiểm/không hợp lệ): {", ".join(rejected[:12])}'
        messages.warning(request, msg)
    else:
        messages.success(request, msg)
    return redirect(reverse('audit:login_security') + '?tab=filescan')


@module_perm_required(MODULE_AUDIT, 'export')
@require_POST
def test_file_scan_view(request):
    """Gửi chuỗi thử EICAR để xác nhận scanner thực sự phát hiện được."""
    import io

    from nas_storage.av_scan import scan_stream
    from nas_storage.management.commands.av_status import EICAR

    result = scan_stream(io.BytesIO(EICAR), size=len(EICAR))
    if result.is_infected:
        messages.success(
            request,
            f'Scanner hoạt động đúng — phát hiện chuỗi thử EICAR ({result.signature}).',
        )
    elif result.is_clean:
        messages.error(
            request,
            'Scanner báo chuỗi thử EICAR là SẠCH — không hoạt động đúng. Liên hệ IT.',
        )
    else:
        messages.error(
            request,
            f'Không quét được ({result.status}): {result.detail}',
        )
    return redirect(reverse('audit:login_security') + '?tab=filescan')


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


@module_perm_required(MODULE_HRM, 'update')
@require_POST
def unlock_user_login(request, pk):
    lock = get_object_or_404(UserLoginLock.objects.select_related('user'), pk=pk)
    if not lock.is_locked:
        messages.info(request, 'Tài khoản này không còn bị khóa.')
        return redirect('locked_accounts')

    unlock_user_account(lock=lock, admin_user=request.user)
    messages.success(
        request,
        f'Đã mở khóa đăng nhập cho {lock.user.username}.',
    )
    return redirect('locked_accounts')


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
