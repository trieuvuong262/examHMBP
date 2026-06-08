"""One-off: audit portal logins on VPS — run via docker compose exec web python scripts/vps_audit_login.py"""
from datetime import datetime

from django.db.models import Count
from django.utils import timezone

from audit.models import UserActivityLog


def main():
    start = timezone.make_aware(datetime(2026, 6, 5, 0, 0, 0))
    end = timezone.make_aware(datetime(2026, 6, 8, 0, 0, 0))
    qs = UserActivityLog.objects.filter(
        created_at__gte=start,
        created_at__lt=end,
        action__in=[UserActivityLog.ACTION_LOGIN, UserActivityLog.ACTION_LOGIN_FAILED],
    )
    print('=== PORTAL LOGIN 5/6-7/6 ===')
    print('Total:', qs.count())
    print('By action:', list(qs.values('action').annotate(c=Count('id')).order_by('-c')))
    print('=== SUCCESS LOGINS ===')
    for r in qs.filter(action=UserActivityLog.ACTION_LOGIN).order_by('created_at'):
        print(
            r.created_at.strftime('%Y-%m-%d %H:%M'),
            r.username,
            r.ip_address,
            r.machine_name or '-',
        )
    print('=== FAILED BY IP (top 15) ===')
    for row in qs.filter(action=UserActivityLog.ACTION_LOGIN_FAILED).values('ip_address').annotate(
        c=Count('id')
    ).order_by('-c')[:15]:
        print(row)
    print('=== FAILED BY USERNAME (top 15) ===')
    for row in qs.filter(action=UserActivityLog.ACTION_LOGIN_FAILED).values('username').annotate(
        c=Count('id')
    ).order_by('-c')[:15]:
        print(row)
    print('=== UNIQUE SUCCESS IPS ===')
    for row in qs.filter(action=UserActivityLog.ACTION_LOGIN).values('ip_address').annotate(
        c=Count('id')
    ).order_by('-c'):
        print(row)


if __name__ == '__main__':
    main()
