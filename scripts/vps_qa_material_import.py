"""
QA import danh mục NPL trên VPS (dữ liệu thật, mã test tạm rồi xóa).
Chạy:
  docker compose exec -T web python manage.py shell < scripts/vps_qa_material_import.py
"""
import io
import sys
import traceback

import pandas as pd
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from kho_npl.models import Material, MaterialCategory, Unit
from kho_npl.services.material_import_export import (
    EXCEL_HEADERS,
    import_materials_from_excel,
    sample_template_xlsx,
)

User = get_user_model()
PREFIX = '[VPS-QA-IMPORT]'
TEST_CODE = 'ZZ-QA-IMPORT-TMP'
PASS = []
FAIL = []


def ok(msg):
    PASS.append(msg)
    print(f'  PASS: {msg}')


def fail(msg, detail=''):
    FAIL.append(f'{msg} {detail}'.strip())
    print(f'  FAIL: {msg}' + (f' — {detail}' if detail else ''))


def section(title):
    print(f'\n=== {title} ===')


def make_xlsx(rows):
    df = pd.DataFrame(rows, columns=EXCEL_HEADERS)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    buf.name = 'qa_import.xlsx'
    return buf


print(f'{PREFIX} bắt đầu')

# --- 0. Prerequisites ---
section('0. Prerequisites')
try:
    category = MaterialCategory.objects.filter(is_active=True).order_by('id').first()
    unit = Unit.objects.filter(is_active=True).order_by('id').first()
    if not category or not unit:
        fail('Thiếu nhóm/ĐVT active', f'cat={category} unit={unit}')
        print(f'\n{PREFIX} STOP — không đủ master data')
        sys.exit(1)
    ok(f'Nhóm={category.code}, ĐVT={unit.code}')
    Material.objects.filter(code=TEST_CODE).delete()
    ok(f'Dọn mã test cũ {TEST_CODE}')
except Exception as e:
    fail('Prerequisites', str(e))
    traceback.print_exc()
    sys.exit(1)

# --- 1. Sample template ---
section('1. Sample template Excel')
try:
    resp = sample_template_xlsx()
    if resp.status_code == 200 and 'spreadsheet' in resp.get('Content-Type', ''):
        ok(f'Template OK ({len(resp.content)} bytes)')
    else:
        fail('Template', f'status={resp.status_code} ct={resp.get("Content-Type")}')
except Exception as e:
    fail('Template', str(e))
    traceback.print_exc()

# --- 2. Import tạo mới ---
section('2. Import tạo mới theo mã')
try:
    xlsx = make_xlsx([{
        'Mã NPL': TEST_CODE,
        'Tên NPL': 'QA IMPORT TEMP V1',
        'Tên nhóm hàng': 'QAIMP',
        'Mã nhóm': category.code,
        'Màu sắc': '',
        'Quy cách': '',
        'Mã ĐVT': unit.code,
        'Mã NCC': '',
        'Tồn tối thiểu': 1.5,
        'Giá cơ bản': 12345,
        'Ghi chú': 'vps-qa-create',
        'Đang dùng': 'Có',
    }])
    result = import_materials_from_excel(xlsx)
    print(f'  result={result}')
    mat = Material.objects.filter(code=TEST_CODE).first()
    if result.get('created') == 1 and result.get('updated') == 0 and mat:
        ok(f'Tạo mới: {mat.code} | {mat.name} | giá={mat.base_price}')
    else:
        fail('Tạo mới', f'result={result} exists={bool(mat)}')
    if mat and str(mat.name).upper() == 'QA IMPORT TEMP V1':
        ok('Tên được normalize uppercase')
    elif mat:
        fail('Tên uppercase', repr(mat.name))
except Exception as e:
    fail('Import tạo mới', str(e))
    traceback.print_exc()

# --- 3. Import cùng mã → cập nhật (không tạo mới) ---
section('3. Import cùng mã → cập nhật (đè), không tạo mã mới')
try:
    before_count = Material.objects.filter(code=TEST_CODE).count()
    before_pk = Material.objects.get(code=TEST_CODE).pk
    xlsx = make_xlsx([{
        'Mã NPL': TEST_CODE,
        'Tên NPL': 'QA IMPORT TEMP V2 UPDATED',
        'Tên nhóm hàng': 'QAIMP',
        'Mã nhóm': category.code,
        'Màu sắc': '',
        'Quy cách': '',
        'Mã ĐVT': unit.code,
        'Mã NCC': '',
        'Tồn tối thiểu': 9,
        'Giá cơ bản': 99999,
        'Ghi chú': 'vps-qa-update',
        'Đang dùng': 'Có',
    }])
    result = import_materials_from_excel(xlsx)
    print(f'  result={result}')
    after_count = Material.objects.filter(code=TEST_CODE).count()
    mat = Material.objects.get(code=TEST_CODE)
    if result.get('created') == 0 and result.get('updated') == 1:
        ok('result: created=0, updated=1')
    else:
        fail('result update', str(result))
    if after_count == before_count == 1 and mat.pk == before_pk:
        ok(f'Giữ cùng PK={mat.pk}, không nhân bản mã')
    else:
        fail('Nhân bản / đổi PK', f'before={before_count}/{before_pk} after={after_count}/{mat.pk}')
    if 'V2 UPDATED' in mat.name and float(mat.base_price) == 99999.0 and float(mat.min_stock) == 9.0:
        ok(f'Đã đè field: name={mat.name}, giá={mat.base_price}, min={mat.min_stock}')
    else:
        fail('Field chưa đè', f'name={mat.name} price={mat.base_price} min={mat.min_stock}')
except Exception as e:
    fail('Import cập nhật', str(e))
    traceback.print_exc()

# --- 4. HTTP endpoint (CSRF + multipart) ---
section('4. HTTP POST /kho-npl/danh-muc/import-excel/')
try:
    user = (
        User.objects.filter(username='admin').first()
        or User.objects.filter(is_superuser=True).first()
    )
    if not user:
        fail('Không có user admin/superuser để test HTTP')
    else:
        Material.objects.filter(code=TEST_CODE).delete()
        client = Client(HTTP_HOST='portal.justplay.vn')
        client.force_login(user)
        xlsx = make_xlsx([{
            'Mã NPL': TEST_CODE,
            'Tên NPL': 'QA IMPORT HTTP',
            'Tên nhóm hàng': 'QAIMP',
            'Mã nhóm': category.code,
            'Màu sắc': '',
            'Quy cách': '',
            'Mã ĐVT': unit.code,
            'Mã NCC': '',
            'Tồn tối thiểu': 0,
            'Giá cơ bản': 1000,
            'Ghi chú': 'vps-qa-http',
            'Đang dùng': 'Có',
        }])
        url = reverse('kho_npl:material_import')
        resp = client.post(url, {'excel_file': xlsx}, follow=True)
        mat = Material.objects.filter(code=TEST_CODE).first()
        if resp.status_code == 200 and mat and 'HTTP' in mat.name:
            ok(f'HTTP import OK via {user.username} → {mat.code}')
        else:
            fail(
                'HTTP import',
                f'status={resp.status_code} mat={mat} content={resp.content[:300]!r}',
            )

        # list page có nút import
        list_resp = client.get(reverse('kho_npl:material_list'))
        body = list_resp.content.decode('utf-8', errors='ignore')
        if list_resp.status_code == 200 and ('import' in body.lower() or 'Nhập' in body):
            ok('Trang danh mục có UI nhập Excel')
        else:
            fail('UI import trên list', f'status={list_resp.status_code}')
except Exception as e:
    fail('HTTP endpoint', str(e))
    traceback.print_exc()

# --- 5. Cleanup ---
section('5. Cleanup')
try:
    deleted, _ = Material.objects.filter(code=TEST_CODE).delete()
    ok(f'Đã xóa mã test {TEST_CODE} (deleted={deleted})')
except Exception as e:
    fail('Cleanup', str(e))

# --- Summary ---
print(f'\n{PREFIX} SUMMARY: {len(PASS)} PASS, {len(FAIL)} FAIL')
for f in FAIL:
    print(f'  - {f}')
sys.exit(1 if FAIL else 0)
