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
def save_shortage_request(*, order_id: int, post, user=None, group_key: str = '') -> SxNplPurchaseRequest:
    order = sync_order_npl(order_id=order_id)
    preview = {ln.npl_line_id: ln for group in build_shortage_preview(order) for ln in group.lines}
    key = (group_key or '').strip()
    if key:
        preview = {
            line_id: src for line_id, src in preview.items()
            if str(src.supplier_id or 0) == key
        }
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
        pr.request_date = timezone.localdate()
        pr.save(update_fields=['due_date', 'payment_method', 'notes', 'request_date'])
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
            created_by=user if getattr(user, 'pk', None) else None,
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


def apply_posted_shortage(groups: list[ShortageOrderGroup], post) -> None:
    """Giữ lại NCC, số lượng và thông tin đơn người vừa nhập khi lưu bị lỗi."""
    for group in groups:
        key = group.key
        raw_supplier = (post.get(f'supplier__{key}') or '').strip()
        if raw_supplier.isdigit():
            group.supplier_id = int(raw_supplier)
        for attr, field in (
            ('contact_name', 'contact'),
            ('phone', 'phone'),
            ('address', 'address'),
            ('tax_code', 'tax'),
            ('payment_method', 'pay'),
        ):
            raw = post.get(f'{field}__{key}')
            if raw is not None:
                setattr(group, attr, raw)
        raw_date = post.get(f'date__{key}')
        if raw_date is not None:
            text = raw_date.strip()
            if not text:
                group.expected_date = None
            else:
                try:
                    group.expected_date = date.fromisoformat(text)
                except ValueError:
                    pass
        for ln in group.lines:
            qty_raw = post.get(f'qty__{ln.npl_line_id}')
            if qty_raw is not None and str(qty_raw).strip():
                try:
                    ln.qty = _parse_qty(qty_raw)
                except PlanningError:
                    pass
            price_raw = post.get(f'price__{ln.npl_line_id}')
            if price_raw is not None and str(price_raw).strip():
                try:
                    ln.unit_price = _parse_qty(price_raw)
                except PlanningError:
                    pass
            note_raw = post.get(f'note__{ln.npl_line_id}')
            if note_raw is not None:
                ln.note = note_raw


@transaction.atomic
def place_shortage_requests_from_post(*, order_id: int, post, user=None) -> list[SxNplPurchaseRequest]:
    """Một phiếu yêu cầu mua chờ xác nhận cho mỗi nhóm nhà cung cấp trên form."""
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

    from san_xuat.services.plan_order_npl import upsert_material_plan_from_order

    plan = upsert_material_plan_from_order(order, user=user)
    npl_by_id = {ln.pk: ln for ln in order.npl_lines.all()}
    created: list[SxNplPurchaseRequest] = []
    order_day = timezone.localdate()
    for key, line_ids in by_group.items():
        raw_supplier = (post.get(f'supplier__{key}') or '').strip()
        supplier_id = int(raw_supplier) if raw_supplier.isdigit() else 0
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
        pr = SxNplPurchaseRequest.objects.create(
            code=_code('npl_pr', SxNplPurchaseRequest),
            material_plan=plan,
            sales_order=order,
            request_date=order_day,
            due_date=expected,
            status=SxNplPurchaseRequest.STATUS_SUBMITTED,
            notes=order.code,
            payment_method=pay,
            is_demo=False,
            created_by=user if getattr(user, 'pk', None) else None,
        )
        SxNplPurchaseRequestLine.objects.bulk_create([
            SxNplPurchaseRequestLine(
                request=pr,
                material_code=chosen[line_id]['src'].material_code,
                material_name=chosen[line_id]['src'].material_name,
                qty=chosen[line_id]['qty'],
                need_date=npl_by_id[line_id].ready_date if line_id in npl_by_id else None,
                supplier=supplier,
                unit_price=chosen[line_id]['price'],
                expected_date=expected,
                payment_method=pay,
                notes=chosen[line_id]['note'],
            )
            for line_id in line_ids
        ])
        created.append(pr)
    sync_order_npl(order_id=order.pk)
    return created


@transaction.atomic
def update_open_purchase_request(*, request_id: int, post, user=None) -> SxNplPurchaseRequest:
    """Sửa đơn đặt hàng khi chưa xác nhận."""
    pr = (
        SxNplPurchaseRequest.objects.select_for_update()
        .prefetch_related('lines')
        .get(pk=request_id, is_demo=False)
    )
    if pr.status not in (
        SxNplPurchaseRequest.STATUS_DRAFT,
        SxNplPurchaseRequest.STATUS_SUBMITTED,
    ):
        raise PlanningError('Đơn đã xác nhận — không sửa được.')
    lines = list(pr.lines.all())
    if not lines:
        raise PlanningError('Đơn không có dòng hàng.')
    raw_supplier = (post.get('supplier') or '').strip()
    supplier_id = int(raw_supplier) if raw_supplier.isdigit() else 0
    supplier = Supplier.objects.filter(pk=supplier_id, is_active=True).first() if supplier_id else None
    if supplier is None:
        raise PlanningError('Chọn nhà cung cấp.')
    pay = (post.get('pay') or '').strip()
    if pay not in _PAYMENTS:
        pay = SxNplPurchaseRequest.PAYMENT_TRANSFER
    expected = _parse_date(post.get('date'))
    supplier.contact_name = (post.get('contact') or '').strip()[:120]
    supplier.phone = (post.get('phone') or '').strip()[:40]
    supplier.address = (post.get('address') or '').strip()[:255]
    supplier.tax_code = (post.get('tax') or '').strip()[:32]
    supplier.save(update_fields=['contact_name', 'phone', 'address', 'tax_code'])
    kept = 0
    for ln in lines:
        qty = _parse_qty(post.get(f'qty__{ln.pk}'))
        if qty <= 0:
            ln.delete()
            continue
        price = _parse_qty(post.get(f'price__{ln.pk}'))
        if price < 0:
            raise PlanningError('Đơn giá không được âm.')
        ln.qty = qty
        ln.unit_price = price
        ln.notes = (post.get(f'note__{ln.pk}') or '').strip()[:255]
        ln.supplier = supplier
        ln.expected_date = expected
        ln.payment_method = pay
        ln.save(update_fields=[
            'qty', 'unit_price', 'notes', 'supplier', 'expected_date', 'payment_method',
        ])
        kept += 1
    if not kept:
        raise PlanningError('Nhập số lượng đặt lớn hơn 0.')
    pr.due_date = expected
    pr.payment_method = pay
    pr.save(update_fields=['due_date', 'payment_method'])
    if pr.sales_order_id:
        sync_order_npl(order_id=pr.sales_order_id)
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
    order_day = timezone.localdate()
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
            po.order_date = po.order_date or order_day
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
                order_date=order_day,
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
    stamp = next((po.order_date for po in created if po.order_date), None)
    if stamp and pr.request_date != stamp:
        pr.request_date = stamp
        pr.save(update_fields=['request_date'])
    return created


@transaction.atomic
def create_shortage_requests_from_order(
    *,
    order_id: int,
    user=None,
    allocate_by_line: dict | None = None,
    buy_by_line: dict | None = None,
) -> tuple[list[SxNplPurchaseRequest], list[str]]:
    """Một YCM chờ xác nhận cho mỗi NCC, SL = phần thiếu còn đặt được."""
    order = sync_order_npl(
        order_id=order_id,
        allocate_by_line=allocate_by_line,
        buy_by_line=buy_by_line,
    )
    groups = build_shortage_preview(order)
    from san_xuat.services.plan_order_npl import upsert_material_plan_from_order

    plan = upsert_material_plan_from_order(order, user=user)
    npl_by_id = {ln.pk: ln for ln in order.npl_lines.all()}
    created: list[SxNplPurchaseRequest] = []
    missing: list[str] = []
    for group in groups:
        lines = [ln for ln in group.lines if ln.qty > 0]
        if not lines:
            continue
        supplier = (
            Supplier.objects.filter(pk=group.supplier_id, is_active=True).first()
            if group.supplier_id else None
        )
        if supplier is None:
            missing.extend((ln.material_name or ln.material_code) for ln in lines)
            continue
        due = group.expected_date
        pr = SxNplPurchaseRequest.objects.create(
            code=_code('npl_pr', SxNplPurchaseRequest),
            material_plan=plan,
            sales_order=order,
            request_date=timezone.localdate(),
            due_date=due,
            status=SxNplPurchaseRequest.STATUS_SUBMITTED,
            notes=order.code,
            payment_method=group.payment_method or SxNplPurchaseRequest.PAYMENT_TRANSFER,
            is_demo=False,
            created_by=user if getattr(user, 'pk', None) else None,
        )
        SxNplPurchaseRequestLine.objects.bulk_create([
            SxNplPurchaseRequestLine(
                request=pr,
                material_code=ln.material_code,
                material_name=ln.material_name,
                qty=ln.qty,
                need_date=(npl_by_id[ln.npl_line_id].ready_date if ln.npl_line_id in npl_by_id else None),
                supplier=supplier,
                unit_price=ln.unit_price,
                expected_date=group.expected_date,
                payment_method=group.payment_method,
                notes=ln.note,
            )
            for ln in lines
        ])
        created.append(pr)
    if not created:
        if missing:
            raise PlanningError('Chưa gán nhà cung cấp cho: ' + ', '.join(missing[:8]))
        raise PlanningError('Không còn NPL thiếu để đặt.')
    sync_order_npl(order_id=order.pk)
    return created, missing


@transaction.atomic
def confirm_purchase_requests(*, request_ids: list[int], user=None) -> list[SxPurchaseOrder]:
    """Duyệt YCM chờ xác nhận → tách đơn mua hàng theo NCC."""
    from san_xuat.services.planning import approve_npl_purchase_request, submit_npl_purchase_request

    pos: list[SxPurchaseOrder] = []
    seen: set[int] = set()
    ids = []
    for raw in request_ids or []:
        try:
            rid = int(raw)
        except (TypeError, ValueError):
            continue
        if rid and rid not in ids:
            ids.append(rid)
    for rid in ids:
        pr = SxNplPurchaseRequest.objects.filter(pk=rid, is_demo=False).first()
        if pr is None:
            continue
        if pr.status == SxNplPurchaseRequest.STATUS_DRAFT:
            pr = submit_npl_purchase_request(request_id=pr.pk)
        if pr.status == SxNplPurchaseRequest.STATUS_SUBMITTED:
            pr = approve_npl_purchase_request(request_id=pr.pk)
        for po in pr.purchase_orders.filter(is_demo=False).order_by('pk'):
            if po.pk not in seen:
                seen.add(po.pk)
                pos.append(po)
    if not pos:
        raise PlanningError('Không tạo được đơn mua hàng từ các yêu cầu đã chọn.')
    return pos


def list_npl_confirm_groups(*, order_id: int | None = None, stage: str = 'pending') -> list[dict]:
    """Phiếu yêu cầu mua, gom theo mã đơn. stage: pending | confirmed."""
    import json

    from san_xuat.services.products import product_gallery_map
    from san_xuat.services.sales_orders import normalize_size_qtys
    from san_xuat.templatetags.sx_format import format_sx_num

    pending = (
        SxNplPurchaseRequest.STATUS_DRAFT,
        SxNplPurchaseRequest.STATUS_SUBMITTED,
    )
    qs = (
        SxNplPurchaseRequest.objects.filter(is_demo=False)
        .exclude(status=SxNplPurchaseRequest.STATUS_REJECTED)
        .select_related('sales_order')
        .prefetch_related('lines__supplier', 'purchase_orders__lines', 'sales_order__lines')
        .order_by('-created_at', '-pk')
    )
    if stage == 'confirmed':
        qs = qs.filter(status=SxNplPurchaseRequest.STATUS_APPROVED)
    else:
        qs = qs.filter(status__in=pending)
    if order_id:
        qs = qs.filter(sales_order_id=order_id)
    buckets: dict[int, list[SxNplPurchaseRequest]] = defaultdict(list)
    order_by_id: dict[int, SxSalesOrder] = {}
    for pr in qs:
        oid = pr.sales_order_id or 0
        buckets[oid].append(pr)
        if pr.sales_order_id and pr.sales_order_id not in order_by_id:
            order_by_id[pr.sales_order_id] = pr.sales_order

    product_codes = [
        ln.product_code
        for order in order_by_id.values()
        for ln in order.lines.all()
    ]
    galleries = product_gallery_map(product_codes)
    mat_codes = [
        ln.material_code
        for prs in buckets.values()
        for pr in prs
        for ln in pr.lines.all()
    ]
    materials = {
        (m.code or '').strip().casefold(): m
        for m in Material.objects.filter(code__in=mat_codes)
    }

    groups: list[dict] = []
    for oid, prs in buckets.items():
        order = order_by_id.get(oid)
        products = []
        if order:
            for ln in order.lines.all():
                urls = galleries.get((ln.product_code or '').casefold()) or []
                sizes = normalize_size_qtys(ln.size_qtys)
                size_label = ' · '.join(
                    f'{size} {format_sx_num(qty)}' for size, qty in sizes.items()
                )
                products.append({
                    'code': ln.product_code,
                    'name': ln.product_name or ln.product_code,
                    'qty': ln.qty,
                    'size_label': size_label,
                    'image_url': urls[0] if urls else '',
                    'image_urls_json': json.dumps(urls, ensure_ascii=False),
                })
        tickets = []
        pending_ids = []
        for pr in prs:
            can_confirm = pr.status in pending
            if can_confirm:
                pending_ids.append(pr.pk)
            items = []
            suppliers: list[str] = []
            qty_total = Decimal('0')
            for ln in pr.lines.all():
                mat = materials.get((ln.material_code or '').strip().casefold())
                image_url = ''
                if mat and mat.image:
                    try:
                        image_url = mat.image.url
                    except (ValueError, OSError):
                        image_url = ''
                qty_total += _q(ln.qty)
                name = (ln.supplier.name if ln.supplier_id else '').strip()
                if name and name not in suppliers:
                    suppliers.append(name)
                items.append({
                    'material_code': ln.material_code,
                    'material_name': ln.material_name or ln.material_code,
                    'image_url': image_url,
                    'qty': ln.qty,
                })
            pos = [
                po for po in pr.purchase_orders.all()
                if not po.is_demo
            ]
            if pos and not can_confirm:
                for po in pos:
                    wanted = {
                        (ln.material_code or '').strip().casefold()
                        for ln in po.lines.all()
                    }
                    po_items = [
                        item for item in items
                        if (item['material_code'] or '').strip().casefold() in wanted
                    ] or items
                    po_qty = sum((_q(ln.qty_ordered) for ln in po.lines.all()), Decimal('0'))
                    tickets.append({
                        'id': pr.pk,
                        'po_id': po.pk,
                        'code': pr.code,
                        'supplier_name': (po.supplier_name or '').strip() or ' · '.join(suppliers),
                        'qty': po_qty or qty_total,
                        'line_count': len(po_items),
                        'items': po_items,
                        'can_confirm': False,
                        'status_label': pr.get_status_display(),
                        'purchase_orders': [po],
                        'receipt_id': None,
                        'receipt_number': '',
                        'receipt_open': False,
                    })
            else:
                tickets.append({
                    'id': pr.pk,
                    'po_id': 0,
                    'code': pr.code,
                    'supplier_name': ' · '.join(suppliers),
                    'qty': qty_total,
                    'line_count': len(items),
                    'items': items,
                    'can_confirm': can_confirm,
                    'status_label': pr.get_status_display(),
                    'purchase_orders': pos,
                    'receipt_id': None,
                    'receipt_number': '',
                    'receipt_open': False,
                })
        tickets.sort(key=lambda t: (0 if t['can_confirm'] else 1, -t['id']))
        groups.append({
            'order_id': oid,
            'order': order,
            'order_code': order.code if order else 'Không gắn đơn',
            'customer_name': (order.customer_name if order else '') or '',
            'due_date': order.due_date if order else None,
            'products': products,
            'tickets': tickets,
            'pending_ids': pending_ids,
        })
    groups.sort(key=lambda g: (0 if g['pending_ids'] else 1, -(g['tickets'][0]['id'] if g['tickets'] else 0)))
    _attach_ticket_receipts(groups)
    return groups


def _attach_ticket_receipts(groups: list[dict]) -> None:
    from kho_npl.choices import DOC_STATUS_CANCELLED, DOC_STATUS_POSTED
    from kho_npl.models import StockReceipt

    codes = [
        (po.code or '').strip()
        for group in groups
        for ticket in group['tickets']
        for po in ticket['purchase_orders']
        if (po.code or '').strip()
    ]
    if not codes:
        return
    by_po: dict[str, StockReceipt] = {}
    for rec in (
        StockReceipt.objects.filter(po_number__in=codes)
        .exclude(status=DOC_STATUS_CANCELLED)
        .order_by('id')
    ):
        by_po.setdefault((rec.po_number or '').strip(), rec)
    for group in groups:
        for ticket in group['tickets']:
            rec = next(
                (by_po.get((po.code or '').strip()) for po in ticket['purchase_orders'] if by_po.get((po.code or '').strip())),
                None,
            )
            if rec is None:
                continue
            ticket['receipt_id'] = rec.pk
            ticket['receipt_number'] = rec.number
            ticket['receipt_open'] = rec.status != DOC_STATUS_POSTED
