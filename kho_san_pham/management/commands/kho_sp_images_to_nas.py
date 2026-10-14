"""Dời ảnh thư viện còn nằm trên VPS (kho_sp/products) sang NAS.

File mới đã ghi thẳng lên ``06_RnD_THIET_KE_SAN_PHAM/0.Portal``. Lệnh này chỉ
xử lý ảnh cũ. NAS mất kết nối thì bản sao nằm tạm trên VPS và được đồng bộ sau.
"""

from pathlib import Path

from django.conf import settings
from django.core.files.base import File
from django.core.management.base import BaseCommand

from kho_san_pham.models import Product, product_image_upload_to
from san_xuat.design_nas_storage import DesignDocNasStorage, is_legacy_media_path


class Command(BaseCommand):
    help = 'Dời ảnh sản phẩm còn nằm trên VPS sang thư mục NAS 06_RnD_THIET_KE_SAN_PHAM/0.Portal.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Chỉ liệt kê, không ghi NAS / không đổi DB.')

    def _out(self, text, *, warn=False):
        text = str(text)
        style = self.style.WARNING if warn else None
        try:
            self.stdout.write(style(text) if style else text)
        except UnicodeEncodeError:
            safe = text.encode('ascii', 'replace').decode('ascii')
            self.stdout.write(style(safe) if style else safe)

    def handle(self, *args, **options):
        dry = options['dry_run']
        storage = DesignDocNasStorage()
        moved = missing = 0
        for product in Product.objects.exclude(image='').iterator():
            name = (product.image.name or '').replace('\\', '/')
            if not is_legacy_media_path(name):
                continue
            src = Path(settings.MEDIA_ROOT) / name
            try:
                exists = src.is_file()
            except OSError:
                exists = False
            if not exists:
                missing += 1
                self._out(f'  thiếu file: {product.pk} {name}', warn=True)
                continue
            if dry:
                self._out(f'  {product.pk} {name}')
                moved += 1
                continue
            with src.open('rb') as handle:
                new_name = storage.save(product_image_upload_to(product, src.name), File(handle))
            product.image.name = new_name
            product.save(update_fields=['image'])
            try:
                src.unlink(missing_ok=True)
            except OSError:
                pass
            moved += 1
            self._out(f'  {product.pk} -> {new_name}')
        verb = 'sẽ dời' if dry else 'đã dời'
        self._out(f'{verb} {moved}, thiếu {missing}.')
