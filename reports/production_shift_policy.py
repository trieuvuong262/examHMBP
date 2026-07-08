"""Quy tắc ca làm — báo cáo sản xuất (ca sáng + ca tối)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.utils import timezone

from reports.models import DailyWorkReport
from reports.period_utils import PERIOD_DAY
from reports.production_slots import normalize_shift, shift_contains_datetime
from reports.report_lock import production_employee_may_edit
from reports.report_profile import REPORT_PROFILE_PRODUCTION

PRODUCTION_SHIFT_ORDER = (
    DailyWorkReport.SHIFT_MORNING,
    DailyWorkReport.SHIFT_NIGHT,
)

SHIFT_META = {
    DailyWorkReport.SHIFT_MORNING: {
        'label': 'Ca sáng',
        'time_range': '7h30 – 23h',
        'description': 'Ca ban ngày — gồm khung tăng ca 18h–23h trong cùng báo cáo',
    },
    DailyWorkReport.SHIFT_NIGHT: {
        'label': 'Ca tối',
        'time_range': '23h – 5h sáng hôm sau',
        'description': 'Ca đêm — ngày báo cáo là ngày bắt đầu lúc 23h',
    },
}


def production_reports_for_day(employee, report_date):
    return DailyWorkReport.objects.filter(
        employee=employee,
        report_date=report_date,
        report_profile=REPORT_PROFILE_PRODUCTION,
        report_period=PERIOD_DAY,
    )


def get_production_report(employee, report_date, shift: str):
    shift = normalize_shift(shift)
    try:
        return production_reports_for_day(employee, report_date).get(shift=shift)
    except DailyWorkReport.DoesNotExist:
        return None


def shift_display_label(shift: str) -> str:
    shift = normalize_shift(shift)
    meta = SHIFT_META.get(shift)
    return meta['label'] if meta else shift


def shift_badge_class(shift: str) -> str:
    """Màu badge ca — cùng palette Loại VP (Ngày / Tháng)."""
    shift = normalize_shift(shift)
    period_suffix = {
        DailyWorkReport.SHIFT_MORNING: 'day',
        DailyWorkReport.SHIFT_NIGHT: 'month',
    }.get(shift)
    if period_suffix:
        return f'badge jp-report-period-badge jp-report-period-badge--{period_suffix}'
    return 'badge bg-secondary-subtle text-secondary'


def production_shift_for_datetime(
    at: datetime,
    employee,
) -> tuple[date, str]:
    """
    Suy ra (report_date, shift) từ thời điểm thực tế (VPS).
    - Ca sáng (+ tăng ca): 7h30–23h
    - Ca tối: 23h–5h sáng hôm sau (report_date = ngày bắt đầu lúc 23h)
    """
    local = timezone.localtime(at)
    day = local.date()
    clock = local.time()

    if clock < time(5, 0):
        prev_day = day - timedelta(days=1)
        if shift_contains_datetime(local, prev_day, DailyWorkReport.SHIFT_NIGHT):
            return prev_day, DailyWorkReport.SHIFT_NIGHT

    if shift_contains_datetime(local, day, DailyWorkReport.SHIFT_MORNING):
        return day, DailyWorkReport.SHIFT_MORNING

    if clock >= time(23, 0):
        return day, DailyWorkReport.SHIFT_NIGHT

    return day, DailyWorkReport.SHIFT_MORNING


def find_open_production_report(employee, at: datetime | None = None):
    """Báo cáo ca đang nhập (draft) gần nhất — ưu tiên khi quay lại portal."""
    at = at or timezone.localtime()
    local_day = timezone.localtime(at).date()
    candidates = production_reports_for_day(employee, local_day).filter(
        status=DailyWorkReport.STATUS_DRAFT,
    ).order_by('-shift_started_at', '-updated_at')
    for report in candidates:
        if report.shift_started_at:
            return report
    prev_day = local_day - timedelta(days=1)
    night = production_reports_for_day(employee, prev_day).filter(
        shift=DailyWorkReport.SHIFT_NIGHT,
        status=DailyWorkReport.STATUS_DRAFT,
        shift_started_at__isnull=False,
    ).first()
    if night and shift_contains_datetime(at, prev_day, DailyWorkReport.SHIFT_NIGHT):
        return night
    return candidates.first()


def resolve_production_entry(
    employee,
    requested_date: date | None = None,
    *,
    at: datetime | None = None,
    explicit_shift: str | None = None,
) -> tuple[date, str]:
    """
    Xác định ngày báo cáo và ca làm khi NV mở trang / bắt đầu công đoạn.
    Ưu tiên: shift trên URL → báo cáo draft đang mở → suy từ thời điểm hiện tại.
    """
    at = at or timezone.localtime()
    explicit_shift = normalize_shift(explicit_shift) if explicit_shift else None

    if explicit_shift and explicit_shift in PRODUCTION_SHIFT_ORDER:
        report_date = requested_date or timezone.localtime(at).date()
        return report_date, explicit_shift

    open_report = find_open_production_report(employee, at)
    if open_report:
        return open_report.report_date, normalize_shift(open_report.shift)

    report_date, shift = production_shift_for_datetime(at, employee)
    if requested_date and requested_date != report_date:
        if shift_contains_datetime(at, requested_date, shift):
            report_date = requested_date
    return report_date, shift


def can_start_production_shift(employee, report_date, shift: str) -> tuple[bool, str]:
    """Kiểm tra NV có được mở báo cáo ca mới không."""
    shift = normalize_shift(shift)
    if shift not in PRODUCTION_SHIFT_ORDER:
        return False, 'Ca làm không hợp lệ.'

    existing = {
        normalize_shift(row.shift): row
        for row in production_reports_for_day(employee, report_date)
    }

    if shift in existing:
        return True, ''

    if shift == DailyWorkReport.SHIFT_NIGHT:
        if DailyWorkReport.SHIFT_MORNING in existing:
            return False, 'Ca tối không áp dụng khi đã có ca sáng cùng ngày.'
        return True, ''

    if shift == DailyWorkReport.SHIFT_MORNING:
        if DailyWorkReport.SHIFT_NIGHT in existing:
            return False, 'Đã có báo cáo ca tối cùng ngày — không thể mở ca sáng.'
        return True, ''

    return False, 'Ca làm không hợp lệ.'


def build_shift_picker_options(employee, report_date, *, can_edit: bool) -> list[dict]:
    """Danh sách ca cho màn chọn — gồm trạng thái và nút hành động."""
    existing = {
        normalize_shift(row.shift): row
        for row in production_reports_for_day(employee, report_date)
    }
    options = []
    for shift in PRODUCTION_SHIFT_ORDER:
        meta = SHIFT_META[shift]
        report = existing.get(shift)
        can_start, block_reason = can_start_production_shift(employee, report_date, shift)
        if report:
            action = 'continue'
            action_label = 'Tiếp tục' if report.status == DailyWorkReport.STATUS_DRAFT else 'Xem / sửa'
            enabled = can_edit and production_employee_may_edit(report)
            if report.hod_reviewed and report.status == DailyWorkReport.STATUS_SUBMITTED:
                status_label = 'Đã duyệt'
            elif getattr(report, 'hod_rejected', False) and report.status == DailyWorkReport.STATUS_SUBMITTED:
                status_label = 'Không duyệt'
            elif report.status == DailyWorkReport.STATUS_SUBMITTED:
                status_label = 'Đã gửi'
            else:
                status_label = 'Đang nhập'
        elif can_start and can_edit:
            action = 'start'
            action_label = 'Bắt đầu'
            enabled = True
            status_label = 'Chưa mở'
        else:
            action = 'blocked'
            action_label = 'Không mở được'
            enabled = False
            status_label = block_reason or 'Không khả dụng'

        options.append({
            'shift': shift,
            'label': meta['label'],
            'time_range': meta['time_range'],
            'description': meta['description'],
            'action': action,
            'action_label': action_label,
            'enabled': enabled,
            'status_label': status_label,
            'report': report,
            'has_report': report is not None,
        })
    return options
