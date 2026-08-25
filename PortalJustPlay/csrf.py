"""Trang CSRF 403 thân thiện — hướng dẫn mở lại trình duyệt / về đăng nhập."""

from __future__ import annotations

import re
from urllib.parse import urlencode

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from audit.login_security import it_contact_display
from audit.zalo_webview import (
    chrome_intent_url,
    is_android_ua,
    is_ios_ua,
    is_zalo_in_app_browser,
    open_in_browser_context,
)

_INAPP_UA_RE = re.compile(
    r'(FBAN|FBAV|FB_IAB|FBIOS|Instagram|Line/|MicroMessenger)',
    re.I,
)


def _is_ajax(request) -> bool:
    accept = request.headers.get('Accept') or ''
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or bool(request.headers.get('X-CSRFToken'))
        or 'application/json' in accept
    )


def _is_in_app_browser(request) -> bool:
    if is_zalo_in_app_browser(request):
        return True
    ua = request.META.get('HTTP_USER_AGENT', '') or ''
    return bool(_INAPP_UA_RE.search(ua))


def _retry_url(request) -> str:
    path = request.get_full_path() or '/'
    if request.method != 'GET' and path.startswith('/accounts/login'):
        return reverse('login')
    return path


def _login_url(retry_url: str) -> str:
    login_url = reverse('login')
    params = {'csrf': '1'}
    if retry_url and not retry_url.startswith(login_url):
        params['next'] = retry_url
    return f'{login_url}?{urlencode(params)}'


@never_cache
def csrf_failure(request, reason=''):
    """Thay trang 403 mặc định của Django khi token CSRF không hợp lệ."""
    login_url = reverse('login')
    retry_url = _retry_url(request)
    message = (
        'Phiên làm việc hết hạn hoặc trình duyệt chặn cookie. '
        'Tải lại trang, đóng hẳn trình duyệt rồi mở lại, hoặc đăng nhập lại.'
    )

    if _is_ajax(request):
        return JsonResponse(
            {
                'status': 'error',
                'csrf': True,
                'open_in_browser': is_zalo_in_app_browser(request),
                'message': message,
                'login_url': login_url,
            },
            status=403,
        )

    if is_zalo_in_app_browser(request):
        return render(
            request,
            'registration/zalo_open_browser.html',
            open_in_browser_context(request),
            status=403,
        )

    android = is_android_ua(request)
    portal_url = (getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '') or 'https://portal.justplay.vn').rstrip('/')
    context = {
        'jp_page_title': 'Phiên làm việc hết hạn',
        'retry_url': retry_url,
        'login_href': _login_url(retry_url),
        'portal_url': portal_url,
        'it_contact': it_contact_display(),
        'is_authenticated': bool(getattr(request.user, 'is_authenticated', False)),
        'in_app_browser': _is_in_app_browser(request),
        'is_android': android,
        'is_ios': is_ios_ua(request),
        'chrome_intent_url': chrome_intent_url(portal_url) if android else '',
        'debug_reason': reason if settings.DEBUG else '',
    }
    return render(request, 'registration/csrf_failure.html', context, status=403)
