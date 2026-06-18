"""Khung giờ báo cáo sản lượng hàng giờ — khớp mẫu Excel SX."""

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional

from django.utils import timezone


@dataclass(frozen=True)
class ProductionHourlySlot:
    index: int
    label: str
    start: time
    end: time


PRODUCTION_HOURLY_SLOTS = (
    ProductionHourlySlot(0, '7h30 - 8h30', time(7, 30), time(8, 30)),
    ProductionHourlySlot(1, '8h30 - 9h30', time(8, 30), time(9, 30)),
    ProductionHourlySlot(2, '9h30 - 10h30', time(9, 30), time(10, 30)),
    ProductionHourlySlot(3, '10h30 - 12h', time(10, 30), time(12, 0)),
    ProductionHourlySlot(4, '13h - 14h', time(13, 0), time(14, 0)),
    ProductionHourlySlot(5, '14h - 15h', time(14, 0), time(15, 0)),
    ProductionHourlySlot(6, '15h - 16h', time(15, 0), time(16, 0)),
    ProductionHourlySlot(7, '16h - 17h', time(16, 0), time(17, 0)),
    ProductionHourlySlot(8, '17h - 18h', time(17, 0), time(18, 0)),
    ProductionHourlySlot(9, '18h - 19h', time(18, 0), time(19, 0)),
    ProductionHourlySlot(10, '19h - 20h', time(19, 0), time(20, 0)),
    ProductionHourlySlot(11, '20h - 21h', time(20, 0), time(21, 0)),
    ProductionHourlySlot(12, '21h - 22h30', time(21, 0), time(22, 30)),
)

SLOT_COUNT = len(PRODUCTION_HOURLY_SLOTS)


def slot_by_index(index: int) -> Optional[ProductionHourlySlot]:
    if 0 <= index < SLOT_COUNT:
        return PRODUCTION_HOURLY_SLOTS[index]
    return None


def _combine(report_date, t: time):
    return timezone.make_aware(datetime.combine(report_date, t))


def current_slot_index(now=None, report_date=None) -> Optional[int]:
    """Slot đang diễn ra; None nếu ngoài giờ làm."""
    now = now or timezone.localtime()
    if report_date and now.date() != report_date:
        if now.date() < report_date:
            return None
        return SLOT_COUNT - 1
    current = now.time()
    for slot in PRODUCTION_HOURLY_SLOTS:
        if slot.start <= current < slot.end:
            return slot.index
    if current < PRODUCTION_HOURLY_SLOTS[0].start:
        return None
    for slot in reversed(PRODUCTION_HOURLY_SLOTS):
        if current >= slot.end:
            return slot.index
    return None


def due_slot_indices(now=None, report_date=None) -> list[int]:
    """Các slot đã qua (hoặc đang diễn ra) — cần nhập nếu còn trống."""
    now = now or timezone.localtime()
    if report_date and now.date() < report_date:
        return []
    current = current_slot_index(now, report_date)
    if current is None:
        if report_date and now.date() > report_date:
            return list(range(SLOT_COUNT))
        return []
    return list(range(current + 1))
