import sys
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION

User = get_user_model()
HOST = 'portal.justplay.vn'
FAIL = []

def ok(m): print('PASS:', m)
def fail(m, d=''): FAIL.append(m); print('FAIL:', m, d)

def run(username, checks):
    u = User.objects.filter(username=username).first()
    if not u:
        fail(f'user {username} missing')
        return
    c = Client(HTTP_HOST=HOST)
    c.force_login(u)
    print(f'\n--- {username} ---')
    for name, code, kwargs in checks:
        url = reverse(name, kwargs=kwargs) if kwargs else reverse(name)
        r = c.get(url)
        if r.status_code == code:
            ok(f'{name} → {code}')
        else:
            fail(f'{name}', f'got {r.status_code} url={getattr(r,"url","")}')

run('binhthuan', [
    ('reports:today_cn', 200, None),
    ('reports:today_vp', 200, None),
])
run('Thoptt', [
    ('reports:today_vp', 200, None),
    ('reports:today_cn', 200, None),
])
run('tp.tb', [
    ('reports:team_cn', 200, None),
    ('reports:team_vp', 200, None),
])
office = DailyWorkReport.objects.filter(report_profile=REPORT_PROFILE_OFFICE).order_by('-report_date').first()
prod = DailyWorkReport.objects.filter(report_profile=REPORT_PROFILE_PRODUCTION).order_by('-report_date').first()
if office and prod:
    u = User.objects.get(username='tp.tb')
    c = Client(HTTP_HOST=HOST); c.force_login(u)
    for name, pk in [('reports:detail_vp', office.pk), ('reports:detail_cn', prod.pk)]:
        r = c.get(reverse(name, args=[pk]))
        ok(f'{name} {r.status_code}') if r.status_code == 200 else fail(name, str(r.status_code))
    for name, pk in [('reports:detail_export_vp', office.pk), ('reports:detail_export_cn', prod.pk)]:
        r = c.get(reverse(name, args=[pk]))
        ok(f'{name} {r.status_code}') if r.status_code == 200 else fail(name, str(r.status_code))

print('\n', 'OK' if not FAIL else 'FAILED', len(FAIL))
sys.exit(1 if FAIL else 0)
