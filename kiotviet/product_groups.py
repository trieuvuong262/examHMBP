"""Gộp sản phẩm quần áo: cùng tên, mỗi size một mã SP riêng."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Q, Sum

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


def _stock_totals(retailer: str, product_ids: list[int]) -> dict[int, float]:
    if not product_ids:
        return {}
    rows = (
        KvProductInventory.objects.filter(
            retailer=retailer,
            product_kiotviet_id__in=product_ids,
            is_deleted=False,
        )
        .values('product_kiotviet_id')
        .annotate(total=Sum('on_hand'))
    )
    return {
        int(row['product_kiotviet_id']): float(row['total'] or 0)
        for row in rows
    }


@dataclass
class ProductGroup:
    key: str
    name: str
    category_name: str
    unit: str
    variant_count: int
    representative_id: int
    image_urls: list[str] = field(default_factory=list)
    variant_ids: list[int] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    total_on_hand: float = 0.0
    min_price: float | None = None
    max_price: float | None = None


def _build_groups_from_products(
    products: list[KvProduct],
    *,
    retailer: str,
) -> list[ProductGroup]:
    buckets: dict[str, list[KvProduct]] = defaultdict(list)
    for product in products:
        buckets[group_key(product.name, product.full_name)].append(product)

    all_ids = [p.kiotviet_id for p in products]
    stock_by_id = _stock_totals(retailer, all_ids)

    groups: list[ProductGroup] = []
    for key, variants in buckets.items():
        variants.sort(key=lambda p: (p.code or '', p.kiotviet_id))
        rep = variants[0]
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
            category_name=rep.category_name or '',
            unit=rep.unit or '',
            variant_count=len(variants),
            representative_id=rep.kiotviet_id,
            image_urls=images,
            variant_ids=variant_ids,
            codes=[p.code for p in variants if p.code],
            total_on_hand=sum(stock_by_id.get(vid, 0.0) for vid in variant_ids),
            min_price=min(prices) if prices else None,
            max_price=max(prices) if prices else None,
        ))

    groups.sort(key=lambda g: g.name.casefold())
    return groups


def browse_product_groups(
    *,
    page: int,
    per_page: int,
    retailer: str | None = None,
    name: str = '',
    code: str = '',
    bar_code: str = '',
) -> tuple[list[ProductGroup], int]:
    """Trả về danh sách nhóm SP (đã gộp size) và tổng số nhóm."""
    retailer = retailer or current_retailer()
    qs = KvProduct.objects.filter(retailer=retailer, is_deleted=False)

    if code:
        term = code.strip()
        matched = qs.filter(code__iexact=term).first()
        if matched:
            gk = group_key(matched.name, matched.full_name)
            products = [
                p for p in qs
                if group_key(p.name, p.full_name) == gk
            ]
            groups = _build_groups_from_products(products, retailer=retailer)
            total = len(groups)
            offset = (max(page, 1) - 1) * per_page
            return groups[offset: offset + per_page], total
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
            groups = _build_groups_from_products(products, retailer=retailer)
            total = len(groups)
            offset = (max(page, 1) - 1) * per_page
            return groups[offset: offset + per_page], total
        qs = qs.filter(bar_code__icontains=term)
    elif name:
        term = name.strip()
        qs = qs.filter(Q(name__icontains=term) | Q(full_name__icontains=term))

    products = list(qs.order_by('name', 'code', 'kiotviet_id'))
    groups = _build_groups_from_products(products, retailer=retailer)
    total = len(groups)
    offset = (max(page, 1) - 1) * per_page
    return groups[offset: offset + per_page], total


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
    return {
        'name': display_group_name(anchor.name, anchor.full_name),
        'category_name': anchor.category_name or '',
        'unit': anchor.unit or '',
        'variant_count': len(variants),
        'representative_id': variants[0].kiotviet_id,
        'images': images,
        'variants': variant_rows,
        'total_on_hand': sum(stock_by_id.get(vid, 0.0) for vid in variant_ids),
        'min_price': min(prices) if prices else None,
        'max_price': max(prices) if prices else None,
    }
