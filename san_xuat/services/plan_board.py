"""Kế hoạch sản xuất theo đơn (MTO board) — hàng đợi, xếp hạng, chuyển LSX.

Phase 1: chỉ ĐĐH đã xác nhận. MTS/MPS swimlane sau.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from san_xuat.hub_models import SxProductionOrder, SxSalesOrder, SxSalesOrderLine, SxSalesOrderPlanStep, SxWorkCenter
from san_xuat.services.dispatch import DispatchError, create_mo_from_bom
from san_xuat.services.planning import PlanningError
from san_xuat.services.order_routing import sales_order_line_routing, steps_dicts_from_order_line
from san_xuat.templatetags.sx_format import format_sx_num_input

_Q2 = Decimal('0.01')
# Ca KHSX mặc định: 9 giờ 30 phút
PLAN_SHIFT_MINUTES = Decimal('570')
PLAN_SHIFT_LABEL = '9 giờ 30 phút'

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


def line_order_smv_seconds(order_line: SxSalesOrderLine) -> Decimal:
    """Tổng SMV đơn hàng (giây/cái) = Σ (SMV đơn × SL/SP) mọi CĐ đã có khi lên đơn."""
    rows = list(order_line.routing_lines.all())
    if rows:
        total = Decimal('0')
        for rt in rows:
            op_total = rt.total_operation_smv
            if op_total is None:
                qty = rt.qty_per_garment
                if qty is None:
                    qty = Decimal('1')
                op_total = Decimal(str(rt.applied_unit_smv or 0)) * qty
            total += Decimal(str(op_total or 0))
        return _q(total, '0.0001')

    routing = sales_order_line_routing(order_line)
    return _q(routing.total_smv * Decimal('60'), '0.0001')


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
    khsx_start: date | None = None
    khsx_end: date | None = None
    khsx_overrun: bool = False
    duration_label: str = ''
    duration_work_days: int = 0
    duration_detail: dict = field(default_factory=dict)
    duration_script_id: str = ''
    derived_status: str = SxSalesOrder.PLAN_QUEUED
    release_products: list[dict] = field(default_factory=list)
    release_script_id: str = ''
    work_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    buffer_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    hops: list = field(default_factory=list)
    active_hops: list = field(default_factory=list)
    open_hops: list = field(default_factory=list)
    flow_groups: list = field(default_factory=list)
    product_flows: list = field(default_factory=list)
    can_unrelease: bool = False
    team_spans: list = field(default_factory=list)


@dataclass
class PlanProductFlow:
    """Flow công đoạn theo từng mã SP — không gộp chung nhiều mã trên một ticket."""

    product_code: str
    product_name: str
    qty: Decimal
    flow_groups: list = field(default_factory=list)
    line_id: int = 0
    process_names: list[str] = field(default_factory=list)
    smv_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    work_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    buffer_minutes: Decimal = field(default_factory=lambda: Decimal('0'))


@dataclass
class TeamKhsxSpan:
    """Khoảng KHSX của một tổ tham gia Ob trên đơn."""

    slug: str
    label: str
    work_minutes: Decimal
    buffer_minutes: Decimal
    minutes: Decimal
    start: date
    end: date
    pinned: bool = False
    duration_label: str = ''
    duration_work_days: int = 0


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
    return SxSalesOrder.PLAN_QUEUED


def sync_plan_status(order: SxSalesOrder) -> str:
    """Đồng bộ plan_status từ LSX (không đè on_hold). Gộp ranked cũ → chờ xếp."""
    if order.plan_status == SxSalesOrder.PLAN_ON_HOLD:
        return order.plan_status
    derived = derive_plan_status(order)
    if derived != order.plan_status:
        order.plan_status = derived
        order.save(update_fields=['plan_status', 'updated_at'])
    return derived


def _enrich_routing(order: SxSalesOrder, lines: list[SxSalesOrderLine]) -> tuple[list[str], Decimal, bool, Decimal]:
    names: list[str] = []
    seen: set[str] = set()
    work_min = Decimal('0')
    buffer_min = Decimal('0')
    has_any = False
    for ln in lines:
        routing = sales_order_line_routing(ln)
        qty = ln.qty_to_produce
        smv_min = _q(line_order_smv_seconds(ln) / Decimal('60'), '0.0001')
        if routing.has_time_data or smv_min > 0:
            has_any = True
            work_min += (smv_min * qty).quantize(_Q2)
            buffer_min += _q(routing.hop_buffer_minutes)
        for step in routing.steps:
            n = (step.process_name or '').strip()
            if n and n not in seen:
                seen.add(n)
                names.append(n)
    return names, _q(work_min), has_any, _q(buffer_min)


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


def _buffer_from_flow_groups(groups) -> Decimal:
    """Tổng phút kiểm/VC giữa các tổ trên một dải flow (bỏ cụm cuối)."""
    rows = list(groups or [])
    if len(rows) < 2:
        return Decimal('0')
    total = Decimal('0')
    for g in rows[:-1]:
        total += _q(getattr(g, 'form_count_minutes', 0)) + _q(getattr(g, 'form_transfer_minutes', 0))
    return _q(total)


def _hops_from_flow_groups(groups) -> list[dict]:
    """Khoảng kiểm/VC giữa các tổ — dữ liệu modal chi tiết thời gian."""
    rows = list(groups or [])
    hops: list[dict] = []
    for i, g in enumerate(rows[:-1]):
        nxt = rows[i + 1]
        from_lab = (getattr(g, 'team_label', None) or '').strip()
        if not from_lab and getattr(g, 'process_names', None):
            from_lab = g.process_names[0]
        to_lab = (getattr(nxt, 'team_label', None) or '').strip()
        if not to_lab and getattr(nxt, 'process_names', None):
            to_lab = nxt.process_names[0]
        count = _q(getattr(g, 'form_count_minutes', 0))
        transfer = _q(getattr(g, 'form_transfer_minutes', 0))
        hops.append({
            'from': from_lab or '—',
            'to': to_lab or '—',
            'count': format_sx_num_input(count),
            'transfer': format_sx_num_input(transfer),
            'total': format_sx_num_input(count + transfer),
        })
    return hops


def format_order_duration(minutes: Decimal) -> tuple[str, int]:
    """Nhãn thời gian làm đơn: '16 giờ 29 phút · 3 ngày làm việc'."""
    from decimal import ROUND_CEILING

    mins = max(_q(minutes), Decimal('0'))
    if mins <= 0:
        return '', 0
    hours = int(mins // 60)
    rem = int((mins % 60).to_integral_value())
    if rem == 0 and (mins % 60) > 0:
        rem = 1
    clock_parts: list[str] = []
    if hours:
        clock_parts.append(f'{hours} giờ')
    if rem:
        clock_parts.append(f'{rem} phút')
    if not clock_parts:
        clock_parts.append('dưới 1 phút')
    clock = ' '.join(clock_parts)
    per_day = PLAN_SHIFT_MINUTES
    days = int((mins / per_day).to_integral_value(rounding=ROUND_CEILING))
    days = max(1, days)
    if days == 1:
        return f'{clock} · 1 ngày làm việc', 1
    return f'{clock} · {days} ngày làm việc', days


def _next_working_day_after(d: date) -> date:
    from san_xuat.services.work_calendar import is_working_day

    day = d + timedelta(days=1)
    for _ in range(800):
        if is_working_day(day):
            return day
        day += timedelta(days=1)
    return day


def _factory_slug_rank() -> dict[str, int]:
    from san_xuat.services.progress_template import TEAM_SLUGS

    return {slug: i for i, (slug, *_rest) in enumerate(TEAM_SLUGS)}


def _team_display_label(slug: str, fallback: str = '') -> str:
    from san_xuat.services.progress_template import team_by_slug

    meta = team_by_slug(slug) or {}
    return (meta.get('label') or fallback or slug or '').strip()


def _add_flow_hops(groups, hop_by_slug: dict[str, Decimal]) -> None:
    rows = list(groups or [])
    for i, g in enumerate(rows[:-1]):
        slug = (getattr(g, 'team_slug', None) or '').strip().lower()
        if not slug or slug.startswith('wc:'):
            continue
        hop_by_slug[slug] = hop_by_slug.get(slug, Decimal('0')) + _q(
            getattr(g, 'form_count_minutes', 0),
        ) + _q(getattr(g, 'form_transfer_minutes', 0))


def _team_loads_from_order(
    order: SxSalesOrder,
    *,
    product_flows: list[PlanProductFlow] | None = None,
) -> list[dict]:
    """Phút làm + hop theo tổ tham gia Ob, thứ tự xưởng."""
    from san_xuat.services.inter_step_times import _step_team_slug, flow_groups_from_steps

    work: dict[str, Decimal] = {}
    hops: dict[str, Decimal] = {}
    labels: dict[str, str] = {}
    lines = [ln for ln in order.lines.all() if (ln.qty or 0) > 0]
    for ln in lines:
        routing = sales_order_line_routing(ln)
        qty = ln.qty_to_produce
        for step in routing.steps:
            slug = (_step_team_slug(step) or '').strip().lower()
            if not slug:
                continue
            work[slug] = work.get(slug, Decimal('0')) + _q(
                (step.minutes_per_unit or Decimal('0')) * qty, '0.0001',
            )
            if slug not in labels:
                labels[slug] = _team_display_label(slug, step.team_label)

    if product_flows:
        for pf in product_flows:
            _add_flow_hops(pf.flow_groups, hops)
    else:
        for ln in lines:
            routing = sales_order_line_routing(ln)
            if routing.steps:
                _add_flow_hops(flow_groups_from_steps(routing.steps, sort_factory=True), hops)

    rank = _factory_slug_rank()
    slugs = sorted(work.keys(), key=lambda s: (rank.get(s, 99), s))
    out: list[dict] = []
    for slug in slugs:
        work_min = _q(work.get(slug, Decimal('0')))
        buf = _q(hops.get(slug, Decimal('0')))
        out.append({
            'slug': slug,
            'label': labels.get(slug) or _team_display_label(slug),
            'work_minutes': work_min,
            'buffer_minutes': buf,
            'minutes': _q(work_min + buf),
        })
    return out


def _pinned_starts_from_steps(plan_steps) -> dict[str, date]:
    from san_xuat.services.inter_step_times import _step_team_slug

    pinned: dict[str, date] = {}
    for step in plan_steps or []:
        slug = (_step_team_slug(step) or '').strip().lower()
        planned = getattr(step, 'planned_date', None)
        if not slug or not planned:
            continue
        if slug not in pinned or planned < pinned[slug]:
            pinned[slug] = planned
    return pinned


def team_khsx_spans(
    order: SxSalesOrder,
    *,
    product_flows: list[PlanProductFlow] | None = None,
    plan_steps=None,
    today: date | None = None,
) -> list[TeamKhsxSpan]:
    """Span KHSX từng tổ: mặc định nối tiếp; tổ đã kéo dùng planned_date độc lập."""
    from san_xuat.services.inter_step_times import schedule_span

    loads = _team_loads_from_order(order, product_flows=product_flows)
    if not loads:
        return []
    today = today or timezone.localdate()
    anchor = order.plan_start_date or order.request_date or today
    pinned = _pinned_starts_from_steps(plan_steps if plan_steps is not None else list(order.plan_steps.all()))

    cursor = anchor
    defaults: dict[str, tuple[date, date]] = {}
    for row in loads:
        start, end = schedule_span(
            start=cursor,
            lead_minutes=row['minutes'],
            minutes_per_day=PLAN_SHIFT_MINUTES,
        )
        defaults[row['slug']] = (start, end)
        cursor = _next_working_day_after(end)

    spans: list[TeamKhsxSpan] = []
    for row in loads:
        slug = row['slug']
        is_pinned = slug in pinned
        start = pinned[slug] if is_pinned else defaults[slug][0]
        start, end = schedule_span(
            start=start,
            lead_minutes=row['minutes'],
            minutes_per_day=PLAN_SHIFT_MINUTES,
        )
        dur_label, dur_days = format_order_duration(row['minutes'])
        spans.append(TeamKhsxSpan(
            slug=slug,
            label=row['label'],
            work_minutes=row['work_minutes'],
            buffer_minutes=row['buffer_minutes'],
            minutes=row['minutes'],
            start=start,
            end=end,
            pinned=is_pinned,
            duration_label=dur_label,
            duration_work_days=dur_days,
        ))
    return spans


def _mo_progress(mos: list[SxProductionOrder]) -> tuple[int, int, Decimal, Decimal, Decimal]:
    active = [m for m in mos if m.status != SxProductionOrder.STATUS_CANCELLED]
    open_mos = [
        m for m in active
        if m.status != SxProductionOrder.STATUS_DONE
    ]
    qty_planned = sum((m.qty or Decimal('0') for m in active), Decimal('0'))
    qty_done = sum((m.qty_done or Decimal('0') for m in active), Decimal('0'))
    if qty_planned > 0 and qty_done > qty_planned:
        qty_done = qty_planned
    pct = Decimal('0')
    if qty_planned > 0:
        pct = (qty_done / qty_planned * Decimal('100')).quantize(_Q2)
        if pct > Decimal('100'):
            pct = Decimal('100')
    return len(active), len(open_mos), _q(qty_planned), _q(qty_done), pct


_UNRELEASE_MO_STATUSES = (
    SxProductionOrder.STATUS_DRAFT,
    SxProductionOrder.STATUS_RELEASED,
)


def mos_allow_unrelease(mos: list[SxProductionOrder]) -> bool:
    """LSX còn hủy chuyển được: chỉ nháp/đã phát hành, chưa có SL làm."""
    active = [m for m in mos if m.status != SxProductionOrder.STATUS_CANCELLED]
    if not active:
        return False
    for mo in active:
        if mo.status not in _UNRELEASE_MO_STATUSES:
            return False
        if (mo.qty_done or Decimal('0')) > 0:
            return False
    return True


def _assert_order_unreleasable(order: SxSalesOrder, mos: list[SxProductionOrder]) -> None:
    """Chặn hủy khi đã có thống kê / xuất NPL / nhập TP / bàn giao."""
    if not mos_allow_unrelease(mos):
        raise PlanningError(
            'Không hủy chuyển SX: lệnh đã đang sản xuất, hoàn thành hoặc đã ghi SL.'
        )
    mo_ids = [m.pk for m in mos if m.pk]
    if not mo_ids:
        return

    from san_xuat.hub_models import (
        SxFgReceiptRequest,
        SxMaterialIssueRequest,
        SxProductionStat,
        SxWipHandover,
    )

    if SxProductionStat.objects.filter(
        production_order_id__in=mo_ids,
        status=SxProductionStat.STATUS_CONFIRMED,
    ).exists():
        raise PlanningError('Không hủy chuyển SX: đã có thống kê sản xuất xác nhận.')

    blocked_issue = (
        SxMaterialIssueRequest.objects.filter(production_order_id__in=mo_ids)
        .exclude(status__in=('draft', 'cancelled'))
        .exists()
        or SxMaterialIssueRequest.objects.filter(
            production_order_id__in=mo_ids,
            stock_issue_id__isnull=False,
        ).exists()
    )
    if blocked_issue:
        raise PlanningError('Không hủy chuyển SX: đã có yêu cầu / phiếu xuất vật tư.')

    if (
        SxFgReceiptRequest.objects.filter(production_order_id__in=mo_ids)
        .exclude(status=SxFgReceiptRequest.STATUS_CANCELLED)
        .exists()
    ):
        raise PlanningError('Không hủy chuyển SX: đã có yêu cầu nhập thành phẩm.')

    if SxWipHandover.objects.filter(production_order_id__in=mo_ids).exclude(
        status=SxWipHandover.STATUS_REJECTED,
    ).exists():
        raise PlanningError('Không hủy chuyển SX: đã có bàn giao bán thành phẩm.')


def build_plan_board_rows(
    *,
    statuses: tuple[str, ...] | None = None,
    search: str = '',
    include_released: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[PlanBoardRow]:
    """Danh sách đơn trên board (MTO confirmed).

    ``date_from`` / ``date_to`` lọc theo neo KHSX (``plan_start_date`` hoặc
    ``request_date``) — dùng tab Đã chuyển SX.
    """
    qs = (
        SxSalesOrder.objects.filter(
            is_demo=False,
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        )
        .prefetch_related(
            Prefetch(
                'lines',
                queryset=SxSalesOrderLine.objects.order_by('sort_order', 'id').prefetch_related(
                    'routing_lines__work_center',
                ),
            ),
            Prefetch(
                'production_orders',
                queryset=SxProductionOrder.objects.filter(is_demo=False).order_by('-order_date', 'code'),
            ),
            Prefetch(
                'plan_steps',
                queryset=SxSalesOrderPlanStep.objects.select_related('work_center').order_by(
                    'sequence', 'id',
                ),
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

    if date_from or date_to:
        qs = qs.annotate(
            _plan_anchor=Coalesce('plan_start_date', 'request_date'),
        )
        if date_from:
            qs = qs.filter(_plan_anchor__gte=date_from)
        if date_to:
            qs = qs.filter(_plan_anchor__lte=date_to)

    today = timezone.localdate()
    rows: list[PlanBoardRow] = []
    for order in qs:
        lines = list(order.lines.all())
        mos = list(order.production_orders.all())
        total_qty = sum((ln.qty_to_produce for ln in lines), Decimal('0'))
        names, work_min, has_routing, routing_buffer = _enrich_routing(order, lines)
        hops = []
        flow_groups = []
        product_flows: list[PlanProductFlow] = []
        buffer_min = routing_buffer
        plan_steps = list(order.plan_steps.all())
        if not plan_steps and order.confirm_status == SxSalesOrder.CONFIRM_CONFIRMED:
            from san_xuat.services.plan_route import ensure_order_plan_steps

            plan_steps = ensure_order_plan_steps(order)
        if plan_steps:
            from san_xuat.services.inter_step_times import (
                flow_groups_from_steps,
                hops_from_steps,
            )

            hops = hops_from_steps(plan_steps)
            flow_groups = flow_groups_from_steps(plan_steps, sort_factory=True)
            # buffer_min không lấy từ plan_steps gộp (đơn nhiều mã bị cộng hop giả
            # ở chỗ ghép hai mã). Cộng theo từng mã ở dưới.

        # Flow theo từng mã SP — không gộp chung nhiều mã thành một dải tổ
        from san_xuat.services.inter_step_times import (
            attach_flow_group_hops,
            flow_groups_from_steps as _flow_groups,
        )

        active_lines = [ln for ln in lines if (ln.qty or 0) > 0 and (ln.product_code or '').strip()]
        single_product = len({(ln.product_code or '').strip().casefold() for ln in active_lines}) == 1
        for ln in active_lines:
            code = (ln.product_code or '').strip()
            routing = sales_order_line_routing(ln)
            line_steps = list(routing.steps)
            if single_product and plan_steps:
                # 1 mã: dùng snapshot đơn (có hop_step_id để sửa kiểm/VC), xếp lại theo xưởng
                groups = _flow_groups(plan_steps, sort_factory=True)
            elif line_steps:
                groups = _flow_groups(line_steps, sort_factory=True)
                # Gắn lại + / phút kiểm-VC từ snapshot đơn (không gộp flow nhiều mã)
                attach_flow_group_hops(groups, plan_steps)
            else:
                groups = []
            pnames: list[str] = []
            seen_p: set[str] = set()
            for g in groups:
                for n in g.process_names:
                    k = n.casefold()
                    if k not in seen_p:
                        seen_p.add(k)
                        pnames.append(n)
            pbuf = _buffer_from_flow_groups(groups)
            psmv = _q(line_order_smv_seconds(ln) / Decimal('60'), '0.0001')
            product_flows.append(PlanProductFlow(
                product_code=code,
                product_name=(ln.product_name or '').strip(),
                qty=_q(ln.qty_to_produce),
                flow_groups=groups,
                line_id=int(ln.pk or 0),
                process_names=pnames[:12],
                smv_minutes=psmv,
                work_minutes=_q(psmv * ln.qty_to_produce),
                buffer_minutes=pbuf,
            ))
        if product_flows:
            # Ticket-level groups = mã đầu (fallback include cũ); UI ưu tiên product_flows
            flow_groups = product_flows[0].flow_groups if len(product_flows) == 1 else []
            if not names:
                names = [n for pf in product_flows for n in pf.process_names][:12]
            # Kiểm/VC: cộng tất cả mã (mỗi dải flow riêng), đã gồm mặc định cặp tổ
            flow_buf = sum((_buffer_from_flow_groups(pf.flow_groups) for pf in product_flows), Decimal('0'))
            buffer_min = _q(flow_buf)
            work_min = _q(sum((pf.work_minutes for pf in product_flows), Decimal('0')))
        cycle_min = _q(work_min + buffer_min)
        score, days_to_due, is_overdue = compute_score(
            order=order, cycle_minutes=cycle_min, today=today,
        )
        mo_count, mo_open, qty_planned, qty_done, pct = _mo_progress(mos)
        derived = derive_plan_status(order, mos)
        from san_xuat.services.inter_step_times import schedule_span

        team_spans = team_khsx_spans(
            order,
            product_flows=product_flows,
            plan_steps=plan_steps,
            today=today,
        )
        if team_spans:
            khsx_start = min(s.start for s in team_spans)
            khsx_end = max(s.end for s in team_spans)
        else:
            khsx_start = order.plan_start_date or order.request_date or today
            khsx_end = khsx_start
            if cycle_min > 0:
                khsx_start, khsx_end = schedule_span(
                    start=khsx_start,
                    lead_minutes=cycle_min,
                    minutes_per_day=PLAN_SHIFT_MINUTES,
                )
        khsx_overrun = bool(order.due_date and khsx_end and khsx_end > order.due_date)
        eta = khsx_end
        duration_label, duration_work_days = format_order_duration(cycle_min)

        def _fmt_date(d):
            return d.strftime('%d/%m/%Y') if d else ''

        duration_detail = {
            'code': order.code,
            'request': _fmt_date(order.request_date),
            'due': _fmt_date(order.due_date),
            'khsx_start': _fmt_date(khsx_start),
            'khsx_end': _fmt_date(khsx_end),
            'shift_label': PLAN_SHIFT_LABEL,
            'work_minutes': format_sx_num_input(work_min),
            'buffer_minutes': format_sx_num_input(buffer_min),
            'cycle_minutes': format_sx_num_input(cycle_min),
            'duration_label': duration_label,
            'work_days': duration_work_days,
            'teams': [
                {
                    'slug': ts.slug,
                    'label': ts.label,
                    'start': _fmt_date(ts.start),
                    'end': _fmt_date(ts.end),
                    'work_minutes': format_sx_num_input(ts.work_minutes),
                    'buffer_minutes': format_sx_num_input(ts.buffer_minutes),
                    'minutes': format_sx_num_input(ts.minutes),
                    'duration_label': ts.duration_label,
                }
                for ts in team_spans
            ],
            'products': [
                {
                    'code': pf.product_code,
                    'name': pf.product_name,
                    'qty': format_sx_num_input(pf.qty),
                    'smv_min': format_sx_num_input(pf.smv_minutes),
                    'smv_sec': format_sx_num_input(_q(pf.smv_minutes * Decimal('60'))),
                    'work_minutes': format_sx_num_input(pf.work_minutes),
                    'buffer_minutes': format_sx_num_input(pf.buffer_minutes),
                    'hops': _hops_from_flow_groups(pf.flow_groups),
                }
                for pf in product_flows
            ],
        }
        duration_script_id = f'jp-duration-{order.pk}'

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
                'qty': format_sx_num_input(ln.qty_to_produce),
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
            khsx_start=khsx_start,
            khsx_end=khsx_end,
            khsx_overrun=khsx_overrun,
            duration_label=duration_label,
            duration_work_days=duration_work_days,
            duration_detail=duration_detail,
            duration_script_id=duration_script_id,
            derived_status=derived,
            release_products=release_products,
            release_script_id=f'jp-release-products-{order.pk}',
            work_minutes=work_min,
            buffer_minutes=buffer_min,
            hops=hops,
            active_hops=[h for h in hops if getattr(h, 'is_set', False)],
            open_hops=[h for h in hops if not getattr(h, 'is_set', False)],
            flow_groups=flow_groups,
            product_flows=product_flows,
            can_unrelease=mos_allow_unrelease(mos),
            team_spans=team_spans,
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
        # Không dùng trạng thái «Đã xếp» — hàng đợi vẫn là chờ xếp đến khi Chuyển SX
        if order.plan_status == SxSalesOrder.PLAN_RANKED:
            order.plan_status = SxSalesOrder.PLAN_QUEUED
            order.save(update_fields=['plan_score', 'plan_rank', 'plan_status', 'updated_at'])
        else:
            order.save(update_fields=['plan_score', 'plan_rank', 'updated_at'])
        updated += 1
    return updated


@transaction.atomic
def save_plan_hops(*, order_id: int, hops: list[dict]) -> list[SxSalesOrderPlanStep]:
    """Cập nhật phút kiểm đếm / vận chuyển trên từng khoảng CĐ (đơn đã xác nhận)."""
    from san_xuat.services.plan_route import ensure_order_plan_steps

    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ chỉnh thời gian chuyển CĐ trên đơn đã xác nhận.')
    if order.plan_status == SxSalesOrder.PLAN_DONE:
        raise PlanningError('Đơn đã hoàn thành.')
    steps = ensure_order_plan_steps(order)
    if len(steps) < 2:
        raise PlanningError('Đơn chưa có đủ công đoạn để khai báo khoảng chuyển.')
    by_id = {s.pk: s for s in steps}
    updated = 0
    for raw in hops or []:
        try:
            sid = int(raw.get('step_id') or 0)
        except (TypeError, ValueError):
            continue
        step = by_id.get(sid)
        if step is None:
            continue
        try:
            count = _q(raw.get('count_minutes') or 0)
            transfer = _q(raw.get('transfer_minutes') or 0)
        except Exception:
            raise PlanningError('Phút kiểm đếm / vận chuyển không hợp lệ.')
        if count < 0 or transfer < 0:
            raise PlanningError('Phút kiểm đếm / vận chuyển không được âm.')
        step.count_minutes = count
        step.transfer_minutes = transfer
        step.save(update_fields=['count_minutes', 'transfer_minutes'])
        updated += 1
    if not updated:
        raise PlanningError('Không cập nhật được khoảng công đoạn.')
    return list(order.plan_steps.order_by('sequence', 'id'))


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
        .prefetch_related('lines__routing_lines__work_center', 'plan_steps')
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

    # planned_date + hop times từ snapshot kế hoạch — khớp theo tên công đoạn
    planned_by_name = {
        (s.process_name or '').strip().casefold(): s.planned_date
        for s in order.plan_steps.all()
        if s.planned_date
    }
    from san_xuat.services.inter_step_times import hop_pair_map, resolve_adjacent_hop

    plan_step_rows = list(order.plan_steps.all())
    hop_by_name = {}
    if plan_step_rows:
        pairs = hop_pair_map()
        for i, s in enumerate(plan_step_rows):
            nxt = plan_step_rows[i + 1] if i + 1 < len(plan_step_rows) else None
            key = (s.process_name or '').strip().casefold()
            hop_by_name[key] = resolve_adjacent_hop(s, nxt, fill_default=True, pairs=pairs)

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

        from san_xuat.services.inter_step_times import schedule_span
        from san_xuat.services.order_routing import sales_order_line_routing as _line_routing

        line_routing = _line_routing(ln)
        lead = (line_routing.total_smv * ln.qty_to_produce) + line_routing.hop_buffer_minutes
        plan_anchor = order.plan_start_date or order.request_date or timezone.localdate()
        plan_start, plan_end = schedule_span(
            start=plan_anchor,
            lead_minutes=lead,
            minutes_per_day=PLAN_SHIFT_MINUTES,
        )

        mo = None
        try:
            mo = create_mo_from_bom(
                product_code=code,
                qty=ln.qty_to_produce,
                order_date=timezone.localdate(),
                due_date=ln.due_date or order.due_date,
                planned_start=plan_start,
                planned_end=plan_end,
                notes=f'Từ ĐĐH {order.code}',
                user=user,
                sales_order_id=order.pk,
                bom_version_id=bom_id,
                routing_id=routing_id,
            )
            # Ưu tiên snapshot CĐ trên dòng đơn; fallback routing mã hàng; không thì BOM
            routing_steps = steps_dicts_from_order_line(ln) or steps_dicts_from_routing(routing_id)
            if routing_steps:
                for row in routing_steps:
                    key = (row.get('process_name') or '').strip().casefold()
                    if key in planned_by_name:
                        row['planned_date'] = planned_by_name[key]
                    if key in hop_by_name:
                        row['count_minutes'], row['transfer_minutes'] = hop_by_name[key]
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


@transaction.atomic
def unrelease_order_from_production(*, order_id: int) -> tuple[SxSalesOrder, int]:
    """Hủy chuyển SX: hủy LSX chưa phát sinh SX, đơn về hàng đợi để sửa lại."""
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ hủy chuyển đơn đã xác nhận.')
    if order.plan_status == SxSalesOrder.PLAN_ON_HOLD:
        raise PlanningError('Đơn đang tạm giữ.')
    if order.plan_status == SxSalesOrder.PLAN_DONE:
        raise PlanningError('Đơn đã hoàn thành — không hủy chuyển SX.')

    mos = list(
        order.production_orders.filter(is_demo=False)
        .exclude(status=SxProductionOrder.STATUS_CANCELLED)
        .select_for_update()
    )
    if not mos:
        order.plan_status = SxSalesOrder.PLAN_QUEUED
        order.plan_rank = None
        order.plan_hold_reason = ''
        order.save(update_fields=['plan_status', 'plan_rank', 'plan_hold_reason', 'updated_at'])
        return order, 0

    _assert_order_unreleasable(order, mos)

    cancelled = 0
    for mo in mos:
        mo.status = SxProductionOrder.STATUS_CANCELLED
        mo.save(update_fields=['status'])
        cancelled += 1

    from san_xuat.hub_models import SxTeamWorkClose

    SxTeamWorkClose.objects.filter(production_order_id__in=[m.pk for m in mos]).delete()

    order.plan_status = SxSalesOrder.PLAN_QUEUED
    order.plan_rank = None
    order.plan_hold_reason = ''
    order.save(update_fields=['plan_status', 'plan_rank', 'plan_hold_reason', 'updated_at'])
    return order, cancelled


@transaction.atomic
def reschedule_order_plan_start(*, order_id: int, start_date: date) -> SxSalesOrder:
    """Kéo thả lộ trình: neo ngày bắt đầu KHSX (chỉ đơn chưa chuyển SX)."""
    if not isinstance(start_date, date):
        raise PlanningError('Ngày bắt đầu không hợp lệ.')
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ xếp lịch đơn đã xác nhận.')
    if order.plan_status not in QUEUE_STATUSES:
        raise PlanningError('Chỉ kéo thả đơn chưa chuyển SX.')
    if order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    ).exists():
        raise PlanningError('Đơn đã có LSX — hủy chuyển SX trước khi xếp lại lịch.')
    order.plan_start_date = start_date
    order.save(update_fields=['plan_start_date', 'updated_at'])
    return order


@transaction.atomic
def reschedule_order_team_start(*, order_id: int, start_date: date, team_slug: str = '') -> SxSalesOrder:
    """Kéo thả một tổ trên lộ trình — các tổ khác giữ nguyên ngày."""
    if not isinstance(start_date, date):
        raise PlanningError('Ngày bắt đầu không hợp lệ.')
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ xếp lịch đơn đã xác nhận.')
    if order.plan_status not in QUEUE_STATUSES:
        raise PlanningError('Chỉ kéo thả đơn chưa chuyển SX.')
    if order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    ).exists():
        raise PlanningError('Đơn đã có LSX — hủy chuyển SX trước khi xếp lại lịch.')

    from san_xuat.services.inter_step_times import _step_team_slug
    from san_xuat.services.plan_route import ensure_order_plan_steps

    steps = ensure_order_plan_steps(order)
    spans = team_khsx_spans(order, plan_steps=steps)
    if not spans:
        raise PlanningError('Đơn chưa có tổ trên Ob để xếp lịch.')
    slug = (team_slug or '').strip().lower()
    if not slug:
        slug = spans[0].slug
    valid = {s.slug for s in spans}
    if slug not in valid:
        raise PlanningError('Tổ này không tham gia đơn.')

    any_pinned = any(getattr(s, 'planned_date', None) for s in steps)
    if not any_pinned:
        by_start = {s.slug: s.start for s in spans}
        for step in steps:
            st = (_step_team_slug(step) or '').strip().lower()
            if st and st in by_start:
                step.planned_date = by_start[st]
                step.save(update_fields=['planned_date'])

    for step in steps:
        st = (_step_team_slug(step) or '').strip().lower()
        if st == slug:
            step.planned_date = start_date
            step.save(update_fields=['planned_date'])

    steps = list(order.plan_steps.select_related('work_center').order_by('sequence', 'id'))
    spans = team_khsx_spans(order, plan_steps=steps)
    starts = [s.start for s in spans if s.start]
    if starts:
        order.plan_start_date = min(starts)
        order.save(update_fields=['plan_start_date', 'updated_at'])
    return order


def load_snapshot_for_board(*, days: int = 14) -> dict:
    """Năng lực tổ (tham khảo) cho tab board — không xếp lịch."""
    centers = list(
        SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by('code')
    )
    return {'centers': centers}


TIMELINE_DAYS = 28
TIMELINE_MAX_DAYS = 93


_WD_VN = ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')


@dataclass
class TimelineDay:
    date: date
    day: int
    weekday: str
    is_today: bool
    is_weekend: bool
    is_week_start: bool


@dataclass
class MoTimelineRow:
    mo: SxProductionOrder
    start: date
    end: date
    col_start: int
    col_end: int
    span_days: int
    vis_days: int
    bar_text: str
    is_today: bool
    is_late: bool
    clips_left: bool
    clips_right: bool
    status_key: str
    status_label: str


@dataclass
class TeamTimelineBar:
    """Một thanh tổ trên timeline KHSX."""

    slug: str
    label: str
    start: date
    end: date
    col_start: int
    col_end: int
    vis_days: int
    bar_text: str
    clips_left: bool
    clips_right: bool
    can_drag: bool
    span_days: int
    minutes: Decimal
    duration_label: str
    grid_row: int
    is_first: bool = False
    placed: bool = True


@dataclass
class PlanTimelineRow:
    """Thẻ đơn trên lộ trình — bên trong nhiều thanh tổ."""

    order: SxSalesOrder
    start: date
    end: date
    col_start: int
    col_end: int
    vis_days: int
    bar_text: str
    is_late: bool
    clips_left: bool
    clips_right: bool
    status_key: str
    status_label: str
    duration_label: str
    duration_script_id: str
    subtitle: str
    duration_detail: dict = field(default_factory=dict)
    can_drag: bool = False
    span_days: int = 1
    accepted_teams: list = field(default_factory=list)
    teams: list[TeamTimelineBar] = field(default_factory=list)


@dataclass
class MoTimelineBoard:
    range_start: date
    range_end: date
    days: list[TimelineDay]
    month_spans: list[dict]
    rows: list[MoTimelineRow]
    today: date
    today_col: int | None
    prev_from: date
    prev_to: date
    next_from: date
    next_to: date
    unscheduled: list
    search: str = ''
    month_label: str = ''
    is_current_month: bool = False


def _monday_on_or_before(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _month_bounds(d: date) -> tuple[date, date]:
    """Ngày đầu / cuối tháng chứa ``d``."""
    start = d.replace(day=1)
    if start.month == 12:
        nxt = date(start.year + 1, 1, 1)
    else:
        nxt = date(start.year, start.month + 1, 1)
    return start, nxt - timedelta(days=1)


def _shift_month(d: date, delta: int) -> date:
    """Ngày 1 của tháng ``d`` dịch ``delta`` tháng."""
    y = d.year
    m = d.month + int(delta)
    while m < 1:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return date(y, m, 1)


def _month_label(d: date) -> str:
    return f'Tháng {d.month}/{d.year}'


def _accepted_teams_by_order_ids(order_ids: list[int]) -> dict[int, list[dict]]:
    """Tổ đã nhận SX theo ĐĐH — gom từ mọi LSX của đơn."""
    from san_xuat.hub_models import SxTeamWorkAccept
    from san_xuat.services.progress_template import team_by_slug
    from san_xuat.services.team_work import _person_label

    ids = [int(x) for x in order_ids if x]
    if not ids:
        return {}
    qs = (
        SxTeamWorkAccept.objects.filter(
            is_demo=False,
            production_order__is_demo=False,
            production_order__sales_order_id__in=ids,
        )
        .exclude(production_order__status=SxProductionOrder.STATUS_CANCELLED)
        .select_related('created_by', 'created_by__profile', 'production_order')
        .order_by('accepted_at', 'id')
    )
    out: dict[int, list[dict]] = {oid: [] for oid in ids}
    seen: dict[int, set[str]] = {oid: set() for oid in ids}
    for rec in qs:
        oid = rec.production_order.sales_order_id
        if not oid or oid not in seen:
            continue
        slug = (rec.team_slug or '').strip().lower()
        if not slug or slug in seen[oid]:
            continue
        seen[oid].add(slug)
        meta = team_by_slug(slug) or {}
        out[oid].append({
            'slug': slug,
            'label': meta.get('label') or slug,
            'at': timezone.localtime(rec.accepted_at).strftime('%d/%m %H:%M') if rec.accepted_at else '',
            'by': _person_label(rec.created_by),
        })
    return out


def _timeline_range(
    range_from: date | None,
    range_to: date | None,
    *,
    today: date,
    days: int = TIMELINE_DAYS,
) -> tuple[date, date]:
    start = range_from
    end = range_to
    if start and end and end < start:
        start, end = end, start
    span_min = max(7, int(days or TIMELINE_DAYS))
    if start and not end:
        end = start + timedelta(days=span_min - 1)
    elif end and not start:
        start = end - timedelta(days=span_min - 1)
    elif not start and not end:
        start = _monday_on_or_before(today)
        end = start + timedelta(days=span_min - 1)
    span = (end - start).days + 1
    if span < 1:
        return start, start
    if span > TIMELINE_MAX_DAYS:
        end = start + timedelta(days=TIMELINE_MAX_DAYS - 1)
    return start, end


def _timeline_axis(start: date, end: date, today: date) -> tuple[list[TimelineDay], list[dict], int]:
    span = (end - start).days + 1
    if span < 1:
        span = 1
        end = start
    day_list = [start + timedelta(days=i) for i in range(span)]
    axis_days: list[TimelineDay] = []
    month_spans: list[dict] = []
    for d in day_list:
        axis_days.append(
            TimelineDay(
                date=d,
                day=d.day,
                weekday=_WD_VN[d.weekday()],
                is_today=d == today,
                is_weekend=d.weekday() >= 5,
                is_week_start=d.weekday() == 0,
            )
        )
        key = (d.year, d.month)
        if month_spans and month_spans[-1]['key'] == key:
            month_spans[-1]['span'] += 1
        else:
            month_spans.append({
                'key': key,
                'label': f'Tháng {d.month:02d}/{d.year}',
                'span': 1,
            })
    col = 2
    for m in month_spans:
        m['grid_start'] = col
        m['grid_end'] = col + m['span']
        col += m['span']
    return axis_days, month_spans, span


def _bar_columns(bar_start: date, bar_end: date, start: date, end: date) -> tuple[int, int, int] | None:
    if bar_end < start or bar_start > end:
        return None
    vis_start = max(bar_start, start)
    vis_end = min(bar_end, end)
    offset = (vis_start - start).days
    length = (vis_end - vis_start).days + 1
    return offset + 1, offset + length + 1, length


def build_mo_timeline(
    *,
    range_from: date | None = None,
    range_to: date | None = None,
    days: int = TIMELINE_DAYS,
    search: str = '',
) -> MoTimelineBoard:
    """Timeline LSX theo ngày bắt đầu / kết thúc dự kiến."""
    today = timezone.localdate()
    start, end = _timeline_range(range_from, range_to, today=today, days=days)
    axis_days, month_spans, span = _timeline_axis(start, end, today)

    qs = (
        SxProductionOrder.objects.filter(is_demo=False)
        .exclude(status=SxProductionOrder.STATUS_CANCELLED)
        .select_related('sales_order')
        .order_by('planned_start', 'planned_end', 'code')
    )
    term = (search or '').strip()
    if term:
        from django.db.models import Q

        qs = qs.filter(
            Q(code__icontains=term)
            | Q(product_code__icontains=term)
            | Q(product_name__icontains=term)
            | Q(team_label__icontains=term)
            | Q(sales_order__code__icontains=term)
        )

    rows: list[MoTimelineRow] = []
    unscheduled: list = []
    for mo in qs[:400]:
        raw_start = mo.planned_start
        raw_end = mo.planned_end
        if raw_start and raw_end and raw_end < raw_start:
            raw_start, raw_end = raw_end, raw_start
        if not raw_start and not raw_end:
            unscheduled.append(mo)
            continue
        bar_start = raw_start or raw_end
        bar_end = raw_end or raw_start
        placed = _bar_columns(bar_start, bar_end, start, end)
        if placed is None:
            continue
        col_start, col_end, length = placed
        if length >= 6:
            bar_text = f"{max(bar_start, start).strftime('%d/%m')} – {min(bar_end, end).strftime('%d/%m')}"
        elif length >= 3:
            bar_text = f"SL {format_sx_num_input(mo.qty)}"
        else:
            bar_text = ''
        rows.append(MoTimelineRow(
            mo=mo,
            start=bar_start,
            end=bar_end,
            col_start=col_start,
            col_end=col_end,
            span_days=(bar_end - bar_start).days + 1,
            vis_days=length,
            bar_text=bar_text,
            is_today=start <= today <= end and bar_start <= today <= bar_end,
            is_late=bool(bar_end < today and mo.status != SxProductionOrder.STATUS_DONE),
            clips_left=bar_start < start,
            clips_right=bar_end > end,
            status_key=mo.status,
            status_label=mo.get_status_display(),
        ))

    today_col = (today - start).days + 1 if start <= today <= end else None

    return MoTimelineBoard(
        range_start=start,
        range_end=end,
        days=axis_days,
        month_spans=month_spans,
        rows=rows,
        today=today,
        today_col=today_col,
        prev_from=start - timedelta(days=span),
        prev_to=start - timedelta(days=1),
        next_from=end + timedelta(days=1),
        next_to=end + timedelta(days=span),
        unscheduled=unscheduled[:80],
        search=term,
    )


def build_order_timeline(
    plan_rows: list[PlanBoardRow],
    *,
    range_from: date | None = None,
    range_to: date | None = None,
) -> MoTimelineBoard:
    """Timeline đơn trên KHSX — mặc định tháng hiện tại."""
    today = timezone.localdate()
    if not range_from and not range_to:
        range_from, range_to = _month_bounds(today)
    elif range_from and not range_to:
        range_from, range_to = _month_bounds(range_from)
    elif range_to and not range_from:
        range_from, range_to = _month_bounds(range_to)
    start, end = _timeline_range(range_from, range_to, today=today)
    axis_days, month_spans, span = _timeline_axis(start, end, today)

    accepts_by_order = _accepted_teams_by_order_ids([r.order.pk for r in plan_rows])

    rows: list[PlanTimelineRow] = []
    unscheduled: list = []
    grid_row = 3
    for r in plan_rows:
        bar_start = r.khsx_start
        bar_end = r.khsx_end or r.khsx_start
        if not bar_start:
            unscheduled.append(r.order)
            continue
        if bar_end < bar_start:
            bar_start, bar_end = bar_end, bar_start
        team_spans = list(r.team_spans or [])
        visible_spans = []
        for ts in team_spans:
            placed_team = _bar_columns(ts.start, ts.end or ts.start, start, end)
            if placed_team is not None:
                visible_spans.append((ts, placed_team))
        overall_placed = _bar_columns(bar_start, bar_end, start, end)
        if team_spans and not visible_spans:
            continue
        if not team_spans and overall_placed is None:
            continue
        if overall_placed is None:
            overall_placed = (1, 2, 1)
        col_start, col_end, length = overall_placed
        clock = (r.duration_label or '').split('·')[0].strip()
        if clock:
            bar_text = clock
        elif length >= 4:
            bar_text = f"{max(bar_start, start).strftime('%d/%m')} – {min(bar_end, end).strftime('%d/%m')}"
        else:
            bar_text = ''
        names = [pf.product_name or pf.product_code for pf in (r.product_flows or [])]
        subtitle = (r.order.customer_name or '').strip()
        if names:
            extra = names[0] if len(names) == 1 else f'{len(names)} mã'
            subtitle = f'{subtitle} · {extra}' if subtitle else extra
        can_drag = r.order.plan_status in QUEUE_STATUSES and r.mo_count == 0
        span_days = max(1, (bar_end - bar_start).days + 1)
        status_key = r.order.plan_status
        if status_key == SxSalesOrder.PLAN_RANKED:
            status_key = SxSalesOrder.PLAN_QUEUED
        status_label = (
            'Chờ xếp' if status_key == SxSalesOrder.PLAN_QUEUED
            else r.order.get_plan_status_display()
        )
        team_bars: list[TeamTimelineBar] = []
        if visible_spans:
            for i, (ts, placed_team) in enumerate(visible_spans):
                t_col_s, t_col_e, t_len = placed_team
                t_clock = (ts.duration_label or '').split('·')[0].strip()
                if t_len >= 4 and t_clock:
                    t_text = f'{ts.label} · {t_clock}'
                else:
                    t_text = ts.label
                team_bars.append(TeamTimelineBar(
                    slug=ts.slug,
                    label=ts.label,
                    start=ts.start,
                    end=ts.end,
                    col_start=t_col_s,
                    col_end=t_col_e,
                    vis_days=t_len,
                    bar_text=t_text,
                    clips_left=ts.start < start,
                    clips_right=ts.end > end,
                    can_drag=can_drag,
                    span_days=max(1, (ts.end - ts.start).days + 1),
                    minutes=ts.minutes,
                    duration_label=ts.duration_label or '',
                    grid_row=grid_row,
                    is_first=(i == 0),
                    placed=True,
                ))
        else:
            team_bars.append(TeamTimelineBar(
                slug='',
                label='Chưa có công đoạn',
                start=bar_start,
                end=bar_end,
                col_start=col_start,
                col_end=col_end,
                vis_days=length,
                bar_text='',
                clips_left=False,
                clips_right=False,
                can_drag=False,
                span_days=span_days,
                minutes=Decimal('0'),
                duration_label='',
                grid_row=grid_row,
                is_first=True,
                placed=False,
            ))
        grid_row += 1
        rows.append(PlanTimelineRow(
            order=r.order,
            start=bar_start,
            end=bar_end,
            col_start=col_start,
            col_end=col_end,
            vis_days=length,
            bar_text=bar_text,
            is_late=bool(r.is_overdue or r.khsx_overrun),
            clips_left=bar_start < start,
            clips_right=bar_end > end,
            status_key=status_key,
            status_label=status_label,
            duration_label=r.duration_label or '',
            duration_script_id=r.duration_script_id or '',
            subtitle=subtitle,
            duration_detail=r.duration_detail or {},
            can_drag=can_drag,
            span_days=span_days,
            accepted_teams=accepts_by_order.get(r.order.pk, []),
            teams=team_bars,
        ))

    today_col = (today - start).days + 1 if start <= today <= end else None
    cur_month_start, cur_month_end = _month_bounds(today)
    anchor = _month_bounds(start)[0]
    prev_month = _shift_month(anchor, -1)
    next_month = _shift_month(anchor, 1)
    prev_from, prev_to = _month_bounds(prev_month)
    next_from, next_to = _month_bounds(next_month)
    return MoTimelineBoard(
        range_start=start,
        range_end=end,
        days=axis_days,
        month_spans=month_spans,
        rows=rows,
        today=today,
        today_col=today_col,
        prev_from=prev_from,
        prev_to=prev_to,
        next_from=next_from,
        next_to=next_to,
        unscheduled=unscheduled[:80],
        search='',
        month_label=_month_label(start),
        is_current_month=(start == cur_month_start and end == cur_month_end),
    )


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
