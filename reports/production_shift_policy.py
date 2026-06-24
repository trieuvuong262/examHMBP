"""Quy tắc ca làm — báo cáo sản xuất."""

from __future__ import annotations

from reports.models import DailyWorkReport
from reports.period_utils import PERIOD_DAY
from reports.report_profile import REPORT_PROFILE_PRODUCTION

PRODUCTION_SHIFT_ORDER = (
    DailyWorkReport.SHIFT_MORNING,
    DailyWorkReport.SHIFT_OVERTIME,
    DailyWorkReport.SHIFT_NIGHT,
)

SHIFT_META = {
    DailyWorkReport.SHIFT_MORNING: {
        'label': 'Ca sáng',
        'time_range': '7h30 – 18h',
        'description': 'Ca chính ban ngày',
    },
    DailyWorkReport.SHIFT_OVERTIME: {
        'label': 'Tăng ca',
        'time_range': '18h – 22h',
        'description': 'Làm thêm sau ca sáng (bắt buộc đã có ca sáng cùng ngày)',
    },
    DailyWorkReport.SHIFT_NIGHT: {
        'label': 'Ca tối',
        'time_range': '18h – 5h sáng hôm sau',
        'description': 'Ca đêm — ngày báo cáo là ngày bắt đầu lúc 18h',
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
    try:
        return production_reports_for_day(employee, report_date).get(shift=shift)
    except DailyWorkReport.DoesNotExist:
        return None


def shift_display_label(shift: str) -> str:
    meta = SHIFT_META.get(shift)
    return meta['label'] if meta else shift


def can_start_production_shift(employee, report_date, shift: str) -> tuple[bool, str]:
    """Kiểm tra NV có được mở báo cáo ca mới không."""
    if shift not in PRODUCTION_SHIFT_ORDER:
        return False, 'Ca làm không hợp lệ.'

    existing = {
        row.shift: row
        for row in production_reports_for_day(employee, report_date)
    }

    if shift in existing:
        return True, ''

    if shift == DailyWorkReport.SHIFT_OVERTIME:
        if DailyWorkReport.SHIFT_MORNING not in existing:
            return False, 'Cần có báo cáo ca sáng cùng ngày trước khi nhập tăng ca.'
        return True, ''

    if shift == DailyWorkReport.SHIFT_NIGHT:
        for blocked in (DailyWorkReport.SHIFT_MORNING, DailyWorkReport.SHIFT_OVERTIME):
            if blocked in existing:
                return False, 'Ca tối không áp dụng khi đã có ca sáng hoặc tăng ca cùng ngày.'
        return True, ''

    if shift == DailyWorkReport.SHIFT_MORNING:
        if DailyWorkReport.SHIFT_NIGHT in existing:
            return False, 'Đã có báo cáo ca tối cùng ngày — không thể mở ca sáng.'
        return True, ''

    return False, 'Ca làm không hợp lệ.'


def build_shift_picker_options(employee, report_date, *, can_edit: bool) -> list[dict]:
    """Danh sách ca cho màn chọn — gồm trạng thái và nút hành động."""
    existing = {
        row.shift: row
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
            enabled = can_edit and not (
                report.status == DailyWorkReport.STATUS_SUBMITTED
                and report.hod_reviewed
            )
            status_label = 'Đã gửi' if report.status == DailyWorkReport.STATUS_SUBMITTED else 'Đang nhập'
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
