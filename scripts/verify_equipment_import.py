"""
Đối chiếu dữ liệu thiết bị: file gốc (goc.xlsx) → portal_chuan.xlsx → DB.

Chạy VPS:
  docker compose exec -T -w /app web python scripts/verify_equipment_import.py
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

DATA_DIR = Path(__file__).parent / 'data' / 'equipment_import'
GOC = DATA_DIR / 'goc.xlsx'
CHUAN = DATA_DIR / 'portal_chuan.xlsx'

COMPARE_FIELDS = [
    ('name', 'Tên thiết bị', 'name'),
    ('category', 'Loại (mã)', 'category'),
    ('managed_department', 'Bộ phận quản lý (tên phòng ban)', 'managed_department'),
    ('status', 'Trạng thái (new / active / broken / maintenance / scrapped)', 'status'),
    ('usage_department_text', 'Phòng ban sử dụng', 'usage_department_text'),
    ('usage_room', 'Phòng / vị trí (Line, khu vực…)', 'usage_room'),
    ('assigned_user_text', 'Người dùng / người phụ trách', 'assigned_user_text'),
    ('model_number', 'Model / hãng', 'model_number'),
    ('serial_number', 'Serial Number', 'serial_number'),
    ('quantity', 'Số lượng', 'quantity'),
]


def _norm(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ''
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y-%m-%d')
    text = str(value).strip()
    text = re.sub(r'\s+', ' ', text)
    return text.lower()


def _norm_key(name, serial='', model='', sheet='') -> str:
    return '|'.join(filter(None, [_norm(name), _norm(serial), _norm(model), _norm(sheet)]))


def _safe_str(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ''
    return str(value).strip()


def _safe_int(value, default=1) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return default


def _strip_urls(text: str) -> str:
    return re.sub(r'https?://\S+', '', text or '').strip()


def load_goc_rows(path: Path) -> list[dict]:
    rows = []
    dfs = pd.read_excel(path, sheet_name=None)
    for sheet_name, df in dfs.items():
        for idx, row in df.iterrows():
            name = _safe_str(row.get('Tên thiết bị'))
            if not name:
                continue
            serial = _safe_str(row.get('Serial Number') or row.get('Serial'))
            model = _safe_str(row.get('Model / hãng') or row.get('Model'))
            status_raw = _safe_str(
                row.get('Trạng thái (new / active / broken / maintenance / scrapped)')
                or row.get('Trạng thái mã')
                or row.get('Trạng thái (hiển thị)')
                or row.get('Trạng thái')
            )
            rows.append({
                'sheet': sheet_name,
                'row_num': int(idx) + 2,
                'name': name,
                'serial_number': serial,
                'model_number': model,
                'category': _safe_str(row.get('Loại (mã)')),
                'managed_department': _safe_str(row.get('Bộ phận quản lý (tên phòng ban)')),
                'status_raw': status_raw,
                'usage_department_text': _safe_str(row.get('Phòng ban sử dụng')) or sheet_name,
                'usage_room': _safe_str(
                    row.get('Phòng / vị trí (Line, khu vực…)')
                    or row.get('Vị trí')
                    or row.get('Phòng ban sử dụng')
                    or sheet_name
                ),
                'assigned_user_text': _safe_str(row.get('Người dùng / người phụ trách')),
                'quantity': _safe_int(row.get('Số lượng')),
                'description_raw': _safe_str(row.get('Mô tả')),
                'configuration_raw': _safe_str(row.get('Thông số kỹ thuật') or row.get('Cấu hình')),
                'key': _norm_key(name, serial, model),
                'key_sheet': _norm_key(name, serial, model, sheet_name),
            })
    return rows


def load_chuan_rows(path: Path) -> list[dict]:
    rows = []
    xls = pd.ExcelFile(path)
    for sheet in ('Thiết bị sản xuất', 'Thiết bị IT'):
        if sheet not in xls.sheet_names:
            continue
        df = pd.read_excel(path, sheet_name=sheet)
        for idx, row in df.iterrows():
            name = _safe_str(row.get('Tên thiết bị'))
            if not name:
                continue
            serial = _safe_str(row.get('Serial Number'))
            model = _safe_str(row.get('Model / hãng'))
            rows.append({
                'import_sheet': sheet,
                'row_num': int(idx) + 2,
                'device_code': _safe_str(row.get('Mã thiết bị')),
                'name': name,
                'serial_number': serial,
                'model_number': model,
                'category': _safe_str(row.get('Loại (mã)')),
                'managed_department': _safe_str(row.get('Bộ phận quản lý (tên phòng ban)')),
                'status': _safe_str(row.get('Trạng thái (new / active / broken / maintenance / scrapped)')),
                'usage_department_text': _safe_str(row.get('Phòng ban sử dụng')),
                'usage_room': _safe_str(row.get('Phòng / vị trí (Line, khu vực…)')),
                'assigned_user_text': _safe_str(row.get('Người dùng / người phụ trách')),
                'quantity': _safe_int(row.get('Số lượng')),
                'description': _safe_str(row.get('Mô tả')),
                'configuration': _safe_str(row.get('Thông số kỹ thuật') or row.get('Cấu hình (RAM, CPU…)')),
                'key': _norm_key(name, serial, model),
            })
    return rows


def load_db_rows() -> list[dict]:
    import django
    django.setup()
    from equipment.models import Device
    from equipment.services.device_categories import import_profile_for_code

    rows = []
    for d in Device.objects.select_related('managed_department').order_by('device_code'):
        rows.append({
            'device_code': d.device_code,
            'name': d.name,
            'serial_number': d.serial_number or '',
            'model_number': d.model_number or '',
            'category': d.category,
            'scope': 'it' if import_profile_for_code(d.category) == 'it' else 'production',
            'managed_department': (d.managed_department.name if d.managed_department_id else ''),
            'status': d.status,
            'usage_department_text': d.usage_department_text or '',
            'usage_room': d.usage_room or '',
            'assigned_user_text': d.assigned_user_text or '',
            'quantity': d.quantity,
            'description': d.description or '',
            'configuration': d.configuration or '',
            'has_photo': bool(d.photo),
            'key': _norm_key(d.name, d.serial_number, d.model_number),
        })
    return rows


def match_goc_to_chuan(goc_rows, chuan_rows):
    chuan_by_key: dict[str, list] = {}
    for r in chuan_rows:
        chuan_by_key.setdefault(r['key'], []).append(r)

    matched = []
    missing_in_chuan = []
    for g in goc_rows:
        hits = chuan_by_key.get(g['key'], [])
        if not hits:
            # fallback: name only
            name_hits = [c for c in chuan_rows if _norm(c['name']) == _norm(g['name'])]
            hits = name_hits
        if not hits:
            missing_in_chuan.append(g)
            continue
        c = hits.pop(0)
        matched.append((g, c))
    unmatched_chuan = []
    matched_codes = {c['device_code'] for _, c in matched}
    for c in chuan_rows:
        if c['device_code'] not in matched_codes:
            unmatched_chuan.append(c)
    return matched, missing_in_chuan, unmatched_chuan


def compare_pair(left: dict, right: dict, fields: list[tuple]) -> list[str]:
    diffs = []
    for lkey, _, rkey in fields:
        lv = left.get(lkey if lkey != 'status' else lkey)
        rv = right.get(rkey)
        if lkey == 'quantity':
            if _safe_int(lv) != _safe_int(rv):
                diffs.append(f'{lkey}: {lv!r} != {rv!r}')
            continue
        if _norm(lv) != _norm(rv):
            diffs.append(f'{lkey}: {lv!r} != {rv!r}')
    return diffs


def main():
    if not GOC.exists():
        raise SystemExit(f'Missing {GOC}')
    if not CHUAN.exists():
        raise SystemExit(f'Missing {CHUAN}')

    goc_rows = load_goc_rows(GOC)
    chuan_rows = load_chuan_rows(CHUAN)
    db_rows = load_db_rows()

    print('=' * 60)
    print('TỔNG SỐ DÒNG')
    print(f'  File gốc (goc.xlsx):     {len(goc_rows)}')
    print(f'  File chuẩn (portal):     {len(chuan_rows)}')
    print(f'  Database:                {len(db_rows)}')
    print(f'  IT trong chuẩn:          {sum(1 for r in chuan_rows if r["import_sheet"] == "Thiết bị IT")}')
    print(f'  IT trong DB:             {sum(1 for r in db_rows if r["scope"] == "it")}')
    print(f'  Có ảnh trong DB:         {sum(1 for r in db_rows if r["has_photo"])}')

    # goc sheets breakdown
    from collections import Counter
    sheet_counts = Counter(r['sheet'] for r in goc_rows)
    print('\nSheet file gốc:')
    for sheet, cnt in sorted(sheet_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f'  {sheet}: {cnt}')

    # --- goc vs chuan ---
    matched_gc, missing_gc, extra_chuan = match_goc_to_chuan(goc_rows, chuan_rows)
    print('\n' + '=' * 60)
    print('FILE GỐC → FILE CHUẨN')
    print(f'  Khớp theo tên+serial+model: {len(matched_gc)}')
    print(f'  Gốc không tìm thấy trong chuẩn: {len(missing_gc)}')
    print(f'  Chuẩn không khớp gốc: {len(extra_chuan)}')

    gc_field_diffs = []
    for g, c in matched_gc:
        diffs = compare_pair(
            {
                'name': g['name'],
                'category': g['category'] or '(infer)',
                'managed_department': g['managed_department'] or g['sheet'],
                'status': g['status_raw'] or 'active',
                'usage_department_text': g['usage_department_text'],
                'usage_room': g['usage_room'],
                'assigned_user_text': g['assigned_user_text'],
                'model_number': g['model_number'],
                'serial_number': g['serial_number'],
                'quantity': g['quantity'],
            },
            c,
            COMPARE_FIELDS,
        )
        if diffs:
            gc_field_diffs.append((g, c, diffs))

    # Filter expected diffs: category inferred, status normalized, managed_dept default
    unexpected_gc = []
    for g, c, diffs in gc_field_diffs:
        expected = set()
        if not g['category']:
            expected.add('category')
        if not g['managed_department']:
            expected.add('managed_department')
        if g['status_raw'] and _norm(g['status_raw']) not in {'active', 'new', 'broken', 'maintenance', 'scrapped'}:
            expected.add('status')
        real = [d for d in diffs if d.split(':')[0] not in expected]
        if real:
            unexpected_gc.append((g, c, real))

    print(f'  Khác biệt field (sau chuẩn hoá): {len(gc_field_diffs)} dòng có thay đổi')
    print(f'  Khác biệt bất thường: {len(unexpected_gc)}')

    if missing_gc:
        print('\n  --- Gốc THIẾU trong chuẩn ---')
        for g in missing_gc[:15]:
            print(f'    [{g["sheet"]} r{g["row_num"]}] {g["name"]} | S/N {g["serial_number"] or "-"}')

    if unexpected_gc:
        print('\n  --- Khác biệt bất thường (gốc vs chuẩn) ---')
        for g, c, diffs in unexpected_gc[:20]:
            print(f'    {c["device_code"]} {g["name"]}')
            for d in diffs:
                print(f'      · {d}')

    # IT/HCNS check from goc
    hcns_goc = [g for g in goc_rows if 'hcns' in _norm(g['sheet']) or 'hcns' in _norm(g['usage_department_text'])]
    hcns_chuan = [c for c in chuan_rows if c['import_sheet'] == 'Thiết bị IT' and 'hcns' in _norm(c['usage_department_text'])]
    print('\n  PC/Máy in HCNS:')
    print(f'    Gốc (sheet HCNS): {len(hcns_goc)} dòng')
    for g in hcns_goc:
        print(f'      · {g["name"]} | {g["model_number"] or "-"}')
    print(f'    Chuẩn (sheet IT + HCNS): {len(hcns_chuan)} dòng')
    for c in hcns_chuan:
        print(f'      · {c["device_code"]} {c["name"]}')

    # --- chuan vs db ---
    chuan_by_code = {r['device_code']: r for r in chuan_rows}
    db_by_code = {r['device_code']: r for r in db_rows}

    missing_db = [c for code, c in chuan_by_code.items() if code not in db_by_code]
    extra_db = [d for code, d in db_by_code.items() if code not in chuan_by_code]

    print('\n' + '=' * 60)
    print('FILE CHUẨN → DATABASE')
    print(f'  Mã khớp: {len(set(chuan_by_code) & set(db_by_code))}')
    print(f'  Chuẩn chưa vào DB: {len(missing_db)}')
    print(f'  DB thừa (không trong chuẩn): {len(extra_db)}')

    chuan_db_diffs = []
    for code, c in chuan_by_code.items():
        d = db_by_code.get(code)
        if not d:
            continue
        diffs = compare_pair(c, d, COMPARE_FIELDS)
        # managed_department in DB may be FK resolved name
        diffs = [x for x in diffs if not x.startswith('managed_department')]
        if _norm(c['description']) != _norm(d['description']):
            pass  # should match
        else:
            pass
        for field in ('description', 'configuration'):
            if _norm(c.get(field)) != _norm(d.get(field)):
                diffs.append(f'{field}: khác nội dung')
        if diffs:
            chuan_db_diffs.append((code, c['name'], diffs))

    print(f'  Khác biệt field: {len(chuan_db_diffs)}')
    if chuan_db_diffs:
        print('\n  --- Khác biệt chuẩn vs DB ---')
        for code, name, diffs in chuan_db_diffs[:25]:
            print(f'    {code} {name}')
            for d in diffs:
                print(f'      · {d}')

    # Photos: rows with drive link in goc
    from equipment.services.drive_photo import first_drive_url
    goc_with_photo = 0
    photo_matched = 0
    photo_missing = []
    for g in goc_rows:
        url = first_drive_url(g['description_raw'], g['configuration_raw'])
        if not url:
            continue
        goc_with_photo += 1
        hits = [d for d in db_rows if d['key'] == g['key']]
        if not hits:
            hits = [d for d in db_rows if _norm(d['name']) == _norm(g['name'])]
        if hits and hits[0]['has_photo']:
            photo_matched += 1
        elif hits:
            photo_missing.append((g['name'], hits[0]['device_code']))

    print('\n' + '=' * 60)
    print('ẢNH GOOGLE DRIVE')
    print(f'  Gốc có link ảnh: {goc_with_photo}')
    print(f'  DB đã gắn photo: {photo_matched}')
    print(f'  Có link gốc nhưng DB chưa có ảnh: {len(photo_missing)}')
    if photo_missing:
        for name, code in photo_missing:
            print(f'    · {code} {name}')

    # Summary
    ok = (
        len(goc_rows) == len(chuan_rows) == len(db_rows)
        and not missing_gc
        and not missing_db
        and not extra_db
        and not unexpected_gc
        and not chuan_db_diffs
    )
    print('\n' + '=' * 60)
    if ok:
        print('KẾT LUẬN: Dữ liệu KHỚP file gốc (sau chuẩn hoá mã loại/trạng thái/mô tả ảnh).')
    else:
        print('KẾT LUẬN: Có điểm cần xem — chi tiết ở trên.')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
