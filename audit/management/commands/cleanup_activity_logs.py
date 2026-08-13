"""Xóa nhật ký thao tác cũ hơn N ngày (mặc định 7)."""

from django.core.management.base import BaseCommand

from audit.retention import (
    ACTIVITY_LOG_RETENTION_DAYS,
    PURGE_BATCH_SIZE,
    purge_all_old_activity_logs,
)


class Command(BaseCommand):
    help = 'Xóa nhật ký thao tác cũ hơn số ngày giữ lại (mặc định 7 ngày).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=ACTIVITY_LOG_RETENTION_DAYS,
            help=f'Số ngày giữ lại (mặc định {ACTIVITY_LOG_RETENTION_DAYS}).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ đếm số bản ghi sẽ xóa, không xóa thật.',
        )

    def handle(self, *args, **options):
        from audit.models import UserActivityLog
        from datetime import timedelta

        from django.utils import timezone

        days = max(1, int(options['days']))
        cutoff = timezone.now() - timedelta(days=days)
        pending = UserActivityLog.objects.filter(created_at__lt=cutoff).count()

        if options['dry_run']:
            self.stdout.write(
                f'[dry-run] Would delete {pending} logs older than {days} days.'
            )
            return

        deleted = purge_all_old_activity_logs(days=days, batch_size=PURGE_BATCH_SIZE)
        remaining = UserActivityLog.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {deleted} activity logs older than {days} days '
                f'({remaining} remaining).'
            )
        )
