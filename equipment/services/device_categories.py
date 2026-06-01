"""Loại thiết bị — đọc từ DB (CRUD), fallback seed từ categories.py."""

from __future__ import annotations

from django.db.utils import DatabaseError, OperationalError, ProgrammingError

from equipment.categories import (
    CATEGORY_CHOICES_BY_GROUP,
    CATEGORY_GROUP_LABELS,
    CATEGORY_MAP,
    category_group_for_code as static_group_for_code,
    import_profile_for_category as static_import_profile,
)

_DB_ERRORS = (ProgrammingError, OperationalError, DatabaseError)


def _group_label(group_code: str) -> str:
    return CATEGORY_GROUP_LABELS.get(group_code, group_code)


def _db_categories_ready() -> bool:
    try:
        from equipment.models import DeviceCategory

        DeviceCategory.objects.exists()
        return True
    except _DB_ERRORS:
        return False


def get_active_categories():
    if not _db_categories_ready():
        return None
    from equipment.models import DeviceCategory

    qs = DeviceCategory.objects.filter(is_active=True).order_by('group', 'sort_order', 'name')
    if qs.exists():
        return list(qs)
    return None


def category_label(code: str) -> str:
    if not code:
        return '—'
    if _db_categories_ready():
        from equipment.models import DeviceCategory

        cat = DeviceCategory.objects.filter(code=code, is_active=True).first()
        if cat:
            return cat.name
        cat = DeviceCategory.objects.filter(code=code).first()
        if cat:
            return cat.name
    return CATEGORY_MAP.get(code, code)


def category_map() -> dict[str, str]:
    if _db_categories_ready():
        from equipment.models import DeviceCategory

        rows = DeviceCategory.objects.filter(is_active=True).order_by('group', 'sort_order', 'name')
        if rows.exists():
            return {r.code: r.name for r in rows}
    return dict(CATEGORY_MAP)


def category_choices() -> list[tuple[str, str]]:
    return list(category_map().items())


def categories_by_group() -> list[tuple[str, str, list[tuple[str, str]]]]:
    if _db_categories_ready():
        from equipment.models import DeviceCategory

        rows = list(
            DeviceCategory.objects.filter(is_active=True).order_by('group', 'sort_order', 'name')
        )
        if rows:
            grouped: dict[str, list[tuple[str, str]]] = {}
            order: list[str] = []
            for row in rows:
                if row.group not in grouped:
                    grouped[row.group] = []
                    order.append(row.group)
                grouped[row.group].append((row.code, row.name))
            return [(g, _group_label(g), grouped[g]) for g in order]
    return list(CATEGORY_CHOICES_BY_GROUP)


def import_profile_for_code(code: str) -> str:
    if _db_categories_ready():
        from equipment.models import DeviceCategory

        cat = DeviceCategory.objects.filter(code=code).first()
        if cat:
            return cat.import_profile
    return static_import_profile(code)


def group_for_code(code: str) -> str:
    if _db_categories_ready():
        from equipment.models import DeviceCategory

        cat = DeviceCategory.objects.filter(code=code).first()
        if cat:
            return cat.group
    return static_group_for_code(code)


def valid_codes() -> set[str]:
    return set(category_map().keys())


def normalize_category_value(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    codes = valid_codes()
    if text in codes:
        return text
    lower = text.lower()
    for code, label in category_map().items():
        if lower == label.lower() or lower == code.lower():
            return code
    from equipment.categories import normalize_category

    return normalize_category(value)
