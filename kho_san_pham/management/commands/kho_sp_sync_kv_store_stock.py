"""Đồng bộ tồn cửa hàng (CH-TRUNG-TAM) từ mirror KiotViet.

Mặc định xem trước. Thêm ``--apply`` để ghi sổ.

    manage.py kho_sp_sync_kv_store_stock
    manage.py kho_sp_sync_kv_store_stock --apply
"""

from django.core.management.base import BaseCommand

from kho_san_pham.services.sync_store_stock import sync_store_stock_from_kiotviet


class Command(BaseCommand):
    help = (
        'Bám tồn cửa hàng Portal theo tồn KiotViet (chi nhánh bán, không gồm xưởng). '
        'Mặc định xem trước; --apply mới ghi.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Ghi sổ CH-TRUNG-TAM. Không có cờ này thì chỉ xem trước.',
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get('apply'))
        result = sync_store_stock_from_kiotviet(apply=apply_changes)
        if result.errors and not result.applied and not result.pending:
            for err in result.errors:
                self.stderr.write(self.style.ERROR(err))
            return

        self.stdout.write(f'Chi nhánh KV (cửa hàng): {", ".join(result.branches) or "—"}')
        self.stdout.write(f'SKU có mã KV:            {result.matched}')
        self.stdout.write(f'Khớp sổ, không ghi:      {result.unchanged}')
        self.stdout.write(f'Lệch, cần ghi:           {result.pending}')
        self.stdout.write(f'Tổng tồn KV cửa hàng:    {result.total_kv}')
        if result.skipped_no_kv_id:
            self.stdout.write(f'SKU không có mã KV:      {result.skipped_no_kv_id}')

        if not apply_changes:
            self.stdout.write(self.style.WARNING('\nXem trước — chưa ghi gì. Thêm --apply để ghi DB.'))
            return

        self.stdout.write(self.style.SUCCESS(f'\nĐã ghi {result.applied} SKU. {result.summary()}'))
        for err in result.errors[:20]:
            self.stderr.write(self.style.WARNING(f'  - {err}'))
