"""Ghi lịch sử thay đổi thông tin thiết bị."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from equipment.models import Device, DeviceUpdateLog

User = get_user_model()

TRACKED_FIELDS: list[tuple[str, str]] = [
    ('device_code', 'Mã thiết bị'),
    ('name', 'Tên'),
    ('managed_department_id', 'Bộ phận quản lý'),
    ('category', 'Loại'),
    ('status', 'Trạng thái'),
    ('usage_department_id', 'Phòng ban (HT)'),
    ('usage_department_text', 'Phòng ban'),
    ('usage_room', 'Vị trí'),
    ('assigned_user_id', 'Người dùng (HT)'),
    ('assigned_user_text', 'Người dùng'),
    ('handover_date', 'Ngày bàn giao'),
    ('model_number', 'Model'),
    ('serial_number', 'Serial'),
    ('configuration', 'Cấu hình'),
    ('description', 'Mô tả'),
    ('contact_email', 'Email'),
    ('quantity', 'Số lượng'),
    ('unit_price', 'Đơn giá'),
    ('hostname', 'Hostname'),
    ('ip_address', 'IP'),
]


def _display_value(device: Device, field: str):
    if field == 'managed_department_id':
        return device.managed_department_label
    if field == 'status':
        return device.get_status_display()
    if field == 'category':
        return device.get_category_display()
    if field == 'usage_department_id':
        return device.usage_department.name if device.usage_department_id else '—'
    if field == 'assigned_user_id':
        return device.assigned_user_label
    if field == 'handover_date':
        return device.handover_date.strftime('%d/%m/%Y') if device.handover_date else '—'
    if field == 'unit_price':
        return str(int(device.unit_price or 0))
    value = getattr(device, field, None)
    if value in (None, ''):
        return '—'
    return str(value)


def _diff_devices(before: Device, after: Device) -> list[str]:
    changes: list[str] = []
    for field, label in TRACKED_FIELDS:
        old_raw = getattr(before, field, None)
        new_raw = getattr(after, field, None)
        if old_raw == new_raw:
            continue
        old_display = _display_value(before, field)
        new_display = _display_value(after, field)
        if old_display == new_display:
            continue
        changes.append(f'{label}: {old_display} → {new_display}')
    return changes


def log_device_created(device: Device, user: User | None) -> DeviceUpdateLog:
    return DeviceUpdateLog.objects.create(
        device=device,
        changed_by=user,
        action=DeviceUpdateLog.ACTION_CREATE,
        summary=f'Tạo thiết bị {device.device_code} — {device.name}',
    )


def log_device_update(before: Device, after: Device, user: User | None) -> DeviceUpdateLog | None:
    changes = _diff_devices(before, after)
    if not changes:
        return None
    return DeviceUpdateLog.objects.create(
        device=after,
        changed_by=user,
        action=DeviceUpdateLog.ACTION_UPDATE,
        summary='; '.join(changes),
    )
