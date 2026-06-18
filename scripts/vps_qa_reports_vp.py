"""QA VP báo cáo — tìm user VP và kiểm tra workflow."""
import sys
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_REPORTS
from reports.models import DailyWorkReport
from reports.navigation import MENU_DAILY_VP, MENU_DAILY_VP_DETAIL

User = get_user_model()
HOST = 'portal.justplay.vn'
FAIL = []


def ok(msg):
    print(f'  PASS: {msg}')


def fail(msg, detail=''):
    FAIL.append(f'{msg} {detail}'.strip())
    print(f'  FAIL: {msg}' + (f' — {detail}' if detail else ''))


def client_for(user):
    c = Client(HTTP_HOST=HOST)
    c.force_login(user)
    return c


# Users with VP menu
vp_users = []
for u in User.objects.filter(is_active=True).select_related('profile__permission_group', 'profile__department'):
    if user_can_access_menu(u, MODULE_REPORTS, MENU_DAILY_VP) or user_can_access_menu(u, MODULE_REPORTS, MENU_DAILY_VP_DETAIL):
        dept = getattr(getattr(u, 'profile', None), 'department', None)
        vp_users.append((u, dept.name if dept else '?'))

print('Users with VP menu access:', len(vp_users))
for u, dept in vp_users[:15]:
    cn = user_can_access_menu(u, MODULE_REPORTS, 'daily_cn')
    vp = user_can_access_menu(u, MODULE_REPORTS, MENU_DAILY_VP)
    vpd = user_can_access_menu(u, MODULE_REPORTS, MENU_DAILY_VP_DETAIL)
    print(f'  {u.username} ({dept}) cn={cn} vp={vp} vp_detail={vpd}')

# Pick first user with daily_vp for today page
today_user = next((u for u, _ in vp_users if user_can_access_menu(u, MODULE_REPORTS, MENU_DAILY_VP)), None)
detail_user = next((u for u, _ in vp_users if user_can_access_menu(u, MODULE_REPORTS, MENU_DAILY_VP_DETAIL)), None)

if today_user:
    print(f'\n=== VP today ({today_user.username}) ===')
    c = client_for(today_user)
    r = c.get(reverse('reports:today_vp'))
    if r.status_code == 200:
        ok('today_vp 200')
    else:
        fail('today_vp', str(r.status_code))
    r = c.get(reverse('reports:today'))
    if r.status_code in (301, 302) and '/reports/vp/today' in (r.url or ''):
        ok('legacy today → vp')
    elif user_can_access_menu(today_user, MODULE_REPORTS, 'daily_cn'):
        ok('legacy today → cn (user has both)')
    else:
        fail('legacy today redirect', f'{r.status_code} {getattr(r, "url", "")}')
else:
    fail('No user with daily_vp menu')

if detail_user:
    print(f'\n=== VP team ({detail_user.username}) ===')
    c = client_for(detail_user)
    r = c.get(reverse('reports:team_vp'), {'date': date.today().isoformat()})
    if r.status_code == 200:
        ok('team_vp 200')
        html = r.content.decode('utf-8', errors='replace')
        if 'Quản lý' in html or 'Báo cáo' in html:
            ok('team VP page content')
    else:
        fail('team_vp', str(r.status_code))
    r = c.get(reverse('reports:team'))
    if r.status_code in (301, 302):
        url = r.url or ''
        if '/reports/vp/team' in url or '/reports/sx/team' in url:
            ok(f'legacy team → {url}')
        else:
            fail('legacy team', url)

    office = DailyWorkReport.objects.filter(report_type='OFFICE').order_by('-report_date').first()
    if office:
        r = c.get(reverse('reports:detail_vp', args=[office.pk]))
        if r.status_code == 200:
            ok(f'detail_vp pk={office.pk}')
        else:
            fail('detail_vp', str(r.status_code))
        r = c.get(reverse('reports:detail', args=[office.pk]))
        if r.status_code in (301, 302) and f'/reports/vp/{office.pk}' in (r.url or ''):
            ok('legacy detail → vp')
        else:
            fail('legacy detail', f'{r.status_code} {getattr(r, "url", "")}')
    else:
        ok('No OFFICE report in DB (skip detail_vp)')

print('\nRESULT:', 'OK' if not FAIL else 'FAILED')
for f in FAIL:
    print('  •', f)
sys.exit(1 if FAIL else 0)
