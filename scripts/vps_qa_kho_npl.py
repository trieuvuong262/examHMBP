"""
QA toàn diện module kho_npl trên VPS (dữ liệu thật).
Chạy: docker compose exec -T web python manage.py shell < scripts/vps_qa_kho_npl.py
"""
import sys
import traceback
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import (
    MODULE_KHO_NPL,
    user_can_access_module,
    user_can_create_module,
    user_can_export_module,
    user_can_update_module,
)
from kho_npl.choices import (
    ADJUST_STATUS_APPROVED,
    ADJUST_STATUS_PENDING,
    DOC_STATUS_DRAFT,
    DOC_STATUS_POSTED,
    STOCKTAKE_STATUS_COUNTING,
    STOCKTAKE_STATUS_DRAFT,
)
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockAdjustment,
    StockBalance,
    StockIssue,
    StockLedger,
    StockReceipt,
    Stocktake,
    StocktakeLine,
    Unit,
    WarehouseLocation,
)

User = get_user_model()
PREFIX = '[VPS-QA]'
PASS = []
FAIL = []
WARN = []


def ok(msg):
    PASS.append(msg)
    print(f'  PASS: {msg}')


def fail(msg, detail=''):
    FAIL.append(f'{msg} {detail}'.strip())
    print(f'  FAIL: {msg}' + (f' — {detail}' if detail else ''))


def warn(msg):
    WARN.append(msg)
    print(f'  WARN: {msg}')


def section(title):
    print(f'\n=== {title} ===')


# --- 1. Migrations & master data ---
section('1. Migration & master data')
try:
    from django.db.migrations.executor import MigrationExecutor
    from django.db import connections

    executor = MigrationExecutor(connections['default'])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if plan:
        fail('Còn migration chưa apply', str(len(plan)))
    else:
        ok('Tất cả migration đã apply')

    cat_count = MaterialCategory.objects.filter(is_active=True).count()
    unit_count = Unit.objects.filter(is_active=True).count()
    loc = WarehouseLocation.objects.filter(code='MAIN').first()
    if cat_count >= 1 and unit_count >= 1 and loc:
        ok(f'Master data: {cat_count} nhóm, {unit_count} ĐVT, vị trí MAIN')
    else:
        fail('Thiếu master data seed', f'cat={cat_count} unit={unit_count} MAIN={bool(loc)}')
except Exception as e:
    fail('Migration/master data', str(e))


# --- 2. Quyền user thật ---
section('2. Quyền user thật')
CHECK_USERS = ['admin', 'Ductn', 'Vuonglnt', 'huuchung']
qa_user = None
for uname in CHECK_USERS:
    u = User.objects.filter(username=uname).first()
    if not u:
        warn(f'User {uname} không tồn tại')
        continue
    can_view = user_can_access_module(u, MODULE_KHO_NPL)
    can_create = user_can_create_module(u, MODULE_KHO_NPL)
    can_export = user_can_export_module(u, MODULE_KHO_NPL)
    pg = getattr(getattr(u, 'profile', None), 'permission_group', None)
    pg_name = pg.name if pg else '(none)'
    print(f'  {uname}: view={can_view} create={can_create} export={can_export} group={pg_name}')
    if can_view and can_create and can_export and qa_user is None:
        qa_user = u

if qa_user:
    ok(f'User QA chính: {qa_user.username}')
else:
    # fallback: tạo session với admin hoặc user có view
    for uname in CHECK_USERS:
        u = User.objects.filter(username=uname).first()
        if u and user_can_access_module(u, MODULE_KHO_NPL):
            qa_user = u
            warn(f'Dùng {uname} (thiếu full quyền create/export)')
            break
if not qa_user:
    fail('Không có user nào có quyền view kho_npl')


# --- 3. Smoke HTTP tất cả trang ---
section('3. Smoke HTTP — tất cả trang chính')
if qa_user:
    client = Client(HTTP_HOST='portal.justplay.vn')
    client.force_login(qa_user)
    page_urls = [
        'kho_npl:overview',
        'kho_npl:material_list', 'kho_npl:material_create',
        'kho_npl:receipt_list', 'kho_npl:receipt_create',
        'kho_npl:issue_list', 'kho_npl:issue_create',
        'kho_npl:adjustment_list', 'kho_npl:adjustment_create',
        'kho_npl:stocktake_list', 'kho_npl:stocktake_create',
        'kho_npl:report_hub',
        'kho_npl:report_stock', 'kho_npl:report_alerts', 'kho_npl:report_movement',
        'kho_npl:report_issue_lsx', 'kho_npl:report_stocktake_history', 'kho_npl:report_ledger',
        'kho_npl:settings_hub',
    ]
    for name in page_urls:
        url = reverse(name)
        r = client.get(url)
        if r.status_code == 200:
            ok(f'GET {name} → 200')
        else:
            fail(f'GET {name}', f'status={r.status_code}')

    for section_key in ('nhom', 'dvt', 'vi-tri', 'ncc'):
        url = reverse('kho_npl:settings_list', kwargs={'section': section_key})
        r = client.get(url)
        if r.status_code == 200:
            ok(f'GET settings/{section_key} → 200')
        else:
            fail(f'GET settings/{section_key}', f'status={r.status_code}')

    export_names = [
        'kho_npl:report_stock_export', 'kho_npl:report_alerts_export',
        'kho_npl:report_movement_export', 'kho_npl:report_ledger_export',
    ]
    for name in export_names:
        url = reverse(name)
        r = client.get(url)
        ct = r.get('Content-Type', '')
        if r.status_code == 200 and 'spreadsheetml' in ct:
            ok(f'Export {name} → Excel OK')
        elif r.status_code == 403:
            warn(f'Export {name} → 403 (user thiếu quyền export)')
        else:
            fail(f'Export {name}', f'status={r.status_code} ct={ct[:60]}')

    # User không quyền → redirect
    denied = User.objects.exclude(pk=qa_user.pk).filter(is_active=True).first()
    if denied and not user_can_access_module(denied, MODULE_KHO_NPL):
        c2 = Client(HTTP_HOST='portal.justplay.vn')
        c2.force_login(denied)
        r = c2.get(reverse('kho_npl:overview'))
        if r.status_code in (302, 403):
            ok(f'User {denied.username} không quyền → chặn ({r.status_code})')
        else:
            warn(f'User {denied.username} không quyền nhưng GET overview → {r.status_code}')


# --- 4. E2E Workflow trên DB thật ---
section('4. E2E Workflow (dữ liệu test, sẽ dọn sau)')
cleanup_ids = {'materials': [], 'receipts': [], 'issues': [], 'adjustments': [], 'stocktakes': []}

try:
    if not qa_user or not user_can_create_module(qa_user, MODULE_KHO_NPL):
        fail('Bỏ qua E2E — user QA không có quyền create')
    else:
        category = MaterialCategory.objects.filter(is_active=True).first()
        unit = Unit.objects.filter(is_active=True).first()
        location = WarehouseLocation.objects.get(code='MAIN')
        ts = timezone.now().strftime('%H%M%S')
        mat_code = f'QA-{ts}'

        # 4a. Tạo NPL
        mat = Material.objects.create(
            code=mat_code,
            name=f'{PREFIX} Vải test {ts}',
            category=category,
            unit=unit,
            min_stock=Decimal('10'),
        )
        cleanup_ids['materials'].append(mat.pk)
        ok(f'Tạo NPL {mat_code}')

        # 4b. Phiếu nhập → ghi sổ
        from kho_npl.services.receipts import post_stock_receipt

        receipt = StockReceipt.objects.create(
            number=f'PN-QA-{ts}',
            receipt_date=timezone.localdate(),
            created_by=qa_user,
            status=DOC_STATUS_DRAFT,
            notes=f'{PREFIX} phiếu nhập test',
        )
        cleanup_ids['receipts'].append(receipt.pk)
        from kho_npl.models import StockReceiptLine
        StockReceiptLine.objects.create(
            receipt=receipt, material=mat, location=location,
            received_qty=Decimal('100'),
        )
        post_stock_receipt(receipt, qa_user)
        receipt.refresh_from_db()
        if receipt.status == DOC_STATUS_POSTED:
            ok('Phiếu nhập: Nháp → Ghi sổ')
        else:
            fail('Phiếu nhập ghi sổ', f'status={receipt.status}')

        bal = StockBalance.objects.get(material=mat, location=location)
        if bal.quantity == Decimal('100'):
            ok('Tồn sau nhập = 100')
        else:
            fail('Tồn sau nhập', f'got {bal.quantity}')

        ledger_in = StockLedger.objects.filter(material=mat, qty_delta=Decimal('100')).exists()
        if ledger_in:
            ok('Sổ kho ghi nhận phiếu nhập')
        else:
            fail('Sổ kho thiếu bút toán nhập')

        # 4c. Phiếu xuất → ghi sổ
        from kho_npl.services.issues import post_stock_issue
        from kho_npl.models import StockIssueLine

        issue = StockIssue.objects.create(
            number=f'PX-QA-{ts}',
            issue_date=timezone.localdate(),
            created_by=qa_user,
            status=DOC_STATUS_DRAFT,
            notes=f'{PREFIX} phiếu xuất test',
        )
        cleanup_ids['issues'].append(issue.pk)
        StockIssueLine.objects.create(
            issue=issue, material=mat, location=location,
            quantity=Decimal('30'),
        )
        post_stock_issue(issue, qa_user)
        issue.refresh_from_db()
        bal.refresh_from_db()
        if issue.status == DOC_STATUS_POSTED and bal.quantity == Decimal('70'):
            ok('Phiếu xuất: Ghi sổ, tồn còn 70')
        else:
            fail('Phiếu xuất', f'status={issue.status} tồn={bal.quantity}')

        # 4d. Xuất vượt tồn → phải lỗi
        bad_issue = StockIssue.objects.create(
            number=f'PX-QA-BAD-{ts}',
            issue_date=timezone.localdate(),
            created_by=qa_user,
            status=DOC_STATUS_DRAFT,
        )
        cleanup_ids['issues'].append(bad_issue.pk)
        StockIssueLine.objects.create(
            issue=bad_issue, material=mat, location=location,
            quantity=Decimal('9999'),
        )
        try:
            post_stock_issue(bad_issue, qa_user)
            fail('Xuất vượt tồn — không bị chặn')
        except Exception:
            ok('Xuất vượt tồn bị chặn đúng')

        # 4e. Điều chỉnh → duyệt
        from kho_npl.services.adjustments import approve_stock_adjustment

        adj = StockAdjustment.objects.create(
            number=f'DC-QA-{ts}',
            adjust_date=timezone.localdate(),
            material=mat,
            location=location,
            system_qty=Decimal('70'),
            actual_qty=Decimal('65'),
            reason=f'{PREFIX} điều chỉnh test',
            proposed_by=qa_user,
            status=ADJUST_STATUS_PENDING,
        )
        cleanup_ids['adjustments'].append(adj.pk)
        approve_stock_adjustment(adj, qa_user)
        adj.refresh_from_db()
        bal.refresh_from_db()
        if adj.status == ADJUST_STATUS_APPROVED and bal.quantity == Decimal('65'):
            ok('Điều chỉnh: Duyệt → tồn = 65')
        else:
            fail('Điều chỉnh', f'status={adj.status} tồn={bal.quantity}')

        # 4f. Kiểm kê → chốt
        from kho_npl.services.stocktakes import close_stocktake

        st = Stocktake.objects.create(
            number=f'KK-QA-{ts}',
            name=f'{PREFIX} Kỳ kiểm kê {ts}',
            stocktake_date=timezone.localdate(),
            created_by=qa_user,
            status=STOCKTAKE_STATUS_COUNTING,
        )
        cleanup_ids['stocktakes'].append(st.pk)
        StocktakeLine.objects.create(
            stocktake=st, material=mat, location=location,
            system_qty=Decimal('65'), actual_qty=Decimal('60'),
        )
        close_stocktake(st, qa_user)
        bal.refresh_from_db()
        if bal.quantity == Decimal('60'):
            ok('Kiểm kê: Chốt kỳ → tồn = 60')
        else:
            fail('Kiểm kê chốt', f'tồn={bal.quantity}')

        # 4g. Sửa phiếu đã ghi sổ → phải chặn (HTTP)
        client = Client(HTTP_HOST='portal.justplay.vn')
        client.force_login(qa_user)
        r = client.get(reverse('kho_npl:receipt_edit', args=[receipt.pk]))
        if r.status_code in (302, 403, 404):
            ok('Không sửa được phiếu nhập đã ghi sổ')
        else:
            warn(f'Phiếu nhập posted edit → {r.status_code}')

        # 4h. Chi tiết trang render
        for url_name, pk in [
            ('kho_npl:material_detail', mat.pk),
            ('kho_npl:receipt_detail', receipt.pk),
            ('kho_npl:issue_detail', issue.pk),
            ('kho_npl:adjustment_detail', adj.pk),
            ('kho_npl:stocktake_detail', st.pk),
        ]:
            r = client.get(reverse(url_name, args=[pk]))
            if r.status_code == 200:
                ok(f'Chi tiết {url_name} → 200')
            else:
                fail(f'Chi tiết {url_name}', f'status={r.status_code}')

except Exception as e:
    fail('E2E workflow exception', str(e))
    traceback.print_exc()


# --- 5. Dọn dữ liệu test ---
section('5. Dọn dữ liệu test [VPS-QA]')
try:
    StockLedger.objects.filter(material_id__in=cleanup_ids['materials']).delete()
    for model, key in [
        (Stocktake, 'stocktakes'),
        (StockAdjustment, 'adjustments'),
        (StockIssue, 'issues'),
        (StockReceipt, 'receipts'),
    ]:
        if cleanup_ids[key]:
            model.objects.filter(pk__in=cleanup_ids[key]).delete()
    StockBalance.objects.filter(material_id__in=cleanup_ids['materials']).delete()
    Material.objects.filter(pk__in=cleanup_ids['materials']).delete()
    # Dọn số phiếu QA còn sót theo prefix
    Material.objects.filter(code__startswith='QA-').delete()
    StockReceipt.objects.filter(number__startswith='PN-QA-').delete()
    StockIssue.objects.filter(number__startswith='PX-QA-').delete()
    StockAdjustment.objects.filter(number__startswith='DC-QA-').delete()
    Stocktake.objects.filter(number__startswith='KK-QA-').delete()
    ok('Đã xóa dữ liệu test QA')
except Exception as e:
    warn(f'Dọn dữ liệu: {e}')


# --- 6. Kiểm tra sidebar / module trong portal ---
section('6. Portal integration')
try:
    if qa_user:
        client = Client(HTTP_HOST='portal.justplay.vn')
        client.force_login(qa_user)
        r = client.get('/kho-npl/')
        if r.status_code in (301, 302):
            ok(f'Hub redirect /kho-npl/ → {r.status_code}')
        else:
            warn(f'/kho-npl/ → {r.status_code}')
        r = client.get(reverse('kho_npl:overview'))
        content = r.content.decode('utf-8', errors='replace')
        checks = [
            ('Tổng quan tồn kho', 'Tiêu đề trang'),
            ('Danh mục nguyên phụ liệu', 'Subnav danh mục'),
            ('Phiếu nhập kho', 'Subnav phiếu nhập'),
            ('jp-tab-pills', 'Subnav UI pills'),
        ]
        for needle, label in checks:
            if needle in content:
                ok(f'Overview HTML: {label}')
            else:
                fail(f'Overview HTML thiếu: {label}')
except Exception as e:
    fail('Portal integration', str(e))


# --- Tổng kết ---
section('TỔNG KẾT')
print(f'  PASS: {len(PASS)}')
print(f'  FAIL: {len(FAIL)}')
print(f'  WARN: {len(WARN)}')
if FAIL:
    print('\n--- FAILURES ---')
    for f in FAIL:
        print(f'  • {f}')
if WARN:
    print('\n--- WARNINGS ---')
    for w in WARN:
        print(f'  • {w}')
print('\nRESULT:', 'OK' if not FAIL else 'FAILED')
sys.exit(1 if FAIL else 0)
