"""Quy tắc ứng lương — chỉ ngày 18–19, tối đa 3 triệu, 1 lần/tháng/tài khoản."""

from decimal import Decimal

from django.utils import timezone

MAX_SALARY_ADVANCE = Decimal('3000000')
SALARY_ADVANCE_OPEN_DAYS = (18, 19)


def is_salary_advance_open(*, now=None) -> bool:
    now = now or timezone.localtime()
    return now.day in SALARY_ADVANCE_OPEN_DAYS


def current_advance_month(*, now=None):
    now = now or timezone.localtime()
    return now.date().replace(day=1)


def salary_advance_window_label() -> str:
    return 'Ngày 18 và 19 hàng tháng'
