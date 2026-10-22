from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

from cham_cong.models import AttendanceDay


def parse_month(text, today):
    raw = (text or '').strip()
    try:
        year, month = (int(part) for part in raw.split('-', 1))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        year, month = today.year, today.month
    return year, month, f'{year:04d}-{month:02d}'


def parse_day(text, today):
    raw = (text or '').strip()
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return today


def week_bounds(day):
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def month_bounds(year, month):
    start = datetime(year, month, 1).date()
    if month == 12:
        end = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        end = datetime(year, month + 1, 1).date() - timedelta(days=1)
    return start, end


def summarize_days(queryset):
    row = queryset.aggregate(
        credit=Coalesce(Sum('work_credit'), Decimal('0')),
        late=Coalesce(Sum('late_minutes'), 0),
        early=Coalesce(Sum('early_minutes'), 0),
        shortage=Coalesce(Sum('shortage_minutes'), 0),
        ot=Coalesce(Sum('ot_minutes'), 0),
        missing=Count('pk', filter=Q(clock_in__isnull=False, clock_out__isnull=True)),
        supplements=Count('pk', filter=Q(source=AttendanceDay.SOURCE_SUPPLEMENT)),
        adjustments=Count('pk', filter=Q(source=AttendanceDay.SOURCE_ADJUSTMENT)),
    )
    row['leave_days'] = Decimal('0')
    return row


def rows_for_users(users, start, end, leave_by_user=None):
    ids = [user.pk for user in users]
    leave_by_user = leave_by_user or {}
    grouped = {
        item['user_id']: item
        for item in AttendanceDay.objects.filter(
            user_id__in=ids, work_date__gte=start, work_date__lte=end,
        ).values('user_id').annotate(
            credit=Coalesce(Sum('work_credit'), Decimal('0')),
            late=Coalesce(Sum('late_minutes'), 0),
            early=Coalesce(Sum('early_minutes'), 0),
            shortage=Coalesce(Sum('shortage_minutes'), 0),
            ot=Coalesce(Sum('ot_minutes'), 0),
            missing=Count('pk', filter=Q(clock_in__isnull=False, clock_out__isnull=True)),
            supplements=Count('pk', filter=Q(source=AttendanceDay.SOURCE_SUPPLEMENT)),
            adjustments=Count('pk', filter=Q(source=AttendanceDay.SOURCE_ADJUSTMENT)),
        )
    }
    empty = {
        'credit': Decimal('0'), 'late': 0, 'early': 0, 'shortage': 0, 'ot': 0,
        'missing': 0, 'supplements': 0, 'adjustments': 0,
        'leave_days': Decimal('0'), 'unpaid_days': Decimal('0'),
    }
    rows = []
    for user in users:
        stats = dict(grouped.get(user.pk, empty))
        extra = leave_by_user.get(user.pk) or empty
        stats['leave_days'] = extra.get('leave_days', Decimal('0'))
        stats['unpaid_days'] = extra.get('unpaid_days', Decimal('0'))
        profile = user.profile if hasattr(user, 'profile') else None
        stats['user'] = user
        stats['name'] = (getattr(profile, 'full_name', '') or user.username)
        stats['department'] = profile.department.name if profile and profile.department_id else ''
        rows.append(stats)
    rows.sort(key=lambda item: item['name'])
    return rows
