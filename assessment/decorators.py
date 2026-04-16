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
        # Kiểm tra nếu là Admin (is_staff = True) thì cho qua
        if request.user.is_authenticated and request.user.is_staff:
            return view_func(request, *args, **kwargs)
        else:
            # Nếu là User thường, báo lỗi và đá về trang chủ
            messages.error(request, "🚫 CẢNH BÁO: Khu vực này chỉ dành cho Ban Quản Trị Hệ Thống!")
            return redirect('home_portal') # Nhớ thay bằng tên URL trang Portal của ní
    return wrapper