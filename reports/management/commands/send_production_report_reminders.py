from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date

from reports.production_report_reminders import auto_submit_unsubmitted_production_reports


class Command(BaseCommand):
    help = (
        'Tự động gửi báo cáo SX ca sáng chưa nộp (trừ ca tối) theo giờ trong '
        'Thiết lập chung báo cáo — ngày báo cáo = hôm nay, thời gian làm việc mặc định 9,50 giờ. '
        'Có thể chạy tay theo --date hoặc khoảng --until / --from.'
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
            help='Chạy ngoài khung giờ tự nộp (dùng khi chạy tay).',
        )
        parser.add_argument(
            '--date',
            dest='report_date',
            default='',
            help='Một ngày báo cáo YYYY-MM-DD (mặc định cron: hôm nay).',
        )
        parser.add_argument(
            '--from',
            dest='date_from',
            default='',
            help='Đầu khoảng YYYY-MM-DD (dùng với --until hoặc một mình).',
        )
        parser.add_argument(
            '--until',
            dest='date_to',
            default='',
            help='Cuối khoảng YYYY-MM-DD — gửi mọi BC chưa nộp đến hết ngày này.',
        )

    def handle(self, *args, **options):
        report_date = parse_date((options.get('report_date') or '').strip()) or None
        date_from = parse_date((options.get('date_from') or '').strip()) or None
        date_to = parse_date((options.get('date_to') or '').strip()) or None
        range_mode = bool(date_from or date_to) and report_date is None
        stats = auto_submit_unsubmitted_production_reports(
            dry_run=options['dry_run'],
            force=options['force'] or bool(report_date) or range_mode,
            report_date=report_date,
            date_from=date_from,
            date_to=date_to,
        )
        reason = stats.get('reason')
        if reason:
            self.stdout.write(self.style.WARNING(f'Bỏ qua: {reason}'))
            return

        skip_reasons = stats.get('skip_reasons') or {}
        extra = ''
        if skip_reasons:
            extra = ' | skip: ' + ', '.join(f'{k}={v}' for k, v in sorted(skip_reasons.items()))
        dates = stats.get('dates') or []
        if len(dates) > 1:
            extra += f' | ngày có BC: {len(dates)}'

        self.stdout.write(
            self.style.SUCCESS(
                f"Auto-submit BC SX {stats.get('report_date')} — "
                f"gửi: {stats['submitted']}, bỏ qua: {stats['skipped']}, lỗi: {stats['failed']}"
                + extra
                + (' (dry-run)' if options['dry_run'] else '')
            ),
        )
