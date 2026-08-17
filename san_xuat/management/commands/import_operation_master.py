"""Import Master Data Mã Công Đoạn Sản Xuất từ file Excel.

Ví dụ:
    python manage.py import_operation_master "C:/path/Just_Play_Master_Data.xlsx"
    python manage.py import_operation_master file.xlsx --dry-run
    python manage.py import_operation_master file.xlsx --as-user ngan.ptk
"""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from san_xuat.services.operation_master import (
    OperationMasterImportError,
    import_operation_master,
)


class Command(BaseCommand):
    help = 'Import master data mã công đoạn sản xuất (nhóm, thư viện, routing, time study) từ file Excel.'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Đường dẫn file Excel master data.')
        parser.add_argument('--dry-run', action='store_true', help='Chạy thử, không lưu (rollback).')
        parser.add_argument(
            '--as-user',
            default='',
            help='Username gán Người lập (vd. ngan.ptk). Bỏ trống = không gán từ user.',
        )

    def handle(self, *args, **options):
        path = Path(options['path'])
        if not path.exists():
            raise CommandError(f'Không tìm thấy file: {path}')

        user = None
        as_user = (options.get('as_user') or '').strip()
        if as_user:
            User = get_user_model()
            user = User.objects.filter(username__iexact=as_user).first()
            if user is None:
                raise CommandError(f'Không tìm thấy user: {as_user}')

        try:
            result = import_operation_master(str(path), dry_run=options['dry_run'], user=user)
        except OperationMasterImportError as exc:
            raise CommandError(str(exc))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY-RUN (không lưu):'))

        self.stdout.write(self.style.SUCCESS('Đã tạo mới:'))
        for key, val in sorted(result.created.items()):
            self.stdout.write(f'  + {key}: {val}')
        self.stdout.write(self.style.SUCCESS('Đã cập nhật:'))
        for key, val in sorted(result.updated.items()):
            self.stdout.write(f'  ~ {key}: {val}')

        if result.warnings:
            self.stdout.write(self.style.WARNING(f'Cảnh báo ({len(result.warnings)}):'))
            for w in result.warnings[:50]:
                self.stdout.write(f'  ! {w}')
            if len(result.warnings) > 50:
                self.stdout.write(f'  … và {len(result.warnings) - 50} cảnh báo khác.')

        self.stdout.write(self.style.SUCCESS(
            f'Xong. Tổng tạo mới {result.total_created}, cập nhật {result.total_updated}.'
        ))
