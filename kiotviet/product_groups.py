"""Gộp sản phẩm quần áo: cùng tên, mỗi size một mã SP riêng."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Q, Sum

from .category_paths import CategoryPathResolver, category_info_from_product
from .models import KvProduct, KvProductAttribute, KvProductInventory
from .sync_service import current_retailer

SIZE_ATTR_NAMES = frozenset({
    'size', 'kích cỡ', 'kich co', 'cỡ', 'co',
})


def display_group_name(name: str, full_name: str) -> str:
    return (name or full_name or '').strip() or '—'


def group_key(name: str, full_name: str) -> str:
    return display_group_name(name, full_name).casefold()


def _size_label(attrs: list[dict]) -> str:
    for attr in attrs:
        name = (attr.get('attributeName') or '').strip().lower()
        if name in SIZE_ATTR_NAMES or 'size' in name or 'cỡ' in name or 'co' in name:
            value = (attr.get('attributeValue') or '').strip()
            if value:
                return value
    for attr in attrs:
        value = (attr.get('attributeValue') or '').strip()
        if value:
            return value
    return ''


def _product_attrs_map(retailer: str, product_ids: list[int]) -> dict[int, list[dict]]:
    if not product_ids:
        return {}
    result: dict[int, list[dict]] = defaultdict(list)
    for row in KvProductAttribute.objects.filter(
        retailer=retailer,
        product_kiotviet_id__in=product_ids,
    ).order_by('attribute_name', 'attribute_value'):
        result[row.product_kiotviet_id].append({
            'attributeName': row.attribute_name,
            'attributeValue': row.attribute_value,
        })
    return dict(result)


def _inventory_totals(retailer: str, product_ids: list[int]) -> dict[int, dict[str, float]]:
    if not product_ids:
        return {}
    rows = (
        KvProductInventory.objects.filter(
            retailer=retailer,
            product_kiotviet_id__in=product_ids,
            is_deleted=False,
        )
        .values('product_kiotviet_id')
        .annotate(
            on_hand_total=Sum('on_hand'),
            reserved_total=Sum('reserved'),
        )
    )
    return {
        int(row['product_kiotviet_id']): {
            'on_hand': float(row['on_hand_total'] or 0),
            'reserved': float(row['reserved_total'] or 0),
        }
        for row in rows
    }


def _stock_totals(retailer: str, product_ids: list[int]) -> dict[int, float]:
    return {
        product_id: values['on_hand']
        for product_id, values in _inventory_totals(retailer, product_ids).items()
    }


@dataclass
class ProductGroupVariant:
    id: int
    code: str
    size_label: str
    on_hand: float = 0.0
    reserved: float = 0.0
    base_price: float | None = None
    image_url: str = ''


@dataclass
class ProductGroup:
    key: str
    name: str
    category_name: str
    category_path: str
    unit: str
    variant_count: int
    representative_id: int
    category_path_parts: list[str] = field(default_factory=list)
    category_kiotviet_id: int | None = None
    image_urls: list[str] = field(default_factory=list)
    variant_ids: list[int] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    variants: list[ProductGroupVariant] = field(default_factory=list)
    total_on_hand: float = 0.0
    total_reserved: float = 0.0
    min_price: float | None = None
    max_price: float | None = None
    allows_sale_values: list = field(default_factory=list)
    is_active_values: list = field(default_factory=list)


def _build_group_variants(
    variants: list[KvProduct],
    *,
    attrs_map: dict[int, list[dict]],
    inventory_by_id: dict[int, dict[str, float]],
) -> list[ProductGroupVariant]:
    rows: list[ProductGroupVariant] = []
    for product in variants:
        product_id = product.kiotviet_id
        inventory = inventory_by_id.get(product_id, {})
        size_label = _size_label(attrs_map.get(product_id, []))
        image_url = next(
            (url for url in (product.image_urls or []) if url),
            '',
        )
        rows.append(ProductGroupVariant(
            id=product_id,
            code=(product.code or '').strip(),
            size_label=size_label or '—',
            on_hand=inventory.get('on_hand', 0.0),
            reserved=inventory.get('reserved', 0.0),
            base_price=float(product.base_price) if product.base_price is not None else None,
            image_url=image_url,
        ))
    return rows


def _resolve_group_category(
    variants: list[KvProduct],
    resolver: CategoryPathResolver,
) -> dict:
    cat_ids = {p.category_kiotviet_id for p in variants if p.category_kiotviet_id}
    if len(cat_ids) == 1:
        return category_info_from_product(variants[0], resolver)
    if len(cat_ids) > 1:
        paths: list[str] = []
        for product in variants:
            info = category_info_from_product(product, resolver)
            if info['category_path'] not in paths:
                paths.append(info['category_path'])
        return {
            'category_id': None,
            'category_name': 'Khác nhau',
            'category_path': ' · '.join(paths),
            'category_path_parts': [],
        }
    rep = variants[0]
    return category_info_from_product(rep, resolver)


def _build_groups_from_products(
    products: list[KvProduct],
    *,
    retailer: str,
) -> list[ProductGroup]:
    buckets: dict[str, list[KvProduct]] = defaultdict(list)
    for product in products:
        buckets[group_key(product.name, product.full_name)].append(product)

    all_ids = [p.kiotviet_id for p in products]
    inventory_by_id = _inventory_totals(retailer, all_ids)
    attrs_map = _product_attrs_map(retailer, all_ids)
    category_resolver = CategoryPathResolver(retailer)

    groups: list[ProductGroup] = []
    for key, variants in buckets.items():
        variants.sort(key=lambda p: (p.code or '', p.kiotviet_id))
        rep = variants[0]
        category = _resolve_group_category(variants, category_resolver)
        prices = [
            float(p.base_price)
            for p in variants
            if p.base_price is not None
        ]
        images: list[str] = []
        for p in variants:
            for url in (p.image_urls or []):
                if url and url not in images:
                    images.append(url)
        variant_ids = [p.kiotviet_id for p in variants]
        groups.append(ProductGroup(
            key=key,
            name=display_group_name(rep.name, rep.full_name),
            category_name=category['category_name'],
            category_path=category['category_path'],
            category_path_parts=category['category_path_parts'],
            category_kiotviet_id=category['category_id'],
            unit=rep.unit or '',
            variant_count=len(variants),
            representative_id=rep.kiotviet_id,
            image_urls=images,
            variant_ids=variant_ids,
            codes=[p.code for p in variants if p.code],
            variants=_build_group_variants(
                variants,
                attrs_map=attrs_map,
                inventory_by_id=inventory_by_id,
            ),
            total_on_hand=sum(
                inventory_by_id.get(vid, {}).get('on_hand', 0.0) for vid in variant_ids
            ),
            total_reserved=sum(
                inventory_by_id.get(vid, {}).get('reserved', 0.0) for vid in variant_ids
            ),
            min_price=min(prices) if prices else None,
            max_price=max(prices) if prices else None,
            allows_sale_values=[p.allows_sale for p in variants],
            is_active_values=[p.is_active for p in variants],
        ))

    return groups


def browse_product_groups(
    *,
    page: int,
    per_page: int,
    retailer: str | None = None,
    search: str = '',
    name: str = '',
    code: str = '',
    bar_code: str = '',
    filters=None,
) -> tuple[list[ProductGroup], int]:
    """Trả về danh sách nhóm SP (đã gộp size) và tổng số nhóm."""
    from .product_filters import (
        ProductListFilters,
        apply_product_queryset_filters,
        filter_product_groups,
    )

    retailer = retailer or current_retailer()
    filters = filters or ProductListFilters()
    qs = KvProduct.objects.filter(retailer=retailer, is_deleted=False)
    qs = apply_product_queryset_filters(qs, retailer=retailer, filters=filters)

    def _paginate(groups: list[ProductGroup]) -> tuple[list[ProductGroup], int]:
        groups = filter_product_groups(groups, filters)
        total = len(groups)
        offset = (max(page, 1) - 1) * per_page
        return groups[offset: offset + per_page], total

    if search:
        term = search.strip()
        matched = qs.filter(
            Q(code__iexact=term) | Q(bar_code__iexact=term),
        ).first()
        if matched:
            gk = group_key(matched.name, matched.full_name)
            products = [
                p for p in qs
                if group_key(p.name, p.full_name) == gk
            ]
            return _paginate(_build_groups_from_products(products, retailer=retailer))
        qs = qs.filter(
            Q(code__icontains=term)
            | Q(name__icontains=term)
            | Q(full_name__icontains=term)
            | Q(bar_code__icontains=term),
        )
    elif code:
        term = code.strip()
        matched = qs.filter(code__iexact=term).first()
        if matched:
            gk = group_key(matched.name, matched.full_name)
            products = [
                p for p in qs
                if group_key(p.name, p.full_name) == gk
            ]
            return _paginate(_build_groups_from_products(products, retailer=retailer))
        qs = qs.filter(code__icontains=term)
    elif bar_code:
        term = bar_code.strip()
        matched = qs.filter(bar_code__iexact=term).first()
        if matched:
            gk = group_key(matched.name, matched.full_name)
            products = [
                p for p in qs
                if group_key(p.name, p.full_name) == gk
            ]
            return _paginate(_build_groups_from_products(products, retailer=retailer))
        qs = qs.filter(bar_code__icontains=term)
    elif name:
        term = name.strip()
        qs = qs.filter(Q(name__icontains=term) | Q(full_name__icontains=term))

    products = list(qs.order_by('name', 'code', 'kiotviet_id'))
    return _paginate(_build_groups_from_products(products, retailer=retailer))


def get_product_group(retailer: str, product_id: int) -> dict | None:
    """Lấy nhóm SP chứa product_id, kèm từng size/mã."""
    anchor = KvProduct.objects.filter(
        retailer=retailer,
        kiotviet_id=product_id,
        is_deleted=False,
    ).first()
    if not anchor:
        return None

    gkey = group_key(anchor.name, anchor.full_name)
    base_name = (anchor.name or '').strip()
    base_full = (anchor.full_name or '').strip()
    match_q = Q()
    if base_name:
        match_q |= Q(name__iexact=base_name)
    if base_full:
        match_q |= Q(full_name__iexact=base_full)
    if match_q:
        candidates = KvProduct.objects.filter(
            retailer=retailer, is_deleted=False,
        ).filter(match_q).order_by('code', 'kiotviet_id')
        variants = [
            p for p in candidates
            if group_key(p.name, p.full_name) == gkey
        ]
    else:
        variants = []
    if not variants:
        variants = [anchor]

    variant_ids = [p.kiotviet_id for p in variants]
    attrs_map = _product_attrs_map(retailer, variant_ids)
    stock_by_id = _stock_totals(retailer, variant_ids)

    variant_rows = []
    for product in variants:
        pdata = product.to_api_dict(include_inventory=True)
        attrs = attrs_map.get(product.kiotviet_id, [])
        pdata['attributes'] = attrs
        pdata['size_label'] = _size_label(attrs)
        pdata['stock_total'] = stock_by_id.get(product.kiotviet_id, 0.0)
        pdata['hasVariants'] = product.has_variants
        pdata['productType'] = product.product_type
        pdata['description'] = product.description
        variant_rows.append(pdata)

    images: list[str] = []
    for p in variants:
        for url in (p.image_urls or []):
            if url and url not in images:
                images.append(url)

    prices = [
        float(p.base_price) for p in variants if p.base_price is not None
    ]
    category = _resolve_group_category(variants, CategoryPathResolver(retailer))
    return {
        'name': display_group_name(anchor.name, anchor.full_name),
        'category_name': category['category_name'],
        'category_path': category['category_path'],
        'category_path_parts': category['category_path_parts'],
        'category_kiotviet_id': category['category_id'],
        'unit': anchor.unit or '',
        'variant_count': len(variants),
        'representative_id': variants[0].kiotviet_id,
        'images': images,
        'variants': variant_rows,
        'total_on_hand': sum(stock_by_id.get(vid, 0.0) for vid in variant_ids),
        'min_price': min(prices) if prices else None,
        'max_price': max(prices) if prices else None,
    }
