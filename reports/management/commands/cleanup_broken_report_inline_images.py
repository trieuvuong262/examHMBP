"""Gỡ ảnh inline CKEditor (reports/ckeditor5/...) đã mất file khỏi document_html."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from reports.models import DailyWorkReport
from reports.office_content import (
    CKEDITOR_INLINE_PREFIX,
    remove_missing_ckeditor_inline_images,
)


class Command(BaseCommand):
    help = 'Xóa thẻ img trỏ tới ảnh CKEditor cũ (reports/ckeditor5/) khi file không còn.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ liệt kê, không ghi DB.',
        )
        parser.add_argument(
            '--report-id',
            type=int,
            action='append',
            dest='report_ids',
            help='Chỉ xử lý báo cáo theo pk (có thể lặp).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        report_ids = options.get('report_ids')

        qs = DailyWorkReport.objects.filter(
            document_html__contains=CKEDITOR_INLINE_PREFIX,
        ).select_related('employee')
        if report_ids:
            qs = qs.filter(pk__in=report_ids)

        total = qs.count()
        if dry_run:
            self.stdout.write(self.style.WARNING('== DRY RUN - khong ghi DB =='))
        self.stdout.write(f'{total} bao cao co tham chieu ckeditor5')

        reports_updated = images_removed = 0
        for report in qs.iterator():
            old_html = report.document_html or ''
            new_html, removed = remove_missing_ckeditor_inline_images(old_html)
            if removed == 0:
                continue
            images_removed += removed
            self.stdout.write(
                f'  #{report.pk} {report.report_date} {report.employee.username}: '
                f'go {removed} anh',
            )
            if not dry_run and new_html != old_html:
                report.document_html = new_html
                report.save(update_fields=['document_html', 'updated_at'])
                reports_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Hoan tat: go {images_removed} anh, cap nhat {reports_updated} bao cao.',
            ),
        )
