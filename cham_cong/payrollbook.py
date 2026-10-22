"""Ghép công, phép, thưởng và tạm ứng thành phiếu lương."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from cham_cong.hr_report import month_bounds
from cham_cong.leave_calc import leave_day_weight, scheduled_credit
from cham_cong.leavebook import holiday_dates
from cham_cong.models import (
    AttendanceDay,
    LeaveRequest,
    PayAdjustment,
    PayrollPeriod,
    PayrollSlip,
    SalaryProfile,
)
from cham_cong.payroll_calc import build_slip, money
from utilities.models import SalaryAdvanceRequest

PAID_KINDS = (LeaveRequest.KIND_ANNUAL, LeaveRequest.KIND_PERSONAL)
SLIP_FIELDS = (
    'standard_credit', 'work_credit', 'paid_leave_credit', 'unpaid_credit', 'payable_credit',
    'base_salary', 'work_pay', 'meal_allowance', 'transport_allowance', 'phone_allowance',
    'ot_minutes', 'ot_pay', 'bonus', 'penalty', 'unpaid_pay', 'advance', 'net_pay',
)


def _person_name(user):
    profile = user.profile if hasattr(user, 'profile') else None
    name = (getattr(profile, 'full_name', '') or user.username)
    department = profile.department.name if profile and profile.department_id else ''
    join_date = profile.join_date if profile else None
    return name, department, join_date


def _daterange(start, end):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def compute_month(year, month, user_ids=None):
    start, end = month_bounds(year, month)
    profiles = SalaryProfile.objects.select_related('user', 'user__profile', 'user__profile__department')
    if user_ids is not None:
        profiles = profiles.filter(user_id__in=user_ids)
    profiles = [item for item in profiles if _employed_in_month(item, end)]
    ids = [item.user_id for item in profiles]
    if not ids:
        return []

    holidays = holiday_dates(start, end)
    worked = {}
    overtime = {}
    for row in AttendanceDay.objects.filter(user_id__in=ids, work_date__gte=start, work_date__lte=end).only(
        'user_id', 'work_date', 'work_credit', 'ot_minutes', 'ot_rate',
    ):
        worked[(row.user_id, row.work_date)] = Decimal(row.work_credit or 0)
        if row.ot_minutes and row.ot_rate:
            overtime[(row.user_id, row.work_date)] = (row.ot_minutes, row.ot_rate)

    paid = {}
    unpaid = {}
    for item in LeaveRequest.objects.filter(
        user_id__in=ids,
        status=LeaveRequest.STATUS_APPROVED,
        start_date__lte=end,
        end_date__gte=start,
        kind__in=(*PAID_KINDS, LeaveRequest.KIND_UNPAID),
    ):
        bucket = unpaid if item.kind == LeaveRequest.KIND_UNPAID else paid
        day = max(item.start_date, start)
        last = min(item.end_date, end)
        while day <= last:
            bucket[(item.user_id, day)] = bucket.get((item.user_id, day), Decimal('0')) + leave_day_weight(
                day, item.kind, item.portion, holidays,
            )
            day += timedelta(days=1)

    bonus = {}
    penalty = {}
    for row in PayAdjustment.objects.filter(
        user_id__in=ids, year=year, month=month, status=PayAdjustment.STATUS_APPROVED,
    ):
        target = bonus if row.kind == PayAdjustment.KIND_BONUS else penalty
        target[row.user_id] = target.get(row.user_id, Decimal('0')) + row.amount

    advances = {
        row['employee_id']: row['total'] or Decimal('0')
        for row in SalaryAdvanceRequest.objects.filter(
            employee_id__in=ids, request_month=start,
        ).values('employee_id').annotate(total=Sum('amount'))
    }

    rows = []
    for item in profiles:
        name, department, join_date = _person_name(item.user)
        standard = Decimal('0')
        work_credit = Decimal('0')
        paid_credit = Decimal('0')
        unpaid_credit = Decimal('0')
        payable = Decimal('0')
        ot_minutes = 0
        ot_parts = []
        for day in _daterange(start, end):
            if join_date and day < join_date:
                continue
            scheduled = scheduled_credit(day, holidays)
            day_worked = worked.get((item.user_id, day), Decimal('0'))
            day_paid = paid.get((item.user_id, day), Decimal('0'))
            day_unpaid = unpaid.get((item.user_id, day), Decimal('0'))
            standard += scheduled
            work_credit += day_worked
            paid_credit += day_paid
            unpaid_credit += day_unpaid
            payable += min(scheduled, day_worked + day_paid)
            if (item.user_id, day) in overtime:
                minutes, rate = overtime[(item.user_id, day)]
                ot_minutes += minutes
                ot_parts.append((minutes, rate))
        amounts = build_slip(
            base=item.base_salary,
            meal=item.meal_allowance,
            transport=item.transport_allowance,
            phone=item.phone_allowance,
            standard=standard,
            payable=payable,
            unpaid=unpaid_credit,
            ot_parts=ot_parts,
            bonus=bonus.get(item.user_id, 0),
            penalty=penalty.get(item.user_id, 0),
            advance=advances.get(item.user_id, 0),
        )
        rows.append({
            'user': item.user,
            'name': name,
            'department': department,
            'standard_credit': standard,
            'work_credit': work_credit,
            'paid_leave_credit': paid_credit,
            'unpaid_credit': unpaid_credit,
            'payable_credit': payable,
            'base_salary': money(item.base_salary),
            'ot_minutes': ot_minutes,
            **amounts,
        })
    rows.sort(key=lambda row: row['name'])
    return rows


def _employed_in_month(profile, month_end):
    person = profile.user.profile if hasattr(profile.user, 'profile') else None
    if person and person.join_date and person.join_date > month_end:
        return False
    return True


def period_for(year, month):
    return PayrollPeriod.objects.filter(year=year, month=month).first()


def is_closed(year, month) -> bool:
    period = period_for(year, month)
    return bool(period and period.status == PayrollPeriod.STATUS_CLOSED)


def save_calculation(year, month, actor):
    if is_closed(year, month):
        return None, 'Kỳ lương đã chốt.'
    rows = compute_month(year, month)
    period, _created = PayrollPeriod.objects.get_or_create(year=year, month=month)
    PayrollSlip.objects.filter(period=period).delete()
    PayrollSlip.objects.bulk_create([
        PayrollSlip(period=period, user=row['user'], **{key: row[key] for key in SLIP_FIELDS})
        for row in rows
    ])
    period.fund_total = sum((row['net_pay'] for row in rows), Decimal('0'))
    period.calculated_by = actor
    period.calculated_at = timezone.now()
    period.status = PayrollPeriod.STATUS_DRAFT
    period.save()
    return period, None


def stored_rows(period, user_ids):
    slips = PayrollSlip.objects.filter(period=period, user_id__in=user_ids).select_related(
        'user', 'user__profile', 'user__profile__department',
    )
    rows = []
    for slip in slips:
        name, department, _join = _person_name(slip.user)
        row = {key: getattr(slip, key) for key in SLIP_FIELDS}
        row.update(user=slip.user, name=name, department=department)
        rows.append(row)
    rows.sort(key=lambda row: row['name'])
    return rows


def payroll_fund(year, month):
    period = period_for(year, month)
    if not period or period.fund_total is None:
        return {'label': 'Chưa tính', 'total': None, 'closed': False}
    closed = period.status == PayrollPeriod.STATUS_CLOSED
    return {
        'label': 'Đã chốt' if closed else 'Tạm tính',
        'total': period.fund_total,
        'closed': closed,
    }


def fund_report(year, month):
    summary = payroll_fund(year, month)
    if summary['total'] is None:
        return {**summary, 'groups': []}
    period = period_for(year, month)
    grouped = {}
    for slip in period.slips.select_related('user', 'user__profile', 'user__profile__department'):
        name, department, _join = _person_name(slip.user)
        department = department or 'Chưa gán bộ phận'
        allowance = slip.meal_allowance + slip.transport_allowance + slip.phone_allowance
        grouped.setdefault(department, []).append({
            'name': name,
            'work_pay': slip.work_pay,
            'allowance': allowance,
            'ot_pay': slip.ot_pay,
            'bonus': slip.bonus,
            'penalty': slip.penalty,
            'advance': slip.advance,
            'net_pay': slip.net_pay,
        })
    groups = []
    for department, people in grouped.items():
        people.sort(key=lambda item: item['name'])
        groups.append({
            'department': department,
            'people': people,
            'net_pay': sum((item['net_pay'] for item in people), Decimal('0')),
            'ot_pay': sum((item['ot_pay'] for item in people), Decimal('0')),
        })
    groups.sort(key=lambda item: item['department'])
    return {**summary, 'groups': groups}
