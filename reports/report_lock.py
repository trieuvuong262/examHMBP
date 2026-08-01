"""Khóa báo cáo sau khi cấp trên đã xem hoặc quá hạn chỉnh sửa."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.db.models.functions import Coalesce
from django.utils import timezone

from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.period_utils import PERIOD_DAY, PERIOD_MONTH, PERIOD_WEEK
from reports.report_submit_time import submit_anchor_at
from reports.report_settings import (
    report_approve_deadline_hours,
    report_auto_reject_deadline_hours,
    report_auto_reject_window,
    report_employee_edit_deadline_hours,
    report_employee_edit_window,
    report_manager_edit_window,
    report_unapprove_deadline_days,
)

# Fallback khi chưa migrate / DB lỗi — giữ hành vi cũ.
PRODUCTION_EDIT_WINDOW = timedelta(hours=24)
PRODUCTION_MANAGER_EDIT_WINDOW = timedelta(days=7)


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


def production_approve_deadline(report):
    """Hạn duyệt (SLA) — X giờ kể từ khi nhân viên gửi báo cáo."""
    anchor = submit_anchor_at(report)
    if report.status != DailyWorkReport.STATUS_SUBMITTED or not anchor:
        return None
    return anchor + timedelta(hours=report_approve_deadline_hours())


def is_production_approve_overdue(report) -> bool:
    """True khi quá hạn duyệt nhưng chưa duyệt / chưa không duyệt."""
    if report.hod_reviewed or getattr(report, 'hod_rejected', False):
        return False
    deadline = production_approve_deadline(report)
    if not deadline:
        return False
    return timezone.now() > deadline


def production_auto_reject_deadline(report):
    """Hạn «Không duyệt» — Y giờ kể từ khi nhân viên gửi báo cáo."""
    anchor = submit_anchor_at(report)
    if report.status != DailyWorkReport.STATUS_SUBMITTED or not anchor:
        return None
    return anchor + report_auto_reject_window()


def is_production_auto_reject_expired(report) -> bool:
    deadline = production_auto_reject_deadline(report)
    if not deadline:
        return False
    return timezone.now() > deadline


def production_employee_edit_deadline(report):
    """Hạn sửa của nhân viên sau khi nộp báo cáo SX."""
    anchor = submit_anchor_at(report)
    if report.status != DailyWorkReport.STATUS_SUBMITTED or not anchor:
        return None
    return anchor + report_employee_edit_window()


def production_manager_edit_deadline(report):
    """Hạn hoàn duyệt / sửa của quản lý — N ngày kể từ khi duyệt báo cáo SX."""
    if not report.hod_reviewed:
        return None
    reviewed_at = getattr(report, 'hod_reviewed_at', None) or submit_anchor_at(report) or report.updated_at
    if not reviewed_at:
        return None
    return reviewed_at + report_manager_edit_window()


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
    """Chuyển báo cáo SX quá hạn không duyệt mà chưa duyệt sang «Không duyệt»."""
    from reports.report_profile import REPORT_PROFILE_PRODUCTION

    now = timezone.now()
    hours = report_auto_reject_deadline_hours()
    cutoff = now - timedelta(hours=hours)
    qs = (
        DailyWorkReport.objects.filter(
            report_profile=REPORT_PROFILE_PRODUCTION,
            status=DailyWorkReport.STATUS_SUBMITTED,
            hod_reviewed=False,
            hod_rejected=False,
            submitted_at__isnull=False,
        )
        .annotate(submit_anchor=Coalesce('submit_clicked_at', 'submitted_at'))
        .filter(submit_anchor__lte=cutoff)
    )
    if employee_ids is not None:
        qs = qs.filter(employee_id__in=employee_ids)
    if date_from is not None:
        qs = qs.filter(report_date__gte=date_from)
    if date_to is not None:
        qs = qs.filter(report_date__lte=date_to)
    expired_ids = list(qs.values_list('pk', flat=True))
    if not expired_ids:
        return 0
    return DailyWorkReport.objects.filter(pk__in=expired_ids).update(
        hod_rejected=True,
        hod_rejected_at=now,
        updated_at=now,
    )


def ensure_production_report_approval_state(report) -> bool:
    """Đồng bộ trạng thái duyệt khi mở báo cáo — trả True nếu vừa đổi trạng thái."""
    if not report or not report.pk:
        return False
    # Không tự duyệt lại báo cáo nhập hộ khi mở trang — tránh ghi đè Hoàn duyệt.
    # Tự duyệt nhập hộ chỉ chạy lúc nộp/lưu (save_proxy_shift_sessions, …).
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
    """Báo cáo SX nhập hộ toàn bộ — mặc định đã duyệt (theo thiết lập chung)."""
    from reports.report_settings import auto_approve_proxy_reports

    if not auto_approve_proxy_reports():
        return False
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


def manager_edited_report_may_auto_approve(report, editor) -> bool:
    # Cùng điều kiện với nút «Duyệt» trên trang chi tiết (can_approve).
    from reports.production_hourly import can_edit_production_norms
    from reports.report_settings import auto_approve_manager_edited_reports

    if not auto_approve_manager_edited_reports():
        return False
    if not report or not report.pk or not editor:
        return False
    if not is_production_report(report):
        return False
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        return False
    if report.hod_reviewed or getattr(report, 'hod_rejected', False):
        return False
    if report.employee_id == getattr(editor, 'id', None):
        return False
    return can_edit_production_norms(editor, report)


def auto_approve_manager_edited_report(report, editor) -> bool:
    """QL / tổ trưởng sửa báo cáo SX đã nộp — chốt duyệt luôn (theo thiết lập chung)."""
    if not manager_edited_report_may_auto_approve(report, editor):
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

    reject_hours = report_auto_reject_deadline_hours()
    edit_hours = report_employee_edit_deadline_hours()
    unapprove_days = report_unapprove_deadline_days()

    if getattr(report, 'hod_rejected', False) and not report.hod_reviewed:
        deadline = production_auto_reject_deadline(report)
        if deadline:
            local_deadline = timezone.localtime(deadline)
            return (
                'Báo cáo đã chuyển sang trạng thái không duyệt — '
                f'quá {reject_hours} giờ kể từ khi nộp '
                f'({local_deadline.strftime("%H:%M %d/%m/%Y")}).'
            )
        return 'Báo cáo đã chuyển sang trạng thái không duyệt — không thể chỉnh sửa.'
    if report.hod_reviewed:
        if viewer and can_review_user_report(viewer, report):
            if is_production_manager_edit_expired(report):
                return (
                    f'Đã quá {unapprove_days} ngày kể từ khi duyệt — '
                    'không thể hoàn duyệt hoặc chỉnh sửa.'
                )
        return 'Báo cáo đã được duyệt — bạn không thể chỉnh sửa.'
    if report.status == DailyWorkReport.STATUS_SUBMITTED:
        deadline = production_employee_edit_deadline(report)
        if deadline and timezone.now() > deadline:
            local_deadline = timezone.localtime(deadline)
            return (
                f'Đã quá {edit_hours} giờ kể từ khi nộp — hạn sửa '
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
    from hrm.permissions import get_report_team_users, has_company_wide_report_access

    if is_production_report(report):
        return False
    if (
        report.employee_id == viewer.id
        or not _can_supervisor_view_report(viewer, report)
        or report.status != DailyWorkReport.STATUS_SUBMITTED
        or report.hod_reviewed
    ):
        return False
    # Giám đốc / admin xem toàn công ty — không đánh dấu đã xem, trừ cấp dưới M2M.
    if has_company_wide_report_access(viewer) and not get_report_team_users(viewer).filter(
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
