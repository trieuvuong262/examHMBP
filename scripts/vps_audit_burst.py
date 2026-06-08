from datetime import datetime, timezone as py_tz

from audit.models import UserActivityLog

start = datetime(2026, 6, 5, 8, 20, 0, tzinfo=py_tz.utc)
end = datetime(2026, 6, 5, 8, 30, 0, tzinfo=py_tz.utc)
qs = UserActivityLog.objects.filter(
    created_at__gte=start,
    created_at__lt=end,
    action=UserActivityLog.ACTION_LOGIN,
).order_by('created_at')
print('burst count', qs.count())
for r in qs[:3]:
    print('---', r.username, r.ip_address, repr(r.created_at))
    print('path', r.path, 'ua', (r.user_agent or '')[:100])
    print('extra', r.extra)
