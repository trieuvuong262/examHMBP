"""Đẩy ảnh sản phẩm KiotViet → Odoo (image_1920).

Tải ảnh đầu tiên của mỗi SP từ CDN KiotViet, nạp vào product.template.image_1920.
Idempotent: mặc định bỏ qua SP đã có ảnh trên Odoo (--all để ghi đè tất cả).

Usage:
    python manage.py kiotviet_odoo_images
    python manage.py kiotviet_odoo_images --limit 50
    python manage.py kiotviet_odoo_images --all      # ghi đè cả SP đã có ảnh
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from kiotviet.client import KiotVietClient
from kiotviet.odoo_bridge import odoo_ready, push_images


class Command(BaseCommand):
    help = 'Đẩy ảnh sản phẩm KiotViet → Odoo (image_1920).'

    def add_arguments(self, parser):
        parser.add_argument('--retailer', default=None)
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--all', dest='all', action='store_true',
                            help='Ghi đè cả SP đã có ảnh (mặc định chỉ SP thiếu ảnh).')

    def handle(self, *args, **options):
        if not KiotVietClient.is_configured():
            self.stderr.write(self.style.ERROR('KiotViet chưa cấu hình.'))
            return
        if not odoo_ready():
            self.stderr.write(self.style.ERROR('Odoo chưa cấu hình.'))
            return

        result = push_images(
            retailer=options.get('retailer'),
            limit=options.get('limit'),
            only_missing=not options.get('all'),
            progress=lambda m, p=None: self.stdout.write(f'  … {m}'),
        )
        s = result.summary()
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(f'KẾT QUẢ ĐẨY ẢNH (retailer={result.retailer or "-"})'))
        self.stdout.write(f'  SP có ảnh (xử lý)   : {s["products_total"]}')
        self.stdout.write(self.style.SUCCESS(f'  Ảnh đã đặt          : {s["images_set"]}'))
        self.stdout.write(f'  Bỏ qua (đã có ảnh)  : {s["images_skipped"]}')
        if s['images_failed']:
            self.stdout.write(self.style.ERROR(f'  Lỗi                 : {s["images_failed"]}'))
            for row in result.images_failed[:10]:
                self.stdout.write(f'      - {row.get("code")}: {row.get("error")}')
        self.stdout.write(self.style.SUCCESS('\nĐẩy ảnh hoàn tất.'))
