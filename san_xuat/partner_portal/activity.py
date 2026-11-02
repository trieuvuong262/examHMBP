"""Nhật ký thao tác + giới hạn đăng nhập theo IP cho cổng đối tác pn."""

from __future__ import annotations

from django.core.cache import cache

from san_xuat.partner_models import GcPartnerActivity

IP_MAX_FAILED = 20
IP_WINDOW_SECONDS = 15 * 60


def client_ip(request) -> str | None:
    # IP từ proxy (không dùng header/cookie máy trạm tự khai — đối tác có thể giả).
    from audit.utils import get_forwarded_client_ip

    ip = (get_forwarded_client_ip(request) or '').strip()
    return ip or None


def log(request, action: str, *, account=None, partner=None, order=None, detail: str = '', username: str = '') -> None:
    acc = account if account is not None else getattr(request, 'gc_account', None)
    GcPartnerActivity.objects.create(
        partner=partner or (acc.partner if acc else None),
        account=acc,
        username=(username or (acc.username if acc else ''))[:60],
        action=action,
        order=order,
        detail=(detail or '')[:255],
        ip=client_ip(request),
        user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
    )


def _ip_key(ip: str) -> str:
    return f'gcpn-login-fail:{ip}'


def ip_blocked(request) -> bool:
    ip = client_ip(request)
    return bool(ip) and int(cache.get(_ip_key(ip)) or 0) >= IP_MAX_FAILED


def record_ip_failure(request) -> None:
    ip = client_ip(request)
    if not ip:
        return
    key = _ip_key(ip)
    if cache.add(key, 1, IP_WINDOW_SECONDS):
        return
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, IP_WINDOW_SECONDS)


def clear_ip_failures(request) -> None:
    ip = client_ip(request)
    if ip:
        cache.delete(_ip_key(ip))
