"""Gán dữ liệu agent + hồ sơ user lên thiết bị."""

from __future__ import annotations

import re


def agent_device_display_name(data: dict, serial: str) -> str:
    """Mã/tên thiết bị agent — luôn bắt đầu bằng PC-."""
    host = (data.get('hostname') or '').strip()
    digits = re.sub(r'\D', '', serial or '')
    tail = digits[-6:] if len(digits) >= 6 else (digits or '000000')
    if host:
        slug = re.sub(r'[^A-Za-z0-9\-]+', '-', host).strip('-')[:28]
        if not slug:
            return f'PC-{tail}'
        upper = slug.upper()
        if upper.startswith('PC-'):
            return slug
        if upper.startswith('PC'):
            return f'PC-{slug[2:].lstrip("-")}' if len(slug) > 2 else f'PC-{tail}'
        return f'PC-{slug}'
    return f'PC-{tail}'


def build_configuration_text(data: dict) -> str:
    from equipment.services.chassis_category import (
        chassis_types_display,
        parse_chassis_types,
    )

    lines = []
    chassis_types = parse_chassis_types(data.get('chassis_types'))
    chassis_label = chassis_types_display(chassis_types)
    if chassis_label:
        lines.append(f'Loại vỏ (chassis): {chassis_label}')

    mapping = (
        ('cpu', 'CPU'),
        ('ram', 'RAM (GB)'),
        ('disk', 'Ổ cứng (GB)'),
        ('os', 'Hệ điều hành'),
        ('os_build', 'Build OS'),
        ('manufacturer', 'Hãng'),
    )
    for key, label in mapping:
        val = (data.get(key) or '').strip()
        if val:
            lines.append(f'{label}: {val}')
    return '\n'.join(lines) if lines else (data.get('configuration') or '')


def apply_user_profile_to_device(device, user) -> list[str]:
    """Đồng bộ phòng ban, vị trí, email từ hồ sơ HRM."""
    from hrm.choices import DEFAULT_POSITION

    updated: list[str] = []
    profile = getattr(user, 'profile', None)

    device.assigned_user = user
    if profile and profile.full_name:
        device.assigned_user_text = profile.full_name
    elif not device.assigned_user_text:
        device.assigned_user_text = user.get_full_name() or user.username
    updated.extend(['assigned_user', 'assigned_user_text'])

    if profile:
        if profile.department_id:
            device.usage_department_id = profile.department_id
            device.usage_department_text = profile.department.name if profile.department_id else ''
            updated.extend(['usage_department', 'usage_department_text'])

        position = (profile.job_position or '').strip()
        title = (profile.job_title or '').strip()
        if title:
            device.usage_room = title
        elif position and position != DEFAULT_POSITION:
            device.usage_room = position
        if device.usage_room:
            updated.append('usage_room')

    if user.email:
        device.contact_email = user.email
        updated.append('contact_email')

    return updated


def apply_agent_company_defaults(device, data: dict, *, created: bool = False) -> list[str]:
    """Máy công ty từ agent: tên PC-*, bộ phận quản lý IT."""
    from equipment.scope import SCOPE_IT
    from equipment.services.managed_department import default_managed_department_for_scope

    updated: list[str] = []
    dept = default_managed_department_for_scope(SCOPE_IT)
    if dept and (created or not device.managed_department_id):
        device.managed_department = dept
        updated.append('managed_department')

    display_name = agent_device_display_name(data, device.serial_number)
    if display_name and (
        created
        or not device.name
        or not str(device.name).upper().startswith('PC')
    ):
        device.name = display_name
        updated.append('name')

    if created and not (device.category or '').strip():
        device.category = 'PC'
        updated.append('category')

    return updated


def apply_agent_hardware_to_device(device, data: dict, *, created: bool = False) -> list[str]:
    from equipment.models import Device

    updated: list[str] = []
    hostname = (data.get('hostname') or '').strip()
    if hostname:
        device.hostname = hostname
        updated.append('hostname')
    ip = (data.get('ip') or '').strip()
    if ip:
        device.ip_address = ip
        updated.append('ip_address')
    model = (data.get('model') or '').strip()
    if model:
        device.model_number = model
        updated.append('model_number')

    config = build_configuration_text(data)
    if config:
        device.configuration = config
        updated.append('configuration')

    from equipment.services.chassis_category import infer_it_category_from_agent_data

    updated.extend(apply_agent_company_defaults(device, data, created=created))

    inferred = infer_it_category_from_agent_data(data)
    if inferred and created and device.category == 'PC':
        device.category = inferred
        updated.append('category')
    if device.status in ('', Device.STATUS_NEW):
        device.status = Device.STATUS_ACTIVE
        updated.append('status')

    uv_id = (data.get('ultraviewer_id') or '').strip()
    if uv_id:
        device.ultraviewer_id = uv_id[:32]
        updated.append('ultraviewer_id')
    uv_pass = (data.get('ultraviewer_password') or '').strip()
    if uv_pass:
        device.ultraviewer_password = uv_pass[:128]
        updated.append('ultraviewer_password')

    return updated


def apply_agent_payload_from_data(device, data: dict) -> list[str]:
    """Bổ sung từ payload agent (ini) khi chưa có trên DB."""
    updated: list[str] = []

    dept_name = (data.get('department') or '').strip()
    dept_id = data.get('department_id')
    if dept_id and str(dept_id).isdigit() and not device.usage_department_id:
        device.usage_department_id = int(dept_id)
        updated.append('usage_department')
    if dept_name and not device.usage_department_text:
        device.usage_department_text = dept_name
        updated.append('usage_department_text')
        if not device.usage_department_id:
            from hrm.models import Department

            dept = Department.objects.filter(name__iexact=dept_name).first()
            if dept:
                device.usage_department_id = dept.pk
                updated.append('usage_department')

    for key in ('job_position', 'position', 'job_title'):
        val = (data.get(key) or '').strip()
        if val and not device.usage_room:
            device.usage_room = val
            updated.append('usage_room')
            break

    email = (data.get('email') or '').strip()
    if email and not device.contact_email:
        device.contact_email = email
        updated.append('contact_email')

    full_name = (data.get('full_name') or '').strip()
    if full_name and not device.assigned_user_text:
        device.assigned_user_text = full_name
        updated.append('assigned_user_text')

    return updated
