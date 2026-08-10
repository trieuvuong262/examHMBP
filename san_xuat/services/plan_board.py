"""Kế hoạch sản xuất theo đơn (MTO board) — hàng đợi, xếp hạng, chuyển LSX.

Phase 1: chỉ ĐĐH đã xác nhận. MTS/MPS swimlane sau.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch, Sum
from django.utils import timezone

from san_xuat.hub_models import SxProductionOrder, SxSalesOrder, SxSalesOrderLine, SxWorkCenter
from san_xuat.services.dispatch import DispatchError, create_mo_from_bom
from san_xuat.services.planning import PlanningError
from san_xuat.services.scheduling import product_routing

_Q2 = Decimal('0.01')

PRIORITY_WEIGHT = {
    SxSalesOrder.PRIORITY_CRITICAL: Decimal('5000'),
    SxSalesOrder.PRIORITY_URGENT: Decimal('2000'),
    SxSalesOrder.PRIORITY_HIGH: Decimal('1000'),
    SxSalesOrder.PRIORITY_NORMAL: Decimal('100'),
    SxSalesOrder.PRIORITY_LOW: Decimal('10'),
}

# Màu mức độ gấp (board ticket / badge) — đồng bộ CSS `.jp-pb-urgency` / `.jp-pb-ticket.is-*`
PRIORITY_COLORS = {
    SxSalesOrder.PRIORITY_CRITICAL: '#991b1b',  # đỏ đậm
    SxSalesOrder.PRIORITY_URGENT: '#c2410c',    # cam
    SxSalesOrder.PRIORITY_HIGH: '#a16207',      # vàng hổ phách
    SxSalesOrder.PRIORITY_NORMAL: '#0369a1',    # xanh
    SxSalesOrder.PRIORITY_LOW: '#64748b',       # xám
}

PLAN_STATUS_LABELS = dict(SxSalesOrder.PLAN_STATUS_CHOICES)
PRIORITY_LABELS = dict(SxSalesOrder.PRIORITY_CHOICES)

# Trạng thái còn trong hàng đợi / xếp (chưa chuyển SX)
QUEUE_STATUSES = (
    SxSalesOrder.PLAN_QUEUED,
    SxSalesOrder.PLAN_RANKED,
    SxSalesOrder.PLAN_ON_HOLD,
)

ACTIVE_MO_STATUSES = (
    SxProductionOrder.STATUS_DRAFT,
    SxProductionOrder.STATUS_RELEASED,
    SxProductionOrder.STATUS_IN_PROGRESS,
    SxProductionOrder.STATUS_DONE,
)


def _q(value, places: str = '0.01') -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places))


@dataclass
class PlanBoardRow:
    order: SxSalesOrder
    total_qty: Decimal
    line_count: int
    process_names: list[str] = field(default_factory=list)
    cycle_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    has_routing: bool = False
    score: Decimal = field(default_factory=lambda: Decimal('0'))
    days_to_due: int | None = None
    is_overdue: bool = False
    mo_count: int = 0
    mo_open: int = 0
    qty_done: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_planned: Decimal = field(default_factory=lambda: Decimal('0'))
    progress_pct: Decimal = field(default_factory=lambda: Decimal('0'))
    eta_date: date | None = None
    derived_status: str = SxSalesOrder.PLAN_QUEUED
    release_products: list[dict] = field(default_factory=list)
    release_script_id: str = ''


def enqueue_on_confirm(order: SxSalesOrder) -> None:
    """Gọi khi ĐĐH vừa xác nhận — đưa vào hàng đợi kế hoạch."""
    if order.plan_status in (
        SxSalesOrder.PLAN_RELEASED,
        SxSalesOrder.PLAN_IN_PROGRESS,
        SxSalesOrder.PLAN_DONE,
    ):
        return
    order.plan_status = SxSalesOrder.PLAN_QUEUED
    if not order.plan_queued_at:
        order.plan_queued_at = timezone.now()
    order.plan_hold_reason = ''
    order.save(update_fields=[
        'plan_status', 'plan_queued_at', 'plan_hold_reason', 'updated_at',
    ])


def derive_plan_status(order: SxSalesOrder, mos: list[SxProductionOrder] | None = None) -> str:
    if order.plan_status == SxSalesOrder.PLAN_ON_HOLD:
        return SxSalesOrder.PLAN_ON_HOLD
    if mos is None:
        mos = list(
            order.production_orders.filter(is_demo=False).exclude(
                status=SxProductionOrder.STATUS_CANCELLED,
            )
        )
    else:
        mos = [m for m in mos if m.status != SxProductionOrder.STATUS_CANCELLED]
    if mos:
        statuses = {m.status for m in mos}
        if statuses <= {SxProductionOrder.STATUS_DONE}:
            return SxSalesOrder.PLAN_DONE
        if SxProductionOrder.STATUS_IN_PROGRESS in statuses:
            return SxSalesOrder.PLAN_IN_PROGRESS
        return SxSalesOrder.PLAN_RELEASED
    if order.plan_rank is not None and order.plan_status != SxSalesOrder.PLAN_ON_HOLD:
        return SxSalesOrder.PLAN_RANKED
    return SxSalesOrder.PLAN_QUEUED


def sync_plan_status(order: SxSalesOrder) -> str:
    """Đồng bộ plan_status từ LSX (không đè on_hold)."""
    if order.plan_status == SxSalesOrder.PLAN_ON_HOLD:
        return order.plan_status
    derived = derive_plan_status(order)
    if derived != order.plan_status:
        order.plan_status = derived
        order.save(update_fields=['plan_status', 'updated_at'])
    return derived


def _enrich_routing(order: SxSalesOrder, lines: list[SxSalesOrderLine]) -> tuple[list[str], Decimal, bool]:
    names: list[str] = []
    seen: set[str] = set()
    total_min = Decimal('0')
    has_any = False
    for ln in lines:
        routing = product_routing(ln.product_code)
        qty = ln.qty_to_produce
        if routing.has_time_data:
            has_any = True
            total_min += (routing.total_smv * qty).quantize(_Q2)
        for step in routing.steps:
            n = (step.process_name or '').strip()
            if n and n not in seen:
                seen.add(n)
                names.append(n)
    return names, _q(total_min), has_any


def compute_score(
    *,
    order: SxSalesOrder,
    cycle_minutes: Decimal,
    today: date | None = None,
) -> tuple[Decimal, int | None, bool]:
    """Điểm xếp hạng (cao hơn = nên làm trước)."""
    today = today or timezone.localdate()
    due = order.due_date
    days_to_due: int | None = None
    is_overdue = False
    urgency = Decimal('0')
    if due:
        days_to_due = (due - today).days
        is_overdue = days_to_due < 0
        # Trễ: cộng mạnh; còn hạn: càng gần hạn càng cao
        urgency = Decimal(str(-days_to_due)) * Decimal('15')

    prio = PRIORITY_WEIGHT.get(order.plan_priority, PRIORITY_WEIGHT[SxSalesOrder.PRIORITY_NORMAL])
    # Chu kỳ dài hơn → hơi giảm (ưu tiên đơn ngắn trước khi hòa)
    cycle_penalty = min(_q(cycle_minutes) / Decimal('60'), Decimal('50'))
    # FIFO: đơn vào sớm hơn được cộng nhẹ
    fifo = Decimal('0')
    if order.plan_queued_at:
        age_hours = (timezone.now() - order.plan_queued_at).total_seconds() / 3600.0
        fifo = Decimal(str(min(age_hours, 240))) * Decimal('0.1')

    score = prio + urgency - cycle_penalty + fifo
    return _q(score), days_to_due, is_overdue


def _mo_progress(mos: list[SxProductionOrder]) -> tuple[int, int, Decimal, Decimal, Decimal]:
    active = [m for m in mos if m.status != SxProductionOrder.STATUS_CANCELLED]
    open_mos = [
        m for m in active
        if m.status != SxProductionOrder.STATUS_DONE
    ]
    qty_planned = sum((m.qty or Decimal('0') for m in active), Decimal('0'))
    qty_done = sum((m.qty_done or Decimal('0') for m in active), Decimal('0'))
    pct = Decimal('0')
    if qty_planned > 0:
        pct = (qty_done / qty_planned * Decimal('100')).quantize(_Q2)
    return len(active), len(open_mos), _q(qty_planned), _q(qty_done), pct


def build_plan_board_rows(
    *,
    statuses: tuple[str, ...] | None = None,
    search: str = '',
    include_released: bool = False,
) -> list[PlanBoardRow]:
    """Danh sách đơn trên board (MTO confirmed)."""
    qs = (
        SxSalesOrder.objects.filter(
            is_demo=False,
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        )
        .prefetch_related(
            Prefetch('lines', queryset=SxSalesOrderLine.objects.order_by('sort_order', 'id')),
            Prefetch(
                'production_orders',
                queryset=SxProductionOrder.objects.filter(is_demo=False).order_by('-order_date', 'code'),
            ),
        )
    )
    if statuses:
        qs = qs.filter(plan_status__in=statuses)
    elif not include_released:
        qs = qs.filter(plan_status__in=QUEUE_STATUSES)

    term = (search or '').strip()
    if term:
        from django.db.models import Q

        qs = qs.filter(
            Q(code__icontains=term)
            | Q(customer_name__icontains=term)
        )

    today = timezone.localdate()
    rows: list[PlanBoardRow] = []
    for order in qs:
        lines = list(order.lines.all())
        mos = list(order.production_orders.all())
        total_qty = sum((ln.qty_to_produce for ln in lines), Decimal('0'))
        names, cycle_min, has_routing = _enrich_routing(order, lines)
        score, days_to_due, is_overdue = compute_score(
            order=order, cycle_minutes=cycle_min, today=today,
        )
        mo_count, mo_open, qty_planned, qty_done, pct = _mo_progress(mos)
        derived = derive_plan_status(order, mos)
        eta = None
        if order.due_date:
            eta = order.due_date
        elif cycle_min > 0:
            # ETA thô: hôm nay + ceil(cycle_hours/8)
            hours = float(cycle_min) / 60.0
            days_need = max(1, int((hours / 8.0) + 0.999))
            eta = today + timedelta(days=days_need)

        # Gom mã SP unique cho modal Chuyển SX (chọn BOM) — kèm mặc định từ ĐĐH
        release_products: list[dict] = []
        seen_codes: set[str] = set()
        for ln in lines:
            if (ln.qty or 0) <= 0:
                continue
            code = (ln.product_code or '').strip()
            key = code.casefold()
            if not code or key in seen_codes:
                continue
            seen_codes.add(key)
            release_products.append({
                'code': code,
                'name': (ln.product_name or '').strip(),
                'qty': str(ln.qty_to_produce),
                'bom_version_id': ln.bom_version_id or None,
                'routing_id': ln.routing_id or None,
            })

        rows.append(PlanBoardRow(
            order=order,
            total_qty=_q(total_qty),
            line_count=len(lines),
            process_names=names[:12],
            cycle_minutes=cycle_min,
            has_routing=has_routing,
            score=score,
            days_to_due=days_to_due,
            is_overdue=is_overdue,
            mo_count=mo_count,
            mo_open=mo_open,
            qty_done=qty_done,
            qty_planned=qty_planned,
            progress_pct=pct,
            eta_date=eta,
            derived_status=derived,
            release_products=release_products,
            release_script_id=f'jp-release-products-{order.pk}',
        ))

    rows.sort(
        key=lambda r: (
            0 if r.order.plan_status != SxSalesOrder.PLAN_ON_HOLD else 1,
            r.order.plan_rank if r.order.plan_rank is not None else 10_000,
            -float(r.score),
            r.order.id or 0,
        )
    )
    return rows


def pipeline_counts() -> dict[str, int]:
    base = SxSalesOrder.objects.filter(
        is_demo=False,
        confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
    )
    return {
        'queued': base.filter(plan_status=SxSalesOrder.PLAN_QUEUED).count(),
        'ranked': base.filter(plan_status=SxSalesOrder.PLAN_RANKED).count(),
        'on_hold': base.filter(plan_status=SxSalesOrder.PLAN_ON_HOLD).count(),
        'released': base.filter(plan_status=SxSalesOrder.PLAN_RELEASED).count(),
        'in_progress': base.filter(plan_status=SxSalesOrder.PLAN_IN_PROGRESS).count(),
        'done': base.filter(plan_status=SxSalesOrder.PLAN_DONE).count(),
        'waiting': base.filter(plan_status__in=QUEUE_STATUSES).count(),
    }


@transaction.atomic
def recompute_plan_ranks(*, only_queue: bool = True) -> int:
    """Tính lại score + gán plan_rank 1..n theo điểm (bỏ qua on_hold)."""
    statuses = QUEUE_STATUSES if only_queue else None
    rows = build_plan_board_rows(statuses=statuses, include_released=not only_queue)
    # Chỉ xếp đơn không hold
    active = [r for r in rows if r.order.plan_status != SxSalesOrder.PLAN_ON_HOLD]
    active.sort(key=lambda r: (-float(r.score), r.order.plan_queued_at or timezone.now(), r.order.id))
    updated = 0
    for i, row in enumerate(active, start=1):
        order = SxSalesOrder.objects.select_for_update().get(pk=row.order.pk)
        if order.plan_status == SxSalesOrder.PLAN_ON_HOLD:
            continue
        if order.production_orders.filter(is_demo=False).exclude(
            status=SxProductionOrder.STATUS_CANCELLED,
        ).exists():
            continue
        order.plan_score = row.score
        order.plan_rank = i
        order.plan_status = SxSalesOrder.PLAN_RANKED
        order.save(update_fields=['plan_score', 'plan_rank', 'plan_status', 'updated_at'])
        updated += 1
    return updated


@transaction.atomic
def set_plan_priority(*, order_id: int, priority: str) -> SxSalesOrder:
    if priority not in {
        SxSalesOrder.PRIORITY_CRITICAL,
        SxSalesOrder.PRIORITY_URGENT,
        SxSalesOrder.PRIORITY_HIGH,
        SxSalesOrder.PRIORITY_NORMAL,
        SxSalesOrder.PRIORITY_LOW,
    }:
        raise PlanningError('Mức độ gấp không hợp lệ.')
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ xếp đơn đã xác nhận.')
    order.plan_priority = priority
    order.save(update_fields=['plan_priority', 'updated_at'])
    return order


@transaction.atomic
def hold_plan_order(*, order_id: int, reason: str = '') -> SxSalesOrder:
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ giữ đơn đã xác nhận.')
    if order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    ).exists():
        raise PlanningError('Đơn đã có LSX — không tạm giữ trên hàng đợi.')
    order.plan_status = SxSalesOrder.PLAN_ON_HOLD
    order.plan_hold_reason = (reason or '').strip()[:500]
    order.plan_rank = None
    order.save(update_fields=[
        'plan_status', 'plan_hold_reason', 'plan_rank', 'updated_at',
    ])
    return order


@transaction.atomic
def unhold_plan_order(*, order_id: int) -> SxSalesOrder:
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if order.plan_status != SxSalesOrder.PLAN_ON_HOLD:
        return order
    order.plan_status = SxSalesOrder.PLAN_QUEUED
    order.plan_hold_reason = ''
    order.save(update_fields=['plan_status', 'plan_hold_reason', 'updated_at'])
    return order


@transaction.atomic
def release_order_to_production(
    *,
    order_id: int,
    user=None,
    bom_by_product: dict[str, int] | None = None,
    routing_by_product: dict[str, int] | None = None,
) -> list[SxProductionOrder]:
    """Chuyển đơn xuống SX: tạo LSX theo từng dòng SP, gắn sales_order + BOM đã chọn."""
    from san_xuat.models import BomVersion, ProcessStep
    from san_xuat.services.dispatch import (
        publish_mo_to_team_work,
        steps_dicts_from_routing,
        sync_mo_process_steps,
    )

    order = (
        SxSalesOrder.objects.select_for_update()
        .prefetch_related('lines', 'plan_steps')
        .get(pk=order_id, is_demo=False)
    )
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ chuyển đơn đã xác nhận.')
    if order.plan_status == SxSalesOrder.PLAN_ON_HOLD:
        raise PlanningError('Đơn đang tạm giữ — bỏ giữ trước khi chuyển SX.')
    if order.plan_status == SxSalesOrder.PLAN_DONE:
        raise PlanningError('Đơn đã hoàn thành.')

    lines = list(order.lines.filter(qty__gt=0).order_by('sort_order', 'id'))
    if not lines:
        raise PlanningError('Đơn không có dòng sản phẩm.')

    def _id_map(raw_map: dict[str, int] | None) -> dict[str, int]:
        out: dict[str, int] = {}
        for raw_code, raw_id in (raw_map or {}).items():
            code = (raw_code or '').strip()
            if not code or not raw_id:
                continue
            try:
                out[code.casefold()] = int(raw_id)
            except (TypeError, ValueError):
                raise PlanningError(f'{code}: giá trị không hợp lệ.')
        return out

    bom_map = _id_map(bom_by_product)
    routing_map = _id_map(routing_by_product)

    # planned_date từ lộ trình Kanban (nếu có) — khớp theo tên công đoạn
    planned_by_name = {
        (s.process_name or '').strip().casefold(): s.planned_date
        for s in order.plan_steps.all()
        if s.planned_date
    }

    created: list[SxProductionOrder] = []
    errors: list[str] = []
    for ln in lines:
        exists = order.production_orders.filter(
            is_demo=False,
            product_code__iexact=ln.product_code,
        ).exclude(status=SxProductionOrder.STATUS_CANCELLED).exists()
        if exists:
            continue

        code = (ln.product_code or '').strip()
        bom_id = bom_map.get(code.casefold()) or ln.bom_version_id
        if not bom_id:
            raise PlanningError(f'{code}: chưa chọn hồ sơ thiết kế (BOM).')
        bom = BomVersion.objects.filter(pk=bom_id).select_related('tech_doc').first()
        if not bom or (bom.tech_doc.product_code or '').strip().casefold() != code.casefold():
            raise PlanningError(f'{code}: hồ sơ thiết kế không thuộc mã này.')
        routing_id = routing_map.get(code.casefold()) or ln.routing_id

        mo = None
        try:
            mo = create_mo_from_bom(
                product_code=code,
                qty=ln.qty_to_produce,
                order_date=timezone.localdate(),
                due_date=ln.due_date or order.due_date,
                notes=f'Từ ĐĐH {order.code}',
                user=user,
                sales_order_id=order.pk,
                bom_version_id=bom_id,
                routing_id=routing_id,
            )
            # Ưu tiên snapshot CD từ routing đã chọn; không thì BOM (+ ngày KH Kanban)
            routing_steps = steps_dicts_from_routing(routing_id)
            if routing_steps:
                if planned_by_name:
                    for row in routing_steps:
                        key = (row.get('process_name') or '').strip().casefold()
                        if key in planned_by_name:
                            row['planned_date'] = planned_by_name[key]
                sync_mo_process_steps(mo, routing_steps)
            elif planned_by_name and mo.bom_version_id:
                bom_rows = list(
                    ProcessStep.objects.filter(bom_id=mo.bom_version_id).order_by('sequence', 'id')
                )
                step_dicts = []
                for i, s in enumerate(bom_rows):
                    key = (s.process_name or '').strip().casefold()
                    step_dicts.append({
                        'id': s.pk,
                        'sequence': s.sequence or ((i + 1) * 10),
                        'process_name': s.process_name,
                        'work_center_id': s.work_center_id,
                        'planned_date': planned_by_name.get(key),
                        'manager_id': None,
                    })
                if step_dicts:
                    sync_mo_process_steps(mo, step_dicts)
            if ln.product_name and not mo.product_name:
                mo.product_name = ln.product_name
                mo.save(update_fields=['product_name'])
            # Phát hành để hiện trên Công việc tổ (tổ trưởng phân công nhân)
            publish_mo_to_team_work(mo_id=mo.pk)
            mo.refresh_from_db()
            created.append(mo)
        except DispatchError as exc:
            if mo is not None and getattr(mo, 'pk', None):
                mo.delete()
            errors.append(f'{code}: {exc}')

    if not created and errors:
        raise PlanningError('Không tạo được LSX: ' + '; '.join(errors[:5]))
    if not created:
        sync_plan_status(order)
        return list(
            order.production_orders.filter(is_demo=False).exclude(
                status=SxProductionOrder.STATUS_CANCELLED,
            )
        )

    order.plan_status = SxSalesOrder.PLAN_RELEASED
    order.plan_hold_reason = ''
    order.save(update_fields=['plan_status', 'plan_hold_reason', 'updated_at'])
    return created


def load_snapshot_for_board(*, days: int = 14) -> dict:
    """Năng lực tổ (tham khảo) cho tab board — không xếp lịch."""
    centers = list(
        SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by('code')
    )
    return {'centers': centers}


def confirmed_order_qty_summary() -> dict:
    qs = SxSalesOrder.objects.filter(
        is_demo=False,
        confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        plan_status__in=QUEUE_STATUSES,
    )
    agg = SxSalesOrderLine.objects.filter(order__in=qs).aggregate(total=Sum('qty'))
    return {
        'order_count': qs.count(),
        'total_qty': _q(agg.get('total')),
    }
