"""Đối chiếu NPL Portal ↔ Odoo (chỉ đọc).

Khóa: Material.code == product.product.default_code

Usage:
    python manage.py npl_odoo_reconcile
    python manage.py npl_odoo_reconcile --limit 50
    python manage.py npl_odoo_reconcile --show missing_in_odoo --limit 30
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from kho_npl.odoo_bridge import odoo_npl_ready, reconcile_materials

_SHOW = (
    'missing_in_odoo',
    'name_mismatch',
    'price_mismatch',
    'duplicate_in_portal',
    'duplicate_in_odoo',
    'no_code',
    'conflict_demo_or_kv',
    'matched',
)


class Command(BaseCommand):
    help = 'Đối chiếu Material Portal ↔ Odoo theo code=default_code (chỉ đọc).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None, help='Giới hạn số NPL đọc từ Portal.')
        parser.add_argument(
            '--show',
            dest='show',
            choices=_SHOW,
            default=None,
            help='In chi tiết một nhóm kết quả.',
        )
        parser.add_argument(
            '--show-limit',
            type=int,
            default=30,
            help='Số dòng tối đa khi --show (mặc định 30).',
        )

    def handle(self, *args, **options):
        if not odoo_npl_ready():
            self.stderr.write(self.style.ERROR(
                'Odoo chưa cấu hình (ODOO_URL / ODOO_DB / ODOO_API_USER / ODOO_API_PASSWORD).',
            ))
            return

        result = reconcile_materials(limit=options.get('limit'))
        s = result.summary()
        self.stdout.write(self.style.MIGRATE_HEADING('ĐỐI CHIẾU NPL ↔ ODOO'))
        self.stdout.write(f'  Tổng NPL active     : {s["materials_total"]}')
        self.stdout.write(self.style.SUCCESS(f'  Khớp mã             : {s["matched"]}'))
        self.stdout.write(f'  Thiếu trên Odoo     : {s["missing_in_odoo"]}')
        self.stdout.write(f'  Lệch tên            : {s["name_mismatch"]}')
        self.stdout.write(f'  Lệch giá (cost)     : {s["price_mismatch"]}')
        self.stdout.write(f'  Trùng mã Portal     : {s["duplicate_in_portal"]}')
        self.stdout.write(f'  Trùng mã Odoo       : {s["duplicate_in_odoo"]}')
        self.stdout.write(f'  Cảnh báo JP-DEMO    : {s["conflict_demo_or_kv"]}')

        show = options.get('show')
        if show:
            rows = getattr(result, show, []) or []
            self.stdout.write('')
            self.stdout.write(self.style.MIGRATE_HEADING(f'— {show} ({len(rows)}) —'))
            for row in rows[: options['show_limit']]:
                self.stdout.write(f'  {row}')
