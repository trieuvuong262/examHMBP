"""Chỉ portal admin (is_staff) được vào Company Trip / Lucky Spin."""

from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

from hrm.permissions import is_portal_admin


def company_trip_admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if is_portal_admin(request.user):
            return view_func(request, *args, **kwargs)
        message = 'Chỉ quản trị viên mới được truy cập mục này.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (
            request.headers.get('Accept') or ''
        ):
            return JsonResponse({'ok': False, 'message': message}, status=403)
        messages.error(request, message)
        return redirect('home_portal')

    return wrapper
