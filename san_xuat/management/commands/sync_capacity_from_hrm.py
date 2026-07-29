"""
Đồng bộ Năng lực SX từ cơ cấu nhân sự (bộ phận phòng SẢN XUẤT).

Usage:
    python manage.py sync_capacity_from_hrm
    python manage.py sync_capacity_from_hrm --reset-capacity
    python manage.py sync_capacity_from_hrm --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from san_xuat.services.capacity_from_hrm import sync_capacity_from_hrm


class Command(BaseCommand):
    help = (
        'Đồng bộ danh mục Năng lực SX (tổ/chuyền) theo bộ phận HR phòng SẢN XUẤT; '
        'tắt tổ demo TO-MAY-1/2/ĐG.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-capacity',
            action='store_true',
            help='Ghi đè NL/ngày theo ước lượng headcount (mặc định giữ NL đã chỉnh tay nếu > 0).',
        )
        parser.add_argument(
            '--no-legacy-off',
            action='store_true',
            help='Không tắt tổ demo TO-MAY-1 / TO-MAY-2 / TO-DG.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chạy trong transaction rồi rollback — chỉ xem kết quả.',
        )

    def handle(self, *args, **options):
        dry = bool(options.get('dry_run'))
        with transaction.atomic():
            result = sync_capacity_from_hrm(
                reset_capacity=bool(options.get('reset_capacity')),
                deactivate_legacy=not bool(options.get('no_legacy_off')),
            )
            if not result.department:
                self.stderr.write(self.style.ERROR('Không tìm thấy phòng ban SẢN XUẤT trên HR.'))
                if dry:
                    transaction.set_rollback(True)
                return

            from san_xuat.services.capacity_from_hrm import remap_process_steps_to_hr

            remapped = remap_process_steps_to_hr()

            self.stdout.write(f'Phòng ban: {result.department}')
            self.stdout.write(
                f'Tạo {result.created} · cập nhật {result.updated} · '
                f'tắt {result.deactivated} · map HR {result.hr_maps} · '
                f'remap công đoạn {remapped}'
            )
            for line in result.centers or []:
                self.stdout.write(f'  - {line}')

            if dry:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('DRY-RUN: đã rollback, không ghi DB.'))
            else:
                self.stdout.write(self.style.SUCCESS('Đã đồng bộ Năng lực SX từ HR.'))
