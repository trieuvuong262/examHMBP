from django.core.management.base import BaseCommand

from utilities.schedule_push_service import send_schedule_reminder_pushes


class Command(BaseCommand):
    help = 'Gửi web push nhắc lịch đến hạn (cron mỗi phút).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ đếm, không gửi push.',
        )

    def handle(self, *args, **options):
        stats = send_schedule_reminder_pushes(dry_run=options['dry_run'])
        reason = stats.get('reason')
        if reason:
            self.stdout.write(self.style.WARNING(f'Bỏ qua: {reason}'))
        self.stdout.write(
            self.style.SUCCESS(
                f"Push nhắc lịch — gửi: {stats['sent']}, bỏ qua: {stats['skipped']}, lỗi: {stats['failed']}"
                + (' (dry-run)' if options['dry_run'] else ''),
            ),
        )
