"""Dựng lại `SxSku` từ danh mục kho sản phẩm đã chuẩn hóa từ vựng.

Nguồn sự thật là `kho_sp_product`: mỗi thành phẩm đang dùng sinh đúng một SKU, với
`sku_code` giữ nguyên `Product.code` theo quy ước sẵn có của `get_or_create_sku`.
SKU cũ không khớp sản phẩm nào thì đánh `is_active=False` chứ không xóa, để còn truy vết.

Mặc định chỉ xem trước. Thêm ``--apply`` để ghi DB.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from kho_san_pham.choices import PRODUCT_TYPE_THANH_PHAM
from kho_san_pham.models import Product
from san_xuat.hub_models import SxColor, SxSize, SxSku

RETIRE_NOTE = 'Ngừng dùng: dựng lại SKU từ danh mục kho sản phẩm.'
_SAMPLE = 10


class Command(BaseCommand):
    help = (
        'Dựng lại danh mục SKU sản xuất từ kho sản phẩm đang dùng. '
        'Mặc định xem trước; dùng --apply để ghi DB.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Ghi DB (mặc định chỉ xem trước).',
        )

    def handle(self, *args, **options):
        self.apply = options['apply']
        with transaction.atomic():
            self._rebuild()
            if not self.apply:
                transaction.set_rollback(True)
        self._report()

    def _rebuild(self):
        color_names = {row.code: row.name for row in SxColor.objects.all()}
        known_sizes = set(SxSize.objects.values_list('code', flat=True))

        existing = list(SxSku.objects.all())
        by_key = {self._key(r.style_code, r.color_code, r.size_label, r.gender): r for r in existing}
        by_sku_code = {(r.sku_code or '').upper(): r for r in existing}

        self.created = 0
        self.updated = 0
        self.linked = 0
        self.conflicts: list[str] = []
        self.unknown_size: dict[str, int] = {}
        matched_ids: set[int] = set()

        products = (
            Product.objects
            .filter(is_active=True, product_type=PRODUCT_TYPE_THANH_PHAM)
            .order_by('code')
        )

        for product in products.iterator(chunk_size=1000):
            key = self._key(product.style_code, product.color_code, product.size_label, product.gender)
            if product.size_label not in known_sizes:
                self.unknown_size[product.size_label] = self.unknown_size.get(product.size_label, 0) + 1
            label = (color_names.get(product.color_code) or product.color_label)[:80]

            row = by_key.get(key)
            is_new = row is None
            if is_new:
                clash = by_sku_code.get((product.code or '').upper())
                if clash is not None:
                    self.conflicts.append(
                        f'{product.code}: mã SKU đã thuộc định danh khác '
                        f'({clash.style_code}/{clash.color_code}/{clash.size_label}/{clash.gender or "-"})'
                    )
                    continue
                row = SxSku(
                    style_code=product.style_code,
                    style_name=product.name[:255],
                    color_code=product.color_code,
                    color_label=label,
                    size_label=product.size_label,
                    gender=product.gender,
                    sku_code=product.code,
                    is_active=True,
                    is_demo=False,
                )
                if self.apply:
                    row.save()
                self.created += 1
                by_key[key] = row
                by_sku_code[(product.code or '').upper()] = row
            else:
                matched_ids.add(row.pk)
                changes = []
                if row.sku_code != product.code and (product.code or '').upper() not in by_sku_code:
                    by_sku_code.pop((row.sku_code or '').upper(), None)
                    row.sku_code = product.code
                    by_sku_code[(product.code or '').upper()] = row
                    changes.append('sku_code')
                if row.style_name != product.name[:255]:
                    row.style_name = product.name[:255]
                    changes.append('style_name')
                if row.color_label != label:
                    row.color_label = label
                    changes.append('color_label')
                if not row.is_active:
                    row.is_active = True
                    changes.append('is_active')
                if changes:
                    if self.apply:
                        row.save(update_fields=changes)
                    self.updated += 1

            if is_new or product.sx_sku_id != row.pk:
                self.linked += 1
                if self.apply:
                    product.sx_sku = row
                    product.save(update_fields=['sx_sku', 'updated_at'])

        self.retired: list[str] = []
        for row in existing:
            if row.pk in matched_ids or not row.is_active:
                continue
            row.is_active = False
            fields = ['is_active']
            if not row.notes:
                row.notes = RETIRE_NOTE
                fields.append('notes')
            if self.apply:
                row.save(update_fields=fields)
            self.retired.append(row.sku_code)

    @staticmethod
    def _key(style: str, color: str, size: str, gender: str) -> tuple[str, str, str, str]:
        return (style or '').upper(), (color or '').upper(), (size or '').upper(), (gender or '').upper()

    def _report(self):
        out = self.stdout
        mode = 'ĐÃ GHI DB' if self.apply else 'XEM TRƯỚC (chưa ghi gì)'
        out.write(self.style.MIGRATE_HEADING(f'\n=== {mode} ==='))
        out.write(f'  SKU sinh mới: {self.created}')
        out.write(f'  SKU cập nhật: {self.updated}')
        out.write(f'  Nối sản phẩm → SKU: {self.linked}')
        out.write(f'  SKU cũ ngừng dùng: {len(self.retired)}')

        if self.retired:
            sample = ', '.join(self.retired[:_SAMPLE])
            more = f' … (+{len(self.retired) - _SAMPLE})' if len(self.retired) > _SAMPLE else ''
            out.write(f'      {sample}{more}')

        if self.unknown_size:
            out.write(self.style.WARNING('\nSize chưa có trong danh mục:'))
            for size, count in sorted(self.unknown_size.items(), key=lambda x: -x[1]):
                out.write(f'  [{count}] {size}')

        if self.conflicts:
            out.write(self.style.ERROR(f'\nXung đột mã SKU: {len(self.conflicts)}'))
            for line in self.conflicts[:_SAMPLE]:
                out.write(f'  - {line}')

        if not self.apply:
            out.write(self.style.NOTICE('\nChạy lại với --apply để ghi DB.'))
