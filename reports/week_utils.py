from datetime import date, datetime, timedelta


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def parse_week_start(raw, default=None) -> date:
    if default is None:
        from django.utils import timezone
        default = monday_of(timezone.localdate())
    if not raw:
        return default
    if isinstance(raw, date):
        return monday_of(raw)
    if isinstance(raw, str):
        return monday_of(datetime.strptime(raw, '%Y-%m-%d').date())
    return default


def week_end(week_start: date) -> date:
    return week_start + timedelta(days=6)


def week_label(week_start: date) -> str:
    end = week_end(week_start)
    return f'{week_start.strftime("%d/%m")} – {end.strftime("%d/%m/%Y")}'
