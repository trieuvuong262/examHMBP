"""Đối chiếu sản phẩm KiotViet ↔ Odoo (Giai đoạn 1 — chỉ đọc, không ghi Odoo).

So khớp theo khóa: KvProduct.code == Odoo product.product.default_code

Usage:
    python manage.py kiotviet_odoo_reconcile
    python manage.py kiotviet_odoo_reconcile --retailer myshop
    python manage.py kiotviet_odoo_reconcile --csv /tmp/recon.csv
    python manage.py kiotviet_odoo_reconcile --show missing_in_odoo --limit 50
"""

from __future__ import annotations

import csv

from django.core.management.base import BaseCommand

from kiotviet.client import KiotVietClient
from kiotviet.odoo_bridge import odoo_ready, reconcile_products

_CSV_CATEGORIES = [
    'missing_in_odoo',
    'price_mismatch',
    'name_mismatch',
    'duplicate_in_kv',
    'duplicate_in_odoo',
    'no_code',
]


class Command(BaseCommand):
    help = 'Đối chiếu sản phẩm KiotViet ↔ Odoo theo code=default_code (chỉ đọc).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--retailer',
            dest='retailer',
            default=None,
            help='Retailer KiotViet cần đối chiếu (mặc định KIOTVIET_RETAILER).',
        )
        parser.add_argument(
            '--csv',
            dest='csv_path',
            default=None,
            help='Xuất chi tiết ra file CSV tại đường dẫn này.',
        )
        parser.add_argument(
            '--show',
            dest='show',
            choices=_CSV_CATEGORIES + ['matched'],
            default=None,
            help='In chi tiết một nhóm ra màn hình.',
        )
        parser.add_argument(
            '--limit',
            dest='limit',
            type=int,
            default=30,
            help='Giới hạn số dòng khi dùng --show (mặc định 30).',
        )

    def handle(self, *args, **options):
        if not KiotVietClient.is_configured():
            self.stderr.write(self.style.ERROR(
                'KiotViet chưa cấu hình (KIOTVIET_ENABLED + credentials trong .env).'
            ))
            return
        if not odoo_ready():
            self.stderr.write(self.style.ERROR(
                'Odoo chưa cấu hình (ODOO_URL/ODOO_DB/ODOO_API_USER/ODOO_API_PASSWORD).'
            ))
            return

        self.stdout.write('Đang đối chiếu KiotViet ↔ Odoo (chỉ đọc)...')
        result = reconcile_products(retailer=options.get('retailer'))

        summary = result.summary()
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'KẾT QUẢ ĐỐI CHIẾU (retailer={result.retailer or "-"})'
        ))
        self.stdout.write(f'  Tổng SP KiotViet (đang KD)   : {summary["kv_total"]}')
        self.stdout.write(self.style.SUCCESS(
            f'  Khớp mã (matched)            : {summary["matched"]}'))
        self.stdout.write(self.style.WARNING(
            f'  Thiếu trên Odoo (cần tạo)    : {summary["missing_in_odoo"]}'))
        self.stdout.write(f'  Lệch giá bán                 : {summary["price_mismatch"]}')
        self.stdout.write(f'  Lệch tên                     : {summary["name_mismatch"]}')
        self.stdout.write(f'  Trùng mã trong KiotViet      : {summary["duplicate_in_kv"]}')
        self.stdout.write(f'  Trùng mã trên Odoo           : {summary["duplicate_in_odoo"]}')
        self.stdout.write(f'  SP KiotViet thiếu mã         : {summary["no_code"]}')

        show = options.get('show')
        if show:
            self._print_detail(result, show, options.get('limit') or 30)

        csv_path = options.get('csv_path')
        if csv_path:
            self._write_csv(result, csv_path)
            self.stdout.write(self.style.SUCCESS(f'\nĐã xuất chi tiết CSV: {csv_path}'))

        self.stdout.write(self.style.SUCCESS('\nĐối chiếu hoàn tất (không có thay đổi nào ghi lên Odoo).'))

    def _print_detail(self, result, category, limit):
        rows = getattr(result, category, []) or []
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'CHI TIẾT [{category}] — hiển thị {min(limit, len(rows))}/{len(rows)}'
        ))
        for row in rows[:limit]:
            self.stdout.write('  ' + '  '.join(f'{k}={v}' for k, v in row.items()))

    def _write_csv(self, result, path):
        with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
            writer = csv.writer(fh)
            writer.writerow(['category', 'code', 'kiotviet_id', 'odoo_id', 'detail'])
            for category in _CSV_CATEGORIES:
                for row in getattr(result, category, []) or []:
                    detail = {
                        k: v for k, v in row.items()
                        if k not in ('code', 'kiotviet_id', 'odoo_id')
                    }
                    writer.writerow([
                        category,
                        row.get('code', ''),
                        row.get('kiotviet_id', ''),
                        row.get('odoo_id', ''),
                        '; '.join(f'{k}={v}' for k, v in detail.items()),
                    ])
