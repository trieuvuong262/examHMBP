"""Trang cấu hình SMTP email (Quản trị hệ thống)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from assessment.decorators import module_perm_required_methods
from audit.email_smtp import email_is_configured, send_portal_mail, smtp_status_dict
from audit.models import EmailSmtpConfig
from hrm.module_permissions import MODULE_AUDIT
from hrm.models import Profile


@module_perm_required_methods(MODULE_AUDIT, get='view', post='update')
@require_http_methods(['GET', 'POST'])
def email_config_page(request):
    cfg = EmailSmtpConfig.get_solo()

    if request.method == 'POST':
        action = (request.POST.get('action') or 'save').strip()
        if action == 'save':
            cfg.enabled = (request.POST.get('enabled') or '') in ('1', 'on', 'true', 'yes')
            cfg.host = (request.POST.get('host') or '').strip()
            try:
                cfg.port = max(1, int(request.POST.get('port') or 587))
            except (TypeError, ValueError):
                cfg.port = 587
            cfg.username = (request.POST.get('username') or '').strip()
            new_password = request.POST.get('password')
            if new_password is not None and str(new_password).strip() != '':
                cfg.password = str(new_password).strip()
            cfg.use_tls = (request.POST.get('use_tls') or '') in ('1', 'on', 'true', 'yes')
            cfg.use_ssl = (request.POST.get('use_ssl') or '') in ('1', 'on', 'true', 'yes')
            if cfg.use_ssl:
                cfg.use_tls = False
            cfg.from_email = (request.POST.get('from_email') or '').strip()
            cfg.updated_by = request.user
            cfg.save()
            messages.success(request, 'Đã lưu cấu hình SMTP.')
            return redirect('audit:email_config')

        if action == 'send_test':
            to_email = (request.POST.get('test_email') or '').strip()
            if not to_email or '@' not in to_email:
                messages.error(request, 'Email nhận thử không hợp lệ.')
            elif not email_is_configured():
                messages.error(request, 'Chưa cấu hình SMTP (bật + host + From, hoặc .env).')
            else:
                try:
                    send_portal_mail(
                        'JustPlay Portal — Email thử',
                        (
                            'Đây là email kiểm tra SMTP từ JustPlay Portal.\n'
                            'Nếu bạn nhận được thư này, cấu hình email đã hoạt động.\n'
                        ),
                        [to_email],
                    )
                    messages.success(request, f'Đã gửi email thử tới {to_email}.')
                except Exception as exc:
                    messages.error(request, f'Gửi thử thất bại: {exc}')
            return redirect('audit:email_config')

        messages.error(request, 'Hành động không hợp lệ.')
        return redirect('audit:email_config')

    employed = Profile.objects.filter(is_employed=True).select_related('user')
    with_email = 0
    without_email = 0
    for p in employed:
        if (p.user.email or '').strip():
            with_email += 1
        else:
            without_email += 1

    # admin có thể không có profile employed
    admin = User.objects.filter(username='admin').first()
    admin_email = (admin.email or '').strip() if admin else ''

    return render(request, 'audit/email_config.html', {
        'cfg': cfg,
        'status': smtp_status_dict(),
        'users_with_email': with_email,
        'users_without_email': without_email,
        'admin_email': admin_email,
        'test_email_default': admin_email or (request.user.email or ''),
    })
