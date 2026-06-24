"""Đăng ký máy RustDesk từ script cài đặt — upsert RustDeskHost."""

from __future__ import annotations

import re

from django.conf import settings

RUSTDESK_ID_RE = re.compile(r'^\d{9,12}$')


def normalize_rustdesk_id(raw: str) -> str:
    digits = ''.join(c for c in (raw or '') if c.isdigit())
    if not RUSTDESK_ID_RE.match(digits):
        raise ValueError('RustDesk ID không hợp lệ')
    return digits


def enroll_secret_ok(secret: str) -> bool:
    expected = (getattr(settings, 'RUSTDESK_ENROLL_SECRET', '') or '').strip()
    if not expected:
        return False
    return secret == expected


def upsert_rustdesk_host(*, data: dict) -> tuple[object, bool]:
    from audit.models import RustDeskHost

    rustdesk_id = normalize_rustdesk_id(data.get('rustdesk_id', ''))
    password = (data.get('rustdesk_password') or '').strip()[:128]
    env_pw = (getattr(settings, 'RUSTDESK_CLIENT_PASSWORD', '') or '').strip()[:128]
    if env_pw:
        password = env_pw
    elif not password:
        password = ''
    hostname = (data.get('hostname') or '').strip()[:128]
    ip_raw = (data.get('ip_address') or data.get('ip') or '').strip()
    ip_address = ip_raw or None
    mac_raw = (data.get('mac_address') or data.get('mac') or '').strip()

    name = (data.get('name') or hostname or f'PC-{rustdesk_id[-6:]}').strip()[:200]
    department_text = (data.get('department_text') or data.get('department') or '').strip()[:200]
    assigned_user_text = (
        data.get('assigned_user_text')
        or data.get('full_name')
        or data.get('username')
        or ''
    ).strip()[:200]
    notes = (data.get('notes') or '').strip()

    defaults = {
        'name': name,
        'hostname': hostname,
        'ip_address': ip_address,
        'rustdesk_password': password,
        'notes': notes,
        'is_active': True,
    }
    if department_text:
        defaults['department_text'] = department_text
    if assigned_user_text:
        defaults['assigned_user_text'] = assigned_user_text
    if mac_raw:
        try:
            from audit.services.wake_on_lan import normalize_mac

            defaults['mac_address'] = normalize_mac(mac_raw)
        except ValueError:
            pass

    host, created = RustDeskHost.objects.update_or_create(
        rustdesk_id=rustdesk_id,
        defaults=defaults,
    )

    from audit.services.rustdesk_device_sync import sync_host_from_device

    sync_host_from_device(host, save=True)

    return host, created


def _try_link_device(host, *, hostname: str):
    from audit.services.rustdesk_device_sync import find_device_for_host

    return find_device_for_host(host)


def downloader_script_fields(user) -> dict:
    """Thông tin người tải script — nhúng vào file cài đặt."""
    if not user or not getattr(user, 'is_authenticated', False):
        return {'assigned_user_text': '', 'department_text': ''}
    profile = getattr(user, 'profile', None)
    full_name = ''
    department_text = ''
    if profile:
        full_name = (profile.full_name or '').strip()
        if profile.department_id:
            department_text = (profile.department.name or '').strip()
    if not full_name:
        full_name = (user.get_full_name() or '').strip() or (user.username or '').strip()
    return {
        'assigned_user_text': full_name[:200],
        'department_text': department_text[:200],
    }


def script_config() -> dict:
    return {
        'portal_url': getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '').rstrip('/'),
        'rustdesk_host': getattr(settings, 'RUSTDESK_PUBLIC_HOST', 'rd.justplay.vn'),
        'public_key': getattr(settings, 'RUSTDESK_PUBLIC_KEY', '').strip(),
        'client_password': getattr(settings, 'RUSTDESK_CLIENT_PASSWORD', '').strip(),
        'enroll_secret': getattr(settings, 'RUSTDESK_ENROLL_SECRET', '').strip(),
        'installer_url_win': getattr(settings, 'RUSTDESK_INSTALLER_URL_WIN', '').strip(),
        'installer_url_linux': getattr(settings, 'RUSTDESK_INSTALLER_URL_LINUX', '').strip(),
        'approve_mode': getattr(settings, 'RUSTDESK_APPROVE_MODE', 'password').strip().lower()
        or 'password',
    }
