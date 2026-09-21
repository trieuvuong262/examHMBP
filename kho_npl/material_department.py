"""Bộ phận phân loại NPL / vật tư — nguồn HR (Division)."""

from __future__ import annotations

from django.db.models import Q

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
    'vat-tu': 'CƠ ĐIỆN',
    # Khác
    'khac': 'MAY',
}

DEFAULT_FALLBACK_DEPARTMENT = 'MAY'
DEFAULT_VAT_TU_DEPARTMENT = 'CƠ ĐIỆN'


def hr_division_department_options() -> list[dict]:
    """Toàn bộ bộ phận HR đang dùng — kho vật tư (Cơ điện, IT, …)."""
    from hrm.models import Division

    options: list[dict] = []
    seen: set[str] = set()
    qs = (
        Division.objects.filter(is_active=True)
        .filter(Q(department__isnull=True) | Q(department__is_active=True))
        .select_related('department')
        .order_by('department__sort_order', 'department__name', 'sort_order', 'name')
    )
    for div in qs:
        name = (div.name or '').strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        dept_name = div.department.name if div.department_id else ''
        options.append({
            'name': name,
            'department_name': (dept_name or '').strip(),
        })
    return options


def material_department_options() -> list[dict]:
    """Dropdown bộ phận: NPL = SX+QLCL; kho vật tư = mọi bộ phận Nhân sự."""
    from kho_npl.stock_domain import STOCK_DOMAIN_VAT_TU, domain_from_current_request

    if domain_from_current_request() == STOCK_DOMAIN_VAT_TU:
        return hr_division_department_options()
    from san_xuat.services.capacity_from_hrm import ie_group_department_options

    return ie_group_department_options()


def material_department_choices(*, include_blank: bool = True, current: str = '') -> list[tuple[str, str]]:
    from san_xuat.services.capacity_from_hrm import normalize_ie_group_department_label

    choices: list[tuple[str, str]] = []
    if include_blank:
        choices.append(('', '— Chọn bộ phận —'))
    seen: set[str] = set()
    for opt in material_department_options():
        name = (opt.get('name') or '').strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        dept = (opt.get('department_name') or '').strip()
        label = f'{name} ({dept})' if dept else name
        choices.append((name, label))
    current_norm = normalize_ie_group_department_label(current) or (current or '').strip()
    if current_norm and current_norm.casefold() not in seen:
        choices.append((current_norm, f'{current_norm} (cũ)'))
    return choices


def normalize_material_department(value: str) -> str:
    from san_xuat.services.capacity_from_hrm import normalize_ie_group_department_label

    return normalize_ie_group_department_label(value or '') or (value or '').strip()


def default_department_for_category_code(category_code: str) -> str:
    code = (category_code or '').strip().lower()
    if code in CATEGORY_DEPARTMENT_DEFAULTS:
        return CATEGORY_DEPARTMENT_DEFAULTS[code]
    from kho_npl.stock_domain import STOCK_DOMAIN_VAT_TU, domain_from_current_request

    if domain_from_current_request() == STOCK_DOMAIN_VAT_TU:
        return DEFAULT_VAT_TU_DEPARTMENT
    return DEFAULT_FALLBACK_DEPARTMENT


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
