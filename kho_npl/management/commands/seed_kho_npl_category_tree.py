"""Đồng bộ danh mục nhóm NPL một cấp — dùng cho demo / VPS."""

from django.core.management.base import BaseCommand

from kho_npl.material_category_catalog import sync_material_category_catalog


class Command(BaseCommand):
    help = 'Tạo/cập nhật danh mục nhóm nguyên phụ liệu một cấp.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tree-only',
            action='store_true',
            help='Tùy chọn tương thích cũ; chỉ đồng bộ danh mục nhóm.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Tùy chọn tương thích cũ; đồng bộ lại danh mục nhóm.',
        )

    def handle(self, *args, **options):
        tree_only: bool = options['tree_only']
        if tree_only:
            from kho_npl.category_tree import ensure_material_category_tree
            ensure_material_category_tree()
            self.stdout.write(self.style.SUCCESS('Đã đồng bộ nhóm NPL một cấp.'))
            return

        stats = sync_material_category_catalog(backfill=True)
        self.stdout.write(f'  Nhóm đang dùng: {stats["roots"]}')
        self.stdout.write(f'  NPL đang hoạt động: {stats["materials_active"]}')
        self.stdout.write(self.style.SUCCESS('Đã đồng bộ nhóm NPL một cấp.'))
