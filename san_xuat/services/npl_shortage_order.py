"""Đặt hàng phần NPL thiếu trên thẻ KHSX — gom theo nhà cung cấp."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from kho_npl.models import Material, Supplier
from san_xuat.hub_models import (
    SxNplPurchaseRequest,
    SxNplPurchaseRequestLine,
    SxPurchaseOrder,
    SxPurchaseOrderLine,
    SxSalesOrder,
)
from san_xuat.services.planning import PlanningError, _code
from san_xuat.services.plan_order_npl import sync_order_npl

_Q4 = Decimal('0.0001')
_PAYMENTS = {key for key, _label in SxNplPurchaseRequest.PAYMENT_CHOICES}


def _q(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_Q4)


def _parse_qty(raw) -> Decimal:
    text = str(raw or '').strip().replace(' ', '')
    if not text:
        return Decimal('0')
    if ',' in text and '.' in text:
        text = text.replace('.', '').replace(',', '.')
    elif ',' in text:
        text = text.replace(',', '.')
    try:
        return _q(text)
    except (InvalidOperation, ValueError):
        raise PlanningError('Số lượng hoặc đơn giá không hợp lệ.')


def _parse_date(raw) -> date | None:
    text = str(raw or '').strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise PlanningError('Ngày giao không hợp lệ.')


@dataclass
class ShortageOrderLine:
    npl_line_id: int
    material_code: str
    material_name: str
    image_url: str
    spec_label: str
    unit: str
    qty: Decimal
    unit_price: Decimal
    note: str
    shortfall: Decimal
    supplier_id: int


@dataclass
class ShortageOrderGroup:
    key: str
    supplier_id: int
    supplier_name: str
    contact_name: str
    phone: str
    address: str
    tax_code: str
    payment_method: str
    expected_date: date | None
    lines: list[ShortageOrderLine] = field(default_factory=list)


def _draft_pr(order: SxSalesOrder) -> SxNplPurchaseRequest | None:
    return (
        SxNplPurchaseRequest.objects.filter(
            sales_order=order,
            is_demo=False,
            status=SxNplPurchaseRequest.STATUS_DRAFT,
        )
        .order_by('-id')
        .first()
    )


def _pending_qty_by_code(order: SxSalesOrder, *, exclude_pr_id: int | None) -> dict[str, Decimal]:
    """SL đang nằm trên YCM nháp/đã gửi của đơn này, chưa thành đơn mua."""
    qs = SxNplPurchaseRequestLine.objects.filter(
        request__sales_order=order,
        request__is_demo=False,
        request__status__in=(
            SxNplPurchaseRequest.STATUS_DRAFT,
            SxNplPurchaseRequest.STATUS_SUBMITTED,
        ),
    )
    if exclude_pr_id:
        qs = qs.exclude(request_id=exclude_pr_id)
    covered = set(
        SxPurchaseOrderLine.objects.filter(
            order__purchase_request_id__in=qs.values('request_id'),
            order__is_demo=False,
            order__status__in=(
                SxPurchaseOrder.STATUS_DRAFT,
                SxPurchaseOrder.STATUS_CONFIRMED,
            ),
        ).values_list('order__purchase_request_id', 'material_code')
    )
    out: dict[str, Decimal] = defaultdict(lambda: Decimal('0'))
    for ln in qs.only('request_id', 'material_code', 'qty'):
        key = (ln.material_code or '').strip().casefold()
        if (ln.request_id, ln.material_code) in covered:
            continue
        out[key] += _q(ln.qty)
    return out


def build_shortage_preview(order: SxSalesOrder) -> list[ShortageOrderGroup]:
    draft = _draft_pr(order)
    pending = _pending_qty_by_code(order, exclude_pr_id=draft.pk if draft else None)
    draft_lines = {}
    if draft:
        for ln in draft.lines.all():
            draft_lines[(ln.material_code or '').strip().casefold()] = ln

    codes = [(ln.material_code or '').strip() for ln in order.npl_lines.all()]
    materials = {
        m.code.casefold(): m
        for m in Material.objects.filter(code__in=codes).select_related(
            'supplier', 'unit', 'color', 'specification',
        )
    }
    buckets: dict[str, ShortageOrderGroup] = {}
    for ln in order.npl_lines.all():
        code_key = (ln.material_code or '').strip().casefold()
        mat = materials.get(code_key)
        supplier = mat.supplier if mat and mat.supplier_id and mat.supplier.is_active else None
        saved = draft_lines.get(code_key)
        supplier_id = saved.supplier_id if saved and saved.supplier_id else (supplier.pk if supplier else 0)
        shortfall = _q(ln.qty_shortfall)
        orderable = shortfall - _q(pending.get(code_key))
        if orderable < 0:
            orderable = Decimal('0')
        qty = _q(saved.qty) if saved and saved.qty else orderable
        if qty <= 0 and orderable <= 0:
            continue
        if qty <= 0:
            qty = orderable
        spec_bits = []
        if mat and mat.specification_id:
            spec_bits.append(mat.specification.name)
        if mat and mat.color_id:
            spec_bits.append(mat.color.name)
        image_url = ''
        if mat and mat.image:
            try:
                image_url = mat.image.url
            except (ValueError, OSError):
                image_url = ''
        price = _q(saved.unit_price) if saved and saved.unit_price else _q(mat.base_price if mat else 0)
        note = (saved.notes if saved else '') or order.code
        lead = int(ln.buy_lead_days or 0)
        expected = saved.expected_date if saved and saved.expected_date else (
            timezone.localdate() + timedelta(days=lead)
        )
        pay = (saved.payment_method if saved else '') or SxNplPurchaseRequest.PAYMENT_TRANSFER
        key = str(supplier_id or 0)
        group = buckets.get(key)
        if group is None:
            src = None
            if saved and saved.supplier_id:
                src = saved.supplier
            elif supplier and supplier.pk == supplier_id:
                src = supplier
            group = ShortageOrderGroup(
                key=key,
                supplier_id=supplier_id or 0,
                supplier_name=(src.name if src else ''),
                contact_name=(src.contact_name if src else ''),
                phone=(src.phone if src else ''),
                address=(src.address if src else ''),
                tax_code=(src.tax_code if src else ''),
                payment_method=pay if pay in _PAYMENTS else SxNplPurchaseRequest.PAYMENT_TRANSFER,
                expected_date=expected,
            )
            buckets[key] = group
        elif expected and (group.expected_date is None or expected > group.expected_date):
            group.expected_date = expected
        group.lines.append(ShortageOrderLine(
            npl_line_id=ln.pk,
            material_code=ln.material_code,
            material_name=ln.material_name or (mat.name if mat else ''),
            image_url=image_url,
            spec_label=' / '.join(spec_bits),
            unit=ln.unit or (mat.unit.name if mat and mat.unit_id else ''),
            qty=qty,
            unit_price=price,
            note=note,
            shortfall=shortfall,
            supplier_id=supplier_id or 0,
        ))
    return list(buckets.values())


@transaction.atomic
def save_shortage_request(*, order_id: int, post, user=None) -> SxNplPurchaseRequest:
    order = sync_order_npl(order_id=order_id)
    preview = {ln.npl_line_id: ln for group in build_shortage_preview(order) for ln in group.lines}
    if not preview:
        raise PlanningError('Không còn NPL thiếu để đặt.')

    chosen: dict[int, dict] = {}
    for line_id, src in preview.items():
        qty = _parse_qty(post.get(f'qty__{line_id}'))
        if qty <= 0:
            continue
        price = _parse_qty(post.get(f'price__{line_id}'))
        if price < 0:
            raise PlanningError('Đơn giá không được âm.')
        chosen[line_id] = {
            'src': src,
            'qty': qty,
            'price': price,
            'note': (post.get(f'note__{line_id}') or '').strip()[:255],
        }
    if not chosen:
        raise PlanningError('Nhập số lượng đặt lớn hơn 0.')

    by_group: dict[str, list[int]] = defaultdict(list)
    for line_id, src in preview.items():
        if line_id in chosen:
            by_group[str(src.supplier_id or 0)].append(line_id)

    group_meta: dict[str, dict] = {}
    for key, line_ids in by_group.items():
        raw_supplier = (post.get(f'supplier__{key}') or '').strip()
        supplier_id = int(raw_supplier) if raw_supplier.isdigit() else 0
        if key != '0' and not supplier_id:
            supplier_id = int(key) if key.isdigit() else 0
        supplier = Supplier.objects.filter(pk=supplier_id, is_active=True).first() if supplier_id else None
        if supplier is None:
            raise PlanningError('Chọn nhà cung cấp cho nhóm hàng chưa có NCC.')
        pay = (post.get(f'pay__{key}') or '').strip()
        if pay not in _PAYMENTS:
            pay = SxNplPurchaseRequest.PAYMENT_TRANSFER
        expected = _parse_date(post.get(f'date__{key}'))
        supplier.contact_name = (post.get(f'contact__{key}') or '').strip()[:120]
        supplier.phone = (post.get(f'phone__{key}') or '').strip()[:40]
        supplier.address = (post.get(f'address__{key}') or '').strip()[:255]
        supplier.tax_code = (post.get(f'tax__{key}') or '').strip()[:32]
        supplier.save(update_fields=['contact_name', 'phone', 'address', 'tax_code'])
        group_meta[key] = {
            'supplier': supplier,
            'pay': pay,
            'expected': expected,
            'line_ids': line_ids,
        }

    draft = _draft_pr(order)
    due_dates = [meta['expected'] for meta in group_meta.values() if meta['expected']]
    due = min(due_dates) if due_dates else None
    pays = {meta['pay'] for meta in group_meta.values()}
    header_pay = next(iter(pays)) if len(pays) == 1 else ''
    if draft:
        pr = draft
        pr.lines.all().delete()
        pr.due_date = due or pr.due_date
        pr.payment_method = header_pay
        pr.notes = pr.notes or order.code
        pr.save(update_fields=['due_date', 'payment_method', 'notes'])
    else:
        from san_xuat.services.plan_order_npl import upsert_material_plan_from_order

        plan = upsert_material_plan_from_order(order, user=user)
        pr = SxNplPurchaseRequest.objects.create(
            code=_code('npl_pr', SxNplPurchaseRequest),
            material_plan=plan,
            sales_order=order,
            request_date=timezone.localdate(),
            due_date=due,
            status=SxNplPurchaseRequest.STATUS_DRAFT,
            notes=order.code,
            payment_method=header_pay,
            is_demo=False,
        )

    npl_by_id = {ln.pk: ln for ln in order.npl_lines.all()}
    rows = []
    for meta in group_meta.values():
        for line_id in meta['line_ids']:
            item = chosen[line_id]
            src = item['src']
            npl = npl_by_id.get(line_id)
            rows.append(SxNplPurchaseRequestLine(
                request=pr,
                material_code=src.material_code,
                material_name=src.material_name,
                qty=item['qty'],
                need_date=npl.ready_date if npl else None,
                supplier=meta['supplier'],
                unit_price=item['price'],
                expected_date=meta['expected'],
                payment_method=meta['pay'],
                notes=item['note'],
            ))
    SxNplPurchaseRequestLine.objects.bulk_create(rows)
    return pr


@transaction.atomic
def split_purchase_orders_from_request(*, request_id: int, user=None) -> list[SxPurchaseOrder]:
    """Một đơn mua nháp cho mỗi nhà cung cấp trên YCM đã duyệt."""
    pr = (
        SxNplPurchaseRequest.objects.select_for_update()
        .prefetch_related('lines__supplier')
        .get(pk=request_id)
    )
    if pr.status != SxNplPurchaseRequest.STATUS_APPROVED:
        raise PlanningError('Chỉ tách đơn mua từ yêu cầu đã duyệt.')
    lines = [ln for ln in pr.lines.all() if ln.qty and ln.qty > 0]
    if not lines or not any(ln.supplier_id for ln in lines):
        return []
    if any(not ln.supplier_id for ln in lines):
        raise PlanningError('Còn dòng chưa có nhà cung cấp — không tách được đơn mua.')

    groups: dict[int, list] = defaultdict(list)
    for ln in lines:
        groups[ln.supplier_id].append(ln)

    created: list[SxPurchaseOrder] = []
    for supplier_id, glines in groups.items():
        supplier = glines[0].supplier
        po = (
            SxPurchaseOrder.objects.filter(
                purchase_request=pr,
                supplier_id=supplier_id,
                is_demo=False,
                status=SxPurchaseOrder.STATUS_DRAFT,
            )
            .order_by('-id')
            .first()
        )
        expected = max((ln.expected_date for ln in glines if ln.expected_date), default=None)
        pay = next((ln.payment_method for ln in glines if ln.payment_method), pr.payment_method or '')
        if po:
            po.lines.all().delete()
            po.supplier_name = supplier.name if supplier else po.supplier_name
            po.expected_date = expected or po.expected_date
            po.payment_method = pay
            po.order_date = po.order_date or timezone.localdate()
            po.save(update_fields=[
                'supplier_name', 'expected_date', 'payment_method', 'order_date',
            ])
        else:
            po = SxPurchaseOrder.objects.create(
                code=_code('po', SxPurchaseOrder),
                supplier_name=supplier.name if supplier else '',
                supplier=supplier,
                expected_date=expected or pr.due_date,
                purchase_request=pr,
                status=SxPurchaseOrder.STATUS_DRAFT,
                notes=pr.notes or '',
                payment_method=pay,
                order_date=timezone.localdate(),
                is_demo=False,
            )
        SxPurchaseOrderLine.objects.bulk_create([
            SxPurchaseOrderLine(
                order=po,
                material_code=ln.material_code,
                material_name=ln.material_name,
                qty_ordered=_q(ln.qty),
                qty_received=Decimal('0'),
                unit_price=_q(ln.unit_price),
                need_date=ln.need_date,
                notes=ln.notes or '',
            )
            for ln in glines
        ])
        created.append(po)
    return created
