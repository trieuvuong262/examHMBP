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
from kho_npl.services.scrap_warehouse import material_default_location

from san_xuat.hub_models import SxPurchaseOrder
from san_xuat.services.planning import PlanningError
from san_xuat.services.plan_audit import log_plan_action

_Q3 = Decimal('0.001')


def default_receipt_location() -> WarehouseLocation | None:
    """Vị trí nhập gợi ý — kho thường được tạo sớm nhất (thường là kho chính).

    Chỉ dùng khi người nhập không chọn vị trí; màn hình DMH luôn bắt chọn.
    """
    return (
        WarehouseLocation.objects.filter(
            is_active=True, location_kind=WarehouseLocation.KIND_STOCK,
        )
        .order_by('pk')
        .first()
        or WarehouseLocation.objects.filter(is_active=True).order_by('pk').first()
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
    auto_post: bool = False,
) -> StockReceipt:
    po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    if po.status == SxPurchaseOrder.STATUS_DRAFT:
        from san_xuat.services.planning import confirm_purchase_order

        po = confirm_purchase_order(order_id=po.pk, user=user)
        po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=po.pk)

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
        for m in Material.objects.filter(code__in=codes).select_related('primary_location')
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
        line_location = material_default_location(material) or target
        receipt_lines.append(
            StockReceiptLine(
                receipt=receipt,
                material=material,
                ordered_qty=(ln.qty_ordered or Decimal('0')).quantize(_Q3),
                received_qty=qty,
                location=line_location,
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
    if auto_post:
        raise PlanningError(
            'Phiếu từ đơn đặt hàng phải nhập số thực nhận và số đạt QC trước khi ghi sổ. '
            'Hàng chưa kiểm hoặc hàng lỗi không được cộng vào tồn khả dụng.'
        )
    return receipt


def ensure_draft_receipts(orders, *, user=None) -> list[StockReceipt]:
    """Phiếu nhập kho của các đơn mua: mở phiếu đang có, hoặc lập nháp mới."""
    found: list[StockReceipt] = []
    seen: set[int] = set()
    for po in orders or []:
        existing = (
            po_receipts(po)
            .exclude(status=DOC_STATUS_CANCELLED)
            .order_by('-id')
            .first()
        )
        if existing is not None:
            if existing.pk not in seen:
                seen.add(existing.pk)
                found.append(existing)
            continue
        fresh = SxPurchaseOrder.objects.prefetch_related('lines').filter(pk=po.pk).first()
        if fresh is None or not po_remaining_lines(fresh):
            continue
        receipt = create_receipt_from_po(order_id=fresh.pk, user=user, auto_post=False)
        if receipt.pk not in seen:
            seen.add(receipt.pk)
            found.append(receipt)
    return found


@transaction.atomic
def sync_po_received_from_po_receipts(*, order_id: int, user=None) -> dict:
    """Cập nhật SL đã nhập của DMH từ các phiếu nhập kho đã ghi sổ."""
    po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    posted = po_receipts(po).filter(status=DOC_STATUS_POSTED)
    qty_by_code: dict[str, Decimal] = {}
    pass_by_code: dict[str, Decimal] = {}
    fail_by_code: dict[str, Decimal] = {}
    for line in StockReceiptLine.objects.filter(receipt__in=posted).select_related('material'):
        key = (line.material.code or '').strip().upper()
        physical = line.received_qty or Decimal('0')
        qty_by_code[key] = qty_by_code.get(key, Decimal('0')) + physical
        pass_by_code[key] = pass_by_code.get(key, Decimal('0')) + (line.qc_pass_qty or Decimal('0'))
        fail_by_code[key] = fail_by_code.get(key, Decimal('0')) + (line.qc_fail_qty or Decimal('0'))

    updated = 0
    for ln in po.lines.all():
        key = (ln.material_code or '').strip().upper()
        new_qty = qty_by_code.get(key)
        if new_qty is None:
            continue
        new_qty = new_qty.quantize(Decimal('0.0001'))
        new_pass = pass_by_code.get(key, Decimal('0')).quantize(Decimal('0.0001'))
        new_fail = fail_by_code.get(key, Decimal('0')).quantize(Decimal('0.0001'))
        changed = (
            ln.qty_received != new_qty
            or (ln.qty_qc_pass or Decimal('0')) != new_pass
            or (ln.qty_qc_fail or Decimal('0')) != new_fail
        )
        if changed:
            ln.qty_received = new_qty
            ln.qty_qc_pass = new_pass
            ln.qty_qc_fail = new_fail
            ln.save(update_fields=['qty_received', 'qty_qc_pass', 'qty_qc_fail'])
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


def on_npl_receipt_posted(receipt) -> None:
    """Sau ghi sổ phiếu nhập NPL: cập nhật DMH và load tồn các mã trên KHSX."""
    codes = [
        (line.material.code or '').strip()
        for line in receipt.lines.select_related('material').all()
        if getattr(line.material, 'code', None)
    ]
    po_number = (getattr(receipt, 'po_number', None) or '').strip()
    if po_number:
        po = SxPurchaseOrder.objects.filter(code=po_number, is_demo=False).first()
        if po:
            sync_po_received_from_po_receipts(order_id=po.pk)
    from san_xuat.services.plan_order_npl import reload_khsx_stock_for_codes

    reload_khsx_stock_for_codes(codes)


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value or '0'))
    except Exception:
        return Decimal('0')


@transaction.atomic
def receive_po_batch(
    *,
    order_id: int,
    rows: list[dict],
    user=None,
    allow_over: bool = False,
    over_note: str = '',
) -> StockReceipt:
    """Nhận một đợt: chỉ số đạt QC vào kho thường, hàng lỗi vào kho hủy."""
    from kho_npl.services.receipts import post_stock_receipt
    from kho_npl.services.scrap_warehouse import get_scrap_location
    from kho_npl.stock_domain import STOCK_DOMAIN_NPL

    po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    if po.status != SxPurchaseOrder.STATUS_CONFIRMED:
        raise PlanningError('Chỉ nhận hàng trên đơn đã phát hành.')
    pending = po_receipts(po).exclude(status__in=(DOC_STATUS_POSTED, DOC_STATUS_CANCELLED)).first()
    if pending is not None:
        if pending.lines.filter(received_qty__gt=0).exists():
            raise PlanningError(f'Phiếu {pending.number} đang chờ ghi sổ. Ghi sổ hoặc hủy phiếu đó trước.')
        pending.status = DOC_STATUS_CANCELLED
        pending.save(update_fields=['status'])

    by_id = {ln.pk: ln for ln in po.lines.all()}
    parsed = []
    for row in rows or []:
        try:
            line_id = int(row.get('line_id') or 0)
        except (TypeError, ValueError):
            continue
        ln = by_id.get(line_id)
        if ln is None:
            continue
        actual = _dec(row.get('actual'))
        if actual <= 0:
            continue
        passed = _dec(row.get('qc_pass'))
        failed = _dec(row.get('qc_fail'))
        doc = _dec(row.get('doc'))
        if passed < 0 or failed < 0:
            raise PlanningError(f'{ln.material_code}: số QC không được âm.')
        if (passed + failed).quantize(_Q3) != actual.quantize(_Q3):
            raise PlanningError(
                f'{ln.material_code}: số đạt QC cộng số không đạt phải bằng số thực nhận. '
                'Phần chưa kiểm không được nhập kho.'
            )
        open_physical = (ln.qty_ordered or Decimal('0')) - (ln.qty_received or Decimal('0'))
        if actual > open_physical:
            if not allow_over:
                raise PlanningError(
                    f'{ln.material_code}: thực nhận {actual} vượt số còn theo đơn {open_physical}. '
                    'Đánh dấu nhận vượt và ghi chú nếu vẫn nhập.'
                )
            if not (over_note or '').strip():
                raise PlanningError('Nhận vượt số lượng đặt — nhập ghi chú.')
        parsed.append((ln, doc, actual, passed, failed))
    if not parsed:
        raise PlanningError('Nhập số thực nhận lớn hơn 0 cho ít nhất một dòng.')

    codes = [(ln.material_code or '').strip() for ln, *_rest in parsed]
    materials = {
        (m.code or '').strip().upper(): m
        for m in Material.objects.filter(code__in=codes).select_related('primary_location')
    }
    target = default_receipt_location()
    if target is None:
        raise PlanningError('Chưa khai báo vị trí kho thường.')
    scrap = get_scrap_location(STOCK_DOMAIN_NPL)
    receipt = StockReceipt.objects.create(
        number=next_receipt_number(),
        receipt_date=timezone.localdate(),
        supplier=po.supplier,
        po_number=po.code,
        created_by=user if getattr(user, 'pk', None) else None,
        received_by=user if getattr(user, 'pk', None) else None,
        notes=(over_note or f'Nhận và QC theo đơn {po.code}').strip(),
    )
    receipt_lines = []
    for ln, doc, actual, passed, failed in parsed:
        material = materials.get((ln.material_code or '').strip().upper())
        if material is None:
            raise PlanningError(f'{ln.material_code} chưa có trong danh mục kho.')
        price = ln.unit_price or material.base_price or Decimal('0')
        stock_loc = material_default_location(material) or target
        if passed > 0:
            receipt_lines.append(StockReceiptLine(
                receipt=receipt,
                material=material,
                ordered_qty=(ln.qty_ordered or Decimal('0')).quantize(_Q3),
                received_qty=passed.quantize(_Q3),
                doc_qty=doc.quantize(_Q3),
                actual_qty=passed.quantize(_Q3),
                qc_pass_qty=passed.quantize(_Q3),
                qc_fail_qty=Decimal('0'),
                location=stock_loc,
                batch_code=(po.code or '')[:60],
                unit_price=price,
                notes=f'Đạt QC {po.code}'[:255],
            ))
        if failed > 0:
            receipt_lines.append(StockReceiptLine(
                receipt=receipt,
                material=material,
                ordered_qty=(ln.qty_ordered or Decimal('0')).quantize(_Q3),
                received_qty=failed.quantize(_Q3),
                doc_qty=Decimal('0'),
                actual_qty=failed.quantize(_Q3),
                qc_pass_qty=Decimal('0'),
                qc_fail_qty=failed.quantize(_Q3),
                location=scrap,
                batch_code=(po.code or '')[:60],
                unit_price=price,
                notes=f'Không đạt QC {po.code}'[:255],
            ))
    StockReceiptLine.objects.bulk_create(receipt_lines)
    posted = post_stock_receipt(receipt, user, require_attachment=False)
    sync_po_received_from_po_receipts(order_id=po.pk, user=user)
    log_plan_action(
        action='receipt',
        obj=po,
        summary=(
            f'Nhận và QC {posted.number} cho {po.code}. '
            'Chỉ số đạt QC vào kho thường, hàng lỗi vào kho hủy.'
        ),
        changes={'receipt': posted.number, 'lines': len(parsed)},
        user=user,
    )
    return posted
