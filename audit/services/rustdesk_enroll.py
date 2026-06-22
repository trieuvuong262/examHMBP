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
    if not password:
        password = (getattr(settings, 'RUSTDESK_CLIENT_PASSWORD', '') or '').strip()[:128]
    hostname = (data.get('hostname') or '').strip()[:128]
    ip_raw = (data.get('ip_address') or data.get('ip') or '').strip()
    ip_address = ip_raw or None

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
        'department_text': department_text,
        'assigned_user_text': assigned_user_text,
        'notes': notes,
        'is_active': True,
    }

    host, created = RustDeskHost.objects.update_or_create(
        rustdesk_id=rustdesk_id,
        defaults=defaults,
    )

    device = _try_link_device(host, hostname=hostname)
    if device and host.device_id != device.pk:
        host.device = device
        host.save(update_fields=['device', 'updated_at'])

    return host, created


def _try_link_device(host, *, hostname: str):
    if host.device_id or not hostname:
        return None
    from equipment.models import Device

    return Device.objects.filter(hostname__iexact=hostname).order_by('-updated_at').first()


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
