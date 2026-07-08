"""Khóa báo cáo sau khi cấp trên đã xem hoặc quá hạn chỉnh sửa."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.utils import timezone

from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.period_utils import PERIOD_DAY, PERIOD_MONTH, PERIOD_WEEK

PRODUCTION_EDIT_WINDOW = timedelta(hours=24)


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


def is_production_report(report) -> bool:
    return bool(getattr(report, 'is_production_report', False))


def production_auto_reject_deadline(report):
    """Hạn «Không duyệt» — 24h kể từ khi nhân viên gửi báo cáo."""
    return production_employee_edit_deadline(report)


def is_production_auto_reject_expired(report) -> bool:
    deadline = production_auto_reject_deadline(report)
    if not deadline:
        return False
    return timezone.now() > deadline


def production_employee_edit_deadline(report):
    """Hạn sửa của nhân viên sau khi nộp báo cáo SX."""
    if report.status != DailyWorkReport.STATUS_SUBMITTED or not report.submitted_at:
        return None
    return report.submitted_at + PRODUCTION_EDIT_WINDOW


def production_manager_edit_deadline(report):
    """Hạn sửa của quản lý sau khi duyệt báo cáo SX."""
    if not report.hod_reviewed:
        return None
    reviewed_at = getattr(report, 'hod_reviewed_at', None) or report.submitted_at or report.updated_at
    if not reviewed_at:
        return None
    return reviewed_at + PRODUCTION_EDIT_WINDOW


def is_production_employee_edit_expired(report) -> bool:
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        return is_report_edit_expired(report)
    deadline = production_employee_edit_deadline(report)
    if not deadline:
        return False
    return timezone.now() > deadline


def is_production_manager_edit_expired(report) -> bool:
    deadline = production_manager_edit_deadline(report)
    if not deadline:
        return True
    return timezone.now() > deadline


def production_employee_may_edit(report) -> bool:
    if report.hod_reviewed or getattr(report, 'hod_rejected', False):
        return False
    if report.status == DailyWorkReport.STATUS_SUBMITTED:
        return not is_production_employee_edit_expired(report)
    return not is_report_edit_expired(report)


def should_auto_reject_production_report(report) -> bool:
    if not is_production_report(report):
        return False
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        return False
    if report.hod_reviewed or getattr(report, 'hod_rejected', False):
        return False
    return is_production_auto_reject_expired(report)


def auto_reject_production_report(report) -> bool:
    if not should_auto_reject_production_report(report):
        return False
    now = timezone.now()
    report.hod_rejected = True
    report.hod_rejected_at = now
    report.save(update_fields=['hod_rejected', 'hod_rejected_at', 'updated_at'])
    return True


def auto_reject_expired_production_reports(
    *,
    employee_ids=None,
    date_from=None,
    date_to=None,
) -> int:
    """Chuyển báo cáo SX quá 24h kể từ khi nộp mà chưa duyệt sang «Không duyệt»."""
    from reports.report_profile import REPORT_PROFILE_PRODUCTION

    now = timezone.now()
    cutoff = now - PRODUCTION_EDIT_WINDOW
    qs = DailyWorkReport.objects.filter(
        report_profile=REPORT_PROFILE_PRODUCTION,
        status=DailyWorkReport.STATUS_SUBMITTED,
        hod_reviewed=False,
        hod_rejected=False,
        submitted_at__isnull=False,
        submitted_at__lte=cutoff,
    )
    if employee_ids is not None:
        qs = qs.filter(employee_id__in=employee_ids)
    if date_from is not None:
        qs = qs.filter(report_date__gte=date_from)
    if date_to is not None:
        qs = qs.filter(report_date__lte=date_to)
    return qs.update(hod_rejected=True, hod_rejected_at=now, updated_at=now)


def ensure_production_report_approval_state(report) -> bool:
    """Đồng bộ trạng thái duyệt khi mở báo cáo — trả True nếu vừa đổi trạng thái."""
    if not report or not report.pk:
        return False
    if auto_approve_fully_proxy_entered_report(report):
        return True
    return auto_reject_production_report(report)


def production_manager_may_edit(report) -> bool:
    if not report.hod_reviewed:
        return False
    return not is_production_manager_edit_expired(report)


def approve_production_report(report) -> None:
    now = timezone.now()
    report.hod_reviewed = True
    report.hod_reviewed_at = now
    report.hod_rejected = False
    report.hod_rejected_at = None
    update_fields = [
        'hod_reviewed',
        'hod_reviewed_at',
        'hod_rejected',
        'hod_rejected_at',
        'updated_at',
    ]
    if hasattr(report, 'hod_first_reviewed_at') and not report.hod_first_reviewed_at:
        report.hod_first_reviewed_at = now
        update_fields.append('hod_first_reviewed_at')
    report.save(update_fields=update_fields)


def auto_approve_fully_proxy_entered_report(report) -> bool:
    """Báo cáo SX nhập hộ toàn bộ — mặc định đã duyệt."""
    if not report or not report.pk:
        return False
    if not is_production_report(report):
        return False
    if not report.proxy_entered_by_id:
        return False
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        return False
    if report.hod_reviewed:
        return False
    approve_production_report(report)
    return True


def unapprove_production_report(report) -> None:
    report.hod_reviewed = False
    report.hod_reviewed_at = None
    report.save(update_fields=['hod_reviewed', 'hod_reviewed_at', 'updated_at'])
    auto_reject_production_report(report)


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


def production_edit_denied_message(report, *, viewer=None) -> str:
    from hrm.permissions import can_review_user_report

    if getattr(report, 'hod_rejected', False) and not report.hod_reviewed:
        deadline = production_auto_reject_deadline(report)
        if deadline:
            local_deadline = timezone.localtime(deadline)
            return (
                'Báo cáo đã chuyển sang trạng thái không duyệt — '
                f'quá 24 giờ kể từ khi nộp ({local_deadline.strftime("%H:%M %d/%m/%Y")}).'
            )
        return 'Báo cáo đã chuyển sang trạng thái không duyệt — không thể chỉnh sửa.'
    if report.hod_reviewed:
        if viewer and can_review_user_report(viewer, report):
            if is_production_manager_edit_expired(report):
                return 'Đã quá 24 giờ kể từ khi duyệt — không thể chỉnh sửa.'
        return 'Báo cáo đã được duyệt — bạn không thể chỉnh sửa.'
    if report.status == DailyWorkReport.STATUS_SUBMITTED:
        deadline = production_employee_edit_deadline(report)
        if deadline and timezone.now() > deadline:
            local_deadline = timezone.localtime(deadline)
            return (
                'Đã quá 24 giờ kể từ khi nộp — hạn sửa '
                f'{local_deadline.strftime("%H:%M %d/%m/%Y")}.'
            )
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
    """Tự khóa khi cấp trên mở xem báo cáo đã gửi (lần đầu) — không áp dụng SX."""
    from hrm.permissions import get_report_team_users, is_global_report_viewer

    if is_production_report(report):
        return False
    if (
        report.employee_id == viewer.id
        or not _can_supervisor_view_report(viewer, report)
        or report.status != DailyWorkReport.STATUS_SUBMITTED
        or report.hod_reviewed
    ):
        return False
    # ductn/admin xem toàn công ty — không đánh dấu đã xem, trừ cấp dưới M2M/kiêm nhiệm.
    if is_global_report_viewer(viewer) and not get_report_team_users(viewer).filter(
        pk=report.employee_id,
    ).exists():
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
