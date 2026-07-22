"""Tự động gửi báo cáo sản xuất chưa nộp — cron 11:30 hàng ngày."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from reports.models import DailyWorkReport, DailyWorkReportEditLog, ProductionReportReminderLog
from reports.period_utils import PERIOD_DAY
from reports.production_hourly import (
    build_hourly_grid,
    lock_production_steps_on_submit,
    unfinalized_active_with_data,
    validate_production_submit_efficiency,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION

logger = logging.getLogger(__name__)

# 11:30 mỗi ngày (giờ VN) — cửa sổ grace vài phút nếu cron trễ.
AUTO_SUBMIT_HOUR = 11
AUTO_SUBMIT_MINUTE = 30
AUTO_SUBMIT_GRACE_MINUTES = 5
DEFAULT_DECLARED_WORK_HOURS = Decimal('9.50')
# Dùng wave=1 trong log dedupe cho đợt auto-submit 11:30.
AUTO_SUBMIT_WAVE = ProductionReportReminderLog.WAVE_1


def _local_now(now=None) -> datetime:
    now = now or timezone.now()
    return timezone.localtime(now)


def is_auto_submit_window(now=None) -> bool:
    """True trong khung 11:30–11:35 (giờ local)."""
    local_now = _local_now(now)
    target = local_now.replace(
        hour=AUTO_SUBMIT_HOUR,
        minute=AUTO_SUBMIT_MINUTE,
        second=0,
        microsecond=0,
    )
    if local_now < target:
        return False
    return (local_now - target) <= timedelta(minutes=AUTO_SUBMIT_GRACE_MINUTES)


def auto_submit_report_date(now=None) -> date:
    """Ngày báo cáo cần chốt: hôm qua (đóng BC ngày trước lúc 11:30)."""
    return _local_now(now).date() - timedelta(days=1)


def _unsubmitted_non_night_queryset(report_date: date):
    """BC SX chưa nộp, không phải ca tối (gồm MORNING / OVERTIME cũ)."""
    return (
        DailyWorkReport.objects.filter(
            report_date=report_date,
            report_profile=REPORT_PROFILE_PRODUCTION,
            report_period=PERIOD_DAY,
        )
        .exclude(shift=DailyWorkReport.SHIFT_NIGHT)
        .exclude(status=DailyWorkReport.STATUS_SUBMITTED)
        .select_related('employee', 'employee__profile')
        .prefetch_related('production_products__hourly_entries')
    )


def _report_has_submittable_quantity(report: DailyWorkReport) -> bool:
    grid = build_hourly_grid(report)
    return bool(grid.get('rows')) and (grid.get('grand_total') or 0) > 0


def can_auto_submit_report(report: DailyWorkReport) -> tuple[bool, str]:
    """Kiểm tra BC có thể tự gửi không."""
    if report.status == DailyWorkReport.STATUS_SUBMITTED:
        return False, 'already_submitted'
    if report.shift == DailyWorkReport.SHIFT_NIGHT:
        return False, 'night_shift'
    if unfinalized_active_with_data(report):
        return False, 'unfinalized_session'
    if not _report_has_submittable_quantity(report):
        return False, 'no_quantity'
    _, efficiency_err = validate_production_submit_efficiency(report)
    if efficiency_err:
        return False, 'efficiency_block'
    return True, ''


def auto_submit_one_report(report: DailyWorkReport, *, dry_run: bool = False) -> str:
    """
    Gửi một báo cáo — đặt giờ làm việc mặc định 9,50 nếu chưa có.
    Trả về: submitted | dry_run | skip reason.
    """
    ok, reason = can_auto_submit_report(report)
    if not ok:
        return reason

    if dry_run:
        return 'dry_run'

    with transaction.atomic():
        report = (
            DailyWorkReport.objects.select_for_update()
            .filter(pk=report.pk)
            .first()
        )
        if not report or report.status == DailyWorkReport.STATUS_SUBMITTED:
            return 'already_submitted'

        if report.declared_work_hours is None or report.declared_work_hours <= 0:
            report.declared_work_hours = DEFAULT_DECLARED_WORK_HOURS

        now = timezone.now()
        report.status = DailyWorkReport.STATUS_SUBMITTED
        report.submitted_at = now
        report.report_profile = REPORT_PROFILE_PRODUCTION
        report.save()
        lock_production_steps_on_submit(report)

        DailyWorkReportEditLog.objects.create(
            report=report,
            edited_by=None,
            actor_kind=DailyWorkReportEditLog.ACTOR_EMPLOYEE,
            action=DailyWorkReportEditLog.ACTION_SUBMIT,
            summary='Hệ thống tự động gửi báo cáo lúc 11:30.',
            detail=f'Thời gian làm việc: {report.declared_work_hours} giờ (mặc định 9,50 nếu trống).',
        )

        # Dedupe theo (employee, date, shift) — shift có thể MORNING/OVERTIME
        ProductionReportReminderLog.objects.get_or_create(
            employee_id=report.employee_id,
            report_date=report.report_date,
            shift=report.shift or DailyWorkReport.SHIFT_MORNING,
            wave=AUTO_SUBMIT_WAVE,
        )

    return 'submitted'


def auto_submit_unsubmitted_production_reports(
    *,
    now=None,
    dry_run: bool = False,
    force: bool = False,
    report_date: date | None = None,
) -> dict:
    """
    11:30 hàng ngày: tự động gửi mọi BC SX chưa nộp của ngày hôm trước,
    trừ ca tối. Thời gian làm việc mặc định 9,50 giờ.
    """
    if not force and not is_auto_submit_window(now=now):
        return {
            'submitted': 0,
            'skipped': 0,
            'failed': 0,
            'reason': 'outside_auto_submit_window',
        }

    target_date = report_date or auto_submit_report_date(now=now)
    qs = _unsubmitted_non_night_queryset(target_date)

    submitted = skipped = failed = 0
    skip_reasons: dict[str, int] = {}

    for report in qs.iterator(chunk_size=50):
        try:
            result = auto_submit_one_report(report, dry_run=dry_run)
        except Exception:
            logger.exception('Auto-submit failed for report pk=%s', report.pk)
            failed += 1
            continue

        if result in ('submitted', 'dry_run'):
            submitted += 1
        else:
            skipped += 1
            skip_reasons[result] = skip_reasons.get(result, 0) + 1

    return {
        'submitted': submitted,
        'skipped': skipped,
        'failed': failed,
        'report_date': target_date.isoformat(),
        'skip_reasons': skip_reasons,
    }


# Tên cũ — giữ để command/migrate gọi không gãy.
def send_production_report_reminders(*, now=None, dry_run: bool = False, **kwargs) -> dict:
    stats = auto_submit_unsubmitted_production_reports(now=now, dry_run=dry_run, **kwargs)
    return {
        'sent': stats.get('submitted', 0),
        'skipped': stats.get('skipped', 0),
        'failed': stats.get('failed', 0),
        'reason': stats.get('reason'),
        'report_date': stats.get('report_date'),
        'skip_reasons': stats.get('skip_reasons'),
    }
