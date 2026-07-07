"""Đẩy sản phẩm KiotViet → Odoo (Giai đoạn 2, một chiều, idempotent).

An toàn: mặc định --dry-run (chỉ in kế hoạch, KHÔNG ghi Odoo).
Muốn ghi thật phải thêm --apply.

Usage:
    # Xem trước sẽ tạo gì (không ghi Odoo)
    python manage.py kiotviet_odoo_push

    # Chạy thử 20 SP đầu (ghi thật, kèm tồn kho)
    python manage.py kiotviet_odoo_push --apply --limit 20

    # Đẩy toàn bộ, KHÔNG đụng tồn kho
    python manage.py kiotviet_odoo_push --apply --no-stock

    # Chỉ tồn kho từ vài chi nhánh
    python manage.py kiotviet_odoo_push --apply --branch 38644 --branch 69185
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from kiotviet.client import KiotVietClient
from kiotviet.odoo_bridge import odoo_ready, push_products


class Command(BaseCommand):
    help = 'Đẩy danh mục + sản phẩm (+ tồn kho) KiotViet → Odoo. Mặc định dry-run.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Ghi thật lên Odoo (mặc định chỉ dry-run).')
        parser.add_argument('--retailer', default=None,
                            help='Retailer KiotViet (mặc định KIOTVIET_RETAILER).')
        parser.add_argument('--limit', type=int, default=None,
                            help='Chỉ xử lý N sản phẩm đầu (để test).')
        parser.add_argument('--no-stock', dest='with_stock', action='store_false',
                            help='Không đẩy tồn kho, chỉ danh mục + sản phẩm.')
        parser.add_argument('--no-update', dest='update_existing', action='store_false',
                            help='Bỏ qua SP đã có trên Odoo (không cập nhật giá/tên).')
        parser.add_argument('--branch', action='append', dest='branches', type=int,
                            help='Chỉ đẩy tồn từ branch_kiotviet_id này (lặp lại được).')
        parser.add_argument('--type', dest='product_type', choices=['storable', 'consu'],
                            default='storable', help='Loại SP tạo trên Odoo.')

    def handle(self, *args, **options):
        if not KiotVietClient.is_configured():
            self.stderr.write(self.style.ERROR('KiotViet chưa cấu hình.'))
            return
        if not odoo_ready():
            self.stderr.write(self.style.ERROR('Odoo chưa cấu hình (ODOO_URL/DB/API_USER/PASSWORD).'))
            return

        apply = bool(options.get('apply'))
        dry_run = not apply

        if dry_run:
            self.stdout.write(self.style.WARNING('CHẾ ĐỘ DRY-RUN — không ghi gì lên Odoo (thêm --apply để ghi thật).'))
        else:
            self.stdout.write(self.style.MIGRATE_HEADING('CHẾ ĐỘ GHI THẬT (--apply) → sẽ tạo/cập nhật dữ liệu Odoo.'))

        result = push_products(
            retailer=options.get('retailer'),
            dry_run=dry_run,
            limit=options.get('limit'),
            with_stock=options.get('with_stock', True),
            update_existing=options.get('update_existing', True),
            branch_filter=options.get('branches'),
            product_type=options.get('product_type', 'storable'),
            progress=lambda m, p=None: self.stdout.write(f'  … {m}'),
        )

        s = result.summary()
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(f'KẾT QUẢ ĐẨY (retailer={result.retailer or "-"})'))
        self.stdout.write(f'  Kho tạo mới          : {s["warehouses_created"]}')
        self.stdout.write(f'  Danh mục tạo mới     : {s["categories_created"]}')
        self.stdout.write(f'  Tổng SP xử lý        : {s["products_total"]}')
        self.stdout.write(self.style.SUCCESS(f'  SP tạo mới           : {s["products_created"]}'))
        self.stdout.write(f'  SP cập nhật          : {s["products_updated"]}')
        self.stdout.write(f'  SP bỏ qua            : {s["products_skipped"]}')
        self.stdout.write(f'  Dòng tồn kho đã set  : {s["stock_applied"]}')
        if s['products_failed']:
            self.stdout.write(self.style.ERROR(f'  SP lỗi               : {s["products_failed"]}'))
            for row in result.products_failed[:10]:
                self.stdout.write(f'      - {row.get("code")}: {row.get("error")}')
        if s['stock_failed']:
            self.stdout.write(self.style.ERROR(f'  Tồn kho lỗi          : {s["stock_failed"]}'))
            for row in result.stock_failed[:10]:
                self.stdout.write(f'      - {row.get("code")} @branch {row.get("branch")}: {row.get("error")}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry-run xong. Chạy lại với --apply --limit 20 để test ghi thật.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nĐẩy hoàn tất.'))
