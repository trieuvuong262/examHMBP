"""Đơn mua hàng (DMH) → phiếu nhập kho NPL.

P4 — đóng vòng phản hồi giữa mua hàng và kho:
  * ``create_receipt_from_po`` sinh phiếu nhập kho *nháp* trong kho NPL từ phần
    còn lại chưa nhận của DMH. Nghiệp vụ kho vẫn phải đính kèm chứng từ rồi
    ghi sổ (``post_stock_receipt``) — ta không tự ghi sổ thay thủ kho.
  * ``sync_po_received_from_po_receipts`` đọc lại các phiếu nhập đã ghi sổ gắn
    với DMH để cập nhật ``qty_received`` và trạng thái DMH.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_CANCELLED, DOC_STATUS_POSTED
from kho_npl.models import Material, StockReceipt, StockReceiptLine, WarehouseLocation
from kho_npl.services.doc_numbers import next_receipt_number

from san_xuat.hub_models import SxPurchaseOrder
from san_xuat.services.planning import PlanningError
from san_xuat.services.plan_audit import log_plan_action

_Q3 = Decimal('0.001')


def default_receipt_location() -> WarehouseLocation | None:
    """Vị trí nhập mặc định — kho thường đầu tiên đang dùng."""
    return (
        WarehouseLocation.objects.filter(
            is_active=True, location_kind=WarehouseLocation.KIND_STOCK,
        )
        .order_by('code')
        .first()
        or WarehouseLocation.objects.filter(is_active=True).order_by('code').first()
    )


def po_receipts(po: SxPurchaseOrder):
    """Các phiếu nhập kho NPL gắn với DMH (theo số PO)."""
    codes = [c for c in {(po.code or '').strip()} if c]
    if not codes:
        return StockReceipt.objects.none()
    return StockReceipt.objects.filter(po_number__in=codes).order_by('-receipt_date', '-id')


def po_remaining_lines(po: SxPurchaseOrder) -> list:
    return [ln for ln in po.lines.all() if ln.qty_remaining > 0]


@transaction.atomic
def create_receipt_from_po(
    *,
    order_id: int,
    user=None,
    receipt_date=None,
    location=None,
    notes: str = '',
) -> StockReceipt:
    po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    if po.status == SxPurchaseOrder.STATUS_DRAFT:
        raise PlanningError('Xác nhận đơn mua hàng trước khi tạo phiếu nhập kho.')

    existing = po_receipts(po).exclude(status=DOC_STATUS_CANCELLED).first()
    if existing and existing.status != DOC_STATUS_POSTED:
        raise PlanningError(
            f'Đơn mua hàng đã có phiếu nhập {existing.number} đang chờ ghi sổ.'
        )

    lines = po_remaining_lines(po)
    if not lines:
        raise PlanningError('Đơn mua hàng không còn số lượng chờ nhập.')

    codes = [(ln.material_code or '').strip() for ln in lines]
    materials = {
        (m.code or '').strip().upper(): m
        for m in Material.objects.filter(code__in=codes)
    }
    missing = sorted({
        (ln.material_code or '').strip()
        for ln in lines
        if (ln.material_code or '').strip().upper() not in materials
    })
    if missing:
        raise PlanningError(
            'Các mã sau chưa có trong danh mục NPL của kho: ' + ', '.join(missing[:8])
        )

    target = location or default_receipt_location()
    if target is None:
        raise PlanningError('Chưa khai báo vị trí kho — tạo vị trí trong Kho NPL trước.')

    receipt = StockReceipt.objects.create(
        number=next_receipt_number(),
        receipt_date=receipt_date or timezone.localdate(),
        supplier=po.supplier,
        po_number=po.code,
        created_by=user if getattr(user, 'pk', None) else None,
        received_by=user if getattr(user, 'pk', None) else None,
        notes=(notes or f'Nhập theo đơn mua hàng {po.code}').strip(),
    )

    receipt_lines = []
    for ln in lines:
        material = materials[(ln.material_code or '').strip().upper()]
        qty = ln.qty_remaining.quantize(_Q3)
        price = ln.unit_price or material.base_price or Decimal('0')
        receipt_lines.append(
            StockReceiptLine(
                receipt=receipt,
                material=material,
                ordered_qty=(ln.qty_ordered or Decimal('0')).quantize(_Q3),
                received_qty=qty,
                location=target,
                batch_code=(po.code or '')[:60],
                unit_price=price,
                notes=f'DMH {po.code}'[:255],
            )
        )
    StockReceiptLine.objects.bulk_create(receipt_lines)

    po.stock_receipt = receipt
    po.save(update_fields=['stock_receipt'])

    log_plan_action(
        action='receipt',
        obj=po,
        summary=(
            f'Tạo phiếu nhập kho {receipt.number} từ DMH {po.code} '
            f'({len(receipt_lines)} mã NPL).'
        ),
        changes={'receipt': receipt.number, 'lines': len(receipt_lines)},
        user=user,
    )
    return receipt


@transaction.atomic
def sync_po_received_from_po_receipts(*, order_id: int, user=None) -> dict:
    """Cập nhật SL đã nhập của DMH từ các phiếu nhập kho đã ghi sổ."""
    po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    posted = po_receipts(po).filter(status=DOC_STATUS_POSTED)
    qty_by_code: dict[str, Decimal] = {}
    for line in StockReceiptLine.objects.filter(receipt__in=posted).select_related('material'):
        key = (line.material.code or '').strip().upper()
        qty_by_code[key] = qty_by_code.get(key, Decimal('0')) + (line.received_qty or Decimal('0'))

    updated = 0
    for ln in po.lines.all():
        key = (ln.material_code or '').strip().upper()
        new_qty = qty_by_code.get(key)
        if new_qty is None:
            continue
        new_qty = new_qty.quantize(Decimal('0.0001'))
        if ln.qty_received != new_qty:
            ln.qty_received = new_qty
            ln.save(update_fields=['qty_received'])
            updated += 1

    lines = list(po.lines.all())
    fully = bool(lines) and all(ln.qty_remaining <= 0 for ln in lines)
    status_changed = False
    if fully and po.status != SxPurchaseOrder.STATUS_RECEIVED:
        po.status = SxPurchaseOrder.STATUS_RECEIVED
        po.save(update_fields=['status'])
        status_changed = True

    if updated or status_changed:
        log_plan_action(
            action='receipt',
            obj=po,
            summary=(
                f'Cập nhật SL đã nhập DMH {po.code} từ {posted.count()} phiếu nhập'
                + (' — đã nhập đủ.' if status_changed else '.')
            ),
            changes={'lines_updated': updated, 'received_full': fully},
            user=user,
        )
    return {
        'updated': updated,
        'received_full': fully,
        'receipts': posted.count(),
        'status_changed': status_changed,
    }
