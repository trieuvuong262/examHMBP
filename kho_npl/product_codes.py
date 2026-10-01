"""Tìm mã sản phẩm cho phiếu xuất NPL."""

from __future__ import annotations

from django.db.models import Q

from kho_npl.models import StockIssue


def _catalog_product_rows(q: str, *, limit: int) -> list[dict]:
    try:
        from san_xuat.services.products import search_products
    except ImportError:
        return []
    try:
        products = search_products(q, limit=limit)
    except Exception:
        return []
    return [
        {
            'id': row['code'],
            'code': row['code'],
            'name': row.get('name') or '',
            'text': row.get('text') or row['code'],
            'image_url': row.get('image_url') or '',
            'color': row.get('color') or '',
        }
        for row in products
        if row.get('code')
    ]


def _kv_product_rows(q: str, *, limit: int, exclude: set[str]) -> list[dict]:
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
        if not code or code.casefold() in exclude:
            continue
        name = (product.name or product.full_name or '').strip()
        images = product.image_urls or []
        rows.append({
            'id': code,
            'code': code,
            'name': name,
            'text': f'{code} — {name}' if name else code,
            'image_url': images[0] if images else '',
        })
    return rows


def _issue_product_rows(q: str, *, limit: int, exclude: set[str]) -> list[dict]:
    qs = StockIssue.objects.exclude(product_code='').values_list('product_code', flat=True).distinct()
    if q:
        qs = qs.filter(product_code__icontains=q)
    rows = []
    for code in qs.order_by('product_code')[:limit]:
        code = (code or '').strip()
        if not code or code.casefold() in exclude:
            continue
        rows.append({'id': code, 'code': code, 'name': '', 'text': code, 'image_url': ''})
    return rows


def search_product_codes(q: str = '', *, limit: int = 40) -> list[dict]:
    q = (q or '').strip()
    results = _catalog_product_rows(q, limit=limit)
    seen = {row['code'].casefold() for row in results}
    if len(results) < limit:
        extra = _kv_product_rows(q, limit=limit - len(results), exclude=seen)
        results.extend(extra)
        seen.update(row['code'].casefold() for row in extra)
    if len(results) < limit:
        results.extend(
            _issue_product_rows(q, limit=limit - len(results), exclude=seen),
        )
    return results[:limit]


def product_code_display(code: str) -> dict:
    """{code, name, text, image_url} cho mã SP đã lưu trên phiếu."""
    code = (code or '').strip()
    if not code:
        return {}
    for row in search_product_codes(code, limit=10):
        if row['code'].casefold() == code.casefold():
            return {**row, 'code': code, 'id': code}
    return {'id': code, 'code': code, 'name': '', 'text': code, 'image_url': ''}


def product_code_option_label(code: str) -> str:
    return product_code_display(code).get('text', '')
