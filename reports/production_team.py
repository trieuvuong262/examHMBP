"""Team view — báo cáo sản xuất theo ca."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count, Exists, OuterRef, Subquery, Sum, Value, DecimalField
from django.db.models.functions import Coalesce

from reports.models import DailyWorkReport, ProductionHourlyQuantity, ReportComment
from reports.period_utils import PERIOD_DAY
from reports.production_shift_policy import (
    PRODUCTION_SHIFT_ORDER,
    production_reports_for_day,
    shift_badge_class,
    shift_display_label,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.team_utils import (
    build_report_team_department_groups,
    daily_report_visible_to_team,
    department_filter_choices,
    meaningful_daily_reports_qs,
)
from reports.week_utils import monday_of

PRODUCTION_WEEK_WORK_DAYS = 6  # Thứ 2 – Thứ 7


def build_production_reports_by_employee(reports_qs) -> dict[int, list[DailyWorkReport]]:
    by_employee: dict[int, list[DailyWorkReport]] = defaultdict(list)
    for report in reports_qs:
        by_employee[report.employee_id].append(report)
    return dict(by_employee)


def _visible_reports(reports: list[DailyWorkReport], visible_fn) -> list[DailyWorkReport]:
    return [report for report in reports if _visible_report(report, visible_fn)]


def _shift_badges_for_reports(reports: list[DailyWorkReport]) -> list[dict]:
    badges: list[dict] = []
    shifts_present = {report.shift for report in reports}
    for shift in PRODUCTION_SHIFT_ORDER:
        if shift in shifts_present:
            badges.append({
                'shift': shift,
                'label': shift_display_label(shift),
                'badge_class': shift_badge_class(shift),
            })
    return badges


def _aggregate_production_row(reports: list[DailyWorkReport], visible_fn) -> dict:
    visible = _visible_reports(reports, visible_fn)
    visible.sort(
        key=lambda report: (
            PRODUCTION_SHIFT_ORDER.index(report.shift)
            if report.shift in PRODUCTION_SHIFT_ORDER
            else len(PRODUCTION_SHIFT_ORDER)
        )
    )
    total_qty = sum(int(getattr(report, 'total_qty', 0) or 0) for report in visible)
    primary = visible[0] if visible else None
    all_submitted = bool(visible) and all(
        report.status == DailyWorkReport.STATUS_SUBMITTED for report in visible
    )
    any_submitted = any(
        report.status == DailyWorkReport.STATUS_SUBMITTED for report in visible
    )
    all_reviewed = bool(visible) and all(report.hod_reviewed for report in visible)
    has_manager_comment = any(getattr(report, 'has_manager_comment', False) for report in visible)
    has_employee_reply = any(getattr(report, 'has_employee_reply', False) for report in visible)
    return {
        'report': primary,
        'production_reports': visible,
        'production_report_count': len(visible),
        'production_total_qty': total_qty,
        'production_all_submitted': all_submitted,
        'production_any_submitted': any_submitted,
        'production_all_reviewed': all_reviewed,
        'production_has_manager_comment': has_manager_comment,
        'production_has_employee_reply': has_employee_reply,
        'shift_badges': _shift_badges_for_reports(visible),
    }


def _visible_report(report, visible_fn) -> DailyWorkReport | None:
    if report and visible_fn(report):
        return report
    return None


def _reports_by_employee_date(
    reports: list[DailyWorkReport],
) -> dict[date, list[DailyWorkReport]]:
    by_date: dict[date, list[DailyWorkReport]] = defaultdict(list)
    for report in reports:
        by_date[report.report_date].append(report)
    return dict(by_date)


def _iter_dates(date_from: date, date_to: date):
    day = date_from
    while day <= date_to:
        yield day
        day += timedelta(days=1)


def _append_production_member_rows(
    rows: list[dict],
    member,
    reports: list[DailyWorkReport],
    visible_fn,
    *,
    date_from: date,
    date_to: date,
) -> None:
    by_date = _reports_by_employee_date(reports)
    if by_date:
        for report_date in sorted(_iter_dates(date_from, date_to), reverse=True):
            rows.append({
                'member': member,
                'report_date': report_date,
                **_aggregate_production_row(by_date.get(report_date, []), visible_fn),
            })
        return
    rows.append({
        'member': member,
        'report_date': None,
        **_aggregate_production_row([], visible_fn),
    })


def _ensure_team_members_in_groups(groups: list[dict], team) -> list[dict]:
    """Đảm bảo mọi NV trong queryset team đều có trong một nhóm hiển thị."""
    team_users = list(team.select_related('profile', 'profile__department'))
    if not team_users:
        return groups

    indexed = {user.pk: user for user in team_users}
    covered = {member.pk for group in groups for member in group['members']}
    missing = [indexed[pk] for pk in indexed if pk not in covered]
    if not missing:
        return groups

    groups = [dict(group, members=list(group['members'])) for group in groups]
    other = next((group for group in groups if group['key'] == 'other'), None)
    if other is None:
        groups.append({
            'key': 'other',
            'department_id': None,
            'label': 'Khác',
            'subtitle': '',
            'members': missing,
        })
    else:
        other['members'] = sorted(
            {member.pk: member for member in other['members'] + missing}.values(),
            key=lambda user: (
                (getattr(getattr(user, 'profile', None), 'full_name', '') or user.username).lower(),
                user.username.lower(),
            ),
        )
    return groups


def build_production_team_department_groups(
    viewer,
    team,
    reports_by_employee: dict[int, list[DailyWorkReport]],
    visible_fn,
    *,
    date_from: date,
    date_to: date,
    dept_filter: str = '',
):
    all_groups = build_report_team_department_groups(viewer, team)
    dept_choices = department_filter_choices(all_groups)
    groups = (
        build_report_team_department_groups(viewer, team, dept_filter=dept_filter)
        if dept_filter else all_groups
    )
    groups = _ensure_team_members_in_groups(groups, team)
    department_groups = []
    for group in groups:
        rows = []
        for member in group['members']:
            reports = reports_by_employee.get(member.id, [])
            _append_production_member_rows(
                rows,
                member,
                reports,
                visible_fn,
                date_from=date_from,
                date_to=date_to,
            )
        department_groups.append({**group, 'rows': rows})
    return department_groups, dept_choices


def production_team_submitted_count(
    reports_by_employee: dict[int, list[DailyWorkReport]],
    visible_fn,
    *,
    team_count: int,
) -> tuple[int, int]:
    submitted = 0
    for reports in reports_by_employee.values():
        if _aggregate_production_row(reports, visible_fn)['production_any_submitted']:
            submitted += 1
    missing = team_count - submitted
    return submitted, missing


def production_team_row_is_submitted(row, *, submitted_status: str, shift_filter: str = '') -> bool:
    reports = row.get('production_reports') or []
    if not reports and row.get('report'):
        reports = [row['report']]
    return any(report.status == submitted_status for report in reports)


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


def build_production_day_shift_tabs(
    report: DailyWorkReport,
    *,
    detail_url_name: str,
    list_query: str = '',
) -> list[dict]:
    """Tab chuyển ca trong trang chi tiết — cùng NV + ngày."""
    from django.urls import reverse

    if not report.is_production_report:
        return []

    siblings = list(production_reports_for_day(report.employee, report.report_date))
    siblings.sort(
        key=lambda row: (
            PRODUCTION_SHIFT_ORDER.index(row.shift)
            if row.shift in PRODUCTION_SHIFT_ORDER
            else len(PRODUCTION_SHIFT_ORDER)
        )
    )
    if len(siblings) <= 1:
        return []

    tabs = []
    for sibling in siblings:
        url = reverse(detail_url_name, args=[sibling.pk])
        if list_query:
            url = f'{url}?{list_query}'
        tabs.append({
            'pk': sibling.pk,
            'shift': sibling.shift,
            'label': shift_display_label(sibling.shift),
            'badge_class': shift_badge_class(sibling.shift),
            'is_active': sibling.pk == report.pk,
            'url': url,
        })
    return tabs


def _production_total_qty_subquery():
    return (
        ProductionHourlyQuantity.objects.filter(product__report_id=OuterRef('pk'))
        .values('product__report_id')
        .annotate(total=Sum('quantity'))
        .values('total')[:1]
    )


def query_production_team_reports(team_ids, date_from, date_to):
    if not team_ids:
        return DailyWorkReport.objects.none()
    return (
        meaningful_daily_reports_qs()
        .filter(
            employee_id__in=team_ids,
            report_date__gte=date_from,
            report_date__lte=date_to,
            report_profile=REPORT_PROFILE_PRODUCTION,
            report_period=PERIOD_DAY,
        )
        .order_by('-report_date', '-id')
        .select_related('employee', 'employee__profile')
        .annotate(
            line_count=Count('lines'),
            total_qty=Coalesce(
                Subquery(_production_total_qty_subquery()),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
            has_manager_comment=Exists(
                ReportComment.objects.filter(daily_report=OuterRef('pk')).exclude(author_id=OuterRef('employee_id')),
            ),
            has_employee_reply=Exists(
                ReportComment.objects.filter(daily_report=OuterRef('pk'), author_id=OuterRef('employee_id')),
            ),
        )
        .prefetch_related('production_products__hourly_entries')
    )
