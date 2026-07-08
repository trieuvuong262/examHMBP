"""Ghi nhận lịch sử chỉnh sửa báo cáo (nhân viên / quản lý)."""

from __future__ import annotations

from reports.models import DailyWorkReport, DailyWorkReportEditLog


def report_edit_actor_kind(user, report: DailyWorkReport) -> str:
    if user.id != report.employee_id:
        return DailyWorkReportEditLog.ACTOR_MANAGER
    return DailyWorkReportEditLog.ACTOR_EMPLOYEE


def log_report_edit(
    report: DailyWorkReport,
    user,
    *,
    action: str = DailyWorkReportEditLog.ACTION_UPDATE,
    summary: str = '',
) -> DailyWorkReportEditLog | None:
    if not report.pk:
        return None
    return DailyWorkReportEditLog.objects.create(
        report=report,
        edited_by=user,
        actor_kind=report_edit_actor_kind(user, report),
        action=action,
        summary=(summary or '')[:500],
    )
