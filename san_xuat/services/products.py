"""Resolve mã hàng KiotViet cho hồ sơ SX."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q


@dataclass(frozen=True)
class KvProductRef:
    code: str
    name: str
    base_price: object
    kiotviet_id: int | None
    image_url: str


def _first_image_url(product) -> str:
    urls = getattr(product, 'image_urls', None) or []
    if isinstance(urls, list) and urls:
        first = urls[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return (first.get('url') or first.get('Image') or '') or ''
    return ''


def find_kv_product(product_code: str):
    """Trả KvProduct hoặc None."""
    code = (product_code or '').strip()
    if not code:
        return None
    try:
        from kiotviet.models import KvProduct
        from kiotviet.sync_service import current_retailer
    except ImportError:
        return None

    retailer = current_retailer()
    qs = KvProduct.objects.filter(retailer=retailer, is_deleted=False, code=code)
    return qs.first()


def resolve_kv_product_ref(product_code: str) -> KvProductRef | None:
    product = find_kv_product(product_code)
    if not product:
        return None
    name = (product.name or product.full_name or '').strip()
    return KvProductRef(
        code=(product.code or '').strip(),
        name=name,
        base_price=product.base_price or 0,
        kiotviet_id=product.kiotviet_id,
        image_url=_first_image_url(product),
    )


def search_kv_products(q: str = '', *, limit: int = 30) -> list[dict]:
    q = (q or '').strip()
    try:
        from kiotviet.models import KvProduct
        from kiotviet.sync_service import current_retailer
    except ImportError:
        return []

    retailer = current_retailer()
    qs = (
        KvProduct.objects.filter(retailer=retailer, is_deleted=False)
        .exclude(code='')
        .order_by('code')
    )
    if q:
        qs = qs.filter(
            Q(code__icontains=q)
            | Q(name__icontains=q)
            | Q(full_name__icontains=q)
            | Q(bar_code__icontains=q),
        )
    rows = []
    for product in qs[:limit]:
        code = (product.code or '').strip()
        if not code:
            continue
        name = (product.name or product.full_name or '').strip()
        rows.append({
            'id': code,
            'code': code,
            'name': name,
            'text': f'{code} — {name}' if name else code,
            'base_price': str(product.base_price or 0),
        })
    return rows
