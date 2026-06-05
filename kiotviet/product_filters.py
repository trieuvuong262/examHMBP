"""Bộ lọc danh sách hàng hoá (mirror kv_*)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.db.models import QuerySet

from .category_paths import CategoryPathResolver
from .models import KvCategory, KvProduct


@dataclass
class ProductListFilters:
    category_id: int | None = None
    allows_sale: str = ''
    is_active: str = ''
    stock: str = ''

    def is_active_filter(self) -> bool:
        return bool(
            self.category_id
            or self.allows_sale in ('yes', 'no')
            or self.is_active in ('yes', 'no')
            or self.stock in ('yes', 'no')
        )


def parse_product_filters(request) -> ProductListFilters:
    category_raw = (request.GET.get('category') or '').strip()
    category_id = int(category_raw) if category_raw.isdigit() else None
    allows_sale = (request.GET.get('allows_sale') or '').strip()
    if allows_sale not in ('yes', 'no'):
        allows_sale = ''
    is_active = (request.GET.get('is_active') or '').strip()
    if is_active not in ('yes', 'no'):
        is_active = ''
    stock = (request.GET.get('stock') or '').strip()
    if stock not in ('yes', 'no'):
        stock = ''
    return ProductListFilters(
        category_id=category_id,
        allows_sale=allows_sale,
        is_active=is_active,
        stock=stock,
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
    options = [{'id': '', 'label': 'Tất cả nhóm hàng'}]
    for row in KvCategory.objects.filter(retailer=retailer, is_deleted=False):
        info = resolver.resolve(row.kiotviet_id, fallback_name=row.category_name)
        options.append({
            'id': str(row.kiotviet_id),
            'label': info['category_path'],
        })
    options[1:] = sorted(options[1:], key=lambda item: item['label'].casefold())
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
    return qs


def _group_has_any(values: list, expected: bool) -> bool:
    cleaned = [value for value in values if value is not None]
    return any(value is expected for value in cleaned)


def _group_all_match(values: list, expected: bool) -> bool:
    cleaned = [value for value in values if value is not None]
    return bool(cleaned) and all(value is expected for value in cleaned)


def filter_product_groups(groups, filters: ProductListFilters):
    result = groups
    if filters.allows_sale == 'yes':
        result = [g for g in result if _group_has_any(g.allows_sale_values, True)]
    elif filters.allows_sale == 'no':
        result = [g for g in result if _group_all_match(g.allows_sale_values, False)]
    if filters.is_active == 'yes':
        result = [g for g in result if _group_has_any(g.is_active_values, True)]
    elif filters.is_active == 'no':
        result = [g for g in result if not _group_has_any(g.is_active_values, True)]
    if filters.stock == 'yes':
        result = [g for g in result if g.total_on_hand > 0]
    elif filters.stock == 'no':
        result = [g for g in result if g.total_on_hand <= 0]
    return result
