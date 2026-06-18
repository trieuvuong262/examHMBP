"""Khóa báo cáo sau khi cấp trên đã xem."""

from reports.models import DailyWorkReport, WeeklyWorkReport


def is_report_locked(report) -> bool:
    return bool(report.hod_reviewed)


def _can_supervisor_view_report(viewer, report) -> bool:
    from hrm.permissions import can_view_user_report, can_view_user_weekly_report

    if isinstance(report, WeeklyWorkReport):
        return can_view_user_weekly_report(viewer, report)
    return can_view_user_report(viewer, report)


def lock_report_on_supervisor_view(report, viewer) -> bool:
    """Tự khóa khi cấp trên mở xem báo cáo đã gửi (lần đầu)."""
    if (
        report.employee_id == viewer.id
        or not _can_supervisor_view_report(viewer, report)
        or report.status != DailyWorkReport.STATUS_SUBMITTED
        or report.hod_reviewed
    ):
        return False
    report.hod_reviewed = True
    report.save(update_fields=['hod_reviewed', 'updated_at'])
    return True


def can_edit_own_daily_report(viewer, report, *, can_submit: bool) -> bool:
    if is_report_locked(report):
        return False
    if report.employee_id != viewer.id:
        return False
    return can_submit


def can_edit_own_weekly_report(viewer, report, *, can_submit: bool) -> bool:
    if is_report_locked(report):
        return False
    if report.employee_id != viewer.id:
        return False
    return can_submit
