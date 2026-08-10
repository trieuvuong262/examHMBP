"""Resolve mã SX / sản phẩm từ kho sản phẩm cho hồ sơ SX & LSX."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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


def product_sx_code(product) -> str:
    """Mã SX chuẩn dùng cho hồ sơ / LSX (ưu tiên style_code)."""
    if product is None:
        return ''
    ref = resolve_product_ref(
        (getattr(product, 'style_code', None) or getattr(product, 'code', None) or '')
    )
    if ref:
        return ref.code
    return _norm(getattr(product, 'style_code', None) or getattr(product, 'code', None) or '')


def find_tech_doc_for_product(product):
    """Tìm ProductTechDoc gắn với sản phẩm kho SP (style / SKU / mã KV)."""
    if product is None:
        return None
    from san_xuat.models import ProductTechDoc

    seen: set[str] = set()
    candidates: list[str] = []
    for raw in (
        product_sx_code(product),
        getattr(product, 'style_code', None),
        getattr(product, 'code', None),
        getattr(product, 'kiotviet_code', None),
    ):
        code = _norm(raw)
        key = code.casefold()
        if not code or key in seen:
            continue
        seen.add(key)
        candidates.append(code)

    for code in candidates:
        doc = ProductTechDoc.objects.filter(product_code__iexact=code).first()
        if doc:
            return doc
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
                break
        else:
            sku = (product.code or '').strip()
            name = (product.name or product.full_name or '').strip()
            if _add(sku, name, product.base_price or 0):
                break

    if len(rows) < limit:
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

    # Tồn TP khả dụng (KV) — tham khảo trên form ĐĐH / TomSelect
    try:
        from san_xuat.services.demand import fg_stock_map

        stock = fg_stock_map([r['code'] for r in rows])
        for r in rows:
            qty = stock.get(r['code'], None)
            if qty is None:
                qty = next(
                    (v for k, v in stock.items() if k.casefold() == r['code'].casefold()),
                    Decimal('0'),
                )
            qty = Decimal(str(qty or 0))
            r['stock_qty'] = str(qty)
            text = format(qty, 'f').rstrip('0').rstrip('.')
            r['stock_label'] = text or '0'
    except Exception:
        for r in rows:
            r['stock_qty'] = '0'
            r['stock_label'] = '0'

    return rows


def suggest_style_size_stock(style_code: str) -> dict:
    """Tồn TP theo size cho 1 Style (mã SX) — lấy từ kho sản phẩm + KV.

    Trả về:
      style_code, name, sizes: [{size, stock, sku_count}], colors (tuỳ chọn)
    """
    from collections import defaultdict

    from san_xuat.services.demand import fg_stock_map

    style = _norm(style_code)
    empty = {
        'style_code': style,
        'name': '',
        'sizes': [],
        'colors': [],
        'found': False,
    }
    if not style:
        return empty

    try:
        from kho_san_pham.models import Product
        from kho_san_pham.services.sync_from_kiotviet import _size_sort_key
    except ImportError:
        return empty

    products = list(
        Product.objects.filter(is_active=True)
        .filter(
            Q(style_code__iexact=style)
            | Q(code__iexact=style)
            | Q(kiotviet_code__iexact=style),
        )
        .order_by('color_code', 'size_label', 'code')
    )
    if not products:
        ref = resolve_product_ref(style)
        if ref:
            empty['style_code'] = ref.code
            empty['name'] = ref.name
        return empty

    # Chuẩn hoá về style_code đại diện
    style_canon = (products[0].style_code or '').strip() or style
    name = (products[0].name or products[0].full_name or '').strip()
    for p in products:
        sc = (p.style_code or '').strip()
        if sc:
            style_canon = sc
            name = (p.name or p.full_name or name or '').strip()
            break

    lookup_codes: list[str] = []
    for p in products:
        for raw in (p.code, p.kiotviet_code):
            c = _norm(raw)
            if c:
                lookup_codes.append(c)
    stock_by_code = fg_stock_map(lookup_codes)

    def _qty_for(product) -> Decimal:
        for raw in (product.code, product.kiotviet_code):
            c = _norm(raw)
            if not c:
                continue
            if c in stock_by_code:
                return Decimal(str(stock_by_code[c] or 0))
            hit = next(
                (v for k, v in stock_by_code.items() if k.casefold() == c.casefold()),
                None,
            )
            if hit is not None:
                return Decimal(str(hit or 0))
        return Decimal('0')

    by_size: dict[str, Decimal] = defaultdict(lambda: Decimal('0'))
    sku_count: dict[str, int] = defaultdict(int)
    colors: dict[str, str] = {}
    for p in products:
        size = (p.size_label or '').strip().upper()
        if not size:
            # Không có size → gộp vào cột «—» / dùng mã SKU ngắn
            size = '—'
        by_size[size] += _qty_for(p)
        sku_count[size] += 1
        color = (p.color_code or '').strip().upper()
        if color and color not in colors:
            colors[color] = (p.color_label or color).strip() or color

    ordered = sorted(by_size.keys(), key=_size_sort_key)
    sizes = []
    for sz in ordered:
        qty = by_size[sz]
        if qty == qty.to_integral_value():
            stock_label = str(int(qty))
        else:
            stock_label = format(qty.quantize(Decimal('0.01')), 'f').rstrip('0').rstrip('.')
        sizes.append({
            'size': sz,
            'stock': stock_label or '0',
            'stock_qty': float(qty),
            'sku_count': sku_count[sz],
        })
    return {
        'style_code': style_canon,
        'name': name,
        'sizes': sizes,
        'colors': [{'code': c, 'label': colors[c]} for c in colors],
        'found': True,
    }


# --- Aliases tương thích API cũ (trước đây lấy từ KiotViet) ---

find_kv_product = find_product
resolve_kv_product_ref = resolve_product_ref
search_kv_products = search_products
