"""Đẩy NPL Portal → Odoo (một chiều, idempotent).

Mặc định dry-run — thêm --apply để ghi thật.

Usage:
    python manage.py npl_odoo_push
    python manage.py npl_odoo_push --apply --limit 20
    python manage.py npl_odoo_push --apply --no-stock
    python manage.py npl_odoo_push --apply --codes JP-VAI-COT180-WHT --codes JP-CHI-PES40-WHT
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from kho_npl.odoo_bridge import odoo_npl_ready, push_materials


class Command(BaseCommand):
    help = 'Đẩy danh mục + NPL (+ tồn) kho_npl → Odoo. Mặc định dry-run.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Ghi thật lên Odoo (mặc định chỉ dry-run).',
        )
        parser.add_argument('--limit', type=int, default=None, help='Chỉ xử lý N mã đầu.')
        parser.add_argument(
            '--no-stock',
            dest='with_stock',
            action='store_false',
            help='Không đẩy tồn kho.',
        )
        parser.add_argument(
            '--no-update',
            dest='update_existing',
            action='store_false',
            help='Bỏ qua NPL đã có trên Odoo.',
        )
        parser.add_argument(
            '--codes',
            action='append',
            dest='codes',
            help='Chỉ đẩy các mã này (lặp lại được).',
        )

    def handle(self, *args, **options):
        if not odoo_npl_ready():
            self.stderr.write(self.style.ERROR(
                'Odoo chưa cấu hình (ODOO_URL / ODOO_DB / ODOO_API_USER / ODOO_API_PASSWORD).',
            ))
            return

        apply = bool(options.get('apply'))
        dry_run = not apply
        if dry_run:
            self.stdout.write(self.style.WARNING(
                'CHẾ ĐỘ DRY-RUN — không ghi Odoo (thêm --apply để ghi thật).',
            ))
        else:
            self.stdout.write(self.style.MIGRATE_HEADING(
                'CHẾ ĐỘ GHI THẬT (--apply) → tạo/cập nhật Odoo.',
            ))

        codes = set(options.get('codes') or []) or None
        result = push_materials(
            dry_run=dry_run,
            limit=options.get('limit'),
            codes=codes,
            with_stock=options.get('with_stock', True),
            update_existing=options.get('update_existing', True),
            progress=lambda m, p=None: self.stdout.write(f'  … {m}'),
        )

        s = result.summary()
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('KẾT QUẢ ĐẨY NPL → ODOO'))
        self.stdout.write(f'  Danh mục tạo mới     : {s["categories_created"]}')
        self.stdout.write(f'  Warehouse tạo mới    : {s["warehouse_created"]}')
        self.stdout.write(f'  Vị trí tạo mới       : {s["locations_created"]}')
        self.stdout.write(f'  NCC tạo mới          : {s["suppliers_created"]}')
        self.stdout.write(f'  NCC cập nhật         : {s["suppliers_updated"]}')
        self.stdout.write(f'  Vendor gắn product   : {s["vendors_linked"]}')
        self.stdout.write(f'  Tổng NPL xử lý       : {s["materials_total"]}')
        self.stdout.write(self.style.SUCCESS(f'  NPL tạo mới          : {s["materials_created"]}'))
        self.stdout.write(f'  NPL cập nhật         : {s["materials_updated"]}')
        self.stdout.write(f'  NPL bỏ qua           : {s["materials_skipped"]}')
        self.stdout.write(f'  Dòng tồn đã set      : {s["stock_applied"]}')
        if s['materials_failed']:
            self.stdout.write(self.style.ERROR(f'  NPL lỗi              : {s["materials_failed"]}'))
            for row in result.materials_failed[:10]:
                self.stdout.write(f'      - {row.get("code")}: {row.get("error")}')
        if s['stock_failed']:
            self.stdout.write(self.style.ERROR(f'  Tồn kho lỗi          : {s["stock_failed"]}'))
            for row in result.stock_failed[:10]:
                self.stdout.write(f'      - {row}')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\nDry-run xong. Full push: python manage.py npl_odoo_push --apply',
            ))
        else:
            self.stdout.write(self.style.SUCCESS('\nĐẩy NPL hoàn tất.'))
            self.stdout.write(
                'Tiếp: python manage.py npl_odoo_reconcile  (thiếu trên Odoo ≈ 0)',
            )
