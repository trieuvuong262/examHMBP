"""Khóa báo cáo sau khi cấp trên đã xem hoặc quá hạn chỉnh sửa."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.utils import timezone

from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.period_utils import PERIOD_DAY, PERIOD_MONTH, PERIOD_WEEK


def _report_reference_date(report) -> date:
    """Mốc ngày của báo cáo — dùng tính hạn sửa."""
    if isinstance(report, WeeklyWorkReport):
        return report.week_start + timedelta(days=6)
    report_date = report.report_date
    period = getattr(report, 'report_period', PERIOD_DAY) or PERIOD_DAY
    if period == PERIOD_WEEK:
        return report_date + timedelta(days=6)
    if period == PERIOD_MONTH:
        last_day = calendar.monthrange(report_date.year, report_date.month)[1]
        return report_date.replace(day=last_day)
    return report_date


def last_editable_date(report) -> date:
    """Ngày cuối cùng được phép sửa (hôm sau của mốc báo cáo)."""
    return _report_reference_date(report) + timedelta(days=1)


def is_report_edit_expired(report) -> bool:
    """True nếu đã qua hết ngày hôm sau của báo cáo."""
    return timezone.localdate() > last_editable_date(report)


def is_report_locked(report) -> bool:
    return bool(report.hod_reviewed)


def report_edit_denied_message(report) -> str:
    if is_report_locked(report):
        return 'Cấp trên đã xem báo cáo — không thể chỉnh sửa.'
    if is_report_edit_expired(report):
        return (
            'Đã quá hạn chỉnh sửa — chỉ được sửa đến hết ngày '
            f'{last_editable_date(report).strftime("%d/%m/%Y")}.'
        )
    return 'Bạn không có quyền chỉnh sửa báo cáo này.'


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
    if is_report_locked(report) or is_report_edit_expired(report):
        return False
    if report.employee_id != viewer.id:
        return False
    return can_submit


def can_edit_own_weekly_report(viewer, report, *, can_submit: bool) -> bool:
    if is_report_locked(report) or is_report_edit_expired(report):
        return False
    if report.employee_id != viewer.id:
        return False
    return can_submit
