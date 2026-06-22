"""Deep link RustDesk client — mở app trên máy IT (không remote trong trình duyệt)."""

from __future__ import annotations

from urllib.parse import urlencode


def build_rustdesk_connect_url(rustdesk_id: str, password: str = '') -> str:
    """rustdesk://connection/new/{id}?password=… — dùng khi bấm Kết nối từ Portal."""
    digits = ''.join(c for c in (rustdesk_id or '') if c.isdigit())
    if not digits:
        return ''
    path = f'rustdesk://connection/new/{digits}'
    pwd = (password or '').strip()
    if pwd:
        return f'{path}?{urlencode({"password": pwd})}'
    return path
