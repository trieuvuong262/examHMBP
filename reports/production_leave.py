"""Đánh dấu nghỉ phép — báo cáo SX theo ngày."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from reports.models import ProductionDayLeaveMark
from reports.production_hourly import can_proxy_enter_daily_report


def build_production_leave_dates_by_employee(
    team_ids: list[int],
    date_from: date,
    date_to: date,
) -> dict[int, set[date]]:
    if not team_ids:
        return {}
    by_employee: dict[int, set[date]] = defaultdict(set)
    for emp_id, report_date in (
        ProductionDayLeaveMark.objects.filter(
            employee_id__in=team_ids,
            report_date__gte=date_from,
            report_date__lte=date_to,
        ).values_list('employee_id', 'report_date')
    ):
        by_employee[emp_id].add(report_date)
    return dict(by_employee)


def is_production_day_on_leave(
    employee_id: int,
    report_date: date | None,
    leave_dates_by_employee: dict[int, set[date]] | None,
) -> bool:
    if not report_date or not leave_dates_by_employee:
        return False
    return report_date in leave_dates_by_employee.get(employee_id, set())


def mark_production_day_leave(viewer, employee, report_date: date) -> ProductionDayLeaveMark:
    if not can_proxy_enter_daily_report(viewer, employee):
        raise PermissionError('Không có quyền đánh dấu nghỉ phép.')
    mark, _created = ProductionDayLeaveMark.objects.update_or_create(
        employee=employee,
        report_date=report_date,
        defaults={'marked_by': viewer},
    )
    return mark


def unmark_production_day_leave(viewer, employee, report_date: date) -> bool:
    if not can_proxy_enter_daily_report(viewer, employee):
        raise PermissionError('Không có quyền hủy đánh dấu nghỉ phép.')
    deleted, _ = ProductionDayLeaveMark.objects.filter(
        employee=employee,
        report_date=report_date,
    ).delete()
    return deleted > 0


def clear_production_day_leave(employee_id: int, report_date: date) -> None:
    """Gỡ đánh dấu khi NV/quản lý tạo báo cáo cho ngày đó."""
    ProductionDayLeaveMark.objects.filter(
        employee_id=employee_id,
        report_date=report_date,
    ).delete()


def production_team_leave_no_report_counts(
    department_groups: list[dict],
    *,
    exempt_no_report_ids: set[int] | None = None,
) -> dict[str, int]:
    """Đếm dòng NV×ngày: nghỉ phép / chưa báo cáo (trước khi lọc status)."""
    exempt = exempt_no_report_ids or set()
    on_leave = 0
    no_report = 0
    for group in department_groups:
        for row in group.get('rows') or []:
            if row.get('production_report_count', 0) > 0:
                continue
            if row.get('production_on_leave'):
                on_leave += 1
            elif row['member'].pk not in exempt:
                no_report += 1
    return {'on_leave': on_leave, 'no_report': no_report}
