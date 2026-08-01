"""Quy tắc ứng lương — khung ngày + mức tối đa cấu hình bởi HR (mặc định 18–19, 3 triệu)."""

from decimal import Decimal

from django.utils import timezone

DEFAULT_MAX_SALARY_ADVANCE = Decimal('3000000')
ABSOLUTE_MAX_SALARY_ADVANCE = Decimal('50000000')
DEFAULT_OPEN_DAY_START = 18
DEFAULT_OPEN_DAY_END = 19

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


def is_salary_advance_open(*, now=None) -> bool:
    now = now or timezone.localtime()
    try:
        settings = get_salary_advance_settings()
    except Exception:
        return now.day in SALARY_ADVANCE_OPEN_DAYS
    if not settings.is_enabled:
        return False
    start = int(settings.open_day_start or DEFAULT_OPEN_DAY_START)
    end = int(settings.open_day_end or DEFAULT_OPEN_DAY_END)
    return start <= now.day <= end


def current_advance_month(*, now=None):
    now = now or timezone.localtime()
    return now.date().replace(day=1)


def salary_advance_window_label() -> str:
    try:
        settings = get_salary_advance_settings()
    except Exception:
        return f'Ngày {DEFAULT_OPEN_DAY_START} và {DEFAULT_OPEN_DAY_END} hàng tháng'
    if not settings.is_enabled:
        return 'Ứng lương đang tắt'
    start = int(settings.open_day_start or DEFAULT_OPEN_DAY_START)
    end = int(settings.open_day_end or DEFAULT_OPEN_DAY_END)
    if start == end:
        return f'Ngày {start} hàng tháng'
    return f'Ngày {start}–{end} hàng tháng'
