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


def _append_unique_url(urls: list[str], seen: dict[str, bool], url: str | None) -> None:
    value = (url or '').strip()
    if not value or value in seen:
        return
    seen[value] = True
    urls.append(value)


def _lookup_code_set(codes: set[str]) -> set[str]:
    return {c for code in codes for c in (code, code.upper(), code.lower()) if c}


def fill_tech_doc_display_images(docs) -> None:
    """Gắn gallery ảnh: snapshot hồ sơ + kho SP + ảnh KV (ít query)."""
    from collections import defaultdict

    docs = [d for d in docs if d is not None]
    if not docs:
        return

    galleries: dict[int, list[str]] = {}
    seen_maps: dict[int, dict[str, bool]] = {}
    for doc in docs:
        urls: list[str] = []
        seen: dict[str, bool] = {}
        for item in getattr(doc, 'gallery_images', None) or []:
            if getattr(item, 'is_image', False):
                _append_unique_url(urls, seen, getattr(item, 'file_url', None))
        _append_unique_url(urls, seen, getattr(doc, 'product_image_url', None))
        galleries[id(doc)] = urls
        seen_maps[id(doc)] = seen

    def _apply_galleries() -> None:
        for doc in docs:
            urls = galleries[id(doc)]
            doc._display_image_urls = urls
            doc._display_image_url = urls[0] if urls else ''

    try:
        from kho_san_pham.models import Product
    except ImportError:
        _apply_galleries()
        return

    codes = {(d.product_code or '').strip() for d in docs if (d.product_code or '').strip()}
    lookup = _lookup_code_set(codes)
    product_fields = ('code', 'style_code', 'kiotviet_code', 'kiotviet_id', 'image', 'image_url')
    products = []
    if lookup:
        products = list(
            Product.objects.filter(
                Q(style_code__in=lookup) | Q(code__in=lookup) | Q(kiotviet_code__in=lookup)
            ).only(*product_fields)
        )

    extra_styles = {
        (p.style_code or '').strip()
        for p in products
        if (p.style_code or '').strip()
        and (p.style_code or '').strip() not in lookup
        and (p.style_code or '').upper() not in lookup
    }
    if extra_styles:
        extra_lookup = _lookup_code_set(extra_styles)
        seen_pks = {p.pk for p in products}
        products.extend(
            p for p in Product.objects.filter(style_code__in=extra_lookup).only(*product_fields)
            if p.pk not in seen_pks
        )

    by_style: dict[str, list] = defaultdict(list)
    by_code: dict[str, list] = defaultdict(list)
    by_kv_code: dict[str, list] = defaultdict(list)
    kv_ids: set[int] = {
        d.kv_product_id for d in docs if getattr(d, 'kv_product_id', None)
    }
    for product in products:
        style = (product.style_code or '').strip()
        sku = (product.code or '').strip()
        kv_code = (product.kiotviet_code or '').strip()
        if style:
            by_style[style.casefold()].append(product)
        if sku:
            by_code[sku.casefold()].append(product)
        if kv_code:
            by_kv_code[kv_code.casefold()].append(product)
        if product.kiotviet_id:
            kv_ids.add(product.kiotviet_id)

    kv_images_by_id: dict[int, list[str]] = {}
    if kv_ids:
        try:
            from kiotviet.models import KvProduct
        except ImportError:
            KvProduct = None
        if KvProduct is not None:
            for row in KvProduct.objects.filter(
                kiotviet_id__in=kv_ids, is_deleted=False,
            ).only('kiotviet_id', 'image_urls'):
                bucket = kv_images_by_id.setdefault(row.kiotviet_id, [])
                seen_kv: dict[str, bool] = {u: True for u in bucket}
                for url in row.image_urls or []:
                    _append_unique_url(bucket, seen_kv, url)

    for doc in docs:
        key = (doc.product_code or '').strip().casefold()
        urls = galleries[id(doc)]
        seen = seen_maps[id(doc)]
        matched = list(by_style.get(key) or [])
        if not matched:
            matched = list(by_code.get(key) or by_kv_code.get(key) or [])
            styles = {
                (p.style_code or '').strip().casefold()
                for p in matched
                if (p.style_code or '').strip()
            }
            for style_key in styles:
                for product in by_style.get(style_key, []):
                    if product not in matched:
                        matched.append(product)
        for product in matched:
            _append_unique_url(urls, seen, product.display_image_url)
            if product.kiotviet_id:
                for url in kv_images_by_id.get(product.kiotviet_id, []):
                    _append_unique_url(urls, seen, url)
        if getattr(doc, 'kv_product_id', None):
            for url in kv_images_by_id.get(doc.kv_product_id, []):
                _append_unique_url(urls, seen, url)

    _apply_galleries()


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


def product_lookup_codes(product_code: str) -> list[str]:
    """Mã cùng một hàng (mã SX / SKU / KV) để khớp hồ sơ, BOM, OB."""
    code = _norm(product_code)
    out: list[str] = []
    seen: set[str] = set()

    def add(raw) -> None:
        value = _norm(raw)
        key = value.casefold()
        if not value or key in seen:
            return
        seen.add(key)
        out.append(value)

    add(code)
    ref = resolve_product_ref(code)
    if ref:
        add(ref.code)
    product = find_product(code)
    if product:
        add(getattr(product, 'style_code', None))
        add(getattr(product, 'code', None))
        add(getattr(product, 'kiotviet_code', None))
        add(product_sx_code(product))
        style = _norm(getattr(product, 'style_code', None))
        if style:
            try:
                from kho_san_pham.models import Product

                for sku in Product.objects.filter(style_code__iexact=style).values_list(
                    'code', 'kiotviet_code',
                )[:80]:
                    add(sku[0])
                    add(sku[1])
            except Exception:
                pass
    return out


def find_tech_doc_for_code(product_code: str):
    """Tìm hồ sơ SX theo mã nhập (style / SKU / mã KV)."""
    from san_xuat.models import ProductTechDoc

    for code in product_lookup_codes(product_code):
        doc = ProductTechDoc.objects.filter(product_code__iexact=code).first()
        if doc:
            return doc
    return find_tech_doc_for_product(find_product(product_code))


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


def suggest_style_size_stock(style_code: str, *, days: int = 30) -> dict:
    """Tồn TP + tốc độ tiêu thụ (bán KV) theo size cho 1 Style.

    ``days``: số ngày gần nhất lấy từ hóa đơn KiotViet (mặc định 30).
    """
    from collections import defaultdict
    from datetime import timedelta

    from django.db.models import Q, Sum
    from django.db.models.functions import Upper
    from django.utils import timezone

    from san_xuat.services.demand import fg_stock_map

    style = _norm(style_code)
    try:
        days_n = max(1, min(int(days or 30), 365))
    except (TypeError, ValueError):
        days_n = 30

    empty = {
        'style_code': style,
        'name': '',
        'days': days_n,
        'sizes': [],
        'colors': [],
        'found': False,
        'sold_from': '',
        'sold_to': '',
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
    sold_by_size: dict[str, Decimal] = defaultdict(lambda: Decimal('0'))
    sku_count: dict[str, int] = defaultdict(int)
    colors: dict[str, str] = {}
    _size_alias = {
        'XXL': '2XL', '2XL': '2XL',
        'XXXL': '3XL', '3XL': '3XL',
    }
    code_to_size: dict[str, str] = {}
    kid_to_size: dict[int, str] = {}

    for p in products:
        size = (p.size_label or '').strip().upper() or '—'
        size = _size_alias.get(size, size)
        by_size[size] += _qty_for(p)
        sku_count[size] += 1
        color = (p.color_code or '').strip().upper()
        if color and color not in colors:
            colors[color] = (p.color_label or color).strip() or color
        for raw in (p.code, p.kiotviet_code):
            c = _norm(raw)
            if c:
                code_to_size[c.upper()] = size
        if p.kiotviet_id:
            kid_to_size[int(p.kiotviet_id)] = size

    # —— Tốc độ tiêu thụ = tổng SL bán KV trong N ngày ——
    now = timezone.now()
    since = now - timedelta(days=days_n)
    sold_from = since.date().isoformat()
    sold_to = now.date().isoformat()
    try:
        from kiotviet.models import KvInvoice, KvInvoiceLine
        from kiotviet.sync_service import current_retailer

        retailer = current_retailer()
        invoice_ids = (
            KvInvoice.objects.filter(
                retailer=retailer,
                purchase_date__gte=since,
            )
            .exclude(status=2)  # 2 = đã hủy (KV)
            .values('kiotviet_id')
        )
        line_q = Q()
        if kid_to_size:
            line_q |= Q(product_kiotviet_id__in=list(kid_to_size.keys()))
        if code_to_size:
            line_q |= Q(code_u__in=list(code_to_size.keys()))
        if line_q:
            rows = (
                KvInvoiceLine.objects.filter(
                    retailer=retailer,
                    invoice_kiotviet_id__in=invoice_ids,
                )
                .annotate(code_u=Upper('product_code'))
                .filter(line_q)
                .values('product_kiotviet_id', 'code_u')
                .annotate(qty=Sum('quantity'))
            )
            for row in rows:
                size = ''
                kid = row.get('product_kiotviet_id')
                if kid is not None:
                    size = kid_to_size.get(int(kid), '')
                if not size:
                    size = code_to_size.get((row.get('code_u') or '').upper(), '')
                if not size:
                    continue
                sold_by_size[size] += Decimal(str(row.get('qty') or 0))
    except Exception:
        # Không có KV / lỗi sync — để velocity = 0
        pass

    ordered = sorted(set(by_size.keys()) | set(sold_by_size.keys()), key=_size_sort_key)
    sizes = []
    for sz in ordered:
        qty = by_size.get(sz, Decimal('0'))
        sold = sold_by_size.get(sz, Decimal('0'))
        if sold < 0:
            sold = Decimal('0')
        if qty == qty.to_integral_value():
            stock_label = str(int(qty))
        else:
            stock_label = format(qty.quantize(Decimal('0.01')), 'f').rstrip('0').rstrip('.')
        if sold == sold.to_integral_value():
            sold_label = str(int(sold))
        else:
            sold_label = format(sold.quantize(Decimal('0.01')), 'f').rstrip('0').rstrip('.')
        sizes.append({
            'size': sz,
            'stock': stock_label or '0',
            'stock_qty': float(qty),
            'velocity': sold_label or '0',
            'velocity_qty': float(sold),
            'sku_count': sku_count.get(sz, 0),
        })
    return {
        'style_code': style_canon,
        'name': name,
        'days': days_n,
        'sizes': sizes,
        'colors': [{'code': c, 'label': colors[c]} for c in colors],
        'found': True,
        'sold_from': sold_from,
        'sold_to': sold_to,
    }


def search_gc_out_items(q: str = '', *, limit: int = 40) -> list[dict]:
    """TomSelect dòng xuất GC: NPL (kho NPL) + BTP/SP (kho SP)."""
    q = _norm(q)
    limit = max(1, min(int(limit or 40), 80))
    rows: list[dict] = []
    npl_cap = min(40, limit)

    try:
        from django.db.models import Sum

        from kho_npl.catalog_labels import unit_label
        from kho_npl.material_search import apply_material_search_strict, material_relevance_sort_key
        from kho_npl.models import Material, StockBalance
        from kho_npl.services.scrap_warehouse import exclude_scrap_locations
        from kho_npl.templatetags.npl_extras import format_npl_qty

        qs = Material.objects.filter(is_active=True).select_related('unit')
        if q:
            qs = apply_material_search_strict(qs, q)
        materials = list(qs.order_by('name', 'code')[:npl_cap])
        if q:
            materials.sort(key=lambda m: material_relevance_sort_key(m, q))
        balance_map: dict[int, Decimal] = {}
        if materials:
            for row in (
                exclude_scrap_locations(
                    StockBalance.objects.filter(material_id__in=[m.pk for m in materials]),
                )
                .values('material_id')
                .annotate(total=Sum('quantity'))
            ):
                balance_map[row['material_id']] = row['total'] or Decimal('0')
        for material in materials:
            qty = balance_map.get(material.pk, Decimal('0'))
            unit = unit_label(material.unit) if material.unit_id else ''
            qty_text = format_npl_qty(qty)
            stock_label = f'{qty_text} {unit}'.strip() if unit else (qty_text or '0')
            rows.append({
                'id': f'npl:{material.pk}',
                'code': material.code,
                'name': material.name,
                'text': f'{material.code} — {material.name}',
                'kind': 'npl',
                'kind_label': 'NPL',
                'unit': unit or 'cái',
                'unit_name': (material.unit.name if material.unit_id else '') or 'cái',
                'stock_qty': str(qty),
                'stock_label': stock_label or '0',
            })
    except Exception:
        pass

    for product in search_products(q, limit=min(20, limit)):
        rows.append({
            'id': f'sp:{product["id"]}',
            'code': product.get('code') or product['id'],
            'name': product.get('name') or '',
            'text': product.get('text') or product.get('code') or product['id'],
            'kind': 'sp',
            'kind_label': 'BTP/SP',
            'unit': 'cái',
            'unit_name': 'cái',
            'stock_qty': product.get('stock_qty') or '0',
            'stock_label': product.get('stock_label') or '0',
        })
    return rows


def resolve_gc_out_item(raw: str) -> tuple[str, str, str]:
    """(code, name, uom) từ giá trị TomSelect NPL/BTP."""
    value = _norm(raw)
    if not value:
        return '', '', ''

    if value.lower().startswith('npl:'):
        try:
            pk = int(value.split(':', 1)[1])
        except (TypeError, ValueError):
            raise ValueError('Mã NPL không hợp lệ.') from None
        from kho_npl.catalog_labels import unit_label
        from kho_npl.models import Material

        material = Material.objects.filter(pk=pk, is_active=True).select_related('unit').first()
        if not material:
            raise ValueError('NPL không có trong danh mục.')
        unit = unit_label(material.unit) if material.unit_id else 'cái'
        return material.code, material.name, unit or 'cái'

    if value.lower().startswith('sp:'):
        code = value.split(':', 1)[1].strip()
        ref = resolve_product_ref(code)
        if not ref:
            raise ValueError(f'Mã {code} không có trong kho sản phẩm.')
        return ref.code, ref.name, 'cái'

    from kho_npl.catalog_labels import unit_label
    from kho_npl.models import Material

    material = Material.objects.filter(code__iexact=value, is_active=True).select_related('unit').first()
    if material:
        unit = unit_label(material.unit) if material.unit_id else 'cái'
        return material.code, material.name, unit or 'cái'
    ref = resolve_product_ref(value)
    if ref:
        return ref.code, ref.name, 'cái'
    raise ValueError(f'Không tìm thấy NPL / BTP {value}.')


# --- Aliases tương thích API cũ (trước đây lấy từ KiotViet) ---

find_kv_product = find_product
resolve_kv_product_ref = resolve_product_ref
search_kv_products = search_products
