"""Khung giờ báo cáo sản lượng — theo ca làm (sáng / tăng ca / tối)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from django.utils import timezone

from reports.models import DailyWorkReport


@dataclass(frozen=True)
class ProductionHourlySlot:
    index: int
    label: str
    start: time
    end: time
    start_day_offset: int = 0
    end_day_offset: int = 0


MORNING_SLOTS = (
    ProductionHourlySlot(0, '7h30 - 8h30', time(7, 30), time(8, 30)),
    ProductionHourlySlot(1, '8h30 - 9h30', time(8, 30), time(9, 30)),
    ProductionHourlySlot(2, '9h30 - 10h30', time(9, 30), time(10, 30)),
    ProductionHourlySlot(3, '10h30 - 12h', time(10, 30), time(12, 0)),
    ProductionHourlySlot(4, '13h - 14h', time(13, 0), time(14, 0)),
    ProductionHourlySlot(5, '14h - 15h', time(14, 0), time(15, 0)),
    ProductionHourlySlot(6, '15h - 16h', time(15, 0), time(16, 0)),
    ProductionHourlySlot(7, '16h - 17h', time(16, 0), time(17, 0)),
    ProductionHourlySlot(8, '17h - 18h', time(17, 0), time(18, 0)),
)

OVERTIME_SLOTS = (
    ProductionHourlySlot(0, '18h - 19h', time(18, 0), time(19, 0)),
    ProductionHourlySlot(1, '19h - 20h', time(19, 0), time(20, 0)),
    ProductionHourlySlot(2, '20h - 21h', time(20, 0), time(21, 0)),
    ProductionHourlySlot(3, '21h - 22h', time(21, 0), time(22, 0)),
)

NIGHT_SLOTS = (
    ProductionHourlySlot(0, '18h - 19h', time(18, 0), time(19, 0)),
    ProductionHourlySlot(1, '19h - 20h', time(19, 0), time(20, 0)),
    ProductionHourlySlot(2, '20h - 21h', time(20, 0), time(21, 0)),
    ProductionHourlySlot(3, '21h - 22h', time(21, 0), time(22, 0)),
    ProductionHourlySlot(4, '22h - 23h', time(22, 0), time(23, 0)),
    ProductionHourlySlot(5, '23h - 0h', time(23, 0), time(0, 0), end_day_offset=1),
    ProductionHourlySlot(6, '0h - 1h', time(0, 0), time(1, 0), start_day_offset=1, end_day_offset=1),
    ProductionHourlySlot(7, '1h - 2h', time(1, 0), time(2, 0), start_day_offset=1, end_day_offset=1),
    ProductionHourlySlot(8, '2h - 3h', time(2, 0), time(3, 0), start_day_offset=1, end_day_offset=1),
    ProductionHourlySlot(9, '3h - 4h', time(3, 0), time(4, 0), start_day_offset=1, end_day_offset=1),
    ProductionHourlySlot(10, '4h - 5h', time(4, 0), time(5, 0), start_day_offset=1, end_day_offset=1),
)

SHIFT_SLOTS = {
    DailyWorkReport.SHIFT_MORNING: MORNING_SLOTS,
    DailyWorkReport.SHIFT_OVERTIME: OVERTIME_SLOTS,
    DailyWorkReport.SHIFT_NIGHT: NIGHT_SLOTS,
}

# Tương thích code cũ — mặc định ca sáng
PRODUCTION_HOURLY_SLOTS = MORNING_SLOTS
SLOT_COUNT = len(MORNING_SLOTS)


def normalize_shift(shift: str | None) -> str:
    if shift in SHIFT_SLOTS:
        return shift
    return DailyWorkReport.SHIFT_MORNING


def slots_for_shift(shift: str | None) -> tuple[ProductionHourlySlot, ...]:
    return SHIFT_SLOTS[normalize_shift(shift)]


def slot_count_for_shift(shift: str | None) -> int:
    return len(slots_for_shift(shift))


def slot_by_index(index: int, shift: str | None = None) -> Optional[ProductionHourlySlot]:
    slots = slots_for_shift(shift)
    if 0 <= index < len(slots):
        return slots[index]
    return None


def _slot_start_dt(report_date, slot: ProductionHourlySlot) -> datetime:
    day = report_date + timedelta(days=slot.start_day_offset)
    return timezone.make_aware(datetime.combine(day, slot.start))


def _slot_end_dt(report_date, slot: ProductionHourlySlot) -> datetime:
    day = report_date + timedelta(days=slot.end_day_offset)
    return timezone.make_aware(datetime.combine(day, slot.end))


def _shift_window(report_date, shift: str | None) -> tuple[datetime, datetime]:
    slots = slots_for_shift(shift)
    return _slot_start_dt(report_date, slots[0]), _slot_end_dt(report_date, slots[-1])


def shift_break_intervals(
    report_date,
    shift: str | None,
) -> list[tuple[datetime, datetime]]:
    """Khoảng nghỉ cố định trong ca (vd. nghỉ trưa 12h–13h)."""
    slots = slots_for_shift(shift)
    intervals: list[tuple[datetime, datetime]] = []
    for i in range(len(slots) - 1):
        gap_start = _slot_end_dt(report_date, slots[i])
        gap_end = _slot_start_dt(report_date, slots[i + 1])
        if gap_end > gap_start:
            intervals.append((gap_start, gap_end))
    return intervals


def shift_contains_datetime(
    at: datetime,
    report_date,
    shift: str | None,
) -> bool:
    """Thời điểm có nằm trong khung ca (theo report_date của ca đó)."""
    local = timezone.localtime(at) if timezone.is_aware(at) else timezone.make_aware(at)
    window_start, window_end = _shift_window(report_date, shift)
    return window_start <= local < window_end


def current_slot_index(
    now=None,
    report_date=None,
    shift: str | None = None,
) -> Optional[int]:
    """Slot đang diễn ra trong ca; None nếu ngoài khung ca."""
    now = now or timezone.localtime()
    shift = normalize_shift(shift)
    slots = slots_for_shift(shift)
    if report_date is None:
        report_date = now.date()

    window_start, window_end = _shift_window(report_date, shift)
    if now < window_start or now >= window_end:
        return None

    for slot in slots:
        start_dt = _slot_start_dt(report_date, slot)
        end_dt = _slot_end_dt(report_date, slot)
        if start_dt <= now < end_dt:
            return slot.index

    last = slots[-1]
    if now >= _slot_end_dt(report_date, last):
        return last.index
    return None


def overlap_minutes(
    interval_start: datetime,
    interval_end: datetime,
    slot_start: datetime,
    slot_end: datetime,
) -> Decimal:
    """Số phút giao nhau giữa khoảng thời gian làm việc và khung giờ ca."""
    overlap_start = max(interval_start, slot_start)
    overlap_end = min(interval_end, slot_end)
    if overlap_end <= overlap_start:
        return Decimal('0')
    seconds = (overlap_end - overlap_start).total_seconds()
    return Decimal(str(seconds)) / Decimal('60')


def slots_overlapping_interval(
    report_date,
    shift: str | None,
    interval_start: datetime,
    interval_end: datetime,
) -> list[tuple[int, Decimal]]:
    """Các khung giờ giao với [interval_start, interval_end] và số giờ thực tế mỗi khung."""
    if interval_end <= interval_start:
        return []
    shift = normalize_shift(shift)
    results: list[tuple[int, Decimal]] = []
    for slot in slots_for_shift(shift):
        slot_start = _slot_start_dt(report_date, slot)
        slot_end = _slot_end_dt(report_date, slot)
        minutes = overlap_minutes(interval_start, interval_end, slot_start, slot_end)
        if minutes <= 0:
            continue
        hours = (minutes / Decimal('60')).quantize(Decimal('0.01'))
        results.append((slot.index, hours))
    return results


def due_slot_indices(
    now=None,
    report_date=None,
    shift: str | None = None,
) -> list[int]:
    """Các slot đã qua (hoặc đang diễn ra) — cần nhập nếu còn trống."""
    now = now or timezone.localtime()
    shift = normalize_shift(shift)
    slots = slots_for_shift(shift)
    count = len(slots)

    if report_date is None:
        report_date = now.date()

    window_start, window_end = _shift_window(report_date, shift)

    if now < window_start:
        return []
    if now >= window_end:
        return list(range(count))

    current = current_slot_index(now, report_date, shift)
    if current is None:
        return []
    return list(range(current + 1))
