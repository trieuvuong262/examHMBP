"""Nhu cầu sản xuất — netting tồn thành phẩm và hàng đang sản xuất.

Dùng chung cho 3 phương án lập kế hoạch:
  * MTO — nhu cầu từ đơn đặt hàng KiotViet
  * MTS — nhu cầu bù tồn theo chính sách tồn thành phẩm
  * MPS — nhu cầu nhập tay / gộp, chia theo kỳ lịch trình

Công thức chung:
    nhu cầu thực = nhu cầu gộp − tồn TP khả dụng − SL đang sản xuất
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from san_xuat.hub_models import SxProductionOrder, SxProductStockPolicy

_Q = Decimal('0.01')


def _q(value) -> Decimal:
    return (Decimal(str(value or 0))).quantize(_Q)


# ---------------------------------------------------------------------------
# Tồn thành phẩm (mirror KiotViet)
# ---------------------------------------------------------------------------

def fg_stock_map(product_codes: list[str]) -> dict[str, Decimal]:
    """Tồn thành phẩm khả dụng theo mã SP (on_hand − reserved), gộp mọi chi nhánh."""
    codes = [c.strip() for c in (product_codes or []) if (c or '').strip()]
    if not codes:
        return {}
    try:
        from kiotviet.models import KvProduct, KvProductInventory
        from kiotviet.sync_service import current_retailer
    except Exception:
        return {}

    retailer = current_retailer()
    upper = {c.upper(): c for c in codes}
    products = list(
        KvProduct.objects.filter(retailer=retailer, code__in=list(upper.keys()) + codes)
        .values_list('kiotviet_id', 'code')
    )
    if not products:
        return {}
    id_to_code: dict[int, str] = {}
    for kid, code in products:
        key = (code or '').strip().upper()
        if key in upper:
            id_to_code[int(kid)] = upper[key]

    if not id_to_code:
        return {}

    rows = (
        KvProductInventory.objects.filter(
            retailer=retailer, product_kiotviet_id__in=list(id_to_code.keys()),
        )
        .values('product_kiotviet_id')
        .annotate(on_hand_total=Sum('on_hand'), reserved_total=Sum('reserved'))
    )
    out: dict[str, Decimal] = {}
    for row in rows:
        code = id_to_code.get(int(row['product_kiotviet_id']))
        if not code:
            continue
        avail = _q(row['on_hand_total']) - _q(row['reserved_total'])
        if avail < 0:
            avail = Decimal('0')
        out[code] = out.get(code, Decimal('0')) + avail
    return out


def fg_available_qty(product_code: str) -> Decimal:
    return fg_stock_map([product_code]).get((product_code or '').strip(), Decimal('0'))


# ---------------------------------------------------------------------------
# Hàng đang sản xuất (WIP trên lệnh chưa xong)
# ---------------------------------------------------------------------------

_OPEN_MO_STATUSES = (
    SxProductionOrder.STATUS_DRAFT,
    SxProductionOrder.STATUS_RELEASED,
    SxProductionOrder.STATUS_IN_PROGRESS,
)


def wip_qty_map(product_codes: list[str]) -> dict[str, Decimal]:
    """SL còn phải làm trên các LSX chưa hoàn thành, theo mã SP."""
    codes = {(c or '').strip().upper() for c in (product_codes or []) if (c or '').strip()}
    if not codes:
        return {}
    out: dict[str, Decimal] = {}
    rows = SxProductionOrder.objects.filter(
        is_demo=False, status__in=_OPEN_MO_STATUSES,
    ).values_list('product_code', 'qty', 'qty_done')
    for code, qty, qty_done in rows:
        key = (code or '').strip().upper()
        if key not in codes:
            continue
        remaining = _q(qty) - _q(qty_done)
        if remaining > 0:
            out[key] = out.get(key, Decimal('0')) + remaining
    return out


# ---------------------------------------------------------------------------
# Netting
# ---------------------------------------------------------------------------

@dataclass
class DemandItem:
    """Một dòng nhu cầu sau khi netting."""

    product_code: str
    product_name: str = ''
    qty_gross: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_on_hand: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_wip: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_net: Decimal = field(default_factory=lambda: Decimal('0'))
    due_date: date | None = None
    kv_order_code: str = ''
    kv_order_kiotviet_id: int | None = None
    sales_order_id: int | None = None
    note: str = ''

    @property
    def is_covered(self) -> bool:
        """Nhu cầu đã được tồn kho / hàng đang SX phủ hết."""
        return self.qty_net <= 0


def apply_netting(items: list[DemandItem], *, enabled: bool = True) -> list[DemandItem]:
    """Trừ tồn TP khả dụng + WIP khỏi nhu cầu gộp.

    Tồn và WIP được phân bổ theo thứ tự hạn giao (đơn gấp trước), nên mỗi mã SP
    chỉ được trừ một lần dù xuất hiện ở nhiều dòng.
    """
    if not items:
        return []
    if not enabled:
        for item in items:
            item.qty_on_hand = Decimal('0')
            item.qty_wip = Decimal('0')
            item.qty_net = _q(item.qty_gross)
        return items

    codes = [it.product_code for it in items]
    stock = fg_stock_map(codes)
    wip = wip_qty_map(codes)

    # Ưu tiên trừ cho dòng có hạn giao sớm nhất
    ordered = sorted(
        items,
        key=lambda it: (it.due_date is None, it.due_date or date.max, it.product_code),
    )
    remaining_stock = {k.strip().upper(): v for k, v in stock.items()}
    remaining_wip = dict(wip)

    for item in ordered:
        key = (item.product_code or '').strip().upper()
        gross = _q(item.qty_gross)

        avail = remaining_stock.get(key, Decimal('0'))
        use_stock = min(gross, avail) if avail > 0 else Decimal('0')
        remaining_stock[key] = avail - use_stock

        left = gross - use_stock
        on_wip = remaining_wip.get(key, Decimal('0'))
        use_wip = min(left, on_wip) if on_wip > 0 else Decimal('0')
        remaining_wip[key] = on_wip - use_wip

        item.qty_on_hand = _q(use_stock)
        item.qty_wip = _q(use_wip)
        item.qty_net = _q(max(Decimal('0'), left - use_wip))
    return items


def merge_by_product(items: list[DemandItem]) -> list[DemandItem]:
    """Gộp nhiều dòng cùng mã SP thành một dòng (giữ hạn giao sớm nhất)."""
    bucket: dict[str, DemandItem] = {}
    for item in items:
        key = (item.product_code or '').strip().upper()
        if not key:
            continue
        cur = bucket.get(key)
        if cur is None:
            bucket[key] = DemandItem(
                product_code=item.product_code.strip(),
                product_name=item.product_name,
                qty_gross=_q(item.qty_gross),
                due_date=item.due_date,
                kv_order_code=item.kv_order_code,
                kv_order_kiotviet_id=item.kv_order_kiotviet_id,
                sales_order_id=item.sales_order_id,
                note=item.note,
            )
            continue
        cur.qty_gross = _q(cur.qty_gross + item.qty_gross)
        if item.due_date and (cur.due_date is None or item.due_date < cur.due_date):
            cur.due_date = item.due_date
        if item.kv_order_code and item.kv_order_code not in cur.kv_order_code:
            joined = f'{cur.kv_order_code}, {item.kv_order_code}'.strip(', ')
            cur.kv_order_code = joined[:64]
        if cur.sales_order_id and item.sales_order_id and cur.sales_order_id != item.sales_order_id:
            cur.sales_order_id = None
        elif not cur.sales_order_id and item.sales_order_id:
            cur.sales_order_id = item.sales_order_id
    return sorted(bucket.values(), key=lambda it: it.product_code)


# ---------------------------------------------------------------------------
# MTS — đề xuất sản xuất bù tồn
# ---------------------------------------------------------------------------

@dataclass
class RestockSuggestion:
    policy: SxProductStockPolicy
    qty_on_hand: Decimal
    qty_wip: Decimal
    qty_suggest: Decimal

    @property
    def coverage(self) -> Decimal:
        return _q(self.qty_on_hand + self.qty_wip)

    @property
    def needs_restock(self) -> bool:
        return self.qty_suggest > 0

    @property
    def is_zero_stock(self) -> bool:
        return self.qty_on_hand <= 0


def build_restock_suggestions(*, include_covered: bool = False) -> list[RestockSuggestion]:
    """Danh sách SP có tồn (kể cả hàng đang SX) dưới mức tối thiểu.

    SL đề xuất = tồn mục tiêu − tồn khả dụng − SL đang sản xuất.
    """
    return build_mts_stock_board(include_covered=include_covered, only_policies=True)


def build_mts_stock_board(
    *,
    include_covered: bool = True,
    only_policies: bool = False,
    search: str = '',
    stock_filter: str = 'all',
    sort: str = 'on_hand',
) -> list[RestockSuggestion]:
    """Bảng tồn TP cho MTS.

    Nguồn mã (khi ``only_policies=False``):
      1. Chính sách tồn đang active
      2. Hồ sơ thiết kế active chưa có chính sách
      3. Kho sản phẩm (``kho_san_pham.Product`` active) — theo mã Style
         (hoặc SKU nếu chưa có Style), chưa có ở (1)/(2)

    ``stock_filter``: all | zero | need | ok
    ``sort``: on_hand | -on_hand | code | -code | suggest | -suggest
    """
    policies = {
        (p.product_code or '').strip().upper(): p
        for p in SxProductStockPolicy.objects.filter(is_active=True, is_demo=False)
    }
    entries: list[SxProductStockPolicy] = list(policies.values())
    seen: set[str] = set(policies.keys())

    def _add_virtual(code: str, name: str = '') -> None:
        key = (code or '').strip().upper()
        if not key or key in seen:
            return
        seen.add(key)
        entries.append(
            SxProductStockPolicy(
                product_code=(code or '').strip(),
                product_name=(name or '').strip(),
                min_stock=Decimal('0'),
                max_stock=Decimal('0'),
                lead_time_days=0,
                is_active=True,
            )
        )

    if not only_policies:
        from san_xuat.models import ProductTechDoc

        for doc in ProductTechDoc.objects.filter(is_active=True).order_by('product_code'):
            _add_virtual(doc.product_code, doc.product_name or '')

        try:
            from kho_san_pham.models import Product
        except ImportError:
            Product = None  # type: ignore[misc, assignment]

        if Product is not None:
            # Một dòng / Style (mã SX); fallback SKU khi chưa gắn Style.
            prod_qs = (
                Product.objects.filter(is_active=True)
                .order_by('style_code', 'code')
                .values_list('style_code', 'code', 'name', 'full_name')
            )
            for style_code, sku, name, full_name in prod_qs.iterator(chunk_size=1000):
                code = (style_code or '').strip() or (sku or '').strip()
                label = (name or full_name or '').strip()
                _add_virtual(code, label)

    if not entries:
        return []

    codes = [p.product_code for p in entries]
    stock = {k.strip().upper(): v for k, v in fg_stock_map(codes).items()}
    wip = wip_qty_map(codes)

    out: list[RestockSuggestion] = []
    for policy in entries:
        key = (policy.product_code or '').strip().upper()
        on_hand = stock.get(key, Decimal('0'))
        on_wip = wip.get(key, Decimal('0'))
        coverage = on_hand + on_wip
        min_stock = policy.min_stock or Decimal('0')
        suggest = Decimal('0')
        if coverage < min_stock:
            suggest = _q(max(Decimal('0'), policy.target_stock - coverage))
        # Hết tồn, chưa khai chính sách: đề xuất mặc định 1 để chọn nạp KHTT
        if suggest <= 0 and on_hand <= 0 and not getattr(policy, 'pk', None):
            suggest = Decimal('1')
        if suggest <= 0 and not include_covered:
            continue
        out.append(
            RestockSuggestion(
                policy=policy,
                qty_on_hand=_q(on_hand),
                qty_wip=_q(on_wip),
                qty_suggest=suggest,
            )
        )

    term = (search or '').strip().lower()
    if term:
        out = [
            r for r in out
            if term in (r.policy.product_code or '').lower()
            or term in (r.policy.product_name or '').lower()
        ]

    filt = (stock_filter or 'all').strip().lower()
    if filt == 'zero':
        out = [r for r in out if r.is_zero_stock]
    elif filt == 'need':
        out = [r for r in out if r.needs_restock]
    elif filt == 'ok':
        out = [r for r in out if not r.needs_restock and not r.is_zero_stock]

    reverse = sort.startswith('-')
    key = (sort[1:] if reverse else sort) or 'on_hand'
    if key == 'code':
        out.sort(key=lambda r: (r.policy.product_code or '').upper(), reverse=reverse)
    elif key == 'suggest':
        out.sort(key=lambda r: (r.qty_suggest, (r.policy.product_code or '').upper()), reverse=reverse)
    else:
        # on_hand: mặc định tồn thấp → cao (hết tồn lên đầu)
        out.sort(
            key=lambda r: (r.qty_on_hand, (r.policy.product_code or '').upper()),
            reverse=reverse,
        )
    return out
