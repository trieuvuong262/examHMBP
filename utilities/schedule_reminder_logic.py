"""Logic lịch nhắc — thứ trong tuần, một lần hoặc lặp hàng tuần."""

from __future__ import annotations

from datetime import datetime, timedelta

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

SCHEDULE_PUSH_GRACE_MINUTES = 2


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


def _matches_schedule_day(reminder, today, weekday: int) -> bool:
    if reminder.repeat_mode == REPEAT_ONCE:
        return reminder.once_date == today
    return weekday in normalize_weekdays(reminder.weekdays)


def _time_on_date(day, hour: int, minute: int):
    return datetime.combine(day, datetime.min.time().replace(hour=hour, minute=minute))


def is_reminder_due(reminder, now=None, *, grace_minutes: int = 0) -> bool:
    """True khi đến giờ nhắc (theo giờ VN). grace_minutes: cron bù trễ vài phút."""
    now = now or timezone.now()
    local_now = timezone.localtime(now)
    today = local_now.date()
    weekday = local_now.isoweekday()

    if not _matches_schedule_day(reminder, today, weekday):
        return False

    target = reminder.remind_time.replace(second=0, microsecond=0)
    current = local_now.time().replace(second=0, microsecond=0)

    if current.hour == target.hour and current.minute == target.minute:
        return True

    if grace_minutes <= 0:
        return False

    target_dt = _time_on_date(today, target.hour, target.minute)
    now_dt = _time_on_date(today, current.hour, current.minute)
    if now_dt <= target_dt:
        return False
    return (now_dt - target_dt) <= timedelta(minutes=grace_minutes)


def should_fire_reminder(reminder, now=None) -> bool:
    """Giữ tên cũ — cron dùng grace window như đặt cơm (không lỡ phút)."""
    return is_reminder_due(reminder, now, grace_minutes=SCHEDULE_PUSH_GRACE_MINUTES)


def reminder_fire_key(reminder, now=None) -> str:
    local_now = timezone.localtime(now or timezone.now())
    return (
        f'{reminder.pk}-{local_now.date().isoformat()}-'
        f'{reminder.remind_time.strftime("%H:%M")}'
    )


def validate_once_datetime(once_date, remind_time, *, now=None) -> None:
    """Raise ValidationError nếu thời điểm nhắc một lần đã qua."""
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
