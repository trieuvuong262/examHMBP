"""OEE đầy đủ: Sẵn sàng × Hiệu suất × Chất lượng.

Trước P4 màn Dừng chuyền chỉ tính được phần Sẵn sàng (phút ca − phút dừng).
P4 bổ sung hai thành phần còn lại từ dữ liệu đã có:

  * Hiệu suất = phút định mức kiếm được / phút chạy thực.
    Phút định mức lấy từ SMV trong routing (``services.scheduling``): sản lượng
    ghi nhận trên TKSX × phút/cái của công đoạn tương ứng.
  * Chất lượng = SL đạt / (SL đạt + SL lỗi) trên TKSX đã xác nhận.

Sản lượng được quy về tổ theo thứ tự: công đoạn khớp tên trong routing → nhãn
tổ ghi trên TKSX → tổ của lệnh sản xuất. Phần không quy được về tổ nào được
tách riêng để người dùng biết dữ liệu còn thiếu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from san_xuat.hub_models import (
    SxDowntimeEvent,
    SxProductionStat,
    SxWorkCenter,
)
from san_xuat.services.scheduling import routing_map
from san_xuat.services.work_calendar import working_days

_Q1 = Decimal('0.1')
_Q2 = Decimal('0.01')


def _q(value, places: Decimal = _Q2) -> Decimal:
    return Decimal(str(value or 0)).quantize(places)


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal('0')
    return (numerator / denominator * Decimal('100')).quantize(_Q1)


@dataclass
class OeeRow:
    center: SxWorkCenter | None
    label: str = ''
    planned_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    downtime_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    earned_minutes: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_good: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_defect: Decimal = field(default_factory=lambda: Decimal('0'))
    qty_no_smv: Decimal = field(default_factory=lambda: Decimal('0'))

    @property
    def operating_minutes(self) -> Decimal:
        return max(Decimal('0'), self.planned_minutes - self.downtime_minutes)

    @property
    def availability_pct(self) -> Decimal:
        return _pct(self.operating_minutes, self.planned_minutes)

    @property
    def performance_pct(self) -> Decimal:
        return _pct(self.earned_minutes, self.operating_minutes)

    @property
    def qty_total(self) -> Decimal:
        return self.qty_good + self.qty_defect

    @property
    def quality_pct(self) -> Decimal:
        return _pct(self.qty_good, self.qty_total)

    @property
    def oee_pct(self) -> Decimal:
        a = self.availability_pct / Decimal('100')
        p = self.performance_pct / Decimal('100')
        q = self.quality_pct / Decimal('100')
        return (a * p * q * Decimal('100')).quantize(_Q1)

    @property
    def has_output(self) -> bool:
        return self.qty_total > 0

    @property
    def has_smv(self) -> bool:
        return self.earned_minutes > 0


def _center_minutes_per_day(wc: SxWorkCenter, fallback_shift_minutes: Decimal) -> Decimal:
    minutes = wc.available_minutes_per_day
    if minutes and minutes > 0:
        return _q(minutes)
    return fallback_shift_minutes


def build_oee_rows(*, date_from: date, date_to: date) -> dict:
    """Bảng OEE theo tổ trong khoảng ngày (đã trừ ngày nghỉ)."""
    from san_xuat.services.sx_settings import sx_int

    shift_hours = sx_int('oee_shift_hours', 8, min_v=1, max_v=24)
    fallback_shift = Decimal(shift_hours) * Decimal('60')

    days = working_days(date_from, date_to)
    day_count = len(days)
    centers = list(
        SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by('code')
    )

    rows: dict[int, OeeRow] = {}
    for wc in centers:
        rows[wc.pk] = OeeRow(
            center=wc,
            label=wc.name or wc.code,
            planned_minutes=_q(_center_minutes_per_day(wc, fallback_shift) * Decimal(day_count)),
        )
    unassigned = OeeRow(center=None, label='Chưa quy được về tổ')

    # --- Sẵn sàng: phút dừng chuyền ---
    downtime = (
        SxDowntimeEvent.objects.filter(
            is_demo=False,
            event_date__gte=date_from,
            event_date__lte=date_to,
        )
        .values('work_center_id')
        .annotate(total=Sum('minutes'))
    )
    for item in downtime:
        row = rows.get(item['work_center_id'])
        if row is None:
            continue
        row.downtime_minutes += _q(item['total'])

    # --- Hiệu suất + Chất lượng: từ TKSX đã xác nhận ---
    stats = list(
        SxProductionStat.objects.filter(
            is_demo=False,
            status=SxProductionStat.STATUS_CONFIRMED,
            stat_date__gte=date_from,
            stat_date__lte=date_to,
        ).select_related('production_order')
    )
    routings = routing_map([
        getattr(s.production_order, 'product_code', '') or '' for s in stats
    ])

    team_index: dict[str, int] = {}
    for wc in centers:
        for key in ((wc.team_label or '').strip(), (wc.name or '').strip(), (wc.code or '').strip()):
            if key:
                team_index.setdefault(key.casefold(), wc.pk)

    for stat in stats:
        mo = stat.production_order
        product_code = (getattr(mo, 'product_code', '') or '').strip()
        routing = routings.get(product_code)
        stage = (stat.process_name or '').strip().casefold()

        center_id = None
        minutes_per_unit = Decimal('0')
        if routing and routing.steps:
            for step in routing.steps:
                if (step.process_name or '').strip().casefold() == stage and stage:
                    center_id = step.work_center_id
                    minutes_per_unit = step.minutes_per_unit
                    break

        if center_id is None or center_id not in rows:
            label = (stat.team_label or getattr(mo, 'team_label', '') or '').strip()
            center_id = team_index.get(label.casefold()) if label else None
            if center_id is not None and minutes_per_unit <= 0 and routing and routing.has_time_data:
                # Không khớp tên công đoạn: coi như tổ làm trọn mã hàng
                minutes_per_unit = routing.total_smv

        row = rows.get(center_id) if center_id is not None else None
        if row is None:
            row = unassigned

        good = _q(stat.qty_good)
        defect = _q(stat.qty_defect)
        row.qty_good += good
        row.qty_defect += defect
        qty = good + defect
        if minutes_per_unit > 0:
            row.earned_minutes += _q(qty * minutes_per_unit)
        else:
            row.qty_no_smv += qty

    ordered = [rows[wc.pk] for wc in centers]
    if unassigned.qty_total > 0:
        ordered.append(unassigned)

    total = OeeRow(center=None, label='Toàn nhà máy')
    for row in ordered:
        if row.center is None:
            continue
        total.planned_minutes += row.planned_minutes
        total.downtime_minutes += row.downtime_minutes
        total.earned_minutes += row.earned_minutes
        total.qty_good += row.qty_good
        total.qty_defect += row.qty_defect
        total.qty_no_smv += row.qty_no_smv

    return {
        'rows': ordered,
        'total': total,
        'days': day_count,
        'date_from': date_from,
        'date_to': date_to,
        'shift_hours': shift_hours,
        'centers_without_smv': [r.label for r in ordered if r.has_output and not r.has_smv],
    }
