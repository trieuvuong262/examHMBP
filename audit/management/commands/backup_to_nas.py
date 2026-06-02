"""Backup database + source lên NAS — dùng cho cron hàng ngày."""

from django.core.management.base import BaseCommand

from audit.portal_backup import PortalBackupError, run_portal_backup


class Command(BaseCommand):
    help = 'Backup PostgreSQL, mã nguồn và media lên NAS (rclone).'

    def handle(self, *args, **options):
        try:
            manifest = run_portal_backup(trigger='scheduled')
        except PortalBackupError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            raise SystemExit(1) from exc
        remote = manifest.get('remote_path', '')
        count = len(manifest.get('artifacts', []))
        self.stdout.write(self.style.SUCCESS(f'Backup xong: {remote} ({count} file)'))
