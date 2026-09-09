"""Kế hoạch NPL theo đơn trên KHSX — tồn, ngày mua tự nhập, cộng vào lịch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.models import Material
from kho_npl.services.reservation import material_available_qty
from kho_npl.services.stock import material_total_qty
from san_xuat.hub_models import (
    SxMaterialPlan,
    SxMaterialPlanLine,
    SxNplPurchaseRequest,
    SxOrderNplLine,
    SxOverallPlan,
    SxSalesOrder,
)
from san_xuat.services.bom_need import explode_for_sales_line
from san_xuat.services.plan_audit import log_plan_action
from san_xuat.services.planning import PlanningError, _code, _expected_inbound_qty, npl_prep_days
from san_xuat.services.work_calendar import add_working_days

_Q4 = Decimal('0.0001')


def _q(value, places: str = '0.0001') -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places))


def kit_days_for_order(order: SxSalesOrder) -> int:
    if order.npl_kit_days is not None:
        return int(order.npl_kit_days)
    return npl_prep_days()


def npl_anchor_for_order(order: SxSalesOrder, *, today: date | None = None) -> date:
    return order.npl_anchor or today or timezone.localdate()


def line_ready_date(
    *,
    anchor: date,
    kit_days: int,
    shortfall: Decimal,
    buy_lead_days: int | None,
) -> date:
    kit = max(0, int(kit_days or 0))
    if (shortfall or 0) > 0:
        buy = int(buy_lead_days or 0)
        inbound = anchor + timedelta(days=buy)
        return add_working_days(inbound, kit)
    return add_working_days(anchor, kit)


def total_npl_lead_days(*, lines, kit_days: int) -> int:
    """Tổng ngày NPL = cộng lead mua mọi mã thiếu + ngày chuẩn bị."""
    total_buy_days = sum(
        int(ln.buy_lead_days or 0)
        for ln in lines
        if (ln.qty_shortfall or 0) > 0
    )
    return total_buy_days + max(0, int(kit_days or 0))


def production_start_for_order(order: SxSalesOrder, *, today: date | None = None) -> date:
    """Neo ngày bắt đầu tổ SX = max(plan_start|request, npl_ready nếu đã tính)."""
    today = today or timezone.localdate()
    intent = order.plan_start_date or order.request_date or today
    if order.npl_status == SxSalesOrder.NPL_READY and order.npl_ready_date:
        return max(intent, order.npl_ready_date)
    return intent


@dataclass
class ExplodedNpl:
    material_code: str
    material_name: str
    unit: str
    qty_required: Decimal
    qty_on_hand: Decimal
    qty_available: Decimal
    qty_inbound: Decimal
    qty_shortfall: Decimal


def explode_order_npl_rows(order: SxSalesOrder) -> list[ExplodedNpl]:
    """Gộp nhu cầu NPL mọi dòng SP, đọc tồn kho_npl."""
    needed: dict[str, dict] = {}
    for ln in order.lines.all():
        if (ln.qty or 0) <= 0:
            continue
        for need in explode_for_sales_line(ln):
            code = (need.material_code or '').strip()
            if not code or need.qty_total <= 0:
                continue
            key = code.casefold()
            row = needed.get(key)
            if row is None:
                needed[key] = {
                    'code': code[:60],
                    'name': (need.material_name or code)[:255],
                    'unit': (need.unit or '')[:30],
                    'qty': _q(need.qty_total),
                }
            else:
                row['qty'] += _q(need.qty_total)
                if not row['name']:
                    row['name'] = (need.material_name or code)[:255]
                if not row['unit']:
                    row['unit'] = (need.unit or '')[:30]

    out: list[ExplodedNpl] = []
    for key in sorted(needed):
        rec = needed[key]
        mat = Material.objects.filter(code__iexact=rec['code'], is_active=True).first()
        on_hand = _q(material_total_qty(mat) if mat else 0)
        available = _q(material_available_qty(mat) if mat else 0)
        inbound = _q(_expected_inbound_qty(rec['code']))
        shortfall = max(Decimal('0'), rec['qty'] - available - inbound)
        out.append(ExplodedNpl(
            material_code=rec['code'],
            material_name=rec['name'],
            unit=rec['unit'],
            qty_required=rec['qty'].quantize(_Q4),
            qty_on_hand=on_hand,
            qty_available=available,
            qty_inbound=inbound,
            qty_shortfall=shortfall.quantize(_Q4),
        ))
    return out


def _apply_header_ready(
    order: SxSalesOrder,
    *,
    lines: list[SxOrderNplLine],
    kit_days: int,
    apply_schedule: bool,
    today: date,
) -> None:
    shorts = [ln for ln in lines if ln.qty_shortfall > 0]
    missing_buy = [ln for ln in shorts if ln.buy_lead_days is None]
    order.npl_short_count = len(shorts)
    if not apply_schedule or missing_buy:
        order.npl_status = SxSalesOrder.NPL_DRAFT if lines else SxSalesOrder.NPL_NONE
        order.npl_ready_date = None
        order.npl_lead_days = 0
        for ln in lines:
            ln.ready_date = None
            ln.save(update_fields=['ready_date'])
        order.save(update_fields=[
            'npl_status', 'npl_anchor', 'npl_kit_days', 'npl_ready_date',
            'npl_lead_days', 'npl_short_count', 'updated_at',
        ])
        return

    anchor = npl_anchor_for_order(order, today=today)
    for ln in lines:
        ready = line_ready_date(
            anchor=anchor,
            kit_days=kit_days,
            shortfall=ln.qty_shortfall,
            buy_lead_days=ln.buy_lead_days,
        )
        ln.ready_date = ready
        ln.save(update_fields=['ready_date'])

    # Kế hoạch tổng cộng dồn thời gian mua của mọi mã thiếu, sau đó mới
    # cộng thời gian chuẩn bị NPL.
    lead = total_npl_lead_days(lines=lines, kit_days=kit_days)
    kit = max(0, int(kit_days or 0))
    total_buy_days = max(0, lead - kit)
    npl_ready = add_working_days(
        anchor + timedelta(days=total_buy_days),
        kit,
    )
    order.npl_anchor = anchor
    order.npl_ready_date = npl_ready
    order.npl_lead_days = lead
    order.npl_status = SxSalesOrder.NPL_READY
    order.save(update_fields=[
        'npl_status', 'npl_anchor', 'npl_kit_days', 'npl_ready_date',
        'npl_lead_days', 'npl_short_count', 'updated_at',
    ])


@transaction.atomic
def sync_order_npl(
    *,
    order_id: int,
    kit_days: int | None = None,
    buy_by_line: dict[int, int | None] | None = None,
    apply_schedule: bool = False,
    refresh_stock: bool = True,
) -> SxSalesOrder:
    """Explode/làm mới dòng NPL; lưu ngày mua; tùy chọn cộng vào KHSX."""
    order = (
        SxSalesOrder.objects.select_for_update()
        .prefetch_related('lines', 'npl_lines')
        .get(pk=order_id, is_demo=False)
    )
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ lập kế hoạch NPL trên đơn đã xác nhận.')
    if order.plan_status == SxSalesOrder.PLAN_ON_HOLD:
        raise PlanningError('Đơn đang tạm giữ — bỏ giữ trước khi lập NPL.')

    today = timezone.localdate()
    if order.npl_anchor is None:
        order.npl_anchor = today

    rows = explode_order_npl_rows(order)
    if not rows:
        order.npl_lines.all().delete()
        order.npl_status = SxSalesOrder.NPL_NONE
        order.npl_ready_date = None
        order.npl_lead_days = 0
        order.npl_short_count = 0
        order.save(update_fields=[
            'npl_status', 'npl_ready_date', 'npl_lead_days', 'npl_short_count', 'updated_at',
        ])
        raise PlanningError('Chưa explode được NPL — gắn BOM trên đơn trước.')

    existing = {ln.material_code.casefold(): ln for ln in order.npl_lines.all()}
    keep_ids: list[int] = []
    seen: set[str] = set()
    sort = 0
    for rec in rows:
        key = rec.material_code.casefold()
        seen.add(key)
        sort += 10
        ln = existing.get(key)
        buy = ln.buy_lead_days if ln else None
        if buy_by_line is not None and ln and ln.pk in buy_by_line:
            buy = buy_by_line[ln.pk]
        if rec.qty_shortfall <= 0:
            buy = None
        if ln is None:
            ln = SxOrderNplLine(order=order, material_code=rec.material_code)
        ln.material_name = rec.material_name
        ln.unit = rec.unit
        if refresh_stock:
            ln.qty_required = rec.qty_required
            ln.qty_on_hand = rec.qty_on_hand
            ln.qty_available = rec.qty_available
            ln.qty_inbound = rec.qty_inbound
            ln.qty_shortfall = rec.qty_shortfall
        ln.buy_lead_days = buy
        ln.sort_order = sort
        ln.save()
        keep_ids.append(ln.pk)

    order.npl_lines.exclude(pk__in=keep_ids).delete()
    lines = list(order.npl_lines.order_by('sort_order', 'id'))

    if buy_by_line is not None:
        for ln in lines:
            if ln.pk in buy_by_line:
                ln.buy_lead_days = buy_by_line[ln.pk]
                if ln.qty_shortfall <= 0:
                    ln.buy_lead_days = None
                ln.save(update_fields=['buy_lead_days'])

    if kit_days is not None:
        kit = max(0, min(int(kit_days), 120))
        order.npl_kit_days = kit
    else:
        kit = kit_days_for_order(order)

    lines = list(order.npl_lines.order_by('sort_order', 'id'))
    if (
        not apply_schedule
        and buy_by_line is None
        and order.npl_status == SxSalesOrder.NPL_READY
    ):
        apply_schedule = True
    _apply_header_ready(
        order,
        lines=lines,
        kit_days=kit,
        apply_schedule=apply_schedule,
        today=today,
    )
    order.refresh_from_db()
    upsert_material_plan_from_order(order)
    return order


def active_material_plan_for_order(order: SxSalesOrder) -> SxMaterialPlan | None:
    """KH NPL đang sống gắn đơn — bỏ hủy / đã đóng."""
    return (
        SxMaterialPlan.objects.filter(sales_order=order, is_demo=False)
        .exclude(status__in=(SxOverallPlan.STATUS_CANCELLED, SxOverallPlan.STATUS_DONE))
        .order_by('-id')
        .first()
    )


@transaction.atomic
def upsert_material_plan_from_order(
    order: SxSalesOrder,
    *,
    code: str | None = None,
    name: str = '',
    user=None,
) -> SxMaterialPlan | None:
    """Đồng bộ phiếu KH NPL từ snapshot KHSX để menu Kế hoạch NPL nhìn thấy đơn."""
    lines = list(order.npl_lines.order_by('sort_order', 'id'))
    if not lines:
        return None

    plan = active_material_plan_for_order(order)
    created = False
    label = (name or '').strip() or (
        f"NPL {order.code}" + (f" — {order.customer_name}" if (order.customer_name or '').strip() else '')
    )
    if not plan:
        plan = SxMaterialPlan.objects.create(
            code=_code('plan_npl', SxMaterialPlan, code=code),
            name=label[:200],
            sales_order=order,
            status=SxOverallPlan.STATUS_DRAFT,
            is_demo=False,
        )
        created = True
    else:
        plan.lines.all().delete()
        if (name or '').strip() and plan.name != label[:200]:
            plan.name = label[:200]
            plan.save(update_fields=['name'])

    need_default = order.npl_ready_date
    SxMaterialPlanLine.objects.bulk_create(
        [
            SxMaterialPlanLine(
                plan=plan,
                material_code=ln.material_code,
                material_name=ln.material_name,
                qty_required=ln.qty_required,
                qty_on_hand=ln.qty_on_hand,
                qty_expected_inbound=ln.qty_inbound,
                qty_shortfall=ln.qty_shortfall,
                need_date=ln.ready_date or need_default,
            )
            for ln in lines
        ]
    )

    if plan.status == SxOverallPlan.STATUS_CONFIRMED:
        from kho_npl.services.reservation import upsert_reservations_for_khnvl

        upsert_reservations_for_khnvl(plan=plan.pk)

    log_plan_action(
        action='explode' if created else 'update',
        obj=plan,
        summary=(
            f"{'Tạo' if created else 'Cập nhật'} KH NPL {plan.code} từ KHSX {order.code}: "
            f"{len(lines)} mã."
        ),
        changes={'sales_order': order.code, 'lines': len(lines)},
        user=user,
    )
    return plan


@transaction.atomic
def build_pr_from_order(*, order_id: int, user=None) -> SxNplPurchaseRequest:
    """Tạo / làm mới YCM nháp từ shortfall trên đơn KHSX."""
    from san_xuat.services.planning import build_pr_from_material_plan

    order = sync_order_npl(order_id=order_id)
    shorts = [ln for ln in order.npl_lines.all() if ln.qty_shortfall > 0]
    if not shorts:
        raise PlanningError('Đơn không thiếu NPL — không tạo yêu cầu mua.')
    plan = upsert_material_plan_from_order(order, user=user)
    if plan is None:
        raise PlanningError('Chưa có dòng NPL trên đơn để tạo YCM.')
    return build_pr_from_material_plan(
        material_plan_id=plan.pk,
        only_shortfall=True,
        user=user,
    )


def npl_span_for_order(order: SxSalesOrder, *, today: date | None = None):
    """(start, end) thanh Chuẩn bị NPL — None nếu chưa cộng lịch hoặc lead 0."""
    if order.npl_status != SxSalesOrder.NPL_READY:
        return None
    if not order.npl_ready_date or (order.npl_lead_days or 0) <= 0:
        return None
    start = npl_anchor_for_order(order, today=today)
    end = order.npl_ready_date
    if end < start:
        return None
    return start, end
