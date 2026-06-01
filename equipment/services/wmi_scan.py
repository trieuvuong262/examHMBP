"""Quét WMI / dải IP — chỉ hỗ trợ Windows (dev/local)."""

from __future__ import annotations

import platform
import socket

from django.conf import settings
from django.utils import timezone

from equipment.relay.wmi_standalone import (
    build_configuration,
    get_info_via_powershell,
    is_bad_serial,
    parse_ip_range,
    port_135_open,
    probe_ip,
)

__all__ = [
    'apply_wmi_info_to_device',
    'discover_device_from_ip',
    'get_info_via_powershell',
    'is_bad_serial',
    'is_wmi_scan_supported',
    'parse_ip_range',
    'port_135_open',
    'probe_ip',
    'scan_device_wmi',
    'wmi_unavailable_message',
]


def is_wmi_scan_supported() -> bool:
    """WMI qua PowerShell — Windows và môi trường dev/local."""
    if platform.system().lower() != 'windows':
        return False
    return bool(getattr(settings, 'IS_LOCAL', False) or getattr(settings, 'DEBUG', False))


def wmi_unavailable_message() -> str:
    if platform.system().lower() != 'windows':
        return 'Quét WMI chỉ chạy trên Windows (máy dev). Production: dùng scan_relay.py trên máy IT.'
    return 'Quét WMI chỉ bật khi DEBUG hoặc DJANGO_ENV=local. Production: dùng scan_relay.py trên máy IT.'


def resolve_device_ip(device) -> tuple[str | None, bool]:
    """Trả về (ip, ip_changed)."""
    socket.setdefaulttimeout(2)
    target_ip = None
    ip_changed = False

    if device.hostname:
        try:
            resolved = socket.gethostbyname(device.hostname)
            if device.ip_address != resolved or not device.is_online:
                device.ip_address = resolved
                device.is_online = True
                ip_changed = True
            target_ip = resolved
        except OSError:
            if device.is_online:
                device.is_online = False
                device.save(update_fields=['is_online', 'updated_at'])

    if not target_ip and device.ip_address:
        target_ip = str(device.ip_address)
    return target_ip, ip_changed


def apply_wmi_info_to_device(device, info: dict) -> bool:
    """Cập nhật model/serial/config — True nếu serial/model đổi (cần vẽ lại QR)."""
    important_change = False
    if info.get('model') and device.model_number != info['model']:
        device.model_number = info['model']
        important_change = True

    new_sn = info.get('serial')
    if new_sn and not is_bad_serial(new_sn) and device.serial_number != new_sn:
        device.serial_number = new_sn
        important_change = True

    new_config = build_configuration(info)
    if device.configuration != new_config:
        device.configuration = new_config
        if not important_change:
            device.save(update_fields=['configuration', 'updated_at'])
    return important_change


def scan_device_wmi(device, *, username: str, password: str) -> tuple[bool, bool, bool]:
    """
    Quét một thiết bị.
    Returns: (ip_updated, wmi_updated, qr_redrawn)
    """
    ip_updated = False
    wmi_updated = False
    qr_redrawn = False

    target_ip, ip_changed = resolve_device_ip(device)
    if ip_changed:
        device.last_scan_date = timezone.now()
        device.save(update_fields=['ip_address', 'is_online', 'last_scan_date', 'updated_at'])
        ip_updated = True

    if target_ip and username and password and port_135_open(target_ip):
        info = get_info_via_powershell(target_ip, username, password)
        if info:
            important = apply_wmi_info_to_device(device, info)
            wmi_updated = True
            device.last_scan_date = timezone.now()
            if important:
                device.save()
                qr_redrawn = True
            else:
                device.save(update_fields=['last_scan_date', 'updated_at'])

    if not wmi_updated and not ip_updated:
        device.last_scan_date = timezone.now()
        device.save(update_fields=['last_scan_date', 'updated_at'])

    return ip_updated, wmi_updated, qr_redrawn


def discover_device_from_ip(ip_str: str, *, username: str, password: str):
    """Tìm máy trên IP — trả về (device, created) hoặc None."""
    from equipment.models import Device

    payload = probe_ip(ip_str, username=username, password=password)
    if not payload:
        return None

    device, created = Device.objects.get_or_create(
        serial_number=payload['serial'],
        defaults={
            'name': payload.get('hostname') or f"{payload.get('model', 'PC')} — {ip_str}",
            'managed_by': Device.MANAGED_IT,
            'category': 'PC',
            'status': Device.STATUS_ACTIVE,
        },
    )
    device.ip_address = ip_str
    device.hostname = payload.get('hostname') or device.hostname
    device.model_number = payload.get('model') or device.model_number
    device.configuration = build_configuration(payload)
    device.is_online = True
    device.last_scan_date = timezone.now()
    if created and device.hostname:
        device.name = device.hostname
    device.save()
    return device, created
