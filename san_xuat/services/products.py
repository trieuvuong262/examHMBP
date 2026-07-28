"""Resolve mã SX / sản phẩm từ kho sản phẩm cho hồ sơ SX & LSX."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q


@dataclass(frozen=True)
class ProductRef:
    """Snapshot mã SX gốc từ kho SP cho hồ sơ SX / lệnh SX."""

    code: str
    name: str
    base_price: object
    kiotviet_id: int | None
    image_url: str


# Alias tương thích chỗ gọi cũ
KvProductRef = ProductRef


def _norm(code: str) -> str:
    return (code or '').strip()


def find_product(product_code: str):
    """Trả Product đại diện (SKU) trong kho SP, hoặc None.

    Khớp theo: style_code → SKU ``code`` → ``kiotviet_code``.
    """
    code = _norm(product_code)
    if not code:
        return None
    try:
        from kho_san_pham.models import Product
    except ImportError:
        return None

    qs = Product.objects.all()
    for lookup in (
        qs.filter(style_code__iexact=code, is_active=True).order_by('code'),
        qs.filter(style_code__iexact=code).order_by('code'),
        qs.filter(code__iexact=code, is_active=True),
        qs.filter(code__iexact=code),
        qs.filter(kiotviet_code__iexact=code, is_active=True).order_by('code'),
        qs.filter(kiotviet_code__iexact=code).order_by('code'),
    ):
        product = lookup.first()
        if product:
            return product
    return None


def _ref_from_product(product) -> ProductRef:
    style = (product.style_code or '').strip() or (product.code or '').strip()
    name = (product.name or product.full_name or '').strip()
    return ProductRef(
        code=style,
        name=name,
        base_price=product.base_price or 0,
        kiotviet_id=product.kiotviet_id,
        image_url=product.display_image_url or '',
    )


def _ref_from_style(style) -> ProductRef:
    return ProductRef(
        code=(style.code or '').strip(),
        name=(style.name or '').strip(),
        base_price=0,
        kiotviet_id=None,
        image_url='',
    )


def resolve_product_ref(product_code: str) -> ProductRef | None:
    """Resolve mã nhập (mã SX / SKU / mã KV) → ProductRef với ``code`` = mã SX chuẩn."""
    code = _norm(product_code)
    if not code:
        return None

    product = find_product(code)
    if product:
        return _ref_from_product(product)

    try:
        from kho_san_pham.models import ProductStyle
    except ImportError:
        return None

    style = (
        ProductStyle.objects.filter(code__iexact=code).first()
        or ProductStyle.objects.filter(root_kiotviet_code__iexact=code).first()
    )
    if style:
        return _ref_from_style(style)
    return None


def search_products(q: str = '', *, limit: int = 30) -> list[dict]:
    """TomSelect: danh sách mã SX từ kho SP (gom nhiều SKU theo style_code)."""
    q = _norm(q)
    limit = max(1, min(int(limit or 30), 50))
    try:
        from kho_san_pham.models import Product, ProductStyle
    except ImportError:
        return []

    rows: list[dict] = []
    seen: set[str] = set()

    def _add(code: str, name: str, base_price=0) -> bool:
        key = code.casefold()
        if not code or key in seen:
            return len(rows) >= limit
        seen.add(key)
        label = f'{code} — {name}' if name else code
        rows.append({
            'id': code,
            'code': code,
            'name': name,
            'text': label,
            'base_price': str(base_price or 0),
        })
        return len(rows) >= limit

    prod_qs = Product.objects.filter(is_active=True).order_by('style_code', 'code')
    if q:
        prod_qs = prod_qs.filter(
            Q(style_code__icontains=q)
            | Q(code__icontains=q)
            | Q(name__icontains=q)
            | Q(full_name__icontains=q)
            | Q(bar_code__icontains=q)
            | Q(kiotviet_code__icontains=q),
        )

    for product in prod_qs[: limit * 8]:
        style = (product.style_code or '').strip()
        if style:
            name = (product.name or product.full_name or '').strip()
            if _add(style, name, product.base_price or 0):
                return rows
        else:
            sku = (product.code or '').strip()
            name = (product.name or product.full_name or '').strip()
            if _add(sku, name, product.base_price or 0):
                return rows

    style_qs = ProductStyle.objects.filter(is_active=True).order_by('code')
    if q:
        style_qs = style_qs.filter(
            Q(code__icontains=q)
            | Q(name__icontains=q)
            | Q(root_kiotviet_code__icontains=q),
        )
    for style in style_qs[:limit]:
        if _add((style.code or '').strip(), (style.name or '').strip()):
            break

    return rows


# --- Aliases tương thích API cũ (trước đây lấy từ KiotViet) ---

find_kv_product = find_product
resolve_kv_product_ref = resolve_product_ref
search_kv_products = search_products
