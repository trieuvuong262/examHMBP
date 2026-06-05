"""Bộ lọc danh sách hàng hoá (mirror kv_*)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Q, QuerySet

from .category_paths import CategoryPathResolver
from .models import KvCategory, KvProduct

DEFAULT_IS_ACTIVE = 'yes'

PRODUCT_TYPE_OPTIONS = (
    ('', 'Tất cả loại'),
    ('2', 'Hàng thường'),
    ('1', 'Hàng combo'),
    ('3', 'Dịch vụ'),
)

SORT_OPTIONS = (
    ('name', 'Tên A→Z'),
    ('stock_desc', 'Tồn kho cao → thấp'),
    ('stock_asc', 'Tồn kho thấp → cao'),
    ('price_asc', 'Giá thấp → cao'),
    ('price_desc', 'Giá cao → thấp'),
)


@dataclass
class ProductListFilters:
    category_id: int | None = None
    category_q: str = ''
    is_active: str = DEFAULT_IS_ACTIVE
    stock: str = ''
    product_type: str = ''
    unit: str = ''
    sort: str = 'name'

    def is_non_default_filter(self) -> bool:
        return bool(
            self.category_id
            or self.category_q
            or self.is_active != DEFAULT_IS_ACTIVE
            or self.stock in ('yes', 'no')
            or self.product_type
            or self.unit
            or self.sort != 'name'
        )


def parse_product_filters(request) -> ProductListFilters:
    category_raw = (request.GET.get('category') or '').strip()
    category_id = int(category_raw) if category_raw.isdigit() else None
    category_q = (request.GET.get('category_q') or '').strip()

    if 'is_active' in request.GET:
        is_active = (request.GET.get('is_active') or '').strip()
        if is_active == 'all':
            is_active = ''
        elif is_active not in ('yes', 'no'):
            is_active = DEFAULT_IS_ACTIVE
    else:
        is_active = DEFAULT_IS_ACTIVE

    stock = (request.GET.get('stock') or '').strip()
    if stock not in ('yes', 'no'):
        stock = ''

    product_type = (request.GET.get('product_type') or '').strip()
    if product_type not in {'1', '2', '3'}:
        product_type = ''

    unit = (request.GET.get('unit') or '').strip()

    sort = (request.GET.get('sort') or 'name').strip()
    if sort not in {value for value, _ in SORT_OPTIONS}:
        sort = 'name'

    return ProductListFilters(
        category_id=category_id,
        category_q=category_q,
        is_active=is_active,
        stock=stock,
        product_type=product_type,
        unit=unit,
        sort=sort,
    )


def category_descendant_ids(retailer: str, category_id: int) -> set[int]:
    children: dict[int | None, list[int]] = defaultdict(list)
    for row in KvCategory.objects.filter(retailer=retailer, is_deleted=False):
        children[row.parent_kiotviet_id].append(row.kiotviet_id)
    result = {category_id}
    stack = [category_id]
    while stack:
        current = stack.pop()
        for child_id in children.get(current, []):
            if child_id not in result:
                result.add(child_id)
                stack.append(child_id)
    return result


def list_category_filter_options(retailer: str) -> list[dict]:
    resolver = CategoryPathResolver(retailer)
    options = [{'id': '', 'label': 'Tất cả nhóm hàng', 'depth': 0}]
    rows = []
    for row in KvCategory.objects.filter(retailer=retailer, is_deleted=False):
        info = resolver.resolve(row.kiotviet_id, fallback_name=row.category_name)
        depth = len(info['category_path_parts']) or 1
        indent = '　' * (depth - 1)
        rows.append({
            'id': str(row.kiotviet_id),
            'label': f'{indent}{info["category_path"]}',
            'depth': depth,
        })
    rows.sort(key=lambda item: item['label'].casefold())
    options.extend(rows)
    return options


def list_unit_filter_options(retailer: str) -> list[dict]:
    units = (
        KvProduct.objects.filter(retailer=retailer, is_deleted=False)
        .exclude(unit='')
        .values_list('unit', flat=True)
        .distinct()
        .order_by('unit')
    )
    options = [{'value': '', 'label': 'Tất cả ĐVT'}]
    options.extend({'value': unit, 'label': unit} for unit in units)
    return options


def apply_product_queryset_filters(
    qs: QuerySet[KvProduct],
    *,
    retailer: str,
    filters: ProductListFilters,
) -> QuerySet[KvProduct]:
    if filters.category_id:
        qs = qs.filter(
            category_kiotviet_id__in=category_descendant_ids(retailer, filters.category_id),
        )
    if filters.category_q:
        term = filters.category_q
        qs = qs.filter(
            Q(category_path__icontains=term)
            | Q(category_name__icontains=term),
        )
    if filters.product_type:
        qs = qs.filter(product_type=int(filters.product_type))
    if filters.unit:
        qs = qs.filter(unit=filters.unit)
    return qs


def _group_has_any(values: list, expected: bool) -> bool:
    cleaned = [value for value in values if value is not None]
    return any(value is expected for value in cleaned)


def filter_product_groups(groups, filters: ProductListFilters):
    result = groups
    if filters.is_active == 'yes':
        result = [g for g in result if _group_has_any(g.is_active_values, True)]
    elif filters.is_active == 'no':
        result = [g for g in result if not _group_has_any(g.is_active_values, True)]
    if filters.stock == 'yes':
        result = [g for g in result if g.total_on_hand > 0]
    elif filters.stock == 'no':
        result = [g for g in result if g.total_on_hand <= 0]
    if filters.category_q:
        term = filters.category_q.casefold()
        result = [
            g for g in result
            if term in (g.category_path or '').casefold()
            or term in (g.category_name or '').casefold()
            or any(term in part.casefold() for part in (g.category_path_parts or []))
        ]
    return sort_product_groups(result, filters.sort)


def sort_product_groups(groups, sort_key: str):
    if sort_key == 'stock_desc':
        return sorted(groups, key=lambda g: (-g.total_on_hand, g.name.casefold()))
    if sort_key == 'stock_asc':
        return sorted(groups, key=lambda g: (g.total_on_hand, g.name.casefold()))
    if sort_key == 'price_asc':
        return sorted(
            groups,
            key=lambda g: (
                g.min_price is None,
                g.min_price or 0,
                g.name.casefold(),
            ),
        )
    if sort_key == 'price_desc':
        return sorted(
            groups,
            key=lambda g: (
                g.min_price is None,
                -(g.min_price or 0),
                g.name.casefold(),
            ),
        )
    return sorted(groups, key=lambda g: g.name.casefold())
