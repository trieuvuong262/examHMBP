"""Logic lịch nhắc — thứ trong tuần, một lần hoặc lặp hàng tuần."""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone

REPEAT_ONCE = 'once'
REPEAT_WEEKLY = 'weekly'

REPEAT_MODE_CHOICES = (
    (REPEAT_ONCE, 'Một lần'),
    (REPEAT_WEEKLY, 'Hàng tuần'),
)

WEEKDAY_LABELS = {
    1: 'T2',
    2: 'T3',
    3: 'T4',
    4: 'T5',
    5: 'T6',
    6: 'T7',
    7: 'CN',
}

WEEKDAY_CHOICES = [(str(k), v) for k, v in WEEKDAY_LABELS.items()]


def normalize_weekdays(raw) -> list[int]:
    """Chuẩn hóa danh sách thứ ISO (1=T2 … 7=CN)."""
    if not raw:
        return []
    out = []
    for item in raw:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 7 and day not in out:
            out.append(day)
    return sorted(out)


def format_weekdays(days) -> str:
    normalized = normalize_weekdays(days)
    if not normalized:
        return '—'
    return ', '.join(WEEKDAY_LABELS.get(d, str(d)) for d in normalized)


def reminder_schedule_summary(reminder) -> str:
    time_str = reminder.remind_time.strftime('%H:%M')
    if reminder.repeat_mode == REPEAT_ONCE:
        if reminder.once_date:
            return f'Một lần · {time_str} ngày {reminder.once_date:%d/%m/%Y}'
        return f'Một lần · {time_str}'
    return f'Hàng tuần · {time_str} · {format_weekdays(reminder.weekdays)}'


def _same_minute(now_time, remind_time) -> bool:
    return now_time.hour == remind_time.hour and now_time.minute == remind_time.minute


def should_fire_reminder(reminder, now=None) -> bool:
    """True khi đúng phút nhắc (theo giờ địa phương)."""
    now = now or timezone.now()
    local_now = timezone.localtime(now)
    today = local_now.date()
    current_time = local_now.time().replace(second=0, microsecond=0)
    remind_time = reminder.remind_time.replace(second=0, microsecond=0)

    if not _same_minute(current_time, remind_time):
        return False

    if reminder.repeat_mode == REPEAT_ONCE:
        return reminder.once_date == today

    return local_now.isoweekday() in normalize_weekdays(reminder.weekdays)


def validate_once_datetime(once_date, remind_time, *, now=None) -> None:
    """Raise ValueError nếu thời điểm nhắc một lần đã qua."""
    from django.core.exceptions import ValidationError

    now = now or timezone.now()
    local_now = timezone.localtime(now)
    today = local_now.date()
    if once_date < today:
        raise ValidationError('Chọn ngày hôm nay hoặc trong tương lai.')
    if once_date == today:
        current = local_now.time().replace(second=0, microsecond=0)
        target = remind_time.replace(second=0, microsecond=0)
        if target <= current:
            raise ValidationError('Chọn giờ trong tương lai (hôm nay).')


def combine_once_datetime(once_date, remind_time):
    tz = timezone.get_current_timezone()
    naive = datetime.combine(once_date, remind_time)
    return timezone.make_aware(naive, tz)
