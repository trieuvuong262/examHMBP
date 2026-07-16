from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from hrm.module_permissions import (
    MODULE_KIOTVIET,
    MODULE_SAN_XUAT,
    bypass_department_modules,
    user_can_access_module,
)

from .access import kiotviet_is_live


def kiotviet_access_required(view_func):
    """Cho phép MODULE_KIOTVIET, hoặc MODULE_SAN_XUAT khi request.kv_embed_urls (nhúng hub SX)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not getattr(user, 'is_authenticated', False):
            messages.error(request, 'Vui lòng đăng nhập.')
            return redirect('login')

        embed = bool(getattr(request, 'kv_embed_urls', None))
        allowed = bypass_department_modules(user) or user_can_access_module(user, MODULE_KIOTVIET)
        if not allowed and embed:
            allowed = user_can_access_module(user, MODULE_SAN_XUAT)
        if not allowed:
            messages.error(request, 'Bạn không có quyền truy cập dữ liệu KiotViet.')
            return redirect('home_portal')

        if not kiotviet_is_live():
            messages.error(
                request,
                'KiotViet mirror chưa sẵn sàng (.env: KIOTVIET_USE_LOCAL_MIRROR=1 và KIOTVIET_RETAILER).',
            )
            return redirect('san_xuat:overview' if embed else 'home_portal')
        return view_func(request, *args, **kwargs)

    return wrapper
