"""Gom kho sản phẩm theo Style — trình bày giống Bán hàng / Hàng hoá."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal

from kho_san_pham.choices import PRODUCT_TYPE_LABELS
from kho_san_pham.models import Product


@dataclass
class StyleVariant:
    id: int
    code: str
    size_label: str
    color_code: str
    color_label: str
    base_price: Decimal | None
    image_url: str
    is_active: bool
    product_type: str
    accounting_code: str
    bar_code: str
    kiotviet_code: str


@dataclass
class StyleGroup:
    key: str
    style_code: str
    name: str
    category_name: str
    unit: str
    product_type: str
    representative_id: int
    image_url: str = ''
    codes: list[str] = field(default_factory=list)
    variants: list[StyleVariant] = field(default_factory=list)
    variant_count: int = 0
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    is_active: bool = True
    is_group: bool = False


def _group_key(product: Product) -> str:
    style = (product.style_code or '').strip().upper()
    if style:
        return f'style:{style}'
    # Không có Style → mỗi SKU một dòng
    return f'sku:{product.pk}'


def _variant_from_product(product: Product) -> StyleVariant:
    return StyleVariant(
        id=product.pk,
        code=product.code or '',
        size_label=product.size_label or '',
        color_code=product.color_code or '',
        color_label=product.color_label or '',
        base_price=product.base_price,
        image_url=product.display_image_url or '',
        is_active=bool(product.is_active),
        product_type=product.product_type,
        accounting_code=product.accounting_code or '',
        bar_code=product.bar_code or '',
        kiotviet_code=product.kiotviet_code or '',
    )


def group_products_by_style(products: list[Product]) -> list[StyleGroup]:
    buckets: OrderedDict[str, list[Product]] = OrderedDict()
    for product in products:
        buckets.setdefault(_group_key(product), []).append(product)

    groups: list[StyleGroup] = []
    for key, items in buckets.items():
        items = sorted(
            items,
            key=lambda p: (
                (p.color_code or '').upper(),
                (p.size_label or '').upper(),
                (p.code or '').upper(),
                p.pk,
            ),
        )
        rep = items[0]
        prices = [p.base_price for p in items if p.base_price is not None]
        image_url = ''
        for p in items:
            url = p.display_image_url
            if url:
                image_url = url
                break
        variants = [_variant_from_product(p) for p in items]
        style_code = (rep.style_code or '').strip()
        groups.append(StyleGroup(
            key=key,
            style_code=style_code,
            name=rep.name or style_code or rep.code,
            category_name=rep.category_name or '',
            unit=rep.unit or '',
            product_type=rep.product_type,
            representative_id=rep.pk,
            image_url=image_url,
            codes=[p.code for p in items if p.code],
            variants=variants,
            variant_count=len(variants),
            min_price=min(prices) if prices else None,
            max_price=max(prices) if prices else None,
            is_active=any(p.is_active for p in items),
            is_group=len(variants) > 1,
        ))
    return groups


def format_style_group(group: StyleGroup) -> dict:
    # Dòng cha: 1 mã Style gốc; dòng con: SKU size
    if group.style_code:
        code_label = group.style_code
        if group.is_group and group.variant_count > 1:
            code_label = f'{group.style_code} (+{group.variant_count - 1})'
    elif group.is_group and group.codes:
        code_label = f'{group.codes[0]} … (+{group.variant_count - 1})'
    elif group.codes:
        code_label = group.codes[0]
    else:
        code_label = '—'

    accounting_codes = sorted({
        (v.accounting_code or '').strip()
        for v in group.variants
        if (v.accounting_code or '').strip()
    })
    accounting_label = accounting_codes[0] if len(accounting_codes) == 1 else (
        f'{accounting_codes[0]}…' if accounting_codes else '—'
    )
    barcodes = sorted({
        (v.bar_code or '').strip()
        for v in group.variants
        if (v.bar_code or '').strip()
    })
    barcode_label = barcodes[0] if len(barcodes) == 1 else (
        f'{barcodes[0]}…' if barcodes else '—'
    )

    return {
        'id': group.representative_id,
        'group_key': group.key,
        'code': code_label,
        'style_code': group.style_code or '—',
        'accounting_code': accounting_label,
        'bar_code': barcode_label,
        'name': group.name,
        'category_name': group.category_name or '—',
        'unit': group.unit or '—',
        'product_type': group.product_type,
        'product_type_label': PRODUCT_TYPE_LABELS.get(group.product_type, group.product_type),
        'image_url': group.image_url,
        'variant_count': group.variant_count,
        'min_price': group.min_price,
        'max_price': group.max_price,
        'base_price': group.min_price,
        'is_active': group.is_active,
        'is_group': group.is_group,
        'variants': [
            {
                'id': v.id,
                'code': v.code or '—',
                'size_label': v.size_label or '—',
                'color_code': v.color_code or '',
                'color_label': v.color_label or '',
                'base_price': v.base_price,
                'image_url': v.image_url,
                'is_active': v.is_active,
                'accounting_code': v.accounting_code or '—',
                'bar_code': v.bar_code or '—',
                'kiotviet_code': v.kiotviet_code or '—',
            }
            for v in group.variants
        ],
    }
