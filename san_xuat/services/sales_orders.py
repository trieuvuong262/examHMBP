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
) -> SxSalesOrder:
    req = request_date or timezone.localdate()
    order = SxSalesOrder.objects.create(
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
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id)
    if order.confirm_status != SxSalesOrder.CONFIRM_DRAFT:
        raise PlanningError('Chỉ sửa đơn khi đang nháp / chưa xác nhận.')
    order.customer_name = (customer_name or '').strip()[:255]
    if request_date:
        order.request_date = request_date
    order.due_date = due_date
    order.notes = (notes or '').strip()
    order.save(update_fields=['customer_name', 'request_date', 'due_date', 'notes', 'updated_at'])
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
        rows.append(
            SxSalesOrderLine(
                order=order,
                product_code=code[:60],
                product_name=_resolve_name(code, ln.product_name),
                qty=qty,
                qty_scrap_rate=_q(ln.qty_scrap_rate),
                uom=(ln.uom or '').strip()[:30],
                due_date=ln.due_date or order.due_date,
                sort_order=i,
            )
        )
    if not rows:
        raise PlanningError('Đơn phải có ít nhất một dòng sản phẩm hợp lệ.')
    SxSalesOrderLine.objects.bulk_create(rows)


@transaction.atomic
def confirm_sales_order(*, order_id: int) -> SxSalesOrder:
    order = SxSalesOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id)
    if order.confirm_status == SxSalesOrder.CONFIRM_CONFIRMED:
        return order
    if order.confirm_status == SxSalesOrder.CONFIRM_REJECTED:
        raise PlanningError('Đơn đã từ chối — không xác nhận lại được.')
    if not order.lines.exists():
        raise PlanningError('Đơn chưa có dòng sản phẩm.')
    order.confirm_status = SxSalesOrder.CONFIRM_CONFIRMED
    order.reject_reason = ''
    order.save(update_fields=['confirm_status', 'reject_reason', 'updated_at'])
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
    order.save(update_fields=['confirm_status', 'reject_reason', 'updated_at'])
    return order


@transaction.atomic
def import_from_kv_orders(*, kv_order_ids: list[int], user=None) -> list[SxSalesOrder]:
    """Tạo / cập nhật ĐĐH Portal từ đơn KiotViet (chỉ khi chưa confirmed khác nguồn)."""
    ids = [int(x) for x in (kv_order_ids or []) if str(x).strip().isdigit()]
    if not ids:
        raise PlanningError('Chưa chọn đơn KiotViet nào.')
    try:
        from kiotviet.models import KvOrder, KvOrderLine
        from kiotviet.sync_service import current_retailer
    except Exception as exc:
        raise PlanningError('Chưa cấu hình kết nối KiotViet.') from exc

    retailer = current_retailer()
    orders = {
        o.kiotviet_id: o
        for o in KvOrder.objects.filter(retailer=retailer, kiotviet_id__in=ids)
    }
    missing = [str(i) for i in ids if i not in orders]
    if missing:
        raise PlanningError(f'Không tìm thấy đơn KV: {", ".join(missing[:8])}')

    created: list[SxSalesOrder] = []
    for kid in ids:
        kv = orders[kid]
        lines_kv = list(
            KvOrderLine.objects.filter(retailer=retailer, order_kiotviet_id=kid).order_by('id')
        )
        line_inputs: list[LineInput] = []
        for ln in lines_kv:
            code = (ln.product_code or '').strip()
            qty = _q(ln.quantity)
            if not code or qty <= 0:
                continue
            line_inputs.append(
                LineInput(
                    product_code=code,
                    product_name=(ln.product_name or '').strip(),
                    qty=qty,
                )
            )
        if not line_inputs:
            continue

        pd = getattr(kv, 'purchase_date', None)
        req = pd.date() if hasattr(pd, 'date') and pd else (pd if isinstance(pd, date) else timezone.localdate())
        existing = SxSalesOrder.objects.filter(kv_order_kiotviet_id=kid).first()
        if existing:
            if existing.confirm_status != SxSalesOrder.CONFIRM_DRAFT:
                created.append(existing)
                continue
            update_draft_sales_order(
                order_id=existing.pk,
                customer_name=getattr(kv, 'customer_name', '') or '',
                request_date=req,
                due_date=req,
                notes=existing.notes,
                lines=line_inputs,
            )
            existing.source = SxSalesOrder.SOURCE_KIOTVIET
            existing.kv_order_code = (kv.code or '')[:64]
            existing.save(update_fields=['source', 'kv_order_code', 'updated_at'])
            created.append(existing)
        else:
            so = create_sales_order(
                customer_name=getattr(kv, 'customer_name', '') or '',
                request_date=req,
                due_date=req,
                lines=line_inputs,
                user=user,
                source=SxSalesOrder.SOURCE_KIOTVIET,
                kv_order_kiotviet_id=kid,
                kv_order_code=(kv.code or '')[:64],
            )
            created.append(so)
    if not created:
        raise PlanningError('Không import được đơn nào (thiếu dòng hàng).')
    return created


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
