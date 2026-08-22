"""Thời gian kiểm đếm + vận chuyển khi chuyển sang tổ khác.

Mỗi khoảng giữa hai tổ liền kề:
  kiểm đếm (count_minutes) + vận chuyển (transfer_minutes).

Cùng tổ (nhiều công đoạn) không phát sinh trung gian.
Đơn vị: phút / khoảng (theo lô, không nhân SMV). 0 = không phát sinh.
Mặc định nhà máy lấy từ Thời gian trung gian; từng đơn ghi đè bằng nút + trên bảng kế hoạch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING

from san_xuat.services.sx_settings import sx_decimal, sx_int
from san_xuat.services.work_calendar import is_working_day

_Q2 = Decimal('0.01')


def _q(value, places: str = '0.01') -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places))


def default_hop_minutes() -> tuple[Decimal, Decimal]:
    count = max(_q(sx_decimal('plan_count_minutes', '0')), Decimal('0'))
    transfer = max(_q(sx_decimal('plan_transfer_minutes', '0')), Decimal('0'))
    return count, transfer


def resolve_hop_minutes(count, transfer, *, fill_default: bool = False) -> tuple[Decimal, Decimal]:
    """Lấy phút hop. fill_default=True chỉ khi seed hàng mới (cả hai còn 0)."""
    c = max(_q(count), Decimal('0'))
    t = max(_q(transfer), Decimal('0'))
    if fill_default and c == 0 and t == 0:
        return default_hop_minutes()
    return c, t


def hop_buffer_minutes(steps) -> Decimal:
    """Tổng kiểm đếm + vận chuyển các khoảng *khác tổ* (bỏ qua CĐ liền kề cùng tổ)."""
    rows = list(steps or [])
    if len(rows) < 2:
        return Decimal('0')
    total = Decimal('0')
    for i, step in enumerate(rows[:-1]):
        nxt = rows[i + 1]
        if not is_inter_team_hop(step, nxt):
            continue
        c, t = resolve_hop_minutes(
            _step_attr(step, 'count_minutes'),
            _step_attr(step, 'transfer_minutes'),
            fill_default=True,
        )
        total += c + t
    return _q(total)


def minutes_per_shift() -> Decimal:
    hours = sx_int('oee_shift_hours', 8, min_v=1, max_v=24)
    return _q(Decimal(hours) * Decimal('60'))


def add_working_minutes(start: date, minutes: Decimal, *, minutes_per_day: Decimal | None = None) -> date:
    """Ngày làm việc khi cộng thêm ``minutes`` (làm tròn lên ngày nếu > 0)."""
    mins = _q(minutes)
    if mins <= 0:
        return start
    per_day = minutes_per_day if minutes_per_day is not None else minutes_per_shift()
    if per_day <= 0:
        per_day = Decimal('480')
    days_need = int((mins / per_day).to_integral_value(rounding=ROUND_CEILING))
    days_need = max(1, days_need)
    day = start
    remaining = days_need
    # start đã là ngày làm việc (hoặc không) — bước sang ngày kế nếu cần đủ số ngày
    guard = 0
    while remaining > 0 and guard < 800:
        if is_working_day(day):
            remaining -= 1
            if remaining == 0:
                return day
        day += timedelta(days=1)
        guard += 1
    return day


def schedule_span(*, start: date, lead_minutes: Decimal) -> tuple[date, date]:
    """(ngày bắt đầu, ngày kết thúc) theo lịch làm việc + quỹ phút/ca."""
    if lead_minutes <= 0:
        return start, start
    end = add_working_minutes(start, lead_minutes)
    return start, end


@dataclass
class PlanHop:
    step_id: int
    from_name: str
    to_name: str
    count_minutes: Decimal
    transfer_minutes: Decimal

    @property
    def buffer_minutes(self) -> Decimal:
        return _q(self.count_minutes + self.transfer_minutes)

    @property
    def is_set(self) -> bool:
        return self.buffer_minutes > 0


def hops_from_steps(steps) -> list[PlanHop]:
    rows = list(steps or [])
    hops: list[PlanHop] = []
    for i, step in enumerate(rows[:-1]):
        nxt = rows[i + 1]
        if not is_inter_team_hop(step, nxt):
            continue
        c, t = resolve_hop_minutes(
            _step_attr(step, 'count_minutes'),
            _step_attr(step, 'transfer_minutes'),
            fill_default=False,
        )
        hops.append(PlanHop(
            step_id=int(_step_attr(step, 'pk', 0) or 0),
            from_name=(_step_attr(step, 'process_name') or '').strip(),
            to_name=(_step_attr(nxt, 'process_name') or '').strip(),
            count_minutes=c,
            transfer_minutes=t,
        ))
    return hops


def _step_attr(step, name: str, default=None):
    if isinstance(step, dict):
        return step.get(name, default)
    return getattr(step, name, default)


def _step_team_key(step) -> tuple[int | None, str]:
    """(work_center_id, nhãn tổ). Không có tổ → id None, không gộp với bước khác."""
    wc = _step_attr(step, 'work_center')
    wc_id = _step_attr(step, 'work_center_id')
    if wc is not None and getattr(wc, 'pk', None):
        wc_id = int(wc.pk)
    elif wc_id not in (None, '', 0, '0'):
        wc_id = int(wc_id)
    else:
        wc_id = None
    label = (_step_attr(step, 'team_label') or '').strip()
    if not label and wc is not None:
        label = (getattr(wc, 'team_label', None) or getattr(wc, 'name', None) or '').strip()
    return wc_id, label


def is_inter_team_hop(step, nxt) -> bool:
    """True khi bước sau thuộc tổ khác (cùng quy tắc cụm trên bảng kế hoạch)."""
    next_id, _ = _step_team_key(nxt)
    if next_id is None:
        return True
    cur_id, _ = _step_team_key(step)
    return cur_id != next_id


@dataclass
class PlanFlowGroup:
    """Cụm công đoạn liền kề cùng tổ; hop là khoảng sang tổ kế."""

    team_label: str
    work_center_id: int | None
    process_names: list[str] = field(default_factory=list)
    hop_step_id: int = 0
    count_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    transfer_minutes: Decimal = field(default_factory=lambda: Decimal('0'))

    @property
    def buffer_minutes(self) -> Decimal:
        return _q(self.count_minutes + self.transfer_minutes)

    @property
    def hop_is_set(self) -> bool:
        return self.buffer_minutes > 0

    @property
    def form_count_minutes(self) -> Decimal:
        if self.hop_is_set:
            return self.count_minutes
        return default_hop_minutes()[0]

    @property
    def form_transfer_minutes(self) -> Decimal:
        if self.hop_is_set:
            return self.transfer_minutes
        return default_hop_minutes()[1]


def flow_groups_from_steps(steps) -> list[PlanFlowGroup]:
    """Gộp công đoạn liền kề cùng tổ. Bước chưa gán tổ đứng riêng."""
    rows = list(steps or [])
    if not rows:
        return []

    clusters: list[tuple[int | None, str, list]] = []
    for step in rows:
        wc_id, label = _step_team_key(step)
        if wc_id is None:
            clusters.append((None, label, [step]))
            continue
        if clusters and clusters[-1][0] == wc_id:
            clusters[-1][2].append(step)
        else:
            clusters.append((wc_id, label, [step]))

    groups: list[PlanFlowGroup] = []
    for i, (wc_id, label, cluster) in enumerate(clusters):
        names: list[str] = []
        seen: set[str] = set()
        for step in cluster:
            name = (getattr(step, 'process_name', None) or '').strip()
            key = name.casefold()
            if name and key not in seen:
                seen.add(key)
                names.append(name)
        hop_c = hop_t = Decimal('0')
        hop_step_id = 0
        if i < len(clusters) - 1:
            last = cluster[-1]
            hop_step_id = int(getattr(last, 'pk', 0) or 0)
            hop_c, hop_t = resolve_hop_minutes(
                getattr(last, 'count_minutes', 0),
                getattr(last, 'transfer_minutes', 0),
                fill_default=False,
            )
        groups.append(PlanFlowGroup(
            team_label=label,
            work_center_id=wc_id,
            process_names=names,
            hop_step_id=hop_step_id,
            count_minutes=hop_c,
            transfer_minutes=hop_t,
        ))
    return groups
