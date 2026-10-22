"""Đọc đơn nghỉ và số dư phép. Ngày công không bị ghi lúc duyệt."""

from datetime import date
from decimal import Decimal

from django.utils import timezone

from cham_cong.leave_calc import (
    KIND_ANNUAL,
    accrual_months,
    carry_days,
    days_in_year,
    entitlement_days,
    ranges_conflict,
    request_day_count,
)
from cham_cong.models import Holiday, LeaveRequest, TimesheetPeriod
from cham_cong.services import cached_policy
from hrm.permissions import get_profile

OPEN_STATUSES = (LeaveRequest.STATUS_PENDING, LeaveRequest.STATUS_APPROVED)


def holiday_dates(start, end):
    if start > end:
        return set()
    return set(Holiday.objects.filter(
        holiday_date__gte=start, holiday_date__lte=end,
    ).values_list('holiday_date', flat=True))


def span_hits_locked(start, end) -> bool:
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        if TimesheetPeriod.objects.filter(year=year, month=month, is_locked=True).exists():
            return True
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return False


def _snapshot(user, year, as_of, annual_days, carry_cap, holidays, requests):
    profile = get_profile(user)
    on_probation = bool(profile and profile.on_probation)
    if on_probation:
        accrued = Decimal('0.00')
        carry = Decimal('0.00')
    else:
        join_date = profile.join_date if profile else None
        months = accrual_months(join_date, year, as_of)
        accrued = entitlement_days(annual_days, months)
        prev_end = date(year - 1, 12, 31)
        prev_months = accrual_months(join_date, year - 1, prev_end)
        prev_entitlement = entitlement_days(annual_days, prev_months)
        prev_used = Decimal('0')
        for item in requests:
            if item.status != LeaveRequest.STATUS_APPROVED:
                continue
            prev_used += days_in_year(
                item.start_date, item.end_date, year - 1, item.kind, item.portion, holidays,
            )
        carry = carry_days(prev_entitlement, prev_used, carry_cap)
    used = Decimal('0')
    pending = Decimal('0')
    for item in requests:
        weight = days_in_year(item.start_date, item.end_date, year, item.kind, item.portion, holidays)
        if item.status == LeaveRequest.STATUS_APPROVED:
            used += weight
        elif item.status == LeaveRequest.STATUS_PENDING:
            pending += weight
    remaining = accrued + carry - used - pending
    return {
        'year': year,
        'on_probation': on_probation,
        'join_date': profile.join_date if profile else None,
        'accrued': accrued,
        'carry': carry,
        'used': used,
        'pending': pending,
        'remaining': remaining,
    }


def annual_balance(user, today=None):
    today = today or timezone.localdate()
    policy = cached_policy()
    requests = _annual_requests(user, today.year - 1, today.year)
    holidays = holiday_dates(date(today.year - 1, 1, 1), date(today.year, 12, 31))
    return _snapshot(
        user, today.year, today,
        policy.annual_leave_days, policy.leave_carry_max_days, holidays, requests,
    )


def annual_shortfall(user, start, end, portion, today=None, exclude_pk=None):
    today = today or timezone.localdate()
    policy = cached_policy()
    requests = _annual_requests(user, start.year - 1, end.year)
    if exclude_pk:
        requests = [item for item in requests if item.pk != exclude_pk]
    holidays = holiday_dates(date(start.year - 1, 1, 1), date(end.year, 12, 31))
    missing = []
    year = start.year
    while year <= end.year:
        as_of = min(date(year, 12, 31), max(today, min(end, date(year, 12, 31))))
        snap = _snapshot(
            user, year, as_of,
            policy.annual_leave_days, policy.leave_carry_max_days, holidays, requests,
        )
        weight = days_in_year(start, end, year, KIND_ANNUAL, portion, holidays)
        if weight > 0 and snap['remaining'] < weight:
            missing.append((year, snap['remaining'], weight))
        year += 1
    return missing


def _annual_requests(user, first_year, last_year):
    return list(LeaveRequest.objects.filter(
        user=user,
        kind=LeaveRequest.KIND_ANNUAL,
        status__in=OPEN_STATUSES,
        start_date__lte=date(last_year, 12, 31),
        end_date__gte=date(first_year, 1, 1),
    ))


def conflicting_request(user, start, end, kind, portion, exclude_pk=None):
    qs = LeaveRequest.objects.filter(
        user=user, status__in=OPEN_STATUSES, start_date__lte=end, end_date__gte=start,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    holidays = holiday_dates(start, end)
    incoming = {'start': start, 'end': end, 'kind': kind, 'portion': portion}
    for item in qs:
        other = {
            'start': item.start_date, 'end': item.end_date,
            'kind': item.kind, 'portion': item.portion,
        }
        if ranges_conflict(incoming, other, holidays):
            return item
    return None


def leave_totals(user_ids, start, end):
    empty = {'leave_days': Decimal('0'), 'unpaid_days': Decimal('0')}
    totals = {pk: dict(empty) for pk in user_ids}
    if not user_ids:
        return totals
    rows = LeaveRequest.objects.filter(
        user_id__in=user_ids,
        status=LeaveRequest.STATUS_APPROVED,
        kind__in=(
            LeaveRequest.KIND_ANNUAL,
            LeaveRequest.KIND_PERSONAL,
            LeaveRequest.KIND_UNPAID,
        ),
        start_date__lte=end,
        end_date__gte=start,
    )
    holidays = holiday_dates(start, end)
    for item in rows:
        day = max(item.start_date, start)
        last = min(item.end_date, end)
        weight = request_day_count(day, last, item.kind, item.portion, holidays)
        bucket = 'unpaid_days' if item.kind == LeaveRequest.KIND_UNPAID else 'leave_days'
        totals[item.user_id][bucket] += weight
    return totals
