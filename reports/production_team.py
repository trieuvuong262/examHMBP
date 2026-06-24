"""Team view — báo cáo sản xuất theo ca."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count, Q, Sum

from reports.models import DailyWorkReport
from reports.period_utils import PERIOD_DAY
from reports.production_hourly import active_product
from reports.production_shift_policy import PRODUCTION_SHIFT_ORDER, shift_display_label
from reports.production_slots import slot_count_for_shift
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.team_utils import (
    build_report_team_department_groups,
    daily_report_visible_to_team,
    department_filter_choices,
    meaningful_daily_reports_qs,
)
from reports.week_utils import monday_of

PRODUCTION_WEEK_WORK_DAYS = 6  # Thứ 2 – Thứ 7


def parse_team_shift_filter(request) -> str:
    shift = (request.GET.get('shift') or '').strip().upper()
    if shift in PRODUCTION_SHIFT_ORDER:
        return shift
    return ''


def production_shift_filter_choices() -> list[dict]:
    return [
        {'value': '', 'label': 'Tất cả ca'},
        *[
            {'value': shift, 'label': shift_display_label(shift)}
            for shift in PRODUCTION_SHIFT_ORDER
        ],
    ]


def build_production_reports_by_employee(reports_qs) -> dict[int, dict[str, DailyWorkReport]]:
    by_employee: dict[int, dict[str, DailyWorkReport]] = defaultdict(dict)
    for report in reports_qs:
        by_employee[report.employee_id][report.shift] = report
    return dict(by_employee)


def _visible_report(report, visible_fn) -> DailyWorkReport | None:
    if report and visible_fn(report):
        return report
    return None


def _filled_slot_counts(report: DailyWorkReport) -> tuple[int, int]:
    total = slot_count_for_shift(report.shift)
    if not report.shift_started_at:
        return 0, total
    product = active_product(report)
    if not product:
        return 0, total
    filled = product.hourly_entries.filter(
        Q(quantity__gt=0) | ~Q(zero_reason=''),
    ).count()
    return filled, total


def build_shift_cell(report: DailyWorkReport | None) -> dict:
    if report is None:
        return {
            'status': 'missing',
            'status_label': 'Chưa báo cáo',
            'badge_class': 'bg-danger-subtle text-danger',
            'slot_label': '',
            'report': None,
        }
    if report.status == DailyWorkReport.STATUS_SUBMITTED:
        status = 'submitted'
        status_label = 'Đã nộp'
        badge_class = 'bg-success-subtle text-success'
    else:
        status = 'draft'
        status_label = 'Nháp'
        badge_class = 'bg-warning-subtle text-warning'

    filled, total = _filled_slot_counts(report)
    slot_label = ''
    if report.shift_started_at and total:
        slot_label = f'{filled}/{total}'

    return {
        'status': status,
        'status_label': status_label,
        'badge_class': badge_class,
        'slot_label': slot_label,
        'report': report,
    }


def production_shift_stats(
    team_count: int,
    reports_by_employee: dict[int, dict[str, DailyWorkReport]],
    visible_fn,
) -> list[dict]:
    stats = []
    for shift in PRODUCTION_SHIFT_ORDER:
        submitted = 0
        for reports in reports_by_employee.values():
            report = _visible_report(reports.get(shift), visible_fn)
            if report and report.status == DailyWorkReport.STATUS_SUBMITTED:
                submitted += 1
        stats.append({
            'shift': shift,
            'label': shift_display_label(shift),
            'submitted': submitted,
            'missing': team_count - submitted,
            'team_count': team_count,
        })
    return stats


def _primary_report(reports: dict[str, DailyWorkReport], visible_fn) -> DailyWorkReport | None:
    for shift in PRODUCTION_SHIFT_ORDER:
        report = _visible_report(reports.get(shift), visible_fn)
        if report:
            return report
    return None


def _report_for_shift_filter(
    reports: dict[str, DailyWorkReport],
    visible_fn,
    *,
    shift_filter: str,
) -> DailyWorkReport | None:
    if shift_filter:
        return _visible_report(reports.get(shift_filter), visible_fn)
    return _primary_report(reports, visible_fn)


def build_production_team_department_groups(
    viewer,
    team,
    reports_by_employee: dict[int, dict[str, DailyWorkReport]],
    visible_fn,
    *,
    shift_filter: str = '',
    dept_filter: str = '',
):
    all_groups = build_report_team_department_groups(viewer, team)
    dept_choices = department_filter_choices(all_groups)
    groups = (
        build_report_team_department_groups(viewer, team, dept_filter=dept_filter)
        if dept_filter else all_groups
    )
    department_groups = []
    for group in groups:
        rows = []
        for member in group['members']:
            reports = reports_by_employee.get(member.id, {})
            shift_cells = {
                shift: build_shift_cell(_visible_report(reports.get(shift), visible_fn))
                for shift in PRODUCTION_SHIFT_ORDER
            }
            shift_cell_list = [
                {
                    'shift': shift,
                    'label': shift_display_label(shift),
                    **shift_cells[shift],
                }
                for shift in PRODUCTION_SHIFT_ORDER
            ]
            report = _report_for_shift_filter(reports, visible_fn, shift_filter=shift_filter)
            visible_reports = [
                _visible_report(reports.get(shift), visible_fn)
                for shift in PRODUCTION_SHIFT_ORDER
            ]
            visible_reports = [r for r in visible_reports if r]
            total_qty = sum(int(getattr(r, 'total_qty', 0) or 0) for r in visible_reports)
            rows.append({
                'member': member,
                'report': report,
                'reports_by_shift': reports,
                'shift_cells': shift_cells,
                'shift_cell_list': shift_cell_list,
                'production_multi_shift': not shift_filter,
                'production_total_qty': total_qty,
            })
        department_groups.append({**group, 'rows': rows})
    return department_groups, dept_choices


def production_team_submitted_count(
    reports_by_employee: dict[int, dict[str, DailyWorkReport]],
    visible_fn,
    *,
    shift_filter: str,
    team_count: int,
) -> tuple[int, int]:
    submitted = 0
    for reports in reports_by_employee.values():
        report = _report_for_shift_filter(reports, visible_fn, shift_filter=shift_filter)
        if report and report.status == DailyWorkReport.STATUS_SUBMITTED:
            submitted += 1
    missing = team_count - submitted
    return submitted, missing


def production_team_row_is_submitted(row, *, submitted_status: str, shift_filter: str = '') -> bool:
    if shift_filter:
        cell = row.get('shift_cells', {}).get(shift_filter, {})
        report = cell.get('report')
    elif row.get('production_multi_shift'):
        cell = row.get('shift_cells', {}).get(DailyWorkReport.SHIFT_MORNING, {})
        report = cell.get('report')
    else:
        report = row.get('report')
    return bool(report and report.status == submitted_status)


def expected_morning_days_through(anchor: date) -> int:
    week_start = monday_of(anchor)
    count = 0
    for offset in range(PRODUCTION_WEEK_WORK_DAYS):
        day = week_start + timedelta(days=offset)
        if day > anchor:
            break
        count += 1
    return count


def build_production_week_rollup(
    team_ids: list[int],
    anchor_date: date,
    visible_fn,
) -> dict[int, dict]:
    if not team_ids:
        return {}

    week_start = monday_of(anchor_date)
    week_end = week_start + timedelta(days=PRODUCTION_WEEK_WORK_DAYS - 1)
    submitted_dates: dict[int, set[date]] = defaultdict(set)
    reports = meaningful_daily_reports_qs().filter(
        employee_id__in=team_ids,
        report_date__gte=week_start,
        report_date__lte=week_end,
        report_profile=REPORT_PROFILE_PRODUCTION,
        report_period=PERIOD_DAY,
        shift=DailyWorkReport.SHIFT_MORNING,
        status=DailyWorkReport.STATUS_SUBMITTED,
    )
    for report in reports:
        if visible_fn(report):
            submitted_dates[report.employee_id].add(report.report_date)

    expected = expected_morning_days_through(anchor_date)
    rollup = {}
    for employee_id in team_ids:
        done = len(submitted_dates.get(employee_id, set()))
        missing = max(0, expected - done)
        rollup[employee_id] = {
            'submitted_days': done,
            'expected_days': expected,
            'missing_days': missing,
            'is_complete': missing == 0,
            'warning': (
                f'Thiếu {missing} ngày ca sáng tuần này'
                if missing > 0 and expected > 0 else ''
            ),
        }
    return rollup


def query_production_team_reports(team_ids, report_date):
    if not team_ids:
        return DailyWorkReport.objects.none()
    return (
        meaningful_daily_reports_qs()
        .filter(
            employee_id__in=team_ids,
            report_date=report_date,
            report_profile=REPORT_PROFILE_PRODUCTION,
            report_period=PERIOD_DAY,
        )
        .select_related('employee', 'employee__profile')
        .annotate(
            line_count=Count('lines'),
            total_qty=Sum('lines__quantity'),
        )
        .prefetch_related('production_products__hourly_entries')
    )
