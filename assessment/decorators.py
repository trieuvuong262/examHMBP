from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect


def _wants_json_response(request):
    accept = request.headers.get('Accept', '')
    content_type = request.headers.get('Content-Type', '')
    return (
        'application/json' in accept
        or 'application/json' in content_type
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('X-CSRFToken')
    )


def admin_only(view_func):
    """
    Chỉ cho phép staff. Request AJAX/fetch nhận JSON thay vì redirect HTML.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return view_func(request, *args, **kwargs)

        message = 'Chức năng này chỉ dành cho Ban Quản Trị Hệ Thống!'
        if _wants_json_response(request):
            return JsonResponse({'status': 'error', 'message': message}, status=403)

        messages.error(request, message)
        return redirect('home_portal')

    return wrapper
