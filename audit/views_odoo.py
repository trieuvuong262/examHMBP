from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from assessment.decorators import module_perm_required
from audit.services.odoo_sync import ensure_portal_user_in_odoo, odoo_login_url
from hrm.module_permissions import MODULE_ODOO


@login_required
@module_perm_required(MODULE_ODOO, 'view')
def odoo_redirect(request):
    """User có quyền module Odoo — đồng bộ tài khoản rồi chuyển sang ERP."""
    result = ensure_portal_user_in_odoo(request.user)
    if result.get('status') == 'error':
        messages.error(request, f'Không đồng bộ được tài khoản Odoo: {result.get("error")}')
    elif result.get('status') == 'skipped' and result.get('reason') == 'not_configured':
        messages.warning(
            request,
            'Chưa cấu hình ODOO_URL / ODOO_API_* trên Portal — vẫn mở ERP nhưng cần IT tạo user thủ công.',
        )
    elif result.get('created') and result.get('temp_password'):
        messages.info(
            request,
            'Đã tạo tài khoản Odoo. Mật khẩu tạm: '
            f'{result["temp_password"]} — đăng nhập ERP và đổi mật khẩu, hoặc đổi mật khẩu Portal để đồng bộ.',
        )
    elif result.get('status') == 'ok':
        messages.success(request, 'Đã đồng bộ tài khoản Odoo.')

    target = odoo_login_url(request.user)
    return redirect(target)
