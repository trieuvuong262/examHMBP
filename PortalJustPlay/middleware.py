from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            profile = getattr(request.user, 'profile', None)
            if profile and profile.must_change_password:
                allowed_urls = [
                    reverse('password_change'),
                    reverse('password_change_done'),
                    reverse('logout'),
                    reverse('login_redirect'),
                ]

                if not any([
                    request.path in allowed_urls,
                    request.path.startswith('/admin/'),
                    request.path.startswith('/admin-panel/'),
                    request.path.startswith('/accounts/'),
                    request.path.startswith('/static/'),
                    request.path.startswith('/media/'),
                    request.path.startswith('/thiet-bi/agent/'),
                    request.path in ('/sw.js', '/manifest.webmanifest'),
                ]):
                    return redirect('password_change')

        return self.get_response(request)
