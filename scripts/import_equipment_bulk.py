"""
Xóa toàn bộ thiết bị cũ và import từ Excel chuẩn Portal + ảnh Google Drive.

Chạy local:
  python scripts/import_equipment_bulk.py

Chạy VPS:
  docker compose exec -T -w /app web python scripts/import_equipment_bulk.py --yes
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

DATA_DIR = Path(__file__).parent / 'data' / 'equipment_import'
OPTIMIZED_XLSX = DATA_DIR / 'portal_chuan.xlsx'
SOURCE_XLSX = DATA_DIR / 'goc.xlsx'

IT_CATEGORIES = {'PC', 'Laptop', 'Printer', 'Network', 'Internet', 'CCTV', 'PHONE', 'ATTENDANCE', 'DISPLAY'}


def _setup_django():
    import django
    django.setup()


def _norm_key(*parts) -> str:
    bits = []
    for p in parts:
        if p is None or (isinstance(p, float) and pd.isna(p)):
            continue
        text = str(p).strip().lower()
        if text:
            bits.append(re.sub(r'\s+', ' ', text))
    return '|'.join(bits)


def _safe_str(value, default='') -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value).strip()


def _safe_int(value, default=1) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return default


def _parse_date(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, 'date'):
        return value.date()
    text = str(value).strip()
    if not text or text.lower() in ('cũ', 'cu', 'nat'):
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def build_photo_link_index(source_path: Path) -> dict[str, str]:
    """Map key(name|serial|model) -> drive URL từ file Excel gốc."""
    from equipment.services.drive_photo import first_drive_url

    index: dict[str, str] = {}
    dfs = pd.read_excel(source_path, sheet_name=None)
    for sheet_name, df in dfs.items():
        for _, row in df.iterrows():
            name = _safe_str(row.get('Tên thiết bị'))
            if not name:
                continue
            serial = _safe_str(row.get('Serial Number') or row.get('Serial'))
            model = _safe_str(row.get('Model / hãng') or row.get('Model'))
            url = first_drive_url(
                row.get('Mô tả'),
                row.get('Thông số kỹ thuật'),
                row.get('Cấu hình'),
            )
            if not url:
                continue
            for key in {
                _norm_key(name, serial, model),
                _norm_key(name, serial),
                _norm_key(name, model),
                _norm_key(name),
                _norm_key(sheet_name, name, serial),
            }:
                index.setdefault(key, url)
    return index


def load_rows(optimized_path: Path) -> list[dict]:
    rows: list[dict] = []
    xls = pd.ExcelFile(optimized_path)
    for sheet in ('Thiết bị sản xuất', 'Thiết bị IT'):
        if sheet not in xls.sheet_names:
            continue
        df = pd.read_excel(optimized_path, sheet_name=sheet)
        for _, row in df.iterrows():
            name = _safe_str(row.get('Tên thiết bị'))
            if not name:
                continue
            cat = _safe_str(row.get('Loại (mã)')) or 'PROD_OTHER'
            rows.append({
                'scope': 'it' if cat in IT_CATEGORIES or sheet == 'Thiết bị IT' else 'production',
                'device_code': _safe_str(row.get('Mã thiết bị')),
                'name': name,
                'category': cat,
                'managed_department': _safe_str(row.get('Bộ phận quản lý (tên phòng ban)')),
                'status': _safe_str(row.get('Trạng thái (new / active / broken / maintenance / scrapped)'), 'active'),
                'usage_department_text': _safe_str(row.get('Phòng ban sử dụng')),
                'usage_room': _safe_str(row.get('Phòng / vị trí (Line, khu vực…)')),
                'assigned_user_text': _safe_str(row.get('Người dùng / người phụ trách')),
                'contact_email': _safe_str(row.get('Email liên hệ')),
                'handover_date': _parse_date(row.get('Ngày bàn giao (YYYY-MM-DD)')),
                'model_number': _safe_str(row.get('Model / hãng')),
                'serial_number': _safe_str(row.get('Serial Number')),
                'description': _safe_str(row.get('Mô tả')),
                'configuration': _safe_str(row.get('Thông số kỹ thuật') or row.get('Cấu hình (RAM, CPU…)')),
                'hostname': _safe_str(row.get('Hostname')),
                'ip_address': _safe_str(row.get('Địa chỉ IP')),
                'quantity': _safe_int(row.get('Số lượng')),
                'unit_price': 0,
                'serial_key': _norm_key(name, row.get('Serial Number'), row.get('Model / hãng')),
                'name_key': _norm_key(name),
            })
    return rows


def wipe_equipment_data():
    from equipment.models import Device, DeviceUpdateLog, MaintenanceLog

    counts = {
        'DeviceUpdateLog': DeviceUpdateLog.objects.count(),
        'MaintenanceLog': MaintenanceLog.objects.count(),
        'Device': Device.objects.count(),
    }
    DeviceUpdateLog.objects.all().delete()
    MaintenanceLog.objects.all().delete()
    Device.objects.all().delete()
    return counts


def import_rows(rows: list[dict], photo_index: dict[str, str], *, dry_run: bool = False) -> dict:
    from equipment.models import Device
    from equipment.services.device_code import normalize_device_code
    from equipment.services.device_statuses import normalize_status_value
    from equipment.services.drive_photo import attach_photo_from_drive, first_drive_url
    from equipment.services.managed_department import default_managed_department_for_scope, resolve_managed_department

    stats = {'created': 0, 'photos': 0, 'errors': [], 'it': 0, 'production': 0}

    if dry_run:
        stats['would_create'] = len(rows)
        stats['it'] = sum(1 for r in rows if r['scope'] == 'it')
        stats['production'] = sum(1 for r in rows if r['scope'] == 'production')
        return stats

    for i, row in enumerate(rows, 1):
        try:
            scope = row['scope']
            managed = resolve_managed_department(row['managed_department']) or default_managed_department_for_scope(scope)
            status = normalize_status_value(row['status']) or row['status'] or Device.STATUS_ACTIVE
            code = normalize_device_code(row['device_code'])
            if not code:
                raise ValueError('Thiếu mã thiết bị')

            device = Device(
                device_code=code,
                name=row['name'],
                category=row['category'],
                managed_department=managed,
                status=status,
                usage_department_text=row['usage_department_text'],
                usage_room=row['usage_room'],
                assigned_user_text=row['assigned_user_text'],
                contact_email=row['contact_email'],
                handover_date=row['handover_date'],
                model_number=row['model_number'],
                serial_number=row['serial_number'],
                description=row['description'],
                configuration=row['configuration'],
                hostname=row['hostname'],
                ip_address=row['ip_address'] or None,
                quantity=row['quantity'],
                unit_price=Decimal(row['unit_price'] or 0),
            )
            device.save()

            photo_url = (
                photo_index.get(row['serial_key'])
                or photo_index.get(row['name_key'])
            )
            if photo_url and attach_photo_from_drive(device, photo_url):
                device.save(update_fields=['photo', 'updated_at'])
                stats['photos'] += 1

            stats['created'] += 1
            if scope == 'it':
                stats['it'] += 1
            else:
                stats['production'] += 1
        except Exception as exc:
            stats['errors'].append(f'Dòng {i} {row.get("device_code")} {row.get("name")}: {exc}')

    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--optimized', type=Path, default=OPTIMIZED_XLSX)
    parser.add_argument('--source', type=Path, default=SOURCE_XLSX)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--yes', action='store_true', help='Xác nhận xóa toàn bộ thiết bị cũ')
    args = parser.parse_args()

    if not args.optimized.exists():
        raise SystemExit(f'Không thấy file: {args.optimized}')
    if not args.source.exists():
        raise SystemExit(f'Không thấy file gốc (link ảnh): {args.source}')

    _setup_django()

    rows = load_rows(args.optimized)
    photo_index = build_photo_link_index(args.source)
    print(f'Rows to import: {len(rows)} (IT: {sum(1 for r in rows if r["scope"]=="it")})')
    print(f'Photo links indexed: {len(photo_index)}')

    if args.dry_run:
        stats = import_rows(rows, photo_index, dry_run=True)
        print('DRY RUN:', stats)
        return

    if not args.yes:
        raise SystemExit('Thêm --yes để xóa toàn bộ thiết bị cũ và import.')

    wiped = wipe_equipment_data()
    print('Wiped:', wiped)
    stats = import_rows(rows, photo_index)
    print('Import done:', stats)
    if stats['errors']:
        print('Errors:')
        for err in stats['errors'][:20]:
            print(' ', err)


if __name__ == '__main__':
    main()
