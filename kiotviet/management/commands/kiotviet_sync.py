"""Đồng bộ mirror KiotViet → PostgreSQL portal (bảng kv_*).

Usage:
    python manage.py kiotviet_sync
    python manage.py kiotviet_sync --full
    python manage.py kiotviet_sync --entity products
    python manage.py kiotviet_sync --entity customers --entity orders
"""

from django.core.management.base import BaseCommand

from kiotviet.client import KiotVietClient
from kiotviet.models import KvSyncConfig
from kiotviet.sync_service import (
    ENTITY_ALL,
    current_retailer,
    refresh_product_images,
    sync_all,
    sync_entity,
)


class Command(BaseCommand):
    help = 'Đồng bộ dữ liệu KiotViet vào database trung gian (kv_*)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--entity',
            action='append',
            dest='entities',
            help=f'Entity cần sync ({", ".join(ENTITY_ALL)}). Lặp lại để chọn nhiều.',
        )
        parser.add_argument(
            '--full',
            action='store_true',
            help='Full sync (bỏ cursor lastModifiedFrom)',
        )
        parser.add_argument(
            '--refresh-images',
            action='store_true',
            help='Quét SP từ API và bổ sung image_urls còn thiếu (không full sync toàn bộ field)',
        )

    def handle(self, *args, **options):
        if not KiotVietClient.is_configured():
            self.stderr.write(self.style.ERROR(
                'KiotViet chưa cấu hình. Đặt KIOTVIET_ENABLED=1 và credentials trong .env.'
            ))
            return

        entities = options.get('entities')
        full = bool(options.get('full'))
        refresh_images = bool(options.get('refresh_images'))

        if refresh_images:
            result = refresh_product_images()
            if result.get('error'):
                self.stderr.write(self.style.ERROR(f'products (images): FAIL — {result["error"]}'))
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'products (images): OK — cập nhật {result.get("upserted", 0)}, '
                        f'bỏ qua {result.get("skipped", 0)}'
                    )
                )
            return

        if not entities:
            retailer = current_retailer()
            if retailer:
                config = KvSyncConfig.get_for_retailer(retailer)
                if config.schedule_enabled:
                    entities = list(config.enabled_entities or ENTITY_ALL)

        if entities:
            results = [sync_entity(e, full=full) for e in entities]
        else:
            results = sync_all(full=full)

        has_error = False
        for row in results:
            entity = row.get('entity', '?')
            if row.get('error'):
                has_error = True
                self.stderr.write(self.style.ERROR(f'{entity}: FAIL — {row["error"]}'))
            else:
                upserted = row.get('upserted', row.get('rows', 0))
                skipped = row.get('skipped', 0)
                self.stdout.write(
                    f'{entity}: OK — cập nhật {upserted}, bỏ qua {skipped}, '
                    f'xóa {row.get("removed", 0)}, '
                    f'tổng mirror {row.get("records", 0)}'
                )

        if has_error:
            self.stderr.write(self.style.WARNING('Một số entity sync thất bại.'))
        else:
            self.stdout.write(self.style.SUCCESS('Sync hoàn tất.'))
