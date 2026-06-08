from datetime import datetime, timezone as py_tz

from django.db.models import Count, Q
from audit.models import UserActivityLog

today = datetime(2026, 6, 8, tzinfo=py_tz.utc)
start = today.replace(hour=0, minute=0, second=0)
end = today.replace(hour=23, minute=59, second=59)
qs = UserActivityLog.objects.filter(created_at__gte=start, created_at__lte=end)
print('=== AUDIT TODAY 8/6 ===')
print('By action:', list(qs.values('action').annotate(c=Count('id')).order_by('-c')[:12]))
logins = qs.filter(action__in=['login', 'login_failed'])
print('=== LOGIN/FAILED TODAY ===')
for r in logins.order_by('-created_at')[:20]:
    print(r.created_at.astimezone().strftime('%H:%M'), r.action, r.username, r.ip_address or '-')
