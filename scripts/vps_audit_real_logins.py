from datetime import datetime, timezone as py_tz

from django.db.models import Q
from audit.models import UserActivityLog

start = datetime(2026, 6, 5, 0, 0, 0, tzinfo=py_tz.utc)
end = datetime(2026, 6, 8, 0, 0, 0, tzinfo=py_tz.utc)
real = UserActivityLog.objects.filter(
    created_at__gte=start,
    created_at__lt=end,
    action=UserActivityLog.ACTION_LOGIN,
).filter(Q(ip_address__isnull=False) | Q(path='/accounts/login/'))
print('=== REAL WEB LOGINS 5-7/6 ===')
for r in real.order_by('created_at'):
    print(r.created_at.astimezone().strftime('%d/%m %H:%M'), r.username, r.ip_address, r.machine_name or '-')
