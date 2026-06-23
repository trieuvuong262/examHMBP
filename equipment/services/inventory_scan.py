"""Quét cấu hình máy từ script — kiểm tra MAC và tạo thiết bị IT mới."""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.utils import timezone

from equipment.scope import SCOPE_IT

MAC_RE = re.compile(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$')

_JUNK_TEXT_VALUES = frozenset({
    '',
    'default string',
    'to be filled by o.e.m.',
    'system serial number',
    'none',
    'n/a',
    'not specified',
    'unknown',
})


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


def _clean_text(value: str | None, *, max_len: int = 200) -> str:
    text = (value or '').strip()
    if text.lower() in _JUNK_TEXT_VALUES:
        return ''
    return text[:max_len]


def _build_name(*, hostname: str, mac: str) -> str:
    host = _clean_text(hostname, max_len=200)
    if host:
        return host
    return f'PC-{mac.replace(":", "")[-8:]}'


def _format_network_summary(data: dict) -> str:
    raw = (data.get('network_adapters') or '').strip()
    if raw and not raw.startswith('['):
        return raw[:500]
    return ''


def _format_scan_description(data: dict, *, mac: str, scanned_at) -> str:
    downloader = _clean_text(data.get('assigned_user_text'), max_len=100)
    usage_dept = _clean_text(data.get('department_text'), max_len=100)
    logged_in = _clean_text(data.get('logged_in_user'), max_len=120)
    if '\\' in logged_in:
        logged_in = logged_in.rsplit('\\', 1)[-1]
    rustdesk_id = _clean_text(data.get('rustdesk_id'), max_len=32)

    lines = [
        'Đăng ký tự động từ script quét cấu hình JustPlay.',
        f'Thời gian quét: {timezone.localtime(scanned_at):%d/%m/%Y %H:%M}',
        f'MAC chính: {mac}',
    ]
    if downloader:
        lines.append(f'Người tải script: {downloader}')
    if usage_dept:
        lines.append(f'Phòng ban sử dụng (theo Portal): {usage_dept}')
    if logged_in:
        lines.append(f'User đang đăng nhập trên máy: {logged_in}')
    if rustdesk_id:
        lines.append(f'RustDesk ID: {rustdesk_id}')

    network = _format_network_summary(data)
    if network:
        lines.append(f'Card mạng: {network}')

    manufacturer = _clean_text(data.get('manufacturer'), max_len=80)
    model = _clean_text(data.get('model') or data.get('model_number'), max_len=80)
    if manufacturer or model:
        lines.append(f'Máy: {" ".join(x for x in (manufacturer, model) if x)}')

    return '\n'.join(lines)[:4000]


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
    net_summary = _format_network_summary(data)
    if net_summary:
        lines.append(f'Mạng: {net_summary}')
    motherboard = _clean_text(data.get('motherboard'), max_len=80)
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
    from equipment.services.device_code import allocate_pc_device_code
    from equipment.services.managed_department import default_managed_department_for_scope

    mac = normalize_mac(data.get('mac_address') or data.get('mac') or '')
    if device_exists_for_mac(mac):
        existing = Device.objects.filter(mac_address=mac).first()
        return existing, False

    hostname = _clean_text(data.get('hostname') or data.get('computer_name'), max_len=100)
    ip_address = _coerce_ip(data.get('ip_address') or data.get('ip'))
    serial = _clean_text(data.get('serial_number') or data.get('bios_serial'), max_len=100)
    model_number = _clean_text(data.get('model') or data.get('model_number'), max_len=100)
    assigned_user_text = _clean_text(
        data.get('assigned_user_text') or data.get('full_name'),
        max_len=100,
    )
    if not assigned_user_text:
        logged = _clean_text(data.get('logged_in_user'), max_len=100)
        if '\\' in logged:
            logged = logged.rsplit('\\', 1)[-1]
        assigned_user_text = logged
    department_text = _clean_text(data.get('department_text') or data.get('department'), max_len=100)
    windows_version = _clean_text(data.get('os_name') or data.get('windows_version'), max_len=200)
    if data.get('os_version'):
        build = _clean_text(data.get('os_build'), max_len=40)
        extra = f" {data['os_version']}"
        if build:
            extra += f' (build {build})'
        if windows_version:
            windows_version = f'{windows_version}{extra}'[:200]
        else:
            windows_version = extra.strip()[:200]
    windows_license = _clean_text(data.get('windows_license') or data.get('os_license'), max_len=128)

    scanned_at = timezone.now()
    managed_department = default_managed_department_for_scope(SCOPE_IT)

    device = Device(
        device_code=allocate_pc_device_code(),
        name=_build_name(hostname=hostname, mac=mac),
        category=_pick_category(data),
        managed_department=managed_department,
        mac_address=mac,
        hostname=hostname,
        ip_address=ip_address,
        serial_number=serial,
        model_number=model_number,
        configuration=_format_configuration(data),
        description=_format_scan_description(data, mac=mac, scanned_at=scanned_at),
        assigned_user_text=assigned_user_text,
        usage_department_text=department_text,
        windows_version=windows_version,
        windows_license=windows_license,
        status=Device.STATUS_NEW,
        last_scan_date=scanned_at,
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
