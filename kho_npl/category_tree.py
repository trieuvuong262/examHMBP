"""Nhóm NPL một cấp — truy vấn, đồng bộ và lọc."""

from django.db.models import Q

from kho_npl.choices import DEFAULT_MATERIAL_CATEGORIES
from kho_npl.filter_utils import parse_int_ids
from kho_npl.models import Material, MaterialCategory


def ensure_material_category_tree():
    """Đồng bộ danh mục nhóm phẳng mặc định."""
    for code, name, sort_order in DEFAULT_MATERIAL_CATEGORIES:
        MaterialCategory.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'sort_order': sort_order,
                'is_active': True,
            },
        )


def active_category_roots():
    """Tên tương thích cũ; trả toàn bộ nhóm phẳng đang dùng."""
    return MaterialCategory.objects.filter(is_active=True).order_by('sort_order', 'name')


def active_category_leaves():
    """Tên tương thích cũ; trả toàn bộ nhóm phẳng đang dùng."""
    return active_category_roots()


def material_form_category_queryset(material: Material | None = None):
    """Nhóm phẳng; luôn gồm nhóm hiện tại khi sửa NPL."""
    qs = active_category_roots()
    if material and material.category_id and not qs.filter(pk=material.category_id).exists():
        return (
            MaterialCategory.objects.filter(
                Q(pk=material.category_id) | Q(pk__in=qs.values('pk')),
            )
            .order_by('sort_order', 'name')
        )
    return qs


def expand_category_filter_ids(category_ids: list[int]) -> list[int]:
    """Giữ các ID nhóm phẳng hợp lệ."""
    return list(
        MaterialCategory.objects.filter(
            pk__in=category_ids,
            is_active=True,
        ).values_list('pk', flat=True)
    )


def category_filter_q(category_ids: list[int]) -> Q:
    leaf_ids = expand_category_filter_ids(category_ids)
    if not leaf_ids:
        return Q()
    return Q(category_id__in=leaf_ids)


def parse_category_cascade_filter(request) -> tuple[int | None, list[int]]:
    """Đọc bộ lọc nhóm phẳng; phần tử đầu giữ tương thích chữ ký cũ."""
    return None, parse_int_ids(request, 'category')


def resolve_category_filter_q(parent_id: int | None, leaf_ids: list[int]) -> Q:
    if leaf_ids:
        return Q(category_id__in=leaf_ids)
    return Q()


def category_cascade_for_filter() -> dict[str, list[dict]]:
    return {}


def category_children_for_parent(parent_id: int | None):
    return MaterialCategory.objects.none()
