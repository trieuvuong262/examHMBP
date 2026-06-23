"""Quét cấu hình máy từ script — kiểm tra MAC và tạo thiết bị IT mới."""

from __future__ import annotations

import json
import re
from typing import Any

from django.conf import settings
from django.utils import timezone

MAC_RE = re.compile(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$')


def normalize_mac(raw: str) -> str:
    cleaned = re.sub(r'[^0-9A-Fa-f]', '', raw or '')
    if len(cleaned) != 12:
        raise ValueError('Địa chỉ MAC không hợp lệ')
    mac = ':'.join(cleaned[i:i + 2] for i in range(0, 12, 2)).upper()
    if not MAC_RE.match(mac):
        raise ValueError('Địa chỉ MAC không hợp lệ')
    return mac


def scan_secret_ok(secret: str) -> bool:
    expected = (getattr(settings, 'EQUIPMENT_SCAN_SECRET', '') or '').strip()
    if not expected:
        expected = (getattr(settings, 'RUSTDESK_ENROLL_SECRET', '') or '').strip()
    if not expected:
        return False
    return secret == expected


def device_exists_for_mac(mac: str) -> bool:
    from equipment.models import Device

    return Device.objects.filter(mac_address=mac).exists()


def _pick_category(data: dict) -> str:
    chassis = ' '.join(
        str(data.get(key) or '')
        for key in ('chassis_type', 'machine_type', 'form_factor', 'product_type')
    ).lower()
    if any(word in chassis for word in ('laptop', 'notebook', 'portable')):
        return 'Laptop'
    return 'PC'


def _build_name(data: dict, *, mac: str, hostname: str) -> str:
    if hostname:
        return hostname[:200]
    manufacturer = (data.get('manufacturer') or data.get('vendor') or '').strip()
    model = (data.get('model') or data.get('model_number') or '').strip()
    label = f'{manufacturer} {model}'.strip()
    if label:
        return label[:200]
    return f'PC-{mac.replace(":", "")[-8:]}'


def _format_configuration(data: dict) -> str:
    lines: list[str] = []
    mapping = [
        ('os_name', 'Hệ điều hành'),
        ('os_version', 'Phiên bản OS'),
        ('os_build', 'Build'),
        ('os_arch', 'Kiến trúc'),
        ('cpu', 'CPU'),
        ('cpu_cores', 'Nhân CPU'),
        ('ram_gb', 'RAM (GB)'),
        ('gpu', 'GPU'),
        ('storage', 'Ổ cứng'),
        ('domain', 'Domain'),
        ('logged_in_user', 'User đăng nhập'),
        ('rustdesk_id', 'RustDesk ID'),
    ]
    for key, label in mapping:
        value = data.get(key)
        if value not in (None, ''):
            lines.append(f'{label}: {value}')
    network = data.get('network_adapters') or data.get('mac_addresses')
    if network:
        lines.append(f'Mạng: {network}')
    motherboard = data.get('motherboard')
    if motherboard:
        lines.append(f'Bo mạch: {motherboard}')
    bios = data.get('bios_version')
    if bios:
        lines.append(f'BIOS: {bios}')
    return '\n'.join(lines)[:4000]


def _coerce_ip(value: str | None) -> str | None:
    raw = (value or '').strip()
    if not raw:
        return None
    if '/' in raw:
        raw = raw.split('/', 1)[0].strip()
    return raw or None


def create_device_from_scan(*, data: dict) -> tuple[Any, bool]:
    """Tạo Device IT nếu MAC chưa có. Trả về (device, created)."""
    from equipment.models import Device

    mac = normalize_mac(data.get('mac_address') or data.get('mac') or '')
    if device_exists_for_mac(mac):
        existing = Device.objects.filter(mac_address=mac).first()
        return existing, False

    hostname = (data.get('hostname') or data.get('computer_name') or '').strip()[:100]
    ip_address = _coerce_ip(data.get('ip_address') or data.get('ip'))
    serial = (data.get('serial_number') or data.get('bios_serial') or '').strip()[:100]
    model_number = (data.get('model') or data.get('model_number') or '').strip()[:100]
    assigned_user_text = (
        data.get('assigned_user_text')
        or data.get('full_name')
        or data.get('logged_in_user')
        or ''
    ).strip()[:100]
    department_text = (data.get('department_text') or data.get('department') or '').strip()[:100]
    windows_version = (data.get('os_name') or data.get('windows_version') or '').strip()[:200]
    if data.get('os_version'):
        build = (data.get('os_build') or '').strip()
        extra = f" {data['os_version']}"
        if build:
            extra += f" (build {build})"
        if windows_version:
            windows_version = f'{windows_version}{extra}'[:200]
        else:
            windows_version = extra.strip()[:200]
    windows_license = (data.get('windows_license') or data.get('os_license') or '').strip()[:128]

    scan_payload = dict(data)
    scan_payload['mac_address'] = mac
    scan_payload['scanned_at'] = timezone.now().isoformat()

    device = Device(
        name=_build_name(data, mac=mac, hostname=hostname),
        category=_pick_category(data),
        mac_address=mac,
        hostname=hostname,
        ip_address=ip_address,
        serial_number=serial,
        model_number=model_number,
        configuration=_format_configuration(data),
        description=json.dumps(scan_payload, ensure_ascii=False, indent=2)[:8000],
        assigned_user_text=assigned_user_text,
        usage_department_text=department_text,
        windows_version=windows_version,
        windows_license=windows_license,
        status=Device.STATUS_NEW,
        last_scan_date=timezone.now(),
    )
    device.save()
    return device, True


def downloader_script_fields(user) -> dict:
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
    secret = (getattr(settings, 'EQUIPMENT_SCAN_SECRET', '') or '').strip()
    if not secret:
        secret = (getattr(settings, 'RUSTDESK_ENROLL_SECRET', '') or '').strip()
    return {
        'portal_url': getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '').rstrip('/'),
        'scan_secret': secret,
    }
