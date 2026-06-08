from audit.models import UserActivityLog
r = UserActivityLog.objects.filter(username='Ductn', action='login').order_by('-created_at').first()
if r:
    print('created_at repr', repr(r.created_at))
    print('ip', r.ip_address, 'path', r.path)
    print('ua', (r.user_agent or '')[:200])
    print('extra', r.extra)
r2 = UserActivityLog.objects.filter(action='login', created_at__date='2026-06-05').count()
print('logins on date', r2)
