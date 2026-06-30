"""Nhóm NPL 2 cấp — truy vấn và lọc."""

from django.db.models import Prefetch, Q

from kho_npl.choices import DEFAULT_MATERIAL_CATEGORY_TREE
from kho_npl.models import MaterialCategory


def ensure_material_category_tree():
    """Đồng bộ cây nhóm 2 cấp từ DEFAULT_MATERIAL_CATEGORY_TREE."""
    for parent_code, parent_name, parent_sort, children in DEFAULT_MATERIAL_CATEGORY_TREE:
        parent, _ = MaterialCategory.objects.get_or_create(
            code=parent_code,
            defaults={
                'name': parent_name,
                'sort_order': parent_sort,
                'is_active': True,
                'parent': None,
            },
        )
        updated = False
        if parent.name != parent_name:
            parent.name = parent_name
            updated = True
        if parent.sort_order != parent_sort:
            parent.sort_order = parent_sort
            updated = True
        if parent.parent_id is not None:
            parent.parent = None
            updated = True
        if not parent.is_active:
            parent.is_active = True
            updated = True
        if updated:
            parent.save()

        for child_code, child_name, child_sort in children:
            child, created = MaterialCategory.objects.get_or_create(
                code=child_code,
                defaults={
                    'name': child_name,
                    'sort_order': child_sort,
                    'is_active': True,
                    'parent': parent,
                },
            )
            if not created:
                child.parent = parent
                child.name = child_name
                child.sort_order = child_sort
                child.is_active = True
                child.save()


def active_category_roots():
    child_qs = MaterialCategory.objects.filter(is_active=True).order_by('sort_order', 'name')
    return (
        MaterialCategory.objects.filter(is_active=True, parent__isnull=True)
        .prefetch_related(Prefetch('children', queryset=child_qs))
        .order_by('sort_order', 'name')
    )


def active_category_leaves():
    return (
        MaterialCategory.objects.filter(is_active=True, parent__isnull=False)
        .select_related('parent')
        .order_by('parent__sort_order', 'parent__name', 'sort_order', 'name')
    )


def expand_category_filter_ids(category_ids: list[int]) -> list[int]:
    """Mở rộng ID nhóm cấp 1 → tất cả nhóm cấp 2; giữ nguyên ID nhóm cấp 2."""
    if not category_ids:
        return []
    expanded: set[int] = set()
    cats = MaterialCategory.objects.filter(pk__in=category_ids, is_active=True)
    for cat in cats:
        if cat.parent_id is None:
            expanded.update(
                MaterialCategory.objects.filter(parent_id=cat.pk, is_active=True).values_list('pk', flat=True)
            )
        else:
            expanded.add(cat.pk)
    return sorted(expanded)


def category_filter_q(category_ids: list[int]) -> Q:
    leaf_ids = expand_category_filter_ids(category_ids)
    if not leaf_ids:
        return Q()
    return Q(category_id__in=leaf_ids)
