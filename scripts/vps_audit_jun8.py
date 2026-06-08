from datetime import datetime, timezone as py_tz

from django.db.models import Count, Q
from audit.models import UserActivityLog

start = datetime(2026, 6, 7, 17, 0, 0, tzinfo=py_tz.utc)  # 8/6 00:00 VN
end = datetime(2026, 6, 8, 17, 0, 0, tzinfo=py_tz.utc)    # 9/6 00:00 VN
qs = UserActivityLog.objects.filter(created_at__gte=start, created_at__lt=end)
print('=== PORTAL AUDIT 8/6 VN ===')
print('By action:', list(qs.values('action').annotate(c=Count('id')).order_by('-c')))
for r in qs.filter(action__in=['login', 'login_failed']).order_by('-created_at'):
    print(r.created_at.astimezone().strftime('%d/%m %H:%M'), r.action, r.username, r.ip_address or '-')
