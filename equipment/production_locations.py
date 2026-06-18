"""Vị trí lắp máy chuẩn — thiết bị sản xuất (2 xưởng)."""

from __future__ import annotations

import re
import unicodedata

LOCATION_CHIEN_LUOC = '19 Chiến Lược'
LOCATION_6A = '152A đường 6A'

PRODUCTION_USAGE_ROOM_VALUES = (
    LOCATION_CHIEN_LUOC,
    LOCATION_6A,
)


def _fold(text: str) -> str:
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace('đ', 'd').replace('Đ', 'D')
    return re.sub(r'\s+', ' ', text).strip().lower()


def production_usage_room_choices() -> list[tuple[str, str]]:
    return [('', '— Chọn vị trí —'), *[(v, v) for v in PRODUCTION_USAGE_ROOM_VALUES]]


def production_usage_room_filter_choices() -> list[str]:
    return list(PRODUCTION_USAGE_ROOM_VALUES)


def normalize_usage_room(value: str | None) -> str:
    """Chuẩn hóa free text → một trong hai vị trí; không khớp thì trả về ''."""
    raw = (value or '').strip()
    if not raw:
        return ''

    folded = _fold(raw)
    for canonical in PRODUCTION_USAGE_ROOM_VALUES:
        if folded == _fold(canonical):
            return canonical

    alias_map = {
        '19 chien luoc': LOCATION_CHIEN_LUOC,
        'so 19 chien luoc': LOCATION_CHIEN_LUOC,
        '19 chienluoc': LOCATION_CHIEN_LUOC,
        'chien luoc': LOCATION_CHIEN_LUOC,
        'chiến lược': LOCATION_CHIEN_LUOC,
        '19cl': LOCATION_CHIEN_LUOC,
        '152a': LOCATION_6A,
        '152 a': LOCATION_6A,
        '152a duong 6a': LOCATION_6A,
        '152a đường 6a': LOCATION_6A,
        'duong 6a': LOCATION_6A,
        'đường 6a': LOCATION_6A,
        'khu 152a': LOCATION_6A,
        'khu 152 a': LOCATION_6A,
    }
    for alias, canonical in alias_map.items():
        if folded == _fold(alias):
            return canonical

    if re.search(r'\b19\b', folded) and ('chien' in folded or 'luoc' in folded or 'cl' in folded):
        return LOCATION_CHIEN_LUOC
    if 'chien luoc' in folded or 'chienluoc' in folded:
        return LOCATION_CHIEN_LUOC

    if '152' in folded or re.search(r'\b6a\b', folded) or 'duong 6' in folded:
        return LOCATION_6A

    return ''
