from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date

from reports.production_report_reminders import auto_submit_unsubmitted_production_reports


class Command(BaseCommand):
    help = (
        'Tự động gửi báo cáo SX chưa nộp (trừ ca tối) lúc 11:30 — '
        'ngày báo cáo = hôm qua, thời gian làm việc mặc định 9,50 giờ.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ đếm/kiểm tra, không ghi DB.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Chạy ngoài khung 11:30 (dùng khi chạy tay).',
        )
        parser.add_argument(
            '--date',
            dest='report_date',
            default='',
            help='Ngày báo cáo YYYY-MM-DD (mặc định: hôm qua).',
        )

    def handle(self, *args, **options):
        report_date = parse_date((options.get('report_date') or '').strip()) or None
        stats = auto_submit_unsubmitted_production_reports(
            dry_run=options['dry_run'],
            force=options['force'] or bool(report_date),
            report_date=report_date,
        )
        reason = stats.get('reason')
        if reason:
            self.stdout.write(self.style.WARNING(f'Bỏ qua: {reason}'))
            return

        skip_reasons = stats.get('skip_reasons') or {}
        extra = ''
        if skip_reasons:
            extra = ' | skip: ' + ', '.join(f'{k}={v}' for k, v in sorted(skip_reasons.items()))

        self.stdout.write(
            self.style.SUCCESS(
                f"Auto-submit BC SX {stats.get('report_date')} — "
                f"gửi: {stats['submitted']}, bỏ qua: {stats['skipped']}, lỗi: {stats['failed']}"
                + extra
                + (' (dry-run)' if options['dry_run'] else '')
            ),
        )
