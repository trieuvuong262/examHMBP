"""Dời CV còn nằm trên VPS (MEDIA_ROOT/_private/recruitment) sang NAS.

File mới đã ghi thẳng lên NAS. Lệnh này chỉ xử lý hồ sơ cũ có ``file.name``
bắt đầu bằng ``cv/``.

Chạy thử:  python manage.py migrate_candidate_cvs_to_nas --dry-run
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from recruitment.cv_nas_storage import (
    LEGACY_CV_PREFIX,
    CandidateCvNasStorage,
    cv_upload_to,
    legacy_cv_abs_path,
    pending_exists,
    remove_pending,
)
from recruitment.models import CandidateFile


class Command(BaseCommand):
    help = 'Dời CV ứng viên còn nằm trên VPS sang thư mục NAS 14.Portal - CV.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Chỉ liệt kê, không ghi NAS / không đổi DB.')
        parser.add_argument(
            '--keep-source',
            action='store_true',
            help='Giữ file gốc trên VPS sau khi dời (mặc định xóa vì CV là dữ liệu cá nhân).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        keep_source = options['keep_source']
        if dry_run:
            self.stdout.write(self.style.WARNING('== DRY RUN - khong ghi thay doi =='))

        qs = CandidateFile.objects.filter(file__startswith=LEGACY_CV_PREFIX).select_related('candidate')
        total = qs.count()
        self.stdout.write(f'{total} CV còn trên VPS')
        storage = CandidateCvNasStorage()
        moved = missing = held = 0
        for obj in qs.iterator():
            old_name = obj.file.name
            src = legacy_cv_abs_path(old_name)
            try:
                data = src.read_bytes() if src.is_file() else None
            except OSError:
                data = None
            if data is None:
                missing += 1
                self.stdout.write(self.style.ERROR(f'  [x] thiếu file: {old_name}'))
                continue
            filename = obj.original_name or os.path.basename(old_name)
            new_rel = cv_upload_to(obj, filename)
            self.stdout.write(f'  {old_name} -> {new_rel}')
            if not dry_run:
                saved = storage.save(new_rel, ContentFile(data, name=filename))
                if pending_exists(saved):
                    # NAS không nhận — giữ file gốc và đường dẫn cũ.
                    remove_pending(saved)
                    held += 1
                    self.stdout.write(self.style.WARNING(f'  [!] NAS chưa nhận, giữ nguyên: {old_name}'))
                    continue
                obj.file.name = saved
                obj.save(update_fields=['file'])
                if not keep_source:
                    try:
                        Path(src).unlink(missing_ok=True)
                    except OSError:
                        pass
            moved += 1
        verb = 'Sẽ dời' if dry_run else 'Đã dời'
        self.stdout.write(self.style.SUCCESS(f'{verb} {moved}, thiếu {missing}, giữ vì NAS lỗi {held}.'))
