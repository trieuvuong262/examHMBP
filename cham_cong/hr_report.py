"""Báo cáo tháng: đi trễ, vắng, về sớm, tăng ca."""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from cham_cong.leave_calc import leave_day_weight, scheduled_credit
from cham_cong.models import AttendanceDay, Holiday, LeaveRequest, ShiftAssignment
from hrm.models import Profile

_LEAVE_KINDS = (
    LeaveRequest.KIND_ANNUAL,
    LeaveRequest.KIND_PERSONAL,
    LeaveRequest.KIND_UNPAID,
)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def absence_gap(scheduled, leave_weight, clocked) -> Decimal:
    if clocked or scheduled <= 0:
        return Decimal('0')
    gap = Decimal(scheduled) - Decimal(leave_weight or 0)
    return gap if gap > 0 else Decimal('0')


def _join_dates(parts, limit=8):
    if len(parts) <= limit:
        return ', '.join(parts)
    hidden = len(parts) - limit
    return ', '.join(parts[:limit]) + f' +{hidden}'


def _leave_cover(user_ids, start, end, holidays):
    cover = {}
    if not user_ids:
        return cover
    rows = LeaveRequest.objects.filter(
        user_id__in=user_ids,
        status=LeaveRequest.STATUS_APPROVED,
        start_date__lte=end,
        end_date__gte=start,
        kind__in=_LEAVE_KINDS,
    )
    for item in rows:
        day = max(item.start_date, start)
        last = min(item.end_date, end)
        while day <= last:
            key = (item.user_id, day)
            cover[key] = cover.get(key, Decimal('0')) + leave_day_weight(
                day, item.kind, item.portion, holidays,
            )
            day += timedelta(days=1)
    return cover


def monthly_attendance_report(year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    today = timezone.localdate()
    holidays = set(
        Holiday.objects.filter(holiday_date__gte=start, holiday_date__lte=end)
        .values_list('holiday_date', flat=True)
    )
    workdays = []
    cursor = start
    while cursor <= end and cursor <= today:
        if scheduled_credit(cursor, holidays) > 0:
            workdays.append(cursor)
        cursor += timedelta(days=1)

    by_user = {}
    by_division = {}
    by_department = {}
    for item in ShiftAssignment.objects.filter(is_active=True, shift__is_active=True).select_related('shift'):
        if item.user_id and item.user_id not in by_user:
            by_user[item.user_id] = item.shift
        elif item.division_id and item.user_id is None and item.division_id not in by_division:
            by_division[item.division_id] = item.shift
        elif item.department_id and item.division_id is None and item.user_id is None:
            by_department.setdefault(item.department_id, item.shift)

    attendance = {}
    rows_by_user = {}
    for row in AttendanceDay.objects.filter(work_date__gte=start, work_date__lte=end):
        attendance[(row.user_id, row.work_date)] = row
        rows_by_user.setdefault(row.user_id, []).append(row)
    profiles = list(Profile.objects.filter(is_employed=True, user__is_active=True).select_related(
        'user', 'department', 'division',
    ))
    assigned_ids = []
    for profile in profiles:
        shift = (
            by_user.get(profile.user_id)
            or by_division.get(profile.division_id)
            or by_department.get(profile.department_id)
        )
        if shift:
            assigned_ids.append(profile.user_id)
    cover = _leave_cover(assigned_ids, start, end, holidays)

    people = []
    totals = {
        'late': 0, 'late_minutes': 0, 'early': 0, 'early_minutes': 0,
        'absent': 0, 'absent_credit': Decimal('0'), 'ot_minutes': 0, 'headcount': 0,
    }
    for profile in profiles:
        shift = (
            by_user.get(profile.user_id)
            or by_division.get(profile.division_id)
            or by_department.get(profile.department_id)
        )
        if not shift:
            continue
        totals['headcount'] += 1
        late = early = late_minutes = early_minutes = ot_minutes = 0
        absent = 0
        absent_credit = Decimal('0')
        late_parts = []
        early_parts = []
        absent_parts = []
        ot_parts = []
        for row in rows_by_user.get(profile.user_id, []):
            if row.late_minutes:
                late += 1
                late_minutes += row.late_minutes
                late_parts.append(f'{row.work_date:%d/%m} ({row.late_minutes} phút)')
            if row.early_minutes:
                early += 1
                early_minutes += row.early_minutes
                early_parts.append(f'{row.work_date:%d/%m} ({row.early_minutes} phút)')
            if row.ot_minutes:
                ot_minutes += row.ot_minutes
                ot_parts.append(f'{row.work_date:%d/%m} ({row.ot_minutes} phút)')
        for day in workdays:
            row = attendance.get((profile.user_id, day))
            gap = absence_gap(
                scheduled_credit(day, holidays),
                cover.get((profile.user_id, day), 0),
                bool(row and row.clock_in),
            )
            if not gap:
                continue
            absent += 1
            absent_credit += gap
            absent_parts.append(day.strftime('%d/%m') if gap >= 1 else f'{day:%d/%m} ({gap} công)')
        if not (late or early or absent or ot_minutes):
            continue
        totals['late'] += late
        totals['late_minutes'] += late_minutes
        totals['early'] += early
        totals['early_minutes'] += early_minutes
        totals['absent'] += absent
        totals['absent_credit'] += absent_credit
        totals['ot_minutes'] += ot_minutes
        people.append({
            'user_id': profile.user_id,
            'name': profile.full_name or profile.user.username,
            'department': profile.department.name if profile.department_id else '',
            'late': late,
            'late_minutes': late_minutes,
            'early': early,
            'early_minutes': early_minutes,
            'absent': absent,
            'absent_credit': absent_credit,
            'ot_minutes': ot_minutes,
            'late_detail': _join_dates(sorted(late_parts)),
            'early_detail': _join_dates(sorted(early_parts)),
            'absent_detail': _join_dates(sorted(absent_parts)),
            'ot_detail': _join_dates(sorted(ot_parts)),
        })
    people.sort(key=lambda item: (-item['absent'], -item['late_minutes'], -item['ot_minutes'], item['name']))
    return {
        'start': start,
        'end': end,
        'workday_count': len(workdays),
        'totals': totals,
        'people': people[:500],
    }
