"""Quét WMI / dải IP — local Windows hoặc relay HTTP (máy IT)."""

from __future__ import annotations

import socket

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
    'apply_probe_payload_to_device',
    'apply_wmi_info_to_device',
    'discover_device_from_ip',
    'get_info_via_powershell',
    'is_bad_serial',
    'is_local_wmi_available',
    'is_relay_scan_available',
    'is_scan_available',
    'is_wmi_scan_supported',
    'parse_ip_range',
    'port_135_open',
    'probe_ip',
    'scan_device_wmi',
    'scan_unavailable_message',
    'wmi_unavailable_message',
]


def is_local_wmi_available() -> bool:
    from equipment.services.scan_backend import is_local_wmi_available as _local

    return _local()


def is_relay_scan_available() -> bool:
    from equipment.services.scan_backend import is_relay_scan_available as _relay

    return _relay()


def is_scan_available() -> bool:
    from equipment.services.scan_backend import is_scan_available as _available

    return _available()


def is_wmi_scan_supported() -> bool:
    return is_scan_available()


def scan_unavailable_message() -> str:
    from equipment.services.scan_backend import scan_unavailable_message as _msg

    return _msg()


def wmi_unavailable_message() -> str:
    return scan_unavailable_message()


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


def apply_probe_payload_to_device(device, payload: dict) -> tuple[bool, bool, bool]:
    """
    Áp kết quả quét (local hoặc relay) lên Device.
    Returns: (ip_updated, wmi_updated, qr_redrawn)
    """
    ip_updated = bool(payload.get('ip_updated'))
    wmi_updated = bool(payload.get('wmi_updated'))
    qr_redrawn = bool(payload.get('qr_redrawn'))

    if payload.get('ip_address'):
        device.ip_address = payload['ip_address']
    if 'is_online' in payload:
        device.is_online = bool(payload['is_online'])
    if payload.get('hostname'):
        device.hostname = payload['hostname']

    probe = payload.get('probe')
    if probe:
        important = apply_wmi_info_to_device(device, probe)
        if important:
            qr_redrawn = True
        wmi_updated = True

    device.last_scan_date = timezone.now()
    if qr_redrawn or ip_updated:
        device.save()
    elif wmi_updated:
        device.save(update_fields=['last_scan_date', 'updated_at', 'configuration'])
    else:
        device.save(update_fields=['last_scan_date', 'updated_at'])

    return ip_updated, wmi_updated, qr_redrawn


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


def upsert_device_from_probe(probe: dict):
    """Tạo hoặc cập nhật thiết bị từ kết quả quét (relay / local)."""
    from equipment.models import Device

    ip_str = probe.get('ip') or probe.get('ip_address')
    serial = probe.get('serial')
    if not serial or is_bad_serial(serial):
        return None, False

    hostname = probe.get('hostname') or ''
    device, created = Device.objects.get_or_create(
        serial_number=serial,
        defaults={
            'name': hostname or f"{probe.get('model', 'PC')} — {ip_str}",
            'managed_by': Device.MANAGED_IT,
            'category': 'PC',
            'status': Device.STATUS_ACTIVE,
        },
    )
    if ip_str:
        device.ip_address = ip_str
    if hostname:
        device.hostname = hostname
    device.model_number = probe.get('model') or device.model_number
    device.configuration = build_configuration(probe)
    device.is_online = True
    device.last_scan_date = timezone.now()
    if created and hostname:
        device.name = hostname
    device.save()
    return device, created
