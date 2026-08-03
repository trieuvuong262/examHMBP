"""Xếp lịch sản xuất theo SMV và năng lực từng tổ (finite capacity scheduling).

Khác biệt với cách chia đều của P1:
  * Mỗi sản phẩm có bộ công đoạn (routing/BOM), mỗi công đoạn thuộc một tổ và
    tốn ``std_time_minutes`` phút cho một cái.
  * Mỗi tổ có quỹ phút hữu ích mỗi ngày = số người × phút/ca × hiệu suất.
  * Sản lượng mỗi ngày bị chặn bởi tổ chật nhất *trong routing của chính sản phẩm đó*,
    không phải bottleneck toàn nhà máy.

Nhờ vậy lịch trình phản ánh đúng tải thực của từng tổ theo từng ngày.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal

from django.db import transaction

from san_xuat.hub_models import (
    SxDetailPlan,
    SxDetailPlanLine,
    SxOverallPlan,
    SxProductionOrder,
    SxWorkCenter,
)
from san_xuat.models import ProductTechDoc
from san_xuat.services.bom import get_active_bom
from san_xuat.services.planning import PlanningError
from san_xuat.services.work_calendar import working_days

_Q2 = Decimal('0.01')


def _q(value, places: str = '0.01') -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places))


# ---------------------------------------------------------------------------
# Định mức thời gian theo sản phẩm
# ---------------------------------------------------------------------------

@dataclass
class RoutingStep:
    """Một công đoạn trong routing của mã SP, kèm tổ và phút/cái."""

    sequence: int
    process_name: str
    work_center: SxWorkCenter | None
    minutes_per_unit: Decimal

    @property
    def work_center_id(self) -> int | None:
        return self.work_center.pk if self.work_center else None

    @property
    def team_label(self) -> str:
        wc = self.work_center
        if not wc:
            return ''
        return (wc.team_label or wc.name or '').strip()


@dataclass
class ProductRouting:
    product_code: str
    steps: list[RoutingStep] = field(default_factory=list)
    source: str = ''  # bom | routing | none

    @property
    def total_smv(self) -> Decimal:
        return _q(sum((s.minutes_per_unit for s in self.steps), Decimal('0')), '0.0001')

    @property
    def has_time_data(self) -> bool:
        return bool(self.steps) and self.total_smv > 0

    def minutes_by_center(self) -> dict[int, Decimal]:
        """Phút/cái cộng dồn theo từng tổ (một tổ có thể làm nhiều công đoạn)."""
        out: dict[int, Decimal] = {}
        for step in self.steps:
            cid = step.work_center_id
            if cid is None:
                continue
            out[cid] = out.get(cid, Decimal('0')) + step.minutes_per_unit
        return out


def product_routing(product_code: str) -> ProductRouting:
    """Lấy công đoạn + phút/cái của mã SP.

    Ưu tiên BOM đang áp dụng (``ProcessStep`` đã được IE đổ SMV vào
    ``std_time_minutes``); nếu BOM chưa có thời gian thì đọc trực tiếp routing IE.
    """
    code = (product_code or '').strip()
    result = ProductRouting(product_code=code)
    if not code:
        return result

    doc = (
        ProductTechDoc.objects.filter(product_code__iexact=code, is_active=True).first()
        or ProductTechDoc.objects.filter(product_code__iexact=code).first()
    )
    if not doc:
        return result

    bom = get_active_bom(doc)
    if bom:
        steps = list(
            bom.process_steps.select_related('work_center').order_by('sequence', 'id')
        )
        rows = [
            RoutingStep(
                sequence=s.sequence or (i + 1) * 10,
                process_name=s.process_name or '',
                work_center=s.work_center,
                minutes_per_unit=_q(s.std_time_minutes, '0.0001'),
            )
            for i, s in enumerate(steps)
        ]
        if any(r.minutes_per_unit > 0 for r in rows):
            result.steps = [r for r in rows if r.minutes_per_unit > 0]
            result.source = 'bom'
            return result

    routing = getattr(bom, 'routing', None) if bom else None
    if routing is None:
        from san_xuat.ie_models import SxRouting

        routing = (
            SxRouting.objects.filter(style_code__iexact=code, is_active=True)
            .order_by('-routing_rev')
            .first()
        )
    if routing is not None:
        from san_xuat.services.capacity_from_hrm import map_ie_center_to_hr

        rows = []
        for line in routing.lines.select_related('work_center').order_by('seq_no'):
            minutes = _q(line.total_operation_smv, '0.0001')
            if minutes <= 0:
                continue
            rows.append(
                RoutingStep(
                    sequence=line.seq_no or 10,
                    process_name=line.op_name_vi or line.op_code or '',
                    work_center=map_ie_center_to_hr(line.work_center) or line.work_center,
                    minutes_per_unit=minutes,
                )
            )
        if rows:
            result.steps = rows
            result.source = 'routing'
    return result


def routing_map(product_codes: list[str]) -> dict[str, ProductRouting]:
    out: dict[str, ProductRouting] = {}
    for code in {(c or '').strip() for c in (product_codes or []) if (c or '').strip()}:
        out[code] = product_routing(code)
    return out


# ---------------------------------------------------------------------------
# Quỹ phút của các tổ
# ---------------------------------------------------------------------------

def center_minute_budget() -> dict[int, Decimal]:
    """Phút hữu ích / ngày của từng tổ đang hoạt động."""
    out: dict[int, Decimal] = {}
    for wc in SxWorkCenter.objects.filter(is_active=True, is_demo=False):
        minutes = wc.available_minutes_per_day
        if minutes > 0:
            out[wc.pk] = minutes
    return out


def center_lookup() -> dict[int, SxWorkCenter]:
    return {
        wc.pk: wc
        for wc in SxWorkCenter.objects.filter(is_active=True, is_demo=False)
    }


# ---------------------------------------------------------------------------
# Xếp lịch kế hoạch chi tiết theo năng lực
# ---------------------------------------------------------------------------

@dataclass
class ScheduleResult:
    detail_plan: SxDetailPlan
    lines_created: int = 0
    scheduled_qty: Decimal = field(default_factory=lambda: Decimal('0'))
    unscheduled: list[dict] = field(default_factory=list)
    no_routing: list[str] = field(default_factory=list)
    days_used: int = 0

    @property
    def is_complete(self) -> bool:
        return not self.unscheduled


@transaction.atomic
def schedule_detail_plan_by_capacity(
    *,
    overall_plan_id: int,
    code: str | None = None,
    name: str = '',
    user=None,
) -> ScheduleResult:
    """Lập KHCT bằng cách nạp dần sản lượng vào quỹ phút của từng tổ theo ngày.

    Sản phẩm nào chưa khai định mức thời gian sẽ được chia đều như trước
    (ghi vào ``no_routing`` để người lập kế hoạch biết cần bổ sung IE).
    """
    from san_xuat.services.planning import _code

    overall = (
        SxOverallPlan.objects.select_for_update()
        .prefetch_related('lines')
        .get(pk=overall_plan_id)
    )
    if overall.status != SxOverallPlan.STATUS_CONFIRMED:
        raise PlanningError('KHTT phải đã xác nhận trước khi xếp lịch.')

    demand: list[tuple[str, str, Decimal]] = []
    for ln in overall.lines.all():
        qty = ln.qty_planned or ln.qty_required or Decimal('0')
        if qty > 0:
            demand.append((ln.product_code, ln.product_name or '', _q(qty)))
    if not demand:
        raise PlanningError('KHTT không có sản lượng để xếp lịch.')

    plan_days = working_days(overall.date_from, overall.date_to)
    if not plan_days:
        raise PlanningError(
            'Kỳ KHTT không có ngày làm việc nào — kiểm tra lịch làm việc và ngày nghỉ.'
        )

    budget = center_minute_budget()
    if not budget:
        raise PlanningError(
            'Chưa tổ nào khai số nhân sự / phút làm việc — '
            'đồng bộ nhân sự hoặc khai báo tại Năng lực SX trước khi xếp lịch theo định mức.'
        )

    routings = routing_map([code_ for code_, _, _ in demand])
    centers = center_lookup()

    result = ScheduleResult(detail_plan=None)  # type: ignore[arg-type]

    # Tách nhóm có / không có định mức thời gian
    timed: list[tuple[str, str, Decimal, ProductRouting]] = []
    untimed: list[tuple[str, str, Decimal]] = []
    for product_code, product_name, qty in demand:
        routing = routings.get(product_code)
        if routing and routing.has_time_data and routing.minutes_by_center():
            timed.append((product_code, product_name, qty, routing))
        else:
            untimed.append((product_code, product_name, qty))
            result.no_routing.append(product_code)

    # Tái dùng bản nháp cùng KHTT (giữ hành vi như P1)
    detail = (
        SxDetailPlan.objects.filter(
            overall_plan=overall, is_demo=False, status=SxOverallPlan.STATUS_DRAFT,
        )
        .order_by('-id')
        .first()
    )
    if detail:
        detail.lines.all().delete()
        detail.date_from = overall.date_from
        detail.date_to = overall.date_to
        detail.name = (name or '').strip() or detail.name
        detail.save(update_fields=['date_from', 'date_to', 'name'])
    else:
        detail = SxDetailPlan.objects.create(
            code=_code('plan_detail', SxDetailPlan, code=code),
            name=(name or '').strip() or f'KHCT theo định mức từ {overall.code}',
            overall_plan=overall,
            date_from=overall.date_from,
            date_to=overall.date_to,
            status=SxOverallPlan.STATUS_DRAFT,
            is_demo=False,
        )
    result.detail_plan = detail

    remaining = {code_: qty for code_, _, qty, _ in timed}
    names = {code_: nm for code_, nm, _, _ in timed}
    rows: list[SxDetailPlanLine] = []
    days_used = 0

    for day in plan_days:
        if not any(v > 0 for v in remaining.values()):
            break
        free = dict(budget)  # phút còn lại của từng tổ trong ngày
        day_had_output = False

        # Chia lượt theo mã để không mã nào bị bỏ rơi
        for product_code, _product_name, _qty, routing in timed:
            left = remaining.get(product_code, Decimal('0'))
            if left <= 0:
                continue
            per_unit = routing.minutes_by_center()
            usable = [(cid, m) for cid, m in per_unit.items() if cid in free and m > 0]
            if not usable:
                continue
            # Số cái tối đa hôm nay = min theo từng tổ trong routing
            cap = min((free[cid] / m) for cid, m in usable)
            take = min(left, cap).quantize(_Q2, rounding=ROUND_DOWN)
            if take <= 0:
                continue
            for cid, m in usable:
                free[cid] -= take * m
            remaining[product_code] = left - take

            # Tổ chật nhất trong routing của mã này → gán cho dòng KHCT
            bottleneck_cid = max(usable, key=lambda x: x[1])[0]
            wc = centers.get(bottleneck_cid)
            rows.append(
                SxDetailPlanLine(
                    plan=detail,
                    plan_date=day,
                    product_code=product_code,
                    product_name=names.get(product_code, ''),
                    qty=take,
                    work_center=wc,
                    team_label=(wc.team_label or wc.name or '') if wc else '',
                )
            )
            result.scheduled_qty += take
            day_had_output = True

        if day_had_output:
            days_used += 1

    # Mã chưa có định mức: chia đều trên toàn kỳ như P1
    if untimed:
        num_days = len(plan_days)
        for product_code, product_name, qty in untimed:
            daily = (qty / Decimal(num_days)).quantize(_Q2)
            leftover = qty - (daily * num_days)
            for idx, day in enumerate(plan_days):
                q = daily + (leftover if idx == num_days - 1 else Decimal('0'))
                if q <= 0:
                    continue
                rows.append(
                    SxDetailPlanLine(
                        plan=detail,
                        plan_date=day,
                        product_code=product_code,
                        product_name=product_name,
                        qty=_q(q),
                    )
                )
                result.scheduled_qty += _q(q)

    if not rows:
        raise PlanningError(
            'Không xếp được ngày nào — kiểm tra định mức thời gian và quỹ phút của các tổ.'
        )
    SxDetailPlanLine.objects.bulk_create(rows)
    result.lines_created = len(rows)
    result.days_used = days_used

    # Phần không xếp hết trong kỳ
    for product_code, _nm, qty, _r in timed:
        left = remaining.get(product_code, Decimal('0'))
        if left > 0:
            result.unscheduled.append({
                'product_code': product_code,
                'qty_total': qty,
                'qty_left': _q(left),
            })

    notes: list[str] = []
    if result.unscheduled:
        head = result.unscheduled[0]
        notes.append(
            f'Vượt năng lực kỳ: {len(result.unscheduled)} mã không xếp hết '
            f'(vd {head["product_code"]} còn {head["qty_left"]}).'
        )
    if result.no_routing:
        notes.append(
            f'Chưa có định mức thời gian (chia đều): {", ".join(sorted(set(result.no_routing))[:6])}.'
        )
    if notes:
        joined = ' · '.join(notes)
        detail.notes = f'{detail.notes}\n{joined}'.strip() if detail.notes else joined
        detail.save(update_fields=['notes'])

    from san_xuat.services.plan_audit import log_plan_action

    log_plan_action(
        action='reschedule',
        obj=detail,
        summary=(
            f'Xếp lịch theo định mức từ {overall.code}: {result.lines_created} dòng, '
            f'{result.days_used} ngày, SL {result.scheduled_qty}'
            + (f', {len(result.unscheduled)} mã chưa xếp hết' if result.unscheduled else '')
            + '.'
        ),
        changes={
            'overall_plan': overall.code,
            'lines': result.lines_created,
            'days_used': result.days_used,
            'scheduled_qty': str(result.scheduled_qty),
            'unscheduled': [u['product_code'] for u in result.unscheduled],
            'no_routing': sorted(set(result.no_routing)),
        },
        user=user,
    )
    return result


# ---------------------------------------------------------------------------
# Ma trận tải: tổ × ngày
# ---------------------------------------------------------------------------

@dataclass
class CenterDayLoad:
    minutes_needed: Decimal = field(default_factory=lambda: Decimal('0'))
    minutes_available: Decimal = field(default_factory=lambda: Decimal('0'))

    @property
    def load_pct(self) -> Decimal:
        if self.minutes_available <= 0:
            return Decimal('0')
        return (self.minutes_needed / self.minutes_available * Decimal('100')).quantize(_Q2)

    @property
    def is_over(self) -> bool:
        return self.minutes_available > 0 and self.minutes_needed > self.minutes_available

    @property
    def has_data(self) -> bool:
        return self.minutes_needed > 0


def build_load_matrix(
    *,
    date_from: date,
    date_to: date,
    include_mo: bool = True,
    include_plan: bool = True,
) -> dict:
    """Tải phút của từng tổ theo từng ngày làm việc.

    Nguồn tải: dòng KHCT đã xác nhận (kế hoạch) + LSX chưa hoàn thành (thực thi).
    """
    days = working_days(date_from, date_to)
    centers = [
        wc
        for wc in SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by('code')
        if wc.available_minutes_per_day > 0
    ]
    if not days or not centers:
        return {'days': days, 'centers': centers, 'rows': [], 'totals': []}

    day_set = set(days)
    grid: dict[tuple[int, date], CenterDayLoad] = {}
    for wc in centers:
        for day in days:
            grid[(wc.pk, day)] = CenterDayLoad(
                minutes_available=wc.available_minutes_per_day,
            )

    # Thu thập nhu cầu theo (mã SP, ngày, SL)
    demand_rows: list[tuple[str, date, Decimal]] = []
    if include_plan:
        for ln in SxDetailPlanLine.objects.filter(
            plan__status=SxOverallPlan.STATUS_CONFIRMED,
            plan__is_demo=False,
            plan_date__gte=date_from,
            plan_date__lte=date_to,
        ).values_list('product_code', 'plan_date', 'qty'):
            demand_rows.append((ln[0], ln[1], _q(ln[2])))
    if include_mo:
        open_statuses = (
            SxProductionOrder.STATUS_RELEASED,
            SxProductionOrder.STATUS_IN_PROGRESS,
        )
        for mo in SxProductionOrder.objects.filter(
            is_demo=False, status__in=open_statuses,
        ).values_list('product_code', 'planned_start', 'qty', 'qty_done'):
            code, start, qty, done = mo
            if not start or start not in day_set:
                continue
            remaining = _q(qty) - _q(done)
            if remaining > 0:
                demand_rows.append((code, start, remaining))

    routings = routing_map([r[0] for r in demand_rows])
    for product_code, day, qty in demand_rows:
        if day not in day_set:
            continue
        routing = routings.get((product_code or '').strip())
        if not routing or not routing.has_time_data:
            continue
        for cid, minutes in routing.minutes_by_center().items():
            cell = grid.get((cid, day))
            if cell is None:
                continue
            cell.minutes_needed += (qty * minutes).quantize(_Q2)

    rows = []
    for wc in centers:
        cells = [{'day': d, 'load': grid[(wc.pk, d)]} for d in days]
        need = sum((c['load'].minutes_needed for c in cells), Decimal('0'))
        avail = wc.available_minutes_per_day * len(days)
        rows.append({
            'center': wc,
            'cells': cells,
            'minutes_needed': _q(need),
            'minutes_available': _q(avail),
            'load_pct': _q(need / avail * Decimal('100')) if avail > 0 else Decimal('0'),
            'over_days': sum(1 for c in cells if c['load'].is_over),
        })

    totals = []
    for day in days:
        need = sum((grid[(wc.pk, day)].minutes_needed for wc in centers), Decimal('0'))
        avail = sum((wc.available_minutes_per_day for wc in centers), Decimal('0'))
        totals.append({
            'day': day,
            'minutes_needed': _q(need),
            'minutes_available': _q(avail),
            'is_over': avail > 0 and need > avail,
        })

    return {'days': days, 'centers': centers, 'rows': rows, 'totals': totals}


# ---------------------------------------------------------------------------
# Kiểm tra năng lực KHCT theo phút của từng tổ
# ---------------------------------------------------------------------------

@dataclass
class CenterCapacityWarning:
    plan_date: date
    center: SxWorkCenter
    minutes_needed: Decimal
    minutes_available: Decimal

    @property
    def over_by(self) -> Decimal:
        return _q(self.minutes_needed - self.minutes_available)

    @property
    def load_pct(self) -> Decimal:
        if self.minutes_available <= 0:
            return Decimal('0')
        return _q(self.minutes_needed / self.minutes_available * Decimal('100'))


def check_detail_plan_center_capacity(*, plan_id: int) -> list[CenterCapacityWarning]:
    """Cảnh báo quá tải theo từng tổ từng ngày (dựa trên SMV)."""
    plan = SxDetailPlan.objects.prefetch_related('lines').get(pk=plan_id)
    lines = list(plan.lines.all())
    if not lines:
        return []

    budget = center_minute_budget()
    if not budget:
        return []
    centers = center_lookup()
    routings = routing_map([ln.product_code for ln in lines])

    need: dict[tuple[int, date], Decimal] = {}
    for ln in lines:
        routing = routings.get((ln.product_code or '').strip())
        if not routing or not routing.has_time_data:
            continue
        qty = _q(ln.qty)
        for cid, minutes in routing.minutes_by_center().items():
            if cid not in budget:
                continue
            key = (cid, ln.plan_date)
            need[key] = need.get(key, Decimal('0')) + (qty * minutes).quantize(_Q2)

    out: list[CenterCapacityWarning] = []
    for (cid, day), minutes_needed in sorted(need.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        available = budget.get(cid, Decimal('0'))
        if available > 0 and minutes_needed > available:
            wc = centers.get(cid)
            if wc is None:
                continue
            out.append(
                CenterCapacityWarning(
                    plan_date=day,
                    center=wc,
                    minutes_needed=_q(minutes_needed),
                    minutes_available=_q(available),
                )
            )
    return out
