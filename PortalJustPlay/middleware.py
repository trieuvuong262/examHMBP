from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from audit.zalo_webview import is_zalo_in_app_browser, open_in_browser_context
from PortalJustPlay.pwa import ZALO_DOMAIN_VERIFIER_FILENAME


def _ajax_password_change_required(request):
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('X-CSRFToken')
        or 'application/json' in (request.headers.get('Accept') or '')
    )


class ZaloInAppBrowserMiddleware:
    """Chặn portal trong WebView Zalo — bắt mở Chrome/Safari, tránh nhập sai MK bị khóa."""

    _EXEMPT_PREFIXES = (
        '/static/',
        '/media/',
        '/nhat-ky/rustdesk/api/',
        '/thiet-bi/api/',
    )
    _EXEMPT_EXACT = frozenset({
        '/sw.js',
        '/manifest.webmanifest',
        f'/{ZALO_DOMAIN_VERIFIER_FILENAME}',
    })

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not is_zalo_in_app_browser(request):
            return self.get_response(request)

        path = request.path or '/'
        if path in self._EXEMPT_EXACT or any(path.startswith(p) for p in self._EXEMPT_PREFIXES):
            return self.get_response(request)

        accept = request.headers.get('Accept', '')
        if (
            'application/json' in accept
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        ):
            return JsonResponse(
                {
                    'status': 'error',
                    'open_in_browser': True,
                    'message': 'Portal không dùng trong Zalo. Mở link bằng Chrome hoặc Safari.',
                },
                status=403,
            )

        return render(
            request,
            'registration/zalo_open_browser.html',
            open_in_browser_context(request),
        )


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
        '/zalo_verifierJkUCT9Va0dHBbeT2puK0VXksi7dtm6eYCZ8q.html',
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
                    if _ajax_password_change_required(request):
                        return JsonResponse(
                            {
                                'uploaded': 0,
                                'error': {
                                    'message': 'Vui lòng đổi mật khẩu trước khi tiếp tục.',
                                },
                            },
                            status=403,
                        )
                    return redirect('password_change')

        return self.get_response(request)
