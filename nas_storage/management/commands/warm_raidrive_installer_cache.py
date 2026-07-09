from django.core.management.base import BaseCommand

from nas_storage.raidrive_installer_cache import warm_raidrive_installer_cache


class Command(BaseCommand):
    help = 'Đồng bộ file cài RaiDrive từ NAS vào cache đĩa VPS (tăng tốc tải cho user).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Ghi đè cache dù metadata chưa đổi.',
        )

    def handle(self, *args, **options):
        path = warm_raidrive_installer_cache(force=options['force'])
        size_mb = path.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(f'OK: {path} ({size_mb:.1f} MB)'))
