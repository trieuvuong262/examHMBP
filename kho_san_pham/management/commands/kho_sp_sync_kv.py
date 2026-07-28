from django.core.management.base import BaseCommand

from kho_san_pham.services.sync_from_kiotviet import sync_thanh_pham_from_kiotviet


class Command(BaseCommand):
    help = 'Đồng bộ thành phẩm 1 chiều từ mirror KiotViet (kv_product) → kho sản phẩm'

    def add_arguments(self, parser):
        parser.add_argument(
            '--deactivate-missing',
            action='store_true',
            help='Ngừng dùng thành phẩm sync KV không còn trên mirror',
        )

    def handle(self, *args, **options):
        result = sync_thanh_pham_from_kiotviet(
            deactivate_missing=bool(options.get('deactivate_missing')),
        )
        if result.errors and not (result.created or result.updated):
            self.stderr.write(self.style.ERROR(result.summary()))
            for err in result.errors[:10]:
                self.stderr.write(f'  - {err}')
            return
        self.stdout.write(self.style.SUCCESS(result.summary()))
        for err in result.errors[:10]:
            self.stderr.write(self.style.WARNING(f'  - {err}'))
