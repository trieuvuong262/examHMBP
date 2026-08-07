"""Lộ trình Kanban kế hoạch SX — snapshot công đoạn đơn + kéo thả theo ngày/công đoạn/tổ."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from san_xuat.hub_models import (
    SxMoProcessStep,
    SxProductionOrder,
    SxSalesOrder,
    SxSalesOrderPlanStep,
    SxWorkCenter,
)
from san_xuat.services.planning import PlanningError
from san_xuat.services.scheduling import product_routing
from san_xuat.services.work_calendar import working_days

_Q4 = Decimal('0.0001')

AXIS_DAY = 'day'
AXIS_PROCESS = 'process'
AXIS_TEAM = 'team'
AXES = (AXIS_DAY, AXIS_PROCESS, AXIS_TEAM)

CARD_ORDER = 'order'
CARD_MO = 'mo'

UNASSIGNED_KEY = '__none__'


@dataclass
class KanbanCard:
    card_type: str  # order | mo
    card_id: int
    process_name: str
    sequence: int
    planned_date: date | None
    work_center_id: int | None
    work_center_label: str
    status: str
    order_id: int
    order_code: str
    customer_name: str
    plan_priority: str
    plan_status: str
    mo_id: int | None = None
    mo_code: str = ''
    editable_route: bool = False


@dataclass
class KanbanColumn:
    key: str
    label: str
    cards: list[KanbanCard] = field(default_factory=list)


@dataclass
class KanbanBoard:
    axis: str
    columns: list[KanbanColumn] = field(default_factory=list)


def _q(value, places: str = '0.0001') -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places))


def ensure_order_plan_steps(order: SxSalesOrder) -> list[SxSalesOrderPlanStep]:
    """Seed snapshot từ routing dòng SP nếu đơn chưa có bước."""
    existing = list(order.plan_steps.select_related('work_center').order_by('sequence', 'id'))
    if existing:
        return existing
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        return []

    merged: dict[str, dict] = {}
    for ln in order.lines.all().order_by('sort_order', 'id'):
        routing = product_routing(ln.product_code)
        for step in routing.steps:
            name = (step.process_name or '').strip()
            if not name:
                continue
            key = name.casefold()
            if key not in merged:
                merged[key] = {
                    'sequence': step.sequence or (len(merged) + 1) * 10,
                    'process_name': name,
                    'work_center_id': step.work_center_id,
                    'minutes_per_unit': _q(step.minutes_per_unit),
                }
            else:
                prev = merged[key]
                prev['minutes_per_unit'] = max(prev['minutes_per_unit'], _q(step.minutes_per_unit))
                if not prev['work_center_id'] and step.work_center_id:
                    prev['work_center_id'] = step.work_center_id

    if not merged:
        return []

    rows = sorted(merged.values(), key=lambda r: (r['sequence'], r['process_name']))
    created: list[SxSalesOrderPlanStep] = []
    used: set[int] = set()
    for i, row in enumerate(rows):
        seq = int(row['sequence'] or (i + 1) * 10)
        while seq in used:
            seq += 1
        used.add(seq)
        created.append(
            SxSalesOrderPlanStep(
                sales_order=order,
                sequence=seq,
                process_name=row['process_name'],
                work_center_id=row['work_center_id'],
                minutes_per_unit=row['minutes_per_unit'] or Decimal('0'),
            )
        )
    SxSalesOrderPlanStep.objects.bulk_create(created)
    cache = getattr(order, '_prefetched_objects_cache', None)
    if cache is not None:
        cache.pop('plan_steps', None)
    return list(order.plan_steps.select_related('work_center').order_by('sequence', 'id'))


@transaction.atomic
def replace_order_plan_steps(*, order_id: int, steps: list[dict]) -> list[SxSalesOrderPlanStep]:
    """Thay toàn bộ lộ trình đơn. steps: process_name, work_center_id?, planned_date?, minutes?, sequence?."""
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ chỉnh lộ trình đơn đã xác nhận.')
    if order.plan_status in {SxSalesOrder.PLAN_DONE}:
        raise PlanningError('Đơn đã hoàn thành — không chỉnh lộ trình.')
    if order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    ).exists():
        raise PlanningError('Đơn đã có LSX — chỉnh công đoạn trên lệnh SX / kéo Kanban.')

    cleaned: list[dict] = []
    for i, raw in enumerate(steps or []):
        name = (raw.get('process_name') or '').strip()
        if not name:
            continue
        seq = int(raw.get('sequence') or (i + 1) * 10)
        wc_id = raw.get('work_center_id') or None
        if wc_id in ('', '0', 0):
            wc_id = None
        if wc_id is not None:
            wc_id = int(wc_id)
        planned = raw.get('planned_date') or None
        if isinstance(planned, str):
            planned = planned.strip() or None
            if planned:
                planned = date.fromisoformat(planned)
        mins = _q(raw.get('minutes_per_unit') or 0)
        cleaned.append({
            'sequence': seq,
            'process_name': name[:120],
            'work_center_id': wc_id,
            'planned_date': planned,
            'minutes_per_unit': mins,
        })

    order.plan_steps.all().delete()
    used: set[int] = set()
    created: list[SxSalesOrderPlanStep] = []
    for i, row in enumerate(cleaned):
        seq = int(row['sequence'] or (i + 1) * 10)
        while seq in used:
            seq += 1
        used.add(seq)
        created.append(
            SxSalesOrderPlanStep(
                sales_order=order,
                sequence=seq,
                process_name=row['process_name'],
                work_center_id=row['work_center_id'],
                planned_date=row['planned_date'],
                minutes_per_unit=row['minutes_per_unit'],
            )
        )
    SxSalesOrderPlanStep.objects.bulk_create(created)
    return list(order.plan_steps.select_related('work_center').order_by('sequence', 'id'))


def plan_steps_as_mo_dicts(order: SxSalesOrder) -> list[dict] | None:
    steps = list(order.plan_steps.order_by('sequence', 'id'))
    if not steps:
        return None
    return [
        {
            'sequence': s.sequence,
            'process_name': s.process_name,
            'work_center_id': s.work_center_id,
            'planned_date': s.planned_date,
            'status': SxMoProcessStep.STATUS_PENDING,
            'manager_id': None,
        }
        for s in steps
    ]


def _queue_orders(search: str = '') -> list[SxSalesOrder]:
    from san_xuat.services.plan_board import QUEUE_STATUSES

    qs = (
        SxSalesOrder.objects.filter(
            is_demo=False,
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
            plan_status__in=QUEUE_STATUSES,
        )
        .prefetch_related(
            Prefetch('plan_steps', queryset=SxSalesOrderPlanStep.objects.select_related('work_center')),
            'lines',
        )
        .order_by('plan_rank', 'due_date', 'id')
    )
    term = (search or '').strip()
    if term:
        qs = qs.filter(
            Q(code__icontains=term)
            | Q(customer_name__icontains=term)
            | Q(kv_order_code__icontains=term)
        )
    return list(qs)


def _open_mo_steps(search: str = '') -> list[SxMoProcessStep]:
    qs = (
        SxMoProcessStep.objects.filter(
            production_order__is_demo=False,
        )
        .exclude(production_order__status=SxProductionOrder.STATUS_CANCELLED)
        .exclude(production_order__status=SxProductionOrder.STATUS_DONE)
        .select_related(
            'work_center',
            'production_order',
            'production_order__sales_order',
        )
        .order_by('sequence', 'id')
    )
    term = (search or '').strip()
    if term:
        qs = qs.filter(
            Q(production_order__code__icontains=term)
            | Q(production_order__product_code__icontains=term)
            | Q(production_order__sales_order__code__icontains=term)
            | Q(production_order__sales_order__customer_name__icontains=term)
            | Q(process_name__icontains=term)
        )
    return list(qs)


def _card_from_order_step(order: SxSalesOrder, step: SxSalesOrderPlanStep) -> KanbanCard:
    return KanbanCard(
        card_type=CARD_ORDER,
        card_id=step.pk,
        process_name=step.process_name or '',
        sequence=step.sequence,
        planned_date=step.planned_date,
        work_center_id=step.work_center_id,
        work_center_label=step.team_label,
        status=SxMoProcessStep.STATUS_PENDING,
        order_id=order.pk,
        order_code=order.code,
        customer_name=order.customer_name or '',
        plan_priority=order.plan_priority or SxSalesOrder.PRIORITY_NORMAL,
        plan_status=order.plan_status,
        editable_route=True,
    )


def _card_from_mo_step(step: SxMoProcessStep) -> KanbanCard:
    mo = step.production_order
    so = mo.sales_order
    return KanbanCard(
        card_type=CARD_MO,
        card_id=step.pk,
        process_name=step.process_name or '',
        sequence=step.sequence,
        planned_date=step.planned_date,
        work_center_id=step.work_center_id,
        work_center_label=step.team_label,
        status=step.status or SxMoProcessStep.STATUS_PENDING,
        order_id=so.pk if so else 0,
        order_code=so.code if so else '',
        customer_name=(so.customer_name if so else '') or '',
        plan_priority=(so.plan_priority if so else SxSalesOrder.PRIORITY_NORMAL) or SxSalesOrder.PRIORITY_NORMAL,
        plan_status=(so.plan_status if so else '') or '',
        mo_id=mo.pk,
        mo_code=mo.code,
        editable_route=False,
    )


def _collect_cards(*, search: str = '') -> list[KanbanCard]:
    cards: list[KanbanCard] = []
    for order in _queue_orders(search):
        steps = ensure_order_plan_steps(order)
        for step in steps:
            cards.append(_card_from_order_step(order, step))
    for step in _open_mo_steps(search):
        cards.append(_card_from_mo_step(step))
    return cards


def build_kanban(*, axis: str, days: int = 14, search: str = '') -> KanbanBoard:
    if axis not in AXES:
        axis = AXIS_DAY
    cards = _collect_cards(search=search)
    columns: list[KanbanColumn] = []

    if axis == AXIS_DAY:
        today = timezone.localdate()
        end = today + timedelta(days=max(days * 2, 28))
        work_days = working_days(today, end)[: max(1, days)]
        by_key: dict[str, list[KanbanCard]] = {UNASSIGNED_KEY: []}
        for d in work_days:
            by_key[d.isoformat()] = []
        for card in cards:
            if card.planned_date and card.planned_date.isoformat() in by_key:
                by_key[card.planned_date.isoformat()].append(card)
            elif card.planned_date and card.planned_date < today:
                # Quá khứ → cột chưa xếp để planner kéo lại
                by_key[UNASSIGNED_KEY].append(card)
            elif card.planned_date:
                # Ngoài cửa sổ → gán ngày gần nhất trong window hoặc unassigned
                by_key[UNASSIGNED_KEY].append(card)
            else:
                by_key[UNASSIGNED_KEY].append(card)
        columns.append(KanbanColumn(key=UNASSIGNED_KEY, label='Chưa xếp', cards=by_key[UNASSIGNED_KEY]))
        for d in work_days:
            key = d.isoformat()
            columns.append(
                KanbanColumn(key=key, label=d.strftime('%d/%m'), cards=by_key.get(key, []))
            )

    elif axis == AXIS_PROCESS:
        names: list[str] = []
        seen: set[str] = set()
        from san_xuat.models import SxProcessName

        for n in SxProcessName.objects.filter(is_active=True).order_by('sort_order', 'name').values_list('name', flat=True):
            key = n.casefold()
            if key not in seen:
                seen.add(key)
                names.append(n)
        for card in cards:
            n = (card.process_name or '').strip()
            if n and n.casefold() not in seen:
                seen.add(n.casefold())
                names.append(n)
        by_key: dict[str, list[KanbanCard]] = {UNASSIGNED_KEY: []}
        name_by_fold = {n.casefold(): n for n in names}
        for n in names:
            by_key[n] = []
        for card in cards:
            n = (card.process_name or '').strip()
            if not n:
                by_key[UNASSIGNED_KEY].append(card)
            else:
                canon = name_by_fold.get(n.casefold(), n)
                if canon not in by_key:
                    by_key[canon] = []
                    names.append(canon)
                by_key[canon].append(card)
        columns.append(KanbanColumn(key=UNASSIGNED_KEY, label='Chưa gắn', cards=by_key[UNASSIGNED_KEY]))
        for n in names:
            columns.append(KanbanColumn(key=n, label=n, cards=by_key.get(n, [])))

    else:  # team
        centers = list(
            SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by('code', 'name')
        )
        by_key: dict[str, list[KanbanCard]] = {UNASSIGNED_KEY: []}
        for wc in centers:
            by_key[str(wc.pk)] = []
        for card in cards:
            if card.work_center_id and str(card.work_center_id) in by_key:
                by_key[str(card.work_center_id)].append(card)
            else:
                by_key[UNASSIGNED_KEY].append(card)
        columns.append(KanbanColumn(key=UNASSIGNED_KEY, label='Chưa gán', cards=by_key[UNASSIGNED_KEY]))
        for wc in centers:
            label = (wc.team_label or wc.name or wc.code or str(wc.pk)).strip()
            columns.append(KanbanColumn(key=str(wc.pk), label=label, cards=by_key.get(str(wc.pk), [])))

    return KanbanBoard(axis=axis, columns=columns)


@transaction.atomic
def move_kanban_card(
    *,
    card_type: str,
    card_id: int,
    axis: str,
    target_key: str,
) -> KanbanCard:
    target_key = (target_key or '').strip() or UNASSIGNED_KEY
    if axis not in AXES:
        raise PlanningError('Trục Kanban không hợp lệ.')
    if card_type not in {CARD_ORDER, CARD_MO}:
        raise PlanningError('Loại thẻ không hợp lệ.')

    if card_type == CARD_ORDER:
        step = (
            SxSalesOrderPlanStep.objects.select_for_update()
            .select_related('sales_order', 'work_center')
            .get(pk=card_id)
        )
        order = step.sales_order
        if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
            raise PlanningError('Đơn chưa xác nhận.')
        if order.production_orders.filter(is_demo=False).exclude(
            status=SxProductionOrder.STATUS_CANCELLED,
        ).exists():
            raise PlanningError('Đơn đã có LSX — kéo thẻ công đoạn LSX.')

        if axis == AXIS_DAY:
            if target_key == UNASSIGNED_KEY:
                step.planned_date = None
            else:
                step.planned_date = date.fromisoformat(target_key)
            step.save(update_fields=['planned_date'])
        elif axis == AXIS_PROCESS:
            if target_key == UNASSIGNED_KEY:
                raise PlanningError('Công đoạn không được để trống — chọn tên công đoạn.')
            step.process_name = target_key[:120]
            step.save(update_fields=['process_name'])
        else:
            if target_key == UNASSIGNED_KEY:
                step.work_center_id = None
            else:
                if not SxWorkCenter.objects.filter(pk=int(target_key), is_active=True).exists():
                    raise PlanningError('Tổ không hợp lệ.')
                step.work_center_id = int(target_key)
            step.save(update_fields=['work_center_id'])
        step.refresh_from_db()
        return _card_from_order_step(order, step)

    step = (
        SxMoProcessStep.objects.select_for_update()
        .select_related('production_order', 'production_order__sales_order', 'work_center')
        .get(pk=card_id)
    )
    mo = step.production_order
    if mo.status == SxProductionOrder.STATUS_CANCELLED:
        raise PlanningError('LSX đã hủy.')

    if axis == AXIS_DAY:
        if target_key == UNASSIGNED_KEY:
            step.planned_date = None
        else:
            step.planned_date = date.fromisoformat(target_key)
        step.save(update_fields=['planned_date'])
    elif axis == AXIS_PROCESS:
        if target_key == UNASSIGNED_KEY:
            raise PlanningError('Công đoạn không được để trống — chọn tên công đoạn.')
        step.process_name = target_key[:120]
        # Kéo sang cột công đoạn khác → đang làm; nếu trùng tên bước hiện tại giữ status
        if step.status == SxMoProcessStep.STATUS_DONE:
            step.status = SxMoProcessStep.STATUS_IN_PROGRESS
        elif step.status == SxMoProcessStep.STATUS_PENDING:
            step.status = SxMoProcessStep.STATUS_IN_PROGRESS
        step.save(update_fields=['process_name', 'status'])
        if mo.status == SxProductionOrder.STATUS_DRAFT:
            mo.status = SxProductionOrder.STATUS_IN_PROGRESS
            mo.save(update_fields=['status'])
        elif mo.status == SxProductionOrder.STATUS_RELEASED:
            mo.status = SxProductionOrder.STATUS_IN_PROGRESS
            mo.save(update_fields=['status'])
    else:
        if target_key == UNASSIGNED_KEY:
            step.work_center_id = None
        else:
            if not SxWorkCenter.objects.filter(pk=int(target_key), is_active=True).exists():
                raise PlanningError('Tổ không hợp lệ.')
            step.work_center_id = int(target_key)
        step.save(update_fields=['work_center_id'])

    step.refresh_from_db()
    return _card_from_mo_step(step)


def work_centers_for_route_form() -> list[SxWorkCenter]:
    return list(
        SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by('code', 'name')
    )


def process_names_for_route_form() -> list[str]:
    from san_xuat.models import SxProcessName

    return list(
        SxProcessName.objects.filter(is_active=True).order_by('sort_order', 'name').values_list('name', flat=True)
    )
