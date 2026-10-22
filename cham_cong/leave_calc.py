"""Tính ngày phép. Không đọc database."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

KIND_ANNUAL = 'annual'
KIND_UNPAID = 'unpaid'
KIND_PERSONAL = 'personal'
KIND_LATE = 'late'
KIND_EARLY = 'early'
DAY_KINDS = frozenset({KIND_ANNUAL, KIND_UNPAID, KIND_PERSONAL})

PORTION_FULL = 'full'
PORTION_MORNING = 'morning'
PORTION_AFTERNOON = 'afternoon'

_CENT = Decimal('0.01')


def quantize_days(value) -> Decimal:
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def scheduled_credit(day, holidays) -> Decimal:
    if day.weekday() == 6 or day in holidays:
        return Decimal('0')
    if day.weekday() == 5:
        return Decimal('0.5')
    return Decimal('1')


def leave_day_weight(day, kind, portion, holidays) -> Decimal:
    if kind not in DAY_KINDS:
        return Decimal('0')
    base = scheduled_credit(day, holidays)
    if base == 0:
        return Decimal('0')
    if portion == PORTION_FULL or base <= Decimal('0.5'):
        return base
    return Decimal('0.5')


def request_day_count(start, end, kind, portion, holidays) -> Decimal:
    total = Decimal('0')
    day = start
    while day <= end:
        total += leave_day_weight(day, kind, portion, holidays)
        day += timedelta(days=1)
    return total


def days_in_year(start, end, year, kind, portion, holidays) -> Decimal:
    window_start = max(start, date(year, 1, 1))
    window_end = min(end, date(year, 12, 31))
    if window_start > window_end:
        return Decimal('0')
    return request_day_count(window_start, window_end, kind, portion, holidays)


def accrual_months(join_date, year, as_of) -> int:
    year_start = date(year, 1, 1)
    as_of = min(as_of, date(year, 12, 31))
    if as_of < year_start:
        return 0
    start = year_start if join_date is None else max(join_date, year_start)
    if start > as_of:
        return 0
    return (as_of.year - start.year) * 12 + as_of.month - start.month + 1


def entitlement_days(annual_leave_days, months) -> Decimal:
    if months <= 0:
        return Decimal('0.00')
    return quantize_days(Decimal(annual_leave_days) * Decimal(months) / Decimal(12))


def carry_days(entitlement, used, cap) -> Decimal:
    cap = Decimal(cap or 0)
    if cap <= 0:
        return Decimal('0.00')
    leftover = Decimal(entitlement) - Decimal(used)
    if leftover <= 0:
        return Decimal('0.00')
    return quantize_days(min(leftover, cap))


def day_portions_conflict(day, portion_a, portion_b, holidays) -> bool:
    credit = scheduled_credit(day, holidays)
    if credit == 0:
        return False
    if credit <= Decimal('0.5'):
        return True
    if portion_a == PORTION_FULL or portion_b == PORTION_FULL:
        return True
    return portion_a == portion_b


def ranges_conflict(left, right, holidays) -> bool:
    if left['start'] > right['end'] or right['start'] > left['end']:
        return False
    left_day = left['kind'] in DAY_KINDS
    right_day = right['kind'] in DAY_KINDS
    if left_day and right_day:
        day = max(left['start'], right['start'])
        last = min(left['end'], right['end'])
        while day <= last:
            if day_portions_conflict(day, left['portion'], right['portion'], holidays):
                return True
            day += timedelta(days=1)
        return False
    return left['kind'] == right['kind'] and left['kind'] in (KIND_LATE, KIND_EARLY)
