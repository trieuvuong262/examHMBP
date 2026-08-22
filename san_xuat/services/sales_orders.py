"""Đơn đặt hàng sản xuất (SoT Portal) — CRUD, import KV, nạp MTO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from san_xuat.hub_models import (
    SxOverallPlan,
    SxOverallPlanLine,
    SxProductionOrder,
    SxSalesOrder,
    SxSalesOrderLine,
)
from san_xuat.services.planning import PlanningError, _next_code
from san_xuat.services.products import resolve_product_ref

_Q = Decimal('0.01')


def _q(value) -> Decimal:
    return (Decimal(str(value or 0))).quantize(_Q)


def _resolve_name(code: str, fallback: str = '') -> str:
    name = (fallback or '').strip()
    if name:
        return name[:255]
    ref = resolve_product_ref(code)
    return (ref.name if ref else '')[:255]


@dataclass
class LineInput:
    product_code: str
    qty: Decimal
    product_name: str = ''
    qty_scrap_rate: Decimal = Decimal('0')
    uom: str = ''
    due_date: date | None = None
    size_qtys: dict | None = None
    bom_version_id: int | None = None
    routing_id: int | None = None
    applied_smv: list | None = None
    applied_bom: list | None = None


def normalize_size_qtys(raw) -> dict[str, Decimal]:
    """Chuẩn hóa map size → SL (bỏ size ≤ 0)."""
    if not raw:
        return {}
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Decimal] = {}
    for key, val in raw.items():
        size = str(key or '').strip()
        if not size:
            continue
        qty = _q(val)
        if qty > 0:
            out[size] = qty
    return out


def _normalize_bom_overrides(raw) -> list[dict]:
    """Chuẩn hóa snapshot NPL trên đơn từ form lên đơn."""
    if not raw:
        return []
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            bom_line_id = int(row.get('bom_line_id') or row.get('id') or 0)
        except (TypeError, ValueError):
            bom_line_id = 0
        qty = _q(row.get('qty'))
        scrap = _q(row.get('scrap_pct'))
        code = str(row.get('material_code') or '').strip()[:60]
        name = str(row.get('material_name') or '').strip()[:255]
        unit = str(row.get('unit') or '').strip()[:30]
        size_code = str(row.get('size_code') or '').strip()[:20]
        qty_std = _q(row.get('qty_std') if row.get('qty_std') is not None else row.get('qty'))
        if bom_line_id <= 0 and not code:
            continue
        out.append({
            'bom_line_id': bom_line_id or None,
            'material_code': code,
            'material_name': name,
            'qty': float(qty),
            'qty_std': float(qty_std),
            'scrap_pct': float(scrap),
            'unit': unit,
            'size_code': size_code,
        })
    return out


def bom_lines_snapshot(bom_id: int | None) -> list[dict]:
    """Snapshot NPL từ phiên bản BOM (định mức gốc)."""
    if not bom_id:
        return []
    from san_xuat.models import BomVersion

    bom = (
        BomVersion.objects.filter(pk=bom_id)
        .prefetch_related('lines__material__unit')
        .first()
    )
    if bom is None:
        return []
    out: list[dict] = []
    for line in bom.lines.select_related('material', 'material__unit').order_by('sort_order', 'pk'):
        mat = line.material
        unit = ''
        if mat and mat.unit_id:
            unit = (mat.unit.code or mat.unit.name or '')[:30]
        qty = _q(line.qty)
        out.append({
            'bom_line_id': line.pk,
            'material_code': (mat.code if mat else '')[:60],
            'material_name': (mat.name if mat else '')[:255],
            'qty': float(qty),
            'qty_std': float(qty),
            'scrap_pct': float(_q(line.scrap_pct)),
            'unit': unit,
            'size_code': (line.size_code or '')[:20],
        })
    return out


@dataclass
class SalesOrderOption:
    id: int
    code: str
    customer_name: str
    request_date: date | None
    due_date: date | None
    line_count: int
    total_qty: Decimal


def next_sales_order_code() -> str:
    return _next_code('DH', SxSalesOrder)


@transaction.atomic
def create_sales_order(
    *,
    customer_name: str = '',
    request_date: date | None = None,
    due_date: date | None = None,
    notes: str = '',
    lines: list[LineInput] | None = None,
    user=None,
    code: str = '',
    source: str = SxSalesOrder.SOURCE_MANUAL,
    kv_order_kiotviet_id: int | None = None,
    kv_order_code: str = '',
    attachment=None,
) -> SxSalesOrder:
    req = request_date or timezone.localdate()
    order = SxSalesOrder(
        code=(code or '').strip() or next_sales_order_code(),
        customer_name=(customer_name or '').strip()[:255],
        request_date=req,
        due_date=due_date,
        notes=(notes or '').strip(),
        source=source or SxSalesOrder.SOURCE_MANUAL,
        kv_order_kiotviet_id=kv_order_kiotviet_id,
        kv_order_code=(kv_order_code or '').strip()[:64],
        confirm_status=SxSalesOrder.CONFIRM_DRAFT,
        created_by=user if getattr(user, 'is_authenticated', False) else None,
        is_demo=False,
    )
    if attachment is not None:
        order.attachment = attachment
    order.save()
    if lines:
        _replace_lines(order, lines)
    return order


@transaction.atomic
def update_draft_sales_order(
    *,
    order_id: int,
    customer_name: str = '',
    request_date: date | None = None,
    due_date: date | None = None,
    notes: str = '',
    lines: list[LineInput] | None = None,
) -> SxSalesOrder:
    """Tương thích cũ — ủy quyền sang ``update_sales_order``."""
    return update_sales_order(
        order_id=order_id,
        customer_name=customer_name,
        request_date=request_date,
        due_date=due_date,
        notes=notes,
        lines=lines,
    )


def sales_order_is_editable(order: SxSalesOrder) -> bool:
    """Sửa được khi chưa có lệnh SX còn hiệu lực (chưa sản xuất)."""
    for mo in related_mos(order):
        if mo.status != SxProductionOrder.STATUS_CANCELLED:
            return False
    return True


@transaction.atomic
def update_sales_order(
    *,
    order_id: int,
    customer_name: str = '',
    request_date: date | None = None,
    due_date: date | None = None,
    notes: str = '',
    lines: list[LineInput] | None = None,
    code: str = '',
    attachment=None,
) -> SxSalesOrder:
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if not sales_order_is_editable(order):
        raise PlanningError('Đơn đã vào sản xuất — không sửa được.')
    new_code = (code or '').strip()
    if new_code and new_code != order.code:
        if SxSalesOrder.objects.filter(code=new_code).exclude(pk=order.pk).exists():
            raise PlanningError(f'Số đơn «{new_code}» đã tồn tại.')
        order.code = new_code[:40]
    order.customer_name = (customer_name or '').strip()[:255]
    if request_date:
        order.request_date = request_date
    order.due_date = due_date
    order.notes = (notes or '').strip()
    update_fields = ['code', 'customer_name', 'request_date', 'due_date', 'notes', 'updated_at']
    if attachment is not None:
        order.attachment = attachment
        update_fields.append('attachment')
    order.save(update_fields=update_fields)
    if lines is not None:
        _replace_lines(order, lines)
    return order


def _replace_lines(order: SxSalesOrder, lines: list[LineInput]) -> None:
    order.lines.all().delete()
    rows: list[SxSalesOrderLine] = []
    for i, ln in enumerate(lines):
        code = (ln.product_code or '').strip()
        qty = _q(ln.qty)
        if not code or qty <= 0:
            continue
        size_map = normalize_size_qtys(getattr(ln, 'size_qtys', None))
        bom_id = getattr(ln, 'bom_version_id', None) or None
        routing_id = getattr(ln, 'routing_id', None) or None
        try:
            bom_id = int(bom_id) if bom_id else None
        except (TypeError, ValueError):
            bom_id = None
        try:
            routing_id = int(routing_id) if routing_id else None
        except (TypeError, ValueError):
            routing_id = None
        bom_overrides = _normalize_bom_overrides(getattr(ln, 'applied_bom', None))
        if not bom_overrides and bom_id:
            bom_overrides = bom_lines_snapshot(bom_id)
        rows.append(
            SxSalesOrderLine(
                order=order,
                product_code=code[:60],
                product_name=_resolve_name(code, ln.product_name),
                qty=qty,
                size_qtys={k: float(v) for k, v in size_map.items()},
                bom_version_id=bom_id,
                routing_id=routing_id,
                bom_line_overrides=bom_overrides,
                qty_scrap_rate=_q(ln.qty_scrap_rate),
                uom=(ln.uom or '').strip()[:30],
                due_date=ln.due_date or order.due_date,
                sort_order=i,
            )
        )
    if not rows:
        raise PlanningError('Đơn phải có ít nhất một dòng sản phẩm hợp lệ.')
    SxSalesOrderLine.objects.bulk_create(rows)
    from san_xuat.services.order_routing import apply_smv_overrides, seed_order_routing

    seed_order_routing(order)
    smv_by_code: dict[str, list] = {}
    for ln in lines:
        code = (ln.product_code or '').strip().casefold()
        if code and getattr(ln, 'applied_smv', None):
            smv_by_code[code] = ln.applied_smv
    if smv_by_code:
        for so_ln in order.lines.all():
            ov = smv_by_code.get((so_ln.product_code or '').strip().casefold())
            if ov:
                apply_smv_overrides(so_ln, ov)


@transaction.atomic
def confirm_sales_order(*, order_id: int, user=None) -> SxSalesOrder:
    order = SxSalesOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    if order.confirm_status == SxSalesOrder.CONFIRM_CONFIRMED:
        return order
    if order.confirm_status == SxSalesOrder.CONFIRM_REJECTED:
        raise PlanningError('Đơn đã từ chối — không xác nhận lại được.')
    if not order.lines.exists():
        raise PlanningError('Đơn chưa có dòng sản phẩm.')
    from san_xuat.services.order_routing import assert_order_ready_to_confirm

    assert_order_ready_to_confirm(order)
    order.confirm_status = SxSalesOrder.CONFIRM_CONFIRMED
    order.reject_reason = ''
    order.confirmed_at = timezone.now()
    order.confirmed_by = user if getattr(user, 'is_authenticated', False) else None
    order.plan_status = SxSalesOrder.PLAN_QUEUED
    if not order.plan_queued_at:
        order.plan_queued_at = timezone.now()
    order.plan_hold_reason = ''
    order.save(update_fields=[
        'confirm_status', 'reject_reason', 'confirmed_at', 'confirmed_by',
        'plan_status', 'plan_queued_at', 'plan_hold_reason', 'updated_at',
    ])
    return order


@transaction.atomic
def reject_sales_order(*, order_id: int, reason: str = '') -> SxSalesOrder:
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id)
    if order.confirm_status == SxSalesOrder.CONFIRM_REJECTED:
        return order
    # Cho phép từ chối cả confirmed nếu chưa gắn KHTT/LSX
    if order.overall_plan_lines.exists() or order.production_orders.exists():
        raise PlanningError('Đơn đã gắn kế hoạch / lệnh SX — không thể từ chối.')
    order.confirm_status = SxSalesOrder.CONFIRM_REJECTED
    order.reject_reason = (reason or '').strip()[:500]
    order.confirmed_at = None
    order.confirmed_by = None
    order.save(update_fields=[
        'confirm_status', 'reject_reason', 'confirmed_at', 'confirmed_by', 'updated_at',
    ])
    return order


def list_confirmed_orders_for_mto(*, limit: int = 100, search: str = '') -> list[SalesOrderOption]:
    qs = (
        SxSalesOrder.objects.filter(
            is_demo=False,
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        )
        .annotate(
            line_count=Count('lines'),
            total_qty=Sum('lines__qty'),
        )
        .order_by('-request_date', '-id')
    )
    term = (search or '').strip()
    if term:
        qs = qs.filter(
            Q(code__icontains=term)
            | Q(customer_name__icontains=term)
            | Q(kv_order_code__icontains=term)
        )
    out: list[SalesOrderOption] = []
    for o in qs[:limit]:
        if (o.line_count or 0) <= 0:
            continue
        out.append(
            SalesOrderOption(
                id=o.pk,
                code=o.code,
                customer_name=o.customer_name or '',
                request_date=o.request_date,
                due_date=o.due_date,
                line_count=int(o.line_count or 0),
                total_qty=_q(o.total_qty),
            )
        )
    return out


def collect_mto_demand_from_sales_orders(*, sales_order_ids: list[int]):
    """Gom dòng ĐĐH Portal thành DemandItem (SL = qty_to_produce)."""
    from san_xuat.services.demand import DemandItem

    ids = [int(x) for x in (sales_order_ids or []) if str(x).strip().isdigit()]
    if not ids:
        raise PlanningError('Chưa chọn đơn đặt hàng nào.')

    orders = {
        o.pk: o
        for o in SxSalesOrder.objects.filter(
            pk__in=ids,
            is_demo=False,
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        ).prefetch_related('lines')
    }
    missing = [str(i) for i in ids if i not in orders]
    if missing:
        raise PlanningError(
            f'Đơn không hợp lệ hoặc chưa xác nhận: {", ".join(missing[:8])}'
        )

    items: list[DemandItem] = []
    for oid in ids:
        order = orders[oid]
        for ln in order.lines.all():
            code = (ln.product_code or '').strip()
            qty = _q(ln.qty_to_produce)
            if not code or qty <= 0:
                continue
            items.append(
                DemandItem(
                    product_code=code,
                    product_name=ln.product_name or '',
                    qty_gross=qty,
                    due_date=ln.due_date or order.due_date,
                    kv_order_code=order.code,
                    kv_order_kiotviet_id=order.kv_order_kiotviet_id,
                    sales_order_id=order.pk,
                )
            )
    if not items:
        raise PlanningError('Các đơn đã chọn không có dòng hàng hợp lệ.')
    return items


def related_overall_plans(order: SxSalesOrder) -> list[SxOverallPlan]:
    plan_ids = set(
        SxOverallPlanLine.objects.filter(sales_order=order)
        .values_list('plan_id', flat=True)
    )
    if order.code:
        plan_ids |= set(
            SxOverallPlanLine.objects.filter(kv_order_code__icontains=order.code)
            .values_list('plan_id', flat=True)
        )
    if order.kv_order_code:
        plan_ids |= set(
            SxOverallPlanLine.objects.filter(kv_order_code__icontains=order.kv_order_code)
            .values_list('plan_id', flat=True)
        )
    if not plan_ids:
        return []
    return list(
        SxOverallPlan.objects.filter(pk__in=plan_ids, is_demo=False).order_by('-date_from', 'code')
    )


def related_mos(order: SxSalesOrder) -> list[SxProductionOrder]:
    plan_ids = [p.pk for p in related_overall_plans(order)]
    qs = SxProductionOrder.objects.filter(is_demo=False).filter(
        Q(sales_order=order)
        | Q(detail_plan__overall_plan_id__in=plan_ids)
    )
    return list(qs.select_related('detail_plan').distinct().order_by('-order_date', 'code')[:80])


def production_status_summary(order: SxSalesOrder) -> str:
    """Chip TT SX suy từ LSX liên quan."""
    mos = related_mos(order)
    if not mos:
        if order.confirm_status == SxSalesOrder.CONFIRM_DRAFT:
            return 'chua_xac_nhan'
        if order.confirm_status == SxSalesOrder.CONFIRM_REJECTED:
            return 'tu_choi'
        return 'chua_sx'
    statuses = {m.status for m in mos}
    if statuses <= {SxProductionOrder.STATUS_DONE, SxProductionOrder.STATUS_CANCELLED} and (
        SxProductionOrder.STATUS_DONE in statuses
    ):
        open_or_active = [
            m for m in mos
            if m.status not in (SxProductionOrder.STATUS_DONE, SxProductionOrder.STATUS_CANCELLED)
        ]
        if not open_or_active:
            return 'hoan_thanh'
    if SxProductionOrder.STATUS_IN_PROGRESS in statuses:
        return 'dang_sx'
    if SxProductionOrder.STATUS_RELEASED in statuses or SxProductionOrder.STATUS_DRAFT in statuses:
        return 'chua_du_lenh'
    return 'chua_sx'


PROD_STATUS_LABELS = {
    'chua_xac_nhan': 'Chưa xác nhận',
    'tu_choi': 'Từ chối',
    'chua_sx': 'Chưa sản xuất',
    'chua_du_lenh': 'Chưa lập đủ lệnh',
    'dang_sx': 'Đang sản xuất',
    'hoan_thanh': 'Hoàn thành',
}
