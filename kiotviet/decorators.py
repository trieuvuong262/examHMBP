from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .access import kiotviet_is_live, user_can_use_kiotviet


def kiotviet_access_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not kiotviet_is_live():
            messages.error(
                request,
                'KiotViet mirror chưa sẵn sàng (.env: KIOTVIET_USE_LOCAL_MIRROR=1 và KIOTVIET_RETAILER).',
            )
            return redirect('home_portal')
        if not user_can_use_kiotviet(request.user):
            messages.error(request, 'Bạn không có quyền truy cập module KiotViet.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)

    return wrapper
