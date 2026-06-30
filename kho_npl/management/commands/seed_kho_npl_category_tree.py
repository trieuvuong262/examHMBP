"""Đồng bộ cây nhóm NPL 2 cấp — dùng cho demo / VPS."""

from django.core.management.base import BaseCommand

from kho_npl.category_tree import ensure_material_category_tree


class Command(BaseCommand):
    help = 'Tạo/cập nhật nhóm nguyên phụ liệu 2 cấp (cha + con).'

    def handle(self, *args, **options):
        ensure_material_category_tree()
        self.stdout.write(self.style.SUCCESS('Đã đồng bộ nhóm NPL 2 cấp.'))
