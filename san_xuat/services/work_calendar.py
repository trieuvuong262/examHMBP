"""Lịch làm việc sản xuất — ngày làm việc trong tuần + ngày nghỉ lễ.

Dùng khi phân bổ kế hoạch chi tiết theo ngày: chỉ rải sản lượng vào ngày làm việc.
"""

from __future__ import annotations

from datetime import date, timedelta

DEFAULT_WORKDAYS = '1111110'  # T2..CN — mặc định nghỉ Chủ nhật
_WEEKDAY_LABELS = ('Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật')


def normalize_workdays(raw: str | None) -> str:
    """Chuẩn hoá chuỗi 7 ký tự 0/1 (T2→CN). Trả mặc định nếu dữ liệu sai."""
    text = (raw or '').strip()
    cleaned = ''.join('1' if ch == '1' else '0' for ch in text if ch in '01')
    if len(cleaned) != 7 or '1' not in cleaned:
        return DEFAULT_WORKDAYS
    return cleaned


def workdays_pattern() -> str:
    from san_xuat.services.sx_settings import load_sx_settings

    cfg = load_sx_settings()
    return normalize_workdays(getattr(cfg, 'plan_workdays', DEFAULT_WORKDAYS))


def workdays_labels(pattern: str | None = None) -> list[str]:
    bits = normalize_workdays(pattern) if pattern else workdays_pattern()
    return [label for label, bit in zip(_WEEKDAY_LABELS, bits) if bit == '1']


def holiday_dates(date_from: date, date_to: date) -> set[date]:
    from san_xuat.hub_models import SxHoliday

    return set(
        SxHoliday.objects.filter(
            holiday_date__gte=date_from,
            holiday_date__lte=date_to,
        ).values_list('holiday_date', flat=True)
    )


def is_working_day(day: date, *, pattern: str | None = None, holidays: set[date] | None = None) -> bool:
    bits = normalize_workdays(pattern) if pattern else workdays_pattern()
    if bits[day.weekday()] != '1':
        return False
    if holidays is None:
        holidays = holiday_dates(day, day)
    return day not in holidays


def working_days(date_from: date, date_to: date) -> list[date]:
    """Danh sách ngày làm việc trong khoảng (đã trừ ngày nghỉ tuần + lễ)."""
    if not date_from or not date_to or date_from > date_to:
        return []
    bits = workdays_pattern()
    holidays = holiday_dates(date_from, date_to)
    days: list[date] = []
    day = date_from
    while day <= date_to:
        if bits[day.weekday()] == '1' and day not in holidays:
            days.append(day)
        day += timedelta(days=1)
    return days


def working_day_count(date_from: date, date_to: date) -> int:
    return len(working_days(date_from, date_to))
