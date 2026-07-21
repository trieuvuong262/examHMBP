"""
Seed dữ liệu demo Sản xuất trên VPS — hiển thị trên UI, không đụng kho NPL / bán hàng.

Usage:
    python manage.py seed_san_xuat_vps_demo
    python manage.py seed_san_xuat_vps_demo --clear
    python manage.py seed_san_xuat_vps_demo --limit 8 --codes SP008073,SP008074
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from san_xuat.services.bom import BomError
from san_xuat.services.demo_seed import discover_kv_product_codes
from san_xuat.services.demo_seed_vps import VPS_DEMO_NOTE, clear_vps_demo, seed_vps_demo


class Command(BaseCommand):
    help = (
        'Tạo demo Sản xuất trên VPS: hồ sơ/BOM + kế hoạch + điều phối + QC + '
        'đóng gói/GC/giao việc. Hiển thị trên UI (is_demo=False). '
        'Không tạo/xử lý kho NPL hay bán hàng KiotViet.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help=f'Xóa dữ liệu seed VPS ({VPS_DEMO_NOTE}) và demo cũ is_demo=True.',
        )
        parser.add_argument(
            '--codes',
            default='',
            help='Mã SP phân tách dấu phẩy. Mặc định: đọc mirror KV (chỉ đọc, không ghi KV).',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=8,
            help='Số hồ sơ SX tối đa (mặc định 8).',
        )
        parser.add_argument(
            '--user',
            default='admin',
            help='Username người tạo (mặc định: admin).',
        )
        parser.add_argument(
            '--force-lines',
            action='store_true',
            help='Ghi lại dòng BOM/công đoạn mẫu.',
        )
        parser.add_argument(
            '--keep-legacy-demo',
            action='store_true',
            help='Khi --clear: không xóa demo cũ is_demo=True (*-DEMO-*).',
        )

    def handle(self, *args, **options):
        if options['clear']:
            counts = clear_vps_demo(include_legacy_demo=not options['keep_legacy_demo'])
            self.stdout.write(self.style.SUCCESS(f'Đã xóa seed VPS: {counts}'))
            return

        user = self._resolve_user(options['user'])
        codes = self._resolve_codes(options)
        if not codes:
            raise CommandError(
                'Không tìm thấy mã SP. Truyền --codes SP008073,... hoặc sync mirror KV trước.',
            )

        self.stdout.write(f'Mã SP ({len(codes)}): {", ".join(codes)}')
        self.stdout.write(f'User: {user.username}')

        with transaction.atomic():
            result = seed_vps_demo(
                product_codes=codes,
                user=user,
                visible=True,
                force_lines=options['force_lines'],
            )

        doc = result['docs']
        self.stdout.write(self.style.SUCCESS(
            f'Hồ sơ: {doc["created"]} tạo, {doc["updated"]} cập nhật, {doc["skipped"]} bỏ qua.',
        ))
        self.stdout.write(self.style.SUCCESS('Hub VPS:'))
        for key, val in sorted(result['hub'].items()):
            self.stdout.write(f'  {key}: {val}')

        self.stdout.write('')
        self.stdout.write('Mở nhanh:')
        self.stdout.write('  /san-xuat/tong-quan/')
        self.stdout.write('  /san-xuat/dieu-phoi/lenh-sx/')
        self.stdout.write('  /san-xuat/truy-xuat/?query=LSX-2026-VPS-001&gaps=1')
        self.stdout.write('Không tạo phiếu xuất kho NPL / không sync KiotViet.')

    def _resolve_user(self, username: str):
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if not user:
            raise CommandError(f'Không tìm thấy user: {username}')
        return user

    def _resolve_codes(self, options) -> list[str]:
        raw = (options['codes'] or '').strip()
        if raw:
            return [c.strip() for c in raw.split(',') if c.strip()][: max(1, options['limit'])]
        return discover_kv_product_codes(limit=max(1, options['limit']))
