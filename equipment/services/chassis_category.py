"""Phân loại PC / Laptop theo WMI Win32_SystemEnclosure.ChassisTypes."""

from __future__ import annotations

# https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-systemenclosure
CHASSIS_LABELS: dict[int, str] = {
    3: 'Desktop',
    4: 'Low Profile Desktop',
    5: 'Pizza Box',
    6: 'Mini Tower',
    7: 'Tower',
    8: 'Portable',
    9: 'Laptop',
    10: 'Notebook',
    11: 'Hand Held',
    12: 'Docking Station',
    13: 'All in One',
    14: 'Sub Notebook',
    15: 'Space-Saving',
    16: 'Lunch Box',
    23: 'Rack Mount',
    24: 'Sealed-Case PC',
    30: 'Tablet',
    31: 'Convertible',
    32: 'Detachable',
    35: 'Mini PC',
    36: 'Stick PC',
}

LAPTOP_CHASSIS = frozenset({8, 9, 10, 11, 12, 14, 30, 31, 32})
DESKTOP_CHASSIS = frozenset({3, 4, 5, 6, 7, 13, 15, 16, 23, 24, 35, 36})

CATEGORY_PC = 'PC'
CATEGORY_LAPTOP = 'Laptop'


def parse_chassis_types(raw) -> list[int]:
    """Đọc chassis_types từ agent: list, chuỗi '9,10' hoặc số đơn."""
    if raw is None or raw == '':
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = str(raw).replace(';', ',').split(',')
    out: list[int] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        try:
            out.append(int(float(text)))
        except (TypeError, ValueError):
            continue
    return out


def chassis_types_display(types: list[int]) -> str:
    if not types:
        return ''
    parts = [CHASSIS_LABELS.get(code, f'Type {code}') for code in types]
    return ', '.join(parts)


def infer_it_category_from_chassis(types: list[int]) -> str | None:
    """
    Trả về mã category IT ('PC' | 'Laptop') hoặc None nếu không xác định.
    Ưu tiên Laptop khi có bất kỳ mã portable nào.
    """
    if not types:
        return None
    if any(code in LAPTOP_CHASSIS for code in types):
        return CATEGORY_LAPTOP
    if any(code in DESKTOP_CHASSIS for code in types):
        return CATEGORY_PC
    return None
