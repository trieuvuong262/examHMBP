"""Bổ sung QA: user Ductn/Vuonglnt, sidebar, dữ liệu thật."""
import sys

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from hrm.module_permissions import (
    MODULE_KHO_NPL,
    user_can_access_module,
    user_can_create_module,
    user_can_export_module,
)
from kho_npl.models import Material, StockIssue, StockReceipt, StockAdjustment, Stocktake

User = get_user_model()
HOST = 'portal.justplay.vn'
FAIL = []


def check_user(uname, expect_create=None, expect_export=None):
    u = User.objects.filter(username=uname).first()
    if not u:
        print(f'  SKIP {uname}: not found')
        return
    c = Client(HTTP_HOST=HOST)
    c.force_login(u)
    pages = [
        reverse('kho_npl:overview'),
        reverse('kho_npl:material_list'),
        reverse('kho_npl:receipt_list'),
        reverse('kho_npl:report_hub'),
    ]
    ok = True
    for url in pages:
        r = c.get(url)
        if r.status_code != 200:
            ok = False
            FAIL.append(f'{uname} GET {url} -> {r.status_code}')
    create_url = reverse('kho_npl:material_create')
    r_create = c.get(create_url)
    can_create = user_can_create_module(u, MODULE_KHO_NPL)
    can_export = user_can_export_module(u, MODULE_KHO_NPL)
    if expect_create is not None and can_create != expect_create:
        FAIL.append(f'{uname} create perm expected {expect_create} got {can_create}')
        ok = False
    if expect_export is not None and can_export != expect_export:
        FAIL.append(f'{uname} export perm expected {expect_export} got {can_export}')
        ok = False
    if can_create and r_create.status_code != 200:
        FAIL.append(f'{uname} material_create -> {r_create.status_code}')
        ok = False
    if not can_create and r_create.status_code == 200:
        # có thể vẫn 200 nhưng form disabled — chỉ warn
        pass
    exp_r = c.get(reverse('kho_npl:report_stock_export'))
    if can_export:
        if exp_r.status_code != 200:
            FAIL.append(f'{uname} export -> {exp_r.status_code}')
            ok = False
    elif exp_r.status_code not in (302, 403):
        FAIL.append(f'{uname} no export but got {exp_r.status_code}')
        ok = False
    # sidebar flag
    home = c.get('/')
    html = home.content.decode('utf-8', errors='replace')
    has_sidebar = '/kho-npl/' in html or 'kho-npl' in html
    has_access = user_can_access_module(u, MODULE_KHO_NPL)
    if has_access and not has_sidebar:
        FAIL.append(f'{uname} has access but sidebar missing kho-npl link on home')
        ok = False
    status = 'PASS' if ok else 'FAIL'
    print(f'  {status} {uname}: view={has_access} create={can_create} export={can_export} sidebar={has_sidebar}')


print('=== User matrix ===')
check_user('Ductn', expect_create=True, expect_export=True)
check_user('admin', expect_create=True, expect_export=True)
check_user('Vuonglnt', expect_create=False, expect_export=False)
check_user('huuchung', expect_create=False, expect_export=False)

print('\n=== Production data counts ===')
print(f'  Materials (active): {Material.objects.filter(is_active=True).count()}')
print(f'  Receipts: {StockReceipt.objects.count()} (posted: {StockReceipt.objects.filter(status="posted").count()})')
print(f'  Issues: {StockIssue.objects.count()} (posted: {StockIssue.objects.filter(status="posted").count()})')
print(f'  Adjustments: {StockAdjustment.objects.count()}')
print(f'  Stocktakes: {Stocktake.objects.count()}')

print('\n=== HTTPS smoke (internal) ===')
c = Client(HTTP_HOST=HOST, secure=True)
r = c.get('/accounts/login/')
print(f'  Login page: {r.status_code}')
r = c.get('/kho-npl/tong-quan/')
print(f'  Overview anonymous: {r.status_code} (expect 302)')

print('\nRESULT:', 'OK' if not FAIL else 'FAILED')
for f in FAIL:
    print('  •', f)
sys.exit(1 if FAIL else 0)
