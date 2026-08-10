"""Đồng bộ thư viện công đoạn chuẩn JustPlay.

Usage:
  python manage.py sync_process_master
  python manage.py sync_process_master --retire-missing
  python manage.py sync_process_master --purge
"""

from django.core.management.base import BaseCommand

from san_xuat.services.sync_process_master import sync_standard_process_library


class Command(BaseCommand):
    help = 'Đồng bộ SxOperation / nhóm / khâu / SxProcessName từ mẫu công đoạn chuẩn'

    def add_arguments(self, parser):
        parser.add_argument(
            '--retire-missing',
            action='store_true',
            help='Ngưng dùng các OP không còn trong mẫu (không xoá)',
        )
        parser.add_argument(
            '--purge',
            action='store_true',
            help='Xoá mọi OP không còn trong mẫu (chỉ giữ Cắt / In-Ép / Thêu / May / HT / GH chuẩn)',
        )

    def handle(self, *args, **options):
        stats = sync_standard_process_library(
            retire_missing=options['retire_missing'],
            purge_missing=options['purge'],
        )
        self.stdout.write(self.style.SUCCESS(
            'Synced stages={stages} groups={groups} '
            'groups_deactivated={groups_deactivated} stages_deactivated={stages_deactivated} '
            'work_centers_deactivated={work_centers_deactivated} '
            'ops_created={ops_created} ops_updated={ops_updated} '
            'ops_retired={ops_retired} ops_deleted={ops_deleted} '
            'process_names={process_names} '
            'process_names_deactivated={process_names_deactivated}'.format(**stats)
        ))
