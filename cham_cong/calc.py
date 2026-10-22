"""Tính công và xác minh vị trí. Hàm thuần không ghi database để test được."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

from django.utils import timezone


WEEKDAY = 'weekday'
SATURDAY = 'saturday'
SUNDAY = 'sunday'
HOLIDAY = 'holiday'


@dataclass
class Span:
    kind: str
    start: datetime | None = None
    end: datetime | None = None
    break_start: datetime | None = None
    break_end: datetime | None = None
    late_grace: int = 5
    early_grace: int = 5
    full_credit: Decimal = Decimal('1')
    ot_rate: Decimal = Decimal('1.50')
    off_ot_rate: Decimal = Decimal('2')


def local_dt(day, clock_time):
    tz = timezone.get_current_timezone()
    combined = datetime.combine(day, clock_time)
    if timezone.is_naive(combined):
        return timezone.make_aware(combined, tz)
    return combined


def place_time(work_date, clock_time, shift_start, crosses_midnight):
    day = work_date
    if crosses_midnight and clock_time < shift_start:
        day = work_date + timedelta(days=1)
    return local_dt(day, clock_time)


def attendance_work_date(shift, when):
    """Ca qua đêm: trước giờ ra thì ngày công là hôm trước."""
    local = timezone.localtime(when)
    if shift.crosses_midnight and local.time() <= shift.end_time:
        return local.date() - timedelta(days=1)
    return local.date()


def build_span(shift, work_date, *, is_holiday: bool, policy) -> Span:
    if is_holiday:
        return Span(kind=HOLIDAY, off_ot_rate=policy.ot_holiday_rate)
    weekday = work_date.weekday()
    if weekday == 6:
        return Span(kind=SUNDAY, off_ot_rate=policy.ot_sunday_rate)
    if weekday == 5:
        start = local_dt(work_date, shift.saturday_start)
        end = local_dt(work_date, shift.saturday_end)
        return Span(
            kind=SATURDAY,
            start=start,
            end=end,
            late_grace=shift.late_grace_minutes,
            early_grace=shift.early_grace_minutes,
            full_credit=Decimal('0.5'),
            ot_rate=policy.ot_weekday_rate,
        )
    start = local_dt(work_date, shift.start_time)
    end = place_time(work_date, shift.end_time, shift.start_time, shift.crosses_midnight)
    break_start = break_end = None
    if shift.break_start and shift.break_end:
        break_start = place_time(work_date, shift.break_start, shift.start_time, shift.crosses_midnight)
        break_end = place_time(work_date, shift.break_end, shift.start_time, shift.crosses_midnight)
    return Span(
        kind=WEEKDAY,
        start=start,
        end=end,
        break_start=break_start,
        break_end=break_end,
        late_grace=shift.late_grace_minutes,
        early_grace=shift.early_grace_minutes,
        full_credit=Decimal('1'),
        ot_rate=policy.ot_weekday_rate,
    )


def in_reminder_window(span: Span, when, lead_minutes: int) -> bool:
    if span.kind in (SUNDAY, HOLIDAY) or span.start is None:
        return False
    local = timezone.localtime(when)
    window_start = span.start - timedelta(minutes=lead_minutes)
    return window_start <= local < span.start


def _minutes(later, earlier) -> int:
    return int((later - earlier).total_seconds() // 60)


def classify_day(clock_in, clock_out, break_out, break_in, span: Span | None) -> dict:
    result = {
        'late_minutes': 0,
        'early_minutes': 0,
        'shortage_minutes': 0,
        'worked_minutes': 0,
        'ot_minutes': 0,
        'ot_rate': Decimal('0'),
        'work_credit': None,
        'status': 'open',
        'day_kind': span.kind if span else '',
    }
    if not clock_in:
        return result
    if not clock_out:
        result['status'] = 'missing_out'
        return result

    result['status'] = 'complete'
    break_minutes = 0
    if break_out and break_in and break_in > break_out:
        break_minutes = _minutes(break_in, break_out)
    elif (
        span and span.break_start and span.break_end
        and clock_in <= span.break_start and clock_out >= span.break_end
    ):
        break_minutes = _minutes(span.break_end, span.break_start)
    worked = max(0, _minutes(clock_out, clock_in) - break_minutes)
    result['worked_minutes'] = worked

    if span is None or span.kind in (SUNDAY, HOLIDAY) or span.start is None or span.end is None:
        result['ot_minutes'] = worked
        result['ot_rate'] = span.off_ot_rate if span else Decimal('0')
        result['work_credit'] = Decimal('0')
        return result

    late_raw = _minutes(clock_in, span.start)
    if late_raw > span.late_grace:
        result['late_minutes'] = late_raw
    early_raw = _minutes(span.end, clock_out)
    if early_raw > span.early_grace:
        result['early_minutes'] = early_raw
    ot_raw = _minutes(clock_out, span.end)
    if ot_raw > span.early_grace:
        result['ot_minutes'] = ot_raw
        result['ot_rate'] = span.ot_rate

    scheduled_break = 0
    if span.break_start and span.break_end:
        scheduled_break = _minutes(span.break_end, span.break_start)
    scheduled_net = max(0, _minutes(span.end, span.start) - scheduled_break)
    if worked < scheduled_net:
        result['shortage_minutes'] = scheduled_net - worked

    if span.kind == SATURDAY:
        result['work_credit'] = Decimal('0.5')
    elif span.break_end and (clock_out <= span.break_end or clock_in >= span.break_start):
        result['work_credit'] = Decimal('0.5')
    else:
        result['work_credit'] = span.full_credit
    return result


def distance_m(lat1, lon1, lat2, lon2) -> float:
    radius = 6371000
    phi1, phi2 = radians(float(lat1)), radians(float(lat2))
    d_phi = radians(float(lat2) - float(lat1))
    d_lambda = radians(float(lon2) - float(lon1))
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def ip_matches_rule(ip: str, rule: str) -> bool:
    try:
        address = ipaddress.ip_address((ip or '').strip())
        text = (rule or '').strip()
        if '/' in text:
            return address in ipaddress.ip_network(text, strict=False)
        return address == ipaddress.ip_address(text)
    except ValueError:
        return False


def format_minutes(value) -> str:
    minutes = int(value or 0)
    hours, remain = divmod(minutes, 60)
    if hours and remain:
        return f'{hours} giờ {remain} phút'
    if hours:
        return f'{hours} giờ'
    return f'{remain} phút'


def format_credit(value) -> str:
    if value is None:
        return 'Chưa tính'
    number = Decimal(value)
    if number == Decimal('0.5'):
        return '0,5 công'
    if number == Decimal('1') or number == Decimal('1.0'):
        return '1 công'
    if number == 0:
        return '0 công'
    text = format(number.normalize(), 'f').replace('.', ',')
    return f'{text} công'
