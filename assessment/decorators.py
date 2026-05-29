from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

from hrm.module_permissions import (
    MODULE_PERMISSIONS,
    bypass_department_modules,
    resolve_module_from_request,
    user_can_edit_module,
)
from hrm.permissions import portal_admin_denied_message


def _wants_json_response(request):
    accept = request.headers.get('Accept', '')
    content_type = request.headers.get('Content-Type', '')
    return (
        'application/json' in accept
        or 'application/json' in content_type
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('X-CSRFToken')
    )


def _user_can_admin_request(request) -> bool:
    user = request.user
    if not user.is_authenticated:
        return False
    if bypass_department_modules(user):
        return True

    path = request.path
    module = resolve_module_from_request(path, request.GET.get('tab'))
    if module:
        return user_can_edit_module(user, module)

    return user_can_edit_module(user, MODULE_PERMISSIONS)


def admin_only(view_func):
    """
    Chỉ cho phép user có quyền cập nhật module tương ứng URL.
    Request AJAX/fetch nhận JSON thay vì redirect HTML.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if _user_can_admin_request(request):
            return view_func(request, *args, **kwargs)

        message = portal_admin_denied_message()
        if _wants_json_response(request):
            return JsonResponse({'status': 'error', 'message': message}, status=403)

        messages.error(request, message)
        return redirect('home_portal')

    return wrapper
