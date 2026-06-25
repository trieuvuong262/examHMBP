"""Token SSO Portal → Odoo (HMAC, TTL ngắn)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.models import User

from audit.services.odoo_sync import _odoo_public_url, _portal_login, odoo_configured


def odoo_sso_configured() -> bool:
    return bool(odoo_configured() and (getattr(settings, 'ODOO_SSO_SECRET', '') or '').strip())


def _sso_secret() -> str:
    return (getattr(settings, 'ODOO_SSO_SECRET', '') or '').strip()


def _sso_ttl() -> int:
    try:
        return max(30, int(getattr(settings, 'ODOO_SSO_TTL_SECONDS', 120)))
    except (TypeError, ValueError):
        return 120


def build_odoo_sso_token(user) -> str | None:
    """Token một lần dùng (TTL ngắn) — Odoo addon portal_justplay_sso xác thực."""
    secret = _sso_secret()
    login = _portal_login(user)
    if not secret or not login:
        return None
    payload = {
        'login': login,
        'exp': int(time.time()) + _sso_ttl(),
    }
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(',', ':')).encode(),
    ).decode().rstrip('=')
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip('=')
    return f'{payload_b64}.{sig_b64}'


def odoo_sso_url(user, *, redirect_path: str = '/web') -> str | None:
    token = build_odoo_sso_token(user)
    if not token:
        return None
    base = _odoo_public_url()
    path = redirect_path if redirect_path.startswith('/') else '/web'
    return f'{base}/portal/sso?token={quote(token)}&redirect={quote(path)}'


def odoo_entry_url(user) -> str:
    """URL vào Odoo — SSO nếu cấu hình, không thì trang login (prefill username)."""
    if odoo_sso_configured():
        url = odoo_sso_url(user)
        if url:
            return url
    login = _portal_login(user)
    base = _odoo_public_url() or 'https://erp.justplay.vn'
    if login:
        return f'{base}/web/login?login={quote(login)}'
    return f'{base}/web/login'


def ensure_odoo_account_for_redirect(user) -> dict:
    """
    Đường nhanh khi bấm menu Odoo: không gọi XML-RPC nếu đã có odoo_user_id.
  Full sync chạy khi tạo user / đổi mật khẩu / lệnh sync_odoo_users.
    """
    from audit.services.odoo_sync import ensure_portal_user_in_odoo, user_has_odoo_portal_access

    if not user_has_odoo_portal_access(user):
        return {'status': 'denied'}

    profile = getattr(user, 'profile', None)
    if profile and profile.odoo_user_id:
        return {
            'status': 'ok',
            'odoo_user_id': profile.odoo_user_id,
            'login': _portal_login(user),
            'password_synced': bool(getattr(profile, 'odoo_password_synced', False)),
            'skipped_sync': True,
        }

    return ensure_portal_user_in_odoo(user)


def generate_odoo_sso_secret() -> str:
    return secrets.token_urlsafe(48)
