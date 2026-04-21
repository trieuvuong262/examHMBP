from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from functools import wraps
from django.shortcuts import redirect

def admin_only(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # 1. Chưa đăng nhập -> Đá ra trang Login
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        
        # 2. Đăng nhập rồi nhưng không phải Staff -> Đá về trang chủ portal
        if not request.user.is_staff:
            messages.error(request, "Truy cập bị từ chối: Chức năng này chỉ dành cho Ban Quản Trị!")
            return redirect('home_portal')
            
        # 3. Hợp lệ -> Cho đi tiếp
        return view_func(request, *args, **kwargs)
    return wrapper