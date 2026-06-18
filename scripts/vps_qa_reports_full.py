"""QA tổng hợp CN/VP trên VPS — dùng tp.tb (trưởng BP) và Ductn."""
import sys
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_REPORTS
from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION

User = get_user_model()
HOST = 'portal.justplay.vn'
FAIL = []


def ok(msg):
    print(f'  PASS: {msg}')


def fail(msg, detail=''):
    FAIL.append(f'{msg} {detail}'.strip())
    print(f'  FAIL: {msg}' + (f' — {detail}' if detail else ''))


def get_client(user):
    c = Client(HTTP_HOST=HOST)
    c.force_login(user)
    return c


def check(user, label):
    print(f'\n========== {label} ({user.username}) ==========')
    menus = ['daily_cn', 'daily_cn_detail', 'daily_vp', 'daily_vp_detail', 'weekly']
    for k in menus:
        print(f'  menu {k}:', 'YES' if user_can_access_menu(user, MODULE_REPORTS, k) else 'no')

    c = get_client(user)
    tests = [
        ('reports:today_cn', 200),
        ('reports:today_vp', 200),
        ('reports:team_cn', 200),
        ('reports:team_vp', 200),
        ('reports:my_cn', 200),
        ('reports:my_vp', 200),
    ]
    for name, code in tests:
        r = c.get(reverse(name))
        if r.status_code == code:
            ok(f'GET {name} → {code}')
        else:
            fail(f'GET {name}', f'expected {code}, got {r.status_code} url={getattr(r, "url", "")}')

    for legacy, expect in [
        ('reports:today', '/reports/'),
        ('reports:team', '/reports/'),
        ('reports:copy_yesterday', '/reports/'),
    ]:
        r = c.get(reverse(legacy))
        if r.status_code in (301, 302) and expect in (r.url or ''):
            ok(f'legacy {legacy} → {r.url}')
        else:
            fail(f'legacy {legacy}', f'{r.status_code} {getattr(r, "url", "")}')

    prod = DailyWorkReport.objects.filter(report_profile=REPORT_PROFILE_PRODUCTION).order_by('-report_date').first()
    office = DailyWorkReport.objects.filter(report_profile=REPORT_PROFILE_OFFICE).order_by('-report_date').first()
    if prod:
        for name, pk in [('reports:detail_cn', prod.pk), ('reports:detail', prod.pk)]:
            r = c.get(reverse(name, args=[pk]) if 'detail_cn' in name else reverse('reports:detail', args=[pk]))
            if r.status_code in (200, 301, 302):
                ok(f'{name} pk={pk} → {r.status_code}')
            else:
                fail(name, str(r.status_code))
        r = c.get(reverse('reports:export_cn', args=[prod.pk]))
        if r.status_code == 200:
            ok(f'export_cn pk={prod.pk}')
        else:
            fail('export_cn', str(r.status_code))
    if office:
        r = c.get(reverse('reports:detail_vp', args=[office.pk]))
        if r.status_code == 200:
            ok(f'detail_vp pk={office.pk}')
        else:
            fail('detail_vp', str(r.status_code))
        r = c.get(reverse('reports:export_vp', args=[office.pk]))
        if r.status_code == 200:
            ok(f'export_vp pk={office.pk}')
        else:
            fail('export_vp', str(r.status_code))


leader = User.objects.filter(username='tp.tb').first()
ductn = User.objects.filter(username='Ductn').first()
worker = User.objects.filter(username='nv.tb').first()

if leader:
    check(leader, 'Trưởng BP tp.tb')
if ductn:
    check(ductn, 'TGD Ductn')
if worker:
    print(f'\n========== Worker nv.tb (cấu hình nhóm quyền) ==========')
    c = get_client(worker)
    r = c.get(reverse('reports:today_cn'))
    if r.status_code == 302 and r.url == '/':
        ok('nv.tb blocked from today_cn (menu view=false) — đúng middleware')
    elif r.status_code == 200:
        fail('nv.tb should NOT access today_cn without menu perm')
    else:
        fail('today_cn nv.tb', f'{r.status_code} {getattr(r, "url", "")}')

print('\n========== KẾT QUẢ ==========')
print('OK' if not FAIL else 'FAILED')
for f in FAIL:
    print(' •', f)
sys.exit(1 if FAIL else 0)
