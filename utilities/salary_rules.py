"""Quy tắc ứng lương — khung ngày/giờ + mức tối đa cấu hình bởi HR (mặc định 18–19, 3 triệu)."""

from datetime import time
from decimal import Decimal

from django.utils import timezone

DEFAULT_MAX_SALARY_ADVANCE = Decimal('3000000')
ABSOLUTE_MAX_SALARY_ADVANCE = Decimal('50000000')
DEFAULT_OPEN_DAY_START = 18
DEFAULT_OPEN_DAY_END = 19
DEFAULT_OPEN_TIME_START = time(0, 0)
DEFAULT_OPEN_TIME_END = time(23, 59)

# Tương thích import cũ — giá trị mặc định khi chưa có DB settings.
MAX_SALARY_ADVANCE = DEFAULT_MAX_SALARY_ADVANCE
SALARY_ADVANCE_OPEN_DAYS = (DEFAULT_OPEN_DAY_START, DEFAULT_OPEN_DAY_END)


def get_salary_advance_settings():
    from utilities.models import SalaryAdvanceSettings

    return SalaryAdvanceSettings.load()


def get_max_salary_advance() -> Decimal:
    try:
        return Decimal(get_salary_advance_settings().max_amount)
    except Exception:
        return DEFAULT_MAX_SALARY_ADVANCE


def _resolve_window(settings=None):
    """Trả về (day_start, time_start, day_end, time_end)."""
    if settings is None:
        start_day, end_day = DEFAULT_OPEN_DAY_START, DEFAULT_OPEN_DAY_END
        start_time, end_time = DEFAULT_OPEN_TIME_START, DEFAULT_OPEN_TIME_END
        return start_day, start_time, end_day, end_time
    start_day = int(settings.open_day_start or DEFAULT_OPEN_DAY_START)
    end_day = int(settings.open_day_end or DEFAULT_OPEN_DAY_END)
    start_time = settings.open_time_start or DEFAULT_OPEN_TIME_START
    end_time = settings.open_time_end or DEFAULT_OPEN_TIME_END
    return start_day, start_time, end_day, end_time


def is_salary_advance_open(*, now=None) -> bool:
    now = now or timezone.localtime()
    try:
        settings = get_salary_advance_settings()
    except Exception:
        return now.day in SALARY_ADVANCE_OPEN_DAYS
    if not settings.is_enabled:
        return False
    start_day, start_time, end_day, end_time = _resolve_window(settings)
    day = now.day
    current_time = now.time().replace(second=0, microsecond=0)
    if day < start_day or day > end_day:
        return False
    if day == start_day and day == end_day:
        return start_time <= current_time <= end_time
    if day == start_day:
        return current_time >= start_time
    if day == end_day:
        return current_time <= end_time
    return True


def current_advance_month(*, now=None):
    now = now or timezone.localtime()
    return now.date().replace(day=1)


def _format_hm(value: time) -> str:
    return value.strftime('%H:%M')


def salary_advance_window_label() -> str:
    try:
        settings = get_salary_advance_settings()
    except Exception:
        return (
            f'Ngày {DEFAULT_OPEN_DAY_START} {_format_hm(DEFAULT_OPEN_TIME_START)}'
            f' – ngày {DEFAULT_OPEN_DAY_END} {_format_hm(DEFAULT_OPEN_TIME_END)} hàng tháng'
        )
    if not settings.is_enabled:
        return 'Ứng lương đang tắt'
    start_day, start_time, end_day, end_time = _resolve_window(settings)
    if start_day == end_day:
        return f'Ngày {start_day} {_format_hm(start_time)}–{_format_hm(end_time)} hàng tháng'
    return (
        f'Ngày {start_day} {_format_hm(start_time)}'
        f' – ngày {end_day} {_format_hm(end_time)} hàng tháng'
    )
