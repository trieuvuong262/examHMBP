#!/usr/bin/env python3
"""Kiểm tra báo cáo tuần + file NAS trên VPS (chạy trong container web)."""
import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth.models import User
from django.utils import timezone

from hrm.permissions import can_view_user_weekly_report, can_view_team_reports
from reports.models import WeeklyWorkReport, WeeklyWorkReportAttachment
from reports.team_utils import meaningful_weekly_reports_qs, weekly_report_visible_to_team
from reports.week_utils import monday_of
from reports.weekly_nas_storage import (
    is_legacy_weekly_path,
    weekly_attachment_abs_path,
    weekly_report_nas_abs_root,
    _weekly_rclone_target,
)


def main():
    viewer_username = (sys.argv[1] if len(sys.argv) > 1 else 'ductn').strip()
    week = monday_of(timezone.localdate())
    print(f'WEEK_START={week.isoformat()}')
    print(f'NAS_ROOT={weekly_report_nas_abs_root()}')

    reports = (
        WeeklyWorkReport.objects.filter(week_start=week)
        .select_related('employee', 'employee__profile', 'employee__profile__department')
        .prefetch_related('attachments')
        .order_by('employee__username')
    )
    print(f'REPORTS_THIS_WEEK={reports.count()}')

    legacy_on_vps = []
    on_nas = []
    missing = []

    for r in reports:
        dept = getattr(getattr(r.employee, 'profile', None), 'department', None)
        dept_name = dept.name if dept else '-'
        print('---')
        print(
            f'id={r.pk} user={r.employee.username} '
            f'name={getattr(getattr(r.employee, "profile", None), "full_name", "")} '
            f'dept={dept_name} status={r.status}'
        )
        print(f'  draft={r.draft_saved_at} submitted={r.submitted_at}')
        print(f'  links={(r.links or "")[:100]!r}')
        for a in r.attachments.all():
            legacy = is_legacy_weekly_path(a.file.name)
            path = weekly_attachment_abs_path(a)
            ok = bool(path and path.is_file())
            print(f'  att id={a.pk} kind={a.kind} name={a.file.name!r} legacy={legacy} ok={ok}')
            if not ok:
                print(f'    rclone_target={_weekly_rclone_target(a.file.name)}')
                missing.append((r.pk, a.pk, a.file.name))
            elif legacy:
                legacy_on_vps.append(a.file.name)
            else:
                on_nas.append(a.file.name)

    viewer = User.objects.filter(username__iexact=viewer_username).select_related('profile', 'profile__department').first()
    print('---')
    print(f'VIEWER={viewer.username if viewer else "NOT_FOUND"}')
    if viewer:
        prof = getattr(viewer, 'profile', None)
        print(
            f'  dept={prof.department.name if prof and prof.department_id else "-"} '
            f'role={getattr(prof, "role", "-")} can_team={can_view_team_reports(viewer)}'
        )
        visible = meaningful_weekly_reports_qs().filter(week_start=week)
        print(f'  meaningful_reports={visible.count()}')
        for r in visible.select_related('employee', 'employee__profile'):
            can = can_view_user_weekly_report(viewer, r)
            vis = weekly_report_visible_to_team(r)
            dept = getattr(getattr(r.employee, 'profile', None), 'department', None)
            mark = 'OK' if can and vis else 'DENY'
            print(
                f'  [{mark}] report={r.pk} author={r.employee.username} '
                f'dept={dept.name if dept else "-"}'
            )

    print('---')
    print(f'SUMMARY legacy_vps={len(legacy_on_vps)} nas_ok={len(on_nas)} missing={len(missing)}')
    if missing:
        print('MISSING_FILES:')
        for item in missing:
            print(' ', item)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
