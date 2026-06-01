"""Trạng thái quét WMI — local Windows hoặc relay HTTP (máy IT)."""

from __future__ import annotations

import platform

from django.conf import settings


def is_local_wmi_available() -> bool:
    if platform.system().lower() != 'windows':
        return False
    if getattr(settings, 'EQUIPMENT_ENABLE_LOCAL_WMI', False):
        return True
    return bool(getattr(settings, 'IS_LOCAL', False) or getattr(settings, 'DEBUG', False))


def is_relay_scan_available() -> bool:
    url = getattr(settings, 'EQUIPMENT_RELAY_HTTP_URL', '') or ''
    secret = getattr(settings, 'EQUIPMENT_RELAY_SECRET', '') or ''
    return bool(url.strip() and secret.strip())


def is_agent_scan_available() -> bool:
    return bool(getattr(settings, 'EQUIPMENT_AGENT_SECRET', '') or '')


def is_scan_available() -> bool:
    return is_local_wmi_available() or is_relay_scan_available() or is_agent_scan_available()


def scan_unavailable_message() -> str:
    if is_scan_available():
        return ''
    return (
        'Chưa bật quét. Trên VPS đặt EQUIPMENT_AGENT_SECRET trong .env, '
        'cài JustPlayAgent.exe trên PC. Xem /thiet-bi/agent/'
    )


def relay_http_url() -> str:
    return (getattr(settings, 'EQUIPMENT_RELAY_HTTP_URL', '') or '').rstrip('/')


def relay_secret() -> str:
    return getattr(settings, 'EQUIPMENT_RELAY_SECRET', '') or ''


def relay_timeout() -> int:
    return int(getattr(settings, 'EQUIPMENT_RELAY_TIMEOUT', 300))
