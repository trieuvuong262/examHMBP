from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KIOTVIET

from .access import kiotviet_is_live


def kiotviet_access_required(view_func):
    @module_perm_required(MODULE_KIOTVIET, 'view')
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not kiotviet_is_live():
            messages.error(
                request,
                'KiotViet mirror chưa sẵn sàng (.env: KIOTVIET_USE_LOCAL_MIRROR=1 và KIOTVIET_RETAILER).',
            )
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)

    return wrapper
