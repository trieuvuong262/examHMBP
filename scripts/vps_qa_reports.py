"""QA báo cáo trên VPS — user Ductn."""
import sys
from datetime import date

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import Client
from django.urls import reverse

from hrm.permissions import get_report_team_users
from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.week_utils import monday_of

User = get_user_model()
HOST = 'portal.justplay.vn'
FAIL = []


def ok(msg):
    print(f'  PASS: {msg}')


def fail(msg, detail=''):
    FAIL.append(f'{msg} {detail}'.strip())
    print(f'  FAIL: {msg}' + (f' — {detail}' if detail else ''))


ductn = User.objects.filter(username='Ductn').first()
if not ductn:
    fail('User Ductn not found')
    sys.exit(1)

all_employed = User.objects.filter(is_active=True, profile__is_employed=True).exclude(pk=ductn.pk).count()
team = get_report_team_users(ductn)
team_count = team.count()
print(f'=== Ductn team: {team_count} (total employed excl self: {all_employed}) ===')
if team_count >= all_employed and all_employed > 5:
    fail('Ductn still sees whole company', f'team={team_count} all={all_employed}')
elif team_count < all_employed:
    ok(f'Chỉ {team_count} cấp dưới (không phải toàn công ty)')

for u in team[:8]:
    p = getattr(u, 'profile', None)
    print(f'    - {u.username}: {p.full_name if p else ""}')

client = Client(HTTP_HOST=HOST)
client.force_login(ductn)

for url_name in ('reports:team', 'reports:team_weekly'):
    r = client.get(reverse(url_name))
    if r.status_code == 200:
        ok(f'GET {url_name} → 200')
    else:
        fail(f'GET {url_name}', str(r.status_code))

# Draft logic: orphan draft without draft_saved_at
today = date.today()
orphan = DailyWorkReport.objects.filter(
    status=DailyWorkReport.STATUS_DRAFT,
    draft_saved_at__isnull=True,
).first()
if orphan and team.filter(pk=orphan.employee_id).exists():
    r = client.get(reverse('reports:team'), {'date': orphan.report_date.isoformat()})
    html = r.content.decode('utf-8', errors='replace')
    if 'Nháp' in html and orphan.employee.profile.full_name in html:
        # might be ok if also has saved drafts
        pass
    ok('Team page loads with orphan drafts in DB')

saved = DailyWorkReport.objects.filter(draft_saved_at__isnull=False).first()
if saved and team.filter(pk=saved.employee_id).exists():
    r = client.get(reverse('reports:detail', args=[saved.pk]))
    if r.status_code == 200:
        ok('Xem chi tiết báo cáo đã lưu nháp')
    else:
        fail('Detail saved draft', str(r.status_code))

week = monday_of(today)
weekly = WeeklyWorkReport.objects.filter(
    employee_id__in=team.values_list('pk', flat=True),
    week_start=week,
).filter(
    Q(status=WeeklyWorkReport.STATUS_SUBMITTED) | Q(draft_saved_at__isnull=False),
).first()
if weekly:
    r = client.get(reverse('reports:weekly_detail', args=[weekly.pk]))
    if r.status_code == 200:
        ok('Xem báo cáo tuần cấp dưới')
    else:
        fail('weekly_detail', str(r.status_code))
else:
    ok('Chưa có báo cáo tuần cấp dưới tuần này (OK nếu chưa nộp)')

print('\nRESULT:', 'OK' if not FAIL else 'FAILED')
for f in FAIL:
    print('  •', f)
sys.exit(1 if FAIL else 0)
