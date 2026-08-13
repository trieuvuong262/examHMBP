"""Phát hiện Zalo in-app browser — portal chỉ dùng trên Chrome/Safari."""

from __future__ import annotations

import re
from urllib.parse import quote, urlparse

from django.http import HttpRequest

# UA Zalo WebView: "... Zalo android / 250", "... Zalo iOS / 451", "ZaloAndroid"
_ZALO_INAPP_UA_RE = re.compile(r'zalo', re.I)
_ANDROID_UA_RE = re.compile(r'android', re.I)
_IOS_UA_RE = re.compile(r'(iphone|ipad|ipod|ios)', re.I)


def request_user_agent(request: HttpRequest) -> str:
    return request.META.get('HTTP_USER_AGENT', '') or ''


def is_zalo_in_app_browser(request: HttpRequest) -> bool:
    return bool(_ZALO_INAPP_UA_RE.search(request_user_agent(request)))


def is_android_ua(request: HttpRequest) -> bool:
    return bool(_ANDROID_UA_RE.search(request_user_agent(request)))


def is_ios_ua(request: HttpRequest) -> bool:
    return bool(_IOS_UA_RE.search(request_user_agent(request)))


def chrome_intent_url(absolute_url: str) -> str:
    """Intent mở Chrome trên Android từ WebView Zalo."""
    parsed = urlparse(absolute_url)
    host_path = parsed.netloc + (parsed.path or '/')
    if parsed.query:
        host_path = f'{host_path}?{parsed.query}'
    fallback = quote(absolute_url, safe='')
    return (
        f'intent://{host_path}#Intent;scheme=https;package=com.android.chrome;'
        f'S.browser_fallback_url={fallback};end'
    )


def open_in_browser_context(request: HttpRequest) -> dict:
    page_url = request.build_absolute_uri()
    android = is_android_ua(request)
    return {
        'page_url': page_url,
        'is_android': android,
        'is_ios': is_ios_ua(request),
        'chrome_intent_url': chrome_intent_url(page_url) if android else '',
        'jp_page_title': 'Mở bằng trình duyệt - Just Play Portal',
    }
