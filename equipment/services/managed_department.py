"""Bộ phận quản lý thiết bị — lấy từ cơ cấu tổ chức (hrm.Department)."""

from __future__ import annotations

from equipment.scope import SCOPE_IT, SCOPE_PRODUCTION

_IT_NAME_CANDIDATES = ('IT / CNTT', 'CNTT', 'IT')
_PRODUCTION_NAME_CANDIDATES = ('Bảo trì xưởng', 'Bảo trì', 'Sản xuất')


def _find_department_by_names(names: tuple[str, ...]):
    from hrm.models import Department

    for name in names:
        dept = Department.objects.filter(name__iexact=name, is_active=True).first()
        if dept:
            return dept
    for name in names:
        token = name.split()[0]
        dept = Department.objects.filter(name__icontains=token, is_active=True).order_by('sort_order', 'name').first()
        if dept:
            return dept
    return None


def default_managed_department_for_scope(scope: str | None):
    from hrm.models import Department

    if scope == SCOPE_PRODUCTION:
        dept = _find_department_by_names(_PRODUCTION_NAME_CANDIDATES)
        if dept:
            return dept
        dept, _ = Department.objects.get_or_create(
            name='Bảo trì xưởng',
            defaults={'is_active': True, 'sort_order': 0},
        )
        return dept

    dept = _find_department_by_names(_IT_NAME_CANDIDATES)
    if dept:
        return dept
    dept, _ = Department.objects.get_or_create(
        name='IT / CNTT',
        defaults={'is_active': True, 'sort_order': 0},
    )
    return dept


def resolve_managed_department(value):
    """Tìm phòng ban từ tên hoặc id (import Excel)."""
    from hrm.models import Department

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return Department.objects.filter(pk=int(text), is_active=True).first()
    dept = Department.objects.filter(name__iexact=text, is_active=True).first()
    if dept:
        return dept
    return Department.objects.filter(name__icontains=text, is_active=True).order_by('sort_order', 'name').first()
