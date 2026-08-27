"""Ghi tăng tồn thành phẩm khi nhập kho từ YCNTP.

Tạo phiếu ``StockReceipt`` (menu Kho SP) rồi ghi sổ — cùng transaction với
cập nhật trạng thái YCNTP (done / còn hàng chưa nhập).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from kho_san_pham.choices import (
    DOC_TYPE_STOCK_RECEIPT,
    MOVEMENT_PRODUCTION_IN,
    SOURCE_SYSTEM_PORTAL,
    WAREHOUSE_OWNER_PORTAL,
)
from kho_san_pham.models import Product, StockReceipt, StockReceiptLine, Warehouse
from kho_san_pham.services.stock import RESULT_APPLIED, StockMovementError, post_movement


class FgStockError(Exception):
    """Không ghi được tồn — chặn việc hoàn thành phiếu."""


@dataclass
class FgStockResult:
    posted: int = 0
    already: int = 0
    missing_cost: int = 0
    stock_receipt: StockReceipt | None = None
    lines: list = field(default_factory=list)


def resolve_product_for_line(line) -> Product:
    if line.sku_id:
        matches = list(Product.objects.filter(sx_sku_id=line.sku_id)[:2])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise FgStockError(
                f'SKU sản xuất {line.sku_code or line.sku_id} đang trỏ tới nhiều sản phẩm '
                'trong kho sản phẩm — phải gộp trước khi nhập kho.'
            )

    code = (line.sku_code or '').strip().upper()
    if not code:
        raise FgStockError(
            f'Dòng nhập thành phẩm #{line.pk} không có SKU — không biết ghi tăng tồn cho mã nào.'
        )

    product = Product.objects.filter(code=code).first()
    if product is None:
        raise FgStockError(
            f'SKU {code} không có trong kho sản phẩm. Tạo SKU trong danh mục trước khi nhập kho.'
        )
    return product


def resolve_fg_warehouse(receipt, *, line=None) -> Warehouse:
    if line is not None and getattr(line, 'warehouse_id', None):
        return line.warehouse

    if receipt.warehouse_id:
        return receipt.warehouse

    portal_warehouses = list(
        Warehouse.objects.filter(is_active=True, owner_system=WAREHOUSE_OWNER_PORTAL)[:2]
    )
    if len(portal_warehouses) == 1:
        return portal_warehouses[0]
    if not portal_warehouses:
        raise FgStockError(
            'Chưa có kho thành phẩm nào. Chạy "manage.py kho_sp_seed_warehouses --apply" trước.'
        )
    raise FgStockError(
        f'Phiếu {receipt.code} chưa chọn kho nhập mà hệ có nhiều kho thành phẩm — phải chọn rõ kho.'
    )


def resolve_unit_cost(receipt) -> Decimal | None:
    mo = receipt.production_order
    product_code = (getattr(mo, 'product_code', '') or '').strip()
    if not product_code:
        return None

    from san_xuat.services.plan_costing import resolve_unit_standard_cost

    try:
        cost = resolve_unit_standard_cost(product_code)
    except Exception:
        return None
    if cost is None or cost <= 0:
        return None
    return Decimal(cost).quantize(Decimal('0.01'))


def next_stock_receipt_number() -> str:
    year = timezone.localdate().year
    prefix = f'PN-TP-{year}-'
    last = (
        StockReceipt.objects.filter(number__startswith=prefix)
        .aggregate(m=Max('number'))
        .get('m')
    )
    seq = 1
    if last:
        try:
            seq = int(str(last).rsplit('-', 1)[-1]) + 1
        except ValueError:
            seq = StockReceipt.objects.filter(number__startswith=prefix).count() + 1
    return f'{prefix}{seq:04d}'


def _occurred_at(receipt):
    if receipt.request_date is None:
        return timezone.now()
    naive = datetime.combine(receipt.request_date, time.min)
    return timezone.make_aware(naive) if settings.USE_TZ else naive


@transaction.atomic
def post_fg_receipt_to_stock(receipt, *, user=None, only_unposted: bool = True) -> FgStockResult:
    """Tạo phiếu nhập kho SP + ghi tăng tồn cho dòng YCNTP chưa gắn phiếu nhập."""
    from san_xuat.hub_models import SxFgReceiptRequest

    if receipt.status not in (
        SxFgReceiptRequest.STATUS_DONE,
        SxFgReceiptRequest.STATUS_PARTIAL,
        SxFgReceiptRequest.STATUS_SUBMITTED,
        SxFgReceiptRequest.STATUS_DRAFT,
    ):
        raise FgStockError(
            f'Không ghi tồn khi phiếu {receipt.code} ở trạng thái {receipt.status}.'
        )

    unit_cost = resolve_unit_cost(receipt)
    qs = receipt.lines.select_related('warehouse').all()
    if only_unposted:
        qs = qs.filter(stock_receipt__isnull=True)
    lines = [ln for ln in qs if (ln.qty or Decimal('0')) > 0]
    if not lines:
        raise FgStockError(
            f'Phiếu {receipt.code} không có dòng SKU mới để nhập kho.'
        )

    # Gom theo kho — mỗi kho một phiếu nhập.
    by_wh: dict[int, list] = {}
    for line in lines:
        wh = resolve_fg_warehouse(receipt, line=line)
        by_wh.setdefault(wh.pk, []).append((line, wh))

    result = FgStockResult()
    actor = getattr(user, 'username', '') or ''
    mo = receipt.production_order
    primary_receipt = None

    for _wh_id, group in by_wh.items():
        warehouse = group[0][1]
        doc = StockReceipt.objects.create(
            number=next_stock_receipt_number(),
            receipt_date=receipt.request_date or timezone.localdate(),
            warehouse=warehouse,
            status='posted',
            production_order_code=(mo.code if mo else '') or '',
            product_code=(mo.product_code if mo else '') or '',
            fg_receipt=receipt,
            notes=f'Nhập từ {receipt.code}',
            created_by=user if getattr(user, 'pk', None) else None,
            posted_at=timezone.now(),
        )
        if primary_receipt is None:
            primary_receipt = doc

        for line, _wh in group:
            product = resolve_product_for_line(line)
            qty = Decimal(line.qty).quantize(Decimal('0.01'))
            StockReceiptLine.objects.create(
                receipt=doc,
                product=product,
                quantity=qty,
                unit_cost=unit_cost,
                size_label=(line.size_label or '').strip(),
                color_label=(line.color_label or '').strip(),
                notes=f'{receipt.code} #{line.pk}',
            )
            try:
                movement = post_movement(
                    product=product,
                    warehouse=warehouse,
                    kind=MOVEMENT_PRODUCTION_IN,
                    qty_delta=qty,
                    unit_cost=unit_cost,
                    source_system=SOURCE_SYSTEM_PORTAL,
                    source_doc_type=DOC_TYPE_STOCK_RECEIPT,
                    source_doc_code=doc.number,
                    source_line_no=line.pk,
                    occurred_at=_occurred_at(receipt),
                    created_by=user if getattr(user, 'pk', None) else None,
                    actor=actor,
                    notes=f'Nhập thành phẩm {receipt.code} → {doc.number}',
                )
            except StockMovementError as exc:
                raise FgStockError(f'{product.code}: {exc}') from exc

            line.stock_receipt = doc
            line.save(update_fields=['stock_receipt'])

            if movement.status == RESULT_APPLIED:
                result.posted += 1
            else:
                result.already += 1
            if unit_cost is None:
                result.missing_cost += 1
            result.lines.append((product.code, qty, movement.status))

    result.stock_receipt = primary_receipt
    return result
