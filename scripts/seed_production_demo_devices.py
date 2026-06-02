"""Tạo 5 thiết bị sản xuất demo — chạy trên VPS:
docker compose exec -T -w /app web python scripts/seed_production_demo_devices.py
"""
import os
from datetime import date
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django

django.setup()

from equipment.models import Device
from equipment.scope import SCOPE_PRODUCTION
from equipment.services.device_categories import import_profile_for_code
from equipment.services.managed_department import default_managed_department_for_scope

DEMO_DEVICES = [
    {
        'device_code': 'SX-DEMO-001',
        'name': 'Máy may Juki DDL-8700 — Chuyền 1',
        'category': 'SEW_LOCKSTITCH',
        'usage_room': 'Chuyền 1 · Cụm may thân',
        'usage_department_text': 'Xưởng may',
        'model_number': 'DDL-8700',
        'serial_number': 'JK-DEMO-8700-01',
        'configuration': '1 kim, tốc độ 5500 v/ph, bàn ủi hơi tích hợp',
        'status': Device.STATUS_ACTIVE,
        'quantity': 1,
        'unit_price': Decimal('45000000'),
        'description': 'Thiết bị demo — máy may chính chuyền 1',
    },
    {
        'device_code': 'SX-DEMO-002',
        'name': 'Máy overlock Pegasus M832 — Chuyền 2',
        'category': 'SEW_OVERLOCK',
        'usage_room': 'Chuyền 2 · Cụm viền',
        'usage_department_text': 'Xưởng may',
        'model_number': 'M832-405',
        'serial_number': 'PG-DEMO-M832-02',
        'configuration': '4 chỉ, ứng dụng viền áo thun',
        'status': Device.STATUS_ACTIVE,
        'quantity': 1,
        'unit_price': Decimal('28000000'),
    },
    {
        'device_code': 'SX-DEMO-003',
        'name': 'Máy cắt dao rung Eastman — Tổ cắt',
        'category': 'CUT_MACHINE',
        'usage_room': 'Tổ cắt · Bàn số 3',
        'usage_department_text': 'Tổ cắt',
        'model_number': '625X-612',
        'serial_number': 'EM-DEMO-625-03',
        'configuration': 'Dao rung, bàn 6m, hút chân không',
        'status': Device.STATUS_MAINTENANCE,
        'quantity': 1,
        'unit_price': Decimal('120000000'),
        'description': 'Demo — đang bảo trì dao cắt',
    },
    {
        'device_code': 'SX-DEMO-004',
        'name': 'Bàn ủi hơi Veit — Hoàn thiện',
        'category': 'FINISH_IRON',
        'usage_room': 'Khu hoàn thiện · Bàn 12',
        'usage_department_text': 'Hoàn thiện',
        'model_number': 'Veit 9210',
        'serial_number': 'VT-DEMO-9210-04',
        'status': Device.STATUS_BROKEN,
        'quantity': 1,
        'unit_price': Decimal('15000000'),
        'description': 'Demo — báo hỏng van hơi (kiểm thử hỗ trợ kỹ thuật)',
    },
    {
        'device_code': 'SX-DEMO-005',
        'name': 'Máy thêu Tajima 2 đầu — Thêu',
        'category': 'EMB_MACHINE',
        'usage_room': 'Phòng thêu · Lô 2',
        'usage_department_text': 'Thêu in',
        'model_number': 'TFMX-C1501',
        'serial_number': 'TJ-DEMO-C1501-05',
        'configuration': '2 đầu, khung 360×200mm',
        'status': Device.STATUS_ACTIVE,
        'quantity': 1,
        'unit_price': Decimal('85000000'),
        'handover_date': date(2024, 6, 15),
    },
]


def main():
    dept = default_managed_department_for_scope(SCOPE_PRODUCTION)
    created = []
    skipped = []

    for spec in DEMO_DEVICES:
        code = spec['device_code']
        if Device.objects.filter(device_code__iexact=code).exists():
            skipped.append(code)
            continue
        profile = import_profile_for_code(spec['category'])
        if profile != 'machine':
            print(f'Bỏ qua {code}: category {spec["category"]} không phải máy xưởng')
            continue
        device = Device(
            managed_department=dept,
            handover_date=spec.get('handover_date'),
            **{k: v for k, v in spec.items() if k != 'handover_date'},
        )
        device.save()
        created.append(device)

    print(f'Bộ phận quản lý: {dept.name if dept else "—"}')
    print(f'Đã tạo: {len(created)}')
    for d in created:
        print(f'  · {d.device_code} | {d.name} | {d.get_category_display()} | {d.get_status_display()}')
    if skipped:
        print(f'Đã tồn tại (bỏ qua): {", ".join(skipped)}')
    return 0 if created or skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
