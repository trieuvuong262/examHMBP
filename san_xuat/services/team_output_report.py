"""Báo cáo sản lượng tổ theo ngày (tab Tổ SX trên bảng KHSX).

Hàng = tổ bộ phận HR, cột = ngày. SL ô = số bộ tổ làm xong trong ngày:
mỗi lệnh × size lấy min các công đoạn của tổ (như phiếu tiến độ tổ), rồi cộng
các size và các lệnh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.db.models import Prefetch, Q

from san_xuat.hub_models import (
    SxMoProcessStep,
    SxOrderTeamDayPlan,
    SxProductionOrder,
    SxProductionStat,
)

ZERO = Decimal('0')

@dataclass
class TeamOutputCell:
    day: date
    qty: Decimal = ZERO
    plan: Decimal | None = None
    is_workday: bool = True
    is_today: bool = False
    is_past: bool = False
    orders: list[tuple[str, Decimal]] = field(default_factory=list)
    plan_orders: list[dict] = field(default_factory=list)

    @property
    def has_value(self) -> bool:
        return bool(self.qty) or bool(self.plan)

    @property
    def state(self) -> str:
        """met / under / miss khi ngày đã qua có kế hoạch; '' nếu chưa tới hạn hoặc không KH."""
        if not self.plan or not self.is_past:
            return ''
        if self.qty >= self.plan:
            return 'met'
        return 'under' if self.qty > 0 else 'miss'

    @property
    def tip(self) -> str:
        from san_xuat.templatetags.sx_format import sx_num

        parts = [f'Dự kiến {sx_num(self.plan or 0)} · Thực hiện {sx_num(self.qty)}']
        parts += [f'{code}: {sx_num(qty)}' for code, qty in self.orders]
        return '\n'.join(parts)


@dataclass
class TeamOutputRow:
    slug: str
    label: str
    stage_slug: str
    stage_label: str
    color_slug: str = ''
    cells: list[TeamOutputCell] = field(default_factory=list)
    total: Decimal = ZERO
    plan_total: Decimal = ZERO
    active_days: int = 0
    avg_per_day: Decimal = ZERO
    best_day: date | None = None
    best_qty: Decimal = ZERO
    low_day: date | None = None
    low_qty: Decimal = ZERO
    order_count: int = 0
    stage_share: Decimal | None = None

    @property
    def plan_rate(self) -> Decimal | None:
        if self.plan_total <= 0:
            return None
        return (self.total * 100 / self.plan_total).quantize(Decimal('1'))


@dataclass
class TeamOutputStage:
    slug: str
    label: str
    rows: list[TeamOutputRow] = field(default_factory=list)
    day_totals: list[Decimal] = field(default_factory=list)
    day_plans: list[Decimal | None] = field(default_factory=list)
    foot: list[TeamOutputCell] = field(default_factory=list)
    total: Decimal = ZERO
    plan_total: Decimal = ZERO
    active_days: int = 0
    avg_per_day: Decimal = ZERO

    @property
    def plan_rate(self) -> Decimal | None:
        if self.plan_total <= 0:
            return None
        return (self.total * 100 / self.plan_total).quantize(Decimal('1'))

    @property
    def best_qty(self) -> Decimal:
        return max(self.day_totals, default=ZERO)


@dataclass
class TeamOutputReport:
    date_from: date
    date_to: date
    days: list[TeamOutputCell]
    stages: list[TeamOutputStage]
    workday_count: int = 0
    active_team_count: int = 0
    idle_teams: list[str] = field(default_factory=list)
    unlabeled_qty: Decimal = ZERO
    day_details: dict = field(default_factory=dict)

    @property
    def rows(self) -> list[TeamOutputRow]:
        return [r for st in self.stages for r in st.rows]

    @property
    def has_data(self) -> bool:
        return any(st.total > 0 for st in self.stages)


def _stage_label(stage_slug: str) -> str:
    from san_xuat.services.progress_template import TEAM_SLUGS

    for slug, _gk, _mk, label in TEAM_SLUGS:
        if slug == stage_slug:
            return label
    return 'Chất lượng & khác'


def _q(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return ZERO


def _team_day_qty_for_mo(
    mo: SxProductionOrder,
    *,
    sizes,
    keys: set[str],
    label_map: dict,
    stats: list[SxProductionStat],
    date_from: date,
    date_to: date,
) -> dict[date, Decimal]:
    """SL theo bộ của một tổ trên một lệnh, theo ngày.

    Dòng ghi không size (tổ nhập tổng) gom vào nhóm riêng `''` thay vì bỏ qua.
    """
    if not keys:
        return {}
    size_set = {r.size_label for r in sizes} | {''}
    single_total = len(sizes) == 1 and sizes[0].size_label == 'Tổng'
    acc: dict[date, dict[tuple[str, str], Decimal]] = {}
    for st in stats:
        if not (date_from <= st.stat_date <= date_to):
            continue
        step = label_map.get((st.process_name or '').strip().casefold())
        if not step or step.key not in keys:
            continue
        size = (st.size_label or '').strip()
        if single_total:
            size = 'Tổng'
        elif size not in size_set:
            continue
        qty = _q(st.qty_good)
        if qty <= 0:
            continue
        day = acc.setdefault(st.stat_date, {})
        day[(size, step.key)] = day.get((size, step.key), ZERO) + qty
    out: dict[date, Decimal] = {}
    for d, cells in acc.items():
        total = sum(
            (min((cells.get((sz, k), ZERO) for k in keys), default=ZERO) for sz in size_set),
            ZERO,
        )
        if total > 0:
            out[d] = total
    return out


def _plan_by_team_day(
    teams, *, date_from: date, date_to: date,
) -> tuple[
    dict[str, dict[date, Decimal]],
    dict[str, dict[date, Decimal]],
    dict[str, dict[date, list[dict]]],
]:
    """SL phân bổ ngày KHSX → (theo tổ, theo công đoạn, đơn của từng tổ/ngày).

    Dòng gắn mã tổ `d{id}` hoặc mã tổ năng lực thì vào đúng bộ phận. Slug công
    đoạn cũ chỉ gom khi công đoạn đó còn đúng một tổ.
    """
    from django.urls import reverse

    from san_xuat.hub_models import SxSalesOrderLine, SxSalesOrderPlanStep

    by_slug = {col.slug: col for col in teams}
    by_wc: dict[str, str] = {}
    teams_by_stage: dict[str, list[str]] = {}
    for col in teams:
        stage = (col.meta.get('stage_slug') or '').strip().lower()
        code = (col.meta.get('work_center_code') or '').strip().upper()
        if code:
            by_wc[code] = col.slug
        if stage:
            teams_by_stage.setdefault(stage, []).append(col.slug)

    def _team_for(slug: str, code: str) -> str:
        key = (slug or '').strip().lower()
        if key in by_slug:
            return key
        wc = (code or '').strip().upper()
        if wc and wc in by_wc:
            return by_wc[wc]
        members = teams_by_stage.get(key) or []
        if len(members) == 1:
            return members[0]
        return ''

    rows = list(
        SxOrderTeamDayPlan.objects.filter(
            plan_date__range=(date_from, date_to),
            sales_order__is_demo=False,
            qty__gt=0,
        ).select_related('sales_order', 'work_center')
    )
    order_ids = {row.sales_order_id for row in rows}
    products: dict[int, list[str]] = {}
    if order_ids:
        for oid, code, name in SxSalesOrderLine.objects.filter(
            order_id__in=order_ids,
        ).values_list('order_id', 'product_code', 'product_name'):
            label = ' '.join(part for part in ((code or '').strip(), (name or '').strip()) if part)
            if not label or label in products.get(oid, ()):
                continue
            products.setdefault(oid, []).append(label)

    order_teams: dict[int, set[str]] = {}
    if order_ids and by_wc:
        for oid, code in SxSalesOrderPlanStep.objects.filter(
            sales_order_id__in=order_ids,
            work_center__code__in=list(by_wc),
        ).values_list('sales_order_id', 'work_center__code'):
            team = by_wc.get((code or '').strip().upper())
            if team:
                order_teams.setdefault(oid, set()).add(team)

    by_team: dict[str, dict[date, Decimal]] = {}
    by_stage: dict[str, dict[date, Decimal]] = {}
    orders: dict[str, dict[date, dict[int, dict]]] = {}

    def _add(bucket: dict, key: str, day: date, qty: Decimal) -> None:
        inner = bucket.setdefault(key, {})
        inner[day] = inner.get(day, ZERO) + qty

    for row in rows:
        team = _team_for(row.team_slug, getattr(row.work_center, 'code', '') or '')
        if not team:
            stage = (row.team_slug or '').strip().lower()
            candidates = [
                slug for slug in (teams_by_stage.get(stage) or [])
                if slug in order_teams.get(row.sales_order_id, ())
            ]
            if len(candidates) == 1:
                team = candidates[0]
        if not team:
            continue
        qty = _q(row.qty)
        day = row.plan_date
        col = by_slug[team]
        stage = (col.meta.get('stage_slug') or '').strip().lower()
        if stage:
            _add(by_stage, stage, day, qty)
        _add(by_team, team, day, qty)
        order = row.sales_order
        bucket = orders.setdefault(team, {}).setdefault(day, {})
        hit = bucket.get(order.pk)
        if hit is None:
            names = products.get(order.pk) or []
            product = ', '.join(names[:3])
            if len(names) > 3:
                product = f'{product}…'
            bucket[order.pk] = {
                'code': order.code,
                'customer': (order.customer_name or '').strip(),
                'product': product,
                'qty': qty,
                'due': order.due_date.strftime('%d/%m/%Y') if order.due_date else '',
                'url': reverse('san_xuat:sales_order_detail', args=[order.pk]),
            }
        else:
            hit['qty'] = hit['qty'] + qty
    listed = {
        team: {day: list(items.values()) for day, items in days.items()}
        for team, days in orders.items()
    }
    return by_team, by_stage, listed


def build_team_output_report(
    *,
    date_from: date,
    date_to: date,
    search: str = '',
    today: date | None = None,
) -> TeamOutputReport:
    from django.utils import timezone

    from san_xuat.services.goods_progress import _team_columns
    from san_xuat.services.order_progress_sheet import (
        _size_plans,
        progress_steps_for_mo,
        progress_steps_for_team,
        stats_for_team,
    )
    from san_xuat.services.work_calendar import working_days

    today = today or timezone.localdate()
    from san_xuat.services.plan_board import _factory_slug_rank

    rank = _factory_slug_rank()
    teams = sorted(
        _team_columns(),
        key=lambda col: (rank.get(col.slug, 99), col.label),
    )
    workdays = set(working_days(date_from, date_to))
    day_list: list[date] = []
    d = date_from
    while d <= date_to:
        day_list.append(d)
        d += timedelta(days=1)

    stats_qs = SxProductionStat.objects.filter(
        is_demo=False,
        status=SxProductionStat.STATUS_CONFIRMED,
        stat_date__range=(date_from, date_to),
        production_order__isnull=False,
    )
    if search:
        stats_qs = stats_qs.filter(
            Q(production_order__code__icontains=search)
            | Q(production_order__product_code__icontains=search)
            | Q(production_order__product_name__icontains=search)
            | Q(production_order__sales_order__code__icontains=search)
        )
    stats_by_mo: dict[int, list[SxProductionStat]] = {}
    unlabeled = ZERO
    for st in stats_qs.only(
        'production_order_id', 'stat_date', 'process_name', 'size_label', 'qty_good', 'team_label',
    ):
        if not (st.team_label or '').strip():
            unlabeled += _q(st.qty_good)
            continue
        stats_by_mo.setdefault(st.production_order_id, []).append(st)

    mos = list(
        SxProductionOrder.objects.filter(pk__in=list(stats_by_mo))
        .select_related('sales_order')
        .prefetch_related(
            Prefetch(
                'mo_process_steps',
                queryset=SxMoProcessStep.objects.select_related('work_center').order_by('sequence', 'id'),
            ),
        )
    )

    qty: dict[str, dict[date, Decimal]] = {}
    orders: dict[str, dict[date, list[tuple[str, Decimal]]]] = {}
    team_mos: dict[str, set[int]] = {}
    for mo in mos:
        mo_steps = progress_steps_for_mo(mo)
        if not mo_steps:
            continue
        sizes = _size_plans(mo)
        if not sizes:
            continue
        label_map = {s.label.casefold(): s for s in mo_steps}
        mo_stats = stats_by_mo.get(mo.pk, [])
        for col in teams:
            steps = progress_steps_for_team(mo, col.meta, steps=mo_steps)
            if not steps:
                continue
            per_day = _team_day_qty_for_mo(
                mo,
                sizes=sizes,
                keys={s.key for s in steps},
                label_map=label_map,
                stats=stats_for_team(mo_stats, col.meta),
                date_from=date_from,
                date_to=date_to,
            )
            if not per_day:
                continue
            team_mos.setdefault(col.slug, set()).add(mo.pk)
            bucket = qty.setdefault(col.slug, {})
            ob = orders.setdefault(col.slug, {})
            for day, v in per_day.items():
                bucket[day] = bucket.get(day, ZERO) + v
                ob.setdefault(day, []).append((mo.code, v))

    plans, stage_plans, plan_orders = _plan_by_team_day(teams, date_from=date_from, date_to=date_to)
    from san_xuat.services.team_stage_colors import team_stage_palette

    palette = team_stage_palette()

    stages: dict[str, TeamOutputStage] = {}
    for col in teams:
        stage_slug = (col.meta.get('stage_slug') or '').strip().lower()
        stage = stages.get(stage_slug)
        if stage is None:
            stage = TeamOutputStage(
                slug=stage_slug,
                label=_stage_label(stage_slug),
                day_totals=[ZERO] * len(day_list),
            )
            stages[stage_slug] = stage
        row = TeamOutputRow(
            slug=col.slug,
            label=col.label,
            stage_slug=stage_slug,
            stage_label=stage.label,
            color_slug=col.slug if col.slug in palette else (stage_slug or col.slug),
            order_count=len(team_mos.get(col.slug, ())),
        )
        t_qty = qty.get(col.slug, {})
        t_plan = plans.get(col.slug, {})
        t_orders = orders.get(col.slug, {})
        t_plan_orders = plan_orders.get(col.slug, {})
        for i, day in enumerate(day_list):
            v = t_qty.get(day, ZERO)
            cell = TeamOutputCell(
                day=day,
                qty=v,
                plan=t_plan.get(day),
                is_workday=day in workdays,
                is_today=day == today,
                is_past=day <= today,
                orders=sorted(t_orders.get(day, []), key=lambda t: -t[1]),
                plan_orders=sorted(t_plan_orders.get(day, []), key=lambda item: item['code']),
            )
            row.cells.append(cell)
            stage.day_totals[i] += v
            row.total += v
            row.plan_total += t_plan.get(day) or ZERO
        active = [c for c in row.cells if c.qty > 0]
        row.active_days = len(active)
        if active:
            row.avg_per_day = (row.total / len(active)).quantize(Decimal('1'))
            best = max(active, key=lambda c: c.qty)
            low = min(active, key=lambda c: c.qty)
            row.best_day, row.best_qty = best.day, best.qty
            row.low_day, row.low_qty = low.day, low.qty
        stage.rows.append(row)
        stage.total += row.total

    for stage in stages.values():
        s_plan = stage_plans.get(stage.slug, {})
        stage.day_plans = [s_plan.get(day) for day in day_list]
        stage.plan_total = sum(s_plan.values(), ZERO)
        stage.foot = [
            TeamOutputCell(
                day=day,
                qty=stage.day_totals[i],
                plan=stage.day_plans[i],
                is_workday=day in workdays,
                is_today=day == today,
                is_past=day <= today,
            )
            for i, day in enumerate(day_list)
        ]

    stage_order = [s.slug for s in teams_stage_order(teams)]
    ordered = sorted(stages.values(), key=lambda s: stage_order.index(s.slug) if s.slug in stage_order else 99)
    for stage in ordered:
        active_days = sum(1 for v in stage.day_totals if v > 0)
        stage.active_days = active_days
        if active_days:
            stage.avg_per_day = (stage.total / active_days).quantize(Decimal('1'))
        for row in stage.rows:
            if stage.total > 0 and len(stage.rows) > 1:
                row.stage_share = (row.total * 100 / stage.total).quantize(Decimal('1'))

    report = TeamOutputReport(
        date_from=date_from,
        date_to=date_to,
        days=[
            TeamOutputCell(day=d, is_workday=d in workdays, is_today=d == today)
            for d in day_list
        ],
        stages=ordered,
        workday_count=len(workdays),
        unlabeled_qty=unlabeled,
    )
    rows = report.rows
    report.active_team_count = sum(1 for r in rows if r.total > 0)
    report.idle_teams = [r.label for r in rows if r.total <= 0]
    report.day_details = _day_detail_payload(rows)
    return report


_WD_VN = ('Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật')


def _day_detail_payload(rows: list[TeamOutputRow]) -> dict:
    """JSON cho modal: bấm một ngày của một tổ → các đơn cần làm ngày đó."""
    from san_xuat.templatetags.sx_format import format_sx_num

    payload: dict[str, dict] = {}
    for row in rows:
        for cell in row.cells:
            if not cell.plan_orders and not cell.orders:
                continue
            orders = []
            for item in cell.plan_orders:
                orders.append({
                    'code': item['code'],
                    'customer': item['customer'],
                    'product': item['product'],
                    'qty': format_sx_num(item['qty']),
                    'due': item['due'],
                    'url': item['url'],
                })
            done = [
                {'code': code, 'qty': format_sx_num(qty)}
                for code, qty in cell.orders
            ]
            payload[f'{row.slug}|{cell.day.isoformat()}'] = {
                'team': row.label,
                'date': cell.day.strftime('%d/%m/%Y'),
                'weekday': _WD_VN[cell.day.weekday()],
                'plan': format_sx_num(cell.plan or 0),
                'done': format_sx_num(cell.qty),
                'orders': orders,
                'done_orders': done,
            }
    return payload


def teams_stage_order(teams) -> list[SimpleNamespace]:
    seen: list[str] = []
    for col in teams:
        s = (col.meta.get('stage_slug') or '').strip().lower()
        if s not in seen:
            seen.append(s)
    return [SimpleNamespace(slug=s) for s in seen]


def export_team_output_xlsx(report: TeamOutputReport):
    """Xuất bảng Tổ × ngày ra Excel (cùng bố cục tab Tổ SX)."""
    from io import BytesIO

    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.cell.cell import MergedCell
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = 'San luong to'
    thin = Side(style='thin', color='CBD5E1')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill('solid', fgColor='F1F5F9')
    off_fill = PatternFill('solid', fgColor='F8FAFC')
    plan_fill = PatternFill('solid', fgColor='DBEAFE')
    state_font = {
        'met': Font(color='047857', bold=True),
        'under': Font(color='B45309', bold=True),
        'miss': Font(color='B91C1C', bold=True),
    }
    bold = Font(bold=True)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left = Alignment(horizontal='left', vertical='center')
    num_fmt = '#,##0'

    ws.cell(row=1, column=1, value=(
        f'Sản lượng tổ theo ngày {report.date_from:%d/%m/%Y} – {report.date_to:%d/%m/%Y}'
    )).font = Font(bold=True, size=14)

    summary_heads = ['Cả kỳ', '% KH', 'TB/ngày', 'Cao nhất', 'Số ngày']
    n_days = len(report.days)
    first_day_col = 3
    head_row = 3
    ws.cell(row=head_row, column=1, value='Tổ')
    ws.cell(row=head_row, column=2, value='')
    for i, c in enumerate(report.days):
        ws.cell(row=head_row, column=first_day_col + i, value=f'{c.day:%d/%m}')
    sum_col = first_day_col + n_days
    for j, label in enumerate(summary_heads):
        ws.cell(row=head_row, column=sum_col + j, value=label)
    last_col = sum_col + len(summary_heads) - 1
    for col in range(1, last_col + 1):
        cell = ws.cell(row=head_row, column=col)
        cell.font = bold
        cell.fill = head_fill
        cell.alignment = center
        cell.border = border
    for i, c in enumerate(report.days):
        if not c.is_workday:
            ws.cell(row=head_row, column=first_day_col + i).fill = off_fill

    def _num(cell, v) -> None:
        cell.value = float(v) if v else None
        cell.number_format = num_fmt
        cell.alignment = center
        cell.border = border

    def _write_pair(r: int, label: str, cells: list[TeamOutputCell], *, total, plan_total, rate, avg, best, days) -> int:
        """Hai dòng: Dự kiến (trên) · Thực hiện (dưới), như lưới Lộ trình."""
        ws.cell(row=r, column=1, value=label)
        ws.merge_cells(start_row=r, start_column=1, end_row=r + 1, end_column=1)
        ws.cell(row=r, column=1).alignment = left
        ws.cell(row=r, column=1).font = bold
        ws.cell(row=r, column=2, value='Dự kiến')
        ws.cell(row=r + 1, column=2, value='Thực hiện')
        for i, c in enumerate(cells):
            col = first_day_col + i
            plan_cell = ws.cell(row=r, column=col)
            _num(plan_cell, c.plan)
            if c.plan:
                plan_cell.fill = plan_fill
            done_cell = ws.cell(row=r + 1, column=col)
            _num(done_cell, c.qty)
            if c.state:
                done_cell.font = state_font[c.state]
            if not c.is_workday and not c.plan:
                plan_cell.fill = off_fill
            if not c.is_workday and not c.qty:
                done_cell.fill = off_fill
        _num(ws.cell(row=r, column=sum_col), plan_total)
        _num(ws.cell(row=r + 1, column=sum_col), total)
        extras = [(f'{rate}%' if rate is not None else None), avg, best, days]
        for j, v in enumerate(extras, start=1):
            ws.merge_cells(start_row=r, start_column=sum_col + j, end_row=r + 1, end_column=sum_col + j)
            cell = ws.cell(row=r, column=sum_col + j)
            if isinstance(v, Decimal):
                _num(cell, v)
            else:
                cell.value = v or None
                cell.alignment = center
                cell.border = border
        for rr in (r, r + 1):
            for col in range(1, last_col + 1):
                cell = ws.cell(row=rr, column=col)
                if isinstance(cell, MergedCell):
                    continue
                cell.border = border
        return r + 2

    r = head_row + 1
    for row in report.rows:
        r = _write_pair(
            r,
            row.label,
            row.cells,
            total=row.total,
            plan_total=row.plan_total,
            rate=row.plan_rate,
            avg=row.avg_per_day,
            best=row.best_qty,
            days=row.active_days,
        )

    ws.column_dimensions['A'].width = 26
    ws.column_dimensions['B'].width = 10
    for col in range(first_day_col, sum_col):
        ws.column_dimensions[get_column_letter(col)].width = 7.5
    for col in range(sum_col, last_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = 11
    ws.row_dimensions[head_row].height = 30
    ws.freeze_panes = ws.cell(row=head_row + 1, column=first_day_col)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = (
        f'attachment; filename=San_luong_to_{report.date_from:%Y%m%d}_{report.date_to:%Y%m%d}.xlsx'
    )
    return response
