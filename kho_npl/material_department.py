"""Bộ phận phân loại NPL — cùng nguồn HR với hồ sơ sản phẩm (SX + QLCL)."""

from __future__ import annotations

# Gợi ý mặc định theo mã nhóm NPL (user kiểm tra lại sau khi gán).
CATEGORY_DEPARTMENT_DEFAULTS: dict[str, str] = {
    # Cắt / trải
    'vai': 'CẮT, TRẢI VẢI',
    'vai-phoi': 'CẮT, TRẢI VẢI',
    'giaylot': 'CẮT, TRẢI VẢI',
    'cat-print-tmp': 'CẮT, TRẢI VẢI',
    # May
    'bo-tay': 'MAY',
    'bo-co': 'MAY',
    'dayco': 'MAY',
    'dayxoquan': 'MAY',
    'thun': 'MAY',
    'day-khoa': 'MAY',
    'day-rut': 'MAY',
    'nut': 'MAY',
    'chi-may': 'MAY',
    'satin': 'MAY',
    'phulieu-may': 'MAY',
    'nhansize': 'MAY',
    'tem-nhan': 'MAY',
    'thebai': 'MAY',
    'tagdaybar': 'MAY',
    # In ép
    'decal': 'IN ÉP',
    # Gấp xếp / bao bì
    'bao-bi': 'GẤP XẾP',
    'bich': 'GẤP XẾP',
    'chongam': 'GẤP XẾP',
    'phulieu-xep': 'GẤP XẾP',
    # Cơ điện / vật tư
    'vattu': 'CƠ ĐIỆN',
    # Khác
    'khac': 'MAY',
}

DEFAULT_FALLBACK_DEPARTMENT = 'MAY'


def material_department_options() -> list[dict]:
    """Dropdown bộ phận — cùng chuẩn hồ sơ sản phẩm / nhóm công đoạn IE."""
    from san_xuat.services.capacity_from_hrm import ie_group_department_options

    return ie_group_department_options()


def material_department_choices(*, include_blank: bool = True, current: str = '') -> list[tuple[str, str]]:
    from san_xuat.services.capacity_from_hrm import (
        ie_group_department_label_choices,
        normalize_ie_group_department_label,
    )

    labels = ie_group_department_label_choices(
        include_labels=[current] if current else None,
    )
    choices: list[tuple[str, str]] = []
    if include_blank:
        choices.append(('', '— Chọn bộ phận —'))
    option_map = {opt['name']: opt for opt in material_department_options()}
    for name in labels:
        opt = option_map.get(name) or {}
        dept = (opt.get('department_name') or '').strip()
        label = f'{name} ({dept})' if dept else name
        choices.append((name, label))
    current_norm = normalize_ie_group_department_label(current) or (current or '').strip()
    if current_norm and current_norm not in {c[0] for c in choices}:
        choices.append((current_norm, f'{current_norm} (cũ)'))
    return choices


def normalize_material_department(value: str) -> str:
    from san_xuat.services.capacity_from_hrm import normalize_ie_group_department_label

    return normalize_ie_group_department_label(value or '') or (value or '').strip()


def default_department_for_category_code(category_code: str) -> str:
    code = (category_code or '').strip().lower()
    return CATEGORY_DEPARTMENT_DEFAULTS.get(code, DEFAULT_FALLBACK_DEPARTMENT)


def assign_default_departments(*, only_blank: bool = True, dry_run: bool = False) -> dict:
    """Gán bộ phận mặc định theo nhóm NPL. Trả về thống kê."""
    from collections import Counter

    from kho_npl.models import Material

    qs = Material.objects.select_related('category').order_by('pk')
    if only_blank:
        qs = qs.filter(department='')

    counts: Counter[str] = Counter()
    updated = 0
    for material in qs.iterator(chunk_size=500):
        label = default_department_for_category_code(
            material.category.code if material.category_id else '',
        )
        label = normalize_material_department(label) or label
        counts[label] += 1
        if dry_run:
            continue
        if material.department != label:
            material.department = label
            material.save(update_fields=['department', 'updated_at'])
            updated += 1

    return {
        'matched': sum(counts.values()),
        'updated': updated,
        'by_department': dict(counts.most_common()),
        'dry_run': dry_run,
    }
