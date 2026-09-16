"""Kế hoạch sản xuất theo đơn (MTO board) — hàng đợi, xếp hạng, chuyển LSX.

Phase 1: chỉ ĐĐH đã xác nhận. MTS/MPS swimlane sau.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from san_xuat.hub_models import (
    SxMaterialPlan,
    SxNplPurchaseRequest,
    SxOrderTeamDayPlan,
    SxOverallPlan,
    SxProductionOrder,
    SxProductionStat,
    SxSalesOrder,
    SxSalesOrderLine,
    SxSalesOrderPlanStep,
    SxWorkCenter,
)
from san_xuat.services.dispatch import DispatchError, create_mo_from_bom
from san_xuat.services.planning import PlanningError
from san_xuat.services.order_routing import sales_order_line_routing, steps_dicts_from_order_line
from san_xuat.templatetags.sx_format import format_sx_num_input

_Q2 = Decimal('0.01')
# Ca KHSX mặc định: 9 giờ 30 phút
PLAN_SHIFT_MINUTES = Decimal('570')
PLAN_SHIFT_LABEL = '9 giờ 30 phút'


def _line_has_operations(order_line: SxSalesOrderLine, *, routing_id=None, bom=None) -> bool:
    """True nếu dòng đã có công đoạn: snapshot đơn, OB/routing, hoặc CĐ trên BOM."""
    if steps_dicts_from_order_line(order_line):
        return True
    from san_xuat.services.dispatch import steps_dicts_from_routing

    rid = routing_id if routing_id is not None else order_line.routing_id
    if steps_dicts_from_routing(rid):
        return True
    src_bom = bom if bom is not None else getattr(order_line, 'bom_version', None)
    if src_bom is not None:
        steps = getattr(src_bom, 'process_steps', None)
        if steps is not None and steps.exists():
            return True
    return False


def _tech_choices_for_code(product_code: str, cache: dict) -> dict:
    """BOM / OB dropdown trên ticket KHSX — cache theo mã trong một lần build board."""
    from urllib.parse import urlencode

    from django.urls import reverse

    from san_xuat.services.order_routing import boms_for_product, routings_for_product
    from san_xuat.services.products import find_tech_doc_for_code

    key = (product_code or '').strip().casefold()
    empty = {
        'boms': [],
        'routings': [],
        'bom_create_url': '',
        'routing_create_url': '',
    }
    if not key:
        return empty
    if key in cache:
        return cache[key]
    code = (product_code or '').strip()
    create_url = reverse('san_xuat:doc_create') + (f'?code={code}' if code else '')
    routing_qs = {'style_code': code} if code else {}
    routing_create = reverse('san_xuat:ie_routing_create') + (
        ('?' + urlencode(routing_qs)) if routing_qs else ''
    )
    doc = find_tech_doc_for_code(code)
    if doc:
        doc_url = reverse('san_xuat:doc_detail', kwargs={'pk': doc.pk})
        bom_url = doc_url + ('&' if '?' in doc_url else '?') + 'tab=bom&edit=1'
        rt_url = doc_url + ('&' if '?' in doc_url else '?') + 'tab=process&edit=1'
        style = (doc.product_code or code).strip()
        rq = {'style_code': style}
        if (doc.product_name or '').strip():
            rq['style_name'] = doc.product_name.strip()
        routing_create = reverse('san_xuat:ie_routing_create') + '?' + urlencode(rq)
    else:
        bom_url = create_url
        rt_url = routing_create
    payload = {
        'boms': [
            {'id': b.pk, 'label': (b.version_label or '').strip() or f'#{b.pk}'}
            for b in boms_for_product(product_code)
        ],
        'routings': [
            {'id': r.pk, 'label': (r.routing_rev or '').strip() or f'#{r.pk}'}
            for r in routings_for_product(product_code)
        ],
        'bom_create_url': bom_url,
        'routing_create_url': rt_url,
    }
    cache[key] = payload
    return payload


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

# Tab kế hoạch gộp hàng đợi + đã chuyển SX
BOARD_LIST_STATUSES = QUEUE_STATUSES + (
    SxSalesOrder.PLAN_RELEASED,
    SxSalesOrder.PLAN_IN_PROGRESS,
    SxSalesOrder.PLAN_DONE,
)

ACTIVE_MO_STATUSES = (
    SxProductionOrder.STATUS_DRAFT,
    SxProductionOrder.STATUS_RELEASED,
    SxProductionOrder.STATUS_IN_PROGRESS,
    SxProductionOrder.STATUS_DONE,
)


ROUTE_TRACK_COUNT = 10
ROUTE_TRACK_COLORS = (
    ('#dc2626', '#fef2f2'),
    ('#2563eb', '#eff6ff'),
    ('#059669', '#ecfdf5'),
    ('#d97706', '#fffbeb'),
    ('#7c3aed', '#f5f3ff'),
    ('#db2777', '#fdf2f8'),
    ('#0f766e', '#f0fdfa'),
    ('#ea580c', '#fff7ed'),
    ('#4f46e5', '#eef2ff'),
    ('#4d7c0f', '#f7fee7'),
)


def route_track_index(order_id: int) -> int:
    """Chỉ số màu ổn định theo đơn — lần Cắt/May/Ủi cùng một sắc."""
    return (int(order_id or 0) * 7 + 3) % ROUTE_TRACK_COUNT


def normalize_plan_color(raw: str, *, allow_empty: bool = False) -> str:
    text = (raw or '').strip().lower()
    if text.startswith('#') and len(text) == 7:
        hex_part = text[1:]
    elif len(text) == 6:
        hex_part = text
        text = f'#{hex_part}'
    elif allow_empty and text == '':
        return ''
    else:
        raise PlanningError('Màu không hợp lệ — chọn mã #RRGGBB.')
    if any(ch not in '0123456789abcdef' for ch in hex_part):
        raise PlanningError('Màu không hợp lệ — chọn mã #RRGGBB.')
    return text


def mix_track_soft(hex_color: str) -> str:
    color = normalize_plan_color(hex_color)
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    red = min(255, int(red + (255 - red) * 0.88))
    green = min(255, int(green + (255 - green) * 0.88))
    blue = min(255, int(blue + (255 - blue) * 0.88))
    return f'#{red:02x}{green:02x}{blue:02x}'


def route_track_pair(order: SxSalesOrder) -> tuple[str, str]:
    custom = (getattr(order, 'plan_color', '') or '').strip()
    if custom:
        try:
            color = normalize_plan_color(custom)
            return color, mix_track_soft(color)
        except PlanningError:
            pass
    idx = route_track_index(order.pk)
    return ROUTE_TRACK_COLORS[idx]


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
    subcontract: object | None = None
    subcontracts: list = field(default_factory=list)
    missing_bom: bool = False
    missing_ops: bool = False
    npl_status: str = SxSalesOrder.NPL_NONE
    npl_ready_date: date | None = None
    npl_lead_days: int = 0
    npl_short_count: int = 0
    npl_ok_count: int = 0
    npl_missing_buy: bool = False
    npl_plan_id: int = 0
    npl_plan_code: str = ''
    npl_pr_id: int = 0
    npl_pr_code: str = ''
    show_npl_uom_col: bool = False
    timeline_steps: list = field(default_factory=list)

    @property
    def in_queue(self) -> bool:
        return self.order.plan_status in QUEUE_STATUSES

    @property
    def is_released(self) -> bool:
        return self.order.plan_status in (
            SxSalesOrder.PLAN_RELEASED,
            SxSalesOrder.PLAN_IN_PROGRESS,
            SxSalesOrder.PLAN_DONE,
        )

    @property
    def can_adjust_timeline(self) -> bool:
        return self.order.plan_status not in (
            SxSalesOrder.PLAN_ON_HOLD,
            SxSalesOrder.PLAN_DONE,
        )

    @property
    def can_edit_npl(self) -> bool:
        return self.order.plan_status in (
            SxSalesOrder.PLAN_QUEUED,
            SxSalesOrder.PLAN_RANKED,
        )

    @property
    def npl_step(self):
        for step in self.timeline_steps:
            if getattr(step, 'kind', '') == 'npl':
                return step
        return None


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
    production_order_id: int = 0
    has_bom: bool = False
    has_ops: bool = False
    bom_label: str = ''
    routing_label: str = ''
    available_boms: list = field(default_factory=list)
    available_routings: list = field(default_factory=list)
    bom_create_url: str = ''
    routing_create_url: str = ''
    image_url: str = ''
    image_urls: list = field(default_factory=list)

    @property
    def image_urls_json(self) -> str:
        urls = self.image_urls or ([self.image_url] if self.image_url else [])
        return json.dumps(urls, ensure_ascii=False)


@dataclass
class TeamDayPiece:
    """Một thẻ ngày đã tách của tổ trên KHSX."""

    plan_date: date
    qty: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_label: str = ''


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
    can_drag: bool = True
    day_pieces: list[TeamDayPiece] = field(default_factory=list)
    labor_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    headcount: int = 0
    efficiency_pct: Decimal = field(default_factory=lambda: Decimal('0'))
    catalog_headcount: int = 0
    catalog_efficiency_pct: Decimal = field(default_factory=lambda: Decimal('0'))
    work_hours_per_day: Decimal = field(default_factory=lambda: Decimal('0'))
    capacity_minutes_per_day: Decimal = field(default_factory=lambda: Decimal('0'))
    work_center_id: int = 0
    smv_seconds: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_per_day: Decimal = field(default_factory=lambda: Decimal('0'))
    planned_qty: Decimal = field(default_factory=lambda: Decimal('0'))


@dataclass
class TicketTimelineStep:
    """Một nấc trên timeline ticket KHSX: tổ → nhập kho. NPL tách khỏi trục công đoạn."""

    slug: str
    kind: str
    label: str
    start: date | None = None
    end: date | None = None
    duration_label: str = ''
    days: int = 0
    status: str = ''
    flex: int = 1
    is_late: bool = False
    process_count: int = 0
    product_groups: list[dict] = field(default_factory=list)
    subcontracts: list = field(default_factory=list)
    hop_step_id: int = 0
    hop_process_name: str = ''
    hop_count_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    hop_transfer_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    can_edit_hop: bool = False
    qty_label: str = ''
    team_qty_total: str = ''
    show_connector: bool = True
    split_index: int = 0
    split_count: int = 1
    work_center_id: int = 0
    headcount: int = 0
    efficiency_pct: Decimal = field(default_factory=lambda: Decimal('0'))
    catalog_headcount: int = 0
    catalog_efficiency_pct: Decimal = field(default_factory=lambda: Decimal('0'))
    work_hours_per_day: Decimal = field(default_factory=lambda: Decimal('0'))
    labor_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    capacity_minutes_per_day: Decimal = field(default_factory=lambda: Decimal('0'))
    smv_seconds: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_per_day: Decimal = field(default_factory=lambda: Decimal('0'))
    planned_qty: Decimal = field(default_factory=lambda: Decimal('0'))

    @property
    def unhired_product_groups(self) -> list[dict]:
        return [pg for pg in self.product_groups if not pg.get('subcontracts')]

    @property
    def date_label(self) -> str:
        if not self.start:
            return ''
        a = self.start.strftime('%d/%m')
        if not self.end or self.end == self.start:
            return a
        if self.start.month == self.end.month:
            return f'{self.start.strftime("%d")}–{self.end.strftime("%d/%m")}'
        return f'{a}–{self.end.strftime("%d/%m")}'


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


def _wc_has_capacity(wc: SxWorkCenter | None) -> bool:
    if wc is None:
        return False
    if _q(getattr(wc, 'available_minutes_per_day', 0)) > 0:
        return True
    return _q(getattr(wc, 'capacity_per_day', 0)) > 0


def _work_center_catalog_by_slug() -> dict[str, SxWorkCenter]:
    """Tổ Năng lực SX mặc định theo slug KHSX (cat/may/…) — ưu tiên tổ có quỹ phút."""
    from san_xuat.services.capacity_from_hrm import team_slug_for_work_center

    ranked: dict[str, tuple[tuple[int, int], SxWorkCenter]] = {}
    qs = SxWorkCenter.objects.filter(is_active=True)
    if hasattr(SxWorkCenter, 'is_demo'):
        qs = qs.filter(is_demo=False)
    if hasattr(SxWorkCenter, 'is_subcontract'):
        qs = qs.filter(is_subcontract=False)
    for wc in qs.order_by('code', 'name'):
        slug = (team_slug_for_work_center(wc) or '').strip().lower()
        if not slug:
            continue
        cap = 1 if _wc_has_capacity(wc) else 0
        code = (wc.code or '').strip().upper()
        exact = 1 if code in {'CAT', 'IN-EP', 'THEU', 'MAY', 'HT', 'GH'} else 0
        key = (cap, exact)
        prev = ranked.get(slug)
        if prev is None or key > prev[0]:
            ranked[slug] = (key, wc)
    return {slug: wc for slug, (_key, wc) in ranked.items()}


def apply_default_capacity_teams(
    order: SxSalesOrder,
    steps=None,
    *,
    replace_without_capacity: bool = False,
) -> list:
    """Gán tổ Năng lực SX mặc định cho công đoạn chưa có tổ (hoặc tổ không có quỹ phút)."""
    from san_xuat.hub_models import SxSalesOrderRoutingLine
    from san_xuat.services.inter_step_times import (
        _group_slug_scope,
        _step_team_slug,
        attach_group_codes_from_routing,
    )

    steps = list(steps) if steps is not None else list(
        order.plan_steps.select_related('work_center').order_by('sequence', 'id'),
    )
    routing_lines = [
        rl
        for ln in order.lines.all()
        for rl in ln.routing_lines.select_related('work_center', 'operation__group').all()
    ]
    if steps:
        attach_group_codes_from_routing(steps, routing_lines)
    catalog = _work_center_catalog_by_slug()
    if not catalog:
        return steps
    dirty_steps: list[SxSalesOrderPlanStep] = []
    dirty_lines: list = []
    with _group_slug_scope():
        for step in steps:
            wc = getattr(step, 'work_center', None)
            keep = bool(step.work_center_id) and (
                _wc_has_capacity(wc) or not replace_without_capacity
            )
            if keep:
                continue
            slug = _plan_step_team_slug(step)
            default = catalog.get(slug)
            if default is None or step.work_center_id == default.pk:
                continue
            step.work_center = default
            dirty_steps.append(step)
        for rl in routing_lines:
            wc = getattr(rl, 'work_center', None)
            keep = bool(rl.work_center_id) and (
                _wc_has_capacity(wc) or not replace_without_capacity
            )
            if keep:
                continue
            slug = (_step_team_slug(rl) or '').strip().lower()
            default = catalog.get(slug)
            if default is None or rl.work_center_id == default.pk:
                continue
            rl.work_center = default
            rl.work_center_code = (default.code or '')[:40]
            dirty_lines.append(rl)
    if dirty_steps:
        SxSalesOrderPlanStep.objects.bulk_update(dirty_steps, ['work_center'])
    if dirty_lines:
        SxSalesOrderRoutingLine.objects.bulk_update(
            dirty_lines, ['work_center', 'work_center_code'],
        )
    return steps


def plan_board_work_center_options() -> list[dict]:
    """Danh sách tổ Năng lực SX để chọn trên menu ⋯."""
    qs = SxWorkCenter.objects.filter(is_active=True)
    if hasattr(SxWorkCenter, 'is_demo'):
        qs = qs.filter(is_demo=False)
    rows: list[dict] = []
    for wc in qs.order_by('code', 'name'):
        cap = _q(getattr(wc, 'available_minutes_per_day', 0))
        rows.append({
            'id': int(wc.pk),
            'code': wc.code or '',
            'name': (wc.team_label or wc.name or wc.code or '').strip(),
            'headcount': int(wc.headcount or 0),
            'minutes_per_day': format_sx_num_input(cap) if cap > 0 else '',
        })
    return rows


def _khsx_available_minutes(
    wc: SxWorkCenter | None,
    *,
    headcount: int | None = None,
    efficiency_pct=None,
) -> Decimal:
    """Quỹ phút/ngày theo số người × giờ/ca × hệ số tải — giờ ca lấy từ tổ NL (tham khảo)."""
    from san_xuat.hub_models import DEFAULT_SHIFT_MINUTES, DEFAULT_WORK_HOURS_PER_DAY

    heads = headcount
    if heads is None:
        heads = int(getattr(wc, 'headcount', 0) or 0) if wc is not None else 0
    heads = max(0, int(heads or 0))
    hours = Decimal('0')
    if wc is not None:
        hours = _q(getattr(wc, 'work_hours_per_day', 0) or 0)
    if hours <= 0:
        hours = DEFAULT_WORK_HOURS_PER_DAY
    shift = hours * Decimal('60')
    if shift <= 0:
        shift = Decimal(str(DEFAULT_SHIFT_MINUTES))
    if efficiency_pct is None:
        efficiency_pct = getattr(wc, 'efficiency_pct', None) if wc is not None else None
    load = _q(efficiency_pct if efficiency_pct is not None else 100) / Decimal('100')
    if load < 0:
        load = Decimal('0')
    return (Decimal(heads) * shift * load).quantize(Decimal('0.01'))


def _labor_to_calendar_minutes(
    labor: Decimal,
    wc: SxWorkCenter | None,
    *,
    qty: Decimal = Decimal('0'),
    headcount: int | None = None,
    efficiency_pct=None,
) -> Decimal:
    """Phút lịch (quy về 1 ca KHSX) = công SMV chia quỹ phút tổ / NL ngày."""
    labor = _q(labor, '0.0001')
    if labor <= 0:
        return Decimal('0')
    cap_min = _khsx_available_minutes(wc, headcount=headcount, efficiency_pct=efficiency_pct)
    if cap_min > 0:
        return _q(labor * PLAN_SHIFT_MINUTES / cap_min, '0.0001')
    if wc is not None and headcount is None and efficiency_pct is None:
        cap_qty = _q(getattr(wc, 'capacity_per_day', 0))
        qty_n = _q(qty)
        if cap_qty > 0 and qty_n > 0:
            return _q(qty_n / cap_qty * PLAN_SHIFT_MINUTES, '0.0001')
    return labor


def _floor_daily_qty(raw: Decimal) -> Decimal:
    """Làm tròn xuống SL/ngày: ≥100 thì xuống hàng trăm (627.25 → 600), không thì xuống số nguyên."""
    raw = _q(raw)
    if raw <= 0:
        return Decimal('0')
    if raw >= 100:
        return (raw / Decimal('100')).to_integral_value(rounding=ROUND_DOWN) * Decimal('100')
    n = raw.to_integral_value(rounding=ROUND_DOWN)
    return n if n > 0 else Decimal('1')


def _smv_seconds_per_unit(labor_minutes: Decimal, qty: Decimal) -> Decimal:
    """SMV (giây/sp) = tổng công hồ sơ thiết kế của tổ / SL đơn."""
    qty_n = _q(qty)
    labor = _q(labor_minutes, '0.0001')
    if qty_n <= 0 or labor <= 0:
        return Decimal('0')
    return _q(labor * Decimal('60') / qty_n, '0.0001')


def _daily_qty_capacity(smv_seconds, headcount, hours, efficiency_pct) -> Decimal:
    """SL/ngày = (số giờ × 3600 × hiệu suất / SMV) × số CN, làm tròn xuống hàng trăm."""
    from san_xuat.hub_models import DEFAULT_WORK_HOURS_PER_DAY

    smv = _q(smv_seconds, '0.0001')
    heads = max(0, int(headcount or 0))
    hrs = _q(hours)
    if hrs <= 0:
        hrs = DEFAULT_WORK_HOURS_PER_DAY
    load = _q(efficiency_pct if efficiency_pct is not None else 100) / Decimal('100')
    if load < 0:
        load = Decimal('0')
    if smv <= 0 or heads <= 0 or hrs <= 0:
        return Decimal('0')
    per_head = (hrs * Decimal('3600') * load) / smv
    return _floor_daily_qty(per_head * Decimal(heads))


def _auto_day_qty_rows(qty, qty_per_day) -> list[Decimal]:
    """2600 với 600/ngày → [600, 600, 600, 600, 200]."""
    total = _q(qty)
    daily = _q(qty_per_day)
    if total <= 0:
        return []
    if daily <= 0:
        return [total]
    rows: list[Decimal] = []
    remain = total
    for _ in range(800):
        if remain <= 0:
            break
        if remain > daily:
            rows.append(daily)
            remain = _q(remain - daily)
        else:
            rows.append(remain)
            remain = Decimal('0')
    if remain > 0:
        rows.append(remain)
    return rows


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
    from san_xuat.services.inter_step_times import (
        _group_slug_scope,
        _step_team_slug,
        flow_groups_from_steps,
    )

    work: dict[str, Decimal] = {}
    hops: dict[str, Decimal] = {}
    labels: dict[str, str] = {}
    assigned: dict[str, SxWorkCenter] = {}
    qty_by: dict[str, Decimal] = {}
    overrides: dict[str, dict] = {}
    line_slug_seen: set[tuple[int, str]] = set()
    lines = [ln for ln in order.lines.all() if (ln.qty or 0) > 0]
    with _group_slug_scope():
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
                wc = getattr(step, 'work_center', None)
                if wc is not None and slug not in assigned:
                    assigned[slug] = wc
                if slug not in labels:
                    wc_label = ''
                    if wc is not None:
                        wc_label = (wc.team_label or wc.name or '').strip()
                    labels[slug] = _team_display_label(slug, wc_label or step.team_label)
                line_key = (int(getattr(ln, 'pk', 0) or 0), slug)
                if line_key not in line_slug_seen:
                    line_slug_seen.add(line_key)
                    qty_by[slug] = qty_by.get(slug, Decimal('0')) + _q(qty)

        if product_flows:
            for pf in product_flows:
                _add_flow_hops(pf.flow_groups, hops)
        else:
            for ln in lines:
                routing = sales_order_line_routing(ln)
                if routing.steps:
                    _add_flow_hops(flow_groups_from_steps(routing.steps, sort_factory=True), hops)

    with _group_slug_scope():
        plan_mgr = getattr(order, 'plan_steps', None)
        plan_iter = list(plan_mgr.all()) if plan_mgr is not None else []
        for step in plan_iter:
            slug = _plan_step_team_slug(step)
            if not slug:
                continue
            wc = getattr(step, 'work_center', None)
            if wc is not None:
                assigned[slug] = wc
                wc_label = (wc.team_label or wc.name or '').strip()
                if wc_label:
                    labels[slug] = _team_display_label(slug, wc_label)
            ov_h = getattr(step, 'khsx_headcount', None)
            ov_e = getattr(step, 'khsx_efficiency_pct', None)
            if ov_h is not None or ov_e is not None:
                cur = overrides.get(slug) or {}
                if ov_h is not None:
                    cur['headcount'] = int(ov_h)
                if ov_e is not None:
                    cur['efficiency_pct'] = _q(ov_e)
                overrides[slug] = cur

    catalog: dict[str, SxWorkCenter] | None = None

    def _wc_for(slug: str) -> SxWorkCenter | None:
        nonlocal catalog
        found = assigned.get(slug)
        ov = overrides.get(slug) or {}
        if found is not None and (
            _wc_has_capacity(found) or ov.get('headcount') or ov.get('efficiency_pct')
        ):
            return found
        if catalog is None:
            catalog = _work_center_catalog_by_slug()
        default = catalog.get(slug)
        picked = default or found
        if picked is not None and slug not in assigned:
            assigned[slug] = picked
        return picked

    rank = _factory_slug_rank()
    slugs = sorted(work.keys(), key=lambda s: (rank.get(s, 99), s))
    out: list[dict] = []
    for slug in slugs:
        labor = _q(work.get(slug, Decimal('0')), '0.0001')
        wc = _wc_for(slug)
        ov = overrides.get(slug) or {}
        catalog_h = int(getattr(wc, 'headcount', 0) or 0) if wc is not None else 0
        catalog_e = _q(getattr(wc, 'efficiency_pct', 100) or 100) if wc is not None else Decimal('100')
        use_h = int(ov['headcount']) if 'headcount' in ov else catalog_h
        use_e = ov['efficiency_pct'] if 'efficiency_pct' in ov else catalog_e
        hours = _q(getattr(wc, 'work_hours_per_day', 0) or 0) if wc is not None else Decimal('0')
        if hours <= 0:
            from san_xuat.hub_models import DEFAULT_WORK_HOURS_PER_DAY
            hours = DEFAULT_WORK_HOURS_PER_DAY
        qty_n = _q(qty_by.get(slug, Decimal('0')))
        smv_sec = _smv_seconds_per_unit(labor, qty_n)
        qpd = _daily_qty_capacity(smv_sec, use_h, hours, use_e)
        n_days = len(_auto_day_qty_rows(qty_n, qpd)) if qpd > 0 and qty_n > 0 else 0
        if n_days > 0:
            calendar = _q(Decimal(n_days) * PLAN_SHIFT_MINUTES)
        else:
            calendar = _labor_to_calendar_minutes(
                labor, wc, qty=qty_n,
                headcount=use_h, efficiency_pct=use_e,
            )
        buf = _q(hops.get(slug, Decimal('0')))
        cap_min = _khsx_available_minutes(wc, headcount=use_h, efficiency_pct=use_e)
        wc_label = ''
        if wc is not None:
            wc_label = (wc.team_label or wc.name or '').strip()
        out.append({
            'slug': slug,
            'label': wc_label or labels.get(slug) or _team_display_label(slug),
            'labor_minutes': labor,
            'work_minutes': calendar,
            'buffer_minutes': buf,
            'minutes': _q(calendar + buf),
            'headcount': use_h,
            'efficiency_pct': _q(use_e),
            'catalog_headcount': catalog_h,
            'catalog_efficiency_pct': catalog_e,
            'work_hours_per_day': hours,
            'capacity_minutes_per_day': cap_min,
            'work_center_id': int(getattr(wc, 'pk', 0) or 0) if wc is not None else 0,
            'qty': qty_n,
            'smv_seconds': smv_sec,
            'qty_per_day': qpd,
        })
    return out


def _plan_step_team_slug(step) -> str:
    """Slug tổ của bước kế hoạch — group_code, rồi tên công đoạn."""
    from san_xuat.services.inter_step_times import _step_team_slug
    from san_xuat.services.progress_template import team_slug_for_process_label

    slug = (_step_team_slug(step) or '').strip().lower()
    if slug:
        return slug
    name = (getattr(step, 'process_name', None) or '').strip()
    return (team_slug_for_process_label(name) or '').strip().lower()


def _pinned_starts_from_steps(plan_steps) -> dict[str, date]:
    from san_xuat.services.inter_step_times import _group_slug_scope

    pinned: dict[str, date] = {}
    with _group_slug_scope():
        for step in plan_steps or []:
            slug = _plan_step_team_slug(step)
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
    """Span KHSX từng tổ: mặc định nối tiếp; tổ đã kéo dùng planned_date độc lập (được chồng ngày)."""
    from san_xuat.services.inter_step_times import schedule_span

    loads = _team_loads_from_order(order, product_flows=product_flows)
    today = today or timezone.localdate()
    from san_xuat.services.plan_order_npl import npl_span_for_order, production_start_for_order

    npl_pair = npl_span_for_order(order, today=today)
    npl_spans: list[TeamKhsxSpan] = []
    if npl_pair:
        npl_start, npl_end = npl_pair
        lead = int(order.npl_lead_days or 0)
        npl_spans.append(TeamKhsxSpan(
            slug='npl',
            label='Chuẩn bị nguyên phụ liệu',
            work_minutes=Decimal('0'),
            buffer_minutes=Decimal('0'),
            minutes=Decimal('0'),
            start=npl_start,
            end=npl_end,
            pinned=False,
            duration_label=f'{lead} ngày' if lead else '',
            duration_work_days=lead,
            can_drag=False,
        ))
    if not loads:
        return npl_spans
    anchor = production_start_for_order(order, today=today)
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
    day_plans_by_slug: dict[str, list] = {}
    cached = getattr(order, '_prefetched_objects_cache', {})
    if 'team_day_plans' in cached:
        day_iter = list(order.team_day_plans.all())
    elif getattr(order, 'pk', None):
        day_iter = list(
            SxOrderTeamDayPlan.objects.filter(sales_order_id=order.pk).order_by('plan_date', 'id')
        )
    else:
        day_iter = []
    for dp in day_iter:
        sk = (dp.team_slug or '').strip().lower()
        if sk:
            day_plans_by_slug.setdefault(sk, []).append(dp)

    for row in loads:
        slug = row['slug']
        is_pinned = slug in pinned
        start = pinned[slug] if is_pinned else defaults[slug][0]
        day_rows = day_plans_by_slug.get(slug) or []
        pieces: list[TeamDayPiece] = []
        if day_rows:
            dates = [d.plan_date for d in day_rows if d.plan_date]
            if dates:
                start = min(dates)
                end = max(dates)
            else:
                start, end = schedule_span(
                    start=start,
                    lead_minutes=row['minutes'],
                    minutes_per_day=PLAN_SHIFT_MINUTES,
                )
            if len(day_rows) >= 2:
                for dp in day_rows:
                    if not dp.plan_date:
                        continue
                    qty = _q(dp.qty)
                    pieces.append(TeamDayPiece(
                        plan_date=dp.plan_date,
                        qty=qty,
                        qty_label=format_sx_num_input(qty) if qty > 0 else '0',
                    ))
            dur_days = max(1, len(dates))
            dur_label = '1 ngày làm việc' if dur_days == 1 else f'{dur_days} ngày làm việc'
        else:
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
            pinned=is_pinned or bool(day_rows),
            duration_label=dur_label,
            duration_work_days=dur_days,
            day_pieces=pieces,
            labor_minutes=_q(row.get('labor_minutes') or row['work_minutes'], '0.0001'),
            headcount=int(row.get('headcount') or 0),
            efficiency_pct=_q(row.get('efficiency_pct') or 0),
            catalog_headcount=int(row.get('catalog_headcount') or 0),
            catalog_efficiency_pct=_q(row.get('catalog_efficiency_pct') or 0),
            work_hours_per_day=_q(row.get('work_hours_per_day') or 0),
            capacity_minutes_per_day=_q(row.get('capacity_minutes_per_day') or 0),
            work_center_id=int(row.get('work_center_id') or 0),
            smv_seconds=_q(row.get('smv_seconds') or 0, '0.0001'),
            qty_per_day=_q(row.get('qty_per_day') or 0),
            planned_qty=_q(row.get('qty') or 0),
        ))
    return npl_spans + spans


def _write_team_planned_dates(steps, starts_by_slug: dict[str, date], *, require_slug: str = '') -> int:
    from san_xuat.services.inter_step_times import _group_slug_scope

    written = 0
    wrote_required = not require_slug
    with _group_slug_scope():
        for step in steps:
            st = _plan_step_team_slug(step)
            if st not in starts_by_slug:
                continue
            if step.planned_date != starts_by_slug[st]:
                fields = ['planned_date']
                step.planned_date = starts_by_slug[st]
                gc = (getattr(step, 'group_code', None) or '').strip()
                if gc:
                    fields.append('group_code')
                step.save(update_fields=fields)
            written += 1
            if require_slug and st == require_slug:
                wrote_required = True
    if require_slug and not wrote_required:
        return 0
    return written


def _clear_day_plan_cache(order: SxSalesOrder) -> None:
    cache = getattr(order, '_prefetched_objects_cache', None)
    if cache is not None:
        cache.pop('team_day_plans', None)
        cache.pop('plan_steps', None)


def _workday_offset(start: date, target: date) -> int:
    """Số ngày làm việc từ start đến target (0 nếu cùng ngày / target trước start)."""
    from san_xuat.services.work_calendar import is_working_day

    if not start or not target or target <= start:
        return 0
    n = 0
    cur = start
    for _ in range(800):
        if cur >= target:
            break
        cur += timedelta(days=1)
        if is_working_day(cur):
            n += 1
    return n


def _last_team_day_plan(order: SxSalesOrder, slug: str) -> date | None:
    row = (
        SxOrderTeamDayPlan.objects.filter(sales_order=order, team_slug=slug)
        .order_by('-plan_date', '-id')
        .first()
    )
    return row.plan_date if row else None


def _schedule_from_qty_or_minutes(span: TeamKhsxSpan, start: date) -> tuple[date, date]:
    from san_xuat.services.inter_step_times import schedule_span
    from san_xuat.services.work_calendar import add_working_days, next_working_day

    start = next_working_day(start)
    qpd = _q(getattr(span, 'qty_per_day', 0) or 0)
    qty = _q(getattr(span, 'planned_qty', 0) or 0)
    if qpd > 0 and qty > 0:
        n = len(_auto_day_qty_rows(qty, qpd))
        end = add_working_days(start, max(0, n - 1))
        return start, end
    return schedule_span(
        start=start,
        lead_minutes=span.minutes,
        minutes_per_day=PLAN_SHIFT_MINUTES,
    )


def _rebase_team_day_plans(order: SxSalesOrder, slug: str, new_start: date) -> date | None:
    """Dời các thẻ ngày, giữ SL và khoảng cách ngày làm việc. Trả ngày cuối."""
    from san_xuat.services.work_calendar import add_working_days, next_working_day

    rows = list(
        SxOrderTeamDayPlan.objects.filter(sales_order=order, team_slug=slug).order_by('plan_date', 'id')
    )
    if not rows:
        return None
    new_start = next_working_day(new_start)
    old_start = rows[0].plan_date
    if old_start == new_start:
        return rows[-1].plan_date
    qtys = [_q(r.qty) for r in rows]
    offsets = [_workday_offset(old_start, r.plan_date) for r in rows]
    occupied: set[date] = set()
    assigned: list[tuple[date, Decimal]] = []
    for off, q in zip(offsets, qtys):
        day = add_working_days(new_start, off)
        while day in occupied:
            day = add_working_days(day, 1)
        occupied.add(day)
        assigned.append((day, q))
    SxOrderTeamDayPlan.objects.filter(sales_order=order, team_slug=slug).delete()
    SxOrderTeamDayPlan.objects.bulk_create([
        SxOrderTeamDayPlan(sales_order=order, team_slug=slug, plan_date=d, qty=q)
        for d, q in assigned
    ])
    _clear_day_plan_cache(order)
    return assigned[-1][0]


def apply_auto_team_day_splits(
    order: SxSalesOrder,
    *,
    only_slug: str = '',
    replace_existing: bool = False,
    origin_start: date | None = None,
) -> int:
    """Tự tách SL theo công suất ngày của tổ. Tách tay (modal Tách) vẫn sửa được."""
    from san_xuat.services.inter_step_times import schedule_span
    from san_xuat.services.plan_order_npl import production_start_for_order
    from san_xuat.services.work_calendar import add_working_days, next_working_day

    if not getattr(order, 'pk', None):
        return 0
    try:
        _assert_schedule_editable(order)
    except PlanningError:
        return 0

    loads = _team_loads_from_order(order)
    if not loads:
        return 0
    today = timezone.localdate()
    cursor = origin_start or production_start_for_order(order, today=today)
    cursor = next_working_day(cursor)
    want = (only_slug or '').strip().lower()
    written = 0
    existing_map: dict[str, list] = {}
    for dp in SxOrderTeamDayPlan.objects.filter(sales_order_id=order.pk).order_by('plan_date', 'id'):
        sk = (dp.team_slug or '').strip().lower()
        if sk:
            existing_map.setdefault(sk, []).append(dp)
    pinned = _pinned_starts_from_steps(list(order.plan_steps.all()))
    starts_to_pin: dict[str, date] = {}

    for row in loads:
        slug = row['slug']
        qpd = _q(row.get('qty_per_day') or 0)
        qty_n = _q(row.get('qty') or 0)
        existing = existing_map.get(slug) or []
        skip = bool(want) and slug != want
        if skip:
            if existing:
                cursor = _next_working_day_after(existing[-1].plan_date)
            else:
                start = pinned.get(slug) or cursor
                start, end = schedule_span(
                    start=start,
                    lead_minutes=row['minutes'],
                    minutes_per_day=PLAN_SHIFT_MINUTES,
                )
                cursor = _next_working_day_after(end)
            continue
        need = _auto_day_qty_rows(qty_n, qpd) if qpd > 0 and qty_n > 0 else []
        if existing and not replace_existing:
            cursor = _next_working_day_after(existing[-1].plan_date)
            continue
        if not need:
            cursor = pinned.get(slug) or cursor
            continue
        if want and origin_start and slug == want:
            start = origin_start
        else:
            start = pinned.get(slug) or cursor
        start = next_working_day(start)
        SxOrderTeamDayPlan.objects.filter(sales_order=order, team_slug=slug).delete()
        occupied: set[date] = set()
        assigned: list[tuple[date, Decimal]] = []
        day = start
        for q in need:
            while day in occupied:
                day = add_working_days(day, 1)
            occupied.add(day)
            assigned.append((day, q))
            day = add_working_days(day, 1)
        SxOrderTeamDayPlan.objects.bulk_create([
            SxOrderTeamDayPlan(sales_order=order, team_slug=slug, plan_date=d, qty=q)
            for d, q in assigned
        ])
        existing_map[slug] = []
        starts_to_pin[slug] = start
        written += 1
        cursor = _next_working_day_after(assigned[-1][0])

    if starts_to_pin:
        _clear_day_plan_cache(order)
        steps = list(order.plan_steps.all())
        pinned.update(starts_to_pin)
        _write_team_planned_dates(steps, pinned)
    return written


def _timeline_bar_capacity(span) -> dict:
    return {
        'headcount': int(getattr(span, 'headcount', 0) or 0),
        'efficiency_pct': _q(getattr(span, 'efficiency_pct', 0) or 0),
        'catalog_headcount': int(getattr(span, 'catalog_headcount', 0) or 0),
        'catalog_efficiency_pct': _q(getattr(span, 'catalog_efficiency_pct', 0) or 0),
        'work_hours_per_day': _q(getattr(span, 'work_hours_per_day', 0) or 0),
        'labor_minutes': _q(getattr(span, 'labor_minutes', 0) or 0, '0.0001'),
        'smv_seconds': _q(getattr(span, 'smv_seconds', 0) or 0, '0.0001'),
        'qty_per_day': _q(getattr(span, 'qty_per_day', 0) or 0),
        'planned_qty': _q(getattr(span, 'planned_qty', 0) or 0),
    }


def _ticket_capacity_kwargs(span: TeamKhsxSpan) -> dict:
    return {
        'work_center_id': int(getattr(span, 'work_center_id', 0) or 0),
        'headcount': int(getattr(span, 'headcount', 0) or 0),
        'efficiency_pct': _q(getattr(span, 'efficiency_pct', 0) or 0),
        'catalog_headcount': int(getattr(span, 'catalog_headcount', 0) or 0),
        'catalog_efficiency_pct': _q(getattr(span, 'catalog_efficiency_pct', 0) or 0),
        'work_hours_per_day': _q(getattr(span, 'work_hours_per_day', 0) or 0),
        'labor_minutes': _q(getattr(span, 'labor_minutes', 0) or 0, '0.0001'),
        'capacity_minutes_per_day': _q(getattr(span, 'capacity_minutes_per_day', 0) or 0),
        'smv_seconds': _q(getattr(span, 'smv_seconds', 0) or 0, '0.0001'),
        'qty_per_day': _q(getattr(span, 'qty_per_day', 0) or 0),
        'planned_qty': _q(getattr(span, 'planned_qty', 0) or 0),
    }


def _span_days(start: date | None, end: date | None) -> int:
    if not start:
        return 0
    finish = end or start
    if finish < start:
        start, finish = finish, start
    return max(1, (finish - start).days + 1)


def build_ticket_timeline_steps(
    *,
    team_spans: list[TeamKhsxSpan],
    product_flows: list[PlanProductFlow] | None = None,
    npl_status: str = '',
    npl_ready_date: date | None = None,
    npl_lead_days: int = 0,
    npl_short_count: int = 0,
    khsx_end: date | None = None,
    due_date: date | None = None,
) -> list[TicketTimelineStep]:
    """Nấc ticket: chuẩn bị NPL → công đoạn → hoàn thành nhập kho."""
    spans = list(team_spans or [])
    npl_span = next((s for s in spans if s.slug == 'npl'), None)
    teams = [s for s in spans if s.slug != 'npl']
    steps: list[TicketTimelineStep] = []
    team_meta: dict[str, dict] = {}
    for product_flow in product_flows or []:
        for group in product_flow.flow_groups:
            slug = (getattr(group, 'team_slug', None) or '').strip().lower()
            if not slug:
                continue
            meta = team_meta.setdefault(slug, {
                'process_count': 0,
                'product_groups': [],
                'hop_step_id': 0,
                'hop_process_name': '',
                'hop_count_minutes': Decimal('0'),
                'hop_transfer_minutes': Decimal('0'),
            })
            names = list(getattr(group, 'process_names', None) or [])
            meta['process_count'] += len(names)
            if names:
                meta['product_groups'].append({
                    'product_code': product_flow.product_code,
                    'product_name': product_flow.product_name or product_flow.product_code,
                    'qty': product_flow.qty,
                    'image_url': product_flow.image_url,
                    'production_order_id': product_flow.production_order_id,
                    'process_names': names,
                })
            if not meta['hop_process_name'] and names:
                meta['hop_process_name'] = names[-1]
            if not meta['hop_step_id'] and getattr(group, 'hop_step_id', 0):
                meta['hop_step_id'] = int(group.hop_step_id)
            if not meta['hop_count_minutes'] and not meta['hop_transfer_minutes']:
                meta['hop_count_minutes'] = _q(getattr(group, 'form_count_minutes', 0))
                meta['hop_transfer_minutes'] = _q(getattr(group, 'form_transfer_minutes', 0))

    if npl_span:
        days = max(
            1,
            int(npl_span.duration_work_days or 0)
            or _span_days(npl_span.start, npl_span.end),
        )
        npl_status_key = 'short' if npl_short_count else 'ready'
        steps.append(TicketTimelineStep(
            slug='npl',
            kind='npl',
            label='Chuẩn bị nguyên phụ liệu',
            start=npl_span.start,
            end=npl_span.end,
            duration_label=npl_span.duration_label,
            days=days,
            status=npl_status_key,
            flex=days,
            is_late=bool(due_date and npl_span.end and npl_span.end > due_date),
        ))
    else:
        status = 'empty'
        if npl_status == SxSalesOrder.NPL_DRAFT:
            status = 'short' if npl_short_count else 'draft'
        elif npl_status == SxSalesOrder.NPL_READY:
            status = 'short' if npl_short_count else 'ready'
        ready_one = npl_ready_date if npl_status == SxSalesOrder.NPL_READY else None
        dur = ''
        if status == 'ready' and not npl_lead_days:
            dur = 'sẵn'
        elif npl_lead_days:
            dur = f'{int(npl_lead_days)} ngày'
        steps.append(TicketTimelineStep(
            slug='npl',
            kind='npl',
            label='Chuẩn bị nguyên phụ liệu',
            start=ready_one,
            end=ready_one,
            duration_label=dur,
            days=0,
            status=status,
            flex=1,
        ))

    if teams:
        for index, s in enumerate(teams):
            meta = team_meta.get((s.slug or '').strip().lower(), {})
            qty_total = Decimal('0')
            for pg in meta.get('product_groups') or []:
                qty_total += _q(pg.get('qty'))
            team_qty_label = format_sx_num_input(qty_total) if qty_total > 0 else ''
            if not team_qty_label:
                team_qty_label = _team_qty_label(s.slug, product_flows, Decimal('0'))
            pieces = [p for p in (s.day_pieces or []) if p.plan_date]
            if len(pieces) >= 2:
                last_i = len(pieces) - 1
                for i, piece in enumerate(pieces):
                    is_last = i == last_i
                    steps.append(TicketTimelineStep(
                        slug=s.slug,
                        kind='team',
                        label=s.label or 'Công đoạn',
                        start=piece.plan_date,
                        end=piece.plan_date,
                        duration_label=s.duration_label if i == 0 else '',
                        days=1,
                        status='ok',
                        flex=1,
                        is_late=bool(due_date and piece.plan_date and piece.plan_date > due_date),
                        process_count=int(meta.get('process_count') or 0),
                        product_groups=list(meta.get('product_groups') or []),
                        hop_step_id=int(meta.get('hop_step_id') or 0) if is_last else 0,
                        hop_process_name=(meta.get('hop_process_name') or '') if is_last else '',
                        hop_count_minutes=_q(meta.get('hop_count_minutes') or 0) if is_last else Decimal('0'),
                        hop_transfer_minutes=_q(meta.get('hop_transfer_minutes') or 0) if is_last else Decimal('0'),
                        can_edit_hop=is_last and index < len(teams) - 1,
                        qty_label=piece.qty_label,
                        team_qty_total=team_qty_label,
                        show_connector=is_last,
                        split_index=i + 1,
                        split_count=len(pieces),
                        **_ticket_capacity_kwargs(s),
                    ))
                continue
            days = _span_days(s.start, s.end)
            steps.append(TicketTimelineStep(
                slug=s.slug,
                kind='team',
                label=s.label or 'Công đoạn',
                start=s.start,
                end=s.end,
                duration_label=s.duration_label,
                days=days,
                status='ok',
                flex=days,
                is_late=bool(due_date and s.end and s.end > due_date),
                process_count=int(meta.get('process_count') or 0),
                product_groups=list(meta.get('product_groups') or []),
                hop_step_id=int(meta.get('hop_step_id') or 0),
                hop_process_name=meta.get('hop_process_name') or '',
                hop_count_minutes=_q(meta.get('hop_count_minutes') or 0),
                hop_transfer_minutes=_q(meta.get('hop_transfer_minutes') or 0),
                can_edit_hop=index < len(teams) - 1,
                qty_label=team_qty_label,
                team_qty_total=team_qty_label,
                **_ticket_capacity_kwargs(s),
            ))
    else:
        steps.append(TicketTimelineStep(
            slug='ops',
            kind='team',
            label='Công đoạn',
            status='empty',
            flex=1,
        ))

    last_end = None
    dated = [s.end for s in teams if s.end] or ([npl_span.end] if npl_span and npl_span.end else [])
    if dated:
        last_end = max(dated)
    last_end = last_end or khsx_end
    steps.append(TicketTimelineStep(
        slug='kho',
        kind='kho',
        label='Hoàn thành · nhập kho',
        start=last_end,
        end=last_end,
        duration_label='',
        days=1 if last_end else 0,
        status='end',
        flex=1,
        is_late=bool(due_date and last_end and last_end > due_date),
    ))
    return steps


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
    ``request_date``) trên các tab danh sách.
    """
    qs = (
        SxSalesOrder.objects.filter(
            is_demo=False,
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        )
        .prefetch_related(
            Prefetch(
                'lines',
                queryset=SxSalesOrderLine.objects.select_related(
                    'bom_version', 'routing',
                ).order_by('sort_order', 'id').prefetch_related(
                    'routing_lines__work_center',
                    'routing_lines__operation__group',
                    'bom_version__process_steps',
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
            Prefetch(
                'team_day_plans',
                queryset=SxOrderTeamDayPlan.objects.order_by('plan_date', 'id'),
            ),
            'npl_lines',
            Prefetch(
                'material_plans',
                queryset=SxMaterialPlan.objects.filter(is_demo=False)
                .exclude(status__in=(SxOverallPlan.STATUS_CANCELLED, SxOverallPlan.STATUS_DONE))
                .order_by('-id')
                .prefetch_related(
                    Prefetch(
                        'purchase_requests',
                        queryset=SxNplPurchaseRequest.objects.filter(is_demo=False).order_by('-id'),
                    ),
                ),
            ),
            Prefetch(
                'npl_purchase_requests',
                queryset=SxNplPurchaseRequest.objects.filter(is_demo=False).order_by('-id'),
            ),
        )
    )
    if statuses:
        qs = qs.filter(plan_status__in=statuses)
    elif not include_released:
        qs = qs.filter(plan_status__in=QUEUE_STATUSES)

    term = (search or '').strip()
    if term:
        qs = qs.filter(
            Q(code__icontains=term)
            | Q(customer_name__icontains=term)
            | Q(lines__product_code__icontains=term)
            | Q(lines__product_name__icontains=term)
            | Q(npl_lines__material_code__icontains=term)
            | Q(npl_lines__material_name__icontains=term)
        ).distinct()

    if date_from or date_to:
        qs = qs.annotate(
            _plan_anchor=Coalesce('plan_start_date', 'request_date'),
        )
        date_q = Q()
        if date_from:
            date_q &= Q(_plan_anchor__gte=date_from)
        if date_to:
            date_q &= Q(_plan_anchor__lte=date_to)
        # Hàng đợi luôn hiện; đơn đã chuyển SX lọc theo tháng KHSX.
        qs = qs.filter(Q(plan_status__in=QUEUE_STATUSES) | date_q)

    today = timezone.localdate()
    rows: list[PlanBoardRow] = []
    _tech_choice_cache: dict[str, dict] = {}
    for order in qs:
        lines = list(order.lines.all())
        mos = list(order.production_orders.all())
        total_qty = sum((ln.qty_to_produce for ln in lines), Decimal('0'))
        names: list[str] = []
        work_min = Decimal('0')
        has_routing = False
        hops = []
        flow_groups = []
        product_flows: list[PlanProductFlow] = []
        buffer_min = Decimal('0')
        plan_steps = list(order.plan_steps.all())
        if plan_steps:
            needs_default = any(
                (not s.work_center_id) or (not _wc_has_capacity(getattr(s, 'work_center', None)))
                for s in plan_steps
            )
            if needs_default:
                plan_steps = apply_default_capacity_teams(
                    order, plan_steps, replace_without_capacity=True,
                )
        wrote = apply_auto_team_day_splits(order, replace_existing=False)
        if wrote:
            try:
                _reflow_order_from(order, sync_mos=False)
            except PlanningError:
                pass
        _clear_day_plan_cache(order)
        plan_steps = list(order.plan_steps.all())
        if plan_steps:
            from san_xuat.services.inter_step_times import (
                attach_group_codes_from_routing,
                flow_groups_from_steps,
                hops_from_steps,
            )

            routing_lines = [
                rl
                for ln in lines
                for rl in ln.routing_lines.all()
            ]
            attach_group_codes_from_routing(plan_steps, routing_lines)
            hops = hops_from_steps(plan_steps)
            flow_groups = flow_groups_from_steps(plan_steps, sort_factory=True)
            # buffer_min không lấy từ plan_steps gộp (đơn nhiều mã bị cộng hop giả
            # ở chỗ ghép hai mã). Cộng theo từng mã ở dưới.

        # Flow theo từng mã SP — không gộp chung nhiều mã thành một dải tổ
        from san_xuat.services.inter_step_times import (
            attach_flow_group_hops,
            flow_groups_from_steps as _flow_groups,
        )

        mo_by_code: dict[str, SxProductionOrder] = {}
        for mo in mos:
            key = (mo.product_code or '').strip().casefold()
            if key and mo.status != SxProductionOrder.STATUS_CANCELLED and key not in mo_by_code:
                mo_by_code[key] = mo
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
            line_has_ops = _line_has_operations(ln)
            tech = _tech_choices_for_code(code, _tech_choice_cache)
            bom_obj = getattr(ln, 'bom_version', None)
            rt_obj = getattr(ln, 'routing', None)
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
                production_order_id=int(
                    getattr(mo_by_code.get(code.casefold()), 'pk', 0) or 0,
                ),
                has_bom=bool(ln.bom_version_id),
                has_ops=line_has_ops,
                bom_label=(getattr(bom_obj, 'version_label', None) or '') if ln.bom_version_id else '',
                routing_label=(getattr(rt_obj, 'routing_rev', None) or '') if ln.routing_id else '',
                available_boms=tech['boms'],
                available_routings=tech['routings'],
                bom_create_url=tech['bom_create_url'],
                routing_create_url=tech['routing_create_url'],
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
            has_routing = any(
                pf.flow_groups or pf.smv_minutes > 0 for pf in product_flows
            )
        from san_xuat.services.inter_step_times import schedule_span

        team_spans = team_khsx_spans(
            order,
            product_flows=product_flows,
            plan_steps=plan_steps,
            today=today,
        )
        prod_all = [s for s in team_spans if s.slug != 'npl']
        if prod_all:
            work_min = _q(sum((s.work_minutes for s in prod_all), Decimal('0')))
            buffer_min = _q(sum((s.buffer_minutes for s in prod_all), Decimal('0')))
            cycle_min = _q(sum((s.minutes for s in prod_all), Decimal('0')))
        else:
            cycle_min = _q(work_min + buffer_min)
        score, days_to_due, is_overdue = compute_score(
            order=order, cycle_minutes=cycle_min, today=today,
        )
        mo_count, mo_open, qty_planned, qty_done, pct = _mo_progress(mos)
        derived = derive_plan_status(order, mos)
        if (
            order.plan_status != SxSalesOrder.PLAN_ON_HOLD
            and derived != order.plan_status
        ):
            order.plan_status = derived

        if team_spans:
            prod_spans = [s for s in team_spans if s.slug != 'npl' and s.start]
            if not prod_spans:
                prod_spans = [s for s in team_spans if s.start]
            if prod_spans:
                khsx_start = min(s.start for s in prod_spans)
                khsx_end = max((s.end or s.start) for s in prod_spans)
            else:
                khsx_start = order.plan_start_date or order.request_date or today
                khsx_end = khsx_start
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
            'customer': (order.customer_name or '').strip(),
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
            'npl_ready': _fmt_date(order.npl_ready_date),
            'npl_lead_days': int(order.npl_lead_days or 0),
            'npl_status': order.npl_status,
            'npl_short_count': int(order.npl_short_count or 0),
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
                    'labor_minutes': format_sx_num_input(ts.labor_minutes),
                    'headcount': ts.headcount,
                    'capacity_minutes_per_day': format_sx_num_input(ts.capacity_minutes_per_day),
                    'splits': [
                        {
                            'date': _fmt_date(p.plan_date),
                            'qty': p.qty_label,
                        }
                        for p in (ts.day_pieces or [])
                    ],
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
        missing_bom = False
        missing_ops = False
        for ln in lines:
            if (ln.qty or 0) <= 0:
                continue
            code = (ln.product_code or '').strip()
            key = code.casefold()
            if not code or key in seen_codes:
                continue
            seen_codes.add(key)
            line_has_ops = _line_has_operations(ln)
            if not ln.bom_version_id:
                missing_bom = True
            if not line_has_ops:
                missing_ops = True
            release_products.append({
                'code': code,
                'name': (ln.product_name or '').strip(),
                'qty': format_sx_num_input(ln.qty_to_produce),
                'bom_version_id': ln.bom_version_id or None,
                'routing_id': ln.routing_id or None,
                'has_ops': line_has_ops,
            })

        npl_plan = next(iter(order.material_plans.all()), None)
        npl_pr = None
        if npl_plan:
            npl_pr = next(iter(npl_plan.purchase_requests.all()), None)
        if npl_pr is None:
            npl_pr = next(iter(order.npl_purchase_requests.all()), None)
        npl_short = int(order.npl_short_count or 0)
        timeline_steps = build_ticket_timeline_steps(
            team_spans=team_spans,
            product_flows=product_flows,
            npl_status=order.npl_status,
            npl_ready_date=order.npl_ready_date,
            npl_lead_days=int(order.npl_lead_days or 0),
            npl_short_count=npl_short,
            khsx_end=khsx_end,
            due_date=order.due_date,
        )

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
            missing_bom=missing_bom,
            missing_ops=missing_ops,
            npl_status=order.npl_status,
            npl_ready_date=order.npl_ready_date,
            npl_lead_days=int(order.npl_lead_days or 0),
            npl_short_count=npl_short,
            npl_ok_count=sum(1 for ln in order.npl_lines.all() if ln.qty_shortfall <= 0),
            npl_missing_buy=any(
                ln.qty_shortfall > 0 and ln.buy_lead_days is None
                for ln in order.npl_lines.all()
            ),
            npl_plan_id=npl_plan.pk if npl_plan else 0,
            npl_plan_code=(npl_plan.code if npl_plan else ''),
            npl_pr_id=npl_pr.pk if npl_pr else 0,
            npl_pr_code=(npl_pr.code if npl_pr else ''),
            timeline_steps=timeline_steps,
        ))

    rows.sort(
        key=lambda r: (
            0 if r.order.plan_status != SxSalesOrder.PLAN_ON_HOLD else 1,
            r.order.plan_rank if r.order.plan_rank is not None else 10_000,
            -float(r.score),
            r.order.id or 0,
        )
    )
    _fill_npl_supplier_names(rows)
    _fill_product_flow_images(rows)
    attach_subcontracts_to_plan_rows(rows)
    return rows


def _fill_npl_supplier_names(rows: list[PlanBoardRow]) -> None:
    """Gắn NCC chính từ danh mục kho lên dòng NPL để hiển thị trên KHSX."""
    from kho_npl.models import Material
    from kho_npl.services.uom import material_units

    codes = {
        (ln.material_code or '').strip()
        for row in rows
        for ln in row.order.npl_lines.all()
        if (ln.material_code or '').strip()
    }
    materials = (
        Material.objects.filter(code__in=codes)
        .select_related('supplier', 'unit', 'specification')
        .prefetch_related('specification__levels__unit')
    )
    material_info = {
        material.code.casefold(): material
        for material in materials
    }
    for row in rows:
        has_alt_uom = False
        for ln in row.order.npl_lines.all():
            material = material_info.get((ln.material_code or '').strip().casefold())
            supplier = material.supplier if material and material.supplier_id else None
            ln.supplier_name = supplier.name if supplier else ''
            ln.supplier_code = supplier.code if supplier else ''
            units = material_units(material) if material else []
            ln.uom_choices = units if len(units) > 1 else []
            if ln.uom_choices:
                has_alt_uom = True
            try:
                ln.material_image_url = material.image.url if material and material.image else ''
            except (ValueError, OSError):
                ln.material_image_url = ''
        row.show_npl_uom_col = has_alt_uom


def _fill_product_flow_images(rows: list[PlanBoardRow]) -> None:
    """Gắn ảnh hàng hoá (kho SP / KV) lên từng mã trên ticket KHSX."""
    from san_xuat.services.products import product_gallery_map

    codes = [pf.product_code for row in rows for pf in row.product_flows]
    galleries = product_gallery_map(codes)
    for row in rows:
        for pf in row.product_flows:
            urls = galleries.get((pf.product_code or '').casefold()) or []
            pf.image_urls = urls
            pf.image_url = urls[0] if urls else ''
        for step in row.timeline_steps:
            for product_group in step.product_groups:
                urls = galleries.get(
                    (product_group.get('product_code') or '').casefold(),
                ) or []
                product_group['image_url'] = urls[0] if urls else ''


def attach_subcontracts_to_plan_rows(rows: list[PlanBoardRow]) -> list[PlanBoardRow]:
    """Gắn toàn bộ phiếu GC và phiếu mới nhất lên từng đơn trên board."""
    if not rows:
        return rows
    from san_xuat.hub_models import SxSubcontractOrder

    order_ids = [r.order.pk for r in rows]
    qs = (
        SxSubcontractOrder.objects.filter(is_demo=False)
        .select_related('production_order')
        .exclude(status=SxSubcontractOrder.STATUS_CANCELLED)
        .filter(Q(sales_order_id__in=order_ids) | Q(production_order__sales_order_id__in=order_ids))
        .exclude(team_slug='')
        .order_by('-order_date', '-pk')
    )
    grouped: dict[int, list[SxSubcontractOrder]] = {}
    for gc in qs:
        oid = gc.sales_order_id
        if not oid and gc.production_order_id:
            oid = getattr(gc.production_order, 'sales_order_id', None)
        if oid:
            grouped.setdefault(oid, []).append(gc)
    for row in rows:
        row.subcontracts = grouped.get(row.order.pk, [])
        row.subcontract = row.subcontracts[0] if row.subcontracts else None
        for step in row.timeline_steps:
            if step.kind == 'team':
                step.subcontracts = [
                    item for item in row.subcontracts
                    if (item.team_slug or '').strip().lower() == (step.slug or '').strip().lower()
                ]
                for product_group in step.product_groups:
                    code = (product_group.get('product_code') or '').strip().casefold()
                    product_group['subcontracts'] = [
                        item for item in step.subcontracts
                        if (item.product_code or '').strip().casefold() == code
                    ]
    return rows


def attach_dangling_subcontracts(*, order: SxSalesOrder, mos: list[SxProductionOrder]) -> None:
    """Sau Chuyển SX: gắn phiếu GC tạo từ hàng đợi vào LSX vừa phát hành."""
    from san_xuat.hub_models import SxSubcontractOrder

    if not mos:
        return
    dangling = list(
        SxSubcontractOrder.objects.filter(
            sales_order=order,
            production_order__isnull=True,
            is_demo=False,
        ).exclude(status=SxSubcontractOrder.STATUS_CANCELLED)
    )
    if not dangling:
        return
    by_code: dict[str, SxProductionOrder] = {}
    for mo in mos:
        key = (mo.product_code or '').strip().casefold()
        if key and key not in by_code:
            by_code[key] = mo
    from san_xuat.services.phase3 import _close_ob_team_for_gc

    for gc in dangling:
        key = (gc.product_code or '').strip().casefold()
        mo = by_code.get(key) or mos[0]
        gc.production_order = mo
        gc.save(update_fields=['production_order'])
        if gc.status in (SxSubcontractOrder.STATUS_DONE, SxSubcontractOrder.STATUS_RECEIVED):
            _close_ob_team_for_gc(order=gc)


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


def _unique_order_ids(raw_ids) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for raw in raw_ids or []:
        try:
            oid = int(raw)
        except (TypeError, ValueError):
            continue
        if oid <= 0 or oid in seen:
            continue
        seen.add(oid)
        out.append(oid)
    return out


@transaction.atomic
def reorder_plan_orders(*, ordered_ids: list[int] | list[str]) -> int:
    """Kéo STT trên lộ trình: ghi plan_rank theo thứ tự mới của các đơn đang hiện."""
    sequence = _unique_order_ids(ordered_ids)
    if len(sequence) < 2:
        return 0
    locked = {
        o.pk: o
        for o in SxSalesOrder.objects.select_for_update().filter(pk__in=sequence, is_demo=False)
    }
    sequence = [oid for oid in sequence if oid in locked]
    if len(sequence) < 2:
        return 0
    current_ranks = [locked[oid].plan_rank for oid in sequence]
    if all(rank is not None for rank in current_ranks) and len(set(current_ranks)) == len(current_ranks):
        new_ranks = sorted(current_ranks)
        merged = sequence
    else:
        rows = build_plan_board_rows(include_released=True)
        all_ids = [r.order.pk for r in rows]
        vis = set(sequence)
        it = iter(sequence)
        merged = []
        for oid in all_ids:
            if oid in vis:
                merged.append(next(it, oid))
            else:
                merged.append(oid)
        seen = set(merged)
        merged.extend(oid for oid in sequence if oid not in seen)
        extra = [
            o for o in SxSalesOrder.objects.select_for_update().filter(
                pk__in=[oid for oid in merged if oid not in locked],
                is_demo=False,
            )
        ]
        for order in extra:
            locked[order.pk] = order
        new_ranks = list(range(1, len(merged) + 1))
    updated = 0
    for oid, rank in zip(merged, new_ranks):
        order = locked.get(oid)
        if order is None or order.plan_rank == rank:
            continue
        order.plan_rank = rank
        order.save(update_fields=['plan_rank', 'updated_at'])
        updated += 1
    return updated


@transaction.atomic
def save_plan_hops(*, order_id: int, hops: list[dict]) -> list[SxSalesOrderPlanStep]:
    """Cập nhật phút kiểm đếm / vận chuyển trên từng khoảng CĐ (đơn đã xác nhận)."""
    from san_xuat.services.plan_route import ensure_order_plan_steps

    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    _assert_schedule_editable(order)
    steps = ensure_order_plan_steps(order)
    if len(steps) < 2:
        raise PlanningError('Đơn chưa có đủ công đoạn để khai báo khoảng chuyển.')
    by_id = {s.pk: s for s in steps}
    updated = 0
    first_touched = None
    for raw in hops or []:
        try:
            sid = int(raw.get('step_id') or 0)
        except (TypeError, ValueError):
            sid = 0
        step = by_id.get(sid)
        if step is None:
            process_name = (raw.get('process_name') or '').strip().casefold()
            if process_name:
                candidates = [
                    row for row in steps
                    if (row.process_name or '').strip().casefold() == process_name
                ]
                if candidates:
                    step = max(candidates, key=lambda row: (row.sequence or 0, row.pk or 0))
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
        if first_touched is None or (step.sequence, step.pk) < (first_touched.sequence, first_touched.pk):
            first_touched = step
        updated += 1
    if not updated:
        raise PlanningError('Không cập nhật được khoảng công đoạn.')
    origin = _plan_step_team_slug(first_touched) if first_touched is not None else ''
    _reflow_order_from(order, origin_slug=origin)
    return list(order.plan_steps.order_by('sequence', 'id'))


@transaction.atomic
def assign_plan_team(
    *,
    order_id: int,
    team_slug: str,
    work_center_id: int | None,
) -> tuple[SxSalesOrder, SxWorkCenter | None]:
    """Gán tổ Năng lực SX cho một cụm công đoạn trên đơn — dùng để chia thời gian."""
    from san_xuat.services.inter_step_times import _group_slug_scope, _step_team_slug

    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    _assert_schedule_editable(order)
    slug = (team_slug or '').strip().lower()
    if not slug or slug == 'npl':
        raise PlanningError('Chọn công đoạn tổ sản xuất để gán.')
    wc = None
    if work_center_id:
        qs = SxWorkCenter.objects.filter(pk=int(work_center_id), is_active=True)
        if hasattr(SxWorkCenter, 'is_demo'):
            qs = qs.filter(is_demo=False)
        wc = qs.first()
        if wc is None:
            raise PlanningError('Tổ không hợp lệ hoặc đã tắt.')
    steps = _load_schedule_steps(order)
    matched: list[SxSalesOrderPlanStep] = []
    with _group_slug_scope():
        for step in steps:
            if _plan_step_team_slug(step) == slug:
                matched.append(step)
    if not matched:
        raise PlanningError('Không tìm thấy công đoạn tương ứng trên đơn.')
    for step in matched:
        step.work_center = wc
        step.khsx_headcount = None
        step.khsx_efficiency_pct = None
        step.save(update_fields=['work_center', 'khsx_headcount', 'khsx_efficiency_pct'])
    with _group_slug_scope():
        for ln in order.lines.all():
            for rl in ln.routing_lines.select_related('work_center', 'operation__group').all():
                rl_slug = (_step_team_slug(rl) or '').strip().lower()
                if rl_slug != slug:
                    continue
                rl.work_center = wc
                rl.work_center_code = (wc.code if wc else '')[:40]
                rl.save(update_fields=['work_center', 'work_center_code'])
    cache = getattr(order, '_prefetched_objects_cache', None)
    if cache is not None:
        cache.pop('plan_steps', None)
        cache.pop('lines', None)
    apply_auto_team_day_splits(order, only_slug=slug, replace_existing=True)
    _reflow_order_from(order, origin_slug=slug)
    return order, wc


@transaction.atomic
def save_plan_team_capacity(
    *,
    order_id: int,
    team_slug: str,
    headcount: int,
    efficiency_pct,
) -> SxSalesOrder:
    """Chỉnh số người / hệ số tải trên KHSX — không đụng danh mục NL hay lệnh SX đã tạo."""
    from san_xuat.services.inter_step_times import _group_slug_scope

    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    _assert_schedule_editable(order)
    slug = (team_slug or '').strip().lower()
    if not slug or slug == 'npl':
        raise PlanningError('Chọn công đoạn tổ sản xuất để chỉnh.')
    try:
        heads = int(headcount)
    except (TypeError, ValueError):
        raise PlanningError('Số người không hợp lệ.') from None
    if heads < 1 or heads > 500:
        raise PlanningError('Số người thực hiện từ 1 đến 500.')
    try:
        load = _q(efficiency_pct)
    except Exception:
        raise PlanningError('Hệ số tải không hợp lệ.') from None
    if load < 1 or load > 200:
        raise PlanningError('Hệ số tải từ 1% đến 200%.')
    steps = _load_schedule_steps(order)
    matched: list[SxSalesOrderPlanStep] = []
    with _group_slug_scope():
        for step in steps:
            if _plan_step_team_slug(step) == slug:
                matched.append(step)
    if not matched:
        raise PlanningError('Không tìm thấy công đoạn tương ứng trên đơn.')
    for step in matched:
        step.khsx_headcount = heads
        step.khsx_efficiency_pct = load
        step.save(update_fields=['khsx_headcount', 'khsx_efficiency_pct'])
    cache = getattr(order, '_prefetched_objects_cache', None)
    if cache is not None:
        cache.pop('plan_steps', None)
    apply_auto_team_day_splits(order, only_slug=slug, replace_existing=True)
    has_mo = order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    ).exists()
    return _reflow_order_from(order, origin_slug=slug, sync_mos=not has_mo)


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
def set_plan_color(*, order_id: int, color: str = '', clear: bool = False) -> SxSalesOrder:
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ tô màu đơn đã xác nhận.')
    if clear or not (color or '').strip():
        order.plan_color = ''
    else:
        order.plan_color = normalize_plan_color(color)
    order.save(update_fields=['plan_color', 'updated_at'])
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


def _assert_lines_ready_to_release(
    lines: list[SxSalesOrderLine],
    *,
    bom_map: dict[str, int],
    routing_map: dict[str, int],
) -> None:
    """KHSX: lên đơn không bắt BOM/OB, nhưng Chuyển SX thì phải có cả hai."""
    from san_xuat.models import BomVersion

    errors: list[str] = []
    for ln in lines:
        if (ln.qty or 0) <= 0:
            continue
        code = (ln.product_code or '').strip() or f'#{ln.pk}'
        bom_id = bom_map.get(code.casefold()) or ln.bom_version_id
        if not bom_id:
            errors.append(f'{code}: chưa gắn BOM.')
            continue
        bom = BomVersion.objects.filter(pk=bom_id).prefetch_related('process_steps').first()
        routing_id = routing_map.get(code.casefold()) or ln.routing_id
        if not _line_has_operations(ln, routing_id=routing_id, bom=bom):
            errors.append(
                f'{code}: chưa gắn công đoạn. Chọn phiên bản công đoạn (OB) '
                'hoặc thêm công đoạn trên hồ sơ BOM.'
            )
    if errors:
        raise PlanningError('Không chuyển SX được. ' + ' '.join(errors))


def _persist_line_tech(order_line: SxSalesOrderLine, *, bom_id: int, routing_id: int | None) -> None:
    """Gắn BOM / OB đã chọn lúc Chuyển SX lên dòng đơn."""
    from san_xuat.services.order_routing import seed_order_line_routing
    from san_xuat.services.sales_orders import bom_lines_snapshot

    fields: list[str] = []
    if bom_id and order_line.bom_version_id != bom_id:
        order_line.bom_version_id = bom_id
        fields.append('bom_version')
        if not order_line.bom_line_overrides:
            order_line.bom_line_overrides = bom_lines_snapshot(bom_id)
            fields.append('bom_line_overrides')
    if routing_id and order_line.routing_id != routing_id:
        order_line.routing_id = routing_id
        fields.append('routing')
    if fields:
        order_line.save(update_fields=fields)
    if not order_line.routing_lines.exists():
        seed_order_line_routing(order_line, replace=True)


@transaction.atomic
def attach_plan_line_tech(
    *,
    order_id: int,
    line_id: int,
    bom_version_id: int | None = None,
    routing_id: int | None = None,
) -> SxSalesOrderLine:
    """Gắn BOM / công đoạn ngay trên KHSX (hàng đợi), không sang màn đơn hàng."""
    from san_xuat.services.order_routing import (
        OrderRoutingError,
        attach_order_line_bom,
        attach_order_line_routing,
    )
    from san_xuat.services.plan_route import ensure_order_plan_steps

    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ gắn BOM / công đoạn trên đơn đã xác nhận.')
    if order.plan_status == SxSalesOrder.PLAN_ON_HOLD:
        raise PlanningError('Đơn đang tạm giữ — bỏ giữ trước khi gắn.')
    if order.plan_status not in (SxSalesOrder.PLAN_QUEUED, SxSalesOrder.PLAN_ON_HOLD):
        raise PlanningError('Đơn đã chuyển SX — không gắn lại trên hàng đợi.')
    ln = order.lines.filter(pk=line_id).first()
    if ln is None:
        raise PlanningError('Không tìm thấy dòng sản phẩm trên đơn.')
    if not bom_version_id and not routing_id:
        raise PlanningError('Chọn BOM hoặc công đoạn để gắn.')
    try:
        if bom_version_id:
            attach_order_line_bom(ln, bom_version_id=bom_version_id)
        if routing_id:
            attach_order_line_routing(ln, routing_id=routing_id)
    except OrderRoutingError as exc:
        raise PlanningError(str(exc)) from exc
    ln.refresh_from_db()
    order.plan_steps.all().delete()
    ensure_order_plan_steps(order)
    return ln


@dataclass
class ReloadPlanTechResult:
    order: SxSalesOrder
    bom_count: int = 0
    routing_count: int = 0
    npl_reloaded: bool = False


def _assert_plan_tech_reloadable(order: SxSalesOrder) -> None:
    """Load BOM/OB/NPL chỉ khi đơn còn trên hàng đợi, chưa có LSX."""
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ tải lại BOM / OB / NPL trên đơn đã xác nhận.')
    if order.plan_status == SxSalesOrder.PLAN_ON_HOLD:
        raise PlanningError('Đơn đang tạm giữ — bỏ giữ trước khi tải lại.')
    if order.plan_status not in QUEUE_STATUSES:
        raise PlanningError(
            'Đơn đã chuyển SX — BOM, OB, NPL đã khoá. Hủy chuyển SX nếu cần tải lại.'
        )
    if order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    ).exists():
        raise PlanningError(
            'Đơn đã có lệnh sản xuất — BOM, OB, NPL đã khoá. Hủy chuyển SX nếu cần tải lại.'
        )


@transaction.atomic
def reload_plan_order_tech(
    *,
    order_id: int,
    user=None,
    kit_days: int | None = None,
    buy_by_line: dict | None = None,
    allocate_by_line: dict | None = None,
    reset_allocated: bool = False,
) -> ReloadPlanTechResult:
    """Ghi đè snapshot BOM / OB / NPL trên KHSX từ hồ sơ hiện tại.

    Dùng khi sửa BOM/OB sau lúc gắn nhưng đơn chưa Chuyển SX. Sau Chuyển SX
    snapshot bị khoá — không gọi hàm này.
    """
    from san_xuat.services.order_routing import seed_order_line_routing
    from san_xuat.services.plan_audit import log_plan_action
    from san_xuat.services.plan_route import ensure_order_plan_steps
    from san_xuat.services.sales_orders import bom_lines_snapshot

    order = (
        SxSalesOrder.objects.select_for_update()
        .prefetch_related(
            'lines__bom_version__process_steps',
            'lines__routing',
            'npl_lines',
        )
        .get(pk=order_id, is_demo=False)
    )
    _assert_plan_tech_reloadable(order)

    lines = [ln for ln in order.lines.all() if (ln.qty or 0) > 0]
    if not lines:
        raise PlanningError('Đơn không có dòng sản phẩm.')

    bom_count = 0
    routing_count = 0
    for ln in lines:
        if ln.bom_version_id:
            ln.bom_line_overrides = bom_lines_snapshot(ln.bom_version_id)
            ln.save(update_fields=['bom_line_overrides'])
            bom_count += 1
        bom = ln.bom_version if ln.bom_version_id else None
        has_ob_source = bool(ln.routing_id) or bool(
            bom is not None and bom.process_steps.exists()
        )
        if has_ob_source:
            n = seed_order_line_routing(ln, replace=True)
            if n:
                routing_count += 1
    if bom_count <= 0 and routing_count <= 0:
        raise PlanningError('Chưa gắn BOM / OB trên đơn — gắn hồ sơ trước khi Load.')

    order.plan_steps.all().delete()
    ensure_order_plan_steps(order)

    npl_reloaded = False
    if order.npl_status != SxSalesOrder.NPL_NONE or order.npl_lines.exists():
        from san_xuat.services.plan_order_npl import sync_order_npl

        was_ready = order.npl_status == SxSalesOrder.NPL_READY
        try:
            order = sync_order_npl(
                order_id=order.pk,
                kit_days=kit_days,
                buy_by_line=buy_by_line,
                allocate_by_line=None if reset_allocated else allocate_by_line,
                reset_allocated=reset_allocated,
                apply_schedule=was_ready,
            )
            npl_reloaded = True
        except PlanningError:
            npl_reloaded = False

    bits = []
    if bom_count:
        bits.append('BOM')
    if routing_count:
        bits.append('OB')
    if npl_reloaded:
        bits.append('NPL')
    log_plan_action(
        action='reload_tech',
        obj=order,
        summary=f'Load {", ".join(bits) or "hồ sơ"} trên KHSX {order.code}.',
        changes={'bom': bom_count, 'routing': routing_count, 'npl': npl_reloaded},
        user=user,
    )
    return ReloadPlanTechResult(
        order=order,
        bom_count=bom_count,
        routing_count=routing_count,
        npl_reloaded=npl_reloaded,
    )


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
    _assert_lines_ready_to_release(lines, bom_map=bom_map, routing_map=routing_map)

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
        _persist_line_tech(ln, bom_id=bom_id, routing_id=routing_id)

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
    attach_dangling_subcontracts(order=order, mos=created)
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

    from san_xuat.hub_models import SxSubcontractOrder, SxTeamWorkClose

    SxTeamWorkClose.objects.filter(production_order_id__in=[m.pk for m in mos]).delete()
    SxSubcontractOrder.objects.filter(production_order_id__in=[m.pk for m in mos]).update(
        production_order=None,
    )

    order.plan_status = SxSalesOrder.PLAN_QUEUED
    order.plan_rank = None
    order.plan_hold_reason = ''
    order.save(update_fields=['plan_status', 'plan_rank', 'plan_hold_reason', 'updated_at'])
    return order, cancelled


@transaction.atomic
def reschedule_order_plan_start(*, order_id: int, start_date: date) -> SxSalesOrder:
    """Kéo thả lộ trình: neo ngày bắt đầu KHSX, dồn các công đoạn sau."""
    if not isinstance(start_date, date):
        raise PlanningError('Ngày bắt đầu không hợp lệ.')
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    _assert_schedule_editable(order)
    return _reflow_order_from(order, origin_slug='', origin_start=start_date)


@transaction.atomic
def reschedule_order_team_start(
    *,
    order_id: int,
    start_date: date,
    team_slug: str = '',
    from_date: date | None = None,
) -> SxSalesOrder:
    """Kéo một tổ trên lộ trình — các tổ khác giữ nguyên ngày.

    Nếu tổ đã tách ngày và có ``from_date``, chỉ dịch mảnh đó.
    """
    if not isinstance(start_date, date):
        raise PlanningError('Ngày bắt đầu không hợp lệ.')
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    _assert_schedule_editable(order)
    slug = (team_slug or '').strip().lower()
    if slug == 'npl':
        raise PlanningError('Không kéo thanh chuẩn bị NPL — sửa ngày mua trên kế hoạch.')
    if not slug:
        return _reflow_order_from(order, origin_slug='', origin_start=start_date)
    if from_date is not None and SxOrderTeamDayPlan.objects.filter(
        sales_order=order, team_slug=slug,
    ).exists():
        return move_team_day_plan(
            order_id=order.pk,
            team_slug=slug,
            from_date=from_date,
            to_date=start_date,
        )
    return _move_team_start_independent(order, slug=slug, start_date=start_date)


def _assert_schedule_editable(order: SxSalesOrder) -> None:
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        raise PlanningError('Chỉ xếp lịch đơn đã xác nhận.')
    if order.plan_status == SxSalesOrder.PLAN_DONE:
        raise PlanningError('Đơn đã hoàn thành — không chỉnh lộ trình.')
    if order.plan_status == SxSalesOrder.PLAN_ON_HOLD:
        raise PlanningError('Đơn đang tạm giữ — bỏ giữ trước khi chỉnh lộ trình.')


def _load_schedule_steps(order: SxSalesOrder):
    from san_xuat.services.inter_step_times import attach_group_codes_from_routing
    from san_xuat.services.plan_route import ensure_order_plan_steps

    steps = ensure_order_plan_steps(order)
    routing_lines = [
        rl for ln in order.lines.all() for rl in ln.routing_lines.all()
    ]
    attach_group_codes_from_routing(steps, routing_lines)
    dirty_gc = [
        s for s in steps
        if getattr(s, 'pk', None) and (getattr(s, 'group_code', None) or '').strip()
    ]
    if dirty_gc:
        SxSalesOrderPlanStep.objects.bulk_update(dirty_gc, ['group_code'])
    return steps


def _move_team_start_independent(
    order: SxSalesOrder, *, slug: str, start_date: date,
) -> SxSalesOrder:
    """Ghim ngày mọi tổ đang hiện, rồi chỉ dịch tổ được kéo."""
    from san_xuat.services.work_calendar import next_working_day

    steps = _load_schedule_steps(order)
    spans = team_khsx_spans(order, plan_steps=steps)
    prod = [s for s in spans if s.slug != 'npl']
    if slug not in {s.slug for s in prod}:
        raise PlanningError('Tổ này không tham gia đơn.')
    starts: dict[str, date] = {
        span.slug: span.start for span in prod if span.start
    }
    starts[slug] = next_working_day(start_date)
    written = _write_team_planned_dates(steps, starts, require_slug=slug)
    if written <= 0:
        raise PlanningError('Không gán được công đoạn của tổ này.')
    return _sync_schedule_to_mos(order, starts)


def _sync_schedule_to_mos(
    order: SxSalesOrder, starts: dict[str, date], *, sync_mos: bool = True,
) -> SxSalesOrder:
    from san_xuat.services.capacity_from_hrm import team_slug_for_work_center
    from san_xuat.services.progress_template import team_slug_for_process_label

    steps = list(order.plan_steps.select_related('work_center').order_by('sequence', 'id'))
    spans = team_khsx_spans(order, plan_steps=steps)
    prod = [s for s in spans if s.slug != 'npl' and s.start]
    if not prod:
        return order
    pstart = min(s.start for s in prod)
    pend = max((s.end or s.start) for s in prod)
    if order.plan_start_date != pstart:
        order.plan_start_date = pstart
        order.save(update_fields=['plan_start_date', 'updated_at'])
    if not sync_mos:
        return order
    mos = order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    )
    for mo in mos:
        fields: list[str] = []
        if mo.planned_start != pstart:
            mo.planned_start = pstart
            fields.append('planned_start')
        if mo.planned_end != pend:
            mo.planned_end = pend
            fields.append('planned_end')
        if fields:
            mo.save(update_fields=fields)
        for step in mo.mo_process_steps.select_related('work_center'):
            st_slug = (
                team_slug_for_process_label(step.process_name or '')
                or team_slug_for_work_center(step.work_center)
                or ''
            ).strip().lower()
            new_date = starts.get(st_slug)
            if new_date and step.planned_date != new_date:
                step.planned_date = new_date
                step.save(update_fields=['planned_date'])
    return order


def _reflow_order_from(
    order: SxSalesOrder,
    *,
    origin_slug: str = '',
    origin_start: date | None = None,
    sync_mos: bool = True,
) -> SxSalesOrder:
    """Giữ ngày tổ đang sửa, dồn các tổ sau theo quỹ phút + ngày làm việc."""
    from san_xuat.services.work_calendar import next_working_day

    steps = _load_schedule_steps(order)
    spans = team_khsx_spans(order, plan_steps=steps)
    prod = [s for s in spans if s.slug != 'npl']
    if not prod:
        return order
    slug = (origin_slug or '').strip().lower() or prod[0].slug
    if slug not in {s.slug for s in prod}:
        raise PlanningError('Tổ này không tham gia đơn.')

    starts: dict[str, date] = {}
    prev_end = None
    passed = False
    for span in prod:
        if span.slug == slug:
            passed = True
            raw = origin_start if origin_start is not None else span.start
            if raw is None:
                raw = timezone.localdate()
            start = next_working_day(raw)
            last = _rebase_team_day_plans(order, span.slug, start)
            if last is None:
                n = apply_auto_team_day_splits(
                    order, only_slug=span.slug, replace_existing=False, origin_start=start,
                )
                last = _last_team_day_plan(order, span.slug) if n else None
            if last is None:
                start, end = _schedule_from_qty_or_minutes(span, start)
            else:
                end = last
            starts[span.slug] = start
            prev_end = end
            continue
        if not passed:
            if span.start:
                starts[span.slug] = span.start
            prev_end = span.end or span.start
            continue
        cursor = (
            _next_working_day_after(prev_end)
            if prev_end else next_working_day(timezone.localdate())
        )
        last = _rebase_team_day_plans(order, span.slug, cursor)
        if last is None:
            n = apply_auto_team_day_splits(
                order, only_slug=span.slug, replace_existing=False, origin_start=cursor,
            )
            last = _last_team_day_plan(order, span.slug) if n else None
        if last is None:
            start, end = _schedule_from_qty_or_minutes(span, cursor)
            starts[span.slug] = start
            prev_end = end
            continue
        starts[span.slug] = cursor
        prev_end = last

    written = _write_team_planned_dates(steps, starts, require_slug=slug)
    if written <= 0:
        raise PlanningError('Không gán được công đoạn của tổ này.')
    return _sync_schedule_to_mos(order, starts, sync_mos=sync_mos)


def load_snapshot_for_board(*, days: int = 14) -> dict:
    """Năng lực tổ (tham khảo) cho tab board — không xếp lịch."""
    centers = list(
        SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by('code')
    )
    return {'centers': centers}


TIMELINE_DAYS = 28
TIMELINE_MAX_DAYS = 93
ROUTE_TIMELINE_DAYS = 60


_WD_VN = ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')


@dataclass
class TimelineDay:
    date: date
    day: int
    weekday: str
    is_today: bool
    is_weekend: bool
    is_week_start: bool
    is_off: bool = False


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
    lane: int = 0
    lane_count: int = 1
    qty_label: str = ''
    done_qty_label: str = '0'
    is_split: bool = False
    segment_id: int = 0
    plan_date: date | None = None
    team_qty_total: str = ''
    work_center_id: int = 0
    headcount: int = 0
    efficiency_pct: Decimal = field(default_factory=lambda: Decimal('0'))
    catalog_headcount: int = 0
    catalog_efficiency_pct: Decimal = field(default_factory=lambda: Decimal('0'))
    work_hours_per_day: Decimal = field(default_factory=lambda: Decimal('0'))
    labor_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    smv_seconds: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_per_day: Decimal = field(default_factory=lambda: Decimal('0'))
    planned_qty: Decimal = field(default_factory=lambda: Decimal('0'))


@dataclass
class RouteDayCell:
    """Một ô ngày trên lưới lộ trình (Excel)."""

    date: date
    is_today: bool = False
    is_weekend: bool = False
    is_week_start: bool = False
    is_off: bool = False
    bar: TeamTimelineBar | None = None


@dataclass
class RouteStageRow:
    """Một hàng bộ phận trên lưới lộ trình."""

    slug: str
    label: str
    short_label: str
    work_center_id: int = 0
    team_qty_total: str = ''
    total_label: str = ''
    can_drag: bool = False
    can_split: bool = False
    first_date: date | None = None
    last_date: date | None = None
    cells: list[RouteDayCell] = field(default_factory=list)
    headcount: int = 0
    efficiency_pct: Decimal = field(default_factory=lambda: Decimal('0'))
    catalog_headcount: int = 0
    catalog_efficiency_pct: Decimal = field(default_factory=lambda: Decimal('0'))
    work_hours_per_day: Decimal = field(default_factory=lambda: Decimal('0'))
    labor_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    smv_seconds: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_per_day: Decimal = field(default_factory=lambda: Decimal('0'))
    planned_qty: Decimal = field(default_factory=lambda: Decimal('0'))


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
    product_images: list[dict] = field(default_factory=list)
    product_code_label: str = ''
    track_index: int = 0
    track_color: str = '#dc2626'
    track_soft: str = '#fef2f2'
    color_custom: bool = False
    lane_count: int = 1
    line_label: str = ''
    color_label: str = ''
    qty_label: str = ''
    product_name_label: str = ''
    stage_rows: list[RouteStageRow] = field(default_factory=list)


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
    months: int = 1


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


def _clamp_route_months(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 1
    return n if n in (1, 2, 3) else 1


def _months_bounds(start: date, months: int = 1) -> tuple[date, date]:
    """Đầu tháng của ``start`` đến cuối tháng sau ``months - 1`` tháng."""
    months = _clamp_route_months(months)
    first = start.replace(day=1)
    last_start = _shift_month(first, months - 1)
    _, last = _month_bounds(last_start)
    return first, last


def _months_span_label(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f'Tháng {start.month}/{start.year}'
    if start.year == end.year:
        return f'Tháng {start.month}–{end.month}/{start.year}'
    return f'{start.month}/{start.year} – {end.month}/{end.year}'


def _span_bounds(start: date, *, days: int = ROUTE_TIMELINE_DAYS) -> tuple[date, date]:
    """Khoảng ``days`` ngày bắt đầu từ ``start`` (gồm cả ngày đầu)."""
    span = max(1, int(days))
    return start, start + timedelta(days=span - 1)


def _range_label(start: date, end: date) -> str:
    return f'{start.strftime("%d/%m")} – {end.strftime("%d/%m/%Y")}'


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
    from san_xuat.services.work_calendar import is_working_day

    span = (end - start).days + 1
    if span < 1:
        span = 1
        end = start
    day_list = [start + timedelta(days=i) for i in range(span)]
    axis_days: list[TimelineDay] = []
    month_spans: list[dict] = []
    for d in day_list:
        off = not is_working_day(d)
        axis_days.append(
            TimelineDay(
                date=d,
                day=d.day,
                weekday=_WD_VN[d.weekday()],
                is_today=d == today,
                is_weekend=d.weekday() == 6,
                is_week_start=d.weekday() == 0,
                is_off=off,
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


def _pack_timeline_lanes(bars: list[TeamTimelineBar]) -> int:
    """Xếp lane dọc: công đoạn chồng ngày không đè lên nhau."""
    placed = [b for b in bars if b.placed]
    if not placed:
        for bar in bars:
            bar.lane = 0
            bar.lane_count = 1
        return 1
    ordered = sorted(placed, key=lambda b: (b.col_start, b.col_end, b.slug or ''))
    lane_ends: list[int] = []
    for bar in ordered:
        lane = None
        for i, end in enumerate(lane_ends):
            if bar.col_start >= end:
                lane = i
                lane_ends[i] = bar.col_end
                break
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(bar.col_end)
        bar.lane = lane
    n = max(1, len(lane_ends))
    for bar in bars:
        bar.lane_count = n
        if not bar.placed:
            bar.lane = 0
    return n


def _team_qty_value(slug: str, product_flows, fallback_qty: Decimal) -> Decimal:
    """SL kế hoạch số của tổ (Decimal)."""
    key = (slug or '').strip().lower()
    total = Decimal('0')
    matched = False
    for pf in product_flows or []:
        groups = getattr(pf, 'flow_groups', None) or []
        if key and any((getattr(g, 'team_slug', '') or '').strip().lower() == key for g in groups):
            total += _q(getattr(pf, 'qty', 0))
            matched = True
    if not matched:
        total = _q(fallback_qty)
    return total if total > 0 else Decimal('0')


def _team_qty_label(slug: str, product_flows, fallback_qty: Decimal) -> str:
    """SL trên thanh tổ: tổng SL mã hàng đi qua tổ đó."""
    total = _team_qty_value(slug, product_flows, fallback_qty)
    if total <= 0:
        return ''
    return format_sx_num_input(total)


_SHEET_STAGE_LABELS = {
    'cat': 'Cắt',
    'inep': 'In/ép',
    'theu': 'Thêu',
    'may': 'May',
    'ht': 'Ủi',
    'gh': 'Đóng gói',
    'kho': 'Nhập kho',
}
_SHEET_STAGE_ORDER = ('cat', 'inep', 'theu', 'may', 'ht', 'gh', 'kho')
_SHEET_STAGE_ALWAYS = ('cat', 'inep', 'may', 'ht', 'gh')


def _stage_sheet_label(slug: str, full_label: str = '') -> str:
    key = (slug or '').strip().lower()
    if key in _SHEET_STAGE_LABELS:
        return _SHEET_STAGE_LABELS[key]
    from san_xuat.services.progress_template import team_by_slug

    meta = team_by_slug(key)
    if meta and meta.get('label'):
        return str(meta['label'])
    text = (full_label or '').split('(')[0].strip()
    return text or key or 'Công đoạn'


def _color_from_product_code(code: str) -> str:
    s = (code or '').strip()
    i = len(s) - 1
    while i >= 0 and s[i].isalpha():
        i -= 1
    tail = s[i + 1 :]
    if 1 <= len(tail) <= 3:
        return tail
    return ''


def _stage_day_cells(
    axis_days: list[TimelineDay],
    by_day: dict[date, TeamTimelineBar],
) -> list[RouteDayCell]:
    return [
        RouteDayCell(
            date=d.date,
            is_today=d.is_today,
            is_weekend=d.is_weekend,
            is_week_start=d.is_week_start,
            is_off=bool(getattr(d, 'is_off', d.is_weekend)),
            bar=None if getattr(d, 'is_off', False) else by_day.get(d.date),
        )
        for d in axis_days
    ]


def _stage_rows_from_bars(
    bars: list[TeamTimelineBar],
    axis_days: list[TimelineDay],
    *,
    range_start: date,
    range_end: date,
) -> list[RouteStageRow]:
    """Gom thanh tổ thành hàng bộ phận, mỗi ngày một ô SL."""
    from collections import OrderedDict

    grouped: OrderedDict[str, list[TeamTimelineBar]] = OrderedDict()
    from san_xuat.services.work_calendar import is_working_day

    for bar in bars:
        slug = (bar.slug or '').strip().lower()
        if slug == 'npl':
            continue
        grouped.setdefault(slug, []).append(bar)

    ordered = list(_SHEET_STAGE_ALWAYS)
    for key in _SHEET_STAGE_ORDER:
        if key not in ordered and key in grouped:
            ordered.append(key)
    ordered.extend(k for k in grouped if k and k not in ordered)

    out: list[RouteStageRow] = []
    for slug in ordered:
        items = grouped.get(slug) or []
        sample = items[0] if items else None
        by_day: dict[date, TeamTimelineBar] = {}
        for bar in items:
            if not bar.placed:
                continue
            cell_date = bar.plan_date or bar.start
            if cell_date is None:
                continue
            if cell_date < range_start:
                cell_date = range_start
            if cell_date > range_end:
                continue
            if not is_working_day(cell_date):
                continue
            if cell_date not in by_day:
                by_day[cell_date] = bar
        first_date = min(by_day) if by_day else (sample.start if sample else None)
        last_date = max(by_day) if by_day else (sample.end if sample else None)
        cap = _timeline_bar_capacity(sample) if sample else {}
        out.append(RouteStageRow(
            slug=slug,
            label=(sample.label if sample else '') or slug,
            short_label=_stage_sheet_label(slug, sample.label if sample else ''),
            work_center_id=int(sample.work_center_id or 0) if sample else 0,
            team_qty_total=(sample.team_qty_total if sample else '') or '',
            total_label=(sample.team_qty_total if sample else '') or (sample.qty_label if sample else '') or '',
            can_drag=bool(sample.can_drag) if sample else False,
            can_split=bool(slug and slug != 'npl'),
            first_date=first_date,
            last_date=last_date,
            cells=_stage_day_cells(axis_days, by_day),
            **cap,
        ))
    return out


def _day_plans_by_order_team(
    order_ids: list[int],
) -> dict[tuple[int, str], list[SxOrderTeamDayPlan]]:
    ids = [int(x) for x in order_ids if x]
    if not ids:
        return {}
    out: dict[tuple[int, str], list[SxOrderTeamDayPlan]] = {}
    for row in SxOrderTeamDayPlan.objects.filter(sales_order_id__in=ids).order_by('plan_date', 'id'):
        key = (int(row.sales_order_id), (row.team_slug or '').strip().lower())
        out.setdefault(key, []).append(row)
    return out


def _fifo_allocate_done(planned_qtys: list[Decimal], done_total: Decimal) -> list[Decimal]:
    """Phân bổ SL đã làm theo FIFO trên các mảnh ngày."""
    remaining = max(_q(done_total), Decimal('0'))
    allocated: list[Decimal] = []
    for planned in planned_qtys:
        take = min(remaining, max(_q(planned), Decimal('0')))
        allocated.append(take)
        remaining -= take
    return allocated


def _split_qty_pair(qty: Decimal) -> tuple[Decimal, Decimal]:
    """Chia SL thành 2 phần dương, tổng giữ nguyên."""
    total = _q(qty)
    if total < Decimal('0.02'):
        raise PlanningError('SL quá nhỏ để tách thành 2 thẻ.')
    first = (total / 2).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    if first <= 0:
        first = Decimal('0.01')
    second = total - first
    if second <= 0:
        raise PlanningError('SL quá nhỏ để tách thành 2 thẻ.')
    return first, second


def _next_free_workday(start: date, occupied: set[date]) -> date:
    from san_xuat.services.work_calendar import add_working_days, next_working_day

    day = add_working_days(next_working_day(start), 1)
    for _ in range(400):
        if day not in occupied:
            return day
        day = add_working_days(day, 1)
    return day


def _order_team_target_qty(order: SxSalesOrder, slug: str) -> Decimal:
    lines = [ln for ln in order.lines.all() if (ln.qty or 0) > 0]
    plan_rows_qty = Decimal('0')
    for ln in lines:
        plan_rows_qty += _q(ln.qty_to_produce)
    try:
        from san_xuat.services.inter_step_times import _group_slug_scope, _step_team_slug
        from san_xuat.services.order_routing import sales_order_line_routing

        matched = Decimal('0')
        with _group_slug_scope():
            for ln in lines:
                routing = sales_order_line_routing(ln)
                if any((_step_team_slug(step) or '').strip().lower() == slug for step in routing.steps):
                    matched += _q(ln.qty_to_produce)
        return matched if matched > 0 else plan_rows_qty
    except Exception:
        return plan_rows_qty


def _pin_team_planned_date(order: SxSalesOrder, slug: str, pin: date) -> dict[str, date]:
    """Ghim planned_date các bước của tổ = pin; giữ pin các tổ khác."""
    from san_xuat.services.work_calendar import next_working_day

    steps = _load_schedule_steps(order)
    spans = team_khsx_spans(order, plan_steps=steps)
    prod = [s for s in spans if s.slug != 'npl']
    starts: dict[str, date] = {
        span.slug: span.start for span in prod if span.start
    }
    starts[slug] = next_working_day(pin) if pin else pin
    written = _write_team_planned_dates(steps, starts, require_slug=slug)
    if written <= 0:
        raise PlanningError('Không gán được công đoạn của tổ này.')
    return starts


@transaction.atomic
def save_team_day_plans(
    *,
    order_id: int,
    team_slug: str,
    rows: list[dict],
) -> SxSalesOrder:
    """Lưu phân bổ SL theo ngày cho một tổ. Tổng SL phải khớp kế hoạch tổ."""
    from san_xuat.services.work_calendar import next_working_day

    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    _assert_schedule_editable(order)
    slug = (team_slug or '').strip().lower()
    if not slug or slug == 'npl':
        raise PlanningError('Không tách công đoạn NPL.')

    steps = _load_schedule_steps(order)
    spans = team_khsx_spans(order, plan_steps=steps)
    prod = [s for s in spans if s.slug != 'npl']
    if slug not in {s.slug for s in prod}:
        raise PlanningError('Tổ này không tham gia đơn.')

    target_qty = _order_team_target_qty(order, slug)

    parsed: list[tuple[date, Decimal]] = []
    for raw in rows or []:
        d = raw.get('date') if isinstance(raw, dict) else None
        if isinstance(d, str):
            from san_xuat.list_filters import parse_sx_date
            d = parse_sx_date(d.strip())
        if not isinstance(d, date):
            continue
        qty = _q(raw.get('qty') if isinstance(raw, dict) else 0)
        if qty <= 0:
            continue
        parsed.append((d, qty))

    if not parsed:
        SxOrderTeamDayPlan.objects.filter(sales_order=order, team_slug=slug).delete()
        return order

    total = sum((q for _d, q in parsed), Decimal('0'))
    if abs(total - target_qty) > Decimal('0.01'):
        raise PlanningError(
            f'Tổng SL tách ({format_sx_num_input(total)}) phải bằng SL tổ ({format_sx_num_input(target_qty)}).'
        )

    SxOrderTeamDayPlan.objects.filter(sales_order=order, team_slug=slug).delete()
    from san_xuat.services.work_calendar import add_working_days

    occupied: set[date] = set()
    assigned: list[tuple[date, Decimal]] = []
    for d, q in parsed:
        day = next_working_day(d)
        while day in occupied:
            day = add_working_days(day, 1)
        occupied.add(day)
        assigned.append((day, q))

    SxOrderTeamDayPlan.objects.bulk_create([
        SxOrderTeamDayPlan(sales_order=order, team_slug=slug, plan_date=d, qty=q)
        for d, q in assigned
    ])
    pin = min(d for d, _qty in assigned)
    starts = _pin_team_planned_date(order, slug, pin)
    return _sync_schedule_to_mos(order, starts)


@transaction.atomic
def split_team_bar_in_two(
    *,
    order_id: int,
    team_slug: str,
    from_date: date | None = None,
    segment_id: int = 0,
) -> SxSalesOrder:
    """Tách một thanh công đoạn thành 2 thẻ độc lập để kéo trên lộ trình."""
    from san_xuat.services.work_calendar import next_working_day

    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    _assert_schedule_editable(order)
    slug = (team_slug or '').strip().lower()
    if not slug or slug == 'npl':
        raise PlanningError('Không tách công đoạn NPL.')

    steps = _load_schedule_steps(order)
    spans = team_khsx_spans(order, plan_steps=steps)
    prod = [s for s in spans if s.slug != 'npl']
    span = next((s for s in prod if s.slug == slug), None)
    if span is None:
        raise PlanningError('Tổ này không tham gia đơn.')

    existing = list(
        SxOrderTeamDayPlan.objects.filter(sales_order=order, team_slug=slug).order_by('plan_date', 'id')
    )
    if existing:
        src = None
        sid = int(segment_id or 0)
        if sid:
            src = next((row for row in existing if int(row.pk) == sid), None)
        if src is None and isinstance(from_date, date):
            src = next((row for row in existing if row.plan_date == from_date), None)
        if src is None:
            src = existing[0]
        first, second = _split_qty_pair(src.qty)
        occupied = {row.plan_date for row in existing}
        second_day = _next_free_workday(src.plan_date, occupied)
        src.qty = first
        src.save(update_fields=['qty'])
        SxOrderTeamDayPlan.objects.create(
            sales_order=order,
            team_slug=slug,
            plan_date=second_day,
            qty=second,
        )
        pin = min(src.plan_date, second_day, *(row.plan_date for row in existing))
    else:
        target = _order_team_target_qty(order, slug)
        first, second = _split_qty_pair(target)
        start = from_date or span.start or timezone.localdate()
        first_day = next_working_day(start)
        second_day = _next_free_workday(first_day, {first_day})
        SxOrderTeamDayPlan.objects.bulk_create([
            SxOrderTeamDayPlan(sales_order=order, team_slug=slug, plan_date=first_day, qty=first),
            SxOrderTeamDayPlan(sales_order=order, team_slug=slug, plan_date=second_day, qty=second),
        ])
        pin = min(first_day, second_day)

    starts = _pin_team_planned_date(order, slug, pin)
    return _sync_schedule_to_mos(order, starts)


@transaction.atomic
def move_team_day_plan(
    *,
    order_id: int,
    team_slug: str,
    from_date: date,
    to_date: date,
) -> SxSalesOrder:
    """Kéo một mảnh ngày đã tách sang ngày khác (gộp nếu trùng)."""
    from san_xuat.services.work_calendar import next_working_day

    if not isinstance(from_date, date) or not isinstance(to_date, date):
        raise PlanningError('Ngày không hợp lệ.')
    order = SxSalesOrder.objects.select_for_update().get(pk=order_id, is_demo=False)
    _assert_schedule_editable(order)
    slug = (team_slug or '').strip().lower()
    if not slug or slug == 'npl':
        raise PlanningError('Không kéo thanh chuẩn bị NPL — sửa ngày mua trên kế hoạch.')

    new_day = next_working_day(to_date)
    old_day = from_date
    qs = SxOrderTeamDayPlan.objects.filter(sales_order=order, team_slug=slug)
    src = qs.filter(plan_date=old_day).first()
    if not src:
        # Không tìm thấy mảnh — kéo cả khối (và xóa day-plans lệch nếu có)
        qs.delete()
        return _move_team_start_independent(order, slug=slug, start_date=new_day)

    if new_day == old_day:
        return order

    dst = qs.filter(plan_date=new_day).first()
    if dst:
        dst.qty = _q(dst.qty) + _q(src.qty)
        dst.save(update_fields=['qty'])
        src.delete()
    else:
        src.plan_date = new_day
        src.save(update_fields=['plan_date'])

    remaining = list(qs.order_by('plan_date'))
    if not remaining:
        return order
    pin = remaining[0].plan_date
    starts = _pin_team_planned_date(order, slug, pin)
    return _sync_schedule_to_mos(order, starts)


def _done_qty_by_order_team(order_ids: list[int]) -> dict[tuple[int, str], Decimal]:
    """SL đã thực hiện (TKSX confirmed) theo (order_id, team_slug).

    Trong mỗi LSX × tổ: lấy max theo công đoạn (tránh cộng đôi áo+quần),
    rồi cộng các LSX thuộc cùng đơn.
    """
    from san_xuat.services.progress_template import TEAM_SLUGS, team_slug_for_process_label

    ids = [int(x) for x in order_ids if x]
    if not ids:
        return {}
    label_to_slug = {
        (lab or '').strip().casefold(): slug
        for slug, _gk, _mk, lab in TEAM_SLUGS
        if (lab or '').strip()
    }
    stats = (
        SxProductionStat.objects.filter(
            is_demo=False,
            status=SxProductionStat.STATUS_CONFIRMED,
            production_order__sales_order_id__in=ids,
            production_order__is_demo=False,
        )
        .exclude(production_order__status=SxProductionOrder.STATUS_CANCELLED)
        .values(
            'production_order_id',
            'production_order__sales_order_id',
            'process_name',
            'team_label',
            'qty_good',
        )
    )
    by_mo_proc: dict[tuple[int, str, str], Decimal] = {}
    mo_order: dict[int, int] = {}
    for st in stats:
        mid = int(st['production_order_id'])
        oid = int(st['production_order__sales_order_id'] or 0)
        if not oid:
            continue
        mo_order[mid] = oid
        slug = team_slug_for_process_label(st.get('process_name') or '')
        if not slug:
            tl = (st.get('team_label') or '').strip().casefold()
            slug = label_to_slug.get(tl) or ''
            if not slug and tl:
                for lab, s in label_to_slug.items():
                    if lab and (lab in tl or tl in lab):
                        slug = s
                        break
        if not slug:
            continue
        proc = (st.get('process_name') or '').strip().casefold() or '_'
        key = (mid, slug, proc)
        by_mo_proc[key] = by_mo_proc.get(key, Decimal('0')) + _q(st.get('qty_good') or 0)

    by_mo_team: dict[tuple[int, str], Decimal] = {}
    for (mid, slug, _proc), qty in by_mo_proc.items():
        k = (mid, slug)
        cur = by_mo_team.get(k)
        by_mo_team[k] = qty if cur is None or qty > cur else cur

    out: dict[tuple[int, str], Decimal] = {}
    for (mid, slug), qty in by_mo_team.items():
        oid = mo_order.get(mid)
        if not oid:
            continue
        k = (oid, slug)
        out[k] = out.get(k, Decimal('0')) + qty
    return out


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
    months: int = 1,
) -> MoTimelineBoard:
    """Timeline đơn trên KHSX — lưới 1/2/3 tháng, mặc định tháng hiện tại."""
    today = timezone.localdate()
    months = _clamp_route_months(months)
    if range_from and range_to and range_to < range_from:
        range_from, range_to = range_to, range_from
    start, end = _months_bounds(range_from or today, months)
    axis_days, month_spans, span = _timeline_axis(start, end, today)

    accepts_by_order = _accepted_teams_by_order_ids([r.order.pk for r in plan_rows])
    done_by_order_team = _done_qty_by_order_team([r.order.pk for r in plan_rows])
    day_plans_map = _day_plans_by_order_team([r.order.pk for r in plan_rows])

    rows: list[PlanTimelineRow] = []
    unscheduled: list = []
    grid_row = 3
    line_no = 0
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
            if ts.slug == 'npl':
                continue
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
        names = [n for pf in (r.product_flows or []) if (n := (pf.product_name or pf.product_code or '').strip())]
        subtitle = (r.order.customer_name or '').strip()
        if names:
            extra = names[0] if len(names) == 1 else f'{len(names)} mã'
            subtitle = f'{subtitle} · {extra}' if subtitle else extra
        product_codes: list[str] = []
        seen_codes: set[str] = set()
        for pf in r.product_flows or []:
            code = (pf.product_code or '').strip()
            key = code.casefold()
            if not code or key in seen_codes:
                continue
            seen_codes.add(key)
            product_codes.append(code)
        if not product_codes:
            product_code_label = r.order.code
        elif len(product_codes) == 1:
            product_code_label = product_codes[0]
        else:
            product_code_label = f'{product_codes[0]} +{len(product_codes) - 1}'
        product_images = []
        for pf in r.product_flows or []:
            product_images.append({
                'url': pf.image_url or '',
                'urls_json': pf.image_urls_json,
                'name': pf.product_name or pf.product_code,
            })
        track_color, track_soft = route_track_pair(r.order)
        can_drag = r.can_adjust_timeline
        span_days = max(1, (bar_end - bar_start).days + 1)
        status_key = r.order.plan_status
        if status_key == SxSalesOrder.PLAN_RANKED:
            status_key = SxSalesOrder.PLAN_QUEUED
        if status_key in (SxSalesOrder.PLAN_QUEUED, SxSalesOrder.PLAN_ON_HOLD):
            status_label = 'Chờ xếp'
            if status_key == SxSalesOrder.PLAN_ON_HOLD:
                status_label = 'Tạm giữ'
        elif status_key == SxSalesOrder.PLAN_DONE:
            status_label = 'Hoàn thành'
        else:
            status_label = 'Đang sản xuất'
        team_bars: list[TeamTimelineBar] = []
        if visible_spans:
            for i, (ts, placed_team) in enumerate(visible_spans):
                slug_key = (ts.slug or '').strip().lower()
                day_rows = day_plans_map.get((r.order.pk, slug_key), [])
                team_total = _team_qty_value(ts.slug, r.product_flows, r.total_qty)
                team_total_label = format_sx_num_input(team_total) if team_total > 0 else ''
                done_total = done_by_order_team.get((r.order.pk, slug_key), Decimal('0'))
                can_team_drag = can_drag and ts.slug != 'npl' and getattr(ts, 'can_drag', True)

                if day_rows:
                    planned_list = [_q(d.qty) for d in day_rows]
                    done_parts = _fifo_allocate_done(planned_list, done_total)
                    first_bar = True
                    for di, day_row in enumerate(day_rows):
                        d_start = day_row.plan_date
                        d_end = day_row.plan_date
                        placed_day = _bar_columns(d_start, d_end, start, end)
                        if placed_day is None:
                            continue
                        t_col_s, t_col_e, t_len = placed_day
                        qty_label = format_sx_num_input(day_row.qty) if _q(day_row.qty) > 0 else '0'
                        done_part = done_parts[di] if di < len(done_parts) else Decimal('0')
                        done_qty_label = format_sx_num_input(done_part) if done_part > 0 else '0'
                        team_bars.append(TeamTimelineBar(
                            slug=ts.slug,
                            label=ts.label,
                            start=d_start,
                            end=d_end,
                            col_start=t_col_s,
                            col_end=t_col_e,
                            vis_days=t_len,
                            bar_text=qty_label,
                            clips_left=False,
                            clips_right=False,
                            can_drag=can_team_drag,
                            span_days=1,
                            minutes=ts.minutes,
                            duration_label=ts.duration_label or '',
                            grid_row=grid_row,
                            is_first=first_bar,
                            placed=True,
                            qty_label=qty_label,
                            done_qty_label=done_qty_label,
                            is_split=True,
                            segment_id=int(day_row.pk),
                            plan_date=d_start,
                            team_qty_total=team_total_label,
                            work_center_id=int(getattr(ts, 'work_center_id', 0) or 0),
                            **_timeline_bar_capacity(ts),
                        ))
                        first_bar = False
                    continue

                t_col_s, t_col_e, t_len = placed_team
                qty_label = _team_qty_label(ts.slug, r.product_flows, r.total_qty)
                done_qty_label = format_sx_num_input(done_total) if done_total > 0 else '0'
                team_bars.append(TeamTimelineBar(
                    slug=ts.slug,
                    label=ts.label,
                    start=ts.start,
                    end=ts.end,
                    col_start=t_col_s,
                    col_end=t_col_e,
                    vis_days=t_len,
                    bar_text=qty_label,
                    clips_left=ts.start < start,
                    clips_right=ts.end > end,
                    can_drag=can_team_drag,
                    span_days=max(1, (ts.end - ts.start).days + 1),
                    minutes=ts.minutes,
                    duration_label=ts.duration_label or '',
                    grid_row=grid_row,
                    is_first=(i == 0),
                    placed=True,
                    qty_label=qty_label,
                    done_qty_label=done_qty_label,
                    is_split=False,
                    segment_id=0,
                    plan_date=ts.start,
                    team_qty_total=team_total_label,
                    work_center_id=int(getattr(ts, 'work_center_id', 0) or 0),
                    **_timeline_bar_capacity(ts),
                ))
        else:
            qty_label = format_sx_num_input(r.total_qty) if r.total_qty else ''
            team_bars.append(TeamTimelineBar(
                slug='',
                label='Chưa có công đoạn',
                start=bar_start,
                end=bar_end,
                col_start=col_start,
                col_end=col_end,
                vis_days=length,
                bar_text=qty_label,
                clips_left=False,
                clips_right=False,
                can_drag=False,
                span_days=span_days,
                minutes=Decimal('0'),
                duration_label='',
                grid_row=grid_row,
                is_first=True,
                placed=False,
                qty_label=qty_label,
                done_qty_label='0',
            ))
        lane_count = _pack_timeline_lanes(team_bars)
        grid_row += 1
        line_no += 1
        colors = []
        seen_color: set[str] = set()
        for code in product_codes:
            c = _color_from_product_code(code)
            if c and c.casefold() not in seen_color:
                seen_color.add(c.casefold())
                colors.append(c)
        color_label = ', '.join(colors)
        qty_label = format_sx_num_input(r.total_qty) if r.total_qty else ''
        stage_rows = _stage_rows_from_bars(
            team_bars, axis_days, range_start=start, range_end=end,
        )
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
            product_images=product_images,
            product_code_label=product_code_label,
            product_name_label=' · '.join(names),
            track_index=route_track_index(r.order.pk),
            track_color=track_color,
            track_soft=track_soft,
            color_custom=bool((r.order.plan_color or '').strip()),
            lane_count=lane_count,
            line_label=f'Line {line_no}',
            color_label=color_label,
            qty_label=qty_label,
            stage_rows=stage_rows,
        ))

    today_col = (today - start).days + 1 if start <= today <= end else None
    default_from, default_to = _months_bounds(today, months)
    prev_from, prev_to = _months_bounds(_shift_month(start, -1), months)
    next_from, next_to = _months_bounds(_shift_month(start, 1), months)
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
        month_label=_months_span_label(start, end),
        is_current_month=(start == default_from and end == default_to),
        months=months,
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
