"""Đồng bộ vị trí lắp máy thiết bị sản xuất → 19 Chiến Lược | 152A đường 6A."""

from django.core.management.base import BaseCommand

from equipment.models import Device
from equipment.production_locations import normalize_usage_room
from equipment.scope import SCOPE_PRODUCTION, filter_devices_for_scope


class Command(BaseCommand):
    help = 'Chuan hoa usage_room thiet bi san xuat ve 19 Chien Luoc hoac 152A duong 6A.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Ghi DB (mặc định chỉ xem trước).',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        qs = filter_devices_for_scope(Device.objects.all(), SCOPE_PRODUCTION)
        updated = 0
        skipped = 0
        unmapped: dict[str, int] = {}

        for device in qs.iterator():
            raw = (device.usage_room or '').strip()
            if not raw:
                skipped += 1
                continue
            canonical = normalize_usage_room(raw)
            if not canonical:
                unmapped[raw] = unmapped.get(raw, 0) + 1
                continue
            if raw == canonical:
                skipped += 1
                continue
            if apply:
                device.usage_room = canonical
                device.save(update_fields=['usage_room', 'updated_at'])
            updated += 1
            self.stdout.write(f'  {device.device_code}: "{raw}" -> "{canonical}"')

        mode = 'ĐÃ CẬP NHẬT' if apply else 'XEM TRƯỚC'
        self.stdout.write(self.style.SUCCESS(f'\n{mode}: {updated} thiết bị'))
        self.stdout.write(f'Bỏ qua (trống hoặc đã chuẩn): {skipped}')

        if unmapped:
            self.stdout.write(self.style.WARNING('\nKhông map được (cần xử lý thủ công):'))
            for raw, count in sorted(unmapped.items(), key=lambda x: (-x[1], x[0])):
                self.stdout.write(f'  [{count}] {raw}')

        if not apply and updated:
            self.stdout.write(self.style.NOTICE('\nChạy lại với --apply để ghi DB.'))
