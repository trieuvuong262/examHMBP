from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

# Host vào bằng HTTP (IP) — cookie Secure=True sẽ bị trình duyệt bỏ.
HTTP_IP_HOSTS = frozenset({
    '103.90.224.203',
    '100.79.206.125',
})

from audit.zalo_webview import is_zalo_in_app_browser, open_in_browser_context
from PortalJustPlay.pwa import ZALO_DOMAIN_VERIFIER_FILENAME


def _ajax_password_change_required(request):
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('X-CSRFToken')
        or 'application/json' in (request.headers.get('Accept') or '')
    )


class RelaxSecureCookiesOnHttpIpMiddleware:
    """Session/CSRF trên http://IP khi DNS hoặc FortiGate chặn HTTPS theo IP."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        host = (request.get_host() or '').split(':')[0]
        if host in HTTP_IP_HOSTS and not request.is_secure():
            for attr in ('SESSION_COOKIE_NAME', 'CSRF_COOKIE_NAME'):
                name = getattr(settings, attr, None)
                if name and name in response.cookies:
                    response.cookies[name]['secure'] = False
        return response


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


class ReadOnlyAccountMiddleware:
    """Tài khoản demo (hrm.user_search.READ_ONLY_USERNAMES) chỉ được xem.

    - Chặn mọi request ghi (POST/PUT/PATCH/DELETE), trừ đăng xuất.
    - Chặn GET tới URL thao tác: in, PDF, xuất/nhập Excel, tải về, xóa, sửa, tạo,
      duyệt, đổi/đặt lại mật khẩu…; chặn toàn bộ admin-panel và hàng đợi job.
    - Trang HTML được chèn CSS @media print để bản in (Ctrl+P) ra trắng.
    """

    _SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})
    _WRITE_ALLOWED_PREFIXES = (
        '/accounts/logout',
        '/accounts/login',
    )
    _ALWAYS_ALLOWED_PREFIXES = (
        '/static/',
        '/media/',
        '/accounts/logout',
    )
    _BLOCKED_PREFIXES = (
        '/admin-panel/',
        '/hang-doi/',
        '/change-password',
        '/accounts/password',
    )
    # Token trong url_name (tách theo '_' / '-') → coi là thao tác, không phải xem.
    _BLOCKED_NAME_TOKENS = frozenset({
        'print', 'pdf', 'export', 'excel', 'xlsx', 'csv', 'zip', 'download', 'import',
        'upload', 'delete', 'toggle', 'approve', 'reject', 'cancel', 'restore', 'backup',
        'clone', 'duplicate', 'copy', 'sync', 'reset', 'revoke', 'reissue', 'mark',
        'password', 'create', 'add', 'edit', 'update', 'save', 'run', 'watermark',
    })
    # Trang demo không được xem dù nhóm quyền có bật (Danh sách nhân sự).
    _BLOCKED_URL_NAMES = frozenset({'user_list'})
    # Đoạn path nguyên vẹn (giữa các '/') → thao tác.
    _BLOCKED_PATH_SEGMENTS = frozenset({
        'in', 'print', 'pdf', 'xoa', 'delete', 'export', 'xuat-excel', 'download',
        'tai-ve', 'import', 'edit', 'sua',
    })
    _PRINT_BLOCK_STYLE = (
        '<style id="readonly-no-print">@media print{body>*{display:none!important}'
        'body::after{content:"Tài khoản demo không được in.";'
        'display:block;padding:2rem;font-size:18px}}</style>'
    ).encode('utf-8')
    _FILE_CONTENT_TYPES = (
        'application/pdf',
        'application/vnd.',
        'application/msword',
        'application/zip',
        'application/octet-stream',
        'text/csv',
    )
    MESSAGE = 'Tài khoản demo chỉ được xem — không được thêm, sửa, xóa, in, xuất hay đổi mật khẩu.'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from hrm.user_search import is_read_only_account

        if not is_read_only_account(getattr(request, 'user', None)):
            return self.get_response(request)

        path = request.path or '/'
        if any(path.startswith(p) for p in self._ALWAYS_ALLOWED_PREFIXES):
            return self.get_response(request)

        if self._is_blocked(request, path):
            return self._deny(request)

        response = self.get_response(request)
        return self._inject_print_block(response)

    def _is_blocked(self, request, path: str) -> bool:
        if request.method not in self._SAFE_METHODS:
            return not any(path.startswith(p) for p in self._WRITE_ALLOWED_PREFIXES)
        if any(path.startswith(p) for p in self._BLOCKED_PREFIXES):
            return True
        segments = {s.lower() for s in path.split('/') if s}
        if segments & self._BLOCKED_PATH_SEGMENTS:
            return True
        lowered = path.lower()
        if lowered.endswith(('.pdf', '.xlsx', '.xls', '.csv', '.zip', '.docx')):
            return True
        from django.urls import Resolver404, resolve

        try:
            match = resolve(path, getattr(request, 'urlconf', None))
        except Resolver404:
            return False
        name = (match.url_name or '').lower()
        if name in self._BLOCKED_URL_NAMES:
            return True
        tokens = set(name.replace('-', '_').split('_'))
        return bool(tokens & self._BLOCKED_NAME_TOKENS)

    def _deny(self, request):
        from django.contrib import messages
        from django.http import HttpResponseForbidden

        if _ajax_password_change_required(request) or (
            request.method not in self._SAFE_METHODS
            and request.headers.get('Content-Type', '').startswith('application/json')
        ):
            return JsonResponse({'status': 'error', 'message': self.MESSAGE}, status=403)
        if request.method in self._SAFE_METHODS:
            return HttpResponseForbidden(self.MESSAGE)
        messages.error(request, self.MESSAGE)
        referer = request.META.get('HTTP_REFERER') or ''
        from django.utils.http import url_has_allowed_host_and_scheme

        if referer and url_has_allowed_host_and_scheme(
            referer, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
        ):
            return redirect(referer)
        return redirect('/')

    def _inject_print_block(self, response):
        from django.http import HttpResponseForbidden

        content_type = (response.get('Content-Type') or '').lower()
        disposition = (response.get('Content-Disposition') or '').lower()
        # Lưới an toàn: view nào trả file tải về / PDF / Excel mà URL lọt bộ lọc.
        if 'attachment' in disposition or content_type.startswith(self._FILE_CONTENT_TYPES):
            if hasattr(response, 'close'):
                response.close()
            return HttpResponseForbidden(self.MESSAGE)
        if (
            getattr(response, 'streaming', False)
            or 'text/html' not in content_type
            or response.status_code != 200
        ):
            return response
        content = response.content
        marker = b'</head>'
        idx = content.lower().find(marker)
        if idx == -1:
            return response
        response.content = content[:idx] + self._PRINT_BLOCK_STYLE + content[idx:]
        if response.has_header('Content-Length'):
            response['Content-Length'] = str(len(response.content))
        return response
