"""QA báo cáo CN/VP trên VPS — phân quyền menu + workflow."""
import sys
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_REPORTS
from hrm.permissions import can_submit_daily_report, can_view_team_reports, get_report_team_users
from reports.models import DailyWorkReport
from reports.navigation import (
    MENU_DAILY_CN,
    MENU_DAILY_CN_DETAIL,
    MENU_DAILY_VP,
    MENU_DAILY_VP_DETAIL,
)

User = get_user_model()
HOST = 'portal.justplay.vn'
FAIL = []


def ok(msg):
    print(f'  PASS: {msg}')


def fail(msg, detail=''):
    FAIL.append(f'{msg} {detail}'.strip())
    print(f'  FAIL: {msg}' + (f' — {detail}' if detail else ''))


def check_menu_perms(user, label):
    print(f'\n=== {label} ({user.username}) ===')
    for key in (MENU_DAILY_CN, MENU_DAILY_CN_DETAIL, MENU_DAILY_VP, MENU_DAILY_VP_DETAIL):
        access = user_can_access_menu(user, MODULE_REPORTS, key)
        print(f'    menu {key}: {"YES" if access else "no"}')
    print(f'    can_submit_daily: {can_submit_daily_report(user)}')
    print(f'    can_view_team: {can_view_team_reports(user)}')


def get_client(user):
    client = Client(HTTP_HOST=HOST)
    client.force_login(user)
    return client


def expect_status(client, url_name, expected, **kwargs):
    r = client.get(reverse(url_name, kwargs=kwargs) if kwargs else reverse(url_name))
    if r.status_code == expected:
        ok(f'GET {url_name} → {expected}')
        return r
    fail(f'GET {url_name}', f'expected {expected}, got {r.status_code}')
    return r


def expect_redirect_to(client, url_name, fragment, **kwargs):
    r = client.get(reverse(url_name, kwargs=kwargs) if kwargs else reverse(url_name))
    if r.status_code in (301, 302) and fragment in (r.url or ''):
        ok(f'GET {url_name} redirects → {fragment}')
        return r
    fail(f'GET {url_name} redirect', f'status={r.status_code} url={getattr(r, "url", "")}')
    return r


# --- Users from conversation / common test accounts ---
worker = User.objects.filter(username='nv.tb').select_related('profile').first()
leader = User.objects.filter(username='tp.tb').select_related('profile').first()
ductn = User.objects.filter(username='Ductn').select_related('profile').first()

if not worker:
    fail('Test worker nv.tb not found')
if not leader:
    fail('Test leader tp.tb not found')

if worker:
    check_menu_perms(worker, 'Worker')
    c = get_client(worker)
    if user_can_access_menu(worker, MODULE_REPORTS, MENU_DAILY_CN):
        expect_status(c, 'reports:today_cn', 200)
    else:
        fail('Worker should have daily_cn menu')
    if user_can_access_menu(worker, MODULE_REPORTS, MENU_DAILY_CN_DETAIL):
        expect_status(c, 'reports:my_cn', 200)
    # Legacy today → cn or vp by permission
    expect_redirect_to(c, 'reports:today', '/reports/sx/today' if user_can_access_menu(worker, MODULE_REPORTS, MENU_DAILY_CN) else '/reports/vp/today')

if leader:
    check_menu_perms(leader, 'Team leader')
    c = get_client(leader)
    if user_can_access_menu(leader, MODULE_REPORTS, MENU_DAILY_CN_DETAIL):
        expect_status(c, 'reports:team_cn', 200)
        html = c.get(reverse('reports:team_cn'), {'date': date.today().isoformat()}).content.decode('utf-8', errors='replace')
        if 'Quản lý báo cáo' in html or 'Báo cáo cấp dưới' in html:
            ok('Team CN page title present')
        else:
            fail('Team CN page missing title')
    expect_redirect_to(c, 'reports:team', '/reports/sx/team' if user_can_access_menu(leader, MODULE_REPORTS, MENU_DAILY_CN_DETAIL) else '/reports/vp/team')

    # Detail CN for subordinate report
    if worker:
        report = DailyWorkReport.objects.filter(employee=worker).order_by('-report_date').first()
        if report and report.is_production_report:
            r = c.get(reverse('reports:detail_cn', args=[report.pk]))
            if r.status_code == 200:
                ok(f'Detail CN pk={report.pk}')
                html = r.content.decode('utf-8', errors='replace')
                if 'Quản l' in html or 'Danh s' in html or 'Lịch s' in html:
                    ok('Detail CN has nav buttons')
            else:
                fail('Detail CN', str(r.status_code))
            expect_redirect_to(c, 'reports:detail', f'/reports/sx/{report.pk}', pk=report.pk)
        else:
            ok('No production report for worker yet (skip detail)')

if ductn:
    check_menu_perms(ductn, 'Manager Ductn')
    c = get_client(ductn)
    team = get_report_team_users(ductn)
    print(f'    team size: {team.count()}')
    if user_can_access_menu(ductn, MODULE_REPORTS, MENU_DAILY_CN_DETAIL):
        expect_status(c, 'reports:team_cn', 200)
    if user_can_access_menu(ductn, MODULE_REPORTS, MENU_DAILY_VP_DETAIL):
        expect_status(c, 'reports:team_vp', 200)

# Submenu registry smoke
from hrm.submenu_registry import MODULE_SUBMENUS, MODULE_REPORTS as MR

labels = {m['key']: m['label'] for m in MODULE_SUBMENUS.get(MR, [])}
for key, label in labels.items():
    if 'daily' in key and 'Quản lý' not in label and 'Báo cáo ngày' not in label and key != 'weekly':
        fail(f'Submenu label unexpected: {key}={label}')
if labels.get('daily_cn_detail', '').startswith('Quản lý'):
    ok('Submenu daily_cn_detail = Quản lý báo cáo (SX)')
else:
    fail('Submenu label', labels.get('daily_cn_detail', 'missing'))

print('\nRESULT:', 'OK' if not FAIL else 'FAILED')
for f in FAIL:
    print('  •', f)
sys.exit(1 if FAIL else 0)
