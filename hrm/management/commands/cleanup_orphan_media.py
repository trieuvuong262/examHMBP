from django.core.management.base import BaseCommand

from hrm.media_cleanup import cleanup_orphan_media


class Command(BaseCommand):
    help = 'Xóa file trong media/ không còn được model hoặc nội dung HTML tham chiếu.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ liệt kê file sẽ xóa, không xóa thật.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        result = cleanup_orphan_media(dry_run=dry_run)

        freed_mb = result['freed_bytes'] / (1024 * 1024)
        prefix = '[dry-run] ' if dry_run else ''
        self.stdout.write(
            f"{prefix}Referenced: {result['referenced_count']} · "
            f"Orphans: {result['orphan_count']} · "
            f"{'Would remove' if dry_run else 'Removed'}: {result['removed_count']} "
            f"({freed_mb:.2f} MB)"
        )

        if dry_run and result['orphan_count']:
            self.stdout.write(self.style.WARNING('Run again without --dry-run to delete.'))
