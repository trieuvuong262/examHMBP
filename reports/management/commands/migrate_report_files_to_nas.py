"""Dời file/ảnh báo cáo còn lưu trên VPS (MEDIA_ROOT) sang NAS.

Áp dụng cho dữ liệu cũ tạo trước khi chuyển sang NAS storage:
  - Đính kèm báo cáo ngày VP  : file.name bắt đầu bằng ``reports/daily/``
  - Đính kèm báo cáo tuần      : file.name bắt đầu bằng ``reports/weekly/``
  - Ảnh inline CKEditor (văn bản): tham chiếu ``reports/ckeditor5/...`` trong document_html

File mới đã luôn ghi thẳng lên NAS nên lệnh này chỉ xử lý phần tồn dư.
Chạy thử trước:  python manage.py migrate_report_files_to_nas --dry-run
"""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from reports.daily_inline_images import inline_image_upload_rel
from reports.daily_nas_storage import (
    LEGACY_DAILY_PREFIX,
    DailyReportNasStorage,
    daily_attachment_upload_to,
)
from reports.models import (
    DailyWorkReport,
    DailyWorkReportAttachment,
    WeeklyWorkReportAttachment,
)
from reports.office_content import CKEDITOR_INLINE_PREFIX
from reports.weekly_nas_storage import (
    LEGACY_WEEKLY_PREFIX,
    WeeklyReportNasStorage,
    weekly_attachment_upload_to,
)


class Command(BaseCommand):
    help = 'Dời file/ảnh báo cáo còn nằm trên VPS (MEDIA_ROOT) sang NAS.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ liệt kê, không ghi NAS / không đổi DB.',
        )
        parser.add_argument(
            '--delete-source',
            action='store_true',
            help='Xóa file gốc trên VPS sau khi dời thành công.',
        )
        parser.add_argument(
            '--skip-inline',
            action='store_true',
            help='Bỏ qua ảnh inline CKEditor trong document_html.',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.delete_source = options['delete_source']
        if self.dry_run:
            self.stdout.write(self.style.WARNING('== DRY RUN - khong ghi thay doi =='))

        self._migrate_daily_attachments()
        self._migrate_weekly_attachments()
        if not options['skip_inline']:
            self._migrate_inline_images()

        self.stdout.write(self.style.SUCCESS('Hoan tat.'))

    def _media_path(self, rel_name: str) -> Path:
        return Path(settings.MEDIA_ROOT) / rel_name

    def _read_source(self, rel_name: str) -> bytes | None:
        path = self._media_path(rel_name)
        try:
            if not path.is_file():
                return None
            return path.read_bytes()
        except OSError:
            return None

    def _delete_media(self, rel_name: str) -> None:
        try:
            self._media_path(rel_name).unlink(missing_ok=True)
        except OSError:
            pass

    def _migrate_daily_attachments(self):
        qs = DailyWorkReportAttachment.objects.filter(
            file__startswith=LEGACY_DAILY_PREFIX,
        ).select_related('report__employee')
        total = qs.count()
        self.stdout.write(f'\n[Bao cao ngay] {total} dinh kem con tren VPS')
        storage = DailyReportNasStorage()
        moved = missing = 0
        for att in qs.iterator():
            old_name = att.file.name
            data = self._read_source(old_name)
            if data is None:
                missing += 1
                self.stdout.write(self.style.ERROR(f'  [x] thieu file: {old_name}'))
                continue
            filename = att.original_name or os.path.basename(old_name)
            new_rel = daily_attachment_upload_to(att, filename)
            self.stdout.write(f'  {old_name} -> {new_rel}')
            if not self.dry_run:
                saved_rel = self._save_to_nas(storage, new_rel, data)
                att.file.name = saved_rel
                att.save(update_fields=['file'])
                if self.delete_source:
                    self._delete_media(old_name)
            moved += 1
        self.stdout.write(f'  => doi {moved}, thieu {missing}')

    def _migrate_weekly_attachments(self):
        qs = WeeklyWorkReportAttachment.objects.filter(
            file__startswith=LEGACY_WEEKLY_PREFIX,
        ).select_related('report__employee')
        total = qs.count()
        self.stdout.write(f'\n[Bao cao tuan] {total} dinh kem con tren VPS')
        storage = WeeklyReportNasStorage()
        moved = missing = 0
        for att in qs.iterator():
            old_name = att.file.name
            data = self._read_source(old_name)
            if data is None:
                missing += 1
                self.stdout.write(self.style.ERROR(f'  [x] thieu file: {old_name}'))
                continue
            filename = att.original_name or os.path.basename(old_name)
            new_rel = weekly_attachment_upload_to(att, filename)
            self.stdout.write(f'  {old_name} -> {new_rel}')
            if not self.dry_run:
                saved_rel = self._save_to_nas(storage, new_rel, data)
                att.file.name = saved_rel
                att.save(update_fields=['file'])
                if self.delete_source:
                    self._delete_media(old_name)
            moved += 1
        self.stdout.write(f'  => doi {moved}, thieu {missing}')

    def _migrate_inline_images(self):
        """Ảnh inline CKEditor cũ (reports/ckeditor5/...) trong document_html."""
        qs = DailyWorkReport.objects.filter(
            document_html__contains=CKEDITOR_INLINE_PREFIX,
        ).select_related('employee')
        total = qs.count()
        self.stdout.write(f'\n[Anh inline van ban] {total} bao cao co anh CKEditor cu')
        storage = DailyReportNasStorage()
        moved = missing = reports_touched = 0
        for report in qs.iterator():
            html = report.document_html or ''
            replacements: dict[str, str] = {}
            for old_rel in self._iter_ckeditor_rels(html):
                if old_rel in replacements:
                    continue
                data = self._read_source(old_rel)
                if data is None:
                    missing += 1
                    self.stdout.write(self.style.ERROR(f'  [x] thieu anh: {old_rel}'))
                    continue
                ext = os.path.splitext(old_rel)[1] or '.png'
                new_rel = inline_image_upload_rel(
                    report.employee.username,
                    report.report_date,
                    ext,
                )
                self.stdout.write(f'  {old_rel} -> {new_rel}')
                if not self.dry_run:
                    self._save_to_nas(storage, new_rel, data)
                replacements[old_rel] = new_rel
                moved += 1
            if replacements and not self.dry_run:
                new_html = html
                for old_rel, new_rel in replacements.items():
                    new_url = f'/reports/inline-image/{new_rel}'
                    new_html = new_html.replace(f'/media/{old_rel}', new_url)
                    new_html = new_html.replace(old_rel, new_url)
                if new_html != html:
                    report.document_html = new_html
                    report.save(update_fields=['document_html', 'updated_at'])
                    reports_touched += 1
                    if self.delete_source:
                        for old_rel in replacements:
                            self._delete_media(old_rel)
        self.stdout.write(
            f'  => doi {moved} anh, cap nhat {reports_touched} bao cao, thieu {missing}',
        )

    @staticmethod
    def _iter_ckeditor_rels(html: str):
        import re

        pattern = re.compile(
            r'(?:/media/)?(' + re.escape(CKEDITOR_INLINE_PREFIX) + r'[^\s"\'<>?]+)',
        )
        for match in pattern.finditer(html or ''):
            yield match.group(1)

    def _save_to_nas(self, storage, rel_name: str, data: bytes) -> str:
        from django.core.files.base import ContentFile

        if storage.exists(rel_name):
            return rel_name
        return storage.save(rel_name, ContentFile(data))
