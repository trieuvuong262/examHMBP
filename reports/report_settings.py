"""Đọc thiết lập chung báo cáo SX (singleton DB)."""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal, InvalidOperation


def load_report_settings():
    from reports.models import ReportsGeneralSettings

    return ReportsGeneralSettings.load()


def report_bool(field: str, default: bool = True) -> bool:
    cfg = load_report_settings()
    return bool(getattr(cfg, field, default))


def report_int(field: str, default: int = 0, *, min_v: int = 0, max_v: int = 10_000) -> int:
    cfg = load_report_settings()
    try:
        n = int(getattr(cfg, field, default) or default)
    except (TypeError, ValueError):
        n = default
    return max(min_v, min(max_v, n))


def report_decimal(field: str, default: str | Decimal = '0') -> Decimal:
    cfg = load_report_settings()
    raw = getattr(cfg, field, None)
    try:
        return Decimal(str(raw if raw is not None else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(default))


def report_auto_submit_time() -> time:
    cfg = load_report_settings()
    value = getattr(cfg, 'auto_submit_time', None)
    if isinstance(value, time):
        return value
    return time(23, 30)


def report_approve_deadline_hours() -> int:
    return report_int('approve_deadline_hours', 24, min_v=1, max_v=168)


def report_auto_reject_deadline_hours() -> int:
    approve_h = report_approve_deadline_hours()
    reject_h = report_int('auto_reject_deadline_hours', 24, min_v=1, max_v=168)
    return max(reject_h, approve_h)


def report_employee_edit_deadline_hours() -> int:
    return report_int('employee_edit_deadline_hours', 24, min_v=1, max_v=168)


def report_unapprove_deadline_days() -> int:
    return report_int('unapprove_deadline_days', 7, min_v=1, max_v=90)


def report_auto_reject_window() -> timedelta:
    return timedelta(hours=report_auto_reject_deadline_hours())


def report_approve_window() -> timedelta:
    return timedelta(hours=report_approve_deadline_hours())


def report_employee_edit_window() -> timedelta:
    return timedelta(hours=report_employee_edit_deadline_hours())


def report_manager_edit_window() -> timedelta:
    return timedelta(days=report_unapprove_deadline_days())


def report_default_declared_work_hours() -> Decimal:
    return report_decimal('default_declared_work_hours', '9.50')


def report_work_hours_min() -> Decimal:
    return report_decimal('work_hours_min', '7.50')


def report_work_hours_max() -> Decimal:
    return report_decimal('work_hours_max', '16')


def workers_may_edit_stage_time() -> bool:
    return report_bool('workers_may_edit_stage_time', True)


def managers_may_edit_stage_time() -> bool:
    return report_bool('managers_may_edit_stage_time', True)


def auto_approve_proxy_reports() -> bool:
    return report_bool('auto_approve_proxy_reports', True)
