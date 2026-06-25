from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from assessment.decorators import module_perm_required
from audit.services.odoo_sso import ensure_odoo_account_for_redirect, odoo_entry_url, odoo_sso_configured
from hrm.module_permissions import MODULE_ODOO


@login_required
@module_perm_required(MODULE_ODOO, 'view')
def odoo_redirect(request):
    """Vào Odoo — SSO token (nhanh) hoặc login thường."""
    result = ensure_odoo_account_for_redirect(request.user)

    if result.get('status') == 'error':
        messages.error(request, f'Không đồng bộ được tài khoản Odoo: {result.get("error")}')
    elif result.get('status') == 'skipped' and result.get('reason') == 'not_configured':
        messages.warning(
            request,
            'Chưa cấu hình Odoo API — vẫn mở ERP nhưng cần IT tạo user thủ công.',
        )
    elif result.get('created') and result.get('temp_password'):
        messages.info(
            request,
            'Đã tạo tài khoản Odoo. Mật khẩu tạm: '
            f'{result["temp_password"]} — đổi mật khẩu Portal để đồng bộ.',
        )
    elif result.get('status') == 'ok' and not result.get('password_synced', True) and not result.get('skipped_sync'):
        login = result.get('login') or request.user.username
        messages.warning(
            request,
            f'Tài khoản ERP: {login}. Đổi mật khẩu Portal (hoặc nhờ HR reset) để đăng nhập ERP.',
        )
    elif odoo_sso_configured() and result.get('status') == 'ok':
        pass  # SSO — không cần flash message
    elif result.get('status') == 'ok':
        messages.success(request, 'Đã mở Odoo ERP.')

    return redirect(odoo_entry_url(request.user))
