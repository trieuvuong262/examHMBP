"""Phát hành, điều chỉnh, hủy và ghi nhận xác nhận nhà cung cấp trên đơn đặt hàng.

Không gửi email. Đơn đã phát hành không sửa trực tiếp: điều chỉnh tạo phiên bản
và đưa đơn về nháp. Đổi đơn giá thì chờ duyệt giá trước khi phát hành lại.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from san_xuat.hub_models import SxPurchaseOrder, SxPurchaseOrderRevision
from san_xuat.services.plan_audit import log_plan_action
from san_xuat.services.planning import PlanningError, confirm_purchase_order


def _q(value) -> Decimal:
    try:
        return Decimal(str(value or '0'))
    except Exception:
        return Decimal('0')


def _money(value: Decimal) -> str:
    return format(_q(value).quantize(Decimal('0.000001')), 'f')


def _qty(value: Decimal) -> str:
    return format(_q(value).quantize(Decimal('0.0001')), 'f')


@transaction.atomic
def issue_purchase_order(*, order_id: int, user=None) -> SxPurchaseOrder:
    return confirm_purchase_order(order_id=order_id, user=user)


@transaction.atomic
def cancel_purchase_order(*, order_id: int, reason: str, user=None) -> SxPurchaseOrder:
    po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    if po.status == SxPurchaseOrder.STATUS_CANCELLED:
        raise PlanningError(f'{po.code} đã hủy.')
    if po.status == SxPurchaseOrder.STATUS_RECEIVED:
        raise PlanningError(f'{po.code} đã nhập đủ — không hủy.')
    if any((ln.qty_received or Decimal('0')) > 0 for ln in po.lines.all()):
        raise PlanningError(f'{po.code} đã nhập một phần — không hủy cả đơn.')
    note = (reason or '').strip()
    if not note:
        raise PlanningError('Nhập lý do hủy đơn.')
    po.status = SxPurchaseOrder.STATUS_CANCELLED
    po.cancel_reason = note[:500]
    po.price_change_pending = False
    po.save(update_fields=['status', 'cancel_reason', 'price_change_pending'])
    log_plan_action(
        action='cancel',
        obj=po,
        summary=f'Hủy đơn đặt hàng {po.code}: {po.cancel_reason}',
        changes={'reason': po.cancel_reason},
        user=user,
    )
    return po


@transaction.atomic
def close_po_remainder(*, order_id: int, reason: str, user=None) -> SxPurchaseOrder:
    """Chấp nhận phần còn thiếu hoặc hàng lỗi và đóng đơn. Bắt buộc có lý do."""
    po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    if po.status != SxPurchaseOrder.STATUS_CONFIRMED:
        raise PlanningError('Chỉ đóng phần còn lại của đơn đã phát hành.')
    note = (reason or '').strip()
    if not note:
        raise PlanningError('Nhập lý do đóng phần còn lại.')
    closed_any = False
    for ln in po.lines.all():
        due = ln.qty_remaining
        if due <= 0:
            continue
        ln.qty_closed = (ln.qty_closed or Decimal('0')) + due
        ln.save(update_fields=['qty_closed'])
        closed_any = True
    if not closed_any:
        raise PlanningError('Không còn số lượng để đóng.')
    po.status = SxPurchaseOrder.STATUS_RECEIVED
    po.notes = (f'{po.notes}\nĐóng phần còn lại: {note}'.strip())[:4000]
    po.save(update_fields=['status', 'notes'])
    log_plan_action(
        action='close',
        obj=po,
        summary=f'Đóng phần còn lại của {po.code}: {note[:300]}',
        changes={'reason': note[:500]},
        user=user,
    )
    return po


@transaction.atomic
def revise_purchase_order(*, order_id: int, post, user=None) -> SxPurchaseOrder:
    po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    if po.status not in (SxPurchaseOrder.STATUS_DRAFT, SxPurchaseOrder.STATUS_CONFIRMED):
        raise PlanningError('Chỉ điều chỉnh đơn nháp hoặc đã phát hành, chưa nhập đủ.')
    if any((ln.qty_received or Decimal('0')) > 0 for ln in po.lines.all()):
        raise PlanningError('Đơn đã nhập một phần — không sửa số lượng đã phát hành.')
    reason = (post.get('reason') or '').strip()
    if not reason:
        raise PlanningError('Nhập lý do điều chỉnh.')
    lines = list(po.lines.all())
    if not lines:
        raise PlanningError('Đơn không có dòng hàng.')

    before = []
    price_changed = False
    for ln in lines:
        qty = _q(post.get(f'qty__{ln.pk}'))
        price = _q(post.get(f'price__{ln.pk}'))
        if qty <= 0:
            raise PlanningError(f'{ln.material_code}: số lượng điều chỉnh phải lớn hơn 0.')
        if price < 0:
            raise PlanningError(f'{ln.material_code}: đơn giá không được âm.')
        if price != _q(ln.unit_price):
            price_changed = True
        before.append({
            'line_id': ln.pk,
            'material_code': ln.material_code,
            'qty_ordered': _qty(ln.qty_ordered),
            'unit_price': _money(ln.unit_price),
            'expected_date': po.expected_date.isoformat() if po.expected_date else None,
        })
        ln.qty_ordered = qty.quantize(Decimal('0.0001'))
        ln.unit_price = price.quantize(Decimal('0.000001'))
        ln.confirmed_qty = None
        ln.confirmed_unit_price = None
        ln.confirmed_date = None
        ln.save(update_fields=[
            'qty_ordered', 'unit_price', 'confirmed_qty', 'confirmed_unit_price', 'confirmed_date',
        ])

    from kho_npl.models import Supplier

    supplier_changed = False
    raw_supplier = (post.get('supplier_id') or '').strip()
    if raw_supplier:
        try:
            supplier_id = int(raw_supplier)
        except (TypeError, ValueError):
            supplier_id = po.supplier_id
        if supplier_id != po.supplier_id:
            supplier = Supplier.objects.filter(pk=supplier_id, is_active=True).first()
            if supplier is None:
                raise PlanningError('Nhà cung cấp không còn dùng.')
            before.append({'supplier_id': po.supplier_id, 'supplier_name': getattr(po.supplier, 'name', '')})
            po.supplier = supplier
            po.supplier_name = (supplier.name or '')[:200]
            supplier_changed = True

    new_date = parse_date((post.get('expected_date') or '').strip()) if post.get('expected_date') else po.expected_date
    version = (po.revisions.order_by('-version').values_list('version', flat=True).first() or 0) + 1
    SxPurchaseOrderRevision.objects.create(
        order=po,
        version=version,
        reason=reason[:500],
        changes={'before': before, 'expected_date': new_date.isoformat() if new_date else None, 'supplier_id': po.supplier_id},
        created_by=user if getattr(user, 'pk', None) else None,
    )
    po.expected_date = new_date
    po.status = SxPurchaseOrder.STATUS_DRAFT
    po.supplier_confirm_status = SxPurchaseOrder.CONFIRM_PENDING
    po.supplier_confirmed_at = None
    po.supplier_confirm_note = ''
    po.price_change_pending = price_changed or supplier_changed or po.price_change_pending
    po.save(update_fields=[
        'supplier', 'supplier_name', 'expected_date', 'status', 'supplier_confirm_status',
        'supplier_confirmed_at', 'supplier_confirm_note', 'price_change_pending',
    ])
    log_plan_action(
        action='update',
        obj=po,
        summary=f'Điều chỉnh {po.code} phiên bản {version}. Đơn về nháp để phát hành lại.',
        changes={'version': version, 'price_changed': bool(po.price_change_pending), 'reason': reason[:500]},
        user=user,
    )
    return po


@transaction.atomic
def approve_po_price_change(*, order_id: int, user=None) -> SxPurchaseOrder:
    po = SxPurchaseOrder.objects.select_for_update().get(pk=order_id)
    if not po.price_change_pending:
        raise PlanningError(f'{po.code} không có thay đổi giá chờ duyệt.')
    if po.status != SxPurchaseOrder.STATUS_DRAFT:
        raise PlanningError('Duyệt giá điều chỉnh khi đơn đang nháp.')
    po.price_change_pending = False
    po.save(update_fields=['price_change_pending'])
    log_plan_action(
        action='confirm',
        obj=po,
        summary=f'Duyệt giá điều chỉnh đơn {po.code}.',
        user=user,
    )
    return po


@transaction.atomic
def record_supplier_confirmation(*, order_id: int, post, user=None) -> SxPurchaseOrder:
    po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    if po.status != SxPurchaseOrder.STATUS_CONFIRMED:
        raise PlanningError('Chỉ ghi nhận xác nhận khi đơn đã phát hành.')
    lines = list(po.lines.all())
    if not lines:
        raise PlanningError('Đơn không có dòng hàng.')
    shared_date = parse_date((post.get('confirmed_date') or '').strip()) if post.get('confirmed_date') else None
    variance = False
    for ln in lines:
        qty = _q(post.get(f'confirm_qty__{ln.pk}'))
        price = _q(post.get(f'confirm_price__{ln.pk}'))
        raw_date = (post.get(f'confirm_date__{ln.pk}') or '').strip()
        line_date = parse_date(raw_date) if raw_date else shared_date
        if qty <= 0:
            raise PlanningError(f'{ln.material_code}: số lượng NCC xác nhận phải lớn hơn 0.')
        if price < 0:
            raise PlanningError(f'{ln.material_code}: đơn giá NCC xác nhận không được âm.')
        if qty != _q(ln.qty_ordered) or price != _q(ln.unit_price) or (
            line_date and po.expected_date and line_date != po.expected_date
        ):
            variance = True
        ln.confirmed_qty = qty.quantize(Decimal('0.0001'))
        ln.confirmed_unit_price = price.quantize(Decimal('0.000001'))
        ln.confirmed_date = line_date
        ln.save(update_fields=['confirmed_qty', 'confirmed_unit_price', 'confirmed_date'])

    note = (post.get('confirm_note') or '').strip()
    if variance and not note:
        raise PlanningError('NCC xác nhận lệch đơn — ghi chú phần lệch.')
    po.supplier_confirm_status = (
        SxPurchaseOrder.CONFIRM_VARIANCE if variance else SxPurchaseOrder.CONFIRM_MATCHED
    )
    po.supplier_confirmed_at = timezone.now()
    po.supplier_confirm_note = note[:500]
    po.supplier_recorded_by = user if getattr(user, 'pk', None) else None
    po.save(update_fields=[
        'supplier_confirm_status', 'supplier_confirmed_at',
        'supplier_confirm_note', 'supplier_recorded_by',
    ])
    log_plan_action(
        action='update',
        obj=po,
        summary=(
            f'Ghi nhận NCC xác nhận {po.code}: {po.get_supplier_confirm_status_display()}.'
        ),
        changes={'variance': variance, 'note': note[:500]},
        user=user,
    )
    return po


@transaction.atomic
def record_po_return(*, order_id: int, line_id: int, qty, reason: str, user=None) -> SxPurchaseOrder:
    """Ghi số trả nhà cung cấp. Không tính phần trả là đã hoàn thành đơn."""
    po = SxPurchaseOrder.objects.select_for_update().get(pk=order_id)
    if po.status not in (SxPurchaseOrder.STATUS_CONFIRMED, SxPurchaseOrder.STATUS_RECEIVED):
        raise PlanningError('Chỉ ghi trả hàng trên đơn đã phát hành.')
    note = (reason or '').strip()
    if not note:
        raise PlanningError('Nhập lý do trả hàng.')
    amount = _q(qty)
    if amount <= 0:
        raise PlanningError('Số lượng trả phải lớn hơn 0.')
    ln = po.lines.select_for_update().filter(pk=line_id).first()
    if ln is None:
        raise PlanningError('Không thấy dòng hàng.')
    if amount > (ln.qty_received or Decimal('0')):
        raise PlanningError(f'{ln.material_code}: số trả vượt số đã nhận.')
    ln.qty_returned = (ln.qty_returned or Decimal('0')) + amount
    ln.save(update_fields=['qty_returned'])
    log_plan_action(
        action='update',
        obj=po,
        summary=f'Trả {amount} {ln.material_code} của {po.code}: {note[:300]}',
        changes={'line_id': ln.pk, 'qty_returned': _qty(ln.qty_returned), 'reason': note[:500]},
        user=user,
    )
    return po
