"""Ghép lại nhóm công đoạn cho thư viện đã import sai.

Ví dụ:
    python manage.py rematch_operation_groups --dry-run
    python manage.py rematch_operation_groups
    python manage.py rematch_operation_groups --only-auto
    python manage.py rematch_operation_groups --excel /path/Thu_Vien_Cong_Doan.xlsx
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from san_xuat.services.operation_group_resolve import rematch_operations_to_groups


class Command(BaseCommand):
    help = 'Ghép lại MÃ NHÓM cho công đoạn trong thư viện theo nhóm đã có trên hệ thống.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Chạy thử, không lưu.')
        parser.add_argument(
            '--only-auto',
            action='store_true',
            help='Chỉ xử lý công đoạn đang gắn nhóm tạm AUTO-*.',
        )
        parser.add_argument(
            '--excel',
            default='',
            help='File Excel thư viện (sheet 02_THU_VIEN_CONG_DOAN) để lấy MÃ NHÓM gốc.',
        )

    def handle(self, *args, **options):
        excel_path = (options.get('excel') or '').strip()
        if excel_path:
            path = Path(excel_path)
            if not path.exists():
                raise CommandError(f'Không tìm thấy file: {path}')
            excel_path = str(path)

        try:
            checked, updated, notes = rematch_operations_to_groups(
                dry_run=options['dry_run'],
                only_auto=options['only_auto'],
                excel_path=excel_path,
            )
        except (RuntimeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY-RUN (không lưu):'))

        self.stdout.write(f'Đã kiểm tra: {checked} công đoạn')
        self.stdout.write(self.style.SUCCESS(f'Cập nhật nhóm: {updated}'))

        for line in notes[:80]:
            self.stdout.write(f'  · {line}')
        if len(notes) > 80:
            self.stdout.write(f'  … và {len(notes) - 80} dòng nữa')
