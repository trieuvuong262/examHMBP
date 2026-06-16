from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Chặn mọi trang khi user phải đổi mật khẩu lần đầu (trừ form đổi MK và đăng xuất)."""

    _ALLOWED_PREFIXES = (
        '/change-password',
        '/accounts/logout',
        '/static/',
        '/media/',
    )
    _ALLOWED_EXACT = frozenset({
        '/sw.js',
        '/manifest.webmanifest',
    })

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            profile = getattr(request.user, 'profile', None)
            if profile and profile.must_change_password:
                path = request.path
                login_redirect = reverse('login_redirect')
                allowed_exact = self._ALLOWED_EXACT | {login_redirect}

                if not (
                    path in allowed_exact
                    or any(path.startswith(prefix) for prefix in self._ALLOWED_PREFIXES)
                ):
                    return redirect('password_change')

        return self.get_response(request)
