"""Đồng bộ cây nhóm NPL 2 cấp — dùng cho demo / VPS."""

from django.core.management.base import BaseCommand

from kho_npl.material_category_catalog import sync_material_category_catalog


class Command(BaseCommand):
    help = 'Tạo/cập nhật nhóm nguyên phụ liệu 2 cấp (cha + con) và gán NPL vào nhóm cấp 2.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tree-only',
            action='store_true',
            help='Chỉ đồng bộ cây nhóm, không gán lại NPL.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Gán lại cả NPL đã có nhóm cấp 2 (suy luận lại từ tên).',
        )

    def handle(self, *args, **options):
        tree_only: bool = options['tree_only']
        force: bool = options['force']

        if tree_only:
            from kho_npl.category_tree import ensure_material_category_tree
            ensure_material_category_tree()
            self.stdout.write(self.style.SUCCESS('Đã đồng bộ nhóm NPL 2 cấp.'))
            return

        if force:
            from kho_npl.material_category_catalog import backfill_material_categories, deactivate_empty_legacy_roots
            from kho_npl.category_tree import ensure_material_category_tree

            ensure_material_category_tree()
            assigned, skipped = backfill_material_categories(only_without_parent=False)
            deactivated = deactivate_empty_legacy_roots()
            self.stdout.write(f'  Gán nhóm cấp 2: {assigned} | Bỏ qua: {skipped} | Ẩn nhóm cũ: {deactivated}')
            self.stdout.write(self.style.SUCCESS('Đã đồng bộ và gán lại nhóm NPL.'))
            return

        stats = sync_material_category_catalog(backfill=True)
        self.stdout.write(
            f'  Nhóm cấp 1: {stats["roots"]} | Nhóm cấp 2: {stats["leaves"]}'
        )
        self.stdout.write(
            f'  Gán NPL: {stats["assigned"]} | Bỏ qua: {stats["skipped"]} | '
            f'Ẩn nhóm cũ: {stats["deactivated_legacy"]}'
        )
        self.stdout.write(
            f'  NPL active có nhóm cấp 1+2: {stats["materials_with_parent"]}/{stats["materials_active"]}'
        )
        self.stdout.write(self.style.SUCCESS('Đã đồng bộ nhóm NPL 2 cấp và danh mục.'))
