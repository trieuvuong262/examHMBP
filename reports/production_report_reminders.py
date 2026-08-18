"""Tự động gửi báo cáo sản xuất chưa nộp — cron theo giờ thiết lập chung."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from reports.models import DailyWorkReport, DailyWorkReportEditLog, ProductionReportReminderLog
from reports.period_utils import PERIOD_DAY
from reports.production_hourly import (
    build_hourly_grid,
    discard_empty_active_sessions,
    is_empty_active_session,
    lock_production_steps_on_submit,
    unfinalized_active_with_data,
    validate_production_submit_efficiency,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.report_settings import (
    report_auto_submit_time,
    report_default_declared_work_hours,
    report_night_auto_submit_enabled,
    report_night_auto_submit_time,
    report_night_default_declared_work_hours,
)

logger = logging.getLogger(__name__)

KIND_MORNING = 'morning'
KIND_NIGHT = 'night'

# Fallback khi chưa đọc được thiết lập.
AUTO_SUBMIT_HOUR = 23
AUTO_SUBMIT_MINUTE = 30
NIGHT_AUTO_SUBMIT_HOUR = 5
NIGHT_AUTO_SUBMIT_MINUTE = 0
AUTO_SUBMIT_GRACE_MINUTES = 5
DEFAULT_DECLARED_WORK_HOURS = Decimal('9.50')
AUTO_SUBMIT_WAVE_MORNING = ProductionReportReminderLog.WAVE_1
AUTO_SUBMIT_WAVE_NIGHT = ProductionReportReminderLog.WAVE_2


def _local_now(now=None) -> datetime:
    now = now or timezone.now()
    return timezone.localtime(now)


def _configured_auto_submit_time(kind: str = KIND_MORNING) -> time:
    try:
        if kind == KIND_NIGHT:
            return report_night_auto_submit_time()
        return report_auto_submit_time()
    except Exception:
        if kind == KIND_NIGHT:
            return time(NIGHT_AUTO_SUBMIT_HOUR, NIGHT_AUTO_SUBMIT_MINUTE)
        return time(AUTO_SUBMIT_HOUR, AUTO_SUBMIT_MINUTE)


def _default_declared_work_hours(kind: str = KIND_MORNING) -> Decimal:
    try:
        if kind == KIND_NIGHT:
            return report_night_default_declared_work_hours()
        return report_default_declared_work_hours()
    except Exception:
        return DEFAULT_DECLARED_WORK_HOURS


def _night_auto_submit_enabled() -> bool:
    try:
        return report_night_auto_submit_enabled()
    except Exception:
        return True


def is_auto_submit_window(now=None, *, kind: str = KIND_MORNING) -> bool:
    """True trong khung giờ tự nộp ± grace (giờ local theo thiết lập chung)."""
    if kind == KIND_NIGHT and not _night_auto_submit_enabled():
        return False
    local_now = _local_now(now)
    submit_at = _configured_auto_submit_time(kind)
    target = local_now.replace(
        hour=submit_at.hour,
        minute=submit_at.minute,
        second=0,
        microsecond=0,
    )
    if local_now < target:
        return False
    return (local_now - target) <= timedelta(minutes=AUTO_SUBMIT_GRACE_MINUTES)


def auto_submit_report_date(now=None, *, kind: str = KIND_MORNING) -> date:
    """Ngày báo cáo cần chốt.

    - Ca sáng: hôm nay.
    - Ca tối: hôm qua (ca bắt đầu 17h hôm trước, kết thúc ~5h hôm nay).
    """
    today = _local_now(now).date()
    if kind == KIND_NIGHT:
        return today - timedelta(days=1)
    return today


def _unsubmitted_base_qs(*, kind: str = KIND_MORNING):
    qs = DailyWorkReport.objects.filter(
        report_profile=REPORT_PROFILE_PRODUCTION,
        report_period=PERIOD_DAY,
    ).exclude(status=DailyWorkReport.STATUS_SUBMITTED)
    if kind == KIND_NIGHT:
        return qs.filter(shift=DailyWorkReport.SHIFT_NIGHT)
    return qs.exclude(shift=DailyWorkReport.SHIFT_NIGHT)


def _unsubmitted_queryset(
    *,
    kind: str = KIND_MORNING,
    report_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    qs = _unsubmitted_base_qs(kind=kind)
    if report_date is not None:
        qs = qs.filter(report_date=report_date)
    else:
        if date_from is not None:
            qs = qs.filter(report_date__gte=date_from)
        if date_to is not None:
            qs = qs.filter(report_date__lte=date_to)
    return qs.select_related('employee', 'employee__profile').prefetch_related(
        'production_products__hourly_entries',
    )


# Alias cũ — giữ tương thích import.
def _unsubmitted_non_night_base_qs():
    return _unsubmitted_base_qs(kind=KIND_MORNING)


def _unsubmitted_non_night_queryset(*, report_date: date | None = None, date_from: date | None = None, date_to: date | None = None):
    return _unsubmitted_queryset(
        kind=KIND_MORNING,
        report_date=report_date,
        date_from=date_from,
        date_to=date_to,
    )


def _report_has_submittable_quantity(report: DailyWorkReport) -> bool:
    grid = build_hourly_grid(report)
    return bool(grid.get('rows')) and (grid.get('grand_total') or 0) > 0


def can_auto_submit_report(
    report: DailyWorkReport,
    *,
    kind: str = KIND_MORNING,
    ignore_empty_active: bool = False,
) -> tuple[bool, str]:
    """Kiểm tra BC có thể tự gửi không."""
    if report.status == DailyWorkReport.STATUS_SUBMITTED:
        return False, 'already_submitted'
    if kind == KIND_NIGHT:
        if report.shift != DailyWorkReport.SHIFT_NIGHT:
            return False, 'not_night_shift'
    elif report.shift == DailyWorkReport.SHIFT_NIGHT:
        return False, 'night_shift'
    blocker = unfinalized_active_with_data(report)
    if blocker and not (ignore_empty_active and is_empty_active_session(blocker)):
        return False, 'unfinalized_session'
    if not _report_has_submittable_quantity(report):
        return False, 'no_quantity'
    declared = report.declared_work_hours
    if declared is None or declared <= 0:
        declared = _default_declared_work_hours(kind)
    _, efficiency_err = validate_production_submit_efficiency(
        report, declared_work_hours=declared,
    )
    if efficiency_err:
        return False, 'efficiency_block'
    return True, ''


def auto_submit_one_report(
    report: DailyWorkReport,
    *,
    kind: str = KIND_MORNING,
    dry_run: bool = False,
) -> str:
    """Gửi một báo cáo — đặt giờ làm việc mặc định nếu chưa có."""
    if dry_run:
        ok, reason = can_auto_submit_report(report, kind=kind, ignore_empty_active=True)
        if not ok:
            return reason
        return 'dry_run'

    with transaction.atomic():
        report = (
            DailyWorkReport.objects.select_for_update()
            .filter(pk=report.pk)
            .first()
        )
        if not report or report.status == DailyWorkReport.STATUS_SUBMITTED:
            return 'already_submitted'

        discard_empty_active_sessions(report)

        ok, reason = can_auto_submit_report(report, kind=kind)
        if not ok:
            return reason

        if report.declared_work_hours is None or report.declared_work_hours <= 0:
            report.declared_work_hours = _default_declared_work_hours(kind)

        from reports.report_submit_time import resolve_submitted_at

        now = timezone.now()
        report.report_profile = REPORT_PROFILE_PRODUCTION
        report.status = DailyWorkReport.STATUS_SUBMITTED
        report.submit_clicked_at = now
        report.submitted_at = resolve_submitted_at(report, now)
        report.auto_submitted = True
        report.save()
        lock_production_steps_on_submit(report)

        submit_at = _configured_auto_submit_time(kind)
        shift_label = 'ca tối' if kind == KIND_NIGHT else 'ca sáng'
        DailyWorkReportEditLog.objects.create(
            report=report,
            edited_by=None,
            actor_kind=DailyWorkReportEditLog.ACTOR_EMPLOYEE,
            action=DailyWorkReportEditLog.ACTION_SUBMIT,
            summary=(
                f'Hệ thống tự động gửi báo cáo {shift_label} lúc '
                f'{submit_at.hour:02d}:{submit_at.minute:02d}.'
            ),
            detail=f'Thời gian làm việc: {report.declared_work_hours} giờ.',
        )

        wave = AUTO_SUBMIT_WAVE_NIGHT if kind == KIND_NIGHT else AUTO_SUBMIT_WAVE_MORNING
        ProductionReportReminderLog.objects.get_or_create(
            employee_id=report.employee_id,
            report_date=report.report_date,
            shift=report.shift or (
                DailyWorkReport.SHIFT_NIGHT if kind == KIND_NIGHT else DailyWorkReport.SHIFT_MORNING
            ),
            wave=wave,
        )

    return 'submitted'


def _merge_stats(base: dict, extra: dict) -> dict:
    skip_reasons = dict(base.get('skip_reasons') or {})
    for key, count in (extra.get('skip_reasons') or {}).items():
        skip_reasons[key] = skip_reasons.get(key, 0) + count
    dates = sorted(set(base.get('dates') or []) | set(extra.get('dates') or []))
    labels = [x for x in (base.get('report_date'), extra.get('report_date')) if x]
    return {
        'submitted': base.get('submitted', 0) + extra.get('submitted', 0),
        'skipped': base.get('skipped', 0) + extra.get('skipped', 0),
        'failed': base.get('failed', 0) + extra.get('failed', 0),
        'report_date': ' · '.join(labels) if labels else None,
        'dates': dates,
        'skip_reasons': skip_reasons,
    }


def _run_auto_submit_kind(
    *,
    kind: str,
    dry_run: bool = False,
    report_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    range_mode = bool(date_from or date_to) and report_date is None
    if range_mode:
        qs = _unsubmitted_queryset(
            kind=kind,
            date_from=date_from,
            date_to=date_to,
        ).order_by('report_date', 'employee_id', 'shift')
        if date_from and date_to:
            date_label = f'{date_from.isoformat()}→{date_to.isoformat()}'
        elif date_to:
            date_label = f'…→{date_to.isoformat()}'
        else:
            date_label = f'{date_from.isoformat()}→…'
    else:
        target_date = report_date or auto_submit_report_date(kind=kind)
        qs = _unsubmitted_queryset(kind=kind, report_date=target_date)
        date_label = f'{target_date.isoformat()}({kind})'

    submitted = skipped = failed = 0
    skip_reasons: dict[str, int] = {}
    dates_touched: set[str] = set()

    for report in qs.iterator(chunk_size=50):
        try:
            result = auto_submit_one_report(report, kind=kind, dry_run=dry_run)
        except Exception:
            logger.exception('Auto-submit failed for report pk=%s kind=%s', report.pk, kind)
            failed += 1
            continue

        dates_touched.add(report.report_date.isoformat())
        if result in ('submitted', 'dry_run'):
            submitted += 1
        else:
            skipped += 1
            skip_reasons[result] = skip_reasons.get(result, 0) + 1

    return {
        'submitted': submitted,
        'skipped': skipped,
        'failed': failed,
        'report_date': date_label,
        'dates': sorted(dates_touched),
        'skip_reasons': skip_reasons,
    }


def auto_submit_unsubmitted_production_reports(
    *,
    now=None,
    dry_run: bool = False,
    force: bool = False,
    report_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """
    Cron mỗi 5 phút:
    - Khung giờ ca sáng → tự nộp ca sáng hôm nay.
    - Khung giờ ca tối → tự nộp ca tối của hôm qua (ngày bắt đầu 17h).

    Chạy tay (--force / --date / khoảng): xử lý cả ca sáng và ca tối (nếu bật).
    """
    range_mode = bool(date_from or date_to) and report_date is None
    morning_due = force or range_mode or bool(report_date) or is_auto_submit_window(now=now, kind=KIND_MORNING)
    night_due = (
        _night_auto_submit_enabled()
        and (force or range_mode or bool(report_date) or is_auto_submit_window(now=now, kind=KIND_NIGHT))
    )

    if not morning_due and not night_due:
        return {
            'submitted': 0,
            'skipped': 0,
            'failed': 0,
            'reason': 'outside_auto_submit_window',
        }

    stats: dict = {
        'submitted': 0,
        'skipped': 0,
        'failed': 0,
        'dates': [],
        'skip_reasons': {},
        'report_date': None,
    }
    if morning_due:
        stats = _merge_stats(
            stats,
            _run_auto_submit_kind(
                kind=KIND_MORNING,
                dry_run=dry_run,
                report_date=report_date,
                date_from=date_from,
                date_to=date_to,
            ),
        )
    if night_due:
        # Cron night: ngày BC = hôm qua. Force/--date: dùng đúng report_date được chỉ định.
        night_report_date = report_date
        if not force and not range_mode and not report_date:
            night_report_date = auto_submit_report_date(now=now, kind=KIND_NIGHT)
        stats = _merge_stats(
            stats,
            _run_auto_submit_kind(
                kind=KIND_NIGHT,
                dry_run=dry_run,
                report_date=night_report_date,
                date_from=date_from,
                date_to=date_to,
            ),
        )
    return stats


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
