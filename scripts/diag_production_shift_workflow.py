"""Chẩn đoán workflow báo cáo SX theo ca trên VPS."""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from datetime import date

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from hrm.permissions import can_view_team_reports, get_report_team_users
from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_PRODUCTION

today = timezone.localdate()
client = Client(HTTP_HOST='portal.justplay.vn')

print('=== Production shift workflow diag ===')
print('today:', today)

leaders = []
for u in User.objects.filter(is_active=True, profile__is_employed=True).select_related('profile'):
    if not can_view_team_reports(u):
        continue
    team = get_report_team_users(u)
    if not team.exists():
        continue
    sx_count = team.filter(profile__department__report_profile=REPORT_PROFILE_PRODUCTION).count()
    leaders.append((u.username, team.count(), sx_count))

print('\nLeaders with team (top 10):')
for row in sorted(leaders, key=lambda x: -x[2])[:10]:
    print(f'  {row[0]}: team={row[1]}, sx={row[2]}')

test_user = None
if len(sys.argv) > 1:
    test_user = User.objects.filter(username__iexact=sys.argv[1]).first()
if not test_user:
    for u in User.objects.filter(is_active=True).select_related('profile'):
        if not can_view_team_reports(u):
            continue
        team = get_report_team_users(u)
        if team.filter(profile__department__report_profile=REPORT_PROFILE_PRODUCTION).exists():
            test_user = u
            break

if not test_user:
    print('\nERROR: no leader found')
    sys.exit(1)

print(f'\nHTTP tests as {test_user.username}:')
client.force_login(test_user)
checks = [
    ('team_all', reverse('reports:team_cn'), {'date': today.isoformat()}),
    ('team_morning', reverse('reports:team_cn'), {
        'date': today.isoformat(),
        'shift': DailyWorkReport.SHIFT_MORNING,
    }),
    ('today_cn', reverse('reports:today_cn'), {'date': today.isoformat()}),
]
ok = True
for label, url, params in checks:
    resp = client.get(url, params)
    html = resp.content.decode('utf-8', errors='replace')
    print(f'  {label}: HTTP {resp.status_code}', end='')
    if resp.status_code != 200:
        print(' FAIL')
        ok = False
        continue
    markers = {
        'shift_stat_grid': 'jp-team-shift-stat-grid' in html,
        'theo_ca': 'Theo ca' in html,
        'shift_morning_url': 'shift=MORNING' in html,
    }
    if label == 'team_morning':
        markers['no_theo_ca'] = 'Theo ca' not in html
        markers['single_shift_mode'] = True
    if label == 'today_cn':
        markers['shift_ui'] = (
            'shift=MORNING' in html
            or 'production_shift' in html
            or 'jp-prod-shift' in html
            or 'Bắt đầu' in html
            or 'Tiếp tục' in html
        )
    print(' OK', markers)
    if label == 'team_all' and not (markers['shift_stat_grid'] and markers['theo_ca']):
        ok = False
    if label == 'team_morning' and not markers.get('no_theo_ca'):
        ok = False

print('\nProduction reports today:')
qs = DailyWorkReport.objects.filter(
    report_date=today,
    report_profile=REPORT_PROFILE_PRODUCTION,
).select_related('employee')
print(f'  count={qs.count()}')
for r in qs[:12]:
    print(
        f'  {r.employee.username} shift={r.shift} '
        f'status={r.status} started={bool(r.shift_started_at)}',
    )

print('\nRESULT:', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
