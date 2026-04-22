from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def admin_only(view_func):
    """
    Decorator này chặn không cho User thường vào.
    Nếu cố tình vào, sẽ bị đá về trang Portal (home_portal) kèm cảnh báo.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "Chức năng này chỉ dành cho Ban Quản Trị Hệ Thống!")
            return redirect('home_portal') 
    return wrapper