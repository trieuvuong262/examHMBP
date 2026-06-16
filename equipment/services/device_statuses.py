"""Trạng thái hoạt động thiết bị — đọc từ DB (CRUD), fallback STATUS_CHOICES."""

from __future__ import annotations

from django.db.utils import DatabaseError, OperationalError, ProgrammingError

from equipment.models import Device

_DB_ERRORS = (ProgrammingError, OperationalError, DatabaseError)


def _db_statuses_ready() -> bool:
    try:
        from equipment.models import DeviceStatus

        DeviceStatus.objects.exists()
        return True
    except _DB_ERRORS:
        return False


def get_active_statuses():
    if not _db_statuses_ready():
        return None
    from equipment.models import DeviceStatus

    qs = DeviceStatus.objects.filter(is_active=True).order_by('sort_order', 'name')
    if qs.exists():
        return list(qs)
    return None


def status_label(code: str) -> str:
    if not code:
        return '—'
    if _db_statuses_ready():
        from equipment.models import DeviceStatus

        row = DeviceStatus.objects.filter(code=code, is_active=True).first()
        if row:
            return row.name
        row = DeviceStatus.objects.filter(code=code).first()
        if row:
            return row.name
    for value, label in Device.STATUS_CHOICES:
        if value == code:
            return label
    return code


def status_map() -> dict[str, str]:
    if _db_statuses_ready():
        from equipment.models import DeviceStatus

        rows = DeviceStatus.objects.filter(is_active=True).order_by('sort_order', 'name')
        if rows.exists():
            return {r.code: r.name for r in rows}
    return dict(Device.STATUS_CHOICES)


def status_choices() -> list[tuple[str, str]]:
    return list(status_map().items())


def valid_status_codes() -> set[str]:
    return set(status_map().keys())


def normalize_status_value(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    codes = valid_status_codes()
    if text in codes:
        return text
    lower = text.lower()
    for code, label in status_map().items():
        if lower == label.lower() or lower == code.lower():
            return code
    aliases = {
        'hoat dong': 'active',
        'dang hoat dong': 'active',
        'hong': 'broken',
        'dang hong': 'broken',
        'bao tri': 'maintenance',
        'dang bao tri': 'maintenance',
        'thanh ly': 'scrapped',
        'huy': 'scrapped',
        'moi': 'new',
        'moi lap': 'new',
    }
    return aliases.get(lower)
