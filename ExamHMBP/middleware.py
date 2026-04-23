from django.shortcuts import redirect
from django.urls import reverse

class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Kiểm tra xem user có thuộc tính này không để tránh lỗi AttributeError
            if getattr(request.user, 'is_first_login', False):
                # Các link bỏ qua để không bị vòng lặp
                allowed_urls = [
                    reverse('password_change'),
                    reverse('password_change_done'),
                    reverse('logout'),
                ]
                
                # Không chặn trang Admin và Static/Media
                if not any([
                    request.path in allowed_urls,
                    request.path.startswith('/admin/'),
                    request.path.startswith('/static/'),
                    request.path.startswith('/media/'),
                ]):
                    return redirect('password_change')
        
        return self.get_response(request)