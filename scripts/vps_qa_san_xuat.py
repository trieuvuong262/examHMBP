"""
QA module Sản xuất trên VPS (dữ liệu thật).

Phạm vi: app san_xuat (/san-xuat/) — hub, điều phối, QC, kế hoạch, giá thành KH,
đóng gói, giao việc, truy xuất, in A5, xuất Excel list.

Loại trừ (không gọi / không assert):
  - kho_npl (/kho-npl/) và redirect san_xuat:redirect_npl_stock
  - bán hàng / KiotViet (/kiotviet/) và kho SP nhúng (fg_*, redirect_fg_stock, redirect_orders)
  - post phiếu xuất kho / sync KV

Chạy trên VPS:
  cd /opt/portaljustplay
  bash scripts/vps_qa_san_xuat.sh
  # hoặc:
  docker compose exec -T web python manage.py shell -c \
    "exec(open('scripts/vps_qa_san_xuat.py', encoding='utf-8').read())"
"""
from __future__ import annotations

# Khi chạy qua `manage.py shell -c exec(...)`, tránh sys.exit làm crash shell wrapper.
_STANDALONE = __name__ == '__main__'
import re
import sys
import traceback
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from hrm.module_permissions import (
    MODULE_SAN_XUAT,
    user_can_access_module,
    user_can_create_module,
    user_can_export_module,
    user_can_print_module,
    user_can_update_module,
)
from san_xuat.hub_models import (
    SxMaterialIssueRequest,
    SxPackingRecord,
    SxProductionOrder,
    SxProductionStat,
    SxWorkAssignment,
)
from san_xuat.list_exports import LIST_EXPORT_REGISTRY
from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.dispatch import (
    build_material_issue_request,
    confirm_stat,
    create_mo_from_bom,
    create_production_stat,
    mo_release,
)
from san_xuat.services.phase3 import (
    create_packing_record,
    create_work_assignment,
    trace_production,
)

User = get_user_model()
HOST = 'portal.justplay.vn'
PREFIX = '[VPS-QA-SX]'
NOTE = f'{PREFIX} auto-test'
PASS: list[str] = []
FAIL: list[str] = []
WARN: list[str] = []

ERROR_MARKERS = (
    'NoReverseMatch',
    'TemplateSyntaxError',
    'Exception Type:',
    'Traceback (most recent call last)',
)

# List / hub / form create — chỉ san_xuat, không kho NPL / bán hàng
LIST_AND_HUB_URLS = [
    'san_xuat:hub',
    'san_xuat:overview',
    'san_xuat:products_nvl',
    'san_xuat:plan_stub',
    'san_xuat:plan_overall',
    'san_xuat:plan_overall_create',
    'san_xuat:plan_detail',
    'san_xuat:plan_detail_create',
    'san_xuat:plan_npl',
    'san_xuat:plan_npl_create',
    'san_xuat:npl_purchase_request',
    'san_xuat:npl_purchase_request_create',
    'san_xuat:purchase_order',
    'san_xuat:purchase_order_create',
    'san_xuat:dispatch_stub',
    'san_xuat:run_order_wizard',
    'san_xuat:dispatch_mo',
    'san_xuat:dispatch_mo_create',
    'san_xuat:dispatch_disassembly',
    'san_xuat:dispatch_disassembly_create',
    'san_xuat:dispatch_schedule',
    'san_xuat:dispatch_material_issue_req',
    'san_xuat:dispatch_prod_stats',
    'san_xuat:dispatch_prod_stats_create',
    'san_xuat:dispatch_fg_receipt_req',
    'san_xuat:dispatch_fg_receipt_req_create',
    'san_xuat:dispatch_npl_surplus',
    'san_xuat:dispatch_npl_surplus_create',
    'san_xuat:dispatch_wip_handover',
    'san_xuat:dispatch_wip_handover_create',
    'san_xuat:dispatch_wip_return',
    'san_xuat:dispatch_wip_return_create',
    'san_xuat:dispatch_handover_status',
    'san_xuat:qc_stub',
    'san_xuat:qc_request',
    'san_xuat:qc_request_create',
    'san_xuat:qc_sheet',
    'san_xuat:qc_sheet_create',
    'san_xuat:qc_alerts',
    'san_xuat:qc_criteria',
    'san_xuat:qc_criteria_create',
    'san_xuat:qc_criteria_group',
    'san_xuat:qc_criteria_group_create',
    'san_xuat:qc_sampling',
    'san_xuat:qc_sampling_create',
    'san_xuat:qc_standard_set',
    'san_xuat:qc_standard_set_create',
    'san_xuat:qc_defect',
    'san_xuat:qc_defect_create',
    'san_xuat:qc_defect_group',
    'san_xuat:qc_defect_group_create',
    'san_xuat:redirect_costing',
    'san_xuat:costing_norm',
    'san_xuat:costing_sheet_list',
    'san_xuat:costing_sheet_create',
    'san_xuat:costing_by_order',
    'san_xuat:costing_order_create',
    'san_xuat:costing_cost_types',
    'san_xuat:costing_cost_type_create',
    'san_xuat:actual_cost_list',
    'san_xuat:process_stub',
    'san_xuat:shop_floor',
    'san_xuat:ncr_list',
    'san_xuat:downtime_list',
    'san_xuat:unified_catalog',
    'san_xuat:staging_locations',
    'san_xuat:work_assignment_list',
    'san_xuat:work_assignment_create',
    'san_xuat:traceability',
    'san_xuat:capacity_list',
    'san_xuat:capacity_create',
    'san_xuat:ops_report',
    'san_xuat:piece_rate_report',
    'san_xuat:team_hr_map',
    'san_xuat:packing_list',
    'san_xuat:packing_create',
    'san_xuat:subcontract_list',
    'san_xuat:subcontract_create',
    'san_xuat:doc_list',
    'san_xuat:doc_create',
    'san_xuat:bom_list',
    'san_xuat:general_settings',
]

# Cố ý không smoke các URL này
EXCLUDED_URLS = {
    'san_xuat:redirect_npl_stock',  # → kho_npl
    'san_xuat:redirect_orders',  # → bán hàng / KV
    'san_xuat:redirect_fg_stock',
    'san_xuat:fg_product_lookup',
    'san_xuat:fg_stock_lookup',
    'san_xuat:fg_purchase_lookup',
}

EXPORT_KEYS_SAMPLE = [
    'dispatch_mo',
    'dispatch_prod_stats',
    'doc_list',
    'bom_list',
    'capacity_list',
    'qc_request',
    'packing_list',
    'plan_overall',
]

CHECK_USERS = ['admin', 'Ductn', 'Vuonglnt', 'huuchung']


def ok(msg: str) -> None:
    PASS.append(msg)
    print(f'  PASS: {msg}')


def fail(msg: str, detail: str = '') -> None:
    FAIL.append(f'{msg} {detail}'.strip())
    print(f'  FAIL: {msg}' + (f' — {detail}' if detail else ''))


def warn(msg: str) -> None:
    WARN.append(msg)
    print(f'  WARN: {msg}')


def section(title: str) -> None:
    print(f'\n=== {title} ===')


def _body_ok(resp) -> tuple[bool, str]:
    if resp.status_code != 200:
        return False, f'status={resp.status_code}'
    body = resp.content.decode('utf-8', errors='replace')
    for marker in ERROR_MARKERS:
        if marker in body:
            title = re.search(r'<title>([^<]+)</title>', body)
            return False, f'contains {marker!r}' + (f' — {title.group(1)}' if title else '')
    return True, ''


# --- 1. Migration ---
section('1. Migration san_xuat')
try:
    executor = MigrationExecutor(connections['default'])
    plan = [
        (mig, back)
        for mig, back in executor.migration_plan(executor.loader.graph.leaf_nodes())
        if mig.app_label == 'san_xuat'
    ]
    if plan:
        fail('Còn migration san_xuat chưa apply', str(len(plan)))
    else:
        ok('Migration san_xuat đã apply')
except Exception as e:
    fail('Migration', str(e))


# --- 2. Master / dữ liệu nền ---
section('2. Dữ liệu nền SX')
try:
    docs = ProductTechDoc.objects.count()
    boms = BomVersion.objects.filter(status=BomVersion.STATUS_ACTIVE).count()
    mos = SxProductionOrder.objects.filter(is_demo=False).count()
    print(f'  hồ sơ={docs} BOM active={boms} LSX (non-demo)={mos}')
    if docs >= 1 and boms >= 1:
        ok(f'Có hồ sơ + BOM active ({docs}/{boms})')
    elif docs >= 1:
        warn(f'Có hồ sơ ({docs}) nhưng chưa có BOM active')
    else:
        warn('Chưa có hồ sơ SX — E2E tạo LSX sẽ bỏ qua')
except Exception as e:
    fail('Dữ liệu nền', str(e))


# --- 3. Quyền ---
section('3. Quyền MODULE_SAN_XUAT')
qa_user = None
for uname in CHECK_USERS:
    u = User.objects.filter(username=uname).first()
    if not u:
        warn(f'User {uname} không tồn tại')
        continue
    flags = {
        'view': user_can_access_module(u, MODULE_SAN_XUAT),
        'create': user_can_create_module(u, MODULE_SAN_XUAT),
        'update': user_can_update_module(u, MODULE_SAN_XUAT),
        'export': user_can_export_module(u, MODULE_SAN_XUAT),
        'print': user_can_print_module(u, MODULE_SAN_XUAT),
    }
    print(f'  {uname}: {flags}')
    if flags['view'] and flags['create'] and qa_user is None:
        qa_user = u

if not qa_user:
    for uname in CHECK_USERS:
        u = User.objects.filter(username=uname).first()
        if u and user_can_access_module(u, MODULE_SAN_XUAT):
            qa_user = u
            warn(f'Dùng {uname} (thiếu create đầy đủ)')
            break

if qa_user:
    ok(f'User QA: {qa_user.username}')
else:
    su = User.objects.filter(is_superuser=True, is_active=True).first()
    if su:
        qa_user = su
        warn(f'Fallback superuser: {su.username}')
    else:
        fail('Không có user có quyền xem san_xuat')


# --- 4. Smoke HTTP ---
section('4. Smoke HTTP — trang SX (trừ kho NPL / bán hàng)')
client = None
if qa_user:
    client = Client(HTTP_HOST=HOST)
    client.force_login(qa_user)

    # Đảm bảo không vô tình test URL excluded
    for name in EXCLUDED_URLS:
        print(f'  SKIP excluded: {name}')

    for name in LIST_AND_HUB_URLS:
        if name in EXCLUDED_URLS:
            continue
        try:
            url = reverse(name)
        except Exception as e:
            fail(f'reverse {name}', str(e))
            continue
        # Chặn nhầm sang kho-npl / kiotviet
        if url.startswith('/kho-npl/') or url.startswith('/kiotviet/'):
            fail(f'{name} trỏ ra module ngoài SX', url)
            continue
        try:
            resp = client.get(url)
        except Exception:
            fail(f'GET {name}', traceback.format_exc(limit=3))
            continue
        good, detail = _body_ok(resp)
        if good:
            ok(f'GET {name}')
        elif resp.status_code in (301, 302) and name in (
            'san_xuat:hub',
            'san_xuat:redirect_costing',
            'san_xuat:plan_stub',
            'san_xuat:dispatch_stub',
            'san_xuat:qc_stub',
            'san_xuat:process_stub',
        ):
            ok(f'GET {name} → redirect {resp.status_code}')
        else:
            fail(f'GET {name}', detail or f'status={resp.status_code}')

    # User không quyền → chặn
    denied = (
        User.objects.filter(is_active=True)
        .exclude(pk=qa_user.pk)
        .exclude(is_superuser=True)
        .first()
    )
    if denied and not user_can_access_module(denied, MODULE_SAN_XUAT):
        c2 = Client(HTTP_HOST=HOST)
        c2.force_login(denied)
        r = c2.get(reverse('san_xuat:overview'))
        if r.status_code in (302, 403):
            ok(f'User {denied.username} không quyền SX → chặn ({r.status_code})')
        else:
            warn(f'User {denied.username} không quyền nhưng overview → {r.status_code}')


# --- 5. Xuất Excel list ---
section('5. Xuất Excel list')
if client and qa_user:
    for key in EXPORT_KEYS_SAMPLE:
        if key not in LIST_EXPORT_REGISTRY:
            warn(f'Export key không có trong registry: {key}')
            continue
        url = reverse('san_xuat:list_export', kwargs={'export_key': key})
        r = client.get(url)
        ct = r.get('Content-Type', '')
        if r.status_code == 200 and ('spreadsheetml' in ct or 'octet-stream' in ct or 'excel' in ct.lower()):
            ok(f'Export {key}')
        elif r.status_code == 403:
            warn(f'Export {key} → 403 (thiếu quyền export)')
        else:
            fail(f'Export {key}', f'status={r.status_code} ct={ct[:80]}')


# --- 6. E2E nội bộ SX (không post kho NPL / KV) ---
section('6. E2E SX nội bộ (không kho NPL / bán hàng)')
created = {
    'mo': None,
    'ycx': None,
    'stat': None,
    'pack': None,
    'wa': None,
}

try:
    if not qa_user or not user_can_create_module(qa_user, MODULE_SAN_XUAT):
        warn('Bỏ qua E2E — thiếu quyền create')
    else:
        tech = (
            ProductTechDoc.objects.filter(bom_versions__status=BomVersion.STATUS_ACTIVE)
            .distinct()
            .order_by('id')
            .first()
        )
        if not tech:
            tech = ProductTechDoc.objects.order_by('id').first()
        if not tech:
            warn('Không có hồ sơ SX — bỏ qua E2E tạo LSX')
        else:
            ts = timezone.now().strftime('%H%M%S')
            mo = create_mo_from_bom(
                product_code=tech.product_code,
                qty=Decimal('2'),
                notes=NOTE,
                user=qa_user,
            )
            created['mo'] = mo
            ok(f'Tạo LSX nháp {mo.code} ({tech.product_code})')

            mo = mo_release(mo_id=mo.pk, user=qa_user)
            if mo.status == SxProductionOrder.STATUS_RELEASED:
                ok(f'Phát hành {mo.code}')
            else:
                fail('Phát hành LSX', mo.status)

            # YCX nháp — không duyệt/post kho
            ycx = build_material_issue_request(
                production_order_id=mo.pk,
                user=qa_user,
                notes=NOTE,
            )
            created['ycx'] = ycx
            ok(f'Tạo YCX nháp {ycx.code} (không post kho)')

            stat = create_production_stat(
                production_order_id=mo.pk,
                stat_date=timezone.localdate(),
                process_name='QA-VPS',
                qty_good=Decimal('1'),
                team_label='QA',
                notes=NOTE,
            )
            created['stat'] = stat
            ok(f'Tạo TKSX nháp {stat.code}')
            try:
                confirm_stat(stat_id=stat.pk)
                stat.refresh_from_db()
                if stat.status == SxProductionStat.STATUS_CONFIRMED:
                    ok(f'Xác nhận TKSX {stat.code}')
                else:
                    warn(f'TKSX status={stat.status}')
            except Exception as exc:
                # Gate yêu cầu phiếu xuất đã ghi sổ — cố ý không post kho NPL.
                warn(f'Bỏ qua xác nhận TKSX (gate/kho): {type(exc).__name__}')

            pack = create_packing_record(
                production_order_id=mo.pk,
                qty=Decimal('1'),
                pack_date=timezone.localdate(),
                lot_code=f'QA-LOT-{ts}',
                notes=NOTE,
            )
            created['pack'] = pack
            ok(f'Tạo đóng gói {pack.code}')

            wa = create_work_assignment(
                production_order_id=mo.pk,
                title=f'{PREFIX} giao việc {ts}',
                notes=NOTE,
                assigner=qa_user,
            )
            created['wa'] = wa
            ok(f'Tạo giao việc {wa.code}')

            tr = trace_production(query=mo.code)
            if tr.mo and tr.mo.pk == mo.pk and len(tr.timeline or []) >= 1:
                ok(f'Truy xuất {mo.code}: timeline={len(tr.timeline)}')
            else:
                fail('Truy xuất service', f'mo={getattr(tr.mo, "code", None)}')

            if client:
                detail_checks = [
                    ('san_xuat:dispatch_mo_detail', {'pk': mo.pk}),
                    ('san_xuat:dispatch_material_issue_req_detail', {'pk': ycx.pk}),
                    ('san_xuat:dispatch_prod_stats_detail', {'pk': stat.pk}),
                    ('san_xuat:packing_detail', {'pk': pack.pk}),
                    ('san_xuat:print_mo', {'pk': mo.pk}),
                    ('san_xuat:print_ycx', {'pk': ycx.pk}),
                    ('san_xuat:print_packing', {'pk': pack.pk}),
                ]
                for name, kwargs in detail_checks:
                    url = reverse(name, kwargs=kwargs)
                    r = client.get(url)
                    good, detail = _body_ok(r)
                    if good:
                        ok(f'GET {name}')
                    elif r.status_code == 403 and 'print' in name:
                        warn(f'{name} → 403 (thiếu quyền in)')
                    else:
                        fail(f'GET {name}', detail or f'status={r.status_code}')

                r = client.get(reverse('san_xuat:traceability'), {'query': mo.code, 'gaps': '1'})
                good, detail = _body_ok(r)
                if good and mo.code.encode() in r.content:
                    ok('GET truy-xuat + gaps')
                elif good:
                    ok('GET truy-xuat (200)')
                else:
                    fail('GET truy-xuat', detail)
except Exception as e:
    fail('E2E SX', f'{e}\n{traceback.format_exc(limit=5)}')


# --- 7. Dọn dữ liệu QA ---
section('7. Dọn dữ liệu QA')
try:
    cleaned = 0
    if created['wa']:
        cleaned += SxWorkAssignment.objects.filter(pk=created['wa'].pk).delete()[0]
    if created['pack']:
        cleaned += SxPackingRecord.objects.filter(pk=created['pack'].pk).delete()[0]
    if created['stat']:
        cleaned += SxProductionStat.objects.filter(pk=created['stat'].pk).delete()[0]
    if created['ycx']:
        # lines cascade
        cleaned += SxMaterialIssueRequest.objects.filter(pk=created['ycx'].pk).delete()[0]
    if created['mo']:
        cleaned += SxProductionOrder.objects.filter(pk=created['mo'].pk).delete()[0]
    # Dọn sót theo note prefix
    cleaned += SxWorkAssignment.objects.filter(notes__startswith=PREFIX).delete()[0]
    cleaned += SxPackingRecord.objects.filter(notes__startswith=PREFIX).delete()[0]
    cleaned += SxProductionStat.objects.filter(notes__startswith=PREFIX).delete()[0]
    cleaned += SxMaterialIssueRequest.objects.filter(notes__startswith=PREFIX).delete()[0]
    cleaned += SxProductionOrder.objects.filter(notes__startswith=PREFIX).delete()[0]
    ok(f'Đã dọn ~{cleaned} bản ghi QA')
except Exception as e:
    warn(f'Dọn dữ liệu: {e}')


# --- 8. Portal sidebar ---
section('8. Portal — menu SX')
try:
    if client:
        r = client.get(reverse('san_xuat:overview'))
        body = r.content.decode('utf-8', errors='replace')
        if r.status_code == 200:
            ok('Overview SX render OK')
        else:
            fail('Overview SX', f'status={r.status_code}')
        # Không được lộ link test kho-npl trong assert bắt buộc — chỉ kiểm tra trang sống
except Exception as e:
    fail('Portal menu', str(e))


# --- Tổng kết ---
section('TỔNG KẾT')
print(f'  PASS: {len(PASS)}')
print(f'  FAIL: {len(FAIL)}')
print(f'  WARN: {len(WARN)}')
if FAIL:
    print('\nCác lỗi:')
    for item in FAIL:
        print(f'  - {item}')
print('\nOK' if not FAIL else '\nFAILED')
_exit_code = 1 if FAIL else 0
if _STANDALONE:
    sys.exit(_exit_code)
raise SystemExit(_exit_code)
