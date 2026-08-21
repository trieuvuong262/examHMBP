"""Đồng bộ tồn cửa hàng từ mirror KiotViet → kho ``CH-TRUNG-TAM``.

Xưởng (XUONG-TP) không đụng: tồn xưởng phải đếm / nhập thành phẩm.
Cửa hàng vẫn đang bán trên KiotViet nên số trên Portal phải bám ``kv_product_inventory``
các chi nhánh không phải xưởng (hiện là «Chi nhánh trung tâm» + «Kho bán hàng»).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from kho_san_pham.choices import (
    DOC_TYPE_KV_ONHAND,
    SOURCE_SYSTEM_SALES,
    is_kv_sales_branch_name,
)
from kho_san_pham.models import Product, StockBalance
from kho_san_pham.services.stock import (
    StockMovementError,
    catalog_and_sales_warehouses,
    set_warehouse_qty,
)


def _qty(value) -> Decimal:
    if value is None:
        return Decimal('0')
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


@dataclass
class StoreStockSyncResult:
    branches: list[str] = field(default_factory=list)
    matched: int = 0
    unchanged: int = 0
    pending: int = 0
    applied: int = 0
    skipped_no_kv_id: int = 0
    errors: list[str] = field(default_factory=list)
    total_kv: Decimal = Decimal('0')

    def summary(self) -> str:
        names = ', '.join(self.branches) or '—'
        return (
            f'{self.applied} SKU ghi tồn cửa hàng từ KV ({names}); '
            f'{self.unchanged} khớp sổ; tổng KV {self.total_kv}'
        )


def kv_sales_branch_ids(*, retailer: str | None = None) -> list[tuple[int, str]]:
    """Chi nhánh KV được cộng vào tồn cửa hàng Portal."""
    from kiotviet.models import KvProductInventory
    from kiotviet.sync_service import current_retailer

    qs = KvProductInventory.objects.filter(is_deleted=False)
    r = retailer or current_retailer()
    if r:
        qs = qs.filter(retailer=r)
    rows = (
        qs.values('branch_kiotviet_id', 'branch_name')
        .distinct()
        .order_by('branch_kiotviet_id')
    )
    return [
        (int(row['branch_kiotviet_id']), (row['branch_name'] or '').strip())
        for row in rows
        if row['branch_kiotviet_id'] is not None
        and is_kv_sales_branch_name(row['branch_name'] or '')
    ]


def kv_store_qty_by_product(*, retailer: str | None = None) -> dict[int, Decimal]:
    """Tổng on_hand KV theo product_kiotviet_id, chỉ chi nhánh cửa hàng."""
    from kiotviet.models import KvProductInventory
    from kiotviet.sync_service import current_retailer

    branches = kv_sales_branch_ids(retailer=retailer)
    if not branches:
        return {}
    ids = [bid for bid, _name in branches]
    qs = KvProductInventory.objects.filter(
        is_deleted=False,
        branch_kiotviet_id__in=ids,
    )
    r = retailer or current_retailer()
    if r:
        qs = qs.filter(retailer=r)
    totals: dict[int, Decimal] = {}
    for row in qs.values('product_kiotviet_id').annotate(t=Sum('on_hand')):
        kid = row['product_kiotviet_id']
        if kid is None:
            continue
        totals[int(kid)] = _qty(row['t'])
    return totals


def sync_store_stock_from_kiotviet(
    *,
    apply: bool = False,
    user=None,
    retailer: str | None = None,
) -> StoreStockSyncResult:
    """Bám tồn ``CH-TRUNG-TAM`` theo tổng tồn các chi nhánh bán KV.

    Mặc định chỉ tính; ``apply=True`` mới ghi sổ (adjust từng SKU lệch).
    """
    result = StoreStockSyncResult()
    _factory, store = catalog_and_sales_warehouses()
    if store is None:
        result.errors.append('Chưa có kho bán hàng (CH-TRUNG-TAM). Chạy kho_sp_seed_warehouses --apply.')
        return result

    branches = kv_sales_branch_ids(retailer=retailer)
    result.branches = [name or str(bid) for bid, name in branches]
    if not branches:
        result.errors.append('Không thấy chi nhánh KiotViet nào thuộc cửa hàng.')
        return result

    kv_qty = kv_store_qty_by_product(retailer=retailer)
    products = list(
        Product.objects.exclude(kiotviet_id=None).only('id', 'code', 'kiotviet_id', 'qty_on_hand')
    )
    on_book = {
        pid: qty
        for pid, qty in StockBalance.objects.filter(warehouse=store).values_list(
            'product_id', 'qty_on_hand',
        )
    }

    plan: list[tuple[Product, Decimal, Decimal]] = []
    for product in products:
        target = kv_qty.get(int(product.kiotviet_id), Decimal('0'))
        current = _qty(on_book.get(product.pk, Decimal('0')))
        result.matched += 1
        result.total_kv += target
        if target == current:
            result.unchanged += 1
            continue
        plan.append((product, current, target))

    result.pending = len(plan)
    result.skipped_no_kv_id = Product.objects.filter(kiotviet_id=None).count()
    if not apply:
        return result

    now = timezone.now()
    doc_code = f'KVOH-{store.code}-{now.strftime("%Y%m%d%H%M%S")}'[:60]
    for product, current, target in plan:
        try:
            with transaction.atomic():
                posted = set_warehouse_qty(
                    product,
                    target,
                    warehouse=store,
                    user=user,
                    notes=f'Sync tồn KV cửa hàng: {current} → {target}',
                    source_system=SOURCE_SYSTEM_SALES,
                    source_doc_type=DOC_TYPE_KV_ONHAND,
                    source_doc_code=doc_code,
                    allow_negative=True,
                    actor=getattr(user, 'username', '') or 'kho_sp_sync_kv_store',
                )
        except StockMovementError as exc:
            result.errors.append(f'{product.code}: {exc}')
            continue
        if posted is not None and posted.was_applied:
            result.applied += 1
        else:
            result.unchanged += 1

    return result
