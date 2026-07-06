"""Deep link RustDesk client — mở app trên máy IT (không remote trong trình duyệt)."""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings


def effective_rustdesk_password(host_password: str = '') -> str:
    """Ưu tiên RUSTDESK_CLIENT_PASSWORD (.env) — tránh mật khẩu cũ trong DB."""
    env = (getattr(settings, 'RUSTDESK_CLIENT_PASSWORD', '') or '').strip()
    if env:
        return env
    return (host_password or '').strip()


def build_rustdesk_connect_url(rustdesk_id: str, password: str = '') -> str:
    """Máy IT Ready → connection/new + password trong URL (không hộp thoại nếu máy đích khớp)."""
    digits = ''.join(c for c in (rustdesk_id or '') if c.isdigit())
    if not digits:
        return ''

    path = f'rustdesk://connection/new/{digits}'
    approve = (getattr(settings, 'RUSTDESK_APPROVE_MODE', '') or 'password').strip().lower()
    if approve == 'click':
        return path

    pwd = effective_rustdesk_password(password)
    if pwd:
        # quote(safe='') — tránh quote_plus biến khoảng trắng thành '+' (RustDesk có thể hiểu sai).
        return f'{path}?password={quote(pwd, safe="")}'
    return path
