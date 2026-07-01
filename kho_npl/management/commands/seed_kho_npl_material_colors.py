"""Đồng bộ màu NPL và gán màu cho danh mục thiếu."""

from django.core.management.base import BaseCommand

from kho_npl.material_color_catalog import backfill_material_colors, ensure_material_colors
from kho_npl.models import Material, MaterialColor


class Command(BaseCommand):
    help = 'Đồng bộ bảng màu NPL và gán màu cho NPL chưa có (suy luận từ tên/mã).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Gán lại màu cho tất cả NPL (không chỉ NPL thiếu màu).',
        )
        parser.add_argument(
            '--colors-only',
            action='store_true',
            help='Chỉ đồng bộ bảng màu, không gán NPL.',
        )

    def handle(self, *args, **options):
        force: bool = options['force']
        colors_only: bool = options['colors_only']

        synced = ensure_material_colors()
        active_colors = MaterialColor.objects.filter(is_active=True).count()
        self.stdout.write(f'  Màu master: {synced} định nghĩa, {active_colors} đang active')

        if colors_only:
            self.stdout.write(self.style.SUCCESS('Đã đồng bộ bảng màu NPL.'))
            return

        assigned, skipped = backfill_material_colors(only_missing=not force)
        with_color = Material.objects.filter(is_active=True, color__isnull=False).count()
        active_total = Material.objects.filter(is_active=True).count()
        self.stdout.write(f'  Gán màu: {assigned} NPL | Bỏ qua: {skipped}')
        self.stdout.write(f'  Danh mục active có màu: {with_color}/{active_total}')
        self.stdout.write(self.style.SUCCESS('Đã cập nhật màu sắc danh mục NPL.'))
