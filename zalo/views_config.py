"""Trang cấu hình Zalo OA / ZBS OTP (Quản trị hệ thống)."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from assessment.decorators import module_perm_required_methods
from hrm.models import Profile
from hrm.module_permissions import MODULE_AUDIT
from hrm.phone import format_phone_vn, is_valid_vn_mobile, normalize_phone
from zalo.client import (
    ZaloAPIError,
    ZaloClient,
    zalo_has_refresh_token,
    zalo_is_configured,
    zalo_is_ready,
)
from zalo.models import PasswordResetOtp, ZaloOAuthToken


def _mask_secret(value: str, *, keep: int = 4) -> str:
    text = (value or '').strip()
    if not text:
        return ''
    if len(text) <= keep:
        return '•' * len(text)
    return f'{"•" * max(4, len(text) - keep)}{text[-keep:]}'


def _format_otp_rows(rows):
    out = []
    for row in rows:
        out.append({
            'created_at': row.created_at,
            'username': row.user.username,
            'phone_display': format_phone_vn(row.phone) if row.phone else '—',
            'status_display': row.get_status_display(),
        })
    return out


def _status_context() -> dict:
    app_id = (getattr(settings, 'ZALO_APP_ID', '') or '').strip()
    secret = (getattr(settings, 'ZALO_APP_SECRET', '') or '').strip()
    template_id = (getattr(settings, 'ZALO_OTP_TEMPLATE_ID', '') or '').strip()
    oa_id = (getattr(settings, 'ZALO_OA_ID', '') or '').strip()
    param = (getattr(settings, 'ZALO_OTP_TEMPLATE_PARAM', '') or 'otp').strip() or 'otp'
    enabled = bool(getattr(settings, 'ZALO_ENABLED', False))
    development = bool(getattr(settings, 'ZALO_DEVELOPMENT_MODE', True))

    state = ZaloOAuthToken.get_solo()
    expires_local = None
    if state.expires_at:
        expires_local = timezone.localtime(state.expires_at)

    employed = Profile.objects.filter(is_employed=True)
    phone_ok = employed.exclude(phone='').count()
    phone_missing = employed.filter(phone='').count()

    recent_otps = _format_otp_rows(
        PasswordResetOtp.objects.select_related('user')
        .order_by('-created_at')[:8]
    )

    return {
        'zalo_enabled': enabled,
        'zalo_configured': zalo_is_configured(),
        'zalo_ready': zalo_is_ready(),
        'zalo_has_refresh': zalo_has_refresh_token(),
        'zalo_app_id': app_id,
        'zalo_app_id_display': app_id or '—',
        'zalo_has_secret': bool(secret),
        'zalo_secret_masked': _mask_secret(secret) if secret else '',
        'zalo_oa_id': oa_id or '—',
        'zalo_template_id': template_id or '—',
        'zalo_otp_param': param,
        'zalo_development_mode': development,
        'zalo_ttl_seconds': int(getattr(settings, 'ZALO_OTP_TTL_SECONDS', 300) or 300),
        'token_has_access': bool(state.access_token),
        'token_has_refresh': bool(state.refresh_token),
        'token_expires_at': expires_local,
        'token_valid': state.access_token_valid(),
        'token_updated_at': timezone.localtime(state.updated_at) if state.updated_at else None,
        'phone_ok_count': phone_ok,
        'phone_missing_count': phone_missing,
        'recent_otps': recent_otps,
    }


@module_perm_required_methods(MODULE_AUDIT, get='view', post='update')
@require_http_methods(['GET', 'POST'])
def zalo_oa_config_page(request):
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if action == 'exchange_code':
                code = (request.POST.get('auth_code') or '').strip()
                verifier = (request.POST.get('code_verifier') or '').strip()
                if not code:
                    messages.error(request, 'Vui lòng dán authorization code.')
                else:
                    ZaloClient().exchange_authorization_code(code, code_verifier=verifier)
                    messages.success(request, 'Đã đổi code → token và lưu vào DB.')
            elif action == 'refresh_token':
                ZaloClient().get_access_token()
                messages.success(request, 'Đã làm mới access token.')
            elif action == 'send_test_otp':
                phone_raw = (request.POST.get('test_phone') or '').strip()
                otp = (request.POST.get('test_otp') or '123456').strip() or '123456'
                phone = normalize_phone(phone_raw)
                if not is_valid_vn_mobile(phone):
                    messages.error(request, 'SĐT không hợp lệ.')
                elif not otp.isdigit() or not (4 <= len(otp) <= 8):
                    messages.error(request, 'OTP thử phải là 4–8 chữ số.')
                else:
                    development = bool(getattr(settings, 'ZALO_DEVELOPMENT_MODE', True))
                    ZaloClient().send_otp(
                        phone=phone,
                        otp=otp,
                        development=development,
                        tracking_id=f'jp-admin-test-{phone[-4:]}',
                    )
                    mode = 'development' if development else 'production'
                    messages.success(
                        request,
                        f'Đã gửi OTP thử tới {format_phone_vn(phone)} ({mode}).',
                    )
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except ZaloAPIError as exc:
            messages.error(request, str(exc))
        return redirect('audit:zalo_oa')

    return render(request, 'audit/zalo_oa.html', _status_context())
