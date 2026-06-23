"""Chẩn đoán ductn xem báo cáo MKT hôm nay."""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from hrm.menu_permissions import user_can_access_menu
from hrm.models import Department, ProfileConcurrentPosition
from hrm.module_permissions import MODULE_REPORTS
from hrm.permissions import (
    can_view_team_reports,
    can_view_user_report,
    get_report_team_users,
)
from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_OFFICE
from reports.team_utils import meaningful_daily_reports_qs
from reports.week_utils import monday_of

today = timezone.localdate()
ductn = User.objects.filter(username__iexact='ductn').first()
mkt = Department.objects.filter(name__icontains='MARKETING').first()

print('=== DIAG ductn / MKT reports ===')
print('today:', today)
print('ductn:', ductn.username if ductn else 'NOT FOUND')
print('mkt:', f'{mkt.name} (id={mkt.pk})' if mkt else 'NOT FOUND')

if not ductn:
    sys.exit(1)

team = get_report_team_users(ductn)
print('team_count:', team.count())
print('can_view_team_reports:', can_view_team_reports(ductn))
print('menu daily_vp_detail:', user_can_access_menu(ductn, MODULE_REPORTS, 'daily_vp_detail'))
print('menu daily_cn_detail:', user_can_access_menu(ductn, MODULE_REPORTS, 'daily_cn_detail'))

mkt_team = team.filter(profile__department=mkt) if mkt else team.none()
print('mkt_in_team:', list(mkt_team.values_list('username', flat=True)))

for period, anchor in (
    ('day', today),
    ('week', monday_of(today)),
    ('month', today.replace(day=1)),
):
    qs = meaningful_daily_reports_qs().filter(
        employee__in=team,
        report_profile=REPORT_PROFILE_OFFICE,
        report_period=period,
        report_date=anchor,
    )
    print(f'office_{period} meaningful:', qs.count())
    for r in qs[:8]:
        print(f'  - {r.employee.username} status={r.status} can_view={can_view_user_report(ductn, r)}')

print('\n=== All office reports today (any period) ===')
for r in DailyWorkReport.objects.filter(
    report_date=today,
    report_profile=REPORT_PROFILE_OFFICE,
).select_related('employee', 'employee__profile'):
    dept = r.employee.profile.department if hasattr(r.employee, 'profile') else None
    in_team = team.filter(pk=r.employee_id).exists()
    print(
        f'  {r.employee.username} dept={dept.name if dept else None} '
        f'period={r.report_period} status={r.status} in_team={in_team} '
        f'can_view={can_view_user_report(ductn, r)}',
    )

if mkt:
    slots = ProfileConcurrentPosition.objects.filter(
        profile=ductn.profile,
        department=mkt,
        is_active=True,
    ).prefetch_related('subordinates')
    print('\n=== ductn MKT concurrent slots ===')
    for cp in slots:
        subs = list(cp.subordinates.filter(is_active=True).values_list('username', flat=True))
        print(f'  slot id={cp.pk} role={cp.role} subs={subs}')

client = Client(HTTP_HOST='portal.justplay.vn')
client.force_login(ductn)
for url_name, params in (
    ('reports:team_vp', {'period': 'day', 'date': today.isoformat()}),
    ('reports:team_vp', {'period': 'week', 'date': monday_of(today).isoformat()}),
    ('reports:team_cn', {'date': today.isoformat()}),
):
    resp = client.get(reverse(url_name), params)
    print(f'\nGET {url_name} {params} -> {resp.status_code}')
    if resp.status_code == 200:
        html = resp.content.decode('utf-8', errors='replace')
        for u in mkt_team[:6]:
            name = u.profile.full_name or u.username
            print(f'  contains {u.username}: {u.username in html}')
            print(f'  contains {name}: {name in html}')
