"""Chuyển SKU nhóm phụ kiện từ Thành phẩm → Hàng hoá."""

from django.core.management.base import BaseCommand
from django.db.models import Q

from kho_san_pham.choices import (
    HANG_HOA_CATEGORY_NAMES,
    PRODUCT_TYPE_HANG_HOA,
    PRODUCT_TYPE_THANH_PHAM,
)
from kho_san_pham.models import Product


class Command(BaseCommand):
    help = (
        'Chuyển SKU có nhóm hàng BĂNG THẤM MÔ HÔI, TÚI ĐỰNG GIÀY, BALO, '
        'NÓN/ MŨ, TẤT VỚ từ Thành phẩm sang Hàng hoá. '
        'Mặc định xem trước; --apply mới ghi.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Ghi DB (mặc định chỉ xem trước).',
        )

    def handle(self, *args, **options):
        apply = bool(options.get('apply'))
        q = Q()
        for name in HANG_HOA_CATEGORY_NAMES:
            q |= Q(category_name__iexact=name)
        qs = Product.objects.filter(q).exclude(product_type=PRODUCT_TYPE_HANG_HOA)
        total = qs.count()
        by_cat = (
            Product.objects.filter(q)
            .values('category_name', 'product_type', 'is_active')
        )
        from collections import Counter
        counts = Counter(
            (row['category_name'], row['product_type'], row['is_active'])
            for row in by_cat
        )
        self.stdout.write('Nhóm hàng mục tiêu:')
        for (cat, ptype, active), n in sorted(counts.items()):
            flag = 'đang dùng' if active else 'ngừng'
            self.stdout.write(f'  {cat!r:24} {ptype:12} {flag:10} n={n}')
        self.stdout.write(f'Sẽ chuyển sang Hàng hoá: {total} SKU')
        if not apply:
            self.stdout.write(self.style.WARNING('Chưa ghi DB — thêm --apply để thực hiện.'))
            return
        updated = qs.update(product_type=PRODUCT_TYPE_HANG_HOA)
        leftover = Product.objects.filter(q, product_type=PRODUCT_TYPE_THANH_PHAM).count()
        self.stdout.write(self.style.SUCCESS(f'Đã chuyển {updated} SKU → Hàng hoá. Còn Thành phẩm: {leftover}.'))
