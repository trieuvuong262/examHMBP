#!/usr/bin/env python3
"""Chuyển file báo cáo tuần còn trên media VPS lên NAS."""
import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

import shutil
from pathlib import Path

from django.conf import settings

from reports.models import WeeklyWorkReportAttachment
from reports.weekly_nas_storage import (
    WeeklyReportNasStorage,
    _rclone_upload_file,
    is_legacy_weekly_path,
    weekly_report_nas_abs_root,
)


def migrate_one(att, dry_run: bool) -> bool:
    name = att.file.name
    if not name or not is_legacy_weekly_path(name):
        return False
    src = Path(settings.MEDIA_ROOT) / name
    if not src.is_file():
        print(f'SKIP missing src att={att.pk} {name}')
        return False

    storage = WeeklyReportNasStorage()
    # Giữ cấu trúc tuần/user từ legacy path hoặc tạo mới từ report
    from reports.weekly_nas_storage import weekly_attachment_upload_to

    new_name = weekly_attachment_upload_to(att, src.name)
    dest = Path(storage.path(new_name))

    print(f'MIGRATE att={att.pk} {name} -> {new_name}')
    if dry_run:
        return True

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    except OSError:
        _rclone_upload_file(src, new_name)

    att.file.name = new_name
    att.save(update_fields=['file'])
    print(f'  OK saved db att={att.pk}')
    return True


def main():
    dry_run = '--dry-run' in sys.argv
    week_only = None
    for arg in sys.argv[1:]:
        if arg.startswith('--week='):
            from datetime import date
            week_only = date.fromisoformat(arg.split('=', 1)[1])

    print(f'NAS_ROOT={weekly_report_nas_abs_root()} dry_run={dry_run} week={week_only}')

    qs = WeeklyWorkReportAttachment.objects.select_related('report', 'report__employee').order_by('pk')
    if week_only:
        qs = qs.filter(report__week_start=week_only)

    migrated = 0
    for att in qs:
        if migrate_one(att, dry_run):
            migrated += 1

    print(f'DONE migrated={migrated}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
